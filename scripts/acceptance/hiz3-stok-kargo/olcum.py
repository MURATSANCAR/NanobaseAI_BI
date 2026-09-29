"""Stok listesi (`/stok`) ve kargo (`/kargo`, `/kargo/mutabakat`) uçlarının süresi — hız 2. tur, test sunucusunda.

Ekran gibi ölçer: `/stok` açılışında `/stock/names` ve `/stock/items` AYNI ANDA istenir (eskiden ikisi modeli ayrı ayrı
kuruyordu, 14 sn). Her ekran iki kez açılır («ilk giriş», «ikinci giriş»); hazır cevap katmanı `X-Data-Refresh: 1` ile
atlanır, yani ölçülen ucun kendi süresidir. Ardından kargo belleği eskimiş gibi davranması için `BEKLE_SN` (vars. 0)
beklenip üçüncü tur ölçülür (5 dakikayı aşan bekleme: bellek süresi dolmuş, istek yine beklememeli).

Yazma yok (yalnız GET); kişi verisi yazdırılmaz (yalnız durum, süre, satır sayısı).
Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), HEDEF_SN (vars. 1.5), BEKLE_SN (vars. 0).
Kullanım: python olcum.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
LIMIT = float(os.environ.get("HEDEF_SN", "1.5"))
WAIT = float(os.environ.get("BEKLE_SN", "0"))


def get(path: str) -> tuple[int, float, object]:
    req = urllib.request.Request(BASE + path, headers={"Cookie": COOKIE, "X-Data-Refresh": "1"})
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


def together(paths: list[str]) -> list[tuple[str, int, float, object]]:
    """Ekranın açılışı gibi: istekler aynı anda."""
    out: list[tuple[str, int, float, object]] = []
    lock = threading.Lock()

    def one(p: str) -> None:
        s, took, body = get(p)
        with lock:
            out.append((p, s, took, body))
    threads = [threading.Thread(target=one, args=(p,)) for p in paths]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(out)


def main() -> int:
    month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    screens = {
        "/stok": ["/api/v1/stock/meta", "/api/v1/stock/names", "/api/v1/stock/items"],
        "/kargo": ["/api/v1/shipping/meta", "/api/v1/shipping/overview",
                   "/api/v1/shipping/shipments?q=&durum=hepsi&firma=&sayfa=0"],
        "/kargo/mutabakat": ["/api/v1/shipping/meta", f"/api/v1/shipping/reconcile?ay={month}"],
    }
    bad = 0
    rounds = ["ilk giriş", "ikinci giriş"] + (["bellek süresi dolduktan sonra"] if WAIT > 0 else [])
    for n, name in enumerate(rounds):
        if n == 2:
            print(f"-- {WAIT:.0f} sn bekleniyor", flush=True)
            time.sleep(WAIT)
        for screen, paths in screens.items():
            for p, s, took, body in together(paths):
                ok = s in (200, 403) and took < LIMIT
                bad += 0 if ok else 1
                size = ""
                if isinstance(body, dict):
                    items = body.get("items")
                    size = f" · {len(items)} satır" if isinstance(items, list) else ""
                print(f"{'GEÇTİ' if ok else 'KALDI'} [{name}] {screen} {p}: {s} · {took:.2f} sn{size}", flush=True)
    print(f"-- {bad} kaldı (hedef < {LIMIT} sn)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
