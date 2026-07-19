#!/usr/bin/env python3
"""Faz 2: 20-question schema retrieval + NL2SQL quality gate.

Pass rule: overall score >= 0.80 (retrieval hit-rate weighted with SQL validity).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("NANOBASE_ROOT", "/data/nanobaseai/bi/frontend"))
OUT_DIR = Path(os.environ.get("PHASE2_OUT_DIR", str(ROOT / "docs/architecture")))
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
COLLECTION = os.environ.get("BI_SCHEMA_COLLECTION", "bi_schema_bi_reporting")
EMBED_URL = os.environ.get("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings")
API_BASE = os.environ.get("NANOBASE_API_BASE", "http://127.0.0.1:8790").rstrip("/")
DB_NAME = os.environ.get("SMOKE_DB_NAME", "bi_reporting")
PASS_THRESHOLD = float(os.environ.get("PHASE2_PASS_THRESHOLD", "0.80"))
TOP_K = int(os.environ.get("PHASE2_TOP_K", "6"))
RUN_NL2SQL = os.environ.get("PHASE2_RUN_NL2SQL", "1") == "1"


@dataclass
class Q:
    id: str
    question: str
    expect_tables: list[str]
    expect_sql_tokens: list[str]


QUESTIONS: list[Q] = [
    Q("q01", "Kaç müşteri var?", ["customers"], ["select", "count", "customer"]),
    Q("q02", "Enterprise segmentindeki müşterileri listele", ["customers"], ["select", "segment", "enterprise"]),
    Q("q03", "Almanya'daki müşteri sayısı", ["customers"], ["select", "country", "de"]),
    Q("q04", "Ürün kategorilerine göre ürün sayısı", ["products"], ["select", "category", "count"]),
    Q("q05", "En pahalı ürün hangisi?", ["products"], ["select", "unit_price", "order"]),
    Q("q06", "SKU-100 ürününün adı nedir?", ["products"], ["select", "sku"]),
    Q("q07", "Completed sipariş sayısı", ["orders"], ["select", "completed", "count"]),
    Q("q08", "2026 yılı siparişlerini getir", ["orders"], ["select", "order_date"]),
    Q("q09", "Pending siparişleri olan müşteriler", ["orders", "customers"], ["select", "pending"]),
    Q("q10", "Her siparişin toplam tutarı (order_items)", ["order_items", "orders"], ["select", "quantity", "unit_price"]),
    Q("q11", "En çok satılan ürün (adet)", ["order_items", "products"], ["select", "sum", "quantity"]),
    Q("q12", "Segment bazında toplam gelir", ["v_order_revenue", "customers"], ["select", "segment"]),
    Q("q13", "v_order_revenue üzerinden ülke bazında ciro", ["v_order_revenue"], ["select", "country", "revenue"]),
    Q("q14", "Acme Holding'in sipariş sayısı", ["customers", "orders"], ["select", "acme"]),
    Q("q15", "Services kategorisindeki ürünler", ["products"], ["select", "services", "category"]),
    Q("q16", "İptal edilen siparişler", ["orders"], ["select", "cancelled"]),
    Q("q17", "2026 yılındaki toplam fatura tutarı", ["invoices"], ["select", "sum", "invoice"]),
    Q("q18", "Ödenmemiş faturaların kalan tutarı", ["invoices"], ["select", "remaining", "sum"]),
    Q("q19", "Ankara'daki müşterilere ait gecikmiş faturalar", ["invoices", "customers"], ["select", "ankara", "overdue"]),
    Q("q20", "İptal edilmiş faturaları hariç tutarak toplam tutar", ["invoices"], ["select", "cancelled", "sum"]),
]


def _http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: int = 180) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw[:500]}") from e


def _embed_key() -> str:
    preferred = ("BI_EMBED_API_KEY", "EMBEDDING_API_KEY", "CONTRACT_API_KEY")
    for k in preferred:
        if os.environ.get(k):
            return os.environ[k].strip()
    parsed: dict[str, str] = {}
    for env in (ROOT / "backend/.env", ROOT / "backend/nanobase_api.env", ROOT / "backend/contract.env"):
        if not env.is_file():
            continue
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            parsed[k.strip()] = v.strip().strip('"').strip("'")
    for k in preferred:
        if parsed.get(k):
            return parsed[k]
    raise RuntimeError("BI_EMBED_API_KEY not found")


def embed_one(text: str, api_key: str) -> list[float]:
    res = _http_json("POST", EMBED_URL, {"texts": [text]}, headers={"Authorization": f"Bearer {api_key}"})
    vectors = res.get("embeddings") or []
    if not vectors:
        raise RuntimeError("empty embedding")
    return vectors[0]


def retrieve(question: str, api_key: str) -> list[dict[str, Any]]:
    vec = embed_one(question, api_key)
    res = _http_json(
        "POST",
        f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
        {
            "vector": vec,
            "limit": TOP_K,
            "with_payload": True,
        },
    )
    return list(res.get("result") or [])


def retrieval_hit(q: Q, hits: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    tables = set()
    for h in hits:
        p = h.get("payload") or {}
        if p.get("table"):
            # payload may be "customers" or "analytics.customers"
            raw = str(p["table"]).lower()
            tables.add(raw)
            tables.add(raw.split(".")[-1])
    missing = [t for t in q.expect_tables if t.lower() not in tables]
    return (len(missing) == 0, sorted(tables))


def plan_nl2sql(question: str) -> tuple[str | None, str]:
    """Nanobase nl2sql-plan (no customer SQL execute — Gateway path)."""
    plan = _http_json(
        "POST",
        f"{API_BASE}/api/v1/bi/workflows/nl2sql-plan",
        {"question": question, "datasource_id": DB_NAME},
        timeout=180,
    )
    if plan.get("error"):
        raise RuntimeError(str(plan["error"])[:300])
    sql = plan.get("sql") or plan.get("executed_sql")
    reply = json.dumps(plan, ensure_ascii=False)
    return (str(sql) if sql else None, reply)


def sql_ok(q: Q, sql: str | None, reply: str) -> bool:
    hay = f"{(sql or '').lower()}\n{reply.lower()}"
    if "select" not in hay:
        return False
    hits = sum(1 for t in q.expect_sql_tokens if t.lower() in hay)
    return hits >= max(1, len(q.expect_sql_tokens) // 2)


def main() -> None:
    api_key = _embed_key()
    results = []
    ret_pass = 0
    sql_pass = 0
    sql_run = 0

    for q in QUESTIONS:
        t0 = time.time()
        hits = retrieve(q.question, api_key)
        ok_ret, found_tables = retrieval_hit(q, hits)
        if ok_ret:
            ret_pass += 1

        sql = None
        reply = ""
        ok_sql = None
        err = None
        if RUN_NL2SQL:
            sql_run += 1
            try:
                sql, reply = plan_nl2sql(q.question)
                ok_sql = sql_ok(q, sql, reply)
                if ok_sql:
                    sql_pass += 1
            except Exception as e:
                ok_sql = False
                err = str(e)[:300]

        # per-question score: retrieval 0.5 + sql 0.5 (or retrieval only if NL2SQL off)
        if RUN_NL2SQL:
            score = (1.0 if ok_ret else 0.0) * 0.5 + (1.0 if ok_sql else 0.0) * 0.5
        else:
            score = 1.0 if ok_ret else 0.0

        results.append(
            {
                "id": q.id,
                "question": q.question,
                "retrieval_ok": ok_ret,
                "found_tables": found_tables,
                "expect_tables": q.expect_tables,
                "sql_ok": ok_sql,
                "sql": sql,
                "score": score,
                "elapsed_s": round(time.time() - t0, 2),
                "error": err,
                "top_hit": ((hits[0].get("payload") or {}).get("text") if hits else None),
            }
        )
        print(
            f"[{'PASS' if score >= 0.5 else 'FAIL'}] {q.id} "
            f"ret={'Y' if ok_ret else 'N'} sql={ok_sql} score={score:.2f} ({results[-1]['elapsed_s']}s)"
        )

    overall = sum(r["score"] for r in results) / max(len(results), 1)
    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "collection": COLLECTION,
        "api_base": API_BASE,
        "nl2sql_path": "nanobase_api /workflows/nl2sql-plan",
        "top_k": TOP_K,
        "nl2sql": RUN_NL2SQL,
        "retrieval_pass": f"{ret_pass}/{len(QUESTIONS)}",
        "sql_pass": f"{sql_pass}/{sql_run}" if RUN_NL2SQL else "skipped",
        "overall_score": round(overall, 3),
        "pass_threshold": PASS_THRESHOLD,
        "passed": overall >= PASS_THRESHOLD,
        "results": results,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "phase-2-quality.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = OUT_DIR / "phase-2-results.md"
    lines = [
        "# Faz 2 — Şema indeksi + kalite",
        "",
        f"- Zaman: `{summary['ts']}`",
        f"- Collection: `{COLLECTION}`",
        f"- Retrieval: **{summary['retrieval_pass']}**",
        f"- NL2SQL: **{summary['sql_pass']}**",
        f"- Overall: **{summary['overall_score']}** (eş {PASS_THRESHOLD}) → "
        f"{'PASS' if summary['passed'] else 'FAIL'}",
        "",
        "| ID | Ret | SQL | Score | Soru |",
        "|----|-----|-----|-------|------|",
    ]
    for r in results:
        lines.append(
            f"| `{r['id']}` | {'Y' if r['retrieval_ok'] else 'N'} | "
            f"{r['sql_ok']} | {r['score']:.2f} | {r['question']} |"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"OVERALL {overall:.3f} passed={summary['passed']}")
    if not summary["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
