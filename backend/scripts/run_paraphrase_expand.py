#!/usr/bin/env python3
"""Continuous end-user paraphrase expansion from question grammar.

Lighter than full scenario rebuild: keeps published SQL scenarios, regenerates
all combinatorial user-language surfaces whenever grammar evolves.

  PYTHONPATH=backend backend/.venv/bin/python backend/scripts/run_paraphrase_expand.py

Env:
  SCENARIO_REBUILD_DATASOURCES   comma list (default: erp,sigorta)
  SCENARIO_REBUILD_TENANT        default: default
  SCENARIO_PARAPHRASE_LOCK_FILE  default: /tmp/nanobase-paraphrase-expand.lock
"""

from __future__ import annotations

import fcntl
import os
import sys
import time
import traceback
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


def _datasources() -> list[str]:
    raw = (os.environ.get("SCENARIO_REBUILD_DATASOURCES") or "erp,sigorta").strip()
    return [p.strip() for p in raw.split(",") if p.strip()]


def _acquire_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        print("SKIP another paraphrase expand is already running", flush=True)
        sys.exit(0)
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    for cand in (
        Path(os.environ.get("NANOBASE_API_ENV", "")),
        backend / "nanobase_api.env",
        Path("/data/nanobaseai/bi/frontend/backend/nanobase_api.env"),
    ):
        if cand and str(cand) not in (".", ""):
            _load_env_file(cand)

    lock_path = Path(
        os.environ.get("SCENARIO_PARAPHRASE_LOCK_FILE")
        or "/tmp/nanobase-paraphrase-expand.lock"
    )
    lock_fh = _acquire_lock(lock_path)

    tenant_id = (os.environ.get("SCENARIO_REBUILD_TENANT") or "default").strip()
    sources = _datasources()

    from nanobase_api.scenario_engine.application.paraphrase_refresh import (
        expand_paraphrases_continuous,
    )
    from nanobase_api.scenario_engine.infrastructure.question_grammar import GRAMMAR_VERSION
    from nanobase_api.scenario_engine.infrastructure.store import reset_scenario_store

    print(
        f"START paraphrase expand tenant={tenant_id} datasources={sources} "
        f"grammar={GRAMMAR_VERSION}",
        flush=True,
    )

    failures = 0
    try:
        # Fresh hydrate from SQL so we see latest published scenarios
        store = reset_scenario_store()
        for ds in sources:
            print(f"EXPAND datasource={ds}", flush=True)
            t0 = time.time()
            try:
                result = expand_paraphrases_continuous(
                    tenant_id=tenant_id,
                    datasource_id=ds,
                    store=store,
                    purge_periodless=True,
                )
                refresh = result.get("refresh") or {}
                cov = result.get("coverage") or {}
                print(
                    f"  added={refresh.get('paraphrases_added')} "
                    f"scanned={refresh.get('texts_scanned')} "
                    f"scenarios={refresh.get('scenarios')} "
                    f"paras={cov.get('published_paraphrases')} "
                    f"avg/scenario={cov.get('avg_paraphrases_per_scenario')} "
                    f"by_family={refresh.get('by_family')} "
                    f"ELAPSED={round(time.time() - t0, 1)}s",
                    flush=True,
                )
            except Exception:
                failures += 1
                traceback.print_exc()
    finally:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            lock_fh.close()
        except Exception:
            pass

    print(f"DONE failures={failures} grammar={GRAMMAR_VERSION}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
