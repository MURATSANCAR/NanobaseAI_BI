"""Batch fixes never write into a generation that a reading is still working on.

2026-10-05: `identity_fold --apply` ran while a reading of the same generation was still resolving its characters;
it deleted character rows the reading was about to use (foreign-key error) and changed the generation under the
outputs being built (SUPERSEDED) — two readings failed. Every batch command that writes into read generations
(identity_fold --apply, page_scope rebuild, recommend fill --apply, book_type recheck --apply, backfill steps
--apply) asks here first, again right before it writes each generation, and lists what it skipped at the end.

A generation is busy while an analysis job that works on it is QUEUED or RUNNING: the job that created it
(`generation.job_id`) or a redaction job opened on it (`analysis_job.progress.generation_id`)."""

from __future__ import annotations

import json
import sys
from typing import Iterable

BUSY_SQL = (
    "SELECT g.id::text AS generation_id, j.id::text AS job_id, j.status, j.profile"
    " FROM ed.generation g JOIN ed.analysis_job j"
    "   ON j.id = g.job_id OR (j.progress->>'generation_id') = g.id::text"
    " WHERE g.id::text = ANY(%s::text[]) AND j.status IN ('QUEUED','RUNNING')")


def busy(generation_ids: Iterable[str]) -> dict[str, str]:
    """{generation id: why it is busy} for the generations a QUEUED/RUNNING job works on (read only)."""
    from . import db
    ids = sorted({str(g) for g in generation_ids if g})
    if not ids:
        return {}
    out: dict[str, str] = {}
    for r in db.all_rows(BUSY_SQL, ids):
        out.setdefault(r["generation_id"], f"okuma sürüyor: iş {r['job_id']} {r['status']} ({r['profile'] or 'full'})")
    return out


def reason(generation_id: str) -> str | None:
    return busy([generation_id]).get(str(generation_id))


class Skipped:
    """Collects the generations a command left alone and prints them at the end."""

    def __init__(self, command: str) -> None:
        self.command = command
        self.items: list[dict] = []

    def add(self, generation_id: str, why: str, title: str | None = None) -> None:
        self.items.append({"generation_id": str(generation_id), "title": title, "reason": why})

    def check(self, generation_id: str, title: str | None = None) -> bool:
        """True when the generation may be written now; otherwise it is recorded as skipped."""
        why = reason(generation_id)
        if why is None:
            return True
        self.add(generation_id, why, title)
        return False

    def report(self, stream=None) -> None:
        stream = stream or sys.stderr
        if not self.items:
            print(f"{self.command}: süren okuma yüzünden atlanan nesil yok", file=stream)
            return
        print(f"{self.command}: {len(self.items)} nesil atlandı (okuması sürüyor; okuma bitince yeniden koşturun):",
              file=stream)
        for x in self.items:
            print("  " + json.dumps(x, ensure_ascii=False), file=stream)
