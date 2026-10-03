"""Kitaba sor: soru yalnız kart servisine gider (editor.quick_answer: en çok iki model çağrısı). Cevap gelmezse soru
hata olarak kapanır, başka yola düşmez (sohbet ajanı 2026-10-03'te kaldırıldı). Seçili kitapta kart seçimi (kütüphane
düzeyi) devreye girmez."""
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
    monkeypatch.setenv("EDITOR_CATALOG_BASE", "http://kartlar")
    monkeypatch.setenv("EDITOR_CATALOG_KEY", "k")
    monkeypatch.setattr(B, "scope_reply", lambda q, chat=None, book_title=None: None)
    monkeypatch.setattr(B, "_citations_checked", lambda *a: None)
    monkeypatch.setattr(C, "character_graph", lambda *a: None)
    return e


def _wait(engine, qid):
    for _ in range(1000):  # 20 sn: soğuk başlangıçta soru iş parçacığı 4 sn'yi aşabiliyor
        with engine.connect() as c:
            r = c.execute(sa.select(B.QUESTIONS).where(B.QUESTIONS.c.id == qid)).first()
        if r.status in ("bitti", "hata"):
            return r
        time.sleep(0.02)
    raise AssertionError("soru bitmedi")


def test_answer_comes_from_card_service(engine, monkeypatch):
    seen = {}
    monkeypatch.setattr(C, "quick_answer", lambda q, t, h=None: seen.update(q=q, t=t) or
                        {"handled": True, "answer": "Hürdeniz [s.47].", "not_found": False})
    out = B.ask(engine, "t", "u", "Karakterler kim?", book_key="k1", book_title="anne-terligi")
    r = _wait(engine, out["id"])
    assert r.status == "bitti" and r.answer == "Hürdeniz [s.47]." and seen == {"q": "Karakterler kim?", "t": "anne-terligi"}


@pytest.mark.parametrize("quick", [{"handled": False, "reason": "MODEL_UNAVAILABLE"}, RuntimeError("bağlantı yok")])
def test_unanswered_question_closes_as_error_without_another_path(engine, monkeypatch, quick):
    def fake(*a, **k):
        if isinstance(quick, Exception):
            raise quick
        return quick
    monkeypatch.setattr(C, "quick_answer", fake)
    out = B.ask(engine, "t", "u", "s.12'de ne oluyor?", book_key="k1", book_title="anne-terligi")
    r = _wait(engine, out["id"])
    assert r.status == "hata" and r.answer is None and r.error == B.UNAVAILABLE
    assert not hasattr(B, "ask_engine")


def test_no_read_books_is_said_plainly(engine, monkeypatch):
    monkeypatch.setattr(C, "quick_answer", lambda *a, **k: {"handled": False, "reason": "NO_BOOKS", "books": []})
    out = B.ask(engine, "t", "u", "Karakterler kim?", book_key="k1", book_title="anne-terligi")
    r = _wait(engine, out["id"])
    assert r.status == "bitti" and r.answer == B.NO_BOOKS and r.not_found is True


def test_selected_book_skips_card_selection(engine, monkeypatch):
    monkeypatch.setattr(C, "card_answer", lambda *a: pytest.fail("seçili kitapta kart seçimi yok"))
    monkeypatch.setattr(C, "quick_answer", lambda *a, **k: {"handled": True, "answer": "Öneririm [s.5]."})
    out = B.ask(engine, "t", "u", "Bu kitabı önerir misin?", book_key="k1", book_title="bocekleri-seven-kadin",
                chat=lambda *a, **k: '{"intent":"CARD"}')
    assert _wait(engine, out["id"]).answer == "Öneririm [s.5]."
