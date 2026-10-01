"""Kaynak (CRM/Logo) okumasını bellekte tutan uçlar için üç küçük parça (2026-09-29, pazarlama ve iletişim ekranları).

`hizli_bellek.Bellek` üstüne kurulur; modüllerin eski «10 dakika bellekte, süresi dolunca ekran CRM'i bekler»
önbelleklerinin yerini alır:

- `bellek(ad, taze)`: taze penceresi modülün eski süresi (ör. 600 sn), bayat penceresi `HIZLI_KAYNAK_BAYAT_SEC`
  (varsayılan 7 gün). Tazeyse hemen; bayatsa eldeki hemen döner ve kaynak arkada yeniden okunur (anahtar başına tek
  okuma); hiç yoksa ya da bayat penceresi de geçtiyse kaynak beklenir. Arkadaki okuma hata verirse eski değer kalır.
- `oku(b, anahtar, hesap, zorla=, durt=)`: `zorla` ekranın kendi «Yenile» düğmesi — kaynak beklenir (eski davranış).
  `durt` üst şeritteki «Verileri yenile» (`X-Data-Refresh: 1`) — eldeki değer hemen döner, 60 sn'den eskiyse kaynak
  arkada yeniden okunur (sosyal medya ve stok uçlarıyla aynı kural); eldeki değer yoksa beklenir.
- `acilista(ad, is_)`: köprü açıldıktan `SEMANTIC_WARM_DELAY_SEC` (20) sn sonra arkada bir kez ısıtır: ekranı yeniden
  başlatmadan sonra ilk açan kişi de kaynağı beklemesin. `SEMANTIC_WARM_START=0` ya da test süreci (pytest yüklü)
  kapatır; SQLite portal (testler) çağıranda ayrıca denetlenir (`sqlite_mi`).

- `Kalici(ad, motor, bicim)` (hız 4. tur, 2026-09-29): kişiden bağımsız kaynak okumasının son değeri portal tablosu
  `semantic_hizli_okuma`'da da durur (kiracı + bellek adı + anahtarın özeti başına tek satır; değer `typed_json` ile,
  pickle yok). Köprü yeniden başlayınca ekranı ilk açan kişi kaynağı beklemez: kayıt okunur, taze/bayat penceresi
  kaydın okunma anına göre işler (bayatsa eldeki hemen döner, kaynak arkada okunur). `bicim` okuma sorgusunun şeklidir;
  değişince eski kayıt kullanılmaz. `HIZLI_KAYIT=0` kapatır; `HIZLI_KAYIT_DSN` kaydı ayrı bir veritabanına yazar
  (yan port ölçümü: canlı portal tablosuna yazılmasın).

Rakamlar değişmez: bellekteki değer aynı işlevin aynı SQL ile döndürdüğü değerdir. Sayı tavanı yok (bellek yalnız en
eski anahtarı düşürür, sonuç kesilmez). Kaynağa yazma yok.
"""
from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Hashable, Optional

import sqlalchemy as sa

from semantic_bridge import typed_json as TJ
from semantic_bridge.hizli_bellek import Bellek

log = logging.getLogger("semantic.hizli_kaynak")

#: «Verileri yenile» ikinci kez basıldığında aynı okumayı yeniden başlatmamak için alt sınır (sn).
DURT_EN_AZ = 60.0
_KAPALI = ("0", "false", "no", "off", "hayir")


def bayat_sn() -> float:
    try:
        return max(0.0, float(os.environ.get("HIZLI_KAYNAK_BAYAT_SEC", str(7 * 86400))))
    except ValueError:
        return 7 * 86400.0


def bellek(ad: str, taze: float, bayat: Optional[float] = None, en_cok: int = 512, kalici: Any = None) -> Bellek:
    taze = max(0.0, float(taze))
    return Bellek(ad, taze=taze, bayat=max(taze, bayat if bayat is not None else bayat_sn()), en_cok=en_cok,
                  kalici=kalici)


# ------------------------------------------------------------------ kalıcı kayıt

_md = sa.MetaData()
OKUMA = sa.Table(
    "semantic_hizli_okuma", _md,  # kişiden bağımsız kaynak okumasının son değeri (hizli_kaynak.Kalici)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("ad", sa.String(80), primary_key=True),
    sa.Column("anahtar", sa.String(64), primary_key=True),       # anahtar metninin sha256'sı
    sa.Column("anahtar_metin", sa.Text, nullable=False),
    sa.Column("bicim", sa.String(64), nullable=False),
    sa.Column("veri", sa.LargeBinary, nullable=False),            # typed_json.pack
    sa.Column("okundu", sa.DateTime(timezone=True), nullable=False),
)
_ready: set[int] = set()
_ready_lock = threading.Lock()


def _ensure(engine: Any) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def kayit_acik() -> bool:
    return (os.environ.get("HIZLI_KAYIT", "1") or "1").strip().lower() not in _KAPALI


_ayri: dict[str, Any] = {}


def _ayri_motor() -> Any:
    """`HIZLI_KAYIT_DSN` verilmişse kayıt portal veritabanı yerine oraya yazılır (yan port ölçümü: canlı portal
    tablosuna yazmadan köprü yeniden başlama davranışını gerçek veriyle denemek için). Verilmemişse None."""
    dsn = (os.environ.get("HIZLI_KAYIT_DSN") or "").strip()
    if not dsn:
        return None
    with _ready_lock:
        if dsn not in _ayri:
            _ayri[dsn] = sa.create_engine(dsn)
        return _ayri[dsn]


class Kalici:
    """`Bellek`in kalıcı katmanı. `motor()` → (engine, kiracı) ya da None (bağlı değil: kayıt yok, bellek eskisi gibi).
    `bicim`: okuma sorgusunun şekli (SQL metninin özeti gibi); kayıttaki şekil farklıysa kayıt yok sayılır."""

    def __init__(self, ad: str, motor: Callable[[], Optional[tuple[Any, str]]], bicim: str = "") -> None:
        self.ad = ad[:80]
        self.motor = motor
        self.bicim = hashlib.sha256(bicim.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _anahtar(anahtar: Hashable) -> tuple[str, str]:
        metin = TJ.dumps(anahtar)
        return hashlib.sha256(metin.encode("utf-8")).hexdigest(), metin

    def _baglam(self) -> Optional[tuple[Any, str]]:
        if not kayit_acik():
            return None
        m = self.motor()
        if not m or m[0] is None:
            return None
        engine = _ayri_motor() or m[0]
        _ensure(engine)
        return engine, m[1]

    def yukle(self, anahtar: Hashable) -> Optional[tuple[Any, float]]:
        m = self._baglam()
        if m is None:
            return None
        engine, tenant = m
        h, _ = self._anahtar(anahtar)
        with engine.connect() as c:
            r = c.execute(sa.select(OKUMA.c.veri, OKUMA.c.okundu, OKUMA.c.bicim).where(
                OKUMA.c.tenant_id == tenant, OKUMA.c.ad == self.ad, OKUMA.c.anahtar == h)).first()
        if r is None or r.bicim != self.bicim:
            return None
        at = r.okundu if r.okundu.tzinfo else r.okundu.replace(tzinfo=timezone.utc)
        return TJ.unpack(r.veri), at.timestamp()

    def yaz(self, anahtar: Hashable, deger: Any, an: float) -> None:
        m = self._baglam()
        if m is None:
            return
        engine, tenant = m
        h, metin = self._anahtar(anahtar)
        veri = TJ.pack(deger)                     # tanınmayan tür TypeError: kayıt yazılmaz, değer bellekte kalır
        with engine.begin() as c:
            c.execute(OKUMA.delete().where(OKUMA.c.tenant_id == tenant, OKUMA.c.ad == self.ad, OKUMA.c.anahtar == h))
            c.execute(OKUMA.insert().values(tenant_id=tenant, ad=self.ad, anahtar=h, anahtar_metin=metin[:4000],
                                            bicim=self.bicim, veri=veri,
                                            okundu=datetime.fromtimestamp(an, timezone.utc)))


def oku(b: Bellek, anahtar: Hashable, hesap: Callable[[], Any], *, zorla: bool = False, durt: bool = False) -> Any:
    """Bellekten ya da kaynaktan. `zorla`: kaynak beklenir. `durt`: eldeki döner, 60 sn'den eskiyse arkada okunur."""
    if durt and not zorla:
        yas = b.yas(anahtar)
        if yas is not None:
            eldeki = b.al(anahtar, hesap)      # önce eldeki: arkadaki okuma hızlı bitse de bu istek beklemez, eldekini alır
            if yas >= DURT_EN_AZ:
                b.isit(anahtar, hesap)
            return eldeki
    return b.al(anahtar, hesap, zorla=zorla)


def sqlite_mi(engine: Any) -> bool:
    try:
        return engine.dialect.name == "sqlite"
    except Exception:  # noqa: BLE001 — motor yoksa ısıtma yapılmaz
        return True


def _kapali() -> bool:
    if (os.environ.get("SEMANTIC_WARM_START", "1") or "1").strip().lower() in _KAPALI:
        return True
    return "pytest" in sys.modules


def acilista(ad: str, is_: Callable[[], Any], gecikme: Optional[float] = None, *, zorla: bool = False) -> Optional[threading.Timer]:
    """Köprü açılışında arkada bir kez çalıştırır (hata günlüğe yazılır, ekranı etkilemez). `zorla`: denetimsiz (test)."""
    if not zorla and _kapali():
        return None
    if gecikme is None:
        try:
            gecikme = max(0.0, float(os.environ.get("SEMANTIC_WARM_DELAY_SEC", "20")))
        except ValueError:
            gecikme = 20.0

    def run() -> None:
        try:
            is_()
        except Exception as e:  # noqa: BLE001 — ısıtılamazsa ilk açılış kendisi okur
            log.info("%s: açılışta ısıtılamadı: %s", ad, e)

    t = threading.Timer(gecikme, run)
    t.name = f"isit:{ad}"
    t.daemon = True
    t.start()
    return t
