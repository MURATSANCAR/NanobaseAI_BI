"""Discover join relationships between databases on one connection — dry run only.

Reads the catalog's profiles, measures value overlap on the customer's database with sampled,
single-core queries, and writes two files: the full discovery report (every pair, the stage it
stopped at and why) and the apply plan (exactly which relationship would be written to which profile
row). Nothing is written to the catalog.

    python -m scripts.discover_cross_links --out /var/tmp/crmlinks \
        [--oracle ACCOUNTBASE.new_logicalref=LG_CLCARD.LOGICALREF ...]

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
    CrossSourceLinkDiscovery, LinkThresholds, apply_plan, probe_for,
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
    ap.add_argument("--connection", default=os.environ.get("SEMANTIC_CONNECTION_FILE"))
    ap.add_argument("--timeout", type=int, default=900, help="per-query timeout for the confirmation scans")
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
    connector = connector_from_file(args.connection)
    probe = probe_for(connector, timeout=args.timeout)
    report = CrossSourceLinkDiscovery(profiles, probe, thresholds=th).run()

    (out / "report.json").write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=1, default=str))
    plan = apply_plan(report, profiles)
    (out / "apply_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1, default=str))

    accepted = [(f"{p.ref_entity}.{p.ref_column}", f"{p.key_entity}.{p.key_column}") for p in report.accepted()]
    summary = {
        "catalog_pairs": report.catalog.get("pairs"), "sampled_tables": report.sampled_tables,
        "column_families": report.column_families, "blocked": report.blocked,
        "probed_pairs": len(report.pairs),
        "stopped_at": {s: sum(1 for p in report.pairs if p.stage == s) for s in {p.stage for p in report.pairs}},
        "accepted": accepted, "plan_rows": len(plan), "queries": report.queries, "query_seconds": report.query_seconds,
    }
    if args.oracle:
        summary["oracle"] = score(accepted, [tuple(o.split("=", 1)) for o in args.oracle])
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
