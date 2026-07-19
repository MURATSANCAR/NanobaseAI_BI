#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from common import ARTIFACTS, REPO_ROOT, ensure_artifacts, utc_now, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="1.0.0-rc.1")
    args = parser.parse_args(argv)
    ensure_artifacts()
    rc = subprocess.call(
        [
            sys.executable,
            "-m",
            "pytest",
            str(REPO_ROOT / "tests" / "final-gate" / "bypass"),
            "-q",
            "--tb=line",
        ],
        cwd=str(REPO_ROOT),
    )
    # Static script
    rc2 = subprocess.call(
        ["bash", str(REPO_ROOT / "scripts" / "server" / "assert-no-chat-data-execute.sh")],
        cwd=str(REPO_ROOT),
    )
    ok = rc == 0 and rc2 == 0
    doc = {
        "release": args.release,
        "generatedAt": utc_now(),
        "checks": [
            "no_chat_with_db_execute",
            "no_awel_customer_db_connect",
            "plan_only_rollback_path",
            "gateway_only_execution",
        ],
        "productionExecutionPathsOutsideGateway": 0 if ok else 1,
        "pass": ok,
        "pytestExitCode": rc,
        "assertScriptExitCode": rc2,
    }
    write_json(ARTIFACTS / "query-gateway-bypass-results.json", doc)
    print(doc)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
