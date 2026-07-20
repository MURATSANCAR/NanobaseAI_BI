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
DATASOURCE = "erp"
TIMEOUT_S = 420.0

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


def run_one(prompt: dict[str, str]) -> dict[str, Any]:
    body = {
        "message": prompt["message"],
        "db_name": DATASOURCE,
        "session_id": f"erp-complex-{prompt['id']}-{int(time.time())}",
    }
    t0 = time.time()
    events: list[tuple[str, dict[str, Any]]] = []
    wall_err: str | None = None
    event_name = "message"
    data_buf: list[str] = []

    try:
        with httpx.Client(timeout=httpx.Timeout(TIMEOUT_S, connect=30.0)) as client:
            with client.stream(
                "POST",
                API,
                json=body,
                headers={"Accept": "text/event-stream"},
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if time.time() - t0 > TIMEOUT_S:
                        wall_err = f"TimeoutError: wall > {TIMEOUT_S}s"
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
                        stop = event_name in {"done", "error"}
                        event_name = "message"
                        if stop:
                            break
    except Exception as exc:  # noqa: BLE001
        wall_err = f"{type(exc).__name__}: {exc}"[:500]

    elapsed = round(time.time() - t0, 2)
    scored = _score(events, wall_err)
    return {
        "id": prompt["id"],
        "title": prompt["title"],
        "elapsed_s": elapsed,
        "ok": not scored["hard_fail"],
        **scored,
    }


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    results: list[dict[str, Any]] = []
    print(f"# ERP complex chat smoke — {started} — ds={DATASOURCE}", flush=True)
    for i, p in enumerate(PROMPTS, 1):
        print(f"\n== [{i}/10] {p['id']} {p['title']} ==", flush=True)
        print(f"Q: {p['message'][:200]}", flush=True)
        r = run_one(p)
        results.append(r)
        status = "FAIL" if r["hard_fail"] else ("WARN" if r["gaps"] else "PASS")
        print(
            f"→ {status} {r['elapsed_s']}s events={r['event_count']} "
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

    gap_counts: dict[str, int] = {}
    for r in results:
        for g in r.get("gaps") or []:
            gap_counts[g] = gap_counts.get(g, 0) + 1
    out = {
        "started": started,
        "finished": datetime.now(timezone.utc).isoformat(),
        "datasource": DATASOURCE,
        "prompts": [{"id": p["id"], "title": p["title"], "message": p["message"]} for p in PROMPTS],
        "results": results,
        "summary": {
            "total": len(results),
            "pass": sum(1 for r in results if r.get("ok") and not r.get("gaps")),
            "warn": sum(1 for r in results if r.get("ok") and r.get("gaps")),
            "fail": sum(1 for r in results if r.get("hard_fail")),
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
