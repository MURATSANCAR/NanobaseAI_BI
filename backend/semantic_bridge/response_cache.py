"""Yavaş ekran verisi için «önce hazır cevap, arkada tazele» katmanı (kullanıcı kararı 2026-09-28).

Sorun: bazı ekranlar açılışta kaynağı bekliyordu (ölçüm 2026-09-28, 72 menü ekranı: yeni kitap 53 sn, SEO iş listesi
17 sn, veri sözlüğü 13 sn, kişi rehberi 8–10 sn…). İstek: veri önden hazır olsun, ekranda «Yenile» ile ve kendiliğinden
5 dakikada bir tazelensin — yalnız bir ekranda değil, benzer veri çeken hepsinde.

Kural:
- Yalnız **yavaş** (üretimi `SLOW_SECONDS` üstü süren) başarılı JSON GET cevabı saklanır; hızlı uçlar hiç etkilenmez.
- Anahtar **kişi + yol + sorgu**: bir kişinin cevabı başkasına gitmez. Sayfa kapısı (oturum ve sayfa yetkisi) bu
  katmandan önce çalışır; hazır cevap yalnız kapıyı geçen isteğe verilir.
- Saklanan cevap `FRESH_SECONDS` (5 dk) içinde ise hemen döner; daha eskiyse yine hemen döner ve aynı anda arkada
  yeniden üretilir (aynı istek, aynı çerezle uygulamanın içinden). Son 24 saatte istenmiş cevaplar kimse açmasa da
  5 dakikada bir arkada tazelenir; oturum düşmüşse (401/403) o kayıt bırakılır.
- «Yenile» (üst şeritteki `X-Data-Refresh: 1` ya da ekranın kendi yenilemesi) beklemeden kaynaktan okur ve kaydı günceller.
- Bir modülde yazma (POST/PUT/PATCH/DELETE) başarılı olunca o modülün bütün hazır cevapları hemen düşer (herkes için):
  kaydedilen şey eski cevapla görünmez.
- Hiç saklanmayanlar: sohbet/soru, SQL, sonuç dosyası, model, yetki, yönetim, kişisel tercih/profil, kutlama, oda,
  zamanlayıcı uçları, durum/ilerleme yoklamaları, dosya/görsel/PDF/dışa aktarma.
Kayıtlar yalnız bellekte (süreç yeniden başlayınca boşalır, ilk açılış bir kez kaynağı bekler); disk ya da başka bir
kişiyle paylaşım yoktur.
"""
from __future__ import annotations

import asyncio
import logging
import re
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode

log = logging.getLogger("semantic.response_cache")

FRESH_SECONDS = 300
SLOW_SECONDS = 1.5
KEEP_SECONDS = 24 * 3600
MAX_BODY = 8 * 1024 * 1024
MAX_TOTAL = 400 * 1024 * 1024

#: Önek → hiç saklanmaz.
NEVER_PREFIXES = (
    "/api/v1/ask", "/api/v1/run_sql", "/api/v1/result/", "/api/v1/llm/", "/api/v1/access/", "/api/v1/admin/",
    "/api/v1/me/", "/api/v1/greetings", "/api/v1/rooms", "/api/v1/engine", "/api/v1/feedback", "/api/v1/people/",
    "/health",
)
#: Yolun herhangi bir yerinde geçen parça → hiç saklanmaz (yoklama, ilerleme, dosya).
NEVER_PARTS = re.compile(
    r"(run-due|/status$|/progress|/jobs|/stream|export|/file$|/image$|/pdf|/photo|/download|/cover|/covers/|/snapshot$|"
    r"\.(xlsx|csv|pdf|docx|png|jpe?g|webp|svg|zip|epub|mp3|wav)$)", re.I)

REVALIDATE_HEADER = "x-swr-revalidate"


def cacheable_path(path: str) -> bool:
    return path.startswith("/api/v1/") and not path.startswith(NEVER_PREFIXES) and not NEVER_PARTS.search(path)


def module_of(path: str) -> str:
    """Yazmanın düşüreceği önek: editoryal için iki parça (/api/v1/editorial/contracts), diğerlerinde bir (/api/v1/seo-geo)."""
    parts = [p for p in path.split("/") if p][:4]      # api, v1, modül, alt
    if len(parts) < 3:
        return path
    if parts[2] == "editorial" and len(parts) >= 4:
        return "/" + "/".join(parts[:4])
    return "/" + "/".join(parts[:3])


def norm_query(query: str) -> str:
    pairs = [(k, v) for k, v in parse_qsl(query or "", keep_blank_values=True) if k not in ("_", "t", "refresh")]
    return urlencode(sorted(pairs))


@dataclass
class Entry:
    body: bytes
    headers: list[tuple[str, str]]
    status: int
    at: float
    seconds: float
    asked: float
    replay: dict[str, str] = field(default_factory=dict)   # yeniden üretmek için isteğin başlıkları (yalnız bellekte)
    busy: bool = False


class ResponseCache:
    def __init__(self) -> None:
        self._items: "OrderedDict[tuple[str, str, str], Entry]" = OrderedDict()
        self._lock = threading.Lock()
        self.secret = secrets.token_hex(16)
        self.enabled = True
        self.stats = {"hit": 0, "stale": 0, "miss": 0, "stored": 0, "revalidated": 0, "dropped": 0, "invalidated": 0}

    # ---- kayıtlar
    def get(self, key: tuple[str, str, str]) -> Optional[Entry]:
        with self._lock:
            e = self._items.get(key)
            if e is not None:
                e.asked = time.time()
                self._items.move_to_end(key)
            return e

    def put(self, key: tuple[str, str, str], body: bytes, headers: list[tuple[str, str]], status: int, seconds: float,
            replay: dict[str, str]) -> None:
        now = time.time()
        with self._lock:
            old = self._items.get(key)
            self._items[key] = Entry(body, headers, status, now, seconds, old.asked if old else now, replay)
            self._items.move_to_end(key)
            total = sum(len(e.body) for e in self._items.values())
            while total > MAX_TOTAL and len(self._items) > 1:      # en uzun süredir istenmeyen düşer
                _, gone = self._items.popitem(last=False)
                total -= len(gone.body)
            self.stats["stored"] += 1

    def drop(self, key: tuple[str, str, str]) -> None:
        with self._lock:
            if self._items.pop(key, None) is not None:
                self.stats["dropped"] += 1

    def invalidate(self, prefix: str) -> int:
        with self._lock:
            gone = [k for k in self._items if k[1].startswith(prefix)]
            for k in gone:
                del self._items[k]
            self.stats["invalidated"] += len(gone)
            return len(gone)

    def due(self, now: Optional[float] = None) -> list[tuple[tuple[str, str, str], Entry]]:
        """Arkada tazelenecekler: bayat ve son 24 saatte istenmiş, şu an üretilmiyor. Uzun süredir istenmeyen düşer."""
        now = now or time.time()
        out = []
        with self._lock:
            for k in list(self._items):
                e = self._items[k]
                if now - e.asked > KEEP_SECONDS:
                    del self._items[k]
                    continue
                if not e.busy and now - e.at >= FRESH_SECONDS:
                    out.append((k, e))
        return out

    def mark(self, key: tuple[str, str, str], busy: bool) -> bool:
        with self._lock:
            e = self._items.get(key)
            if e is None or (busy and e.busy):
                return False
            e.busy = busy
            return True

    def view(self) -> dict[str, Any]:
        with self._lock:
            return {"entries": len(self._items), "bytes": sum(len(e.body) for e in self._items.values()),
                    "enabled": self.enabled, **self.stats}


def install(app: Any, cache: ResponseCache, user_of: Any, enabled: Any) -> None:
    """Köprüye ara katman ve 5 dakikalık arka plan tazeleyicisini ekler. `user_of(cookie)` → kullanıcı ya da istisna;
    `enabled()` → ayar açık mı. Sayfa kapısından SONRA (içeride) çalışsın diye kapıdan önce kurulmalı."""
    from starlette.requests import Request
    from starlette.responses import Response

    def _key(request: Request) -> Optional[tuple[str, str, str]]:
        cookie = request.headers.get("cookie", "")
        if "timas_session" not in cookie:
            return None
        try:
            user = user_of(cookie)
        except Exception:  # noqa: BLE001 — oturumsuzsa saklanmaz
            return None
        return (str(user).lower(), request.url.path, norm_query(request.url.query))

    def _replay_headers(request: Request) -> dict[str, str]:
        keep = ("cookie", "x-semantic-caller", "authorization", "accept", "accept-language", "x-forwarded-for", "x-real-ip",
                "x-forwarded-proto", "host", "origin", "referer")
        return {k: v for k, v in request.headers.items() if k.lower() in keep}

    async def _revalidate(key: tuple[str, str, str], headers: dict[str, str]) -> None:
        import httpx
        if not cache.mark(key, True):
            return
        try:
            url = key[1] + (("?" + key[2]) if key[2] else "")
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://bridge.internal", timeout=1800) as client:
                res = await client.get(url, headers={**headers, REVALIDATE_HEADER: cache.secret})
            if res.status_code in (401, 403):
                cache.drop(key)     # oturum düştü ya da yetki değişti: kayıt bırakılır
            elif res.status_code == 200:
                cache.stats["revalidated"] += 1
        except Exception as e:  # noqa: BLE001 — eski kayıt korunur, sonraki turda yeniden denenir
            log.info("response cache: %s arkada tazelenemedi: %s", key[1], e)
        finally:
            cache.mark(key, False)

    started_loop: list[bool] = []

    @app.middleware("http")
    async def response_cache_mw(request: Request, call_next):
        if not started_loop:          # köprü lifespan kullandığı için startup olayı çalışmaz; ilk istekte başlar
            started_loop.append(True)
            asyncio.get_running_loop().create_task(_loop())
        path, method = request.url.path, request.method.upper()
        if not enabled() or not cacheable_path(path):
            return await call_next(request)
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            response = await call_next(request)
            if response.status_code < 400:
                n = cache.invalidate(module_of(path))
                if n:
                    log.info("response cache: %s yazıldı, %d hazır cevap düştü", module_of(path), n)
            return response
        if method != "GET":
            return await call_next(request)
        key = _key(request)
        if key is None:
            return await call_next(request)
        revalidating = request.headers.get(REVALIDATE_HEADER) == cache.secret
        asked_refresh = str(request.query_params.get("refresh", "")).lower() in ("1", "true", "evet")
        force = revalidating or asked_refresh or request.headers.get("x-data-refresh") == "1"
        if not force:
            e = cache.get(key)
            if e is not None:
                age = time.time() - e.at
                if age >= FRESH_SECONDS:
                    cache.stats["stale"] += 1
                    asyncio.get_running_loop().create_task(_revalidate(key, e.replay or _replay_headers(request)))
                else:
                    cache.stats["hit"] += 1
                headers = [(k, v) for k, v in e.headers if k.lower() not in ("content-length", "x-data-age", "x-data-cached")]
                resp = Response(content=e.body, status_code=e.status, media_type=None)
                for k, v in headers:
                    resp.headers.append(k, v)
                resp.headers["x-data-age"] = str(int(age))
                resp.headers["x-data-cached"] = "1"
                return resp
        cache.stats["miss"] += 1
        started = time.monotonic()
        response = await call_next(request)
        ctype = response.headers.get("content-type", "")
        if response.status_code != 200 or "json" not in ctype:
            if response.status_code in (401, 403):
                cache.drop(key)
            return response
        body = b""
        async for chunk in response.body_iterator:
            body += chunk if isinstance(chunk, bytes) else chunk.encode()
        seconds = time.monotonic() - started
        headers = [(k, v) for k, v in response.headers.items() if k.lower() != "content-length"]
        slow_enough = seconds >= SLOW_SECONDS or (revalidating and cache.get(key) is not None) or \
            (force and cache.get(key) is not None)
        if slow_enough and len(body) <= MAX_BODY:
            cache.put(key, body, headers, response.status_code, seconds, _replay_headers(request))
        out = Response(content=body, status_code=response.status_code, media_type=None)
        for k, v in headers:
            out.headers.append(k, v)
        return out

    async def _loop() -> None:
        while True:
            await asyncio.sleep(30)
            try:
                if not enabled():
                    continue
                for key, e in cache.due():
                    # Sırayla: aynı anda tek arka plan üretimi; kaynağa yük bindirmez.
                    await _revalidate(key, e.replay)
            except Exception:  # noqa: BLE001 — tazeleyici durmasın
                log.exception("response cache: arka plan turu hata verdi")

