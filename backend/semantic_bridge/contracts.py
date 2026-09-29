"""M6 Sözleşmeler: portalda tutulan sözleşme kaydı, zeyilname, ödeme takvimi, hakediş ve şablon kütüphanesi.

CRM sözleşme portföyünün kaynağıdır ve salt okunur kalır (köprünün CRM'e yazma yolu yok; Web API yetkisi
müşteriden bekleniyor). Portal şunları kendi tablolarında tutar:

- **Kayıt** (`semantic_contracts`): portalda açılan taslak ya da CRM sözleşmesinin portalda düzenlenen hâli.
  CRM'den gelen kayıt ilk düzenlemede CRM değerleriyle açılır (`crm_terms` o anın kopyasıdır); ekran portal
  değeri ile CRM değeri arasındaki farkı gösterir ki CRM'e elle işlenebilsin.
- **Durum**: taslak → imza sürecinde → yürürlükte → süresi bitti / feshedildi; taslak iptal edilebilir.
  Taslak ve imza sürecindeki sözleşmenin şartları serbestçe düzenlenir. Yürürlükteki sözleşmenin şartı
  **zeyilnameyle** değişir; kayıt hatası düzeltmesi gerekçe ister ve geçmişe «düzeltme» diye yazılır.
- **Zeyilname** (`semantic_contract_addenda`): değişen alanlar (eski → yeni) + yürürlük tarihi + gerekçe.
  İmzalandı işaretlenince yama sözleşmeye uygulanır; eski değer imza anındaki değerdir.
- **Ödeme takvimi** (`semantic_contract_payments`): avans, tek ödeme, hakediş ve diğer ödemeler; vade,
  tutar, ödendi bilgisi (tarih, tutar, dekont/fiş no).
- **Hakediş** (`semantic_contract_statements`): dönem hesabı (bkz. `contracts_royalty`); taslak kaydedilir,
  onaylanınca ödeme takvimine hakediş satırı düşer. Onaylı hakediş değişmez, iptal edilip yenisi açılır.
- **Şablon** (`semantic_contract_templates`): sözleşme, zeyilname ve hakediş bildirimi metinleri; metin ya da
  Word dosyası, `{{alan}}` yer tutucularıyla. Her kayıt değişikliği sürümü bir artırır.

Her değişiklik `semantic_contract_events`e (sözleşmenin geçmişi) ve köprünün değişiklik kaydına yazılır.
"""
from __future__ import annotations

import logging
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import contracts_docs as D
from semantic_bridge import crm_rights
from semantic_bridge import contracts_royalty as R
from semantic_bridge import contracts_terms as T
from semantic_bridge.contracts_terms import ContractError

log = logging.getLogger("semantic.contracts")

_md = sa.MetaData()
_MONEY = sa.Numeric(18, 2, asdecimal=False)

RECORDS = sa.Table(
    "semantic_contracts", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("crm_id", sa.String(40)),
    sa.Column("no", sa.String(60), nullable=False),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("terms", sa.JSON, nullable=False),
    sa.Column("crm_terms", sa.JSON),
    sa.Column("template_id", sa.String(40)),
    sa.Column("body", sa.Text),
    sa.Column("body_edited", sa.Boolean, nullable=False, default=False),
    sa.Column("version", sa.Integer, nullable=False, default=1),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("signed_at", sa.String(10)),
    sa.UniqueConstraint("tenant_id", "no", name="uq_semantic_contracts_no"),
    sa.UniqueConstraint("tenant_id", "crm_id", name="uq_semantic_contracts_crm"),
)

EVENTS = sa.Table(
    "semantic_contract_events", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("contract_id", sa.String(40), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("actor", sa.String(120), nullable=False),
    sa.Column("action", sa.String(24), nullable=False),
    sa.Column("summary", sa.Text),
    sa.Column("changes", sa.JSON),
)

ADDENDA = sa.Table(
    "semantic_contract_addenda", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("contract_id", sa.String(40), nullable=False, index=True),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("effective_on", sa.String(10)),
    sa.Column("reason", sa.Text),
    sa.Column("changes", sa.JSON, nullable=False),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("template_id", sa.String(40)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("signed_by", sa.String(120)),
    sa.Column("signed_on", sa.String(10)),
    sa.UniqueConstraint("contract_id", "seq", name="uq_semantic_contract_addenda_seq"),
)

PAYMENTS = sa.Table(
    "semantic_contract_payments", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("contract_id", sa.String(40), nullable=False, index=True),
    sa.Column("kind", sa.String(20), nullable=False),
    sa.Column("party", sa.String(200)),
    sa.Column("due_on", sa.String(10)),
    sa.Column("amount", _MONEY),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("period_start", sa.String(10)),
    sa.Column("period_end", sa.String(10)),
    sa.Column("statement_id", sa.String(40)),
    sa.Column("paid_on", sa.String(10)),
    sa.Column("paid_amount", _MONEY),
    sa.Column("paid_ref", sa.String(120)),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_semantic_contract_payments_due", "tenant_id", "status", "due_on"),
)

STATEMENTS = sa.Table(
    "semantic_contract_statements", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("contract_id", sa.String(40), nullable=False, index=True),
    sa.Column("period_start", sa.String(10), nullable=False),
    sa.Column("period_end", sa.String(10), nullable=False),
    sa.Column("status", sa.String(20), nullable=False),
    sa.Column("calc", sa.JSON, nullable=False),
    sa.Column("gross", _MONEY),
    sa.Column("advance_offset", _MONEY),
    sa.Column("carry_out", _MONEY),
    sa.Column("net", _MONEY),
    sa.Column("currency", sa.String(3), nullable=False),
    sa.Column("fingerprint", sa.String(32)),
    sa.Column("payment_id", sa.String(40)),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("cancelled_by", sa.String(120)),
    sa.Column("cancelled_at", sa.DateTime(timezone=True)),
)

TEMPLATES = sa.Table(
    "semantic_contract_templates", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("target", sa.String(20), nullable=False),
    sa.Column("kind", sa.String(20)),
    sa.Column("description", sa.Text),
    sa.Column("body", sa.Text),
    sa.Column("docx", sa.LargeBinary),
    sa.Column("docx_name", sa.String(200)),
    sa.Column("version", sa.Integer, nullable=False, default=1),
    sa.Column("active", sa.Boolean, nullable=False, default=True),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

PAYMENT_KINDS = {"avans": "Avans", "tek-odeme": "Tek ödeme", "hakedis": "Hakediş", "diger": "Diğer"}
PAYMENT_STATUSES = {"planlandi": "Planlandı", "odendi": "Ödendi", "iptal": "İptal"}
ADDENDUM_STATUSES = {"taslak": "Taslak", "imzalandi": "İmzalandı", "iptal": "İptal"}
STATEMENT_STATUSES = {"taslak": "Taslak", "onaylandi": "Onaylandı", "iptal": "İptal"}

_ready: set[int] = set()
_lock = threading.Lock()
_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_PID = re.compile(r"^[0-9a-f]{32}$")


class NotFound(ContractError):
    def __init__(self, message: str = "Kayıt bulunamadı."):
        super().__init__(message, 404)


class Conflict(ContractError):
    def __init__(self, message: str):
        super().__init__(message, 409)


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return str(v)


def _new_id() -> str:
    return uuid.uuid4().hex


def _today() -> date:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=3))).date()


# ------------------------------------------------------------------------------------------ kayıt

def is_crm_id(key: str) -> bool:
    return bool(_GUID.match(key or ""))


def _record(r: Any) -> dict[str, Any]:
    terms = r.terms or {}
    exp = bool(r.status == "yururlukte" and terms.get("end") and not terms.get("openEnded") and terms["end"] < _today().isoformat())
    return {
        "id": r.id, "crmId": r.crm_id, "no": r.no, "status": r.status, "statusLabel": T.STATUSES.get(r.status, r.status),
        "expired": exp, "terms": terms, "crmTerms": r.crm_terms, "templateId": r.template_id,
        "body": r.body, "bodyEdited": bool(r.body_edited), "version": r.version,
        "createdBy": r.created_by, "createdAt": _iso(r.created_at), "updatedBy": r.updated_by,
        "updatedAt": _iso(r.updated_at), "signedAt": r.signed_at,
    }


def record_stmt(tenant: str, key: str) -> sa.Select:
    """Bir sözleşme kaydı: CRM kimliğiyle ya da portal kimliğiyle (sorgu bilgisinde gösterilen ifade budur)."""
    q = sa.select(RECORDS).where(RECORDS.c.tenant_id == tenant)
    if is_crm_id(key):
        return q.where(RECORDS.c.crm_id == key.lower())
    if _PID.match(key or ""):
        return q.where(RECORDS.c.id == key)
    raise ContractError("Sözleşme kimliği geçerli değil.")


def _get(c: sa.engine.Connection, tenant: str, key: str, *, lock: bool = False) -> Any:
    q = record_stmt(tenant, key)
    if lock:
        q = q.with_for_update()
    return c.execute(q).first()


def find(engine: sa.engine.Engine, tenant: str, key: str) -> Optional[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        r = _get(c, tenant, key)
    return _record(r) if r else None


def _event(c: sa.engine.Connection, tenant: str, contract_id: str, actor: str, action: str, summary: str,
           changes: Any = None) -> None:
    c.execute(EVENTS.insert().values(tenant_id=tenant, contract_id=contract_id, at=_now(), actor=actor,
                                     action=action, summary=summary[:2000], changes=changes))


def events_stmt(tenant: str, contract_id: str) -> sa.Select:
    return (sa.select(EVENTS).where(EVENTS.c.tenant_id == tenant, EVENTS.c.contract_id == contract_id)
            .order_by(EVENTS.c.at.desc(), EVENTS.c.id.desc()))


def events(engine: sa.engine.Engine, tenant: str, contract_id: str) -> list[dict[str, Any]]:
    """Sözleşmenin bütün geçmişi, yeniden eskiye. Satır tavanı yok: eski kayıt kesilirse geçmiş eksik görünür."""
    with engine.connect() as c:
        rows = c.execute(events_stmt(tenant, contract_id)).all()
    return [{"at": _iso(r.at), "actor": r.actor, "action": r.action, "summary": r.summary, "changes": r.changes} for r in rows]


def _next_no(c: sa.engine.Connection, tenant: str, year: int) -> str:
    prefix = f"TS-{year}-"
    rows = c.execute(sa.select(RECORDS.c.no).where(RECORDS.c.tenant_id == tenant, RECORDS.c.no.like(prefix + "%"))).scalars().all()
    n = max([int(x[len(prefix):]) for x in rows if x[len(prefix):].isdigit()] + [0]) + 1
    return f"{prefix}{n:04d}"


def create_draft(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    ensure(engine)
    terms = T.clean(body.get("terms") or {})
    if not terms["title"]:
        raise ContractError("Sözleşmeye bir ad verin (ör. kitap adı ve hak sahibi).")
    now = _now()
    for attempt in range(3):
        try:
            with engine.begin() as c:
                rid = _new_id()
                no = _next_no(c, tenant, _today().year)
                c.execute(RECORDS.insert().values(
                    id=rid, tenant_id=tenant, crm_id=None, no=no, status="taslak", terms=terms, crm_terms=None,
                    template_id=None, body=None, body_edited=False, version=1, created_by=user, created_at=now,
                    updated_by=user, updated_at=now, signed_at=None))
                _event(c, tenant, rid, user, "olustur", f"{no} taslağı açıldı.")
            break
        except sa.exc.IntegrityError:
            if attempt == 2:
                raise Conflict("Sözleşme numarası verilemedi; tekrar deneyin.")
    rec = find(engine, tenant, rid)
    if body.get("templateId"):
        rec = render_body(engine, tenant, user, rid, str(body["templateId"]))
    return rec


def adopt_crm(engine: sa.engine.Engine, tenant: str, user: str, crm_id: str, crm: dict[str, Any]) -> dict[str, Any]:
    """CRM sözleşmesini portal kaydına alır (bir kez). `crm` = `crm_contract` çıktısı."""
    ensure(engine)
    crm_id = crm_id.lower()
    existing = find(engine, tenant, crm_id)
    if existing:
        return existing
    now = _now()
    base_no = (crm.get("no") or f"CRM-{crm_id[:8]}")[:40]
    # CRM'de iki sözleşme aynı adı taşıyabilir; numara çakışırsa kimliğin başı eklenir.
    for no in (base_no, f"{base_no} ({crm_id[:8]})"):
        try:
            with engine.begin() as c:
                rid = _new_id()
                c.execute(RECORDS.insert().values(
                    id=rid, tenant_id=tenant, crm_id=crm_id, no=no,
                    status=crm.get("status") or "yururlukte", terms=crm["terms"], crm_terms=crm["terms"], template_id=None,
                    body=None, body_edited=False, version=1, created_by=user, created_at=now, updated_by=user,
                    updated_at=now, signed_at=crm["terms"].get("start")))
                _event(c, tenant, rid, user, "crm-al", "CRM kaydı portala alındı; bundan sonraki değişiklikler portalda tutulur.")
            break
        except sa.exc.IntegrityError:
            if find(engine, tenant, crm_id):
                break  # aynı anda iki kişi aldı; ikincisi ilkini okur
    rec = find(engine, tenant, crm_id)
    if rec is None:
        raise Conflict("CRM sözleşmesi portala alınamadı; tekrar deneyin.")
    return rec


def _check_version(r: Any, version: Any) -> None:
    if version is not None and int(version) != int(r.version):
        raise Conflict(f"Sözleşme siz açtıktan sonra {r.updated_by} tarafından değiştirildi; sayfayı yenileyip tekrar deneyin.")


def update_terms(engine: sa.engine.Engine, tenant: str, user: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    patch = body.get("terms") or {}
    reason = " ".join(str(body.get("reason") or "").split())[:1000]
    with engine.begin() as c:
        r = _get(c, tenant, key, lock=True)
        if not r:
            raise NotFound("Sözleşme portalda yok.")
        _check_version(r, body.get("version"))
        new = T.clean(patch, r.terms)
        if not new["title"]:
            raise ContractError("Sözleşme adı boş olamaz.")
        changes = T.diff(r.terms, new)
        if not changes:
            return _record(r)
        correction = r.status not in T.FREE_EDIT
        if correction and not reason:
            raise ContractError("Bu sözleşme «" + T.STATUSES[r.status] + "»; şart değişikliği zeyilnameyle yapılır. "
                                "Kayıt hatasını düzeltiyorsanız gerekçe yazın.")
        c.execute(RECORDS.update().where(RECORDS.c.id == r.id).values(
            terms=new, version=r.version + 1, updated_by=user, updated_at=_now()))
        names = ", ".join(ch["label"] for ch in changes[:6]) + (" …" if len(changes) > 6 else "")
        _event(c, tenant, r.id, user, "duzeltme" if correction else "duzenle",
               (f"Kayıt düzeltmesi: {reason}. " if correction else "") + f"Değişen: {names}.", changes)
    return find(engine, tenant, r.id)


def set_status(engine: sa.engine.Engine, tenant: str, user: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    to = str(body.get("status") or "")
    note = " ".join(str(body.get("note") or "").split())[:1000]
    if to not in T.STATUSES:
        raise ContractError("Geçersiz durum.")
    with engine.begin() as c:
        r = _get(c, tenant, key, lock=True)
        if not r:
            raise NotFound("Sözleşme portalda yok.")
        _check_version(r, body.get("version"))
        if to == r.status:
            return _record(r)
        if to not in T.TRANSITIONS.get(r.status, ()):
            raise ContractError(f"«{T.STATUSES[r.status]}» durumundan «{T.STATUSES[to]}» durumuna geçilemez.")
        values: dict[str, Any] = {"status": to, "version": r.version + 1, "updated_by": user, "updated_at": _now()}
        if to == "yururlukte":
            missing = [m for m in (("Başlangıç tarihi", r.terms.get("start")), ("Taraf", r.terms.get("parties")))
                       if not m[1]]
            if missing:
                raise ContractError("Yürürlüğe almadan önce girin: " + ", ".join(m[0] for m in missing) + ".")
            signed = str(body.get("signedOn") or "")[:10] or r.signed_at or _today().isoformat()
            values["signed_at"] = T._day(signed, "İmza tarihi")
        if to == "feshedildi" and not note:
            raise ContractError("Fesih için gerekçe yazın.")
        c.execute(RECORDS.update().where(RECORDS.c.id == r.id).values(**values))
        _event(c, tenant, r.id, user, "durum", f"Durum: {T.STATUSES[r.status]} → {T.STATUSES[to]}." + (f" {note}" if note else ""),
               [{"field": "status", "label": "Durum", "old": r.status, "new": to}])
    return find(engine, tenant, r.id)


def set_body(engine: sa.engine.Engine, tenant: str, user: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    text = str(body.get("body") or "")
    if len(text) > 400_000:
        raise ContractError("Sözleşme metni çok uzun.")
    with engine.begin() as c:
        r = _get(c, tenant, key, lock=True)
        if not r:
            raise NotFound("Sözleşme portalda yok.")
        _check_version(r, body.get("version"))
        if r.status not in T.FREE_EDIT:
            raise ContractError("İmzalanmış sözleşmenin metni değişmez; değişiklik zeyilnameyle yapılır.")
        c.execute(RECORDS.update().where(RECORDS.c.id == r.id).values(
            body=text, body_edited=True, version=r.version + 1, updated_by=user, updated_at=_now()))
        _event(c, tenant, r.id, user, "metin", "Sözleşme metni elle düzenlendi.")
    return find(engine, tenant, r.id)


def render_body(engine: sa.engine.Engine, tenant: str, user: str, key: str, template_id: str) -> dict[str, Any]:
    tpl = template(engine, tenant, template_id, with_docx=False)
    if tpl["target"] != "sozlesme":
        raise ContractError("Bu şablon sözleşme metni için değil.")
    with engine.begin() as c:
        r = _get(c, tenant, key, lock=True)
        if not r:
            raise NotFound("Sözleşme portalda yok.")
        if r.status not in T.FREE_EDIT:
            raise ContractError("İmzalanmış sözleşmenin metni şablondan yeniden üretilmez.")
        text, _ = D.fill(tpl["body"] or "", D.values(r.no, r.terms))
        c.execute(RECORDS.update().where(RECORDS.c.id == r.id).values(
            template_id=tpl["id"], body=text if tpl["body"] else None, body_edited=False,
            version=r.version + 1, updated_by=user, updated_at=_now()))
        _event(c, tenant, r.id, user, "sablon", f"Metin «{tpl['name']}» şablonunun {tpl['version']}. sürümünden üretildi.")
    return find(engine, tenant, r.id)


def _records_where(tenant: str, status: str = "", source: str = "") -> sa.Select:
    stmt = sa.select(RECORDS).where(RECORDS.c.tenant_id == tenant)
    if status:
        stmt = stmt.where(RECORDS.c.status == status)
    if source == "portal":
        stmt = stmt.where(RECORDS.c.crm_id.is_(None))
    elif source == "crm":
        stmt = stmt.where(RECORDS.c.crm_id.is_not(None))
    return stmt


def records_stmt(tenant: str, status: str = "", source: str = "") -> sa.Select:
    """Portal kayıtları listesinin okuması (arama süzgeci satırlar okunduktan sonra uygulanır)."""
    return _records_where(tenant, status, source).order_by(RECORDS.c.updated_at.desc())


def records_payments_stmt(tenant: str, status: str = "", source: str = "") -> sa.Select:
    """Listedeki kayıtların bekleyen ödemeleri (sayı, vadesi geçen, sıradaki vade bunlardan sayılır)."""
    return payment_totals_stmt(tenant, _records_where(tenant, status, source).with_only_columns(RECORDS.c.id))


def list_records(engine: sa.engine.Engine, tenant: str, *, q: str = "", status: str = "", source: str = "") -> list[dict[str, Any]]:
    """Portal kayıtlarının hepsi. Satır tavanı yok: arama süzgeci satırlar okunduktan sonra uygulandığı için tavan,
    eski bir sözleşmeyi aramada da bulunmaz yapıyordu."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(records_stmt(tenant, status, source)).all()
        pay = _payment_totals(c, tenant, _records_where(tenant, status, source).with_only_columns(RECORDS.c.id))
    out = []
    needle = q.strip().lower()
    for r in rows:
        rec = _record(r)
        rec.pop("body", None)
        if needle:
            hay = " ".join([rec["no"], rec["terms"].get("title", "")] + [p["name"] for p in rec["terms"].get("parties", [])]
                           + [b["title"] for b in rec["terms"].get("books", [])]).lower()
            if needle not in hay:
                continue
        rec["payments"] = pay.get(r.id)
        out.append(rec)
    return out


def crm_state_stmt(tenant: str, crm_ids: list[str]) -> sa.Select:
    ids = [i.lower() for i in crm_ids if is_crm_id(i)]
    return sa.select(RECORDS).where(RECORDS.c.tenant_id == tenant, RECORDS.c.crm_id.in_(ids))


def crm_state(engine: sa.engine.Engine, tenant: str, crm_ids: list[str]) -> dict[str, dict[str, Any]]:
    """CRM listesindeki sözleşmelerden portalda kaydı olanlar: crm_id → {id, status, updatedAt, diff}."""
    ids = [i.lower() for i in crm_ids if is_crm_id(i)]
    if not ids:
        return {}
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(crm_state_stmt(tenant, ids)).all()
    return {r.crm_id: {"id": r.id, "status": r.status, "statusLabel": T.STATUSES.get(r.status), "updatedAt": _iso(r.updated_at),
                       "diff": len(T.diff(r.crm_terms or {}, r.terms or {}))} for r in rows}


# ------------------------------------------------------------------------------------------ zeyilname

def _addendum(r: Any, no: str) -> dict[str, Any]:
    return {"id": r.id, "contractId": r.contract_id, "seq": r.seq, "no": f"{no}/Z-{r.seq}", "title": r.title,
            "effectiveOn": r.effective_on, "reason": r.reason, "changes": r.changes or [], "status": r.status,
            "statusLabel": ADDENDUM_STATUSES.get(r.status), "templateId": r.template_id,
            "createdBy": r.created_by, "createdAt": _iso(r.created_at), "updatedBy": r.updated_by,
            "updatedAt": _iso(r.updated_at), "signedBy": r.signed_by, "signedOn": r.signed_on}


def _changes(terms: dict[str, Any], raw: Any) -> list[dict[str, Any]]:
    """İstemcinin gönderdiği {alan: yeni değer} → doğrulanmış değişiklik listesi (eski değer bugünkü)."""
    if not isinstance(raw, dict) or not raw:
        raise ContractError("Zeyilnamede en az bir değişiklik olmalı.")
    patch = T.patch_of([{"field": k, "new": v} for k, v in raw.items()])
    new = T.clean(patch, terms)
    changes = T.diff(terms, new)
    if not changes:
        raise ContractError("Girilen değerler sözleşmedeki değerlerle aynı; değişiklik yok.")
    return changes


def addenda_stmt(tenant: str, contract_id: str) -> sa.Select:
    return sa.select(ADDENDA).where(ADDENDA.c.tenant_id == tenant, ADDENDA.c.contract_id == contract_id).order_by(ADDENDA.c.seq)


def addenda(engine: sa.engine.Engine, tenant: str, contract_id: str, no: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(addenda_stmt(tenant, contract_id)).all()
    return [_addendum(r, no) for r in rows]


def _addendum_fields(body: dict[str, Any]) -> dict[str, Any]:
    title = " ".join(str(body.get("title") or "").split())[:300]
    if not title:
        raise ContractError("Zeyilnamenin konusunu yazın (ör. «Süre uzatımı»).")
    return {"title": title, "effective_on": T._day(body.get("effectiveOn"), "Yürürlük tarihi"),
            "reason": str(body.get("reason") or "").strip()[:4000] or None,
            "template_id": str(body.get("templateId") or "")[:40] or None}


def create_addendum(engine: sa.engine.Engine, tenant: str, user: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        r = _get(c, tenant, key, lock=True)
        if not r:
            raise NotFound("Sözleşme portalda yok.")
        if r.status in ("taslak", "imzada", "iptal"):
            raise ContractError("Zeyilname imzalanmış sözleşmeye yapılır; taslağı doğrudan düzenleyin.")
        fields = _addendum_fields(body)
        changes = _changes(r.terms, body.get("changes"))
        seq = (c.execute(sa.select(sa.func.max(ADDENDA.c.seq)).where(ADDENDA.c.contract_id == r.id)).scalar() or 0) + 1
        now = _now()
        aid = _new_id()
        c.execute(ADDENDA.insert().values(id=aid, tenant_id=tenant, contract_id=r.id, seq=seq, changes=changes,
                                          status="taslak", created_by=user, created_at=now, updated_by=user,
                                          updated_at=now, **fields))
        _event(c, tenant, r.id, user, "zeyilname", f"Z-{seq} «{fields['title']}» taslağı açıldı.", changes)
        a = c.execute(sa.select(ADDENDA).where(ADDENDA.c.id == aid)).first()
    return _addendum(a, r.no)


def _get_addendum(c: sa.engine.Connection, tenant: str, addendum_id: str, lock: bool = False) -> tuple[Any, Any]:
    q = sa.select(ADDENDA).where(ADDENDA.c.tenant_id == tenant, ADDENDA.c.id == addendum_id)
    a = c.execute(q.with_for_update() if lock else q).first()
    if not a:
        raise NotFound("Zeyilname bulunamadı.")
    r = c.execute(sa.select(RECORDS).where(RECORDS.c.id == a.contract_id).with_for_update() if lock else
                  sa.select(RECORDS).where(RECORDS.c.id == a.contract_id)).first()
    return a, r


def update_addendum(engine: sa.engine.Engine, tenant: str, user: str, addendum_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        a, r = _get_addendum(c, tenant, addendum_id, lock=True)
        if a.status != "taslak":
            raise ContractError("Yalnız taslak zeyilname düzenlenir.")
        fields = _addendum_fields({"title": a.title, "effectiveOn": a.effective_on, "reason": a.reason,
                                   "templateId": a.template_id, **body})
        changes = _changes(r.terms, body["changes"]) if "changes" in body else a.changes
        c.execute(ADDENDA.update().where(ADDENDA.c.id == a.id).values(changes=changes, updated_by=user, updated_at=_now(), **fields))
        _event(c, tenant, r.id, user, "zeyilname", f"Z-{a.seq} taslağı düzenlendi.", changes)
        a = c.execute(sa.select(ADDENDA).where(ADDENDA.c.id == a.id)).first()
    return _addendum(a, r.no)


def set_addendum_status(engine: sa.engine.Engine, tenant: str, user: str, addendum_id: str, body: dict[str, Any]) -> dict[str, Any]:
    to = str(body.get("status") or "")
    if to not in ("imzalandi", "iptal"):
        raise ContractError("Zeyilname yalnız imzalandı ya da iptal işaretlenir.")
    with engine.begin() as c:
        a, r = _get_addendum(c, tenant, addendum_id, lock=True)
        if a.status != "taslak":
            raise ContractError(f"Zeyilname zaten «{ADDENDUM_STATUSES[a.status]}».")
        values: dict[str, Any] = {"status": to, "updated_by": user, "updated_at": _now()}
        if to == "imzalandi":
            signed = T._day(body.get("signedOn") or _today().isoformat(), "İmza tarihi")
            patch = T.patch_of(a.changes or [])
            new = T.clean(patch, r.terms)
            applied = T.diff(r.terms, new)  # eski değer imza anındaki değer
            if not applied:
                raise ContractError("Zeyilnamedeki değerler sözleşmeye zaten işlenmiş; iptal edin.")
            rec_values: dict[str, Any] = {"terms": new, "version": r.version + 1, "updated_by": user, "updated_at": _now()}
            reopened = r.status == "sona-erdi" and (new.get("openEnded") or (new.get("end") or "") >= _today().isoformat())
            if reopened:
                rec_values["status"] = "yururlukte"
            c.execute(RECORDS.update().where(RECORDS.c.id == r.id).values(**rec_values))
            values.update(changes=applied, signed_by=user, signed_on=signed)
            _event(c, tenant, r.id, user, "zeyilname", f"Z-{a.seq} «{a.title}» imzalandı ({T.day_tr(signed)}); şartlara işlendi."
                   + (" Sözleşme yeniden yürürlükte." if reopened else ""), applied)
        else:
            _event(c, tenant, r.id, user, "zeyilname", f"Z-{a.seq} «{a.title}» iptal edildi.")
        c.execute(ADDENDA.update().where(ADDENDA.c.id == a.id).values(**values))
        a = c.execute(sa.select(ADDENDA).where(ADDENDA.c.id == a.id)).first()
    return _addendum(a, r.no)


# ------------------------------------------------------------------------------------------ ödeme takvimi

def _payment(r: Any) -> dict[str, Any]:
    overdue = r.status == "planlandi" and r.due_on and r.due_on < _today().isoformat()
    return {"id": r.id, "contractId": r.contract_id, "kind": r.kind, "kindLabel": PAYMENT_KINDS.get(r.kind),
            "party": r.party, "dueOn": r.due_on, "amount": r.amount, "currency": r.currency,
            "status": r.status, "statusLabel": PAYMENT_STATUSES.get(r.status), "overdue": bool(overdue),
            "periodStart": r.period_start, "periodEnd": r.period_end, "statementId": r.statement_id,
            "paidOn": r.paid_on, "paidAmount": r.paid_amount, "paidRef": r.paid_ref, "note": r.note,
            "createdBy": r.created_by, "updatedBy": r.updated_by, "updatedAt": _iso(r.updated_at)}


def payments_stmt(tenant: str, contract_id: str) -> sa.Select:
    return (sa.select(PAYMENTS).where(PAYMENTS.c.tenant_id == tenant, PAYMENTS.c.contract_id == contract_id)
            .order_by(sa.func.coalesce(PAYMENTS.c.due_on, "9999"), PAYMENTS.c.created_at))


def payments(engine: sa.engine.Engine, tenant: str, contract_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(payments_stmt(tenant, contract_id)).all()
    return [_payment(r) for r in rows]


def payment_totals_stmt(tenant: str, ids: sa.Select) -> sa.Select:
    return (sa.select(PAYMENTS.c.contract_id, PAYMENTS.c.status, PAYMENTS.c.due_on)
            .where(PAYMENTS.c.tenant_id == tenant, PAYMENTS.c.contract_id.in_(ids), PAYMENTS.c.status == "planlandi"))


def _payment_totals(c: sa.engine.Connection, tenant: str, ids: sa.Select) -> dict[str, dict[str, Any]]:
    """`ids`: sözleşme kimliği seçen alt sorgu (kimlik listesi değil; binlerce bağ değişkeni sürücü sınırına takılır)."""
    rows = c.execute(payment_totals_stmt(tenant, ids)).all()
    out: dict[str, dict[str, Any]] = {}
    today = _today().isoformat()
    for r in rows:
        acc = out.setdefault(r.contract_id, {"planned": 0, "overdue": 0, "next": None})
        acc["planned"] += 1
        if r.due_on and r.due_on < today:
            acc["overdue"] += 1
        if r.due_on and (acc["next"] is None or r.due_on < acc["next"]):
            acc["next"] = r.due_on
    return out


def _payment_fields(body: dict[str, Any], terms: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not partial or "kind" in body:
        kind = str(body.get("kind") or "diger")
        if kind not in PAYMENT_KINDS:
            raise ContractError("Geçersiz ödeme türü.")
        out["kind"] = kind
    if not partial or "party" in body:
        out["party"] = " ".join(str(body.get("party") or "").split())[:200] or None
    if not partial or "dueOn" in body:
        out["due_on"] = T._day(body.get("dueOn"), "Vade")
    if not partial or "amount" in body:
        out["amount"] = T._num(body.get("amount"), "Tutar")
    if not partial or "currency" in body:
        cur = str(body.get("currency") or terms.get("currency") or "TRY")
        if cur not in T.CURRENCIES:
            raise ContractError("Geçersiz para birimi.")
        out["currency"] = cur
    if not partial or "note" in body:
        out["note"] = str(body.get("note") or "").strip()[:2000] or None
    return out


def add_payment(engine: sa.engine.Engine, tenant: str, user: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        r = _get(c, tenant, key, lock=True)
        if not r:
            raise NotFound("Sözleşme portalda yok.")
        if r.status == "iptal":
            raise ContractError("İptal edilmiş sözleşmeye ödeme eklenmez.")
        f = _payment_fields(body, r.terms)
        if f["kind"] == "hakedis":
            raise ContractError("Hakediş ödemesi hakediş onaylanınca kendiliğinden eklenir.")
        if f["amount"] is None:
            raise ContractError("Tutar girin.")
        now = _now()
        pid = _new_id()
        c.execute(PAYMENTS.insert().values(id=pid, tenant_id=tenant, contract_id=r.id, status="planlandi",
                                           created_by=user, created_at=now, updated_by=user, updated_at=now, **f))
        _event(c, tenant, r.id, user, "odeme", f"Ödeme planına eklendi: {PAYMENT_KINDS[f['kind']]} "
               f"{T.money(f['amount'], f['currency'])}" + (f", vade {T.day_tr(f['due_on'])}" if f["due_on"] else "") + ".")
        row = c.execute(sa.select(PAYMENTS).where(PAYMENTS.c.id == pid)).first()
    return _payment(row)


def _get_payment(c: sa.engine.Connection, tenant: str, payment_id: str) -> Any:
    p = c.execute(sa.select(PAYMENTS).where(PAYMENTS.c.tenant_id == tenant, PAYMENTS.c.id == payment_id).with_for_update()).first()
    if not p:
        raise NotFound("Ödeme bulunamadı.")
    return p


def update_payment(engine: sa.engine.Engine, tenant: str, user: str, payment_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        p = _get_payment(c, tenant, payment_id)
        if p.status != "planlandi":
            raise ContractError(f"«{PAYMENT_STATUSES[p.status]}» ödeme düzenlenmez.")
        r = c.execute(sa.select(RECORDS).where(RECORDS.c.id == p.contract_id)).first()
        f = _payment_fields(body, r.terms, partial=True)
        if p.kind == "hakedis":
            f = {k: v for k, v in f.items() if k in ("due_on", "note")}  # tutar hakedişten gelir
        if "kind" in f and f["kind"] == "hakedis":
            raise ContractError("Ödeme hakedişe çevrilemez.")
        if "amount" in f and f["amount"] is None:
            raise ContractError("Tutar girin.")
        c.execute(PAYMENTS.update().where(PAYMENTS.c.id == p.id).values(updated_by=user, updated_at=_now(), **f))
        _event(c, tenant, p.contract_id, user, "odeme", f"{PAYMENT_KINDS[p.kind]} ödemesi düzenlendi.",
               [{"field": k, "old": getattr(p, k), "new": v} for k, v in f.items() if getattr(p, k) != v])
        row = c.execute(sa.select(PAYMENTS).where(PAYMENTS.c.id == p.id)).first()
    return _payment(row)


def mark_paid(engine: sa.engine.Engine, tenant: str, user: str, payment_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        p = _get_payment(c, tenant, payment_id)
        if p.status != "planlandi":
            raise ContractError(f"Ödeme zaten «{PAYMENT_STATUSES[p.status]}».")
        paid_on = T._day(body.get("paidOn") or _today().isoformat(), "Ödeme tarihi")
        amount = T._num(body.get("paidAmount") if body.get("paidAmount") not in (None, "") else p.amount, "Ödenen tutar")
        if amount is None:
            raise ContractError("Ödenen tutarı girin.")
        ref = " ".join(str(body.get("paidRef") or "").split())[:120] or None
        c.execute(PAYMENTS.update().where(PAYMENTS.c.id == p.id).values(
            status="odendi", paid_on=paid_on, paid_amount=amount, paid_ref=ref, updated_by=user, updated_at=_now()))
        _event(c, tenant, p.contract_id, user, "odeme", f"{PAYMENT_KINDS[p.kind]} ödendi: {T.money(amount, p.currency)}, "
               f"{T.day_tr(paid_on)}" + (f", belge {ref}" if ref else "") + ".")
        row = c.execute(sa.select(PAYMENTS).where(PAYMENTS.c.id == p.id)).first()
    return _payment(row)


def cancel_payment(engine: sa.engine.Engine, tenant: str, user: str, payment_id: str, body: dict[str, Any]) -> dict[str, Any]:
    note = " ".join(str(body.get("note") or "").split())[:1000]
    with engine.begin() as c:
        p = _get_payment(c, tenant, payment_id)
        if p.status == "iptal":
            raise ContractError("Ödeme zaten iptal.")
        if p.status == "odendi" and not note:
            raise ContractError("Ödenmiş kaydı iptal etmek için gerekçe yazın (ör. hatalı giriş, iade).")
        if p.kind == "hakedis" and p.statement_id:
            st = c.execute(sa.select(STATEMENTS.c.status).where(STATEMENTS.c.id == p.statement_id)).scalar()
            if st == "onaylandi":
                raise ContractError("Bu ödeme onaylı bir hakedişe bağlı; önce hakedişi iptal edin.")
        c.execute(PAYMENTS.update().where(PAYMENTS.c.id == p.id).values(
            status="iptal", note=((p.note + "\n") if p.note else "") + (f"İptal: {note}" if note else "İptal"),
            updated_by=user, updated_at=_now()))
        _event(c, tenant, p.contract_id, user, "odeme", f"{PAYMENT_KINDS[p.kind]} ödemesi iptal edildi." + (f" {note}" if note else ""))
        row = c.execute(sa.select(PAYMENTS).where(PAYMENTS.c.id == p.id)).first()
    return _payment(row)


def plan_payments(engine: sa.engine.Engine, tenant: str, user: str, key: str) -> dict[str, Any]:
    """Şartlardan ödeme planı önerisi: avans ve tek ödeme satırları (yoksa eklenir). Hakediş satırları
    hakediş onaylanınca gelir; burada yalnız dönem vadeleri listelenir."""
    added = []
    with engine.begin() as c:
        r = _get(c, tenant, key, lock=True)
        if not r:
            raise NotFound("Sözleşme portalda yok.")
        t = r.terms
        cur = t.get("currency") or "TRY"
        existing = c.execute(sa.select(PAYMENTS.c.kind).where(PAYMENTS.c.contract_id == r.id, PAYMENTS.c.status != "iptal")).scalars().all()
        due = r.signed_at or t.get("start")
        payee = (t.get("parties") or [{}])[0].get("name") if t.get("parties") else None
        now = _now()
        for kind, amount, note in (("avans", t.get("advance"), "Sözleşme avansı"), ("tek-odeme", t.get("flatFee"), "Tek ödeme")):
            if not amount or kind in existing:
                continue
            if kind == "tek-odeme" and t.get("paymentType") != "tek":
                continue
            pid = _new_id()
            c.execute(PAYMENTS.insert().values(id=pid, tenant_id=tenant, contract_id=r.id, kind=kind, party=payee, due_on=due,
                                               amount=amount, currency=cur, status="planlandi", note=note, created_by=user,
                                               created_at=now, updated_by=user, updated_at=now))
            added.append(f"{PAYMENT_KINDS[kind]} {T.money(amount, cur)}")
        if added:
            _event(c, tenant, r.id, user, "odeme", "Şartlardan ödeme planı: " + ", ".join(added) + ".")
    return {"added": added, "periods": schedule_periods(t)}


def schedule_periods(t: dict[str, Any]) -> list[dict[str, Any]]:
    """Hakediş dönemleri ve vadeleri (bugüne kadar ve bir sonraki dönem)."""
    if t.get("paymentType") not in T.SALES_BASED + T.PRINT_BASED:
        return []
    horizon = _today() + timedelta(days=366)
    days = int(t.get("paymentDays") if t.get("paymentDays") is not None else 30)
    return [{"periodStart": a.isoformat(), "periodEnd": b.isoformat(), "dueOn": (b + timedelta(days=days)).isoformat()}
            for a, b in R.periods(t, horizon)]


def due_stmt(tenant: str, *, status: str = "planlandi", within: Optional[int] = None, kind: str = "") -> sa.Select:
    """Ödeme takviminin okuması (süzgeçler değerleriyle; vade sınırı bugün + `within` gün)."""
    stmt = (sa.select(PAYMENTS, RECORDS.c.no, RECORDS.c.terms, RECORDS.c.crm_id)
            .join(RECORDS, RECORDS.c.id == PAYMENTS.c.contract_id)
            .where(PAYMENTS.c.tenant_id == tenant))
    if status:
        stmt = stmt.where(PAYMENTS.c.status == status)
    if kind:
        stmt = stmt.where(PAYMENTS.c.kind == kind)
    if within is not None and status == "planlandi":
        stmt = stmt.where(sa.or_(PAYMENTS.c.due_on.is_(None), PAYMENTS.c.due_on <= (_today() + timedelta(days=int(within))).isoformat()))
    return stmt.order_by(sa.func.coalesce(PAYMENTS.c.due_on, "9999"), PAYMENTS.c.created_at)


def due_list(engine: sa.engine.Engine, tenant: str, *, status: str = "planlandi", within: Optional[int] = None,
             kind: str = "") -> dict[str, Any]:
    """Bütün sözleşmelerin ödeme takvimi (vadeye göre). Satır tavanı yok: toplamlar ve vadesi geçen sayısı
    ekrandaki listeyle aynı, eksiksiz kümeden hesaplanır."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(due_stmt(tenant, status=status, within=within, kind=kind)).all()
    items = []
    totals: dict[str, dict[str, float]] = {}
    for r in rows:
        p = _payment(r)
        p.update(contractNo=r.no, contractTitle=(r.terms or {}).get("title"), contractKey=r.crm_id or r.contract_id)
        items.append(p)
        tot = totals.setdefault(r.currency, {"amount": 0.0, "overdue": 0.0})
        tot["amount"] += float(r.amount or 0)
        if p["overdue"]:
            tot["overdue"] += float(r.amount or 0)
    return {"items": items, "totals": totals, "today": _today().isoformat()}


# ------------------------------------------------------------------------------------------ hakediş

def _statement(r: Any) -> dict[str, Any]:
    calc = r.calc or {}
    return {"id": r.id, "contractId": r.contract_id, "periodStart": r.period_start, "periodEnd": r.period_end,
            "status": r.status, "statusLabel": STATEMENT_STATUSES.get(r.status), "gross": r.gross,
            "advanceOffset": r.advance_offset, "carryOut": r.carry_out, "net": r.net, "currency": r.currency,
            "paymentId": r.payment_id, "note": r.note, "calc": calc,
            "createdBy": r.created_by, "createdAt": _iso(r.created_at), "approvedBy": r.approved_by,
            "approvedAt": _iso(r.approved_at), "cancelledBy": r.cancelled_by, "cancelledAt": _iso(r.cancelled_at)}


def statements_stmt(tenant: str, contract_id: str) -> sa.Select:
    return (sa.select(STATEMENTS).where(STATEMENTS.c.tenant_id == tenant, STATEMENTS.c.contract_id == contract_id)
            .order_by(STATEMENTS.c.period_start.desc(), STATEMENTS.c.created_at.desc()))


def statement_context_stmt(tenant: str, contract_id: str, period_start: str) -> sa.Select:
    """Önceki onaylı hakedişler: avanstan düşülen toplam ve devreden tutar bunlardan okunur."""
    return (sa.select(STATEMENTS).where(
        STATEMENTS.c.tenant_id == tenant, STATEMENTS.c.contract_id == contract_id,
        STATEMENTS.c.status == "onaylandi", STATEMENTS.c.period_start < period_start)
        .order_by(STATEMENTS.c.period_end))


def statements(engine: sa.engine.Engine, tenant: str, contract_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(statements_stmt(tenant, contract_id)).all()
    return [_statement(r) for r in rows]


def statement_context(engine: sa.engine.Engine, tenant: str, contract_id: str, period_start: str) -> dict[str, float]:
    """Önceki onaylı hakedişlerden: avanstan düşülen toplam ve bir önceki dönemden devreden eksi tutar."""
    with engine.connect() as c:
        rows = c.execute(statement_context_stmt(tenant, contract_id, period_start)).all()
    used = sum(float(r.advance_offset or 0) for r in rows)
    carry = float(rows[-1].carry_out or 0) if rows else 0.0
    return {"advanceUsed": used, "carryIn": carry}


def save_statement(engine: sa.engine.Engine, tenant: str, user: str, key: str, result: dict[str, Any], note: str = "") -> dict[str, Any]:
    with engine.begin() as c:
        r = _get(c, tenant, key, lock=True)
        if not r:
            raise NotFound("Sözleşme portalda yok.")
        clash = c.execute(sa.select(STATEMENTS.c.period_start, STATEMENTS.c.period_end).where(
            STATEMENTS.c.contract_id == r.id, STATEMENTS.c.status == "onaylandi",
            STATEMENTS.c.period_start <= result["periodEnd"], STATEMENTS.c.period_end >= result["periodStart"])).first()
        if clash:
            raise Conflict(f"{T.day_tr(clash.period_start)} – {T.day_tr(clash.period_end)} dönemi için onaylı hakediş var; "
                           "aynı satışa iki kez telif ödenmez.")
        now = _now()
        sid = _new_id()
        c.execute(STATEMENTS.insert().values(
            id=sid, tenant_id=tenant, contract_id=r.id, period_start=result["periodStart"], period_end=result["periodEnd"],
            status="taslak", calc=result, gross=result["gross"], advance_offset=result["advanceOffset"],
            carry_out=result["carryOut"], net=result["net"], currency=result["currency"],
            fingerprint=R.fingerprint(result), note=note.strip()[:2000] or None, created_by=user, created_at=now))
        _event(c, tenant, r.id, user, "hakedis", f"{T.day_tr(result['periodStart'])} – {T.day_tr(result['periodEnd'])} "
               f"hakedişi hesaplandı: net {T.money(result['net'], result['currency'])} (taslak).")
        row = c.execute(sa.select(STATEMENTS).where(STATEMENTS.c.id == sid)).first()
    return _statement(row)


def approve_statement(engine: sa.engine.Engine, tenant: str, user: str, statement_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        s = c.execute(sa.select(STATEMENTS).where(STATEMENTS.c.tenant_id == tenant, STATEMENTS.c.id == statement_id)
                      .with_for_update()).first()
        if not s:
            raise NotFound("Hakediş bulunamadı.")
        if s.status != "taslak":
            raise ContractError(f"Hakediş zaten «{STATEMENT_STATUSES[s.status]}».")
        r = c.execute(sa.select(RECORDS).where(RECORDS.c.id == s.contract_id).with_for_update()).first()
        clash = c.execute(sa.select(STATEMENTS.c.id).where(
            STATEMENTS.c.contract_id == r.id, STATEMENTS.c.status == "onaylandi",
            STATEMENTS.c.period_start <= s.period_end, STATEMENTS.c.period_end >= s.period_start)).first()
        if clash:
            raise Conflict("Bu dönemle çakışan onaylı bir hakediş var.")
        later = c.execute(sa.select(STATEMENTS.c.id).where(
            STATEMENTS.c.contract_id == r.id, STATEMENTS.c.status == "onaylandi", STATEMENTS.c.period_start > s.period_end)).first()
        if later:
            raise ContractError("Daha sonraki bir dönem onaylanmış; avans ve devir sırası bozulmasın diye önce o iptal edilmeli.")
        ctx_rows = c.execute(sa.select(STATEMENTS).where(
            STATEMENTS.c.contract_id == r.id, STATEMENTS.c.status == "onaylandi", STATEMENTS.c.period_start < s.period_start)).all()
        used = sum(float(x.advance_offset or 0) for x in ctx_rows)
        if abs(used - float((s.calc or {}).get("advanceUsedBefore") or 0)) > 0.005:
            raise Conflict("Hakediş hesaplandıktan sonra başka bir dönem onaylandı ya da iptal edildi; yeniden hesaplayın.")
        now = _now()
        pid = None
        if (s.net or 0) > 0:
            pid = _new_id()
            days = int(r.terms.get("paymentDays") if r.terms.get("paymentDays") is not None else 30)
            due = (date.fromisoformat(s.period_end) + timedelta(days=days)).isoformat()
            payees = sorted({ln["party"] for ln in (s.calc or {}).get("lines") or []})
            c.execute(PAYMENTS.insert().values(
                id=pid, tenant_id=tenant, contract_id=r.id, kind="hakedis", party=", ".join(payees)[:200] or None,
                due_on=due, amount=s.net, currency=s.currency, status="planlandi", period_start=s.period_start,
                period_end=s.period_end, statement_id=s.id, note=f"{T.day_tr(s.period_start)} – {T.day_tr(s.period_end)} hakedişi",
                created_by=user, created_at=now, updated_by=user, updated_at=now))
        c.execute(STATEMENTS.update().where(STATEMENTS.c.id == s.id).values(
            status="onaylandi", approved_by=user, approved_at=now, payment_id=pid))
        _event(c, tenant, r.id, user, "hakedis", f"{T.day_tr(s.period_start)} – {T.day_tr(s.period_end)} hakedişi onaylandı: "
               f"net {T.money(s.net, s.currency)}" + (", ödeme takvimine eklendi." if pid else "; ödenecek tutar yok."))
        row = c.execute(sa.select(STATEMENTS).where(STATEMENTS.c.id == s.id)).first()
    return _statement(row)


def cancel_statement(engine: sa.engine.Engine, tenant: str, user: str, statement_id: str, body: dict[str, Any]) -> dict[str, Any]:
    note = " ".join(str(body.get("note") or "").split())[:1000]
    with engine.begin() as c:
        s = c.execute(sa.select(STATEMENTS).where(STATEMENTS.c.tenant_id == tenant, STATEMENTS.c.id == statement_id)
                      .with_for_update()).first()
        if not s:
            raise NotFound("Hakediş bulunamadı.")
        if s.status == "iptal":
            raise ContractError("Hakediş zaten iptal.")
        if s.status == "onaylandi":
            if not note:
                raise ContractError("Onaylı hakedişi iptal etmek için gerekçe yazın.")
            later = c.execute(sa.select(STATEMENTS.c.id).where(
                STATEMENTS.c.contract_id == s.contract_id, STATEMENTS.c.status == "onaylandi",
                STATEMENTS.c.period_start > s.period_end)).first()
            if later:
                raise ContractError("Sonraki dönemin onaylı hakedişi var; önce onu iptal edin.")
            if s.payment_id:
                p = c.execute(sa.select(PAYMENTS).where(PAYMENTS.c.id == s.payment_id)).first()
                if p and p.status == "odendi":
                    raise ContractError("Bu hakedişin ödemesi yapılmış; önce ödeme kaydını gerekçesiyle iptal edin.")
                c.execute(PAYMENTS.update().where(PAYMENTS.c.id == s.payment_id).values(
                    status="iptal", note="Hakediş iptal edildi", updated_by=user, updated_at=_now()))
        c.execute(STATEMENTS.update().where(STATEMENTS.c.id == s.id).values(
            status="iptal", cancelled_by=user, cancelled_at=_now(), note=((s.note + "\n") if s.note else "") + (f"İptal: {note}" if note else "")))
        _event(c, tenant, s.contract_id, user, "hakedis", f"{T.day_tr(s.period_start)} – {T.day_tr(s.period_end)} hakedişi iptal edildi."
               + (f" {note}" if note else ""))
        row = c.execute(sa.select(STATEMENTS).where(STATEMENTS.c.id == s.id)).first()
    return _statement(row)


def get_statement(engine: sa.engine.Engine, tenant: str, statement_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        s = c.execute(sa.select(STATEMENTS).where(STATEMENTS.c.tenant_id == tenant, STATEMENTS.c.id == statement_id)).first()
    if not s:
        raise NotFound("Hakediş bulunamadı.")
    return _statement(s)


# ------------------------------------------------------------------------------------------ şablon

def _template(r: Any, with_docx: bool = False) -> dict[str, Any]:
    body = r.body or ""
    fields = D.placeholders(body)
    if r.docx is not None:
        try:
            fields = sorted(set(fields) | set(D.check_docx(r.docx)))
        except ContractError:
            pass
    out = {"id": r.id, "name": r.name, "target": r.target, "targetLabel": D.TARGETS.get(r.target), "kind": r.kind,
           "description": r.description, "body": body, "hasDocx": r.docx is not None, "docxName": r.docx_name,
           "version": r.version, "active": bool(r.active), "fields": fields,
           "unknownFields": [f for f in fields if f not in D.FIELDS],
           "createdBy": r.created_by, "createdAt": _iso(r.created_at), "updatedBy": r.updated_by, "updatedAt": _iso(r.updated_at)}
    if with_docx:
        out["docx"] = r.docx
    return out


def templates_stmt(tenant: str, *, target: str = "", include_archived: bool = False) -> sa.Select:
    stmt = sa.select(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant)
    if target:
        stmt = stmt.where(TEMPLATES.c.target == target)
    if not include_archived:
        stmt = stmt.where(TEMPLATES.c.active.is_(True))
    return stmt.order_by(TEMPLATES.c.target, TEMPLATES.c.name)


def templates(engine: sa.engine.Engine, tenant: str, *, target: str = "", include_archived: bool = False) -> list[dict[str, Any]]:
    ensure(engine)
    seed_templates(engine, tenant)
    with engine.connect() as c:
        rows = c.execute(templates_stmt(tenant, target=target, include_archived=include_archived)).all()
    return [_template(r) for r in rows]


def template(engine: sa.engine.Engine, tenant: str, template_id: str, with_docx: bool = False) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant, TEMPLATES.c.id == str(template_id))).first()
    if not r:
        raise NotFound("Şablon bulunamadı.")
    return _template(r, with_docx)


def _template_fields(body: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not partial or "name" in body:
        name = " ".join(str(body.get("name") or "").split())[:200]
        if not name:
            raise ContractError("Şablona bir ad verin.")
        out["name"] = name
    if not partial or "target" in body:
        target = str(body.get("target") or "sozlesme")
        if target not in D.TARGETS:
            raise ContractError("Geçersiz şablon türü.")
        out["target"] = target
    if not partial or "kind" in body:
        kind = str(body.get("kind") or "")
        if kind and kind not in T.KINDS:
            raise ContractError("Geçersiz sözleşme türü.")
        out["kind"] = kind or None
    if not partial or "description" in body:
        out["description"] = str(body.get("description") or "").strip()[:2000] or None
    if not partial or "body" in body:
        text = str(body.get("body") or "")
        if len(text) > 400_000:
            raise ContractError("Şablon metni çok uzun.")
        out["body"] = text
    return out


def save_template(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any],
                  template_id: Optional[str] = None) -> dict[str, Any]:
    ensure(engine)
    now = _now()
    with engine.begin() as c:
        if template_id is None:
            f = _template_fields(body)
            tid = _new_id()
            c.execute(TEMPLATES.insert().values(id=tid, tenant_id=tenant, version=1, active=True, created_by=user,
                                                created_at=now, updated_by=user, updated_at=now, **f))
        else:
            r = c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant, TEMPLATES.c.id == template_id)
                          .with_for_update()).first()
            if not r:
                raise NotFound("Şablon bulunamadı.")
            if body.get("version") is not None and int(body["version"]) != r.version:
                raise Conflict(f"Şablon siz açtıktan sonra {r.updated_by} tarafından değiştirildi; yenileyip tekrar deneyin.")
            f = _template_fields(body, partial=True)
            if "active" in body:
                f["active"] = bool(body["active"])
            c.execute(TEMPLATES.update().where(TEMPLATES.c.id == r.id).values(
                version=r.version + 1, updated_by=user, updated_at=now, **f))
            tid = r.id
    return template(engine, tenant, tid)


def upload_template_docx(engine: sa.engine.Engine, tenant: str, user: str, template_id: str, filename: str,
                         data: bytes) -> dict[str, Any]:
    if not data:
        raise ContractError("Dosya boş.")
    D.check_docx(data)
    name = re.sub(r"[^\w .()-]+", "_", filename or "sablon.docx")[:200]
    if not name.lower().endswith(".docx"):
        raise ContractError("Yalnız .docx dosyası yüklenir.")
    with engine.begin() as c:
        r = c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant, TEMPLATES.c.id == template_id)
                      .with_for_update()).first()
        if not r:
            raise NotFound("Şablon bulunamadı.")
        c.execute(TEMPLATES.update().where(TEMPLATES.c.id == r.id).values(
            docx=data, docx_name=name, version=r.version + 1, updated_by=user, updated_at=_now()))
    return template(engine, tenant, template_id)


def remove_template_docx(engine: sa.engine.Engine, tenant: str, user: str, template_id: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant, TEMPLATES.c.id == template_id)
                      .with_for_update()).first()
        if not r:
            raise NotFound("Şablon bulunamadı.")
        if not (r.body or "").strip():
            raise ContractError("Şablonun metni boş; Word dosyası kaldırılırsa şablonda içerik kalmaz.")
        c.execute(TEMPLATES.update().where(TEMPLATES.c.id == r.id).values(
            docx=None, docx_name=None, version=r.version + 1, updated_by=user, updated_at=_now()))
    return template(engine, tenant, template_id)


_seeded: set[tuple[int, str]] = set()


def seed_templates(engine: sa.engine.Engine, tenant: str) -> None:
    """Kütüphane boşsa başlangıç şablonları: hukuk biriminin kendi metniyle değiştirmesi için iskelet."""
    key = (id(engine), tenant)
    if key in _seeded:
        return
    from semantic_bridge.contracts_seed import SEED
    with engine.begin() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(TEMPLATES).where(TEMPLATES.c.tenant_id == tenant)).scalar()
        if not n:
            now = _now()
            for s in SEED:
                c.execute(TEMPLATES.insert().values(id=_new_id(), tenant_id=tenant, version=1, active=True,
                                                    created_by="sistem", created_at=now, updated_by="sistem",
                                                    updated_at=now, docx=None, docx_name=None, **s))
    _seeded.add(key)


# ------------------------------------------------------------------------------------------ belge

def _safe(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("_")[:120] or "belge"


def document(engine: sa.engine.Engine, tenant: str, what: str, obj_id: str, template_id: str = "") -> tuple[bytes, str, list[str]]:
    """Word belgesi: `what` = sozlesme (kayıt kimliği) | zeyilname | hakedis. Dönen: (bayt, dosya adı, boş kalan alanlar)."""
    ensure(engine)
    addendum = statement = None
    if what == "sozlesme":
        rec = find(engine, tenant, obj_id)
        if not rec:
            raise NotFound("Sözleşme portalda yok.")
        target = "sozlesme"
    elif what == "zeyilname":
        with engine.connect() as c:
            a, r = _get_addendum(c, tenant, obj_id)
        rec = _record(r)
        addendum = _addendum(a, r.no)
        target = "zeyilname"
        template_id = template_id or (a.template_id or "")
    elif what == "hakedis":
        statement = get_statement(engine, tenant, obj_id)
        rec = find(engine, tenant, statement["contractId"])
        statement = {**statement["calc"], **{k: statement[k] for k in ("status", "net", "gross", "advanceOffset", "currency")}}
        target = "hakedis"
    else:
        raise ContractError("Bilinmeyen belge türü.")
    vals = D.values(rec["no"], rec["terms"], addendum=addendum, statement=statement)
    title = {"sozlesme": rec["no"], "zeyilname": (addendum or {}).get("no", ""), "hakedis": f"{rec['no']} hakedis {vals.get('hakedis_donem', '')}"}[target]
    fname = _safe(f"{title} {rec['terms'].get('title') or ''}") + ".docx"
    if target == "sozlesme" and not template_id and rec.get("body"):
        # Metin Word şablonundan üretildiyse ve elle değişmediyse Word dosyası doldurulur (biçim korunur);
        # elle düzenlenmiş metin ise o metnin kendisidir.
        src = template(engine, tenant, rec["templateId"]) if rec.get("templateId") and not rec.get("bodyEdited") else None
        if not (src and src["hasDocx"]):
            return D.docx_from_text(rec["body"], title), fname, D.placeholders(rec["body"])
    tpl = None
    if template_id or (target == "sozlesme" and rec.get("templateId")):
        tpl = template(engine, tenant, template_id or rec["templateId"], with_docx=True)
    else:
        options = [t for t in templates(engine, tenant, target=target)]
        kind_match = [t for t in options if t["kind"] == rec["terms"].get("kind")] or [t for t in options if not t["kind"]] or options
        if kind_match:
            tpl = template(engine, tenant, kind_match[0]["id"], with_docx=True)
    if not tpl:
        raise ContractError(f"Kütüphanede «{D.TARGETS[target]}» şablonu yok.")
    if tpl["target"] != target:
        raise ContractError(f"Seçilen şablon {D.TARGETS[target].lower()} için değil.")
    if tpl.get("docx"):
        data, missing = D.docx_fill(tpl["docx"], vals)
        return data, fname, missing
    text, missing = D.fill(tpl["body"] or "", vals)
    return D.docx_from_text(text, title), fname, missing


def preview(engine: sa.engine.Engine, tenant: str, template_id: str, key: str = "") -> dict[str, Any]:
    """Şablonun bir sözleşmeyle (ya da örnek değerlerle) doldurulmuş metni."""
    tpl = template(engine, tenant, template_id, with_docx=True)
    rec = find(engine, tenant, key) if key else None
    terms = rec["terms"] if rec else _sample_terms()
    vals = D.values(rec["no"] if rec else "TS-ÖRNEK-0001", terms,
                    addendum=_sample_addendum() if tpl["target"] == "zeyilname" else None,
                    statement=_sample_statement() if tpl["target"] == "hakedis" else None)
    src = D.docx_text(tpl["docx"]) if tpl.get("docx") else (tpl["body"] or "")
    text, missing = D.fill(src, vals)
    return {"text": text, "missing": missing, "sample": rec is None, "fromDocx": bool(tpl.get("docx"))}


def _sample_terms() -> dict[str, Any]:
    return T.clean({
        "title": "Örnek Kitap — Örnek Yazar", "kind": "telif-alis", "company": "Timaş Basım Ticaret ve Sanayi A.Ş.",
        "parties": [{"name": "Örnek Yazar", "role": "yazar", "share": 100}],
        "books": [{"title": "Örnek Kitap", "isbn": "9786050000000", "stockCode": "ORNEK"}],
        "paymentType": "satis", "basis": "net", "rates": {"karton": 10, "ekitap": 25}, "currency": "TRY",
        "advance": 25000, "start": "2026-01-01", "end": "2031-12-31", "years": 5, "periodMonths": 6, "paymentDays": 30,
        "printRun": 3000, "territory": "Dünya", "language": "Türkçe", "rights": {"cogaltma": True, "yayma": True, "iletim": True},
    })


def _sample_addendum() -> dict[str, Any]:
    return {"no": "TS-ÖRNEK-0001/Z-1", "title": "Süre uzatımı", "effectiveOn": "2026-10-01", "reason": "Taraflar sözleşmeyi uzatmak istedi.",
            "changes": [{"field": "end", "label": "Bitiş", "old": "2031-12-31", "new": "2033-12-31"}]}


def _sample_statement() -> dict[str, Any]:
    return {"periodStart": "2026-01-01", "periodEnd": "2026-06-30", "quantity": 1200, "base": 180000, "gross": 18000,
            "advanceOffset": 18000, "withholding": 0, "net": 0, "currency": "TRY",
            "lines": [{"book": "Örnek Kitap", "party": "Örnek Yazar", "quantity": 1200, "rate": 10, "royalty": 18000}]}


# ------------------------------------------------------------------------------------------ CRM okuma

def crm_contract_sql(p: str, crm_id: str) -> list[str]:
    """Bir CRM sözleşmesinin başlığı, kitapları (stok kodu), tarafları. `p` = `Timas_MSCRM.dbo.` öneki."""
    g = crm_id.lower()
    if not is_crm_id(g):
        raise ContractError("Sözleşme kimliği geçerli değil.")
    rights = ", ".join(f"CAST(ISNULL(s.{col}, 0) AS int) AS {col}" for col in T.RIGHT_FROM_CRM)
    head = (
        "SELECT s.new_sozlesmeId, s.new_name, s.new_SozlesmeKodu, CAST(s.new_SozlesmeTipi AS int) AS tip_kod,"
        " CAST(s.new_TelifTipi AS int) AS odeme_kod, CAST(s.new_telifturu AS int) AS esas_kod,"
        " CAST(s.new_sozlesmeparabirimi AS int) AS para_kod, CAST(s.statuscode AS int) AS durum_kod,"
        " s.new_Telif, s.new_sertkapaktelif, s.new_e_kitap_telif, s.new_SesliKitap, s.new_yurtdisitelif,"
        # Tek ödeme tutarı `new_TekdemeTutari`'nda (2026-09-29: tek ödemeli 7.658 sözleşmenin 6.912'sinde dolu);
        # «Tek Ödeme Tutarı TL» (`new_tekodemetutari`) hiçbir kayıtta dolu değil, doluysa o önce gelir.
        " s.new_sozlesmeavanstutari, COALESCE(NULLIF(s.new_tekodemetutari, 0), s.new_TekdemeTutari) AS new_tekodemetutari,"
        " s.new_telifhesaplamaiskontosu,"
        " s.new_SozlesmeBaslangicTarihi, s.new_SozlesmeBitisTarihi, s.new_SozlesmeSuresiYil,"
        " CAST(ISNULL(s.new_suresizsozlesme, 0) AS int) AS suresiz, s.new_yazar_text, s.new_mutercim_text,"
        f" s.new_cizer_text, s.new_haklaraciklama, s.new_hesaplamatutari, s.new_anasozlesmeid, a.Name AS sirket, {rights},"
        f" {crm_rights.columns('s')}"
        f" FROM {p}new_sozlesmeBase s LEFT JOIN {p}AccountBase a ON a.AccountId = s.new_SozlemeninSahibi"
        f"{crm_rights.joins(p, 's')}"
        f" WHERE s.new_sozlesmeId = '{g}'"
    )
    books = (
        "SELECT k.new_kitapId, k.new_name, k.new_StokKodu, k.new_isbn13, k.new_kdvdahilfiyat, k.new_EKitapStokKodu"
        f" FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_kitapBase k ON k.new_kitapId = sk.new_kitapid"
        f" WHERE sk.new_sozlesmeid = '{g}' ORDER BY k.new_name"
    )
    parties = (
        "SELECT t.new_kisi, t.new_Firma, c.FullName AS kisi, a.Name AS firma, t.new_Odeme,"
        " CAST(ISNULL(t.new_aracivarmi, 0) AS int) AS araci"
        f" FROM {p}new_sozlesmetarafiBase t LEFT JOIN {p}ContactBase c ON c.ContactId = t.new_kisi"
        f" LEFT JOIN {p}AccountBase a ON a.AccountId = t.new_Firma"
        f" WHERE t.statecode = 0 AND t.new_sozlesmeid = '{g}' ORDER BY t.new_Odeme DESC"
    )
    return [head, books, parties]


def related_sql(p: str, crm_id: str, parent: Optional[str]) -> str:
    """CRM'de sözleşmenin ana sözleşmesi ve ona bağlı alt kayıtlar (`new_anasozlesmeid` = '{GUID}' metni).
    2026-09-27 ölçümü: 8.814 etkin sözleşmede dolu; grup sözleşmesi (`new_grupsozlesmesimi`, 8.763) kitap başına
    bir kayda bölünür, «2026009059-1/-2/-3» hepsi «-1»i ana gösterir."""
    g = crm_id.upper()
    ids = [f"UPPER(r.new_anasozlesmeid) = '{{{g}}}'"]
    if parent and is_crm_id(parent):
        pg = parent.upper()
        ids += [f"r.new_sozlesmeId = '{pg}'", f"UPPER(r.new_anasozlesmeid) = '{{{pg}}}'"]
    return ("SELECT r.new_sozlesmeId, r.new_name, CAST(r.statuscode AS int) AS durum_kod, r.new_SozlesmeBaslangicTarihi,"
            " r.new_SozlesmeBitisTarihi, r.new_anasozlesmeid"
            f" FROM {p}new_sozlesmeBase r WHERE r.statecode = 0 AND r.new_sozlesmeId <> '{g}' AND ({' OR '.join(ids)})"
            " ORDER BY r.new_name")


def parent_of(head: dict[str, Any]) -> Optional[str]:
    t = str(head.get("new_anasozlesmeid") or "").strip().strip("{}").lower()
    return t if is_crm_id(t) else None


def _natural(text: str) -> tuple:
    """Sayıyı sayı olarak sıralar: «2024007186-2» «-10»dan önce gelir (yazı sıralaması -10, -100, -11… verir)."""
    return tuple(int(p) if p.isdecimal() else p.casefold() for p in re.split(r"(\d+)", text))


def related(rows: list[dict[str, Any]], parent: Optional[str]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        rid = str(r.get("new_sozlesmeId") or "").lower()
        out.append({"id": rid, "no": str(r.get("new_name") or "").strip() or None,
                    "relation": "ana" if parent and rid == parent else "bagli",
                    "status": T.STATUS_FROM_CRM.get(_i(r.get("durum_kod")), "sona-erdi"),
                    "start": str(r.get("new_SozlesmeBaslangicTarihi") or "")[:10] or None,
                    "end": str(r.get("new_SozlesmeBitisTarihi") or "")[:10] or None})
    out.sort(key=lambda x: (x["relation"] != "ana", _natural(x["no"] or "")))
    return out


def _f(v: Any) -> Optional[float]:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> Optional[int]:
    x = _f(v)
    return None if x is None else int(x)


def _crm_books(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kitap kartı → şarttaki kitaplar. Kapak fiyatı `new_kdvdahilfiyat` (Logo satış satırındaki birim fiyatla aynı,
    2026-09-27'de örneklerde birebir); e-kitabın ayrı stok kodu varsa ayrı satır (e-kitap oranıyla hesaplanır)."""
    out = []
    for b in rows:
        if not b.get("new_name"):
            continue
        base = {"id": str(b.get("new_kitapId") or "") or None, "title": str(b.get("new_name")),
                "isbn": str(b.get("new_isbn13") or "").strip() or None}
        out.append({**base, "stockCode": str(b.get("new_StokKodu") or "").strip() or None, "format": "karton",
                    "listPrice": _f(b.get("new_kdvdahilfiyat")) or None})
        ebook = str(b.get("new_EKitapStokKodu") or "").strip()
        if ebook:
            out.append({**base, "title": f"{base['title']} (e-kitap)", "stockCode": ebook, "format": "ekitap", "listPrice": None})
    return out


def crm_contract(head: dict[str, Any], books: list[dict[str, Any]], parties: list[dict[str, Any]]) -> dict[str, Any]:
    """CRM satırları → {no, status, terms}. Rolü sözleşmedeki yazar/mütercim/çizer metninden çıkarılır."""
    def names(col: str) -> str:
        return str(head.get(col) or "").lower()

    ps = []
    for t in parties:
        name = (str(t.get("kisi") or "").strip() or str(t.get("firma") or "").strip())
        if not name:
            continue
        low = name.lower()
        role = ("yazar" if low in names("new_yazar_text") else "cevirmen" if low in names("new_mutercim_text")
                else "cizer" if low in names("new_cizer_text") else ("ajans" if not t.get("kisi") else "diger"))
        ps.append({"name": name, "role": role, "share": _f(t.get("new_Odeme")),
                   "contactId": str(t.get("new_kisi") or "") or None, "accountId": str(t.get("new_Firma") or "") or None,
                   "viaAgent": bool(_i(t.get("araci")))})
    rates = {k: _f(head.get(col)) for k, col in (("karton", "new_Telif"), ("sert", "new_sertkapaktelif"),
                                                 ("ekitap", "new_e_kitap_telif"), ("sesli", "new_SesliKitap"),
                                                 ("yurtdisi", "new_yurtdisitelif"))}
    raw = {
        "title": " · ".join(str(b.get("new_name")) for b in books if b.get("new_name")) or str(head.get("new_name") or "CRM sözleşmesi"),
        "kind": T.KIND_FROM_CRM.get(_i(head.get("tip_kod")), "telif-alis"),
        "company": str(head.get("sirket") or ""),
        "parties": ps,
        "books": _crm_books(books),
        "paymentType": T.PAYMENT_FROM_CRM.get(_i(head.get("odeme_kod")), "diger"),
        "basis": T.BASIS_FROM_CRM.get(_i(head.get("esas_kod")), "net"),
        "rates": {k: v for k, v in rates.items() if v},
        "currency": T.CURRENCY_FROM_CRM.get(_i(head.get("para_kod")), "TRY"),
        "advance": _f(head.get("new_sozlesmeavanstutari")) or None,
        "flatFee": _f(head.get("new_tekodemetutari")) or None,
        "discountPct": _f(head.get("new_telifhesaplamaiskontosu")) or None,
        "start": str(head.get("new_SozlesmeBaslangicTarihi") or "")[:10] or None,
        "end": str(head.get("new_SozlesmeBitisTarihi") or "")[:10] or None,
        "openEnded": bool(_i(head.get("suresiz"))),
        "years": _f(head.get("new_SozlesmeSuresiYil")) or None,
        "rights": {k: bool(_i(head.get(col))) for col, k in T.RIGHT_FROM_CRM.items()},
        # Çeviri/hizmet sözleşmelerinde ücret serbest metindir («Sayfa başı (200 kelime) 250 TL»).
        "notes": "\n".join(x for x in (str(head.get("new_haklaraciklama") or "").strip(),
                                         ("Hesaplama: " + str(head.get("new_hesaplamatutari")).strip()) if head.get("new_hesaplamatutari") else "") if x),
    }
    if raw["start"] and raw["end"] and raw["end"] < raw["start"]:
        raw["end"] = None  # CRM'de ters girilmiş tarih; portal kaydı bitişi boş açar, ekran uyarır
    # CRM'in bütün hakları ve lisans şartları (salt okunur; portal şartlarına girmez, farkta sayılmaz).
    return {"no": str(head.get("new_name") or "").strip() or None, "crmStatus": _i(head.get("durum_kod")),
            "status": T.STATUS_FROM_CRM.get(_i(head.get("durum_kod")), "yururlukte"), "terms": T.clean(raw),
            "id": str(head.get("new_sozlesmeId") or "").lower() or None,
            "rights": crm_rights.rights(head), "license": crm_rights.license_of(head)}


def detail(engine: sa.engine.Engine, tenant: str, key: str, crm_loader: Callable[[str], Optional[dict[str, Any]]]) -> dict[str, Any]:
    """Sözleşme sayfası: portal kaydı varsa o, yoksa CRM'den okunan hâli (salt okunur, `record: null`)."""
    ensure(engine)
    rec = find(engine, tenant, key)
    crm = None
    crm_error = None
    crm_id = (rec or {}).get("crmId") or (key.lower() if is_crm_id(key) else None)
    if crm_id:
        try:
            crm = crm_loader(crm_id)
        except Exception as e:  # noqa: BLE001 — portal kaydı CRM'e ulaşılamasa da açılır
            if rec is None:
                raise
            log.warning("contracts: CRM okunamadı (%s): %s", crm_id, e)
            crm_error = "CRM şu an okunamadı; CRM ile fark gösterilemiyor."
        if crm is None and rec is None:
            raise NotFound("Sözleşme CRM'de bulunamadı.")
    if rec is None:
        terms = crm["terms"]
        return {"record": None, "key": crm_id, "no": crm["no"], "status": crm["status"],
                "statusLabel": T.STATUSES.get(crm["status"]), "terms": terms, "crm": crm, "diff": [],
                "warnings": T.warnings(terms), "addenda": [], "payments": [], "statements": [], "events": [],
                "periods": schedule_periods(terms)}
    diff = T.diff(crm["terms"], rec["terms"]) if crm else []
    return {"record": rec, "crmError": crm_error, "key": rec["id"], "no": rec["no"], "status": rec["status"], "statusLabel": rec["statusLabel"],
            "terms": rec["terms"], "crm": crm, "diff": diff, "crmChangedSinceAdopt": bool(crm and rec.get("crmTerms") and T.diff(rec["crmTerms"], crm["terms"])),
            "warnings": T.warnings(rec["terms"]), "addenda": addenda(engine, tenant, rec["id"], rec["no"]),
            "payments": payments(engine, tenant, rec["id"]), "statements": statements(engine, tenant, rec["id"]),
            "events": events(engine, tenant, rec["id"]), "periods": schedule_periods(rec["terms"])}


# ------------------------------------------------------------------------------------------ seçiciler

def _like(text: str) -> str:
    from semantic_bridge.editorial import _like as like
    k = like(text)
    if len(k.strip()) < 2:
        raise ContractError("En az iki harf yazın.")
    return k


LOOKUP_PAGE_SIZE = 20


def _page(page: Any) -> str:
    """Seçici sayfası: sonuç kesilmez, toplam (`toplam`) her satırda gelir, ekran «Daha fazla göster» ile ilerler."""
    try:
        n = max(0, int(page or 0))
    except (TypeError, ValueError):
        raise ContractError("Sayfa numarası geçerli değil.") from None
    return f" OFFSET {n * LOOKUP_PAGE_SIZE} ROWS FETCH NEXT {LOOKUP_PAGE_SIZE} ROWS ONLY"


def lookup_page(rows: list[dict[str, Any]], page: Any) -> dict[str, Any]:
    """Seçici cevabının sayfa bilgisi: CRM'deki gerçek eşleşme sayısı (`total`) ve bu sayfayla birlikte gösterilen
    kayıt sayısı (`shown`). Sayım CRM kaydı üzerinedir; e-kitabı olan kitap kartı listede iki satır olur."""
    n = max(0, int(page or 0))
    total = int(rows[0].get("toplam") or 0) if rows else 0
    return {"total": total, "shown": min(total, n * LOOKUP_PAGE_SIZE + len(rows)), "page": n}


def book_lookup_sql(p: str, q: str, page: Any = 0) -> str:
    """Taslağa kitap eklemek için: ad, ISBN, stok kodu (hakediş bu kodla Logo'yu okur)."""
    k = _like(q)
    d = re.sub(r"[^0-9Xx]", "", q or "").upper()
    match = [f"b.new_name LIKE N'%{k}%'", f"b.new_StokKodu LIKE N'%{k}%'"]
    if len(d) >= 5:
        match.append(f"REPLACE(REPLACE(ISNULL(b.new_isbn13, ''), '-', ''), ' ', '') LIKE '%{d}%'")
    return ("SELECT b.new_kitapId, b.new_name, b.new_StokKodu, b.new_isbn13, b.new_kdvdahilfiyat, b.new_EKitapStokKodu,"
            " COUNT(*) OVER () AS toplam"
            f" FROM {p}new_kitapBase b WHERE b.statecode = 0 AND ({' OR '.join(match)}) ORDER BY b.new_name, b.new_kitapId"
            + _page(page))


def party_lookup_sql(p: str, q: str, page: Any = 0) -> str:
    """Taraf: CRM kişisi ya da firması, ada göre tek listede."""
    k = _like(q)
    return ("SELECT x.tur, x.id, x.ad, COUNT(*) OVER () AS toplam FROM ("
            f"SELECT 'kisi' AS tur, c.ContactId AS id, c.FullName AS ad FROM {p}ContactBase c"
            f" WHERE c.statecode = 0 AND c.FullName LIKE N'%{k}%'"
            f" UNION ALL SELECT 'firma' AS tur, a.AccountId AS id, a.Name AS ad FROM {p}AccountBase a"
            f" WHERE a.statecode = 0 AND a.Name LIKE N'%{k}%') x ORDER BY x.ad, x.tur, x.id"
            + _page(page))
