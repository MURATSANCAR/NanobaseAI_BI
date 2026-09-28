"""Sorgu bilgisi — uyarılar: kural listesi, «hepsini kontrol et» özeti, eşik önerisi.

«Son değer» kuralın sorusunun son kontrolde koşan FİZİKSEL SQL'inden gelir; kontrol bu metni (satır, süre, zaman)
kural kaydına yazar. Eski ölçümde metin yoksa pencere «bir sonraki kontrolde yazılır» der (sessiz geçmez).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from semantic_bridge import alerts as A
from semantic_bridge import alerts_kaynak as AK
from semantic_bridge import provenance as P
from semantic_layer.store.catalog_store import open_store

T, D, OWNER = "t1", "logo", "murat"
PHYS = "SELECT SUM(I.[NETTOTAL]) AS iade FROM [dbo].[LG_411_01_INVOICE] AS I WHERE I.[TRCODE] IN (2,3)"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    A._ready.discard(id(e))
    A.ensure(e)
    return e


def _rule(engine, **kw):
    body = {"title": "İade tutarı", "question": "bu ay iade tutarı", "condition": "gt", "threshold": 100,
            "recipients": ["cfo@example.com"], **kw}
    return A.create_rule(engine, T, D, body, by=OWNER)


def _answer(v, **extra):
    return lambda rule: {"records": [{"iade": v}], "sql": "SELECT iade FROM satis", "physicalSql": PHYS,
                         "totalRows": 1, "dbMs": 320, "computedAt": 1790000000.0, **extra}


def _ok(out):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out) == []
    assert P.problems(out) == []
    json.dumps(out, default=str)
    return k


def test_list_shows_the_physical_sql_of_the_last_check(engine):
    r = _rule(engine)
    A.check(engine, T, D, _answer(150), lambda rule, v: "sent", now=datetime(2026, 9, 28, 9, tzinfo=timezone.utc))
    out = {"user": OWNER, "alerts": A.list_rules(engine, T, D, OWNER), "email": A.email_status()}
    k = _ok(P.ekle(out, AK.for_list(engine, T, D, OWNER, out, "TIGERDB", "CRMDB")))
    src = k["sources"][f"uyari.{r['id']}"]
    assert src["sql"].startswith("USE [TIGERDB];") and "LG_411_01_INVOICE" in src["sql"]
    assert "SELECT iade FROM satis" not in json.dumps(k)  # mantıksal metin gösterilmez
    assert src["stats"]["rows"] == 1 and src["stats"]["dbMs"] == 320
    assert k["fields"][f"alerts[]:{r['id']}"] == f"hesap:kural:{r['id']}"
    assert "semantic_alert_rules" in k["sources"]["portal.uyari.kurallar"]["sql"]


def test_rule_measured_before_this_version_says_so(engine):
    r = _rule(engine)
    A.check(engine, T, D, lambda rule: {"records": [{"iade": 150}], "dbMs": 5}, lambda rule, v: "sent")
    out = {"user": OWNER, "alerts": A.list_rules(engine, T, D, OWNER), "email": A.email_status()}
    k = _ok(P.ekle(out, AK.for_list(engine, T, D, OWNER, out, "TIGERDB", None)))
    assert "bir sonraki kontrolde" in k["formulas"][f"kural:{r['id']}"]["text"]


def test_check_summary_and_federated_rule(engine):
    _rule(engine)
    parts = [{"name": "satis", "source": "logo", "ms": 10, "sql": PHYS},
             {"name": "proje", "source": "crm", "ms": 4, "sql": "SELECT 1 AS x FROM [timas_mscrm].[dbo].[new_projeBase]"}]
    out = A.check(engine, T, D, _answer(150, dbParts=parts), lambda rule, v: "sent")
    k = _ok(P.ekle(out, AK.for_check(engine, T, D, None, out, "TIGERDB", "CRMDB")))
    assert k["fields"]["checked"] == "hesap:kontrol"
    assert {s["connection"] for s in k["sources"].values()} == {"portal", "logo", "crm"}


def test_suggestion_sources_are_the_history_reads():
    out = {"ok": True, "alt": 10.0, "ust": 30.0, "merkez": 20.0, "nokta": 18, "yontem": "mevsimsel",
           "kaynak": {"sql": [{"ad": "Gün gün geçmiş", "sql": "SELECT gun, deger FROM satis"}]},
           "fiziksel": [{"sql": PHYS, "rows": 700, "ms": 900, "at": 1790000000.0}],
           "oneri": {"esik": 30.0, "gerekce": "üst", "alt": 10.0, "ust": 30.0, "etiket": "Kurala göre öneri"}}
    k = _ok(P.ekle(dict(out), AK.for_suggest(out, "TIGERDB", None)))
    assert k["sources"]["oneri.gecmis1"]["stats"]["rows"] == 700
    with pytest.raises(P.ProvenanceError):
        AK.for_suggest({"ok": True, "alt": 1.0}, None, None)
