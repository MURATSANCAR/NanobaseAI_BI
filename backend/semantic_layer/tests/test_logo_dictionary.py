"""A Logo database says nothing about itself; the vendor's dictionary has to say it instead.

Logo creates no foreign keys and writes no extended properties. Profiling one without the dictionary
produces a catalog of identifiers with an empty join graph — which is what the customer was looking
at when they said tables and meanings were missing.
"""

from __future__ import annotations

import pytest

from semantic_layer.profiler import logo_dictionary as ld
from semantic_layer.profiler.connectors import MSSQLConnector

FIRM = ["LG_411_ITEMS", "LG_411_CLCARD", "LG_411_SLSMAN", "LG_411_UNITSETL", "LG_411_EMUHACC"]
PERIOD = ["LG_411_01_INVOICE", "LG_411_01_STLINE", "LG_411_01_STFICHE", "LG_411_01_ORFICHE", "LG_411_01_ORFLINE"]
LOGO_TABLES = FIRM + PERIOD


def test_the_dictionary_is_shipped_with_the_repo():
    assert ld.dictionary(), f"missing {ld.dictionary_path()} — run backend/scripts/import_logo_ldds.py"
    assert ld.dictionary()["table_count"] > 300


@pytest.mark.parametrize(
    "physical,expected",
    [
        ("LG_411_01_STLINE", ("STLINE", "411", "01")),
        ("LG_411_ITEMS", ("ITEMS", "411", None)),
        ("L_CAPIFIRM", ("CAPIFIRM", None, None)),
        ("sales_orders", ("SALES_ORDERS", None, None)),
    ],
)
def test_a_physical_name_reduces_to_the_table_the_dictionary_names(physical, expected):
    assert ld.parts(physical) == expected


def test_a_coded_column_arrives_with_what_its_codes_mean():
    """`LINETYPE` as "line type" is unusable; `0=Material, 2=Discount` is the difference between
    summing the goods on an invoice and summing the goods plus the discount lines."""
    desc = ld.column_description("LG_411_01_STLINE", "LINETYPE")
    assert "0=" in desc and "2=" in desc, desc


def test_the_join_graph_crosses_firm_and_period():
    fks = {(f["table"], f["column"]): f["ref_table"] for f in ld.foreign_keys(LOGO_TABLES)}
    assert fks[("LG_411_01_STLINE", "CLIENTREF")] == "LG_411_CLCARD"
    assert fks[("LG_411_01_STLINE", "INVOICEREF")] == "LG_411_01_INVOICE"
    assert fks[("LG_411_01_STLINE", "STOCKREF")] == "LG_411_ITEMS"
    assert fks[("LG_411_01_ORFLINE", "ORDFICHEREF")] == "LG_411_01_ORFICHE"


def test_a_target_that_was_not_scanned_is_not_invented():
    """STLINE points at seventy tables. Scanned on its own, the only joins it can honestly have are
    the ones back to itself — a relationship naming a table nobody catalogued would send generated
    SQL at a table that is not in the schema."""
    fks = ld.foreign_keys(["LG_411_01_STLINE"])
    assert {f["ref_table"] for f in fks} == {"LG_411_01_STLINE"}


def test_a_source_that_is_not_logo_is_left_alone():
    assert not ld.is_logo_schema(["orders", "order_items", "customers", "products"])
    assert ld.descriptions(["orders", "customers"]) == {}
    assert ld.foreign_keys(["orders", "customers"]) == []


class _Logo(MSSQLConnector):
    """A Logo source as the driver actually finds it: no extended properties, no foreign keys."""

    def __init__(self):
        super().__init__({"host": "h", "database": "d", "user": "u", "password": "p"})

    def list_tables(self, schema, like=None):
        return [("dbo", t) for t in LOGO_TABLES]

    def _rows(self, sql, params=()):
        return [], []            # the database answers both catalogue questions with nothing


def test_a_logo_source_is_described_even_though_the_database_says_nothing():
    c = _Logo()
    described = c.descriptions("dbo")
    assert described[("LG_411_01_STLINE", None)], "the table itself is unexplained"
    assert "=" in described[("LG_411_01_STLINE", "LINETYPE")], "the code set did not reach the profile"
    assert len(described) > 500, f"only {len(described)} descriptions for ten Logo tables"


def test_a_logo_source_gets_a_join_graph_even_though_the_database_declares_none():
    c = _Logo()
    fks = c.foreign_keys("dbo")
    assert fks, "the join graph is empty — every join would have to be guessed"
    pairs = {(f["table"], f["column"], f["ref_table"]) for f in fks}
    assert ("LG_411_01_STLINE", "CLIENTREF", "LG_411_CLCARD") in pairs
    assert len(fks) > 50, f"only {len(fks)} joins across ten Logo tables"
    # Logo joins on LOGICALREF almost everywhere, but not quite: ORFLINE.PREVLINENO points at a line
    # number. Forcing every join onto LOGICALREF would produce SQL that joins on the wrong column.
    assert {f["ref_column"] for f in fks} >= {"LOGICALREF"}
    assert all(f["ref_column"] for f in fks), "a join with no target column is not a join"


def test_what_the_database_itself_says_still_wins():
    """A deployment where someone did annotate the schema must not have that overwritten by a
    generic dictionary line."""

    class _Annotated(_Logo):
        def _rows(self, sql, params=()):
            if "extended_properties" in sql:
                return [], [("LG_411_01_STLINE", "LINETYPE", "TİMAŞ: yalnız 0 ve 4 kullanılır")]
            return [], []

    described = _Annotated().descriptions("dbo")
    assert described[("LG_411_01_STLINE", "LINETYPE")] == "TİMAŞ: yalnız 0 ve 4 kullanılır"
    assert described[("LG_411_01_STLINE", "STOCKREF")], "the rest of the dictionary is still there"
