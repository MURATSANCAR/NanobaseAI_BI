#!/usr/bin/env python3
"""M30 yazma uçları — gerçek veriyle yazmadan denetim (AGENTS.md «Yazma uçları gerçek veriyle denenmez»).

Önce geçersiz gövdeyle (422) denenir; tek bir geçerli kayıt şartsa (ziyaret notu) kimliği `--ids` dosyasına yazılır ve
`cleanup.py` o kimlikle siler (değişiklik kaydı satırı dahil). CRM'e ve Logo'ya hiçbir şey yazılmaz: uçlar yalnız köprünün
kendi tablolarına yazar.

  FIELD_COOKIE='timas_session=…' FIELD_CODE=120.xx.yyy python3 scripts/acceptance/M30/write_check.py \\
     --bridge http://127.0.0.1:8795 --ids /tmp/claude-<oturum>/m30-ids.json [--write-one]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def call(base: str, method: str, path: str, cookie: str, body: object | None = None) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"cookie": cookie, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default="http://127.0.0.1:8795")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--write-one", action="store_true", help="bir geçerli ziyaret notu yaz (kimliği silinmek üzere kaydedilir)")
    a = ap.parse_args()
    ck, code = os.environ["FIELD_COOKIE"], os.environ["FIELD_CODE"]
    cases = [
        ("POST", "/api/v1/field/visits", {"hedef": code, "planlanan": "28.09.2026"}, 422),
        ("POST", "/api/v1/field/visits", {"hedef": code, "ton": "kizgin"}, 422),
        ("POST", "/api/v1/field/visits", {"tur": "gemi", "hedef": code}, 422),
        ("POST", "/api/v1/field/payment-plans", {"code": code, "taksitSayisi": "iki"}, 422),
        ("PATCH", "/api/v1/field/payment-plans/yok", {"taksitler": []}, 404),
        ("POST", "/api/v1/field/payment-plans/yok/approve", {}, 403),   # açıkça verilen yetki yoksa 403, varsa 404
        ("POST", "/api/v1/field/overrides", {"code": code, "neden": " "}, 422),
        ("POST", "/api/v1/field/run-due?tur=gece", {}, 403),             # oturumlu kişi zamanlayıcı ucunu tetikleyemez
    ]
    ok = True
    for m, p, b, want in cases:
        st, body = call(a.bridge, m, p, ck, b)
        good = st == want or (want == 403 and st == 404 and p.endswith("/approve"))
        ok &= good
        print(f"[{'BAŞARILI' if good else 'BAŞARISIZ'}] {m} {p} → {st} (beklenen {want})")
    ids: dict[str, list[str]] = {"visits": [], "plans": [], "overrides": []}
    if a.write_one:
        st, v = call(a.bridge, "POST", "/api/v1/field/visits", ck, {"hedef": code, "notu": "kabul denemesi — silinecek", "gizli": True})
        print("tek geçerli not:", st)
        if st == 201:
            ids["visits"].append(v["id"])
            st2, v2 = call(a.bridge, "PATCH", f"/api/v1/field/visits/{v['id']}", ck, {"ton": "notr"})
            print("düzenleme:", st2, v2.get("ton") if isinstance(v2, dict) else v2)
            ok &= st2 == 200
        else:
            ok = False
    with open(a.ids, "w") as fh:
        json.dump(ids, fh)
    print("silinecek kimlikler:", a.ids, ids)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
