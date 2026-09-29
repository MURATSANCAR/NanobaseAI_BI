"""Yavaş ekran verisi için «önce hazır cevap, arkada tazele» katmanı (kullanıcı kararı 2026-09-28).

Sorun: bazı ekranlar açılışta kaynağı bekliyordu (ölçüm 2026-09-28, 72 menü ekranı: yeni kitap 53 sn, SEO iş listesi
17 sn, veri sözlüğü 13 sn, kişi rehberi 8–10 sn…). İstek: veri önden hazır olsun, ekranda «Yenile» ile ve kendiliğinden
5 dakikada bir tazelensin — yalnız bir ekranda değil, benzer veri çeken hepsinde. 2026-09-29 kullanıcı kararı: 5 dakikalık
otomatik tazeleme yerine her gün 07:00 ve 12:00'de (İstanbul saati) tazelenir.

Kural:
- Yalnız **yavaş** (üretimi `SLOW_SECONDS` üstü süren) başarılı JSON GET cevabı saklanır; hızlı uçlar hiç etkilenmez.
- Anahtar **kişi + yol + sorgu**: bir kişinin cevabı başkasına gitmez. Sayfa kapısı (oturum ve sayfa yetkisi) bu
  katmandan önce çalışır; hazır cevap yalnız kapıyı geçen isteğe verilir.
- Saklanan cevap son tazeleme saatinden (`REFRESH_TIMES`: 07:00, 12:00 İstanbul) sonra üretildiyse tazedir, hemen döner;
  daha önce üretildiyse yine hemen döner ve aynı anda arkada yeniden üretilir (aynı istek, aynı çerezle uygulamanın
  içinden). Son 24 saatte istenmiş cevaplar kimse açmasa da 07:00 ve 12:00'de arkada tazelenir; oturum düşmüşse
  (401/403) o kayıt bırakılır.
- «Yenile» (üst şeritteki `X-Data-Refresh: 1` ya da ekranın kendi yenilemesi) beklemeden kaynaktan okur ve kaydı günceller.
- Bir modülde yazma (POST/PUT/PATCH/DELETE) başarılı olunca o modülün bütün hazır cevapları hemen düşer (herkes için):
  kaydedilen şey eski cevapla görünmez.
- Hiç saklanmayanlar: sohbet/soru, SQL, sonuç dosyası, model, yetki, yönetim, kişisel tercih/profil, kutlama, oda,
  zamanlayıcı uçları, durum/ilerleme yoklamaları, dosya/görsel/PDF/dışa aktarma.
Kayıtlar bellekte ve diskte (`RESPONSE_CACHE_DIR`, klasör 0700, köprü kullanıcısının): köprü yeniden başlayınca
(test sunucusunda günde onlarca kez) hazır cevaplar kaybolmaz. Diske yalnız cevap gövdesi ve başlıkları yazılır; isteğin
çerezi (arkada yeniden üretmek için gereken) yalnız bellekte durur — yeniden başlatmadan sonra bayat kayıt ilk açılışta,
o kişinin kendi isteğiyle arkada tazelenir.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode
from zoneinfo import ZoneInfo

log = logging.getLogger("semantic.response_cache")

#: Hazır cevapların tazelendiği saatler (İstanbul). Ortamla değişir: RESPONSE_CACHE_REFRESH_TIMES="07:00,12:00".
TZ = ZoneInfo("Europe/Istanbul")
REFRESH_TIMES: tuple[tuple[int, int], ...] = tuple(
    (int(h), int(m)) for h, m in (t.strip().split(":") for t in
                                  os.environ.get("RESPONSE_CACHE_REFRESH_TIMES", "07:00,12:00").split(",") if t.strip()))


def last_refresh(now: Optional[float] = None) -> float:
    """Şu andan önceki en son tazeleme saatinin zamanı (epoch)."""
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, TZ).date()
    slots = [datetime(d.year, d.month, d.day, h, m, tzinfo=TZ).timestamp()
             for d in (today - timedelta(days=1), today) for h, m in REFRESH_TIMES]
    return max(t for t in slots if t <= now)


def is_stale(at: float, now: Optional[float] = None) -> bool:
    """Cevap son tazeleme saatinden önce üretildiyse bayattır."""
    return at < last_refresh(now)


SLOW_SECONDS = 1.5
KEEP_SECONDS = 3 * 24 * 3600     # son 3 günde açılmış ekranlar 07:00 ve 12:00'de kimse açmasa da hazırlanır
MAX_BODY = 8 * 1024 * 1024
MAX_TOTAL = 400 * 1024 * 1024

#: Önek → hiç saklanmaz.
NEVER_PREFIXES = (
    "/api/v1/ask", "/api/v1/run_sql", "/api/v1/result/", "/api/v1/llm/", "/api/v1/access/", "/api/v1/admin/",
    "/api/v1/me/", "/api/v1/greetings", "/api/v1/rooms", "/api/v1/engine", "/api/v1/feedback", "/api/v1/people/",
    "/health",
    # Sözleşme karşılaştırmanın kendi disk görüntüsü ve arka plan yenilemesi var (CRM'i yeniden oku, kurlar); ikinci
    # önbellek yenilenen görüntüyü 07:00/12:00'ye kadar gizliyordu (2026-09-29 kabulünde bulundu).
    "/api/v1/editorial/contracts/compare",
    # İK personel portalı: kişisel veri diske yazılmasın; kart açılışı her seferinde erişim kaydına düşsün.
    "/api/v1/hr/portal/",
)
#: Yolun herhangi bir yerinde geçen parça → hiç saklanmaz (yoklama, ilerleme, dosya).
NEVER_PARTS = re.compile(
    r"(run-due|/status$|/progress|/jobs|/stream|export|/file$|/image$|/pdf|/photo|/download|/cover|/covers/|/snapshot$|"
    r"\.(xlsx|csv|pdf|docx|png|jpe?g|webp|svg|zip|epub|mp3|wav)$)", re.I)

REVALIDATE_HEADER = "x-swr-revalidate"


def _code_version() -> str:
    """Köprü kodunun içerik özeti. Diskteki hazır cevap başka bir kod sürümünündense bayat sayılır: ekrana hemen gelir
    (beklenmez) ve ilk açılışta arkada yeni kodla yeniden üretilir; kurulumdan sonra hazır cevaplar kaybolmaz."""
    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for f in sorted(root.rglob("*")):
        if f.suffix in (".py", ".json") and "__pycache__" not in f.parts:
            try:
                h.update(str(f.relative_to(root)).encode())
                h.update(f.read_bytes())
            except OSError:
                continue
    return h.hexdigest()[:16]


CODE_VERSION = _code_version()


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
    def __init__(self, directory: Optional[str] = None) -> None:
        self._items: "OrderedDict[tuple[str, str, str], Entry]" = OrderedDict()
        self._lock = threading.Lock()
        self.secret = secrets.token_hex(16)
        self.enabled = True
        self.stats = {"hit": 0, "stale": 0, "miss": 0, "stored": 0, "revalidated": 0, "dropped": 0, "invalidated": 0,
                      "loaded": 0}
        self.dir: Optional[Path] = None
        #: Kişi → oturumun kimlik alanları (hesap adı, görünen ad). Arka plan tazelemesi çerez yerine bunu iç kimlikle
        #: kullanır: köprü yeniden başlasa da 07:00/12:00 tazelemesi herkes için çalışır. Çerez/parola yazılmaz.
        self.people: dict[str, dict[str, str]] = {}
        if directory:
            try:
                self.dir = Path(directory)
                self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                self._load()
                self._load_people()
            except OSError as e:          # disk yoksa yalnız bellekte çalışır
                log.warning("response cache: disk kullanılamıyor (%s): %s", directory, e)
                self.dir = None

    # ---- iç kimlik (arka plan tazelemesi; yalnız bu süreçte bilinen gizli değerle)
    INTERNAL_PREFIX = "timas_session=swr."

    def _people_path(self) -> Optional[Path]:
        return self.dir / "people.json" if self.dir is not None else None

    def _load_people(self) -> None:
        p = self._people_path()
        try:
            data = json.loads(p.read_text()) if p and p.exists() else {}
            self.people = {str(k): {"username": str(v.get("username") or k), "displayName": str(v.get("displayName") or "")}
                           for k, v in data.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            self.people = {}

    def remember(self, session: Optional[dict[str, Any]]) -> None:
        """Gerçek oturumla gelen kişinin kimlik alanları (değiştiyse diske yazılır)."""
        user = str((session or {}).get("username") or "").strip()
        if not user:
            return
        row = {"username": user, "displayName": str(session.get("displayName") or "").strip()}
        if self.people.get(user.lower()) == row:
            return
        self.people[user.lower()] = row
        p = self._people_path()
        if p is None:
            return
        try:
            tmp = p.with_name(p.name + f".{secrets.token_hex(4)}.tmp")
            tmp.write_text(json.dumps(self.people, ensure_ascii=False))
            os.chmod(tmp, 0o600)
            os.replace(tmp, p)
        except OSError as err:
            log.info("response cache: kişi kaydı yazılamadı: %s", err)

    def internal_cookie(self, user: str) -> str:
        return f"{self.INTERNAL_PREFIX}{self.secret}.{user}"

    def resolve_internal(self, cookie: str) -> Optional[dict[str, str]]:
        """İç çerez → oturum (yalnız gizli değer bu süreçteki ile aynıysa). Dışarıdan gelen istek bu değeri bilemez."""
        at = cookie.find(self.INTERNAL_PREFIX)
        if at < 0:
            return None
        rest = cookie[at + len(self.INTERNAL_PREFIX):].split(";")[0].strip()
        secret, _, user = rest.partition(".")
        if not user or not secrets.compare_digest(secret, self.secret):
            return None
        row = self.people.get(user.lower())
        return dict(row) if row else None

    # ---- disk (yeniden başlatmada hazır cevap kaybolmasın)
    @staticmethod
    def _name(key: tuple[str, str, str]) -> str:
        return hashlib.sha256(json.dumps(list(key), ensure_ascii=False).encode()).hexdigest()

    def _write(self, key: tuple[str, str, str], e: "Entry") -> None:
        if self.dir is None:
            return
        base = self.dir / self._name(key)
        meta = {"key": list(key), "headers": e.headers, "status": e.status, "at": e.at, "seconds": e.seconds, "asked": e.asked,
                "code": CODE_VERSION}
        try:
            for suffix, data in ((".body", e.body), (".meta.json", json.dumps(meta, ensure_ascii=False).encode())):
                tmp = base.with_name(base.name + suffix + f".{secrets.token_hex(4)}.tmp")
                with open(tmp, "wb") as f:
                    f.write(data)
                os.chmod(tmp, 0o600)
                os.replace(tmp, base.with_name(base.name + suffix))
        except OSError as err:
            log.info("response cache: diske yazılamadı: %s", err)

    def _unlink(self, key: tuple[str, str, str]) -> None:
        if self.dir is None:
            return
        base = self.dir / self._name(key)
        for suffix in (".body", ".meta.json"):
            try:
                base.with_name(base.name + suffix).unlink()
            except OSError:
                pass

    def _load(self) -> None:
        now = time.time()
        rows = []
        for meta_path in self.dir.glob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text())
                key = tuple(meta["key"])
                # Saklanmayacak yol (sonradan dışarıda bırakılmış): eski kayıt yüklenip arkada sürekli tazelenmez.
                if now - float(meta.get("asked", 0)) > KEEP_SECONDS or not cacheable_path(str(key[1])):
                    self._unlink(key)
                    self.stats["dropped"] += 1
                    continue
                other_code = meta.get("code") != CODE_VERSION     # başka kod sürümü: son tazeleme saatinden eski sayılır
                body = meta_path.with_name(meta_path.name[: -len(".meta.json")] + ".body").read_bytes()
                rows.append((float(meta.get("asked", 0)), key, Entry(body, [tuple(h) for h in meta["headers"]], int(meta["status"]),
                                                                     min(float(meta["at"]), last_refresh(now) - 1) if other_code
                                                                     else float(meta["at"]),
                                                                     float(meta.get("seconds", 0)),
                                                                     float(meta.get("asked", 0)))))
            except (OSError, ValueError, KeyError):
                continue
        for _, key, e in sorted(rows, key=lambda r: r[0]):
            self._items[key] = e
        self.stats["loaded"] = len(rows)

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
        gone_keys = []
        with self._lock:
            old = self._items.get(key)
            entry = Entry(body, headers, status, now, seconds, old.asked if old else now, replay)
            self._items[key] = entry
            self._items.move_to_end(key)
            total = sum(len(e.body) for e in self._items.values())
            while total > MAX_TOTAL and len(self._items) > 1:      # en uzun süredir istenmeyen düşer
                k, gone = self._items.popitem(last=False)
                total -= len(gone.body)
                gone_keys.append(k)
            self.stats["stored"] += 1
        for k in gone_keys:
            self._unlink(k)
        self._write(key, entry)

    def drop(self, key: tuple[str, str, str]) -> None:
        with self._lock:
            if self._items.pop(key, None) is not None:
                self.stats["dropped"] += 1
        self._unlink(key)

    def invalidate(self, prefix: str) -> int:
        with self._lock:
            gone = [k for k in self._items if k[1].startswith(prefix)]
            for k in gone:
                del self._items[k]
            self.stats["invalidated"] += len(gone)
        for k in gone:
            self._unlink(k)
        return len(gone)

    def due(self, now: Optional[float] = None) -> list[tuple[tuple[str, str, str], Entry]]:
        """Arkada tazelenecekler: bayat ve son 24 saatte istenmiş, şu an üretilmiyor. Uzun süredir istenmeyen düşer."""
        now = now or time.time()
        out, forgotten = [], []
        with self._lock:
            for k in list(self._items):
                e = self._items[k]
                if now - e.asked > KEEP_SECONDS:
                    del self._items[k]
                    forgotten.append(k)
                    continue
                # Çerezi olmayan (yeniden başlatmadan diskten gelen) kayıt kişinin bir sonraki açılışında tazelenir.
                # Çerezi bellekte olmayan (yeniden başlatmadan diskten gelen) kayıt iç kimlikle tazelenir.
                if not e.busy and (e.replay or k[0] in self.people) and is_stale(e.at, now):
                    out.append((k, e))
        for k in forgotten:
            self._unlink(k)
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


def install(app: Any, cache: ResponseCache, user_of: Any, enabled: Any, session_of: Any = None) -> None:
    """Köprüye ara katman ve 07:00/12:00 arka plan tazeleyicisini ekler. `user_of(cookie)` → kullanıcı ya da istisna;
    `session_of(cookie)` → oturum sözlüğü (kimlik alanları iç kimlik için saklanır); `enabled()` → ayar açık mı.
    Sayfa kapısından SONRA (içeride) çalışsın diye kapıdan önce kurulmalı."""
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
        if session_of is not None and cache.INTERNAL_PREFIX not in cookie:
            try:
                cache.remember(session_of(cookie))
            except Exception:  # noqa: BLE001 — kimlik saklanamasa da cevap saklanır
                pass
        return (str(user).lower(), request.url.path, norm_query(request.url.query))

    def _internal_headers(user: str) -> dict[str, str]:
        h = {"cookie": cache.internal_cookie(user), "accept": "application/json"}
        token = os.environ.get("SEMANTIC_CALLER_TOKEN", "")
        if token:
            h["x-semantic-caller"] = token
        return h

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
                if is_stale(e.at):
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
                    await _revalidate(key, e.replay or _internal_headers(key[0]))
            except Exception:  # noqa: BLE001 — tazeleyici durmasın
                log.exception("response cache: arka plan turu hata verdi")

