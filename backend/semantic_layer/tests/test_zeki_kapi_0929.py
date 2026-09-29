"""Tam kapı 2026-09-29 (69 soru × 3): bozuk/kararsız soruların SINIF düzeltmeleri.

Her test bir hata sınıfını sınar, soruyu değil (docs/analiz/zeki-kapi-2026-09-29.md):
  K1 eleştirmen yanlış tabloyu okuyor — yıl kopyası kalıbıyla değil varlık adıyla bağlanınca «kolon yok» (B019)
  K2 köprü tablosu (barkod) yalnız kırılım anahtarıyken «şişirilmiş» ret (A023)
  K3 tek parçalık plan: iki yarısını hiçbir ölçülmüş bağ birleştirmeyen soruda tek kaynaklı okuma (D053)
  K4 portal anahtar kelimesi sertifikalı Logo öbeğinin içinde (A016)
  K5 kaydın adıyla kırılımda aynı adlı iki kart tek satır (C015)
  K6 kırılım sözcüğü («X bazında») profil değeri süzgecine dönüşüyor (A044)
  K7 ayrık yazılmış ölçü adı («etkinliklere … toplam gider») genel ölçüye bağlanıyor (B064)

Veriler yapaydır; gerçek veri ve gerçek modelle ölçüm test sunucusunda (answer-gate / resolver-gate).
"""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import ColumnProfile, Mapping, ResolvedSlot, SchemaProfile, SemanticQuery, SemanticType
from semantic_layer.runtime import federated as F
from semantic_layer.runtime.compiler import CompilerRouter, DeterministicCompiler
from semantic_layer.runtime.critic import review
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 29)


def _t(entity, name, cols, *, pattern=None, pk="LOGICALREF", rows=None, schema="dbo", rels=()):
    return SchemaProfile(datasource_id="d", table_name=name, table_pattern=pattern or name, entity=entity, schema_name=schema,
                         columns=[ColumnProfile(name=n, data_type=dt, is_primary_key=(n == pk)) for n, dt in cols],
                         primary_key=[pk] if pk else [], row_count=rows, relationships=list(rels))


# ---------------------------------------------------------------- K1: yıl kopyası kalıbıyla bağlanır

CLFLINE_LG = _t("LG_CLFLINE", "LG_411_01_CLFLINE", [("LOGICALREF", "int"), ("CLIENTREF", "int"), ("AMOUNT", "float"),
                                                    ("SIGN", "smallint"), ("CANCELLED", "smallint")],
                pattern="LG_{firm}_{period}_CLFLINE")
CLFLINE_VIEW = _t("CLFLINE", "CLFLINE", [("LOGICALREF", "int"), ("CODE", "nvarchar(25)")])


def test_a_year_copy_is_read_through_its_pattern_not_through_a_colliding_entity_name():
    """B019: the model wrote LG_211_01_CLFLINE; the catalog holds LG_{firm}_{period}_CLFLINE (entity LG_CLFLINE) and an
    unrelated table whose entity is plain CLFLINE. Resolved by entity name, the unrelated table was read and AMOUNT,
    SIGN and CANCELLED were reported missing — three false refusals of a column Logo has."""
    sql = "SELECT SUM(c.AMOUNT) FROM LG_211_01_CLFLINE c WHERE c.SIGN = 1 AND c.CANCELLED = 0"
    assert not [f for f in review(sql, [CLFLINE_VIEW, CLFLINE_LG]) if f.kind == "UNKNOWN_COLUMN"]


def test_a_column_missing_from_a_guessed_table_is_a_warning_not_a_refusal():
    """Only the entity-name guess reached a profile: the database has the last word, the reviewer does not refuse."""
    f = [x for x in review("SELECT SUM(c.AMOUNT) FROM LG_211_01_CLFLINE c", [CLFLINE_VIEW]) if x.kind == "UNKNOWN_COLUMN"]
    assert f and all(x.severity == "warn" for x in f), f


def test_a_column_missing_from_the_named_table_is_still_refused():
    f = review("SELECT SUM(c.NETTOTAL) FROM LG_411_01_CLFLINE c", [CLFLINE_LG])
    assert any(x.kind == "UNKNOWN_COLUMN" and x.severity == "block" for x in f), f


# ---------------------------------------------------------------- K2: köprü tablosu kırılım anahtarıyken

def _chasm_world(barcode_rows):
    items = _t("ITEMS", "LG_411_ITEMS", [("LOGICALREF", "int"), ("CODE", "nvarchar(25)")], rows=100)
    lines = _t("STLINE", "LG_411_01_STLINE", [("LOGICALREF", "int"), ("STOCKREF", "int"), ("LINENET", "float"), ("DATE_", "datetime")],
               rows=10_000, rels=[{"column": "STOCKREF", "ref_entity": "ITEMS", "ref_column": "LOGICALREF"}])
    codes = _t("UNITBARCODE", "LG_411_UNITBARCODE", [("LOGICALREF", "int"), ("ITEMREF", "int"), ("BARCODE", "nvarchar(50)")],
               rows=barcode_rows, rels=[{"column": "ITEMREF", "ref_entity": "ITEMS", "ref_column": "LOGICALREF"}])
    return [items, lines, codes]


_BY_BARCODE = ("SELECT LTRIM(RTRIM(CAST(ub.BARCODE AS NVARCHAR(100)))) AS barkod, SUM(s.LINENET) AS ciro "
               "FROM LG_411_01_STLINE s JOIN LG_411_ITEMS i ON i.LOGICALREF = s.STOCKREF "
               "JOIN LG_411_UNITBARCODE ub ON ub.ITEMREF = i.LOGICALREF "
               "GROUP BY LTRIM(RTRIM(CAST(ub.BARCODE AS NVARCHAR(100))))")


def test_a_small_bridge_table_used_only_as_the_breakdown_key_does_not_multiply_the_sum():
    """A023: sales lines ← item → barcodes, grouped by barcode. Each group is one barcode row; a sales line is counted
    once in it. Said as a warning (a duplicated value on one item would repeat), not refused."""
    f = [x for x in review(_BY_BARCODE, _chasm_world(150)) if x.kind == "FANOUT"]
    assert f and all(x.severity == "warn" for x in f), f


def test_the_same_join_grouped_by_the_item_still_multiplies_and_is_refused():
    sql = _BY_BARCODE.replace("LTRIM(RTRIM(CAST(ub.BARCODE AS NVARCHAR(100))))", "i.CODE")
    assert any(x.kind == "FANOUT" and x.severity == "block" and "ikinci bir" in x.message for x in review(sql, _chasm_world(150)))


def test_a_movement_table_is_no_bridge_even_when_grouped_by():
    """Many rows per item (a movement table, not a lookup): grouping by its column still repeats the other side."""
    assert any(x.kind == "FANOUT" and x.severity == "block" for x in review(_BY_BARCODE, _chasm_world(5_000)))


# ---------------------------------------------------------------- K3: tek parçalık plan

def _crm_royalty():
    return SchemaProfile(datasource_id="d", table_name="new_teliftanimBase", table_pattern="new_teliftanimBase",
                         entity="NEW_TELIFTANIMBASE", schema_name="Timas_MSCRM.dbo", row_count=42,
                         columns=[ColumnProfile(name="new_BalangicAdeti", data_type="int"),
                                  ColumnProfile(name="new_TelifYuzdesi", data_type="decimal(18,2)")])


def _profiles_with_link():
    from semantic_layer.tests.test_federated import invoices, shipments
    return [shipments(), invoices(), _crm_royalty()]


_ONE_PART = {"parts": [{"name": "telif", "source": "TIMAS_MSCRM",
                        "sql": "SELECT new_BalangicAdeti AS baslangic, AVG(CAST(new_TelifYuzdesi AS FLOAT)) AS ort "
                               "FROM Timas_MSCRM_dbo_new_teliftanimBase GROUP BY new_BalangicAdeti"}],
             "links": [], "final": "SELECT * FROM telif"}


def _plan(d):
    import json
    return F.parse_plan("```json\n" + json.dumps(d) + "\n```")


def test_a_one_part_plan_is_accepted_when_nothing_joins_the_questions_two_halves():
    """D053: the words landed on a Logo measure and a CRM royalty table that no measured link connects. No two-server
    answer exists; the model's one-server plan is the only reading there is."""
    assert F.check_plan(_plan(_ONE_PART), _profiles_with_link(), {}, placed={"STLINE", "NEW_TELIFTANIMBASE"}) == []


def test_a_one_part_plan_is_refused_when_a_measured_link_joins_the_placed_tables():
    problems = F.check_plan(_plan(_ONE_PART), _profiles_with_link(), {}, placed={"NEW_SEVKIYATBASE", "INVOICE"})
    assert any("en az iki parça" in p for p in problems), problems


def test_without_the_placed_tables_the_old_rule_stands():
    assert any("en az iki parça" in p for p in F.check_plan(_plan(_ONE_PART), _profiles_with_link(), {}))


def test_an_unasked_default_year_on_the_server_the_plan_does_not_read_is_not_an_obligation():
    q = SemanticQuery(question="x", tenant_id="t", datasource_id="d",
                      explanation=["dönem belirtilmedi → varsayılan YEAR uygulandı"],
                      temporal_binding={"entity": "STLINE", "column": "DATE_"})
    router = CompilerRouter(None, None)
    assert router._unread_default_period(q, _plan(_ONE_PART)) == {"STLINE"}
    asked = SemanticQuery(question="x", tenant_id="t", datasource_id="d", temporal_binding={"entity": "STLINE", "column": "DATE_"})
    assert router._unread_default_period(asked, _plan(_ONE_PART)) == set(), "a period the person wrote stays"
    reads = dict(_ONE_PART, parts=[{"name": "satis", "source": "LOGO", "sql": "SELECT SUM(AMOUNT) AS a FROM LG_411_01_STLINE"}],
                 final="SELECT * FROM satis")
    assert router._unread_default_period(q, _plan(reads)) == set()


# ---------------------------------------------------------------- K4: portal kelimesi sertifikalı öbeğin içinde

def test_a_portal_keyword_inside_a_certified_phrase_is_not_portal_evidence():
    """A016: «ortalama sepet tutarı» is a certified Logo measure; «sepet» alone is the e-commerce area's keyword."""
    from semantic_bridge import chat_portal as P
    from semantic_bridge import chat_scope
    question = "Müşteri bazında ortalama sepet tutarı en yüksek ilk on firma hangisi?"
    assert P.mentions_portal(question) is True
    slot = ResolvedSlot(term="ortalama sepet tutari", semantic_type=SemanticType.METRIC, status="CERTIFIED",
                        mapping=Mapping(concept_id="c", entity="INVOICE", table_pattern="p", formula="AVG(INVOICE.NETTOTAL)"))
    covered = chat_scope.strong_phrases([slot])
    assert covered == ["ortalama sepet tutari"]
    assert P.mentions_portal(question, covered=covered) is False
    assert P.mentions_portal("Sitede sepet terk oranı nedir?", covered=covered) is True, "the keyword on its own still counts"


# ---------------------------------------------------------------- K5: kaydın adıyla kırılım

def _named_card_catalog(catalog, profiles, *, record_label):
    _certify(catalog, "müşteri", SemanticType.COLUMN,
             Mapping(concept_id="", entity="CLCARD", table_pattern="LG_{n0}_CLCARD", column="DEFINITION_", operator="COLUMN",
                     extra={"record_label": True} if record_label else {}))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    return SemanticResolver(catalog, TENANT, DS, profiles)


def _group_by(sql: str) -> str:
    up = sql.upper().replace("[", "").replace("]", "").replace('"', "")
    return up.split("GROUP BY", 1)[1].split("ORDER BY", 1)[0] if "GROUP BY" in up else ""


def test_a_breakdown_by_a_records_own_name_keeps_same_named_records_apart(catalog, profiles):
    """C015: two customers with one name were one row. The card key joins the GROUP BY (not the SELECT)."""
    sq = _named_card_catalog(catalog, profiles, record_label=True).resolve("Müşteri bazında satış tutarı", today=TODAY)
    out = DeterministicCompiler(profiles, {}, "tsql").compile(sq, catalog)
    assert out is not None, sq.to_dict()
    grouped = _group_by(out.sql)
    assert "CLCARD.DEFINITION_" in grouped and "CLCARD.LOGICALREF" in grouped, out.sql
    assert "LOGICALREF" not in out.sql.upper().split("FROM", 1)[0], "the key is grouped by, not shown"


def test_a_breakdown_by_an_attribute_is_not_split_per_record(catalog, profiles):
    """«kanal» (SPECODE2) is an attribute of many cards: adding the card key would break the answer into cards."""
    sq = _named_card_catalog(catalog, profiles, record_label=True).resolve("Kanal bazında satış tutarı", today=TODAY)
    out = DeterministicCompiler(profiles, {}, "tsql").compile(sq, catalog)
    assert out is not None and "LOGICALREF" not in _group_by(out.sql), out.sql if out else sq.to_dict()


def test_without_the_catalog_mark_the_name_breakdown_is_unchanged(catalog, profiles):
    sq = _named_card_catalog(catalog, profiles, record_label=False).resolve("Müşteri bazında satış tutarı", today=TODAY)
    out = DeterministicCompiler(profiles, {}, "tsql").compile(sq, catalog)
    assert out is not None and "LOGICALREF" not in _group_by(out.sql), out.sql if out else sq.to_dict()


# ---------------------------------------------------------------- K6: kırılım sözcüğü değer değildir

def _value_filters(sq, value):
    return [s for s in sq.slots if s.semantic_type == SemanticType.DIMENSION_VALUE and s.mapping
            and value in [str(v).upper() for v in (s.mapping.values or [])]]


def _observed_channels(profiles):
    """The fixture's CLCARD has three cards with three different SPECODE2 values; the profiler's sample rule
    (`_enum_candidate`: short values that REPEAT) does not probe such a column, so it carries no observed values and
    step 2b has nothing to match — the control below failed for that, not for K6 (sunucu koşusu 45241e2b). The live
    column is a probed code list (KITAPCI, E-TICARET, DAGITICI …); the test states that observation explicitly."""
    col = next(p for p in profiles if p.entity == "CLCARD").column("SPECODE2")
    col.top_values = [("KITAPCI", 1), ("E-TICARET", 1), ("DAGITICI", 1)]
    col.distinct_count = 3
    return profiles


def test_the_fixture_offers_the_observed_value_to_step_2b(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, _observed_channels(profiles))
    r.resolve("Satış tutarı ne kadar?", today=TODAY)
    assert "dagitici" in r._value_index, sorted(r._value_index)[:20]


def test_a_word_that_opens_a_breakdown_is_not_read_as_an_observed_value(catalog, profiles):
    """A044: «yazar bazında … en pahalı beş yazar» — the word is what the answer is broken down by, at both places."""
    r = SemanticResolver(catalog, TENANT, DS, _observed_channels(profiles))
    sq = r.resolve("Satış tutarı dağıtıcı bazında nasıl dağılıyor, en yüksek iki dağıtıcı kim?", today=TODAY)
    assert not _value_filters(sq, "DAGITICI"), [(s.term, s.semantic_type, s.mapping.values if s.mapping else None) for s in sq.slots]


def test_the_same_word_without_a_breakdown_cue_is_still_a_value(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, _observed_channels(profiles))
    sq = r.resolve("Dağıtıcı müşterilere satış tutarı ne kadar?", today=TODAY)
    assert _value_filters(sq, "DAGITICI"), [(s.term, s.semantic_type) for s in sq.slots]


# ---------------------------------------------------------------- K7: ayrık yazılmış ölçü adı

def _cost_catalog(catalog, profiles):
    inv = next(p for p in profiles if p.entity == "INVOICE")
    stl = next(p for p in profiles if p.entity == "STLINE")
    _certify(catalog, "gider", SemanticType.METRIC, Mapping(concept_id="", entity="INVOICE", table_pattern=inv.table_pattern,
                                                           formula="SUM(INVOICE.TOTALVAT)"))
    _certify(catalog, "kargo gideri", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=stl.table_pattern,
                                                                  formula="SUM(STLINE.OUTCOST)"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    return SemanticResolver(catalog, TENANT, DS, profiles)


def _metric_terms(sq):
    return [(s.explain or {}).get("canonical") for s in sq.slots if s.semantic_type == SemanticType.METRIC]


def test_a_measure_name_split_by_a_relative_clause_is_that_measure(catalog, profiles):
    """B064: «etkinliklere harcadığımız toplam gider» names «etkinlik gideri», not the ledger's generic «gider»."""
    sq = _cost_catalog(catalog, profiles).resolve("Kargoya harcadığımız toplam gider ne kadar?", today=TODAY)
    assert _metric_terms(sq) == ["kargo gideri"], (_metric_terms(sq), sq.explanation)
    named = next(s for s in sq.slots if s.semantic_type == SemanticType.METRIC)
    assert named.status == "INFERRED" and (named.explain or {}).get("source") == "split_measure_name"


def test_the_record_word_may_name_another_table_than_the_measure(catalog, profiles):
    """«Etkinlik» names the CRM event table; what was spent on events is booked in the ledger. The certified name
    «etkinlik gideri» decides — the entity word's table does not."""
    stl = next(p for p in profiles if p.entity == "STLINE")
    _certify(catalog, "etkinlik", SemanticType.ENTITY, Mapping(concept_id="", entity="ITEMS", table_pattern="LG_{n0}_ITEMS"))
    _certify(catalog, "etkinlik gideri", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=stl.table_pattern,
                                                                     formula="SUM(STLINE.OUTCOST)"))
    sq = _cost_catalog(catalog, profiles).resolve("Etkinliklere harcadığımız toplam gider ne kadar?", today=TODAY)
    assert _metric_terms(sq) == ["etkinlik gideri"], (_metric_terms(sq), sq.explanation)
    assert not [s for s in sq.slots if s.semantic_type == SemanticType.ENTITY and s.mapping and s.mapping.entity == "ITEMS"]


def test_the_generic_measure_stays_when_no_certified_name_is_split(catalog, profiles):
    sq = _cost_catalog(catalog, profiles).resolve("Bu yıl toplam gider ne kadar?", today=TODAY)
    assert _metric_terms(sq) == ["gider"], (_metric_terms(sq), sq.explanation)


# ---------------------------------------------------------------- K7b: belgelenmiş yokluk bir itiraf değildir

def _c21_rule() -> str:
    from pathlib import Path
    text = (Path(__file__).resolve().parents[3] / "configs/semantic/knowledge/logo/knowledge/rules/crm-timas.md").read_text(encoding="utf-8")
    return next(line for line in text.splitlines() if line.startswith("- **Etkinlik bütçesi yoktur:**"))


def test_a_gap_the_knowledge_pack_documents_is_explained_by_the_operators_sentence():
    """B064 (altın: answer): the model's reading «bütçe tanımlı değil, karşılaştırma yapılamaz» is what Kural C21
    tells it to say. Matched to that documented absence, it is served with the operator's sentence, not refused."""
    from semantic_layer.runtime.compiler import admitted_gaps, caveat_for
    gap = "'butcenin' → etkinlik bütçesi hiçbir kaynakta tanımlı değil; bütçe karşılaştırması yapılamaz"
    assert admitted_gaps([gap]) == [gap]
    assert "bütçe" in caveat_for(gap, _c21_rule(), absence_only=True).lower()


def test_an_undocumented_gap_is_not_excused_by_an_unrelated_rule():
    from semantic_layer.runtime.compiler import caveat_for
    gap = "'birim' → UNITSETL.NAME (STLINE'da birim kolonu yok, birim kırılımı eklenemedi)"
    assert caveat_for(gap, _c21_rule(), absence_only=True) == ""


# ---------------------------------------------------------------- K7c: hariç grup (yansıtma fişi) koşulu

_NO_DISCOUNTED_INVOICE = {"key": "INVOICEREF", "column": "LINETYPE", "like": ["2%"], "why": "iskonto satırı olan fatura"}


def test_exclude_groups_are_read_only_when_well_formed():
    from semantic_layer.runtime.compiler import exclude_groups
    m = Mapping(concept_id="", entity="EMFLINE", table_pattern="p", formula="SUM(EMFLINE.DEBIT)",
                extra={"exclude_groups": [{"key": "ACCFICHEREF", "column": "ACCOUNTCODE", "like": ["7_1%"]},
                                          {"key": "a b", "column": "X", "like": ["1%"]},
                                          {"key": "K", "column": "Y", "like": ["x' OR 1=1 --"]},
                                          {"key": "K", "column": "Y", "like": []}]})
    assert exclude_groups(m) == [{"key": "ACCFICHEREF", "column": "ACCOUNTCODE", "like": ["7_1%"], "why": ""}]
    assert exclude_groups(None) == []


def _grouped_measure(catalog, profiles, *, excluded, question="Yalın hacim ne kadar?"):
    stl = next(p for p in profiles if p.entity == "STLINE")
    extra = {"conditions": ["STLINE.TRCODE IN (7,8)", "STLINE.LINETYPE IN (0)"]}
    if excluded:
        extra["exclude_groups"] = [dict(_NO_DISCOUNTED_INVOICE)]
    _certify(catalog, "yalın hacim", SemanticType.METRIC,
             Mapping(concept_id="", entity="STLINE", table_pattern=stl.table_pattern, formula="SUM(STLINE.AMOUNT)", extra=extra))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    return SemanticResolver(catalog, TENANT, DS, profiles).resolve(question, today=TODAY)


def _compile_run(catalog, profiles, logo_db, sq):
    from semantic_layer.runtime.compiler import default_filters_provider
    comp = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite",
                                 default_filters=default_filters_provider(catalog, TENANT, DS))
    out = comp.compile(sq, catalog)
    assert out is not None, (comp.plan(sq)[1], sq.to_dict())
    return out, logo_db.execute(out.sql).fetchall()[0][0]


def test_a_measure_excluding_whole_groups_is_compiled_as_an_anti_join_on_the_same_source(catalog, profiles, logo_db):
    """Yansıtma fişi sınıfı: a group (voucher / invoice) is dropped when ANY of its rows matches — a row condition
    cannot say it. Fixture: invoice 3 carries a discount line (LINETYPE 2), so its item line (10) leaves the sum:
    lines 10 + 5 + 2 = 17 → 5 + 2 = 7."""
    sq = _grouped_measure(catalog, profiles, excluded=True)
    out, value = _compile_run(catalog, profiles, logo_db, sq)
    up = out.sql.upper()
    assert "LEFT JOIN (SELECT" in up and "IS NULL" in up and "LIKE '2%'" in out.sql and "EXISTS" not in up, out.sql
    assert value == 7, (value, out.sql)


def test_without_the_exclusion_the_same_measure_counts_every_group(catalog, profiles, logo_db):
    sq = _grouped_measure(catalog, profiles, excluded=False)
    out, value = _compile_run(catalog, profiles, logo_db, sq)
    assert "LEFT JOIN" not in out.sql.upper() and value == 17, (value, out.sql)


def _aggregate_bodies(sql: str) -> list[str]:
    """Every aggregate call's argument text, parentheses matched by hand — no parser, no dialect."""
    import re as _re
    out = []
    for m in _re.finditer(r"\b(SUM|COUNT|AVG|MIN|MAX)\s*\(", sql, _re.I):
        depth, i = 1, m.end()
        while i < len(sql) and depth:
            depth += {"(": 1, ")": -1}.get(sql[i], 0)
            i += 1
        out.append(sql[m.end():i - 1])
    return out


def test_no_aggregate_of_the_compiled_measure_contains_a_subquery(catalog, profiles, logo_db):
    """SQL Server refuses an aggregate over an expression containing a subquery (error 130); SQLite accepts it, so
    running the fixture cannot catch it. Checked on the text: no aggregate argument holds a SELECT."""
    for question in ("Yalın hacim ne kadar?", "2026 yalın hacim ne kadar?"):
        sq = _grouped_measure(catalog, profiles, excluded=True, question=question)
        out, _ = _compile_run(catalog, profiles, logo_db, sq)
        bodies = _aggregate_bodies(out.sql)
        assert bodies and not [b for b in bodies if "SELECT" in b.upper()], out.sql


def test_the_anti_join_side_owes_no_period_and_the_dated_answer_passes_the_gate(catalog, profiles, logo_db):
    """The derived table reads the measure's table only to find the groups to drop; a period asked of the measure is
    not owed on it."""
    from semantic_layer.runtime.audit import gate_report, sources_from
    sq = _grouped_measure(catalog, profiles, excluded=True, question="2026 yalın hacim ne kadar?")
    out, value = _compile_run(catalog, profiles, logo_db, sq)
    assert value == 7, (value, out.sql)
    unmet = [u.text for u in gate_report(sq, out.sql, sources=sources_from(profiles))]
    assert not [u for u in unmet if "dönemi" in u or "hariç tuttuğu" in u], (unmet, out.sql)


def test_the_gate_refuses_an_answer_that_keeps_the_excluded_groups(catalog, profiles, logo_db):
    from semantic_layer.runtime.audit import gate_report
    sq = _grouped_measure(catalog, profiles, excluded=True)
    out, _ = _compile_run(catalog, profiles, logo_db, sq)
    kept = ("SELECT SUM(s.AMOUNT) AS yalin_hacim FROM LG_411_01_STLINE s "
            "WHERE s.CANCELLED = 0 AND s.TRCODE IN (7, 8) AND s.LINETYPE IN (0)")
    assert any("hariç tuttuğu gruplar" in u.text for u in gate_report(sq, kept)), [u.text for u in gate_report(sq, kept)]
    assert not [u for u in gate_report(sq, out.sql) if "hariç tuttuğu gruplar" in u.text], out.sql
    written = kept + (" AND NOT EXISTS (SELECT 1 FROM LG_411_01_STLINE g WHERE g.INVOICEREF = s.INVOICEREF "
                      "AND g.LINETYPE LIKE '2%')")
    assert not [u for u in gate_report(sq, written) if "hariç tuttuğu gruplar" in u.text], "a model-written NOT EXISTS counts"
    anti = ("SELECT SUM(CASE WHEN hx.INVOICEREF IS NULL THEN s.AMOUNT ELSE 0 END) AS yalin_hacim FROM LG_411_01_STLINE s "
            "LEFT JOIN (SELECT g.INVOICEREF FROM LG_411_01_STLINE g WHERE g.LINETYPE LIKE '2%' GROUP BY g.INVOICEREF) hx "
            "ON hx.INVOICEREF = s.INVOICEREF WHERE s.CANCELLED = 0 AND s.TRCODE IN (7, 8) AND s.LINETYPE IN (0)")
    assert not [u for u in gate_report(sq, anti) if "hariç tuttuğu gruplar" in u.text], "an anti-join tested inside the CASE counts"
    unjoined = anti.replace("hx.INVOICEREF IS NULL", "1 = 1")
    assert any("hariç tuttuğu gruplar" in u.text for u in gate_report(sq, unjoined)), "a LEFT JOIN never tested IS NULL excludes nothing"

