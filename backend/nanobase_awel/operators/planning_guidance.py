"""Dynamic planning guidance derived from question + retrieved tables.

No hardcoded datasource catalogs — only shape heuristics when evidence is present.
"""

from __future__ import annotations

import re
from typing import Iterable


_LINE_SUFFIXES = (
    "_kalemleri",
    "_kalem",
    "_lines",
    "_items",
    "_hareketleri",
    "_hareket",
    "_detay",
    "_details",
)
_HEADER_HINTS = (
    "fatura",
    "faturalar",
    "invoice",
    "siparis",
    "order",
    "po",
    "yevmiye_fis",
    "journal",
)
_TOTAL_INTENT = re.compile(
    r"(?i)\b(ciro|toplam|genel[_\s]?toplam|yıllık|yillik|yoy|karşılaştır|karsilastir|"
    r"revenue|sum|aggregate|gider|tahsilat|bütçe|butce|kullanım|kullanim)\b"
)
_LINE_INTENT = re.compile(
    r"(?i)\b(ürün|urun|sku|kategori|marka|marj|margin|birim[_\s]?fiyat|kalem|"
    r"fiyat\s*list|iskonto|stok|depo|line\s*item|product)\b"
)
_HAS_DATE = re.compile(
    r"(?i)\b(20\d{2}|son\s+\d+|last\s+\d+|ay|yıl|yil|quarter|q[1-4]|between|"
    r"tarih|date|month|year|hafta|week)\b"
)


def _short_name(table: str) -> str:
    t = (table or "").strip().strip('"').lower()
    if "." in t:
        t = t.rsplit(".", 1)[-1]
    return t


def _is_line_table(name: str) -> bool:
    return any(name.endswith(sfx) or sfx in name for sfx in _LINE_SUFFIXES)


def _looks_header(name: str) -> bool:
    if _is_line_table(name):
        return False
    return any(h in name for h in _HEADER_HINTS)


def build_planning_guidance(
    question: str,
    tables: Iterable[str] | None,
) -> str:
    """Return optional <query_shape_guidance> body (without tags), or empty."""
    names = [_short_name(t) for t in (tables or []) if t]
    if not names:
        return ""

    line_tables = sorted({n for n in names if _is_line_table(n)})
    header_tables = sorted({n for n in names if _looks_header(n)})
    q = question or ""
    wants_totals = bool(_TOTAL_INTENT.search(q))
    wants_lines = bool(_LINE_INTENT.search(q))
    has_date = bool(_HAS_DATE.search(q))

    bullets: list[str] = []

    if wants_totals and not wants_lines and header_tables and line_tables:
        bullets.append(
            "Question is aggregate/total-oriented and header tables are available: "
            "prefer header-level amount columns (e.g. genel_toplam / total) with GROUP BY. "
            f"Do NOT join line tables ({', '.join(line_tables[:6])}) unless line attributes are required."
        )
    elif wants_lines and line_tables:
        bullets.append(
            "Line/product attributes are required — line tables may be used, but always constrain "
            "them with a date/time predicate via join to the header date column."
        )

    if line_tables and not has_date:
        bullets.append(
            "Large/line fact tables are in scope but the question has no explicit time window. "
            "Either (a) add a tight date filter from context (e.g. current year / last 12 months) "
            "in SQL assumptions, or (b) set status=AMBIGUOUS and ask the user for a date range "
            "before scanning those tables. Never full-scan line tables without a date predicate."
        )
    elif line_tables:
        bullets.append(
            "When querying line/fact tables, require an explicit date predicate "
            "(WHERE/JOIN on header date). Prefer LIMIT for ranked lists."
        )

    bullets.append("Never use SELECT *. Project only needed columns.")
    bullets.append(
        "If the request cannot be answered safely without a narrower period, "
        "prefer AMBIGUOUS + clarificationQuestion over an unbounded scan."
    )

    if not bullets:
        return ""
    return "Derived from retrieved tables + question intent (not a static catalog):\n- " + "\n- ".join(
        bullets
    )


def user_guidance_for_gateway_error(code: str, message: str | None = None) -> str | None:
    """Turkish chat guidance when gateway rejects/fails — None if no special UX."""
    c = (code or "").upper()
    msg = (message or "").strip()
    if c in ("QUERY_COST_EXCEEDED",):
        return (
            "Bu sorgu tahmini maliyeti / satır sayısı eşiğini aşıyor (büyük tablo veya filtresiz tarama). "
            "Lütfen tarihi daraltın (ör. 2026, son 3 ay) veya ürün/kategori yerine özet/ciro sorusu sorun; "
            "yeniden deneyin."
        )
    if c in ("QUERY_TIMEOUT",):
        return (
            "Sorgu zaman aşımına uğradı. Tarih aralığını küçültün veya kalem/detay yerine "
            "üst belge toplamlarını (genel_toplam) sorun."
        )
    if c in ("DATABASE_CONNECTION_LOST", "DATABASE_UNAVAILABLE"):
        detail = f" ({msg})" if msg else ""
        return (
            f"Veritabanı bağlantısı / erişilebilirlik sorunu{detail}. "
            "Kısa süre sonra tekrar deneyin; devam ederse tarih filtresi ekleyerek sadeleştirin."
        )
    if c == "WILDCARD_NOT_ALLOWED":
        return None  # repair path handles
    return None
