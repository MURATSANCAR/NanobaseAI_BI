"""Corpus-wide measurement: every sealed book at once, never a single one.

  python -m editor.measure_corpus [--json FILE]

A rule that is tuned on one book is a rule tuned on that book's cast, page count and
drawing style. This prints the same numbers for every sealed generation plus the totals,
so a change can be judged on the corpus: how much of the work reached a name, how much
the editor is asked to look at, and what it cost in calls and model minutes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import db

SQL = """
select b.title, bv.page_count, g.id gid, g.code_version,
  (select count(*) from character ch where ch.generation_id=g.id) chars,
  (select count(*) from character ch where ch.generation_id=g.id and ch.kind in ('OTHER','UNKNOWN')) chars_no_kind,
  (select count(*) from event e where e.generation_id=g.id and e.merged_into is null) events,
  (select count(*) from claim c where c.generation_id=g.id and c.status='VERIFIED') verified,
  (select count(*) from character_mention m where m.generation_id=g.id and m.via='VISUAL') figures,
  (select count(*) from character_mention m where m.generation_id=g.id and m.via='VISUAL'
     and m.resolution='RESOLVED') named,
  (select count(*) from contradiction x where x.generation_id=g.id) findings,
  (select count(*) from review_item r where r.generation_id=g.id and r.status='OPEN') queue,
  (select count(*) from model_call m where m.generation_id=g.id) calls,
  (select coalesce(round(sum(m.latency_ms)/60000.0), 0) from model_call m where m.generation_id=g.id) model_min
from generation g join book_version bv on bv.id=g.book_version_id join book b on b.id=bv.book_id
where g.sealed_at is not null
  and g.id = (select g2.id from generation g2 where g2.book_version_id=bv.id and g2.sealed_at is not null
              order by g2.created_at desc limit 1)
order by bv.page_count
"""


def queue_kinds(gid: str) -> dict[str, int]:
    rows = db.all_rows("select split_part(reason, ':', 1) k, count(*) n from review_item"
                       " where generation_id=%s and status='OPEN' group by 1 order by 2 desc", gid)
    return {r["k"][:30]: r["n"] for r in rows}


def main(out: Path | None) -> None:
    books = db.all_rows(SQL)
    tot = {k: 0 for k in ("page_count", "chars", "events", "verified", "figures", "named",
                          "findings", "queue", "calls", "model_min")}
    print(f"{'kitap':32s} {'sayfa':>5s} {'kar':>4s} {'olay':>5s} {'iddia':>6s} "
          f"{'figür':>6s} {'adlı':>5s} {'%':>4s} {'bulgu':>6s} {'kuyruk':>7s} {'çağrı':>6s} {'dk':>5s}")
    for x in books:
        for k in tot:
            tot[k] += int(x[k] or 0)
        pct = round(100 * (x["named"] or 0) / max(1, x["figures"] or 0))
        mins = int(x["model_min"] or 0)
        print(f"{x['title'][:32]:32s} {x['page_count']:5d} {x['chars']:4d} {x['events']:5d} "
              f"{x['verified']:6d} {x['figures']:6d} {x['named']:5d} {pct:4d} {x['findings']:6d} "
              f"{x['queue']:7d} {x['calls']:6d} {mins:5d}")
    pct = round(100 * tot["named"] / max(1, tot["figures"]))
    print(f"{'TOPLAM (' + str(len(books)) + ' kitap)':32s} {tot['page_count']:5d} {tot['chars']:4d} "
          f"{tot['events']:5d} {tot['verified']:6d} {tot['figures']:6d} {tot['named']:5d} {pct:4d} "
          f"{tot['findings']:6d} {tot['queue']:7d} {tot['calls']:6d} {tot['model_min']:5d}")
    print("\nkuyruk kalemleri (kitap başına):")
    kinds: dict[str, int] = {}
    for x in books:
        ks = queue_kinds(str(x["gid"]))
        for k, n in ks.items():
            kinds[k] = kinds.get(k, 0) + n
        print(f"  {x['title'][:30]:31s} {ks}")
    print("\ntoplam:", dict(sorted(kinds.items(), key=lambda kv: -kv[1])))
    if out:
        out.write_text(json.dumps({"books": [dict(x) for x in books], "total": tot,
                                   "queue_kinds": kinds}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    a = ap.parse_args()
    main(Path(a.json) if a.json else None)
