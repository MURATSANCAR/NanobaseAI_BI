"""Fatura sayısı tanım birliği, iade faturası notu, «iadeleri de ekle» takibi ve Logo boş tarihleri.

Kullanıcı kararı 2026-10-01: fatura sayısı iade faturası içermez (7/8/9, iptal hariç); iade
faturası (2/3) ayrı ölçüdür ve her fatura sayısı cevabında not olarak söylenir. Canlı Eylül
2026: 13.680 satış + 120 iade = 13.800. Veri tabanı yok: sahte bağlantı üretilen SQL'i kaydeder.
"""
from datetime import date, datetime
import json
import re
from zoneinfo import ZoneInfo

import pytest

from semantic_bridge.finance_query.contracts import METRICS, ContractError
from semantic_bridge.finance_query.executor import (Executor, logo_date_entered, logo_date_text,
                                                    logo_entered_date)
from semantic_bridge.finance_query.logo_reports import execute_logo_report, validate_logo_report
from semantic_bridge.finance_query.plan_types import PeriodComparison
from semantic_bridge.finance_query.planner import (Plan, apply_scope_extension, plan_from_dict,
                                                   scope_extension)
from semantic_bridge.finance_query.result_metadata import return_invoice_note

SEPT = (("2026-09-01", "2026-10-01"),)
COLUMNS = ("CANCELLED DATE_ TRCODE LOGICALREF NETTOTAL CLIENTREF CODE DEFINITION_ SPECODE2 LINETYPE INVOICEREF "
           "STOCKREF LINENET VATMATRAH AMOUNT UINFO1 UINFO2 NAME SIGN FICHENO TRCURR TRNET FIRMNR CURTYPE CURCODE ORDFICHEREF "
           "CLOSED SHIPPEDAMOUNT UOMREF SOURCEINDEX DUEDATE DEBIT CREDIT ACCFICHEREF ACCOUNTREF").split()


class Connector:
    """Answers by SQL shape and records every statement."""

    def __init__(self, answer):
        self.answer, self.sql = answer, []

    def execute(self, sql, max_rows):
        if "L_CAPIPERIOD" in sql:
            rows = [{"FIRMNR": 411, "NR": 1, "BEGDATE": "2026-01-01", "ENDDATE": "2026-12-31"}]
        elif "INFORMATION_SCHEMA" in sql:
            tables = re.findall(r"N'([^']+)'", sql)
            rows = [{"TABLE_NAME": t, "COLUMN_NAME": c, "DATA_TYPE": "float"} for t in tables for c in COLUMNS]
        elif "COUNT_BIG(*) AS n FROM dbo.[LG_" in sql and "] m WHERE" in sql:
            given = self.answer(sql)                       # ad süzgecinin ana kayıt denetimi: testin cevabı yoksa ad var
            rows = given if given and "n" in given[0] else [{"n": 1}]
        else:
            self.sql.append(sql)
            rows = self.answer(sql)
        return list(rows[0]) if rows else [], rows, False


class Runtime:
    def __init__(self, answer):
        self.connector = Connector(answer)
        self.crm_connector = None

    def _check_data_scope(self, sql):
        return None


def invoice_answer(sql):
    if "GROUP BY" in sql and "[customer_code]" in sql:
        return [{"customer_code": "120.01", "customer_name": "A", "invoice_count": 13000},
                {"customer_code": "120.02", "customer_name": "B", "invoice_count": 680}]
    row = {}
    for metric, value in (("invoice_count", 13680), ("return_invoice_count", 120), ("invoice_count_with_returns", 13800)):
        if f"AS [{metric}]" in sql:
            row[metric] = value
    return [row]


@pytest.fixture(autouse=True)
def firms(monkeypatch):
    monkeypatch.setenv("SEMANTIC_FIRMS", "411")
    monkeypatch.delenv("SEMANTIC_EXCLUDE_CONTEXT", raising=False)


def run(plan, answer=invoice_answer):
    engine = Executor(Runtime(answer))
    rows = engine.execute(plan)
    return engine, rows, engine.rt.connector.sql


def test_invoice_count_is_sales_only_and_the_same_run_counts_returns():
    engine, rows, sql = run(Plan(("invoice_count",), (), SEPT))
    assert rows == [{"invoice_count": 13680.0}]
    main, probe = sql
    assert "f.TRCODE IN (7,8,9)" in main and "IN (2,3" not in main
    assert "f.TRCODE IN (2,3)" in probe and "[return_invoice_count]" in probe and "GROUP BY" not in probe
    assert engine.return_invoice_counts == [{"start": "2026-09-01", "end": "2026-10-01", "returnInvoiceCount": 120}]
    note = engine.notes[-1]
    assert note == "Bu dönemde 120 iade faturası var; fatura sayısına dahil edilmedi. Eklemek için ‘iadeleri de ekle’ yazabilirsiniz."
    assert "TRCODE" not in note and "2/3" not in note


def test_breakdown_note_has_one_total_with_the_same_filter_and_sale_kind():
    plan = Plan(("invoice_count",), ("customer",), SEPT, (("channel", "eq", "KURUM"),), "wholesale")
    engine, rows, sql = run(plan)
    assert len(rows) == 2
    probe = sql[-1]
    # Filter columns may group the probe; the rows are summed, breakdown columns are not read.
    assert "c.SPECODE2 COLLATE Latin1_General_CI_AI=N'KURUM'" in probe and "f.TRCODE IN (8,3)" in probe and "customer_code" not in probe
    assert engine.notes[-1].startswith("Bu dönemde seçilen koşullarla 120 iade faturası var")


def test_comparison_note_lists_each_period():
    plan = Plan(("invoice_count",), (), (("2025-09-01", "2025-10-01"), ("2026-09-01", "2026-10-01")),
                comparison=PeriodComparison("difference", "invoice_count", "fark"))
    engine = Executor(Runtime(invoice_answer))
    engine.partitions = lambda a, b: [(a, b, "411", "01")]
    engine.verify_schema = lambda tables, source: {(t.lower(), c.lower()): "float" for t in tables for c in COLUMNS}
    engine.execute(plan)
    assert "01.09.2025–30.09.2025: 120; 01.09.2026–30.09.2026: 120" in engine.notes[-1]


def test_return_metrics_follow_the_contract():
    assert set(METRICS) >= {"invoice_count", "return_invoice_count", "invoice_count_with_returns"}
    assert "7,8,9" in METRICS["invoice_count"].expression and "2,3)" in METRICS["return_invoice_count"].expression
    retail = Plan(("return_invoice_count",), (), SEPT, sale_kind="retail")
    engine, _, sql = run(retail)
    assert "f.TRCODE IN (2,3)" in sql[0] and "f.TRCODE IN (7,2)" in sql[0]
    assert len(sql) == 1 and not engine.return_invoice_counts  # explicit return count: no extra note probe


@pytest.mark.parametrize("question", ["iadeleri de ekle", "İade faturalarını dahil et", "iadelerle birlikte",
                                      "iadeler dahil olsun", "iade faturalarını da say", "fatura sayısını iadelerle beraber göster"])
def test_scope_extension_recognises_include_returns(question):
    assert scope_extension(question, date(2026, 10, 1)) == {"include_returns": True}


@pytest.mark.parametrize("question", ["iadeler hariç", "iadeleri katma", "iadeleri eklemeden göster", "iadeleri dahil etmeyin",
                                      "Eylül 2026 iadeler dahil fatura sayısı", "iadelerle birlikte net satış",
                                      "bunu müşteri bazında göster", "iade tutarını ekle", "iade faturası sayısı nedir",
                                      "kaç iade faturası var"])
def test_scope_extension_ignores_other_questions(question):
    assert scope_extension(question, date(2026, 10, 1)) is None


def test_include_returns_keeps_the_previous_plan_and_adds_three_counts():
    previous = {"question": "Eylül faturaları müşteri bazında", "plan": json.loads(json.dumps(
        Plan(("invoice_count", "invoice_amount"), ("customer",), SEPT, (("channel", "eq", "KURUM"),), limit=5,
             order_by="invoice_count", notes=("not",)).to_dict()))}
    plan = apply_scope_extension(previous, {"include_returns": True})
    assert plan.metrics == ("invoice_count", "return_invoice_count", "invoice_count_with_returns", "invoice_amount")
    assert (plan.dimensions, plan.periods, plan.filters, plan.limit, plan.order_by) == (
        ("customer",), SEPT, (("channel", "eq", "KURUM"),), 5, "invoice_count")
    assert plan.notes[0] == "not" and "iade faturaları eklenerek" in plan.notes[-1]
    assert apply_scope_extension({"plan": plan.to_dict()}, {"include_returns": True}) == plan


def test_extended_plan_reads_all_codes_and_needs_no_note():
    plan = apply_scope_extension({"plan": Plan(("invoice_count",), (), SEPT).to_dict()}, {"include_returns": True})
    engine, rows, sql = run(plan)
    assert rows == [{"invoice_count": 13680.0, "return_invoice_count": 120.0, "invoice_count_with_returns": 13800.0}]
    assert len(sql) == 1 and "f.TRCODE IN (2,3,7,8,9)" in sql[0]
    assert not any("iadeleri de ekle" in n for n in engine.notes)


def test_include_returns_on_a_period_comparison_compares_the_total():
    previous = Plan(("invoice_count",), (), (("2025-09-01", "2025-10-01"), SEPT[0]),
                    comparison=PeriodComparison("difference", "invoice_count", "fark")).to_dict()
    plan = apply_scope_extension(previous, {"include_returns": True})
    assert plan.metrics == ("invoice_count_with_returns",) and plan.comparison.metric == "invoice_count_with_returns"


@pytest.mark.parametrize("previous", [None, {}, {"plan": Plan(("net_sales",), (), SEPT).to_dict()},
                                      {"plan": Plan((), (), SEPT, logo_report={"mode": "stock"}).to_dict()}])
def test_include_returns_without_an_invoice_count_asks(previous):
    with pytest.raises(ContractError) as error:
        apply_scope_extension(previous, {"include_returns": True})
    assert error.value.code == "NEEDS_CLARIFICATION" and str(error.value).startswith("Hangi fatura sayısına ekleyeyim?")


def test_plan_from_dict_survives_json_round_trip():
    plan = Plan(("invoice_count",), ("month",), SEPT, comparison=None, sections=(Plan(("invoice_count",), (), SEPT, section_title="A"),))
    assert plan_from_dict(json.loads(json.dumps(plan.to_dict()))) == plan


def test_return_note_wording():
    assert return_invoice_note([("2026-09-01", "2026-10-01", 0)]) == "Bu dönemde iade faturası yok; fatura sayısı yalnız satış faturalarıdır."
    assert "1.234 iade faturası" in return_invoice_note([("2026-09-01", "2026-10-01", 1234)])


# --- Logo boş tarih: 1899-12-30 ve 1900-01-01 "girilmemiş" ---

def test_logo_empty_dates_are_not_entered():
    assert logo_date_entered("O.DUEDATE") == "O.DUEDATE>='19010101'"
    assert logo_date_text("O.DUEDATE") == "CASE WHEN O.DUEDATE>='19010101' THEN CONVERT(varchar(10),O.DUEDATE,23) END"
    for empty in (None, "", "1899-12-30", "1900-01-01", datetime(1900, 1, 1), date(1899, 12, 30), "1900-01-01 00:00:00"):
        assert logo_entered_date(empty) is None
    assert logo_entered_date(datetime(2026, 9, 1, 0, 0)) == date(2026, 9, 1)
    assert logo_entered_date("1901-01-01") == date(1901, 1, 1)


def test_open_orders_never_age_an_unentered_due_date():
    today = datetime.now(ZoneInfo("Europe/Istanbul")).date()

    def answer(sql):
        if "missing_headers" in sql:
            return [{"missing_headers": 0}]
        base = dict(order_number="S1", order_date="2026-09-01", book_code="K", book_name="Kitap", customer_code="120.01",
                    customer_name="A", warehouse_no=0, unit_ref=1, unit_factor_1=1, unit_factor_2=1, ordered_quantity=10,
                    shipped_quantity=0, remaining_quantity=10, line_net_amount=100)
        return [{**base, "order_line_ref": 1, "due_date": "1900-01-01"}, {**base, "order_line_ref": 2, "due_date": None},
                {**base, "order_line_ref": 3, "due_date": "2026-09-01"}]

    engine = Executor(Runtime(answer))
    result = execute_logo_report(engine, {"mode": "open_orders", "as_of": str(today), "overdue_only": True})
    sql = engine.rt.connector.sql[-1]
    assert "O.DUEDATE>='19010101'" in sql and "19000101" not in sql
    by_ref = {r["order_line_ref"]: r for r in result["records"]}
    assert by_ref[1]["due_date"] is None and by_ref[1]["overdue_days"] is None
    assert by_ref[2]["overdue_days"] is None
    assert by_ref[3]["overdue_days"] == (today - date(2026, 9, 1)).days
    assert result["notes"][0].startswith("2 sipariş satırında vade tarihi girilmemiş")


# --- Rapor yolları aynı tanımda ---

def currency_answer(sql):
    if "L_CURRENCYLIST" in sql:
        return [{"currency_id": 0, "currency_code": "TL"}]
    return [{"currency_id": 0, "invoice_count": 13680, "return_invoice_count": 120, "local_invoice_net": 1000,
             "original_invoice_net": 1000, "unverified_original_amounts": 0}]


def test_currency_report_counts_sales_invoices_and_returns_separately():
    engine = Executor(Runtime(currency_answer))
    spec = {"mode": "currencies", "start": "2026-09-01", "end": "2026-10-01"}
    result = execute_logo_report(engine, spec)
    sql = engine.rt.connector.sql[-1]
    assert "SUM(CASE WHEN I.TRCODE IN (7,8,9) THEN 1 ELSE 0 END) invoice_count" in sql
    assert "SUM(CASE WHEN I.TRCODE IN (2,3) THEN 1 ELSE 0 END) return_invoice_count" in sql and "COUNT_BIG(*)" not in sql
    assert result["records"][0]["invoice_count"] == 13680 and result["records"][0]["return_invoice_count"] == 120
    assert "120 iade faturası var" in result["notes"][-1]
    extended = execute_logo_report(Executor(Runtime(currency_answer)), {**spec, "include_returns": True})
    assert extended["records"][0]["invoice_count_with_returns"] == 13800 and not extended["return_invoice_counts"]


def test_invoice_statistics_note_and_union_on_request():
    def answer(sql):
        if "return_invoice_count" in sql:
            return [{"customer_code": "120.01", "customer_name": "A", "return_invoice_count": 2},
                    {"customer_code": "120.09", "customer_name": "Yalnız iade", "return_invoice_count": 1}]
        return [{"invoice_id": 1, "invoice_number": "F1", "invoice_date": "2026-09-02", "customer_code": "120.01",
                 "customer_name": "A", "invoice_total": 100}]
    spec = {"mode": "invoice_statistics", "start": "2026-09-01", "end": "2026-10-01"}
    engine = Executor(Runtime(answer))
    plain = execute_logo_report(engine, spec)
    assert "i.TRCODE IN (2,3)" in engine.rt.connector.sql[-1]
    assert [r["customer_code"] for r in plain["records"]] == ["120.01"] and "return_invoice_count" not in plain["output_fields"]
    assert "3 iade faturası var" in plain["notes"][-1]
    extended = execute_logo_report(Executor(Runtime(answer)), {**spec, "include_returns": True})
    rows = {r["customer_code"]: r for r in extended["records"]}
    assert rows["120.01"]["invoice_count_with_returns"] == 2 + 1
    assert rows["120.09"]["invoice_count"] == 0 and rows["120.09"]["invoice_mean"] is None


def test_include_returns_is_not_a_model_field_and_only_for_invoice_counts():
    from semantic_bridge.finance_query.logo_reports import LOGO_REPORT_SCHEMA
    assert "include_returns" not in LOGO_REPORT_SCHEMA["properties"]
    with pytest.raises(ContractError):
        validate_logo_report({"mode": "stock", "as_of": "2026-09-30", "include_returns": True})


# Kullanıcı kararı 2026-10-01: satış tutarı KDV matrahı (fatura geneli iskonto dahil), dönem fatura tarihi.
def sales_answer(sql):
    return [{"net_sales": 1, "sales_amount": 1, "return_amount": 0, "month": "2026-09"}]


def test_sales_amounts_use_the_vat_base_and_the_invoice_date():
    engine, rows, sql = run(Plan(("net_sales", "sales_amount", "return_amount"), ("month",), SEPT), sales_answer)
    sales = [s for s in sql if "_STLINE" in s and "611%" not in s]
    assert sales, sql
    for s in sales:
        assert "VATMATRAH" in s and "LINENET" not in s
        assert "JOIN dbo.[LG_411_01_INVOICE] h ON h.LOGICALREF=f.INVOICEREF" in s and "h.CANCELLED=0" in s
        assert "h.DATE_>='2026-09-01'" in s and "h.DATE_<'2026-10-01'" in s and "f.DATE_" not in s
        assert "CONVERT(varchar(7),h.DATE_,23)" in s


def test_sales_metric_definitions_name_the_basis():
    for m in ("net_sales", "sales_amount", "return_amount"):
        assert "VATMATRAH" in METRICS[m].expression and "LINENET" not in METRICS[m].expression
        assert "fatura tarihi" in METRICS[m].definition


# 2026-10-01 FC23: kartı olan ama kaynakta yazarı boş ürün (kılavuz, dergi) kapsam açığı değildir;
# kartı olmayan / aktif olmayan kart açık kalır.
def book_sales(sql):
    return [{"book_code": "K1", "book_name": "Roman", "sales_amount": 10},
            {"book_code": "K2", "book_name": "Kılavuz", "sales_amount": 5},
            {"book_code": "K3", "book_name": "Pasif kartlı", "sales_amount": 7}]


def test_authorless_product_with_a_card_is_a_note_not_a_gap(monkeypatch):
    monkeypatch.setattr(Executor, "crm_dimension_books", lambda self, plan: {
        "k1": {"author": "Yazar A"}, "k2": {"author": None}, "k3": {"author": "Yazar C"}})
    engine = Executor(Runtime(book_sales))
    engine.execute(Plan(("sales_amount",), ("book", "author"), SEPT))
    assert engine.coverage_complete
    assert any("kaynakta yazar alanı boş" in n for n in engine.notes)


def test_sale_without_an_active_card_stays_a_gap(monkeypatch):
    monkeypatch.setattr(Executor, "crm_dimension_books", lambda self, plan: {
        "k1": {"author": "Yazar A"}, "k2": {"author": None}})
    engine = Executor(Runtime(book_sales))
    engine.execute(Plan(("sales_amount",), ("book", "author"), SEPT))
    assert not engine.coverage_complete
    assert any("aktif CRM kitap eşleşmesi yok" in n for n in engine.notes)


# Karar 2026-10-01: muhasebe net satışı defterden (600–602 − 610–612), yalnız dönem kırılımı; satış tutarı cevabında
# ayrı faturayla verilen iskonto fiyat farkı (hizmet kartı 611…) not olarak.
def ledger_answer(sql):
    return [{"month": "2026-09", "accounting_net_sales": 250.0}] if "EMFLINE" in sql else []


def test_accounting_net_sales_reads_the_ledger_without_closing_and_transfer_fiches():
    engine, rows, sql = run(Plan(("accounting_net_sales",), ("month",), SEPT), ledger_answer)
    assert rows == [{"month": "2026-09", "accounting_net_sales": 250.0}]
    ledger = [s for s in sql if "EMFLINE" in s]
    assert len(ledger) == 1
    s = ledger[0]
    assert "SUM(f.CREDIT-f.DEBIT)" in s and "LEFT(a.CODE,3) IN ('600','601','602','610','611','612')" in s
    assert "JOIN dbo.[LG_411_01_EMFICHE] h ON h.LOGICALREF=f.ACCFICHEREF" in s and "h.CANCELLED=0" in s
    assert "NOT EXISTS" in s and "'690'" in s and "'711'" in s, "kapanış ve yansıtma fişleri M45 kuralıyla hariç"
    assert "f.DATE_>='2026-09-01'" in s and "CONVERT(varchar(7),f.DATE_,23)" in s


class NoModel:
    def complete(self, *a, **kw):
        raise AssertionError("bu testte model çağrılmaz")


@pytest.mark.parametrize("question,data,expect", [
    ("Eylül 2026 kanallara göre muhasebe net satışı", {"metrics": ["accounting_net_sales"], "dimensions": ["channel"]}, "yalnız dönem"),
    ("Eylül 2026 muhasebe net satışı ve net satış", {"metrics": ["accounting_net_sales", "net_sales"], "dimensions": []}, "birleştirilemez"),
    ("Eylül 2026 gelir tablosu net satışı", {"metrics": ["net_sales"], "dimensions": []}, "accounting_net_sales"),
])
def test_accounting_net_sales_plan_rules(question, data, expect):
    from semantic_bridge.finance_query.planner import build
    with pytest.raises(ContractError) as e:
        build(question, NoModel(), None, [], _data=data)
    assert expect in str(e.value)


def price_answer(sql):
    if "611%" in sql:
        return [{"discount": 1234.5}]
    return [{"channel": "KITAPCI", "net_sales": 100.0, "sold_quantity": 5.0, "_unverified_quantity_units": 0}]


def test_sales_answer_carries_the_separately_invoiced_price_difference():
    engine, rows, sql = run(Plan(("net_sales",), ("channel",), SEPT, filters=(("channel", "eq", "KITAPCI"),)), price_answer)
    note = [s for s in sql if "611%" in s]
    assert len(note) == 1 and "f.LINETYPE=4" in note[0] and "h.DATE_>='2026-09-01'" in note[0] and "c.SPECODE2 COLLATE Latin1_General_CI_AI=N'KITAPCI'" in note[0]
    assert any("iskonto fiyat farkı 1.234,50 TL" in n for n in engine.notes)
    assert engine.source_periods == [{"start": "2026-09-01", "end": "2026-10-01", "sourceCode": "411", "periodCode": "01"}], \
        "not okuması kapsamı ikinci kez yazmaz"
    engine, _, _ = run(Plan(("sold_quantity",), ("channel",), SEPT), price_answer)
    assert not any("fiyat farkı" in n for n in engine.notes), "adet cevabında not yok"


def test_a_name_with_a_turkish_suffix_is_found_by_its_stem_and_an_unknown_name_is_not_zero():
    from semantic_bridge.finance_query.executor import name_stems
    assert name_stems("kitapyurduna")[0] == "kitapyurdu"
    assert name_stems("D&R'dan")[0] == "D&R"

    def master(sql):
        if "] m WHERE" in sql:
            return [{"n": 1 if "%kitapyurdu%" in sql else 0}]
        return [{"invoice_amount": 5}]
    engine, rows, sql = run(Plan(("invoice_amount",), (), SEPT, filters=(("customer", "eq", "kitapyurduna"),)), master)
    main = next(s for s in sql if "AS [invoice_amount]" in s)
    assert "LIKE N'%kitapyurdu%'" in main and any("«kitapyurdu» içeren ad olarak arandı" in n for n in engine.notes)
    with pytest.raises(ContractError, match="bulunamadı"):
        run(Plan(("invoice_amount",), (), SEPT, filters=(("customer", "eq", "olmayanfirma"),)), lambda sql: [{"n": 0}])
