#!/usr/bin/env python3
"""Live capacity measurement for the chat pipeline (the deferred
``MEASURE_ON_LIVE_MODEL`` item from the release gate).

For each concurrency profile it fires that many *simultaneous* chat streams
(distinct sessions — the per-(tenant,session) gate would otherwise serialize
them) and measures what a real user feels: total latency, time-to-first-token,
queue waits, timeouts and errors. Results land next to the release-gate format
so ``capacity-results.json`` finally carries numbers instead of
``MEASURE_ON_LIVE_MODEL`` placeholders.

Run on the BI server with the full stack up (llama.cpp with ``--parallel N``
matching MODEL_MAX_CONCURRENCY):

    python3 tests/text2sql/run-capacity-probe.py
    python3 tests/text2sql/run-capacity-probe.py --profiles 1,2,4 --rounds 2
    python3 tests/text2sql/run-capacity-probe.py --timeout 240

Environment:
    NANOBASE_API_BASE  default http://127.0.0.1:8790
    NANOBASE_BEARER    optional JWT (omit in DEV auth mode)
    CAPACITY_OUT_DIR   default artifacts/capacity

Interpretation guide (printed into the report):
  - p95 at concurrency 1 ≈ raw pipeline latency.
  - If p95 at concurrency N ≈ N × (p95 at 1), requests are serializing —
    raise llama.cpp ``--parallel`` + MODEL_MAX_CONCURRENCY together.
  - queue_timeout / session_queued counts show where the ceiling is.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

API_BASE = os.environ.get("NANOBASE_API_BASE", "http://127.0.0.1:8790").rstrip("/")
BEARER = (os.environ.get("NANOBASE_BEARER") or "").strip()

# Distinct questions so the learned cache / scenario engine can't turn the
# probe into a cache benchmark; all resolve against the seeded reporting DB.
QUESTIONS = [
    "Kaç müşteri var?",
    "Segmentlere göre toplam ciro nedir?",
    "En çok adet satılan 3 ürünü listele",
    "2026 yılında verilen sipariş sayısı kaç?",
    "Fatura durumlarına göre fatura adedi nedir?",
    "Ülkelere göre müşteri sayısını sırala",
    "Açık faturaların toplam kalan tutarı ne kadar?",
    "Ürün kategorilerine göre ortalama birim fiyat nedir?",
]


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if BEARER:
        h["Authorization"] = f"Bearer {BEARER}"
    h.update(extra or {})
    return h


def _get_json(path: str, timeout: float = 10.0) -> dict[str, Any]:
    req = urllib.request.Request(f"{API_BASE}{path}", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def one_chat(question: str, timeout: float) -> dict[str, Any]:
    """Single chat stream → user-facing timing summary."""
    body = {
        "message": question,
        "session_id": f"cap-{uuid.uuid4()}",
        "db_name": os.environ.get("CAPACITY_DATASOURCE", "bi_reporting"),
    }
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/bi/chat/stream",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers=_headers({"Accept": "text/event-stream"}),
    )
    t0 = time.time()
    out: dict[str, Any] = {
        "question": question,
        "ok": False,
        "error": None,
        "ttft_s": None,
        "queue_waits": 0,
        "max_queue_position": 0,
        "repairs": 0,
        "phases_seen": 0,
    }
    event = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line.startswith("event:"):
                    event = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                try:
                    data = json.loads(line[5:].strip())
                except Exception:
                    continue
                if event == "status":
                    out["phases_seen"] += 1
                    phase = str(data.get("phase") or "")
                    if phase in ("queued", "session_queued"):
                        out["queue_waits"] += 1
                        pos = data.get("position")
                        if isinstance(pos, (int, float)):
                            out["max_queue_position"] = max(out["max_queue_position"], int(pos))
                    elif phase == "repairing_sql":
                        out["repairs"] += 1
                elif event in ("token", "answer_delta") and out["ttft_s"] is None:
                    out["ttft_s"] = round(time.time() - t0, 2)
                elif event == "done":
                    out["ok"] = True
                elif event == "error":
                    out["error"] = str(data.get("code") or data.get("message") or "error")[:200]
    except Exception as e:  # noqa: BLE001 — a timeout IS the measurement
        out["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    out["elapsed_s"] = round(time.time() - t0, 2)
    return out


def _pct(values: list[float], q: float) -> float | None:
    vals = sorted(values)
    if not vals:
        return None
    idx = min(len(vals) - 1, max(0, int(round((len(vals) - 1) * q))))
    return round(vals[idx], 2)


def run_profile(concurrency: int, rounds: int, timeout: float) -> dict[str, Any]:
    total = concurrency * rounds
    tasks = [QUESTIONS[i % len(QUESTIONS)] for i in range(total)]
    queue_before = _get_json("/api/v1/bi/model-queue/status")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda q: one_chat(q, timeout), tasks))
    wall = round(time.time() - t0, 2)
    queue_after = _get_json("/api/v1/bi/model-queue/status")

    ok = [r for r in results if r["ok"]]
    latencies = [r["elapsed_s"] for r in ok]
    ttfts = [r["ttft_s"] for r in ok if r.get("ttft_s") is not None]
    return {
        "concurrentPlanners": concurrency,
        "requests": total,
        "succeeded": len(ok),
        "errors": [r["error"] for r in results if r["error"]][:10],
        "error_rate": round(1 - len(ok) / total, 3) if total else None,
        "wall_clock_s": wall,
        "throughput_req_per_min": round(total / wall * 60, 2) if wall else None,
        "latency_p50_s": _pct(latencies, 0.50),
        "latency_p95_s": _pct(latencies, 0.95),
        "latency_max_s": max(latencies) if latencies else None,
        "ttft_p50_s": _pct(ttfts, 0.50),
        "queue_waits_total": sum(r["queue_waits"] for r in results),
        "max_queue_position": max((r["max_queue_position"] for r in results), default=0),
        "repairs_total": sum(r["repairs"] for r in results),
        "model_queue_before": queue_before or None,
        "model_queue_after": queue_after or None,
        "status": "MEASURED",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profiles", default="1,2,4,8", help="comma-separated concurrency levels")
    ap.add_argument("--rounds", type=int, default=3, help="requests per worker per profile")
    ap.add_argument("--timeout", type=float, default=300.0, help="per-request timeout (s)")
    ap.add_argument("--cooldown", type=float, default=5.0, help="pause between profiles (s)")
    args = ap.parse_args()

    profiles = [int(p) for p in args.profiles.split(",") if p.strip()]
    health = _get_json("/health") or _get_json("/api/v1/bi/status")
    print(f"→ target {API_BASE} · profiles {profiles} · rounds {args.rounds}")
    if not health:
        print("!! API is not answering /health — start the stack first", file=sys.stderr)
        return 2

    measured: list[dict[str, Any]] = []
    for level in profiles:
        print(f"\n== concurrency {level} ({level * args.rounds} requests) ==")
        prof = run_profile(level, args.rounds, args.timeout)
        measured.append(prof)
        print(
            f"   ok {prof['succeeded']}/{prof['requests']} · p50 {prof['latency_p50_s']}s · "
            f"p95 {prof['latency_p95_s']}s · ttft p50 {prof['ttft_p50_s']}s · "
            f"queue waits {prof['queue_waits_total']} · {prof['throughput_req_per_min']} req/min"
        )
        if prof["errors"]:
            print(f"   errors: {prof['errors'][:3]}")
        time.sleep(args.cooldown)

    base = measured[0] if measured else {}
    serialization_note = ""
    if base.get("latency_p95_s") and len(measured) > 1:
        worst = measured[-1]
        if worst.get("latency_p95_s") and worst["concurrentPlanners"] > 1:
            ratio = worst["latency_p95_s"] / base["latency_p95_s"]
            expected_if_serial = float(worst["concurrentPlanners"])
            serialization_note = (
                f"p95 grows {ratio:.1f}× from concurrency 1 → {worst['concurrentPlanners']} "
                f"(pure serialization would be ~{expected_if_serial:.0f}×). "
                + (
                    "Requests are effectively serializing — raise llama.cpp --parallel "
                    "and MODEL_MAX_CONCURRENCY together."
                    if ratio > expected_if_serial * 0.7
                    else "Parallel slots are absorbing load."
                )
            )

    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "MODEL_MAX_CONCURRENCY": (base.get("model_queue_before") or {}).get("maxConcurrency"),
        "profiles": measured,
        "serialization_assessment": serialization_note or None,
        "pass": all((p["error_rate"] or 0) < 0.34 for p in measured),
    }

    out_dir = Path(os.environ.get("CAPACITY_OUT_DIR", str(ROOT / "artifacts/capacity")))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "capacity-results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Canlı kapasite ölçümü",
        "",
        f"- Zaman: `{summary['generatedAt']}`",
        f"- MODEL_MAX_CONCURRENCY: `{summary['MODEL_MAX_CONCURRENCY']}`",
        "",
        "| Eşzamanlı | İstek | Başarı | p50 | p95 | TTFT p50 | Kuyruk | req/dk |",
        "|-----------|-------|--------|-----|-----|----------|--------|--------|",
    ]
    for p in measured:
        lines.append(
            f"| {p['concurrentPlanners']} | {p['requests']} | {p['succeeded']} | "
            f"{p['latency_p50_s']}s | {p['latency_p95_s']}s | {p['ttft_p50_s']}s | "
            f"{p['queue_waits_total']} | {p['throughput_req_per_min']} |"
        )
    if serialization_note:
        lines += ["", f"**Değerlendirme:** {serialization_note}"]
    (out_dir / "capacity-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nreports → {out_dir}/capacity-results.json, capacity-results.md")
    if serialization_note:
        print(f"assessment: {serialization_note}")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
