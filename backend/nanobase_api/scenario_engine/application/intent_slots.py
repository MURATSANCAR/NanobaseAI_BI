"""Generic NL intent slots for scenario matching — period / family / entity.

Not table-specific hardcodes: entity fingerprints come from scenario entity codes
and physical table names; period/family use ordered Turkish phrase patterns.
"""

from __future__ import annotations

import re
from typing import Iterable

from nanobase_api.scenario_engine.domain.period import PeriodKind
from nanobase_api.scenario_engine.domain.scenario import normalize_question

# Longest / most specific first — "yil basindan bugune" must beat bare "bugun(e)".
_PERIOD_PATTERNS: list[tuple[re.Pattern[str], PeriodKind]] = [
    (re.compile(r"\by[iı]l\s+bas[iı]ndan(\s+bug[uü]ne)?(\s+kadar)?\b", re.I), PeriodKind.YEAR_TO_DATE),
    (re.compile(r"\bay\s+bas[iı]ndan(\s+bug[uü]ne)?(\s+kadar)?\b", re.I), PeriodKind.MONTH_TO_DATE),
    (re.compile(r"\bge[cç]en\s+y[iı]l(ki|a|ın)?\b", re.I), PeriodKind.PREVIOUS_YEAR),
    (re.compile(r"\bbu\s+y[iı]l(ki|a|ın|da)?\b", re.I), PeriodKind.CURRENT_YEAR),
    (re.compile(r"\bge[cç]en\s+[cç]eyrek\b", re.I), PeriodKind.PREVIOUS_QUARTER),
    (re.compile(r"\bbu\s+[cç]eyrek\b", re.I), PeriodKind.CURRENT_QUARTER),
    (re.compile(r"\bge[cç]en\s+ay(ki|a|ın)?\b", re.I), PeriodKind.PREVIOUS_MONTH),
    (re.compile(r"\bbu\s+ay(ki|a|ın)?\b", re.I), PeriodKind.CURRENT_MONTH),
    (re.compile(r"\bge[cç]en\s+hafta(ki|ya)?\b", re.I), PeriodKind.PREVIOUS_WEEK),
    (re.compile(r"\bbu\s+hafta(ki|ya)?\b", re.I), PeriodKind.CURRENT_WEEK),
    (re.compile(r"\bd[uü]n(e|ki|ün)?\b", re.I), PeriodKind.YESTERDAY),
    # Bare "bugün(e/ki)" last — after YTD/MTD phrases that also contain "bugüne"
    (re.compile(r"\bbug[uü]n(e|ki|ün)?\b", re.I), PeriodKind.TODAY),
]

# Known semantic aliases → boost entity codes that are not literal table names
_ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "invoice": ("fatura", "faturalar", "faturalari", "satis", "satislar"),
    "customer": ("musteri", "musteriler", "cari", "cariler"),
    "product": ("urun", "urunler", "malzeme"),
    "order": ("siparis", "siparisler"),
    "payment": ("odeme", "odemeler", "tahsilat"),
    "stock": ("stok", "stoklar", "envanter"),
    "branch": ("sube", "subeler"),
    "staff": ("personel", "calisan"),
}

_STOP = frozenset(
    {
        "olan",
        "olanı",
        "olanlari",
        "kadar",
        "ait",
        "icin",
        "ile",
        "bir",
        "bu",
        "su",
        "ve",
        "veya",
        "nedir",
        "mi",
        "mı",
        "mu",
        "mü",
        "var",
        "yok",
        "kayit",
        "kayitlari",
        "kayitlar",
        "tane",
        "adet",
        "ne",
        "nasil",
        "hangi",
        "benim",
        "bizim",
    }
)

_STEM_SUFFIXES = (
    "larimiz",
    "lerimiz",
    "larimiz",
    "lerimiz",
    "larin",
    "lerin",
    "lari",
    "leri",
    "lar",
    "ler",
    "imiz",
    "umuz",
    "miz",
    "muz",
    "sin",
    "nin",
    "nun",
)


def detect_period(question: str) -> PeriodKind | None:
    """Return the most specific period mentioned in the question."""
    q = question or ""
    # Prefer normalized scan for ASCII-folded phrases, but keep original for ı/i
    candidates = (q, normalize_question(q))
    for text in candidates:
        for pat, kind in _PERIOD_PATTERNS:
            if pat.search(text):
                return kind
    return None


def detect_family(question: str) -> str | None:
    """Infer COUNT / SUM / LIST / TOP_N / STATUS / AGING from wording."""
    q = normalize_question(question or "")
    if not q:
        return None
    if re.search(r"\bvadesi\b|\bgecmis\b.*\bvade\b", q):
        return "AGING"
    if re.search(r"\biptal\b|\bodenmemis\b|\bacik\b.*\bfatura", q):
        # status filters only when clearly filter-ish; unpaid often list
        if "iptal" in q or "odenmemis" in q:
            return "STATUS_FILTER"
    if re.search(r"\ben (yuksek|buyuk|dusuk|kucuk)\b|\btop[-\s]?\d+\b|\bilk\s+\d+\b", q):
        return "TOP_N"
    # COUNT before SUM: "ne kadar X var/kaç" is cardinality, not amount
    if re.search(
        r"\bkac\b|\bsayisi\b|\bsayi\b|\badedi\b|\badet\b|"
        r"\bne kadar\b.+\b(var|mevcut)\b|\b(var|mevcut)\b.*\bne kadar\b|"
        r"\bne kadar\b.+\bfatura|\bfatura.+\bne kadar\b",
        q,
    ):
        # "ne kadar tutar/toplam/ciro" → SUM
        if re.search(r"\bne kadar\b.+\b(tutar|toplam|ciro|gelir|satis)\b", q) or re.search(
            r"\b(tutar|toplam|ciro)\b.+\bne kadar\b", q
        ):
            return "SUM_MEASURE"
        return "COUNT_ENTITY"
    if re.search(r"\btoplam\b|\btutari\b|\btutar\b|\bciro\b|\bsum\b", q):
        return "SUM_MEASURE"
    if re.search(r"\blistele\b|\bgoster\b|\bgetir\b|\bcikar\b|\bver\b|\bbul\b", q):
        return "LIST_ENTITY"
    return None


def _stem_token(tok: str) -> str:
    t = tok
    for suf in _STEM_SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def question_content_tokens(question: str) -> set[str]:
    q = normalize_question(question or "")
    out: set[str] = set()
    for raw in q.split():
        if raw in _STOP or len(raw) < 3:
            continue
        stem = _stem_token(raw)
        out.add(raw)
        out.add(stem)
    return out


def entity_fingerprint(entity: str, physical_table: str | None = None) -> set[str]:
    """Tokens that identify a scenario entity/table (generic from names)."""
    parts: set[str] = set()
    raws = [entity or ""]
    if physical_table:
        raws.append(physical_table.split(".")[-1])
    for raw in raws:
        norm = normalize_question(raw.replace(".", " ").replace("-", " "))
        for piece in re.split(r"[_\s]+", norm):
            if len(piece) < 3 or piece in _STOP:
                continue
            parts.add(piece)
            parts.add(_stem_token(piece))
    # semantic aliases for known domain codes
    ent = (entity or "").lower()
    for alias in _ENTITY_ALIASES.get(ent, ()):
        parts.add(alias)
        parts.add(_stem_token(alias))
    return {p for p in parts if p and len(p) >= 3}


def entity_score(question: str, entity: str, physical_table: str | None = None) -> float:
    """0–1 overlap between question tokens and entity/table fingerprint."""
    fp = entity_fingerprint(entity, physical_table)
    if not fp:
        return 0.0
    qtok = question_content_tokens(question)
    if not qtok:
        return 0.0
    inter = fp & qtok
    if not inter:
        # substring fallback: "alis" in "alisfaturasi" compound rare; check containment
        for f in fp:
            for t in qtok:
                if len(f) >= 4 and (f in t or t in f):
                    inter.add(f)
                    break
    if not inter:
        return 0.0
    # Prefer denser coverage of fingerprint (specific tables have more tokens)
    coverage = len(inter) / max(1, len(fp))
    precision = len(inter) / max(1, len(qtok))
    return round(min(1.0, 0.65 * coverage + 0.35 * min(1.0, precision * 3)), 4)


def period_score(question_period: PeriodKind | None, scenario_period: str | None) -> float:
    if question_period is None:
        return 0.55 if not scenario_period else 0.45
    if not scenario_period:
        return 0.25
    if scenario_period == question_period.value:
        return 1.0
    # Near-miss: CURRENT_YEAR vs YEAR_TO_DATE etc. — soft, not hard
    near = {
        PeriodKind.YEAR_TO_DATE.value: {PeriodKind.CURRENT_YEAR.value},
        PeriodKind.CURRENT_YEAR.value: {PeriodKind.YEAR_TO_DATE.value},
        PeriodKind.MONTH_TO_DATE.value: {PeriodKind.CURRENT_MONTH.value},
        PeriodKind.CURRENT_MONTH.value: {PeriodKind.MONTH_TO_DATE.value},
    }
    if scenario_period in near.get(question_period.value, set()):
        return 0.35
    return 0.0


def family_score(question_family: str | None, scenario_family: str) -> float:
    if question_family is None:
        return 0.55
    if scenario_family == question_family:
        return 1.0
    # COUNT vs LIST confusion is common — soft penalty
    if {question_family, scenario_family} <= {"COUNT_ENTITY", "LIST_ENTITY"}:
        return 0.2
    if {question_family, scenario_family} <= {"SUM_MEASURE", "COUNT_ENTITY"}:
        return 0.15
    return 0.0


def period_compatible(question_period: PeriodKind | None, scenario_period: str | None) -> bool:
    """Hard gate: explicit period in question must not map to a conflicting scenario period."""
    if question_period is None:
        return True
    if not scenario_period:
        return False
    if scenario_period == question_period.value:
        return True
    # Allow near aliases only as soft candidates elsewhere — hard gate rejects them
    return False


def family_compatible(question_family: str | None, scenario_family: str) -> bool:
    if question_family is None:
        return True
    return scenario_family == question_family


def best_entity_among(
    question: str,
    candidates: Iterable[tuple[str, str | None]],
) -> tuple[str, float] | None:
    """Pick best (entity, score) among candidate (entity, physical_table) pairs."""
    best: tuple[str, float] | None = None
    for ent, table in candidates:
        sc = entity_score(question, ent, table)
        if best is None or sc > best[1]:
            best = (ent, sc)
    return best
