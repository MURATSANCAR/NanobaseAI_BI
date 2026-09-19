"""Temporal activities: thin wrappers over the editor modules."""

from __future__ import annotations

import asyncio
import os
import subprocess

from temporalio import activity

from .. import __version__, db, document, knowledge, ledger, prompts, quality, retrieval, summary, vision
from ..config import settings
from ..llm import aliases, client


def _t(fn, *a):
    return asyncio.to_thread(fn, *a)


def _code_version() -> str:
    v = os.environ.get("EDITOR_CODE_VERSION")
    if v:
        return v
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return __version__


@activity.defn
async def set_step(job_id: str, n: int, label: str, extra: dict) -> None:
    await _t(db.one, "UPDATE analysis_job SET status='RUNNING', step=%s, progress=progress || %s"
             " WHERE id=%s RETURNING id", f"{n}/15 {label}",
             db.J({f"step_{n:02d}": {"label": label, **extra}}), job_id)


@activity.defn
async def prepare_generation(job_id: str) -> dict:
    """Step 1: new generation (never overwrites an old one) with the model and
    prompt manifests and the editor corrections that apply to this book."""
    job = await _t(db.one, "SELECT j.book_version_id, bv.book_id FROM analysis_job j JOIN book_version"
                   " bv ON bv.id=j.book_version_id WHERE j.id=%s", job_id)
    manifest = await aliases()
    pm = await _t(prompts.register_all)

    def mk():
        with db.tx() as c:
            corr = ledger.corrections_for_book(c, job["book_id"])
            row = c.execute(
                "INSERT INTO generation(job_id, book_version_id, code_version, model_manifest,"
                " prompt_manifest, corrections_applied) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (job_id, job["book_version_id"], _code_version(),
                 db.J({a: {"real_model": m["real_model"], "revision": m["revision"]} for a, m in manifest.items()}),
                 db.J(pm), db.J([{**x, "created_at": str(x["created_at"])} for x in corr]))).fetchone()
        return str(row["id"])

    gid = await _t(mk)
    return {"generation_id": gid, "book_version_id": str(job["book_version_id"])}


@activity.defn
async def page_manifest(book_version_id: str) -> dict:
    return await _t(document.create_page_manifest, book_version_id)


@activity.defn
async def text_layer(generation_id: str, book_version_id: str) -> dict:
    return await _t(document.extract_text_layer, generation_id, book_version_id)


@activity.defn
async def ocr_page(generation_id: str, book_version_id: str, page_no: int) -> dict:
    return await document.run_ocr(generation_id, book_version_id, page_no)


@activity.defn
async def scan_page_fast(generation_id: str, page_no: int) -> dict:
    return await vision.analyze_page_visual(generation_id, page_no, "fast")


@activity.defn
async def scan_page_deep(generation_id: str, page_no: int) -> dict:
    return await vision.analyze_page_visual(generation_id, page_no, "deep")


@activity.defn
async def persist_visual(generation_id: str) -> dict:
    await _t(knowledge.text_chunks, generation_id)   # records FRONT_MATTER page roles first
    pages = await _t(db.all_rows, "SELECT DISTINCT page_no FROM page_scan WHERE generation_id=%s",
                     generation_id)
    out = [await _t(vision.persist_page_visual, generation_id, r["page_no"]) for r in pages]
    return {"pages": len(out), "visual_mentions": sum(o.get("visual_mentions", 0) for o in out),
            "text_visual_candidates": sum(o.get("text_visual_candidates", 0) for o in out)}


@activity.defn
async def text_chunks(generation_id: str) -> list[list[int]]:
    return [list(c) for c in await _t(knowledge.text_chunks, generation_id)]


@activity.defn
async def extract_chunk(generation_id: str, chunk: list[int]) -> dict:
    return await knowledge.extract_chunk(generation_id, chunk[0], chunk[1])


@activity.defn
async def resolve_identity(generation_id: str) -> dict:
    return await knowledge.resolve_character_identity(generation_id)


@activity.defn
async def continuity_checks(generation_id: str) -> dict:
    """Deep model on characters seen on >= 3 pages (analysis §6: süreklilik)."""
    rows = await _t(db.all_rows,
                    "SELECT ch.canonical_name, array_agg(DISTINCT cm.page_no ORDER BY cm.page_no) AS pages"
                    " FROM character ch JOIN character_mention cm ON cm.character_id=ch.id AND cm.via<>'TEXT'"
                    " WHERE ch.generation_id=%s GROUP BY ch.canonical_name HAVING count(DISTINCT cm.page_no)>=3",
                    generation_id)

    async def one(r):
        ps = r["pages"]
        pick = sorted({ps[round(i * (len(ps) - 1) / 5)] for i in range(6)}) if len(ps) > 6 else ps
        res = await vision.compare_character_appearances(generation_id, r["canonical_name"], pick)
        return {"character": r["canonical_name"], "pages": pick,
                "differences": len(res["differences"]), "same_everywhere": res["same_character_everywhere"]}

    return {"checked": await asyncio.gather(*(one(r) for r in rows))}


@activity.defn
async def verify_modality(generation_id: str) -> dict:
    return await knowledge.verify_event_modality(generation_id)


@activity.defn
async def merge_events(generation_id: str) -> dict:
    return await knowledge.merge_events(generation_id)


@activity.defn
async def emotions_themes(generation_id: str) -> dict:
    return await knowledge.link_emotions_and_themes(generation_id)


@activity.defn
async def embed_index(generation_id: str) -> dict:
    return await retrieval.embed_passages(generation_id)


@activity.defn
async def list_chapters(generation_id: str) -> list[dict]:
    return [c for c in await _t(knowledge.chapters, generation_id) if c["title"] != "Ön sayfalar"]


@activity.defn
async def chapter_summary(generation_id: str, chapter: dict) -> dict:
    return await summary.chapter_summary(generation_id, chapter)


@activity.defn
async def book_summary(generation_id: str) -> dict:
    return await summary.book_summary(generation_id)


@activity.defn
async def critic(generation_id: str) -> dict:
    return await quality.critic_pass(generation_id)


@activity.defn
async def contradictions(generation_id: str) -> dict:
    found = await knowledge.detect_contradictions(generation_id)
    queued = await _t(quality.contradictions_to_queue, generation_id)
    return {**found, **queued}


@activity.defn
async def regression(generation_id: str) -> dict:
    r = await _t(quality.run_regression_suite, generation_id)
    return {"passed": r["passed"], "failed": [c["check"] for c in r["checks"] if not c["passed"]],
            "counts": r["counts"]}


@activity.defn
async def report(generation_id: str) -> dict:
    r = await _t(quality.create_analysis_report, generation_id, "ANALYSIS", None)
    await _t(db.one, "UPDATE generation SET sealed_at=now() WHERE id=%s RETURNING id", generation_id)
    return {"report_id": r["report_id"]}


@activity.defn
async def finish_job(job_id: str, status: str, result: dict) -> None:
    await _t(db.one, "UPDATE analysis_job SET status=%s, finished_at=now(), progress=progress || %s,"
             " error=%s WHERE id=%s RETURNING id", status, db.J({"result": result}),
             result.get("error"), job_id)


@activity.defn
async def release_models(aliases_: list[str]) -> dict:
    """Stop the named models (or all, when no other job is running) so the
    editor does not hold GPU memory after its work is done."""
    s = settings()
    h = {"authorization": f"Bearer {s.gateway_internal_key}"}
    if aliases_:
        for a in aliases_:
            await client().post(f"/internal/stop/{a}", headers=h)
        return {"stopped": aliases_}
    busy = await _t(db.one, "SELECT count(*) n FROM analysis_job WHERE status='RUNNING'")
    if (busy or {}).get("n", 0) > 0:
        return {"stopped": [], "reason": "another job is running"}
    r = await client().post("/internal/stop-all", headers=h)
    return r.json()


ALL = [set_step, prepare_generation, page_manifest, text_layer, ocr_page, scan_page_fast, scan_page_deep,
       persist_visual, text_chunks, extract_chunk, resolve_identity, continuity_checks, verify_modality,
       merge_events, emotions_themes, embed_index, list_chapters, chapter_summary, book_summary, critic,
       contradictions, regression, report, finish_job, release_models]
