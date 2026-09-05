#!/usr/bin/env python3
"""Forecasting V1 chat acceptance runner (stdlib only, run on the BI server).

For each corpus case: POST /api/v1/bi/chat/stream, collect SSE phases + done payload,
check the expectation (done / declined:<code> / llm). Writes artifacts/forecast/chat-eval-<ts>.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_corpus(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)["cases"]
    except ImportError:
        # minimal YAML subset parser for this corpus shape
        cases, cur = [], None
        for line in text.splitlines():
            s = line.rstrip()
            if s.startswith("  - id:"):
                cur = {"id": s.split(":", 1)[1].strip()}
                cases.append(cur)
            elif cur is not None and s.startswith("    ") and ":" in s:
                k, v = s.strip().split(":", 1)
                v = v.strip().strip('"')
                if v.startswith("{"):
                    inner = v.strip("{} ")
                    dk, dv = inner.split(":", 1)
                    v = {dk.strip(): dv.strip().strip('"')}
                elif v.isdigit():
                    v = int(v)
                cur[k] = v
        return cases


def _stream(api: str, question: str, datasource: str, timeout: int) -> tuple[list[str], dict | None, dict | None]:
    body = json.dumps({"message": question, "db_name": datasource, "session_id": f"fc-eval-{int(time.time()*1000)}"}).encode()
    req = urllib.request.Request(f"{api}/api/v1/bi/chat/stream", data=body, headers={"Content-Type": "application/json"}, method="POST")
    phases: list[str] = []
    done = err = None
    ev = None
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                try:
                    d = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if ev == "status" and d.get("phase"):
                    phases.append(str(d["phase"]))
                elif ev == "done":
                    done = d
                elif ev == "error":
                    err = d
    return phases, done, err


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8790")
    ap.add_argument("--datasource", default="bi_reporting")
    ap.add_argument("--corpus", default=str(ROOT / "tests/text2sql/forecast-corpus.yaml"))
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--only", default=None)
    args = ap.parse_args()

    cases = _load_corpus(Path(args.corpus))
    results = []
    passed = 0
    for c in cases:
        if args.only and c["id"] not in args.only.split(","):
            continue
        t0 = time.time()
        try:
            phases, done, err = _stream(args.api, c["question"], args.datasource, args.timeout)
        except Exception as e:  # noqa: BLE001
            phases, done, err = [], None, {"message": f"{type(e).__name__}: {e}"}
        elapsed = round(time.time() - t0, 1)
        exp = c["expect"]
        llm_used = any(p in ("generating_sql", "plan_ready") for p in phases)
        forecast_phases = [p for p in phases if p.startswith("forecast_")]
        ok = False
        detail = ""
        if exp == "done":
            ok = (
                "forecast_done" in phases
                and not llm_used
                and bool(done)
                and done.get("intent") == "forecast"
                and done.get("sql_source") == "semantic_metric_compiler"
                and (not c.get("horizon") or (done.get("forecast") or {}).get("horizon") == c["horizon"])
                and (not c.get("dimension") or (done.get("forecast") or {}).get("dimension") == c["dimension"])
            )
            detail = f"engine={(done or {}).get('forecast', {}).get('engine')} phases={forecast_phases}"
        elif exp == "declined":
            ok = "forecast_declined" in phases and not llm_used and bool(done) and (done.get("forecast") or {}).get("code") == c.get("code")
            detail = f"code={(done or {}).get('forecast', {}).get('code')}"
        elif exp == "llm":
            ok = not forecast_phases
            detail = f"forecast_phases={forecast_phases}"
        passed += int(ok)
        results.append({"id": c["id"], "question": c["question"], "expect": exp, "ok": ok, "elapsed_s": elapsed, "phases": phases, "detail": detail, "error": err})
        print(f"{'PASS' if ok else 'FAIL'} {c['id']} ({elapsed}s) {detail}{(' ERR ' + str(err)) if err else ''}")

    out = ROOT / "artifacts/forecast" / f"chat-eval-{time.strftime('%Y%m%dT%H%M')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"passed": passed, "total": len(results), "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{passed}/{len(results)} passed → {out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
