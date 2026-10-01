"""Yandex Webmaster (yalnız okuma).

Neden Yandex: Yandex'in yapay zekâ asistanı kendi arama dizinini kullanır; Rusça ve Türkçe konuşan okura ulaşan ikinci
büyük dizin budur. Bu dosya Yandex'ten sorgu, günlük gösterim/tıklama, dizin sayısı, tarama yanıt kodları, site
teşhisi ve dış bağlantı örneklerini okur; aynı sorguları Search Console ile yan yana koyar.

Yandex Webmaster API v4: `https://api.webmaster.yandex.net/v4/…`, başlık `Authorization: OAuth <jeton>`. Jeton
oauth.yandex.com'da açılan uygulamadan (izin `webmaster:hostinfo`) alınır ve Yönetim → SEO & GEO → «Yandex Webmaster
jetonu» alanına girilir. Sitenin sahibi olmak gerekmez; sahibin verdiği yetki yeter. Kullanılan uçlar:
`/user` (kullanıcı kimliği), `/user/{u}/hosts` (site kimliği, örn. `https:timas.com.tr:443`), `…/summary`,
`…/search-queries/popular` (sayfa başına en çok 500), `…/search-queries/all/history`, `…/indexing/history`,
`…/diagnostics`, `…/links/external/samples` (sayfa başına en çok 100). Sayfalama `count`a göre sonuna kadar yürür.
IndexNow bildirimi bing.py'dedir ve Yandex'e de gider; burada ayrıca gönderim yoktur.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta
from typing import Any, Optional
from urllib.parse import quote, urlparse

import httpx
import sqlalchemy as sa
from fastapi import HTTPException, Request

from .bing import norm_query, site_root
from .store import _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

API = "https://api.webmaster.yandex.net/v4"
#: Karşılaştırma dönemi (Search Console ile aynı: 28 gün).
PERIOD_DAYS = 28
#: Yandex sırası Google'dan bu kadar ya da daha çok gerideyse "çok geride" sayılır.
GAP = 5.0
DEFAULT_SITE = "https://timas.com.tr"
#: Yandex API sayfa boyları (belgedeki üst sınır).
QUERY_PAGE = 500
LINK_PAGE = 100
#: Ardışık istekler arası bekleme (Yandex saniyede çok isteği reddeder).
PAUSE_SECONDS = 0.3

YANDEX = sa.Table(
    "semantic_seo_yandex", _md,  # Yandex Webmaster okumaları: tür başına son hâl
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kind", sa.String(24), primary_key=True),       # summary | queries | daily | indexing | problems | links
    sa.Column("rows_json", sa.Text, nullable=False),
    sa.Column("error", sa.String(1000)),                      # son okumada bu tür okunamadıysa; eski satırlar korunur
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
_ready: set[int] = set()
_ready_lock = threading.Lock()


def _ensure(eng: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(eng) in _ready:
            return
        YANDEX.create(eng, checkfirst=True)
        _ready.add(id(eng))


class YandexError(RuntimeError):
    """Ekrana olduğu gibi gidecek Türkçe hata."""


# ------------------------------------------------------------------------------------------------ ayrıştırma

#: Teşhis kodları → Türkçe ad. Listede olmayan kod olduğu gibi gösterilir.
PROBLEMS = {
    "DISALLOWED_IN_ROBOTS": "Site robots.txt ile kapatılmış",
    "DNS_ERROR": "DNS hatası: sunucuya bağlanılamıyor",
    "MAIN_PAGE_ERROR": "Ana sayfa hata veriyor",
    "THREATS": "Güvenlik tehdidi bulundu",
    "SLOW_AVG_RESPONSE_TIME": "Sunucu yavaş yanıt veriyor",
    "SSL_CERTIFICATE_ERROR": "SSL sertifikası hatalı",
    "BAD_ADVERTISEMENT": "Kurala aykırı reklam biçimi",
    "DOCUMENTS_MISSING_DESCRIPTION": "Sayfalarda açıklama (meta description) eksik",
    "DOCUMENTS_MISSING_TITLE": "Sayfalarda başlık (title) eksik",
    "ERROR_IN_ROBOTS_TXT": "robots.txt dosyasında hata",
    "ERRORS_IN_SITEMAPS": "Site haritasında hata",
    "MAIN_MIRROR_IS_NOT_HTTPS": "Ana adres HTTPS değil",
    "MAIN_PAGE_REDIRECTS": "Ana sayfa başka adrese yönleniyor",
    "NO_METRIKA_COUNTER_CRAWL_ENABLED": "Yandex ziyaretçi sayacı üzerinden tarama kapalı",
    "NO_ROBOTS_TXT": "robots.txt yok",
    "NO_SITEMAPS": "Site haritası yok",
    "NO_SITEMAP_MODIFICATIONS": "Site haritası uzun süredir değişmemiş",
    "NON_WORKING_VIDEO": "Video dizine alınamadı",
    "SOFT_404": "Olmayan sayfa 404 yerine 200 dönüyor",
    "TOO_MANY_DOMAINS_ON_SEARCH": "Alt alan adları aramada çoğalıyor",
    "TOO_MANY_PAGE_DUPLICATES": "Çok sayıda kopya sayfa",
    "FAVICON_PROBLEM": "Site simgesi (favicon) bulunamadı",
    "INCOMPLETE_SPRAV_COMPANY_PROFILE": "Yandex işletme kaydı eksik",
    "NO_CHATS": "Aramada sohbet bağlantısı yok",
    "NO_METRIKA_COUNTER": "Yandex ziyaretçi sayacı hatalı ya da yok",
    "NO_REGIONS": "Sitenin bölgesi tanımlanmamış",
    "NOT_IN_SPRAV": "Yandex işletme rehberinde kayıt yok",
    "NOT_MOBILE_FRIENDLY": "Mobil uyumlu değil",
}
SEVERITY = {"FATAL": "Ölümcül", "CRITICAL": "Kritik", "POSSIBLE_PROBLEM": "Olası sorun", "RECOMMENDATION": "Öneri"}
_SEV_ORDER = {k: i for i, k in enumerate(SEVERITY)}


def _n(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _day(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    return s[:10] if len(s) >= 10 and s[4] == "-" else None


def query_rows(raw: Any) -> list[dict[str, Any]]:
    """`search-queries/popular` → {key, clicks, impressions, ctr, position}. Konum bilinmiyorsa (≤0) None."""
    out = []
    for r in (raw or {}).get("queries") or []:
        if not isinstance(r, dict):
            continue
        ind = r.get("indicators") or {}
        shows, clicks = int(_n(ind.get("TOTAL_SHOWS"))), int(_n(ind.get("TOTAL_CLICKS")))
        p = _n(ind.get("AVG_SHOW_POSITION"))
        key = str(r.get("query_text") or "").strip()
        if key:
            out.append({"key": key, "clicks": clicks, "impressions": shows, "ctr": (clicks / shows) if shows else 0.0,
                        "position": round(p, 1) if p > 0 else None})
    out.sort(key=lambda r: (-r["clicks"], -r["impressions"], r["key"]))
    return out


def series(raw: Any, names: dict[str, str]) -> list[dict[str, Any]]:
    """`{"indicators": {AD: [{date, value}]}}` → gün başına {date, <ad>: değer}. Eksik gün 0 sayılır."""
    by_day: dict[str, dict[str, Any]] = {}
    ind = (raw or {}).get("indicators") or {}
    for src, dst in names.items():
        for p in ind.get(src) or []:
            d = _day(p.get("date")) if isinstance(p, dict) else None
            if d:
                by_day.setdefault(d, {"date": d, **{v: 0 for v in names.values()}})[dst] = int(_n(p.get("value")))
    return [by_day[d] for d in sorted(by_day)]


def problem_rows(raw: Any) -> list[dict[str, Any]]:
    """Teşhis: yalnız şu an var olan (`PRESENT`) sorunlar, önem sırasıyla."""
    out = []
    for code, p in ((raw or {}).get("problems") or {}).items():
        if not isinstance(p, dict) or p.get("state") != "PRESENT":
            continue
        sev = str(p.get("severity") or "")
        out.append({"code": code, "label": PROBLEMS.get(code, code), "severity": sev,
                     "severityLabel": SEVERITY.get(sev, sev), "since": _day(p.get("last_state_update"))})
    out.sort(key=lambda r: (_SEV_ORDER.get(r["severity"], 9), r["label"]))
    return out


def link_rows(pages: list[Any]) -> list[dict[str, Any]]:
    out = []
    for raw in pages:
        for r in (raw or {}).get("links") or []:
            if isinstance(r, dict) and r.get("source_url"):
                out.append({"source": str(r["source_url"]), "target": str(r.get("destination_url") or ""),
                            "found": _day(r.get("discovery_date")), "seen": _day(r.get("source_last_access_date"))})
    out.sort(key=lambda r: (r["found"] or "", r["source"]), reverse=True)
    return out


def summary_row(raw: Any) -> dict[str, Any]:
    raw = raw or {}
    probs = raw.get("site_problems") or {}
    return {"sqi": int(_n(raw.get("sqi"))), "searchable": int(_n(raw.get("searchable_pages_count"))),
            "excluded": int(_n(raw.get("excluded_pages_count"))),
            "problems": {k: int(_n(probs.get(k))) for k in SEVERITY}}


def compare(google: list[dict[str, Any]], yandex: list[dict[str, Any]], gap: float = GAP) -> dict[str, Any]:
    """İki motorda da görünen sorgular yan yana; Yandex sırası `gap` kadar gerideyse `worse`."""
    y = {norm_query(r["key"]): r for r in yandex}
    both, only_google = [], 0
    for g in google:
        q = (g.get("keys") or [""])[0]
        k = norm_query(q)
        if not k:
            continue
        r = y.get(k)
        if not r:
            only_google += 1
            continue
        gp = round(float(g.get("position") or 0), 1) or None
        yp = r["position"]
        diff = round(yp - gp, 1) if (gp and yp) else None
        both.append({"query": q, "google": {"clicks": int(g.get("clicks") or 0), "impressions": int(g.get("impressions") or 0),
                                            "position": gp},
                     "yandex": {"clicks": r["clicks"], "impressions": r["impressions"], "position": yp},
                     "gap": diff, "worse": diff is not None and diff >= gap})
    both.sort(key=lambda r: (-r["google"]["impressions"], r["query"]))
    return {"items": both, "onlyGoogle": only_google, "worse": sum(1 for r in both if r["worse"])}


def totals(daily: list[dict[str, Any]], days: int = PERIOD_DAYS) -> dict[str, Any]:
    """Son `days` gün ve ondan önceki aynı uzunlukta dönem."""
    if not daily:
        return {"start": None, "end": None, "clicks": 0, "impressions": 0, "ctr": 0.0, "prevClicks": None, "prevImpressions": None}
    end = date.fromisoformat(daily[-1]["date"])
    start = end - timedelta(days=days - 1)
    prev_start = start - timedelta(days=days)
    cur = [r for r in daily if r["date"] >= start.isoformat()]
    prev = [r for r in daily if prev_start.isoformat() <= r["date"] < start.isoformat()]
    c, i = sum(r["clicks"] for r in cur), sum(r["impressions"] for r in cur)
    return {"start": start.isoformat(), "end": end.isoformat(), "clicks": c, "impressions": i,
            "ctr": (c / i) if i else 0.0,
            "prevClicks": sum(r["clicks"] for r in prev) if prev else None,
            "prevImpressions": sum(r["impressions"] for r in prev) if prev else None}


def pick_host(hosts: list[dict[str, Any]], site: str) -> Optional[dict[str, Any]]:
    """Hesaptaki siteler arasından ayardaki siteyi bulur; www'li/www'siz ve http/https farkı yok sayılır, doğrulanmış
    ve https olan önce gelir."""
    want = (urlparse(site).hostname or "").lower().removeprefix("www.")
    cands = [h for h in hosts if (urlparse(str(h.get("ascii_host_url") or "")).hostname or "").lower().removeprefix("www.") == want]
    cands.sort(key=lambda h: (not h.get("verified"), not str(h.get("ascii_host_url") or "").startswith("https")))
    return cands[0] if cands else None


# ------------------------------------------------------------------------------------------------ ağ

def _mask(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def yandex_call(path: str, token: str, params: Optional[list[tuple[str, Any]]] = None, *, timeout: float = 60) -> Any:
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as c:
            resp = c.get(f"{API}{path}", params=params or [],
                         headers={"Authorization": f"OAuth {token}", "Accept": "application/json"})
    except httpx.HTTPError as e:
        raise YandexError(_mask(f"Yandex'e ulaşılamadı: {e}", token)) from None
    if resp.status_code >= 400:
        code, msg = "", ""
        try:
            body = resp.json()
            code, msg = str(body.get("error_code") or ""), str(body.get("error_message") or "")
        except ValueError:
            msg = resp.text[:200]
        if resp.status_code == 401 or code in ("INVALID_OAUTH_TOKEN", "EXPIRED_TOKEN"):
            raise YandexError("Yandex jetonu geçersiz ya da süresi dolmuş (oauth.yandex.com'dan yeniden alınmalı).")
        if code == "HOST_NOT_VERIFIED":
            raise YandexError("Site bu Yandex hesabında doğrulanmamış ya da hesaba yetki verilmemiş.")
        if code in ("HOST_NOT_INDEXED", "HOST_NOT_LOADED"):
            raise YandexError("Yandex bu site için henüz veri hazırlamadı; site yeni eklendiyse birkaç gün sürer.")
        if resp.status_code == 403:
            raise YandexError("Yandex jetonunun bu bilgiyi okuma izni yok (uygulamada «webmaster:hostinfo» izni olmalı).")
        if resp.status_code == 429:
            raise YandexError("Yandex istek sınırına takıldı; daha sonra yeniden okunur.")
        raise YandexError(_mask(f"Yandex {path.rsplit('/', 1)[-1]} {resp.status_code}: {code or msg or 'beklenmeyen cevap'}", token))
    try:
        return resp.json()
    except ValueError:
        raise YandexError("Yandex cevabı okunamadı.") from None


def resolve_host(token: str, site: str) -> tuple[str, str, str]:
    """Jetonun kullanıcı kimliği ve ayardaki sitenin Yandex kimliği → (user_id, host_id, host_url)."""
    uid = str((yandex_call("/user", token) or {}).get("user_id") or "")
    if not uid:
        raise YandexError("Yandex kullanıcı kimliği okunamadı.")
    hosts = (yandex_call(f"/user/{uid}/hosts", token) or {}).get("hosts") or []
    h = pick_host(hosts, site)
    if not h:
        raise YandexError(f"{urlparse(site).hostname} bu Yandex hesabında yok ({len(hosts)} site kayıtlı); Yandex "
                          "Webmaster'da sahibi hesaba yetki vermeli.")
    if not h.get("verified"):
        raise YandexError(f"{h.get('ascii_host_url')} Yandex'te kayıtlı ama doğrulanmamış.")
    return uid, str(h["host_id"]), str(h.get("ascii_host_url") or site)


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


# ------------------------------------------------------------------------------------------------ uçlar

def register(app, ctx) -> None:
    seo = ctx.seo
    lock = threading.Lock()
    state: dict[str, Any] = {"running": False, "startedAt": None, "error": None, "host": None}

    def eng() -> sa.engine.Engine:
        e = seo.engine()
        _ensure(e)
        return e

    def site() -> str:
        return site_root(seo.conf("SEO_SITE_URL") or DEFAULT_SITE)

    def token() -> str:
        return (seo.conf("YANDEX_WEBMASTER_TOKEN") or "").strip()

    def load() -> dict[str, dict[str, Any]]:
        with eng().connect() as c:
            rows = c.execute(sa.select(YANDEX).where(YANDEX.c.tenant_id == seo.tenant())).mappings().all()
        return {r["kind"]: {"rows": loads(r["rows_json"], []), "error": r["error"], "savedAt": iso(r["saved_at"])} for r in rows}

    def read_all(tok: str, base: str) -> dict[str, Any]:
        """Her tür ayrı okunur; biri düşerse ötekiler kaydedilir."""
        today = date.today()
        q_from = (today - timedelta(days=PERIOD_DAYS)).isoformat()
        h_from = (today - timedelta(days=PERIOD_DAYS * 2)).isoformat()
        to = today.isoformat()

        def queries() -> list[dict[str, Any]]:
            params = [("order_by", "TOTAL_SHOWS"), ("date_from", q_from), ("date_to", to)] + [
                ("query_indicator", i) for i in ("TOTAL_SHOWS", "TOTAL_CLICKS", "AVG_SHOW_POSITION", "AVG_CLICK_POSITION")]
            rows, offset = [], 0
            while True:
                page = yandex_call(f"{base}/search-queries/popular", tok, params + [("offset", offset), ("limit", QUERY_PAGE)])
                got = (page or {}).get("queries") or []
                rows.extend(query_rows(page))
                offset += len(got)
                if not got or offset >= int(_n((page or {}).get("count"))):
                    break
                time.sleep(PAUSE_SECONDS)
            rows.sort(key=lambda r: (-r["clicks"], -r["impressions"], r["key"]))
            return rows

        def links() -> list[dict[str, Any]]:
            pages, offset = [], 0
            while True:
                page = yandex_call(f"{base}/links/external/samples", tok, [("offset", offset), ("limit", LINK_PAGE)])
                got = (page or {}).get("links") or []
                pages.append(page)
                offset += len(got)
                if not got or offset >= int(_n((page or {}).get("count"))):
                    break
                time.sleep(PAUSE_SECONDS)
            return link_rows(pages)

        plan = {
            "summary": lambda: summary_row(yandex_call(f"{base}/summary", tok)),
            "queries": queries,
            "daily": lambda: series(yandex_call(f"{base}/search-queries/all/history", tok, [
                ("query_indicator", "TOTAL_SHOWS"), ("query_indicator", "TOTAL_CLICKS"),
                ("date_from", h_from), ("date_to", to)]), {"TOTAL_SHOWS": "impressions", "TOTAL_CLICKS": "clicks"}),
            "indexing": lambda: series(yandex_call(f"{base}/indexing/history", tok, [("date_from", h_from), ("date_to", to)]),
                                       {"HTTP_2XX": "code2xx", "HTTP_3XX": "code3xx", "HTTP_4XX": "code4xx",
                                        "HTTP_5XX": "code5xx", "OTHER": "other"}),
            "problems": lambda: problem_rows(yandex_call(f"{base}/diagnostics", tok)),
            "links": links,
        }
        results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for kind, fn in plan.items():
            try:
                results[kind] = fn()
            except YandexError as e:
                errors[kind] = str(e)[:1000]
            time.sleep(PAUSE_SECONDS)
        return {"results": results, "errors": errors, "kinds": list(plan)}

    def refresh() -> dict[str, Any]:
        tok = token()
        if not tok:
            raise YandexError("Yandex Webmaster jetonu girilmemiş (Yönetim → SEO & GEO).")
        if not lock.acquire(blocking=False):
            raise YandexError("Yandex okuması zaten sürüyor.")
        state.update(running=True, startedAt=iso(now()), error=None)
        try:
            uid, host_id, host_url = resolve_host(tok, site())
            state["host"] = host_url
            out = read_all(tok, f"/user/{uid}/hosts/{quote(host_id, safe=':')}")
            results, errors = out["results"], out["errors"]
            if not results and errors:
                raise YandexError(next(iter(errors.values())))
            tenant, at = seo.tenant(), now()
            with eng().begin() as c:
                for kind in out["kinds"]:
                    if kind in results:
                        c.execute(YANDEX.delete().where(YANDEX.c.tenant_id == tenant, YANDEX.c.kind == kind))
                        c.execute(YANDEX.insert().values(tenant_id=tenant, kind=kind, rows_json=dumps(results[kind]),
                                                         error=None, saved_at=at))
                    else:
                        c.execute(YANDEX.update().where(YANDEX.c.tenant_id == tenant, YANDEX.c.kind == kind)
                                  .values(error=errors.get(kind)))
            counts = {k: (len(v) if isinstance(v, list) else 1) for k, v in results.items()}
            return {"counts": counts, "errors": errors, "host": host_url}
        except YandexError as e:
            state.update(error=str(e))
            raise
        finally:
            state.update(running=False)
            lock.release()

    def google_queries() -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
        g = seo.gsc("queries")
        if not g:
            return [], None
        return g.get("rows") or [], {"start": g.get("start"), "end": g.get("end"), "savedAt": g.get("savedAt")}

    @app.get("/api/v1/seo-geo/yandex")
    def yandex_summary(request: Request) -> dict[str, Any]:
        ctx.gate(request)
        data = load()
        daily = data.get("daily", {}).get("rows", [])
        indexing = data.get("indexing", {}).get("rows", [])
        queries = data.get("queries", {}).get("rows", [])
        cmp = compare(google_queries()[0], queries)
        g_meta = google_queries()[1]
        saved = [v["savedAt"] for v in data.values() if v.get("savedAt")]
        summ = data.get("summary", {}).get("rows") or None
        probs = data.get("problems", {}).get("rows", [])
        return {
            "configured": bool(token()), "site": site() + "/", "running": state["running"], "error": state["error"],
            "lastRefresh": max(saved) if saved else None,
            "errors": {k: v["error"] for k, v in data.items() if v.get("error")},
            "summary": summ if isinstance(summ, dict) else None,
            "totals": totals(daily),
            "daily": daily,
            "indexing": indexing,
            "indexingLatest": indexing[-1] if indexing else None,
            "problems": probs,
            "counts": {"queries": len(queries), "links": len(data.get("links", {}).get("rows", [])), "problems": len(probs),
                       "compared": len(cmp["items"]), "worse": cmp["worse"], "onlyGoogle": cmp["onlyGoogle"]},
            "google": g_meta, "gap": GAP, "period": PERIOD_DAYS,
        }

    @app.get("/api/v1/seo-geo/yandex/list/{kind}")
    def yandex_list(kind: str, request: Request, start: int = 0, limit: int = 50, q: str = "",
                    filter: str = "") -> dict[str, Any]:
        """Sayfalı listeler: queries | compare | links. `filter=worse` karşılaştırmada Yandex'in çok geride
        olduklarını süzer."""
        ctx.gate(request)
        data = load()
        if kind == "queries":
            items: list[dict[str, Any]] = data.get("queries", {}).get("rows", [])
            key = "key"
        elif kind == "compare":
            items = compare(google_queries()[0], data.get("queries", {}).get("rows", []))["items"]
            if filter == "worse":
                items = [r for r in items if r["worse"]]
            key = "query"
        elif kind == "links":
            items = data.get("links", {}).get("rows", [])
            key = "source"
        else:
            raise _err(404, "Bilinmeyen liste.")
        if q.strip():
            needle = norm_query(q)
            items = [r for r in items if needle in norm_query(r[key]) or (kind == "links" and needle in norm_query(r["target"]))]
        start, limit = max(0, start), max(1, limit)
        return {"total": len(items), "start": start, "items": items[start:start + limit]}

    @app.post("/api/v1/seo-geo/yandex/refresh")
    def yandex_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        try:
            out = refresh()
        except YandexError as e:
            raise _err(409 if "girilmemiş" in str(e) or "sürüyor" in str(e) else 502, str(e)) from None
        seo.audit(user, "run", "yandex", "Yandex Webmaster okuması", out)
        return out

    def nightly_yandex() -> None:
        if not token():
            return
        try:
            refresh()
        except YandexError as e:
            log.warning("yandex nightly: %s", e)

    seo.nightly.append(("yandex", nightly_yandex))
