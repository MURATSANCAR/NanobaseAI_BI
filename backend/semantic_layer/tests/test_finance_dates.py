"""Finans motoru dönem ayrıştırıcısı (2026-10-01 kullanıcı kuralı).

Yıl yazılmamışsa her ay, gün, hafta ve çeyrek güncel yıla / bugüne bağlanır; geçmiş yıl
yalnız yıl ya da göreli geçmiş (geçen yıl, bir önceki yıl …) yazılınca okunur.
Beklenen aralıklar yarı açıktır: [başlangıç, bitiş). Bugün 2026-10-01 perşembe.
"""
from datetime import date

import pytest

from semantic_bridge.finance_query.contracts import ContractError
from semantic_bridge.finance_query.language import dates

TODAY = date(2026, 10, 1)


def periods(question):
    return dates(question, TODAY)[0]


@pytest.mark.parametrize("question, expected", [
    # Gün ve ay aralıkları — 01.10 incelemesinde yanlış çözülüyordu.
    ("1 Ocak 2026 - 15 Mart 2026 net satış", (("2026-01-01", "2026-03-16"),)),
    ("1-15 Mart 2026 net satış", (("2026-03-01", "2026-03-16"),)),
    ("1-15 Mart net satış", (("2026-03-01", "2026-03-16"),)),
    ("1 Ocak - 15 Mart 2026 net satış", (("2026-01-01", "2026-03-16"),)),
    ("1 Ocak - 15 Mart arası net satış", (("2026-01-01", "2026-03-16"),)),
    ("1 Ocak'tan 15 Mart'a kadar net satış", (("2026-01-01", "2026-03-16"),)),
    ("01.01.2026 - 15.03.2026 net satış", (("2026-01-01", "2026-03-16"),)),
    ("Ocak-Mart 2026 net satış", (("2026-01-01", "2026-04-01"),)),
    ("Ocak-Mart net satış", (("2026-01-01", "2026-04-01"),)),
    ("Ocak'tan Mart'a kadar net satış", (("2026-01-01", "2026-04-01"),)),
    ("Ocak ile Mart arası net satış", (("2026-01-01", "2026-04-01"),)),
    # Yıla bağlı ilk N ay ve yarıyıl.
    ("2025'in ilk 3 ayı net satış", (("2025-01-01", "2025-04-01"),)),
    ("2025in ilk 3 ayı net satış", (("2025-01-01", "2025-04-01"),)),
    ("2025 yılının ilk 6 ayı net satış", (("2025-01-01", "2025-07-01"),)),
    ("geçen yılın ilk 8 ayı net satış", (("2025-01-01", "2025-09-01"),)),
    ("bu yılın ilk 8 ayı net satış", (("2026-01-01", "2026-09-01"),)),
    ("2026 ilk yarısı net satış", (("2026-01-01", "2026-07-01"),)),
    ("geçen yılın ikinci yarısı net satış", (("2025-07-01", "2026-01-01"),)),
    ("ilk yarıyıl net satış", (("2026-01-01", "2026-07-01"),)),
    # Yılsız ay ve gün: her zaman güncel yıl, ay henüz gelmemiş olsa bile.
    ("kasım ayı net satış", (("2026-11-01", "2026-12-01"),)),
    ("eylül ayında net satış", (("2026-09-01", "2026-10-01"),)),
    ("5 Mart'taki faturalar", (("2026-03-05", "2026-03-06"),)),
    ("Aralık ayı satışları", (("2026-12-01", "2027-01-01"),)),
    ("Aralık'ta kesilen faturalar", (("2026-12-01", "2027-01-01"),)),
    # Göreli dönemler bugüne göre.
    ("geçen ay net satış", (("2026-09-01", "2026-10-01"),)),
    ("bir önceki ay net satış", (("2026-09-01", "2026-10-01"),)),
    ("dün kesilen faturalar", (("2026-09-30", "2026-10-01"),)),
    ("geçen gün kesilen faturalar", (("2026-09-30", "2026-10-01"),)),
    ("önceki çeyrek net satış", (("2026-07-01", "2026-10-01"),)),
    ("bu hafta net satış", (("2026-09-28", "2026-10-05"),)),
    ("geçen hafta net satış", (("2026-09-21", "2026-09-28"),)),
    ("geçen sene net satış", (("2025-01-01", "2026-01-01"),)),
    ("bir önceki yıl net satış", (("2025-01-01", "2026-01-01"),)),
    ("geçen sene ve bu sene net satış", (("2025-01-01", "2026-01-01"), ("2026-01-01", "2027-01-01"))),
    ("geçen yıl net satış", (("2025-01-01", "2026-01-01"),)),
    ("2025 yılı net satış", (("2025-01-01", "2026-01-01"),)),
    ("son 3 ay net satış", (("2026-07-01", "2026-10-02"),)),
    # '... den beri'
    ("Eylül'den beri net satış", (("2026-09-01", "2026-10-02"),)),
    ("2021'den bugüne net satış", (("2021-01-01", "2026-10-02"),)),
    # "aralık" sözcüğü ay değilse Aralık ayı eklenmez.
    ("bu yılın ilk 3 ayı ile geçen yıl aynı aralık net satış", (("2026-01-01", "2026-04-01"), ("2025-01-01", "2025-04-01"))),
    ("bu yılın ilk 3 ayı ile geçen senenin aynı dönemi net satış", (("2026-01-01", "2026-04-01"), ("2025-01-01", "2025-04-01"))),
    ("hangi aralıkta en çok satış yaptık", ()),
    # Dönem yazılmamış: ayrıştırıcı uydurmaz (varsayılan planlayıcıda ve not ile).
    ("net ciro ne kadar", ()),
])
def test_periods(question, expected):
    assert periods(question) == expected


def test_two_dates_with_ile_are_not_a_range():
    # "ile" yalnız "arası" ile aralık kurar; aksi halde iki ayrı gün karşılaştırılıyor.
    assert periods("1 Ocak 2026 ile 15 Mart 2026 satışlarını karşılaştır") == (
        ("2026-01-01", "2026-01-02"), ("2026-03-15", "2026-03-16"))


def test_month_range_crossing_year_asks():
    with pytest.raises(ContractError) as err:
        periods("Ekim-Mart net satış")
    assert err.value.code == "NEEDS_CLARIFICATION"


def test_since_future_month_asks():
    with pytest.raises(ContractError) as err:
        periods("Kasım'dan beri net satış")
    assert err.value.code == "NEEDS_CLARIFICATION"


def test_no_year_never_reaches_past_copies():
    # Yıl ya da göreli geçmiş yazılmamış hiçbir ifade 2026 öncesine gitmemeli.
    for question in ("kasım ayı", "5 Mart", "1-15 Mart", "Ocak-Mart", "ilk yarı", "ilk 3 ay",
                     "geçen ay", "dün", "önceki çeyrek", "geçen hafta", "bu yıl", "Aralık ayı"):
        for start, _ in periods(question + " net satış"):
            assert start >= "2026-01-01", (question, start)
