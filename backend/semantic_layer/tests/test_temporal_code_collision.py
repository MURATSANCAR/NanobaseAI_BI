import pytest
from semantic_layer.history.question_facts import extract_question_facts


@pytest.mark.parametrize("month", "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split())
def test_month_year_is_not_a_column_value_pair(month):
    q=extract_question_facts(f"{month} 2026 net ciro")
    assert q.temporal
    assert not q.explicit_codes


def test_explicit_assignment_keeps_column_intent():
    assert ("MART",("2026",)) in extract_question_facts("MART=2026 net ciro").explicit_codes
    assert ("TRCODE",("8",)) in extract_question_facts("Mart 2026 TRCODE 8 net ciro").explicit_codes


def test_same_column_elsewhere_does_not_get_removed():
    q=extract_question_facts("Mart 2026 MART=3 net ciro")
    assert q.explicit_codes==[("MART",("3",))]
