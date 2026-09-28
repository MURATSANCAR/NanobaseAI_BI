"""Ortak yapı taşı 4 — belge okuma ve OCR hattı (portal tarafı; docs/analiz/ai-firsatlari/README.md).

Portalın bütün belge yüklemeleri için tek okuma işlevi: `read(dosya_adı, bayt)` → sayfa sayfa metin, her sayfada
**okuma** etiketi (`metin` = PDF'in metin katmanı / Word / düz metin, `ocr` = görüntüden okundu, `yok` = okunamadı) ve
**güven** (yalnız OCR'da; modelin yazdığı token olasılıklarının geometrik ortalaması, model vermezse `None`).

Yol: önce köprünün kendi okuyucusu (PDF metin katmanı `pypdf`, Word `.docx`, OpenDocument `.odt`, düz metin). Metin
katmanı olmayan PDF sayfası (harf sayısı `DOC_READ_MIN_PAGE_CHARS` altı) ve görüntü dosyası (JPG/PNG/TIFF/WebP),
GPU sunucusundaki editör kart servisinin `POST /v1/read` ucuna gönderilir; orada kitap okumasında ölçülerek seçilen OCR
okuyucusu okur (apps/editor/deploy/models.yaml 99–104; `apps/editor/src/editor/portal_read.py`). Bağlantı kitap
kartlarıyla aynıdır (`EDITOR_CATALOG_BASE` + anahtar + nginx başlığı, `editorial_cards._headers`); müşteri VM'inde
TT GPU nginx beyaz listesinde `/editor/cards/v1/read` location'ı gerekir (docs/analiz/ai-firsatlari/BELGE-OKUMA.md).

**Alıntı denetimi korunur:** modelin belgeden çıkardığı her alan/alıntı `find_quote` ile belgenin okunan metninde
birebir (Türkçe harf katlamalı, boşluk sadeleştirilmiş) aranır; bulunmayan atılır. Bulunan alıntının hangi sayfadan ve
hangi okumayla (metin/ocr) geldiği döner; OCR sayfasından gelen alan ekranda «OCR» etiketiyle görünür.

**Kişisel veri:** OCR bizim GPU'muzda koşar; kart servisi belge içeriğini modelin defterine yazmaz, dosyayı diske
yazmaz. Okunan metin bir sohbet modeline gitmeden önce çağıranın maskesinden geçer (İK: `hr_recruit_text`).

Ayarlar (Yönetim → «Zeki AI ortak araçlar»): `DOC_READ_OCR` (taranmış sayfa okunsun mu), `DOC_READ_TIMEOUT_SEC`,
`DOC_READ_MIN_PAGE_CHARS`, `DOC_READ_LOW_CONFIDENCE` (bu güvenin altındaki OCR sayfası «düşük güven» diye işaretlenir;
metin atılmaz, alıntı denetimi yine uygulanır).
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from xml.etree import ElementTree

log = logging.getLogger("semantic.doc_read")

READ_PATH = "/v1/read"
PDF = "pdf"
IMAGES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "tif": "image/tiff",
          "tiff": "image/tiff"}
TEXTS = ("docx", "odt", "txt", "md", "csv")
MAGIC = {"pdf": (b"%PDF",), "png": (b"\x89PNG",), "jpg": (b"\xff\xd8",), "jpeg": (b"\xff\xd8",),
         "webp": (b"RIFF",), "tif": (b"II*\x00", b"MM\x00*"), "tiff": (b"II*\x00", b"MM\x00*"),
         "docx": (b"PK",), "odt": (b"PK",)}

METIN, OCR, YOK = "metin", "ocr", "yok"
LABELS = {METIN: "Metin", OCR: "OCR", YOK: "Okunamadı"}

#: Uzak okuyucu: (dosya adı, bayt, OCR istenen sayfalar ya da None) → kart servisinin cevabı. Testte sahte verilir.
Remote = Callable[[str, bytes, Optional[list[int]]], dict]


class ReadError(ValueError):
    """Belgenin kendisiyle ilgili, kullanıcıya olduğu gibi gösterilecek hata."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def settings() -> dict[str, Any]:
    from semantic_bridge import admin as admin_mod

    def num(key: str, default: float, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(str(admin_mod.conf(key) or default).replace(",", "."))))
        except ValueError:
            return default

    return {"ocr": (admin_mod.conf("DOC_READ_OCR") or "1").strip().lower() not in ("0", "false", "hayir", "hayır", "off"),
            "timeout": int(num("DOC_READ_TIMEOUT_SEC", 900, 10, 7200)),
            "minChars": int(num("DOC_READ_MIN_PAGE_CHARS", 20, 1, 10000)),
            "lowConfidence": num("DOC_READ_LOW_CONFIDENCE", 0.80, 0.0, 1.0)}


def ext_of(filename: str) -> str:
    return (filename or "").rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


def letters(text: str) -> int:
    return len(re.findall(r"[^\W\d_]", text or ""))


def fold(s: Any) -> str:
    """Alıntı karşılaştırması: Türkçe küçük harf, aksansız, noktalama boşluk, tek boşluk (M33 `tenders.fold` ile aynı)."""
    import unicodedata

    t = str(s or "").replace("İ", "i").replace("I", "ı").lower()
    t = t.replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^0-9a-z]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ================================================================================ okuma sonucu


@dataclass
class Reading:
    """Belgenin okunmuş hâli. `pages`: [{"sayfa": "1", "metin": "…", "okuma": metin|ocr|yok, "guven": 0.93|None}]."""

    filename: str
    pages: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    low_confidence: float = 0.80

    def text(self) -> str:
        return "\n".join(p["metin"] for p in self.pages if p.get("metin"))

    @property
    def ocr_pages(self) -> list[str]:
        return [p["sayfa"] for p in self.pages if p["okuma"] == OCR]

    @property
    def unread_pages(self) -> list[str]:
        return [p["sayfa"] for p in self.pages if p["okuma"] == YOK]

    def low_pages(self) -> list[str]:
        return [p["sayfa"] for p in self.pages if p["okuma"] == OCR and p.get("guven") is not None
                and p["guven"] < self.low_confidence]

    def page_of(self, sayfa: str) -> Optional[dict[str, Any]]:
        return next((p for p in self.pages if p["sayfa"] == str(sayfa)), None)

    def summary(self) -> dict[str, Any]:
        """Ekrana giden okuma özeti (teknoloji adı yok): kaç sayfa, hangileri OCR, en düşük güven, okunamayanlar."""
        ocr = [p for p in self.pages if p["okuma"] == OCR]
        confs = [p["guven"] for p in ocr if p.get("guven") is not None]
        note = None
        if ocr:
            note = (f"{len(ocr)} sayfa taranmış görüntüden okundu (OCR)"
                    + (f"; en düşük güven %{round(min(confs) * 100)}" if confs else "; güven ölçülemedi") + ".")
        if self.unread_pages:
            note = ((note + " ") if note else "") + f"{len(self.unread_pages)} sayfa okunamadı."
        return {"sayfa": len(self.pages), "ocrSayfa": self.ocr_pages, "okunamayan": self.unread_pages,
                "dusukGuven": self.low_pages(), "enDusukGuven": round(min(confs), 4) if confs else None,
                "esik": self.low_confidence, "hatalar": list(self.errors), "not": note}


# ================================================================================ yerel okuma


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _odt_text(data: bytes) -> str:
    ns_text = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            root = ElementTree.fromstring(z.read("content.xml"))
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        raise ReadError("OpenDocument dosyası okunamadı.") from None
    return "\n".join("".join(el.itertext()) for el in root.iter() if el.tag in (f"{{{ns_text}}}p", f"{{{ns_text}}}h"))


def _docx_text(data: bytes) -> str:
    from semantic_bridge.contracts_docs import docx_text

    try:
        return docx_text(data)
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        raise ReadError("Word dosyası okunamadı.") from None


def pdf_pages(data: bytes) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        raise ReadError("PDF okuyucu bu kurulumda yok.", 503) from None
    try:
        reader = PdfReader(io.BytesIO(data))
        return [(p.extract_text() or "").strip() for p in reader.pages]
    except Exception as e:  # noqa: BLE001
        raise ReadError(f"PDF okunamadı: {str(e)[:120]}") from None


def check(filename: str, data: bytes, allowed: Optional[tuple[str, ...]] = None) -> str:
    ext = ext_of(filename)
    kinds = allowed or ((PDF,) + tuple(IMAGES) + TEXTS)
    if ext not in kinds:
        raise ReadError("Desteklenmeyen dosya türü: ." + (ext or "?") + " (desteklenen: " + ", ".join(kinds) + ").")
    if not data:
        raise ReadError("Dosya boş.")
    magic = MAGIC.get(ext)
    if magic and not any(data.startswith(m) for m in magic):
        raise ReadError("Dosyanın içeriği uzantısıyla uyuşmuyor.")
    return ext


def local_pages(filename: str, data: bytes, min_chars: int) -> list[dict[str, Any]]:
    """Köprünün kendi okuyabildiği: sayfa listesi; metni olmayan sayfa `yok` (OCR adayı)."""
    ext = ext_of(filename)
    if ext == PDF:
        return [{"sayfa": str(i), "metin": t if letters(t) >= min_chars else "",
                 "okuma": METIN if letters(t) >= min_chars else YOK, "guven": None}
                for i, t in enumerate(pdf_pages(data), start=1)]
    if ext in IMAGES:
        return [{"sayfa": "1", "metin": "", "okuma": YOK, "guven": None}]
    if ext == "docx":
        text = _docx_text(data)
    elif ext == "odt":
        text = _odt_text(data)
    else:
        text = _decode(data)
    text = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")).strip()
    return [{"sayfa": "1", "metin": text, "okuma": METIN if text else YOK, "guven": None}]


# ================================================================================ uzak okuyucu (GPU sunucusu)


def remote_available() -> bool:
    from semantic_bridge import editorial_cards

    try:
        editorial_cards._headers()
        return True
    except ValueError:
        return False


def remote_read(filename: str, data: bytes, pages: Optional[list[int]], timeout: float = 900.0) -> dict:
    """Kart servisinin `POST /v1/read` ucu (multipart). Kitap kartlarıyla aynı adres, anahtar ve CA."""
    import httpx

    from semantic_bridge import editorial_cards

    base, headers, ca = editorial_cards._headers()
    form = {"ocr": "auto"}
    if pages:
        form["pages"] = ",".join(str(p) for p in pages)
    mime = IMAGES.get(ext_of(filename), "application/pdf")
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0), verify=ca or True, follow_redirects=False) as client:
        r = client.post(base + READ_PATH, headers=headers, data=form, files={"file": (filename, data, mime)})
    if r.status_code == 422:
        try:
            msg = r.json().get("detail")
        except ValueError:
            msg = None
        raise ReadError(str(msg or "Belge okunamadı."))
    r.raise_for_status()
    if "json" not in (r.headers.get("content-type") or ""):
        # nginx beyaz listesinde yol yoksa varsayılan site 200 + HTML döner (bellek tt-gpu-nginx-card-whitelist)
        raise RuntimeError("belge okuma servisi JSON dönmedi (sunucu yönlendirmesi eksik olabilir)")
    return r.json()


def _merge(pages: list[dict[str, Any]], remote: dict) -> None:
    by = {int(p.get("page") or 0): p for p in remote.get("pages") or []}
    for p in pages:
        if p["okuma"] != YOK:
            continue
        o = by.get(int(p["sayfa"]))
        if not o:
            continue
        text = str(o.get("text") or "").strip()
        src = o.get("source")
        if text and src == "ocr":
            p.update(metin=text, okuma=OCR, guven=o.get("confidence"))
        elif text and src == "text":
            p.update(metin=text, okuma=METIN, guven=None)


# ================================================================================ tek giriş


def read(filename: str, data: bytes, *, ocr: Optional[bool] = None, remote: Optional[Remote] = None,
         allowed: Optional[tuple[str, ...]] = None, cfg: Optional[dict[str, Any]] = None) -> Reading:
    """Belgenin sayfa sayfa metni. Önce yerel okuma; okunamayan sayfalar (taranmış PDF sayfası, görüntü dosyası)
    OCR açıksa uzak okuyucuya gider. Uzak okuyucu yoksa ya da düşerse sayfa `yok` kalır ve nedeni `errors`'a yazılır —
    çağıran «okunamadı» diye gösterir, sessizce boş geçmez."""
    st = cfg or settings()
    check(filename, data, allowed)
    pages = local_pages(filename, data, st["minChars"])
    out = Reading(filename=filename, pages=pages, low_confidence=st["lowConfidence"])
    missing = [int(p["sayfa"]) for p in pages if p["okuma"] == YOK]
    want_ocr = st["ocr"] if ocr is None else (ocr and st["ocr"])
    if not missing or ext_of(filename) not in ((PDF,) + tuple(IMAGES)):
        return out
    if not want_ocr:
        out.errors.append("Taranmış sayfa okuma bu kurulumda kapalı (Yönetim → Zeki AI ortak araçlar).")
        return out
    if remote is None:
        if not remote_available():
            out.errors.append("Taranmış sayfa okuma servisi bu kurulumda bağlı değil.")
            return out
        remote = lambda n, d, p: remote_read(n, d, p, st["timeout"])  # noqa: E731
    try:
        res = remote(filename, data, missing if ext_of(filename) == PDF else None)
    except ReadError:
        raise
    except Exception as e:  # noqa: BLE001 — servis düşerse okunan kısım kalır, eksik açıkça yazılır
        log.warning("belge okuma: OCR servisi cevap vermedi (%s): %s", filename, str(e)[:300])
        out.errors.append("Taranmış sayfalar okunamadı: belge okuma servisi cevap vermedi.")
        return out
    _merge(out.pages, res)
    for e in res.get("errors") or []:
        out.errors.append(f"Sayfa {e.get('page')} okunamadı.")
    return out


def read_text(filename: str, data: bytes, **kw: Any) -> tuple[str, Reading]:
    r = read(filename, data, **kw)
    return r.text(), r


# ================================================================================ alıntı denetimi


def find_quote(quote: Any, reading: Reading, *, min_len: int = 8) -> Optional[dict[str, Any]]:
    """Alıntı belgede birebir (katlamalı) geçiyor mu; geçiyorsa hangi sayfada ve hangi okumayla. Sayfa sınırında
    bölünen alıntı için bütün metin de aranır (sayfa = ilk parçanın sayfası)."""
    q = fold(quote)
    if len(q) < min_len:
        return None
    for p in reading.pages:
        if p.get("metin") and q in fold(p["metin"]):
            return {"sayfa": p["sayfa"], "okuma": p["okuma"], "guven": p.get("guven")}
    whole = ""
    starts: list[tuple[int, dict[str, Any]]] = []
    for p in reading.pages:
        if not p.get("metin"):
            continue
        starts.append((len(whole), p))
        whole += fold(p["metin"]) + " "
    i = whole.find(q)
    if i < 0:
        return None
    page = next((p for s, p in reversed(starts) if s <= i), None)
    if page is None:
        return None
    return {"sayfa": page["sayfa"], "okuma": page["okuma"], "guven": page.get("guven")}


def quote_ok(quote: Any, reading: Reading, **kw: Any) -> bool:
    return find_quote(quote, reading, **kw) is not None


def label(okuma: Optional[str]) -> Optional[str]:
    return LABELS.get(okuma or "")
