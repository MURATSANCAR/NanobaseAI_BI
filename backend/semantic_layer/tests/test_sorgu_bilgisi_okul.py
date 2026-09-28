"""M31 Okul tanıtım: her rakamın sorgu bilgisi. CRM/Logo rakamlarının SQL'i okumada ÇALIŞAN metindir (anahtarıyla,
veritabanı adıyla, satır/süre/anla); portal kayıtları uçta çalışan ifade; puan, sayaç ve dönem raporu formülle."""
from __future__ import annotations

from datetime import date

from semantic_bridge import provenance as P
from semantic_bridge import school_visits as SV
from semantic_bridge import school_visits_api as API
from semantic_bridge import school_visits_kaynak as K
from semantic_bridge import school_visits_sources as src
from semantic_bridge.management.kaynak import is_template
from semantic_layer.tests.test_school_visits import S1, T, _settings, _snap, engine  # noqa: F401 — fikstür


def _check(out):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [] and not is_template(s["sql"])
    return k


# ---------------------------------------------------------------- okuma: çalışan SQL kaydı


class _Conn:
    def __init__(self, db: str):
        self.cfg = {"database": db, "password": "gizli-deger", "host": "10.0.0.1"}
        self.sql: list[str] = []

    def execute(self, sql, limit):
        self.sql.append(sql)
        if "L_CAPIPERIOD" in sql:
            return ["x"], [{"FIRMNR": 411, "BEGDATE": "2026-01-01", "ENDDATE": "2026-12-31"}], False
        return ["x"], [], False

    def close(self):
        pass


def test_read_records_every_executed_sql_with_key_and_database_name_only():
    crm, logo = _Conn("CRMDB"), _Conn("LOGODB")
    s = src.Source(lambda: crm, lambda: logo, lambda: "Timas_MSCRM.dbo", lambda: _settings())
    snap = s.read()
    q = snap["sorgular"]
    keys = [x["key"] for x in q]
    assert keys[:8] == ["okullar", "ziyaretler", "bayi_gecmisi", "siparisler", "bayiler", "kitaplar", "kullanicilar", "ilceler"]
    assert {"donemler", "stok", "fiyat", "cariler", "bayi_satisi", "bayi_aylik"} <= set(keys)
    assert [x["sql"] for x in q if x["conn"] == "crm"] == crm.sql and [x["sql"] for x in q if x["conn"] == "logo"] == logo.sql
    assert {x["db"] for x in q} == {"CRMDB", "LOGODB"}
    assert "gizli-deger" not in repr(q) and "10.0.0.1" not in repr(q)
    assert all(x["rows"] is not None and x["at"] for x in q)


# ---------------------------------------------------------------- uçlar


class _Src:
    def __init__(self):
        snap = _snap()
        snap["sorgular"] = [
            {"conn": "crm", "db": "CRMDB", "key": k, "sql": f"SELECT {k} FROM Timas_MSCRM.dbo.new_ziyaretyerleriBase", "rows": 3,
             "dbMs": 12, "at": "2026-09-28T09:00:00+03:00"}
            for k in ("okullar", "ziyaretler", "bayi_gecmisi", "siparisler", "bayiler", "kitaplar", "kullanicilar", "ilceler")
        ] + [
            {"conn": "logo", "db": "LOGODB", "key": k, "sql": f"SELECT {k} FROM dbo.LG_411_01_STLINE", "rows": 5, "dbMs": 30,
             "at": "2026-09-28T09:00:01+03:00"}
            for k in ("donemler", "stok", "fiyat", "cariler", "bayi_satisi", "bayi_aylik")
        ]
        self.snap = snap

    def snapshot(self, fresh=False):
        return self.snap


def _svc():
    return API.Service(_Src(), lambda: _settings(), lambda _p: None)


def test_list_card_plan_queue_dealers_visits(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(SV, "today", lambda: date(2026, 9, 28))
    svc = _svc()
    SV.sync_history_links(engine, T, svc.model(engine, T))
    lst = svc.list(engine, T, "ayse", True)
    k = _check(P.ekle(lst, K.for_list(engine, T, svc.current(), lst)))
    assert k["sources"]["okul.okullar"]["sql"].startswith("USE [CRMDB];")
    assert k["sources"]["okul.okullar"]["stats"]["rows"] == 3
    assert "Ağırlıklar" in k["formulas"]["puan"]["text"]
    card = svc.card(engine, T, "ayse", True, S1)
    k = _check(P.ekle(card, K.for_card(engine, T, svc.current(), S1, card)))
    assert k["sources"]["okul.stok"]["sql"].startswith("USE [LOGODB];")
    assert {"school", "score", "fittingBooks", "orders", "crmDoneLinked"} <= set(k["fields"])
    plan = svc.plan(engine, T, "ayse", True, date(2026, 9, 28), None, True)
    _check(P.ekle(plan, K.for_plan(engine, T, svc.current(), date(2026, 9, 28), plan["owner"], plan)))
    q = svc.queue(engine, T)
    _check(P.ekle(q, K.for_queue(engine, T, svc.current(), q)))
    d = svc.dealers(engine, T, S1)
    k = _check(P.ekle(d, K.for_dealers(engine, T, svc.current(), S1, d)))
    assert "okul.bayi_satisi" in k["formulas"]["bayi_aday"]["inputs"]
    v = svc.visits(engine, T, "ayse", True, S1)
    _check(P.ekle(v, K.for_visits(engine, T, svc.current(), S1, v)))
    cat = svc.catalog(engine, T, "ayse", S1, {"siniflar": [1, 2], "adet": "hepsi", "onizleme": True})
    _check(P.ekle(cat, K.for_catalog(engine, T, svc.current(), cat)))


def test_term_context_meta(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(SV, "today", lambda: date(2026, 9, 28))
    svc = _svc()
    tr = svc.term_report(engine, T, "ayse", True, "2025-2026")
    a, b = SV.term_range(tr["term"])
    k = _check(P.ekle(tr, K.for_term(engine, T, svc.current(), tr, a, b, tr["owner"])))
    assert {"plans", "visits", "orders", "samples", "conversion", "byIl", "byOwner"} <= set(k["fields"])
    ctx = SV.load_context(engine, T)
    out = {"uploads": list(ctx["uploads"].values()), "calendar": ctx["takvim"], "districts": [], "range": ctx["endeksRange"]}
    _check(P.ekle(out, K.for_context(engine, T, svc.current(), out)))
    meta = {"weights": [{"key": "ogrenci", "label": "Öğrenci", "max": 30}], "status": {"schools": 3},
            "settings": {"planSize": 10}, "uploads": []}
    _check(P.ekle(meta, K.for_meta(engine, T, svc.current(), meta)))


def test_old_snapshot_without_reads_says_so_instead_of_inventing(engine):  # noqa: F811
    svc = _svc()
    svc.source.snap.pop("sorgular")
    lst = svc.list(engine, T, "ayse", True)
    out = P.bagla(lst, lambda: K.for_list(engine, T, svc.current(), lst))
    assert out["kaynaklar"]["error"] and out["items"]  # rakamlar düşmez, «hazırlanamadı» görünür
