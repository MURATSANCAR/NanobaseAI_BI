"""Count the rows behind each code the source named, for columns the scan never sampled.

A coded column carrying the source's dictionary but no observed values is worse than useless: the
prompt shows nothing, the value search has nothing to walk, and the label sits in the catalog doing
no work. `new_siparisBase.statuscode` was exactly this — fifteen Turkish names, zero measurements.

This asks the database for the counts, and only for the columns in that state. Nothing is invented:
a code the source names but no row carries is stored as absent, not as zero.

    python -m scripts.probe_labelled_codes --schema Timas_MSCRM.dbo            # dry run
    python -m scripts.probe_labelled_codes --schema Timas_MSCRM.dbo --apply
"""
from __future__ import annotations

import argparse
import json
import time

from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store

MAX_DISTINCT = 64


def targets(profiles, schema):
    for p in profiles:
        if schema and p.schema_name != schema:
            continue
        for col in p.columns:
            if col.value_labels and not col.top_values and not col.sensitive:
                yield p, col


def probe(conn, store, settings, schema, apply=False, budget=1800.0):
    profiles = [p for p in store.list_profiles(settings.datasource_id)]
    started = time.perf_counter()
    report = {"applied": apply, "columns": 0, "measured": 0, "empty": 0, "failed": 0, "changed": []}
    touched = {}
    for prof, col in targets(profiles, schema):
        if time.perf_counter() - started > budget:
            report["stoppedOnBudget"] = True
            break
        report["columns"] += 1
        db, _, tbl_schema = prof.schema_name.partition(".")
        cur = conn.cursor()
        try:
            cur.execute(
                f"SELECT TOP {MAX_DISTINCT + 1} [{col.name}] AS v, COUNT_BIG(*) AS n "
                f"FROM [{db}].[{tbl_schema}].[{prof.table_name}] "
                f"WHERE [{col.name}] IS NOT NULL GROUP BY [{col.name}] ORDER BY COUNT_BIG(*) DESC")
            rows = [(str(r[0]), int(r[1])) for r in cur.fetchall()]
        except Exception as e:  # noqa: BLE001
            report["failed"] += 1
            report["changed"].append({"table": prof.table_name, "column": col.name, "error": str(e)[:120]})
            continue
        finally:
            cur.close()
        if not rows:
            report["empty"] += 1
            report["changed"].append({"table": prof.table_name, "column": col.name, "empty": True})
            continue
        # More distinct values than a code column has means this is not one; the labels describe a
        # subset and pretending the list is complete would let a filter be written against a closed
        # set that is not closed.
        if len(rows) > MAX_DISTINCT:
            report["changed"].append({"table": prof.table_name, "column": col.name,
                                      "skipped": f"{len(rows)}+ distinct, not a code column"})
            continue
        col.top_values = rows
        col.distinct_count = len(rows)
        named = [(v, col.value_labels.get(v)) for v, _ in rows]
        report["measured"] += 1
        report["changed"].append({
            "table": prof.table_name, "column": col.name, "distinct": len(rows),
            "rows": sum(n for _, n in rows),
            "named": sum(1 for _, lbl in named if lbl),
            "sample": [f"{v}={lbl}" for v, lbl in named[:6] if lbl]})
        touched[id(prof)] = prof
    if apply:
        for prof in touched.values():
            store.upsert_profile(prof)
        report["savedTables"] = len(touched)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", default="Timas_MSCRM.dbo")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--budget", type=float, default=1800.0)
    parser.add_argument("--out")
    args = parser.parse_args()
    from pathlib import Path

    from scripts.export_crm_metadata import SECRETS, connect

    settings = SemanticSettings.from_env()
    store = open_store(settings.store_dsn, create=False)
    report = probe(connect(SECRETS, args.schema.partition(".")[0]),
                   store, settings, args.schema, args.apply, args.budget)
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "changed"}, ensure_ascii=False))
