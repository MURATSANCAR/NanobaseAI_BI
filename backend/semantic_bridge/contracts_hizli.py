"""M6 sözleşme listesi ve özeti: ekranı açan kişi CRM'i beklemez (2026-09-29).

Neden yavaştı (test sunucusunda `X-Data-Refresh: 1` ile 11–14 sn): iki uç istek anında CRM'i okuyordu — özet üç sorgu
(`editorial.summary`: özet + iki süzgeç sayımı), liste dört sorgu (`editorial.page`: sayım, 50 satırlık liste — hak
bitleri ve lisans şartları aynı sorgunun kolonları ve beş LEFT JOIN'i —, sayfanın kitapları, tarafları). Satır başına
sorgu yok; ağırlık köprünün bütün Logo/CRM okumalarının tek bağlantı kilidinden (`Runtime._execute`) sırayla geçmesi:
yazar hazırlığı, editoryal masam ve yazar giriş turları (5 dk'da bir, bütün tabloları okur) sürerken uçtaki her sorgu
o turların sırasını bekliyordu. Özetin aynısı editoryal masam hazırlığında zaten 5 dakikada bir hesaplanıyordu.

Şimdi:
- **Özet**: editoryal masam hazırlığının `contracts` parçası (aynı işlev `editorial.summary`, aynı şema ve uyarı günü;
  kapsam klasörü bunları anahtarında taşır). Parça yoksa ya da iki tur aralığından eskiyse süreç içi bellekten
  (`OZET`), o da yoksa CRM'den.
- **Liste**: CRM parçası (`editorial.page` çıktısı) süreç içi bellekte (`LISTE`), anahtar kiracı + şema + sayfa + sıra +
  süzgeç. Portal rozeti (portalda düzenlenen sözleşme) her istekte portaldan okunur, bellekteki satırın kopyasına
  konur; bellekteki kayıt değişmez.
- Pencere köprünün sorgu önbelleğiyle aynı (`SEMANTIC_CACHE_TTL_SEC` taze, `SEMANTIC_STALE_MAX_SEC` bayat): taze kayıt
  hemen, bayat kayıt hemen + arkada yeniden okuma. «Verileri yenile» (`fresh`) eskisi gibi kaynağı bekler.
- Rakamlar değişmez: bellekteki değer aynı işlevin aynı girdiyle döndürdüğü değerdir; sorgu bilgisi (`contracts_kaynak`)
  aynı SQL'i gösterir, çalıştığı an `db.computedAt`'tir.
CRM'e yazma yok; sayı tavanı yok (bellek yalnız en eski anahtarı düşürür, sonuç kesilmez).
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Optional

from semantic_bridge import editorial as E
from semantic_bridge.editorial_home import INTERVAL, EditorialHomeSnapshots
from semantic_bridge.hizli_bellek import Bellek

TAZE = float(os.environ.get("SEMANTIC_CACHE_TTL_SEC", "300") or 300)
BAYAT = max(TAZE, float(os.environ.get("SEMANTIC_STALE_MAX_SEC", "900") or 900))

LISTE = Bellek("sozlesme.liste", taze=TAZE, bayat=BAYAT)
OZET = Bellek("sozlesme.ozet", taze=TAZE, bayat=BAYAT)

#: Hazırlık bundan eskiyse (tur durmuş) kullanılmaz: iki tur aralığı.
HAZIR_EN_ESKI = 2 * INTERVAL


def hazir_ozet(home: Any, warn_days: int, now: Optional[float] = None) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
    """Editoryal masam hazırlığındaki sözleşme özeti (veri, parça kaydı); yoksa, uyarı günü farklıysa ya da eskiyse None."""
    if home is None:
        return None
    try:
        part = EditorialHomeSnapshots.load(home.directory() / "contracts.json")
    except Exception:  # noqa: BLE001 — hazırlık okunamazsa canlı yol
        return None
    data = part.get("data")
    if not isinstance(data, dict) or data.get("warnDays") != int(warn_days):
        return None
    if (now if now is not None else time.time()) - float(part.get("updatedAt") or 0) > HAZIR_EN_ESKI:
        return None
    return data, part


def ozet(tenant: str, schema: str, run: Callable[[str], dict[str, Any]], warn_days: int, home: Any = None, *,
         fresh: bool = False) -> tuple[dict[str, Any], Optional[float]]:
    """Sözleşme özeti ve (hazırlıktan geldiyse) hazırlığın an'ı. `fresh`: kaynağı bekle (hazırlık da bellek de atlanır)."""
    if not fresh:
        got = hazir_ozet(home, warn_days)
        if got is not None:
            return dict(got[0]), float(got[1].get("updatedAt") or 0) or None
    out = OZET.al((tenant, schema, int(warn_days)), lambda: E.summary(schema, run, int(warn_days)), zorla=fresh)
    return out, None


def sayfa(tenant: str, schema: str, run: Callable[[str], dict[str, Any]], page_no: int, *, order: str,
          fresh: bool = False, **flt: Any) -> dict[str, Any]:
    """`editorial.page` ile aynı cevap; CRM parçası bellekte. Dönen sözlüğün `items` satırları kopyadır (uç portal
    rozetini ekleyebilir); iç içe listeler (kitaplar, taraflar, haklar) paylaşılır, değiştirilmez."""
    page_no = max(0, int(page_no))
    key = (tenant, schema, page_no, order, tuple(sorted(flt.items())))
    out = LISTE.al(key, lambda: E.page(schema, run, page_no, order=order, **flt), zorla=fresh)
    out["items"] = [dict(c) for c in out.get("items") or []]
    return out
