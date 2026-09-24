"""Boş cevap, dönem veriden sonra kaldığı için boşsa: tarih söylenir, aynı soru o döneme kurulup önerilir.

Öneri kalıp değildir: sorudaki dönem ifadesi, verinin son gününü içeren aynı türden dönemle yer değiştirir
ve kurulan soru ayrıştırıcıdan geri geçmek zorundadır.
"""
from __future__ import annotations

from datetime import date

import pytest

from semantic_layer.runtime.same_period import empty_hint, rephrase
from semantic_layer.runtime.temporal import parse_temporal

TODAY = date(2026, 9, 24)          # perşembe
LAST = date(2026, 8, 17)           # .155 kopyasının son faturası (pazartesi)


def _hint(q, last=LAST):
    (slot,) = parse_temporal(q, TODAY)[0]
    return empty_hint(q, slot, last, TODAY)


def _period(q):
    (slot,) = parse_temporal(q, TODAY)[0]
    return slot.primitive, slot.start, slot.end


# --- ayrıştırıcı: tek gün ve "önceki gün" -------------------------------------------------------------

def test_one_named_day_is_that_day_not_the_month():
    assert _period("17 ağustos 2026 en çok satan kitap") == ("DATE", date(2026, 8, 17), date(2026, 8, 18))
    assert _period("17.08.2026 en çok satan kitap") == ("DATE", date(2026, 8, 17), date(2026, 8, 18))
    assert _period("17/08/2026 ciro") == ("DATE", date(2026, 8, 17), date(2026, 8, 18))
    assert _period("3 mart'ta kaç fatura kesildi") == ("DATE", date(2026, 3, 3), date(2026, 3, 4))


def test_a_count_before_a_month_is_not_a_day():
    assert _period("10 ocak ayında ciro")[0] == "MONTH"


def test_forms_that_already_worked_are_unchanged():
    assert _period("31 ağustosa kadar ciro") == ("YEAR_TO_DAY", date(2026, 1, 1), date(2026, 9, 1))
    assert _period("Temmuz 2026 da en cok satan kitaplar") == ("MONTH", date(2026, 7, 1), date(2026, 8, 1))
    assert _period("1 Ocak 2025 ile 31 Aralik 2026 arasindaki ciro") == ("RANGE", date(2025, 1, 1), date(2027, 1, 1))


def test_a_span_between_two_days_is_those_days():
    """Önceden "15 ocak ile 20 mart arası" iki ay olarak okunuyor, 1 Ocak–31 Mart çıkıyordu."""
    assert _period("15 ocak 2025 ile 20 mart 2025 arası ciro") == ("RANGE", date(2025, 1, 15), date(2025, 3, 21))


@pytest.mark.parametrize("q,expected", [
    ("dün ciro", ("YESTERDAY", date(2026, 9, 23), date(2026, 9, 24))),
    ("bir önceki gün ciro", ("YESTERDAY", date(2026, 9, 23), date(2026, 9, 24))),
    ("önceki gün ciro", ("DAY_BEFORE_YESTERDAY", date(2026, 9, 22), date(2026, 9, 23))),
    ("evvelsi gün ciro", ("DAY_BEFORE_YESTERDAY", date(2026, 9, 22), date(2026, 9, 23))),
    ("bir önceki hafta ciro", ("LAST_WEEK", date(2026, 9, 14), date(2026, 9, 21))),
])
def test_previous_day_and_week_wordings(q, expected):
    assert _period(q) == expected


# --- boş cevap açıklaması ve öneri ----------------------------------------------------------------------

@pytest.mark.parametrize("q,last,asked,start,end", [
    # gün türü → verinin son günü
    ("bugün en çok satan kitap", LAST, "17 ağustos 2026 en çok satan kitap", date(2026, 8, 17), date(2026, 8, 18)),
    ("Bugün en çok satan kitap hangisi?", LAST, "17 ağustos 2026 en çok satan kitap hangisi?", date(2026, 8, 17), date(2026, 8, 18)),
    ("dün kaç fatura kesildi", LAST, "17 ağustos 2026 kaç fatura kesildi", date(2026, 8, 17), date(2026, 8, 18)),
    ("bir önceki gün ciro", LAST, "17 ağustos 2026 ciro", date(2026, 8, 17), date(2026, 8, 18)),
    ("önceki gün ciro", LAST, "17 ağustos 2026 ciro", date(2026, 8, 17), date(2026, 8, 18)),
    ("bugünün cirosu", LAST, "17 ağustos 2026 cirosu", date(2026, 8, 17), date(2026, 8, 18)),
    ("bugün'ün cirosu", LAST, "17 ağustos 2026 cirosu", date(2026, 8, 17), date(2026, 8, 18)),
    # hafta türü → son günü içeren hafta, son günde kesilir
    ("bu hafta en çok satan kitap", date(2026, 8, 20), "17 ağustos 2026 ile 20 ağustos 2026 arası en çok satan kitap",
     date(2026, 8, 17), date(2026, 8, 21)),
    ("geçen hafta ciro", date(2026, 8, 20), "17 ağustos 2026 ile 20 ağustos 2026 arası ciro", date(2026, 8, 17), date(2026, 8, 21)),
    ("geçen hafta ciro", date(2026, 8, 23), "17 ağustos 2026 ile 23 ağustos 2026 arası ciro", date(2026, 8, 17), date(2026, 8, 24)),
    # ay türü → ay son günde bitmediyse tarih aralığı, bittiyse ayın adı
    ("bu ay en çok satan kitap", LAST, "1 ağustos 2026 ile 17 ağustos 2026 arası en çok satan kitap",
     date(2026, 8, 1), date(2026, 8, 18)),
    ("geçen ay ciro", date(2026, 7, 31), "temmuz 2026 ciro", date(2026, 7, 1), date(2026, 8, 1)),
    # çeyrek ve yıl
    ("bu çeyrek ciro", date(2026, 6, 30), "2026 nisan-haziran ciro", date(2026, 4, 1), date(2026, 7, 1)),
    ("bu yıl en çok satan kitap", date(2025, 12, 31), "2025 en çok satan kitap", date(2025, 1, 1), date(2026, 1, 1)),
    ("geçen yıl ciro", date(2024, 12, 31), "2024 ciro", date(2024, 1, 1), date(2025, 1, 1)),
])
def test_the_same_question_is_rebuilt_for_the_last_period_of_the_same_kind(q, last, asked, start, end):
    h = _hint(q, last)
    assert h["lastDay"] == last.isoformat()
    assert f"veri {last.strftime('%d.%m.%Y')} tarihinde bitiyor" in h["note"]
    assert h["suggestion"] == {"question": asked, "start": start.isoformat(), "end": end.isoformat()}


def test_a_rolling_window_keeps_its_length_and_ends_on_the_last_day():
    (slot,) = parse_temporal("son 7 gün ciro", TODAY)[0]
    h = empty_hint("son 7 gün ciro", slot, LAST, TODAY)
    s = h["suggestion"]
    assert s["end"] == "2026-08-18"
    assert (date.fromisoformat(s["end"]) - date.fromisoformat(s["start"])) == (slot.end - slot.start)
    assert s["question"].endswith("arası ciro")


def test_note_quotes_the_words_the_person_used():
    assert "'Bugün' için kayıt yok" in _hint("Bugün en çok satan kitap")["note"]


def test_data_inside_the_period_means_the_empty_answer_is_real():
    """Ağustos'ta veri var; boşluk sorunun süzgecinden geliyor — o bir "yok"tur, öneri verilmez."""
    assert _hint("geçen ay ciro", LAST) is None


def test_no_data_at_all_says_so_without_a_suggestion():
    h = _hint("bugün ciro", None)
    assert h["lastDay"] is None and h["suggestion"] is None
    assert "kaydı yok" in h["note"]


def test_rephrase_leaves_the_rest_of_the_question_alone():
    assert rephrase("Yayınevlerine göre bugün net ciro", "bugun", "17 ağustos 2026") == \
        "Yayınevlerine göre 17 ağustos 2026 net ciro"
    assert rephrase("net ciro", "bugun", "17 ağustos 2026") is None
