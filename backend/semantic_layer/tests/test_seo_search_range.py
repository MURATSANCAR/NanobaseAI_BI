"""ZEKI-50: «Aranan kelimeler ve sayfalar» tarih aralığı. Yalnız saf kurallar ve önbellek; ağ ve veritabanı yok."""
from datetime import date

import pytest

from semantic_bridge.seo_geo import search_range as R

TODAY = date(2026, 9, 29)


def test_bounds_follow_google_lag_and_retention():
    assert R.latest_final(TODAY) == date(2026, 9, 26)
    assert R.earliest_kept(TODAY) == date(2025, 5, 30)
    assert R.months_back(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert R.months_back(date(2028, 3, 31), 1) == date(2028, 2, 29)


def test_resolve_keeps_a_valid_range_as_is():
    w = R.resolve("2026-08-01", "2026-08-31", TODAY)
    assert (w.start, w.end, w.days, w.notes) == (date(2026, 8, 1), date(2026, 8, 31), 31, [])


def test_resolve_clamps_unfinal_end_and_says_why():
    w = R.resolve("2026-09-20", "2026-09-29", TODAY)
    assert w.end == date(2026, 9, 26)
    assert len(w.notes) == 1 and "kesinleşmediği" in w.notes[0]


def test_resolve_clamps_start_older_than_retention_and_says_why():
    w = R.resolve("2024-01-01", "2025-07-01", TODAY)
    assert w.start == R.earliest_kept(TODAY)
    assert "16 aydan eski" in w.notes[0]


@pytest.mark.parametrize("start,end,needle", [
    ("2026-09-27", "2026-09-29", "henüz kesinleşmedi"),
    ("2023-01-01", "2023-12-31", "16 aydan eski"),
    ("2026-09-10", "2026-09-01", "bitişten sonra"),
    ("2026-9-1", "2026-09-10", "YYYY-AA-GG"),
    ("2026-09-01", None, "birlikte"),
])
def test_resolve_rejects_impossible_ranges_with_a_reason(start, end, needle):
    with pytest.raises(R.RangeError) as e:
        R.resolve(start, end, TODAY)
    assert needle in str(e.value)


def test_previous_period_and_same_days_last_year():
    w = R.Window(date(2026, 8, 30), date(2026, 9, 26))
    p = R.previous(w, "onceki")
    assert (p.start, p.end, p.days) == (date(2026, 8, 2), date(2026, 8, 29), 28)
    y = R.previous(w, "gecen_yil")
    assert (y.start, y.end) == (date(2025, 8, 30), date(2025, 9, 26))
    with pytest.raises(R.RangeError):
        R.previous(w, "yarin")


def test_range_cache_reuses_rows_and_never_trims_them():
    calls = []
    rows = [{"keys": [f"q{i}"], "clicks": i} for i in range(30_000)]

    def fetch():
        calls.append(1)
        return rows

    c = R.RangeCache(ttl=60, slots=2)
    t = [1000.0]
    a, _ = c.get(("t", "queries", "2026-08-01", "2026-08-31"), fetch, clock=lambda: t[0])
    b, _ = c.get(("t", "queries", "2026-08-01", "2026-08-31"), fetch, clock=lambda: t[0])
    assert len(a) == len(b) == 30_000 and len(calls) == 1
    t[0] += 61
    c.get(("t", "queries", "2026-08-01", "2026-08-31"), fetch, clock=lambda: t[0])
    assert len(calls) == 2


def test_range_cache_does_not_store_failures():
    c = R.RangeCache()

    def boom():
        raise RuntimeError("Google 503")

    with pytest.raises(RuntimeError):
        c.get(("t", "pages", "2026-08-01", "2026-08-31"), boom)
    assert c._data == {}
