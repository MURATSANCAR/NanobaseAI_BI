"""Prometheus-style counters (in-process; scrape adapter can wire later)."""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

_lock = Lock()
_counters: dict[str, float] = defaultdict(float)
_histograms: dict[str, list[float]] = defaultdict(list)


def inc(name: str, value: float = 1.0) -> None:
    with _lock:
        _counters[name] += value


def observe(name: str, value: float) -> None:
    with _lock:
        _histograms[name].append(value)


def snapshot() -> dict[str, object]:
    with _lock:
        return {
            "counters": dict(_counters),
            "histograms": {k: {"count": len(v), "last": v[-1] if v else None} for k, v in _histograms.items()},
        }


# Named metrics from spec §34
SCENARIO_CANDIDATES_GENERATED = "scenario_candidates_generated_total"
SCENARIO_STATIC_VALIDATION_FAILURES = "scenario_static_validation_failures_total"
SCENARIO_EXECUTION_VALIDATION_FAILURES = "scenario_execution_validation_failures_total"
SCENARIO_PERFORMANCE_VALIDATION_FAILURES = "scenario_performance_validation_failures_total"
SCENARIO_PUBLISHED = "scenario_published_total"
SCENARIO_STALE = "scenario_stale_total"
SCENARIO_MATCH_DURATION = "scenario_match_duration_seconds"
SCENARIO_EXACT_MATCH = "scenario_exact_match_total"
SCENARIO_SEMANTIC_MATCH = "scenario_semantic_match_total"
SCENARIO_FALLBACK_AWEL = "scenario_fallback_to_awel_total"
SCENARIO_CACHE_HIT = "scenario_cache_hit_total"
SCENARIO_GATEWAY_REJECTIONS = "scenario_query_gateway_rejections_total"
SCENARIO_RUNTIME_FAILURES = "scenario_runtime_failures_total"
