#!/usr/bin/env python3
"""Run 20-question Text2SQL smoke suite (retrieval + nanobase nl2sql-plan)."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


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


def load_suite() -> dict[str, Any]:
    path = HERE / "smoke-questions.yaml"
    if yaml is None:
        raise SystemExit("PyYAML required: pip install pyyaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def embed_key() -> str:
    preferred = ("BI_EMBED_API_KEY", "EMBEDDING_API_KEY", "CONTRACT_API_KEY")
    for k in preferred:
        if os.environ.get(k):
            return os.environ[k].strip()
    for env in (
        ROOT / "backend/.env",
        Path("/data/nanobaseai/bi/frontend/backend/.env"),
    ):
        if not env.is_file():
            continue
        parsed: dict[str, str] = {}
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.strip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            parsed[k.strip()] = v.strip().strip('"').strip("'")
        for k in preferred:
            if parsed.get(k):
                return parsed[k]
    raise SystemExit("BI_EMBED_API_KEY missing")


def retrieve(question: str, collection: str, api_key: str, top_k: int = 6) -> list[dict[str, Any]]:
    embed_url = os.environ.get("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings")
    qdrant = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
    emb = _http_json("POST", embed_url, {"texts": [question]}, headers={"Authorization": f"Bearer {api_key}"})
    vecs = emb.get("embeddings") or []
    if not vecs:
        raise RuntimeError("empty embedding")
    res = _http_json(
        "POST",
        f"{qdrant}/collections/{collection}/points/search",
        {"vector": vecs[0], "limit": top_k, "with_payload": True},
    )
    return list(res.get("result") or [])


def plan_sql(question: str, datasource: str) -> str | None:
    api = os.environ.get("NANOBASE_API_BASE", "http://127.0.0.1:8790").rstrip("/")
    plan = _http_json(
        "POST",
        f"{api}/api/v1/bi/workflows/nl2sql-plan",
        {"question": question, "datasource_id": datasource},
        timeout=180,
    )
    if plan.get("error"):
        raise RuntimeError(str(plan["error"])[:300])
    return plan.get("sql")


def main() -> int:
    suite = load_suite()
    datasource = suite.get("datasource") or "bi_reporting"
    collection = suite.get("collection") or f"bi_schema_{datasource}"
    threshold = float(suite.get("pass_threshold") or 0.80)
    run_sql = os.environ.get("PHASE2_RUN_NL2SQL", "1") == "1"
    api_key = embed_key()

    results = []
    ret_pass = sql_pass = sql_run = 0
    for q in suite.get("questions") or []:
        t0 = time.time()
        hits = retrieve(q["question"], collection, api_key)
        found = set()
        for h in hits:
            p = h.get("payload") or {}
            t = str(p.get("table") or p.get("table_name") or "").lower()
            if t:
                found.add(t)
                found.add(t.split(".")[-1])
        expect = [str(x).lower() for x in (q.get("expect_tables") or [])]
        ok_ret = all(t in found for t in expect)
        if ok_ret:
            ret_pass += 1

        sql = None
        ok_sql = None
        err = None
        if run_sql:
            sql_run += 1
            try:
                sql = plan_sql(q["question"], datasource)
                hay = (sql or "").lower()
                tokens = [str(t).lower() for t in (q.get("expect_sql_tokens") or [])]
                ok_sql = "select" in hay and sum(1 for t in tokens if t in hay) >= max(1, len(tokens) // 2)
                if ok_sql:
                    sql_pass += 1
            except Exception as e:
                ok_sql = False
                err = str(e)[:300]

        score = (0.5 if ok_ret else 0.0) + ((0.5 if ok_sql else 0.0) if run_sql else (0.5 if ok_ret else 0.0))
        if not run_sql:
            score = 1.0 if ok_ret else 0.0
        results.append(
            {
                "id": q["id"],
                "question": q["question"],
                "retrieval_ok": ok_ret,
                "found_tables": sorted(found),
                "expect_tables": expect,
                "sql_ok": ok_sql,
                "sql": sql,
                "score": score,
                "elapsed_s": round(time.time() - t0, 2),
                "error": err,
            }
        )
        print(
            f"[{'PASS' if score >= 0.5 else 'FAIL'}] {q['id']} "
            f"ret={'Y' if ok_ret else 'N'} sql={ok_sql} score={score:.2f}"
        )

    overall = sum(r["score"] for r in results) / max(len(results), 1)
    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "collection": collection,
        "retrieval_pass": f"{ret_pass}/{len(results)}",
        "sql_pass": f"{sql_pass}/{sql_run}" if run_sql else "skipped",
        "overall_score": round(overall, 3),
        "pass_threshold": threshold,
        "passed": overall >= threshold,
        "results": results,
    }

    out_dir = Path(os.environ.get("PHASE2_OUT_DIR", str(ROOT / "docs/architecture")))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "phase-2-quality.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# Faz 2 — Şema indeksi + kalite",
        "",
        f"- Zaman: `{summary['ts']}`",
        f"- Collection: `{collection}`",
        f"- Retrieval: **{summary['retrieval_pass']}**",
        f"- NL2SQL: **{summary['sql_pass']}**",
        f"- Overall: **{summary['overall_score']}** (eş {threshold}) → "
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
    (out_dir / "phase-2-results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if "--write-expected" in sys.argv:
        exp = {
            "datasource": datasource,
            "ts": summary["ts"],
            "overall_score": summary["overall_score"],
            "results": [
                {"id": r["id"], "found_tables": r["found_tables"], "sql_ok": r["sql_ok"]}
                for r in results
            ],
        }
        (HERE / "expected-results.yaml").write_text(
            yaml.dump(exp, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    print(f"OVERALL {overall:.3f} passed={summary['passed']}")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
