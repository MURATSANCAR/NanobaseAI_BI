"""Renkli resimden boyama çizgisi (modelsiz) ve modelin çizdiği çizginin temizliği.

Modelsiz yol (`extract`), kitaptan bağımsız dört adım:
1. Doku düzleştirme: resim çalışma ölçüsüne (WORK_PX_MM px/mm) indirilir, ortanca süzgeçle suluboya/kalem
   dokusu bastırılır; CIELAB'a çevrilir.
2. Renk bölgesi sınırı: k-ortalamayla (ayrıntı düzeyine göre k) renk bölgelerine ayrılır, bölge haritası çoğunluk
   süzgeciyle yumuşatılır; iki bölgenin değdiği yer aday çizgidir (1 px, yeri kesin).
3. Kenar gücü: adayın çevresindeki renk değişimi (Sobel, ΔE/mm). Yumuşak geçişlerdeki (duvar ışığı, gökyüzü)
   bant sınırları zayıftır, nesne kenarları güçlü. Canny'deki gibi iki eşik: güçlü noktası olan zayıf zincir kalır.
   Resmin kendi koyu kontur çizgileri (ince koyu şerit) ayrıca eklenir.
4. Temizlik ve kalınlık: kısa kırıntılar silinir, çizgi baskıda boyanabilir kalınlığa (yaşa göre STROKE_MM)
   yuvarlak uçlu genişletilir, boyanamayacak kadar küçük beyaz adacıklar doldurulur, çıktı 2× ölçüde yumuşak kenarla
   yeniden ikilenir. Sonuç yalnız saf siyah ve beyaz («L», 0/255), gri yok.

Model yolu (`clean_drawn`): görsel modelin çizdiği siyah-beyaz çizgi aynı temizlikten geçer (eşik, kırıntı,
küçük delik, en ince çizgi kalınlığı), böylece iki yolun baskı kuralı aynıdır.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter

from . import raster
from .palette import _kmeans, rgb_to_lab

WORK_PX_MM = 8.0                  # çözümleme ölçüsü (~200 dpi); çizgi yeri bu ölçüde bulunur
OUT_SCALE = 2                     # çıktı kaynak pikselinin 2 katı (300 dpi resim → 600 dpi çizgi)
DETAIL = {                        # ayrıntı düzeyi → (renk sayısı, birleşme eşiği ΔE/mm, en küçük bölge mm²)
    "az": (10, 14.0, 60.0),
    "orta": (14, 10.0, 30.0),
    "cok": (18, 7.0, 14.0),
}
KEEP_DE = 35.0                    # küçük bölge komşusundan bu kadar (ΔE) ayrışıyorsa korunur (göz)
DARK_MIN_MM2 = 1.5                # bundan büyük küçük koyu bölge (göz bebeği) dolu siyah kalır
MIN_STROKE_LEN_MM = 3.0           # bundan kısa kırıntı çizgi silinir
MIN_HOLE_MM2 = 2.5                # bundan küçük kapalı beyaz alan boyanamaz: doldurulur
DARK_L = 40.0                     # küçük koyu bölge (göz bebeği, burun) bu açıklığın altında: dolu siyah


def stroke_mm(age_max: int | None) -> float:
    """Yaşa göre çizgi kalınlığı: küçük çocuk kalın çizgiyle boyar (taşırmaz), büyük çocuk ince ayrıntı ister."""
    a = age_max or 8
    return 1.2 if a <= 6 else 0.9 if a <= 9 else 0.6


def detail_for(age_max: int | None) -> str:
    a = age_max or 8
    return "az" if a <= 6 else "orta" if a <= 9 else "cok"


@dataclass
class Result:
    image: Image.Image            # «L», yalnız 0/255
    info: dict


def _work(src: Image.Image, src_dpi: float) -> tuple[Image.Image, float]:
    """Çalışma ölçüsü: WORK_PX_MM px/mm (kaynak daha küçükse kaynak)."""
    px_mm = src_dpi / 25.4
    k = min(1.0, WORK_PX_MM / px_mm)
    if k < 1.0:
        src = src.resize((max(8, round(src.width * k)), max(8, round(src.height * k))), Image.Resampling.LANCZOS)
    return src, px_mm * k


def _sobel(ch: np.ndarray) -> np.ndarray:
    p = np.pad(ch, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    return np.hypot(gx, gy) / 8.0


def _quantize(lab: np.ndarray, k: int) -> np.ndarray:
    flat = lab.reshape(-1, 3)
    step = max(1, len(flat) // 60000)
    centers, _ = _kmeans(flat[::step].astype(np.float64), k)
    best = np.zeros(len(flat), np.int32)
    bestd = np.full(len(flat), np.inf, np.float32)
    for i, c in enumerate(centers):
        dd = ((flat - c.astype(np.float32)) ** 2).sum(1)
        m = dd < bestd
        best[m], bestd[m] = i, dd[m]
    return best.reshape(lab.shape[:2])


def extract(src: Image.Image, *, src_dpi: float = 300.0, stroke: float = 1.0, detail: str = "orta",
            frame: bool = True) -> Result:
    """Renkli resim → boyama çizgisi. `src_dpi`: kaynağın basılacağı çözünürlük (mm hesabı için)."""
    t0 = time.time()
    k, weak, min_mm2 = DETAIL.get(detail, DETAIL["orta"])
    rgb0 = src.convert("RGB")
    work, pxmm = _work(rgb0, src_dpi)
    flat = work.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.MedianFilter(5))
    lab = rgb_to_lab(np.asarray(flat, dtype=np.float32)).astype(np.float32)
    # 2) renk bölgeleri: nicemleme → çoğunluk süzgeci → her rengin bağlı parçası bir bölge
    q = _quantize(lab, k)
    q = np.asarray(Image.fromarray(q.astype(np.uint8), "L").filter(ImageFilter.ModeFilter(5)))
    regions = np.zeros(q.shape, np.int32)
    n = 0
    for c in np.unique(q):
        lc, nc = raster.label(q == c, conn8=False)
        regions[lc > 0] = lc[lc > 0] + n
        n += nc
    # 3) kenar gücü (ΔE / mm); zayıf sınırlı komşular birleşir, küçük bölge komşusuna katılır
    g = (np.sqrt(sum(_sobel(lab[..., i]) ** 2 for i in range(3))) * pxmm).astype(np.float32)
    min_area = max(4, round(min_mm2 * pxmm * pxmm))
    dark_min = max(2, round(DARK_MIN_MM2 * pxmm * pxmm))

    def keep_small(a, color, around):                # göz, burun gibi küçük ama belirgin bölge korunur
        return a >= dark_min and (color[0] < DARK_L or float(np.linalg.norm(color - around)) >= KEEP_DE)
    seg = raster.merge_regions(regions, n, g, lab, weak=weak, min_area=min_area, keep_small=keep_small)
    lines = np.zeros(seg.shape, bool)
    lines[:, :-1] |= seg[:, :-1] != seg[:, 1:]
    lines[:-1] |= seg[:-1] != seg[1:]
    # küçük koyu bölgeler (göz bebeği) dolu siyah
    ids, inv = np.unique(seg, return_inverse=True)
    inv = inv.reshape(seg.shape)
    ar = np.bincount(inv.ravel())
    Lm = np.bincount(inv.ravel(), weights=lab[..., 0].ravel()) / np.maximum(ar, 1)
    solid = ((ar < min_area) & (Lm < DARK_L))[inv]
    if frame:
        lines[0, :] = lines[-1, :] = lines[:, 0] = lines[:, -1] = True
    # 4) temizlik ve kalınlık
    lines, specks = raster.remove_small(lines, max(4, round(MIN_STROKE_LEN_MM * pxmm)))
    r = max(1, round(stroke * pxmm / 2))
    ink = raster.round_dilate(lines, r) | solid
    if frame:
        b = max(1, round(stroke * pxmm))
        ink[:b, :] = ink[-b:, :] = True
        ink[:, :b] = ink[:, -b:] = True
    ink, holes = raster.fill_small_holes(ink, max(4, round(MIN_HOLE_MM2 * pxmm * pxmm)))
    out = raster.smooth_upscale(ink, (rgb0.width * OUT_SCALE, rgb0.height * OUT_SCALE),
                                soften=OUT_SCALE * rgb0.width / work.width * 0.6)
    n_regions = raster.label(~ink, conn8=False)[1]
    return Result(out, {"method": "cizgi", "detail": detail, "stroke_mm": stroke, "k": k, "work_px": list(work.size),
                        "segments": int(n), "specks_removed": specks, "holes_filled": holes, "regions": n_regions,
                        "ink_share": round(float(ink.mean()), 3), "seconds": round(time.time() - t0, 2),
                        "dpi": round(src_dpi * OUT_SCALE)})


def clean_drawn(img: Image.Image, *, src_dpi: float = 300.0, stroke: float = 1.0, size: tuple[int, int] | None = None,
                frame: bool = True) -> Result:
    """Modelin çizdiği çizgi resmini baskı kuralına getirir: gri → eşik, kırıntı sil, en ince çizgi `stroke`'un
    yarısına kalınlaştırılır, küçük delik doldurulur, 2× ölçüde yeniden ikilenir. `size`: hedef kaynak ölçüsü
    (kaynak resmin pikseli; model başka ölçüde döndürdüyse ona getirilir)."""
    t0 = time.time()
    g = img.convert("L")
    if size and g.size != size:
        g = g.resize(size, Image.Resampling.LANCZOS)
    work, pxmm = _work(g, src_dpi)
    a = np.asarray(work.filter(ImageFilter.MedianFilter(3)), dtype=np.float32)
    thr = min(170.0, max(60.0, float(np.percentile(a, 50)) * 0.6))
    ink = a < thr
    if frame:
        ink[0, :] = ink[-1, :] = ink[:, 0] = ink[:, -1] = True
    ink, specks = raster.remove_small(ink, max(4, round(MIN_STROKE_LEN_MM * pxmm)))
    ink = raster.round_dilate(ink, max(0, round(stroke * pxmm / 4)))
    if frame:
        b = max(1, round(stroke * pxmm))
        ink[:b, :] = ink[-b:, :] = True
        ink[:, :b] = ink[:, -b:] = True
    ink, holes = raster.fill_small_holes(ink, max(4, round(MIN_HOLE_MM2 * pxmm * pxmm)))
    W, H = (size or g.size)
    out = raster.smooth_upscale(ink, (W * OUT_SCALE, H * OUT_SCALE), soften=OUT_SCALE * W / work.width * 0.6)
    regions = raster.label(~ink, conn8=False)[1]
    return Result(out, {"method": "model", "stroke_mm": stroke, "threshold": round(thr), "specks_removed": specks,
                        "holes_filled": holes, "regions": regions, "ink_share": round(float(ink.mean()), 3),
                        "seconds": round(time.time() - t0, 2), "dpi": round(src_dpi * OUT_SCALE)})


def png_bytes(im: Image.Image) -> bytes:
    """İki renkli çizgi PNG'si (1 bit: baskıda gri yok, dosya küçük)."""
    buf = io.BytesIO()
    im.convert("1", dither=Image.Dither.NONE).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def is_two_tone(im: Image.Image) -> bool:
    vals = np.unique(np.asarray(im.convert("L")))
    return set(vals.tolist()) <= {0, 255}


REDRAW_PROMPT = (
    "Redraw the first reference image as a clean black-and-white coloring book page for children. "
    "Bold, smooth, uniform black outlines of every character, object and background shape, closed shapes that can "
    "be colored in, pure white inside every shape. No color, no gray, no shading, no hatching, no texture, no "
    "gradients, no filled black areas. Keep the composition, the characters, their poses and faces exactly as in "
    "the reference. No text or letters anywhere.")
