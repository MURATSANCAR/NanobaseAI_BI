"""The vendor dictionary has to reach the catalogue, or a Logo scan is 8.900 bare identifiers.

Logo declares no foreign keys and writes no extended properties: `INFORMATION_SCHEMA` gives back
column names and nothing else. What `CLIENTREF` points at and what `CARDTYPE = 12` means live only
in the workbook Logo ships, imported by backend/scripts/import_logo_ldds.py.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent
_REPO = _ROOT.parents[1]
sys.path.insert(0, str(_ROOT))


def _mssql_module():
    """Load scanner.mssql without scanner/__init__, which pulls in the postgres driver."""
    spec = importlib.util.spec_from_file_location("_mssql_dict", _ROOT / "scanner" / "mssql.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _mssql_module()
DICT_PATH = _REPO / "configs" / "schemas" / "logo-ldds.json"


def test_the_dictionary_is_present_and_covers_the_schema():
    data = json.loads(DICT_PATH.read_text(encoding="utf-8"))
    assert data["table_count"] > 300, "the workbook documents ~310 tables"
    assert data["column_count"] > 8000
    assert data["relation_count"] > 1000, "the join graph is the part the database does not declare"


def test_one_dictionary_entry_answers_for_every_copy_of_a_table():
    """A firm's tables and each period's tables are separate objects in SQL Server and the same
    table in the dictionary. That mapping is the whole reason one import covers the database."""
    assert m._logo_base("LG_411_01_STLINE") == "STLINE"
    assert m._logo_base("LG_411_ITEMS") == "ITEMS"
    assert m._logo_base("L_CAPIFIRM") == "CAPIFIRM"
    assert m._logo_parts("LG_411_01_INVOICE") == ("INVOICE", "411", "01")
    assert m._logo_parts("LG_411_CLCARD") == ("CLCARD", "411", None)


def test_a_coded_column_arrives_with_its_codes():
    """`CARDTYPE` as "kart türü" cannot be filtered on; `12 = Finished Good` can. This is the single
    biggest thing the dictionary adds, and it has to survive into the column description."""
    desc = m._col_desc("CARDTYPE", "LG_411_ITEMS")
    assert "1=" in desc and "12=" in desc, desc
    assert "Finished" in desc or "Mamul" in desc, desc


def test_a_table_nobody_wrote_about_still_gets_described():
    """26 tables had hand-written Turkish. The other ~285 had nothing at all."""
    assert m._table_desc("LG_411_PRCARDS"), "promotion cards were undescribed before the import"
    assert m._table_desc("LG_411_01_PRDCOST")


def test_hand_written_turkish_still_wins_where_it_exists():
    """The written entries carry the filters an answer needs (CANCELLED=0, which TRCODE is a sale);
    the dictionary's one-line English does not replace that."""
    desc = m._table_desc("LG_411_01_INVOICE")
    assert "TRCODE" in desc and "CANCELLED" in desc, desc


def test_the_join_graph_crosses_firm_and_period_correctly():
    """A period table's CLIENTREF points at the firm's cari card, not a period one — getting this
    wrong produces SQL that references a table that does not exist."""
    present = {
        "LG_411_01_STLINE", "LG_411_ITEMS", "LG_411_CLCARD", "LG_411_01_INVOICE",
        "LG_411_01_STFICHE", "LG_411_SLSMAN", "LG_411_UNITSETL",
    }
    links = {l["column"]: l["table"] for l in m._dictionary_links(
        "LG_411_01_STLINE",
        ["STOCKREF", "CLIENTREF", "INVOICEREF", "STFICHEREF", "SALESMANREF", "UOMREF", "AMOUNT"],
        present,
    )}
    assert links["CLIENTREF"] == "LG_411_CLCARD", "firm-level target took a period prefix"
    assert links["STOCKREF"] == "LG_411_ITEMS"
    assert links["INVOICEREF"] == "LG_411_01_INVOICE", "period-level target lost its period"
    assert links["STFICHEREF"] == "LG_411_01_STFICHE"
    assert links["SALESMANREF"] == "LG_411_SLSMAN", "the workbook calls SLSMAN global; it ships per firm"
    assert "AMOUNT" not in links, "a plain measure is not a join"


def test_a_join_to_a_table_that_was_not_scanned_is_not_invented():
    """Half the dictionary's targets are tables a narrowed scope never scanned. A relationship
    pointing at one of them would send generated SQL at a table nobody catalogued."""
    links = m._dictionary_links(
        "LG_411_01_STLINE", ["STOCKREF", "CLIENTREF"], {"LG_411_01_STLINE", "LG_411_ITEMS"}
    )
    assert [l["column"] for l in links] == ["STOCKREF"]


def test_a_non_logo_table_is_left_alone():
    assert m._dictionary_links("sales_orders", ["customer_id"], {"customers"}) == []
    assert m._table_desc("sales_orders") == ""


def test_the_key_the_database_never_declares_is_supplied():
    """Logo enforces uniqueness in the application, so `sys.key_constraints` is empty for every one
    of its tables and a scan reports a schema in which no row is identifiable. The dictionary's
    unique index on LOGICALREF is what every `*REF` column in the database points at."""
    assert m._dictionary_key("LG_411_01_STLINE", ["LOGICALREF", "STOCKREF", "AMOUNT"]) == ["LOGICALREF"]
    assert m._dictionary_key("LG_411_CLCARD", ["LOGICALREF", "CODE"]) == ["LOGICALREF"]
    assert m._dictionary_key("LG_411_01_STLINE", ["STOCKREF", "AMOUNT"]) == [], "a key must be columns the scan found"
    assert m._dictionary_key("sales_orders", ["id"]) == []


def test_turkish_reaches_the_description():
    """Questions arrive in Turkish. A table described only as "Item Transactions" is text no Turkish
    question matches, and a code labelled "Discount" is not what someone asking for indirim typed."""
    # STLINE has a hand-written entry, which still wins; these are two of the ~285 that never did.
    assert "Banka fişleri" in m._table_desc("LG_411_01_BNFICHE")
    assert "Bank Vouchers" in m._table_desc("LG_411_01_BNFICHE"), "the English is what reads like BNFICHE"
    assert "İndirim" in m._col_desc("LINETYPE", "LG_411_01_STLINE")


def test_a_table_only_the_structure_document_knows_is_described():
    """The workbook omits twenty tables the document covers — the ones a question about a customer's
    city or a day's exchange rate lands on."""
    assert m._table_desc("LG_411_CITY")
    assert m._table_desc("L_DAILYEXCHANGES")
