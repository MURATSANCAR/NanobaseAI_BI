"""Persist active BI datasource across API restarts and bridge stampede."""

from __future__ import annotations

import json
import os
from pathlib import Path

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
ACTIVE_FILE = SECRETS / "active_datasource"
CONNECTION_LOCAL = SECRETS / "connection.local.json"

# Bridge historically reads a different path — keep both in sync on activate.
_BRIDGE_SOURCES_CANDIDATES = [
    Path(os.environ["BI_SOURCES_FILE"]) if os.environ.get("BI_SOURCES_FILE") else None,
    SECRETS / "connection.local.json",
    Path(__file__).resolve().parents[3]
    / "configs"
    / "sources"
    / "local"
    / "connection.local.json",
    Path("/data/nanobaseai/bi/frontend/configs/sources/local/connection.local.json"),
]


def _bridge_sources_files() -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for p in _BRIDGE_SOURCES_CANDIDATES:
        if p is None:
            continue
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def read_persisted_active() -> str | None:
    try:
        if ACTIVE_FILE.is_file():
            val = ACTIVE_FILE.read_text(encoding="utf-8").strip()
            if val:
                return val
    except OSError:
        pass
    for path in _bridge_sources_files():
        try:
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            aid = raw.get("active_id")
            if aid:
                return str(aid)
        except (OSError, json.JSONDecodeError):
            continue
    return None


def write_persisted_active(source_id: str) -> None:
    sid = str(source_id or "").strip()
    if not sid:
        return
    try:
        SECRETS.mkdir(parents=True, exist_ok=True)
        ACTIVE_FILE.write_text(sid + "\n", encoding="utf-8")
        try:
            ACTIVE_FILE.chmod(0o600)
        except OSError:
            pass
    except OSError:
        pass

    for path in _bridge_sources_files():
        try:
            raw: dict = {}
            if path.is_file():
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    raw = loaded
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = {"sources": {}}
            raw["active_id"] = sid
            path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            try:
                path.chmod(0o600)
            except OSError:
                pass
        except (OSError, json.JSONDecodeError, TypeError):
            continue


def resolve_active_id(*, memory_id: str | None = None, known_ids: set[str] | None = None) -> str:
    """Resolve active datasource without letting env stomp an explicit activate.

    Priority: in-memory → persisted file → NANOBASE_ACTIVE_DB → first known id.
    No hardcoded source names.
    """
    candidates = [
        (memory_id or "").strip(),
        read_persisted_active() or "",
        (os.environ.get("NANOBASE_ACTIVE_DB") or "").strip(),
    ]
    for cand in candidates:
        if not cand:
            continue
        if known_ids is not None and known_ids and cand not in known_ids:
            continue
        return cand
    if known_ids:
        return sorted(known_ids)[0]
    return (os.environ.get("NANOBASE_ACTIVE_DB") or "").strip() or "default"


def resolve_schema_datasource_id(
    *,
    query_datasource_id: str | None = None,
    body_datasource_id: str | None = None,
    memory_id: str | None = None,
) -> str:
    """Explicit query/body datasource wins; else active resolution."""
    for cand in (query_datasource_id, body_datasource_id):
        sid = str(cand or "").strip()
        if sid:
            return sid
    return resolve_active_id(memory_id=memory_id)


def prefer_datasource_id(
    *candidates: str | None,
    memory_id: str | None = None,
    known_ids: set[str] | None = None,
) -> str:
    """First non-empty candidate, else resolve_active_id. No hardcoded source names."""
    for cand in candidates:
        sid = str(cand or "").strip()
        if not sid:
            continue
        if known_ids is not None and known_ids and sid not in known_ids:
            continue
        return sid
    return resolve_active_id(memory_id=memory_id, known_ids=known_ids)
