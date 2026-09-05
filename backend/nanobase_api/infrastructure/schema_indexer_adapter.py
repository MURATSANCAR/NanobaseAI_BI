"""Adapter: run tools/schema-indexer CLI."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from nanobase_api.config import get_settings


class SchemaIndexerAdapter:
    def run_scan(self, *, datasource_id: str, schemas: str | None = None) -> dict[str, Any]:
        s = get_settings()
        indexer = Path(s.schema_indexer_root)
        py = s.python_bin
        from nanobase_api.infrastructure.datasource_registry import reporting_datasource_id

        rid = reporting_datasource_id()
        ds = rid if datasource_id == "nanobase_test" else datasource_id
        if ds == rid:
            schemas = schemas or "analytics,public"
        else:
            try:
                from nanobase_api.infrastructure.datasource_registry import resolve_mssql_connect_cfg

                mssql_cfg = resolve_mssql_connect_cfg(ds)
            except Exception:
                mssql_cfg = None
            if mssql_cfg:
                schemas = schemas or ",".join(mssql_cfg.get("allowed_schemas") or ["dbo"])
            else:
                schemas = schemas or "public"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(indexer)
        env.setdefault("SECRETS_ROOT", s.secrets_root)
        cmd = [
            py,
            "-m",
            "cli.main",
            "--datasource",
            ds,
            "--schemas",
            schemas,
            "--json",
        ]
        # --json prints report JSON; pipeline also prints a line — capture stdout and find JSON
        proc = subprocess.run(
            cmd,
            cwd=str(indexer.parent.parent) if indexer.name == "schema-indexer" else str(indexer),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "indexer failed")[:800])
        # Prefer report file
        out_dir = Path(os.environ.get("PHASE2_OUT_DIR", "/data/nanobaseai/bi/frontend/docs/architecture"))
        report_path = out_dir / f"schema-index-{ds}.json"
        if report_path.is_file():
            return json.loads(report_path.read_text(encoding="utf-8"))
        # parse last JSON object from stdout
        text = proc.stdout.strip()
        start = text.find("{")
        if start >= 0:
            return json.loads(text[start:])
        return {"ok": True, "raw": text[:500]}
