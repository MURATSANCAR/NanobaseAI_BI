"""Dönem ifadesi kabul listesi (donem_kabul.json): kuralı verilen bugüne göre somut aralığa çevirir.

  python donem_kabul.py --today 2026-10-01            # aralıkları bas
  python donem_kabul.py --self-check                   # bugün=2026-10-01 için kural == elle yazılmış örnek
  python donem_kabul.py --live --out DIR [--only DK01]  # yalnız test sunucusu: API planındaki dönemleri karşılaştır

Ürün ayrıştırıcısı import edilmez; beklenen aralık bu dosyadaki kuraldan bağımsız hesaplanır. --live API'ye soru
başına bir istek gönderir (uzun koşu değil, 37 soru); koordinatör çalıştırır.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys

SPEC = Path(__file__).with_name("donem_kabul.json")


def add_months(d, n):
    m = d.year * 12 + d.month - 1 + n
    y, m = divmod(m, 12)
    m += 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def month_start(y, m):
    return date(y + (m - 1) // 12, (m - 1) % 12 + 1, 1)


def materialize(rule, today):
    """Kural → [[başlangıç, bitiş)] listesi; 'NETLESTIRME' ya da {'as_of','end_exclusive'}."""
    k = rule["kind"]
    y = today.year + rule.get("year_offset", 0)
    if "year" in rule:
        y = rule["year"]
    iso = lambda a, b: [a.isoformat(), b.isoformat()]
    tomorrow = today + timedelta(days=1)
    if k == "clarify":
        return "NETLESTIRME"
    if k == "calendar":
        unit, off = rule["unit"], rule.get("offset", 0)
        if unit == "year":
            return [iso(date(today.year + off, 1, 1), date(today.year + off + 1, 1, 1))]
        if unit == "month":
            a = add_months(date(today.year, today.month, 1), off)
            return [iso(a, add_months(a, 1))]
        if unit == "quarter":
            q0 = month_start(today.year, (today.month - 1) // 3 * 3 + 1)
            a = add_months(q0, 3 * off)
            return [iso(a, add_months(a, 3))]
        if unit == "week":
            a = today - timedelta(days=today.weekday()) + timedelta(weeks=off)
            return [iso(a, a + timedelta(days=7))]
        if unit == "day":
            a = today + timedelta(days=off)
            return [iso(a, a + timedelta(days=1))]
    if k == "quarter_n":
        a = month_start(y, (rule["n"] - 1) * 3 + 1)
        return [iso(a, add_months(a, 3))]
    if k == "day_range":
        a = date(y, rule["month"], rule["from_day"])
        return [iso(a, date(y, rule["month"], rule["to_day"]) + timedelta(days=1))]
    if k == "month_range":
        return [iso(month_start(y, rule["from"]), month_start(y, rule["to"] + 1))]
    if k == "first_n_months":
        return [iso(date(y, 1, 1), month_start(y, rule["n"] + 1))]
    if k == "half":
        a = month_start(y, 1 + 6 * (rule["n"] - 1))
        return [iso(a, add_months(a, 6))]
    if k == "same_period_last_year":
        return [iso(date(today.year, 1, 1), today), iso(date(today.year - 1, 1, 1), add_months(today, -12))]
    if k == "rolling_months":
        end = tomorrow if rule.get("include_today") else today
        return [iso(add_months(today, -rule["n"]), end)]
    if k == "rolling_days":
        end = tomorrow if rule.get("include_today", True) else today
        return [iso(end - timedelta(days=rule["n"]), end)]
    if k == "last_n_years_month":
        m = rule["month"]
        last_year = today.year if month_start(today.year, m + 1) <= today else today.year - 1
        return [iso(month_start(yy, m), month_start(yy, m + 1)) for yy in range(last_year - rule["n"] + 1, last_year + 1)]
    if k == "since":
        a = date(rule["year"], 1, 1) if "year" in rule and "month" not in rule else month_start(y, rule["month"])
        return [iso(a, tomorrow if rule.get("include_today", True) else today)]
    if k == "as_of_month_end":
        end = month_start(y, rule["month"] + 1)
        return {"as_of": (end - timedelta(days=1)).isoformat(), "end_exclusive": end.isoformat()}
    if k == "month_named":
        return [iso(month_start(y, rule["month"]), month_start(y, rule["month"] + 1))]
    if k == "ytd":
        return [iso(date(today.year, 1, 1), tomorrow)]
    if k == "same_day_years_ago":
        a = add_months(today, -12 * rule["years"])
        return [iso(a, a + timedelta(days=1))]
    if k == "month_then_next_january":
        a = month_start(y, rule["month"])
        return [iso(a, add_months(a, 1)), iso(date(a.year + 1, 1, 1), date(a.year + 1, 2, 1))]
    raise ValueError("tanımsız kural: " + k)


def expected(today, spec=None):
    spec = spec or json.loads(SPEC.read_text(encoding="utf-8"))
    return [dict(id=c["id"], ifade=c["ifade"], soru=c["soru"], beklenen=materialize(c["kural"], today),
                 kirilim=c.get("kirilim")) for c in spec["cases"]]


def self_check():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    today = date.fromisoformat(spec["referenceToday"])
    bad = []
    for c in spec["cases"]:
        got = materialize(c["kural"], today)
        if got != c["ornek_2026_10_01"]:
            bad.append({"id": c["id"], "kural": got, "ornek": c["ornek_2026_10_01"]})
    return bad


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--today", default=None)
    p.add_argument("--self-check", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--out")
    p.add_argument("--only", default="")
    p.add_argument("--base", default="http://127.0.0.1:8795")
    a = p.parse_args()
    if a.self_check:
        bad = self_check()
        print(json.dumps({"selfCheck": "PASS" if not bad else "FAIL", "mismatches": bad}, ensure_ascii=False, indent=1))
        return 1 if bad else 0
    if not a.live:
        today = date.fromisoformat(a.today) if a.today else date.today()
        print(json.dumps({"today": today.isoformat(), "cases": expected(today)}, ensure_ascii=False, indent=1))
        return 0
    if sys.platform != "linux" or not a.out or not a.base.startswith("http://127.0.0.1:"):
        raise SystemExit("--live yalnız test sunucusunda, geri döngü API ve --out ile")
    from zoneinfo import ZoneInfo
    from datetime import datetime
    today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
    if a.today and a.today != today.isoformat():
        raise SystemExit("--today canlı İstanbul günüyle aynı olmalı; göreli ifadeler kayar")
    sys.path.insert(0, str(Path(__file__).parent))
    from routing_eval import live_session
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise SystemExit("Boş kanıt klasörü kullanın")
    call, close = live_session(a.base)
    results = []
    try:
        for case in expected(today):
            if a.only and case["id"] not in a.only.split(","):
                continue
            answer = call("/api/v1/ask", {"question": case["soru"], "sampleSize": 3})
            plan = (answer.get("semantic") or {}).get("plan") or {}
            got = [list(x) for x in plan.get("periods") or []]
            want = case["beklenen"]
            if want == "NETLESTIRME":
                status = "PASS" if answer.get("type") == "CLARIFICATION" else "FAIL"
            elif isinstance(want, dict):
                report = plan.get("logo_report") or {}
                status = "PASS" if report.get("as_of") in (want["as_of"], want["end_exclusive"]) else "INCELE"
            else:
                status = "PASS" if sorted(got) == sorted(want) else "FAIL"
            item = dict(case, apiPeriods=got, answerType=answer.get("type"), status=status)
            results.append(item)
            print(json.dumps({k: item[k] for k in ("id", "ifade", "beklenen", "apiPeriods", "status")}, ensure_ascii=False), flush=True)
    finally:
        removed = close()
        (out / "report.json").write_text(json.dumps({"today": today.isoformat(), "sessionsDeleted": removed,
            "counts": {s: sum(r["status"] == s for r in results) for s in ("PASS", "FAIL", "INCELE")}, "results": results},
            ensure_ascii=False, indent=1))
    return 1 if any(r["status"] == "FAIL" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
