"""Keyword resolver in retrieval/semantic.py: which questions may resolve to
a deterministic metric vs must stay on the LLM plan path.

MetricCompiler only compiles a single scalar aggregate (no GROUP BY, no
ranking) — resolving a dimensional/ranked question would silently serve the
wrong-shaped answer disguised as verified truth, so the negative cases here
matter as much as the positive one.
"""

from __future__ import annotations

import pytest

from nanobase_awel.retrieval.semantic import (
    _DIMENSION_OR_RANK_HINT,
    _REVENUE_INTENT,
    _UNPAID_INVOICE_INTENT,
)


def _may_resolve_total_revenue(question: str) -> bool:
    return bool(_REVENUE_INTENT.search(question)) and not _DIMENSION_OR_RANK_HINT.search(question)


@pytest.mark.parametrize(
    "question",
    [
        "Toplam ciro nedir?",
        "Ciro ne kadar?",
        "Toplam satış tutarımız nedir",
    ],
)
def test_bare_revenue_question_resolves(question: str):
    assert _may_resolve_total_revenue(question)


@pytest.mark.parametrize(
    "question",
    [
        "Müşteri bazında toplam ciroyu en yüksekten başlayarak ilk 3 müşteri",
        "Ürün kategorisine göre toplam satış tutarı",
        "Segmentlere göre toplam ciro",
        "Cirosu 20000 TL üzerinde olan müşteriler",
        "En çok adet satılan ürün hangisi?",
        "Şehirlere göre ciro dağılımı",
        "En yüksek ciro yapan müşteri",
    ],
)
def test_dimensional_or_ranked_revenue_question_does_not_resolve(question: str):
    assert not _may_resolve_total_revenue(question)


def test_unpaid_invoice_intent_does_not_collide_with_revenue_intent():
    q = "Açık faturaların toplam kalan tutarı ne kadar?"
    assert _UNPAID_INVOICE_INTENT.search(q)
    # "kalan tutar" carries no "ciro"/"revenue" wording — must not also try
    # to resolve total_revenue for the same question.
    assert not _REVENUE_INTENT.search(q)


@pytest.mark.parametrize(
    "question",
    [
        "Ciroyu göster",  # ciro + accusative suffix
        "Cirosu ne kadar artmış",  # ciro + possessive suffix
        "Toplam satışımızı öğrenmek istiyorum",  # toplam standalone is fine either way
    ],
)
def test_revenue_intent_matches_turkish_suffixed_forms(question: str):
    """Regression: a trailing \\b on the Turkish stem would silently reject
    almost every real inflected form ('ciroyu', 'cirosu', ...) — only the
    bare, unsuffixed word would ever match."""
    assert _REVENUE_INTENT.search(question)


def test_dimension_hint_matches_turkish_suffixed_forms():
    """Same class of bug: 'segmentlere', 'kategorisine', 'müşteriye' must
    still be detected as dimension hints despite the suffix."""
    assert _DIMENSION_OR_RANK_HINT.search("Segmentlere göre ciro")
    assert _DIMENSION_OR_RANK_HINT.search("Ürün kategorisine göre toplam satış tutarı")
    assert _DIMENSION_OR_RANK_HINT.search("Müşteriye göre ciro dağılımı")
