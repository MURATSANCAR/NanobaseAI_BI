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
            str(REPO_ROOT / "tests" / "final-gate" / "tenant_isolation"),
            "-q",
            "--tb=line",
        ],
        cwd=str(REPO_ROOT),
    )
    doc = {
        "release": args.release,
        "generatedAt": utc_now(),
        "layers": [
            "api",
            "metadata",
            "qdrant",
            "query_gateway",
            "postgres_rls",
            "oracle_vpd",
            "sap",
            "honeytenant",
        ],
        "honeytenant": "honeytenant-final-gate",
        "leaks": 0 if rc == 0 else 1,
        "pass": rc == 0,
        "pytestExitCode": rc,
    }
    write_json(ARTIFACTS / "tenant-isolation-results.json", doc)
    print(doc)
    return rc


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
