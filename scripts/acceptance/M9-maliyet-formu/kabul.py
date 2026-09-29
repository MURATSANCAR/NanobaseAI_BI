#!/usr/bin/env python3
"""M9 maliyet formu × TİMAŞ basım Excel'leri — Excel'le paralel hesap kabulü (test sunucusunda).

Girdi: `excel_oku.py --out formlar.json` çıktısı (her Excel sayfasının girdileri, kendi tarifesi, Excel'in sonuçları).
Her sayfa, sayfanın kendi tarifesiyle ve «Excel tarifesi» kâğıt kaynağıyla hesaplanır; 16 sonuç hücresi (F4, I5, J5,
J25, J37, J40–J42, J46, J48–J50, D39–D42) kuruş duyarlığıyla Excel'le karşılaştırılır.

    # köprü içinden (modül):
    cd <kaynak>/backend && python3 ../scripts/acceptance/M9-maliyet-formu/kabul.py formlar.json
    # gerçek uçtan (portal oturum çerezi KABUL_COOKIE'de, 15 dk'lık timasai oturumu):
    KABUL_COOKIE='__Secure-timas_session=…' python3 kabul.py formlar.json --api https://portal.nanobase.ai/timas

Yalnız hesaplar; hiçbir şey kaydetmez.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

TOL_TL = 0.01
TOL_PCT = 1e-6


def via_module(form: dict) -> dict:
    from semantic_bridge.pricing import form as F
    return F.compute(form["inputs"], form["tariff"], paper_source="tarife")


def via_api(base: str, form: dict) -> dict:
    body = json.dumps({"inputs": form["inputs"], "tariff": form["tariff"], "paperSource": "tarife"}).encode()
    req = urllib.request.Request(f"{base}/api/v1/pricing/form/calc", data=body, method="POST", headers={
        "Content-Type": "application/json", "Cookie": os.environ.get("KABUL_COOKIE", ""),
        "Origin": base.split("/timas")[0]})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("formlar")
    ap.add_argument("--api", help="portal kökü, ör. https://portal.nanobase.ai/timas")
    ap.add_argument("--out", help="sonuç JSON")
    a = ap.parse_args()
    forms = json.loads(Path(a.formlar).read_text(encoding="utf-8"))
    rows, bad = [], 0
    for f in forms:
        name = f"{f['file']} [{f['sheet']}]"
        try:
            res = via_api(a.api, f) if a.api else via_module(f)
        except Exception as e:  # noqa: BLE001
            rows.append({"form": name, "durum": "HATA", "hata": str(e)[:300]})
            bad += 1
            print(f"[HATA] {name}: {e}")
            continue
        sm = res["summary"]
        diffs = {}
        for k, want in f["excel"].items():
            got = sm.get(k)
            if want is None and got in (None, 0, 0.0):
                continue
            tol = TOL_PCT if k == "karYuzde" else TOL_TL
            if want is None or got is None or abs(float(got) - float(want)) > tol:
                diffs[k] = {"excel": want, "zeki": got}
        ok = not diffs
        bad += 0 if ok else 1
        rows.append({"form": name, "durum": "OK" if ok else "FARK", "fark": diffs, "birimMaliyet": sm.get("birimMaliyet")})
        print(f"[{'OK' if ok else 'FARK'}] {name}  birim {sm.get('birimMaliyet')} / Excel {f['excel'].get('birimMaliyet')}"
              + ("" if ok else f"  {json.dumps(diffs, ensure_ascii=False)[:500]}"))
    print(f"\n{len(forms) - bad}/{len(forms)} form Excel'le aynı (kuruş duyarlığı)")
    if a.out:
        Path(a.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
