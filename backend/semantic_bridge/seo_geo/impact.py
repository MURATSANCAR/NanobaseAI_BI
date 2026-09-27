"""Onaylanan değişikliğin etkisi: yayına girdiği günün 28 gün öncesi ve 28 gün sonrası, Search Console ile.

Onaylanan öneri hiçbir yere gönderilmez (T-soft'a yazma yasak; hedef CRM, oradan siteye). Bu yüzden "yayına girdi"
günü bizim gönderimimiz değil, gece T-soft eşitlemesinde ürünün canlı alanlarının (SeoTitle, SeoDescription,
SearchKeywords, Details) onaylanan metinle — HTML ve boşluk farkı yok sayılarak — İLK KEZ aynı görüldüğü gündür.
Yalnız öneride gerçekten değişen alanlar karşılaştırılır.

Ölçüm: yayın günü hariç önceki 28 gün ve sonraki 28 gün; Search Console kesin verisi 3 gün geç geldiği için
sonraki pencere yayından 28+3 gün sonra ölçülür. Ürün sayfasının tıklama/gösterim/oran/sıra değerlerinin yanında
aynı pencerelerde bütün sitenin toplamı da saklanır: "site genelinde de %X değişti" karşılaştırması için.

Durumlar: bekliyor (onaylı, sitede henüz görünmüyor — tabloda satır yok) | olculuyor (yayında, pencere dolmadı ya da
ölçüm hatası) | tamam | veri_yok (iki pencerede de gösterim yok) | yenilendi (sitede görülmeden aynı ürüne daha
yeni bir öneri onaylandı; eski metin artık yayına girmeyecek, ölçülmez). Search Console'dan yalnız okunur.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlsplit

import sqlalchemy as sa
from fastapi import Request

from . import connections, propose, rules
from .opportunities import path_key
from .store import PRODUCTS, PROPOSALS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

IMPACT = sa.Table(
    "semantic_seo_impact", _md,  # onaylı önerinin sitede görüldüğü gün ve önce/sonra Search Console ölçümü
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("proposal_id", sa.String(32), primary_key=True),
    sa.Column("product_id", sa.String(40), nullable=False, index=True),
    sa.Column("url", sa.String(800)),
    sa.Column("fields", sa.String(200)),                    # "SeoTitle,SeoDescription" — yayında görülen alanlar
    sa.Column("applied_at", sa.Date),
    sa.Column("before_json", sa.Text),                      # ürün sayfası, önceki 28 gün
    sa.Column("after_json", sa.Text),                       # ürün sayfası, sonraki 28 gün
    sa.Column("control_json", sa.Text),                     # site geneli {before, after}
    sa.Column("measured_at", sa.DateTime(timezone=True)),
    sa.Column("status", sa.String(16), nullable=False),     # bekliyor | olculuyor | tamam | veri_yok
    sa.Column("error", sa.String(500)),
)

DAYS, LAG = 28, 3
STATUSES = ("bekliyor", "olculuyor", "tamam", "veri_yok", "yenilendi")

_ready: set[int] = set()
_ready_lock = threading.Lock()
_run_lock = threading.Lock()
state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "applied": 0, "measured": 0,
                         "failed": 0, "error": None}


def ensure_table(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) not in _ready:
            IMPACT.create(engine, checkfirst=True)
            _ready.add(id(engine))


# ------------------------------------------------------------------------------------------------ saf işlevler

def norm(field: str, value: Any) -> str:
    """Karşılaştırma biçimi: HTML etiketleri ve varlıklar çözülür, boşluklar teke iner; arama kelimelerinde virgül
    çevresindeki boşluk ve sıra önemsizdir."""
    text = rules.text_of(value)
    if field == "SearchKeywords":
        return ",".join(sorted(w.strip().lower() for w in text.split(",") if w.strip()))
    return text


def same(field: str, a: Any, b: Any) -> bool:
    return norm(field, a) == norm(field, b)


def changed_fields(fields: dict[str, Any], before: dict[str, Any]) -> dict[str, str]:
    """Onaylanan metinde, öneri anındaki değerden gerçekten farklı olan alanlar."""
    return {k: str(v) for k, v in fields.items()
            if k in propose.FIELDS and norm(k, v) and not same(k, v, before.get(k))}


def is_applied(live: dict[str, Any], wanted: dict[str, str]) -> bool:
    """Değişen alanların hepsi canlı kayıtta onaylanan metinle aynı mı."""
    return bool(wanted) and all(same(k, live.get(k), v) for k, v in wanted.items())


def windows(applied: date, today: date) -> dict[str, Any]:
    """Yayın günü hariç önceki ve sonraki 28 gün; sonraki pencere kesin veri gecikmesiyle ölçülebilir olunca `due`."""
    b_start, b_end = applied - timedelta(days=DAYS), applied - timedelta(days=1)
    a_start, a_end = applied + timedelta(days=1), applied + timedelta(days=DAYS)
    due_on = a_end + timedelta(days=LAG)
    return {"before": [b_start.isoformat(), b_end.isoformat()], "after": [a_start.isoformat(), a_end.isoformat()],
            "dueOn": due_on.isoformat(), "due": due_on <= today}


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Search Console satırlarının toplamı: oran tıklama/gösterim, sıra gösterim ağırlıklı ortalama."""
    clicks = sum(float(r.get("clicks") or 0) for r in rows)
    impr = sum(float(r.get("impressions") or 0) for r in rows)
    pos = sum(float(r.get("position") or 0) * float(r.get("impressions") or 0) for r in rows)
    return {"clicks": int(clicks), "impressions": int(impr), "ctr": (clicks / impr) if impr else None,
            "position": (pos / impr) if impr else None}


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or not b:
        return None
    return (a - b) / b * 100


def delta(before: Optional[dict[str, Any]], after: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Değişim: tıklama/gösterim yüzde, oran yüzde puan, sıra fark (eksi = yukarı çıktı)."""
    if not before or not after:
        return None
    ctr = (after["ctr"] - before["ctr"]) * 100 if after.get("ctr") is not None and before.get("ctr") is not None else None
    pos = (after["position"] - before["position"]) if after.get("position") is not None and before.get("position") is not None else None
    return {"clicksPct": _pct(after["clicks"], before["clicks"]), "impressionsPct": _pct(after["impressions"], before["impressions"]),
            "ctrPt": ctr, "position": pos}


def product_url(p: dict[str, Any], site: str) -> Optional[str]:
    link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or ""
    if not link:
        return None
    return str(link) if str(link).startswith("http") else f"{site.rstrip('/')}/{str(link).lstrip('/')}"


# ------------------------------------------------------------------------------------------------ Search Console

def _query(start: str, end: str, dims: list[str], filters: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while True:
        rows = connections.gsc_query(start, end, dims, start_row=len(out), filters=filters)
        out.extend(rows)
        if len(rows) < 25000:
            return out


def page_totals(url: str, start: str, end: str) -> dict[str, Any]:
    """Tek ürün sayfası. Search Console mülkünün alan adı (www, http/https) bizimkinden farklı olabildiği için yol
    parçasıyla süzülür, gelen satırlar yol anahtarı birebir aynı olanlara indirilir."""
    key = path_key(url)
    path = urlsplit(url).path.rstrip("/") or url
    rows = _query(start, end, ["page"], [{"dimension": "page", "operator": "contains", "expression": path}])
    return aggregate([r for r in rows if path_key((r.get("keys") or [""])[0]) == key])


def site_totals(start: str, end: str) -> dict[str, Any]:
    return aggregate(_query(start, end, ["date"]))


# ------------------------------------------------------------------------------------------------ iş

def detect(seo) -> int:
    """Onaylı ve henüz yayında görülmemiş önerileri canlı kayıtla karşılaştırır; aynıysa yayın günü yazılır."""
    eng, tenant = seo.engine(), seo.tenant()
    ensure_table(eng)
    site = seo.conf("SEO_SITE_URL") or "https://timas.com.tr"
    with eng.connect() as c:
        done = {r[0] for r in c.execute(sa.select(IMPACT.c.proposal_id).where(
            IMPACT.c.tenant_id == tenant, IMPACT.c.applied_at.isnot(None)))}
        rows = c.execute(sa.select(PROPOSALS.c.id, PROPOSALS.c.product_id, PROPOSALS.c.fields_json, PROPOSALS.c.before_json,
                                   PROPOSALS.c.decided_at, PRODUCTS.c.data_json, PRODUCTS.c.synced_at)
                         .select_from(PROPOSALS.join(PRODUCTS, sa.and_(PRODUCTS.c.tenant_id == PROPOSALS.c.tenant_id,
                                                                       PRODUCTS.c.product_id == PROPOSALS.c.product_id)))
                         .where(PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status == "onaylandi")).mappings().all()
    latest: dict[str, Any] = {}
    for r in rows:
        prev = latest.get(r["product_id"])
        if prev is None or (r["decided_at"] and (prev["decided_at"] is None or r["decided_at"] > prev["decided_at"])):
            latest[r["product_id"]] = r
    applied = 0
    for r in rows:
        if r["id"] in done or latest[r["product_id"]]["id"] != r["id"]:
            continue
        wanted = changed_fields(loads(r["fields_json"], {}), loads(r["before_json"], {}))
        live = loads(r["data_json"], {})
        if not is_applied(live, wanted):
            continue
        seen: datetime = r["synced_at"] or now()
        day = seen.date()
        if r["decided_at"] and r["decided_at"].date() > day:
            day = r["decided_at"].date()
        vals = dict(product_id=r["product_id"], url=product_url(live, site), fields=",".join(wanted)[:200],
                    applied_at=day, status="olculuyor", error=None)
        with eng.begin() as c:
            n = c.execute(IMPACT.update().where(IMPACT.c.tenant_id == tenant, IMPACT.c.proposal_id == r["id"])
                          .values(**vals)).rowcount
            if not n:
                c.execute(IMPACT.insert().values(tenant_id=tenant, proposal_id=r["id"], **vals))
        applied += 1
    return applied


def measure(seo, today: Optional[date] = None) -> tuple[int, int]:
    """Penceresi dolan yayındaki değişiklikleri ölçer. Hata tek satırda kalır, diğerleri sürer."""
    today = today or date.today()
    eng, tenant = seo.engine(), seo.tenant()
    ensure_table(eng)
    with eng.connect() as c:
        rows = c.execute(sa.select(IMPACT).where(IMPACT.c.tenant_id == tenant, IMPACT.c.status == "olculuyor",
                                                 IMPACT.c.applied_at.isnot(None))).mappings().all()
    control: dict[tuple[str, str], dict[str, Any]] = {}
    measured = failed = 0
    for r in rows:
        w = windows(r["applied_at"], today)
        if not w["due"]:
            continue
        try:
            if not r["url"]:
                raise ValueError("Ürünün sitedeki adresi bilinmiyor.")
            before = page_totals(r["url"], *w["before"])
            after = page_totals(r["url"], *w["after"])
            for win in (w["before"], w["after"]):
                if tuple(win) not in control:
                    control[tuple(win)] = site_totals(*win)
            ctl = {"before": control[tuple(w["before"])], "after": control[tuple(w["after"])]}
            status = "veri_yok" if not before["impressions"] and not after["impressions"] else "tamam"
            vals: dict[str, Any] = dict(before_json=dumps(before), after_json=dumps(after), control_json=dumps(ctl),
                                        measured_at=now(), status=status, error=None)
            measured += 1
        except Exception as e:  # noqa: BLE001 — satır başına hata; ekranda gösterilir, sonraki gece yeniden denenir
            log.warning("seo impact measure %s failed: %s", r["proposal_id"], e)
            vals = dict(error=str(e)[:500], measured_at=now())
            failed += 1
        with eng.begin() as c:
            c.execute(IMPACT.update().where(IMPACT.c.tenant_id == tenant, IMPACT.c.proposal_id == r["proposal_id"]).values(**vals))
    return measured, failed


def run(seo) -> dict[str, Any]:
    """Algılama her zaman; ölçüm yalnız Google bağlıysa. Aynı anda ikinci tur başlamaz."""
    if not _run_lock.acquire(blocking=False):
        return {"started": False}
    state.update(running=True, startedAt=iso(now()), finishedAt=None, applied=0, measured=0, failed=0, error=None)
    try:
        state["applied"] = detect(seo)
        if connections.service_account_email():
            state["measured"], state["failed"] = measure(seo)
        return {"started": True, **state}
    except Exception as e:  # noqa: BLE001
        state["error"] = str(e)[:500]
        log.exception("seo impact run failed")
        raise
    finally:
        state.update(running=False, finishedAt=iso(now()))
        _run_lock.release()


# ------------------------------------------------------------------------------------------------ uçlar

def _item(r: dict[str, Any], site: str) -> dict[str, Any]:
    fields = loads(r["fields_json"], {})
    before_fields = loads(r["before_json"], {})
    status = r["impact_status"] or r.get("computed_status") or "bekliyor"
    before, after = loads(r["before_m"], None), loads(r["after_m"], None)
    ctl = loads(r["control_json"], None)
    d = delta(before, after)
    cd = delta(ctl.get("before"), ctl.get("after")) if ctl else None
    net = (d["clicksPct"] - cd["clicksPct"]) if d and cd and d["clicksPct"] is not None and cd["clicksPct"] is not None else None
    live = loads(r["data_json"], {}) if r["data_json"] else {}
    applied = r["applied_at"]
    return {"proposalId": r["id"], "productId": r["product_id"], "productName": r["name"],
            "url": r["url"] or product_url(live, site),
            "fields": r["fields"].split(",") if r["fields"] else list(changed_fields(fields, before_fields)),
            "decidedAt": iso(r["decided_at"]), "decidedBy": r["decided_by"],
            "appliedAt": applied.isoformat() if applied else None, "status": status,
            "windows": windows(applied, date.today()) if applied else None,
            "measuredAt": iso(r["measured_at"]), "error": r["error"],
            "before": before, "after": after, "delta": d,
            "control": {"before": ctl.get("before"), "after": ctl.get("after"), "delta": cd} if ctl else None,
            "netClicksPct": net}


def register(app, ctx) -> None:
    seo = ctx.seo

    def nightly() -> None:
        out = run(seo)
        log.info("seo impact nightly: %s", out)

    seo.nightly.append(("impact", nightly))

    newer = PROPOSALS.alias("newer")

    def _status():
        # Sabit satır içi yazılır: bağ parametresi olsa GROUP BY ifadesi SELECT ile eşleşmez (PostgreSQL).
        # Sitede görülmeden yerine daha yeni onay gelen öneri "yenilendi": eski metin artık yayına girmeyecek.
        superseded = sa.exists().where(newer.c.tenant_id == PROPOSALS.c.tenant_id, newer.c.product_id == PROPOSALS.c.product_id,
                                       newer.c.status == "onaylandi", newer.c.decided_at > PROPOSALS.c.decided_at)
        return sa.func.coalesce(IMPACT.c.status, sa.case((superseded, sa.literal_column("'yenilendi'")),
                                                         else_=sa.literal_column("'bekliyor'")))

    def _join():
        return (PROPOSALS
                .outerjoin(PRODUCTS, sa.and_(PRODUCTS.c.tenant_id == PROPOSALS.c.tenant_id,
                                             PRODUCTS.c.product_id == PROPOSALS.c.product_id))
                .outerjoin(IMPACT, sa.and_(IMPACT.c.tenant_id == PROPOSALS.c.tenant_id,
                                           IMPACT.c.proposal_id == PROPOSALS.c.id)))

    @app.get("/api/v1/seo-geo/impact")
    def seo_impact(request: Request, status: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        eng, tenant = seo.engine(), seo.tenant()
        ensure_table(eng)
        site = seo.conf("SEO_SITE_URL") or "https://timas.com.tr"
        # Sayfa önerileri ("model:12") bu ölçüme girmez: canlı değerleri ürün kaydında değil.
        base = [PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status == "onaylandi", ~PROPOSALS.c.product_id.contains(":")]
        cond = list(base)
        if status in STATUSES:
            cond.append(_status() == status)
        with eng.connect() as c:
            counts = dict(c.execute(sa.select(_status(), sa.func.count()).select_from(_join()).where(*base)
                                    .group_by(_status())).all())
            total = c.execute(sa.select(sa.func.count()).select_from(_join()).where(*cond)).scalar() or 0
            rows = c.execute(
                sa.select(PROPOSALS.c.id, PROPOSALS.c.product_id, PROPOSALS.c.fields_json, PROPOSALS.c.before_json,
                          PROPOSALS.c.decided_at, PROPOSALS.c.decided_by, PRODUCTS.c.name, PRODUCTS.c.data_json,
                          IMPACT.c.status.label("impact_status"), IMPACT.c.url, IMPACT.c.fields, IMPACT.c.applied_at,
                          IMPACT.c.before_json.label("before_m"), IMPACT.c.after_json.label("after_m"),
                          IMPACT.c.control_json, IMPACT.c.measured_at, IMPACT.c.error, _status().label("computed_status"))
                .select_from(_join()).where(*cond)
                .order_by(IMPACT.c.applied_at.desc().nullslast(), PROPOSALS.c.decided_at.desc().nullslast(), PROPOSALS.c.id)
                .offset(max(0, start)).limit(max(1, limit))).mappings().all()
        return {"total": total, "start": start, "items": [_item(dict(r), site) for r in rows],
                "summary": {"counts": {s: counts.get(s, 0) for s in STATUSES},
                            "connected": bool(connections.service_account_email()),
                            "windowDays": DAYS, "lagDays": LAG, "state": state}}

    @app.post("/api/v1/seo-geo/impact/run")
    def seo_impact_run(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        if state["running"]:
            return {"started": False, "state": state}

        def job() -> None:
            try:
                run(seo)
            except Exception:  # noqa: BLE001 — hata state.error'da
                pass

        threading.Thread(target=job, name="seo-impact", daemon=True).start()
        seo.audit(user, "run", "impact", "Değişiklik etkisi ölçümü", {"connected": bool(connections.service_account_email())})
        return {"started": True, "state": state}
