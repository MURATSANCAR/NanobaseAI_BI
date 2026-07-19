#!/usr/bin/env python3
"""Validate release-manifest.json structure and freeze fields."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import ARTIFACTS, read_json

REQUIRED_TOP = ("release", "gitCommit", "createdAt", "components")
REQUIRED_COMPONENTS = (
    "frontend",
    "backend",
    "queryGateway",
    "dbgpt",
    "awel",
    "model",
    "embedding",
    "semanticCatalog",
    "queryPolicies",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-digests",
        action="store_true",
        help="Fail if any image digest is pending-build",
    )
    args = parser.parse_args(argv)

    path = ARTIFACTS / "release-manifest.json"
    if not path.exists():
        print(f"FAIL: missing {path}")
        return 1
    data = read_json(path)
    errors: list[str] = []
    for k in REQUIRED_TOP:
        if k not in data:
            errors.append(f"missing top-level {k}")
    comps = data.get("components") or {}
    for k in REQUIRED_COMPONENTS:
        if k not in comps:
            errors.append(f"missing component {k}")
    if args.require_digests:
        for name in ("frontend", "backend", "queryGateway"):
            dig = (comps.get(name) or {}).get("digest", "pending-build")
            if dig == "pending-build" or not dig:
                errors.append(f"{name} digest not pinned")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print(f"OK release-manifest {data.get('release')} commit={data.get('gitCommit')}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
