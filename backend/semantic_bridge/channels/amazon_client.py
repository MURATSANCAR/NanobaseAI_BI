"""M41 Amazon satıcı API'si için **salt okunur** istemci (analizde ikinci sürüm) — bu sürümde ağ kapalı.

İzinli çağrılar yalnız okumadır: sipariş ve sipariş kalemi listesi, depo stok özeti, katalog kaydı. Listeleme, fiyat,
stok, A+ içerik gibi her yazma yolu `ALLOWED`'da yoktur ve ağa çıkmadan `ReadOnlyViolation` atar. Erişim belirteci alma
adımı (kimlik sunucusuna POST) bu sürümde yazılmadı; hesap türü (satıcı/tedarikçi) ve yetki netleşince eklenir
(analiz §10 Soru 1). Kullanıcı kararı (2026-09-28) gereği `OfflineClient` hiçbir isteği göndermez.
"""
from __future__ import annotations

from semantic_bridge.channels.platform_common import OfflineClient


class AmazonClient(OfflineClient):
    platform = "amazon"
    BASE_KEY = "AMAZON_API_BASE"
    BASE_DEFAULT = "https://sellingpartnerapi-eu.amazon.com"
    CONF_KEYS = {"saticiNo": "AMAZON_SELLER_ID", "istemci": "AMAZON_LWA_CLIENT_ID", "gizli": "AMAZON_LWA_CLIENT_SECRET",
                 "yenileme": "AMAZON_LWA_REFRESH_TOKEN"}
    ALLOWED = (
        ("GET", r"orders/v0/orders"),
        ("GET", r"orders/v0/orders/[\w-]+/orderItems"),
        ("GET", r"fba/inventory/v1/summaries"),
        ("GET", r"catalog/2022-04-01/items/[\w-]+"),
    )
    MIN_INTERVAL = 1.0
