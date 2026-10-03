"""Modül ekranı kapsamı uçtan uca (`Runtime.ask`, 2026-09-30 kullanıcı kararı; 2026-10-03 bugünkü akışa taşındı).

Modül ekranından sorulan soru yalnız o modülün konularıyla cevaplanır: konu dışarıdaysa plan çağrısı yapılmaz, veri
okunmaz, ana sayfadaki ZEKİ önerilir. Aynı soru ana sayfadan sorulunca finans planlayıcısına gider.
"""
import types
from types import SimpleNamespace

import pytest

import semantic_bridge.finance_query as fq
from semantic_bridge import chat_scope
from semantic_bridge.app import Runtime
from semantic_bridge.finance_query.planner import Plan
from semantic_layer.runtime.llm_choose import Choice, LOGPROBS
from semantic_layer.store.catalog_store import open_store


class Chooser:
    def __init__(self, probs):
        self.probs, self.calls = probs, []

    def choose(self, prompt, choices, *, system=None, **kw):
        self.calls.append(choices)
        key = {chat_scope._topic_choice(t): t["id"] for t in chat_scope.topics()}
        key.update({v: k for k, v in chat_scope._SCREEN_CHOICES.items()})
        by_choice = {c: self.probs.get(key[c], 0.0) for c in choices}
        picked = max(by_choice, key=by_choice.get)
        return Choice(picked, choices.index(picked), by_choice, LOGPROBS)


class Executor:
    def __init__(self, runtime):
        self.read_retries, self.source_periods, self.runs, self.output_fields = 0, [], [], []
        self.numeric_fields, self.gaps, self.coverage_complete, self.notes, self.section_results = [], [], True, [], []

    def execute(self, plan):
        return [{"net_sales": 1234.5}]


@pytest.fixture
def planned(monkeypatch):
    seen = []

    def build(question, llm, previous=None, trace=None, **kw):
        seen.append(question)
        return Plan(("net_sales",), (), (("2026-01-01", "2026-10-02"),))

    monkeypatch.setattr(fq, "build", build)
    monkeypatch.setattr(fq, "Executor", Executor)
    return seen


def runtime(model):
    rt = SimpleNamespace(store=open_store("sqlite://"), settings=SimpleNamespace(tenant_id="t", datasource_id="d"),
                         llm_for=lambda module: model, attach_widget=lambda *a, **k: None,
                         remember_result=lambda *a, **k: None)
    rt._ask = types.MethodType(Runtime._ask, rt)
    return rt


def ask(rt, question, module=None):
    return Runtime.ask(rt, question, thread_id=None, sample_size=50, username="ali", module=module)


def test_question_outside_the_screen_module_is_not_planned(planned):
    model = Chooser({"finans": 0.96, "pazarlama": 0.04})
    body = ask(runtime(model), "Bu yıl net ciro ne kadar?", module="pazarlama")
    assert body["type"] == chat_scope.OUT_OF_MODULE, body
    assert "Pazarlama" in body["explanation"] and body["chatScope"]["screenModule"] == "pazarlama"
    assert body["chatScope"]["module"] == "finans" and "records" not in body
    assert planned == [], "plan çağrısı yapılmadı"


def test_same_question_on_its_own_module_or_home_is_planned(planned):
    model = Chooser({"finans": 0.96, "pazarlama": 0.04})
    body = ask(runtime(model), "Bu yıl net ciro ne kadar?", module="finans")
    assert body["type"] == "TEXT_TO_SQL", body
    assert body["chatScope"]["module"] == "finans" and body["chatScope"]["screenModule"] == "finans"
    body = ask(runtime(model), "Bu yıl net ciro ne kadar?")
    assert body["type"] == "TEXT_TO_SQL" and "chatScope" not in body, body
    assert len(planned) == 2


def test_unknown_module_id_is_home(planned):
    body = ask(runtime(Chooser({"finans": 0.96})), "Bu yıl net ciro ne kadar?", module="kampus")
    assert body["type"] == "TEXT_TO_SQL" and planned


def test_identity_on_a_module_screen_needs_no_model(planned):
    model = Chooser({"finans": 1.0})
    body = ask(runtime(model), "Sen kimsin?", module="pazarlama")
    assert body["type"] == "MODULE_INTRO" and model.calls == [] and planned == []
