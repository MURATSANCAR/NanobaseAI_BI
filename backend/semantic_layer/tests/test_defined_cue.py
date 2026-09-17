"""2026-09-17, soru 16: "Kartında indirim yüzdesi tanımlı müşteriler gerçekte ortalama ne kadar iskonto alıyor?"
'tanımlı' after a column names a condition on that column; 'gerçekte' says nothing about the catalog."""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import Mapping, SemanticType
from semantic_layer.runtime.compiler import DeterministicCompiler
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 17)


def _resolver(catalog, profiles):
    _certify(catalog, "kartında tanımlı iskonto", SemanticType.COLUMN, Mapping(concept_id="", entity="CLCARD", table_pattern="LG_{n0}_CLCARD",
             column="SPECODE2", operator="COLUMN"), synonyms=["kartında indirim yüzdesi"])
    _certify(catalog, "iskonto oranı", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
             formula="SUM(CASE WHEN STLINE.LINETYPE = 2 THEN STLINE.TOTAL ELSE 0 END) / NULLIF(SUM(CASE WHEN STLINE.LINETYPE = 0 THEN STLINE.TOTAL ELSE 0 END), 0)",
             extra={"conditions": ["STLINE.TRCODE IN (7,8)"]}), synonyms=["iskonto"])
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    return SemanticResolver(catalog, TENANT, DS, profiles)


def test_a_defined_word_after_a_column_is_a_non_empty_condition_on_it(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("Kartında indirim yüzdesi tanımlı müşteriler gerçekte ortalama ne kadar iskonto alıyor?", today=TODAY)
    defined = [s for s in sq.slots if (s.explain or {}).get("source") == "defined_cue"]
    assert defined and defined[0].mapping.column == "SPECODE2" and defined[0].mapping.operator == "<>", [(s.term, s.semantic_type) for s in sq.slots]
    assert "tanimli" not in sq.unresolved and "gercekte" not in sq.unresolved, sq.unresolved


def test_the_defined_column_question_compiles_without_the_model(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("Kartında indirim yüzdesi tanımlı müşteriler gerçekte ortalama ne kadar iskonto alıyor?", today=TODAY)
    out = DeterministicCompiler(profiles, {}, "tsql").compile(sq, catalog)
    assert out is not None, sq.to_dict()
    up = out.sql.upper().replace("[", "").replace("]", "")
    assert "CLCARD.SPECODE2 <> ''" in up, out.sql


def test_columns_named_beside_a_measure_are_its_breakdown(catalog, profiles):
    """The measure is asked per customer, with the card's rate beside it — not one average of everyone."""
    sq = _resolver(catalog, profiles).resolve("Kartında indirim yüzdesi tanımlı müşteriler gerçekte ortalama ne kadar iskonto alıyor?", today=TODAY)
    assert "SPECODE2" in {g.mapping.column for g in sq.group_by}, [(g.term, g.mapping.column) for g in sq.group_by]
    out = DeterministicCompiler(profiles, {}, "tsql").compile(sq, catalog)
    assert out is not None and "GROUP BY" in out.sql.upper(), (sq.to_dict(), out.sql if out else None)
