"""Arka plan işleri: ana ekran özeti 3 dk, uyarı kontrolü 15 dk, pano kartları 15 dk, planlı raporlar 5 dk.

Sunucuda bunlar systemd zamanlayıcılarıdır (timas-metrics, timas-alerts, timas-board, timas-reports). Müşteri
yığınında aynı işler bu tek konteynerde döner; mantık yine köprüdedir, burası yalnız zamanında çağırır.
"""
import json
import os
import runpy
import threading
import time
import urllib.request

BRIDGE = os.environ.get("BRIDGE", "http://bridge:8795")
TOKEN = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
METRICS_EVERY = int(os.environ.get("METRICS_EVERY_SEC", "180"))


def metrics() -> None:
    try:
        runpy.run_path("/app/jobs/metrics_build.py", run_name="__main__")
    except SystemExit:
        pass
    except Exception as e:  # noqa: BLE001 — bir tur patlarsa bir sonraki denenir
        print(f"özet üretilemedi: {e}", flush=True)


def call(name: str, path: str, timeout: int) -> None:
    req = urllib.request.Request(f"{BRIDGE}{path}", data=b"{}", method="POST",
                                 headers={"Content-Type": "application/json", "X-Semantic-Caller": TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            print(f"{name}:", json.load(res), flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"{name} başarısız: {e}", flush=True)


# (ad, yol, aralık sn, zaman aşımı sn) — sunucudaki zamanlayıcıların aynısı
JOBS = [
    ("uyarı kontrolü", "/api/v1/alerts/check", int(os.environ.get("ALERTS_EVERY_SEC", "900")), 590),
    ("pano kartları", "/api/v1/board/run-due", int(os.environ.get("BOARD_EVERY_SEC", "900")), 590),
    ("planlı raporlar", "/api/v1/reports/run-due", int(os.environ.get("REPORTS_EVERY_SEC", "300")), 1700),
]


def loop(every: int, fn, *args) -> None:
    # Her iş kendi iş parçacığında: uzun bir rapor turu uyarı kontrolünü bekletmez.
    while True:
        started = time.monotonic()
        fn(*args)
        time.sleep(max(5.0, every - (time.monotonic() - started)))


def main() -> None:
    time.sleep(30)   # köprü açılsın diye kısa bekleme
    threads = [threading.Thread(target=loop, args=(METRICS_EVERY, metrics), daemon=True)]
    threads += [threading.Thread(target=loop, args=(every, call, name, path, timeout), daemon=True)
                for name, path, every, timeout in JOBS]
    for t in threads:
        t.start()
    while all(t.is_alive() for t in threads):
        time.sleep(30)
    raise SystemExit("bir iş döngüsü durdu")  # konteyner yeniden başlar


if __name__ == "__main__":
    main()
