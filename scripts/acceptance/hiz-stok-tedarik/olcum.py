"""Stok (M43) ve tedarik (M52) ekran uçlarının süresi — hazır cevap atlanarak (`X-Data-Refresh: 1`), test sunucusunda.

Hedef: her GET ucu < 1,5 sn (kaynak okuması arka planda). Önce ısınma turu yapılır: son okuma tabloda yoksa (bu sürümün
ilk kurulumu, gece turu henüz koşmamış) ilk istek kaynağı bekler — bu süre hedefe sayılmaz, ayrıca yazılır. Sonra her uç
`X-Data-Refresh: 1` ile ölçülür. Yazma yok (yalnız GET); kişi verisi yazdırılmaz.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi). İsteğe bağlı HEDEF_SN (vars. 1.5).
Kullanım: python olcum.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
LIMIT = float(os.environ.get("HEDEF_SN", "1.5"))


def get(path: str, fresh: bool) -> tuple[int, float, object]:
    headers = {"Cookie": COOKIE}
    if fresh:
        headers["X-Data-Refresh"] = "1"
    req = urllib.request.Request(BASE + path, headers=headers)
    t = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    took = time.monotonic() - t
    try:
        body = json.loads(raw) if raw[:1] in (b"{", b"[") else None
    except ValueError:
        body = None
    return status, took, body


def main() -> int:
    stock = ["/meta", "/overview", "/names", "/items", "/items?durum=bitecek", "/running-out", "/excess", "/diff",
             "/transfer-errors", "/pick-line", "/thresholds", "/thresholds?durum=oneri", "/suggestions", "/sources",
             "/bulletin"]
    supply = ["/meta", "/overview", "/load", "/conflicts", "/incoming", "/paper", "/suppliers", "/payments", "/unbilled",
              "/cost-trend", "/suggestions", "/capacity", "/supplier-map", "/invoice-links", "/sources"]
    paths = [("/api/v1/stock" + p) for p in stock] + [("/api/v1/supply" + p) for p in supply]
    # ısınma: son okuma yoksa burada beklenir (hedefe sayılmaz)
    for p in ("/api/v1/stock/overview", "/api/v1/supply/overview"):
        s, took, _ = get(p, False)
        print(f"ısınma {p}: {s} · {took:.1f} sn", flush=True)
    _, _, items = get("/api/v1/stock/items", False)
    if isinstance(items, dict) and items.get("items"):
        paths.append("/api/v1/stock/items/" + urllib.parse.quote(items["items"][0]["stokKodu"]))
    _, _, sup = get("/api/v1/supply/suppliers", False)
    if isinstance(sup, dict) and sup.get("items"):
        paths.append("/api/v1/supply/suppliers/" + urllib.parse.quote(sup["items"][0]["kod"]))
    bad = 0
    for p in paths:
        s, took, body = get(p, True)
        ok = s in (200, 403) and took < LIMIT
        bad += 0 if ok else 1
        extra = ""
        if isinstance(body, dict) and ("yenileniyor" in body or "refreshing" in body):
            extra = f" · arka planda tazeleniyor={body.get('yenileniyor', body.get('refreshing'))}"
        print(f"{'GEÇTİ' if ok else 'KALDI'} {p}: {s} · {took:.2f} sn{extra}", flush=True)
    print(f"-- {len(paths) - bad} geçti, {bad} kaldı (hedef < {LIMIT} sn)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
