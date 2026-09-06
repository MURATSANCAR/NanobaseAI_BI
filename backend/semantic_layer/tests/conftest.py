"""Shared fixtures: SQLite catalog store, a tiny Logo-shaped SQLite database, profiles from it."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from semantic_layer.config import SemanticSettings
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
    s = SemanticSettings(store_dsn="sqlite://", tenant_id=TENANT, datasource_id=DS, project_dir=PROJECT if PROJECT.exists() else None, dialect="sqlite", table_like="LG_411_%")
    return s


def build_logo_sqlite() -> sqlite3.Connection:
    """LG_411_01_INVOICE / STLINE / CLCARD / ITEMS with a handful of rows whose sums are easy to check."""
    c = sqlite3.connect(":memory:", check_same_thread=False)
    c.executescript(
        """
        CREATE TABLE LG_411_CLCARD (LOGICALREF INTEGER PRIMARY KEY, CODE TEXT, DEFINITION_ TEXT, SPECODE2 TEXT, CITY TEXT, ACTIVE INTEGER);
        CREATE TABLE LG_411_ITEMS (LOGICALREF INTEGER PRIMARY KEY, CODE TEXT, NAME TEXT, SPECODE TEXT, ACTIVE INTEGER);
        CREATE TABLE LG_411_01_INVOICE (LOGICALREF INTEGER PRIMARY KEY, TRCODE INTEGER, CANCELLED INTEGER, CLIENTREF INTEGER, DATE_ TEXT, NETTOTAL REAL, GROSSTOTAL REAL, TOTALVAT REAL);
        CREATE TABLE LG_411_01_STLINE (LOGICALREF INTEGER PRIMARY KEY, TRCODE INTEGER, LINETYPE INTEGER, CANCELLED INTEGER, CLIENTREF INTEGER, STOCKREF INTEGER, INVOICEREF INTEGER, DATE_ TEXT, AMOUNT REAL, TOTAL REAL, OUTCOST REAL, PRICE REAL);
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


@pytest.fixture
def logo_db():
    return build_logo_sqlite()


@pytest.fixture
def logo_connector(logo_db):
    return SQLiteConnector(conn=logo_db)


@pytest.fixture
def profiles(logo_connector):
    return Profiler(logo_connector, enum_max_distinct=16).profile(DS, "main", "LG_411_%")


def _mk_profile(entity: str, pattern: str, columns: list[tuple[str, str, list[tuple[str, int]] | None]], rels=None, pk=("LOGICALREF",)) -> SchemaProfile:
    cols = []
    for name, typ, top in columns:
        cols.append(ColumnProfile(name=name, data_type=typ, top_values=top or [], distinct_count=len(top) if top else None, is_primary_key=name in pk))
    return SchemaProfile(datasource_id=DS, table_name=pattern.replace("{firm}", "411").replace("{period}", "01"), table_pattern=pattern, entity=entity, columns=cols, primary_key=list(pk), relationships=rels or [], context={"firm": "411", "period": "01"})


@pytest.fixture
def synthetic_profiles():
    inv = _mk_profile("INVOICE", "LG_{firm}_{period}_INVOICE", [("LOGICALREF", "int", None), ("TRCODE", "smallint", [("7", 100), ("8", 50), ("9", 5), ("2", 3), ("3", 4), ("1", 10), ("4", 2)]), ("CANCELLED", "smallint", [("0", 170), ("1", 4)]), ("CLIENTREF", "int", None), ("DATE_", "datetime", None), ("NETTOTAL", "float", None)], rels=[{"column": "CLIENTREF", "ref_entity": "CLCARD", "ref_column": "LOGICALREF"}])
    stl = _mk_profile("STLINE", "LG_{firm}_{period}_STLINE", [("LOGICALREF", "int", None), ("TRCODE", "smallint", [("8", 100), ("7", 50), ("3", 5), ("2", 3)]), ("LINETYPE", "smallint", [("0", 100), ("2", 50)]), ("CANCELLED", "smallint", [("0", 150), ("1", 1)]), ("STOCKREF", "int", None), ("DATE_", "datetime", None), ("AMOUNT", "float", None), ("TOTAL", "float", None), ("OUTCOST", "float", None)], rels=[{"column": "STOCKREF", "ref_entity": "ITEMS", "ref_column": "LOGICALREF"}])
    clc = _mk_profile("CLCARD", "LG_{firm}_CLCARD", [("LOGICALREF", "int", None), ("CODE", "varchar(17)", None), ("DEFINITION_", "varchar(51)", None), ("SPECODE2", "varchar(11)", [("KITAPCI", 10), ("E-TICARET", 5)])])
    itm = _mk_profile("ITEMS", "LG_{firm}_ITEMS", [("LOGICALREF", "int", None), ("CODE", "varchar(25)", None), ("NAME", "varchar(51)", None), ("SPECODE", "varchar(11)", None)])
    return [inv, stl, clc, itm]
