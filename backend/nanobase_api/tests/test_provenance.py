#!/usr/bin/env python3
"""Provenance mapping for SQL panel."""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("NANOBASE_ENV", "development")


def test_build_provenance():
    from nanobase_api.chat_gateway import _build_provenance, _with_provenance

    plan = {
        "tables": ["reporting.invoice"],
        "columns": ["invoice.amount"],
        "assumptions": ["TRY currency"],
        "warnings": ["soft"],
        "ambiguities": [],
        "confidence": 0.91,
        "dialect": "postgres",
    }
    p = _build_provenance(plan, executed=True, execution_mode="QUERY_GATEWAY")
    assert p["selected_tables"] == ["reporting.invoice"]
    assert p["columns"] == ["invoice.amount"]
    assert p["executed"] is True
    assert p["dialect"] == "postgres"
    assert p["confidence"] == 0.91

    out = _with_provenance({"reply": "x"}, plan, executed=False, execution_mode="PLAN_ONLY")
    assert out["provenance"]["executed"] is False
    assert out["provenance"]["execution_mode"] == "PLAN_ONLY"
    print("provenance ok")


if __name__ == "__main__":
    test_build_provenance()
