"""Boyama / etkinlik kitabı: resimli kitabın işinden türetilen yeni stüdyo işi (ek ürün, maliyeti düşük).

Kaynak iş değişmez; yeni işin job.json'unda `kind: "coloring"` ve `derived_from: <kaynak iş>` durur. Yeni iş bugünkü
iş/plan altyapısını kullanır: manuscript/profile/spec/pagemap/front kaynaktan kopyalanır (başlık «… Boyama Kitabı»,
ISBN yeni ürün için boşaltılır), her resmin çizgisi studio.json'da bir resim kaydıdır (onay, sürüm, «Farklı üret»
bugünkü ekrandan), sayfalar doğrudan plan.json olarak kurulur. Böylece yeni kitap sayfa düzenleme ekranında aynı
araçlarla düzenlenir.

Hat (Temporal `ColoringBook`, stüdyo işçisi; görsel model açılmaz):
    kaynak → çizgi hatları (lineart.extract, modelsiz) → kısa cümleler (metin modeli; olmazsa kural) →
    etkinlik sayfaları (activities, modelsiz) → kapak (kaynak kapağın yarısı renkli, yarısı çizgi) → dizgi → ön kontrol
Sayfa düzeni: her resim için sol sayfada hikâyeden kısa cümle, sağ sayfada tam sayfa boyama (çizgi sağ sayfada:
çocuk boyarken arkadaki çizgiye taşmaz). Etkinlikler editörün seçtiği sırayla sonra gelir; forma katına kadar
«Kendi resmini çiz» sayfası eklenir (bilgi olarak yazılır), cevap anahtarı en sonda.

Çizgiyi görsel modelle yeniden çizdirme (`redraw`, `ColoringRedraw` GPU işi): kaynağın renkli resmi görsel modele
«boyama sayfası çizgisi» istemiyle verilir, dönen çizgi aynı baskı kuralından geçer (lineart.clean_drawn), yeni sürüm
olur. Görsel modelin lisansı ticari değildir: model çizgisi ekranda «taslak» diye işaretlenir.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from pathlib import Path

from PIL import Image

from . import activities as act_mod
from . import lineart
from . import plan as plan_mod
from . import studio

KIND = "coloring"
MODES = ("coloring", "coloring_activities")
FILE = "coloring.json"
STEPS = [("kaynak", "Kaynak kitap"), ("cizgi", "Çizgi hatları"), ("cumleler", "Kısa cümleler"),
         ("etkinlik", "Etkinlik sayfaları"), ("kapak", "Kapak"), ("dizgi", "Dizgi (PDF)"),
         ("on_kontrol", "Ön baskı denetimi")]
MODEL_MODES = {"lineart-model", "fix", "new"}          # görsel modelin çizdiği sürümler: taslak
TITLE_SUFFIX = {"coloring": "Boyama Kitabı", "coloring_activities": "Boyama ve Etkinlik Kitabı"}
LINE_STYLE = ("Black-and-white coloring book line art for children: bold, smooth, uniform black outlines, closed "
              "shapes, pure white inside, no color, no gray, no shading, no texture.")


def is_coloring(d: Path) -> bool:
    return (studio.read(d, "job.json") or {}).get("kind") == KIND


def age_of(d: Path) -> int:
    return int((studio.read(d, "profile.json") or {}).get("age_max") or 8)


# ------------------------------------------------------------------ kaynak
def source_arts(src: Path) -> list[dict]:
    """Kaynak kitabın basılan resimleri, sayfa sırasıyla: {key, path, dpi, text, moment, quote, grounded,
    characters, no}. Plan varsa plandan (fotoğraf/figür olarak konmuş sayfa resmi dahil), yoksa akıştan."""
    from . import photo
    sel = studio.selected_art(src)
    ap = studio.read(src, "artplan.json") or {}
    by_art = {s.get("art_id"): s for s in ap.get("scenes", []) if s.get("art_id")}
    by_page = {s["page"]: s for s in ap.get("scenes", [])}
    pl = plan_mod.load(src)
    out, seen = [], set()

    def add(key, path, box_mm, fit, text, sc, no):
        p = Path(path)
        if not p.exists() or str(p) in seen:
            return
        seen.add(str(p))
        with Image.open(p) as im:
            w, h = im.size
        dpi = photo.dpi(w, h, {"w": box_mm[0], "h": box_mm[1]}, fit) or 300.0
        out.append({"key": key, "path": str(p), "dpi": round(dpi, 1), "text": text or "", "no": no,
                    "moment": (sc or {}).get("moment", ""), "quote": (sc or {}).get("quote", ""),
                    "grounded": bool((sc or {}).get("grounded", True)), "characters": (sc or {}).get("characters", [])})

    if pl is not None:
        for i, pg in enumerate(pl["pages"]):
            a = pg.get("art")
            if not a:
                continue
            box = (a["box"]["w"], a["box"]["h"])
            if a.get("asset") and a["asset"] in pl.get("assets", {}):
                add(a["asset"], src / pl["assets"][a["asset"]]["path"], box, a.get("fit", "cover"),
                    plan_mod.page_text(pg), None, plan_mod.FRONT + i + 1)
            elif a.get("id") in sel:
                add(a["id"], sel[a["id"]], box, a.get("fit", "cover"), plan_mod.page_text(pg), by_art.get(a["id"]),
                    plan_mod.FRONT + i + 1)
    else:
        pm = studio.read(src, "pagemap.json") or {"pages": []}
        if not pm["pages"] or not sel:
            return out
        spec = studio._spec(src)
        full = studio.full_mm(spec)
        band = studio.band_mm(spec, studio._pagemap(src)) if pm["pages"] else full
        for p in pm["pages"]:
            if str(p["no"]) in sel:
                add(str(p["no"]), sel[str(p["no"])], full if p["kind"] == "full" else band, "cover", p.get("text", ""),
                    by_page.get(p["no"]), p["no"])
    return out


def characters_of(src: Path) -> list[dict]:
    """Referans resmi olan karakterler (ana karakter önce): {name, path, role}."""
    refs = studio.studio_state(src).get("characters", {})
    chars = (studio.read(src, "artplan.json") or {}).get("characters", [])
    out = [{"name": c["name"], "path": refs[c["name"]], "role": c.get("role")} for c in chars
           if c["name"] in refs and Path(refs[c["name"]]).exists()]
    return sorted(out, key=lambda c: c["role"] != "ANA")


def available(src: Path) -> list[dict]:
    """Etkinlik türleri ve bu kitapta yapılabilirliği (yapılamıyorsa sebebi)."""
    arts = source_arts(src)
    chars = characters_of(src)
    reason = {
        "paint_by_number": None if arts else "Kitapta resim yok",
        "spot_difference": None if arts else "Kitapta resim yok",
        "dot_to_dot": None if chars or arts else "Karakter resmi yok",
        "maze": None,
        "word_search": None,
        "matching": None if len(chars) >= 2 else "En az iki karakter resmi gerekir",
    }
    return [{"kind": k, "name": act_mod.NAMES[k], "ok": reason[k] is None, "reason": reason[k]} for k in act_mod.KINDS]


def derived(src: Path) -> list[dict]:
    """Bu kitaptan türetilmiş boyama/etkinlik işleri (en yeni önce)."""
    out = []
    for j in studio.list_jobs():
        if j.get("derived_from") == src.name and j.get("kind") == KIND:
            st = studio.read(studio.root() / j["id"], "state.json") or {}
            out.append({"id": j["id"], "title": j.get("title"), "created_at": j.get("created_at"),
                        "created_by": j.get("created_by"), "mode": (j.get("coloring") or {}).get("mode"),
                        "status": st.get("status"), "error": st.get("error"),
                        "steps": [{k: s.get(k) for k in ("key", "label", "status", "progress")} for s in st.get("steps", [])]})
    return out


# ------------------------------------------------------------------ yeni iş
def validate(src: Path, mode: str, acts: list[dict]) -> list[dict]:
    if mode not in MODES:
        raise ValueError("Seçim: yalnız boyama ya da boyama + etkinlik")
    if not source_arts(src):
        raise ValueError("Bu kitapta boyamaya dönüşecek resim yok")
    if mode == "coloring":
        return []
    ok = {a["kind"]: a for a in available(src)}
    out = []
    for a in acts:
        k = a.get("kind")
        if k not in ok:
            raise ValueError(f"bilinmeyen etkinlik: {k}")
        if not ok[k]["ok"]:
            raise ValueError(f"{ok[k]['name']}: {ok[k]['reason']}")
        o = {"kind": k}
        if k == "spot_difference":
            n = int(a.get("count") or 5)
            if n < 1:
                raise ValueError("Fark sayısı en az 1")
            o["count"] = n
        if a.get("source"):
            o["source"] = str(a["source"])
        out.append(o)
    if not out:
        raise ValueError("Etkinlik seçilmedi")
    return out


def new_job(src: Path, by: str, mode: str, acts: list[dict], captions: str = "model") -> Path:
    """Yeni boyama işini açar (klasör + job.json + bekleyen adımlar); hattı API kuyruğa verir."""
    acts = validate(src, mode, acts)
    sj = studio.read(src, "job.json") or {}
    d = studio.new_job(sj.get("source") or {}, by, "every_page",
                       extra={"kind": KIND, "derived_from": src.name,
                              "coloring": {"mode": mode, "activities": acts,
                                           "captions": "model" if captions != "rule" else "rule"}})
    st = _State(d)
    title = (studio.read(src, "manuscript.json") or {}).get("title") or ""
    st.data["title"] = f"{title} – {TITLE_SUFFIX[mode]}" if title else TITLE_SUFFIX[mode]
    st.flush()
    return d


class _State:
    """state.json: stüdyonun adım görünümüyle aynı biçim. Hata «bitti + hata» olarak yazılır: akış ekranının
    «kaldığı yerden devam» düğmesi kitap hattına aittir, boyama işini boyama panelindeki «yeniden dene» sürdürür."""

    def __init__(self, d: Path):
        self.d = d
        self.data = studio.read(d, "state.json") or {
            "title": "", "kind": KIND, "started": time.time(), "finished": None, "status": "running", "error": None,
            "steps": [{"key": k, "label": lab, "status": "waiting", "seconds": None, "summary": ""} for k, lab in STEPS]}
        self.t0: dict[str, float] = {}

    def step(self, key):
        return next(s for s in self.data["steps"] if s["key"] == key)

    def start(self, key):
        self.t0[key] = time.time()
        self.step(key).update(status="running", summary="")
        self.flush()

    def done(self, key, summary="", status="done", **extra):
        self.step(key).update(status=status, summary=summary,
                              seconds=round(time.time() - self.t0.get(key, time.time()), 1), **extra)
        self.flush()

    def progress(self, key, i, n):
        self.step(key)["progress"] = [i, n]
        self.flush()

    def flush(self):
        studio.write(self.d, "state.json", self.data)


def _link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        dst.hardlink_to(src)
    except OSError:
        shutil.copy(src, dst)


def _write_png(path: Path, im: Image.Image, two_tone: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if two_tone and im.mode != "RGB":
        tmp.write_bytes(lineart.png_bytes(im))
    else:
        im.save(tmp, "PNG", optimize=True)
    tmp.replace(path)


# ------------------------------------------------------------------ kısa cümle
SENT = re.compile(r"(?<=[.!?…])\s+")
DIALOGUE = re.compile(r"[“”\"«»]|^\s*[–—-]\s*")


def max_words(age: int) -> int:
    return 8 if age <= 6 else 12 if age <= 9 else 16


def rule_caption(text: str, age: int) -> str:
    """Modelsiz kısa cümle: diyalog olmayan ilk cümle; uzunsa virgülden ya da kelime sınırından kısaltılır."""
    words_max = max_words(age)
    sents = [s.strip() for s in SENT.split(" ".join((text or "").split())) if s.strip()]
    plain = [s for s in sents if not DIALOGUE.search(s)] or sents
    if not plain:
        return ""
    s = DIALOGUE.sub("", plain[0]).strip()
    w = s.split()
    if len(w) <= words_max:
        return s
    head = " ".join(w[:words_max])
    cut = head.rfind(",")
    s = head[:cut] if cut > len(head) // 2 else head
    return s.rstrip(",;:– ") + "."


async def captions(d: Path, arts: list[dict], age: int, use_model: bool, st: _State | None = None) -> list[dict]:
    """Her resim için kısa cümle: metin modeli (gateway, «book-director»); tutmazsa ya da kapalıysa kural."""
    from ..prompts import render
    out = []
    llm = None
    if use_model:
        from .run import FileLlm
        llm = FileLlm(d / "provenance.jsonl")
    schema = {"type": "object", "additionalProperties": False, "required": ["sentence"],
              "properties": {"sentence": {"type": "string"}}}
    n = max_words(age)
    for i, a in enumerate(arts, 1):
        text = a["text"] or a["quote"]
        rule = rule_caption(a["quote"] or text, age)
        cap = {"text": rule, "source": "kural", "original": text, "approved": False}
        if llm is not None and text.strip():
            try:
                ref, prompt = render("production_coloring_caption", age=str(age), moment=a.get("moment") or "-",
                                     text=text.strip()[:3000], max_words=str(n))
                res, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                                        schema=schema, max_tokens=300, thinking=False, temperature=0.2)
                s = " ".join(str(res.get("sentence", "")).split())
                if s and len(s.split()) <= n + 2:
                    cap.update(text=s, source="model")
                else:
                    cap["note"] = "model cümlesi uzun ya da boş: kural kullanıldı"
            except Exception as e:  # noqa: BLE001 - kısa cümle kuralla sürer
                cap["note"] = f"model yanıt vermedi: {type(e).__name__}"[:200]
        out.append(cap)
        if st:
            st.progress("cumleler", i, len(arts))
    return out


# ------------------------------------------------------------------ kapak
def cover_art(colored: Image.Image, line: Image.Image) -> Image.Image:
    """Kaynak kapaktan boyama kapağı: sol üst yarı renkli, sağ alt yarı çizgi (çapraz, arada ince beyaz şerit)."""
    import numpy as np
    col = colored.convert("RGB")
    W, H = col.size
    ln = line.convert("L").resize((W, H), Image.Resampling.LANCZOS).point(lambda v: 0 if v < 128 else 255)
    yy, xx = np.mgrid[0:H, 0:W]
    t = xx / W + yy / H - 1.0                     # 0 köşegen
    gap = 0.012
    out = np.where((t < -gap)[..., None], np.asarray(col), np.asarray(ln.convert("RGB")))
    out[np.abs(t) <= gap] = 255
    return Image.fromarray(out.astype("uint8"), "RGB")


# ------------------------------------------------------------------ sayfalar
def _blank(layout: str = "custom") -> dict:
    return {"id": plan_mod.new_id("p"), "chapter": None, "layout": layout, "art": None, "text": None, "bubbles": [],
            "figures": [], "texts": [], "shapes": [], "overflow": False}


def _free(box: dict, text: str, size: float, *, weight: int = 400, font: str = "body", z: int = 3) -> dict:
    return {"id": plan_mod.new_id("t"), "box": box, "align": "center", "size": size, "background": None,
            "runs": [{"text": text, "weight": weight, "font": font}], "z": z}


def page_boxes(page: dict) -> dict:
    """Etkinlik sayfasının kutuları (mm): başlık, yönerge, gövde; güvenli alanın içinde."""
    W, H, b, s = page["w"], page["h"], page["bleed"], page["safe"]
    m = b + s
    tw = W - 2 * m
    return {"title": plan_mod.box(m, m, tw, 14), "hint": plan_mod.box(m, m + 15, tw, 12),
            "body": plan_mod.box(m, m + 29, tw, H - 2 * m - 29), "safe": plan_mod.box(m, m, tw, H - 2 * m)}


def caption_page(page: dict, text: str, body: float) -> dict:
    W, H, b, s = page["w"], page["h"], page["bleed"], page["safe"]
    m = b + s
    pg = _blank("custom")
    pg["text"] = {"box": plan_mod.box(m, H * 0.36, W - 2 * m, H * 0.3), "align": "center", "size": round(body * 1.45, 1),
                  "background": None, "blocks": [{"id": plan_mod.new_id("k"), "kind": "para", "runs": [{"text": text}]}]}
    return pg


def coloring_page(page: dict, aid: str) -> dict:
    pg = _blank("custom")
    bx = page_boxes(page)["safe"]
    pg["art"] = {"id": aid, "box": bx, "fit": "contain", "focus": {"x": 0.5, "y": 0.5}}
    return pg


def activity_page(page: dict, a: act_mod.Activity, gid: str, body: float) -> dict:
    bx = page_boxes(page)
    pg = _blank("custom")
    pg["texts"].append(_free(bx["title"], a.title, round(body * 1.5, 1), weight=800, font="heading"))
    pg["texts"].append(_free(bx["hint"], a.instruction, round(body * 0.9, 1)))
    body_box = dict(bx["body"])
    if a.words:
        wb = 26.0
        body_box["h"] = round(body_box["h"] - wb, 2)
        pg["texts"].append(_free(plan_mod.box(body_box["x"], body_box["y"] + body_box["h"] + 2, body_box["w"], wb - 2),
                                 "   ".join(a.words), round(body * 0.95, 1), weight=700))
    pg["art"] = {"asset": gid, "id": None, "box": body_box, "fit": "contain", "focus": {"x": 0.5, "y": 0.5}}
    return pg


def body_mm(page: dict, words: bool = False) -> tuple[float, float]:
    b = page_boxes(page)["body"]
    return b["w"], b["h"] - (26.0 if words else 0.0)


# ------------------------------------------------------------------ hat
async def build(d: Path) -> dict:
    """Boyama işinin hattı (stüdyo işçisinde). Tekrar koşarsa hazır olanı atlar (çizgiler, cümleler, etkinlikler
    dosyada), plan varsa yalnız dizgi ve ön kontrol yenilenir."""
    job = studio.read(d, "job.json")
    opts = job["coloring"]
    src = studio.job_dir(job["derived_from"])
    by = job.get("created_by", "")
    st = _State(d)
    st.data.update(status="running", error=None, finished=None)
    st.flush()
    try:
        await _build(d, src, job, opts, by, st)
        st.data.update(status="done", finished=time.time())
    except Exception as e:  # noqa: BLE001 - ekranda adım hatası; «yeniden dene» kaldığı yerden sürer
        import traceback
        running = next((s for s in st.data["steps"] if s["status"] == "running"), None)
        if running:
            running.update(status="fail", summary=str(e)[:300])
        st.data.update(status="done", error=f"{type(e).__name__}: {e}"[:500], finished=time.time())
        (d / "hata.txt").write_text("".join(traceback.format_exception(type(e), e, e.__traceback__)))
    st.flush()
    return st.data


async def _build(d: Path, src: Path, job: dict, opts: dict, by: str, st: _State) -> None:
    import dataclasses

    from .art import ArtPlan, Character, Scene, Style
    # 1) kaynak
    st.start("kaynak")
    arts = source_arts(src)
    if not arts:
        raise ValueError("Kaynak kitapta resim yok")
    ms = studio.read(src, "manuscript.json")
    mode = opts["mode"]
    ms["title"] = st.data["title"] or f"{ms['title']} – {TITLE_SUFFIX[mode]}"
    meta = dict(ms.get("meta") or {})
    meta.pop("ISBN", None)                                  # yeni ürün: ISBN editörden
    ms["meta"] = meta
    studio.write(d, "manuscript.json", ms)
    for name in ("profile.json", "spec.json", "pagemap.json"):
        studio.write(d, name, studio.read(src, name))
    from . import front as front_mod
    fr = studio.read(src, "front.json") or {"kunye_fields": {}, "manual": {}, "bios": []}
    manual = {k: v for k, v in (fr.get("manual") or {}).items() if k != "ISBN"}
    fr.update(manual=manual, kunye=front_mod.kunye(studio._manuscript(d), fr.get("kunye_fields") or {}, manual))
    studio.write(d, "front.json", fr)
    chars = characters_of(src)
    ap = studio.read(src, "artplan.json")
    style = dict(ap["style"])
    style["style_prompt"] = LINE_STYLE                     # «Farklı üret» bu işte çizgi çizer
    style["avoid"] = (style.get("avoid") or "") + ", color, gray, shading, gradient"
    sd = studio.studio_state(d)
    sd.setdefault("characters", {})
    for i, c in enumerate(chars):
        dst = d / "resim" / f"karakter-{i:02d}.png"
        _link(Path(c["path"]), dst)
        sd["characters"][c["name"]] = str(dst)
    studio.write(d, "studio.json", sd)
    age = age_of(d)
    st.done("kaynak", f"{len(arts)} resim · {len(chars)} karakter · {age} yaş üstü sınır")

    # 2) çizgi hatları
    st.start("cizgi")
    cz = studio.read(d, FILE) or {}
    lines = cz.get("arts") or []
    have = {a["key"]: a for a in lines}
    stroke = lineart.stroke_mm(age)
    detail = lineart.detail_for(age)
    for i, a in enumerate(arts, 1):
        if a["key"] not in have:
            aid = plan_mod.new_id("a")
            im = await asyncio.to_thread(_open_rgb, Path(a["path"]))
            res = await asyncio.to_thread(lineart.extract, im, src_dpi=a["dpi"], stroke=stroke, detail=detail)
            rel = d / "resim" / f"cizgi-{aid}.v1.png"
            await asyncio.to_thread(_write_png, rel, res.image)
            src_rel = d / "kaynak" / f"{aid}{Path(a['path']).suffix}"
            _link(Path(a["path"]), src_rel)
            studio.add_version(d, aid, str(rel), mode="lineart", prompt=f"Çizgi (kaynak sayfa {a['no']})", seed=0,
                               by=by, dpi=res.info["dpi"])
            have[a["key"]] = {"key": a["key"], "aid": aid, "source": str(src_rel), "src_dpi": a["dpi"], "no": a["no"],
                              "info": res.info}
            lines.append(have[a["key"]])
            cz["arts"] = lines
            studio.write(d, FILE, cz)
        st.progress("cizgi", i, len(arts))
    st.done("cizgi", f"{len(arts)} boyama sayfası · çizgi {stroke:g} mm · yalnız siyah-beyaz")

    # 3) kısa cümleler
    st.start("cumleler")
    if not cz.get("captions"):
        caps = await captions(d, arts, age, opts.get("captions", "model") == "model", st)
        cz["captions"] = [{**c, "aid": have[a["key"]]["aid"]} for c, a in zip(caps, arts)]
        studio.write(d, FILE, cz)
    by_model = sum(c["source"] == "model" for c in cz["captions"])
    st.done("cumleler", f"{len(cz['captions'])} cümle · {by_model} Zeki AI önerisi · editör onayı bekliyor")

    # 4) etkinlikler
    st.start("etkinlik")
    spec = studio._spec(d)
    from .typeset import Layout
    lay = Layout(**studio.read(d, "pagemap.json")["layout"])
    page = plan_mod.geometry(spec, lay)
    assets: dict[str, dict] = {}
    acts_out = cz.get("activities")
    if acts_out is None and mode == "coloring_activities":
        acts_out, assets = await asyncio.to_thread(_activities, d, opts["activities"], arts, have, chars, page, age,
                                                   by, st)
        cz["activities"], cz["assets"] = acts_out, assets
        studio.write(d, FILE, cz)
    acts_out = acts_out or []
    assets = cz.get("assets") or assets
    st.done("etkinlik", f"{sum(1 for a in acts_out if a['kind'] != 'answers')} etkinlik sayfası"
            if mode == "coloring_activities" else "yalnız boyama seçildi", status="done" if acts_out or
            mode == "coloring" else "warn")

    # 5) kapak
    st.start("kapak")
    if "kapak" not in studio.studio_state(d)["pages"]:
        sel = studio.selected_art(src)
        cover_src = Path(sel["kapak"]) if "kapak" in sel else Path(arts[0]["path"])
        col = await asyncio.to_thread(_open_rgb, cover_src)
        spec_c = studio.cover_mm(spec)
        cdpi = col.width / (spec_c[0] / 25.4)
        ln = await asyncio.to_thread(lineart.extract, col, src_dpi=cdpi, stroke=stroke, detail=detail)
        comp = await asyncio.to_thread(cover_art, col, ln.image)
        path = d / "resim" / "kapak.v1.png"
        await asyncio.to_thread(_write_png, path, comp, False)
        studio.add_version(d, "kapak", str(path), mode="lineart", prompt="Kaynak kapaktan (yarısı çizgi)", seed=0,
                           by=by, dpi=round(cdpi))
    st.done("kapak", "kaynak kapağın yarısı renkli, yarısı boyanacak çizgi")

    # 6) sahneler (ön kontrol ve «Farklı üret» için) + plan + dizgi
    st.start("dizgi")
    scenes = []
    src_scenes = {s.get("art_id") or str(s["page"]): s for s in ap.get("scenes", [])}
    for a in arts:
        sc = src_scenes.get(a["key"])
        if sc:
            s2 = dict(sc)
            s2.update(art_id=have[a["key"]]["aid"], kind="full")
            scenes.append(s2)
    new_ap = ArtPlan(Style(**style), [Character(**c) for c in ap["characters"]])
    new_ap.scenes = [Scene(**{k: v for k, v in s.items() if k in {f.name for f in dataclasses.fields(Scene)}})
                     for s in scenes]
    studio.write(d, "artplan.json", new_ap.to_json())
    if not plan_mod.exists(d):
        plan = await asyncio.to_thread(assemble, d, src, arts, have, cz, assets, page, lay, by)
        cz["filler"] = plan.pop("_filler", 0)
        cz["pages"] = plan.pop("_roles", {})
        studio.write(d, FILE, cz)
    else:
        await asyncio.to_thread(studio.rebuild, d)
    info = studio.read(d, "cover.json") or {}
    extra = f" · {cz.get('filler')} «kendi resmini çiz» sayfası forma katı için eklendi" if cz.get("filler") else ""
    st.done("dizgi", f"{plan_mod.FRONT + len(plan_mod.load(d)['pages'])} sayfa{extra}"
            + (f" · kapak sırtı {info.get('spine_mm')} mm" if info else ""))
    st.start("on_kontrol")
    rep = studio.read(d, "preflight.json") or {"status": "WARN", "checks": []}
    bad = [c for c in rep["checks"] if c["status"] != "OK"]
    st.done("on_kontrol", "; ".join(f"{c['name']}: {c['status']}" for c in bad) or "hepsi geçti",
            status={"OK": "done", "WARN": "warn", "FAIL": "warn"}[rep["status"]])


def _open_rgb(p: Path) -> Image.Image:
    with Image.open(p) as im:
        return act_mod.on_white(im)


def _pick(arts: list[dict], have: dict, used: set[str], prefer: str | None) -> dict:
    """Etkinliğin resmi: editör seçtiyse o; yoksa henüz kullanılmamış, en çok kapalı bölgesi olan."""
    if prefer:
        for a in arts:
            if a["key"] == prefer or have[a["key"]]["aid"] == prefer:
                return a
    pool = [a for a in arts if a["key"] not in used] or arts
    return max(pool, key=lambda a: have[a["key"]]["info"].get("regions", 0))


def _activities(d: Path, chosen: list[dict], arts: list[dict], have: dict, chars: list[dict], page: dict, age: int,
                by: str, st: _State) -> tuple[list[dict], dict]:
    """Etkinlik sayfalarının görselleri → etkinlik/<gid>.png; dönen: sayfa kayıtları ve plan varlıkları."""
    fonts = studio.fonts()
    out, assets, answers, used = [], {}, [], set()
    text = " ".join(b["text"] for c in studio.read(d, "manuscript.json")["chapters"] for b in c["blocks"])
    names = [c["name"] for c in (studio.read(d, "artplan.json") or {}).get("characters", [])]
    char_imgs = [(c["name"], _open_rgb(Path(c["path"]))) for c in chars]
    ci = 0
    for n, a in enumerate(chosen, 1):
        k = a["kind"]
        seed = act_mod.seed_of(d.name, k, n)
        made: list[act_mod.Activity] = []
        if k == "paint_by_number":
            art = _pick(arts, have, used, a.get("source"))
            used.add(art["key"])
            line = Image.open(studio.selected_art(d)[have[art["key"]]["aid"]])
            made.append(act_mod.paint_by_number(_open_rgb(Path(art["path"])), line, body_mm(page), age, fonts))
        elif k == "spot_difference":
            art = _pick(arts, have, used, a.get("source"))
            used.add(art["key"])
            line = Image.open(studio.selected_art(d)[have[art["key"]]["aid"]])
            made.append(act_mod.spot_difference(line, body_mm(page), age, seed, a.get("count", 5)))
        elif k == "dot_to_dot":
            if char_imgs:
                made.append(act_mod.dot_to_dot(char_imgs[ci % len(char_imgs)][1], body_mm(page), age, fonts))
                ci += 1
            else:
                art = _pick(arts, have, used, a.get("source"))
                made.append(act_mod.dot_to_dot(_open_rgb(Path(art["path"])), body_mm(page), age, fonts))
        elif k == "maze":
            s = char_imgs[0] if char_imgs else (None, None)
            g = char_imgs[1] if len(char_imgs) > 1 else (None, None)
            made.append(act_mod.maze(body_mm(page), age, seed, s[1], g[1], s[0] or "", g[0] or ""))
        elif k == "word_search":
            grid = 8 if age <= 6 else 10 if age <= 9 else 12
            made.append(act_mod.word_search(act_mod.book_words(text, names, grid), body_mm(page, True), age, seed,
                                            fonts))
        elif k == "matching":
            made += act_mod.matching(char_imgs, body_mm(page), age, seed, fonts)
        for m in made:
            gid = plan_mod.new_id("g")
            rel = f"etkinlik/{gid}.png"
            _write_png(d / rel, m.image, m.image.mode != "RGB")
            assets[gid] = {"kind": "activity", "activity": m.kind, "path": rel, "w_px": m.image.width,
                           "h_px": m.image.height, "alpha": False, "name": m.title, "by": by, "at": plan_mod._now()}
            out.append({"kind": m.kind, "title": m.title, "instruction": m.instruction, "words": m.words,
                        "asset": gid, "info": m.info})
            if m.answer is not None:
                answers.append((m.title, m.answer))
        st.progress("etkinlik", n, len(chosen))
    if answers:
        for im in act_mod.answer_pages(answers, body_mm(page), fonts):
            gid = plan_mod.new_id("g")
            rel = f"etkinlik/{gid}.png"
            _write_png(d / rel, im)
            assets[gid] = {"kind": "activity", "activity": "answers", "path": rel, "w_px": im.width, "h_px": im.height,
                           "alpha": False, "name": "Cevap anahtarı", "by": by, "at": plan_mod._now()}
            out.append({"kind": "answers", "title": "Cevap anahtarı", "instruction": "Etkinliklerin çözümleri.",
                        "words": [], "asset": gid, "info": {}})
    return out, assets


def assemble(d: Path, src: Path, arts: list[dict], have: dict, cz: dict, assets: dict, page: dict, lay, by: str) -> dict:
    """plan.json: [kısa cümle | boyama] çiftleri, etkinlikler, forma katına «kendi resmini çiz», cevap anahtarı.
    Dizgi, kapak ve ön kontrol bugünkü yoldan (plan.mutate'in yaptıklarının aynısı; ilk sürüm)."""
    spec = studio._spec(d)
    body = page.get("body_size") or spec.body_size
    caps = {c["aid"]: c for c in cz.get("captions") or []}
    pages: list[dict] = []
    roles: dict[str, dict] = {}                   # sayfa kimliği → rolü (coloring.json; sayfa düzenlense de kalır)
    for a in arts:
        aid = have[a["key"]]["aid"]
        cap = caps.get(aid, {}).get("text") or ""
        cp = caption_page(page, cap, body) if cap else _blank("blank")
        roles[cp["id"]] = {"role": "caption", "aid": aid}
        pages.append(cp)
        pg = coloring_page(page, aid)
        roles[pg["id"]] = {"role": "coloring", "aid": aid}
        pages.append(pg)
    acts = [a for a in cz.get("activities") or [] if a["kind"] != "answers"]
    tail = [a for a in cz.get("activities") or [] if a["kind"] == "answers"]
    for a in acts:
        m = act_mod.Activity(a["kind"], a["title"], a["instruction"], Image.new("L", (1, 1)), a.get("words") or [])
        pg = activity_page(page, m, a["asset"], body)
        roles[pg["id"]] = {"role": "activity", "kind": a["kind"]}
        pages.append(pg)
    filler = 0
    sig = spec.signature
    age = age_of(d)
    need = (-(plan_mod.FRONT + len(pages) + len(tail))) % sig
    if need:
        gid = plan_mod.new_id("g")
        bx = page_boxes(page)
        fb = (bx["body"]["w"], bx["body"]["h"])
        im = act_mod.frame(fb, age)
        rel = f"etkinlik/{gid}.png"
        _write_png(d / rel, im)
        assets[gid] = {"kind": "activity", "activity": "draw", "path": rel, "w_px": im.width, "h_px": im.height,
                       "alpha": False, "name": "Kendi resmini çiz", "by": by, "at": plan_mod._now()}
        for _ in range(need):
            m = act_mod.Activity("draw", "Kendi resmini çiz", "Hikâyede en sevdiğin anı çerçevenin içine çiz.",
                                 im)
            pg = activity_page(page, m, gid, body)
            roles[pg["id"]] = {"role": "filler"}
            pages.append(pg)
            filler += 1
    for a in tail:
        m = act_mod.Activity("answers", a["title"], a["instruction"], Image.new("L", (1, 1)))
        pg = activity_page(page, m, a["asset"], body)
        roles[pg["id"]] = {"role": "answers"}
        pages.append(pg)
    spal = (plan_mod.load(src) or {}).get("palette")
    if not spal:
        from . import palette as pal_mod
        cols = pal_mod.extract([Path(a["path"]) for a in arts], n=6)
        spal = {"colors": cols, "text": plan_mod.INK, "characters": {}}
    plan = {"version": 1, "rev": 0, "frozen_at": plan_mod._now(), "frozen_by": by, "page": page,
            "palette": spal, "pages": [], "assets": assets, "warnings": []}
    plan["pages"] = [plan_mod._clean_page(pg, plan) for pg in pages]
    with plan_mod._locked(d):
        plan_mod._typeset(d, plan, True)
        plan_mod._commit(d, plan, by, "boyama kitabı kuruldu")
    plan_mod.after_write(d, cover=True, mode="sync")
    plan["_filler"] = filler
    plan["_roles"] = roles
    return plan


# ------------------------------------------------------------------ ekran
def view(d: Path) -> dict:
    """Boyama işinin ekrandaki özeti: kaynak, cümleler (onay), etkinlikler, taslak (model) çizgiler."""
    job = studio.read(d, "job.json") or {}
    cz = studio.read(d, FILE) or {}
    pl = plan_mod.load(d) or {"pages": []}
    sd = studio.studio_state(d)
    no_of = {}
    for i, pg in enumerate(pl["pages"]):
        if pg.get("art") and pg["art"].get("id"):
            no_of[pg["art"]["id"]] = plan_mod.FRONT + i + 1
    roles = cz.get("pages") or {}
    cap_page = {roles[pg["id"]]["aid"]: (plan_mod.FRONT + i + 1, pg) for i, pg in enumerate(pl["pages"])
                if (roles.get(pg["id"]) or {}).get("role") == "caption"}
    sentences = []
    for c in cz.get("captions") or []:
        no, pg = cap_page.get(c["aid"], (None, None))
        cur = plan_mod.page_text(pg) if pg else c["text"]
        sentences.append({"aid": c["aid"], "page": pg["id"] if pg else None, "no": no, "text": cur,
                          "suggested": c["text"], "source": c["source"], "original": c.get("original", "")[:600],
                          "approved": bool(c.get("approved")), "note": c.get("note")})
    arts = []
    for a in cz.get("arts") or []:
        pg = sd["pages"].get(a["aid"]) or {}
        v = pg["versions"][pg["selected"] - 1] if pg.get("selected") else {}
        arts.append({"aid": a["aid"], "no": no_of.get(a["aid"]), "source_no": a.get("no"),
                     "versions": len(pg.get("versions", [])), "selected": pg.get("selected"),
                     "approved": pg.get("approved", False), "method": v.get("mode"),
                     "draft": v.get("mode") in MODEL_MODES, "regions": (a.get("info") or {}).get("regions")})
    return {"kind": "derived", "derived_from": job.get("derived_from"), "options": job.get("coloring"),
            "sentences": sentences, "activities": [{k: a.get(k) for k in ("kind", "title", "info")}
                                                   for a in cz.get("activities") or []],
            "arts": arts, "drafts": [a["no"] for a in arts if a["draft"]], "filler": cz.get("filler", 0),
            "state": studio.read(d, "state.json")}


def source_view(src: Path) -> dict:
    arts = source_arts(src)
    return {"kind": "source", "arts": len(arts), "characters": len(characters_of(src)),
            "available": available(src), "derived": derived(src),
            "caption_words": max_words(age_of(src))}


def set_sentences(d: Path, items: list[dict], by: str) -> dict:
    """Kısa cümle düzeltme/onay: metin değiştiyse karşı sayfanın metni güncellenir (plan yazımı, yeni sürüm);
    onay coloring.json'da. Editörün yazdığı cümle `source: "editor"` olur."""
    cz = studio.read(d, FILE) or {}
    caps = {c["aid"]: c for c in cz.get("captions") or []}
    changes: dict[str, str] = {}
    for it in items:
        c = caps.get(str(it.get("aid")))
        if c is None:
            raise KeyError(f"cümle yok: {it.get('aid')}")
        if "text" in it and it["text"] is not None:
            t = " ".join(str(it["text"]).split())[:400]
            if not t:
                raise ValueError("Cümle boş olamaz")
            changes[c["aid"]] = t
        if "approved" in it:
            c["approved"] = bool(it["approved"])
            c["approved_by"] = by if c["approved"] else None
    if changes:
        roles = cz.get("pages") or {}

        def fn(plan):
            for pg in plan["pages"]:
                role = roles.get(pg["id"]) or {}
                if role.get("role") == "caption" and role.get("aid") in changes and pg.get("text"):
                    pg["text"]["blocks"] = [{"id": plan_mod.new_id("k"), "kind": "para",
                                             "runs": [{"text": changes[role["aid"]], "source": "editor"}]}]
        plan_mod.mutate(d, None, by, "kısa cümle düzeltildi", fn)
        for aid, t in changes.items():
            caps[aid].update(text=t, source="editor")
    studio.write(d, FILE, cz)
    return view(d)


async def redraw(d: Path, aid: str, by: str) -> dict:
    """Çizgiyi görsel modelle yeniden çizdirir (GPU): kaynağın renkli resmi + «boyama sayfası» istemi; dönen çizgi
    baskı kuralından geçer, yeni sürüm olur (seçili, onayı düşer). Taslak: görsel modelin lisansı ticari değil."""
    import random

    from .images import Painter
    cz = studio.read(d, FILE) or {}
    a = next((x for x in cz.get("arts") or [] if x["aid"] == aid), None)
    if a is None:
        raise KeyError(f"çizgi yok: {aid}")
    src = Path(a["source"])
    col = await asyncio.to_thread(_open_rgb, src)
    from .images import PIXEL_BUDGET
    k = min(1.0, (PIXEL_BUDGET / (col.width * col.height)) ** 0.5)
    W, H = int(col.width * k) // 32 * 32, int(col.height * k) // 32 * 32
    import io
    buf = io.BytesIO()
    col.resize((W, H), Image.Resampling.LANCZOS).save(buf, "PNG")
    painter = Painter(d / "resim", studio._plan(d))
    seed = random.randint(1, 2**31 - 1)
    try:
        png = await painter._edit(lineart.REDRAW_PROMPT, [buf.getvalue()], W, H, seed)
    finally:
        await painter.close()
    raw = Image.open(io.BytesIO(png))
    res = await asyncio.to_thread(lineart.clean_drawn, raw, src_dpi=a["src_dpi"], stroke=lineart.stroke_mm(age_of(d)),
                                  size=col.size)
    v = len(studio.studio_state(d)["pages"].get(aid, {"versions": []})["versions"]) + 1
    path = d / "resim" / f"cizgi-{aid}.v{v}.png"
    await asyncio.to_thread(_write_png, path, res.image)
    (d / "resim" / f"cizgi-{aid}.v{v}.ham.png").write_bytes(png)
    studio.add_version(d, aid, str(path), mode="lineart-model", prompt="Zeki AI ile yeniden çizildi (taslak)",
                       seed=seed, by=by, dpi=res.info["dpi"])
    await asyncio.to_thread(studio.rebuild, d)
    return {"aid": aid, "v": v, "info": res.info}


def after_version(d: Path, key: str, path: str) -> None:
    """studio.add_version kancası: boyama işinde görsel modelin çizdiği sayfa sürümü (Düzelt/Farklı üret) baskı
    kuralına getirilir — saf siyah-beyaz, kırıntısız, yaşa uygun kalınlık. Modelsiz çizgi zaten öyledir."""
    if key == "kapak":
        return
    p = Path(path)
    with Image.open(p) as im:
        if lineart.is_two_tone(im):
            return
        raw = im.convert("RGB")
    cz = studio.read(d, FILE) or {}
    a = next((x for x in cz.get("arts") or [] if x["aid"] == key), {})
    dpi = float(a.get("src_dpi") or 300.0)
    res = lineart.clean_drawn(raw, src_dpi=dpi, stroke=lineart.stroke_mm(age_of(d)))
    shutil.copy(p, p.with_name(p.stem + ".ham.png"))
    _write_png(p, res.image)

