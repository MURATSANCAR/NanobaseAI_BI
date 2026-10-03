"""Ölçünün satır kapsamı cevapta tutarlı ve görünür (2026-09-30, A044 sınıfı — soruya özel değil).

  1. Ölçünün yanındaki sayım ölçüyle aynı satırları saymalı: seyrek bir kolonun toplamının yanında bütün satırları sayan
     COUNT eleştirmende reddedilir, onarım talimatıyla (`critic._count_scope`); istem de ölçüyü «seyrek kolon» diye gösterir.
  2. Ölçünün kapsam sınırı cevabın `dataNotes`'unda: kolonda beyan edilmiş VERİ NOTU toplanan ölçü için de gösterilir;
     beyan yoksa profilin «taramada boş» ölçümü, satır geldiyse «kapsamı sınırlı» der (`column_facts`).
  3. Kırılım için okunan kardeş ölçünün notu (`explain.scope_note`) cevabın `dataNotes`'una gider (`column_facts.scope_notes`).

Veriler yapaydır; gerçek veriyle ölçüm test sunucusunda (answer-gate).
"""
from __future__ import annotations

from datetime import date

from semantic_layer.models import ColumnProfile, SchemaProfile, SemanticType
from semantic_layer.runtime.column_facts import predicate_column_notes, scope_notes
from semantic_layer.runtime.critic import review
from semantic_layer.tests.test_zeki_kapi_0929 import _family_world

TODAY = date(2026, 9, 30)


def _events(cost_null=0.999):
    event = SchemaProfile(datasource_id="d", table_name="new_eventBase", table_pattern="NEW_EVENTBASE", entity="NEW_EVENTBASE",
                          schema_name="crm.dbo", row_count=57_000, primary_key=["new_eventId"],
                          columns=[ColumnProfile(name="new_eventId", data_type="uniqueidentifier", is_primary_key=True, null_ratio=0.0),
                                   ColumnProfile(name="new_Cost", data_type="money", null_ratio=cost_null, description="Toplam Gider"),
                                   ColumnProfile(name="statecode", data_type="int", null_ratio=0.0)])
    link = SchemaProfile(datasource_id="d", table_name="new_event_contactBase", table_pattern="NEW_EVENT_CONTACTBASE",
                         entity="NEW_EVENT_CONTACTBASE", schema_name="crm.dbo", row_count=9_000,
                         columns=[ColumnProfile(name="new_eventid", data_type="uniqueidentifier"),
                                  ColumnProfile(name="contactid", data_type="uniqueidentifier")],
                         relationships=[{"column": "new_eventid", "ref_entity": "NEW_EVENTBASE", "ref_column": "new_eventId"},
                                        {"column": "contactid", "ref_entity": "CONTACTBASE", "ref_column": "ContactId"}])
    person = SchemaProfile(datasource_id="d", table_name="ContactBase", table_pattern="CONTACTBASE", entity="CONTACTBASE",
                           schema_name="crm.dbo", row_count=59_000, primary_key=["ContactId"],
                           columns=[ColumnProfile(name="ContactId", data_type="uniqueidentifier", is_primary_key=True),
                                    ColumnProfile(name="FullName", data_type="nvarchar(160)", null_ratio=0.0)])
    return [event, link, person]


_PER_AUTHOR = ("SELECT TOP 5 c.FullName AS yazar, COUNT(DISTINCT e.new_eventId) AS etkinlik_sayisi, "
               "SUM(e.new_Cost) AS toplam_gider FROM new_eventBase e "
               "JOIN new_event_contactBase x ON e.new_eventId = x.new_eventid JOIN ContactBase c ON x.contactid = c.ContactId "
               "WHERE e.statecode = 0 {extra}GROUP BY c.FullName ORDER BY toplam_gider DESC")


# ---------------------------------------------------------------- 1. sayım ölçünün satırlarında

def test_a_count_beside_a_sparse_measure_over_all_rows_is_refused_with_the_rewrite():
    f = [x for x in review(_PER_AUTHOR.format(extra=""), _events()) if x.kind == "COUNT_SCOPE"]
    assert f and f[0].severity == "block", f
    assert "e.new_Cost IS NOT NULL" in f[0].message and "COUNT(DISTINCT e.new_eventId)" in f[0].message, f[0].message


def test_a_second_sources_table_written_by_its_logical_name_is_reviewed():
    """The model writes a CRM table as `<database>_dbo_<table>` (schema `Timas_MSCRM.dbo`, dots as underscores). That
    name matched no profile, so nothing in a CRM statement was ever reviewed — the count above went through live."""
    sql = _PER_AUTHOR.format(extra="").replace("new_eventBase e", "crm_dbo_new_eventBase e") \
        .replace("new_event_contactBase x", "crm_dbo_new_event_contactBase x").replace("ContactBase c", "crm_dbo_ContactBase c")
    assert [x for x in review(sql, _events()) if x.kind == "COUNT_SCOPE"], sql


def test_the_same_count_restricted_to_the_measures_rows_passes():
    for extra in ("AND e.new_Cost > 0 ", "AND e.new_Cost IS NOT NULL "):
        assert not [x for x in review(_PER_AUTHOR.format(extra=extra), _events()) if x.kind == "COUNT_SCOPE"], extra


def test_a_count_that_reads_the_measure_column_itself_is_in_scope():
    sql = ("SELECT c.FullName, COUNT(DISTINCT CASE WHEN e.new_Cost IS NOT NULL THEN e.new_eventId END) AS n, SUM(e.new_Cost) AS s "
           "FROM new_eventBase e JOIN new_event_contactBase x ON e.new_eventId = x.new_eventid "
           "JOIN ContactBase c ON x.contactid = c.ContactId GROUP BY c.FullName")
    assert not [x for x in review(sql, _events()) if x.kind == "COUNT_SCOPE"]


def test_a_dense_measure_keeps_its_count_as_written():
    """Rows without the amount are a rounding error on a filled column (LINENET): the count is not the reviewer's."""
    assert not [x for x in review(_PER_AUTHOR.format(extra=""), _events(cost_null=0.02)) if x.kind == "COUNT_SCOPE"]


def test_a_count_in_another_select_than_the_measure_is_not_compared():
    sql = ("SELECT (SELECT COUNT(*) FROM new_eventBase) AS tum, SUM(e.new_Cost) AS s FROM new_eventBase e WHERE e.new_Cost > 0")
    assert not [x for x in review(sql, _events()) if x.kind == "COUNT_SCOPE"]


def test_the_prompt_marks_a_measure_over_a_sparse_column():
    from semantic_layer.runtime.compiler import ExistingCompiler
    comp = ExistingCompiler.__new__(ExistingCompiler)
    comp.profiles = _events()
    assert "seyrek kolon: NEW_EVENTBASE.new_Cost" in comp._sparse("SUM(NEW_EVENTBASE.new_Cost)")
    comp.profiles = _events(cost_null=0.02)
    assert comp._sparse("SUM(NEW_EVENTBASE.new_Cost)") == ""


# ---------------------------------------------------------------- 2. ölçünün kapsam notu

_SUM = "SELECT SUM(e.new_Cost) AS gider FROM new_eventBase e WHERE e.statecode = 0"


def test_a_declared_note_on_a_summed_column_is_given_with_the_answer():
    said = {("NEW_EVENTBASE", "NEW_COST"): "VERİ NOTU: Bu alan 57.972 kaydın yalnız 28 tanesinde dolu."}
    notes = predicate_column_notes(_SUM, _events(), said, result_is_empty=False)
    assert [n["kind"] for n in notes] == ["DECLARED"] and "yalnız 28" in notes[0]["message"], notes


def test_without_a_declaration_a_measure_the_scan_saw_empty_is_said_to_be_partial():
    notes = predicate_column_notes(_SUM, _events(), {}, result_is_empty=False)
    assert [n["kind"] for n in notes] == ["SPARSE_MEASURE"] and "kapsamı sınırlı" in notes[0]["message"], notes


def test_a_measure_over_a_filled_column_carries_no_note():
    assert predicate_column_notes(_SUM, _events(cost_null=0.02), {}, result_is_empty=False) == []


def test_a_column_only_tested_inside_the_aggregate_is_no_measure():
    """SUM(CASE WHEN e.new_Cost > 0 THEN 1 ELSE 0 END) counts rows; the cost is a condition there, not the figure."""
    sql = "SELECT SUM(CASE WHEN e.new_Cost > 0 THEN 1 ELSE 0 END) AS n FROM new_eventBase e"
    assert [n["kind"] for n in predicate_column_notes(sql, _events(), {}, result_is_empty=False)] == []


# ---------------------------------------------------------------- 3. kardeş ölçünün notu cevapta

def test_the_sibling_measures_scope_note_reaches_the_answers_data_notes(store):
    sq = _family_world(store).resolve("Olay gideri yazar bazında nasıl dağılıyor?", today=TODAY)
    notes = scope_notes(sq)
    assert len(notes) == 1 and notes[0]["kind"] == "MEASURE_SCOPE", notes
    msg = notes[0]["message"]
    assert "'kart olay gideri'" in msg and "'olay gideri'" in msg and "yazar" in msg, msg
    assert "EVENT" not in msg and "LEDGER" not in msg, "the person reads measure names, not tables"


def test_a_measure_read_as_named_carries_no_scope_note(store):
    sq = _family_world(store, with_breakdown_word=False).resolve("Olay gideri yazar bazında nasıl dağılıyor?", today=TODAY)
    assert scope_notes(sq) == []
    assert all(s.semantic_type != SemanticType.METRIC or s.mapping.entity == "LEDGER" for s in sq.slots if s.mapping)
