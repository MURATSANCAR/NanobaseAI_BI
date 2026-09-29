"""Hazır cevap ısıtması (hız 2. tur, 2026-09-29): bir ekranı ilk kez açan kişi beklemesin.

Sözleşme: son 3 günde herhangi birinin açtığı yavaş uçlar, son 3 günde gelmiş ve henüz hazır cevabı olmayan her kişi
için o kişinin iç kimliğiyle üretilir — kişiler arası paylaşım yok, her cevap kişinin kendi oturumuyla üretilir ve
yalnız onun anahtarına yazılır (farklı kişiler birbirinin cevabını görmez). Sayfa kapısı önceden sorulur; kapalıysa
istek atılmaz. Tek sıra, en çok `WARM_CONCURRENCY` eşzamanlı istek. Isıtılmış ama açılmamış cevap tazeleme turuna ve
«kaç kişi açtı» sayısına girmez. Arka plan tazelemesi kaydın istenme anını uzatmaz.
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from semantic_bridge import response_cache as RC

A, M, Z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=m"}, {"cookie": "timas_session=z"}


@pytest.fixture
def kur(monkeypatch):
    monkeypatch.setattr(RC, "SLOW_SECONDS", 0.05)
    app = FastAPI()
    cache = RC.ResponseCache()
    users = {"timas_session=a": "ayse", "timas_session=m": "mehmet", "timas_session=z": "zeynep"}
    st = {"now": 0, "max": 0, "calls": [], "closed": set()}

    def session_of(cookie):
        s = cache.resolve_internal(cookie)
        if s:
            return s
        u = users.get(cookie)
        return {"username": u, "displayName": u.title()} if u else None

    def user_of(cookie):
        s = session_of(cookie)
        if not s:
            raise RuntimeError("oturum yok")
        return s["username"]

    RC.install(app, cache, user_of, lambda: True, session_of=session_of)
    cache.may_open = lambda user, path: (user, path) not in st["closed"]

    async def slow_body(request: Request, what: str):
        who = user_of(request.headers.get("cookie", ""))
        st["calls"].append((who, what))
        st["now"] += 1
        st["max"] = max(st["max"], st["now"])
        await asyncio.sleep(0.1)
        st["now"] -= 1
        # Cevap kişiye göre değişir (kapsam): kişi kendi satırlarını görür.
        return {"kim": who, "satirlar": [f"{who}-{what}-{i}" for i in range(3)]}

    @app.get("/api/v1/mod/slow")
    async def slow(request: Request):
        return await slow_body(request, "slow")

    @app.get("/api/v1/mod/other")
    async def other(request: Request, x: str = ""):
        return await slow_body(request, "other" + x)

    @app.get("/api/v1/mod/fast")
    def fast(request: Request):
        st["calls"].append((user_of(request.headers.get("cookie", "")), "fast"))
        return {"ok": True}

    return app, cache, st


def _run(cache, plan):
    asyncio.run(cache.warm_round(plan))


def test_plan_covers_known_people_without_their_own_answer(kur):
    app, cache, st = kur
    cl = TestClient(app)
    assert cl.get("/api/v1/mod/slow", headers=A).json()["kim"] == "ayse"      # ayşe açtı (yavaş, saklandı)
    cl.get("/api/v1/mod/fast", headers=M)                                     # mehmet geldi ama bu ekranı açmadı
    assert cache.warm_plan() == [("mehmet", "/api/v1/mod/slow", "")]          # zeynep hiç gelmedi: iç kimliği yok
    cache.seen["mehmet"] = time.time() - RC.KEEP_SECONDS - 1                  # 3 günden önce gelmiş: ısıtılmaz
    assert cache.warm_plan() == []


def test_warmed_answer_is_the_persons_own_and_never_anothers(kur):
    app, cache, st = kur
    cl = TestClient(app)
    cl.get("/api/v1/mod/slow", headers=A)
    cl.get("/api/v1/mod/fast", headers=M)
    _run(cache, cache.warm_plan())
    assert ("mehmet", "slow") in st["calls"] and cache.stats["warmed"] == 1
    e = cache.peek(("mehmet", "/api/v1/mod/slow", ""))
    assert e is not None and not e.real
    assert json.loads(e.body)["kim"] == "mehmet"                              # kendi kimliğiyle üretildi
    n = len(st["calls"])
    r = cl.get("/api/v1/mod/slow", headers=M)                                 # ilk açılış beklemez
    assert r.headers.get("x-data-cached") == "1" and len(st["calls"]) == n
    body = r.json()
    assert body["kim"] == "mehmet" and all(s.startswith("mehmet-") for s in body["satirlar"])
    assert cache.peek(("mehmet", "/api/v1/mod/slow", "")).real                # artık kişinin kendi isteği
    a = cl.get("/api/v1/mod/slow", headers=A).json()
    assert a["kim"] == "ayse" and all(s.startswith("ayse-") for s in a["satirlar"])


def test_closed_page_is_not_requested_and_not_retried(kur):
    app, cache, st = kur
    cl = TestClient(app)
    cl.get("/api/v1/mod/slow", headers=A)
    cl.get("/api/v1/mod/fast", headers=M)
    st["closed"].add(("mehmet", "/api/v1/mod/slow"))
    n = len(st["calls"])
    _run(cache, cache.warm_plan())
    assert len(st["calls"]) == n and cache.peek(("mehmet", "/api/v1/mod/slow", "")) is None
    assert cache.warm_plan() == []                                            # 3 gün yeniden denenmez


def test_fast_answer_is_not_stored_and_not_retried(kur, monkeypatch):
    app, cache, st = kur
    cl = TestClient(app)
    cl.get("/api/v1/mod/slow", headers=A)
    cl.get("/api/v1/mod/fast", headers=M)
    monkeypatch.setattr(RC, "SLOW_SECONDS", 5)                                # mehmet için hızlı çıkar
    _run(cache, cache.warm_plan())
    assert cache.peek(("mehmet", "/api/v1/mod/slow", "")) is None and cache.warm_plan() == []


def test_concurrency_limit_and_popular_first(kur, monkeypatch):
    app, cache, st = kur
    cl = TestClient(app)
    for x in ("1", "2", "3"):
        cl.get(f"/api/v1/mod/other?x={x}", headers=A)
    cl.get("/api/v1/mod/other?x=3", headers=Z)                                # x=3'ü iki kişi açtı
    cl.get("/api/v1/mod/fast", headers=M)
    plan = cache.warm_plan()
    assert plan[0] == ("mehmet", "/api/v1/mod/other", "x=3")                  # çok açılan önce
    assert len(plan) == 5                                                     # x=3: mehmet; x=1, x=2: mehmet+zeynep
    assert len(cache.warm_plan(min_people=2)) == 1
    st["max"] = 0
    monkeypatch.setattr(RC, "WARM_CONCURRENCY", 2)
    _run(cache, plan)
    assert st["max"] <= 2 and cache.stats["warmed"] == len(plan)


def test_warmed_unopened_answers_do_not_count_or_refresh(kur):
    app, cache, st = kur
    cl = TestClient(app)
    cl.get("/api/v1/mod/slow", headers=A)
    cl.get("/api/v1/mod/fast", headers=M)
    cl.get("/api/v1/mod/fast", headers=Z)
    _run(cache, [("mehmet", "/api/v1/mod/slow", "")])
    # Yalnız ayşe açtı: mehmet'in ısıtılmış kaydı «açan» sayılmaz.
    assert cache.warm_plan(min_people=2) == []
    for e in cache._items.values():
        e.at = RC.last_refresh() - 1
    assert [k[0] for k, _ in cache.due()] == ["ayse"]                        # ısıtılmış kayıt tazelenmez
    assert ("mehmet", "/api/v1/mod/slow", "") in cache.warm_plan()           # ertesi ısıtma yeniler


def test_revalidation_does_not_extend_asked(kur):
    app, cache, st = kur
    cl = TestClient(app)
    cl.get("/api/v1/mod/slow", headers=A)
    key = ("ayse", "/api/v1/mod/slow", "")
    cache._items[key].asked -= 1000
    asked = cache._items[key].asked
    r = cl.get("/api/v1/mod/slow", headers={**A, RC.REVALIDATE_HEADER: cache.secret})
    assert r.status_code == 200 and cache.peek(key).asked == asked


def test_warm_slot_once_and_not_late(tmp_path, monkeypatch):
    monkeypatch.setattr(RC, "WARM_TIMES", ((7, 0),))
    cache = RC.ResponseCache(str(tmp_path))
    assert cache.warm_slot_due() is None                                      # yeni kurulum: ilk tur ertesi saatte
    from datetime import datetime
    slot = datetime(2026, 9, 30, 7, 0, tzinfo=RC.TZ).timestamp()
    cache.warm_done = slot - 86400
    assert cache.warm_slot_due(slot + 60) == slot
    assert cache.warm_slot_due(slot + RC.WARM_LATE + 1) is None               # köprü geç kalktı: o gün yok
    cache.warm_mark(slot)
    assert cache.warm_slot_due(slot + 60) is None
    assert RC.ResponseCache(str(tmp_path)).warm_done == slot                  # yeniden başlatmada ikinci kez yok


def test_seen_is_kept_on_disk_without_changing_identity(tmp_path):
    cache = RC.ResponseCache(str(tmp_path))
    cache.remember({"username": "Ayse", "displayName": "Ayşe"}, now=1000.0)
    again = RC.ResponseCache(str(tmp_path))
    assert again.seen["ayse"] == 1000.0
    assert again.resolve_internal(again.internal_cookie("ayse")) == {"username": "Ayse", "displayName": "Ayşe"}
