import copy
import json
import sys
from pathlib import Path

import pytest

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.models import ColumnProfile, SchemaProfile, SemanticQuery
from semantic_layer.runtime.compiler import CompilerRouter, ExistingCompiler
from semantic_layer.runtime.language_pool import LanguagePool, atomic_write, schema_documents, validate_candidate


def profiles():
    return [SchemaProfile(datasource_id="d", entity="ORDER", table_name="orders", table_pattern="orders",
                          columns=[ColumnProfile("ID", is_primary_key=True), ColumnProfile("AMOUNT", description="Sipariş tutarı"),
                                   ColumnProfile("CLIENT", ref_entity="CLIENT", ref_column="ID"), ColumnProfile("SECRET", sensitive=True)],
                          relationships=[{"column": "CLIENT", "ref_entity": "CLIENT", "ref_column": "ID"}]),
            SchemaProfile(datasource_id="d", entity="CLIENT", table_name="clients", table_pattern="clients",
                          columns=[ColumnProfile("ID", is_primary_key=True), ColumnProfile("NAME", description="Müşteri adı")]),
            SchemaProfile(datasource_id="d", entity="UNRELATED", table_name="elsewhere", table_pattern="elsewhere",
                          columns=[ColumnProfile("ID")])]


def candidate(phrase="Müşterilerin sipariş hacmi ne kadar?"):
    return {"phrase": phrase, "operation": "aggregate", "ambiguities": ["İptal kapsamı ayrıca doğrulanmalı"],
            "columns": [{"entity": "ORDER", "column": "AMOUNT", "role": "measure"},
                        {"entity": "CLIENT", "column": "NAME", "role": "dimension"}]}


def write_pool(path, ps, *raw):
    entries = [validate_candidate(c, schema_documents(ps)) for c in raw]
    atomic_write(path, {"version": 1, "datasourceId": "d", "entries": entries})
    return LanguagePool.load(path, ps, "d")


@pytest.mark.parametrize("entity,column", [("ORDER", "MISSING"), ("ORDER", "SECRET"), ("NOT_REAL", "ID"), ("UNRELATED", "ID")])
def test_generated_references_must_exist_and_be_connected(entity, column):
    raw = candidate()
    raw["columns"][1].update(entity=entity, column=column)
    with pytest.raises(ValueError):
        validate_candidate(raw, schema_documents(profiles()))


def test_schema_changes_withdraw_candidates_but_new_rows_do_not(tmp_path):
    ps = profiles(); path = tmp_path / "pool.json"
    write_pool(path, ps, candidate())
    ps[0].row_count = 700
    ps[0].columns[1].top_values = [("999", 10)]
    assert len(LanguagePool.load(path, ps, "d").entries) == 1
    ps[0].columns[1].description = "Farklı anlam"
    pool = LanguagePool.load(path, ps, "d")
    assert pool.entries == [] and pool.rejected == 1
    with pytest.raises(ValueError):
        LanguagePool.load(path, ps, "another-source")


def test_source_annotations_and_units_are_versioned(tmp_path):
    ps = profiles(); path = tmp_path / "pool.json"
    write_pool(path, ps, candidate())
    assert LanguagePool.load(path, ps, "d", {("ORDER", "AMOUNT"): "Brüt tutar"}).entries == []
    ps[0].columns[1].unit = "KDV dahil"
    assert LanguagePool.load(path, ps, "d").entries == []


def test_pool_never_promotes_generated_meaning_or_clears_a_clarification(tmp_path):
    pool = write_pool(tmp_path / "pool.json", profiles(), candidate())
    q = SemanticQuery(candidate()["phrase"], "t", "d", unhandled=["bekleyen"], clarification=["Hangi durum?"],
                      language_candidates=pool.search(candidate()["phrase"]))
    out = CompilerRouter(None, None).compile(q, None)
    assert out.compiler == "clarification" and not out.sql
    assert q.unhandled == ["bekleyen"] and not q.slots
    assert q.to_dict()["languageCandidates"][0]["status"] == "SCHEMA_CHECKED_CANDIDATE"


def test_generated_language_retains_relevant_columns_without_certifying_them(tmp_path):
    ps = profiles()
    ps[0].columns.extend(ColumnProfile(f"UNUSED{i}") for i in range(50))
    pool = write_pool(tmp_path / "pool.json", ps, candidate())
    compiler = ExistingCompiler(None, ps, {}, dialect="tsql")
    compiler.language_pool = pool
    compiler.selector_mode = "off"
    q = SemanticQuery(candidate()["phrase"], "t", "d")
    assert ("ORDER", "AMOUNT") in compiler._scored_columns(q.question)
    assert "ORDER" in compiler.relevant_entities(q, [])
    shown, _ = compiler.prompt_columns(ps[0], q)
    assert "AMOUNT" in {c.name for c in shown}
    assert "UNUSED10" not in {c.name for c in shown}
    messages = compiler.build_messages(q, [])
    assert "ÜRETİLMİŞ İFADE ADAYLARI" in str(messages)
    assert q.slots == [] and q.candidates == []


def test_negative_and_positive_phrases_are_distinct_and_exact_match_wins(tmp_path):
    positive = candidate("Siparişi olan müşteriler")
    negative = candidate("Siparişi olmayan müşteriler")
    negative["operation"] = "absence"
    pool = write_pool(tmp_path / "pool.json", profiles(), positive, negative)
    assert len(pool.entries) == 2
    assert pool.search(negative["phrase"])[0]["operation"] == "absence"


def test_invalid_status_is_not_a_way_to_inject_certified_rules(tmp_path):
    path = tmp_path / "pool.json"
    write_pool(path, profiles(), candidate())
    payload = json.loads(path.read_text())
    payload["entries"][0]["status"] = "CERTIFIED"
    atomic_write(path, payload)
    assert not LanguagePool.load(path, profiles(), "d").entries


def test_generator_resumes_and_regenerates_changed_sources(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from build_language_pool import extend_pool
    ps = profiles(); path = tmp_path / "pool.json"
    raw = candidate()
    raw["columns"] = raw["columns"][:1]
    llm = FakeLlm([json.dumps({"candidates": [raw]})] * 2)
    kwargs = dict(entities=["ORDER"], max_batches=1, count=2, page_size=24)
    first = extend_pool(llm, ps, "d", path, **kwargs)
    assert first["poolSize"] == 1
    assert extend_pool(llm, ps, "d", path, **kwargs)["completed"] == 0
    ps[0].columns[1].description = "Net sipariş tutarı"
    changed = extend_pool(llm, ps, "d", path, **kwargs)
    assert changed["staleRemoved"] == 1 and changed["poolSize"] == 1
    assert len(llm.calls) == 2
    assert "SECRET" not in json.dumps(llm.calls)


def test_generator_rejects_unknown_entities_before_spending_llm_calls(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from build_language_pool import extend_pool
    llm = FakeLlm([])
    with pytest.raises(ValueError, match="Unknown entities"):
        extend_pool(llm, profiles(), "d", tmp_path / "pool.json", entities=["CLIENT", "MISSING"])
    assert not llm.calls


def test_generator_round_robin_covers_tables_before_second_pages():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from build_language_pool import batches
    docs = schema_documents(profiles())
    jobs = list(batches(docs, ["ORDER", "UNRELATED"], page_size=1))
    assert "ORDER" in jobs[0][1]
    assert "UNRELATED" in jobs[1][1]
    assert "ORDER" in jobs[2][1]


def test_generator_self_relationship_cannot_replace_the_root_page():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from build_language_pool import batches
    ps = profiles()
    ps[0].columns.extend(ColumnProfile(f"X{i:02d}") for i in range(30))
    ps[0].relationships.append({"column": "ID", "ref_entity": "ORDER", "ref_column": "ID"})
    docs = schema_documents(ps)
    jobs = list(batches(docs, ["ORDER"], page_size=24))
    selected = set().union(*(set(ctx["ORDER"]["columns"]) for _, ctx in jobs))
    assert selected == set(docs["ORDER"]["columns"])
    assert len(jobs[0][1]["ORDER"]["columns"]) >= 24


def test_one_shared_word_and_its_suffix_variant_are_not_two_pieces_of_evidence(tmp_path):
    raw=candidate("Amortisman oranı en yüksek sabit kıymetler")
    pool=write_pool(tmp_path / "pool.json",profiles(),raw)
    assert not pool.search("2026 iade oranı")
    assert pool.search(raw["phrase"])[0]["id"]==pool.entries[0]["id"]


def test_source_change_outside_shown_page_still_regenerates_withdrawn_entries(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from build_language_pool import extend_pool
    ps=profiles()
    ps[0].columns.extend(ColumnProfile(f"ZZ{i:02d}") for i in range(30))
    raw=candidate();raw["columns"]=raw["columns"][:1]
    llm=FakeLlm([json.dumps({"candidates":[raw]})]*2)
    path=tmp_path / "pool.json"
    kwargs=dict(entities=["ORDER"],max_batches=1,count=1,page_size=4)
    assert extend_pool(llm,ps,"d",path,**kwargs)["poolSize"]==1
    ps[0].columns[-1].description="Changed outside the first page"
    again=extend_pool(llm,ps,"d",path,**kwargs)
    assert again["staleRemoved"]==1 and again["poolSize"]==1
    assert len(llm.calls)==2
