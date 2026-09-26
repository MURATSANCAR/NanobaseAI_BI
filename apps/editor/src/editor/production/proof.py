"""Ekranda baskı provası (soft proof) ve 3B kitabın ölçüleri.

Sayfa (ya da kapak açılımı) önizlemesi sRGB kabul edilir ve seçilen kâğıdın basım profiline göre çevrilir:

    sRGB ──(göreli kolorimetrik + siyah nokta dengeleme)──▶ CMYK (kâğıdın profili)
         ──(mutlak kolorimetrik)──▶ ekran sRGB     «kâğıt tonuyla»: kâğıdın beyazı ve mürekkebin koyuluğu görünür
         ──(göreli kolorimetrik)──▶ ekran sRGB     «kâğıt tonu olmadan»: beyaz ekran beyazı kalır

Profiller `icc/` altında, lisansı `icc/LISANS.md` (CC0). Renk dönüşümü Pillow'un ImageCms'i (LittleCMS) ile.

İki uyarı katmanı üretilir (ekranda taranmış işaret olarak, önizleme ile aynı boyda saydam PNG):

- **Renk kaybı (gamut dışı):** kaynak renk ile kâğıda basılıp geri okunmuş rengi (ikisi de siyah nokta dengeli,
  göreli) Lab'de karşılaştırılır; fark `GAMUT_DE`'yi aşan piksel işaretlenir. Nötr koyular siyah nokta dengelemesiyle
  eşlendiği için yalnız doygunluk/ton kaybı (canlı mavi, yeşil, turuncu) işaretlenir; kâğıdın grileşen siyahı değil.
- **Mürekkep yükü (TAC):** C+M+Y+K toplamı (%) kâğıdın sınırını (`Paper.tac_limit`) aşan piksel. Kaynak, varsa ve
  güncelse matbaaya gidecek baskı PDF'inin kendi ayrımıdır (gerçek yük); yoksa prova ayrımı («prova» diye işaretlenir).

Sonuçlar iş klasöründe `prova/` altında önbelleğe yazılır; önizleme, baskı PDF'i ya da profil değişince yenilenir.
Kitaba özel kural yoktur: her değer aşağıdaki kâğıt tablosundan ve sayfa görüntüsünden gelir.
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import studio
from .spec import COVER_BOARD

ICC = Path(__file__).resolve().parent / "icc"

# Renk kaybı eşiği (Lab farkı; açıklık aşağıdaki ağırlıkla). ~2,3 ancak yan yana fark edilen fark; 6 üstü «bakınca görülen» fark (baskı
# sektöründe kabul toleransı ~5–6). Gerçek bir resimli sayfada ölçüldü: 6'nın altı yumuşak geçişlerde gürültü üretiyor.
GAMUT_DE = 6.0
# Açıklık farkı yarı ağırlıkla sayılır (CMC 2:1 kabul ölçüsündeki gibi): kaplamasız kâğıtta siyahın ve çok koyu
# grilerin açılması (siyah nokta dengelemesine rağmen L≈9) metin sayfasını baştan sona «renk kaybı» diye
# boyuyordu; asıl uyarılması gereken doygunluk ve ton kaybıdır (koyu lacivert, canlı mavi/yeşil, turuncu).
L_WEIGHT = 0.5
MARK_GROW = 5          # işaretlenen bölge bu kadar piksel büyütülür (tek pikselli leke ekranda görünmez)
HATCH = 6              # tarama çizgisi kalınlığı (px)
# Tarama renkleri (RGBA): dolu çizgi + arasında hafif perde; alttaki resim çizgi aralarından görünür kalır.
GAMUT_INK, GAMUT_GAP = (214, 31, 138, 215), (255, 255, 255, 70)
TAC_INK, TAC_GAP = (235, 120, 0, 225), (0, 0, 0, 70)


@dataclass(frozen=True)
class Paper:
    key: str
    label: str
    note: str
    profile: str             # icc/ altındaki dosya
    tac_limit: int           # % (C+M+Y+K); aynı basım koşulunun yaygın sınırı
    finish: str              # gloss | matte | uncoated — 3B görünümde yüzey parlaklığı
    grammage: int            # g/m²
    bulk: float              # hacim (cm³/g); kalınlık = gramaj × hacim / 1000 (mm, bir yaprak)

    @property
    def caliper(self) -> float:
        return round(self.grammage * self.bulk / 1000, 3)


# Mürekkep sınırları, aynı basım koşuluna ait yaygın profillerin sınırıdır: kaplamalı %330, kaplamasız beyaz %300,
# kaplamasız sarımsı %320. Kalınlık: kuşe 130 g × 0,85 = 0,11 mm ve 1. hamur 70 g × 1,3 = 0,09 mm, `spec.CALIPER`
# ile aynı; mat kuşe daha kabarık (0,95), şamua kitap kâğıdı olarak en kabarık (1,6).
PAPERS: dict[str, Paper] = {p.key: p for p in (
    Paper("kuse", "Kuşe", "Parlak kaplamalı; renkler en canlı, siyah en koyu.", "FOGRA39L_coated.icc",
          330, "gloss", 130, 0.85),
    Paper("mat_kuse", "Mat kuşe", "Mat kaplamalı; renk kuşeyle aynı basılır, yüzey parlamaz.", "FOGRA39L_coated.icc",
          330, "matte", 130, 0.95),
    Paper("hamur", "1. hamur", "Kaplamasız beyaz (ofset); renkler daha yumuşak, siyah daha açık.",
          "FOGRA47L_uncoated.icc", 300, "uncoated", 70, 1.3),
    Paper("samua", "Şamua", "Kaplamasız krem tonlu kitap kâğıdı; beyazlar sıcak görünür.",
          "FOGRA30L_uncoated_yellowish.icc", 320, "uncoated", 70, 1.6),
)}
# Kitabın kendi kâğıdı (spec.paper) → varsayılan prova kâğıdı.
SPEC_PAPER = {"kuse_130": "kuse", "hamur_70": "hamur"}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def paper(key: str) -> Paper:
    if key not in PAPERS:
        raise KeyError(key)
    return PAPERS[key]


# ------------------------------------------------------------------ renk dönüşümleri
@lru_cache(maxsize=None)
def _profile(name: str):
    from PIL import ImageCms
    return ImageCms.getOpenProfile(str(ICC / name))


@lru_cache(maxsize=None)
def _tx(profile: str, kind: str):
    """Dönüşümler bir kez kurulur (LittleCMS dönüşümleri eşzamanlı kullanıma uygundur)."""
    from PIL import ImageCms
    srgb, lab, cmyk = ImageCms.createProfile("sRGB"), ImageCms.createProfile("LAB"), _profile(profile)
    rel, absol = ImageCms.Intent.RELATIVE_COLORIMETRIC, ImageCms.Intent.ABSOLUTE_COLORIMETRIC
    bpc = ImageCms.Flags.BLACKPOINTCOMPENSATION
    if kind == "to_cmyk":
        return ImageCms.buildTransform(srgb, cmyk, "RGB", "CMYK", rel, flags=bpc)
    if kind == "show_paper":
        return ImageCms.buildTransform(cmyk, srgb, "CMYK", "RGB", absol)
    if kind == "show_plain":
        return ImageCms.buildTransform(cmyk, srgb, "CMYK", "RGB", rel, flags=bpc)
    if kind == "src_lab":
        return ImageCms.buildTransform(srgb, lab, "RGB", "LAB", rel)
    if kind == "cmyk_lab":
        return ImageCms.buildTransform(cmyk, lab, "CMYK", "LAB", rel, flags=bpc)
    raise ValueError(kind)


@lru_cache(maxsize=None)
def paper_white(key: str) -> str:
    """Kâğıdın beyazı ekranda (mutlak kolorimetrik, mürekkepsiz CMYK)."""
    from PIL import Image, ImageCms
    im = ImageCms.applyTransform(Image.new("CMYK", (1, 1), (0, 0, 0, 0)), _tx(PAPERS[key].profile, "show_paper"))
    return "#%02x%02x%02x" % im.getpixel((0, 0))


def papers() -> list[dict]:
    return [{"key": p.key, "label": p.label, "note": p.note, "tac_limit": p.tac_limit, "finish": p.finish,
             "grammage": p.grammage, "caliper_mm": p.caliper, "white": paper_white(p.key)} for p in PAPERS.values()]


def convert(im, key: str) -> dict:
    """Saf dönüşüm (dosyasız): RGB görüntü → {"cmyk", "paper", "plain", "gamut" (bool dizi), "de" (dizi)}."""
    import numpy as np
    from PIL import ImageCms
    prof = PAPERS[key].profile
    im = im.convert("RGB")
    cmyk = ImageCms.applyTransform(im, _tx(prof, "to_cmyk"))
    d = _lab(ImageCms.applyTransform(im, _tx(prof, "src_lab"))) - _lab(ImageCms.applyTransform(cmyk, _tx(prof, "cmyk_lab")))
    d[..., 0] *= L_WEIGHT
    de = np.sqrt((d ** 2).sum(axis=-1))
    return {"cmyk": cmyk, "paper": ImageCms.applyTransform(cmyk, _tx(prof, "show_paper")),
            "plain": ImageCms.applyTransform(cmyk, _tx(prof, "show_plain")), "de": de, "gamut": de > GAMUT_DE}


def _lab(im):
    """Pillow'un LAB görüntüsü → gerçek birimde dizi (L 0–100, a/b −128…127). Dizi arayüzü a/b'yi işaretli bayt
    (ikiye tümleyen) olarak verir; `getpixel` ise 128 kaydırmalı verir — burada dizi yolu kullanılır."""
    import numpy as np
    raw = np.asarray(im)
    out = np.empty(raw.shape, dtype=np.float32)
    out[..., 0] = raw[..., 0] * (100 / 255)
    out[..., 1:] = np.ascontiguousarray(raw[..., 1:]).view(np.int8)
    return out


def tac(cmyk):
    """Piksel başına toplam mürekkep (%)."""
    import numpy as np
    return np.asarray(cmyk, dtype=np.float32).sum(axis=-1) * (100 / 255)


def hatch(mask, a: tuple, b: tuple):
    """Saydam zemin üstünde çapraz taranmış işaret (iki renk dönüşümlü): her zeminde okunur."""
    import numpy as np
    from PIL import Image, ImageFilter
    m = Image.fromarray((mask.astype("uint8")) * 255, "L")
    if MARK_GROW > 1:
        m = m.filter(ImageFilter.MaxFilter(MARK_GROW if MARK_GROW % 2 else MARK_GROW + 1))
    on = np.asarray(m) > 0
    h, w = on.shape
    yy, xx = np.mgrid[0:h, 0:w]
    stripe = ((xx + yy) // HATCH) % 2 == 0
    out = np.zeros((h, w, 4), dtype=np.uint8)
    out[on & stripe] = a
    out[on & ~stripe] = b
    return Image.fromarray(out, "RGBA")


# ------------------------------------------------------------------ iş klasörü
def _lock(key: str) -> threading.Lock:
    """Aynı dosyayı iki iş parçacığı birden üretmesin; farklı sayfa/kâğıt paralel çalışır (kâğıt değişince bütün
    açılımın dokuları aynı anda istenir)."""
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _print_cmyk(d: Path, what: str, n: int, size: tuple[int, int], src_pdf: Path):
    """Baskı PDF'inin (CMYK, kesim işaretli) ilgili sayfası, taşma kutusu kırpılarak önizleme boyunda; baskı PDF'i
    yoksa ya da ekran PDF'inden eskiyse None."""
    pdf = studio.print_paths(d)["ic" if what == "page" else "kapak"]
    if not pdf.exists() or not src_pdf.exists() or pdf.stat().st_mtime < src_pdf.stat().st_mtime:
        return None, None
    import pymupdf
    from PIL import Image
    doc = pymupdf.open(pdf)
    i = n - 1 if what == "page" else 0
    if not 0 <= i < doc.page_count:
        return None, None
    page = doc[i]
    clip = page.bleedbox
    zoom = size[0] / clip.width
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, colorspace=pymupdf.csCMYK, alpha=False)
    im = Image.frombytes("CMYK", (pix.width, pix.height), pix.samples)
    if im.size != size:
        im = im.resize(size, Image.Resampling.BILINEAR)
    return im, pdf


def render(d: Path, what: str, n: int, key: str, width: int) -> dict[str, Path]:
    """Prova dosyaları (önbellekli): {"paper", "plain", "gamut", "tac", "report"}. `what`: page | cover."""
    from PIL import Image
    paper(key)
    base = f"s{n}" if what == "page" else "kapak"
    with _lock(f"{d.name}/kaynak/{base}-{width}"):      # aynı önizlemeyi dört kâğıt birden yazmasın
        src = studio.page_preview(d, n, width) if what == "page" else studio.cover_preview(d, width)
    src_pdf = d / ("dizgi/ic-sayfalar.pdf" if what == "page" else "kapak/kapak.pdf")
    stem = f"{base}-{width}-{key}"
    out = d / "prova"
    files = {k: out / f"{stem}-{k}.{'json' if k == 'report' else 'png'}"
             for k in ("paper", "plain", "gamut", "tac", "report")}
    prof = ICC / PAPERS[key].profile
    printed = studio.print_paths(d)["ic" if what == "page" else "kapak"]
    deps = [src, prof] + ([printed] if printed.exists() else [])
    newest = max(p.stat().st_mtime for p in deps)
    with _lock(f"{d.name}/{stem}"):
        if all(f.exists() and f.stat().st_mtime >= newest for f in files.values()):
            return files
        out.mkdir(exist_ok=True)
        im = Image.open(src).convert("RGB")
        r = convert(im, key)
        pc, used = _print_cmyk(d, what, n, im.size, src_pdf)
        t = tac(pc if pc is not None else r["cmyk"])
        p = PAPERS[key]
        over = t > p.tac_limit + 0.5
        for k, img in (("paper", r["paper"]), ("plain", r["plain"]),
                       ("gamut", hatch(r["gamut"], GAMUT_INK, GAMUT_GAP)),
                       ("tac", hatch(over, TAC_INK, TAC_GAP))):
            tmp = files[k].with_suffix(".tmp.png")
            img.save(tmp, "PNG", compress_level=6)
            tmp.replace(files[k])
        report = {"paper": key, "label": p.label, "width": im.width, "height": im.height,
                  "gamut_share": round(float(r["gamut"].mean()) * 100, 2), "gamut_de": GAMUT_DE,
                  "tac_max": int(math.floor(float(t.max()) + 0.5)), "tac_limit": p.tac_limit,
                  "tac_share": round(float(over.mean()) * 100, 2),
                  "tac_source": "baski" if used is not None else "prova", "white": paper_white(key)}
        studio.write(out, files["report"].name, report)
    return files


def report(d: Path, what: str, n: int, key: str, width: int) -> dict:
    return json.loads(render(d, what, n, key, width)["report"].read_text())


def book(d: Path) -> dict:
    """3B kitabın gerçek ölçüleri (mm) ve kâğıtlar. Kalınlık kâğıda göre: yaprak sayısı × yaprak kalınlığı + iki
    kapak kartonu; kapak açılımının sırtı (`cover.spine_mm`) dizgideki gerçek değerdir (tel dikişte 0)."""
    spec = studio.read(d, "spec.json")
    if not spec:
        raise FileNotFoundError("baskı özellikleri henüz yok")
    pages = studio.page_count(d)
    leaves = math.ceil(pages / 2)
    cover = studio.read(d, "cover.json")
    has_cover = (d / "kapak" / "kapak.pdf").exists()
    return {
        "trim_w": spec["trim_w"], "trim_h": spec["trim_h"], "bleed": spec["bleed"], "pages": pages, "leaves": leaves,
        "board_mm": COVER_BOARD, "spec_paper": spec.get("paper"),
        "default_paper": SPEC_PAPER.get(spec.get("paper") or "", "kuse"),
        "cover": ({"size_mm": cover.get("size_mm"), "spine_mm": cover.get("spine_mm", 0.0),
                   "binding": cover.get("binding")} if has_cover and cover else None),
        "thickness_mm": {k: round(leaves * p.caliper + 2 * COVER_BOARD, 2) for k, p in PAPERS.items()},
        "papers": papers(), "gamut_de": GAMUT_DE,
    }
