from __future__ import annotations

from nanobase_awel.operators.planning_guidance import (
    build_planning_guidance,
    user_guidance_for_gateway_error,
)


def test_prefer_header_for_totals_when_line_tables_present():
    g = build_planning_guidance(
        "2025 ile 2026 yıllık ciro karşılaştırması",
        ["public.faturalar", "public.fatura_kalemleri", "public.alis_faturalari"],
    )
    assert "header-level" in g.lower() or "header" in g.lower()
    assert "fatura_kalemleri" in g
    assert "SELECT *" in g or "select *" in g.lower() or "Never use SELECT" in g


def test_ask_date_when_line_tables_no_period():
    g = build_planning_guidance(
        "ürün bazında marj hesapla",
        ["public.fatura_kalemleri", "public.urunler"],
    )
    assert "date" in g.lower() or "AMBIGUOUS" in g


def test_user_guidance_cost_and_timeout():
    assert "tarih" in (user_guidance_for_gateway_error("QUERY_COST_EXCEEDED") or "").lower()
    assert "zaman" in (user_guidance_for_gateway_error("QUERY_TIMEOUT") or "").lower()
    assert user_guidance_for_gateway_error("WILDCARD_NOT_ALLOWED") is None
