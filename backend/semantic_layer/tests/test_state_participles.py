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


def test_a_qualifier_on_the_entity_name_binds_after_the_table_is_renamed(profiles):
    """The model wrote the table under its label and qualified a column by the entity. After
    physicalisation neither name was left, and SQL Server could not bind the column."""
    from semantic_layer.runtime.guardrails import physicalize_sql

    crm = orders()
    crm.entity, crm.table_name, crm.table_pattern = "NEW_SIPARISBASE", "new_siparisBase", "new_siparisBase"
    sql = "SELECT SUM(NEW_SIPARISBASE.statuscode) FROM Timas_MSCRM_dbo_new_siparisBase"
    out = physicalize_sql(sql, profiles + [crm], {})
    assert "NEW_SIPARISBASE.statuscode" not in out.replace('"', "").replace("[", "").replace("]", ""), out
    assert "Timas_MSCRM_dbo_new_siparisBase.statuscode" in out, out


def test_two_periods_without_a_comparison_word_are_two_conditions(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    absence = r.resolve("2025 yılında alıp 2026 yılında hiç almamış cariler", today=TODAY)
    assert absence.comparison is None, absence.comparison
    compared = r.resolve("2026 net ciro 2025 yılına göre", today=TODAY)
    assert compared.comparison is not None


def test_a_state_word_does_not_cross_into_the_other_database(catalog, profiles):
    """A question placed in the ERP never takes a condition from a CRM table."""
    crm = orders()
    sq = resolve(catalog, profiles + [crm], "iptal edilen net ciro")
    assert not any(s.mapping and s.mapping.entity == "NEW_SIPARISBASE" for s in state_slots(sq)), sq.to_dict()


def test_a_bare_verb_root_is_not_a_reading(catalog, profiles):
    stay = ColumnProfile(name="new_kalmasuresi", data_type="int", description="Depoda Kalma Süresi")
    sq = resolve(catalog, profiles + [orders(extra=[stay])], "elimizde hiç kalmamış sipariş sayısı")
    assert not any(q["column"] == "NEW_KALMASURESI" for q in sq.qualifier_columns), sq.qualifier_columns


def test_a_missing_column_is_answered_with_the_tables_real_columns(profiles):
    from semantic_layer.runtime.compiler import ExistingCompiler

    c = ExistingCompiler.__new__(ExistingCompiler)
    c.profiles = profiles + [orders()]
    c.dialect, c.model_naming, c.period_in_sql, c.context, c.tables_of = "tsql", "mdl", False, {}, {}
    hint = c.column_hint("SELECT new_kdvli_tutar FROM NEW_SIPARISBASE",
                         "[42S22] [FreeTDS][SQL Server]Invalid column name 'new_kdvli_tutar'. (207)")
    assert "new_kdvlitoplamtutar" in hint and "new_kdvli_tutar" in hint, hint
    assert c.column_hint("SELECT 1", "some other error") == ""


def test_a_query_timeout_is_not_a_lost_connection():
    from semantic_layer.runtime.guardrails import is_connection_error, is_query_timeout

    timeout = "('HYT00', '[HYT00] [FreeTDS][SQL Server]Timeout expired (0) (SQLExecDirectW)')"
    down = "('08S01', '[08S01] [FreeTDS][SQL Server]Communication link failure (0)')"
    assert is_query_timeout(timeout) and not is_connection_error(timeout)
    assert is_connection_error(down) and not is_query_timeout(down)


def test_is_not_null_on_the_period_column_admits_the_period():
    from semantic_layer.runtime import audit
    tree = audit.parse_sql('SELECT AVG(CASE WHEN I."DATE_" >= \'2025-01-01\' AND I."DATE_" < \'2026-01-01\' THEN 1 END) AS a '
                           'FROM INVOICE I WHERE I."DATE_" IS NOT NULL AND I."DATE_" >= \'2025-01-01\' AND I."DATE_" < \'2027-01-01\'')
    period = {"start": "2025-01-01", "end": "2026-01-01"}
    assert audit._admits_period(tree.args.get("where"), {("I", "DATE_")}, period)


def test_a_question_word_that_is_a_column_name_elsewhere_is_not_swallowed(catalog, profiles):
    """"tahsilat" happens to be a column on an unrelated table; the question still gets to say it."""
    stray = SchemaProfile(datasource_id=DS, table_name="ESP_KULLANICIGRUP", table_pattern="ESP_KULLANICIGRUP",
                          entity="ESP_KULLANICIGRUP", schema_name="dbo", description="Kullanıcı grubu",
                          columns=[ColumnProfile(name="TAHSILAT", data_type="int")])
    sq = resolve(catalog, profiles + [stray], "ortalama tahsilat vademiz kaç gün")
    assert "tahsilat" in sq.unresolved, sq.to_dict()


def test_an_unresolved_word_needs_a_reading_line_too():
    from semantic_layer.models import SemanticQuery
    from semantic_layer.runtime.audit import unmet_obligations

    sq = SemanticQuery(question="alacaklarımızı yaşlandır", tenant_id=TENANT, datasource_id=DS)
    sq.unresolved = ["alacaklarimizi"]
    silent = unmet_obligations(sq, "SELECT SUM(NETTOTAL) FROM INVOICE")
    assert any("alacaklarimizi" in u and "yorumland" in u for u in silent), silent
    said = unmet_obligations(sq, "-- yorum: 'alacak' → kesilen satış faturalarının tutarı\nSELECT SUM(NETTOTAL) FROM INVOICE")
    assert not any("yorumland" in u for u in said), said


def test_an_undated_call_reads_the_years_the_statement_names(profiles):
    """run_sql passes no period. The statement dates its own rows; those years are read — not the
    biggest copy, which silently answered a 2026 question from 2021–2025."""
    from semantic_layer.runtime.guardrails import physicalize_sql

    years = [SchemaProfile(datasource_id=DS, table_name=f"LG_{n}_01_INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
                           entity="INVOICE", schema_name="dbo", description="Fatura", row_count=rows,
                           context={"n0": n, "n1": "01"}, time_window=(w0, w1),
                           columns=[ColumnProfile(name="DATE_", data_type="datetime"), ColumnProfile(name="NETTOTAL", data_type="float")])
             for n, rows, w0, w1 in (("211", 500_000, "2021-01-01", "2025-12-31"), ("411", 80_000, "2026-01-01", "2026-08-17"))]
    out = physicalize_sql("SELECT SUM(NETTOTAL) FROM INVOICE WHERE DATE_ >= '2026-01-01' AND DATE_ < '2027-01-01'", years, {})
    assert "LG_411_01_INVOICE" in out and "LG_211_01_INVOICE" not in out, out


def _copies():
    def prof(entity, pattern, firm, rows, window, cols):
        return SchemaProfile(datasource_id=DS, table_name=pattern.replace("{n0}", firm).replace("{n1}", "01"), table_pattern=pattern,
                             entity=entity, schema_name="dbo", description=entity, row_count=rows, context={"n0": firm, "n1": "01"},
                             time_window=window, columns=[ColumnProfile(name=c) for c in cols])
    out = []
    for firm, window in (("211", ("2021-01-01", "2025-12-31")), ("411", ("2026-01-01", "2026-08-17"))):
        out.append(prof("INVOICE", "LG_{n0}_{n1}_INVOICE", firm, 100, window, ["LOGICALREF", "DATE_", "NETTOTAL", "CLIENTREF"]))
        out.append(prof("PAYTRANS", "LG_{n0}_{n1}_PAYTRANS", firm, 100, window, ["LOGICALREF", "DATE_", "FICHEREF", "MODULENR"]))
        out.append(prof("CLCARD", "LG_{n0}_CLCARD", firm, 50, None, ["LOGICALREF", "DEFINITION_"]))
    return out


def test_partitioned_relations_spread_in_lockstep_and_join_within_their_copy():
    from datetime import date
    from semantic_layer.runtime.guardrails import physicalize_sql

    sql = ('SELECT AVG(DATEDIFF(day, i."DATE_", p."DATE_")) AS gun FROM PAYTRANS p JOIN INVOICE i ON i."LOGICALREF" = p."FICHEREF" '
           'WHERE i."DATE_" >= \'2025-01-01\' AND i."DATE_" < \'2027-01-01\'')
    out = physicalize_sql(sql, _copies(), {}, period=(date(2025, 1, 1), date(2027, 1, 1)))
    assert "LG_211_01_PAYTRANS" in out and "LG_411_01_PAYTRANS" in out, out
    assert "LG_211_01_INVOICE" in out and "LG_411_01_INVOICE" in out, out
    assert out.count("__nb_firm") >= 5 and "[i].[__nb_firm] = [p].[__nb_firm]" in out.replace('"', "") or "__nb_firm] = " in out, out


def test_a_single_year_question_reads_the_reference_table_of_the_same_copy():
    from datetime import date
    from semantic_layer.runtime.guardrails import physicalize_sql

    sql = ('SELECT c."DEFINITION_", SUM(i."NETTOTAL") FROM INVOICE i JOIN CLCARD c ON c."LOGICALREF" = i."CLIENTREF" '
           'WHERE i."DATE_" >= \'2026-01-01\' AND i."DATE_" < \'2027-01-01\' GROUP BY c."DEFINITION_"')
    out = physicalize_sql(sql, _copies(), {}, period=(date(2026, 1, 1), date(2027, 1, 1)))
    assert "LG_411_CLCARD" in out and "LG_211_CLCARD" not in out, out
    assert "__nb_firm" not in out, "one copy needs no tag"


def test_a_keyword_alias_is_quoted():
    from semantic_layer.runtime.guardrails import physicalize_sql

    out = physicalize_sql("WITH plan AS (SELECT 1 AS x FROM INVOICE) SELECT AVG(x) FROM plan", _copies(), {})
    assert "[plan]" in out, out
