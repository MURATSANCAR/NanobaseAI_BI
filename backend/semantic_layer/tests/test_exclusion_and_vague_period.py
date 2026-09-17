"""2026-09-17, soru 19: "İptal edilmemiş satış faturalarında iade hariç toplam ciro ne kadar oldu bu ara?" """
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import Mapping, SemanticType
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.temporal import parse_temporal
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 17)


def test_a_label_followed_by_haric_is_left_out_not_selected(catalog, profiles):
    _certify(catalog, "iade", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
             column="TRCODE", operator="IN", values=["2", "3"]))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("İade hariç toplam net ciro ne kadar?", today=TODAY)
    ret = [s for s in sq.slots if s.mapping and s.mapping.column == "TRCODE" and set(s.mapping.values) == {"2", "3"}]
    assert ret and ret[0].mapping.operator == "NOT IN", [(s.term, s.mapping.operator) for s in sq.slots if s.mapping]
    assert "haric" not in sq.unresolved, sq.unresolved


def test_bu_ara_is_a_period_nobody_bounded():
    slots, _ = parse_temporal("toplam ciro ne kadar oldu bu ara?", TODAY)
    assert [(t.primitive, t.ambiguous) for t in slots] == [("AMBIGUOUS_RECENT", True)]


def test_a_vague_period_is_asked_back_not_guessed(catalog, profiles):
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("Net ciro ne kadar oldu bu ara?", today=TODAY)
    assert any("bu ara" in c and "hangi dönemi" in c for c in sq.clarification), sq.clarification
    assert "bu ara" not in sq.unresolved
