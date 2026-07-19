"""Smoke: Oracle benchmark YAML exists and has ≥250 questions; cross-dialect ≥100."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
BENCH = ROOT / "tests" / "text2sql" / "oracle-250.yaml"
CROSS = ROOT / "tests" / "text2sql" / "cross-dialect-100.json"


def test_oracle_benchmark_file():
    if not BENCH.is_file():
        from query_gateway.tests.security.generate_oracle_benchmark import main

        main()
    text = BENCH.read_text(encoding="utf-8")
    assert text.count("id: ora-") >= 250
    assert "dialect: oracle" in text
    assert "forbid_tokens" in text


def test_cross_dialect_metrics_file():
    if not CROSS.is_file():
        from query_gateway.tests.security.generate_oracle_benchmark import main

        main()
    data = json.loads(CROSS.read_text(encoding="utf-8"))
    assert len(data["metrics"]) >= 100
    assert data["min_equivalence"] >= 0.98
