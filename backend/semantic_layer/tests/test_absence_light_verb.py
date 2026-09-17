"""2026-09-17, soru 17: "Sipariş verip de hiç sevkiyat almamış müşterilerimiz var mı?" — read as order lines with
nothing shipped yet (31 customers); asked were the customers with no shipment record at all (4)."""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import Mapping, ResolvedSlot, SemanticQuery, SemanticType
from semantic_layer.runtime.audit import unmet_obligations
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 17)


def test_a_negated_light_verb_after_a_measure_asks_for_its_absence(catalog, profiles):
    _certify(catalog, "sevkiyat", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
             formula="SUM(STLINE.AMOUNT)", extra={"conditions": ["STLINE.TRCODE IN (7,8)"]}), synonyms=["sevk"])
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("Sipariş verip de hiç sevkiyat almamış müşterilerimiz var mı?", today=TODAY)
    assert sq.shape == "ABSENCE", (sq.shape, sq.explanation)
    assert any(m.get("decision") == "ABSENCE" and m.get("absent_entity") == "STLINE" for m in sq.modifiers), sq.modifiers
    assert not sq.temporal, sq.temporal          # "never" is not "not this year"


def _absence_query():
    ship = ResolvedSlot("sevkiyat", "METRIC", "CERTIFIED", mapping=Mapping("", "STLINE", "LG_{n0}_{n1}_STLINE", formula="SUM(STLINE.AMOUNT)"))
    sq = SemanticQuery(question="x", tenant_id="t", datasource_id="d", slots=[ship], shape="ABSENCE")
    sq.modifiers = [{"token": "almamis", "decision": "ABSENCE", "absent_entity": "STLINE"}]
    return sq


def test_an_absence_without_a_contract_needs_an_anti_join_over_the_absent_entity():
    sq = _absence_query()
    filtered = ("SELECT c.CODE FROM ORFICHE o JOIN CLCARD c ON c.LOGICALREF = o.CLIENTREF JOIN LG_ORFLINE ol ON ol.ORDFICHEREF = o.LOGICALREF "
                "WHERE ol.SHIPPEDAMOUNT = 0 GROUP BY c.CODE")
    assert any("yokluk" in u for u in unmet_obligations(sq, filtered))
    excluded = ("SELECT c.CODE FROM ORFICHE o JOIN CLCARD c ON c.LOGICALREF = o.CLIENTREF WHERE o.TRCODE = 1 "
                "AND NOT EXISTS (SELECT 1 FROM STLINE s WHERE s.CLIENTREF = c.LOGICALREF AND s.TRCODE IN (7,8)) GROUP BY c.CODE")
    assert not any("yokluk" in u for u in unmet_obligations(sq, excluded)), unmet_obligations(sq, excluded)
    left_null = ("SELECT c.CODE FROM CLCARD c LEFT JOIN STLINE s ON s.CLIENTREF = c.LOGICALREF AND s.TRCODE IN (7,8) "
                 "WHERE s.LOGICALREF IS NULL GROUP BY c.CODE")
    assert not any("yokluk" in u for u in unmet_obligations(sq, left_null)), unmet_obligations(sq, left_null)


def test_a_filter_inside_a_correlated_subquery_is_a_reading_of_its_table():
    """The order filter written inside EXISTS was 'not in the result's scope': the gate never walked
    correlated subqueries, and the correct statement for question 17 was refused for it."""
    order = ResolvedSlot("siparis", "DIMENSION_VALUE", "CERTIFIED",
                         mapping=Mapping("", "LG_ORFICHE", "LG_{n0}_{n1}_ORFICHE", column="TRCODE", operator="IN", values=["1"]))
    sq = SemanticQuery(question="x", tenant_id="t", datasource_id="d", slots=[order])
    sql = ("SELECT c.CODE FROM CLCARD c WHERE EXISTS (SELECT 1 FROM LG_ORFICHE o WHERE o.CLIENTREF = c.LOGICALREF AND o.TRCODE IN (1) AND o.CANCELLED = 0)")
    assert not any("koşulu sonuç kapsamında" in u for u in unmet_obligations(sq, sql)), unmet_obligations(sq, sql)
    unfiltered = "SELECT c.CODE FROM CLCARD c WHERE EXISTS (SELECT 1 FROM LG_ORFICHE o WHERE o.CLIENTREF = c.LOGICALREF)"
    assert any("koşulu sonuç kapsamında" in u for u in unmet_obligations(sq, unfiltered))


def test_an_absent_measure_has_no_reference_priority_to_prove():
    """'musterilerimiz' carries the invoice-customer rule for STLINE; with the shipment measure excluded by
    NOT EXISTS there is nothing attributed per customer, and the rule honoured inside the subquery counts."""
    ship = ResolvedSlot("sevkiyat", "METRIC", "CERTIFIED", mapping=Mapping("", "STLINE", "LG_{n0}_{n1}_STLINE", formula="SUM(STLINE.AMOUNT)"),
                        explain={"absent": True})
    rule = {"reference_resolution": {"STLINE": {"via": "INVOICE", "via_column": "INVOICEREF", "via_key": "LOGICALREF",
                                                "fallback_column": "CLIENTREF", "target_column": "LOGICALREF"}}}
    cust = ResolvedSlot("musterilerimiz", "COLUMN", "CERTIFIED", mapping=Mapping("", "CLCARD", "LG_{n0}_CLCARD", column="DEFINITION_", operator="COLUMN", extra=rule))
    sq = SemanticQuery(question="x", tenant_id="t", datasource_id="d", slots=[ship, cust], shape="ABSENCE", group_by=[cust])
    sq.modifiers = [{"token": "almamis", "decision": "ABSENCE", "absent_entity": "STLINE"}]
    sql = ("SELECT c.CODE, c.DEFINITION_ FROM CLCARD c WHERE NOT EXISTS (SELECT 1 FROM STLINE s INNER JOIN INVOICE i ON s.INVOICEREF = i.LOGICALREF "
           "WHERE i.CLIENTREF = c.LOGICALREF AND s.TRCODE IN (7, 8)) ORDER BY c.DEFINITION_")
    out = unmet_obligations(sq, sql)
    assert not any("ilişki önceliği" in u for u in out), out
    assert not any("yokluk" in u for u in out), out


def test_a_header_filter_is_proven_on_its_line_table_by_the_same_column():
    """The model checked the order type on LG_ORFLINE; the certified filter names LG_ORFICHE. The line
    points at exactly one header and carries TRCODE as the header does."""
    order = ResolvedSlot("siparis", "DIMENSION_VALUE", "CERTIFIED",
                         mapping=Mapping("", "LG_ORFICHE", "LG_{n0}_{n1}_ORFICHE", column="TRCODE", operator="IN", values=["1"]))
    sq = SemanticQuery(question="x", tenant_id="t", datasource_id="d", slots=[order])
    sources = {"LG_ORFLINE": {"types": {}, "window": None, "declared": False, "refs": {"ORDFICHEREF": "LG_ORFICHE"}}}
    sql = "SELECT c.CODE FROM CLCARD c WHERE EXISTS (SELECT 1 FROM LG_ORFLINE o WHERE o.CLIENTREF = c.LOGICALREF AND o.TRCODE IN (1) AND o.CANCELLED = 0)"
    assert not any("koşulu sonuç kapsamında" in u for u in unmet_obligations(sq, sql, sources=sources)), unmet_obligations(sq, sql, sources=sources)
    other = sql.replace("o.TRCODE IN (1)", "o.TRCODE IN (2)")
    assert any("koşulu sonuç kapsamında" in u for u in unmet_obligations(sq, other, sources=sources))


def test_negating_a_record_kind_is_absence_not_the_other_kinds(catalog, profiles):
    """"bu yıl hiç sipariş vermemiş müşteriler": 'sipariş' names the order document (TRCODE 1). Flipped to
    TRCODE NOT IN (1) it asked for customers with orders of another type; asked was no order at all."""
    _certify(catalog, "sipariş", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
             column="TRCODE", operator="IN", values=["1"], extra={"count_key": "LOGICALREF"}))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("Bu yıl hiç sipariş vermemiş müşteriler kimler?", today=TODAY)
    assert sq.shape == "ABSENCE", (sq.shape, sq.explanation)
    assert not any(s.mapping and (s.mapping.operator or "").upper() == "NOT IN" for s in sq.slots), [(s.term, s.mapping.operator) for s in sq.slots if s.mapping]
    assert any(m.get("decision") == "ABSENCE" and m.get("absent_entity") == "INVOICE" for m in sq.modifiers), sq.modifiers


def test_a_negated_record_verb_after_a_document_label_is_absence(catalog, profiles):
    """2026-09-17, soru 21: "bu yıl hiç fatura kesilmemiş ama kartı aktif duran müşteriler" — 'kesilmemiş' is the
    negation of a record verb; 'kartı' is the customer's card, not the measure "kâr"; 'duran' is grammar."""
    _certify(catalog, "fatura", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
             column="TRCODE", operator="IN", values=["7", "8", "9"], extra={"count_key": "LOGICALREF"}))
    _certify(catalog, "kâr", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
             formula="SUM(STLINE.TOTAL)"), synonyms=["kar"])
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("Bu yıl hiç fatura kesilmemiş ama kartı aktif duran müşteriler kimler?", today=TODAY)
    assert sq.shape == "ABSENCE", (sq.shape, sq.explanation)
    assert not any(s.semantic_type == SemanticType.METRIC and s.mapping and s.mapping.entity == "STLINE" for s in sq.slots), [(s.term, s.semantic_type) for s in sq.slots]
    assert not any(m.get("token") == "duran" for m in (sq.model_qualifiers or [])), sq.model_qualifiers
    assert sq.temporal and sq.temporal[0].text == "bu yil"        # a stated period stays: "this year" is part of the absence
