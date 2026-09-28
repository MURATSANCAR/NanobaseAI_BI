"""Yavaş ekran verisi için hazır cevap katmanı.

Sözleşme: yalnız yavaş JSON GET saklanır; anahtar kişi + yol + sorgu (bir kişinin cevabı başkasına gitmez);
5 dk içinde hazır cevap döner, bayatsa döner ve arkada yenilenir; «Yenile» (X-Data-Refresh, ?refresh=true) beklemeden
kaynaktan okur; bir modülde başarılı yazma o modülün hazır cevaplarını düşürür; sohbet, yetki, yoklama ve dosya
yolları hiç saklanmaz; oturumsuz istek saklanmaz.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from semantic_bridge import response_cache as RC


def test_paths_and_keys():
    assert RC.cacheable_path("/api/v1/seo-geo/overview")
    for p in ("/api/v1/ask", "/api/v1/ask/stream", "/api/v1/admin/overview", "/api/v1/me/profile", "/api/v1/rooms/now",
              "/api/v1/editorial/studio/jobs/x", "/api/v1/board/export.xlsx", "/api/v1/editorial/authors/snapshot",
              "/api/v1/reports/run-due", "/api/v1/people/ayse/photo", "/health", "/api/v1/editorial/ask/covers/abc"):
        assert not RC.cacheable_path(p), p
    assert RC.cacheable_path("/api/v1/people")
    assert RC.module_of("/api/v1/seo-geo/products/1/propose") == "/api/v1/seo-geo"
    assert RC.module_of("/api/v1/editorial/contracts/records/9") == "/api/v1/editorial/contracts"
    assert RC.norm_query("b=2&a=1&_=99&refresh=true") == "a=1&b=2"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(RC, "SLOW_SECONDS", 0.05)
    counters = {"slow": 0, "fast": 0}
    app = FastAPI()
    cache = RC.ResponseCache()
    users = {"timas_session=a": "ayse", "timas_session=m": "mehmet"}

    def user_of(cookie):
        if cookie not in users:
            raise RuntimeError("oturum yok")
        return users[cookie]

    RC.install(app, cache, user_of, lambda: True)

    @app.get("/api/v1/mod/slow")
    def slow(x: str = ""):
        counters["slow"] += 1
        time.sleep(0.1)
        return {"n": counters["slow"], "x": x}

    @app.get("/api/v1/mod/fast")
    def fast():
        counters["fast"] += 1
        return {"n": counters["fast"]}

    @app.post("/api/v1/mod/items")
    def write():
        return {"ok": True}

    @app.post("/api/v1/other/items")
    def other():
        return {"ok": True}

    @app.get("/api/v1/ask/slow")
    def ask():
        time.sleep(0.1)
        counters["slow"] += 1
        return {"n": counters["slow"]}

    return app, cache, counters


def test_slow_answers_are_ready_fast_ones_untouched(app):
    app_, cache, c = app
    cl = TestClient(app_)
    a = {"cookie": "timas_session=a"}
    assert cl.get("/api/v1/mod/slow", headers=a).json()["n"] == 1
    r = cl.get("/api/v1/mod/slow", headers=a)
    assert r.json()["n"] == 1 and r.headers["x-data-cached"] == "1" and c["slow"] == 1
    assert cl.get("/api/v1/mod/slow?x=2", headers=a).json()["n"] == 2          # başka sorgu, başka kayıt
    assert cl.get("/api/v1/mod/fast", headers=a).json()["n"] == 1
    assert cl.get("/api/v1/mod/fast", headers=a).json()["n"] == 2              # hızlı uç saklanmaz
    assert cl.get("/api/v1/mod/slow", headers={"cookie": "timas_session=m"}).json()["n"] == 3   # başka kişi
    assert cl.get("/api/v1/mod/slow").json()["n"] == 4                         # oturumsuz: saklanmaz
    assert cl.get("/api/v1/ask/slow", headers=a).json()["n"] == 5
    assert cl.get("/api/v1/ask/slow", headers=a).json()["n"] == 6              # sohbet hiç saklanmaz


def test_refresh_and_writes(app):
    app_, cache, c = app
    cl = TestClient(app_)
    a = {"cookie": "timas_session=a"}
    cl.get("/api/v1/mod/slow", headers=a)
    assert cl.get("/api/v1/mod/slow", headers={**a, "x-data-refresh": "1"}).json()["n"] == 2
    assert cl.get("/api/v1/mod/slow", headers=a).json()["n"] == 2              # yenilenen kayıt saklandı
    assert cl.get("/api/v1/mod/slow?refresh=true", headers=a).json()["n"] == 3
    cl.post("/api/v1/other/items", headers=a)
    assert cl.get("/api/v1/mod/slow", headers=a).json()["n"] == 3              # başka modül yazdı: kayıt durur
    cl.post("/api/v1/mod/items", headers=a)
    assert cl.get("/api/v1/mod/slow", headers=a).json()["n"] == 4              # bu modül yazdı: kayıt düştü


def test_stale_answer_is_served_and_renewed_behind(app, monkeypatch):
    app_, cache, c = app
    with TestClient(app_) as cl:          # olay döngüsü açık kalsın: arka plan tazelemesi onda koşar
        _stale(cl, cache, c)


def _stale(cl, cache, c):
    a = {"cookie": "timas_session=a"}
    cl.get("/api/v1/mod/slow", headers=a)
    for e in cache._items.values():
        e.at -= RC.FRESH_SECONDS + 1
    r = cl.get("/api/v1/mod/slow", headers=a)
    assert r.json()["n"] == 1 and int(r.headers["x-data-age"]) >= RC.FRESH_SECONDS
    for _ in range(100):                      # arka plan tazelemesi kaydı yazana kadar
        if cache.view()["revalidated"] >= 1:
            break
        time.sleep(0.05)
    assert c["slow"] == 2
    assert cl.get("/api/v1/mod/slow", headers=a).json()["n"] == 2


def test_forgotten_entries_leave_and_due_skips_fresh():
    cache = RC.ResponseCache()
    cache.put(("u", "/api/v1/x", ""), b"{}", [], 200, 2.0, {"cookie": "timas_session=u"})
    assert cache.due() == []
    e = cache._items[("u", "/api/v1/x", "")]
    e.at -= RC.FRESH_SECONDS + 1
    assert len(cache.due()) == 1
    e.asked -= RC.KEEP_SECONDS + 1
    assert cache.due() == [] and cache.view()["entries"] == 0


def test_ready_answers_survive_a_restart_without_cookies(tmp_path):
    key = ("ayse", "/api/v1/mod/slow", "a=1")
    first = RC.ResponseCache(str(tmp_path))
    first.put(key, b'{"n": 1}', [("content-type", "application/json")], 200, 2.0, {"cookie": "timas_session=a"})
    import os
    assert all(oct(os.stat(p).st_mode)[-3:] == "600" for p in tmp_path.iterdir())
    assert not any(b"timas_session" in p.read_bytes() for p in tmp_path.iterdir())       # çerez diske gitmez
    again = RC.ResponseCache(str(tmp_path))                                              # yeniden başlatma
    e = again.get(key)
    assert e is not None and e.body == b'{"n": 1}' and e.replay == {} and again.view()["loaded"] == 1
    e.at -= RC.FRESH_SECONDS + 1
    assert again.due() == []              # çerezsiz kayıt arkada değil, kişinin açılışında tazelenir
    again.invalidate("/api/v1/mod")
    assert list(tmp_path.iterdir()) == [] and RC.ResponseCache(str(tmp_path)).get(key) is None
