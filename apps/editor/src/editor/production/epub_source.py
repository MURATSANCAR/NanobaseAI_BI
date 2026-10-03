"""Basılı kitabın e-kitabı: özgün kapak ve özgün künye (stüdyonun yeniden tasarımı yerine).

Yayınevinin e-kitapları basılı kitabın kendisidir: kapak yayınevinin kapağı, künyede kapak tasarımcısı ve iç tasarımcı
gerçek adlarıyla geçer. Okunmuş bir yayınevi kitabından açılan stüdyo işinde e-kitap varsayılan olarak böyle üretilir
(`epub_edit` «kaynak»); Word'den gelen ya da stüdyonun yeni tasarımı istenen işte stüdyonun kapağı ve künyesi kalır.

- **Kapak** (`original_cover`): yayınevi sitesinin kapak kütüphanesinden (`ed.cover_library`), basılı ISBN'le eşlenir.
  Adla eşleme yapılmaz: aynı adlı başka baskı/kitap vardır («Devlerin Savaşı» ↔ «Devlerin Savaşı - Efsane Savaşçı»).
- **Künye** (`print_kunye`): basılı kitabın künye sayfasının okunmuş paragraflarından, kuralla. Yayınevinin künyesinde
  her satır «BÜYÜK HARFLİ ETİKET + değer» biçimindedir («KAPAK TASARIMI Rabia Erdohan»); etiket satırın başındaki büyük
  harfli kelimelerdir. Basıma ait satırlar (baskı, ISBN, baskı ve cilt, matbaa) e-künyeye girmez; kitap adı/yazar ve
  tür satırı künyenin başlığında zaten vardır. Model çağrılmaz, metin olduğu gibi kalır (telif cümlesi yarım kalmaz).
"""

from __future__ import annotations

import re
import threading
from pathlib import Path

#: Basıma ait etiketler (e-künyeye girmez). «1. BASKI», «2. BASKI»… da baskıdır.
PRINT_LABELS = re.compile(r"^(\d+\.\s*)?BASKI$|^ISBN$|^BASKI VE C[İI]LT$|^MATBAA|^SERT[İI]F[İI]KA NO$")
#: Künyenin yayınevi ve dizi satırı: «TİMAŞ YAYINLARI | 6543 Edebiyat Kitaplığı - Dünya Edebiyatı Dizisi | 132».
SERIES = re.compile(r"^(?P<pub>[^|]+?)\s*\|\s*(?P<no>\d{1,6})\s+(?P<rest>.+)$")
#: Matbaa bloğu (etiketsiz devam paragrafı dahil): künyede yasal zorunluluk olan matbaa sertifikası satırı.
PRINTER = re.compile(r"matbaa sertifika", re.I)
SERIES_KEY = "__dizi__"
UPPER = re.compile(r"^[A-ZÇĞİÖŞÜÂÎÛ0-9][A-ZÇĞİÖŞÜÂÎÛ0-9.,'’()&/-]*$")


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def original_cover(ms) -> tuple[bytes, str, dict] | None:
    """Yayınevinin kapağı (kapak kütüphanesi, basılı ISBN eşleşmesiyle): (veri, uzantı, bilgi) ya da None."""
    isbn = digits((ms.meta or {}).get("ISBN"))
    if len(isbn) not in (10, 13):
        return None
    from .. import db
    from . import library
    rows = db.all_rows("SELECT id, isbn, title, image_w, image_h FROM ed.cover_library WHERE image_file IS NOT NULL "
                       "AND status <> 'hidden' AND regexp_replace(coalesce(isbn, ''), '[^0-9]', '', 'g') = %s", isbn)
    for r in rows:
        p = library.image_path(r["id"])
        if p is not None and p.exists():
            return p.read_bytes(), p.suffix.lower(), {"source": "yayınevi sitesi", "title": r["title"],
                                                      "width": r["image_w"], "height": r["image_h"]}
    return None


def split_label(text: str) -> tuple[str | None, str]:
    """«PROJE EDİTÖRÜ Ayşe Tuba Ayman» → ("PROJE EDİTÖRÜ", "Ayşe Tuba Ayman"); büyük harfli etiketi olmayan satır
    (None, metin). Etiket en çok 5 kelimedir; bütün satır büyük harfse etiket yoktur (başlık satırı)."""
    words = text.split()
    k = 0
    while k < len(words) and k < 5 and UPPER.match(words[k]) and not words[k].isdigit():
        k += 1
    if k == 0 or k == len(words):
        return None, text.strip()
    return " ".join(words[:k]), " ".join(words[k:]).strip()


def kunye_pages(src: dict, pages: list[tuple[int, str]]) -> list[int]:
    """Basılı künye sayfaları: okuma kaydının baskı kararı (`not_printed`), yoksa bugünkü baskı kuralı."""
    reasons = src.get("not_printed")
    if reasons is None:
        from .epub_compare import _reasons_now
        reasons = _reasons_now(pages, src.get("non_story_pages") or [], {"title": src.get("title")})
    return sorted(int(p) for p, why in reasons.items() if why == "künye")


def parse_kunye(paras: list[str], title: str = "", author: str = "") -> list[tuple[str | None, str]]:
    """Künye paragraflarından e-künye satırları [(etiket | None, değer)]: yayınevi-dizi satırından başlar (öncesi
    kitap adı, yazar, tür, yer-yıl), basıma ait etiketli satırlar düşer. Değeri boş etiket («ISBN» tek başına) düşer."""
    from .manuscript import _fold
    start = next((i for i, t in enumerate(paras) if SERIES.match(t.strip())), None)
    rows: list[tuple[str | None, str]] = []
    for t in paras[start:] if start is not None else paras:
        t = " ".join(t.split())
        if not t:
            continue
        if start is None and (_fold(t) in (_fold(title), _fold(f"{title} {author}"))):
            continue
        if SERIES.match(t):
            rows.append((SERIES_KEY, t))
            continue
        if PRINTER.search(t) or PRINT_LABELS.match(t):           # matbaa bloğunun devamı, tek başına «ISBN»
            continue
        label, value = split_label(t)
        if label and (PRINT_LABELS.match(label) or not value):
            continue
        rows.append((label, value))
    return rows


def print_kunye(d: Path) -> list[tuple[str | None, str]]:
    """Stüdyo işinin kaynağı okunmuş kitapsa basılı künye satırları; değilse boş liste."""
    from . import studio
    from .epub_compare import source_pages
    m = studio.read(d, "manuscript.json") or {}
    src = m.get("source") or {}
    if src.get("kind") != "generation" or not src.get("generation_id"):
        return []
    pages = source_pages(src["generation_id"])
    keep = set(kunye_pages({**src, "title": m.get("title")}, pages))
    paras = [t for p, text in pages if p in keep for t in text.split("\n") if t.strip()]
    return parse_kunye(paras, m.get("title") or "", m.get("author") or "")


# ------------------------------------------------------------------ basılı kitabın metni (dizgiyle)
#: Dizgi okumasının sürümü: kural değişince önbellek yeniden kurulur.
LAYOUT_VERSION = 9
CACHE = "basili.json"
_busy: set[str] = set()
_busy_lock = threading.Lock()


def _gid(d: Path) -> str | None:
    from . import studio
    src = (studio.read(d, "manuscript.json") or {}).get("source") or {}
    return src.get("generation_id") if src.get("kind") == "generation" else None


def _drop_back_ads(ms, signature: str | None, source: list[tuple[int, str]] | None = None) -> None:
    """Kitabın sonundaki yayınevi tanıtım sayfaları (yayınevi imzasıyla açılır: «iyi ki kitaplar var...») e-kitaba
    girmez; imza okunmuş kitabın son %15'indeki sayfalarda aranır (başındaki imza sayfası baskı kuralıyla zaten çıkar;
    imza küçük puntoyla dizildiyse dizgi katmanı onu sayfa başlığı sayıp gövdeden atmış olabilir, o yüzden okunmuş
    metne bakılır). İlk böyle sayfadan sonuna dek e-kitaba girmez."""
    if not signature:
        return
    from .manuscript import _fold
    key = _fold(signature)
    pages = sorted({p for p, _ in source or []} or {p for c in ms.chapters for b in c.blocks for p in b.pages})
    if not pages or not key:
        return
    back = pages[-1] - max(5, (pages[-1] - pages[0]) * 15 // 100)
    hits = [p for p, t in source or [] if p >= back and any(_fold(x).startswith(key) for x in t.split("\n"))]
    cut = min(hits) if hits else None
    if cut is None:
        return
    for ch in ms.chapters:
        ch.blocks = [b for b in ch.blocks if not b.pages or b.pages[0] < cut]
    ms.chapters = [c for c in ms.chapters if c.blocks]


def print_bios(d: Path) -> list[dict]:
    """Basılı kitabın tanıtım sayfaları (baskı kuralının «yazar tanıtımı» dediği sayfalar) okunmuş metinden: her sayfa
    grubunda ilk kısa satır ad, gerisi metin. Model çıkarımı yok; e-kitap basılı kitabın tanıtımını aynen taşır."""
    from . import studio
    from .epub_compare import _reasons_now, source_pages
    m = studio.read(d, "manuscript.json") or {}
    src = m.get("source") or {}
    if src.get("kind") != "generation" or not src.get("generation_id"):
        return []
    pages = source_pages(src["generation_id"], heads=False)
    reasons = src.get("not_printed")
    if reasons is None:
        reasons = _reasons_now(pages, src.get("non_story_pages") or [], m)
    bio = {int(p) for p, why in reasons.items() if why == "yazar tanıtımı"}
    out: list[dict] = []
    for p, text in pages:
        if p not in bio:
            continue
        for t in (x.strip() for x in text.split("\n") if x.strip()):
            if len(t.split()) <= 8 and not t.endswith((".", ",", ";", ":")):
                out.append({"name": t, "text": ""})
            elif out:
                out[-1]["text"] = (out[-1]["text"] + "\n\n" + t).strip()
            else:
                out.append({"name": m.get("author") or "", "text": t})
    return [b for b in out if b["text"]]


def print_manuscript(d: Path, wait: bool = True, signature: str | None = None):
    """Basılı kitabın e-kitabının metni: okunmuş kitap dizgiyle (`manuscript.from_generation(layout=True)`: sayfa
    üst başlığı/numarası yok, dipnotlar bölüm sonunda, tablolar, şiir/epigraf/perde). Kitap adı, yazar ve kitap
    bilgisi stüdyonun el yazmasından (editörün düzeltmesi korunur). Sonuç `epub/basili.json`'da saklanır; büyük
    kitapta dakikalar sürebilir. `wait=False`: önbellek yoksa okumayı arka planda başlatır, None döner."""
    from . import studio
    from .manuscript import Block, Chapter, Manuscript, from_generation
    gid = _gid(d)
    if not gid:
        return None
    cache = studio.read(d / "epub", CACHE)
    base = studio._manuscript(d)
    if cache and cache.get("generation_id") == gid and cache.get("v") == LAYOUT_VERSION:
        chapters = [Chapter(c["title"], [Block(**b) for b in c["blocks"]], c.get("kind", "chapter"))
                    for c in cache["chapters"]]
        return Manuscript(base.title, base.author, base.illustrator, base.meta, chapters, base.source)

    def run():
        try:
            ms = from_generation(gid, layout=True)
            from .epub_compare import source_pages
            _drop_back_ads(ms, signature, source_pages(gid))
            (d / "epub").mkdir(exist_ok=True)
            studio.write(d / "epub", CACHE, {"generation_id": gid, "v": LAYOUT_VERSION,
                                             "chapters": [{"title": c.title, "kind": c.kind,
                                                           "blocks": [b.__dict__ for b in c.blocks]}
                                                          for c in ms.chapters]})
        finally:
            with _busy_lock:
                _busy.discard(str(d))
    with _busy_lock:
        running = str(d) in _busy
        if not running:
            _busy.add(str(d))
    if wait:
        if running:                                   # başka bir çağrı kuruyorsa bitmesini bekle
            import time
            while str(d) in _busy:
                time.sleep(1)
        else:
            run()
        return print_manuscript(d, wait=False, signature=signature)
    if not running:
        threading.Thread(target=run, daemon=True).start()
    return None
