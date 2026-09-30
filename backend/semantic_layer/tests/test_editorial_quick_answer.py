"""Kitaba sor hızlı yolu (2026-09-30): soru önce kart servisinin tek çağrılık yoluna gider; `handled` değilse ya da
yol hata verirse sohbet ajanına düşer. Seçili kitapta kart seçimi (kütüphane düzeyi) devreye girmez."""
from __future__ import annotations

import time

import pytest
import sqlalchemy as sa
from sqlalchemy.pool import StaticPool

from semantic_bridge import editorial_books as B
from semantic_bridge import editorial_cards as C


@pytest.fixture()
def engine(monkeypatch):
    e = sa.create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    B._md.create_all(e)
    monkeypatch.setenv("EDITOR_API_BASE", "http://motor")
    monkeypatch.setenv("EDITOR_API_KEY", "k")
    monkeypatch.setattr(B, "scope_reply", lambda q, chat=None: None)
    monkeypatch.setattr(B, "_citations_checked", lambda *a: None)
    monkeypatch.setattr(C, "character_graph", lambda *a: None)
    return e


def _wait(engine, qid):
    for _ in range(200):
        with engine.connect() as c:
            r = c.execute(sa.select(B.QUESTIONS).where(B.QUESTIONS.c.id == qid)).first()
        if r.status in ("bitti", "hata"):
            return r
        time.sleep(0.02)
    raise AssertionError("soru bitmedi")


def test_quick_answer_is_used_and_agent_is_not_called(engine, monkeypatch):
    seen = {}
    monkeypatch.setattr(C, "quick_answer", lambda q, t, h=None: seen.update(q=q, t=t) or
                        {"handled": True, "answer": "Hürdeniz [s.47].", "not_found": False})
    monkeypatch.setattr(B, "ask_engine", lambda *a, **k: pytest.fail("ajan çağrılmamalı"))
    out = B.ask(engine, "t", "u", "Karakterler kim?", book_key="k1", book_title="anne-terligi")
    r = _wait(engine, out["id"])
    assert r.status == "bitti" and r.answer == "Hürdeniz [s.47]." and seen == {"q": "Karakterler kim?", "t": "anne-terligi"}


@pytest.mark.parametrize("quick", [{"handled": False, "reason": "NEEDS_DEEPER_READ"}, RuntimeError("bağlantı yok")])
def test_falls_back_to_agent(engine, monkeypatch, quick):
    def fake(*a, **k):
        if isinstance(quick, Exception):
            raise quick
        return quick
    monkeypatch.setattr(C, "quick_answer", fake)
    monkeypatch.setattr(B, "ask_engine", lambda *a, **k: "Ajan cevabı [s.3].")
    out = B.ask(engine, "t", "u", "s.12'de ne oluyor?", book_key="k1", book_title="anne-terligi")
    r = _wait(engine, out["id"])
    assert r.status == "bitti" and r.answer == "Ajan cevabı [s.3]."


def test_selected_book_skips_card_selection(engine, monkeypatch):
    monkeypatch.setattr(C, "card_answer", lambda *a: pytest.fail("seçili kitapta kart seçimi yok"))
    monkeypatch.setattr(C, "quick_answer", lambda *a, **k: {"handled": True, "answer": "Öneririm [s.5]."})
    out = B.ask(engine, "t", "u", "Bu kitabı önerir misin?", book_key="k1", book_title="bocekleri-seven-kadin",
                chat=lambda *a, **k: '{"intent":"CARD"}')
    assert _wait(engine, out["id"]).answer == "Öneririm [s.5]."
