""""Geçen yılın aynı dönemi": yanındaki dönemin bir yıl (ay, çeyrek, hafta) öncesi — bütün geçen yıl değil."""
from __future__ import annotations

from datetime import date

import pytest

from semantic_layer.runtime.temporal import parse_temporal

TODAY = date(2026, 9, 24)


def _spans(q):
    return [(s.start, s.end) for s in parse_temporal(q, TODAY)[0]]


@pytest.mark.parametrize("q,expected", [
    # önceden referans bütün 2025'ti
    ("Aralık 2025 ile Ocak 2026 arası net ciro geçen yılın aynı dönemine göre",
     [(date(2025, 12, 1), date(2026, 2, 1)), (date(2024, 12, 1), date(2025, 2, 1))]),
    ("temmuz 2026 ciro geçen yılın aynı ayına göre",
     [(date(2026, 7, 1), date(2026, 8, 1)), (date(2025, 7, 1), date(2025, 8, 1))]),
    ("temmuz 2026 ciro bir önceki yılın aynı ayına göre",
     [(date(2026, 7, 1), date(2026, 8, 1)), (date(2025, 7, 1), date(2025, 8, 1))]),
    ("1 ağustos 2026 ile 17 ağustos 2026 arası satış geçen yılın aynı dönemine göre",
     [(date(2026, 8, 1), date(2026, 8, 18)), (date(2025, 8, 1), date(2025, 8, 18))]),
    ("bu ay ciro geçen yılın aynı dönemiyle karşılaştır",
     [(date(2026, 9, 1), date(2026, 10, 1)), (date(2025, 9, 1), date(2025, 10, 1))]),
    ("bu hafta satış geçen ayın aynı dönemine göre",
     [(date(2026, 9, 21), date(2026, 9, 28)), (date(2026, 8, 21), date(2026, 8, 28))]),
    ("bu çeyrek ciro geçen yılın aynı dönemine göre",
     [(date(2026, 7, 1), date(2026, 10, 1)), (date(2025, 7, 1), date(2025, 10, 1))]),
    ("17 ağustos 2026 satış geçen haftanın aynı gününe göre",
     [(date(2026, 8, 17), date(2026, 8, 18)), (date(2026, 8, 10), date(2026, 8, 11))]),
])
def test_same_period_is_the_other_period_moved_back(q, expected):
    assert _spans(q) == expected


def test_month_end_is_clamped():
    """29 Şubat 2028'in bir yıl öncesi 28 Şubat 2027."""
    assert _spans("29 şubat 2028 satış geçen yılın aynı gününe göre") == [
        (date(2028, 2, 29), date(2028, 3, 1)), (date(2027, 2, 28), date(2027, 3, 1))]


@pytest.mark.parametrize("q,expected", [
    # "aynı" yoksa takvim okuması kalır
    ("Aralık 2025 ile Ocak 2026 arası net ciro geçen yıla göre",
     [(date(2025, 12, 1), date(2026, 2, 1)), (date(2025, 1, 1), date(2026, 1, 1))]),
    # yanında dönem yok: dokunulmaz, karşılaştırma adımı karar verir
    ("net ciro geçen yılın aynı dönemine göre", [(date(2025, 1, 1), date(2026, 1, 1))]),
])
def test_without_the_phrase_or_an_anchor_nothing_moves(q, expected):
    assert _spans(q) == expected


def test_the_phrase_is_one_span():
    """"aynı dönemine" dönem ifadesinin parçası: başka bir okuma onu ayrı kelime sanmasın."""
    slots = parse_temporal("temmuz 2026 ciro geçen yılın aynı ayına göre", TODAY)[0]
    assert slots[1].text == "gecen yilin ayni ayina"
