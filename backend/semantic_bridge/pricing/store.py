"""M9 kayıtları: fiyat analizleri, onaylar, elle girilen rakip/pazar fiyatları, varsayılanlar, backlist zam teklifleri.

Hepsi kendi tablolarımızda (`semantic_pricing_*`). CRM'e, Logo'ya ve e-ticarete yazılmaz: onaylanan kapak fiyatı
CRM kitap kartına ayrıca girilir (ekran bunu söyler).

Onay akışı (iş tanımı):
- **Aşama 1 — tahmini fiyat** (kabul kararından sonra, emsalle): Mali İşler + Satış.
- **Aşama 2 — kesin fiyat** (kesin sayfa sayısı ve teknik özellikler gelince): Mali İşler + Satış + Pazarlama + Üst Yönetim.
Her imza açıkça verilen bir yetki ister (`ozellik:fiyatlama.onay-<rol>`). Analizi hazırlayan onaylayamaz; bir kişi
aynı analizde tek rol adına imza atar. Onaya gönderilen analizin sonucu dondurulur (`result_json`); imzalar o sürüme
aittir. Analiz yeniden düzenlenirse (taslağa dönerse) imzalar düşer, sürüm artar.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import sqlalchemy as sa

_md = sa.MetaData()

STAGES = {"tahmini": "Aşama 1 · Tahmini fiyat", "kesin": "Aşama 2 · Kesin fiyat"}
APPROVERS = {
    "mali": "Mali İşler",
    "satis": "Satış",
    "pazarlama": "Pazarlama",
    "yonetim": "Üst Yönetim",
}
REQUIRED = {"tahmini": ("mali", "satis"), "kesin": ("mali", "satis", "pazarlama", "yonetim")}
STATES = ("taslak", "onayda", "onaylandi", "reddedildi", "arsiv")
STATE_LABELS = {"taslak": "Taslak", "onayda": "Onay bekliyor", "onaylandi": "Onaylandı",
                "reddedildi": "Geri gönderildi", "arsiv": "Arşiv"}


def approve_key(role: str) -> str:
    return f"ozellik:fiyatlama.onay-{role}"


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


ANALYSES = sa.Table(
    "semantic_pricing_analyses", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("stage", sa.String(12), nullable=False, default="tahmini"),
    sa.Column("status", sa.String(12), nullable=False, default="taslak"),
    sa.Column("version", sa.Integer, nullable=False, default=1),
    sa.Column("crm_book_id", sa.String(40), index=True),
    sa.Column("crm_project_id", sa.String(40)),
    sa.Column("stock_code", sa.String(40)),
    sa.Column("specs_json", sa.Text, nullable=False, default="{}"),
    sa.Column("inputs_json", sa.Text, nullable=False, default="{}"),
    sa.Column("result_json", sa.Text),
    sa.Column("chosen_price", sa.Numeric(14, 2)),
    sa.Column("chosen_qty", sa.Integer),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    _ts("created_at", False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at"),
    sa.Column("submitted_by", sa.String(120)),
    _ts("submitted_at"),
)
APPROVALS = sa.Table(
    "semantic_pricing_approvals", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("analysis_id", sa.String(32), nullable=False, index=True),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("role", sa.String(16), nullable=False),
    sa.Column("decision", sa.String(8), nullable=False),        # onay | ret
    sa.Column("note", sa.Text),
    sa.Column("by", sa.String(120), nullable=False),
    _ts("at", False),
)
MARKET = sa.Table(
    "semantic_pricing_market", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("analysis_id", sa.String(32), index=True),
    sa.Column("crm_book_id", sa.String(40), index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("publisher", sa.String(200)),
    sa.Column("channel", sa.String(120)),
    sa.Column("price", sa.Numeric(14, 2), nullable=False),
    sa.Column("pages", sa.Integer),
    sa.Column("url", sa.String(500)),
    sa.Column("seen_on", sa.Date),
    sa.Column("created_by", sa.String(120), nullable=False),
    _ts("created_at", False),
)
DEFAULTS = sa.Table(
    "semantic_pricing_defaults", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("values_json", sa.Text, nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at"),
)
FORM_TARIFF = sa.Table(
    "semantic_pricing_form_tariff", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("values_json", sa.Text, nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at"),
)
PROPOSALS = sa.Table(
    "semantic_pricing_proposals", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("status", sa.String(12), nullable=False, default="onayda"),
    sa.Column("items_json", sa.Text, nullable=False),
    sa.Column("params_json", sa.Text, nullable=False, default="{}"),
    sa.Column("created_by", sa.String(120), nullable=False),
    _ts("created_at", False),
    sa.Column("decided_by", sa.String(120)),
    _ts("decided_at"),
    sa.Column("decision_note", sa.Text),
)

#: Kullanıcı değiştirmedikçe geçerli varsayılanlar. Ölçülen değerler (kanal iskontosu, baskı eğrisi) bunların
#: üstüne gelir; burada yalnız veride karşılığı olmayan iş kararları var (ekranda «varsayım» diye yazılır).
BASE_DEFAULTS: dict[str, Any] = {
    "targetMargin": 0.15,        # net gelire göre hedef kâr marjı
    "variableRate": 0.05,        # dağıtım/nakliye/komisyon, net gelirin oranı
    "overheadRate": 0.0,         # genel gider payı, basılan adet maliyetinin oranı
    "sellThrough": 1.0,          # basılanın hesap döneminde satılan oranı
    "qtys": [1000, 2000, 3000, 5000],
    "channelMix": None,          # None = son 12 ayın gerçek kanal dağılımı
}

_ready: set[int] = set()
_lock = threading.Lock()


class PricingError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new() -> str:
    return uuid.uuid4().hex


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return str(v)


def _j(text: Optional[str], default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


def _num(v: Any) -> Optional[float]:
    return None if v is None else float(v)


# ------------------------------------------------------------------ varsayılanlar

def get_defaults(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(defaults_stmt(tenant)).mappings().first()
    saved = _j(row["values_json"], {}) if row else {}
    return {**BASE_DEFAULTS, **{k: v for k, v in saved.items() if k in BASE_DEFAULTS},
            "updatedBy": row["updated_by"] if row else None, "updatedAt": _iso(row["updated_at"]) if row else None}


def _rate(body: dict, key: str, lo: float = 0.0, hi: float = 0.95) -> Optional[float]:
    if key not in body or body[key] is None or body[key] == "":
        return None
    try:
        v = float(body[key])
    except (TypeError, ValueError):
        raise PricingError(f"«{key}» sayı olmalı.") from None
    if not lo <= v <= hi:
        raise PricingError(f"«{key}» {lo:g} ile {hi:g} arasında olmalı.")
    return v


def _qtys(value: Any) -> list[int]:
    if not isinstance(value, list) or not value:
        raise PricingError("En az bir baskı adedi girin.")
    out = []
    for q in value:
        try:
            n = int(float(q))
        except (TypeError, ValueError):
            raise PricingError("Baskı adedi tam sayı olmalı.") from None
        if n <= 0:
            raise PricingError("Baskı adedi sıfırdan büyük olmalı.")
        out.append(n)
    return sorted(set(out))


def save_defaults(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    cur = get_defaults(engine, tenant)
    vals = {k: cur[k] for k in BASE_DEFAULTS}
    for key, hi in (("targetMargin", 0.9), ("variableRate", 0.9), ("overheadRate", 2.0), ("sellThrough", 1.0)):
        v = _rate(body, key, 0.0, hi)
        if v is not None:
            vals[key] = v
    if vals["sellThrough"] <= 0:
        raise PricingError("Satış oranı sıfır olamaz.")
    if "qtys" in body:
        vals["qtys"] = _qtys(body["qtys"])
    if "channelMix" in body:
        vals["channelMix"] = _mix(body["channelMix"])
    with engine.begin() as c:
        c.execute(DEFAULTS.delete().where(DEFAULTS.c.tenant_id == tenant))
        c.execute(DEFAULTS.insert().values(tenant_id=tenant, values_json=json.dumps(vals, ensure_ascii=False),
                                           updated_by=user, updated_at=_now()))
    return get_defaults(engine, tenant)


def _mix(value: Any) -> Optional[dict[str, float]]:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise PricingError("Kanal karması kanal → pay biçiminde olmalı.")
    out = {}
    for k, v in value.items():
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise PricingError("Kanal payı sayı olmalı.") from None
        if f < 0:
            raise PricingError("Kanal payı eksi olamaz.")
        if f:
            out[str(k)[:40]] = f
    total = sum(out.values())
    if not total:
        raise PricingError("Kanal karmasında en az bir kanalın payı olmalı.")
    return {k: round(v / total, 6) for k, v in out.items()}


# ------------------------------------------------------------------ analizler

def _analysis_row(r: Any, approvals: list[dict] | None = None) -> dict[str, Any]:
    out = {
        "id": r["id"], "title": r["title"], "stage": r["stage"], "stageLabel": STAGES.get(r["stage"], r["stage"]),
        "status": r["status"], "statusLabel": STATE_LABELS.get(r["status"], r["status"]), "version": r["version"],
        "crmBookId": r["crm_book_id"], "crmProjectId": r["crm_project_id"], "stockCode": r["stock_code"],
        "specs": _j(r["specs_json"], {}), "inputs": _j(r["inputs_json"], {}), "result": _j(r["result_json"], None),
        "chosenPrice": _num(r["chosen_price"]), "chosenQty": r["chosen_qty"], "note": r["note"],
        "createdBy": r["created_by"], "createdAt": _iso(r["created_at"]), "updatedBy": r["updated_by"],
        "updatedAt": _iso(r["updated_at"]), "submittedBy": r["submitted_by"], "submittedAt": _iso(r["submitted_at"]),
        "required": [{"role": k, "label": APPROVERS[k]} for k in REQUIRED.get(r["stage"], ())],
    }
    if approvals is not None:
        out["approvals"] = approvals
    return out


def _approvals(conn, analysis_id: str, version: Optional[int] = None) -> list[dict[str, Any]]:
    stmt = sa.select(APPROVALS).where(APPROVALS.c.analysis_id == analysis_id).order_by(APPROVALS.c.at)
    if version is not None:
        stmt = stmt.where(APPROVALS.c.version == version)
    return [{"id": a["id"], "version": a["version"], "role": a["role"], "roleLabel": APPROVERS.get(a["role"], a["role"]),
             "decision": a["decision"], "note": a["note"], "by": a["by"], "at": _iso(a["at"])}
            for a in conn.execute(stmt).mappings()]


# Okuma ifadeleri ayrı kurulur: aynı ifade hem çalıştırılır hem sorgu bilgisinde gösterilir (pricing/kaynak.py).


def analyses_stmt(tenant: str, *, status: Optional[str] = None, q: str = "", book: Optional[str] = None):
    stmt = sa.select(ANALYSES).where(ANALYSES.c.tenant_id == tenant)
    if status:
        stmt = stmt.where(ANALYSES.c.status == status)
    else:
        stmt = stmt.where(ANALYSES.c.status != "arsiv")
    if book:
        stmt = stmt.where(ANALYSES.c.crm_book_id == book)
    if q.strip():
        stmt = stmt.where(ANALYSES.c.title.ilike(f"%{q.strip()[:80]}%"))
    return stmt.order_by(sa.func.coalesce(ANALYSES.c.updated_at, ANALYSES.c.created_at).desc())


def analysis_stmt(tenant: str, analysis_id: str):
    return sa.select(ANALYSES).where(ANALYSES.c.id == analysis_id, ANALYSES.c.tenant_id == tenant)


def defaults_stmt(tenant: str):
    return sa.select(DEFAULTS).where(DEFAULTS.c.tenant_id == tenant)


def market_stmt(tenant: str, *, analysis_id: Optional[str] = None, book: Optional[str] = None):
    stmt = sa.select(MARKET).where(MARKET.c.tenant_id == tenant)
    if analysis_id:
        stmt = stmt.where(MARKET.c.analysis_id == analysis_id)
    if book:
        stmt = stmt.where(MARKET.c.crm_book_id == book)
    return stmt.order_by(MARKET.c.created_at.desc())


def proposals_stmt(tenant: str):
    return sa.select(PROPOSALS).where(PROPOSALS.c.tenant_id == tenant).order_by(PROPOSALS.c.created_at.desc())


def proposal_stmt(tenant: str, pid: str):
    return sa.select(PROPOSALS).where(PROPOSALS.c.id == pid, PROPOSALS.c.tenant_id == tenant)


def list_analyses(engine: sa.engine.Engine, tenant: str, *, status: Optional[str] = None, q: str = "",
                  book: Optional[str] = None) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(analyses_stmt(tenant, status=status, q=q, book=book)).mappings().all()
        items = []
        for r in rows:
            item = _analysis_row(r, _approvals(c, r["id"], r["version"]))
            item.pop("inputs", None)
            item.pop("specs", None)
            res = item.pop("result", None) or {}
            item["summary"] = res.get("summary")
            items.append(item)
        counts = dict(c.execute(sa.select(ANALYSES.c.status, sa.func.count()).where(ANALYSES.c.tenant_id == tenant)
                                .group_by(ANALYSES.c.status)).all())
    return {"items": items, "total": len(items), "counts": counts}


def get_analysis(engine: sa.engine.Engine, tenant: str, analysis_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(analysis_stmt(tenant, analysis_id)).mappings().first()
        if not r:
            raise PricingError("Fiyat analizi bulunamadı.", 404)
        out = _analysis_row(r, _approvals(c, r["id"], r["version"]))
        out["history"] = _approvals(c, r["id"])
        out["market"] = market_list(engine, tenant, analysis_id=analysis_id, conn=c)["items"]
    return out


def _clean_title(body: dict) -> str:
    title = str(body.get("title") or "").strip()
    if not title:
        raise PricingError("Kitap ya da analiz adı girin.")
    return title[:300]


def create_analysis(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    stage = body.get("stage") or "tahmini"
    if stage not in STAGES:
        raise PricingError("Aşama «tahmini» ya da «kesin» olmalı.")
    aid = _new()
    with engine.begin() as c:
        c.execute(ANALYSES.insert().values(
            id=aid, tenant_id=tenant, title=_clean_title(body), stage=stage, status="taslak", version=1,
            crm_book_id=(str(body.get("crmBookId") or "")[:40] or None),
            crm_project_id=(str(body.get("crmProjectId") or "")[:40] or None),
            stock_code=(str(body.get("stockCode") or "")[:40] or None),
            specs_json=json.dumps(body.get("specs") or {}, ensure_ascii=False),
            inputs_json=json.dumps(body.get("inputs") or {}, ensure_ascii=False),
            note=(str(body.get("note") or "")[:4000] or None), created_by=user, created_at=_now()))
    return get_analysis(engine, tenant, aid)


EDITABLE = ("title", "stage", "specs", "inputs", "note", "chosenPrice", "chosenQty", "stockCode", "crmBookId")


def update_analysis(engine: sa.engine.Engine, tenant: str, user: str, analysis_id: str,
                    body: dict[str, Any]) -> dict[str, Any]:
    cur = get_analysis(engine, tenant, analysis_id)
    if cur["status"] in ("onayda", "onaylandi"):
        raise PricingError("Onaya gönderilmiş analiz değiştirilemez; önce taslağa geri alın.", 409)
    vals: dict[str, Any] = {}
    if "title" in body:
        vals["title"] = _clean_title(body)
    if "stage" in body:
        if body["stage"] not in STAGES:
            raise PricingError("Aşama «tahmini» ya da «kesin» olmalı.")
        vals["stage"] = body["stage"]
    for key, col in (("specs", "specs_json"), ("inputs", "inputs_json")):
        if key in body:
            if not isinstance(body[key], dict):
                raise PricingError(f"«{key}» nesne olmalı.")
            vals[col] = json.dumps(body[key], ensure_ascii=False)
    if "note" in body:
        vals["note"] = str(body.get("note") or "")[:4000] or None
    if "chosenPrice" in body:
        p = body["chosenPrice"]
        if p not in (None, ""):
            try:
                p = float(p)
            except (TypeError, ValueError):
                raise PricingError("Seçilen fiyat sayı olmalı.") from None
            if p <= 0:
                raise PricingError("Seçilen fiyat sıfırdan büyük olmalı.")
        vals["chosen_price"] = p if p not in ("",) else None
    if "chosenQty" in body:
        q = body["chosenQty"]
        vals["chosen_qty"] = None if q in (None, "") else _qtys([q])[0]
    for key, col in (("stockCode", "stock_code"), ("crmBookId", "crm_book_id")):
        if key in body:
            vals[col] = str(body.get(key) or "")[:40] or None
    if cur["status"] == "reddedildi":
        vals["status"] = "taslak"
    if not vals:
        return cur
    vals.update(updated_by=user, updated_at=_now())
    with engine.begin() as c:
        c.execute(ANALYSES.update().where(ANALYSES.c.id == analysis_id).values(**vals))
    return get_analysis(engine, tenant, analysis_id)


def submit(engine: sa.engine.Engine, tenant: str, user: str, analysis_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Onaya gönderir: sonuç dondurulur, yeni sürüm açılır (eski imzalar o sürümde kalır)."""
    cur = get_analysis(engine, tenant, analysis_id)
    if cur["status"] not in ("taslak", "reddedildi"):
        raise PricingError("Yalnız taslak analiz onaya gönderilir.", 409)
    if not cur["chosenPrice"] or not cur["chosenQty"]:
        raise PricingError("Onaya göndermeden önce baskı adedini ve kapak fiyatını seçin.")
    with engine.begin() as c:
        c.execute(ANALYSES.update().where(ANALYSES.c.id == analysis_id).values(
            status="onayda", version=cur["version"] + 1, result_json=json.dumps(result, ensure_ascii=False, default=str),
            submitted_by=user, submitted_at=_now(), updated_by=user, updated_at=_now()))
    return get_analysis(engine, tenant, analysis_id)


def withdraw(engine: sa.engine.Engine, tenant: str, user: str, analysis_id: str) -> dict[str, Any]:
    cur = get_analysis(engine, tenant, analysis_id)
    if cur["status"] not in ("onayda", "onaylandi", "reddedildi"):
        raise PricingError("Analiz zaten taslak.", 409)
    with engine.begin() as c:
        c.execute(ANALYSES.update().where(ANALYSES.c.id == analysis_id).values(
            status="taslak", version=cur["version"] + 1, updated_by=user, updated_at=_now()))
    return get_analysis(engine, tenant, analysis_id)


def archive(engine: sa.engine.Engine, tenant: str, user: str, analysis_id: str) -> dict[str, Any]:
    cur = get_analysis(engine, tenant, analysis_id)
    if cur["status"] == "onayda":
        raise PricingError("Onay bekleyen analiz arşive alınamaz; önce geri alın.", 409)
    with engine.begin() as c:
        c.execute(ANALYSES.update().where(ANALYSES.c.id == analysis_id).values(
            status="arsiv", updated_by=user, updated_at=_now()))
    return get_analysis(engine, tenant, analysis_id)


def decide(engine: sa.engine.Engine, tenant: str, user: str, analysis_id: str, role: str, decision: str,
           note: str, version: int, allowed: bool) -> dict[str, Any]:
    """Bir rol adına imza. `allowed` = kişinin bu rolün açıkça verilen yetkisi var mı (uç denetler)."""
    cur = get_analysis(engine, tenant, analysis_id)
    if role not in APPROVERS:
        raise PricingError("Bilinmeyen onay rolü.")
    if role not in REQUIRED[cur["stage"]]:
        raise PricingError(f"{STAGES[cur['stage']]} için {APPROVERS[role]} onayı istenmiyor.")
    if not allowed:
        raise PricingError(f"{APPROVERS[role]} adına onay yetkiniz yok.", 403)
    if cur["status"] != "onayda":
        raise PricingError("Analiz onay beklemiyor.", 409)
    if int(version) != cur["version"]:
        raise PricingError("Analiz siz bakarken değişti; sayfayı yenileyip yeniden bakın.", 409)
    if (user or "").lower() == (cur["submittedBy"] or "").lower():
        raise PricingError("Onaya gönderen kişi aynı analizi onaylayamaz.", 409)
    signed = cur["approvals"]
    if any(a["role"] == role for a in signed):
        raise PricingError(f"{APPROVERS[role]} bu sürüm için kararını verdi.", 409)
    if any((a["by"] or "").lower() == (user or "").lower() for a in signed):
        raise PricingError("Bir kişi aynı analizde tek rol adına karar verir.", 409)
    if decision not in ("onay", "ret"):
        raise PricingError("Karar «onay» ya da «ret» olmalı.")
    if decision == "ret" and not (note or "").strip():
        raise PricingError("Geri gönderirken nedenini yazın.")
    with engine.begin() as c:
        c.execute(APPROVALS.insert().values(id=_new(), analysis_id=analysis_id, version=cur["version"], role=role,
                                            decision=decision, note=(note or "").strip()[:2000] or None, by=user,
                                            at=_now()))
        if decision == "ret":
            status = "reddedildi"
        else:
            done = {a["role"] for a in signed if a["decision"] == "onay"} | {role}
            status = "onaylandi" if set(REQUIRED[cur["stage"]]) <= done else "onayda"
        c.execute(ANALYSES.update().where(ANALYSES.c.id == analysis_id).values(status=status))
    return get_analysis(engine, tenant, analysis_id)


# ------------------------------------------------------------------ elle girilen pazar fiyatları

def market_list(engine: sa.engine.Engine, tenant: str, *, analysis_id: Optional[str] = None,
                book: Optional[str] = None, conn=None) -> dict[str, Any]:
    stmt = market_stmt(tenant, analysis_id=analysis_id, book=book)

    def run(c):
        return [{"id": m["id"], "analysisId": m["analysis_id"], "crmBookId": m["crm_book_id"], "title": m["title"],
                 "publisher": m["publisher"], "channel": m["channel"], "price": _num(m["price"]), "pages": m["pages"],
                 "url": m["url"], "seenOn": _iso(m["seen_on"]), "createdBy": m["created_by"],
                 "createdAt": _iso(m["created_at"])} for m in c.execute(stmt).mappings()]

    if conn is not None:
        return {"items": run(conn)}
    with engine.connect() as c:
        return {"items": run(c)}


def market_add(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    from datetime import date as _date
    title = str(body.get("title") or "").strip()
    if not title:
        raise PricingError("Emsal kitabın adını girin.")
    try:
        price = float(body.get("price"))
    except (TypeError, ValueError):
        raise PricingError("Fiyat sayı olmalı.") from None
    if price <= 0:
        raise PricingError("Fiyat sıfırdan büyük olmalı.")
    pages = body.get("pages")
    if pages not in (None, ""):
        try:
            pages = int(float(pages))
        except (TypeError, ValueError):
            raise PricingError("Sayfa sayısı tam sayı olmalı.") from None
        if pages <= 0:
            raise PricingError("Sayfa sayısı sıfırdan büyük olmalı.")
    else:
        pages = None
    url = str(body.get("url") or "").strip()[:500] or None
    if url and not url.startswith(("http://", "https://")):
        raise PricingError("Bağlantı http:// ya da https:// ile başlamalı.")
    seen = body.get("seenOn")
    try:
        seen_on = _date.fromisoformat(str(seen)[:10]) if seen else None
    except ValueError:
        raise PricingError("Tarih YYYY-AA-GG biçiminde olmalı.") from None
    mid = _new()
    with engine.begin() as c:
        c.execute(MARKET.insert().values(
            id=mid, tenant_id=tenant, analysis_id=(str(body.get("analysisId") or "")[:32] or None),
            crm_book_id=(str(body.get("crmBookId") or "")[:40] or None), title=title[:300],
            publisher=(str(body.get("publisher") or "").strip()[:200] or None),
            channel=(str(body.get("channel") or "").strip()[:120] or None), price=price, pages=pages, url=url,
            seen_on=seen_on, created_by=user, created_at=_now()))
    return {"id": mid}


def market_delete(engine: sa.engine.Engine, tenant: str, user: str, market_id: str, is_admin: bool) -> dict[str, Any]:
    with engine.begin() as c:
        row = c.execute(sa.select(MARKET).where(MARKET.c.id == market_id, MARKET.c.tenant_id == tenant)).mappings().first()
        if not row:
            raise PricingError("Kayıt bulunamadı.", 404)
        if row["created_by"].lower() != (user or "").lower() and not is_admin:
            raise PricingError("Kaydı yalnız giren kişi ya da yönetici siler.", 403)
        c.execute(MARKET.delete().where(MARKET.c.id == market_id))
    return {"ok": True, "title": row["title"]}


# ------------------------------------------------------------------ backlist zam teklifleri

def proposal_create(engine: sa.engine.Engine, tenant: str, user: str, title: str, items: list[dict],
                    params: dict[str, Any]) -> dict[str, Any]:
    if not items:
        raise PricingError("Teklifte en az bir kitap olmalı.")
    pid = _new()
    with engine.begin() as c:
        c.execute(PROPOSALS.insert().values(
            id=pid, tenant_id=tenant, title=(title or "Backlist fiyat revizyonu")[:300], status="onayda",
            items_json=json.dumps(items, ensure_ascii=False, default=str),
            params_json=json.dumps(params, ensure_ascii=False, default=str), created_by=user, created_at=_now()))
    return proposal_get(engine, tenant, pid)


def _proposal_row(r: Any, with_items: bool = True) -> dict[str, Any]:
    items = _j(r["items_json"], [])
    out = {"id": r["id"], "title": r["title"], "status": r["status"],
           "statusLabel": STATE_LABELS.get(r["status"], r["status"]), "count": len(items),
           "params": _j(r["params_json"], {}), "createdBy": r["created_by"], "createdAt": _iso(r["created_at"]),
           "decidedBy": r["decided_by"], "decidedAt": _iso(r["decided_at"]), "decisionNote": r["decision_note"]}
    if with_items:
        out["items"] = items
    return out


def proposal_list(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(proposals_stmt(tenant)).mappings().all()
    return {"items": [_proposal_row(r, False) for r in rows]}


def proposal_get(engine: sa.engine.Engine, tenant: str, pid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(proposal_stmt(tenant, pid)).mappings().first()
    if not r:
        raise PricingError("Teklif bulunamadı.", 404)
    return _proposal_row(r)


def proposal_decide(engine: sa.engine.Engine, tenant: str, user: str, pid: str, decision: str, note: str,
                    allowed: bool) -> dict[str, Any]:
    cur = proposal_get(engine, tenant, pid)
    if not allowed:
        raise PricingError("Toplu fiyat teklifini yalnız Mali İşler onay yetkisi olan karara bağlar.", 403)
    if cur["status"] != "onayda":
        raise PricingError("Teklif karar beklemiyor.", 409)
    if (user or "").lower() == (cur["createdBy"] or "").lower():
        raise PricingError("Teklifi hazırlayan kişi karar veremez.", 409)
    if decision not in ("onay", "ret"):
        raise PricingError("Karar «onay» ya da «ret» olmalı.")
    if decision == "ret" and not (note or "").strip():
        raise PricingError("Geri gönderirken nedenini yazın.")
    with engine.begin() as c:
        c.execute(PROPOSALS.update().where(PROPOSALS.c.id == pid).values(
            status="onaylandi" if decision == "onay" else "reddedildi", decided_by=user, decided_at=_now(),
            decision_note=(note or "").strip()[:2000] or None))
    return proposal_get(engine, tenant, pid)


# ------------------------------------------------------------------ maliyet formu tarifesi

def form_tariff_stmt(tenant: str):
    return sa.select(FORM_TARIFF).where(FORM_TARIFF.c.tenant_id == tenant)


def get_form_tariff(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Maliyet formunun matbaa ve malzeme tarifesi: portalda değiştirildiyse o, yoksa basım Excel'inden alınan varsayılan."""
    from semantic_bridge.pricing import form as F
    base = F.default_tariff()
    with engine.connect() as c:
        row = c.execute(form_tariff_stmt(tenant)).mappings().first()
    saved = _j(row["values_json"], {}) if row else {}
    return {**base, **saved, "updatedBy": row["updated_by"] if row else None,
            "updatedAt": _iso(row["updated_at"]) if row else None, "isDefault": not row}


def _pos(v: Any, what: str, allow_zero: bool = True) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise PricingError(f"{what} sayı olmalı.") from None
    if x < 0 or (x == 0 and not allow_zero) or x > 1e9:
        raise PricingError(f"{what} geçersiz.")
    return x


def save_form_tariff(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    """Tarifenin değiştirilebilen kısımları: kur, vade, kâğıt fiyatları, kalem fiyatları, fire, dolaylı gider, kapak
    ücretinin bölündüğü baskı sayısı, yayınevi iskontoları. Ebat ve klişe tabloları varsayılandan gelir."""
    cur = get_form_tariff(engine, tenant)
    out = {k: cur[k] for k in ("kur", "vade", "papers", "prices", "fire", "dolayli", "kapakBolen", "publishers")}
    if "kur" in body:
        out["kur"] = {c: _pos((body["kur"] or {}).get(c, out["kur"][c]), f"{c} kuru", False) for c in ("USD", "EUR")}
    if "vade" in body:
        v = body["vade"] or {}
        out["vade"] = {"oran": _pos(v.get("oran", out["vade"]["oran"]), "Vade oranı"),
                       "ay": _pos(v.get("ay", out["vade"]["ay"]), "Vade süresi")}
    if "papers" in body:
        by = {p["name"]: p for p in out["papers"]}
        for p in body["papers"] or []:
            if p.get("name") in by:
                by[p["name"]]["base"] = _pos(p.get("base"), f"«{p['name']}» fiyatı")
    if "prices" in body:
        for k, v in (body["prices"] or {}).items():
            if k in out["prices"]:
                out["prices"][k] = {**out["prices"][k], "m": _pos((v or {}).get("m", out["prices"][k]["m"]), k),
                                    "n": _pos((v or {}).get("n", out["prices"][k]["n"]), k)}
    if "fire" in body:
        out["fire"] = {k: _pos((body["fire"] or {}).get(k, v), f"{k} firesi") for k, v in out["fire"].items()}
    if "dolayli" in body:
        out["dolayli"] = _pos(body["dolayli"], "Dolaylı gider oranı")
    if "kapakBolen" in body:
        out["kapakBolen"] = _pos(body["kapakBolen"], "Kapak ücretinin bölündüğü baskı sayısı", False)
    if "publishers" in body:
        out["publishers"] = {str(k): _pos(v, f"«{k}» iskontosu") for k, v in (body["publishers"] or {}).items() if str(k).strip()}
    with engine.begin() as c:
        c.execute(FORM_TARIFF.delete().where(FORM_TARIFF.c.tenant_id == tenant))
        c.execute(FORM_TARIFF.insert().values(tenant_id=tenant, values_json=json.dumps(out, ensure_ascii=False),
                                              updated_by=user, updated_at=_now()))
    return get_form_tariff(engine, tenant)


def reset_form_tariff(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.begin() as c:
        c.execute(FORM_TARIFF.delete().where(FORM_TARIFF.c.tenant_id == tenant))
    return get_form_tariff(engine, tenant)
