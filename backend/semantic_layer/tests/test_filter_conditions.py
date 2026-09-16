"""A named state that is several columns is written as all of them, spelled as the source spells them."""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, Mapping, SchemaProfile, SemanticType
from semantic_layer.runtime.compiler import DeterministicCompiler
from semantic_layer.runtime.guardrails import physicalize_sql
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401


def test_a_two_column_state_reaches_the_where_clause(catalog, profiles):
    _certify(catalog, "onay bekleyen toptan", SemanticType.DIMENSION_VALUE,
             Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE", column="TRCODE", operator="IN", values=["8"],
                     extra={"conditions": ["INVOICE.CANCELLED IN (0)", "INVOICE.NETTOTAL IN (0)"]}))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Onay bekleyen toptan kaç tane?", today=date(2026, 9, 16))
    out = DeterministicCompiler(profiles, {}, "tsql").compile(sq, catalog)
    assert out is not None, sq.to_dict()
    low = out.sql.upper()
    assert "TRCODE" in low and "IN (8)" in low, out.sql
    assert "[NETTOTAL] IN (0)" in out.sql and "[CANCELLED] IN (0)" in out.sql, out.sql


def test_columns_are_spelled_as_the_source_spells_them():
    crm = SchemaProfile(datasource_id="d", table_name="new_sozlesmeBase", table_pattern="new_sozlesmeBase", entity="NEW_SOZLESMEBASE",
                        schema_name="Timas_MSCRM.dbo", columns=[ColumnProfile(name="statecode", data_type="int"), ColumnProfile(name="new_sozlesmeId", data_type="uniqueidentifier")])
    sql = physicalize_sql('SELECT COUNT(DISTINCT NEW_SOZLESMEBASE."NEW_SOZLESMEID") AS n FROM Timas_MSCRM_dbo_new_sozlesmeBase AS NEW_SOZLESMEBASE WHERE NEW_SOZLESMEBASE."STATECODE" IN (0)',
                          [crm], {}, "tsql")
    assert "[statecode]" in sql and "[new_sozlesmeId]" in sql and "STATECODE" not in sql, sql
