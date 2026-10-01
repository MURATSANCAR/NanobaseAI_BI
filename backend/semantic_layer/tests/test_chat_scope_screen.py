"""Plan öncesi kapsam kapısı (`chat_scope.screen`, 2026-10-01).

Şirket dışı soru 8.192 token'lık plan çağrısına gitmeden kibar yönlendirme alır; iş sorusu hiçbir arıza yüzünden
reddedilmez: ret yalnız olasılık okunmuş ve eşik üstündeyse.
"""
import pytest

from semantic_bridge import chat_scope
from semantic_bridge.chat_scope import BI_INTRO, BI_REDIRECT, DATA, IDENTITY, OFFTOPIC, screen
from semantic_layer.runtime.llm_choose import Choice, LOGPROBS, TEXT

LABELS = chat_scope._SCREEN_CHOICES


class FakeChooser:
    def __init__(self, probs=None, choice=None, method=LOGPROBS, error=None):
        self.probs, self.choice, self.method, self.error = probs, choice, method, error
        self.calls = []

    def choose(self, prompt, choices, *, system=None, **kw):
        self.calls.append({"prompt": prompt, "choices": choices, "system": system})
        if self.error:
            raise self.error
        by_choice = {LABELS[k]: v for k, v in (self.probs or {}).items()} if self.probs else None
        picked = LABELS[self.choice] if self.choice else max(by_choice, key=by_choice.get)
        return Choice(picked, choices.index(picked), by_choice, self.method)


def test_confident_offtopic_is_redirected():
    llm = FakeChooser({DATA: 0.02, OFFTOPIC: 0.97, IDENTITY: 0.01})
    got = screen("Mercimek çorbası tarifi verir misin?", llm)
    assert got.intent == OFFTOPIC and got.reply == BI_REDIRECT and got.is_intro
    assert got.to_dict()["screen"]["probabilities"][OFFTOPIC] == 0.97
    assert len(llm.calls) == 1 and "Mercimek" in llm.calls[0]["prompt"]


def test_confident_identity_gets_the_intro():
    got = screen("Bana kendinden bahset", FakeChooser({DATA: 0.03, OFFTOPIC: 0.02, IDENTITY: 0.95}))
    assert got.intent == IDENTITY and got.reply == BI_INTRO


@pytest.mark.parametrize("probs", [
    {DATA: 0.2, OFFTOPIC: 0.8, IDENTITY: 0.0},        # eşik altı
    {DATA: 0.6, OFFTOPIC: 0.3, IDENTITY: 0.1},        # iş sorusu
    {DATA: 0.12, OFFTOPIC: 0.45, IDENTITY: 0.43},     # dışarıda toplam 0,88 < 0,9
])
def test_uncertain_or_business_goes_to_the_data_pipeline(probs):
    got = screen("Suç ve Ceza'yı kim yazdı?", FakeChooser(probs))
    assert got.intent == DATA and got.reply is None and not got.is_intro


def test_no_probability_means_no_rejection():
    got = screen("Hava nasıl?", FakeChooser(choice=OFFTOPIC, method=TEXT))
    assert got.intent == DATA


def test_model_failure_or_plain_client_keeps_the_data_pipeline():
    assert screen("Hava nasıl?", FakeChooser(error=TimeoutError("x"))).intent == DATA
    assert screen("Hava nasıl?", object()).intent == DATA
    assert screen("Hava nasıl?", None).intent == DATA


def test_identity_pattern_needs_no_model():
    llm = FakeChooser({DATA: 1.0, OFFTOPIC: 0.0, IDENTITY: 0.0})
    assert screen("Hangi modelsin?", llm).intent == IDENTITY
    assert llm.calls == []


def test_context_is_passed_to_the_model():
    llm = FakeChooser({DATA: 0.9, OFFTOPIC: 0.1, IDENTITY: 0.0})
    screen("ya toptan?", llm, has_context=True)
    assert '"hasDataContext": true' in llm.calls[0]["prompt"]


def test_screen_prompt_lists_company_areas_and_no_technology_names():
    prompt = chat_scope.screen_system_prompt()
    assert "finans ve bütçe" in prompt and "kitap" in prompt
    for name in ("Qwen", "vLLM", "SQL", "LINENET"):
        assert name not in prompt
