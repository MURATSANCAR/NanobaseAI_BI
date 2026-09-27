"""Bing Webmaster Tools (yalnız okuma) ve IndexNow bildirimi.

Neden Bing: ChatGPT'nin web araması büyük ölçüde Bing dizinine dayanır. Google'da iyi olup Bing'de geride kalan
sorgu, yapay zekâ cevaplarında da geride kalır. Bu dosya Bing'den sorgu/sayfa/günlük trafik, tarama istatistiği ve
tarama sorunlarını okur, Search Console ile aynı sorguları yan yana koyar.

Bing Webmaster API (JSON): `https://ssl.bing.com/webmaster/api.svc/json/<Yöntem>?siteUrl=…&apikey=…`. Cevap
`{"d": …}` sarmalında gelir, tarihler `/Date(1316156400000-0700)/` biçimindedir (milisaniye UTC; ek saat dilimi
yalnız gösterim içindir, yok sayılır). Kullanılan yöntemler: GetQueryStats, GetPageStats (haftalık kovalar, yaklaşık
son 6 ay), GetRankAndTrafficStats (günlük), GetCrawlStats (günlük), GetCrawlIssues, GetUrlSubmissionQuota. Anahtar
adreste taşındığı için httpx günlüğünde ve hata metninde maskelenir.

IndexNow: `INDEXNOW_KEY` ile. Anahtar dosyası (`<site>/<anahtar>.txt`, içinde yalnız anahtar) sitede doğrulanmadan
hiçbir bildirim gönderilmez; dosyayı site yöneticisi koyar, biz T-soft'a yazmayız. Değişiklik izleme: etkin her
kitabın SEO'yu ilgilendiren alanlarından (ad, SEO başlığı/açıklaması, açıklama, fiyat, stok) parmak izi alınır.
**İlk tur yalnız taban kaydeder, bildirim göndermez** (6.500 kitabı körlemesine göndermemek için); sonraki gece
turlarında yeni/değişen/satıştan kalkan kitaplar kuyruğa girer ve anahtar dosyası doğruysa gönderilir. Bütün
kitapları bir kez göndermek onay yetkisiyle elle yapılır. Bir istekte en çok 10.000 adres gider (protokol sınırı);
fazlası sıradaki isteklere bölünür.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from urllib.parse import quote, urlparse

import httpx
import sqlalchemy as sa
from fastapi import HTTPException, Request

from .store import PRODUCTS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

API = "https://ssl.bing.com/webmaster/api.svc/json"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
#: IndexNow protokolü: bir istekte en çok 10.000 adres. Tavan değil, bölme ölçüsü.
INDEXNOW_BATCH = 10_000
#: Karşılaştırma dönemi (Search Console ile aynı: 28 gün).
PERIOD_DAYS = 28
#: Bing sırası Google'dan bu kadar ya da daha çok gerideyse "çok geride" sayılır.
GAP = 5.0
DEFAULT_SITE = "https://timas.com.tr"

BING = sa.Table(
    "semantic_seo_bing", _md,  # Bing Webmaster okumaları: tür başına son hâl
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kind", sa.String(24), primary_key=True),       # queries | pages | daily | crawl | issues | quota
    sa.Column("rows_json", sa.Text, nullable=False),
    sa.Column("error", sa.String(1000)),                      # son okumada bu tür okunamadıysa; eski satırlar korunur
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
INDEXNOW_STATE = sa.Table(
    "semantic_seo_indexnow_state", _md,  # kitap başına son bildirilen/görülen parmak izi
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("product_id", sa.String(40), primary_key=True),
    sa.Column("fingerprint", sa.String(40), nullable=False),  # "gone": artık etkin değil
    sa.Column("url", sa.String(800)),
    sa.Column("pending", sa.Boolean, nullable=False, default=False),
    sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("notified_at", sa.DateTime(timezone=True)),
)
INDEXNOW_LOG = sa.Table(
    "semantic_seo_indexnow_log", _md,  # her bildirim isteği
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("kind", sa.String(12), nullable=False),         # gece | kuyruk | tumu
    sa.Column("count", sa.Integer, nullable=False),
    sa.Column("status_code", sa.Integer),
    sa.Column("error", sa.String(1000)),
    sa.Column("started_by", sa.String(120)),
)
_TABLES = (BING, INDEXNOW_STATE, INDEXNOW_LOG)
_ready: set[int] = set()
_ready_lock = threading.Lock()


def _ensure(eng: sa.engine.Engine) -> None:
    """store.ensure bu dosya yüklenmeden koşmuş olabilir; tablolar burada da kurulur."""
    with _ready_lock:
        if id(eng) in _ready:
            return
        for t in _TABLES:
            t.create(eng, checkfirst=True)
        _ready.add(id(eng))


class BingError(RuntimeError):
    """Ekrana olduğu gibi gidecek Türkçe hata."""


# ------------------------------------------------------------------------------------------------ ayrıştırma

_DATE = re.compile(r"Date\((-?\d+)([+-]\d{4})?\)")


def parse_date(v: Any) -> Optional[str]:
    """`/Date(ms±hhmm)/` → `YYYY-AA-GG` (UTC). ISO metin de kabul edilir; okunamazsa None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000, tz=timezone.utc).date().isoformat()
    s = str(v).strip()
    m = _DATE.search(s)
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date().isoformat()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return None


def unwrap(body: Any) -> Any:
    """`{"d": …}` sarmalını açar; `__type` gibi WCF alanlarını atar."""
    if isinstance(body, dict) and set(body) - {"__type"} == {"d"}:
        body = body["d"]
    if isinstance(body, list):
        return [{k: v for k, v in r.items() if k != "__type"} if isinstance(r, dict) else r for r in body]
    if isinstance(body, dict):
        return {k: v for k, v in body.items() if k != "__type"}
    return body


def _n(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def stat_rows(raw: Any) -> list[dict[str, Any]]:
    """GetQueryStats / GetPageStats satırı → {key, date, clicks, impressions, position}. Konum bilinmiyorsa (≤0) None."""
    out = []
    for r in unwrap(raw) or []:
        if not isinstance(r, dict):
            continue
        pos = _n(r.get("AvgImpressionPosition"))
        out.append({"key": str(r.get("Query") or r.get("Page") or "").strip(), "date": parse_date(r.get("Date")),
                    "clicks": int(_n(r.get("Clicks"))), "impressions": int(_n(r.get("Impressions"))),
                    "position": pos if pos > 0 else None})
    return [r for r in out if r["key"]]


def daily_rows(raw: Any) -> list[dict[str, Any]]:
    out = [{"date": parse_date(r.get("Date")), "clicks": int(_n(r.get("Clicks"))),
            "impressions": int(_n(r.get("Impressions")))} for r in unwrap(raw) or [] if isinstance(r, dict)]
    return sorted((r for r in out if r["date"]), key=lambda r: r["date"])


CRAWL_FIELDS = {"CrawledPages": "crawled", "InIndex": "inIndex", "CrawlErrors": "errors", "Code2xx": "code2xx",
                "Code301": "code301", "Code302": "code302", "Code4xx": "code4xx", "Code5xx": "code5xx",
                "BlockedByRobotsTxt": "blockedByRobots", "DnsFailures": "dnsFailures",
                "ConnectionTimeout": "timeouts", "AllOtherCodes": "otherCodes", "InLinks": "inLinks"}


def crawl_rows(raw: Any) -> list[dict[str, Any]]:
    out = []
    for r in unwrap(raw) or []:
        if isinstance(r, dict) and parse_date(r.get("Date")):
            out.append({"date": parse_date(r.get("Date")), **{v: int(_n(r.get(k))) for k, v in CRAWL_FIELDS.items()}})
    return sorted(out, key=lambda r: r["date"])


#: GetCrawlIssues `Issues` bayrakları (bit alanı).
ISSUE_FLAGS = [(1, "301 yönlendirme"), (2, "302 yönlendirme"), (4, "4xx hata"), (8, "5xx hata"),
               (16, "robots.txt engelli"), (32, "zararlı yazılım"), (64, "önemli sayfa robots.txt ile engelli"),
               (128, "DNS hatası"), (256, "zaman aşımı")]


def issue_labels(flags: Any) -> list[str]:
    if isinstance(flags, str) and not flags.strip().lstrip("-").isdigit():
        return [s.strip() for s in flags.split(",") if s.strip() and s.strip() != "None"]
    f = int(_n(flags))
    return [label for bit, label in ISSUE_FLAGS if f & bit]


def issue_rows(raw: Any) -> list[dict[str, Any]]:
    return [{"url": str(r.get("Url") or ""), "httpCode": int(_n(r.get("HttpCode"))) or None,
             "issues": issue_labels(r.get("Issues")), "inLinks": int(_n(r.get("InLinks")))}
            for r in unwrap(raw) or [] if isinstance(r, dict) and r.get("Url")]


def norm_query(q: str) -> str:
    """Google ve Bing sorgusunu aynı biçime getirir: Türkçe büyük harf, fazla boşluk."""
    s = str(q or "").replace("İ", "i").replace("I", "ı").lower().replace("i̇", "i")
    return " ".join(s.split())


def aggregate(rows: list[dict[str, Any]], days: int = PERIOD_DAYS) -> tuple[list[dict[str, Any]], Optional[str], Optional[str]]:
    """Haftalık kovaları son `days` güne göre anahtar başına toplar. Konum gösterimle ağırlıklı ortalamadır.
    Dönem en yeni kovanın tarihinden geriye sayılır (Bing verisi birkaç gün geriden gelir)."""
    dates = [r["date"] for r in rows if r.get("date")]
    if not dates:
        return [], None, None
    end = max(dates)
    since = (datetime.fromisoformat(end) - timedelta(days=days - 1)).date().isoformat()
    acc: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not r.get("date") or r["date"] < since:
            continue
        a = acc.setdefault(norm_query(r["key"]), {"key": r["key"], "clicks": 0, "impressions": 0, "_pw": 0.0, "_w": 0})
        a["clicks"] += r["clicks"]
        a["impressions"] += r["impressions"]
        if r.get("position"):
            w = max(1, r["impressions"])
            a["_pw"] += r["position"] * w
            a["_w"] += w
    out = []
    for a in acc.values():
        out.append({"key": a["key"], "clicks": a["clicks"], "impressions": a["impressions"],
                    "ctr": (a["clicks"] / a["impressions"]) if a["impressions"] else 0.0,
                    "position": round(a["_pw"] / a["_w"], 1) if a["_w"] else None})
    out.sort(key=lambda r: (-r["clicks"], -r["impressions"], r["key"]))
    return out, since, end


def compare(google: list[dict[str, Any]], bing: list[dict[str, Any]], gap: float = GAP) -> dict[str, Any]:
    """Her iki motorda da görünen sorgular yan yana; Bing sırası `gap` kadar gerideyse `worse`. Yalnız Google'da
    olanlar ayrıca sayılır (Bing'de hiç görünmüyor)."""
    b = {norm_query(r["key"]): r for r in bing}
    both, only_google = [], 0
    for g in google:
        q = (g.get("keys") or [""])[0]
        k = norm_query(q)
        if not k:
            continue
        r = b.get(k)
        if not r:
            only_google += 1
            continue
        gp = round(float(g.get("position") or 0), 1) or None
        bp = r["position"]
        diff = round(bp - gp, 1) if (gp and bp) else None
        both.append({"query": q, "google": {"clicks": int(g.get("clicks") or 0), "impressions": int(g.get("impressions") or 0),
                                            "position": gp},
                     "bing": {"clicks": r["clicks"], "impressions": r["impressions"], "position": bp},
                     "gap": diff, "worse": diff is not None and diff >= gap})
    both.sort(key=lambda r: (-r["google"]["impressions"], r["query"]))
    return {"items": both, "onlyGoogle": only_google, "worse": sum(1 for r in both if r["worse"])}


def totals(daily: list[dict[str, Any]], days: int = PERIOD_DAYS) -> dict[str, Any]:
    """Son `days` gün ve ondan önceki aynı uzunlukta dönem."""
    if not daily:
        return {"start": None, "end": None, "clicks": 0, "impressions": 0, "ctr": 0.0, "prevClicks": None, "prevImpressions": None}
    end = datetime.fromisoformat(daily[-1]["date"]).date()
    start = end - timedelta(days=days - 1)
    prev_start = start - timedelta(days=days)
    cur = [r for r in daily if r["date"] >= start.isoformat()]
    prev = [r for r in daily if prev_start.isoformat() <= r["date"] < start.isoformat()]
    c, i = sum(r["clicks"] for r in cur), sum(r["impressions"] for r in cur)
    return {"start": start.isoformat(), "end": end.isoformat(), "clicks": c, "impressions": i,
            "ctr": (c / i) if i else 0.0,
            "prevClicks": sum(r["clicks"] for r in prev) if prev else None,
            "prevImpressions": sum(r["impressions"] for r in prev) if prev else None}


# ------------------------------------------------------------------------------------------------ IndexNow saf yardımcılar

_KEY = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def valid_key(key: str) -> bool:
    """IndexNow anahtarı: 8–128 karakter, yalnız harf, rakam ve tire."""
    return bool(_KEY.match(key or ""))


def site_root(site: str) -> str:
    s = (site or DEFAULT_SITE).strip().rstrip("/")
    return s or DEFAULT_SITE


def key_file_url(site: str, key: str) -> str:
    return f"{site_root(site)}/{key}.txt"


def key_matches(body: str, key: str) -> bool:
    """Dosya yalnız anahtarı taşımalı (baş/son boşluk ve BOM hariç)."""
    return (body or "").lstrip("﻿").strip() == key


#: Parmak izine giren alanlar: arama sonucunu ve sayfanın içeriğini değiştirenler. Kayıtta olmayan alan atlanır.
FP_FIELDS = ("ProductName", "SeoTitle", "SeoDescription", "SearchKeywords", "Details", "SeoLink",
             "SellingPrice", "SellingPriceVatIncluded", "DiscountedSellingPrice", "DiscountedSellingPriceVatIncluded",
             "Price", "ListPrice", "Stock", "StockCount", "IsActive")


def fingerprint(p: dict[str, Any]) -> str:
    parts = {k: ("" if p.get(k) is None else str(p.get(k)).strip()) for k in FP_FIELDS if k in p}
    return hashlib.sha1(dumps(dict(sorted(parts.items()))).encode("utf-8")).hexdigest()


def product_url(p: dict[str, Any], site: str) -> Optional[str]:
    """Ürün sayfasının tam adresi (__init__._product_view ile aynı kural)."""
    link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or ""
    if not link:
        return None
    link = str(link)
    return link if link.startswith("http") else f"{site_root(site)}/{link.lstrip('/')}"


GONE = "gone"


def diff_state(old: dict[str, str], current: dict[str, tuple[str, Optional[str]]]) -> dict[str, list[str]]:
    """old: ürün → son parmak izi; current: etkin ürün → (parmak izi, adres).
    Döner: new (ilk kez görülen), changed (izi değişen ya da geri gelen), gone (artık etkin değil)."""
    new = [pid for pid in current if pid not in old]
    changed = [pid for pid, (fp, _) in current.items() if pid in old and old[pid] != fp]
    gone = [pid for pid, fp in old.items() if pid not in current and fp != GONE]
    return {"new": sorted(new), "changed": sorted(changed), "gone": sorted(gone)}


def batches(items: list[Any], size: int = INDEXNOW_BATCH) -> list[list[Any]]:
    if size < 1:
        raise ValueError("size")
    return [items[i:i + size] for i in range(0, len(items), size)]


def same_host(urls: Iterable[str], host: str) -> list[str]:
    """IndexNow yalnız anahtarın bulunduğu alan adına ait adresleri kabul eder; tekrarlar atılır, sıra korunur."""
    seen: dict[str, None] = {}
    for u in urls:
        if u and urlparse(u).netloc.lower() == host.lower():
            seen.setdefault(u, None)
    return list(seen)


INDEXNOW_STATUS = {200: "Alındı", 202: "Alındı; anahtar doğrulaması sürüyor",
                   400: "İstek geçersiz", 403: "Anahtar geçersiz (dosya bulunamadı ya da içerik farklı)",
                   422: "Adresler bu alan adına ait değil ya da anahtar uyuşmuyor", 429: "Çok sık istek; daha sonra"}


# ------------------------------------------------------------------------------------------------ ağ

class _Redact(logging.Filter):
    """httpx isteği INFO düzeyinde adresiyle yazar; Bing anahtarı adreste gider. Günlükte maskelenir."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        if "apikey=" in msg:
            record.msg, record.args = re.sub(r"apikey=[^&\s\"']+", "apikey=***", msg), ()
        return True


_redact = _Redact()
if not any(isinstance(f, _Redact) for f in logging.getLogger("httpx").filters):
    logging.getLogger("httpx").addFilter(_redact)


def _mask(text: str, key: str) -> str:
    return text.replace(key, "***") if key else text


def bing_call(method: str, key: str, site: str, *, timeout: float = 60) -> Any:
    url = f"{API}/{method}?siteUrl={quote(site, safe='')}&apikey={quote(key, safe='')}"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as c:
            resp = c.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError as e:
        raise BingError(_mask(f"Bing'e ulaşılamadı: {e}", key)) from None
    if resp.status_code >= 400:
        msg = ""
        try:
            body = resp.json()
            msg = str(body.get("Message") or body.get("message") or "") if isinstance(body, dict) else ""
        except ValueError:
            msg = resp.text[:200]
        if resp.status_code in (401, 403) or "InvalidApiKey" in msg:
            raise BingError("Bing anahtarı geçersiz ya da bu site için yetkisi yok (Bing Webmaster → Ayarlar → API erişimi).")
        if "NotAuthorized" in msg or "not verified" in msg.lower():
            raise BingError(f"Site Bing Webmaster'da doğrulanmamış: {site}")
        raise BingError(_mask(f"Bing {method} {resp.status_code}: {msg or 'beklenmeyen cevap'}", key))
    try:
        return resp.json()
    except ValueError:
        raise BingError(f"Bing {method} cevabı okunamadı.") from None


# ------------------------------------------------------------------------------------------------ uçlar

def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


def register(app, ctx) -> None:
    seo = ctx.seo
    lock = threading.Lock()
    submit_lock = threading.Lock()
    state: dict[str, Any] = {"running": False, "startedAt": None, "error": None}
    key_check: dict[str, Any] = {"key": None, "at": 0.0, "ok": False, "error": None, "checkedAt": None}

    def eng() -> sa.engine.Engine:
        e = seo.engine()
        _ensure(e)
        return e

    def site() -> str:
        return site_root(seo.conf("SEO_SITE_URL") or DEFAULT_SITE)

    def bing_key() -> str:
        return (seo.conf("BING_WEBMASTER_API_KEY") or "").strip()

    def ix_key() -> str:
        return (seo.conf("INDEXNOW_KEY") or "").strip()

    # ---------------------------------------------------------------- Bing okuma
    def load() -> dict[str, dict[str, Any]]:
        with eng().connect() as c:
            rows = c.execute(sa.select(BING).where(BING.c.tenant_id == seo.tenant())).mappings().all()
        return {r["kind"]: {"rows": loads(r["rows_json"], []), "error": r["error"], "savedAt": iso(r["saved_at"])} for r in rows}

    def refresh() -> dict[str, Any]:
        key = bing_key()
        if not key:
            raise BingError("Bing Webmaster API anahtarı girilmemiş (Yönetim → SEO & GEO).")
        if not lock.acquire(blocking=False):
            raise BingError("Bing okuması zaten sürüyor.")
        state.update(running=True, startedAt=iso(now()), error=None)
        counts: dict[str, int] = {}
        errors: dict[str, str] = {}
        try:
            url = site() + "/"
            plan = {"queries": ("GetQueryStats", stat_rows), "pages": ("GetPageStats", stat_rows),
                    "daily": ("GetRankAndTrafficStats", daily_rows), "crawl": ("GetCrawlStats", crawl_rows),
                    "issues": ("GetCrawlIssues", issue_rows), "quota": ("GetUrlSubmissionQuota", lambda b: unwrap(b) or {})}
            results: dict[str, Any] = {}
            for kind, (method, parse) in plan.items():
                try:
                    results[kind] = parse(bing_call(method, key, url))
                    counts[kind] = len(results[kind]) if isinstance(results[kind], list) else 1
                except BingError as e:
                    errors[kind] = str(e)[:1000]
            if not results and errors:
                # Hepsi düştüyse aynı hata (anahtar/site) — tek mesaj yeter.
                raise BingError(next(iter(errors.values())))
            tenant, at = seo.tenant(), now()
            with eng().begin() as c:
                for kind in plan:
                    if kind in results:
                        c.execute(BING.delete().where(BING.c.tenant_id == tenant, BING.c.kind == kind))
                        c.execute(BING.insert().values(tenant_id=tenant, kind=kind, rows_json=dumps(results[kind]),
                                                       error=None, saved_at=at))
                    else:
                        c.execute(BING.update().where(BING.c.tenant_id == tenant, BING.c.kind == kind)
                                  .values(error=errors.get(kind)))
            return {"counts": counts, "errors": errors}
        except BingError as e:
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

    @app.get("/api/v1/seo-geo/bing")
    def bing_summary(request: Request) -> dict[str, Any]:
        ctx.gate(request)
        data = load()
        daily = data.get("daily", {}).get("rows", [])
        crawl = data.get("crawl", {}).get("rows", [])
        queries, q_start, q_end = aggregate(data.get("queries", {}).get("rows", []))
        pages, _, _ = aggregate(data.get("pages", {}).get("rows", []))
        g_rows, g_meta = google_queries()
        cmp = compare(g_rows, queries)
        saved = [v["savedAt"] for v in data.values() if v.get("savedAt")]
        quota = data.get("quota", {}).get("rows") or None
        return {
            "configured": bool(bing_key()), "site": site() + "/", "running": state["running"], "error": state["error"],
            "lastRefresh": max(saved) if saved else None,
            "errors": {k: v["error"] for k, v in data.items() if v.get("error")},
            "totals": totals(daily),
            "daily": daily,
            "crawl": crawl,
            "crawlLatest": crawl[-1] if crawl else None,
            "quota": ({"daily": quota.get("DailyQuota"), "monthly": quota.get("MonthlyQuota")} if isinstance(quota, dict) else None),
            "queryPeriod": {"start": q_start, "end": q_end},
            "counts": {"queries": len(queries), "pages": len(pages), "issues": len(data.get("issues", {}).get("rows", [])),
                       "compared": len(cmp["items"]), "worse": cmp["worse"], "onlyGoogle": cmp["onlyGoogle"]},
            "google": g_meta, "gap": GAP,
        }

    @app.get("/api/v1/seo-geo/bing/list/{kind}")
    def bing_list(kind: str, request: Request, start: int = 0, limit: int = 50, q: str = "",
                  filter: str = "") -> dict[str, Any]:
        """Sayfalı listeler: queries | pages | compare | issues. `filter=worse` karşılaştırmada Bing'in çok geride
        olduklarını süzer."""
        ctx.gate(request)
        data = load()
        if kind in ("queries", "pages"):
            items: list[dict[str, Any]] = aggregate(data.get(kind, {}).get("rows", []))[0]
            key = "key"
        elif kind == "compare":
            items = compare(google_queries()[0], aggregate(data.get("queries", {}).get("rows", []))[0])["items"]
            if filter == "worse":
                items = [r for r in items if r["worse"]]
            key = "query"
        elif kind == "issues":
            items = data.get("issues", {}).get("rows", [])
            key = "url"
        else:
            raise _err(404, "Bilinmeyen liste.")
        if q.strip():
            needle = norm_query(q)
            items = [r for r in items if needle in norm_query(r[key])]
        start, limit = max(0, start), max(1, limit)
        return {"total": len(items), "start": start, "items": items[start:start + limit]}

    @app.post("/api/v1/seo-geo/bing/refresh")
    def bing_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        try:
            out = refresh()
        except BingError as e:
            raise _err(409 if "girilmemiş" in str(e) or "sürüyor" in str(e) else 502, str(e)) from None
        seo.audit(user, "run", "bing", "Bing Webmaster okuması", out)
        return out

    # ---------------------------------------------------------------- IndexNow
    def check_key(force: bool = False) -> dict[str, Any]:
        """Anahtar dosyasını sitede okur; 10 dakika içinde aynı anahtar için tekrar okunmaz (force hariç)."""
        key = ix_key()
        if not key or not valid_key(key):
            key_check.update(key=key, ok=False, error=None, checkedAt=None, at=0.0)
            return key_check
        if not force and key_check["key"] == key and time.monotonic() - key_check["at"] < 600:
            return key_check
        url = key_file_url(site(), key)
        ok, error = False, None
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as c:
                resp = c.get(url, headers={"Cache-Control": "no-cache"})
            if resp.status_code != 200:
                error = f"Dosya açılmadı (HTTP {resp.status_code})."
            elif not key_matches(resp.text, key):
                error = "Dosya var ama içeriği anahtarla aynı değil; dosyada yalnız anahtar yazmalı."
            else:
                ok = True
        except httpx.HTTPError as e:
            error = f"Siteye ulaşılamadı: {type(e).__name__}"
        key_check.update(key=key, ok=ok, error=error, at=time.monotonic(), checkedAt=iso(now()))
        return key_check

    def active_products() -> dict[str, tuple[str, Optional[str]]]:
        s = site()
        with eng().connect() as c:
            rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.data_json).where(
                PRODUCTS.c.tenant_id == seo.tenant(), PRODUCTS.c.active.is_(True))).all()
        out = {}
        for pid, raw in rows:
            p = loads(raw, {})
            out[str(pid)] = (fingerprint(p), product_url(p, s))
        return out

    def scan() -> dict[str, Any]:
        """Parmak izlerini günceller. Kayıt hiç yoksa yalnız taban yazılır, kuyruğa bir şey girmez."""
        tenant, at = seo.tenant(), now()
        current = active_products()
        if not current:
            return {"skipped": "etkin ürün yok (T-soft eşitlemesi bekleniyor)"}
        with eng().begin() as c:
            old_rows = c.execute(sa.select(INDEXNOW_STATE.c.product_id, INDEXNOW_STATE.c.fingerprint, INDEXNOW_STATE.c.url)
                                 .where(INDEXNOW_STATE.c.tenant_id == tenant)).all()
            old = {r[0]: r[1] for r in old_rows}
            if not old:
                values = [dict(tenant_id=tenant, product_id=pid, fingerprint=fp, url=(url or "")[:800] or None,
                               pending=False, changed_at=at, notified_at=None) for pid, (fp, url) in current.items()]
                for i in range(0, len(values), 1000):
                    c.execute(INDEXNOW_STATE.insert(), values[i:i + 1000])
                return {"baseline": len(values)}
            d = diff_state(old, current)
            if d["new"]:
                values = [dict(tenant_id=tenant, product_id=pid, fingerprint=current[pid][0],
                               url=(current[pid][1] or "")[:800] or None, pending=True, changed_at=at, notified_at=None)
                          for pid in d["new"]]
                for i in range(0, len(values), 1000):
                    c.execute(INDEXNOW_STATE.insert(), values[i:i + 1000])
            for pid in d["changed"]:
                fp, url = current[pid]
                c.execute(INDEXNOW_STATE.update().where(INDEXNOW_STATE.c.tenant_id == tenant, INDEXNOW_STATE.c.product_id == pid)
                          .values(fingerprint=fp, url=(url or "")[:800] or None, pending=True, changed_at=at))
            if d["gone"]:
                # Satıştan kalkan sayfa da bildirilir: arama motoru sayfanın değiştiğini/kalktığını öğrenir.
                c.execute(INDEXNOW_STATE.update().where(INDEXNOW_STATE.c.tenant_id == tenant,
                                                        INDEXNOW_STATE.c.product_id.in_(d["gone"]))
                          .values(fingerprint=GONE, pending=True, changed_at=at))
        return {k: len(v) for k, v in d.items()}

    def pending_rows() -> list[tuple[str, str]]:
        with eng().connect() as c:
            return [(r[0], r[1]) for r in c.execute(sa.select(INDEXNOW_STATE.c.product_id, INDEXNOW_STATE.c.url).where(
                INDEXNOW_STATE.c.tenant_id == seo.tenant(), INDEXNOW_STATE.c.pending.is_(True))
                .order_by(INDEXNOW_STATE.c.changed_at, INDEXNOW_STATE.c.product_id)).all()]

    def submit(pairs: list[tuple[str, Optional[str]]], kind: str, user: str) -> dict[str, Any]:
        """Adresleri 10.000'lik parçalarla gönderir; başarılı parçadaki kitaplar kuyruktan düşer. Anahtar ya da alan
        adı reddedilirse (403/422) ya da çok sık istek (429) gelirse kalan parçalar gönderilmez."""
        key = ix_key()
        if not key or not valid_key(key):
            raise _err(409, "IndexNow anahtarı girilmemiş ya da biçimi geçersiz (8–128 harf, rakam ya da tire).")
        chk = check_key(force=True)
        if not chk["ok"]:
            raise _err(409, f"Anahtar dosyası sitede doğrulanmadı; bildirim gönderilmedi. {chk['error'] or ''}".strip())
        if not submit_lock.acquire(blocking=False):
            raise _err(409, "Bir bildirim zaten gönderiliyor.")
        try:
            s = site()
            host = urlparse(s).netloc
            by_url: dict[str, list[str]] = {}
            for pid, url in pairs:
                if url:
                    by_url.setdefault(url, []).append(pid)
            urls = same_host(by_url, host)
            skipped = len(pairs) - sum(len(by_url[u]) for u in urls)
            results = []
            tenant = seo.tenant()
            for part in batches(urls):
                code, error = None, None
                try:
                    with httpx.Client(timeout=60) as c:
                        resp = c.post(INDEXNOW_ENDPOINT, json={"host": host, "key": key, "keyLocation": key_file_url(s, key),
                                                               "urlList": part},
                                      headers={"Content-Type": "application/json; charset=utf-8"})
                    code = resp.status_code
                    if code not in (200, 202):
                        error = INDEXNOW_STATUS.get(code, f"Beklenmeyen cevap: {resp.text[:200]}")
                except httpx.HTTPError as e:
                    error = f"IndexNow'a ulaşılamadı: {type(e).__name__}"
                at = now()
                with eng().begin() as c:
                    c.execute(INDEXNOW_LOG.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, at=at, kind=kind,
                                                           count=len(part), status_code=code, error=error, started_by=user))
                    if error is None:
                        ids = [pid for u in part for pid in by_url[u]]
                        for i in range(0, len(ids), 1000):
                            c.execute(INDEXNOW_STATE.update().where(INDEXNOW_STATE.c.tenant_id == tenant,
                                                                    INDEXNOW_STATE.c.product_id.in_(ids[i:i + 1000]))
                                      .values(pending=False, notified_at=at))
                results.append({"count": len(part), "status": code, "error": error})
                if code in (403, 422, 429) or (error and code is None):
                    break
            sent = sum(r["count"] for r in results if r["error"] is None)
            return {"submitted": sent, "urls": len(urls), "skipped": skipped, "batches": results}
        finally:
            submit_lock.release()

    def log_view(r: Any) -> dict[str, Any]:
        return {"id": r["id"], "at": iso(r["at"]), "kind": r["kind"], "count": r["count"], "status": r["status_code"],
                "error": r["error"], "by": r["started_by"],
                "statusText": INDEXNOW_STATUS.get(r["status_code"]) if r["status_code"] else None}

    @app.get("/api/v1/seo-geo/indexnow")
    def indexnow_status(request: Request, recheck: int = 0, start: int = 0, limit: int = 20) -> dict[str, Any]:
        ctx.gate(request)
        key = ix_key()
        chk = check_key(force=bool(recheck))
        tenant = seo.tenant()
        with eng().connect() as c:
            pending = c.execute(sa.select(sa.func.count()).select_from(INDEXNOW_STATE).where(
                INDEXNOW_STATE.c.tenant_id == tenant, INDEXNOW_STATE.c.pending.is_(True))).scalar() or 0
            tracked = c.execute(sa.select(sa.func.count()).select_from(INDEXNOW_STATE).where(
                INDEXNOW_STATE.c.tenant_id == tenant, INDEXNOW_STATE.c.fingerprint != GONE)).scalar() or 0
            baseline = c.execute(sa.select(sa.func.min(INDEXNOW_STATE.c.changed_at)).where(
                INDEXNOW_STATE.c.tenant_id == tenant)).scalar()
            log_total = c.execute(sa.select(sa.func.count()).select_from(INDEXNOW_LOG).where(
                INDEXNOW_LOG.c.tenant_id == tenant)).scalar() or 0
            logs = c.execute(sa.select(INDEXNOW_LOG).where(INDEXNOW_LOG.c.tenant_id == tenant)
                             .order_by(INDEXNOW_LOG.c.at.desc()).offset(max(0, start)).limit(max(1, limit))).mappings().all()
        return {"configured": bool(key), "keyValid": valid_key(key) if key else False,
                "keyFileUrl": key_file_url(site(), key) if key else None,
                "keyFileOk": bool(chk["ok"]), "keyFileError": chk["error"], "checkedAt": chk["checkedAt"],
                "host": urlparse(site()).netloc, "pending": pending, "tracked": tracked, "baselineAt": iso(baseline),
                "logTotal": log_total, "lastSubmissions": [log_view(r) for r in logs], "batchSize": INDEXNOW_BATCH}

    @app.post("/api/v1/seo-geo/indexnow/submit")
    def indexnow_submit(request: Request) -> dict[str, Any]:
        user = ctx.approver(request)
        pairs = pending_rows()
        if not pairs:
            return {"submitted": 0, "urls": 0, "skipped": 0, "batches": []}
        out = submit(pairs, "kuyruk", user)
        seo.audit(user, "run", "indexnow", "IndexNow bildirimi (bekleyenler)", out)
        return out

    @app.post("/api/v1/seo-geo/indexnow/submit-all")
    def indexnow_submit_all(request: Request) -> dict[str, Any]:
        user = ctx.approver(request)
        current = active_products()
        if not current:
            raise _err(409, "Etkin ürün yok; önce T-soft eşitlemesi gerekir.")
        scan()  # taban yoksa kurulsun ki gönderim sonrası kuyruk doğru kalsın
        out = submit([(pid, url) for pid, (_, url) in current.items()], "tumu", user)
        seo.audit(user, "run", "indexnow", "IndexNow bildirimi (bütün kitaplar)", out)
        return out

    # ---------------------------------------------------------------- gece
    def nightly_bing() -> None:
        if not bing_key():
            return
        try:
            refresh()
        except BingError as e:
            log.warning("bing nightly: %s", e)

    def nightly_indexnow() -> None:
        if not ix_key():
            return
        result = scan()
        log.info("indexnow scan: %s", result)
        if "baseline" in result or not valid_key(ix_key()) or not check_key(force=True)["ok"]:
            return
        pairs = pending_rows()
        if pairs:
            try:
                submit(pairs, "gece", "zamanlayıcı")
            except HTTPException as e:
                log.warning("indexnow nightly: %s", e.detail)

    seo.nightly.append(("bing", nightly_bing))
    seo.nightly.append(("indexnow", nightly_indexnow))
