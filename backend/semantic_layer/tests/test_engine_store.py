from semantic_layer.candidates.doc_miner import mine_text
from semantic_layer.candidates.generator import CandidateGenerator
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import Annotation, ConceptStatus, CounterEvidence, Evidence, EvidenceType, Mapping, SemanticType
from semantic_layer.tests.conftest import DS, TENANT


def _dim(store, term, entity, pattern, column, values, *, pairs, doc=0, alias=0):
    m = Mapping(concept_id="", entity=entity, table_pattern=pattern, column=column, operator="IN", values=values)
    c, _ = store.upsert_concept(TENANT, DS, term, SemanticType.DIMENSION_VALUE, mapping=m, status=ConceptStatus.CANDIDATE)
    if pairs:
        store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "hm", support_count=len(pairs), payload={"pairs": pairs, "precision": 1.0}))
    if alias:
        store.add_evidence(Evidence(c.id, EvidenceType.ALIAS_BINDING, "hm", support_count=alias, payload={"pairs": pairs}))
    for i in range(doc):
        store.add_evidence(Evidence(c.id, EvidenceType.DOC, f"doc:{i}", payload={}))
    return c


def test_store_concepts_mappings_evidence_roundtrip(store):
    c = _dim(store, "toptan", "INVOICE", "LG_{firm}_{period}_INVOICE", "TRCODE", ["8"], pairs=["a"])
    again, created = store.upsert_concept(TENANT, DS, "Toptan", SemanticType.DIMENSION_VALUE, mapping=Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{firm}_{period}_INVOICE", column="TRCODE", operator="IN", values=["8"]))
    assert not created and again.id == c.id  # same physical sense
    other, created = store.upsert_concept(TENANT, DS, "toptan", SemanticType.DIMENSION_VALUE, mapping=Mapping(concept_id="", entity="STLINE", table_pattern="LG_{firm}_{period}_STLINE", column="TRCODE", operator="IN", values=["8"]))
    assert created and other.sense_id == 2
    ev = store.list_evidence(c.id)
    assert ev[0].support_count == 1
    store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "hm", support_count=3, payload={"pairs": ["a", "b", "c"]}))
    assert store.list_evidence(c.id)[0].support_count == 3  # idempotent per source


def test_hard_gate_and_certification(store, synthetic_profiles):
    eng = EvidenceEngine(store, min_support=3)
    weak = _dim(store, "toptan", "INVOICE", "LG_{firm}_{period}_INVOICE", "TRCODE", ["8"], pairs=["a"])
    strong = _dim(store, "perakende", "INVOICE", "LG_{firm}_{period}_INVOICE", "TRCODE", ["7"], pairs=["a", "b", "c"], alias=2)
    documented = _dim(store, "iade", "INVOICE", "LG_{firm}_{period}_INVOICE", "TRCODE", ["2", "3"], pairs=["a"], doc=2)
    ghost = _dim(store, "hayalet", "INVOICE", "LG_{firm}_{period}_INVOICE", "NOPE", ["1"], pairs=["a", "b", "c", "d"])
    rep = eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(weak.id).status == ConceptStatus.CANDIDATE          # 1 validated, undocumented → not enough
    assert store.get_concept(strong.id).status == ConceptStatus.CERTIFIED        # ≥ 3 validated
    assert store.get_concept(documented.id).status == ConceptStatus.CERTIFIED    # validated + documented + profile fit
    g = store.get_concept(ghost.id)
    assert g.status == ConceptStatus.CANDIDATE and "physical mapping invalid" in g.explain["gate"]["reasons"][0]
    assert rep["catalog_version"] == 1
    # LLM candidate alone can never pass
    llm = _dim(store, "bolgesel", "INVOICE", "LG_{firm}_{period}_INVOICE", "TRCODE", ["9"], pairs=[])
    store.add_evidence(Evidence(llm.id, EvidenceType.LLM_CANDIDATE, "llm:qwen", weight=0.1, payload={"confidence": 0.97}))
    eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(llm.id).status == ConceptStatus.CANDIDATE


def test_counter_evidence_damps_and_blocks(store, synthetic_profiles):
    eng = EvidenceEngine(store, min_support=3)
    c = _dim(store, "toptan", "INVOICE", "LG_{firm}_{period}_INVOICE", "TRCODE", ["7", "8"], pairs=list("abcdefghijklmnopq"))  # 17 pairs
    base = eng.evaluate(c, {p.entity: p for p in synthetic_profiles})
    store.add_counter_evidence(CounterEvidence(c.id, "pairs:xyz", "VALUE_MISMATCH", payload={"support": 4}))
    damped = eng.evaluate(c, {p.entity: p for p in synthetic_profiles})
    assert damped.score < base.score and abs(damped.score - base.raw_score * (1 - min(1, 2 * (4 / 21)))) < 1e-6
    store.add_counter_evidence(CounterEvidence(c.id, "human:x", "HUMAN_REJECT", payload={"support": 3}, severity="BLOCKING"))
    assert eng.evaluate(c, {p.entity: p for p in synthetic_profiles}).status == ConceptStatus.REJECTED


def test_sense_conflict_and_doc_dominance(store, synthetic_profiles):
    eng = EvidenceEngine(store, min_support=3)
    a = _dim(store, "iade", "INVOICE", "LG_{firm}_{period}_INVOICE", "TRCODE", ["2", "3"], pairs=["a", "b", "c", "d"])
    b = _dim(store, "iade", "INVOICE", "LG_{firm}_{period}_INVOICE", "TRCODE", ["7", "8", "9"], pairs=["e", "f", "g"])
    eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(a.id).status == ConceptStatus.SENSE_CONFLICT and store.get_concept(b.id).status == ConceptStatus.SENSE_CONFLICT
    # documentation breaks the tie: the documented sense wins, the other is rejected with counter-evidence
    store.add_evidence(Evidence(a.id, EvidenceType.DOC, "doc:rules", payload={}))
    store.clear_counter_evidence(a.id)
    store.clear_counter_evidence(b.id)
    store.update_concept(a.id, status=ConceptStatus.CANDIDATE)
    store.update_concept(b.id, status=ConceptStatus.CANDIDATE)
    eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(a.id).status == ConceptStatus.CERTIFIED
    assert store.get_concept(b.id).status == ConceptStatus.REJECTED


def test_drift_deprecates_certified_mapping(store, synthetic_profiles):
    eng = EvidenceEngine(store, min_support=3)
    c = _dim(store, "toptan", "INVOICE", "LG_{firm}_{period}_INVOICE", "TRCODE", ["8"], pairs=["a", "b", "c"])
    eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(c.id).status == ConceptStatus.CERTIFIED
    inv = next(p for p in synthetic_profiles if p.entity == "INVOICE")
    inv.column("TRCODE").top_values = [("7", 100), ("9", 50)]  # 8 disappeared after a Logo customisation
    inv.column("TRCODE").distinct_count = 2
    rep = eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(c.id).status == ConceptStatus.DEPRECATED and rep["drift"][0]["drift"] == "values_gone"


def test_doc_miner_extracts_enum_glosses_and_column_aliases():
    facts = mine_text("Fatura türleri (dbo_LG_411_01_INVOICE.TRCODE): 7 perakende satış, 8 toptan satış, 9 verilen hizmet = SATIŞ; 2 perakende satış iadesi, 3 toptan satış iadesi = SATIŞ İADESİ; 1 mal alım, 4 alınan hizmet = SATINALMA; 6 alım iadesi.", "doc:test")
    got = {(f.term, f.column, f.values) for f in facts if f.kind == "value"}
    assert ("toptan", "TRCODE", ("8",)) in got and ("perakende", "TRCODE", ("7",)) in got
    assert ("satis", "TRCODE", ("7", "8", "9")) in got and ("satis iade", "TRCODE", ("2", "3")) in got
    assert not any(t == "iade" and v == ("6",) for t, _, v in got)  # 'alım iadesi' never becomes bare 'iade'
    col = {(f.term, f.entity, f.column) for f in mine_text('- "kanal / satış kanalı" = faturanın carisindeki `CLCARD.SPECODE2`; boş = (boş).', "doc:c") if f.kind == "column"}
    assert ("kanal", "CLCARD", "SPECODE2") in col and ("satis kanal", "CLCARD", "SPECODE2") in col


def test_human_annotation_becomes_candidate_with_human_evidence(store, synthetic_profiles):
    gen = CandidateGenerator(store, TENANT, DS, synthetic_profiles)
    store.add_annotation(Annotation(datasource_id=DS, table_pattern="LG_{firm}_{period}_INVOICE", column="TRCODE", text="8 = toptan satış, 7 = perakende satış", author="ayse"))
    rep = gen.ingest_annotation("LG_{firm}_{period}_INVOICE", "TRCODE", "8 = toptan satış, 7 = perakende satış", "annotation:1")
    assert rep["evidence"] >= 2
    c = store.find_concepts(TENANT, DS, normalized_term="toptan", semantic_type=SemanticType.DIMENSION_VALUE)[0]
    assert c.status == ConceptStatus.CANDIDATE
    assert any(e.evidence_type == EvidenceType.HUMAN_ANNOTATION for e in store.list_evidence(c.id))
    # a human annotation alone does not certify — it needs at least one validated query too
    EvidenceEngine(store, min_support=3).run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(c.id).status == ConceptStatus.CANDIDATE
