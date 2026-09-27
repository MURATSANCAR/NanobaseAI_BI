"""M10 İlk baskı ekranının uçları: /api/v1/management/first-print/*.

Veri, günlük hazırlanan `ilk-baski` raporunun önbelleğinden okunur (Logo'ya ve CRM'e bu uçlardan gidilmez).
Anlık tahmin (kitap seçimi, yayın ayı değişikliği, kayıtta olmayan kitap) önbellekteki veri kümesiyle bellekte hesaplanır.

Karar kaydı: önerilen ilk baskı adedi bir karara dönüşür; satış ve üretim onayı iki ayrı kişiden gelir
(«ilk baskı onayı» açıkça verilen yetki). Onaylanan karar üretim modülünün okuyacağı kayıttır; CRM'e ya da Logo'ya
yazılmaz.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import sqlalchemy as sa
from fastapi import HTTPException, Request

from semantic_bridge.management import ilk_baski as IB
from semantic_bridge.management import ilk_baski_model as M

log = logging.getLogger(__name__)
PREFIX = "/api/v1/management/first-print"
FEATURE_DECIDE = "ozellik:ilk-baski.karar"
FEATURE_APPROVE = "ozellik:ilk-baski.onay"
ROLES = {"satis": "Satış", "uretim": "Üretim"}
SCENARIO_IDS = {s[0] for s in M.SCENARIOS} | {"oneri", "elle"}

_md = sa.MetaData()
DECISIONS = sa.Table(
    "semantic_first_print_decisions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("stock_code", sa.String(60), index=True),
    sa.Column("title", sa.String(400), nullable=False),
    sa.Column("launch", sa.String(7)),
    sa.Column("units", sa.Integer, nullable=False),
    sa.Column("scenario", sa.String(16), nullable=False),
    sa.Column("recommended", sa.Integer),
    sa.Column("forecast_json", sa.Text, nullable=False, default="{}"),
    sa.Column("note", sa.Text),
    sa.Column("status", sa.String(16), nullable=False),  # bekliyor · onaylandi · geri_cekildi
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("sales_by", sa.String(120)),
    sa.Column("sales_at", sa.DateTime(timezone=True)),
    sa.Column("production_by", sa.String(120)),
    sa.Column("production_at", sa.DateTime(timezone=True)),
    sa.Column("closed_by", sa.String(120)),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
)
_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) not in _ready:
            _md.create_all(engine, checkfirst=True)
            _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> str | None:
    return v.isoformat() if v else None


def decision_row(r: Any) -> dict:
    return {"id": r.id, "code": r.stock_code, "title": r.title, "launch": r.launch, "units": r.units,
            "scenario": r.scenario, "recommended": r.recommended, "note": r.note, "status": r.status,
            "createdBy": r.created_by, "createdAt": _iso(r.created_at),
            "approvals": {"satis": {"by": r.sales_by, "at": _iso(r.sales_at)} if r.sales_by else None,
                          "uretim": {"by": r.production_by, "at": _iso(r.production_at)} if r.production_by else None},
            "closedBy": r.closed_by, "closedAt": _iso(r.closed_at),
            "forecast": json.loads(r.forecast_json or "{}")}


class DecisionError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def create_decision(engine, tenant: str, user: str, body: dict) -> dict:
    title = str(body.get("title") or "").strip()
    code = str(body.get("code") or "").strip() or None
    try:
        units = int(body.get("units"))
    except (TypeError, ValueError):
        raise DecisionError("Baskı adedi sayı olmalı.") from None
    if units <= 0:
        raise DecisionError("Baskı adedi sıfırdan büyük olmalı.")
    if not title:
        raise DecisionError("Kitap adı gerekli.")
    scenario = str(body.get("scenario") or "elle")
    if scenario not in SCENARIO_IDS:
        raise DecisionError("Bilinmeyen senaryo.")
    launch = str(body.get("launch") or "")[:7] or None
    rec = body.get("recommended")
    with engine.begin() as c:
        if code:
            open_ = c.execute(sa.select(DECISIONS.c.id).where(
                DECISIONS.c.tenant_id == tenant, DECISIONS.c.stock_code == code,
                DECISIONS.c.status == "bekliyor")).first()
            if open_:
                raise DecisionError("Bu kitap için onay bekleyen bir karar var; önce onu sonuçlandırın ya da geri çekin.", 409)
        did = uuid.uuid4().hex
        c.execute(DECISIONS.insert().values(
            id=did, tenant_id=tenant, stock_code=code, title=title[:400], launch=launch, units=units, scenario=scenario,
            recommended=int(rec) if isinstance(rec, (int, float)) else None,
            forecast_json=json.dumps(body.get("forecast") or {}, ensure_ascii=False)[:20000],
            note=(str(body.get("note") or "").strip() or None), status="bekliyor", created_by=user, created_at=_now()))
        return decision_row(c.execute(sa.select(DECISIONS).where(DECISIONS.c.id == did)).one())


def approve(engine, tenant: str, user: str, did: str, role: str) -> dict:
    if role not in ROLES:
        raise DecisionError("Onay türü satış ya da üretim olmalı.")
    with engine.begin() as c:
        r = c.execute(sa.select(DECISIONS).where(DECISIONS.c.id == did, DECISIONS.c.tenant_id == tenant)).first()
        if r is None:
            raise DecisionError("Karar bulunamadı.", 404)
        if r.status != "bekliyor":
            raise DecisionError("Bu karar artık onay beklemiyor.", 409)
        by, other = (r.sales_by, r.production_by) if role == "satis" else (r.production_by, r.sales_by)
        if by:
            raise DecisionError(f"{ROLES[role]} onayı zaten verilmiş.", 409)
        if other and other.lower() == user.lower():
            raise DecisionError("İki onay iki ayrı kişiden gelmeli; diğer onayı siz verdiniz.", 409)
        vals: dict[str, Any] = {"sales_by": user, "sales_at": _now()} if role == "satis" else \
            {"production_by": user, "production_at": _now()}
        if other:
            vals["status"] = "onaylandi"
        c.execute(DECISIONS.update().where(DECISIONS.c.id == did).values(**vals))
        return decision_row(c.execute(sa.select(DECISIONS).where(DECISIONS.c.id == did)).one())


def withdraw(engine, tenant: str, user: str, admin: bool, did: str) -> dict:
    with engine.begin() as c:
        r = c.execute(sa.select(DECISIONS).where(DECISIONS.c.id == did, DECISIONS.c.tenant_id == tenant)).first()
        if r is None:
            raise DecisionError("Karar bulunamadı.", 404)
        if r.status != "bekliyor":
            raise DecisionError("Onaylanmış ya da geri çekilmiş karar değiştirilemez.", 409)
        if r.created_by.lower() != user.lower() and not admin:
            raise DecisionError("Kararı yalnız öneren ya da yönetici geri çekebilir.", 403)
        c.execute(DECISIONS.update().where(DECISIONS.c.id == did).values(status="geri_cekildi", closed_by=user, closed_at=_now()))
        return decision_row(c.execute(sa.select(DECISIONS).where(DECISIONS.c.id == did)).one())


def list_decisions(engine, tenant: str, code: str | None = None, status: str | None = None) -> list[dict]:
    q = sa.select(DECISIONS).where(DECISIONS.c.tenant_id == tenant)
    if code:
        q = q.where(DECISIONS.c.stock_code == code)
    if status:
        q = q.where(DECISIONS.c.status == status)
    with engine.connect() as c:
        return [decision_row(r) for r in c.execute(q.order_by(DECISIONS.c.created_at.desc()))]


# ---------------------------------------------------------------- önbellekteki model

class Store:
    """Raporun son sonucunu ve veri kümesini dosyalar değiştikçe bir kez yükler (bellekte tutar)."""

    def __init__(self, reports):
        self.reports = reports
        self._keys: dict[str, tuple] = {}
        self._snap: dict = {}
        self._eng: IB.Engine | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _stamp(path) -> tuple | None:
        try:
            st = os.stat(path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def load(self) -> tuple[dict, IB.Engine | None]:
        snap_path = self.reports.path(IB.REPORT_ID)
        model_path = snap_path.with_name(IB.MODEL_FILE)
        with self._lock:
            k = self._stamp(snap_path)
            if k and k != self._keys.get("snap"):
                try:
                    self._snap = json.loads(snap_path.read_text())
                    self._keys["snap"] = k
                except (OSError, ValueError):
                    pass
            k = self._stamp(model_path)
            if k and k != self._keys.get("model"):
                try:
                    self._eng = IB.engine_from(json.loads(model_path.read_text()))
                    self._keys["model"] = k
                except (OSError, ValueError, KeyError) as e:
                    log.warning("first print model unreadable: %s", e)
            return self._snap, self._eng


def _month(v: Any) -> int | None:
    s = str(v or "")
    if len(s) >= 7 and s[:4].isdigit() and s[5:7].isdigit() and 1 <= int(s[5:7]) <= 12:
        return M.mi(s[:4], s[5:7])
    return None


def book_forecast(eng: IB.Engine, code: str, launch: int | None = None, emsal: list[str] | None = None) -> dict:
    ds = eng.ds
    b = ds.books.get(code)
    if b is None:
        raise HTTPException(404, {"code": "NOT_FOUND", "message": "Bu stok kodunda kitap kartı yok."})
    launched = code in ds.outcomes
    if launch is None:
        launch = b.launch if launched else max(M.month_of(b.first_pub) or ds.end + 1, ds.end + 1)
    # Çıkmış kitapta tahmin lansmandan GAP ay önceki veriyle kurulur (o gün verilecek karar); sonrası gerçekleşendir.
    cutoff = launch - IB.GAP if launched and launch == b.launch else ds.end
    out = eng.full(b, launch, emsal=emsal, cutoff=cutoff)
    if out is None:
        raise HTTPException(422, {"code": "NO_ANALOG", "message": "Bu kitap için emsal bulunamadı."})
    if launched and launch == b.launch:
        o = ds.outcomes[code]
        run, cum = 0.0, []
        for j, q in enumerate(o.months):
            run += q
            cum.append({"month": M.ms(launch + j), "label": M.month_name(launch + j), "units": round(q), "cum": round(run)})
        out["actual"] = cum
        out["revised"] = {str(h): (round(v) if (v := M.revise(ds, fc, o.months[:h], h)) is not None else None)
                          for h in IB.HORIZONS if (fc := eng.raw(b, launch, cutoff, h, emsal)) is not None}
        out["mode"] = "launched"
    else:
        out["mode"] = "upcoming"
    out["emsalCrm"] = ds.emsal.get(code, [])
    out["emsalOverride"] = emsal is not None
    return out


def free_forecast(eng: IB.Engine, body: dict) -> dict:
    ds = eng.ds
    b = M.Book(code=str(body.get("code") or "_yeni"), name=str(body.get("name") or "Yeni kitap").strip()[:300],
               publisher=str(body.get("publisher") or ""), library=str(body.get("library") or ""),
               series=str(body.get("series") or ""), authors_text=str(body.get("authors") or ""),
               audience=str(body.get("audience") or ""), genre_text=str(body.get("genre") or ""),
               pages=M.num(body.get("pages")), price=M.num(body.get("price"))).finish()
    launch = _month(body.get("launch")) or ds.end + 1
    if launch <= ds.end:
        raise HTTPException(400, {"code": "BAD_LAUNCH", "message": "Yayın ayı, verinin son ayından sonra olmalı."})
    emsal = [str(x).strip() for x in (body.get("emsal") or []) if str(x).strip() in ds.books]
    out = eng.full(b, launch, emsal=emsal)
    if out is None:
        raise HTTPException(422, {"code": "NO_ANALOG", "message": "Bu özelliklerle emsal bulunamadı."})
    out["mode"] = "free"
    return out


def register(app, runtime: Callable, gate: Callable[[Request], str], reports) -> Store:
    store = Store(reports)

    def ready() -> tuple[dict, IB.Engine]:
        snap, eng = store.load()
        if eng is None:
            if not snap.get("error"):
                reports.start_refresh(IB.REPORT_ID)
            raise HTTPException(503, {"code": "NOT_READY", "message": snap.get("error") or
                                      "İlk baskı tahmini hazırlanıyor: Logo'dan 2015'ten bu yana satış okunuyor "
                                      "(yaklaşık 15 dakika). Sayfa hazır olunca kendiliğinden dolar."})
        return snap, eng

    def db():
        engine = runtime().store.engine
        ensure(engine)
        return engine, runtime().settings.tenant_id

    def fail(e: DecisionError):
        raise HTTPException(e.status, {"code": "DECISION", "message": str(e)})

    def can(user: str, key: str) -> bool:
        from semantic_bridge import access
        return access.user_can(user, key)

    @app.get(PREFIX + "/summary")
    def fp_summary(request: Request) -> dict[str, Any]:
        user = gate(request)
        status = reports.read(IB.REPORT_ID, with_data=False)
        snap, eng = store.load()
        data = (snap or {}).get("data") or {}
        if not data and not status.get("refreshing") and not status.get("error"):
            reports.start_refresh(IB.REPORT_ID)
            status = reports.read(IB.REPORT_ID, with_data=False)
        return {
            "status": {k: status.get(k) for k in ("updatedAt", "refreshing", "error", "nextRefreshAt", "durationMs",
                                                   "refreshStartedAt", "hasData")},
            "ready": bool(data),
            "meta": {k: data.get(k) for k in ("asOf", "dataEnd", "lastFullMonth", "counts", "levelNote", "warnings")},
            "backtest": data.get("backtest"), "upcoming": data.get("upcoming") or [], "tracking": data.get("tracking") or [],
            "formulas": [{"name": n, "text": t} for n, t in IB.FORMULAS], "notes": IB.NOTES,
            "sources": [{"id": sid, "connection": conn, "title": title, "description": desc,
                         "sql": ((data.get("sourceStats") or {}).get(sid) or {}).get("sql") or _sql(sid),
                         "rows": ((data.get("sourceStats") or {}).get(sid) or {}).get("rows")}
                        for sid, conn, title, desc in IB.SOURCES],
            "can": {"decide": can(user, FEATURE_DECIDE), "approve": can(user, FEATURE_APPROVE)},
        }

    def _sql(sid: str) -> str:
        from semantic_bridge.management import sql_text
        try:
            return sql_text(IB.REPORT_ID, sid)
        except OSError:
            return ""

    @app.get(PREFIX + "/books")
    def fp_books(request: Request, q: str = "") -> dict[str, Any]:
        gate(request)
        _, eng = ready()
        needle = M.norm(q)
        if len(needle) < 2:
            return {"items": [], "total": 0}
        words = needle.split()
        items = []
        for b in eng.ds.books.values():
            if not M.is_book(b.code):  # set, dergi, e-kitap, ticari ürün: ilk baskı tahmini yalnız kitap
                continue
            hay = M.norm(f"{b.code} {b.name} {b.authors_text} {b.publisher}")
            if all(w in hay for w in words):
                items.append({"code": b.code, "name": b.name, "authors": b.authors_text or None,
                              "publisher": b.publisher or None, "firstPub": b.first_pub,
                              "launched": b.code in eng.ds.outcomes})
        items.sort(key=lambda x: (not M.norm(x["name"]).startswith(words[0]), x["name"]))
        return {"items": items, "total": len(items)}

    @app.get(PREFIX + "/options")
    def fp_options(request: Request) -> dict[str, Any]:
        """Serbest giriş formunun seçenekleri (CRM'de geçen değerler, kullanım sıklığına göre)."""
        gate(request)
        _, eng = ready()
        from collections import Counter
        cnt = {k: Counter() for k in ("publisher", "library", "series", "audience")}
        for b in eng.ds.books.values():
            for k, v in (("publisher", b.publisher), ("library", b.library), ("series", b.series), ("audience", b.audience)):
                if v:
                    cnt[k][v] += 1
        return {k: [v for v, _ in c.most_common()] for k, c in cnt.items()} | {"lastFullMonth": M.ms(eng.ds.end)}

    @app.get(PREFIX + "/forecast/{code}")
    def fp_forecast(code: str, request: Request, launch: str | None = None, emsal: str | None = None) -> dict[str, Any]:
        gate(request)
        _, eng = ready()
        em = [x for x in (emsal or "").split(",") if x.strip()] if emsal is not None else None
        return book_forecast(eng, code, _month(launch), em)

    @app.post(PREFIX + "/forecast")
    async def fp_free(request: Request) -> dict[str, Any]:
        gate(request)
        _, eng = ready()
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, {"code": "BAD_REQUEST", "message": "Geçersiz istek."})
        return free_forecast(eng, body)

    @app.get(PREFIX + "/decisions")
    def fp_decisions(request: Request, code: str | None = None, status: str | None = None) -> dict[str, Any]:
        gate(request)
        engine, tenant = db()
        return {"items": list_decisions(engine, tenant, code, status)}

    @app.post(PREFIX + "/decisions")
    async def fp_decide(request: Request) -> dict[str, Any]:
        user = gate(request)
        engine, tenant = db()
        body = await request.json()
        try:
            out = create_decision(engine, tenant, user, body if isinstance(body, dict) else {})
        except DecisionError as e:
            fail(e)
        _audit(engine, user, "create", out)
        return out

    @app.post(PREFIX + "/decisions/{did}/approve")
    async def fp_approve(did: str, request: Request) -> dict[str, Any]:
        user = gate(request)
        if not can(user, FEATURE_APPROVE):
            raise HTTPException(403, {"code": "FORBIDDEN", "message": "İlk baskı onayı için yetkiniz yok."})
        engine, tenant = db()
        body = await request.json()
        try:
            out = approve(engine, tenant, user, did, str((body or {}).get("role") or ""))
        except DecisionError as e:
            fail(e)
        _audit(engine, user, "approve", out)
        return out

    @app.post(PREFIX + "/decisions/{did}/withdraw")
    def fp_withdraw(did: str, request: Request) -> dict[str, Any]:
        user = gate(request)
        engine, tenant = db()
        from semantic_bridge import admin as admin_mod
        try:
            out = withdraw(engine, tenant, user, admin_mod.is_admin(user), did)
        except DecisionError as e:
            fail(e)
        _audit(engine, user, "withdraw", out)
        return out

    def _audit(engine, user: str, action: str, d: dict) -> None:
        try:
            from semantic_bridge import admin as admin_mod
            admin_mod.audit(engine, user, action, "first_print", d["id"], d["title"],
                            {"units": d["units"], "status": d["status"], "code": d["code"]})
        except Exception:  # noqa: BLE001 — kayıt düşmesi işlemi geri almaz
            log.exception("first print audit failed")

    return store
