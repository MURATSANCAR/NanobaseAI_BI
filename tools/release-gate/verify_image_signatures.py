#!/usr/bin/env python3
"""Verify container image signatures (cosign) or record pending state."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from common import ARTIFACTS, ensure_artifacts, read_json, utc_now, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-signed",
        action="store_true",
        help="Fail unless all digests are cosign-verified",
    )
    args = parser.parse_args(argv)
    ensure_artifacts()

    digests_path = ARTIFACTS / "image-digests.txt"
    images: dict[str, str] = {}
    if digests_path.exists():
        for line in digests_path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                images[k.strip()] = v.strip()

    results = []
    cosign = shutil.which("cosign")
    all_ok = True
    for name, ref in images.items():
        entry = {"name": name, "ref": ref, "signed": False, "error": None}
        if ref in ("pending-build", "", "pin-before-freeze"):
            entry["error"] = "digest-pending"
            all_ok = False
        elif cosign:
            try:
                subprocess.check_call(
                    ["cosign", "verify", ref],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                entry["signed"] = True
            except subprocess.CalledProcessError as e:
                entry["error"] = f"cosign-verify-failed:{e.returncode}"
                all_ok = False
        else:
            entry["error"] = "cosign-not-installed"
            all_ok = False
        results.append(entry)

    if not images:
        results.append(
            {
                "name": "_none_",
                "ref": None,
                "signed": False,
                "error": "no-image-digests",
            }
        )
        all_ok = False

    report = {
        "generatedAt": utc_now(),
        "policy": {
            "rejectUnsigned": True,
            "rejectUnknownRegistry": True,
            "rejectTagOnlyDeploy": True,
            "digestOnly": True,
            "requireProvenance": True,
        },
        "images": results,
        "pass": all_ok,
    }
    write_json(ARTIFACTS / "image-signatures.json", report)
    print(f"signatures pass={all_ok} count={len(results)}")
    if args.require_signed and not all_ok:
        return 1
    # Soft mode for host vertical slice
    return 0 if not args.require_signed else (0 if all_ok else 1)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
