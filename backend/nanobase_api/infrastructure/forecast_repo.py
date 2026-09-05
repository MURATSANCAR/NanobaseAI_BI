"""bi_meta persistence for forecast runs (provenance) and reconciliation."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from forecasting.contracts.models import ForecastResponse, SeriesBundle


def save_forecast_run(
    engine: Engine,
    *,
    tenant_id: str,
    datasource_id: str,
    bundle: SeriesBundle,
    response: ForecastResponse,
    question: str | None = None,
    session_id: str | None = None,
    benchmark_ref: str | None = None,
) -> str:
    run_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fc_forecast_run (id, tenant_id, datasource_id, metric_code, metric_version,
                    dimension_filters, frequency, horizon, history_points, bundle_hash, engine, engine_version,
                    checkpoint_sha, benchmark_ref, question, session_id, warnings)
                VALUES (:id, :tenant_id, :datasource_id, :metric_code, :metric_version,
                    CAST(:dimension_filters AS JSONB), :frequency, :horizon, :history_points, :bundle_hash,
                    :engine, :engine_version, :checkpoint_sha, :benchmark_ref, :question, :session_id,
                    CAST(:warnings AS JSONB))
                """
            ),
            {
                "id": run_id,
                "tenant_id": tenant_id,
                "datasource_id": datasource_id,
                "metric_code": bundle.metric,
                "metric_version": bundle.metric_version,
                "dimension_filters": json.dumps(bundle.dimension, ensure_ascii=False),
                "frequency": bundle.frequency,
                "horizon": bundle.horizon,
                "history_points": len(bundle.history),
                "bundle_hash": bundle.bundle_hash,
                "engine": response.engine,
                "engine_version": response.engine_version,
                "checkpoint_sha": response.checkpoint_sha,
                "benchmark_ref": benchmark_ref,
                "question": question,
                "session_id": session_id,
                "warnings": json.dumps(response.warnings, ensure_ascii=False),
            },
        )
        for p in response.forecast:
            conn.execute(
                text(
                    "INSERT INTO fc_forecast_point (run_id, ts, p10, p50, p90) VALUES (:run_id, :ts, :p10, :p50, :p90)"
                ),
                {"run_id": run_id, "ts": p.timestamp, "p10": p.p10, "p50": p.p50, "p90": p.p90},
            )
    return run_id


def list_points_due_for_reconcile(engine: Engine, *, as_of: date, limit: int = 500) -> list[dict[str, Any]]:
    """Forecast points whose period has fully closed and still lack an actual."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT r.id AS run_id, r.tenant_id, r.datasource_id, r.metric_code, r.dimension_filters,
                       r.frequency, r.engine, p.ts, p.p10, p.p50, p.p90
                FROM fc_forecast_point p JOIN fc_forecast_run r ON r.id = p.run_id
                WHERE p.actual IS NULL AND p.ts < :as_of
                ORDER BY p.ts ASC LIMIT :limit
                """
            ),
            {"as_of": as_of, "limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]


def record_actual(engine: Engine, *, run_id: str, ts: date, actual: float) -> str:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT p10, p90 FROM fc_forecast_point WHERE run_id = :run_id AND ts = :ts"),
            {"run_id": run_id, "ts": ts},
        ).mappings().first()
        if row is None:
            return "missing"
        violation = "above_p90" if actual > float(row["p90"]) else ("below_p10" if actual < float(row["p10"]) else "within")
        conn.execute(
            text(
                "UPDATE fc_forecast_point SET actual = :actual, violation = :violation, reconciled_at = now() "
                "WHERE run_id = :run_id AND ts = :ts"
            ),
            {"actual": actual, "violation": violation, "run_id": run_id, "ts": ts},
        )
    return violation


def recent_violations(engine: Engine, *, tenant_id: str, datasource_id: str, limit: int = 20) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT r.metric_code, r.dimension_filters, r.engine, p.ts, p.p10, p.p50, p.p90, p.actual, p.violation
                FROM fc_forecast_point p JOIN fc_forecast_run r ON r.id = p.run_id
                WHERE r.tenant_id = :tenant_id AND r.datasource_id = :datasource_id
                  AND p.violation IN ('above_p90', 'below_p10')
                ORDER BY p.reconciled_at DESC LIMIT :limit
                """
            ),
            {"tenant_id": tenant_id, "datasource_id": datasource_id, "limit": limit},
        ).mappings().all()
    return [dict(r) for r in rows]
