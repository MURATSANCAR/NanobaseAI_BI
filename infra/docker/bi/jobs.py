"""Arka plan işleri: ana ekran özeti 3 dakikada bir, uyarı kontrolü 15 dakikada bir.

Sunucuda bunlar systemd zamanlayıcılarıdır (timas-metrics.timer, timas-alerts.timer). Müşteri yığınında
aynı iki iş bu tek konteynerde döner; mantık yine köprüdedir, burası yalnız zamanında çağırır.
"""
import json
import os
import runpy
import time
import urllib.request

BRIDGE = os.environ.get("BRIDGE", "http://bridge:8795")
TOKEN = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
METRICS_EVERY = int(os.environ.get("METRICS_EVERY_SEC", "180"))
ALERTS_EVERY = int(os.environ.get("ALERTS_EVERY_SEC", "900"))


def metrics() -> None:
    try:
        runpy.run_path("/app/jobs/metrics_build.py", run_name="__main__")
    except SystemExit:
        pass
    except Exception as e:  # noqa: BLE001 — bir tur patlarsa bir sonraki denenir
        print(f"özet üretilemedi: {e}", flush=True)


def alerts() -> None:
    req = urllib.request.Request(f"{BRIDGE}/api/v1/alerts/check", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", "X-Semantic-Caller": TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=590) as res:
            print("uyarı kontrolü:", json.load(res), flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"uyarı kontrolü başarısız: {e}", flush=True)


def main() -> None:
    next_m = next_a = time.monotonic() + 30   # köprü açılsın diye kısa bekleme
    while True:
        now = time.monotonic()
        if now >= next_m:
            metrics()
            next_m = now + METRICS_EVERY
        if now >= next_a:
            alerts()
            next_a = now + ALERTS_EVERY
        time.sleep(5)


if __name__ == "__main__":
    main()
