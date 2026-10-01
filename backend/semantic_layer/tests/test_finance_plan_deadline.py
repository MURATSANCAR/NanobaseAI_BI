"""Finans planının düşünmeli denemesine duvar saati sınırı (2026-10-01).

Yavaş GPU'da düşünmeli ilk deneme 646 sn sürüp boş kesildi; düşünmesiz deneme 4-18 sn'de doğru plan
veriyor. Sınır dolunca istek iptal edilir (akışlı, bağlantı kapanır) ve düşünmesiz denemeye geçilir.
"""
import threading

from semantic_bridge.finance_query.planner import _object
from semantic_layer.candidates.llm_client import LlmCancelled


class SlowThinker:
    """Düşünmeli istekte iptal gelene kadar bekler; düşünmesizde hemen cevap verir."""

    supports_cancel = True

    def __init__(self):
        self.calls = []

    def complete(self, messages, **kw):
        thinking = kw["body"]["chat_template_kwargs"]["enable_thinking"]
        self.calls.append({"thinking": thinking, "stream": kw.get("stream"), "cancel": kw.get("cancel") is not None})
        if thinking:
            assert kw["cancel"].wait(5), "sınır iptali gelmedi"
            raise LlmCancelled()
        return {"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}


def test_reasoning_attempt_is_cut_at_the_deadline_and_retried_plain(monkeypatch):
    monkeypatch.setenv("FINANCE_PLAN_THINK_DEADLINE_SEC", "0.05")
    llm, trace = SlowThinker(), []
    assert _object(llm, [{"role": "user", "content": "x"}], 100, {}, "finance_plan", trace) == {"ok": True}
    assert [c["thinking"] for c in llm.calls] == [True, False]
    assert llm.calls[0]["stream"] is True and llm.calls[0]["cancel"]
    assert llm.calls[1]["stream"] is False and not llm.calls[1]["cancel"]
    assert trace[0]["finishReason"] == "think_deadline" and trace[0]["nextAttemptThinkingRequested"] is False


def test_deadline_zero_keeps_the_old_unbounded_call(monkeypatch):
    monkeypatch.setenv("FINANCE_PLAN_THINK_DEADLINE_SEC", "0")

    class Fast:
        def __init__(self):
            self.kw = None

        def complete(self, messages, **kw):
            self.kw = kw
            return {"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}

    llm = Fast()
    assert _object(llm, [{"role": "user", "content": "x"}], 100, {}, "finance_plan", []) == {"ok": True}
    assert llm.kw["stream"] is False and "cancel" not in llm.kw


def test_an_outside_cancel_is_not_mistaken_for_the_deadline(monkeypatch):
    monkeypatch.setenv("FINANCE_PLAN_THINK_DEADLINE_SEC", "60")

    class Broken:
        def complete(self, messages, **kw):
            raise LlmCancelled()

    import pytest
    with pytest.raises(LlmCancelled):
        _object(Broken(), [{"role": "user", "content": "x"}], 100, {}, "finance_plan", [])


def test_queued_model_starts_the_timer_only_when_admitted(monkeypatch):
    monkeypatch.setenv("FINANCE_PLAN_THINK_DEADLINE_SEC", "0.05")

    class Queued(SlowThinker):
        queue = object()

        def complete(self, messages, **kw):
            admitted = kw.pop("on_admitted", None)
            if kw["body"]["chat_template_kwargs"]["enable_thinking"]:
                assert admitted is not None
                assert not kw["cancel"].wait(0.2), "zamanlayıcı sıra kabulünden önce başladı"
                admitted(object())
            return super().complete(messages, **kw)

    llm = Queued()
    assert _object(llm, [{"role": "user", "content": "x"}], 100, {}, "finance_plan", []) == {"ok": True}
    assert [c["thinking"] for c in llm.calls] == [True, False]
