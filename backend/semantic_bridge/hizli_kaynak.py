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

Rakamlar değişmez: bellekteki değer aynı işlevin aynı SQL ile döndürdüğü değerdir. Sayı tavanı yok (bellek yalnız en
eski anahtarı düşürür, sonuç kesilmez). Kaynağa yazma yok.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any, Callable, Hashable, Optional

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


def bellek(ad: str, taze: float, bayat: Optional[float] = None, en_cok: int = 512) -> Bellek:
    taze = max(0.0, float(taze))
    return Bellek(ad, taze=taze, bayat=max(taze, bayat if bayat is not None else bayat_sn()), en_cok=en_cok)


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
