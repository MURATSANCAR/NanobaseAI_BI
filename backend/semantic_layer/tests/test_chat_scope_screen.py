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


# ------------------------------------------------------------------ modül ekranı (2026-09-30 kararı, 10-03 bugünkü akış)
class TopicChooser:
    """Modül kapısının seçenekleri konulardır (+ şirket dışı, asistan); olasılık konu kimliğiyle verilir."""

    def __init__(self, probs, method=LOGPROBS):
        self.probs, self.method, self.calls = probs, method, []

    def choose(self, prompt, choices, *, system=None, **kw):
        self.calls.append({"prompt": prompt, "choices": choices, "system": system})
        key = {chat_scope._topic_choice(t): t["id"] for t in chat_scope.topics()}
        key.update({v: k for k, v in LABELS.items()})
        by_choice = {c: self.probs.get(key[c], 0.0) for c in choices}
        picked = max(by_choice, key=by_choice.get)
        return Choice(picked, choices.index(picked), by_choice if self.method == LOGPROBS else None, self.method)


PAZARLAMA = chat_scope.module_scope("pazarlama")


def test_confident_topic_outside_the_module_is_not_answered():
    llm = TopicChooser({"finans": 0.95, "pazarlama": 0.05})
    got = screen("Bu yıl net ciro ne kadar?", llm, module=PAZARLAMA)
    assert got.outside_module and got.answer_type == chat_scope.OUT_OF_MODULE
    assert "Pazarlama" in got.reply and "ana sayfa" in got.reply
    assert got.to_dict()["module"] == "finans" and got.to_dict()["screenModule"] == "pazarlama"
    assert len(llm.calls) == 1, "konu ve şirket dışı kararı tek çağrıda"
    assert "Pazarlama" in llm.calls[0]["system"] and len(llm.calls[0]["choices"]) == len(chat_scope.topics()) + 2


@pytest.mark.parametrize("probs", [
    {"finans": 0.6, "pazarlama": 0.4},                    # dışarısı eşik altı
    {"finans": 0.45, "satis": 0.44, "pazarlama": 0.11},   # dışarı toplam 0,89 < 0,9
])
def test_uncertain_topic_stays_in_the_module(probs):
    got = screen("kampanya cirosu", TopicChooser(probs), module=PAZARLAMA)
    assert got.intent == DATA and not got.outside_module and got.reply is None


def test_module_topic_goes_to_data_and_carries_its_module():
    got = screen("Bu ay kaç lansman kapandı?", TopicChooser({"pazarlama": 0.9, "finans": 0.1}), module=PAZARLAMA)
    assert not got.outside_module and got.topic["id"] == "pazarlama" and got.to_dict()["module"] == "pazarlama"


def test_module_screen_still_redirects_offtopic_and_never_refuses_without_probability():
    got = screen("Mercimek çorbası tarifi", TopicChooser({OFFTOPIC: 0.97, "finans": 0.03}), module=PAZARLAMA)
    assert got.intent == OFFTOPIC and got.reply == BI_REDIRECT
    got = screen("Bu yıl net ciro ne kadar?", TopicChooser({"finans": 1.0}, method=TEXT), module=PAZARLAMA)
    assert got.intent == DATA and not got.outside_module
    assert not screen("net ciro", FakeChooser(error=TimeoutError("x")), module=PAZARLAMA).outside_module


def test_module_screen_prompt_carries_no_technology_names():
    prompt = chat_scope.screen_system_prompt(PAZARLAMA)
    assert "Pazarlama" in prompt and "pazarlama planları" in prompt
    for name in ("Qwen", "vLLM", "SQL", "LINENET"):
        assert name not in prompt
