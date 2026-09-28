"""Arka plan işleri: ana ekran özeti 3 dk, uyarı kontrolü 15 dk, pano kartları 15 dk, planlı raporlar 5 dk, sistem durumu 5 dk.

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


def _post(path: str, body: dict, timeout: int):
    req = urllib.request.Request(f"{BRIDGE}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "X-Semantic-Caller": TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)


def report(name: str, path: str, every: int, ok: bool, detail: str = "") -> None:
    """M48: VM'de sunucu zamanlayıcısı yok; her işin sonucu Sistem durumu'nun iş tablosuna buradan yazılır. Bu
    bildirimlerin tazeliği aynı zamanda «Müşteri VM'i» halkasının kalp atışıdır. Bildirim düşerse iş etkilenmez."""
    try:
        _post("/api/v1/it-ops/watchdog", {"job": f"vm:{path}", "label": name, "ok": ok, "detail": detail[:500],
                                          "every": f"{max(1, every // 60)} dk", "source": "jobs-container"}, 30)
    except Exception as e:  # noqa: BLE001
        print(f"{name}: sistem durumuna bildirilemedi: {e}", flush=True)


def call(name: str, path: str, timeout: int, every: int = 0) -> None:
    try:
        out = _post(path, {}, timeout)
        print(f"{name}:", out, flush=True)
        report(name, path, every, True)
    except Exception as e:  # noqa: BLE001
        print(f"{name} başarısız: {e}", flush=True)
        report(name, path, every, False, f"{type(e).__name__}: {e}")


# (ad, yol, aralık sn, zaman aşımı sn) — sunucudaki zamanlayıcıların aynısı
JOBS = [
    ("uyarı kontrolü", "/api/v1/alerts/check", int(os.environ.get("ALERTS_EVERY_SEC", "900")), 590),
    ("pano kartları", "/api/v1/board/run-due", int(os.environ.get("BOARD_EVERY_SEC", "900")), 590),
    ("planlı raporlar", "/api/v1/reports/run-due", int(os.environ.get("REPORTS_EVERY_SEC", "300")), 1700),
    ("SEO & GEO eşitlemesi", "/api/v1/seo-geo/run-due", int(os.environ.get("SEO_EVERY_SEC", "86400")), 1700),
    # M46 bütçe: Logo gerçekleşmesi + sapma uyarıları (sunucuda timas-budget.timer, saatte bir; geçmiş yıl okuması 3-4 dk).
    ("bütçe", "/api/v1/budget/run-due", int(os.environ.get("BUDGET_EVERY_SEC", "3600")), 1790),
    # M7 yazar ilişkileri sabah özeti (sunucuda timas-author-reminders.timer): köprü saat eşiğini ve günde bir kez kuralını
    # kendisi uygular, sık çağrı zararsız.
    ("yazar hatırlatmaları", "/api/v1/editorial/authors/reminders/run-due", int(os.environ.get("AUTHOR_REMINDERS_EVERY_SEC", "900")), 590),
    # M48 sistem durumu: halka denetimi, olay aç/kapat, bildirim (sunucuda timas-itops.timer, 5 dk).
    ("sistem durumu", "/api/v1/it-ops/run-due", int(os.environ.get("ITOPS_EVERY_SEC", "300")), 290),
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
    threads += [threading.Thread(target=loop, args=(every, call, name, path, timeout, every), daemon=True)
                for name, path, every, timeout in JOBS]
    for t in threads:
        t.start()
    while all(t.is_alive() for t in threads):
        time.sleep(30)
    raise SystemExit("bir iş döngüsü durdu")  # konteyner yeniden başlar


if __name__ == "__main__":
    main()
