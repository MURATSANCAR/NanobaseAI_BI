#!/usr/bin/env python3
"""Generate everyday names for catalog fields whose description changed. Bounded, lock-guarded,
idempotent: an unchanged description costs no model call. Runs from a timer; the bridge also runs
`vocabulary.maintain(only=…)` for a field the moment a person annotates it.

    maintain_vocabulary.py --max-targets 50
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path

from semantic_layer.candidates.llm_client import LlmClient
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.config import SemanticSettings
from semantic_layer.runtime.llm_queue import LlmQueue, QueuedLlm
from semantic_layer.store.catalog_store import open_store
from semantic_layer import vocabulary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-targets", type=int, default=50, help="model calls per run")
    ap.add_argument("--lock", default=os.environ.get("SEMANTIC_VOCABULARY_LOCK", "/tmp/semantic-vocabulary.lock"))
    args = ap.parse_args()
    settings = SemanticSettings.from_env()
    store = open_store(settings.store_dsn, create=False)
    profiles = one_entity_per_pattern(store.list_profiles(settings.datasource_id),
                                      store.concept_entities(settings.tenant_id, settings.datasource_id))
    llm = QueuedLlm(LlmClient(settings.llm_base, settings.llm_model, settings.llm_key, settings.llm_timeout,
                              extra={"chat_template_kwargs": {"enable_thinking": False}} | settings.llm_extra),
                    LlmQueue.from_env(store.engine), purpose="bg:vocabulary",
                    tenant_id=settings.tenant_id, datasource_id=settings.datasource_id)
    Path(args.lock).parent.mkdir(parents=True, exist_ok=True)
    with open(args.lock, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("başka bir sözlük üretimi çalışıyor")
        result = vocabulary.maintain(store, settings, llm, profiles, max_targets=args.max_targets)
    result["queue"] = vocabulary.counts(store, settings)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 1 if result["failed"] and not result["calls"] - result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
