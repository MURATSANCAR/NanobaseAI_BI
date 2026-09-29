"""Basın ilişkileri, kurumsal ilişkiler, etkinlikler, okur topluluğu, reklam, katalog ve bülten ekran uçlarının süresi —
hazır cevap atlanarak (`X-Data-Refresh: 1`), test sunucusunda (2026-09-29 hız işi).

Hedef: her uç < 1,5 sn. Önce ısınma turu (başlıksız): köprü yeni başladıysa ve açılış ısıtması (20 sn sonra) henüz
bitmediyse ilk istek kaynağı bekler — bu süre hedefe sayılmaz, ayrıca yazılır. Sonra her uç iki kez `X-Data-Refresh: 1`
ile ölçülür (ikincisi «Verileri yenile»ye art arda basmak). Rakam denetimi: medya kişilerinde bellekteki cevap ile
ekranın «Yenile»si (`yenile=true`, CRM'i bekler) aynı kişi sayısını ve ilk sayfayı vermeli. Yazma yok (yalnız GET);
kişi verisi yazdırılmaz (yalnız sayı ve süre).

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi). İsteğe bağlı HEDEF_SN (vars. 1.5).
Kullanım: python olcum.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
LIMIT = float(os.environ.get("HEDEF_SN", "1.5"))

PATHS = [
    "/api/v1/pr/contacts",
    "/api/v1/public-affairs/crm/roles",
    "/api/v1/public-affairs/report",
    "/api/v1/events/type-map",
    f"/api/v1/events/calendar?year={date.today().year}",
    "/api/v1/okur/overview",
    "/api/v1/ads/overview",
    "/api/v1/catalog-newsletter/report",
]


def get(path: str, fresh: bool) -> tuple[int, float, object]:
    headers = {"Cookie": COOKIE}
    if fresh:
        headers["X-Data-Refresh"] = "1"
    req = urllib.request.Request(BASE + path, headers=headers)
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            raw, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    took = time.monotonic() - t
    try:
        body = json.loads(raw) if raw[:1] in (b"{", b"[") else None
    except ValueError:
        body = None
    return status, took, body


def main() -> int:
    for p in PATHS:
        s, took, _ = get(p, False)
        print(f"ısınma {p}: {s} · {took:.1f} sn", flush=True)
    bad = 0
    for p in PATHS:
        for i in (1, 2):
            s, took, body = get(p, True)
            err = (body or {}).get("kaynaklar", {}).get("error") if isinstance(body, dict) else None
            ok = s == 200 and took < LIMIT and not err
            bad += 0 if ok else 1
            print(f"{'GEÇTİ' if ok else 'KALDI'} {p} ({i}): {s} · {took:.2f} sn{' · sorgu bilgisi: ' + err if err else ''}",
                  flush=True)
    # rakam: bellekteki medya kişileri = CRM'i bekleyen «Yenile»
    _, _, a = get("/api/v1/pr/contacts", False)
    _, took, b = get("/api/v1/pr/contacts?yenile=true", False)
    same = isinstance(a, dict) and isinstance(b, dict) and a.get("all") == b.get("all") and a.get("total") == b.get("total") \
        and [x.get("key") for x in a.get("items") or []] == [x.get("key") for x in b.get("items") or []]
    bad += 0 if same else 1
    print(f"{'GEÇTİ' if same else 'KALDI'} medya kişileri bellek = CRM: {a.get('all') if isinstance(a, dict) else '?'} kişi "
          f"(«Yenile» {took:.1f} sn)")
    print(f"-- {len(PATHS) * 2 + 1 - bad} geçti, {bad} kaldı (hedef < {LIMIT} sn)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
