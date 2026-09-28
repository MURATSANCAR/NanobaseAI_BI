"""Serbest çalışanlar (M8): çizer, kapak tasarımcı, mizanpajcı, redaktör, çevirmen… CRM'de yalnız eser katılımı
olarak görünen kişilerin iş takibi. Hepsi kendi tablolarımızda (`semantic_freelance_*`); CRM'e ve Logo'ya yazılmaz.

- **Kayıt ve portfolyo:** kişi kartı (roller, iletişim, üslup etiketleri, birim ücretler, haftalık kapasite, müsait
  olmadığı günler), isteğe bağlı CRM kişisi ve Logo cari kodu bağı; portfolyo dosyaları (görsel/PDF) diskte.
- **İş paketi:** bir kitabın bir işi (ör. «24 iç illüstrasyon»). Paket görevlere bölünür; her görev bir kişiye
  atanır. Toplu dağıtımda öneri, rol + görev aralığındaki boş saat + zamanında teslim oranıyla sıralanır.
- **Kapasite:** görevin tahmini saati, başlangıç–termin arasındaki iş günlerine eşit yayılır; haftalık kapasiteyle
  (müsait olmadığı günler düşülerek) karşılaştırılır. Termini geçmiş, teslim edilmemiş iş bu haftaya yazılır.
- **Teslim:** dosya ya da bağlantı; kabul ya da revizyon. Kabul edilen görev ödenecek işe düşer.
- **Hakediş:** ödenecek işlerden kişi başına belge; satırlar oluşturulduğu anki tutarla dondurulur. Taslak → onay
  bekliyor → onaylandı → ödendi. Tutarlar anlaşılan brüt ücrettir (KDV hariç); kesinti ve ödeme Logo'da yapılır,
  burada yalnız ödeme tarihi ve belge/açıklama tutulur.
- **Mesajlaşma:** her iş paketinin (ve kişinin genel) yazışması. Serbest çalışan portala giremez (giriş yalnız AD):
  «serbest çalışana» yazılan ileti e-postayla gider (yanıt adresi yazan kişinin e-postası), gelen yanıt ekibin
  kaydettiği iletidir. Olaylar (atama, teslim, kabul, revizyon, hakediş) aynı akışa sistem satırı olarak düşer.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic.freelance")
_md = sa.MetaData()

#: İş rolleri: anahtar → (ad, varsayılan birim, birim başına varsayılan saat). Birim saat yalnız ilk öneridir.
ROLES: dict[str, tuple[str, str, float]] = {
    "cizer": ("Çizer / illüstratör", "çizim", 6.0),
    "kapak": ("Kapak tasarım", "kapak", 16.0),
    "mizanpaj": ("Mizanpaj", "sayfa", 0.25),
    "redaksiyon": ("Redaksiyon", "sayfa", 0.2),
    "tashih": ("Tashih / son okuma", "sayfa", 0.1),
    "ceviri": ("Çeviri", "sayfa", 1.0),
    "yayina-hazirlik": ("Yayına hazırlık", "sayfa", 0.15),
    "danismanlik": ("Danışmanlık / raportörlük", "iş", 8.0),
}
UNITS = ("çizim", "kapak", "sayfa", "forma", "iş", "saat", "kelime")

TASK_STATES = ("atanmadi", "atandi", "calisiyor", "teslim", "revizyon", "onaylandi", "iptal")
#: Kapasiteyi dolduran durumlar (kişinin elinde olan iş).
ACTIVE = ("atandi", "calisiyor", "revizyon")
PAYOUT_STATES = ("taslak", "onay", "onaylandi", "odendi")
#: Silinen taslak: listelerde görünmez, numarası yeniden verilmez.
DELETED = "silindi"

PORTFOLIO_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
                 "gif": "image/gif", "pdf": "application/pdf"}
PORTFOLIO_MAX = 40 * 1024 * 1024
DELIVERY_MAX = 200 * 1024 * 1024
WORKDAYS = 5


def _id() -> sa.Column:
    return sa.Column("id", sa.String(32), primary_key=True)


def _ts(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


PEOPLE = sa.Table(
    "semantic_freelance_people", _md, _id(),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("roles_json", sa.Text, nullable=False, default="[]"),
    sa.Column("email", sa.String(200)),
    sa.Column("phone", sa.String(40)),
    sa.Column("city", sa.String(80)),
    sa.Column("website", sa.String(300)),
    sa.Column("crm_contact_id", sa.String(40)),
    sa.Column("logo_card", sa.String(40)),
    sa.Column("styles_json", sa.Text, nullable=False, default="[]"),
    sa.Column("note", sa.Text),
    sa.Column("weekly_hours", sa.Float, nullable=False, default=20.0),
    sa.Column("rates_json", sa.Text, nullable=False, default="[]"),
    sa.Column("away_json", sa.Text, nullable=False, default="[]"),
    sa.Column("status", sa.String(12), nullable=False, default="aktif"),        # aktif | pasif
    sa.Column("created_by", sa.String(120), nullable=False),
    _ts("created_at", False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at"),
)
PORTFOLIO = sa.Table(
    "semantic_freelance_portfolio", _md, _id(),
    sa.Column("person_id", sa.String(32), nullable=False, index=True),
    sa.Column("title", sa.String(200)),
    sa.Column("tags_json", sa.Text, nullable=False, default="[]"),
    sa.Column("book", sa.String(300)),
    sa.Column("filename", sa.String(300), nullable=False),
    sa.Column("mime", sa.String(60), nullable=False),
    sa.Column("bytes", sa.BigInteger, nullable=False),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("path", sa.String(500), nullable=False),
    sa.Column("uploaded_by", sa.String(120), nullable=False),
    _ts("uploaded_at", False),
)
PACKAGES = sa.Table(
    "semantic_freelance_packages", _md, _id(),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("book_title", sa.String(300)),
    sa.Column("book_id", sa.String(40)),
    sa.Column("role", sa.String(30), nullable=False),
    sa.Column("brief", sa.Text),
    sa.Column("due", sa.Date),
    sa.Column("status", sa.String(12), nullable=False, default="acik"),       # acik | kapandi | iptal
    sa.Column("owner", sa.String(120), nullable=False),
    sa.Column("created_by", sa.String(120), nullable=False),
    _ts("created_at", False),
)
TASKS = sa.Table(
    "semantic_freelance_tasks", _md, _id(),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("package_id", sa.String(32), nullable=False, index=True),
    sa.Column("person_id", sa.String(32), index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("role", sa.String(30), nullable=False),
    sa.Column("units", sa.Numeric(14, 2), nullable=False),
    sa.Column("unit", sa.String(20), nullable=False),
    sa.Column("unit_price", sa.Numeric(14, 2), nullable=False, default=0),
    sa.Column("effort_hours", sa.Float, nullable=False),
    sa.Column("start", sa.Date),
    sa.Column("due", sa.Date),
    sa.Column("status", sa.String(12), nullable=False, default="atanmadi"),
    sa.Column("revisions", sa.Integer, nullable=False, default=0),
    _ts("assigned_at"),
    sa.Column("assigned_by", sa.String(120)),
    _ts("first_delivered_at"),
    _ts("accepted_at"),
    sa.Column("accepted_by", sa.String(120)),
    sa.Column("payout_id", sa.String(32), index=True),
    _ts("created_at", False),
)
DELIVERIES = sa.Table(
    "semantic_freelance_deliveries", _md, _id(),
    sa.Column("task_id", sa.String(32), nullable=False, index=True),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("link", sa.String(1000)),
    sa.Column("filename", sa.String(300)),
    sa.Column("bytes", sa.BigInteger),
    sa.Column("sha256", sa.String(64)),
    sa.Column("path", sa.String(500)),
    sa.Column("uploaded_by", sa.String(120), nullable=False),
    _ts("uploaded_at", False),
    sa.Column("decision", sa.String(12), nullable=False, default="bekliyor"),  # bekliyor | kabul | revizyon
    sa.Column("decision_note", sa.Text),
    sa.Column("decided_by", sa.String(120)),
    _ts("decided_at"),
)
PAYOUTS = sa.Table(
    "semantic_freelance_payouts", _md, _id(),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("no", sa.Integer, nullable=False),
    sa.Column("person_id", sa.String(32), nullable=False, index=True),
    sa.Column("status", sa.String(12), nullable=False, default="taslak"),
    sa.Column("total", sa.Numeric(14, 2), nullable=False, default=0),
    sa.Column("note", sa.Text),
    sa.Column("return_note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    _ts("created_at", False),
    sa.Column("submitted_by", sa.String(120)),
    _ts("submitted_at"),
    sa.Column("approved_by", sa.String(120)),
    _ts("approved_at"),
    sa.Column("paid_on", sa.Date),
    sa.Column("paid_ref", sa.String(200)),
    sa.Column("paid_by", sa.String(120)),
    _ts("paid_at"),
)
PAYOUT_LINES = sa.Table(
    "semantic_freelance_payout_lines", _md, _id(),
    sa.Column("payout_id", sa.String(32), nullable=False, index=True),
    sa.Column("task_id", sa.String(32), nullable=False),
    sa.Column("description", sa.String(600), nullable=False),
    sa.Column("units", sa.Numeric(14, 2), nullable=False),
    sa.Column("unit", sa.String(20), nullable=False),
    sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
    sa.Column("amount", sa.Numeric(14, 2), nullable=False),
)
MESSAGES = sa.Table(
    "semantic_freelance_messages", _md, _id(),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("thread", sa.String(40), nullable=False, index=True),         # p:<paket> | k:<kişi>
    sa.Column("task_id", sa.String(32)),
    sa.Column("kind", sa.String(10), nullable=False),                       # ic | giden | gelen | sistem
    sa.Column("author", sa.String(120), nullable=False),
    sa.Column("author_display", sa.String(200)),
    sa.Column("body", sa.Text, nullable=False),
    sa.Column("email_to", sa.String(200)),
    sa.Column("email_status", sa.String(20)),                               # gonderildi | gonderilemedi | ayar-yok | adres-yok
    _ts("created_at", False),
)
READS = sa.Table(
    "semantic_freelance_reads", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("username", sa.String(120), primary_key=True),
    sa.Column("thread", sa.String(40), primary_key=True),
    _ts("read_at", False),
)

_ready: set[int] = set()
_lock = threading.Lock()


class FreelanceError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    # İş günü İstanbul'a göre (UTC+3, yaz saati yok).
    return (_now() + timedelta(hours=3)).date()


def _new() -> str:
    return uuid.uuid4().hex


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v.isoformat()


def _root() -> str:
    return os.environ.get("FREELANCE_DIR", "/data/nanobaseai/bi/var/freelance")


def _loads(v: Optional[str], default: Any) -> Any:
    try:
        out = json.loads(v or "")
    except ValueError:
        return default
    return out if isinstance(out, type(default)) else default


def _text(v: Any, limit: int) -> Optional[str]:
    t = " ".join(str(v or "").split()) if limit <= 400 else str(v or "").strip()
    return t[:limit] or None


def _money(v: Any, what: str = "Tutar") -> Decimal:
    if v in (None, ""):
        return Decimal("0")
    try:
        d = Decimal(str(v).replace(" ", "").replace(",", ".")) if not isinstance(v, (int, float, Decimal)) else Decimal(str(v))
    except InvalidOperation as e:
        raise FreelanceError(f"{what} sayı olmalı.") from e
    if d < 0 or d > Decimal("99999999"):
        raise FreelanceError(f"{what} 0 ile 99.999.999 arasında olmalı.")
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _num(v: Any, what: str, *, low: float = 0.0, high: float = 1e6, allow_zero: bool = False) -> float:
    try:
        f = float(str(v).replace(",", ".")) if v not in (None, "") else float("nan")
    except ValueError as e:
        raise FreelanceError(f"{what} sayı olmalı.") from e
    if f != f or f < low or f > high or (not allow_zero and f == 0):
        raise FreelanceError(f"{what} {'0' if allow_zero else 'sıfırdan büyük'} ile {high:g} arasında olmalı.")
    return f


def _day(v: Any, what: str) -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError as e:
        raise FreelanceError(f"{what} tarihi YYYY-AA-GG biçiminde olmalı.") from e


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CRM_ID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


# ---------------------------------------------------------------------------------------------- kişiler

def _roles(v: Any) -> list[str]:
    out = [str(r) for r in (v or []) if str(r) in ROLES]
    return list(dict.fromkeys(out))


def _tags(v: Any, limit: int = 20) -> list[str]:
    out = []
    for t in v or []:
        s = " ".join(str(t).split())[:40]
        if s and s.lower() not in {x.lower() for x in out}:
            out.append(s)
    return out[:limit]


def _rates(v: Any) -> list[dict[str, Any]]:
    out = []
    for r in v or []:
        if not isinstance(r, dict):
            continue
        role = str(r.get("role") or "")
        unit = str(r.get("unit") or "")
        if role not in ROLES or unit not in UNITS:
            raise FreelanceError("Ücret satırında rol ya da birim geçerli değil.")
        price = _money(r.get("price"), "Birim ücret")
        out.append({"role": role, "unit": unit, "price": float(price)})
    return out


def _away(v: Any) -> list[dict[str, Any]]:
    out = []
    for r in v or []:
        if not isinstance(r, dict):
            continue
        a, b = _day(r.get("from"), "Başlangıç"), _day(r.get("to"), "Bitiş")
        if a is None or b is None:
            raise FreelanceError("Müsait olmadığı aralığın iki tarihi de gerekli.")
        if b < a:
            raise FreelanceError("Müsait olmadığı aralıkta bitiş başlangıçtan önce.")
        out.append({"from": a.isoformat(), "to": b.isoformat(), "note": _text(r.get("note"), 120)})
    return sorted(out, key=lambda x: x["from"])


def _person_values(body: dict[str, Any], partial: bool) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if not partial or "name" in body:
        name = _text(body.get("name"), 200)
        if not name:
            raise FreelanceError("Ad soyad gerekli.")
        vals["name"] = name
    if not partial or "roles" in body:
        roles = _roles(body.get("roles"))
        if not roles:
            raise FreelanceError("En az bir iş rolü seçilmeli.")
        vals["roles_json"] = json.dumps(roles)
    if "email" in body or not partial:
        email = _text(body.get("email"), 200)
        if email and not _EMAIL.match(email):
            raise FreelanceError("E-posta adresi geçerli değil.")
        vals["email"] = email.lower() if email else None
    for key, limit in (("phone", 40), ("city", 80), ("website", 300)):
        if key in body or not partial:
            vals[key] = _text(body.get(key), limit)
    if "crmContactId" in body or not partial:
        c = _text(body.get("crmContactId"), 40)
        if c and not _CRM_ID.match(c):
            raise FreelanceError("CRM kişi kimliği geçerli değil.")
        vals["crm_contact_id"] = c.lower() if c else None
    if "logoCard" in body or not partial:
        vals["logo_card"] = _text(body.get("logoCard"), 40)
    if "styles" in body or not partial:
        vals["styles_json"] = json.dumps(_tags(body.get("styles")), ensure_ascii=False)
    if "note" in body or not partial:
        vals["note"] = _text(body.get("note"), 4000)
    if "weeklyHours" in body or not partial:
        vals["weekly_hours"] = _num(body.get("weeklyHours", 20), "Haftalık kapasite", high=80)
    if "rates" in body or not partial:
        vals["rates_json"] = json.dumps(_rates(body.get("rates")), ensure_ascii=False)
    if "away" in body or not partial:
        vals["away_json"] = json.dumps(_away(body.get("away")), ensure_ascii=False)
    if "status" in body:
        if body["status"] not in ("aktif", "pasif"):
            raise FreelanceError("Durum aktif ya da pasif olmalı.")
        vals["status"] = body["status"]
    return vals


def person_stmt(tenant: str, person_id: str):
    return sa.select(PEOPLE).where(PEOPLE.c.id == person_id, PEOPLE.c.tenant_id == tenant)


def _person_row(conn: sa.Connection, tenant: str, person_id: str) -> Any:
    row = conn.execute(person_stmt(tenant, person_id)).first()
    if row is None:
        raise FreelanceError("Serbest çalışan bulunamadı.", 404)
    return row


def _person_out(row: Any) -> dict[str, Any]:
    return {
        "id": row.id, "name": row.name, "roles": _loads(row.roles_json, []), "email": row.email, "phone": row.phone,
        "city": row.city, "website": row.website, "crmContactId": row.crm_contact_id, "logoCard": row.logo_card,
        "styles": _loads(row.styles_json, []), "note": row.note, "weeklyHours": row.weekly_hours,
        "rates": _loads(row.rates_json, []), "away": _loads(row.away_json, []), "status": row.status,
        "createdBy": row.created_by, "createdAt": _iso(row.created_at), "updatedBy": row.updated_by,
        "updatedAt": _iso(row.updated_at),
    }


def create_person(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _person_values(body, partial=False)
    with engine.begin() as conn:
        if vals.get("crm_contact_id"):
            dup = conn.execute(sa.select(PEOPLE.c.id, PEOPLE.c.name).where(
                PEOPLE.c.tenant_id == tenant, PEOPLE.c.crm_contact_id == vals["crm_contact_id"])).first()
            if dup:
                raise FreelanceError(f"Bu CRM kişisi zaten kayıtlı: {dup.name}.", 409)
        if vals.get("email"):
            dup = conn.execute(sa.select(PEOPLE.c.id, PEOPLE.c.name).where(
                PEOPLE.c.tenant_id == tenant, PEOPLE.c.email == vals["email"])).first()
            if dup:
                raise FreelanceError(f"Bu e-posta başka bir kayıtta: {dup.name}.", 409)
        row = {"id": _new(), "tenant_id": tenant, "status": "aktif", "created_by": user, "created_at": _now(), **vals}
        conn.execute(sa.insert(PEOPLE).values(**row))
    return get_person(engine, tenant, row["id"])


def update_person(engine: sa.engine.Engine, tenant: str, user: str, person_id: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _person_values(body, partial=True)
    with engine.begin() as conn:
        _person_row(conn, tenant, person_id)
        if vals.get("email"):
            dup = conn.execute(sa.select(PEOPLE.c.name).where(PEOPLE.c.tenant_id == tenant, PEOPLE.c.email == vals["email"],
                                                              PEOPLE.c.id != person_id)).first()
            if dup:
                raise FreelanceError(f"Bu e-posta başka bir kayıtta: {dup.name}.", 409)
        if vals.get("crm_contact_id"):
            dup = conn.execute(sa.select(PEOPLE.c.name).where(PEOPLE.c.tenant_id == tenant, PEOPLE.c.id != person_id,
                                                              PEOPLE.c.crm_contact_id == vals["crm_contact_id"])).first()
            if dup:
                raise FreelanceError(f"Bu CRM kişisi başka bir kayıtta: {dup.name}.", 409)
        conn.execute(sa.update(PEOPLE).where(PEOPLE.c.id == person_id).values(**vals, updated_by=user, updated_at=_now()))
    return get_person(engine, tenant, person_id)


def _stats(tasks: list[Any], today: date) -> dict[str, Any]:
    done = [t for t in tasks if t.status == "onaylandi"]
    delivered = [t for t in tasks if t.first_delivered_at is not None and t.due is not None]
    on_time = [t for t in delivered if (t.first_delivered_at + timedelta(hours=3)).date() <= t.due]
    late_open = [t for t in tasks if t.status in ACTIVE and t.due is not None and t.due < today]
    return {
        "active": sum(1 for t in tasks if t.status in ACTIVE),
        "waiting": sum(1 for t in tasks if t.status == "teslim"),
        "done": len(done),
        "late": len(late_open),
        "onTimeRate": round(len(on_time) / len(delivered), 3) if delivered else None,
        "avgRevisions": round(sum(t.revisions or 0 for t in done) / len(done), 2) if done else None,
        "payable": float(sum((Decimal(t.units) * Decimal(t.unit_price) for t in done if t.payout_id is None), Decimal("0"))),
    }


def people_stmt(tenant: str, status: str = ""):
    stmt = sa.select(PEOPLE).where(PEOPLE.c.tenant_id == tenant)
    if status in ("aktif", "pasif"):
        stmt = stmt.where(PEOPLE.c.status == status)
    return stmt.order_by(PEOPLE.c.name)


def people_tasks_stmt(tenant: str):
    """Kişi istatistiklerinin görevleri: kişisi olan, iptal olmayan bütün görevler."""
    return sa.select(TASKS).where(TASKS.c.tenant_id == tenant, TASKS.c.person_id.is_not(None), TASKS.c.status != "iptal")


def list_people(engine: sa.engine.Engine, tenant: str, *, q: str = "", role: str = "", status: str = "") -> dict[str, Any]:
    with engine.connect() as conn:
        rows = conn.execute(people_stmt(tenant, status)).all()
        tasks = conn.execute(people_tasks_stmt(tenant)).all()
        thumbs = conn.execute(sa.select(PORTFOLIO.c.person_id, PORTFOLIO.c.id, PORTFOLIO.c.mime)
                              .where(PORTFOLIO.c.person_id.in_([r.id for r in rows] or [""]))
                              .order_by(PORTFOLIO.c.uploaded_at.desc())).all()
    by_person: dict[str, list[Any]] = {}
    for t in tasks:
        by_person.setdefault(t.person_id, []).append(t)
    firsts: dict[str, list[str]] = {}
    for p_id, f_id, mime in thumbs:
        if mime.startswith("image/") and len(firsts.setdefault(p_id, [])) < 3:
            firsts[p_id].append(f_id)
    ql = q.strip().lower()
    today = _today()
    items = []
    for r in rows:
        p = _person_out(r)
        if role and role not in p["roles"]:
            continue
        if ql and ql not in f"{p['name']} {p['email'] or ''} {p['city'] or ''} {' '.join(p['styles'])}".lower():
            continue
        p["stats"] = _stats(by_person.get(r.id, []), today)
        p["preview"] = firsts.get(r.id, [])
        items.append(p)
    return {"items": items, "total": len(items), "roles": [{"key": k, "label": v[0], "unit": v[1], "hoursPerUnit": v[2]}
                                                            for k, v in ROLES.items()], "units": list(UNITS)}


def person_files_stmt(person_id: str):
    return sa.select(PORTFOLIO).where(PORTFOLIO.c.person_id == person_id).order_by(PORTFOLIO.c.uploaded_at.desc())


def person_tasks_stmt(person_id: str):
    return (sa.select(TASKS, PACKAGES.c.title.label("package_title"), PACKAGES.c.book_title)
            .join(PACKAGES, PACKAGES.c.id == TASKS.c.package_id)
            .where(TASKS.c.person_id == person_id, TASKS.c.status != "iptal")
            .order_by(TASKS.c.due.desc().nulls_last(), TASKS.c.created_at.desc()))


def person_payouts_stmt(person_id: str):
    return (sa.select(PAYOUTS).where(PAYOUTS.c.person_id == person_id, PAYOUTS.c.status != DELETED)
            .order_by(PAYOUTS.c.created_at.desc()))


def get_person(engine: sa.engine.Engine, tenant: str, person_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        row = _person_row(conn, tenant, person_id)
        files = conn.execute(person_files_stmt(person_id)).all()
        tasks = conn.execute(person_tasks_stmt(person_id)).all()
        payouts = conn.execute(person_payouts_stmt(person_id)).all()
    out = _person_out(row)
    out["stats"] = _stats(list(tasks), _today())
    out["portfolio"] = [_portfolio_out(f) for f in files]
    out["tasks"] = [_task_out(t, packageTitle=t.package_title, bookTitle=t.book_title) for t in tasks]
    out["payouts"] = [_payout_head(p) for p in payouts]
    return out


def lookup_crm(engine: sa.engine.Engine, tenant: str, crm_ids: list[str]) -> dict[str, str]:
    ids = [c.lower() for c in crm_ids if _CRM_ID.match(c or "")][:200]
    if not ids:
        return {}
    with engine.connect() as conn:
        rows = conn.execute(sa.select(PEOPLE.c.crm_contact_id, PEOPLE.c.id).where(
            PEOPLE.c.tenant_id == tenant, PEOPLE.c.crm_contact_id.in_(ids))).all()
    return {r.crm_contact_id: r.id for r in rows}


# ---------------------------------------------------------------------------------------------- portfolyo

def _portfolio_out(f: Any) -> dict[str, Any]:
    return {"id": f.id, "title": f.title, "tags": _loads(f.tags_json, []), "book": f.book, "filename": f.filename,
            "mime": f.mime, "bytes": f.bytes, "uploadedBy": f.uploaded_by, "uploadedAt": _iso(f.uploaded_at)}


def _magic(data: bytes, mime: str) -> bool:
    head = data[:16]
    return {
        "image/jpeg": head.startswith(b"\xff\xd8\xff"),
        "image/png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": head.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": head[:4] == b"RIFF" and head[8:12] == b"WEBP",
        "application/pdf": head.startswith(b"%PDF"),
    }.get(mime, False)


def _write(folder: str, name: str, data: bytes) -> tuple[str, str]:
    path = os.path.join(folder, name)
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as e:
        # Klasör yazılamıyor ya da disk dolu: iz günlükte, kişiye düz cümle (kurulumda FREELANCE_DIR köprünün kullanıcısına açılmalı).
        log.error("serbest çalışan dosyası yazılamadı (%s): %s", path, e)
        raise FreelanceError("Dosya sunucuya kaydedilemedi; yöneticiye bildirin.", 503) from e
    return path, hashlib.sha256(data).hexdigest()


def _ext(filename: str) -> str:
    return re.sub(r"[^a-z0-9]", "", filename.lower().rsplit(".", 1)[-1])[:8] if "." in filename else ""


def add_portfolio(engine: sa.engine.Engine, tenant: str, user: str, person_id: str, filename: str, data: bytes,
                  meta: dict[str, Any]) -> dict[str, Any]:
    ext = _ext(filename)
    mime = PORTFOLIO_EXT.get(ext)
    if not mime:
        raise FreelanceError("Portfolyo dosyası JPG, PNG, WEBP, GIF ya da PDF olmalı.")
    if not data:
        raise FreelanceError("Dosya boş.")
    if len(data) > PORTFOLIO_MAX:
        raise FreelanceError("Portfolyo dosyası 40 MB sınırını aşıyor.", 413)
    if not _magic(data, mime):
        raise FreelanceError("Dosyanın içeriği uzantısıyla uyuşmuyor.")
    with engine.connect() as conn:
        _person_row(conn, tenant, person_id)
    fid = _new()
    path, sha = _write(os.path.join(_root(), "people", person_id), f"{fid}.{ext}", data)
    row = {"id": fid, "person_id": person_id, "title": _text(meta.get("title"), 200) or _text(filename.rsplit(".", 1)[0], 200),
           "tags_json": json.dumps(_tags(meta.get("tags"), 10), ensure_ascii=False), "book": _text(meta.get("book"), 300),
           "filename": filename[:300], "mime": mime, "bytes": len(data), "sha256": sha, "path": path,
           "uploaded_by": user, "uploaded_at": _now()}
    with engine.begin() as conn:
        conn.execute(sa.insert(PORTFOLIO).values(**row))
    return _portfolio_out(_Obj(row))


class _Obj:
    """Sözlüğü satır gibi okutur (eklenen kaydı yeniden sorgulamadan döndürmek için)."""

    def __init__(self, d: dict[str, Any]):
        self.__dict__.update(d)


def update_portfolio(engine: sa.engine.Engine, tenant: str, file_id: str, body: dict[str, Any]) -> None:
    vals: dict[str, Any] = {}
    if "title" in body:
        vals["title"] = _text(body.get("title"), 200)
    if "tags" in body:
        vals["tags_json"] = json.dumps(_tags(body.get("tags"), 10), ensure_ascii=False)
    if "book" in body:
        vals["book"] = _text(body.get("book"), 300)
    with engine.begin() as conn:
        _portfolio_row(conn, tenant, file_id)
        if vals:
            conn.execute(sa.update(PORTFOLIO).where(PORTFOLIO.c.id == file_id).values(**vals))


def _portfolio_row(conn: sa.Connection, tenant: str, file_id: str) -> Any:
    row = conn.execute(sa.select(PORTFOLIO).join(PEOPLE, PEOPLE.c.id == PORTFOLIO.c.person_id)
                       .where(PORTFOLIO.c.id == file_id, PEOPLE.c.tenant_id == tenant)).first()
    if row is None:
        raise FreelanceError("Portfolyo dosyası bulunamadı.", 404)
    return row


def delete_portfolio(engine: sa.engine.Engine, tenant: str, file_id: str) -> dict[str, Any]:
    with engine.begin() as conn:
        row = _portfolio_row(conn, tenant, file_id)
        conn.execute(sa.delete(PORTFOLIO).where(PORTFOLIO.c.id == file_id))
    try:
        os.remove(row.path)
    except OSError:
        log.warning("portfolyo dosyası diskte yoktu: %s", row.path)
    return {"filename": row.filename, "personId": row.person_id}


def portfolio_file(engine: sa.engine.Engine, tenant: str, file_id: str) -> tuple[str, str, str]:
    with engine.connect() as conn:
        row = _portfolio_row(conn, tenant, file_id)
    if not os.path.exists(row.path):
        raise FreelanceError("Dosya sunucuda bulunamadı.", 410)
    return row.path, row.filename, row.mime


# ---------------------------------------------------------------------------------------------- paket ve görev

def _task_out(t: Any, **extra: Any) -> dict[str, Any]:
    units, price = Decimal(t.units), Decimal(t.unit_price)
    return {
        "id": t.id, "packageId": t.package_id, "personId": t.person_id, "title": t.title, "role": t.role,
        "units": float(units), "unit": t.unit, "unitPrice": float(price), "amount": float((units * price).quantize(Decimal("0.01"))),
        "effortHours": t.effort_hours, "start": _iso(t.start), "due": _iso(t.due), "status": t.status,
        "revisions": t.revisions or 0, "assignedAt": _iso(t.assigned_at), "assignedBy": t.assigned_by,
        "firstDeliveredAt": _iso(t.first_delivered_at), "acceptedAt": _iso(t.accepted_at), "acceptedBy": t.accepted_by,
        "payoutId": t.payout_id, "late": bool(t.status in ACTIVE and t.due and t.due < _today()), **extra,
    }


def package_stmt(tenant: str, package_id: str):
    return sa.select(PACKAGES).where(PACKAGES.c.id == package_id, PACKAGES.c.tenant_id == tenant)


def _package_row(conn: sa.Connection, tenant: str, package_id: str) -> Any:
    row = conn.execute(package_stmt(tenant, package_id)).first()
    if row is None:
        raise FreelanceError("İş paketi bulunamadı.", 404)
    return row


def _task_row(conn: sa.Connection, tenant: str, task_id: str) -> Any:
    row = conn.execute(task_stmt(tenant, task_id)).first()
    if row is None:
        raise FreelanceError("Görev bulunamadı.", 404)
    return row


def _task_values(body: dict[str, Any], role_default: str, partial: bool) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if not partial or "title" in body:
        title = _text(body.get("title"), 300)
        if not title:
            raise FreelanceError("Görev adı gerekli.")
        vals["title"] = title
    role = str(body.get("role") or role_default)
    if not partial or "role" in body:
        if role not in ROLES:
            raise FreelanceError("Görevin rolü geçerli değil.")
        vals["role"] = role
    if not partial or "units" in body:
        vals["units"] = _money(body.get("units"), "Miktar")
        if vals["units"] <= 0:
            raise FreelanceError("Miktar sıfırdan büyük olmalı.")
    if not partial or "unit" in body:
        unit = str(body.get("unit") or ROLES.get(role, ("", "iş"))[1])
        if unit not in UNITS:
            raise FreelanceError("Birim geçerli değil.")
        vals["unit"] = unit
    if not partial or "unitPrice" in body:
        vals["unit_price"] = _money(body.get("unitPrice"), "Birim ücret")
    if not partial or "effortHours" in body:
        eff = body.get("effortHours")
        if eff in (None, "") and "units" in vals:
            eff = float(vals["units"]) * ROLES[role][2]
        vals["effort_hours"] = round(_num(eff, "Tahmini süre", high=5000), 2)
    for key in ("start", "due"):
        if not partial or key in body:
            vals[key] = _day(body.get(key), "Başlangıç" if key == "start" else "Termin")
    if vals.get("start") and vals.get("due") and vals["due"] < vals["start"]:
        raise FreelanceError("Termin başlangıçtan önce olamaz.")
    return vals


def create_package(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    title = _text(body.get("title"), 300)
    if not title:
        raise FreelanceError("İş paketinin adı gerekli.")
    role = str(body.get("role") or "")
    if role not in ROLES:
        raise FreelanceError("İş paketinin rolü seçilmeli.")
    due = _day(body.get("due"), "Termin")
    # Kitap CRM'den seçildiyse kimliği tutulur; elle yazılan (henüz CRM'de olmayan) kitapta yalnız ad kalır.
    book_id = _text(body.get("bookId"), 40)
    if book_id and not _CRM_ID.match(book_id):
        book_id = None
    pid = _new()
    now = _now()
    tasks = []
    for i, t in enumerate(body.get("tasks") or []):
        if not isinstance(t, dict):
            continue
        vals = _task_values({**t, "due": t.get("due") or (due.isoformat() if due else None)}, role, partial=False)
        tasks.append({"id": _new(), "tenant_id": tenant, "package_id": pid, "person_id": None, "status": "atanmadi",
                      "revisions": 0, "created_at": now + timedelta(microseconds=i), **vals})
    if not tasks:
        raise FreelanceError("Pakete en az bir görev eklenmeli.")
    with engine.begin() as conn:
        conn.execute(sa.insert(PACKAGES).values(
            id=pid, tenant_id=tenant, title=title, book_title=_text(body.get("bookTitle"), 300),
            book_id=book_id.lower() if book_id else None, role=role, brief=_text(body.get("brief"), 8000), due=due,
            status="acik", owner=user, created_by=user, created_at=now))
        conn.execute(sa.insert(TASKS), tasks)
        _system(conn, tenant, f"p:{pid}", user, f"İş paketi açıldı: {len(tasks)} görev.")
    return {"id": pid, "title": title}


def update_package(engine: sa.engine.Engine, tenant: str, user: str, package_id: str, body: dict[str, Any]) -> None:
    vals: dict[str, Any] = {}
    if "title" in body:
        vals["title"] = _text(body.get("title"), 300)
        if not vals["title"]:
            raise FreelanceError("İş paketinin adı gerekli.")
    if "brief" in body:
        vals["brief"] = _text(body.get("brief"), 8000)
    if "bookTitle" in body:
        vals["book_title"] = _text(body.get("bookTitle"), 300)
    if "due" in body:
        vals["due"] = _day(body.get("due"), "Termin")
    if "status" in body:
        if body["status"] not in ("acik", "kapandi", "iptal"):
            raise FreelanceError("Paket durumu geçerli değil.")
        vals["status"] = body["status"]
    with engine.begin() as conn:
        pkg = _package_row(conn, tenant, package_id)
        if vals.get("status") == "iptal":
            busy = conn.execute(sa.select(sa.func.count()).select_from(TASKS).where(
                TASKS.c.package_id == package_id, TASKS.c.payout_id.is_not(None))).scalar_one()
            if busy:
                raise FreelanceError("Hakedişe girmiş görevi olan paket iptal edilemez.", 409)
            conn.execute(sa.update(TASKS).where(TASKS.c.package_id == package_id, TASKS.c.status != "onaylandi")
                         .values(status="iptal"))
        if vals:
            conn.execute(sa.update(PACKAGES).where(PACKAGES.c.id == package_id).values(**vals))
        if "status" in vals and vals["status"] != pkg.status:
            _system(conn, tenant, f"p:{package_id}", user,
                    {"acik": "Paket yeniden açıldı.", "kapandi": "Paket kapatıldı.", "iptal": "Paket iptal edildi."}[vals["status"]])


def add_tasks(engine: sa.engine.Engine, tenant: str, user: str, package_id: str, items: list[dict[str, Any]]) -> int:
    now = _now()
    with engine.begin() as conn:
        pkg = _package_row(conn, tenant, package_id)
        if pkg.status != "acik":
            raise FreelanceError("Kapalı pakete görev eklenemez.", 409)
        rows = []
        for i, t in enumerate(items):
            vals = _task_values({**t, "due": t.get("due") or (pkg.due.isoformat() if pkg.due else None)}, pkg.role, partial=False)
            rows.append({"id": _new(), "tenant_id": tenant, "package_id": package_id, "person_id": None, "status": "atanmadi",
                         "revisions": 0, "created_at": now + timedelta(microseconds=i), **vals})
        if not rows:
            raise FreelanceError("Eklenecek görev yok.")
        conn.execute(sa.insert(TASKS), rows)
    return len(rows)


def update_task(engine: sa.engine.Engine, tenant: str, user: str, task_id: str, body: dict[str, Any]) -> None:
    with engine.begin() as conn:
        t = _task_row(conn, tenant, task_id)
        if t.payout_id and any(k in body for k in ("units", "unitPrice", "unit")):
            raise FreelanceError("Hakedişe girmiş görevin tutarı değiştirilemez.", 409)
        vals = _task_values(body, t.role, partial=True)
        start = vals.get("start", t.start)
        due = vals.get("due", t.due)
        if start and due and due < start:
            raise FreelanceError("Termin başlangıçtan önce olamaz.")
        if "status" in body:
            st = body["status"]
            allowed = {"atandi": ("calisiyor", "iptal"), "calisiyor": ("atandi", "iptal"), "revizyon": ("iptal",),
                       "atanmadi": ("iptal",), "iptal": ("atanmadi",)}
            if st != t.status and st not in allowed.get(t.status, ()):
                raise FreelanceError("Bu durum değişikliği buradan yapılamaz.", 409)
            if st == "atanmadi" and t.status == "iptal":
                vals["person_id"] = None
            vals["status"] = st
        if vals:
            conn.execute(sa.update(TASKS).where(TASKS.c.id == task_id).values(**vals))
        if vals.get("status") in ("calisiyor", "iptal") and vals["status"] != t.status:
            _system(conn, tenant, f"p:{t.package_id}", user,
                    f"«{t.title}» " + ("üzerinde çalışılıyor." if vals["status"] == "calisiyor" else "iptal edildi."), task_id)


def delete_task(engine: sa.engine.Engine, tenant: str, user: str, task_id: str) -> None:
    with engine.begin() as conn:
        t = _task_row(conn, tenant, task_id)
        if t.status != "atanmadi":
            raise FreelanceError("Yalnız atanmamış görev silinebilir; atanmış görevi iptal edin.", 409)
        conn.execute(sa.delete(TASKS).where(TASKS.c.id == task_id))


def assign(engine: sa.engine.Engine, tenant: str, user: str, pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Toplu atama: [{taskId, personId|None}]. None ataması geri alır (yalnız teslim öncesi)."""
    if not pairs:
        raise FreelanceError("Atanacak görev seçilmedi.")
    now = _now()
    done = []
    with engine.begin() as conn:
        for p in pairs:
            t = _task_row(conn, tenant, str(p.get("taskId") or ""))
            person_id = p.get("personId") or None
            if t.status not in ("atanmadi", "atandi", "calisiyor"):
                raise FreelanceError(f"«{t.title}» teslim aşamasında; ataması değiştirilemez.", 409)
            if person_id is None:
                if t.person_id is None:
                    continue
                conn.execute(sa.update(TASKS).where(TASKS.c.id == t.id).values(person_id=None, status="atanmadi",
                                                                               assigned_at=None, assigned_by=None))
                _system(conn, tenant, f"p:{t.package_id}", user, f"«{t.title}» ataması geri alındı.", t.id)
                done.append({"taskId": t.id, "personId": None})
                continue
            person = _person_row(conn, tenant, str(person_id))
            if person.status != "aktif":
                raise FreelanceError(f"{person.name} pasif; iş atanamaz.", 409)
            if person.id == t.person_id:
                continue
            conn.execute(sa.update(TASKS).where(TASKS.c.id == t.id).values(
                person_id=person.id, status="atandi", assigned_at=now, assigned_by=user,
                start=t.start or _today()))
            _system(conn, tenant, f"p:{t.package_id}", user, f"«{t.title}» → {person.name}.", t.id)
            done.append({"taskId": t.id, "personId": person.id, "name": person.name, "email": person.email,
                         "packageId": t.package_id})
    return done


def _packages_where(tenant: str, status: str) -> list[Any]:
    where = [PACKAGES.c.tenant_id == tenant]
    if status in ("acik", "kapandi", "iptal"):
        where.append(PACKAGES.c.status == status)
    return where


def packages_stmt(tenant: str, status: str = "acik"):
    return (sa.select(PACKAGES).where(*_packages_where(tenant, status))
            .order_by(PACKAGES.c.due.asc().nulls_last(), PACKAGES.c.created_at.desc()))


def packages_tasks_stmt(tenant: str, status: str = "acik"):
    """Süzgeçteki paketlerin bütün görevleri (paket kimlikleri alt sorguyla: listede çalışan ifade budur)."""
    return sa.select(TASKS).where(TASKS.c.package_id.in_(sa.select(PACKAGES.c.id).where(*_packages_where(tenant, status))))


def packages_threads(tenant: str, status: str = "acik"):
    """Süzgeçteki paketlerin yazışma kimlikleri («p:<paket>»)."""
    return sa.select((sa.literal("p:", sa.String) + PACKAGES.c.id).label("thread")).where(*_packages_where(tenant, status))


def list_packages(engine: sa.engine.Engine, tenant: str, user: str, *, q: str = "", status: str = "acik") -> dict[str, Any]:
    with engine.connect() as conn:
        pkgs = conn.execute(packages_stmt(tenant, status)).all()
        tasks = conn.execute(packages_tasks_stmt(tenant, status)).all() if pkgs else []
        people = {r.id: r.name for r in conn.execute(sa.select(PEOPLE.c.id, PEOPLE.c.name).where(PEOPLE.c.tenant_id == tenant))}
        unread = _unread(conn, tenant, user, packages_threads(tenant, status)) if pkgs else {}
    by_pkg: dict[str, list[Any]] = {}
    for t in tasks:
        by_pkg.setdefault(t.package_id, []).append(t)
    ql = q.strip().lower()
    items = []
    today = _today()
    for p in pkgs:
        if ql and ql not in f"{p.title} {p.book_title or ''}".lower():
            continue
        ts = [t for t in by_pkg.get(p.id, []) if t.status != "iptal"]
        counts = {s: sum(1 for t in ts if t.status == s) for s in TASK_STATES}
        items.append({
            "id": p.id, "title": p.title, "bookTitle": p.book_title, "role": p.role, "due": _iso(p.due), "status": p.status,
            "owner": p.owner, "createdAt": _iso(p.created_at), "tasks": len(ts), "counts": counts,
            "people": sorted({people.get(t.person_id, "") for t in ts if t.person_id} - {""}),
            "amount": float(sum((Decimal(t.units) * Decimal(t.unit_price) for t in ts), Decimal("0"))),
            "late": sum(1 for t in ts if t.status in ACTIVE and t.due and t.due < today),
            "unread": unread.get(f"p:{p.id}", 0),
        })
    return {"items": items, "total": len(items)}


def package_tasks_stmt(package_id: str):
    return sa.select(TASKS).where(TASKS.c.package_id == package_id).order_by(TASKS.c.created_at)


def package_deliveries_stmt(package_id: str):
    """Paketin görevlerinin teslimleri (görev kimlikleri alt sorguyla), en yeni sürüm önce."""
    return (sa.select(DELIVERIES).where(DELIVERIES.c.task_id.in_(sa.select(TASKS.c.id).where(TASKS.c.package_id == package_id)))
            .order_by(DELIVERIES.c.version.desc()))


def get_package(engine: sa.engine.Engine, tenant: str, package_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        p = _package_row(conn, tenant, package_id)
        tasks = conn.execute(package_tasks_stmt(package_id)).all()
        people = {r.id: r for r in conn.execute(sa.select(PEOPLE.c.id, PEOPLE.c.name, PEOPLE.c.email).where(
            PEOPLE.c.tenant_id == tenant, PEOPLE.c.id.in_([t.person_id for t in tasks if t.person_id] or [""])))}
        dels = conn.execute(package_deliveries_stmt(package_id)).all() if tasks else []
    by_task: dict[str, list[Any]] = {}
    for d in dels:
        by_task.setdefault(d.task_id, []).append(d)
    return {
        "id": p.id, "title": p.title, "bookTitle": p.book_title, "bookId": p.book_id, "role": p.role, "brief": p.brief,
        "due": _iso(p.due), "status": p.status, "owner": p.owner, "createdBy": p.created_by, "createdAt": _iso(p.created_at),
        "tasks": [_task_out(t, personName=people[t.person_id].name if t.person_id in people else None,
                            personEmail=people[t.person_id].email if t.person_id in people else None,
                            deliveries=[_delivery_out(d) for d in by_task.get(t.id, [])]) for t in tasks],
    }


# ---------------------------------------------------------------------------------------------- kapasite

def _workdays(a: date, b: date, away: list[tuple[date, date]]) -> list[date]:
    out = []
    d = a
    while d <= b:
        if d.weekday() < WORKDAYS and not any(x <= d <= y for x, y in away):
            out.append(d)
        d += timedelta(days=1)
    return out


def _away_ranges(row: Any) -> list[tuple[date, date]]:
    return [(date.fromisoformat(a["from"]), date.fromisoformat(a["to"])) for a in _loads(row.away_json, [])]


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def load_by_day(tasks: Iterable[Any], away: list[tuple[date, date]], today: date) -> dict[date, float]:
    """Görevin saatini başlangıç–termin arasındaki iş günlerine eşit dağıtır. Termini geçmiş iş bugüne yazılır."""
    out: dict[date, float] = {}
    for t in tasks:
        if t.status not in ACTIVE:
            continue
        start = t.start or today
        due = t.due or start
        if due < today:
            days = [today]
        else:
            # Geçmiş günlere düşen pay yapılmış sayılmaz; kalan iş kalan iş günlerine yayılır.
            days = _workdays(max(start, today), due, away) or [max(due, today)]
        share = float(t.effort_hours or 0) / len(days)
        for d in days:
            out[d] = out.get(d, 0.0) + share
    return out


def active_people_stmt(tenant: str):
    return sa.select(PEOPLE).where(PEOPLE.c.tenant_id == tenant, PEOPLE.c.status == "aktif").order_by(PEOPLE.c.name)


def capacity_tasks_stmt(tenant: str):
    return (sa.select(TASKS, PACKAGES.c.title.label("package_title")).join(PACKAGES, PACKAGES.c.id == TASKS.c.package_id)
            .where(TASKS.c.tenant_id == tenant, TASKS.c.status.in_(ACTIVE)))


def unassigned_stmt(tenant: str):
    return (sa.select(sa.func.count(), sa.func.coalesce(sa.func.sum(TASKS.c.effort_hours), 0.0))
            .select_from(TASKS).join(PACKAGES, PACKAGES.c.id == TASKS.c.package_id)
            .where(TASKS.c.tenant_id == tenant, TASKS.c.status == "atanmadi", PACKAGES.c.status == "acik"))


def capacity(engine: sa.engine.Engine, tenant: str, *, weeks: int = 8, role: str = "", start: Optional[str] = None) -> dict[str, Any]:
    weeks = max(1, min(int(weeks or 8), 26))
    today = _today()
    first = _monday(_day(start, "Başlangıç") or today)
    week_starts = [first + timedelta(weeks=i) for i in range(weeks)]
    with engine.connect() as conn:
        people = conn.execute(active_people_stmt(tenant)).all()
        tasks = conn.execute(capacity_tasks_stmt(tenant)).all()
        unassigned = conn.execute(unassigned_stmt(tenant)).one()
    by_person: dict[str, list[Any]] = {}
    for t in tasks:
        by_person.setdefault(t.person_id, []).append(t)
    rows = []
    for p in people:
        roles = _loads(p.roles_json, [])
        if role and role not in roles:
            continue
        away = _away_ranges(p)
        daily = load_by_day(by_person.get(p.id, []), away, today)
        cells = []
        for ws in week_starts:
            we = ws + timedelta(days=6)
            # İçinde bulunulan haftada yalnız kalan iş günleri sayılır.
            cap = round(p.weekly_hours * len(_workdays(max(ws, today), we, away)) / WORKDAYS, 1) if we >= today else 0.0
            load = round(sum(h for d, h in daily.items() if ws <= d <= we), 1)
            cells.append({"week": ws.isoformat(), "capacity": cap, "load": load,
                          "ratio": round(load / cap, 2) if cap else (None if not load else 9.99),
                          "away": any(x <= we and y >= ws for x, y in away)})
        active = by_person.get(p.id, [])
        rows.append({"id": p.id, "name": p.name, "roles": roles, "weeklyHours": p.weekly_hours, "weeks": cells,
                     "active": len(active), "late": sum(1 for t in active if t.due and t.due < today),
                     "tasks": [{"id": t.id, "title": t.title, "packageId": t.package_id, "packageTitle": t.package_title,
                                "start": _iso(t.start), "due": _iso(t.due), "effortHours": t.effort_hours, "status": t.status,
                                "late": bool(t.due and t.due < today)} for t in sorted(active, key=lambda t: (t.due or date.max))]})
    return {"weeks": [w.isoformat() for w in week_starts], "today": today.isoformat(), "people": rows,
            "unassigned": {"tasks": int(unassigned[0]), "hours": round(float(unassigned[1] or 0), 1)}}


def task_stmt(tenant: str, task_id: str):
    return sa.select(TASKS).where(TASKS.c.id == task_id, TASKS.c.tenant_id == tenant)


def suggest_active_stmt(tenant: str):
    return sa.select(TASKS).where(TASKS.c.tenant_id == tenant, TASKS.c.status.in_(ACTIVE), TASKS.c.person_id.is_not(None))


def suggest_history_stmt(tenant: str):
    return sa.select(TASKS).where(TASKS.c.tenant_id == tenant, TASKS.c.person_id.is_not(None),
                                  TASKS.c.first_delivered_at.is_not(None))


def suggest(engine: sa.engine.Engine, tenant: str, task_ids: list[str]) -> list[dict[str, Any]]:
    """Seçili atanmamış görevler için sıralı öneri. Sıra: rol uyar → görev aralığında boş saat yeter → boş saat çok
    → zamanında teslim oranı yüksek. Birden çok görevde önceki önerinin yükü sonrakine eklenir (aynı kişiye yığılmaz)."""
    today = _today()
    with engine.connect() as conn:
        tasks = [_task_row(conn, tenant, tid) for tid in task_ids[:200]]
        people = conn.execute(active_people_stmt(tenant)).all()
        active = conn.execute(suggest_active_stmt(tenant)).all()
        history = conn.execute(suggest_history_stmt(tenant)).all()
    by_person: dict[str, list[Any]] = {}
    for t in active:
        by_person.setdefault(t.person_id, []).append(t)
    hist: dict[str, list[Any]] = {}
    for t in history:
        hist.setdefault(t.person_id, []).append(t)
    daily = {p.id: load_by_day(by_person.get(p.id, []), _away_ranges(p), today) for p in people}
    out = []
    for t in tasks:
        if t.status != "atanmadi":
            out.append({"taskId": t.id, "candidates": [], "note": "Görev zaten atanmış."})
            continue
        start = max(t.start or today, today)
        due = t.due or (start + timedelta(days=13))
        cands = []
        for p in people:
            if t.role not in _loads(p.roles_json, []):
                continue
            away = _away_ranges(p)
            days = _workdays(start, due, away)
            if not days:
                cands.append({"personId": p.id, "name": p.name, "freeHours": 0.0, "fits": False, "onTimeRate": None,
                              "reason": "Görev aralığında müsait değil."})
                continue
            cap = p.weekly_hours / WORKDAYS * len(days)
            used = sum(daily[p.id].get(d, 0.0) for d in days)
            free = round(cap - used, 1)
            st = _stats(hist.get(p.id, []), today)
            fits = free >= float(t.effort_hours)
            reason = (f"Aralıkta {free:g} saat boş, iş {float(t.effort_hours):g} saat" if fits
                      else f"Aralıkta yalnız {max(free, 0):g} saat boş, iş {float(t.effort_hours):g} saat")
            if st["onTimeRate"] is not None:
                reason += f"; zamanında teslim %{round(st['onTimeRate'] * 100)}"
            cands.append({"personId": p.id, "name": p.name, "freeHours": free, "fits": fits,
                          "onTimeRate": st["onTimeRate"], "reason": reason, "_days": days})
        cands.sort(key=lambda c: (not c["fits"], -(c["freeHours"]), -(c["onTimeRate"] if c["onTimeRate"] is not None else 0.5)))
        best = next((c for c in cands if c["fits"]), None)
        if best:
            share = float(t.effort_hours) / len(best["_days"])
            for d in best["_days"]:
                daily[best["personId"]][d] = daily[best["personId"]].get(d, 0.0) + share
        for c in cands:
            c.pop("_days", None)
        out.append({"taskId": t.id, "title": t.title, "role": t.role, "candidates": cands[:5],
                    "suggested": best["personId"] if best else None,
                    "note": None if best else ("Bu rolde kayıtlı aktif kişi yok." if not cands else "Hiçbir kişinin aralıkta yeterli boş saati yok.")})
    return out


# ---------------------------------------------------------------------------------------------- teslim

def _delivery_out(d: Any) -> dict[str, Any]:
    return {"id": d.id, "taskId": d.task_id, "version": d.version, "note": d.note, "link": d.link, "filename": d.filename,
            "bytes": d.bytes, "uploadedBy": d.uploaded_by, "uploadedAt": _iso(d.uploaded_at), "decision": d.decision,
            "decisionNote": d.decision_note, "decidedBy": d.decided_by, "decidedAt": _iso(d.decided_at)}


def add_delivery(engine: sa.engine.Engine, tenant: str, user: str, task_id: str, *, filename: str = "",
                 data: bytes = b"", link: str = "", note: str = "") -> dict[str, Any]:
    link = (link or "").strip()
    if link and not re.match(r"^https?://\S+$", link):
        raise FreelanceError("Bağlantı http:// ya da https:// ile başlamalı.")
    if not data and not link:
        raise FreelanceError("Teslim için dosya ya da bağlantı gerekli.")
    if data and len(data) > DELIVERY_MAX:
        raise FreelanceError("Teslim dosyası 200 MB sınırını aşıyor; daha büyük dosya için bağlantı verin.", 413)
    now = _now()
    with engine.begin() as conn:
        t = _task_row(conn, tenant, task_id)
        if t.status not in ("atandi", "calisiyor", "revizyon", "teslim"):
            raise FreelanceError("Bu görev teslim beklemiyor.", 409)
        if t.status == "teslim":
            raise FreelanceError("Önceki teslim henüz incelenmedi.", 409)
        version = (conn.execute(sa.select(sa.func.max(DELIVERIES.c.version)).where(DELIVERIES.c.task_id == task_id)).scalar() or 0) + 1
        did = _new()
        path = sha = None
        if data:
            ext = _ext(filename) or "bin"
            path, sha = _write(os.path.join(_root(), "tasks", task_id), f"v{version}-{did}.{ext}", data)
        conn.execute(sa.insert(DELIVERIES).values(
            id=did, task_id=task_id, version=version, note=_text(note, 4000), link=link[:1000] or None,
            filename=(filename[:300] or None) if data else None, bytes=len(data) if data else None, sha256=sha, path=path,
            uploaded_by=user, uploaded_at=now, decision="bekliyor"))
        conn.execute(sa.update(TASKS).where(TASKS.c.id == task_id).values(
            status="teslim", first_delivered_at=t.first_delivered_at or now))
        _system(conn, tenant, f"p:{t.package_id}", user, f"«{t.title}» teslim alındı (sürüm {version}).", task_id)
    return {"id": did, "version": version}


def decide_delivery(engine: sa.engine.Engine, tenant: str, user: str, delivery_id: str, body: dict[str, Any]) -> dict[str, Any]:
    decision = body.get("decision")
    if decision not in ("kabul", "revizyon"):
        raise FreelanceError("Karar kabul ya da revizyon olmalı.")
    note = _text(body.get("note"), 4000)
    if decision == "revizyon" and not note:
        raise FreelanceError("Revizyon için ne düzeltileceği yazılmalı.")
    now = _now()
    with engine.begin() as conn:
        d = conn.execute(sa.select(DELIVERIES).where(DELIVERIES.c.id == delivery_id)).first()
        if d is None:
            raise FreelanceError("Teslim bulunamadı.", 404)
        t = _task_row(conn, tenant, d.task_id)
        if d.decision != "bekliyor":
            raise FreelanceError("Bu teslim zaten karara bağlandı.", 409)
        conn.execute(sa.update(DELIVERIES).where(DELIVERIES.c.id == delivery_id).values(
            decision=decision, decision_note=note, decided_by=user, decided_at=now))
        if decision == "kabul":
            conn.execute(sa.update(TASKS).where(TASKS.c.id == t.id).values(status="onaylandi", accepted_at=now, accepted_by=user))
            _system(conn, tenant, f"p:{t.package_id}", user, f"«{t.title}» kabul edildi; ödenecek işlere düştü.", t.id)
        else:
            conn.execute(sa.update(TASKS).where(TASKS.c.id == t.id).values(status="revizyon", revisions=(t.revisions or 0) + 1))
            _system(conn, tenant, f"p:{t.package_id}", user, f"«{t.title}» revizyona döndü: {note}", t.id)
        person = conn.execute(sa.select(PEOPLE.c.name, PEOPLE.c.email).where(PEOPLE.c.id == t.person_id)).first()
    return {"taskId": t.id, "packageId": t.package_id, "title": t.title, "decision": decision, "note": note,
            "personName": person.name if person else None, "personEmail": person.email if person else None}


def delivery_file(engine: sa.engine.Engine, tenant: str, delivery_id: str) -> tuple[str, str]:
    with engine.connect() as conn:
        d = conn.execute(sa.select(DELIVERIES).where(DELIVERIES.c.id == delivery_id)).first()
        if d is None:
            raise FreelanceError("Teslim bulunamadı.", 404)
        _task_row(conn, tenant, d.task_id)
    if not d.path:
        raise FreelanceError("Bu teslim bir bağlantı; dosyası yok.", 404)
    if not os.path.exists(d.path):
        raise FreelanceError("Dosya sunucuda bulunamadı.", 410)
    return d.path, d.filename or os.path.basename(d.path)


# ---------------------------------------------------------------------------------------------- hakediş

def _payout_head(p: Any, person_name: Optional[str] = None) -> dict[str, Any]:
    return {"id": p.id, "no": p.no, "personId": p.person_id, "personName": person_name, "status": p.status,
            "total": float(p.total), "note": p.note, "returnNote": p.return_note, "createdBy": p.created_by,
            "createdAt": _iso(p.created_at), "submittedBy": p.submitted_by, "submittedAt": _iso(p.submitted_at),
            "approvedBy": p.approved_by, "approvedAt": _iso(p.approved_at), "paidOn": _iso(p.paid_on),
            "paidRef": p.paid_ref, "paidBy": p.paid_by}


def payable_stmt(tenant: str):
    """Ödenecek iş: kabul edilmiş, hakedişe girmemiş görevler."""
    return (sa.select(TASKS, PACKAGES.c.title.label("package_title"), PACKAGES.c.book_title, PEOPLE.c.name.label("person_name"))
            .join(PACKAGES, PACKAGES.c.id == TASKS.c.package_id)
            .join(PEOPLE, PEOPLE.c.id == TASKS.c.person_id)
            .where(TASKS.c.tenant_id == tenant, TASKS.c.status == "onaylandi", TASKS.c.payout_id.is_(None))
            .order_by(PEOPLE.c.name, TASKS.c.accepted_at))


def payable(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(payable_stmt(tenant)).all()
    groups: dict[str, dict[str, Any]] = {}
    for r in rows:
        g = groups.setdefault(r.person_id, {"personId": r.person_id, "personName": r.person_name, "tasks": [], "total": 0.0})
        task = _task_out(r, packageTitle=r.package_title, bookTitle=r.book_title)
        g["tasks"].append(task)
        g["total"] = round(g["total"] + task["amount"], 2)
    return list(groups.values())


def create_payout(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    person_id = str(body.get("personId") or "")
    wanted = [str(x) for x in body.get("taskIds") or []]
    now = _now()
    with engine.begin() as conn:
        person = _person_row(conn, tenant, person_id)
        stmt = sa.select(TASKS, PACKAGES.c.title.label("package_title"), PACKAGES.c.book_title).join(
            PACKAGES, PACKAGES.c.id == TASKS.c.package_id).where(
            TASKS.c.tenant_id == tenant, TASKS.c.person_id == person_id, TASKS.c.status == "onaylandi",
            TASKS.c.payout_id.is_(None))
        if wanted:
            stmt = stmt.where(TASKS.c.id.in_(wanted))
        tasks = conn.execute(stmt.order_by(TASKS.c.accepted_at)).all()
        if not tasks or (wanted and len(tasks) != len(set(wanted))):
            raise FreelanceError("Seçilen işlerin hepsi bu kişinin ödenmemiş, kabul edilmiş işi olmalı.", 409)
        no = (conn.execute(sa.select(sa.func.max(PAYOUTS.c.no)).where(PAYOUTS.c.tenant_id == tenant)).scalar() or 0) + 1
        pid = _new()
        lines, total = [], Decimal("0")
        for t in tasks:
            amount = (Decimal(t.units) * Decimal(t.unit_price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total += amount
            desc = " · ".join(x for x in (t.book_title or t.package_title, t.title) if x)
            lines.append({"id": _new(), "payout_id": pid, "task_id": t.id, "description": desc[:600], "units": t.units,
                          "unit": t.unit, "unit_price": t.unit_price, "amount": amount})
        conn.execute(sa.insert(PAYOUTS).values(id=pid, tenant_id=tenant, no=no, person_id=person_id, status="taslak",
                                               total=total, note=_text(body.get("note"), 2000), created_by=user, created_at=now))
        conn.execute(sa.insert(PAYOUT_LINES), lines)
        conn.execute(sa.update(TASKS).where(TASKS.c.id.in_([t.id for t in tasks])).values(payout_id=pid))
        _system(conn, tenant, f"k:{person_id}", user, f"Hakediş #{no} hazırlandı: {len(lines)} iş, {_tl(total)}.")
    return {"id": pid, "no": no, "total": float(total), "personName": person.name}


def _tl(v: Decimal | float) -> str:
    s = f"{Decimal(str(v)):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} ₺"


def payout_stmt(tenant: str, payout_id: str):
    return sa.select(PAYOUTS).where(PAYOUTS.c.id == payout_id, PAYOUTS.c.tenant_id == tenant)


def payout_lines_stmt(payout_id: str):
    return sa.select(PAYOUT_LINES).where(PAYOUT_LINES.c.payout_id == payout_id).order_by(PAYOUT_LINES.c.description)


def _payout_row(conn: sa.Connection, tenant: str, payout_id: str) -> Any:
    row = conn.execute(payout_stmt(tenant, payout_id)).first()
    if row is None:
        raise FreelanceError("Hakediş bulunamadı.", 404)
    return row


def payouts_stmt(tenant: str, status: str = "", person_id: str = ""):
    stmt = sa.select(PAYOUTS, PEOPLE.c.name.label("person_name")).join(PEOPLE, PEOPLE.c.id == PAYOUTS.c.person_id).where(
        PAYOUTS.c.tenant_id == tenant)
    if status in PAYOUT_STATES:
        stmt = stmt.where(PAYOUTS.c.status == status)
    else:
        stmt = stmt.where(PAYOUTS.c.status != DELETED)
    if person_id:
        stmt = stmt.where(PAYOUTS.c.person_id == person_id)
    return stmt.order_by(PAYOUTS.c.no.desc())


def list_payouts(engine: sa.engine.Engine, tenant: str, *, status: str = "", person_id: str = "") -> dict[str, Any]:
    with engine.connect() as conn:
        rows = conn.execute(payouts_stmt(tenant, status, person_id)).all()
    items = [_payout_head(r, r.person_name) for r in rows]
    totals = {s: round(sum(i["total"] for i in items if i["status"] == s), 2) for s in PAYOUT_STATES}
    return {"items": items, "totals": totals}


def get_payout(engine: sa.engine.Engine, tenant: str, payout_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        p = _payout_row(conn, tenant, payout_id)
        person = _person_row(conn, tenant, p.person_id)
        lines = conn.execute(payout_lines_stmt(payout_id)).all()
    out = _payout_head(p, person.name)
    out["person"] = {"id": person.id, "name": person.name, "logoCard": person.logo_card, "email": person.email}
    out["lines"] = [{"id": ln.id, "taskId": ln.task_id, "description": ln.description, "units": float(ln.units),
                     "unit": ln.unit, "unitPrice": float(ln.unit_price), "amount": float(ln.amount)} for ln in lines]
    return out


def payout_action(engine: sa.engine.Engine, tenant: str, user: str, payout_id: str, action: str, body: dict[str, Any],
                  can_approve: bool) -> dict[str, Any]:
    """submit (taslak→onay), return (onay→taslak, not şart), approve (onay→onaylandi), pay (onaylandi→odendi),
    delete (yalnız taslak; işler ödenecekler listesine döner). Onay ve ödeme `can_approve` ister; kişi kendi
    hazırladığı hakedişi onaylayamaz (iki göz)."""
    now = _now()
    with engine.begin() as conn:
        p = _payout_row(conn, tenant, payout_id)
        thread = f"k:{p.person_id}"
        if action == "submit":
            if p.status != "taslak":
                raise FreelanceError("Yalnız taslak onaya gönderilir.", 409)
            conn.execute(sa.update(PAYOUTS).where(PAYOUTS.c.id == payout_id).values(status="onay", submitted_by=user,
                                                                                    submitted_at=now, return_note=None))
            _system(conn, tenant, thread, user, f"Hakediş #{p.no} onaya gönderildi.")
        elif action == "return":
            if p.status not in ("onay", "onaylandi"):
                raise FreelanceError("Yalnız onaydaki ya da onaylanmış (ödenmemiş) hakediş geri gönderilir.", 409)
            if not can_approve:
                raise FreelanceError("Hakediş onay yetkiniz yok.", 403)
            note = _text(body.get("note"), 2000)
            if not note:
                raise FreelanceError("Geri gönderme nedeni yazılmalı.")
            conn.execute(sa.update(PAYOUTS).where(PAYOUTS.c.id == payout_id).values(
                status="taslak", return_note=note, approved_by=None, approved_at=None))
            _system(conn, tenant, thread, user, f"Hakediş #{p.no} geri gönderildi: {note}")
        elif action == "approve":
            if p.status != "onay":
                raise FreelanceError("Yalnız onay bekleyen hakediş onaylanır.", 409)
            if not can_approve:
                raise FreelanceError("Hakediş onay yetkiniz yok.", 403)
            if user.lower() in {(p.created_by or "").lower(), (p.submitted_by or "").lower()}:
                raise FreelanceError("Hazırladığınız hakedişi başka biri onaylamalı.", 409)
            conn.execute(sa.update(PAYOUTS).where(PAYOUTS.c.id == payout_id).values(status="onaylandi", approved_by=user,
                                                                                    approved_at=now))
            _system(conn, tenant, thread, user, f"Hakediş #{p.no} onaylandı ({_tl(p.total)}).")
        elif action == "pay":
            if p.status != "onaylandi":
                raise FreelanceError("Yalnız onaylanmış hakediş ödendi işaretlenir.", 409)
            if not can_approve:
                raise FreelanceError("Hakediş onay yetkiniz yok.", 403)
            paid_on = _day(body.get("paidOn"), "Ödeme") or _today()
            if paid_on > _today():
                raise FreelanceError("Ödeme tarihi ileri bir gün olamaz.")
            ref = _text(body.get("paidRef"), 200)
            if not ref:
                raise FreelanceError("Ödemenin Logo belge numarası ya da açıklaması yazılmalı.")
            conn.execute(sa.update(PAYOUTS).where(PAYOUTS.c.id == payout_id).values(
                status="odendi", paid_on=paid_on, paid_ref=ref, paid_by=user, paid_at=now))
            _system(conn, tenant, thread, user, f"Hakediş #{p.no} ödendi: {paid_on.isoformat()} · {ref}.")
        elif action == "delete":
            if p.status != "taslak":
                raise FreelanceError("Yalnız taslak hakediş silinir.", 409)
            # Belge silinmez, «silindi» olur: numarası tekrar verilmez, satırları iz olarak kalır; işler serbest kalır.
            conn.execute(sa.update(TASKS).where(TASKS.c.payout_id == payout_id).values(payout_id=None))
            conn.execute(sa.update(PAYOUTS).where(PAYOUTS.c.id == payout_id).values(status="silindi"))
            _system(conn, tenant, thread, user, f"Hakediş #{p.no} taslağı silindi; işler ödenecekler listesine döndü.")
        else:
            raise FreelanceError("Bilinmeyen işlem.")
    return {"id": payout_id, "no": p.no, "action": action}


def payout_csv(engine: sa.engine.Engine, tenant: str, payout_id: str) -> tuple[str, bytes]:
    p = get_payout(engine, tenant, payout_id)

    def cell(v: Any) -> str:
        s = "" if v is None else (f"{v:.2f}".replace(".", ",") if isinstance(v, float) else str(v))
        return '"' + s.replace('"', '""') + '"' if any(c in s for c in ';"\n') else s

    rows = [["Hakediş", f"#{p['no']}"], ["Kişi", p["personName"]], ["Logo cari kodu", p["person"]["logoCard"] or ""],
            ["Durum", {"taslak": "Taslak", "onay": "Onay bekliyor", "onaylandi": "Onaylandı", "odendi": "Ödendi", DELETED: "Silindi"}[p["status"]]],
            [], ["Açıklama", "Miktar", "Birim", "Birim ücret (₺)", "Tutar (₺)"]]
    rows += [[ln["description"], ln["units"], ln["unit"], ln["unitPrice"], ln["amount"]] for ln in p["lines"]]
    rows += [[], ["Toplam (KDV hariç)", "", "", "", p["total"]]]
    body = "\r\n".join(";".join(cell(c) for c in r) for r in rows) + "\r\n"
    slug = re.sub(r"[^A-Za-z0-9]+", "-", _ascii(p["personName"] or "kisi")).strip("-")[:40] or "kisi"
    return f"hakedis-{p['no']}-{slug}.csv", ("﻿" + body).encode("utf-8")


def _ascii(s: str) -> str:
    return s.translate(str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU"))


# ---------------------------------------------------------------------------------------------- mesajlaşma

def _system(conn: sa.Connection, tenant: str, thread: str, user: str, body: str, task_id: Optional[str] = None) -> None:
    conn.execute(sa.insert(MESSAGES).values(id=_new(), tenant_id=tenant, thread=thread, task_id=task_id, kind="sistem",
                                            author=user, author_display=None, body=body[:4000], created_at=_now()))


def _thread_ok(conn: sa.Connection, tenant: str, thread: str) -> tuple[Optional[Any], Optional[Any]]:
    """(paket, kişi) — paket yazışmasında kişi yok, kişi yazışmasında paket yok."""
    kind, _, key = thread.partition(":")
    if kind == "p":
        return _package_row(conn, tenant, key), None
    if kind == "k":
        return None, _person_row(conn, tenant, key)
    raise FreelanceError("Yazışma bulunamadı.", 404)


def unread_reads_stmt(tenant: str, user: str, threads: Any):
    """Kişinin yazışmaları en son okuduğu an. `threads`: kimlik listesi ya da kimlik veren alt sorgu."""
    return sa.select(READS).where(READS.c.tenant_id == tenant, READS.c.username == user.lower(), READS.c.thread.in_(threads))


def unread_messages_stmt(tenant: str, user: str, threads: Any):
    """Başkasının yazdığı (sistem satırı hariç) iletiler; okunma anından sonrakiler okunmamış sayılır."""
    return sa.select(MESSAGES.c.thread, MESSAGES.c.created_at).where(
        MESSAGES.c.tenant_id == tenant, MESSAGES.c.thread.in_(threads), MESSAGES.c.kind != "sistem",
        sa.func.lower(MESSAGES.c.author) != user.lower())


def all_threads(tenant: str):
    return sa.select(MESSAGES.c.thread).distinct().where(MESSAGES.c.tenant_id == tenant)


def _unread(conn: sa.Connection, tenant: str, user: str, threads: Any) -> dict[str, int]:
    if isinstance(threads, (list, tuple)) and not threads:
        return {}
    reads = {r.thread: r.read_at for r in conn.execute(unread_reads_stmt(tenant, user, threads))}
    rows = conn.execute(unread_messages_stmt(tenant, user, threads)).all()
    out: dict[str, int] = {}
    for th, at in rows:
        seen = reads.get(th)
        at = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        if seen is None or at > (seen if seen.tzinfo else seen.replace(tzinfo=timezone.utc)):
            out[th] = out.get(th, 0) + 1
    return out


def _msg_out(m: Any, user: str) -> dict[str, Any]:
    return {"id": m.id, "thread": m.thread, "taskId": m.task_id, "kind": m.kind, "author": m.author,
            "authorDisplay": m.author_display, "mine": m.author.lower() == user.lower() and m.kind != "sistem",
            "body": m.body, "emailTo": m.email_to, "emailStatus": m.email_status, "createdAt": _iso(m.created_at)}


def thread(engine: sa.engine.Engine, tenant: str, user: str, thread_id: str, *, mark_read: bool = True) -> dict[str, Any]:
    with engine.connect() as conn:
        pkg, person = _thread_ok(conn, tenant, thread_id)
        msgs = conn.execute(sa.select(MESSAGES).where(MESSAGES.c.tenant_id == tenant, MESSAGES.c.thread == thread_id)
                            .order_by(MESSAGES.c.created_at)).all()
        recipients = []
        if pkg is not None:
            recipients = [{"id": r.id, "name": r.name, "email": r.email} for r in conn.execute(
                sa.select(PEOPLE.c.id, PEOPLE.c.name, PEOPLE.c.email).distinct().join(TASKS, TASKS.c.person_id == PEOPLE.c.id)
                .where(TASKS.c.package_id == pkg.id, TASKS.c.status != "iptal"))]
        elif person is not None:
            recipients = [{"id": person.id, "name": person.name, "email": person.email}]
    if mark_read:
        mark(engine, tenant, user, thread_id)
    return {"thread": thread_id, "title": pkg.title if pkg is not None else person.name,
            "kind": "paket" if pkg is not None else "kisi", "recipients": recipients,
            "messages": [_msg_out(m, user) for m in msgs]}


def mark(engine: sa.engine.Engine, tenant: str, user: str, thread_id: str) -> None:
    now = _now()
    with engine.begin() as conn:
        done = conn.execute(sa.update(READS).where(READS.c.tenant_id == tenant, READS.c.username == user.lower(),
                                                   READS.c.thread == thread_id).values(read_at=now)).rowcount
        if not done:
            conn.execute(sa.insert(READS).values(tenant_id=tenant, username=user.lower(), thread=thread_id, read_at=now))


def post_message(engine: sa.engine.Engine, tenant: str, user: str, display: str, thread_id: str, body: dict[str, Any],
                 send_mail: Optional[Callable[[dict[str, Any]], str]] = None) -> dict[str, Any]:
    """kind: ic (ekip içi not), giden (serbest çalışana; e-postayla gider), gelen (serbest çalışanın yanıtı, ekip kaydeder)."""
    kind = body.get("kind") or "ic"
    if kind not in ("ic", "giden", "gelen"):
        raise FreelanceError("İleti türü geçerli değil.")
    text = str(body.get("body") or "").strip()[:8000]
    if not text:
        raise FreelanceError("İleti boş.")
    with engine.connect() as conn:
        pkg, person = _thread_ok(conn, tenant, thread_id)
        to = None
        if kind in ("giden", "gelen"):
            # Kişi yazışmasında karşı taraf hep o kişidir; paket yazışmasında seçilir.
            pid = person.id if person is not None else str(body.get("personId") or "")
            target = _person_row(conn, tenant, pid) if pid else None
            if target is None:
                raise FreelanceError("İletinin kime gittiği/kimden geldiği seçilmeli.")
            if pkg is not None:
                involved = conn.execute(sa.select(TASKS.c.id).where(TASKS.c.package_id == pkg.id, TASKS.c.person_id == target.id)).first()
                if involved is None:
                    raise FreelanceError(f"{target.name} bu pakette görevli değil.", 409)
            to = target
    email_status = None
    if kind == "giden":
        if not to.email:
            email_status = "adres-yok"
        elif send_mail is None:
            email_status = "ayar-yok"
        else:
            email_status = send_mail({"to": to.email, "name": to.name, "subject": pkg.title if pkg is not None else "Timaş Yayınları",
                                      "body": text, "from_user": user, "from_display": display})
    mid = _new()
    with engine.begin() as conn:
        conn.execute(sa.insert(MESSAGES).values(
            id=mid, tenant_id=tenant, thread=thread_id, task_id=_text(body.get("taskId"), 32), kind=kind, author=user,
            author_display=(to.name if kind == "gelen" and to is not None else display) or user, body=text,
            email_to=to.email if (kind == "giden" and to is not None) else None, email_status=email_status, created_at=_now()))
    mark(engine, tenant, user, thread_id)
    return {"id": mid, "emailStatus": email_status}


def inbox_stmt(tenant: str):
    """Yazışma başına son ileti ve ileti sayısı."""
    last = (sa.select(MESSAGES.c.thread, sa.func.max(MESSAGES.c.created_at).label("at"), sa.func.count().label("n"))
            .where(MESSAGES.c.tenant_id == tenant).group_by(MESSAGES.c.thread).subquery())
    return (sa.select(MESSAGES, last.c.n, last.c.at)
            .join(last, sa.and_(MESSAGES.c.thread == last.c.thread, MESSAGES.c.created_at == last.c.at))
            .where(MESSAGES.c.tenant_id == tenant))


def inbox(engine: sa.engine.Engine, tenant: str, user: str) -> dict[str, Any]:
    """Yazışması olan paketler ve kişiler, son iletiye göre. Sistem satırı da son hareket sayılır."""
    with engine.connect() as conn:
        rows = conn.execute(inbox_stmt(tenant)).all()
        latest: dict[str, Any] = {}
        for m in rows:
            latest.setdefault(m.thread, m)          # aynı anda iki ileti: biri yeter
        # Son iletisi olan yazışmalar = kiracının bütün yazışmaları (alt sorgu: çalışan ifade budur).
        unread = _unread(conn, tenant, user, all_threads(tenant)) if latest else {}
        pkgs = {r.id: r for r in conn.execute(sa.select(PACKAGES.c.id, PACKAGES.c.title, PACKAGES.c.book_title, PACKAGES.c.status)
                                              .where(PACKAGES.c.tenant_id == tenant))}
        people = {r.id: r for r in conn.execute(sa.select(PEOPLE.c.id, PEOPLE.c.name).where(PEOPLE.c.tenant_id == tenant))}
    items = []
    for th, m in latest.items():
        kind, _, key = th.partition(":")
        if kind == "p" and key in pkgs:
            title, sub = pkgs[key].title, pkgs[key].book_title
        elif kind == "k" and key in people:
            title, sub = people[key].name, "Kişiyle genel yazışma"
        else:
            continue
        items.append({"thread": th, "kind": "paket" if kind == "p" else "kisi", "title": title, "subtitle": sub,
                      "count": m.n, "unread": unread.get(th, 0), "at": _iso(m.at),
                      "last": {"kind": m.kind, "body": m.body[:160], "author": m.author_display or m.author}})
    items.sort(key=lambda x: x["at"] or "", reverse=True)
    return {"items": items, "unread": sum(unread.values())}


# ---------------------------------------------------------------------------------------------- özet

def ov_people_stmt(tenant: str):
    return sa.select(PEOPLE.c.status, sa.func.count()).where(PEOPLE.c.tenant_id == tenant).group_by(PEOPLE.c.status)


def ov_tasks_stmt(tenant: str):
    """Özet sayıları ve ödenecek tutarın görevleri: iptal edilmemiş paketlerdeki bütün görevler."""
    return (sa.select(TASKS.c.status, TASKS.c.due, TASKS.c.payout_id, TASKS.c.units, TASKS.c.unit_price)
            .join(PACKAGES, PACKAGES.c.id == TASKS.c.package_id)
            .where(TASKS.c.tenant_id == tenant, PACKAGES.c.status != "iptal"))


def ov_payouts_stmt(tenant: str):
    return (sa.select(PAYOUTS.c.status, sa.func.count(), sa.func.coalesce(sa.func.sum(PAYOUTS.c.total), 0))
            .where(PAYOUTS.c.tenant_id == tenant, PAYOUTS.c.status != DELETED).group_by(PAYOUTS.c.status))


def overview(engine: sa.engine.Engine, tenant: str, user: str) -> dict[str, Any]:
    today = _today()
    with engine.connect() as conn:
        people = conn.execute(ov_people_stmt(tenant)).all()
        tasks = conn.execute(ov_tasks_stmt(tenant)).all()
        pays = conn.execute(ov_payouts_stmt(tenant)).all()
        unread = sum(_unread(conn, tenant, user, all_threads(tenant)).values())
    pc = dict(people)
    payable_total = sum((Decimal(t.units) * Decimal(t.unit_price) for t in tasks if t.status == "onaylandi" and t.payout_id is None),
                        Decimal("0"))
    return {
        "people": {"active": pc.get("aktif", 0), "passive": pc.get("pasif", 0)},
        "tasks": {"unassigned": sum(1 for t in tasks if t.status == "atanmadi"),
                  "active": sum(1 for t in tasks if t.status in ACTIVE),
                  "late": sum(1 for t in tasks if t.status in ACTIVE and t.due and t.due < today),
                  "review": sum(1 for t in tasks if t.status == "teslim")},
        "payable": float(payable_total),
        "payouts": {s: {"count": n, "total": float(v)} for s, n, v in pays},
        "unread": unread,
        "roles": [{"key": k, "label": v[0], "unit": v[1], "hoursPerUnit": v[2]} for k, v in ROLES.items()],
        "units": list(UNITS),
    }
