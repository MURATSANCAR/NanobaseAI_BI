"""2026-09-21: "Bu yılki net ciromuz geçen yıla göre nasıl değişti?" — veri 17.08.2026'da bitiyor; takvim
yılıyla 8,5 ay 12 ayla kıyaslanıp artan ciro "düştü" çıkıyordu. Karşılaştırmanın iki tarafı ölçünün
kendi verisinin bittiği göreli günde biter (ürün sahibinin kuralı: aynı gün / aynı ay)."""

from datetime import date
from types import SimpleNamespace as NS

import pytest

from semantic_layer.models import TemporalSlot
from semantic_layer.runtime import same_period as sp
from semantic_layer.runtime.compiler import Dialect

TODAY = date(2026, 9, 21)


@pytest.mark.parametrize("cs,rs,re_,last,want", [
    (date(2026, 1, 1), date(2025, 1, 1), date(2026, 1, 1), date(2026, 8, 17), date(2025, 8, 18)),   # yıl
    (date(2028, 1, 1), date(2027, 1, 1), date(2028, 1, 1), date(2028, 2, 29), date(2027, 3, 1)),    # 29 Şub → 28 Şub
    (date(2025, 1, 1), date(2024, 1, 1), date(2025, 1, 1), date(2025, 2, 28), date(2024, 3, 1)),    # ay sonu → ay sonu
    (date(2026, 3, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 3, 31), date(2026, 3, 1)),    # 31 Mar → Şub sonu
    (date(2026, 3, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 3, 15), date(2026, 2, 16)),   # ay: aynı gün
    (date(2026, 7, 1), date(2026, 4, 1), date(2026, 7, 1), date(2026, 8, 17), date(2026, 5, 18)),   # çeyrek
    (date(2026, 9, 21), date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 23), date(2026, 9, 17)),  # hafta
])
def test_aligned_end(cs, rs, re_, last, want):
    assert sp.aligned_end(cs, rs, re_, last) == want


def _sq(periods, comparison=True):
    temporal = [TemporalSlot(t, p, s, e, "YEAR") for t, p, s, e in periods]
    metric = NS(mapping=NS(entity="STLINE", extra={"conditions": ["STLINE.CANCELLED = (0)", "STLINE.TRCODE IN (7,8,9)"]}))
    comp = None
    if comparison:
        comp = {"kind": "PERIOD", "current": temporal[0].to_dict(), "reference": temporal[1].to_dict(),
                "entity": "STLINE", "dateColumn": "DATE_", "alignment": "CALENDAR_PERIODS", "coverageComparable": False}
    return NS(question="q", metrics=[metric], temporal=temporal, comparison=comp,
              temporal_binding={"entity": "STLINE", "column": "DATE_"},
              explanation=["Karşılaştırmada takvim dönemleri kullanıldı; dönemlerin eşit veri kapsamına sahip olduğu doğrulanmadı."])


YEARS = [("bu yıl", "THIS_YEAR", date(2026, 1, 1), date(2027, 1, 1)),
         ("geçen yıl", "LAST_YEAR", date(2025, 1, 1), date(2026, 1, 1))]


def test_comparison_is_cut_where_the_measure_data_ends():
    sq = _sq(YEARS)
    plan = sp.probe_plan(sq, TODAY, Dialect("tsql"))
    # the measure's own conditions, the current period only, never past today
    assert "STLINE.[TRCODE] IN (7, 8, 9)" in plan["sql"] and "< '2026-09-22'" in plan["sql"]
    assert plan["period"] == (date(2026, 1, 1), date(2026, 9, 22))
    ok, last = sp.last_day_of({"records": [{"last_0": "2026-08-17T00:00:00"}]})
    assert ok and last == date(2026, 8, 17)
    assert sp.apply(sq, plan, last)
    assert [(t.start, t.end) for t in sq.temporal] == [(date(2026, 1, 1), date(2026, 8, 18)), (date(2025, 1, 1), date(2025, 8, 18))]
    assert sq.comparison["current"]["end"] == "2026-08-18" and sq.comparison["reference"]["end"] == "2025-08-18"
    assert sq.comparison["alignment"] == "SAME_ELAPSED"
    assert not any(e.startswith("Karşılaştırmada takvim") for e in sq.explanation)
    assert any("eş dönem" in e for e in sq.explanation)


def test_earliest_measure_end_wins():
    ok, last = sp.last_day_of({"records": [{"last_0": "2026-08-17", "last_1": "2026-09-21"}]})
    assert ok and last == date(2026, 8, 17)


def test_closed_period_is_left_alone():
    sq = _sq([("2025", "YEAR", date(2025, 1, 1), date(2026, 1, 1)), ("2024", "YEAR", date(2024, 1, 1), date(2025, 1, 1))])
    assert sp.probe_plan(sq, TODAY, Dialect("tsql")) is None


def test_no_rows_in_current_period_keeps_calendar_and_says_so():
    sq = _sq(YEARS)
    plan = sp.probe_plan(sq, TODAY, Dialect("tsql"))
    assert not sp.apply(sq, plan, None)
    assert sq.temporal[0].end == date(2027, 1, 1)
    assert any(e.startswith("Karşılaştırmada takvim") for e in sq.explanation)
    assert any("kaydı yok" in e for e in sq.explanation)


def test_unreadable_probe_changes_nothing():
    assert sp.last_day_of({"records": []}) == (False, None)
    assert sp.last_day_of({"records": [{"last_0": "not a date"}]}) == (False, None)


def test_single_open_period_gets_a_coverage_note_only():
    sq = _sq(YEARS[:1], comparison=False)
    plan = sp.probe_plan(sq, TODAY, Dialect("tsql"))
    assert plan["kind"] == "single"
    assert not sp.apply(sq, plan, date(2026, 8, 17))
    assert sq.temporal[0].end == date(2027, 1, 1)
    assert any(e.startswith("Veri kapsamı:") and "17.08.2026" in e for e in sq.explanation)
