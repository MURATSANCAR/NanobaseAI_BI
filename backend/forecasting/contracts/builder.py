"""SeriesBundleBuilder — the deterministic layer between governed SQL rows and
the forecast engine (plan Faz 2).

Guarantees, in order: parse → normalize timestamps to period start → reject
duplicates → sort → detect gaps and apply the missing policy → metric rules
(non-negative) → minimum history → horizon cap → canonical hash.

Nothing here is heuristic: every rejection is a coded SeriesBundleError the
chat layer surfaces verbatim. A bundle that passes is reproducible: the same
rows in any order yield the same `bundle_hash`.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from forecasting.contracts.models import (
    FREQUENCIES,
    SeriesBundle,
    SeriesBundleError,
    SeriesPoint,
)

MIN_HISTORY_HARD = 12
MIN_HISTORY_RECOMMENDED = 24
MAX_HORIZON = 12
MAX_HISTORY_POINTS = 120  # bundle cap (CPU cost + TimesFM context)

_SEASONALITY = {"D": 7, "W": 52, "M": 12, "Q": 4, "Y": 1}


def seasonality(frequency: str) -> int:
    return _SEASONALITY.get(frequency, 1)


# --- period arithmetic --------------------------------------------------------


def _to_date(raw: Any) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    s = str(raw).strip()
    if not s:
        raise SeriesBundleError("INVALID_TIMESTAMP", "Boş tarih değeri.")
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(s[:10])
        except ValueError as e:
            raise SeriesBundleError("INVALID_TIMESTAMP", f"Tarih çözümlenemedi: {s}") from e


def period_start(d: date, frequency: str) -> date:
    if frequency == "D":
        return d
    if frequency == "W":
        return d - timedelta(days=d.weekday())
    if frequency == "M":
        return d.replace(day=1)
    if frequency == "Q":
        return d.replace(month=((d.month - 1) // 3) * 3 + 1, day=1)
    if frequency == "Y":
        return d.replace(month=1, day=1)
    raise SeriesBundleError("FREQUENCY_MISMATCH", f"Bilinmeyen frekans: {frequency}")


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    return d.replace(year=d.year + m // 12, month=m % 12 + 1, day=1)


def next_period(d: date, frequency: str, steps: int = 1) -> date:
    if frequency == "D":
        return d + timedelta(days=steps)
    if frequency == "W":
        return d + timedelta(days=7 * steps)
    if frequency == "M":
        return _add_months(d, steps)
    if frequency == "Q":
        return _add_months(d, 3 * steps)
    if frequency == "Y":
        return _add_months(d, 12 * steps)
    raise SeriesBundleError("FREQUENCY_MISMATCH", f"Bilinmeyen frekans: {frequency}")


def future_periods(last: date, frequency: str, horizon: int) -> list[date]:
    return [next_period(last, frequency, i) for i in range(1, horizon + 1)]


# --- builder ------------------------------------------------------------------


def _coerce_value(raw: Any, ts: date) -> float:
    if raw is None:
        return float("nan")
    try:
        return float(raw)
    except (TypeError, ValueError) as e:
        raise SeriesBundleError("INVALID_VALUE", f"Sayısal olmayan değer ({ts.isoformat()}): {raw!r}") from e


def canonical_hash(
    *, series_id: str, frequency: str, history: list[SeriesPoint], horizon: int, missing_policy: str
) -> str:
    payload = {
        "series_id": series_id,
        "frequency": frequency,
        "horizon": horizon,
        "missing_policy": missing_policy,
        "history": [[p.timestamp.isoformat(), round(p.value, 6)] for p in history],
    }
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_series_bundle(
    rows: Iterable[tuple[Any, Any] | dict[str, Any]],
    *,
    metric: str,
    frequency: str,
    horizon: int,
    dimension: dict[str, str] | None = None,
    timezone: str = "Europe/Istanbul",
    missing_policy: str = "zero",
    target_unit: str | None = None,
    metric_version: int | None = None,
    non_negative: bool = True,
    min_history_hard: int = MIN_HISTORY_HARD,
    min_history_recommended: int = MIN_HISTORY_RECOMMENDED,
    max_horizon: int = MAX_HORIZON,
    period_key: str = "period",
    value_key: str | None = None,
) -> SeriesBundle:
    """Normalize governed metric rows into a SeriesBundle or raise SeriesBundleError.

    `rows` are (timestamp, value) pairs or dicts with `period_key` and a value
    column (`value_key`, else the first non-period key).
    """
    if frequency not in FREQUENCIES:
        raise SeriesBundleError("FREQUENCY_MISMATCH", f"Desteklenmeyen frekans: {frequency}")
    if missing_policy not in ("zero", "interpolate", "reject"):
        raise SeriesBundleError("INVALID_POLICY", f"Bilinmeyen eksik-veri politikası: {missing_policy}")
    dimension = {str(k): str(v) for k, v in sorted((dimension or {}).items())}
    warnings: list[str] = []

    # 1) parse + normalize to period start
    seen: dict[date, tuple[date, float]] = {}
    for row in rows:
        if isinstance(row, dict):
            raw_ts = row.get(period_key)
            if value_key is not None:
                raw_val = row.get(value_key)
            else:
                others = [k for k in row.keys() if k != period_key]
                raw_val = row.get(others[0]) if others else None
        else:
            raw_ts, raw_val = row[0], row[1]
        ts = _to_date(raw_ts)
        p = period_start(ts, frequency)
        if p in seen:
            raise SeriesBundleError(
                "DUPLICATE_TIMESTAMPS",
                f"Aynı dönem için birden fazla satır: {p.isoformat()}",
                period=p.isoformat(),
            )
        seen[p] = (ts, _coerce_value(raw_val, ts))
        if ts != p and frequency != "D":
            warnings.append(f"timestamp_normalized:{ts.isoformat()}->{p.isoformat()}")

    if not seen:
        raise SeriesBundleError("INSUFFICIENT_HISTORY", "Seri boş: hiç geçmiş dönem yok.", points=0)

    # 2) sort + gap detection
    ordered = sorted(seen.items())
    first, last = ordered[0][0], ordered[-1][0]
    values: dict[date, float] = {p: v for p, (_, v) in ordered}
    expected: list[date] = []
    cur = first
    while cur <= last:
        expected.append(cur)
        cur = next_period(cur, frequency)
        if len(expected) > 10_000:
            raise SeriesBundleError("FREQUENCY_MISMATCH", "Dönem aralığı frekansla tutarsız.")
    missing = [p for p in expected if p not in values or values[p] != values[p]]  # NaN check
    if missing and missing_policy == "reject":
        raise SeriesBundleError(
            "GAPS_EXCEED_POLICY",
            f"{len(missing)} eksik dönem var ve politika 'reject'.",
            missing=[m.isoformat() for m in missing],
        )
    if missing and missing_policy == "zero":
        for m in missing:
            values[m] = 0.0
    if missing and missing_policy == "interpolate":
        known = [p for p in expected if p in values and values[p] == values[p]]
        for m in missing:
            before = max((k for k in known if k < m), default=None)
            after = min((k for k in known if k > m), default=None)
            if before is None or after is None:
                values[m] = values[before if before is not None else after]
            else:
                span = expected.index(after) - expected.index(before)
                pos = expected.index(m) - expected.index(before)
                values[m] = values[before] + (values[after] - values[before]) * pos / span
    if missing:
        warnings.append(f"filled_periods:{len(missing)}:{missing_policy}")

    history = [SeriesPoint(timestamp=p, value=float(values[p])) for p in expected]

    # 3) metric rules
    if non_negative:
        bad = [pt for pt in history if pt.value < 0]
        if bad:
            raise SeriesBundleError(
                "NEGATIVE_VALUE_FOR_METRIC",
                f"Metrik negatif olamaz; {len(bad)} dönem negatif (ilk: {bad[0].timestamp.isoformat()}).",
                metric=metric,
            )

    # 4) history bounds
    if len(history) > MAX_HISTORY_POINTS:
        history = history[-MAX_HISTORY_POINTS:]
        warnings.append(f"history_truncated:{MAX_HISTORY_POINTS}")
    if len(history) < min_history_hard:
        raise SeriesBundleError(
            "INSUFFICIENT_HISTORY",
            f"En az {min_history_hard} dönem geçmiş gerekir; {len(history)} dönem var.",
            points=len(history),
            required=min_history_hard,
        )
    if len(history) < min_history_recommended:
        warnings.append(f"short_history:{len(history)}<{min_history_recommended}")

    # 5) horizon cap
    cap = min(max_horizon, max(1, len(history) // 3))
    if horizon > cap:
        raise SeriesBundleError(
            "HORIZON_TOO_LONG",
            f"Ufuk {horizon} dönem; bu seri için en fazla {cap} dönem tahmin edilebilir.",
            horizon=horizon,
            max_horizon=cap,
        )

    dim_part = ",".join(f"{k}={v}" for k, v in dimension.items())
    series_id = f"{metric}|{dim_part}" if dim_part else metric
    bundle = SeriesBundle(
        series_id=series_id,
        metric=metric,
        dimension=dimension,
        frequency=frequency,  # type: ignore[arg-type]
        timezone=timezone,
        history=history,
        horizon=horizon,
        target_unit=target_unit,
        missing_policy=missing_policy,  # type: ignore[arg-type]
        filled_periods=missing,
        warnings=warnings,
        metric_version=metric_version,
    )
    bundle.bundle_hash = canonical_hash(
        series_id=series_id,
        frequency=frequency,
        history=history,
        horizon=horizon,
        missing_policy=missing_policy,
    )
    return bundle
