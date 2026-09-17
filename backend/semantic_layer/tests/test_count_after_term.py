"""2026-09-17, soru 14: "Geçen çeyrekte bekleyen sipariş adedi ay ay nasıl değişti?"

'adedi' matched the certified sold-quantity measure on the sales lines and moved the question to
another table; 'ay' and 'çeyrekte' — words the temporal parser had already read — were looked up again
and found CRM columns, then reported as words the catalog could not place."""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, Mapping, SchemaProfile, SemanticType
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 17)


def _resolver(catalog, profiles):
    crm = SchemaProfile(datasource_id=DS, table_name="new_projeBase", table_pattern="NEW_PROJEBASE", entity="NEW_PROJEBASE",
                        schema_name="Timas_MSCRM.dbo", description="Proje",
                        columns=[ColumnProfile(name="new_projeninayi", data_type="int"), ColumnProfile(name="createdon", data_type="datetime")], row_count=100)
    catalog.upsert_profile(crm)
    _certify(catalog, "adet", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
             formula="SUM(STLINE.AMOUNT)", extra={"func": "SUM", "aliases": ["adet"], "conditions": ["STLINE.TRCODE IN (7,8)"]}), synonyms=["satilan adet"])
    _certify(catalog, "bekleyen sipariş", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
             column="TRCODE", operator="IN", values=["1"]))
    _certify(catalog, "ay", SemanticType.COLUMN, Mapping(concept_id="", entity="NEW_PROJEBASE", table_pattern="NEW_PROJEBASE",
             column="new_projeninayi", operator="COLUMN"), synonyms=["planlanan ay"])
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, list(profiles) + [crm])
    return SemanticResolver(catalog, TENANT, DS, list(profiles) + [crm])


def test_a_count_word_after_a_term_counts_that_term_not_a_generic_quantity_measure(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("Geçen çeyrekte bekleyen sipariş adedi ay ay nasıl değişti?", today=TODAY)
    metrics = [(s.term, s.mapping.entity, (s.explain or {}).get("source")) for s in sq.metrics if s.mapping]
    assert metrics and all(e == "INVOICE" for _, e, _ in metrics), (metrics, sq.explanation)
    assert any(src == "count_cue" for _, _, src in metrics), metrics
    assert sq.temporal_binding and sq.temporal_binding["entity"] == "INVOICE", sq.temporal_binding


def test_words_the_temporal_parser_read_are_not_looked_up_again(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("Geçen çeyrekte bekleyen sipariş adedi ay ay nasıl değişti?", today=TODAY)
    assert sq.grain == "MONTH" and sq.temporal and sq.temporal[0].primitive == "LAST_QUARTER", (sq.grain, sq.temporal)
    assert not any(s.mapping and s.mapping.entity == "NEW_PROJEBASE" for s in sq.slots), [(s.term, s.mapping.entity) for s in sq.slots if s.mapping]
    assert not {"ay", "ceyrekte", "çeyrekte"} & set(sq.unresolved), sq.unresolved


def test_the_measures_own_name_still_reaches_the_certified_measure(catalog, profiles):
    """A bare "adet" is a count word by design; the measure is reached by its certified name."""
    sq = _resolver(catalog, profiles).resolve("Toptan satılan adet ne kadar?", today=TODAY)
    assert any(s.mapping and s.mapping.entity == "STLINE" and s.semantic_type == SemanticType.METRIC for s in sq.slots), \
        [(s.term, s.semantic_type, s.mapping.entity if s.mapping else None) for s in sq.slots]
