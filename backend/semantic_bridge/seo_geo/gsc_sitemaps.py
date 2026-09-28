"""Search Console'a gönderilmiş site haritalarının Google tarafındaki durumu (hata, uyarı, son okuma).

Kaynak: Search Console API `sites/{site}/sitemaps` (salt okuma, `webmasters.readonly`). Dizin haritası (sitemap
index) ise alt haritaları `sitemapIndex=` ile ayrıca listelenir. Google hata/uyarı SAYISINI verir, metnini vermez;
ayrıntı Search Console'un site haritaları ekranındadır (ekrandaki bağlantı oraya gider).

Sürekli çekilir: `REFRESH_HOURS`'ta bir arka planda (süreç içi döngü), gece işinde ve ekran açıldığında son okuma
eskiyse. Her okuma harita başına bir geçmiş satırı yazar; hata/uyarı artışı iş listesine düşer (`worklist.src_gsc_sitemaps`).
Siteye ya da Search Console'a hiçbir şey yazılmaz (harita gönderme/silme çağrısı yok).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

import sqlalchemy as sa
from fastapi import HTTPException, Request

from .store import _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

API = "https://www.googleapis.com/webmasters/v3/sites/{site}/sitemaps"
#: Arka plan okuma aralığı; ekran açıldığında da bu kadar eskiyse yeniden okunur.
REFRESH_HOURS = 6
#: Google bu kadar gündür okumadıysa harita «okunmuyor» sayılır (az değişen blog haritası 1–2 haftada bir okunur).
STALE_DOWNLOAD_DAYS = 14
#: Bu kadar gündür okunmayan harita eski siteden kalmış kayıttır (2026-09-28 canlıda 2020 WordPress haritaları
#: duruyordu); hata/uyarısı güncel sorun sayılmaz, iş «Search Console'dan kaldırın» olur.
OBSOLETE_DAYS = 365

SNAP = sa.Table(
    "semantic_seo_gsc_sitemaps", _md,  # son okuma: haritalar + özet
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("error", sa.String(500)),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)
HIST = sa.Table(
    "semantic_seo_gsc_sitemaps_hist", _md,  # her okumada harita başına sayılar (artışı görmek için)
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("path", sa.String(800), nullable=False, index=True),
    sa.Column("errors", sa.Integer, nullable=False, default=0),
    sa.Column("warnings", sa.Integer, nullable=False, default=0),
    sa.Column("submitted", sa.Integer),
    sa.Column("last_downloaded", sa.DateTime(timezone=True)),
    sa.Column("read_at", sa.DateTime(timezone=True), nullable=False, index=True),
)
_ready: set[int] = set()


def _ensure(eng: sa.engine.Engine) -> None:
    if id(eng) in _ready:
        return
    for t in (SNAP, HIST):
        t.create(eng, checkfirst=True)
    _ready.add(id(eng))


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def parse_entry(e: dict[str, Any], parent: Optional[str] = None) -> dict[str, Any]:
    """API satırı → düz kayıt. Sayılar API'de metin gelir."""
    contents = [{"type": c.get("type"), "submitted": _int(c.get("submitted"))} for c in e.get("contents") or []]
    return {"path": e.get("path") or "", "parent": parent, "type": e.get("type"),
            "isIndex": bool(e.get("isSitemapsIndex")), "isPending": bool(e.get("isPending")),
            "lastSubmitted": e.get("lastSubmitted"), "lastDownloaded": e.get("lastDownloaded"),
            "errors": _int(e.get("errors")), "warnings": _int(e.get("warnings")),
            "submitted": sum(c["submitted"] for c in contents) if contents else None, "contents": contents}


def flags(m: dict[str, Any], at: Optional[datetime] = None) -> list[str]:
    """Haritanın sorunları: eski | hata | uyari | okunmuyor | bekliyor. «eski» tek başına döner."""
    at = at or datetime.now(timezone.utc)
    last = _dt(m.get("lastDownloaded"))
    if not m.get("isPending") and last is not None and at - last > timedelta(days=OBSOLETE_DAYS):
        return ["eski"]
    out = []
    if m.get("errors"):
        out.append("hata")
    if m.get("warnings"):
        out.append("uyari")
    if m.get("isPending"):
        out.append("bekliyor")
    elif last is None or at - last > timedelta(days=STALE_DOWNLOAD_DAYS):
        out.append("okunmuyor")
    return out


def summarize(maps: list[dict[str, Any]], at: Optional[datetime] = None) -> dict[str, Any]:
    """Dizin haritası kendi sayısını alt haritalardan toplar; toplamda yalnız yaprak haritalar sayılır."""
    for m in maps:
        m["flags"] = flags(m, at)
    live = [m for m in maps if "eski" not in m["flags"]]
    leaves = [m for m in live if not m.get("isIndex")] or live
    return {"sitemaps": len(maps), "errors": sum(m["errors"] for m in leaves),
            "warnings": sum(m["warnings"] for m in leaves),
            "submitted": sum(m["submitted"] or 0 for m in leaves),
            "obsolete": sum(1 for m in maps if "eski" in m["flags"]),
            "withErrors": sum(1 for m in maps if "hata" in m["flags"]),
            "withWarnings": sum(1 for m in maps if "uyari" in m["flags"]),
            "notRead": sum(1 for m in maps if "okunmuyor" in m["flags"])}


def deltas(maps: list[dict[str, Any]], prev: dict[str, tuple[int, int]]) -> None:
    """Önceki okumaya göre hata/uyarı farkı (ilk okumada None)."""
    for m in maps:
        p = prev.get(m["path"])
        m["errorsDelta"] = None if p is None else m["errors"] - p[0]
        m["warningsDelta"] = None if p is None else m["warnings"] - p[1]


def fetch(site: str) -> list[dict[str, Any]]:
    """Gönderilmiş haritalar + dizin haritalarının alt haritaları (bir kat)."""
    from . import connections

    url = API.format(site=quote(site, safe=""))
    top = connections._google("GET", url).get("sitemap") or []
    out = [parse_entry(e) for e in top]
    for m in list(out):
        if m["isIndex"]:
            kids = connections._google("GET", f"{url}?sitemapIndex={quote(m['path'], safe='')}").get("sitemap") or []
            seen = {x["path"] for x in out}
            out.extend(parse_entry(k, parent=m["path"]) for k in kids if k.get("path") not in seen)
    return out


def gsc_link(site: str) -> str:
    return f"https://search.google.com/search-console/sitemaps?resource_id={quote(site, safe='')}"


def register(app, ctx) -> None:
    seo = ctx.seo
    lock = threading.Lock()
    state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None}

    def eng() -> sa.engine.Engine:
        e = seo.engine()
        _ensure(e)
        return e

    def site() -> str:
        return (seo.conf("GSC_SITE") or "").strip()

    def read_snap() -> Optional[dict[str, Any]]:
        with eng().connect() as c:
            r = c.execute(sa.select(SNAP.c.data_json, SNAP.c.error, SNAP.c.saved_at)
                          .where(SNAP.c.tenant_id == seo.tenant())).first()
        if not r:
            return None
        return {**loads(r[0], {}), "error": r[1], "savedAt": iso(r[2]), "_at": r[2]}

    def previous() -> dict[str, tuple[int, int]]:
        """Her haritanın bir önceki okumadaki sayıları."""
        tenant = seo.tenant()
        with eng().connect() as c:
            last = c.execute(sa.select(sa.func.max(HIST.c.read_at)).where(HIST.c.tenant_id == tenant)).scalar()
            if last is None:
                return {}
            rows = c.execute(sa.select(HIST.c.path, HIST.c.errors, HIST.c.warnings)
                             .where(HIST.c.tenant_id == tenant, HIST.c.read_at == last)).all()
        return {r[0]: (int(r[1]), int(r[2])) for r in rows}

    def refresh() -> dict[str, Any]:
        s = site()
        if not s:
            raise RuntimeError("Search Console mülkü (GSC_SITE) girilmemiş.")
        tenant, at = seo.tenant(), now()
        try:
            maps = fetch(s)
        except Exception as e:  # noqa: BLE001 — okuma hatası son okumanın yanına yazılır, eski veri silinmez
            with eng().begin() as c:
                n = c.execute(SNAP.update().where(SNAP.c.tenant_id == tenant)
                              .values(error=str(e)[:500])).rowcount
                if not n:
                    c.execute(SNAP.insert().values(tenant_id=tenant, data_json=dumps({"sitemaps": [], "summary": {}}),
                                                   error=str(e)[:500], saved_at=at))
            raise
        deltas(maps, previous())
        data = {"site": s, "link": gsc_link(s), "summary": summarize(maps, at), "sitemaps": maps}
        with eng().begin() as c:
            c.execute(SNAP.delete().where(SNAP.c.tenant_id == tenant))
            c.execute(SNAP.insert().values(tenant_id=tenant, data_json=dumps(data), error=None, saved_at=at))
            for m in maps:
                c.execute(HIST.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, path=m["path"][:800],
                                               errors=m["errors"], warnings=m["warnings"], submitted=m["submitted"],
                                               last_downloaded=_dt(m["lastDownloaded"]), read_at=at))
        return data

    def start() -> bool:
        with lock:
            if state["running"]:
                return False
            state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)

        def run() -> None:
            try:
                refresh()
            except Exception as e:  # noqa: BLE001
                state["error"] = str(e)[:500]
                log.warning("gsc sitemaps: %s", e)
            finally:
                state.update(running=False, finishedAt=iso(now()))

        threading.Thread(target=run, name="seo-gsc-sitemaps", daemon=True).start()
        return True

    def stale(snap: Optional[dict[str, Any]]) -> bool:
        at = snap.get("_at") if snap else None
        if at is None:
            return True
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return now() - at > timedelta(hours=REFRESH_HOURS)

    def loop() -> None:
        """Süreç açık kaldıkça REFRESH_HOURS'ta bir; son okuma tazeyse (başka süreç okuduysa) atlanır."""
        time.sleep(120)
        while True:
            try:
                if site() and stale(read_snap()):
                    start()
            except Exception as e:  # noqa: BLE001
                log.warning("gsc sitemaps döngüsü: %s", e)
            time.sleep(1800)

    threading.Thread(target=loop, name="seo-gsc-sitemaps-loop", daemon=True).start()

    @app.get("/api/v1/seo-geo/gsc-sitemaps")
    def seo_gsc_sitemaps(request: Request) -> dict[str, Any]:
        ctx.gate(request)
        snap = read_snap()
        if site() and stale(snap):
            start()
        if snap:
            snap.pop("_at", None)
        return {"configured": bool(site()), "snapshot": snap, "state": state,
                "refreshHours": REFRESH_HOURS, "staleDays": STALE_DOWNLOAD_DAYS}

    @app.post("/api/v1/seo-geo/gsc-sitemaps/refresh")
    def seo_gsc_sitemaps_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        if not site():
            raise HTTPException(409, "Search Console mülkü girilmemiş (Yönetim → SEO & GEO).")
        started = start()
        seo.audit(user, "run", "gsc-sitemaps", "Search Console site haritası okuması", {"started": started})
        return {"started": started, "state": state}

    def nightly() -> None:
        if site():
            start()

    seo.nightly.append(("gsc_sitemaps", nightly))
