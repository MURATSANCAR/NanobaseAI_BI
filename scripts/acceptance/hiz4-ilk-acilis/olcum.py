"""Hız 4 — ilk açılış: kişiye ait hazır cevap yokken ekran uçlarının süresi (test sunucusunda, yan köprüde).

Hazır cevap anahtarı kişi + yol + sorgudur; her istek sorguya benzersiz `_olc=<n>` ekler, böylece hazır cevap katmanı
her seferinde uca iner (yeni kişinin ilk açılışı). `X-Data-Refresh` GÖNDERİLMEZ: «Verileri yenile» değil, ilk açılış
ölçülür. Yalnız GET; kişi verisi yazdırılmaz (durum, süre, satır sayısı).

Ortam: BASE (vars. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), HEDEF_SN (vars. 1.5),
TUR (vars. 2: aynı uç art arda kaç kez), ESZAMANLI=1 ise ekranın yaptığı gibi hepsi aynı anda bir tur daha.
Kullanım: python olcum.py [yol-süzgeci]
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
LIMIT = float(os.environ.get("HEDEF_SN", "1.5"))
TUR = int(os.environ.get("TUR", "2"))

_t = date.today()
PATHS = [
    f"/api/v1/marketing/new-books?frm={_t.isoformat()}&to={(_t + timedelta(days=120)).isoformat()}&sahip=ben&page=0",
    "/api/v1/okur/meta",
    "/api/v1/me/profile",
    "/api/v1/model-quality/scorecard?days=30",
    "/api/v1/semantic/concepts?status=CERTIFIED&limit=5000",
    f"/api/v1/pr/home?ay={_t.isoformat()[:7]}",
    "/api/v1/editorial/production/overview",
    f"/api/v1/channels/matrix?yil={_t.year}&page=0",
    "/api/v1/channels/trendyol/weekly",
    "/api/v1/events/me/agenda",
    "/api/v1/financial-audit/runs",
    "/api/v1/channels/trendyol/overview",
]
_n = [int(time.time() * 1000)]


def get(path: str) -> tuple[int, float, object]:
    _n[0] += 1
    url = BASE + path + ("&" if "?" in path else "?") + f"_olc={_n[0]}"
    req = urllib.request.Request(url, headers={"Cookie": COOKIE})
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            raw, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    took = time.monotonic() - t
    try:
        body = json.loads(raw) if raw[:1] in (b"{", b"[") else None
    except ValueError:
        body = None
    return status, took, body


def size(body: object) -> str:
    if not isinstance(body, dict):
        return ""
    for k in ("items", "rows", "books"):
        if isinstance(body.get(k), list):
            return f" · {k}={len(body[k])}" + (f"/{body['total']}" if "total" in body else "")
    return ""


def main() -> int:
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    paths = [p for p in PATHS if want in p]
    bad = 0
    for p in paths:
        for i in range(1, TUR + 1):
            s, took, body = get(p)
            err = (body or {}).get("kaynaklar", {}).get("error") if isinstance(body, dict) else None
            ok = s == 200 and took < LIMIT and not err
            bad += 0 if ok else 1
            print(f"{'GEÇTİ' if ok else 'KALDI'} {p} ({i}): {s} · {took:.2f} sn{size(body)}"
                  f"{' · sorgu bilgisi: ' + err if err else ''}", flush=True)
    if os.environ.get("ESZAMANLI") == "1":
        t0 = time.monotonic()
        with ThreadPoolExecutor(len(paths)) as ex:
            res = list(ex.map(get, paths))
        for p, (s, took, _b) in zip(paths, res):
            print(f"eşzamanlı {p}: {s} · {took:.2f} sn", flush=True)
        print(f"eşzamanlı tur: {time.monotonic() - t0:.2f} sn")
    print(f"-- {len(paths) * TUR - bad} geçti, {bad} kaldı (hedef < {LIMIT} sn)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
