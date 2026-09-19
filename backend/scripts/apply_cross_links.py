#!/usr/bin/env python3
"""Write measured cross-source links (discover_cross_links' apply_plan.json) into the catalog.

    apply_cross_links.py /var/tmp/crmlinks2/apply_plan.json            # report only
    apply_cross_links.py /var/tmp/crmlinks2/apply_plan.json --apply    # write

Each entry names one profile row and one relationship. A relationship on the same column that the
plan says it replaces is removed; everything else on the row stays. The bridge reads the new links
after it reloads profiles (restart it, or wait for the catalog check).
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

import sqlalchemy as sa

from semantic_layer.config import SemanticSettings
from semantic_layer.store import schema as S
from semantic_layer.store.catalog_store import _json, open_store


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    plan = json.load(open(args.plan, encoding="utf-8"))
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    counts: Counter = Counter()
    links: Counter = Counter()
    with (store.engine.begin() if args.apply else store.engine.connect()) as conn:
        for entry in plan:
            rel = entry["relationship"]
            row = conn.execute(sa.select(S.sl_schema_profile.c.id, S.sl_schema_profile.c.relationships_json).where(
                S.sl_schema_profile.c.datasource_id == entry["datasource_id"],
                S.sl_schema_profile.c.table_name == entry["table_name"])).first()
            if row is None:
                counts["profil yok"] += 1
                continue
            current = [r for r in (_json(row[1]) or []) if isinstance(r, dict)]
            same = lambda r: (str(r.get("column", "")).upper() == str(rel["column"]).upper()
                              and str(r.get("ref_entity", "")).upper() == str(rel["ref_entity"]).upper())
            replaced = [r for r in current if same(r) or r in (entry.get("replaces") or [])]
            updated = [r for r in current if r not in replaced] + [rel]
            counts["değiştirilen" if replaced else "eklenen"] += 1
            links[f"{entry['table_name']}.{rel['column']} → {rel['ref_entity']}.{rel['ref_column']} ({rel.get('confidence')})"] += 1
            if args.apply:
                conn.execute(S.sl_schema_profile.update().where(S.sl_schema_profile.c.id == row[0])
                             .values(relationships_json=updated))
    print(json.dumps({"applied": args.apply, "rows": dict(counts), "links": dict(links)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
