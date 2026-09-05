"""Chat forecast branch (plan Faz 5.2/5.3/6.2).

question → resolve_forecast_intent (deterministic)
         → load_metric_series (MetricCompiler time_grain → Query Gateway)
         → build_series_bundle (fail-visible normalization)
         → Forecast API (engine adapters)
         → persist fc_forecast_run → deterministic Turkish answer + chart block

The LLM never writes SQL, never sees the series and never invents a number.
Every failure is a coded `forecast_declined` — this branch does not fall
back to the LLM plan path.
"""

from __future__ import annotations

import asyncio
import os
from datetime import date
from typing import Any, AsyncIterator, Callable

from forecasting.contracts import SeriesBundleError, build_series_bundle
from forecasting.contracts.builder import next_period, period_start
from forecasting.contracts.models import ForecastResponse, SeriesBundle
from nanobase_api.application.series import SeriesError, load_metric_series
from nanobase_api.infrastructure.forecast_client import ForecastClient, ForecastError

_METRIC_LABEL = {"total_revenue": "toplam ciro", "total_quantity_sold": "satılan adet"}
_GRAIN_LABEL = {"M": "ay", "W": "hafta", "Q": "çeyrek", "Y": "yıl", "D": "gün"}

_DECLINE_TR = {
    "INSUFFICIENT_HISTORY": "Bu seri için yeterli geçmiş veri yok; güvenilir tahmin için en az 12 kapalı dönem gerekir.",
    "HORIZON_TOO_LONG": "İstenen tahmin ufku bu serinin geçmişine göre çok uzun.",
    "DUPLICATE_TIMESTAMPS": "Seri verisinde aynı döneme ait birden fazla kayıt var; veri kaynağı kontrol edilmeli.",
    "GAPS_EXCEED_POLICY": "Seri verisinde boşluklar var ve doldurma politikası bunu reddediyor.",
    "NEGATIVE_VALUE_FOR_METRIC": "Metrik negatif değer içeriyor; tahmin üretilmedi.",
    "FORECAST_UNAVAILABLE": "Tahmin servisine şu anda ulaşılamıyor.",
    "METRIC_UNAVAILABLE": "Tahmin için tanımlı (yayınlanmış) bir metrik bulunamadı.",
}


def _fmt(v: float, unit: str | None) -> str:
    s = f"{v:,.0f}".replace(",", ".")
    return f"{s} {unit}" if unit else s


def _pct(a: float, b: float) -> str | None:
    if b == 0:
        return None
    d = (a - b) / abs(b) * 100
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:.1f}%"


def _period_label(d: date, freq: str) -> str:
    if freq == "M":
        return d.strftime("%Y-%m")
    if freq == "Q":
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    if freq == "Y":
        return str(d.year)
    return d.isoformat()


def build_forecast_answer(
    *, bundle: SeriesBundle, resp: ForecastResponse, unit: str | None, question: str
) -> dict[str, Any]:
    """Deterministic narrative + blocks. No model-generated numbers."""
    freq = bundle.frequency
    metric_label = _METRIC_LABEL.get(bundle.metric, bundle.metric)
    dim = ", ".join(f"{v}" for v in bundle.dimension.values())
    scope = f"{dim} için {metric_label}" if dim else metric_label
    h = bundle.horizon
    hist_vals = [p.value for p in bundle.history]
    last_actual_sum = sum(hist_vals[-h:])
    p50_sum = sum(p.p50 for p in resp.forecast)
    p10_sum = sum(p.p10 for p in resp.forecast)
    p90_sum = sum(p.p90 for p in resp.forecast)
    change = _pct(p50_sum, last_actual_sum)
    first, last = resp.forecast[0], resp.forecast[-1]

    lines = [
        f"{scope[0].upper() + scope[1:]} — önümüzdeki {h} {_GRAIN_LABEL.get(freq, 'dönem')} tahmini "
        f"({len(bundle.history)} dönem geçmiş, aylık kapanmış veriler):",
        f"• Toplam beklenti: {_fmt(p50_sum, unit)} (aralık {_fmt(p10_sum, unit)} – {_fmt(p90_sum, unit)})"
        + (f", son {h} döneme göre {change}" if change else ""),
        f"• İlk dönem {_period_label(first.timestamp, freq)}: {_fmt(first.p50, unit)} "
        f"(aralık {_fmt(first.p10, unit)} – {_fmt(first.p90, unit)})",
        f"• Son dönem {_period_label(last.timestamp, freq)}: {_fmt(last.p50, unit)} "
        f"(aralık {_fmt(last.p10, unit)} – {_fmt(last.p90, unit)})",
    ]
    filled = len(bundle.filled_periods)
    if filled:
        lines.append(f"• Not: {filled} dönem verisi eksikti, {bundle.missing_policy} politikasıyla dolduruldu.")
    if any(w.startswith("short_history") for w in bundle.warnings):
        lines.append("• Not: Geçmiş 24 dönemden kısa; aralıklar daha geniş yorumlanmalı.")
    if any(w.startswith("seasonal_fallback_naive") for w in resp.warnings):
        lines.append("• Not: Mevsimsellik için yeterli geçmiş yok; son değer temelli tahmin kullanıldı.")
    reply = "\n".join(lines)

    table_cols = ["Dönem", "Alt (p10)", "Beklenen (p50)", "Üst (p90)"]
    table_rows = [
        [_period_label(p.timestamp, freq), round(p.p10, 2), round(p.p50, 2), round(p.p90, 2)] for p in resp.forecast
    ]
    forecast_block = {
        "type": "forecast",
        "title": f"{scope[0].upper() + scope[1:]} — {h} {_GRAIN_LABEL.get(freq, 'dönem')} tahmin",
        "forecast": {
            "metric": bundle.metric,
            "unit": unit,
            "frequency": freq,
            "engine": "nanobaseai-bi-forecast",
            "history": [{"period": p.timestamp.isoformat(), "value": p.value} for p in bundle.history[-24:]],
            "forecast": [
                {"period": p.timestamp.isoformat(), "p10": p.p10, "p50": p.p50, "p90": p.p90} for p in resp.forecast
            ],
        },
    }
    blocks = [
        {"type": "text", "content": reply},
        forecast_block,
        {"type": "table", "title": "Tahmin değerleri", "columns": table_cols, "rows": table_rows},
    ]
    follow_ups = [
        f"Son 12 ayda {scope} aylık nasıl gelişti?",
        f"{dim + ' ' if dim else ''}aylık sipariş sayısı son 12 ay",
        f"{dim + ' ' if dim else ''}satılan adet son 12 ay aylık",
    ]
    return {"reply": reply, "blocks": blocks, "followUps": follow_ups, "table": {"columns": table_cols, "rows": table_rows}}


async def stream_forecast(
    *,
    intent: dict[str, Any],
    message: str,
    session_id: str,
    datasource_id: str,
    tenant_id: str,
    execution_id: str,
    execution_mode: str,
    sse: Callable[[str, dict[str, Any]], str],
    with_provenance: Callable[..., dict[str, Any]],
    meta_engine: Any = None,
) -> AsyncIterator[bytes]:
    def _declined(code: str, reason: str, **extra: Any) -> list[bytes]:
        text = _DECLINE_TR.get(code, reason) or reason
        if text != reason and reason:
            text = f"{text} ({reason})"
        out = [
            sse("status", {"phase": "forecast_declined", "type": "FORECAST_DECLINED", "code": code, "reason": text, **extra}).encode(),
            sse("completed", {"type": "COMPLETED", "payload": {"forecast": False, "code": code}}).encode(),
            sse(
                "done",
                with_provenance(
                    {
                        "session_id": session_id,
                        "reply": text,
                        "intent": "forecast_declined",
                        "sql": None,
                        "sql_error": f"{code}: {reason}",
                        "needs_clarification": False,
                        "query_result": {"columns": [], "rows": []},
                        "widgets": [],
                        "answer_blocks": [{"type": "text", "content": text}],
                        "engine": "nanobaseai-bi-forecast",
                        "workflows": {"forecast": {"status": "DECLINED", "code": code, "intent": intent}},
                        "execution_id": execution_id,
                        "forecast": {"status": "declined", "code": code},
                    },
                    None,
                    executed=False,
                    execution_mode=execution_mode,
                ),
            ).encode(),
        ]
        return out

    if "declined" in intent:
        for b in _declined(str(intent["declined"]), str(intent.get("reason") or "")):
            yield b
        return

    metric_code = str(intent["metricCode"])
    dims = dict(intent.get("dimensionFilters") or {})
    grain = str(intent.get("grain") or "month")
    horizon = int(intent.get("horizon") or 6)
    history_periods = int(intent.get("historyMonths") or 36)

    yield sse(
        "status",
        {"phase": "forecast_intent", "type": "STATUS", "metric": metric_code, "dimensionFilters": dims, "grain": grain, "horizon": horizon},
    ).encode()

    try:
        series = await load_metric_series(
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            metric_code=metric_code,
            grain=grain,
            history_periods=history_periods,
            dimension_filters=dims,
            execution_id=execution_id,
        )
    except SeriesError as e:
        for b in _declined(e.code, e.message):
            yield b
        return

    yield sse(
        "status",
        {"phase": "forecast_series_hit", "type": "STATUS", "sql": series["sql"], "sql_source": series["sqlSource"], "rows": series["rowCount"]},
    ).encode()
    yield sse("sql_generated", {"type": "SQL_GENERATED", "payload": {"sql": series["sql"], "sql_source": series["sqlSource"]}}).encode()

    try:
        bundle = build_series_bundle(
            [(r["period"], r["value"]) for r in series["rows"] if r.get("period")],
            metric=metric_code,
            frequency=series["frequency"],
            horizon=horizon,
            dimension=dims,
            metric_version=(series.get("logicalPlan") or {}).get("metricVersion"),
        )
    except SeriesBundleError as e:
        for b in _declined(e.code, e.message, **{k: v for k, v in e.details.items() if isinstance(v, (int, str))}):
            yield b
        return

    yield sse(
        "status",
        {
            "phase": "forecast_bundle_ready",
            "type": "STATUS",
            "points": len(bundle.history),
            "filled": len(bundle.filled_periods),
            "bundle_hash": bundle.bundle_hash,
            "warnings": bundle.warnings,
        },
    ).encode()

    try:
        resp = await ForecastClient().forecast(bundle)
    except ForecastError as e:
        for b in _declined(e.code, e.message):
            yield b
        return

    run_id: str | None = None
    if meta_engine is not None:
        try:
            from nanobase_api.infrastructure.forecast_repo import save_forecast_run

            run_id = await asyncio.to_thread(
                save_forecast_run,
                meta_engine,
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                bundle=bundle,
                response=resp,
                question=message,
                session_id=session_id,
            )
        except Exception as e:  # noqa: BLE001 — provenance persistence must not break the answer
            yield sse("status", {"phase": "forecast_persist_skip", "detail": str(e)[:200]}).encode()

    unit = os.environ.get("FORECAST_UNIT_LABEL", "TL") if metric_code == "total_revenue" else None
    answer = build_forecast_answer(bundle=bundle, resp=resp, unit=unit, question=message)

    yield sse(
        "status",
        {"phase": "forecast_done", "type": "STATUS", "engine": resp.engine, "engine_version": resp.engine_version, "horizon": horizon, "run_id": run_id, "latency_ms": resp.latency_ms},
    ).encode()
    yield sse("completed", {"type": "COMPLETED", "payload": {"forecast": True, "run_id": run_id}}).encode()

    result = with_provenance(
        {
            "session_id": session_id,
            "reply": answer["reply"],
            "intent": "forecast",
            "sql": series["sql"],
            "sql_source": series["sqlSource"],
            "sql_error": None,
            "needs_clarification": False,
            "query_result": answer["table"],
            "widgets": [],
            "answer_blocks": answer["blocks"],
            "followUps": answer["followUps"],
            "engine": "nanobaseai-bi-forecast",
            "workflows": {
                "series": {"workflow": "nanobase-metric-series-v1", "sql": series["sql"], "logicalPlan": series.get("logicalPlan"), "rows": series["rowCount"]},
                "forecast": {
                    "workflow": "nanobase-forecast-v1",
                    "status": "DONE",
                    "engine": resp.engine,
                    "engine_version": resp.engine_version,
                    "checkpoint_sha": resp.checkpoint_sha,
                    "bundle_hash": bundle.bundle_hash,
                    "history_points": len(bundle.history),
                    "filled_periods": [d.isoformat() for d in bundle.filled_periods],
                    "warnings": [*bundle.warnings, *resp.warnings],
                    "run_id": run_id,
                },
            },
            "execution_id": execution_id,
            "forecast": {
                "status": "done",
                "metric": metric_code,
                "dimension": dims,
                "frequency": bundle.frequency,
                "horizon": horizon,
                "engine": resp.engine,
                "bundle_hash": bundle.bundle_hash,
                "run_id": run_id,
                "points": [p.model_dump(mode="json") for p in resp.forecast],
            },
        },
        None,
        executed=True,
        execution_mode=execution_mode,
        extra_warnings=["deterministic_fast_path", "sql_source=semantic_metric_compiler", "forecast"],
    )
    yield sse("done", result).encode()


# --- Faz 6.1: reconcile closed periods against forecasts ------------------------


async def reconcile_forecasts(meta_engine: Any, *, as_of: date | None = None, limit: int = 200) -> dict[str, Any]:
    """For every forecast point whose period has closed, fetch the actual from the
    governed series and record within/above_p90/below_p10. No new model."""
    import json as _json

    from nanobase_api.infrastructure.forecast_repo import list_points_due_for_reconcile, record_actual

    as_of = as_of or date.today()
    due = await asyncio.to_thread(list_points_due_for_reconcile, meta_engine, as_of=period_start(as_of, "M"), limit=limit)
    stats = {"due": len(due), "reconciled": 0, "violations": 0, "missing_actual": 0, "errors": 0}
    cache: dict[tuple, dict[str, float]] = {}
    for item in due:
        freq = str(item["frequency"])
        grain = {"M": "month", "W": "week", "Q": "quarter", "Y": "year", "D": "day"}.get(freq, "month")
        dims = item["dimension_filters"]
        if isinstance(dims, str):
            dims = _json.loads(dims or "{}")
        key = (item["tenant_id"], item["datasource_id"], item["metric_code"], grain, _json.dumps(dims, sort_keys=True))
        try:
            if key not in cache:
                series = await load_metric_series(
                    tenant_id=item["tenant_id"],
                    datasource_id=item["datasource_id"],
                    metric_code=item["metric_code"],
                    grain=grain,
                    history_periods=24,
                    dimension_filters=dims,
                )
                cache[key] = {r["period"]: r["value"] for r in series["rows"] if r.get("period") and r.get("value") is not None}
            ts = item["ts"]
            ts_d = ts if isinstance(ts, date) else date.fromisoformat(str(ts)[:10])
            actual = cache[key].get(ts_d.isoformat())
            if actual is None:
                # Period closed but no rows at all → actual is genuinely 0 for an additive metric.
                actual = 0.0 if ts_d < period_start(as_of, "M") else None
            if actual is None:
                stats["missing_actual"] += 1
                continue
            verdict = await asyncio.to_thread(record_actual, meta_engine, run_id=item["run_id"], ts=ts_d, actual=float(actual))
            stats["reconciled"] += 1
            if verdict in ("above_p90", "below_p10"):
                stats["violations"] += 1
        except Exception:  # noqa: BLE001
            stats["errors"] += 1
    stats["next_period_start"] = next_period(period_start(as_of, "M"), "M").isoformat()
    return stats
