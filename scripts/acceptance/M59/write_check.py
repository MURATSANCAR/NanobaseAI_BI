#!/usr/bin/env python3
"""M59 yazma uçları kabulü (test sunucusunda; AGENTS.md «yazma uçları gerçek veriyle denenmez» kuralına göre).

Önce her yazma ucu boş/geçersiz gövdeyle denenir (422/403 beklenir, hiçbir satır yazılmaz). `--write` verilirse bir not,
bir aksiyon ve bir kural taslağı yazılır; kimlikleri `--ids` dosyasına kaydedilir ve `cleanup.py` ile aynı iş içinde silinir.
Limit önerisi gerçek kayıt olduğu için onaylanmaz/reddedilmez; yalnız gerekçesiz ret (422) denenir.

  set -a; . /etc/nanobase/semantic-bridge.env; set +a
  DEALERS_COOKIE='timas_session=…' DEALERS_CODE=120.xx.yyy python3 scripts/acceptance/M59/write_check.py \\
      --ids /tmp/claude-<oturum>/m59-ids.json [--write]
  python3 scripts/acceptance/M59/cleanup.py --ids /tmp/claude-<oturum>/m59-ids.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request


def call(base: str, method: str, path: str, cookie: str, body: object) -> tuple[int, object]:
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body).encode("utf-8"),
                                 headers={"cookie": cookie, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default="http://127.0.0.1:8795")
    ap.add_argument("--ids", required=True)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    cookie, code = os.environ["DEALERS_COOKIE"], os.environ["DEALERS_CODE"]
    c = urllib.parse.quote(code)
    P = "/api/v1/dealers"
    checks = [
        ("POST", f"{P}/{c}/notes", {}, 422, "boş not"),
        ("POST", f"{P}/actions", {"code": code, "tur": "yanlis"}, 422, "geçersiz aksiyon türü"),
        ("POST", f"{P}/actions", {"code": code, "termin": "2026-13-45"}, 422, "geçersiz termin"),
        ("POST", f"{P}/rules", {"agirliklar": {"gecikme": 90}}, 422, "ağırlık toplamı 100 değil"),
        ("POST", f"{P}/rules", {"esikler": {"standart": {"A": 50, "B": 40, "C": 60}}}, 422, "eşikler artan değil"),
        ("POST", f"{P}/limits/yok/reject", {"note": ""}, None, "gerekçesiz ret (404 ya da 422)"),
    ]
    ok = True
    for m, path, body, want, name in checks:
        st, out = call(a.bridge, m, path, cookie, body)
        good = st in (404, 422) if want is None else st == want
        ok &= good
        print(f"[{'BAŞARILI' if good else 'BAŞARISIZ'}] {name}: {st}")
    ids: dict[str, list[str]] = {"notes": [], "actions": [], "rules": []}
    if a.write:
        st, n = call(a.bridge, "POST", f"{P}/{c}/notes", cookie, {"notu": "Kabul testi notu (silinecek)", "gizli": True})
        if st == 201:
            ids["notes"].append(n["id"])
        st2, x = call(a.bridge, "POST", f"{P}/actions", cookie, {"code": code, "tur": "arama", "notu": "Kabul testi (silinecek)"})
        if st2 == 201:
            ids["actions"].append(x["id"])
        st3, r = call(a.bridge, "POST", f"{P}/rules", cookie, {"gerekce": "Kabul testi taslağı (silinecek)"})
        if st3 == 201:
            ids["rules"].append(r["id"])
            st4, pv = call(a.bridge, "POST", f"{P}/rules/{r['id']}/preview", cookie, {})
            print(f"[{'BAŞARILI' if st4 == 200 else 'BAŞARISIZ'}] kural önizleme: {st4}", "" if st4 != 200 else f"değişen {len(pv['degisen'])}")
            ok &= st4 == 200
        good = (st, st2, st3) == (201, 201, 201)
        ok &= good
        print(f"[{'BAŞARILI' if good else 'BAŞARISIZ'}] yazma: not {st}, aksiyon {st2}, kural taslağı {st3}")
    json.dump(ids, open(a.ids, "w"))
    print("kimlikler:", a.ids, "→ cleanup.py ile silin")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
