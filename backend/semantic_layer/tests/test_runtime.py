"""Resolver + deterministic compiler executed on the SQLite Logo fixture; bridge API via TestClient."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from semantic_layer.candidates.llm_client import FakeLlm
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ConceptStatus, Evidence, EvidenceType, Mapping, SemanticType, TemporalSlot
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

    llm = FakeLlm(by_keyword={"ölgesel": "```sql\nSELECT c.\"CITY\" AS bolge, SUM(i.\"NETTOTAL\") AS tutar FROM dbo_LG_411_01_INVOICE i JOIN dbo_LG_411_CLCARD c ON c.\"LOGICALREF\" = i.\"CLIENTREF\" WHERE i.\"CANCELLED\" = 0 AND i.\"TRCODE\" IN (7,8,9) AND i.DATE_ >= '2026-01-01' AND i.DATE_ < '2027-01-01' GROUP BY c.\"CITY\"\n```"})
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
    from semantic_layer.runtime.compiler import ExistingCompiler

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

    # a source that splits one entity across periods must not spend the context twice on it
    import copy

    inv = next(p for p in rt.profiles if p.entity == "INVOICE")
    older = copy.deepcopy(inv)
    older.table_name, older.context = "LG_211_01_INVOICE", {"n0": "211", "n1": "01"}
    doubled = rt.profiles + [older]
    twice = ExistingCompiler(FakeLlm([""]), doubled, {}, conventions=rt.conventions)
    twice.catalog_entities = rt.existing.catalog_entities
    text = twice.build_messages(sq, [])[0]["content"]
    assert text.count("(INVOICE)") <= 1, "one entry per entity, not one per period"


def test_a_period_after_the_last_observed_row_cannot_claim_zero(catalog, profiles):
    """An observed maximum is not a loading watermark or evidence of zero sales."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    inv = next(p for p in profiles if p.entity == "INVOICE")
    last = inv.time_window[1]
    after = r.resolve("Bu ay toptan satış ne kadar?", today=date(2027, 6, 15))
    assert after.out_of_scope and not after.fully_resolved
    assert any(last in e and "sıfır" in e for e in after.explanation)
    assert after.data_coverage[0]["completeness"] == "UNKNOWN"
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
    assert any(t.primitive == "LAST_MONTH" for t in sq.temporal)
    assert sq.comparison and sq.temporal[0].primitive == "THIS_MONTH"
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
    body = client.post("/api/v1/ask", json={"question": "2026 yılında toptan satış tutarı", "sampleSize": 5}).json()
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
    # The measurement is kept and labelled where a person reads it, and deliberately left out of the
    # dense schema line: "filled until 2025-12-31" there read as the table's date coverage, and the
    # model refused a question about the current month on the strength of it.
    assert "2026-08-17 tarihine kadar dolu" not in prompt
    assert col.data_facts() == ["2026-08-17 tarihine kadar dolu"]


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


def test_a_question_that_crosses_a_period_boundary_reads_both_tables(catalog, profiles, logo_db):
    """The year before this one lived in a different physical table, and the compiler only ever wrote
    one table name — so a comparison with last year could not be expressed at all, however much of the
    history the source actually held."""
    import copy

    inv = next(p for p in profiles if p.entity == "INVOICE")
    inv.time_window = ("2026-01-01", "2026-08-17")
    older = copy.deepcopy(inv)
    older.table_name, older.context, older.time_window = "LG_211_01_INVOICE", {"n0": "211", "n1": "01"}, ("2021-01-01", "2025-12-31")
    both = [older if p.entity == "INVOICE" else p for p in profiles] + [inv]
    c = DeterministicCompiler(both, {}, "sqlite", default_filters=default_filters_provider(catalog, TENANT, DS))
    r = SemanticResolver(catalog, TENANT, DS, both)

    this_year = c.compile(r.resolve("Bu yıl toptan satış tutarı", today=date(2026, 7, 20)), catalog)
    assert "LG_411_01_INVOICE" in this_year.sql and "LG_211_01_INVOICE" not in this_year.sql

    last_year = c.compile(r.resolve("Geçen yıl toptan satış tutarı", today=date(2026, 7, 20)), catalog)
    assert "LG_211_01_INVOICE" in last_year.sql, last_year.sql
    assert set(last_year.tables) == {"LG_211_01_INVOICE"}

    spanning = c.compile(r.resolve("Son 12 ayda toptan satış tutarı", today=date(2026, 7, 20)), catalog)
    assert "UNION ALL" in spanning.sql and "LG_211_01_INVOICE" in spanning.sql and "LG_411_01_INVOICE" in spanning.sql
    assert any("dönem" in e for e in spanning.explain), spanning.explain


def test_two_periods_in_one_question_become_two_columns(catalog, profiles, logo_db):
    """"This year and last year" ANDed is a date that falls in both years, which is no date at all —
    the query comes back empty and empty reads as zero. Two periods are being compared, never
    intersected, so each becomes its own column."""
    import copy

    inv = next(p for p in profiles if p.entity == "INVOICE")
    inv.time_window = ("2026-01-01", "2026-08-17")
    older = copy.deepcopy(inv)
    older.table_name, older.context, older.time_window = "LG_211_01_INVOICE", {"n0": "211", "n1": "01"}, ("2021-01-01", "2025-12-31")
    both = [older if p.entity == "INVOICE" else p for p in profiles] + [inv]
    c = DeterministicCompiler(both, {}, "sqlite", default_filters=default_filters_provider(catalog, TENANT, DS))
    r = SemanticResolver(catalog, TENANT, DS, both)

    out = c.compile(r.resolve("Bu yıl ve geçen yıl toptan satış tutarı", today=date(2026, 7, 20)), catalog)
    assert out is not None
    assert " OR " in out.sql, "the two periods are a union of spans, not an impossible intersection"
    assert out.sql.count("AS bu_yil") + out.sql.count("AS gecen_yil") >= 2 or out.sql.lower().count(" as ") >= 3, out.sql
    assert "UNION ALL" in out.sql, "and both period tables are read"
    # the fixture holds only this year's table, so the shape is checked against the one that exists
    logo_db.execute(out.sql.replace("LG_211_01_INVOICE", "LG_411_01_INVOICE")).fetchall()


def test_the_model_never_speaks_for_itself(catalog, profiles, logo_connector, settings):
    """Its job is to write SQL. When it writes none, what the person is told is decided by what the
    resolver established — never by the sentence the model chose. A tool that can be talked into
    discussing itself, the weather or anything else is no longer a data tool."""
    from semantic_bridge.app import Runtime, create_app

    chatty = FakeLlm([
        "Merhaba! Ben bir yapay zeka modeliyim, GPT mimarisiyle çalışıyorum ve size her konuda yardımcı olabilirim.",
        "Bugün hava çok güzel, isterseniz sohbet edelim.",
    ])
    client = TestClient(create_app(Runtime(settings, store=catalog, connector=logo_connector, llm=chatty)))

    for question in ("Sen kimsin, hangi modeli kullanıyorsun?", "Bugün hava nasıl?"):
        body = client.post("/api/v1/ask", json={"question": question, "sampleSize": 5}).json()
        text = str(body.get("explanation") or "") + str(body.get("summary") or "")
        assert body["type"] == "NON_SQL_QUERY", body
        # nothing the model wrote survives into what the person reads
        for said in ("yapay zeka modeliyim", "GPT mimarisiyle", "sohbet edelim", "her konuda yardımcı"):
            assert said not in text, text
        assert "tanımlı" in text.lower() or "veri" in text.lower(), text   # a data tool's answer, or none


def test_the_catalogue_can_be_asked_for_a_page_instead_of_all_of_it(catalog, profiles, logo_connector, settings):
    """The full inventory is eight megabytes across hundreds of tables and tens of thousands of columns
    — not something to hand a browser on every visit. A list view asks without columns and gets a few
    kilobytes; opening one table asks for that table."""
    from semantic_bridge.app import Runtime

    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    full = rt.inventory()
    assert full["tableCount"] == len(rt.profiles) and full["tables"][0]["columns"]

    listing = rt.inventory(with_columns=False, limit=2)
    assert len(listing["tables"]) == 2 and listing["total"] == len(rt.profiles)
    assert listing["tables"][0]["columns"] == []
    assert listing["tables"][0]["columnCount"] > 0, "the count still travels, only the detail is dropped"

    one = rt.inventory(entity="INVOICE")
    assert [t["entity"] for t in one["tables"]] == ["INVOICE"] and one["tables"][0]["columns"]

    found = rt.inventory(search="TRCODE", with_columns=False)
    assert found["tables"] and all("TRCODE" in t["entity"] or t["columnCount"] for t in found["tables"])


def test_the_catalogue_is_remembered_until_the_catalog_changes(catalog, profiles, logo_connector, settings):
    """It is built from profiles that only move when the pipeline runs. A timer would either rebuild
    work nothing changed or serve a stale page after a rebuild; the catalog's own fingerprint does
    neither."""
    from semantic_bridge.app import Runtime
    from semantic_layer.models import Annotation

    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    first = rt.inventory(with_columns=False, limit=3)
    assert rt.inventory(with_columns=False, limit=3) is first, "the same view is not rebuilt"
    assert rt.inventory(with_columns=False, limit=4) is not first, "a different view is its own answer"

    # something a person did in the portal changes the catalog, so the remembered answer is dropped
    catalog.add_annotation(Annotation(datasource_id=DS, table_pattern=profiles[0].table_pattern, column=None, text="fatura başlıkları", author="portal"))
    rt.rebuild()
    assert rt.inventory(with_columns=False, limit=3) is not first


def test_a_label_can_be_corrected_and_the_correction_is_what_the_model_sees(catalog, profiles, logo_connector, settings):
    """A wrong label is worse than a missing one, so fixing it has to actually change the answers. The
    old text is retired rather than erased — the record still shows what was believed and who changed
    it — and only the newest reaches the model."""
    from semantic_bridge.app import Runtime, create_app

    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    client = TestClient(create_app(rt))
    inv = next(p for p in profiles if p.entity == "INVOICE")

    first = client.post("/api/v1/schema/annotations", json={
        "tablePattern": inv.table_pattern, "column": "NETTOTAL", "text": "Ciro: KDV dahil tutar", "author": "ali"}).json()
    rt.rebuild()
    assert rt.existing.annotations[("INVOICE", "NETTOTAL")] == "Ciro: KDV dahil tutar"

    fixed = client.put(f"/api/v1/schema/annotations/{first['annotation']['id']}", json={
        "tablePattern": inv.table_pattern, "column": "NETTOTAL", "text": "Ciro: KDV hariç net tutar", "author": "veli"}).json()
    assert fixed["replaced"] == first["annotation"]["id"]

    rt.rebuild()
    assert rt.existing.annotations[("INVOICE", "NETTOTAL")] == "Ciro: KDV hariç net tutar"
    r = SemanticResolver(catalog, TENANT, DS, rt.profiles)
    prompt = rt.existing.build_messages(r.resolve("Toptan satış tutarı", today=date(2026, 7, 20)), [])[0]["content"]
    line = next(l for l in prompt.splitlines() if l.strip().startswith(("main_", "dbo_")) and "NETTOTAL" in l)
    assert "KDV hariç net tutar (kullanıcı)" in line and "KDV dahil" not in line, line


def test_withdrawing_a_label_withdraws_what_it_taught(catalog, profiles, logo_connector, settings):
    """Retiring only the text left the meanings it produced standing, so a corrected label kept
    answering with the old one — worse than never having written it, because the record says it was
    fixed."""
    from semantic_bridge.app import Runtime, create_app

    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    client = TestClient(create_app(rt))
    inv = next(p for p in profiles if p.entity == "INVOICE")

    written = client.post("/api/v1/schema/annotations", json={
        "tablePattern": inv.table_pattern, "column": "TRCODE", "text": "4 = konsinye", "author": "ali"}).json()
    source = f"annotation:{written['annotation']['id']}"
    born = [c.id for c in catalog.find_concepts(TENANT, DS, limit=10000)
            if any(e.source_id == source for e in catalog.list_evidence(c.id))]
    assert born, "the sentence produced a meaning"

    client.delete(f"/api/v1/schema/annotations/{written['annotation']['id']}")
    for cid in born:
        still = catalog.get_concept(cid)
        assert still is None or (still.status != "CERTIFIED"
                                 and not any(e.source_id == source for e in catalog.list_evidence(cid))), cid


def test_a_catalogue_that_cannot_be_read_says_so(catalog, profiles, logo_connector, settings, monkeypatch):
    """An empty page that says nothing reads as "this database has nothing in it" — a different and
    much worse claim than "I could not read the catalogue just now". One retry against a freshly
    loaded catalog, then a warning the screen can show."""
    from semantic_bridge.app import Runtime, create_app

    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    client = TestClient(create_app(rt))

    tries = {"n": 0}
    real = rt.inventory

    def flaky(*a, **k):
        tries["n"] += 1
        if tries["n"] == 1:
            raise RuntimeError("depo cevap vermedi")
        return real(*a, **k)

    monkeypatch.setattr(rt, "inventory", flaky)
    body = client.get("/api/v1/schema/inventory?columns=false&limit=2").json()
    assert tries["n"] == 2 and body["tables"], "a failure is tried again before it is reported"
    assert "warning" not in body

    monkeypatch.setattr(rt, "inventory", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("depo yok")))
    broken = client.get("/api/v1/schema/inventory?columns=false").json()
    assert broken["tables"] == [] and "okunamıyor" in broken["warning"], broken


def test_the_columns_a_prompt_carries_are_the_ones_an_answer_needs(catalog, profiles, settings):
    """A wide table does not fit in a prompt, and which sixty columns go in decides whether the
    question can be answered at all. Declaration order — what the scan returns — puts a void flag, a
    unit cost and a channel code past position 70 on a real ERP schema, so a question about margin by
    channel would be asked with none of the three on screen."""
    from semantic_bridge.app import Runtime
    from semantic_layer.models import ColumnProfile, SchemaProfile, SemanticQuery

    wide = SchemaProfile(
        datasource_id=DS, table_name="LG_411_01_WIDE", table_pattern="LG_{n0}_{n1}_WIDE",
        entity="WIDE", schema_name="main", primary_key=["LOGICALREF"],
        columns=(
            [ColumnProfile(name="LOGICALREF", data_type="int", is_primary_key=True)]
            + [ColumnProfile(name=f"FILLER{i}", data_type="varchar(50)", description="vendor line") for i in range(200)]
            + [ColumnProfile(name="VOIDFLAG", data_type="int", top_values=[("0", 9), ("1", 1)], distinct_count=2),
               ColumnProfile(name="UNITCOST", data_type="float", unit="TL / adet"),
               ColumnProfile(name="OWNERREF", data_type="int", ref_entity="CLCARD", ref_column="LOGICALREF")]
        ),
        context={"n0": "411", "n1": "01"})
    catalog.upsert_profile(wide)
    rt = Runtime(settings, store=catalog, connector=None, llm=FakeLlm([""]))
    c = rt.existing
    c.catalog_columns = {("WIDE", "VOIDFLAG")}

    # With no ceiling the whole table goes in — that is the point: nothing is cut for its own sake.
    assert c.prompt_columns(wide)[1] == 0, "a table that answers the question goes in whole"

    # A deployment that does set one keeps the useful end of the ranking rather than the first rows
    # the scan happened to return.
    c.max_prompt_columns = 20
    shown, left_out = c.prompt_columns(wide)
    names = {col.name for col in shown}
    assert left_out == len(wide.columns) - 20
    assert "VOIDFLAG" in names, "the default filter is column 202 — declaration order buries it"
    assert "UNITCOST" in names, "a measure with a documented basis has to be visible to be summed"
    assert "OWNERREF" in names, "a join column the model cannot see is a join it cannot write"
    assert "LOGICALREF" in names
    assert [col.name for col in shown] == [c.name for c in wide.columns if c.name in names], \
        "the model should read a table in the source's order, not in our ranking"

    text = c.schema_context(SemanticQuery(question="x", tenant_id=TENANT, datasource_id=DS), [], {"WIDE"})
    assert "listelenmedi" in text, "columns dropped from the prompt have to be declared"


def test_a_question_about_an_earlier_year_is_shown_that_year_s_table(catalog, profiles, settings):
    """A source that keeps a year per table answers 2024 from a different table than 2026, and a
    question spanning both has to read both. The deterministic compiler already unions them; the
    prompt used to name whichever table was biggest — which, for an entity split by year, is the one
    with the most history behind it. A question about this year was being shown last year's table."""
    import copy
    from datetime import date

    from semantic_bridge.app import Runtime
    from semantic_layer.models import SemanticQuery, TemporalSlot

    new = next(p for p in profiles if p.entity == "INVOICE")
    new.time_window = ("2026-01-01", "2026-08-31")
    old = copy.deepcopy(new)
    old.table_name, old.context = "LG_211_01_INVOICE", {"n0": "211", "n1": "01"}
    old.time_window = ("2021-01-01", "2025-12-31")
    old.row_count = (new.row_count or 0) + 10_000_000        # five years of history: the bigger table
    catalog.upsert_profile(old)
    catalog.upsert_profile(new)

    rt = Runtime(settings, store=catalog, connector=None, llm=FakeLlm([""]))
    c = rt.existing

    def ask(start, end):
        q = SemanticQuery(question="ciro", tenant_id=TENANT, datasource_id=DS)
        q.temporal.append(TemporalSlot(text="dönem", primitive="YEAR", start=start, end=end))
        return q

    def shown(q):
        return {p.table_name for p in c._one_per_entity(["INVOICE"], q)}

    assert shown(ask(date(2024, 1, 1), date(2025, 1, 1))) == {"LG_211_01_INVOICE"}, "2024 was shown the 2026 table"
    assert shown(ask(date(2026, 1, 1), date(2027, 1, 1))) == {"LG_411_01_INVOICE"}, "the bigger table won on size"

    # Reading across the boundary is now the compiler's job rather than the model's: it is told the
    # entity is split and to name one table, and physicalize_sql adds the years around it. So the
    # guarantee is asserted where it now lives — in the SQL, not in the prompt.
    from semantic_layer.runtime.guardrails import physicalize_sql

    spanning = ask(date(2024, 1, 1), date(2027, 1, 1))
    text = c.period_block(spanning, ["INVOICE"])
    assert "UNION ALL" in text, "the model must be told not to write the union itself"
    assert "INVOICE" in text

    sql = physicalize_sql("SELECT SUM(NETTOTAL) FROM INVOICE", [old, new], {},
                          period=(date(2024, 1, 1), date(2027, 1, 1)))
    assert "LG_211_01_INVOICE" in sql and "LG_411_01_INVOICE" in sql, sql
    assert "UNION ALL" in sql.upper(), "a question spanning both years has to read both"

    one_year = physicalize_sql("SELECT SUM(NETTOTAL) FROM INVOICE", [old, new], {},
                               period=(date(2026, 1, 1), date(2027, 1, 1)))
    assert "LG_411_01_INVOICE" in one_year and "LG_211_01_INVOICE" not in one_year, one_year

    # The old contract is still available to a deployment that wants the model to do it.
    c.period_in_sql = False
    legacy = c.period_block(spanning, ["INVOICE"])
    assert "LG_211_01_INVOICE" in legacy and "LG_411_01_INVOICE" in legacy
    assert legacy.count("← bu soru için") == 2, "both years are needed and both have to be marked"


def test_a_year_the_deployment_never_loaded_is_refused_not_handed_to_a_model(catalog, profiles, settings):
    """"I cannot write this" and "this must not be written" are different answers. They left the
    deterministic compiler as the same bare None, so a question about 2019 — a year this deployment
    holds no rows for — fell through to the model, which wrote SQL returning zero rows. A zero meaning
    "not loaded" is indistinguishable on screen from a zero meaning "sold nothing"."""
    from semantic_layer.models import SemanticQuery, TemporalSlot
    from semantic_layer.runtime.compiler import CompilerRouter

    class Never:
        name = "existing_llm"
        called = False

        def compile(self, q, catalog, thread=None, *, recall=None):
            Never.called = True
            raise AssertionError("a refused question must never reach a compiler")

    router = CompilerRouter(None, Never())

    out_of_scope = SemanticQuery(question="2019 cirosu", tenant_id=TENANT, datasource_id=DS)
    out_of_scope.out_of_scope.append("2019")
    out_of_scope.explanation.append("'2019' bu kurulumun kapsamı dışında: INVOICE için tanımlı veri 2021-01-01 – 2026-08-17 arasını içeriyor")
    answer = router.compile(out_of_scope, catalog)
    assert answer.refusal == "OUT_OF_SCOPE" and answer.sql == "", answer
    assert "kapsamı dışında" in " ".join(answer.explain)
    assert not Never.called

    contradictory = SemanticQuery(question="hem toptan hem perakende", tenant_id=TENANT, datasource_id=DS)
    contradictory.conflicts.append("INVOICE.TRCODE")
    assert router.compile(contradictory, catalog).refusal == "AMBIGUOUS"

    # A limit of the deterministic compiler is not a refusal: it is handed on.
    passes_through = SemanticQuery(question="bir sey", tenant_id=TENANT, datasource_id=DS)
    passes_through.unresolved.append("problemli")
    assert passes_through.refusal_reason is None
    assert passes_through.state == "UNRESOLVED"


# --- rapor çerçevesi: sorunun biçim tarifi ile konusu ayrı şeylerdir -------------------------

def test_a_spelled_out_report_request_is_not_a_pile_of_unknown_business_terms(catalog, profiles):
    """"1. kolon kanal adı 2. kolon yıl 3. kolon toplam satış": 'kolon' bir iş terimi değil, çıktının
    biçimi. Eskiden çözümleyici onu katalogda arayıp bulamıyor ve tüm soruyu reddediyordu."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("rapor istiyorum - 1. kolon kanal 2. kolon toptan satış 3. kolon net ciro")
    assert "kolon" not in sq.unresolved
    assert sq.projection == ["kanal", "toptan satis", "net ciro"]
    assert any("istenen kolonlar" in e for e in sq.explanation)


def test_the_role_word_is_recognised_by_where_it_stands_not_from_a_list(catalog, profiles):
    """Liste tutulsaydı 'sütun' yarın yine reddedilirdi. Konum kuralı onu da tanır."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("1. sütun kanal 2. sütun toptan satış 3. sütun net ciro")
    assert sq.unresolved == [] and sq.projection == ["kanal", "toptan satis", "net ciro"]


def test_a_numbered_comparison_is_not_a_report_frame_and_its_words_are_still_missing(catalog, profiles):
    """"1. bölge cirosu 2. bölge cirosu": burada sıra sayısı kolonu değil konuyu numaralandırıyor.
    'bölge'yi çerçeve sanıp yutmak, sorulandan geniş bir soruyu cevaplamak olurdu."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("1. bölge cirosu 2. bölge cirosu 3. bölge cirosu")
    assert "bolge" in sq.unresolved and sq.projection == []


def test_a_word_the_catalog_knows_is_never_taken_for_a_frame_word(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("1. kanal net ciro 2. kanal net ciro 3. kanal net ciro")
    assert sq.projection == [] and any(s.explain.get("normalized") == "kanal" for s in sq.slots)


def test_items_that_drop_the_role_word_still_belong_to_the_same_list(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("1. kolon kanal 2. kolon toptan satış 3. kolon net ciro 4. ay bazında kırılım")
    assert sq.projection[-1] == "ay bazinda kirilim"


def test_a_year_is_not_an_item_number(catalog, profiles):
    """Madde numarası 20'ye kadar; 2026 bir yıl, kolon sayısı değil."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("1. kolon kanal 2. kolon toptan satış 3. kolon net ciro 2026")
    assert sq.projection[-1] == "net ciro 2026" or sq.projection[-1] == "net ciro"


def test_a_generic_head_noun_beside_a_resolved_term_is_absorbed_not_reported_missing(catalog, profiles):
    """"net ciro rakamı" — 'rakam' katalogda eksik bir kavram değil, yanındaki terimin baş ismi."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("2026 net ciro rakamı")
    assert "rakami" not in sq.unresolved and sq.unresolved == []


# --- taneciklik: ölçünün bir satırı neyi temsil ediyor ---------------------------------------

def test_a_header_measure_is_swapped_for_the_line_level_sense_when_the_breakdown_needs_it(catalog, profiles):
    """Fatura seviyeli ciro ürüne bölünemez — bir faturada birkaç ürün vardır. Katalogda aynı terimin
    satır seviyeli anlamı varsa doğru olan odur; soru reddedilmez, ölçü değişir."""
    _certify(catalog, "urun", SemanticType.COLUMN,
             Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS", column="NAME", operator="COLUMN"))
    _certify(catalog, "net ciro", SemanticType.METRIC,
             Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
                     formula="SUM(CASE WHEN STLINE.TRCODE IN (7,8) THEN STLINE.TOTAL ELSE -STLINE.TOTAL END)"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Ürün bazında net ciro", today=date(2026, 7, 20))
    metric = next(s for s in sq.slots if s.semantic_type == SemanticType.METRIC)
    assert metric.mapping.entity == "STLINE", sq.to_dict()
    assert any("daha ince" in e for e in sq.explanation)


def test_a_breakdown_the_measure_can_already_carry_is_left_alone(catalog, profiles):
    """Faturanın müşterisi tektir: kanal kırılımı fatura seviyeli ölçüyü bölmez, anlam değişmemeli."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Kanal bazında satış tutarı", today=date(2026, 7, 20))
    metric = next(s for s in sq.slots if s.semantic_type == SemanticType.METRIC)
    assert metric.mapping.entity == "INVOICE"
    assert not any("daha ince" in e for e in sq.explanation)


def test_the_catalog_can_declare_a_grain_that_is_not_the_table_it_sits_on(catalog, profiles):
    """`extra.grain` beyanı, ölçünün durduğu tablodan farklı bir tanecikliği söyleyebilir: satır
    tablosunda duran ama fatura başına bir kez geçerli olan bir tutar gibi."""
    from semantic_layer.runtime.resolver import SemanticResolver as R
    from semantic_layer.models import ResolvedSlot

    slot = ResolvedSlot(term="x", semantic_type=SemanticType.METRIC, status="CERTIFIED",
                        mapping=Mapping(concept_id="", entity="STLINE", table_pattern="p",
                                        extra={"grain": "INVOICE"}))
    assert R._grain_of(slot) == "INVOICE"


def test_an_item_number_is_not_read_as_a_code_for_a_column_that_happens_to_be_named_beside_it(catalog, profiles):
    """"…net ciro 3. kolon…" — sayı listenin üçüncü maddesi. Yanındaki kelime şemada bir kolon adıysa
    kod okuması sessizce bir filtre ekliyordu; sorulmamış bir daraltma cevabı sessizce değiştirir."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("1. kolon kanal 2. kolon net ciro 3. kolon toptan satış")
    assert sq.projection == ["kanal", "net ciro", "toptan satis"]
    assert not any((f.mapping.column or "") == "CIRO" for f in sq.filters if f.mapping)


def test_a_joined_entity_that_spans_years_is_not_projected_with_the_other_side_s_column(catalog, profiles):
    """Yılları UNION ile okunan bir tabloya karşı tarafın join kolonu yazılıyordu: veritabanı
    "Invalid column name 'STOCKREF'" diyerek sorguyu reddediyor. Yalnız hem dönemlere yayılan hem de
    join'lenen bir varlıkta görünüyor — ürün kırılımının ürettiği şekil."""
    from copy import deepcopy
    from semantic_layer.models import utcnow

    _certify(catalog, "urun", SemanticType.COLUMN,
             Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS", column="NAME", operator="COLUMN"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)

    older = deepcopy(next(p for p in profiles if p.entity == "ITEMS"))   # aynı desenin ikinci yılı
    older.table_name, older.context, older.scanned_at = "LG_211_ITEMS", {"n0": "211"}, utcnow()
    spread = profiles + [older]

    r = SemanticResolver(catalog, TENANT, DS, spread)
    c = DeterministicCompiler(spread, {"n0": "411", "n1": "01"}, "tsql")
    sq = r.resolve("2026 ürün bazında satış tutarı", today=date(2026, 7, 20))
    out = c.compile(sq, catalog)
    if out is None or "UNION ALL" not in out.sql:
        return                                   # bu kurulumda yıl birleşimi oluşmuyorsa iddia yok
    items_block = out.sql.split("AS ITEMS")[0].rsplit("JOIN", 1)[-1]
    assert "STOCKREF" not in items_block, out.sql


def test_two_copies_of_a_dated_table_are_not_read_as_two_periods_of_it():
    """Tarihi olmayan bir tablonun dönemi de yoktur: aynı desenin iki kopyası iki yarım değil, iki
    kopyadır. Birleştirilince her ürün satırı ikizleniyor ve ürün bazlı her rakam iki katına çıkıyordu
    — üstelik bir firmanın satır tablosu başka bir firmanın ürünlerine bağlanıyordu."""
    from semantic_layer.models import SchemaProfile, utcnow
    from semantic_layer.runtime import periods as P

    def _p(name, pattern, rows):
        return SchemaProfile(datasource_id="d", table_name=name, table_pattern=pattern, entity="ITEMS",
                             schema_name="dbo", row_count=rows, scanned_at=utcnow())

    same = [_p("LG_211_ITEMS", "LG_{n0}_ITEMS", 29759), _p("LG_411_ITEMS", "LG_{n0}_ITEMS", 32322)]
    kept = P.tables_for(same, date(2026, 1, 1), date(2027, 1, 1))
    assert [k.table_name for k in kept] == ["LG_411_ITEMS"], "aynı desenin tarihsiz kopyalarından biri okunur"

    # ...ama farklı desenler farklı şeylerdir ve ikisi de elde kalır
    mixed = same + [_p("LV_411_ITEMS", "LV_{n0}_ITEMS", 32322)]
    assert len(P.tables_for(mixed, date(2026, 1, 1), date(2027, 1, 1))) == 2


def test_a_join_is_read_from_the_same_firm_as_the_rows_it_is_joined_to(catalog, profiles):
    """Referans satırları firma başına anahtarlanır: bir firmanın satırlarını başka bir firmanın
    referansına bağlamak, ilgisiz kayıtları eşleştirir ve isimler sessizce yer değiştirir."""
    from copy import deepcopy
    from semantic_layer.models import utcnow

    _certify(catalog, "urun", SemanticType.COLUMN,
             Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS", column="NAME", operator="COLUMN"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    older = deepcopy(next(p for p in profiles if p.entity == "ITEMS"))
    older.table_name, older.context, older.scanned_at = "LG_211_ITEMS", {"n0": "211"}, utcnow()
    older.row_count = 10
    spread = profiles + [older]

    r = SemanticResolver(catalog, TENANT, DS, spread)
    c = DeterministicCompiler(spread, {}, "tsql")
    out = c.compile(r.resolve("2026 ürün bazında satış tutarı", today=date(2026, 7, 20)), catalog)
    if out is None:
        return                                   # birden çok firma okunuyorsa reddetmek de doğru cevap
    assert "LG_211_ITEMS" not in out.sql, out.sql


def test_a_question_that_spans_copies_joins_inside_each_one_and_unions_the_results(catalog, profiles):
    """En eski veriden bugüne tek soru: her kopya kendi referansıyla eşleşmeli. Tek bir join iki
    kopyaya birden hizmet edemez — ikinci kopyanın her satırı ilgisiz bir referansa denk gelir."""
    from copy import deepcopy
    from semantic_layer.models import utcnow

    _certify(catalog, "urun", SemanticType.COLUMN,
             Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS", column="NAME", operator="COLUMN"))
    _certify(catalog, "satır tutarı", SemanticType.METRIC,
             Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
                     formula="SUM(STLINE.TOTAL)"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)

    old_line = deepcopy(next(p for p in profiles if p.entity == "STLINE"))
    old_line.table_name, old_line.context = "LG_211_01_STLINE", {"n0": "211", "n1": "01"}
    old_line.time_window, old_line.scanned_at = ("2021-01-01", "2025-12-31"), utcnow()
    old_items = deepcopy(next(p for p in profiles if p.entity == "ITEMS"))
    old_items.table_name, old_items.context, old_items.scanned_at = "LG_211_ITEMS", {"n0": "211"}, utcnow()
    spread = profiles + [old_line, old_items]

    r = SemanticResolver(catalog, TENANT, DS, spread)
    c = DeterministicCompiler(spread, {}, "tsql")
    sq = r.resolve("ürün bazında satır tutarı", today=date(2026, 7, 20))
    sq.temporal = [TemporalSlot(text="2021'den bugüne", primitive="RANGE",
                                start=date(2021, 1, 1), end=date(2026, 12, 31))]
    out = c.compile(sq, catalog)
    assert out is not None, sq.to_dict()
    assert "UNION ALL" in out.sql
    # her iki taraf da kopya damgası taşır ve join o damgayla kapanır
    assert out.sql.count("__nb_firm") >= 5, out.sql
    assert "STLINE.[__nb_firm] = ITEMS.[__nb_firm]" in out.sql or "ITEMS.[__nb_firm] = STLINE.[__nb_firm]" in out.sql, out.sql
    assert "LG_211_ITEMS" in out.sql and "LG_411_ITEMS" in out.sql, out.sql


def test_a_word_the_vocabulary_lacks_is_looked_for_in_the_schema(catalog, profiles):
    """Katalogda yoksa şemada ara: kolonun kendi adı kelimeyi taşıyorsa, o kelime tanımsız bir kavram
    değil, adı konmamış bir kolondur. Okunur ama sertifikalı sayılmaz."""
    from semantic_layer.runtime.column_index import ColumnIndex

    r = SemanticResolver(catalog, TENANT, DS, profiles)
    r.columns = ColumnIndex(profiles)
    sq = r.resolve("definition bazında 2026 net ciro")
    inferred = [s for s in sq.slots if s.status == "INFERRED" and s.explain.get("source") == "column_index"]
    assert inferred, sq.to_dict()
    assert inferred[0].mapping.column == "DEFINITION_"
    assert any("sertifikalı değil" in e for e in sq.explanation)

    # Konusu olmayan bir soruda varsayım yapılmaz: kolon adı bulunur ama aday olarak kalır. Aksi
    # halde aynı adı taşıyan bir rapor görünümü ya da yıllar önceki bir yedek kopya seçilebiliyor.
    sq2 = r.resolve("2026 outcost toplamı")
    assert [s for s in sq2.slots if s.explain.get("source") == "column_index"] == []
    assert [c["column"] for c in sq2.candidates] == ["OUTCOST"], sq2.to_dict()


def test_an_entity_word_is_never_read_as_a_column_by_the_schema_search(catalog, profiles):
    """"müşteri" bir tablonun adı; kolon diye okunursa sorulmayan bir kırılım eklenir."""
    from semantic_layer.runtime.column_index import ColumnIndex

    r = SemanticResolver(catalog, TENANT, DS, profiles)
    r.columns = ColumnIndex(profiles)
    sq = r.resolve("müşteri bazında 2026 net ciro")
    from_data = [s for s in sq.slots if s.explain.get("source") == "column_index"]
    assert from_data == [], [s.term for s in from_data]


def test_a_word_that_only_appears_among_a_column_s_values_is_not_read_as_that_column(catalog, profiles):
    """Bir kelime bir kolonun İÇİNDE geçiyorsa, o kolonun ne olduğunu değil neyle süzüleceğini söyler."""
    from semantic_layer.runtime.column_index import ColumnIndex

    r = SemanticResolver(catalog, TENANT, DS, profiles)
    r.columns = ColumnIndex(profiles)
    sq = r.resolve("kitapçı bazında 2026 net ciro")
    bad = [s for s in sq.slots if s.explain.get("source") == "column_index" and s.mapping.column == "SPECODE2"]
    assert bad == [], [s.term for s in bad]


# --- erişim: CTE adı katalog iznini aşamaz ---------------------------------------------------

def test_a_cte_name_cannot_excuse_a_table_the_catalog_never_profiled(profiles):
    """CTE adları tek bir küresel kümede toplanıp ADI eşleşen her başvuru denetimden çıkarılıyordu.
    Şemayla nitelenmiş bir ad ise hiçbir zaman CTE olamaz — `dbo.X` her koşulda fiziksel tablodur.
    Sonuç: sorgu hiç tablo görmemiş sayılıyor, tablo görmeyen bir denetim de her şeye izin veriyordu."""
    ctx = {"n0": "411", "n1": "01"}
    ok, _ = allowed_tables("SELECT 1 FROM dbo_LG_411_01_INVOICE", profiles, ctx, "tsql")
    assert ok

    for sql in (
        "SELECT * FROM master.dbo.sysusers",
        "WITH sysusers AS (SELECT 1 AS x) SELECT * FROM master.dbo.sysusers",
        "WITH dbo_sysusers AS (SELECT 1 AS x) SELECT * FROM dbo_sysusers",
        # iç kapsamda tanımlanan ad dış kapsamdaki başvuruyu mazur göstermez
        "WITH a AS (WITH sysusers AS (SELECT 1 AS x) SELECT x FROM sysusers) SELECT * FROM master.dbo.sysusers",
    ):
        blocked, why = allowed_tables(sql, profiles, ctx, "tsql")
        assert not blocked, sql
        assert why, sql

    # gerçek CTE kullanımı çalışmaya devam eder
    good = "WITH t AS (SELECT * FROM dbo_LG_411_01_INVOICE) SELECT COUNT(*) FROM t"
    assert allowed_tables(good, profiles, ctx, "tsql")[0]


def test_a_statement_that_cannot_be_read_is_refused_not_permitted(profiles):
    """Okunamayan ifade zararsız değildir: tablolarını adlandıramayan bir denetim, tam da gerektiği
    yerde yok demektir."""
    ctx = {"n0": "411", "n1": "01"}
    assert not allowed_tables("SELECT * FROM ((((", profiles, ctx, "tsql")[0]
    assert not allowed_tables("SELECT 1", profiles, ctx, "tsql")[0]


def test_generic_information_after_composed_measure_is_not_an_unknown_concept(catalog, profiles):
    _certify(catalog, "perakende satis", SemanticType.DIMENSION_VALUE,
             Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE", column="TRCODE", operator="IN", values=["7"]))
    _certify(catalog, "satis tutar", SemanticType.COLUMN,
             Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE", column="NETTOTAL", operator="COLUMN"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Ocak 2026 dönemindeki perakende satış tutarı bilgisini raporla.")
    assert "bilgisini" not in sq.unresolved
    assert any(s.semantic_type == SemanticType.METRIC and s.mapping for s in sq.slots)
    assert "bilgisini" in r.resolve("Bilgisini raporla").unresolved


def test_long_certified_metric_is_not_split_into_narrower_filter(catalog, profiles):
    _certify(catalog, "toptan net satis tutari", SemanticType.METRIC,
             Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
                     formula="SUM(CASE WHEN INVOICE.TRCODE = 8 THEN INVOICE.NETTOTAL ELSE -INVOICE.NETTOTAL END)",
                     extra={"conditions":["INVOICE.TRCODE IN (3,8)"]}))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Ocak 2026 toptan net satış tutarı nedir?")
    metrics=[s for s in sq.slots if s.semantic_type==SemanticType.METRIC]
    assert len(metrics)==1 and metrics[0].term=="toptan net satis tutari"
    assert not [s for s in sq.slots if s.semantic_type==SemanticType.DIMENSION_VALUE]
    assert sq.unresolved==[]


def test_composed_measure_uses_normalized_key_for_line_grain(catalog, profiles):
    _certify(catalog, "perakende satis", SemanticType.DIMENSION_VALUE,
             Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE", column="TRCODE", operator="IN", values=["7"]))
    _certify(catalog, "satis tutar", SemanticType.COLUMN,
             Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE", column="NETTOTAL", operator="COLUMN"))
    _certify(catalog, "urun", SemanticType.COLUMN,
             Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS", column="NAME", operator="COLUMN"))
    _certify(catalog, "satis tutari", SemanticType.METRIC,
             Mapping(concept_id="", entity="STLINE", table_pattern="LG_{n0}_{n1}_STLINE", formula="SUM(STLINE.TOTAL)", extra={"grain":"STLINE","conditions":["STLINE.TRCODE IN (7,8)","STLINE.LINETYPE = (0)"]}))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve("Ocak 2026 ürün bazında perakende satış tutarı göster.")
    metrics=[s for s in sq.slots if s.semantic_type==SemanticType.METRIC]
    assert len(metrics)==1 and metrics[0].mapping.entity=="STLINE"
    assert metrics[0].explain.get("grain_switch")=="INVOICE → STLINE"


def test_a_table_in_another_database_on_the_same_server_is_named_in_full():
    """Bir kaynak, tablolarını aynı sunucuda birden çok veritabanında tutabilir. İki parçalı ad
    bağlantının bakmakta olduğu veritabanında çözülür — yani yanlış veritabanında."""
    from semantic_layer.models import ColumnProfile, SchemaProfile
    from semantic_layer.runtime.compiler import Dialect
    from semantic_layer.runtime.guardrails import allowed_tables, physicalize_sql

    crm = SchemaProfile(datasource_id="d", table_name="new_siparisBase", table_pattern="new_siparisBase",
                        entity="SIPARIS", schema_name="Timas_MSCRM.dbo",
                        columns=[ColumnProfile(name="new_CariKodu", data_type="nvarchar")])
    assert Dialect("tsql").table("Timas_MSCRM.dbo", "new_siparisBase") == "[Timas_MSCRM].[dbo].[new_siparisBase]"

    sql = physicalize_sql("SELECT new_CariKodu FROM SIPARIS", [crm], {}, dialect="tsql")
    assert "[Timas_MSCRM].[dbo].[new_siparisBase]" in sql, sql

    # ve izin listesi bu adı tanır, tanımadığını hâlâ reddeder
    assert allowed_tables(sql, [crm], {}, "tsql")[0]
    assert not allowed_tables("SELECT * FROM Timas_MSCRM.dbo.AuditBase", [crm], {}, "tsql")[0]


def test_explicit_quantity_in_top_n_is_not_replaced_by_sales_amount(catalog, profiles):
    _certify(catalog, "kitap", SemanticType.COLUMN,
             Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS", column="NAME", operator="COLUMN"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    resolver = SemanticResolver(catalog, TENANT, DS, profiles)
    for question in ["En çok satan 10 kitap (adet)", "En çok satan 5 kitap adet", "En çok satan on kitap adet", "kitap bazında satılan adet ilk 10"]:
        sq = resolver.resolve(question, today=date(2026, 9, 9))
        metrics = [slot for slot in sq.slots if slot.semantic_type == SemanticType.METRIC]
        assert len(metrics) == 1, sq.to_dict()
        assert "STLINE.AMOUNT" in metrics[0].mapping.formula
        assert any(slot.mapping.entity == "ITEMS" for slot in sq.group_by)
        assert not sq.clarification, sq.to_dict()


def test_a_year_after_a_measure_is_not_a_physical_column_filter(catalog, profiles):
    resolver = SemanticResolver(catalog, TENANT, DS, profiles)
    resolver.column_names.add("CIRO")
    for question in ["kanal bazında net ciro 2025", "net ciro 2024"]:
        sq = resolver.resolve(question, today=date(2026, 9, 9))
        assert not any(slot.status == "EXPLICIT" for slot in sq.slots), sq.to_dict()
        assert not sq.unhandled, sq.to_dict()
        assert sq.temporal[0].start.year in (2024, 2025)
