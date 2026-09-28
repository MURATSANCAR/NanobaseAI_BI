"""Portal belge okuma: portalın (köprünün) yüklediği belgenin sayfa sayfa metni — ortak yapı taşı 4.

Portalda şartname (M33), özgeçmiş (M55), sektör raporu (M39), sertifika (M57) gibi belgeler yüklenir. Metin katmanı
olan sayfa katmandan okunur; katmanı olmayan (taranmış) ya da katmanı bozuk sayfa, kitap okumasında ölçülerek seçilen
OCR okuyucusuyla (`settings().ocr_alias`, models.yaml 99–104: 39 zor sayfada %2,3 kelime hatası, döngü yok) okunur.

Çıktı her sayfa için: metin, kaynak (`text` = metin katmanı, `ocr` = görüntüden okuma, `none` = okunamadı) ve güven.
Güven OCR'da modelin yazdığı token'ların olasılıklarının geometrik ortalamasıdır (`exp(ortalama logprob)`); model
olasılık vermezse `None` («ölçülemedi»). Metin katmanında 1,0 değil `None` yazılır: katman okunan değil basılan
metindir, güveni ölçülmez; ekranda «metin» etiketi yeterli.

Gizlilik: belge (ör. özgeçmiş) kişisel veri taşıyabilir. Bu yol modele giden isteği ve cevabı `ed.model_call`
defterine YAZMAZ (kitap okumasının aksine); yalnız sayfa sayısı ve süre günlüğe düşer. Dosya diske yazılmaz, bellekte
işlenir. Maskeleme portalda, metin herhangi bir sohbet modeline gitmeden önce yapılır (İK: `hr_recruit_text`).

Bu modül kitaba özel değildir; kitap okuma hattını (document.py) değiştirmez, yalnız onun ölçülmüş parçalarını
(sayfa sağlığı, döngü kırpma, görüntü boyutu) kullanır.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import time
from pathlib import PurePath

from .config import settings

log = logging.getLogger("editor.portal_read")

PDF = "pdf"
IMAGE_TYPES = ("png", "jpg", "jpeg", "webp", "tif", "tiff")
FORMATS = (PDF,) + IMAGE_TYPES
#: Bu kadar harften az metin katmanı olan sayfa taranmış sayılır (başlık/sayfa numarası kadar metin katman sayılmaz).
MIN_PAGE_CHARS = int(os.environ.get("EDITOR_PORTAL_READ_MIN_CHARS", "20"))
MAX_TOKENS = int(os.environ.get("EDITOR_PORTAL_READ_MAX_TOKENS", "4096"))


class ReadError(ValueError):
    """Belgenin kendisiyle ilgili (açılamıyor, desteklenmeyen tür): yükleyene gösterilir."""


def fmt_of(file_name: str) -> str:
    ext = PurePath(file_name or "").suffix.lower().lstrip(".")
    if ext not in FORMATS:
        raise ReadError(f"Desteklenmeyen dosya türü: .{ext or '?'} (desteklenen: {', '.join(FORMATS)})")
    return ext


def _letters(text: str) -> int:
    return len(re.findall(r"[^\W\d_]", text or ""))


def page_needs_ocr(text: str) -> list[str]:
    """Metin katmanına güvenilmeyen sayfanın gerekçeleri; boş liste = katman okunur. Kitap okumasının ölçülmüş
    eşikleri (document.py): harf aralıklı, özel kodlu yazı tipi, bozuk kelime yapısı."""
    from .document import GARBLED_MAX, SPACED_MAX, _garbled_ratio, _spaced_ratio, layer_health

    if _letters(text) < MIN_PAGE_CHARS:
        return ["NO_TEXT_LAYER"]
    why = []
    if _garbled_ratio(text) > GARBLED_MAX:
        why.append("GARBLED_CHARACTERS")
    if _spaced_ratio(text) > SPACED_MAX:
        why.append("LETTER_SPACED")
    if layer_health(text).get("suspect"):
        why.append("SCRAMBLED_WORDS")
    return why


def plan(data: bytes, file_name: str) -> tuple[str, list[dict]]:
    """(tür, sayfalar). Sayfa: {page, text, reasons}; `reasons` boş değilse sayfa OCR ister."""
    import pymupdf

    kind = fmt_of(file_name)
    if not data:
        raise ReadError("Dosya boş.")
    if kind in IMAGE_TYPES:
        return "image", [{"page": 1, "text": "", "reasons": ["IMAGE"]}]
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ReadError("PDF açılamadı.") from e
    out = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        out.append({"page": i, "text": text.strip(), "reasons": page_needs_ocr(text)})
    return "pdf", out


def page_png(data: bytes, kind: str, page_no: int) -> bytes:
    """Sayfanın OCR'a giden görüntüsü: uzun kenar kitap okumasıyla aynı (`TARGET_LONG_SIDE_PX`)."""
    import pymupdf
    from .document import TARGET_LONG_SIDE_PX

    if kind == "image":
        try:
            pix = pymupdf.Pixmap(data)
        except Exception as e:  # noqa: BLE001
            raise ReadError("Görüntü açılamadı.") from e
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)
        if pix.n > 3:                                     # CMYK vb. → RGB
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        long_side = max(pix.width, pix.height)
        if long_side > TARGET_LONG_SIDE_PX:
            # küçültme: görüntüyü tek sayfalık PDF'e koyup hedef boyda yeniden çizmek pymupdf'in kararlı yolu
            doc = pymupdf.open()
            pg = doc.new_page(width=pix.width, height=pix.height)
            pg.insert_image(pg.rect, pixmap=pix)
            zoom = TARGET_LONG_SIDE_PX / long_side
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    doc = pymupdf.open(stream=data, filetype="pdf")
    page = doc[page_no - 1]
    zoom = TARGET_LONG_SIDE_PX / max(page.rect.width, page.rect.height)
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")


def confidence(logprobs: list[float]) -> float | None:
    """Token olasılıklarının geometrik ortalaması (0–1); olasılık yoksa None."""
    vals = [float(x) for x in logprobs if x is not None and not math.isnan(float(x))]
    if not vals:
        return None
    return round(math.exp(sum(vals) / len(vals)), 4)


def clean_ocr(text: str) -> tuple[str, int]:
    """OCR metni: biçim etiketleri atılır, döngüye giren tekrar tek kez tutulur (document._collapse_repeats)."""
    from .document import _collapse_repeats

    text = re.sub(r"<[^>]+>", " ", text or "")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    cut = 0
    out = []
    for b in blocks:
        b2, n = _collapse_repeats(b)
        cut += n
        out.append(b2.strip())
    return "\n\n".join(x for x in out if x), cut


async def ocr_png(png: bytes, page_no: int) -> dict:
    """Bir sayfa görüntüsünü OCR okuyucusuyla okur. Defter kaydı yok (belge kişisel veri taşıyabilir)."""
    from .llm import _post, image_part

    s = settings()
    req = {"model": s.ocr_alias, "max_tokens": MAX_TOKENS, "temperature": 0.0, "logprobs": True,
           "messages": [{"role": "user", "content": [image_part(png), {"type": "text", "text": s.ocr_prompt}]}]}
    r = await _post("/v1/chat/completions", req)
    if r.status_code >= 400:
        raise RuntimeError(f"OCR {r.status_code}: {r.text[:300]}")
    data = r.json()
    ch = data["choices"][0]
    raw = (ch.get("message") or {}).get("content") or ""
    lp = [t.get("logprob") for t in (((ch.get("logprobs") or {}).get("content")) or []) if isinstance(t, dict)]
    text, cut = clean_ocr(raw)
    return {"page": page_no, "text": text, "confidence": confidence(lp), "loopCharsRemoved": cut,
            "truncated": ch.get("finish_reason") == "length"}


async def read(data: bytes, file_name: str, *, ocr: bool = True, only_pages: list[int] | None = None) -> dict:
    """Belgenin sayfaları. `ocr=False`: yalnız metin katmanı (taranmış sayfa `none`). `only_pages`: OCR yalnız bu
    sayfalarda (köprü kendi okuyamadığı sayfaları gönderir); diğer sayfalar katmandan döner."""
    t0 = time.time()
    kind, pages = plan(data, file_name)
    want = set(only_pages or [])
    todo = [p for p in pages if p["reasons"] and ocr and (not want or p["page"] in want)]
    sem = asyncio.Semaphore(max(1, settings().page_concurrency))

    async def one(p: dict) -> dict:
        async with sem:
            png = await asyncio.to_thread(page_png, data, kind, p["page"])
            return await ocr_png(png, p["page"])

    results = await asyncio.gather(*(one(p) for p in todo), return_exceptions=True)
    by_page = {}
    errors = []
    for p, res in zip(todo, results):
        if isinstance(res, Exception):
            errors.append({"page": p["page"], "error": str(res)[:200]})
            continue
        by_page[p["page"]] = res
    out = []
    for p in pages:
        o = by_page.get(p["page"])
        if o is not None:
            out.append({"page": p["page"], "text": o["text"], "source": "ocr" if o["text"] else "none",
                        "confidence": o["confidence"], "reasons": p["reasons"], "truncated": o["truncated"]})
        elif p["reasons"]:
            # OCR istenmedi ya da düştü: katmanda okunur bir şey varsa (bozuk da olsa) boş bırakmak yerine işaretli verilir
            has = _letters(p["text"]) >= MIN_PAGE_CHARS
            out.append({"page": p["page"], "text": p["text"] if has else "", "source": "text" if has else "none",
                        "confidence": None, "reasons": p["reasons"], "truncated": False})
        else:
            out.append({"page": p["page"], "text": p["text"], "source": "text", "confidence": None,
                        "reasons": [], "truncated": False})
    log.info("portal belge okuma: %s sayfa, %s OCR, %s hata, %.1f sn", len(pages), len(by_page), len(errors),
             time.time() - t0)
    return {"kind": kind, "pageCount": len(pages), "pages": out, "ocrPages": sorted(by_page), "errors": errors,
            "seconds": round(time.time() - t0, 1)}
