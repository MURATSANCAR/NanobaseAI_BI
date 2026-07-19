"""Deterministic Turkish question templates for scenarios."""

from __future__ import annotations

from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.period import PeriodKind

_ENTITY_PLURAL = {
    "invoice": "faturaları",
    "customer": "müşterileri",
    "product": "ürünleri",
    "order": "siparişleri",
    "payment": "ödemeleri",
}

_ENTITY_SINGULAR = {
    "invoice": "fatura",
    "customer": "müşteri",
    "product": "ürün",
    "order": "sipariş",
    "payment": "ödeme",
}

_PERIOD_PHRASE = {
    PeriodKind.TODAY.value: "bugüne",
    PeriodKind.YESTERDAY.value: "düne",
    PeriodKind.CURRENT_WEEK.value: "bu haftaya",
    PeriodKind.PREVIOUS_WEEK.value: "geçen haftaya",
    PeriodKind.CURRENT_MONTH.value: "bu aya",
    PeriodKind.PREVIOUS_MONTH.value: "geçen aya",
    PeriodKind.CURRENT_YEAR.value: "bu yıla",
    PeriodKind.PREVIOUS_YEAR.value: "geçen yıla",
    PeriodKind.CURRENT_QUARTER.value: "bu çeyreğe",
    PeriodKind.PREVIOUS_QUARTER.value: "geçen çeyreğe",
    PeriodKind.MONTH_TO_DATE.value: "ay başından bugüne",
    PeriodKind.YEAR_TO_DATE.value: "yıl başından bugüne",
}

_PERIOD_ADJ = {
    PeriodKind.TODAY.value: "bugünkü",
    PeriodKind.YESTERDAY.value: "dünkü",
    PeriodKind.CURRENT_WEEK.value: "bu haftaki",
    PeriodKind.PREVIOUS_WEEK.value: "geçen haftaki",
    PeriodKind.CURRENT_MONTH.value: "bu ayki",
    PeriodKind.PREVIOUS_MONTH.value: "geçen ayki",
    PeriodKind.CURRENT_YEAR.value: "bu yılki",
    PeriodKind.PREVIOUS_YEAR.value: "geçen yılki",
}


def _plural(entity: str) -> str:
    return _ENTITY_PLURAL.get(entity, f"{entity} kayıtları")


def _singular(entity: str) -> str:
    return _ENTITY_SINGULAR.get(entity, entity)


def generate_questions(plan: LogicalPlan) -> list[str]:
    """Return canonical + paraphrase variants (deterministic grammar only)."""
    entity = plan.entity
    plural = _plural(entity)
    singular = _singular(entity)
    period = plan.period
    questions: list[str] = []

    if plan.family in ("LIST_ENTITY", "STATUS_FILTER") and period:
        prep = _PERIOD_PHRASE.get(period, period.lower())
        adj = _PERIOD_ADJ.get(period, prep)
        questions.extend(
            [
                f"{prep.capitalize()} ait {plural} getir.",
                f"{adj.capitalize()} {plural} göster.",
                f"{adj.capitalize()} {plural} listele.",
                f"{prep.capitalize()} kayıtlı {plural} göster.",
            ]
        )
    elif plan.family == "LIST_ENTITY" and plan.status_filter == "cancelled":
        questions.extend(
            [
                f"İptal edilen {plural} getir.",
                f"İptal {plural} göster.",
            ]
        )
    elif plan.family == "LIST_ENTITY" and plan.status_filter in ("open", "partial", "unpaid"):
        questions.extend(
            [
                f"Ödenmemiş {plural} getir.",
                f"Açık {plural} göster.",
            ]
        )
    elif plan.family == "AGING":
        questions.extend(
            [
                f"Vadesi geçen {plural} getir.",
                f"Vadesi geçmiş {plural} göster.",
            ]
        )
    elif plan.family == "COUNT_ENTITY" and period:
        adj = _PERIOD_ADJ.get(period, period.lower())
        questions.extend(
            [
                f"{adj.capitalize()} kaç {singular} var?",
                f"{adj.capitalize()} {singular} sayısı nedir?",
            ]
        )
    elif plan.family == "SUM_MEASURE" and period:
        adj = _PERIOD_ADJ.get(period, period.lower())
        questions.extend(
            [
                f"{adj.capitalize()} {plural} toplamı nedir?",
                f"{adj.capitalize()} fatura tutarı toplamını getir.",
            ]
        )
    elif plan.family == "TOP_N":
        n = plan.top_n or 10
        questions.extend(
            [
                f"En yüksek tutarlı {n} {singular}yı getir.",
                f"En yüksek tutarlı {plural} göster.",
            ]
        )
    elif plan.family == "GROUP_MEASURE" and plan.dimension:
        dim = "şehirlere" if "city" in (plan.dimension or "") else "duruma"
        questions.extend(
            [
                f"{dim.capitalize()} göre satış tutarı nedir?",
                f"{dim.capitalize()} göre fatura toplamını göster.",
            ]
        )
    elif plan.family == "COMPARE_PERIOD":
        questions.extend(
            [
                "Bu ay ile geçen ay fatura tutarlarını karşılaştır.",
                "Bu ay ve geçen ay satışları karşılaştır.",
            ]
        )
    elif plan.family == "TIME_TREND":
        questions.extend(
            [
                "Aylara göre fatura toplamlarını göster.",
                "Aylık fatura toplamlarını getir.",
            ]
        )
    else:
        if plan.canonical_hint if hasattr(plan, "canonical_hint") else None:
            pass
        questions.append(f"{plural.capitalize()} getir.")

    # Deduplicate preserve order
    seen: set[str] = set()
    out: list[str] = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out


def canonical_question(plan: LogicalPlan) -> str:
    qs = generate_questions(plan)
    return qs[0] if qs else f"{_plural(plan.entity)} getir."
