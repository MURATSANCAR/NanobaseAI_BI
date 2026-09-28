"""İK-0: dört İK modülünün (M55 işe alım, M56 performans, M57 eğitim, M58 bağlılık) ortak temeli.

Analiz: docs/analiz/kullanici-ihtiyaclari/M55-ise-alim-yetkinlik.md §14.1.

- **Çalışan ve birim kaydı** (`semantic_hr_employees`, `semantic_hr_units`): CRM ∩ AD'den öneri gelir
  (`hr_sources.sync_preview`), İK onaylayınca yazılır; CRM'e hiçbir şey yazılmaz. T.C. kimlik no, adres, ücret, sağlık
  tutulmaz. Bilgisayar kullanmayan çalışan elle eklenir (hesap adı boş).
- **KVKK kayıtları:** aydınlatma metni sürümleri (`semantic_hr_notices`), açık rıza (`semantic_hr_consents`; yalnız
  aday havuzu, referans görüşmesi ve gereksiz özel nitelikli veri için — başvurunun değerlendirilmesi md. 5/2-c'ye
  dayanır, rıza istenmez), veri sınıfı başına saklama süresi (`semantic_hr_retention`), erişim kaydı
  (`semantic_hr_access_log`) ve imha tutanağı (`semantic_hr_purge_runs`).
- **Gece imha işi** (`run_due_purge`): her İK modülü kendi veri sınıfını `register_purger` ile bağlar; iş süresi dolanı
  siler, sınıf başına tutanak yazar. Rıza geri çekilince modülün `register_withdraw_hook` kancası çağrılır.
- **Yetki:** İK sayfa ve özellikleri `access_catalog.json`'da `explicit` (Herkes rolüne ve «Bütün sayfalar»a girmez);
  kişisel veri anahtarları `sensitive`. `Who` bu anahtarları yöneticiye kendiliğinden vermez — yönetici kendine
  Yetkiler ekranından rol bağlar (`semantic_audit`'e düşer). `HR_ADMIN_SEES_PERSONAL=1` eski kurala döner.
- **Model izi:** İK çağrıları `hr_llm()` ile LLM kapısından gider; sıra kaydına (`sl_llm_queue.question`) mesaj
  yerine yalnız etiket yazılır (`QueuedLlm.labelled`). `/api/v1/llm/jobs` İK için kullanılmaz (mesajı süresiz saklar).

M56–M58 bu modülün tablolarını ve işlevlerini kullanır; kendi tablolarını `semantic_hr_<modul>_*` önekiyle açar.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic_bridge.hr")

_md = sa.MetaData()


def _ts(name: str, **kw: Any) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


UNITS = sa.Table(
    "semantic_hr_units", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("parent_id", sa.String(40)),
    sa.Column("manager_employee_id", sa.String(40)),
    sa.Column("crm_businessunit_id", sa.String(40), index=True),
    sa.Column("ad_ou", sa.String(400)),
    sa.Column("active", sa.Boolean, nullable=False, default=True),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
)

EMPLOYEES = sa.Table(
    "semantic_hr_employees", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("username", sa.String(120), index=True),          # AD sAMAccountName (küçük harf); bilgisayarsızda boş
    sa.Column("ad_guid", sa.String(40)),
    sa.Column("crm_systemuser_id", sa.String(40), index=True),
    sa.Column("display_name", sa.String(200), nullable=False),
    sa.Column("unit_id", sa.String(40), index=True),
    sa.Column("manager_id", sa.String(40)),
    sa.Column("title", sa.String(200)),
    sa.Column("start_date", sa.Date),
    sa.Column("end_date", sa.Date),
    sa.Column("status", sa.String(16), nullable=False, default="aktif"),   # aktif | ayrildi
    sa.Column("source_json", sa.Text),                           # alan → kaynak (crm / ad / ik)
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
)

NOTICES = sa.Table(
    "semantic_hr_notices", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("audience", sa.String(16), nullable=False),        # aday | calisan
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("body", sa.Text, nullable=False),
    _ts("published_at", nullable=False),
    sa.Column("published_by", sa.String(120)),
    sa.UniqueConstraint("tenant_id", "audience", "version", name="uq_hr_notice_version"),
)

CONSENTS = sa.Table(
    "semantic_hr_consents", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("subject_type", sa.String(16), nullable=False),    # aday | calisan
    sa.Column("subject_id", sa.String(40), nullable=False, index=True),
    sa.Column("purpose", sa.String(40), nullable=False),
    sa.Column("notice_version", sa.Integer),
    _ts("given_at", nullable=False),
    sa.Column("channel", sa.String(40)),                         # eposta | form | kagit | sozlu
    sa.Column("evidence", sa.Text),                              # kanıtın yeri/özeti (ör. «12.03 e-postası, İK klasörü»)
    sa.Column("recorded_by", sa.String(120)),
    _ts("withdrawn_at"),
    sa.Column("withdrawn_by", sa.String(120)),
)

RETENTION = sa.Table(
    "semantic_hr_retention", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("data_class", sa.String(40), primary_key=True),
    sa.Column("keep_days", sa.Integer),                          # None: süre girilmedi → imha yok, ekranda uyarı
    sa.Column("legal_basis", sa.Text),
    sa.Column("approved_by", sa.String(120)),
    _ts("approved_at"),
)

ACCESS_LOG = sa.Table(
    "semantic_hr_access_log", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    _ts("at", nullable=False),
    sa.Column("username", sa.String(120), nullable=False),
    sa.Column("subject_type", sa.String(16), nullable=False),
    sa.Column("subject_id", sa.String(40), nullable=False, index=True),
    sa.Column("action", sa.String(16), nullable=False),          # goruntule | indir | disa_aktar | sil
    sa.Column("purpose", sa.String(200)),
)

PURGE_RUNS = sa.Table(
    "semantic_hr_purge_runs", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    _ts("at", nullable=False),
    sa.Column("data_class", sa.String(40), nullable=False),
    sa.Column("purged_count", sa.Integer, nullable=False, default=0),
    sa.Column("detail_json", sa.Text),                           # yalnız kayıt kimlikleri; ad/e-posta yok
    sa.Column("error", sa.Text),
    sa.Column("actor", sa.String(120)),                          # sistem (gece işi) ya da talebi işleyen kişi
)

JOBS = sa.Table(
    "semantic_hr_jobs", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("owner", sa.String(120), nullable=False),
    sa.Column("kind", sa.String(40), nullable=False),
    sa.Column("subject_id", sa.String(40), index=True),
    sa.Column("state", sa.String(16), nullable=False),           # calisiyor | bitti | hata
    sa.Column("progress", sa.Integer, nullable=False, default=0),
    sa.Column("total", sa.Integer, nullable=False, default=0),
    sa.Column("result_json", sa.Text),                           # özet; kişisel veri yazılmaz
    sa.Column("error", sa.Text),
    _ts("started_at", nullable=False),
    _ts("finished_at"),
)

#: Kurulmuş veritabanları. Kimlik (id) değil zayıf başvuru: çöpe giden motorun kimliği yenisine verilirse tablo kurulmadan kalmasın.
_ready: "weakref.WeakSet[sa.engine.Engine]" = weakref.WeakSet()
_lock = threading.Lock()

EMPLOYEE_STATUS = {"aktif": "Aktif", "ayrildi": "Ayrıldı"}
AUDIENCES = {"aday": "Adaylar", "calisan": "Çalışanlar"}
SUBJECT_TYPES = {"aday": "Aday", "calisan": "Çalışan"}
CHANNELS = {"eposta": "E-posta", "form": "Başvuru formu", "kagit": "Islak imzalı form", "sozlu": "Sözlü (kayıtlı görüşme)"}

#: Açık rızanın alınabileceği amaçlar. Başvurunun değerlendirilmesi burada YOK (md. 5/2-c, rıza istenmez).
#: Modüller kendi amacını `register_purpose` ile ekler.
PURPOSES: dict[str, dict[str, str]] = {
    "aday_havuzu": {"label": "Aday havuzu", "hint": "Özgeçmişin ileride açılacak pozisyonlar için saklanması",
                    "subject": "aday"},
    "referans": {"label": "Referans görüşmesi", "hint": "Adayın bildirdiği referans kişilerle görüşülmesi", "subject": "aday"},
    "ozel_nitelikli": {"label": "Özel nitelikli veri", "hint": "Adayın kendiliğinden paylaştığı gerekli olmayan özel nitelikli verinin işlenmesi (tercihen işlenmez, maskelenir)",
                       "subject": "aday"},
}

#: Saklama süresi verilen veri sınıfları. Modüller kendi sınıfını `register_data_class` ile ekler.
DATA_CLASSES: dict[str, dict[str, str]] = {
    "aday_ret": {"label": "İşe alınmayan aday", "hint": "Sonuçlanmış (ret / aday çekildi) ve havuz rızası olmayan adayın bütün verisi; süre sonuç tarihinden sayılır"},
    "aday_havuz": {"label": "Havuz rızalı aday", "hint": "Havuz rızası süren adayın verisi; süre sonuç tarihinden sayılır, rıza geri çekilince hemen imha kuyruğuna girer"},
    "mulakat_notu": {"label": "Mülakat notu", "hint": "Görüşmecilerin notları; aday kaydıyla birlikte ya da bu süre dolunca (hangisi önceyse) silinir"},
}


class HrError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if engine in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(engine)


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(v: Any) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    if isinstance(v, date) and not isinstance(v, datetime):
        v = datetime(v.year, v.month, v.day)
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v.isoformat()
    return aware(v).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def load(v: Optional[str], default: Any = None) -> Any:
    if not v:
        return default
    try:
        return json.loads(v)
    except ValueError:
        return default


def clean(v: Any, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def parse_date(v: Any, what: str) -> Optional[date]:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise HrError(f"{what} tarihi geçersiz (YYYY-AA-GG).") from None


_subject_checks: dict[str, Callable[[sa.engine.Engine, str, str], bool]] = {}


def register_subject_check(subject_type: str, fn: Callable[[sa.engine.Engine, str, str], bool]) -> None:
    """Rıza/erişim kaydının ait olduğu kaydın varlığını denetleyen işlev (aday: M55)."""
    _subject_checks[subject_type] = fn


def subject_exists(engine: sa.engine.Engine, tenant: str, subject_type: str, subject_id: str) -> bool:
    if subject_type == "calisan":
        with engine.connect() as c:
            return c.execute(sa.select(EMPLOYEES.c.id).where(EMPLOYEES.c.id == subject_id, EMPLOYEES.c.tenant_id == tenant)).first() is not None
    fn = _subject_checks.get(subject_type)
    return bool(fn and fn(engine, tenant, subject_id))


def register_purpose(key: str, label: str, hint: str, subject: str) -> None:
    PURPOSES[key] = {"label": label, "hint": hint, "subject": subject}


def register_data_class(key: str, label: str, hint: str) -> None:
    DATA_CLASSES[key] = {"label": label, "hint": hint}


# ------------------------------------------------------------------ ayarlar


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    """Ayarlar ekran > env (admin.conf). Varsayılan yok: eşik girilmediyse ekran «ayarlanmadı» der."""
    def num(key: str) -> Optional[int]:
        raw = (conf(key) or "").strip()
        try:
            n = int(raw)
        except ValueError:
            return None
        return n if n > 0 else None

    return {
        "adminSeesPersonal": (conf("HR_ADMIN_SEES_PERSONAL") or "").strip() in ("1", "true", "evet"),
        "slaDays": num("HR_RECRUIT_SLA_DAYS"),
        "fileMaxMb": num("HR_FILE_MAX_MB") or 20,
        "alertRecipients": [x.strip() for x in (conf("HR_ALERT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x],
        "company": (conf("HR_COMPANY_NAME") or "Timaş Yayınları").strip(),
    }


# ------------------------------------------------------------------ yetki


@dataclass
class Who:
    """İsteği yapan kişi ve İK anahtarları. `can` duyarlı anahtarı yöneticiye ancak rolüyle verir."""

    user: str
    display: str
    admin: bool
    keys: frozenset[str] = field(default_factory=frozenset)

    def can(self, *keys: str) -> bool:
        return any(k in self.keys for k in keys)


def who_from(access_obj: Any, display: str, sensitive: frozenset[str], admin_sees_personal: bool) -> Who:
    """`access.Access` → `Who`. Yöneticinin «her şey» yetkisinden, rolünde açıkça olmayan duyarlı anahtarlar düşer."""
    granted = frozenset(access_obj.granted())
    if access_obj.admin and not admin_sees_personal:
        granted = granted - (sensitive - frozenset(access_obj.perms))
    return Who(user=access_obj.user, display=display or access_obj.user, admin=bool(access_obj.admin), keys=granted)


# ------------------------------------------------------------------ model (LLM kapısı)


def hr_llm(rt: Any, label: str, priority: Optional[int] = None) -> Any:
    """İK'nın model çağrısı: LLM kapısından, sıra kaydına mesaj yerine yalnız `ik: <etiket>` yazılır.
    Model tanımlı değilse None. `LlmClient` doğrudan kurulmaz; `/api/v1/llm/jobs` kullanılmaz."""
    try:
        m = rt.llm_for("ik", priority)
    except Exception:  # noqa: BLE001 — model tanımlı değil
        return None
    if m is None:
        return None
    labelled = getattr(m, "labelled", None)
    return labelled(f"ik: {label}") if callable(labelled) else m


# ------------------------------------------------------------------ birimler


def _unit_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "parentId": r.parent_id, "managerEmployeeId": r.manager_employee_id,
            "crmBusinessUnitId": r.crm_businessunit_id, "adOu": r.ad_ou, "active": bool(r.active),
            "updatedBy": r.updated_by, "updatedAt": iso(r.updated_at)}


def list_units(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(UNITS).where(UNITS.c.tenant_id == tenant).order_by(UNITS.c.name)).all()
        counts = dict(c.execute(sa.select(EMPLOYEES.c.unit_id, sa.func.count()).where(
            EMPLOYEES.c.tenant_id == tenant, EMPLOYEES.c.status == "aktif").group_by(EMPLOYEES.c.unit_id)).all())
    return [{**_unit_out(r), "employees": int(counts.get(r.id, 0))} for r in rows]


def save_unit(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any],
              unit_id: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Birim ekler (unit_id None) ya da düzeltir. Dönen: (birim, değişen alanlar)."""
    ensure(engine)
    with engine.begin() as c:
        before = None
        if unit_id:
            before = c.execute(sa.select(UNITS).where(UNITS.c.id == unit_id, UNITS.c.tenant_id == tenant)).first()
            if before is None:
                raise HrError("Birim bulunamadı.", 404)
        vals: dict[str, Any] = {}
        if "name" in body or before is None:
            name = clean(body.get("name"), 200)
            if not name:
                raise HrError("Birimin adı boş olamaz.")
            vals["name"] = name
        if "parentId" in body:
            pid = body.get("parentId") or None
            if pid and (pid == unit_id or not c.execute(sa.select(UNITS.c.id).where(UNITS.c.id == pid, UNITS.c.tenant_id == tenant)).first()):
                raise HrError("Üst birim geçersiz.")
            if pid and unit_id and _is_descendant(c, tenant, pid, unit_id):
                raise HrError("Birim kendi alt biriminin altına taşınamaz.")
            vals["parent_id"] = pid
        if "managerEmployeeId" in body:
            mid = body.get("managerEmployeeId") or None
            if mid and not c.execute(sa.select(EMPLOYEES.c.id).where(EMPLOYEES.c.id == mid, EMPLOYEES.c.tenant_id == tenant)).first():
                raise HrError("Birim yöneticisi çalışan kaydında yok.")
            vals["manager_employee_id"] = mid
        if "active" in body:
            vals["active"] = bool(body.get("active"))
        if "adOu" in body:
            vals["ad_ou"] = clean(body.get("adOu"), 400) or None
        vals.update(updated_by=actor, updated_at=now())
        if before is None:
            uid = new_id("brm")
            c.execute(UNITS.insert().values(id=uid, tenant_id=tenant, active=vals.pop("active", True), **vals))
            diff = {"yeni": vals.get("name")}
        else:
            uid = unit_id
            diff = {k: {"once": getattr(before, k), "sonra": v} for k, v in vals.items()
                    if k not in ("updated_by", "updated_at") and getattr(before, k) != v}
            c.execute(UNITS.update().where(UNITS.c.id == uid).values(**vals))
        row = c.execute(sa.select(UNITS).where(UNITS.c.id == uid)).first()
    return _unit_out(row), diff


def _is_descendant(c: Any, tenant: str, candidate: str, root: str) -> bool:
    parents = dict(c.execute(sa.select(UNITS.c.id, UNITS.c.parent_id).where(UNITS.c.tenant_id == tenant)).all())
    seen: set[str] = set()
    cur: Optional[str] = candidate
    while cur and cur not in seen:
        if cur == root:
            return True
        seen.add(cur)
        cur = parents.get(cur)
    return False


# ------------------------------------------------------------------ çalışanlar


def _emp_out(r: Any, units: Optional[dict[str, str]] = None) -> dict[str, Any]:
    return {"id": r.id, "username": r.username or None, "adGuid": r.ad_guid, "crmSystemUserId": r.crm_systemuser_id,
            "displayName": r.display_name, "unitId": r.unit_id, "unitName": (units or {}).get(r.unit_id or ""),
            "managerId": r.manager_id, "title": r.title or "", "startDate": iso(r.start_date), "endDate": iso(r.end_date),
            "status": r.status, "statusLabel": EMPLOYEE_STATUS.get(r.status, r.status), "source": load(r.source_json, {}),
            "updatedBy": r.updated_by, "updatedAt": iso(r.updated_at)}


def list_employees(engine: sa.engine.Engine, tenant: str, *, status: str = "aktif", q: str = "",
                   unit_id: str = "") -> list[dict[str, Any]]:
    """Bütün eşleşen çalışanlar (sayı tavanı yok)."""
    ensure(engine)
    stmt = sa.select(EMPLOYEES).where(EMPLOYEES.c.tenant_id == tenant)
    if status in EMPLOYEE_STATUS:
        stmt = stmt.where(EMPLOYEES.c.status == status)
    if unit_id:
        stmt = stmt.where(EMPLOYEES.c.unit_id == unit_id)
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(EMPLOYEES.c.display_name)).all()
        units = dict(c.execute(sa.select(UNITS.c.id, UNITS.c.name).where(UNITS.c.tenant_id == tenant)).all())
    out = [_emp_out(r, units) for r in rows]
    needle = (q or "").strip().casefold()
    if needle:
        out = [e for e in out if needle in f"{e['displayName']} {e['username'] or ''} {e['title']} {e['unitName'] or ''}".casefold()]
    return out


def get_employee(engine: sa.engine.Engine, tenant: str, eid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(EMPLOYEES).where(EMPLOYEES.c.id == eid, EMPLOYEES.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Çalışan kaydı bulunamadı.", 404)
        units = dict(c.execute(sa.select(UNITS.c.id, UNITS.c.name).where(UNITS.c.tenant_id == tenant)).all())
    return _emp_out(r, units)


def employee_by_username(engine: sa.engine.Engine, tenant: str, username: str) -> Optional[dict[str, Any]]:
    u = (username or "").strip().lower()
    if not u:
        return None
    with engine.connect() as c:
        r = c.execute(sa.select(EMPLOYEES).where(EMPLOYEES.c.tenant_id == tenant, EMPLOYEES.c.username == u)
                      .order_by(EMPLOYEES.c.status)).first()
        units = dict(c.execute(sa.select(UNITS.c.id, UNITS.c.name).where(UNITS.c.tenant_id == tenant)).all())
    return _emp_out(r, units) if r else None


#: Elle düzeltilebilen alanlar (API adı → kolon).
_EMP_FIELDS = {"displayName": "display_name", "unitId": "unit_id", "managerId": "manager_id", "title": "title",
               "startDate": "start_date", "endDate": "end_date", "status": "status", "username": "username"}


def save_employee(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any],
                  eid: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Çalışan ekler (bilgisayarsız çalışan, işe alınan aday) ya da düzeltir. Elle yazılan alan kaynağı «ik» olur."""
    ensure(engine)
    with engine.begin() as c:
        before = None
        if eid:
            before = c.execute(sa.select(EMPLOYEES).where(EMPLOYEES.c.id == eid, EMPLOYEES.c.tenant_id == tenant)).first()
            if before is None:
                raise HrError("Çalışan kaydı bulunamadı.", 404)
        vals: dict[str, Any] = {}
        for api, col in _EMP_FIELDS.items():
            if api not in body:
                continue
            v = body.get(api)
            if col == "display_name":
                v = clean(v, 200)
                if not v:
                    raise HrError("Çalışanın adı boş olamaz.")
            elif col == "title":
                v = clean(v, 200) or None
            elif col == "username":
                v = clean(v, 120).lower() or None
                if v and c.execute(sa.select(EMPLOYEES.c.id).where(EMPLOYEES.c.tenant_id == tenant, EMPLOYEES.c.username == v,
                                                                    EMPLOYEES.c.id != (eid or ""))).first():
                    raise HrError(f"«{v}» hesabı başka bir çalışan kaydında.")
            elif col in ("start_date", "end_date"):
                v = parse_date(v, "İşe giriş" if col == "start_date" else "Ayrılış")
            elif col == "status":
                if v not in EMPLOYEE_STATUS:
                    raise HrError("Durum «aktif» ya da «ayrildi» olmalı.")
            elif col == "unit_id":
                v = v or None
                if v and not c.execute(sa.select(UNITS.c.id).where(UNITS.c.id == v, UNITS.c.tenant_id == tenant)).first():
                    raise HrError("Birim bulunamadı.")
            elif col == "manager_id":
                v = v or None
                if v and (v == eid or not c.execute(sa.select(EMPLOYEES.c.id).where(EMPLOYEES.c.id == v, EMPLOYEES.c.tenant_id == tenant)).first()):
                    raise HrError("Yönetici geçersiz.")
            vals[col] = v
        if before is None and not vals.get("display_name"):
            raise HrError("Çalışanın adı boş olamaz.")
        source = load(before.source_json, {}) if before is not None else {}
        for col in vals:
            source[col] = "ik"
        vals.update(source_json=dump(source), updated_by=actor, updated_at=now())
        if before is None:
            eid = new_id("clsn")
            vals.setdefault("status", "aktif")
            c.execute(EMPLOYEES.insert().values(id=eid, tenant_id=tenant, **vals))
            diff = {"yeni": vals.get("display_name")}
        else:
            diff = {k: {"once": iso(getattr(before, k)) if k.endswith("_date") else getattr(before, k),
                        "sonra": iso(v) if k.endswith("_date") else v}
                    for k, v in vals.items() if k not in ("updated_by", "updated_at", "source_json") and getattr(before, k) != v}
            c.execute(EMPLOYEES.update().where(EMPLOYEES.c.id == eid).values(**vals))
    return get_employee(engine, tenant, eid), diff


def apply_sync(engine: sa.engine.Engine, tenant: str, actor: str, preview: dict[str, Any],
               kinds: Iterable[str]) -> dict[str, int]:
    """`hr_sources.sync_preview` önerisini İK onayıyla yazar. `kinds`: units, new, changed, departed.
    Elle düzeltilmiş alan (kaynağı «ik») eşitlemeyle ezilmez."""
    ensure(engine)
    kinds = set(kinds)
    done = {"units": 0, "new": 0, "changed": 0, "departed": 0, "managers": 0}
    t = now()
    with engine.begin() as c:
        by_crm_unit = {r.crm_businessunit_id: r.id for r in c.execute(
            sa.select(UNITS.c.id, UNITS.c.crm_businessunit_id).where(UNITS.c.tenant_id == tenant, UNITS.c.crm_businessunit_id.isnot(None))).all()}
        if "units" in kinds:
            for u in preview.get("units") or []:
                uid = by_crm_unit.get(u["crmBusinessUnitId"])
                if uid is None:
                    uid = new_id("brm")
                    c.execute(UNITS.insert().values(id=uid, tenant_id=tenant, name=u["name"], crm_businessunit_id=u["crmBusinessUnitId"],
                                                    active=True, updated_by=actor, updated_at=t))
                    by_crm_unit[u["crmBusinessUnitId"]] = uid
                    done["units"] += 1
                elif u.get("action") == "degisti":
                    c.execute(UNITS.update().where(UNITS.c.id == uid).values(name=u["name"], updated_by=actor, updated_at=t))
                    done["units"] += 1
            for u in preview.get("units") or []:
                parent = by_crm_unit.get(u.get("crmParentId") or "")
                c.execute(UNITS.update().where(UNITS.c.id == by_crm_unit[u["crmBusinessUnitId"]]).values(parent_id=parent))
        existing = {r.crm_systemuser_id: r for r in c.execute(
            sa.select(EMPLOYEES).where(EMPLOYEES.c.tenant_id == tenant, EMPLOYEES.c.crm_systemuser_id.isnot(None))).all()}
        for p in preview.get("employees") or []:
            act = p.get("action")
            if act not in ("yeni", "degisti") or ({"yeni": "new", "degisti": "changed"}[act] not in kinds):
                continue
            unit = by_crm_unit.get(p.get("crmBusinessUnitId") or "")
            vals = {"username": p.get("username") or None, "ad_guid": p.get("adGuid") or None,
                    "display_name": p["displayName"], "unit_id": unit}
            row = existing.get(p["crmSystemUserId"])
            if row is None:
                src = {k: p.get("source", {}).get(k, "crm") for k in vals}
                c.execute(EMPLOYEES.insert().values(id=new_id("clsn"), tenant_id=tenant, crm_systemuser_id=p["crmSystemUserId"],
                                                    status="aktif", source_json=dump(src), updated_by=actor, updated_at=t, **vals))
                done["new"] += 1
            else:
                src = load(row.source_json, {})
                upd = {k: v for k, v in vals.items() if src.get(k) != "ik" and getattr(row, k) != v}
                if row.status != "aktif" and src.get("status") != "ik":
                    upd["status"], upd["end_date"] = "aktif", None
                if upd:
                    for k in upd:
                        src.setdefault(k, "crm")
                    c.execute(EMPLOYEES.update().where(EMPLOYEES.c.id == row.id).values(**upd, source_json=dump(src),
                                                                                        updated_by=actor, updated_at=t))
                    done["changed"] += 1
        if "departed" in kinds:
            for p in preview.get("departed") or []:
                c.execute(EMPLOYEES.update().where(EMPLOYEES.c.id == p["id"], EMPLOYEES.c.tenant_id == tenant,
                                                   EMPLOYEES.c.status == "aktif")
                          .values(status="ayrildi", end_date=t.date(), updated_by=actor, updated_at=t))
                done["departed"] += 1
        if "units" in kinds:
            # Birim yöneticisi CRM kullanıcısı olarak gelir; çalışan kaydı varsa bağlanır.
            emp_by_crm = dict(c.execute(sa.select(EMPLOYEES.c.crm_systemuser_id, EMPLOYEES.c.id).where(
                EMPLOYEES.c.tenant_id == tenant, EMPLOYEES.c.crm_systemuser_id.isnot(None))).all())
            for u in preview.get("units") or []:
                mid = emp_by_crm.get(u.get("crmManagerId") or "")
                if mid:
                    c.execute(UNITS.update().where(UNITS.c.id == by_crm_unit[u["crmBusinessUnitId"]]).values(manager_employee_id=mid))
                    done["managers"] += 1
    return done


# ------------------------------------------------------------------ aydınlatma metinleri


def _notice_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "audience": r.audience, "version": r.version, "title": r.title, "body": r.body,
            "publishedAt": iso(r.published_at), "publishedBy": r.published_by}


def list_notices(engine: sa.engine.Engine, tenant: str, audience: str = "") -> list[dict[str, Any]]:
    ensure(engine)
    stmt = sa.select(NOTICES).where(NOTICES.c.tenant_id == tenant)
    if audience:
        stmt = stmt.where(NOTICES.c.audience == audience)
    with engine.connect() as c:
        return [_notice_out(r) for r in c.execute(stmt.order_by(NOTICES.c.audience, NOTICES.c.version.desc())).all()]


def current_notice(engine: sa.engine.Engine, tenant: str, audience: str) -> Optional[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(NOTICES).where(NOTICES.c.tenant_id == tenant, NOTICES.c.audience == audience)
                      .order_by(NOTICES.c.version.desc()).limit(1)).first()
    return _notice_out(r) if r else None


def publish_notice(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any]) -> dict[str, Any]:
    """Yeni sürüm yayımlar; eski sürümler silinmez (rıza kaydı hangi sürümü gördüğünü taşır)."""
    ensure(engine)
    audience = str(body.get("audience") or "")
    if audience not in AUDIENCES:
        raise HrError("Aydınlatma metninin kitlesi «aday» ya da «calisan» olmalı.")
    title = clean(body.get("title"), 300)
    text = str(body.get("body") or "").strip()
    if not title or not text:
        raise HrError("Başlık ve metin boş olamaz.")
    with engine.begin() as c:
        last = c.execute(sa.select(sa.func.max(NOTICES.c.version)).where(NOTICES.c.tenant_id == tenant,
                                                                         NOTICES.c.audience == audience)).scalar() or 0
        nid = new_id("aydn")
        c.execute(NOTICES.insert().values(id=nid, tenant_id=tenant, audience=audience, version=int(last) + 1, title=title,
                                          body=text, published_at=now(), published_by=actor))
        return _notice_out(c.execute(sa.select(NOTICES).where(NOTICES.c.id == nid)).first())


# ------------------------------------------------------------------ açık rıza

_withdraw_hooks: list[Callable[[sa.engine.Engine, str, str, str, str], None]] = []


_added_hooks: list[Callable[[sa.engine.Engine, str, str, str, str], None]] = []
_retention_hooks: list[Callable[[sa.engine.Engine, str], None]] = []


def register_withdraw_hook(fn: Callable[[sa.engine.Engine, str, str, str, str], None]) -> None:
    """Rıza geri çekilince çağrılır: fn(engine, tenant, subject_type, subject_id, purpose)."""
    if fn not in _withdraw_hooks:
        _withdraw_hooks.append(fn)


def register_consent_added_hook(fn: Callable[[sa.engine.Engine, str, str, str, str], None]) -> None:
    """Rıza kaydedilince çağrılır (ör. havuz rızası adayın saklama sınıfını değiştirir)."""
    if fn not in _added_hooks:
        _added_hooks.append(fn)


def register_retention_hook(fn: Callable[[sa.engine.Engine, str], None]) -> None:
    """Saklama süresi değişince çağrılır: modül kendi kayıtlarının bitiş tarihini yeniden hesaplar."""
    if fn not in _retention_hooks:
        _retention_hooks.append(fn)


def _run_hooks(hooks: list[Callable[..., None]], *args: Any) -> None:
    for hook in list(hooks):
        try:
            hook(*args)
        except Exception as e:  # noqa: BLE001 — kayıt durur; kanca hatası loga
            log.warning("hr: kanca hata verdi: %s", e)


def _consent_out(r: Any) -> dict[str, Any]:
    p = PURPOSES.get(r.purpose, {})
    return {"id": r.id, "subjectType": r.subject_type, "subjectId": r.subject_id, "purpose": r.purpose,
            "purposeLabel": p.get("label", r.purpose), "noticeVersion": r.notice_version, "givenAt": iso(r.given_at),
            "channel": r.channel, "channelLabel": CHANNELS.get(r.channel or "", r.channel), "evidence": r.evidence or "",
            "recordedBy": r.recorded_by, "withdrawnAt": iso(r.withdrawn_at), "withdrawnBy": r.withdrawn_by,
            "active": r.withdrawn_at is None}


def list_consents(engine: sa.engine.Engine, tenant: str, subject_type: str = "", subject_id: str = "") -> list[dict[str, Any]]:
    ensure(engine)
    stmt = sa.select(CONSENTS).where(CONSENTS.c.tenant_id == tenant)
    if subject_type:
        stmt = stmt.where(CONSENTS.c.subject_type == subject_type)
    if subject_id:
        stmt = stmt.where(CONSENTS.c.subject_id == subject_id)
    with engine.connect() as c:
        return [_consent_out(r) for r in c.execute(stmt.order_by(CONSENTS.c.given_at.desc())).all()]


def active_consent(engine: sa.engine.Engine, tenant: str, subject_type: str, subject_id: str, purpose: str) -> bool:
    with engine.connect() as c:
        return c.execute(sa.select(CONSENTS.c.id).where(
            CONSENTS.c.tenant_id == tenant, CONSENTS.c.subject_type == subject_type, CONSENTS.c.subject_id == subject_id,
            CONSENTS.c.purpose == purpose, CONSENTS.c.withdrawn_at.is_(None))).first() is not None


def add_consent(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any],
                exists: Optional[Callable[[str, str], bool]] = None) -> dict[str, Any]:
    """Rıza kaydı: kim, hangi amaç, hangi aydınlatma sürümü, ne zaman, hangi kanal, kanıt nerede."""
    ensure(engine)
    st = str(body.get("subjectType") or "")
    sid = str(body.get("subjectId") or "").strip()
    purpose = str(body.get("purpose") or "")
    if st not in SUBJECT_TYPES or not sid:
        raise HrError("Rızanın kime ait olduğu seçilmedi.")
    if purpose not in PURPOSES or PURPOSES[purpose].get("subject") != st:
        raise HrError("Bu kişi türü için geçerli bir rıza amacı seçin.")
    if exists is not None and not exists(st, sid):
        raise HrError("Rızanın ait olduğu kayıt bulunamadı.", 404)
    channel = str(body.get("channel") or "")
    if channel not in CHANNELS:
        raise HrError("Rızanın alındığı kanalı seçin.")
    notice = current_notice(engine, tenant, st)
    version = body.get("noticeVersion")
    if version in (None, ""):
        if notice is None:
            raise HrError("Önce bu kitle için aydınlatma metni yayımlayın; rıza hangi metne dayandığını taşımalı.")
        version = notice["version"]
    given = aware(body.get("givenAt")) if body.get("givenAt") else now()
    if given > now() + timedelta(minutes=5):
        raise HrError("Rıza tarihi gelecekte olamaz.")
    if active_consent(engine, tenant, st, sid, purpose):
        raise HrError("Bu amaç için geçerli bir rıza zaten kayıtlı.", 409)
    cid = new_id("riza")
    with engine.begin() as c:
        c.execute(CONSENTS.insert().values(id=cid, tenant_id=tenant, subject_type=st, subject_id=sid, purpose=purpose,
                                           notice_version=int(version), given_at=given, channel=channel,
                                           evidence=str(body.get("evidence") or "").strip()[:2000] or None, recorded_by=actor))
        out = _consent_out(c.execute(sa.select(CONSENTS).where(CONSENTS.c.id == cid)).first())
    _run_hooks(_added_hooks, engine, tenant, st, sid, purpose)
    return out


def withdraw_consent(engine: sa.engine.Engine, tenant: str, actor: str, consent_id: str) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(CONSENTS).where(CONSENTS.c.id == consent_id, CONSENTS.c.tenant_id == tenant)).first()
        if r is None:
            raise HrError("Rıza kaydı bulunamadı.", 404)
        if r.withdrawn_at is not None:
            raise HrError("Bu rıza zaten geri çekilmiş.", 409)
        c.execute(CONSENTS.update().where(CONSENTS.c.id == consent_id).values(withdrawn_at=now(), withdrawn_by=actor))
        row = c.execute(sa.select(CONSENTS).where(CONSENTS.c.id == consent_id)).first()
    _run_hooks(_withdraw_hooks, engine, tenant, r.subject_type, r.subject_id, r.purpose)
    return _consent_out(row)


# ------------------------------------------------------------------ saklama süreleri


def retention(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        rows = {r.data_class: r for r in c.execute(sa.select(RETENTION).where(RETENTION.c.tenant_id == tenant)).all()}
    out = []
    for key, meta in DATA_CLASSES.items():
        r = rows.get(key)
        out.append({"dataClass": key, "label": meta["label"], "hint": meta["hint"],
                    "keepDays": (r.keep_days if r else None), "legalBasis": (r.legal_basis or "") if r else "",
                    "approvedBy": r.approved_by if r else None, "approvedAt": iso(r.approved_at) if r else None})
    return out


def keep_days(engine: sa.engine.Engine, tenant: str, data_class: str) -> Optional[int]:
    with engine.connect() as c:
        v = c.execute(sa.select(RETENTION.c.keep_days).where(RETENTION.c.tenant_id == tenant,
                                                             RETENTION.c.data_class == data_class)).scalar()
    return int(v) if v else None


def put_retention(engine: sa.engine.Engine, tenant: str, actor: str, items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Veri sınıfı başına süre ve hukuki dayanak. Süre boş bırakılırsa o sınıfta imha yapılmaz (ekranda uyarı)."""
    ensure(engine)
    diff: dict[str, Any] = {}
    with engine.begin() as c:
        for it in items or []:
            key = str(it.get("dataClass") or "")
            if key not in DATA_CLASSES:
                raise HrError(f"Bilinmeyen veri sınıfı: {key}")
            raw = it.get("keepDays")
            days: Optional[int]
            if raw in (None, ""):
                days = None
            else:
                try:
                    days = int(raw)
                except (TypeError, ValueError):
                    raise HrError(f"«{DATA_CLASSES[key]['label']}» süresi gün sayısı olmalı.") from None
                if days <= 0:
                    raise HrError(f"«{DATA_CLASSES[key]['label']}» süresi 1 günden kısa olamaz.")
            basis = str(it.get("legalBasis") or "").strip()[:2000]
            if days is not None and not basis:
                raise HrError(f"«{DATA_CLASSES[key]['label']}» için hukuki dayanağı yazın.")
            old = c.execute(sa.select(RETENTION).where(RETENTION.c.tenant_id == tenant, RETENTION.c.data_class == key)).first()
            if old is not None and old.keep_days == days and (old.legal_basis or "") == basis:
                continue
            vals = dict(keep_days=days, legal_basis=basis or None, approved_by=actor, approved_at=now())
            if old is None:
                c.execute(RETENTION.insert().values(tenant_id=tenant, data_class=key, **vals))
            else:
                c.execute(RETENTION.update().where(RETENTION.c.tenant_id == tenant, RETENTION.c.data_class == key).values(**vals))
            diff[key] = {"once": old.keep_days if old is not None else None, "sonra": days}
    if diff:
        _run_hooks(_retention_hooks, engine, tenant)
    return retention(engine, tenant), diff


# ------------------------------------------------------------------ erişim kaydı


def log_access(engine: sa.engine.Engine, tenant: str, user: str, subject_type: str, subject_id: str, action: str,
               purpose: str = "") -> None:
    try:
        ensure(engine)
        with engine.begin() as c:
            c.execute(ACCESS_LOG.insert().values(tenant_id=tenant, at=now(), username=(user or "sistem")[:120],
                                                 subject_type=subject_type[:16], subject_id=str(subject_id)[:40],
                                                 action=action[:16], purpose=(purpose or None) and purpose[:200]))
    except Exception as e:  # noqa: BLE001 — erişim kaydı yazılamazsa loga; istek durmaz
        log.warning("hr: erişim kaydı yazılamadı: %s", e)


def access_log(engine: sa.engine.Engine, tenant: str, *, subject_id: str = "", username: str = "",
               before: Optional[int] = None, limit: int = 200) -> dict[str, Any]:
    """Sayfa sayfa (en yeni önce). `hasMore` ile devam edilir; hiçbir satır sessizce atlanmaz."""
    ensure(engine)
    limit = max(1, min(int(limit or 200), 1000))
    stmt = sa.select(ACCESS_LOG).where(ACCESS_LOG.c.tenant_id == tenant)
    if subject_id:
        stmt = stmt.where(ACCESS_LOG.c.subject_id == subject_id)
    if username:
        stmt = stmt.where(ACCESS_LOG.c.username == username.strip().lower())
    if before:
        stmt = stmt.where(ACCESS_LOG.c.id < int(before))
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(ACCESS_LOG.c.id.desc()).limit(limit + 1)).all()
    items = [{"id": r.id, "at": iso(r.at), "username": r.username, "subjectType": r.subject_type, "subjectId": r.subject_id,
              "action": r.action, "purpose": r.purpose or ""} for r in rows[:limit]]
    return {"items": items, "hasMore": len(rows) > limit, "next": items[-1]["id"] if len(rows) > limit else None}


# ------------------------------------------------------------------ imha


@dataclass
class Purger:
    """Bir İK modülünün imha bağı. `due` süresi dolan kayıt kimliklerini verir, `purge` onları siler ve silinen sayıyı döner."""

    key: str
    label: str
    due: Callable[[sa.engine.Engine, str, datetime], list[str]]
    purge: Callable[[sa.engine.Engine, str, list[str], datetime], int]


_purgers: dict[str, Purger] = {}


def register_purger(p: Purger) -> None:
    _purgers[p.key] = p


def purge_preview(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """Gece işinin bu gece sileceği kayıt sayısı, sınıf başına (kimlik yok)."""
    ensure(engine)
    t = now()
    out = []
    for p in _purgers.values():
        try:
            out.append({"key": p.key, "label": p.label, "due": len(p.due(engine, tenant, t)), "error": None})
        except Exception as e:  # noqa: BLE001
            out.append({"key": p.key, "label": p.label, "due": None, "error": str(e)[:300]})
    return out


def run_due_purge(engine: sa.engine.Engine, tenant: str, actor: str = "sistem") -> dict[str, Any]:
    """Süresi dolan her kaydı siler; her sınıf için bir tutanak satırı (sıfır da olsa) yazar."""
    ensure(engine)
    t = now()
    out = []
    for p in _purgers.values():
        ids: list[str] = []
        count, error = 0, None
        try:
            ids = list(p.due(engine, tenant, t))
            count = p.purge(engine, tenant, ids, t) if ids else 0
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"[:500]
            log.exception("hr: imha işi %s hata verdi", p.key)
        record_purge(engine, tenant, p.key, count, {"ids": ids}, error, actor, t)
        out.append({"key": p.key, "label": p.label, "purged": count, "error": error})
    return {"at": iso(t), "classes": out, "ok": not any(x["error"] for x in out)}


def record_purge(engine: sa.engine.Engine, tenant: str, data_class: str, count: int, detail: dict[str, Any],
                 error: Optional[str], actor: str, at: Optional[datetime] = None) -> None:
    with engine.begin() as c:
        c.execute(PURGE_RUNS.insert().values(tenant_id=tenant, at=at or now(), data_class=data_class[:40], purged_count=int(count),
                                             detail_json=dump(detail), error=error, actor=actor[:120]))


def purge_runs(engine: sa.engine.Engine, tenant: str, *, before: Optional[int] = None, limit: int = 200) -> dict[str, Any]:
    ensure(engine)
    limit = max(1, min(int(limit or 200), 1000))
    stmt = sa.select(PURGE_RUNS).where(PURGE_RUNS.c.tenant_id == tenant)
    if before:
        stmt = stmt.where(PURGE_RUNS.c.id < int(before))
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(PURGE_RUNS.c.id.desc()).limit(limit + 1)).all()
    labels = {p.key: p.label for p in _purgers.values()}
    items = [{"id": r.id, "at": iso(r.at), "dataClass": r.data_class, "label": labels.get(r.data_class, r.data_class),
              "purged": r.purged_count, "ids": (load(r.detail_json, {}) or {}).get("ids", []), "error": r.error,
              "actor": r.actor} for r in rows[:limit]]
    return {"items": items, "hasMore": len(rows) > limit, "next": items[-1]["id"] if len(rows) > limit else None}


# ------------------------------------------------------------------ arka plan işleri


def start_job(engine: sa.engine.Engine, tenant: str, owner: str, kind: str, subject_id: str,
              work: Callable[[Callable[[int, int], None]], dict[str, Any]]) -> dict[str, Any]:
    """İşi arka planda başlatır; aynı kayıtta aynı türden tek iş. Sonuç özeti tabloda (kişisel veri yazılmaz)."""
    ensure(engine)
    jid = new_id("is")
    with engine.begin() as c:
        running = c.execute(sa.select(JOBS.c.id, JOBS.c.started_at).where(
            JOBS.c.tenant_id == tenant, JOBS.c.subject_id == subject_id, JOBS.c.kind == kind, JOBS.c.state == "calisiyor")).first()
        if running is not None and aware(running.started_at) > now() - timedelta(hours=1):
            raise HrError("Bu kayıtta aynı iş sürüyor; bitmesini bekleyin.", 409)
        c.execute(JOBS.insert().values(id=jid, tenant_id=tenant, owner=owner, kind=kind, subject_id=subject_id,
                                       state="calisiyor", progress=0, total=0, started_at=now()))

    def progress(done: int, total: int) -> None:
        with engine.begin() as c:
            c.execute(JOBS.update().where(JOBS.c.id == jid).values(progress=done, total=total))

    def run() -> None:
        try:
            res = work(progress)
            with engine.begin() as c:
                c.execute(JOBS.update().where(JOBS.c.id == jid).values(state="bitti", result_json=dump(res), finished_at=now()))
        except Exception as e:  # noqa: BLE001
            log.exception("hr: iş %s (%s) hata verdi", jid, kind)
            msg = str(e) if isinstance(e, HrError) else f"İş tamamlanamadı: {type(e).__name__}"
            with engine.begin() as c:
                c.execute(JOBS.update().where(JOBS.c.id == jid).values(state="hata", error=msg[:500], finished_at=now()))

    threading.Thread(target=run, name=f"hr-{kind}-{jid[-6:]}", daemon=True).start()
    return job(engine, tenant, jid, owner)


def job(engine: sa.engine.Engine, tenant: str, jid: str, owner: Optional[str] = None) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(JOBS).where(JOBS.c.id == jid, JOBS.c.tenant_id == tenant)).first()
    if r is None or (owner is not None and r.owner != owner):
        raise HrError("İş bulunamadı.", 404)
    return {"id": r.id, "kind": r.kind, "subjectId": r.subject_id, "state": r.state, "progress": r.progress, "total": r.total,
            "result": load(r.result_json), "error": r.error, "startedAt": iso(r.started_at), "finishedAt": iso(r.finished_at)}


# ------------------------------------------------------------------ kişinin kendi kaydı


RIGHTS = ("KVKK md. 11 uyarınca kişisel verilerinizin işlenip işlenmediğini öğrenme, bilgi isteme, düzeltilmesini ya da "
          "silinmesini isteme ve itiraz etme haklarınız vardır. Başvurunuzu İnsan Kaynakları'na iletebilirsiniz.")


def me(engine: sa.engine.Engine, tenant: str, user: str) -> dict[str, Any]:
    emp = employee_by_username(engine, tenant, user)
    consents = list_consents(engine, tenant, "calisan", emp["id"]) if emp else []
    return {"employee": emp, "consents": consents, "notice": current_notice(engine, tenant, "calisan"), "rights": RIGHTS}
