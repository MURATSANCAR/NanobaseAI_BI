#!/usr/bin/env python3
"""Timaş Finans Copilot regresyon testi: korpustaki soruları köprüye sorar, dönen SQL'i çalıştırır,
sonuçları ham T-SQL gerçek değerleriyle (artifacts/timas/complex-truth.json) karşılaştırır.
Gece zamanlayıcısı bunu koşar; hata varsa çıkış kodu 1 → watchdog/journal görür.

  python3 timas-copilot-eval.py --bridge http://127.0.0.1:8794 --corpus timas-copilot-complex.json \
      --truth complex-truth.json --out /data/nanobaseai/bi/logs/copilot-eval-YYYYMMDD.json
"""
from __future__ import annotations
import argparse, json, sys, time, urllib.request
from pathlib import Path


def post(base: str, path: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def nums(row: dict) -> list[float]:
    return [float(v) for v in row.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]


def close(a: float, b: float, tol: float = 0.005) -> bool:
    if a == b:
        return True
    if b == 0:
        return abs(a) < 1e-6
    return abs(a - b) / max(abs(a), abs(b)) <= tol


def labels(row: dict) -> set[str]:
    return {str(v).strip().lower() for v in row.values() if isinstance(v, str)}


def compare(rows: list[dict], truth: list[dict]) -> tuple[bool, str]:
    """Satır sayısı eşit olmalı; etiketle eşleşen ilk 10 gerçek satırın sayısal değerleri sonuçta bulunmalı."""
    if len(rows) != len(truth):
        return False, "satır sayısı %d ≠ gerçek %d" % (len(rows), len(truth))
    misses = 0
    checked = 0
    for t in truth[:10]:
        tl = labels(t)
        cand = [r for r in rows if tl and (tl & labels(r))] or rows[:1]
        rn = [x for r in cand for x in nums(r)]
        for tv in nums(t):
            if abs(tv) < 13:  # ay/yıl sıra numaraları vb. karşılaştırma dışı
                continue
            checked += 1
            if not any(close(rv, tv) or close(rv, tv * 100) or close(rv * 100, tv) for rv in rn):
                misses += 1
    if checked and misses / checked > 0.15:
        return False, "sayısal uyumsuzluk %d/%d" % (misses, checked)
    return True, "eşleşti (%d değer)" % checked


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default="http://127.0.0.1:8794")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    corpus = json.loads(Path(a.corpus).read_text(encoding="utf-8"))
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8"))
    results, fails = [], 0
    for c in corpus:
        t0 = time.time()
        rec = {"id": c["id"], "q": c["q"]}
        try:
            r = post(a.bridge, "/api/v1/ask", {"question": c["q"], "sampleSize": 100}, a.timeout)
            rec.update({k: r.get(k) for k in ("type", "sql", "rowCount", "repairs", "timings")})
            if r.get("sql"):
                rr = post(a.bridge, "/api/v1/run_sql", {"sql": r["sql"], "limit": 200}, 300)
                ok, why = compare(rr["records"], truth.get(c["id"], []))
                rec["ok"], rec["why"] = ok, why
            else:
                rec["ok"], rec["why"] = False, "SQL üretilmedi: %s" % (r.get("explanation") or r.get("type"))
        except Exception as e:  # noqa: BLE001
            rec["ok"], rec["why"] = False, "hata: %s" % str(e)[:200]
        rec["wall_s"] = round(time.time() - t0, 1)
        fails += 0 if rec["ok"] else 1
        print("%s %-5s %5.1fs %s" % (c["id"], "OK" if rec["ok"] else "FAIL", rec["wall_s"], rec["why"]), flush=True)
        results.append(rec)
    summary = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "total": len(results), "passed": len(results) - fails, "failed": fails, "results": results}
    Path(a.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("%d/%d geçti → %s" % (summary["passed"], summary["total"], a.out))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
