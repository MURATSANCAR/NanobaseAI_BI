"""Arşiv okuması hızlandırmaları (2026-10-06 ölçümü, book-vision-deep, 3 gün):

- düşünme bütçesi: page_scan_deep / scan_page_deep_key isteğinde `thinking_token_budget` (vars. 8000), cluster_name'de
  4000; max_tokens = bütçe + cevap payı; env ile ayarlanır, 0 = eski davranış;
- aynı istek önbelleği yalnız deterministik çağrıda (sıcaklık 0, tek cevap); oylama / yeniden bakış (0.1–0.6) asla;
- altyapı hataları: DNS / bağlantı reddi beklenip yeniden denenir, zaman aşımı çağrı içinde tekrar edilmez ve
  geçici sayılır; boş (0 bayt) sayfa görüntüsü yeniden çizilir; çağıran gidince gateway modele giden isteği iptal eder.

Model ve DB yok; geçit ve kayıt taklit edilir. Çalıştırma: editor-py imajında pytest."""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import httpx  # noqa: E402
import pytest  # noqa: E402

from editor import config, llm, transient  # noqa: E402

META = {"book-vision-deep": {"real_model": "m", "revision": "r1", "args": ["--max-model-len=40960"]}}


class _Resp:
    def __init__(self, status: int, body: dict | None = None, text: str = ""):
        self.status_code, self._body, self.text = status, body, text

    def json(self):
        return self._body


def _answer(content: str) -> _Resp:
    return _Resp(200, {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                       "usage": {"prompt_tokens": 10, "completion_tokens": 10}})


def _choice(token: str) -> _Resp:
    return _Resp(200, {"choices": [{"message": {"content": token}, "logprobs": {"content": [
        {"top_logprobs": [{"token": token, "logprob": 0.0}]}]}}]})


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    for k in ("EDITOR_VISION_THINK_BUDGET", "EDITOR_CLUSTER_THINK_BUDGET", "EDITOR_LLM_CACHE",
              "EDITOR_MODEL_TIMEOUT_SECONDS", "EDITOR_GATEWAY_DOWN_WAIT_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    config.settings.cache_clear()
    yield
    config.settings.cache_clear()


@pytest.fixture
def gateway(monkeypatch):
    """Scripted gateway + ledger: queued responses in order; every request and every cache lookup kept."""
    sent: list[dict] = []
    queue: list = []
    lookups: list[dict] = []
    ledger: dict[str, dict] = {}

    async def post(path, req):
        sent.append({**req})
        r = queue.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r

    async def aliases():
        return META

    async def record(self, *a, **k):
        return 1

    async def cached(self, alias, req):
        lookups.append({**req})
        return ledger.get(llm.request_digest(req))

    async def no_sleep(_):
        return None

    monkeypatch.setattr(llm, "_post", post)
    monkeypatch.setattr(llm, "aliases", aliases)
    monkeypatch.setattr(llm.Llm, "_record", record)
    monkeypatch.setattr(llm.Llm, "_cached", cached)
    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    return sent, queue, lookups, ledger


MSG = [{"role": "user", "content": "x"}]


# ------------------------------------------------------------------ thinking budget
def test_deep_scan_budget_default_and_env(monkeypatch):
    from editor import vision
    assert vision.deep_scan_limits() == (8000 + vision.SCAN_ANSWER_TOKENS, 8000)
    monkeypatch.setenv("EDITOR_VISION_THINK_BUDGET", "6000")
    config.settings.cache_clear()
    assert vision.deep_scan_limits() == (6000 + vision.SCAN_ANSWER_TOKENS, 6000)
    monkeypatch.setenv("EDITOR_VISION_THINK_BUDGET", "0")
    config.settings.cache_clear()
    assert vision.deep_scan_limits() == (16384, None)          # eski davranış


def test_cluster_name_budget_stays_under_old_ceiling(monkeypatch):
    from editor import figure_identity as fi
    max_tokens, budget = fi.cluster_name_limits()
    assert budget == 4000 and max_tokens == 6144 and max_tokens - budget >= fi.CLUSTER_ANSWER_TOKENS
    monkeypatch.setenv("EDITOR_CLUSTER_THINK_BUDGET", "5000")
    config.settings.cache_clear()
    assert fi.cluster_name_limits() == (5000 + fi.CLUSTER_ANSWER_TOKENS, 5000)
    monkeypatch.setenv("EDITOR_CLUSTER_THINK_BUDGET", "0")
    config.settings.cache_clear()
    assert fi.cluster_name_limits() == (6144, None)


def test_budget_field_in_request(gateway):
    sent, queue, _, _ = gateway
    queue += [_answer('{"a": 1}'), _answer('{"a": 1}')]
    asyncio.run(llm.Llm("g").chat("book-vision-deep", MSG, schema={"type": "object"}, max_tokens=16192,
                                  temperature=0.1, think_budget=8000))
    asyncio.run(llm.Llm("g").chat("book-vision-deep", MSG, schema={"type": "object"}, temperature=0.1))
    assert sent[0]["thinking_token_budget"] == 8000 and sent[0]["max_tokens"] == 16192
    assert "thinking_token_budget" not in sent[1]


def test_vision_deep_scan_sends_budget(monkeypatch):
    """page_scan_deep (scan_page_deep ve scan_page_deep_key aynı yoldan) isteği bütçeyi taşır."""
    from editor import vision
    seen = {}

    class _Db:
        @staticmethod
        def one(sql, *a):
            if "FROM generation" in sql:
                return {"book_version_id": "bv"}
            if "FROM page " in sql:
                return {"nontext_ink": 0.5, "layer_health": {}}
            return None

        class _Tx:
            def __enter__(self):
                return type("C", (), {"execute": lambda *a, **k: None})()

            def __exit__(self, *a):
                return False

        tx = _Tx
        J = staticmethod(lambda x: x)

    class _Llm:
        def __init__(self, gid):
            pass

        async def chat(self, alias, messages, **kw):
            seen.update(kw, alias=alias)
            return dict(vision.EMPTY_SCAN), 7

    tmp = pathlib.Path(__file__).parent / "__nonexistent__.png"
    monkeypatch.setattr(vision, "db", _Db)
    monkeypatch.setattr(vision, "Llm", _Llm)
    monkeypatch.setattr(vision, "render_page", lambda bv, p: {"path": str(tmp)})
    monkeypatch.setattr(vision.Path, "read_bytes", lambda self: b"png")
    monkeypatch.setattr(vision, "page_text_numbered", lambda g, p: "metin")
    monkeypatch.setattr(vision, "known_characters_text", lambda g: "-")
    monkeypatch.setattr(vision.prompts, "render", lambda name, **kw: (llm.PromptRef(name, "6"), "istem"))
    asyncio.run(vision.analyze_page_visual("g", 3, "deep", ["IMPORTANT_EVENT"]))
    assert seen["alias"] == "book-vision-deep"
    assert seen["think_budget"] == 8000 and seen["max_tokens"] == 8000 + vision.SCAN_ANSWER_TOKENS


# ------------------------------------------------------------------ same-request cache
def test_cacheable_only_deterministic(monkeypatch):
    assert llm.cacheable({"temperature": 0})
    assert llm.cacheable({"temperature": 0.0, "seed": 17})
    assert not llm.cacheable({"temperature": 0.1})         # tek görsel okuma (page_scan_deep, recheck)
    assert not llm.cacheable({"temperature": 0.6})         # oylama (text_visual_vote, continuity_vote)
    assert not llm.cacheable({"temperature": 0, "n": 3})
    assert not llm.cacheable({})
    monkeypatch.setenv("EDITOR_LLM_CACHE", "0")
    config.settings.cache_clear()
    assert not llm.cacheable({"temperature": 0})


def test_deterministic_call_answered_from_ledger(gateway):
    sent, queue, lookups, ledger = gateway
    req = {"model": "book-vision-deep", "messages": MSG, "max_tokens": 6144, "temperature": 0.0,
           "response_format": {"type": "json_schema", "json_schema": {"name": "out", "schema": {"type": "object"},
                                                                      "strict": True}}}
    ledger[llm.request_digest(req)] = {"id": 42, "response": {"content": '{"name": "Ali"}'}}
    out, cid = asyncio.run(llm.Llm("g").chat("book-vision-deep", MSG, schema={"type": "object"},
                                             max_tokens=6144, temperature=0.0))
    assert (out, cid) == ({"name": "Ali"}, 42) and sent == [] and len(lookups) == 1


def test_votes_and_sampled_reads_never_cached(gateway):
    sent, queue, lookups, ledger = gateway
    for t in (0.6, 0.1):
        req = {"model": "book-vision-deep", "messages": MSG, "max_tokens": 8192, "temperature": t}
        ledger[llm.request_digest(req)] = {"id": 42, "response": {"content": "eski"}}
        queue.append(_answer("yeni"))
        out, _ = asyncio.run(llm.Llm("g").chat("book-vision-deep", MSG, max_tokens=8192, temperature=t))
        assert out == "yeni"
    assert lookups == [] and len(sent) == 2


def test_cache_false_and_miss_go_to_model(gateway):
    sent, queue, lookups, ledger = gateway
    req = {"model": "book-vision-deep", "messages": MSG, "max_tokens": 4096, "temperature": 0}
    ledger[llm.request_digest(req)] = {"id": 42, "response": {"content": "eski"}}
    queue += [_answer("yeni"), _answer("x")]
    out, _ = asyncio.run(llm.Llm("g").chat("book-vision-deep", MSG, temperature=0, cache=False))
    assert out == "yeni" and lookups == []
    asyncio.run(llm.Llm("g").chat("book-vision-deep", [{"role": "user", "content": "başka"}], temperature=0))
    assert len(lookups) == 1 and len(sent) == 2                  # önbellekte yok: modele gitti


def test_choose_cached(gateway):
    sent, queue, lookups, ledger = gateway
    req = {"model": "book-vision-deep", "messages": MSG, "max_tokens": 1, "temperature": 0, "seed": 17,
           "logprobs": True, "top_logprobs": 20, "structured_outputs": {"choice": ["A", "B"]},
           "chat_template_kwargs": {"enable_thinking": False}}
    ledger[llm.request_digest(req)] = {"id": 9, "response": {"probs": {"A": 0.25, "B": 0.75}}}
    probs, cid = asyncio.run(llm.Llm("g").choose("book-vision-deep", MSG, ["A", "B"]))
    assert probs == {"A": 0.25, "B": 0.75} and cid == 9 and sent == []
    queue.append(_choice("A"))
    probs, _ = asyncio.run(llm.Llm("g").choose("book-vision-deep", MSG, ["A", "C"]))
    assert probs["A"] == 1.0 and len(sent) == 1


def test_digest_ignores_image_bytes_but_not_image_identity():
    a = {"messages": [{"content": [llm.image_part(b"one")]}], "temperature": 0}
    b = {"messages": [{"content": [llm.image_part(b"two")]}], "temperature": 0}
    assert llm.request_digest(a) == llm.request_digest({**a})
    assert llm.request_digest(a) != llm.request_digest(b)


# ------------------------------------------------------------------ infrastructure errors
def test_transient_classification():
    E = llm.ModelError
    assert transient.is_transient(E("book-vision-deep failed after 3 attempts: ConnectError: "
                                    "[Errno -3] Temporary failure in name resolution"))
    assert transient.model_text_transient("cluster_name failed after 3 attempts: [Errno -3] Temporary failure "
                                          "in name resolution")
    assert transient.model_text_transient("book-vision-deep timed out after 6600s: ReadTimeout: ")
    assert transient.failure_type_transient("ModelError", "x failed after 3 attempts: RemoteProtocolError: closed")
    assert not transient.model_text_transient("x failed after 3 attempts: 400 Failed to load image")
    assert not transient.model_text_transient("x failed after 3 attempts: finish_reason=length after 0 chars")
    # zincir korunur: son ModelError, düşen bağlantı hatasından doğar
    try:
        try:
            raise httpx.ConnectError("[Errno -3] Temporary failure in name resolution")
        except httpx.ConnectError as c:
            raise E("book-vision-deep failed after 3 attempts") from c
    except E as e:
        assert transient.is_transient(e)


def test_read_timeout_not_retried_in_call(gateway):
    sent, queue, _, _ = gateway
    queue.append(httpx.ReadTimeout(""))
    with pytest.raises(llm.ModelError) as ei:
        asyncio.run(llm.Llm("g").chat("book-vision-deep", MSG, temperature=0.1))
    assert len(sent) == 1 and "ReadTimeout" in str(ei.value)
    assert transient.is_transient(ei.value)


def test_connect_error_exhausting_attempts_is_transient(gateway):
    sent, queue, _, _ = gateway
    queue += [httpx.ConnectError("[Errno -3] Temporary failure in name resolution")] * 3
    with pytest.raises(llm.ModelError) as ei:
        asyncio.run(llm.Llm("g").chat("book-vision-deep", MSG, temperature=0.1))
    assert "ConnectError" in str(ei.value) and transient.is_transient(ei.value)


def test_error_text_never_empty():
    assert llm._error_text(httpx.ReadTimeout("")) == "ReadTimeout: "
    assert llm._error_text(ValueError("x")) == "x"


def test_post_waits_for_gateway_to_come_back(monkeypatch):
    calls = {"n": 0}

    class _Client:
        async def post(self, path, json=None, headers=None):
            calls["n"] += 1
            if calls["n"] <= 3:
                raise httpx.ConnectError("[Errno -3] Temporary failure in name resolution")
            return _Resp(200, {})

    async def no_sleep(_):
        return None

    monkeypatch.setattr(llm, "client", lambda: _Client())
    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
    r = asyncio.run(llm._post("/v1/chat/completions", {}))
    assert r.status_code == 200 and calls["n"] == 4
    # etkileşimli istek beklemez
    calls["n"] = 0
    with pytest.raises(httpx.ConnectError):
        asyncio.run(llm._post("/v1/embeddings", {}, llm.INTERACTIVE))
    assert calls["n"] == 1


def test_post_gives_up_after_window(monkeypatch):
    monkeypatch.setenv("EDITOR_GATEWAY_DOWN_WAIT_SECONDS", "0")
    config.settings.cache_clear()

    class _Client:
        async def post(self, path, json=None, headers=None):
            raise httpx.ConnectError("refused")

    monkeypatch.setattr(llm, "client", lambda: _Client())
    with pytest.raises(httpx.ConnectError):
        asyncio.run(llm._post("/v1/chat/completions", {}))


def test_model_timeout_setting(monkeypatch):
    assert config.settings().model_timeout_seconds == 6600
    monkeypatch.setenv("EDITOR_MODEL_TIMEOUT_SECONDS", "900")
    config.settings.cache_clear()
    assert config.settings().model_timeout_seconds == 900


# ------------------------------------------------------------------ page image
def test_empty_page_image_is_rendered_again(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    from editor import document
    doc = pymupdf.open()
    page = doc.new_page(width=200, height=300)
    page.insert_text((20, 40), "Sayfa")
    out = tmp_path / "p0001.png"
    out.write_bytes(b"")                                        # ölçülen durum: 0 bayt
    assert not document.png_complete(out)
    r = document._render_to(page, out, 600)
    assert document.png_complete(out) and r["path"] == str(out)
    assert not list(tmp_path.glob(".*.tmp"))                    # geçici dosya kalmaz
    before = out.stat().st_mtime_ns
    document._render_to(page, out, 600)                          # sağlamsa yeniden çizilmez
    assert out.stat().st_mtime_ns == before
    out.write_bytes(out.read_bytes()[:-20])                      # yarım yazılmış
    assert not document.png_complete(out)


def test_failed_cache_lookup_falls_back_to_model(monkeypatch):
    """Önbellek yalnız kısayol: DB araması düşerse model çağrılır."""
    sent = []

    async def post(path, req):
        sent.append(req)
        return _answer("yeni")

    async def aliases():
        return META

    async def record(self, *a, **k):
        return 1

    def broken(*a, **k):
        raise RuntimeError("db yok")

    monkeypatch.setattr(llm, "_post", post)
    monkeypatch.setattr(llm, "aliases", aliases)
    monkeypatch.setattr(llm.Llm, "_record", record)
    monkeypatch.setattr(llm.db, "one", broken)
    out, _ = asyncio.run(llm.Llm("g").chat("book-vision-deep", MSG, temperature=0))
    assert out == "yeni" and len(sent) == 1
