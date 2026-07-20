#!/usr/bin/env python3
"""Run 10 complex ERP NL prompts through chat/stream using httpx SSE."""

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
# Soft budget for one prompt; we still wait for terminal done/error beyond this.
TIMEOUT_S = 420.0
# Never abandon a prompt and start the next one before this absolute cap.
HARD_TIMEOUT_S = 900.0
# After terminal SSE, wait until model queue is fully idle before POSTing the next prompt.
QUEUE_IDLE_POLL_S = 2.0
QUEUE_IDLE_MAX_WAIT_S = 600.0
BETWEEN_PROMPTS_PAUSE_S = 1.0

PROMPTS: list[dict[str, str]] = [
    {
        "id": "P01",
        "title": "YoY AR vs AP + collection gap",
        "message": (
            "ERP'de 2025 ile 2026'yı karşılaştır: satış faturaları (faturalar) genel_toplam "
            "yıllık ciro ile alış faturaları (alis_faturalari) genel_toplam yıllık gideri yan yana getir; "
            "her yıl için tahsilatlar.tutar toplamını da ekle. Sonra 2026'da açık veya kısmi "
            "durumdaki satış faturalarının vadesi geçmiş olanlarının "
            "kalan riskini müşteri unvanına göre top 10 listele."
        ),
    },
    {
        "id": "P02",
        "title": "Budget vs AP actuals by code",
        "message": (
            "2026 mali yılı için butce_planlari ile alis_faturalari'yı butce_kodu üzerinden eşleştir. "
            "Her bütçe kalemi için planlanan_tutar, 2026 yılı fatura genel_toplam toplamı, fark ve "
            "kullanım yüzdesi hesapla. Sadece OPEX kalemleri; kullanım > 80 olanları önce göster. "
            "Departman kodu ve kalem adını da yaz."
        ),
    },
    {
        "id": "P03",
        "title": "Margin by product category + brand",
        "message": (
            "Son 12 aydaki satış fatura kalemlerinden ürün bazında ciro üret; urunler, "
            "urun_kategorileri ve markalar ile birleştir. Kategori cirosuna göre top 8 ve "
            "kaba brüt marj ((birim_fiyat - alis_fiyat)*miktar) hesapla. İptal faturalarını hariç tut."
        ),
    },
    {
        "id": "P04",
        "title": "PO → invoice lag by supplier",
        "message": (
            "2026 satın alma siparişlerini tedarikçi ile birleştir; bağlı alış faturalarının "
            "sipariş-fatura gün farkı ortalamasını tedarikçi bazında hesapla. Faturası gelmemiş "
            "sipariş sayısını ve vadesi geçmiş ödenmemiş alış fatura tutarını da ekle."
        ),
    },
    {
        "id": "P05",
        "title": "Stock days cover + dead stock",
        "message": (
            "stok_bakiyeleri + urunler + depolar: net stok (miktar-rezervasyon). Son 90 günde "
            "stok_hareketleri çıkışlarından günlük ortalama ile kaç günlük stok kaldığını hesapla. "
            "Hareketi olmayan ölü stok top 15 (miktar*alis_fiyat)."
        ),
    },
    {
        "id": "P06",
        "title": "Customer concentration + limit",
        "message": (
            "2026 satış faturalarında müşteri ciro payı top 10; top 5'in toplam payı. "
            "Açık bakiye (fatura-tahsilat) ile musteriler.risk_limit kıyası; limiti aşanlar. "
            "İl bazında 2026 ciro dağılımı."
        ),
    },
    {
        "id": "P07",
        "title": "Branch sales per headcount",
        "message": (
            "Şube bazında 2026 fatura cirosu, satış sipariş sayısı ve aktif personel ile "
            "kişi başı ciro. En düşük ve en yüksek 5 şube."
        ),
    },
    {
        "id": "P08",
        "title": "GL revenue vs invoices by month",
        "message": (
            "yevmiye_kalemleri + hesap_planlari 2026 gelir/satış hesapları alacak toplamını "
            "ay ay faturalar.genel_toplam ile karşılaştır; farkı büyük ayları göster."
        ),
    },
    {
        "id": "P09",
        "title": "Price list leakage",
        "message": (
            "2026'da fatura_kalemleri birim fiyatı, fiyat_listesi_kalemleri liste fiyatının "
            "%10 altındaysa iskonto kaybını hesapla; en çok kayıp üreten 20 satır ve ürün toplamı."
        ),
    },
    {
        "id": "P10",
        "title": "CAPEX plan vs AP vs open PO",
        "message": (
            "2026 CAPEX butce_planlari için plan, aynı butce_kodu alış fatura gerçekleşeni ve "
            "açık satın alma sipariş tutarını birleştir; kalan=plan-gerçekleşen-açıkPO; "
            "aşım olan kalemleri tedarikçi dağılımıyla listele."
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

    for ev, data in events:
        if ev == "error" or data.get("type") == "ERROR":
            final_error = str(data.get("message") or data.get("error") or data)[:500]
        if data.get("phase") == "schema_retrieval_done":
            tables = data.get("tables")
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
        "confidence": conf,
        "reply_snip": reply_snip,
        "error": final_error,
        "event_count": len(events),
        "event_names": [ev for ev, _ in events],
    }


def wait_model_queue_idle(*, label: str = "") -> dict[str, Any]:
    """Block until API reports active=0 and waiting=0 (or give up after max wait)."""
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
                print(f"  queue idle ({elapsed}s wait){(' — ' + label) if label else ''}", flush=True)
            return last
        print(
            f"  waiting model queue idle… active={active} waiting={waiting}"
            f"{(' [' + label + ']') if label else ''}",
            flush=True,
        )
        time.sleep(QUEUE_IDLE_POLL_S)
    print(
        f"  WARN: model queue still busy after {QUEUE_IDLE_MAX_WAIT_S}s "
        f"(active={last.get('active')} waiting={last.get('waiting')}) — proceeding cautiously",
        flush=True,
    )
    return last


def run_one(prompt: dict[str, str]) -> dict[str, Any]:
    """POST one prompt and block until a clear terminal SSE (done|error) arrives.

    Does not return early on soft wall timeout — only HARD_TIMEOUT_S can force-stop,
    and even then the caller must wait for queue idle before the next POST.
    """
    body = {
        "message": prompt["message"],
        "db_name": DATASOURCE,
        "session_id": f"erp-complex-{prompt['id']}-{int(time.time())}",
    }
    t0 = time.time()
    events: list[tuple[str, dict[str, Any]]] = []
    wall_err: str | None = None
    terminal = False
    event_name = "message"
    data_buf: list[str] = []
    soft_warned = False

    # httpx read timeout must cover HARD_TIMEOUT; we gate logic ourselves.
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
                            f"  … still waiting for terminal done/error "
                            f"(soft budget {TIMEOUT_S}s exceeded, hard cap {HARD_TIMEOUT_S}s)",
                            flush=True,
                        )
                    if elapsed > HARD_TIMEOUT_S:
                        wall_err = f"TimeoutError: hard wall > {HARD_TIMEOUT_S}s (no terminal SSE)"
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
                        stop = event_name in {"done", "error"}
                        if stop:
                            terminal = True
                            event_name = "message"
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
    print(f"# ERP complex chat smoke — {started} — ds={DATASOURCE}", flush=True)
    print(
        f"# gate: next prompt ONLY after terminal done/error + model-queue idle "
        f"(soft={TIMEOUT_S}s hard={HARD_TIMEOUT_S}s)",
        flush=True,
    )

    # Ensure nothing leftover is holding the model before we start.
    wait_model_queue_idle(label="before P01")

    for i, p in enumerate(PROMPTS, 1):
        print(f"\n== [{i}/10] {p['id']} {p['title']} ==", flush=True)
        print(f"Q: {p['message'][:200]}", flush=True)
        print("  POST chat/stream — waiting for clear result (done|error)…", flush=True)
        r = run_one(p)
        results.append(r)
        status = "FAIL" if r["hard_fail"] else ("WARN" if r["gaps"] else "PASS")
        term = "terminal=Y" if r.get("terminal") else "terminal=N"
        print(
            f"→ {status} {r['elapsed_s']}s {term} events={r['event_count']} "
            f"exec={r['executed']} rows={r['row_count']} gaps={r['gaps']}",
            flush=True,
        )
        if r.get("tables_retrieved"):
            print(f"SCHEMA: {r['tables_retrieved'][:8]}", flush=True)
        if r.get("sql"):
            print(f"SQL: {r['sql'][:500].replace(chr(10), ' ')}", flush=True)
        if r.get("sql_error"):
            print(f"SQL_ERR: {r['sql_error']}", flush=True)
        if r.get("error"):
            print(f"ERR: {r['error']}", flush=True)
        if r.get("reply_snip"):
            print(f"REPLY: {r['reply_snip']}", flush=True)
        print(f"EVENTS: {r.get('event_names')}", flush=True)

        # CRITICAL: do not POST the next prompt until this one fully released the model.
        if i < len(PROMPTS):
            wait_model_queue_idle(label=f"after {p['id']} before next")
            time.sleep(BETWEEN_PROMPTS_PAUSE_S)

    gap_counts: dict[str, int] = {}
    for r in results:
        for g in r.get("gaps") or []:
            gap_counts[g] = gap_counts.get(g, 0) + 1
    out = {
        "started": started,
        "finished": datetime.now(timezone.utc).isoformat(),
        "datasource": DATASOURCE,
        "gate": {
            "next_prompt_requires_terminal_sse": True,
            "next_prompt_requires_queue_idle": True,
            "soft_timeout_s": TIMEOUT_S,
            "hard_timeout_s": HARD_TIMEOUT_S,
        },
        "prompts": [{"id": p["id"], "title": p["title"], "message": p["message"]} for p in PROMPTS],
        "results": results,
        "summary": {
            "total": len(results),
            "pass": sum(1 for r in results if r.get("ok") and not r.get("gaps")),
            "warn": sum(1 for r in results if r.get("ok") and r.get("gaps")),
            "fail": sum(1 for r in results if r.get("hard_fail")),
            "terminal": sum(1 for r in results if r.get("terminal")),
            "with_sql": sum(1 for r in results if r.get("sql")),
            "executed": sum(1 for r in results if r.get("executed")),
            "gap_counts": gap_counts,
        },
    }
    path = "/tmp/erp-complex-chat-smoke.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n# SUMMARY {json.dumps(out['summary'], ensure_ascii=False)}", flush=True)
    print(f"# wrote {path}", flush=True)
    return 0 if out["summary"]["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
