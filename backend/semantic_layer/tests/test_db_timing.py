"""Veritabanı süresi (dbMs): arayüzün "Veritabanında … sürede geldi" etiketi her uçta gerçek ölçümden gelir.

Sözleşme: veri döndüren her uç `dbMs` (ms, tamsayı), `cached` ve `computedAt` taşır. Önbellekten gelen
cevapta dbMs ilk yürütmenin süresidir, `cached` true'dur. Ölçülmemiş süre uydurulmaz (None).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from semantic_layer.tests.test_runtime import catalog  # noqa: F401

SQL = 'SELECT COUNT(*) AS n FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0'
QUESTION = "2026 yılında net ciro"


def _is_ms(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def test_timed_counts_only_the_time_spent_waiting_for_rows():
    from semantic_bridge.app import _timed

    def slow():
        time.sleep(0.05)
        yield 1
        time.sleep(0.05)
        yield 2

    box = [0.0]
    out = []
    for item in _timed(slow(), box):
        out.append(item)
        time.sleep(0.1)          # tüketicinin işi (dosyaya yazma) veritabanı süresine girmez
    assert out == [1, 2]
    assert 0.09 <= box[0] < 0.18, box[0]


def test_run_sql_and_its_cached_copy_carry_the_same_measured_time(store, profiles, settings, logo_connector):
    from semantic_bridge.app import Runtime

    for p in profiles:
        store.upsert_profile(p)
    rt = Runtime(settings, store=store, connector=logo_connector, llm=None)
    first = rt.run_sql(SQL, 10)
    second = rt.run_sql(SQL, 10)
    assert _is_ms(first["dbMs"]) and first["cached"] is False
    assert second["cached"] is True and second["dbMs"] == first["dbMs"]
    assert second["computedAt"] == first["computedAt"]
    whole = rt.run_complete(SQL)
    assert _is_ms(whole["dbMs"]) and "computedAt" in whole


def test_db_timing_never_invents_a_duration():
    from semantic_bridge.app import db_timing

    assert db_timing({}) == {"dbMs": None, "cached": False, "computedAt": None}
    assert db_timing({"dbMs": 12, "cached": True, "computedAt": 1.5, "dbParts": [{"name": "a", "ms": 12}]})["dbParts"]


@pytest.fixture
def client(catalog, logo_connector, settings, monkeypatch, tmp_path):  # noqa: F811
    from semantic_bridge import board as board_mod
    from semantic_bridge import reports as reports_mod
    from semantic_bridge.app import Runtime, create_app

    monkeypatch.delenv("ALERT_SMTP_HOST", raising=False)
    monkeypatch.setenv("ALERT_MEASURE_ON_CREATE", "sync")
    monkeypatch.setattr(reports_mod, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: "ayse")
    runtime = Runtime(settings, store=catalog, connector=logo_connector, llm=None)
    return TestClient(create_app(runtime), cookies={"__Secure-timas_session": "test"})


def test_every_data_endpoint_returns_the_database_time(client):
    # Serbest SQL
    r = client.post("/api/v1/run_sql", json={"sql": SQL, "limit": 10}).json()
    assert _is_ms(r["dbMs"]) and r["cached"] is False and r["computedAt"]

    # Doğal dil sorusu (sohbet / genel bakış)
    a = client.post("/api/v1/ask", json={"question": QUESTION, "execute": True}).json()
    assert a["type"] == "TEXT_TO_SQL", a
    assert _is_ms(a["dbMs"]) and a["computedAt"] and "cached" in a

    # Pano kartı: koşunca ve panoyu yeniden açınca aynı süre
    card = {"id": "k1", "title": "Fatura", "sql": SQL, "chart": "kpi"}
    assert client.put("/api/v1/board", json={"cards": [card]}).status_code == 200
    ran = client.post("/api/v1/board/cards/k1/run").json()
    assert _is_ms(ran["dbMs"]) and "cached" in ran and ran["computedAt"]
    kept = client.get("/api/v1/board").json()["cards"][0]["result"]
    assert kept["dbMs"] == ran["dbMs"] and kept["computedAt"] == ran["computedAt"]

    # Planlı rapor önizlemesi ve çalıştırması
    pv = client.post("/api/v1/reports/preview", json={"question": QUESTION, "columns": []}).json()
    assert _is_ms(pv["dbMs"]) and "cached" in pv, pv
    made = client.post("/api/v1/reports", json={"title": "Ciro", "question": QUESTION, "recipients": "cfo@example.com"}).json()
    assert made["lastDb"] is None, "hiç çalışmamış raporun süresi yok"
    run = client.post(f"/api/v1/reports/{made['id']}/run").json()
    assert run["lastStatus"] != "failed", run
    assert _is_ms(run["lastDb"]["dbMs"]) and "cached" in run["lastDb"]
    assert client.get("/api/v1/reports").json()["reports"][0]["lastDb"] == run["lastDb"]

    # Uyarı ölçümü
    rule = client.post("/api/v1/alerts", json={"title": "Net ciro", "question": QUESTION, "condition": "gt",
                                               "threshold": -1, "recipients": "cfo@example.com"}).json()
    assert _is_ms(rule["last_db"]["dbMs"]), rule
    client.post("/api/v1/alerts/check")
    listed = client.get("/api/v1/alerts").json()["alerts"][0]
    assert _is_ms(listed["last_db"]["dbMs"]) and "computedAt" in listed["last_db"]


def test_people_directory_reports_its_crm_time_and_memory_hits():
    from semantic_bridge import people as P

    d = P.Directory()
    rows = [{"SystemUserId": "a1", "FullName": "Ahmet Yıldız", "DomainName": "TIMAS\\AhmetY"}]
    run = lambda sql: {"records": rows, "dbMs": 42, "cached": False, "computedAt": 1000.0}  # noqa: E731
    assert d.timing(from_memory=False)["dbMs"] is None, "okunmadan süre yok"
    asked = time.time()
    _, at = d.rows("Timas_MSCRM.dbo", run)
    assert d.timing(from_memory=at < asked) == {"dbMs": 42, "cached": False, "computedAt": 1000.0}
    asked = time.time()
    _, at = d.rows("Timas_MSCRM.dbo", run)
    assert at < asked
    assert d.timing(from_memory=at < asked)["cached"] is True
