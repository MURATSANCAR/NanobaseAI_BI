"""resolve_revenue_intent: which questions the deterministic compiler may
answer (bare aggregate, single-dimension breakdown, ranked top-N) vs which
must fall through to the LLM (multi-dimension, HAVING/threshold).

Every case here is drawn from tests/text2sql/quality-corpus.yaml qa-014
through qa-020 — the exact question set that exposed the LLM's
inconsistency on this class of question.
"""

from __future__ import annotations

import pytest

from nanobase_awel.retrieval.semantic import resolve_revenue_intent


def test_bare_aggregate_qa014():
    r = resolve_revenue_intent("Toplam ciro nedir?")
    assert r == {"metricCode": "total_revenue", "groupBy": [], "limit": None, "orderDesc": True}


def test_ranked_top3_by_customer_qa015():
    r = resolve_revenue_intent(
        "Müşteri bazında toplam ciroyu en yüksekten başlayarak ilk 3 müşteri"
    )
    assert r == {
        "metricCode": "total_revenue",
        "groupBy": ["customer_name"],
        "limit": 3,
        "orderDesc": True,
    }


def test_breakdown_by_product_category_qa016():
    """'Ürün kategorisine göre' is the compound phrase 'product category' —
    ONE dimension (category), not two ('product' AND 'category')."""
    r = resolve_revenue_intent("Ürün kategorisine göre toplam satış tutarı")
    assert r == {
        "metricCode": "total_revenue",
        "groupBy": ["product_category"],
        "limit": None,
        "orderDesc": True,
    }


def test_breakdown_by_segment_qa017():
    r = resolve_revenue_intent("Segmentlere göre toplam ciro")
    assert r == {
        "metricCode": "total_revenue",
        "groupBy": ["segment"],
        "limit": None,
        "orderDesc": True,
    }


def test_threshold_question_falls_through_qa018():
    """HAVING/threshold extraction is out of scope — a wrong extraction would
    confidently show a wrong financial figure. Must return None (LLM path)."""
    assert resolve_revenue_intent("Cirosu 20000 TL üzerinde olan müşteriler") is None


def test_top_selling_product_by_quantity_qa020():
    """'satılan' (sold) is a different inflection from 'satış' (sale) and
    intentionally not matched by _REVENUE_INTENT — 'adet' correctly selects
    the quantity metric instead."""
    r = resolve_revenue_intent("En çok adet satılan ürün hangisi?")
    assert r == {
        "metricCode": "total_quantity_sold",
        "groupBy": ["product_name"],
        "limit": 1,
        "orderDesc": True,
    }


def test_multi_dimension_breakdown_falls_through():
    """Two genuinely distinct dimensions in one ask — not GROUP BY-list
    supported this round; must fall through rather than guess an order."""
    assert resolve_revenue_intent("Segment ve ülke kırılımında ciro") is None


def test_non_revenue_non_quantity_question_returns_none():
    assert resolve_revenue_intent("Sipariş durumlarına göre sipariş adetleri") is None


@pytest.mark.parametrize(
    "question,expected_limit",
    [
        ("İlk 5 müşteri ciroya göre", 5),
        ("Cirosu en yüksek ilk 10 ürün", 10),
        ("En yüksek ciro yapan müşteri", 1),
        ("En çok ciro getiren segment", 1),
    ],
)
def test_rank_limit_extraction(question, expected_limit):
    r = resolve_revenue_intent(question)
    assert r is not None
    assert r["limit"] == expected_limit


def test_generic_adet_word_does_not_trigger_quantity_metric():
    """'adet' alone is heavily overloaded in Turkish ('sipariş adetleri' =
    order COUNT) — must require 'satılan'/'satış adedi' specifically, or a
    generic order-count question would silently resolve to the wrong metric
    (quantity sold) as 'verified truth'."""
    assert resolve_revenue_intent("Sipariş durumlarına göre sipariş adetleri") is None
    assert resolve_revenue_intent("Kaç adet siparişimiz var?") is None


def test_bare_aggregate_matches_turkish_suffixed_forms():
    """Regression companion to the \\b-boundary fix: 'ciroyu'/'cirosu' must
    still resolve the bare-aggregate case, not just the unsuffixed 'ciro'."""
    assert resolve_revenue_intent("Ciroyu göster") == {
        "metricCode": "total_revenue",
        "groupBy": [],
        "limit": None,
        "orderDesc": True,
    }
