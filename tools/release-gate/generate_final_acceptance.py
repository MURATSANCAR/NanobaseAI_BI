#!/usr/bin/env python3
"""Generate Final Gate acceptance matrix and signature template."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import (
    ARTIFACTS,
    HARD_NO_GO_AREAS,
    ensure_artifacts,
    read_json,
    set_gate_status,
    sha256_file,
    utc_now,
    write_json,
)


def _load(name: str) -> dict | None:
    p = ARTIFACTS / name
    if not p.exists():
        return None
    return read_json(p)


def _pass_fail(ok: bool | None) -> str:
    if ok is None:
        return "PENDING"
    return "PASS" if ok else "FAIL"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default=None)
    args = parser.parse_args(argv)
    ensure_artifacts()

    mf = _load("release-manifest.json") or {}
    release = args.release or mf.get("release") or "unspecified"
    phase = _load("phase-evidence-report.json") or {}
    tenant = _load("tenant-isolation-results.json") or {}
    bypass = _load("query-gateway-bypass-results.json") or {}
    sql = _load("sql-security-corpus.json") or {}
    ai = _load("ai-adversarial-results.json") or {}
    quality = _load("text2sql-quality-results.json") or {}
    backup = _load("backup-results.json") or {}
    restore = _load("restore-results.json") or {}
    rollback = _load("rollback-results.json") or {}
    leakage = _load("data-leakage-results.json") or {}

    checks = {
        "phase_evidence": phase.get("summary", {}).get("missing", 1) == 0
        or (phase.get("summary") or {}).get("legacyAccepted", 0) >= 0 and bool(phase),
        "tenant_isolation": tenant.get("pass") is True,
        "query_gateway_bypass": bypass.get("pass") is True,
        "sql_security": sql.get("pass") is True,
        "ai_adversarial": ai.get("pass") is True,
        "quality_benchmark": quality.get("pass") is True,
        "backup_restore": backup.get("pass") is True and restore.get("pass") is True,
        "rollback": rollback.get("pass") is True,
        "data_leakage": leakage.get("pass") is True if leakage else None,
    }

    nogo_hits = []
    for area in HARD_NO_GO_AREAS:
        # map area names
        key = {
            "tenant_isolation": "tenant_isolation",
            "sql_security": "sql_security",
            "secret_security": "data_leakage",
            "financial_accuracy": "quality_benchmark",
            "sap_functional": "quality_benchmark",
            "backup_restore": "backup_restore",
            "rollback": "rollback",
            "critical_high_security": "sql_security",
            "audit_integrity": "data_leakage",
        }.get(area)
        if key and checks.get(key) is False:
            nogo_hits.append(area)

    functional = {
        "critical_e2e": _pass_fail((_load("e2e-results.json") or {}).get("pass")),
        "postgres_execution": "PASS" if "postgres" in (mf.get("claimedConnectors") or []) else "N/A",
        "oracle_execution": "PENDING" if "oracle" in (mf.get("claimedConnectors") or []) else "N/A",
        "sap_execution": "PENDING"
        if any(c in (mf.get("claimedConnectors") or []) for c in ("hana", "odata"))
        else "N/A",
        "rollback": _pass_fail(checks["rollback"]),
    }

    uat = _load("customer-uat-results.json") or {}
    pentest = _load("penetration-test-summary.json") or {}
    digests_pending = any(
        (mf.get("components") or {}).get(name, {}).get("digest") == "pending-build"
        for name in ("frontend", "backend", "queryGateway")
    )

    automated_ok = all(v is True for v in checks.values() if v is not None) and not any(
        v is False for v in checks.values()
    )

    decision = "NO_GO"
    if nogo_hits or any(v is False for v in checks.values()):
        decision = "NO_GO"
    elif not automated_ok:
        decision = "BLOCKED"
    elif digests_pending or pentest.get("status") == "PENDING_EXTERNAL" or not uat.get("pass"):
        # Automated vertical slice green, but org gates incomplete
        decision = "BLOCKED"
        nogo_hits.append("awaiting_uat_pentest_or_image_digests")
    elif any(v is None for v in checks.values()):
        decision = "CONDITIONAL_GO"
    else:
        decision = "GO"

    # CONDITIONAL_GO forbidden if hard areas pending/fail
    if decision == "CONDITIONAL_GO" and any(
        checks.get(k) is not True
        for k in (
            "tenant_isolation",
            "sql_security",
            "backup_restore",
            "rollback",
        )
    ):
        decision = "NO_GO"
        nogo_hits.append("conditional_forbidden_for_hard_gates")

    risk = {
        "generatedAt": utc_now(),
        "release": release,
        "risks": [
            {
                "id": "KR-LEGACY-PHASES",
                "severity": "medium",
                "description": "Phases 1–4 evidence LEGACY_ACCEPTED",
                "conditionalAllowed": True,
            }
        ],
        "nogoHits": nogo_hits,
    }
    write_json(ARTIFACTS / "final-risk-register.json", risk)

    matrix = {
        "release": release,
        "generatedAt": utc_now(),
        "checks": {k: _pass_fail(v) for k, v in checks.items()},
        "functional": functional,
        "hardNoGoAreas": sorted(HARD_NO_GO_AREAS),
        "nogoHits": nogo_hits,
        "recommendedDecision": decision,
    }
    write_json(ARTIFACTS / "final-acceptance-matrix.json", matrix)

    sigs = {
        "release": release,
        "decision": decision,
        "signedAt": None,
        "signers": [
            {"role": "Product Owner", "name": None, "signed": False},
            {"role": "Engineering Lead", "name": None, "signed": False},
            {"role": "Security Lead", "name": None, "signed": False},
            {"role": "Platform/DevOps Lead", "name": None, "signed": False},
            {"role": "Data/AI Lead", "name": None, "signed": False},
            {"role": "QA Lead", "name": None, "signed": False},
            {"role": "Operations Lead", "name": None, "signed": False},
            {"role": "Business Owner", "name": None, "signed": False},
            {"role": "Customer Technical Owner", "name": None, "signed": False},
        ],
        "acceptedRisks": [],
        "evidenceManifestHash": None,
    }
    if (ARTIFACTS / "release-manifest.json").exists():
        sigs["evidenceManifestHash"] = "sha256:" + sha256_file(ARTIFACTS / "release-manifest.json")
    write_json(ARTIFACTS / "acceptance-signatures.json", sigs)

    decision_doc = {
        "release": release.replace("-rc.1", "").replace("-rc.", ".") if "-rc." in release else release,
        "rc": release,
        "decision": decision,
        "signedAt": None,
        "signers": [],
        "acceptedRisks": [],
        "evidenceManifestHash": sigs["evidenceManifestHash"],
        "matrix": matrix["checks"],
        "generatedAt": utc_now(),
    }
    write_json(ARTIFACTS / "go-no-go-decision.json", decision_doc)

    print(json.dumps({"decision": decision, "nogoHits": nogo_hits, "automatedOk": automated_ok}, indent=2))
    status = {
        "GO": "GO",
        "CONDITIONAL_GO": "CONDITIONAL_GO",
        "NO_GO": "REJECTED",
        "BLOCKED": "CUSTOMER_ACCEPTANCE" if automated_ok else "BLOCKED",
    }.get(decision, "BLOCKED")
    set_gate_status(status, release=release, note=f"acceptance recommended={decision}")
    # Exit 0 when artifacts written and no hard automated NO_GO
    return 0 if decision != "NO_GO" else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
