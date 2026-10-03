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
           "STOCKREF VATMATRAH AMOUNT UINFO1 UINFO2 NAME SIGN EINVOICE PROFILEID ESTATUS VATEXCEPTCODE "
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
