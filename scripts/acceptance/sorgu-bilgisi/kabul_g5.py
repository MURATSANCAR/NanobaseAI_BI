"""Sorgu bilgisi kabulü — G5 (e-ticaret, kampanyalar, e-ticaret müşterileri, kanallar, Trendyol, Amazon, SEO & GEO).

Test sunucusunda yan port köprüsü açıkken (yalnız okuma; hiçbir yere yazmaz). Ortam `kabul.py` ile aynı:
BASE, COOKIE, SEMANTIC_CONNECTION_FILE, SEMANTIC_CRM_CONNECTION_FILE, SEMANTIC_STORE_DSN, PYTHONPATH=<ağaç>/backend.
Kullanım: python kabul_g5.py [--skip-heavy] [--only eticaret,kampanya,commerce,kanallar,pazaryeri,seo]
Önce gece okumalarını bir kez elle koşturun ki «asıl sorgu» (köken) kayıtları dolsun: e-ticaret /run-due,
kampanya /run-due, kanallar /run-due, trendyol /run-due, amazon /run-due.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import kabul as KB  # noqa: E402

MODULES = ("eticaret", "kampanya", "commerce", "kanallar", "pazaryeri", "seo")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = [x for x in a.only.split(",") if x] or list(MODULES)
    for name in only:
        mod = importlib.import_module(f"g5_{name}")
        print(f"== {name}", flush=True)
        try:
            mod.kabul(not a.skip_heavy)
        except Exception as e:  # noqa: BLE001 — bir modülün hatası öbürlerini durdurmaz
            KB.check(f"{name} kabulü", False, str(e)[:300])
    ok = sum(1 for _, s, _ in KB.results if s == "GEÇTİ")
    bad = sum(1 for _, s, _ in KB.results if s == "KALDI")
    warn = sum(1 for _, s, _ in KB.results if s == "UYARI")
    print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
