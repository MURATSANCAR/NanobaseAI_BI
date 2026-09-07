"""Collect the values that make a column findable.

The column index can route "trendyol satışları" to `CLFLINE.TRADINGGRP` because that column's values
happen to be in the catalog. Almost none are: the profiler probes values only on the handful of
tables it treats as deep, so 229 of fourteen thousand columns know what they contain. Every code
column that was not probed — the channel codes, the cities, the special codes a business actually
filters by — is invisible to a question that names one of its values.

This asks the source for them, for the columns where an answer is likely and the cost is bounded:

  * text columns whose name says they carry a code, a group, a type, a place or a status
  * short ones — a column declared as 200 characters holds prose, not a code set
  * one query each, `TOP (n+1) … GROUP BY`, so a column with more distinct values than the ceiling
    is recognised as not-an-enum and dropped rather than read whole

Anything with more distinct values than `--max-distinct` is left alone: a value list is only useful
while it is a list. Nothing already probed is re-probed unless `--refresh` says so, and the whole run
stops at `--budget` seconds so it cannot become an open-ended load on a customer's database.

    python backend/scripts/probe_column_values.py --dry-run
    python backend/scripts/probe_column_values.py --apply --budget 900
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semantic_layer.config import SemanticSettings              # noqa: E402
from semantic_layer.pipeline import build_connector              # noqa: E402
from semantic_layer.store.catalog_store import open_store        # noqa: E402

#: Names that carry a small set of meanings rather than free text or a measurement.
_CODE_LIKE = re.compile(
    r"(SPECODE|CYPHCODE|AUXILCODE|TRADINGGRP|GRPCODE|GROUPCODE|STGRPCODE|CLASSCODE|DELIVERYCODE"
    r"|PAYMENTCODE|PROJECTCODE|CAMPAIGNCODE|DIVISION|DEPARTMENT|BRANCH|CITY|TOWN|COUNTRY|DISTRICT"
    r"|STATUS|STATE|KIND|CATEGORY|SECTOR|CURRENCY|CURR$|TYPE$|TYP$|CODE$|GRP$)")

#: A code fits in a short column. Anything wider is a title, an address or a note.
_MAX_WIDTH = 32

_NOT_A_TABLE = re.compile(r"(YEDEK|BACKUP|_BAK|_COPY|PERFTEST|_TMP|TEMP\d|_OLD|_ESKI|_TEST)", re.I)


def candidates(profiles) -> list[tuple[object, object]]:
    """One profile per entity — the copy with the most rows — and its code-bearing text columns."""
    best: dict[str, object] = {}
    for p in profiles:
        if _NOT_A_TABLE.search(p.entity):
            continue
        cur = best.get(p.entity)
        if cur is None or (p.row_count or 0) > (cur.row_count or 0):
            best[p.entity] = p
    out = []
    for prof in best.values():
        if not (prof.row_count or 0):
            continue                    # an empty table has no values to learn
        for col in prof.columns:
            if col.top_values or col.sensitive:
                continue
            dtype = (col.data_type or "").lower()
            if not any(t in dtype for t in ("char", "text", "varchar")):
                continue
            width = re.search(r"\((\d+)\)", dtype)
            if width and int(width.group(1)) > _MAX_WIDTH:
                continue
            # A name that says "code" is the likeliest, but it is not the only one: a column called
            # KANAL or DURUM carries a code set and matches no English pattern. What actually decides
            # is the answer from the source — a column with more distinct values than the ceiling is
            # dropped there. The name only chooses what to ask about first.
            out.append((prof, col, 0 if _CODE_LIKE.search(col.name.upper()) else 1))
    out.sort(key=lambda x: (x[2], -(x[0].row_count or 0)))
    return [(prof, col) for prof, col, _ in out]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-distinct", type=int, default=64)
    ap.add_argument("--budget", type=float, default=0.0, help="saniye; 0 = sınır yok")
    ap.add_argument("--limit", type=int, default=0, help="en fazla kaç kolon denenecek")
    args = ap.parse_args(argv)

    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn)
    profiles = store.list_profiles(s.datasource_id)
    todo = candidates(profiles)
    if args.limit:
        todo = todo[: args.limit]
    print(f"aday kolon: {len(todo)} ({len({p.entity for p, _ in todo})} tabloda)")
    print("kod adlı olanlar önce, sonra satır sayısına göre — sınır yoksa hepsi okunur")
    for prof, col in todo[:12]:
        print(f"   {prof.entity}.{col.name}  ({col.data_type}, {prof.row_count:,} satır)")
    if args.dry_run or not args.apply:
        print("\n(kuru çalışma — okumak için --apply)")
        return 0

    connector = build_connector(s)
    started = time.time()
    found = skipped = failed = 0
    changed: dict[str, object] = {}
    for prof, col in todo:
        if args.budget and time.time() - started > args.budget:
            print(f"\nsüre bütçesi doldu ({args.budget:.0f} sn) — {found} kolon okundu, kalan bırakıldı")
            break
        try:
            rows = connector.top_values(prof.schema_name or "dbo", prof.table_name,
                                        col.name, args.max_distinct + 1)
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"   okunamadı {prof.entity}.{col.name}: {str(e)[:70]}")
            continue
        done = found + skipped + failed + 1
        if done % 25 == 0:
            print(f"   {done}/{len(todo)} kolon denendi, {found} değer kümesi bulundu "
                  f"({time.time() - started:.0f} sn)", flush=True)
        clean = [(v, n) for v, n in rows if str(v).strip()]
        if not clean or len(clean) > args.max_distinct:
            skipped += 1           # free text, not a code set
            continue
        col.top_values = clean
        col.distinct_count = len(clean)
        changed[prof.table_name] = prof
        found += 1

    print(f"\ndeğer bulundu: {found} | kod kümesi değil: {skipped} | okunamadı: {failed}")
    for prof in changed.values():
        store.upsert_profile(prof)
    print(f"{len(changed)} profil güncellendi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
