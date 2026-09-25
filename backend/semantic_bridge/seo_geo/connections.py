"""T-soft REST1 ve Google bağlantıları. Ayarlar Yönetim ekranından (`admin.conf`) okunur; sır dönmez.

T-soft yöntem ve alan adları mağazanın kendi konsolundaki katalogdan alındı (`/rest1/ConsoleHelper/getApiDetails`,
2026-09-25): giriş `auth/login/{kullanıcı}` + `pass`, sonraki çağrılar `token` parametresi taşır. Liste yöntemleri en
çok 500 kayıt döner, `start` ile sayfalanır. `updateProducts` gönderilen anahtarı yazar; gönderilmeyen alan
korunur (boş gönderilen alan sıfırlanır).

**T-soft'a yazma YASAK (kullanıcı kararı 2026-09-25):** bu istemci yalnız okur. `READ_ONLY` dışındaki her yöntem
(`update*`, `set*`, `delete*`, önbellek temizleme dahil) çağrılmadan hata atar. Onaylanan öneriler T-soft'a gitmez;
gidecekleri yer CRM'dir (Web API yetkisi bekleniyor).

Google için yeni bağımlılık yok: servis hesabı JWT'si sunucudaki `openssl` ile imzalanır, belirteç ve
Search Console çağrıları httpx ile yapılır.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import threading
import re
import time
from typing import Any, Optional

import httpx

log = logging.getLogger("semantic.seo_geo")

#: Bir liste çağrısında T-soft'un verdiği en çok kayıt (konsol: "Default:50, Max:500").
PAGE = 500

#: Çağrılmasına izin verilen T-soft yöntemleri: yalnız okuma. Liste dışı yol (yazma) hiç gönderilmez.
READ_ONLY = re.compile(r"^(auth/(login/[^/]+|isLogin)|[A-Za-z]+/get[A-Za-z]*(/[^/]*)?)$")


class ConnectionError_(RuntimeError):
    """Kullanıcıya olduğu gibi gösterilecek Türkçe bağlantı hatası."""


def _conf(key: str) -> str:
    from semantic_bridge import admin as admin_mod

    return (admin_mod.conf(key) or "").strip()


# ------------------------------------------------------------------------------------------------ T-soft

class TSoft:
    """Tek kullanıcılı T-soft istemcisi. Belirteç süreç içinde saklanır; geçersiz sayılırsa bir kez yeniden
    giriş yapılır. Kimlik bilgisi değişince (ekrandan kaydedilince) yeni girişe zorlanır."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._key: tuple[str, str, str] = ("", "", "")

    def _creds(self) -> tuple[str, str, str]:
        base, user, pw = _conf("TSOFT_BASE").rstrip("/"), _conf("TSOFT_USER"), _conf("TSOFT_PASSWORD")
        if not base or not user or not pw:
            raise ConnectionError_("T-soft kullanıcısı ya da şifresi girilmemiş (Yönetim → SEO & GEO).")
        return base, user, pw

    def configured(self) -> bool:
        try:
            self._creds()
            return True
        except ConnectionError_:
            return False

    @staticmethod
    def _body(resp: httpx.Response) -> dict[str, Any]:
        try:
            data = resp.json()
        except ValueError:
            raise ConnectionError_(f"T-soft beklenmeyen cevap verdi (HTTP {resp.status_code}).") from None
        if not isinstance(data, dict):
            raise ConnectionError_("T-soft cevabı okunamadı.")
        return data

    @staticmethod
    def _message(data: dict[str, Any]) -> str:
        msgs = data.get("message") or []
        if isinstance(msgs, list):
            texts = []
            for m in msgs:
                if isinstance(m, dict):
                    t = m.get("text")
                    texts.extend(t if isinstance(t, list) else [t] if t else [])
                    if m.get("code"):
                        texts.append(f"({m['code']})")
            return " ".join(str(t) for t in texts if t) or "T-soft isteği reddetti."
        return str(msgs) or "T-soft isteği reddetti."

    def _login(self) -> str:
        base, user, pw = self._creds()
        with httpx.Client(timeout=30, follow_redirects=False) as c:
            resp = c.post(f"{base}/auth/login/{user}", data={"pass": pw})
        data = self._body(resp)
        if not data.get("success"):
            raise ConnectionError_(f"T-soft girişi başarısız: {self._message(data)}")
        token = _find(data.get("data"), "token")
        if not token:
            raise ConnectionError_("T-soft girişi belirteç döndürmedi.")
        self._token, self._key = str(token), (base, user, pw)
        return self._token

    def call(self, path: str, params: Optional[dict[str, Any]] = None, *, timeout: float = 120) -> dict[str, Any]:
        """`path` örn. `product/get`. Yalnız okuma yöntemleri; başarısız cevapta Türkçe hata atar, belirteç düşmüşse bir
        kez yeniden girer."""
        if not READ_ONLY.match(path):
            raise ConnectionError_(f"T-soft'a yazma kapalı: «{path}» çağrılmadı (yalnız okuma izinli).")
        with self._lock:
            base, user, pw = self._creds()
            if self._token is None or self._key != (base, user, pw):
                self._login()
            token = self._token
        for attempt in (0, 1):
            form = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else
                        ("true" if v is True else "false" if v is False else str(v)))
                    for k, v in (params or {}).items() if v is not None}
            form["token"] = token
            with httpx.Client(timeout=timeout, follow_redirects=False) as c:
                resp = c.post(f"{base}/{path}", data=form)
            data = self._body(resp)
            if data.get("success"):
                return data
            msg = self._message(data)
            if attempt == 0 and ("token" in msg.lower() or "oturum" in msg.lower() or resp.status_code == 401):
                with self._lock:
                    token = self._login()
                continue
            raise ConnectionError_(f"T-soft {path}: {msg}")
        raise ConnectionError_(f"T-soft {path}: yeniden girişten sonra da reddedildi.")

    def products(self, start: int = 0, limit: int = PAGE) -> tuple[list[dict[str, Any]], Optional[int]]:
        """Bir sayfa ürün (ayrıntı ve görsellerle) ve varsa toplam kayıt sayısı."""
        data = self.call("product/get", {"start": start, "limit": limit, "FetchDetails": True,
                                         "FetchImageUrls": True, "FetchAllCategories": True})
        rows = data.get("data") or []
        total = None
        summary = data.get("summary")
        if isinstance(summary, dict):
            for k in ("totalRecordCount", "totalCount", "total"):
                if summary.get(k) is not None:
                    total = int(summary[k])
                    break
        return (rows if isinstance(rows, list) else []), total

    def product(self, product_id: str) -> Optional[dict[str, Any]]:
        data = self.call("product/get", {"ProductId": product_id, "FetchDetails": True, "FetchImageUrls": True})
        rows = data.get("data") or []
        return rows[0] if rows else None



def _find(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find(v, key)
            if found is not None:
                return found
    return None


tsoft = TSoft()


def tsoft_test() -> tuple[bool, str]:
    if not tsoft.configured():
        return False, "Kullanıcı ya da şifre girilmemiş."
    t0 = time.monotonic()
    rows, total = tsoft.products(0, 1)
    ms = int((time.monotonic() - t0) * 1000)
    if not rows:
        return True, f"Giriş başarılı, ürün listesi boş döndü ({ms} ms)."
    name = rows[0].get("ProductName") or rows[0].get("ProductCode") or "?"
    count = f"{total:,}".replace(",", ".") + " ürün" if total is not None else "ürün sayısı bildirilmedi"
    return True, f"Giriş başarılı, {count}; ilk kayıt «{name}» ({ms} ms)."


# ------------------------------------------------------------------------------------------------ Google

_GTOKEN: dict[str, Any] = {"token": None, "exp": 0.0, "key": ""}
_glock = threading.Lock()
SCOPES = "https://www.googleapis.com/auth/webmasters.readonly https://www.googleapis.com/auth/analytics.readonly"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _service_account() -> dict[str, Any]:
    raw = _conf("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise ConnectionError_("Google servis hesabı girilmemiş (Yönetim → SEO & GEO).")
    try:
        info = json.loads(raw)
    except ValueError:
        raise ConnectionError_("Servis hesabı JSON olarak okunamadı; dosyanın içeriğini olduğu gibi yapıştırın.") from None
    if info.get("type") != "service_account" or not info.get("private_key") or not info.get("client_email"):
        raise ConnectionError_("Bu bir servis hesabı anahtarı değil (type=service_account, private_key, client_email gerekli).")
    return info


def service_account_email() -> Optional[str]:
    try:
        return _service_account()["client_email"]
    except ConnectionError_:
        return None


def _sign(key_pem: str, payload: bytes) -> bytes:
    """RS256: sunucudaki openssl ile. Anahtar yalnız imza süresince 0600 geçici dosyada durur."""
    fd, path = tempfile.mkstemp(prefix="sa-", suffix=".pem")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key_pem)
        out = subprocess.run(["openssl", "dgst", "-sha256", "-sign", path], input=payload,
                             capture_output=True, timeout=20, check=False)
        if out.returncode != 0:
            raise ConnectionError_("Servis hesabı anahtarı imzalanamadı: " + out.stderr.decode(errors="replace")[:200])
        return out.stdout
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def google_token() -> str:
    info = _service_account()
    with _glock:
        if _GTOKEN["token"] and _GTOKEN["key"] == info["client_email"] and _GTOKEN["exp"] - 60 > time.time():
            return _GTOKEN["token"]
        now = int(time.time())
        head = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64(json.dumps({"iss": info["client_email"], "scope": SCOPES,
                                  "aud": info.get("token_uri") or "https://oauth2.googleapis.com/token",
                                  "iat": now, "exp": now + 3600}).encode())
        unsigned = f"{head}.{claims}".encode()
        jwt = unsigned.decode() + "." + _b64(_sign(info["private_key"], unsigned))
        with httpx.Client(timeout=30) as c:
            resp = c.post(info.get("token_uri") or "https://oauth2.googleapis.com/token",
                          data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt})
        if resp.status_code != 200:
            raise ConnectionError_(f"Google belirteci alınamadı: {resp.text[:200]}")
        body = resp.json()
        _GTOKEN.update(token=body["access_token"], exp=time.time() + int(body.get("expires_in", 3600)),
                       key=info["client_email"])
        return _GTOKEN["token"]


def _google(method: str, url: str, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    token = google_token()
    with httpx.Client(timeout=60) as c:
        resp = c.request(method, url, headers={"Authorization": f"Bearer {token}"}, json=body)
    if resp.status_code == 403:
        raise ConnectionError_(f"Google erişimi reddetti: servis hesabı ({service_account_email()}) bu mülke "
                               "kullanıcı olarak eklenmemiş olabilir.")
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", {}).get("message")
        except ValueError:
            msg = None
        raise ConnectionError_(f"Google {resp.status_code}: {msg or resp.text[:200]}")
    return resp.json()


def gsc_query(start: str, end: str, dimensions: list[str], *, row_limit: int = 25000,
              start_row: int = 0, filters: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Search Console arama analitiği. Tarihler YYYY-AA-GG; bir çağrıda en çok 25.000 satır."""
    site = _conf("GSC_SITE")
    if not site:
        raise ConnectionError_("Search Console mülkü girilmemiş.")
    from urllib.parse import quote

    body: dict[str, Any] = {"startDate": start, "endDate": end, "dimensions": dimensions,
                            "rowLimit": row_limit, "startRow": start_row, "dataState": "final"}
    if filters:
        body["dimensionFilterGroups"] = [{"filters": filters}]
    data = _google("POST", f"https://www.googleapis.com/webmasters/v3/sites/{quote(site, safe='')}/searchAnalytics/query", body)
    return data.get("rows") or []


def gsc_all(start: str, end: str, dimensions: list[str]) -> list[dict[str, Any]]:
    """Bütün satırlar: 25.000'lik sayfalarla, boş sayfa gelene kadar. Sessiz tavan yok."""
    out: list[dict[str, Any]] = []
    while True:
        rows = gsc_query(start, end, dimensions, start_row=len(out))
        out.extend(rows)
        if len(rows) < 25000:
            return out


def gsc_test() -> tuple[bool, str]:
    from datetime import date, timedelta

    end = date.today() - timedelta(days=3)
    rows = gsc_query((end - timedelta(days=6)).isoformat(), end.isoformat(), ["date"])
    clicks = sum(int(r.get("clicks", 0)) for r in rows)
    return True, (f"{_conf('GSC_SITE')} okundu: son 7 günde {clicks:,} tıklama".replace(",", ".")
                  + f" ({service_account_email()}).")
