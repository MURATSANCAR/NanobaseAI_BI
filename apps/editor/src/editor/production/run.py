"""Basıma hazırlık hattı: kitap (okunmuş kayıt ya da Word) → baskıya hazır iç sayfa + kapak PDF'i.

    python -m editor.production.run --generation <okuma nesli> [--no-images]
    python -m editor.production.run --docx <dosya> [--no-images]

İş klasörü studio.py'de anlatılır. Her adımdan sonra state.json yazılır (adım, durum, süre, özet);
ekran ilerlemeyi buradan okur. Model çağrılarının kaydı provenance.jsonl. Resimler v1 sürümü olarak
kaydedilir; dizgi ve kapak stüdyonun `rebuild`'inden geçer, sonraki düzeltmelerle aynı yol.
Adımlar: içerik → CRM → profil → kurallar → üslup → karakterler → yerleşim → karakter resimleri →
sayfa resimleri → kapak → dizgi → ön kontrol.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
import traceback
from pathlib import Path

from ..llm import Llm, aliases
from . import art as art_mod
from . import front as front_mod
from . import profile as profile_mod
from . import spec as spec_mod
from . import studio
from .images import Painter
from .manuscript import from_docx, from_generation
from .typeset import Typesetter

STEPS = [("icerik", "İçerik okundu"), ("crm", "CRM proje verisi"), ("profil", "Yaş ve tür profili"),
         ("kurallar", "Baskı kuralları"), ("uslup", "Üslup"), ("karakterler", "Karakterler"),
         ("yerlesim", "Sayfa yerleşimi"), ("karakter_resimleri", "Karakter referansları"),
         ("sayfa_resimleri", "Sayfa resimleri"), ("kapak", "Kapak açılımı"), ("dizgi", "Dizgi (PDF)"),
         ("on_kontrol", "Ön baskı denetimi")]


class FileLlm(Llm):
    """Model çağrısı kaydını okuma defterine değil işin klasörüne yazar (basıma hazırlık bir okuma
    nesline ait değil)."""

    def __init__(self, path: Path):
        super().__init__(None)
        self.path = path
        self.n = 0

    async def _record(self, alias, prompt, pages, request, response, usage, t0, ok, error) -> int:
        meta = (await aliases()).get(alias, {})
        self.n += 1
        row = {"id": self.n, "alias": alias, "real_model": meta.get("real_model"), "revision": meta.get("revision"),
               "prompt": f"{prompt.name}@{prompt.version}" if prompt else None, "pages": pages,
               "request_sha": hashlib.sha256(json.dumps(request, sort_keys=True, default=str).encode()).hexdigest()[:16],
               "usage": usage, "ms": int((time.time() - t0) * 1000), "ok": ok, "error": error}
        with self.path.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return self.n


class State:
    def __init__(self, d: Path, keep: bool = False):
        self.d = d
        old = studio.read(d, "state.json") if keep else None
        self.data = old or {"title": "", "started": time.time(), "finished": None, "status": "running", "error": None,
                     "steps": [{"key": k, "label": l, "status": "waiting", "seconds": None, "summary": ""}
                               for k, l in STEPS]}
        self.t0: dict[str, float] = {}
        self.flush()

    def step(self, key):
        return next(s for s in self.data["steps"] if s["key"] == key)

    def start(self, key):
        self.t0[key] = time.time()
        self.step(key)["status"] = "running"
        self.flush()

    def done(self, key, summary="", status="done", **extra):
        s = self.step(key)
        s.update(status=status, summary=summary, seconds=round(time.time() - self.t0.get(key, time.time()), 1), **extra)
        self.flush()

    def flush(self):
        studio.write(self.d, "state.json", self.data)


async def run(d: Path, images: bool = True, seed: int = 42) -> dict:
    job = studio.read(d, "job.json")
    st = State(d)
    try:
        await _run(d, job, st, images, seed)
        st.data["status"] = "done"
    except Exception as e:  # noqa: BLE001 - adım hata durumuyla kapanır, ekran sebebi gösterir
        running = next((s for s in st.data["steps"] if s["status"] == "running"), None)
        if running:
            running.update(status="fail", summary=str(e)[:300])
        st.data.update(status="fail", error=f"{type(e).__name__}: {e}"[:500])
        (d / "hata.txt").write_text(traceback.format_exc())
    st.data["finished"] = time.time()
    st.flush()
    return st.data


async def _run(d: Path, job: dict, st: State, images: bool, seed: int) -> None:
    llm = FileLlm(d / "provenance.jsonl")
    src = job["source"]
    by = job.get("created_by", "")

    st.start("icerik")
    ms = await asyncio.to_thread(from_generation, src["generation_id"]) if src.get("generation_id") \
        else await asyncio.to_thread(from_docx, src["docx"])
    st.data["title"] = ms.title
    words = sum(len(b.text.split()) for _, _, b in ms.blocks())
    st.done("icerik", f"{len(ms.chapters)} bölüm · {words} kelime")
    st.start("crm")
    crm_ok = bool(ms.source.get("crm_book_id"))
    st.done("crm", (f"{ms.title} · {ms.author} · ISBN {ms.meta.get('ISBN')}" if crm_ok
                    else "CRM kaydı bulunamadı; kitap bilgisi elle tamamlanmalı"),
            status="done" if crm_ok else "warn",
            crm={"title": ms.title, "author": ms.author, **{k: ms.meta.get(k) for k in
                 ("ISBN", "STOCK_CODE", "SERIES", "GENRE", "AGE_RANGE", "CRM_SUMMARY")}})
    studio.write(d, "manuscript.json", ms.to_json())

    st.start("profil")
    prof = await profile_mod.build(ms, llm)
    st.done("profil", f"{prof.age_min}–{prof.age_max} yaş · {prof.genre} · Ateşman {prof.reading['atesman']}",
            status="warn" if prof.disagreement else "done")
    studio.write(d, "profile.json", prof.to_json())
    st.start("kurallar")
    spec = spec_mod.build(prof)
    st.done("kurallar", f"{spec.trim_w:g}×{spec.trim_h:g} mm · {spec.body_font} · {spec.paper}", reasons=spec.reasons)
    studio.write(d, "spec.json", spec.to_json())

    st.start("uslup")
    style = await art_mod.style(ms, prof, llm)
    st.done("uslup", f"{style.medium} · vurgu {style.accent}", palette=style.palette)
    st.start("karakterler")
    chars = await art_mod.characters(ms, prof, style, llm)
    st.done("karakterler", ", ".join(c.name for c in chars), names=[c.name for c in chars])

    st.start("yerlesim")
    fields = await front_mod.kunye_fields(ms, llm)
    front = {"kunye": front_mod.kunye(ms, fields), "kunye_fields": fields, "manual": {},
             "bios": await front_mod.bios(ms, llm)}
    studio.write(d, "front.json", front)
    ts = Typesetter(d / "dizgi", studio.fonts())
    pm = await asyncio.to_thread(ts.fit, ms, spec, front, style.accent)
    studio.write(d, "pagemap.json", pm.to_json())
    plan = art_mod.ArtPlan(style, chars)
    plan.scenes = await art_mod.scenes(ms, prof, chars, pm, llm)
    studio.write(d, "artplan.json", plan.to_json())
    st.done("yerlesim", f"{len(pm.pages)} sayfa · resim bandı %{pm.layout.art_ratio * 100:.0f} · "
                        f"{pm.layout.body_size:g} pt · {len(plan.scenes)} resim", pages=len(pm.pages))

    await _finish(d, st, plan, spec, pm, by, seed, images)


async def _finish(d: Path, st: State, plan, spec, pm, by: str, seed: int, images: bool) -> None:
    """Resimler, kapak, dizgi, ön kontrol. Yalnız eksik olanı çizer: ilk koşu da, yarıda kalan işin
    devamı da buradan geçer. Tek resmin hatası hattı durdurmaz; sayfa «resim yok» kalır, hata kayda
    geçer ve stüdyoda «Farklı üret» ile tamamlanır. Bitince görsel model beklemeden kapatılır."""
    if images:
        painter = Painter(d / "resim", plan, seed=seed)
        try:
            sd = studio.studio_state(d)
            st.start("karakter_resimleri")
            if not sd.get("characters"):
                sd["characters"] = await painter.character_refs()
                studio.write(d, "studio.json", sd)
            painter.refs = dict(sd["characters"])
            st.done("karakter_resimleri", f"{len(painter.refs)} karakter")
            st.start("sayfa_resimleri")
            band, full = studio.band_mm(spec, pm), studio.full_mm(spec)
            have = set(studio.studio_state(d)["pages"])
            failed: dict[str, str] = {}
            painted = pm.art_pages()
            todo = [sc for sc in plan.scenes if sc.page in painted]      # sayfada basılmayacak resim çizilmez
            for i, sc in enumerate(todo, 1):
                if str(sc.page) not in have:
                    try:
                        rd = await painter.page(sc, *(full if sc.kind == "full" else band))
                        studio.add_version(d, str(sc.page), rd.path, mode=rd.mode, prompt="", seed=rd.seed,
                                           by=by, dpi=rd.dpi)
                    except Exception as e:  # noqa: BLE001 - tek sayfa hattı durdurmaz
                        failed[str(sc.page)] = f"{type(e).__name__}: {e}"[:300]
                st.step("sayfa_resimleri")["progress"] = [i, len(todo)]
                st.step("sayfa_resimleri")["failed"] = failed
                st.flush()
            modes: dict[str, int] = {}
            for p in studio.studio_state(d)["pages"].values():
                if p["versions"]:
                    modes[p["versions"][0]["mode"]] = modes.get(p["versions"][0]["mode"], 0) + 1
            fell = modes.get("edit_failed→generate", 0)
            parts = [f"{len(todo) - len(failed)}/{len(todo)} resim"]
            if failed:
                parts.append(f"çizilemeyen sayfa: {', '.join(sorted(failed, key=int))} (stüdyoda yeniden üretin)")
            parts.append(f"{fell} resim karakter referansı olmadan çizildi" if fell else
                         f"{modes.get('edit', 0)} resim karakter referanslı")
            st.done("sayfa_resimleri", " · ".join(parts), status="warn" if failed or fell else "done", modes=modes)
            st.start("kapak")
            if "kapak" not in studio.studio_state(d)["pages"]:
                try:
                    rd = await studio._cover_render(painter, plan, spec, 1, seed, "", None)
                    studio.add_version(d, "kapak", rd.path, mode="new", prompt="", seed=seed, by=by, dpi=rd.dpi)
                except Exception as e:  # noqa: BLE001
                    st.step("kapak")["error"] = f"{type(e).__name__}: {e}"[:300]
        finally:
            # Resimler bitti (ya da hat düştü): görsel modeli beklemeden kapat, kart ana modele dönsün.
            st.data["gpu_release"] = await painter.release()
            await painter.close()
    else:
        for k in ("karakter_resimleri", "sayfa_resimleri", "kapak"):
            st.start(k)
            st.done(k, "atlandı", status="skipped")

    st.start("dizgi")
    await asyncio.to_thread(studio.rebuild, d)
    info = studio.read(d, "cover.json")
    if images:
        err = st.step("kapak").get("error")
        st.done("kapak", f"{info['size_mm'][0]}×{info['size_mm'][1]} mm · {info['binding']} · sırt {info['spine_mm']} mm"
                if info else f"kapak resmi çizilemedi: {err or 'bilinmiyor'} (stüdyoda yeniden üretin)",
                status="done" if info else "warn")
    st.done("dizgi", "ic-sayfalar.pdf" + (" + kapak.pdf" if info else ""))
    st.start("on_kontrol")
    rep = studio.read(d, "preflight.json")
    bad = [c for c in rep["checks"] if c["status"] != "OK"]
    st.done("on_kontrol", "; ".join(f"{c['name']}: {c['status']}" for c in bad) or "hepsi geçti",
            status={"OK": "done", "WARN": "warn", "FAIL": "fail"}[rep["status"]])


async def resume(d: Path, seed: int = 42) -> dict:
    """Yarıda kalan işi kaldığı yerden sürdürür: metin, profil, yerleşim ve çizilmiş resimler korunur,
    yalnız eksik resimler, kapak, dizgi ve ön kontrol yapılır."""
    job = studio.read(d, "job.json")
    st = State(d, keep=True)
    st.data.update(status="running", error=None, finished=None)
    for s in st.data["steps"]:
        if s["key"] in ("karakter_resimleri", "sayfa_resimleri", "kapak", "dizgi", "on_kontrol") and s["status"] != "done":
            s.update(status="waiting", summary="")
    st.flush()
    try:
        await _finish(d, st, studio._plan(d), studio._spec(d), studio._pagemap(d), job.get("created_by", ""), seed, True)
        st.data["status"] = "done"
    except Exception as e:  # noqa: BLE001
        running = next((s for s in st.data["steps"] if s["status"] == "running"), None)
        if running:
            running.update(status="fail", summary=str(e)[:300])
        st.data.update(status="fail", error=f"{type(e).__name__}: {e}"[:500])
        (d / "hata.txt").write_text(traceback.format_exc())
    st.data["finished"] = time.time()
    st.flush()
    return st.data


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--generation")
    g.add_argument("--docx")
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--by", default="cli")
    a = ap.parse_args()
    d = studio.new_job({"generation_id": a.generation} if a.generation else {"docx": a.docx}, a.by)
    res = asyncio.run(run(d, images=not a.no_images, seed=a.seed))
    print(d.name, json.dumps([{k: s[k] for k in ("label", "status", "seconds", "summary")} for s in res["steps"]],
                             ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
