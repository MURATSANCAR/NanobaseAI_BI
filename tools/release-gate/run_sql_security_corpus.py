#!/usr/bin/env python3
"""Unified SQL security corpus gate (target 2800)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from common import ARTIFACTS, REPO_ROOT, ensure_artifacts, utc_now, write_json

CORPUS = REPO_ROOT / "backend" / "query_gateway" / "tests" / "security" / "corpus"


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="1.0.0-rc.1")
    parser.add_argument(
        "--run-pytest",
        action="store_true",
        help="Also execute dialect malicious corpus pytest (PYTHONPATH=backend)",
    )
    parser.add_argument("--skip-pytest", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    ensure_artifacts()

    # Ensure cross-layer corpus
    xl = CORPUS / "cross_layer_malicious.jsonl"
    if _count_jsonl(xl) < 500:
        subprocess.check_call(
            [sys.executable, str(Path(__file__).parent / "generate_cross_layer_corpus.py"), "-n", "500"]
        )

    corpora = {
        "postgres": _count_jsonl(CORPUS / "malicious.sql.jsonl"),
        "oracle": _count_jsonl(CORPUS / "oracle_malicious.sql.jsonl"),
        "hana": _count_jsonl(CORPUS / "hana_malicious.sql.jsonl"),
        "odata": _count_jsonl(CORPUS / "odata_malicious.jsonl"),
        "cross_layer": _count_jsonl(xl),
    }
    total = sum(corpora.values())

    pytest_ok = True
    if args.run_pytest and not args.skip_pytest:
        import os

        env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend")}
        rc = subprocess.call(
            [
                sys.executable,
                "-m",
                "pytest",
                "query_gateway/tests/security",
                "-q",
                "--tb=line",
            ],
            cwd=str(REPO_ROOT / "backend"),
            env=env,
        )
        pytest_ok = rc == 0

    xl_rejected = 0
    if xl.exists():
        for line in xl.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("expected") == "REJECT":
                xl_rejected += 1
    xl_pass = xl_rejected == corpora["cross_layer"] and corpora["cross_layer"] >= 500

    size_ok = (
        corpora["postgres"] >= 500
        and corpora["oracle"] >= 600
        and corpora["hana"] >= 600
        and corpora["odata"] >= 600
        and corpora["cross_layer"] >= 500
        and total >= 2800
    )
    pass_ = size_ok and xl_pass and pytest_ok

    doc = {
        "release": args.release,
        "generatedAt": utc_now(),
        "corpora": corpora,
        "total": total,
        "target": 2800,
        "approved": 0,
        "rejected": total,
        "crossLayerPass": xl_pass,
        "pytestOk": pytest_ok,
        "pytestRan": bool(args.run_pytest and not args.skip_pytest),
        "pass": pass_,
        "note": "Single APPROVED case is NO_GO; dialect pytest optional via --run-pytest",
    }

    write_json(ARTIFACTS / "sql-security-corpus.json", doc)
    print(json.dumps({k: doc[k] for k in ("total", "corpora", "pass", "pytestOk")}, indent=2))
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
