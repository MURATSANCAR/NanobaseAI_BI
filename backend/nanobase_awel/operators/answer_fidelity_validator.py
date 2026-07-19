"""Reject invented numeric values in explanations."""

from __future__ import annotations

import re
from typing import Any


def _normalize_number_token(s: str) -> str:
    s = s.strip().replace(" ", "")
    # TR: 1.250.000,50 → 1250000.50
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(".") >= 2:
        # TR thousands: 1.350.000
        s = s.replace(".", "")
    elif "," in s:
        # either 1,350,000 or decimal 12,5
        if s.count(",") >= 2 or re.fullmatch(r"\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    return s


_NUMBER_RE = re.compile(
    r"(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?)|"  # 1.350.000 or 1.350.000,50
    r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?)|"  # 1,350,000.50
    r"(?:\d+[.,]\d+)|"  # 1250000.5 / 12,5
    r"\d+"
)


def extract_numbers(text: str) -> list[float]:
    found: list[float] = []
    for m in _NUMBER_RE.finditer(text or ""):
        raw = _normalize_number_token(m.group(0))
        try:
            found.append(float(raw))
        except Exception:
            continue
    return found


def allowed_numbers_from_summary(summary: dict[str, Any], rows: list[dict[str, Any]]) -> set[float]:
    allowed: set[float] = {float(summary.get("rowCount") or 0)}
    for stats in (summary.get("numericStatistics") or {}).values():
        for k in ("min", "max", "sum", "count"):
            if k in stats:
                try:
                    allowed.add(float(stats[k]))
                except Exception:
                    pass
    for row in rows[:200]:
        for v in row.values():
            if isinstance(v, bool) or v is None:
                continue
            try:
                allowed.add(float(v))
            except Exception:
                continue
    return allowed


def numbers_compatible(value: float, allowed: set[float], *, rel_tol: float = 1e-6) -> bool:
    for a in allowed:
        if abs(a - value) <= max(rel_tol * max(abs(a), abs(value)), 1e-9):
            return True
        # allow integer formatting of same value
        if abs(a - value) < 0.01 and abs(a) >= 1:
            return True
    return False


def validate_answer_fidelity(
    answer: str,
    *,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Return (ok, problems). Small integers used in prose (e.g. '2 satır') allowed if ≤ rowCount."""
    allowed = allowed_numbers_from_summary(summary, rows)
    problems: list[str] = []
    row_count = int(summary.get("rowCount") or 0)
    for n in extract_numbers(answer):
        if n <= max(row_count, 20) and n == int(n) and n <= 1000:
            # likely counting language — allow if not a huge invented total
            continue
        if not numbers_compatible(n, allowed):
            problems.append(f"invented_number:{n}")
    return (len(problems) == 0, problems)


def deterministic_fallback_answer(
    *,
    summary: dict[str, Any],
    columns: list[str],
    rows: list[dict[str, Any]],
    truncated: bool,
) -> str:
    rc = int(summary.get("rowCount") or 0)
    if rc == 0:
        return "Kayıt bulunamadı."
    stats = summary.get("numericStatistics") or {}
    if len(columns) == 1 and rc == 1 and columns[0] in stats:
        total = stats[columns[0]].get("sum") or stats[columns[0]].get("max")
        msg = f"Sonuç başarıyla hesaplandı. Değer: {total}."
    elif rc == 1 and rows:
        parts = [f"{k}={rows[0].get(k)}" for k in columns[:4]]
        msg = "Sorgu 1 satır döndürdü: " + ", ".join(parts) + "."
    else:
        msg = f"Sorgu {rc} satır döndürdü."
    if truncated:
        msg += " Sonuç satır limiti nedeniyle kesilmiş olabilir."
    return msg
