"""Yavaş ekran verisi için hazır cevap katmanı.

Sözleşme: yalnız yavaş JSON GET saklanır; anahtar kişi + yol + sorgu (bir kişinin cevabı başkasına gitmez);
5 dk içinde hazır cevap döner, bayatsa döner ve arkada yenilenir; «Yenile» (X-Data-Refresh, ?refresh=true) beklemeden
kaynaktan okur; bir modülde başarılı yazma o modülün hazır cevaplarını düşürür; sohbet, yetki, yoklama ve dosya
yolları hiç saklanmaz; oturumsuz istek saklanmaz.
"""

from __future__ import annotations

import json
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
    # Kitaba sor: soru ve soru listesi hiç saklanmaz (bekleyen cevap donuyordu); kitap listesi/katalog saklanabilir.
    assert not RC.cacheable_path("/api/v1/editorial/ask")
    assert not RC.cacheable_path("/api/v1/editorial/ask/20437294592646eaa80ea7ed088aa08b")
    assert RC.cacheable_path("/api/v1/editorial/ask/books")
    assert RC.cacheable_path("/api/v1/editorial/ask/catalog")
    assert RC.module_of("/api/v1/seo-geo/products/1/propose") == "/api/v1/seo-geo"
    assert RC.module_of("/api/v1/editorial/contracts/records/9") == "/api/v1/editorial/contracts"
    # Redaksiyon: dosya kaldırma ve dosyadan eser, eser uçlarının hazır cevaplarını düşürür.
    assert RC.module_of("/api/v1/editorial/files/abc/remove") == "/api/v1/editorial/works"
    assert RC.module_of("/api/v1/editorial/works-from-file") == "/api/v1/editorial/works"
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
        e.at = RC.last_refresh() - 1
    r = cl.get("/api/v1/mod/slow", headers=a)
    assert r.json()["n"] == 1 and int(r.headers["x-data-age"]) >= 1
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
    e.at = RC.last_refresh() - 1
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
    e.at = RC.last_refresh() - 1
    assert again.due() == []              # çerezsiz kayıt arkada değil, kişinin açılışında tazelenir
    again.invalidate("/api/v1/mod")
    assert list(tmp_path.iterdir()) == [] and RC.ResponseCache(str(tmp_path)).get(key) is None


def test_disk_answer_of_a_path_excluded_later_is_not_loaded(tmp_path):
    """Yol sonradan saklanmayanlara alındıysa diskteki eski kayıt yüklenmez (arkada her turda tazelenmez) ve silinir."""
    key = ("ayse", "/api/v1/editorial/contracts/compare/meta", "")
    first = RC.ResponseCache(str(tmp_path))
    first.put(key, b'{"n": 1}', [("content-type", "application/json")], 200, 2.0, {})
    again = RC.ResponseCache(str(tmp_path))
    assert again.get(key) is None and again.due() == [] and list(tmp_path.glob("*.meta.json")) == []


def test_disk_answers_of_another_code_version_are_stale(tmp_path, monkeypatch):
    """Kurulumdan sonra eski kodun diskteki hazır cevabı kaybolmaz ama bayattır: hemen gelir, arkada yeniden üretilir."""
    key = ("ayse", "/api/v1/stock/overview", "")
    first = RC.ResponseCache(str(tmp_path))
    first.put(key, b'{"n": 1}', [("content-type", "application/json")], 200, 2.0, {})
    assert RC.ResponseCache(str(tmp_path)).get(key) is not None          # aynı kod: yeniden başlatmada kalır
    monkeypatch.setattr(RC, "CODE_VERSION", "baska-surum")
    again = RC.ResponseCache(str(tmp_path))
    e = again.get(key)
    assert e is not None and e.body == b'{"n": 1}' and RC.is_stale(e.at)


def test_refresh_is_at_seven_and_noon_istanbul():
    """Hazır cevap her gün 07:00 ve 12:00'de (İstanbul) tazelenir; arada 5 dakikada bir değil."""
    from datetime import datetime

    def ts(h, m):
        return datetime(2026, 9, 29, h, m, tzinfo=RC.TZ).timestamp()

    assert RC.REFRESH_TIMES == ((7, 0), (12, 0))
    assert RC.last_refresh(ts(9, 30)) == ts(7, 0)
    assert RC.last_refresh(ts(12, 0)) == ts(12, 0)
    assert RC.last_refresh(ts(23, 59)) == ts(12, 0)
    assert RC.last_refresh(ts(6, 59)) == datetime(2026, 9, 28, 12, 0, tzinfo=RC.TZ).timestamp()
    assert not RC.is_stale(ts(7, 5), ts(11, 59))       # 07:05'te üretilen, 12:00'ye kadar taze
    assert RC.is_stale(ts(7, 5), ts(12, 1))            # 12:00'den sonra bayat
    assert RC.is_stale(ts(11, 0), ts(7, 0) + 86400)    # ertesi sabah 07:00'de bayat


def test_internal_identity_needs_this_process_secret(tmp_path):
    """Arka plan tazelemesinin iç çerezi yalnız bu süreçteki gizli değerle geçer; kişi kaydında çerez yok."""
    cache = RC.ResponseCache(str(tmp_path))
    cache.remember({"username": "Ayse", "displayName": "Ayşe Y.", "token": "gizli"})
    ok = cache.resolve_internal(cache.internal_cookie("Ayse"))
    assert ok == {"username": "Ayse", "displayName": "Ayşe Y."}
    assert cache.resolve_internal(f"{cache.INTERNAL_PREFIX}yanlis.Ayse") is None          # başka gizli değer
    assert cache.resolve_internal(cache.internal_cookie("bilinmeyen")) is None            # kaydı olmayan kişi
    assert cache.resolve_internal("timas_session=a") is None                              # gerçek çerez burada çözülmez
    other = RC.ResponseCache(str(tmp_path))                                                # yeniden başlatma: yeni gizli değer
    assert other.resolve_internal(cache.internal_cookie("Ayse")) is None
    assert other.people["ayse"]["displayName"] == "Ayşe Y."                               # kimlik diskten gelir
    assert b"gizli" not in (tmp_path / "people.json").read_bytes()


def test_board_session_uses_internal_identity_only_with_hook(monkeypatch):
    from semantic_bridge import board as B

    cache = RC.ResponseCache()
    cache.remember({"username": "ayse", "displayName": "Ayşe"})
    monkeypatch.setattr(B, "internal_session", None)
    monkeypatch.setattr(B, "_sessions", {})
    monkeypatch.setattr(B.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("yok")))
    assert B._fetch_session(cache.internal_cookie("ayse")) is None         # kanca yokken giriş servisine gider
    monkeypatch.setattr(B, "internal_session", cache.resolve_internal)
    assert B.user_of(cache.internal_cookie("ayse")) == "ayse"


def test_after_restart_stale_entry_is_refreshed_with_internal_identity(tmp_path):
    """Yeniden başlatmadan sonra çerez bellekte yok; 07:00/12:00 tazelemesi iç kimlikle yine çalışır."""
    counters = {"n": 0}
    app = FastAPI()
    cache = RC.ResponseCache(str(tmp_path))
    cache.remember({"username": "ayse", "displayName": "Ayşe"})

    def user_of(cookie):
        s = cache.resolve_internal(cookie) or ({"username": "ayse"} if cookie == "timas_session=a" else None)
        if not s:
            raise RuntimeError("oturum yok")
        return s["username"]

    RC.install(app, cache, user_of, lambda: True)

    @app.get("/api/v1/mod/slow")
    def slow():
        counters["n"] += 1
        time.sleep(0.1)
        return {"n": counters["n"]}

    key = ("ayse", "/api/v1/mod/slow", "")
    cache.put(key, b'{"n": 0}', [("content-type", "application/json")], 200, 2.0, {})    # diskten gelmiş gibi: çerez yok
    cache._items[key].at = RC.last_refresh() - 1
    due = cache.due()
    assert [k for k, _ in due] == [key]
    import asyncio

    async def run():
        import httpx
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            h = {"cookie": cache.internal_cookie("ayse"), RC.REVALIDATE_HEADER: cache.secret}
            return await client.get("/api/v1/mod/slow", headers=h)

    r = asyncio.run(run())
    assert r.status_code == 200 and counters["n"] == 1
    assert json.loads(cache.get(key).body)["n"] == 1 and not RC.is_stale(cache.get(key).at)


def test_disk_dir_live_port_only():
    """Yan köprü (başka port) canlı klasöre yazmaz; açık klasör her zaman geçerli (2026-09-29, geri gelen test kaydı)."""
    live = ["uvicorn", "semantic_bridge.app:app", "--host", "127.0.0.1", "--port", "8795"]
    side = ["uvicorn", "semantic_bridge.app:app", "--host", "127.0.0.1", "--port", "8801"]
    assert RC.disk_dir({}, live) == RC.LIVE_DIR
    assert RC.disk_dir({}, ["uvicorn", "x:app", "--port=8795"]) == RC.LIVE_DIR
    assert RC.disk_dir({}, side) is None
    assert RC.disk_dir({"RESPONSE_CACHE_DIR": "/tmp/x"}, side) == "/tmp/x"
    assert RC.disk_dir({"RESPONSE_CACHE_LIVE_PORT": "8801"}, side) == RC.LIVE_DIR
    assert RC.disk_dir({}, ["pytest"]) == RC.LIVE_DIR    # port yok, test dışı süreç: eski davranış
    assert RC.disk_dir({"PYTEST_CURRENT_TEST": "t"}, live) is None     # test süreci canlı klasöre yazmaz
