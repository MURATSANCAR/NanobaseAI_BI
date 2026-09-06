"""A narrower profiling scope must never silently decertify what it did not look at."""

from __future__ import annotations

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ConceptStatus, Evidence, EvidenceType, Mapping, SemanticType
from semantic_layer.tests.conftest import DS, TENANT


def _certified(store, profiles, term, entity, column, values):
    prof = next(p for p in profiles if p.entity == entity)
    c, _ = store.upsert_concept(TENANT, DS, term, SemanticType.DIMENSION_VALUE,
                                mapping=Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, column=column, operator="IN", values=values),
                                status=ConceptStatus.CANDIDATE)
    store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "hm", support_count=3, payload={"pairs": ["a", "b", "c"], "precision": 1.0}))
    return c


def test_out_of_scope_tables_keep_their_status(store, synthetic_profiles):
    engine = EvidenceEngine(store, min_support=3)
    invoice = _certified(store, synthetic_profiles, "toptan", "INVOICE", "TRCODE", ["8"])
    line = _certified(store, synthetic_profiles, "iade", "STLINE", "TRCODE", ["2", "3"])
    engine.run(TENANT, DS, synthetic_profiles, scoped=False)
    assert store.get_concept(invoice.id).status == ConceptStatus.CERTIFIED
    assert store.get_concept(line.id).status == ConceptStatus.CERTIFIED

    narrow = [p for p in synthetic_profiles if p.entity != "STLINE"]      # a run that only covered part
    engine.run(TENANT, DS, narrow, scoped=True)
    assert store.get_concept(invoice.id).status == ConceptStatus.CERTIFIED
    assert store.get_concept(line.id).status == ConceptStatus.CERTIFIED, "a narrower scan decertified a table it never looked at"


def test_a_full_scan_still_reports_a_vanished_table(store, synthetic_profiles):
    engine = EvidenceEngine(store, min_support=3)
    line = _certified(store, synthetic_profiles, "iade", "STLINE", "TRCODE", ["2", "3"])
    engine.run(TENANT, DS, synthetic_profiles, scoped=False)
    assert store.get_concept(line.id).status == ConceptStatus.CERTIFIED
    narrow = [p for p in synthetic_profiles if p.entity != "STLINE"]
    report = engine.run(TENANT, DS, narrow, scoped=False)               # full scan: the table is really gone
    assert store.get_concept(line.id).status == ConceptStatus.DEPRECATED
    assert any(d["drift"] == "table_missing" for d in report["drift"])
