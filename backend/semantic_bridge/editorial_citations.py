"""Kitaba sor cevabındaki sayfa atıfları: her atıf hangi kitabın, o sayfa o kitapta var mı (ZEKI-43).

Sorun: cevap tek bir kitap kimliği taşıyordu (`editorial_books._row` → `bookId`); ekran cevaptaki BÜTÜN sayfa
rozetlerini o kitaba bağlıyordu. Seçili kitapla başka bir kitap karşılaştırılınca ikinci kitabın sayfaları da seçili
kitabın sayfası olarak açılıyordu. Ayrıca «(s. 114, 127)» gibi çoklu atıfta yalnız ilk sayı rozet oluyordu.

Kural (ekrandaki `src/canvas/editorial/citations.ts` ile aynı, genel; kitap adı/sayfa bilgisi kodda yoktur):
- Atıf grubu: «s. 14», «[s.2]», «s. 12-14», «(s. 114, 127)», «ss. 3, 5 ve 9», «sayfa 7», «[s.3 p2]».
- Grubun kitabı: metinde gruptan ÖNCE en son anılan aday kitap (kitabın adı, katalogdaki kısa adı ya da yayınevi adı;
  Türkçe harf ve büyük/küçük farkı yok sayılır). Hiç anılmadıysa seçili kitap; seçili yoksa tek aday varsa o.
- Doğrulama: cevap bittiğinde her (kitap, sayfa) çifti için o kitabın son okumasında sayfa var mı bakılır. Yoksa ekran
  rozeti «kaynaksız» gösterir; bağlantı hatasında «bilinmiyor» kalır (rozet eskisi gibi önizleme dener).

Motor (kitap sohbeti) cevapta yalnız son metni döndürür; hangi sayfaların kanıt aramasından geldiği köprüye gelmez.
Bu yüzden «kanıta bağlı» denetim burada sayfanın o kitapta var olmasıdır; kanıt listesinin kendisi değildir.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Iterable, Optional

import httpx

log = logging.getLogger("semantic.editorial_citations")

# ------------------------------------------------------------------ atıf grubu (ekrandaki citations.ts ile aynı desen)
_PREFIX = r"(?:ss\.|sf\.|syf\.|s\.|sayfa(?:lar)?)"
_ITEM = r"\d+(?:[ \t]?[-–—][ \t]?\d+)?(?:[ \t]?p[ \t]?\d+)?"
# Ek sayı yalnız ardından ondalık ya da kelime gelmiyorsa atıftır: «s. 14, 3 kişi» → yalnız 14.
_MORE = (r"(?:(?:[ \t]*[,;/&][ \t]*|[ \t]+(?:ve|ile)[ \t]+)(?:(?:ss|sf|syf|s)\.[ \t]?)?"
         r"\d+(?:[ \t]?[-–—][ \t]?\d+)?(?:[ \t]?p[ \t]?\d+)?"
         r"(?![ \t]*[.,]\d)(?![ \t]+(?!(?:ve|ile)[ \t]+\d)[^\W\d_]))")
GROUP = re.compile(rf"\[?(?<![^\W_]){_PREFIX}[ \t]?{_ITEM}{_MORE}*\]?", re.I)
_PAGE_ITEM = re.compile(r"(\d+)(?:[ \t]?p[ \t]?\d+)?", re.I)


def groups(text: str) -> list[tuple[int, int, list[int]]]:
    """(başlangıç, bitiş, sayfalar) — metindeki sırayla. Aralık («12-14») iki uç sayfa olarak döner."""
    out = []
    for m in GROUP.finditer(text or ""):
        pages = [int(x.group(1)) for x in _PAGE_ITEM.finditer(m.group(0))]
        pages = [p for p in pages if p >= 1]
        if pages:
            out.append((m.start(), m.end(), pages))
    return out


# ------------------------------------------------------------------ kitap adı eşleme
_TR = str.maketrans({"ı": "i", "İ": "i", "I": "i", "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ö": "o", "Ö": "o",
                     "ş": "s", "Ş": "s", "ü": "u", "Ü": "u"})


def norm(s: Optional[str]) -> str:
    """Türkçe harfler sadeleşir, büyük/küçük farkı ve noktalama gider: «Anne Terliği'nde» → «anne terligi nde»,
    «dedem-tekrar-cocuk-oldu» → «dedem tekrar cocuk oldu»."""
    s = unicodedata.normalize("NFKD", (s or "").translate(_TR).lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^0-9a-z]+", " ", s).split())


def card_names(card: dict) -> list[str]:
    names = [card.get("title") or "", ((card.get("publisher") or {}).get("title") or "")]
    return list(dict.fromkeys(n for n in (norm(x) for x in names) if n))


def _last_mention(segment: str, books: list[dict]) -> Optional[str]:
    """Parçada en son anılan kitap (anılışın BİTTİĞİ yer en sağda olan; eşitse uzun ad). Yoksa None."""
    body = f" {norm(segment)} "
    best: tuple[int, int, Optional[str]] = (-1, -1, None)
    for b in books:
        for n in b["names"]:
            i = body.rfind(f" {n} ")
            if i >= 0:
                cand = (i + len(n), len(n), b["id"])
                if cand[:2] > best[:2]:
                    best = cand
    return best[2]


def resolve(text: str, books: list[dict], default_id: Optional[str]) -> list[tuple[Optional[str], list[int]]]:
    """Her atıf grubunun kitabı (metindeki sırayla): gruptan önce en son anılan aday, yoksa varsayılan."""
    out, current, pos = [], default_id, 0
    for start, end, pages in groups(text):
        current = _last_mention(text[pos:start], books) or current
        out.append((current, pages))
        pos = end
    return out


def candidates(cards: Iterable[dict], book_title: Optional[str], question: str, answer: str) -> tuple[list[dict], Optional[str]]:
    """Aday kitaplar: seçili kitap + adı soruda ya da cevapta geçen kitaplar. Varsayılan: seçili kitap; seçili
    yoksa tek aday. Seçili kitap katalogda tek karşılık bulamazsa varsayılan yoktur (tahmin edilmez)."""
    body = f" {norm(question)} {norm(answer)} "
    selected = norm(book_title)
    books, default_id, exact = [], None, []
    for c in cards:
        names = card_names(c)
        if not names or not c.get("id"):
            continue
        if selected and selected in names:
            exact.append(c)
        if (selected and selected in names) or any(f" {n} " in body for n in names):
            books.append({"id": str(c["id"]), "title": (c.get("publisher") or {}).get("title") or c.get("title"),
                          "names": names})
    if selected:
        default_id = str(exact[0]["id"]) if len(exact) == 1 else None
    elif len(books) == 1:
        default_id = books[0]["id"]
    return books, default_id


def verify(pairs: Iterable[tuple[str, int]], exists: Callable[[str, int], Optional[bool]]) -> dict[str, dict[str, bool]]:
    """Her (kitap, sayfa) için var/yok. Bağlantı hatası (None) yazılmaz: ekran onu «bilinmiyor» sayar."""
    todo = sorted(set(pairs))
    out: dict[str, dict[str, bool]] = {}
    if not todo:
        return out
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="editorial-cite") as pool:
        for (book_id, page), ok in zip(todo, pool.map(lambda p: exists(*p), todo)):
            if ok is not None:
                out.setdefault(book_id, {})[str(page)] = ok
    return out


def page_exists(book_id: str, page_no: int) -> Optional[bool]:
    """Kitabın son okumasında sayfanın görseli var mı (önizlemenin açacağı görselin aynısı, küçük boy)."""
    from . import editorial_cards
    try:
        editorial_cards.page(book_id, page_no, 48)
        return True
    except httpx.HTTPStatusError as e:
        # Yalnız kart servisinin «bu sayfa yok» cevabı (404) kaynaksız sayılır.
        return False if e.response is not None and e.response.status_code == 404 else None
    except Exception as e:  # noqa: BLE001 — bağlantı hatası atıfı düşürmez, «bilinmiyor» kalır
        log.info("citation page check failed %s/%s: %s", book_id, page_no, e)
        return None


def build(question: str, book_title: Optional[str], answer: Optional[str], *,
          cards: Optional[list[dict]] = None, check: Optional[Callable[[str, int], Optional[bool]]] = None) -> Optional[dict[str, Any]]:
    """Cevabın atıf özeti: {books, defaultId, pages}. Katalog okunamazsa None (ekran eski davranışa döner).
    `check` verilmezse sayfa varlığı sorulmaz (eski kayıtlar için hızlı yol)."""
    if not answer:
        return None
    try:
        if cards is None:
            from . import editorial_cards
            if not os.environ.get("EDITOR_CATALOG_BASE"):
                return None
            cards = editorial_cards.catalogue_cached()
        books, default_id = candidates(cards, book_title, question, answer)
    except (ValueError, KeyError, TypeError, httpx.HTTPError) as e:
        log.info("citation catalogue failed: %s", e)
        return None
    pages: dict[str, dict[str, bool]] = {}
    if check is not None:
        pairs = [(bid, p) for bid, ps in resolve(answer, books, default_id) if bid for p in ps]
        pages = verify(pairs, check)
    return {"books": books, "defaultId": default_id, "pages": pages}
