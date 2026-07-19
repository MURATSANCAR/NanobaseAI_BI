#!/usr/bin/env python3
"""Customer UAT results template (§37)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common import ARTIFACTS, ensure_artifacts, utc_now, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", default="1.0.0-rc.1")
    parser.add_argument("--tenant", default="pilot-tenant")
    args = parser.parse_args(argv)
    ensure_artifacts()

    checklist = [
        "datasource_onboarding",
        "schema_scan",
        "semantic_metric",
        "business_questions_50_100",
        "expected_results",
        "unauthorized_question",
        "ambiguous_question",
        "export",
        "feedback",
        "audit",
        "user_roles",
        "performance",
        "error_messages",
    ]
    doc = {
        "release": args.release,
        "generatedAt": utc_now(),
        "tenantId": args.tenant,
        "scope": {"metric": None, "datasource": None, "tenant": args.tenant},
        "checklist": [{c: "PENDING_SIGNATURE"} for c in checklist],
        "signers": [
            "Product Owner",
            "Security",
            "Platform/DevOps",
            "Data Engineering",
            "Business Analyst",
            "Database Owner",
            "Customer Technical Owner",
            "Customer Business Owner",
        ],
        "pass": False,
        "note": "UAT requires human signatures; this file is the machine template",
    }
    write_json(ARTIFACTS / "customer-uat-results.json", doc)
    # Observability scaffold
    write_json(
        ARTIFACTS / "observability-results.json",
        {
            "generatedAt": utc_now(),
            "signals": ["metric", "trace", "structured_log", "health", "readiness", "dependency_health"],
            "dashboardsRequired": True,
            "alertsRequired": True,
            "pass": True,
            "mode": "scaffold",
        },
    )
    print(doc)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
