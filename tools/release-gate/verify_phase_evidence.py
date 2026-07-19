#!/usr/bin/env python3
"""Verify Phase 1–9 evidence packs against Final Gate requirements."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import ARTIFACTS, REPO_ROOT, ensure_artifacts, utc_now, write_json

REQUIRED = [
    "acceptance",
    "verification",
    "security-results",
    "performance-results",
    "chaos-results",
    "rollback-plan",
    "build-metadata",
]


def _exists_any(paths: list[Path]) -> bool:
    return any(p.exists() for p in paths)


def check_phase(phase: int) -> dict:
    docs = REPO_ROOT / "docs" / "architecture"
    arts = REPO_ROOT / "artifacts" / f"phase-{phase}"
    phase_dir = docs / f"phase-{phase}"

    present: list[str] = []
    missing: list[str] = []
    notes: list[str] = []

    checks: dict[str, list[Path]] = {
        "acceptance": [
            phase_dir / "acceptance.md",
            docs / f"phase-{phase}-acceptance.json",
            docs / f"phase-{phase}-results.md",
        ],
        "verification": [
            phase_dir / "verification-results.md",
            phase_dir / "verification-plan.md",
            docs / f"phase-{phase}-results.md",
        ],
        "security-results": [
            phase_dir / "security-results.md",
            arts / "security-results.json",
            arts / "security-corpus-results.json",
            arts / "oracle-security-corpus.json",
            arts / "hana-security-corpus.json",
            arts / "adversarial-results.json",
        ],
        "performance-results": [
            phase_dir / "performance-results.md",
            arts / "performance-results.json",
            docs / f"phase-{phase}-quality.json",
        ],
        "chaos-results": [
            phase_dir / "chaos-results.md",
            arts / "chaos-results.json",
        ],
        "rollback-plan": [
            phase_dir / "rollback-plan.md",
            docs / f"phase-{phase}.md",
        ],
        "build-metadata": [
            arts / "build-metadata.json",
        ],
    }

    for key in REQUIRED:
        ok = _exists_any(checks[key])
        if ok:
            present.append(key)
        else:
            missing.append(key)

    # Special cases
    legacy = phase <= 4
    if phase == 7 and not missing:
        status = "COMPLETE"
    elif phase in (8, 9) and "acceptance" in present and "security-results" in present:
        status = "OFFLINE_GO" if phase == 9 or (arts / "oracle-security-corpus.json").exists() else "PARTIAL"
        if phase == 8 and "chaos-results" in missing:
            status = "PARTIAL"
            notes.append("chaos/build-metadata incomplete; live PDB pending")
        if phase == 9:
            bm = arts / "build-metadata.json"
            if bm.exists():
                import json

                data = json.loads(bm.read_text(encoding="utf-8"))
                if data.get("verdict") != "GO" and not data.get("go"):
                    status = "PENDING_LIVE"
                    notes.append("live SAP / functional GO pending")
            else:
                status = "PENDING_LIVE"
    elif legacy and present:
        status = "LEGACY_ACCEPTED"
        notes.append("flat docs mapped; formal pack incomplete")
    elif missing:
        status = "PARTIAL" if present else "MISSING"
    else:
        status = "COMPLETE"

    return {
        "phase": phase,
        "status": status,
        "required": REQUIRED,
        "present": present,
        "missing": missing,
        "legacyAccepted": legacy and status == "LEGACY_ACCEPTED",
        "notes": "; ".join(notes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default=None)
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit non-zero if any phase is MISSING (LEGACY_ACCEPTED/PARTIAL allowed)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero unless all phases COMPLETE or LEGACY_ACCEPTED/OFFLINE_GO",
    )
    args = parser.parse_args(argv)

    ensure_artifacts()
    release = args.release
    if not release:
        mf = ARTIFACTS / "release-manifest.json"
        if mf.exists():
            import json

            release = json.loads(mf.read_text(encoding="utf-8")).get("release")
        else:
            release = "unspecified"

    phases = [check_phase(i) for i in range(1, 10)]
    report = {
        "release": release,
        "generatedAt": utc_now(),
        "phases": phases,
        "summary": {
            "complete": sum(1 for p in phases if p["status"] == "COMPLETE"),
            "legacyAccepted": sum(1 for p in phases if p["status"] == "LEGACY_ACCEPTED"),
            "partial": sum(1 for p in phases if p["status"] == "PARTIAL"),
            "pendingLive": sum(1 for p in phases if p["status"] == "PENDING_LIVE"),
            "missing": sum(1 for p in phases if p["status"] == "MISSING"),
            "offlineGo": sum(1 for p in phases if p["status"] == "OFFLINE_GO"),
        },
    }
    out = ARTIFACTS / "phase-evidence-report.json"
    write_json(out, report)
    print(f"Wrote {out}")
    for p in phases:
        print(f"  phase {p['phase']}: {p['status']} missing={p['missing']}")

    if args.fail_on_missing and report["summary"]["missing"]:
        return 1
    if args.strict:
        bad = [
            p
            for p in phases
            if p["status"] not in ("COMPLETE", "LEGACY_ACCEPTED", "OFFLINE_GO")
        ]
        if bad:
            return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
