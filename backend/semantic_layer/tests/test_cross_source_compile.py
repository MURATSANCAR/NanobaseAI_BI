"""Ölçülmüş bir veritabanları arası bağ derlendiğinde geçerli T-SQL çıkmalı.

Üç şey sessizce bozuluyordu: metinde saklı sayı ile tamsayı anahtar karşılaştırması (dönüştürme hatası),
iki farklı harmanlamanın karşılaştırılması (SQL Server reddeder) ve yıl kopyalı hedefe yalnız bir
yılın bağlanması (öteki yılların satırları iç join'de kaybolur).
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, Mapping, SchemaProfile, SemanticType, TemporalSlot, utcnow
from semantic_layer.runtime.compiler import DeterministicCompiler
from semantic_layer.runtime.guardrails import allowed_tables
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify

OTHER_DB = "OtherDb.dbo"


def _world(store, profiles):
    inv = next(p for p in profiles if p.entity == "INVOICE")
    old_inv = deepcopy(inv)
    old_inv.table_name, old_inv.context, old_inv.scanned_at = "LG_211_01_INVOICE", {"n0": "211", "n1": "01"}, utcnow()
    old_inv.time_window = ("2021-01-01", "2025-12-31")
    inv.time_window = ("2026-01-01", "2026-12-31")
    old_card = deepcopy(next(p for p in profiles if p.entity == "CLCARD"))
    old_card.table_name, old_card.context, old_card.scanned_at = "LG_211_CLCARD", {"n0": "211"}, utcnow()
    ship = SchemaProfile(
        datasource_id=DS, table_name="ShipmentBase", table_pattern="SHIPMENTBASE", entity="SHIPMENTBASE", schema_name=OTHER_DB,
        columns=[ColumnProfile("ShipmentId", "uniqueidentifier", is_primary_key=True), ColumnProfile("invoice_no", "nvarchar(100)"),
                 ColumnProfile("createdon", "datetime"), ColumnProfile("qty", "int")],
        primary_key=["ShipmentId"], row_count=1000, time_window=("2019-01-01", "2026-09-01"),
        relationships=[{"column": "invoice_no", "ref_entity": "INVOICE", "ref_column": "FICHENO", "source": "cross-source-overlap",
                        "join_cast": None, "join_collate": True, "period_semantics": "periodic"}])
    acc = SchemaProfile(
        datasource_id=DS, table_name="AccountBase", table_pattern="ACCOUNTBASE", entity="ACCOUNTBASE", schema_name=OTHER_DB,
        columns=[ColumnProfile("AccountId", "uniqueidentifier", is_primary_key=True), ColumnProfile("erp_ref", "nvarchar(100)"),
                 ColumnProfile("creditlimit", "money")],
        primary_key=["AccountId"], row_count=100,
        relationships=[{"column": "erp_ref", "ref_entity": "CLCARD", "ref_column": "LOGICALREF", "source": "cross-source-overlap",
                        "join_cast": "int", "join_collate": False, "period_semantics": "replicated"}])
    allp = profiles + [old_inv, old_card, ship, acc]
    for p in allp:
        store.upsert_profile(p)
    _certify(store, "sevkiyat adedi", SemanticType.METRIC, Mapping(concept_id="", entity="SHIPMENTBASE", table_pattern="SHIPMENTBASE", formula="SUM(SHIPMENTBASE.qty)"))
    _certify(store, "fatura turu", SemanticType.COLUMN, Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE", column="TRCODE", operator="COLUMN"))
    _certify(store, "kredi limiti", SemanticType.METRIC, Mapping(concept_id="", entity="ACCOUNTBASE", table_pattern="ACCOUNTBASE", formula="SUM(ACCOUNTBASE.creditlimit)"))
    _certify(store, "kanal", SemanticType.COLUMN, Mapping(concept_id="", entity="CLCARD", table_pattern="LG_{n0}_CLCARD", column="SPECODE2", operator="COLUMN"))
    EvidenceEngine(store, min_support=3).run(TENANT, DS, allp)
    return allp


def test_a_reference_into_period_tables_joins_every_period_with_a_named_collation(store, profiles):
    allp = _world(store, profiles)
    r = SemanticResolver(store, TENANT, DS, allp)
    c = DeterministicCompiler(allp, {}, "tsql")
    sq = r.resolve("fatura turu bazında sevkiyat adedi", today=date(2026, 7, 20))
    sq.temporal = [TemporalSlot(text="2025-2026", primitive="RANGE", start=date(2025, 1, 1), end=date(2027, 1, 1))]
    out = c.compile(sq, store)
    assert out is not None, c.plan(sq)
    assert "[OtherDb].[dbo].[ShipmentBase]" in out.sql
    assert "LG_211_01_INVOICE" in out.sql and "LG_411_01_INVOICE" in out.sql and "UNION ALL" in out.sql, out.sql
    assert "SHIPMENTBASE.[INVOICE_NO] COLLATE DATABASE_DEFAULT = INVOICE.[FICHENO]" in out.sql, out.sql
    assert allowed_tables(out.sql, allp, {}, "tsql") == (True, "ok")


def test_an_integer_kept_as_text_is_cast_and_a_replicated_target_is_read_once(store, profiles):
    allp = _world(store, profiles)
    r = SemanticResolver(store, TENANT, DS, allp)
    c = DeterministicCompiler(allp, {}, "tsql")
    sq = r.resolve("kanal bazında kredi limiti", today=date(2026, 7, 20))
    out = c.compile(sq, store)
    assert out is not None, c.plan(sq)
    assert "TRY_CAST(ACCOUNTBASE.[ERP_REF] AS int) = CLCARD.[LOGICALREF]" in out.sql, out.sql
    assert ("LG_211_CLCARD" in out.sql) != ("LG_411_CLCARD" in out.sql), out.sql       # kopyalardan yalnız biri


def test_the_model_is_told_how_to_compare_a_measured_link():
    from semantic_layer.runtime.compiler import _join_note
    note = _join_note({"column": "erp_ref", "join_cast": "int", "join_collate": True, "period_semantics": "periodic"})
    assert "TRY_CAST(erp_ref AS int)" in note and "COLLATE DATABASE_DEFAULT" in note and "dönem" in note
    assert _join_note({"column": "x"}) == ""
