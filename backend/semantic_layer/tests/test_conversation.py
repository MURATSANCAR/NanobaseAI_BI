from datetime import date
from semantic_layer.models import SemanticQuery, TemporalSlot
from semantic_layer.runtime.conversation import compose_followup


def previous():
    return SemanticQuery(question="2026 kanal bazında net ciro", tenant_id="a", datasource_id="b",
                         temporal=[TemporalSlot("2026", "YEAR", date(2026,1,1),date(2027,1,1))])


def test_period_edit_removes_old_period_and_keeps_measure_and_group():
    text, error = compose_followup("Peki geçen yıl?", previous())
    assert error is None
    assert "2026" not in text
    assert "gecen yil" in text and "kanal bazinda net ciro" in text


def test_expired_context_asks_instead_of_guessing():
    text, error = compose_followup("Peki geçen yıl?", None)
    assert text is None and error


def test_new_question_never_inherits_previous_context():
    assert compose_followup("2025 fatura sayısı", previous()) == ("2025 fatura sayısı", None)


def test_city_followup_preserves_previous_period_and_metric():
    text, error = compose_followup("Sadece Ankara", previous())
    assert not error and "2026" in text and "net ciro" in text and "sadece ankara" in text


def test_unknown_followup_words_are_not_dropped():
    assert compose_followup("Peki geçen yıl gizli", previous())[0] == "Peki geçen yıl gizli"
