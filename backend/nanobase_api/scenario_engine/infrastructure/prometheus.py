"""Prometheus text exposition for scenario engine counters."""

from __future__ import annotations

from nanobase_api.scenario_engine.infrastructure import metrics as m


def render_prometheus() -> str:
    snap = m.snapshot()
    lines: list[str] = [
        "# HELP scenario_engine_info Nanobase scenario engine metrics",
        "# TYPE scenario_engine_info gauge",
        'scenario_engine_info{component="scenario_engine"} 1',
    ]
    counters = snap.get("counters") or {}
    for name, value in sorted(counters.items()):
        safe = str(name).replace("-", "_")
        lines.append(f"# TYPE {safe} counter")
        lines.append(f"{safe} {float(value)}")
    hist = snap.get("histograms") or {}
    for name, meta in sorted(hist.items()):
        safe = str(name).replace("-", "_")
        lines.append(f"# TYPE {safe} summary")
        lines.append(f'{safe}_count {int(meta.get("count") or 0)}')
        last = meta.get("last")
        if last is not None:
            lines.append(f"{safe} {float(last)}")
    return "\n".join(lines) + "\n"
