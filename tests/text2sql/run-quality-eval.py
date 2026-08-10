#!/usr/bin/env python3
"""Execution-accuracy evaluation for the Text2SQL chat pipeline.

Runs each corpus question through the REAL chat pipeline (retrieval → plan →
shape guard → Gateway validate → repair → execute → explain) and compares the
returned RESULT SET against the result of hand-written reference SQL executed
through the same Gateway.

Why this exists: the pre-existing suites score token containment
(``expect_sql_tokens``) or synthetic fingerprints, so SQL that is wrong but
mentions the right words passes. Execution accuracy is the metric that
actually moves when generation quality changes.

Usage (on the BI server, stack running):

    python3 tests/text2sql/run-quality-eval.py
    python3 tests/text2sql/run-quality-eval.py --corpus tests/text2sql/quality-corpus.yaml
    python3 tests/text2sql/run-quality-eval.py --write-baseline     # lock in current state
    python3 tests/text2sql/run-quality-eval.py --compare-baseline   # fail on regressions
    python3 tests/text2sql/run-quality-eval.py --only qa-014,qa-015 --verbose

Environment:
    NANOBASE_API_BASE   default http://127.0.0.1:8790
    NANOBASE_BEARER     optional JWT (omit when the API runs in DEV auth mode)
    QUALITY_TIMEOUT_SEC per-question timeout, default 300
    QUALITY_OUT_DIR     default artifacts/quality

Exit code: 0 when accuracy >= corpus pass_threshold (and no baseline
regressions when --compare-baseline), else 1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from itertools import combinations, permutations
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None

API_BASE = os.environ.get("NANOBASE_API_BASE", "http://127.0.0.1:8790").rstrip("/")
BEARER = (os.environ.get("NANOBASE_BEARER") or "").strip()
TIMEOUT = float(os.environ.get("QUALITY_TIMEOUT_SEC", "300"))
# Column-permutation search is bounded: wide result sets are compared by the
# first N columns only (see _match_rows).
MAX_PERMUTE_COLS = 6


# --------------------------------------------------------------------------
# HTTP helpers (stdlib only — matches run-smoke-tests.py house style)
# --------------------------------------------------------------------------


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if BEARER:
        h["Authorization"] = f"Bearer {BEARER}"
    h.update(extra or {})
    return h


def _post_json(path: str, body: dict[str, Any], timeout: float = 120.0) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers=_headers(),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data.setdefault("ok", False)
                data.setdefault("http_status", e.code)
                return data
        except Exception:
            pass
        return {"ok": False, "http_status": e.code, "error": raw[:400]}


def _chat_stream(
    question: str,
    datasource: str,
    *,
    session_id: str,
    timeout: float = TIMEOUT,
) -> dict[str, Any]:
    """Drive POST /api/v1/bi/chat/stream and fold the SSE frames into a summary."""
    body = {"message": question, "session_id": session_id, "db_name": datasource}
    req = urllib.request.Request(
        f"{API_BASE}/api/v1/bi/chat/stream",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers=_headers({"Accept": "text/event-stream"}),
    )
    out: dict[str, Any] = {
        "phases": [],
        "sql": None,
        "sql_source": None,
        "repairs": 0,
        "guard_blocks": [],
        "queue_waits": 0,
        "ttft_s": None,
        "tokens": 0,
        "done": None,
        "error": None,
        "clarification": False,
    }
    t0 = time.time()
    event = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
                if line.startswith("event:"):
                    event = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                try:
                    data = json.loads(payload)
                except Exception:
                    continue
                if event == "status":
                    phase = str(data.get("phase") or "")
                    out["phases"].append(phase)
                    if phase == "repairing_sql":
                        out["repairs"] += 1
                    elif phase == "sql_shape_guard":
                        out["guard_blocks"].append(str(data.get("code") or ""))
                    elif phase in ("queued", "session_queued"):
                        out["queue_waits"] += 1
                    elif phase == "clarification_required":
                        out["clarification"] = True
                elif event == "sql_generated":
                    p = data.get("payload") or data
                    out["sql"] = p.get("sql") or out["sql"]
                    out["sql_source"] = p.get("sql_source") or out["sql_source"]
                elif event in ("token", "answer_delta"):
                    if out["ttft_s"] is None:
                        out["ttft_s"] = round(time.time() - t0, 2)
                    out["tokens"] += 1
                elif event == "done":
                    out["done"] = data
                elif event == "error":
                    out["error"] = str(data.get("message") or data.get("code") or "error")[:400]
    except urllib.error.HTTPError as e:
        out["error"] = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}"
    except Exception as e:  # noqa: BLE001 — timeouts / resets are results, not crashes
        out["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    out["elapsed_s"] = round(time.time() - t0, 2)
    done = out["done"] or {}
    out["needs_clarification"] = bool(done.get("needs_clarification")) or out["clarification"]
    prov = done.get("provenance") or {}
    out["executed"] = bool(prov.get("executed"))
    out["warnings"] = [str(w) for w in (prov.get("warnings") or done.get("warnings") or [])]
    qr = done.get("query_result") or {}
    out["columns"] = list(qr.get("columns") or [])
    out["rows"] = list(qr.get("rows") or [])
    out["final_sql"] = done.get("sql") or out["sql"]
    return out


def _execute_sql(sql: str, datasource: str) -> dict[str, Any]:
    """Run reference SQL through the same Gateway the pipeline uses."""
    return _post_json(
        "/api/v1/bi/query/execute",
        {"sql": sql, "datasource_id": datasource},
        timeout=120.0,
    )


# --------------------------------------------------------------------------
# Result-set comparison
# --------------------------------------------------------------------------


def _norm_value(v: Any, tol: float) -> Any:
    """Normalize a cell so equivalent SQL shapes compare equal.

    Numbers are quantized to the tolerance, dates/timestamps reduced to their
    ISO date part (DATE_TRUNC('month', ...) returns a timestamp while a
    reference may return a date), strings stripped/casefolded.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v) / tol) * tol if tol > 0 else float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()[:10]
    s = str(v).strip()
    try:
        return round(float(s) / tol) * tol if tol > 0 else float(s)
    except ValueError:
        pass
    # ISO date/timestamp strings → date part
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        head = s[:10]
        try:
            datetime.strptime(head, "%Y-%m-%d")
            return head
        except ValueError:
            pass
    return s.casefold()


def _row_tuples(
    rows: Iterable[dict[str, Any] | list[Any]],
    columns: list[Any],
    tol: float,
) -> list[tuple[Any, ...]]:
    col_names = [
        str(c.get("name") if isinstance(c, dict) else c) for c in (columns or [])
    ]
    out: list[tuple[Any, ...]] = []
    for r in rows:
        if isinstance(r, dict):
            keys = col_names or list(r.keys())
            out.append(tuple(_norm_value(r.get(k), tol) for k in keys))
        elif isinstance(r, (list, tuple)):
            out.append(tuple(_norm_value(v, tol) for v in r))
        else:
            out.append((_norm_value(r, tol),))
    return out


def _match_rows(
    gold: list[tuple[Any, ...]],
    got: list[tuple[Any, ...]],
    *,
    ordered: bool,
) -> bool:
    """Execution-accuracy match tolerant of column order and extra columns.

    A generated query that answers the question but also projects helper
    columns (a very common and acceptable LLM habit) still passes, as long as
    some column selection reproduces the gold result exactly.
    """
    if not gold:
        return not got
    if not got:
        return False
    if len(gold) != len(got):
        return False
    gold_w = len(gold[0])
    got_w = max(len(r) for r in got)
    if got_w < gold_w:
        return False

    def eq(sel: tuple[int, ...]) -> bool:
        projected = [tuple(r[i] if i < len(r) else None for i in sel) for r in got]
        if ordered:
            return projected == gold
        return sorted(projected, key=repr) == sorted(gold, key=repr)

    if got_w == gold_w and eq(tuple(range(gold_w))):
        return True
    # Bounded search: pick gold_w of the first MAX_PERMUTE_COLS columns, any order.
    width = min(got_w, MAX_PERMUTE_COLS)
    if gold_w > width:
        return False
    for combo in combinations(range(width), gold_w):
        for perm in permutations(combo):
            if eq(perm):
                return True
    return False


def _scalar_match(
    gold: list[tuple[Any, ...]],
    got: list[tuple[Any, ...]],
) -> bool:
    """Scalar answers: the gold value must appear in the first returned row."""
    if not gold or not gold[0]:
        return False
    target = gold[0][0]
    if not got:
        return False
    return any(cell == target for cell in got[0])


# --------------------------------------------------------------------------
# Case evaluation
# --------------------------------------------------------------------------


def evaluate_case(case: dict[str, Any], datasource: str, *, verbose: bool) -> dict[str, Any]:
    cid = str(case.get("id") or "?")
    question = str(case.get("question") or "").strip()
    expect = str(case.get("expect") or "").strip()
    tol = float(case.get("tolerance") or 1e-6)
    ordered = bool(case.get("ordered"))
    shape = str(case.get("shape") or "rows")
    session_id = f"qa-eval-{cid}-{int(time.time())}"

    res: dict[str, Any] = {
        "id": cid,
        "question": question,
        "tags": list(case.get("tags") or []),
        "mode": "safety" if expect else "execution",
        "passed": False,
        "reason": "",
    }

    run = _chat_stream(question, datasource, session_id=session_id)
    res.update(
        {
            "generated_sql": run.get("final_sql"),
            "sql_source": run.get("sql_source"),
            "repairs": run.get("repairs"),
            "guard_blocks": run.get("guard_blocks"),
            "queue_waits": run.get("queue_waits"),
            "warnings": run.get("warnings"),
            "ttft_s": run.get("ttft_s"),
            "elapsed_s": run.get("elapsed_s"),
            "stream_error": run.get("error"),
        }
    )

    # Safety cases: the pipeline must ask / refuse rather than fabricate.
    if expect:
        asked = bool(run.get("needs_clarification"))
        executed = bool(run.get("executed"))
        res["passed"] = asked or not executed
        res["reason"] = (
            "clarification requested"
            if asked
            else ("no fabricated execution" if not executed else "answered a question it should not have")
        )
        return res

    ref_sql = str(case.get("reference_sql") or "").strip()
    if not ref_sql:
        res["reason"] = "corpus case has no reference_sql"
        return res

    gold_raw = _execute_sql(ref_sql, datasource)
    if not gold_raw.get("ok"):
        res["reason"] = f"reference SQL failed: {str(gold_raw.get('message') or gold_raw.get('error'))[:200]}"
        res["reference_broken"] = True
        return res

    gold = _row_tuples(gold_raw.get("rows") or [], gold_raw.get("columns") or [], tol)
    got = _row_tuples(run.get("rows") or [], run.get("columns") or [], tol)
    res["gold_row_count"] = len(gold)
    res["got_row_count"] = len(got)

    if run.get("error"):
        res["reason"] = f"pipeline error: {run['error']}"
        return res
    if not run.get("executed"):
        res["reason"] = "pipeline produced no executed result"
        return res

    ok = _scalar_match(gold, got) if shape == "scalar" else _match_rows(gold, got, ordered=ordered)
    res["passed"] = ok
    res["reason"] = "result set matches reference" if ok else "result set differs from reference"
    if verbose and not ok:
        res["gold_sample"] = [list(r) for r in gold[:3]]
        res["got_sample"] = [list(r) for r in got[:3]]
    return res


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _tag_breakdown(results: list[dict[str, Any]]) -> dict[str, str]:
    agg: dict[str, list[int]] = {}
    for r in results:
        for tag in r.get("tags") or ["untagged"]:
            slot = agg.setdefault(str(tag), [0, 0])
            slot[1] += 1
            if r["passed"]:
                slot[0] += 1
    return {k: f"{v[0]}/{v[1]}" for k, v in sorted(agg.items())}


def _percentile(values: list[float], q: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    idx = min(len(vals) - 1, max(0, int(round((len(vals) - 1) * q))))
    return round(vals[idx], 2)


def write_reports(summary: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "quality-eval.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    lines = [
        "# Text2SQL execution accuracy",
        "",
        f"- Zaman: `{summary['ts']}`",
        f"- Datasource: `{summary['datasource']}`",
        f"- Korpus: `{summary['corpus']}` ({summary['case_count']} vaka)",
        f"- **Execution accuracy: {summary['accuracy']:.1%}** "
        f"({summary['passed_count']}/{summary['case_count']}, eşik {summary['pass_threshold']:.0%}) → "
        f"{'PASS' if summary['passed'] else 'FAIL'}",
        f"- Pipeline hata oranı: {summary['error_rate']:.1%} · repair'li vaka: {summary['cases_with_repair']}",
        f"- Gecikme: p50 {summary['latency_p50_s']}s · p95 {summary['latency_p95_s']}s · "
        f"ilk token p50 {summary['ttft_p50_s']}s",
        "",
        "## Etiket kırılımı",
        "",
        "| Etiket | Geçen |",
        "|--------|-------|",
    ]
    for tag, score in summary["tags"].items():
        lines.append(f"| {tag} | {score} |")
    lines += [
        "",
        "## Vakalar",
        "",
        "| ID | Sonuç | Süre | Repair | Not |",
        "|----|-------|------|--------|-----|",
    ]
    for r in summary["results"]:
        lines.append(
            f"| `{r['id']}` | {'PASS' if r['passed'] else 'FAIL'} | {r.get('elapsed_s')}s | "
            f"{r.get('repairs') or 0} | {r.get('reason', '')} |"
        )
    if summary.get("broken_references"):
        lines += [
            "",
            "## Bozuk referans SQL (korpus bakımı gerekli)",
            "",
            *[f"- `{cid}`" for cid in summary["broken_references"]],
        ]
    (out_dir / "quality-eval.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=str(HERE / "quality-corpus.yaml"))
    ap.add_argument("--datasource", default=None)
    ap.add_argument("--only", default="", help="comma-separated case ids")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--compare-baseline", action="store_true")
    ap.add_argument("--baseline", default=str(HERE / "quality-baseline.json"))
    ap.add_argument("--verbose", action="store_true", help="include row samples for failures")
    args = ap.parse_args()

    if yaml is None:
        raise SystemExit("PyYAML required: pip install pyyaml")
    corpus_path = Path(args.corpus)
    corpus = yaml.safe_load(corpus_path.read_text(encoding="utf-8")) or {}
    datasource = args.datasource or str(corpus.get("datasource") or "bi_reporting")
    threshold = float(corpus.get("pass_threshold") or 0.80)
    cases = list(corpus.get("cases") or corpus.get("questions") or [])
    if args.only:
        wanted = {c.strip() for c in args.only.split(",") if c.strip()}
        cases = [c for c in cases if str(c.get("id")) in wanted]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("no cases selected")

    print(f"→ {len(cases)} case(s) against {API_BASE} (datasource={datasource})")
    results: list[dict[str, Any]] = []
    for i, case in enumerate(cases, start=1):
        r = evaluate_case(case, datasource, verbose=args.verbose)
        results.append(r)
        print(
            f"[{'PASS' if r['passed'] else 'FAIL'}] {i:>3}/{len(cases)} {r['id']:<8} "
            f"{r.get('elapsed_s')}s repair={r.get('repairs') or 0} — {r.get('reason', '')}"
        )

    passed_count = sum(1 for r in results if r["passed"])
    accuracy = passed_count / len(results)
    latencies = [float(r["elapsed_s"]) for r in results if r.get("elapsed_s") is not None]
    ttfts = [float(r["ttft_s"]) for r in results if r.get("ttft_s") is not None]
    summary: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "api_base": API_BASE,
        "corpus": corpus_path.name,
        "datasource": datasource,
        "case_count": len(results),
        "passed_count": passed_count,
        "accuracy": round(accuracy, 4),
        "pass_threshold": threshold,
        "passed": accuracy >= threshold,
        "error_rate": round(
            sum(1 for r in results if r.get("stream_error")) / len(results), 4
        ),
        "cases_with_repair": sum(1 for r in results if (r.get("repairs") or 0) > 0),
        "latency_p50_s": _percentile(latencies, 0.50),
        "latency_p95_s": _percentile(latencies, 0.95),
        "ttft_p50_s": _percentile(ttfts, 0.50),
        "broken_references": [r["id"] for r in results if r.get("reference_broken")],
        "tags": _tag_breakdown(results),
        "results": results,
    }

    out_dir = Path(os.environ.get("QUALITY_OUT_DIR", str(ROOT / "artifacts/quality")))
    write_reports(summary, out_dir)

    baseline_path = Path(args.baseline)
    regressions: list[str] = []
    if args.write_baseline:
        baseline_path.write_text(
            json.dumps(
                {
                    "ts": summary["ts"],
                    "corpus": summary["corpus"],
                    "accuracy": summary["accuracy"],
                    "cases": {r["id"]: r["passed"] for r in results},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"baseline written → {baseline_path}")
    elif args.compare_baseline:
        if not baseline_path.is_file():
            print(f"!! no baseline at {baseline_path} — run --write-baseline first")
        else:
            prev = json.loads(baseline_path.read_text(encoding="utf-8")).get("cases") or {}
            regressions = [r["id"] for r in results if prev.get(r["id"]) and not r["passed"]]
            summary["regressions"] = regressions
            write_reports(summary, out_dir)
            if regressions:
                print(f"!! regressions vs baseline: {', '.join(regressions)}")

    print(
        f"\nEXECUTION ACCURACY {accuracy:.1%} ({passed_count}/{len(results)}) "
        f"threshold={threshold:.0%} passed={summary['passed']}"
    )
    print(f"reports → {out_dir}/quality-eval.json, quality-eval.md")
    if summary["broken_references"]:
        print(f"!! reference SQL failed for: {', '.join(summary['broken_references'])}")
    return 0 if (summary["passed"] and not regressions) else 1


if __name__ == "__main__":
    sys.exit(main())
