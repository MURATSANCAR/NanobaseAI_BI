"""Discovery must not lose tables to the alphabet, and must say when a cap bit.

A Logo/Unity ERP database holds one table set per firm and one per firm-period. Scanning it with
`SELECT TOP 200 ... ORDER BY TABLE_NAME` stopped mid-alphabet: the catalogue was missing ITEMS,
STLINE and STFICHE, and nothing in the report said a cut had happened — so it read as a database
that simply did not have them.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

from config import IndexerConfig  # noqa: E402


def _mssql_module():
    """Load scanner.mssql without scanner/__init__, which pulls in the postgres driver."""
    spec = importlib.util.spec_from_file_location("_mssql_scanner", _ROOT / "scanner" / "mssql.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


select_tables = _mssql_module().select_tables

FIRM_LEVEL = ["CLCARD", "ITEMS", "SLSMAN", "PAYPLANS", "BANKACC", "EMUHACC"]
PERIOD_LEVEL = ["INVOICE", "STLINE", "STFICHE", "ORFICHE", "ORFLINE", "CLFLINE", "BNFLINE"]


def logo_tables(firms=(411,), periods=(1, 2, 3)) -> list[dict]:
    """The shape of a real Logo schema, listed the way INFORMATION_SCHEMA returns it: alphabetically."""
    out = []
    for f in firms:
        out += [{"TABLE_SCHEMA": "dbo", "TABLE_NAME": f"LG_{f}_{t}", "TABLE_TYPE": "BASE TABLE"} for t in FIRM_LEVEL]
        for p in periods:
            out += [
                {"TABLE_SCHEMA": "dbo", "TABLE_NAME": f"LG_{f}_{p:02d}_{t}", "TABLE_TYPE": "BASE TABLE"}
                for t in PERIOD_LEVEL
            ]
    return sorted(out, key=lambda r: r["TABLE_NAME"])


def counts_where_the_transactions_are(rows):
    """STLINE and INVOICE carry the rows; the code tables are tiny. This is what ranking should see."""
    big = {"STLINE": 8_000_000, "INVOICE": 900_000, "CLFLINE": 700_000, "ORFLINE": 400_000}
    return lambda: {
        (r["TABLE_SCHEMA"], r["TABLE_NAME"]): next((n for k, n in big.items() if r["TABLE_NAME"].endswith(k)), 500)
        for r in rows
    }


def test_the_default_cap_does_not_bite_a_real_erp_schema():
    """Three firms with five periods each stay well under the cap — nobody should have to know an
    environment variable exists in order to see their own database."""
    rows = logo_tables(firms=(411, 412, 413), periods=(1, 2, 3, 4, 5))
    cfg = IndexerConfig()
    picked = select_tables(cfg, rows, lambda: {})
    assert cfg.truncated_tables == []
    assert len(picked) == len(rows)


def test_the_transaction_tables_survive_a_cut():
    """The old cut kept the alphabet's first n, and ITEMS/STLINE/STFICHE sort late — they were the
    tables people actually asked about."""
    rows = logo_tables()
    cfg = IndexerConfig()
    cfg.max_tables = 12
    picked = select_tables(cfg, rows, counts_where_the_transactions_are(rows))
    kept = {r["TABLE_NAME"] for r in picked}
    assert any(n.endswith("_STLINE") for n in kept), "the largest table in the database was dropped"
    assert any(n.endswith("_INVOICE") for n in kept)
    alphabetical = {r["TABLE_NAME"] for r in rows[: cfg.max_tables]}
    assert kept != alphabetical, "selection still follows the alphabet"


def test_a_cut_is_reported_rather_than_silent():
    rows = logo_tables()
    cfg = IndexerConfig()
    cfg.max_tables = 10
    picked = select_tables(cfg, rows, counts_where_the_transactions_are(rows))
    assert cfg.discovered_tables == len(rows), "the run must know how many tables the scope matched"
    assert len(cfg.truncated_tables) == len(rows) - 10
    assert len(picked) == 10


def test_missing_stats_permission_is_not_a_failure():
    """A read-only login without VIEW DATABASE STATE still gets a catalogue — just an unranked cut."""
    rows = logo_tables()
    cfg = IndexerConfig()
    cfg.max_tables = 10

    def denied():
        raise PermissionError("VIEW DATABASE STATE denied")

    picked = select_tables(cfg, rows, denied)
    assert len(picked) == 10
    assert cfg.discovered_tables == len(rows)
