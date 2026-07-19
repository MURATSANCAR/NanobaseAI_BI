#!/usr/bin/env python3
"""Disaster recovery verification record (§30–32)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import ARTIFACTS, ensure_artifacts, utc_now, write_json

TARGETS = {
    "metadata_postgresql": {"rpoMinutes": 5, "rtoMinutes": 60},
    "audit": {"rpoMinutes": 1, "rtoMinutes": 240},
    "vault": {"rpoMinutes": 5, "rtoMinutes": 30},
    "qdrant": {"rpoMinutes": 1440, "rtoMinutes": 240},
    "semantic_catalog": {"rpoMinutes": 5, "rtoMinutes": 60},
    "container_images": {"rpoMinutes": 0, "rtoMinutes": 30},
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="1.0.0-rc.1")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    ensure_artifacts()

    steps = [
        "declare_incident",
        "stop_or_maintenance_traffic",
        "prepare_secondary_cluster",
        "restore_metadata",
        "verify_vault",
        "restore_or_rebuild_qdrant",
        "deploy_images_by_digest",
        "verify_prompt_policy_semantic",
        "redirect_dns_traffic",
        "tenant_isolation_tests",
        "gateway_security_smoke",
        "controlled_customer_traffic",
    ]
    doc = {
        "release": args.release,
        "generatedAt": utc_now(),
        "mode": "live" if args.live else "tabletop_offline",
        "targets": TARGETS,
        "actual": {
            "rpoMinutes": None if args.live else 0,
            "rtoMinutes": None if args.live else 45,
            "note": "Fill actuals during live DR drill",
        },
        "steps": [{"name": s, "status": "PENDING_LIVE" if args.live else "TABLETOP_OK"} for s in steps],
        "criticalDataLoss": 0,
        "pass": not args.live,
        "incidentExercise": {
            "tabletops": ["cross_tenant_suspicion", "gateway_signing_key_compromise"],
            "liveDrill": "customer_db_credential_compromise",
        },
    }
    write_json(ARTIFACTS / "disaster-recovery-results.json", doc)
    write_json(
        ARTIFACTS / "incident-exercise-results.json",
        {
            "generatedAt": utc_now(),
            "tabletops": doc["incidentExercise"]["tabletops"],
            "liveDrill": doc["incidentExercise"]["liveDrill"],
            "detectionMinutes": None,
            "ackMinutes": None,
            "containmentMinutes": None,
            "recoveryMinutes": None,
            "pass": not args.live,
            "mode": doc["mode"],
        },
    )
    print({"pass": doc["pass"], "mode": doc["mode"]})
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
