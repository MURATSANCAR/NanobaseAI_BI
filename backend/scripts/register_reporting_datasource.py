#!/usr/bin/env python3
"""Register bi_reporting (RO) into DB-GPT for Faz-1 NL2SQL smoke."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE = os.environ.get("DBGPT_BASE", "http://127.0.0.1:5670")
SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
RO_PASSWORD_FILE = SECRETS / "reporting-ro.password"


def _http_json(method: str, url: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw}") from e


def _wait_ready(base: str, attempts: int = 60) -> None:
    url = f"{base.rstrip('/')}/api/v1/chat/db/support/type"
    for i in range(attempts):
        try:
            _http_json("GET", url)
            return
        except Exception:
            time.sleep(1)
            if i == attempts - 1:
                raise SystemExit(f"DB-GPT not ready at {base}")


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    if not RO_PASSWORD_FILE.is_file():
        raise SystemExit(f"Missing {RO_PASSWORD_FILE}")
    password = RO_PASSWORD_FILE.read_text(encoding="utf-8").strip()
    _wait_ready(base)

    payload = {
        "db_type": "postgresql",
        "db_name": "bi_reporting",
        "db_host": "127.0.0.1",
        "db_port": 5435,
        "db_user": "bi_reporting_ro",
        "db_pwd": password,
        "comment": "BI reporting (RO / analytics seed)",
        "ext_config": {
            "database": "bi_reporting",
            "schema": "analytics",
        },
    }

    create_url = f"{base.rstrip('/')}/api/v2/serve/datasources"
    try:
        res = _http_json("POST", create_url, payload)
        print(f"created bi_reporting: {res.get('success', res)}")
    except RuntimeError as e:
        print(f"create note: {e}")
        res = _http_json("PUT", create_url, payload)
        print(f"updated bi_reporting: {res.get('success', res)}")

    # Refresh schema cache
    try:
        _http_json(
            "POST",
            f"{base.rstrip('/')}/api/v1/chat/db/refresh",
            {"db_name": "bi_reporting", "db_type": "postgresql"},
        )
        print("refreshed bi_reporting schema")
    except RuntimeError as e:
        print(f"refresh warn: {e}")

    listed = _http_json("GET", f"{base.rstrip('/')}/api/v1/chat/db/list")
    names = [d.get("db_name") for d in (listed.get("data") or [])]
    print("datasources:", names)
    if "bi_reporting" not in names:
        raise SystemExit("bi_reporting not present in DB-GPT list")


if __name__ == "__main__":
    main()
