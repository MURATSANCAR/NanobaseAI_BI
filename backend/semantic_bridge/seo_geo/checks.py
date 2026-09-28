"""Yönetim → SEO & GEO «Bağlantıyı sına»: girilmiş her anahtar ayrı ayrı, yalnız okuyarak denenir.

Her deneme ücretsiz ve kotasız bir okuma çağrısıdır (hesap/anahtar doğrulama, model listesi, tek kayıt). Hiçbir
yere yazılmaz; T-soft'a yalnız ürün listesi okunur. Soru başına ücret alan motorlarda (Perplexity) soru
sorulmaz, anahtarın girildiği söylenir. Mesajlara anahtar ya da istek adresi yazılmaz: hata metni anahtarı
içerebileceği için anahtar değeri metinden silinir.

Sonuç parçaları: `state` = ok (bağlandı) · err (hata) · off (girilmemiş). Grubun sonucu, girilmiş bütün
parçalar başarılıysa başarılıdır; hiçbiri girilmemişse hata sayılır.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

import httpx

from semantic_bridge.seo_geo import connections

Part = dict[str, Any]
TIMEOUT = 25


def _conf(key: str) -> str:
    return connections._conf(key)


def _site() -> str:
    return (_conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")


def _clean(msg: str, *secrets: str) -> str:
    for s in secrets:
        if s:
            msg = msg.replace(s, "•••")
    return msg[:300]


def _err_text(r: httpx.Response) -> str:
    try:
        body = r.json()
    except ValueError:
        return r.text[:200]
    err = body.get("error") if isinstance(body, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err)[:200]
    if isinstance(body, dict):
        for k in ("message", "Message", "errors"):
            if body.get(k):
                return str(body[k])[:200]
    return str(err or body)[:200]


def _get(url: str, *, params: Optional[dict[str, str]] = None, headers: Optional[dict[str, str]] = None,
         secret: str = "") -> tuple[Optional[httpx.Response], str]:
    """(cevap, hata metni). Ağ hatasında cevap None; metinde anahtar geçmez."""
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as c:
            return c.get(url, params=params, headers=headers), ""
    except httpx.HTTPError as e:
        return None, _clean(f"Ulaşılamadı: {type(e).__name__}: {e}", secret)


def _run(label: str, fn: Callable[[], tuple[str, str]], *secrets: str) -> Part:
    t0 = time.monotonic()
    try:
        state, message = fn()
    except connections.ConnectionError_ as e:
        state, message = "err", str(e)
    except Exception as e:  # noqa: BLE001 — deneme hiçbir hatada düşmez, satırda gösterir
        state, message = "err", f"{type(e).__name__}: {e}"
    return {"label": label, "state": state, "message": _clean(message, *secrets),
            "ms": int((time.monotonic() - t0) * 1000)}


def _off(label: str, what: str) -> Part:
    return {"label": label, "state": "off", "message": f"{what} girilmemiş.", "ms": 0}


# ------------------------------------------------------------------------------------------------ SEO

def _tsoft() -> tuple[str, str]:
    ok, msg = connections.tsoft_test()
    return ("ok" if ok else "err"), msg


def _gsc() -> tuple[str, str]:
    if not _conf("GSC_SITE"):
        return "err", "Servis hesabı girilmiş ama Search Console mülkü (GSC_SITE) boş."
    ok, msg = connections.gsc_test()
    return ("ok" if ok else "err"), msg


def _ga4() -> tuple[str, str]:
    prop = _conf("GA4_PROPERTY_ID").removeprefix("properties/")
    token = connections.google_token()
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport",
                       headers={"Authorization": f"Bearer {token}"},
                       json={"dateRanges": [{"startDate": "7daysAgo", "endDate": "yesterday"}],
                             "metrics": [{"name": "sessions"}]})
    except httpx.HTTPError as e:
        return "err", f"Ulaşılamadı: {type(e).__name__}"
    if r.status_code == 403:
        return "err", (f"Erişim yok: servis hesabı ({connections.service_account_email()}) GA4 mülkünde "
                       "«Görüntüleyici» olarak ekli değil.")
    if r.status_code >= 400:
        return "err", f"GA4 {r.status_code}: {_err_text(r)}"
    rows = r.json().get("rows") or []
    sessions = int(rows[0]["metricValues"][0]["value"]) if rows else 0
    return "ok", f"Mülk {prop} okundu: son 7 günde {sessions:,} oturum.".replace(",", ".")


def _google_key() -> tuple[str, str]:
    key = _conf("GOOGLE_API_KEY")
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.post("https://chromeuxreport.googleapis.com/v1/records:queryRecord", params={"key": key},
                       json={"origin": _site()})
    except httpx.HTTPError as e:
        return "err", _clean(f"Ulaşılamadı: {type(e).__name__}", key)
    if r.status_code == 404:
        return "ok", "Anahtar geçerli (Chrome kullanıcı verisi); sitenin kökeni için henüz yeterli ziyaretçi verisi yok."
    if r.status_code >= 400:
        return "err", f"{r.status_code}: {_err_text(r)}"
    return "ok", "Anahtar geçerli: Chrome kullanıcı hız verisi okundu (sayfa hızı ölçümü aynı anahtarla çalışır)."


def _youtube() -> tuple[str, str]:
    key = _conf("YOUTUBE_API_KEY")
    r, err = _get("https://www.googleapis.com/youtube/v3/videos",
                  params={"part": "id", "chart": "mostPopular", "regionCode": "TR", "maxResults": "1", "key": key},
                  secret=key)
    if r is None:
        return "err", err
    if r.status_code >= 400:
        return "err", f"{r.status_code}: {_err_text(r)}"
    return "ok", "Anahtar geçerli: YouTube video bilgisi okundu (1 birim kota)."


def _bing() -> tuple[str, str]:
    key = _conf("BING_WEBMASTER_API_KEY")
    r, err = _get("https://ssl.bing.com/webmaster/api.svc/json/GetUserSites", params={"apikey": key}, secret=key)
    if r is None:
        return "err", err
    if r.status_code >= 400:
        return "err", f"{r.status_code}: {_err_text(r)}"
    sites = [str(s.get("Url") or "") for s in (r.json().get("d") or [])]
    host = _site().split("://", 1)[-1].removeprefix("www.")
    mine = [s for s in sites if host in s]
    if not mine:
        return "err", f"Anahtar geçerli ama {host} bu Bing hesabında yok ({len(sites)} site kayıtlı)."
    return "ok", f"Anahtar geçerli: {mine[0]} Bing hesabında kayıtlı."


def _indexnow() -> tuple[str, str]:
    key = _conf("INDEXNOW_KEY")
    url = f"{_site()}/{key}.txt"
    r, err = _get(url, secret=key)
    if r is None:
        return "err", err
    if r.status_code != 200 or r.text.strip() != key:
        return "err", (f"Anahtar dosyası sitede yok ya da içeriği farklı (HTTP {r.status_code}). Sitenin köküne "
                       "anahtar adıyla .txt dosyası konmalı, içinde yalnız anahtar yazmalı.")
    return "ok", "Anahtar dosyası sitede yayında ve içeriği doğru."


def _serpapi() -> tuple[str, str]:
    key = _conf("SERPAPI_KEY")
    r, err = _get("https://serpapi.com/account.json", params={"api_key": key}, secret=key)
    if r is None:
        return "err", err
    if r.status_code >= 400:
        return "err", f"{r.status_code}: {_err_text(r)}"
    d = r.json()
    left = d.get("total_searches_left", d.get("plan_searches_left"))
    return "ok", f"Anahtar geçerli: bu ay kalan arama {left if left is not None else 'bildirilmedi'} (sınama arama harcamaz)."


def _cloudflare() -> tuple[str, str]:
    token = _conf("CLOUDFLARE_API_TOKEN")
    zone = _conf("CLOUDFLARE_ZONE_ID")
    head = {"Authorization": f"Bearer {token}"}
    r, err = _get("https://api.cloudflare.com/client/v4/user/tokens/verify", headers=head, secret=token)
    if r is None:
        return "err", err
    if r.status_code >= 400 or not r.json().get("success"):
        return "err", f"Anahtar geçersiz ({r.status_code}): {_err_text(r)}"
    if not zone:
        return "err", "Anahtar geçerli ama alan (Zone ID) girilmemiş."
    r, err = _get(f"https://api.cloudflare.com/client/v4/zones/{zone}", headers=head, secret=token)
    if r is None:
        return "err", err
    if r.status_code >= 400:
        return "err", f"Anahtar geçerli ama alan okunamadı ({r.status_code}): {_err_text(r)}"
    return "ok", f"Anahtar geçerli: {r.json().get('result', {}).get('name', zone)} alanı okundu."


def seo_parts() -> list[Part]:
    out: list[Part] = []
    out.append(_run("T-soft", _tsoft) if _conf("TSOFT_USER") and _conf("TSOFT_PASSWORD")
               else _off("T-soft", "Kullanıcı ya da şifre"))
    if _conf("GOOGLE_SERVICE_ACCOUNT_JSON"):
        out.append(_run("Search Console", _gsc))
        out.append(_run("Google Analytics 4", _ga4) if _conf("GA4_PROPERTY_ID") else _off("Google Analytics 4", "Mülk kimliği"))
    else:
        out.append(_off("Search Console", "Google servis hesabı (JSON)"))
    for label, key, fn in (("Google API anahtarı", "GOOGLE_API_KEY", _google_key),
                           ("YouTube", "YOUTUBE_API_KEY", _youtube),
                           ("Bing Webmaster", "BING_WEBMASTER_API_KEY", _bing),
                           ("IndexNow", "INDEXNOW_KEY", _indexnow),
                           ("Google arama sonucu (SerpAPI)", "SERPAPI_KEY", _serpapi),
                           ("Cloudflare", "CLOUDFLARE_API_TOKEN", _cloudflare)):
        out.append(_run(label, fn, _conf(key)) if _conf(key) else _off(label, "Anahtar"))
    return out


# ------------------------------------------------------------------------------------------------ GEO

def _models(url: str, *, params: Optional[dict[str, str]] = None, headers: Optional[dict[str, str]] = None,
            secret: str, model: str) -> tuple[str, str]:
    r, err = _get(url, params=params, headers=headers, secret=secret)
    if r is None:
        return "err", err
    if r.status_code >= 400:
        return "err", f"{r.status_code}: {_err_text(r)}"
    body = r.json()
    names = [str(m.get("name") or m.get("id") or "").removeprefix("models/")
             for m in (body.get("models") or body.get("data") or [])]
    if model and names and not any(n == model or n.startswith(model + "-") for n in names):
        return "err", f"Anahtar geçerli ama «{model}» modeli bu hesapta yok."
    return "ok", f"Anahtar geçerli{f', model «{model}» açık' if model else ''} (sınama soru sormaz, kota harcamaz)."


def geo_parts() -> list[Part]:
    from semantic_bridge.seo_geo import geo

    def model(engine: str) -> str:
        return _conf(geo.ENGINES[engine]["model"]) or geo.DEFAULT_MODEL.get(engine, "")

    out: list[Part] = []
    k = _conf("GEMINI_API_KEY")
    out.append(_run("Gemini", lambda: _models("https://generativelanguage.googleapis.com/v1beta/models",
                                               params={"key": k, "pageSize": "1000"}, secret=k,
                                               model=model("gemini")), k)
               if k else _off("Gemini", "Anahtar"))
    k2 = _conf("GEO_OPENAI_API_KEY")
    out.append(_run("ChatGPT", lambda: _models("https://api.openai.com/v1/models",
                                                headers={"Authorization": f"Bearer {k2}"}, secret=k2,
                                                model=model("openai")), k2)
               if k2 else _off("ChatGPT", "Anahtar"))
    k3 = _conf("GEO_ANTHROPIC_API_KEY")
    out.append(_run("Claude", lambda: _models("https://api.anthropic.com/v1/models",
                                               params={"limit": "1000"},
                                               headers={"x-api-key": k3, "anthropic-version": "2023-06-01"},
                                               secret=k3, model=model("claude")), k3)
               if k3 else _off("Claude", "Anahtar"))
    if _conf("PERPLEXITY_API_KEY"):
        out.append({"label": "Perplexity", "state": "ok", "ms": 0,
                    "message": "Anahtar girilmiş. Perplexity'de ücretsiz doğrulama yok; ilk ölçümde denenir."})
    else:
        out.append(_off("Perplexity", "Anahtar"))
    return out


def summarize(parts: list[Part]) -> tuple[bool, str]:
    on = [p for p in parts if p["state"] != "off"]
    bad = [p for p in on if p["state"] == "err"]
    if not on:
        return False, "Hiçbir bağlantı girilmemiş."
    if bad:
        return False, f"{len(on) - len(bad)} / {len(on)} bağlantı başarılı; hata: " + ", ".join(p["label"] for p in bad) + "."
    off = len(parts) - len(on)
    return True, f"{len(on)} bağlantının hepsi başarılı." + (f" {off} tanesi girilmemiş." if off else "")
