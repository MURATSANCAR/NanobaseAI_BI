"""COUNT_ENTITY grammar must emit combinatorial phrases like 'toplam müşteri sayısı'."""

from __future__ import annotations

from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.scenario import normalize_question
from nanobase_api.scenario_engine.infrastructure.question_grammar import generate_questions


def _count_plan(entity: str = "customer", period: str | None = None) -> LogicalPlan:
    return LogicalPlan(
        family="COUNT_ENTITY",
        entity=entity,
        physical_table="musteriler" if entity == "customer" else None,
        period=period,
    )


def test_toplam_musteri_sayisi_in_customer_count_combos():
    qs = generate_questions(_count_plan("customer"), expand=True)
    norms = {normalize_question(q) for q in qs}
    assert "toplam musteri sayisi" in norms
    assert "toplam musteri adedi" in norms
    assert "kac musteri var" in norms
    assert "musteri sayisi nedir" in norms


def test_count_combos_cover_all_entities():
    for entity in ("customer", "invoice", "order", "product", "payment"):
        qs = generate_questions(_count_plan(entity), expand=True)
        norms = {normalize_question(q) for q in qs}
        singular = {
            "customer": "musteri",
            "invoice": "fatura",
            "order": "siparis",
            "product": "urun",
            "payment": "odeme",
        }[entity]
        assert f"toplam {singular} sayisi" in norms
        assert f"kac {singular} var" in norms
        # Combinatorial volume — prefix × synonym × tails
        assert len(qs) >= 80


def test_period_count_includes_toplam_forms():
    qs = generate_questions(_count_plan("invoice", period="TODAY"), expand=True)
    norms = {normalize_question(q) for q in qs}
    # Period scenarios must not own bare global forms
    assert "toplam fatura sayisi" not in norms
    assert any("bugun" in n and "toplam fatura sayisi" in n for n in norms)
    assert any("bugun" in n and "fatura" in n for n in norms)


def test_list_and_sum_combos_are_cartesian():
    list_plan = LogicalPlan(family="LIST_ENTITY", entity="invoice", physical_table="faturalar")
    sum_plan = LogicalPlan(family="SUM_MEASURE", entity="invoice", physical_table="faturalar")
    list_qs = generate_questions(list_plan, expand=True)
    sum_qs = generate_questions(sum_plan, expand=True)
    list_n = {normalize_question(q) for q in list_qs}
    sum_n = {normalize_question(q) for q in sum_qs}
    assert any("fatura" in n and "listele" in n for n in list_n)
    assert any("son" in n and "fatura" in n for n in list_n)
    assert any("toplam fatura tutari" in n or "fatura toplami" in n for n in sum_n)
    assert len(list_qs) >= 80
    assert len(sum_qs) >= 40
    # SUM must not emit COUNT tails
    assert "toplam fatura sayisi" not in sum_n
