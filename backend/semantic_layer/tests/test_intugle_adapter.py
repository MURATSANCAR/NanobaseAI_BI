"""Intugle plug-in: consumed when installed, a no-op when not, and never able to certify anything."""

from __future__ import annotations

import sys
import types

import pytest

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ConceptStatus, Mapping, SemanticType
from semantic_layer.profiler import intugle_adapter
from semantic_layer.tests.conftest import DS, TENANT


class _FakeLink:
    def __init__(self, s, t, confidence):
        self.source, self.target, self.confidence = s, t, confidence


def _install_fake_intugle(monkeypatch, links, glossary):
    module = types.ModuleType("intugle")

    class SemanticModel:
        def __init__(self, spec):
            self.spec = spec
            self.links = []
            self.glossary = {}

        def build(self):
            self.links = links
            self.glossary = glossary

    module.SemanticModel = SemanticModel
    monkeypatch.setitem(sys.modules, "intugle", module)
    return module


def test_absent_package_is_a_no_op(monkeypatch, profiles):
    monkeypatch.setitem(sys.modules, "intugle", None)
    report = intugle_adapter.run(profiles)
    assert report.available is False and report.ran is False and report.links_added == 0


def test_links_and_glossary_are_merged_into_the_profile(monkeypatch, retail_profiles):
    orders = next(p for p in retail_profiles if p.entity == "ORDERS")
    assert not orders.relationships                      # no FK, no naming convention
    _install_fake_intugle(
        monkeypatch,
        links=[
            _FakeLink("sales_2024_orders.customer", "customers.id", 0.97),
            _FakeLink("sales_2024_orders.kind", "customers.id", 0.42),   # low confidence → ignored
        ],
        glossary={"NET_AMOUNT": "Sipariş net tutarı (KDV dahil)", "SEGMENT": "Müşteri segmenti"},
    )
    report = intugle_adapter.run(retail_profiles, min_confidence=0.8)
    assert report.ran and report.links_seen == 2 and report.links_added == 1
    link = next(r for r in orders.relationships if r["column"] == "customer")
    assert (link["ref_entity"], link["ref_column"], link["source"], link["confidence"]) == ("CUSTOMERS", "id", "intugle", 0.97)
    # a third party's glossary is a reading, not the source's own words: it sits beside the column's
    # description rather than replacing whatever the database itself says
    col = orders.column("net_amount")
    assert col.description is None
    assert col.meaning().startswith("Sipariş net tutarı"), col.derived
    # and a person's own words take it back: what the portal says is the last word
    assert col.meaning("Ciro, iade düşülmemiş hâli") == "Ciro, iade düşülmemiş hâli"
    assert report.glossary_added == 2


def test_intugle_evidence_never_certifies(monkeypatch, store, synthetic_profiles):
    """A link Intugle predicted is PROFILE evidence; the hard gate still needs validated queries."""
    inv = next(p for p in synthetic_profiles if p.entity == "INVOICE")
    inv.relationships.append({"column": "CLIENTREF", "ref_entity": "CLCARD", "ref_column": "LOGICALREF", "source": "intugle", "confidence": 0.95})
    concept, _ = store.upsert_concept(
        TENANT, DS, "INVOICE.CLIENTREF -> CLCARD.LOGICALREF", SemanticType.RELATIONSHIP,
        mapping=Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="CLIENTREF", operator="JOIN", values=["CLCARD.LOGICALREF"], extra={"ref_entity": "CLCARD", "ref_column": "LOGICALREF"}),
        status=ConceptStatus.CANDIDATE,
    )
    report = intugle_adapter.IntugleReport(available=True, ran=True)
    intugle_adapter.attach_evidence(store, TENANT, DS, synthetic_profiles, report)
    assert report.evidence == 1
    types_ = {e.evidence_type for e in store.list_evidence(concept.id)}
    assert types_ == {"PROFILE"}
    EvidenceEngine(store, min_support=3).run(TENANT, DS, synthetic_profiles)
    # the relationship is real in the profile, so it may be certified on profile grounds — but a
    # *business* concept with only Intugle evidence must not be:
    value, _ = store.upsert_concept(TENANT, DS, "bolgesel", SemanticType.DIMENSION_VALUE, mapping=Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="TRCODE", operator="IN", values=["9"]), status=ConceptStatus.CANDIDATE)
    from semantic_layer.models import Evidence, EvidenceType

    store.add_evidence(Evidence(value.id, EvidenceType.PROFILE, "intugle:link", weight=0.99, payload={}))
    EvidenceEngine(store, min_support=3).run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(value.id).status != ConceptStatus.CERTIFIED
