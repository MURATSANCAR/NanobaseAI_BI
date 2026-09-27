"""Kapalı küme seçim (`QueuedLlm.choose`): tek token cevap, aday olasılıkları, yedek yol, eleme turu, kapı sırası.

Model yerine sahte bir uç: her seçeneğe bir ağırlık verilir, uç ilk token'ın adaylarını bu ağırlıklardan
üretir — vLLM'in `structured_outputs.choice` + `logprobs` cevabının biçiminde."""

from __future__ import annotations

import math
import re
import threading
import time
from contextlib import contextmanager

import pytest
import sqlalchemy as sa

from semantic_layer.candidates.llm_client import LlmHttpError
from semantic_layer.runtime import llm_choose as C
from semantic_layer.runtime.llm_queue import LlmQueue, QueuedLlm
from semantic_layer.store import schema as S
from semantic_layer.store.catalog_store import open_store

_OPTION = re.compile(r"^([A-Z])\) (.*)$")


def _shown(messages):
    """Soruya eklenen «A) …» satırlarından etiket → seçenek."""
    out = {}
    for line in messages[-1]["content"].splitlines():
        m = _OPTION.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


class Endpoint:
    """Sahte vLLM ucu. `weights`: seçenek metni → ilk token olasılığı (etiket üstünden); `noise`: etiket
    olmayan bir token'a düşen olasılık; `fail`: complete() bu istisnayı atar; `logprobs=False`: cevapta
    olasılık yok; `content`: cevap metnini zorla; `text`: düz metin (chat) cevabı."""

    supports_cancel = False

    def __init__(self, weights=None, *, noise=0.0, fail=None, logprobs=True, content=None, text="", delay=0.0):
        self.weights = dict(weights or {})
        self.noise, self.fail, self.logprobs, self.content, self.text, self.delay = noise, fail, logprobs, content, text, delay
        self.model = "sahte"
        self.requests: list[tuple[str, list, dict]] = []
        self.order: list[str] = []
        self.concurrent = self.max_concurrent = 0
        self._lock = threading.Lock()

    @contextmanager
    def _busy(self, messages):
        with self._lock:
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            time.sleep(self.delay)
            self.order.append(messages[-1]["content"].split("\n", 1)[0])
            yield
        finally:
            with self._lock:
                self.concurrent -= 1

    def complete(self, messages, *, max_tokens=4096, temperature=0.0, body=None, stream=None, **_):
        self.requests.append(("complete", messages, {"max_tokens": max_tokens, "temperature": temperature, "stream": stream, **(body or {})}))
        with self._busy(messages):
            if self.fail is not None:
                raise self.fail
            labels = list(((body or {}).get("structured_outputs") or {}).get("choice") or [])
            shown = _shown(messages)
            w = {label: self.weights.get(shown.get(label), 0.0) for label in labels}
            best = max(labels, key=lambda label: (w[label], -labels.index(label)))
            top = [{"token": label, "logprob": math.log(p)} for label, p in w.items() if p > 0]
            if self.noise:
                top.append({"token": "Bu", "logprob": math.log(self.noise)})
            reply = {"message": {"content": best if self.content is None else self.content}, "finish_reason": "length"}
            if self.logprobs:
                reply["logprobs"] = {"content": [{"token": best, "logprob": math.log(w[best]) if w[best] > 0 else -9999.0, "top_logprobs": top}]}
            return reply

    def chat(self, messages, **kwargs):
        self.requests.append(("chat", messages, kwargs))
        with self._busy(messages):
            return self.text


class TextOnly:
    """complete() bilmeyen eski tip istemci: yalnız metin."""

    model = "metin"

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def chat(self, messages, **_):
        self.calls += 1
        return self.text


def _gate(llm):
    return QueuedLlm(llm, LlmQueue())


# ---------------------------------------------------------------------------------------------- tek token
def test_single_token_answer_gives_normalised_probabilities():
    ep = Endpoint({"evet": 0.6, "hayır": 0.2}, noise=0.2)
    r = _gate(ep).choose("Özet bu kategoriyle uyumlu mu?", ["evet", "hayır"])
    assert r.method == C.LOGPROBS and r.choice == "evet" and r.index == 0 and r.error is None and r.calls == 1
    assert r.probs == pytest.approx({"evet": 0.75, "hayır": 0.25})
    assert r.probability == pytest.approx(0.75) and r.margin == pytest.approx(0.5)
    assert r.coverage == pytest.approx(0.8), "etiket dışı token'a düşen pay kapsamda görünmeli"
    kind, _, sent = ep.requests[0]
    assert kind == "complete" and len(ep.requests) == 1
    assert sent["max_tokens"] == 1 and sent["temperature"] == 0.0 and sent["stream"] is False
    assert sent["structured_outputs"] == {"choice": ["A", "B"]}
    assert sent["logprobs"] is True and sent["top_logprobs"] == C.DEFAULT_TOP_LOGPROBS
    # eşik çağıranın
    assert r.confident(0.7) and not r.confident(0.8)
    assert r.confident(0.7, min_margin=0.4) and not r.confident(0.7, min_margin=0.6)
    assert not r.confident(0.7, min_coverage=0.9)


def test_multi_token_choices_are_asked_by_single_letter_label():
    opts = ["Çocuk Kitapları > Masal", "Tarih > Osmanlı Tarihi", "Kişisel Gelişim > İletişim"]
    ep = Endpoint({opts[1]: 0.9, opts[2]: 0.1})
    r = _gate(ep).choose("Bu kitap hangi kategoriye girer?\nÖzet: Kanuni dönemi.", opts, system="Kısa cevap ver.")
    assert r.choice == opts[1] and r.index == 1 and r.method == C.LOGPROBS
    assert set(r.probs) == set(opts) and r.probs[opts[0]] == 0.0
    assert sum(r.probs.values()) == pytest.approx(1.0)
    _, messages, sent = ep.requests[0]
    assert sent["structured_outputs"]["choice"] == ["A", "B", "C"], "seçeneğin kendisi değil etiketi seçtirilmeli"
    assert messages[0] == {"role": "system", "content": "Kısa cevap ver."}
    assert "B) Tarih > Osmanlı Tarihi" in messages[-1]["content"]
    assert messages[-1]["content"].startswith("Bu kitap hangi kategoriye girer?")


def test_option_text_is_listed_on_one_line():
    messages = C.build_messages("Soru", ["Roman\n(yetişkin)", "Öykü"])
    assert "A) Roman (yetişkin)" in messages[-1]["content"] and len(messages) == 1


# ---------------------------------------------------------------------------------------------- olasılık okuma
def test_probabilities_are_normalised_over_the_labels():
    reply = {"logprobs": {"content": [{"token": "B", "logprob": math.log(0.3), "top_logprobs": [
        {"token": "B", "logprob": math.log(0.3)},       # üretilen token adaylarda da var: bir kez sayılır
        {"token": " B", "logprob": math.log(0.1)},      # boşluklu yazımı da B'nin payı
        {"token": "A", "logprob": math.log(0.2)},
        {"token": "Hmm", "logprob": math.log(0.4)},     # etiket değil: normalize dışı
    ]}]}}
    probs, coverage = C.read_logprobs(reply, ["A", "B", "C"])
    assert probs == pytest.approx({"A": 1 / 3, "B": 2 / 3, "C": 0.0})
    assert sum(probs.values()) == pytest.approx(1.0) and coverage == pytest.approx(0.6)


def test_the_sampled_token_counts_even_when_missing_from_the_top_list():
    reply = {"logprobs": {"content": [{"token": "C", "logprob": math.log(0.5), "top_logprobs": [{"token": "A", "logprob": math.log(0.5)}]}]}}
    probs, _ = C.read_logprobs(reply, ["A", "B", "C"])
    assert probs == pytest.approx({"A": 0.5, "B": 0.0, "C": 0.5})


@pytest.mark.parametrize("reply", [
    None, {}, {"logprobs": None}, {"logprobs": {"content": []}}, {"logprobs": {"content": ["x"]}},
    {"logprobs": {"content": [{"token": "A", "logprob": "sayı değil"}]}},
    {"logprobs": {"content": [{"token": "Bu", "logprob": -0.1, "top_logprobs": [{"token": "Şu", "logprob": -2.0}]}]}},
])
def test_unreadable_logprobs_give_no_probability(reply):
    assert C.read_logprobs(reply, ["A", "B"]) == (None, 0.0)


# ---------------------------------------------------------------------------------------------- yedek yol
def test_answer_without_logprobs_is_read_as_text_without_probability():
    ep = Endpoint({"roman": 1.0}, logprobs=False, content="B")
    r = _gate(ep).choose("Tür?", ["roman", "öykü"])
    assert r.choice == "öykü" and r.index == 1 and r.method == C.TEXT
    assert r.probs is None and r.probability is None and r.margin is None
    assert r.calls == 1 and "olasılı" in r.error
    assert not r.confident(0.0), "olasılıksız sonuç hiçbir eşikte «emin» sayılmaz"


def test_endpoint_that_rejects_the_structured_request_falls_back_to_text():
    ep = Endpoint(fail=LlmHttpError(400, "unknown field: structured_outputs"), text="Cevap: B")
    r = _gate(ep).choose("Tür?", ["roman", "öykü", "şiir"])
    assert r.choice == "öykü" and r.method == C.TEXT and r.probs is None and r.calls == 2
    assert "desteklenmiyor" in r.error
    assert [k for k, _, _ in ep.requests] == ["complete", "chat"]
    _, _, sent = ep.requests[1]
    assert sent == {"max_tokens": 16, "temperature": 0.0}


def test_client_without_structured_call_uses_text():
    r = _gate(TextOnly("(C)")).choose("Tür?", ["roman", "öykü", "şiir"])
    assert r.choice == "şiir" and r.method == C.TEXT and r.probs is None and r.calls == 1


@pytest.mark.parametrize("error", [LlmHttpError(503, "dolu"), LlmHttpError(429, "dolu"), RuntimeError("LLM unreachable after 3 attempts")])
def test_a_model_that_cannot_answer_is_raised_not_guessed(error):
    ep = Endpoint(fail=error, text="A")
    with pytest.raises(RuntimeError):
        _gate(ep).choose("Tür?", ["roman", "öykü"])
    assert [k for k, _, _ in ep.requests] == ["complete"], "model yokken düz metinle ikinci kez beklenmemeli"


# ---------------------------------------------------------------------------------------------- bilinmeyen cevap
def test_unknown_answer_gives_no_choice():
    r = _gate(TextOnly("Bilmiyorum, ikisi de olabilir.")).choose("Tür?", ["roman", "öykü"])
    assert r.choice is None and r.index is None and r.method == C.NONE and r.probs is None
    assert r.raw == "Bilmiyorum, ikisi de olabilir." and not r.confident(0.0)


def test_unmappable_structured_answer_is_asked_once_more_as_text():
    ep = Endpoint({"roman": 1.0}, logprobs=False, content="Bu", text="emin değilim")
    r = _gate(ep).choose("Tür?", ["roman", "öykü"])
    assert r.choice is None and r.method == C.NONE and r.calls == 2
    assert [k for k, _, _ in ep.requests] == ["complete", "chat"]


OPTS = ["Roman", "Öykü", "Irmak Dizisi", "E-kitap", "Şiir"]


@pytest.mark.parametrize("text,index", [
    ("B", 1), ("(C)", 2), ("D)", 3), ("  **A**  ", 0), ("Cevap: E", 4), ("yanıt: b", None),
    ("ırmak dizisi", 2), ("IRMAK DİZİSİ", 2), ("E-kitap", 3), ("B) Öykü", 1),
    ("<think>uzun düşünce</think>B", 1), ("<think>bitmeyen düşünce", None),
    ("Roman değil", None), ("A veya B", None), ("F", None), ("", None),
])
def test_text_is_matched_only_when_unambiguous(text, index):
    assert C.match_text(text, OPTS) == index


# ---------------------------------------------------------------------------------------------- eleme turu
def test_more_choices_than_labels_are_decided_in_rounds():
    opts = [f"Kategori {i:02d}" for i in range(60)]
    weights = {o: 0.01 for o in opts}
    weights[opts[45]] = 0.5
    ep = Endpoint(weights)
    r = _gate(ep).choose("Hangi kategori?", opts)
    assert r.choice == opts[45] and r.index == 45 and r.method == C.LOGPROBS
    assert [len(b["structured_outputs"]["choice"]) for _, _, b in ep.requests] == [20, 20, 20, 3]
    assert r.calls == 4 and len(r.probs) == 60
    assert sum(r.probs.values()) == pytest.approx(1.0)
    # P(c) = P(grup içinde c) × P(finalde grubunun galibi)
    assert r.probs[opts[45]] == pytest.approx((0.5 / 0.69) * (0.5 / 0.52))
    assert r.margin > 0


def test_groups_are_balanced():
    assert [len(g) for g in C.split_groups([str(i) for i in range(26)])] == [26]
    assert [len(g) for g in C.split_groups([str(i) for i in range(27)])] == [14, 13]
    assert [len(g) for g in C.split_groups([str(i) for i in range(100)])] == [25, 25, 25, 25]


# ---------------------------------------------------------------------------------------------- girdi
def test_one_choice_needs_no_model():
    ep = Endpoint()
    r = _gate(ep).choose("Tür?", ["roman"])
    assert r.choice == "roman" and r.method == C.SINGLE and r.probability == 1.0 and r.calls == 0
    assert ep.requests == []


@pytest.mark.parametrize("choices", [[], ["a", "a"], "roman", ["a", "  "]])
def test_bad_choices_are_refused(choices):
    with pytest.raises(ValueError):
        _gate(Endpoint()).choose("Tür?", choices)


# ---------------------------------------------------------------------------------------------- kapı sırası
@pytest.fixture
def queue_store(tmp_path):
    return open_store(f"sqlite:///{tmp_path}/queue.db")


def test_choose_waits_its_turn_in_the_gate(queue_store):
    ep = Endpoint({"evet": 0.9, "hayır": 0.1}, delay=0.15, text="ok")
    base = QueuedLlm(ep, LlmQueue(queue_store.engine, slots=1, poll_seconds=0.02))
    categories = base.for_module("categories")
    results: dict[int, object] = {}

    def ask(i):
        if i % 2:
            results[i] = categories.choose(f"soru-{i}", ["evet", "hayır"])
        else:
            results[i] = base.chat([{"role": "user", "content": f"soru-{i}"}])

    threads = []
    for i in range(4):
        t = threading.Thread(target=ask, args=(i,))
        threads.append(t)
        t.start()
        time.sleep(0.05)              # geliş sırası kapının sırasıdır
    for t in threads:
        t.join(timeout=20)
    assert len(results) == 4 and results[1].choice == "evet" and results[0] == "ok"
    assert ep.max_concurrent == 1, "seçim çağrısı kapının slot sınırını deldi"
    assert ep.order == [f"soru-{i}" for i in range(4)], "seçim çağrısı sırayı atladı"
    with queue_store.engine.connect() as conn:
        rows = conn.execute(sa.select(S.sl_llm_queue.c.module, S.sl_llm_queue.c.status)).all()
    assert sorted(m for m, _ in rows) == ["categories", "categories", "nl2sql", "nl2sql"]
    assert {s for _, s in rows} == {"DONE"}


def test_fallback_stays_on_the_same_ticket(queue_store):
    ep = Endpoint(fail=LlmHttpError(422, "logprobs"), text="A")
    llm = QueuedLlm(ep, LlmQueue(queue_store.engine, slots=1, poll_seconds=0.02), purpose="bg:categories")
    r = llm.choose("Tür?", ["roman", "öykü"])
    assert r.choice == "roman" and r.calls == 2
    with queue_store.engine.connect() as conn:
        rows = conn.execute(sa.select(S.sl_llm_queue.c.module, S.sl_llm_queue.c.priority, S.sl_llm_queue.c.status)).all()
    assert [tuple(row) for row in rows] == [("categories", 2, "DONE")], "yedek çağrı ikinci bilet almamalı"
