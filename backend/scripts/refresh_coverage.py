#!/usr/bin/env python3
"""Try to refute every coverage declaration against the source: count rows outside the declared
range per table, record declared / contested. Run by a timer, and by hand the first time.

    refresh_coverage.py            # measure and print the verdicts
"""
from __future__ import annotations

import json
from pathlib import Path

from semantic_layer import coverage
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.config import SemanticSettings
from semantic_layer.conventions import Conventions
from semantic_layer.profiler.connectors import connector_from_file
from semantic_layer.store.catalog_store import open_store


def main() -> int:
    settings = SemanticSettings.from_env()
    store = open_store(settings.store_dsn, create=False)
    profiles = store.list_profiles(settings.datasource_id)
    conventions = Conventions.from_profiles(one_entity_per_pattern(profiles, store.concept_entities(settings.tenant_id, settings.datasource_id)))
    rules = coverage.load_rules(Path(settings.project_dir) / "coverage.yml") if settings.project_dir else []
    connector = connector_from_file(settings.connection_file) if settings.connection_file and Path(settings.connection_file).exists() else None
    # only the entities a certified concept points at: those are the tables an answer can read
    entities = {m.entity for c in store.find_concepts(settings.tenant_id, settings.datasource_id, status="CERTIFIED", limit=100000)
                for m in store.list_mappings(c.id)}
    out = coverage.refresh(store, settings, profiles, rules, connector, conventions, entities=entities)
    for r in out["rows"]:
        print(f"{r['status']:10s} {r['table']:28s} {r['from']}–{r['to']}  dönem dışı: {r['spill']}")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
