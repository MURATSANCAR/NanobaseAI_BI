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
    r"tarih|date|month|year|hafta|week|mali\s+yıl|mali\s+yil)\b"
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

    bullets.append(
        "Bias to PLANNED SQL. Use status=AMBIGUOUS only when a critical join key or metric "
        "cannot be inferred at all — not for polite confirmation of years/periods already stated."
    )

    if has_date:
        bullets.append(
            "A time window is already present in the user question (year, 'son N …', mali yıl, etc.). "
            "Encode it directly in SQL (EXTRACT/YEAR, date literals, INTERVAL). "
            "Do NOT ask the user to restate start/end dates."
        )
    elif line_tables:
        # Do NOT default to "current calendar year" (or any other silent
        # window) when the question states none — that changes the answer's
        # meaning ("toplam ciro" -> "this year's ciro") without telling the
        # user. The Gateway's own cost guard (QUERY_COST_EXCEEDED, repairable)
        # already rejects genuinely too-expensive unbounded scans and the
        # repair/clarification path asks for a date range only when the query
        # actually needs one — that is the real safety net, not a guess here.
        bullets.append(
            "Large/line fact tables are in scope and no time window was stated. "
            "Answer the question as asked, over ALL time, with no date filter — "
            "do not invent a default period. If the resulting query is too "
            "expensive, the gateway will reject it and you will get a chance "
            "to add a date range then. PLANNED SQL; use AMBIGUOUS only when a "
            "date range is unavoidable to answer at all (e.g. 'yearly trend' "
            "with no years named)."
        )

    if wants_totals and not wants_lines and header_tables and line_tables:
        bullets.append(
            "Aggregate/total question with header tables available: prefer header amount columns "
            "(names the user mentioned such as genel_toplam, or obvious total/amount columns) "
            f"with GROUP BY. Do NOT join line tables ({', '.join(line_tables[:6])}) unless line "
            "attributes are required."
        )
    elif wants_lines and line_tables:
        bullets.append(
            "Line/product attributes are required — line tables may be used with a date predicate "
            "via the header date column."
        )

    if line_tables:
        bullets.append(
            "When querying line/fact tables, always include a date/time predicate "
            "(WHERE/JOIN on header date). Prefer LIMIT for ranked lists."
        )

    bullets.append(
        "If the user names a column on an authorized table (e.g. genel_toplam), use it. "
        "Missing column metadata in the retrieval snippet is NOT a reason for AMBIGUOUS — "
        "state an assumption and proceed."
    )
    bullets.append(
        "Never use SELECT * and never wrap a CTE as SELECT * FROM (WITH ...). "
        "Project only needed columns."
    )

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
