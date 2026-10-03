"""E-kitap ↔ basılı kaynak karşılaştırması: basılı kitapta olup e-kitapta olmayan (ve tersi) metin, sayfasıyla.

Kaynak, okunmuş kitabın sayfa sayfa paragrafları (`ed.paragraph`); e-kitabın metni üretilen dosyanın okuma sırasındaki
belgelerinden (içindekiler hariç). Karşılaştırma kitaptan bağımsız: iki metin kelimelere ayrılır, ardışık `N` kelimelik
diziler eşlenir; hiçbir ortak diziye girmeyen ve en az `MIN_RUN` kelime süren parça «eksik» sayılır. Dizgi farkı
(satır sonu tirelemesi, tırnak biçimi, büyük/küçük harf) eksik sayılmaz.

Eksik parçanın sayfası okuma kaydındaki baskı kararıyla eşlenir (`manuscript.source.not_printed`: künye, içindekiler,
iç kapak, yazar tanıtımı, yayınevi tanıtımı). Bu nedenlerle çıkan parça «beklenen» olarak işaretlenir (e-kitapta yeri
yoktur ya da kendi sayfasında yeniden dizilir); nedeni olmayan parça editörün bakması gerekendir.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

N = 6
MIN_RUN = 8
PREVIEW = 240
TABLE_SHARE = 0.85                # kelimelerinin bu payı e-kitabın tablolarında geçen parça: tablo hücrelerinin sırası
CIRCUMFLEX = str.maketrans("âîû", "aiu")
EXPECTED = ("künye", "içindekiler", "iç kapak", "yayınevi tanıtımı", "hikâye dışı sayfa", "tablo düzeni", "dizin")
from .manuscript import _PROMO  # noqa: E402 - basılı kitabın baskı kuralındaki reklam tanımı

HYPHEN = re.compile(r"([a-zçğıöşüâîû])[-\u00ad]\s+([a-zçğıöşüâîû])")


def words(text: str) -> list[str]:
    text = (text or "").replace("\u00ad", "").replace("İ", "i").replace("I", "ı").lower()   # Türkçe küçük harf
    text = re.sub(r"(?<=[^\W\d_])\d{1,3}\b", "", text)          # kelimeye yapışık dipnot numarası («tarihinde138»)
    text = text.translate(CIRCUMFLEX)                            # «nâibi» = «naibi» (dizgi/okuma farkı)
    # Yalnız rakamdan oluşan kelime karşılaştırmaya girmez: dipnotlar e-kitapta kitap boyu yeniden numaralanır,
    # sayfa numarası e-kitapta yoktur; aranan eksik metindir.
    return [w for w in re.findall(r"\w+", HYPHEN.sub(r"\1\2", text)) if not w.isdigit()]   # «İ» casefold'da bölünür


def epub_table_words(path: Path) -> set[str]:
    z = zipfile.ZipFile(path)
    cells = []
    for n in z.namelist():
        if n.endswith(".xhtml"):
            cells += re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", z.read(n).decode("utf-8", "ignore"), re.S)
    return set(words(" ".join(re.sub(r"<[^>]+>", " ", c) for c in cells)))


def epub_text(path: Path) -> str:
    """E-kitabın okuma sırasındaki belgelerinin gövde metni (içindekiler belgesi hariç)."""
    from lxml import etree, html as lhtml
    z = zipfile.ZipFile(path)
    container = etree.fromstring(z.read("META-INF/container.xml"))
    opf_path = container.find(".//{*}rootfile").get("full-path")
    base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
    opf = etree.fromstring(z.read(opf_path))
    items = {i.get("id"): i for i in opf.iter("{*}item")}
    out, parser = [], lhtml.HTMLParser(encoding="utf-8")
    for ref in opf.iter("{*}itemref"):
        it = items.get(ref.get("idref"))
        if it is None or "nav" in (it.get("properties") or "").split():
            continue
        doc = lhtml.fromstring(z.read(base + it.get("href")), parser=parser)
        for el in doc.iter("br", "p", "h1", "h2", "h3", "li", "div", "section", "aside", "figure"):
            el.tail = " " + (el.tail or "")                    # paragraflar birbirine yapışmasın
        body = doc.find(".//body")
        out.append((body if body is not None else doc).text_content())
    return "\n".join(out)


def _runs(src: list[str], other: set[tuple[str, ...]]) -> tuple[list[tuple[int, int]], int]:
    cov = [False] * len(src)
    for i in range(len(src) - N + 1):
        if tuple(src[i:i + N]) in other:
            for j in range(i, i + N):
                cov[j] = True
    out, i = [], 0
    while i < len(src):
        if cov[i]:
            i += 1
            continue
        j = i
        while j < len(src) and not cov[j]:
            j += 1
        if j - i >= MIN_RUN:
            out.append((i, j))
        i = j
    return out, sum(cov)


def _grams(w: list[str]) -> set[tuple[str, ...]]:
    return {tuple(w[i:i + N]) for i in range(len(w) - N + 1)}


def compare(pages: list[tuple[int, str]], epub_txt: str, reasons: dict | None = None,
            table_words: set[str] | None = None) -> dict:
    """`pages`: [(sayfa, metin)] okuma sırasıyla; `reasons`: {sayfa: baskıya girmeme nedeni}; `table_words`: e-kitabın
    tablolarındaki kelimeler (okunmuş metin tablo hücrelerini başka sırayla verir; kısa parçanın kelimeleri tabloda
    geçiyorsa eksik değil, tablo düzeni farkıdır)."""
    reasons = {int(k): v for k, v in (reasons or {}).items()}
    sw, sp = [], []
    for no, text in pages:
        w = words(text)
        sw += w
        sp += [no] * len(w)
    ew = words(epub_txt)
    miss, cov = _runs(sw, _grams(ew))
    extra, _ = _runs(ew, _grams(sw))
    parts = []
    for a, b in miss:                     # sayfanın içindeki yayınevi reklamı (karekod…) kendi parçası olur:
        m = _PROMO.search(" ".join(sw[a:b]))                     # önündeki metin eksik, reklam beklenen
        cut = a + len(" ".join(sw[a:b])[:m.start()].split()) if m else a
        parts += ([(a, cut, None)] if cut - a >= MIN_RUN else []) + [(cut if cut - a >= MIN_RUN else a, b, bool(m))]
    missing = []
    for a, b, promo in parts:
        first, last = sp[a], sp[b - 1]
        why = [reasons.get(sp[k]) for k in range(a, b)]          # kelimelerin çoğunun sayfasındaki neden
        reason = max(set(why), key=why.count)
        if reason is None and promo:
            reason = "yayınevi tanıtımı"
        if reason is None and table_words and sum(1 for w in sw[a:b] if w in table_words) >= TABLE_SHARE * (b - a):
            reason = "tablo düzeni"
        missing.append({"pages": [first, last], "words": b - a, "reason": reason,
                        "expected": reason in EXPECTED, "text": " ".join(sw[a:b])[:PREVIEW]})
    unexpected = [m for m in missing if not m["expected"]]
    return {"source_words": len(sw), "epub_words": len(ew),
            "covered": round(cov / len(sw), 4) if sw else None,
            "missing": missing, "missing_words": sum(m["words"] for m in unexpected),
            "missing_parts": len(unexpected),
            "extra": [{"words": b - a, "text": " ".join(ew[a:b])[:PREVIEW]} for a, b in extra]}


def source_pages(generation_id: str, heads: bool = True) -> list[tuple[int, str]]:
    """Okunmuş kitabın sayfaları. `heads=False`: sayfa üst başlıkları çıkar (en az 3 sayfada aynen tekrarlanan, en çok
    8 kelimelik paragraf: kitap ya da bölüm adı; e-kitapta yoktur, karşılaştırmada eksik sayılmaz)."""
    from .. import db
    rows = db.all_rows("SELECT page_no, text FROM ed.paragraph WHERE generation_id=%s ORDER BY page_no, idx",
                       generation_id)
    pages: dict[int, list[str]] = {}
    for r in rows:
        pages.setdefault(int(r["page_no"]), []).append(r["text"] or "")
    if not heads:
        import collections
        seen = collections.Counter(" ".join(words(t)) for ts in pages.values() for t in set(ts) if len(t.split()) <= 8)
        rep = {k for k, n in seen.items() if n >= 3 and k}
        pages = {p: [t for t in ts if " ".join(words(t)) not in rep] for p, ts in pages.items()}
    return [(p, "\n".join(t)) for p, t in sorted(pages.items())]


def for_job(d: Path, epub_path: Path) -> dict | None:
    """Okunmuş kitaptan gelen işte karşılaştırma; Word'den gelen işte basılı kaynak yok (None)."""
    from . import studio
    ms = studio.read(d, "manuscript.json") or {}
    src = ms.get("source") or {}
    gid = src.get("generation_id") if src.get("kind") == "generation" else None
    if not gid:
        return None
    pages = source_pages(gid, heads=False)
    reasons = src.get("not_printed")
    if reasons is None:
        reasons = _reasons_now(pages, src.get("non_story_pages") or [], ms)
    from .manuscript import index_pages
    reasons = {**reasons, **{str(p): "dizin" for p in index_pages(dict(pages))}}   # e-kitapta dizin yok
    return compare(pages, epub_text(epub_path), reasons, epub_table_words(epub_path))


def _reasons_now(pages: list[tuple[int, str]], non_story: list[int], ms: dict) -> dict:
    """Baskı kararı kaydı olmayan (eski) işte bugünkü baskı kuralı: okumanın hikâye dışı dediği sayfalardan yalnız
    künye, içindekiler, iç kapak, tanıtım ve reklam olanlar «beklenen»; ötekiler (yazarın notu, önsöz…) basılı
    kitabın içeriğidir, e-kitapta yoksa eksik sayılır."""
    from .manuscript import print_plan
    by_page = {p: [t for t in text.split("\n") if t.strip()] for p, text in pages}
    names = [ms.get("author") or ""] + [str((ms.get("meta") or {}).get(k) or "") for k in ("TRANSLATOR", "EDITOR")]
    plan = print_plan(by_page, set(non_story), max(by_page) if by_page else 0, [ms.get("title") or ""], names)
    return {p: why for p, (why, keep) in plan.items() if keep == 0}
