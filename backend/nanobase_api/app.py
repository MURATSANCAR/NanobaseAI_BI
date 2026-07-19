"""Nanobase BI API — production FastAPI surface (Faz 3/4).

Reuses the bridge route surface and overlays bi_meta datasources.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from bridge import app as bridge_mod  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

app = bridge_mod.app
app.title = "Nanobase BI API"
app.version = "0.4.0"

META_DSN = os.environ.get(
    "NANOBASE_META_DSN",
    "postgresql+psycopg2://bi_meta@127.0.0.1:5434/bi_meta",
)
_engine = None

bridge_mod.ACTIVE_DB["id"] = os.environ.get("NANOBASE_ACTIVE_DB", "bi_reporting")


def _meta_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(META_DSN, pool_pre_ping=True, pool_size=5)
    return _engine


_orig_sources_list = bridge_mod._sources_list_payload
_orig_health = bridge_mod.health


def _sources_list_payload_overlay() -> dict:
    base = _orig_sources_list()
    by_id = {s["id"]: s for s in (base.get("sources") or [])}

    try:
        with _meta_engine().connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT id, label, driver, dialect, host, port, database,
                           username, ssl, secret_ref, tenant_id, project_id
                    FROM bi_sources
                    ORDER BY label
                    """
                )
            ).mappings()
            for r in rows:
                by_id[r["id"]] = {
                    "id": r["id"],
                    "label": r["label"],
                    "driver": r["driver"],
                    "dialect": r["dialect"],
                    "host": r["host"],
                    "port": r["port"],
                    "database": r["database"],
                    "username": r["username"],
                    "ssl": bool(r["ssl"]),
                    "secret_ref": r["secret_ref"],
                    "tenant_id": r["tenant_id"],
                    "project_id": r["project_id"] or "default",
                    "password_masked": "********" if r["secret_ref"] else None,
                    "deployment": "cloud",
                }
    except Exception:
        pass

    if "bi_reporting" not in by_id:
        by_id["bi_reporting"] = {
            "id": "bi_reporting",
            "label": "BI Reporting (RO)",
            "driver": "postgresql",
            "dialect": "postgresql",
            "host": "127.0.0.1",
            "port": 5435,
            "database": "bi_reporting",
            "username": "bi_reporting_ro",
            "ssl": False,
            "secret_ref": "file:/data/nanobaseai/bi/secrets/reporting-ro.password",
            "tenant_id": "default",
            "project_id": "default",
            "password_masked": "********",
            "deployment": "onprem",
        }

    active = os.environ.get("NANOBASE_ACTIVE_DB") or bridge_mod.ACTIVE_DB.get("id") or "bi_reporting"
    if active not in by_id:
        active = next(iter(by_id), "bi_reporting")
    bridge_mod.ACTIVE_DB["id"] = active

    return {"active_id": active, "sources": list(by_id.values())}


async def _health_overlay():
    h = await _orig_health()
    meta_ok = False
    try:
        with _meta_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
            meta_ok = True
    except Exception:
        meta_ok = False
    return {
        **h,
        "service": "nanobase_api",
        "bridge": False,
        "meta": meta_ok,
        "engine": "nanobase_api",
        "active_source": bridge_mod.ACTIVE_DB.get("id"),
    }


bridge_mod._sources_list_payload = _sources_list_payload_overlay
bridge_mod.health = _health_overlay
