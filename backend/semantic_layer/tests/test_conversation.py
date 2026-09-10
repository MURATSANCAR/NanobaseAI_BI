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


def test_unique_exact_value_becomes_audited_filter():
    from types import SimpleNamespace
    from semantic_layer.models import ResolvedSlot, Mapping
    from semantic_layer.runtime.value_probe import ValueHit
    from semantic_layer.runtime.conversation import bind_followup_value
    old=previous();old.slots=[ResolvedSlot("kanal","COLUMN","CERTIFIED",mapping=Mapping("","CLCARD","LG_{n0}_CLCARD",column="SPECODE2"))]
    current=previous();current.unresolved=["ankara"]
    probe=SimpleNamespace(find=lambda *a:[ValueHit("CLCARD","CITY","ANKARA",2)])
    bind_followup_value("Sadece Ankara",current,old,probe,None,SimpleNamespace(patterns={"CLCARD":"LG_{n0}_CLCARD"}))
    assert not current.unresolved
    assert current.filters[0].mapping.values==["ANKARA"]
    assert current.filters[0].status=="INFERRED"


def test_ambiguous_or_partial_value_does_not_become_filter():
    from types import SimpleNamespace
    from semantic_layer.models import ResolvedSlot, Mapping
    from semantic_layer.runtime.value_probe import ValueHit
    from semantic_layer.runtime.conversation import bind_followup_value
    old=previous();old.slots=[ResolvedSlot("kanal","COLUMN","CERTIFIED",mapping=Mapping("","CLCARD","p",column="SPECODE2"))]
    for hits in [[ValueHit("CLCARD","CITY","ANKARA MERKEZ",2)],
                 [ValueHit("CLCARD","CITY","ANKARA",2),ValueHit("CLCARD","NAME","ANKARA",1)]]:
        current=previous();current.unresolved=["ankara"]
        bind_followup_value("Sadece Ankara",current,old,SimpleNamespace(find=lambda *a:hits),None,SimpleNamespace(patterns={"CLCARD":"p"}))
        assert current.unresolved==["ankara"] and not current.filters
