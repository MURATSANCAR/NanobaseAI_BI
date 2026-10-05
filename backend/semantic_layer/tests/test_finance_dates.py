"""Finans motoru dönem ayrıştırıcısı (2026-10-01 kullanıcı kuralı).

Yıl yazılmamışsa her ay, gün, hafta ve çeyrek güncel yıla / bugüne bağlanır; geçmiş yıl
yalnız yıl ya da göreli geçmiş (geçen yıl, bir önceki yıl …) yazılınca okunur.
Beklenen aralıklar yarı açıktır: [başlangıç, bitiş). Bugün 2026-10-01 perşembe.
"""
import json
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


# 2026-10-01 canlı kabul FC54/FC66: denetçi «Aralık 2026» aralığını (henüz gelmemiş ay) yanlış sanıp
# doğru planı reddetti. Dönemi model seçmez; sorudaki ifadeden kurallı çözüldüyse denetçiye söylenir.
class _ReviewSpy:
    def __init__(self):
        self.review = None

    def complete(self, messages, **kw):
        import json as _json
        name = kw["body"]["response_format"]["json_schema"]["name"]
        if name == "finance_review":
            self.review = _json.loads(messages[-1]["content"])
            content = '{"ok": true, "missing": []}'
        else:
            raise AssertionError(name)
        return {"message": {"content": content}, "finish_reason": "stop"}


def _plan_data(**extra):
    data = {"metrics": ["net_sales"], "dimensions": [], "sale_kind": "all", "filters": [], "limit": None,
            "order_by": None, "descending": True, "derived": [], "having": [], "comparison": None, "crm": None,
            "logo_report": None, "crm_report": None, "relational_query": None, "analytics": [], "sections": [],
            "gaps": [], "coverage": [], "uncovered": [], "clarification": ""}
    data.update(extra)
    return data


def test_reviewer_is_told_a_written_future_month_was_parsed_by_rule():
    from semantic_bridge.finance_query.planner import build
    spy = _ReviewSpy()
    plan = build("Aralık 2026 net satış tutarı nedir?", spy, _data=_plan_data())
    assert plan.periods == (("2026-12-01", "2027-01-01"),)
    assert spy.review["plan"]["tarih_kaynağı"] == "sorudaki_ifadeden_kurallı_çözüm"
    # No concrete range to re-judge (the reviewer rewrote December as November/January).
    assert isinstance(spy.review["plan"]["uygulanan_tarih_aralıkları"], str)
    assert "2026-12" not in json.dumps(spy.review["plan"]["uygulanan_tarih_aralıkları"])


def test_default_period_is_not_marked_as_parsed_from_the_question():
    from semantic_bridge.finance_query.planner import build
    spy = _ReviewSpy()
    build("Net satış tutarı nedir?", spy, _data=_plan_data())
    assert spy.review["plan"]["tarih_kaynağı"] is None
    assert isinstance(spy.review["plan"]["uygulanan_tarih_aralıkları"], list)


def test_an_ongoing_period_says_how_far_its_data_reaches():
    from datetime import date
    from semantic_bridge.finance_query.planner import build
    plan = build("Ekim 2026 net satış tutarı nedir?", _ReviewSpy(), _data=_plan_data())
    today = date.today()
    if date(2026, 10, 1) <= today < date(2026, 10, 31):
        assert any(n.startswith("Dönem sürüyor: 01.10.2026") for n in plan.notes)
    else:
        assert not any(n.startswith("Dönem sürüyor") for n in plan.notes)


def test_comparing_a_finished_month_with_the_running_one_uses_the_same_days():
    from datetime import date
    from semantic_bridge.finance_query.plan_types import PeriodComparison
    from semantic_bridge.finance_query.planner import align_ongoing_comparison
    cmp = PeriodComparison("percent_change", "net_sales", "x", 0, 1)
    periods, note = align_ongoing_comparison((("2026-09-01", "2026-10-01"), ("2026-10-01", "2026-11-01")), cmp, date(2026, 10, 5))
    assert periods == (("2026-09-01", "2026-09-06"), ("2026-10-01", "2026-10-06"))
    assert "01.09.2026–05.09.2026 ile 01.10.2026–05.10.2026 (5 gün)" in note
    # Two finished periods, or a period that has not started, are left as asked.
    assert align_ongoing_comparison((("2025-09-01", "2025-10-01"), ("2026-09-01", "2026-10-01")), cmp, date(2026, 10, 5)) == (
        (("2025-09-01", "2025-10-01"), ("2026-09-01", "2026-10-01")), None)
    # A year against the running year: same number of days into each.
    periods, _ = align_ongoing_comparison((("2025-01-01", "2026-01-01"), ("2026-01-01", "2027-01-01")), cmp, date(2026, 10, 5))
    assert periods == (("2025-01-01", "2025-10-06"), ("2026-01-01", "2026-10-06"))



@pytest.mark.parametrize("q", ["geçen yıl eylülle bu yıl eylülü karşılaştır satış olarak",
                               "bu yıl eylülü geçen yıl eylülüyle kıyasla", "geçen sene eylülde ve bu sene eylülde satış"])
def test_a_relative_year_with_any_suffix_on_the_month_is_that_month(q):
    from datetime import date
    from semantic_bridge.finance_query.language import dates
    periods, _ = dates(q, date(2026, 10, 5))
    assert sorted(periods) == [("2025-09-01", "2025-10-01"), ("2026-09-01", "2026-10-01")]


def test_a_source_value_matches_the_question_across_spaces_and_suffixes():
    from semantic_bridge.finance_query.language import fold
    from semantic_bridge.finance_query.planner import _in_question
    q = fold("yurt dışına ne kadar sattık bu sene")
    assert _in_question("YURTDIŞI", q) and _in_question("yurt dışı", q) and not _in_question("KITAPCI", q)
