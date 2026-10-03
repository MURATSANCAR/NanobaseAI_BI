"""Kitaba sor: soru yalnız kart servisine gider (editor.quick_answer: en çok iki model çağrısı). Cevap gelmezse soru
hata olarak kapanır, başka yola düşmez (sohbet ajanı 2026-10-03'te kaldırıldı). Seçili kitapta kart seçimi (kütüphane
düzeyi) devreye girmez."""
from __future__ import annotations

import time

import pytest
import sqlalchemy as sa

from semantic_bridge import editorial_books as B
from semantic_bridge import editorial_cards as C


@pytest.fixture()
def engine(monkeypatch, tmp_path):
    # Dosya veritabanı, iş parçacığı başına bağlantı: soru iş parçacığı ile bekleyen test tek SQLite bağlantısını
    # (StaticPool) aynı anda kullanınca iş parçacığı ara sıra düşüyor, soru «bitmedi» kalıyordu.
    e = sa.create_engine(f"sqlite:///{tmp_path / 'sorular.db'}", connect_args={"timeout": 30})
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


def _open_row(engine, qid, minutes_ago, status="calisiyor"):
    from datetime import datetime, timedelta, timezone
    with engine.begin() as c:
        c.execute(sa.insert(B.QUESTIONS).values(
            id=qid, tenant_id="t", username="u", book_key="k1", book_title="anne-terligi", question="Kim?",
            status=status, created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)))


def test_restart_asks_the_interrupted_question_again_once(engine, monkeypatch):
    from datetime import datetime, timedelta, timezone
    calls = []
    monkeypatch.setattr(C, "quick_answer", lambda q, t, h=None: calls.append(q) or
                        {"handled": True, "answer": "Hürdeniz [s.47]."})
    _open_row(engine, "yarim", 3)
    _open_row(engine, "eski", 90, status="bekliyor")
    monkeypatch.setattr(B, "_BOOT", datetime.now(timezone.utc) - timedelta(minutes=1))
    _open_row(engine, "yeni", 0)          # bu süreç başladıktan sonra açılmış: başka işçinin, dokunulmaz
    out = B.resume_stale(engine)
    assert out == {"resumed": 1, "expired": 1}
    assert _wait(engine, "yarim").answer == "Hürdeniz [s.47]."
    with engine.connect() as c:
        rows = {r.id: r for r in c.execute(sa.select(B.QUESTIONS))}
    assert rows["eski"].status == "hata" and rows["eski"].error == B.STALE_ERROR
    assert rows["yeni"].status == "calisiyor"
    assert B.resume_stale(engine) == {"resumed": 0, "expired": 0} and calls == ["Kim?"]   # ikinci işçi almaz


def test_restart_does_not_take_a_question_another_worker_just_claimed(engine, monkeypatch):
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(C, "quick_answer", lambda *a, **k: pytest.fail("üstlenilmiş soru yeniden sorulmaz"))
    _open_row(engine, "alindi", 2)
    with engine.begin() as c:
        c.execute(sa.update(B.QUESTIONS).where(B.QUESTIONS.c.id == "alindi").values(
            resumed_at=datetime.now(timezone.utc) - timedelta(seconds=30)))
    monkeypatch.setattr(B, "_BOOT", datetime.now(timezone.utc))
    assert B.resume_stale(engine) == {"resumed": 0, "expired": 0}
