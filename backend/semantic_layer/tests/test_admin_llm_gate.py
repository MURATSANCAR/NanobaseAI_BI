"""Yönetim ekranındaki model denemesi LLM kapısından geçer (2026-09-28 AI fırsatları, hemen-düzelt 5).

Sözleşme: `admin.llm_test` istemciyi kendisi kurmaz; app.py'nin bağladığı kapı işlevinden alır (kayıtlı ayarla), cevap
ve sırada bekleme süresi ekrana yazılır; kapı bağlı değilse deneme «bağlı değil» der, sıranın dışından çağrı yapmaz.
Köprü içinde bağlanan kapı, kayıtlı ayar çalışan istemciyle aynıysa `rt.llm_for("yonetim")`, değilse aynı sıraya bağlı
geçici `QueuedLlm` döndürür.
"""

from __future__ import annotations

import inspect

import pytest

from semantic_bridge import admin as AD
from semantic_bridge import app as APP
from semantic_layer.runtime.llm_queue import QueuedLlm

CONF = {"OPENAI_API_BASE": "http://model.example/v1", "LLM_MODEL_NAME": "nanobaseAI", "OPENAI_API_KEY": "k"}


class FakeGateLlm:
    def __init__(self, reply="TAMAM", wait=0):
        self.reply, self.last_wait_ms, self.calls = reply, wait, []

    def chat(self, messages, **kw):
        self.calls.append((messages, kw))
        return self.reply


@pytest.fixture
def conf(monkeypatch):
    monkeypatch.setattr(AD, "conf", lambda k, d="": CONF.get(k, d))
    yield
    AD.set_llm_gate(None)


def test_llm_test_does_not_build_its_own_client():
    src = inspect.getsource(AD.llm_test)
    assert "LlmClient" not in src and "_llm_gate(" in src


def test_without_gate_the_test_refuses(conf):
    AD.set_llm_gate(None)
    ok, msg = AD.llm_test()
    assert not ok and "kapısı" in msg


def test_gate_gets_saved_settings_and_wait_is_reported(conf):
    seen = {}
    fake = FakeGateLlm(wait=1500)

    def gate(base, model, key, timeout):
        seen.update(base=base, model=model, key=key)
        return fake

    AD.set_llm_gate(gate)
    ok, msg = AD.llm_test()
    assert ok and "«TAMAM»" in msg and "1500 ms sırada bekledi" in msg
    assert seen == {"base": CONF["OPENAI_API_BASE"], "model": "nanobaseAI", "key": "k"}
    assert fake.calls[0][1] == {"max_tokens": 8}

    AD.set_llm_gate(lambda *a: FakeGateLlm(reply="<think>x</think>  "))
    ok, msg = AD.llm_test()
    assert not ok and "boş cevap" in msg
    AD.set_llm_gate(lambda *a: None)
    assert AD.llm_test()[0] is False


def test_missing_settings_short_circuit(monkeypatch):
    monkeypatch.setattr(AD, "conf", lambda k, d="": "")
    AD.set_llm_gate(lambda *a: pytest.fail("ayar yokken kapıya gidilmez"))
    try:
        assert AD.llm_test() == (False, "Model adresi ya da model adı girilmemiş.")
    finally:
        AD.set_llm_gate(None)


def test_bridge_binds_a_gate_that_queues():
    src = inspect.getsource(APP)
    i = src.index("def _llm_gate_for_test")
    body = src[i:src.index("admin_mod.set_llm_gate(_llm_gate_for_test)")]
    assert 'llm_for("yonetim"' in body and "QueuedLlm(client, r.queue" in body
    assert QueuedLlm  # sarmalayıcı kapının kendisi
