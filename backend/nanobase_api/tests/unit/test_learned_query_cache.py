"""Unit tests for learned query cache (exact + similar, period guard)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from nanobase_api.infrastructure import learned_query_cache as lqc


@pytest.fixture()
def sqlite_engine(monkeypatch):
    """In-memory engine with a SQLite-flavored twin of the Postgres schema
    (NOW()/TIMESTAMPTZ aren't valid SQLite) — ensure_schema() is bypassed via
    _SCHEMA_READY so production DDL never runs against it. Module globals are
    reset around the test since _MEM/_MEM_BY_DS/_DS_HYDRATED_AT are process-wide.
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE bi_learned_queries (
                  id VARCHAR(64) PRIMARY KEY,
                  tenant_id VARCHAR(128) NOT NULL DEFAULT 'default',
                  datasource_id VARCHAR(128) NOT NULL,
                  question TEXT NOT NULL,
                  normalized_question TEXT NOT NULL,
                  question_hash VARCHAR(64) NOT NULL,
                  sql_text TEXT NOT NULL,
                  sql_source VARCHAR(64),
                  hit_count INTEGER NOT NULL DEFAULT 1,
                  success_count INTEGER NOT NULL DEFAULT 1,
                  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  last_hit_at TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX ux_bi_learned_qhash "
                "ON bi_learned_queries (tenant_id, datasource_id, question_hash)"
            )
        )
    monkeypatch.setattr(lqc, "_SCHEMA_READY", True)
    lqc._MEM.clear()
    lqc._MEM_BY_DS.clear()
    lqc._DS_HYDRATED_AT.clear()
    yield engine
    lqc._MEM.clear()
    lqc._MEM_BY_DS.clear()
    lqc._DS_HYDRATED_AT.clear()


def test_normalize_and_hash_stable():
    a = lqc.question_hash("Kaç müşteri var?")
    b = lqc.question_hash("  kaç MUSTERI var?  ")
    assert a == b


def test_period_guard_blocks_cross_month():
    assert not lqc._periods_compatible(
        lqc.normalize_question("Bu ayki fatura sayısı"),
        lqc.normalize_question("Geçen ayki fatura sayısı"),
    )
    assert lqc._periods_compatible(
        lqc.normalize_question("Bu ayki fatura sayısı"),
        lqc.normalize_question("Bu ay fatura adedi nedir"),
    )


def test_exact_and_similar_memory_lookup():
    lqc._MEM.clear()
    lqc._MEM_BY_DS.clear()
    row = {
        "id": "lq-test1",
        "tenant_id": "default",
        "datasource_id": "erp",
        "question": "Kaç müşteri var?",
        "normalized_question": lqc.normalize_question("Kaç müşteri var?"),
        "question_hash": lqc.question_hash("Kaç müşteri var?"),
        "sql_text": 'SELECT COUNT(*) AS n FROM public.musteriler',
        "sql_source": "nl2sql_plan",
        "hit_count": 1,
        "success_count": 1,
    }
    lqc._mem_put(row)

    hit = lqc.lookup(None, tenant_id="default", datasource_id="erp", question="kaç müşteri var?")
    assert hit is not None
    assert hit.match == "exact"
    assert "musteriler" in hit.sql

    hit2 = lqc.lookup(
        None,
        tenant_id="default",
        datasource_id="erp",
        question="Müşteri sayısı nedir?",
        similar_threshold=0.55,
    )
    assert hit2 is not None
    assert hit2.match == "similar"
    assert hit2.sql == row["sql_text"]


def test_similar_rejects_different_period():
    lqc._MEM.clear()
    lqc._MEM_BY_DS.clear()
    row = {
        "id": "lq-test2",
        "tenant_id": "default",
        "datasource_id": "erp",
        "question": "Bu ayki fatura sayısı nedir?",
        "normalized_question": lqc.normalize_question("Bu ayki fatura sayısı nedir?"),
        "question_hash": lqc.question_hash("Bu ayki fatura sayısı nedir?"),
        "sql_text": "SELECT COUNT(*) FROM faturalar WHERE fatura_tarihi >= '2026-07-01'",
        "sql_source": "nl2sql_plan",
        "hit_count": 1,
        "success_count": 1,
    }
    lqc._mem_put(row)
    miss = lqc.lookup(
        None,
        tenant_id="default",
        datasource_id="erp",
        question="Geçen ayki fatura sayısı nedir?",
        similar_threshold=0.5,
    )
    assert miss is None


def test_exact_lookup_stops_serving_row_deleted_directly_in_db(sqlite_engine):
    """Regression for the bug found 2026-08-11: deleting a row straight from
    Postgres (bypassing remember()) used to be invisible to any already-running
    worker — the in-memory copy kept being served forever. Exact lookups must
    now re-verify against the DB on every call."""
    engine = sqlite_engine
    lid = lqc.remember(
        engine,
        tenant_id="default",
        datasource_id="bi_reporting",
        question="Enterprise segmentindeki müşterileri isimleriyle listele",
        sql="SELECT customer_name FROM public.customers WHERE segment = 'Enterprise'",
    )
    assert lid is not None

    hit = lqc.lookup(
        engine,
        tenant_id="default",
        datasource_id="bi_reporting",
        question="Enterprise segmentindeki müşterileri isimleriyle listele",
    )
    assert hit is not None and hit.match == "exact"
    assert "Enterprise" in hit.sql

    # Simulate an operator fixing the bad row directly in Postgres — no call
    # through remember()/the app at all.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM bi_learned_queries WHERE id = :id"), {"id": lid})

    miss = lqc.lookup(
        engine,
        tenant_id="default",
        datasource_id="bi_reporting",
        question="Enterprise segmentindeki müşterileri isimleriyle listele",
    )
    assert miss is None, "deleted row must not keep being served from stale memory"


def test_exact_lookup_picks_up_a_correction_made_directly_in_db(sqlite_engine):
    """Same bug, the 'operator fixes the SQL' variant: an UPDATE bypassing
    remember() must be reflected on the very next lookup, not after a restart."""
    engine = sqlite_engine
    lqc.remember(
        engine,
        tenant_id="default",
        datasource_id="bi_reporting",
        question="Toplam ciro nedir?",
        sql="SELECT SUM(gross_amount) FROM analytics.invoices",
    )
    lqc.lookup(engine, tenant_id="default", datasource_id="bi_reporting", question="Toplam ciro nedir?")

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE bi_learned_queries SET sql_text = :sql "
                "WHERE tenant_id='default' AND datasource_id='bi_reporting'"
            ),
            {"sql": "SELECT SUM(quantity * unit_price) FROM analytics.sales_order_items"},
        )

    hit = lqc.lookup(
        engine, tenant_id="default", datasource_id="bi_reporting", question="Toplam ciro nedir?"
    )
    assert hit is not None
    assert "sales_order_items" in hit.sql
    assert "invoices" not in hit.sql


def test_similar_bucket_evicts_deleted_row_after_ttl(sqlite_engine, monkeypatch):
    """The fuzzy-match path must also stop offering a row Postgres no longer
    has, once its TTL window elapses — not hold onto it until a restart."""
    engine = sqlite_engine
    monkeypatch.setattr(lqc, "HYDRATE_TTL_SEC", 0.0)  # always re-sync in this test
    lid = lqc.remember(
        engine,
        tenant_id="default",
        datasource_id="erp",
        question="Kaç müşteri var?",
        sql="SELECT COUNT(*) FROM public.musteriler",
    )
    hit = lqc.lookup(
        engine, tenant_id="default", datasource_id="erp", question="Müşteri sayısı nedir?"
    )
    assert hit is not None and hit.match == "similar"

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM bi_learned_queries WHERE id = :id"), {"id": lid})

    miss = lqc.lookup(
        engine, tenant_id="default", datasource_id="erp", question="Müşteri sayısı nedir?"
    )
    assert miss is None
