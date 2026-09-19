"""Mine business rules from Logo views and CRM saved views into the catalog.

    mine_rules.py --source logo|crm [--apply] [--limit N] [--out report.jsonl]

Report only by default. --apply writes candidates with evidence and certifies the ones the
policy allows (the source's own rule, refuted OK, no conflicting certified term).
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter

from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.config import SemanticSettings
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.profiler.connectors import connector_from_file
from semantic_layer.rule_miner import crm_queries, logo_views, probe
from semantic_layer.rule_miner.common import Catalog
from semantic_layer.store.catalog_store import open_store


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", choices=("logo", "crm"), required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="only the first N candidate groups (for a trial)")
    ap.add_argument("--out", default="", help="jsonl report path")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    all_profiles = store.list_profiles(s.datasource_id)
    unique = one_entity_per_pattern(all_profiles, store.concept_entities(s.tenant_id, s.datasource_id))
    catalog = Catalog(unique, all_profiles)
    logo = connector_from_file(s.connection_file)
    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    crm = connector_from_file(crm_file) if os.path.exists(crm_file) else None
    t0 = time.time()
    cands = []
    if args.source == "logo":
        views = logo_views.fetch(logo)
        parsed = 0
        for name, definition in views:
            got = logo_views.candidates(name, definition, catalog)
            parsed += 1 if got else 0
            cands += got
        print(json.dumps({"views": len(views), "views_with_candidates": parsed, "raw_candidates": len(cands)}), flush=True)
    else:
        rows = crm_queries.fetch(crm)
        for kind, name, xml in rows:
            cands += crm_queries.candidates(name, xml, catalog, source_kind=kind)
        print(json.dumps({"saved_views": len(rows), "raw_candidates": len(cands)}), flush=True)
    groups = probe.group(cands)
    if args.limit:
        groups = groups[: args.limit]
    kinds = Counter(k for g in groups for k in g.kinds)
    types = Counter(g.cand.semantic_type for g in groups)
    print(json.dumps({"groups": len(groups), "kinds": dict(kinds), "types": dict(types)}, ensure_ascii=False), flush=True)
    engine = EvidenceEngine(store, min_support=s.min_support, threshold=s.certify_threshold)
    report: list[dict] = []
    tally = probe.run(groups, catalog, lambda c: (crm if "MSCRM" in (c.schema or "").upper() else logo), store, engine, s,
                      apply=args.apply, report=report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for r in report:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"tally": tally, "seconds": round(time.time() - t0, 1), "applied": args.apply}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
