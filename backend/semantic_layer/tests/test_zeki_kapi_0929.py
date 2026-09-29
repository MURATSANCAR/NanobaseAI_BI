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


def test_a_word_that_opens_a_breakdown_is_not_read_as_an_observed_value(catalog, profiles):
    """A044: «yazar bazında … en pahalı beş yazar» — the word is what the answer is broken down by, at both places."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("Satış tutarı dağıtıcı bazında nasıl dağılıyor, en yüksek iki dağıtıcı kim?", today=TODAY)
    assert not _value_filters(sq, "DAGITICI"), [(s.term, s.semantic_type, s.mapping.values if s.mapping else None) for s in sq.slots]


def test_the_same_word_without_a_breakdown_cue_is_still_a_value(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
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


def test_the_generic_measure_stays_when_no_certified_name_is_split(catalog, profiles):
    sq = _cost_catalog(catalog, profiles).resolve("Bu yıl toplam gider ne kadar?", today=TODAY)
    assert _metric_terms(sq) == ["gider"], (_metric_terms(sq), sq.explanation)
