"""Sorgu bilgisi — uç süsleyicisi `sorgu_izi.izlenir` (editoryal, çeviri, masa, stüdyo uçları) ve Logo/CRM metin izi.

Kritik: `from __future__ import annotations` olan modülde süslenen uçta «Request» türü metin kalırsa FastAPI onu sorgu
parametresi sanar ve her istek 422'ye düşer. Süsleyici türleri asıl fonksiyonun modülünde çözer; bu test onu bekler.
"""
from __future__ import annotations

import inspect
import json
from typing import Any

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from semantic_bridge import provenance as P
from semantic_bridge import sorgu_izi as IZ
from semantic_layer.store.catalog_store import open_store

_md = sa.MetaData()
T = sa.Table("semantic_deneme_isler", _md, sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("kelime", sa.Integer))


def _engine():
    e = open_store("sqlite://").engine
    _md.create_all(e)
    with e.begin() as c:
        c.execute(T.insert(), [{"id": 1, "kelime": 1200}, {"id": 2, "kelime": 800}])
    return e


def test_decorated_endpoint_keeps_request_type_and_returns_sources():
    e = _engine()
    app = FastAPI()

    @app.get("/isler")
    @IZ.izlenir("portal.deneme", "Deneme işleri", "Toplam kelime = Σ kelime.", engine=lambda: e,
                dbs=lambda: ("TIGERDB", "CRMDB"))
    def isler(request: Request, sayfa: int = 0) -> dict[str, Any]:
        with e.connect() as c:
            rows = c.execute(sa.select(T.c.kelime).where(T.c.id > sayfa)).all()
        IZ.dis("logo", "SELECT 1 AS n FROM dbo.LG_411_01_INVOICE WHERE 1 = 1", rows=1, ms=3)
        return {"toplam": sum(r[0] for r in rows), "adet": len(rows)}

    assert inspect.signature(isler).parameters["request"].annotation is Request
    res = TestClient(app).get("/isler?sayfa=0")
    assert res.status_code == 200, res.text
    out = res.json()
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out) == [] and P.problems(out) == []
    conns = {s["connection"] for s in k["sources"].values()}
    assert conns == {"portal", "logo"}
    portal = [s for s in k["sources"].values() if s["connection"] == "portal"][0]
    assert "semantic_deneme_isler" in portal["sql"] and "> 0" in portal["sql"]
    logo = [s for s in k["sources"].values() if s["connection"] == "logo"][0]
    assert logo["sql"].startswith("USE [TIGERDB];")
    assert k["fields"]["_hepsi"] == "hesap:portal.deneme"


def test_async_endpoint_and_external_only_source():
    app = FastAPI()

    @app.get("/studyo")
    @IZ.izlenir("portal.studyo", "Stüdyo", "Sayfa sayısı servisin kaydından.", engine=None, dbs=lambda: (None, None),
                dis_adi="Kitap tasarım servisi (işin kendi kaydı)")
    async def studyo(request: Request) -> dict[str, Any]:
        return {"sayfa": 32}

    out = TestClient(app).get("/studyo").json()
    k = out["kaynaklar"]
    assert P.uncovered_numbers(out) == [] and P.problems(out) == []
    assert any(f.get("external") for f in k["formulas"].values())


def test_non_dict_response_is_untouched():
    @IZ.izlenir("x", "x", "x", engine=None, dbs=lambda: (None, None))
    def dosya(request: Request) -> Any:
        return b"%PDF"

    assert dosya(None) == b"%PDF"


def test_tam_kaynak_with_cache_origin_rows():
    got = [{"connection": "crm", "sql": "SELECT p.new_name FROM Timas_MSCRM.dbo.new_projeBase AS p", "rows": 40,
            "ms": 120, "at": 1790000000.0}]
    out = {"items": [{"n": 3}], "toplam": 40}
    k = IZ.tam_kaynak(None, [], [], out, prefix="crm.deneme", title="Projeler", text="Proje sayısı.", logo_db=None,
                      crm_db="CRMDB", onceki=got)
    o = P.ekle(out, k)
    assert P.uncovered_numbers(o) == [] and P.problems(o) == []
    src = list(k.sources.values())[0]
    assert src["stats"]["rows"] == 40 and "önbelle" in src["title"].lower()
    json.dumps(o, default=str)
