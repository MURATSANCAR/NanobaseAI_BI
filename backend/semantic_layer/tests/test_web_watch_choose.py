"""Basın ve web etiketi (README «hemen düzeltilecekler» 8): serbest cevap kelimeyle ayrıştırılmaz; `QueuedLlm.choose`
kapalı küme (olumlu / olumsuz / nötr / ilgisiz) + olasılık eşiği. Eşik altı, olasılıksız yedek yol ve eşlenemeyen cevap
«emin değil» olarak saklanır (yeniden sorulmaz) ve ekranda gösterilmez.

Ağ yok: akışlar, robots.txt ve Wikidata taklit edilir.
"""

from __future__ import annotations

import json
import uuid

import pytest

from semantic_bridge import web_watch as W
from semantic_layer.runtime.llm_choose import Choice
from semantic_layer.store.catalog_store import open_store

T = "t1"


class Llm:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def choose(self, prompt, choices):
        self.calls.append((prompt, list(choices)))
        return self.answers.pop(0)

    def chat(self, *a, **k):  # eski yol kullanılmamalı
        raise AssertionError("serbest metin cevabı istenmemeli")


def _c(choice, p, margin, method="logprobs"):
    probs = None if p is None else {choice: p, "diğer": 1 - p}
    return Choice(choice, 0 if choice else None, probs, method, margin)


def test_ask_uses_closed_set_and_threshold():
    llm = Llm([_c("olumsuz", 0.9, 0.8)])
    label, note = W.ask(llm, "Ayşe Yılmaz", [{"title": "Deniz"}], "Başlık", "Özet")
    assert label == "olumsuz" and "p=0.90" in note
    prompt, choices = llm.calls[0]
    assert choices == ["olumlu", "olumsuz", "nötr", "ilgisiz"] and "tek kelime" not in prompt and "«Deniz»" in prompt
    assert W.ask(Llm([_c("nötr", 0.95, 0.9)]), "A B", [], "t", None)[0] == "notr"


@pytest.mark.parametrize("ch", [_c("olumlu", 0.6, 0.5), _c("olumlu", 0.8, 0.1), _c("olumlu", None, None, "text"),
                                _c(None, None, None, "none")])
def test_ask_below_threshold_or_without_probability_is_unsure(ch):
    label, note = W.ask(Llm([ch]), "A B", [], "t", None)
    assert label == W.UNSURE and label not in W.SHOWN and len(label) <= 12
    if ch.choice:
        assert "en olası olumlu" in note


def test_thresholds_from_settings():
    assert W.thresholds(lambda k: "") == (0.70, 0.30)
    assert W.thresholds(lambda k: {"WEB_WATCH_MIN_PROB": "0,8", "WEB_WATCH_MIN_MARGIN": "x"}.get(k, "")) == (0.8, 0.30)


def test_run_labels_pending_mentions_and_hides_unsure(monkeypatch):
    e = open_store("sqlite://").engine
    W._ready.discard(id(e))
    W.ensure(e)
    monkeypatch.setattr(W, "FEEDS", ())
    monkeypatch.setattr(W, "allowed", lambda url: False)
    ids = []
    with e.begin() as c:
        for i in range(3):
            iid = uuid.uuid4().hex
            c.execute(W.ITEMS.insert().values(id=iid, tenant_id=T, source="x", url=f"https://h/{i}", title=f"Haber {i}",
                                              summary="s", fetched_at=W._now()))
            mid = uuid.uuid4().hex
            ids.append(mid)
            c.execute(W.MENTIONS.insert().values(id=mid, tenant_id=T, item_id=iid, contact_id="c1", author="Ayşe Yılmaz",
                                                 books_json="[]", created_at=W._now()))
    llm = Llm([_c("olumlu", 0.9, 0.85), _c("olumsuz", 0.55, 0.2), _c("ilgisiz", 0.95, 0.9)])
    rep = W.run_due(e, T, lambda sql: [], "Timas_MSCRM.dbo", llm, budget_seconds=60)
    assert rep["labelled"] == 3 and rep["unsure"] == 1
    with e.connect() as c:
        rows = {r.id: r for r in c.execute(W.MENTIONS.select())}
    assert [rows[m].label for m in ids] == ["olumlu", W.UNSURE, "ilgisiz"]
    assert rows[ids[1]].label_note.startswith("p=0.55")
    shown, total = W._mention_rows(e, T, [], 0, None)
    assert total == 1 and shown[0]["label"] == "olumlu"
    # etiketlenenler yeniden sorulmaz
    again = Llm([])
    assert W.run_due(e, T, lambda sql: [], "Timas_MSCRM.dbo", again, budget_seconds=60)["labelled"] == 0 and again.calls == []


def test_model_error_leaves_mentions_for_next_run(monkeypatch):
    e = open_store("sqlite://").engine
    W._ready.discard(id(e))
    W.ensure(e)
    monkeypatch.setattr(W, "FEEDS", ())
    monkeypatch.setattr(W, "allowed", lambda url: False)
    with e.begin() as c:
        c.execute(W.ITEMS.insert().values(id="i1", tenant_id=T, source="x", url="https://h/1", title="H", fetched_at=W._now()))
        c.execute(W.MENTIONS.insert().values(id="m1", tenant_id=T, item_id="i1", contact_id="c1", author="A B",
                                             books_json=json.dumps([]), created_at=W._now()))

    class Down:
        def choose(self, *a):
            raise RuntimeError("kapı kapalı")

    rep = W.run_due(e, T, lambda sql: [], "S.dbo", Down(), budget_seconds=60)
    assert rep["labelled"] == 0 and any(x.startswith("model:") for x in rep["errors"])
    with e.connect() as c:
        assert c.execute(W.MENTIONS.select()).first().label is None
