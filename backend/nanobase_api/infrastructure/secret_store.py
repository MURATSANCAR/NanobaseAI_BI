"""File/Vault secret store for datasource passwords."""

from __future__ import annotations

from pathlib import Path

from nanobase_api.config import get_settings
from nanobase_api.secrets_resolver import resolve_secret


class FileVaultSecretStore:
    """Stores passwords as files under SECRETS_ROOT; vault refs supported for resolve."""

    def store_datasource_password(
        self, *, tenant_id: str, datasource_id: str, password: str
    ) -> str:
        root = Path(get_settings().secrets_root)
        root.mkdir(parents=True, exist_ok=True)
        # never put password in the filename content beyond id
        path = root / f"ds-{tenant_id}-{datasource_id}.password"
        path.write_text(password.strip() + "\n", encoding="utf-8")
        path.chmod(0o600)
        return f"file:{path}"

    def resolve(self, ref: str) -> str:
        return resolve_secret(ref)
