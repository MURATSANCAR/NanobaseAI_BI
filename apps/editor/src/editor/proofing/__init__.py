"""Final-read ("son okuma") checks.

A check is one module in this package with

    NAME = "hyphenation"            # stable id, also the queue label key
    VERSION = "1"                   # bump when the rule changes: a new run, comparable results
    LABEL = "Satır sonu heceleme"   # Turkish, shown to the editor
    async def run(generation_id: str) -> list[dict]

Each finding is a dict: page (int|None), severity (INFO|WARN|ERROR), message (Turkish),
optional quote (text exactly as printed), suggestion, bbox [x0,y0,x1,y1] in 0..1000,
details (dict). A check reads the book (source.read, page renders, the ledger) and returns
findings; it never writes knowledge, never edits the book's text, never raises for a
problem of the BOOK (that is a finding). It may raise for a problem of its OWN (a model is
down): the run is then recorded FAILED and the other checks still run.

Rules that apply to every check (project rules):
- nothing book-specific: no titles, names, page numbers or thresholds tuned on one book;
- measured before trusted: each check's precision is measured on real books and written in
  its module docstring and docs/son-okuma/<name>.md;
- a finding is a candidate for the editor; the application does not "fix" the book.
"""

from __future__ import annotations

import asyncio
import importlib
import pkgutil
import time
import traceback

from .. import book_type, db

SEVERITIES = ("INFO", "WARN", "ERROR")
#: Who closes a superseded queue item (the change log shows the application as «ZEKİ AI»).
ACTOR = "ZEKİ AI"

# Every check runs on every book (user decision 2026-09-24: what a children's book gets, every
# book gets). Where a check's premise does not hold for this kind of book (editor.book_type) —
# story continuity (how a character looks, what they carry, where and when a scene is, who
# speaks) in a book that tells no story, content judged for a child's age in an adult's book —
# its findings are kept as advice: severity INFO, the reason in details.advisory, no review
# item, nothing that blocks acceptance. (An adult novel read as a children's book had opened
# 81 "sensitive for children" questions, 2026-09-23.)
STORY_ONLY = frozenset({"appearance", "props", "setting", "timeline", "dialogue"})
AGE_JUDGED_ONLY = frozenset({"age_fit"})


def advisory_reason(name: str, profile: dict) -> str | None:
    if name in STORY_ONLY and not book_type.is_story(profile):
        return "öneri: kitap bir hikâye anlatmıyor (" + book_type.describe(profile) + ")"
    if name in AGE_JUDGED_ONLY and profile["audience"] not in book_type.AGE_JUDGED:
        return "öneri: kitap çocuk ya da genç okur için değil (" + book_type.describe(profile) + ")"
    return None


def as_advice(findings: list[dict], reason: str) -> list[dict]:
    """The same findings, as advice: INFO, with the reason; message and evidence unchanged."""
    return [{**f, "severity": "INFO", "details": {**(f.get("details") or {}), "advisory": reason,
             "severity_as_found": f.get("severity", "WARN")}} for f in findings]


def checks() -> dict[str, object]:
    """Every module of this package that defines NAME and run()."""
    out = {}
    for m in pkgutil.iter_modules(__path__):
        if m.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{m.name}")
        if hasattr(mod, "NAME") and hasattr(mod, "run"):
            out[mod.NAME] = mod
    return dict(sorted(out.items()))


def _clean(f: dict) -> dict:
    sev = f.get("severity", "WARN")
    if sev not in SEVERITIES:
        raise ValueError(f"severity must be one of {SEVERITIES}: {sev}")
    if not (f.get("message") or "").strip():
        raise ValueError("a finding needs a message")
    return {"page": f.get("page"), "severity": sev, "quote": f.get("quote"),
            "bbox": f.get("bbox"), "message": f["message"].strip(),
            "suggestion": f.get("suggestion"), "details": f.get("details") or {}}


def record(generation_id: str, mod, findings: list[dict], stats: dict, started: float) -> dict:
    """Write one run and its findings; one grouped queue item when there is anything to see."""
    rows = [_clean(f) for f in findings]
    with db.tx() as c:
        run = c.execute(
            "INSERT INTO proof_run(generation_id, check_name, check_version, status, stats, started_at,"
            " finished_at) VALUES (%s,%s,%s,'SUCCEEDED',%s,to_timestamp(%s),now()) RETURNING id",
            (generation_id, mod.NAME, str(mod.VERSION), db.J({**stats, "findings": len(rows)}), started)
        ).fetchone()["id"]
        for f in rows:
            c.execute(
                "INSERT INTO proof_finding(run_id, generation_id, check_name, page_no, severity, quote, bbox,"
                " message, suggestion, details) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (run, generation_id, mod.NAME, f["page"], f["severity"], f["quote"],
                 db.J(f["bbox"]) if f["bbox"] is not None else None, f["message"], f["suggestion"],
                 db.J(f["details"])))
        # an older run of the same check on this generation is superseded: its still-open queue item
        # would be a duplicate of this one (an activity retry used to run every check again, up to
        # four open items per check, 2026-10-01..03); an item the editor already decided stays
        c.execute("UPDATE review_item SET status='REJECTED', decided_by=%s, decided_at=now(),"
                  " decision=%s WHERE generation_id=%s AND status='OPEN' AND proof_run_id IN"
                  " (SELECT id FROM proof_run WHERE generation_id=%s AND check_name=%s AND id<>%s)",
                  (ACTOR, db.J({"superseded_by_run": str(run), "reason": "aynı denetimin yeni koşusu"}),
                   generation_id, generation_id, mod.NAME, run))
        serious = [f for f in rows if f["severity"] != "INFO"]
        if serious:
            pages = sorted({f["page"] for f in serious if f["page"] is not None})
            shown = ", ".join(f"s.{p}" for p in pages[:12]) + (" …" if len(pages) > 12 else "")
            c.execute(
                "INSERT INTO review_item(generation_id, proof_run_id, reason, priority) VALUES (%s,%s,%s,%s)",
                (generation_id, run,
                 f"Son okuma — {getattr(mod, 'LABEL', mod.NAME)}: {len(serious)} bulgu"
                 + (f" ({shown})" if shown else ""),
                 1 if any(f["severity"] == "ERROR" for f in serious) else 3))
    return {"run_id": str(run), "findings": len(rows), "serious": len(serious)}


def recorded(generation_id: str) -> dict[str, str]:
    """{check name: run id} of the checks that already have a SUCCEEDED run at their current version on
    this generation (what a resumed run skips)."""
    have = {(r["check_name"], r["check_version"]): str(r["id"]) for r in db.all_rows(
        "SELECT DISTINCT ON (check_name, check_version) id, check_name, check_version FROM proof_run"
        " WHERE generation_id=%s AND status='SUCCEEDED' ORDER BY check_name, check_version, started_at DESC",
        generation_id)}
    return {name: have[(name, str(mod.VERSION))] for name, mod in checks().items()
            if (name, str(mod.VERSION)) in have}


def _failed(generation_id: str, name: str, mod, e: BaseException, t0: float) -> None:
    with db.tx() as c:
        c.execute("INSERT INTO proof_run(generation_id, check_name, check_version, status, error,"
                  " started_at, finished_at) VALUES (%s,%s,%s,'FAILED',%s,to_timestamp(%s),now())",
                  (generation_id, name, str(getattr(mod, "VERSION", "?")),
                   (str(e) + "\n" + "".join(traceback.format_exception(e)))[-4000:], t0))


async def _one(generation_id: str, name: str, mod, reason: str | None) -> dict:
    """One check, start to record. Runs on its own event loop (editor.offloop): a check reads the whole
    book, renders pages and measures them, and much of that is synchronous; on the worker's shared loop
    it stopped every activity's heartbeat (layout 151 s, series_canon, setting — 2026-10-01..03)."""
    from .. import transient
    t0 = time.time()
    try:
        result = await mod.run(generation_id)
        findings, stats = (result if isinstance(result, tuple) else (result, {}))
        if reason:
            findings, stats = as_advice(findings, reason), {**stats, "advisory": reason}
        return record(generation_id, mod, findings, stats, t0)
    except Exception as e:  # noqa: BLE001 - recorded, the other checks go on
        _failed(generation_id, name, mod, e, t0)
        out = {"failed": str(e)[:300]}
        if transient.is_transient(e):
            out["transient"] = True
        return out


async def run_all(generation_id: str, only: list[str] | None = None, *, resume: bool = False,
                  progress=None) -> dict:
    """Run every check, each isolated: one failing check never costs the book the others.
    A check whose premise does not hold for this kind of book reports advice (as_advice).

    Each check runs on its own event loop and thread (editor.offloop), so nothing a check does can
    stop the worker's heartbeats. `resume`: a check that already has a SUCCEEDED run at its current
    version on this generation is not run again (an activity retry continues where the lost attempt
    stopped instead of starting over and queueing every finding a second time). `progress(**kw)` is
    told which check runs (the activity's heartbeat details).

    A check that failed for an infrastructure reason (editor.transient: connection, database, model
    down) is marked `transient`; the caller decides whether that may pass silently (the workflow's
    activity does not let it)."""
    from .. import offloop
    out: dict = {}
    profile = await offloop.run(book_type.profile, generation_id)
    done = await asyncio.to_thread(recorded, generation_id) if resume else {}
    todo = [(n, m) for n, m in checks().items() if not only or n in only]
    for i, (name, mod) in enumerate(todo):
        if name in done:
            out[name] = {"resumed": done[name]}
            continue
        if progress is not None:
            progress(check=name, index=i + 1, of=len(todo),
                     done=sorted(k for k, v in out.items() if "failed" not in v))
        out[name] = await offloop.run(_one, generation_id, name, mod, advisory_reason(name, profile))
    if progress is not None:
        progress(check=None, index=len(todo), of=len(todo),
                 done=sorted(k for k, v in out.items() if "failed" not in v))
    return out


def latest(generation_id: str) -> dict:
    """The newest run of every check and its findings (what a screen or Hermes reads)."""
    runs = db.all_rows("SELECT DISTINCT ON (check_name) * FROM proof_run WHERE generation_id=%s"
                       " ORDER BY check_name, started_at DESC", generation_id)
    return {r["check_name"]: {"run": r, "findings": db.all_rows(
        "SELECT page_no, severity, quote, bbox, message, suggestion, details FROM proof_finding"
        " WHERE run_id=%s ORDER BY page_no NULLS FIRST, severity DESC", r["id"])} for r in runs}
