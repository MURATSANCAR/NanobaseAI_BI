"""Figure crops are a cache, not a record.

Every analysis writes one PNG per figure into `<book>/pages/gallery/<generation_id>/`,
so a book re-read five times keeps five copies of nearly the same drawings. Nothing is
lost by deleting an old generation's crops: a crop is `bbox` cut out of the page render
that stays on disk (`p0001.png`), the bbox itself lives in `visual_region` /
`character_mention`, and the identity vectors are already in `figure_embedding`. Any
crop that is needed again is re-cut in milliseconds by `vision._crop`.

What may NOT be deleted is a generation someone still reads or is still writing:

* the newest generation of each book version — the one a reader is served, because a
  newer generation always takes precedence over an older sealed one (CURRENT-READS.md),
* any generation whose job is QUEUED or RUNNING,
* any generation that is PUBLISHED.

Note what is NOT a reason to keep: having rows in `current_artifact`. Those exist per
generation, so every generation that ever finished its outputs has them, which would
keep every reading of every book forever — and they are exactly the built outputs whose
crops are no longer read once a newer generation supersedes them.

Everything else goes, including directories whose generation no longer exists at all.
Page renders are never touched: they are per book version, not per generation, and both
OCR and the crops are produced from them.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from . import db


def _dir_bytes(d: Path) -> int:
    return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())


def _keep() -> set[str]:
    rows = db.all_rows(
        "SELECT id::text FROM (SELECT DISTINCT ON (book_version_id) id FROM generation"
        "   ORDER BY book_version_id, created_at DESC, id DESC) newest"
        " UNION SELECT g.id::text FROM generation g JOIN analysis_job j ON j.id=g.job_id"
        "   WHERE j.status IN ('QUEUED','RUNNING')"
        " UNION SELECT generation_id::text FROM generation_state"
        "   WHERE publication_status='PUBLISHED'")
    return {r["id"] for r in rows}


def plan() -> dict:
    """What a prune would delete, without deleting anything."""
    keep = _keep()
    books = db.all_rows("SELECT bv.id::text AS book_version_id, b.title, bv.file_path"
                        " FROM book_version bv JOIN book b ON b.id=bv.book_id ORDER BY b.title")
    kept, drop = [], []
    for bv in books:
        gdir = Path(bv["file_path"]).parent / "pages" / "gallery"
        if not gdir.is_dir():
            continue
        for d in sorted(gdir.iterdir()):
            if not d.is_dir():
                continue
            row = {"title": bv["title"], "generation_id": d.name, "path": str(d),
                   "files": sum(1 for f in d.iterdir() if f.is_file()), "bytes": _dir_bytes(d)}
            (kept if d.name in keep else drop).append(row)
    return {"kept": kept, "deletable": drop, "kept_bytes": sum(r["bytes"] for r in kept),
            "deletable_bytes": sum(r["bytes"] for r in drop)}


def prune(apply: bool = False) -> dict:
    """Delete the crops of superseded generations. `apply=False` only reports."""
    p = plan()
    deleted = []
    if apply:
        for row in p["deletable"]:
            shutil.rmtree(row["path"], ignore_errors=False)
            deleted.append(row["path"])
    return {"applied": apply, "deleted": deleted,
            "freed_bytes": p["deletable_bytes"] if apply else 0,
            "would_free_bytes": 0 if apply else p["deletable_bytes"],
            "kept_generations": len(p["kept"]), "kept_bytes": p["kept_bytes"],
            "deletable": p["deletable"]}
