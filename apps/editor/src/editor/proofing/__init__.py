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

import importlib
import pkgutil
import time
import traceback

from .. import book_type, db

SEVERITIES = ("INFO", "WARN", "ERROR")

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


async def run_all(generation_id: str, only: list[str] | None = None) -> dict:
    """Run every check, each isolated: one failing check never costs the book the others.
    A check whose premise does not hold for this kind of book reports advice (as_advice)."""
    out = {}
    profile = await book_type.profile(generation_id)
    for name, mod in checks().items():
        if only and name not in only:
            continue
        t0 = time.time()
        reason = advisory_reason(name, profile)
        try:
            result = await mod.run(generation_id)
            findings, stats = (result if isinstance(result, tuple) else (result, {}))
            if reason:
                findings, stats = as_advice(findings, reason), {**stats, "advisory": reason}
            out[name] = record(generation_id, mod, findings, stats, t0)
        except Exception as e:  # noqa: BLE001 - recorded, the other checks go on
            with db.tx() as c:
                c.execute("INSERT INTO proof_run(generation_id, check_name, check_version, status, error,"
                          " started_at, finished_at) VALUES (%s,%s,%s,'FAILED',%s,to_timestamp(%s),now())",
                          (generation_id, name, str(getattr(mod, "VERSION", "?")),
                           (str(e) + "\n" + traceback.format_exc())[-4000:], t0))
            out[name] = {"failed": str(e)[:300]}
    return out


def latest(generation_id: str) -> dict:
    """The newest run of every check and its findings (what a screen or Hermes reads)."""
    runs = db.all_rows("SELECT DISTINCT ON (check_name) * FROM proof_run WHERE generation_id=%s"
                       " ORDER BY check_name, started_at DESC", generation_id)
    return {r["check_name"]: {"run": r, "findings": db.all_rows(
        "SELECT page_no, severity, quote, bbox, message, suggestion, details FROM proof_finding"
        " WHERE run_id=%s ORDER BY page_no NULLS FIRST, severity DESC", r["id"])} for r in runs}
