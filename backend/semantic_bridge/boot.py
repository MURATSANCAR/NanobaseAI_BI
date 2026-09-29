"""Köprünün açılışı: kapı hemen açılır, ağır yükleme arkada sürer.

Eskiden uvicorn, lifespan içindeki `build_runtime()` bitmeden portu açmıyordu: 4.874 tablo profili (iki kez), katalog
dizini, kolon dizini, ~180 bin ifadelik dil havuzu… Test sunucusunda bu 40–100 sn sürüyor ve o sürede bütün ekranlar
502 alıyordu. Şimdi açılış iki aşamalıdır ve ikisi de arka plandaki tek iş parçacığında koşar:

1. **Çalışma ortamı** (saniyeler): katalog veritabanı bağlantısı, Logo/CRM bağlantı tanımları, model sırası. Ekranların
   neredeyse hepsi yalnız bunu kullanır (`rt().store.engine`, `rt().settings`, `rt().run_sql`, `rt().llm_for`).
   Bu aşama bitmeden gelen istek (/health dışında) en çok `SEMANTIC_BOOT_REQUEST_WAIT_SEC` bekler.
2. **Katalog** (profiller, çözümleyici, derleyiciler, dil havuzu): yalnız soru/katalog uçları kullanır. Bu alanlara
   dokunan istek katalog bitene kadar bekler; süre dolarsa kısa bir «hazırlanıyor» cevabı (503, `Retry-After`) alır.
   Cevap hiçbir zaman yarım katalogla üretilmez — rakamlar açılışa göre değişmez.

Arka plan iş parçacıkları (zamanlayıcılar, ısıtmalar) istek değildir: onlar hazırlığı süre sınırı olmadan bekler.
Hiçbir yol çalışma ortamını ikinci kez kurmaz (2026-09-28'de böyle bir çift kurulum açılışı 40 → 110 sn yapmıştı).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from contextvars import ContextVar
from typing import Any, Callable, Optional

from fastapi import HTTPException

log = logging.getLogger("semantic_bridge.boot")

#: Bu bağlam bir HTTP isteğine mi ait (açılış kapısı ara katmanı kurar; iş parçacığı havuzuna bağlamla geçer)?
IN_REQUEST: ContextVar[bool] = ContextVar("boot_in_request", default=False)

WARMING_CODE = "WARMING_UP"
WARMING_MESSAGE = "Sistem yeniden başlıyor; veriler birkaç saniye içinde hazır olur. Lütfen biraz sonra tekrar deneyin."


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.environ.get(name, "") or default))
    except ValueError:
        return default


def request_wait_sec() -> float:
    """İstek, hazırlığı en çok bu kadar bekler (sonra 503 «hazırlanıyor»)."""
    return _env_float("SEMANTIC_BOOT_REQUEST_WAIT_SEC", 45.0)


def background_wait_sec() -> float:
    """Arka plan işi hazırlığı en çok bu kadar bekler (bir saat: açılış bundan uzun sürüyorsa ayrı bir arıza vardır)."""
    return _env_float("SEMANTIC_BOOT_BACKGROUND_WAIT_SEC", 3600.0)


class Warming(HTTPException):
    """Hazırlık sürüyor: kısa ve yeniden denenebilir cevap. HTTPException olduğu için uçların
    `except HTTPException: raise` yolundan olduğu gibi geçer."""

    def __init__(self, what: str = "catalog") -> None:
        super().__init__(status_code=503, detail={"code": WARMING_CODE, "message": WARMING_MESSAGE,
                                                  "retryable": True, "phase": what},
                         headers={"Retry-After": "5"})


def on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def wait(event: threading.Event, what: str) -> None:
    """Hazırlık bitene kadar bekle. İstekte süre sınırlı (sonra `Warming`), arka planda uzun.

    Olay döngüsünde çalışan istek (async uç) hiç beklemez, hemen `Warming` alır: döngüyü kilitlemek bütün köprüyü
    durdurur. Olay döngüsünde ama istek dışında (uygulama kurulurken) eskisi gibi beklenir."""
    if event.is_set():
        return
    in_request = IN_REQUEST.get()
    if in_request and on_event_loop():
        raise Warming(what)
    if not event.wait(request_wait_sec() if in_request else background_wait_sec()):
        raise Warming(what)


class Boot:
    """Tek arka plan iş parçacığı: çalışma ortamı → servisler → katalog → katalog servisleri.

    `build()` çalışma ortamını kurar (katalog yüklemeden); `on_runtime(rt)` ekranların arka plan işlerini başlatır;
    `on_catalog(rt)` katalog isteyen işleri başlatır. Kurulum düşerse artan aralıkla yeniden denenir.

    Servisler (zamanlayıcılar, ısıtmalar) yalnız uygulama gerçekten ayağa kalkarken (lifespan: `start(services=True)`)
    ve her biri bir kez başlar. İstek içinden tetiklenen kurulum (lifespan'sız test istemcisi) eskisi gibi yalnız
    çalışma ortamını ve katalogu kurar.
    """

    def __init__(self, build: Callable[[], Any], on_runtime: Callable[[Any], None],
                 on_catalog: Callable[[Any], None], *, runtime: Any = None) -> None:
        self._build = build
        self._on_runtime = on_runtime
        self._on_catalog = on_catalog
        self.runtime = runtime
        self.runtime_ready = threading.Event()
        if runtime is not None:
            self.runtime_ready.set()
        self.catalog_ready = threading.Event()
        self.phase = "bekliyor"
        self.error: Optional[str] = None
        self.started_at: Optional[float] = None
        self.timings: dict[str, float] = {}
        self.stopping = threading.Event()
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._with_services = False      # lifespan servis istedi mi
        self._services = False           # on_runtime koştu mu (durdururken bakılır)
        self._catalog_services = False   # on_catalog koştu mu
        self._done = False               # iş parçacığı son adımını geçti

    # ---- dışarıdan
    def start(self, services: bool = False) -> None:
        with self._lock:
            self._with_services = self._with_services or services
            if self.stopping.is_set():
                return
            if self._thread is None:
                self.started_at = self.started_at or time.time()
                self._thread = threading.Thread(target=self._run, name="bridge-boot", daemon=True)
                self._thread.start()
                return
            if not self._done:
                return                   # iş parçacığı servis noktalarına henüz gelmedi: kendisi başlatır
            want_rt, want_cat = self._claim_services(), self._claim_catalog_services()
        self._start_services(want_rt, want_cat)

    def run_inline(self) -> None:
        """Hazır verilen çalışma ortamı (testler): her şey bu iş parçacığında, hemen (eski lifespan davranışı)."""
        with self._lock:
            self._with_services = True
            self.started_at = self.started_at or time.time()
        self._run()

    def wait_runtime(self) -> Any:
        """Çalışma ortamı (katalogsuz). Kimse başlatmadıysa başlatır; asla ikinci kez kurmaz."""
        if self.runtime is not None:
            return self.runtime
        self.start()
        wait(self.runtime_ready, "runtime")
        if self.runtime is None:          # olay kuruldu ama çalışma ortamı yok: durduruluyor
            raise Warming("runtime")
        return self.runtime

    async def wait_runtime_async(self, timeout: float) -> bool:
        """Olay döngüsünü kilitlemeden bekler (açılış kapısı)."""
        self.start()
        end = time.monotonic() + timeout
        pause = 0.05
        while not self.runtime_ready.is_set():
            if time.monotonic() >= end:
                return False
            await asyncio.sleep(pause)
            pause = min(pause * 1.5, 0.5)
        return self.runtime is not None

    def uptime(self) -> float:
        return round(time.time() - self.started_at, 1) if self.started_at else 0.0

    def view(self) -> dict[str, Any]:
        return {"phase": self.phase, "runtimeReady": self.runtime_ready.is_set(), "catalogReady": self.catalog_ready.is_set(),
                "uptimeSec": self.uptime(), "error": self.error, "timings": dict(self.timings)}

    def stop(self) -> bool:
        """Döner: servisler başlatılmıştı (durdurulmalı)."""
        with self._lock:
            self.stopping.set()
            return self._services

    # ---- servis başlatma (kilit altında sahiplenilir, dışında koşar)
    def _claim_services(self) -> bool:
        with self._lock:
            if self.stopping.is_set() or self._services or not self._with_services or self.runtime is None:
                return False
            self._services = True
            return True

    def _claim_catalog_services(self) -> bool:
        with self._lock:
            if self.stopping.is_set() or self._catalog_services or not self._services or not self.catalog_ready.is_set():
                return False
            self._catalog_services = True
            return True

    def _start_services(self, want_rt: bool, want_cat: bool) -> None:
        rt = self.runtime
        if want_rt:
            self._once("servisler", lambda: self._on_runtime(rt))
        if want_cat:
            self._once("katalog-servisleri", lambda: self._on_catalog(rt))

    # ---- iş parçacığı
    def _retry(self, what: str, fn: Callable[[], Any]) -> Any:
        delay = 2.0
        while not self.stopping.is_set():
            started = time.perf_counter()
            try:
                out = fn()
                self.timings[what] = round(time.perf_counter() - started, 2)
                self.error = None
                return out
            except Exception as e:  # noqa: BLE001 — veritabanı açılışta hazır olmayabilir: bekle, yeniden dene
                self.error = f"{what}: {type(e).__name__}: {str(e)[:300]}"
                log.exception("açılış: %s kurulamadı, %.0f sn sonra yeniden denenecek", what, delay)
                self.stopping.wait(delay)
                delay = min(delay * 2, 60.0)
        return None

    def _once(self, what: str, fn: Callable[[], Any]) -> None:
        """Servis başlatma yeniden denenmez (yarım kalan bir başlatma ikinci kez koşarsa iş parçacıkları çiftlenir)."""
        started = time.perf_counter()
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            self.error = f"{what}: {type(e).__name__}: {str(e)[:300]}"
            log.exception("açılış: %s başlatılamadı", what)
        self.timings[what] = round(time.perf_counter() - started, 2)

    def _run(self) -> None:
        if self.runtime is None:
            self.phase = "calisma-ortami"
            rt = self._retry("calisma-ortami", self._build)
            if rt is None:
                with self._lock:
                    self._done = True
                self.runtime_ready.set()   # bekleyenler «hazırlanıyor» alsın, asılı kalmasın
                return
            self.runtime = rt
            self.runtime_ready.set()
            log.info("açılış: çalışma ortamı hazır (%.1f sn) — ekran uçları istek kabul ediyor", self.uptime())
        rt = self.runtime
        self._start_services(self._claim_services(), False)
        self.phase = "katalog"
        if not getattr(rt, "catalog_is_ready", lambda: True)():
            if self._retry("katalog", rt.load_catalog) is None and self.stopping.is_set():
                with self._lock:
                    self._done = True
                return
        self.catalog_ready.set()
        # Son sahiplenme kilit altında `_done` ile birlikte: lifespan bu arada servis istediyse ya burada ya da
        # `start()` içinde başlar — ikisi birden asla, hiçbiri de değil.
        with self._lock:
            self._done = True
            want_rt = self._claim_services()
            want_cat = self._claim_catalog_services()
        self._start_services(want_rt, want_cat)
        self.phase = "hazir"
        log.info("açılış tamam (%.1f sn): %s", self.uptime(), self.timings)
