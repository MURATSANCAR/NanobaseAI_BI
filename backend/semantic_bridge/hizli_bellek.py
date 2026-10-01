"""Uç içi kısa bellek: ağır okumanın sonucu süreçte tutulur, ekranı açan kişi kaynağı beklemez (2026-09-29).

Neden: hazır cevap katmanı (`response_cache`) cevabı saklar ama «Yenile», ilk açılış ve köprü yeniden başlaması uçta
kendi hesabını koşturur; canlı CRM/Logo okuması ya da bütün tabloyu okuyan hesap o anda saniyelerce sürer. Bu bellek
ucun **kendi** ağır parçasını (kaynak okuması, büyük sözlük kurulumu) anahtar başına tutar:

- Yaşı `taze` saniyeden küçükse hemen döner.
- `taze` ile `bayat` arasındaysa eldeki değer hemen döner, aynı anda arkada yeniden hesaplanır (anahtar başına tek iş).
- Hiç yoksa ya da `bayat`tan eskiyse hesap beklenir; aynı anahtarı aynı anda isteyenler tek hesabı bekler (kaynağa
  ikinci yük binmez).
- `zorla=True` (ör. «Verileri yenile» kaynağı beklesin isteyen uç) beklenerek yeniden hesaplar.
- Arkadaki hesap hata verirse eski değer kalır, hata günlüğe yazılır; beklenen hesap hatası çağırana gider.

Anahtar kiracı + parametredir (kişiye özel sonuç kişi adını anahtara koymalıdır). Değer değiştirilmez kabul edilir:
sözlük dönen değerin sığ kopyası verilir (uç `kaynaklar` gibi üst anahtar ekleyebilir); iç içe yapıyı değiştiren uç
kendisi kopyalamalıdır. Yazma uçları `dusur()` ile ilgili anahtarları düşürür. Sayı tavanı yok: `en_cok` yalnız bellek
koruması (en eski kullanılan düşer, sonuç kesilmez).

Kalıcı katman (hız 4. tur, 2026-09-29): `kalici` verilirse (bkz. `hizli_kaynak.Kalici`) hesaplanan her değer portal
tablosuna da yazılır; süreçte değeri olmayan anahtar ilk istendiğinde önce oradan okunur (köprü yeniden başlayınca kişi
kaynağı beklemez, taze/bayat penceresi kaydın okunma anına göre işler). Kayıt okunamaz ya da yazılamazsa bellek eskisi
gibi çalışır.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Hashable, Optional

log = logging.getLogger("semantic.hizli_bellek")

#: Bütün bellekler (ısıtma ve teşhis için ada göre).
KAYIT: dict[str, "Bellek"] = {}


class _Kayit:
    __slots__ = ("deger", "an", "is_", "kilit", "diskte")

    def __init__(self) -> None:
        self.deger: Any = None
        self.an: float = 0.0          # 0 = hiç hesaplanmadı
        self.is_: bool = False        # arkada hesap sürüyor
        self.kilit = threading.Lock()  # beklenen hesap (tek uçuş)
        self.diskte = False           # kalıcı kayda bir kez bakıldı


class Bellek:
    def __init__(self, ad: str, taze: float, bayat: Optional[float] = None, en_cok: int = 512,
                 kalici: Any = None) -> None:
        self.ad = ad
        self.taze = float(taze)
        self.bayat = float(bayat) if bayat is not None else float(taze)
        self.en_cok = int(en_cok)
        #: `yukle(anahtar) -> (deger, an) | None` ve `yaz(anahtar, deger, an)` veren katman (hizli_kaynak.Kalici).
        self.kalici = kalici
        self._k: "OrderedDict[Hashable, _Kayit]" = OrderedDict()
        self._lock = threading.Lock()
        self.sayac = {"isabet": 0, "bayat": 0, "hesap": 0, "arka": 0, "hata": 0}
        #: Son `dusur` anı: bundan önce yazılmış kalıcı kayıt yüklenmez (düşürülen değer diskten geri gelmesin).
        self._dusuldu = 0.0
        KAYIT[ad] = self

    # ------------------------------------------------------------------ iç
    def _kayit(self, anahtar: Hashable) -> _Kayit:
        with self._lock:
            k = self._k.get(anahtar)
            if k is None:
                k = self._k[anahtar] = _Kayit()
                while len(self._k) > self.en_cok:
                    self._k.popitem(last=False)
            else:
                self._k.move_to_end(anahtar)
            return k

    @staticmethod
    def _ver(deger: Any) -> Any:
        return dict(deger) if isinstance(deger, dict) else deger

    def _diskten(self, anahtar: Hashable, k: _Kayit) -> None:
        """Süreçte değeri olmayan anahtar: kalıcı kayıt bir kez okunur (hata olursa kaynak beklenir)."""
        if self.kalici is None or k.diskte or k.an:
            return
        with k.kilit:
            if k.diskte or k.an:
                return
            k.diskte = True
            try:
                got = self.kalici.yukle(anahtar)
            except Exception as e:  # noqa: BLE001 — kayıt okunamazsa kaynaktan okunur
                log.warning("%s: kalıcı kayıt okunamadı (%r): %s", self.ad, anahtar, e)
                return
            if got is not None and not k.an and got[1] > self._dusuldu:
                k.deger, k.an = got
                self.sayac["kayit"] = self.sayac.get("kayit", 0) + 1

    def _hesapla(self, k: _Kayit, hesap: Callable[[], Any], istek_an: float, anahtar: Hashable = None) -> Any:
        with k.kilit:
            if k.an and k.an >= istek_an:        # beklerken başka biri hesapladı
                return k.deger
            deger = hesap()
            k.deger, k.an = deger, time.time()
            k.diskte = True
            self.sayac["hesap"] += 1
        if self.kalici is not None:
            try:
                self.kalici.yaz(anahtar, deger, k.an)
            except Exception as e:  # noqa: BLE001 — kayıt yazılamasa da değer ekrana gider
                log.warning("%s: kalıcı kayıt yazılamadı (%r): %s", self.ad, anahtar, e)
        return deger

    def _arkada(self, anahtar: Hashable, k: _Kayit, hesap: Callable[[], Any]) -> None:
        with self._lock:
            if k.is_:
                return
            k.is_ = True

        def run() -> None:
            try:
                self._hesapla(k, hesap, time.time(), anahtar)
                self.sayac["arka"] += 1
            except Exception as e:  # noqa: BLE001 — eski değer gösterilmeye devam eder
                self.sayac["hata"] += 1
                log.warning("%s: arka plan hesabı başarısız (%r): %s", self.ad, anahtar, e)
            finally:
                k.is_ = False

        threading.Thread(target=run, name=f"bellek:{self.ad}", daemon=True).start()

    # ------------------------------------------------------------------ dış
    def al(self, anahtar: Hashable, hesap: Callable[[], Any], *, zorla: bool = False) -> Any:
        k = self._kayit(anahtar)
        if not zorla:
            self._diskten(anahtar, k)
        simdi = time.time()
        if not zorla and k.an:
            yas = simdi - k.an
            if yas < self.taze:
                self.sayac["isabet"] += 1
                return self._ver(k.deger)
            if yas < self.bayat:
                self.sayac["bayat"] += 1
                deger = k.deger
                self._arkada(anahtar, k, hesap)
                return self._ver(deger)
        return self._ver(self._hesapla(k, hesap, simdi, anahtar))

    def isit(self, anahtar: Hashable, hesap: Callable[[], Any]) -> None:
        """Beklemeden arkada hesaplar (açılışta ya da tur sonunda ısıtma)."""
        self._arkada(anahtar, self._kayit(anahtar), hesap)

    def isit_gerekirse(self, anahtar: Hashable, hesap: Callable[[], Any]) -> bool:
        """Açılış ısıtması: değer (süreçte ya da kalıcı kayıtta) tazeyse bir şey yapmaz; değilse arkada hesaplar."""
        k = self._kayit(anahtar)
        self._diskten(anahtar, k)
        if k.an and time.time() - k.an < self.taze:
            return False
        self._arkada(anahtar, k, hesap)
        return True

    def yas(self, anahtar: Hashable) -> Optional[float]:
        with self._lock:
            k = self._k.get(anahtar)
        if self.kalici is not None and (k is None or not k.an):
            k = self._kayit(anahtar)
            self._diskten(anahtar, k)
        return None if k is None or not k.an else time.time() - k.an

    def an(self, anahtar: Hashable) -> Optional[float]:
        """Değerin hesaplandığı an (epoch) ya da None."""
        with self._lock:
            k = self._k.get(anahtar)
        return None if k is None or not k.an else k.an

    def dusur(self, sart: Optional[Callable[[Hashable], bool]] = None) -> int:
        """Anahtarları düşürür (şart yoksa hepsi); sonraki okuma yeniden hesaplar."""
        with self._lock:
            silinecek = [a for a in self._k if sart is None or sart(a)]
            for a in silinecek:
                del self._k[a]
            self._dusuldu = time.time()
        return len(silinecek)
