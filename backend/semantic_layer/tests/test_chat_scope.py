import pytest
from semantic_bridge.chat_scope import is_intro

@pytest.mark.parametrize("question", ["test", "şişt", "Sen kimsin?", "Merhaba!", "..."])
def test_intro_does_not_call_model(question):
    class Never:
        def chat(self, *args, **kwargs):
            raise AssertionError("unnecessary model call")
    assert is_intro(question, Never())

@pytest.mark.parametrize("question", ["test müşterisinin cirosu", "2026", "sadece Ankara", "bilinmeyen iş terimine göre rapor"])
def test_unknown_data_is_not_rejected_without_classifier(question):
    assert not is_intro(question)

@pytest.mark.parametrize("reply, expected", [('{{bad', False), ('{"intent":"UNKNOWN"}', False), ('{"intent":"DATA"}', False), ('{"intent":"INTRO"}', True)])
def test_classifier_contract(reply, expected):
    class Model:
        def chat(self, messages, **kwargs):
            assert 'hasDataContext' in messages[-1]['content']
            return reply
    assert is_intro('örnek mesaj', Model(), has_context=True) is expected
