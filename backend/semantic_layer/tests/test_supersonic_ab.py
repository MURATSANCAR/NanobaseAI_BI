"""SuperSonic adapter + A/B plumbing, tested against a fake service (no Java, no network).

What is asserted: the SemanticQuery is translated into a struct query carrying our certified meaning,
the returned SQL is wrapped as a CompiledQuery, a missing dataSet mapping makes the adapter fall
through instead of guessing, and a shadow compiler never changes the production answer.
"""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ConceptStatus, Evidence, EvidenceType, Mapping, SemanticType
from semantic_layer.runtime.compiler import CompilerRouter, DeterministicCompiler, default_filters_provider
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.supersonic import (
    SuperSonicClient,
    SuperSonicCompilerAdapter,
    SuperSonicSettings,
    export_semantic_model,
    extract_sql,
)
from semantic_layer.tests.conftest import DS, TENANT


class FakeSuperSonic:
    """Implements the documented struct-query contract: metrics + dimensions + filters + dateInfo → SQL."""

    def __init__(self, dataset_table: dict[int, str]):
        self.dataset_table = dataset_table
        self.calls: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"data": {"token": "tok-123"}})
        self.calls.append(body)
        table = self.dataset_table.get(body.get("dataSetId"))
        if table is None:
            return httpx.Response(200, json={"code": 400, "msg": "unknown dataSet"})
        select = ", ".join(body.get("dimensions") or []) or "1"
        metrics = ", ".join(body.get("metrics") or [])
        where = " AND ".join(
            f"{f['name']} {f['operator']} ({', '.join(map(str, f['value']))})" for f in body.get("dimensionFilters") or []
        )
        date_info = body.get("dateInfo") or {}
        if date_info:
            where = (where + " AND " if where else "") + f"date BETWEEN '{date_info['startDate']}' AND '{date_info['endDate']}'"
        sql = f"SELECT {select}, {metrics} FROM {table}" + (f" WHERE {where}" if where else "")
        return httpx.Response(200, json={"code": 200, "data": {"querySQL": sql}})


@pytest.fixture
def adapter():
    fake = FakeSuperSonic({7: "invoice_dataset"})
    settings = SuperSonicSettings(base_url="http://supersonic.test", user="u", password="p", datasets={"INVOICE": 7}, date_field={"INVOICE": "invoice_date"})
    client = SuperSonicClient(settings, transport=httpx.MockTransport(fake.handler))
    return SuperSonicCompilerAdapter(client, settings), fake


@pytest.fixture
def catalog(store, profiles):
    for p in profiles:
        store.upsert_profile(p)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    clc = next(p for p in profiles if p.entity == "CLCARD")

    def certify(term, stype, mapping):
        c, _ = store.upsert_concept(TENANT, DS, term, stype, mapping=mapping, status=ConceptStatus.CANDIDATE)
        store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "hm", support_count=3, payload={"pairs": ["a", "b", "c"], "precision": 1.0}))
        return c

    certify("net ciro", SemanticType.METRIC, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, formula="SUM(INVOICE.NETTOTAL)", extra={"conditions": ["INVOICE.TRCODE IN (7,8,9)"]}))
    certify("toptan", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="TRCODE", operator="IN", values=["8"]))
    certify("kanal", SemanticType.COLUMN, Mapping(concept_id="", entity="CLCARD", table_pattern=clc.table_pattern, column="SPECODE2", operator="COLUMN"))
    EvidenceEngine(store, min_support=3).run(TENANT, DS, profiles)
    return store


def test_struct_query_carries_certified_meaning(adapter, catalog, profiles):
    comp, fake = adapter
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    q = r.resolve("Kanal bazında 2026 toptan net ciro", today=date(2026, 9, 6))
    struct, why = comp.build_struct(q)
    assert why == "ok" and struct["dataSetId"] == 7
    assert struct["metrics"] == ["net ciro"] and struct["dimensions"] == ["kanal"]
    assert struct["dimensionFilters"][0]["name"] == "TRCODE" and struct["dimensionFilters"][0]["value"] == ["8"]
    assert struct["dateInfo"]["startDate"] == "2026-01-01" and struct["dateInfo"]["endDate"] == "2027-01-01"
    assert struct["dateInfo"]["dateField"] == "invoice_date"
    out = comp.compile(q, catalog)
    assert out is not None and out.compiler == "supersonic" and out.certified
    assert "invoice_dataset" in out.sql and "TRCODE IN (8)" in out.sql
    assert fake.calls and fake.calls[0]["sqlOnly"] is True


def test_adapter_falls_through_when_unmapped_or_broken(catalog, profiles):
    unmapped = SuperSonicSettings(base_url="http://supersonic.test", datasets={})
    comp = SuperSonicCompilerAdapter(SuperSonicClient(unmapped, transport=httpx.MockTransport(lambda r: httpx.Response(500))), unmapped)
    q = SemanticResolver(catalog, TENANT, DS, profiles).resolve("2026 net ciro", today=date(2026, 9, 6))
    assert comp.compile(q, catalog) is None                    # no dataSet → router continues, no guessing
    broken = SuperSonicSettings(base_url="http://supersonic.test", datasets={"INVOICE": 7})
    comp2 = SuperSonicCompilerAdapter(SuperSonicClient(broken, transport=httpx.MockTransport(lambda r: httpx.Response(503, json={"msg": "down"}))), broken)
    out = comp2.compile(q, catalog)
    assert out is not None and out.sql == "" and "SuperSonic hata" in out.explain[0]


def test_router_shadow_never_changes_the_answer(adapter, catalog, profiles):
    comp, _ = adapter
    det = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite", default_filters=default_filters_provider(catalog, TENANT, DS))
    router = CompilerRouter(det, None, shadow=[comp])
    q = SemanticResolver(catalog, TENANT, DS, profiles).resolve("2026 toptan net ciro", today=date(2026, 9, 6))
    out = router.compile(q, catalog)
    assert out.compiler == "deterministic" and "LG_411_01_INVOICE" in out.sql
    assert router.shadow_results and router.shadow_results[0]["compiler"] == "supersonic"
    assert router.shadow_results[0]["same_as_primary"] is False   # measured, not used
    pinned = CompilerRouter(det, None, primary="supersonic", alternates={"supersonic": comp})
    assert pinned.compile(q, catalog).compiler == "supersonic"    # explicit experiment only


def test_catalog_exports_as_supersonic_model(catalog, profiles):
    model = export_semantic_model(catalog, TENANT, DS, profiles, context={"n0": "411", "n1": "01"})
    invoice = next(m for m in model if m["name"] == "INVOICE")
    assert invoice["tableName"] == "LG_411_01_INVOICE"
    assert any(m["bizName"] == "net ciro" and m["expr"].startswith("SUM(") for m in invoice["metrics"])
    assert any(d["bizName"] == "toptan" and d["valueFilter"]["values"] == ["8"] for d in invoice["dimensions"])
    clcard = next(m for m in model if m["name"] == "CLCARD")
    assert any(d["bizName"] == "kanal" and d["expr"] == "SPECODE2" for d in clcard["dimensions"])


def test_extract_sql_handles_release_variants():
    assert extract_sql({"data": {"querySQL": "SELECT 1;"}}) == "SELECT 1"
    assert extract_sql({"data": {"s2SQL": "SELECT 2"}}) == "SELECT 2"
    assert extract_sql({"sql": "SELECT 3"}) == "SELECT 3"
    assert extract_sql({"data": {"msg": "no sql"}}) is None
