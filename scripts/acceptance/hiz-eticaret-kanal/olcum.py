"""E-ticaret pazar yerleri (M34), Amazon kitap listesi (M41), e-ticaret müşteri özeti (H3) ve saha «Bugün» (M30) uçlarının
süresi — hazır cevap atlanarak (`X-Data-Refresh: 1`), test sunucusunda. Yalnız GET; yazma yok, kişi verisi yazdırılmaz.

Hedef: her uç < 1,5 sn. Önce ısınma: pazar yeri okuması tabloda yoksa (bu sürümün ilk kurulumu, `timas-eticaret` gece
turu henüz koşmamış) ilk istek Logo'yu bekler — bu süre hedefe sayılmaz, ayrıca yazılır. Sonra her uç iki kez ölçülür
(ikinci ölçüm aynı süreçte bellekten). Rakam denetimi: pazar yeri özetinin toplam neti = cari satırlarının neti.

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

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
LIMIT = float(os.environ.get("HEDEF_SN", "1.5"))

PATHS = [
    "/api/v1/eticaret/marketplaces",
    "/api/v1/eticaret/marketplaces/stock-risk",
    "/api/v1/channels/amazon/books",
    "/api/v1/commerce/overview",
    "/api/v1/commerce/overview?period=ay",
    "/api/v1/field/today",
    "/api/v1/field/today/brief",
]


def get(path: str, fresh: bool) -> tuple[int, float, object]:
    headers = {"Cookie": COOKIE}
    if fresh:
        headers["X-Data-Refresh"] = "1"
    req = urllib.request.Request(BASE + path, headers=headers)
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
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
    for p in ("/api/v1/eticaret/marketplaces", "/api/v1/eticaret/marketplaces/stock-risk"):
        s, took, _ = get(p, False)
        print(f"ısınma {p}: {s} · {took:.1f} sn", flush=True)
    bad = 0
    for p in PATHS:
        for n in (1, 2):
            s, took, body = get(p, True)
            ok = s in (200, 403) and took < LIMIT
            bad += 0 if ok else 1
            extra = f" · okundu {body.get('okundu')}" if isinstance(body, dict) and body.get("okundu") else ""
            print(f"{'GEÇTİ' if ok else 'KALDI'} {p} ({n}): {s} · {took:.2f} sn{extra}", flush=True)
    _, _, m = get("/api/v1/eticaret/marketplaces", False)
    if isinstance(m, dict) and m.get("cariler") is not None:
        net = round(sum(c["net"] for c in m["cariler"]), 2)
        ok = abs(net - round(m["toplam"]["net"], 2)) < 0.01
        bad += 0 if ok else 1
        print(f"{'GEÇTİ' if ok else 'KALDI'} pazar yeri toplam net = Σ cari net: {m['toplam']['net']:.2f} / {net:.2f}")
    print(f"-- {bad} kaldı (hedef < {LIMIT} sn)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
