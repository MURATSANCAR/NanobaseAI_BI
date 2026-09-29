"""M12 Üretim Yönetimi — portalın kendi kayıtları (CRM'e ve Logo'ya yazılmaz).

CRM üretim kartında (`new_UretimBase`) olmayan ya da CRM'e yazılamayan bilgiler burada tutulur, CRM kartının
kimliğine (`new_UretimId`) bağlanır:

- **Kayıt** (`semantic_production_entries`): bir noktanın gerçekleşen tarihi (CRM boşsa doldurur, CRM'i ezmez),
  kitabın hedef yayın tarihi (geriye doğru takvimin çıpası), kalite sonucu (sorunsuz / sorun), not, prodüksiyon
  müdürünün matbaa onayı. Her kayıt yazanıyla ve zamanıyla durur; silinen kayıt işaretlenir, satır kalır.
- **Teklif** (`semantic_production_quotes`): matbaanın o iş için verdiği teklif (birim/toplam fiyat, teslim tarihi,
  kapasite notu). Matbaa seçim raporu önerileri geçmiş performansla bu teklifleri yan yana koyar.

Aynı türde (ve aynı noktada) birden çok kayıt varsa geçerli olan en yenisidir; eskiler geçmiş olarak görünür.
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge.production_plan import KEYS, LABEL

_md = sa.MetaData()

ENTRIES = sa.Table(
    "semantic_production_entries", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("card_id", sa.String(40), nullable=False, index=True),     # CRM new_UretimId
    sa.Column("kind", sa.String(20), nullable=False),                     # gercek | yayin | kalite | not | onay
    sa.Column("milestone", sa.String(20)),                                # gercek için: dosya | matbaa | baski | depo
    sa.Column("day", sa.Date),
    sa.Column("value", sa.String(200)),                                   # kalite: sorunsuz|sorun; onay: matbaa adı
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_display", sa.String(200)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("deleted_by", sa.String(120)),
    sa.Column("deleted_at", sa.DateTime(timezone=True)),
)
QUOTES = sa.Table(
    "semantic_production_quotes", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("card_id", sa.String(40), nullable=False, index=True),
    sa.Column("printer", sa.String(200), nullable=False),
    sa.Column("unit_price", sa.Numeric(18, 4)),
    sa.Column("total_price", sa.Numeric(18, 2)),
    sa.Column("delivery_day", sa.Date),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_display", sa.String(200)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("deleted_by", sa.String(120)),
    sa.Column("deleted_at", sa.DateTime(timezone=True)),
)

KINDS = {
    "gercek": "Gerçekleşen tarih",
    "yayin": "Hedef yayın tarihi",
    "kalite": "Kalite sonucu",
    "not": "Not",
    "onay": "Matbaa onayı",
}
QUALITY = {"sorunsuz": "Sorunsuz", "sorun": "Kalite sorunu"}

_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_ID = re.compile(r"^[0-9a-f]{32}$")
_ready: set[int] = set()
_lock = threading.Lock()


class ProductionError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

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


def card_id(v: Any) -> str:
    s = str(v or "").strip()
    if not _GUID.match(s):
        raise ProductionError("Üretim kartı bulunamadı.", 404)
    return s.lower()


def _rid(v: Any) -> str:
    s = str(v or "").strip()
    if not _ID.match(s):
        raise ProductionError("Kayıt bulunamadı.", 404)
    return s


def _day(v: Any, label: str, required: bool = False) -> Optional[date]:
    if v in (None, ""):
        if required:
            raise ProductionError(f"{label} gerekli.")
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ProductionError(f"{label} YYYY-AA-GG biçiminde olmalı.") from None


def _text(v: Any, limit: int) -> Optional[str]:
    s = re.sub(r"[ \t]+", " ", str(v or "")).strip()
    if len(s) > limit:
        raise ProductionError(f"Metin en çok {limit} karakter olabilir.")
    return s or None


def _money(v: Any, label: str) -> Optional[float]:
    if v in (None, ""):
        return None
    s = str(v).replace("₺", "").replace(" ", "").strip()
    if "," in s:  # Türkçe yazım: binlik nokta, ondalık virgül (1.250,50)
        s = s.replace(".", "").replace(",", ".")
    try:
        x = float(s)
    except ValueError:
        raise ProductionError(f"{label} sayı olmalı.") from None
    if x < 0:
        raise ProductionError(f"{label} eksi olamaz.")
    return x


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).isoformat()


def entry_values(body: dict[str, Any], today: date) -> dict[str, Any]:
    kind = str(body.get("kind") or "")
    if kind not in KINDS:
        raise ProductionError("Kayıt türü geçersiz.")
    out: dict[str, Any] = {"kind": kind, "milestone": None, "day": None, "value": None,
                           "note": _text(body.get("note"), 2000)}
    if kind == "gercek":
        m = str(body.get("milestone") or "")
        if m not in KEYS:
            raise ProductionError("Hangi aşamanın tarihi girildiği belli değil.")
        d = _day(body.get("day"), f"{LABEL[m]} tarihi", required=True)
        if d > today:
            raise ProductionError("Gerçekleşen tarih ileri bir gün olamaz.")
        out.update(milestone=m, day=d)
    elif kind == "yayin":
        out["day"] = _day(body.get("day"), "Hedef yayın tarihi", required=True)
    elif kind == "kalite":
        v = str(body.get("value") or "")
        if v not in QUALITY:
            raise ProductionError("Kalite sonucu «sorunsuz» ya da «sorun» olmalı.")
        if v == "sorun" and not out["note"]:
            raise ProductionError("Kalite sorununu bir cümleyle yazın.")
        out["value"] = v
    elif kind == "not":
        if not out["note"]:
            raise ProductionError("Not boş olamaz.")
    elif kind == "onay":
        v = _text(body.get("value"), 200)
        if not v:
            raise ProductionError("Onaylanan matbaa seçilmeli.")
        out["value"] = v
    return out


def add_entry(engine: sa.engine.Engine, tenant: str, user: str, display: str, cid: str, body: dict[str, Any],
              today: date) -> dict[str, Any]:
    vals = entry_values(body, today)
    row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "card_id": card_id(cid), **vals,
           "created_by": user, "created_display": display, "created_at": _now()}
    with engine.begin() as c:
        c.execute(ENTRIES.insert().values(**row))
    return _entry(row)


def delete_entry(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, rid: str) -> dict[str, Any]:
    rid = _rid(rid)
    with engine.begin() as c:
        r = c.execute(sa.select(ENTRIES).where(ENTRIES.c.tenant_id == tenant, ENTRIES.c.id == rid,
                                               ENTRIES.c.deleted_at.is_(None))).mappings().first()
        if r is None:
            raise ProductionError("Kayıt bulunamadı.", 404)
        if r["created_by"] != user and not admin:
            raise ProductionError("Kaydı yalnız yazan kişi (ya da yönetici) silebilir.", 403)
        c.execute(ENTRIES.update().where(ENTRIES.c.id == rid).values(deleted_by=user, deleted_at=_now()))
    return _entry(dict(r))


def _entry(r: dict[str, Any]) -> dict[str, Any]:
    d = r.get("day")
    return {"id": r["id"], "cardId": r["card_id"], "kind": r["kind"], "kindLabel": KINDS.get(r["kind"], r["kind"]),
            "milestone": r.get("milestone"), "milestoneLabel": LABEL.get(r.get("milestone") or "", None),
            "day": d.isoformat() if isinstance(d, date) else (str(d)[:10] if d else None),
            "value": r.get("value"), "valueLabel": QUALITY.get(r.get("value") or "", r.get("value")),
            "note": r.get("note"), "by": r["created_by"], "byName": r.get("created_display") or r["created_by"],
            "at": _iso(r.get("created_at"))}


def quote_values(body: dict[str, Any]) -> dict[str, Any]:
    printer = _text(body.get("printer"), 200)
    if not printer:
        raise ProductionError("Teklifi veren matbaa seçilmeli.")
    unit = _money(body.get("unitPrice"), "Birim fiyat")
    total = _money(body.get("totalPrice"), "Toplam fiyat")
    if unit is None and total is None:
        raise ProductionError("Birim ya da toplam fiyat girilmeli.")
    return {"printer": printer, "unit_price": unit, "total_price": total,
            "delivery_day": _day(body.get("deliveryDay"), "Teslim tarihi"), "note": _text(body.get("note"), 1000)}


def add_quote(engine: sa.engine.Engine, tenant: str, user: str, display: str, cid: str, body: dict[str, Any]) -> dict[str, Any]:
    row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "card_id": card_id(cid), **quote_values(body),
           "created_by": user, "created_display": display, "created_at": _now()}
    with engine.begin() as c:
        c.execute(QUOTES.insert().values(**row))
    return _quote(row)


def delete_quote(engine: sa.engine.Engine, tenant: str, user: str, admin: bool, rid: str) -> dict[str, Any]:
    rid = _rid(rid)
    with engine.begin() as c:
        r = c.execute(sa.select(QUOTES).where(QUOTES.c.tenant_id == tenant, QUOTES.c.id == rid,
                                              QUOTES.c.deleted_at.is_(None))).mappings().first()
        if r is None:
            raise ProductionError("Teklif bulunamadı.", 404)
        if r["created_by"] != user and not admin:
            raise ProductionError("Teklifi yalnız giren kişi (ya da yönetici) silebilir.", 403)
        c.execute(QUOTES.update().where(QUOTES.c.id == rid).values(deleted_by=user, deleted_at=_now()))
    return _quote(dict(r))


def _quote(r: dict[str, Any]) -> dict[str, Any]:
    d = r.get("delivery_day")
    num = lambda v: float(v) if v is not None else None  # noqa: E731
    return {"id": r["id"], "cardId": r["card_id"], "printer": r["printer"], "unitPrice": num(r.get("unit_price")),
            "totalPrice": num(r.get("total_price")),
            "deliveryDay": d.isoformat() if isinstance(d, date) else (str(d)[:10] if d else None),
            "note": r.get("note"), "by": r["created_by"], "byName": r.get("created_display") or r["created_by"],
            "at": _iso(r.get("created_at"))}


def entries_stmt(tenant: str, card_ids: Optional[list[str]] = None):
    """Silinmemiş portal kayıtları (gerçekleşen tarih, yayın, kalite, onay), yeniden eskiye. Sorgu bilgisi de bunu gösterir."""
    q = sa.select(ENTRIES).where(ENTRIES.c.tenant_id == tenant, ENTRIES.c.deleted_at.is_(None))
    if card_ids is not None:
        q = q.where(ENTRIES.c.card_id.in_(card_ids))
    return q.order_by(ENTRIES.c.created_at.desc())


def quotes_stmt(tenant: str, card_ids: Optional[list[str]] = None):
    """Silinmemiş matbaa teklifleri, yeniden eskiye."""
    q = sa.select(QUOTES).where(QUOTES.c.tenant_id == tenant, QUOTES.c.deleted_at.is_(None))
    if card_ids is not None:
        q = q.where(QUOTES.c.card_id.in_(card_ids))
    return q.order_by(QUOTES.c.created_at.desc())


def load(engine: sa.engine.Engine, tenant: str, card_ids: Optional[list[str]] = None) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Silinmemiş kayıtlar ve teklifler, karta göre, yeniden eskiye."""
    entries: dict[str, list[dict]] = {}
    quotes: dict[str, list[dict]] = {}
    with engine.connect() as c:
        for r in c.execute(entries_stmt(tenant, card_ids)).mappings():
            entries.setdefault(r["card_id"], []).append(_entry(dict(r)))
        for r in c.execute(quotes_stmt(tenant, card_ids)).mappings():
            quotes.setdefault(r["card_id"], []).append(_quote(dict(r)))
    return entries, quotes


def current(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Kartın geçerli portal bilgileri: nokta başına son gerçekleşen tarih, son yayın tarihi, son kalite, son onay."""
    out: dict[str, Any] = {"actual": {}, "publication": None, "quality": None, "approval": None}
    for e in entries:  # yeniden eskiye: ilk görülen geçerli
        if e["kind"] == "gercek" and e["milestone"] not in out["actual"]:
            out["actual"][e["milestone"]] = {"day": e["day"], "by": e["byName"], "note": e["note"], "id": e["id"]}
        elif e["kind"] == "yayin" and out["publication"] is None:
            out["publication"] = e
        elif e["kind"] == "kalite" and out["quality"] is None:
            out["quality"] = e
        elif e["kind"] == "onay" and out["approval"] is None:
            out["approval"] = e
    return out
