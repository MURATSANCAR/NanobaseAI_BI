"""M59 Bayi riski: her rakamın sorgu bilgisi. Ekran rakamları günlük turun skor satırlarından (portal ifadesi), tabloyu
dolduran Logo/CRM SQL'i günlük turda ÇALIŞAN metin (tur kaydında, köken); skor, segment, limit önerisi ve pano
toplamları yürürlükteki kural sürümünün formülüyle."""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from semantic_bridge import dealers as D
from semantic_bridge import dealers_kaynak as K
from semantic_bridge import dealers_sources as DS
from semantic_bridge import field_sales_sources as S
from semantic_bridge import provenance as P
from semantic_bridge.management.kaynak import is_template
from semantic_layer.tests.test_dealers import ACC1, T, U1, _data, engine  # noqa: F401 — fikstür

SCHEMA = "Timas_MSCRM.dbo"


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
        self.cfg = {"database": "CRMDB" if name == "crm" else "LOGODB", "password": "gizli-parola"}

    def execute(self, sql, limit):
        if S.query_tag(sql) == "crm.kullanicilar":
            return ["x"], [{"id": U1, "ad": "Ayşe Bmt", "domain": "TIMAS\\ayseb", "bmt": 1}], False
        return ["x"], [], False

    def close(self):
        pass


def _night(source):
    """Günlük turun okuması yerine: gerçek üreticilerle birkaç CRM/Logo sorgusu koşar (kayıt bunlardan), veri tohumdan."""
    end = date(2026, 8, 17)
    source.crm(lambda run: [run(q) for q in (S.crm_users_sql(SCHEMA), S.crm_accounts_sql(SCHEMA), S.crm_risk_orders_sql(SCHEMA),
                                             DS.crm_account_flags_sql(SCHEMA))])
    source.logo(lambda run: [run(q) for q in ("SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD", S.data_end_sql("411"),
                                              S.clients_sql("411"), S.aging_sql("411", 2026, end),
                                              S.cheque_events_sql("411", date(2025, 8, 17)),
                                              S.payments_sql("411", date(2025, 8, 17), (1, 20)),
                                              DS.monthly_sales_sql("211", date(2025, 9, 1), date(2025, 12, 31)),
                                              DS.monthly_sales_sql("411", date(2026, 1, 1), end),
                                              DS.monthly_payments_sql("411", date(2026, 1, 1), end, (1, 20)))])
    return _data()


def _app(engine, monkeypatch):  # noqa: F811
    from fastapi import FastAPI, Request

    from semantic_bridge import dealers_api

    monkeypatch.setattr(D, "read_all", lambda source, st, now=None: _night(source))

    def auth(request: Request):
        return engine, T, "ayseb", "Ayşe"

    app = FastAPI()
    dealers_api.register(app, {
        "auth": auth, "require_caller": lambda r: None, "can": lambda u, k: True, "is_admin": lambda u: True,
        "audit": lambda *a, **k: None, "conf": lambda k, d="": d, "fresh": lambda: False,
        "crm_connect": lambda: _Conn("crm"), "logo_connect": lambda: _Conn("logo"), "llm": lambda batch: None,
        "engine": lambda: engine, "tenant": lambda: T})
    return TestClient(app)


def test_monthly_series_and_flags_have_their_own_tags():
    assert S.query_tag(DS.monthly_sales_sql("411", date(2026, 1, 1), date(2026, 8, 17))) == "logo.aylik_satis.411.2026-01-01"
    assert S.query_tag(DS.monthly_payments_sql("411", date(2026, 1, 1), date(2026, 8, 17), (1,))) == "logo.aylik_odeme.411.2026-01-01"
    assert S.query_tag(DS.crm_account_flags_sql(SCHEMA)) == "crm.cari_bayrak"
    assert S.query_tag(DS.crm_risk_history_sql(SCHEMA, ACC1, date(2025, 9, 28))) == "crm.risk_gecmisi"


def test_every_dealer_screen_cites_its_queries(engine, monkeypatch):  # noqa: F811
    c = _app(engine, monkeypatch)
    r = c.post("/api/v1/dealers/run-due?tur=gunluk")
    assert r.status_code == 200, r.text
    assert "sorgular" not in r.json()
    saved = D.meta_get(engine, T, "run")["sorgular"]
    assert {q["key"] for q in saved} >= {"crm.cari_bayrak", "logo.aylik_satis.411.2026-01-01", "logo.yaslandirma.411"}
    assert "sorgular" not in c.get("/api/v1/dealers/status").json()["run"]
    rule_id = D.active_rule(engine, T)["id"]
    for method, path in (("get", "/api/v1/dealers/meta"), ("get", "/api/v1/dealers/summary"), ("get", "/api/v1/dealers/list"),
                         ("get", "/api/v1/dealers/limits?durum="), ("get", "/api/v1/dealers/rules"),
                         ("post", f"/api/v1/dealers/rules/{rule_id}/preview"), ("get", "/api/v1/dealers/actions"),
                         ("get", "/api/v1/dealers/120.01"), ("get", "/api/v1/dealers/120.01/aging"),
                         ("get", "/api/v1/dealers/120.01/history"), ("post", "/api/v1/dealers/120.01/brief"),
                         ("get", "/api/v1/dealers/120.01/notes")):
        resp = getattr(c, method)(path)
        assert resp.status_code == 200, (path, resp.text)
        _check(resp.json())
    card = c.get("/api/v1/dealers/120.01").json()
    k = card["kaynaklar"]
    assert k["sources"]["bayi.gece.logo.aylik_satis.411.2026-01-01"]["sql"].startswith("USE [LOGODB];")
    assert "Segment" in k["formulas"]["skor"]["text"] and "kural sürüm" in k["formulas"]["skor"]["text"]
    assert k["sources"]["bayi.seri"]["origin"]                                      # seri tablosunun kökeni çalışan Logo metni
