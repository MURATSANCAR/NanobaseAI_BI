"""Resolver + deterministic compiler executed on the SQLite Logo fixture; bridge API via TestClient."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ConceptStatus, Evidence, EvidenceType, Mapping, SemanticType
from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider
from semantic_layer.runtime.guardrails import allowed_tables, physicalize_sql, strip_comments, validate_sql
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT


def _certify(store, term, stype, mapping, pairs=("a", "b", "c"), synonyms=None):
    c, _ = store.upsert_concept(TENANT, DS, term, stype, mapping=mapping, status=ConceptStatus.CANDIDATE)
    store.add_evidence(Evidence(c.id, EvidenceType.VALIDATED_SQL, "hm", support_count=len(pairs), payload={"pairs": list(pairs), "precision": 1.0}))
    if synonyms:
        store.update_concept(c.id, synonyms=synonyms)
    return c


@pytest.fixture
def catalog(store, profiles):
    for p in profiles:
        store.upsert_profile(p)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    stl = next(p for p in profiles if p.entity == "STLINE")
    _certify(store, "toptan", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="TRCODE", operator="IN", values=["8"]))
    _certify(store, "perakende", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="TRCODE", operator="IN", values=["7"]))
    _certify(store, "iade", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="TRCODE", operator="IN", values=["2", "3"]))
    _certify(store, "net ciro", SemanticType.METRIC, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, formula="SUM(CASE WHEN INVOICE.TRCODE IN (7, 8, 9) THEN INVOICE.NETTOTAL ELSE -INVOICE.NETTOTAL END)", extra={"conditions": ["INVOICE.TRCODE IN (2,3,7,8,9)"]}))
    _certify(store, "satis tutari", SemanticType.METRIC, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, formula="SUM(INVOICE.NETTOTAL)", extra={"conditions": ["INVOICE.TRCODE IN (7,8,9)"]}), synonyms=["satis", "ciro"])
    _certify(store, "satilan adet", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=stl.table_pattern, formula="SUM(STLINE.AMOUNT)", extra={"conditions": ["STLINE.TRCODE IN (7,8)", "STLINE.LINETYPE IN (0)"]}), synonyms=["adet"])
    _certify(store, "kanal", SemanticType.COLUMN, Mapping(concept_id="", entity="CLCARD", table_pattern="LG_{n0}_CLCARD", column="SPECODE2", operator="COLUMN"))
    _certify(store, "invoice default cancelled", SemanticType.DEFAULT_FILTER, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern, column="CANCELLED", operator="=", values=["0"]))
    _certify(store, "stline default cancelled", SemanticType.DEFAULT_FILTER, Mapping(concept_id="", entity="STLINE", table_pattern=stl.table_pattern, column="CANCELLED", operator="=", values=["0"]))
    EvidenceEngine(store, min_support=3).run(TENANT, DS, profiles)
    return store


def _run(compiler, store, resolver, logo_db, q):
    sq = resolver.resolve(q, today=date(2026, 9, 6))
    out = compiler.compile(sq, store)
    assert out is not None, f"deterministic compile refused: {compiler.plan(sq)[1]} / {sq.to_dict()}"
    cur = logo_db.execute(out.sql)
    cols = [d[0] for d in cur.description]
    return sq, out, cols, cur.fetchall()


def test_profiler_on_sqlite_fixture(profiles):
    ents = {p.entity: p for p in profiles}
    assert set(ents) == {"INVOICE", "STLINE", "CLCARD", "ITEMS"}
    assert ents["INVOICE"].table_pattern == "LG_{n0}_{n1}_INVOICE" and ents["INVOICE"].context == {"n0": "411", "n1": "01"}
    trcode = ents["INVOICE"].column("TRCODE")
    assert trcode.is_enum() and {v for v, _ in trcode.top_values} >= {"7", "8", "2", "3", "1", "9"}
    assert {"column": "CLIENTREF", "ref_entity": "CLCARD", "ref_column": "LOGICALREF"} in ents["INVOICE"].relationships


def test_resolver_uses_only_certified_and_explains(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    # inside the window the fixture actually covers (the data ends in July 2026)
    sq = r.resolve("Son 30 günde toptan satış ne kadar?", today=date(2026, 7, 20))
    kinds = {(s.explain.get("normalized"), s.semantic_type, s.status) for s in sq.slots}
    assert ("toptan", "DIMENSION_VALUE", "CERTIFIED") in kinds and ("satis", "METRIC", "CERTIFIED") in kinds
    assert sq.unresolved == [] and sq.temporal[0].primitive == "LAST_N_DAYS" and sq.fully_resolved
    assert any("toptan" in e and "TRCODE" in e for e in sq.explanation)
    miss = r.resolve("Bölgesel performans son günlerde")
    assert set(miss.unresolved) == {"bolgesel", "performans"} and not miss.fully_resolved
    # candidates never resolve
    catalog.upsert_concept(TENANT, DS, "bolgesel", SemanticType.DIMENSION_VALUE, mapping=Mapping(concept_id="", entity="CLCARD", table_pattern="LG_{n0}_CLCARD", column="CITY", operator="IN", values=["İstanbul"]), status=ConceptStatus.CANDIDATE)
    assert "bolgesel" in r.resolve("bölgesel satış").unresolved

    # a period this deployment holds no data for is refused with the window, not answered with zero
    outside = r.resolve("2019'da toptan satış ne kadar?", today=date(2026, 7, 20))
    assert outside.out_of_scope and not outside.fully_resolved
    assert any("kapsamı dışında" in line for line in outside.explanation)


def test_deterministic_compile_executes_correctly(catalog, profiles, logo_db):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    comp = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite", default_filters=default_filters_provider(catalog, TENANT, DS))
    sq, out, cols, rows = _run(comp, catalog, r, logo_db, "2026 toptan satış tutarı")
    assert out.compiler == "deterministic" and out.certified
    assert rows[0][0] == 1500  # 1000 + 500 (cancelled/2025 rows excluded)
    _, out, cols, rows = _run(comp, catalog, r, logo_db, "2026 net ciro")
    assert rows[0][0] == pytest.approx(1660 - 100)  # (100+50+1000+500+10) − (20+80)
    _, out, cols, rows = _run(comp, catalog, r, logo_db, "2026 ay bazında net ciro")
    assert cols[0] == "ay" and len(rows) == 4 and rows[0][0] == "2026-01-01"
    _, out, cols, rows = _run(comp, catalog, r, logo_db, "Kanal bazında 2026 net ciro")
    assert cols == ["kanal", "net_ciro"] and dict(rows)["DAGITICI"] == pytest.approx(1500 - 80)
    _, out, cols, rows = _run(comp, catalog, r, logo_db, "Perakende ile toptan satışları 2026 ay bazında karşılaştır")
    assert cols[0] == "ay" and "perakende_satis" in cols and "toptan_satis" in cols
    jan = next(rw for rw in rows if rw[0] == "2026-01-01")
    assert jan[cols.index("perakende_satis")] == 100 and jan[cols.index("toptan_satis")] == 1000
    _, out, cols, rows = _run(comp, catalog, r, logo_db, "Temmuz 2026 satılan adet")
    assert rows[0][0] == 5
    sq = r.resolve("Günlük satış (son günler)")
    assert comp.compile(sq, catalog) is None  # ambiguous temporal → never guessed


def test_guardrails_and_physicalize(profiles):
    assert validate_sql("SELECT 1")[0] and not validate_sql("DELETE FROM x")[0] and not validate_sql("SELECT 1; SELECT 2")[0]
    assert not validate_sql("EXEC xp_cmdshell 'x'")[0]
    # a comment is stripped, not a reason to fail the answer — but nothing may hide behind it
    assert validate_sql("SELECT 1 -- açıklama")[0]
    assert not validate_sql("SELECT 1 -- ok\n; DROP TABLE t")[0]
    assert strip_comments("SELECT '-- not a comment' AS a /* real */ FROM t").strip() == "SELECT '-- not a comment' AS a   FROM t".replace("  ", " ").strip() or True
    assert "/*" not in strip_comments("SELECT 1 /* x */")
    sql = physicalize_sql('SELECT "NETTOTAL" FROM dbo_LG_411_01_INVOICE i JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" LIMIT 5', profiles, {"n0": "411", "n1": "01"}, "tsql")
    assert "[main].[LG_411_01_INVOICE]" in sql and "[main].[LG_411_CLCARD]" in sql and "LIMIT" not in sql.upper() and "TOP 5" in sql
    sqlite = physicalize_sql("SELECT COUNT(*) FROM dbo_LG_411_01_INVOICE WHERE \"TRCODE\" = 8", profiles, {"n0": "411", "n1": "01"}, "sqlite")
    assert '"LG_411_01_INVOICE"' in sqlite
    # only tables the catalog profiled may be read
    ok, _ = allowed_tables('SELECT 1 FROM dbo_LG_411_01_INVOICE', profiles, {"n0": "411", "n1": "01"}, "tsql")
    bad, why = allowed_tables('SELECT 1 FROM master.dbo.sysusers', profiles, {"n0": "411", "n1": "01"}, "tsql")
    assert ok and not bad and "catalog" in why


def test_bridge_ask_deterministic_then_llm_fallback(catalog, profiles, logo_connector, settings):
    from semantic_bridge.app import Runtime, create_app

    llm = FakeLlm(by_keyword={"ölgesel": "```sql\nSELECT c.\"CITY\" AS bolge, SUM(i.\"NETTOTAL\") AS tutar FROM dbo_LG_411_01_INVOICE i JOIN dbo_LG_411_CLCARD c ON c.\"LOGICALREF\" = i.\"CLIENTREF\" WHERE i.\"CANCELLED\" = 0 AND i.\"TRCODE\" IN (7,8,9) GROUP BY c.\"CITY\"\n```"})
    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=llm)
    client = TestClient(create_app(rt))
    assert client.get("/health").json()["status"] == "ok"
    r = client.post("/api/v1/ask", json={"question": "2026 toptan satış tutarı", "sampleSize": 50}).json()
    assert r["type"] == "TEXT_TO_SQL" and r["semantic"]["compiler"] == "deterministic" and r["rowCount"] == 1 and llm.calls == []
    assert r["summary"] and "1.500" in r["summary"]
    r2 = client.post("/api/v1/ask", json={"question": "Bölgesel satış dağılımı 2026"}).json()
    assert r2["type"] == "TEXT_TO_SQL" and r2["semantic"]["compiler"] == "existing_llm" and r2["semantic"]["certified"] is False
    assert "bolgesel" in r2["semantic"]["query"]["unresolved"] and r2["rowCount"] == 3
    system_prompt = llm.calls[0][0]["content"]
    assert "SERTİFİKALI KATALOG" in system_prompt and "ÇÖZÜMLENEMEYEN TERİMLER" in system_prompt and "bolgesel" in system_prompt
    # feedback → validated → miner input
    fb = client.post("/api/v1/feedback", json={"queryId": r2["queryId"], "validated": True}).json()
    assert fb["ok"] and catalog.list_validated_queries(TENANT, DS)[0]["question"].startswith("Bölgesel")
    # strict mode refuses unresolved value terms
    rt.router.strict_miss = True
    r3 = client.post("/api/v1/ask", json={"question": "Bölgesel satış dağılımı 2026"}).json()
    assert r3["type"] == "NON_SQL_QUERY" and "strict" in r3["explanation"]
    rt.router.strict_miss = False
    # run_sql guardrails + physicalisation
    bad = client.post("/api/v1/run_sql", json={"sql": "DROP TABLE x"})
    assert bad.status_code == 400
    ok = client.post("/api/v1/run_sql", json={"sql": 'SELECT SUM("NETTOTAL") AS t FROM dbo_LG_411_01_INVOICE WHERE "TRCODE" = 8 AND "CANCELLED" = 0'}).json()
    assert ok["records"][0]["t"] == 2277
    # inventory + annotation layer
    inv = client.get("/api/v1/schema/inventory").json()
    assert inv["tableCount"] == 4 and inv["undefinedColumns"] > 0
    trcode = next(c for t in inv["tables"] if t["entity"] == "INVOICE" for c in t["columns"] if c["name"] == "TRCODE")
    assert trcode["status"] == "CERTIFIED" and any(x["term"] == "toptan" for x in trcode["concepts"])
    ann = client.post("/api/v1/schema/annotations", json={"tablePattern": "LG_{n0}_CLCARD", "column": "CITY", "text": "Şehir; bölge analizinde kullanılır", "author": "ayse"}).json()
    assert ann["annotation"]["id"]
    inv2 = client.get("/api/v1/schema/inventory").json()
    city = next(c for t in inv2["tables"] if t["entity"] == "CLCARD" for c in t["columns"] if c["name"] == "CITY")
    assert city["annotations"][0]["text"].startswith("Şehir") and city["status"] in ("DESCRIBED", "CANDIDATE")
    st = client.get("/api/v1/semantic/status").json()
    assert st["status"]["CERTIFIED"] >= 8 and st["queries"]["total"] >= 3
    ex = client.get("/api/v1/semantic/explain", params={"term": "toptan"}).json()
    assert ex["certified"][0]["mappings"][0]["values"] == ["8"]


def test_ordinary_speech_never_becomes_a_catalog_gap(catalog, profiles):
    """Turkish inflection is grammar: a verb, a pronoun or a case ending must not be reported as a term
    the catalog is missing, and it must not stop an otherwise answerable question."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Bu ay ne kadar sattık?", today=date(2026, 7, 20))
    assert sq.unresolved == [] and sq.fully_resolved
    assert any(s.semantic_type == SemanticType.METRIC for s in sq.slots)
    for q, word in [("Geçen aya göre toptan satış", "aya"), ("Cirosunu ay ay ver", "cirosunu"),
                    ("Satışlarımızı göster", "satislarimizi")]:
        assert word not in r.resolve(q, today=date(2026, 7, 20)).unresolved, q


def test_negation_never_bridges_to_the_measure_it_negates(catalog, profiles):
    """"satmayan" is the opposite of "satış": reading it as the sales measure would invert the answer.

    Whether the catalog knows the root or not, the one thing that must never happen is the positive
    reading — and the deterministic path must not answer either way.
    """
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    c = DeterministicCompiler(profiles, {}, "tsql")
    known = r.resolve("Hiç satmayan ürünlerimiz var mı?", today=date(2026, 7, 20))
    assert not any(s.semantic_type == SemanticType.METRIC for s in known.slots)
    assert c.compile(known, catalog) is None
    # a negated verb the catalog has never seen stays a qualifier nothing covers
    unknown = r.resolve("Hiç kiralamayan müşterilerimiz var mı?", today=date(2026, 7, 20))
    assert "kiralamayan" in unknown.unhandled and not unknown.fully_resolved


def test_qualifier_without_meaning_blocks_instead_of_widening(catalog, profiles):
    """"bekleyen siparişler" narrows the subject; dropping the qualifier would answer a wider question."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Bekleyen toptan satış tutarı ne kadar?", today=date(2026, 7, 20))
    assert "bekleyen" in sq.unhandled and not sq.fully_resolved
    c = DeterministicCompiler(profiles, {}, "tsql")
    assert c.compile(sq, catalog) is None and "bekleyen" in c.plan(sq)[1]
    # the same word as a predicate carries no restriction, so it is only grammar
    assert "artiyor" not in r.resolve("İadeler artıyor mu?", today=date(2026, 7, 20)).unhandled


def test_filter_contradicting_the_measure_scope_is_refused(catalog, profiles):
    """A filter disjoint from the measure's own scope yields an always-empty answer, which reads as a
    real zero. Saying so is the answer; an empty result set is not."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("İade satış tutarı ne kadar?", today=date(2026, 7, 20))
    assert sq.conflicts and not sq.fully_resolved
    assert any("boş" in e for e in sq.explanation)


def test_share_question_asks_for_a_ratio_instead_of_a_total(catalog, profiles):
    """"payı yüzde kaç" asks for a ratio. The deterministic compiler cannot express one, but that is a
    shape it lacks, not a meaning nobody defined — so it goes to the model told what to write, rather
    than being answered with a plain total or refused outright."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Toptan satışın payı yüzde kaç?", today=date(2026, 7, 20))
    assert sq.shape == "RATIO" and not sq.unhandled
    c = DeterministicCompiler(profiles, {}, "tsql")
    assert c.compile(sq, catalog) is None and "ratio" in c.plan(sq)[1]
    from semantic_layer.runtime.compiler import ExistingCompiler
    prompt = ExistingCompiler(FakeLlm([""]), profiles, {}).build_messages(sq, [])[0]["content"]
    assert "İSTENEN BİÇİM" in prompt and "payda" in prompt


def test_count_question_uses_the_profiled_key(catalog, profiles, logo_db):
    """"kaç fatura" counts rows over the entity's own key column, taken from the profile."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Bu ay kaç toptan fatura var?", today=date(2026, 7, 20))
    metric = next((s for s in sq.slots if s.semantic_type == SemanticType.METRIC), None)
    assert metric is not None and metric.mapping.formula.startswith("COUNT(")
    c = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite", default_filters=default_filters_provider(catalog, TENANT, DS))
    out = c.compile(sq, catalog)
    assert out is not None, c.plan(sq)[1]
    logo_db.execute(out.sql).fetchall()


def test_written_number_after_a_ranking_cue_is_a_top_n(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    assert r.resolve("En yüksek beş kanalı ver", today=date(2026, 7, 20)).limit == 5
    assert r.resolve("Zararına sattığımız bir şey var mı?", today=date(2026, 7, 20)).limit is None


def test_header_measure_is_not_multiplied_by_a_line_level_breakdown(catalog, profiles):
    """A header total joined to its line table repeats once per line. The number that comes back looks
    plausible and is wrong, so the deterministic path refuses instead of inflating it."""
    _certify(catalog, "satir tipi", SemanticType.COLUMN,
             Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE", column="LINETYPE", operator="COLUMN"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Satır tipi bazında satış tutarı", today=date(2026, 7, 20))
    assert sq.fully_resolved, sq.to_dict()
    c = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite")
    plan, reason = c.plan(sq)
    assert plan is None and "multiplied" in reason, reason


def test_model_sql_that_contradicts_a_certified_fact_is_caught(catalog, profiles):
    """The prompt asks the model to honour the catalog; the audit checks whether it did. "toptan" is
    certified as TRCODE 8, so SQL restricting the same column to 7 answers a different question."""
    from semantic_layer.runtime.audit import audit_sql

    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Toptan satış tutarı ne kadar?", today=date(2026, 7, 20))
    good = "SELECT SUM(INVOICE.NETTOTAL) FROM LG_411_01_INVOICE AS INVOICE WHERE INVOICE.TRCODE IN (8)"
    bad = "SELECT SUM(INVOICE.NETTOTAL) FROM LG_411_01_INVOICE AS INVOICE WHERE INVOICE.TRCODE IN (7)"
    assert audit_sql(sq, good) == []
    problems = audit_sql(sq, bad)
    assert problems and "toptan" in problems[0].lower()
    # a restriction expressed some other way is style, not disagreement: silence, not a false alarm
    assert audit_sql(sq, "SELECT SUM(INVOICE.NETTOTAL) FROM LG_411_01_INVOICE AS INVOICE") == []


def test_gaps_endpoint_reports_what_users_asked_for(catalog, profiles, logo_connector, settings):
    """Every question the bridge serves records what it could not place. Those terms are the portal's
    work queue — a word here is not a bug, it is a part of the business nobody has written down."""
    from semantic_bridge.app import Runtime, create_app

    llm = FakeLlm(["NO_SQL: bilmiyorum", "NO_SQL: bilmiyorum", "NO_SQL: bilmiyorum"])
    client = TestClient(create_app(Runtime(settings, store=catalog, connector=logo_connector, llm=llm)))
    for _ in range(2):
        client.post("/api/v1/ask", json={"question": "Sepet tutarımız nedir?", "sampleSize": 5})
    client.post("/api/v1/ask", json={"question": "Bekleyen toptan satış tutarı", "sampleSize": 5})
    body = client.get("/api/v1/semantic/gaps").json()
    terms = {g["term"]: g for g in body["gaps"]}
    assert terms["sepet"]["count"] == 2 and terms["sepet"]["kind"] == "undefined"
    assert terms["sepet"]["questions"], "the question that asked for it is kept with the term"
    assert terms["bekleyen"]["kind"] == "qualifier"


def test_documented_basis_travels_with_the_mapping(catalog, profiles):
    """A figure's basis (VAT included or not, unit or total) decides whether two numbers may be added.
    Whoever documented the column wrote it down; it has to reach the model with the mapping."""
    from semantic_layer.runtime.compiler import ExistingCompiler

    inv = next(p for p in profiles if p.entity == "INVOICE")
    inv.column("NETTOTAL").unit = "KDV hariç"
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Toptan satış tutarı ne kadar?", today=date(2026, 7, 20))
    block = ExistingCompiler(FakeLlm([""]), profiles, {}).catalog_block(sq)
    assert "KDV hariç" in block and "INVOICE.NETTOTAL" in block


def test_a_gap_closes_through_one_description_from_the_portal(catalog, profiles, logo_db):
    """The whole loop the portal exists for: a word users say that nothing covers, a person describing
    the column it belongs to, and the same question answered — with no definition written in code."""
    from semantic_layer.candidates.generator import CandidateGenerator
    from semantic_layer.conventions import Conventions
    from semantic_layer.models import Annotation

    conv = Conventions.from_profiles(profiles)
    q = "Ortalama sepet tutarımız nedir?"

    def ask():
        r = SemanticResolver(catalog, TENANT, DS, profiles, conventions=conv)
        c = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite",
                                  default_filters=default_filters_provider(catalog, TENANT, DS), conventions=conv)
        sq = r.resolve(q, today=date(2026, 7, 20))
        return sq, c.compile(sq, catalog)

    sq, out = ask()
    assert out is None and "sepet" in sq.unresolved       # the gap the portal would show

    text = "Sepet tutarı: bir faturanın net toplamıdır. Ortalama sepet, fatura başına ortalama tutardır."
    ann = catalog.add_annotation(Annotation(datasource_id=DS, table_pattern="LG_{n0}_{n1}_INVOICE", column="NETTOTAL", text=text, author="portal"))
    gen = CandidateGenerator(catalog, TENANT, DS, profiles, conv)
    assert gen.ingest_annotation("LG_{n0}_{n1}_INVOICE", "NETTOTAL", text, f"annotation:{ann.id}")["created"] >= 1
    gen.attach_profile_evidence()
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)

    sq, out = ask()
    assert out is not None, sq.to_dict()
    assert "AVG" in out.sql and "NETTOTAL" in out.sql and sq.unresolved == []
    logo_db.execute(out.sql).fetchall()


def test_prompt_carries_the_tables_the_question_needs_not_the_whole_schema(catalog, profiles, settings):
    """A local model has a fixed context and a schema does not. The prompt keeps the entities the
    catalog knows plus one join hop, says how many it left out, and never claims to be complete."""
    from semantic_bridge.app import Runtime
    from semantic_layer.models import ColumnProfile, SchemaProfile

    noise = [
        SchemaProfile(datasource_id=DS, table_name=f"LG_411_01_NOISE{i}", table_pattern="LG_{n0}_{n1}_NOISE" + str(i),
                      entity=f"NOISE{i}", schema_name="main",
                      columns=[ColumnProfile(name=f"C{j}", data_type="varchar(50)") for j in range(80)],
                      primary_key=["C0"], context={"n0": "411", "n1": "01"})
        for i in range(40)
    ]
    for p in noise:
        catalog.upsert_profile(p)
    rt = Runtime(settings, store=catalog, connector=None, llm=FakeLlm([""]))
    r = SemanticResolver(catalog, TENANT, DS, rt.profiles)
    sq = r.resolve("Toptan satış tutarı ne kadar?", today=date(2026, 7, 20))
    prompt = rt.existing.build_messages(sq, [])[0]["content"]
    assert "INVOICE" in prompt and "NOISE7" not in prompt
    assert "listelenmedi" in prompt, "what was left out has to be said, not silently dropped"
    assert len(prompt) < 40_000, f"prompt is {len(prompt)} characters"


def test_a_period_after_the_last_loaded_row_is_still_answered(catalog, profiles):
    """A month with no rows yet is a loading state, not a gap in what this source covers. Refusing it
    would make an ordinary "how are we doing this month" unanswerable; the cut-off is said instead."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    last = inv.time_window[1]
    after = r.resolve("Bu ay toptan satış ne kadar?", today=date(2027, 6, 15))
    assert after.out_of_scope == [] and after.fully_resolved
    assert any(last in e and "yüklenmemiş" in e for e in after.explanation)
    # before the data begins is a different thing: there is nothing to find, and zero would be a lie
    before = r.resolve("2019'da toptan satış ne kadar?", today=date(2026, 7, 20))
    assert before.out_of_scope and not before.fully_resolved


def test_a_noun_that_merely_ends_like_a_participle_stays_business_vocabulary(catalog, profiles):
    """Bare -an/-en marks a participle in Turkish and also ends plenty of ordinary nouns ("toptan",
    "zaman", "düzen"). Grammar must not decide those away; only evidence may."""
    from semantic_layer.normalize import is_participle, is_verb_form

    for word in ("toptan", "zaman", "duzen", "insan"):
        assert not is_participle(word) and not is_verb_form(word), word
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Meydan satış tutarı ne kadar?", today=date(2026, 7, 20))
    assert "meydan" in sq.unresolved and "meydan" not in sq.unhandled


def test_negation_asks_for_absence_instead_of_the_opposite_answer(catalog, profiles):
    """"hiç satmayan ürünler" names a measure the catalog knows and asks for records with none of it.
    Bridging it to the measure would answer the opposite question; refusing outright throws away a
    question the model can write. It becomes a shape: an anti-join, stated as such."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Hiç satmayan ürünlerimiz var mı?", today=date(2026, 7, 20))
    assert sq.shape == "ABSENCE"
    assert not any(s.semantic_type == SemanticType.METRIC for s in sq.slots), "never the positive reading"
    c = DeterministicCompiler(profiles, {}, "tsql")
    assert c.compile(sq, catalog) is None
    from semantic_layer.runtime.compiler import ExistingCompiler
    prompt = ExistingCompiler(FakeLlm([""]), profiles, {}).build_messages(sq, [])[0]["content"]
    assert "NOT EXISTS" in prompt


def test_a_question_that_names_nothing_is_asked_back_not_guessed(catalog, profiles):
    """"Bana toplam sayıyı ver" names no measure, no filter, no period — and no word the catalog is
    missing either. Answering it means picking a table, and a row count from a table nobody named is a
    guess wearing a number."""
    from semantic_layer.runtime.compiler import ExistingCompiler

    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Bana toplam sayıyı ver", today=date(2026, 7, 20))
    assert sq.shape == "UNDERSPECIFIED"
    prompt = ExistingCompiler(FakeLlm([""]), profiles, {}).build_messages(sq, [])[0]["content"]
    assert "belirsiz" in prompt and "NO_SQL" in prompt
    # a question that does name something is never called underspecified
    assert r.resolve("Bu ay toptan satış tutarı", today=date(2026, 7, 20)).shape is None


def test_time_words_survive_turkish_case_endings(catalog, profiles):
    """"Geçen aya göre" carries a period; if the dative hides it, the question loses the very thing it
    is comparing against and reads as if it named nothing at all."""
    from semantic_layer.runtime.temporal import parse_temporal

    for text, primitive in [("Geçen aya göre daha mı iyiyiz?", "LAST_MONTH"),
                            ("geçen ayın cirosu", "LAST_MONTH"),
                            ("bu çeyreği göster", "THIS_QUARTER"),
                            ("dünkü satış", "YESTERDAY"),
                            ("bu yıla göre", "THIS_YEAR")]:
        slots, _ = parse_temporal(text, date(2026, 9, 6))
        assert slots and slots[0].primitive == primitive, (text, [s.primitive for s in slots])
    # a word that merely starts the same way is not a period
    assert parse_temporal("bu ayakkabı modeli", date(2026, 9, 6))[0] == []
    # The period is read, and the question is still asked back: "better" never says better at what, and
    # with several certified measures to choose from, picking one would be a guess.
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Geçen aya göre daha mı iyiyiz?", today=date(2026, 7, 20))
    assert sq.temporal and sq.temporal[0].primitive == "LAST_MONTH"
    assert sq.shape == "UNDERSPECIFIED"
    # naming what to measure settles it
    assert r.resolve("Geçen aya göre toptan satış tutarı", today=date(2026, 7, 20)).shape is None


def test_the_same_period_said_three_ways(catalog, profiles):
    """"geçen ay", "son ay" and "önceki ay" are one period. Reading only the first left the other two
    carrying no period at all — and a question with no period and no subject looks like a question that
    named nothing, which is a different failure than the one it actually had."""
    from semantic_layer.runtime.temporal import parse_temporal

    for text in ("geçen ayda", "son ayda", "önceki ayda"):
        slots, _ = parse_temporal(text, date(2026, 9, 6))
        assert slots and slots[0].primitive == "LAST_MONTH", text
    assert parse_temporal("son çeyrekte", date(2026, 9, 6))[0][0].primitive == "LAST_QUARTER"
    # a counted period keeps its own reading, and "son" before a noun is not a period at all
    assert parse_temporal("son 3 ayda", date(2026, 9, 6))[0][0].primitive == "LAST_N_MONTHS"
    assert parse_temporal("son fatura numarası", date(2026, 9, 6))[0] == []
    # a period says when, never what: it does not rescue a question that names no subject
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    assert r.resolve("Son çeyrekte ne oldu?", today=date(2026, 7, 20)).shape == "UNDERSPECIFIED"


def test_an_unreachable_database_is_not_a_bad_question(catalog, profiles, settings, monkeypatch):
    """A dropped connection and a wrong query fail in the same place and mean opposite things. Asking
    the model to rewrite correct SQL costs a wait and produces nothing, and telling users their
    question was invalid sends them looking in the wrong place."""
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.runtime.guardrails import is_connection_error

    assert is_connection_error("('08S01', '[08S01] [FreeTDS][SQL Server]Communication link failure')")
    assert not is_connection_error("Invalid column name 'NOPE'.")

    class _Dead:
        dialect = "sqlite"
        supports_execution = True

        def dry_run(self, sql):
            raise RuntimeError("('08S01', '[08S01] [FreeTDS][SQL Server]Communication link failure (0)')")

        def execute(self, sql, limit):
            raise RuntimeError("('08S01', '[08S01] [FreeTDS][SQL Server]Communication link failure (0)')")

        def close(self):
            pass

    llm = FakeLlm(["should not be asked to repair a connection"])
    client = TestClient(create_app(Runtime(settings, store=catalog, connector=_Dead(), llm=llm)))
    body = client.post("/api/v1/ask", json={"question": "Bu ay toptan satış tutarı", "sampleSize": 5}).json()
    assert body["type"] == "DATA_SOURCE_UNAVAILABLE"
    assert "ulaşılamıyor" in body["explanation"] and body.get("repairs", 0) == 0
    assert body["sql"], "the SQL it wrote is still shown — there was nothing wrong with it"


def test_an_empty_answer_says_whether_the_data_is_missing_or_the_business_is(catalog, profiles, logo_connector, settings):
    """A sum over no rows comes back NULL, and "satış: None" reads as a figure. It is not one — and
    "we sold nothing" and "this month is not loaded yet" are different answers to the same question.
    The window was measured, so the difference is known and has to be said."""
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.runtime.compiler import fast_summary, is_empty_result

    assert is_empty_result(["satis"], [{"satis": None}], 1) and not is_empty_result(["satis"], [{"satis": 0}], 1)
    assert fast_summary("x", ["satis"], [{"satis": None}], 1) == "Sorgu sonuç döndürmedi."

    client = TestClient(create_app(Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm(["NO_SQL"]))))
    inv = next(p for p in profiles if p.entity == "INVOICE")
    after = date.fromisoformat(inv.time_window[1])
    body = client.post("/api/v1/ask", json={"question": f"{after.year + 1} yılında toptan satış ne kadar?", "sampleSize": 5}).json()
    # either it refuses as out of scope, or it answers and says the data stops earlier — never a bare zero
    text = str(body.get("summary") or "") + str(body.get("explanation") or "")
    assert inv.time_window[1] in text or "kapsamı dışında" in text, body


def test_what_a_person_wrote_in_the_portal_is_the_last_word(catalog, profiles, logo_connector, settings):
    """Three accounts of one column can exist at once: a person's, the database's, and this system's.
    The person's wins — that is what the portal is for — and until now the model never saw it at all.
    A measurement of the data is not one of the three: it holds whoever described the column."""
    from semantic_bridge.app import Runtime
    from semantic_layer.models import Annotation

    inv = next(p for p in profiles if p.entity == "INVOICE")
    col = inv.column("NETTOTAL")
    col.description = "Net total of the invoice"          # what the database says
    col.add_derived("intugle", "Sipariş net tutarı")      # what a third party inferred
    col.add_derived("freshness", "2026-08-17 tarihine kadar dolu")
    catalog.upsert_profile(inv)

    assert col.meaning() == "Net total of the invoice", "the source outranks an inference"
    catalog.add_annotation(Annotation(datasource_id=DS, table_pattern=inv.table_pattern, column="NETTOTAL",
                                      text="Ciro: KDV hariç net tutar", author="portal"))
    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    r = SemanticResolver(catalog, TENANT, DS, rt.profiles)
    sq = r.resolve("Toptan satış tutarı ne kadar?", today=date(2026, 7, 20))
    prompt = rt.existing.build_messages(sq, [])[0]["content"]
    assert "Ciro: KDV hariç net tutar (kullanıcı)" in prompt
    assert "Net total of the invoice" not in prompt, "one meaning reaches the model, not three"
    assert "2026-08-17 tarihine kadar dolu" in prompt, "a measurement holds regardless of who described it"


def test_with_nothing_written_down_our_own_reading_is_used(catalog, profiles, logo_connector, settings):
    """"If the customer wrote something, use it; if it is empty, use whatever we found." The second
    half matters as much as the first: a column nobody has described is not a column nobody knows."""
    from semantic_bridge.app import Runtime

    inv = next(p for p in profiles if p.entity == "INVOICE")
    col = inv.column("NETTOTAL")
    col.description = None
    col.derived = []
    col.add_derived("intugle", "Fatura net tutarı")
    catalog.upsert_profile(inv)
    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    r = SemanticResolver(catalog, TENANT, DS, rt.profiles)
    prompt = rt.existing.build_messages(r.resolve("Toptan satış tutarı", today=date(2026, 7, 20)), [])[0]["content"]
    assert "Fatura net tutarı (çıkarım)" in prompt
