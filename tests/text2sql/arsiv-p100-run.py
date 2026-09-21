"""Arşiv P100 kabulü: 100 soru köprüye sorulur, köprünün çalıştırdığı SQL doğrudan veritabanında koşulur;
satır (grup) sayısı ve ölçü toplamı, arşivdeki SQL'in şablonundan kurulan bağımsız referansla karşılaştırılır.

Referans şablonu (arşivdeki 100 SQL'in ortak biçimi): STLINE ⋈ INVOICE ⋈ ITEMS, LEFT UNITSETL/SHIPINFO/SLSMAN/
PAYPLANS/CLCARD; CANCELLED=0, LINETYPE=0, ay aralığı; kanal perakende TRCODE 7 (iade 2), toptan 8 (iade 3),
belirtilmemişse 7,8 (iade 2,3); ölçü adet SUM(AMOUNT) / tutar SUM(LINENET) / satır COUNT / net ±LINENET.
2026 → firma 411 (VW_411_SHIPINFO), 2021–25 → firma 211 (LG_211_SHIPINFO) — arşivdeki SQL'lerle aynı.

Kullanım (sunucuda): SEMANTIC_CALLER_TOKEN=… python arsiv-p100-run.py arsiv-p100.jsonl [--workers 4] [--url …]
"""
from __future__ import annotations

import json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

AYLAR = {"ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6, "temmuz": 7,
         "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12}


def _arg(name, default=""):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def reference_sql(q: str) -> tuple[str, str]:
    low = q.lower()
    m = re.search(r"(" + "|".join(AYLAR) + r")\s+(20\d\d)", low)
    mon, year = AYLAR[m.group(1)], int(m.group(2))
    start = f"{year}-{mon:02d}-01"
    end = f"{year + (mon == 12)}-{(mon % 12) + 1:02d}-01"
    sales, ret = ("7", "2") if "perakende" in low else ("8", "3") if "toptan" in low else ("7, 8", "2, 3")
    if "net satış tutarı" in low:
        kind, measure, codes = "net", "SUM(CASE WHEN S.TRCODE IN (7, 8) THEN S.LINENET ELSE -S.LINENET END)", f"{ret}, {sales}"
    elif "satış satırı sayısı" in low:
        kind, measure, codes = "satir", "COUNT(S.LOGICALREF)", sales
    elif "satılan adet" in low:
        kind, measure, codes = "adet", "SUM(S.AMOUNT)", sales
    else:
        kind, measure, codes = "tutar", "SUM(S.LINENET)", sales
    f = "411" if year >= 2026 else "211"
    ship = f"VW_{f}_SHIPINFO" if f == "411" else f"LG_{f}_SHIPINFO"
    sql = f"""SELECT COUNT(*) AS grup, SUM(CAST(olcu AS float)) AS toplam FROM (
SELECT U.NAME a, SH.CITY b, SM.DEFINITION_ c, PP.DEFINITION_ d, IT.NAME e, CL.DEFINITION_ g, {measure} AS olcu
FROM LG_{f}_01_STLINE S JOIN LG_{f}_01_INVOICE I ON S.INVOICEREF = I.LOGICALREF
LEFT JOIN LG_{f}_UNITSETL U ON S.UOMREF = U.LOGICALREF
LEFT JOIN {ship} SH ON I.SHIPINFOREF = SH.LOGICALREF
LEFT JOIN LG_SLSMAN SM ON I.SALESMANREF = SM.LOGICALREF
LEFT JOIN LG_{f}_PAYPLANS PP ON PP.LOGICALREF = COALESCE(NULLIF(S.PAYDEFREF, 0), I.PAYDEFREF)
JOIN LG_{f}_ITEMS IT ON S.STOCKREF = IT.LOGICALREF
LEFT JOIN LG_{f}_CLCARD CL ON I.CLIENTREF = CL.LOGICALREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE IN ({codes}) AND S.DATE_ >= '{start}' AND S.DATE_ < '{end}'
GROUP BY U.NAME, SH.CITY, SM.DEFINITION_, PP.DEFINITION_, IT.NAME, CL.DEFINITION_) x"""
    return kind, sql


def ask(url: str, token: str, q: str) -> dict:
    req = urllib.request.Request(url + "/api/v1/ask", data=json.dumps({"question": q}).encode(),
                                 headers={"X-Semantic-Caller": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def main() -> int:
    sys.path.insert(0, _arg("--backend", "/data/nanobaseai/bi/frontend/backend"))
    from semantic_layer.profiler.connectors import connector_from_file
    conn_file = os.environ.get("SEMANTIC_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
    url, token = _arg("--url", "http://127.0.0.1:8795"), os.environ["SEMANTIC_CALLER_TOKEN"]
    cases = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]

    def one(case):
        c = connector_from_file(conn_file)
        kind, ref_sql = reference_sql(case["soru"])
        out = {"id": case["id"], "soru": case["soru"], "tur": kind}
        t0 = time.time()
        try:
            ref = c.execute(ref_sql, 10)[1][0]
            out["ref_grup"], out["ref_toplam"] = int(ref["grup"]), float(ref["toplam"] or 0)
        except Exception as ex:  # noqa: BLE001
            out["karar"], out["neden"] = "REFERANS_HATASI", str(ex)[:200]
            return out
        try:
            ans = ask(url, token, case["soru"])
        except Exception as ex:  # noqa: BLE001
            out["karar"], out["neden"] = "KÖPRÜ_HATASI", str(ex)[:200]
            return out
        out["sure_sn"] = round(time.time() - t0, 1)
        out["sql"] = ans.get("physicalSql") or ans.get("sql") or ""
        out["yol"] = "model" if "yorum:" in (ans.get("sql") or "") else "katalog"
        if not ans.get("physicalSql"):
            out["karar"], out["neden"] = "CEVAP_YOK", str(ans.get("explanation") or ans.get("type"))[:300]
            return out
        body = re.sub(r"(?is)\s+ORDER\s+BY\s+[^()]*$", "", out["sql"].strip().rstrip(";"))
        out["top_var"] = bool(re.search(r"(?i)\bSELECT\s+TOP\b", body))
        try:
            rows = c.execute(body, 5_000_000)[1]
        except Exception as ex:  # noqa: BLE001
            out["karar"], out["neden"] = "SQL_HATASI", str(ex)[:200]
            return out
        out["grup"] = len(rows)
        nums: dict[str, float] = {}
        for r in rows:
            for k, v in r.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    nums[k] = nums.get(k, 0.0) + float(v)
        out["toplamlar"] = nums
        want = out["ref_toplam"]
        tol = max(0.5, abs(want) * 0.0005)
        match = [k for k, v in nums.items() if abs(v - want) <= tol]
        dims = [k for k in (rows[0] if rows else {}) if k not in nums]
        out["boyut_sayisi"] = len(dims)
        if match and out["grup"] == out["ref_grup"]:
            out["karar"] = "DOĞRU"
        elif match:
            out["karar"], out["neden"] = "TOPLAM_DOĞRU_GRUP_FARKLI", f"grup {out['grup']} ≠ {out['ref_grup']} (boyut {len(dims)})"
        else:
            shown = ", ".join(f"{k}: {v:,.2f}" for k, v in nums.items())
            out["karar"], out["neden"] = "YANLIŞ", f"toplamlar {{{shown}}} ≠ ref {want:,.2f}; grup {out['grup']}/{out['ref_grup']}"
        return out

    results = []
    with ThreadPoolExecutor(int(_arg("--workers", "4"))) as pool:
        for r in pool.map(one, cases):
            results.append(r)
            print(f"{r['id']} {r['karar']:<26} {r.get('tur', ''):<6} {r.get('yol', '')} {r.get('neden', '')[:150]}", flush=True)
    json.dump(results, open(_arg("--out", "arsiv-p100-sonuc.json"), "w"), ensure_ascii=False, indent=1)
    from collections import Counter
    print("ÖZET:", dict(Counter(r["karar"] for r in results)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
