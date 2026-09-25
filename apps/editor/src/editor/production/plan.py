"""Sayfa planı (plan.json): iç sayfaların kalıcı kaydı. Sözleşme: docs/analiz/studyo-sayfa-plani-sozlesme.md.

Otomatik hat (run.py) sayfaları metnin akışından türetir (pagemap.json) ve resimleri sayfa numarasıyla tutar.
`freeze` bu akışı bir kez kalıcı sayfalara çevirir: her sayfa bir kimlik (p_…), her resim bir kimlik (a_…) alır;
`studio.json.pages["12"]` kaydı `studio.json.pages["a_…"]`'e taşınır, `artplan.scenes[].art_id` yazılır. Sonra iç
sayfalar `templates/plan.typ` ile dizilir. plan.json yoksa her şey eskisi gibi `book.typ`'den (geri uyum).

Dondurmada sayfa sınırından bölünen blok özgün dizgideki yerinden bölünür: o bloklar kelime kelime işaretlenerek
bir kez daha dizilir ve her kelimenin düştüğü sayfa okunur. Yazı kutusu özgün dizginin metin alanıyla aynı
genişlikte ve en az aynı yükseklikte olduğu için metin kutusuna sığar.

Yazımlar: her değişiklik `mutate` ile — dosya kilidi (API ve işçi ayrı süreç), `rev` denetimi (uyuşmazsa `Stale`),
dizgi (taşma işaretleri), uyarılar, atomik yazım, `plan-history/<rev>.json` (her sürüm, silinmez), provenance
satırı. Kapak (sayfa sayısı değiştiyse) ve ön kontrol yazımdan sonra arka planda yenilenir.

Kurallar kitaptan bağımsızdır. Otomatikler (palet, renkli yazı, balon) B işinin modüllerindedir (palette, colorize,
bubbles); modül yoksa o adım atlanır, plan yine kurulur.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import math
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import photo as photo_mod
from . import studio

PLAN = "plan.json"
HISTORY = "plan-history"
JOBS = "plan-jobs"
FRONT = 3                                  # plana girmeyen ön sayfalar: iç kapak, künye, yazar/çizer
FRONT_KEYS = ("ic_kapak", "kunye", "yazar_cizer")
LAYOUTS = ("art-top", "art-bottom", "art-full", "art-left", "art-right", "text-over-art", "text-only", "blank",
           "custom")
KINDS = ("para", "dialogue", "sound", "heading")
SHAPES = ("oval", "thought", "shout", "box")
ALIGNS = ("left", "justify", "center")
FITS = ("cover", "contain")
INK = "#2C2C2A"                            # gövde metni rengi (palet vermezse)
OVER_ART_BG = "#FFFFFFE6"                  # «yazı resmin üstünde» yerleşiminde yarı saydam kutu
ART_TOP = 0.52                             # resim bandı oranı (kitabın kendi oranı yoksa)
GAP = 9.0                                  # resim ile yazı arası (mm; book.typ'deki üst boşlukla aynı)
Z_FREE = 3                                 # figür ve serbest yazının en alt katmanı
HEX = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
ART_ID = re.compile(r"^a_[0-9a-f]{8}$")


class Stale(Exception):
    """İstemcinin bildiği `rev` güncel değil (başka biri ya da başka sekme yazdı)."""

    def __init__(self, rev: int):
        super().__init__(f"plan güncel değil (sunucuda sürüm {rev})")
        self.rev = rev


class NoPlan(FileNotFoundError):
    pass


class InUse(Exception):
    def __init__(self, pages: list[int]):
        super().__init__("kullanılıyor: " + ", ".join(f"{n}. sayfa" for n in pages))
        self.pages = pages


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ depo
def exists(d: Path) -> bool:
    return (d / PLAN).exists()


def load(d: Path) -> dict | None:
    return studio.read(d, PLAN)


@contextlib.contextmanager
def _locked(d: Path):
    """Plan yazımı tek sıra: API (iş parçacıkları) ve stüdyo işçisi (ayrı süreç) aynı dosya kilidini alır."""
    with open(d / "plan.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _commit(d: Path, plan: dict, by: str, what: str) -> None:
    plan["rev"] = int(plan.get("rev") or 0) + 1
    plan["updated_at"], plan["updated_by"] = _now(), by
    (d / HISTORY).mkdir(exist_ok=True)
    studio.write(d / HISTORY, f"{plan['rev']}.json",
                 {"rev": plan["rev"], "at": plan["updated_at"], "by": by, "what": what, "plan": plan})
    studio.write(d, PLAN, plan)
    with (d / "provenance.jsonl").open("a") as f:
        f.write(json.dumps({"kind": "plan", "rev": plan["rev"], "by": by, "what": what, "at": plan["updated_at"]},
                           ensure_ascii=False) + "\n")


def history(d: Path) -> list[dict]:
    out = []
    for p in (d / HISTORY).glob("*.json") if (d / HISTORY).exists() else []:
        h = json.loads(p.read_text())
        out.append({k: h.get(k) for k in ("rev", "at", "by", "what")})
    return sorted(out, key=lambda h: -h["rev"])


def mutate(d: Path, rev: int | None, by: str, what: str, fn, *, build: bool = True, post: str = "thread"):
    """Kilit → rev denetimi → `fn(plan)` → dizgi + uyarılar → yazım. Dönen: (plan, fn'in dönüşü).
    `rev` None ise denetlenmez (sunucu içi yazımlar: figür, geri yükleme)."""
    with _locked(d):
        plan = load(d)
        if plan is None:
            raise NoPlan(d.name)
        if rev is not None and int(rev) != int(plan["rev"]):
            raise Stale(plan["rev"])
        before = len(plan["pages"])
        out = fn(plan)
        _typeset(d, plan, build)
        _commit(d, plan, by, what)
    after_write(d, cover=len(plan["pages"]) != before, mode=post)
    return plan, out


# ------------------------------------------------------------------ geometri
def geometry(spec, layout=None) -> dict:
    """plan.json `page`: spec'ten kopya; `art_ratio` ve `body_size` kitabın yerleşiminden (hazır kutular ve
    varsayılan punto için)."""
    return {"w": spec.trim_w + 2 * spec.bleed, "h": spec.trim_h + 2 * spec.bleed, "bleed": spec.bleed,
            "safe": spec.safe, "gutter": spec.gutter,
            "art_ratio": (layout.art_ratio if layout and layout.art_ratio > 0 else ART_TOP),
            "body_size": layout.body_size if layout else spec.body_size}


def box(x: float, y: float, w: float, h: float) -> dict:
    return {"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2)}


def safe_rect(page: dict) -> tuple[float, float, float, float]:
    """Güvenli alan (x0, y0, x1, y1): kesimden `safe` kadar içeri."""
    m = page["bleed"] + page["safe"]
    return m, m, page["w"] - m, page["h"] - m


def inside_safe(bx: dict, page: dict, tol: float = 0.05) -> bool:
    x0, y0, x1, y1 = safe_rect(page)
    return (bx["x"] >= x0 - tol and bx["y"] >= y0 - tol and bx["x"] + bx["w"] <= x1 + tol
            and bx["y"] + bx["h"] <= y1 + tol)


def preset(layout: str, page: dict) -> dict | None:
    """Hazır yerleşimin kutuları: {"art": kutu|None, "text": kutu|None, "background": renk|None}. `custom` → None.
    Yazı iki yanda güvenli alan + cilt payı kadar içeride (sayfa sırası değişse de cilde girmez)."""
    if layout not in LAYOUTS:
        raise ValueError(f"bilinmeyen yerleşim: {layout}")
    if layout == "custom":
        return None
    W, H, b, s, g = page["w"], page["h"], page["bleed"], page["safe"], page["gutter"]
    mx, my = b + s + g, b + s
    ratio = page.get("art_ratio") or ART_TOP
    band = b + ratio * (H - 2 * b)
    tw = W - 2 * mx
    art = text = bg = None
    if layout == "art-top":
        art, text = box(0, 0, W, band), box(mx, band + GAP, tw, H - my - band - GAP)
    elif layout == "art-bottom":
        art, text = box(0, H - band, W, band), box(mx, my, tw, H - band - GAP - my)
    elif layout == "art-full":
        art = box(0, 0, W, H)
    elif layout == "art-left":
        art, text = box(0, 0, W / 2, H), box(W / 2 + GAP, my, W / 2 - GAP - mx, H - 2 * my)
    elif layout == "art-right":
        art, text = box(W / 2, 0, W / 2, H), box(mx, my, W / 2 - GAP - mx, H - 2 * my)
    elif layout == "text-over-art":
        th = 0.34 * (H - 2 * b)
        art, text, bg = box(0, 0, W, H), box(mx, H - my - th, tw, th), OVER_ART_BG
    elif layout == "text-only":
        text = box(mx, my, tw, H - 2 * my)
    return {"art": art, "text": text, "background": bg}


def _clamp_box(bx, page: dict, what: str) -> dict:
    """Kutu sayfanın (taşma payı dahil) içine alınır; en küçük kenar 1 mm."""
    try:
        x, y, w, h = (float(bx[k]) for k in ("x", "y", "w", "h"))
    except (TypeError, KeyError, ValueError):
        raise ValueError(f"{what}: kutu x, y, w, h (mm) ister") from None
    if not all(math.isfinite(v) for v in (x, y, w, h)):
        raise ValueError(f"{what}: kutu ölçüsü sayı olmalı")
    W, H = page["w"], page["h"]
    w, h = min(max(w, 1.0), W), min(max(h, 1.0), H)
    return box(min(max(x, 0.0), W - w), min(max(y, 0.0), H - h), w, h)


# ------------------------------------------------------------------ balon çizimi
def _ellipse(cx, cy, rx, ry, n=72, r=lambda t: 1.0):
    return [[round(cx + rx * r(t) * math.cos(t), 2), round(cy + ry * r(t) * math.sin(t), 2)]
            for t in (2 * math.pi * i / n for i in range(n))]


def bubble_shapes(bb: dict, size: float = 14.0) -> dict:
    """Balonun vektör çizimi (mm, sayfa koordinatı): dış çizgi, kuyruk, kuyruk dolgusu (dış çizginin kuyruk
    ağzındaki parçasını örter), düşünce balonunun noktaları ve metnin iç kutusu. İç kutu balon ölçüsünün
    hesabıyla (bubbles.bubble_size) aynı: kenarda 0,6 em pay, yuvarlak biçimlerde metin alanı OVAL kadar küçük."""
    from .bubbles import OVAL, PT_MM
    bx, shape = bb["box"], bb.get("shape") or "oval"
    x, y, w, h = bx["x"], bx["y"], bx["w"], bx["h"]
    cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
    pad = 0.6 * float(size) * PT_MM
    if shape == "box":
        rad = min(3.0, w / 4, h / 4)
        outline = []
        for (ax, ay, a0) in ((x + w - rad, y + rad, -90), (x + w - rad, y + h - rad, 0), (x + rad, y + h - rad, 90),
                             (x + rad, y + rad, 180)):
            outline += [[round(ax + rad * math.cos(math.radians(a0 + k * 15)), 2),
                         round(ay + rad * math.sin(math.radians(a0 + k * 15)), 2)] for k in range(7)]
        iw, ih = w - 2 * pad, h - 2 * pad
    else:
        if shape == "shout":
            outline = [[round(cx + rx * (1.0 if i % 2 == 0 else 0.84) * math.cos(math.pi * i / 16), 2),
                        round(cy + ry * (1.0 if i % 2 == 0 else 0.84) * math.sin(math.pi * i / 16), 2)]
                       for i in range(32)]
        elif shape == "thought":
            outline = _ellipse(cx, cy, rx, ry, 132, lambda t: 0.93 + 0.07 * abs(math.sin(5.5 * t)))
        else:
            outline = _ellipse(cx, cy, rx, ry)
        iw, ih = (w - 2 * pad) / OVAL, (h - 2 * pad) / OVAL
    iw, ih = max(iw, 1.0), max(ih, 1.0)
    inner = box(cx - iw / 2, cy - ih / 2, iw, ih)
    tail = tail_fill = None
    dots = []
    t = bb.get("tail")
    if t:
        dx, dy = t["x"] - cx, t["y"] - cy
        L = math.hypot(dx, dy)
        if L > 1e-6:
            ux, uy = dx / L, dy / L
            rb = (min(rx / abs(ux) if ux else math.inf, ry / abs(uy) if uy else math.inf) if shape == "box"
                  else 1 / math.sqrt((ux / rx) ** 2 + (uy / ry) ** 2))
            if L > rb:
                if shape == "thought":
                    for f, r in ((0.2, 2.2), (0.5, 1.5), (0.8, 1.0)):
                        dots.append([round(cx + ux * (rb + (L - rb) * f), 2), round(cy + uy * (rb + (L - rb) * f), 2), r])
                else:
                    px, py = -uy, ux
                    bc = (cx + ux * rb * 0.55, cy + uy * rb * 0.55)
                    hw = min(rx, ry) * 0.28
                    lt = L - rb * 0.55
                    tail = [[round(bc[0] + px * hw, 2), round(bc[1] + py * hw, 2)], [round(t["x"], 2), round(t["y"], 2)],
                            [round(bc[0] - px * hw, 2), round(bc[1] - py * hw, 2)]]
                    inset = 0.35
                    sc = min(rb * 0.45 + 1.0, lt * 0.9)          # dış çizginin kuyrukla kesiştiği yerin biraz ötesi
                    hc = hw * (1 - sc / lt) - inset
                    if hc > 0 and hw - inset > 0:
                        c = (bc[0] + ux * sc, bc[1] + uy * sc)
                        tail_fill = [[round(bc[0] + px * (hw - inset), 2), round(bc[1] + py * (hw - inset), 2)],
                                     [round(c[0] + px * hc, 2), round(c[1] + py * hc, 2)],
                                     [round(c[0] - px * hc, 2), round(c[1] - py * hc, 2)],
                                     [round(bc[0] - px * (hw - inset), 2), round(bc[1] - py * (hw - inset), 2)]]
    return {"outline": outline, "tail": tail, "tail_fill": tail_fill, "dots": dots, "inner": inner}


# ------------------------------------------------------------------ doğrulama
def _hex(v, what: str) -> str | None:
    if v in (None, ""):
        return None
    if not isinstance(v, str) or not HEX.match(v):
        raise ValueError(f"{what}: renk #RRGGBB biçiminde olmalı")
    return v.upper()


def _runs(runs, what: str) -> list[dict]:
    if not isinstance(runs, list):
        raise ValueError(f"{what}: runs listesi gerekli")
    out = []
    for r in runs:
        if not isinstance(r, dict) or not isinstance(r.get("text"), str):
            raise ValueError(f"{what}: her run'da text olmalı")
        o = {"text": r["text"]}
        if r.get("color") not in (None, ""):
            o["color"] = _hex(r["color"], what)
        if r.get("weight") is not None:
            wt = int(r["weight"])
            if not 100 <= wt <= 900:
                raise ValueError(f"{what}: kalınlık 100–900")
            o["weight"] = wt
        if r.get("size") is not None:
            sz = float(r["size"])
            if sz <= 0:
                raise ValueError(f"{what}: punto sıfırdan büyük olmalı")
            o["size"] = sz
        if r.get("font") is not None:
            if r["font"] not in ("body", "heading"):
                raise ValueError(f"{what}: yazı tipi body ya da heading")
            o["font"] = r["font"]
        if r.get("source") is not None:
            if r["source"] not in ("auto", "editor"):
                raise ValueError(f"{what}: source auto ya da editor")
            o["source"] = r["source"]
        out.append(o)
    return out


def _text_common(t: dict, page: dict, what: str) -> dict:
    align = t.get("align") or "left"
    if align not in ALIGNS:
        raise ValueError(f"{what}: hizalama {', '.join(ALIGNS)}")
    size = t.get("size")
    if size is not None and float(size) <= 0:
        raise ValueError(f"{what}: punto sıfırdan büyük olmalı")
    return {"box": _clamp_box(t.get("box"), page, what), "align": align,
            "size": float(size) if size is not None else None, "background": _hex(t.get("background"), what)}


def _clean_page(p: dict, plan: dict, old: dict | None = None) -> dict:
    """İstemcinin gönderdiği sayfa nesnesi → doğrulanmış, eksik kimlikleri tamamlanmış sayfa."""
    if not isinstance(p, dict):
        raise ValueError("sayfa nesnesi gerekli")
    page, assets = plan["page"], plan.get("assets", {})
    layout = p.get("layout") or (old or {}).get("layout") or "custom"
    if layout not in LAYOUTS:
        raise ValueError(f"bilinmeyen yerleşim: {layout}")
    out = {"id": p["id"], "chapter": p.get("chapter", (old or {}).get("chapter")), "layout": layout,
           "art": None, "text": None, "bubbles": [], "figures": [], "texts": [], "overflow": bool(p.get("overflow"))}
    a = p.get("art")
    if a:
        aid, gid = a.get("id"), a.get("asset")
        if aid is not None and not ART_ID.match(str(aid)):
            raise ValueError("resim kimliği a_ ile başlar")
        if gid is not None and gid not in assets:
            raise ValueError(f"kütüphanede yok: {gid}")
        if aid is None and gid is None:
            aid = new_id("a")
        fit = a.get("fit") or "cover"
        if fit not in FITS:
            raise ValueError("resim sığdırma cover ya da contain")
        foc = a.get("focus") or {}
        out["art"] = {"id": aid, "box": _clamp_box(a.get("box"), page, "resim"), "fit": fit,
                      "focus": {"x": min(max(float(foc.get("x", 0.5)), 0.0), 1.0),
                                "y": min(max(float(foc.get("y", 0.5)), 0.0), 1.0)}}
        if gid is not None:
            out["art"]["asset"] = gid
    t = p.get("text")
    if t:
        blocks = []
        for k in t.get("blocks") or []:
            kind = k.get("kind") or "para"
            if kind not in KINDS:
                raise ValueError(f"blok türü {', '.join(KINDS)}")
            blocks.append({"id": str(k.get("id") or new_id("k")), "kind": kind, "runs": _runs(k.get("runs"), "metin")})
        out["text"] = {**_text_common(t, page, "yazı kutusu"), "blocks": blocks}
    for bb in p.get("bubbles") or []:
        shape = bb.get("shape") or "oval"
        if shape not in SHAPES:
            raise ValueError(f"balon biçimi {', '.join(SHAPES)}")
        tail = bb.get("tail")
        if tail:
            tail = {"x": round(min(max(float(tail["x"]), 0.0), page["w"]), 2),
                    "y": round(min(max(float(tail["y"]), 0.0), page["h"]), 2)}
        o = {"id": str(bb.get("id") or new_id("b")), "speaker": bb.get("speaker"), "text": str(bb.get("text") or ""),
             "shape": shape, "box": _clamp_box(bb.get("box"), page, "balon"), "tail": tail,
             "color": _hex(bb.get("color"), "balon"), "source": bb.get("source") or "editor"}
        if bb.get("size") is not None:
            o["size"] = float(bb["size"])
        if bb.get("warning") and o["source"] == "auto":       # yerleşimin notu; editör taşıyınca düşer
            o["warning"] = str(bb["warning"])
        out["bubbles"].append(o)
    for f in p.get("figures") or []:
        if f.get("asset") not in assets:
            raise ValueError(f"kütüphanede yok: {f.get('asset')}")
        out["figures"].append({"id": str(f.get("id") or new_id("f")), "asset": f["asset"],
                               "box": _clamp_box(f.get("box"), page, "figür"),
                               "rotate": round(float(f.get("rotate") or 0) % 360, 2), "flip": bool(f.get("flip")),
                               "z": max(Z_FREE, int(f.get("z") or Z_FREE))})
    for x in p.get("texts") or []:
        out["texts"].append({"id": str(x.get("id") or new_id("t")), **_text_common(x, page, "serbest yazı"),
                             "runs": _runs(x.get("runs") or [], "serbest yazı"),
                             "z": max(Z_FREE, int(x.get("z") or Z_FREE))})
    return out


# ------------------------------------------------------------------ otomatikler (palette, colorize, bubbles)
def bubble_size(body: float) -> float:
    """Balon puntosu: gövde puntosunun iki altı (en az 10 pt); balon ölçüsü de bununla hesaplanır."""
    return max(10.0, float(body) - 2.0)


def _fallback_box(i: int, page: dict, art_box: dict | None) -> dict:
    """Yerleşim bir balona kutu veremediyse: güvenli alanın üst kenarına yan yana (editör taşır)."""
    x0, y0, x1, _ = safe_rect(page)
    top = max(y0, (art_box or {}).get("y", y0))
    w, h = min(60.0, (x1 - x0) * 0.45), 24.0
    return box(x0 + (i % 2) * (x1 - x0 - w), top + (i // 2) * (h + 4), w, h)


def suggest_bubbles(plan: dict, pg: dict, speakers: list[str], image_path, locate) -> list[dict]:
    """Sayfanın diyalog bloklarından balon önerisi (kaydetmez): konuşan, biçim, kutu, kuyruk."""
    from . import bubbles as bubbles_mod
    if not pg["text"]:
        return []
    _, bbs = bubbles_mod.from_dialogue(pg["text"]["blocks"], speakers)
    return _placed(plan, pg, bbs, image_path, locate)


def _placed(plan: dict, pg: dict, bbs: list[dict], image_path, locate) -> list[dict]:
    from . import bubbles as bubbles_mod
    if not bbs:
        return []
    size = bubble_size(plan["page"].get("body_size") or 14)
    placed = bubbles_mod.place(bbs, pg["art"], pg["text"]["box"] if pg["text"] else None, image_path,
                               locate or (lambda _p, _n: None), page=plan["page"], size=size)
    out = []
    for i, bb in enumerate(placed):
        o = {**bb, "size": bb.get("size") or size, "source": bb.get("source") or "auto"}
        if not o.get("box"):
            o["box"] = _fallback_box(i, plan["page"], (pg["art"] or {}).get("box"))
        c = _clean_page({"id": pg["id"], "bubbles": [o]}, plan)["bubbles"][0]
        if bb.get("warning"):
            c["warning"] = str(bb["warning"])
        out.append(c)
    return out


# ------------------------------------------------------------------ dondurma
def pages_from_flow(ms, spec, layout, marks: list[dict], art_ids: dict[int, str]) -> list[dict]:
    """Akış işaretlerinden (kelime işaretli geçiş) plan sayfaları. Saf: model ve dosya yok (sınanır)."""
    from .typeset import Typesetter, block_kind
    pm = Typesetter.from_marks(ms, marks, layout)
    page = geometry(spec, layout)
    W, H, b, s, g = page["w"], page["h"], page["bleed"], page["safe"], page["gutter"]
    arth = layout.art_ratio * spec.trim_h
    band = b + arth
    blocks = {f"c{ci}b{bi}": blk for ci, bi, blk in ms.blocks()}
    heads = {m["page"]: m["ci"] for m in marks if m["kind"] == "chapter"}
    spans: dict[str, list[int]] = {}
    for p in pm.pages:
        for bid in p.blocks:
            spans.setdefault(bid, []).append(p.no)
    words: dict[str, dict[int, list[int]]] = {}
    for m in marks:
        if m["kind"] == "w":
            words.setdefault(m["id"], {}).setdefault(m["page"], []).append(m["i"])
    painted = pm.art_pages()
    out = []
    for p in pm.pages:
        if p.kind == "front" and p.key in FRONT_KEYS:
            continue
        pg = {"id": new_id("p"), "chapter": p.chapter, "layout": "blank", "art": None, "text": None, "bubbles": [],
              "figures": [], "texts": [], "overflow": False}
        if p.kind == "full":
            pg["layout"] = "art-full"
            pg["art"] = {"id": art_ids.get(p.no) or new_id("a"), "box": box(0, 0, W, H), "fit": "cover",
                         "focus": {"x": 0.5, "y": 0.5}}
        elif p.kind == "flow":
            ks = []
            ci = heads.get(p.no)
            if ci is not None and ms.chapters[ci].title:
                ks.append({"id": f"h{ci}", "kind": "heading", "runs": [{"text": ms.chapters[ci].title}]})
            for bid in p.blocks:
                src, span = blocks[bid], spans[bid]
                if len(span) > 1 and bid in words:
                    toks = src.text.split(" ")
                    piece = " ".join(toks[i] for i in sorted(words[bid].get(p.no, [])))
                else:
                    piece = src.text if span[0] == p.no else ""
                if piece.strip():
                    n = span.index(p.no)
                    ks.append({"id": bid if n == 0 else f"{bid}-{n + 1}", "kind": block_kind(src.kind, src.text),
                               "runs": [{"text": piece}]})
            if ks:
                recto = p.no % 2 == 1                    # sol cilt: tek sayfa sağda, cilt payı solda
                top = band + GAP if arth > 0 else b + s
                pg["text"] = {"box": box(b + s + (g if recto else 0), top, W - 2 * b - 2 * s - g, H - b - s - top),
                              "align": "justify" if spec.justify else "left", "size": None, "background": None,
                              "blocks": ks}
                pg["layout"] = "text-only"
            if p.no in painted and arth > 0:
                pg["layout"] = "art-top" if ks else "custom"
                pg["art"] = {"id": art_ids.get(p.no) or new_id("a"), "box": box(0, 0, W, band), "fit": "cover",
                             "focus": {"x": 0.5, "y": 0.5}}
        out.append(pg)
    return out


def _flow_marks(d: Path, ms, spec, pm, front) -> list[dict]:
    """Özgün yerleşimle bir kez daha dizer; sayfa sınırından bölünen blokların kelimeleri işaretli."""
    from .typeset import Typesetter, book_data
    spans: dict[str, int] = {}
    for p in pm.pages:
        for bid in p.blocks:
            spans[bid] = spans.get(bid, 0) + 1
    split = sorted(b for b, n in spans.items() if n > 1)
    ts = Typesetter(d / "dizgi" / "plan-dondurma", studio.fonts())
    return ts.marks(book_data(ms, spec, pm.layout, front, {}, wordmarks=split))


def freeze(d: Path, by: str, *, build: bool = True, locate=None, marks: list[dict] | None = None) -> dict:
    """plan.json yoksa kurar (varsa dokunmaz, aynısını döner). `locate`: balonu konuşana yöneltmek için görsel
    okuyucu (stüdyo işçisinde verilir; API'den gelen dondurmada yok, balon yerleşimi kuralla)."""
    with _locked(d):
        cur = load(d)
        if cur is not None:
            return cur
        ms, spec, pm = studio._manuscript(d), studio._spec(d), studio._pagemap(d)
        front = studio.read(d, "front.json")
        ap = studio.read(d, "artplan.json") or {"style": {}, "characters": [], "scenes": []}
        if marks is None:
            marks = _flow_marks(d, ms, spec, pm, front)
        from .typeset import Typesetter
        pm2 = Typesetter.from_marks(ms, marks, pm.layout)
        warn = [] if len(pm2.pages) == len(pm.pages) else [
            f"Dondurmada sayfa bölünmesi özgün dizgiden farklı çıktı ({len(pm.pages)} → {len(pm2.pages)} sayfa)."]
        # Resim kimliği göçü. Plan yazılamazsa göç geri alınır: plan.json yokken eski yol (book.typ) resmi sayfa
        # numarasıyla arar. Yarıda kalan dondurma yeniden koşarsa artplan'daki kimlikler yeniden kullanılır.
        ap0, st0 = json.loads(json.dumps(ap)), studio.studio_state(d)
        painted = pm2.art_pages()
        art_ids = {}
        for sc in ap["scenes"]:
            if sc["page"] in painted:
                sc["art_id"] = sc.get("art_id") or new_id("a")
                art_ids[sc["page"]] = sc["art_id"]
        st = json.loads(json.dumps(st0))
        for no, aid in art_ids.items():
            if str(no) in st["pages"] and aid not in st["pages"]:
                st["pages"][aid] = st["pages"].pop(str(no))
        studio.write(d, "artplan.json", ap)
        studio.write(d, "studio.json", st)
        try:
            pages = pages_from_flow(ms, spec, pm.layout, marks, art_ids)
            plan = {"version": 1, "rev": 0, "frozen_at": _now(), "frozen_by": by,
                    "page": geometry(spec, pm.layout), "palette": {"colors": [], "text": INK, "characters": {}},
                    "pages": pages, "assets": {}, "warnings": warn}
            _automatics(d, plan, ap, locate)
            _typeset(d, plan, build)
            plan["warnings"] = warn + [w for w in plan["warnings"] if w not in warn]
            _commit(d, plan, by, "sayfa planı kuruldu")
        except BaseException:
            studio.write(d, "artplan.json", ap0)
            studio.write(d, "studio.json", st0)
            (d / PLAN).unlink(missing_ok=True)
            raise
    return plan


def _automatics(d: Path, plan: dict, ap: dict, locate) -> None:
    """Palet (her kitap: resimlerden, baskıya uygun), karakter renkleri; çocuk profilinde (bubbles.wanted)
    diyalog → balon ve renkli yazı (ses sözcüğü, karakter adı)."""
    from . import bubbles as bubbles_mod
    from . import colorize, palette
    sel = studio.selected_art(d)
    paths = [Path(sel[pg["art"]["id"]]) for pg in plan["pages"] if pg["art"] and pg["art"]["id"] in sel]
    chars = ap.get("characters") or []
    colors = palette.extract(paths, n=6)
    plan["palette"] = {"colors": colors, "text": INK,
                       "characters": palette.assign_characters(chars, colors) if chars else {}}
    if not bubbles_mod.wanted(studio.read(d, "profile.json")):
        return
    names = [c["name"] for c in chars]
    for pg in plan["pages"]:
        if not pg["text"]:
            continue
        blocks, bbs = bubbles_mod.from_dialogue(pg["text"]["blocks"], names)
        pg["text"]["blocks"] = blocks
        pg["bubbles"] = _placed(plan, pg, bbs, sel.get(pg["art"]["id"]) if pg["art"] else None, locate)
        pg["text"]["blocks"] = colorize.apply(pg["text"]["blocks"], plan["palette"]["characters"], plan["palette"],
                                              body_size=plan["page"].get("body_size"))


# ------------------------------------------------------------------ dizgi
def _link(src: Path, dst: Path) -> None:
    """Dizgi klasörüne sabit bağ (Typst kökü dizgi/); yoksa kopya."""
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        dst.hardlink_to(src)
    except OSError:
        import shutil
        shutil.copy(src, dst)


def _px(path: Path, cache: dict) -> tuple[int, int]:
    if path not in cache:
        from PIL import Image
        with Image.open(path) as im:
            cache[path] = im.size
    return cache[path]


def _asset_src(d: Path, plan: dict, gid: str) -> Path:
    return d / plan["assets"][gid]["path"]


def render_data(d: Path, plan: dict) -> dict:
    """plan.typ'nin verisi: sayfa başına hazır kutular, yollar (dizgi köküne göre), kırpma ve balon çizimleri."""
    ms, spec = studio._manuscript(d), studio._spec(d)
    pm = studio.read(d, "pagemap.json") or {}
    accent = (pm.get("layout") or {}).get("accent") or ((studio.read(d, "artplan.json") or {}).get("style") or {}).get(
        "accent") or "#264653"
    dz = d / "dizgi"
    sel = studio.selected_art(d)
    pal = plan.get("palette") or {}
    ink = pal.get("text") or INK
    body = plan["page"].get("body_size") or spec.body_size
    px: dict = {}

    def art_item(a):
        bx = a["box"]
        src = rel = None
        if a.get("asset") and a["asset"] in plan["assets"]:
            src = _asset_src(d, plan, a["asset"])
            rel = plan["assets"][a["asset"]]["path"]
        elif a.get("id") in sel:
            src = Path(sel[a["id"]])
            rel = f"resim/{src.name}"
        if src is None or not src.exists():
            return {"box": bx, "path": None, "fit": a["fit"], "label": "Resim bekliyor", "iw": 0, "ih": 0, "dx": 0,
                    "dy": 0}
        _link(src, dz / rel)
        pw, ph = _px(src, px)
        k = max(bx["w"] / pw, bx["h"] / ph)
        iw, ih = pw * k, ph * k
        return {"box": bx, "path": rel, "fit": a["fit"], "label": "", "iw": round(iw, 3), "ih": round(ih, 3),
                "dx": round(-(iw - bx["w"]) * a["focus"]["x"], 3), "dy": round(-(ih - bx["h"]) * a["focus"]["y"], 3)}

    def text_item(t, ink_=ink, **extra):
        return {"box": t["box"], "align": t.get("align") or "left", "size": t.get("size") or body, "ink": ink_,
                "background": t.get("background"), "pad": 3 if t.get("background") else 0, "valign": "top",
                "leading": None, **extra}

    pages = []
    for pg in plan["pages"]:
        items = []
        for f in pg["figures"]:
            if f["asset"] not in plan["assets"]:
                continue
            rel = plan["assets"][f["asset"]]["path"]
            _link(_asset_src(d, plan, f["asset"]), dz / rel)
            items.append({"type": "figure", "id": f["id"], "box": f["box"], "rotate": f["rotate"], "flip": f["flip"],
                          "path": rel, "z": f["z"]})
        for x in pg["texts"]:
            items.append({"type": "text", "id": x["id"], "z": x["z"], **text_item(x, runs=x["runs"])})
        items.sort(key=lambda it: it["z"])
        bubbles = []
        for bb in pg["bubbles"]:
            size = bb.get("size") or bubble_size(body)
            sh = bubble_shapes(bb, size)
            color = bb.get("color") or (pal.get("characters") or {}).get(bb.get("speaker") or "") or ink
            # Balonda satır adımı 1,25 em (bubbles.LINE_EM: balon ölçüsü bununla hesaplanır), metin dikeyde ortada.
            bubbles.append({"id": bb["id"], "outline": sh["outline"], "tail": sh["tail"], "tail_fill": sh["tail_fill"],
                            "dots": sh["dots"], "stroke": ink,
                            "text": text_item({"box": sh["inner"], "align": "center", "size": size}, color,
                                              runs=[{"text": bb["text"]}], valign="horizon", leading=0.55)})
        t = pg["text"]
        pages.append({"id": pg["id"], "art": art_item(pg["art"]) if pg["art"] else None,
                      "text": text_item(t, blocks=t["blocks"]) if t else None, "bubbles": bubbles, "items": items,
                      "folio": t is not None})
    fr = studio.read(d, "front.json")
    return {"book": {"title": ms.title, "author": ms.author or "", "publisher": ms.meta.get("PUBLISHER") or ""},
            "spec": spec.to_json(), "front": fr, "accent": accent, "body_size": body, "pages": pages}


def build_pdf(d: Path, plan: dict) -> dict:
    """İç sayfa PDF'i plan.typ ile (ön sayfalar dahil bütün kitap). Dönen: taşma işaretleri ve süre."""
    from . import preflight
    from .typeset import PLAN_TEMPLATE, Typesetter
    t = time.time()
    spec = studio._spec(d)
    ts = Typesetter(d / "dizgi", studio.fonts(), PLAN_TEMPLATE)
    tmp, marks = ts.build(render_data(d, plan), "ic-sayfalar.pdf")
    preflight.set_boxes(tmp, spec.bleed)
    os.replace(tmp, d / "dizgi" / "ic-sayfalar.pdf")
    prev = d / "dizgi" / "onizleme"
    for f in prev.glob("*.png") if prev.exists() else []:
        f.unlink(missing_ok=True)
    return {"overflow": [m for m in marks if m["kind"] == "overflow"], "seconds": round(time.time() - t, 2)}


def _typeset(d: Path, plan: dict, build: bool) -> None:
    """Dizer, taşma işaretlerini sayfalara yazar, uyarıları yeniler. Dizgi hatası yazımı durdurmaz: değişiklik
    kaydedilir, uyarı düşer, ayrıntı hata-plan.txt'de."""
    extra = []
    if build:
        try:
            res = build_pdf(d, plan)
            apply_overflow(plan, res["overflow"])
            plan["built_seconds"] = res["seconds"]
        except Exception as e:  # noqa: BLE001 - değişiklik kaybolmaz; ekranda uyarı
            import traceback
            (d / "hata-plan.txt").write_text("".join(traceback.format_exception(type(e), e, e.__traceback__)))
            extra.append("Dizgi yapılamadı; değişiklik kaydedildi, bir sonraki kayıtta yeniden denenecek.")
    plan["warnings"] = warnings(d, plan) + extra


def apply_overflow(plan: dict, marks: list[dict]) -> None:
    over: dict[str, set] = {}
    for m in marks:
        over.setdefault(m["page"], set()).add((m["what"], m["id"]))
    for pg in plan["pages"]:
        o = over.get(pg["id"], set())
        pg["overflow"] = ("text", pg["id"]) in o
        for bb in pg["bubbles"]:
            bb["overflow"] = ("bubble", bb["id"]) in o
        for x in pg["texts"]:
            x["overflow"] = ("free", x["id"]) in o


def page_no(plan: dict, pid: str) -> int:
    return FRONT + index(plan, pid) + 1


def index(plan: dict, pid: str) -> int:
    for i, pg in enumerate(plan["pages"]):
        if pg["id"] == pid:
            return i
    raise KeyError(pid)


def low_dpi(d: Path, plan: dict) -> list[tuple[int, str, int]]:
    """Kutusunda 300 dpi'nin altında basılacak görseller: (sayfa no, tür, dpi). Tür: fotoğraf | figür | resim."""
    sel, px, out = studio.selected_art(d), {}, []

    def check(no, src, bx, fit, kind):
        if src is None or not src.exists():
            return
        v = photo_mod.dpi(*_px(src, px), bx, fit)
        if v and round(v) < photo_mod.LOW_DPI:
            out.append((no, kind, int(round(v))))

    for i, pg in enumerate(plan["pages"]):
        no = FRONT + i + 1
        a = pg["art"]
        if a:
            if a.get("asset") in plan["assets"]:
                kind = "fotoğraf" if plan["assets"][a["asset"]]["kind"] == "photo" else "figür"
                check(no, _asset_src(d, plan, a["asset"]), a["box"], a["fit"], kind)
            elif a.get("id") in sel:
                check(no, Path(sel[a["id"]]), a["box"], a["fit"], "resim")
        for f in pg["figures"]:
            if f["asset"] in plan["assets"]:
                kind = "fotoğraf" if plan["assets"][f["asset"]]["kind"] == "photo" else "figür"
                check(no, _asset_src(d, plan, f["asset"]), f["box"], "contain", kind)
    return out


def warnings(d: Path | None, plan: dict) -> list[str]:
    page = plan["page"]
    spec = studio._spec(d) if d is not None else None
    sig = spec.signature if spec else 8
    out = []
    total = FRONT + len(plan["pages"])
    if total % sig:
        out.append(f"Sayfa sayısı {sig}'in katı değil: {sig - total % sig} sayfa eksik.")
    for i, pg in enumerate(plan["pages"]):
        no = FRONT + i + 1
        if pg["text"] and not inside_safe(pg["text"]["box"], page):
            out.append(f"{no}. sayfa: yazı kutusu güvenli alanın dışına taşıyor.")
        if any(not inside_safe(bb["box"], page) for bb in pg["bubbles"]):
            out.append(f"{no}. sayfa: balon güvenli alanın dışına taşıyor.")
        if any(not inside_safe(x["box"], page) for x in pg["texts"]):
            out.append(f"{no}. sayfa: serbest yazı güvenli alanın dışına taşıyor.")
        if pg.get("overflow"):
            out.append(f"{no}. sayfa: metin kutusuna sığmıyor (kutuyu büyütün, puntoyu küçültün ya da sonraki "
                       "sayfaya taşıyın).")
        if any(bb.get("overflow") for bb in pg["bubbles"]):
            out.append(f"{no}. sayfa: balon metni balona sığmıyor.")
        for msg in dict.fromkeys(bb["warning"] for bb in pg["bubbles"] if bb.get("warning")):
            out.append(f"{no}. sayfa: {msg}")
        if any(x.get("overflow") for x in pg["texts"]):
            out.append(f"{no}. sayfa: serbest yazı kutusuna sığmıyor.")
    if d is not None:
        for no, kind, v in low_dpi(d, plan):
            out.append(f"{no}. sayfa: {kind} baskıda bulanık çıkabilir ({v} dpi).")
    return out


# ------------------------------------------------------------------ yazımlar
def _page(plan: dict, pid: str) -> dict:
    try:
        return plan["pages"][index(plan, pid)]
    except KeyError:
        raise KeyError(f"sayfa yok: {pid}") from None


def _apply_preset(pg: dict, layout: str, page: dict) -> None:
    pr = preset(layout, page)
    if pr is None:
        return
    if pr["text"] is None and pg["text"] and any(r["text"].strip() for k in pg["text"]["blocks"] for r in k["runs"]):
        raise ValueError("Bu sayfada metin var; önce metni başka sayfaya taşıyın ya da «yazı resmin üstünde» "
                         "yerleşimini seçin")
    if pr["art"]:
        pg["art"] = {**(pg["art"] or {"id": new_id("a"), "fit": "cover", "focus": {"x": 0.5, "y": 0.5}}),
                     "box": pr["art"]}
    else:
        pg["art"] = None                   # resim kütüphanede kalır («kullanılmayan resimler»)
    if pr["text"]:
        pg["text"] = {**(pg["text"] or {"align": "left", "size": None, "blocks": []}), "box": pr["text"],
                      "background": pr["background"]}
    else:
        pg["text"] = None
    pg["layout"] = layout


def update_page(d: Path, pid: str, rev: int, page: dict, by: str, **kw) -> tuple[dict, dict]:
    """Sayfayı istemcinin gönderdiğiyle değiştirir. Yerleşim değiştiyse (custom dışı) hazır kutular uygulanır."""
    def fn(plan):
        i = index(plan, pid)
        old = plan["pages"][i]
        new = _clean_page({**page, "id": pid}, plan, old)
        if new["layout"] != old["layout"] and new["layout"] != "custom":
            _apply_preset(new, new["layout"], plan["page"])
        plan["pages"][i] = new
        return new
    return mutate(d, rev, by, f"sayfa düzenlendi ({pid})", fn, **kw)


def insert_page(d: Path, rev: int, after: str | None, layout: str, by: str, **kw) -> tuple[dict, dict]:
    def fn(plan):
        i = index(plan, after) + 1 if after else 0
        prev = plan["pages"][i - 1] if i > 0 else None
        pg = {"id": new_id("p"), "chapter": prev["chapter"] if prev else None, "layout": "blank", "art": None,
              "text": None, "bubbles": [], "figures": [], "texts": [], "overflow": False}
        _apply_preset(pg, layout, plan["page"])
        plan["pages"].insert(i, pg)
        return pg
    return mutate(d, rev, by, f"sayfa eklendi ({layout})", fn, **kw)


def delete_page(d: Path, pid: str, rev: int, by: str, **kw) -> tuple[dict, dict]:
    """Sayfa silinir; resmi studio.json'da kalır («kullanılmayan resimler»), figürleri kütüphanede kalır."""
    def fn(plan):
        return plan["pages"].pop(index(plan, pid))
    return mutate(d, rev, by, f"sayfa silindi ({pid})", fn, **kw)


def order(d: Path, rev: int, ids: list[str], by: str, **kw) -> tuple[dict, None]:
    def fn(plan):
        cur = [p["id"] for p in plan["pages"]]
        if len(ids) != len(cur) or set(ids) != set(cur):
            raise ValueError("sıralama bütün sayfaların kimliklerini birer kez içermeli")
        by_id = {p["id"]: p for p in plan["pages"]}
        plan["pages"] = [by_id[i] for i in ids]
    return mutate(d, rev, by, "sayfalar sıralandı", fn, **kw)


def _cut_runs(runs: list[dict], at: int) -> tuple[list[dict], list[dict]]:
    head, tail, pos = [], [], 0
    for r in runs:
        n = len(r["text"])
        if pos + n <= at:
            head.append(r)
        elif pos >= at:
            tail.append(r)
        else:
            head.append({**r, "text": r["text"][:at - pos]})
            tail.append({**r, "text": r["text"][at - pos:]})
        pos += n
    if head:
        head[-1] = {**head[-1], "text": head[-1]["text"].rstrip()}
    if tail:
        tail[0] = {**tail[0], "text": tail[0]["text"].lstrip()}
    return [r for r in head if r["text"]], [r for r in tail if r["text"]]


def split_page(d: Path, pid: str, rev: int, block: str, at: int, by: str, **kw) -> tuple[dict, list[dict]]:
    """«Sonraki sayfaya taşı»: `block` bloğunun `at`. karakterinden sonrası ve ardından gelen bloklar yeni sayfaya
    (yazı sayfası, aynı hizalama ve punto) geçer."""
    def fn(plan):
        i = index(plan, pid)
        pg = plan["pages"][i]
        if not pg["text"]:
            raise ValueError("bu sayfada metin yok")
        ks = pg["text"]["blocks"]
        k = next((j for j, b in enumerate(ks) if b["id"] == block), None)
        if k is None:
            raise ValueError(f"blok yok: {block}")
        full = "".join(r["text"] for r in ks[k]["runs"])
        if not 0 <= at <= len(full):
            raise ValueError("bölme yeri bloğun içinde olmalı")
        head, tail = _cut_runs(ks[k]["runs"], at)
        first = ks[:k] + ([{**ks[k], "runs": head}] if head else [])
        rest = ([{**ks[k], "id": new_id("k"), "runs": tail}] if tail else []) + ks[k + 1:]
        if not rest:
            raise ValueError("taşınacak metin yok")
        pg["text"]["blocks"] = first
        new = {"id": new_id("p"), "chapter": pg["chapter"], "layout": "blank", "art": None, "text": None,
               "bubbles": [], "figures": [], "texts": [], "overflow": False}
        _apply_preset(new, "text-only", plan["page"])
        new["text"].update(align=pg["text"]["align"], size=pg["text"]["size"], blocks=rest)
        plan["pages"].insert(i + 1, new)
        return [pg, new]
    return mutate(d, rev, by, f"sayfa bölündü ({pid})", fn, **kw)


def set_palette(d: Path, rev: int, palette: dict, by: str, **kw) -> tuple[dict, None]:
    """Paleti değiştirir. Bir karakterin rengi değiştiyse otomatik kuralın o renkle boyadığı yazı da yeni renge
    geçer; editörün elle verdiği renk (source=editor) değişmez."""
    colors = []
    for c in palette.get("colors") or []:
        colors.append({"name": str(c.get("name") or ""), "hex": _hex(c.get("hex"), "palet"),
                       "source": c.get("source") or "editor"})
    if any(c["hex"] is None for c in colors):
        raise ValueError("palet rengi boş olamaz")
    new = {"colors": colors, "text": _hex(palette.get("text"), "metin rengi") or INK,
           "characters": {str(k): _hex(v, f"karakter rengi ({k})") for k, v in (palette.get("characters") or {}).items()
                          if v}}

    def fn(plan):
        old = (plan.get("palette") or {}).get("characters") or {}
        counts: dict[str, int] = {}
        for v in old.values():
            counts[v] = counts.get(v, 0) + 1
        remap = {v: new["characters"][k] for k, v in old.items()
                 if k in new["characters"] and new["characters"][k] != v and counts[v] == 1}
        for pg in plan["pages"]:
            for k in (pg["text"] or {}).get("blocks", []):
                for r in k["runs"]:
                    if r.get("source") == "auto" and r.get("color") in remap:
                        r["color"] = remap[r["color"]]
        plan["palette"] = new
    return mutate(d, rev, by, "palet değişti", fn, **kw)


def restore(d: Path, rev: int, by: str, **kw) -> tuple[dict, None]:
    """Eski sürümü yeni sürüm olarak geri yükler. Kütüphane (figür/fotoğraf) birleşir: sonradan eklenen
    varlık kaybolmaz."""
    p = d / HISTORY / f"{int(rev)}.json"
    if not p.exists():
        raise KeyError(f"sürüm yok: {rev}")
    old = json.loads(p.read_text())["plan"]

    def fn(plan):
        assets = {**plan.get("assets", {}), **old.get("assets", {})}
        cur = plan["rev"]
        plan.clear()
        plan.update(old)
        plan["assets"], plan["rev"] = assets, cur
        plan["restored_from"] = int(rev)
    return mutate(d, None, by, f"{int(rev)}. sürüm geri yüklendi", fn, **kw)


def _default_figure_box(page: dict, w_px: int, h_px: int, share: float) -> dict:
    x0, y0, x1, y1 = safe_rect(page)
    w = (x1 - x0) * share
    h = w * h_px / max(1, w_px)
    if h > (y1 - y0) * 0.6:
        h = (y1 - y0) * 0.6
        w = h * w_px / max(1, h_px)
    return box((page["w"] - w) / 2, (page["h"] - h) / 2, w, h)


def add_asset(d: Path, gid: str, meta: dict, page: str | None, by: str, *, share: float = 0.4,
              **kw) -> tuple[dict, dict | None]:
    """Kütüphaneye varlık (figür/fotoğraf) ekler; `page` verildiyse o sayfaya en üst katmanda, güvenli alanın
    ortasında figür olarak konur. Dönen ikinci değer eklenen figür (ya da None)."""
    def fn(plan):
        plan.setdefault("assets", {})[gid] = meta
        if not page:
            return None
        pg = _page(plan, page)
        z = max([f["z"] for f in pg["figures"]] + [x["z"] for x in pg["texts"]] + [Z_FREE - 1]) + 1
        f = {"id": new_id("f"), "asset": gid, "box": _default_figure_box(plan["page"], meta["w_px"], meta["h_px"], share),
             "rotate": 0, "flip": False, "z": z}
        pg["figures"].append(f)
        return f
    return mutate(d, None, by, f"kütüphaneye eklendi ({meta.get('kind')} {gid})", fn, **kw)


def add_photo(d: Path, data: bytes, filename: str, page: str | None, by: str, **kw) -> tuple[str, dict, dict]:
    """Yüklenen fotoğraf: EXIF yönü, sRGB, üst veri silinmiş (photo.ingest) → foto/<gid>.<ext> → kütüphane."""
    if not exists(d):
        raise NoPlan(d.name)
    info = photo_mod.ingest(data, filename)
    gid = new_id("g")
    rel = f"foto/{gid}.{info['ext']}"
    (d / "foto").mkdir(exist_ok=True)
    tmp = d / (rel + ".tmp")
    tmp.write_bytes(info["bytes"])
    tmp.replace(d / rel)
    meta = {"kind": "photo", "path": rel, "w_px": info["w_px"], "h_px": info["h_px"], "alpha": info["alpha"],
            "name": Path(filename).name[:200], "by": by, "at": _now()}
    plan, fig = add_asset(d, gid, meta, page, by, share=0.6, **kw)
    return gid, meta, {"plan": plan, "figure": fig}


def delete_asset(d: Path, gid: str, rev: int, by: str, **kw) -> tuple[dict, None]:
    """Kütüphaneden çıkarır (dosya diskte kalır, geçmişten geri gelir). Bir sayfada kullanılıyorsa `InUse`."""
    def fn(plan):
        if gid not in plan.get("assets", {}):
            raise KeyError(f"kütüphanede yok: {gid}")
        used = [FRONT + i + 1 for i, pg in enumerate(plan["pages"])
                if any(f["asset"] == gid for f in pg["figures"]) or (pg["art"] or {}).get("asset") == gid]
        if used:
            raise InUse(used)
        plan["assets"].pop(gid)
    return mutate(d, rev, by, f"kütüphaneden çıkarıldı ({gid})", fn, **kw)


# ------------------------------------------------------------------ okuma
def art_at(plan: dict, no: int) -> str | None:
    """Sayfa numarasındaki resmin kimliği (eski ekranın numarayla gelen isteği için)."""
    i = no - FRONT - 1
    if 0 <= i < len(plan["pages"]) and plan["pages"][i]["art"]:
        return plan["pages"][i]["art"].get("id")
    return None


def page_of_art(plan: dict, aid: str) -> tuple[int | None, dict | None]:
    for i, pg in enumerate(plan["pages"]):
        if pg["art"] and pg["art"].get("id") == aid:
            return FRONT + i + 1, pg
    return None, None


def printed_art(plan: dict) -> list[tuple[int, str]]:
    """Basılan (sayfada, fotoğrafla değiştirilmemiş) resimler: (sayfa no, resim kimliği)."""
    return [(FRONT + i + 1, pg["art"]["id"]) for i, pg in enumerate(plan["pages"])
            if pg["art"] and pg["art"].get("id") and not pg["art"].get("asset")]


def unused_art(d: Path, plan: dict) -> list[dict]:
    used = {pg["art"].get("id") for pg in plan["pages"] if pg["art"]}
    out = []
    for key, pg in studio.studio_state(d)["pages"].items():
        if ART_ID.match(key) and key not in used:
            out.append({"id": key, "selected": pg.get("selected"), "approved": pg.get("approved", False),
                        "versions": len(pg.get("versions", []))})
    return out


def page_text(pg: dict) -> str:
    return "\n".join("".join(r["text"] for r in k["runs"]) for k in (pg["text"] or {}).get("blocks", []))


class PlanText:
    """Ön kontrolün «Metin eksiksiz» karşılaştırması için planın metni (dizilme sırasıyla): sayfa metni,
    balonlar, serbest yazılar."""

    def __init__(self, plan: dict):
        self.plan = plan

    def text(self) -> str:
        parts = []
        for pg in self.plan["pages"]:
            parts.append(page_text(pg))
            parts += [bb["text"] for bb in pg["bubbles"]]
            parts += ["".join(r["text"] for r in x["runs"]) for x in sorted(pg["texts"], key=lambda x: x["z"])]
        return "\n\n".join(p for p in parts if p)


def placement(plan: dict, pid: str, item: str) -> tuple[dict, str, str]:
    """Sayfadaki bir görselin (kutu, sığdırma, varlık kimliği). `item`: figür kimliği ya da «art»."""
    pg = _page(plan, pid)
    if item == "art":
        if not pg["art"] or not pg["art"].get("asset"):
            raise KeyError("sayfa resmi bir fotoğraf değil")
        return pg["art"]["box"], pg["art"]["fit"], pg["art"]["asset"]
    f = next((f for f in pg["figures"] if f["id"] == item), None)
    if f is None:
        raise KeyError(f"sayfada yok: {item}")
    return f["box"], "contain", f["asset"]


def preview(d: Path, pid: str, width: int) -> Path:
    plan = load(d)
    if plan is None:
        raise NoPlan(d.name)
    return studio.page_preview(d, page_no(plan, pid), width)


# ------------------------------------------------------------------ GPU/uzun işlerin kaydı (ekran bekler)
def job_record(d: Path, jid: str, **fields) -> dict:
    (d / JOBS).mkdir(exist_ok=True)
    rec = {**(studio.read(d / JOBS, f"{jid}.json") or {"id": jid, "created": _now()}), **fields, "updated": _now()}
    studio.write(d / JOBS, f"{jid}.json", rec)
    return rec


def jobs(d: Path) -> list[dict]:
    out = [json.loads(p.read_text()) for p in (d / JOBS).glob("*.json")] if (d / JOBS).exists() else []
    return sorted(out, key=lambda r: r.get("created", ""), reverse=True)


# ------------------------------------------------------------------ yazım sonrası (kapak, ön kontrol)
_post: dict[str, dict] = {}
_post_lock = threading.Lock()


def after_write(d: Path, cover: bool, mode: str = "thread") -> None:
    """Kapak (sayfa sayısı değiştiyse: sırt kalınlığı) ve ön kontrol. «thread»: arka planda, iş başına tek sıra;
    art arda gelen yazımlar birleşir. «sync»: hemen (işçi, sınama). «none»: yapılmaz."""
    if mode == "none":
        return
    if mode == "sync":
        _post_run_once(d, cover)
        return
    with _post_lock:
        st = _post.setdefault(d.name, {"cover": False, "running": False, "again": False})
        st["cover"] = st["cover"] or cover
        if st["running"]:
            st["again"] = True
            return
        st["running"] = True
    threading.Thread(target=_post_loop, args=(d,), daemon=True).start()


def _post_loop(d: Path) -> None:
    while True:
        with _post_lock:
            st = _post[d.name]
            cover, st["cover"], st["again"] = st["cover"], False, False
        _post_run_once(d, cover)
        with _post_lock:
            if not st["again"]:
                st["running"] = False
                return


def _post_run_once(d: Path, cover: bool) -> None:
    try:
        if cover:
            studio.build_cover(d)
        studio.refresh_preflight(d)
    except Exception:  # noqa: BLE001 - ön kontrol bir sonraki yazımda yenilenir
        import traceback
        (d / "hata-plan.txt").write_text(traceback.format_exc())


# ------------------------------------------------------------------ görsel okuyucu (balonun kuyruğu için)
def locator(characters: list[dict], timeout: float = 180.0):
    """`locate(image_path, name) -> {"x","y","w","h"} | None`: karakterin başı/yüzü, resme göre 0–1 oran.
    Görsel okuyan model gateway üzerinden (`book-vision-fast`); bulamazsa ya da hata olursa None."""
    import base64
    import io

    import httpx
    from PIL import Image

    from ..config import settings
    s = settings()
    looks = {c["name"]: f"{c['name']} ({c.get('species', '')}; {c.get('look', '')})" for c in characters}
    schema = {"type": "object", "additionalProperties": False, "required": ["found", "box"],
              "properties": {"found": {"type": "boolean"},
                             "box": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}}}

    def locate(image_path, name):
        try:
            im = Image.open(image_path).convert("RGB")
            im.thumbnail((1280, 1280))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=88)
            prompt = (f"Find {looks.get(name, name)} in this children's book illustration. Return the bounding box of "
                      "that character's head and face as [x0, y0, x1, y1] in 0-1000 coordinates of the image. "
                      "If the character is not visible, found=false.")
            body = {"model": "book-vision-fast", "max_tokens": 120, "temperature": 0.0,
                    "chat_template_kwargs": {"enable_thinking": False},
                    "response_format": {"type": "json_schema",
                                        "json_schema": {"name": "locate", "schema": schema, "strict": True}},
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}]}]}
            r = httpx.post(f"{s.gateway_url.rstrip('/')}/v1/chat/completions", json=body, timeout=timeout,
                           headers={"authorization": f"Bearer {s.gateway_key}"})
            r.raise_for_status()
            out = json.loads(r.json()["choices"][0]["message"]["content"])
            x0, y0, x1, y1 = (min(max(v / 1000, 0.0), 1.0) for v in out["box"])
            if not (out["found"] and x1 > x0 and y1 > y0):
                return None
            return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}
        except Exception:  # noqa: BLE001 - kuyruk kuralla yerleşir
            return None
    return locate
