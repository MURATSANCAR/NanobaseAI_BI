#!/usr/bin/env python3
"""Mid-complex ERP chat smoke: 5 multi-join prompts (not the full 10-prompt suite).

Reuses the same chat/stream + model-queue gate as erp-complex-chat-smoke.py.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any

import httpx

API = "http://127.0.0.1:8790/api/v1/bi/chat/stream"
QUEUE_STATUS = "http://127.0.0.1:8790/api/v1/bi/model-queue/status"
DATASOURCE = "erp"
TIMEOUT_S = 360.0
HARD_TIMEOUT_S = 720.0
QUEUE_IDLE_POLL_S = 2.0
QUEUE_IDLE_MAX_WAIT_S = 480.0
BETWEEN_PROMPTS_PAUSE_S = 1.0
OUT_JSON = "/tmp/erp-mid-complex-chat-smoke.json"
OUT_LOG = "/tmp/erp-mid-complex-chat-smoke.log"

# Complex enough (joins + filters + aggregates), not monster multi-part questions.
PROMPTS: list[dict[str, str]] = [
    {
        "id": "M01",
        "title": "Budget vs AP OPEX usage",
        "message": (
            "2026 mali yılı için butce_planlari ile alis_faturalari'yı butce_kodu üzerinden eşleştir. "
            "Her bütçe kalemi için planlanan_tutar, 2026 yılı fatura genel_toplam toplamı, fark ve "
            "kullanım yüzdesi hesapla. Sadece OPEX kalemleri; kullanım > 80 olanları önce göster. "
            "Departman kodu ve kalem adını da yaz."
        ),
    },
    {
        "id": "M02",
        "title": "Product category margin top 8",
        "message": (
            "Son 12 aydaki satış fatura kalemlerinden ürün bazında ciro üret; urunler, "
            "urun_kategorileri ve markalar ile birleştir. Kategori cirosuna göre top 8 ve "
            "kaba brüt marj ((birim_fiyat - alis_fiyat)*miktar) hesapla. İptal faturalarını hariç tut."
        ),
    },
    {
        "id": "M03",
        "title": "Branch sales per headcount",
        "message": (
            "Şube bazında 2026 fatura cirosu, satış sipariş sayısı ve aktif personel ile "
            "kişi başı ciro. En düşük ve en yüksek 5 şube."
        ),
    },
    {
        "id": "M04",
        "title": "Price list leakage top 20",
        "message": (
            "2026'da fatura_kalemleri birim fiyatı, fiyat_listesi_kalemleri liste fiyatının "
            "%10 altındaysa iskonto kaybını hesapla; en çok kayıp üreten 20 satır ve ürün toplamı."
        ),
    },
    {
        "id": "M05",
        "title": "Customer concentration + limit",
        "message": (
            "2026 satış faturalarında müşteri ciro payı top 10; top 5'in toplam payı. "
            "Açık bakiye (fatura-tahsilat) ile musteriler.risk_limit kıyası; limiti aşanlar. "
            "İl bazında 2026 ciro dağılımı."
        ),
    },
]


def _extract_sql(data: dict[str, Any]) -> str | None:
    for key in ("sql", "executed_sql", "final_sql"):
        v = data.get(key)
        if isinstance(v, str) and len(v.strip()) > 10:
            return v
    plan = data.get("plan")
    if isinstance(plan, dict):
        v = plan.get("sql")
        if isinstance(v, str) and len(v.strip()) > 10:
            return v
    for block in data.get("answer_blocks") or []:
        if isinstance(block, dict) and isinstance(block.get("sql"), str) and len(block["sql"]) > 10:
            return block["sql"]
    return None


def _score(events: list[tuple[str, dict[str, Any]]], wall_err: str | None) -> dict[str, Any]:
    phases = [e.get("phase") for _, e in events if e.get("phase")]
    sql = None
    sql_error = None
    row_count = None
    reply_snip = None
    tables = None
    conf = None
    final_error = wall_err
    executed = False
    repaired = False
    shape_guard = False

    for ev, data in events:
        if ev == "error" or data.get("type") == "ERROR":
            final_error = str(data.get("message") or data.get("error") or data)[:500]
        ph = data.get("phase")
        if ph == "schema_retrieval_done":
            tables = data.get("tables")
        if ph == "sql_repaired":
            repaired = True
        if ph == "sql_shape_guard":
            shape_guard = True
        found = _extract_sql(data)
        if found:
            sql = found
        if data.get("sql_error"):
            sql_error = str(data["sql_error"])[:500]
        qr = data.get("query_result")
        if isinstance(qr, dict):
            row_count = len(qr.get("rows") or [])
            executed = True
        if data.get("row_count") is not None:
            try:
                row_count = int(data["row_count"])
            except Exception:
                pass
        if data.get("reply"):
            reply_snip = str(data["reply"])[:300]
        prov = data.get("provenance")
        if isinstance(prov, dict):
            conf = prov.get("confidence")
            if prov.get("executed"):
                executed = True
        if isinstance(data.get("error"), str) and data.get("ok") is False:
            final_error = str(data["error"])[:500]

    gaps: list[str] = []
    if final_error and not sql:
        gaps.append("stream_error")
    if not sql:
        gaps.append("no_sql")
    if sql_error:
        gaps.append("sql_error")
    if sql and not executed and not sql_error:
        gaps.append("sql_not_executed")
    if tables is not None and len(tables) == 0:
        gaps.append("empty_schema_retrieval")

    hard_fail = ("no_sql" in gaps) or ("sql_error" in gaps) or (bool(final_error) and not sql)
    return {
        "gaps": gaps,
        "hard_fail": hard_fail,
        "phases": phases,
        "tables_retrieved": (tables or [])[:14],
        "sql": (sql or "")[:2500],
        "sql_error": sql_error,
        "row_count": row_count,
        "executed": executed,
        "repaired": repaired,
        "shape_guard": shape_guard,
        "confidence": conf,
        "reply_snip": reply_snip,
        "error": final_error,
        "event_count": len(events),
        "event_names": [ev for ev, _ in events],
    }


def wait_model_queue_idle(*, label: str = "") -> dict[str, Any]:
    t0 = time.time()
    last: dict[str, Any] = {}
    while time.time() - t0 < QUEUE_IDLE_MAX_WAIT_S:
        try:
            with httpx.Client(timeout=10.0) as c:
                r = c.get(QUEUE_STATUS)
                r.raise_for_status()
                last = r.json()
        except Exception as e:  # noqa: BLE001
            last = {"ok": False, "error": str(e), "active": -1, "waiting": -1}
            time.sleep(QUEUE_IDLE_POLL_S)
            continue
        active = int(last.get("active") or 0)
        waiting = int(last.get("waiting") or 0)
        if active == 0 and waiting == 0:
            elapsed = round(time.time() - t0, 1)
            if label:
                print(f"  queue idle ({elapsed}s wait) — {label}", flush=True)
            return last
        print(
            f"  waiting model queue idle… active={active} waiting={waiting} [{label}]",
            flush=True,
        )
        time.sleep(QUEUE_IDLE_POLL_S)
    print(
        f"  WARN: model queue still busy after {QUEUE_IDLE_MAX_WAIT_S}s — proceeding",
        flush=True,
    )
    return last


def run_one(prompt: dict[str, str]) -> dict[str, Any]:
    body = {
        "message": prompt["message"],
        "db_name": DATASOURCE,
        "session_id": f"erp-mid-{prompt['id']}-{int(time.time())}",
    }
    t0 = time.time()
    events: list[tuple[str, dict[str, Any]]] = []
    wall_err: str | None = None
    terminal = False
    event_name = "message"
    data_buf: list[str] = []
    soft_warned = False

    try:
        with httpx.Client(timeout=httpx.Timeout(HARD_TIMEOUT_S + 30.0, connect=30.0)) as client:
            with client.stream(
                "POST",
                API,
                json=body,
                headers={"Accept": "text/event-stream"},
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    elapsed = time.time() - t0
                    if elapsed > TIMEOUT_S and not soft_warned:
                        soft_warned = True
                        print(
                            f"  … soft budget {TIMEOUT_S}s exceeded, hard cap {HARD_TIMEOUT_S}s",
                            flush=True,
                        )
                    if elapsed > HARD_TIMEOUT_S:
                        wall_err = f"TimeoutError: hard wall > {HARD_TIMEOUT_S}s"
                        break
                    if line.startswith("event:"):
                        event_name = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data_buf.append(line.split(":", 1)[1].strip())
                    elif line == "":
                        if not data_buf:
                            continue
                        blob = "\n".join(data_buf)
                        data_buf = []
                        try:
                            payload = json.loads(blob)
                        except json.JSONDecodeError:
                            payload = {"raw": blob[:400]}
                        if isinstance(payload, dict):
                            events.append((event_name, payload))
                            ph = payload.get("phase")
                            if ph:
                                print(f"  phase={ph}", flush=True)
                        if event_name in {"done", "error"}:
                            terminal = True
                            break
                        event_name = "message"
    except Exception as exc:  # noqa: BLE001
        wall_err = f"{type(exc).__name__}: {exc}"[:500]

    if not terminal and not wall_err:
        wall_err = "IncompleteStream: connection closed without done/error"

    elapsed = round(time.time() - t0, 2)
    scored = _score(events, wall_err)
    scored["terminal"] = terminal
    scored["gaps"] = list(scored.get("gaps") or [])
    if not terminal:
        scored["gaps"].append("no_terminal_sse")
        scored["hard_fail"] = True
    return {
        "id": prompt["id"],
        "title": prompt["title"],
        "elapsed_s": elapsed,
        "ok": bool(terminal) and not scored["hard_fail"],
        **scored,
    }


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []
    print(f"# ERP mid-complex chat smoke — {started} — ds={DATASOURCE}", flush=True)
    print(
        f"# gate: terminal SSE + queue idle (soft={TIMEOUT_S}s hard={HARD_TIMEOUT_S}s)",
        flush=True,
    )

    wait_model_queue_idle(label="before M01")

    for i, p in enumerate(PROMPTS, 1):
        print(f"\n== [{i}/{len(PROMPTS)}] {p['id']} {p['title']} ==", flush=True)
        print(f"Q: {p['message'][:180]}", flush=True)
        print("  POST chat/stream…", flush=True)
        r = run_one(p)
        results.append(r)
        status = "FAIL" if r["hard_fail"] else ("WARN" if r["gaps"] else "PASS")
        print(
            f"→ {status} {r['elapsed_s']}s terminal={'Y' if r.get('terminal') else 'N'} "
            f"exec={r['executed']} rows={r['row_count']} repaired={r.get('repaired')} "
            f"gaps={r['gaps']}",
            flush=True,
        )
        if r.get("tables_retrieved"):
            print(f"SCHEMA: {r['tables_retrieved'][:8]}", flush=True)
        if r.get("sql"):
            print(f"SQL: {r['sql'][:420].replace(chr(10), ' ')}", flush=True)
        if r.get("error"):
            print(f"ERR: {r['error']}", flush=True)
        if r.get("reply_snip"):
            print(f"REPLY: {r['reply_snip']}", flush=True)

        if i < len(PROMPTS):
            wait_model_queue_idle(label=f"after {p['id']} before next")
            time.sleep(BETWEEN_PROMPTS_PAUSE_S)

    gap_counts: dict[str, int] = {}
    for r in results:
        for g in r.get("gaps") or []:
            gap_counts[g] = gap_counts.get(g, 0) + 1

    elapsed_vals = [float(r["elapsed_s"]) for r in results]
    out = {
        "started": started,
        "finished": datetime.now(timezone.utc).isoformat(),
        "datasource": DATASOURCE,
        "suite": "mid-complex-5",
        "results": results,
        "summary": {
            "total": len(results),
            "pass": sum(1 for r in results if r.get("ok") and not r.get("gaps")),
            "warn": sum(1 for r in results if r.get("ok") and r.get("gaps")),
            "fail": sum(1 for r in results if r.get("hard_fail")),
            "terminal": sum(1 for r in results if r.get("terminal")),
            "with_sql": sum(1 for r in results if r.get("sql")),
            "executed": sum(1 for r in results if r.get("executed")),
            "repaired": sum(1 for r in results if r.get("repaired")),
            "gap_counts": gap_counts,
            "elapsed_s": {
                "total": round(sum(elapsed_vals), 2),
                "avg": round(sum(elapsed_vals) / len(elapsed_vals), 2) if elapsed_vals else 0,
                "min": round(min(elapsed_vals), 2) if elapsed_vals else 0,
                "max": round(max(elapsed_vals), 2) if elapsed_vals else 0,
            },
        },
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n# SUMMARY {json.dumps(out['summary'], ensure_ascii=False)}", flush=True)
    print(f"# wrote {OUT_JSON}", flush=True)
    return 0 if out["summary"]["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
