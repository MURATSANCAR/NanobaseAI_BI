"""2026-09-17, soru 15: "Son üç ayda satılan adet, aynı dönemde üretilen adedin ne kadarı?" — two measures
and a word asking for one over the other. Answered as two totals, "how much of" became "how much"."""
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
    _certify(catalog, "satılan adet", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
             formula="SUM(STLINE.AMOUNT)", extra={"func": "SUM", "conditions": ["STLINE.LINETYPE = (0)", "STLINE.TRCODE IN (7,8)"]}))
    _certify(catalog, "üretilen adet", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
             formula="SUM(STLINE.AMOUNT)", extra={"func": "SUM", "conditions": ["STLINE.LINETYPE = (0)", "STLINE.TRCODE = (13)"]}))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    return SemanticResolver(catalog, TENANT, DS, profiles)


def test_two_measures_and_a_ratio_word_become_numerator_over_denominator(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("Son üç ayda satılan adet, aynı dönemde üretilen adedin ne kadarı?", today=TODAY)
    assert sq.shape == "RATIO" and sq.ratio and sq.ratio["numerator"].startswith("satilan") and sq.ratio["denominator"].startswith("uretilen"), (sq.shape, sq.ratio, sq.explanation)
    assert sq.temporal and (sq.temporal[0].start, sq.temporal[0].end) == (date(2026, 7, 1), date(2026, 10, 1)), sq.temporal


def test_the_deterministic_compiler_writes_the_ratio_beside_both_totals(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("Son üç ayda satılan adet, aynı dönemde üretilen adedin ne kadarı?", today=TODAY)
    out = DeterministicCompiler(profiles, {}, "tsql").compile(sq, catalog)
    assert out is not None, sq.to_dict()
    up = out.sql.upper()
    assert "AS SATILAN_ADET" in up and "AS URETILEN_ADET" in up and "AS ORAN" in up, out.sql
    assert "NULLIF(" in up and "CAST(" in up, out.sql


def test_two_measures_without_a_ratio_word_stay_two_totals(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("Son üç ayda satılan adet ve üretilen adet", today=TODAY)
    assert sq.shape is None and sq.ratio is None, (sq.shape, sq.ratio)


def test_a_label_and_a_ratio_word_reach_the_certified_ratio_named_after_the_label(catalog, profiles):
    """2026-09-17, soru 20: "iade faturalarının satış cirosuna oranı" — 'iade' became a filter on every row and the
    two 'satış/ciro' words one measure divided by itself: a ratio of 1 over the returns alone."""
    _certify(catalog, "iade", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
             column="TRCODE", operator="IN", values=["2", "3"]))
    _certify(catalog, "iade oranı", SemanticType.METRIC, Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
             formula="SUM(CASE WHEN INVOICE.TRCODE IN (2, 3) THEN INVOICE.NETTOTAL ELSE 0 END) / NULLIF(SUM(CASE WHEN INVOICE.TRCODE IN (7, 8, 9) THEN INVOICE.NETTOTAL ELSE 0 END), 0)",
             extra={"conditions": ["INVOICE.TRCODE IN (2,3,7,8,9)"]}))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("Son çeyrekte iade faturalarının satış cirosuna oranı yüzde kaç?", today=TODAY)
    metrics = [s for s in sq.slots if s.semantic_type == SemanticType.METRIC]
    assert len(metrics) == 1 and "/" in metrics[0].mapping.formula, [(s.term, s.mapping.formula) for s in metrics]
    assert not any(s.semantic_type == SemanticType.DIMENSION_VALUE and s.mapping and set(s.mapping.values) == {"2", "3"} for s in sq.slots)
    det = DeterministicCompiler(profiles, {}, "tsql")
    assert det.compile(sq, catalog) is not None, (det.plan(sq)[1], sq.explanation)
