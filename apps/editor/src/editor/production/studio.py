"""Kitap Tasarım Stüdyosu: işler ve sayfa işlemleri.

Bir iş = bir kitabın basıma hazırlığı; klasörü <storage>/production/<iş>/:
    job.json        kim, ne zaman, kaynak (okunmuş kitap ya da Word dosyası)
    state.json      hattın adımları (run.py yazar)
    manuscript/profile/spec/pagemap/artplan/front.json
    studio.json     sayfa başına resim sürümleri, seçili sürüm, onay; karakter referansları
    resim/          karakter-XX.png, sayfa-NN.vK.png, kapak.vK.png
    dizgi/          ic-sayfalar.pdf (+ önizleme/), kapak/kapak.pdf, preflight.json

Sayfa resminde iki yol:
- DÜZELT (`fix`): seçili sürüm ilk referans görseldir; yalnız editörün yazdığı değişir.
- FARKLI ÜRET (`new`): sayfanın sahnesinden yeni tohumla sıfırdan; editörün yazdığı yönlendirme olarak eklenir.
Her yeni sürüm seçili olur, sayfanın onayı düşer, iç sayfa ve kapak yeniden dizilir, ön kontrol yenilenir.
Onaylanmamış sayfa varsa ön kontrol basımı durdurur.
"""

from __future__ import annotations

import json
import os
import random
import secrets
import threading
import time
from pathlib import Path

from ..config import settings
from . import art as art_mod
from . import cover as cover_mod
from . import preflight
from .art import ArtPlan, Character, Scene, Style
from .images import Painter
from .manuscript import Block, Chapter, Manuscript
from .profile import Profile
from .spec import Spec
from .typeset import Layout, PageMap, Page, Typesetter, book_data

_locks: dict[str, threading.Lock] = {}


def root() -> Path:
    return Path(settings().storage) / "production"


def job_dir(job_id: str) -> Path:
    if not job_id.isalnum() or len(job_id) > 40:
        raise ValueError("geçersiz iş")
    d = root() / job_id
    if not d.is_dir():
        raise FileNotFoundError(job_id)
    return d


def new_job(source: dict, by: str, art_mode: str = "auto", extra: dict | None = None) -> Path:
    """`art_mode`: işi açarken resim seçimi (auto | every_page | chapter | none); profilin kararının önüne geçer.
    `extra`: türetilmiş işin alanları (boyama kitabı: `kind`, `derived_from`; coloring.py)."""
    job_id = time.strftime("%Y%m%d%H%M%S") + secrets.token_hex(3)
    d = root() / job_id
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps({**(extra or {}), "id": job_id, "source": source, "created_by": by,
                                            "created_at": time.time(), "art_mode": art_mode}, ensure_ascii=False))
    return d


def lock(job_id: str) -> threading.Lock:
    return _locks.setdefault(job_id, threading.Lock())


def read(d: Path, name: str, default=None):
    p = d / name
    return json.loads(p.read_text()) if p.exists() else default


def write(d: Path, name: str, obj) -> None:
    tmp = d / (name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
    tmp.replace(d / name)


def busy(d: Path) -> dict | None:
    """Süren ya da sırada bekleyen GPU işi: {key, mode, since, queued, workflow_id} ya da son üretimin
    hatası {…, error}. API işi başlatırken yazar, Temporal etkinliği başlayınca «sırada»yı kaldırır,
    bitince siler (flow.py)."""
    return read(d, "busy.json")


def set_busy(d: Path, info: dict | None) -> None:
    if info is None:
        (d / "busy.json").unlink(missing_ok=True)
    else:
        write(d, "busy.json", info)


def list_jobs() -> list[dict]:
    out = []
    if not root().exists():
        return out
    for d in sorted(root().iterdir(), reverse=True):
        j = read(d, "job.json")
        if not j:
            continue
        st = read(d, "state.json", {})
        out.append({**j, "title": st.get("title"), "steps": [
            {k: s.get(k) for k in ("key", "label", "status")} for s in st.get("steps", [])]})
    return out


# ------------------------------------------------------------------ yükleme
def _manuscript(d: Path) -> Manuscript:
    m = read(d, "manuscript.json")
    ms = Manuscript(**{k: m[k] for k in ("title", "author", "illustrator", "meta", "source")})
    ms.chapters = [Chapter(c["title"], [Block(**b) for b in c["blocks"]]) for c in m["chapters"]]
    return ms


def _profile(d: Path) -> Profile:
    return Profile(**read(d, "profile.json"))


def _spec(d: Path) -> Spec:
    s = read(d, "spec.json")
    s["art_ratio"] = tuple(s["art_ratio"])
    return Spec(**s)


def _pagemap(d: Path) -> PageMap:
    pm = read(d, "pagemap.json")
    return PageMap([Page(**p) for p in pm["pages"]], Layout(**pm["layout"]))


def _plan(d: Path) -> ArtPlan:
    a = read(d, "artplan.json")
    plan = ArtPlan(Style(**a["style"]), [Character(**c) for c in a["characters"]])
    plan.scenes = [Scene(**s) for s in a["scenes"]]
    return plan


def fonts() -> Path:
    import os
    return Path(os.environ.get("EDITOR_FONT_DIR", "/app/data/fonts"))


def band_mm(spec: Spec, pm: PageMap) -> tuple[float, float]:
    return spec.trim_w + 2 * spec.bleed, spec.bleed + pm.layout.art_ratio * spec.trim_h


def full_mm(spec: Spec) -> tuple[float, float]:
    return spec.trim_w + 2 * spec.bleed, spec.trim_h + 2 * spec.bleed


def cover_mm(spec: Spec) -> tuple[float, float]:
    return spec.trim_w + spec.bleed, spec.trim_h + 2 * spec.bleed


# ------------------------------------------------------------------ durum
def studio_state(d: Path) -> dict:
    return read(d, "studio.json", {"pages": {}, "characters": {}})


def add_version(d: Path, key: str, path: str, *, mode: str, prompt: str, seed: int, by: str,
                dpi: int, base: int | None = None, prompt_en: str = "") -> int:
    st = studio_state(d)
    pg = st["pages"].setdefault(key, {"versions": [], "selected": None, "approved": False})
    v = len(pg["versions"]) + 1
    pg["versions"].append({"v": v, "path": path, "mode": mode, "prompt": prompt, "seed": seed, "by": by,
                           "at": time.time(), "dpi": dpi, "base": base,
                           **({"prompt_en": prompt_en} if prompt_en else {})})
    pg["selected"], pg["approved"], pg["approved_by"] = v, False, None
    write(d, "studio.json", st)
    if (read(d, "job.json") or {}).get("kind") == "coloring":       # boyama kitabı: çizgi baskı kuralına
        from . import coloring
        coloring.after_version(d, key, path)
    return v


def selected_art(d: Path) -> dict[str, str]:
    st = studio_state(d)
    out = {}
    for key, pg in st["pages"].items():
        if pg.get("selected"):
            out[key] = pg["versions"][pg["selected"] - 1]["path"]
    return out


def select(d: Path, key: str, v: int, by: str) -> None:
    st = studio_state(d)
    pg = st["pages"][key]
    if not 1 <= v <= len(pg["versions"]):
        raise ValueError("böyle sürüm yok")
    pg["selected"], pg["approved"], pg["approved_by"] = v, False, None
    write(d, "studio.json", st)
    rebuild(d)


def approve(d: Path, key: str, ok: bool, by: str) -> None:
    st = studio_state(d)
    pg = st["pages"][key]
    pg["approved"], pg["approved_by"], pg["approved_at"] = ok, by if ok else None, time.time()
    write(d, "studio.json", st)
    refresh_preflight(d)


def set_kunye(d: Path, values: dict[str, str], by: str) -> dict:
    """Ekranda elle girilen künye alanları (etiket → değer). Boş değer elle girişi kaldırır (sistemin
    bulduğu değer ya da «—» geri gelir). Yerleşim değişmez; iç sayfa yeniden dizilir."""
    from . import front as front_mod
    fr = read(d, "front.json")
    manual = dict(fr.get("manual") or {})
    for label, value in values.items():
        if label not in front_mod.EDITABLE:
            raise ValueError(f"düzenlenemeyen alan: {label}")
        value = " ".join(str(value).split())[:300]
        if value:
            manual[label] = value
        else:
            manual.pop(label, None)
    fr["manual"] = manual
    fr["manual_by"] = by
    fr["kunye"] = front_mod.kunye(_manuscript(d), fr.get("kunye_fields") or {}, manual)
    write(d, "front.json", fr)
    rebuild(d)
    return fr


# ------------------------------------------------------------------ dizgi
def page_count(d: Path) -> int:
    """İç sayfa sayısı: sayfa planı varsa ön sayfalar + plan sayfaları, yoksa akışın sayfa haritası."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    return plan_mod.FRONT + len(pl["pages"]) if pl else len(_pagemap(d).pages)


def build_cover(d: Path) -> None:
    """Kapak açılımı (sırt kalınlığı sayfa sayısına bağlı). Kapak resmi varsa resimli; yoksa ve kitap «resimsiz»
    seçildiyse tipografik (görsel model açılmaz); öteki kitapta kapak resmi beklenir, yapılmaz."""
    art = selected_art(d)
    typographic = "kapak" not in art and (read(d, "job.json") or {}).get("art_mode") == "none"
    if "kapak" not in art and not typographic:
        return
    ms, spec, plan = _manuscript(d), _spec(d), _plan(d)
    cpdf, info = cover_mod.build(ms, _profile(d), spec, page_count(d), None if typographic else Path(art["kapak"]),
                                 plan.style.accent, _back_bg(plan.style.palette), d / "kapak", fonts(),
                                 front_bg=_cover_bg(d, plan.style) if typographic else None)
    preflight.set_boxes(cpdf, spec.bleed)
    write(d, "cover.json", info)


def _cover_bg(d: Path, style) -> str:
    """Tipografik kapağın zemini: sayfa planının paletinden (yoksa üsluptan) beyaz yazıyı okutan ilk renk
    (kontrast ≥ 4,5); hiçbiri tutmazsa vurgu rengi (yazı koyu mürekkebe döner)."""
    from . import plan as plan_mod
    from .palette import contrast
    pl = plan_mod.load(d)
    colors = [c["hex"] for c in ((pl or {}).get("palette") or {}).get("colors", []) if c.get("hex")] + \
        list(style.palette or [])
    return next((c for c in colors if contrast(c) >= 4.5), style.accent)


def rebuild(d: Path) -> None:
    """Seçili sürümlerle iç sayfayı ve kapağı yeniden dizer (yerleşim değişmez), ön kontrolü yeniler. Sayfa planı
    varsa iç sayfa planın şablonuyla (plan.typ) dizilir; plan değişmez."""
    from . import plan as plan_mod
    if plan_mod.exists(d):
        with plan_mod._locked(d):           # plan yazımıyla aynı dizgi klasörü: tek sıra
            plan_mod.build_pdf(d, plan_mod.load(d))
        build_cover(d)
        refresh_preflight(d)
        return
    ms, spec, pm = _manuscript(d), _spec(d), _pagemap(d)
    front = read(d, "front.json")
    art = selected_art(d)
    dz = d / "dizgi"
    (dz / "resim").mkdir(parents=True, exist_ok=True)
    rel = {}
    for key, path in art.items():
        if not key.isdigit():
            continue
        dst = dz / "resim" / Path(path).name
        if not dst.exists():
            dst.hardlink_to(path)
        rel[int(key)] = f"resim/{Path(path).name}"
    ts = Typesetter(dz, fonts())
    pdf = ts.compile(book_data(ms, spec, pm.layout, front, rel), "ic-sayfalar.pdf")
    preflight.set_boxes(pdf, spec.bleed)
    for f in (dz / "onizleme").glob("*.png") if (dz / "onizleme").exists() else []:
        f.unlink()
    build_cover(d)
    refresh_preflight(d)


def _back_bg(palette: list[str]) -> str:
    def light(h):
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b > 215
    return next((c for c in reversed(palette) if light(c)), "#fbf7ef")


def refresh_preflight(d: Path) -> dict:
    import dataclasses

    from . import front as front_mod
    from . import plan as plan_mod
    ms, spec = _manuscript(d), _spec(d)
    pdf = d / "dizgi" / "ic-sayfalar.pdf"
    cpdf = d / "kapak" / "kapak.pdf"
    st = studio_state(d)
    pl = plan_mod.load(d)
    scenes = _plan(d).scenes
    if pl is not None:
        # Sayfa planında: resimler kimlikle, sayfa numarası planın sırasından; metin planın metni.
        at = dict((aid, no) for no, aid in plan_mod.printed_art(pl))
        label = {aid: str(no) for aid, no in at.items()} | {"kapak": "kapak"}
        text_src = plan_mod.PlanText(pl)
        scenes = [dataclasses.replace(sc, page=at[sc.art_id]) for sc in scenes if sc.art_id in at]
        missing = sorted((str(no) for aid, no in at.items() if aid not in st["pages"]), key=int)
    else:
        painted = _pagemap(d).art_pages()
        at = {str(n): n for n in painted}
        label = {k: k for k in at} | {"kapak": "kapak"}
        text_src = ms
        missing = sorted(str(sc.page) for sc in scenes if sc.page in painted and str(sc.page) not in st["pages"])
    shown = set(label)
    renders = [{"key": f"sayfa-{label[k]}", "dpi": pg["versions"][pg["selected"] - 1]["dpi"]}
               for k, pg in st["pages"].items() if pg.get("selected") and k in shown]
    rep = preflight.check(pdf, cpdf if cpdf.exists() else None, text_src, spec, renders,
                          front_mod.missing(read(d, "front.json")["kunye"]), scenes)
    rep["checks"].append({"name": "Sayfa resimleri", "status": "FAIL" if missing else "OK",
                          "detail": "her resimli sayfanın resmi var" if not missing else
                          f"resmi olmayan sayfa: {', '.join(missing)} (stüdyoda «Farklı üret»)"})
    if pl is not None:
        low = plan_mod.low_dpi(d, pl)
        rep["checks"].append({"name": "Yerleşimde çözünürlük", "status": "WARN" if low else "OK",
                              "detail": "her görsel kutusunda en az 300 dpi" if not low else
                              "; ".join(f"{no}. sayfa {kind} {v} dpi" for no, kind, v in low)})
    # basılmayan (eski yerleşimden kalan ya da sayfadan kaldırılan) resim onay istemez
    waiting = sorted((label[k] for k, pg in st["pages"].items() if k in shown and not pg.get("approved")),
                     key=lambda k: (not k.isdigit(), int(k) if k.isdigit() else 0))
    rep["checks"].append({"name": "Editör onayı", "status": "FAIL" if waiting else "OK",
                          "detail": "bütün resimler onaylı" if not waiting else
                          f"onay bekleyen {len(waiting)} resim: {', '.join(waiting[:12])}"})
    rep["checks"].append(_print_check(d, spec, ms.title, ready=not any(c["status"] == "FAIL" for c in rep["checks"])))
    from . import epub as epub_mod
    rep["checks"] += epub_mod.preflight_checks(d)          # e-kitap: bilgi satırı (basımı durdurmaz)
    rep["status"] = ("FAIL" if any(c["status"] == "FAIL" for c in rep["checks"])
                     else "WARN" if any(c["status"] == "WARN" for c in rep["checks"]) else "OK")
    write(d, "preflight.json", rep)
    return rep


def print_paths(d: Path) -> dict[str, Path]:
    return {"ic": d / "baski" / "ic-sayfalar-baski.pdf", "kapak": d / "baski" / "kapak-baski.pdf"}


def _print_check(d: Path, spec: Spec, title: str, ready: bool) -> dict:
    """Baskı PDF'leri (CMYK, PDF/X, kesim işaretli) yalnız öteki denetimler geçince üretilir; iç sayfa ya da
    kapak değişince yenilenir. Matbaa ICC profili tanımlı değilse uyarı."""
    from . import prepress
    name = "Baskı PDF'i (CMYK, PDF/X)"
    if not ready:
        return {"name": name, "status": "WARN", "detail": "öteki denetimler geçince üretilir"}
    src = {"ic": d / "dizgi" / "ic-sayfalar.pdf", "kapak": d / "kapak" / "kapak.pdf"}
    out = print_paths(d)
    notes, info = [], {}
    try:
        for k in ("ic", "kapak"):
            if not src[k].exists():
                continue
            if not out[k].exists() or out[k].stat().st_mtime < src[k].stat().st_mtime:
                info[k] = prepress.make(src[k], out[k], spec.bleed, title)
            c = prepress.check(out[k])
            if not c["output_intent"] or c["non_cmyk_images"] or c["unembedded_fonts"] or not c["boxes"]:
                notes.append(f"{k}: çıktı niyeti {c['output_intent']}, CMYK olmayan görsel {c['non_cmyk_images']}, "
                             f"gömülmemiş font {c['unembedded_fonts']}, kutular {c['boxes']}")
    except Exception as e:  # noqa: BLE001 - denetim sonucu olarak görünür
        return {"name": name, "status": "FAIL", "detail": f"üretilemedi: {e}"[:300]}
    if notes:
        return {"name": name, "status": "FAIL", "detail": "; ".join(notes)[:300]}
    icc, own = prepress.icc_profile()
    if info:
        write(d, "prepress.json", {k: v for k, v in info.items()})
    return {"name": name, "status": "OK" if own else "WARN",
            "detail": (f"CMYK, PDF/X-3, kesim işaretli; profil {Path(icc).name}" if own else
                       f"CMYK, PDF/X-3, kesim işaretli; matbaanın ICC profili tanımlı değil, varsayılan {Path(icc).name} "
                       "kullanıldı (matbaaya sorun, EDITOR_CMYK_ICC)")}


def page_preview(d: Path, page_no: int, width: int) -> Path:
    import pymupdf
    pdf = d / "dizgi" / "ic-sayfalar.pdf"
    if not pdf.exists():
        raise FileNotFoundError("iç sayfalar henüz dizilmedi")
    out = d / "dizgi" / "onizleme" / f"s{page_no}-{width}.png"
    if out.exists() and out.stat().st_mtime >= pdf.stat().st_mtime:
        return out
    out.parent.mkdir(exist_ok=True)
    doc = pymupdf.open(pdf)
    if not 1 <= page_no <= doc.page_count:
        raise FileNotFoundError(page_no)
    page = doc[page_no - 1]
    zoom = width / page.rect.width
    _save_pixmap(page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)), out)
    return out


def cover_preview(d: Path, width: int) -> Path:
    import pymupdf
    pdf = d / "kapak" / "kapak.pdf"
    out = d / "kapak" / f"onizleme-{width}.png"
    if out.exists() and out.stat().st_mtime >= pdf.stat().st_mtime:
        return out
    doc = pymupdf.open(pdf)
    page = doc[0]
    zoom = width / page.rect.width
    _save_pixmap(page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)), out)
    return out


def _save_pixmap(pix, out: Path) -> None:
    """Önizleme PNG'si geçici adla yazılıp yerine konur: aynı sayfayı aynı anda isteyen ikinci istek yarım dosya
    okumasın (ekran bir sayfayı gezginde ve açılımda birlikte isteyebilir)."""
    tmp = out.with_name(f".{out.stem}.{os.getpid()}.{threading.get_ident()}.png")
    pix.save(tmp)
    os.replace(tmp, out)


# ------------------------------------------------------------------ yeniden üretim
async def regenerate(d: Path, key: str, mode: str, direction: str, by: str, variants: int = 1) -> list[int]:
    """`key`: sayfa numarası, sayfa planındaki resim kimliği (a_…) ya da «kapak». Dönen: yeni sürüm numaraları
    (sonuncusu seçili). Planda resim kutusunun ölçüsünde üretilir; plana sonradan eklenen sayfanın sahnesi yoktur,
    yönlendirme zorunludur (sahne = yönlendirme + sayfa metninde adı geçen karakterler)."""
    if mode not in ("fix", "new"):
        raise ValueError("mod fix ya da new olmalı")
    if mode == "fix" and not direction.strip():
        raise ValueError("Düzeltme için neyin değişeceğini yazın")
    from . import plan as plan_mod
    spec, pm, plan = _spec(d), _pagemap(d), _plan(d)
    st = studio_state(d)
    pg = st["pages"].get(key)
    if key == "kapak":
        chars = plan.characters[:1]
        sc = Scene(0, "cover", "", "", [c.name for c in chars], _cover_scene(plan), "", True)
        size = cover_mm(spec)
    elif key.startswith("a_"):
        pl = plan_mod.load(d) or {"pages": []}
        no, ppg = plan_mod.page_of_art(pl, key)
        sc = next((s for s in plan.scenes if s.art_id == key), None)
        if sc is None:
            if ppg is None:
                raise ValueError("bu resim hiçbir sayfada değil")
            if not direction.strip() and not pg:
                raise ValueError("Yeni resim için ne çizileceğini yazın")
            text = plan_mod.page_text(ppg)
            sc = Scene(no, "flow", "", "", [c.name for c in plan.characters if art_mod._mentions(c.name, text)],
                       "", "", False, art_id=key)
        size = ((ppg["art"]["box"]["w"], ppg["art"]["box"]["h"]) if ppg else
                full_mm(spec) if sc.kind == "full" else band_mm(spec, pm))
    else:
        sc = next((s for s in plan.scenes if s.page == int(key)), None)
        if sc is None:
            raise ValueError("bu sayfada resim yok")
        size = full_mm(spec) if sc.kind == "full" else band_mm(spec, pm)
    from .run import FileLlm
    # Görsel modele İngilizcesi gider; sürüm kaydında editörün yazdığı kalır.
    english = await art_mod.direction_en(direction, plan.characters, FileLlm(d / "provenance.jsonl"))
    painter = Painter(d / "resim", plan)
    painter.refs = {n: p for n, p in st.get("characters", {}).items()}
    base = pg["versions"][pg["selected"] - 1]["path"] if (mode == "fix" and pg and pg.get("selected")) else None
    if mode == "fix" and not base:
        raise ValueError("düzeltilecek görsel yok")
    made = []
    try:
        for _ in range(max(1, min(variants, 3))):
            v_next = len(studio_state(d)["pages"].get(key, {"versions": []})["versions"]) + 1
            seed = random.randint(1, 2**31 - 1)
            if key == "kapak":
                rd = await _cover_render(painter, plan, spec, v_next, seed, english, base)
            else:
                rd = await painter.page(sc, *size, version=v_next, seed=seed, direction=english, base_image=base,
                                        key=f"resim-{key}" if key.startswith("a_") else None)
            made.append(add_version(d, key, rd.path, mode=mode, prompt=direction, seed=seed, by=by, dpi=rd.dpi,
                                    base=pg["selected"] if base and pg else None, prompt_en=english))
    finally:
        await painter.close()
    import asyncio
    await asyncio.to_thread(rebuild, d)
    return made


def _cover_scene(plan: ArtPlan) -> str:
    hero = plan.characters[0] if plan.characters else None
    setting = plan.scenes[0].setting if plan.scenes else ""
    return (f"{hero.name} as the hero of the book, in its world: {setting}." if hero else setting)


async def _cover_render(painter: Painter, plan: ArtPlan, spec: Spec, v: int, seed: int, direction: str,
                        base: str | None):
    from .images import Render, size_for, target_px, upscale
    W, H, dpi = size_for(*cover_mm(spec))
    t = time.time()
    if base:
        prompt = (f"Edit the first reference image: {direction.strip()}. Keep everything else as it is. "
                  "Keep the top third calm and empty for the title. No text or letters anywhere.")
        png = await painter._edit(prompt, [Path(base).read_bytes()], W, H, seed)
        mode = "fix"
    else:
        scene = _cover_scene(plan) + (f" Editor's direction: {direction.strip()}." if direction.strip() else "")
        prompt = cover_mod.front_art_prompt(scene, plan.style.style_prompt)
        refs = [painter.refs[c.name] for c in plan.characters[:3] if c.name in painter.refs]
        png = (await painter._edit(prompt, [Path(r).read_bytes() for r in refs], W, H, seed) if refs
               else await painter._generate(prompt, W, H, seed))
        mode = "new"
    png, _how = await painter.enlarge(png, *target_px(*cover_mm(spec)))
    path = painter._save(f"kapak.v{v}", png)
    return Render(f"kapak.v{v}", path, W, H, dpi, seed, [], mode, round(time.time() - t, 1), prompt)


# ------------------------------------------------------------------ sayfa planı: figür, zemin ayıklama, büyütme
def _save_asset(d: Path, rel: str, data: bytes) -> None:
    (d / rel).parent.mkdir(parents=True, exist_ok=True)
    tmp = d / (rel + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(d / rel)


async def make_figure(d: Path, gid: str, prompt: str, characters: list[str], page: str | None, by: str) -> dict:
    """Serbest figür (GPU): tarif İngilizceye çevrilir, kitabın üslubunda düz tek renk zemin üzerinde çizilir
    (renk kitabın paletinden en uzak anahtar renk), zemin ayıklanır (photo.cutout), figur/<gid>.png saydam kaydedilir,
    kütüphaneye girer; `page` verildiyse o sayfaya eklenir. Ham çizim figur/<gid>.ham.png olarak saklanır."""
    from . import photo, plan as plan_mod
    from .run import FileLlm
    ap = _plan(d)
    chars = [c for c in ap.characters if c.name in characters]
    english = await art_mod.direction_en(prompt, ap.characters, FileLlm(d / "provenance.jsonl"))
    key_name, key_hex = photo.key_color(ap.style.palette)
    painter = Painter(d / "figur", ap)
    painter.refs = dict(studio_state(d).get("characters", {}))
    seed = random.randint(1, 2**31 - 1)
    try:
        raw, mode = await painter.figure(english, chars, key_name, key_hex, seed)
    finally:
        await painter.close()
    _save_asset(d, f"figur/{gid}.ham.png", raw)
    import asyncio
    png, info = await asyncio.to_thread(photo.cutout, raw, True)
    rel = f"figur/{gid}.png"
    _save_asset(d, rel, png)
    meta = {"kind": "figure", "prompt": prompt, "prompt_en": english, "path": rel, "w_px": info["w_px"],
            "h_px": info["h_px"], "alpha": True, "by": by, "at": plan_mod._now(), "characters": [c.name for c in chars],
            "seed": seed, "mode": mode, "key": key_hex, "cutout": {k: info[k] for k in ("bg", "noise", "flat", "removed")}}
    await asyncio.to_thread(plan_mod.add_asset, d, gid, meta, page, by, post="sync")
    return {"asset": gid, "flat": info["flat"]}


def cutout_asset(d: Path, gid: str, new_gid: str, by: str) -> dict:
    """Fotoğrafın (ya da figürün) zeminini ayıklar → yeni saydam varlık (`derived_from`); sayfaya konmaz, editör
    önizleyip onaylayınca kutu yeni varlığa geçer (sayfa PUT'u). Düz olmayan zemin `flat: false` ile döner."""
    from . import photo, plan as plan_mod
    pl = plan_mod.load(d)
    a = (pl or {}).get("assets", {}).get(gid)
    if not a:
        raise KeyError(f"kütüphanede yok: {gid}")
    png, info = photo.cutout((d / a["path"]).read_bytes(), a.get("kind") == "figure")
    rel = f"{'figur' if a.get('kind') == 'figure' else 'foto'}/{new_gid}.png"
    _save_asset(d, rel, png)
    meta = {"kind": a.get("kind", "photo"), "path": rel, "w_px": info["w_px"], "h_px": info["h_px"], "alpha": True,
            "name": a.get("name"), "by": by, "at": plan_mod._now(), "derived_from": gid,
            "cutout": {k: info[k] for k in ("bg", "noise", "flat", "removed")}}
    plan_mod.add_asset(d, new_gid, meta, None, by, post="sync")
    return {"asset": new_gid, "flat": info["flat"],
            "note": "" if info["flat"] else "Zemin düz değil; sonucu önizleyip onaylayın."}


async def upscale_asset(d: Path, gid: str, new_gid: str, page: str, item: str, by: str) -> dict:
    """«Kaliteyi artır» (GPU): yerleştirildiği kutuda 300 dpi'ye yetecek katsayıyla (2–4) büyütür → yeni varlık
    (`derived_from`, `upscale`); özgün silinmez, sayfaya konmaz (editör onaylayınca kutu yeni varlığa geçer).
    Büyütme servisi açılamazsa basit büyütme yapılır ve sonuçta yazılır. 4× de yetmezse ulaşılan dpi döner."""
    import asyncio
    import io

    from PIL import Image

    from . import photo, plan as plan_mod
    pl = plan_mod.load(d)
    bx, fit, used = plan_mod.placement(pl, page, item)
    if used != gid:
        raise ValueError("bu kutudaki görsel başka bir varlık")
    a = pl["assets"][gid]
    now = photo.dpi(a["w_px"], a["h_px"], bx, fit)
    f = photo.upscale_factor(now)
    src = Image.open(d / a["path"])
    alpha = src.getchannel("A") if src.mode in ("RGBA", "LA") else None
    W, H = src.width * f, src.height * f
    buf = io.BytesIO()
    src.convert("RGB").save(buf, "PNG")
    painter = Painter(d / "foto", _plan(d))
    try:
        png, how = await painter.enlarge(buf.getvalue(), W, H)
    finally:
        await painter.close()
    out = Image.open(io.BytesIO(png)).convert("RGB")
    if out.size != (W, H):
        out = out.resize((W, H), Image.Resampling.LANCZOS)
    b2 = io.BytesIO()
    if alpha is not None:
        out.putalpha(alpha.resize((W, H), Image.Resampling.LANCZOS))
        out.save(b2, "PNG", compress_level=6)
        ext = "png"
    else:
        out.save(b2, "JPEG", quality=95, subsampling=0)
        ext = "jpg"
    rel = f"foto/{new_gid}.{ext}"
    await asyncio.to_thread(_save_asset, d, rel, b2.getvalue())
    reached = photo.dpi(W, H, bx, fit)
    note = "Yalnız büyütüldü, keskinleştirilemedi." if how else ""
    meta = {"kind": a.get("kind", "photo"), "path": rel, "w_px": W, "h_px": H, "alpha": alpha is not None,
            "name": a.get("name"), "by": by, "at": plan_mod._now(), "derived_from": gid, "upscale": f,
            "dpi": int(round(reached)), "sharpened": not how, **({"note": note} if note else {})}
    await asyncio.to_thread(plan_mod.add_asset, d, new_gid, meta, None, by, post="sync")
    return {"asset": new_gid, "factor": f, "dpi_before": int(round(now)), "dpi": int(round(reached)),
            "enough": round(reached) >= photo.LOW_DPI, "note": note}
