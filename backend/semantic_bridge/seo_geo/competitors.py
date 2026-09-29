"""Rakipler: aynı kitap aramasında timas.com.tr ile rakip sitelerin Google sırası.

Her kitap için Google'da "kitap adı + yazar" aranır (Türkiye, Türkçe; arama sonucu servisi aylık kotalı,
`SERPAPI_KEY` / `SEO_SERP_MONTHLY`). Organik sonuçların ilk 20'si alan adıyla saklanır; hangi alan adının rakip
sayıldığı (`SEO_COMPETITORS`) okuma anında uygulanır — liste değişince eski aramalar da yeni listeyle okunur.
Ayrıca sayfada alışveriş sonuçları, yapay zekâ özeti ve bilgi paneli var mı, bizim sitemiz orada mı kaydedilir.

Sıra: aktif kitaplar çok satandan aza; son `REFRESH_DAYS` gün içinde aranmış kitap atlanır. Tur başına arama
sayısı kalan aylık kotadır; gece işi kotayı ayın kalan günlerine böler (günlük dilim). Yalnız okunur: Google'a
arama isteğinden başka hiçbir yere bir şey gönderilmez.
"""
from __future__ import annotations

import logging
import math
import re
import threading
import uuid
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlparse

import sqlalchemy as sa
from fastapi import Request

from . import rules
from .store import PRODUCTS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

SERP_URL = "https://serpapi.com/search.json"
REFRESH_DAYS = 30
DEFAULT_MONTHLY = 240
KEEP = 20            # saklanan organik sonuç sayısı (Google'ın ilk iki sayfası)
FILTERS = ("geride", "onde", "yok")

SERP = sa.Table(
    "semantic_seo_serp", _md,  # bir kitabın bir Google araması: organik sıralar ve sayfa öğeleri
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("product_id", sa.String(40), nullable=False, index=True),
    sa.Column("query", sa.String(600), nullable=False),
    sa.Column("searched_at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("positions_json", sa.Text, nullable=False),   # {"organic": [{position, domain, title, link}], "domains": {...}}
    sa.Column("features_json", sa.Text, nullable=False),    # {shopping, shoppingUs, aiOverview, aiOverviewUs, knowledgePanel, ...}
)
USAGE = sa.Table(
    "semantic_seo_serp_usage", _md,  # ay başına harcanan arama (kota)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("month", sa.String(7), primary_key=True),       # 2026-09
    sa.Column("used", sa.Integer, nullable=False, default=0),
)
_ready: set[int] = set()
_ready_lock = threading.Lock()


# ------------------------------------------------------------------------------ saf yardımcılar (testli)

_PAREN = re.compile(r"\s*[(\[{][^)\]}]*[)\]}]")


def clean_title(name: Any) -> str:
    """Ürün adından parantezli ekler ("(Ciltli)", "[Özel Baskı]") atılır; boşluk sadeleşir."""
    t = rules.text_of(name) if name else ""
    prev = None
    while prev != t:             # iç içe ya da art arda parantezler
        prev, t = t, _PAREN.sub("", t)
    return re.sub(r"\s+", " ", t).strip(" -–|,")


def build_query(p: dict[str, Any]) -> str:
    """Arama metni: kitap adı + yazar (T-soft `Model` alanı yazardır). Yazar adı başlıkta zaten geçiyorsa eklenmez."""
    title = clean_title(p.get("ProductName"))
    author = re.sub(r"\s+", " ", rules.text_of(p.get("Model")) if p.get("Model") else "").strip()
    if author and author.casefold() not in title.casefold():
        return f"{title} {author}".strip()
    return title


def domain_of(url: Any) -> str:
    """Alan adı: küçük harf, "www." atılmış. Şemasız girdi ("timas.com.tr/x") de kabul edilir."""
    s = str(url or "").strip().lower()
    if not s:
        return ""
    if "://" not in s:
        s = "http://" + s
    host = (urlparse(s).hostname or "").strip(".")
    return host[4:] if host.startswith("www.") else host


def matches(host: str, domain: str) -> bool:
    """Alt alan adları da sayılır: "m.dr.com.tr" → "dr.com.tr". Benzer adlı başka site ("xdr.com.tr") sayılmaz."""
    host, domain = domain_of(host), domain_of(domain)
    return bool(host and domain) and (host == domain or host.endswith("." + domain))


def parse_domains(raw: Optional[str]) -> list[str]:
    out: list[str] = []
    for part in re.split(r"[,\s;]+", raw or ""):
        d = domain_of(part)
        if d and d not in out:
            out.append(d)
    return out


def organic(serp: dict[str, Any]) -> list[dict[str, Any]]:
    """Organik sonuçlar, sırasıyla; ilk `KEEP` tanesi."""
    out = []
    for i, r in enumerate(serp.get("organic_results") or []):
        link = r.get("link") or ""
        try:
            pos = int(r.get("position") or i + 1)
        except (TypeError, ValueError):
            pos = i + 1
        out.append({"position": pos, "domain": domain_of(link), "title": (r.get("title") or "")[:300], "link": link[:800]})
    out.sort(key=lambda x: x["position"])
    return out[:KEEP]


def positions(results: list[dict[str, Any]], domains: list[str]) -> dict[str, Optional[int]]:
    """Her alan adının en iyi (en küçük) organik sırası; çıkmadıysa None."""
    out: dict[str, Optional[int]] = {d: None for d in domains}
    for r in results:
        for d in domains:
            if matches(r["domain"], d) and (out[d] is None or r["position"] < out[d]):
                out[d] = r["position"]
    return out


def _any_link(items: Any, domain: str) -> bool:
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        for k in ("link", "product_link", "source_link", "url"):
            if it.get(k) and matches(domain_of(it[k]), domain):
                return True
        label = domain.split(".")[0]
        if label and label in re.sub(r"[^a-z0-9]", "", str(it.get("source") or "").lower().replace("ş", "s")):
            return True
    return False


def features(serp: dict[str, Any], our: str) -> dict[str, Any]:
    """Sayfa öğeleri: alışveriş sonuçları, yapay zekâ özeti, bilgi paneli; bizim sitemiz içlerinde mi."""
    shop = [*(serp.get("shopping_results") or []), *(serp.get("inline_shopping") or []),
            *(serp.get("inline_shopping_results") or []), *(serp.get("immersive_products") or [])]
    ai = serp.get("ai_overview")
    ai_refs = (ai or {}).get("references") if isinstance(ai, dict) else None
    kg = serp.get("knowledge_graph")
    return {
        "shopping": bool(shop), "shoppingUs": _any_link(shop, our) if shop else False,
        "aiOverview": bool(ai),
        # Özet ayrı bir istekle açılıyorsa (yalnız sayfa belirteci gelir) kaynakları bilinmez: None.
        "aiOverviewUs": (_any_link(ai_refs, our) if isinstance(ai_refs, list) else None) if ai else False,
        "knowledgePanel": bool(kg),
        "knowledgePanelTitle": (kg.get("title") if isinstance(kg, dict) else None),
    }


def verdict(ours: Optional[int], rivals: dict[str, Optional[int]]) -> tuple[str, Optional[dict[str, Any]]]:
    """(durum, en iyi rakip). yok: biz ilk 20'de yokuz · geride: bir rakip bizden önde · onde: hiçbir rakip önde değil."""
    found = [(p, d) for d, p in rivals.items() if p is not None]
    best = min(found) if found else None
    best_v = {"domain": best[1], "position": best[0]} if best else None
    if ours is None:
        return "yok", best_v
    if best and best[0] < ours:
        return "geride", best_v
    return "onde", best_v


def slice_size(monthly: int, used: int, today: datetime) -> int:
    """Günlük dilim: kalan kota / ayın kalan günleri (bugün dahil), yukarı yuvarlanır."""
    remaining = max(0, monthly - used)
    days_left = monthrange(today.year, today.month)[1] - today.day + 1
    return math.ceil(remaining / max(1, days_left)) if remaining else 0


def month_key(t: datetime) -> str:
    return t.strftime("%Y-%m")


# ------------------------------------------------------------------------------ çalışma

class Competitors:
    def __init__(self, seo) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "done": 0, "failed": 0, "queue": None, "startedAt": None,
                                      "finishedAt": None, "error": None}

    def engine(self) -> sa.engine.Engine:
        eng = self.seo.engine()
        with _ready_lock:
            if id(eng) not in _ready:
                from semantic_layer.store import schema_stamp
                schema_stamp.create_all(_md, eng, tables=[SERP, USAGE])
                _ready.add(id(eng))
        return eng

    def key(self) -> str:
        return (self.seo.conf("SERPAPI_KEY") or "").strip()

    def monthly(self) -> int:
        try:
            return max(0, int(self.seo.conf("SEO_SERP_MONTHLY") or DEFAULT_MONTHLY))
        except ValueError:
            return DEFAULT_MONTHLY

    def our(self) -> str:
        return domain_of(self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr") or "timas.com.tr"

    def rivals(self) -> list[str]:
        our = self.our()
        return [d for d in parse_domains(self.seo.conf("SEO_COMPETITORS")) if not matches(d, our)]

    def used(self) -> int:
        with self.engine().connect() as c:
            return c.execute(sa.select(USAGE.c.used).where(USAGE.c.tenant_id == self.seo.tenant(),
                                                           USAGE.c.month == month_key(now()))).scalar() or 0

    def _spend(self) -> None:
        tenant, month = self.seo.tenant(), month_key(now())
        with self.engine().begin() as c:
            n = c.execute(USAGE.update().where(USAGE.c.tenant_id == tenant, USAGE.c.month == month)
                          .values(used=USAGE.c.used + 1)).rowcount
            if not n:
                c.execute(USAGE.insert().values(tenant_id=tenant, month=month, used=1))

    def quota(self) -> dict[str, Any]:
        monthly, used = self.monthly(), self.used()
        return {"monthly": monthly, "used": used, "remaining": max(0, monthly - used),
                "dailySlice": slice_size(monthly, used, now()), "month": month_key(now())}

    def queue(self) -> list[tuple[str, dict[str, Any]]]:
        """Çok satandan aza aktif kitaplar; son REFRESH_DAYS günde aranmış olan atlanır."""
        from . import SALES, VIEWS

        tenant = self.seo.tenant()
        recent = sa.select(SERP.c.product_id).where(SERP.c.tenant_id == tenant,
                                                    SERP.c.searched_at >= now() - timedelta(days=REFRESH_DAYS))
        with self.engine().connect() as c:
            rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.data_json).where(
                PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True), PRODUCTS.c.product_id.not_in(recent))
                .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)).all()
        return [(pid, loads(d, {})) for pid, d in rows]

    def start(self, count: int) -> bool:
        if not self.key() or count <= 0:
            return False
        if not self._lock.acquire(blocking=False):
            return False
        self.state.update(running=True, done=0, failed=0, queue=None, startedAt=iso(now()), finishedAt=None, error=None)
        threading.Thread(target=self._run, args=(count,), name="seo-serp", daemon=True).start()
        return True

    def _run(self, count: int) -> None:
        import httpx

        tenant, our = self.seo.tenant(), self.our()
        try:
            todo = self.queue()
            count = min(count, max(0, self.monthly() - self.used()))
            self.state["queue"] = min(count, len(todo))
            with httpx.Client(timeout=60) as client:
                for pid, p in todo[:count]:
                    q = build_query(p)
                    if not q:
                        continue
                    r = client.get(SERP_URL, params={"engine": "google", "q": q, "gl": "tr", "hl": "tr",
                                                     "google_domain": "google.com.tr", "num": KEEP, "api_key": self.key()})
                    if r.status_code in (401, 403, 429):
                        raise RuntimeError("Google arama sonucu servisi isteği reddetti (anahtar ya da kota); tur durdu.")
                    data = r.json() if r.status_code == 200 else {}
                    if r.status_code != 200 or data.get("error"):
                        err = str(data.get("error") or f"HTTP {r.status_code}")
                        # "sonuç yok" da harcanmış aramadır; kayıt boş sonuçla yazılır, kitap 30 gün beklemeye girer.
                        if "hasn't returned any results" not in err:
                            self.state["failed"] += 1
                            continue
                    self._spend()
                    res = organic(data)
                    with self.engine().begin() as c:
                        c.execute(SERP.insert().values(
                            id=uuid.uuid4().hex, tenant_id=tenant, product_id=pid, query=q[:600], searched_at=now(),
                            positions_json=dumps({"organic": res, "domains": positions(res, [our, *self.rivals()])}),
                            features_json=dumps(features(data, our))))
                    self.state["done"] += 1
        except Exception as e:  # noqa: BLE001 — tur durur, yapılan aramalar kalır
            self.state["error"] = str(e)[:500]
            log.exception("seo serp run failed")
        finally:
            self.state.update(running=False, finishedAt=iso(now()))
            self._lock.release()

    # -------------------------------------------------------------- okuma
    def latest(self) -> list[dict[str, Any]]:
        """Her kitabın son araması, ürün adı ve satışıyla; çok satandan aza."""
        from . import SALES, _product_view  # döngüsel içe aktarım: paket yüklendikten sonra

        tenant = self.seo.tenant()
        last = (sa.select(SERP.c.product_id, sa.func.max(SERP.c.searched_at).label("m"))
                .where(SERP.c.tenant_id == tenant).group_by(SERP.c.product_id).subquery())
        with self.engine().connect() as c:
            rows = c.execute(sa.select(SERP, PRODUCTS.c.name, PRODUCTS.c.data_json, SALES.label("sales")).select_from(
                SERP.join(last, sa.and_(last.c.product_id == SERP.c.product_id, last.c.m == SERP.c.searched_at))
                .outerjoin(PRODUCTS, sa.and_(PRODUCTS.c.tenant_id == SERP.c.tenant_id, PRODUCTS.c.product_id == SERP.c.product_id)))
                .where(SERP.c.tenant_id == tenant).order_by(SALES.desc().nullslast(), SERP.c.product_id)).mappings().all()
        our, rivals = self.our(), self.rivals()
        site = self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr"
        out, seen = [], set()
        for r in rows:
            if r["product_id"] in seen:     # aynı anda iki kayıt (eşit zaman) → bir tanesi
                continue
            seen.add(r["product_id"])
            pos = loads(r["positions_json"], {})
            res = pos.get("organic") or []
            p = positions(res, [our, *rivals])
            state, best = verdict(p.get(our), {d: p[d] for d in rivals})
            view = _product_view({**{k: None for k in ("code", "brand", "active", "score", "synced_at")},
                                  "product_id": r["product_id"], "name": r["name"], "issues_json": "[]",
                                  "data_json": r["data_json"] or "{}"}, site) if r["data_json"] else {}
            out.append({"productId": r["product_id"], "name": r["name"] or r["query"], "image": view.get("image"),
                        "url": view.get("url"), "sales": int(r["sales"] or 0), "query": r["query"],
                        "searchedAt": iso(r["searched_at"]), "our": p.get(our), "best": best,
                        "positions": {d: p[d] for d in rivals}, "verdict": state,
                        "features": loads(r["features_json"], {}), "results": res[:10]})
        return out

    def summary(self, rows: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        rows = self.latest() if rows is None else rows
        our, rivals = self.our(), self.rivals()
        n = len(rows)
        first = sum(1 for r in rows if r["verdict"] == "onde")
        domains = []
        for d in [our, *rivals]:
            ps = [(r["our"] if d == our else r["positions"].get(d)) for r in rows]
            got = [x for x in ps if x is not None]
            beats = 0 if d == our else sum(
                1 for r in rows if r["positions"].get(d) is not None and (r["our"] is None or r["positions"][d] < r["our"]))
            domains.append({"domain": d, "ours": d == our, "found": len(got),
                            "average": round(sum(got) / len(got), 1) if got else None, "beatsUs": beats})
        feat = lambda k: sum(1 for r in rows if r["features"].get(k))  # noqa: E731
        return {
            "configured": bool(self.key()), "our": our, "competitors": rivals, "tracked": n,
            "first": first, "firstShare": round(100 * first / n, 1) if n else None,
            "counts": {k: sum(1 for r in rows if r["verdict"] == k) for k in FILTERS},
            "domains": domains,
            "features": {"shopping": feat("shopping"), "shoppingUs": feat("shoppingUs"), "aiOverview": feat("aiOverview"),
                         "aiOverviewUs": feat("aiOverviewUs"), "knowledgePanel": feat("knowledgePanel")},
            "quota": self.quota(), "refreshDays": REFRESH_DAYS, "state": self.state,
            "lastSearched": max((r["searchedAt"] for r in rows if r["searchedAt"]), default=None),
        }


def register(app, ctx) -> None:
    comp = Competitors(ctx.seo)
    ctx.seo.competitors = comp

    @app.get("/api/v1/seo-geo/competitors")
    def seo_competitors(request: Request, filter: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if filter and filter not in FILTERS:
            from . import _err
            raise _err(422, "Bilinmeyen süzgeç.")
        rows = comp.latest()
        shown = [r for r in rows if not filter or r["verdict"] == filter]
        s, n = max(0, start), max(1, limit)
        return {"total": len(shown), "start": s, "items": shown[s:s + n], "summary": comp.summary(rows)}

    @app.get("/api/v1/seo-geo/competitors/summary")
    def seo_competitors_summary(request: Request) -> dict[str, Any]:
        ctx.gate(request)
        return comp.summary()

    @app.post("/api/v1/seo-geo/competitors/run")
    def seo_competitors_run(request: Request, count: int = 0) -> dict[str, Any]:
        """Arka planda arar; `count` verilmezse kalan aylık kotanın tamamı (kotayı aşmaz)."""
        user = ctx.gate(request)
        if not comp.key():
            from . import _err
            raise _err(409, "Google arama sonucu anahtarı girilmemiş (Yönetim → SEO & GEO).")
        q = comp.quota()
        n = min(q["remaining"], count) if count > 0 else q["remaining"]
        if n <= 0:
            from . import _err
            raise _err(409, "Bu ayın arama kotası doldu.")
        started = comp.start(n)
        ctx.seo.audit(user, "run", "competitors", "Rakip sıralaması", {"started": started, "count": n})
        return {"started": started, "count": n, "state": comp.state, "quota": q}

    def nightly() -> None:
        if not comp.key():
            return
        comp.start(comp.quota()["dailySlice"])

    ctx.seo.nightly.append(("competitors", nightly))
