"""Portaldan kitap okutma: editörün yüklediği PDF gelen kutusuna yazılır ve okuma işi başlar.

Okuma, `editorctl analyze` ile aynı iştir (`jobs.start_analysis_job`); yalnız dosya kabuğa değil portala yüklenir.
Aynı dosya (içerik özeti) daha önce okunduysa yeni kitap açılmaz, var olan kayıt döner. İsteyen, `requested_by`
alanında `portal:<AD kullanıcısı>` olarak durur; liste bu önekle süzülür.

Ekrana adım adı değil aşama gider: iş akışının adım etiketleri teknik ad taşır (OCR, manifest), aşama adı taşımaz.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import unicodedata
import uuid
from pathlib import Path
from typing import BinaryIO

PREFIX = "portal:"
STEPS = 15
PDF_MAGIC = b"%PDF"

#: Adım numarası (iş akışının «n/15 etiket» biçimi) → ekranda görünen aşama.
PHASES = ((2, "Hazırlanıyor"), (4, "Metin okunuyor"), (6, "Resimler inceleniyor"),
          (9, "Karakterler ve olaylar çıkarılıyor"), (10, "Duygu, tema ve son okuma"), (STEPS, "Özet ve künye hazırlanıyor"))

_TR = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


class UploadError(ValueError):
    """Dosyanın kendisiyle ilgili, editöre olduğu gibi gösterilecek hata."""


def slug(name: str) -> str:
    """Gelen kutusu dosya adı: Türkçe harfler sadeleşir, küçük harf, tire; boşsa «kitap»."""
    t = unicodedata.normalize("NFKD", (name or "").translate(_TR))
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:80].strip("-") or "kitap"


def title_of(given: str, filename: str) -> str:
    """Kitabın adı: editör yazdıysa o; yoksa dosya adından (uzantısız, tire/alt çizgi boşluk)."""
    t = (given or "").strip()
    if t:
        return t[:300]
    stem = Path(filename or "").stem
    return re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", stem)).strip()[:300] or "Adsız kitap"


def phase(step: str | None, status: str) -> dict:
    """«7/15 Karakter ve olay adayları» → {'n': 7, 'of': 15, 'label': 'Karakterler ve olaylar çıkarılıyor'}."""
    if status == "SUCCEEDED":
        return {"n": STEPS, "of": STEPS, "label": "Hazır"}
    if status == "QUEUED" or not step:
        return {"n": 0, "of": STEPS, "label": "Sırada"}
    m = re.match(r"\s*(\d+)\s*/", step)
    n = min(int(m.group(1)), STEPS) if m else 0
    label = next((lab for last, lab in PHASES if n <= last), PHASES[-1][1])
    return {"n": n, "of": STEPS, "label": label}


def save(src: BinaryIO, inbox: Path, filename: str, title: str) -> tuple[str, int]:
    """Yüklemeyi gelen kutusuna yazar: önce geçici ada, doğrulanınca asıl ada. Aynı adda farklı içerik varsa
    ad «-2», «-3» alır; aynı içerik varsa var olan dosya kullanılır. Döner: (dosya adı, bayt)."""
    if Path(filename or "").suffix.lower() != ".pdf":
        raise UploadError("Yalnız PDF okutulabilir.")
    inbox.mkdir(parents=True, exist_ok=True)
    base = slug(title if title.strip() else Path(filename).stem)
    tmp = inbox / f".yukleniyor-{uuid.uuid4().hex}.part"   # .pdf değil: kuyruk komutu yarım dosyayı görmez
    digest = hashlib.sha256()
    size = 0
    try:
        with tmp.open("wb") as out:
            head = src.read(len(PDF_MAGIC))
            if head != PDF_MAGIC:
                raise UploadError("Dosyanın içeriği PDF değil." if head else "Dosya boş.")
            out.write(head)
            digest.update(head)
            size += len(head)
            while chunk := src.read(1 << 20):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        sha = digest.hexdigest()
        for n in range(1, 1000):
            name = f"{base}.pdf" if n == 1 else f"{base}-{n}.pdf"
            dest = inbox / name
            if not dest.exists():
                shutil.move(str(tmp), dest)
                return name, size
            if _sha(dest) == sha:
                return name, size
        raise UploadError("Gelen kutusunda bu adda çok fazla dosya var; kitaba başka bir ad verin.")
    finally:
        tmp.unlink(missing_ok=True)


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()
