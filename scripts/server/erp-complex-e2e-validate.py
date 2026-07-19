#!/usr/bin/env python3
"""Sequential real-world ERP validation: DB → SQL smoke → chat smoke → budget APIs.

Writes /tmp/erp-complex-e2e-report.json and prints a human summary.
Exit 0 only if hard gates pass (DB + SQL 10/10 + no chat hard-unavailable storm).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore

SECRETS = Path("/data/nanobaseai/bi/secrets")
QG = "http://127.0.0.1:8792"
API = "http://127.0.0.1:8790"
CHAT = f"{API}/api/v1/bi/chat/stream"
REPORT = Path("/tmp/erp-complex-e2e-report.json")
DS = "erp"

# Import SQL cases from sibling smoke if present
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from erp_complex_sql_smoke import CASES as SQL_CASES  # type: ignore
except Exception:
    SQL_CASES = None

# Fallback: load from erp-complex-sql-smoke.py via exec
if SQL_CASES is None:
    smoke_path = Path(__file__).resolve().parent / "erp-complex-sql-smoke.py"
    ns: dict[str, Any] = {}
    if smoke_path.is_file():
        exec(smoke_path.read_text(encoding="utf-8"), ns)
        SQL_CASES = ns.get("CASES") or []

CHAT_PROMPTS = [
    {
        "id": "C01",
        "expect_min_rows": 1,
        "message": (
            "2026 mali yılında butce_planlari OPEX kalemlerini alis_faturalari ile "
            "butce_kodu üzerinden eşleştirip planlanan_tutar, gerçekleşen (genel_toplam toplamı) "
            "ve kullanım yüzdesini listele; en yüksek kullanımdan başla."
        ),
    },
    {
        "id": "C02",
        "expect_min_rows": 1,
        "message": (
            "2026 satış faturalarında (faturalar) müşteri bazında ciro top 5; "
            "her müşteri için unvan ve genel_toplam toplamını göster."
        ),
    },
    {
        "id": "C03",
        "expect_min_rows": 1,
        "message": (
            "2025 ile 2026 satış fatura cirosunu (faturalar.genel_toplam) yıllara göre karşılaştır; "
            "her yıl için toplam ciroyu tek satırda göster."
        ),
    },
    {
        "id": "C04",
        "expect_min_rows": 0,  # may be empty if model joins wrong table
        "message": (
            "Aktif fiyat listesine göre 2026 fatura kalemlerinde liste fiyatının %10 altındaki "
            "satışları ürün adıyla listele; en fazla 10 satır."
        ),
    },
    {
        "id": "C05",
        "expect_min_rows": 1,
        "message": (
            "2026 CAPEX butce_planlari kalemlerini listele; planlanan_tutar ve butce_kodu yaz."
        ),
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def qg_execute(sql: str) -> dict[str, Any]:
    body = json.dumps({"datasource_id": DS, "sql": sql, "tenant_id": "default"}).encode()
    last = None
    for path in ("/api/v1/query/execute", "/internal/v1/queries/execute"):
        try:
            req = urllib.request.Request(
                f"{QG}{path}",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:  # noqa: BLE001
            last = str(e)
    return {"ok": False, "error": last}


def qg_rows(data: dict[str, Any]) -> list[Any]:
    if isinstance(data.get("rows"), list):
        return data["rows"]
    res = data.get("result")
    if isinstance(res, dict) and isinstance(res.get("rows"), list):
        return res["rows"]
    if isinstance(data.get("data"), list):
        return data["data"]
    return []


def connect_owner():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 missing")
    src = json.loads((SECRETS / "connection.local.json").read_text())["sources"]["erp"]
    return psycopg2.connect(
        host=src["host"],
        port=int(src.get("port") or 5432),
        dbname=src["database"],
        user=src.get("username") or src.get("user"),
        password=src["password"],
        sslmode="require",
    )


def phase_db() -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "checks": []}
    conn = connect_owner()
    cur = conn.cursor()

    def check(name: str, sql: str, pred) -> None:
        cur.execute(sql)
        row = cur.fetchone()
        val = row[0] if row and len(row) == 1 else row
        ok = bool(pred(val))
        out["checks"].append({"name": name, "ok": ok, "value": _jsonable(val)})
        print(f"  DB {'PASS' if ok else 'FAIL'} {name}: {val}")

    check(
        "faturalar_2026",
        "SELECT count(*), coalesce(sum(genel_toplam),0) FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026",
        lambda v: v and v[0] >= 100 and float(v[1]) > 0,
    )
    check(
        "tahsilat_2026",
        "SELECT count(*) FROM tahsilatlar WHERE EXTRACT(YEAR FROM odeme_tarihi)=2026",
        lambda v: v >= 50,
    )
    check(
        "po_2026",
        "SELECT count(*) FROM satin_alma_siparisleri WHERE EXTRACT(YEAR FROM siparis_tarihi)=2026",
        lambda v: v >= 20,
    )
    check(
        "aktif_fiyat_listeleri",
        "SELECT count(*) FROM fiyat_listeleri WHERE aktif IS TRUE",
        lambda v: v >= 1,
    )
    check(
        "fiyat_kalem",
        "SELECT count(*) FROM fiyat_listesi_kalemleri",
        lambda v: v >= 50,
    )
    check(
        "yevmiye_2026",
        "SELECT count(*) FROM yevmiye_fisleri WHERE EXTRACT(YEAR FROM fis_tarihi)=2026",
        lambda v: v >= 1,
    )
    check(
        "butce_opex_2026",
        "SELECT count(*) FROM butce_planlari WHERE mali_yil=2026 AND upper(tur)='OPEX'",
        lambda v: v >= 3,
    )
    check(
        "demo26_tag",
        "SELECT count(*) FROM faturalar WHERE fatura_no LIKE 'DEMO26-FT-%'",
        lambda v: v >= 100,
    )
    # Cross-check QG RO can see same counts
    ro = qg_execute(
        "SELECT count(*) AS n FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026"
    )
    rows = qg_rows(ro)
    n = None
    if rows:
        r0 = rows[0]
        n = r0.get("n") if isinstance(r0, dict) else r0[0]
    qg_ok = n is not None and int(n) >= 100
    out["checks"].append({"name": "qg_ro_faturalar_2026", "ok": qg_ok, "value": n})
    print(f"  DB {'PASS' if qg_ok else 'FAIL'} qg_ro_faturalar_2026: {n}")

    out["ok"] = all(c["ok"] for c in out["checks"])
    cur.close()
    conn.close()
    return out


def _jsonable(v: Any) -> Any:
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    try:
        from decimal import Decimal

        if isinstance(v, Decimal):
            return float(v)
    except Exception:
        pass
    return v


def phase_sql() -> dict[str, Any]:
    results = []
    if not SQL_CASES:
        return {"ok": False, "error": "SQL_CASES missing", "results": []}
    for case in SQL_CASES:
        cid = case["id"]
        t0 = time.time()
        data = qg_execute(case["sql"])
        rows = qg_rows(data)
        elapsed = round(time.time() - t0, 2)
        ok = bool(data.get("ok", True)) and "error" not in (data.get("code") or "").lower()
        if data.get("error") and not rows:
            ok = False
        # Soft semantic gates
        notes = []
        if cid in ("P01", "P02", "P05", "P07", "P09", "P10") and ok and len(rows) == 0:
            notes.append("empty_rows")
            # P03 can be non-empty with 2026 data; P09 should have leakage
            if cid in ("P02", "P05", "P07", "P09", "P10", "P01"):
                ok = False
                notes.append("expected_rows")
        if cid == "P03" and ok and len(rows) == 0:
            notes.append("empty_margin_unexpected")
            ok = False
        if cid == "P06" and ok and len(rows) == 0:
            notes.append("empty_customer_share")
            ok = False
        sample = rows[0] if rows else None
        results.append(
            {
                "id": cid,
                "title": case.get("title"),
                "ok": ok,
                "elapsed_s": elapsed,
                "row_count": len(rows),
                "notes": notes,
                "sample": _jsonable(sample),
                "error": data.get("error") or data.get("message"),
            }
        )
        print(
            f"  SQL {'PASS' if ok else 'FAIL'} {cid} {elapsed}s rows={len(rows)} {notes or ''}"
        )
    passed = sum(1 for r in results if r["ok"])
    return {"ok": passed == len(results), "pass": passed, "total": len(results), "results": results}


def run_chat(prompt: dict[str, Any]) -> dict[str, Any]:
    if httpx is None:
        return {"id": prompt["id"], "ok": False, "error": "httpx missing"}
    msg = prompt["message"]
    t0 = time.time()
    events: list[str] = []
    sql = None
    rows: list[Any] = []
    err = None
    code = None
    clarify = False
    phases: list[str] = []
    try:
        with httpx.Client(timeout=httpx.Timeout(280.0, connect=20.0)) as c:
            with c.stream(
                "POST",
                CHAT,
                json={
                    "message": msg,
                    "db_name": "erp",
                    "session_id": f"e2e-{prompt['id']}-{int(t0)}",
                },
                headers={"Accept": "text/event-stream"},
            ) as r:
                name = "message"
                buf: list[str] = []
                for line in r.iter_lines():
                    if line.startswith("event:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        buf.append(line.split(":", 1)[1].strip())
                    elif line == "" and buf:
                        data = json.loads("\n".join(buf))
                        buf = []
                        events.append(name)
                        ph = data.get("phase")
                        if isinstance(ph, str):
                            phases.append(ph)
                        if data.get("sql"):
                            sql = data["sql"]
                        plan = data.get("plan")
                        if isinstance(plan, dict) and plan.get("sql"):
                            sql = plan["sql"]
                        if name == "done":
                            qr = data.get("query_result") or {}
                            rows = qr.get("rows") or []
                            err = data.get("sql_error")
                            clarify = bool(data.get("needs_clarification"))
                            break
                        if name == "error":
                            err = data.get("message") or data.get("error")
                            code = data.get("code")
                            break
                        name = "message"
    except Exception as e:  # noqa: BLE001
        err = str(e)
        code = type(e).__name__

    elapsed = round(time.time() - t0, 1)
    hard_fail = code in (
        "TEXT_TO_SQL_MODEL_UNAVAILABLE",
        "MODEL_QUEUE_TIMEOUT",
        "MODEL_QUEUE_FULL",
    ) or (err and "Text-to-SQL modeline erişilemiyor" in str(err))
    min_rows = int(prompt.get("expect_min_rows") or 0)
    ok = (not hard_fail) and (clarify or (sql is not None) or len(rows) >= min_rows)
    if min_rows > 0 and not clarify and len(rows) < min_rows and not hard_fail:
        # soft fail: pipeline worked but empty/wrong SQL
        ok = bool(sql) and err is None
    status = "PASS" if ok and not hard_fail else ("HARD_FAIL" if hard_fail else "SOFT_FAIL")
    if clarify:
        status = "CLARIFY"
        ok = True  # not a hard system failure
    print(
        f"  CHAT {status} {prompt['id']} {elapsed}s rows={len(rows)} "
        f"sql={'Y' if sql else 'N'} err={str(err)[:80] if err else None}"
    )
    return {
        "id": prompt["id"],
        "ok": ok and not hard_fail,
        "hard_fail": hard_fail,
        "status": status,
        "elapsed_s": elapsed,
        "row_count": len(rows),
        "has_sql": bool(sql),
        "sql_preview": (sql or "")[:300],
        "sql_error": err,
        "code": code,
        "clarify": clarify,
        "phases": phases[-12:],
        "events": events[-20:],
        "sample_row": _jsonable(rows[0]) if rows else None,
    }


def phase_chat() -> dict[str, Any]:
    results = []
    for p in CHAT_PROMPTS:
        results.append(run_chat(p))
        time.sleep(2)  # breathe between model calls
    hard = sum(1 for r in results if r.get("hard_fail"))
    passed = sum(1 for r in results if r.get("ok"))
    return {
        "ok": hard == 0 and passed >= max(1, len(results) - 1),
        "pass": passed,
        "hard_fail": hard,
        "total": len(results),
        "results": results,
    }


def phase_api() -> dict[str, Any]:
    checks = []

    def hit(name: str, url: str, method: str = "GET", body: dict | None = None) -> None:
        data = None
        code = 0
        try:
            req = urllib.request.Request(
                url,
                data=(json.dumps(body).encode() if body is not None else None),
                headers={"Content-Type": "application/json"},
                method=method,
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                code = resp.status
                raw = resp.read()
                try:
                    data = json.loads(raw.decode())
                except Exception:
                    data = {"raw_len": len(raw)}
        except urllib.error.HTTPError as e:
            code = e.code
            try:
                data = json.loads(e.read().decode())
            except Exception:
                data = {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            data = {"error": str(e)}
        ok = 200 <= code < 300
        checks.append({"name": name, "ok": ok, "http": code, "sample": _jsonable(data) if isinstance(data, dict) else data})
        print(f"  API {'PASS' if ok else 'FAIL'} {name} http={code}")

    hit("health", f"{API}/health")
    hit("status", f"{API}/api/v1/bi/status")
    hit("match_preview", f"{API}/api/v1/bi/budgets/match-preview")
    hit("import_template", f"{API}/api/v1/bi/budgets/import-template")
    hit("budgets_2026", f"{API}/api/v1/bi/budgets?fiscal_year=2026")
    hit("export_xlsx", f"{API}/api/v1/bi/budgets/export?format=xlsx&fiscal_year=2026")
    hit("briefing", f"{API}/api/v1/bi/briefing?dashboard_id=default&locale=tr")
    hit("narrative_limited", f"{API}/api/v1/bi/narrative?dashboard_id=default&locale=tr")
    # QG AND/CASE regression
    sql = (
        "SELECT bp.butce_kodu, CASE WHEN bp.planlanan_tutar=0 THEN NULL "
        "ELSE ROUND(100.0*COALESCE(SUM(af.genel_toplam),0)/bp.planlanan_tutar,2) END AS pct "
        "FROM butce_planlari bp LEFT JOIN alis_faturalari af "
        "ON bp.butce_kodu=af.butce_kodu AND EXTRACT(YEAR FROM af.fatura_tarihi)=bp.mali_yil "
        "WHERE bp.mali_yil=2026 AND upper(bp.tur)='OPEX' "
        "GROUP BY bp.butce_kodu, bp.planlanan_tutar ORDER BY pct DESC NULLS LAST LIMIT 5"
    )
    data = qg_execute(sql)
    rows = qg_rows(data)
    and_ok = len(rows) >= 1 and not data.get("error")
    checks.append({"name": "qg_and_case", "ok": and_ok, "row_count": len(rows), "sample": _jsonable(rows[0]) if rows else None})
    print(f"  API {'PASS' if and_ok else 'FAIL'} qg_and_case rows={len(rows)}")

    # narrative is known limited — ok if returns 200 with limited/empty
    for c in checks:
        if c["name"] == "narrative_limited":
            c["ok"] = c.get("http") == 200
            c["note"] = "endpoint may be limited/empty by design"

    return {"ok": all(c["ok"] for c in checks if c["name"] != "narrative_limited") and and_ok, "checks": checks}


def main() -> int:
    report: dict[str, Any] = {
        "started_at": _now(),
        "host_checks": {},
        "phases": {},
    }
    print("# ERP complex E2E validate", _now())
    print("## 1) DB")
    report["phases"]["db"] = phase_db()
    print("## 2) SQL smoke")
    report["phases"]["sql"] = phase_sql()
    print("## 3) Chat smoke")
    report["phases"]["chat"] = phase_chat()
    print("## 4) API smoke")
    report["phases"]["api"] = phase_api()

    db_ok = report["phases"]["db"]["ok"]
    sql_ok = report["phases"]["sql"]["ok"]
    chat = report["phases"]["chat"]
    api_ok = report["phases"]["api"]["ok"]
    report["summary"] = {
        "db": db_ok,
        "sql": sql_ok,
        "sql_pass": f"{report['phases']['sql'].get('pass')}/{report['phases']['sql'].get('total')}",
        "chat_pass": f"{chat.get('pass')}/{chat.get('total')}",
        "chat_hard_fail": chat.get("hard_fail"),
        "api": api_ok,
        "gate_pass": db_ok and sql_ok and chat.get("hard_fail", 1) == 0 and api_ok,
    }
    report["finished_at"] = _now()
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n# SUMMARY")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"report → {REPORT}")
    return 0 if report["summary"]["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
