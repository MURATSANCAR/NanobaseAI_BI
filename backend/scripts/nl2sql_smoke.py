#!/usr/bin/env python3
"""Faz-1 NL2SQL acceptance against bi_reporting via DB-GPT SSE chat."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASE = os.environ.get("DBGPT_BASE", "http://127.0.0.1:5670")
DB_NAME = os.environ.get("SMOKE_DB_NAME", "bi_reporting")
MODEL = os.environ.get("SMOKE_MODEL", "nanobase-qwen36-35b-a3b-mtp")
OUT_DIR = Path(os.environ.get("SMOKE_OUT_DIR", "/data/nanobaseai/bi/frontend/docs/architecture"))


@dataclass
class Case:
    id: str
    question: str
    expect_sql_contains: list[str]
    expect_reply_regex: str | None = None
    notes: str = ""


CASES: list[Case] = [
    Case(
        "q1_customer_count",
        "analytics şemasındaki customers tablosunda kaç müşteri var? Sadece sayıyı söyle.",
        ["select", "customer"],
        r"\b5\b",
    ),
    Case(
        "q2_revenue_by_segment",
        "Her müşteri segmenti için toplam gelir nedir? analytics.v_order_revenue veya order_items üzerinden hesapla.",
        ["select", "segment"],
        None,
        "Expect GROUP BY segment style SQL",
    ),
    Case(
        "q3_top_product",
        "En çok satılan ürün (quantity toplamı) hangisi?",
        ["select", "product"],
        None,
    ),
    Case(
        "q4_completed_orders",
        "status'u completed olan siparişlerin sayısını ver.",
        ["select", "completed"],
        r"\b[0-9]+\b",
    ),
    Case(
        "q5_ro_no_write",
        "customers tablosuna 'Hack Corp' adında yeni bir müşteri ekle.",
        [],
        None,
        "Must refuse or fail write; must NOT succeed silently",
    ),
]


def _stream_chat(base: str, question: str, conv_uid: str, timeout: int = 300) -> str:
    body = {
        "user_input": question,
        "conv_uid": conv_uid,
        "chat_mode": "chat_with_db_execute",
        "select_param": DB_NAME,
        "model_name": MODEL,
        "incremental": True,
        "temperature": 0.1,
        "max_new_tokens": 2048,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/chat/completions",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
    )
    last_content = ""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text.startswith("data:"):
                    continue
                payload = text[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                msg = choices[0].get("message") or choices[0].get("delta") or {}
                content = msg.get("content")
                if isinstance(content, str) and content:
                    # incremental=True sends cumulative content in this deployment
                    last_content = content
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"chat HTTP {e.code}: {raw[:800]}") from e
    return last_content


def _extract_sql(text: str) -> str | None:
    m = re.search(r"```sql\s*(.*?)```", text, re.I | re.S)
    if m:
        return m.group(1).strip()
    # DB-GPT often embeds JSON with sql field
    m = re.search(r'"sql"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if m:
        return bytes(m.group(1), "utf-8").decode("unicode_escape")
    m = re.search(r"(SELECT\b[\s\S]{8,1200}?;)", text, re.I)
    if m:
        return m.group(1).strip()
    return None


def evaluate(case: Case, reply: str, sql: str | None) -> tuple[bool, str]:
    low = (reply or "").lower()
    sql_l = (sql or "").lower()

    if case.id == "q5_ro_no_write":
        write_ok = any(
            x in low
            for x in (
                "insert into",
                "rows affected",
                "1 row",
                "eklendi",
                "successfully inserted",
            )
        )
        refuse = any(
            x in low
            for x in (
                "permission",
                "denied",
                "read-only",
                "readonly",
                "cannot",
                "yapamam",
                "izin",
                "error",
                "fail",
                "forbidden",
                "not allowed",
                "sadece select",
            )
        )
        if write_ok and not refuse:
            return False, "write appears to have succeeded"
        return True, "write refused or failed (expected)"

    hay = f"{sql_l}\n{low}"
    for token in case.expect_sql_contains:
        if token.lower() not in hay:
            return False, f"missing token '{token}' in sql/reply"

    if case.expect_reply_regex:
        if not re.search(case.expect_reply_regex, reply or "", re.I):
            return False, f"reply regex not matched: {case.expect_reply_regex}"

    if not (reply or "").strip():
        return False, "empty reply"
    return True, "ok"


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    results = []
    passed = 0

    for case in CASES:
        conv = f"smoke-{case.id}-{int(time.time() * 1000)}"
        t0 = time.time()
        err = None
        reply = ""
        sql = None
        try:
            reply = _stream_chat(base, case.question, conv)
            sql = _extract_sql(reply)
            ok, reason = evaluate(case, reply, sql)
        except Exception as e:
            ok, reason = False, str(e)
            err = str(e)
        elapsed = round(time.time() - t0, 2)
        if ok:
            passed += 1
        row = {
            "id": case.id,
            "question": case.question,
            "ok": ok,
            "reason": reason,
            "elapsed_s": elapsed,
            "sql": sql,
            "reply_excerpt": (reply or "")[:1500],
            "error": err,
            "notes": case.notes,
        }
        results.append(row)
        print(f"[{'PASS' if ok else 'FAIL'}] {case.id} ({elapsed}s) — {reason}")

    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "db": DB_NAME,
        "model": MODEL,
        "base": base,
        "passed": passed,
        "total": len(CASES),
        "pass_rate": round(passed / max(len(CASES), 1), 3),
        "results": results,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "phase-1-smoke.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = OUT_DIR / "phase-1-results.md"
    lines = [
        "# Faz 1 — NL2SQL kabul sonuçları",
        "",
        f"- Zaman: `{summary['ts']}`",
        f"- DB-GPT: `{base}`",
        f"- Model: `{MODEL}`",
        f"- Datasource: `{DB_NAME}` (RO / analytics)",
        f"- Sonuç: **{passed}/{len(CASES)}** geçti (oran {summary['pass_rate']})",
        "",
        "| Case | Sonuç | Süre | Not |",
        "|------|-------|------|-----|",
    ]
    for r in results:
        lines.append(
            f"| `{r['id']}` | {'PASS' if r['ok'] else 'FAIL'} | {r['elapsed_s']}s | {r['reason']} |"
        )
    lines.extend(["", "## Detay", ""])
    for r in results:
        lines.append(f"### {r['id']}")
        lines.append(f"- Soru: {r['question']}")
        lines.append(f"- SQL: `{r.get('sql') or '—'}`")
        lines.append("- Yanıt (özet):")
        lines.append("")
        lines.append("```")
        lines.append((r.get("reply_excerpt") or "")[:900])
        lines.append("```")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    # Accept ≥4/5 for Faz-1 gate (RO denial + core NL2SQL)
    if passed < 4:
        sys.exit(1)


if __name__ == "__main__":
    main()
