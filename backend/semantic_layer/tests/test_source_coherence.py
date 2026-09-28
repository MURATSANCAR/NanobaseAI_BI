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


def test_a_top_n_grouping_the_resolver_added_itself_does_not_protect_the_foreign_word(catalog, profiles):
    """The rank rule turns every COLUMN slot into a grouping; that is bookkeeping, not the person's
    "X bazında". 'kâr' grouped that way still leaves for the model when the measure is elsewhere."""
    r = _with_crm_profit(catalog, profiles)
    sq = r.resolve("En çok net ciro yaptığımız on kanal, kâr ile", today=TODAY)
    assert "NEW_SATISSENARYOSUBASE" not in {s.mapping.entity for s in list(sq.slots) + list(sq.group_by) if s.mapping}
    assert "kar" in sq.unresolved, sq.unresolved


def test_without_a_measure_the_named_things_decide_the_database(catalog, profiles):
    """'… faturalar' names invoices; a two-word CRM state ("fiyat listesi") in the same question is
    left to the model, to be read in the ERP.

    Both databases keep a price list (the premise of `_source_votes`: "fiyat" is no vote), so the
    ERP's own price-list table is part of the world here; without it "fiyatın" voted for the CRM
    alone. Since 2026-09-18 (cf11f1be) a phrase placed on one side with nothing placed on the other
    decided the database before the plain words were read — this question went to the CRM, which
    has no invoices. The plain words are now read first: a table the question names in its own word
    on the other side sends it to the vote, where the phrase and the table weigh the same."""
    crm = SchemaProfile(datasource_id=DS, table_name="new_fiyatlistesiBase", table_pattern="new_fiyatlistesiBase", entity="NEW_FIYATLISTESIBASE",
                        schema_name="Timas_MSCRM.dbo", description="Fiyat listesi", columns=[ColumnProfile(name="statecode", data_type="int")], row_count=40)
    erp_prices = SchemaProfile(datasource_id=DS, table_name="LG_411_PRCLIST", table_pattern="LG_{n0}_PRCLIST", entity="PRCLIST",
                               schema_name="main", description="Fiyat listesi", context={"n0": "411"},
                               columns=[ColumnProfile(name="LOGICALREF", data_type="int", is_primary_key=True),
                                        ColumnProfile(name="CARDREF", data_type="int")],
                               primary_key=["LOGICALREF"], row_count=300)
    catalog.upsert_profile(crm)
    catalog.upsert_profile(erp_prices)
    _certify(catalog, "fiyat listesi", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="NEW_FIYATLISTESIBASE",
             table_pattern="new_fiyatlistesiBase", column="statecode", operator="IN", values=["0"]))
    inv = next(p for p in profiles if p.entity == "INVOICE")
    inv.description = "Fatura"                                   # the table's own name, as the live scan carries it
    world = list(profiles) + [crm, erp_prices]
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, world)
    sq = SemanticResolver(catalog, TENANT, DS, world).resolve("Fiyat listesinde tanımlı fiyatın altında kesilen faturalar hangileri?", today=TODAY)
    assert "NEW_FIYATLISTESIBASE" not in {s.mapping.entity for s in sq.slots if s.mapping}, [(s.term, s.mapping.entity) for s in sq.slots if s.mapping]
    assert sq.source_hint == "", "the ERP is the connection's own database: its source name is empty"
    assert any("faturalar" in e or "yorumlayacak" in e for e in sq.explanation)


def test_a_phrase_placed_on_one_side_still_decides_when_no_plain_word_names_the_other(catalog, profiles):
    """The shortcut stays for what it was written for: a certified phrase on one side and nothing —
    placed, or named in plain words — on the other."""
    crm = SchemaProfile(datasource_id=DS, table_name="new_fiyatlistesiBase", table_pattern="new_fiyatlistesiBase", entity="NEW_FIYATLISTESIBASE",
                        schema_name="Timas_MSCRM.dbo", description="Fiyat listesi", columns=[ColumnProfile(name="statecode", data_type="int")], row_count=40)
    catalog.upsert_profile(crm)
    _certify(catalog, "fiyat listesi", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="NEW_FIYATLISTESIBASE",
             table_pattern="new_fiyatlistesiBase", column="statecode", operator="IN", values=["0"]))
    world = list(profiles) + [crm]
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, world)
    sq = SemanticResolver(catalog, TENANT, DS, world).resolve("Fiyat listesinde tanımlı olanlar hangileri?", today=TODAY)
    assert "NEW_FIYATLISTESIBASE" in {s.mapping.entity for s in sq.slots if s.mapping}, sq.explanation
    assert sq.source_hint == "TIMAS_MSCRM", sq.source_hint
