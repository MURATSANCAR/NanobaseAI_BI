"""Sayfa üst/alt bilgisi (running head / running foot): sayfanın kenarında tekrar eden kısa satır.

Sorun (2026-10-03 denetimi, 25 kitap): sayfa başlığı gövde metni sayılıyordu (`source._span` rolü hep `body`).
Dokuz kitapta yazar adı ya da kitap adı sayfaların %15–50'sinde metnin ilk paragrafıydı: yazar karakter oldu
(bir kitapta beş kayıt), bölüm adı bozuldu, özel ad testi saptı.

Kural (kitaptan bağımsız; yalnız sayfaların kendi dizilişi, ad listesi yok):
- Aday: sayfanın harf taşıyan İLK bloğu (üst) ya da — sayfada en az iki blok varsa — SON bloğu (alt); kısa
  (≤ `MAX_WORDS` sözcük, ≤ `MAX_CHARS` karakter), cümle gibi bitmeyen, konuşma çizgisi/tırnakla açılmayan satır.
- Karşılaştırma anahtarı: rakamlar (sayfa numarası «23 AYŞE OSMANOĞLU», «AYŞE OSMANOĞLU 24»), noktalama,
  boşluk ve aksan atılır, Türkçe küçük harf («DİJİTAL DÜNYADA E-BEVEYN» = «Dijital Dünyada E beveyn»).
- Kitap başlığı: aynı konumda (üst ya da alt) aynı anahtar, metinli sayfaların en az `MIN_SHARE` kadarında ve en
  az `MIN_PAGES` sayfada; ya tek/çift sayfaya bağlı (≥ `PARITY`: yazar adı sol, kitap adı sağ sayfada) ya da
  sayfaların en az `BOTH_SIDES` kadarında.
- Bölüm başlığı (sağ sayfada bölüm adı, sol sayfada kitap adı): kitap başlığı tek/çift sayfanın birine
  oturmuşsa, ÖTEKİ yüzdeki aynı konumda en az `SLOT_MIN` sayfada tekrar eden, o yüze bağlı (≥ `PARITY`) ve
  aralığında sık duran (aynı yüzdeki sayfaların en az yarısı) kısa satır da sayfa başlığıdır.

Aynı kuralı iki yer kullanır: `source` (okunan metin blokları: rol `running_head`) ve `chapters` (PDF dizgi
satırları: bölüm açılışı aranmadan önce ayıklanır); `page_scope` paragraf listesinde aynı ayıklamayı yapar.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

MIN_SHARE = 0.15
MIN_PAGES = 4
BOTH_SIDES = 0.30
PARITY = 0.8
SLOT_MIN = 3
MAX_WORDS = 10
MAX_CHARS = 80
#: tek sayfalık sorguda (source.load page_no=…) sayfa metninin yalnız kenarları okunur; aday zaten kısadır
WINDOW = 400
POSITIONS = ("top", "bottom")

_LETTER = re.compile(r"[^\W\d_]")
_BLOCK = re.compile(r"\S.*?(?=\n\s*\n|\Z)", re.S)


def key(text: str) -> str:
    """Karşılaştırma anahtarı: Türkçe küçük harf, aksansız, yalnız harfler (rakam/noktalama/boşluk atılır)."""
    t = (text or "").replace("İ", "i").replace("I", "ı").casefold().replace("ı", "i")
    t = unicodedata.normalize("NFKD", t)
    return "".join(ch for ch in t if ch.isalpha() and not unicodedata.combining(ch))


def candidate(text: str) -> bool:
    """Sayfa başlığı olabilecek kısa satır mı."""
    t = " ".join((text or "").split())
    # sözcük sayısı harf aralıklı dizgide («D İ J İ T A L») harf sayısıdır: aralıklı harfler tek sözcük sayılır
    words = len(re.sub(r"(?<=\b[^\W\d_]) (?=[^\W\d_]\b)", "", t).split())
    if not t or len(t) > MAX_CHARS or words > MAX_WORDS or len(key(t)) < 2:
        return False
    if t[0] in "—–-«“\"'‘„":
        return False                       # konuşma: «— Gel.»
    letters = [c for c in t if c.isalpha()]
    if re.search(r"[^.][.!?]$", t) and not (letters and all(c.isupper() for c in letters) and t[-1] == "?"):
        return False                       # cümle: «Kapıyı açtı.»; büyük harfli soru başlığı aday kalır
    return True                            # («GALİLEO’YU KİM ÖLDÜRDÜ?», bölüm adı sağ sayfa başlığında)


def _blocks(text: str) -> list[tuple[int, int]]:
    out = []
    for m in _BLOCK.finditer(text):
        end = m.end()
        while end > m.start() and text[end - 1].isspace():
            end -= 1
        out.append((m.start(), end))
    return out


def edge_blocks(head: str, tail: str, length: int) -> dict[str, tuple[int, int]]:
    """{konum: (başlangıç, bitiş)} — sayfa metninin harf taşıyan ilk ve son bloğu, metnin başından ofsetle.
    `head`/`tail` metnin ilk/son `WINDOW` karakteri (kısa metinde metnin kendisi). Pencerede bitmeyen blok aday
    değildir (uzundur). Yalnız sayfada en az iki harfli blok varsa: tek bloklu sayfa (başlık sayfası «AÇIKLIK»)
    sayfa başlığı taşımaz — bölüm adı sağ sayfaların başlığıysa bölümün kendi başlık sayfası ayıklanmasın."""
    out: dict[str, tuple[int, int]] = {}
    if length <= len(head):                       # bütün metin elde
        bl = [b for b in _blocks(head) if _LETTER.search(head[b[0]:b[1]])]
        if len(bl) >= 2:
            out["top"], out["bottom"] = bl[0], bl[-1]
        return out
    bl = [b for b in _blocks(head) if _LETTER.search(head[b[0]:b[1]])]
    if len(bl) >= 2:                              # ilk blok pencere içinde bitiyor
        out["top"] = bl[0]
    tb = _blocks(tail)
    lettered = [i for i, b in enumerate(tb) if _LETTER.search(tail[b[0]:b[1]])]
    if lettered and lettered[-1] > 0:             # önünde blok ayırıcısı var: tam blok
        s, e = tb[lettered[-1]]
        off = length - len(tail)
        out["bottom"] = (off + s, off + e)
    return out


def edge_texts(head: str, tail: str, length: int) -> dict[str, str]:
    """{konum: blok metni} — `edge_blocks`'un bulduğu kenar blokları, pencerelerden okunmuş."""
    out = {}
    off = length - len(tail)
    for pos, (s, e) in edge_blocks(head, tail, length).items():
        out[pos] = head[s:e] if e <= len(head) else tail[s - off:e - off]
    return out


def edges_of(text: str) -> dict[str, str]:
    """Tam metinden {konum: blok metni} (tek sayfalık sorguyla aynı pencere kuralı)."""
    text = text or ""
    return edge_texts(text[:WINDOW], text[-WINDOW:] if text else "", len(text))


def _parity_share(pages: list[int]) -> tuple[int, float]:
    odd = sum(p % 2 for p in pages)
    side = 1 if odd * 2 >= len(pages) else 0
    return side, (odd if side else len(pages) - odd) / max(1, len(pages))


def detect(edges: dict[int, dict[str, str]], text_pages: int | None = None) -> dict[int, set[str]]:
    """{sayfa: {konum}} — sayfa başlığı/altlığı olan kenar blokları. `edges`: {sayfa: {"top": metin,
    "bottom": metin}} (yalnız aday olabilecek kenarlar; olmayan konum yazılmaz). `text_pages`: metinli sayfa
    sayısı (varsayılan: edges'teki sayfa sayısı)."""
    n = text_pages if text_pages is not None else len(edges)
    if n <= 0:
        return {}
    need = max(MIN_PAGES, math.ceil(MIN_SHARE * n))
    marks: dict[int, set[str]] = {}
    for pos in POSITIONS:
        where: dict[str, list[int]] = {}
        for p, e in edges.items():
            t = e.get(pos)
            if t and candidate(t):
                where.setdefault(key(t), []).append(p)
        confirmed: dict[str, list[int]] = {}
        sides = Counter()
        for k, ps in where.items():
            if len(ps) < need:
                continue
            side, share = _parity_share(ps)
            if share >= PARITY:
                confirmed[k] = ps
                sides[side] += len(ps)
            elif len(ps) >= BOTH_SIDES * n:
                confirmed[k] = ps
                sides[0] += len(ps)
                sides[1] += len(ps)
        # bölüm başlığı: kitap başlığının oturmadığı yüzde, sık ve o yüze bağlı tekrar
        free = {s for s in (0, 1) if not sides[s]} if sides else set()
        for k, ps in where.items():
            if k in confirmed or len(ps) < SLOT_MIN or not free:
                continue
            side, share = _parity_share(ps)
            if side not in free or share < PARITY:
                continue
            same = [p for p in ps if p % 2 == side]
            span = (max(same) - min(same)) // 2 + 1
            if len(same) >= SLOT_MIN and len(same) * 2 >= span:
                confirmed[k] = same
        for ps in confirmed.values():
            for p in ps:
                marks.setdefault(p, set()).add(pos)
    return marks


def detect_texts(texts: dict[int, str]) -> dict[int, set[str]]:
    """Sayfa metinlerinden (bloklar boş satırla ayrılmış) `detect`."""
    edges = {p: edges_of(t) for p, t in texts.items() if t and t.strip()}
    return detect(edges, len(edges))


def detect_paragraphs(pages: dict[int, list[str]]) -> dict[int, set[str]]:
    """Paragraf listelerinden (`ed.paragraph`): ilk/son harfli paragraf kenar bloğudur."""
    edges = {}
    for p, paras in pages.items():
        ls = [t for t in paras if t and _LETTER.search(t)]
        if len(ls) >= 2:
            edges[p] = {"top": ls[0], "bottom": ls[-1]}
    return detect(edges, len(edges))


def has_heads(pages: list[dict]) -> bool:
    from .source import RUNNING_HEAD
    return any(s.get("role") == RUNNING_HEAD for p in pages for s in p.get("spans") or [])


def head_mention(m: dict, heads: dict[int, list[dict]], body: dict[int, list[dict]]) -> bool:
    """Anmanın kanıtı sayfa başlığından mı: metin kanıtının bağlı olduğu spanların hepsi sayfa başlığı/altlığı, ya
    da (span bağı yoksa) alıntı o sayfanın başlığında geçiyor, gövdesinde geçmiyor. Görsel kanıt gövdedir."""
    from .source import key as skey
    if (m.get("kind") or "TEXT") != "TEXT":
        return False
    p = m.get("page_no")
    hs, bs = heads.get(p) or [], body.get(p) or []
    if not hs:
        return False
    refs = [r.get("span_id") for r in ((m.get("source_refs") or {}).get("spans") or []) if r.get("span_id")]
    if refs:
        ids = {s["span_id"] for s in hs}
        return all(r in ids for r in refs)
    q = skey(m.get("quote") or "")
    return bool(q) and any(q in skey(s["text"]) for s in hs) and not any(q in skey(s["text"]) for s in bs)


def characters_only_in_heads(characters: list[dict], mentions: list[dict], pages: list[dict]) -> set[str]:
    """Bütün anmaları sayfa başlığından/altlığından gelen karakterlerin kimlikleri (salt hesap). Bu kuraldan önce
    okunmuş kitaplar için: yazar adı her sayfanın başında okundu, aynı yazar dört-beş ayrı kayıt oldu (2026-10-03
    denetimi). `mentions`: [{character_id, page_no, quote, kind, source_refs}] (anmanın kanıtı). Gövdede bir kez
    bile anılan karakter kalır; anması olmayan karakter hakkında hüküm yok (kalır)."""
    from .source import RUNNING_HEAD
    heads: dict[int, list[dict]] = {}
    body: dict[int, list[dict]] = {}
    for p in pages:
        for s in p.get("spans") or []:
            (heads if s.get("role") == RUNNING_HEAD else body).setdefault(p["page_no"], []).append(s)
    if not heads:
        return set()
    seen: dict[str, list[bool]] = {}
    for m in mentions:
        if m.get("character_id") is not None:
            seen.setdefault(str(m["character_id"]), []).append(head_mention(m, heads, body))
    ids = {str(ch["id"]) for ch in characters}
    return {cid for cid, flags in seen.items() if cid in ids and flags and all(flags)}


def strip_paragraphs(pages: dict[int, list[str]]) -> dict[int, list[str]]:
    """Paragraf listeleri, sayfa başlığı/altlığı paragrafları çıkarılmış (sıra korunur)."""
    marks = detect_paragraphs(pages)
    out = {}
    for p, paras in pages.items():
        m = marks.get(p)
        if not m:
            out[p] = list(paras)
            continue
        idx = [i for i, t in enumerate(paras) if t and _LETTER.search(t)]
        drop = {idx[0 if pos == "top" else -1] for pos in m}
        out[p] = [t for i, t in enumerate(paras) if i not in drop]
    return out
