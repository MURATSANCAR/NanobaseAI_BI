from __future__ import annotations

from nanobase_awel.operators.answer_fidelity_validator import (
    deterministic_fallback_answer,
    validate_answer_fidelity,
)
from nanobase_awel.operators.result_summarizer import summarize_result

CASES = [
    {"name": "empty", "cols": [], "rows": [], "truncated": False, "bad": "Toplam 999 TL"},
    {"name": "single", "cols": ["n"], "rows": [{"n": 5}], "truncated": False, "bad": "Toplam 42 müşteri"},
    {
        "name": "truncated",
        "cols": ["id"],
        "rows": [{"id": i} for i in range(10)],
        "truncated": True,
        "bad": "Tüm kayıtlar 999999",
    },
]


def test_fidelity_cases_reject_inventions():
    for case in CASES:
        summary = summarize_result(case["cols"], case["rows"], truncated=case["truncated"])
        ok, _ = validate_answer_fidelity(case["bad"], summary=summary, rows=case["rows"])
        # invented large numbers should fail; empty-result "999" fails
        assert not ok or case["name"] == "skip", case["name"]


def test_fallback_mentions_truncation():
    summary = summarize_result(["id"], [{"id": 1}], truncated=True)
    ans = deterministic_fallback_answer(
        summary=summary, columns=["id"], rows=[{"id": 1}], truncated=True
    )
    assert "kesil" in ans.lower() or "limit" in ans.lower()
