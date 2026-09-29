"""Kitapsız pazarlama işi (M19 «Pazarlama görsel ve metin», üretim yolu B).

Stüdyoda işi olmayan kitap (backlist, kataloğun geri kalanı) için pazarlama kiti: el yazması yok; kitap bilgisi ve
metinler köprünün CRM'den okuduğu alanlardır (`new_kitapBase`: ad, yazar, özet, spot, en önemli cümle, alıntılar,
sosyal medya metni, hashtag), kapak köprünün getirdiği görseldir (CRM/e-ticaret görseli ya da kullanıcının yüklediği
yüksek çözünürlüklü dosya). Kitap metni bu işe hiç gelmez.

İş, stüdyonun türetilmiş iş kancasıyla açılır (`studio.new_job(extra={"kind": "marketing"})`, boyama kitabıyla aynı
yol); hat koşmaz, GPU harcamaz. İş klasörü pazarlama kitinin beklediği biçimdedir, böylece sosyal görsel uçları
(`/v1/studio/jobs/{job}/marketing/social…`) ve dizim (`marketing.render_social`) aynen çalışır:

- `manuscript.json`: başlık, yazar, tür (`meta.GENRE`, CRM `new_turlertext`), yaş üst sınırı (`meta.AGE_MAX`, varsa),
  tek «CRM metinleri» bölümü. Alıntı kartındaki alıntı bu metinlerde birebir aranır (`marketing.in_book`); kitabın
  metni olmadığı için alıntı yalnız CRM alanlarından olabilir.
- `girdi/kapak.png`: ön kapak (RGB PNG). Özeti (`sha256`) ve kaynağı `job.json`'da kayıtlı (kabul testi 3).
- `job.json` → `palette`: marka paleti (köprü gönderir) + kapaktan çıkarılan renkler (`palette.extract`).

Aynı stok kodu için ikinci istek yeni iş açmaz, var olanı günceller (metinler, kapak, palet). Stüdyonun iş listesi
bu işleri göstermez (`api.jobs`); yalnız pazarlama ekranı kullanır. Model görseli burada üretilmez: kapak gerçek
kapaktır, dizim modelsizdir.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import re
import time
from pathlib import Path

from . import marketing as mk
from . import studio

KIND = "marketing"
STOCK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,39}$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
COVER_MAX = 25 * 1024 * 1024
COVER_SIDE = 3000                    # en uzun kenar; daha büyüğü küçültülür (dizim 1800 px'e kadar okur)
TEXT_MAX = 20000
TEXTS = (("ozet", "Özet"), ("spot", "Kitap spotu"), ("onemli_cumle", "Kitabın en önemli cümlesi"),
         ("sosyal_medya", "Sosyal medya metni"))


class JobError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata (API 400)."""


def is_marketing(d: Path) -> bool:
    return (studio.read(d, "job.json") or {}).get("kind") == KIND


def find(stok_kodu: str) -> Path | None:
    """Bu stok kodunun kitapsız pazarlama işi (en yenisi)."""
    root = studio.root()
    if not root.exists():
        return None
    for d in sorted(root.iterdir(), reverse=True):
        j = studio.read(d, "job.json") if d.is_dir() else None
        if j and j.get("kind") == KIND and j.get("stok_kodu") == stok_kodu:
            return d
    return None


def _text(v, label: str) -> str:
    t = re.sub(r"[ \t]+", " ", str(v or "")).strip()
    if len(t) > TEXT_MAX:
        raise JobError(f"{label} çok uzun ({TEXT_MAX} karakteri aşıyor).")
    return t


def _paras(t: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n|\n", t or "") if p.strip()]


def manuscript(body: dict) -> dict:
    """Pazarlama kitinin okuduğu el yazması biçimi: tek bölüm, CRM metinleri paragraf paragraf."""
    title = _text(body.get("baslik"), "Kitap adı")
    if not title:
        raise JobError("Kitap adı gerekli.")
    texts = body.get("metinler") or {}
    if not isinstance(texts, dict):
        raise JobError("Metinler bir nesne olmalı.")
    blocks = []
    for key, label in TEXTS:
        for p in _paras(_text(texts.get(key), label)):
            blocks.append({"kind": "para", "text": p, "pages": []})
    quotes = texts.get("alinti") or []
    if isinstance(quotes, str):
        quotes = _paras(quotes)
    if not isinstance(quotes, list):
        raise JobError("Alıntılar liste olmalı.")
    for q in quotes:
        q = mk.clean_quote(_text(q, "Alıntı"))
        if q:
            blocks.append({"kind": "para", "text": q, "pages": []})
    meta = {"KIND": KIND}
    for key, field in (("GENRE", "tur"), ("PUBLISHER", "yayinevi"), ("ISBN", "isbn"), ("SERIES", "dizi")):
        v = _text(body.get(field), field)[:300]
        if v:
            meta[key] = v
    ozet = _text(texts.get("ozet"), "Özet")
    if ozet:
        meta["CRM_SUMMARY"] = ozet
    age = body.get("yas_ust")
    if age not in (None, ""):
        try:
            meta["AGE_MAX"] = max(1, min(99, int(age)))
        except (TypeError, ValueError):
            raise JobError("Yaş üst sınırı sayı olmalı.") from None
    return {"title": title, "author": _text(body.get("yazar"), "Yazar")[:300] or None, "illustrator": None,
            "meta": meta, "source": {"kind": KIND, "stok_kodu": body.get("stok_kodu")},
            "chapters": [{"title": "CRM metinleri", "blocks": blocks}]}


def _cover(data: bytes):
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:  # noqa: BLE001 — bozuk ya da görsel olmayan dosya
        raise JobError("Kapak dosyası okunamadı (PNG, JPEG ya da WebP olmalı).") from None
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "#FFFFFF")
        bg.paste(im, (0, 0), im)
        im = bg
    im = im.convert("RGB")
    if max(im.size) > COVER_SIDE:
        k = COVER_SIDE / max(im.size)
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.Resampling.LANCZOS)
    if min(im.size) < 120:
        raise JobError("Kapak görseli çok küçük (kısa kenar en az 120 piksel olmalı).")
    return im


def upsert(body: dict, by: str) -> dict:
    """Stok kodunun işini açar ya da günceller. Gövde: stok_kodu, baslik, yazar, tur, yas_ust, yayinevi, isbn,
    metinler{ozet, spot, onemli_cumle, sosyal_medya, alinti[], hashtag}, kapak_b64 (isteğe bağlı; yeni işte kapak
    yoksa yalnız alıntı kartı dizilebilir), kapak_kaynak (crm | eticaret | yukleme), kapak_url (kayıt için),
    marka_paleti[] (#RRGGBB)."""
    stok = str(body.get("stok_kodu") or "").strip()
    if not STOCK.match(stok):
        raise JobError("Stok kodu geçerli değil.")
    ms = manuscript({**body, "stok_kodu": stok})
    brand = [str(c).upper() for c in (body.get("marka_paleti") or []) if HEX.match(str(c))]
    img = None
    raw = body.get("kapak_b64")
    if raw:
        try:
            data = base64.b64decode(str(raw), validate=True)
        except (binascii.Error, ValueError):
            raise JobError("Kapak dosyası bozuk.") from None
        if len(data) > COVER_MAX:
            raise JobError("Kapak dosyası 25 MB'tan büyük.")
        img = _cover(data)
    d = find(stok)
    created = d is None
    if created:
        d = studio.new_job({"kind": KIND, "stok_kodu": stok}, by, "none", extra={"kind": KIND, "stok_kodu": stok})
    studio.write(d, "manuscript.json", ms)
    job = studio.read(d, "job.json") or {}
    extracted = list(job.get("palette_cover") or [])
    if img is not None:
        path = mk.cover_file(d)
        path.parent.mkdir(exist_ok=True)
        img.save(path, "PNG", optimize=True)
        from .palette import extract
        extracted = [c["hex"].upper() for c in extract([path], 6)]
        job["cover"] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "source_sha256": hashlib.sha256(data).hexdigest(),
                        "source": str(body.get("kapak_kaynak") or "yukleme")[:20],
                        "url": str(body.get("kapak_url") or "")[:500] or None,
                        "w": img.width, "h": img.height, "at": time.time(), "by": by}
    job.update(palette=list(dict.fromkeys(brand + extracted)), palette_cover=extracted, brand_palette=brand,
               updated_by=by, updated_at=time.time(), title=ms["title"])
    studio.write(d, "job.json", job)
    mk.log_event(d, by, "pazarlama işi açıldı" if created else "pazarlama işi güncellendi", stok_kodu=stok,
                 cover=bool(img is not None))
    return {**view(d), "created": created}


def view(d: Path) -> dict:
    job = studio.read(d, "job.json") or {}
    ms = studio.read(d, "manuscript.json") or {}
    return {"id": d.name, "kind": KIND, "stok_kodu": job.get("stok_kodu"), "title": ms.get("title"),
            "author": ms.get("author"), "cover": job.get("cover"), "palette": mk.palette_colors(d),
            "texts": sum(len(c.get("blocks") or []) for c in ms.get("chapters") or [])}
