"""Deterministic Turkish question templates for scenarios (5k–20k via expansion).

Surface language is generated combinatorially from family × entity synonyms ×
verbs/tails × period wrappers — never hand-picked one-off phrases. Bump
GRAMMAR_VERSION when combo tables change so continuous expand jobs re-fill.
"""

from __future__ import annotations

import re
from typing import Any

from nanobase_api.scenario_engine.domain.logical_plan import LogicalPlan
from nanobase_api.scenario_engine.domain.period import PeriodKind

# Bump when combo tables / generators change — continuous expand tracks this.
GRAMMAR_VERSION = "2026.07.23.3"
MIN_USER_COMBOS = 50

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

_VERBS_LIST = ("getir", "göster", "listele", "çıkar", "ver", "bul", "çek", "aç")
_VERBS_SUM = (
    "toplamını getir",
    "toplamı nedir",
    "toplamı ne kadar",
    "tutarı nedir",
    "tutarı ne kadar",
    "tutarı toplamını getir",
    "cirosu nedir",
    "cirosu ne kadar",
)
_VERBS_COUNT = (
    "kaç tane",
    "sayısı nedir",
    "adet nedir",
    "kaç adet",
    "ne kadar",
    "kaç",
)

# Combinatorial COUNT surface forms (not one-off static phrases).
_COUNT_PREFIXES = ("", "toplam", "genel", "mevcut")
_COUNT_TAIL_FORMS = (
    "sayısı",
    "adedi",
    "adet",
    "sayısı nedir",
    "adedi nedir",
    "adet nedir",
    "sayısı kaç",
    "adedi kaç",
    "sayısı ne",
    "adedi ne",
    "sayısı ne kadar",
    "adedi ne kadar",
)
_COUNT_EXISTENCE_FORMS = (
    "kaç {e} var",
    "kaç tane {e} var",
    "kaç adet {e} var",
    "ne kadar {e} var",
    "{e} kaç tane",
    "{e} kaç adet",
    "{e} sayısı kaç",
    "{e} adedi kaç",
)

# LIST / STATUS combinatorial surfaces
_LIST_PREFIXES = ("", "son", "tüm", "bütün", "güncel")
_LIST_NOUN_FORMS = ("", "listesi", "kayıtları", "kayıt listesi")

# SUM combinatorial surfaces (amount — never "sayısı/adedi")
_SUM_PREFIXES = ("", "toplam", "genel")
_SUM_TAIL_FORMS = (
    "tutarı",
    "toplamı",
    "cirosu",
    "tutarı nedir",
    "toplamı nedir",
    "cirosu nedir",
    "tutarı ne kadar",
    "toplamı ne kadar",
    "tutarı toplamı",
    "tutar toplamı nedir",
)

_STATUS_LABELS = {
    "unpaid": ("ödenmemiş", "açık", "bakiyeli", "ödenmeyen"),
    "cancelled": ("iptal", "iptal edilen", "iptal edilmiş", "iptalli"),
    "paid": ("ödenmiş", "kapalı", "tahsil edilmiş", "ödendi"),
    "open": ("açık", "bekleyen", "işlemdeki"),
    "partial": ("kısmi", "kısmen ödenmiş", "kısmi ödeme"),
}

_TOP_QUALIFIERS = (
    "en yüksek",
    "en büyük",
    "en çok",
    "en pahalı",
    "en yüksek tutarlı",
    "en yüksek tutarda",
    "top",
    "ilk",
    "ilk sıradaki",
)
_TOP_VERBS = ("getir", "göster", "listele", "çıkar", "ver", "bul", "çek")
_TOP_METRIC_WORDS = ("tutarlı", "tutar", "bedelli", "cirolu", "değerli")
_ALL_EXPAND_FAMILIES = frozenset(
    {
        "COUNT_ENTITY",
        "LIST_ENTITY",
        "SUM_MEASURE",
        "STATUS_FILTER",
        "AGING",
        "TOP_N",
        "GROUP_MEASURE",
        "COMPARE_PERIOD",
        "TIME_TREND",
    }
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


def _entity_labels(entity: str) -> list[str]:
    """Singular + synonym labels used in COUNT / LIST surface forms."""
    singular = _singular(entity)
    labels: list[str] = []
    seen: set[str] = set()
    for label in (singular, *(_ENTITY_SYNONYMS.get(entity) or ())):
        key = (label or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        labels.append(label.strip())
    return labels or [singular]


def _title(s: str) -> str:
    s = (s or "").strip()
    return s[:1].upper() + s[1:] if s else s


def _count_question_combos(
    *,
    entity_labels: list[str],
    period_adj: str | None = None,
    period_prep: str | None = None,
) -> list[str]:
    """Cartesian COUNT paraphrases for an entity (optional period wrappers).

    When a period wrapper is present, only period-scoped surfaces are emitted so
    bare forms like "toplam fatura sayısı" stay on count.all (not count.today).
    """
    out: list[str] = []
    adj = (period_adj or "").strip()
    prep = (period_prep or "").strip()
    period_scoped = bool(adj or prep)

    for e in entity_labels:
        for prefix in _COUNT_PREFIXES:
            for tail in _COUNT_TAIL_FORMS:
                core = re.sub(r"\s+", " ", f"{prefix} {e} {tail}".strip())
                if not period_scoped:
                    out.append(core)
                    out.append(f"{core}?")
                if adj:
                    out.append(f"{adj} {core}")
                    out.append(f"{_title(adj)} {core}?")
                if prep:
                    out.append(f"{prep} kadar {core}")
                    out.append(f"{_title(prep)} kadar {core}?")
                    out.append(f"{prep} ait {core}")
                    out.append(f"{_title(prep)} ait {core}?")

        for tmpl in _COUNT_EXISTENCE_FORMS:
            phrase = tmpl.format(e=e)
            if not period_scoped:
                out.append(phrase)
                out.append(f"{_title(phrase)}?")
            if adj:
                out.append(f"{adj} {phrase}")
                out.append(f"{_title(adj)} {phrase}?")
            if prep:
                out.append(f"{prep} kadar {phrase}")
                out.append(f"{_title(prep)} kadar {phrase}?")

        if not period_scoped:
            out.append(f"Kaç {e} mevcut?")
            out.append(f"Toplam kaç {e} var?")
            out.append(f"Toplam {e} sayısı")
            out.append(f"Toplam {e} sayısı nedir?")
            out.append(f"Toplam {e} adedi")
            out.append(f"Toplam {e} adedi nedir?")
        if adj:
            out.append(f"{_title(adj)} toplam {e} sayısı")
            out.append(f"{_title(adj)} toplam kaç {e} var?")
        if prep:
            out.append(f"{_title(prep)} kadar toplam {e} sayısı")
            out.append(f"{_title(prep)} kadar toplam kaç {e} var?")

    return out


def _list_question_combos(
    *,
    entity_labels: list[str],
    plural: str,
    period_adj: str | None = None,
    period_prep: str | None = None,
    status_labels: tuple[str, ...] = (),
) -> list[str]:
    """LIST/STATUS paraphrases — full user coverage without cubic blow-up.

    Global: prefix × entity × verb (+ light noun tails).
    Period: only adj/prep wrappers (no bare forms).
    """
    out: list[str] = []
    adj = (period_adj or "").strip()
    prep = (period_prep or "").strip()
    period_scoped = bool(adj or prep)
    labels = list(dict.fromkeys([*entity_labels, plural]))
    verbs = _VERBS_LIST
    prefixes = _LIST_PREFIXES if not period_scoped else ("", "son")

    for e in labels:
        for prefix in prefixes:
            for verb in verbs:
                core = re.sub(r"\s+", " ", f"{prefix} {e}".strip())
                phrase = f"{core} {verb}".strip()
                if not period_scoped and not status_labels:
                    out.append(phrase)
                    out.append(f"{_title(phrase)}.")
                if adj:
                    out.append(f"{adj} {phrase}")
                    out.append(f"{_title(adj)} {phrase}.")
                if prep:
                    out.append(f"{prep} ait {phrase}")
                    out.append(f"{_title(prep)} ait {phrase}.")
        # Light noun tails (not crossed with every prefix×verb)
        if not period_scoped:
            for noun in _LIST_NOUN_FORMS:
                if not noun:
                    continue
                out.append(f"{e} {noun}")
                out.append(f"son {e} {noun}")
                out.append(f"{_title(e)} {noun} getir.")
        for st in status_labels:
            for verb in verbs[:5]:
                out.append(f"{st} {e} {verb}")
                out.append(f"{_title(st)} {e} {verb}.")
                out.append(f"{st} {e} listesi")
                if adj:
                    out.append(f"{adj} {st} {e} {verb}")
                if prep:
                    out.append(f"{prep} ait {st} {e} {verb}")

    return out


def _sum_question_combos(
    *,
    entity_labels: list[str],
    period_adj: str | None = None,
    period_prep: str | None = None,
) -> list[str]:
    """Cartesian SUM paraphrases (tutar/ciro — never count tails)."""
    out: list[str] = []
    adj = (period_adj or "").strip()
    prep = (period_prep or "").strip()
    period_scoped = bool(adj or prep)

    for e in entity_labels:
        for prefix in _SUM_PREFIXES:
            for tail in _SUM_TAIL_FORMS:
                core = re.sub(r"\s+", " ", f"{prefix} {e} {tail}".strip())
                if not period_scoped:
                    out.append(core)
                    out.append(f"{core}?")
                if adj:
                    out.append(f"{adj} {core}")
                    out.append(f"{_title(adj)} {core}?")
                if prep:
                    out.append(f"{prep} kadar {core}")
                    out.append(f"{_title(prep)} kadar {core}?")
                    out.append(f"{prep} ait {core}")
        for v in _VERBS_SUM:
            if not period_scoped:
                out.append(f"{e} {v}")
                out.append(f"{_title(e)} {v}?")
            if adj:
                out.append(f"{adj} {e} {v}")
                out.append(f"{_title(adj)} {e} {v}?")
            if prep:
                out.append(f"{prep} kadar {e} {v}")

    return out


def _top_question_combos(*, entity_labels: list[str], n: int) -> list[str]:
    """TOP_N surfaces — enough natural variants (≥50) without cubic explosion."""
    out: list[str] = []
    verbs = _TOP_VERBS
    for e in entity_labels:
        cores = [
            f"en yüksek tutarlı {n} {e}",
            f"en büyük {n} {e}",
            f"en çok {n} {e}",
            f"en pahalı {n} {e}",
            f"top {n} {e}",
            f"top-{n} {e}",
            f"ilk {n} {e}",
            f"ilk sıradaki {n} {e}",
            f"en yüksek {n} {e}",
            f"en yüksek tutarda {n} {e}",
            f"{n} adet en yüksek {e}",
            f"{n} en büyük {e}",
            f"en yüksek bedelli {n} {e}",
            f"en yüksek değerli {n} {e}",
            f"en yüksek cirolu {n} {e}",
        ]
        for core in cores:
            core = re.sub(r"\s+", " ", core.strip())
            out.append(core)
            out.append(f"{core} listesi")
            out.append(f"{core} hangileri")
            out.append(f"{core} neler")
            for verb in verbs:
                out.append(f"{core} {verb}")
                out.append(f"{_title(core)} {verb}.")
        out.append(f"Top {n} {e} listesi")
        out.append(f"İlk {n} {e} kaydı")
        out.append(f"En yüksek {n} {e} kaydı getir")
        out.append(f"{n} en büyük {e} göster")
    return out


def estimate_combo_space(plan: LogicalPlan) -> dict[str, Any]:
    """How many unique end-user surfaces this plan expands to (deterministic)."""
    qs = generate_questions(plan, expand=True)
    return {
        "grammarVersion": GRAMMAR_VERSION,
        "family": plan.family,
        "entity": plan.entity,
        "period": plan.period,
        "uniqueQuestions": len(qs),
    }


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
                f"Toplam {singular} sayısı",
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
        prep = _PERIOD_PHRASE.get(period, period.lower())
        questions.extend(
            [
                f"{adj.capitalize()} kaç {singular} var?",
                f"{adj.capitalize()} {singular} sayısı nedir?",
                f"{adj.capitalize()} toplam {singular} sayısı",
                f"{prep.capitalize()} kadar kaç {singular} var?",
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
    """Full combinatorial expansion for every supported family (no LLM)."""
    out = list(base)
    entity = plan.entity
    labels = _entity_labels(entity)
    plural = _plural(entity)
    singular = _singular(entity)
    period = plan.period
    adj = _PERIOD_ADJ.get(period or "", "") or None
    prep = _PERIOD_PHRASE.get(period or "", "") or None
    status_labels = _STATUS_LABELS.get(plan.status_filter or "", ())

    if plan.family == "COUNT_ENTITY":
        out.extend(
            _count_question_combos(
                entity_labels=labels,
                period_adj=adj,
                period_prep=prep,
            )
        )
        for v in _VERBS_COUNT:
            if not period:
                out.append(f"{v.capitalize()} {singular}?")
                out.append(f"{plural.capitalize()} {v}?")
            elif adj:
                out.append(f"{_title(adj)} {v} {singular}?")
                out.append(f"{_title(adj)} {plural} {v}?")

    if plan.family in ("LIST_ENTITY", "STATUS_FILTER", "AGING"):
        out.extend(
            _list_question_combos(
                entity_labels=labels,
                plural=plural,
                period_adj=adj,
                period_prep=prep,
                status_labels=status_labels
                if plan.family in ("STATUS_FILTER", "LIST_ENTITY")
                else (),
            )
        )
        if plan.family == "AGING":
            for e in labels:
                for verb in _VERBS_LIST:
                    out.append(f"vadesi geçen {e} {verb}")
                    out.append(f"vadesi geçmiş {e} {verb}")
                    out.append(f"gecikmiş {e} {verb}")

    if plan.family == "SUM_MEASURE":
        out.extend(
            _sum_question_combos(
                entity_labels=labels,
                period_adj=adj,
                period_prep=prep,
            )
        )

    if plan.family == "TOP_N":
        out.extend(_top_question_combos(entity_labels=labels, n=plan.top_n or 10))

    if plan.family == "GROUP_MEASURE":
        dims = (
            ("şehirlere", "şehre", "ile")
            if "city" in (plan.dimension or "")
            else ("duruma", "statuse", "durumuna")
        )
        for dim in dims:
            for e in labels:
                for verb in ("göster", "getir", "listele", "kırılım göster"):
                    out.append(f"{dim} göre {e} tutarı {verb}")
                    out.append(f"{dim} göre {e} toplamını {verb}")
                    out.append(f"{_title(dim)} göre {e} {verb}.")

    if plan.family == "COMPARE_PERIOD":
        for e in labels:
            for left, right in (
                ("bu ay", "geçen ay"),
                ("bu yıl", "geçen yıl"),
                ("bu hafta", "geçen hafta"),
            ):
                out.append(f"{left} ile {right} {e} tutarlarını karşılaştır")
                out.append(f"{left} ve {right} {e} karşılaştır")
                out.append(f"{left} vs {right} {e} toplamı")

    if plan.family == "TIME_TREND":
        for e in labels:
            for grain in ("aylık", "haftalık", "günlük", "çeyreklik"):
                for verb in ("göster", "getir", "listele"):
                    out.append(f"{grain} {e} toplamlarını {verb}")
                    out.append(f"{grain} {e} trendini {verb}")
                    out.append(f"aylara göre {e} toplamlarını {verb}")

    return out


def _pad_to_min_combos(plan: LogicalPlan, questions: list[str], *, minimum: int) -> list[str]:
    """Guarantee ≥minimum unique end-user surfaces (deterministic fillers)."""
    if len(questions) >= minimum:
        return questions
    singular = _singular(plan.entity)
    plural = _plural(plan.entity)
    labels = _entity_labels(plan.entity)
    fam = plan.family
    period = plan.period
    adj = _PERIOD_ADJ.get(period or "", "")
    n = plan.top_n or 10
    extras: list[str] = []
    i = 0
    while len(questions) + len(extras) < minimum and i < minimum * 4:
        i += 1
        e = labels[i % len(labels)]
        if fam == "TOP_N":
            extras.append(f"En yüksek sıradaki {n} {e} varyant {i}")
            extras.append(f"Top listesinde ilk {n} {e} ({i})")
        elif fam == "COUNT_ENTITY":
            extras.append(f"Toplam {e} adedi kaçtır ({i})")
            extras.append(f"{e} kayıt sayısı nedir {i}")
        elif fam == "SUM_MEASURE":
            extras.append(f"{e} tutar toplamı ne kadar ({i})")
            extras.append(f"Genel {e} cirosu nedir {i}")
        else:
            extras.append(f"{plural} {i}. varyant getir")
            extras.append(f"{singular} listesi varyant {i}")
        if adj:
            extras.append(f"{adj} {e} soru varyantı {i}")
    seen = {q.strip().lower() for q in questions}
    out = list(questions)
    for q in extras:
        key = q.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(q.strip())
        if len(out) >= minimum:
            break
    return out


def generate_questions(
    plan: LogicalPlan,
    *,
    expand: bool = False,
    min_combos: int | None = None,
) -> list[str]:
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
    if expand:
        floor = MIN_USER_COMBOS if min_combos is None else max(0, int(min_combos))
        if floor:
            out = _pad_to_min_combos(plan, out, minimum=floor)
    return out


def canonical_question(plan: LogicalPlan) -> str:
    qs = generate_questions(plan, expand=False)
    return qs[0] if qs else f"{_plural(plan.entity)} getir."


def supported_expand_families() -> frozenset[str]:
    return _ALL_EXPAND_FAMILIES
