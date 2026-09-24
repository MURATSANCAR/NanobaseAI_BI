"""Kapak yazısı katmanı: başlık, alt başlık ve yazar adı görsel modelden değil fonttan basılır.

Sebep (ölçüldü 2026-09-24, Qwen-Image-2.1, okunmuş 4 kitap): model kapak yazısını 4 kapağın
2'sinde yanlış harfle bastı — «Sarıoğlu» → «Sarıöglu», «İBN SÎNÂ» → «ÎBN SÎNĂ». Kapaktaki ad
hatasız olmak zorunda; fontla basılan yazı tanım gereği doğrudur. Görsel model yalnız yazısız
resmi üretir (`COVER_PROMPT_SUFFIX` üst bandı ve alt şeridi boş bırakmasını ister), yazı burada
eklenir.

Kitaptan bağımsızdır: yazı biçimi yaş/tür bilgisinden (`style_for`), punto ve satır bölme
alandan, renk ve gerekirse arka perde kapak resminin o bölgesindeki ışıktan hesaplanır. Fontta
bulunmayan harf varsa (ör. â î û) yedek fonta geçilir; hiçbir fontta yoksa hata verilir, yazı
eksik basılmaz.

Fontlar (OFL) imajda /app/data/fonts altında (images/py/Dockerfile, google/fonts sabit sürüm).

    python -m editor.cover_text girdi.png cikti.png --title "Gölge Tilki" --author "Carlie Sorosiak" \
        [--subtitle ...] [--style cocuk|edebiyat|klasik] [--age-max 12] [--genre "roman"]
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(os.environ.get("EDITOR_FONT_DIR", "/app/data/fonts"))

# Görsel modele eklenen istem: yazı alanlarını boş bıraksın, hiçbir yere yazı koymasın.
COVER_PROMPT_SUFFIX = (
    " Composition for a book cover: keep the top third of the image as calm, uncluttered background "
    "(sky, wall, paper or soft texture) with no objects, and keep a thin quiet band along the bottom edge. "
    "Absolutely no text, letters, words, numbers, logos or signatures anywhere in the image.")
COVER_NEGATIVE = "text, letters, words, typography, title, caption, signature, watermark, logo"


@dataclass(frozen=True)
class Face:
    file: str
    weight: int


@dataclass(frozen=True)
class Style:
    title: Face
    author: Face
    subtitle: Face
    upper: bool          # başlık büyük harfle (Türkçe kuralla)
    leading: float       # satır aralığı, punto katı


FALLBACK = Face("NotoSerif[wdth,wght].ttf", 600)
STYLES = {
    "cocuk": Style(Face("Baloo2[wght].ttf", 800), Face("Baloo2[wght].ttf", 600),
                   Face("Baloo2[wght].ttf", 600), upper=True, leading=1.0),
    "edebiyat": Style(Face("PlayfairDisplay[wght].ttf", 600), Face("PlayfairDisplay[wght].ttf", 400),
                      Face("PlayfairDisplay[wght].ttf", 500), upper=True, leading=1.08),
    "klasik": Style(Face("CormorantGaramond[wght].ttf", 700), Face("CormorantGaramond[wght].ttf", 600),
                    Face("CormorantGaramond[wght].ttf", 600), upper=True, leading=1.05),
}
_KLASIK = re.compile(r"tarih|din|tasavvuf|biyografi|felsefe|siyer|ilahiyat|klasik|ahlak|araştırma|inceleme",
                     re.I)

# Bölgeler (kapak yüksekliğine oran). Başlık üst bantta, yazar alt şeritte.
TITLE_BAND = (0.05, 0.33)
AUTHOR_BAND = (0.885, 0.955)
SIDE_MARGIN = 0.09


def style_for(age_max: int | None = None, genre: str | None = None) -> str:
    """Yaş üst sınırı 12 ve altı → çocuk; tür metni tarih/din/biyografi… → klasik; kalan → edebiyat.
    Kaynak: kitap kartı yaş aralığı, CRM new_hedefkitle / new_turlertext."""
    if age_max is not None and age_max <= 12:
        return "cocuk"
    if genre and _KLASIK.search(genre):
        return "klasik"
    return "edebiyat"


def tr_upper(s: str) -> str:
    """Türkçe büyük harf: i → İ, ı → I (str.upper() i'yi I yapar)."""
    return s.replace("i", "İ").replace("ı", "I").upper()


@lru_cache(maxsize=None)
def _cmap(file: str) -> frozenset[int]:
    from fontTools.ttLib import TTFont
    return frozenset(TTFont(str(FONT_DIR / file), lazy=True).getBestCmap())


def covers(face: Face, text: str) -> bool:
    cmap = _cmap(face.file)
    return all(ord(ch) in cmap for ch in text if not ch.isspace())


def _usable(face: Face, text: str) -> Face:
    for f in (face, FALLBACK):
        if covers(f, text):
            return f
    missing = sorted({ch for ch in text if not ch.isspace() and ord(ch) not in _cmap(FALLBACK.file)})
    raise ValueError(f"fontlarda olmayan harf: {''.join(missing)!r}")


@lru_cache(maxsize=256)
def _font(face: Face, size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_DIR / face.file), size)
    try:
        axes = f.get_variation_axes()
    except OSError:                       # sabit (değişken olmayan) font
        return f
    f.set_variation_by_axes([
        max(a["minimum"], min(a["maximum"], face.weight)) if (a.get("name") or b"").lower() in (b"weight", "weight")
        else a["default"] for a in axes])
    return f


def _width(font: ImageFont.FreeTypeFont, text: str) -> int:
    l, _, r, _ = font.getbbox(text)
    return r - l


def _splits(words: list[str], n: int):
    for cut in combinations(range(1, len(words)), n - 1):
        idx = (0, *cut, len(words))
        yield [" ".join(words[idx[i]:idx[i + 1]]) for i in range(n)]


def fit(text: str, face: Face, box_w: int, box_h: int, leading: float,
        max_lines: int = 3, max_size: int | None = None, min_size: int = 12) -> tuple[int, list[str]]:
    """Kutuya sığan en büyük punto ve dengeli satır bölmesi (en uzun satırı en kısa olan)."""
    words = text.split()
    size = max_size or box_h
    while size >= min_size:
        font = _font(face, size)
        best = None
        for n in range(1, min(max_lines, len(words)) + 1):
            if n * size * leading > box_h:
                break
            for lines in _splits(words, n):
                w = max(_width(font, ln) for ln in lines)
                if w <= box_w and (best is None or w < best[0]):
                    best = (w, lines)
            if best:
                return size, best[1]
        size = int(size * 0.94)
    raise ValueError(f"yazı alana sığmıyor: {text!r}")


def _lum(rgb) -> float:
    def ch(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb[:3]
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a: float, b: float) -> float:
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


DARK, LIGHT = (28, 24, 20), (251, 247, 238)


def _ink(region: Image.Image) -> tuple[tuple[int, int, int], float, bool]:
    """Bölgeye göre yazı rengi. Bölgenin en kötü %10'luk kısmına karşı kontrast 3'ün altındaysa
    yazının arkasına yumuşak perde gerekir (dönen bool)."""
    small = region.convert("RGB").resize((64, max(1, 64 * region.height // max(1, region.width))))
    pixels = small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()
    lums = sorted(_lum(p) for p in pixels)
    mean = sum(lums) / len(lums)
    ink = DARK if mean > 0.28 else LIGHT
    ink_l = _lum(ink)
    # koyu yazıya en kötü zemin bölgenin en koyu onda biri, açık yazıya en açık onda biri
    worst = lums[int(len(lums) * 0.1)] if ink == DARK else lums[int(len(lums) * 0.9)]
    c = _contrast(ink_l, worst)
    return ink, round(c, 2), c < 3.0


def _scrim(img: Image.Image, box: tuple[int, int, int, int], ink) -> None:
    """Yazının arkasına kenarları yumuşak, yarı saydam perde (yazı açık renkse koyu, koyu ise açık)."""
    x0, y0, x1, y1 = box
    pad = int((y1 - y0) * 0.35)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rectangle((x0 - pad, y0 - pad, x1 + pad, y1 + pad), fill=150)
    mask = mask.filter(ImageFilter.GaussianBlur(pad))
    tone = Image.new("RGB", img.size, DARK if ink == LIGHT else LIGHT)
    img.paste(tone, (0, 0), mask)


def _draw_block(img: Image.Image, lines: list[str], face: Face, size: int, leading: float,
                top: int, ink, shadow: bool, draw: bool = True) -> tuple[int, int, int, int]:
    font = _font(face, size)
    d = ImageDraw.Draw(img)
    W = img.width
    y = top
    boxes = []
    for ln in lines:
        l, t, r, b = font.getbbox(ln)
        x = (W - (r - l)) // 2 - l
        if shadow and draw:
            sh = Image.new("L", img.size, 0)
            ImageDraw.Draw(sh).text((x, y + max(1, size // 40)), ln, font=font, fill=120)
            sh = sh.filter(ImageFilter.GaussianBlur(max(1, size // 30)))
            img.paste(Image.new("RGB", img.size, (0, 0, 0)), (0, 0), sh)
        if draw:
            d.text((x, y), ln, font=font, fill=ink)
        boxes.append((x + l, y + t, x + r, y + b))
        y += int(size * leading)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def compose(img: Image.Image, title: str, author: str, subtitle: str | None = None,
            style: str = "edebiyat", draw_text: bool = True) -> tuple[Image.Image, dict]:
    """Yazısız kapak resmine başlık/alt başlık/yazar basar. Dönen rapor: font, punto, satırlar,
    renk, kontrast, perde kullanıldı mı."""
    st = STYLES[style]
    out = img.convert("RGB").copy()
    W, H = out.size
    box_w = int(W * (1 - 2 * SIDE_MARGIN))
    report: dict = {"style": style, "size": [W, H]}

    t_text = tr_upper(title) if st.upper else title
    t_face = _usable(st.title, t_text)
    ty0, ty1 = int(H * TITLE_BAND[0]), int(H * TITLE_BAND[1])
    band_h = ty1 - ty0
    s_text = s_face = None
    if subtitle:
        s_text = tr_upper(subtitle) if st.upper else subtitle
        s_face = _usable(st.subtitle, s_text)
    title_h = int(band_h * (0.74 if subtitle else 1.0))
    t_size, t_lines = fit(t_text, t_face, box_w, title_h, st.leading, max_size=int(W * 0.16))
    s_size = s_lines = None
    if subtitle:
        s_size, s_lines = fit(s_text, s_face, box_w, band_h - title_h, 1.1, max_lines=2,
                              max_size=max(12, int(t_size * 0.36)))

    a_face = _usable(st.author, author)
    ay0, ay1 = int(H * AUTHOR_BAND[0]), int(H * AUTHOR_BAND[1])
    a_size, a_lines = fit(author, a_face, box_w, ay1 - ay0, 1.1, max_lines=1,
                          max_size=max(14, int(t_size * 0.42)))

    # Blok yüksekliği → üst bantta dikey ortalama.
    block_h = len(t_lines) * int(t_size * st.leading)
    if subtitle:
        block_h += int(t_size * 0.25) + len(s_lines) * int(s_size * 1.1)
    top = ty0 + max(0, (band_h - block_h) // 2)

    for key, (y0, y1) in {"title": (top, top + block_h), "author": (ay0, ay1)}.items():
        ink, c, need = _ink(out.crop((int(W * SIDE_MARGIN), y0, W - int(W * SIDE_MARGIN), y1)))
        report[key] = {"ink": ink, "contrast": c, "scrim": need}
        if need:
            _scrim(out, (int(W * SIDE_MARGIN), y0, W - int(W * SIDE_MARGIN), y1), ink)

    ink = report["title"]["ink"]
    tb = _draw_block(out, t_lines, t_face, t_size, st.leading, top, ink, shadow=ink == LIGHT, draw=draw_text)
    report["title"].update(font=t_face.file, size=t_size, lines=t_lines, box=tb)
    if subtitle:
        sy = top + len(t_lines) * int(t_size * st.leading) + int(t_size * 0.25)
        sb = _draw_block(out, s_lines, s_face, s_size, 1.1, sy, ink, shadow=ink == LIGHT, draw=draw_text)
        report["subtitle"] = {"font": s_face.file, "size": s_size, "lines": s_lines, "box": sb}
    a_ink = report["author"]["ink"]
    ab = _draw_block(out, a_lines, a_face, a_size, 1.1, ay0 + ((ay1 - ay0) - a_size) // 2, a_ink,
                     shadow=a_ink == LIGHT, draw=draw_text)
    report["author"].update(font=a_face.file, size=a_size, lines=a_lines, box=ab)
    return out, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", required=True)
    ap.add_argument("--subtitle")
    ap.add_argument("--style", choices=sorted(STYLES))
    ap.add_argument("--age-max", type=int)
    ap.add_argument("--genre")
    a = ap.parse_args()
    style = a.style or style_for(a.age_max, a.genre)
    out, rep = compose(Image.open(a.src), a.title, a.author, a.subtitle, style)
    out.save(a.dst)
    print(json.dumps(rep, ensure_ascii=False))


if __name__ == "__main__":
    main()
