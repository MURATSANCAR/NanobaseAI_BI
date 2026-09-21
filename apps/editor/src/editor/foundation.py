"""Versioned analysis foundation; no model calls or automatic book re-runs.

These primitives are for the next workflow revision. Existing generations are
legacy previews, never retroactively certified. All new control API reads are
repeatable-read/read-only; publication remains blocked until independent gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import contextmanager
from typing import Callable

from . import db


@contextmanager
def read_snapshot():
    with db.tx() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        c.execute("SET LOCAL statement_timeout='15s'")
        yield c


def assert_enabled(c=None) -> None:
    if c is None:
        with read_snapshot() as conn:
            return assert_enabled(conn)
    row = c.execute("SELECT maintenance,reason FROM ed.runtime_control WHERE singleton").fetchone()
    if row is None or row["maintenance"]:
        raise RuntimeError("EDITOR_MAINTENANCE: " + (row["reason"] if row else "control missing"))


def runtime_status() -> dict:
    with read_snapshot() as c:
        control = c.execute("SELECT * FROM ed.runtime_control WHERE singleton").fetchone()
        return {
            "control": control,
            "jobs": c.execute("SELECT status,count(*) AS count FROM ed.analysis_job GROUP BY status").fetchall(),
            "generations": c.execute("SELECT origin,count(*) AS count FROM ed.generation_state GROUP BY origin").fetchall(),
            "pending_rebuilds": c.execute("SELECT count(*) AS n FROM ed.rebuild_request "
                "WHERE completed_revision<requested_revision").fetchone()["n"],
            "dependencies": c.execute("SELECT * FROM ed.artifact_definition ORDER BY kind").fetchall(),
            "analysis_worker_required": False,
            "automatic_rebuild_consumer": "PAUSED" if control["maintenance"] else "AVAILABLE_OPT_IN",
        }


def generations(limit: int = 100) -> list[dict]:
    with read_snapshot() as c:
        return c.execute("SELECT g.id,g.code_version,g.sealed_at,b.title,s.* FROM ed.generation g "
            "JOIN ed.generation_state s ON s.generation_id=g.id "
            "JOIN ed.book_version bv ON bv.id=g.book_version_id JOIN ed.book b ON b.id=bv.book_id "
            "ORDER BY g.created_at DESC LIMIT %s", (limit,)).fetchall()


def readiness(generation_id: str) -> dict:
    with read_snapshot() as c:
        state = c.execute("SELECT s.*,g.sealed_at,g.code_version FROM ed.generation_state s "
            "JOIN ed.generation g ON g.id=s.generation_id WHERE generation_id=%s", (generation_id,)).fetchone()
        if state is None:
            raise KeyError(generation_id)
        counts = c.execute("SELECT "
            "(SELECT count(*) FROM ed.claim WHERE generation_id=%s) AS total_claims, "
            "(SELECT count(*) FROM ed.usable_claim WHERE generation_id=%s) AS usable_claims, "
            "(SELECT count(*) FROM ed.usable_event WHERE generation_id=%s) AS usable_events, "
            "(SELECT count(*) FROM ed.usable_emotion WHERE generation_id=%s) AS usable_emotions, "
            "(SELECT count(*) FROM ed.review_item WHERE generation_id=%s AND status='OPEN') AS open_reviews",
            (generation_id,)*5).fetchone()
        artifacts = c.execute("SELECT * FROM ed.derived_artifact WHERE generation_id=%s ORDER BY kind",
            (generation_id,)).fetchall()
        latest_regression = c.execute("SELECT passed,created_at FROM ed.regression_run "
            "WHERE generation_id=%s ORDER BY created_at DESC LIMIT 1", (generation_id,)).fetchone()
        blockers = []
        if state["origin"] != "TRACKED":
            blockers.append("LEGACY_UNASSESSED")
        for field in ("coverage_status", "semantic_status"):
            if state[field] != "PASSED":
                blockers.append(field.upper() + ":" + state[field])
        expected = c.execute("SELECT count(*) AS n FROM ed.artifact_definition").fetchone()["n"]
        if len(artifacts) != expected or any(a["state"] != "READY" or
                a["input_revision"] != state["knowledge_revision"] for a in artifacts):
            blockers.append("ARTIFACTS_NOT_CURRENT")
        if latest_regression is None or not latest_regression["passed"]:
            blockers.append("REGRESSION_NOT_PASSED")
        if counts["open_reviews"]:
            blockers.append("OPEN_EDITOR_REVIEW")
        if state["publication_status"] not in ("READY", "PUBLISHED"):
            blockers.append("PUBLICATION_BLOCKED")
        # An editor's acceptance of THIS revision may knowingly waive coverage blockers;
        # they are reported as waived, never silently dropped.
        acc = c.execute("SELECT accepted_by,note,waived,created_at FROM ed.semantic_acceptance WHERE "
            "generation_id=%s AND revision=%s", (generation_id, state["knowledge_revision"])).fetchone()
        waived = [b for b in blockers if acc and b.split(":")[0] in WAIVABLE and
                  ACCEPT_WAIVES[b.split(":")[0]] & set(acc["waived"])]
        blockers = [b for b in blockers if b not in waived]
        return {"generation": state, "counts": counts, "artifacts": artifacts,
            "acceptance": acc, "waived": waived,
            "regression": latest_regression, "accepted": not blockers, "blockers": blockers,
            "mode": "source_supported_preview", "complete_book": not blockers}


# What an editor may knowingly waive, and which readiness blocker each waiver lifts. Open
# reviews, a failed regression, stale artifacts and legacy origin can never be waived.
ACCEPT_WAIVES = {"COVERAGE_STATUS": {"SOURCE_ISSUES", "PAGE_ROLES_UNASSESSED"}}
WAIVABLE = set(ACCEPT_WAIVES)


def accept(generation_id: str, editor: str, note: str = "", waive: list[str] | None = None) -> dict:
    """Record an editor's semantic acceptance of the current validated revision."""
    waive = sorted(set(waive or []))
    unknown = set(waive) - set().union(*ACCEPT_WAIVES.values())
    if unknown:
        raise ValueError(f"cannot be waived: {sorted(unknown)}")
    before = readiness(generation_id)
    state = before["generation"]
    if state["validated_revision"] != state["knowledge_revision"]:
        raise ValueError("current revision is not validated; outputs must be rebuilt first")
    hard = [b for b in before["blockers"] if b.split(":")[0] not in
            ("SEMANTIC_STATUS", "PUBLICATION_BLOCKED", "COVERAGE_STATUS")]
    if hard:
        raise ValueError(f"not acceptable yet: {hard}")
    snap = db.one("SELECT content->'blockers' AS b FROM ed.knowledge_snapshot WHERE generation_id=%s AND"
                  " revision=%s", generation_id, state["knowledge_revision"])
    open_cov = sorted(set((snap or {}).get("b") or []) & ACCEPT_WAIVES["COVERAGE_STATUS"])
    if state["coverage_status"] != "PASSED" and not set(open_cov) <= set(waive):
        raise ValueError(f"coverage is {state['coverage_status']}; waive explicitly or resolve: {open_cov}")
    with db.tx() as c:
        c.execute("INSERT INTO ed.semantic_acceptance(generation_id,revision,accepted_by,note,waived)"
                  " VALUES (%s,%s,%s,%s,%s)", (generation_id, state["knowledge_revision"], editor, note, waive))
        c.execute("UPDATE ed.generation_state SET semantic_status='PASSED',publication_status='READY'"
                  " WHERE generation_id=%s AND knowledge_revision=%s AND validated_revision=%s",
                  (generation_id, state["knowledge_revision"], state["knowledge_revision"]))
    return readiness(generation_id)


def read_records(generation_id: str, kind: str, limit: int, offset: int) -> dict:
    from . import read_model
    return read_model.records(generation_id, kind, limit, offset)


def digest_inputs(inputs: dict) -> str:
    """Caller includes source revision, code, prompt, model and settings hashes."""
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode()).hexdigest()


def persist_once(generation_id: str, stage: str, inputs: dict, persist: Callable) -> dict:
    """Atomic DB-only persistence + receipt. Never call a model inside persist.

    The input digest must describe the logical operation, not a retry attempt.
    The lock survives neither a crash nor rollback; a committed receipt does.
    """
    key = digest_inputs(inputs)
    with db.tx() as c:
        assert_enabled(c)
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"{generation_id}:{stage}:{key}",))
        old = c.execute("SELECT result FROM ed.operation_receipt WHERE generation_id=%s AND stage=%s "
            "AND input_digest=%s", (generation_id,stage,key)).fetchone()
        if old:
            return old["result"]
        result = persist(c)
        c.execute("INSERT INTO ed.operation_receipt(generation_id,stage,input_digest,result) VALUES (%s,%s,%s,%s)",
            (generation_id,stage,key,db.J(result)))
        return result


def invalidate_dependents(c, generation_id: str, changed_kind: str) -> list[str]:
    """Called in the same transaction that replaces a derived artifact."""
    c.execute("SELECT knowledge_revision FROM ed.generation_state WHERE generation_id=%s FOR UPDATE", (generation_id,))
    rows = c.execute("WITH RECURSIVE downstream(kind) AS ("
        "SELECT kind FROM ed.artifact_definition WHERE %s=ANY(depends_on) UNION "
        "SELECT d.kind FROM ed.artifact_definition d JOIN downstream u ON u.kind=ANY(d.depends_on)) "
        "UPDATE ed.derived_artifact SET state='STALE',updated_at=now() "
        "WHERE generation_id=%s AND kind IN (SELECT kind FROM downstream) RETURNING kind",
        (changed_kind,generation_id)).fetchall()
    if rows:
        c.execute("UPDATE ed.generation_state SET semantic_status='NOT_EVALUATED',publication_status='BLOCKED',"
            "updated_at=now() WHERE generation_id=%s", (generation_id,))
        c.execute("INSERT INTO ed.rebuild_request(generation_id,requested_revision,reason) "
            "SELECT generation_id,knowledge_revision,%s FROM ed.generation_state WHERE generation_id=%s "
            "ON CONFLICT(generation_id) DO UPDATE SET requested_revision=EXCLUDED.requested_revision,"
            "completed_revision=LEAST(ed.rebuild_request.completed_revision,EXCLUDED.requested_revision-1),"
            "reason=EXCLUDED.reason,updated_at=now()", (changed_kind,generation_id))
    return [r["kind"] for r in rows]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate", "status", "pause", "resume"])
    parser.add_argument("--reason", default="User requested analysis stop")
    args = parser.parse_args()
    if args.command == "migrate":
        result = {"applied": db.migrate()}
    elif args.command == "pause":
        result = db.one("UPDATE ed.runtime_control SET maintenance=true,reason=%s,updated_at=now() "
            "WHERE singleton RETURNING *", args.reason)
    elif args.command == "resume":
        # The switch had an "on" and no "off": leaving maintenance took hand-written SQL.
        result = db.one("UPDATE ed.runtime_control SET maintenance=false,reason=%s,updated_at=now() "
            "WHERE singleton RETURNING *", args.reason)
    else:
        result = runtime_status()
    print(json.dumps(result, default=str, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
