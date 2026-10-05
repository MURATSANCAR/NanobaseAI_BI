"""Logo kodlu kırılım ve süzgeçler (logo_codes.CODED): belge türü, e-Fatura senaryosu, e-belge durumu,
KDV istisnası, cari e-Fatura mükellefliği ve şahıs/şirket.

Kodların anlamı 2026-10-03'te canlı veriyle doğrulandı (docs/analiz/kolon-eslestirme/). Veri tabanı
yok: sahte bağlantı üretilen SQL'i kaydeder; sınanan, kodun doğru kolona ve doğru kayıt düzeyine gitmesi.
"""
import re

import pytest

from semantic_bridge.finance_query.contracts import ContractError
from semantic_bridge.finance_query.executor import Executor
from semantic_bridge.finance_query.logo_codes import CODED
from semantic_bridge.finance_query.planner import Plan

SEPT = (("2026-09-01", "2026-10-01"),)
COLUMNS = ("CANCELLED DATE_ TRCODE LOGICALREF NETTOTAL CLIENTREF CODE DEFINITION_ SPECODE2 LINETYPE INVOICEREF "
           "STOCKREF VATMATRAH AMOUNT UINFO1 UINFO2 NAME SIGN EINVOICE PROFILEID EINVOICETYP ESTATUS VATEXCEPTCODE "
           "ACCEPTEINV ISPERSCOMP").split()


class Connector:
    def __init__(self):
        self.sql = []

    def execute(self, sql, max_rows):
        if "L_CAPIPERIOD" in sql:
            rows = [{"FIRMNR": 411, "NR": 1, "BEGDATE": "2026-01-01", "ENDDATE": "2026-12-31"}]
        elif "INFORMATION_SCHEMA" in sql:
            tables = re.findall(r"N'([^']+)'", sql)
            rows = [{"TABLE_NAME": t, "COLUMN_NAME": c, "DATA_TYPE": "float"} for t in tables for c in COLUMNS]
        else:
            self.sql.append(sql)
            rows = [{"sales_amount": 10, "invoice_count": 3, "return_invoice_count": 1, "collections": 5}]
        return list(rows[0]) if rows else [], rows, False


class Runtime:
    def __init__(self):
        self.connector, self.crm_connector = Connector(), None

    def _check_data_scope(self, sql):
        return None


@pytest.fixture(autouse=True)
def firms(monkeypatch):
    monkeypatch.setenv("SEMANTIC_FIRMS", "411")
    monkeypatch.delenv("SEMANTIC_EXCLUDE_CONTEXT", raising=False)


def run(plan):
    engine = Executor(Runtime())
    engine.execute(plan)
    return engine, [s for s in engine.rt.connector.sql if "LG_411" in s]


def main_sql(sql, table):
    return next(s for s in sql if f"FROM dbo.[{table}] f" in s)


def test_sales_by_document_type_reads_the_invoice_header():
    _, sql = run(Plan(("sales_amount",), ("e_document",), SEPT))
    s = main_sql(sql, "LG_411_01_STLINE")
    assert "WHEN h.EINVOICE=1 THEN N'e-Fatura'" in s and "AS [e_document]" in s
    assert "GROUP BY" in s and "CASE WHEN h.EINVOICE=0" in s.split("GROUP BY")[1]


def test_e_archive_filter_takes_both_codes_that_mean_e_archive():
    _, sql = run(Plan(("invoice_count",), (), SEPT, filters=(("e_document", "eq", "e-Arşiv"),)))
    assert "f.EINVOICE IN (2,3)" in main_sql(sql, "LG_411_01_INVOICE")


def test_vat_exemption_is_a_line_code_in_sales_and_a_header_code_in_invoices():
    _, sql = run(Plan(("sales_amount",), (), SEPT, filters=(("vat_exemption", "contains", "basılı kitap"),)))
    assert "LTRIM(RTRIM(ISNULL(f.VATEXCEPTCODE,''))) IN (N'335')" in main_sql(sql, "LG_411_01_STLINE")
    _, sql = run(Plan(("invoice_count",), ("vat_exemption",), SEPT))
    assert "THEN N'Basılı kitap ve süreli yayın teslimi (335)'" in main_sql(sql, "LG_411_01_INVOICE")


def test_negated_customer_flag_is_not_swallowed_by_its_positive_word():
    _, sql = run(Plan(("invoice_count",), (), SEPT, filters=(("customer_einvoice_user", "contains", "e-Fatura mükellefi değil"),)))
    s = main_sql(sql, "LG_411_01_INVOICE")
    assert "c.ACCEPTEINV IN (0)" in s and "LEFT JOIN dbo.[LG_411_CLCARD] c" in s


def test_customer_flags_work_on_collections_but_invoice_codes_do_not():
    _, sql = run(Plan(("collections",), ("customer_legal_form",), SEPT))
    assert "WHEN c.ISPERSCOMP=1 THEN N'Şahıs'" in main_sql(sql, "LG_411_01_CLFLINE")
    with pytest.raises(ContractError):
        run(Plan(("collections",), ("e_document",), SEPT))


@pytest.mark.parametrize("value", ["iade edildi", "harici yollardan iptal edildi", "onaylanmış gibi"])
def test_unverified_or_ambiguous_words_are_refused_not_guessed(value):
    with pytest.raises(ContractError):
        run(Plan(("invoice_count",), (), SEPT, filters=(("einvoice_status", "eq", value),)))


def test_labels_with_apostrophes_are_valid_sql_and_unknown_codes_show_as_other():
    expr = CODED["einvoice_status"].expression("f")
    assert "N'GİB''e gönderilemedi'" in expr and "ELSE N'Diğer durum (' + CAST(f.ESTATUS" in expr


def test_price_difference_note_does_not_claim_a_coded_filter_it_cannot_apply():
    engine, sql = run(Plan(("sales_amount",), (), SEPT, filters=(("e_document", "eq", "e-Fatura"),)))
    assert not any("611%" in s for s in sql)


class Review:
    """Plan denetimini onaylar; başka model çağrısı olmaz."""

    def complete(self, messages, **kw):
        assert kw["body"]["response_format"]["json_schema"]["name"] == "finance_review"
        return {"message": {"content": '{"ok": true, "missing": []}'}, "finish_reason": "stop"}


def plan_data(metric, filters):
    return {"metrics": [metric], "dimensions": [], "sale_kind": "all", "filters": filters, "limit": None,
            "order_by": None, "descending": True, "derived": [], "having": [], "comparison": None, "crm": None,
            "logo_report": None, "crm_report": None, "relational_query": None, "analytics": [], "sections": [],
            "gaps": [], "coverage": [], "uncovered": [], "clarification": ""}


def test_model_may_word_a_coded_value_its_own_way_when_the_question_names_the_code():
    from semantic_bridge.finance_query.planner import build
    f = [{"dimension": "customer_einvoice_user", "op": "eq", "value": "Evet"}]
    plan = build("Bu yıl e-fatura mükellefi müşterilere satışımız ne kadar?", Review(), _data=plan_data("net_sales", f))
    assert plan.filters == (("customer_einvoice_user", "eq", "Evet"),)
    with pytest.raises(ContractError, match="soruda bulunamadı"):
        build("Bu yıl müşterilere satışımız ne kadar?", Review(), _data=plan_data("net_sales", f))


def test_document_codes_do_not_reach_payments_from_the_planner():
    from semantic_bridge.finance_query.planner import build
    f = [{"dimension": "e_document", "op": "eq", "value": "e-Arşiv"}]
    with pytest.raises(ContractError, match="Ödeme hareketlerinde"):
        build("2026 e-arşiv tahsilatları", Review(), _data=plan_data("collections", f))


def test_a_coded_filter_reports_the_cancelled_invoices_it_left_out():
    class Cancelled(Connector):
        def execute(self, sql, max_rows):
            if "f.CANCELLED=1" in sql and "COUNT_BIG" in sql:
                self.sql.append(sql)
                return ["n"], [{"n": 2}], False
            return super().execute(sql, max_rows)

    rt = Runtime()
    rt.connector = Cancelled()
    engine = Executor(rt)
    engine.execute(Plan(("invoice_count",), ("einvoice_status",), SEPT, filters=(("einvoice_status", "eq", "Reddedildi"),)))
    probe = next(s for s in rt.connector.sql if "f.CANCELLED=1" in s)
    assert "f.ESTATUS IN (13)" in probe and "f.TRCODE IN (7,8,9)" in probe
    assert any("2 satış faturası iptal edilmiş" in n for n in engine.notes)


@pytest.mark.parametrize("op", ["eq", "contains"])
@pytest.mark.parametrize("value,codes", [("e-fatura mükellefi olmayan", {0}), ("e-Fatura mükellefi", {1}),
                                         ("mükellefi olmayan müşteriler", {0}), ("e-fatura mükellefi müşteriler", {1})])
def test_a_negated_phrase_is_not_read_as_its_positive_part(op, value, codes):
    assert CODED["customer_einvoice_user"].codes_for(op, value) == codes


def test_withholding_invoices_are_a_header_code_not_the_line_vat_exemption():
    _, sql = run(Plan(("invoice_count",), (), SEPT, filters=(("einvoice_type", "contains", "tevkifatlı faturalar"),)))
    assert "f.EINVOICETYP IN (4)" in main_sql(sql, "LG_411_01_INVOICE")
    _, sql = run(Plan(("sales_amount",), ("einvoice_type",), SEPT))
    assert "WHEN h.EINVOICETYP=2 THEN N'İstisna'" in main_sql(sql, "LG_411_01_STLINE")


def test_retail_against_wholesale_is_a_breakdown_that_nets_each_kind_with_its_own_returns():
    _, sql = run(Plan(("sales_amount",), ("sale_type",), SEPT))
    s = main_sql(sql, "LG_411_01_STLINE")
    assert "WHEN f.TRCODE=7 THEN N'Perakende' WHEN f.TRCODE=2 THEN N'Perakende'" in s
    assert "GROUP BY CASE WHEN f.TRCODE=7" in s
