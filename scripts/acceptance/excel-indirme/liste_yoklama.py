"""Kimlikli uçların liste cevaplarını özetler (anahtarlar, kayıt sayısı, ilk kaydın alanları) — kabul hazırlığı, yalnız okuma."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yerinde as Y  # noqa: E402

for p in ["/api/v1/hr/engagement/surveys", "/api/v1/hr/performance/cycles", "/api/v1/readers/imports",
          "/api/v1/editorial/translation/jobs", "/api/v1/editorial/freelance/payouts", "/api/v1/royalty/runs",
          "/api/v1/budget/plans", "/api/v1/hr/learning/export/expiring.csv"]:
    st, h, b = Y.transport(p, {"Cookie": Y.COOKIE}, "GET", None)
    try:
        d = json.loads(b)
    except ValueError:
        print(p, st, b[:120]); continue
    if isinstance(d, dict):
        its = next((v for v in d.values() if isinstance(v, list)), [])
        print(p, st, "anahtarlar:", list(d)[:8], "liste:", len(its), "ilk:", {k: its[0][k] for k in list(its[0])[:8]} if its and isinstance(its[0], dict) else its[:1])
    else:
        print(p, st, type(d).__name__, len(d), d[:1])
