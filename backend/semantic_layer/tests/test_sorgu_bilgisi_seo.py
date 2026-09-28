"""Sorgu bilgisi — SEO & GEO (G5 yayılımı): ara katman her okuma ucunun cevabına «kaynaklar» ekler.

Denetlenen: (1) her SEO & GEO GET ucunun (dosya indirmeleri ve /me hariç) sorgu bilgisi tanımı var — yeni uç eklenip
tanımı yazılmazsa test düşer; (2) uç cevabında kaynaksız rakam yok, SQL o istekte koşan metin (değerler yerinde);
(3) ara katman öbür yollara dokunmaz; (4) CRM'den dolan tablonun asıl CRM sorgusu köken olarak eklenir.
Kabul (gerçek veriyle): `scripts/acceptance/sorgu-bilgisi/g5_seo.py`.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from sqlalchemy import event
from fastapi.testclient import TestClient

from semantic_bridge import provenance as P
from semantic_bridge import seo_geo
from semantic_bridge.seo_geo import kaynak as K
from semantic_layer.store.catalog_store import open_store

T = "t1"


def _regexp_replace(s, pattern, repl, flags=""):
    return None if s is None else re.sub(pattern, repl, s, count=0 if "g" in (flags or "") else 1)


def _pg_functions(dbapi_conn, _rec=None):
    """Canlı veritabanında olan regexp_replace test veritabanında yok: aynı davranışla tanımlanır."""
    dbapi_conn.create_function("regexp_replace", 4, _regexp_replace)


@pytest.fixture
def client():
    eng = open_store("sqlite://").engine
    event.listen(eng, "connect", _pg_functions)
    with eng.connect() as c:                 # bellek içi veritabanının açık bağlantısına da
        _pg_functions(c.connection.driver_connection)
    rt = SimpleNamespace(store=SimpleNamespace(engine=eng), settings=SimpleNamespace(tenant_id=T, connection_file=""),
                         llm=None, llm_for=lambda *a, **k: None)
    app = FastAPI()

    @app.get("/api/v1/baska/uc")
    def other() -> dict:
        return {"sayi": 5}

    seo_geo.register(app, runtime=lambda: rt, authorize=lambda r: None, session_user=lambda r: "ayse")
    return TestClient(app, raise_server_exceptions=False), eng


def _get_paths(app: FastAPI) -> list[str]:
    return sorted({r.path for r in app.routes if "GET" in getattr(r, "methods", ()) and r.path.startswith(K.PREFIX)})


def test_every_seo_read_endpoint_has_a_spec(client):
    c, _ = client
    missing = [p for p in _get_paths(c.app) if not re.search(r"\.(csv|tsv|md|html|pdf|xml|json)$|/me$", p)
               and K.spec_for(re.sub(r"\{[^}]+\}", "x", p)) is None]
    assert not missing, missing


def test_other_paths_are_untouched(client):
    c, _ = client
    assert c.get("/api/v1/baska/uc").json() == {"sayi": 5}


def test_seo_responses_carry_sources(client):
    c, _ = client
    done, no_read = [], []
    for p in _get_paths(c.app):
        if "{" in p or K.spec_for(p) is None:
            continue
        r = c.get(p)
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("application/json"):
            continue
        data = r.json()
        if not isinstance(data, dict):
            continue
        k = data.get("kaynaklar")
        assert k is not None, p
        if k.get("error"):
            no_read.append(p)          # bu istekte veritabanı okuması yok (dış servis/bellek): pencere nedenini yazar
            continue
        assert P.uncovered_numbers(data) == [], p
        assert P.problems(data) == [], (p, P.problems(data))
        for s in k["sources"].values():
            assert s["connection"] in ("portal", "crm", "logo") and P.placeholders_left(s["sql"]) == [], (p, s)
        done.append(p)
    assert "/api/v1/seo-geo/overview" in done and len(done) >= 10, (done, no_read)


def test_overview_sql_is_the_executed_statement_with_values(client):
    c, _ = client
    k = c.get("/api/v1/seo-geo/overview").json()["kaynaklar"]
    sqls = [s["sql"] for s in k["sources"].values()]
    assert any("semantic_seo_products" in s and "'t1'" in s for s in sqls)
    assert all("?" not in P._STRING_OR_COMMENT.sub(" ", s) for s in sqls)
    assert k["fields"]["products"].startswith("hesap:")


def test_crm_table_gets_its_crm_origin(client, monkeypatch):
    c, eng = client
    monkeypatch.setattr(seo_geo.SeoGeo, "conf", staticmethod(lambda key: "Timas_MSCRM.dbo" if key == "CRM_SCHEMA" else ""))
    data = c.get("/api/v1/seo-geo/crm").json()
    k = data["kaynaklar"]
    if k.get("error"):
        pytest.skip(k["error"])
    crm_tbl = [s for s in k["sources"].values() if "semantic_seo_crm_books" in s["sql"]]
    assert crm_tbl and any(k["sources"][o]["connection"] == "crm" for s in crm_tbl for o in s["origin"])
    assert "Timas_MSCRM" in json.dumps(k)
