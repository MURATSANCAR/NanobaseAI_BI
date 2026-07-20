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
    assert "header" in g.lower()
    assert "fatura_kalemleri" in g
    assert "Do NOT ask the user to restate" in g or "already present" in g
    assert "SELECT *" in g or "Never use SELECT" in g


def test_stated_year_discourages_date_clarification():
    g = build_planning_guidance(
        "2026 mali yılı için bütçe kullanımı",
        ["public.butce_planlari", "public.alis_faturalari"],
    )
    assert "Do NOT ask the user to restate" in g
    assert "Bias to PLANNED" in g


def test_ask_default_when_line_tables_no_period():
    g = build_planning_guidance(
        "ürün bazında marj hesapla",
        ["public.fatura_kalemleri", "public.urunler"],
    )
    assert "default" in g.lower() or "AMBIGUOUS" in g
    assert "Bias to PLANNED" in g


def test_user_guidance_cost_and_timeout():
    assert "tarih" in (user_guidance_for_gateway_error("QUERY_COST_EXCEEDED") or "").lower()
    assert "zaman" in (user_guidance_for_gateway_error("QUERY_TIMEOUT") or "").lower()
    assert user_guidance_for_gateway_error("WILDCARD_NOT_ALLOWED") is None
