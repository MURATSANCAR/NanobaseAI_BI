"""Fırsat listesi: Search Console'daki sorgulardan iki tür iş çıkarır.

- **Yakın sıra (`yakin`)**: ortalama sırası 4–15 arasındaki sorgu+sayfa. İlk üçe çıkarsa gelecek ek tıklama sitenin
  KENDİ tıklama oranı eğrisiyle tahmin edilir (sektör eğrisi uydurulmaz).
- **Düşük tıklama (`dusuk_tiklama`)**: çok gösterilip, aynı sıradaki sorguların tipik oranının yarısından az tıklanan
  sorgu+sayfa. Sıra iyi, başlık/meta açıklama çekmiyor demektir; ürün sayfasına bağlanır ki öneri oradan istensin.

Eğri: marka dışı, en az `CURVE_MIN_IMPR` gösterimli satırlar yuvarlanmış sıraya göre gruplanır, her grubun ortanca
tıklama oranı alınır (grupta en az `CURVE_MIN_SAMPLES` satır). Eksik sıra komşulardan doğrusal doldurulur ve eğri
sıra ilerledikçe artmayacak biçimde düzeltilir. Marka sorguları ("timaş") eğriye girmez: oranları olağan dışı yüksektir.

Kaynak: gece (ve ekrandaki düğmeyle) son 28 günün sorgu+sayfa kırılımı okunur ve `semantic_seo_opps`'ta durur.
Henüz yoksa ortak Search Console önbelleğindeki yalnız-sorgu satırları kullanılır (sayfa bilgisi olmadan).
Search Console'a yalnız okuma yapılır; hiçbir yere yazılmaz.
"""
from __future__ import annotations

import logging
import statistics
import threading
from datetime import date, timedelta
from typing import Any, Optional
from urllib.parse import unquote, urlsplit

import sqlalchemy as sa
from fastapi import HTTPException, Request

from . import connections
from .store import PRODUCTS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

OPPS = sa.Table(
    "semantic_seo_opps", _md,  # fırsat hesabının kaynağı: Search Console sorgu+sayfa kırılımı (son hâl)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kind", sa.String(24), primary_key=True),        # query_page
    sa.Column("start_date", sa.String(10), nullable=False),
    sa.Column("end_date", sa.String(10), nullable=False),
    sa.Column("rows_json", sa.Text, nullable=False),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)

#: Eşikler ekranda da gösterilir.
NEAR_MIN, NEAR_MAX = 4.0, 15.0
TARGET_POSITION = 3
CURVE_MIN_IMPR = 50
CURVE_MIN_SAMPLES = 5
CURVE_MAX_BUCKET = 20
LOW_MIN_IMPR = 100
LOW_RATIO = 0.5
DAYS, LAG = 28, 3
KINDS = ("yakin", "dusuk_tiklama")

_ready: set[int] = set()
_ready_lock = threading.Lock()
_cache: dict[str, Any] = {"key": None, "data": None}
_cache_lock = threading.Lock()


def ensure_table(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) not in _ready:
            OPPS.create(engine, checkfirst=True)
            _ready.add(id(engine))


# ------------------------------------------------------------------------------------------------ saf işlevler

def fold(text: str) -> str:
    """Türkçe büyük/küçük harf ve şapka farkını siler: "TİMAŞ", "Timas", "tımaş" → "timas"."""
    t = str(text or "").replace("İ", "i").replace("I", "ı").lower().replace("̇", "")
    return t.translate(str.maketrans("ışğüöçâîû", "isguocaiu"))


def is_brand(query: str) -> bool:
    return "timas" in fold(query)


def path_key(url: Optional[str]) -> Optional[str]:
    """Adres karşılaştırma anahtarı: alan adı, şema, sorgu dizesi ve sondaki "/" atılır; küçük harf."""
    if not url:
        return None
    raw = str(url).strip()
    if "://" not in raw and not raw.startswith("/"):
        raw = "/" + raw
    parts = urlsplit(raw if "://" in raw else "http://x" + raw)
    path = unquote(parts.path or "/").rstrip("/").lower()
    return path or "/"


def bucket(position: float) -> int:
    return max(1, int(float(position) + 0.5))


def _row(r: dict[str, Any]) -> tuple[str, Optional[str], float, float, float]:
    keys = r.get("keys") or []
    q = str(keys[0]) if keys else ""
    page = str(keys[1]) if len(keys) > 1 else None
    return q, page, float(r.get("clicks") or 0), float(r.get("impressions") or 0), float(r.get("position") or 0)


def ctr_curve(rows: list[dict[str, Any]], min_impr: int = CURVE_MIN_IMPR, min_samples: int = CURVE_MIN_SAMPLES,
              max_bucket: int = CURVE_MAX_BUCKET) -> dict[int, dict[str, Any]]:
    """Sıra → {ctr, samples, measured}. `measured` False ise değer komşu sıralardan doldurulmuştur. Veri yoksa {}."""
    groups: dict[int, list[float]] = {}
    for r in rows:
        q, _, clicks, impr, pos = _row(r)
        if impr < min_impr or pos <= 0 or is_brand(q):
            continue
        b = bucket(pos)
        if b > max_bucket:
            continue
        groups.setdefault(b, []).append(clicks / impr)
    known = {b: statistics.median(v) for b, v in groups.items() if len(v) >= min_samples}
    if not known:
        return {}
    pts = sorted(known)
    out: dict[int, dict[str, Any]] = {}
    for b in range(1, max_bucket + 1):
        if b in known:
            val = known[b]
        else:
            lo = max((p for p in pts if p < b), default=None)
            hi = min((p for p in pts if p > b), default=None)
            if lo is not None and hi is not None:
                val = known[lo] + (known[hi] - known[lo]) * (b - lo) / (hi - lo)
            else:
                val = known[lo if lo is not None else hi]
        out[b] = {"ctr": val, "samples": len(groups.get(b, [])), "measured": b in known}
    for b in range(2, max_bucket + 1):  # sıra düştükçe oran artmaz
        out[b]["ctr"] = min(out[b]["ctr"], out[b - 1]["ctr"])
    return out


def expected_ctr(curve: dict[int, dict[str, Any]], position: float) -> Optional[float]:
    if not curve or position <= 0:
        return None
    b = min(bucket(position), max(curve))
    return curve[b]["ctr"]


def classify(rows: list[dict[str, Any]], curve: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Her satır için fırsat türleri ve tahminler. Bir satır iki türde de olabilir; hiçbirine girmeyen atlanır."""
    target = curve.get(TARGET_POSITION, {}).get("ctr") if curve else None
    out: list[dict[str, Any]] = []
    for r in rows:
        q, page, clicks, impr, pos = _row(r)
        if impr <= 0:
            continue
        ctr = clicks / impr
        exp = expected_ctr(curve, pos)
        kinds: list[str] = []
        extra = lost = None
        if NEAR_MIN <= pos <= NEAR_MAX:
            kinds.append("yakin")
            if target is not None:
                extra = max(0.0, impr * target - clicks)
        if exp is not None and impr >= LOW_MIN_IMPR and ctr < LOW_RATIO * exp:
            kinds.append("dusuk_tiklama")
        if exp is not None:
            lost = max(0.0, impr * exp - clicks)
        if not kinds:
            continue
        out.append({"query": q, "page": page, "clicks": int(clicks), "impressions": int(impr), "ctr": ctr,
                    "position": pos, "expectedCtr": exp, "targetCtr": target,
                    "extraClicks": round(extra) if extra is not None else None,
                    "lostClicks": round(lost) if lost is not None else None,
                    "brand": is_brand(q), "kinds": kinds})
    return out


def rank(items: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    chosen = [i for i in items if kind in i["kinds"]]
    if kind == "yakin":
        return sorted(chosen, key=lambda i: (-i["impressions"], i["position"], i["query"]))
    return sorted(chosen, key=lambda i: (-(i["lostClicks"] or 0), -i["impressions"], i["query"]))


def totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in KINDS:
        chosen = [i for i in items if kind in i["kinds"]]
        field = "extraClicks" if kind == "yakin" else "lostClicks"
        out[kind] = {"all": len(chosen), "brand": sum(1 for i in chosen if i["brand"]),
                     "nonBrand": sum(1 for i in chosen if not i["brand"]),
                     "clicks": sum(i[field] or 0 for i in chosen if not i["brand"]),
                     "clicksBrand": sum(i[field] or 0 for i in chosen if i["brand"])}
    return out


def window(today: date) -> tuple[str, str]:
    end = today - timedelta(days=LAG)
    return (end - timedelta(days=DAYS - 1)).isoformat(), end.isoformat()


# ------------------------------------------------------------------------------------------------ veri

def refresh(seo) -> dict[str, Any]:
    """Son 28 günün sorgu+sayfa kırılımını okur ve saklar (bütün satırlar, sayfalı)."""
    s, e = window(date.today())
    rows = connections.gsc_all(s, e, ["query", "page"])
    eng, tenant = seo.engine(), seo.tenant()
    ensure_table(eng)
    with eng.begin() as c:
        c.execute(OPPS.delete().where(OPPS.c.tenant_id == tenant, OPPS.c.kind == "query_page"))
        c.execute(OPPS.insert().values(tenant_id=tenant, kind="query_page", start_date=s, end_date=e,
                                       rows_json=dumps(rows), saved_at=now()))
    return {"rows": len(rows), "start": s, "end": e}


def source(seo) -> dict[str, Any]:
    """Hesabın kaynağı: önce kendi sorgu+sayfa kırılımımız, yoksa ortak önbellekteki yalnız-sorgu satırları."""
    eng, tenant = seo.engine(), seo.tenant()
    ensure_table(eng)
    with eng.connect() as c:
        r = c.execute(sa.select(OPPS).where(OPPS.c.tenant_id == tenant, OPPS.c.kind == "query_page")).mappings().first()
    if r:
        return {"from": "query_page", "start": r["start_date"], "end": r["end_date"], "savedAt": iso(r["saved_at"]),
                "rows": loads(r["rows_json"], [])}
    q = seo.gsc("queries")
    if q:
        return {"from": "queries", "start": q["start"], "end": q["end"], "savedAt": q["savedAt"], "rows": q["rows"]}
    return {"from": None, "start": None, "end": None, "savedAt": None, "rows": []}


def computed(seo) -> dict[str, Any]:
    src = source(seo)
    key = (seo.tenant(), src["from"], src["savedAt"])
    with _cache_lock:
        if _cache["key"] == key and _cache["data"] is not None:
            return _cache["data"]
    curve = ctr_curve(src["rows"])
    items = classify(src["rows"], curve)
    data = {"source": {k: v for k, v in src.items() if k != "rows"} | {"rowCount": len(src["rows"])},
            "curve": [{"position": b, **v} for b, v in sorted(curve.items())], "items": items, "totals": totals(items)}
    with _cache_lock:
        _cache.update(key=key, data=data)
    return data


def product_map(seo) -> dict[str, dict[str, str]]:
    """Adres anahtarı → ürün (kimlik, ad). T-soft `SeoLink` ürünün sitedeki yoludur."""
    link = sa.cast(PRODUCTS.c.data_json, sa.JSON)["SeoLink"].as_string()
    with seo.engine().connect() as c:
        rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, link).where(
            PRODUCTS.c.tenant_id == seo.tenant())).all()
    out: dict[str, dict[str, str]] = {}
    for pid, name, l in rows:
        k = path_key(l)
        if k and k != "/":
            out.setdefault(k, {"id": pid, "name": name})
    return out


# ------------------------------------------------------------------------------------------------ uçlar

def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


def register(app, ctx) -> None:
    seo = ctx.seo

    def nightly() -> None:
        if connections.service_account_email():
            log.info("seo opportunities refresh: %s", refresh(seo))

    seo.nightly.append(("opportunities", nightly))

    @app.get("/api/v1/seo-geo/opportunities")
    def seo_opportunities(request: Request, kind: str = "yakin", brand: str = "0", start: int = 0,
                          limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if kind not in KINDS:
            raise _err(404, "Bilinmeyen fırsat türü.")
        data = computed(seo)
        ranked = rank(data["items"], kind)
        if brand in ("0", "1"):
            ranked = [i for i in ranked if i["brand"] == (brand == "1")]
        start = max(0, start)
        page = ranked[start:start + max(1, limit)]
        products = product_map(seo) if any(i["page"] for i in page) else {}
        items = []
        for i in page:
            p = products.get(path_key(i["page"]) or "") if i["page"] else None
            items.append({k: v for k, v in i.items() if k != "kinds"} | {
                "kinds": i["kinds"], "productId": p["id"] if p else None, "productName": p["name"] if p else None})
        return {"kind": kind, "brand": brand, "start": start, "total": len(ranked), "items": items,
                "totals": data["totals"], "source": data["source"], "curve": data["curve"],
                "connected": bool(connections.service_account_email()),
                "thresholds": {"nearMin": NEAR_MIN, "nearMax": NEAR_MAX, "targetPosition": TARGET_POSITION,
                               "curveMinImpressions": CURVE_MIN_IMPR, "curveMinSamples": CURVE_MIN_SAMPLES,
                               "lowMinImpressions": LOW_MIN_IMPR, "lowRatio": LOW_RATIO, "days": DAYS, "lagDays": LAG}}

    @app.post("/api/v1/seo-geo/opportunities/refresh")
    def seo_opportunities_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        if not connections.service_account_email():
            raise _err(409, "Search Console bağlantısı tanımlı değil (Yönetim → SEO & GEO).")
        try:
            out = refresh(seo)
        except connections.ConnectionError_ as e:
            raise _err(502, str(e)) from None
        seo.audit(user, "run", "opportunities", "Fırsat listesi okuması", out)
        return out
