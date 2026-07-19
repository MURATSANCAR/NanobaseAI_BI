#!/usr/bin/env python3
"""Verify or generate a minimal SPDX SBOM stub for Final Gate."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from common import ARTIFACTS, REPO_ROOT, ensure_artifacts, git_commit, utc_now, write_json


def _try_syft(out: Path) -> bool:
    if not shutil.which("syft"):
        return False
    # Best-effort: SBOM of repo directory
    try:
        subprocess.check_call(
            ["syft", f"dir:{REPO_ROOT}", "-o", "spdx-json", f"--file={out}"],
            cwd=REPO_ROOT,
        )
        return out.exists()
    except subprocess.CalledProcessError:
        return False


def _stub_sbom(out: Path) -> None:
    """Minimal SPDX-like document when syft is unavailable."""
    pkgs: list[dict] = []
    # Pin notable roots
    for req in [
        REPO_ROOT / "backend" / "query_gateway" / "requirements.txt",
        REPO_ROOT / "package.json",
    ]:
        if req.exists():
            pkgs.append(
                {
                    "SPDXID": f"SPDXRef-{req.name.replace('.', '-')}",
                    "name": req.name,
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                }
            )
    doc = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "nanobase-text2sql",
        "documentNamespace": f"https://nanobase.ai/spdx/{git_commit()}",
        "creationInfo": {
            "created": utc_now(),
            "creators": ["Tool: nanobase-release-gate"],
            "comment": "Stub SBOM — replace with syft CycloneDX/SPDX in CI",
        },
        "packages": pkgs,
        "files": [],
        "relationships": [],
        "nanobase": {
            "gitCommit": git_commit(),
            "stub": True,
            "includes": [
                "python-packages",
                "node-packages",
                "os-packages",
                "native-libraries",
                "oracle-sap-clients",
                "dbgpt-deps",
                "llama-cpp-build",
            ],
        },
    }
    write_json(out, doc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true", default=True)
    parser.add_argument("--require-real", action="store_true", help="Fail if only stub SBOM")
    args = parser.parse_args(argv)

    ensure_artifacts()
    out = ARTIFACTS / "sbom.spdx.json"
    real = _try_syft(out)
    if not real:
        _stub_sbom(out)
        print(f"Wrote stub SBOM {out}")
        if args.require_real:
            print("FAIL: syft not available; real SBOM required")
            return 1
    else:
        print(f"Wrote syft SBOM {out}")
    # Also emit dependency report summary
    write_json(
        ARTIFACTS / "dependency-report.json",
        {
            "generatedAt": utc_now(),
            "sbom": str(out.relative_to(REPO_ROOT)),
            "stub": not real,
            "gitCommit": git_commit(),
        },
    )
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
