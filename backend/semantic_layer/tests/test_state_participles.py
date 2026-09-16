"""A participle names a state, and a state this deployment records is a labelled code.

"iptal edilmemiş sipariş" asked for nothing before this: the resolver could not say what condition the
word imposed, so it asked the person instead of reading the label the source itself writes next to the
code. These tests hold that reading to the catalog: the word must reach the labelled value, the
negative must exclude it, and two columns answering to the same word must still ask.
"""
from __future__ import annotations

from datetime import date

from semantic_layer.models import ColumnProfile, SchemaProfile, SemanticType
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401

TODAY = date(2026, 7, 20)


def orders(extra=()):
    status = ColumnProfile(name="statuscode", data_type="int", distinct_count=4,
                           top_values=[("100000002", 180), ("100000001", 41)],
                           value_labels={"1": "Taslak", "100000000": "Sevk Edildi",
                                         "100000001": "İptal Edildi", "100000002": "Sipariş"})
    amount = ColumnProfile(name="new_kdvlitoplamtutar", data_type="money")
    return SchemaProfile(datasource_id=DS, table_name="new_siparisBase", table_pattern="new_siparisBase",
                         entity="NEW_SIPARISBASE", schema_name="Timas_MSCRM.dbo", description="Sipariş",
                         columns=[status, amount, *extra], row_count=333_063)


def resolve(catalog, profiles, question):
    return SemanticResolver(catalog, TENANT, DS, profiles).resolve(question, today=TODAY)


def state_slots(sq):
    return [s for s in sq.slots if (s.explain or {}).get("source") == "value_label"]


def test_a_state_word_reaches_the_code_the_source_named(catalog, profiles):
    profiles = profiles + [orders()]
    sq = resolve(catalog, profiles, "iptal edilen sipariş sayısı")
    found = state_slots(sq)
    assert found, sq.to_dict()
    m = found[0].mapping
    assert (m.entity, m.column, m.operator, m.values) == ("NEW_SIPARISBASE", "STATUSCODE", "IN", ["100000001"])
    assert found[0].semantic_type == SemanticType.DIMENSION_VALUE
    assert "İptal Edildi" in found[0].explain["why"]


def test_the_negative_excludes_that_code_instead_of_asking(catalog, profiles):
    profiles = profiles + [orders()]
    sq = resolve(catalog, profiles, "iptal edilmemiş sipariş sayısı")
    found = state_slots(sq)
    assert found, sq.to_dict()
    assert found[0].mapping.operator == "NOT IN" and found[0].mapping.values == ["100000001"]
    assert not any("iptal" in c.lower() or "edilmemis" in c.lower() for c in sq.clarification), sq.clarification


def test_two_columns_answering_to_the_same_word_still_ask(catalog, profiles):
    twin = ColumnProfile(name="new_sevkdurumu", data_type="int", distinct_count=2,
                         value_labels={"1": "İptal Edildi", "2": "Sevk Edildi"})
    profiles = profiles + [orders(extra=[twin])]
    sq = resolve(catalog, profiles, "iptal edilen sipariş sayısı")
    assert not state_slots(sq), "two readings is ambiguity, not a decision"


def test_a_word_with_no_label_behind_it_is_still_asked_about(catalog, profiles):
    profiles = profiles + [orders()]
    sq = resolve(catalog, profiles, "zımbalanan sipariş sayısı")
    assert not state_slots(sq)
    assert "zimbalanan" in [m["token"] for m in sq.model_qualifiers], "nothing explains it: the model must"


def described_invoice():
    """A source that says what a column is for and never says what its values mean — Logo's own shape."""
    cancelled = ColumnProfile(name="CANCELLED", data_type="smallint",
                              description="İptal Edilmiş (Cancelled)")
    total = ColumnProfile(name="NETTOTAL", data_type="money", description="Net Toplam")
    return SchemaProfile(datasource_id=DS, table_name="LG_411_01_INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
                         entity="LG_INVOICE", schema_name="dbo", description="Fatura",
                         columns=[cancelled, total], row_count=81_760)


def test_a_described_column_carries_the_word_instead_of_asking(catalog, profiles):
    sq = resolve(catalog, profiles + [described_invoice()], "iptal edilmemiş fatura sayısı")
    assert sq.qualifier_columns, sq.to_dict()
    want = sq.qualifier_columns[0]
    assert (want["entity"], want["column"], want["negative"]) == ("LG_INVOICE", "CANCELLED", True)
    assert not any("iptal" in c.lower() or "edilmemis" in c.lower() for c in sq.clarification), sq.clarification


def test_the_gate_refuses_an_answer_that_ignores_that_column(catalog, profiles):
    from semantic_layer.runtime.audit import unmet_obligations

    sq = resolve(catalog, profiles + [described_invoice()], "iptal edilmemiş fatura sayısı")
    ignored = unmet_obligations(sq, "SELECT COUNT(*) AS adet FROM dbo.LG_411_01_INVOICE")
    assert any("CANCELLED" in u for u in ignored), ignored
    honoured = unmet_obligations(sq, "SELECT COUNT(*) AS adet FROM dbo.LG_411_01_INVOICE WHERE CANCELLED = 0")
    assert not any("CANCELLED" in u for u in honoured), honoured


def test_a_word_two_columns_describe_is_still_asked_about(catalog, profiles):
    twin = ColumnProfile(name="CANCELDATE", data_type="datetime", description="İptal Edilme Tarihi")
    prof = described_invoice()
    prof.columns.append(twin)
    sq = resolve(catalog, profiles + [prof], "iptal edilmemiş fatura sayısı")
    assert not sq.qualifier_columns and "edilmemis" in [m["token"] for m in sq.model_qualifiers]


def test_a_shortlist_where_nothing_can_be_dropped_costs_no_model_call(catalog, profiles):
    """A certified catalog that names every table pins every table; the call then decides nothing.

    This is what a grown vocabulary does: once each CRM table had approved everyday names, the
    selector was shown 282 tables, kept 282, and charged the person ninety seconds for it.
    """
    from semantic_layer.runtime.compiler import ExistingCompiler

    class _Selector:
        def __init__(self):
            self.calls = 0

        def select(self, *a, **kw):
            self.calls += 1
            raise AssertionError("bir şey elenemiyorken seçiciye sorulmamalı")

    sq = resolve(catalog, profiles + [orders()], "iptal edilen sipariş sayısı")
    compiler = ExistingCompiler.__new__(ExistingCompiler)
    compiler.selector, compiler.selector_mode = _Selector(), "on"
    compiler.by_entity = {p.entity: p for p in profiles}
    compiler.catalog_entities = {"CLCARD", "INVOICE", "STLINE"}
    kept = compiler.narrow(sq, ["CLCARD", "INVOICE", "STLINE"])
    assert kept == ["CLCARD", "INVOICE", "STLINE"] and compiler.selector.calls == 0


def orders_with_dates():
    due = ColumnProfile(name="new_termintarihi", data_type="datetime", description="Termin Tarihi")
    created = ColumnProfile(name="createdon", data_type="datetime", description="Oluşturulma Tarihi")
    receipt = ColumnProfile(name="new_makbuzno", data_type="nvarchar(100)", description="Makbuz Numarası")
    planned = ColumnProfile(name="new_planlanantutar", data_type="money", description="Planlanan Ciro")
    return orders(extra=[due, created, receipt, planned])


def test_the_words_beside_a_participle_pick_the_column(catalog, profiles):
    sq = resolve(catalog, profiles + [orders_with_dates()], "termin tarihi geçen sipariş sayısı")
    assert sq.qualifier_columns, sq.to_dict()
    assert sq.qualifier_columns[0]["column"] == "NEW_TERMINTARIHI", sq.qualifier_columns
    assert not sq.clarification, sq.clarification


def test_an_empty_field_is_asked_for_on_the_field_it_names(catalog, profiles):
    sq = resolve(catalog, profiles + [orders_with_dates()], "makbuz numarası girilmemiş sipariş sayısı")
    assert sq.qualifier_columns and sq.qualifier_columns[0]["column"] == "NEW_MAKBUZNO", sq.to_dict()
    assert sq.qualifier_columns[0]["negative"] is True


def test_a_participle_that_names_a_measure_is_not_a_condition(catalog, profiles):
    sq = resolve(catalog, profiles + [orders_with_dates()], "sipariş bazında planlanan ciro")
    assert not sq.qualifier_columns, "a named amount demands no restriction"
    assert any(c.get("column") == "NEW_PLANLANANTUTAR" for c in sq.candidates), sq.candidates
    assert not sq.clarification, sq.clarification


def test_a_number_is_not_a_participle(catalog, profiles):
    sq = resolve(catalog, profiles + [orders_with_dates()], "vadesi doksan günü aşan sipariş sayısı")
    assert not any("doksan" in c for c in sq.clarification), sq.clarification



def test_every_label_the_prompt_uses_comes_back_as_the_stored_table(profiles):
    """Round trip: what the model is told a table is called must physicalise to that table.

    A CRM schema carries its database ("Timas_MSCRM.dbo"); glued to the table name with "_", the
    label split at the wrong dot and fourteen questions reached the server with a name it lacks.
    """
    from semantic_layer.runtime.guardrails import allowed_tables, physicalize_sql

    crm = orders()
    crm.entity, crm.table_name, crm.table_pattern = "NEW_SIPARISBASE", "new_siparisBase", "new_siparisBase"
    everything = profiles + [crm]
    label = "Timas_MSCRM_dbo_new_siparisBase"
    sql = f"SELECT COUNT(*) FROM {label} WHERE {label}.statuscode <> 1"
    assert allowed_tables(sql, everything, {})[0], allowed_tables(sql, everything, {})
    out = physicalize_sql(sql, everything, {})
    assert "[Timas_MSCRM].[dbo].[new_siparisBase]" in out, out
    # the written name survives as the alias, so the qualified column still binds
    assert f"AS {label}" in out and f"{label}.statuscode" in out, out


def test_a_list_gets_no_year_nobody_asked_for(catalog, profiles):
    """A question about master data has no date to restrict. A default year added to it became a
    restriction the gate then hunted for on a column nobody chose, and the answer was refused."""
    import datetime as dt
    from semantic_layer.models import TemporalSlot

    year = TemporalSlot(text="varsayılan", primitive="YEAR", start=dt.date(2026, 1, 1), end=dt.date(2027, 1, 1),
                        grain="YEAR", params={"year": 2026, "default": True})
    r = SemanticResolver(catalog, TENANT, DS, profiles, default_temporal=year)
    listing = r.resolve("kanal bazında cari listesi", today=TODAY)
    assert not listing.temporal and any("tüm kayıtlar" in e for e in listing.explanation), listing.explanation
    measure = r.resolve("net ciro", today=TODAY)
    assert measure.temporal and measure.temporal[0].params.get("default"), "a measure still gets the default year"


def test_written_counts_are_periods():
    from semantic_layer.runtime.temporal import parse_temporal

    found, _ = parse_temporal("son üç ayda en çok satan kitaplar", today=TODAY)
    assert found and found[0].primitive == "LAST_N_MONTHS" and found[0].params["n"] == 3, found


def test_a_word_left_to_the_model_must_be_read_and_applied():
    """The gate holds a model-interpreted word to two things: a reading line, and a restriction."""
    from semantic_layer.models import SemanticQuery
    from semantic_layer.runtime.audit import unmet_obligations

    sq = SemanticQuery(question="tahsil edilmemiş alacaklar", tenant_id=TENANT, datasource_id=DS)
    sq.model_qualifiers = [{"token": "edilmemis", "position": 1, "negative": True, "phrase": "tahsil edilmemis alacaklar"}]
    silent = unmet_obligations(sq, "SELECT SUM(AMOUNT) FROM PAYTRANS")
    assert any("yorumlandığı yazılmadı" in u for u in silent), silent
    said_only = unmet_obligations(sq, "-- yorum: 'edilmemiş' → kapanmamış ödeme satırları\nSELECT SUM(AMOUNT) FROM PAYTRANS")
    assert any("hiçbir koşula dönüşmedi" in u for u in said_only), said_only
    applied = unmet_obligations(sq, "-- yorum: 'edilmemiş' → kapanmamış ödeme satırları\n"
                                    "SELECT SUM(AMOUNT) FROM PAYTRANS WHERE PAID = 0")
    assert not any("niteleyici" in u for u in applied), applied


def test_the_models_reading_is_shown_above_the_answer():
    from semantic_layer.runtime.compiler import interpretations

    sql = "-- yorum: 'edilmemiş' → PAID = 0 olan satırlar\n-- yorum: 'aşmış' → bakiye > limit\nSELECT 1"
    assert interpretations(sql) == ["'edilmemiş' → PAID = 0 olan satırlar", "'aşmış' → bakiye > limit"]


def test_a_reading_written_before_or_outside_the_sql_block_is_kept():
    from semantic_layer.runtime.compiler import extract_sql, interpretations

    inside = "```sql\n-- yorum: 'duran' → portföydeki çekler\nSELECT 1 FROM CSCARD WHERE STATUS = 1\n```"
    assert extract_sql(inside) and interpretations(extract_sql(inside)) == ["'duran' → portföydeki çekler"]
    outside = "-- yorum: 'duran' → portföydeki çekler\n```sql\nSELECT 1 FROM CSCARD WHERE STATUS = 1\n```"
    assert interpretations(extract_sql(outside)) == ["'duran' → portföydeki çekler"]
    assert extract_sql("```sql\n-- yorum: 'x' → yok\nNO_SQL: şemada yok\n```") is None
