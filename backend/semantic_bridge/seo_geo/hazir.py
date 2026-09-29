"""SEO & GEO: hazır hesap — ağır ekran hesabı girdisinin damgasıyla saklanır (2026-09-29, ekran hızı).

Neden: sorgu–sayfa eşlemesi, rehber konuları, yazar güveni, sayfalar, özet, yarışan sayfalar, soru–cevap listesi, okur
yorumları, biyografiler ve ürün sırası her istekte bütün T-soft ürün JSON'unu açıyor, Search Console satırlarını yeniden
işliyordu (test sunucusunda hazır cevap atlanınca 2–87 sn). Hesap artık `semantic_seo_hazir`'da durur:

- İstek önce girdilerin damgasını ölçer (tek sorgu: girdi tablosu başına satır sayısı + son yazım zamanı, hesaba giren
  ayarlar) ve kayıttaki damgaya bakar. Aynıysa sonuç süreç belleğinden ya da tablodan gelir. Girdi değiştiyse (gece
  eşitlemesi, «yeniden oku», karar) hesap o istekte bir kez yapılır ve yazılır — rakam hiçbir zaman eski girdiden gelmez.
- Gece turu, eşitlemeler bittikten sonra kayıtlı bütün hesapları ısıtır (`isit`): ekranı ilk açan da beklemez.
  Köprü açılışında da (`acilis`) kaydı olmayan ya da girdisi değişmiş hesap arkada hesaplanır, güncel kayıt belleğe
  alınır (2. tur, 2026-09-29: genel bakış kayıt yokken 12 sn bekliyordu).
- 2. turda eklenenler: site içi bağlantılar (grafik hesabı 53 sn), fırsat listesi ve ürün adres eşlemesi, kimlik
  (yazar toplamı + Google Kitaplar satırları), Google taraması (ürün bilgisi + denetim kayıtları), alışveriş denetimi,
  CRM listesinin sıra/süzgeç alanları.
- Sorgu bilgisi: hesap sırasında çalışan okumalar `semantic_query_origin`'e (`seo.hazir.<ad>`) yazılır; hazır kaydı
  okuyan sorgunun kökeni olarak «i» penceresinde görünür (kaynak.py).

Kayıt, ekranın göstereceği sonucun kendisidir; kesme/tavan yoktur. T-soft'a, CRM'e, Logo'ya hiçbir şey yazılmaz.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from contextvars import ContextVar
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional, Sequence

import sqlalchemy as sa

from semantic_bridge import sorgu_yakala as Y

from .store import _md, iso, now

log = logging.getLogger("semantic.seo_geo.hazir")

HAZIR = sa.Table(
    "semantic_seo_hazir", _md,  # ekran hesabının son sonucu + girdilerinin damgası
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("name", sa.String(80), primary_key=True),
    sa.Column("stamp", sa.Text, nullable=False),
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("compute_ms", sa.Integer),
)
KOKEN = "seo.hazir."

#: Bu istekte okunan hazır hesapların adları (kaynak.py ara katmanı kurar; köken eklemek için).
OKUNAN: ContextVar[Optional[list[str]]] = ContextVar("seo_hazir_okunan", default=None)

_ready: set[int] = set()
_ready_lock = threading.Lock()
_mem: dict[tuple[int, str, str], tuple[str, Any]] = {}
_mem_lock = threading.Lock()
_key_locks: dict[tuple[int, str, str], threading.Lock] = {}
_MISSING = object()


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        HAZIR.create(engine, checkfirst=True)
        _ready.add(id(engine))


def _plain(v: Any) -> Any:
    if isinstance(v, datetime):
        return iso(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _encode(v: Any) -> Any:
    """JSON'a çevrilemeyen değer: tarih ekrana giden biçimde (ISO); küme/demet gibi belirsiz tip sessizce çevrilmez."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    raise TypeError(f"hazır hesapta JSON'a çevrilemeyen değer: {type(v).__name__}")


def damga(seo: Any, girdiler: Sequence[tuple], ek: Iterable[Any] = ()) -> str:
    """Girdilerin damgası: `girdiler` = [(tablo, zaman kolonu | None, *ek koşullar)] → tablo başına (satır sayısı, en son
    zaman). Tek sorguda ölçülür. `ek`: hesaba giren ayarlar (site adresi, eşikler)."""
    tenant = seo.tenant()
    cols: list[Any] = []
    for i, g in enumerate(girdiler):
        table, col, *cond = g
        where = [table.c.tenant_id == tenant, *cond]
        cols.append(sa.select(sa.func.count()).select_from(table).where(*where).scalar_subquery().label(f"n{i}"))
        if col is not None:
            cols.append(sa.select(sa.func.max(col)).where(*where).scalar_subquery().label(f"t{i}"))
    row: Sequence[Any] = ()
    if cols:
        with seo.engine().connect() as c:
            row = tuple(c.execute(sa.select(*cols)).first() or ())
    return json.dumps([_plain(v) for v in row] + [_plain(v) for v in ek], ensure_ascii=False, default=str)


def _lock_for(key: tuple[int, str, str]) -> threading.Lock:
    with _mem_lock:
        lk = _key_locks.get(key)
        if lk is None:
            lk = _key_locks[key] = threading.Lock()
        return lk


def _stored_stamp(eng: sa.engine.Engine, tenant: str, name: str) -> Optional[str]:
    with eng.connect() as c:
        return c.execute(sa.select(HAZIR.c.stamp).where(HAZIR.c.tenant_id == tenant, HAZIR.c.name == name)).scalar()


def _stored_data(eng: sa.engine.Engine, tenant: str, name: str, stamp: str) -> Any:
    with eng.connect() as c:
        raw = c.execute(sa.select(HAZIR.c.data_json).where(HAZIR.c.tenant_id == tenant, HAZIR.c.name == name,
                                                           HAZIR.c.stamp == stamp)).scalar()
    if raw is None:
        return _MISSING
    try:
        return json.loads(raw)
    except ValueError:
        return _MISSING


def al(seo: Any, name: str, stamp: str, hesapla: Callable[[], Any]) -> Any:
    """Damgası `stamp` olan hesabın sonucu: bellek → tablo → (yoksa) hesapla + yaz. Dönen değer her yolda aynı biçimdedir
    (JSON'dan geçmiş: demet liste olur), böylece ilk hesap ile sonraki okuma birebir aynı cevabı verir."""
    eng, tenant = seo.engine(), seo.tenant()
    ensure(eng)
    okunan = OKUNAN.get()
    if okunan is not None and name not in okunan:
        okunan.append(name)
    key = (id(eng), tenant, name)
    stored = _stored_stamp(eng, tenant, name)
    with _mem_lock:
        m = _mem.get(key)
    if stored == stamp and m is not None and m[0] == stamp:
        return m[1]
    if stored == stamp:
        data = _stored_data(eng, tenant, name, stamp)
        if data is not _MISSING:
            with _mem_lock:
                _mem[key] = (stamp, data)
            return data
    with _lock_for(key):
        with _mem_lock:
            m = _mem.get(key)
        if m is not None and m[0] == stamp:     # aynı anda gelen istek az önce hesapladı
            return m[1]
        t0 = time.monotonic()
        with Y.yakala(eng) as y:
            raw = hesapla()
        text = json.dumps(raw, ensure_ascii=False, default=_encode, separators=(",", ":"))
        data = json.loads(text)
        ms = int((time.monotonic() - t0) * 1000)
        try:
            with eng.begin() as c:
                c.execute(HAZIR.delete().where(HAZIR.c.tenant_id == tenant, HAZIR.c.name == name))
                c.execute(HAZIR.insert().values(tenant_id=tenant, name=name, stamp=stamp, data_json=text,
                                                computed_at=now(), compute_ms=ms))
            Y.koken_yaz(eng, tenant, KOKEN + name, y, connections=("portal", "logo", "crm"))
        except Exception as e:  # noqa: BLE001 — yazılamasa da sonuç bu istekte doğru döner
            log.warning("hazır hesap yazılamadı (%s): %s", name, e)
        with _mem_lock:
            _mem[key] = (stamp, data)
        log.info("seo hazır hesap %s: %d ms", name, ms)
        return data


def son(seo: Any, name: str) -> Optional[tuple[Any, float]]:
    """Damgasına bakmadan son kayıt: (sonuç, kaç saniye önce hesaplandı); kayıt yoksa None. Yalnız girdisi tur boyunca
    her saniye değişen hesap için (teknik tarama sürerken bağlantı grafiği): tur sürerken son hesap gösterilir, ekranda
    hesap zamanı yazar; tur bitince damga yeniden bağlar."""
    eng, tenant = seo.engine(), seo.tenant()
    ensure(eng)
    okunan = OKUNAN.get()
    if okunan is not None and name not in okunan:
        okunan.append(name)
    with eng.connect() as c:
        row = c.execute(sa.select(HAZIR.c.stamp, HAZIR.c.computed_at).where(HAZIR.c.tenant_id == tenant,
                                                                            HAZIR.c.name == name)).first()
    if row is None:
        return None
    stamp, at = row
    key = (id(eng), tenant, name)
    with _mem_lock:
        m = _mem.get(key)
    if m is not None and m[0] == stamp:
        data = m[1]
    else:
        data = _stored_data(eng, tenant, name, stamp)
        if data is _MISSING:
            return None
        with _mem_lock:
            _mem[key] = (stamp, data)
    if at is not None and at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return data, ((now() - at).total_seconds() if at is not None else float("inf"))


_arkada: set[tuple[int, str, str]] = set()


def al_arkada(seo: Any, name: str, stamp: str, hesapla: Callable[[], Any]) -> bool:
    """`al`'ı kendi iş parçacığında koşturur (istek beklemez). Aynı hesap zaten arkada koşuyorsa yenisi başlamaz."""
    eng, tenant = seo.engine(), seo.tenant()
    key = (id(eng), tenant, name)
    with _mem_lock:
        if key in _arkada:
            return False
        _arkada.add(key)

    def run() -> None:
        try:
            al(seo, name, stamp, hesapla)
        except Exception:  # noqa: BLE001 — sonraki istek yine dener
            log.exception("seo hazır arka plan hesabı %s", name)
        finally:
            with _mem_lock:
                _arkada.discard(key)

    threading.Thread(target=run, name=f"seo-hazir-{name}", daemon=True).start()
    return True


def unut() -> None:
    """Süreç belleğini boşaltır (testler için; tablo kalır)."""
    with _mem_lock:
        _mem.clear()


# ------------------------------------------------------------------ gece ısıtması
def kaydet(seo: Any, name: str, fn: Callable[[], Any]) -> None:
    """Gece ısıtılacak hesap: `fn()` hesabı `al` üzerinden çağırır (damgası güncelse iş yapmaz)."""
    lst = getattr(seo, "hazir_isiticilar", None)
    if lst is None:
        lst = []
        setattr(seo, "hazir_isiticilar", lst)
    lst.append((name, fn))


def mesgul(seo: Any, fn: Callable[[], bool]) -> None:
    """Isıtmadan önce bitmesi beklenen arka plan okuması (T-soft/CRM/yorum okuması sürüyor mu)."""
    lst = getattr(seo, "hazir_mesgul", None)
    if lst is None:
        lst = []
        setattr(seo, "hazir_mesgul", lst)
    lst.append(fn)


def _busy(seo: Any) -> bool:
    for fn in getattr(seo, "hazir_mesgul", None) or []:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def isit(seo: Any, wait: Optional[float] = None, poll: float = 15.0) -> dict[str, Any]:
    """Arka plan okumaları bitince (en çok `wait` sn; ayar `SEO_HAZIR_WAIT`, varsayılan 7200) kayıtlı hesapları
    sırayla ısıtır. Bir hesap düşerse ötekiler sürer."""
    if wait is None:
        try:
            wait = float(seo.conf("SEO_HAZIR_WAIT") or 7200)
        except (TypeError, ValueError):
            wait = 7200.0
    deadline = time.monotonic() + max(0.0, wait)
    while _busy(seo) and time.monotonic() < deadline:
        time.sleep(poll)
    out: dict[str, Any] = {}
    for name, fn in list(getattr(seo, "hazir_isiticilar", None) or []):
        t0 = time.monotonic()
        try:
            fn()
            out[name] = int((time.monotonic() - t0) * 1000)
        except Exception as e:  # noqa: BLE001
            out[name] = f"hata: {e}"
            log.exception("seo hazır ısıtma %s", name)
    log.info("seo hazır ısıtma: %s", out)
    return out


def isit_arkada(seo: Any) -> None:
    """Gece işinden çağrılır: bekleme gece sırasını (öneri/tarama turlarını) tutmasın diye kendi iş parçacığında."""
    threading.Thread(target=isit, args=(seo,), name="seo-hazir-isit", daemon=True).start()


def _off(v: Any) -> bool:
    return str(v or "").strip().lower() in ("0", "false", "no", "off", "hayir", "hayır")


def acilis(seo: Any, poll: float = 5.0, wait: float = 900.0) -> bool:
    """Köprü açılışı: veritabanı hazır olunca kayıtlı bütün hesaplar arkada ısıtılır. Kaydı olmayan ya da girdisi
    değişmiş hesap bu turda hesaplanıp yazılır; güncel kayıt yalnız belleğe alınır. Böylece köprü yeniden kalktıktan sonra
    ekranı ilk açan da (genel bakış, soru–cevap…) hesabı beklemez.

    Kapatmak: ortam `SEO_HAZIR_ACILIS=0`. Test veritabanında (SQLite, tek bağlantı) çalışmaz: arka plan iş parçacığı
    testin kendi okumalarıyla yarışırdı (veri sözlüğü ısıtmasıyla aynı kural). Dönen: iş parçacığı başladı mı."""
    import os

    if _off(os.environ.get("SEO_HAZIR_ACILIS", "1")):
        return False

    def raw_engine() -> Any:
        """Bağlantı açmadan motor (lehçesine bakmak için); çalışma ortamı henüz kurulmadıysa hata."""
        rt = getattr(seo, "runtime", None)
        return rt().store.engine if callable(rt) else seo.engine()

    try:
        if raw_engine().dialect.name == "sqlite":
            return False
    except Exception:  # noqa: BLE001 — çalışma ortamı açılışta kurulur; iş parçacığı bekler
        pass

    def run() -> None:
        deadline = time.monotonic() + max(0.0, wait)
        eng = None
        while eng is None:
            try:
                eng = raw_engine()        # köprü çalışma ortamı açılışta kurulur; hazır olana kadar beklenir
            except Exception:  # noqa: BLE001
                if time.monotonic() >= deadline:
                    log.info("seo hazır açılış ısıtması: veritabanı hazır olmadı, atlandı")
                    return
                time.sleep(poll)
        if eng.dialect.name == "sqlite":
            return
        try:
            if _off(seo.conf("SEO_HAZIR_ACILIS")):
                return
        except Exception:  # noqa: BLE001
            pass
        isit(seo, wait=0, poll=poll)

    threading.Thread(target=run, name="seo-hazir-acilis", daemon=True).start()
    return True
