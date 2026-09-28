"""M56 Performans yönetimi: hedef ağacı (şirket → birim → kişi), çeyrek check-in, revizyon, değerlendirme dönemi, form,
değerlendirme akışı, iş kayıtları özeti ve kalibrasyon. Ortak temel `hr_core` (İK-0).

Analiz: docs/analiz/kullanici-ihtiyaclari/M56-performans.md §14.

Kurallar:
- **Kapsam kayıttan gelir.** Yönetici yalnız `semantic_hr_employees.manager_id` zincirindeki kişileri (doğrudan ve dolaylı
  ekip) görür; zincir dışı kişinin kaydına bakma denemesi 403 olur ve `semantic_hr_access_log`'a «reddedildi» diye düşer.
  Başka birinin kaydı her görüntülendiğinde erişim kaydı yazılır. Bütün değerlendirmeleri yalnız `ik.degerlendirme-onay`
  (İK) ve `ik.kalibrasyon` (İK/GM, duyarlı) görür; portal yöneticisi bunları ancak rolüyle alır (`hr_core.who_from`).
- **Sistem kişiye puan vermez** (KVKK md. 11/1-g). Puanı yönetici verir; kalibrasyon yöneticilerin verdiği genel puanın
  birim × dağılımıdır. Terfi/ücret kararı kayıtta tutulmaz, yönetimdedir.
- **Çalışan her şeyi görür:** kendi hedefleri, check-in'leri, yöneticinin paylaştığı değerlendirme ve hakkında üretilen iş
  kayıtları özeti (KVKK md. 11). Yöneticinin bölümü «paylaşıldı»dan önce çalışana görünmez; paylaşımdan sonra çalışan yorum
  ve itiraz yazar, İK onaylar (yönetici kendi değerlendirmesini onaylayamaz).
- **İş kayıtları özeti bilgi amaçlıdır:** sayılar SQL'den (M2 görevleri, CRM sahiplik kayıtları), cümle sabit kalıptan;
  Zeki AI rakam üretmez. Portal kullanım kayıtları (`sl_query_log`, giriş sayısı) hiçbir yerde kullanılmaz (amaçla sınırlılık).
- **Zeki AI'a kişisel veri gitmez:** yorum yeniden yazımında çalışan ve diğer çalışan adları, iletişim bilgisi ve özel nitelikli
  satırlar maskelenir; OKR taslağına kişi adı değil birim ve unvan gider. Sıra kaydına yalnız etiket yazılır (`hr_llm`).
- **Saklama:** ayrılan çalışanın performans kayıtları `performans_kaydi` süresi (ayrılış tarihinden) dolunca silinir; süre
  girilmemişse silinmez, ekran uyarır (İş Kanunu md. 75 saklama süresi TİMAŞ politikasından).
"""
from __future__ import annotations

import json
import logging
import re
import weakref
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import hr_core as H
from semantic_bridge.hr_core import HrError, clean, dump, iso, load, new_id, now

log = logging.getLogger("semantic_bridge.hr.performance")

F_GOAL_WRITE = "ozellik:ik.hedef-yaz"
F_GOAL_APPROVE = "ozellik:ik.hedef-onay"
F_CYCLE = "ozellik:ik.donem-yonet"
F_REVIEW_WRITE = "ozellik:ik.degerlendirme-yaz"
F_REVIEW_APPROVE = "ozellik:ik.degerlendirme-onay"
F_CALIBRATION = "ozellik:ik.kalibrasyon"
F_WORK = "ozellik:ik.is-ozeti"
F_EXPORT = "ozellik:ik.disa-aktar"

DATA_CLASS = "performans_kaydi"

_md = sa.MetaData()


def _ts(name: str, **kw: Any) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


GOALS = sa.Table(
    "semantic_hr_goals", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("level", sa.String(8), nullable=False),              # sirket | birim | kisi
    sa.Column("owner_employee_id", sa.String(40), index=True),
    sa.Column("unit_id", sa.String(40), index=True),
    sa.Column("parent_goal_id", sa.String(40), index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("description", sa.Text),
    sa.Column("measure_kind", sa.String(8), nullable=False),       # beyan | sistem
    sa.Column("system_measure", sa.String(40)),                    # logo_net_satis
    sa.Column("measure_ref", sa.String(80)),                       # ör. Logo satış temsilcisi kodu
    sa.Column("target_value", sa.Numeric(20, 2)),
    sa.Column("unit_label", sa.String(20)),
    sa.Column("weight", sa.Integer),
    sa.Column("period", sa.String(10), nullable=False, index=True),  # 2026 | 2026-Q4
    sa.Column("state", sa.String(12), nullable=False),             # taslak | onayda | yururlukte | kapandi
    sa.Column("submitted_by", sa.String(120)),
    _ts("submitted_at"),
    sa.Column("approved_by", sa.String(120)),
    _ts("approved_at"),
    sa.Column("review_note", sa.Text),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
    _ts("closed_at"),
)

CHECKINS = sa.Table(
    "semantic_hr_goal_checkins", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("goal_id", sa.String(40), nullable=False, index=True),
    _ts("at", nullable=False),
    sa.Column("author", sa.String(120), nullable=False),
    sa.Column("progress_pct", sa.Integer),
    sa.Column("value", sa.Numeric(20, 2)),
    sa.Column("note", sa.Text),
)

REVISIONS = sa.Table(
    "semantic_hr_goal_revisions", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("goal_id", sa.String(40), nullable=False, index=True),
    sa.Column("requested_by", sa.String(120), nullable=False),
    _ts("requested_at", nullable=False),
    sa.Column("change_json", sa.Text, nullable=False),
    sa.Column("reason", sa.Text),
    sa.Column("decided_by", sa.String(120)),
    _ts("decided_at"),
    sa.Column("decision", sa.String(8)),                          # onay | ret
    sa.Column("decision_note", sa.Text),
)

FORMS = sa.Table(
    "semantic_hr_review_forms", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("sections_json", sa.Text, nullable=False),
    sa.Column("overall_labels_json", sa.Text),
    sa.Column("state", sa.String(12), nullable=False),             # taslak | yururlukte | arsiv
    sa.Column("created_by", sa.String(120)),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
)

CYCLES = sa.Table(
    "semantic_hr_review_cycles", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("period_start", sa.Date, nullable=False),            # değerlendirilen dönem
    sa.Column("period_end", sa.Date, nullable=False),
    sa.Column("starts_on", sa.Date, nullable=False),               # formların doldurulduğu aralık
    sa.Column("ends_on", sa.Date, nullable=False),
    sa.Column("self_due", sa.Date),
    sa.Column("manager_due", sa.Date),
    sa.Column("form_template_id", sa.String(40)),
    sa.Column("form_snapshot_json", sa.Text),
    sa.Column("audience_json", sa.Text),                           # {"units": [...]} ya da {} (herkes)
    sa.Column("state", sa.String(12), nullable=False),             # hazirlik | acik | kalibrasyon | kapandi
    sa.Column("last_reminded_on", sa.Date),
    sa.Column("created_by", sa.String(120)),
    _ts("created_at", nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at", nullable=False),
    _ts("closed_at"),
)

REVIEWS = sa.Table(
    "semantic_hr_reviews", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("cycle_id", sa.String(40), nullable=False, index=True),
    sa.Column("employee_id", sa.String(40), nullable=False, index=True),
    sa.Column("manager_id", sa.String(40), index=True),
    sa.Column("self_json", sa.Text),
    _ts("self_submitted_at"),
    sa.Column("manager_json", sa.Text),
    _ts("manager_submitted_at"),
    _ts("shared_at"),
    _ts("meeting_at"),
    sa.Column("employee_comment", sa.Text),
    sa.Column("objection", sa.Boolean, nullable=False, default=False),
    _ts("commented_at"),
    sa.Column("hr_approved_by", sa.String(120)),
    _ts("hr_approved_at"),
    sa.Column("hr_note", sa.Text),
    _ts("updated_at", nullable=False),
    sa.UniqueConstraint("cycle_id", "employee_id", name="uq_hr_review_cycle_employee"),
)

WORK = sa.Table(
    "semantic_hr_work_summaries", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("employee_id", sa.String(40), nullable=False, index=True),
    sa.Column("cycle_id", sa.String(40), index=True),
    sa.Column("period_start", sa.Date, nullable=False),
    sa.Column("period_end", sa.Date, nullable=False),
    _ts("generated_at", nullable=False),
    sa.Column("generated_by", sa.String(120), nullable=False),
    sa.Column("facts_json", sa.Text, nullable=False),              # sayılar + kaynak sorgu kimliği
    sa.Column("text", sa.Text, nullable=False),
    _ts("shown_to_employee_at"),
)

_ready: "weakref.WeakSet[sa.engine.Engine]" = weakref.WeakSet()

LEVELS = {"sirket": "Şirket", "birim": "Birim", "kisi": "Kişi"}
GOAL_STATES = {"taslak": "Taslak", "onayda": "Onayda", "yururlukte": "Yürürlükte", "kapandi": "Kapandı"}
MEASURE_KINDS = {"beyan": "Beyan (check-in ile)", "sistem": "Sistem ölçüsü"}
SYSTEM_MEASURES = {"logo_net_satis": {"label": "Logo faturalı net satış (₺)", "unit": "₺",
                                      "hint": "Satış temsilcisi kodunun faturalı net satışı: satış − iade, LINENET"}}
FORM_STATES = {"taslak": "Taslak", "yururlukte": "Yürürlükte", "arsiv": "Arşiv"}
SECTION_KINDS = {"yetkinlik": "Yetkinlik (1–5 puan)", "hedef": "Hedefler (dönemin hedefleri üzerinden)", "acik": "Açık uçlu"}
CYCLE_STATES = {"hazirlik": "Hazırlık", "acik": "Açık", "kalibrasyon": "Kalibrasyon", "kapandi": "Kapandı"}
REVIEW_STATES = {"oz_degerlendirme": "Öz değerlendirme bekleniyor", "yonetici": "Yönetici değerlendirmesi bekleniyor",
                 "gorusme": "Görüşme ve paylaşım bekleniyor", "calisan_yorumu": "Çalışan yorumu bekleniyor",
                 "ik_onayi": "İK onayı bekleniyor", "onaylandi": "Onaylandı"}
DEFAULT_OVERALL = ["Beklenenin çok altında", "Beklenenin altında", "Beklenen düzeyde", "Beklenenin üstünde", "Beklenenin çok üstünde"]
_PERIOD = re.compile(r"^(\d{4})(?:-Q([1-4]))?$")


def ensure(engine: sa.engine.Engine) -> None:
    H.ensure(engine)
    with H._lock:
        if engine in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(engine)


def register_hooks() -> None:
    H.register_data_class(DATA_CLASS, "Performans kaydı (ayrılan çalışan)",
                          "Hedef, check-in, revizyon, değerlendirme ve iş kayıtları özeti; süre çalışanın ayrılış tarihinden sayılır. "
                          "Onaylı değerlendirme özlük kaydıdır: süreyi TİMAŞ saklama politikasına göre girin")
    H.register_purger(H.Purger(DATA_CLASS, "Performans kayıtları", due_purge, purge))


# ------------------------------------------------------------------ yardımcılar


def period_range(period: str) -> tuple[date, date]:
    """«2026» → 2026-01-01..2026-12-31; «2026-Q4» → 2026-10-01..2026-12-31 (iki uç dahil)."""
    m = _PERIOD.match((period or "").strip())
    if not m:
        raise HrError("Dönem «2026» ya da «2026-Q4» biçiminde olmalı.")
    y = int(m.group(1))
    if not m.group(2):
        return date(y, 1, 1), date(y, 12, 31)
    q = int(m.group(2))
    start = date(y, 3 * q - 2, 1)
    end = (date(y + 1, 1, 1) if q == 4 else date(y, 3 * q + 1, 1)) - timedelta(days=1)
    return start, end


def _num(v: Any, what: str) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        raise HrError(f"{what} sayı olmalı.") from None


def _f(v: Any) -> Optional[float]:
    return None if v is None else float(v)


class Scope:
    """İsteği yapan kişinin kapsamı: kendi çalışan kaydı, ekibi (manager_id zinciri) ve genel anahtarları."""

    def __init__(self, engine: sa.engine.Engine, tenant: str, who: H.Who):
        self.who = who
        with engine.connect() as c:
            rows = c.execute(sa.select(H.EMPLOYEES.c.id, H.EMPLOYEES.c.manager_id, H.EMPLOYEES.c.unit_id, H.EMPLOYEES.c.username,
                                       H.EMPLOYEES.c.display_name, H.EMPLOYEES.c.title, H.EMPLOYEES.c.status,
                                       H.EMPLOYEES.c.crm_systemuser_id, H.EMPLOYEES.c.start_date, H.EMPLOYEES.c.end_date)
                             .where(H.EMPLOYEES.c.tenant_id == tenant)).all()
            units = c.execute(sa.select(H.UNITS.c.id, H.UNITS.c.name, H.UNITS.c.parent_id, H.UNITS.c.manager_employee_id)
                              .where(H.UNITS.c.tenant_id == tenant)).all()
        self.emp = {r.id: r for r in rows}
        self.units = {u.id: u for u in units}
        u = (who.user or "").strip().lower()
        mine = [r for r in rows if (r.username or "") == u]
        mine.sort(key=lambda r: r.status != "aktif")
        self.me: Optional[Any] = mine[0] if mine else None
        self.me_id = self.me.id if self.me else None
        children: dict[str, list[str]] = {}
        for r in rows:
            if r.manager_id:
                children.setdefault(r.manager_id, []).append(r.id)
        self.team: set[str] = set()
        stack = list(children.get(self.me_id or "", []))
        while stack:
            x = stack.pop()
            if x in self.team or x == self.me_id:
                continue
            self.team.add(x)
            stack.extend(children.get(x, []))
        self.direct = set(children.get(self.me_id or "", []))
        #: Bütün kişi kayıtlarını görenler: İK onayı, kalibrasyon (İK/GM).
        self.all = who.can(F_REVIEW_APPROVE, F_CALIBRATION)
        self.cycle_admin = who.can(F_CYCLE)

    def name(self, eid: Optional[str]) -> Optional[str]:
        r = self.emp.get(eid or "")
        return r.display_name if r else None

    def unit_name(self, uid: Optional[str]) -> Optional[str]:
        u = self.units.get(uid or "")
        return u.name if u else None

    def managed_units(self) -> set[str]:
        """Yöneticisi olduğum birimler ve alt birimleri."""
        if not self.me_id:
            return set()
        roots = {u.id for u in self.units.values() if u.manager_employee_id == self.me_id}
        out: set[str] = set()
        kids: dict[str, list[str]] = {}
        for u in self.units.values():
            if u.parent_id:
                kids.setdefault(u.parent_id, []).append(u.id)
        stack = list(roots)
        while stack:
            x = stack.pop()
            if x in out:
                continue
            out.add(x)
            stack.extend(kids.get(x, []))
        return out

    def sees_person(self, eid: Optional[str]) -> bool:
        return bool(eid) and (eid == self.me_id or eid in self.team or self.all)

    def unit_subtree(self, uid: str) -> set[str]:
        kids: dict[str, list[str]] = {}
        for u in self.units.values():
            if u.parent_id:
                kids.setdefault(u.parent_id, []).append(u.id)
        out, stack = set(), [uid]
        while stack:
            x = stack.pop()
            if x in out:
                continue
            out.add(x)
            stack.extend(kids.get(x, []))
        return out


def deny(engine: sa.engine.Engine, tenant: str, sc: Scope, subject_id: str, what: str) -> HrError:
    """Kapsam dışı deneme: erişim kaydına «reddedildi» yazılır, 403 döner."""
    H.log_access(engine, tenant, sc.who.user, "calisan", subject_id or "-", "reddedildi", what)
    return HrError("Bu kişinin performans kaydı kapsamınızda değil.", 403)


# ------------------------------------------------------------------ hedefler


def _goal_out(r: Any, sc: Scope, last: Optional[Any] = None, parent_title: Optional[str] = None,
              open_revision: Optional[Any] = None) -> dict[str, Any]:
    return {
        "id": r.id, "level": r.level, "levelLabel": LEVELS.get(r.level, r.level), "ownerEmployeeId": r.owner_employee_id,
        "ownerName": sc.name(r.owner_employee_id), "unitId": r.unit_id, "unitName": sc.unit_name(r.unit_id),
        "parentGoalId": r.parent_goal_id, "parentTitle": parent_title, "title": r.title, "description": r.description or "",
        "measureKind": r.measure_kind, "systemMeasure": r.system_measure, "measureRef": r.measure_ref,
        "targetValue": _f(r.target_value), "unitLabel": r.unit_label or "", "weight": r.weight, "period": r.period,
        "state": r.state, "stateLabel": GOAL_STATES.get(r.state, r.state), "submittedBy": r.submitted_by,
        "submittedAt": iso(r.submitted_at), "approvedBy": r.approved_by, "approvedAt": iso(r.approved_at),
        "reviewNote": r.review_note or "", "createdBy": r.created_by, "updatedAt": iso(r.updated_at),
        "aligned": r.level == "sirket" or bool(r.parent_goal_id),
        "lastCheckin": None if last is None else {"at": iso(last.at), "author": last.author, "progressPct": last.progress_pct,
                                                   "value": _f(last.value), "note": last.note or ""},
        "openRevision": None if open_revision is None else _revision_out(open_revision),
    }


def _revision_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "goalId": r.goal_id, "requestedBy": r.requested_by, "requestedAt": iso(r.requested_at),
            "changes": load(r.change_json, {}), "reason": r.reason or "", "decidedBy": r.decided_by, "decidedAt": iso(r.decided_at),
            "decision": r.decision, "decisionNote": r.decision_note or ""}


def _visible_goal(sc: Scope, r: Any) -> bool:
    if r.level != "kisi":
        return True
    # Kişi hedefi: kendisi, yönetici zinciri (GM zincirin tepesinde olduğu için hepsini), İK (dönem yönetimi) ve İK onayı.
    return sc.sees_person(r.owner_employee_id) or sc.cycle_admin


def list_goals(engine: sa.engine.Engine, tenant: str, sc: Scope, *, period: str = "", owner: str = "", level: str = "",
               year: str = "") -> list[dict[str, Any]]:
    ensure(engine)
    stmt = sa.select(GOALS).where(GOALS.c.tenant_id == tenant)
    if period:
        stmt = stmt.where(GOALS.c.period == period)
    elif year:
        stmt = stmt.where(GOALS.c.period.like(f"{clean(year, 4)}%"))
    if owner:
        stmt = stmt.where(GOALS.c.owner_employee_id == owner)
    if level in LEVELS:
        stmt = stmt.where(GOALS.c.level == level)
    with engine.connect() as c:
        rows = [r for r in c.execute(stmt.order_by(GOALS.c.period, GOALS.c.level, GOALS.c.title)).all() if _visible_goal(sc, r)]
        ids = [r.id for r in rows] or [""]
        last: dict[str, Any] = {}
        for ck in c.execute(sa.select(CHECKINS).where(CHECKINS.c.goal_id.in_(ids)).order_by(CHECKINS.c.at)).all():
            last[ck.goal_id] = ck
        revs = {r.goal_id: r for r in c.execute(sa.select(REVISIONS).where(REVISIONS.c.goal_id.in_(ids), REVISIONS.c.decided_at.is_(None))).all()}
        parent_ids = {r.parent_goal_id for r in rows if r.parent_goal_id}
        titles = dict(c.execute(sa.select(GOALS.c.id, GOALS.c.title).where(GOALS.c.id.in_(sorted(parent_ids) or [""]))).all())
    return [_goal_out(r, sc, last.get(r.id), titles.get(r.parent_goal_id or ""), revs.get(r.id)) for r in rows]


def _goal_row(c: Any, tenant: str, gid: str) -> Any:
    r = c.execute(sa.select(GOALS).where(GOALS.c.id == gid, GOALS.c.tenant_id == tenant)).first()
    if r is None:
        raise HrError("Hedef bulunamadı.", 404)
    return r


def get_goal(engine: sa.engine.Engine, tenant: str, sc: Scope, gid: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = _goal_row(c, tenant, gid)
        if not _visible_goal(sc, r):
            raise deny(engine, tenant, sc, r.owner_employee_id or "", "hedef")
        checkins = c.execute(sa.select(CHECKINS).where(CHECKINS.c.goal_id == gid).order_by(CHECKINS.c.at.desc())).all()
        revs = c.execute(sa.select(REVISIONS).where(REVISIONS.c.goal_id == gid).order_by(REVISIONS.c.requested_at.desc())).all()
        parent = c.execute(sa.select(GOALS.c.title).where(GOALS.c.id == (r.parent_goal_id or ""))).scalar()
        children = c.execute(sa.select(GOALS).where(GOALS.c.parent_goal_id == gid, GOALS.c.tenant_id == tenant)).all()
    if r.level == "kisi" and r.owner_employee_id and r.owner_employee_id != sc.me_id:
        H.log_access(engine, tenant, sc.who.user, "calisan", r.owner_employee_id, "goruntule", "performans hedefi")
    out = _goal_out(r, sc, checkins[0] if checkins else None, parent,
                    next((x for x in revs if x.decided_at is None), None))
    out["checkins"] = [{"id": k.id, "at": iso(k.at), "author": k.author, "progressPct": k.progress_pct, "value": _f(k.value),
                        "note": k.note or ""} for k in checkins]
    out["revisions"] = [_revision_out(x) for x in revs]
    out["children"] = [{"id": k.id, "title": k.title, "level": k.level, "ownerName": sc.name(k.owner_employee_id),
                        "unitName": sc.unit_name(k.unit_id), "state": k.state} for k in children if _visible_goal(sc, k)]
    out["can"] = goal_can(sc, r)
    return out


def _can_write_level(sc: Scope, level: str, owner: Optional[str], unit: Optional[str]) -> bool:
    w = sc.who
    if level == "sirket":
        return w.can(F_GOAL_APPROVE)
    if level == "birim":
        return w.can(F_GOAL_APPROVE) or (w.can(F_GOAL_WRITE) and bool(unit) and unit in sc.managed_units())
    return bool(owner) and (owner == sc.me_id or (w.can(F_GOAL_WRITE) and owner in sc.team))


def _can_approve(sc: Scope, r: Any, submitted_by: Optional[str]) -> bool:
    w = sc.who
    if not w.can(F_GOAL_APPROVE):
        return False
    if r.level == "sirket":
        return True                                   # şirket hedefi üst yönetimin kararıdır
    if submitted_by and submitted_by == w.user:
        return False                                  # gönderen onaylayamaz
    if r.level == "kisi":
        return r.owner_employee_id in sc.team
    return True


def goal_can(sc: Scope, r: Any) -> dict[str, bool]:
    write = _can_write_level(sc, r.level, r.owner_employee_id, r.unit_id)
    track = r.state == "yururlukte" and (write or (r.level == "kisi" and r.owner_employee_id == sc.me_id))
    return {"edit": write and r.state == "taslak", "submit": write and r.state == "taslak",
            "withdraw": write and r.state == "onayda", "approve": r.state == "onayda" and _can_approve(sc, r, r.submitted_by),
            "checkin": track, "revise": track, "close": r.state == "yururlukte" and (sc.cycle_admin or sc.who.can(F_GOAL_APPROVE))}


def save_goal(engine: sa.engine.Engine, tenant: str, sc: Scope, body: dict[str, Any], gid: Optional[str] = None,
              *, system_measures_on: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure(engine)
    with engine.begin() as c:
        before = _goal_row(c, tenant, gid) if gid else None
        if before is not None and before.state != "taslak":
            raise HrError("Yalnız taslak hedef düzenlenir; yürürlükteki hedef için revizyon isteyin.", 409)
        level = before.level if before is not None else str(body.get("level") or "kisi")
        if level not in LEVELS:
            raise HrError("Hedef düzeyi şirket, birim ya da kişi olmalı.")
        owner = before.owner_employee_id if before is not None else (body.get("ownerEmployeeId") or (sc.me_id if level == "kisi" else None))
        unit = body.get("unitId", before.unit_id if before is not None else None) or None
        if level == "kisi":
            if not owner or owner not in sc.emp:
                raise HrError("Hedefin sahibi çalışan kaydında yok. Önce İK çalışan kaydınızı açmalı.")
            unit = sc.emp[owner].unit_id
        elif level == "birim":
            owner = None
            if not unit or unit not in sc.units:
                raise HrError("Birim hedefi için birim seçin.")
        else:
            owner, unit = None, None
        if not _can_write_level(sc, level, owner, unit):
            raise HrError("Bu hedefi yazma yetkiniz yok (kendi hedefiniz, ekibinizin hedefi ya da yöneticisi olduğunuz birim).", 403)
        vals: dict[str, Any] = {}

        def pick(key: str, default: Any = None) -> Any:
            return body.get(key) if key in body else (getattr(before, _COLS[key]) if before is not None else default)

        title = clean(pick("title"), 300)
        if not title:
            raise HrError("Hedefin başlığı boş olamaz.")
        period = clean(pick("period"), 10)
        period_range(period)
        kind = str(pick("measureKind", "beyan") or "beyan")
        if kind not in MEASURE_KINDS:
            raise HrError("Ölçü türü beyan ya da sistem olmalı.")
        sm, ref = None, None
        if kind == "sistem":
            if not system_measures_on:
                raise HrError("Sistem ölçüsü bu kurulumda kapalı (satış temsilcisi alanı doluluğu ölçülmeden açılmaz).")
            sm = str(pick("systemMeasure") or "")
            if sm not in SYSTEM_MEASURES:
                raise HrError("Tanımlı bir sistem ölçüsü seçin.")
            ref = clean(pick("measureRef"), 80)
            if not ref:
                raise HrError("Logo satış temsilcisi kodunu yazın.")
        target = _num(pick("targetValue"), "Hedef değer")
        weight = pick("weight")
        if weight not in (None, ""):
            try:
                weight = int(weight)
            except (TypeError, ValueError):
                raise HrError("Ağırlık tam sayı olmalı.") from None
            if not 0 <= weight <= 100:
                raise HrError("Ağırlık 0–100 arasında olmalı.")
        else:
            weight = None
        parent = pick("parentGoalId") or None
        if parent:
            p = c.execute(sa.select(GOALS).where(GOALS.c.id == parent, GOALS.c.tenant_id == tenant)).first()
            if p is None or p.id == gid:
                raise HrError("Bağlı olduğu hedef bulunamadı.")
            if level == "sirket" or (level == "birim" and p.level == "kisi") or (level == "kisi" and p.level == "kisi"):
                raise HrError("Hedef yalnız üst düzey bir hedefe bağlanır (kişi → birim/şirket, birim → şirket/üst birim).")
            if p.period[:4] != period[:4]:
                raise HrError("Bağlı olduğu hedef aynı yılın hedefi olmalı.")
            if p.state == "kapandi":
                raise HrError("Kapanmış bir hedefe bağlanamaz.")
        vals.update(level=level, owner_employee_id=owner, unit_id=unit, parent_goal_id=parent, title=title,
                    description=str(pick("description") or "").strip()[:4000] or None, measure_kind=kind, system_measure=sm,
                    measure_ref=ref, target_value=target, unit_label=clean(pick("unitLabel"), 20) or (SYSTEM_MEASURES[sm]["unit"] if sm else None),
                    weight=weight, period=period, updated_by=sc.who.user, updated_at=now())
        if before is None:
            gid = new_id("hdf")
            c.execute(GOALS.insert().values(id=gid, tenant_id=tenant, state="taslak", created_by=sc.who.user, created_at=now(), **vals))
            diff = {"yeni": title, "duzey": level}
        else:
            diff = {k: {"once": _jsonable(getattr(before, k)), "sonra": _jsonable(v)} for k, v in vals.items()
                    if k not in ("updated_by", "updated_at") and _jsonable(getattr(before, k)) != _jsonable(v)}
            c.execute(GOALS.update().where(GOALS.c.id == gid).values(**vals))
    return get_goal(engine, tenant, sc, gid), diff


_COLS = {"title": "title", "period": "period", "measureKind": "measure_kind", "systemMeasure": "system_measure",
         "measureRef": "measure_ref", "targetValue": "target_value", "weight": "weight", "parentGoalId": "parent_goal_id",
         "description": "description", "unitLabel": "unit_label"}


def _jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, bool)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def goal_transition(engine: sa.engine.Engine, tenant: str, sc: Scope, gid: str, action: str, note: str = "") -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        r = _goal_row(c, tenant, gid)
        can = goal_can(sc, r)
        t = now()
        if action == "submit" and can["submit"]:
            vals = dict(state="onayda", submitted_by=sc.who.user, submitted_at=t, review_note=None)
        elif action == "withdraw" and can["withdraw"]:
            vals = dict(state="taslak")
        elif action == "approve" and can["approve"]:
            vals = dict(state="yururlukte", approved_by=sc.who.user, approved_at=t, review_note=clean(note, 2000) or None)
        elif action == "reject" and can["approve"]:
            if not note.strip():
                raise HrError("Geri gönderirken gerekçe yazın.")
            vals = dict(state="taslak", review_note=clean(note, 2000))
        elif action == "close" and can["close"]:
            vals = dict(state="kapandi", closed_at=t)
        else:
            raise HrError(f"Bu hedefte «{action}» işlemi şu durumda ({GOAL_STATES.get(r.state, r.state)}) ya da rolünüzle yapılamaz.", 403)
        c.execute(GOALS.update().where(GOALS.c.id == gid).values(updated_by=sc.who.user, updated_at=t, **vals))
    return get_goal(engine, tenant, sc, gid)


def add_checkin(engine: sa.engine.Engine, tenant: str, sc: Scope, gid: str, body: dict[str, Any]) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        r = _goal_row(c, tenant, gid)
        if not goal_can(sc, r)["checkin"]:
            raise HrError("Check-in yalnız yürürlükteki hedefte, hedefin sahibi ya da yöneticisi tarafından yapılır.", 403)
        pct = body.get("progressPct")
        if pct not in (None, ""):
            try:
                pct = int(pct)
            except (TypeError, ValueError):
                raise HrError("İlerleme yüzde olarak tam sayı olmalı.") from None
            if not 0 <= pct <= 100:
                raise HrError("İlerleme 0–100 arasında olmalı.")
        else:
            pct = None
        value = _num(body.get("value"), "Değer")
        note = str(body.get("note") or "").strip()[:2000]
        if pct is None and value is None and not note:
            raise HrError("İlerleme, değer ya da not girin.")
        c.execute(CHECKINS.insert().values(id=new_id("ci"), tenant_id=tenant, goal_id=gid, at=now(), author=sc.who.user,
                                           progress_pct=pct, value=value, note=note or None))
    return get_goal(engine, tenant, sc, gid)


_REV_FIELDS = {"title": "title", "targetValue": "target_value", "weight": "weight", "parentGoalId": "parent_goal_id",
               "description": "description"}


def request_revision(engine: sa.engine.Engine, tenant: str, sc: Scope, gid: str, body: dict[str, Any]) -> dict[str, Any]:
    ensure(engine)
    changes = {k: body["changes"][k] for k in _REV_FIELDS if isinstance(body.get("changes"), dict) and k in body["changes"]}
    reason = str(body.get("reason") or "").strip()[:2000]
    if not changes:
        raise HrError("Değişecek alanı yazın (başlık, hedef değer, ağırlık, bağlı hedef, açıklama).")
    if not reason:
        raise HrError("Revizyonun gerekçesini yazın.")
    with engine.begin() as c:
        r = _goal_row(c, tenant, gid)
        if not goal_can(sc, r)["revise"]:
            raise HrError("Revizyon yalnız yürürlükteki hedefte, sahibi ya da yöneticisi tarafından istenir.", 403)
        if c.execute(sa.select(REVISIONS.c.id).where(REVISIONS.c.goal_id == gid, REVISIONS.c.decided_at.is_(None))).first():
            raise HrError("Bu hedefte karar bekleyen bir revizyon var.", 409)
        if "targetValue" in changes:
            changes["targetValue"] = _num(changes["targetValue"], "Hedef değer")
        if "title" in changes:
            changes["title"] = clean(changes["title"], 300)
            if not changes["title"]:
                raise HrError("Başlık boş olamaz.")
        c.execute(REVISIONS.insert().values(id=new_id("rev"), tenant_id=tenant, goal_id=gid, requested_by=sc.who.user,
                                            requested_at=now(), change_json=dump(changes), reason=reason))
    return get_goal(engine, tenant, sc, gid)


def decide_revision(engine: sa.engine.Engine, tenant: str, sc: Scope, rid: str, decision: str, note: str = "") -> dict[str, Any]:
    ensure(engine)
    if decision not in ("onay", "ret"):
        raise HrError("Karar «onay» ya da «ret» olmalı.")
    with engine.begin() as c:
        rev = c.execute(sa.select(REVISIONS).where(REVISIONS.c.id == rid, REVISIONS.c.tenant_id == tenant)).first()
        if rev is None:
            raise HrError("Revizyon talebi bulunamadı.", 404)
        if rev.decided_at is not None:
            raise HrError("Bu talep zaten karara bağlandı.", 409)
        g = _goal_row(c, tenant, rev.goal_id)
        if not _can_approve(sc, g, rev.requested_by):
            raise HrError("Bu revizyonu onaylama yetkiniz yok (talep eden onaylayamaz; kişi hedefinde yalnız zincirdeki yönetici).", 403)
        if decision == "ret" and not note.strip():
            raise HrError("Reddederken gerekçe yazın.")
        t = now()
        c.execute(REVISIONS.update().where(REVISIONS.c.id == rid).values(decided_by=sc.who.user, decided_at=t, decision=decision,
                                                                         decision_note=clean(note, 2000) or None))
        if decision == "onay":
            ch = load(rev.change_json, {})
            vals = {_REV_FIELDS[k]: v for k, v in ch.items() if k in _REV_FIELDS}
            if vals.get("weight") not in (None, ""):
                vals["weight"] = int(vals["weight"])
            c.execute(GOALS.update().where(GOALS.c.id == g.id).values(updated_by=sc.who.user, updated_at=t, **vals))
    return get_goal(engine, tenant, sc, g.id)


def align_candidates(engine: sa.engine.Engine, tenant: str, sc: Scope, gid: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Hizalama önerisinin aday listesi: aynı yılın üst düzey (birim/şirket), kapanmamış hedefleri."""
    g = get_goal(engine, tenant, sc, gid)
    if g["level"] == "sirket":
        raise HrError("Şirket hedefi bir üst hedefe bağlanmaz.")
    with engine.connect() as c:
        rows = c.execute(sa.select(GOALS).where(GOALS.c.tenant_id == tenant, GOALS.c.period.like(g["period"][:4] + "%"),
                                                GOALS.c.state.in_(("onayda", "yururlukte")), GOALS.c.id != gid,
                                                GOALS.c.level.in_(("birim", "sirket") if g["level"] == "kisi" else ("sirket", "birim")))).all()
    cands = [{"id": r.id, "title": r.title, "level": r.level, "unitName": sc.unit_name(r.unit_id)} for r in rows
             if not (g["level"] == "birim" and r.level == "birim" and r.unit_id == g["unitId"])]
    return g, cands


def align_prompt(goal: dict[str, Any], cands: list[dict[str, Any]]) -> tuple[str, list[str]]:
    labels = [str(i + 1) for i in range(len(cands))]
    lines = "\n".join(f"{i + 1}. [{LEVELS[x['level']]}{' · ' + x['unitName'] if x['unitName'] else ''}] {x['title']}" for i, x in enumerate(cands))
    prompt = (f"Bir çalışanın ya da birimin hedefi aşağıdaki üst hedeflerden hangisine en doğrudan katkı verir?\n\nHedef: {goal['title']}\n"
              f"{('Açıklama: ' + goal['description'][:600]) if goal['description'] else ''}\n\nÜst hedefler:\n{lines}\n\n"
              "Yalnız numarayı yaz.")
    return prompt, labels


def okr_messages(parent: Optional[dict[str, Any]], unit_name: str, title: str, hint: str) -> list[dict[str, str]]:
    """OKR taslağı istemi. Kişi adı gönderilmez: yalnız üst hedef, birim ve unvan."""
    ctx = []
    if parent:
        ctx.append(f"Bağlanacağı üst hedef: {parent['title']}" + (f" — {parent['description'][:600]}" if parent.get("description") else ""))
    if unit_name:
        ctx.append(f"Birim: {unit_name}")
    if title:
        ctx.append(f"Görev/unvan: {title}")
    if hint:
        ctx.append(f"Yöneticinin notu: {hint[:600]}")
    return [
        {"role": "system", "content": "Bir yayınevinin İK uzmanısın. Kısa, ölçülebilir, çeyrekte ya da yılda izlenebilir hedef taslakları "
                                      "yazarsın. Rakam uydurmazsın: hedef değer bilinmiyorsa «hedef değer: yönetici belirler» yazarsın."},
        {"role": "user", "content": "\n".join(ctx) + "\n\nBu bağlamda 3 hedef taslağı yaz. Her biri JSON nesnesi olsun: "
                                                     '{"title": "...", "measure": "nasıl ölçülür", "target": "hedef değer ya da boş"}. '
                                                     "Yalnız JSON dizisi döndür."},
    ]


def parse_drafts(text: str) -> list[dict[str, str]]:
    m = re.search(r"\[.*\]", text or "", re.S)
    try:
        arr = json.loads(m.group(0)) if m else []
    except ValueError:
        arr = []
    out = []
    for x in arr if isinstance(arr, list) else []:
        if isinstance(x, dict) and clean(x.get("title"), 300):
            out.append({"title": clean(x.get("title"), 300), "measure": clean(x.get("measure"), 400),
                        "target": clean(x.get("target"), 100)})
    return out[:6]


# ------------------------------------------------------------------ form şablonları


def _form_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "version": r.version, "sections": load(r.sections_json, []),
            "overallLabels": load(r.overall_labels_json, None) or DEFAULT_OVERALL, "state": r.state,
            "stateLabel": FORM_STATES.get(r.state, r.state), "updatedBy": r.updated_by, "updatedAt": iso(r.updated_at)}


def list_forms(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        return [_form_out(r) for r in c.execute(sa.select(FORMS).where(FORMS.c.tenant_id == tenant).order_by(FORMS.c.name)).all()]


def _clean_sections(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise HrError("Formda en az bir bölüm olmalı.")
    out = []
    for i, s in enumerate(raw, 1):
        if not isinstance(s, dict):
            continue
        kind = str(s.get("kind") or "acik")
        if kind not in SECTION_KINDS:
            raise HrError(f"Bölüm türü geçersiz: {kind}")
        title = clean(s.get("title"), 200)
        if not title:
            raise HrError(f"{i}. bölümün başlığı boş.")
        key = re.sub(r"[^a-z0-9_]", "", str(s.get("key") or f"b{i}").lower())[:30] or f"b{i}"
        items = []
        if kind == "yetkinlik":
            for j, it in enumerate(s.get("items") or [], 1):
                label = clean(it.get("label") if isinstance(it, dict) else it, 300)
                if label:
                    ik = re.sub(r"[^a-z0-9_]", "", str((it.get("key") if isinstance(it, dict) else "") or f"{key}_{j}").lower())[:40]
                    items.append({"key": ik or f"{key}_{j}", "label": label})
            if not items:
                raise HrError(f"«{title}» yetkinlik bölümünde madde yok.")
        out.append({"key": key, "title": title, "kind": kind, "items": items, "help": clean(s.get("help"), 400)})
    keys = [s["key"] for s in out] + [it["key"] for s in out for it in s["items"]]
    if len(keys) != len(set(keys)):
        raise HrError("Bölüm ve madde anahtarları tekrar ediyor.")
    return out


def save_form(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any], fid: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Form şablonu; bölümler değişince sürüm artar (açık dönemler kendi kopyasını taşır)."""
    ensure(engine)
    with engine.begin() as c:
        before = c.execute(sa.select(FORMS).where(FORMS.c.id == fid, FORMS.c.tenant_id == tenant)).first() if fid else None
        if fid and before is None:
            raise HrError("Form bulunamadı.", 404)
        name = clean(body.get("name", before.name if before is not None else ""), 200)
        if not name:
            raise HrError("Formun adı boş olamaz.")
        sections = _clean_sections(body["sections"]) if "sections" in body or before is None else load(before.sections_json, [])
        labels = body.get("overallLabels")
        if labels is not None:
            labels = [clean(x, 80) for x in labels] if isinstance(labels, list) else []
            if len(labels) != 5 or not all(labels):
                raise HrError("Genel değerlendirme ölçeği 5 etiket olmalı.")
        state = str(body.get("state") or (before.state if before is not None else "taslak"))
        if state not in FORM_STATES:
            raise HrError("Form durumu geçersiz.")
        t = now()
        if before is None:
            fid = new_id("form")
            c.execute(FORMS.insert().values(id=fid, tenant_id=tenant, name=name, version=1, sections_json=dump(sections),
                                            overall_labels_json=dump(labels) if labels else None, state=state, created_by=actor,
                                            updated_by=actor, updated_at=t))
            diff = {"yeni": name}
        else:
            changed = dump(sections) != before.sections_json or (labels is not None and dump(labels) != before.overall_labels_json)
            vals = dict(name=name, sections_json=dump(sections), state=state, updated_by=actor, updated_at=t,
                        version=before.version + (1 if changed else 0))
            if labels is not None:
                vals["overall_labels_json"] = dump(labels)
            c.execute(FORMS.update().where(FORMS.c.id == fid).values(**vals))
            diff = {k: v for k, v in (("ad", name != before.name), ("bolumler", changed), ("durum", state != before.state)) if v}
        r = c.execute(sa.select(FORMS).where(FORMS.c.id == fid)).first()
    return _form_out(r), diff


#: Başlangıç formu: İK düzeltip yürürlüğe alır (kısa tutuldu — uzmanın «30 alanlı form» tuzağı).
STARTER_FORM = {
    "name": "Yıllık değerlendirme (kısa)",
    "sections": [
        {"key": "hedef", "title": "Dönemin hedefleri", "kind": "hedef", "help": "Hedeflerin ilerlemesi ve check-in notları üzerinden"},
        {"key": "yetkinlik", "title": "Yetkinlikler", "kind": "yetkinlik", "items": [
            {"key": "is_kalitesi", "label": "İşin kalitesi ve doğruluğu"},
            {"key": "zaman", "label": "Terminlere uyum ve önceliklendirme"},
            {"key": "isbirligi", "label": "Birimler arası işbirliği ve iletişim"},
            {"key": "gelisim", "label": "Öğrenme ve kendini geliştirme"}]},
        {"key": "guclu", "title": "Güçlü yönler ve somut örnekler", "kind": "acik"},
        {"key": "gelisim_alani", "title": "Gelişim alanları ve gelişim planı", "kind": "acik",
         "help": "Burada yazılan gelişim maddeleri eğitim ihtiyacı olarak İK'ya gider"},
    ],
}


# ------------------------------------------------------------------ dönemler


def _cycle_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "periodStart": iso(r.period_start), "periodEnd": iso(r.period_end),
            "startsOn": iso(r.starts_on), "endsOn": iso(r.ends_on), "selfDue": iso(r.self_due), "managerDue": iso(r.manager_due),
            "formTemplateId": r.form_template_id, "form": load(r.form_snapshot_json, None), "audience": load(r.audience_json, {}),
            "state": r.state, "stateLabel": CYCLE_STATES.get(r.state, r.state), "createdBy": r.created_by,
            "updatedAt": iso(r.updated_at), "closedAt": iso(r.closed_at)}


def list_cycles(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        return [_cycle_out(r) for r in c.execute(sa.select(CYCLES).where(CYCLES.c.tenant_id == tenant)
                                                  .order_by(CYCLES.c.starts_on.desc())).all()]


def _cycle_row(c: Any, tenant: str, cid: str) -> Any:
    r = c.execute(sa.select(CYCLES).where(CYCLES.c.id == cid, CYCLES.c.tenant_id == tenant)).first()
    if r is None:
        raise HrError("Değerlendirme dönemi bulunamadı.", 404)
    return r


def save_cycle(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any], cid: Optional[str] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure(engine)
    with engine.begin() as c:
        before = _cycle_row(c, tenant, cid) if cid else None
        if before is not None and before.state not in ("hazirlik", "acik"):
            raise HrError("Kalibrasyondaki ya da kapanmış dönem düzenlenmez.", 409)

        def d(key: str, col: str, what: str, required: bool = True) -> Optional[date]:
            v = H.parse_date(body[key], what) if key in body else (getattr(before, col) if before is not None else None)
            if required and v is None:
                raise HrError(f"{what} tarihini girin.")
            return v

        name = clean(body.get("name", before.name if before is not None else ""), 200)
        if not name:
            raise HrError("Dönemin adı boş olamaz.")
        ps, pe = d("periodStart", "period_start", "Değerlendirilen dönemin başı"), d("periodEnd", "period_end", "Değerlendirilen dönemin sonu")
        so, eo = d("startsOn", "starts_on", "Form açılış"), d("endsOn", "ends_on", "Form kapanış")
        sd, md = d("selfDue", "self_due", "Öz değerlendirme son", False), d("managerDue", "manager_due", "Yönetici değerlendirmesi son", False)
        if ps > pe or so > eo:
            raise HrError("Başlangıç tarihi bitişten sonra olamaz.")
        for x, what in ((sd, "Öz değerlendirme"), (md, "Yönetici değerlendirmesi")):
            if x and not so <= x <= eo:
                raise HrError(f"{what} son tarihi form aralığının içinde olmalı.")
        form_id = body.get("formTemplateId", before.form_template_id if before is not None else None) or None
        if form_id and not c.execute(sa.select(FORMS.c.id).where(FORMS.c.id == form_id, FORMS.c.tenant_id == tenant)).first():
            raise HrError("Form bulunamadı.")
        units = body.get("units") if "units" in body else (load(before.audience_json, {}) or {}).get("units") if before is not None else None
        units = [u for u in (units or []) if isinstance(u, str)]
        if units and before is not None and before.state != "hazirlik":
            raise HrError("Açılmış dönemin hedef kitlesi değişmez; yeni katılanlar «katılımcıları eşitle» ile eklenir.", 409)
        vals = dict(name=name, period_start=ps, period_end=pe, starts_on=so, ends_on=eo, self_due=sd, manager_due=md,
                    form_template_id=form_id, audience_json=dump({"units": units} if units else {}), updated_by=actor, updated_at=now())
        if before is not None and before.state != "hazirlik" and form_id != before.form_template_id:
            raise HrError("Açılmış dönemin formu değişmez.", 409)
        if before is None:
            cid = new_id("dnm")
            c.execute(CYCLES.insert().values(id=cid, tenant_id=tenant, state="hazirlik", created_by=actor, created_at=now(), **vals))
            diff = {"yeni": name}
        else:
            diff = {k: {"once": iso(getattr(before, k)) if isinstance(getattr(before, k), date) else getattr(before, k),
                        "sonra": iso(v) if isinstance(v, date) else v}
                    for k, v in vals.items() if k not in ("updated_by", "updated_at") and getattr(before, k) != v}
            c.execute(CYCLES.update().where(CYCLES.c.id == cid).values(**vals))
        r = c.execute(sa.select(CYCLES).where(CYCLES.c.id == cid)).first()
    return _cycle_out(r), diff


def _audience(sc: Scope, audience: dict[str, Any]) -> list[Any]:
    units = audience.get("units") or []
    allowed: Optional[set[str]] = None
    if units:
        allowed = set()
        for u in units:
            allowed |= sc.unit_subtree(u)
    return [e for e in sc.emp.values() if e.status == "aktif" and (allowed is None or e.unit_id in allowed)]


def sync_participants(engine: sa.engine.Engine, tenant: str, sc: Scope, cid: str) -> dict[str, int]:
    """Hedef kitledeki aktif çalışanlar için değerlendirme kaydı açar (var olana dokunmaz). Yönetici çalışan kaydından."""
    ensure(engine)
    added = 0
    with engine.begin() as c:
        cy = _cycle_row(c, tenant, cid)
        if cy.state not in ("acik",):
            raise HrError("Katılımcılar yalnız açık dönemde eşitlenir.", 409)
        have = {r[0] for r in c.execute(sa.select(REVIEWS.c.employee_id).where(REVIEWS.c.cycle_id == cid)).all()}
        for e in _audience(sc, load(cy.audience_json, {})):
            if e.id in have:
                continue
            c.execute(REVIEWS.insert().values(id=new_id("dgr"), tenant_id=tenant, cycle_id=cid, employee_id=e.id,
                                              manager_id=e.manager_id, objection=False, updated_at=now()))
            added += 1
    return {"added": added}


def cycle_transition(engine: sa.engine.Engine, tenant: str, sc: Scope, cid: str, action: str) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        cy = _cycle_row(c, tenant, cid)
        t = now()
        if action == "open" and cy.state == "hazirlik":
            if not cy.form_template_id:
                raise HrError("Önce bir form seçin.")
            f = c.execute(sa.select(FORMS).where(FORMS.c.id == cy.form_template_id)).first()
            if f is None or f.state != "yururlukte":
                raise HrError("Dönem yalnız yürürlükteki bir formla açılır.")
            vals = dict(state="acik", form_snapshot_json=dump(_form_out(f)))
        elif action == "calibrate" and cy.state == "acik":
            vals = dict(state="kalibrasyon")
        elif action == "reopen" and cy.state == "kalibrasyon":
            vals = dict(state="acik")
        elif action == "close" and cy.state in ("acik", "kalibrasyon"):
            vals = dict(state="kapandi", closed_at=t)
        else:
            raise HrError(f"Dönemde «{action}» şu durumda ({CYCLE_STATES.get(cy.state, cy.state)}) yapılamaz.", 409)
        c.execute(CYCLES.update().where(CYCLES.c.id == cid).values(updated_by=sc.who.user, updated_at=t, **vals))
    out: dict[str, Any] = {}
    if action == "open":
        out = sync_participants(engine, tenant, sc, cid)
    with engine.connect() as c:
        return {**_cycle_out(_cycle_row(c, tenant, cid)), **out}


def review_state(r: Any) -> str:
    if r.hr_approved_at:
        return "onaylandi"
    if r.commented_at:
        return "ik_onayi"
    if r.shared_at:
        return "calisan_yorumu"
    if r.manager_submitted_at:
        return "gorusme"
    if r.self_submitted_at:
        return "yonetici"
    return "oz_degerlendirme"


def cycle_status(engine: sa.engine.Engine, tenant: str, sc: Scope, cid: str) -> dict[str, Any]:
    """Tamamlanma panosu. Oranların payı/paydası kabul betiğinin doğrudan SQL'iyle aynı tanım: bütün dönem satırları."""
    ensure(engine)
    with engine.connect() as c:
        cy = _cycle_row(c, tenant, cid)
        rows = c.execute(sa.select(REVIEWS).where(REVIEWS.c.cycle_id == cid)).all()
    total = len(rows)
    self_done = sum(1 for r in rows if r.self_submitted_at)
    mgr_done = sum(1 for r in rows if r.manager_submitted_at)
    by_unit: dict[str, dict[str, Any]] = {}
    people = []
    for r in rows:
        e = sc.emp.get(r.employee_id)
        uid = e.unit_id if e else None
        u = by_unit.setdefault(uid or "", {"unitId": uid, "unitName": sc.unit_name(uid) or "Birimsiz", "total": 0, "self": 0, "manager": 0, "approved": 0})
        u["total"] += 1
        u["self"] += bool(r.self_submitted_at)
        u["manager"] += bool(r.manager_submitted_at)
        u["approved"] += bool(r.hr_approved_at)
        people.append({"reviewId": r.id, "employeeId": r.employee_id, "name": sc.name(r.employee_id), "unitName": sc.unit_name(uid),
                       "managerId": r.manager_id, "managerName": sc.name(r.manager_id), "state": review_state(r),
                       "stateLabel": REVIEW_STATES[review_state(r)], "objection": bool(r.objection)})
    return {
        "cycle": _cycle_out(cy), "total": total, "selfDone": self_done, "managerDone": mgr_done,
        "selfRate": (self_done / total) if total else None, "managerRate": (mgr_done / total) if total else None,
        "shared": sum(1 for r in rows if r.shared_at), "approved": sum(1 for r in rows if r.hr_approved_at),
        "objections": sum(1 for r in rows if r.objection), "noManager": sum(1 for r in rows if not r.manager_id),
        "units": sorted(by_unit.values(), key=lambda x: x["unitName"].casefold()),
        "people": sorted(people, key=lambda x: ((x["unitName"] or "").casefold(), (x["name"] or "").casefold())),
    }


def hierarchy_gaps(sc: Scope) -> list[dict[str, Any]]:
    """Yöneticisi kayıtlı olmayan aktif çalışanlar (Ekibim ve dönem kapsamı bunlarda boş kalır)."""
    return sorted(({"id": e.id, "name": e.display_name, "unitName": sc.unit_name(e.unit_id)} for e in sc.emp.values()
                   if e.status == "aktif" and not e.manager_id), key=lambda x: x["name"].casefold())


def calibration(engine: sa.engine.Engine, tenant: str, sc: Scope, cid: str) -> dict[str, Any]:
    """Birim × yöneticinin verdiği genel puan dağılımı. Sistem puan üretmez; kişi adları yalnız bu yetkide."""
    ensure(engine)
    with engine.connect() as c:
        cy = _cycle_row(c, tenant, cid)
        rows = c.execute(sa.select(REVIEWS).where(REVIEWS.c.cycle_id == cid, REVIEWS.c.manager_submitted_at.isnot(None))).all()
    labels = (load(cy.form_snapshot_json, {}) or {}).get("overallLabels") or DEFAULT_OVERALL
    units: dict[str, dict[str, Any]] = {}
    overall = [0, 0, 0, 0, 0]
    for r in rows:
        score = (load(r.manager_json, {}) or {}).get("overall")
        if not isinstance(score, int) or not 1 <= score <= 5:
            continue
        e = sc.emp.get(r.employee_id)
        uid = (e.unit_id if e else None) or ""
        u = units.setdefault(uid, {"unitId": uid or None, "unitName": sc.unit_name(uid) or "Birimsiz", "counts": [0, 0, 0, 0, 0], "people": []})
        u["counts"][score - 1] += 1
        overall[score - 1] += 1
        u["people"].append({"reviewId": r.id, "name": sc.name(r.employee_id), "score": score, "managerName": sc.name(r.manager_id)})
    for u in units.values():
        n = sum(u["counts"])
        u["n"] = n
        u["mean"] = round(sum((i + 1) * k for i, k in enumerate(u["counts"])) / n, 2) if n else None
        u["people"].sort(key=lambda x: (-x["score"], (x["name"] or "").casefold()))
    n_all = sum(overall)
    return {"cycle": _cycle_out(cy), "labels": labels, "overall": overall, "n": n_all,
            "mean": round(sum((i + 1) * k for i, k in enumerate(overall)) / n_all, 2) if n_all else None,
            "units": sorted(units.values(), key=lambda x: x["unitName"].casefold())}


# ------------------------------------------------------------------ değerlendirmeler


def _review_row(c: Any, tenant: str, rid: str) -> Any:
    r = c.execute(sa.select(REVIEWS).where(REVIEWS.c.id == rid, REVIEWS.c.tenant_id == tenant)).first()
    if r is None:
        raise HrError("Değerlendirme bulunamadı.", 404)
    return r


def review_role(sc: Scope, r: Any) -> str:
    """self | manager (doğrudan değerlendiren) | chain (üst yönetici) | hr (İK/GM) | none."""
    if r.employee_id == sc.me_id:
        return "self"
    if r.manager_id and r.manager_id == sc.me_id:
        return "manager"
    if sc.all:
        return "hr"
    if r.employee_id in sc.team:
        return "chain"
    return "none"


def get_review(engine: sa.engine.Engine, tenant: str, sc: Scope, rid: str, *, log_view: bool = True) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = _review_row(c, tenant, rid)
        cy = _cycle_row(c, tenant, r.cycle_id)
        role = review_role(sc, r)
        if role == "none":
            raise deny(engine, tenant, sc, r.employee_id, "performans değerlendirmesi")
        goals = c.execute(sa.select(GOALS).where(GOALS.c.tenant_id == tenant, GOALS.c.owner_employee_id == r.employee_id,
                                                 GOALS.c.level == "kisi", GOALS.c.state.in_(("yururlukte", "kapandi")))).all()
        period_goals = []
        for g in goals:
            gs, ge = period_range(g.period)
            if ge < cy.period_start or gs > cy.period_end:
                continue
            last = c.execute(sa.select(CHECKINS).where(CHECKINS.c.goal_id == g.id).order_by(CHECKINS.c.at.desc()).limit(1)).first()
            period_goals.append(_goal_out(g, sc, last))
        summaries = c.execute(sa.select(WORK).where(WORK.c.tenant_id == tenant, WORK.c.employee_id == r.employee_id,
                                                    WORK.c.cycle_id == r.cycle_id).order_by(WORK.c.generated_at.desc())).all()
    if log_view and role != "self":
        H.log_access(engine, tenant, sc.who.user, "calisan", r.employee_id, "goruntule", "performans değerlendirmesi")
    see_manager = role != "self" or r.shared_at is not None
    state = review_state(r)
    cycle_open = cy.state in ("acik", "kalibrasyon")
    return {
        "id": r.id, "cycle": _cycle_out(cy), "employeeId": r.employee_id, "employeeName": sc.name(r.employee_id),
        "unitName": sc.unit_name((sc.emp.get(r.employee_id) or _Empty).unit_id), "title": (sc.emp.get(r.employee_id) or _Empty).title,
        "managerId": r.manager_id, "managerName": sc.name(r.manager_id), "role": role, "state": state, "stateLabel": REVIEW_STATES[state],
        "self": load(r.self_json, {}) or {}, "selfSubmittedAt": iso(r.self_submitted_at),
        "manager": (load(r.manager_json, {}) or {}) if see_manager else None, "managerSubmittedAt": iso(r.manager_submitted_at),
        "sharedAt": iso(r.shared_at), "meetingAt": iso(r.meeting_at), "employeeComment": r.employee_comment or "",
        "objection": bool(r.objection), "commentedAt": iso(r.commented_at), "hrApprovedBy": r.hr_approved_by,
        "hrApprovedAt": iso(r.hr_approved_at), "hrNote": r.hr_note or "", "goals": period_goals,
        "workSummaries": [_work_out(w) for w in summaries],
        "can": {
            "editSelf": role == "self" and cycle_open and not r.self_submitted_at,
            "editManager": role == "manager" and sc.who.can(F_REVIEW_WRITE) and cycle_open and not r.shared_at,
            "share": role == "manager" and bool(r.manager_submitted_at) and not r.shared_at and cycle_open,
            "comment": role == "self" and bool(r.shared_at) and not r.commented_at and not r.hr_approved_at,
            "approve": sc.who.can(F_REVIEW_APPROVE) and r.manager_id != sc.me_id and bool(r.shared_at) and not r.hr_approved_at,
            "reassign": sc.who.can(F_REVIEW_APPROVE, F_CYCLE) and not r.hr_approved_at,
            "workSummary": role in ("manager", "chain", "hr") and sc.who.can(F_WORK),
            "rewrite": role == "manager" and sc.who.can(F_REVIEW_WRITE) and not r.shared_at,
        },
    }


class _Empty:
    unit_id = None
    title = ""


def _clean_answers(form: dict[str, Any], raw: Any, *, with_overall: bool) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    ratings_in = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
    notes_in = raw.get("notes") if isinstance(raw.get("notes"), dict) else {}
    ratings, notes = {}, {}
    for s in (form or {}).get("sections") or []:
        for it in s.get("items") or []:
            v = ratings_in.get(it["key"])
            if v in (None, ""):
                continue
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise HrError(f"«{it['label']}» puanı 1–5 olmalı.") from None
            if not 1 <= v <= 5:
                raise HrError(f"«{it['label']}» puanı 1–5 olmalı.")
            ratings[it["key"]] = v
        txt = str(notes_in.get(s["key"]) or "").strip()[:6000]
        if txt:
            notes[s["key"]] = txt
    out: dict[str, Any] = {"ratings": ratings, "notes": notes}
    if with_overall:
        ov = raw.get("overall")
        if ov not in (None, ""):
            try:
                ov = int(ov)
            except (TypeError, ValueError):
                raise HrError("Genel değerlendirme 1–5 olmalı.") from None
            if not 1 <= ov <= 5:
                raise HrError("Genel değerlendirme 1–5 olmalı.")
            out["overall"] = ov
    return out


def save_review(engine: sa.engine.Engine, tenant: str, sc: Scope, rid: str, body: dict[str, Any], *, submit: str = "") -> dict[str, Any]:
    """Taslak kaydı (`self` ya da `manager` gövdesi) ve teslim (`submit` = self | manager)."""
    ensure(engine)
    with engine.begin() as c:
        r = _review_row(c, tenant, rid)
        cy = _cycle_row(c, tenant, r.cycle_id)
        role = review_role(sc, r)
        if role == "none":
            raise deny(engine, tenant, sc, r.employee_id, "performans değerlendirmesi")
        if cy.state not in ("acik", "kalibrasyon"):
            raise HrError("Dönem açık değil; değerlendirme yazılamaz.", 409)
        form = load(cy.form_snapshot_json, {}) or {}
        vals: dict[str, Any] = {}
        t = now()
        if "self" in body or submit == "self":
            if role != "self":
                raise HrError("Öz değerlendirmeyi yalnız çalışanın kendisi yazar.", 403)
            if r.self_submitted_at:
                raise HrError("Öz değerlendirme teslim edildi; değişmez.", 409)
            if "self" in body:
                vals["self_json"] = dump(_clean_answers(form, body.get("self"), with_overall=False))
            if submit == "self":
                vals["self_submitted_at"] = t
        if "manager" in body or submit == "manager":
            if role != "manager" or not sc.who.can(F_REVIEW_WRITE):
                raise HrError("Yönetici bölümünü yalnız çalışanın kayıtlı yöneticisi (değerlendirme yetkisiyle) yazar.", 403)
            if r.shared_at:
                raise HrError("Değerlendirme çalışanla paylaşıldı; değişmez.", 409)
            data = _clean_answers(form, body["manager"], with_overall=True) if "manager" in body else (load(r.manager_json, {}) or {})
            if "manager" in body:
                vals["manager_json"] = dump(data)
            if submit == "manager":
                if not data.get("overall"):
                    raise HrError("Teslim etmeden önce genel değerlendirmeyi seçin.")
                vals["manager_submitted_at"] = t
        if not vals:
            raise HrError("Kaydedilecek bir şey yok.")
        c.execute(REVIEWS.update().where(REVIEWS.c.id == rid).values(updated_at=t, **vals))
    return get_review(engine, tenant, sc, rid, log_view=False)


def review_action(engine: sa.engine.Engine, tenant: str, sc: Scope, rid: str, action: str, body: dict[str, Any]) -> dict[str, Any]:
    """share (yönetici, görüşme tarihiyle) · comment (çalışan; itiraz işaretli olabilir) · approve (İK) · reassign (yönetici değişir)."""
    ensure(engine)
    rv = get_review(engine, tenant, sc, rid, log_view=False)
    can = rv["can"]
    t = now()
    if action == "share":
        if not can["share"]:
            raise HrError("Paylaşım yalnız teslim edilmiş değerlendirmede, yöneticisi tarafından yapılır.", 403)
        meeting = H.aware(body.get("meetingAt")) if body.get("meetingAt") else None
        vals: dict[str, Any] = dict(shared_at=t, meeting_at=meeting)
    elif action == "comment":
        if not can["comment"]:
            raise HrError("Yorum yalnız paylaşılan değerlendirmede, çalışanın kendisi tarafından bir kez yazılır.", 403)
        text = str(body.get("comment") or "").strip()[:6000]
        objection = bool(body.get("objection"))
        if objection and not text:
            raise HrError("İtirazın gerekçesini yazın.")
        vals = dict(employee_comment=text or None, objection=objection, commented_at=t)
    elif action == "approve":
        if not can["approve"]:
            raise HrError("Onay İK'nındır; değerlendirmeyi yazan yönetici onaylayamaz ve paylaşılmamış değerlendirme onaylanmaz.", 403)
        vals = dict(hr_approved_by=sc.who.user, hr_approved_at=t, hr_note=clean(body.get("note"), 2000) or None)
    elif action == "reassign":
        if not can["reassign"]:
            raise HrError("Değerlendiren yöneticiyi yalnız İK değiştirir.", 403)
        mid = body.get("managerId") or None
        if mid and mid not in sc.emp:
            raise HrError("Yönetici çalışan kaydında yok.")
        if mid == rv["employeeId"]:
            raise HrError("Çalışan kendi yöneticisi olamaz.")
        vals = dict(manager_id=mid)
        if rv["sharedAt"] is None:
            vals.update(manager_submitted_at=None)
    else:
        raise HrError("Bilinmeyen işlem.", 404)
    with engine.begin() as c:
        c.execute(REVIEWS.update().where(REVIEWS.c.id == rid).values(updated_at=t, **vals))
    return get_review(engine, tenant, sc, rid, log_view=False)


# ------------------------------------------------------------------ iş kayıtları özeti


def _work_out(w: Any) -> dict[str, Any]:
    return {"id": w.id, "periodStart": iso(w.period_start), "periodEnd": iso(w.period_end), "generatedAt": iso(w.generated_at),
            "generatedBy": w.generated_by, "facts": load(w.facts_json, {}), "text": w.text,
            "shownToEmployeeAt": iso(w.shown_to_employee_at)}


def work_text(facts: dict[str, Any]) -> str:
    """Sayılardan sabit kalıpla cümle. Yorum ve puan yok; model kullanılmaz (rakam modelden gelmez)."""
    parts = []
    ed = facts.get("editorial") or {}
    if ed.get("available"):
        if ed.get("done"):
            parts.append(f"Dönemde portalda {ed['done']} editörlük görevi tamamlandı; terminli olanlardan {ed.get('onTime', 0)} tanesi "
                         f"termininde ya da önce bitti ({ed.get('withDue', 0)} terminli görev).")
        else:
            parts.append("Dönemde portalda tamamlanan editörlük görevi yok.")
        if ed.get("openOverdue"):
            parts.append(f"Dönem sonunda termini geçmiş ve açık {ed['openOverdue']} görev vardı.")
    crm = facts.get("crm") or {}
    if crm.get("available"):
        parts.append(f"CRM'de bu dönemde sahibi olduğu {crm.get('projects', 0)} proje ve {crm.get('contracts', 0)} sözleşme kaydı açıldı "
                     "(toplu kayıtlar servis hesabında birikebildiği için bu sayı iş hacmini tam göstermez).")
    elif crm.get("reason"):
        parts.append(f"CRM sahiplik sayıları okunamadı: {crm['reason']}")
    if not parts:
        parts.append("Bu dönem için sistemde bu kişiye bağlanan bir iş kaydı bulunamadı.")
    parts.append("Bu özet bilgi amaçlıdır; puan ya da değerlendirme değildir. Çalışan aynı özeti kendi ekranında görür.")
    return " ".join(parts)


def save_work_summary(engine: sa.engine.Engine, tenant: str, actor: str, employee_id: str, cycle_id: Optional[str],
                      start: date, end: date, facts: dict[str, Any]) -> dict[str, Any]:
    ensure(engine)
    wid = new_id("ozet")
    with engine.begin() as c:
        c.execute(WORK.insert().values(id=wid, tenant_id=tenant, employee_id=employee_id, cycle_id=cycle_id, period_start=start,
                                       period_end=end, generated_at=now(), generated_by=actor, facts_json=dump(facts), text=work_text(facts)))
        return _work_out(c.execute(sa.select(WORK).where(WORK.c.id == wid)).first())


# ------------------------------------------------------------------ Performansım ve Ekibim


def me_view(engine: sa.engine.Engine, tenant: str, sc: Scope) -> dict[str, Any]:
    ensure(engine)
    if not sc.me_id:
        return {"employee": None, "goals": [], "reviews": [], "workSummaries": [], "tasks": []}
    goals = list_goals(engine, tenant, sc, owner=sc.me_id)
    with engine.begin() as c:
        rows = c.execute(sa.select(REVIEWS, CYCLES.c.name, CYCLES.c.state.label("cycle_state"), CYCLES.c.self_due, CYCLES.c.ends_on)
                         .join(CYCLES, CYCLES.c.id == REVIEWS.c.cycle_id)
                         .where(REVIEWS.c.tenant_id == tenant, REVIEWS.c.employee_id == sc.me_id)
                         .order_by(CYCLES.c.starts_on.desc())).all()
        works = c.execute(sa.select(WORK).where(WORK.c.tenant_id == tenant, WORK.c.employee_id == sc.me_id)
                          .order_by(WORK.c.generated_at.desc())).all()
        # Çalışan kendi özetini gördü: ilk görüntüleme anı yazılır (KVKK md. 11 — hakkında kullanılan veri).
        unseen = [w.id for w in works if w.shown_to_employee_at is None]
        if unseen:
            c.execute(WORK.update().where(WORK.c.id.in_(unseen)).values(shown_to_employee_at=now()))
    tasks, reviews = [], []
    today = date.today()
    for r in rows:
        st = review_state(r)
        reviews.append({"id": r.id, "cycleName": r.name, "cycleState": r.cycle_state, "state": st, "stateLabel": REVIEW_STATES[st],
                        "selfDue": iso(r.self_due), "sharedAt": iso(r.shared_at)})
        if r.cycle_state == "acik" and not r.self_submitted_at:
            due = r.self_due or r.ends_on
            tasks.append({"kind": "oz", "reviewId": r.id, "label": f"{r.name}: öz değerlendirme", "due": iso(due),
                          "daysLeft": (due - today).days if due else None})
        if r.shared_at and not r.commented_at and not r.hr_approved_at:
            tasks.append({"kind": "yorum", "reviewId": r.id, "label": f"{r.name}: yöneticinizin değerlendirmesi paylaşıldı", "due": None,
                          "daysLeft": None})
    for g in goals:
        if g["state"] == "yururlukte":
            _, end = period_range(g["period"])
            last = g["lastCheckin"]
            if last is None or H.aware(last["at"]).date() < end - timedelta(days=92):
                tasks.append({"kind": "checkin", "goalId": g["id"], "label": f"«{g['title']}» için check-in", "due": iso(end),
                              "daysLeft": (end - today).days})
    return {"employee": {"id": sc.me.id, "displayName": sc.me.display_name, "unitName": sc.unit_name(sc.me.unit_id),
                         "managerName": sc.name(sc.me.manager_id), "title": sc.me.title or ""},
            "goals": goals, "reviews": reviews, "workSummaries": [_work_out(w) for w in works], "tasks": tasks}


def team_view(engine: sa.engine.Engine, tenant: str, sc: Scope, *, direct_only: bool = False) -> dict[str, Any]:
    """Ekibim: yalnız manager_id zincirindeki kişiler (kabul 7: WITH RECURSIVE ile aynı küme)."""
    ensure(engine)
    ids = sorted(sc.direct if direct_only else sc.team)
    with engine.connect() as c:
        goals = c.execute(sa.select(GOALS).where(GOALS.c.tenant_id == tenant, GOALS.c.level == "kisi",
                                                 GOALS.c.owner_employee_id.in_(ids or [""]), GOALS.c.state.in_(("onayda", "yururlukte")))).all()
        gids = [g.id for g in goals] or [""]
        last: dict[str, Any] = {}
        for ck in c.execute(sa.select(CHECKINS).where(CHECKINS.c.goal_id.in_(gids)).order_by(CHECKINS.c.at)).all():
            last[ck.goal_id] = ck
        open_revs = {r.goal_id for r in c.execute(sa.select(REVISIONS.c.goal_id).where(REVISIONS.c.goal_id.in_(gids),
                                                                                        REVISIONS.c.decided_at.is_(None))).all()}
        reviews = c.execute(sa.select(REVIEWS, CYCLES.c.name, CYCLES.c.state.label("cycle_state"))
                            .join(CYCLES, CYCLES.c.id == REVIEWS.c.cycle_id)
                            .where(REVIEWS.c.employee_id.in_(ids or [""]), CYCLES.c.state.in_(("acik", "kalibrasyon")))).all()
    people = []
    for eid in ids:
        e = sc.emp[eid]
        if e.status != "aktif":
            continue
        mine = [g for g in goals if g.owner_employee_id == eid]
        pct = [last[g.id].progress_pct for g in mine if g.id in last and last[g.id].progress_pct is not None]
        people.append({
            "id": eid, "name": e.display_name, "title": e.title or "", "unitName": sc.unit_name(e.unit_id), "direct": eid in sc.direct,
            "managerName": sc.name(e.manager_id), "goals": len(mine), "pendingApproval": sum(1 for g in mine if g.state == "onayda"),
            "openRevisions": sum(1 for g in mine if g.id in open_revs),
            "noCheckin": sum(1 for g in mine if g.state == "yururlukte" and g.id not in last),
            "avgProgress": round(sum(pct) / len(pct)) if pct else None,
            "reviews": [{"id": r.id, "cycleName": r.name, "state": review_state(r), "stateLabel": REVIEW_STATES[review_state(r)],
                         "mine": r.manager_id == sc.me_id} for r in reviews if r.employee_id == eid],
        })
    people.sort(key=lambda x: (not x["direct"], x["name"].casefold()))
    return {"me": {"id": sc.me_id, "name": sc.me.display_name if sc.me else None}, "people": people,
            "gaps": hierarchy_gaps(sc) if sc.cycle_admin else None}


# ------------------------------------------------------------------ saklama ve imha


def due_purge(engine: sa.engine.Engine, tenant: str, at: datetime) -> list[str]:
    days = H.keep_days(engine, tenant, DATA_CLASS)
    if not days:
        return []
    ensure(engine)
    limit = (at - timedelta(days=days)).date()
    with engine.connect() as c:
        left = [r[0] for r in c.execute(sa.select(H.EMPLOYEES.c.id).where(
            H.EMPLOYEES.c.tenant_id == tenant, H.EMPLOYEES.c.status == "ayrildi", H.EMPLOYEES.c.end_date.isnot(None),
            H.EMPLOYEES.c.end_date < limit)).all()]
        if not left:
            return []
        has = set()
        for tbl, col in ((GOALS, GOALS.c.owner_employee_id), (REVIEWS, REVIEWS.c.employee_id), (WORK, WORK.c.employee_id)):
            has |= {r[0] for r in c.execute(sa.select(col).where(col.in_(left)).distinct()).all()}
    return sorted(has)


def purge(engine: sa.engine.Engine, tenant: str, ids: list[str], at: datetime) -> int:
    n = 0
    with engine.begin() as c:
        gids = [r[0] for r in c.execute(sa.select(GOALS.c.id).where(GOALS.c.tenant_id == tenant, GOALS.c.owner_employee_id.in_(ids))).all()]
        if gids:
            c.execute(CHECKINS.delete().where(CHECKINS.c.goal_id.in_(gids)))
            c.execute(REVISIONS.delete().where(REVISIONS.c.goal_id.in_(gids)))
            n += c.execute(GOALS.delete().where(GOALS.c.id.in_(gids))).rowcount or 0
        n += c.execute(REVIEWS.delete().where(REVIEWS.c.tenant_id == tenant, REVIEWS.c.employee_id.in_(ids))).rowcount or 0
        n += c.execute(WORK.delete().where(WORK.c.tenant_id == tenant, WORK.c.employee_id.in_(ids))).rowcount or 0
    return n


# ------------------------------------------------------------------ hatırlatma


def due_reminders(engine: sa.engine.Engine, tenant: str, days: Optional[int], today: Optional[date] = None) -> list[dict[str, Any]]:
    """Açık dönemlerde son tarihe `days` gün ya da daha az kalan eksikler (birim başına sayı; ad yok). Eşik yoksa boş."""
    if not days:
        return []
    ensure(engine)
    today = today or date.today()
    out = []
    with engine.connect() as c:
        for cy in c.execute(sa.select(CYCLES).where(CYCLES.c.tenant_id == tenant, CYCLES.c.state == "acik")).all():
            if cy.last_reminded_on == today:
                continue
            rows = c.execute(sa.select(REVIEWS).where(REVIEWS.c.cycle_id == cy.id)).all()
            item = {"cycleId": cy.id, "name": cy.name, "selfMissing": 0, "managerMissing": 0, "selfDue": iso(cy.self_due),
                    "managerDue": iso(cy.manager_due)}
            sd, md = cy.self_due or cy.ends_on, cy.manager_due or cy.ends_on
            if (sd - today).days <= days:
                item["selfMissing"] = sum(1 for r in rows if not r.self_submitted_at)
            if (md - today).days <= days:
                item["managerMissing"] = sum(1 for r in rows if not r.manager_submitted_at)
            if item["selfMissing"] or item["managerMissing"]:
                out.append(item)
    return out


def mark_reminded(engine: sa.engine.Engine, tenant: str, items: list[dict[str, Any]], today: Optional[date] = None) -> None:
    with engine.begin() as c:
        c.execute(CYCLES.update().where(CYCLES.c.tenant_id == tenant, CYCLES.c.id.in_([i["cycleId"] for i in items] or [""]))
                  .values(last_reminded_on=today or date.today()))


def reminder_text(items: list[dict[str, Any]], link: str) -> str:
    lines = ["Değerlendirme dönemi hatırlatması (kişi adı içermez):", ""]
    for i in items:
        lines.append(f"- {i['name']}: öz değerlendirmesi eksik {i['selfMissing']} kişi (son {i['selfDue'] or 'dönem sonu'}), "
                     f"yönetici değerlendirmesi eksik {i['managerMissing']} kişi (son {i['managerDue'] or 'dönem sonu'})")
    if link:
        lines += ["", f"Ayrıntı: {link}"]
    return "\n".join(lines)


def export_rows(engine: sa.engine.Engine, tenant: str, sc: Scope, cid: str) -> list[list[Any]]:
    """Dönem durum tablosu (dışa aktarma): kişi, birim, yönetici, durum, genel puan. Yorum metni yok."""
    st = cycle_status(engine, tenant, sc, cid)
    with engine.connect() as c:
        scores = {r.id: (load(r.manager_json, {}) or {}).get("overall") for r in c.execute(
            sa.select(REVIEWS.c.id, REVIEWS.c.manager_json).where(REVIEWS.c.cycle_id == cid, REVIEWS.c.manager_submitted_at.isnot(None))).all()}
    rows = [["Çalışan", "Birim", "Yönetici", "Durum", "Genel puan (yönetici)", "İtiraz"]]
    for p in st["people"]:
        rows.append([p["name"], p["unitName"] or "", p["managerName"] or "", p["stateLabel"], scores.get(p["reviewId"]) or "",
                     "evet" if p["objection"] else ""])
    return rows


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    def num(key: str) -> Optional[int]:
        try:
            n = int((conf(key) or "").strip())
        except ValueError:
            return None
        return n if n > 0 else None

    return {"logoSales": (conf("HR_PERF_LOGO_SALES") or "").strip() in ("1", "true", "evet"),
            "remindDays": num("HR_PERF_REMIND_DAYS")}
