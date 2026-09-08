"""A person's decision on a proposed term has to outlast the engine that proposed it.

The evidence engine reruns every night. If a portal approval were only a status flag, the next run
would weigh the same evidence, reach the same score, and put the term back in the queue — the
reviewer's minute spent for nothing. So an approval is written as evidence with its own weight, and
these tests hold that: the decision survives, the runtime notices, and a rejection is as durable as
a yes.
"""

from __future__ import annotations

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import (ColumnProfile, Concept, ConceptStatus, Evidence, EvidenceType,
                                   Mapping, SchemaProfile)

TENANT, DS = "t1", "logo"


def _candidate(store, term: str = "toptan") -> Concept:
    mapping = Mapping("", "INVOICE", "LG_{n0}_{n1}_INVOICE", column="TRCODE", operator="IN", values=["8"])
    c, _ = store.upsert_concept(TENANT, DS, term, "DIMENSION_VALUE", mapping=mapping, status=ConceptStatus.CANDIDATE)
    store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "q1", support_count=2, weight=0.5))
    return c


def test_approval_is_recorded_as_evidence_not_just_a_flag(store):
    c = _candidate(store)
    store.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, "portal:ayse", support_count=1, weight=1.0,
                                payload={"snippet": "Logo sözlüğü: 8 = toptan satış faturası", "by": "ayse"}))
    store.update_concept(c.id, status=ConceptStatus.CERTIFIED, explain={"approved_by": "ayse"})

    bundle = store.concept_bundle(c.id)
    assert bundle["concept"]["status"] == ConceptStatus.CERTIFIED
    kinds = {e["evidence_type"] for e in bundle["evidence"]}
    assert EvidenceType.HUMAN_ANNOTATION in kinds, "onay kanıt olarak yazılmalı, yoksa gece koşusu geri alır"
    human = [e for e in bundle["evidence"] if e["evidence_type"] == EvidenceType.HUMAN_ANNOTATION][0]
    assert human["weight"] >= 1.0 and human["payload"]["by"] == "ayse"


def test_approved_term_reaches_the_certified_vocabulary(store):
    c = _candidate(store, "toptan")
    assert not any(x.id == c.id for x in store.find_concepts(TENANT, DS, status=ConceptStatus.CERTIFIED))
    store.update_concept(c.id, status=ConceptStatus.CERTIFIED)
    certified = store.find_concepts(TENANT, DS, status=ConceptStatus.CERTIFIED)
    assert [x.term for x in certified] == ["toptan"]
    # and the entity it names is what the runtime rebuilds its labels from
    assert store.concept_entities(TENANT, DS).get("LG_{n0}_{n1}_INVOICE") == "INVOICE"


def test_certifying_moves_the_fingerprint_so_the_runtime_reloads(store):
    """The bridge only rebuilds when this tuple changes. If it did not move, an approval would sit
    in the database while the running process kept answering without the word."""
    c = _candidate(store)
    before = store.catalog_fingerprint(TENANT, DS)
    store.update_concept(c.id, status=ConceptStatus.CERTIFIED)
    assert store.catalog_fingerprint(TENANT, DS) != before


def test_rejection_takes_the_term_out_of_the_queue(store):
    c = _candidate(store, "eksi")
    store.update_concept(c.id, status=ConceptStatus.REJECTED, explain={"rejected_by": "ayse"})
    waiting = [x.term for x in store.find_concepts(TENANT, DS, status=ConceptStatus.CANDIDATE)]
    assert "eksi" not in waiting
    assert store.get_concept(c.id).status == ConceptStatus.REJECTED


def _profile() -> SchemaProfile:
    return SchemaProfile(datasource_id=DS, table_name="LG_411_01_INVOICE",
                         table_pattern="LG_{n0}_{n1}_INVOICE", entity="INVOICE", schema_name="dbo",
                         row_count=1000,
                         columns=[ColumnProfile(name="TRCODE", data_type="int", distinct_count=8,
                                                top_values=[("7", 500), ("8", 300)])])


def test_an_approval_survives_the_nightly_re_scoring(store):
    """The one that matters, and the one a status flag alone does not give you.

    The engine re-scores every concept each night. A term approved in the portal has, by definition,
    too little query history to clear the evidence bar on its own — that is why a person had to
    decide. If the approval is only a status, the next run reads the same thin evidence and demotes
    it, and the reviewer's work is undone before morning.
    """
    c = _candidate(store)
    eng = EvidenceEngine(store, min_support=3, threshold=0.6)
    eng.human_certify(c.id, "ayse", reason="Logo sözlüğü: 8 = toptan satış faturası")
    eng.run(TENANT, DS, [_profile()], scoped=False)
    assert store.get_concept(c.id).status == ConceptStatus.CERTIFIED


def test_a_rejection_survives_it_too(store):
    c = _candidate(store, "eksi")
    eng = EvidenceEngine(store, min_support=3, threshold=0.6)
    eng.human_reject(c.id, "ayse", reason="bu terim satış demek değil")
    eng.run(TENANT, DS, [_profile()], scoped=False)
    assert store.get_concept(c.id).status == ConceptStatus.REJECTED
