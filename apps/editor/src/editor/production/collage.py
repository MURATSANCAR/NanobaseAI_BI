"""Kolaj kapak (kapağın ikinci tarzı): siyah-beyaz analog fotoğraf yırtık kâğıt gibi kesilip beyaz zemine konur,
fotoğraftaki öznenin yukarı uzanan parçası kesimin üstünden taşar; arkada gri lekeler ve yırtık şeritler, başlık
daktilo yazılı kâğıt şeritlerde, yazar adı ince geniş aralıklı yazıyla. Arka kapak, sırt ve barkod mevcut kalıptan
(`cover.py` / `templates/cover.typ`); bu modül yalnız ön kapağı kurar.

Kapak tarzı editörün seçimidir (`kolaj/kolaj.json` → `style`): `illustrated` (resimli, bugünkü yol) | `collage` |
`typographic` (yazı ağırlıklı). Seçim yoksa bugünkü kural geçerlidir (kapak resmi varsa resimli; resimsiz kitapta
tipografik). `studio.build_cover` önce `build_cover(d)`'yi sorar; True dönerse kapağı bu modül kurmuştur.

Fotoğraf iki kaynaktan: (a) görsel model, kitabın profilinden/özetinden yazılan sahneyle (kitaba özel istem yok;
dil modeli genel kalıbı doldurur, `prompts/production_collage_scene.md`), bu tarza özel negatif istemle
(analog görünümle çelişen «blurry, low quality» yok); her çağrıda 2–3 tohumla aday. (b) editörün yüklediği fotoğraf
(`photo.ingest`: EXIF yönü, sRGB, üst veri silinir). Model fotoğrafı ekranda «taslak» uyarısı taşır (ticari lisans).

Kurallar (hepsi kitaptan bağımsız; değiştirmek buradaki sabitleri değiştirmektir):
1. Belirlenimcilik: bütün rastgelelik tek tohumdan (`seed_for(başlık, düzen)`): aynı kitap + aynı düzen numarası +
   aynı fotoğraf → bayt bayt aynı ön kapak. «Başka düzen» düzen numarasını bir artırır.
2. Taşan figür (`figure_cut`): fotoğrafın üst şeridinden gökyüzü/düz zemin tonu ve gürültüsü ölçülür; zemine benzeyen
   ve üst kenara bağlı bölge «gök»tür. Gökün satır payı %35'in altına düştüğü satır ufuktur. Ufuk çizgisine bağlı,
   gök olmayan bölge figürdür (uçan kuş, bulut gibi kopuk lekeler sayılmaz); ufuk yoksa (düz fonda duran figür) fon
   dışı her şey figürdür. Kesimin üst kenarı figürün maskesinden:
   figürün satır genişliği gövde genişliğinin %40'ına ilk ulaştığı satırın biraz üstü (baş içeride, yukarı uzanan
   ince parça dışarıda); ince parça yoksa figür yüksekliğinin %22'si (baş taşar). Üst şerit düz değilse (gürültü
   `FLAT_NOISE` üstü) taşma yapılmaz, kesim düz yırtık kâğıttır; ekranda nedeni yazılır.
3. Etiket şeritleri başlıktan ölçülür (`label_lines`): kelimeler sırası bozulmadan en dengeli satırlara bölünür,
   her şerit en çok kesim genişliğinin `LABEL_MAX_W`'i; satır sayısı puntonun `LABEL_TARGET` oranına ulaştığı en
   küçük sayı (yoksa puntoyu en büyük veren). Editör şeritleri elle yazarsa her satır bir şerittir ve ortak punto
   en uzun şeride göre küçülür; `LABEL_MIN_PT` altına düşecekse açık hata (kesilmez).
4. Leke kütüphanesi (`BLOBS`): organik gri leke ve yırtık kâğıt şerit; düzen tohumuyla 3–4 tanesi seçilir, sağ-sol
   aynalanabilir. Tarz siyah-beyazdır: lekeler gri tonlarda, yazı rengi planın mürekkebi (`INK`), etiket kâğıdı
   sıcak beyaz. Baskı: ön kapak 300 dpi gri tonlu PNG (CMYK'ya yalnız siyah kanalla döner), yazılar vektör.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import re
import secrets
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DIR = "kolaj"
STATE = "kolaj.json"
STYLES = ("illustrated", "collage", "typographic")
PHOTO_ID = re.compile(r"^k_[0-9a-f]{8}$")
FONT_DIR = Path(__file__).resolve().parent / "fonts"
TYPEWRITER = ("Special Elite", "SpecialElite-Regular.ttf")
TYPEWRITER_FALLBACK = ("Courier Prime", "CourierPrime-Bold.ttf")
THIN = ("Poppins", "Poppins-Light.ttf", 300)

DPI = 300
MM = DPI / 25.4
PT_MM = 25.4 / 72
INK = "#2C2C2A"                  # etiket yazısı (plan.INK)
AUTHOR_INK = "#3A3A3A"
SPINE = "#3A3A3A"                # sırt ve arka kapak başlığı: kolaj siyah-beyaz, renkli vurgu yok
BACK_BG = "#F4F2EE"              # arka kapak zemini: sıcak beyaz kâğıt

LABEL_MAX_W = 0.80               # şerit genişliği ≤ kesim genişliğinin bu kadarı
LABEL_PT_PER_MM = 0.165          # en büyük etiket puntosu = kesim genişliği (mm) × bu (135 mm → 22 pt)
LABEL_TARGET = 0.85              # bu oranın üstündeki puntoya ulaşan en az satırlı bölme seçilir
LABEL_MIN_PT = 11.0
LABEL_PAD = (4.5, 2.4)           # şerit iç boşluğu (mm): yatay, dikey
TRACKING_PT = -0.2               # daktilo harf aralığı (Typst ile aynı)
AUTHOR_PT_PER_MM = 0.078         # yazar adı puntosu = kesim genişliği × bu (9–12 pt arası)
AUTHOR_TRACK = 0.32              # yazar adı harf aralığı (punto × bu)

ANALYSIS_W = 640                 # figür çözümlemesi bu genişlikte (hız); maske baskı ölçüsüne büyütülür
FLAT_NOISE = 18.0                # üst şerit gürültüsü (0–255) bunun üstündeyse zemin düz değil: taşma yok
PHOTO_ASPECT = (0.66, 1.0)       # fotoğraf en/boy aralığı; dışındaki fotoğraf ortadan kırpılır
GEN_ASPECT = 0.8                 # model fotoğrafı 4:5 dik üretilir
DRAFT = "Taslak — ticari kullanım izni bekleniyor"

# Görsel model istemi: genel kalıp; konu (özne, hareket, yer, dönem) dil modelinden, kitaba özel cümle yok.
PHOTO_FRAME = ("Black and white analog film photograph, {era} documentary snapshot. {subject} {gesture} {setting} "
               "Above the subject the upper part of the picture is plain, empty, pale sky or a plain pale wall with "
               "nothing else in it, so the raised gesture stands out cleanly against it. If a person appears, the face "
               "is not visible (seen from behind or turned away). Heavy film grain, dust specks and fine scratches, "
               "faded low-contrast grey tones, slightly soft focus, old photographic print. Monochrome, no colour. "
               "No text or letters anywhere.")
# Kolaja özel negatif: analog görünümü bozan «blurry, low quality, grain» gibi terimler yok (tarzın kendisi).
NEGATIVE = ("text, letters, words, caption, signature, watermark, logo, colour, color, saturated colors, sepia tint, "
            "modern digital look, oversharpened, HDR, studio lighting, frame, border, collage, crowd, visible face, "
            "deformed, extra limbs, extra fingers")
SCENE_SCHEMA = {"type": "object", "additionalProperties": False,
                "required": ["subject", "gesture", "setting", "era", "why"],
                "properties": {k: {"type": "string"} for k in ("subject", "gesture", "setting", "era", "why")}}


# ------------------------------------------------------------------ durum
def _dir(d: Path) -> Path:
    p = d / DIR
    p.mkdir(exist_ok=True)
    return p


def load(d: Path) -> dict:
    p = d / DIR / STATE
    st = json.loads(p.read_text()) if p.exists() else {}
    return {"version": 1, "style": None, "layout": 0, "photos": [], "selected": None, "labels": None,
            "scene": None, "job": None, **st}


def save(d: Path, st: dict, by: str | None = None) -> dict:
    st["updated_at"] = time.time()
    if by:
        st["updated_by"] = by
    tmp = _dir(d) / (STATE + ".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    tmp.replace(d / DIR / STATE)
    return st


@contextlib.contextmanager
def locked(d: Path):
    """Durum yazımı ve kapak kurulumu tek sıra (API iş parçacıkları ve stüdyo işçisi ayrı süreçler)."""
    import fcntl
    with open(_dir(d) / "kolaj.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def style_of(d: Path) -> str | None:
    return load(d).get("style")


def selected(st: dict) -> dict | None:
    return next((p for p in st["photos"] if p["id"] == st.get("selected")), None)


def seed_for(title: str, layout: int = 0) -> int:
    """Kitaptan türeyen tohum: aynı başlık ve düzen numarası hep aynı kolajı verir."""
    return int(hashlib.sha256(f"{title}\n{int(layout)}".encode()).hexdigest()[:12], 16)


def _log(d: Path, what: str, by: str, **extra) -> None:
    with (d / "provenance.jsonl").open("a") as f:
        f.write(json.dumps({"kind": "collage", "what": what, "by": by, "at": time.time(), **extra},
                           ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ etiket ölçümü
@lru_cache(maxsize=None)
def _face(file: str) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / file), 1000)


@lru_cache(maxsize=None)
def _cmap(file: str) -> frozenset[int]:
    from fontTools.ttLib import TTFont
    return frozenset(TTFont(str(FONT_DIR / file), lazy=True).getBestCmap())


def label_font(texts: list[str]) -> tuple[str, str]:
    """Daktilo fontu; metinde fontta olmayan harf varsa yedek daktilo fontu (ikisinde de yoksa açık hata)."""
    chars = {c for t in texts for c in t if not c.isspace()}
    for fam, file in (TYPEWRITER, TYPEWRITER_FALLBACK):
        if all(ord(c) in _cmap(file) for c in chars):
            return fam, file
    missing = sorted(c for c in chars if ord(c) not in _cmap(TYPEWRITER_FALLBACK[1]))
    raise ValueError(f"Etiket fontunda olmayan harf: {''.join(missing)}")


def text_mm(text: str, size_pt: float, file: str = TYPEWRITER[1], tracking_pt: float = TRACKING_PT) -> float:
    """Yazının basılı genişliği (mm): fontun ilerleme genişliği + harf aralığı."""
    return (_face(file).getlength(text) / 1000 * size_pt + tracking_pt * max(0, len(text) - 1)) * PT_MM


def _fit_pt(text: str, max_mm: float, file: str) -> float:
    adv = _face(file).getlength(text) / 1000
    return (max_mm / PT_MM - TRACKING_PT * max(0, len(text) - 1)) / adv if adv else 1e9


def _partition(words: list[str], n: int, width) -> list[str]:
    """Kelimeleri sırası bozulmadan n satıra böler; en geniş satırı en dar olan bölme (dinamik programlama)."""
    k = len(words)
    inf = float("inf")
    best = [[inf] * (k + 1) for _ in range(n + 1)]
    cut = [[0] * (k + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for m in range(1, n + 1):
        for j in range(m, k + 1):
            for i in range(m - 1, j):
                v = max(best[m - 1][i], width(" ".join(words[i:j])))
                if v < best[m][j]:
                    best[m][j], cut[m][j] = v, i
    out, j = [], k
    for m in range(n, 0, -1):
        i = cut[m][j]
        out.append(" ".join(words[i:j]))
        j = i
    return out[::-1]


def label_lines(title: str, trim_w: float, lines: list[str] | None = None) -> dict:
    """Başlıktan etiket şeritleri ve ortak punto. `lines` verilirse (editör) her satır bir şerit.
    Dönen: {"lines", "size_pt", "font", "file", "max_mm"}."""
    max_pt = trim_w * LABEL_PT_PER_MM
    max_mm = trim_w * LABEL_MAX_W - 2 * LABEL_PAD[0]
    if lines is not None:
        lines = [" ".join(str(x).split()) for x in lines]
        if not lines or any(not x for x in lines):
            raise ValueError("Boş etiket şeridi olamaz")
        fam, file = label_font(lines)
        size = min(max_pt, *(_fit_pt(x, max_mm, file) for x in lines))
        if size < LABEL_MIN_PT:
            long = max(lines, key=lambda x: text_mm(x, 1, file))
            raise ValueError(f"«{long}» şeride sığmıyor; iki şeride bölün")
        return {"lines": lines, "size_pt": round(size, 2), "font": fam, "file": file, "max_mm": round(max_mm, 2)}
    words = title.split()
    if not words:
        raise ValueError("Kitabın adı yok")
    fam, file = label_font(words)
    options = []
    for n in range(1, len(words) + 1):
        ls = _partition(words, n, lambda s: text_mm(s, 1, file))
        size = min(max_pt, *(_fit_pt(x, max_mm, file) for x in ls))
        options.append((ls, size))
        if size >= max_pt * LABEL_TARGET:
            break
    ls, size = next(((a, s) for a, s in options if s >= max_pt * LABEL_TARGET),
                    max(options, key=lambda o: (o[1], -len(o[0]))))
    if size < LABEL_MIN_PT:
        long = max(ls, key=lambda x: text_mm(x, 1, file))
        raise ValueError(f"«{long}» şeride sığmıyor; etiketleri elle bölün")
    return {"lines": ls, "size_pt": round(size, 2), "font": fam, "file": file, "max_mm": round(max_mm, 2)}


# ------------------------------------------------------------------ figür (taşma)
def _grow(reach: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    while True:
        n = reach.copy()
        n[1:] |= reach[:-1]
        n[:-1] |= reach[1:]
        n[:, 1:] |= reach[:, :-1]
        n[:, :-1] |= reach[:, 1:]
        n &= allowed
        if (n == reach).all():
            return reach
        reach = n


def _flood(seed: np.ndarray, allowed: np.ndarray) -> np.ndarray:
    """`seed`'den `allowed` içinde 4-komşulukla yayılan bölge. Önce 4× küçük ızgarada (blok tamamen izinliyse),
    sonra tam çözünürlükte ince uzantılar (kol, dal) tamamlanır; yakınsayana kadar (tur sınırı yok)."""
    s = 4
    h, w = allowed.shape
    H, W = -(-h // s) * s, -(-w // s) * s
    pa, ps = np.zeros((H, W), bool), np.zeros((H, W), bool)
    pa[:h, :w], ps[:h, :w] = allowed, seed
    small = pa.reshape(H // s, s, W // s, s).all(axis=(1, 3))
    sseed = ps.reshape(H // s, s, W // s, s).any(axis=(1, 3)) & small
    reach = _grow(sseed, small)
    full = np.repeat(np.repeat(reach, s, 0), s, 1)[:h, :w] & allowed
    return _grow(full | (seed & allowed), allowed)


def figure_cut(img: Image.Image) -> dict:
    """Fotoğrafta taşacak figür ve kesimin üst kenarı (modül başındaki kural 2). Dönen oranlar fotoğraf yüksekliğine
    göre: `top` figürün tepesi, `cut` yırtık kesimin üst kenarı, `horizon` ufuk; `mask` (bool, çözümleme ölçüsünde)
    yalnız bellekte döner, kayda yazılmaz."""
    g = img.convert("L")
    s = min(1.0, ANALYSIS_W / g.width)
    small = g.resize((max(8, round(g.width * s)), max(8, round(g.height * s))), Image.Resampling.LANCZOS)
    L = np.asarray(small.filter(ImageFilter.GaussianBlur(1.2)), np.float32)
    h, w = L.shape
    band = L[: max(4, h // 25)]
    sky = float(np.median(band))
    noise = float(np.percentile(np.abs(band - sky), 95))
    out = {"method": "key", "sky": round(sky, 1), "noise": round(noise, 1), "flat": noise < FLAT_NOISE,
           "overflow": False, "top": None, "cut": None, "horizon": None, "mask": None}
    if not out["flat"]:
        return {**out, "note": "Fotoğrafın üst kısmı düz değil; figür taşırılmadı."}
    t = max(noise * 1.6, 12.0)
    bgish = np.abs(L - sky) < t
    seed = np.zeros_like(bgish)
    seed[0] = bgish[0]
    bg = _flood(seed, bgish)
    low = np.nonzero(bg.mean(axis=1) < 0.35)[0]
    horizon = int(low[0]) if len(low) else h
    fg = ~bg
    fg[horizon:] = False
    seed = np.zeros_like(fg)
    if horizon > 0:
        seed[horizon - 1] = fg[horizon - 1]
    fig = _flood(seed, fg)
    if not fig.any() and horizon == h:
        fig = fg                                     # zemin yok (düz fon üstünde duran figür): fon dışı her şey
    rows = fig.sum(axis=1)
    on = np.nonzero(rows >= max(2, int(0.004 * w)))[0]
    if not len(on) or horizon - int(on[0]) < 0.12 * h:
        return {**out, "horizon": round(horizon / h, 4), "note": "Fotoğrafta taşırılacak bir figür bulunamadı."}
    top = int(on[0])
    fh = horizon - top
    body = float(np.median(rows[top + fh // 2: horizon])) if horizon - (top + fh // 2) > 0 else float(rows.max())
    wide = np.nonzero(rows[top:horizon] >= 0.4 * body)[0]
    cut = top + int(wide[0]) - int(0.03 * h) if len(wide) else top
    if cut - top < 0.08 * fh:                       # yukarı uzanan ince parça yok: baş taşar
        cut = top + int(0.22 * fh)
    cut = int(np.clip(cut, top + 0.08 * fh, top + 0.45 * fh))
    cut = int(np.clip(cut, 0.10 * h, 0.60 * h))
    if cut <= top:
        return {**out, "horizon": round(horizon / h, 4), "note": "Figür fotoğrafın tepesine değiyor; taşırılmadı."}
    return {**out, "overflow": True, "top": round(top / h, 4), "cut": round(cut / h, 4),
            "horizon": round(horizon / h, 4), "mask": fig}


def _public_cut(c: dict) -> dict:
    return {k: v for k, v in c.items() if k != "mask"}


def fit_aspect(img: Image.Image) -> Image.Image:
    """En/boy `PHOTO_ASPECT` dışındaysa ortadan kırpılır (panorama ya da çok ince dik fotoğraf)."""
    a = img.width / img.height
    lo, hi = PHOTO_ASPECT
    if a > hi:
        nw = round(img.height * hi)
        x = (img.width - nw) // 2
        return img.crop((x, 0, x + nw, img.height))
    if a < lo:
        nh = round(img.width / lo)
        y = (img.height - nh) // 2
        return img.crop((0, y, img.width, y + nh))
    return img


# ------------------------------------------------------------------ düzen (saf; mm)
def layout(seed: int, trim_w: float, trim_h: float, bleed: float, safe: float, aspect: float, cut: dict,
           labels: dict, author: str) -> dict:
    """Ön kapağın yerleşimi (mm, ön panelin sol üstü köken; x=0 sırt kesimi, sağda ve üst/altta taşma payı).
    Her şey tohumdan: fotoğraf genişliği ve yeri, kesim kenarları, lekeler, etiketlerin kayması ve açısı."""
    rng = np.random.default_rng(seed)
    W, H = trim_w + bleed, trim_h + 2 * bleed
    top_lim, bot_lim = bleed + safe, bleed + trim_h - safe
    size = labels["size_pt"]
    lab_h = size * PT_MM * 1.05 + 2 * LABEL_PAD[1]
    step = lab_h * rng.uniform(0.86, 0.96)
    a_pt = float(np.clip(trim_w * AUTHOR_PT_PER_MM, 9.0, 12.0))
    a_track = a_pt * AUTHOR_TRACK
    a_h = a_pt * PT_MM
    top_frac = cut["cut"] if cut.get("overflow") else float(rng.uniform(0.10, 0.18))
    vis_frac = cut["top"] if cut.get("overflow") else top_frac
    bottom_frac = float(rng.uniform(0.90, 0.96))
    pw = trim_w * float(rng.uniform(0.78, 0.86))
    top_gap = float(rng.uniform(4.0, 16.0))
    a_gap = float(rng.uniform(9.0, 16.0))
    lift = float(rng.uniform(0.25, 0.40))
    if not author:                                 # yazar adı yoksa onun yeri ayrılmaz (yığın ortalanır)
        a_gap, a_h = 0.0, 0.0
    n = len(labels["lines"])
    for _ in range(200):                           # sığana kadar fotoğraf küçülür (her tur %2,5)
        ph = pw / aspect
        y0 = top_lim + top_gap - vis_frac * ph
        piece_top, piece_bot = y0 + top_frac * ph, y0 + bottom_frac * ph
        l0 = piece_bot - lift * lab_h
        a_y = l0 + (n - 1) * step + lab_h / 2 + a_gap
        if a_y + a_h <= bot_lim or pw < trim_w * 0.35:
            break
        pw *= 0.975
    x0 = (trim_w - pw) / 2 + trim_w * float(rng.uniform(-0.03, 0.03))
    x0 = float(np.clip(x0, 0.0, trim_w - pw))
    spare = bot_lim - (a_y + a_h)
    if spare > 0:                                  # artan yer: yığın dikeyde ortalanır
        shift = spare * 0.5
        y0, piece_top, piece_bot, l0, a_y = y0 + shift, piece_top + shift, piece_bot + shift, l0 + shift, a_y + shift
    vis_h = piece_bot - piece_top
    # etiketler: sırayla sağa-sola kayar, dönüşümlü açı
    sign = 1 if rng.random() < 0.5 else -1
    labs = []
    for i, text in enumerate(labels["lines"]):
        w = text_mm(text, size, labels["file"]) + 2 * LABEL_PAD[0]
        shift = sign * (1 if i % 2 == 0 else -1) * trim_w * float(rng.uniform(0.03, 0.10))
        cx = float(np.clip(trim_w / 2 + shift, safe + w / 2, trim_w - safe - w / 2)) if w < trim_w - 2 * safe \
            else trim_w / 2
        rot = -sign * (1 if i % 2 == 0 else -1) * float(rng.uniform(1.2, 3.0))
        labs.append({"text": text, "cx": round(cx, 2), "cy": round(l0 + i * step, 2), "w": round(w, 2),
                     "h": round(lab_h, 2), "rot": round(rot, 2), "wear": round(float(rng.uniform(9, 15)), 1)})
    # lekeler: kütüphaneden 3–4 tane, fotoğraf kutusuna göre; aynalama
    mirror = bool(rng.random() < 0.5)
    picks = [b for b in BLOBS if rng.random() < b["p"]] or [BLOBS[0], BLOBS[2]]
    if not any(b["kind"] == "strip" for b in picks):
        picks.append(BLOBS[2])
    blobs = []
    for b in picks:
        spec = b["make"](rng, x0, piece_top, pw, vis_h)
        if mirror:
            spec["cx"] = x0 + pw - (spec["cx"] - x0)
            spec["rot"] = -spec["rot"]
        # sırt kıvrımına (x=0) taşmasın: lekenin en geniş yarıçapı + 2 mm içeride
        spec["cx"] = float(np.clip(spec["cx"], max(spec["rx"], spec["ry"]) * 0.9 + 2.0, W))
        blobs.append({"kind": b["kind"], "name": b["name"], **{k: round(v, 2) if isinstance(v, float) else v
                                                               for k, v in spec.items()}})
    return {"seed": seed, "panel": [round(W, 2), round(H, 2)],
            "photo": {"x": round(x0, 2), "y": round(y0, 2), "w": round(pw, 2), "h": round(pw / aspect, 2),
                      "top_frac": round(top_frac, 4), "bottom_frac": round(bottom_frac, 4),
                      "left_frac": round(float(rng.uniform(0.03, 0.06)), 4),
                      "right_frac": round(float(rng.uniform(0.94, 0.97)), 4),
                      "squareness": round(float(rng.uniform(3.5, 5.5)), 2), "wobble": round(float(rng.uniform(2.0, 2.8)), 2),
                      "rough": round(float(rng.uniform(1.1, 1.5)), 2)},
            "film": {"fade": [round(float(rng.uniform(52, 62)), 1), round(float(rng.uniform(218, 228)), 1)],
                     "gamma": round(float(rng.uniform(1.0, 1.12)), 3), "grain": round(float(rng.uniform(13, 18)), 1),
                     "dust": int(rng.integers(220, 340)), "hairs": int(rng.integers(4, 9)),
                     "soft": round(float(rng.uniform(0.6, 0.85)), 2), "blotch": round(float(rng.uniform(3, 5)), 2)},
            "blobs": blobs, "labels": labs,
            "author": {"text": author, "y": round(a_y, 2), "size_pt": round(a_pt, 2), "tracking_pt": round(a_track, 2)}
            if author else None,
            "mirror": mirror}


# Leke kütüphanesi: her biri fotoğraf kutusuna göre konum/ölçü üretir (mm). `p` seçilme olasılığı; `front` fotoğrafın
# önünde. Gri ton 0–255 (siyah-beyaz tarz; renkli rol kullanılmaz).
BLOBS = [
    {"kind": "organic", "name": "üst leke", "p": 0.9,
     "make": lambda r, x, t, w, h: {"cx": x + w * r.uniform(0.10, 0.35), "cy": t + h * r.uniform(-0.12, 0.10),
                                    "rx": w * r.uniform(0.25, 0.33), "ry": w * r.uniform(0.13, 0.18),
                                    "rot": r.uniform(-20, 8), "grey": r.uniform(150, 172), "e": 2.0,
                                    "organic": r.uniform(1.3, 1.9), "front": False, "opacity": 1.0}},
    {"kind": "organic", "name": "koyu leke", "p": 0.7,
     "make": lambda r, x, t, w, h: {"cx": x + w * r.uniform(-0.04, 0.08), "cy": t + h * r.uniform(0.60, 0.82),
                                    "rx": w * r.uniform(0.11, 0.16), "ry": w * r.uniform(0.08, 0.11),
                                    "rot": r.uniform(-10, 10), "grey": r.uniform(80, 100), "e": 2.0,
                                    "organic": r.uniform(1.0, 1.4), "front": False, "opacity": 1.0}},
    {"kind": "strip", "name": "arka şerit", "p": 0.85,
     "make": lambda r, x, t, w, h: {"cx": x + w * r.uniform(0.90, 1.02), "cy": t + h * r.uniform(0.18, 0.45),
                                    "rx": w * r.uniform(0.08, 0.11), "ry": h * r.uniform(0.26, 0.36),
                                    "rot": r.uniform(6, 14), "grey": r.uniform(205, 220), "e": 5.0,
                                    "tear": 1100.0, "front": False, "opacity": 1.0}},
    {"kind": "strip", "name": "ön şerit", "p": 0.6,
     "make": lambda r, x, t, w, h: {"cx": x + w * r.uniform(0.86, 0.97), "cy": t + h * r.uniform(0.58, 0.82),
                                    "rx": w * r.uniform(0.045, 0.065), "ry": h * r.uniform(0.13, 0.19),
                                    "rot": r.uniform(-10, -4), "grey": r.uniform(190, 205), "e": 5.0,
                                    "tear": 900.0, "front": True, "opacity": 0.93}},
]


# ------------------------------------------------------------------ çizim yardımcıları (px)
def px(mm: float) -> int:
    return int(round(mm * MM))


def _noise1d(n: int, rng, bands) -> np.ndarray:
    """Kapalı eğri boyunca periyodik gürültü: bands = [(genlik, kmin, kmax, adet)]."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    out = np.zeros(n)
    for amp, kmin, kmax, cnt in bands:
        for _ in range(cnt):
            k = rng.integers(kmin, kmax + 1)
            out += amp / math.sqrt(cnt) * rng.uniform(0.4, 1.0) * np.sin(k * t + rng.uniform(0, 2 * np.pi))
    return out


def _superellipse(cx, cy, a, b, e, n, radial) -> list[tuple[float, float]]:
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    x = cx + a * np.sign(c) * np.abs(c) ** (2 / e)
    y = cy + b * np.sign(s) * np.abs(s) ** (2 / e)
    dx, dy = x - cx, y - cy
    ln = np.hypot(dx, dy) + 1e-9
    return list(zip((x + radial * dx / ln).tolist(), (y + radial * dy / ln).tolist()))


def _torn_radial(n: int, scale: float, rng, rough: float = 1.0, wobble: float = 1.0) -> np.ndarray:
    """Yırtık kenar: düşük frekanslı dalga + orta frekans çentik + lif pürüzü + tek tük koparılmış diş."""
    r = _noise1d(n, rng, [(0.018 * scale * wobble, 2, 5, 4), (0.006 * scale * wobble, 7, 40, 8),
                          (0.0022 * scale * rough, 80, 260, 10)])
    r += rng.normal(0, 0.0011 * scale * rough, n)
    jumps = rng.random(n) < 0.004
    r += np.convolve(jumps * rng.uniform(-0.01, 0.006, n) * scale, np.ones(9) / 3, mode="same")
    return r


def _poly(size, pts, blur: float = 0.0) -> np.ndarray:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(m, np.float32) / 255


def _grain(shape, rng, sigma: float, fine: float = 1.0, coarse: float = 0.5) -> np.ndarray:
    a = rng.normal(0, 1, shape)
    b = np.asarray(Image.fromarray((rng.normal(0, 1, shape) * 40 + 128).clip(0, 255).astype(np.uint8))
                   .filter(ImageFilter.GaussianBlur(1.6)), np.float32)
    return sigma * (fine * a + coarse * (b - 128) / 40 * 2.2)


def _lowfreq(shape, rng, cell: int) -> np.ndarray:
    h, w = shape
    z = rng.normal(128, 40, (h // cell + 1, w // cell + 1)).clip(0, 255).astype(np.uint8)
    return (np.asarray(Image.fromarray(z).resize((w, h), Image.Resampling.BICUBIC), np.float32) - 128) / 40


def film(img: Image.Image, w_px: int, f: dict, rng) -> tuple[Image.Image, np.ndarray]:
    """Fotoğrafı analog baskıya çevirir: gri ton, soldurma, iri gren, leke, toz, kıl/çizik, hafif yumuşama.
    Dönen: (işlenmiş gri görüntü, işlenmemiş gri dizi — figür anahtarlaması için)."""
    g = img.convert("L")
    th = round(g.height * w_px / g.width)
    g = g.resize((w_px, th), Image.Resampling.LANCZOS)
    L0 = np.asarray(g, np.float32)
    lo, hi = f["fade"]
    L = lo + (L0 / 255.0) ** f["gamma"] * (hi - lo)
    L += _grain(L.shape, rng, f["grain"])
    L += _lowfreq(L.shape, rng, 40) * f["blotch"]
    out = Image.fromarray(L.clip(0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(out)
    for _ in range(f["dust"]):
        x, y = rng.uniform(0, w_px), rng.uniform(0, th)
        r = float(rng.choice([0.8, 1.2, 1.8, 2.6], p=[0.5, 0.3, 0.15, 0.05]))
        dr.ellipse([x - r, y - r, x + r, y + r], fill=int(rng.choice([235, 30])) if rng.random() < 0.8 else 250)
    for _ in range(f["hairs"]):
        x, y = rng.uniform(0, w_px), rng.uniform(0, th)
        pts = [(x, y)]
        for _ in range(6):
            x += rng.normal(0, 7)
            y += rng.normal(0, 7)
            pts.append((x, y))
        dr.line(pts, fill=int(rng.choice([240, 40])), width=1)
    return out.filter(ImageFilter.GaussianBlur(f["soft"])), L0


def torn_piece(photo: Image.Image, L0: np.ndarray, pp: dict, cut: dict, rng) -> tuple[np.ndarray, np.ndarray]:
    """Yırtık kâğıt kesim: fotoğraf + kenarda beyaz lifli kâğıt çekirdeği; figür kesimin üstünden taşar.
    Dönen: (gri değerler, saydamlık) — ikisi de fotoğraf ölçüsünde."""
    w, h = photo.size
    top, bot = pp["top_frac"] * h, pp["bottom_frac"] * h
    left, right = pp["left_frac"] * w, pp["right_frac"] * w
    cx, cy, a, b = (left + right) / 2, (top + bot) / 2, (right - left) / 2, (bot - top) / 2
    n = 2400
    scale = min(w, h)
    rad = _torn_radial(n, scale, rng, pp["rough"], pp["wobble"])
    mask = _poly((w, h), _superellipse(cx, cy, a, b, pp["squareness"], n, rad))
    rim_r = rad + np.clip(6 + _noise1d(n, rng, [(4, 20, 90, 6), (2, 150, 400, 6)]) + rng.normal(0, 1.3, n), 2, 14)
    rim = _poly((w, h), _superellipse(cx, cy, a, b, pp["squareness"], n, rim_r))
    fig_a = np.zeros((h, w), np.float32)
    if cut.get("overflow") and cut.get("mask") is not None:
        m = Image.fromarray(cut["mask"].astype(np.uint8) * 255).resize((w, h), Image.Resampling.BILINEAR)
        region = np.asarray(m.filter(ImageFilter.MaxFilter(5)), np.float32) / 255 > 0.25
        Lb = np.asarray(Image.fromarray(L0.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)),
                        np.float32)
        sky = cut["sky"]
        t0 = max(cut["noise"] * 1.2, 4.0)
        soft = np.clip((np.abs(Lb - sky) - t0) / 22.0, 0, 1)
        fig_a = np.where(region, soft, 0).astype(np.float32)
        fig_a[int(top + 0.05 * h):, :] = 0         # kesimin altında figür zaten fotoğrafın içinde
        fig_a = np.asarray(Image.fromarray((fig_a * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6)),
                           np.float32) / 255
    p = np.asarray(photo, np.float32)
    paper = 244 + rng.normal(0, 4, p.shape)
    grey = np.where(mask > 0.5, p, np.where(fig_a > 0, p, paper))
    return grey, np.maximum(np.maximum(mask, fig_a), rim)


def _blob(size, spec: dict, rng) -> tuple[np.ndarray, np.ndarray]:
    W, H = size
    cx, cy, a, b = px(spec["cx"]), px(spec["cy"]), spec["rx"] * MM, spec["ry"] * MM
    n = 1600
    s = min(a, b)
    if spec["kind"] == "strip":
        rad = _torn_radial(n, spec.get("tear", 900.0), rng, rough=1.6, wobble=1.4)
        pts = _superellipse(0, 0, a, b, spec["e"], n, rad)
    else:
        o = spec.get("organic", 1.0)
        rad = _noise1d(n, rng, [(0.10 * s * o, 2, 3, 3), (0.025 * s * o, 4, 9, 4), (0.004 * s, 30, 90, 6)])
        rad += rng.normal(0, 0.0012 * s, n)
        pts = _superellipse(0, 0, a, b, spec["e"], n, rad)
    ang = math.radians(spec["rot"])
    pts = [(cx + x * math.cos(ang) - y * math.sin(ang), cy + x * math.sin(ang) + y * math.cos(ang)) for x, y in pts]
    m = _poly(size, pts, blur=0.7)
    g = spec["grey"] + _grain((H, W), rng, 7.0, fine=0.9, coarse=0.8) + _lowfreq((H, W), rng, 60) * 5
    return g.clip(0, 255), m * spec.get("opacity", 1.0)


def _label_png(w_mm: float, h_mm: float, wear_amt: float, rng, path: Path, wear_path: Path) -> float:
    """Daktilo etiketi kâğıdı (gölgeli, pürüzlü kenar) ve aşınma katmanı (yazının üstüne basılan kâğıt benekleri).
    Dönen: kenar payı (mm)."""
    pad = 24
    w, h = px(w_mm), px(h_mm)
    W, H = w + 2 * pad, h + 2 * pad
    n = 900
    rad = _noise1d(n, rng, [(1.2, 3, 8, 3), (0.6, 30, 90, 5)]) + rng.normal(0, 0.35, n)
    m = _poly((W, H), _superellipse(W / 2, H / 2, w / 2, h / 2, 14, n, rad), blur=0.5)
    sh = Image.new("L", (W, H), 0)
    sh.paste(Image.fromarray((m * 255).astype(np.uint8)), (4, 7))
    shadow = np.asarray(sh.filter(ImageFilter.GaussianBlur(7)), np.float32) / 255 * 0.34
    paper = 246 + _grain((H, W), rng, 3.2, fine=1.0, coarse=0.6)
    tint = np.stack([paper, paper - 1.5, paper - 5], -1)
    ma = m[..., None]
    rgb = tint * ma + np.array([40, 38, 36]) * (1 - ma)
    alpha = np.maximum(m, shadow)
    Image.fromarray(np.dstack([rgb.clip(0, 255), alpha[..., None] * 255]).astype(np.uint8), "RGBA").save(path)
    f = rng.normal(0, 1, (H, W))
    f = np.asarray(Image.fromarray((f * 50 + 128).clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.3)),
                   np.float32)
    thr = np.percentile(f, 100 - wear_amt)
    wa = np.clip((f - thr) / 6, 0, 1) * m
    wear = np.dstack([np.full((H, W), 244), np.full((H, W), 242), np.full((H, W), 238), wa * 255]).astype(np.uint8)
    Image.fromarray(wear, "RGBA").save(wear_path)
    return pad / MM


def render(out: Path, photo: Image.Image, lay: dict, cut: dict, labels: dict) -> dict:
    """Ön kapak katmanları: `out/kolaj-on.png` (gri, 300 dpi, taşma paylı ön panel), etiket kâğıtları ve aşınmaları.
    Dönen: cover.typ'in `front_collage` verisi (yazılar vektör basılır)."""
    rng = np.random.default_rng(lay["seed"] + 1)
    out.mkdir(parents=True, exist_ok=True)
    W, H = px(lay["panel"][0]), px(lay["panel"][1])
    pp = lay["photo"]
    img, L0 = film(photo, px(pp["w"]), lay["film"], rng)
    grey, alpha = torn_piece(img, L0, pp, cut, rng)
    base = np.full((H, W), 255.0)
    for b in lay["blobs"]:
        if not b["front"]:
            g, m = _blob((W, H), b, rng)
            base = base * (1 - m) + g * m
    ox, oy = px(pp["x"]), px(pp["y"])
    ph, pw = alpha.shape
    # yumuşak gölge, sonra kesim (panelin dışına düşen kısım kırpılır)
    sh = Image.new("L", (W, H), 0)
    sh.paste(Image.fromarray((alpha * 255).astype(np.uint8)), (ox + 5, oy + 8))
    shadow = np.asarray(sh.filter(ImageFilter.GaussianBlur(9)), np.float32) / 255 * 0.22
    base = base * (1 - shadow) + 60 * shadow
    y1, y2, x1, x2 = max(0, oy), min(H, oy + ph), max(0, ox), min(W, ox + pw)
    if y2 > y1 and x2 > x1:
        a = alpha[y1 - oy:y2 - oy, x1 - ox:x2 - ox]
        base[y1:y2, x1:x2] = base[y1:y2, x1:x2] * (1 - a) + grey[y1 - oy:y2 - oy, x1 - ox:x2 - ox] * a
    for b in lay["blobs"]:
        if b["front"]:
            g, m = _blob((W, H), b, rng)
            base = base * (1 - m) + g * m
    Image.fromarray(base.clip(0, 255).astype(np.uint8), "L").save(out / "kolaj-on.png", dpi=(DPI, DPI))
    labs = []
    for i, lb in enumerate(lay["labels"], 1):
        pad = _label_png(lb["w"], lb["h"], lb["wear"], rng, out / f"kolaj-etiket-{i}.png", out / f"kolaj-asinma-{i}.png")
        labs.append({"text": lb["text"], "size_pt": labels["size_pt"], "cx_mm": lb["cx"], "cy_mm": lb["cy"],
                     "rot": lb["rot"], "w_mm": lb["w"], "h_mm": lb["h"], "pad_mm": round(pad, 3),
                     "img": f"kolaj-etiket-{i}.png", "wear_img": f"kolaj-asinma-{i}.png", "ink": INK, "stroke_pt": 0.4,
                     "tracking_pt": TRACKING_PT})
    a = lay["author"]
    return {"art": "kolaj-on.png", "font": labels["font"], "labels": labs,
            "author": {**{k: a[k] for k in ("text", "size_pt", "tracking_pt")}, "y_mm": a["y"], "ink": AUTHOR_INK,
                       "font": THIN[0], "weight": THIN[2]} if a else None,
            "fonts": str(FONT_DIR)}


def compose(out: Path, photo_path: Path, title: str, author: str, trim_w: float, trim_h: float, bleed: float,
            safe: float, layout_n: int = 0, lines: list[str] | None = None) -> tuple[dict, dict]:
    """Fotoğraf + kitap bilgisi → ön kapak katmanları. Dönen: (cover.typ verisi, düzen ayrıntısı)."""
    photo = fit_aspect(Image.open(photo_path).convert("RGB"))
    cut = figure_cut(photo)
    labels = label_lines(title, trim_w, lines)
    seed = seed_for(title, layout_n)
    lay = layout(seed, trim_w, trim_h, bleed, safe, photo.width / photo.height, cut, labels, author)
    data = render(out, photo, lay, cut, labels)
    return data, {"layout": lay, "cut": _public_cut(cut), "labels": {k: labels[k] for k in ("lines", "size_pt", "font")}}


# ------------------------------------------------------------------ kapak (studio.build_cover kancası)
def build_cover(d: Path) -> bool:
    """Kapak tarzı seçildiyse kapağı kurar ve True döner: kolaj (seçili fotoğraf varsa) ya da tipografik (resim olsa
    da). Seçim yoksa, «resimli» seçildiyse ya da kolajın fotoğrafı henüz yoksa False: bugünkü yol sürer."""
    from . import cover as cover_mod
    from . import preflight, studio
    st = load(d)
    style = st.get("style")
    if style == "typographic":
        ms, spec, plan = studio._manuscript(d), studio._spec(d), studio._plan(d)
        cpdf, info = cover_mod.build(ms, studio._profile(d), spec, studio.page_count(d), None, plan.style.accent,
                                     studio._back_bg(plan.style.palette), d / "kapak", studio.fonts(),
                                     front_bg=studio._cover_bg(d, plan.style))
        preflight.set_boxes(cpdf, spec.bleed)
        studio.write(d, "cover.json", {**info, "style": "typographic"})
        return True
    ph = selected(st) if style == "collage" else None
    if ph is None:
        return False
    ms, spec = studio._manuscript(d), studio._spec(d)
    t = time.time()
    front, info_c = compose(d / "kapak", d / ph["path"], ms.title, ms.author or "", spec.trim_w, spec.trim_h,
                            spec.bleed, spec.safe, int(st.get("layout") or 0), st.get("labels"))
    cpdf, info = cover_mod.build(ms, studio._profile(d), spec, studio.page_count(d), None, SPINE, BACK_BG,
                                 d / "kapak", studio.fonts(), collage=front)
    preflight.set_boxes(cpdf, spec.bleed)
    studio.write(d, "cover.json", {**info, "style": "collage", "photo": ph["id"], "source": ph["source"],
                                   "draft": ph["source"] == "model", "seconds": round(time.time() - t, 1),
                                   "cut": info_c["cut"], "labels": info_c["labels"]})
    return True


def apply(d: Path) -> None:
    """Seçim değişince kapak ve ön kontrol yenilenir (iç sayfa dizgisi değişmez)."""
    from . import studio
    with locked(d):
        studio.build_cover(d)
    if (d / "dizgi" / "ic-sayfalar.pdf").exists():
        studio.refresh_preflight(d)


# ------------------------------------------------------------------ editör işlemleri
def set_style(d: Path, style: str, by: str) -> dict:
    if style not in STYLES:
        raise ValueError("Kapak tarzı resimli, kolaj ya da tipografik olmalı")
    with locked(d):
        st = load(d)
        st["style"] = style
        save(d, st, by)
    _log(d, "style", by, style=style)
    apply(d)
    return load(d)


def select(d: Path, pid: str, by: str) -> dict:
    with locked(d):
        st = load(d)
        if not any(p["id"] == pid for p in st["photos"]):
            raise KeyError(f"fotoğraf yok: {pid}")
        st["selected"] = pid
        save(d, st, by)
    _log(d, "select", by, photo=pid)
    apply(d)
    return load(d)


def set_layout(d: Path, n: int | None, by: str) -> dict:
    """«Başka düzen»: `n` None ise bir sonraki düzen; verilirse o düzen (geri dönmek için)."""
    with locked(d):
        st = load(d)
        st["layout"] = int(st.get("layout") or 0) + 1 if n is None else max(0, int(n))
        save(d, st, by)
    _log(d, "layout", by, layout=load(d)["layout"])
    apply(d)
    return load(d)


def set_labels(d: Path, lines: list[str] | None, by: str) -> dict:
    """Etiket şeritleri: liste (her satır bir şerit) ya da None (başlıktan otomatik). Sığmayan şerit açık hata."""
    from . import studio
    spec, ms = studio._spec(d), studio._manuscript(d)
    if lines is not None:
        label_lines(ms.title, spec.trim_w, lines)         # doğrulama: sığmıyorsa ValueError
        lines = [" ".join(str(x).split()) for x in lines]
    with locked(d):
        st = load(d)
        st["labels"] = lines
        save(d, st, by)
    _log(d, "labels", by, labels=lines)
    apply(d)
    return load(d)


def _new_id() -> str:
    return f"k_{secrets.token_hex(4)}"


def _analyse(path: Path) -> dict:
    return _public_cut(figure_cut(fit_aspect(Image.open(path).convert("RGB"))))


def add_upload(d: Path, data: bytes, filename: str, by: str) -> dict:
    """Editörün fotoğrafı (fotoğraf yükleme yolu: EXIF yönü, sRGB, üst veri silinir); aday olur ve seçilir."""
    from . import photo as photo_mod
    info = photo_mod.ingest(data, filename)
    pid = _new_id()
    rel = f"{DIR}/foto/{pid}.{info['ext']}"
    (d / rel).parent.mkdir(parents=True, exist_ok=True)
    (d / rel).write_bytes(info["bytes"])
    rec = {"id": pid, "source": "editor", "path": rel, "w_px": info["w_px"], "h_px": info["h_px"],
           "name": Path(filename).name[:120], "by": by, "at": time.time(), "cut": _analyse(d / rel)}
    with locked(d):
        st = load(d)
        st["photos"].append(rec)
        st["selected"] = pid
        save(d, st, by)
    _log(d, "upload", by, photo=pid)
    if st.get("style") == "collage":
        apply(d)
    return rec


async def scene(d: Path, direction: str, llm) -> dict:
    """Fotoğrafın konusu: dil modeli kitabın profilinden, tanıtımından ve metninden genel kalıbı doldurur."""
    from . import studio
    from ..prompts import render as render_prompt
    from .art import _age
    ms, p = studio._manuscript(d), studio._profile(d)
    ap = studio.read(d, "artplan.json") or {}
    chars = "; ".join(f"{c['name']} ({c.get('species', '')})" for c in ap.get("characters", [])) or "(yok)"
    excerpt = "\n\n".join(b.text for b in ms.chapters[0].blocks)[:3000] if ms.chapters else ""
    ref, prompt = render_prompt("production_collage_scene", title=ms.title, age=_age(p), genre=p.genre,
                                tone=", ".join(p.tone), characters=chars,
                                summary=ms.meta.get("CRM_SUMMARY") or "(yok)", excerpt=excerpt or "(yok)",
                                direction=direction.strip() or "(yok)")
    out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref, schema=SCENE_SCHEMA,
                            max_tokens=800, thinking=False, temperature=0.5)
    out = {k: " ".join(str(out[k]).split()) for k in SCENE_SCHEMA["required"]}
    out["era"] = out["era"] or "timeless"
    return out


def photo_prompt(sc: dict) -> str:
    return PHOTO_FRAME.format(**{k: sc[k].rstrip(".") + ("" if k == "era" else ".") for k in
                                 ("era", "subject", "gesture", "setting")})


def photo_size(trim_w: float) -> tuple[float, float]:
    """Model fotoğrafının basılı ölçüsü (mm): kesimin %90'ı genişlik, 4:5 dik (düzen en çok %86 kullanır)."""
    w = trim_w * 0.9
    return w, w / GEN_ASPECT


async def generate(d: Path, count: int, direction: str, by: str, painter=None, llm=None) -> list[str]:
    """GPU işi: sahne istemi (dil modeli) → `count` tohumla fotoğraf (görsel model) → 300 dpi'ye büyütme. Her aday
    bitince kaydedilir (işçi düşerse biten adaylar kalır). İlk aday, seçili fotoğraf yoksa seçilir; kapak kolaj
    tarzındaysa yeniden kurulur. Dönen: yeni aday kimlikleri."""
    from . import studio
    from .images import Painter, size_for, target_px

    class _CollagePainter(Painter):
        @property
        def negative(self) -> str:                  # kolaja özel negatif istem
            return NEGATIVE

    ms, spec = studio._manuscript(d), studio._spec(d)
    if llm is None:
        from .run import FileLlm
        llm = FileLlm(d / "provenance.jsonl")
    sc = await scene(d, direction, llm)
    prompt = photo_prompt(sc)
    with locked(d):
        st = load(d)
        st["scene"] = {**sc, "prompt_en": prompt, "negative": NEGATIVE, "direction": direction, "at": time.time()}
        base = seed_for(ms.title, 0) % (2**31 - 1)
        k0 = sum(1 for p in st["photos"] if p["source"] == "model")
        save(d, st)
    w_mm, h_mm = photo_size(spec.trim_w)
    W, H, gen_dpi = size_for(w_mm, h_mm)
    TW, TH = target_px(w_mm, h_mm)
    own = painter is None
    painter = painter or _CollagePainter(d, None)
    made = []
    try:
        for i in range(count):
            seed = (base + 7919 * (k0 + i + 1)) % (2**31 - 1) or 1
            t = time.time()
            png = await painter._generate(prompt, W, H, seed)
            gen_s = round(time.time() - t, 1)
            png, how = await painter.enlarge(png, TW, TH)
            pid = _new_id()
            rel = f"{DIR}/foto/{pid}.png"
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            Image.open(io.BytesIO(png)).convert("L").save(d / rel, "PNG", dpi=(DPI, DPI))
            rec = {"id": pid, "source": "model", "path": rel, "w_px": TW, "h_px": TH, "gen_px": [W, H],
                   "gen_dpi": gen_dpi, "seed": seed, "by": by, "at": time.time(), "seconds": gen_s,
                   "enlarge_seconds": round(time.time() - t - gen_s, 1), "note": how, "cut": _analyse(d / rel)}
            with locked(d):
                st = load(d)
                st["photos"].append(rec)
                if not st.get("selected"):
                    st["selected"] = pid
                if st.get("job"):
                    st["job"] = {**st["job"], "done": i + 1}
                save(d, st)
            made.append(pid)
            _log(d, "photo", by, photo=pid, seed=seed, seconds=gen_s)
    finally:
        if own:
            await painter.close()
    if load(d).get("style") == "collage":
        import asyncio
        await asyncio.to_thread(apply, d)
    return made


def set_job(d: Path, **info) -> None:
    with locked(d):
        st = load(d)
        st["job"] = {**(st.get("job") or {}), **info}
        save(d, st)


# ------------------------------------------------------------------ ekran görünümü
def view(d: Path) -> dict:
    from . import studio
    st = load(d)
    ms, spec = studio._manuscript(d), studio._spec(d)
    try:
        auto = label_lines(ms.title, spec.trim_w)
        auto_err = None
    except ValueError as e:
        auto, auto_err = None, str(e)
    try:
        eff = label_lines(ms.title, spec.trim_w, st.get("labels")) if st.get("labels") else auto
    except ValueError:
        eff = auto
    ph = selected(st)
    cov = studio.read(d, "cover.json") or {}
    pdf = d / "kapak" / "kapak.pdf"
    return {
        "style": st.get("style"),
        "effective_style": cov.get("style") or ((("typographic" if cov.get("typographic") else "illustrated"))
                                                if cov else None),
        "layout": int(st.get("layout") or 0),
        "photos": [{k: p.get(k) for k in ("id", "source", "w_px", "h_px", "name", "by", "at", "seed", "note")}
                   | {"overflow": bool((p.get("cut") or {}).get("overflow")),
                      "cut_note": (p.get("cut") or {}).get("note"), "draft": p["source"] == "model"}
                   for p in st["photos"]],
        "selected": st.get("selected"),
        "draft": bool(ph and ph["source"] == "model"),
        "labels": st.get("labels"),
        "auto_labels": auto and auto["lines"],
        "auto_labels_error": auto_err,
        "label_lines": eff and eff["lines"],
        "label_size_pt": eff and eff["size_pt"],
        "scene": st.get("scene") and {k: st["scene"].get(k) for k in ("why", "direction", "at")},
        "job": st.get("job"),
        "cover_art": "kapak" in studio.selected_art(d),
        "built": pdf.stat().st_mtime if pdf.exists() else 0,
        "updated_at": st.get("updated_at"),
    }


def front_preview(d: Path, width: int) -> Path:
    """Kapak açılımından yalnız ön panel (taşma paylı), istenen genişlikte PNG; kapak değişince yenilenir."""
    import pymupdf

    from . import studio
    pdf = d / "kapak" / "kapak.pdf"
    if not pdf.exists():
        raise FileNotFoundError("kapak henüz kurulmadı")
    out = d / "kapak" / f"on-onizleme-{width}.png"
    if out.exists() and out.stat().st_mtime >= pdf.stat().st_mtime:
        return out
    spec = studio._spec(d)
    page = pymupdf.open(pdf)[0]
    pt = 72 / 25.4
    x0 = page.rect.width - (spec.trim_w + spec.bleed) * pt
    clip = pymupdf.Rect(x0, 0, page.rect.width, page.rect.height)
    zoom = width / clip.width
    page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip).save(out)
    return out
