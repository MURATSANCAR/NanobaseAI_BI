"""File-based team / public share links (dashboards, chat answers, budget packs)."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _shares_root() -> Path:
    root = Path(os.environ.get("SECRETS_ROOT", "/tmp")) / "bi-shares"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _legacy_budget_root() -> Path:
    return Path(os.environ.get("SECRETS_ROOT", "/tmp")) / "budget-shares"


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _safe_token(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw or "/" in raw or ".." in raw or len(raw) > 200:
        return None
    return raw


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_expires(exp: Any) -> datetime | None:
    if not exp:
        return None
    try:
        expires = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires
    except Exception:
        return None


def _is_expired(entry: dict[str, Any]) -> bool:
    expires = _parse_expires(entry.get("expires_at"))
    if expires is None:
        return False
    return expires < _now()


def _path_for(token: str) -> Path:
    return _shares_root() / f"{token}.json"


def _read_entry_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(entry, dict):
        return None
    if _is_expired(entry):
        return None
    return entry


def _write_entry(token: str, entry: dict[str, Any]) -> None:
    path = _path_for(token)
    path.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")


def _public_fields(entry: dict[str, Any], *, include_token: bool = False) -> dict[str, Any]:
    token = str(entry.get("token") or "")
    out: dict[str, Any] = {
        "resource_type": str(entry.get("resource_type") or ""),
        "resource_id": str(entry.get("resource_id") or ""),
        "expires_at": entry.get("expires_at"),
        "view_count": int(entry.get("view_count") or 0),
        "password_protected": bool(entry.get("password_hash")),
        "created_at": entry.get("created_at"),
        "token_hash": entry.get("token_hash") or (_token_hash(token) if token else None),
    }
    if include_token and token:
        out["token"] = token
    if entry.get("max_views") is not None:
        out["max_views"] = entry.get("max_views")
    return out


def create_share(
    *,
    resource_type: str,
    resource_id: str,
    ttl_hours: float | int | None = 168,
    password: str | None = None,
    tenant_id: str = "default",
    max_views: int | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = secrets.token_urlsafe(24)
    created = _now().isoformat()
    ttl = ttl_hours
    if ttl is None:
        ttl = 168
    ttl_f = float(ttl)
    if ttl_f <= 0:
        expires_at: str | None = None
    else:
        expires_at = (_now() + timedelta(hours=ttl_f)).isoformat()

    entry: dict[str, Any] = {
        "token": token,
        "token_hash": _token_hash(token),
        "resource_type": str(resource_type or "superset_dashboard"),
        "resource_id": str(resource_id or ""),
        "tenant_id": str(tenant_id or "default"),
        "expires_at": expires_at,
        "password_hash": _hash_password(password) if password else None,
        "created_at": created,
        "view_count": 0,
        "views": [],
    }
    if max_views is not None:
        try:
            mv = int(max_views)
            if mv > 0:
                entry["max_views"] = mv
        except Exception:
            pass
    if isinstance(payload, dict) and payload:
        entry["payload"] = payload

    _write_entry(token, entry)
    return _public_fields(entry, include_token=True)


def get_share(token: str) -> dict[str, Any] | None:
    raw = _safe_token(token)
    if not raw:
        return None
    entry = _read_entry_file(_path_for(raw))
    if entry:
        if not entry.get("token"):
            entry["token"] = raw
        return entry

    # Legacy budget-pack files written by budget_shares before unified store.
    legacy = _legacy_budget_root() / f"{raw}.json"
    entry = _read_entry_file(legacy)
    if entry:
        if not entry.get("token"):
            entry["token"] = raw
        if not entry.get("token_hash"):
            entry["token_hash"] = _token_hash(raw)
        entry.setdefault("view_count", 0)
        entry.setdefault("views", [])
        return entry
    return None


def get_share_by_token_or_hash(token_or_hash: str) -> tuple[str, dict[str, Any]] | None:
    raw = _safe_token(token_or_hash)
    if not raw:
        return None
    direct = get_share(raw)
    if direct:
        return str(direct.get("token") or raw), direct

    needle = raw.lower()
    for path in _shares_root().glob("*.json"):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(entry, dict) or _is_expired(entry):
            continue
        th = str(entry.get("token_hash") or "")
        tok = str(entry.get("token") or path.stem)
        if th == needle or th.lower() == needle or _token_hash(tok) == needle:
            if not entry.get("token"):
                entry["token"] = tok
            return tok, entry
    return None


def list_shares(*, tenant_id: str = "default") -> list[dict[str, Any]]:
    tid = str(tenant_id or "default")
    out: list[dict[str, Any]] = []
    for path in sorted(_shares_root().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(entry, dict) or _is_expired(entry):
            continue
        if str(entry.get("tenant_id") or "default") != tid:
            continue
        if not entry.get("token"):
            entry["token"] = path.stem
        # List returns token so operators can copy the link (token is the capability).
        out.append(_public_fields(entry, include_token=True))
    return out


def delete_share(token_or_hash: str, *, tenant_id: str | None = None) -> bool:
    found = get_share_by_token_or_hash(token_or_hash)
    if not found:
        # Also try legacy budget path delete by exact token filename.
        raw = _safe_token(token_or_hash)
        if raw:
            legacy = _legacy_budget_root() / f"{raw}.json"
            if legacy.is_file():
                try:
                    legacy.unlink()
                    return True
                except Exception:
                    return False
        return False
    token, entry = found
    if tenant_id is not None and str(entry.get("tenant_id") or "default") != str(tenant_id):
        return False
    path = _path_for(token)
    try:
        if path.is_file():
            path.unlink()
            return True
    except Exception:
        return False
    legacy = _legacy_budget_root() / f"{token}.json"
    try:
        if legacy.is_file():
            legacy.unlink()
            return True
    except Exception:
        return False
    return False


def record_view(
    token: str,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
    bump: bool = True,
) -> dict[str, Any] | None:
    entry = get_share(token)
    if not entry:
        return None
    if not bump:
        return entry

    max_views = entry.get("max_views")
    count = int(entry.get("view_count") or 0)
    if max_views is not None and count >= int(max_views):
        raise PermissionError("share_view_limit")

    views = entry.get("views")
    if not isinstance(views, list):
        views = []
    views.append(
        {
            "at": _now().isoformat(),
            "ip": (ip or "")[:64] or None,
            "user_agent": (user_agent or "")[:240] or None,
        }
    )
    # Cap stored log
    if len(views) > 200:
        views = views[-200:]
    entry["views"] = views
    entry["view_count"] = count + 1
    tok = str(entry.get("token") or token)
    # Persist into unified store even if it was a legacy file.
    _write_entry(tok, entry)
    return entry


def list_views(token_or_hash: str, *, tenant_id: str | None = None) -> dict[str, Any] | None:
    found = get_share_by_token_or_hash(token_or_hash)
    if not found:
        return None
    token, entry = found
    if tenant_id is not None and str(entry.get("tenant_id") or "default") != str(tenant_id):
        return None
    views = entry.get("views") if isinstance(entry.get("views"), list) else []
    return {
        "token": token,
        "view_count": int(entry.get("view_count") or len(views)),
        "views": list(reversed(views[-100:])),
    }


def verify_password(entry: dict[str, Any], password: str | None) -> bool:
    expected = entry.get("password_hash")
    if not expected:
        return True
    if not password:
        return False
    return _hash_password(password) == str(expected)
