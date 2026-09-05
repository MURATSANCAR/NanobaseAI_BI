"""SeriesBundleBuilder property + edge-case tests (plan Faz 2.3)."""

from __future__ import annotations

import random
from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from forecasting.contracts import SeriesBundleError, build_series_bundle
from forecasting.contracts.builder import future_periods, next_period, period_start


def _months(n: int, start: date = date(2023, 1, 1)) -> list[date]:
    return [next_period(start, "M", i) for i in range(n)]


def _rows(n: int = 36, seed: int = 1) -> list[tuple[date, float]]:
    rnd = random.Random(seed)
    return [(d, 1000.0 + i * 10 + rnd.random() * 50) for i, d in enumerate(_months(n))]


def test_happy_path_hash_and_shape():
    b = build_series_bundle(_rows(), metric="total_revenue", frequency="M", horizon=6, dimension={"branch_city": "İstanbul"})
    assert b.series_id == "total_revenue|branch_city=İstanbul"
    assert len(b.history) == 36
    assert b.history[0].timestamp == date(2023, 1, 1)
    assert b.history[-1].timestamp == date(2025, 12, 1)
    assert b.bundle_hash.startswith("sha256:")
    assert b.filled_periods == []
    assert not [w for w in b.warnings if w.startswith("short_history")]


def test_order_independence_same_hash():
    rows = _rows()
    a = build_series_bundle(rows, metric="m", frequency="M", horizon=3)
    b = build_series_bundle(list(reversed(rows)), metric="m", frequency="M", horizon=3)
    assert a.bundle_hash == b.bundle_hash
    assert [p.value for p in a.history] == [p.value for p in b.history]


def test_idempotent_rebuild_from_own_history():
    a = build_series_bundle(_rows(), metric="m", frequency="M", horizon=3)
    b = build_series_bundle([(p.timestamp, p.value) for p in a.history], metric="m", frequency="M", horizon=3)
    assert a.bundle_hash == b.bundle_hash


def test_dict_rows_with_period_key():
    rows = [{"period": d.isoformat(), "total_revenue": v} for d, v in _rows(24)]
    b = build_series_bundle(rows, metric="total_revenue", frequency="M", horizon=4)
    assert len(b.history) == 24


def test_mid_month_timestamps_normalized_to_period_start():
    rows = [(d.replace(day=15), v) for d, v in _rows(24)]
    b = build_series_bundle(rows, metric="m", frequency="M", horizon=2)
    assert all(p.timestamp.day == 1 for p in b.history)
    assert any(w.startswith("timestamp_normalized") for w in b.warnings)


def test_duplicate_period_rejected():
    rows = _rows(24) + [(date(2023, 3, 20), 5.0)]
    with pytest.raises(SeriesBundleError) as e:
        build_series_bundle(rows, metric="m", frequency="M", horizon=2)
    assert e.value.code == "DUPLICATE_TIMESTAMPS"


def test_gap_zero_fill_records_filled_periods():
    rows = [r for r in _rows(24) if r[0] != date(2023, 6, 1)]
    b = build_series_bundle(rows, metric="m", frequency="M", horizon=2, missing_policy="zero")
    assert b.filled_periods == [date(2023, 6, 1)]
    assert [p for p in b.history if p.timestamp == date(2023, 6, 1)][0].value == 0.0
    assert "filled_periods:1:zero" in b.warnings


def test_gap_interpolate():
    rows = [(d, float(i)) for i, d in enumerate(_months(24)) if i != 5]
    b = build_series_bundle(rows, metric="m", frequency="M", horizon=2, missing_policy="interpolate")
    assert b.history[5].value == pytest.approx(5.0)


def test_gap_reject():
    rows = [r for r in _rows(24) if r[0] != date(2023, 6, 1)]
    with pytest.raises(SeriesBundleError) as e:
        build_series_bundle(rows, metric="m", frequency="M", horizon=2, missing_policy="reject")
    assert e.value.code == "GAPS_EXCEED_POLICY"


def test_insufficient_history_hard_min():
    with pytest.raises(SeriesBundleError) as e:
        build_series_bundle(_rows(11), metric="m", frequency="M", horizon=1)
    assert e.value.code == "INSUFFICIENT_HISTORY"
    assert e.value.details["points"] == 11


def test_short_history_warns_below_recommended():
    b = build_series_bundle(_rows(18), metric="m", frequency="M", horizon=3)
    assert any(w.startswith("short_history:18") for w in b.warnings)


def test_horizon_cap_len_over_3():
    with pytest.raises(SeriesBundleError) as e:
        build_series_bundle(_rows(15), metric="m", frequency="M", horizon=6)  # cap = 5
    assert e.value.code == "HORIZON_TOO_LONG"
    assert e.value.details["max_horizon"] == 5


def test_horizon_cap_absolute_12():
    with pytest.raises(SeriesBundleError) as e:
        build_series_bundle(_rows(60), metric="m", frequency="M", horizon=13)
    assert e.value.code == "HORIZON_TOO_LONG"


def test_negative_rejected_for_non_negative_metric():
    rows = _rows(24)
    rows[3] = (rows[3][0], -1.0)
    with pytest.raises(SeriesBundleError) as e:
        build_series_bundle(rows, metric="total_revenue", frequency="M", horizon=2)
    assert e.value.code == "NEGATIVE_VALUE_FOR_METRIC"
    b = build_series_bundle(rows, metric="net_change", frequency="M", horizon=2, non_negative=False)
    assert b.history[3].value == -1.0


def test_history_cap_keeps_latest():
    b = build_series_bundle(_rows(150), metric="m", frequency="M", horizon=6)
    assert len(b.history) == 120
    assert b.history[-1].timestamp == _months(150)[-1]


def test_empty_rows():
    with pytest.raises(SeriesBundleError) as e:
        build_series_bundle([], metric="m", frequency="M", horizon=1)
    assert e.value.code == "INSUFFICIENT_HISTORY"


def test_bad_frequency_and_policy():
    with pytest.raises(SeriesBundleError):
        build_series_bundle(_rows(), metric="m", frequency="H", horizon=1)
    with pytest.raises(SeriesBundleError):
        build_series_bundle(_rows(), metric="m", frequency="M", horizon=1, missing_policy="guess")


@pytest.mark.parametrize(
    "freq,d,expected",
    [
        ("M", date(2026, 9, 17), date(2026, 9, 1)),
        ("Q", date(2026, 8, 3), date(2026, 7, 1)),
        ("Y", date(2026, 8, 3), date(2026, 1, 1)),
        ("W", date(2026, 9, 6), date(2026, 8, 31)),  # Sunday → Monday
        ("D", date(2026, 9, 6), date(2026, 9, 6)),
    ],
)
def test_period_start(freq, d, expected):
    assert period_start(d, freq) == expected


def test_future_periods_month_rollover():
    assert future_periods(date(2026, 8, 1), "M", 6) == [
        date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1)
    ]


@settings(max_examples=60, deadline=None)
@given(
    n=st.integers(min_value=12, max_value=80),
    values=st.lists(st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False), min_size=80, max_size=80),
    seed=st.integers(min_value=0, max_value=10_000),
)
def test_property_hash_stable_under_shuffle_and_rebuild(n, values, seed):
    rows = list(zip(_months(n), values[:n]))
    shuffled = rows[:]
    random.Random(seed).shuffle(shuffled)
    a = build_series_bundle(rows, metric="m", frequency="M", horizon=1)
    b = build_series_bundle(shuffled, metric="m", frequency="M", horizon=1)
    c = build_series_bundle([(p.timestamp, p.value) for p in a.history], metric="m", frequency="M", horizon=1)
    assert a.bundle_hash == b.bundle_hash == c.bundle_hash
    assert len(a.history) == n
    assert [p.timestamp for p in a.history] == sorted(p.timestamp for p in a.history)
