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
