""""(bir) önceki X", soruda aynı türden başka bir dönem varsa o dönemden önceki X'tir — bugünden önceki değil."""
from __future__ import annotations

from datetime import date

import pytest

from semantic_layer.runtime.temporal import parse_temporal

TODAY = date(2026, 9, 24)          # perşembe


def _spans(q):
    return [(s.start, s.end) for s in parse_temporal(q, TODAY)[0]]


@pytest.mark.parametrize("q,expected", [
    # önceden iki taraf da 14–21 Eylül'dü: hafta kendisiyle karşılaştırılıyordu
    ("Geçen haftaki tahsilat toplamı bir önceki haftaya göre nasıl?",
     [(date(2026, 9, 14), date(2026, 9, 21)), (date(2026, 9, 7), date(2026, 9, 14))]),
    ("geçen hafta ciro önceki haftaya göre",
     [(date(2026, 9, 14), date(2026, 9, 21)), (date(2026, 9, 7), date(2026, 9, 14))]),
    ("dünkü satış bir önceki güne göre",
     [(date(2026, 9, 23), date(2026, 9, 24)), (date(2026, 9, 22), date(2026, 9, 23))]),
    ("geçen ay ciro bir önceki aya göre",
     [(date(2026, 8, 1), date(2026, 9, 1)), (date(2026, 7, 1), date(2026, 8, 1))]),
    ("geçen yıl ciro bir önceki yıla göre",
     [(date(2025, 1, 1), date(2026, 1, 1)), (date(2024, 1, 1), date(2025, 1, 1))]),
    ("2024 ciro bir önceki yıla göre",
     [(date(2024, 1, 1), date(2025, 1, 1)), (date(2023, 1, 1), date(2024, 1, 1))]),
    ("temmuz 2026 ciro önceki aya göre",
     [(date(2026, 7, 1), date(2026, 8, 1)), (date(2026, 6, 1), date(2026, 7, 1))]),
    ("geçen çeyrek ciro bir önceki çeyreğe göre",
     [(date(2026, 4, 1), date(2026, 7, 1)), (date(2026, 1, 1), date(2026, 4, 1))]),
    ("ocak 2026 ciro önceki aya göre",
     [(date(2026, 1, 1), date(2026, 2, 1)), (date(2025, 12, 1), date(2026, 1, 1))]),
])
def test_previous_is_counted_back_from_the_other_period(q, expected):
    assert _spans(q) == expected


@pytest.mark.parametrize("q,expected", [
    # bugüne göre okununca da doğru olanlar değişmez
    ("bu ay ciro önceki aya göre", [(date(2026, 9, 1), date(2026, 10, 1)), (date(2026, 8, 1), date(2026, 9, 1))]),
    ("bu hafta satış geçen haftaya göre", [(date(2026, 9, 21), date(2026, 9, 28)), (date(2026, 9, 14), date(2026, 9, 21))]),
    # tek dönem: bugüne göre
    ("bir önceki hafta ciro", [(date(2026, 9, 14), date(2026, 9, 21))]),
    # ikisi de bugüne bağlı ("geçen"): dokunulmaz
    ("geçen yıl ve geçen ay ciro", [(date(2025, 1, 1), date(2026, 1, 1)), (date(2026, 8, 1), date(2026, 9, 1))]),
])
def test_what_was_already_right_stays(q, expected):
    assert _spans(q) == expected


def test_different_grains_are_not_re_anchored():
    """"bu ay önceki yıla göre": aydan geriye yıl sayılmaz; bugüne göre okunur."""
    assert _spans("bu ay ciro önceki yıla göre") == [(date(2026, 9, 1), date(2026, 10, 1)), (date(2025, 1, 1), date(2026, 1, 1))]
