"""HANA EXPLAIN PLAN guard (best-effort offline heuristics + live explain)."""

from __future__ import annotations

import re
from typing import Any

from query_gateway.domain.errors import GatewayError

HANA_PLAN_REJECTED = "HANA_PLAN_REJECTED"

_RISKY = re.compile(
    r"\b(CARTESIAN|REMOTE|VIRTUAL\s+TABLE|COLUMN\s+TABLE\s+SCAN|FULL\s+SCAN)\b",
    re.I,
)

SIZE_THRESHOLDS = {
    "SMALL": {"max_estimated_rows": 100_000},
    "MEDIUM": {"max_estimated_rows": 1_000_000},
    "LARGE": {"max_estimated_rows": 10_000_000},
    "VERY_LARGE": {"max_estimated_rows": 50_000_000},
}


def evaluate_plan_text(plan_text: str, *, size_profile: str = "MEDIUM") -> list[str]:
    warnings: list[str] = []
    if _RISKY.search(plan_text or ""):
        raise GatewayError(
            HANA_PLAN_REJECTED,
            "HANA plan contains risky operators.",
            status=400,
        )
    # Heuristic estimated rows if present
    m = re.search(r"ESTIMATED_ROWS[^\d]*(\d+)", plan_text or "", re.I)
    if m:
        est = int(m.group(1))
        limit = SIZE_THRESHOLDS.get(size_profile.upper(), SIZE_THRESHOLDS["MEDIUM"])[
            "max_estimated_rows"
        ]
        if est > limit:
            raise GatewayError(
                HANA_PLAN_REJECTED,
                f"Estimated rows {est} exceeds {size_profile} limit {limit}.",
                status=400,
            )
        warnings.append(f"estimated_rows:{est}")
    return warnings


def explain_sql(conn: Any, sql: str) -> str:
    cur = conn.cursor()
    try:
        cur.execute(f"EXPLAIN PLAN FOR {sql}")
        try:
            cur.execute(
                "SELECT * FROM EXPLAIN_PLAN_TABLE ORDER BY OPERATOR_ID"
            )
            rows = cur.fetchall() or []
            return "\n".join(str(r) for r in rows)
        except Exception:
            # Some HANA versions use different plan tables — return marker
            return "EXPLAIN_OK"
    finally:
        try:
            cur.close()
        except Exception:
            pass
