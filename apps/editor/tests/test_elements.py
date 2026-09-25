"""Öğeler: süs/şekil kataloğu, efekt yazı, doğrulama, Typst çizimi ve önizleme (sayfa planı sözleşmesi,
«Efekt yazılar ve süs/şekiller»).

Stüdyo imajında koşar (Typst ve fontlar orada; EDITOR_FONT_DIR). Görsel denetim için bütün şekil ve efektlerin
temas sayfası üretilir; `ELEMENTS_SHEET=/yol/sayfa.png` verilirse oraya da yazılır.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from editor.production import elements as el

CONTRACT_KINDS = {"frame", "corner", "scatter", "arrow", "sign", "note", "envelope", "scroll", "badge", "ribbon",
                  "star", "heart", "cloud", "burst", "line"}
CONTRACT_EFFECTS = {"burst", "wave", "arc", "shadow", "outline", "stacked", "bounce", "rainbow"}
TR = "Güüüm! Şişşt! Ağaç, çiçek, ırmak"
PNG = b"\x89PNG\r\n\x1a\n"
OTHER_PALETTE = {"colors": [{"name": "Petrol mavisi", "hex": "#0B6477"}, {"name": "Menekşe", "hex": "#6A4499"},
                            {"name": "Zeytin yeşili", "hex": "#4F6B1F"}, {"name": "Turuncu", "hex": "#B04A00"}],
                 "text": "#1B2440", "characters": {"Elif": "#6A4499"}}


def _squash(s: str) -> str:
    return "".join(s.split())


# ------------------------------------------------------------------ katalog
def test_catalog_covers_contract():
    assert set(el.CATALOG) == CONTRACT_KINDS
    assert set(el.EFFECTS) == CONTRACT_EFFECTS
    groups = {g["key"] for g in el.GROUPS}
    for kind, c in el.CATALOG.items():
        assert c["name"] and c["group"] in groups and c["presets"], kind
        assert isinstance(c["text"], bool)
        for p in c["params"].values():
            assert p["label"] and "default" in p
    frame_styles = {c["value"] for c in el.CATALOG["frame"]["params"]["style"]["choices"]}
    assert {"plain", "wavy", "dotted", "double"} <= frame_styles
    assert any(p.get("box", {}).get("place") == "page" for p in el.CATALOG["frame"]["presets"])  # tam sayfa kenarlık
    assert {c["value"] for c in el.CATALOG["scatter"]["params"]["item"]["choices"]} >= {"star", "heart", "dot", "confetti"}
    assert {c["value"] for c in el.CATALOG["arrow"]["params"]["style"]["choices"]} >= {"straight", "curved"}


def test_catalog_payload_is_json_and_has_roles():
    cat = el.catalog(None)
    json.dumps(cat, ensure_ascii=False)
    assert {k for g in cat["groups"] for k in g["kinds"]} == CONTRACT_KINDS
    roles = {r["key"]: r["hex"] for r in cat["roles"]}
    assert set(roles) == set(el.ROLES)
    assert all(isinstance(h, str) and el.HEX.match(h) for h in roles.values())
    assert cat["fonts"] == el.DEFAULT_FONTS


def test_defaults_match_typst():
    main = ('#import "elements.typ": SHAPE-DEFAULTS, EFFECT-DEFAULTS\n'
            "#metadata(SHAPE-DEFAULTS)\n#metadata(EFFECT-DEFAULTS)\n")
    shapes, effects = el.typst_query(main, {})
    assert set(shapes) == set(el.CATALOG)
    for kind in el.CATALOG:
        assert shapes[kind] == el.shape_defaults(kind), kind
    for style in el.EFFECTS:
        assert effects[style] == el.effect_defaults(style), style


def test_new_shape_and_presets_validate():
    page = {"w": 169, "h": 231, "bleed": 2, "safe": 8}
    for kind, c in el.CATALOG.items():
        for p in c["presets"]:
            s = el.new_shape(kind, page, p["key"])
            assert el.validate(s) is None, (kind, p["key"], el.validate(s))
            b = s["box"]
            assert b["x"] >= 0 and b["y"] >= 0
            assert b["x"] + b["w"] <= page["w"] + 2 * page["bleed"] + 1e-6
            assert b["y"] + b["h"] <= page["h"] + 2 * page["bleed"] + 1e-6
    full = el.new_shape("frame", page, "page")["box"]
    assert full == {"x": 6.0, "y": 6.0, "w": 161, "h": 223}
    for style in el.EFFECTS:
        assert el.validate(el.new_effect(style)) is None


# ------------------------------------------------------------------ doğrulama
@pytest.mark.parametrize("patch,fragment", [
    ({"kind": "uçak"}, "Bilinmeyen şekil"),
    ({"box": {"x": 0, "y": 0, "w": 0, "h": 10}}, "sıfırdan büyük"),
    ({"box": {"x": 0, "y": 0, "w": "on"}}, "kutu"),
    ({"fill": "kırmızı"}, "renk"),
    ({"stroke": "#12345"}, "renk"),
    ({"opacity": 1.5}, "saydamlık"),
    ({"params": {"posts": 3}}, "en çok 2"),
    ({"params": {"point": "yukarı"}}, "değerlerinden biri"),
    ({"params": {"renk": 1}}, "bilinmeyen parametre"),
    ({"runs": [{"text": "a", "weight": 900}]}, "kalınlığı"),
    ({"runs": [{"text": "a", "color": "mavi"}]}, "renk"),
    ({"runs": [{"yazi": "a"}]}, "metin yok"),
    ({"text_size": 0}, "puntosu"),
    ({"z": 1.5}, "katman"),
])
def test_validate_shape_errors(patch, fragment):
    s = el.new_shape("sign")
    s.update(patch)
    err = el.validate(s)
    assert err and fragment in err, err


def test_validate_shape_accepts_roles_hex_and_alpha():
    s = el.new_shape("note")
    s.update(fill="#FFF8E7", stroke="bark", runs=[{"text": "Ağaç", "color": "#B0341CE6", "weight": 800,
                                                    "font": "heading", "size": 18, "source": "editor"}])
    assert el.validate(s) is None
    assert "yazı taşımaz" in el.validate({**el.new_shape("frame"), "runs": [{"text": "x"}]})


def test_validate_effect():
    assert el.validate({"style": "arc", "params": {"curve": 0.6, "outline": "#FFFFFF", "outline_w": 0.8}}) is None
    assert el.validate({"style": "rainbow", "params": {"colors": ["#B0341C", "accent2"]}}) is None
    assert el.validate({"style": "shadow", "params": {"outline": "white"}}) is None     # ortak parametre
    assert "Bilinmeyen efekt" in el.validate({"style": "sparkle"})
    assert "en çok 1" in el.validate({"style": "arc", "params": {"curve": 1.4}})
    assert "renk" in el.validate({"style": "rainbow", "params": {"colors": ["yeşil"]}})
    assert "bilinmeyen parametre" in el.validate({"style": "wave", "params": {"hız": 2}})
    assert el.validate({"foo": 1}).startswith("Şekil ya da efekt değil")


# ------------------------------------------------------------------ roller
def test_roles_follow_palette():
    r = el.roles_for(el.default_palette())
    assert r["accent"] == "#1F3B73" and r["accent2"] == "#B0341C"
    assert r["sun"] != r["accent"] and r["ink"] == "#2C2C2A"
    # karaktere verilmiş renk vurgu olmaz; palette.roles kazanır
    r2 = el.roles_for(OTHER_PALETTE)
    assert r2["accent"] == "#0B6477" and r2["accent2"] == "#4F6B1F" and r2["ink"] == "#1B2440"
    r3 = el.roles_for({**OTHER_PALETTE, "roles": {"sun": "#FFD23F"}})
    assert r3["sun"] == "#FFD23F"
    # sıcak renk yoksa «güneş» Timaş hardalından
    cold = el.roles_for({"colors": [{"hex": "#1F3B73"}, {"hex": "#0B6477"}]})
    assert cold["sun"] == el.roles_for({"colors": [{"hex": "#8A6500"}]})["sun"]


# ------------------------------------------------------------------ çizim
def _sheet_data(palette=None) -> dict:
    return {"palette": palette or el.default_palette(), "fonts": el.DEFAULT_FONTS}


def test_every_shape_and_preset_renders_deterministically():
    for kind, c in el.CATALOG.items():
        for p in c["presets"]:
            a = el.render_shape_preview(kind, 160, p["key"])
            b = el.render_shape_preview(kind, 160, p["key"])
            assert a.startswith(PNG) and a == b, (kind, p["key"])
    with pytest.raises(KeyError):
        el.render_shape_preview("uçak", 160)
    with pytest.raises(ValueError):
        el.render_shape_preview("frame", 160, "yok")
    with pytest.raises(ValueError):
        el.render_shape_preview("frame", 5)


def test_scatter_seed_is_deterministic():
    main = ('#import "elements.typ": draw-shape\n#let d = json("data.json")\n'
            "#set page(width: 110mm, height: 90mm, margin: 2mm)\n#draw-shape(d.item, d.palette, d.fonts)\n")

    def png(seed):
        s = el.new_shape("scatter", preset="confetti", id="s1")
        s["params"]["seed"] = seed
        return el.typst_png(main, {**_sheet_data(), "item": s}, 72)
    assert png(3) == png(3)
    assert png(3) != png(4)


def test_effects_are_vector_text_with_turkish():
    import pymupdf
    pages = []
    for style in el.EFFECTS:
        pages.append({"id": f"t_{style}", "box": {"x": 0, "y": 0, "w": 110, "h": 50}, "align": "center", "size": None,
                      "runs": [{"text": TR, "font": "heading", "weight": 800}], "effect": el.new_effect(style)})
    main = ('#import "elements.typ": effect-text\n#let d = json("data.json")\n'
            "#set page(width: 116mm, height: 56mm, margin: 3mm)\n"
            "#for (i, t) in d.items.enumerate() { if i > 0 { pagebreak() }; effect-text(t, d.palette, d.fonts) }\n")
    pdf = el.typst_pdf(main, {**_sheet_data(), "items": pages})
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    assert doc.page_count == len(el.EFFECTS)
    for i, style in enumerate(el.EFFECTS):
        page = doc[i]
        assert page.get_images() == [], style                 # resim yok: her şey vektör
        assert _squash(TR) in _squash(page.get_text()), (style, page.get_text()[:200])


def test_shape_text_is_vector_and_turkish():
    import pymupdf
    items = []
    for kind, c in el.CATALOG.items():
        if c["text"]:
            s = el.new_shape(kind, id=f"s_{kind}")
            s["runs"] = [{"text": "Ağaç çiçek ırmak"}]
            items.append(s)
    main = ('#import "elements.typ": draw-shape\n#let d = json("data.json")\n'
            "#set page(width: 200mm, height: 200mm, margin: 3mm)\n"
            "#for (i, s) in d.items.enumerate() { if i > 0 { pagebreak() }; draw-shape(s, d.palette, d.fonts) }\n")
    doc = __import__("pymupdf").open(stream=el.typst_pdf(main, {**_sheet_data(), "items": items}), filetype="pdf")
    for i, s in enumerate(items):
        assert doc[i].get_images() == []
        assert "Ağaççiçekırmak" in _squash(doc[i].get_text()), (s["kind"], doc[i].get_text())


def test_mirror_keeps_text_readable():
    import pymupdf
    main = ('#import "elements.typ": draw-shape\n#let d = json("data.json")\n'
            "#set page(width: 80mm, height: 60mm, margin: 3mm)\n"
            "#draw-shape(d.item, d.palette, d.fonts, mirror: d.mirror)\n")
    s = el.new_shape("sign", preset="arrow", id="s1")
    s["runs"] = [{"text": "Çiçek Yolu"}]
    a = el.typst_pdf(main, {**_sheet_data(), "item": s, "mirror": False})
    b = el.typst_pdf(main, {**_sheet_data(), "item": s, "mirror": True})
    assert a != b
    text = pymupdf.open(stream=b, filetype="pdf")[0].get_text()
    assert "ÇiçekYolu" in _squash(text), text


def test_fixed_size_overflow_is_reported():
    main = ('#import "elements.typ": draw-shape, effect-text\n#let d = json("data.json")\n'
            "#set page(width: 200mm, height: 200mm, margin: 3mm)\n"
            "#for s in d.shapes { draw-shape(s, d.palette, d.fonts) }\n"
            "#for t in d.texts { effect-text(t, d.palette, d.fonts) }\n")
    big = el.new_shape("sign", id="s_big")
    big["text_size"] = 90
    auto = el.new_shape("sign", id="s_auto")
    t_big = {"id": "t_big", "box": {"x": 0, "y": 0, "w": 40, "h": 12}, "size": 80, "runs": [{"text": TR}],
             "effect": el.new_effect("arc")}
    t_auto = {**t_big, "id": "t_auto", "size": None}
    marks = el.typst_query(main, {**_sheet_data(), "shapes": [big, auto], "texts": [t_big, t_auto]})
    over = {m["id"] for m in marks if isinstance(m, dict) and m.get("kind") == "element-overflow"}
    assert over == {"s_big", "t_big"}


def test_preview_uses_book_palette_and_cache(tmp_path):
    (tmp_path / "spec.json").write_text(json.dumps({"body_font": "Noto Serif", "heading_font": "Playfair Display"}))
    (tmp_path / "plan.json").write_text(json.dumps({"palette": OTHER_PALETTE}))
    cat = el.catalog(tmp_path)
    assert cat["fonts"] == {"body": "Noto Serif", "heading": "Playfair Display"}
    assert {r["key"]: r["hex"] for r in cat["roles"]}["accent"] == "#0B6477"
    a = el.render_effect_preview("rainbow", "Ağaç", 300, tmp_path)
    assert list((tmp_path / "dizgi" / "ogeler").glob("*.png"))
    assert el.render_effect_preview("rainbow", "Ağaç", 300, tmp_path) == a
    assert a != el.render_effect_preview("rainbow", "Ağaç", 300, None)          # palet farkı görünür
    assert el.render_shape_preview("badge", 200, "circle", tmp_path).startswith(PNG)


# ------------------------------------------------------------------ temas sayfası (görsel denetim)
SHEET = """#import "elements.typ": draw-shape, effect-text, roles
#let d = json("data.json")
#set page(width: 290mm, height: auto, margin: 8mm, fill: rgb("#FBFAF7"))
#set text(font: "Andika", size: 8pt, lang: "tr")
#let cell(label, body, bg: white) = box(width: 66mm, height: 60mm, stroke: 0.3pt + luma(215), radius: 1.5mm,
  inset: 2.5mm, fill: bg, {
    text(size: 7pt, fill: luma(100), label)
    place(center + horizon, dy: 2mm, body)
  })
#let sw(R) = for k in ("accent", "accent2", "ink", "pop", "pop2", "sun", "rose", "soft", "soft2", "paper", "wood", "bark", "deep") {
  box(width: 21mm, inset: 1mm, [#box(width: 5mm, height: 5mm, fill: rgb(R.at(k)), stroke: 0.3pt + luma(180)) #text(size: 6.5pt, k)])
}
#for (pi, grp) in d.sets.enumerate() {
  let R = roles(grp.palette)
  text(size: 11pt, weight: 700, grp.title)
  linebreak()
  sw(R)
  v(2mm)
  grid(columns: 4, gutter: 2mm, ..grp.shapes.map(s => cell(s.label,
    scale(s.k * 100%, reflow: true, draw-shape(s.item, grp.palette, d.fonts)))))
  v(3mm)
  grid(columns: 4, gutter: 2mm, ..grp.effects.map(t => cell(t.label, bg: rgb("#CFE6EF"),
    scale(t.k * 100%, reflow: true, effect-text(t.item, grp.palette, d.fonts)))))
  if pi < d.sets.len() - 1 { pagebreak() }
}
"""


def _sheet_set(title: str, palette: dict, samples: dict, only: set | None = None) -> dict:
    shapes, effects = [], []
    for kind, c in el.CATALOG.items():
        for p in c["presets"]:
            if only and kind not in only:
                continue
            s = el.new_shape(kind, preset=p["key"], id=f"{kind}-{p['key']}")
            if c["text"] and kind in samples:
                s["runs"] = [{"text": samples[kind]}]
            b = s["box"]
            shapes.append({"label": f"{c['name']} · {p['name']}", "item": s, "k": min(58 / b["w"], 46 / b["h"], 1.6)})
    for style, e in el.EFFECTS.items():
        w, h = e["box"]
        effects.append({"label": f"Efekt · {e['name']}", "k": min(58 / w, 46 / h),
                        "item": {"id": f"t-{style}", "box": {"x": 0, "y": 0, "w": w, "h": h}, "size": None,
                                 "align": "center", "runs": [{"text": samples.get(style, e["sample"]), "font": "heading",
                                                              "weight": 800}], "effect": el.new_effect(style)}})
    return {"title": title, "palette": palette, "shapes": shapes, "effects": effects}


def test_contact_sheet(tmp_path):
    samples = {"burst": "Güüüm!", "wave": "Şişşt! Sessizce…", "arc": "Ağaç, çiçek, ırmak", "shadow": "Işıl ışıl",
               "outline": "Çıtır çıtır!", "stacked": "Büyük Gün", "bounce": "Hop hop zıpla!", "rainbow": "Gökkuşağı",
               "sign": "Orman Yolu", "scroll": "Bir varmış, bir yokmuş", "ribbon": "Birinci Bölüm",
               "note": "Unutma: çiçekleri sula!", "envelope": "Sevgili Ayşe", "badge": "7", "star": "5", "heart": "Sev",
               "cloud": "Düşün…"}
    data = {"fonts": el.DEFAULT_FONTS, "sets": [
        _sheet_set("Timaş çocuk paleti", el.default_palette(), samples),
        _sheet_set("Başka bir kitabın paleti", OTHER_PALETTE, samples,
                   only={"frame", "badge", "ribbon", "burst", "sign", "cloud", "scatter", "star"}),
    ]}
    png = el.typst_png(SHEET, data, 110)
    assert isinstance(png, list) or png.startswith(PNG)
    pages = png if isinstance(png, list) else [png]
    out = os.environ.get("ELEMENTS_SHEET")
    for i, pg in enumerate(pages):
        (tmp_path / f"sayfa-{i + 1}.png").write_bytes(pg)
        if out:
            p = Path(out)
            (p.parent / f"{p.stem}-{i + 1}{p.suffix}").write_bytes(pg)
