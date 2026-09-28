"""Platform satıcı API istemcileri için **salt okunur** taban sınıf (M40 Trendyol, M41 Amazon kullanır; M42 ilk sürümde
kullanmaz).

Kullanıcı kararı (2026-09-28): pazar yerine yazma yok; mağazaya fiyat/stok/içerik gönderilmez. Koruma T-soft istemcisindeki
`READ_ONLY` desenidir (`seo_geo/connections.py`): alt sınıf izinli (yöntem, yol) desenlerini `ALLOWED`'da sayar; listede
olmayan her çağrı **ağa çıkmadan** `ReadOnlyViolation` atar. GET dışı yöntem ancak alt sınıf okuma olduğunu açıkça
yazarsa (ör. yalnız sorgu gövdesi alan bir arama ucu) izinlidir; yazma yöntemi hiçbir alt sınıfta tanımlanmaz ve testle
kilitlenir.

Kimlik bilgisi Yönetim → «Platform ve kanallar» (`admin.conf`) anahtarlarındadır; alt sınıf `CONF_KEYS` ile adlandırır.
Gizli değer hiçbir uçtan geri dönmez (`admin.py`'nin «secret» türü).
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable, Optional

import httpx


class ReadOnlyViolation(RuntimeError):
    """İzinli okuma listesi dışında bir çağrı denendi (hiçbir istek gönderilmedi)."""


class PlatformError(RuntimeError):
    """Kullanıcıya olduğu gibi gösterilecek Türkçe bağlantı hatası."""


class ReadOnlyClient:
    #: Platform anahtarı (`mapping.PLATFORMS`).
    platform: str = ""
    #: Taban adres ayarının anahtarı ve varsayılanı.
    BASE_KEY: str = ""
    BASE_DEFAULT: str = ""
    #: Kimlik ayarları: {"alan": "ADMIN_CONF_ANAHTARI"}.
    CONF_KEYS: dict[str, str] = {}
    #: İzinli çağrılar: (yöntem, yol deseni). Yalnız okuma.
    ALLOWED: tuple[tuple[str, str], ...] = ()
    #: Art arda iki çağrı arasında en az bu kadar saniye (platform hız sınırı).
    MIN_INTERVAL: float = 0.0

    def __init__(self, conf: Callable[[str], str], transport: Optional[httpx.BaseTransport] = None, timeout: float = 60):
        self._conf = conf
        self._transport = transport
        self._timeout = timeout
        self._last = 0.0
        self._allowed = [(m.upper(), re.compile(rx)) for m, rx in self.ALLOWED]

    # ------------------------------------------------------------------ ayar

    def creds(self) -> dict[str, str]:
        return {k: (self._conf(v) or "").strip() for k, v in self.CONF_KEYS.items()}

    def base(self) -> str:
        return ((self._conf(self.BASE_KEY) if self.BASE_KEY else "") or self.BASE_DEFAULT).rstrip("/")

    def configured(self) -> bool:
        c = self.creds()
        return bool(self.base()) and bool(c) and all(c.values())

    # ------------------------------------------------------------------ koruma

    def allowed(self, method: str, path: str) -> bool:
        m = method.upper()
        return any(m == am and rx.fullmatch(path) for am, rx in self._allowed)

    def guard(self, method: str, path: str) -> None:
        if not self.allowed(method, path):
            raise ReadOnlyViolation(f"Platforma yazma kapalı: «{method.upper()} {path}» gönderilmedi (yalnız okuma izinli).")

    # ------------------------------------------------------------------ çağrı

    def headers(self) -> dict[str, str]:
        """Alt sınıf kimlik başlıklarını üretir."""
        return {}

    def request(self, method: str, path: str, *, params: Optional[dict[str, Any]] = None, json_body: Any = None) -> Any:
        self.guard(method, path)                 # ağa çıkmadan önce
        if not self.configured():
            raise PlatformError("Platform bağlantısı tanımlı değil (Yönetim → Platform ve kanallar).")
        wait = self.MIN_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        with httpx.Client(timeout=self._timeout, transport=self._transport, follow_redirects=False) as c:
            resp = c.request(method.upper(), f"{self.base()}/{path.lstrip('/')}", params=params, json=json_body, headers=self.headers())
        self._last = time.monotonic()
        if resp.status_code in (401, 403):
            raise PlatformError("Platform kimlik bilgisi reddedildi.")
        if resp.status_code == 429:
            raise PlatformError("Platform hız sınırına takıldı; sonraki turda denenecek.")
        if resp.status_code >= 400:
            raise PlatformError(f"Platform {resp.status_code} döndü.")
        try:
            return resp.json()
        except ValueError:
            raise PlatformError("Platform cevabı okunamadı.") from None

    def get(self, path: str, params: Optional[dict[str, Any]] = None) -> Any:
        return self.request("GET", path, params=params)
