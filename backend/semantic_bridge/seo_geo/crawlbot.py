"""Google taraması: sunucu günlüğü olmadan Googlebot'un sitede ne yaptığı.

(1) URL Denetimi (Search Console `urlInspection/index:inspect`, yalnız okuma). Her adres için Google'ın son hâli:
    karar (verdict), kapsam durumu, dizine alma durumu, robots.txt, sayfa getirme, son tarama zamanı, Google'ın ve
    sitenin canonical'ı, hangi tarayıcıyla (mobil/masaüstü) tarandığı, zengin sonuç öğeleri ve sorunları.
    Kota: Google mülk başına günde 2.000 denetim verir; `SEO_INSPECT_DAILY` (varsayılan 1.800) İstanbul gününe göre
    sayılır (`semantic_seo_inspect_usage`). 429 gelirse o gün için durulur; 403 gelirse servis hesabının mülkte
    sahip/tam yetkili olmadığı yazılır ve durulur.
    Sıra: son `RECENT_DAYS` günde bakılmamış etkin ürünler çok satandan aza, sonra yazar/kategori/yayınevi sayfaları
    ve anasayfa, sonra en eski bakılan. Kota dolunca ertesi gün kaldığı yerden sürer (sessiz tavan yok; günlük kota
    bir ayardır).
    Dil: istek `en-US` ile yapılır. Google kapsam metnini istek diline çevirir; sınıflandırma (dizinde / tarandı ama
    dizinde değil / keşfedildi ama taranmadı …) İngilizce metinde kararlıdır. Ekrana giden etiketler buradaki Türkçe
    karşılıklardır; ham metin ayrıntıda durur. Türkçe metin gelirse de tanınır (yedek kalıplar).

(2) Site ağ geçidi bot istatistiği (Cloudflare GraphQL Analytics, yalnız okuma; `CLOUDFLARE_API_TOKEN` ve
    `CLOUDFLARE_ZONE_ID` girilmişse). `httpRequestsAdaptiveGroups` veri kümesinden, kullanıcı ajanı bilinen arama ve
    yapay zekâ botlarını içeren istekler gün (UTC) × bot × durum kodu, ayrıca en çok istenen yollar. Doğrulanmış bot
    alanı (`verifiedBotCategory`) plan izin veriyorsa kullanılır; vermiyorsa sayılar "kendini X olarak tanıtan"
    diye etiketlenir (kullanıcı ajanı taklit edilebilir). Planın vermediği alan/veri kümesi hata metniyle kaydedilir,
    ekran "planınız bu veriyi vermiyor" der.

Hiçbir yere yazılmaz: Search Console'a, Cloudflare'e, T-soft'a ve CRM'e yalnız okuma istekleri gider.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx
import sqlalchemy as sa
from fastapi import HTTPException, Request

from .store import LINKS, PRODUCTS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo.crawlbot")

INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
CF_GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"
IST = ZoneInfo("Europe/Istanbul")
DEFAULT_SITE = "https://timas.com.tr"
INSPECT_LANG = "en-US"

#: Son bu kadar günde denetlenmiş adres öncelik sırasında geriye düşer.
RECENT_DAYS = 14
#: Google bu kadar gündür taramadıysa "bayat" sayılır.
STALE_CRAWL_DAYS = 30
#: SEO_INSPECT_DAILY boşsa: Google'ın günlük 2.000'inden pay bırakır (elle denetim için).
DEFAULT_DAILY = 1800
#: İstekler arası en az bekleme: Google'ın dakikada 600 sınırının altında kalır (≤ 500/dk).
MIN_INTERVAL = 0.12
#: Bir denetim turunun süre bütçesi (sn); dolunca kalan ertesi tura kalır.
RUN_BUDGET_SEC = 5400
#: Cloudflare: veri yoksa en çok bu kadar gün geriye gidilir (planın saklama süresi daha kısaysa hata ile durur).
BOT_BACKFILL_DAYS = 7
#: Son bu kadar gün her okumada yeniden alınır (geç gelen veri).
BOT_REFRESH_DAYS = 2
#: Bot başına saklanan "en çok istenen yol" sayısı (ekranda "en çok istenen 50 yol" diye yazar).
TOP_PATHS = 50
#: Cloudflare bir sorguda en çok 10.000 grup döndürür; dolarsa gün "kısmi" işaretlenir.
CF_ROW_LIMIT = 10_000
#: Art arda bu kadar ağ hatasında tur durur (Google'a ulaşılamıyor; kalan ertesi tura).
NET_FAIL_STOP = 5

INSPECT = sa.Table(
    "semantic_seo_inspect", _md,  # adres başına Google URL Denetimi son hâli
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("url", sa.String(800), primary_key=True),
    sa.Column("product_id", sa.String(40), index=True),
    sa.Column("kind", sa.String(16), nullable=False),          # product | author | category | brand | home
    sa.Column("status", sa.String(24), nullable=False),        # sınıf: indexed | crawled_not_indexed | …
    sa.Column("verdict", sa.String(24)),
    sa.Column("coverage", sa.String(300)),
    sa.Column("indexing", sa.String(40)),
    sa.Column("robots", sa.String(40)),
    sa.Column("fetch", sa.String(40)),
    sa.Column("last_crawl", sa.DateTime(timezone=True)),
    sa.Column("google_canonical", sa.String(800)),
    sa.Column("user_canonical", sa.String(800)),
    sa.Column("canonical_mismatch", sa.Boolean, nullable=False, default=False),
    sa.Column("crawled_as", sa.String(16)),
    sa.Column("rich_json", sa.Text),                          # {verdict, types, issues:[{type, message, severity}]}
    sa.Column("data_json", sa.Text),                          # referringUrls, sitemap, mobile, link
    sa.Column("error", sa.String(500)),
    sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False),
)
INSPECT_HIST = sa.Table(
    "semantic_seo_inspect_hist", _md,  # her denetimin kısa kaydı (durum değişimini izlemek için)
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("url", sa.String(800), nullable=False, index=True),
    sa.Column("status", sa.String(24), nullable=False),
    sa.Column("verdict", sa.String(24)),
    sa.Column("coverage", sa.String(300)),
    sa.Column("last_crawl", sa.DateTime(timezone=True)),
    sa.Column("canonical_mismatch", sa.Boolean),
    sa.Column("crawled_as", sa.String(16)),
    sa.Column("error", sa.String(500)),
    sa.Column("inspected_at", sa.DateTime(timezone=True), nullable=False, index=True),
)
USAGE = sa.Table(
    "semantic_seo_inspect_usage", _md,  # İstanbul günü başına harcanan denetim kotası
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("day", sa.String(10), primary_key=True),
    sa.Column("used", sa.Integer, nullable=False, default=0),
    sa.Column("stopped", sa.String(24)),                      # quota: Google 429 verdi, gün bitti
    sa.Column("note", sa.String(500)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
BOTSTATS = sa.Table(
    "semantic_seo_botstats", _md,  # site ağ geçidinden gün (UTC) × bot özetleri
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("day", sa.String(10), primary_key=True),
    sa.Column("bot", sa.String(32), primary_key=True),
    sa.Column("requests", sa.Integer, nullable=False),
    sa.Column("verified", sa.Integer),                        # doğrulanmış bot isteği; plan vermiyorsa None
    sa.Column("status_json", sa.Text, nullable=False),        # {"200": n, "404": n}
    sa.Column("top_paths_json", sa.Text, nullable=False),     # [{path, count}]
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
STATE = sa.Table(
    "semantic_seo_crawlbot_state", _md,  # son tur bilgisi ve hatalar: inspect | bots
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kind", sa.String(16), primary_key=True),
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
_TABLES = (INSPECT, INSPECT_HIST, USAGE, BOTSTATS, STATE)
_ready: set[int] = set()
_ready_lock = threading.Lock()


def _ensure(eng: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(eng) in _ready:
            return
        for t in _TABLES:
            t.create(eng, checkfirst=True)
        _ready.add(id(eng))


# ================================================================================================ saf: gün ve kota

def istanbul_day(at: Optional[datetime] = None) -> str:
    """Kota günü: İstanbul saatine göre YYYY-AA-GG."""
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.astimezone(IST).date().isoformat()


def daily_limit(raw: Any) -> int:
    """Ayar metni → günlük kota. Boş/bozuk → varsayılan; negatif → 0."""
    try:
        v = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_DAILY
    return max(0, v)


def remaining(used: int, daily: int, stopped: Optional[str] = None) -> int:
    if stopped:
        return 0
    return max(0, int(daily) - int(used or 0))


# ================================================================================================ saf: denetim cevabı

def norm_url(u: Optional[str]) -> str:
    """Karşılaştırma için: şema/alan adı küçük harf, parça (#) yok, sondaki / yok (kök hariç)."""
    if not u:
        return ""
    s = urlsplit(str(u).strip())
    path = s.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    return urlunsplit((s.scheme.lower(), s.netloc.lower(), path, s.query, ""))


def canonical_mismatch(url: str, google: Optional[str], user: Optional[str]) -> bool:
    """Google'ın seçtiği canonical sitenin bildirdiğinden (bildirmediyse denetlenen adresten) farklıysa."""
    if not google:
        return False
    return norm_url(google) != norm_url(user or url)


def _dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_rich(raw: Any) -> Optional[dict[str, Any]]:
    """richResultsResult → {verdict, types, issues:[{type, item, message, severity}]}."""
    if not isinstance(raw, dict):
        return None
    types, issues = [], []
    for d in raw.get("detectedItems") or []:
        t = str(d.get("richResultType") or "")
        if t and t not in types:
            types.append(t)
        for it in d.get("items") or []:
            for i in it.get("issues") or []:
                issues.append({"type": t, "item": it.get("name"), "message": i.get("issueMessage") or "",
                               "severity": i.get("severity") or ""})
    return {"verdict": raw.get("verdict"), "types": types, "issues": issues}


def parse_inspection(body: Any, url: str) -> dict[str, Any]:
    """Denetim cevabı → düz kayıt (sınıf dahil)."""
    res = (body or {}).get("inspectionResult") or {}
    ix = res.get("indexStatusResult") or {}
    mob = res.get("mobileUsabilityResult")
    google, user = ix.get("googleCanonical"), ix.get("userCanonical")
    out = {
        "verdict": ix.get("verdict"), "coverage": ix.get("coverageState"), "indexing": ix.get("indexingState"),
        "robots": ix.get("robotsTxtState"), "fetch": ix.get("pageFetchState"),
        "last_crawl": _dt(ix.get("lastCrawlTime")), "google_canonical": google, "user_canonical": user,
        "canonical_mismatch": canonical_mismatch(url, google, user), "crawled_as": ix.get("crawledAs"),
        "rich": parse_rich(res.get("richResultsResult")),
        "data": {"referringUrls": ix.get("referringUrls") or [], "sitemap": ix.get("sitemap") or [],
                 "link": res.get("inspectionResultLink"),
                 "mobile": ({"verdict": mob.get("verdict"),
                             "issues": [i.get("message") or i.get("issueType") for i in mob.get("issues") or []]}
                            if isinstance(mob, dict) else None)},
    }
    out["status"] = classify(out)
    return out


FETCH_ERRORS = {"SOFT_404", "BLOCKED_ROBOTS_TXT", "NOT_FOUND", "ACCESS_DENIED", "SERVER_ERROR", "REDIRECT_ERROR",
                "ACCESS_FORBIDDEN", "BLOCKED_4XX", "INTERNAL_CRAWL_ERROR", "INVALID_URL"}

#: Sınıf → (ekran etiketi, ton). Sıra ekrandaki sıradır.
STATUS_LABEL: dict[str, tuple[str, str]] = {
    "indexed": ("Dizinde", "good"),
    "crawled_not_indexed": ("Tarandı ama dizinde değil", "bad"),
    "discovered_not_crawled": ("Keşfedildi ama taranmadı", "mid"),
    "unknown": ("Google bu adresi bilmiyor", "mid"),
    "duplicate": ("Kopya: Google başka canonical seçti", "mid"),
    "alternate": ("Başka sayfanın alternatifi", "violet"),
    "redirect": ("Yönlendiriliyor", "violet"),
    "noindex": ("Dizine kapalı (noindex)", "bad"),
    "robots_blocked": ("robots.txt engelliyor", "bad"),
    "not_found": ("Bulunamadı (404)", "bad"),
    "soft_404": ("Boş sayfa sayıldı (soft 404)", "bad"),
    "fetch_error": ("Google sayfayı açamadı", "bad"),
    "other": ("Dizinde değil (diğer)", "mid"),
    "error": ("Denetlenemedi", "bad"),
}
ERROR_STATUSES = {"noindex", "robots_blocked", "not_found", "soft_404", "fetch_error", "error"}


def classify(r: dict[str, Any]) -> str:
    """Kapsam metni, dizine alma, robots ve getirme durumundan tek sınıf. İngilizce metin esas, Türkçe yedek."""
    cov = str(r.get("coverage") or "").lower()
    fetch = str(r.get("fetch") or "").upper()
    indexing = str(r.get("indexing") or "").upper()
    robots = str(r.get("robots") or "").upper()
    verdict = str(r.get("verdict") or "").upper()
    if cov.startswith("indexed") or cov.startswith("submitted and indexed"):
        return "indexed"  # "Indexed, though blocked by robots.txt" de dizindedir
    if "not indexed" in cov or "dizine eklenmedi" in cov or "dizine eklenmemiş" in cov or "dizinde değil" in cov:
        if "crawled" in cov or "tarandı" in cov:
            return "crawled_not_indexed"
        if "discovered" in cov or "keşfedildi" in cov:
            return "discovered_not_crawled"
    if "unknown to google" in cov or "google tarafından bilinmiyor" in cov:
        return "unknown"
    if indexing in ("BLOCKED_BY_META_TAG", "BLOCKED_BY_HTTP_HEADER") or "noindex" in cov:
        return "noindex"
    if robots == "DISALLOWED" or fetch == "BLOCKED_ROBOTS_TXT" or "robots.txt" in cov:
        return "robots_blocked"
    if fetch == "SOFT_404" or "soft 404" in cov:
        return "soft_404"
    if fetch == "NOT_FOUND" or "404" in cov:
        return "not_found"
    if fetch in FETCH_ERRORS or "server error" in cov or "sunucu hatası" in cov:
        return "fetch_error"
    if "duplicate" in cov or "kopya" in cov:
        return "duplicate"
    if "alternate" in cov or "alternatif" in cov:
        return "alternate"
    if "redirect" in cov or "yönlendirme" in cov:
        return "redirect"
    if verdict == "PASS" or ("indexed" in cov and "not" not in cov) or ("dizine eklendi" in cov):
        return "indexed"
    return "other"


def row_status(r: dict[str, Any]) -> str:
    """Son denetim hata verdiyse "error" (önceki sonuç ayrıntıda korunur), yoksa kayıtlı sınıf."""
    return "error" if r.get("error") else str(r.get("status") or "other")


def days_since(last: Optional[datetime], at: Optional[datetime] = None) -> Optional[int]:
    if last is None:
        return None
    at = at or datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return max(0, (at - last).days)


AGE_BUCKETS = (("0–7 gün", 0, 7), ("8–14 gün", 8, 14), ("15–30 gün", 15, 30), ("31–90 gün", 31, 90),
               ("90 günden eski", 91, None))


def age_bucket(days: Optional[int]) -> str:
    if days is None:
        return "Hiç taranmamış"
    for label, lo, hi in AGE_BUCKETS:
        if days >= lo and (hi is None or days <= hi):
            return label
    return AGE_BUCKETS[-1][0]


def is_stale(row: dict[str, Any], at: Optional[datetime] = None) -> bool:
    """Google'ın taramadığı ya da STALE_CRAWL_DAYS'ten uzun süredir taramadığı (başarıyla denetlenmiş) adres."""
    if row.get("error"):
        return False
    d = days_since(row.get("last_crawl"), at)
    return d is None or d > STALE_CRAWL_DAYS


def summarize(rows: list[dict[str, Any]], products: dict[str, dict[str, Any]],
              at: Optional[datetime] = None) -> dict[str, Any]:
    """rows: INSPECT kayıtları; products: ürün → {name, sales, active}."""
    at = at or datetime.now(timezone.utc)
    by_status: dict[str, int] = {}
    ages = {label: 0 for label, _, _ in AGE_BUCKETS}
    ages["Hiç taranmamış"] = 0
    crawled_as: dict[str, int] = {}
    ok = [r for r in rows if not r.get("error")]
    for r in rows:
        k = row_status(r)
        by_status[k] = by_status.get(k, 0) + 1
    for r in ok:
        ages[age_bucket(days_since(r.get("last_crawl"), at))] += 1
        if r.get("crawled_as"):
            crawled_as[r["crawled_as"]] = crawled_as.get(r["crawled_as"], 0) + 1
    stale_sellers = [r for r in ok if r.get("kind") == "product" and is_stale(r, at)
                     and (products.get(str(r.get("product_id"))) or {}).get("sales", 0) > 0]
    rich_rows = [r for r in ok if (r.get("rich") or {}).get("issues")]
    indexed = by_status.get("indexed", 0)
    return {
        "total": len(rows), "inspected": len(ok), "errors": len(rows) - len(ok),
        "byStatus": [{"status": k, "label": STATUS_LABEL.get(k, (k, "mid"))[0], "tone": STATUS_LABEL.get(k, (k, "mid"))[1],
                      "count": by_status[k]} for k in STATUS_LABEL if by_status.get(k)],
        "indexed": indexed, "indexedShare": (indexed / len(ok)) if ok else None,
        "crawledNotIndexed": by_status.get("crawled_not_indexed", 0),
        "discoveredNotCrawled": by_status.get("discovered_not_crawled", 0),
        "canonicalMismatch": sum(1 for r in ok if r.get("canonical_mismatch")),
        "staleSellers": len(stale_sellers),
        "crawlAge": [{"label": k, "count": v} for k, v in ages.items()],
        "crawledAs": crawled_as,
        "richIssues": sum(len(r["rich"]["issues"]) for r in rich_rows), "richIssuePages": len(rich_rows),
        "productsInspected": sum(1 for r in rows if r.get("kind") == "product"),
    }


# ================================================================================================ saf: sıra

def build_queue(products: list[dict[str, Any]], pages: list[dict[str, Any]], inspected: dict[str, datetime],
                at: Optional[datetime] = None, recent_days: int = RECENT_DAYS) -> list[dict[str, Any]]:
    """products: [{url, productId, sales}] (sıra önemsiz), pages: [{url, kind}] (anasayfa dahil).
    1) son `recent_days` günde bakılmamış ürünler, çok satandan aza (eşitlikte hiç bakılmamış/eskisi önce);
    2) son `recent_days` günde bakılmamış sayfalar (anasayfa önce, sonra verilen sıra);
    3) geri kalan her şey, en eski bakılan önce. Adres tekrarı atılır."""
    at = at or datetime.now(timezone.utc)
    cutoff = at - timedelta(days=recent_days)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)

    def when(u: str) -> Optional[datetime]:
        v = inspected.get(u)
        if v is not None and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v

    def due(u: str) -> bool:
        w = when(u)
        return w is None or w < cutoff

    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for p in products:
        if p.get("url") and p["url"] not in seen:
            seen.add(p["url"])
            items.append({"url": p["url"], "kind": "product", "productId": p.get("productId"),
                          "sales": float(p.get("sales") or 0)})
    for i, p in enumerate(sorted(pages, key=lambda x: x.get("kind") != "home")):
        if p.get("url") and p["url"] not in seen:
            seen.add(p["url"])
            items.append({"url": p["url"], "kind": p.get("kind") or "page", "productId": None, "sales": 0.0, "_i": i})
    tier1 = sorted((t for t in items if t["kind"] == "product" and due(t["url"])),
                   key=lambda t: (-t["sales"], when(t["url"]) or epoch, t["url"]))
    tier2 = sorted((t for t in items if t["kind"] != "product" and due(t["url"])), key=lambda t: t["_i"])
    rest = sorted((t for t in items if not due(t["url"])), key=lambda t: (when(t["url"]) or epoch, t["url"]))
    return [{k: v for k, v in t.items() if k != "_i"} for t in tier1 + tier2 + rest]


# ================================================================================================ saf: botlar

#: (anahtar, ekran adı, grup, kullanıcı ajanında aranan parçalar). Sıra önemli: ilk eşleşen kazanır.
BOTS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("googlebot_media", "Googlebot (görsel/video/haber)", "arama", ("Googlebot-Image", "Googlebot-Video", "Googlebot-News")),
    ("googlebot_mobile", "Googlebot (akıllı telefon)", "arama", ()),   # Googlebot + "Mobile"
    ("googlebot_desktop", "Googlebot (masaüstü)", "arama", ("Googlebot",)),
    ("google_other", "Google (diğer tarayıcılar)", "arama", ("GoogleOther", "Google-InspectionTool", "Storebot-Google",
                                                             "AdsBot-Google", "Google-Extended")),
    ("bingbot", "Bingbot", "arama", ("bingbot", "BingPreview")),
    ("yandex", "YandexBot", "arama", ("YandexBot", "YandexImages", "YandexMobileBot")),
    ("applebot", "Applebot", "arama", ("Applebot",)),
    ("oai_search", "OAI-SearchBot", "yapay zekâ araması", ("OAI-SearchBot",)),
    ("chatgpt_user", "ChatGPT-User", "yapay zekâ araması", ("ChatGPT-User",)),
    ("gptbot", "GPTBot", "yapay zekâ eğitimi", ("GPTBot",)),
    ("perplexity", "PerplexityBot", "yapay zekâ araması", ("PerplexityBot", "Perplexity-User")),
    ("claude_search", "Claude-SearchBot", "yapay zekâ araması", ("Claude-SearchBot", "Claude-User")),
    ("claudebot", "ClaudeBot", "yapay zekâ eğitimi", ("ClaudeBot",)),
]
BOT_LABEL = {k: (label, group) for k, label, group, _ in BOTS}
#: Cloudflare süzgecinde aranacak parçalar (büyük/küçük harf kullanıcı ajanındaki gibi).
UA_TOKENS = ("Googlebot", "GoogleOther", "Google-InspectionTool", "Storebot-Google", "AdsBot-Google", "bingbot",
             "BingPreview", "YandexBot", "YandexImages", "YandexMobileBot", "Applebot", "OAI-SearchBot", "ChatGPT-User",
             "GPTBot", "PerplexityBot", "Perplexity-User", "Claude-SearchBot", "Claude-User", "ClaudeBot")


def bot_of(ua: Optional[str]) -> Optional[str]:
    """Kullanıcı ajanı → bot anahtarı; tanınmıyorsa None."""
    s = str(ua or "")
    low = s.lower()
    for key, _, _, tokens in BOTS:
        if key == "googlebot_mobile":
            if "googlebot" in low and "mobile" in low and not any(t.lower() in low for t in BOTS[0][3]):
                return key
            continue
        if any(t.lower() in low for t in tokens):
            return key
    return None


def status_class(code: Any) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "diğer"
    return f"{c // 100}xx" if 100 <= c < 600 else "diğer"


class CfError(RuntimeError):
    """kind: auth (anahtar/bölge), plan (alan ya da veri kümesi planda yok), range (saklama süresi dışı), net."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def cf_filter(day: str, hosts: list[str]) -> dict[str, Any]:
    start = datetime.fromisoformat(day).replace(tzinfo=timezone.utc)
    f: dict[str, Any] = {"datetime_geq": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "datetime_lt": (start + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "OR": [{"userAgent_like": f"%{t}%"} for t in UA_TOKENS]}
    if hosts:
        f["clientRequestHTTPHost_in"] = hosts
    return f


def cf_query(dims: Iterable[str], limit: int = CF_ROW_LIMIT) -> str:
    return ("query Bots($zoneTag: string, $filter: ZoneHttpRequestsAdaptiveGroupsFilter_InputObject) {"
            " viewer { zones(filter: {zoneTag: $zoneTag}) {"
            f" rows: httpRequestsAdaptiveGroups(filter: $filter, limit: {int(limit)}, orderBy: [count_DESC]) {{"
            f" count dimensions {{ {' '.join(dims)} }} }} }} }} }}")


_PLAN_HINTS = ("does not have access", "not available", "unknown field", "cannot query field", "not allowed",
               "not enabled", "plan", "unauthorized to access dataset", "no access")
_RANGE_HINTS = ("too old", "older than", "time range", "cannot request data", "retention", "out of range",
                "exceeds", "maximum")


def cf_parse(status_code: int, body: Any) -> list[dict[str, Any]]:
    """Cevap → satırlar [{count, dimensions}]. Hata → CfError (türüyle)."""
    if status_code in (401, 403):
        raise CfError("auth", "Site ağ geçidi anahtarı geçersiz ya da Analytics okuma yetkisi yok.")
    if not isinstance(body, dict):
        raise CfError("net", f"Site ağ geçidi beklenmeyen cevap verdi (HTTP {status_code}).")
    errors = body.get("errors") or []
    if errors:
        msg = "; ".join(str(e.get("message") or e) if isinstance(e, dict) else str(e) for e in errors)[:500]
        low = msg.lower()
        codes = " ".join(str((e.get("extensions") or {}).get("code") or "") for e in errors if isinstance(e, dict)).lower()
        if "authz" in codes or "not authorized" in low or "authentication" in low or "permission" in low:
            raise CfError("auth", f"Site ağ geçidi yetkisi yetmedi: {msg}")
        if any(h in low for h in _RANGE_HINTS):
            raise CfError("range", msg)
        raise CfError("plan", msg)
    if status_code >= 400:
        raise CfError("net", f"Site ağ geçidi HTTP {status_code}.")
    zones = (((body.get("data") or {}).get("viewer") or {}).get("zones")) or []
    if not zones:
        raise CfError("auth", "Bölge (zone) bulunamadı ya da anahtarın bu bölgeye yetkisi yok.")
    rows = zones[0].get("rows") or []
    return [r for r in rows if isinstance(r, dict)]


def aggregate_bots(rows: list[dict[str, Any]], path_rows: Optional[list[dict[str, Any]]],
                   verified_field: bool, top: int = TOP_PATHS) -> dict[str, dict[str, Any]]:
    """Gün içindeki satırlar → bot başına {requests, verified, status, topPaths}."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        dims = r.get("dimensions") or {}
        bot = bot_of(dims.get("userAgent"))
        if not bot:
            continue
        n = int(r.get("count") or 0)
        a = out.setdefault(bot, {"requests": 0, "verified": 0 if verified_field else None, "status": {}, "paths": {}})
        a["requests"] += n
        code = str(dims.get("edgeResponseStatus") or "?")
        a["status"][code] = a["status"].get(code, 0) + n
        if verified_field and dims.get("verifiedBotCategory"):
            a["verified"] += n
    for r in path_rows or []:
        dims = r.get("dimensions") or {}
        bot = bot_of(dims.get("userAgent"))
        if not bot or bot not in out:
            continue
        p = str(dims.get("clientRequestPath") or "/")
        out[bot]["paths"][p] = out[bot]["paths"].get(p, 0) + int(r.get("count") or 0)
    for a in out.values():
        paths = a.pop("paths")
        a["topPaths"] = [{"path": k, "count": v} for k, v in sorted(paths.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]
    return out


def hosts_of(site: str) -> list[str]:
    host = urlsplit(site).netloc.lower()
    if not host:
        return []
    bare = host[4:] if host.startswith("www.") else host
    return [bare, f"www.{bare}"]


# ================================================================================================ ağ

class InspectError(RuntimeError):
    """kind: permission (403), quota (429), bad (400 vb., adres başına), net."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def _google_message(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error", {}).get("message") or "")[:300]
    except ValueError:
        return resp.text[:300]


def inspect_url(url: str, site: str) -> dict[str, Any]:
    """Tek adres. Belirteç `connections.google_token()` ile (webmasters.readonly kapsamı denetim için yeterli)."""
    from . import connections

    body = {"inspectionUrl": url, "siteUrl": site, "languageCode": INSPECT_LANG}
    for attempt in (0, 1):
        try:
            token = connections.google_token()
            with httpx.Client(timeout=60) as c:
                resp = c.post(INSPECT_URL, json=body, headers={"Authorization": f"Bearer {token}"})
        except connections.ConnectionError_ as e:
            raise InspectError("permission", str(e)) from None
        except httpx.HTTPError as e:
            raise InspectError("net", f"Google'a ulaşılamadı: {type(e).__name__}") from None
        if resp.status_code == 401 and attempt == 0:
            connections._GTOKEN["token"] = None  # süresi dolmuş belirteç: bir kez yenile
            continue
        if resp.status_code == 403:
            raise InspectError("permission", f"Search Console erişimi reddetti: servis hesabı "
                                             f"({connections.service_account_email()}) Search Console'da bu mülke "
                                             f"sahip/tam yetkili olarak eklenmeli. {_google_message(resp)}".strip())
        if resp.status_code == 429:
            raise InspectError("quota", f"Google günlük denetim kotası doldu. {_google_message(resp)}".strip())
        if resp.status_code >= 400:
            raise InspectError("bad", f"Google {resp.status_code}: {_google_message(resp) or 'beklenmeyen cevap'}")
        try:
            return resp.json()
        except ValueError:
            raise InspectError("bad", "Google cevabı okunamadı.") from None
    raise InspectError("permission", "Google belirteci kabul etmedi.")


def cf_call(token: str, zone: str, dims: list[str], day: str, hosts: list[str]) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=60) as c:
            resp = c.post(CF_GRAPHQL, headers={"Authorization": f"Bearer {token}"},
                          json={"query": cf_query(dims), "variables": {"zoneTag": zone, "filter": cf_filter(day, hosts)}})
    except httpx.HTTPError as e:
        raise CfError("net", f"Site ağ geçidine ulaşılamadı: {type(e).__name__}") from None
    try:
        body = resp.json()
    except ValueError:
        body = None
    return cf_parse(resp.status_code, body)


# ================================================================================================ uçlar

def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


FILTERS = ("all", "not_indexed", "canonical", "stale", "errors", "rich")


def register(app, ctx) -> None:
    seo = ctx.seo
    ilock, block = threading.Lock(), threading.Lock()
    istate: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "done": 0, "failed": 0,
                              "queue": None, "error": None, "stoppedBy": None}
    bstate: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None}

    def eng() -> sa.engine.Engine:
        e = seo.engine()
        _ensure(e)
        return e

    def site() -> str:
        return (seo.conf("SEO_SITE_URL") or DEFAULT_SITE).strip().rstrip("/") or DEFAULT_SITE

    def gsc_site() -> str:
        return (seo.conf("GSC_SITE") or "").strip()

    def sa_email() -> Optional[str]:
        from . import connections

        return connections.service_account_email()

    def inspect_configured() -> bool:
        return bool(gsc_site()) and bool(sa_email())

    def cf_creds() -> tuple[str, str]:
        return (seo.conf("CLOUDFLARE_API_TOKEN") or "").strip(), (seo.conf("CLOUDFLARE_ZONE_ID") or "").strip()

    def get_state(kind: str) -> dict[str, Any]:
        with eng().connect() as c:
            r = c.execute(sa.select(STATE.c.data_json, STATE.c.saved_at).where(
                STATE.c.tenant_id == seo.tenant(), STATE.c.kind == kind)).first()
        return {**loads(r[0], {}), "savedAt": iso(r[1])} if r else {}

    def put_state(kind: str, data: dict[str, Any]) -> None:
        tenant = seo.tenant()
        with eng().begin() as c:
            c.execute(STATE.delete().where(STATE.c.tenant_id == tenant, STATE.c.kind == kind))
            c.execute(STATE.insert().values(tenant_id=tenant, kind=kind, data_json=dumps(data), saved_at=now()))

    # ---------------------------------------------------------------- kota
    def usage(day: str) -> tuple[int, Optional[str]]:
        with eng().connect() as c:
            r = c.execute(sa.select(USAGE.c.used, USAGE.c.stopped).where(
                USAGE.c.tenant_id == seo.tenant(), USAGE.c.day == day)).first()
        return (int(r[0] or 0), r[1]) if r else (0, None)

    def bump(day: str, n: int = 1, stopped: Optional[str] = None, note: Optional[str] = None) -> None:
        tenant = seo.tenant()
        with eng().begin() as c:
            r = c.execute(sa.select(USAGE.c.used).where(USAGE.c.tenant_id == tenant, USAGE.c.day == day)).first()
            if r is None:
                c.execute(USAGE.insert().values(tenant_id=tenant, day=day, used=n, stopped=stopped, note=note,
                                                updated_at=now()))
            else:
                vals: dict[str, Any] = {"used": int(r[0] or 0) + n, "updated_at": now()}
                if stopped:
                    vals.update(stopped=stopped, note=(note or "")[:500])
                c.execute(USAGE.update().where(USAGE.c.tenant_id == tenant, USAGE.c.day == day).values(**vals))

    def quota_view() -> dict[str, Any]:
        day = istanbul_day()
        used, stopped = usage(day)
        limit = daily_limit(seo.conf("SEO_INSPECT_DAILY") or DEFAULT_DAILY)
        return {"day": day, "used": used, "limit": limit, "remaining": remaining(used, limit, stopped), "stopped": stopped}

    # ---------------------------------------------------------------- denetim
    def product_info() -> dict[str, dict[str, Any]]:
        from . import SALES

        with eng().connect() as c:
            rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.active, PRODUCTS.c.data_json,
                                       SALES).where(PRODUCTS.c.tenant_id == seo.tenant())).all()
        s = site()
        out = {}
        for pid, name, active, data, sales in rows:
            p = loads(data, {})
            link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or ""
            url = (str(link) if str(link).startswith("http") else f"{s}/{str(link).strip('/')}") if link else None
            out[str(pid)] = {"name": name or "", "active": bool(active), "sales": float(sales or 0), "url": url}
        return out

    def queue() -> list[dict[str, Any]]:
        prods = [{"url": v["url"], "productId": pid, "sales": v["sales"]}
                 for pid, v in product_info().items() if v["active"] and v["url"]]
        kind_of = {"model": "author", "category": "category", "brand": "brand"}
        with eng().connect() as c:
            links = c.execute(sa.select(LINKS.c.link, LINKS.c.type).where(
                LINKS.c.tenant_id == seo.tenant(), LINKS.c.type.in_(list(kind_of)))
                .order_by(LINKS.c.type.desc(), LINKS.c.link)).all()  # model, category, brand
            inspected = dict(c.execute(sa.select(INSPECT.c.url, INSPECT.c.inspected_at).where(
                INSPECT.c.tenant_id == seo.tenant())).all())
        order = {"model": 0, "category": 1, "brand": 2}
        s = site()
        pages = [{"url": f"{s}/", "kind": "home"}] + [
            {"url": f"{s}/{str(l).strip('/')}", "kind": kind_of[t]}
            for l, t in sorted(links, key=lambda r: (order.get(r[1], 9), r[0])) if l]
        return build_queue(prods, pages, inspected)

    def store(target: dict[str, Any], parsed: Optional[dict[str, Any]], error: Optional[str]) -> None:
        tenant, at = seo.tenant(), now()
        p = parsed or {"status": "error"}
        row = dict(tenant_id=tenant, url=target["url"][:800], product_id=target.get("productId"),
                   kind=target.get("kind") or "page", status=p["status"], verdict=p.get("verdict"),
                   coverage=(p.get("coverage") or None) and str(p["coverage"])[:300], indexing=p.get("indexing"),
                   robots=p.get("robots"), fetch=p.get("fetch"), last_crawl=p.get("last_crawl"),
                   google_canonical=(p.get("google_canonical") or None) and p["google_canonical"][:800],
                   user_canonical=(p.get("user_canonical") or None) and p["user_canonical"][:800],
                   canonical_mismatch=bool(p.get("canonical_mismatch")), crawled_as=p.get("crawled_as"),
                   rich_json=dumps(p.get("rich")) if p.get("rich") else None,
                   data_json=dumps(p.get("data")) if p.get("data") else None,
                   error=(error or None) and error[:500], inspected_at=at)
        with eng().begin() as c:
            if parsed is None:
                # Denetlenemedi: önceki başarılı sonuç korunur, yalnız hata ve zaman yazılır.
                old = c.execute(sa.select(INSPECT.c.url).where(INSPECT.c.tenant_id == tenant,
                                                               INSPECT.c.url == row["url"])).first()
                if old:
                    c.execute(INSPECT.update().where(INSPECT.c.tenant_id == tenant, INSPECT.c.url == row["url"])
                              .values(error=row["error"], inspected_at=at))
                else:
                    c.execute(INSPECT.insert().values(**row))
            else:
                c.execute(INSPECT.delete().where(INSPECT.c.tenant_id == tenant, INSPECT.c.url == row["url"]))
                c.execute(INSPECT.insert().values(**row))
            c.execute(INSPECT_HIST.insert().values(
                id=uuid.uuid4().hex, tenant_id=tenant, url=row["url"], status=row["status"], verdict=row["verdict"],
                coverage=row["coverage"], last_crawl=row["last_crawl"], canonical_mismatch=row["canonical_mismatch"],
                crawled_as=row["crawled_as"], error=row["error"], inspected_at=at))

    def run_inspect(limit: Optional[int], budget: float, user: str) -> None:
        if not ilock.acquire(blocking=False):
            return
        try:
            istate.update(running=True, startedAt=iso(now()), finishedAt=None, done=0, failed=0, error=None,
                          stoppedBy=None, queue=None)
            day = istanbul_day()
            q = quota_view()
            n = q["remaining"] if limit is None else min(q["remaining"], max(0, int(limit)))
            if n <= 0:
                istate.update(stoppedBy="quota" if q["stopped"] else "limit")
                return
            items = queue()[:n]  # günlük kota: kalan ertesi güne (sıra kaldığı yerden sürer)
            istate["queue"] = len(items)
            deadline = time.monotonic() + budget
            gsite = gsc_site()
            last = 0.0
            net_fail = 0
            for t in items:
                if time.monotonic() > deadline:
                    istate["stoppedBy"] = "budget"
                    break
                if istanbul_day() != day:
                    istate["stoppedBy"] = "day"
                    break
                wait = MIN_INTERVAL - (time.monotonic() - last)
                if wait > 0:
                    time.sleep(wait)
                last = time.monotonic()
                try:
                    body = inspect_url(t["url"], gsite)
                except InspectError as e:
                    if e.kind == "permission":
                        istate.update(error=str(e), stoppedBy="permission")
                        put_state("inspect", {"permissionError": str(e), "at": iso(now())})
                        break
                    if e.kind == "quota":
                        bump(day, 0, stopped="quota", note=str(e))
                        istate.update(error=str(e), stoppedBy="quota")
                        break
                    if e.kind == "bad":
                        bump(day)
                        net_fail = 0
                    else:
                        net_fail += 1
                        if net_fail >= NET_FAIL_STOP:
                            istate.update(error=str(e), stoppedBy="network")
                            break
                    store(t, None, str(e))
                    istate["failed"] += 1
                    continue
                net_fail = 0
                bump(day)
                store(t, parse_inspection(body, t["url"]), None)
                istate["done"] += 1
            if istate["done"] and istate["stoppedBy"] != "permission":
                put_state("inspect", {"permissionError": None, "at": iso(now()), "by": user})
        except Exception as e:  # noqa: BLE001 — tur düşerse ekranda görünsün
            log.exception("crawlbot inspect failed")
            istate["error"] = f"Denetim turu yarıda kaldı: {type(e).__name__}"
        finally:
            istate.update(running=False, finishedAt=iso(now()))
            ilock.release()

    def load_rows() -> list[dict[str, Any]]:
        with eng().connect() as c:
            rows = c.execute(sa.select(INSPECT).where(INSPECT.c.tenant_id == seo.tenant())).mappings().all()
        out = []
        for r in rows:
            d = dict(r)
            d["rich"] = loads(d.pop("rich_json"), None)
            d["data"] = loads(d.pop("data_json"), None)
            if d.get("last_crawl") is not None and d["last_crawl"].tzinfo is None:
                d["last_crawl"] = d["last_crawl"].replace(tzinfo=timezone.utc)
            out.append(d)
        return out

    # ---------------------------------------------------------------- botlar
    def fetch_day(token: str, zone: str, day: str, hosts: list[str], verified: Optional[bool]) -> tuple[dict[str, Any], bool, Optional[str], bool]:
        """Döner: (bot özetleri, doğrulanmış alan kullanıldı mı, yol sorgusu hatası, kısmi mi)."""
        rows: list[dict[str, Any]] = []
        used_verified = False
        if verified is not False:
            try:
                rows = cf_call(token, zone, ["userAgent", "edgeResponseStatus", "verifiedBotCategory"], day, hosts)
                used_verified = True
            except CfError as e:
                if e.kind != "plan":
                    raise
        if not used_verified:
            rows = cf_call(token, zone, ["userAgent", "edgeResponseStatus"], day, hosts)
        path_error = None
        try:
            path_rows = cf_call(token, zone, ["userAgent", "clientRequestPath"], day, hosts)
        except CfError as e:
            if e.kind in ("auth", "range"):
                raise
            path_rows, path_error = [], str(e)
        return aggregate_bots(rows, path_rows, used_verified), used_verified, path_error, len(rows) >= CF_ROW_LIMIT

    def run_bots() -> None:
        token, zone = cf_creds()
        if not token or not zone or not block.acquire(blocking=False):
            return
        try:
            bstate.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)
            tenant = seo.tenant()
            with eng().connect() as c:
                have = {r[0] for r in c.execute(sa.select(BOTSTATS.c.day).where(BOTSTATS.c.tenant_id == tenant)).all()}
            prev = get_state("bots")
            info: dict[str, Any] = {"authError": None, "planErrors": {}, "partial": prev.get("partial") or [],
                                    "verified": prev.get("verified"), "oldestAvailable": None, "fetched": []}
            today = datetime.now(timezone.utc).date()
            hosts = hosts_of(site())
            verified: Optional[bool] = None
            for back in range(1, BOT_BACKFILL_DAYS + 1):
                day = (today - timedelta(days=back)).isoformat()
                if day in have and back > BOT_REFRESH_DAYS:
                    continue
                try:
                    per_bot, used_verified, path_err, partial = fetch_day(token, zone, day, hosts, verified)
                except CfError as e:
                    if e.kind == "auth":
                        info["authError"] = str(e)
                        break
                    if e.kind == "range":
                        info["oldestAvailable"] = (today - timedelta(days=back - 1)).isoformat()
                        info["planErrors"]["gecmis"] = str(e)
                        break
                    info["planErrors"]["istekler" if e.kind == "plan" else "ag"] = str(e)
                    break
                verified = used_verified
                info["verified"] = used_verified
                if path_err:
                    info["planErrors"]["yollar"] = path_err
                info["partial"] = sorted((set(info["partial"]) - {day}) | ({day} if partial else set()))
                at = now()
                with eng().begin() as c:
                    c.execute(BOTSTATS.delete().where(BOTSTATS.c.tenant_id == tenant, BOTSTATS.c.day == day))
                    # Boş gün de işaretlenir (bot "_none"): tekrar tekrar sorulmasın.
                    values = [dict(tenant_id=tenant, day=day, bot=b, requests=a["requests"], verified=a["verified"],
                                   status_json=dumps(a["status"]), top_paths_json=dumps(a["topPaths"]), saved_at=at)
                              for b, a in per_bot.items()] or [
                        dict(tenant_id=tenant, day=day, bot="_none", requests=0, verified=None, status_json="{}",
                             top_paths_json="[]", saved_at=at)]
                    c.execute(BOTSTATS.insert(), values)
                info["fetched"].append(day)
            put_state("bots", info)
            bstate["error"] = info["authError"]
        except Exception as e:  # noqa: BLE001
            log.exception("crawlbot bots failed")
            bstate["error"] = f"Bot istatistiği okunamadı: {type(e).__name__}"
        finally:
            bstate.update(running=False, finishedAt=iso(now()))
            block.release()

    def bot_rows(days: int) -> list[dict[str, Any]]:
        since = (datetime.now(timezone.utc).date() - timedelta(days=max(1, days))).isoformat()
        with eng().connect() as c:
            rows = c.execute(sa.select(BOTSTATS).where(BOTSTATS.c.tenant_id == seo.tenant(), BOTSTATS.c.day >= since)
                             .order_by(BOTSTATS.c.day)).mappings().all()
        return [dict(r) for r in rows]

    def bots_view(days: int) -> dict[str, Any]:
        rows = bot_rows(days)
        day_list = sorted({r["day"] for r in rows})
        per: dict[str, dict[str, Any]] = {}
        status_total: dict[str, int] = {}
        paths_total: dict[str, int] = {}
        series: dict[str, dict[str, Any]] = {d: {"day": d} for d in day_list}
        for r in rows:
            b = r["bot"]
            if b == "_none":
                continue
            label, group = BOT_LABEL.get(b, (b, "diğer"))
            a = per.setdefault(b, {"bot": b, "label": label, "group": group, "requests": 0, "verified": None,
                                   "status": {}, "paths": {}})
            a["requests"] += r["requests"]
            if r["verified"] is not None:
                a["verified"] = (a["verified"] or 0) + r["verified"]
            for code, n in loads(r["status_json"], {}).items():
                a["status"][code] = a["status"].get(code, 0) + n
                k = status_class(code)
                status_total[k] = status_total.get(k, 0) + n
            for p in loads(r["top_paths_json"], []):
                a["paths"][p["path"]] = a["paths"].get(p["path"], 0) + p["count"]
                paths_total[p["path"]] = paths_total.get(p["path"], 0) + p["count"]
            series[r["day"]][b] = series[r["day"]].get(b, 0) + r["requests"]
        bots = []
        for a in sorted(per.values(), key=lambda x: -x["requests"]):
            paths = a.pop("paths")
            classes: dict[str, int] = {}
            for code, n in a["status"].items():
                classes[status_class(code)] = classes.get(status_class(code), 0) + n
            bots.append({**a, "statusClass": classes,
                         "topPaths": [{"path": k, "count": v} for k, v in sorted(paths.items(), key=lambda kv: -kv[1])[:TOP_PATHS]]})
        return {"days": day_list, "series": list(series.values()), "bots": bots, "statusClass": status_total,
                "topPaths": [{"path": k, "count": v} for k, v in sorted(paths_total.items(), key=lambda kv: -kv[1])[:TOP_PATHS]],
                "topPathsLimit": TOP_PATHS}

    # ---------------------------------------------------------------- uçlar
    @app.get("/api/v1/seo-geo/crawlbot")
    def crawlbot_summary(request: Request) -> dict[str, Any]:
        ctx.gate(request)
        rows = load_rows()
        prods = product_info()
        summary = summarize(rows, prods)
        summary["productsActive"] = sum(1 for p in prods.values() if p["active"] and p["url"])
        last = max((r["inspected_at"] for r in rows), default=None)
        st = get_state("inspect")
        token, zone = cf_creds()
        bst = get_state("bots")
        week = bots_view(14)
        return {
            "inspect": {"configured": inspect_configured(), "site": gsc_site() or None, "serviceAccount": sa_email(),
                        "permissionError": st.get("permissionError"), "quota": quota_view(),
                        "run": dict(istate), "lastInspectedAt": iso(last), "recentDays": RECENT_DAYS,
                        "staleDays": STALE_CRAWL_DAYS, **summary},
            "bots": {"configured": bool(token and zone), "run": dict(bstate), "authError": bst.get("authError"),
                     "planErrors": bst.get("planErrors") or {}, "verified": bst.get("verified"),
                     "partial": bst.get("partial") or [], "lastFetch": bst.get("savedAt"),
                     "requests14": sum(b["requests"] for b in week["bots"]),
                     "byGroup": {g: sum(b["requests"] for b in week["bots"] if b["group"] == g)
                                 for g in {b["group"] for b in week["bots"]}},
                     "googlebot14": sum(b["requests"] for b in week["bots"] if b["bot"].startswith("googlebot"))},
        }

    @app.get("/api/v1/seo-geo/crawlbot/urls")
    def crawlbot_urls(request: Request, filter: str = "all", start: int = 0, limit: int = 50, q: str = "",
                      kind: str = "") -> dict[str, Any]:
        ctx.gate(request)
        if filter not in FILTERS:
            raise _err(400, "Bilinmeyen süzgeç.")
        at = datetime.now(timezone.utc)
        prods = product_info()
        rows = load_rows()
        if kind:
            rows = [r for r in rows if r["kind"] == kind]
        if filter == "not_indexed":
            rows = [r for r in rows if not r.get("error") and r["status"] != "indexed"]
        elif filter == "canonical":
            rows = [r for r in rows if not r.get("error") and r["canonical_mismatch"]]
        elif filter == "stale":
            rows = [r for r in rows if is_stale(r, at)]
        elif filter == "errors":
            rows = [r for r in rows if r.get("error") or r["status"] in ERROR_STATUSES]
        elif filter == "rich":
            rows = [r for r in rows if not r.get("error") and (r.get("rich") or {}).get("issues")]
        needle = q.strip().casefold()
        if needle:
            rows = [r for r in rows if needle in r["url"].casefold()
                    or needle in (prods.get(str(r.get("product_id"))) or {}).get("name", "").casefold()]

        def sales(r: dict[str, Any]) -> float:
            return (prods.get(str(r.get("product_id"))) or {}).get("sales", 0.0)

        if filter == "stale":
            rows.sort(key=lambda r: (-sales(r), r["url"]))
        else:
            rows.sort(key=lambda r: (r["kind"] != "home", r["kind"] != "product", -sales(r), r["url"]))
        start, limit = max(0, start), max(1, limit)
        items = []
        for r in rows[start:start + limit]:
            p = prods.get(str(r.get("product_id"))) or {}
            st = row_status(r)
            label, tone = STATUS_LABEL.get(st, (st, "mid"))
            items.append({"url": r["url"], "kind": r["kind"], "productId": r.get("product_id"), "name": p.get("name"),
                          "sales": int(p.get("sales") or 0), "status": st, "statusLabel": label, "tone": tone,
                          "verdict": r.get("verdict"), "coverage": r.get("coverage"), "indexing": r.get("indexing"),
                          "robots": r.get("robots"), "fetch": r.get("fetch"), "lastCrawl": iso(r.get("last_crawl")),
                          "daysSinceCrawl": days_since(r.get("last_crawl"), at),
                          "googleCanonical": r.get("google_canonical"), "userCanonical": r.get("user_canonical"),
                          "canonicalMismatch": bool(r.get("canonical_mismatch")), "crawledAs": r.get("crawled_as"),
                          "rich": r.get("rich"), "data": r.get("data"), "error": r.get("error"),
                          "inspectedAt": iso(r.get("inspected_at"))})
        return {"total": len(rows), "start": start, "items": items}

    @app.get("/api/v1/seo-geo/crawlbot/bots")
    def crawlbot_bots(request: Request, days: int = 14) -> dict[str, Any]:
        ctx.gate(request)
        token, zone = cf_creds()
        st = get_state("bots")
        return {"configured": bool(token and zone), "verified": st.get("verified"), "authError": st.get("authError"),
                "planErrors": st.get("planErrors") or {}, "partial": st.get("partial") or [],
                "oldestAvailable": st.get("oldestAvailable"), "lastFetch": st.get("savedAt"), "run": dict(bstate),
                "labels": {k: {"label": v[0], "group": v[1]} for k, v in BOT_LABEL.items()},
                **bots_view(max(1, days))}

    @app.post("/api/v1/seo-geo/crawlbot/run")
    def crawlbot_run(request: Request, limit: Optional[int] = None, part: str = "all") -> dict[str, Any]:
        user = ctx.gate(request)
        if part not in ("all", "inspect", "bots"):
            raise _err(400, "Bilinmeyen bölüm.")
        out: dict[str, Any] = {}
        if part in ("all", "inspect"):
            if not inspect_configured():
                out["inspect"] = "Search Console mülkü ya da servis hesabı tanımlı değil."
            elif istate["running"]:
                out["inspect"] = "Denetim zaten sürüyor."
            else:
                q = quota_view()
                if q["remaining"] <= 0:
                    out["inspect"] = "Bugünkü denetim kotası doldu; yarın sürer."
                else:
                    n = q["remaining"] if limit is None else min(q["remaining"], max(1, int(limit)))
                    threading.Thread(target=run_inspect, args=(n, RUN_BUDGET_SEC, user), name="seo-crawlbot-inspect",
                                     daemon=True).start()
                    out["inspect"] = f"başladı ({n} adrese kadar)"
        if part in ("all", "bots"):
            token, zone = cf_creds()
            if not (token and zone):
                out["bots"] = "Site ağ geçidi anahtarı ya da bölge kimliği girilmemiş."
            elif bstate["running"]:
                out["bots"] = "Okuma zaten sürüyor."
            else:
                threading.Thread(target=run_bots, name="seo-crawlbot-bots", daemon=True).start()
                out["bots"] = "başladı"
        seo.audit(user, "run", "crawlbot", "Google taraması okuması", out)
        return out

    # ---------------------------------------------------------------- gece
    def nightly_inspect() -> None:
        if inspect_configured() and not istate["running"]:
            threading.Thread(target=run_inspect, args=(None, RUN_BUDGET_SEC, "zamanlayıcı"),
                             name="seo-crawlbot-inspect", daemon=True).start()

    def nightly_bots() -> None:
        token, zone = cf_creds()
        if token and zone and not bstate["running"]:
            threading.Thread(target=run_bots, name="seo-crawlbot-bots", daemon=True).start()

    seo.nightly.append(("crawlbot_inspect", nightly_inspect))
    seo.nightly.append(("crawlbot_bots", nightly_bots))
