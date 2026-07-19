#!/usr/bin/env python3
"""Record / verify build provenance for Final Gate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import ARTIFACTS, ensure_artifacts, git_commit, utc_now, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-slsa", action="store_true")
    args = parser.parse_args(argv)
    ensure_artifacts()

    mf = ARTIFACTS / "release-manifest.json"
    release = None
    if mf.exists():
        import json

        release = json.loads(mf.read_text(encoding="utf-8")).get("release")

    prov = {
        "generatedAt": utc_now(),
        "release": release,
        "gitCommit": git_commit(),
        "buildType": "https://nanobase.ai/provenance/host-build@v1",
        "builder": {
            "id": "nanobase-release-gate",
            "version": "1.0.0",
        },
        "materials": [{"uri": f"git+https://github.com/nanobase/text2sql@{git_commit()}"}],
        "slsaLevel": "stub" if not args.require_slsa else "required",
        "stub": not args.require_slsa,
        "note": "Replace with SLSA provenance attestation from GitHub Actions when CI builds images",
    }
    write_json(ARTIFACTS / "build-provenance.json", prov)
    print(f"Wrote build-provenance.json stub={prov['stub']}")
    if args.require_slsa:
        print("FAIL: SLSA attestation not yet wired")
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
