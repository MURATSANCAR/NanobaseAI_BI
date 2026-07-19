"""File-based public share tokens for budget board packs."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _shares_root() -> Path:
    root = Path(os.environ.get("SECRETS_ROOT", "/tmp")) / "budget-shares"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def create_share(
    *,
    resource_type: str,
    resource_id: str,
    ttl_hours: float,
    password: str | None = None,
    tenant_id: str,
) -> dict[str, Any]:
    token = secrets.token_urlsafe(24)
    hours = max(0.1, float(ttl_hours or 24))
    expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    entry = {
        "token": token,
        "resource_type": str(resource_type or "budget_pack"),
        "resource_id": str(resource_id or ""),
        "tenant_id": str(tenant_id or "default"),
        "expires_at": expires_at.isoformat(),
        "password_hash": _hash_password(password) if password else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _shares_root() / f"{token}.json"
    path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    return {
        "token": token,
        "expires_at": entry["expires_at"],
        "resource_type": entry["resource_type"],
        "resource_id": entry["resource_id"],
    }


def get_share(token: str) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if not raw or "/" in raw or ".." in raw:
        return None
    path = _shares_root() / f"{raw}.json"
    if not path.is_file():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(entry, dict):
        return None
    exp = entry.get("expires_at")
    if exp:
        try:
            expires = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < datetime.now(timezone.utc):
                return None
        except Exception:
            return None
    return entry
