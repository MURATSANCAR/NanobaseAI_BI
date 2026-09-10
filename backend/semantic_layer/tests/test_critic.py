"""The critic reads a query for the ways it can return the wrong number."""
from __future__ import annotations

import pytest

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime.critic import review
from semantic_layer.tests.test_runtime import catalog  # noqa: F401  — the certified fixture lives there


def _t(entity, name, cols, pk="LOGICALREF", rels=()):
    return SchemaProfile(datasource_id="d", table_name=name, table_pattern=name, entity=entity, schema_name="dbo",
                         columns=[ColumnProfile(name=n, data_type=dt, is_primary_key=(n == pk)) for n, dt in cols],
                         primary_key=[pk], relationships=list(rels))


STLINE = _t("STLINE", "LG_411_01_STLINE", [("LOGICALREF", "int"), ("STOCKREF", "int"), ("TOTAL", "decimal(18,2)"), ("SPECODE", "nvarchar(17)")],
            rels=[{"column": "STOCKREF", "ref_entity": "ITEMS", "ref_column": "LOGICALREF"}])
ITEMS = _t("ITEMS", "LG_411_ITEMS", [("LOGICALREF", "int"), ("CODE", "nvarchar(25)"), ("PRICE", "float")])
P = [STLINE, ITEMS]


def test_a_sum_on_the_many_side_of_a_join_is_fine():
    sql = "SELECT i.CODE, SUM(s.TOTAL) FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.STOCKREF = i.LOGICALREF GROUP BY i.CODE"
    assert [f.kind for f in review(sql, P)] == []


def test_a_sum_on_the_keyed_side_is_inflated_once_per_matching_row():
    """The item price is joined onto every sales line of that item and summed once per line."""
    sql = "SELECT i.CODE, SUM(i.PRICE) FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.STOCKREF = i.LOGICALREF GROUP BY i.CODE"
    f = review(sql, P)
    assert f and f[0].kind == "FANOUT" and f[0].severity == "block"
    assert "ITEMS" in f[0].message


def test_count_star_over_a_fan_out_is_inflated_but_count_distinct_is_not():
    base = "FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.STOCKREF = i.LOGICALREF"
    assert any(f.kind == "FANOUT" for f in review(f"SELECT COUNT(*) {base}", P))
    assert not review(f"SELECT COUNT(DISTINCT i.LOGICALREF) {base}", P)


def test_a_sum_over_a_code_column_is_not_a_number():
    f = review("SELECT SUM(s.SPECODE) FROM dbo.LG_411_01_STLINE s", P)
    assert f and f[0].kind == "NON_NUMERIC" and "SPECODE" in f[0].message


def test_a_column_the_table_does_not_have():
    f = review("SELECT s.NETTOTAL FROM dbo.LG_411_01_STLINE s", P)
    assert [x.kind for x in f] == ["UNKNOWN_COLUMN"]


def test_a_join_the_catalog_knows_nothing_about_is_only_a_warning_and_only_when_the_graph_exists():
    # STLINE has relationships recorded, so a join on a column it does not link through is suspect
    sql = "SELECT SUM(s.TOTAL) FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.SPECODE = i.CODE"
    f = review(sql, P)
    assert any(x.kind == "UNKNOWN_JOIN" and x.severity == "warn" for x in f)
    # with no relationships anywhere the graph is still being filled: say nothing
    bare = [_t("STLINE", "LG_411_01_STLINE", [("LOGICALREF", "int"), ("SPECODE", "nvarchar(17)"), ("TOTAL", "decimal")]),
            _t("ITEMS", "LG_411_ITEMS", [("LOGICALREF", "int"), ("CODE", "nvarchar(25)")])]
    assert not any(x.kind == "UNKNOWN_JOIN" for x in review(sql, bare))


# --- CTE'ler: modelin en sevdiği kalıp, ve kritiğin uzun süre okuyamadığı yer ---------------

INVOICE = _t("INVOICE", "LG_411_01_INVOICE", [("LOGICALREF", "int"), ("CLIENTREF", "int"), ("DATE_", "datetime"), ("NETTOTAL", "decimal(18,2)")])
STLINE2 = _t("STLINE", "LG_411_01_STLINE", [("LOGICALREF", "int"), ("INVOICEREF", "int"), ("STOCKREF", "int"), ("AMOUNT", "float"), ("TOTAL", "decimal(18,2)")])
PC = [INVOICE, STLINE2, ITEMS]

# Fatura seviyesinde toplanmış ciro, fatura×ürün tanecikli satır toplamlarıyla birleştirilip yeniden
# toplanıyor: bir faturada kaç ürün varsa o faturanın cirosu o kadar kez sayılıyor.
_CTE_FANOUT = """
WITH invoice_totals AS (
    SELECT i.LOGICALREF, YEAR(i.DATE_) AS yil, SUM(i.NETTOTAL) AS net_ciro
    FROM dbo.LG_411_01_INVOICE i GROUP BY i.LOGICALREF, YEAR(i.DATE_)
),
line_totals AS (
    SELECT sl.INVOICEREF, sl.STOCKREF, SUM(sl.AMOUNT) AS net_adet
    FROM dbo.LG_411_01_STLINE sl GROUP BY sl.INVOICEREF, sl.STOCKREF
)
SELECT it.yil, itm.CODE, SUM(lt.net_adet) AS net_adet, SUM(it.net_ciro) AS net_ciro
FROM invoice_totals it
JOIN line_totals lt ON lt.INVOICEREF = it.LOGICALREF
JOIN dbo.LG_411_ITEMS itm ON itm.LOGICALREF = lt.STOCKREF
GROUP BY it.yil, itm.CODE
"""


def test_a_total_aggregated_in_a_cte_and_re_summed_after_a_join_is_caught():
    f = review(_CTE_FANOUT, PC)
    fan = [x for x in f if x.kind == "FANOUT" and x.severity == "block"]
    assert fan, [x.to_dict() for x in f]
    assert "net_ciro" in fan[0].message
    # ...ve adet doğru: satır tanecikli taraf join'de çoğalmıyor, onun için bulgu yok.
    assert "net_adet" not in " ".join(x.message for x in fan)


def test_a_cte_grouped_by_a_primary_key_is_one_row_per_key_even_with_other_group_columns():
    """YEAR(tarih) gruplama listesine girmesi tanecikliği inceltmez: LOGICALREF zaten süperanahtar."""
    f = review(_CTE_FANOUT, PC)
    assert any(x.kind == "FANOUT" and "seviyesinde" in x.message for x in f)


def test_a_cte_join_that_covers_the_whole_grain_is_not_a_fan_out():
    sql = """
    WITH line_totals AS (
        SELECT sl.INVOICEREF, sl.STOCKREF, SUM(sl.TOTAL) AS tutar
        FROM dbo.LG_411_01_STLINE sl GROUP BY sl.INVOICEREF, sl.STOCKREF
    )
    SELECT itm.CODE, SUM(lt.tutar) AS tutar
    FROM line_totals lt JOIN dbo.LG_411_ITEMS itm ON itm.LOGICALREF = lt.STOCKREF
    GROUP BY itm.CODE
    """
    assert [x.kind for x in review(sql, PC) if x.severity == "block"] == []


def test_a_finding_inside_a_cte_is_still_found():
    """Kapsam ayrımı, iç sorgunun kendi hatasını görmezden gelmek anlamına gelmemeli."""
    sql = """
    WITH per_item AS (
        SELECT itm.CODE, SUM(itm.PRICE) AS fiyat
        FROM dbo.LG_411_01_STLINE sl JOIN dbo.LG_411_ITEMS itm ON sl.STOCKREF = itm.LOGICALREF
        GROUP BY itm.CODE
    )
    SELECT * FROM per_item
    """
    assert any(x.kind == "FANOUT" and x.severity == "block" for x in review(sql, PC))


def test_a_column_of_an_inner_query_is_not_checked_against_the_outer_tables():
    """Eskiden `find_all` alt sorgulara iniyordu: iç sorgunun kolonu dış kapsamın tablosunda aranıp
    'böyle kolon yok' denebiliyordu. Kapsam ayrımı bunu bitirir."""
    sql = """
    SELECT itm.CODE FROM dbo.LG_411_ITEMS itm
    WHERE itm.LOGICALREF IN (SELECT sl.STOCKREF FROM dbo.LG_411_01_STLINE sl WHERE sl.INVOICEREF > 0)
    """
    assert [x.kind for x in review(sql, PC)] == []


def test_unreadable_sql_gets_no_findings_not_a_refusal():
    assert review("SELECT FROM WHERE (((", P) == []


def test_a_clean_single_table_aggregate_has_nothing_to_say():
    assert review("SELECT SUM(TOTAL) AS ciro FROM dbo.LG_411_01_STLINE WHERE STOCKREF > 0", P) == []


def _client(catalog, logo_connector, settings, replies):
    from fastapi.testclient import TestClient

    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    llm = FakeLlm(list(replies))
    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=llm)
    return TestClient(create_app(rt)), llm


#: "How many customers bought something" written as a count over the invoice join. Every customer is
#: counted once per invoice they have, so the answer is the number of invoices wearing the name of
#: the number of customers. The database returns it without complaint.
_INFLATED = ('```sql\nSELECT COUNT(*) AS musteri_sayisi FROM dbo_LG_411_01_INVOICE i '
             'JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" WHERE i."CANCELLED" = 0 AND i."DATE_" >= \'2026-01-01\' AND i."DATE_" < \'2027-01-01\'\n```')
_CORRECT = ('```sql\nSELECT COUNT(DISTINCT c."LOGICALREF") AS musteri_sayisi FROM dbo_LG_411_01_INVOICE i '
            'JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" WHERE i."CANCELLED" = 0 AND i."DATE_" >= \'2026-01-01\' AND i."DATE_" < \'2027-01-01\'\n```')


def test_an_inflated_count_is_sent_back_to_the_model_and_the_corrected_query_is_what_runs(
        catalog, profiles, logo_connector, settings):
    client, llm = _client(catalog, logo_connector, settings, [_INFLATED, _CORRECT])
    r = client.post("/api/v1/ask", json={"question": "Bölgesel satış dağılımı 2026"}).json()

    assert r["type"] == "TEXT_TO_SQL", r.get("explanation")
    assert r["repairs"] == 1, "the finding went back to the model as an instruction"
    assert "DISTINCT" in r["sql"], "what ran is the corrected query"
    told = llm.calls[-1][-1]["content"]
    assert "şişirilmiş" in told and "CLCARD" in told, told[:200]


def test_a_repair_that_does_not_fix_it_refuses_rather_than_returning_the_number(
        catalog, profiles, logo_connector, settings):
    client, _ = _client(catalog, logo_connector, settings, [_INFLATED, _INFLATED])
    r = client.post("/api/v1/ask", json={"question": "Bölgesel satış dağılımı 2026"}).json()

    assert r["type"] == "SQL_INVALID"
    assert "şişirilmiş" in r["explanation"], "the person is told what is wrong, not that the SQL is invalid"
    assert "doğrulanamadı" not in r["explanation"], "a reviewed refusal is not reported as a database fault"
    assert any(n["kind"] == "FANOUT" for n in r["semantic"]["critic"])


def test_one_physical_pattern_is_one_entity_and_keeps_the_name_the_catalog_is_bound_to():
    """While a scan rewrites the catalog table by table, rows from two runs sit side by side and can
    disagree about what an entity is called — splitting one entity's years in half. The pattern is
    derived from the table name alone, so it decides which rows are one entity; the certified
    vocabulary decides what that entity is called, because nothing rewrites the vocabulary."""
    from datetime import timedelta

    from semantic_bridge.app import one_entity_per_pattern
    from semantic_layer.models import utcnow

    def _p(name, pattern, entity, ago_hours):
        return SchemaProfile(datasource_id="d", table_name=name, table_pattern=pattern, entity=entity,
                             schema_name="dbo", scanned_at=utcnow() - timedelta(hours=ago_hours))

    old_ = _p("LG_211_ITEMS", "LG_{n0}_ITEMS", "ITEMS", 12)       # the name concepts are written against
    new_ = _p("LG_411_ITEMS", "LG_{n0}_ITEMS", "LG_ITEMS", 0)     # what the mid-flight scan called it
    view = _p("LV_411_ITEMS", "LV_{n0}_ITEMS", "LV_ITEMS", 0)

    out = one_entity_per_pattern([old_, new_, view], anchors={"LG_{n0}_ITEMS": "ITEMS"})
    assert {p.table_name: p.entity for p in out} == {
        "LG_211_ITEMS": "ITEMS", "LG_411_ITEMS": "ITEMS", "LV_411_ITEMS": "LV_ITEMS",
    }, "the certified name survives the scan; a pattern nothing is bound to keeps its own"


def test_the_join_graph_is_relabelled_with_the_entities_it_points_at():
    """İlişki kaydı yalnız hedefin ADINI tutuyor. Etiketler taşınınca grafik eski neslin adlarını
    göstermeye devam ediyor ve hiçbir yerde hata çıkmıyor: join'ler sessizce tanınmaz oluyor —
    üretimde STLINE→CLCARD ve STLINE→ITEMS için "katalogda böyle bir ilişki yok" uyarısı bu yüzden
    çıkıyordu."""
    from semantic_bridge.app import one_entity_per_pattern
    from semantic_layer.models import utcnow

    items = SchemaProfile(datasource_id="d", table_name="LG_411_ITEMS", table_pattern="LG_{n0}_ITEMS",
                          entity="LG_ITEMS", schema_name="dbo", scanned_at=utcnow())
    stline = SchemaProfile(datasource_id="d", table_name="LG_411_01_STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
                           entity="LG_STLINE", schema_name="dbo", scanned_at=utcnow(),
                           relationships=[{"column": "STOCKREF", "ref_entity": "LG_ITEMS", "ref_column": "LOGICALREF"},
                                          {"column": "PRODORDERREF", "ref_entity": "PRODORD", "ref_column": "LOGICALREF"}])
    out = one_entity_per_pattern([items, stline], anchors={"LG_{n0}_ITEMS": "ITEMS", "LG_{n0}_{n1}_STLINE": "STLINE"})
    rels = {r["column"]: r["ref_entity"] for p in out for r in (p.relationships or [])}
    assert rels["STOCKREF"] == "ITEMS", "hedef, işaret ettiği varlıkla aynı adı taşımalı"
    assert rels["PRODORDERREF"] == "PRODORD", "taranmamış bir hedefin adı uydurulmaz"


def test_an_ambiguous_old_label_is_left_alone_rather_than_guessed():
    """Aynı etiket iki desende kullanılmışsa hangisinin kastedildiği bilinemez; kaydedilmemiş bir
    ilişkiyi varsaymaktansa dokunmamak doğru."""
    from semantic_bridge.app import one_entity_per_pattern
    from semantic_layer.models import utcnow

    a = SchemaProfile(datasource_id="d", table_name="LG_411_ITEMS", table_pattern="LG_{n0}_ITEMS",
                      entity="SHARED", schema_name="dbo", scanned_at=utcnow())
    b = SchemaProfile(datasource_id="d", table_name="LV_411_ITEMS", table_pattern="LV_{n0}_ITEMS",
                      entity="SHARED", schema_name="dbo", scanned_at=utcnow())
    c = SchemaProfile(datasource_id="d", table_name="LG_411_01_STLINE", table_pattern="LG_{n0}_{n1}_STLINE",
                      entity="STLINE", schema_name="dbo", scanned_at=utcnow(),
                      relationships=[{"column": "STOCKREF", "ref_entity": "SHARED", "ref_column": "LOGICALREF"}])
    out = one_entity_per_pattern([a, b, c], anchors={"LG_{n0}_ITEMS": "ITEMS"})
    assert [r["ref_entity"] for p in out for r in (p.relationships or [])] == ["SHARED"]


def test_a_join_the_graph_records_is_not_reported_unknown_after_relabelling():
    """Uçtan uca: etiketler taşındıktan sonra bilinen join sessiz, bilinmeyen join hâlâ uyarıyor."""
    from semantic_bridge.app import one_entity_per_pattern

    items = _t("LG_ITEMS", "LG_411_ITEMS", [("LOGICALREF", "int"), ("CODE", "nvarchar(25)")])
    items.table_pattern = "LG_{n0}_ITEMS"
    stl = _t("LG_STLINE", "LG_411_01_STLINE", [("LOGICALREF", "int"), ("STOCKREF", "int"), ("SPECODE", "nvarchar(17)"), ("TOTAL", "decimal(18,2)")],
             rels=[{"column": "STOCKREF", "ref_entity": "LG_ITEMS", "ref_column": "LOGICALREF"}])
    stl.table_pattern = "LG_{n0}_{n1}_STLINE"
    profs = one_entity_per_pattern([items, stl], anchors={"LG_{n0}_ITEMS": "ITEMS", "LG_{n0}_{n1}_STLINE": "STLINE"})
    known = "SELECT SUM(s.TOTAL) FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.STOCKREF = i.LOGICALREF"
    assert not [f for f in review(known, profs) if f.kind == "UNKNOWN_JOIN"]
    odd = "SELECT SUM(s.TOTAL) FROM dbo.LG_411_01_STLINE s JOIN dbo.LG_411_ITEMS i ON s.SPECODE = i.CODE"
    assert [f.kind for f in review(odd, profs) if f.kind == "UNKNOWN_JOIN"] == ["UNKNOWN_JOIN"]


def test_the_certified_name_survives_even_when_every_old_row_is_gone():
    """After a rescan replaces every row, no profile carries the old name any more. Anchoring on the
    pattern still holds; anchoring on the name would have quietly let go."""
    from semantic_bridge.app import one_entity_per_pattern
    from semantic_layer.models import utcnow

    only_new = [SchemaProfile(datasource_id="d", table_name=n, table_pattern="LG_{n0}_ITEMS",
                              entity="LG_ITEMS", schema_name="dbo", scanned_at=utcnow())
                for n in ("LG_211_ITEMS", "LG_411_ITEMS")]
    out = one_entity_per_pattern(only_new, anchors={"LG_{n0}_ITEMS": "ITEMS"})
    assert {p.entity for p in out} == {"ITEMS"}


def test_with_nothing_certified_the_newest_label_decides():
    """A deployment with no vocabulary yet still needs one name per pattern."""
    from datetime import timedelta

    from semantic_bridge.app import one_entity_per_pattern
    from semantic_layer.models import utcnow

    a = SchemaProfile(datasource_id="d", table_name="LG_211_ITEMS", table_pattern="LG_{n0}_ITEMS",
                      entity="ITEMS", schema_name="dbo", scanned_at=utcnow() - timedelta(hours=12))
    b = SchemaProfile(datasource_id="d", table_name="LG_411_ITEMS", table_pattern="LG_{n0}_ITEMS",
                      entity="LG_ITEMS", schema_name="dbo", scanned_at=utcnow())
    assert {p.entity for p in one_entity_per_pattern([a, b], anchors={})} == {"LG_ITEMS"}


def test_a_question_this_deployment_has_nothing_about_is_refused_not_guessed(
        catalog, profiles, logo_connector, settings):
    """Two independent readings have to agree: the resolver placed nothing, and a model reading the
    shortlist says none of it is about the question. Either alone is not enough — the selector says
    NONE about questions the certified vocabulary places perfectly well, and plenty of answerable
    questions use words the resolver has never been told."""
    from fastapi.testclient import TestClient

    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm
    from semantic_layer.runtime.table_selector import TableSelector

    class _SaysNone:
        def chat(self, messages):
            return '{"decision":"NONE","tables":[]}'

    sql_llm = FakeLlm(['```sql\nSELECT 1\n```'])
    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=sql_llm)
    rt.existing.selector = TableSelector(_SaysNone())
    rt.existing.selector_mode = "on"
    client = TestClient(create_app(rt))

    r = client.post("/api/v1/ask", json={"question": "Yarın hava nasıl olacak?"}).json()
    assert r["type"] in ("NON_SQL_QUERY", "SQL_INVALID") or not r.get("sql"), r
    assert all("yalnız niyet sınıflandır" in call[0]["content"] for call in sql_llm.calls), "scope classification must never be followed by SQL for an unrelated question"


def test_a_question_the_catalog_can_place_is_not_refused_by_a_selector_saying_none(
        catalog, profiles, logo_connector, settings):
    """The resolver placed it, so NONE is overruled: the certified vocabulary knows this question."""
    from fastapi.testclient import TestClient

    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm
    from semantic_layer.runtime.table_selector import TableSelector

    class _SaysNone:
        def chat(self, messages):
            return '{"decision":"NONE","tables":[]}'

    rt = Runtime(settings, store=catalog, connector=logo_connector, llm=FakeLlm([""]))
    rt.existing.selector = TableSelector(_SaysNone())
    rt.existing.selector_mode = "on"
    client = TestClient(create_app(rt))

    r = client.post("/api/v1/ask", json={"question": "2026 toptan satış tutarı"}).json()
    assert r["type"] == "TEXT_TO_SQL" and r["rowCount"] == 1, r


def _with(profile_cols, **kw):
    return SchemaProfile(datasource_id="d", table_name="LG_411_01_INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
                         entity="INVOICE", schema_name="dbo", primary_key=["LOGICALREF"],
                         columns=[ColumnProfile(**c) for c in profile_cols], **kw)


def test_two_amounts_on_different_bases_are_not_added_together():
    """Arithmetically fine, meaningless as a figure, and nothing about the result gives it away."""
    p = _with([dict(name="LOGICALREF", data_type="int", is_primary_key=True),
               dict(name="NETTOTAL", data_type="decimal", unit="KDV dahil"),
               dict(name="TOTAL", data_type="decimal", unit="KDV hariç")])
    f = review('SELECT SUM(i."NETTOTAL" + i."TOTAL") FROM dbo.LG_411_01_INVOICE i', [p])
    assert f and f[0].kind == "MIXED_BASIS" and f[0].severity == "block"
    assert "KDV dahil" in f[0].message and "KDV hariç" in f[0].message


def test_one_basis_used_consistently_is_fine():
    p = _with([dict(name="LOGICALREF", data_type="int", is_primary_key=True),
               dict(name="NETTOTAL", data_type="decimal", unit="KDV dahil")])
    assert review('SELECT SUM(i."NETTOTAL") FROM dbo.LG_411_01_INVOICE i', [p]) == []


def test_filtering_on_a_value_that_was_never_seen_is_flagged():
    """An empty result reads as "none this month", not as a filter that could never have matched."""
    p = _with([dict(name="LOGICALREF", data_type="int", is_primary_key=True),
               dict(name="TRCODE", data_type="smallint", distinct_count=3,
                    top_values=[("7", 100), ("8", 50), ("9", 5)])])
    f = review('SELECT COUNT(*) FROM dbo.LG_411_01_INVOICE i WHERE i."TRCODE" = 99', [p])
    assert any(x.kind == "UNKNOWN_VALUE" and x.severity == "warn" for x in f)
    assert not [x for x in review('SELECT COUNT(*) FROM dbo.LG_411_01_INVOICE i WHERE i."TRCODE" = 7', [p])
                if x.kind == "UNKNOWN_VALUE"]


def test_a_column_whose_values_were_never_inventoried_says_nothing():
    """Only a complete value set can rule a value out; a partial one would refuse real data."""
    p = _with([dict(name="LOGICALREF", data_type="int", is_primary_key=True),
               dict(name="CODE", data_type="varchar(25)")])
    assert review('SELECT COUNT(*) FROM dbo.LG_411_01_INVOICE i WHERE i."CODE" = \'X\'', [p]) == []


def test_a_table_with_no_rows_at_all_is_said_out_loud():
    p = _with([dict(name="LOGICALREF", data_type="int", is_primary_key=True)], row_count=0)
    f = review("SELECT COUNT(*) FROM dbo.LG_411_01_INVOICE i", [p])
    assert any(x.kind == "EMPTY_TABLE" and x.severity == "warn" for x in f)
