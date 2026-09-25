"""Etkinlik sayfaları (boyama/etkinlik kitabı): şablon + kitabın verisi, modelsiz ve deterministik.

Her üretici bir `Activity` döner: sayfanın gövde görseli (600 dpi, kutunun ölçüsünde), başlık ve yönerge (dizgide
vektör yazı), gerekiyorsa kelime listesi ve cevap anahtarı görseli. Aynı kitap + aynı tohum → aynı sayfa.

Türler (`KINDS`): renk sayıya göre boyama, noktaları birleştir, farkı bul, labirent, kelime avı, eşleştirme.
Zorluk yaşa göre (profilin üst yaşı): çizgi kalınlığı, nokta aralığı, labirent hücresi, bulmaca ızgarası.
Kitaptan bağımsızdır: kelimeler kitabın kendi metninden ve karakter adlarından, resimler kitabın çizgilerinden.
Sayı tavanı yoktur; bir sayfaya sığmayan (eşleştirmede karakter, cevap anahtarında cevap) yeni sayfaya geçer,
ızgaraya sığmayan kelime bilgi olarak döner (sessizce düşmez).

Çıktı iki renklidir (saf siyah/beyaz); yalnız «renk sayıya göre boyama»nın renk anahtarı renklidir.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import raster
from .palette import _kmeans, _rgb_hex, lab_to_rgb, rgb_to_lab

DPI = 600
WORK = 8.0                                   # çözümleme ölçüsü px/mm
KINDS = ("paint_by_number", "dot_to_dot", "spot_difference", "maze", "word_search", "matching")
NAMES = {"paint_by_number": "Renk sayıya göre boyama", "dot_to_dot": "Noktaları birleştir",
         "spot_difference": "Farkı bul", "maze": "Labirent", "word_search": "Kelime avı", "matching": "Eşleştirme"}
TR_LETTERS = "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"
STOP = set("""ve ile bir bu şu o da de ki mi mı mu mü için gibi çok daha en ama ya hem ne diye dedi der sonra her
hiç kadar olan oldu olarak ben sen biz siz onlar onu ona onun beni bana benim seni sana senin bizi bize siz size
şey şimdi artık hemen bile yine işte evet hayır hadi haydi ise değil var yok çünkü ancak fakat eğer belki sadece
tüm bütün hep nasıl neden niye nerede burada orada şurada böyle şöyle öyle kendi kendini birlikte beraber
mış miş muş müş dı di du dü tı ti tu tü""".split())


def px(mm: float) -> int:
    return int(round(mm * DPI / 25.4))


def seed_of(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def tr_upper(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


@dataclass
class Activity:
    kind: str
    title: str
    instruction: str
    image: Image.Image
    words: list[str] = field(default_factory=list)
    answer: Image.Image | None = None
    info: dict = field(default_factory=dict)


# ------------------------------------------------------------------ ortak
def font(font_dir: Path, size_px: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for name in (("Andika-Bold.ttf", "Baloo2[wght].ttf") if bold else ("Andika-Regular.ttf",)):
        p = Path(font_dir) / name
        if p.exists():
            return ImageFont.truetype(str(p), max(6, int(size_px)))
    return ImageFont.load_default(size=max(6, int(size_px)))


def two_tone(im: Image.Image) -> Image.Image:
    return im.convert("L").point(lambda v: 0 if v < 128 else 255)


def fit(im: Image.Image, w: int, h: int, *, binary: bool = True) -> Image.Image:
    if im.mode in ("1", "P"):
        im = im.convert("L")
    k = min(w / im.width, h / im.height)
    out = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.Resampling.LANCZOS)
    return two_tone(out) if binary else out


def on_white(im: Image.Image) -> Image.Image:
    """Saydam görseli beyaz zemine koyar."""
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB")


def content_box(rgb: Image.Image, tol: float = 28.0, margin: float = 0.04) -> tuple[int, int, int, int]:
    """Beyaz zemin üzerindeki çizimin sınır kutusu (biraz payla)."""
    a = np.asarray(rgb.convert("RGB"), dtype=np.float32)
    m = (255 - a).max(axis=2) > tol
    if not m.any():
        return 0, 0, rgb.width, rgb.height
    ys, xs = np.nonzero(m)
    p = int(max(rgb.size) * margin)
    return max(0, xs.min() - p), max(0, ys.min() - p), min(rgb.width, xs.max() + p + 1), min(rgb.height, ys.max() + p + 1)


def silhouette(rgb: Image.Image, tol: float = 14.0, line: Image.Image | None = None) -> np.ndarray:
    """Beyaz zemindeki figürün dolu siluet maskesi (iç boşluklar dolu; açık renkli kenardaki kopukluk kapatılır).
    `line` verilirse çizginin kapattığı alan da eklenir (beyaz zemindeki beyaz figür renkten ayrılmaz)."""
    from .photo import _connected_to_border
    a = np.asarray(rgb.convert("RGB"), dtype=np.float32)
    fg = (255 - a).max(axis=2) > tol
    if line is not None:
        fg |= np.asarray(line.convert("L").resize(rgb.size, Image.Resampling.LANCZOS)) < 128
    r = max(1, round(min(fg.shape) * 0.006))
    fg = raster.erode(raster.dilate(fg, r), r)
    bg = _connected_to_border(~fg)
    sil = ~bg
    sil = np.asarray(Image.fromarray(sil.astype(np.uint8) * 255).filter(ImageFilter.ModeFilter(5))) > 127
    lab, n = raster.label(sil)
    if n > 1:
        ar = raster.areas(lab, n)
        ar[0] = 0
        sil = lab == int(np.argmax(ar))
    return sil


def kid_color_name(rgb) -> str:
    """Çocuğun boya kaleminde bulacağı basit Türkçe renk adı (CIELAB ton açısından)."""
    L, a, b = (float(v) for v in rgb_to_lab(np.asarray(rgb, dtype=float)))
    C = math.hypot(a, b)
    h = math.degrees(math.atan2(b, a)) % 360
    if L < 22:
        return "siyah"
    if C < 9:
        return "beyaz" if L > 90 else "gri"
    if 40 <= h < 105 and L < 55 and C < 60:
        return "kahverengi"
    if 55 <= h < 110 and L > 82 and C < 28:
        return "krem"
    if h < 22 or h >= 345:
        return "pembe" if L > 62 else "kırmızı"
    if h < 45:
        return "pembe" if L > 72 and C < 40 else "kırmızı" if C > 55 and L < 60 else "turuncu"
    if h < 72:
        return "turuncu"
    if h < 105:
        return "sarı"
    if h < 185:
        return "açık yeşil" if L > 72 else "yeşil"
    if h < 315:
        return "lacivert" if L < 35 else "açık mavi" if L > 70 else "mavi"
    return "lila" if L > 65 else "mor"


CRAYON = {"siyah": "#222222", "beyaz": "#FFFFFF", "gri": "#9E9E9E", "kahverengi": "#8D5524", "krem": "#F3E5C0",
          "pembe": "#F48FB1", "kırmızı": "#E53935", "turuncu": "#FB8C00", "sarı": "#FDD835", "açık yeşil": "#9CCC65",
          "yeşil": "#43A047", "açık mavi": "#81D4FA", "mavi": "#1E88E5", "lacivert": "#283593", "lila": "#CE93D8",
          "mor": "#8E24AA"}                  # renk anahtarındaki boya kalemi rengi (ad → örnek)


def char_line(char: Image.Image, w_mm: float, h_mm: float, age: int) -> tuple[Image.Image, Image.Image]:
    """Karakter referansının (beyaz zemin) çizimi, basılacağı ölçüye göre: (kırpılmış renkli, çizgi «L»). Çizgi
    kalınlığı bu ölçüde yaşa uygun olsun diye çizgi o ölçünün çözünürlüğüyle çıkarılır; çerçeve çizilmez."""
    from . import lineart
    rgb = on_white(char)
    rgb = rgb.crop(content_box(rgb))
    k = min(w_mm / rgb.width, h_mm / rgb.height)            # mm / px
    line = lineart.extract(rgb, src_dpi=25.4 / k, stroke=_stroke(age) * 0.8, detail="orta", frame=False).image
    return rgb, line


def _work_of(im: Image.Image) -> tuple[Image.Image, float]:
    """600 dpi görsel → çözümleme ölçüsü (WORK px/mm); dönen katsayı çıktı/çözümleme."""
    f = WORK * 25.4 / DPI
    return im.resize((max(8, round(im.width * f)), max(8, round(im.height * f))), Image.Resampling.LANCZOS), 1 / f


def _stroke(age: int) -> float:
    return 1.2 if age <= 6 else 0.9 if age <= 9 else 0.6


def _text_center(d: ImageDraw.ImageDraw, xy, text: str, f, fill=0) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = d.textbbox((0, 0), text, font=f)
    w, h = x1 - x0, y1 - y0
    x, y = xy[0] - w / 2 - x0, xy[1] - h / 2 - y0
    d.text((x, y), text, font=f, fill=fill)
    return int(x + x0), int(y + y0), int(x + x1), int(y + y1)


# ------------------------------------------------------------------ renk sayıya göre boyama
def paint_by_number(src: Image.Image, line: Image.Image, box_mm: tuple[float, float], age: int,
                    font_dir: Path) -> Activity:
    """Çizginin her kapalı bölgesine kaynak resimdeki renginin numarası; altta renk anahtarı. Numara sığmayan küçük
    bölge numarasız kalır (sayısı bilgi olarak döner). Renk sayısı yaşa göre (5/7/9)."""
    W, H = px(box_mm[0]), px(box_mm[1])
    k = 5 if age <= 6 else 7 if age <= 9 else 9
    legend_row = px(12 if age <= 6 else 10)
    cols = 2 if age <= 9 else 3
    rows = -(-k // cols)
    art = fit(line, W, H - rows * legend_row - px(5))
    work, up = _work_of(art)
    ink = np.asarray(work) < 128
    lab_r, n = raster.label(~ink, conn8=False)
    src_w = src.convert("RGB").resize(work.size, Image.Resampling.LANCZOS)
    lab = rgb_to_lab(np.asarray(src_w, dtype=np.float32))
    flat = lab.reshape(-1, 3)[~ink.ravel()]
    centers, _ = _kmeans(flat[:: max(1, len(flat) // 40000)].astype(float), 2 * k)
    names = [kid_color_name(lab_to_rgb(c)) for c in centers]
    groups: dict[str, list[int]] = {}
    for i, nm in enumerate(names):
        groups.setdefault(nm, []).append(i)
    order = list(groups)
    color_of = {nm: np.mean([centers[i] for i in idx], axis=0) for nm, idx in groups.items()}
    area = raster.areas(lab_r, n)
    mean = np.stack([np.bincount(lab_r.ravel(), weights=lab[..., c].ravel(), minlength=n + 1) for c in range(3)], 1) \
        / np.maximum(area, 1)[:, None]
    gl = np.array([color_of[nm] for nm in order])
    region_group = np.argmin(((mean[:, None, :] - gl[None]) ** 2).sum(-1), axis=1)
    digit_h = (5.0 if age <= 6 else 4.0)
    need = digit_h * 0.62 * WORK
    dist = raster.distance(~ink, limit=int(need) + 2)
    flat_lab, flat_d = lab_r.ravel(), dist.ravel()
    idx = np.lexsort((flat_d, flat_lab))
    last = np.r_[np.nonzero(np.diff(flat_lab[idx]))[0], len(idx) - 1]
    canvas = Image.new("RGB", (W, H), "white")
    ox = (W - art.width) // 2
    canvas.paste(art.convert("RGB"), (ox, 0))
    d = ImageDraw.Draw(canvas)
    f = font(font_dir, px(digit_h) * 1.25)
    placed = skipped = 0
    for j in last:
        r = int(flat_lab[idx[j]])
        if r == 0:
            continue
        if flat_d[idx[j]] < need:
            skipped += 1
            continue
        y, x = divmod(int(idx[j]), work.width)
        _text_center(d, (ox + x * up, y * up), str(int(region_group[r]) + 1), f, fill=(0, 0, 0))
        placed += 1
    # renk anahtarı
    ly = art.height + px(5)
    cw = W // cols
    fl = font(font_dir, legend_row * 0.42)
    rr = legend_row * 0.34
    for i, nm in enumerate(order):
        cx = (i % cols) * cw + px(3) + rr
        cy = ly + (i // cols) * legend_row + legend_row / 2
        rgb = tuple(int(CRAYON.get(nm, "#FFFFFF")[i:i + 2], 16) for i in (1, 3, 5))
        d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=rgb, outline=(0, 0, 0), width=max(2, px(0.4)))
        d.text((cx + rr + px(2.5), cy), f"{i + 1} = {nm}", font=fl, fill=(0, 0, 0), anchor="lm")
    return Activity("paint_by_number", NAMES["paint_by_number"],
                    "Her bölgedeki numaranın rengini alttaki anahtarda bul ve boya.", canvas,
                    info={"colors": [{"n": i + 1, "name": nm, "hex": CRAYON.get(nm), "source": _rgb_hex(lab_to_rgb(color_of[nm]))}
                                     for i, nm in enumerate(order)],
                          "regions": int(n), "numbered": placed, "too_small": skipped})


# ------------------------------------------------------------------ noktaları birleştir
def _resample(contour: list[tuple[int, int]], corners: set[int], step: float) -> list[tuple[float, float]]:
    """Kontur boyunca: köşeler (RDP) + aradaki yol `step`'i aşmayacak kadar ara nokta."""
    pts = np.asarray(contour, dtype=float)
    seg = np.hypot(*np.diff(np.vstack([pts, pts[:1]]), axis=0).T)
    cum = np.r_[0, np.cumsum(seg)]
    keys = sorted(corners | {0})
    out = []
    for a, b in zip(keys, keys[1:] + [len(pts)]):
        la, lb = cum[a], cum[b]
        m = max(1, int(math.ceil((lb - la) / step)))
        for t in range(m):
            L = la + (lb - la) * t / m
            i = min(int(np.searchsorted(cum, L, side="right") - 1), len(pts) - 1)
            j = (i + 1) % len(pts)
            f = 0 if seg[i] == 0 else (L - cum[i]) / seg[i]
            out.append(tuple(pts[i] + (pts[j] - pts[i]) * f))
    return out


def dot_to_dot(char: Image.Image, box_mm: tuple[float, float], age: int, font_dir: Path) -> Activity:
    """Karakterin dış çizgisi numaralı noktalara dönüşür; iç ayrıntı çizgisi kalır. Nokta sayısı konturun
    uzunluğundan ve yaşa göre aralıktan (12/9/6 mm) çıkar."""
    W, H = px(box_mm[0]), px(box_mm[1])
    rgb, line = char_line(char, box_mm[0] * 0.9, box_mm[1] * 0.9, age)
    k = min(W / rgb.width, H / rgb.height) * 0.9
    tw, th = round(rgb.width * k), round(rgb.height * k)
    big = rgb.resize((tw, th), Image.Resampling.LANCZOS)
    work, up = _work_of(big)
    sil = silhouette(work, line=line)
    contour = raster.trace_outer(sil)
    step = (12.0 if age <= 6 else 9.0 if age <= 7 else 6.0) * WORK
    simp = raster.rdp(contour + contour[:1], step * 0.22)
    at = {p: i for i, p in enumerate(contour)}
    corners = {at[(int(p[0]), int(p[1]))] for p in simp if (int(p[0]), int(p[1])) in at}
    # başlangıç: en üstteki nokta (saat yönünde ilerler)
    top = min(range(len(contour)), key=lambda i: (contour[i][1], contour[i][0])) if contour else 0
    contour = contour[top:] + contour[:top]
    corners = {(c - top) % len(contour) for c in corners} if contour else set()
    pts = _resample(contour, corners, step) if len(contour) > 8 else []
    canvas = Image.new("L", (W, H), 255)
    ox, oy = (W - tw) // 2, (H - th) // 2
    stroke = _stroke(age)
    if line is not None:
        a = np.asarray(fit(line, tw, th).resize((tw, th))) < 128
        s_big = np.asarray(Image.fromarray(sil.astype(np.uint8) * 255).resize((tw, th))) > 127
        band = raster.dilate(s_big & ~raster.erode(s_big, 1), px(stroke * 2.2))
        a &= s_big & ~band
        canvas.paste(Image.fromarray(np.where(a, 0, 255).astype(np.uint8)), (ox, oy))
    d = ImageDraw.Draw(canvas)
    r = px(1.0 if age <= 6 else 0.8)
    f = font(font_dir, px(4.2 if age <= 6 else 3.4))
    cx, cy = (np.mean([p[0] for p in pts]) if pts else 0), (np.mean([p[1] for p in pts]) if pts else 0)
    boxes: list[tuple[int, int, int, int]] = []
    dots = [(ox + p[0] * up, oy + p[1] * up) for p in pts]
    for x, y in dots:
        d.ellipse((x - r, y - r, x + r, y + r), fill=0)
    for i, (p, (x, y)) in enumerate(zip(pts, dots), 1):
        nx, ny = p[0] - cx, p[1] - cy
        L = math.hypot(nx, ny) or 1.0
        best = None
        for ang in (0, 30, -30, 60, -60, 90, -90, 180):
            a_ = math.atan2(ny, nx) + math.radians(ang)
            off = px(3.2 if age <= 6 else 2.6)
            tx, ty = x + math.cos(a_) * off, y + math.sin(a_) * off
            bb = d.textbbox((tx, ty), str(i), font=f, anchor="mm")
            hit = any(not (bb[2] < q[0] or bb[0] > q[2] or bb[3] < q[1] or bb[1] > q[3]) for q in boxes) or \
                any(bb[0] - r < qx < bb[2] + r and bb[1] - r < qy < bb[3] + r for qx, qy in dots)
            if not hit and 0 <= bb[0] and bb[2] <= W and 0 <= bb[1] and bb[3] <= H:
                best = (tx, ty, bb)
                break
            best = best or (tx, ty, bb)
        tx, ty, bb = best
        d.text((tx, ty), str(i), font=f, fill=0, anchor="mm")
        boxes.append(bb)
    return Activity("dot_to_dot", NAMES["dot_to_dot"],
                    "1'den başla, noktaları sırayla birleştir, son noktayı yine 1'e bağla; sonra resmi boya.",
                    two_tone(canvas), info={"dots": len(pts), "step_mm": step / WORK})


# ------------------------------------------------------------------ farkı bul
def _star(cx, cy, r, n=5):
    return [(cx + (r if i % 2 == 0 else r * 0.45) * math.cos(math.pi * i / n - math.pi / 2),
             cy + (r if i % 2 == 0 else r * 0.45) * math.sin(math.pi * i / n - math.pi / 2)) for i in range(2 * n)]


def spot_difference(line: Image.Image, box_mm: tuple[float, float], age: int, seed: int, count: int = 5
                    ) -> Activity:
    """Aynı çizginin iki kopyası; alttakinde `count` küçük değişiklik (modelsiz): küçük parça silme, parçayı
    aynalama, kapalı küçük alanı karartma, boş alana küçük şekil ekleme. Değişiklikler birbirinden uzak seçilir;
    yeterli aday yoksa bulunan kadar yapılır ve başlık gerçek sayıyı söyler."""
    W, H = px(box_mm[0]), px(box_mm[1])
    gap = px(6)
    art = fit(line, W, (H - gap) // 2)
    a = np.asarray(art) < 128
    h, w = a.shape
    pxmm = DPI / 25.4
    rng = random.Random(seed)
    cands: list[tuple[str, float, float, object]] = []
    # 1) küçük mürekkep parçaları (kenara değmeyen): sil ya da aynala
    lab, n = raster.label(a)
    ar = raster.areas(lab, n)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])).tolist())
    lo, hi = (2.0 * pxmm) ** 2, (18.0 * pxmm) ** 2
    ys, xs = np.nonzero(lab)
    ls = lab[ys, xs]
    comps: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    if len(ls):
        o = np.argsort(ls, kind="stable")
        cuts = np.searchsorted(ls[o], np.arange(1, n + 2))
        for i in range(1, n + 1):
            if i in edge or not lo <= ar[i] <= hi:
                continue
            sel = o[cuts[i - 1]:cuts[i]]
            yy, xx = ys[sel], xs[sel]
            comps[i] = (yy, xx)
            cands.append(("sil", float(xx.mean()), float(yy.mean()), i))
            x0, x1 = int(xx.min()), int(xx.max())
            y0, y1 = int(yy.min()), int(yy.max())
            m = np.zeros((y1 - y0 + 1, x1 - x0 + 1), bool)
            m[yy - y0, xx - x0] = True
            mir = m[:, ::-1]
            if (mir & m).sum() / max(1, (mir | m).sum()) < 0.6:
                pad = 3
                win = a[max(0, y0 - pad):y1 + pad + 1, max(0, x0 - pad):x1 + pad + 1].copy()
                own = np.zeros_like(win)
                own[yy - max(0, y0 - pad), xx - max(0, x0 - pad)] = True
                mm = np.zeros_like(win)
                mm[y0 - max(0, y0 - pad):y0 - max(0, y0 - pad) + m.shape[0],
                   x0 - max(0, x0 - pad):x0 - max(0, x0 - pad) + m.shape[1]] = mir
                if not (raster.dilate(mm, 3) & win & ~own).any():
                    cands.append(("aynala", float(xx.mean()), float(yy.mean()), (i, (y0, x0, mir))))
    # 2) kapalı küçük beyaz alan: karart
    wl, wn = raster.label(~a, conn8=False)
    war = raster.areas(wl, wn)
    wedge = set(np.unique(np.concatenate([wl[0], wl[-1], wl[:, 0], wl[:, -1]])).tolist())
    if wn:
        wy, wx = np.nonzero(wl)
        lw = wl[wy, wx]
        wcy = np.bincount(lw, weights=wy, minlength=wn + 1) / np.maximum(war, 1)
        wcx = np.bincount(lw, weights=wx, minlength=wn + 1) / np.maximum(war, 1)
        for i in range(1, wn + 1):
            if i not in wedge and (3.0 * pxmm) ** 2 <= war[i] <= (8.0 * pxmm) ** 2:
                cands.append(("karart", wcx[i], wcy[i], i))
    # 3) geniş boş alan: küçük şekil ekle
    dist = raster.distance(~a[::6, ::6], limit=int(8 * pxmm / 6) + 1)
    free = np.argwhere(dist >= int(7 * pxmm / 6)).tolist()
    rng.shuffle(free)
    for yy, xx in free[: 60]:
        cands.append(("ekle", xx * 6 + 3, yy * 6 + 3, rng.choice(["yildiz", "kalp", "daire"])))
    rng.shuffle(cands)
    # türleri karıştırarak, birbirinden uzak seç
    min_d = math.hypot(w, h) / (2.2 * math.sqrt(max(1, count)))
    chosen: list[tuple[str, float, float, object]] = []
    for pref in range(3):
        for c in sorted(cands, key=lambda c: (sum(1 for x in chosen if x[0] == c[0]), rng.random())):
            if len(chosen) >= count:
                break
            if all(math.hypot(c[1] - x[1], c[2] - x[2]) >= min_d / (1 + pref) for x in chosen):
                chosen.append(c)
        if len(chosen) >= count:
            break
    b = a.copy()
    extra = Image.new("L", (w, h), 0)
    ed = ImageDraw.Draw(extra)
    sw = max(3, px(_stroke(age) * 0.8))
    for kind, x, y, obj in chosen:
        if kind == "sil":
            yy, xx = comps[obj]
            b[yy, xx] = False
        elif kind == "aynala":
            i, (y0, x0, mir) = obj
            yy, xx = comps[i]
            b[yy, xx] = False
            b[y0:y0 + mir.shape[0], x0:x0 + mir.shape[1]] |= mir
        elif kind == "karart":
            b[wl == obj] = True
        else:
            r = 3.5 * pxmm
            if obj == "yildiz":
                ed.polygon(_star(x, y, r), outline=255, width=sw)
            elif obj == "kalp":
                ed.polygon([(x + r * 16 * math.sin(t) ** 3 / 17,
                             y - r * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)) / 17)
                            for t in np.linspace(0, 2 * math.pi, 60)], outline=255, width=sw)
            else:
                ed.ellipse((x - r * 0.8, y - r * 0.8, x + r * 0.8, y + r * 0.8), outline=255, width=sw)
    b |= np.asarray(extra) > 127
    top = Image.fromarray(np.where(a, 0, 255).astype(np.uint8))
    bottom = Image.fromarray(np.where(b, 0, 255).astype(np.uint8))
    canvas = Image.new("L", (W, H), 255)
    ox = (W - w) // 2
    canvas.paste(top, (ox, 0))
    canvas.paste(bottom, (ox, h + gap))
    ans = bottom.convert("L").copy()
    ad = ImageDraw.Draw(ans)
    for _k, x, y, _o in chosen:
        r = 9 * pxmm
        ad.ellipse((x - r, y - r, x + r, y + r), outline=0, width=max(4, px(1.0)))
    n_done = len(chosen)
    return Activity("spot_difference", NAMES["spot_difference"],
                    f"İki resim arasındaki {n_done} farkı bul ve alttaki resimde daire içine al.", two_tone(canvas),
                    answer=two_tone(ans), info={"differences": [{"kind": k, "x": round(x / pxmm, 1),
                                                                  "y": round(y / pxmm, 1)} for k, x, y, _ in chosen],
                                                "asked": count, "made": n_done, "candidates": len(cands)})


# ------------------------------------------------------------------ labirent
def maze(box_mm: tuple[float, float], age: int, seed: int, start: Image.Image | None = None,
         goal: Image.Image | None = None, start_name: str = "", goal_name: str = "") -> Activity:
    """Tek çözümlü labirent (derinlik öncelikli, tohumlu). Hücre ölçüsü yaşa göre (16/12/8 mm); girişte ve
    çıkışta karakterlerin çizgisi."""
    W, H = px(box_mm[0]), px(box_mm[1])
    cell_mm = 16.0 if age <= 6 else 12.0 if age <= 9 else 8.0
    pic = 24.0
    cols = max(3, int((box_mm[0] - 4) // cell_mm))
    rows = max(3, int((box_mm[1] - 2 * pic - 4) // cell_mm))
    rng = random.Random(seed)
    walls = {(c, r): {"N", "S", "E", "W"} for c in range(cols) for r in range(rows)}
    seen, stack = {(0, 0)}, [(0, 0)]
    step = {"N": (0, -1), "S": (0, 1), "E": (1, 0), "W": (-1, 0)}
    opp = {"N": "S", "S": "N", "E": "W", "W": "E"}
    while stack:
        c, r = stack[-1]
        nxt = [(dn, (c + dx, r + dy)) for dn, (dx, dy) in step.items()
               if 0 <= c + dx < cols and 0 <= r + dy < rows and (c + dx, r + dy) not in seen]
        if not nxt:
            stack.pop()
            continue
        dn, cell = rng.choice(nxt)
        walls[(c, r)].discard(dn)
        walls[cell].discard(opp[dn])
        seen.add(cell)
        stack.append(cell)
    walls[(0, 0)].discard("N")
    walls[(cols - 1, rows - 1)].discard("S")
    cp = px(cell_mm)
    gw, gh = cols * cp, rows * cp
    ox, oy = (W - gw) // 2, (H - gh) // 2
    canvas = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(canvas)
    sw = max(3, px(_stroke(age)))

    def draw_walls(dr):
        for (c, r), ws in walls.items():
            x, y = ox + c * cp, oy + r * cp
            for wn, seg in (("N", (x, y, x + cp, y)), ("S", (x, y + cp, x + cp, y + cp)),
                            ("W", (x, y, x, y + cp)), ("E", (x + cp, y, x + cp, y + cp))):
                if wn in ws:
                    dr.line(seg, fill=0, width=sw)
                    dr.ellipse((seg[0] - sw / 2, seg[1] - sw / 2, seg[0] + sw / 2, seg[1] + sw / 2), fill=0)
                    dr.ellipse((seg[2] - sw / 2, seg[3] - sw / 2, seg[2] + sw / 2, seg[3] + sw / 2), fill=0)
    draw_walls(d)
    for im, (cx, cy) in ((start, (ox + cp / 2, oy - px(pic) / 2 - px(2))),
                         (goal, (ox + gw - cp / 2, oy + gh + px(pic) / 2 + px(2)))):
        if im is not None:
            t = fit(char_line(im, pic, pic, age)[1], px(pic), px(pic))
            canvas.paste(t, (int(cx - t.width / 2), int(cy - t.height / 2)))
    # çözüm (cevap anahtarı)
    prev = {(0, 0): None}
    q = [(0, 0)]
    for cell in q:
        if cell == (cols - 1, rows - 1):
            break
        for dn, (dx, dy) in step.items():
            nb = (cell[0] + dx, cell[1] + dy)
            if dn not in walls[cell] and nb in walls and nb not in prev:
                prev[nb] = cell
                q.append(nb)
    path, cur = [], (cols - 1, rows - 1)
    while cur is not None:
        path.append(cur)
        cur = prev.get(cur)
    ans = Image.new("L", (W, H), 255)
    ad = ImageDraw.Draw(ans)
    draw_walls(ad)
    pts = [(ox + c * cp + cp / 2, oy + r * cp + cp / 2) for c, r in reversed(path)]
    ad.line(pts, fill=0, width=max(3, sw // 2))
    who = f" ({start_name} → {goal_name})" if start_name and goal_name else ""
    return Activity("maze", NAMES["maze"], f"Girişten başla, çıkışa giden yolu kalemle çiz{who}.",
                    two_tone(canvas), answer=two_tone(ans),
                    info={"cols": cols, "rows": rows, "cell_mm": cell_mm, "path": len(path)})


# ------------------------------------------------------------------ kelime avı
WORD_RE = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]+")


def book_words(text: str, names: list[str], size: int) -> list[str]:
    """Kelime avının adayları: önce karakter adları, sonra kitapta en sık geçen (en az 3 harf, ızgaraya sığan,
    bağlaç/zamir olmayan) kelimeler; kesme işaretinden sonraki ek atılır. Hepsi büyük harf (Türkçe)."""
    out: list[str] = []
    for nm in names:
        w = tr_upper(re.split(r"['’]", nm.strip())[0].split()[0]) if nm.strip() else ""
        if 3 <= len(w) <= size and WORD_RE.fullmatch(w) and w not in out:
            out.append(w)
    words = [re.split(r"['’]", t)[0] for t in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü'’]+", text)]
    cnt = Counter(w.replace("I", "ı").replace("İ", "i").lower() for w in words)
    first: dict[str, int] = {}
    for i, w in enumerate(words):
        first.setdefault(w.replace("I", "ı").replace("İ", "i").lower(), i)
    for w, _c in sorted(cnt.items(), key=lambda kv: (-kv[1], first[kv[0]])):
        if w in STOP or not 3 <= len(w) <= size:
            continue
        u = tr_upper(w)
        if u not in out:
            out.append(u)
    return out


def word_search(candidates: list[str], box_mm: tuple[float, float], age: int, seed: int, font_dir: Path,
                fill_target: float = 0.55) -> Activity:
    """Izgara yaşa göre (8/10/12); yönler: küçük yaşta yalnız sağa ve aşağı, sonra çapraz, büyükte ters yönler de.
    Kelimeler sırayla yerleştirilir; ızgaranın `fill_target`'ı dolunca durulur. Sığmayanlar bilgi olarak döner."""
    n = 8 if age <= 6 else 10 if age <= 9 else 12
    dirs = [(1, 0), (0, 1)] + ([(1, 1)] if age > 6 else []) + ([(-1, 0), (0, -1), (-1, -1), (1, -1), (-1, 1)]
                                                               if age > 9 else [])
    rng = random.Random(seed)
    grid = [[""] * n for _ in range(n)]
    placed: list[tuple[str, int, int, int, int]] = []
    left: list[str] = []
    used = 0
    for w in candidates:
        if used >= fill_target * n * n:
            left.append(w)
            continue
        spots = []
        for dx, dy in dirs:
            for x in range(n):
                for y in range(n):
                    ex, ey = x + dx * (len(w) - 1), y + dy * (len(w) - 1)
                    if not (0 <= ex < n and 0 <= ey < n):
                        continue
                    ok, overlap = True, 0
                    for i, ch in enumerate(w):
                        g = grid[y + dy * i][x + dx * i]
                        if g and g != ch:
                            ok = False
                            break
                        overlap += g == ch
                    if ok:
                        spots.append((overlap, rng.random(), x, y, dx, dy))
        if not spots:
            left.append(w)
            continue
        _, _, x, y, dx, dy = max(spots)
        for i, ch in enumerate(w):
            if not grid[y + dy * i][x + dx * i]:
                used += 1
            grid[y + dy * i][x + dx * i] = ch
        placed.append((w, x, y, dx, dy))
    letters = "".join(w for w, *_ in placed) or TR_LETTERS
    for y in range(n):
        for x in range(n):
            if not grid[y][x]:
                grid[y][x] = rng.choice(letters + TR_LETTERS)
    W, H = px(box_mm[0]), px(box_mm[1])
    side = min(W, H)
    cp = side // n
    gw = cp * n
    ox, oy = (W - gw) // 2, 0
    canvas = Image.new("L", (W, gw + px(2)), 255)
    d = ImageDraw.Draw(canvas)
    f = font(font_dir, cp * 0.62)
    d.rounded_rectangle((ox, oy, ox + gw, oy + gw), radius=px(3), outline=0, width=max(3, px(0.6)))
    for y in range(n):
        for x in range(n):
            _text_center(d, (ox + x * cp + cp / 2, oy + y * cp + cp / 2), grid[y][x], f)
    ans = canvas.copy()
    ad = ImageDraw.Draw(ans)
    for w, x, y, dx, dy in placed:
        a = (ox + x * cp + cp / 2, oy + y * cp + cp / 2)
        b = (ox + (x + dx * (len(w) - 1)) * cp + cp / 2, oy + (y + dy * (len(w) - 1)) * cp + cp / 2)
        ad.line([a, b], fill=0, width=max(3, int(cp * 0.12)))
    return Activity("word_search", NAMES["word_search"],
                    "Aşağıdaki kelimeleri harflerin arasında bul ve çevresini çiz.", two_tone(canvas),
                    words=[w for w, *_ in placed], answer=two_tone(ans),
                    info={"grid": n, "placed": [w for w, *_ in placed], "not_placed": left, "directions": len(dirs)})


# ------------------------------------------------------------------ eşleştirme
def matching(chars: list[tuple[str, Image.Image]], box_mm: tuple[float, float], age: int,
             seed: int, font_dir: Path) -> list[Activity]:
    """Solda karakterin çizgisi ve adı, sağda karışık sırada gölgesi (dolu siluet): çocuk eşlerini çizgiyle
    birleştirir. Sayfaya sığmayan karakter yeni sayfaya geçer (en az iki karakter gerekir)."""
    if len(chars) < 2:
        return []
    row_mm = 36.0 if age <= 6 else 30.0
    per = max(2, int(box_mm[1] // row_mm))
    out = []
    for p in range(0, len(chars), per):
        part = chars[p:p + per]
        if len(part) < 2 and out:
            part = chars[p - 1:p + 1]                        # son sayfada tek karakter kalmasın
        rng = random.Random(seed + p)
        order = list(range(len(part)))
        for _ in range(50):
            rng.shuffle(order)
            if all(order[i] != i for i in range(len(order))):
                break
        W, H = px(box_mm[0]), px(box_mm[1])
        rh = H // len(part)
        cell = min(int(rh * 0.78), int(W * 0.34))
        canvas = Image.new("L", (W, H), 255)
        d = ImageDraw.Draw(canvas)
        f = font(font_dir, px(4.5 if age <= 6 else 3.8))
        r = px(1.3)
        lx, rx = int(W * 0.06), int(W * 0.94) - cell
        left_dots, right_dots = [], []
        cell_mm = cell * 25.4 / DPI
        for i, (name, rgb) in enumerate(part):
            y = i * rh + (rh - cell) // 2
            art = fit(char_line(rgb, cell_mm, cell_mm - 7, age)[1], cell, cell - px(7))
            canvas.paste(art, (lx + (cell - art.width) // 2, y))
            d.text((lx + cell / 2, y + cell - px(3)), name, font=f, fill=0, anchor="mm")
            left_dots.append((lx + cell + px(4), y + cell / 2))
        for i, j in enumerate(order):
            name, rgb = part[j]
            y = i * rh + (rh - cell) // 2
            src = on_white(rgb)
            src = src.crop(content_box(src))
            s = fit(src, cell, cell, binary=False)
            m = silhouette(s, line=char_line(rgb, cell_mm, cell_mm, age)[1])
            sh = Image.fromarray(np.where(m, 0, 255).astype(np.uint8))
            canvas.paste(sh, (rx + (cell - sh.width) // 2, y + (cell - sh.height) // 2))
            right_dots.append((rx - px(4), y + cell / 2))
        for x, y in left_dots + right_dots:
            d.ellipse((x - r, y - r, x + r, y + r), fill=0)
        ans = canvas.copy()
        ad = ImageDraw.Draw(ans)
        for i, j in enumerate(order):
            ad.line([left_dots[j], right_dots[i]], fill=0, width=max(3, px(0.6)))
        out.append(Activity("matching", NAMES["matching"], "Her karakteri gölgesiyle bir çizgiyle birleştir.",
                            two_tone(canvas), answer=two_tone(ans), info={"characters": [c[0] for c in part]}))
    return out


# ------------------------------------------------------------------ çerçeve ve cevap anahtarı
def frame(box_mm: tuple[float, float], age: int) -> Image.Image:
    """«Kendi resmini çiz» sayfasının yuvarlak köşeli çerçevesi."""
    W, H = px(box_mm[0]), px(box_mm[1])
    im = Image.new("L", (W, H), 255)
    sw = max(3, px(_stroke(age)))
    ImageDraw.Draw(im).rounded_rectangle((sw, sw, W - sw, H - sw), radius=px(6), outline=0, width=sw)
    return im


def answer_pages(items: list[tuple[str, Image.Image]], box_mm: tuple[float, float], font_dir: Path) -> list[Image.Image]:
    """Cevap anahtarı: sayfa başına 2×2 küçük görsel ve başlığı; fazlası yeni sayfaya."""
    W, H = px(box_mm[0]), px(box_mm[1])
    pages = []
    f = font(font_dir, px(4.0))
    for p in range(0, len(items), 4):
        im = Image.new("L", (W, H), 255)
        d = ImageDraw.Draw(im)
        cw, ch = W // 2, H // 2
        for i, (title, a) in enumerate(items[p:p + 4]):
            x, y = (i % 2) * cw, (i // 2) * ch
            d.text((x + cw / 2, y + px(5)), title, font=f, fill=0, anchor="mm")
            t = fit(a, cw - px(8), ch - px(14))
            im.paste(t, (x + (cw - t.width) // 2, y + px(10)))
        pages.append(two_tone(im))
    return pages
