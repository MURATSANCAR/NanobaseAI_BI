"""Sorgu bilgisi — kişisel pano ve planlı raporlar.

Kartın ve planın saklı SQL'i mantıksaldır; gösterilen/kopyalanan metin köprünün son koşuda veritabanında koşturduğu
fiziksel SQL'dir (sonuçla birlikte saklanır). Eski sonuçta metin yoksa pencere bunu söyler.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import board as B
from semantic_bridge import board_kaynak as BK
from semantic_bridge import provenance as P
from semantic_bridge import reports as R
from semantic_bridge import reports_kaynak as RK
from semantic_layer.store.catalog_store import open_store

T, D, U = "t1", "logo", "murat"
PHYS = ("SELECT MONTH(I.[DATE_]) AS ay, SUM(I.[NETTOTAL]) AS net FROM [dbo].[LG_411_01_INVOICE] AS I "
        "WHERE I.[DATE_] >= '2026-01-01' GROUP BY MONTH(I.[DATE_])")


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for mod in (B, R):
        mod._ready.discard(id(e))
    B.ensure(e)
    R.ensure(e)
    return e


def _ok(out, ignore=()):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    json.dumps(out, default=str)
    return k


def _card(cid="k1"):
    return {"id": cid, "title": "Aylık net ciro", "question": "aylık net ciro", "sql": "SELECT ay, net FROM satis",
            "chart": "column", "x": 10, "y": 20, "w": 460, "h": 300, "z": 21}


def test_board_card_shows_physical_sql_of_last_run(engine):
    B.save_cards(engine, T, D, U, [_card("k1"), _card("k2")])
    run = lambda sql: {"columns": [{"name": "ay"}, {"name": "net"}], "records": [{"ay": 1, "net": 10.5}],  # noqa: E731
                       "totalRows": 1, "dbMs": 70, "computedAt": 1790000000.0, "physicalSql": PHYS}
    res = B.run_card(engine, T, D, U, "k1", run)
    cards = B.list_cards(engine, T, D, U)
    out = {"user": U, "cards": cards}
    k = _ok(P.ekle(out, BK.for_cards(engine, T, D, U, cards, "TIGERDB", None)), BK.NOT_RAKAM)
    src = k["sources"]["pano.k1"]
    assert src["sql"].startswith("USE [TIGERDB];") and "LG_411_01_INVOICE" in src["sql"]
    assert "SELECT ay, net FROM satis" not in json.dumps(k)
    assert "henüz hiç koşmadı" in k["formulas"]["kart:k2"]["text"]
    assert "semantic_board_cards" in k["sources"]["portal.pano"]["sql"]
    one = dict(res)
    _ok(P.ekle(one, BK.for_run("k1", res, "TIGERDB", None)), ("at",))


def test_board_result_from_before_this_version(engine):
    B.save_cards(engine, T, D, U, [_card()])
    with engine.begin() as c:
        c.execute(B.CARDS.update().values(result_json=json.dumps({"columns": [], "records": [{"n": 3}], "dbMs": 4}),
                                          result_at=datetime(2026, 9, 1, tzinfo=timezone.utc)))
    cards = B.list_cards(engine, T, D, U)
    k = _ok(P.ekle({"cards": cards}, BK.for_cards(engine, T, D, U, cards, None, None)), BK.NOT_RAKAM)
    assert "yenilenince" in k["formulas"]["kart:k1"]["text"]


def test_report_list_and_run(engine):
    rep = R.create_report(engine, T, D, U, {"title": "Aylık satış", "question": "aylık net ciro", "recurrence": "daily",
                                            "at": "08:00", "recipients": []})
    db = {"dbMs": 900, "cached": False, "computedAt": 1790000000.0, "physicalSql": PHYS, "rows": 12}
    with engine.begin() as c:
        c.execute(R.REPORTS.update().where(R.REPORTS.c.id == rep["id"]).values(
            last_db_json=json.dumps(db), last_rows=12, last_status="sent",
            last_run_at=datetime(2026, 9, 28, 8, tzinfo=timezone.utc)))
    reports = R.list_reports(engine, T, D, U)
    out = {"user": U, "reports": reports}
    k = _ok(P.ekle(out, RK.for_list(engine, T, D, U, reports, "TIGERDB", None)), RK.NOT_RAKAM)
    assert k["sources"][f"rapor.{rep['id']}"]["stats"]["rows"] == 12
    single = dict(reports[0])
    _ok(P.ekle(single, RK.for_report(engine, T, D, U, single, "TIGERDB", None)))


def test_report_preview_uses_answer_physical_sql():
    answer = {"type": "TEXT_TO_SQL", "sql": "SELECT ay FROM satis", "physicalSql": PHYS, "totalRows": 240,
              "dbMs": 50, "computedAt": 1790000000.0}
    out = {"question": "aylık", "sql": "SELECT ay FROM satis", "physicalSql": PHYS, "columns": [{"name": "ay"}],
           "records": [{"ay": m} for m in range(1, 13)], "rowCount": 240, "summary": "", "layout": [], "added": [],
           "dropped": [], "dbMs": 50, "cached": False, "computedAt": 1790000000.0}
    k = _ok(P.ekle(out, RK.for_preview(out, answer, "TIGERDB", None)))
    assert k["sources"]["onizleme"]["stats"]["rows"] == 240
    with pytest.raises(P.ProvenanceError):
        RK.for_preview(out, {**answer, "physicalSql": None}, None, None)


def test_list_statements_are_the_executed_reads(engine):
    text = P.portal_sql(R.list_stmt(T, D, U), engine)
    assert "semantic_reports" in text and "'murat'" in text
    assert isinstance(B.list_stmt(T, D, U), sa.sql.Select)
