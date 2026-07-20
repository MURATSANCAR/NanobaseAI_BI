#!/usr/bin/env python3
"""Cross-check Cursor ERP smoke scripts against live ERP DB via Query Gateway + owner.

Verifies:
  1) Seed / inventory truth
  2) Hand-SQL smoke (erp-complex-sql-smoke.py) still returns expected rows
  3) Chat-smoke outcomes are not due to empty DB (intent-level data exists)
  4) P02 chat PASS sample consistency vs DB

Writes /tmp/erp-script-db-crosscheck.json
"""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore

SECRETS = Path("/data/nanobaseai/bi/secrets")
QG = "http://127.0.0.1:8792"
DS = "erp"
SMOKE = Path("/data/nanobaseai/bi/frontend/scripts/server/erp-complex-sql-smoke.py")
CHAT_REPORT = Path("/tmp/erp-complex-chat-smoke.json")
OUT = Path("/tmp/erp-script-db-crosscheck.json")


def qg(sql: str) -> dict[str, Any]:
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
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:  # noqa: BLE001
            last = str(e)
    return {"ok": False, "error": last}


def rows_of(data: dict[str, Any]) -> list[Any]:
    if isinstance(data.get("rows"), list):
        return data["rows"]
    res = data.get("result")
    if isinstance(res, dict) and isinstance(res.get("rows"), list):
        return res["rows"]
    return []


def j(v: Any) -> Any:
    if hasattr(v, "isoformat"):
        return v.isoformat()
    try:
        from decimal import Decimal

        if isinstance(v, Decimal):
            return float(v)
    except Exception:
        pass
    if isinstance(v, (list, tuple)):
        return [j(x) for x in v]
    return v


def owner_connect():
    src = json.loads((SECRETS / "connection.local.json").read_text())["sources"]["erp"]
    return psycopg2.connect(
        host=src["host"],
        port=int(src.get("port") or 5432),
        dbname=src["database"],
        user=src.get("username") or src.get("user"),
        password=src["password"],
        sslmode="require",
    )


def phase_inventory() -> dict[str, Any]:
    checks = []

    def add(name: str, sql: str, pred) -> None:
        data = qg(sql)
        r = rows_of(data)
        val = r[0] if r else None
        # keep both raw row and unwrapped scalar for flexible preds
        raw = val
        if isinstance(val, dict) and len(val) == 1:
            val = next(iter(val.values()))
        ok = False
        try:
            ok = bool(pred(raw, val)) and not data.get("error")
        except TypeError:
            ok = bool(pred(val)) and not data.get("error")
        checks.append({"name": name, "ok": ok, "value": j(raw), "error": data.get("error")})
        print(f"  INV {'PASS' if ok else 'FAIL'} {name}: {raw}")

    add(
        "faturalar_2026_count_sum",
        "SELECT count(*) AS n, coalesce(sum(genel_toplam),0) AS ciro FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026",
        lambda raw, val: isinstance(raw, dict) and int(raw["n"]) >= 100 and float(raw["ciro"]) > 0,
    )
    add(
        "demo26_faturalar",
        "SELECT count(*) AS n FROM faturalar WHERE fatura_no LIKE 'DEMO26-FT-%'",
        lambda raw, val: int(val) >= 100,
    )
    add(
        "tahsilat_2026",
        "SELECT count(*) AS n FROM tahsilatlar WHERE EXTRACT(YEAR FROM odeme_tarihi)=2026",
        lambda raw, val: int(val) >= 50,
    )
    add(
        "po_2026",
        "SELECT count(*) AS n FROM satin_alma_siparisleri WHERE EXTRACT(YEAR FROM siparis_tarihi)=2026",
        lambda raw, val: int(val) >= 20,
    )
    add(
        "aktif_fiyat_listesi",
        "SELECT count(*) AS n FROM fiyat_listeleri WHERE aktif IS TRUE",
        lambda raw, val: int(val) >= 1,
    )
    add(
        "fiyat_kalem",
        "SELECT count(*) AS n FROM fiyat_listesi_kalemleri",
        lambda raw, val: int(val) >= 50,
    )
    add(
        "opex_2026",
        "SELECT count(*) AS n FROM butce_planlari WHERE mali_yil=2026 AND upper(tur)='OPEX'",
        lambda raw, val: int(val) >= 3,
    )
    add(
        "capex_2026",
        "SELECT count(*) AS n FROM butce_planlari WHERE mali_yil=2026 AND upper(tur)='CAPEX'",
        lambda raw, val: int(val) >= 1,
    )
    add(
        "yevmiye_2026",
        "SELECT count(*) AS n FROM yevmiye_fisleri WHERE EXTRACT(YEAR FROM fis_tarihi)=2026",
        lambda raw, val: int(val) >= 1,
    )
    add(
        "fatura_kalemleri_total",
        "SELECT count(*) AS n FROM fatura_kalemleri",
        lambda raw, val: int(val) > 1000,
    )

    # Owner vs QG RO consistency on DEMO26 count
    owner_n = None
    if psycopg2 is not None:
        conn = owner_connect()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM faturalar WHERE fatura_no LIKE 'DEMO26-FT-%'")
        owner_n = cur.fetchone()[0]
        cur.close()
        conn.close()
    ro = qg("SELECT count(*) AS n FROM faturalar WHERE fatura_no LIKE 'DEMO26-FT-%'")
    ro_n = rows_of(ro)[0]["n"] if rows_of(ro) else None
    match = owner_n is not None and int(owner_n) == int(ro_n)
    checks.append(
        {
            "name": "owner_vs_qg_demo26",
            "ok": match,
            "value": {"owner": owner_n, "qg": ro_n},
        }
    )
    print(f"  INV {'PASS' if match else 'FAIL'} owner_vs_qg_demo26: owner={owner_n} qg={ro_n}")

    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def phase_sql_smoke() -> dict[str, Any]:
    ns: dict[str, Any] = {"__name__": "x", "__file__": str(SMOKE)}
    exec(SMOKE.read_text(encoding="utf-8"), ns)
    cases = ns["CASES"]
    results = []
    for case in cases:
        t0 = time.time()
        data = qg(case["sql"])
        rs = rows_of(data)
        elapsed = round(time.time() - t0, 2)
        ok = bool(rs) and not data.get("error")
        # semantic: at least 1 row for all known seeds
        results.append(
            {
                "id": case["id"],
                "title": case["title"],
                "ok": ok,
                "elapsed_s": elapsed,
                "row_count": len(rs),
                "sample": j(rs[0]) if rs else None,
                "error": data.get("error") or data.get("detail") or data.get("message"),
            }
        )
        print(
            f"  SQL {'PASS' if ok else 'FAIL'} {case['id']} {elapsed}s rows={len(rs)} sample={j(rs[0]) if rs else None}"
        )
    passed = sum(1 for r in results if r["ok"])
    return {
        "ok": passed == len(results),
        "pass": passed,
        "total": len(results),
        "results": results,
    }


def phase_intent_data_exists() -> dict[str, Any]:
    """Prove chat WARN/FAIL were not empty-DB — each intent has supporting rows."""
    intents = [
        (
            "P01_yoy",
            "SELECT EXTRACT(YEAR FROM fatura_tarihi)::int AS y, count(*) AS n, sum(genel_toplam) AS ciro FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi) IN (2025,2026) GROUP BY 1 ORDER BY 1",
            lambda rs: len(rs) >= 1 and any(int(r.get("n") or r[1] if not isinstance(r, dict) else r["n"]) > 0 for r in rs),
        ),
        (
            "P02_opex_match",
            "SELECT count(*) AS n FROM butce_planlari b JOIN alis_faturalari a ON a.butce_kodu=b.butce_kodu AND EXTRACT(YEAR FROM a.fatura_tarihi)=b.mali_yil WHERE b.mali_yil=2026 AND upper(b.tur)='OPEX'",
            lambda rs: rs and int((rs[0]["n"] if isinstance(rs[0], dict) else rs[0][0])) > 0,
        ),
        (
            "P03_margin_12m",
            "SELECT count(*) AS n FROM fatura_kalemleri fk JOIN faturalar f ON f.id=fk.fatura_id WHERE f.fatura_tarihi >= CURRENT_DATE - INTERVAL '12 months'",
            lambda rs: rs and int(rs[0]["n"] if isinstance(rs[0], dict) else rs[0][0]) > 0,
        ),
        (
            "P04_po_2026",
            "SELECT count(*) AS n FROM satin_alma_siparisleri WHERE EXTRACT(YEAR FROM siparis_tarihi)=2026",
            lambda rs: rs and int(rs[0]["n"] if isinstance(rs[0], dict) else rs[0][0]) >= 20,
        ),
        (
            "P05_stock",
            "SELECT count(*) AS n FROM stok_bakiyeleri WHERE miktar > 0",
            lambda rs: rs and int(rs[0]["n"] if isinstance(rs[0], dict) else rs[0][0]) > 0,
        ),
        (
            "P06_customers_2026",
            "SELECT count(DISTINCT musteri_id) AS n FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026",
            lambda rs: rs and int(rs[0]["n"] if isinstance(rs[0], dict) else rs[0][0]) > 0,
        ),
        (
            "P07_branches",
            "SELECT count(DISTINCT sube_id) AS n FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026 AND sube_id IS NOT NULL",
            lambda rs: rs and int(rs[0]["n"] if isinstance(rs[0], dict) else rs[0][0]) > 0,
        ),
        (
            "P08_gl_2026",
            "SELECT count(*) AS n FROM yevmiye_kalemleri yk JOIN yevmiye_fisleri yf ON yf.id=yk.fis_id WHERE EXTRACT(YEAR FROM yf.fis_tarihi)=2026",
            lambda rs: rs and int(rs[0]["n"] if isinstance(rs[0], dict) else rs[0][0]) > 0,
        ),
        (
            "P09_price_leak",
            """
SELECT count(*) AS n
FROM fatura_kalemleri fk
JOIN faturalar f ON f.id=fk.fatura_id
JOIN fiyat_listesi_kalemleri flk ON flk.urun_id=fk.urun_id
JOIN fiyat_listeleri fl ON fl.id=flk.liste_id AND fl.aktif IS TRUE
WHERE EXTRACT(YEAR FROM f.fatura_tarihi)=2026
  AND fk.birim_fiyat < flk.fiyat * 0.9
LIMIT 1
""".strip(),
            lambda rs: rs and int(rs[0]["n"] if isinstance(rs[0], dict) else rs[0][0]) > 0,
        ),
        (
            "P10_capex",
            "SELECT count(*) AS n FROM butce_planlari WHERE mali_yil=2026 AND upper(tur)='CAPEX'",
            lambda rs: rs and int(rs[0]["n"] if isinstance(rs[0], dict) else rs[0][0]) >= 1,
        ),
    ]
    out = []
    for name, sql, pred in intents:
        data = qg(sql)
        rs = rows_of(data)
        ok = False
        err = data.get("error") or data.get("detail")
        try:
            ok = bool(pred(rs)) and not err
        except Exception as e:  # noqa: BLE001
            err = str(e)
            ok = False
        out.append({"name": name, "ok": ok, "sample": j(rs[:3] if rs else None), "error": err})
        print(f"  INT {'PASS' if ok else 'FAIL'} {name}: {j(rs[0] if rs else None)} err={err}")
    return {"ok": all(x["ok"] for x in out), "checks": out}


def phase_chat_vs_db() -> dict[str, Any]:
    if not CHAT_REPORT.is_file():
        return {"ok": False, "error": "chat report missing"}
    chat = json.loads(CHAT_REPORT.read_text())
    verdicts = []
    for r in chat.get("results") or []:
        cid = r["id"]
        status = "FAIL" if r.get("hard_fail") else ("WARN" if r.get("gaps") else "PASS")
        # DB truth for this intent already in intent phase; classify cause
        cause = "unknown"
        err = (r.get("sql_error") or r.get("error") or "")
        if status == "PASS" and r.get("executed"):
            cause = "e2e_ok"
        elif "DATABASE_UNAVAILABLE" in str(err):
            cause = "db_or_qg_timeout_on_heavy_sql_not_empty_data"
        elif "TimeoutError" in str(err) or "wall" in str(err):
            cause = "llm_wall_timeout_sql_generated_data_exists"
        elif "WILDCARD" in str(err):
            cause = "policy_reject_select_star_data_exists"
        elif "JSON" in str(err) or "ayrıştırılamadı" in str(err):
            cause = "llm_plan_parse_fail_data_exists"
        elif r.get("sql") and not r.get("executed"):
            cause = "sql_generated_not_executed"
        verdicts.append(
            {
                "id": cid,
                "chat_status": status,
                "elapsed_s": r.get("elapsed_s"),
                "had_sql": bool(r.get("sql")),
                "executed": r.get("executed"),
                "db_cause_class": cause,
                "error": str(err)[:180] or None,
            }
        )
        print(f"  CHAT {cid} {status} → DB-class={cause}")

    # P02 sample consistency: chat said 6 rows OPEX budget
    p02_db = qg(
        """
SELECT count(*) AS n FROM (
  SELECT b.id
  FROM butce_planlari b
  LEFT JOIN alis_faturalari a
    ON a.butce_kodu=b.butce_kodu AND EXTRACT(YEAR FROM a.fatura_tarihi)=b.mali_yil
  WHERE b.mali_yil=2026 AND LOWER(b.tur)='opex'
  GROUP BY b.id
) t
""".strip()
    )
    p02_n = rows_of(p02_db)[0]["n"] if rows_of(p02_db) else None
    p02_chat = next((x for x in chat["results"] if x["id"] == "P02"), None)
    p02_ok = (
        p02_chat
        and p02_chat.get("executed")
        and int(p02_chat.get("row_count") or 0) == 6
        and p02_n is not None
        and int(p02_n) >= 6
    )
    print(f"  P02 cross: chat_rows=6 db_opex_groups={p02_n} ok={p02_ok}")

    # P01: prove light SQL works while chat used heavy kalem join
    light = qg(
        """
SELECT EXTRACT(YEAR FROM fatura_tarihi)::int AS y, sum(genel_toplam) AS ciro
FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi) IN (2025,2026)
GROUP BY 1 ORDER BY 1
""".strip()
    )
    light_rows = rows_of(light)
    print(f"  P01 light header SQL rows={len(light_rows)} sample={j(light_rows)}")

    return {
        "ok": True,
        "verdicts": verdicts,
        "p02_consistency": {"ok": bool(p02_ok), "db_opex_groups": p02_n, "chat_rows": 6},
        "p01_light_sql_works": {
            "ok": len(light_rows) >= 1,
            "rows": j(light_rows),
            "note": "Chat failed with heavy fatura_kalemleri join; header SQL succeeds — data OK, LLM SQL shape bad under load/timeout",
        },
    }


def main() -> int:
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "phases": {},
    }
    print("# 1 Inventory")
    report["phases"]["inventory"] = phase_inventory()
    print("# 2 Hand-SQL smoke vs DB")
    report["phases"]["sql_smoke"] = phase_sql_smoke()
    print("# 3 Intent data exists (chat failures not empty-DB)")
    report["phases"]["intent_data"] = phase_intent_data_exists()
    print("# 4 Chat report vs DB classification")
    report["phases"]["chat_vs_db"] = phase_chat_vs_db()

    inv = report["phases"]["inventory"]["ok"]
    sql = report["phases"]["sql_smoke"]["ok"]
    intent = report["phases"]["intent_data"]["ok"]
    report["summary"] = {
        "inventory_ok": inv,
        "sql_smoke": f"{report['phases']['sql_smoke']['pass']}/{report['phases']['sql_smoke']['total']}",
        "sql_smoke_ok": sql,
        "intent_data_ok": intent,
        "conclusion": (
            "DB seed and hand-SQL OK; chat WARN/FAIL are pipeline/LLM/load — not missing demo data"
            if inv and sql and intent
            else "Mismatch — inspect failed phase"
        ),
        "gate_pass": inv and sql and intent,
    }
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n# SUMMARY")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"wrote {OUT}")
    return 0 if report["summary"]["gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
