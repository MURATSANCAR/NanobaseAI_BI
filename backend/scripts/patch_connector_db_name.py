"""Honor ext_config.database when building DB-GPT connectors.

DB-GPT uses db_name as both the connection id and the Postgres database name.
Neon ERP and Sigorta both use database ``neondb``, so we store source ids
(``erp`` / ``sigorta``) as db_name and the real database in
``ext_config.database``.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def apply() -> None:
    from dbgpt_serve.datasource.manages.connector_manager import ConnectorManager

    if getattr(ConnectorManager._build_connector, "_nanobase_patched", False):
        return

    original = ConnectorManager._build_connector

    def _build_connector(self, db_name: str):  # type: ignore[no-untyped-def]
        db_config = self.storage.get_db_config(db_name)
        try:
            ext = db_config.get("ext_config")
            db_json = json.loads(ext) if isinstance(ext, str) and ext else (ext or {})
            if not isinstance(db_json, dict):
                db_json = {}
        except (json.JSONDecodeError, TypeError):
            db_json = {}

        real_db = str(db_json.get("database") or db_name).strip() or db_name
        if real_db == db_name:
            return original(self, db_name)

        from dbgpt.util.configure.manager import _resolve_env_vars
        from dbgpt_ext.datasource.schema import DBType

        logger.info("Nanobase connector: id=%s → database=%s", db_name, real_db)
        pwd = db_config.get("db_pwd") or ""
        if pwd:
            pwd = _resolve_env_vars(pwd)
        db_type = DBType.of_db_type(db_config.get("db_type"))
        if not db_type or db_type.is_file_db() or db_type.value() == "oracle":
            return original(self, db_name)
        connect_instance = self.get_cls_by_dbtype(db_type.value())
        return connect_instance.from_uri_db(  # type: ignore[attr-defined]
            host=db_config.get("db_host"),
            port=db_config.get("db_port"),
            user=db_config.get("db_user"),
            pwd=pwd,
            db_name=real_db,
            schema=db_json.get("schema"),
        )

    _build_connector._nanobase_patched = True  # type: ignore[attr-defined]
    ConnectorManager._build_connector = _build_connector  # type: ignore[method-assign]
    logger.info("Applied Nanobase ConnectorManager._build_connector patch")
