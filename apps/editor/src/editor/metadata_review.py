"""Künye iddialarının (METADATA) okunurken gözden geçirilmesi — kitaptan bağımsız, model yok (2026-10-03, 56 kitap
denetimi). İddia silinmez; kart ve kitap adı kuralı onu şöyle okur:

- **Dizi sloganı / dizi adı:** aynı TITLE değeri birden çok farklı kitabın künyesinde (≥ `SERIES_MIN_BOOKS`)
  geçiyorsa («iyi ki kitaplarım var…»: yayınevinin dizi sloganı) o değer kitabın adı değildir: kartta `SERIES`
  sayılır (`flag='SHARED_TITLE'`), Kitaba sor'un kitap adları ve `book_title`'ın künye adayları arasına girmez.
- **Dizi adı:** TITLE aynı künyenin SERIES değeriyle aynıysa («ALPARSLAN’IN AKINCISI») kitabın adı değildir.
- **Dizinin başka kitabı:** TITLE kitabın hiçbir adına (kayıt adı, CRM adı/parçaları, dosya adı) uymuyor ama onlarla
  bir anlamlı kelime (dizi adı) paylaşıyorsa («Filippo …»), TITLE «dizi kitabı» olarak işaretlenir
  (`flag='SERIES_BOOK'`): kitabın adı sayılmaz; `book_title` onu zaten «künyede farklı ad» diye gözden geçire düşürür.
- **Kişi adı yayınevi:** PUBLISHER değeri kitabın bir kişisinin adıysa (künyenin AUTHOR/ILLUSTRATOR/TRANSLATOR
  iddiaları, CRM yazar/çizerleri) ya da kişi adı biçimindeyse (2–3 büyük harfle başlayan kelime, yayın/yayınları/
  kitap/basım… sözcüğü yok) ve başka hiçbir kitabın yayınevi değilse reddedilir (karttan düşer).
- **Kitap adı yazar adına karışmış:** AUTHOR değerinin sonu kitap adının başıyla çakışıyorsa («Çiğdem Can İcat»)
  çakışan kelimeler kırpılır — yalnız kalan ad kitabın bilinen bir kişisiyse (CRM yazarı vb.).
"""
from __future__ import annotations

import re
import time
import unicodedata

#: Bir TITLE değeri bu kadar farklı kitabın künyesinde geçiyorsa kitap adı değil, dizi adı/slogandır.
SERIES_MIN_BOOKS = 3
#: Yayınevi adında geçen kurum sözcükleri (katlanmış, ön ek olarak): bunlardan biri varsa kişi adı sayılmaz.
_PUBLISHER_WORDS = ("yayin", "kitap", "basim", "basim", "matbaa", "press", "book", "publish", "yayincilik", "ltd",
                    "sti", "a s", "grup", "dagitim", "medya", "egitim", "kultur", "vakf", "dernek", "ajans",
                    "studyo", "akademi", "sanat", "cocuk", "genc", "dergi", "edition", "verlag", "editions")
#: Anlamlı kelime sayılmayanlar (dizi adı karşılaştırması)
_STOP = frozenset({"ve", "ile", "bir", "bu", "su", "o", "da", "de", "ki", "mi", "icin", "gibi", "kitap", "kitabi",
                   "cilt", "seri", "dizi", "the", "and", "of", "a"})

_TR = str.maketrans("çğıöşüâîûÇĞİIÖŞÜÂÎÛ", "cgiosuaiuCGIIOSUAIU")


def fold(text: str | None) -> str:
    """Karşılaştırma anahtarı: küçük harf, Türkçe harfler sade, noktalama yok, tek boşluk."""
    t = unicodedata.normalize("NFKC", text or "").replace("İ", "i").replace("I", "ı").lower().translate(_TR)
    return " ".join(re.findall(r"[a-z0-9]+", t))


def _words(text: str | None) -> list[str]:
    return [w for w in fold(text).split() if len(w) >= 3 and w not in _STOP and not w.isdigit()]


# ------------------------------------------------------------------ kitaplar arası sayım (salt okuma)
_CTX: dict = {"at": 0.0, "value": None}
CONTEXT_TTL = 600.0


def context(c, now: float | None = None) -> dict:
    """{'shared': {katlanmış TITLE: kitap sayısı ≥ SERIES_MIN_BOOKS}, 'publishers': {katlanmış PUBLISHER: kitap
    sayısı}} — bütün nesillerin doğrulanmış künyesinden, tek sorgu. Süreç içinde `CONTEXT_TTL` saniye saklanır."""
    now = time.monotonic() if now is None else now
    if _CTX["value"] is not None and now - _CTX["at"] < CONTEXT_TTL:
        return _CTX["value"]
    rows = c.execute(
        "SELECT m.subject, m.claim, bv.book_id FROM ed.claim m JOIN ed.generation g ON g.id=m.generation_id"
        " JOIN ed.book_version bv ON bv.id=g.book_version_id WHERE m.kind='METADATA'"
        " AND m.subject IN ('TITLE','PUBLISHER') AND m.status IN ('VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED')"
    ).fetchall()
    books: dict[tuple, set] = {}
    for r in rows:
        k = fold(r["claim"])
        if k:
            books.setdefault((r["subject"], k), set()).add(str(r["book_id"]))
    value = {"shared": {k: len(v) for (s, k), v in books.items() if s == "TITLE" and len(v) >= SERIES_MIN_BOOKS},
             "publishers": {k: len(v) for (s, k), v in books.items() if s == "PUBLISHER"}}
    _CTX.update(at=now, value=value)
    return value


# ------------------------------------------------------------------ kurallar (saf)
def person_like(value: str, people: list[str] = (), known_publishers: dict[str, int] | None = None) -> bool:
    """Yayınevi alanı bir kişi adı mı: kitabın kişilerinden birinin adı, ya da 2–3 kelime, hepsi büyük harfle
    başlayan harf dizisi, kurum sözcüğü yok ve (biliniyorsa) başka hiçbir kitabın yayınevi değil."""
    k = fold(value)
    if not k:
        return False
    if any(k == fold(p) for p in people if p and len(fold(p).split()) >= 2):
        return True
    raw = re.sub(r"\s+", " ", value or "").strip()
    words = raw.split(" ")
    if not 2 <= len(words) <= 3 or not all(re.fullmatch(r"[A-ZÇĞİÖŞÜÂÎÛ][a-zçğıöşüâîû]+\.?", w) for w in words):
        return False
    if any(p in k for p in _PUBLISHER_WORDS):
        return False
    return not known_publishers or known_publishers.get(k, 0) <= 1


def trim_author(author: str, titles: list[str], people: list[str] = ()) -> str:
    """Yazar değerinin sonu kitap adının kelimeleriyle çakışıyorsa («Çiğdem Can Icat» + «Mucitler ve İcat
    Öyküleri») çakışan
    kelimeler atılır — yalnız kırpılmış ad kitabın bilinen bir kişisiyse (CRM yazarı/çizeri, künyenin başka kişi
    iddiası): soyadı kitap adının ilk kelimesi olan yazar («Ali Kaya» + «Kaya Gibi») kırpılmaz. Yazar en az iki
    kelime kalır; değer zaten bilinen bir kişiyse dokunulmaz."""
    known = {fold(p) for p in people if p}
    if not known or fold(author) in known:
        return author or ""
    words = re.sub(r"\s+", " ", author or "").strip().split(" ")
    fa = [fold(w) for w in words]
    best = 0
    for t in titles:
        ft = fold(t).split()
        for n in range(min(len(words) - 2, len(ft)), 0, -1):
            # kitap adının içinde art arda duran kelimeler («Mucitler ve İcat Öyküleri» ← «… Icat»)
            if all(fa[-n:]) and any(ft[i:i + n] == fa[-n:] for i in range(len(ft) - n + 1)):
                best = max(best, n)
                break
    cut = " ".join(words[:-best]) if best else ""
    return cut if cut and fold(cut) in known else (author or "")


#: Okuma hatalı yazımı aynı ad sayan benzerlik («Bir Delinin Sınar Günluğu» = «… Sınav Günlüğü»)
FIT_RATIO = 0.85


def fits_any(claim: str, names: list[str]) -> bool:
    """TITLE kitabın adlarından birine uyuyor mu: boşluksuz anahtarda biri öbürünü içeriyor ya da harf benzerliği
    ≥ `FIT_RATIO` (tek-iki harflik okuma hatası)."""
    from difflib import SequenceMatcher
    k = fold(claim).replace(" ", "")
    if not k:
        return False
    for n in names:
        nk = fold(n).replace(" ", "")
        if nk and (k == nk or (len(nk) >= 4 and nk in k) or (len(k) >= 4 and k in nk)
                   or SequenceMatcher(None, k, nk).ratio() >= FIT_RATIO):
            return True
    return False


def series_book(claim: str, names: list[str]) -> bool:
    """TITLE kitabın hiçbir adına uymuyor ama onlarla anlamlı bir kelime (dizi adı) paylaşıyor: dizinin başka
    kitabı. Hiç kelime paylaşmıyorsa bir şey söylenmez (künye yanlış sayfa da olabilir; book_title gözden geçirir)."""
    names = [n for n in names if n and n.strip()]
    if not names or fits_any(claim, names):
        return False
    have = set(_words(claim))
    return bool(have & {w for n in names for w in _words(n)})


def review(meta: list[dict], *, names: list[str] = (), people: list[str] = (),
           shared: dict[str, int] | None = None, publishers: dict[str, int] | None = None) -> list[dict]:
    """Kartın künye satırları gözden geçirilmiş: ortak TITLE → SERIES (flag SHARED_TITLE), dizi kitabı TITLE → flag
    SERIES_BOOK (subject TITLE kalır ama `book_title=False`), kişi adı PUBLISHER → atılır, AUTHOR kırpılır.
    `names`: kitabın kendi adları (kayıt, CRM, dosya). Girdi değişmez."""
    titles = [m.get("claim") or "" for m in meta if m.get("subject") == "TITLE"]
    series = {fold(m.get("claim")) for m in meta if m.get("subject") == "SERIES"} - {""}
    own = [n for n in names if n] + titles
    out = []
    for m in meta:
        subj, val = m.get("subject"), m.get("claim") or ""
        if subj == "TITLE" and shared and fold(val) in shared:
            out.append({**m, "subject": "SERIES", "flag": "SHARED_TITLE", "original_subject": "TITLE"})
            continue
        if subj == "TITLE" and fold(val) in series:
            # künyede TITLE = aynı künyenin dizi adı («ALPARSLAN'IN AKINCISI»): kitabın adı değil
            out.append({**m, "subject": "SERIES", "flag": "SERIES_NAME", "original_subject": "TITLE"})
            continue
        if subj == "TITLE" and series_book(val, names):
            out.append({**m, "flag": "SERIES_BOOK", "book_title": False})
            continue
        if subj == "PUBLISHER" and person_like(val, people, publishers):
            continue
        if subj == "AUTHOR":
            cut = trim_author(val, [t for t in own if t and fold(t) != fold(val)], people)
            if cut != val:
                out.append({**m, "claim": cut, "flag": "AUTHOR_TRIMMED", "original_claim": val})
                continue
        out.append(m)
    return out


def title_values(meta: list[dict]) -> list[str]:
    """Kitabın adı sayılabilecek künye TITLE değerleri (dizi sloganı ve dizi kitabı hariç)."""
    return [str(m["claim"]) for m in meta if m.get("subject") == "TITLE" and m.get("claim")
            and m.get("book_title", True) is not False]
