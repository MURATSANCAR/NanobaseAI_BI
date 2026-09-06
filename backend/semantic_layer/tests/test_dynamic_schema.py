"""Proof that nothing in the engine is tied to one customer's schema.

The same code path (profile → mine → certify → resolve → compile → execute) is run against a retail
database whose table naming, key naming, column names and enum codes have nothing in common with the
ERP fixture: no *REF columns, no declared foreign keys, no period tables, no TRCODE.
"""

from __future__ import annotations

from datetime import date

import pytest

from semantic_layer.candidates.generator import CandidateGenerator
from semantic_layer.conventions import Conventions
from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.history.miner import HistoryMiner
from semantic_layer.models import ConceptStatus, SemanticType, ValidatedPair
from semantic_layer.naming import logical_table
from semantic_layer.profiler.profiler import Profiler, column_index, infer_links
from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.store.catalog_store import open_store

TENANT, DS = "t1", "retail"

PAIRS = [
    ValidatedPair("r1", "2024 toplam ciro nedir?", 'SELECT SUM("net_amount") AS ciro FROM sales_2024_orders WHERE "voided" = 0 AND "kind" = 1'),
    ValidatedPair("r2", "2024 aylık ciro", 'SELECT strftime(\'%Y-%m\', "order_date") AS ay, SUM("net_amount") AS ciro FROM sales_2024_orders WHERE "voided" = 0 AND "kind" = 1 GROUP BY 1'),
    ValidatedPair("r3", "Ciro nedir (siparişler)?", 'SELECT SUM("net_amount") AS ciro FROM sales_2024_orders WHERE "voided" = 0 AND "kind" = 1 AND "order_date" >= \'2024-01-01\''),
    ValidatedPair("r4", "İade tutarı nedir?", 'SELECT SUM("net_amount") AS iade FROM sales_2024_orders WHERE "voided" = 0 AND "kind" = 2'),
    ValidatedPair("r5", "İade toplamı 2024", 'SELECT SUM("net_amount") AS iade FROM sales_2024_orders WHERE "voided" = 0 AND "kind" = 2 AND "order_date" >= \'2024-01-01\''),
    ValidatedPair("r6", "Segment bazında ciro", 'SELECT c."segment" AS segment, SUM(o."net_amount") AS ciro FROM sales_2024_orders o JOIN customers c ON c."id" = o."customer" WHERE o."voided" = 0 AND o."kind" = 1 GROUP BY c."segment"'),
    ValidatedPair("r7", "Segment kırılımında iade", 'SELECT c."segment" AS segment, SUM(o."net_amount") AS iade FROM sales_2024_orders o JOIN customers c ON c."id" = o."customer" WHERE o."voided" = 0 AND o."kind" = 2 GROUP BY c."segment"'),
    ValidatedPair("r8", "Segment bazında sipariş sayısı", 'SELECT c."segment" AS segment, COUNT(DISTINCT o."id") AS siparis_sayisi FROM sales_2024_orders o JOIN customers c ON c."id" = o."customer" WHERE o."voided" = 0 AND o."kind" = 1 GROUP BY c."segment"'),
]


@pytest.fixture
def retail_catalog(retail_connector, retail_db):
    profiles = Profiler(retail_connector, enum_max_distinct=16).profile(DS, "main", None)
    infer_links(profiles, retail_connector)                       # no FKs in this database
    conv = Conventions.from_profiles(profiles)
    store = open_store("sqlite://")
    for p in profiles:
        store.upsert_profile(p)
    miner = HistoryMiner(column_index(profiles), conventions=conv)
    res = miner.mine(PAIRS)
    conv.learn_time_hint(res.temporal_bindings)
    miner.persist(res, store, TENANT, DS)
    CandidateGenerator(store, TENANT, DS, profiles, conv).attach_profile_evidence()
    EvidenceEngine(store, min_support=3).run(TENANT, DS, profiles)
    return store, profiles, conv


def test_naming_is_derived_not_configured():
    """Numeric segments become positional placeholders whatever the customer calls the table."""
    erp = logical_table("dbo_LG_411_01_INVOICE", "dbo")
    retail = logical_table("sales_2024_orders")
    plain = logical_table("customers")
    assert (erp.entity, erp.table_pattern, erp.context) == ("INVOICE", "LG_{n0}_{n1}_INVOICE", {"n0": "411", "n1": "01"})
    assert (retail.entity, retail.table_pattern, retail.context) == ("ORDERS", "SALES_{n0}_ORDERS", {"n0": "2024"})
    assert (plain.entity, plain.table_pattern, plain.context) == ("CUSTOMERS", "CUSTOMERS", {})
    assert erp.physical({"n0": "412", "n1": "02"}) == "LG_412_02_INVOICE"   # same catalog, next period


def test_conventions_classify_columns_from_data(retail_profiles, profiles):
    """Flags (boolean-shaped), scope codes (other low-cardinality enums), time and key columns are
    read off the profile — the same rules land correctly on two unrelated schemas."""
    retail = Conventions.from_profiles(retail_profiles)
    assert retail.is_flag_column("ORDERS", "voided") and not retail.is_scope_column("ORDERS", "voided")
    assert retail.is_scope_column("ORDERS", "kind")          # 1 = order, 2 = return → not boolean
    assert retail.time_column("ORDERS") == "ORDER_DATE"
    assert retail.key_columns["CUSTOMERS"] == ["id"]
    erp = Conventions.from_profiles(profiles)
    assert erp.is_flag_column("INVOICE", "CANCELLED") and erp.is_scope_column("INVOICE", "TRCODE")
    assert erp.time_column("INVOICE") == "DATE_"


def test_links_inferred_from_value_overlap(retail_profiles, retail_connector):
    """No foreign keys, no naming convention: the link comes from the values themselves."""
    before = sum(len(p.relationships) for p in retail_profiles)
    added = infer_links(retail_profiles, retail_connector)
    orders = next(p for p in retail_profiles if p.entity == "ORDERS")
    assert before == 0 and added >= 1
    link = next(r for r in orders.relationships if r["column"] == "customer")
    assert (link["ref_entity"], link["ref_column"], link["source"]) == ("CUSTOMERS", "id", "value-overlap")


def test_end_to_end_on_an_unrelated_schema(retail_catalog, retail_db):
    store, profiles, conv = retail_catalog
    certified = store.find_concepts(TENANT, DS, status=ConceptStatus.CERTIFIED, limit=500)
    terms = {(c.normalized_term, c.semantic_type) for c in certified}
    assert ("ciro", SemanticType.METRIC) in terms          # SUM(net_amount) scoped to kind = 1
    assert ("segment", SemanticType.COLUMN) in terms       # projection alias ↔ customers.segment
    assert any(t == "voided default" or "voided" in t for t, k in terms if k == SemanticType.DEFAULT_FILTER)

    resolver = SemanticResolver(store, TENANT, DS, profiles, conventions=conv)
    comp = DeterministicCompiler(profiles, {}, "sqlite", default_filters=default_filters_provider(store, TENANT, DS), conventions=conv)
    sq = resolver.resolve("Segment bazında 2024 ciro", today=date(2024, 6, 1))
    assert [s.semantic_type for s in sq.slots].count(SemanticType.METRIC) == 1
    out = comp.compile(sq, store)
    assert out is not None, comp.plan(sq)[1]
    assert "sales_2024_orders" in out.sql.lower() and "customers" in out.sql.lower()
    cur = retail_db.execute(out.sql)
    cols = [d[0] for d in cur.description]
    rows = dict(cur.fetchall())
    assert cols == ["segment", "ciro"]
    # orders: kind 1 only, voided rows excluded → 100·i for i = 1..15 grouped by segment
    assert rows["TOPTAN"] == pytest.approx(100 * (3 + 6 + 9 + 12 + 15))
    assert rows["PERAKENDE"] == pytest.approx(100 * (1 + 2 + 4 + 5 + 7 + 8 + 10 + 11 + 13 + 14))


def test_no_customer_specific_identifiers_in_engine_sources():
    """A grep-level guard: engine modules must not name a customer's tables, columns or codes."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    banned = re.compile(r"\b(TRCODE|LINETYPE|NETTOTAL|LOGICALREF|CLCARD|STLINE|ORFICHE|CLIENTREF|STOCKREF|OUTCOST|SPECODE2?)\b")
    offenders = []
    for path in sorted(root.rglob("*.py")):
        if "tests" in path.parts:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if code.strip().startswith(('"', "'", "*", ">>>")):
                continue
            if banned.search(code):
                offenders.append(f"{path.relative_to(root)}:{i}: {line.strip()[:90]}")
    assert not offenders, "customer-specific identifiers in engine code:\n" + "\n".join(offenders)
