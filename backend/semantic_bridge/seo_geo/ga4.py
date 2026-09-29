"""Aramadan satışa: Google Analytics organik oturum → sepete ekleme → satın alma → ciro, sayfa (giriş sayfası) bazında,
Search Console tıklamasıyla aynı satırda.

Kaynak: Analytics Data API v1beta `POST properties/{mülk}:runReport` (2026-09-29 mülk 347043165'te canlı doğrulandı):
  boyutlar  sessionDefaultChannelGroup, landingPage, date
  ölçüler   sessions, engagedSessions, addToCarts, ecommercePurchases, purchaseRevenue
  organik   dimensionFilter sessionDefaultChannelGroup = "Organic Search"
Sayfalama: `limit` 100000 + `offset`, cevaptaki `rowCount`'a kadar — sessiz tavan yok.

Okunanlar (her okumada hepsi yeniden yazılır):
  - organik giriş sayfası × 5 ölçü: son 28 gün (dün dahil) ve ondan önceki 28 gün → `semantic_seo_ga4_pages`
  - kanal × 5 ölçü: iki dönem → `semantic_seo_ga4_channels` (organiğin toplamdaki payı buradan)
  - organik günlük seri, son 90 gün → `semantic_seo_ga4_daily`
  - Search Console sayfa tıklaması/gösterimi/sırası, aynı uzunlukta iki dönem (kesin veri 3 gün geç geldiği için
    pencere 3 gün geridedir) → sayfa satırına yol üzerinden eklenir.
Yol: tam adres ya da göreli yol → şema/alan/sorgu dizgisi/parça atılır, çözülür, küçük harf, baştaki/sondaki «/» yok
(`sunset.path_of` ile aynı anahtar; kök ""). `(not set)` giriş sayfası ayrı satırdır («Giriş sayfası belirlenemeyen»),
sayfalara dağıtılmaz. Yol T-soft ürününe (SeoLink) eşlenir; eşlenmeyen yol T-soft yazar/kategori/yayınevi sayfasıysa
«kategori», değilse «diğer» (/, /sepet, /arama …).

Bayraklar (eşik veriden, sabit sayı yok):
  satissiz      ürün sayfası, organik oturumu ürün sayfalarının üst çeyreğinde (Q3) VE beklenen satışı en az
                `EXPECTED_SALES` (oturum × ürün sayfalarının organik dönüşüm oranı), ama hiç satış yok. Beklenen 3 satışta
                hiç satış olmaması Poisson'a göre ~%5 olasılıktır: gürültü değil.
  dusen_oturum  önceki dönem oturumu üst çeyrekte ve bu dönem, site genelindeki organik değişime göre beklenenin
                `DROP_RATIO` katının altında ve fark gürültüden (2√beklenen) büyük.
  dusen_ciro    önceki dönemde en az `EXPECTED_SALES` satış, satış adedi aynı testle sert düşmüş.

Etki ölçümü: onaylı önerinin ölçülen önce/sonra pencerelerinde (impact.py) aynı sayfanın organik oturum/satış/ciro
değeri `semantic_seo_ga4_impact`'e yazılır; değişiklik etkisi ekranında Search Console farkının yanında durur.

Günde bir okunur: gece işi, süreç içi döngü ve ekran açıldığında son okuma 24 saatten eskiyse arka planda; «Şimdi oku».
`GA4_PROPERTY_ID` boşsa hiçbir şey yapılmaz. Google'a yalnız okuma isteği gider; hiçbir sisteme yazılmaz.
"""
from __future__ import annotations

import csv
import io
import logging
import math
import re
import threading
import time
from datetime import date, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from urllib.parse import unquote, urlsplit

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .merchant import safe
from .store import LINKS, PRODUCTS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

API = "https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport"
#: Google'ın izin verdiği en büyük sayfa; sayfa sayısında tavan yok (rowCount'a kadar).
PAGE_LIMIT = 100000
REFRESH_HOURS = 24
WINDOW_DAYS = 28
DAILY_DAYS = 90
GSC_LAG = 3
ORGANIC = "Organic Search"
NOT_SET = "(not set)"
METRICS = ("sessions", "engagedSessions", "addToCarts", "ecommercePurchases", "purchaseRevenue")
KEYS = ("sessions", "engaged", "carts", "purchases", "revenue")
#: Beklenen satış bu kadarken hiç satış yoksa (Poisson ~%5) sayfa «satışsız yüksek trafik» sayılır.
EXPECTED_SALES = 3
#: Site genelindeki değişime göre beklenenin bu katının altı «sert düşüş».
DROP_RATIO = 0.6
KINDS = {"urun": "Ürün", "kategori": "Kategori / yazar / yayınevi", "diger": "Diğer", "belirsiz": "Giriş sayfası belirlenemeyen"}
FLAGS = {"satissiz": "Trafik yüksek, satış yok", "dusen_oturum": "Organik ziyaret sert düştü",
         "dusen_ciro": "Organik satış sert düştü"}
SORTS = ("ciro", "oturum", "donusum", "tiklama", "sepet")

PAGES = sa.Table(
    "semantic_seo_ga4_pages", _md,  # organik giriş sayfası: bu ve önceki 28 gün + Search Console
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("path", sa.String(800), primary_key=True),       # yol anahtarı ("" = anasayfa, "(not set)")
    sa.Column("landing", sa.String(800)),                      # Analytics'teki ilk görülen yazım
    sa.Column("kind", sa.String(12), nullable=False, index=True),
    sa.Column("product_id", sa.String(40), index=True),
    sa.Column("title", sa.String(500)),
    *[sa.Column(k, sa.Float, nullable=False, default=0) for k in KEYS],
    *[sa.Column("p_" + k, sa.Float, nullable=False, default=0) for k in KEYS],
    sa.Column("clicks", sa.Float), sa.Column("impressions", sa.Float), sa.Column("position", sa.Float),
    sa.Column("p_clicks", sa.Float), sa.Column("p_impressions", sa.Float), sa.Column("p_position", sa.Float),
    sa.Column("conv", sa.Float),                               # satış ÷ oturum (bu dönem)
    sa.Column("flags", sa.String(120), nullable=False, default=""),  # ",satissiz,dusen_oturum,"
    sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
)
CHANNELS = sa.Table(
    "semantic_seo_ga4_channels", _md,  # kanal × iki dönem
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("channel", sa.String(120), primary_key=True),
    *[sa.Column(k, sa.Float, nullable=False, default=0) for k in KEYS],
    *[sa.Column("p_" + k, sa.Float, nullable=False, default=0) for k in KEYS],
    sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
)
DAILY = sa.Table(
    "semantic_seo_ga4_daily", _md,  # organik günlük seri
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("day", sa.String(10), primary_key=True),
    *[sa.Column(k, sa.Float, nullable=False, default=0) for k in KEYS],
)
SNAP = sa.Table(
    "semantic_seo_ga4", _md,  # son okumanın özeti ve (varsa) hatası
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("error", sa.String(500)),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
IMPACT = sa.Table(
    "semantic_seo_ga4_impact", _md,  # onaylı önerinin sayfası: önce/sonra organik oturum, satış, ciro
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("proposal_id", sa.String(32), primary_key=True),
    sa.Column("before_json", sa.Text),
    sa.Column("after_json", sa.Text),
    sa.Column("error", sa.String(500)),
    sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
)
#: Kurulmuş motorlar: motorun kendisi tutulur (kimlik numarası başka motora geçmesin).
_ready: dict[int, sa.engine.Engine] = {}


def ensure(eng: sa.engine.Engine) -> None:
    if _ready.get(id(eng)) is eng:
        return
    for t in (PAGES, CHANNELS, DAILY, SNAP, IMPACT):
        t.create(eng, checkfirst=True)
    _ready[id(eng)] = eng


# ------------------------------------------------------------------------------------------------ saf işlevler
def property_id(raw: Optional[str]) -> str:
    return (raw or "").strip().removeprefix("properties/").strip("/")


def norm_path(url: Any) -> str:
    """Tam adres ya da yol → anahtar: şema, alan, sorgu dizgisi, parça atılır; çözülür, küçük harf, kenar «/» yok."""
    s = str(url or "").strip()
    if s == NOT_SET or not s:
        return NOT_SET if s == NOT_SET else ""
    if re.match(r"^[a-z][a-z0-9+.\-]*://", s, re.I) or s.startswith("//"):
        s = urlsplit(s if "://" in s else "http:" + s).path
    s = s.split("#", 1)[0].split("?", 1)[0]
    return unquote(s).strip().strip("/").lower()[:800]


def display_path(key: str) -> str:
    return key if key == NOT_SET else "/" + key


def windows(today: date) -> dict[str, list[str]]:
    """Analytics: son 28 gün (dün dahil) ve önceki 28 gün, günlük seri 90 gün. Search Console aynı uzunlukta, 3 gün geride."""
    d = lambda x: x.isoformat()  # noqa: E731
    y = today - timedelta(days=1)
    g = today - timedelta(days=GSC_LAG)
    return {"cur": [d(y - timedelta(days=WINDOW_DAYS - 1)), d(y)],
            "prev": [d(y - timedelta(days=2 * WINDOW_DAYS - 1)), d(y - timedelta(days=WINDOW_DAYS))],
            "daily": [d(y - timedelta(days=DAILY_DAYS - 1)), d(y)],
            "gscCur": [d(g - timedelta(days=WINDOW_DAYS - 1)), d(g)],
            "gscPrev": [d(g - timedelta(days=2 * WINDOW_DAYS - 1)), d(g - timedelta(days=WINDOW_DAYS))]}


def organic_filter() -> dict[str, Any]:
    return {"filter": {"fieldName": "sessionDefaultChannelGroup", "stringFilter": {"value": ORGANIC}}}


def report_body(start: str, end: str, dims: list[str], organic: bool = True,
                extra_filter: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    body: dict[str, Any] = {"dateRanges": [{"startDate": start, "endDate": end}],
                            "dimensions": [{"name": d} for d in dims], "metrics": [{"name": m} for m in METRICS],
                            "keepEmptyRows": False}
    filters = ([organic_filter()] if organic else []) + ([extra_filter] if extra_filter else [])
    if len(filters) == 1:
        body["dimensionFilter"] = filters[0]
    elif filters:
        body["dimensionFilter"] = {"andGroup": {"expressions": filters}}
    return body


def _float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_rows(resp: dict[str, Any]) -> list[dict[str, Any]]:
    """runReport satırları → [{"dims": [...], "m": {sessions, engaged, carts, purchases, revenue}}]."""
    out = []
    for r in (resp or {}).get("rows") or []:
        dims = [str(x.get("value") or "") for x in r.get("dimensionValues") or []]
        vals = [_float(x.get("value")) for x in r.get("metricValues") or []]
        vals += [0.0] * (len(KEYS) - len(vals))
        out.append({"dims": dims, "m": dict(zip(KEYS, vals))})
    return out


def run_report(prop: str, body: dict[str, Any], post: Optional[Callable[[str, dict[str, Any]], dict[str, Any]]] = None
               ) -> list[dict[str, Any]]:
    """Bütün satırlar: `limit` + `offset`, `rowCount`'a kadar. `post(url, gövde) → dict` testte değiştirilir."""
    if post is None:
        from . import connections

        def post(url: str, b: dict[str, Any]) -> dict[str, Any]:
            return connections._google("POST", url, b)

    url = API.format(prop=prop)
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        resp = post(url, {**body, "limit": PAGE_LIMIT, "offset": offset}) or {}
        rows = parse_rows(resp)
        out.extend(rows)
        total = int(_float(resp.get("rowCount")))
        offset += len(rows)
        if not rows:
            if offset < total:
                raise RuntimeError("Google Analytics beklenen satırların hepsini vermedi; okuma yarıda kesildi.")
            return out
        if offset >= total:
            return out


def zero() -> dict[str, float]:
    return {k: 0.0 for k in KEYS}


def add(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    return {k: a.get(k, 0.0) + b.get(k, 0.0) for k in KEYS}


def pct(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or not prev:
        return None
    return (cur - prev) / prev * 100


def quantile(values: list[float], q: float) -> float:
    """Doğrusal aradeğerli yüzdelik (boş liste 0)."""
    v = sorted(values)
    if not v:
        return 0.0
    pos = (len(v) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def sharp_drop(prev: float, cur: float, site_ratio: float) -> bool:
    """Site genelindeki değişim hesaba katılarak beklenen değerin DROP_RATIO katının altı ve fark gürültüden büyük."""
    if prev <= 0:
        return False
    expected = prev * (site_ratio if site_ratio > 0 else 1.0)
    return cur <= expected * DROP_RATIO and (expected - cur) >= 2 * math.sqrt(expected)


def fetch(prop: str, win: dict[str, list[str]], post=None) -> dict[str, list[dict[str, Any]]]:
    return {
        "pagesCur": run_report(prop, report_body(*win["cur"], ["landingPage"]), post),
        "pagesPrev": run_report(prop, report_body(*win["prev"], ["landingPage"]), post),
        "channelsCur": run_report(prop, report_body(*win["cur"], ["sessionDefaultChannelGroup"], organic=False), post),
        "channelsPrev": run_report(prop, report_body(*win["prev"], ["sessionDefaultChannelGroup"], organic=False), post),
        "daily": run_report(prop, report_body(*win["daily"], ["date"]), post),
    }


def fetch_gsc(win: dict[str, list[str]], query: Optional[Callable[[str, str, list[str]], list[dict[str, Any]]]] = None
              ) -> dict[str, Any]:
    """Search Console sayfa satırları, iki dönem. Bağlı değilse boş ve nedeni."""
    if query is None:
        from . import connections

        if not connections.service_account_email() or not connections._conf("GSC_SITE"):
            return {"cur": None, "prev": None, "error": "Search Console bağlı değil."}
        query = connections.gsc_all
    try:
        return {"cur": query(*win["gscCur"], ["page"]), "prev": query(*win["gscPrev"], ["page"]), "error": None}
    except Exception as e:  # noqa: BLE001 — Search Console düşerse Analytics verisi yine yazılır
        return {"cur": None, "prev": None, "error": safe(e)}


def gsc_by_key(rows: Optional[list[dict[str, Any]]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for r in rows or []:
        keys = r.get("keys") or []
        if not keys:
            continue
        k = norm_path(keys[0])
        g = out.setdefault(k, {"clicks": 0.0, "impressions": 0.0, "_pos": 0.0})
        imp = _float(r.get("impressions"))
        g["clicks"] += _float(r.get("clicks"))
        g["impressions"] += imp
        g["_pos"] += _float(r.get("position")) * imp
    for g in out.values():
        g["position"] = round(g.pop("_pos") / g["impressions"], 2) if g["impressions"] else None
    return out


def classify(key: str, products: dict[str, tuple[str, str]], links: dict[str, tuple[str, str]]) -> tuple[str, Optional[str], Optional[str]]:
    """(tür, ürün, başlık)."""
    if key == NOT_SET:
        return "belirsiz", None, "Giriş sayfası belirlenemeyen oturumlar"
    if key in products:
        pid, name = products[key]
        return "urun", pid, name
    if key in links:
        return "kategori", None, links[key][1]
    return "diger", None, ("Anasayfa" if key == "" else None)


def thresholds(pages: list[dict[str, Any]], organic_cur: dict[str, float], organic_prev: dict[str, float],
               gsc_cur_total: Optional[float], gsc_prev_total: Optional[float]) -> dict[str, Any]:
    prod = [p for p in pages if p["kind"] == "urun"]
    ps = sum(p["sessions"] for p in prod)
    conv = (sum(p["purchases"] for p in prod) / ps) if ps else None
    if not conv:
        conv = (organic_cur["purchases"] / organic_cur["sessions"]) if organic_cur["sessions"] else None
    carts = sum(p["carts"] for p in prod)
    cart_rate = carts / ps if ps else None
    buys = sum(p["purchases"] for p in prod)
    per_cart = buys / carts if carts else None
    rev = sum(p["revenue"] for p in prod)
    aov = rev / buys if buys else ((organic_cur["revenue"] / organic_cur["purchases"]) if organic_cur["purchases"] else None)
    q3 = quantile([p["sessions"] for p in prod if p["sessions"] > 0], 0.75)
    need = math.ceil(EXPECTED_SALES / conv) if conv else 0
    known = [p for p in pages if p["kind"] != "belirsiz"]
    q3_prev = quantile([p["p_sessions"] for p in known if p["p_sessions"] > 0], 0.75)
    ratio = lambda a, b: (a / b) if a and b else 1.0  # noqa: E731
    return {"q3": round(q3, 2), "highTraffic": max(q3, float(need)), "expectedSales": EXPECTED_SALES,
            "conv": conv, "cartRate": cart_rate, "purchasePerCart": per_cart, "aov": aov, "q3Prev": round(q3_prev, 2),
            "sessionRatio": ratio(organic_cur["sessions"], organic_prev["sessions"]),
            "purchaseRatio": ratio(organic_cur["purchases"], organic_prev["purchases"]),
            "revenueRatio": ratio(organic_cur["revenue"], organic_prev["revenue"]),
            "clickRatio": ratio(gsc_cur_total or 0, gsc_prev_total or 0), "dropRatio": DROP_RATIO}


def flags_of(p: dict[str, Any], th: dict[str, Any]) -> list[str]:
    out = []
    if p["kind"] == "belirsiz":
        return out
    if p["kind"] == "urun" and p["sessions"] > 0 and p["sessions"] >= th["highTraffic"] and p["purchases"] <= 0:
        out.append("satissiz")
    if p["p_sessions"] >= th["q3Prev"] and p["p_sessions"] > 0 and sharp_drop(p["p_sessions"], p["sessions"], th["sessionRatio"]):
        out.append("dusen_oturum")
    if p["p_purchases"] >= EXPECTED_SALES and sharp_drop(p["p_purchases"], p["purchases"], th["purchaseRatio"]):
        out.append("dusen_ciro")
    return out


def build(raw: dict[str, list[dict[str, Any]]], gsc: dict[str, Any], products: dict[str, tuple[str, str]],
          links: dict[str, tuple[str, str]]) -> dict[str, Any]:
    """Okunan ham satırlar → sayfa satırları, kanal satırları, günlük seri, özet. Saf işlev."""
    pages: dict[str, dict[str, Any]] = {}

    def rec(key: str, landing: Optional[str]) -> dict[str, Any]:
        r = pages.get(key)
        if r is None:
            kind, pid, title = classify(key, products, links)
            r = pages[key] = {"path": key, "landing": landing, "kind": kind, "product_id": pid, "title": title,
                              **zero(), **{"p_" + k: 0.0 for k in KEYS}, "clicks": None, "impressions": None,
                              "position": None, "p_clicks": None, "p_impressions": None, "p_position": None}
        elif not r["landing"] and landing:
            r["landing"] = landing
        return r

    for period, prefix in (("pagesCur", ""), ("pagesPrev", "p_")):
        for row in raw.get(period) or []:
            landing = row["dims"][0] if row["dims"] else ""
            r = rec(norm_path(landing if landing else NOT_SET), landing or NOT_SET)
            for k in KEYS:
                r[prefix + k] += row["m"][k]
    gcur, gprev = gsc_by_key(gsc.get("cur")), gsc_by_key(gsc.get("prev"))
    for g, prefix in ((gcur, ""), (gprev, "p_")):
        for key, v in g.items():
            if key not in pages and not v["clicks"]:
                continue  # yalnız gösterim alan, tıklamasız adres sayfa listesine girmez (huni toplamında sayılır)
            r = rec(key, None)
            r[prefix + "clicks"] = v["clicks"]
            r[prefix + "impressions"] = v["impressions"]
            r[prefix + "position"] = v["position"]

    def chan(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        out: dict[str, dict[str, float]] = {}
        for row in rows or []:
            name = (row["dims"][0] if row["dims"] else "") or NOT_SET
            out[name] = add(out.get(name, zero()), row["m"])
        return out

    ccur, cprev = chan(raw.get("channelsCur")), chan(raw.get("channelsPrev"))
    channels = []
    for name in sorted(set(ccur) | set(cprev), key=lambda n: -ccur.get(n, zero())["sessions"]):
        c, p = ccur.get(name, zero()), cprev.get(name, zero())
        channels.append({"channel": name, **c, **{"p_" + k: p[k] for k in KEYS}})
    all_cur = all_prev = zero()
    for c in ccur.values():
        all_cur = add(all_cur, c)
    for c in cprev.values():
        all_prev = add(all_prev, c)
    org_cur, org_prev = ccur.get(ORGANIC, zero()), cprev.get(ORGANIC, zero())
    daily: dict[str, dict[str, float]] = {}
    for row in raw.get("daily") or []:
        d = row["dims"][0] if row["dims"] else ""
        if len(d) == 8 and d.isdigit():
            d = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        daily[d] = add(daily.get(d, zero()), row["m"])
    rows = list(pages.values())
    gsc_cur_total = sum(v["clicks"] for v in gcur.values()) if gsc.get("cur") is not None else None
    gsc_prev_total = sum(v["clicks"] for v in gprev.values()) if gsc.get("prev") is not None else None
    th = thresholds(rows, org_cur, org_prev, gsc_cur_total, gsc_prev_total)
    counts = {f: 0 for f in FLAGS}
    for r in rows:
        r["conv"] = (r["purchases"] / r["sessions"]) if r["sessions"] else None
        fl = flags_of(r, th)
        r["flags"] = ("," + ",".join(fl) + ",") if fl else ""
        for f in fl:
            counts[f] += 1
    by_kind: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = by_kind.setdefault(r["kind"], {"pages": 0, **zero()})
        k["pages"] += 1
        for m in KEYS:
            k[m] += r[m]
    share = {k: (org_cur[k] / all_cur[k]) if all_cur[k] else None for k in ("sessions", "revenue", "purchases")}
    prev_share = {k: (org_prev[k] / all_prev[k]) if all_prev[k] else None for k in ("sessions", "revenue", "purchases")}
    summary = {
        "organic": {"cur": org_cur, "prev": org_prev,
                    "change": {k: pct(org_cur[k], org_prev[k]) for k in KEYS}},
        "all": {"cur": all_cur, "prev": all_prev},
        "share": share, "prevShare": prev_share,
        "funnel": {"clicks": gsc_cur_total, "prevClicks": gsc_prev_total, **{k: org_cur[k] for k in KEYS}},
        "pages": {"rows": len(rows), "byKind": by_kind,
                  "matched": sum(1 for r in rows if r["product_id"]),
                  "unmatched": sum(1 for r in rows if not r["product_id"] and r["kind"] != "belirsiz"),
                  "notSet": {m: pages[NOT_SET][m] for m in KEYS} if NOT_SET in pages else None},
        "flags": counts, "thresholds": th, "gscError": gsc.get("error"),
    }
    return {"pages": rows, "channels": channels, "daily": [{"day": d, **v} for d, v in sorted(daily.items())],
            "summary": summary}


# ------------------------------------------------------------------------------------------------ veritabanı
def product_index(eng: sa.engine.Engine, tenant: str) -> dict[str, tuple[str, str]]:
    """yol → (ürün, ad). Aynı yolda birden çok ürün varsa satıştaki önce."""
    if not sa.inspect(eng).has_table(PRODUCTS.name):
        return {}
    with eng.connect() as c:
        if eng.dialect.name == "postgresql":
            data = sa.cast(PRODUCTS.c.data_json, sa.JSON)
            rows = [(pid, name, act, a or b or d) for pid, name, act, a, b, d in c.execute(sa.select(
                PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.active, data["SeoLink"].as_string(),
                data["Url"].as_string(), data["ProductUrl"].as_string()).where(PRODUCTS.c.tenant_id == tenant))]
        else:
            rows = []
            for pid, name, act, raw in c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.active,
                                                           PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == tenant)):
                p = loads(raw, {})
                rows.append((pid, name, act, p.get("SeoLink") or p.get("Url") or p.get("ProductUrl")))
    out: dict[str, tuple[str, str]] = {}
    for pid, name, act, link in sorted(rows, key=lambda r: (not r[2], str(r[0]))):
        key = norm_path(link) if link else None
        if key:
            out.setdefault(key, (str(pid), name or str(pid)))
    return out


def link_index(eng: sa.engine.Engine, tenant: str) -> dict[str, tuple[str, str]]:
    from .pages import KINDS as PAGE_KINDS

    if not sa.inspect(eng).has_table(LINKS.name):
        return {}
    with eng.connect() as c:
        rows = c.execute(sa.select(LINKS.c.link, LINKS.c.type, LINKS.c.title).where(
            LINKS.c.tenant_id == tenant, LINKS.c.type.in_(list(PAGE_KINDS)))).all()
    from . import rules

    return {norm_path(l): (t, rules.text_of(title) or l) for l, t, title in rows if norm_path(l)}


def save(eng: sa.engine.Engine, tenant: str, prop: str, built: dict[str, Any], win: dict[str, list[str]], at) -> dict[str, Any]:
    ensure(eng)
    data = {"property": prop, "windows": win, **built["summary"]}
    cols = {c.name for c in PAGES.columns}
    rows = [{**{k: v for k, v in r.items() if k in cols}, "tenant_id": tenant, "read_at": at,
             "title": (r.get("title") or None) and str(r["title"])[:500],
             "landing": (r.get("landing") or None) and str(r["landing"])[:800]} for r in built["pages"]]
    with eng.begin() as c:
        c.execute(PAGES.delete().where(PAGES.c.tenant_id == tenant))
        for i in range(0, len(rows), 1000):
            c.execute(PAGES.insert(), rows[i:i + 1000])
        c.execute(CHANNELS.delete().where(CHANNELS.c.tenant_id == tenant))
        if built["channels"]:
            c.execute(CHANNELS.insert(), [{**ch, "channel": ch["channel"][:120], "tenant_id": tenant, "read_at": at}
                                          for ch in built["channels"]])
        c.execute(DAILY.delete().where(DAILY.c.tenant_id == tenant))
        if built["daily"]:
            c.execute(DAILY.insert(), [{**d, "tenant_id": tenant} for d in built["daily"] if d["day"]])
        c.execute(SNAP.delete().where(SNAP.c.tenant_id == tenant))
        c.execute(SNAP.insert().values(tenant_id=tenant, data_json=dumps(data), error=None, saved_at=at))
    return data


def save_error(eng: sa.engine.Engine, tenant: str, message: str, at) -> None:
    """Okuma hatası son okumanın yanına yazılır; eski veri silinmez."""
    ensure(eng)
    with eng.begin() as c:
        n = c.execute(SNAP.update().where(SNAP.c.tenant_id == tenant).values(error=safe(message))).rowcount
        if not n:
            c.execute(SNAP.insert().values(tenant_id=tenant, data_json=dumps({}), error=safe(message), saved_at=at))


def read_snap(eng: sa.engine.Engine, tenant: str) -> Optional[dict[str, Any]]:
    if not sa.inspect(eng).has_table(SNAP.name):
        return None
    with eng.connect() as c:
        r = c.execute(sa.select(SNAP.c.data_json, SNAP.c.error, SNAP.c.saved_at).where(SNAP.c.tenant_id == tenant)).first()
    if not r:
        return None
    return {**loads(r[0], {}), "error": r[1], "savedAt": iso(r[2]), "_at": r[2]}


def page_view(r: Any) -> dict[str, Any]:
    r = dict(r)
    cur = {k: r[k] for k in KEYS}
    prev = {k: r["p_" + k] for k in KEYS}
    fl = [f for f in (r.get("flags") or "").strip(",").split(",") if f]
    return {"path": display_path(r["path"]), "key": r["path"], "landing": r.get("landing"), "kind": r["kind"],
            "kindLabel": KINDS.get(r["kind"], r["kind"]), "productId": r.get("product_id"), "title": r.get("title"),
            "cur": cur, "prev": prev, "change": {k: pct(cur[k], prev[k]) for k in ("sessions", "purchases", "revenue")},
            "clicks": r.get("clicks"), "impressions": r.get("impressions"), "position": r.get("position"),
            "prevClicks": r.get("p_clicks"), "prevImpressions": r.get("p_impressions"), "prevPosition": r.get("p_position"),
            "conv": r.get("conv"), "cartRate": (r["carts"] / r["sessions"]) if r["sessions"] else None,
            "flags": fl, "flagLabels": [FLAGS[f] for f in fl if f in FLAGS]}


def page_conditions(tenant: str, kind: str = "", flag: str = "", q: str = "") -> list[Any]:
    cond = [PAGES.c.tenant_id == tenant]
    if kind:
        if kind not in KINDS:
            raise HTTPException(422, {"code": "SEO", "message": "Tür urun, kategori, diger ya da belirsiz olmalı."})
        cond.append(PAGES.c.kind == kind)
    if flag == "dusen":
        cond.append(PAGES.c.flags.like("%,dusen_%"))
    elif flag:
        if flag not in FLAGS:
            raise HTTPException(422, {"code": "SEO", "message": "Süzgeç satissiz, dusen, dusen_oturum ya da dusen_ciro olmalı."})
        cond.append(PAGES.c.flags.contains(f",{flag},", autoescape=True))
    if q.strip():
        like = f"%{q.strip().lower()}%"
        cond.append(sa.or_(PAGES.c.path.like(like), sa.func.lower(PAGES.c.title).like(like),
                           PAGES.c.path == norm_path(q), PAGES.c.product_id == q.strip()))
    return cond


def page_order(sort: str) -> list[Any]:
    col = {"ciro": PAGES.c.revenue, "oturum": PAGES.c.sessions, "donusum": PAGES.c.conv, "tiklama": PAGES.c.clicks,
           "sepet": PAGES.c.carts}.get(sort)
    if col is None:
        raise HTTPException(422, {"code": "SEO", "message": "Sıralama ciro, oturum, donusum, tiklama ya da sepet olmalı."})
    return [col.desc().nullslast(), PAGES.c.sessions.desc(), PAGES.c.path]


def product_totals(eng: sa.engine.Engine, tenant: str, pid: str) -> Optional[dict[str, Any]]:
    """Kitap karnesi: ürüne eşlenen bütün giriş yollarının toplamı (eşlenmemişse None)."""
    if not sa.inspect(eng).has_table(PAGES.name):
        return None
    with eng.connect() as c:
        rows = c.execute(sa.select(PAGES).where(PAGES.c.tenant_id == tenant, PAGES.c.product_id == pid)).mappings().all()
    if not rows:
        return None
    cur, prev = zero(), zero()
    for r in rows:
        cur = add(cur, {k: r[k] for k in KEYS})
        prev = add(prev, {k: r["p_" + k] for k in KEYS})
    return {"cur": cur, "prev": prev, "paths": [display_path(r["path"]) for r in rows],
            "flags": sorted({f for r in rows for f in (r["flags"] or "").strip(",").split(",") if f})}


# ------------------------------------------------------------------------------------------------ etki (impact.py)
def page_filter(url_or_path: str) -> dict[str, Any]:
    key = norm_path(url_or_path)
    vals = ["/" + key] + (["/" + key + "/"] if key else [])
    return {"filter": {"fieldName": "landingPage", "inListFilter": {"values": vals, "caseSensitive": False}}}


def page_metrics(prop: str, url: str, start: str, end: str, post=None) -> dict[str, float]:
    tot = zero()
    for row in run_report(prop, report_body(start, end, ["landingPage"], extra_filter=page_filter(url)), post):
        tot = add(tot, row["m"])
    return tot


def measure_impact(eng: sa.engine.Engine, tenant: str, prop: str, post=None, today: Optional[date] = None) -> tuple[int, int]:
    """Search Console ölçümü tamamlanmış (penceresi dolmuş) değişiklikler için aynı pencerelerde organik Analytics
    değerleri. Bir kez ölçülür; hata satırda kalır ve sonraki okumada yeniden denenir."""
    from . import impact as imp

    ensure(eng)
    if not sa.inspect(eng).has_table(imp.IMPACT.name):
        return 0, 0
    today = today or date.today()
    with eng.connect() as c:
        done = {r[0] for r in c.execute(sa.select(IMPACT.c.proposal_id).where(IMPACT.c.tenant_id == tenant,
                                                                              IMPACT.c.error.is_(None)))}
        rows = c.execute(sa.select(imp.IMPACT.c.proposal_id, imp.IMPACT.c.url, imp.IMPACT.c.applied_at).where(
            imp.IMPACT.c.tenant_id == tenant, imp.IMPACT.c.applied_at.isnot(None), imp.IMPACT.c.url.isnot(None),
            imp.IMPACT.c.status.in_(("tamam", "veri_yok")))).all()
    ok = failed = 0
    for pid, url, applied in rows:
        if pid in done:
            continue
        w = imp.windows(applied, today)
        if not w["due"]:
            continue
        try:
            vals = dict(before_json=dumps(page_metrics(prop, url, *w["before"], post)),
                        after_json=dumps(page_metrics(prop, url, *w["after"], post)), error=None, measured_at=now())
            ok += 1
        except Exception as e:  # noqa: BLE001
            vals = dict(before_json=None, after_json=None, error=safe(e), measured_at=now())
            failed += 1
        with eng.begin() as c:
            c.execute(IMPACT.delete().where(IMPACT.c.tenant_id == tenant, IMPACT.c.proposal_id == pid))
            c.execute(IMPACT.insert().values(tenant_id=tenant, proposal_id=pid, **vals))
    return ok, failed


def impact_for(eng: sa.engine.Engine, tenant: str, proposal_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not proposal_ids or not sa.inspect(eng).has_table(IMPACT.name):
        return {}
    with eng.connect() as c:
        rows = c.execute(sa.select(IMPACT).where(IMPACT.c.tenant_id == tenant,
                                                 IMPACT.c.proposal_id.in_(proposal_ids))).mappings().all()
    out = {}
    for r in rows:
        b, a = loads(r["before_json"], None), loads(r["after_json"], None)
        out[r["proposal_id"]] = {"before": b, "after": a, "error": r["error"], "measuredAt": iso(r["measured_at"]),
                                 "delta": {k: pct(a[k], b[k]) for k in ("sessions", "purchases", "revenue")} if a and b else None}
    return out


# ------------------------------------------------------------------------------------------------ uçlar
class PageAsk(BaseModel):
    path: str = Field(..., min_length=0, max_length=2000)


def register(app, ctx) -> None:
    from . import ga4_actions as act

    seo = ctx.seo
    lock = threading.Lock()
    state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None}
    summaries: dict[str, dict[str, Any]] = {}

    def eng() -> sa.engine.Engine:
        e = seo.engine()
        ensure(e)
        return e

    def prop() -> str:
        return property_id(seo.conf("GA4_PROPERTY_ID"))

    def refresh() -> dict[str, Any]:
        p = prop()
        if not p:
            raise RuntimeError("Google Analytics mülk kimliği girilmemiş.")
        e, tenant, at = eng(), seo.tenant(), now()
        win = windows(date.today())
        try:
            raw = fetch(p, win)
        except Exception as ex:  # noqa: BLE001 — hata son okumanın yanına yazılır
            save_error(e, tenant, str(ex), at)
            raise
        built = build(raw, fetch_gsc(win), product_index(e, tenant), link_index(e, tenant))
        data = save(e, tenant, p, built, win, at)
        try:
            measure_impact(e, tenant, p)
        except Exception as ex:  # noqa: BLE001 — etki ölçümü okumayı düşürmez
            log.warning("ga4 etki ölçümü: %s", safe(ex))
        return data

    def kick() -> bool:
        with lock:
            if state["running"]:
                return False
            state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)

        def run() -> None:
            try:
                refresh()
            except Exception as ex:  # noqa: BLE001
                state["error"] = safe(ex)
                log.warning("ga4: %s", safe(ex))
            finally:
                state.update(running=False, finishedAt=iso(now()))

        threading.Thread(target=run, name="seo-ga4", daemon=True).start()
        return True

    def stale(snap: Optional[dict[str, Any]]) -> bool:
        at = snap.get("_at") if snap else None
        if at is None:
            return True
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return now() - at > timedelta(hours=REFRESH_HOURS)

    def loop() -> None:
        time.sleep(240)
        while True:
            try:
                if prop() and stale(read_snap(eng(), seo.tenant())):
                    kick()
            except Exception as ex:  # noqa: BLE001
                log.warning("ga4 döngüsü: %s", safe(ex))
            time.sleep(1800)

    threading.Thread(target=loop, name="seo-ga4-loop", daemon=True).start()

    def snapshot() -> tuple[bool, Optional[dict[str, Any]]]:
        p = prop()
        snap = read_snap(eng(), seo.tenant()) if p else None
        if p and stale(snap):
            kick()
        if snap:
            snap.pop("_at", None)
        return bool(p), snap

    @app.get("/api/v1/seo-geo/ga4")
    def seo_ga4(request: Request) -> dict[str, Any]:
        ctx.gate(request)
        configured, snap = snapshot()
        channels: list[dict[str, Any]] = []
        daily: list[dict[str, Any]] = []
        if configured:
            with eng().connect() as c:
                for r in c.execute(sa.select(CHANNELS).where(CHANNELS.c.tenant_id == seo.tenant())
                                   .order_by(CHANNELS.c.sessions.desc(), CHANNELS.c.channel)).mappings():
                    cur, prev = {k: r[k] for k in KEYS}, {k: r["p_" + k] for k in KEYS}
                    channels.append({"channel": r["channel"], "organic": r["channel"] == ORGANIC, "cur": cur, "prev": prev,
                                     "change": {k: pct(cur[k], prev[k]) for k in ("sessions", "revenue")}})
                daily = [dict(r) for r in c.execute(sa.select(DAILY.c.day, *[DAILY.c[k] for k in KEYS])
                                                    .where(DAILY.c.tenant_id == seo.tenant()).order_by(DAILY.c.day)).mappings()]
        return {"configured": configured, "snapshot": snap, "state": state, "refreshHours": REFRESH_HOURS,
                "channels": channels, "daily": daily, "kinds": KINDS, "flags": FLAGS}

    @app.get("/api/v1/seo-geo/ga4/pages")
    def seo_ga4_pages(request: Request, kind: str = "", flag: str = "", q: str = "", sort: str = "ciro",
                      start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        cond = page_conditions(seo.tenant(), kind, flag, q)
        order = page_order(sort)
        begin = max(0, start)
        e = eng()
        with e.connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(PAGES).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(PAGES).where(*cond).order_by(*order).offset(begin)
                             .limit(max(1, min(limit, 500)))).mappings().all()
        snap = read_snap(e, seo.tenant()) or {}
        items = [page_view(r) for r in rows]
        diag = act.Context.from_seo(seo, snap.get("thresholds") or {})
        diag.preload(items)
        for it in items:
            it["badges"] = [{"code": cd["code"], "label": cd["badge"], "tone": cd["tone"]} for cd in act.cards(it, diag, detail=False)]
        return {"total": total, "start": begin, "items": items, "thresholds": snap.get("thresholds"),
                "savedAt": snap.get("savedAt")}

    def one_page(path: str) -> tuple[dict[str, Any], "act.Context"]:
        key = norm_path(path) if path != NOT_SET else NOT_SET
        with eng().connect() as c:
            r = c.execute(sa.select(PAGES).where(PAGES.c.tenant_id == seo.tenant(), PAGES.c.path == key)).mappings().first()
        if not r:
            raise HTTPException(404, {"code": "SEO", "message": "Bu sayfa son Google Analytics okumasında yok."})
        snap = read_snap(eng(), seo.tenant()) or {}
        item = page_view(r)
        diag = act.Context.from_seo(seo, snap.get("thresholds") or {})
        diag.preload([item])
        return item, diag

    @app.get("/api/v1/seo-geo/ga4/page")
    def seo_ga4_page(request: Request, path: str = "") -> dict[str, Any]:
        ctx.gate(request)
        item, diag = one_page(path)
        item["cards"] = act.cards(item, diag, detail=True)
        item["windows"] = (read_snap(eng(), seo.tenant()) or {}).get("windows")
        return item

    @app.post("/api/v1/seo-geo/ga4/page-summary")
    def seo_ga4_page_summary(body: PageAsk, request: Request) -> dict[str, Any]:
        ctx.gate(request)
        item, diag = one_page(body.path)
        cards = act.cards(item, diag, detail=True)
        facts = act.summary_facts(item, cards)
        key = f"{item['key']}|{hash(facts)}"
        if key in summaries:
            return summaries[key]
        out = act.zeki_summary(seo, facts)
        if out["text"]:
            summaries[key] = out
        return out

    @app.post("/api/v1/seo-geo/ga4/refresh")
    def seo_ga4_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        if not prop():
            raise HTTPException(409, {"code": "SEO", "message": "Google Analytics mülk kimliği girilmemiş (Yönetim → SEO & GEO)."})
        started = kick()
        seo.audit(user, "run", "ga4", "Google Analytics aramadan satışa okuması", {"started": started})
        return {"started": started, "state": state}

    @app.get("/api/v1/seo-geo/ga4/export.csv")
    def seo_ga4_export(request: Request, kind: str = "", flag: str = "", q: str = "", sort: str = "ciro"):
        ctx.gate(request)
        cond = page_conditions(seo.tenant(), kind, flag, q)
        with eng().connect() as c:
            rows = c.execute(sa.select(PAGES).where(*cond).order_by(*page_order(sort))).mappings().all()
        snap = read_snap(eng(), seo.tenant()) or {}
        items = [page_view(r) for r in rows]
        diag = act.Context.from_seo(seo, snap.get("thresholds") or {})
        buf = io.StringIO()
        wr = csv.writer(buf, delimiter=";")
        wr.writerow(["Sayfa", "Tür", "Kitap / başlık", "Google tıklaması", "Organik oturum", "Sepete ekleme", "Satış",
                     "Ciro (₺)", "Dönüşüm %", "Önceki oturum", "Önceki ciro (₺)", "Durum", "Yapılacak iş", "Sorumlu",
                     "Beklenen etki (₺, 28 gün)", "Etki hesabı"])
        for i in range(0, len(items), 400):
            chunk = items[i:i + 400]
            diag.preload(chunk)
            for it in chunk:
                cards = act.cards(it, diag, detail=False)
                top = cards[0] if cards else None
                cur, prev = it["cur"], it["prev"]
                wr.writerow([it["path"], it["kindLabel"], it["title"] or "", _csv_num(it["clicks"]), _csv_num(cur["sessions"]),
                             _csv_num(cur["carts"]), _csv_num(cur["purchases"]), _csv_num(cur["revenue"], 2),
                             _csv_num(it["conv"] * 100, 2) if it["conv"] is not None else "", _csv_num(prev["sessions"]),
                             _csv_num(prev["revenue"], 2), " / ".join(it["flagLabels"]),
                             " | ".join(c["title"] for c in cards), " | ".join(dict.fromkeys(c["ownerLabel"] for c in cards)),
                             _csv_num(top["impact"]["value"], 0) if top and top.get("impact") else "",
                             top["impact"]["formula"] if top and top.get("impact") else ""])
        data = "﻿" + buf.getvalue()
        return StreamingResponse(iter([data]), media_type="text/csv; charset=utf-8",
                                 headers={"Content-Disposition": 'attachment; filename="aramadan-satisa.csv"'})

    def nightly() -> None:
        from . import connections

        if prop() and connections.service_account_email():
            kick()

    seo.nightly.append(("ga4", nightly))


def _csv_num(v: Any, digits: int = 0) -> str:
    if v is None:
        return ""
    return f"{float(v):.{digits}f}".replace(".", ",")
