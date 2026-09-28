"""M40 Trendyol satıcı API'si için **salt okunur** istemci — bu sürümde ağ kapalı.

İzinli çağrılar yalnız okumadır: ürün listesi, sipariş/paket listesi, iade (talep) listesi, müşteri soruları. Stok/fiyat
güncelleme, paket durumu, kargo etiketi, iade onayı, soru cevabı gibi her yazma yolu `ALLOWED`'da yoktur ve ağa çıkmadan
`ReadOnlyViolation` atar (testle kilitli). Kullanıcı kararı (2026-09-28) gereği `OfflineClient` okumayı da göndermez:
satış modeli ve anahtar netleşince yalnız `NETWORK = True` ile açılır; o gün de izin listesi aynı kalır.

Kimlik (ileride): satıcı no, API anahtarı, gizli anahtar — Yönetim → «Platform ve kanallar» (`admin.conf`); bu sürümde
ekranda alan açılmadı (bağlanılmayan bir anahtar istenmez).
"""
from __future__ import annotations

import base64

from semantic_bridge.channels.platform_common import OfflineClient

_S = r"\d+"   # satıcı no


class TrendyolClient(OfflineClient):
    platform = "trendyol"
    BASE_KEY = "TRENDYOL_API_BASE"
    BASE_DEFAULT = "https://apigw.trendyol.com/integration"
    CONF_KEYS = {"saticiNo": "TRENDYOL_SELLER_ID", "anahtar": "TRENDYOL_API_KEY", "gizli": "TRENDYOL_API_SECRET"}
    #: Yalnız GET ve yalnız listeleme uçları.
    ALLOWED = (
        ("GET", rf"product/sellers/{_S}/products"),
        ("GET", rf"order/sellers/{_S}/orders"),
        ("GET", rf"order/sellers/{_S}/claims"),
        ("GET", rf"qna/sellers/{_S}/questions/filter"),
    )
    MIN_INTERVAL = 1.0

    def headers(self) -> dict[str, str]:
        c = self.creds()
        token = base64.b64encode(f"{c.get('anahtar', '')}:{c.get('gizli', '')}".encode()).decode()
        return {"Authorization": f"Basic {token}", "User-Agent": f"{c.get('saticiNo', '')} - SelfIntegration"}

    def products(self, page: int = 0) -> dict:
        return self.get(f"product/sellers/{self.creds()['saticiNo']}/products", {"page": page, "size": 200})
