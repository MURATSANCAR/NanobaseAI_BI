"""Generic NL intent slots for scenario matching — period / family / entity.

Not table-specific hardcodes: entity fingerprints come from scenario entity codes
and physical table names; period/family use ordered Turkish phrase patterns on
normalize_question() (ASCII-folded) text.
"""

from __future__ import annotations

import re
from typing import Iterable

from nanobase_api.scenario_engine.domain.period import PeriodKind
from nanobase_api.scenario_engine.domain.scenario import normalize_question

# Patterns run on normalize_question() output. Longest / most specific first.
_PERIOD_PATTERNS: list[tuple[re.Pattern[str], PeriodKind]] = [
    (re.compile(r"\byil\s+basindan(\s+bugune)?(\s+kadar)?\b"), PeriodKind.YEAR_TO_DATE),
    (re.compile(r"\bay\s+basindan(\s+bugune)?(\s+kadar)?\b"), PeriodKind.MONTH_TO_DATE),
    (re.compile(r"\bgecen\s+yil(ki|a|in)?\b"), PeriodKind.PREVIOUS_YEAR),
    (re.compile(r"\bbu\s+yil(ki|a|in|da)?\b"), PeriodKind.CURRENT_YEAR),
    (re.compile(r"\bgecen\s+ceyrek\b"), PeriodKind.PREVIOUS_QUARTER),
    (re.compile(r"\bbu\s+ceyrek\b"), PeriodKind.CURRENT_QUARTER),
    (re.compile(r"\bgecen\s+ay(ki|a|in)?\b"), PeriodKind.PREVIOUS_MONTH),
    (re.compile(r"\bbu\s+ay(ki|a|in)?\b"), PeriodKind.CURRENT_MONTH),
    (re.compile(r"\bgecen\s+hafta(ki|ya)?\b"), PeriodKind.PREVIOUS_WEEK),
    (re.compile(r"\bbu\s+hafta(ki|ya)?\b"), PeriodKind.CURRENT_WEEK),
    (re.compile(r"\bdun(e|ki|ku|un)?\b"), PeriodKind.YESTERDAY),
    # Bare bugun last — after YTD/MTD which also contain "bugune"
    (re.compile(r"\bbugun(e|ki|ku|un)?\b"), PeriodKind.TODAY),
]

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
        "olani",
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
        "mu",
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
    "si",
    "su",
    "si",
)

# Shared business nouns — alone they must not prefer a qualified table (alis_faturalari)
_GENERIC_NOUNS = frozenset(
    {
        "fatura",
        "faturalar",
        "faturalari",
        "odeme",
        "odemeler",
        "siparis",
        "siparisler",
        "kayit",
        "kayitlar",
        "kayitlari",
        "musteri",
        "musteriler",
        "urun",
        "urunler",
        "police",
        "policeler",
        "hasar",
        "talepler",
        "talepleri",
    }
)


def detect_period(question: str) -> PeriodKind | None:
    """Return the most specific period mentioned in the question."""
    q = normalize_question(question or "")
    if not q:
        return None
    for pat, kind in _PERIOD_PATTERNS:
        if pat.search(q):
            return kind
    return None


def detect_family(question: str) -> str | None:
    """Infer COUNT / SUM / LIST / TOP_N / STATUS / AGING from wording."""
    q = normalize_question(question or "")
    if not q:
        return None
    if re.search(r"\bvadesi\b|\bgecmis\b.*\bvade\b", q):
        return "AGING"
    if "iptal" in q or "odenmemis" in q:
        return "STATUS_FILTER"
    if re.search(r"\ben (yuksek|buyuk|dusuk|kucuk)\b|\btop[-\s]?\d+\b|\bilk\s+\d+\b", q):
        return "TOP_N"
    if re.search(
        r"\bkac\b|\bsayisi\b|\bsayi\b|\badedi\b|\badet\b|"
        r"\bne kadar\b.+\b(var|mevcut)\b|\b(var|mevcut)\b.*\bne kadar\b|"
        r"\bne kadar\b.+\bfatura|\bfatura.+\bne kadar\b",
        q,
    ):
        if re.search(r"\bne kadar\b.+\b(tutar\w*|toplam\w*|ciro|gelir|satis)\b", q) or re.search(
            r"\b(tutar\w*|toplam\w*|ciro)\b.+\bne kadar\b", q
        ):
            return "SUM_MEASURE"
        return "COUNT_ENTITY"
    if re.search(r"\btoplam\w*\b|\btutar\w*\b|\bciro\b|\bsum\b", q):
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
    inter = set(fp & qtok)
    if not inter:
        for f in fp:
            for t in qtok:
                if len(f) >= 4 and (f in t or t in f):
                    inter.add(f)
                    break
    if not inter:
        return 0.0
    coverage = len(inter) / max(1, len(fp))
    precision = len(inter) / max(1, len(qtok))
    score = min(1.0, 0.65 * coverage + 0.35 * min(1.0, precision * 3))

    # Qualified tables (alis_faturalari, musteri_adresleri): require head + qualifier
    # signals so "kaç müşteri var" does not bind to musteri_adresleri.
    short = (physical_table or entity or "").split(".")[-1]
    parts = [p for p in short.split("_") if len(p) >= 3]
    if len(parts) >= 2:
        head = _stem_token(parts[-1])
        head_hit = head in qtok or any(
            len(head) >= 4 and (head in t or t in head) for t in qtok
        )
        if not head_hit and head not in _GENERIC_NOUNS:
            score *= 0.3
        qualifiers = {p for p in parts[:-1] if p not in _GENERIC_NOUNS}
        if qualifiers and not (qualifiers & qtok) and not any(
            any(q in t or t in q for t in qtok if len(t) >= 3) for q in qualifiers
        ):
            score *= 0.35

    return round(min(1.0, score), 4)


def period_score(question_period: PeriodKind | None, scenario_period: str | None) -> float:
    if question_period is None:
        return 0.55 if not scenario_period else 0.45
    if not scenario_period:
        return 0.25
    if scenario_period == question_period.value:
        return 1.0
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
    if {question_family, scenario_family} <= {"COUNT_ENTITY", "LIST_ENTITY"}:
        return 0.2
    if {question_family, scenario_family} <= {"SUM_MEASURE", "COUNT_ENTITY"}:
        return 0.15
    return 0.0


def period_compatible(question_period: PeriodKind | None, scenario_period: str | None) -> bool:
    """Bare questions (no period cue) only match global/all scenarios."""
    if question_period is None:
        return not scenario_period
    if not scenario_period:
        return False
    return scenario_period == question_period.value


def family_compatible(question_family: str | None, scenario_family: str) -> bool:
    if question_family is None:
        return True
    return scenario_family == question_family


def best_entity_among(
    question: str,
    candidates: Iterable[tuple[str, str | None]],
) -> tuple[str, float] | None:
    best: tuple[str, float] | None = None
    for ent, table in candidates:
        sc = entity_score(question, ent, table)
        if best is None or sc > best[1]:
            best = (ent, sc)
    return best
