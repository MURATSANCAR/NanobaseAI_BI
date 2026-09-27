"""Gelen bağlantılar (Bing Webmaster, yalnız okuma): hangi sayfamıza kaç dış bağlantı var, hangi siteler bağlantı
veriyor, son okumaya göre yeni/kaybolan bağlantılar, bağlantısı hiç görünmeyen çok satan kitaplar.

Bing Webmaster API (JSON, anahtar `BING_WEBMASTER_API_KEY`, bing.py ile aynı):
- `GetLinkCounts?siteUrl=…&page=N` → `{"Links": [{"Url", "Count"}], "TotalPages"}`: sitenin bağlantı alan sayfaları.
- `GetUrlLinks?siteUrl=…&link=<sayfa>&page=N` → `{"Details": [{"Url", "AnchorText"}], "TotalPages"}`: bir sayfaya
  bağlantı veren dış adresler.
Sayfalama `TotalPages`'e göre sonuna kadar yürür (tavan yok). Sayfa başına ayrıntı okuması zaman alır; gece turu
`BUDGET_SECONDS` içinde en çok bağlantı alan sayfadan başlayarak okur, bitmeyen sayfa "ayrıntısı okunmadı" kalır.

Anlık görüntüler `semantic_seo_backlink_*` tablolarında; son `KEEP_SNAPSHOTS` tanesi tutulur. Yeni/kaybolan yalnız
iki görüntüde de ayrıntısı okunmuş hedef sayfalar için hesaplanır (okunmamış sayfa "kayboldu" sayılmaz).
Bing yalnız kendi gördüğü bağlantıları bilir; bu tam liste değildir.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Iterable, Optional
from urllib.parse import quote, urlparse

import httpx
import sqlalchemy as sa
from fastapi import Request

from .bing import API, BingError, _mask, site_root, unwrap
from .store import PRODUCTS, _md, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

#: Gece turunda sayfa ayrıntısı (GetUrlLinks) okumaya ayrılan süre.
BUDGET_SECONDS = 1800
#: Saklanan anlık görüntü sayısı (karşılaştırma için en az 2).
KEEP_SNAPSHOTS = 8
#: Bing'e ardışık istekler arası bekleme.
PAUSE_SECONDS = 0.5
SETUP = ("Bing Webmaster Tools → Ayarlar → API erişimi'nden anahtar alınıp Yönetim → SEO & GEO → «Bing Webmaster API "
         "anahtarı» alanına girilmeli. Site Bing Webmaster'da doğrulanmış olmalı (Google Search Console'dan içe aktarma "
         "en kısa yol). Anahtar girilince gece her tur gelen bağlantılar okunur.")

SNAPS = sa.Table(
    "semantic_seo_backlink_snaps", _md,  # Bing gelen bağlantı okuması (anlık görüntü)
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("pages", sa.Integer, nullable=False),          # bağlantı alan sayfa
    sa.Column("detailed", sa.Integer, nullable=False),       # ayrıntısı okunan sayfa
    sa.Column("links", sa.Integer, nullable=False),          # okunan bağlantı satırı
    sa.Column("complete", sa.Boolean, nullable=False),
    sa.Column("error", sa.String(1000)),
)
COUNTS = sa.Table(
    "semantic_seo_backlink_counts", _md,
    sa.Column("snap_id", sa.String(32), primary_key=True),
    sa.Column("target", sa.String(800), primary_key=True),
    sa.Column("count", sa.Integer, nullable=False),
    sa.Column("detailed", sa.Boolean, nullable=False),
)
LINKS_T = sa.Table(
    "semantic_seo_backlinks", _md,
    sa.Column("snap_id", sa.String(32), primary_key=True, index=True),
    sa.Column("target", sa.String(800), primary_key=True),
    sa.Column("source", sa.String(800), primary_key=True),
    sa.Column("anchor", sa.String(300)),
)
_TABLES = (SNAPS, COUNTS, LINKS_T)
_ready: set[int] = set()
_ready_lock = threading.Lock()


def _ensure(eng: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(eng) in _ready:
            return
        for t in _TABLES:
            t.create(eng, checkfirst=True)
        _ready.add(id(eng))


# ------------------------------------------------------------------ saf kısım
def _int(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def parse_link_counts(body: Any) -> tuple[list[dict[str, Any]], int]:
    d = unwrap(body) or {}
    rows = d.get("Links") if isinstance(d, dict) else d
    out = [{"url": str(r.get("Url") or "").strip(), "count": _int(r.get("Count"))}
           for r in rows or [] if isinstance(r, dict) and r.get("Url")]
    return out, _int(d.get("TotalPages")) if isinstance(d, dict) else 0


def parse_url_links(body: Any) -> tuple[list[dict[str, Any]], int]:
    d = unwrap(body) or {}
    rows = d.get("Details") if isinstance(d, dict) else d
    out = [{"url": str(r.get("Url") or "").strip(), "anchor": (str(r.get("AnchorText") or "").strip() or None)}
           for r in rows or [] if isinstance(r, dict) and r.get("Url")]
    return out, _int(d.get("TotalPages")) if isinstance(d, dict) else 0


def domain_of(url: str) -> str:
    host = (urlparse(url if "://" in url else f"http://{url}").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def norm_url(url: str) -> str:
    u = urlparse(url if "://" in url else f"https://{url}")
    host = (u.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    return f"{host}{u.path.rstrip('/') or '/'}".lower()


def diff(prev: Iterable[tuple[str, str]], cur: Iterable[tuple[str, str]], targets: set[str]) -> dict[str, list[tuple[str, str]]]:
    """(hedef, kaynak) çiftleri; yalnız `targets` (iki görüntüde de ayrıntısı okunmuş hedefler) karşılaştırılır."""
    p = {x for x in prev if x[0] in targets}
    c = {x for x in cur if x[0] in targets}
    return {"new": sorted(c - p), "lost": sorted(p - c)}


def domains(pairs: Iterable[tuple[str, str]]) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for target, source in pairs:
        d = domain_of(source)
        if not d:
            continue
        a = agg.setdefault(d, {"domain": d, "links": 0, "pages": set()})
        a["links"] += 1
        a["pages"].add(target)
    out = [{"domain": a["domain"], "links": a["links"], "pages": len(a["pages"])} for a in agg.values()]
    return sorted(out, key=lambda x: (-x["links"], x["domain"]))


# ------------------------------------------------------------------ ağ
def call(method: str, key: str, params: dict[str, Any], timeout: float = 60) -> Any:
    q = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    url = f"{API}/{method}?{q}&apikey={quote(key, safe='')}"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as c:
            resp = c.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError as e:
        raise BingError(_mask(f"Bing'e ulaşılamadı: {e}", key)) from None
    if resp.status_code in (401, 403):
        raise BingError("Bing anahtarı geçersiz ya da bu site için yetkisi yok.")
    if resp.status_code >= 400:
        raise BingError(_mask(f"Bing {method} {resp.status_code}: {resp.text[:200]}", key))
    try:
        return resp.json()
    except ValueError:
        raise BingError(f"Bing {method} cevabı okunamadı.") from None


class Backlinks:
    def __init__(self, seo) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "phase": None, "done": 0, "queue": None, "startedAt": None,
                                      "finishedAt": None, "error": None}

    def engine(self) -> sa.engine.Engine:
        e = self.seo.engine()
        _ensure(e)
        return e

    def key(self) -> str:
        return (self.seo.conf("BING_WEBMASTER_API_KEY") or "").strip()

    def site(self) -> str:
        return site_root(self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr") + "/"

    def start(self, budget: int = BUDGET_SECONDS) -> bool:
        if not self.key():
            return False
        if not self._lock.acquire(blocking=False):
            return False
        self.state.update(running=True, phase="sayfalar", done=0, queue=None, startedAt=iso(now()), finishedAt=None, error=None)
        threading.Thread(target=self._run, args=(budget,), name="seo-backlinks", daemon=True).start()
        return True

    def _run(self, budget: int) -> None:
        key, site, tenant = self.key(), self.site(), self.seo.tenant()
        deadline = time.monotonic() + max(60, budget)
        sid = uuid.uuid4().hex
        counts: list[dict[str, Any]] = []
        links: dict[tuple[str, str], Optional[str]] = {}
        detailed: set[str] = set()
        error = None
        try:
            page = 0
            while True:
                rows, total = parse_link_counts(call("GetLinkCounts", key, {"siteUrl": site, "page": page}))
                counts += rows
                page += 1
                if not rows or page >= max(total, 1):
                    break
                time.sleep(PAUSE_SECONDS)
            counts.sort(key=lambda r: -r["count"])
            self.state.update(phase="bağlantılar", queue=len(counts))
            for r in counts:
                if time.monotonic() > deadline:
                    break
                p = 0
                while True:
                    got, total = parse_url_links(call("GetUrlLinks", key, {"siteUrl": site, "link": r["url"], "page": p}))
                    for g in got:
                        links[(r["url"][:800], g["url"][:800])] = (g["anchor"] or None) and g["anchor"][:300]
                    p += 1
                    time.sleep(PAUSE_SECONDS)
                    if not got or p >= max(total, 1):
                        break
                detailed.add(r["url"])
                self.state["done"] += 1
        except BingError as e:
            error = str(e)[:1000]
        except Exception as e:  # noqa: BLE001
            error = str(e)[:1000]
            log.exception("seo backlinks failed")
        try:
            if counts:
                self._save(sid, tenant, counts, links, detailed, error)
        finally:
            self.state.update(running=False, phase=None, finishedAt=iso(now()), error=error)
            self._lock.release()

    def _save(self, sid: str, tenant: str, counts: list[dict[str, Any]], links: dict[tuple[str, str], Optional[str]],
              detailed: set[str], error: Optional[str]) -> None:
        seen: dict[str, dict[str, Any]] = {}
        for r in counts:
            seen.setdefault(r["url"][:800], dict(snap_id=sid, target=r["url"][:800], count=r["count"],
                                                 detailed=r["url"] in detailed))
        with self.engine().begin() as c:
            c.execute(SNAPS.insert().values(id=sid, tenant_id=tenant, taken_at=now(), pages=len(seen), detailed=len(detailed),
                                            links=len(links), complete=len(detailed) == len(seen) and not error, error=error))
            v = list(seen.values())
            for i in range(0, len(v), 1000):
                c.execute(COUNTS.insert(), v[i:i + 1000])
            lv = [dict(snap_id=sid, target=t, source=s, anchor=a) for (t, s), a in links.items()]
            for i in range(0, len(lv), 1000):
                c.execute(LINKS_T.insert(), lv[i:i + 1000])
            old = [r[0] for r in c.execute(sa.select(SNAPS.c.id).where(SNAPS.c.tenant_id == tenant)
                                           .order_by(SNAPS.c.taken_at.desc()).offset(KEEP_SNAPSHOTS))]
            if old:
                c.execute(LINKS_T.delete().where(LINKS_T.c.snap_id.in_(old)))
                c.execute(COUNTS.delete().where(COUNTS.c.snap_id.in_(old)))
                c.execute(SNAPS.delete().where(SNAPS.c.id.in_(old)))

    # ---- okuma
    def snaps(self) -> list[dict[str, Any]]:
        with self.engine().connect() as c:
            return [dict(r) for r in c.execute(sa.select(SNAPS).where(SNAPS.c.tenant_id == self.seo.tenant())
                                               .order_by(SNAPS.c.taken_at.desc()).limit(2)).mappings()]

    def load(self, sid: str) -> tuple[list[dict[str, Any]], set[tuple[str, str]], dict[tuple[str, str], Optional[str]]]:
        with self.engine().connect() as c:
            counts = [dict(r) for r in c.execute(sa.select(COUNTS).where(COUNTS.c.snap_id == sid)).mappings()]
            rows = c.execute(sa.select(LINKS_T.c.target, LINKS_T.c.source, LINKS_T.c.anchor).where(LINKS_T.c.snap_id == sid)).all()
        return counts, {(t, s) for t, s, _ in rows}, {(t, s): a for t, s, a in rows}

    def books_without_links(self, targets: set[str]) -> list[dict[str, Any]]:
        from . import SALES, VIEWS, _image, _num

        tenant = self.seo.tenant()
        site = (self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        with self.engine().connect() as c:
            rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.data_json)
                             .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
                             .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)).all()
        linked = {norm_url(t) for t in targets}
        out = []
        for pid, name, data in rows:
            p = loads(data, {})
            link = p.get("SeoLink")
            if not link:
                continue
            url = f"{site}/{str(link).strip('/')}"
            if norm_url(url) not in linked:
                out.append({"id": pid, "name": name, "url": url, "image": _image(p, site), "sales": _num(p.get("CountTotalSales"))})
        return out


VIEWS_ = ("pages", "domains", "new", "lost", "books")


def register(app, ctx) -> None:
    bl = Backlinks(ctx.seo)

    @app.get("/api/v1/seo-geo/backlinks")
    def seo_backlinks(request: Request, view: str = "pages", q: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if view not in VIEWS_:
            from . import _err
            raise _err(422, "Bilinmeyen liste.")
        base = {"configured": bool(bl.key()), "setup": SETUP, "state": bl.state, "site": bl.site()}
        snaps = bl.snaps()
        if not snaps:
            return {**base, "snapshot": None, "previous": None, "summary": None, "total": 0, "start": 0, "items": []}
        cur, prev = snaps[0], (snaps[1] if len(snaps) > 1 else None)
        counts, pairs, anchors = bl.load(cur["id"])
        doms = domains(pairs)
        new: list[tuple[str, str]] = []
        lost: list[tuple[str, str]] = []
        if prev:
            pcounts, ppairs, panchors = bl.load(prev["id"])
            both = {r["target"] for r in counts if r["detailed"]} & {r["target"] for r in pcounts if r["detailed"]}
            d = diff(ppairs, pairs, both)
            new, lost = d["new"], d["lost"]
        else:
            panchors = {}
        if view == "pages":
            items: list[dict[str, Any]] = sorted(({"url": r["target"], "count": r["count"], "detailed": r["detailed"]} for r in counts),
                                                 key=lambda x: (-x["count"], x["url"]))
            key = "url"
        elif view == "domains":
            items, key = doms, "domain"
        elif view in ("new", "lost"):
            src = new if view == "new" else lost
            amap = anchors if view == "new" else panchors
            items = [{"target": t, "source": s, "domain": domain_of(s), "anchor": amap.get((t, s))} for t, s in src]
            key = "source"
        else:
            items = bl.books_without_links({r["target"] for r in counts})
            key = "name"
        if q.strip():
            needle = q.strip().casefold()
            items = [r for r in items if needle in str(r.get(key) or "").casefold() or needle in str(r.get("target") or "").casefold()]
        s = max(0, start)
        snap = lambda x: {k: (iso(v) if k == "taken_at" else v) for k, v in x.items() if k != "tenant_id"}  # noqa: E731
        return {**base, "snapshot": snap(cur), "previous": snap(prev) if prev else None,
                "summary": {"pages": len(counts), "inbound": sum(r["count"] for r in counts), "domains": len(doms),
                            "detailed": sum(1 for r in counts if r["detailed"]), "new": len(new), "lost": len(lost)},
                "total": len(items), "start": s, "items": items[s:s + max(1, limit)]}

    @app.post("/api/v1/seo-geo/backlinks/refresh")
    def seo_backlinks_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        if not bl.key():
            from . import _err
            raise _err(409, "Bing Webmaster API anahtarı girilmemiş (Yönetim → SEO & GEO).")
        started = bl.start()
        ctx.seo.audit(user, "run", "backlinks", "Gelen bağlantılar (Bing) okuması", {"started": started})
        return {"started": started, "state": bl.state}

    def nightly() -> None:
        bl.start()  # anahtar yoksa hiçbir şey yapmaz; arka planda, hemen döner

    ctx.seo.nightly.append(("backlinks", nightly))
