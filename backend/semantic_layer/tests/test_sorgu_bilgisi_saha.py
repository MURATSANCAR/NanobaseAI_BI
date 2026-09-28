"""M30 Saha satış ve tahsilat: her rakamın sorgu bilgisi. Ekran rakamları gece turunun portföy/sinyal tablosundan
(portal ifadesi), tabloyu dolduran Logo/CRM SQL'i gece turunda ÇALIŞAN metin (tur kaydında, köken); brifing ve tahsilat
listesinde o istekte çalışan (ya da 5 dk belleği dolduran) CRM/Logo metni; puan, yaşlandırma, hedef formülle."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from semantic_bridge import field_sales as F
from semantic_bridge import field_sales_kaynak as K
from semantic_bridge import field_sales_sources as S
from semantic_bridge import provenance as P
from semantic_bridge.management.kaynak import is_template
from semantic_layer.tests.test_field_sales import ACC1, T, U1, USERS, _data, _settings, engine  # noqa: F401 — fikstür

SCHEMA = "Timas_MSCRM.dbo"
TAHSILAT = [{"id": "c1", "ad": "T1", "account_id": ACC1, "owner_id": U1, "durum": S.T_PENDING, "tip": 100000000, "tutar": 1000,
             "olusturma": "2026-09-25T12:00:00"}]


def _check(out):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [] and not is_template(s["sql"])
        assert s["connection"] in ("logo", "crm", "portal")
        assert "gizli-parola" not in s["sql"]
    return k


class _Conn:
    def __init__(self, name: str):
        self.name = name
        self.cfg = {"database": "CRMDB" if name == "crm" else "LOGODB", "password": "gizli-parola", "host": "10.0.0.9"}

    def execute(self, sql, limit):
        tag = S.query_tag(sql)
        if tag == "crm.kullanicilar":
            return ["x"], [dict(u) for u in USERS], False
        if tag == "crm.tahsilat":
            return ["x"], [dict(t) for t in TAHSILAT], False
        return ["x"], [], False

    def close(self):
        pass


def _night_reads():
    """Gece turunun çalışan metni (üreticilerin kendisiyle; kayıt biçimi `F._runner` ile aynı)."""
    now, end = date(2026, 9, 28), date(2026, 8, 17)
    crm = [S.crm_users_sql(SCHEMA), S.crm_accounts_sql(SCHEMA), S.crm_risk_orders_sql(SCHEMA),
           S.crm_collections_sql(SCHEMA, date(2026, 8, 29))]
    logo = ["SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD", S.data_end_sql("411"), S.clients_sql("411"),
            S.aging_sql("411", 2026, now), S.payments_sql("211", date(2025, 9, 28), (1, 20)),
            S.payments_sql("411", date(2025, 9, 28), (1, 20)), S.sales_sql("411", date(2026, 1, 1), end),
            S.sales_sql("211", date(2025, 1, 1), date(2025, 8, 17)), S.sales_sql("211", date(2025, 1, 1), date(2025, 12, 31)),
            S.cheque_events_sql("411", date(2025, 9, 28)), S.cheque_events_sql("211", date(2025, 9, 28))]
    return ([{"conn": "crm", "db": "CRMDB", "key": S.query_tag(q), "sql": q, "rows": 2, "dbMs": 5, "at": "2026-09-28T06:30:00+03:00"}
             for q in crm] +
            [{"conn": "logo", "db": "LOGODB", "key": S.query_tag(q), "sql": q, "rows": 2, "dbMs": 9, "at": "2026-09-28T06:31:00+03:00"}
             for q in logo])


def _seed(engine):  # noqa: F811
    portfolio, signals, info = F.build(_data(), _settings(), None, {})
    F.write_snapshot(engine, T, portfolio, signals)
    F.meta_set(engine, T, "run", {**info, "firm": "411", "prevFirm": "211", "sorgular": _night_reads()})


def _app(engine):  # noqa: F811
    from fastapi import FastAPI, Request

    from semantic_bridge import field_sales_api

    def auth(request: Request):
        return engine, T, "ayseb", "Ayşe"

    app = FastAPI()
    field_sales_api.register(app, {
        "auth": auth, "require_caller": lambda r: None, "can": lambda u, k: True, "is_admin": lambda u: True,
        "audit": lambda *a, **k: None, "conf": lambda k, d="": d, "fresh": lambda: False,
        "crm_connect": lambda: _Conn("crm"), "logo_connect": lambda: _Conn("logo"), "llm": lambda: None,
        "engine": lambda: engine, "tenant": lambda: T})
    return TestClient(app)


def test_query_tags_name_every_generator():
    assert S.query_tag(S.aging_sql("411", 2026, date(2026, 9, 28))) == "logo.yaslandirma.411"
    assert S.query_tag(S.sales_sql("211", date(2025, 1, 1), date(2025, 8, 17))) == "logo.satis.211.2025-01-01"
    assert S.query_tag(S.cheque_events_sql("411", date(2025, 9, 28))) == "logo.cek.411"
    assert S.query_tag(S.invoices_for_sql("411", "120.01")) == "logo.faturalar.411"
    assert S.query_tag(S.last_payment_sql("411", "120.01", (1,))) == "logo.son_odeme.411"
    assert S.query_tag(S.items_for_sql("411", "120.01", date(2026, 1, 1), date(2026, 8, 17))) == "logo.kitaplar.411.2026-01-01"
    assert S.query_tag(S.similar_items_sql("411", "120.01", "TRABZON", None, date(2026, 1, 1), date(2026, 8, 17))).startswith("logo.benzer.411")
    assert S.query_tag(S.crm_accounts_sql(SCHEMA)) == "crm.cariler"
    assert S.query_tag(S.crm_risk_orders_sql(SCHEMA)) == "crm.riskli_siparis"
    assert S.query_tag(S.crm_orders_for_sql(SCHEMA, ACC1, 180, date(2026, 9, 28))) == "crm.siparisler"


def test_recording_keeps_database_name_only_and_replays_cached_reads():
    src_ = F.Source(lambda: _Conn("crm"), lambda: _Conn("logo"))
    st = {**_settings(), "schema": SCHEMA}
    with F.recording() as first:
        src_.collections(st)
    assert [q["key"] for q in first] == ["crm.tahsilat"] and first[0]["db"] == "CRMDB"
    assert "gizli-parola" not in repr(first) and "10.0.0.9" not in repr(first)
    with F.recording() as again:
        src_.collections(st)                          # bellekten: çalışan metin yine gösterilir (belleği dolduran okuma)
    assert again == first


def test_every_field_screen_cites_its_queries(engine):  # noqa: F811
    _seed(engine)
    c = _app(engine)
    for path in ("/api/v1/field/meta", "/api/v1/field/today", "/api/v1/field/today/brief", "/api/v1/field/portfolio",
                 "/api/v1/field/customers/120.01/brief", "/api/v1/field/collections",
                 "/api/v1/field/collections/crm?durum=onay-bekliyor", "/api/v1/field/visits", "/api/v1/field/payment-plans",
                 "/api/v1/field/overrides", "/api/v1/field/report/weekly"):
        r = c.get(path)
        assert r.status_code == 200, (path, r.text)
        _check(r.json())
    b = c.get("/api/v1/field/customers/120.01/brief").json()
    k = b["kaynaklar"]
    assert k["sources"]["saha.gece.logo.yaslandirma.411"]["sql"].startswith("USE [LOGODB];")
    assert any(s.startswith("saha.canli.logo.faturalar") for s in k["sources"])   # brifingde çalışan Logo metni
    assert "FIFO" in k["formulas"]["yaslandirma"]["text"]
    t = c.get("/api/v1/field/today").json()
    assert "saha.canli.crm.tahsilat" in t["kaynaklar"]["sources"]
    run = F.meta_get(engine, T, "run")
    assert "sorgular" not in c.get("/api/v1/field/meta").json()["run"] and run["sorgular"]


def test_night_run_stores_the_executed_sql_and_hides_it_from_the_answer(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(F, "read_all", lambda source, st, now=None: (source.crm(lambda run: run(S.crm_users_sql(SCHEMA))),
                                                                     _data())[1])
    c = _app(engine)
    r = c.post("/api/v1/field/run-due?tur=gece")
    assert r.status_code == 200, r.text
    assert "sorgular" not in r.json()
    saved = F.meta_get(engine, T, "run")["sorgular"]
    assert [q["key"] for q in saved] == ["crm.kullanicilar"] and saved[0]["db"] == "CRMDB"
