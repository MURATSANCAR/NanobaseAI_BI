"""Grup 3 (Lojistik ve İK) sorgu bilgisi kabulünün koşucusu (test sunucusu, yan port köprüsü; yalnız okuma).

Sırayla: depo ve stok (g3_stock), tedarik (g3_supply), kargo (g3_shipping), İK (g3_hr). Her biri `kabul.py`'nin ortak
denetimlerini (K1 kaynaksız rakam yok, K2 tutarlılık / yer tutucu / sır / teknoloji adı, K3 her SQL gerçekten koşar) ve
kendi doğrudan SQL referanslarını uygular. Bir modül hata verirse diğerleri yine koşar.

Ortam `kabul.py` ile aynı: BASE, COOKIE, SEMANTIC_CONNECTION_FILE, SEMANTIC_CRM_CONNECTION_FILE, SEMANTIC_STORE_DSN,
PYTHONPATH=<aday ağaç>/backend. Kullanım (bu klasörde): python g3.py [--skip-heavy] [--only stok,tedarik,kargo,ik]
"""
from __future__ import annotations

import argparse
import traceback

import kabul as KB

MODULES = (("stok", "g3_stock"), ("tedarik", "g3_supply"), ("kargo", "g3_shipping"), ("ik", "g3_hr"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    for key, mod in MODULES:
        if only and key not in only:
            continue
        print(f"== {key}", flush=True)
        try:
            __import__(mod).main(not a.skip_heavy)
        except Exception as e:  # noqa: BLE001 — bir modülün hatası diğerlerini durdurmaz
            KB.check(f"{key} koşusu", False, f"{type(e).__name__}: {str(e)[:200]}")
            traceback.print_exc()
    ok = sum(1 for _, s, _ in KB.results if s == "GEÇTİ")
    bad = sum(1 for _, s, _ in KB.results if s == "KALDI")
    warn = sum(1 for _, s, _ in KB.results if s == "UYARI")
    print(f"== G3: {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
