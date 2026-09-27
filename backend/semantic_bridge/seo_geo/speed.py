"""Sayfa hızı ve Core Web Vitals: PageSpeed Insights (laboratuvar ölçümü) ve CrUX (gerçek Chrome kullanıcıları, p75).

Yalnız `GOOGLE_API_KEY` tanımlıysa koşar (Yönetim → SEO & GEO). Örneklem: anasayfa, en çok satan N ürün, en çok satan
kitabı olan N kategori ve N yazar sayfası (N parametre; kullanılan değer yanıtta yazılır). Her ölçüm
`semantic_seo_speed` tablosuna eklenir (üzerine yazılmaz), eğilim buradan çizilir. Site kökü (origin) için CrUX
günde bir okunur.

Eşikler (Google, p75): LCP 2,5/4 sn, INP 200/500 ms, CLS 0,1/0,25, FCP 1,8/3 sn, TTFB 0,8/1,8 sn.
CrUX'ta yeterli trafik yoksa API 404 döner: "veri yok" olarak kaydedilir, hata sayılmaz.
"""
from __future__ import annotations

import collections
import logging
import threading
import time
import uuid
from datetime import timedelta
from typing import Any, Optional

import httpx
import sqlalchemy as sa
from fastapi import HTTPException, Request

from . import pages
from .store import LINKS, PRODUCTS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo.speed")

PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CRUX_URL = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"

SPEED = sa.Table(
    "semantic_seo_speed", _md,  # her ölçüm ayrı satır: eğilim için
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("url", sa.String(800), nullable=False, index=True),
    sa.Column("kind", sa.String(16), nullable=False),       # origin | home | product | category | author
    sa.Column("name", sa.String(500)),
    sa.Column("strategy", sa.String(8), nullable=False),    # psi: mobile | desktop · crux: phone | desktop
    sa.Column("source", sa.String(8), nullable=False),      # psi | crux
    sa.Column("metrics_json", sa.Text, nullable=False),
    sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False, index=True),
)

#: metrik → (iyi üst sınır, kötü alt sınır). Süreler ms, CLS birimsiz.
THRESHOLDS: dict[str, tuple[float, float]] = {
    "lcp": (2500, 4000), "inp": (200, 500), "cls": (0.1, 0.25), "fcp": (1800, 3000), "ttfb": (800, 1800),
}
CRUX_KEYS = {
    "largest_contentful_paint": "lcp", "interaction_to_next_paint": "inp", "cumulative_layout_shift": "cls",
    "first_contentful_paint": "fcp", "experimental_time_to_first_byte": "ttfb", "time_to_first_byte": "ttfb",
}
PSI_FIELD_KEYS = {
    "LARGEST_CONTENTFUL_PAINT_MS": "lcp", "INTERACTION_TO_NEXT_PAINT": "inp", "CUMULATIVE_LAYOUT_SHIFT_SCORE": "cls",
    "FIRST_CONTENTFUL_PAINT_MS": "fcp", "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "ttfb",
}
PSI_LAB_AUDITS = {
    "largest-contentful-paint": "lcp", "cumulative-layout-shift": "cls", "first-contentful-paint": "fcp",
    "total-blocking-time": "tbt", "speed-index": "si", "server-response-time": "ttfb", "interactive": "tti",
}


def category(metric: str, value: Optional[float]) -> Optional[str]:
    """good | ni (iyileştirilmeli) | poor."""
    if value is None or metric not in THRESHOLDS:
        return None
    good, poor = THRESHOLDS[metric]
    return "good" if value <= good else "ni" if value <= poor else "poor"


def _f(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _date(d: Optional[dict[str, int]]) -> Optional[str]:
    if not d:
        return None
    return f"{d.get('year'):04d}-{d.get('month'):02d}-{d.get('day'):02d}"


def parse_crux(body: dict[str, Any]) -> dict[str, Any]:
    """CrUX queryRecord cevabı → {"metrics": {lcp: {p75, category, good, ni, poor}}, "period": {first, last}}."""
    rec = body.get("record") or {}
    out: dict[str, Any] = {}
    for key, m in (rec.get("metrics") or {}).items():
        short = CRUX_KEYS.get(key)
        if not short:
            continue
        p75 = _f((m.get("percentiles") or {}).get("p75"))
        hist = m.get("histogram") or []
        dens = [_f(h.get("density")) or 0.0 for h in hist] + [0.0, 0.0, 0.0]
        out[short] = {"p75": p75, "category": category(short, p75),
                      "good": round(dens[0], 4), "ni": round(dens[1], 4), "poor": round(dens[2], 4)}
    period = rec.get("collectionPeriod") or {}
    return {"metrics": out, "period": {"first": _date(period.get("firstDate")), "last": _date(period.get("lastDate"))},
            "formFactor": (rec.get("key") or {}).get("formFactor")}


def parse_psi(body: dict[str, Any]) -> dict[str, Any]:
    """PSI v5 cevabı → {"score" (0–100), "lab": {lcp, cls, tbt, …}, "field": {lcp: {p75, category}}, "fieldOrigin"}."""
    lh = body.get("lighthouseResult") or {}
    perf = ((lh.get("categories") or {}).get("performance") or {}).get("score")
    lab = {}
    for audit, short in PSI_LAB_AUDITS.items():
        v = _f(((lh.get("audits") or {}).get(audit) or {}).get("numericValue"))
        if v is not None:
            lab[short] = round(v, 4) if short == "cls" else round(v)
    le = body.get("loadingExperience") or {}
    field = {}
    for key, m in (le.get("metrics") or {}).items():
        short = PSI_FIELD_KEYS.get(key)
        if not short:
            continue
        p = _f(m.get("percentile"))
        if p is not None and short == "cls":
            p = p / 100.0  # PSI CLS'yi yüzle çarpılmış verir
        field[short] = {"p75": p, "category": category(short, p)}
    return {"score": round(perf * 100) if isinstance(perf, (int, float)) else None, "lab": lab, "field": field,
            "fieldOrigin": bool(le.get("origin_fallback")), "labCategory": {k: category(k, v) for k, v in lab.items()}}


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


class Speed:
    def __init__(self, seo: Any) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "done": 0, "failed": 0, "queue": None, "startedAt": None,
                                      "finishedAt": None, "error": None, "sample": None}
        self._ready: set[int] = set()

    def engine(self) -> sa.engine.Engine:
        eng = self.seo.engine()
        if id(eng) not in self._ready:
            SPEED.create(eng, checkfirst=True)
            self._ready.add(id(eng))
        return eng

    def key(self) -> str:
        return self.seo.conf("GOOGLE_API_KEY") or ""

    def site(self) -> str:
        return (self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")

    # -------------------------------------------------------------- örneklem
    def sample(self, products: int, pages_n: int) -> list[dict[str, Any]]:
        from . import SALES, VIEWS

        site, tenant = self.site(), self.seo.tenant()
        out = [{"url": f"{site}/", "kind": "home", "name": "Anasayfa"}]
        with self.engine().connect() as c:
            prows = c.execute(sa.select(PRODUCTS.c.name, PRODUCTS.c.data_json).where(
                PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True)).order_by(SALES.desc(), VIEWS.desc())).all()
            links = c.execute(sa.select(LINKS.c.link, LINKS.c.type, LINKS.c.table_id, LINKS.c.title).where(
                LINKS.c.tenant_id == tenant, LINKS.c.type.in_(["category", "model"]))).all()
        data = [loads(d, {}) for _, d in prows]
        for (name, _), p in list(zip(prows, data))[:max(0, products)]:
            link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl")
            if link:
                out.append({"url": link if str(link).startswith("http") else f"{site}/{str(link).strip('/')}",
                            "kind": "product", "name": name})
        st = pages.stats(data)
        for typ, kind in (("category", "category"), ("model", "author")):
            ranked = sorted(((st.get((typ, str(tid)), {}).get("sales", 0), link, title) for link, t, tid, title in links
                             if t == typ and link), key=lambda x: -x[0])
            for sales, link, title in ranked[:max(0, pages_n)]:
                out.append({"url": f"{site}/{str(link).strip('/')}", "kind": kind,
                            "name": (str(title or "").split("|")[0].strip() or link)})
        seen: set[str] = set()
        return [x for x in out if not (x["url"] in seen or seen.add(x["url"]))]

    # -------------------------------------------------------------- ölçüm
    def psi(self, client: httpx.Client, url: str, strategy: str) -> dict[str, Any]:
        r = client.get(PSI_URL, params={"url": url, "strategy": strategy, "category": "performance", "key": self.key()},
                       timeout=180)
        if r.status_code != 200:
            return {"error": f"{r.status_code}: {_message(r)}"}
        return parse_psi(r.json())

    def crux(self, client: httpx.Client, form_factor: str, *, origin: Optional[str] = None,
             url: Optional[str] = None) -> dict[str, Any]:
        body: dict[str, Any] = {"formFactor": form_factor}
        body.update({"origin": origin} if origin else {"url": url})
        r = client.post(CRUX_URL, params={"key": self.key()}, json=body, timeout=60)
        if r.status_code == 404:
            return {"noData": True, "metrics": {}}
        if r.status_code != 200:
            return {"error": f"{r.status_code}: {_message(r)}", "metrics": {}}
        return parse_crux(r.json())

    def _save(self, url: str, kind: str, name: Optional[str], strategy: str, source: str, metrics: dict[str, Any]) -> None:
        with self.engine().begin() as c:
            c.execute(SPEED.insert().values(id=uuid.uuid4().hex, tenant_id=self.seo.tenant(), url=url[:800], kind=kind,
                                            name=(name or "")[:500] or None, strategy=strategy, source=source,
                                            metrics_json=dumps(metrics), measured_at=now()))

    def start(self, products: int, pages_n: int, budget: int) -> bool:
        if not self.key():
            raise _err(409, "Google API anahtarı tanımlı değil (Yönetim → SEO & GEO).")
        if not self._lock.acquire(blocking=False):
            return False
        self.state.update(running=True, done=0, failed=0, queue=None, startedAt=iso(now()), finishedAt=None, error=None,
                          sample={"products": max(0, products), "pages": max(0, pages_n)})
        threading.Thread(target=self._run, args=(max(0, products), max(0, pages_n), max(60, budget)),
                         name="seo-speed", daemon=True).start()
        return True

    def _run(self, products: int, pages_n: int, budget: int) -> None:
        deadline = time.monotonic() + budget
        try:
            site = self.site()
            targets = self.sample(products, pages_n)
            self.state["queue"] = len(targets)
            with httpx.Client() as client:
                origin = site.split("/", 3)
                origin = f"{origin[0]}//{origin[2]}"
                for ff in ("PHONE", "DESKTOP"):
                    self._save(origin, "origin", None, ff.lower(), "crux", self.crux(client, ff, origin=origin))
                for t in targets:
                    if time.monotonic() > deadline:
                        break
                    ok = True
                    for strategy in ("mobile", "desktop"):
                        try:
                            m = self.psi(client, t["url"], strategy)
                        except (httpx.HTTPError, ValueError) as e:
                            m = {"error": str(e)[:300]}
                        ok &= "error" not in m
                        self._save(t["url"], t["kind"], t.get("name"), strategy, "psi", m)
                        time.sleep(1.0)
                    for ff in ("PHONE", "DESKTOP"):
                        try:
                            m = self.crux(client, ff, url=t["url"])
                        except (httpx.HTTPError, ValueError) as e:
                            m = {"error": str(e)[:300], "metrics": {}}
                        self._save(t["url"], t["kind"], t.get("name"), ff.lower(), "crux", m)
                    self.state["done" if ok else "failed"] += 1
        except Exception as e:  # noqa: BLE001
            self.state["error"] = str(e)[:500]
            log.exception("seo speed run failed")
        finally:
            self.state.update(running=False, finishedAt=iso(now()))
            self._lock.release()

    # -------------------------------------------------------------- rapor
    def report(self, days: int) -> dict[str, Any]:
        since = now() - timedelta(days=max(1, days))
        with self.engine().connect() as c:
            rows = c.execute(sa.select(SPEED).where(SPEED.c.tenant_id == self.seo.tenant(), SPEED.c.measured_at >= since)
                             .order_by(SPEED.c.measured_at.asc())).mappings().all()
        latest: dict[tuple[str, str, str], Any] = {}
        for r in rows:
            latest[(r["url"], r["source"], r["strategy"])] = r
        origin: dict[str, Any] = {}
        items: dict[str, dict[str, Any]] = {}
        for (url, source, strategy), r in latest.items():
            m = {**loads(r["metrics_json"], {}), "measuredAt": iso(r["measured_at"])}
            if r["kind"] == "origin":
                origin[strategy] = {**m, "origin": url}
                continue
            it = items.setdefault(url, {"url": url, "kind": r["kind"], "name": r["name"], "psi": {}, "crux": {}})
            it[source][strategy] = m
        order = {"home": 0, "product": 1, "category": 2, "author": 3}
        trend_origin = []
        psi_days: dict[tuple[str, str], list[float]] = collections.defaultdict(list)
        for r in rows:
            m = loads(r["metrics_json"], {})
            day = iso(r["measured_at"])[:10]
            if r["kind"] == "origin" and m.get("metrics"):
                trend_origin.append({"date": day, "formFactor": r["strategy"],
                                     **{k: v.get("p75") for k, v in m["metrics"].items()}})
            elif r["source"] == "psi" and m.get("score") is not None:
                psi_days[(day, r["strategy"])].append(m["score"])
        trend_psi = [{"date": d, "strategy": s, "score": round(sum(v) / len(v)), "pages": len(v)}
                     for (d, s), v in sorted(psi_days.items())]
        return {"configured": bool(self.key()), "state": self.state, "days": days,
                "origin": origin, "items": sorted(items.values(), key=lambda x: (order.get(x["kind"], 9), x["name"] or x["url"])),
                "trend": {"origin": trend_origin, "psi": trend_psi},
                "thresholds": {k: {"good": g, "poor": p} for k, (g, p) in THRESHOLDS.items()}}


def _message(r: httpx.Response) -> str:
    try:
        return str(((r.json() or {}).get("error") or {}).get("message") or r.text)[:300]
    except ValueError:
        return r.text[:300]


def register(app, ctx) -> None:
    speed = Speed(ctx.seo)

    @app.get("/api/v1/seo-geo/speed")
    def seo_speed(request: Request, days: int = 90) -> dict[str, Any]:
        ctx.gate(request)
        return speed.report(days)

    @app.post("/api/v1/seo-geo/speed/run")
    def seo_speed_run(request: Request, products: int = 10, pages: int = 5, budget: int = 3600) -> dict[str, Any]:
        user = ctx.gate(request)
        started = speed.start(products, pages, budget)
        ctx.seo.audit(user, "run", "speed", "Hız ölçümü", {"started": started, "products": products, "pages": pages})
        return {"started": started, "state": speed.state}

    def nightly() -> None:
        if speed.key():
            try:
                speed.start(10, 5, 3600)  # kendi iş parçacığında koşar
            except HTTPException:
                pass

    ctx.seo.nightly.append(("speed", nightly))
