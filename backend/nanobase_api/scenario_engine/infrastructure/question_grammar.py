"""Deterministic Turkish question templates for scenarios (5k–20k via expansion)."""

from __future__ import annotations

from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.period import PeriodKind

_ENTITY_PLURAL = {
    "invoice": "faturaları",
    "customer": "müşterileri",
    "product": "ürünleri",
    "order": "siparişleri",
    "payment": "ödemeleri",
    "stock": "stokları",
    "finance": "finans kayıtlarını",
    "invoice_line": "fatura kalemlerini",
    "product_category": "ürün kategorilerini",
    "brand": "markaları",
    "branch": "şubeleri",
    "staff": "personeli",
    "price_list_item": "fiyat listesi kalemlerini",
}

_ENTITY_SINGULAR = {
    "invoice": "fatura",
    "customer": "müşteri",
    "product": "ürün",
    "order": "sipariş",
    "payment": "ödeme",
    "stock": "stok",
    "finance": "finans kaydı",
    "invoice_line": "fatura kalemi",
    "product_category": "ürün kategorisi",
    "brand": "marka",
    "branch": "şube",
    "staff": "personel",
    "price_list_item": "fiyat listesi kalemi",
}

_ENTITY_SYNONYMS = {
    "invoice": ("fatura", "faturalar", "satış faturası", "satis faturasi"),
    "customer": ("müşteri", "musteri", "cari", "müşteriler"),
    "product": ("ürün", "urun", "malzeme", "ürünler"),
    "order": ("sipariş", "siparis", "satış siparişi"),
    "payment": ("ödeme", "odeme", "tahsilat"),
    "stock": ("stok", "stok bakiyesi", "envanter"),
    "branch": ("şube", "sube"),
    "staff": ("personel", "çalışan"),
}

_VERBS_LIST = ("getir", "göster", "listele", "çıkar", "ver", "bul")
_VERBS_SUM = ("toplamını getir", "toplamı nedir", "tutarı nedir", "tutarı ne kadar")
_VERBS_COUNT = (
    "kaç tane",
    "sayısı nedir",
    "adet nedir",
    "kaç adet",
    "ne kadar",
    "kaç",
)

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
    PeriodKind.YESTERDAY.value: "dünki",
    PeriodKind.CURRENT_WEEK.value: "bu haftaki",
    PeriodKind.PREVIOUS_WEEK.value: "geçen haftaki",
    PeriodKind.CURRENT_MONTH.value: "bu ayki",
    PeriodKind.PREVIOUS_MONTH.value: "geçen ayki",
    PeriodKind.CURRENT_YEAR.value: "bu yılki",
    PeriodKind.PREVIOUS_YEAR.value: "geçen yılki",
    PeriodKind.CURRENT_QUARTER.value: "bu çeyrekteki",
    PeriodKind.PREVIOUS_QUARTER.value: "geçen çeyrekteki",
    PeriodKind.MONTH_TO_DATE.value: "ay başından bugüne olan",
    PeriodKind.YEAR_TO_DATE.value: "yıl başından bugüne olan",
}


def _humanize_table(entity: str) -> tuple[str, str]:
    """Fallback singular/plural from entity/table code."""
    raw = (entity or "kayit").replace("_", " ").strip()
    # crude TR plural: append -lar/-ler if not already plural-looking
    if raw.endswith(("lar", "ler", "ları", "leri")):
        plural = raw
        singular = raw
        for suf in ("ları", "leri", "lar", "ler"):
            if raw.endswith(suf):
                singular = raw[: -len(suf)] or raw
                break
    else:
        singular = raw
        plural = f"{raw} kayıtları"
    return singular, plural


def _plural(entity: str) -> str:
    if entity in _ENTITY_PLURAL:
        return _ENTITY_PLURAL[entity]
    _, plural = _humanize_table(entity)
    return plural


def _singular(entity: str) -> str:
    if entity in _ENTITY_SINGULAR:
        return _ENTITY_SINGULAR[entity]
    singular, _ = _humanize_table(entity)
    return singular


def _base_questions(plan: LogicalPlan) -> list[str]:
    entity = plan.entity
    plural = _plural(entity)
    singular = _singular(entity)
    period = plan.period
    questions: list[str] = []

    if plan.family == "COUNT_ENTITY" and not period:
        questions.extend(
            [
                f"Kaç {singular} var?",
                f"{singular.capitalize()} sayısı nedir?",
                f"Toplam {singular} adedi nedir?",
                f"{plural.capitalize()} kaç tane?",
            ]
        )
    elif plan.family in ("LIST_ENTITY", "STATUS_FILTER") and not period and not plan.status_filter:
        questions.extend(
            [
                f"{plural.capitalize()} getir.",
                f"{plural.capitalize()} listele.",
                f"{plural.capitalize()} göster.",
                f"Son {plural} getir.",
            ]
        )
    elif plan.family in ("LIST_ENTITY", "STATUS_FILTER") and period and not plan.status_filter:
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
    elif plan.family in ("LIST_ENTITY", "STATUS_FILTER") and plan.status_filter == "cancelled":
        questions.extend(
            [
                f"İptal edilen {plural} getir.",
                f"İptal {plural} göster.",
                f"İptal edilmiş {singular} listesi.",
            ]
        )
    elif plan.family in ("LIST_ENTITY", "STATUS_FILTER") and plan.status_filter in (
        "open",
        "partial",
        "unpaid",
    ):
        questions.extend(
            [
                f"Ödenmemiş {plural} getir.",
                f"Açık {plural} göster.",
                f"Ödenmemiş {singular} listesi.",
            ]
        )
    elif plan.family == "STATUS_FILTER" and plan.status_filter == "paid":
        questions.extend([f"Ödenmiş {plural} getir.", f"Kapalı {plural} göster."])
    elif plan.family == "AGING":
        questions.extend(
            [
                f"Vadesi geçen {plural} getir.",
                f"Vadesi geçmiş {plural} göster.",
                f"Gecikmiş {plural} listele.",
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
                f"{adj.capitalize()} {singular} tutarı toplamını getir.",
                f"{adj.capitalize()} satış tutarı nedir?",
            ]
        )
    elif plan.family == "SUM_MEASURE":
        questions.extend(
            [
                f"{plural.capitalize()} toplamı nedir?",
                f"{singular.capitalize()} tutarı toplamını getir.",
            ]
        )
    elif plan.family == "TOP_N":
        n = plan.top_n or 10
        questions.extend(
            [
                f"En yüksek tutarlı {n} {singular}yı getir.",
                f"En yüksek tutarlı {plural} göster.",
                f"Top {n} {singular}.",
            ]
        )
    elif plan.family == "GROUP_MEASURE" and plan.dimension:
        dim = "şehirlere" if "city" in (plan.dimension or "") else "duruma"
        questions.extend(
            [
                f"{dim.capitalize()} göre {singular} tutarı nedir?",
                f"{dim.capitalize()} göre {plural} toplamını göster.",
            ]
        )
    elif plan.family == "COMPARE_PERIOD":
        questions.extend(
            [
                f"Bu ay ile geçen ay {singular} tutarlarını karşılaştır.",
                f"Bu ay ve geçen ay {plural} karşılaştır.",
            ]
        )
    elif plan.family == "TIME_TREND":
        questions.extend(
            [
                f"Aylara göre {singular} toplamlarını göster.",
                f"Aylık {singular} toplamlarını getir.",
            ]
        )
    else:
        questions.append(f"{plural.capitalize()} getir.")

    return questions


def _expand_variants(plan: LogicalPlan, base: list[str]) -> list[str]:
    """Template expansion + limited synonym lists (no LLM)."""
    out = list(base)
    entity = plan.entity
    synonyms = _ENTITY_SYNONYMS.get(entity, ())
    plural = _plural(entity)
    singular = _singular(entity)
    period = plan.period
    adj = _PERIOD_ADJ.get(period or "", "")
    prep = _PERIOD_PHRASE.get(period or "", "")

    if plan.family == "COUNT_ENTITY" and not period:
        for v in _VERBS_COUNT:
            out.append(f"{v.capitalize()} {singular}?")
            out.append(f"{plural.capitalize()} {v}?")
        for syn in synonyms or (singular,):
            out.append(f"Kaç {syn} var?")
            out.append(f"{syn.capitalize()} sayısı nedir?")

    if plan.family in ("LIST_ENTITY", "STATUS_FILTER", "AGING"):
        for verb in _VERBS_LIST:
            out.append(f"{plural.capitalize()} {verb}.")
            if adj:
                out.append(f"{adj.capitalize()} {plural} {verb}.")
            if prep:
                out.append(f"{prep.capitalize()} ait {plural} {verb}.")
        for syn in synonyms:
            for verb in _VERBS_LIST[:4]:
                out.append(f"{syn.capitalize()} {verb}.")
                if adj:
                    out.append(f"{adj.capitalize()} {syn} {verb}.")

    if plan.family == "SUM_MEASURE":
        for v in _VERBS_SUM:
            if adj:
                out.append(f"{adj.capitalize()} {plural} {v}?")
                out.append(f"{adj.capitalize()} {singular} {v}?")
            else:
                out.append(f"{plural.capitalize()} {v}?")
        for syn in synonyms:
            if adj:
                out.append(f"{adj.capitalize()} {syn} toplamı nedir?")

    if plan.family == "COUNT_ENTITY" and period:
        for v in _VERBS_COUNT:
            if adj:
                out.append(f"{adj.capitalize()} {v} {singular}?")
                out.append(f"{adj.capitalize()} {plural} {v}?")
        if prep:
            # Natural TR: "… kadar ne kadar X var / kaç X'imiz var"
            out.append(f"{prep.capitalize()} kadar ne kadar {singular} var?")
            out.append(f"{prep.capitalize()} kadar ne kadar {plural} var?")
            out.append(f"{prep.capitalize()} kadar kaç {singular} var?")
            out.append(f"{prep.capitalize()} kadar kaç {singular}mız var?")
            out.append(f"{prep.capitalize()} kadar kaç {singular}miz var?")
            for syn in synonyms or ():
                out.append(f"{prep.capitalize()} kadar ne kadar {syn} var?")
                out.append(f"{prep.capitalize()} kadar kaç {syn} var?")

    if plan.family == "TOP_N":
        n = plan.top_n or 10
        for syn in synonyms or (singular,):
            out.append(f"En büyük {n} {syn}.")
            out.append(f"İlk {n} {syn} getir.")
            out.append(f"Top-{n} {syn} listesi.")

    if plan.family == "GROUP_MEASURE":
        dim = "şehre" if "city" in (plan.dimension or "") else "statuse"
        for verb in ("göster", "getir", "listele"):
            out.append(f"{dim.capitalize()} göre kırılım {verb}.")
            out.append(f"{dim.capitalize()} göre toplam {verb}.")

    if plan.status_filter:
        st_map = {
            "unpaid": ("ödenmemiş", "açık", "bakiyeli"),
            "cancelled": ("iptal", "iptal edilen", "iptal edilmiş"),
            "paid": ("ödenmiş", "kapalı", "tahsil edilmiş"),
            "open": ("açık", "bekleyen"),
            "partial": ("kısmi", "kısmen ödenmiş"),
        }
        for label in st_map.get(plan.status_filter, ()):
            for verb in _VERBS_LIST[:4]:
                out.append(f"{label.capitalize()} {plural} {verb}.")

    return out


def generate_questions(plan: LogicalPlan, *, expand: bool = False) -> list[str]:
    """Return canonical + paraphrase variants (deterministic grammar only)."""
    questions = _base_questions(plan)
    if expand:
        questions = _expand_variants(plan, questions)

    seen: set[str] = set()
    out: list[str] = []
    for q in questions:
        key = q.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(q.strip())
    return out


def canonical_question(plan: LogicalPlan) -> str:
    qs = generate_questions(plan, expand=False)
    return qs[0] if qs else f"{_plural(plan.entity)} getir."
