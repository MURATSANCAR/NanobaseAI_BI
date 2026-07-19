"""Dynamic follow-up question suggestions after a scenario hit."""

from __future__ import annotations

from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan


def followup_suggestions(plan: LogicalPlan) -> list[str]:
    """Adjacent analysis chips (UI) — do not change semantic rules."""
    entity = plan.entity
    out: list[str] = []
    if plan.family in ("LIST_ENTITY", "STATUS_FILTER", "AGING"):
        out.extend(
            [
                "Toplam tutarı göster.",
                "Müşterilere göre grupla.",
                "İptal edilenleri hariç tut.",
                "Şehirlere göre dağılımı göster.",
                "Önceki ay ile karşılaştır.",
            ]
        )
    elif plan.family == "SUM_MEASURE":
        out.extend(
            [
                "Şehirlere göre dağılımı göster.",
                "Önceki dönem ile karşılaştır.",
                "En yüksek tutarlı kayıtları getir.",
            ]
        )
    elif plan.family == "GROUP_MEASURE":
        out.extend(
            [
                "Önceki ay ile karşılaştır.",
                "En yüksek tutarlı 10 kaydı getir.",
            ]
        )
    else:
        out.append(f"{entity} listesini getir.")
    return out[:5]
