"""Secret resolution: Vault KV (optional) with file fallback.

Refs:
  - vault:secret/data/bi/reporting#password
  - file:/data/nanobaseai/bi/secrets/reporting-ro.password
  - reporting-ro.password  (relative to SECRETS_ROOT)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import httpx

SECRETS_ROOT = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
VAULT_ADDR = (os.environ.get("VAULT_ADDR") or "").rstrip("/")
VAULT_TOKEN = os.environ.get("VAULT_TOKEN") or ""
VAULT_NAMESPACE = os.environ.get("VAULT_NAMESPACE") or ""


class SecretError(RuntimeError):
    pass


def _read_file(path: Path) -> str:
    if not path.is_file():
        raise SecretError(f"secret file missing: {path}")
    return path.read_text(encoding="utf-8").strip()


def _vault_read(path: str, key: str) -> str:
    if not VAULT_ADDR or not VAULT_TOKEN:
        raise SecretError("VAULT_ADDR/VAULT_TOKEN not configured")
    # Accept both secret/data/... and secret/...
    api_path = path
    if not api_path.startswith("/"):
        api_path = "/" + api_path
    if "/data/" not in api_path and api_path.startswith("/secret/"):
        # KV v2
        api_path = api_path.replace("/secret/", "/secret/data/", 1)
    url = f"{VAULT_ADDR}/v1{api_path}"
    headers = {"X-Vault-Token": VAULT_TOKEN}
    if VAULT_NAMESPACE:
        headers["X-Vault-Namespace"] = VAULT_NAMESPACE
    with httpx.Client(timeout=10.0) as client:
        r = client.get(url, headers=headers)
        if r.status_code >= 400:
            raise SecretError(f"vault HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
    payload = ((data.get("data") or {}).get("data")) or (data.get("data") or {})
    if key not in payload or payload[key] in (None, ""):
        raise SecretError(f"vault key missing: {key} @ {path}")
    return str(payload[key]).strip()


def resolve_secret(ref: Optional[str], *, default_file: Optional[str] = None) -> str:
    """Resolve a secret reference. Never logs the value."""
    raw = (ref or "").strip()
    if not raw and default_file:
        raw = default_file
    if not raw:
        raise SecretError("empty secret ref")

    if raw.startswith("vault:"):
        body = raw[len("vault:") :]
        if "#" in body:
            path, key = body.split("#", 1)
        else:
            path, key = body, "value"
        try:
            return _vault_read(path, key)
        except SecretError:
            # optional file mirror: SECRETS_ROOT / last path segment
            mirror = SECRETS_ROOT / Path(path).name
            if mirror.is_file():
                return _read_file(mirror)
            raise

    if raw.startswith("file:"):
        return _read_file(Path(raw[len("file:") :]))

    p = Path(raw)
    if p.is_file():
        return _read_file(p)
    return _read_file(SECRETS_ROOT / raw)


def secrets_status() -> dict:
    return {
        "secrets_root": str(SECRETS_ROOT),
        "vault_configured": bool(VAULT_ADDR and VAULT_TOKEN),
        "vault_addr": VAULT_ADDR or None,
        "mode": "vault+file" if (VAULT_ADDR and VAULT_TOKEN) else "file",
    }
