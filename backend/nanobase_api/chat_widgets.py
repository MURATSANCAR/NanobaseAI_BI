"""Infer BiWidget specs from chat query results for chart preview + canvas pin."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Any


_TIME_HINT = re.compile(
    r"(date|time|tarih|gun|gün|ay|yil|yıl|week|hafta|month|year|period|donem|dönem)",
    re.I,
)


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        s = value.strip().replace(",", "")
        if not s:
            return False
        try:
            float(s)
            return True
        except ValueError:
            return False
    return False


def _looks_like_time(col: str, rows: list[dict[str, Any]]) -> bool:
    if _TIME_HINT.search(col or ""):
        return True
    hits = 0
    checked = 0
    for row in rows[:12]:
        val = row.get(col)
        if val is None or val == "":
            continue
        checked += 1
        if isinstance(val, (date, datetime)):
            hits += 1
            continue
        s = str(val).strip()
        if re.match(r"^\d{4}([-/.]\d{1,2}){1,2}", s) or re.match(r"^\d{4}-\d{2}", s):
            hits += 1
    return checked > 0 and hits / checked >= 0.5


# Sonuç seti hem kod hem ad kolonu döndürdüğünde ("cari_kodu" + "unvan") eksen kodla etiketleniyordu.
_CODE_SEG = {"kod", "kodu", "code", "id", "no", "ref", "refno", "key"}
_LABEL_SEG = {
    "unvan", "ad", "adi", "adı", "isim", "ismi", "name", "title",
    "baslik", "başlık", "aciklama", "açıklama", "tanim", "tanım",
    "label", "desc", "description",
}


def _segments(col: str) -> set[str]:
    return {s for s in re.split(r"[\W_]+", (col or "").lower()) if s}


def _label_col(cats: list[str]) -> str:
    """Eksen etiketi için en okunur kategori kolonu.

    Tek kategori varsa o. Birden fazlaysa sırayla: ad/unvan gibi açıklayıcı bir kolon,
    yoksa kod/id olmayan ilk kolon, o da yoksa ilk kolon.
    """
    if len(cats) < 2:
        return cats[0]
    for col in cats:
        if _LABEL_SEG & _segments(col):
            return col
    for col in cats:
        if not _CODE_SEG & _segments(col):
            return col
    return cats[0]


def _numeric_cols(cols: list[str], rows: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for col in cols:
        sample = [r.get(col) for r in rows[:30] if isinstance(r, dict)]
        nonempty = [v for v in sample if v is not None and v != ""]
        if not nonempty:
            continue
        if sum(1 for v in nonempty if _is_number(v)) / len(nonempty) >= 0.7:
            out.append(col)
    return out


def _widget_id(sql: str, title: str, wtype: str) -> str:
    digest = hashlib.sha1(f"{sql}|{title}|{wtype}".encode("utf-8")).hexdigest()[:12]
    return f"chat_{digest}"


def widgets_from_query_result(
    *,
    columns: list[str] | None,
    rows: list[dict[str, Any]] | None,
    sql: str | None = None,
    title: str | None = None,
) -> list[dict[str, Any]]:
    """Build one chart/KPI/table widget from executed chat result rows."""
    cols: list[str] = []
    for c in columns or []:
        if isinstance(c, dict):
            name = str(c.get("name") or "").strip()
        else:
            name = str(c or "").strip()
        if name and name not in cols:
            cols.append(name)
    clean_rows = [r for r in (rows or []) if isinstance(r, dict)]
    if not cols and clean_rows:
        cols = [str(k) for k in clean_rows[0].keys()]
    if not cols or not clean_rows:
        return []

    safe_sql = (sql or "").strip() or None
    label = (title or "").replace("\n", " ").strip()[:80] or "Chat sonucu"
    data = {"columns": cols, "rows": clean_rows, "row_count": len(clean_rows)}
    nums = _numeric_cols(cols, clean_rows)
    cats = [c for c in cols if c not in nums]

    def base(wtype: str, **extra: Any) -> dict[str, Any]:
        w: dict[str, Any] = {
            "id": _widget_id(safe_sql or label, label, wtype),
            "type": wtype,
            "title": label,
            "data": data,
        }
        if safe_sql:
            w["sql"] = safe_sql
        w.update(extra)
        return w

    # Single scalar → KPI card
    if len(clean_rows) == 1 and len(nums) == 1 and len(cols) <= 2:
        vk = nums[0]
        return [base("kpi", value_key=vk, format="number")]

    # One row, several metrics → multi_card (label/value pairs)
    if len(clean_rows) == 1 and 2 <= len(nums) <= 4:
        row0 = clean_rows[0]
        mc_rows = [{"label": c, "value": row0.get(c)} for c in nums]
        return [
            {
                "id": _widget_id(safe_sql or label, label, "multi_card"),
                "type": "multi_card",
                "title": label,
                "label_key": "label",
                "value_key": "value",
                "sql": safe_sql,
                "data": {
                    "columns": ["label", "value"],
                    "rows": mc_rows,
                    "row_count": len(mc_rows),
                },
            }
        ]

    # Category + measure → bar / line / pie
    if cats and nums and len(clean_rows) >= 2:
        xk, yk = _label_col(cats), nums[0]
        if _looks_like_time(xk, clean_rows):
            wtype = "line"
        elif len(clean_rows) <= 8 and len(cats) == 1:
            wtype = "pie"
        else:
            wtype = "bar"
        return [
            base(
                wtype,
                x_key=xk,
                y_key=yk,
                label_key=xk,
                value_key=yk,
            )
        ]

    # Two numeric columns → scatter-ish bar fallback as table if no category
    if len(nums) >= 2 and len(clean_rows) >= 2 and not cats:
        return [base("table")]

    return [base("table")]
