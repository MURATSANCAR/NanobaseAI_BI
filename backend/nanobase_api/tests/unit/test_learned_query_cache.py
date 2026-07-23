"""Unit tests for learned query cache (exact + similar, period guard)."""

from __future__ import annotations

from nanobase_api.infrastructure import learned_query_cache as lqc


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
