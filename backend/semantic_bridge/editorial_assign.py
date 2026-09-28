"""M2 Editör atama: atama, kategori–editör kural tablosu, iş yükü, takvim çakışması ve editörün görev panosu.

CRM'de projenin editörü `new_projeBase.new_editoru` (SystemUser) alanıdır; CRM'e yazma yetkimiz yok. Bu yüzden
atama, termin, iş yükü ve takvim **köprünün kendi tablolarında** tutulur ve CRM'in üstüne bindirilir:

- **Görev** (`semantic_editorial_tasks`): bir projenin bir editördeki işi. Atamayla ya da editörün CRM'deki
  kendi projesini «panoma al» demesiyle doğar. Durum: sırada → çalışılıyor → beklemede → tamamlandı (ya da iptal).
  Termin, başlangıç ve tahmini sayfa görevin üstündedir; her değişiklik gerekçesiyle görev geçmişine yazılır.
- **Editör profili**: eşzamanlı görev kapasitesi (yükün paydası) ve «atamaya açık» bayrağı. Kapasite yazılmamışsa
  yüzde hesaplanmaz; ekran «kapasite girilmemiş» der.
- **İzin/müsait değil** aralıkları: takvimde görevle çakışırsa çakışma sayılır.
- **Kural tablosu** (sürümlü, onaylı): kategori (CRM «Kitaplık», yoksa marka/yayınevi) → birincil ve yedek
  editörler. Taslak yazılır, yetkili onaylayınca yürürlüğe girer; önceki sürüm arşivde kalır.

Kategori ölçümü (2026-09-27, 2024'ten beri 2.738 etkin proje): Kitaplık 1.341, marka 2.721 projede dolu; yayın
sınıfı, sorumlu departman, metin teslim ve hedef baskı tarihi (neredeyse) hiç dolu değil. Takvim bu yüzden CRM'den
değil görevin termininden kurulur.

Öneri kural, geçmiş ve müsaitlikten hesaplanır; her aday puanıyla birlikte gerekçesini taşır. Model kullanılmaz.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.editorial import (
    PAGE_SIZE, EditorialError, _date, _guid, _like, _n, _prefix, _s, _timing,
)

_md = sa.MetaData()

TASKS = sa.Table(
    "semantic_editorial_tasks", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("crm_project_id", sa.String(40), nullable=False, index=True),
    sa.Column("project_name", sa.String(300)),
    sa.Column("category", sa.String(200)),
    sa.Column("editor_id", sa.String(40), nullable=False, index=True),
    sa.Column("editor_name", sa.String(200)),
    sa.Column("role", sa.String(20), nullable=False),              # editor | destek
    sa.Column("status", sa.String(20), nullable=False),            # sirada | calisiyor | beklemede | tamamlandi | iptal
    sa.Column("source", sa.String(20), nullable=False),            # atama | crm
    sa.Column("start_date", sa.Date),
    sa.Column("due_date", sa.Date),
    sa.Column("pages", sa.Integer),
    sa.Column("note", sa.Text),
    sa.Column("crm_editor_id", sa.String(40)),                     # atama anında CRM'de yazan editör
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("done_at", sa.DateTime(timezone=True)),
)
TASK_LOG = sa.Table(
    "semantic_editorial_task_log", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("task_id", sa.String(32), nullable=False, index=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("actor", sa.String(120), nullable=False),
    sa.Column("action", sa.String(24), nullable=False),
    sa.Column("detail", sa.Text),
)
PROFILES = sa.Table(
    "semantic_editorial_editor_profiles", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("editor_id", sa.String(40), primary_key=True),
    sa.Column("editor_name", sa.String(200)),
    sa.Column("capacity", sa.Integer),
    sa.Column("available", sa.Boolean, nullable=False, default=True),
    sa.Column("note", sa.String(500)),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
ABSENCES = sa.Table(
    "semantic_editorial_absences", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("editor_id", sa.String(40), nullable=False, index=True),
    sa.Column("start_date", sa.Date, nullable=False),
    sa.Column("end_date", sa.Date, nullable=False),
    sa.Column("reason", sa.String(200)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
RULES = sa.Table(
    "semantic_editorial_rule_versions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("version", sa.Integer, nullable=False),
    sa.Column("state", sa.String(12), nullable=False),              # taslak | yururlukte | arsiv
    sa.Column("rules_json", sa.Text, nullable=False),
    sa.Column("note", sa.String(500)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
)

STATUSES = {"sirada": "Sırada", "calisiyor": "Çalışılıyor", "beklemede": "Beklemede", "tamamlandi": "Tamamlandı",
            "iptal": "İptal"}
OPEN = ("sirada", "calisiyor", "beklemede")
ROLES = {"editor": "Editör", "destek": "Destek editör"}

#: Editör bekleyen iş sayılan CRM proje durumları (statuscode). 2026-09-27 ölçümü, 2024'ten beri: «İş Planı
#: Çalışıyor» 1.259 (74 editörsüz), «(Basılacak) Yayın Kurulu Onaylı» 517 (278 editörsüz). Ekranda başka durum da
#: seçilebilir; bu yalnız ilk açılıştaki süzgeçtir.
WORK_STATUSES = (100000019, 100000020)

_ready: set[int] = set()
_lock = threading.Lock()


class AssignError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata. `data` 409 çakışmada ekrana giden ayrıntıdır."""

    def __init__(self, message: str, status: int = 400, data: Any = None):
        super().__init__(message)
        self.status = status
        self.data = data


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _now().date()


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v.isoformat() if isinstance(v, date) else str(v)


def _new() -> str:
    return uuid.uuid4().hex


def parse_day(v: Any, label: str = "Tarih") -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise AssignError(f"{label} geçerli değil (YYYY-AA-GG).") from None


def _id(v: Any, label: str = "Kimlik") -> str:
    s = str(v or "").strip().strip("{}")
    try:
        return _guid(s).upper()
    except EditorialError:
        raise AssignError(f"{label} geçerli değil.") from None


def _pages(v: Any) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise AssignError("Sayfa sayısı tam sayı olmalı.") from None
    if n < 0:
        raise AssignError("Sayfa sayısı eksi olamaz.")
    return n


def _text(v: Any, n: int) -> Optional[str]:
    t = str(v or "").strip()
    return t[:n] or None


# ================================================================================ CRM okumaları
# Hepsi köprünün run_sql yolundan geçer (yalnız SELECT, katalogdaki tablolar). Kimlikler GUID'e zorlanır.

def _in(ids: Iterable[str]) -> str:
    return ", ".join(f"'{_guid(i)}'" for i in ids)


def _codes(codes: Iterable[int]) -> str:
    return ", ".join(str(int(c)) for c in codes)


def _project_cols() -> str:
    return (
        "j.new_projeId, j.new_name, j.statuscode, CAST(j.statuscode AS int) AS kod, j.new_Kitaplik, k.new_name AS kitaplik,"
        " j.new_yayinciid, m.new_name AS marka, j.new_editoru, u.FullName AS editor, j.new_tahminisayfasayisi,"
        " j.new_yayinkuruluonaytarihi, j.new_hedeflenenbaskitarihi, j.CreatedOn, j.ModifiedOn,"
        " COALESCE(a.FullName, j.new_olasiyazartext) AS yazar"
    )


def _project_from(p: str) -> str:
    return (
        f" FROM {p}new_projeBase j"
        f" LEFT JOIN {p}new_kitaplikBase k ON k.new_kitaplikId = j.new_Kitaplik"
        f" LEFT JOIN {p}new_markaBase m ON m.new_markaId = j.new_yayinciid"
        f" LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = j.new_editoru"
        f" LEFT JOIN {p}ContactBase a ON a.ContactId = j.new_OlasYazarYazar"
    )


def _pending_where(*, statuses: Iterable[int], since_year: int, exclude: Iterable[str], q: str = "",
                   category: str = "") -> str:
    parts = ["j.statecode = 0", "j.new_editoru IS NULL", f"j.CreatedOn >= '{int(since_year):04d}-01-01'"]
    codes = list(statuses)
    if codes:
        parts.append(f"j.statuscode IN ({_codes(codes)})")
    ex = list(exclude)
    if ex:
        parts.append(f"j.new_projeId NOT IN ({_in(ex)})")
    if q.strip():
        k = _like(q)
        parts.append(f"(j.new_name LIKE N'%{k}%' OR j.new_olasiyazartext LIKE N'%{k}%' OR a.FullName LIKE N'%{k}%')")
    if category:
        kind, _, cid = category.partition(":")
        col = {"kitaplik": "j.new_Kitaplik", "marka": "j.new_yayinciid"}.get(kind)
        if not col:
            raise AssignError("Kategori süzgeci geçerli değil.")
        parts.append(f"{col} = '{_id(cid, 'Kategori')}'")
    return " AND ".join(parts)


def pending_count_sql(schema: str, **flt: Any) -> str:
    p = _prefix(schema)
    return f"SELECT COUNT(*) AS n{_project_from(p)} WHERE {_pending_where(**flt)}"


def pending_list_sql(schema: str, page: int, **flt: Any) -> str:
    p = _prefix(schema)
    return (
        f"SELECT {_project_cols()}{_project_from(p)} WHERE {_pending_where(**flt)}"
        " ORDER BY COALESCE(j.new_yayinkuruluonaytarihi, j.ModifiedOn) DESC, j.new_projeId"
        f" OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"
    )


def pending_facets_sql(schema: str, since_year: int, exclude: Iterable[str] = ()) -> str:
    """Editörsüz etkin projeler durum başına (ekrandaki durum süzgeci); açık görevi olanlar sayılmaz."""
    p = _prefix(schema)
    ex = list(exclude)
    return (
        "SELECT j.statuscode, CAST(j.statuscode AS int) AS kod, COUNT(*) AS n"
        f" FROM {p}new_projeBase j WHERE j.statecode = 0 AND j.new_editoru IS NULL"
        f" AND j.CreatedOn >= '{int(since_year):04d}-01-01'"
        + (f" AND j.new_projeId NOT IN ({_in(ex)})" if ex else "")
        + " GROUP BY j.statuscode ORDER BY COUNT(*) DESC"
    )


def projects_sql(schema: str, ids: list[str]) -> str:
    p = _prefix(schema)
    return f"SELECT {_project_cols()}{_project_from(p)} WHERE j.new_projeId IN ({_in(ids)})"


def experience_sql(schema: str, since_year: int) -> str:
    """Editör × kategori proje sayısı (öneri gerekçesi ve kural önerisi)."""
    p = _prefix(schema)
    return (
        "SELECT j.new_editoru, j.new_Kitaplik, k.new_name AS kitaplik, j.new_yayinciid, m.new_name AS marka, COUNT(*) AS n"
        f" FROM {p}new_projeBase j"
        f" LEFT JOIN {p}new_kitaplikBase k ON k.new_kitaplikId = j.new_Kitaplik"
        f" LEFT JOIN {p}new_markaBase m ON m.new_markaId = j.new_yayinciid"
        f" WHERE j.statecode = 0 AND j.new_editoru IS NOT NULL AND j.CreatedOn >= '{int(since_year):04d}-01-01'"
        " GROUP BY j.new_editoru, j.new_Kitaplik, k.new_name, j.new_yayinciid, m.new_name"
    )


_CATEGORY = {"kitaplik": ("new_kitaplikBase", "new_kitaplikId", "new_Kitaplik"),
             "marka": ("new_markaBase", "new_markaId", "new_yayinciid")}


def categories_sql(schema: str, since_year: int, kind: str) -> str:
    """Kural tablosunda seçilebilecek kategoriler: dönemde projesi olan kitaplık ya da markalar."""
    p = _prefix(schema)
    table, key, col = _CATEGORY[kind]
    return (
        f"SELECT CAST(c.{key} AS nvarchar(40)) AS kimlik, c.new_name AS ad, COUNT(*) AS n"
        f" FROM {p}new_projeBase j JOIN {p}{table} c ON c.{key} = j.{col}"
        f" WHERE j.statecode = 0 AND j.CreatedOn >= '{int(since_year):04d}-01-01' GROUP BY c.{key}, c.new_name"
    )


def categories(schema: str, run: Callable[[str], dict[str, Any]], since_year: int) -> list[dict[str, Any]]:
    out = []
    for kind in _CATEGORY:
        for r in run(categories_sql(schema, since_year, kind)).get("records") or []:
            out.append({"kind": kind, "id": (_s(r.get("kimlik")) or "").upper(), "name": _s(r.get("ad")) or "",
                        "projects": int(_n(r.get("n")) or 0)})
    out.sort(key=lambda c: (c["kind"] != "kitaplik", -c["projects"], c["name"].lower()))
    return out


def users_sql(schema: str, ids: list[str]) -> str:
    p = _prefix(schema)
    return (f"SELECT SystemUserId, FullName, IsDisabled, DomainName FROM {p}SystemUserBase"
            f" WHERE SystemUserId IN ({_in(ids)})")


def me_sql(schema: str, username: str) -> str:
    """Portal kullanıcısı (AD hesap adı) → CRM kullanıcısı. CRM `DomainName` `TIMAS\\ad` ya da `ad@alan` biçimindedir."""
    p = _prefix(schema)
    u = _like(username.lower())
    return (f"SELECT SystemUserId, FullName, IsDisabled, DomainName FROM {p}SystemUserBase"
            f" WHERE LOWER(DomainName) LIKE N'%\\{u}' OR LOWER(DomainName) LIKE N'{u}@%'")


def my_projects_sql(schema: str, editor_id: str, statuses: Iterable[int], since_year: int) -> str:
    p = _prefix(schema)
    return (
        f"SELECT {_project_cols()}{_project_from(p)}"
        f" WHERE j.statecode = 0 AND j.new_editoru = '{_guid(editor_id)}' AND j.statuscode IN ({_codes(statuses)})"
        f" AND j.CreatedOn >= '{int(since_year):04d}-01-01'"
        " ORDER BY j.ModifiedOn DESC, j.new_projeId"
    )


def crm_open_sql(schema: str, statuses: Iterable[int], since_year: int) -> str:
    """Editör başına CRM'de iş durumunda (iş planı / kurul onaylı) yazılı proje sayısı."""
    p = _prefix(schema)
    return (
        "SELECT j.new_editoru, COUNT(*) AS n, MAX(j.ModifiedOn) AS son"
        f" FROM {p}new_projeBase j WHERE j.statecode = 0 AND j.new_editoru IS NOT NULL"
        f" AND j.statuscode IN ({_codes(statuses)}) AND j.CreatedOn >= '{int(since_year):04d}-01-01'"
        " GROUP BY j.new_editoru"
    )


def _is_true(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "evet")


def project_row(r: dict[str, Any]) -> dict[str, Any]:
    kit_id, marka_id = _s(r.get("new_Kitaplik")), _s(r.get("new_yayinciid"))
    return {
        "id": (_s(r.get("new_projeId")) or "").upper(), "name": _s(r.get("new_name")),
        "status": _s(r.get("statuscode")), "statusCode": int(_n(r.get("kod")) or 0),
        "kitaplik": {"id": kit_id.upper(), "name": _s(r.get("kitaplik"))} if kit_id else None,
        "marka": {"id": marka_id.upper(), "name": _s(r.get("marka"))} if marka_id else None,
        "crmEditorId": (_s(r.get("new_editoru")) or "").upper() or None, "crmEditor": _s(r.get("editor")),
        "pages": int(_n(r.get("new_tahminisayfasayisi")) or 0) or None,
        "boardApproved": _date(r.get("new_yayinkuruluonaytarihi")), "targetPrint": _date(r.get("new_hedeflenenbaskitarihi")),
        "createdOn": _date(r.get("CreatedOn")), "modifiedOn": _date(r.get("ModifiedOn")), "author": _s(r.get("yazar")),
    }


def category_of(project: dict[str, Any]) -> Optional[dict[str, str]]:
    """Projenin kural kategorisi: Kitaplık varsa o, yoksa marka."""
    if project.get("kitaplik"):
        return {"kind": "kitaplik", "id": project["kitaplik"]["id"], "name": project["kitaplik"].get("name") or ""}
    if project.get("marka"):
        return {"kind": "marka", "id": project["marka"]["id"], "name": project["marka"].get("name") or ""}
    return None


def category_label(cat: Optional[dict[str, str]]) -> Optional[str]:
    if not cat:
        return None
    return f"{'Kitaplık' if cat['kind'] == 'kitaplik' else 'Marka'}: {cat.get('name') or '—'}"


def experience(schema: str, run: Callable[[str], dict[str, Any]], since_year: int) -> dict[str, Any]:
    """{editör: {"kitaplik:<id>": n, "marka:<id>": n, "total": n}} ve kategori adları."""
    out: dict[str, dict[str, int]] = {}
    names: dict[str, str] = {}
    for r in run(experience_sql(schema, since_year)).get("records") or []:
        ed = (_s(r.get("new_editoru")) or "").upper()
        if not ed:
            continue
        n = int(_n(r.get("n")) or 0)
        row = out.setdefault(ed, {"total": 0})
        row["total"] += n
        for kind, col, name in (("kitaplik", "new_Kitaplik", "kitaplik"), ("marka", "new_yayinciid", "marka")):
            cid = (_s(r.get(col)) or "").upper()
            if cid:
                key = f"{kind}:{cid}"
                row[key] = row.get(key, 0) + n
                names[key] = _s(r.get(name)) or ""
    return {"byEditor": out, "names": names}


def crm_users(schema: str, run: Callable[[str], dict[str, Any]], ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = sorted({i.upper() for i in ids if i})
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), 200):
        chunk = ids[start:start + 200]
        for r in run(users_sql(schema, chunk)).get("records") or []:
            uid = (_s(r.get("SystemUserId")) or "").upper()
            out[uid] = {"id": uid, "name": _s(r.get("FullName")), "disabled": _is_true(r.get("IsDisabled")),
                        "account": ((_s(r.get("DomainName")) or "").rsplit("\\", 1)[-1].split("@", 1)[0]).lower()}
    return out


def crm_me(schema: str, run: Callable[[str], dict[str, Any]], username: str) -> Optional[dict[str, Any]]:
    """Oturumdaki kişinin CRM kullanıcısı; bulunamazsa None. Birden çok satırdan etkin olan seçilir."""
    if not (username or "").strip():
        return None
    rows = run(me_sql(schema, username)).get("records") or []
    acct = username.strip().lower()
    hits = [r for r in rows
            if ((_s(r.get("DomainName")) or "").rsplit("\\", 1)[-1].split("@", 1)[0]).lower() == acct]
    hits.sort(key=lambda r: _is_true(r.get("IsDisabled")))
    if not hits:
        return None
    r = hits[0]
    return {"id": (_s(r.get("SystemUserId")) or "").upper(), "name": _s(r.get("FullName")),
            "disabled": _is_true(r.get("IsDisabled"))}


# ================================================================================ kendi tablolarımız

def _task_out(r: Any) -> dict[str, Any]:
    m = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
    due = m.get("due_date")
    today = _today()
    return {
        "id": m["id"], "projectId": m["crm_project_id"], "projectName": m.get("project_name"),
        "category": m.get("category"), "editorId": m["editor_id"], "editorName": m.get("editor_name"),
        "role": m["role"], "roleLabel": ROLES.get(m["role"], m["role"]),
        "status": m["status"], "statusLabel": STATUSES.get(m["status"], m["status"]), "source": m["source"],
        "start": _iso(m.get("start_date")), "due": _iso(due), "pages": m.get("pages"), "note": m.get("note"),
        "crmEditorId": m.get("crm_editor_id"),
        "overdue": bool(due and m["status"] in OPEN and due < today),
        "createdBy": m.get("created_by"), "createdAt": _iso(m.get("created_at")),
        "updatedBy": m.get("updated_by"), "updatedAt": _iso(m.get("updated_at")), "doneAt": _iso(m.get("done_at")),
    }


def _log(c: Any, task_id: str, actor: str, action: str, detail: Any = None) -> None:
    c.execute(TASK_LOG.insert().values(id=_new(), task_id=task_id, at=_now(), actor=actor[:120], action=action[:24],
                                       detail=json.dumps(detail, ensure_ascii=False, default=str) if detail is not None else None))


def tasks(engine: sa.engine.Engine, tenant: str, *, editor_id: Optional[str] = None, project_ids: Optional[list[str]] = None,
          open_only: bool = False) -> list[dict[str, Any]]:
    q = sa.select(TASKS).where(TASKS.c.tenant_id == tenant)
    if editor_id:
        q = q.where(TASKS.c.editor_id == editor_id.upper())
    if project_ids is not None:
        if not project_ids:
            return []
        q = q.where(TASKS.c.crm_project_id.in_([p.upper() for p in project_ids]))
    if open_only:
        q = q.where(TASKS.c.status.in_(OPEN))
    with engine.connect() as c:
        rows = c.execute(q.order_by(TASKS.c.due_date.is_(None), TASKS.c.due_date, TASKS.c.created_at)).fetchall()
    return [_task_out(r) for r in rows]


def open_project_ids(engine: sa.engine.Engine, tenant: str) -> list[str]:
    """Açık görevi olan projeler: CRM'de editörü boş olsa da «atama bekleyen» listesine girmez."""
    with engine.connect() as c:
        rows = c.execute(sa.select(TASKS.c.crm_project_id).where(TASKS.c.tenant_id == tenant, TASKS.c.status.in_(OPEN))
                         .distinct()).fetchall()
    return sorted({r[0] for r in rows})


def task_history(engine: sa.engine.Engine, tenant: str, task_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        owner = c.execute(sa.select(TASKS.c.id).where(TASKS.c.id == task_id, TASKS.c.tenant_id == tenant)).first()
        if not owner:
            raise AssignError("Görev bulunamadı.", 404)
        rows = c.execute(sa.select(TASK_LOG).where(TASK_LOG.c.task_id == task_id).order_by(TASK_LOG.c.at.desc())).fetchall()
    return [{"at": _iso(r.at), "actor": r.actor, "action": r.action,
             "detail": json.loads(r.detail) if r.detail else None} for r in rows]


def profiles(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(PROFILES).where(PROFILES.c.tenant_id == tenant)).fetchall()
    return {r.editor_id: {"capacity": r.capacity, "available": bool(r.available), "note": r.note,
                          "updatedBy": r.updated_by, "updatedAt": _iso(r.updated_at)} for r in rows}


def save_profile(engine: sa.engine.Engine, tenant: str, actor: str, editor_id: str, editor_name: Optional[str],
                 body: dict[str, Any]) -> dict[str, Any]:
    eid = _id(editor_id, "Editör")
    cap = body.get("capacity")
    if cap in ("", None):
        cap = None
    else:
        try:
            cap = int(cap)
        except (TypeError, ValueError):
            raise AssignError("Kapasite tam sayı olmalı.") from None
        if cap < 1:
            raise AssignError("Kapasite en az 1 olmalı; atamaya kapatmak için «Atamaya açık» işaretini kaldırın.")
    values = {"editor_name": _text(editor_name, 200), "capacity": cap, "available": bool(body.get("available", True)),
              "note": _text(body.get("note"), 500), "updated_by": actor[:120], "updated_at": _now()}
    with engine.begin() as c:
        hit = c.execute(sa.select(PROFILES.c.editor_id).where(PROFILES.c.tenant_id == tenant,
                                                              PROFILES.c.editor_id == eid)).first()
        if hit:
            c.execute(PROFILES.update().where(PROFILES.c.tenant_id == tenant, PROFILES.c.editor_id == eid).values(**values))
        else:
            c.execute(PROFILES.insert().values(tenant_id=tenant, editor_id=eid, **values))
    return profiles(engine, tenant)[eid]


def absences(engine: sa.engine.Engine, tenant: str, *, editor_id: Optional[str] = None,
             start: Optional[date] = None, end: Optional[date] = None) -> list[dict[str, Any]]:
    q = sa.select(ABSENCES).where(ABSENCES.c.tenant_id == tenant)
    if editor_id:
        q = q.where(ABSENCES.c.editor_id == editor_id.upper())
    if start:
        q = q.where(ABSENCES.c.end_date >= start)
    if end:
        q = q.where(ABSENCES.c.start_date <= end)
    with engine.connect() as c:
        rows = c.execute(q.order_by(ABSENCES.c.start_date)).fetchall()
    return [{"id": r.id, "editorId": r.editor_id, "start": _iso(r.start_date), "end": _iso(r.end_date),
             "reason": r.reason, "createdBy": r.created_by} for r in rows]


def add_absence(engine: sa.engine.Engine, tenant: str, actor: str, editor_id: str, body: dict[str, Any]) -> dict[str, Any]:
    eid = _id(editor_id, "Editör")
    s, e = parse_day(body.get("start"), "Başlangıç"), parse_day(body.get("end"), "Bitiş")
    if not s or not e:
        raise AssignError("Başlangıç ve bitiş tarihi gerekli.")
    if e < s:
        raise AssignError("Bitiş, başlangıçtan önce olamaz.")
    row = {"id": _new(), "tenant_id": tenant, "editor_id": eid, "start_date": s, "end_date": e,
           "reason": _text(body.get("reason"), 200), "created_by": actor[:120], "created_at": _now()}
    with engine.begin() as c:
        c.execute(ABSENCES.insert().values(**row))
    return {"id": row["id"], "editorId": eid, "start": _iso(s), "end": _iso(e), "reason": row["reason"], "createdBy": actor}


def absence_owner(engine: sa.engine.Engine, tenant: str, absence_id: str) -> Optional[str]:
    with engine.connect() as c:
        r = c.execute(sa.select(ABSENCES.c.editor_id).where(ABSENCES.c.id == absence_id,
                                                            ABSENCES.c.tenant_id == tenant)).first()
    return r[0] if r else None


def delete_absence(engine: sa.engine.Engine, tenant: str, absence_id: str) -> None:
    with engine.begin() as c:
        n = c.execute(ABSENCES.delete().where(ABSENCES.c.id == absence_id, ABSENCES.c.tenant_id == tenant)).rowcount
    if not n:
        raise AssignError("İzin kaydı bulunamadı.", 404)


# ================================================================================ yük ve çakışma

def _span(task: dict[str, Any], today: date) -> tuple[date, Optional[date]]:
    """Görevin takvimdeki aralığı: başlangıç yoksa oluşturulduğu gün; termin yoksa açık uçlu (kapasiteyi hep tutar)."""
    s = parse_day(task.get("start")) or parse_day((task.get("createdAt") or "")[:10]) or today
    return s, parse_day(task.get("due"))


def _overlaps(a0: date, a1: Optional[date], b0: date, b1: Optional[date]) -> bool:
    return (a1 is None or a1 >= b0) and (b1 is None or b1 >= a0)


def conflicts(open_tasks: list[dict[str, Any]], leave: list[dict[str, Any]], capacity: Optional[int],
              start: date, due: date, *, today: Optional[date] = None) -> list[dict[str, Any]]:
    """Editöre [start, due] aralığında yeni bir iş verilirse çıkan çakışmalar.

    - izin: aralıkla kesişen izin/müsait değil kaydı;
    - kapasite: aralıktaki herhangi bir günde eşzamanlı açık görev (yeni iş dahil) kapasiteyi aşıyor.
      Kapasite yazılmamışsa bu denetim yapılmaz. Termini olmayan açık görev, başladığı günden itibaren her günü tutar.
    """
    today = today or _today()
    out: list[dict[str, Any]] = []
    for a in leave:
        a0, a1 = parse_day(a["start"]), parse_day(a["end"])
        if a0 and a1 and _overlaps(a0, a1, start, due):
            out.append({"kind": "izin", "from": _iso(max(a0, start)), "to": _iso(min(a1, due)),
                        "text": f"{_tr(a0)}–{_tr(a1)} arası {a.get('reason') or 'izinli / müsait değil'}"})
    if capacity:
        spans = [_span(t, today) for t in open_tasks]
        worst, worst_day, first_day = 0, None, None
        day = start
        while day <= due:
            n = 1 + sum(1 for s, e in spans if s <= day and (e is None or e >= day))
            if n > capacity and first_day is None:
                first_day = day
            if n > worst:
                worst, worst_day = n, day
            day += timedelta(days=1)
        if worst > capacity:
            out.append({"kind": "kapasite", "from": _iso(first_day), "to": _iso(worst_day), "count": worst,
                        "capacity": capacity,
                        "text": f"{_tr(first_day)} itibarıyla eşzamanlı {worst} iş olur; kapasite {capacity}"})
    return out


def _tr(d: Optional[date]) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def load_of(open_tasks: list[dict[str, Any]], capacity: Optional[int]) -> dict[str, Any]:
    n = len(open_tasks)
    return {"open": n, "capacity": capacity, "pct": round(100 * n / capacity) if capacity else None,
            "pages": sum(int(t.get("pages") or 0) for t in open_tasks),
            "overdue": sum(1 for t in open_tasks if t.get("overdue")),
            "undated": sum(1 for t in open_tasks if not t.get("due"))}


# ================================================================================ kural tablosu

def _rules_row(r: Any) -> dict[str, Any]:
    return {"id": r.id, "version": r.version, "state": r.state, "rules": json.loads(r.rules_json or "[]"),
            "note": r.note, "createdBy": r.created_by, "createdAt": _iso(r.created_at),
            "approvedBy": r.approved_by, "approvedAt": _iso(r.approved_at)}


def rule_versions(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(RULES).where(RULES.c.tenant_id == tenant).order_by(RULES.c.version.desc())).fetchall()
    items = [_rules_row(r) for r in rows]
    return {"active": next((v for v in items if v["state"] == "yururlukte"), None),
            "draft": next((v for v in items if v["state"] == "taslak"), None),
            "history": [v for v in items if v["state"] == "arsiv"]}


def clean_rules(rules: Any, known_editors: Optional[set[str]] = None) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise AssignError("Kural listesi bekleniyordu.")
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, r in enumerate(rules, 1):
        if not isinstance(r, dict):
            raise AssignError(f"{i}. kural geçerli değil.")
        kind = str(r.get("kind") or "")
        if kind not in ("kitaplik", "marka"):
            raise AssignError(f"{i}. kuralın kategori türü kitaplık ya da marka olmalı.")
        cid = _id(r.get("id"), f"{i}. kuralın kategorisi")
        key = f"{kind}:{cid}"
        if key in seen:
            raise AssignError(f"«{r.get('name') or cid}» kategorisi iki kez yazılmış.")
        seen.add(key)
        primary = [_id(x, "Editör") for x in (r.get("primary") or [])]
        backup = [_id(x, "Editör") for x in (r.get("backup") or []) if _id(x, "Editör") not in primary]
        if not primary:
            raise AssignError(f"«{r.get('name') or cid}» için birincil editör seçilmemiş.")
        if known_editors is not None:
            unknown = [x for x in primary + backup if x not in known_editors]
            if unknown:
                raise AssignError(f"«{r.get('name') or cid}» kuralında CRM'de bulunmayan editör var.")
        out.append({"kind": kind, "id": cid, "name": _text(r.get("name"), 200) or "", "primary": primary,
                    "backup": backup})
    return out


def save_draft(engine: sa.engine.Engine, tenant: str, actor: str, rules: list[dict[str, Any]],
               note: Optional[str]) -> dict[str, Any]:
    with engine.begin() as c:
        draft = c.execute(sa.select(RULES).where(RULES.c.tenant_id == tenant, RULES.c.state == "taslak")).first()
        body = json.dumps(rules, ensure_ascii=False)
        if draft:
            c.execute(RULES.update().where(RULES.c.id == draft.id).values(
                rules_json=body, note=_text(note, 500), created_by=actor[:120], created_at=_now()))
        else:
            top = c.execute(sa.select(sa.func.max(RULES.c.version)).where(RULES.c.tenant_id == tenant)).scalar() or 0
            c.execute(RULES.insert().values(id=_new(), tenant_id=tenant, version=int(top) + 1, state="taslak",
                                            rules_json=body, note=_text(note, 500), created_by=actor[:120],
                                            created_at=_now()))
    return rule_versions(engine, tenant)


def discard_draft(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.begin() as c:
        n = c.execute(RULES.delete().where(RULES.c.tenant_id == tenant, RULES.c.state == "taslak")).rowcount
    if not n:
        raise AssignError("Silinecek taslak yok.", 404)
    return rule_versions(engine, tenant)


def approve_draft(engine: sa.engine.Engine, tenant: str, actor: str, version: int) -> dict[str, Any]:
    """Taslağı yürürlüğe alır; önceki yürürlükteki sürüm arşive geçer. `version`, onaylayanın gördüğü taslaktır:
    arada biri taslağı değiştirdiyse onay durur."""
    with engine.begin() as c:
        draft = c.execute(sa.select(RULES).where(RULES.c.tenant_id == tenant, RULES.c.state == "taslak")).first()
        if not draft:
            raise AssignError("Onaylanacak taslak yok.", 404)
        if int(draft.version) != int(version):
            raise AssignError("Taslak siz bakarken değişti; yeniden açıp kontrol edin.", 409)
        c.execute(RULES.update().where(RULES.c.tenant_id == tenant, RULES.c.state == "yururlukte").values(state="arsiv"))
        c.execute(RULES.update().where(RULES.c.id == draft.id).values(state="yururlukte", approved_by=actor[:120],
                                                                     approved_at=_now()))
    return rule_versions(engine, tenant)


def rule_for(rules: list[dict[str, Any]], project: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Önce Kitaplık kuralı, yoksa marka kuralı.

    H1 bağlantı noktası: kural tablosu onaylı kategori ağacına geçtiğinde Kitaplık/marka →
    `categories.m2_node_for(engine, tenant, kitaplik_id=…, marka_id=…)` ile yürürlükteki ağaç düğümüne çevrilir;
    ağaç değişikliğinin M2 kurallarına etkisi `categories.impact()["m2"]`de görünür. Bugünkü kural değişmedi."""
    by = {f"{r['kind']}:{r['id']}": r for r in rules}
    for kind in ("kitaplik", "marka"):
        ref = project.get(kind)
        if ref and f"{kind}:{ref['id']}" in by:
            return by[f"{kind}:{ref['id']}"]
    return None


def suggest_rules(exp: dict[str, Any], users: dict[str, dict[str, Any]],
                  categories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Veriden kural taslağı: her kategoride en çok proje yürütmüş etkin editör birincil, sonraki iki kişi yedek.
    Yalnız bir öneridir; taslağa yazılır, onaylanmadan yürürlüğe girmez."""
    out = []
    for cat in categories:
        key = f"{cat['kind']}:{cat['id']}"
        ranked = sorted(((n.get(key, 0), ed) for ed, n in exp["byEditor"].items()
                         if n.get(key) and not users.get(ed, {}).get("disabled", True)), reverse=True)
        if not ranked:
            continue
        out.append({"kind": cat["kind"], "id": cat["id"], "name": cat["name"], "primary": [ranked[0][1]],
                    "backup": [ed for _, ed in ranked[1:3]]})
    return out


# ================================================================================ öneri

def candidates(project: dict[str, Any], *, editors: dict[str, dict[str, Any]], exp: dict[str, Any],
               rules: list[dict[str, Any]], prof: dict[str, dict[str, Any]], open_by_editor: dict[str, list[dict[str, Any]]],
               leave_by_editor: dict[str, list[dict[str, Any]]], start: date, due: date,
               today: Optional[date] = None) -> dict[str, Any]:
    """Aday editörler, puan ve gerekçeyle. Puan: kural (birincil 40 / yedek 20) + bu kategorideki geçmiş (en deneyimliye
    göre oranla 30) + müsaitlik (boş kapasite oranıyla 20; kapasite yoksa 10) − çakışma başına 25."""
    today = today or _today()
    rule = rule_for(rules, project)
    cat = category_of(project)
    key = f"{cat['kind']}:{cat['id']}" if cat else None
    best_exp = max([n.get(key, 0) for n in exp["byEditor"].values()] + [0]) if key else 0
    ranked, out_of = [], []
    for eid, ed in editors.items():
        p = prof.get(eid) or {}
        if ed.get("disabled"):
            out_of.append({"id": eid, "name": ed.get("name"), "reason": "CRM hesabı kapalı"})
            continue
        if p and not p.get("available", True):
            out_of.append({"id": eid, "name": ed.get("name"), "reason": "Atamaya kapalı (profil)"})
            continue
        score, why = 0.0, []
        if rule and eid in rule["primary"]:
            score += 40
            why.append(f"Kural: {category_label(cat)} birincil editörü")
        elif rule and eid in rule["backup"]:
            score += 20
            why.append(f"Kural: {category_label(cat)} yedek editörü")
        n_cat = exp["byEditor"].get(eid, {}).get(key, 0) if key else 0
        if n_cat and best_exp:
            score += 30 * n_cat / best_exp
            why.append(f"Bu kategoride {n_cat} proje")
        mine = open_by_editor.get(eid, [])
        cap = p.get("capacity")
        load = load_of(mine, cap)
        if cap:
            free = max(0, cap - load["open"]) / cap
            score += 20 * free
            why.append(f"Yük {load['open']}/{cap}")
        else:
            score += 10
            why.append(f"{load['open']} açık görev · kapasite girilmemiş")
        found = conflicts(mine, leave_by_editor.get(eid, []), cap, start, due, today=today)
        score -= 25 * len(found)
        ranked.append({"id": eid, "name": ed.get("name"), "score": round(score, 1), "reasons": why,
                       "conflicts": found, "load": load, "categoryProjects": n_cat,
                       "totalProjects": exp["byEditor"].get(eid, {}).get("total", 0),
                       "rule": "birincil" if rule and eid in rule["primary"] else "yedek" if rule and eid in rule["backup"] else None})
    ranked.sort(key=lambda c: (-c["score"], -c["categoryProjects"], (c["name"] or "").lower()))
    out_of.sort(key=lambda c: (c["name"] or "").lower())
    return {"category": cat, "categoryLabel": category_label(cat), "rule": rule, "items": ranked, "excluded": out_of}


# ================================================================================ atama ve görev

def assign(engine: sa.engine.Engine, tenant: str, actor: str, *, project: dict[str, Any], editor: dict[str, Any],
           role: str, start: date, due: date, pages: Optional[int], note: Optional[str], found: list[dict[str, Any]],
           force: bool) -> dict[str, Any]:
    if role not in ROLES:
        raise AssignError("Rol editör ya da destek editör olmalı.")
    if due < start:
        raise AssignError("Termin, başlangıçtan önce olamaz.")
    if editor.get("disabled"):
        raise AssignError("Bu kişinin CRM hesabı kapalı; atanamaz.")
    if found and not force:
        raise AssignError("Takvimde çakışma var.", 409, {"conflicts": found})
    pid, eid = project["id"].upper(), editor["id"].upper()
    with engine.begin() as c:
        dup = c.execute(sa.select(TASKS.c.id).where(
            TASKS.c.tenant_id == tenant, TASKS.c.crm_project_id == pid, TASKS.c.editor_id == eid,
            TASKS.c.status.in_(OPEN))).first()
        if dup:
            raise AssignError("Bu editörün bu projede zaten açık bir görevi var.", 409)
        if role == "editor":
            other = c.execute(sa.select(TASKS.c.editor_name).where(
                TASKS.c.tenant_id == tenant, TASKS.c.crm_project_id == pid, TASKS.c.role == "editor",
                TASKS.c.status.in_(OPEN))).first()
            if other:
                raise AssignError(f"Projenin açık editör görevi {other[0] or 'başka bir editörde'}; önce onu kapatın "
                                  "ya da destek editör olarak atayın.", 409)
        tid = _new()
        c.execute(TASKS.insert().values(
            id=tid, tenant_id=tenant, crm_project_id=pid, project_name=_text(project.get("name"), 300),
            category=category_label(category_of(project)), editor_id=eid, editor_name=_text(editor.get("name"), 200),
            role=role, status="sirada", source="atama", start_date=start, due_date=due, pages=pages,
            note=_text(note, 2000), crm_editor_id=project.get("crmEditorId"), created_by=actor[:120], created_at=_now()))
        _log(c, tid, actor, "atandi", {"editor": editor.get("name"), "role": role, "start": start, "due": due,
                                       "conflicts": found or None, "force": bool(found and force)})
        row = c.execute(sa.select(TASKS).where(TASKS.c.id == tid)).first()
    return _task_out(row)


def adopt(engine: sa.engine.Engine, tenant: str, actor: str, *, project: dict[str, Any], editor: dict[str, Any]) -> dict[str, Any]:
    """Editörün CRM'de kendisine yazılı projesini panosuna alması (termin sonra girilir)."""
    pid, eid = project["id"].upper(), editor["id"].upper()
    if (project.get("crmEditorId") or "").upper() != eid:
        raise AssignError("Bu proje CRM'de size yazılı değil.", 403)
    with engine.begin() as c:
        dup = c.execute(sa.select(TASKS.c.id).where(TASKS.c.tenant_id == tenant, TASKS.c.crm_project_id == pid,
                                                    TASKS.c.editor_id == eid, TASKS.c.status.in_(OPEN))).first()
        if dup:
            raise AssignError("Bu proje zaten panonuzda.", 409)
        tid = _new()
        c.execute(TASKS.insert().values(
            id=tid, tenant_id=tenant, crm_project_id=pid, project_name=_text(project.get("name"), 300),
            category=category_label(category_of(project)), editor_id=eid, editor_name=_text(editor.get("name"), 200),
            role="editor", status="sirada", source="crm", start_date=_today(), pages=project.get("pages"),
            crm_editor_id=eid, created_by=actor[:120], created_at=_now()))
        _log(c, tid, actor, "panoya-alindi", None)
        row = c.execute(sa.select(TASKS).where(TASKS.c.id == tid)).first()
    return _task_out(row)


def get_task(engine: sa.engine.Engine, tenant: str, task_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(TASKS).where(TASKS.c.id == task_id, TASKS.c.tenant_id == tenant)).first()
    if not row:
        raise AssignError("Görev bulunamadı.", 404)
    return _task_out(row)


def update_task(engine: sa.engine.Engine, tenant: str, actor: str, task_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Durum, başlangıç, termin, sayfa, not. Termin değişikliği gerekçe ister; geçmişe eski/yeni değerle yazılır."""
    cur = get_task(engine, tenant, task_id)
    values: dict[str, Any] = {}
    changes: dict[str, Any] = {}
    if "status" in body:
        st = str(body.get("status") or "")
        if st not in STATUSES:
            raise AssignError("Durum geçerli değil.")
        if st != cur["status"]:
            values["status"], changes["status"] = st, [cur["status"], st]
            values["done_at"] = _now() if st == "tamamlandi" else None
    new_start = parse_day(body["start"], "Başlangıç") if "start" in body else parse_day(cur["start"])
    new_due = parse_day(body["due"], "Termin") if "due" in body else parse_day(cur["due"])
    if new_start and new_due and new_due < new_start:
        raise AssignError("Termin, başlangıçtan önce olamaz.")
    if "start" in body and _iso(new_start) != cur["start"]:
        values["start_date"], changes["start"] = new_start, [cur["start"], _iso(new_start)]
    if "due" in body and _iso(new_due) != cur["due"]:
        if cur["due"] and not _text(body.get("reason"), 500):
            raise AssignError("Termini değiştirmek için gerekçe yazın.")
        values["due_date"], changes["due"] = new_due, [cur["due"], _iso(new_due)]
    if "pages" in body:
        pg = _pages(body.get("pages"))
        if pg != cur["pages"]:
            values["pages"], changes["pages"] = pg, [cur["pages"], pg]
    if "note" in body:
        nt = _text(body.get("note"), 2000)
        if nt != cur["note"]:
            values["note"], changes["note"] = nt, True
    if not values:
        return cur
    values.update(updated_by=actor[:120], updated_at=_now())
    with engine.begin() as c:
        c.execute(TASKS.update().where(TASKS.c.id == task_id, TASKS.c.tenant_id == tenant).values(**values))
        _log(c, task_id, actor, "guncellendi", {**changes, "reason": _text(body.get("reason"), 500)})
    return get_task(engine, tenant, task_id)


# ================================================================================ ekran özetleri

def calendar(open_tasks: list[dict[str, Any]], leave: list[dict[str, Any]], capacity: Optional[int],
             start: date, end: date, *, today: Optional[date] = None) -> dict[str, Any]:
    """Bir editörün [start, end] penceresi: görev çubukları, izinler ve çakışma aralıkları.
    Çakışma günü: eşzamanlı açık görev kapasiteyi aşıyor ya da izinli günde açık görev var."""
    today = today or _today()
    spans = [(t, *_span(t, today)) for t in open_tasks]
    off = [(parse_day(a["start"]), parse_day(a["end"]), a) for a in leave]
    bad: list[dict[str, Any]] = []
    day = start
    while day <= end:
        n = sum(1 for _, s, e in spans if s <= day and (e is None or e >= day))
        away = any(a0 and a1 and a0 <= day <= a1 for a0, a1, _ in off)
        why = "kapasite" if capacity and n > capacity else "izin" if away and n else None
        if why:
            if bad and bad[-1]["kind"] == why and parse_day(bad[-1]["to"]) == day - timedelta(days=1):
                bad[-1]["to"] = _iso(day)
                bad[-1]["max"] = max(bad[-1]["max"], n)
            else:
                bad.append({"kind": why, "from": _iso(day), "to": _iso(day), "max": n})
        day += timedelta(days=1)
    bars = [{**t, "from": _iso(s), "to": _iso(e)} for t, s, e in spans if _overlaps(s, e, start, end)]
    return {"tasks": bars, "absences": [a for a0, a1, a in off if a0 and a1 and _overlaps(a0, a1, start, end)],
            "conflicts": bad}
