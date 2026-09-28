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
import time
import urllib.error
import urllib.parse
import urllib.request


def call(base: str, method: str, path: str, cookie: str, body: object | None = None, timeout: float = 120) -> tuple[int, object]:
    """(durum, gövde). Süre her satırda yazılır; zaman aşımı 0 durumuyla döner (betik düşmez, kayıt ayrıca aranır)."""
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"cookie": cookie, "Content-Type": "application/json",
                                          "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            out = e.code, json.loads(raw)
        except ValueError:
            out = e.code, raw[:300]
    except (TimeoutError, urllib.error.URLError) as e:   # socket.timeout = TimeoutError (3.10+)
        out = 0, f"zaman aşımı / bağlantı: {e}"
    print(f"    {method} {path}: {time.monotonic() - t0:.2f} sn")
    return out


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
        # 403 her zaman FORBIDDEN koduyla (ön yüz başka kodlu 403'ü «oturum düştü» sayar).
        if st == 403 and not (isinstance(body, dict) and (body.get("detail") or {}).get("code") == "FORBIDDEN"):
            good = False
            print("    403 FORBIDDEN koduyla dönmedi:", body)
        ok &= good
        print(f"[{'BAŞARILI' if good else 'BAŞARISIZ'}] {m} {p} → {st} (beklenen {want})")
    ids: dict[str, list[str]] = {"visits": [], "plans": [], "overrides": []}
    if a.write_one:
        marker = f"kabul denemesi — silinecek {int(time.time())}"
        t0 = time.monotonic()
        st, v = call(a.bridge, "POST", "/api/v1/field/visits", ck, {"hedef": code, "notu": marker, "gizli": True})
        took = time.monotonic() - t0
        print(f"tek geçerli not: {st} ({took:.2f} sn; beklenen 201 ve birkaç saniye — yavaşsa köprü günlüğünde "
              f"«field: ziyaret notu yavaş» satırı hangi adımın beklediğini yazar)")
        if st != 201:
            # Zaman aşımında kayıt oluştu mu? Oluştuysa kimliği temizlik listesine girer (yarım bırakılmaz).
            st_l, lst = call(a.bridge, "GET", f"/api/v1/field/visits?musteri={urllib.parse.quote(code)}", ck)
            hit = [x for x in ((lst or {}).get("items") or []) if x.get("notu") == marker] if isinstance(lst, dict) else []
            print("  kayıt sonradan arandı:", st_l, "bulundu" if hit else "yok")
            ids["visits"] += [x["id"] for x in hit]
            ok = False
        else:
            ids["visits"].append(v["id"])
            ok &= took < 10
            st2, v2 = call(a.bridge, "PATCH", f"/api/v1/field/visits/{v['id']}", ck, {"ton": "notr"})
            print("düzenleme:", st2, v2.get("ton") if isinstance(v2, dict) else v2)
            ok &= st2 == 200
    with open(a.ids, "w") as fh:
        json.dump(ids, fh)
    print("silinecek kimlikler:", a.ids, ids)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
