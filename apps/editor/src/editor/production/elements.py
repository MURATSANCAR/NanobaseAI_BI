"""Öğeler: süs/şekil kataloğu, efekt yazı stilleri, doğrulama ve önizleme (sayfa planı sözleşmesi,
«Efekt yazılar ve süs/şekiller»).

Çizim `templates/elements.typ`'tedir: `draw-shape(s, palette, fonts)` bir `shapes[]` öğesini, `effect-text(t, palette,
fonts)` `effect`'li bir serbest yazıyı kendi kutusunun içine (0,0,w,h) vektör olarak çizer; kutunun sayfadaki yeri,
döndürme, aynalama ve z sırası çağıranındır (plan.typ). Bu modül:
- `CATALOG` / `EFFECTS`: her tür ve stil için Türkçe ad, grup, varsayılan kutu, renk rolleri, parametreler (tür,
  seçenekler, varsayılan) ve hazır biçimler (`presets`; önizleme ucundaki `style`). Varsayılanlar `elements.typ`'teki
  SHAPE-DEFAULTS / EFFECT-DEFAULTS ile aynıdır (test sınar); ikisi birlikte değişir.
- `validate(obj)`: şekil ya da efekt nesnesi → hata metni (Türkçe) ya da None. Sayfa PUT'u bunu çağırır.
- `new_shape(kind, page, preset)`: «tıkla-ekle» için varsayılanlarla dolu şekil (kutu sayfa ölçüsünden).
- `catalog(job_dir)`, `render_shape_preview(...)`, `render_effect_preview(...)`: önizleme uçlarının gövdesi.

Renk alanları "#RRGGBB" (isteğe bağlı saydamlıkla "#RRGGBBAA") ya da rol adıdır. Roller kitabın paletinden türer
(`elements.typ` → `roles`): accent (vurgu), accent2, ink (yazı), pop/pop2 (canlı dolgu), sun (güneş sarısı), rose
(kalp kırmızısı), soft/soft2 (açık zemin), paper (kâğıt), wood/bark (ahşap), deep (koyu vurgu), white. Açık tonlarda kroma sınırlıdır (baskıya
uygun); renk verilmemiş alan türün varsayılan rolünü alır. Hesap yalnız Typst tarafındadır; Python rol renklerini
gerektiğinde Typst'e sorar (`roles_for`), iki ayrı hesap yoktur.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import tempfile
from functools import lru_cache
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "templates" / "elements.typ"

ROLES: dict[str, str] = {
    "accent": "Vurgu", "accent2": "İkinci renk", "ink": "Yazı rengi", "pop": "Canlı vurgu", "pop2": "Canlı ikinci",
    "sun": "Güneş sarısı", "rose": "Gül kırmızısı", "soft": "Açık vurgu", "soft2": "Açık ikinci", "paper": "Kâğıt", "wood": "Ahşap",
    "bark": "Koyu ahşap", "deep": "Koyu vurgu", "white": "Beyaz",
}
HEX = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
WEIGHTS = (400, 500, 600, 700, 800)
DEFAULT_FONTS = {"body": "Andika", "heading": "Baloo 2"}
DEFAULT_PAGE = {"w": 165, "h": 225, "bleed": 3, "safe": 10}     # kesim ölçüsü (mm); çocuk resimli dizi
PREVIEW_PAD = 1.5                                                 # önizlemede kutunun çevresi (mm)

GROUPS: list[dict] = [
    {"key": "cerceve", "name": "Çerçeve ve köşe"},
    {"key": "yazi", "name": "Yazı taşıyanlar"},
    {"key": "sekil", "name": "Şekiller"},
    {"key": "sus", "name": "Süs, çizgi ve ok"},
]


def _choice(label: str, default: str, *pairs: tuple[str, str]) -> dict:
    return {"label": label, "type": "choice", "default": default, "choices": [{"value": v, "label": t} for v, t in pairs]}


def _num(label: str, default: float, lo: float | None = None, hi: float | None = None, step: float = 0.1,
         integer: bool = False) -> dict:
    return {"label": label, "type": "int" if integer else "number", "default": default, "min": lo, "max": hi, "step": step}


def _bool(label: str, default: bool) -> dict:
    return {"label": label, "type": "bool", "default": default}


# Kutu: w = kesim genişliğine oran, ratio = en/boy, place = center | page (güvenli alanın yarısı içeride) | corner.
CATALOG: dict[str, dict] = {
    "frame": {
        "name": "Çerçeve", "group": "cerceve", "text": False,
        "box": {"w": 0.7, "ratio": 0.75, "place": "center"},
        "fill": "none", "stroke": "accent", "stroke_w": 1.2,
        "params": {
            "style": _choice("Çizgi", "plain", ("plain", "Düz"), ("wavy", "Dalgalı"), ("dotted", "Noktalı"),
                             ("double", "Çift çizgi"), ("dashed", "Kesik çizgi")),
            "radius": _num("Köşe yuvarlaklığı (mm)", 4, 0, None, 0.5),
            "ornament": _choice("Köşe süsü", "none", ("none", "Yok"), ("dot", "Nokta"), ("star", "Yıldız"),
                                ("heart", "Kalp")),
        },
        "presets": [
            {"key": "plain", "name": "Düz çerçeve", "params": {"style": "plain"}},
            {"key": "wavy", "name": "Dalgalı çerçeve", "params": {"style": "wavy"}},
            {"key": "dotted", "name": "Noktalı çerçeve", "params": {"style": "dotted"}},
            {"key": "double", "name": "Çift çizgili çerçeve", "params": {"style": "double"}},
            {"key": "dashed", "name": "Kesik çizgili çerçeve", "params": {"style": "dashed"}},
            {"key": "page", "name": "Tam sayfa kenarlık", "params": {"style": "double", "ornament": "star", "radius": 6},
             "box": {"place": "page"}},
        ],
    },
    "corner": {
        "name": "Köşe süsü", "group": "cerceve", "text": False,
        "box": {"w": 0.26, "ratio": 1.0, "place": "corner"},
        "fill": "pop2", "stroke": "accent", "stroke_w": 0.9,
        "params": {
            "corner": _choice("Köşe", "tl", ("tl", "Sol üst"), ("tr", "Sağ üst"), ("bl", "Sol alt"), ("br", "Sağ alt")),
            "style": _choice("Biçim", "swirl", ("swirl", "Kıvrım"), ("flower", "Çiçek"), ("dots", "Noktalar"),
                             ("stars", "Yıldızlar")),
        },
        "presets": [
            {"key": "swirl", "name": "Kıvrımlı köşe", "params": {"style": "swirl"}},
            {"key": "flower", "name": "Çiçekli köşe", "params": {"style": "flower"}},
            {"key": "dots", "name": "Noktalı köşe", "params": {"style": "dots"}},
            {"key": "stars", "name": "Yıldızlı köşe", "params": {"style": "stars"}},
        ],
    },
    "sign": {
        "name": "Tabela", "group": "yazi", "text": True,
        "box": {"w": 0.42, "ratio": 1.3, "place": "center"},
        "fill": "wood", "stroke": "bark", "stroke_w": 0.7,
        "params": {
            "posts": _num("Direk", 1, 0, 2, 1, integer=True),
            "point": _choice("Uç", "none", ("none", "Düz"), ("left", "Sola"), ("right", "Sağa")),
        },
        "runs": [{"text": "Orman Yolu"}],
        "presets": [
            {"key": "post", "name": "Direkli tabela", "params": {"posts": 1}},
            {"key": "two", "name": "İki direkli tabela", "params": {"posts": 2}},
            {"key": "arrow", "name": "Yön tabelası", "params": {"posts": 1, "point": "right"}},
            {"key": "board", "name": "Direksiz tabela", "params": {"posts": 0}, "box": {"ratio": 2.2}},
        ],
    },
    "note": {
        "name": "Not kâğıdı", "group": "yazi", "text": True,
        "box": {"w": 0.36, "ratio": 0.9, "place": "center"},
        "fill": "paper", "stroke": "wood", "stroke_w": 0.4,
        "params": {
            "pin": _choice("Tutturma", "tape", ("tape", "Bant"), ("pin", "Raptiye"), ("none", "Yok")),
            "lines": _bool("Çizgili", False),
        },
        "runs": [{"text": "Unutma!"}],
        "presets": [
            {"key": "tape", "name": "Bantlı not", "params": {"pin": "tape"}},
            {"key": "pin", "name": "Raptiyeli not", "params": {"pin": "pin"}},
            {"key": "lined", "name": "Çizgili not", "params": {"pin": "none", "lines": True}},
        ],
    },
    "envelope": {
        "name": "Zarf", "group": "yazi", "text": True,
        "box": {"w": 0.38, "ratio": 1.05, "place": "center"},
        "fill": "wood", "stroke": "bark", "stroke_w": 0.5,
        "params": {
            "open": _bool("Açık (mektup görünür)", True),
            "seal": _choice("Mühür", "heart", ("heart", "Kalp"), ("circle", "Yuvarlak"), ("none", "Yok")),
        },
        "runs": [{"text": "Sevgili dostum"}],
        "presets": [
            {"key": "open", "name": "Açık zarf", "params": {"open": True}},
            {"key": "closed", "name": "Kapalı zarf", "params": {"open": False}, "box": {"ratio": 1.5}},
        ],
    },
    "scroll": {
        "name": "Parşömen", "group": "yazi", "text": True,
        "box": {"w": 0.42, "ratio": 0.72, "place": "center"},
        "fill": "paper", "stroke": "bark", "stroke_w": 0.6,
        "params": {"orient": _choice("Yön", "vertical", ("vertical", "Dikey"), ("horizontal", "Yatay"))},
        "runs": [{"text": "Bir varmış, bir yokmuş"}],
        "presets": [
            {"key": "vertical", "name": "Dikey parşömen", "params": {"orient": "vertical"}},
            {"key": "horizontal", "name": "Yatay parşömen", "params": {"orient": "horizontal"}, "box": {"w": 0.55, "ratio": 1.9}},
        ],
    },
    "badge": {
        "name": "Rozet", "group": "yazi", "text": True,
        "box": {"w": 0.2, "ratio": 0.8, "place": "center"},
        "fill": "accent", "stroke": "none", "stroke_w": 0.6,
        "params": {
            "style": _choice("Biçim", "rosette", ("rosette", "Fistolu"), ("circle", "Yuvarlak"), ("star", "Yıldız")),
            "tails": _bool("Kurdele", True),
        },
        "runs": [{"text": "1"}],
        "presets": [
            {"key": "rosette", "name": "Fistolu rozet", "params": {"style": "rosette"}},
            {"key": "circle", "name": "Yuvarlak rozet", "params": {"style": "circle", "tails": False}, "box": {"ratio": 1.0}},
            {"key": "star", "name": "Yıldız rozet", "params": {"style": "star", "tails": False}, "box": {"ratio": 1.0}},
        ],
    },
    "ribbon": {
        "name": "Şerit", "group": "yazi", "text": True,
        "box": {"w": 0.62, "ratio": 3.6, "place": "center"},
        "fill": "accent", "stroke": "none", "stroke_w": 0.5,
        "params": {"curve": _num("Kavis", 0, -1, 1, 0.05)},
        "runs": [{"text": "Birinci Bölüm"}],
        "presets": [
            {"key": "straight", "name": "Düz şerit", "params": {"curve": 0}},
            {"key": "arch", "name": "Kavisli şerit", "params": {"curve": 0.6}, "box": {"ratio": 2.8}},
        ],
    },
    "star": {
        "name": "Yıldız", "group": "sekil", "text": True,
        "box": {"w": 0.2, "ratio": 1.0, "place": "center"},
        "fill": "sun", "stroke": "none", "stroke_w": 0.6,
        "params": {
            "points": _num("Köşe", 5, 3, None, 1, integer=True),
            "inner": _num("İç oran", 0.5, 0.2, 0.9, 0.05),
            "rounded": _bool("Yuvarlak köşe", True),
        },
        "runs": [],
        "presets": [
            {"key": "five", "name": "Yıldız", "params": {"points": 5}},
            {"key": "six", "name": "Altı köşeli yıldız", "params": {"points": 6, "inner": 0.58}},
        ],
    },
    "heart": {
        "name": "Kalp", "group": "sekil", "text": True,
        "box": {"w": 0.2, "ratio": 1.06, "place": "center"},
        "fill": "rose", "stroke": "none", "stroke_w": 0.6,
        "params": {},
        "runs": [],
        "presets": [{"key": "heart", "name": "Kalp", "params": {}}],
    },
    "cloud": {
        "name": "Bulut", "group": "sekil", "text": True,
        "box": {"w": 0.4, "ratio": 1.6, "place": "center"},
        "fill": "white", "stroke": "pop2", "stroke_w": 0.7,
        "params": {"puffs": _num("Kabarcık", 9, 5, None, 1, integer=True)},
        "runs": [],
        "presets": [{"key": "cloud", "name": "Bulut", "params": {}}],
    },
    "burst": {
        "name": "Patlama", "group": "sekil", "text": True,
        "box": {"w": 0.36, "ratio": 1.3, "place": "center"},
        "fill": "sun", "stroke": "ink", "stroke_w": 0.7,
        "params": {
            "spikes": _num("Uç", 12, 5, None, 1, integer=True),
            "seed": _num("Çeşit", 3, 0, None, 1, integer=True),
            "inner": _bool("İç patlama", True),
        },
        "runs": [{"text": "Bum!"}],
        "presets": [
            {"key": "double", "name": "Patlama", "params": {"inner": True}},
            {"key": "single", "name": "Sade patlama", "params": {"inner": False}},
        ],
    },
    "scatter": {
        "name": "Serpiştirme", "group": "sus", "text": False,
        "box": {"w": 0.6, "ratio": 1.3, "place": "center"},
        "fill": None, "stroke": "none", "stroke_w": 0,
        "params": {
            "item": _choice("Öğe", "star", ("star", "Yıldız"), ("heart", "Kalp"), ("dot", "Nokta"),
                            ("confetti", "Konfeti"), ("sparkle", "Pırıltı")),
            "count": _num("Adet", 14, 1, None, 1, integer=True),
            "seed": _num("Dağılım", 7, 0, None, 1, integer=True),
            "size": _num("Boy (mm)", 7, 0.5, None, 0.5),
        },
        "presets": [
            {"key": "star", "name": "Yıldız serpiştir", "params": {"item": "star"}},
            {"key": "heart", "name": "Kalp serpiştir", "params": {"item": "heart"}},
            {"key": "dot", "name": "Nokta serpiştir", "params": {"item": "dot", "count": 22, "size": 4}},
            {"key": "confetti", "name": "Konfeti", "params": {"item": "confetti", "count": 26, "size": 5}},
            {"key": "sparkle", "name": "Pırıltı", "params": {"item": "sparkle", "count": 10}},
        ],
    },
    "line": {
        "name": "Çizgi", "group": "sus", "text": False,
        "box": {"w": 0.6, "ratio": 8.0, "place": "center"},
        "fill": "none", "stroke": "accent", "stroke_w": 1.0,
        "params": {
            "style": _choice("Biçim", "wave", ("wave", "Dalga"), ("straight", "Düz"), ("zigzag", "Zikzak"),
                             ("dotted", "Noktalı"), ("dashed", "Kesik"), ("loops", "Halkalı")),
            "waves": _num("Dalga sayısı (0 = kendiliğinden)", 0, 0, None, 1, integer=True),
            "ends": _choice("Uçlar", "none", ("none", "Yok"), ("dot", "Nokta"), ("star", "Yıldız"), ("heart", "Kalp")),
        },
        "presets": [
            {"key": "wave", "name": "Dalgalı çizgi", "params": {"style": "wave"}},
            {"key": "straight", "name": "Düz çizgi", "params": {"style": "straight", "ends": "dot"}},
            {"key": "zigzag", "name": "Zikzak", "params": {"style": "zigzag"}},
            {"key": "dotted", "name": "Noktalı çizgi", "params": {"style": "dotted"}},
            {"key": "loops", "name": "Halkalı çizgi", "params": {"style": "loops"}},
            {"key": "stars", "name": "Yıldız uçlu çizgi", "params": {"style": "dashed", "ends": "star"}},
        ],
    },
    "arrow": {
        "name": "Ok", "group": "sus", "text": False,
        "box": {"w": 0.34, "ratio": 2.2, "place": "center"},
        "fill": "none", "stroke": "accent", "stroke_w": 1.6,
        "params": {
            "style": _choice("Biçim", "curved", ("curved", "Kıvrık"), ("straight", "Düz"), ("loop", "Halkalı")),
            "heads": _choice("Uç", "end", ("end", "Tek uç"), ("both", "İki uç")),
            "dashed": _bool("Kesik çizgi", False),
        },
        "presets": [
            {"key": "curved", "name": "Kıvrık ok", "params": {"style": "curved"}},
            {"key": "straight", "name": "Düz ok", "params": {"style": "straight"}, "box": {"ratio": 3.2}},
            {"key": "loop", "name": "Halkalı ok", "params": {"style": "loop"}},
            {"key": "dashed", "name": "Kesik ok", "params": {"style": "curved", "dashed": True}},
        ],
    },
}

EFFECTS: dict[str, dict] = {
    "burst": {"name": "Patlama", "sample": "Güüüm!", "box": (80, 56), "params": {
        "burst_fill": {"label": "Patlama rengi", "type": "color", "default": "sun"},
        "burst_stroke": {"label": "Patlama çizgisi", "type": "color", "default": "ink"},
        "angle": _num("Eğim (°)", -8, -45, 45, 1),
        "outline": {"label": "Dış çizgi rengi", "type": "color", "default": "white"},
        "outline_w": _num("Dış çizgi (mm)", 0.7, 0, None, 0.1),
        "spikes": _num("Uç", 12, 5, None, 1, integer=True),
        "seed": _num("Çeşit", 3, 0, None, 1, integer=True)}},
    "wave": {"name": "Dalga", "sample": "Şişşt! Sessizce…", "box": (100, 40), "params": {
        "curve": _num("Dalga yüksekliği", 0.5, -1, 1, 0.05),
        "waves": _num("Dalga sayısı", 1.5, 0.5, None, 0.5),
        "outline": {"label": "Dış çizgi rengi", "type": "color", "default": "white"},
        "outline_w": _num("Dış çizgi (mm)", 0.6, 0, None, 0.1)}},
    "arc": {"name": "Kavis", "sample": "Ağaç, çiçek, ırmak", "box": (100, 44), "params": {
        "curve": _num("Kavis", 0.6, -1, 1, 0.05),
        "outline": {"label": "Dış çizgi rengi", "type": "color", "default": "white"},
        "outline_w": _num("Dış çizgi (mm)", 0.6, 0, None, 0.1)}},
    "shadow": {"name": "Gölgeli", "sample": "Gölgeli yazı", "box": (90, 28), "params": {
        "shadow": {"label": "Gölge rengi", "type": "color", "default": "sun"},
        "shadow_dx": _num("Gölge sağa (mm)", 0.8, None, None, 0.1),
        "shadow_dy": _num("Gölge aşağı (mm)", 0.8, None, None, 0.1)}},
    "outline": {"name": "Dış çizgili", "sample": "Çıtır çıtır!", "box": (90, 28), "params": {
        "outline": {"label": "Dış çizgi rengi", "type": "color", "default": "white"},
        "outline_w": _num("Dış çizgi (mm)", 0.8, 0, None, 0.1),
        "shadow": {"label": "Gölge rengi", "type": "color", "default": "deep"},
        "shadow_dx": _num("Gölge sağa (mm)", 0, None, None, 0.1),
        "shadow_dy": _num("Gölge aşağı (mm)", 0, None, None, 0.1)}},
    "stacked": {"name": "Kabartma", "sample": "Büyük Gün", "box": (90, 30), "params": {
        "shadow": {"label": "Derinlik rengi", "type": "color", "default": "pop2"},
        "depth": _num("Derinlik (harf boyuna oran)", 0.09, 0, 0.5, 0.01),
        "outline": {"label": "Dış çizgi rengi", "type": "color", "default": "white"},
        "outline_w": _num("Dış çizgi (mm)", 0.6, 0, None, 0.1)}},
    "bounce": {"name": "Zıplayan", "sample": "Hop hop zıpla!", "box": (90, 30), "params": {
        "colors": {"label": "Harf renkleri (boş = palet)", "type": "colors", "default": None},
        "outline": {"label": "Dış çizgi rengi", "type": "color", "default": "white"},
        "outline_w": _num("Dış çizgi (mm)", 0.5, 0, None, 0.1)}},
    "rainbow": {"name": "Gökkuşağı", "sample": "Gökkuşağı", "box": (90, 28), "params": {
        "colors": {"label": "Harf renkleri (boş = palet)", "type": "colors", "default": None},
        "outline": {"label": "Dış çizgi rengi", "type": "color", "default": None},
        "outline_w": _num("Dış çizgi (mm)", 0.6, 0, None, 0.1)}},
}
# Sözleşmedeki ortak efekt parametreleri: her stil hepsini kabul eder (stilin kendi varsayılanı yoksa etkisi yok ya da
# genel anlamıyla uygulanır: dış çizgi/gölge her stilde çalışır).
EFFECT_PARAMS: dict[str, dict] = {}
for _st in EFFECTS.values():
    for _k, _spec in _st["params"].items():
        EFFECT_PARAMS.setdefault(_k, _spec)
EFFECT_PARAMS.setdefault("shadow", EFFECTS["shadow"]["params"]["shadow"])


# ------------------------------------------------------------------ varsayılanlar
def shape_defaults(kind: str) -> dict:
    """Typst SHAPE-DEFAULTS karşılığı: {fill, stroke, stroke_w, params}."""
    c = CATALOG[kind]
    return {"fill": c["fill"], "stroke": c["stroke"], "stroke_w": c["stroke_w"],
            "params": {k: v["default"] for k, v in c["params"].items()}}


def effect_defaults(style: str) -> dict:
    return {k: v["default"] for k, v in EFFECTS[style]["params"].items()}


def _preset(kind: str, key: str | None) -> dict:
    presets = CATALOG[kind]["presets"]
    if key in (None, ""):
        return presets[0]
    for p in presets:
        if p["key"] == key:
            return p
    raise ValueError(f"«{CATALOG[kind]['name']}» için böyle bir biçim yok: {key}")


def default_box(kind: str, page: dict | None = None, preset: str | None = None) -> dict:
    """Sayfaya eklenen şeklin kutusu (mm, taşma paylı sayfanın sol üstünden)."""
    pg = {**DEFAULT_PAGE, **(page or {})}
    spec = {**CATALOG[kind]["box"], **_preset(kind, preset).get("box", {})}
    b, safe = float(pg["bleed"]), float(pg["safe"])
    if spec["place"] == "page":
        return {"x": b + safe / 2, "y": b + safe / 2, "w": pg["w"] - safe, "h": pg["h"] - safe}
    w = round(pg["w"] * spec["w"], 1)
    h = round(w / spec["ratio"], 1)
    if spec["place"] == "corner":
        return {"x": b + safe / 2, "y": b + safe / 2, "w": w, "h": h}
    return {"x": round(b + (pg["w"] - w) / 2, 1), "y": round(b + (pg["h"] - h) / 2, 1), "w": w, "h": h}


def new_shape(kind: str, page: dict | None = None, preset: str | None = None, *, id: str | None = None,
              z: int = 3) -> dict:
    """«Tıkla-ekle»: varsayılanlarla dolu şekil. Renk alanları None → türün varsayılan rolü (paletten)."""
    if kind not in CATALOG:
        raise KeyError(kind)
    c = CATALOG[kind]
    pr = _preset(kind, preset)
    return {
        "id": id or "s_" + secrets.token_hex(4), "kind": kind, "box": default_box(kind, page, preset),
        "rotate": 0, "flip": False, "z": z, "fill": None, "stroke": None, "stroke_w": None, "opacity": 1,
        "params": {**{k: v["default"] for k, v in c["params"].items()}, **pr["params"]},
        "runs": copy.deepcopy(c.get("runs", [])) if c["text"] else [], "text_size": None,
    }


def new_effect(style: str) -> dict:
    if style not in EFFECTS:
        raise KeyError(style)
    return {"style": style, "params": effect_defaults(style)}


# ------------------------------------------------------------------ doğrulama
def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _color_err(v, what: str, allow_none: bool = True) -> str | None:
    if v is None and allow_none:
        return None
    if isinstance(v, str) and (v == "none" or v in ROLES or HEX.match(v)):
        return None
    return f"{what}: renk «#RRGGBB» ya da palet rolü olmalı ({', '.join(ROLES)})"


def _param_err(name: str, spec: dict, v, where: str) -> str | None:
    label = f"{where} · {spec.get('label', name)}"
    t = spec["type"]
    if t == "choice":
        ok = [c["value"] for c in spec["choices"]]
        return None if v in ok else f"{label}: {', '.join(ok)} değerlerinden biri olmalı"
    if t == "bool":
        return None if isinstance(v, bool) else f"{label}: doğru/yanlış olmalı"
    if t == "color":
        return _color_err(v, label)
    if t == "colors":
        if v is None:
            return None
        if not isinstance(v, list):
            return f"{label}: renk listesi olmalı"
        for c in v:
            if e := _color_err(c, label, allow_none=False):
                return e
        return None
    if t in ("number", "int"):
        if not _is_num(v) or (t == "int" and float(v) != int(v)):
            return f"{label}: {'tam sayı' if t == 'int' else 'sayı'} olmalı"
        if spec.get("min") is not None and v < spec["min"]:
            return f"{label}: en az {spec['min']:g}"
        if spec.get("max") is not None and v > spec["max"]:
            return f"{label}: en çok {spec['max']:g}"
        return None
    return f"{label}: bilinmeyen parametre türü"


def _runs_err(runs, where: str) -> str | None:
    if not isinstance(runs, list):
        return f"{where}: yazı (runs) liste olmalı"
    for i, r in enumerate(runs, 1):
        if not isinstance(r, dict) or not isinstance(r.get("text"), str):
            return f"{where}: {i}. yazı parçasında metin yok"
        if e := _color_err(r.get("color"), f"{where}: {i}. yazı parçası"):
            return e
        if r.get("weight") is not None and r["weight"] not in WEIGHTS:
            return f"{where}: {i}. yazı parçasının kalınlığı {', '.join(map(str, WEIGHTS))} olmalı"
        if r.get("size") is not None and not (_is_num(r["size"]) and r["size"] > 0):
            return f"{where}: {i}. yazı parçasının puntosu sıfırdan büyük olmalı"
        if r.get("font") is not None and r["font"] not in ("body", "heading"):
            return f"{where}: {i}. yazı parçasının fontu «body» ya da «heading» olmalı"
        if r.get("source") is not None and r["source"] not in ("auto", "editor"):
            return f"{where}: {i}. yazı parçasının kaynağı «auto» ya da «editor» olmalı"
    return None


def _box_err(b, where: str) -> str | None:
    if not isinstance(b, dict) or not all(_is_num(b.get(k)) for k in ("x", "y", "w", "h")):
        return f"{where}: kutu {{x, y, w, h}} sayı olmalı"
    if b["w"] <= 0 or b["h"] <= 0:
        return f"{where}: kutunun eni ve boyu sıfırdan büyük olmalı"
    return None


def validate_shape(s) -> str | None:
    if not isinstance(s, dict):
        return "Şekil nesne olmalı"
    kind = s.get("kind")
    if kind not in CATALOG:
        return f"Bilinmeyen şekil türü: {kind}"
    c = CATALOG[kind]
    where = c["name"]
    if "id" in s and (not isinstance(s["id"], str) or not s["id"]):
        return f"{where}: kimlik (id) boş olamaz"
    if e := _box_err(s.get("box"), where):
        return e
    for k in ("rotate",):
        if s.get(k) is not None and not _is_num(s[k]):
            return f"{where}: döndürme açısı sayı olmalı"
    if s.get("flip") is not None and not isinstance(s["flip"], bool):
        return f"{where}: aynalama doğru/yanlış olmalı"
    if s.get("z") is not None and not (isinstance(s["z"], int) and not isinstance(s["z"], bool)):
        return f"{where}: katman sırası (z) tam sayı olmalı"
    for k, what in (("fill", "dolgu"), ("stroke", "çizgi")):
        if e := _color_err(s.get(k), f"{where} · {what}"):
            return e
    if s.get("stroke_w") is not None and not (_is_num(s["stroke_w"]) and s["stroke_w"] >= 0):
        return f"{where}: çizgi kalınlığı sıfır ya da pozitif olmalı"
    if s.get("opacity") is not None and not (_is_num(s["opacity"]) and 0 <= s["opacity"] <= 1):
        return f"{where}: saydamlık 0 ile 1 arasında olmalı"
    params = s.get("params") or {}
    if not isinstance(params, dict):
        return f"{where}: parametreler nesne olmalı"
    for k, v in params.items():
        if k not in c["params"]:
            return f"{where}: bilinmeyen parametre «{k}»"
        if e := _param_err(k, c["params"][k], v, where):
            return e
    runs = s.get("runs") or []
    if e := _runs_err(runs, where):
        return e
    if runs and not c["text"]:
        return f"{where} yazı taşımaz"
    if s.get("text_size") is not None and not (_is_num(s["text_size"]) and s["text_size"] > 0):
        return f"{where}: yazı puntosu sıfırdan büyük olmalı"
    return None


def validate_effect(e) -> str | None:
    if not isinstance(e, dict):
        return "Efekt nesne olmalı"
    style = e.get("style")
    if style not in EFFECTS:
        return f"Bilinmeyen efekt: {style}"
    where = EFFECTS[style]["name"]
    params = e.get("params") or {}
    if not isinstance(params, dict):
        return f"{where}: parametreler nesne olmalı"
    for k, v in params.items():
        spec = EFFECTS[style]["params"].get(k) or EFFECT_PARAMS.get(k)
        if spec is None:
            return f"{where}: bilinmeyen parametre «{k}»"
        if v is None and spec["type"] in ("color", "colors"):
            continue
        if e2 := _param_err(k, spec, v, where):
            return e2
    return None


def validate(obj) -> str | None:
    """Şekil (`kind` alanı) ya da efekt (`style` alanı) → hata metni ya da None."""
    if isinstance(obj, dict) and "kind" in obj:
        return validate_shape(obj)
    if isinstance(obj, dict) and "style" in obj:
        return validate_effect(obj)
    return "Şekil ya da efekt değil (kind ya da style alanı yok)"


# ------------------------------------------------------------------ kitap bağlamı ve Typst
def font_dir() -> Path:
    return Path(os.environ.get("EDITOR_FONT_DIR", "/app/data/fonts"))


def default_palette() -> dict:
    from .palette import TIMAS_KIDS
    return {"colors": [{**c, "source": "timas"} for c in TIMAS_KIDS[:6]], "text": "#2C2C2A", "characters": {}}


def book_context(job_dir: Path | None) -> tuple[dict, dict]:
    """(palet, fontlar): iş varsa plan.json paleti ve spec.json fontları, yoksa Timaş çocuk paleti ve çocuk fontları."""
    palette, fonts = None, dict(DEFAULT_FONTS)
    if job_dir is not None:
        d = Path(job_dir)
        try:
            palette = (json.loads((d / "plan.json").read_text()).get("palette") if (d / "plan.json").exists() else None)
        except (OSError, ValueError):
            palette = None
        try:
            spec = json.loads((d / "spec.json").read_text()) if (d / "spec.json").exists() else {}
            fonts = {"body": spec.get("body_font") or fonts["body"], "heading": spec.get("heading_font") or fonts["heading"]}
        except (OSError, ValueError):
            pass
    if not palette or not palette.get("colors"):
        palette = {**default_palette(), **({k: v for k, v in (palette or {}).items() if k != "colors"})}
    return palette, fonts


def _typst_dir(main: str, data: dict) -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory(prefix="ogeler-")
    shutil.copy(TEMPLATE, Path(tmp.name) / "elements.typ")
    (Path(tmp.name) / "data.json").write_text(json.dumps(data, ensure_ascii=False))
    (Path(tmp.name) / "main.typ").write_text(main)
    return tmp


def typst_png(main: str, data: dict, ppi: float) -> bytes:
    import typst
    with _typst_dir(main, data) as tmp:
        return typst.compile(str(Path(tmp) / "main.typ"), root=tmp, font_paths=[str(font_dir())],
                             ignore_system_fonts=True, format="png", ppi=ppi)


def typst_pdf(main: str, data: dict) -> bytes:
    import typst
    with _typst_dir(main, data) as tmp:
        return typst.compile(str(Path(tmp) / "main.typ"), root=tmp, font_paths=[str(font_dir())],
                             ignore_system_fonts=True)


def typst_query(main: str, data: dict) -> list:
    import typst
    with _typst_dir(main, data) as tmp:
        out = typst.query(str(Path(tmp) / "main.typ"), "metadata", root=tmp, font_paths=[str(font_dir())],
                          ignore_system_fonts=True)
    return [m["value"] for m in json.loads(out)]


@lru_cache(maxsize=64)
def _roles_cached(palette_json: str) -> dict:
    main = '#import "elements.typ": roles\n#metadata(roles(json("data.json").palette))\n'
    return typst_query(main, {"palette": json.loads(palette_json)})[0]


def roles_for(palette: dict) -> dict:
    """Paletten rol renkleri (Typst'in hesabı; çizimle birebir aynı)."""
    return _roles_cached(json.dumps(palette, sort_keys=True, ensure_ascii=False))


def catalog(job_dir: Path | None = None) -> dict:
    """Ekranın öğe kütüphanesi: gruplar, türler (varsayılanlar, parametreler, hazır biçimler), efekt stilleri ve bu
    kitabın paletinden rol renkleri."""
    palette, fonts = book_context(job_dir)
    roles = roles_for(palette)
    kinds = []
    for key, c in CATALOG.items():
        kinds.append({
            "kind": key, "name": c["name"], "group": c["group"], "text": c["text"], "box": c["box"],
            "fill": c["fill"], "stroke": c["stroke"], "stroke_w": c["stroke_w"], "params": c["params"],
            "runs": c.get("runs", []) if c["text"] else [],
            "presets": [{"key": p["key"], "name": p["name"], "params": p["params"], "box": p.get("box")}
                        for p in c["presets"]],
        })
    effects = [{"style": k, "name": v["name"], "sample": v["sample"], "box": {"w": v["box"][0], "h": v["box"][1]},
                "params": v["params"]} for k, v in EFFECTS.items()]
    return {
        "groups": [{**g, "kinds": [k for k, c in CATALOG.items() if c["group"] == g["key"]]} for g in GROUPS],
        "kinds": kinds, "effects": effects,
        "roles": [{"key": k, "name": n, "hex": roles.get(k)} for k, n in ROLES.items()],
        "fonts": fonts,
    }


# ------------------------------------------------------------------ önizleme
_SHAPE_DOC = """#import "elements.typ": draw-shape
#let d = json("data.json")
#set page(width: d.pw * 1mm, height: d.ph * 1mm, margin: d.pad * 1mm, fill: none)
#draw-shape(d.item, d.palette, d.fonts)
"""
_EFFECT_DOC = """#import "elements.typ": effect-text
#let d = json("data.json")
#set page(width: d.pw * 1mm, height: d.ph * 1mm, margin: d.pad * 1mm, fill: none)
#effect-text(d.item, d.palette, d.fonts)
"""


def _check_width(width) -> int:
    if not isinstance(width, int) or isinstance(width, bool) or width < 16 or width > 4000:
        raise ValueError("önizleme genişliği 16–4000 piksel olmalı")
    return width


def _preview(doc: str, item: dict, width: int, job_dir: Path | None) -> bytes:
    palette, fonts = book_context(job_dir)
    pw, ph = item["box"]["w"] + 2 * PREVIEW_PAD, item["box"]["h"] + 2 * PREVIEW_PAD
    data = {"item": item, "palette": palette, "fonts": fonts, "pw": pw, "ph": ph, "pad": PREVIEW_PAD}
    ppi = width / (pw / 25.4)
    cache = None
    if job_dir is not None:
        key = hashlib.sha1(json.dumps([doc, data, width], sort_keys=True, ensure_ascii=False).encode()
                           + TEMPLATE.read_bytes()).hexdigest()[:20]
        cache = Path(job_dir) / "dizgi" / "ogeler" / f"{key}.png"
        if cache.exists():
            return cache.read_bytes()
    png = typst_png(doc, data, ppi)
    if cache is not None:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".tmp")
            tmp.write_bytes(png)
            tmp.replace(cache)
        except OSError:
            pass                                       # önbellek yazılamadıysa önizleme yine döner
    return png


def render_shape_preview(kind: str, width: int = 240, style: str | None = None, job_dir: Path | None = None) -> bytes:
    """Kütüphane küçük resmi (saydam PNG): türün `style` hazır biçimi, kitabın paleti ve fontlarıyla.
    Bilinmeyen tür KeyError, bilinmeyen biçim/genişlik ValueError."""
    if kind not in CATALOG:
        raise KeyError(kind)
    item = new_shape(kind, preset=style, id="onizleme")
    return _preview(_SHAPE_DOC, item, _check_width(width), job_dir)


def render_effect_preview(style: str, text: str | None = None, width: int = 360, job_dir: Path | None = None) -> bytes:
    """Efekt yazı önizlemesi (saydam PNG). Metin verilmezse stilin örnek metni. Bilinmeyen stil KeyError."""
    if style not in EFFECTS:
        raise KeyError(style)
    w, h = EFFECTS[style]["box"]
    t = (text or "").strip() or EFFECTS[style]["sample"]
    item = {"id": "onizleme", "box": {"x": 0, "y": 0, "w": w, "h": h}, "align": "center", "size": None,
            "runs": [{"text": t, "font": "heading", "weight": 800}], "effect": new_effect(style)}
    return _preview(_EFFECT_DOC, item, _check_width(width), job_dir)
