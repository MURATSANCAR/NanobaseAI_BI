"""Fail-closed secret resolution for gateway."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from query_gateway.config.settings import Settings
from query_gateway.domain.errors import VAULT_UNAVAILABLE, GatewayError


def resolve_password(cfg: dict[str, Any], settings: Settings) -> str:
    """Resolve datasource password. Never log the value."""
    if cfg.get("password"):
        return str(cfg["password"])
    ref = cfg.get("secret_ref") or cfg.get("password_file")
    if not ref:
        raise GatewayError(VAULT_UNAVAILABLE, "Datasource credential bulunamadı.", status=503)

    ref_s = str(ref)
    # Vault path
    if ref_s.startswith("vault:") or (settings.vault_addr and ref_s.startswith("secret/")):
        if not settings.vault_addr or not settings.vault_token:
            if settings.vault_fail_closed:
                raise GatewayError(VAULT_UNAVAILABLE, "Vault kullanılamıyor.", status=503, retryable=True)
            raise GatewayError(VAULT_UNAVAILABLE, "Vault kullanılamıyor.", status=503, retryable=True)
        try:
            from nanobase_api.secrets_resolver import resolve_secret

            return resolve_secret(ref_s)
        except Exception as e:
            raise GatewayError(
                VAULT_UNAVAILABLE,
                "Vault credential okunamadı.",
                status=503,
                retryable=True,
            ) from e

    try:
        from nanobase_api.secrets_resolver import resolve_secret

        return resolve_secret(ref_s)
    except Exception:
        p = Path(ref_s.removeprefix("file:"))
        if not p.is_absolute():
            p = settings.secrets_root / p
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
        if settings.vault_fail_closed:
            raise GatewayError(VAULT_UNAVAILABLE, "Credential dosyası okunamadı.", status=503)
        raise GatewayError(VAULT_UNAVAILABLE, "Credential dosyası okunamadı.", status=503)
