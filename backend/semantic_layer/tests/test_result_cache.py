"""Sonuç önbelleği ve arka plan tazeleyici: kokpit açılışının kaynağa inmeden karşılanması.

Kokpit her yenilemede aynı beş toplama sorgusunu ister ve bunlar tek bağlantı üstünde sıraya girer.
Buradaki sözleşme: aynı sorgu ikinci kez sorulduğunda kaynağa inilmez, cevabın yaşı cevapla birlikte
gider, ve süresi geçmiş bir kopya yalnız tazeleyici ayaktayken servis edilir.
"""

from __future__ import annotations

import time

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.profiler.connectors import SQLiteConnector

SQL = 'SELECT COUNT(*) AS n FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0'


class CountingConnector(SQLiteConnector):
    """Kaç kez gerçekten kaynağa inildiğini sayar; yavaşlığı da taklit edebilir."""

    def __init__(self, conn, delay: float = 0.0):
        super().__init__(conn=conn)
        self.calls = 0
        self.delay = delay

    def execute(self, sql: str, limit: int):
        self.calls += 1
        if self.delay:
            time.sleep(self.delay)
        return super().execute(sql, limit)


def _runtime(store, profiles, settings, connector):
    from semantic_bridge.app import Runtime

    for p in profiles:
        store.upsert_profile(p)
    return Runtime(settings, store=store, connector=connector, llm=FakeLlm([""]))


def test_second_call_is_served_from_cache_with_its_age(store, profiles, settings, logo_db):
    conn = CountingConnector(logo_db)
    rt = _runtime(store, profiles, settings, conn)

    first = rt.run_sql(SQL, 10)
    second = rt.run_sql(SQL, 10)

    assert conn.calls == 1, "aynı sorgu ikinci kez kaynağa inmemeli"
    assert first["cached"] is False and second["cached"] is True
    assert first["records"] == second["records"]
    assert first["id"] != second["id"], "her cevabın kendi id'si olmalı"
    assert second["ageSec"] >= 0 and second["computedAt"] == first["computedAt"]


def test_expired_copy_is_refetched_when_nothing_refreshes_it(store, profiles, settings, logo_db):
    conn = CountingConnector(logo_db)
    rt = _runtime(store, profiles, settings, conn)
    rt._cache_ttl = 0.01
    rt.run_sql(SQL, 10)
    time.sleep(0.05)

    rt.run_sql(SQL, 10)

    assert conn.calls == 2, "tazeleyici yokken bayat kopya servis edilmemeli"


def test_background_refresher_keeps_hot_queries_warm(store, profiles, settings, logo_db):
    conn = CountingConnector(logo_db)
    rt = _runtime(store, profiles, settings, conn)
    rt._refresh_sec = 0.05
    rt.run_sql(SQL, 10)          # sorguyu sıcak listeye koyar
    assert conn.calls == 1

    rt.start_refresher()
    try:
        deadline = time.time() + 3
        while conn.calls < 3 and time.time() < deadline:
            time.sleep(0.02)
    finally:
        rt.stop_refresher()

    assert conn.calls >= 3, "sıcak sorgu arka planda tazelenmeli"
    # Kullanıcı hiç beklemedi: tazeleme kaynağa indi, istek önbellekten döndü.
    before = conn.calls
    out = rt.run_sql(SQL, 10)
    assert conn.calls == before and out["cached"] is True


def test_refresher_leaves_cold_queries_alone(store, profiles, settings, logo_db):
    conn = CountingConnector(logo_db)
    rt = _runtime(store, profiles, settings, conn)
    rt._refresh_sec = 0.05
    rt._hot_window = 0.1         # kimsenin bakmadığı sorgu bu süre sonunda listeden düşer
    rt.run_sql(SQL, 10)
    rt.start_refresher()
    try:
        time.sleep(0.5)
    finally:
        rt.stop_refresher()
    settled = conn.calls
    time.sleep(0.3)
    assert conn.calls == settled and not rt._hot, "sıcaklığı biten sorgu kaynağı meşgul etmemeli"


def test_slow_query_is_refreshed_less_often(store, profiles, settings, logo_db):
    """Tur uzunluğu = sıcak kümenin toplam süresi × duty. Pahalı sorgu turu uzatır, kaynak bize
    ayrılmaz; tek bağlantı üstünde kullanıcının sorusu sıraya girmeye devam edebilir."""
    conn = CountingConnector(logo_db, delay=0.1)
    rt = _runtime(store, profiles, settings, conn)
    rt._refresh_sec = 0.02
    rt._refresh_duty = 20        # 0.1 sn × 20 = en sık 2 saniyede bir
    rt.run_sql(SQL, 10)
    rt.start_refresher()
    try:
        time.sleep(0.6)
    finally:
        rt.stop_refresher()
    assert conn.calls == 1, f"pahalı sorgu duty sınırını aşarak tazelendi (calls={conn.calls})"


def test_health_reports_cache_state(store, profiles, settings, logo_db):
    from fastapi.testclient import TestClient
    from semantic_bridge.app import create_app

    rt = _runtime(store, profiles, settings, CountingConnector(logo_db))
    client = TestClient(create_app(rt))
    rt.run_sql(SQL, 10)
    cache = client.get("/health").json()["cache"]
    assert cache["entries"] == 1 and cache["hot"] == 1 and cache["refreshSec"] > 0
