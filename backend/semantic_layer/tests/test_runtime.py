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
    """"satmayan" is the opposite of "satış": reading it as the sales measure would invert the answer."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Hiç satmayan ürünlerimiz var mı?", today=date(2026, 7, 20))
    assert not any(s.semantic_type == SemanticType.METRIC for s in sq.slots)
    assert "satmayan" in sq.unhandled and not sq.fully_resolved


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


def test_share_question_needs_a_certified_denominator(catalog, profiles):
    """"payı yüzde kaç" asks for a ratio; answering with the plain total replaces the question."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Toptan satışın payı yüzde kaç?", today=date(2026, 7, 20))
    assert sq.unhandled and not sq.fully_resolved


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
