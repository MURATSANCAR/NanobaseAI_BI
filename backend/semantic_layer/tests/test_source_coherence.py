"""A question written about one database is not pulled into the other by a single certified word."""
from __future__ import annotations

from datetime import date

from semantic_layer.models import ColumnProfile, Mapping, SchemaProfile, SemanticType
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 16)


def scenario():
    return SchemaProfile(datasource_id=DS, table_name="new_satissenaryosuBase", table_pattern="NEW_SATISSENARYOSUBASE",
                         entity="NEW_SATISSENARYOSUBASE", schema_name="Timas_MSCRM.dbo", description="Satış senaryosu",
                         columns=[ColumnProfile(name="new_toplamkar", data_type="money"), ColumnProfile(name="createdon", data_type="datetime")],
                         row_count=1200)


def _with_crm_profit(catalog, profiles):
    crm = scenario()
    catalog.upsert_profile(crm)
    _certify(catalog, "kar", SemanticType.COLUMN, Mapping(concept_id="", entity="NEW_SATISSENARYOSUBASE",
             table_pattern="NEW_SATISSENARYOSUBASE", column="NEW_TOPLAMKAR", operator="COLUMN"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, list(profiles) + [crm])   # candidate → certified
    return SemanticResolver(catalog, TENANT, DS, list(profiles) + [crm])


def test_a_lone_word_certified_on_the_other_database_is_left_to_the_model(catalog, profiles):
    """'kâr' → a CRM column, in a question that reads ERP sales by channel. Kept, it made the gate
    demand the period on the CRM table; the question was refused. Now the word goes to the model."""
    r = _with_crm_profit(catalog, profiles)
    sq = r.resolve("Kanal bazında net ciro ve kâr", today=TODAY)
    entities = {s.mapping.entity for s in sq.slots if s.mapping}
    assert "NEW_SATISSENARYOSUBASE" not in entities, entities
    assert "kar" in sq.unresolved, sq.unresolved
    assert any("model o kaynakta yorumlayacak" in e for e in sq.explanation), sq.explanation


def test_without_a_measure_nothing_decides_and_both_stay(catalog, profiles):
    r = _with_crm_profit(catalog, profiles)
    sq = r.resolve("Kanal ve kâr", today=TODAY)
    entities = {s.mapping.entity for s in sq.slots if s.mapping}
    assert "NEW_SATISSENARYOSUBASE" in entities and "CLCARD" in entities, entities
    assert "kar" not in sq.unresolved


def test_a_measure_on_the_other_side_keeps_the_word_because_the_measures_then_span_both(catalog, profiles):
    crm = scenario()
    catalog.upsert_profile(crm)
    _certify(catalog, "senaryo kari", SemanticType.METRIC, Mapping(concept_id="", entity="NEW_SATISSENARYOSUBASE",
             table_pattern="NEW_SATISSENARYOSUBASE", formula="SUM(NEW_SATISSENARYOSUBASE.NEW_TOPLAMKAR)"))
    _certify(catalog, "kar", SemanticType.COLUMN, Mapping(concept_id="", entity="NEW_SATISSENARYOSUBASE",
             table_pattern="NEW_SATISSENARYOSUBASE", column="NEW_TOPLAMKAR", operator="COLUMN"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, list(profiles) + [crm])
    sq = SemanticResolver(catalog, TENANT, DS, list(profiles) + [crm]).resolve("Net ciro ve senaryo karı, kâr bazında", today=TODAY)
    assert "kar" not in sq.unresolved, sq.explanation
