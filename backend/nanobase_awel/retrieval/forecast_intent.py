"""Deterministic forecast-intent resolver (plan Faz 5.1).

Contract (fable axiom — no guessing):
  * returns None            → not a forecast question; normal chat path
  * returns {"declined": …} → clearly a forecast question we cannot resolve
                              exactly (no metric, no horizon, unsupported shape);
                              the chat layer shows the reason and does NOT fall
                              back to the LLM
  * returns an intent dict  → metric + dimension filter + grain + horizon, all
                              extracted from explicit words in the question

Turkish suffix rule: no trailing \\b on Turkish stems ("satışları", "ayın").
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

from nanobase_awel.retrieval.semantic import (
    _QUANTITY_METRIC_INTENT,
    _REVENUE_INTENT,
    _THRESHOLD_HINT,
    _detect_dimensions,
)

_NUM_WORDS = {
    "bir": 1, "iki": 2, "üç": 3, "uc": 3, "dört": 4, "dort": 4, "beş": 5, "bes": 5, "altı": 6, "alti": 6,
    "yedi": 7, "sekiz": 8, "dokuz": 9, "on": 10, "on bir": 11, "on iki": 12, "one": 1, "two": 2, "three": 3,
    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}
_NUM = r"(\d{1,2}|on iki|on bir|bir|iki|üç|uc|dört|dort|beş|bes|altı|alti|yedi|sekiz|dokuz|on|one|two|three|four|five|six|seven|eight|nine|ten|twelve)"
_GRAIN = r"(ay|hafta|çeyrek|ceyrek|yıl|yil|gün|gun|month|week|quarter|year|day)"
_GRAIN_MAP = {
    "ay": "month", "month": "month", "hafta": "week", "week": "week", "çeyrek": "quarter", "ceyrek": "quarter",
    "quarter": "quarter", "yıl": "year", "yil": "year", "year": "year", "gün": "day", "gun": "day", "day": "day",
}
_GRAIN_FREQ = {"month": "M", "week": "W", "quarter": "Q", "year": "Y"}

# "önümüzdeki 6 ay", "gelecek üç çeyrek", "next 12 months", "6 aylık tahmin", "sonraki 4 hafta"
_HORIZON_EXPLICIT = re.compile(
    rf"(?i)\b(önümüzdeki|onumuzdeki|gelecek|sonraki|next|ilerideki)\s*{_NUM}\s*{_GRAIN}"
)
# "6 aylık (satış) tahmini" — the -lık suffix already marks a duration; the
# forecast word may sit a few tokens later.
_HORIZON_SUFFIX = re.compile(rf"(?i)\b{_NUM}\s*{_GRAIN}(lık|lik|luk|lük)\b")
# "gelecek ay", "önümüzdeki çeyrek" → horizon 1
_HORIZON_ONE = re.compile(rf"(?i)\b(önümüzdeki|onumuzdeki|gelecek|sonraki|next)\s*{_GRAIN}(ın|in|ın|da|de|ki)?\b")

_FORECAST_WORD = re.compile(r"(?i)\btahmin|\bforecast|\bprojeksiyon|\böngör|\bongor|\bbeklenti|\bnasıl\b|\bnasil\b|\bne olur|\bne olacak|\bne kadar olur")
# Broader than the exact-answer resolver: "İstanbul satışları" is a revenue series.
_SALES_WORD = re.compile(r"(?i)\bsatış|\bsatis|\bsales\b|\bgelir")

_DEFAULT_DIMENSION_VALUES: dict[str, list[str]] = {
    "branch_city": ["İstanbul", "Ankara", "Berlin"],
}


def _fold(s: str) -> str:
    s = s.replace("İ", "i").replace("I", "ı")
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def dimension_values() -> dict[str, list[str]]:
    raw = os.environ.get("FORECAST_DIMENSION_VALUES")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): [str(x) for x in v] for k, v in data.items()}
        except json.JSONDecodeError:
            pass
    return _DEFAULT_DIMENSION_VALUES


def _to_int(token: str) -> int:
    t = token.strip().lower()
    if t.isdigit():
        return int(t)
    return _NUM_WORDS.get(t, 0)


def _horizon(q: str) -> tuple[int, str] | None:
    m = _HORIZON_EXPLICIT.search(q)
    if m:
        return _to_int(m.group(2)), _GRAIN_MAP[_fold(m.group(3)) if _fold(m.group(3)) in _GRAIN_MAP else m.group(3).lower()]
    m = _HORIZON_SUFFIX.search(q)
    if m:
        return _to_int(m.group(1)), _GRAIN_MAP[_fold(m.group(2)) if _fold(m.group(2)) in _GRAIN_MAP else m.group(2).lower()]
    m = _HORIZON_ONE.search(q)
    if m:
        return 1, _GRAIN_MAP[_fold(m.group(2)) if _fold(m.group(2)) in _GRAIN_MAP else m.group(2).lower()]
    return None


def _dimension_filter(q: str) -> dict[str, str]:
    fq = _fold(q)
    out: dict[str, str] = {}
    for col, values in dimension_values().items():
        for v in values:
            if re.search(rf"(?<![a-z0-9]){re.escape(_fold(v))}", fq):
                out[col] = v
                break
    return out


def resolve_forecast_intent(question: str) -> dict[str, Any] | None:
    q = question or ""
    hz = _horizon(q)
    is_forecast = bool(hz) and bool(_FORECAST_WORD.search(q))
    if not is_forecast:
        return None

    horizon, grain = hz  # type: ignore[misc]
    if grain == "day":
        return {"declined": "UNSUPPORTED_GRAIN", "reason": "Günlük tahmin desteklenmiyor; ay, hafta veya çeyrek kullanın."}
    if horizon <= 0:
        return {"declined": "HORIZON_UNRESOLVED", "reason": "Tahmin ufku anlaşılamadı (örn. 'önümüzdeki 6 ay')."}
    if _THRESHOLD_HINT.search(q):
        return {"declined": "UNSUPPORTED_SHAPE", "reason": "Eşik/koşul içeren tahmin soruları desteklenmiyor."}

    if _QUANTITY_METRIC_INTENT.search(q):
        metric = "total_quantity_sold"
    elif _REVENUE_INTENT.search(q) or _SALES_WORD.search(q):
        metric = "total_revenue"
    else:
        return {"declined": "METRIC_UNRESOLVED", "reason": "Hangi metriğin tahmin edileceği anlaşılamadı (örn. satış/ciro)."}

    dims = _detect_dimensions(q)
    dim_filter = _dimension_filter(q)
    # "city" dimension word is fine only when it resolved to a concrete value.
    unresolved = [d for d in dims if d != "city"] or (["city"] if "city" in dims and not dim_filter else [])
    if unresolved:
        return {"declined": "UNSUPPORTED_SHAPE", "reason": "Kırılımlı (segment/ürün/müşteri) tahmin V1'de desteklenmiyor; tek seri sorun."}

    return {
        "metricCode": metric,
        "dimensionFilters": dim_filter,
        "grain": grain,
        "frequency": _GRAIN_FREQ[grain],
        "horizon": horizon,
        "historyMonths": int(os.environ.get("FORECAST_HISTORY_MONTHS", "36")),
    }
