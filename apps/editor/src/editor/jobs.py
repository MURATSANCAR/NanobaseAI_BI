"""Job control: Hermes creates a job_id; the Temporal workflow does the work
("Uzun süren bu işlem Hermes'in tek sohbet turunda tutulmamalı")."""

from __future__ import annotations

from temporalio.client import Client

from . import db, document, foundation
from .config import settings

WORKFLOW = "BookFullAnalysis"
_client: Client | None = None


async def temporal() -> Client:
    global _client
    if _client is None:
        s = settings()
        _client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    return _client


async def start_analysis_job(file_name: str, title: str | None = None, universe: str | None = None,
                             age_group: str | None = None, profile: str = "full",
                             requested_by: str = "hermes") -> dict:
    foundation.assert_enabled()
    info = document.inspect_book(file_name, title=title, universe=universe, age_group=age_group)
    running = db.one("SELECT id FROM analysis_job WHERE book_version_id=%s AND status IN "
                     "('QUEUED','RUNNING') ORDER BY created_at DESC LIMIT 1", info["book_version_id"])
    if running:
        return {**info, "job_id": str(running["id"]), "already_running": True}
    job = db.one("INSERT INTO analysis_job(book_version_id, profile, requested_by) VALUES (%s,%s,%s)"
                 " RETURNING id", info["book_version_id"], profile, requested_by)
    job_id = str(job["id"])
    wf_id = f"book-analysis-{job_id}"
    await (await temporal()).start_workflow(WORKFLOW, job_id, id=wf_id,
                                            task_queue=settings().task_queue)
    db.one("UPDATE analysis_job SET workflow_id=%s WHERE id=%s RETURNING id", wf_id, job_id)
    return {**info, "job_id": job_id, "workflow_id": wf_id, "already_running": False}


def get_job_status(job_id: str) -> dict:
    j = db.one("SELECT j.*, b.title FROM analysis_job j JOIN book_version bv ON bv.id=j.book_version_id"
               " JOIN book b ON b.id=bv.book_id WHERE j.id=%s", job_id)
    if j is None:
        raise KeyError(f"job {job_id} not found")
    gen = db.one("SELECT id, sealed_at FROM generation WHERE job_id=%s ORDER BY created_at DESC LIMIT 1",
                 job_id)
    out = {"job_id": job_id, "title": j["title"], "status": j["status"], "step": j["step"],
           "progress": j["progress"], "error": j["error"], "created_at": str(j["created_at"]),
           "finished_at": str(j["finished_at"]) if j["finished_at"] else None,
           "generation_id": str(gen["id"]) if gen else None}
    if gen:
        out["open_review_items"] = (db.one("SELECT count(*) n FROM review_item WHERE generation_id=%s"
                                           " AND status='OPEN'", gen["id"]) or {}).get("n")
        rep = get_report(str(gen['id']))
        out['report_id'] = rep.get('id') if rep['available'] else None
        out['report_available'] = rep['available']
        out['knowledge_revision'] = rep['knowledge_revision']
        out['semantic_acceptance'] = False
    return out


async def cancel_job(job_id: str) -> dict:
    j = db.one("SELECT workflow_id, status FROM analysis_job WHERE id=%s", job_id)
    if j is None or not j["workflow_id"]:
        raise KeyError(f"job {job_id} not found")
    await (await temporal()).get_workflow_handle(j["workflow_id"]).cancel()
    return {"job_id": job_id, "cancel_requested": True}


def list_books() -> list[dict]:
    return db.all_rows(
        "SELECT b.id AS book_id, b.title, b.universe, b.age_group, bv.id AS book_version_id,"
        " bv.page_count, bv.sha256, (SELECT g.id FROM generation g WHERE g.book_version_id=bv.id"
        " ORDER BY g.created_at DESC,g.id DESC LIMIT 1) AS latest_generation_id"
        " FROM book b JOIN book_version bv ON bv.book_id=b.id ORDER BY bv.created_at DESC")


def latest_generation(book_version_id: str) -> dict | None:
    return db.one("SELECT id AS generation_id, created_at, sealed_at FROM generation WHERE"
                  " book_version_id=%s ORDER BY created_at DESC, id DESC LIMIT 1",
                  book_version_id)


def list_review_queue(generation_id: str, status: str = "OPEN", limit: int = 50) -> list[dict]:
    return db.all_rows(
        "SELECT r.id, r.priority, r.reason, r.status, r.created_at, c.kind AS claim_kind, c.claim,"
        " c.source_pages, c.confidence, x.kind AS contradiction_kind, x.description, x.pages"
        " FROM review_item r LEFT JOIN claim c ON c.id=r.claim_id LEFT JOIN contradiction x ON"
        " x.id=r.contradiction_id WHERE r.generation_id=%s AND r.status=%s ORDER BY r.priority,"
        " r.created_at LIMIT %s", generation_id, status, limit)


def get_report(generation_id: str, kind: str = "ANALYSIS") -> dict | None:
    from . import read_model
    return read_model.report(generation_id, kind)
