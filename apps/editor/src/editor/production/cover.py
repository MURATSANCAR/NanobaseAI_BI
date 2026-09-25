"""Kapak açılımı: ön kapak resmi (yazısız üretilir), başlık/yazar vektör yazı, arka kapak yazısı
(CRM tanıtım metni), yaş bandı, dizi, ISBN barkodu, sırt (Amerikan ciltte).

Ön kapak yazısının yeri, puntosu ve rengi `cover_text` ile resmin kendisinden hesaplanır (perde
gerekiyorsa resme işlenir); yazı PDF'e vektör olarak basılır, harf hatası olmaz.
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


def build(ms: Manuscript, p: Profile, spec: Spec, pages: int, art_png: Path, accent: str, back_bg: str,
          workdir: Path, font_dir: Path) -> tuple[Path, dict]:
    import typst
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copy(TEMPLATE, workdir / "cover.typ")
    spine = spec.spine(pages)
    panel_w, panel_h = spec.trim_w + spec.bleed, spec.trim_h + 2 * spec.bleed
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
        r = rep.get(key)
        if r is None:                        # yazar adı boş: yazar bloğu yok
            continue
        size_mm = r["size"] * mm_per_px
        blocks.append({"lines": r["lines"], "font": _family(r["font"]), "weight": _face(st, key).weight,
                       "size": round(size_mm * PT_PER_MM, 1), "top": round(r["box"][1] * mm_per_px, 2),
                       "step": round(r["size"] * leading * mm_per_px, 2), "ink": "#%02x%02x%02x" % tuple(r["ink"])})
    code = None
    if ms.meta.get("ISBN"):
        (workdir / "barkod.svg").write_text(barcode.svg(ms.meta["ISBN"]))
        code = "barkod.svg"
    summary = ms.meta.get("CRM_SUMMARY") or ""
    data = {"bleed": spec.bleed, "trim_w": spec.trim_w, "trim_h": spec.trim_h, "spine": spine, "safe": spec.safe,
            "accent": accent, "body_font": spec.body_font, "heading_font": spec.heading_font,
            "title": ms.title, "author": ms.author or "", "publisher": ms.meta.get("PUBLISHER") or "",
            "front_image": front.name, "front_text": blocks, "barcode": code,
            "back": {"bg": back_bg, "paragraphs": [x.strip() for x in summary.split("\n") if x.strip()],
                     "age": f"{p.age_min}–{p.age_max} YAŞ" if p.age_min else None,
                     "series": ms.meta.get("SERIES")}}
    (workdir / "cover.json").write_text(json.dumps(data, ensure_ascii=False))
    out = workdir / "kapak.pdf"
    typst.compile(str(workdir / "cover.typ"), output=str(out), root=str(workdir), font_paths=[str(font_dir)],
                  ignore_system_fonts=True, sys_inputs={"data": "cover.json"})
    return out, {"spine_mm": spine, "binding": spec.binding(pages), "style": style, "text": rep,
                 "size_mm": [round(2 * spec.trim_w + spine + 2 * spec.bleed, 1), panel_h]}


def _face(st: ct.Style, key: str) -> ct.Face:
    return {"title": st.title, "author": st.author}[key]


FAMILY = {"Baloo2[wght].ttf": "Baloo 2", "PlayfairDisplay[wght].ttf": "Playfair Display",
          "CormorantGaramond[wght].ttf": "Cormorant Garamond", "NotoSerif[wdth,wght].ttf": "Noto Serif"}


def _family(file: str) -> str:
    return FAMILY[file]
