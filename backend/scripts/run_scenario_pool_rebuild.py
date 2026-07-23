#!/usr/bin/env python3
"""Periodic scenario pool rebuild — regenerate question×period×table combinations.

Run via systemd timer (nanobase-scenario-rebuild.timer) or manually:

  PYTHONPATH=backend backend/.venv/bin/python backend/scripts/run_scenario_pool_rebuild.py

Env:
  SCENARIO_REBUILD_DATASOURCES   comma list (default: erp,sigorta)
  SCENARIO_REBUILD_TENANT        default: default
  SCENARIO_REBUILD_LOCK_FILE     default: /tmp/nanobase-scenario-rebuild.lock
  SCENARIO_OFFLINE_VALIDATION    typically 1 for overnight full fills
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
        print("SKIP another scenario rebuild is already running", flush=True)
        sys.exit(0)
    fh.seek(0)
    fh.truncate()
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def _rebuild_one(*, tenant_id: str, datasource_id: str) -> dict:
    from nanobase_api.scenario_engine.application.build_pipeline import start_build
    from nanobase_api.scenario_engine.infrastructure.reporting_exec import datasource_ro_dsn
    from nanobase_api.scenario_engine.infrastructure.schema_snapshot import snapshot_from_pg
    from nanobase_api.scenario_engine.infrastructure.store import reset_scenario_store

    store = reset_scenario_store()
    snapshot = None
    dsn = datasource_ro_dsn(datasource_id)
    if dsn:
        try:
            snapshot = snapshot_from_pg(dsn, datasource_id=datasource_id)
            print(f"  snapshot ok dsn_host={dsn.split('@')[-1][:80]}", flush=True)
        except Exception as e:
            print(f"  snapshot warn: {e}", flush=True)
            snapshot = None

    t0 = time.time()
    result = start_build(
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        snapshot=snapshot,
        auto_publish=True,
        force=True,
    )
    elapsed = round(time.time() - t0, 1)
    counts = result.get("counts") or {}
    print(
        f"  STATUS={result.get('status')} PHASE={result.get('phase')} "
        f"instances={counts.get('instances')} paraphrases={counts.get('paraphrases')} "
        f"ELAPSED={elapsed}s ERROR={result.get('error')}",
        flush=True,
    )
    return result


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    # Prefer production env file when present
    for cand in (
        Path(os.environ.get("NANOBASE_API_ENV", "")),
        backend / "nanobase_api.env",
        Path("/data/nanobaseai/bi/frontend/backend/nanobase_api.env"),
    ):
        if cand and str(cand) not in (".", ""):
            _load_env_file(cand)

    # Sensible overnight defaults (caller env wins via setdefault above + explicit below)
    os.environ.setdefault("SCENARIO_COMBINATION_MODE", "both")
    os.environ.setdefault("SCENARIO_COMBINATION_SCALE", "full")
    os.environ.setdefault("SCENARIO_MAX_COMBINATIONS", "8000")
    os.environ.setdefault("SCENARIO_SQL_DISABLED", "0")
    os.environ.setdefault("SCENARIO_OFFLINE_VALIDATION", "1")
    os.environ.setdefault("SCENARIO_REQUIRE_LIVE_VALIDATION", "0")

    lock_path = Path(
        os.environ.get("SCENARIO_REBUILD_LOCK_FILE") or "/tmp/nanobase-scenario-rebuild.lock"
    )
    lock_fh = _acquire_lock(lock_path)

    tenant_id = (os.environ.get("SCENARIO_REBUILD_TENANT") or "default").strip()
    sources = _datasources()
    print(
        f"START scenario pool rebuild tenant={tenant_id} datasources={sources} "
        f"mode={os.environ.get('SCENARIO_COMBINATION_MODE')} "
        f"offline={os.environ.get('SCENARIO_OFFLINE_VALIDATION')}",
        flush=True,
    )

    failures = 0
    try:
        for ds in sources:
            print(f"BUILD datasource={ds}", flush=True)
            try:
                result = _rebuild_one(tenant_id=tenant_id, datasource_id=ds)
                if str(result.get("status") or "").upper() == "FAILED":
                    failures += 1
            except Exception:
                failures += 1
                traceback.print_exc()
    finally:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)
            lock_fh.close()
        except Exception:
            pass

    print(f"DONE failures={failures}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
