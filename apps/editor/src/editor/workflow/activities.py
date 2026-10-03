"""Temporal activities: thin wrappers over the editor modules."""

from __future__ import annotations

import asyncio
import os
import subprocess

from temporalio import activity

from .. import __version__, book_type, catalog, db, document, figure_identity, knowledge, ledger, prompts, quality, retrieval, summary, vision
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
    job = await _t(db.one, "SELECT j.book_version_id, bv.book_id, j.profile, j.progress FROM analysis_job j"
                   " JOIN book_version bv ON bv.id=j.book_version_id WHERE j.id=%s", job_id)
    # The job's profile (editor.archive): 'full' as before, 'archive' reads for questions only, 'redaction'
    # runs what an archive reading left out — on the archive generation itself, not on a new one.
    profile = job["profile"] or "full"
    if profile == "redaction":
        target = (job["progress"] or {}).get("generation_id")
        g = await _t(db.one, "SELECT id, book_version_id FROM generation WHERE id=%s", target) if target else None
        if g is None or str(g["book_version_id"]) != str(job["book_version_id"]):
            raise ValueError(f"redaction job {job_id}: generation {target!r} is not this book version's")
        return {"generation_id": str(g["id"]), "book_version_id": str(g["book_version_id"]), "profile": profile}
    existing = await _t(db.one, "SELECT id,book_version_id FROM generation WHERE job_id=%s", job_id)
    if existing:
        return {"generation_id": str(existing["id"]), "book_version_id": str(existing["book_version_id"]),
                "profile": profile}
    manifest = await aliases()
    pm = await _t(prompts.register_all)

    def mk():
        with db.tx() as c:
            corr = ledger.corrections_for_book(c, job["book_id"])
            row = c.execute(
                "INSERT INTO generation(job_id, book_version_id, code_version, model_manifest,"
                " prompt_manifest, corrections_applied) VALUES (%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (job_id) DO NOTHING RETURNING id",
                (job_id, job["book_version_id"], _code_version(),
                 db.J({a: {"real_model": m["real_model"], "revision": m["revision"]} for a, m in manifest.items()}),
                 db.J(pm), db.J([{**x, "created_at": str(x["created_at"])} for x in corr]))).fetchone()
            if row is None:
                row = c.execute("SELECT id FROM generation WHERE job_id=%s", (job_id,)).fetchone()
        return str(row["id"])

    gid = await _t(mk)
    return {"generation_id": gid, "book_version_id": str(job["book_version_id"]), "profile": profile}


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
async def archive_visual_pages(book_version_id: str) -> dict:
    """Archive profile: the pages that carry a picture (and the cover); a text-only page never goes
    to the vision model (editor.archive.visual_pages)."""
    from .. import archive
    return await _t(archive.visual_pages, book_version_id)


@activity.defn
async def archive_outputs(generation_id: str) -> dict:
    """Archive profile's rebuild_outputs: the same outputs, validated without contradiction detection
    and the editor's queue (editor.archive.run_outputs)."""
    from .. import archive
    return await archive.run_outputs(generation_id)


@activity.defn
async def archive_recommend(generation_id: str) -> dict:
    """Archive profile: Zeki AI's category and age suggestion from the read content, in the publisher site's
    own category tree (editor.recommend). A suggestion only: the book's profile is not changed."""
    from .. import recommend
    return await recommend.run(generation_id)


# Page scans, visual identity, metadata, identity and final-read checks run on their own event loop
# (editor.offloop): their page renders, page-text reads and DB transactions are synchronous, and on
# the worker's shared loop they stopped the heartbeats of every activity of every book being read
# (worker log 2026-10-03: source.read 33 s, embed_figures 22 s, catalog source.load 28 s).
def _own_loop(fn, *a, **k):
    from .. import offloop
    return offloop.run(fn, *a, **k)


@activity.defn
async def scan_page_fast(generation_id: str, page_no: int) -> dict:
    return await _own_loop(vision.analyze_page_visual, generation_id, page_no, "fast")


@activity.defn
async def scan_page_deep(generation_id: str, page_no: int) -> dict:
    return await _own_loop(vision.analyze_page_visual, generation_id, page_no, "deep")


@activity.defn
async def scan_page_deep_key(generation_id: str, page_no: int) -> dict:
    return await _own_loop(vision.analyze_page_visual, generation_id, page_no, "deep", ["IMPORTANT_EVENT"])


@activity.defn
async def narrative_roles(generation_id: str) -> dict:
    return await knowledge.assign_narrative_roles(generation_id)


@activity.defn
async def persist_visual(generation_id: str, phase: str = "all") -> dict:
    """A page's visual records are written once, when its best scan is final:
    phase "deep" = pages that already have their deep scan; "all" = the rest."""
    # Chapter discovery does not assign page roles or remove source pages.
    pages = await _t(db.all_rows, "SELECT DISTINCT page_no FROM page_scan WHERE generation_id=%s"
                     " AND (%s <> 'deep' OR pass='DEEP')", generation_id, phase)
    out = [await _t(vision.persist_page_visual, generation_id, r["page_no"]) for r in pages]
    return {"pages": len(out), "visual_mentions": sum(o.get("visual_mentions", 0) for o in out)}


@activity.defn
async def confirm_text_visual(generation_id: str) -> dict:
    return await vision.confirm_text_visual(generation_id)


@activity.defn
async def text_chunks(generation_id: str) -> list[list[int]]:
    """Every book is read for people, events, emotions and themes, whatever its kind (user
    decision 2026-09-24). The profile (editor.book_type) is decided here, the first step
    that needs it, while the director model is up; later steps read it.

    A file that is not a book (catalogue, bulletin, brochure, cover only: book_type.NOT_A_BOOK) yields no
    chunks: no characters or events are read from it. The workflow is unchanged (the fan-out over no chunk
    is empty), so recorded histories replay as they were."""
    prof = await book_type.profile(generation_id)
    if not book_type.is_book(prof):
        return []
    return [list(c) for c in await _t(knowledge.text_chunks, generation_id)]


@activity.defn
async def extract_chunk(generation_id: str, chunk: list[int]) -> dict:
    return await knowledge.extract_chunk(generation_id, chunk[0], chunk[1])


@activity.defn
async def resolve_identity(generation_id: str, strict: bool = False) -> dict:
    """Runs on its own event loop (editor.offloop): the write phase reads the whole book's text and
    screens every name synchronously, and on the shared loop it cost heartbeats (2026-10-03).

    Old workflows (no `strict`): on the last attempt the policy allows, a failure that would otherwise be
    retried leaves the mentions unresolved and asks the editor instead of ending the reading.
    `strict` (workflow «infra-step-retry-v1»): an infrastructure failure is never turned into an editor
    question — it is raised on every attempt and the workflow retries the step, then fails the job;
    a deterministic failure still falls back to smaller windows and then to the editor."""
    from .. import offloop
    from .workflows import RETRY
    final = not strict and activity.info().attempt >= (RETRY.maximum_attempts or 1)
    return await offloop.run(knowledge.resolve_character_identity, generation_id, final_attempt=final)


@activity.defn
async def identity_unresolved(generation_id: str, error: str) -> dict:
    """The workflow's last resort when resolve_identity itself could not finish."""
    return await _t(knowledge.identity_unresolved, generation_id, error)


@activity.defn
async def proofreading(generation_id: str, resume: bool = False) -> dict:
    """Final-read checks; each isolated, none can fail the book for a problem of its own (editor.proofing).

    A retry (attempt > 1, or `resume` from the workflow's own retry round) continues where the lost
    attempt stopped: checks already recorded at their version are not run again. Each check's name goes
    into the heartbeat details. A check that failed for an infrastructure reason (model, connection,
    database) makes the activity fail with a retryable `TransientStepFailure` after every other check
    has been recorded: the retry runs only what is missing, and a step that never passes is not
    reported as done."""
    from temporalio.exceptions import ApplicationError

    from .. import proofing, transient
    from .liveness import report
    resume = resume or activity.info().attempt > 1
    out = await proofing.run_all(generation_id, resume=resume, progress=report)
    lost = sorted(k for k, v in out.items() if isinstance(v, dict) and v.get("transient"))
    if lost:
        raise ApplicationError(f"son okuma denetimleri altyapı hatasıyla tamamlanamadı: {', '.join(lost)}: "
                               + "; ".join(f"{k}: {out[k]['failed'][:160]}" for k in lost)[:1500],
                               {"checks": lost}, type=transient.TYPE)
    return out


@activity.defn
async def visual_identity(generation_id: str) -> dict:
    """Who each drawn figure is: embeddings, constrained clustering, one adjudication per
    cluster (figure_identity). The per-figure reference matching it replaces named 31% of a
    six-book corpus at one 32B call per crop; this names more for a call per cluster."""
    out = await _own_loop(figure_identity.resolve, generation_id)
    return {k: v for k, v in out.items() if k not in ("assignments", "by_figure")}


@activity.defn
async def continuity_checks(generation_id: str) -> dict:
    """Compare every resolved figure, grouped by identity rather than name/page."""
    rows = await _t(db.all_rows,
        "SELECT ch.id, ch.canonical_name, array_agg(DISTINCT cm.page_no ORDER BY cm.page_no) AS pages"
        " FROM character ch JOIN character_mention cm ON cm.character_id=ch.id AND cm.via='VISUAL'"
        " AND cm.resolution='RESOLVED' WHERE ch.generation_id=%s AND cm.generation_id=ch.generation_id"
        " GROUP BY ch.id, ch.canonical_name HAVING count(cm.id)>=2", generation_id)

    async def one(r):
        res = await vision.compare_character_appearances(
            generation_id, r["canonical_name"], r["pages"], character_id=str(r["id"]))
        return {"character": r["canonical_name"], "character_id": str(r["id"]), "pages": r["pages"],
                "proposed": res["proposed"], "differences": len(res["differences"]),
                "not_confirmed": res["not_confirmed"], "same_everywhere": None,
                "same_character_in_checked_batches": res["same_character_in_checked_batches"],
                "coverage": res["coverage"]}

    return {"checked": await asyncio.gather(*(one(r) for r in rows)), "complete_book": False}


@activity.defn
async def verify_modality(generation_id: str) -> dict:
    return await knowledge.verify_event_modality(generation_id)


@activity.defn
async def merge_events(generation_id: str) -> dict:
    return await knowledge.merge_events(generation_id)


@activity.defn
async def emotions_themes(generation_id: str) -> dict:
    # not a book (book_type.NOT_A_BOOK): no emotions or themes are read from a catalogue's blurbs
    if not book_type.is_book(await book_type.profile(generation_id)):
        return {"skipped": book_type.NOT_A_BOOK}
    return await knowledge.link_emotions_and_themes(generation_id)


@activity.defn
async def embed_index(generation_id: str) -> dict:
    return await retrieval.embed_passages(generation_id)


@activity.defn
async def list_chapters(generation_id: str) -> list[dict]:
    return await _t(knowledge.chapters, generation_id)


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
async def event_actors(generation_id: str) -> dict:
    return await knowledge.attribute_event_actors(generation_id)


@activity.defn
async def contradictions(generation_id: str) -> dict:
    found = await knowledge.detect_contradictions(generation_id)
    queued = await _t(quality.contradictions_to_queue, generation_id)
    return {**found, **queued}


@activity.defn
async def detect_contradictions(generation_id: str) -> dict:
    """The director's half of `contradictions`, so it can run while the director is loaded."""
    return await knowledge.detect_contradictions(generation_id)


@activity.defn
async def queue_contradictions(generation_id: str) -> dict:
    """The queueing half: runs last, when text-visual and continuity candidates exist too."""
    return await _t(quality.contradictions_to_queue, generation_id)


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
async def book_metadata(generation_id: str) -> dict:
    """Bibliographic claims (ISBN, author, age range...) while the generation is still open.

    The whole-book page rule (editor.page_scope.ensure) is applied first: during the reading it
    only saw each chunk, and an imprint page it had not marked yet left METADATA empty. The
    validation runs it again (idempotent) and reads the imprint once more only if new imprint
    pages appear there."""
    from .. import page_scope
    await _t(page_scope.ensure, generation_id)
    meta = await _own_loop(catalog.extract_metadata, generation_id)
    return {"fields": sorted(meta)}


@activity.defn
async def build_card(generation_id: str) -> dict:
    return await catalog.build_card(generation_id)


@activity.defn
async def finish_job(job_id: str, status: str, result: dict) -> None:
    await _t(db.one, "UPDATE analysis_job SET status=%s, finished_at=now(), progress=progress || %s,"
             " error=%s WHERE id=%s RETURNING id", status, db.J({"result": result}),
             result.get("error"), job_id)
    if status == "SUCCEEDED" and result.get("generation_id"):
        # The book's title from the publisher site / the colophon now that the reading is done
        # (editor.book_title; never over a name a person gave). Inside this activity so no workflow
        # history changes; a failure leaves the title as it was and never fails the job.
        from .. import book_title
        try:
            await _t(book_title.after_reading, result["generation_id"])
        except Exception as e:  # noqa: BLE001
            activity.logger.warning("book title not resolved for %s: %s", result["generation_id"], e)


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
    busy = await _t(db.one, "SELECT (SELECT count(*) FROM analysis_job WHERE status='RUNNING') + "
        "(SELECT count(*) FROM rebuild_request r JOIN pg_stat_activity a ON a.pid=r.consumer_backend_pid "
        "AND a.backend_start=r.consumer_backend_start) AS n")
    if (busy or {}).get("n", 0) > 0:
        return {"stopped": [], "reason": "another job is running"}
    r = await client().post("/internal/stop-all", headers=h)
    return r.json()


@activity.defn
async def rebuild_outputs(generation_id: str) -> dict:
    from .. import rebuild
    await _t(rebuild.activate, generation_id)
    return await rebuild.run(generation_id)


ALL = [archive_visual_pages, archive_outputs, archive_recommend, proofreading, rebuild_outputs, event_actors, detect_contradictions, queue_contradictions, book_metadata, visual_identity, confirm_text_visual, build_card, scan_page_deep_key, narrative_roles, set_step, prepare_generation, page_manifest, text_layer, ocr_page, scan_page_fast, scan_page_deep,
       persist_visual, text_chunks, extract_chunk, resolve_identity, identity_unresolved, continuity_checks, verify_modality,
       merge_events, emotions_themes, embed_index, list_chapters, chapter_summary, book_summary, critic,
       contradictions, regression, report, finish_job, release_models]
