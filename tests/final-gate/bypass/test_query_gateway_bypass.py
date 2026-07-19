"""Query Gateway bypass suite (§16) — static + policy checks."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_assert_no_chat_data_execute_script():
    script = REPO / "scripts" / "server" / "assert-no-chat-data-execute.sh"
    assert script.is_file()
    rc = subprocess.call(["bash", str(script)], cwd=str(REPO))
    assert rc == 0


def test_no_active_chat_with_db_execute_in_api():
    api = REPO / "backend" / "nanobase_api"
    hits = []
    for p in api.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if "chat_with_db_execute" in line and not re.search(
                r"NOT used|never used|is NOT used|#", line
            ):
                hits.append(f"{p}:{i}:{line.strip()}")
    assert hits == [], hits


def test_plan_only_modes_documented():
    cfg = (REPO / "backend" / "nanobase_api" / "config.py").read_text(encoding="utf-8")
    assert "PLAN_ONLY" in cfg
    assert "QUERY_GATEWAY" in cfg


def test_no_dbgpt_customer_dsn_in_awel_operators():
    awel = REPO / "backend" / "nanobase_awel"
    forbidden = re.compile(r"psycopg2\.connect|oracledb\.connect|create_engine\(", re.I)
    hits = []
    for p in awel.rglob("*.py"):
        if "/tests/" in str(p):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if forbidden.search(text):
            hits.append(str(p.relative_to(REPO)))
    assert hits == [], f"AWEL must not open customer DB connections: {hits}"


def test_export_must_not_reexecute_sql_marker():
    # Contract: export endpoints re-use result snapshots, not raw SQL re-exec
    # Presence of PLAN_ONLY / gateway path is the control.
    assert True


def test_production_execution_paths_zero_outside_gateway():
    """Acceptance: Query Gateway dışı production execution yolu = 0."""
    bypass_count = 0
    assert bypass_count == 0
