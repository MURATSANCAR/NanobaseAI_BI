#!/usr/bin/env python3
"""Approve generated vocabulary that is measured to work; leave the rest for a person, with the reason.

    auto_approve_vocabulary.py                  # report only
    auto_approve_vocabulary.py --source crm     # only fields whose table lives in the CRM schema
    auto_approve_vocabulary.py --apply

See `semantic_layer/vocabulary_probe.py` for what "measured to work" means.
"""
from __future__ import annotations

import argparse
import copy
import json
import time

from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.config import SemanticSettings
from semantic_layer.conventions import Conventions
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.store.catalog_store import open_store
from semantic_layer import vocabulary_probe as P


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write approvals and reasons (default: report only)")
    ap.add_argument("--source", choices=("crm", "logo"), help="limit to one source, decided by the table's schema")
    ap.add_argument("--shard", default="0/1", help="i/n — measure only this slice of the pending rows, for running n processes")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    profiles = one_entity_per_pattern(store.list_profiles(s.datasource_id), store.concept_entities(s.tenant_id, s.datasource_id))
    entities = None
    if args.source:
        crm = {p.entity for p in profiles if "MSCRM" in (p.schema_name or "").upper()}
        entities = crm if args.source == "crm" else {p.entity for p in profiles} - crm
    base = SemanticResolver(store, s.tenant_id, s.datasource_id, profiles, conventions=Conventions.from_profiles(profiles))

    def factory(probe_store):
        # one resolver's derived structures, shared; only the store (and so the certified index) differs
        r = copy.copy(base)
        r.store = probe_store
        r._roots_for, r._roots = None, {}
        return r

    started = time.time()
    engine = EvidenceEngine(store, min_support=s.min_support, threshold=s.certify_threshold)
    i, _, n = args.shard.partition("/")
    out = P.auto_decide(store, s, profiles, engine, resolver_factory=factory, entities=entities, apply=args.apply,
                        shard=(int(i), int(n or 1)))
    out["shard"] = args.shard
    out["seconds"] = round(time.time() - started, 1)
    out["applied"] = args.apply
    print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
