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


def test_ciro_disambiguated_from_invoice_when_both_domains_present():
    """'Toplam ciro nedir?' with both an order table and an invoice table
    retrieved must steer to the order/sales table, not invoices.gross_amount
    (the live bug this guards: the model answered from analytics.invoices)."""
    g = build_planning_guidance(
        "Toplam ciro nedir?",
        ["analytics.sales_orders", "analytics.sales_order_items", "analytics.invoices"],
    )
    assert "sales_orders" in g
    assert "NOT from the invoice table" in g


def test_ciro_not_disambiguated_when_question_is_about_invoices():
    """Same tables, but the question explicitly asks about invoicing — must
    NOT steer away from invoices."""
    g = build_planning_guidance(
        "Vadesi geçmiş faturaların toplam kalan tutarı ne kadar?",
        ["analytics.sales_orders", "analytics.invoices"],
    )
    assert "NOT from the invoice table" not in g


def test_revenue_aggregate_requires_completed_orders_filter():
    """Turns the model's occasionally-self-invented 'completed only' revenue
    convention into an always-stated rule (was inconsistent — qa-016/017/020
    in the quality corpus failed exactly because it wasn't always applied)."""
    g = build_planning_guidance(
        "Segmentlere göre toplam ciro",
        ["analytics.sales_orders", "analytics.sales_order_items", "analytics.customers"],
    )
    assert "completed orders only" in g
    assert "not realized revenue" in g


def test_no_completed_filter_rule_without_revenue_intent():
    g = build_planning_guidance(
        "Sipariş durumlarına göre sipariş adetleri",
        ["analytics.sales_orders"],
    )
    assert "completed orders only" not in g


def test_ciro_disambiguation_fires_on_suffixed_turkish_forms():
    """Regression: _TOTAL_INTENT/_INVOICE_INTENT used to require a trailing
    word boundary, which silently rejects almost every real Turkish
    inflection ('ciroyu', 'faturaların') — only the bare stem ever matched."""
    g = build_planning_guidance(
        "Toplam ciroyu öğrenmek istiyorum",
        ["analytics.sales_orders", "analytics.sales_order_items", "analytics.invoices"],
    )
    assert "NOT from the invoice table" in g

    g2 = build_planning_guidance(
        "Faturaların toplamı ne kadar?",
        ["analytics.sales_orders", "analytics.invoices"],
    )
    assert "NOT from the invoice table" not in g2  # invoice intent correctly detected


def test_line_table_date_instruction_never_contradicts_no_default_window():
    """Regression: the line-table bullet used to unconditionally say 'always
    include a date/time predicate' even when no period was stated, directly
    contradicting the 'answer all-time, no invented window' bullet above it.
    The two must never both fire."""
    g = build_planning_guidance(
        "Ürün kategorisine göre toplam satış tutarı",
        ["analytics.sales_order_items", "analytics.products"],
    )
    assert "over ALL time, with no date filter" in g
    assert "always include a date/time predicate" not in g
    assert "do not add a date" in g.lower()
