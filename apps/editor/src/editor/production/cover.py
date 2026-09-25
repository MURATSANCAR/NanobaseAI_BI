"""Kapak açılımı: ön kapak resmi (yazısız üretilir), başlık/yazar vektör yazı, arka kapak yazısı
(CRM tanıtım metni), yaş bandı, dizi, ISBN barkodu, sırt (Amerikan ciltte).

Ön kapak yazısının yeri, puntosu ve rengi `cover_text` ile resmin kendisinden hesaplanır (perde
gerekiyorsa resme işlenir); yazı PDF'e vektör olarak basılır, harf hatası olmaz.

Resimsiz kitapta (art_mode=none, kapak resmi yok) ön kapak tipografiktir (`typographic`): paletten zemin, başlık
ve yazar başlık fontuyla, sade desen; arka kapak, barkod ve sırt aynı. Editör sonradan kapağa resim üretirse
resimli yola döner.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from .. import cover_text as ct
from . import barcode
from .manuscript import Manuscript
from .profile import Profile
from .spec import Spec

TEMPLATE = Path(__file__).resolve().parent / "templates" / "cover.typ"
PT_PER_MM = 72 / 25.4


def front_art_prompt(scene: str, style_prompt: str) -> str:
    return f"Children's book front cover illustration. {scene} Style: {style_prompt}." + ct.COVER_PROMPT_SUFFIX


def typographic(ms: Manuscript, spec: Spec, bg: str) -> dict:
    """Resimsiz kitabın ön kapağı (art_mode=none): paletten düz zemin, başlık ve yazar kitabın başlık fontuyla,
    zeminin bir ton açığında sade daire deseni. Desen başlıktan türeyen tohumla: aynı kitap hep aynı kapak.
    Yazı rengi zemine karşı okunur olan (beyaz ya da koyu mürekkep; WCAG ≥ 4.5)."""
    import hashlib
    import random
    from .palette import contrast
    rng = random.Random(int(hashlib.sha256(ms.title.encode()).hexdigest()[:8], 16))
    w, h = spec.trim_w + spec.bleed, spec.trim_h + 2 * spec.bleed
    # Daireler yazının bandına (yüksekliğin %20–%62'si) girmez: üstte ve altta, dönüşümlü.
    dots = []
    for i in range(7):
        r = rng.uniform(6, 24)
        y = rng.uniform(-r * 0.5, h * 0.20 - r) if i % 2 == 0 else rng.uniform(h * 0.62 + r, h + r * 0.5)
        dots.append([round(rng.uniform(0, w), 1), round(y, 1), round(r, 1)])
    n = len(ms.title)
    return {"bg": bg, "ink": "#FFFFFF" if contrast(bg) >= 4.5 else "#2C2C2A", "dots": dots,
            "title_size": round(max(24.0, min(44.0, 44.0 - (n - 12) * 0.8)), 1), "author_size": 15.0}


def build(ms: Manuscript, p: Profile, spec: Spec, pages: int, art_png: Path | None, accent: str, back_bg: str,
          workdir: Path, font_dir: Path, front_bg: str | None = None) -> tuple[Path, dict]:
    """`art_png` None → tipografik ön kapak (`front_bg` zemin; görsel model gerekmez)."""
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEMPLATE, workdir / "cover.typ")
    spine = spec.spine(pages)
    panel_w, panel_h = spec.trim_w + spec.bleed, spec.trim_h + 2 * spec.bleed
    if art_png is None:
        return _compile(ms, p, spec, workdir, font_dir, accent, back_bg, spine, pages, panel_h, None, [],
                        typographic(ms, spec, front_bg or accent), {"typographic": True})
    img = Image.open(art_png).convert("RGB")
    # resmi panel oranına kırp (ortadan)
    want = panel_w / panel_h
    w, h = img.size
    if w / h > want:
        nw = int(h * want)
        img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = int(w / want)
        img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    style = ct.style_for(p.age_max, ms.meta.get("GENRE"))
    scrimmed, rep = ct.compose(img, ms.title, ms.author or "", None, style, draw_text=False)
    front = workdir / "on-kapak.png"
    scrimmed.save(front)
    mm_per_px = panel_w / scrimmed.width
    st = ct.STYLES[style]
    blocks = []
    for key, leading in (("title", st.leading), ("author", 1.1)):
        r = rep[key]
        size_mm = r["size"] * mm_per_px
        blocks.append({"lines": r["lines"], "font": _family(r["font"]), "weight": _face(st, key).weight,
                       "size": round(size_mm * PT_PER_MM, 1), "top": round(r["box"][1] * mm_per_px, 2),
                       "step": round(r["size"] * leading * mm_per_px, 2), "ink": "#%02x%02x%02x" % tuple(r["ink"])})
    return _compile(ms, p, spec, workdir, font_dir, accent, back_bg, spine, pages, panel_h, front.name, blocks, None,
                    {"style": style, "text": rep, "typographic": False})


def _compile(ms, p, spec, workdir, font_dir, accent, back_bg, spine, pages, panel_h, front_image, blocks, typo,
             extra) -> tuple[Path, dict]:
    import typst
    code = None
    if ms.meta.get("ISBN"):
        (workdir / "barkod.svg").write_text(barcode.svg(ms.meta["ISBN"]))
        code = "barkod.svg"
    # Pazarlama kitinde onaylanıp «kapağa uygula» denen arka kapak yazısı varsa o; yoksa CRM tanıtım metni.
    from .marketing import applied_back_text
    summary = applied_back_text(workdir.parent) or ms.meta.get("CRM_SUMMARY") or ""
    data = {"bleed": spec.bleed, "trim_w": spec.trim_w, "trim_h": spec.trim_h, "spine": spine, "safe": spec.safe,
            "accent": accent, "body_font": spec.body_font, "heading_font": spec.heading_font,
            "title": ms.title, "author": ms.author or "", "publisher": ms.meta.get("PUBLISHER") or "",
            "front_image": front_image, "front_text": blocks, "front_type": typo, "barcode": code,
            "back": {"bg": back_bg, "paragraphs": [x.strip() for x in summary.split("\n") if x.strip()],
                     "age": f"{p.age_min}–{p.age_max} YAŞ" if p.age_min else None,
                     "series": ms.meta.get("SERIES")}}
    (workdir / "cover.json").write_text(json.dumps(data, ensure_ascii=False))
    out = workdir / "kapak.pdf"
    typst.compile(str(workdir / "cover.typ"), output=str(out), root=str(workdir), font_paths=[str(font_dir)],
                  ignore_system_fonts=True, sys_inputs={"data": "cover.json"})
    return out, {"spine_mm": spine, "binding": spec.binding(pages), **extra,
                 "size_mm": [round(2 * spec.trim_w + spine + 2 * spec.bleed, 1), panel_h]}


def _face(st: ct.Style, key: str) -> ct.Face:
    return {"title": st.title, "author": st.author}[key]


FAMILY = {"Baloo2[wght].ttf": "Baloo 2", "PlayfairDisplay[wght].ttf": "Playfair Display",
          "CormorantGaramond[wght].ttf": "Cormorant Garamond", "NotoSerif[wdth,wght].ttf": "Noto Serif"}


def _family(file: str) -> str:
    return FAMILY[file]
