"""Canlı kaynak bağlantı havuzu (hız 2. tur, 2026-09-29).

Köprü bütün Logo/CRM okumalarını tek bağlantı ve tek kilitten geçiriyordu; ekranlar birbirinin ve beş
dakikada bir koşan tazeleme turlarının arkasında bekledi. Buradaki sözleşme:
- iki okuma birbirini beklemez, her iş parçacığı kendi bağlantısını kullanır;
- aynı SQL aynı anda iki kez gelirse kaynağa bir kez inilir;
- sunucunun eşzamanlılık sınırı dolunca okuma sırada bekler ve sonra koşar (düşürülmez);
- sonuçlar tek bağlantılı düzenle aynıdır.
Beklemeler engel (Barrier/Event) ile kanıtlanır, süre ölçümüyle değil: yavaş makinede de aynı sonuç.
"""

from __future__ import annotations

import threading
import time
import uuid

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.profiler.connection_pool import (ConnectorPool, SingleFlight, gate_for, gate_of, pooled,
                                                     queue_wait, server_key)
from semantic_layer.profiler.connectors import MSSQLConnector, SQLiteConnector

COUNT_SQL = 'SELECT COUNT(*) AS n FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0'
OTHER_SQL = 'SELECT COUNT(*) AS n FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 1'
ROWS_SQL = 'SELECT LOGICALREF AS id FROM LG_411_01_INVOICE'


def _host() -> str:
    # Kapılar sunucu adresine bağlı ve süreç boyunca yaşar: her test kendi sunucusunu uydurur.
    return f"test-{uuid.uuid4().hex[:10]}"


def _wait_until(cond, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.005)
    return bool(cond())


def _runtime(store, profiles, settings, connector):
    from semantic_bridge.app import Runtime

    for p in profiles:
        store.upsert_profile(p)
    return Runtime(settings, store=store, connector=connector, llm=FakeLlm([""]))


class FakeServer:
    """Sahte sunucu: içeride kaç okuma var, hangi bağlantı kimde. `hold` açılana kadar okuma bitmez."""

    def __init__(self):
        self.lock = threading.Lock()
        self.inside = 0
        self.peak = 0
        self.calls = 0
        self.busy: set = set()
        self.shared_use = 0          # aynı bağlantı iki iş parçacığında aynı anda — hiç olmamalı
        self.hold = threading.Event()
        self.hold.set()

    def enter(self, conn_id: str) -> None:
        with self.lock:
            self.inside += 1
            self.calls += 1
            self.peak = max(self.peak, self.inside)
            if conn_id in self.busy:
                self.shared_use += 1
            self.busy.add(conn_id)

    def leave(self, conn_id: str) -> None:
        with self.lock:
            self.inside -= 1
            self.busy.discard(conn_id)


class FakeConn:
    """Çoğaltılabilir bağlayıcı; her kopyanın kendi bağlantısı (kimliği) vardır."""

    dialect = "tsql"

    def __init__(self, cfg, server, barrier=None):
        self.cfg, self.server, self.barrier = cfg, server, barrier
        self.conn_id = uuid.uuid4().hex
        self.query_timeout = 120

    def clone(self):
        return FakeConn(dict(self.cfg), self.server, self.barrier)

    def _gate_key(self):
        return server_key(self.cfg)

    def execute(self, sql, limit):
        self.server.enter(self.conn_id)
        try:
            if self.barrier is not None:
                self.barrier.wait()
            if not self.server.hold.wait(5):
                raise TimeoutError("hold never released")
            return [{"name": "sql"}], [{"sql": sql, "conn": self.conn_id}], False
        finally:
            self.server.leave(self.conn_id)

    def batches(self, sql, batch_size=1000):
        self.server.enter(self.conn_id)
        try:
            yield [{"name": "i"}], []
            for i in range(3):
                yield [{"name": "i"}], [{"i": i}]
        finally:
            self.server.leave(self.conn_id)

    def close(self):
        pass


class ParallelSqlite(SQLiteConnector):
    """Köprü testleri için çoğaltılabilir SQLite: iki okuma engelde buluşmadan ilerleyemez. Buluştuktan
    sonra ortak bellek içi veritabanına sırayla girer (SQLite bağlantısı paylaşılıyor, havuz değil)."""

    serial = threading.Lock()

    def __init__(self, conn, cfg, barrier):
        super().__init__(conn=conn)
        self.shared, self.cfg, self.barrier = conn, cfg, barrier

    def clone(self):
        return ParallelSqlite(self.shared, dict(self.cfg), self.barrier)

    def execute(self, sql, limit):
        self.barrier.wait()
        with ParallelSqlite.serial:
            return super().execute(sql, limit)


class BlockingSqlite(SQLiteConnector):
    """Kaç kez kaynağa inildiğini sayar; `release` açılana kadar ilk okumayı içeride tutar."""

    def __init__(self, conn):
        super().__init__(conn=conn)
        self.calls = 0
        self.entered = threading.Event()
        self.release = threading.Event()

    def execute(self, sql, limit):
        self.calls += 1
        self.entered.set()
        if not self.release.wait(5):
            raise TimeoutError("release never set")
        return super().execute(sql, limit)


# ---------------------------------------------------------------------------------------------- havuz


def test_two_slow_reads_on_one_server_do_not_wait_for_each_other():
    server = FakeServer()
    barrier = threading.Barrier(2, timeout=5)     # sırayla koşsalardı ilki burada zaman aşımına düşerdi
    pool = pooled(FakeConn({"host": _host(), "port": 1433}, server, barrier), "logo", lambda: 4)
    out, errors = [], []

    def read(sql):
        try:
            out.append(pool.execute(sql, 10)[1][0])
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=read, args=(s,)) for s in ("SELECT 1", "SELECT 2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not errors, errors
    assert server.peak == 2
    assert len({r["conn"] for r in out}) == 2, "her iş parçacığı kendi bağlantısını almalı"
    assert server.shared_use == 0
    assert pool.pool_stats()["connections"] == 2


def test_limit_queues_reads_and_runs_them_all():
    server = FakeServer()
    server.hold.clear()
    pool = pooled(FakeConn({"host": _host()}, server), "logo", lambda: 2)
    gate = pool.gate
    results, errors = [], []

    def read(i):
        try:
            results.append(pool.execute(f"SELECT {i}", 10)[1][0]["sql"])
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=read, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    assert _wait_until(lambda: server.inside == 2 and gate.waiting() == 3), (server.inside, gate.waiting())
    time.sleep(0.05)
    assert server.inside == 2, "sınır aşılmamalı"
    server.hold.set()
    for t in threads:
        t.join(10)
    assert not errors, errors
    assert sorted(results) == [f"SELECT {i}" for i in range(5)], "sırada bekleyen okuma düşürülmemeli"
    assert server.peak == 2
    st = gate.stats()
    assert st["limit"] == 2 and st["waitedRuns"] == 3 and st["running"] == 0 and st["waiting"] == 0
    assert pool.pool_stats()["connections"] == 2, "açık bağlantı sayısı sınırı aşmamalı"


def test_limit_is_read_from_the_setting_each_time():
    box = {"n": 1}
    pool = pooled(FakeConn({"host": _host()}, FakeServer()), "logo", lambda: box["n"])
    assert pool.gate.limit() == 1
    box["n"] = 6
    assert pool.gate.limit() == 6
    box["n"] = 0
    assert pool.gate.limit() == 1, "sınır en az 1: sıfır kaynağı kapatmaz"


def test_batch_read_holds_its_connection_until_closed_and_nested_read_does_not_deadlock():
    server = FakeServer()
    pool = pooled(FakeConn({"host": _host()}, server), "logo", lambda: 1)
    gen = pool.batches("SELECT big")
    assert next(gen)[0] == [{"name": "i"}]        # tek yer bu okumada
    # Aynı iş parçacığında iç içe okuma kendi yerini kullanır: sınır 1 iken kendini beklemez.
    assert pool.execute("SELECT nested", 10)[1][0]["sql"] == "SELECT nested"
    other = []
    t = threading.Thread(target=lambda: other.append(pool.execute("SELECT other", 10)))
    t.start()
    assert _wait_until(lambda: pool.gate.waiting() == 1)
    gen.close()                                   # yarıda bırakılan okuma yeri hemen bırakır
    t.join(5)
    assert other and other[0][1][0]["sql"] == "SELECT other"
    assert pool.gate.stats()["running"] == 0
    assert server.shared_use == 0


def test_queue_wait_is_not_database_time():
    server = FakeServer()
    server.hold.clear()
    pool = pooled(FakeConn({"host": _host()}, server), "logo", lambda: 1)
    first = threading.Thread(target=lambda: pool.execute("SELECT first", 10))
    first.start()
    assert _wait_until(lambda: server.inside == 1)
    waited = []

    def second():
        with queue_wait() as w:
            pool.execute("SELECT second", 10)
        waited.append(w[0])

    t = threading.Thread(target=second)
    t.start()
    assert _wait_until(lambda: pool.gate.waiting() == 1)
    time.sleep(0.2)
    server.hold.set()
    first.join(5)
    t.join(5)
    assert waited and waited[0] >= 0.15


def test_crm_filter_stays_outside_and_settings_reach_every_copy():
    from semantic_layer.runtime.crm_active import ActiveOnly

    inner = FakeConn({"host": _host()}, FakeServer())
    wrapped = pooled(ActiveOnly(inner, "Timas_MSCRM"), "crm", lambda: 4)
    assert isinstance(wrapped, ActiveOnly), "etkin kayıt süzgeci en dışta kalmalı (metin bir kez yeniden yazılır)"
    pool = wrapped._inner
    assert isinstance(pool, ConnectorPool) and pool.prototype is inner
    assert gate_of(inner) is not None and gate_of(inner) is pool.gate
    assert wrapped.pool_stats()["name"] == "crm"
    pool.query_timeout = 600
    assert inner.query_timeout == 600
    with pool.lease() as a, pool.lease() as b:
        assert a is not b and b.query_timeout == 600, "sonradan açılan kopya da ayarı almalı"


def test_mssql_clone_opens_its_own_connection_and_in_memory_sqlite_stays_shared(logo_db):
    host = _host()
    c = MSSQLConnector({"host": host, "port": 1433, "database": "d", "user": "u", "password": "p"})
    c.query_timeout = 600
    k = c.clone()
    assert k is not c and k.cfg == c.cfg and k.cfg is not c.cfg
    assert k.query_timeout == 600 and k._conn is None
    pool = pooled(c, "logo", lambda: 3)
    assert gate_for(f"{host}:1433") is pool.gate and pool.gate.limit() == 3
    shared = pooled(SQLiteConnector(conn=logo_db), "logo", lambda: 3)
    assert shared.pool_stats()["shared"] is True and shared.gate is None


def test_single_flight_runs_one_call_per_key_and_shares_the_error():
    sf = SingleFlight()
    started, release, calls, got = threading.Event(), threading.Event(), [], []

    def slow():
        calls.append(1)
        started.set()
        release.wait(5)
        return {"v": 42}

    t1 = threading.Thread(target=lambda: got.append(sf.do("k", slow)))
    t1.start()
    assert started.wait(5)
    t2 = threading.Thread(target=lambda: got.append(sf.do("k", slow)))
    t2.start()
    assert _wait_until(lambda: sf.joined == 1)
    release.set()
    t1.join(5)
    t2.join(5)
    assert calls == [1] and got == [{"v": 42}, {"v": 42}]
    assert sf.do("k", lambda: 7) == 7, "bitmiş çağrı saklanmaz; sonraki yeniden koşar"

    started.clear()
    release.clear()
    errors = []

    def boom():
        started.set()
        release.wait(5)
        raise ValueError("kaynak hatası")

    def call():
        try:
            sf.do("e", boom)
        except ValueError as e:
            errors.append(str(e))

    t1 = threading.Thread(target=call)
    t1.start()
    assert started.wait(5)
    t2 = threading.Thread(target=call)
    t2.start()
    assert _wait_until(lambda: sf.joined == 2)
    release.set()
    t1.join(5)
    t2.join(5)
    assert errors == ["kaynak hatası", "kaynak hatası"]


# ---------------------------------------------------------------------------------------------- köprü


def test_bridge_runs_two_different_reads_at_the_same_time(store, profiles, settings, logo_db):
    barrier = threading.Barrier(2, timeout=5)
    rt = _runtime(store, profiles, settings, ParallelSqlite(logo_db, {"host": _host()}, barrier))
    out, errors = {}, []

    def ask(sql):
        try:
            out[sql] = rt.run_sql(sql, 10, use_cache=False)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=ask, args=(s,)) for s in (COUNT_SQL, OTHER_SQL)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not errors, errors
    direct = SQLiteConnector(conn=logo_db)
    for sql, res in out.items():
        assert res["records"] == direct.execute(res["physicalSql"], 10)[1], "sonuç tek bağlantılı düzenle aynı olmalı"
    stats = rt.cache_stats()["pools"]["logo"]
    assert stats["connections"] == 2 and stats["gate"]["peak"] == 2


def test_bridge_runs_the_same_sql_once_when_it_arrives_twice(store, profiles, settings, logo_db):
    conn = BlockingSqlite(logo_db)
    rt = _runtime(store, profiles, settings, conn)
    got, errors = [], []

    def ask():
        try:
            got.append(rt.run_sql(COUNT_SQL, 10, use_cache=False))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=ask)
    t1.start()
    assert conn.entered.wait(5)
    t2 = threading.Thread(target=ask)
    t2.start()
    assert _wait_until(lambda: rt._flight.joined == 1)
    conn.release.set()
    t1.join(5)
    t2.join(5)
    assert not errors, errors
    assert conn.calls == 1, "aynı SQL aynı anda ikinci kez kaynağa inmemeli"
    assert got[0]["records"] == got[1]["records"] and got[0]["id"] != got[1]["id"]
    assert rt.cache_stats()["sameQueryJoined"] == 1


def test_complete_results_match_a_direct_read(store, profiles, settings, logo_db):
    rt = _runtime(store, profiles, settings, SQLiteConnector(conn=logo_db))
    got, errors = [], []

    def run():
        try:
            got.append(rt.run_complete(ROWS_SQL, use_cache=False))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not errors, errors
    direct = SQLiteConnector(conn=logo_db).execute(got[0]["physicalSql"], 10 ** 6)[1]
    for out in got:
        assert rt.result_files.read(out["_result_file"]) == direct
        assert out["totalRows"] == len(direct) and out["cached"] is False
    again = rt.run_complete(ROWS_SQL)
    assert again["cached"] is True and rt.result_files.read(again["_result_file"]) == direct


def test_health_shows_the_pools(store, profiles, settings, logo_db):
    from fastapi.testclient import TestClient
    from semantic_bridge.app import create_app

    rt = _runtime(store, profiles, settings, SQLiteConnector(conn=logo_db))
    rt.run_sql(COUNT_SQL, 10)
    pools = TestClient(create_app(rt)).get("/health").json()["cache"]["pools"]
    assert pools["logo"]["connections"] == 1 and pools["logo"]["shared"] is True


def test_concurrency_setting_defaults_and_floor(monkeypatch):
    from semantic_bridge.app import _concurrency

    monkeypatch.delenv("LOGO_MAX_CONCURRENT", raising=False)
    assert _concurrency("LOGO_MAX_CONCURRENT")() == 4
    monkeypatch.setenv("LOGO_MAX_CONCURRENT", "2")
    assert _concurrency("LOGO_MAX_CONCURRENT")() == 2
    monkeypatch.setenv("LOGO_MAX_CONCURRENT", "0")
    assert _concurrency("LOGO_MAX_CONCURRENT")() == 1
    monkeypatch.setenv("LOGO_MAX_CONCURRENT", "dört")
    assert _concurrency("LOGO_MAX_CONCURRENT")() == 4
