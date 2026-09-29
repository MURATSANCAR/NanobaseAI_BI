"""Sözleşme karşılaştırma — portalda tutulan kararlar: bulgu incelemesi (ve standart pozisyonlar, Faz 3).

**İnceleme** (`semantic_contract_compare_reviews`): bir anlaşmanın bir maddesindeki farkı gören kişi durumunu yazar —
incelendi (uygun), bilinçli istisna, CRM'de düzeltilmeli, hukuka sorulacak — not ve sorumlu kişiyle. Kayıt, işaretlendiği
andaki değerin izini (`value_sig`) taşır: CRM'de değer değişirse inceleme «eski değere ait» sayılır ve bulgu yeniden
incelenmemiş görünür. Madde anahtarı CRM kolonu, serbest metin için `not:<kolon>`, şekil denetimi için `sekil:<kimlik>`.
CRM'e yazma yok; her yazma değişiklik kaydına düşer (uçta).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import sqlalchemy as sa

_md = sa.MetaData()

REVIEWS = sa.Table(
    "semantic_contract_compare_reviews", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("agreement", sa.String(64), nullable=False),        # anlaşma anahtarı (CRM) ya da portal kaydı
    sa.Column("clause", sa.String(80), nullable=False),
    sa.Column("value_sig", sa.String(400)),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("owner", sa.String(120)),
    sa.Column("contract_no", sa.String(120)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "agreement", "clause", name="uq_contract_compare_review"),
)

REVIEW_STATUS = {
    "uygun": "İncelendi, uygun",
    "istisna": "Bilinçli istisna",
    "crm-duzelt": "CRM'de düzeltilmeli",
    "hukuk": "Hukuka sorulacak",
}
#: Bu durumlar bulguyu «kapatır»; «CRM'de düzeltilmeli» ve «hukuka sorulacak» açık iş olarak kalır.
CLOSED = ("uygun", "istisna")

_lock = threading.Lock()
_ensured: set[int] = set()


class StoreError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ensured:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)   # sürüm damgası: tanım değişmediyse açılışta veritabanına sorulmaz
        _ensured.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sig(value: Any) -> str:
    """Değerin izi: aynı değer aynı metni verir (sayı 4 basamağa yuvarlanır)."""
    if isinstance(value, float):
        value = round(value, 4)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)[:400]


def _out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "agreement": r.agreement, "clause": r.clause, "status": r.status,
            "statusLabel": REVIEW_STATUS.get(r.status, r.status), "note": r.note, "owner": r.owner, "valueSig": r.value_sig,
            "contractNo": r.contract_no, "by": r.updated_by, "at": r.updated_at.isoformat() if r.updated_at else None,
            "closed": r.status in CLOSED}


def reviews_stmt(tenant: str, agreement: Optional[str] = None) -> sa.Select:
    stmt = sa.select(REVIEWS).where(REVIEWS.c.tenant_id == tenant)
    if agreement:
        stmt = stmt.where(REVIEWS.c.agreement == agreement)
    return stmt.order_by(REVIEWS.c.agreement, REVIEWS.c.clause)


def reviews(engine: sa.engine.Engine, tenant: str, agreement: Optional[str] = None) -> dict[tuple[str, str], dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        return {(r.agreement, r.clause): _out(r) for r in c.execute(reviews_stmt(tenant, agreement))}


def attach(review: Optional[dict[str, Any]], value_sig: str) -> Optional[dict[str, Any]]:
    """Ekrana giden inceleme; değer değiştiyse `stale` (eski değere ait, bulgu açık sayılır)."""
    if review is None:
        return None
    out = dict(review)
    out["stale"] = review.get("valueSig") != value_sig
    out["open"] = out["stale"] or not review["closed"]
    return out


def save_review(engine: sa.engine.Engine, tenant: str, user: str, *, agreement: str, clause: str, value_sig: str,
                status: str, note: Any = None, owner: Any = None, contract_no: Optional[str] = None) -> dict[str, Any]:
    if status not in REVIEW_STATUS:
        raise StoreError("İnceleme durumu geçerli değil.")
    clause = str(clause or "").strip()
    if not clause or len(clause) > 80:
        raise StoreError("Madde geçerli değil.")
    note = " ".join(str(note or "").split())[:2000] or None
    owner = " ".join(str(owner or "").split())[:120] or None
    if status in ("crm-duzelt", "hukuk") and not (note or owner):
        raise StoreError("Açık kalan inceleme için not ya da sorumlu yazın.")
    ensure(engine)
    now = _now()
    with engine.begin() as c:
        r = c.execute(sa.select(REVIEWS).where(REVIEWS.c.tenant_id == tenant, REVIEWS.c.agreement == agreement,
                                               REVIEWS.c.clause == clause).with_for_update()).first()
        vals = {"value_sig": value_sig, "status": status, "note": note, "owner": owner, "contract_no": contract_no,
                "updated_by": user, "updated_at": now}
        if r is None:
            c.execute(REVIEWS.insert().values(tenant_id=tenant, agreement=agreement, clause=clause, created_by=user,
                                              created_at=now, **vals))
        else:
            c.execute(sa.update(REVIEWS).where(REVIEWS.c.id == r.id).values(**vals))
        return _out(c.execute(sa.select(REVIEWS).where(REVIEWS.c.tenant_id == tenant, REVIEWS.c.agreement == agreement,
                                                       REVIEWS.c.clause == clause)).first())


def delete_review(engine: sa.engine.Engine, tenant: str, agreement: str, clause: str) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(REVIEWS).where(REVIEWS.c.tenant_id == tenant, REVIEWS.c.agreement == agreement,
                                               REVIEWS.c.clause == clause)).first()
        if r is None:
            raise StoreError("İnceleme bulunamadı.", 404)
        c.execute(REVIEWS.delete().where(REVIEWS.c.id == r.id))
    return _out(r)


# ================================================================================ standart pozisyonlar (playbook)

POSITIONS = sa.Table(
    "semantic_contract_positions", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("clause", sa.String(80), nullable=False),           # CRM maddesi ya da `tur:<madde türü>` (belge)
    sa.Column("scope_tip", sa.Integer),
    sa.Column("scope_odeme", sa.Integer),
    sa.Column("scope_para", sa.Integer),
    sa.Column("op", sa.String(12), nullable=False),
    sa.Column("value_json", sa.Text),
    sa.Column("level", sa.String(12), nullable=False),
    sa.Column("reason", sa.Text),
    sa.Column("state", sa.String(12), nullable=False),            # oneri | onayli
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("updated_by", sa.String(120), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

OPS = {"min": "en az", "max": "en çok", "eq": "eşit", "in": "şunlardan biri", "zorunlu": "olmalı", "yasak": "olmamalı"}
LEVELS = {"kirmizi": "Kırmızı çizgi", "uyari": "Uyarı"}
STATES = {"oneri": "Öneri (onay bekliyor)", "onayli": "Onaylı"}


def _pos_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "clause": r.clause, "scope": {"tip": r.scope_tip, "odeme": r.scope_odeme, "para": r.scope_para},
            "op": r.op, "opLabel": OPS.get(r.op, r.op), "value": json.loads(r.value_json) if r.value_json else None,
            "level": r.level, "levelLabel": LEVELS.get(r.level, r.level), "reason": r.reason, "state": r.state,
            "stateLabel": STATES.get(r.state, r.state), "createdBy": r.created_by,
            "approvedBy": r.approved_by, "approvedAt": r.approved_at.isoformat() if r.approved_at else None,
            "updatedBy": r.updated_by, "updatedAt": r.updated_at.isoformat() if r.updated_at else None}


def positions_stmt(tenant: str, state: Optional[str] = None) -> sa.Select:
    stmt = sa.select(POSITIONS).where(POSITIONS.c.tenant_id == tenant)
    if state:
        stmt = stmt.where(POSITIONS.c.state == state)
    return stmt.order_by(POSITIONS.c.clause, POSITIONS.c.id)


def positions(engine: sa.engine.Engine, tenant: str, state: Optional[str] = None) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        return [_pos_out(r) for r in c.execute(positions_stmt(tenant, state))]


def _pos_fields(b: dict[str, Any], valid_clause) -> dict[str, Any]:
    clause = str(b.get("clause") or "").strip()
    if not valid_clause(clause):
        raise StoreError("Madde geçerli değil.")
    op = str(b.get("op") or "")
    if op not in OPS:
        raise StoreError("Kural işlemi geçerli değil.")
    level = str(b.get("level") or "uyari")
    if level not in LEVELS:
        raise StoreError("Düzey geçerli değil.")
    value = b.get("value")
    if op in ("min", "max"):
        try:
            value = float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            raise StoreError("Sınır sayı olmalı.") from None
    elif op == "in":
        if not isinstance(value, list) or not value:
            raise StoreError("En az bir değer seçin.")
    elif op == "eq":
        if value is None or value == "":
            raise StoreError("Değer girin.")
    else:
        value = None

    def scope(k: str) -> Optional[int]:
        v = (b.get("scope") or {}).get(k)
        try:
            return None if v in (None, "") else int(v)
        except (TypeError, ValueError):
            raise StoreError("Kapsam geçerli değil.") from None

    reason = " ".join(str(b.get("reason") or "").split())[:2000] or None
    return {"clause": clause, "op": op, "level": level, "value_json": json.dumps(value, ensure_ascii=False),
            "scope_tip": scope("tip"), "scope_odeme": scope("odeme"), "scope_para": scope("para"), "reason": reason}


def save_position(engine: sa.engine.Engine, tenant: str, user: str, b: dict[str, Any], valid_clause,
                  pid: Optional[int] = None, state: str = "onayli") -> dict[str, Any]:
    """Kural yazılır. Elle yazılan kural onaylıdır (yazan yetkilidir); öneri üretimi `oneri` yazar."""
    vals = _pos_fields(b, valid_clause)
    ensure(engine)
    now = _now()
    with engine.begin() as c:
        if pid is None:
            extra = {"approved_by": user, "approved_at": now} if state == "onayli" else {}
            res = c.execute(POSITIONS.insert().values(tenant_id=tenant, state=state, created_by=user, created_at=now,
                                                      updated_by=user, updated_at=now, **extra, **vals))
            pid = res.inserted_primary_key[0]
        else:
            r = c.execute(sa.select(POSITIONS).where(POSITIONS.c.tenant_id == tenant, POSITIONS.c.id == int(pid))).first()
            if r is None:
                raise StoreError("Kural bulunamadı.", 404)
            c.execute(sa.update(POSITIONS).where(POSITIONS.c.id == r.id).values(updated_by=user, updated_at=now, **vals))
        return _pos_out(c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == pid)).first())


def approve_position(engine: sa.engine.Engine, tenant: str, user: str, pid: int) -> dict[str, Any]:
    ensure(engine)
    now = _now()
    with engine.begin() as c:
        r = c.execute(sa.select(POSITIONS).where(POSITIONS.c.tenant_id == tenant, POSITIONS.c.id == int(pid))).first()
        if r is None:
            raise StoreError("Kural bulunamadı.", 404)
        c.execute(sa.update(POSITIONS).where(POSITIONS.c.id == r.id).values(state="onayli", approved_by=user, approved_at=now,
                                                                            updated_by=user, updated_at=now))
        return _pos_out(c.execute(sa.select(POSITIONS).where(POSITIONS.c.id == r.id)).first())


def delete_position(engine: sa.engine.Engine, tenant: str, pid: int) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(POSITIONS).where(POSITIONS.c.tenant_id == tenant, POSITIONS.c.id == int(pid))).first()
        if r is None:
            raise StoreError("Kural bulunamadı.", 404)
        c.execute(POSITIONS.delete().where(POSITIONS.c.id == r.id))
    return _pos_out(r)


__all__ = ["POSITIONS", "OPS", "LEVELS", "STATES", "approve_position", "delete_position", "positions", "positions_stmt",
           "save_position", "REVIEWS", "REVIEW_STATUS", "CLOSED", "StoreError", "attach", "delete_review", "ensure", "reviews",
           "reviews_stmt", "save_review", "sig"]
