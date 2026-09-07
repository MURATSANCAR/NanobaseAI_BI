from semantic_layer.candidates.doc_miner import mine_text
from semantic_layer.candidates.generator import CandidateGenerator
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import Annotation, ConceptStatus, CounterEvidence, Evidence, EvidenceType, Mapping, SemanticType
from semantic_layer.tests.conftest import DS, TENANT, conventions_for


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
    c = _dim(store, "toptan", "INVOICE", "LG_{n0}_{n1}_INVOICE", "TRCODE", ["8"], pairs=["a"])
    again, created = store.upsert_concept(TENANT, DS, "Toptan", SemanticType.DIMENSION_VALUE, mapping=Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE", column="TRCODE", operator="IN", values=["8"]))
    assert not created and again.id == c.id  # same physical sense
    other, created = store.upsert_concept(TENANT, DS, "toptan", SemanticType.DIMENSION_VALUE, mapping=Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE", column="TRCODE", operator="IN", values=["8"]))
    assert created and other.sense_id == 2
    ev = store.list_evidence(c.id)
    assert ev[0].support_count == 1
    store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "hm", support_count=3, payload={"pairs": ["a", "b", "c"]}))
    assert store.list_evidence(c.id)[0].support_count == 3  # idempotent per source


def test_hard_gate_and_certification(store, synthetic_profiles):
    eng = EvidenceEngine(store, min_support=3)
    weak = _dim(store, "toptan", "INVOICE", "LG_{n0}_{n1}_INVOICE", "TRCODE", ["8"], pairs=["a"])
    strong = _dim(store, "perakende", "INVOICE", "LG_{n0}_{n1}_INVOICE", "TRCODE", ["7"], pairs=["a", "b", "c"], alias=2)
    documented = _dim(store, "iade", "INVOICE", "LG_{n0}_{n1}_INVOICE", "TRCODE", ["2", "3"], pairs=["a"], doc=2)
    ghost = _dim(store, "hayalet", "INVOICE", "LG_{n0}_{n1}_INVOICE", "NOPE", ["1"], pairs=["a", "b", "c", "d"])
    rep = eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(weak.id).status == ConceptStatus.CANDIDATE          # 1 validated, undocumented → not enough
    assert store.get_concept(strong.id).status == ConceptStatus.CERTIFIED        # ≥ 3 validated
    assert store.get_concept(documented.id).status == ConceptStatus.CERTIFIED    # validated + documented + profile fit
    g = store.get_concept(ghost.id)
    assert g.status == ConceptStatus.CANDIDATE and "physical mapping invalid" in g.explain["gate"]["reasons"][0]
    assert rep["catalog_version"] == 1
    # LLM candidate alone can never pass
    llm = _dim(store, "bolgesel", "INVOICE", "LG_{n0}_{n1}_INVOICE", "TRCODE", ["9"], pairs=[])
    store.add_evidence(Evidence(llm.id, EvidenceType.LLM_CANDIDATE, "llm:qwen", weight=0.1, payload={"confidence": 0.97}))
    eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(llm.id).status == ConceptStatus.CANDIDATE


def test_counter_evidence_damps_and_blocks(store, synthetic_profiles):
    eng = EvidenceEngine(store, min_support=3)
    c = _dim(store, "toptan", "INVOICE", "LG_{n0}_{n1}_INVOICE", "TRCODE", ["7", "8"], pairs=list("abcdefghijklmnopq"))  # 17 pairs
    base = eng.evaluate(c, {p.entity: p for p in synthetic_profiles})
    store.add_counter_evidence(CounterEvidence(c.id, "pairs:xyz", "VALUE_MISMATCH", payload={"support": 4}))
    damped = eng.evaluate(c, {p.entity: p for p in synthetic_profiles})
    assert damped.score < base.score and abs(damped.score - base.raw_score * (1 - min(1, 2 * (4 / 21)))) < 1e-6
    store.add_counter_evidence(CounterEvidence(c.id, "human:x", "HUMAN_REJECT", payload={"support": 3}, severity="BLOCKING"))
    assert eng.evaluate(c, {p.entity: p for p in synthetic_profiles}).status == ConceptStatus.REJECTED


def test_sense_conflict_and_doc_dominance(store, synthetic_profiles):
    eng = EvidenceEngine(store, min_support=3)
    a = _dim(store, "iade", "INVOICE", "LG_{n0}_{n1}_INVOICE", "TRCODE", ["2", "3"], pairs=["a", "b", "c", "d"])
    b = _dim(store, "iade", "INVOICE", "LG_{n0}_{n1}_INVOICE", "TRCODE", ["7", "8", "9"], pairs=["e", "f", "g"])
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
    c = _dim(store, "toptan", "INVOICE", "LG_{n0}_{n1}_INVOICE", "TRCODE", ["8"], pairs=["a", "b", "c"])
    eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(c.id).status == ConceptStatus.CERTIFIED
    inv = next(p for p in synthetic_profiles if p.entity == "INVOICE")
    inv.column("TRCODE").top_values = [("7", 100), ("9", 50)]  # 8 disappeared after a Logo customisation
    inv.column("TRCODE").distinct_count = 2
    rep = eng.run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(c.id).status == ConceptStatus.DEPRECATED and rep["drift"][0]["drift"] == "values_gone"


def test_doc_miner_extracts_enum_glosses_and_column_aliases(synthetic_profiles):
    conv = conventions_for(synthetic_profiles)
    facts = mine_text("Fatura türleri (dbo_LG_411_01_INVOICE.TRCODE): 7 perakende satış, 8 toptan satış, 9 verilen hizmet = SATIŞ; 2 perakende satış iadesi, 3 toptan satış iadesi = SATIŞ İADESİ; 1 mal alım, 4 alınan hizmet = SATINALMA; 6 alım iadesi.", "doc:test", None, conv)
    got = {(f.term, f.column, f.values) for f in facts if f.kind == "value"}
    assert ("toptan", "TRCODE", ("8",)) in got and ("perakende", "TRCODE", ("7",)) in got
    assert ("satis", "TRCODE", ("7", "8", "9")) in got and ("satis iade", "TRCODE", ("2", "3")) in got
    assert not any(t == "iade" and v == ("6",) for t, _, v in got)  # 'alım iadesi' never becomes bare 'iade'
    col = {(f.term, f.entity, f.column) for f in mine_text('- "kanal / satış kanalı" = faturanın carisindeki `CLCARD.SPECODE2`; boş = (boş).', "doc:c", None, conv) if f.kind == "column"}
    assert ("kanal", "CLCARD", "SPECODE2") in col and ("satis kanal", "CLCARD", "SPECODE2") in col


def test_a_written_definition_the_data_confirms_is_enough(store, synthetic_profiles):
    """What someone writes in the portal is a definition, and the data either bears it out or it does
    not. Requiring a validated query on top meant a deployment where nobody presses approve could name
    its columns and never say what its codes mean — the part of the business that most needs saying."""
    gen = CandidateGenerator(store, TENANT, DS, synthetic_profiles)
    store.add_annotation(Annotation(datasource_id=DS, table_pattern="LG_{n0}_{n1}_INVOICE", column="TRCODE", text="8 = toptan satış, 7 = perakende satış", author="ayse"))
    rep = gen.ingest_annotation("LG_{n0}_{n1}_INVOICE", "TRCODE", "8 = toptan satış, 7 = perakende satış", "annotation:1")
    assert rep["evidence"] >= 2
    c = store.find_concepts(TENANT, DS, normalized_term="toptan", semantic_type=SemanticType.DIMENSION_VALUE)[0]
    assert c.status == ConceptStatus.CANDIDATE
    assert any(e.evidence_type == EvidenceType.HUMAN_ANNOTATION for e in store.list_evidence(c.id))

    EvidenceEngine(store, min_support=3).run(TENANT, DS, synthetic_profiles)
    assert store.get_concept(c.id).status == ConceptStatus.CERTIFIED

    # and the data still has the last word: a code it never saw on that column stays out
    gen.ingest_annotation("LG_{n0}_{n1}_INVOICE", "TRCODE", "9999 = hayali kanal", "annotation:2")
    EvidenceEngine(store, min_support=3).run(TENANT, DS, synthetic_profiles)
    made_up = store.find_concepts(TENANT, DS, normalized_term="hayali kanal", semantic_type=SemanticType.DIMENSION_VALUE)
    assert all(x.status != ConceptStatus.CERTIFIED for x in made_up), [x.status for x in made_up]


def test_catalog_cache_follows_a_change_that_never_bumped_the_version(store, profiles):
    """A human certification from the portal, or a rebuild that stopped halfway, changes what the
    resolver should see without changing the version number. The cache has to notice."""
    from semantic_layer.models import Evidence, EvidenceType, Mapping, SemanticType
    from semantic_layer.store.catalog_store import ConceptStatus

    for p in profiles:
        store.upsert_profile(p)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    before = store.certified_index(TENANT, DS)
    c, _ = store.upsert_concept(TENANT, DS, "kargo", SemanticType.DIMENSION_VALUE,
                                mapping=Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="TRCODE", operator="IN", values=["4"]),
                                status=ConceptStatus.CANDIDATE)
    store.add_evidence(Evidence(c.id, EvidenceType.HUMAN_ANNOTATION, "portal", support_count=1))
    store.update_concept(c.id, status=ConceptStatus.CERTIFIED, confidence=1.0)
    after = store.certified_index(TENANT, DS)
    assert "kargo" in after and "kargo" not in before
    fp = store.catalog_fingerprint(TENANT, DS)
    assert store.catalog_fingerprint(TENANT, DS) == fp        # stable while nothing changes


def test_documented_value_lands_on_the_table_that_holds_it(store, profiles):
    """A column name does not name a table: in a real schema many tables share one code column.
    Attaching a documented meaning to whichever one came first splits the evidence for a term across
    unrelated tables, so none of them reaches the gate. The data decides which tables it can be about."""
    from semantic_layer.candidates.doc_miner import DocFact
    from semantic_layer.candidates.generator import CandidateGenerator
    from semantic_layer.conventions import Conventions
    from semantic_layer.models import ColumnProfile, SchemaProfile

    # an unrelated table that also has a TRCODE, profiled shallowly so its inventory is unknown
    decoy = SchemaProfile(datasource_id=DS, table_name="LG_411_01_APPROVAL", table_pattern="LG_{n0}_{n1}_APPROVAL",
                          entity="APPROVAL", schema_name="main",
                          columns=[ColumnProfile(name="LOGICALREF", data_type="int", is_primary_key=True),
                                   ColumnProfile(name="TRCODE", data_type="smallint")],
                          primary_key=["LOGICALREF"], context={"n0": "411", "n1": "01"})
    all_profiles = list(profiles) + [decoy]
    for p in all_profiles:
        store.upsert_profile(p)
    gen = CandidateGenerator(store, TENANT, DS, all_profiles, Conventions.from_profiles(all_profiles))
    fact = DocFact("value", "toptan", "doc:rules.md", None, "TRCODE", ("8",), "8 = toptan")
    chosen = gen._entity_for(fact)
    assert chosen != "APPROVAL", "a table whose inventory cannot hold the value is not what the doc means"
    assert chosen in {"INVOICE", "STLINE"} and "8" in {v for v, _ in store.list_profiles(DS) and next(
        p for p in all_profiles if p.entity == chosen).column("TRCODE").top_values}


def test_two_processes_cannot_create_the_same_sense_twice(store, profiles):
    """The store looks a concept up before inserting it, which holds inside one process and not between
    two — the nightly timer and a hand-run pipeline overlap exactly this way. Two rows for one sense
    would split the term's evidence and neither half would reach the gate."""
    from semantic_layer.models import Mapping, SemanticType

    for p in profiles:
        store.upsert_profile(p)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    m = Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="TRCODE", operator="IN", values=["4"])
    first, created = store.upsert_concept(TENANT, DS, "kargo", SemanticType.DIMENSION_VALUE, mapping=m)
    assert created
    # the same insert arriving again, as a second process would issue it
    again, created_again = store.upsert_concept(TENANT, DS, "kargo", SemanticType.DIMENSION_VALUE,
                                                mapping=Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="TRCODE", operator="IN", values=["4"]))
    assert again.id == first.id and not created_again
    rows = [c for c in store.find_concepts(TENANT, DS, normalized_term="kargo") if c.semantic_type == SemanticType.DIMENSION_VALUE]
    assert len(rows) == 1, [c.sense_id for c in rows]


def test_the_gap_list_is_plain_json(store, profiles):
    """The portal returns this through a plain JSON response, where a datetime is a 500 rather than a
    missing field — the page came up empty because the one call that reports what users asked for died."""
    import json

    for p in profiles:
        store.upsert_profile(p)
    store.log_query(TENANT, DS, "Sepet tutarımız nedir?", sql=None, compiler="deterministic",
                    catalog_version=1, resolved={"unresolved": ["sepet"], "unhandled": []}, executed=False)
    gaps = store.term_gaps(TENANT, DS)
    assert gaps and gaps[0]["term"] == "sepet"
    json.dumps({"gaps": gaps})       # would raise on a datetime


def test_a_person_writing_a_definition_is_enough_when_the_data_agrees(store, profiles):
    """A deployment where nobody presses the approve button could define columns and never what its
    codes or its measures mean — the part of the business that actually needs saying. Someone writing
    it down against a table and column is a definition, not a guess. The data still has to agree."""
    from semantic_layer.evidence.engine import EvidenceEngine
    from semantic_layer.models import Evidence, EvidenceType, Mapping, SemanticType
    from semantic_layer.store.catalog_store import ConceptStatus

    for p in profiles:
        store.upsert_profile(p)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    pmap = {p.entity: p for p in profiles}

    # a value the profile actually observed on that column
    good, _ = store.upsert_concept(TENANT, DS, "toptan", SemanticType.DIMENSION_VALUE,
                                   mapping=Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern,
                                                   column="TRCODE", operator="IN", values=["8"]),
                                   status=ConceptStatus.CANDIDATE)
    store.add_evidence(Evidence(good.id, EvidenceType.HUMAN_ANNOTATION, "annotation:1", support_count=1))

    # and a value it never saw there
    bad, _ = store.upsert_concept(TENANT, DS, "hayali", SemanticType.DIMENSION_VALUE,
                                  mapping=Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern,
                                                  column="TRCODE", operator="IN", values=["9999"]),
                                  status=ConceptStatus.CANDIDATE)
    store.add_evidence(Evidence(bad.id, EvidenceType.HUMAN_ANNOTATION, "annotation:2", support_count=1))

    engine = EvidenceEngine(store, min_support=3)
    assert engine.evaluate(store.get_concept(good.id), pmap).status == ConceptStatus.CERTIFIED
    assert engine.evaluate(store.get_concept(bad.id), pmap).status != ConceptStatus.CERTIFIED


def test_the_system_reads_the_schema_itself_but_a_person_still_decides(store, profiles):
    """Tens of thousands of columns nobody has named will not be described by waiting. The table name,
    the column name and the values in it say enough for a reader to propose a meaning — and a proposal
    is filed apart from definitions, because a machine reading a schema is not a business deciding
    what its own words mean."""
    from semantic_layer.candidates.generator import CandidateGenerator
    from semantic_layer.candidates.llm_client import FakeLlm
    from semantic_layer.conventions import Conventions
    from semantic_layer.evidence.engine import EvidenceEngine
    from semantic_layer.store.catalog_store import ConceptStatus

    for p in profiles:
        store.upsert_profile(p)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    gen = CandidateGenerator(store, TENANT, DS, profiles, Conventions.from_profiles(profiles))

    llm = FakeLlm(['[{"entity":"INVOICE","column":"TRCODE","meaning":"Fatura türü",'
                   '"values":{"8":"toptan satış","7":"perakende satış"},"confidence":0.8}]'])
    rep = gen.propose_column_meanings(llm, max_columns=50)
    assert rep["proposed"] == 1, rep

    open_ones = store.list_suggestions(DS)
    assert open_ones and open_ones[0]["column"] == "TRCODE" and "toptan" in open_ones[0]["text"]

    # what it read cannot certify itself, however confident it sounded
    EvidenceEngine(store, min_support=3).run(TENANT, DS, profiles)
    read = [c for c in store.find_concepts(TENANT, DS, normalized_term="toptan satis")]
    assert all(c.status != ConceptStatus.CERTIFIED for c in read), [c.status for c in read]

    # a person accepting it is what makes it a definition
    sug = store.close_suggestion(open_ones[0]["id"], "ACCEPTED")
    gen.ingest_annotation(sug["tablePattern"], sug["column"], sug["text"], "annotation:accepted")
    EvidenceEngine(store, min_support=3).run(TENANT, DS, profiles)
    assert not store.list_suggestions(DS), "a decided suggestion stops being offered"


def test_the_reader_asks_in_batches_and_one_bad_answer_costs_only_its_batch(store, profiles):
    """A hundred columns with their values is more than a local model can read at once — the earlier
    single request came to a hundred thousand tokens against sixteen and answered nothing at all. And
    a batch that comes back unusable must cost only itself."""
    from semantic_layer.candidates.generator import CandidateGenerator
    from semantic_layer.conventions import Conventions

    for p in profiles:
        store.upsert_profile(p)
    gen = CandidateGenerator(store, TENANT, DS, profiles, Conventions.from_profiles(profiles))

    asked: list[str] = []

    class _Counting:
        def chat(self, messages, **kw):
            asked.append(messages[0]["content"])
            if len(asked) == 1:
                return "bu bir JSON değil"          # the first batch is wasted, the rest are not
            return '[{"entity":"INVOICE","column":"TRCODE","meaning":"Fatura türü","confidence":0.7}]'

    import os

    os.environ["SEMANTIC_PROPOSE_BATCH"] = "1"      # tabanı 5: partiler 5'erli gelir
    try:
        rep = gen.propose_column_meanings(_Counting(), max_columns=12)
    finally:
        os.environ.pop("SEMANTIC_PROPOSE_BATCH", None)

    assert len(asked) >= 2, "asked more than once"
    assert all(len(p) < 20_000 for p in asked), "no single request carries the whole schema"
    assert rep["proposed"] >= 1 and rep["asked"] >= 2, rep
