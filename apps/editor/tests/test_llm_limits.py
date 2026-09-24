"""llm: bağlam aşımı tekrar denenmez; uzunluk durmasında bütçe bağlamı aşmayacak kadar büyür.
worker: bağlam aşımı Temporal'a tekrar denenmez hata olarak gider.

Ölçülen olay (2026-09-23): 110k token'lık kimlik istemi 12000 cevap payıyla sığdı, cevap uzunluğa
takıldı, pay 24000'e katlandı, istek bağlamı aştı; aynı istek 4 aktivite denemesi x 3 çağrı = 12 kez
gönderildi. Model ve DB yok; geçit ve kayıt taklit edilir. Çalıştırma: editor-py imajında pytest."""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from editor import llm  # noqa: E402

OVERFLOW = ('{"error":{"message":"This model\'s maximum context length is 131072 tokens. However, '
            'you requested 24000 output tokens and your prompt contains at least 107073 input tokens"}}')
META = {"book-director": {"real_model": "m", "revision": "r", "args": ["--max-model-len=131072", "--x=1"]}}


class _Resp:
    def __init__(self, status: int, body: dict | None = None, text: str = ""):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        return self._body


def _answer(content: str, finish: str = "stop", prompt_tokens: int = 1000) -> _Resp:
    return _Resp(200, {"choices": [{"message": {"content": content}, "finish_reason": finish}],
                       "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 10}})


@pytest.fixture
def gateway(monkeypatch):
    """Scripted gateway: returns the queued responses in order and keeps every request."""
    sent: list[dict] = []
    queue: list[_Resp] = []

    async def post(path, req):
        sent.append({**req})
        return queue.pop(0)

    async def aliases():
        return META

    async def record(self, *a, **k):
        return 1

    async def no_sleep(_):
        return None

    monkeypatch.setattr(llm, "_post", post)
    monkeypatch.setattr(llm, "aliases", aliases)
    monkeypatch.setattr(llm.Llm, "_record", record)
    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    return sent, queue


def test_context_length_from_args():
    assert llm.context_length(META["book-director"]) == 131072
    assert llm.context_length({"args": ["--gpu-memory-utilization=0.9"]}) is None
    assert llm.context_length({}) is None


def test_overflow_is_recognised_only_on_400():
    assert llm._is_context_overflow(400, OVERFLOW)
    assert not llm._is_context_overflow(400, '{"error":"bad json schema"}')
    assert not llm._is_context_overflow(503, OVERFLOW)


def test_retry_budget_keeps_inside_context():
    # measured case: doubling 12000 next to a ~110k prompt overflowed
    assert llm.retry_budget(12000, 110000, 131072) == 131072 - 110000 - 64
    # plenty of room: plain doubling
    assert llm.retry_budget(12000, 20000, 131072) == 24000
    # capped by MAX_RETRY_TOKENS
    assert llm.retry_budget(24000, 1000, 131072) == llm.MAX_RETRY_TOKENS
    # no room to grow: the budget that already fit is kept, never lowered
    assert llm.retry_budget(12000, 125000, 131072) == 12000
    # unknown prompt size or context: previous behaviour
    assert llm.retry_budget(12000, None, 131072) == 24000
    assert llm.retry_budget(12000, 110000, None) == 24000


def test_chat_overflow_is_sent_once(gateway):
    sent, queue = gateway
    queue.append(_Resp(400, text=OVERFLOW))
    with pytest.raises(llm.ContextOverflow):
        asyncio.run(llm.Llm("g").chat("book-director", [{"role": "user", "content": "x"}], max_tokens=12000))
    assert len(sent) == 1


def test_choose_overflow_is_sent_once(gateway):
    sent, queue = gateway
    queue.append(_Resp(400, text=OVERFLOW))
    with pytest.raises(llm.ContextOverflow):
        asyncio.run(llm.Llm("g").choose("book-director", [{"role": "user", "content": "x"}], ["A", "B"]))
    assert len(sent) == 1


def test_chat_length_retry_uses_prompt_size(gateway):
    sent, queue = gateway
    long_text = '{"a": "' + " ".join(str(i) for i in range(200))   # truncated, not a loop
    queue += [_answer(long_text, "length", prompt_tokens=110000), _answer('{"a": 1}')]
    out, _ = asyncio.run(llm.Llm("g").chat("book-director", [{"role": "user", "content": "x"}],
                                           schema={"type": "object"}, max_tokens=12000))
    assert out == {"a": 1}
    assert [r["max_tokens"] for r in sent] == [12000, 131072 - 110000 - 64]


def test_other_400_still_retries(gateway):
    sent, queue = gateway
    queue += [_Resp(400, text='{"error":"transient"}'), _answer("ok")]
    out, _ = asyncio.run(llm.Llm("g").chat("book-director", [{"role": "user", "content": "x"}]))
    assert out == "ok" and len(sent) == 2


def test_worker_turns_overflow_into_non_retryable():
    pytest.importorskip("temporalio")
    from temporalio.exceptions import ApplicationError
    from editor.workflow.worker import DeterministicFailureInterceptor

    class _Next:
        def __init__(self, exc):
            self.exc = exc

        async def execute_activity(self, input):
            raise self.exc

    def run(exc):
        return asyncio.run(DeterministicFailureInterceptor(_Next(exc)).execute_activity(None))

    with pytest.raises(ApplicationError) as e:
        run(llm.ContextOverflow("400 too long"))
    assert e.value.non_retryable and e.value.type == "ContextOverflow"

    # wrapped by the activity's own error: still found through the chain
    try:
        try:
            raise llm.ContextOverflow("400 too long")
        except llm.ContextOverflow as inner:
            raise RuntimeError("identity failed") from inner
    except RuntimeError as wrapped:
        outer = wrapped
    with pytest.raises(ApplicationError) as e:
        run(outer)
    assert e.value.non_retryable

    # anything else keeps the retry policy
    with pytest.raises(llm.ModelError):
        run(llm.ModelError("503 gpu busy"))
