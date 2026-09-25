"""Kitap paleti: kitabın kendi resimlerinden baskıya uygun, beyaz zeminde okunur renkler.

Kurallar (hepsi kitaptan bağımsız; değiştirmek buradaki sabitleri değiştirmektir):
1. Kümeleme: her resim küçültülür (uzun kenar `THUMB` px), renkli pikseller (CIELAB kroma ≥ `C_MIN`, açıklık
   ≤ 95) k-ortalamayla kümelenir (k = 2n + 4, başlangıç sabit tohumlu k-means++ → aynı resim aynı palet).
   Aday sırası: küme payı × (0,5 + kroma/70) — resimde çok yer kaplayan ve renkli olan önce.
2. Baskıya uygunluk: CMYK (kuşe kâğıt) renk uzayının dışına taşan doygunluk kırpılır. Koruyucu sınır
   CIELAB kromasıdır: mavi-mor tonlarda (ton açısı 240°–320°) `C_MAX_BLUE`, ötekilerde `C_MAX`. Ton ve açıklık
   korunur, yalnız kroma düşer. Kroması `C_MIN`'in altındaki (griye yakın) aday elenir; açıklığı `L_MIN`'in
   altındaki aday siyah sayılır, elenir.
3. Okunurluk: renk beyaz zeminde WCAG kontrastı ≥ 4,5 vermeli. Vermiyorsa ton ve kroma korunarak koyulaştırılır;
   gereken koyulaştırma `DARKEN_MAX` açıklık biriminden fazlaysa (renk artık aynı renk değildir) aday elenir.
4. Ayrışma: yeni renk, seçilmiş her renkten CIEDE2000 ΔE ≥ `MIN_DE` uzakta olmalı; değilse elenir.
5. Tamamlama: resimden `n` renk çıkmazsa `TIMAS_KIDS` sırasıyla, seçilmişlerden ayrışanlarla tamamlanır; o da
   yetmezse ayrışma şartı aranmadan en uzak olanlarla. Her rengin `source`'u: "resim" ya da "timas".
6. Ad: Türkçe renk adı tablosunda (`NAMES`) CIEDE2000'e göre en yakın, palette daha önce kullanılmamış ad.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

THUMB = 128                 # kümeleme için resmin uzun kenarı (px)
C_MIN = 15.0                # bunun altı griye yakın: yazı rengi olarak ayırt edilmez
C_MAX = 70.0                # kuşe CMYK'nın kırmızı/turuncu/sarı/yeşil/mor bölgesinde güvenle basılan kroma
C_MAX_BLUE = 55.0           # mavi-mor bölgede CMYK uzayı dardır (saf ekran mavisi basılamaz)
BLUE_HUE = (240.0, 320.0)
L_MIN = 18.0                # bunun altı basılınca siyahtan ayırt edilmez
DARKEN_MAX = 15.0           # kontrast için en çok bu kadar koyulaştırılır
MIN_CONTRAST = 4.5          # WCAG AA, beyaz zemin
MIN_DE = 10.0               # CIEDE2000: palet renkleri birbirinden en az bu kadar ayrışır

# Timaş sabit çocuk paleti: her biri yukarıdaki kuralları geçer (test_autos sınar), birbirinden ayrışır.
TIMAS_KIDS: list[dict] = [
    {"name": "Gece mavisi", "hex": "#1F3B73"},
    {"name": "Kiremit", "hex": "#B0341C"},
    {"name": "Çam yeşili", "hex": "#1F6F5B"},
    {"name": "Menekşe", "hex": "#6A4499"},
    {"name": "Hardal", "hex": "#8A6500"},
    {"name": "Fuşya", "hex": "#A3246B"},
    {"name": "Petrol mavisi", "hex": "#0B6477"},
    {"name": "Zeytin yeşili", "hex": "#4F6B1F"},
]

# Türkçe renk adları; palet renkleri kontrast kuralı gereği koyu-orta tonlardır, tablo o bölgeyi kapsar.
NAMES: list[tuple[str, str]] = [
    ("Gece mavisi", "#1F3B73"), ("Lacivert", "#1B2440"), ("Çivit", "#2E2F85"), ("Kobalt", "#1F4E9C"),
    ("Deniz mavisi", "#1D5C8C"), ("Petrol mavisi", "#0B6477"), ("Turkuaz", "#0F7470"),
    ("Çam yeşili", "#1F6F5B"), ("Orman yeşili", "#2F6B2A"), ("Zeytin yeşili", "#4F6B1F"), ("Haki", "#5F5B2A"),
    ("Hardal", "#8A6500"), ("Turuncu", "#B04A00"), ("Kiremit", "#B0341C"), ("Tarçın", "#8B4513"),
    ("Kestane", "#6B2E1F"), ("Kahverengi", "#5E3A1E"), ("Nar kırmızısı", "#B3202E"), ("Vişne", "#8E1838"),
    ("Bordo", "#6D1A2A"), ("Gül kurusu", "#9A4B5E"), ("Fuşya", "#A3246B"), ("Erik", "#6A2A5E"),
    ("Patlıcan moru", "#4A1F4D"), ("Mor", "#5B2C83"), ("Menekşe", "#6A4499"), ("Arduvaz", "#3F5566"),
    ("Füme", "#3E4448"),
]

_WHITE = np.array([0.95047, 1.0, 1.08883])      # D65


# ------------------------------------------------------------------ renk uzayı
def _hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def _rgb_hex(rgb) -> str:
    r, g, b = (int(round(float(v))) for v in np.clip(rgb, 0, 255))
    return f"#{r:02X}{g:02X}{b:02X}"


def _lin(c: np.ndarray) -> np.ndarray:
    c = np.asarray(c, dtype=float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _gamma(c: np.ndarray) -> np.ndarray:
    c = np.clip(c, 0.0, 1.0)
    return 255.0 * np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)


_M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]])
_MI = np.linalg.inv(_M)


def rgb_to_lab(rgb) -> np.ndarray:
    """sRGB (0–255, son eksen 3) → CIELAB (D65)."""
    xyz = _lin(rgb) @ _M.T / _WHITE
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def lab_to_rgb(lab) -> np.ndarray:
    """CIELAB → sRGB (0–255, uzay dışı kırpılır)."""
    lab = np.asarray(lab, dtype=float)
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], axis=-1)
    xyz = np.where(f > 6 / 29, f ** 3, 3 * (6 / 29) ** 2 * (f - 4 / 29)) * _WHITE
    return _gamma(xyz @ _MI.T)


def hex_lab(h: str) -> np.ndarray:
    return rgb_to_lab(_hex_rgb(h))


def luminance(h: str) -> float:
    """WCAG göreli parlaklık."""
    return float(_lin(_hex_rgb(h)) @ _M[1])


def contrast(a: str, b: str = "#FFFFFF") -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def delta_e(lab1, lab2) -> np.ndarray:
    """CIEDE2000 (Sharma, Wu, Dalal 2005). Girdiler (..., 3) yayınlanabilir."""
    lab1, lab2 = np.asarray(lab1, dtype=float), np.asarray(lab2, dtype=float)
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(C1p * C2p == 0, 0.0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lpm, Cpm = (L1 + L2) / 2, (C1p + C2p) / 2
    hs = h1p + h2p
    hpm = np.where(C1p * C2p == 0, hs,
                   np.where(np.abs(h1p - h2p) <= 180, hs / 2, np.where(hs < 360, (hs + 360) / 2, (hs - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
         + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
    dtheta = 30 * np.exp(-(((hpm - 275) / 25) ** 2))
    Rc = 2 * np.sqrt(Cpm ** 7 / (Cpm ** 7 + 25.0 ** 7))
    Sl = 1 + 0.015 * (Lpm - 50) ** 2 / np.sqrt(20 + (Lpm - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cpm, 1 + 0.015 * Cpm * T
    Rt = -np.sin(np.radians(2 * dtheta)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def _lch(lab) -> tuple[float, float, float]:
    L, a, b = (float(v) for v in lab)
    return L, float(np.hypot(a, b)), float(np.degrees(np.arctan2(b, a)) % 360)


def _from_lch(L: float, C: float, h: float) -> str:
    r = np.radians(h)
    return _rgb_hex(lab_to_rgb([L, C * np.cos(r), C * np.sin(r)]))


def c_max(h: float) -> float:
    return C_MAX_BLUE if BLUE_HUE[0] <= h <= BLUE_HUE[1] else C_MAX


def print_safe(lab) -> str | None:
    """Adayı basılabilir ve beyaz zeminde okunur hâle getirir (modül belgesi, kural 2–3); olmuyorsa None."""
    L, C, h = _lch(lab)
    if C < C_MIN or L < L_MIN:
        return None
    C = min(C, c_max(h))
    hx = _from_lch(L, C, h)
    if contrast(hx) >= MIN_CONTRAST:
        return hx
    lo, hi = max(L_MIN, L - DARKEN_MAX), L          # lo'da da tutmuyorsa renk elenir
    if contrast(_from_lch(lo, C, h)) < MIN_CONTRAST:
        return None
    for _ in range(24):                              # kontrastı sağlayan en açık ton
        mid = (lo + hi) / 2
        if contrast(_from_lch(mid, C, h)) >= MIN_CONTRAST:
            lo = mid
        else:
            hi = mid
    hx = _from_lch(lo, C, h)
    return hx if contrast(hx) >= MIN_CONTRAST else None


# ------------------------------------------------------------------ kümeleme
def _pixels(paths: list[Path]) -> np.ndarray:
    from PIL import Image
    out = []
    for p in paths:
        try:
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((THUMB, THUMB))
                out.append(np.asarray(im, dtype=float).reshape(-1, 3))
        except (OSError, ValueError):
            continue                                  # okunamayan resim paleti düşürmez
    return np.concatenate(out) if out else np.zeros((0, 3))


def _kmeans(x: np.ndarray, k: int, iters: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """Sabit tohumlu k-means++ başlangıçlı k-ortalama. Dönen: (merkezler, küme payları)."""
    rng = np.random.default_rng(0)
    centers = [x[len(x) // 2]]
    d2 = ((x - centers[0]) ** 2).sum(1)
    for _ in range(1, k):
        if d2.sum() <= 0:
            break
        centers.append(x[rng.choice(len(x), p=d2 / d2.sum())])
        d2 = np.minimum(d2, ((x - centers[-1]) ** 2).sum(1))
    c = np.array(centers)
    xx = (x ** 2).sum(1)[:, None]

    def nearest(c):                                   # (N, k) uzaklık matrisi; (N, k, 3) kurulmaz
        return np.argmin(xx - 2 * x @ c.T + (c ** 2).sum(1)[None], axis=1)

    for _ in range(iters):
        lab = nearest(c)
        new = np.array([x[lab == i].mean(0) if np.any(lab == i) else c[i] for i in range(len(c))])
        if np.allclose(new, c, atol=0.05):
            c = new
            break
        c = new
    lab = nearest(c)
    share = np.bincount(lab, minlength=len(c)) / len(x)
    return c, share


def _candidates(paths: list[Path], n: int) -> list[np.ndarray]:
    rgb = _pixels(paths)
    if not len(rgb):
        return []
    lab = rgb_to_lab(rgb)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    lab = lab[(chroma >= C_MIN) & (lab[:, 0] <= 95)]
    if len(lab) < 2:
        return []
    k = min(len(np.unique(np.round(lab), axis=0)), 2 * n + 4)
    centers, share = _kmeans(lab, k)
    score = share * (0.5 + np.minimum(np.hypot(centers[:, 1], centers[:, 2]), 70) / 70)
    order = sorted(range(len(centers)), key=lambda i: (-score[i], i))
    return [centers[i] for i in order if share[i] > 0]


# ------------------------------------------------------------------ adlandırma
_NAME_LAB = np.array([hex_lab(h) for _, h in NAMES])


def name_for(hx: str, used: set[str] = frozenset()) -> str:
    d = delta_e(hex_lab(hx)[None], _NAME_LAB)
    for i in np.argsort(d, kind="stable"):
        if NAMES[i][0] not in used:
            return NAMES[i][0]
    return NAMES[int(np.argmin(d))][0]


# ------------------------------------------------------------------ dışa açık
def extract(image_paths: list[Path], n: int = 6) -> list[dict]:
    """Resimlerden `n` renk: [{"name", "hex", "source": "resim"|"timas"}] (modül belgesindeki kurallarla)."""
    kept: list[tuple[str, str]] = []                 # (hex, kaynak)

    def distinct(hx: str) -> bool:
        return all(float(delta_e(hex_lab(hx), hex_lab(k))) >= MIN_DE for k, _ in kept)

    for c in _candidates([Path(p) for p in image_paths], n):
        if len(kept) >= n:
            break
        hx = print_safe(c)
        if hx and distinct(hx):
            kept.append((hx, "resim"))
    for t in TIMAS_KIDS:
        if len(kept) >= n:
            break
        if distinct(t["hex"]):
            kept.append((t["hex"], "timas"))
    rest = [t["hex"] for t in TIMAS_KIDS if t["hex"] not in {k for k, _ in kept}]
    while len(kept) < n and rest:                    # ayrışan kalmadı: en uzak olan
        far = max(rest, key=lambda h: min((float(delta_e(hex_lab(h), hex_lab(k))) for k, _ in kept), default=0))
        kept.append((far, "timas"))
        rest.remove(far)
    used: set[str] = set()
    out = []
    for hx, src in kept:
        timas = next((t["name"] for t in TIMAS_KIDS if t["hex"] == hx), None)
        name = timas if timas and timas not in used else name_for(hx, used)
        used.add(name)
        out.append({"name": name, "hex": hx, "source": src})
    return out


def _hex_of(c) -> str:
    return (c.get("hex") if isinstance(c, dict) else str(c)).upper()


def assign_characters(characters: list[dict], colors: list) -> dict[str, str]:
    """Karakter → renk. Ana karakterler (role "ANA") önce, sonra verildiği sıra. İlk karaktere paletin ilk rengi;
    her sonraki karaktere, verilmiş renklere en uzak (en küçük ΔE'si en büyük) renk; eşitlikte palet sırası.
    Karakter renkten çoksa renkler en az kullanılandan başlayarak aynı kuralla yeniden dağıtılır.
    Aynı girdi her zaman aynı sonucu verir."""
    hexes = [_hex_of(c) for c in colors]
    if not hexes:
        return {}
    labs = [hex_lab(h) for h in hexes]
    names = [c["name"] if isinstance(c, dict) else str(c) for c in characters]
    roles = [(c.get("role") if isinstance(c, dict) else None) for c in characters]
    order = [i for i in range(len(names)) if roles[i] == "ANA"] + [i for i in range(len(names)) if roles[i] != "ANA"]
    uses = [0] * len(hexes)
    given: list[int] = []
    out: dict[str, str] = {}
    for i in order:
        if names[i] in out:
            continue
        least = min(uses)
        pool = [j for j in range(len(hexes)) if uses[j] == least]
        if not given:
            j = pool[0]
        else:
            j = max(pool, key=lambda j: (min(float(delta_e(labs[j], labs[g])) for g in given if g != j)
                                         if any(g != j for g in given) else float("inf"), -j))
        uses[j] += 1
        given.append(j)
        out[names[i]] = hexes[j]
    return out
