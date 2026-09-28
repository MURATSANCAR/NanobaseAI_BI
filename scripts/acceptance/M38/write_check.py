#!/usr/bin/env python3
"""M38 yazma uçları kabulü (test sunucusunda; AGENTS.md «yazma uçları gerçek veriyle denenmez; önce boş gövde»).

1. Boş/geçersiz gövdeyle aksiyon yaz → 422; olmayan aksiyon PATCH → 404; geçersiz bulgu işareti → 422.
2. Tek aksiyon yazılır (kimlik dosyaya), güncellenir (yapıldı + sonuç notu), liste ve cari ayrıntısında görünür.
3. Tek açık bulgu «CRM'de düzeltildi» işaretlenir, sonra «acik»a geri alınır (önceki durumu dosyaya yazılır).
Hiçbir CRM ya da Logo yazması yoktur. Bitince cleanup.py aynı kimlik dosyasıyla aksiyonu, değişiklik kaydı satırlarını
siler ve bulgunun işaret alanlarını eski hâline getirir.

  set -a; . /etc/nanobase/semantic-bridge.env; set +a
  MUSTERI_COOKIE='timas_session=…' python3 scripts/acceptance/M38/write_check.py --ids /tmp/claude-<oturum>/m38-ids.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def call(base: str, method: str, path: str, cookie: str, body=None) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"cookie": cookie, **({"Content-Type": "application/json"} if data else {})})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge", default="http://127.0.0.1:8795")
    ap.add_argument("--ids", required=True)
    a = ap.parse_args()
    ck = os.environ["MUSTERI_COOKIE"]
    ids: dict = {"actions": [], "findings": []}
    checks = []

    def ok(name: str, cond: bool, ev: object) -> None:
        checks.append({"kontrol": name, "durum": "BAŞARILI" if cond else "BAŞARISIZ", "kanit": ev})
        print(("[BAŞARILI] " if cond else "[BAŞARISIZ] ") + name)

    s, lst = call(a.bridge, "GET", "/api/v1/musteri/accounts?risk=riskli&size=1", ck)
    if s != 200 or not lst["items"]:
        s, lst = call(a.bridge, "GET", "/api/v1/musteri/accounts?size=1", ck)
    code = lst["items"][0]["code"]
    q = urllib.parse.quote(code)
    s, _ = call(a.bridge, "POST", f"/api/v1/musteri/accounts/{q}/actions", ck, {})
    ok("boş aksiyon → 422", s == 422, s)
    s, _ = call(a.bridge, "POST", f"/api/v1/musteri/accounts/{q}/actions", ck, {"tur": "arama", "aciklama": ""})
    ok("açıklamasız aksiyon → 422", s == 422, s)
    s, _ = call(a.bridge, "PATCH", "/api/v1/musteri/actions/yok", ck, {"durum": "yapildi"})
    ok("olmayan aksiyon → 404", s == 404, s)
    s, act = call(a.bridge, "POST", f"/api/v1/musteri/accounts/{q}/actions", ck,
                  {"tur": "arama", "aciklama": "Kabul testi aksiyonu (silinecek)"})
    if s == 201:
        ids["actions"].append(act["id"])
    ok("aksiyon yazıldı", s == 201 and act["code"] == code, act if s != 201 else act["id"])
    json.dump(ids, open(a.ids, "w"))
    if s == 201:
        s, up = call(a.bridge, "PATCH", f"/api/v1/musteri/actions/{act['id']}", ck, {"durum": "yapildi", "sonucNotu": "test"})
        ok("aksiyon güncellendi", s == 200 and up["durum"] == "yapildi", s)
        s, det = call(a.bridge, "GET", f"/api/v1/musteri/accounts/{q}", ck)
        ok("cari ayrıntısında görünüyor", s == 200 and any(x["id"] == act["id"] for x in det["aksiyonlar"]), s)
    s, h = call(a.bridge, "GET", "/api/v1/musteri/health?durum=acik&size=1", ck)
    if s == 200 and h["items"]:
        f = h["items"][0]
        ids["findings"].append({"id": f["id"], "durum": f["durum"], "not": f["not"], "isaretleyen": f["isaretleyen"],
                                "isaretZamani": f["isaretZamani"]})
        json.dump(ids, open(a.ids, "w"))
        s, _ = call(a.bridge, "POST", f"/api/v1/musteri/health/{f['id']}/mark", ck, {"durum": "yanlis"})
        ok("geçersiz işaret → 422", s == 422, s)
        s, m1 = call(a.bridge, "POST", f"/api/v1/musteri/health/{f['id']}/mark", ck, {"durum": "crmde_duzeltildi"})
        ok("CRM'de düzeltildi işareti", s == 200 and m1["durum"] == "crmde_duzeltildi", s)
        s, m2 = call(a.bridge, "POST", f"/api/v1/musteri/health/{f['id']}/mark", ck, {"durum": "acik"})
        ok("işaret geri alındı", s == 200 and m2["durum"] == "acik", s)
    json.dump(ids, open(a.ids, "w"))
    print(json.dumps(checks, ensure_ascii=False, indent=1))
    return 0 if all(c["durum"] == "BAŞARILI" for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
