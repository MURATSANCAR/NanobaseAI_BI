"""Köprü açılışı arkada (hız 2. tur, 2026-09-29): kapı hemen açılır, katalog arkada yüklenir.

Denetlenen: (1) arkada yüklenen katalog, eskisi gibi kurulandan farklı cevap vermez; (2) hazır olmadan gelen istek
beklenir ya da kısa «hazırlanıyor» (503, Retry-After) alır, sağlık ucu hemen cevap verir; (3) çalışma ortamı hiçbir
yoldan ikinci kez kurulmaz; (4) olay döngüsü hiç kilitlenmez; (5) tablo kurulumu sürüm damgasıyla atlanır;
(6) zamanlayıcı sarmalayıcısı (kopru-cagir.sh ve VM iş çalıştırıcısı) yalnız «iş başlamadı» hatalarında yeniden dener.
"""
from __future__ import annotations

import asyncio
import http.client
import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.tests.test_runtime import catalog  # noqa: F401 — fikstür

ROOT = Path(__file__).resolve().parents[3]
QUESTIONS = ["2026 toptan satış tutarı", "2026 net ciro", "Kanal bazında 2026 net ciro", "Temmuz 2026 satılan adet"]
SAME = ("type", "sql", "columns", "records", "rowCount", "summary")


def _answers(rt) -> list[dict]:
    out = []
    for q in QUESTIONS:
        a = rt.ask(q, thread_id=None, sample_size=50)
        out.append({k: a.get(k) for k in SAME} | {"compiler": (a.get("semantic") or {}).get("compiler")})
    return out


# ------------------------------------------------------------------------------------------ katalog arkada
def test_background_catalog_answers_exactly_like_eager_catalog(catalog, logo_connector, settings):  # noqa: F811
    from semantic_bridge.app import Runtime

    eager = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    late = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]), defer_catalog=True)
    assert eager.catalog_is_ready() and not late.catalog_is_ready()
    assert "_cat_profiles" not in late.__dict__                        # profiller açılışta okunmadı
    loader = threading.Thread(target=late.load_catalog)
    loader.start()
    loader.join(30)
    assert late.catalog_is_ready()
    assert [p.table_name for p in late.profiles] == [p.table_name for p in eager.profiles]
    assert _answers(late) == _answers(eager)
    assert late.boot_timings["katalog"] >= 0 and "katalog.profil-okuma" in late.boot_timings


def test_reader_waits_for_the_whole_catalog_never_a_half_built_one(catalog, logo_connector, settings, monkeypatch):  # noqa: F811
    """Yükleme sürerken okuyan iş parçacığı bekler; yükleyici bitince tam kurulmuş nesneleri görür."""
    from semantic_bridge import app as A

    late = A.Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]), defer_catalog=True)
    release = threading.Event()
    real = A.Runtime._rebuild

    def slow_rebuild(self):
        real(self)
        release.wait(10)                  # derleyiciler kuruldu ama yükleme henüz «bitmedi»

    monkeypatch.setattr(A.Runtime, "_rebuild", slow_rebuild)
    seen: dict = {}

    def reader():
        seen["router"] = late.router      # beklemeli
        seen["at"] = time.monotonic()

    loader = threading.Thread(target=late.load_catalog)
    loader.start()
    t = threading.Thread(target=reader)
    t.start()
    time.sleep(0.3)
    assert "router" not in seen            # hâlâ bekliyor
    released_at = time.monotonic()
    release.set()
    t.join(10)
    loader.join(10)
    assert seen["router"] is late.router and seen["at"] >= released_at


def test_request_times_out_with_warming_and_event_loop_is_never_blocked(monkeypatch):
    from semantic_bridge import boot

    ev = threading.Event()
    monkeypatch.setenv("SEMANTIC_BOOT_REQUEST_WAIT_SEC", "0.2")
    token = boot.IN_REQUEST.set(True)
    try:
        t = time.monotonic()
        with pytest.raises(boot.Warming) as e:
            boot.wait(ev, "catalog")
        assert 0.15 <= time.monotonic() - t < 2
        assert e.value.status_code == 503 and e.value.detail["code"] == "WARMING_UP" and e.value.headers["Retry-After"]
    finally:
        boot.IN_REQUEST.reset(token)

    async def on_loop():
        tok = boot.IN_REQUEST.set(True)  # async uç: istek olay döngüsünde
        try:
            t0 = time.monotonic()
            with pytest.raises(boot.Warming):
                boot.wait(ev, "catalog")  # olay döngüsünde beklenmez
            return time.monotonic() - t0
        finally:
            boot.IN_REQUEST.reset(tok)

    assert asyncio.run(on_loop()) < 0.1


def test_boot_services_start_once_whoever_comes_first():
    from semantic_bridge import boot

    class R:
        def catalog_is_ready(self):
            return True

    started: list[str] = []
    b = boot.Boot(lambda: R(), lambda r: started.append("rt"), lambda r: started.append("cat"))
    b.wait_runtime()                      # istek içinden kurulum: servis yok
    b._thread.join(5)
    assert started == [] and b.phase == "hazir"
    b.start(services=True)                # lifespan sonra geldi: servisler şimdi, bir kez
    b.start(services=True)
    assert started == ["rt", "cat"] and b.stop() is True

    started.clear()
    gate = threading.Event()
    b2 = boot.Boot(lambda: (gate.wait(5), R())[1], lambda r: started.append("rt"), lambda r: started.append("cat"))
    b2.start(services=True)               # lifespan önce: iş parçacığı başlatır
    gate.set()
    b2._thread.join(5)
    b2.start(services=True)
    assert started == ["rt", "cat"]

    started.clear()
    b3 = boot.Boot(lambda: R(), lambda r: started.append("rt"), lambda r: started.append("cat"))
    assert b3.stop() is False             # durdurulan açılış servis başlatmaz
    b3.start(services=True)
    assert started == [] and b3._thread is None


def test_bridge_accepts_requests_before_runtime_and_builds_it_once(catalog, logo_connector, settings, monkeypatch):  # noqa: F811
    from semantic_bridge import app as A

    gate = threading.Event()
    calls: list = []

    def slow_build(**kw):
        calls.append(kw)
        gate.wait(20)
        return A.Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]), defer_catalog=True)

    monkeypatch.setattr(A, "build_runtime", slow_build)
    monkeypatch.setenv("SEMANTIC_BOOT_REQUEST_WAIT_SEC", "0.3")
    client = TestClient(A.create_app())
    t = time.monotonic()
    h = client.get("/health")
    assert h.status_code == 200 and h.json()["ready"] is False and h.json()["status"] == "starting"
    assert time.monotonic() - t < 2
    r = client.get("/api/v1/engine")
    assert r.status_code == 503 and r.json()["detail"]["code"] == "WARMING_UP" and r.headers["retry-after"] == "5"
    # Aynı anda gelen istekler ikinci bir kurulum başlatmaz.
    threads = [threading.Thread(target=client.get, args=("/api/v1/llm/queue",)) for _ in range(5)]
    [x.start() for x in threads]
    gate.set()
    [x.join(20) for x in threads]
    for _ in range(200):
        if client.get("/health").json().get("ready"):
            break
        time.sleep(0.05)
    body = client.get("/health").json()
    assert body["ready"] is True and body["profiles"] > 0 and body["boot"]["catalogReady"]
    assert client.get("/api/v1/engine").status_code == 200
    assert len(calls) == 1 and calls[0] == {"defer_catalog": True}


def test_catalog_endpoint_during_catalog_load_gets_warming_then_same_answer(catalog, logo_connector, settings, monkeypatch):  # noqa: F811
    from semantic_bridge import app as A

    monkeypatch.setenv("SEMANTIC_BOOT_REQUEST_WAIT_SEC", "0.3")
    late = A.Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]), defer_catalog=True)
    client = TestClient(A.create_app(late))
    assert client.get("/health").json()["ready"] is False
    assert client.get("/api/v1/llm/queue").status_code == 200          # katalog istemeyen uç hemen
    q = {"question": QUESTIONS[0], "sampleSize": 50}
    r = client.post("/api/v1/ask", json=q)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "WARMING_UP"
    late.load_catalog()
    a = client.post("/api/v1/ask", json=q).json()
    eager = A.Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    b = TestClient(A.create_app(eager)).post("/api/v1/ask", json=q).json()
    assert {k: a.get(k) for k in SAME} == {k: b.get(k) for k in SAME}


def test_given_runtime_keeps_old_health_contract(catalog, logo_connector, settings):  # noqa: F811
    from semantic_bridge.app import Runtime, create_app

    body = TestClient(create_app(Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""])))).get("/health").json()
    assert body["status"] == "ok" and body["ready"] is True and body["profiles"] > 0 and "cache" in body and "catalog" in body


# ------------------------------------------------------------------------------------------ sürüm damgası
def test_schema_stamp_skips_unchanged_install_and_reruns_on_change(tmp_path, monkeypatch):
    from semantic_layer.store import schema_stamp

    monkeypatch.setenv("SCHEMA_STAMP_SQLITE", "1")
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'damga.db'}")
    md = sa.MetaData()
    t = sa.Table("semantic_x_ornek", md, sa.Column("id", sa.Integer, primary_key=True), sa.Column("ad", sa.Text))
    runs: list[int] = []

    def install():
        runs.append(1)
        md.create_all(engine, checkfirst=True)

    schema_stamp.forget()
    assert schema_stamp.run(engine, [t], install) is True and len(runs) == 1
    schema_stamp.forget()                                   # «yeniden başlatma»: süreç belleği boş
    assert schema_stamp.run(engine, [t], install) is False and len(runs) == 1
    # Tanım değişti (yeni kolon): kurulum bir kez daha koşar, damga yenilenir.
    md2 = sa.MetaData()
    t2 = sa.Table("semantic_x_ornek", md2, sa.Column("id", sa.Integer, primary_key=True), sa.Column("ad", sa.Text),
                  sa.Column("yeni", sa.Text))
    schema_stamp.forget()
    assert schema_stamp.run(engine, [t2], install) is True and len(runs) == 2
    schema_stamp.forget()
    assert schema_stamp.run(engine, [t2], install) is False and len(runs) == 2
    # Kapalıyken eskisi gibi her seferinde.
    monkeypatch.setenv("SCHEMA_STAMP", "0")
    assert schema_stamp.run(engine, [t2], install) is True and len(runs) == 3
    schema_stamp.forget()


def test_schema_stamp_create_all_builds_tables_first_time(tmp_path, monkeypatch):
    from semantic_layer.store import schema_stamp

    monkeypatch.setenv("SCHEMA_STAMP_SQLITE", "1")
    schema_stamp.forget()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'ilk.db'}")
    md = sa.MetaData()
    sa.Table("semantic_x_bir", md, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table("semantic_x_iki", md, sa.Column("id", sa.Integer, primary_key=True), sa.Index("ix_x_iki", "id"))
    assert schema_stamp.create_all(md, engine) is True
    names = set(sa.inspect(engine).get_table_names())
    assert {"semantic_x_bir", "semantic_x_iki", "sl_schema_stamp"} <= names
    assert schema_stamp.create_all(md, engine) is False       # aynı süreçte ikinci çağrı DDL derlemez bile
    schema_stamp.forget()


def test_every_module_ensure_uses_the_stamp():
    """Köprü modüllerinde damgasız `_md.create_all(engine, checkfirst=True)` kalmadı (yeni modül de damgayı kullanır)."""
    offenders = []
    for f in (ROOT / "backend" / "semantic_bridge").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("_md.create_all(") and "def install" not in text:
                offenders.append(f"{f.relative_to(ROOT)}: {s}")
    assert offenders == []


# ------------------------------------------------------------------------------------------ zamanlayıcı çağrısı
class _Bridge:
    """Sahte köprü: /health (pid, hazır mı) ve bir tur ucu; cevap sırası testte verilir."""

    def __init__(self, replies: list, *, pid: int = 101, ready_after: int = 0):
        self.replies = list(replies)
        self.calls = 0
        self.health_calls = 0
        self.pid = pid
        self.ready_after = ready_after
        bridge = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: D401
                pass

            def _send(self, code: int, body: dict):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path == "/health":
                    bridge.health_calls += 1
                    ready = bridge.health_calls > bridge.ready_after
                    return self._send(200, {"status": "ok" if ready else "starting", "pid": bridge.pid,
                                            "boot": {"runtimeReady": ready}})
                self._send(404, {})

            def do_POST(self):
                bridge.calls += 1
                reply = bridge.replies.pop(0) if bridge.replies else 200
                if isinstance(reply, tuple):          # (cevap, yeni pid): köprü bu istekte yeniden başladı
                    reply, bridge.pid = reply
                if reply == "drop":                   # cevapsız kopan bağlantı (curl 52)
                    self.close_connection = True
                    self.connection.shutdown(2)
                    return
                self._send(reply, {"ok": reply == 200})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def close(self):
        self.server.shutdown()


def _wrapper(port: int, **env) -> subprocess.CompletedProcess:
    e = {**os.environ, "KOPRU_ARALIK_SN": "0", "KOPRU_BEKLE_SN": "20", "SEMANTIC_CALLER_TOKEN": "gizli", **env}
    return subprocess.run(["bash", str(ROOT / "scripts/server/kopru-cagir.sh"), "-m", "10", "-X", "POST",
                           f"http://127.0.0.1:{port}/api/v1/ornek/run-due?tur=gece"],
                          capture_output=True, text=True, env=e, timeout=60)


def test_wrapper_waits_for_ready_and_retries_only_503():
    b = _Bridge([503, 503, 200], ready_after=1)
    try:
        r = _wrapper(b.port)
    finally:
        b.close()
    assert r.returncode == 0, r.stderr
    assert b.calls == 3 and b.health_calls >= 3 and '"ok": true' in r.stdout
    assert "deneme 1" in r.stderr and "deneme 3: başarılı" in r.stderr
    assert "gizli" not in r.stdout + r.stderr


@pytest.mark.parametrize("reply", [500, 504, 404])
def test_wrapper_does_not_repeat_a_job_that_may_have_run(reply):
    b = _Bridge([reply, 200])
    try:
        r = _wrapper(b.port)
    finally:
        b.close()
    assert r.returncode != 0 and b.calls == 1


def test_wrapper_retries_dropped_connection_only_when_bridge_restarted():
    same = _Bridge(["drop", 200])
    try:
        r = _wrapper(same.port)
    finally:
        same.close()
    assert r.returncode != 0 and same.calls == 1                      # aynı pid: iş sürüyor olabilir

    restarted = _Bridge([("drop", 202), 200])                      # köprü yeniden başladı: iş onunla öldü
    try:
        r = _wrapper(restarted.port)
    finally:
        restarted.close()
    assert r.returncode == 0, r.stderr
    assert restarted.calls == 2 and "yeniden başladı" in r.stderr


def test_wrapper_gives_up_when_bridge_never_ready():
    b = _Bridge([200], ready_after=10_000)
    try:
        r = _wrapper(b.port, KOPRU_BEKLE_SN="3")
    finally:
        b.close()
    assert r.returncode != 0 and b.calls == 0


def test_every_timer_unit_goes_through_the_wrapper():
    raw = [f.name for f in (ROOT / "scripts/server").glob("timas-*.service")
           if "curl -fsS" in f.read_text(encoding="utf-8") and "127.0.0.1:8795" in f.read_text(encoding="utf-8")]
    assert raw == []


def _vm_jobs():
    spec = importlib.util.spec_from_file_location("vm_jobs_retry", ROOT / "infra/docker/bi/jobs.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["vm_jobs_retry"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_vm_jobs_parse_wrapper_line_and_retry_rules(monkeypatch):
    jobs = _vm_jobs()
    line = '/data/nanobaseai/bi/frontend/scripts/server/kopru-cagir.sh -m 3500 -X POST "http://127.0.0.1:8795/api/v1/schools/run-due?kind=nightly"'
    assert jobs.parse_exec(line) == ("/api/v1/schools/run-due?kind=nightly", 3500)
    monkeypatch.setattr(jobs.time, "sleep", lambda s: None)
    monkeypatch.setattr(jobs, "RETRY_DELAY", 0.0)
    pids = iter([7, 7, 7, 7, 7])
    monkeypatch.setattr(jobs, "_bridge_pid", lambda: next(pids))

    def seq(*items):
        items = list(items)
        calls = []

        def post(path, body, timeout):
            calls.append(path)
            it = items.pop(0)
            if isinstance(it, BaseException):
                raise it
            return it
        return post, calls

    err503 = urllib.error.HTTPError("u", 503, "x", {}, None)
    post, calls = seq(err503, urllib.error.URLError(ConnectionRefusedError()), {"ok": True})
    monkeypatch.setattr(jobs, "_post", post)
    assert jobs.call_bridge("/api/v1/x/run-due", 10, budget=30) == {"ok": True} and len(calls) == 3

    post, calls = seq(urllib.error.HTTPError("u", 500, "x", {}, None), {"ok": True})
    monkeypatch.setattr(jobs, "_post", post)
    with pytest.raises(urllib.error.HTTPError):
        jobs.call_bridge("/api/v1/x/run-due", 10, budget=30)
    assert len(calls) == 1

    post, calls = seq(TimeoutError("timed out"), {"ok": True})
    monkeypatch.setattr(jobs, "_post", post)
    with pytest.raises(TimeoutError):
        jobs.call_bridge("/api/v1/x/run-due", 10, budget=30)
    assert len(calls) == 1

    # Bağlantı koptu: pid aynıysa denenmez, değiştiyse denenir.
    pids = iter([7, 7])
    monkeypatch.setattr(jobs, "_bridge_pid", lambda: next(pids))
    post, calls = seq(http.client.RemoteDisconnected("x"), {"ok": True})
    monkeypatch.setattr(jobs, "_post", post)
    with pytest.raises(http.client.RemoteDisconnected):
        jobs.call_bridge("/api/v1/x/run-due", 10, budget=30)
    pids = iter([7, 8, 8])
    monkeypatch.setattr(jobs, "_bridge_pid", lambda: next(pids))
    post, calls = seq(http.client.RemoteDisconnected("x"), {"ok": True})
    monkeypatch.setattr(jobs, "_post", post)
    assert jobs.call_bridge("/api/v1/x/run-due", 10, budget=30) == {"ok": True} and len(calls) == 2
