"""Rolling-origin backtest — the quality gate for choosing the production engine
(plan Faz 4). Nothing is trusted because it is a foundation model: every engine
is scored against the same holdouts, and the recommended engine is the WAPE
winner only if it beats seasonal_naive.

Usage:
  python -m forecasting.evaluation.benchmark --synthetic 6 --engines naive,seasonal_naive
  python -m forecasting.evaluation.benchmark --dataset series.json --engines naive,seasonal_naive,timesfm25 \
      --holdout 6 --origins 3 --out artifacts/forecast/benchmark-2026-09-06.json

Dataset JSON: [{"series_id": "...", "frequency": "M", "history": [["2023-01-01", 123.0], ...]}, ...]
Metrics per (engine): WAPE, sMAPE, RMSE (on p50) and 80% interval coverage (p10..p90).
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from forecasting.app.engines import create_engine
from forecasting.contracts import SeriesBundleError, build_series_bundle
from forecasting.contracts.builder import next_period

BASELINE = "seasonal_naive"


# --- metrics ------------------------------------------------------------------


def wape(actual: list[float], pred: list[float]) -> float:
    denom = sum(abs(a) for a in actual)
    if denom == 0:
        return float("nan")
    return sum(abs(a - p) for a, p in zip(actual, pred)) / denom


def smape(actual: list[float], pred: list[float]) -> float:
    terms = []
    for a, p in zip(actual, pred):
        d = (abs(a) + abs(p)) / 2
        terms.append(0.0 if d == 0 else abs(a - p) / d)
    return sum(terms) / len(terms) if terms else float("nan")


def rmse(actual: list[float], pred: list[float]) -> float:
    if not actual:
        return float("nan")
    return math.sqrt(sum((a - p) ** 2 for a, p in zip(actual, pred)) / len(actual))


def coverage(actual: list[float], lo: list[float], hi: list[float]) -> float:
    if not actual:
        return float("nan")
    return sum(1 for a, l, h in zip(actual, lo, hi) if l <= a <= h) / len(actual)


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x == x]  # drop NaN
    return sum(xs) / len(xs) if xs else None


# --- datasets -----------------------------------------------------------------


def synthetic_dataset(n_series: int, months: int = 48, seed: int = 42) -> list[dict[str, Any]]:
    rnd = random.Random(seed)
    out = []
    for s in range(n_series):
        base = rnd.uniform(500, 5000)
        trend = rnd.uniform(0.0, 0.02)
        amp = rnd.uniform(0.05, 0.3)
        noise = rnd.uniform(0.02, 0.12)
        hist = []
        for i in range(months):
            d = next_period(date(2022, 9, 1), "M", i)
            season = 1 + amp * math.sin(2 * math.pi * (d.month - 1) / 12 - math.pi / 2)
            v = base * (1 + trend * i) * season * (1 + rnd.gauss(0, noise))
            hist.append([d.isoformat(), max(0.0, v)])
        out.append({"series_id": f"synthetic_{s}", "frequency": "M", "history": hist})
    return out


def load_dataset(path: str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "series" in data:
        data = data["series"]
    return data


# --- backtest -----------------------------------------------------------------


def run_benchmark(
    dataset: list[dict[str, Any]],
    engines: list[str],
    *,
    holdout: int = 6,
    origins: int = 3,
) -> dict[str, Any]:
    loaded = {}
    engine_errors: dict[str, str] = {}
    for name in engines:
        try:
            eng = create_engine(name)
            eng.load()
            loaded[name] = eng
        except Exception as e:  # noqa: BLE001 — recorded, benchmark continues
            engine_errors[name] = f"{type(e).__name__}: {e}"

    per_engine: dict[str, dict[str, list[float]]] = {n: {"wape": [], "smape": [], "rmse": [], "coverage": [], "latency_ms": []} for n in loaded}
    folds: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for series in dataset:
        sid = series["series_id"]
        freq = series.get("frequency", "M")
        hist = [(h[0], float(h[1])) for h in series["history"]]
        for k in range(origins):
            cut = len(hist) - holdout - k
            if cut < 12:
                skipped.append({"series_id": sid, "origin": k, "reason": "too_short"})
                continue
            train, test = hist[:cut], hist[cut : cut + holdout]
            actual = [v for _, v in test]
            try:
                bundle = build_series_bundle(train, metric=sid, frequency=freq, horizon=len(test))
            except SeriesBundleError as e:
                skipped.append({"series_id": sid, "origin": k, "reason": e.code})
                continue
            fold = {"series_id": sid, "origin": k, "train_points": len(train), "horizon": len(test), "engines": {}}
            for name, eng in loaded.items():
                t0 = time.perf_counter()
                try:
                    out = eng.forecast(bundle)
                except Exception as e:  # noqa: BLE001
                    fold["engines"][name] = {"error": f"{type(e).__name__}: {e}"}
                    continue
                ms = (time.perf_counter() - t0) * 1000
                p50 = [p.p50 for p in out.points]
                p10 = [p.p10 for p in out.points]
                p90 = [p.p90 for p in out.points]
                m = {
                    "wape": wape(actual, p50),
                    "smape": smape(actual, p50),
                    "rmse": rmse(actual, p50),
                    "coverage": coverage(actual, p10, p90),
                    "latency_ms": ms,
                }
                fold["engines"][name] = m
                for key, val in m.items():
                    per_engine[name][key].append(val)
            folds.append(fold)

    summary = {}
    for name, metrics in per_engine.items():
        summary[name] = {k: _mean(v) for k, v in metrics.items()}
        summary[name]["folds"] = len(metrics["wape"])

    baseline_wape = (summary.get(BASELINE) or {}).get("wape")
    ranked = sorted(
        [(n, s["wape"]) for n, s in summary.items() if s.get("wape") is not None], key=lambda x: x[1]
    )
    recommended = BASELINE if BASELINE in summary else (ranked[0][0] if ranked else None)
    gate: dict[str, Any] = {"baseline": BASELINE, "baseline_wape": baseline_wape, "verdicts": {}}
    for name, w in ranked:
        if name == BASELINE:
            continue
        beats = baseline_wape is not None and w < baseline_wape
        gate["verdicts"][name] = {"wape": w, "beats_baseline": beats}
    if ranked and baseline_wape is not None and ranked[0][1] < baseline_wape:
        recommended = ranked[0][0]
    gate["recommended_engine"] = recommended

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "config": {"holdout": holdout, "origins": origins, "engines": engines, "n_series": len(dataset)},
        "engine_errors": engine_errors,
        "summary": summary,
        "gate": gate,
        "skipped": skipped,
        "folds": folds,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", help="JSON dataset path")
    ap.add_argument("--synthetic", type=int, default=0, help="generate N synthetic monthly series instead")
    ap.add_argument("--engines", default="naive,seasonal_naive")
    ap.add_argument("--holdout", type=int, default=6)
    ap.add_argument("--origins", type=int, default=3)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    if args.dataset:
        dataset = load_dataset(args.dataset)
    elif args.synthetic:
        dataset = synthetic_dataset(args.synthetic)
    else:
        ap.error("--dataset or --synthetic required")

    report = run_benchmark(dataset, [e.strip() for e in args.engines.split(",") if e.strip()], holdout=args.holdout, origins=args.origins)
    out = args.out or f"artifacts/forecast/benchmark-{date.today().isoformat()}.json"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{'engine':<20}{'WAPE':>8}{'sMAPE':>8}{'RMSE':>12}{'cov80':>8}{'ms':>8}{'folds':>7}")
    for name, s in sorted(report["summary"].items(), key=lambda kv: (kv[1].get("wape") is None, kv[1].get("wape") or 9)):
        f = lambda v, p=3: "-" if v is None else f"{v:.{p}f}"  # noqa: E731
        print(f"{name:<20}{f(s['wape']):>8}{f(s['smape']):>8}{f(s['rmse'], 1):>12}{f(s['coverage'], 2):>8}{f(s['latency_ms'], 0):>8}{s['folds']:>7}")
    for name, err in report["engine_errors"].items():
        print(f"{name:<20}ERROR {err}")
    print(f"recommended_engine: {report['gate']['recommended_engine']}  → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
