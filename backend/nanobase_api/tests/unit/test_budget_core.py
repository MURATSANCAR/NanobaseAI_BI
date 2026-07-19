"""Unit tests for budget compute / FX / lock semantics."""

from __future__ import annotations

from nanobase_api.budget_fx import convert_amount
from nanobase_api.budgets import compute_fields


def test_used_pct_includes_commitments():
    row = compute_fields(
        {
            "allocated": 100,
            "committed": 10,
            "actual": 40,
            "status": "approved",
            "fiscal_year": 2026,
        }
    )
    assert row["used_pct"] == 50.0
    assert row["remaining"] == 50.0
    assert row["health"] == "ok"


def test_health_only_for_approved():
    row = compute_fields(
        {
            "allocated": 100,
            "committed": 0,
            "actual": 90,
            "status": "draft",
            "fiscal_year": 2026,
        }
    )
    assert row["used_pct"] == 90.0
    assert row["health"] is None


def test_watch_and_over():
    watch = compute_fields(
        {"allocated": 100, "committed": 0, "actual": 85, "status": "approved", "fiscal_year": 2026}
    )
    over = compute_fields(
        {"allocated": 100, "committed": 10, "actual": 95, "status": "approved", "fiscal_year": 2026}
    )
    assert watch["health"] == "watch"
    assert over["health"] == "over"
    assert over["used_pct"] == 105.0


def test_fx_same_currency():
    assert convert_amount(12.5, from_currency="TRY", to_currency="try", rates=[]) == 12.5


def test_fx_missing_rate_returns_none():
    assert (
        convert_amount(
            10,
            from_currency="USD",
            to_currency="TRY",
            rates=[],
        )
        is None
    )


def test_fx_direct_and_inverse():
    rates = [
        {
            "from_currency": "USD",
            "to_currency": "TRY",
            "rate": 30.0,
            "as_of": "2026-01-01T00:00:00+00:00",
        }
    ]
    assert convert_amount(2, from_currency="USD", to_currency="TRY", rates=rates) == 60.0
    assert convert_amount(60, from_currency="TRY", to_currency="USD", rates=rates) == 2.0


def test_pct_rounded_two_decimals():
    row = compute_fields(
        {
            "allocated": 9,
            "committed": 0,
            "actual": 4.72,
            "status": "approved",
            "fiscal_year": 2026,
        }
    )
    assert row["used_pct"] == 52.44
