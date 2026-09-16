"""Discover join relationships between databases — dry run only.

Reads the catalog's profiles, measures value overlap on the customer's database with sampled,
single-core queries, and writes two files: the full discovery report (every pair, the stage it
stopped at and why) and the apply plan (exactly which relationship would be written to which profile
row). Nothing is written to the catalog.

    python -m scripts.discover_cross_links --out /var/tmp/crmlinks \
        --connection logo.json --connection crm.json \
        [--oracle ACCOUNTBASE.new_logicalref=LG_CLCARD.LOGICALREF ...]

The first connection answers for profiles with an unqualified schema; every connection answers for
profiles whose schema is qualified with the database its file opens. No statement spans two of them.

`--oracle` pairs are only used to print precision / recall at the end; discovery never sees them.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semantic_layer.profiler.connectors import connector_from_file  # noqa: E402
from semantic_layer.profiler.cross_source_links import (  # noqa: E402
    CrossSourceLinkDiscovery, LinkThresholds, RoutedProbe, apply_plan, database_of,
)
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def score(accepted: list[tuple[str, str]], oracle: list[tuple[str, str]]) -> dict:
    norm = lambda pair: tuple(x.upper() for x in pair)  # noqa: E731
    got, want = {norm(a) for a in accepted}, {norm(o) for o in oracle}
    hit = got & want
    return {"accepted": len(got), "oracle": len(want), "found": sorted(hit), "missed": sorted(want - got),
            "recall": round(len(hit) / len(want), 4) if want else None,
            "precision_vs_oracle": round(len(hit) / len(got), 4) if got else None,
            "not_in_oracle": sorted(got - want)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--datasource", default=os.environ.get("SEMANTIC_DATASOURCE_ID", "logo"))
    ap.add_argument("--connection", action="append", default=[],
                    help="connection file; repeat for each database (default: SEMANTIC_CONNECTION_FILE, "
                         "then SEMANTIC_CRM_CONNECTION_FILE when it exists)")
    ap.add_argument("--timeout", type=int, default=900, help="per-query timeout for the confirmation scans")
    ap.add_argument("--samples-cache", default=None, help="reuse/save value profiles (JSON)")
    ap.add_argument("--stop-after", choices=["block"], default=None)
    ap.add_argument("--tenant", default=os.environ.get("SEMANTIC_TENANT_ID", "default"))
    ap.add_argument("--priority-certified", action="store_true",
                    help="measure pairs between tables with certified concepts first and write *_oncelikli.json "
                         "when they are done; every other pair follows (an order, not a filter)")
    ap.add_argument("--oracle", action="append", default=[], help="ENTITY.COLUMN=ENTITY.COLUMN")
    for f in fields(LinkThresholds):
        ap.add_argument(f"--{f.name.replace('_', '-')}", type=type(f.default), default=f.default)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    store = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False)   # read-only use: no DDL
    profiles = store.list_profiles(args.datasource)
    th = LinkThresholds(**{f.name: getattr(args, f.name) for f in fields(LinkThresholds)})
    files = args.connection or [f for f in (os.environ.get("SEMANTIC_CONNECTION_FILE"),
                                            os.environ.get("SEMANTIC_CRM_CONNECTION_FILE")) if f and os.path.exists(f)]
    probe = RoutedProbe.from_connectors([connector_from_file(f) for f in files], timeout=args.timeout)
    logging.info("connections: %s", {k or "(default)": database_of(v.c) for k, v in probe.probes.items()})
    priority = None
    if args.priority_certified:
        # Table patterns the certified vocabulary maps to — patterns, because a rescan can rename an
        # entity but not the pattern its tables come from.
        priority = set(store.concept_entities(args.tenant, args.datasource))
        logging.info("priority: %d certified table patterns", len(priority))

    def write(suffix: str, report) -> dict:
        (out / f"report{suffix}.json").write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=1, default=str))
        plan = apply_plan(report, profiles)
        (out / f"apply_plan{suffix}.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1, default=str))
        accepted = [(f"{p.ref_entity}.{p.ref_column}", f"{p.key_entity}.{p.key_column}") for p in report.accepted()]
        summary = {
            "connections": {k or "(default)": database_of(v.c) for k, v in probe.probes.items()},
            "priority_patterns": len(priority) if priority else None,
            "catalog_pairs": report.catalog.get("pairs"), "sampled_tables": report.sampled_tables,
            "column_families": report.column_families, "blocked": report.blocked,
            "step3_cost": report.cost, "probed_pairs": len(report.pairs),
            "stopped_at": {s: sum(1 for p in report.pairs if p.stage == s) for s in {p.stage for p in report.pairs}},
            "accepted": accepted, "plan_rows": len(plan), "queries": report.queries, "query_seconds": report.query_seconds,
        }
        if args.oracle:
            summary["oracle"] = score(accepted, [tuple(o.split("=", 1)) for o in args.oracle])
        (out / f"summary{suffix}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
        return summary

    def on_batch(name: str, report) -> None:
        if name == "priority":
            s = write("_oncelikli", report)
            logging.info("priority batch written: %s", json.dumps(s, ensure_ascii=False, default=str))

    report = CrossSourceLinkDiscovery(profiles, probe, thresholds=th).run(
        samples_cache=args.samples_cache, stop_after=args.stop_after, priority=priority, on_batch=on_batch)
    print(json.dumps(write("", report), ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
