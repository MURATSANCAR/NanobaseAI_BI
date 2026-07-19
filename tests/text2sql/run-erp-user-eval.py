#!/usr/bin/env python3
"""Run 50 ERP chat questions on-server like a real user; persist full transcripts."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cur_event = "message"
    data_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("event:"):
            cur_event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line.strip() == "":
            if data_lines:
                payload = "\n".join(data_lines)
                try:
                    data = json.loads(payload)
                except Exception:
                    data = {"raw": payload[:2000]}
                events.append({"event": cur_event, "data": data})
            cur_event = "message"
            data_lines = []
    if data_lines:
        payload = "\n".join(data_lines)
        try:
            data = json.loads(payload)
        except Exception:
            data = {"raw": payload[:2000]}
        events.append({"event": cur_event, "data": data})
    return events


def chat_stream(
    *,
    base: str,
    message: str,
    session_id: str,
    db_name: str,
    timeout: int = 240,
) -> tuple[list[dict[str, Any]], float, str | None]:
    url = f"{base.rstrip('/')}/api/v1/bi/chat/stream"
    body = json.dumps(
        {"message": message, "session_id": session_id, "db_name": db_name},
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    t0 = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return _parse_sse(raw), time.perf_counter() - t0, None
    except error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return [], time.perf_counter() - t0, f"HTTP {e.code}: {raw[:800]}"
    except Exception as e:
        return [], time.perf_counter() - t0, str(e)[:800]


def summarize_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    sql = None
    sql_source = None
    answer = None
    error = None
    clarification = None
    phases: list[str] = []
    repaired = False
    row_count = None
    truncated = None
    done_payload: dict[str, Any] = {}

    for ev in events:
        name = ev.get("event")
        data = ev.get("data") or {}
        if name == "status":
            ph = data.get("phase")
            if ph:
                phases.append(str(ph))
            if data.get("sql") and not sql:
                sql = data.get("sql")
        if name in ("message", "result", "answer", "delta"):
            if isinstance(data, dict):
                if data.get("type") == "SQL_GENERATED":
                    sql = (data.get("payload") or {}).get("sql") or sql
                    sql_source = (data.get("payload") or {}).get("sql_source") or sql_source
                if data.get("type") == "CLARIFICATION_REQUIRED":
                    clarification = (data.get("payload") or {}).get("question") or data.get("message")
                if data.get("answer"):
                    answer = data.get("answer")
                if data.get("type") == "ANSWER" or data.get("type") == "RESULT_EXPLAINED":
                    answer = (data.get("payload") or {}).get("answer") or answer
        if name == "error":
            error = data.get("message") or data.get("error") or str(data)[:400]
        if name == "done":
            done_payload = data if isinstance(data, dict) else {"raw": data}
            sql = data.get("sql") or sql
            answer = (
                data.get("reply")
                or data.get("answer")
                or data.get("explanation")
                or answer
            )
            qr = data.get("query_result") or data.get("result") or {}
            if isinstance(qr, dict):
                rows = qr.get("rows") or []
                row_count = qr.get("rowCount") or qr.get("row_count") or len(rows)
                truncated = qr.get("truncated")
            if data.get("clarification"):
                clarification = clarification or data.get("clarificationQuestion")
            sql_source = data.get("sql_source") or sql_source
            if data.get("sql_error"):
                error = error or str(data.get("sql_error"))[:400]
        if name == "completed":
            pass
        # repair markers
        blob = json.dumps(data, ensure_ascii=False)
        if "REPAIRING" in blob or "SQL_REPAIRED" in blob or '"repair"' in blob:
            repaired = True
        if data.get("type") == "SQL_GENERATED" and (data.get("payload") or {}).get("sql_source") == "repair":
            repaired = True
            sql = (data.get("payload") or {}).get("sql") or sql

    # deeper scan for answer/sql in any event
    for ev in events:
        data = ev.get("data") or {}
        if not isinstance(data, dict):
            continue
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        if payload.get("sql"):
            sql = sql or payload.get("sql")
        if payload.get("answer"):
            answer = answer or payload.get("answer")
        if data.get("sql"):
            sql = sql or data.get("sql")
        if data.get("answer"):
            answer = answer or data.get("answer")
        if data.get("type") == "ANSWER_READY":
            answer = answer or payload.get("text") or payload.get("answer")

    ok = error is None and (bool(sql) or bool(clarification) or bool(answer))
    if done_payload.get("ok") is False:
        ok = False
    if error:
        ok = False

    return {
        "ok": ok,
        "sql": sql,
        "sql_source": sql_source,
        "answer": answer,
        "error": error,
        "clarification": clarification,
        "phases": phases,
        "repaired": repaired,
        "row_count": row_count,
        "truncated": truncated,
        "done_keys": sorted(done_payload.keys()) if done_payload else [],
    }


def load_suite() -> dict[str, Any]:
    path = HERE / "erp-user-50.yaml"
    if yaml is None:
        raise SystemExit("PyYAML required")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def main() -> int:
    suite = load_suite()
    ds = os.environ.get("ERP_EVAL_DS", suite.get("datasource") or "erp")
    base = os.environ.get("NANOBASE_API_BASE", "http://127.0.0.1:8790")
    session_id = os.environ.get("ERP_EVAL_SESSION") or f"erp-user-eval-{uuid.uuid4().hex[:12]}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(
        os.environ.get(
            "ERP_EVAL_OUT",
            str(ROOT / "artifacts" / "phase-6" / f"erp-user-eval-{stamp}"),
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "events").mkdir(exist_ok=True)

    questions = suite.get("questions") or []
    results: list[dict[str, Any]] = []
    meta = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "datasource": ds,
        "session_id": session_id,
        "api_base": base,
        "question_count": len(questions),
        "host": os.uname().nodename if hasattr(os, "uname") else "",
        "note": "Simulated last-user chat on ERP via /api/v1/bi/chat/stream",
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[erp-eval] session={session_id} ds={ds} n={len(questions)} out={out_dir}", flush=True)

    for i, q in enumerate(questions, 1):
        qid = q.get("id") or f"q{i:02d}"
        question = str(q.get("question") or "").strip()
        difficulty = q.get("difficulty") or ""
        print(f"[{i:02d}/{len(questions)}] {qid} ({difficulty}) {question[:80]}", flush=True)
        events, elapsed, err = chat_stream(
            base=base, message=question, session_id=session_id, db_name=ds
        )
        summary = summarize_events(events)
        if err:
            summary["ok"] = False
            summary["error"] = err

        record = {
            "id": qid,
            "index": i,
            "difficulty": difficulty,
            "question": question,
            "elapsed_sec": round(elapsed, 2),
            **summary,
            "event_count": len(events),
            "event_names": [e.get("event") for e in events],
        }
        results.append(record)
        (out_dir / "events" / f"{qid}.json").write_text(
            json.dumps({"question": question, "events": events, "summary": summary}, indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        # incremental save
        (out_dir / "results.json").write_text(
            json.dumps({"meta": meta, "results": results}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        status = "OK" if summary.get("ok") else "FAIL"
        print(
            f"         → {status} {elapsed:.1f}s sql={'yes' if summary.get('sql') else 'no'} "
            f"answer={'yes' if summary.get('answer') else 'no'} err={str(summary.get('error') or '')[:80]}",
            flush=True,
        )
        # gentle pacing so we don't stampede LLM
        time.sleep(float(os.environ.get("ERP_EVAL_SLEEP", "0.4")))

    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    ok_n = sum(1 for r in results if r.get("ok"))
    fail_n = len(results) - ok_n
    by_diff: dict[str, dict[str, int]] = {}
    for r in results:
        d = r.get("difficulty") or "unknown"
        by_diff.setdefault(d, {"ok": 0, "fail": 0, "n": 0})
        by_diff[d]["n"] += 1
        if r.get("ok"):
            by_diff[d]["ok"] += 1
        else:
            by_diff[d]["fail"] += 1

    summary_doc = {
        "meta": meta,
        "totals": {
            "n": len(results),
            "ok": ok_n,
            "fail": fail_n,
            "pass_rate": round(ok_n / len(results), 3) if results else 0,
            "avg_elapsed_sec": round(sum(r.get("elapsed_sec") or 0 for r in results) / max(len(results), 1), 2),
            "repaired": sum(1 for r in results if r.get("repaired")),
            "clarifications": sum(1 for r in results if r.get("clarification")),
        },
        "by_difficulty": by_diff,
        "failures": [
            {
                "id": r["id"],
                "difficulty": r.get("difficulty"),
                "question": r["question"],
                "error": r.get("error"),
                "clarification": r.get("clarification"),
            }
            for r in results
            if not r.get("ok")
        ],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "results.json").write_text(
        json.dumps({"meta": meta, "summary": summary_doc["totals"], "results": results}, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    # markdown preview for joint review
    lines = [
        f"# ERP user eval — {stamp}",
        "",
        f"- datasource: `{ds}`",
        f"- session: `{session_id}`",
        f"- pass: **{ok_n}/{len(results)}** ({summary_doc['totals']['pass_rate']})",
        f"- avg latency: {summary_doc['totals']['avg_elapsed_sec']}s",
        f"- repaired: {summary_doc['totals']['repaired']}",
        "",
        "| # | id | diff | ok | sec | sql | answer/error |",
        "|---|----|------|----|-----|-----|--------------|",
    ]
    for r in results:
        ans = (r.get("answer") or r.get("error") or r.get("clarification") or "")[:80].replace("|", "/")
        sql_flag = "Y" if r.get("sql") else "N"
        lines.append(
            f"| {r['index']} | {r['id']} | {r.get('difficulty')} | "
            f"{'✓' if r.get('ok') else '✗'} | {r.get('elapsed_sec')} | {sql_flag} | {ans} |"
        )
    lines.append("")
    lines.append("## Failures")
    for f in summary_doc["failures"]:
        lines.append(f"- **{f['id']}** ({f.get('difficulty')}): {f['question']}")
        lines.append(f"  - error: `{f.get('error')}`")
    (out_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[erp-eval] DONE ok={ok_n}/{len(results)} → {out_dir}", flush=True)
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
