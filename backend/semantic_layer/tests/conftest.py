"""Fixtures. Two unrelated schemas on purpose: an ERP-shaped one with period tables and a plain
retail one — every assertion has to hold for both, so no customer's naming can leak into the code."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from semantic_layer.config import SemanticSettings
from semantic_layer.conventions import Conventions
from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.profiler.connectors import SQLiteConnector
from semantic_layer.profiler.profiler import Profiler
from semantic_layer.store.catalog_store import open_store

ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "deploy" / "wren-project" / "logo_timas"
ENUM_PROBE = ROOT / "artifacts" / "timas" / "apply-all.json"

TENANT, DS = "t1", "logo"


@pytest.fixture
def store():
    return open_store("sqlite://")


@pytest.fixture
def settings():
    return SemanticSettings(store_dsn="sqlite://", tenant_id=TENANT, datasource_id=DS, project_dir=PROJECT if PROJECT.exists() else None, dialect="sqlite", table_like="LG_411_%")


def build_erp_sqlite() -> sqlite3.Connection:
    """Period-partitioned ERP shape (LG_<firm>_<period>_<entity>) with declared foreign keys."""
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.executescript(
        """
        CREATE TABLE LG_411_CLCARD (LOGICALREF INTEGER PRIMARY KEY, CODE TEXT, DEFINITION_ TEXT, SPECODE2 TEXT, CITY TEXT, ACTIVE INTEGER);
        CREATE TABLE LG_411_ITEMS (LOGICALREF INTEGER PRIMARY KEY, CODE TEXT, NAME TEXT, SPECODE TEXT, ACTIVE INTEGER);
        CREATE TABLE LG_411_01_INVOICE (LOGICALREF INTEGER PRIMARY KEY, TRCODE INTEGER, CANCELLED INTEGER, CLIENTREF INTEGER REFERENCES LG_411_CLCARD(LOGICALREF), DATE_ TIMESTAMP, NETTOTAL REAL, GROSSTOTAL REAL, TOTALVAT REAL);
        CREATE TABLE LG_411_01_STLINE (LOGICALREF INTEGER PRIMARY KEY, TRCODE INTEGER, LINETYPE INTEGER, CANCELLED INTEGER,
            CLIENTREF INTEGER REFERENCES LG_411_CLCARD(LOGICALREF), STOCKREF INTEGER REFERENCES LG_411_ITEMS(LOGICALREF),
            INVOICEREF INTEGER REFERENCES LG_411_01_INVOICE(LOGICALREF), DATE_ TIMESTAMP, AMOUNT REAL, TOTAL REAL, OUTCOST REAL, PRICE REAL);
        INSERT INTO LG_411_CLCARD VALUES (1,'C1','Kitapçı A','KITAPCI','İstanbul',1),(2,'C2','E-Mağaza','E-TICARET','Ankara',1),(3,'C3','Dağıtıcı X','DAGITICI','İzmir',1);
        INSERT INTO LG_411_ITEMS VALUES (10,'K1','Kitap Bir','Timaş Çocu',1),(11,'K2','Kitap İki','Genç Timaş',1);
        -- 2026: retail (7) 100+50, wholesale (8) 1000+500, service (9) 10, returns (2) 20, (3) 80, purchase (1) 300, cancelled 7 9999
        INSERT INTO LG_411_01_INVOICE VALUES
          (1,7,0,1,'2026-01-15',100,100,5),(2,7,0,2,'2026-02-10',50,50,2),
          (3,8,0,3,'2026-01-20',1000,1000,50),(4,8,0,3,'2026-07-05',500,500,25),
          (5,9,0,1,'2026-03-01',10,10,1),(6,2,0,2,'2026-02-11',20,20,1),(7,3,0,3,'2026-07-06',80,80,4),
          (8,1,0,3,'2026-01-30',300,300,15),(9,7,1,1,'2026-01-16',9999,9999,1),
          (10,8,0,3,'2025-12-01',777,777,7);
        INSERT INTO LG_411_01_STLINE VALUES
          (1,8,0,0,3,10,3,'2026-01-20',10,1000,50,100),(2,8,0,0,3,11,4,'2026-07-05',5,500,60,100),
          (3,7,0,0,1,10,1,'2026-01-15',2,100,40,50),(4,3,0,0,3,10,7,'2026-07-06',1,80,0,80),
          (5,8,2,0,3,10,3,'2026-01-20',0,100,0,0),(6,7,0,1,1,10,9,'2026-01-16',99,9999,0,101);
        """
    )
    c.commit()
    return c


def build_retail_sqlite() -> sqlite3.Connection:
    """A completely different world: year-suffixed fact table, no foreign keys, no *REF convention,
    English/Turkish mixed column names — the pipeline must work from data alone."""
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.executescript(
        """
        CREATE TABLE customers (id INTEGER PRIMARY KEY, code TEXT, title TEXT, segment TEXT, city TEXT);
        CREATE TABLE sales_2024_orders (id INTEGER PRIMARY KEY, kind INTEGER, voided INTEGER, customer INTEGER, order_date TIMESTAMP, net_amount REAL);
        """
    )
    rows = []
    for i in range(1, 16):
        rows.append((i, f"M{i}", f"Müşteri {i}", "PERAKENDE" if i % 3 else "TOPTAN", "İzmir" if i % 2 else "Bursa"))
    c.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", rows)
    orders = []
    oid = 1
    for i in range(1, 16):
        orders.append((oid, 1, 0, i, "2024-03-%02d" % ((i % 28) + 1), 100.0 * i)); oid += 1
        orders.append((oid, 2, 0, i, "2024-04-%02d" % ((i % 28) + 1), 10.0 * i)); oid += 1
    orders.append((oid, 1, 1, 3, "2024-03-05", 99999.0))
    c.executemany("INSERT INTO sales_2024_orders VALUES (?,?,?,?,?,?)", orders)
    c.commit()
    return c


@pytest.fixture
def logo_db():
    return build_erp_sqlite()


@pytest.fixture
def logo_connector(logo_db):
    return SQLiteConnector(conn=logo_db)


@pytest.fixture
def profiles(logo_connector):
    return Profiler(logo_connector, enum_max_distinct=16).profile(DS, "main", "LG_411_%")


@pytest.fixture
def retail_db():
    return build_retail_sqlite()


@pytest.fixture
def retail_connector(retail_db):
    return SQLiteConnector(conn=retail_db)


@pytest.fixture
def retail_profiles(retail_connector):
    return Profiler(retail_connector, enum_max_distinct=16).profile("retail", "main", None)


def conventions_for(profiles) -> Conventions:
    return Conventions.from_profiles(profiles)


def _mk_profile(entity: str, pattern: str, columns: list[tuple[str, str, list[tuple[str, int]] | None]], rels=None, pk=("LOGICALREF",)) -> SchemaProfile:
    cols = []
    for name, typ, top in columns:
        cols.append(ColumnProfile(name=name, data_type=typ, top_values=top or [], distinct_count=len(top) if top else None, is_primary_key=name in pk))
    return SchemaProfile(datasource_id=DS, table_name=pattern.replace("{n0}", "411").replace("{n1}", "01"), table_pattern=pattern, entity=entity, schema_name="dbo", columns=cols, primary_key=list(pk), relationships=rels or [], context={"n0": "411", "n1": "01"})


@pytest.fixture
def synthetic_profiles():
    inv = _mk_profile("INVOICE", "LG_{n0}_{n1}_INVOICE", [("LOGICALREF", "int", None), ("TRCODE", "smallint", [("7", 100), ("8", 50), ("9", 5), ("2", 3), ("3", 4), ("1", 10), ("4", 2)]), ("CANCELLED", "smallint", [("0", 170), ("1", 4)]), ("CLIENTREF", "int", None), ("DATE_", "datetime", None), ("NETTOTAL", "float", None)], rels=[{"column": "CLIENTREF", "ref_entity": "CLCARD", "ref_column": "LOGICALREF"}])
    stl = _mk_profile("STLINE", "LG_{n0}_{n1}_STLINE", [("LOGICALREF", "int", None), ("TRCODE", "smallint", [("8", 100), ("7", 50), ("3", 5), ("2", 3)]), ("LINETYPE", "smallint", [("0", 100), ("2", 50)]), ("CANCELLED", "smallint", [("0", 150), ("1", 1)]), ("STOCKREF", "int", None), ("DATE_", "datetime", None), ("AMOUNT", "float", None), ("TOTAL", "float", None), ("OUTCOST", "float", None)], rels=[{"column": "STOCKREF", "ref_entity": "ITEMS", "ref_column": "LOGICALREF"}])
    clc = _mk_profile("CLCARD", "LG_{n0}_CLCARD", [("LOGICALREF", "int", None), ("CODE", "varchar(17)", None), ("DEFINITION_", "varchar(51)", None), ("SPECODE2", "varchar(11)", [("KITAPCI", 10), ("E-TICARET", 5), ("DAGITICI", 3)])])
    itm = _mk_profile("ITEMS", "LG_{n0}_ITEMS", [("LOGICALREF", "int", None), ("CODE", "varchar(25)", None), ("NAME", "varchar(51)", None), ("SPECODE", "varchar(11)", None)])
    return [inv, stl, clc, itm]
