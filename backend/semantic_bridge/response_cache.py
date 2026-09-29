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

Isıtma (hız 2. tur, 2026-09-29): bir ekranı hayatında ilk kez açan kişinin hazır cevabı yoktu. Her gün
`WARM_TIMES` (varsayılan 07:00) sonrasında, son 3 günde gelmiş her kişi için son 3 günde herhangi birinin açtığı (en az
`WARM_MIN_PEOPLE` kişinin; varsayılan 1) yavaş uçlardan kişinin henüz hazır cevabı olmayanlar, o kişinin iç kimliğiyle
arkada üretilir. Kişiler arası paylaşım yoktur: her cevap kişinin kendi oturumuyla, kendi yetkisi ve veri kapsamıyla
üretilir ve yalnız onun anahtarına yazılır. (Paylaşım 2026-09-29'da incelendi, yapılmadı: ekran uçlarının hemen hepsi
kişiyi ilk satırda oturumdan okuyor ve cevabı kişiye göre değiştirebiliyor — «benim bekleyenlerim», temsilci/bölge
süzgeci, işlem düğmeleri —; bu satır süzgeçleri CRM sahipliğinden uç içinde kuruluyor, `access.py`'de beyan edilmiyor;
aynı yetki kümesi aynı satırları garanti etmez, gövdede ad aramak kişiye özel sayıyı yakalamaz.) Yük: tek sıra, en çok `WARM_CONCURRENCY` (varsayılan 1) eşzamanlı istek;
sayfa kapısı önceden sorulur (`may_open`; kişinin göremediği sayfa denenmez, güvenlik kaydına 403 düşmez); hızlı çıkan ya
da açılamayan uç 3 gün yeniden denenmez; kişinin kendisi açmadığı ısıtılmış cevap 12:00 tazelemesine girmez ve «kaç kişi
açtı» sayısına katılmaz (`Entry.real`). Köprü ısıtma saatinden 3 saatten geç kalkarsa o günün ısıtması yapılmaz.
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


def _times(env: str, default: str) -> tuple[tuple[int, int], ...]:
    return tuple((int(h), int(m)) for h, m in (t.strip().split(":") for t in os.environ.get(env, default).split(",")
                                                if t.strip()))


#: Isıtma saatleri (İstanbul): RESPONSE_CACHE_WARM_TIMES="07:00"; boş bırakılırsa ısıtma kapalı.
WARM_TIMES = _times("RESPONSE_CACHE_WARM_TIMES", "07:00")
WARM_CONCURRENCY = max(1, int(os.environ.get("RESPONSE_CACHE_WARM_CONCURRENCY", "1") or 1))
WARM_MIN_PEOPLE = max(1, int(os.environ.get("RESPONSE_CACHE_WARM_MIN_PEOPLE", "1") or 1))
WARM_LATE = 3 * 3600


def last_refresh(now: Optional[float] = None, times: Optional[tuple[tuple[int, int], ...]] = None) -> float:
    """Şu andan önceki en son tazeleme saatinin zamanı (epoch). `times` verilirse o saatler (ısıtma)."""
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now, TZ).date()
    slots = [datetime(d.year, d.month, d.day, h, m, tzinfo=TZ).timestamp()
             for d in (today - timedelta(days=1), today) for h, m in (REFRESH_TIMES if times is None else times)]
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
    "/api/v1/hr/leave/",
)
#: Yolun herhangi bir yerinde geçen parça → hiç saklanmaz (yoklama, ilerleme, dosya).
NEVER_PARTS = re.compile(
    r"(run-due|/status$|/progress|/jobs|/stream|export|/file$|/image$|/pdf|/photo|/download|/cover|/covers/|/snapshot$|"
    r"\.(xlsx|csv|pdf|docx|png|jpe?g|webp|svg|zip|epub|mp3|wav)$)", re.I)

REVALIDATE_HEADER = "x-swr-revalidate"
WARM_HEADER = "x-swr-warm"          # ısıtma isteği (gizli değerle): üretilen kayıt «kişi açmadı» diye işaretlenir


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
    real: bool = True      # kişi bu cevabı kendisi istedi (False: yalnız ısıtıldı, henüz açmadı)
    size: int = -1                  # gövde boyu (bayt); diskten gelen kayıtta gövde okunmadan bilinir
    path: Optional[str] = None      # gövdesi henüz okunmamış kaydın dosyası (açılışta gövdeler okunmaz)

    def __post_init__(self) -> None:
        if self.size < 0:
            self.size = len(self.body)


class ResponseCache:
    def __init__(self, directory: Optional[str] = None) -> None:
        self._items: "OrderedDict[tuple[str, str, str], Entry]" = OrderedDict()
        self._lock = threading.Lock()
        self.secret = secrets.token_hex(16)
        self.enabled = True
        self.stats = {"hit": 0, "stale": 0, "miss": 0, "stored": 0, "revalidated": 0, "dropped": 0, "invalidated": 0,
                      "loaded": 0, "warmed": 0, "warmSkipped": 0}
        self.dir: Optional[Path] = None
        #: Kişi → oturumun kimlik alanları (hesap adı, görünen ad). Arka plan tazelemesi çerez yerine bunu iç kimlikle
        #: kullanır: köprü yeniden başlasa da 07:00/12:00 tazelemesi herkes için çalışır. Çerez/parola yazılmaz.
        self.people: dict[str, dict[str, str]] = {}
        #: Kişi → gerçek oturumla son geldiği an (ısıtma yalnız son 3 günde gelenler için).
        self.seen: dict[str, float] = {}
        self._seen_saved: dict[str, float] = {}
        #: Isıtması denenip saklanmayan (hızlı çıkan, sayfası kapalı, hata veren) anahtar → an; 3 gün yeniden denenmez.
        self._warm_skips: dict[tuple[str, str, str], float] = {}
        #: Sayfa kapısının kararı (app.py bağlar): (kişi, yol) → açabilir mi. Yoksa ısıtma yapılmaz.
        self.may_open: Optional[Any] = None
        self.warm_round: Optional[Any] = None     # install() bağlar: async (plan) → ısıtma turu
        self.warm_done = 0.0
        if directory:
            try:
                self.dir = Path(directory)
                self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
                self._load()
                self._load_people()
            except OSError as e:          # disk yoksa yalnız bellekte çalışır
                log.warning("response cache: disk kullanılamıyor (%s): %s", directory, e)
                self.dir = None
        self._load_warm()

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
            self.seen = {str(k): float(v.get("seen") or 0) for k, v in data.items() if isinstance(v, dict)}
            self._seen_saved = dict(self.seen)
        except (OSError, ValueError, TypeError):
            self.people, self.seen, self._seen_saved = {}, {}, {}

    def remember(self, session: Optional[dict[str, Any]], now: Optional[float] = None) -> None:
        """Gerçek oturumla gelen kişinin kimlik alanları ve son geliş anı (kimlik değiştiyse ya da son yazılan geliş
        bir saatten eskiyse diske yazılır)."""
        user = str((session or {}).get("username") or "").strip()
        if not user:
            return
        now = time.time() if now is None else now
        k = user.lower()
        row = {"username": user, "displayName": str(session.get("displayName") or "").strip()}
        self.seen[k] = now
        if self.people.get(k) == row and now - self._seen_saved.get(k, 0.0) < 3600:
            return
        self.people[k] = row
        p = self._people_path()
        if p is None:
            return
        try:
            data = {u: {**r, "seen": self.seen.get(u, 0.0)} for u, r in self.people.items()}
            tmp = p.with_name(p.name + f".{secrets.token_hex(4)}.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False))
            os.chmod(tmp, 0o600)
            os.replace(tmp, p)
            self._seen_saved = {u: self.seen.get(u, 0.0) for u in self.people}
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
                "code": CODE_VERSION, "real": e.real}
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
                # Hız (2026-09-29): açılışta yalnız künye okunur; gövde (toplam yüzlerce MB olabilir) ilk istendiğinde.
                body_path = meta_path.with_name(meta_path.name[: -len(".meta.json")] + ".body")
                size = body_path.stat().st_size
                rows.append((float(meta.get("asked", 0)), key, Entry(b"", [tuple(h) for h in meta["headers"]], int(meta["status"]),
                                                                     min(float(meta["at"]), last_refresh(now) - 1) if other_code
                                                                     else float(meta["at"]),
                                                                     float(meta.get("seconds", 0)),
                                                                     float(meta.get("asked", 0)),
                                                                     real=bool(meta.get("real", True)), size=size, path=str(body_path))))
            except (OSError, ValueError, KeyError):
                continue
        for _, key, e in sorted(rows, key=lambda r: r[0]):
            self._items[key] = e
        self.stats["loaded"] = len(rows)

    # ---- kayıtlar
    def get(self, key: tuple[str, str, str]) -> Optional[Entry]:
        """Kişinin kendi isteği: kayıt «istendi» sayılır (son istenme anı, `real`)."""
        with self._lock:
            e = self._items.get(key)
            if e is not None and e.path is not None:
                try:
                    e.body = Path(e.path).read_bytes()
                    e.size, e.path = len(e.body), None
                except OSError:                    # dosya gitmiş: kayıt da gider
                    del self._items[key]
                    return None
            if e is not None:
                e.asked = time.time()
                e.real = True
                self._items.move_to_end(key)
            return e

    def peek(self, key: tuple[str, str, str]) -> Optional[Entry]:
        """Kaydı istenme anına dokunmadan okur (tazeleme ve ısıtma: kimse açmadıysa kayıt 3 günde düşsün)."""
        with self._lock:
            return self._items.get(key)

    def put(self, key: tuple[str, str, str], body: bytes, headers: list[tuple[str, str]], status: int, seconds: float,
            replay: dict[str, str], origin: str = "real") -> None:
        """`origin`: real (kişinin isteği), revalidate (arka plan tazelemesi), warm (ısıtma — kişi henüz açmadı)."""
        now = time.time()
        gone_keys = []
        with self._lock:
            old = self._items.get(key)
            # Arka plan tazelemesi istenme anını uzatmaz (kimse açmıyorsa kayıt 3 günde düşer).
            asked = old.asked if (origin == "revalidate" and old is not None) else now
            real = origin == "real" or (old.real if old is not None else origin != "warm")
            entry = Entry(body, headers, status, now, seconds, asked, replay, real=real)
            self._items[key] = entry
            self._items.move_to_end(key)
            total = sum(e.size for e in self._items.values())
            while total > MAX_TOTAL and len(self._items) > 1:      # en uzun süredir istenmeyen düşer
                k, gone = self._items.popitem(last=False)
                total -= gone.size
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
                # Çerezi bellekte olmayan (yeniden başlatmadan diskten gelen) kayıt iç kimlikle tazelenir.
                # Yalnız ısıtılmış, kişinin henüz açmadığı kayıt tazelenmez (ertesi ısıtma yeniler; açarsa arkada tazelenir).
                if not e.busy and e.real and (e.replay or k[0] in self.people) and is_stale(e.at, now):
                    out.append((k, e))
        for k in forgotten:
            self._unlink(k)
        return out

    # ---- ısıtma (ilk kez açan kişi beklemesin)
    def _warm_path(self) -> Optional[Path]:
        return self.dir / "warm.json" if self.dir is not None else None

    def _load_warm(self) -> None:
        """Son yapılan ısıtma saati diskten; hiç yoksa şu anki son saat (yeni kurulum ilk turu ertesi saatte yapar)."""
        p = self._warm_path()
        try:
            if p is not None and p.exists():
                self.warm_done = float(json.loads(p.read_text()).get("slot") or 0)
                return
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        self.warm_done = last_refresh(None, WARM_TIMES) if WARM_TIMES else 0.0

    def warm_slot_due(self, now: Optional[float] = None) -> Optional[float]:
        """Yapılmamış ısıtma saati (en çok `WARM_LATE` geç kalınmış) ya da None."""
        if not WARM_TIMES:
            return None
        now = time.time() if now is None else now
        slot = last_refresh(now, WARM_TIMES)
        if slot <= self.warm_done or now - slot > WARM_LATE:
            return None
        return slot

    def warm_mark(self, slot: float) -> None:
        self.warm_done = slot
        p = self._warm_path()
        if p is None:
            return
        try:
            tmp = p.with_name(p.name + f".{secrets.token_hex(4)}.tmp")
            tmp.write_text(json.dumps({"slot": slot}))
            os.chmod(tmp, 0o600)
            os.replace(tmp, p)
        except OSError as err:
            log.info("response cache: ısıtma saati yazılamadı: %s", err)

    def warm_skip(self, key: tuple[str, str, str], now: Optional[float] = None) -> None:
        self._warm_skips[key] = time.time() if now is None else now
        self.stats["warmSkipped"] += 1

    def warm_plan(self, now: Optional[float] = None, min_people: Optional[int] = None) -> list[tuple[str, str, str]]:
        """Isıtılacak (kişi, yol, sorgu) sırası. Uçlar: son 3 günde en az `min_people` kişinin kendisi açtığı saklanmış
        cevaplar (çok açılan önce). Kişiler: son 3 günde gerçek oturumla gelen ve iç kimliği bilinenler. Kişinin kendi
        kaydı varsa (ısıtılmış olup bayatlamamışsa da) atlanır; son 3 günde denenip saklanmayan anahtar atlanır."""
        now = time.time() if now is None else now
        need = WARM_MIN_PEOPLE if min_people is None else max(1, int(min_people))
        with self._lock:
            items = list(self._items.items())
        opened: dict[tuple[str, str], set[str]] = {}
        for (u, p, q), e in items:
            if e.real and now - e.asked <= KEEP_SECONDS:
                opened.setdefault((p, q), set()).add(u)
        have = dict(items)
        self._warm_skips = {k: t for k, t in self._warm_skips.items() if now - t <= KEEP_SECONDS}
        people = sorted(u for u in self.people if now - self.seen.get(u, 0.0) <= KEEP_SECONDS)
        out: list[tuple[str, str, str]] = []
        for (p, q), users in sorted(opened.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            if len(users) < need or not cacheable_path(p):
                continue
            for u in people:
                key = (u, p, q)
                e = have.get(key)
                if e is not None and (e.real or not is_stale(e.at, now)):
                    continue
                if key in self._warm_skips:
                    continue
                out.append(key)
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
            return {"entries": len(self._items), "bytes": sum(e.size for e in self._items.values()),
                    "enabled": self.enabled, "warmDone": self.warm_done, **self.stats}


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

    async def _fetch(key: tuple[str, str, str], headers: dict[str, str], *, warm: bool = False) -> int:
        """Ucu uygulamanın içinden (sayfa kapısı dahil) kişinin kimliğiyle çağırır; ara katman cevabı saklar."""
        import httpx
        url = key[1] + (("?" + key[2]) if key[2] else "")
        h = {**headers, REVALIDATE_HEADER: cache.secret}
        if warm:
            h[WARM_HEADER] = cache.secret
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://bridge.internal", timeout=1800) as client:
            res = await client.get(url, headers=h)
        return res.status_code

    async def _revalidate(key: tuple[str, str, str], headers: dict[str, str]) -> None:
        if not cache.mark(key, True):
            return
        try:
            status = await _fetch(key, headers)
            if status in (401, 403):
                cache.drop(key)     # oturum düştü ya da yetki değişti: kayıt bırakılır
            elif status == 200:
                cache.stats["revalidated"] += 1
        except Exception as e:  # noqa: BLE001 — eski kayıt korunur, sonraki turda yeniden denenir
            log.info("response cache: %s arkada tazelenemedi: %s", key[1], e)
        finally:
            cache.mark(key, False)

    async def _warm(key: tuple[str, str, str]) -> None:
        """Kişinin henüz hazır cevabı olmayan ucu onun iç kimliğiyle üretir. Sayfa kapısı önceden sorulur."""
        if not enabled():
            return
        before = cache.peek(key)
        if before is not None and (before.real or not is_stale(before.at)):
            return                                  # bu arada kişi kendisi açtı ya da zaten hazır
        try:
            ok = bool(await asyncio.get_running_loop().run_in_executor(None, cache.may_open, key[0], key[1]))
        except Exception as e:  # noqa: BLE001 — yetki okunamadıysa denenmez
            log.info("response cache: %s için %s sayfa kararı okunamadı: %s", key[0], key[1], e)
            ok = False
        if not ok:
            cache.warm_skip(key)
            return
        try:
            await _fetch(key, _internal_headers(key[0]), warm=True)
        except Exception as e:  # noqa: BLE001 — sonraki gün yeniden denenir
            log.info("response cache: %s ısıtılamadı: %s", key[1], e)
        after = cache.peek(key)
        if after is not None and after is not before:
            cache.stats["warmed"] += 1
        else:
            cache.warm_skip(key)                    # hızlı çıktı, açılamadı ya da hata: 3 gün denenmez

    async def _warm_round(plan: list[tuple[str, str, str]]) -> None:
        """Tek sıra; en çok `WARM_CONCURRENCY` istek aynı anda (işçiler aynı sıradan çeker)."""
        it = iter(plan)

        async def worker() -> None:
            for key in it:
                await _warm(key)

        await asyncio.gather(*(worker() for _ in range(WARM_CONCURRENCY)))

    cache.warm_round = _warm_round        # teşhis ve test: bir planı hemen ısıtır

    started_loop: list[bool] = []

    @app.middleware("http")
    async def response_cache_mw(request: Request, call_next):
        if not started_loop:          # köprü lifespan kullandığı için startup olayı çalışmaz; ilk istekte başlar
            started_loop.append(True)
            asyncio.get_running_loop().create_task(_loop())
            asyncio.get_running_loop().create_task(_warm_loop())
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
        warming = revalidating and request.headers.get(WARM_HEADER) == cache.secret
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
        # peek: tazeleme ve ısıtma kaydın «istenme» anını uzatmaz.
        slow_enough = seconds >= SLOW_SECONDS or (force and cache.peek(key) is not None)
        if slow_enough and len(body) <= MAX_BODY:
            cache.put(key, body, headers, response.status_code, seconds, _replay_headers(request),
                      origin="warm" if warming else ("revalidate" if revalidating else "real"))
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

    async def _warm_loop() -> None:
        while True:
            await asyncio.sleep(30)
            try:
                if not enabled() or cache.may_open is None:
                    continue
                slot = cache.warm_slot_due()
                if slot is None:
                    continue
                cache.warm_mark(slot)          # önce işaret: tur uzun sürse de aynı saat ikinci kez başlamaz
                plan = cache.warm_plan()
                log.info("response cache: ısıtma başladı, %d kişi×uç", len(plan))
                await _warm_round(plan)
                log.info("response cache: ısıtma bitti (ısıtılan %d, atlanan %d)", cache.stats["warmed"],
                         cache.stats["warmSkipped"])
            except Exception:  # noqa: BLE001 — ısıtıcı durmasın
                log.exception("response cache: ısıtma turu hata verdi")

