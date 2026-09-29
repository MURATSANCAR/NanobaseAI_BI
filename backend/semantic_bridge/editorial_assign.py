"""M2 Editör atama — yalnız CRM'den okunur (kullanıcı kararı 2026-09-29) — ve editörün Masam'daki görevleri.

Kim hangi projenin editörü: CRM proje kartındaki `new_projeBase.new_editoru` (SystemUser). Portalda atama,
öneri, kategori–editör kuralı, kapasite ve izin kaydı yoktur; bunlar 2026-09-27'de eklenmiş, 09-29'da
kaldırılmıştır (tabloları `semantic_editorial_rule_versions`, `…_editor_profiles`, `…_absences` veritabanında
durur, yazılmaz ve okunmaz). CRM'e yazma yetkimiz de yoktur.

Masam › Görevlerim: CRM'de editörü oturumdaki kişi olan iş durumundaki projeler. Editör kendi işinin
durumunu (sırada → çalışılıyor → beklemede → tamamlandı), terminini, sayfasını ve notunu tutar
(`semantic_editorial_tasks`); bu kişisel takiptir, atama değildir. Kayıt ilk değişiklikte açılır, her
değişiklik gerekçesiyle görev geçmişine yazılır. CRM'de editörü değişen projenin kaydı Masam'da görünmez.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.editorial import (
    PAGE_SIZE, EditorialError, _date, _guid, _like, _n, _prefix, _s,
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
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
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


def _pending_where(*, statuses: Iterable[int], since_year: int, q: str = "", category: str = "") -> str:
    parts = ["j.statecode = 0", "j.new_editoru IS NULL", f"j.CreatedOn >= '{int(since_year):04d}-01-01'"]
    codes = list(statuses)
    if codes:
        parts.append(f"j.statuscode IN ({_codes(codes)})")
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


def pending_facets_sql(schema: str, since_year: int) -> str:
    """Editörsüz etkin projeler durum başına (ekrandaki durum süzgeci)."""
    p = _prefix(schema)
    return (
        "SELECT j.statuscode, CAST(j.statuscode AS int) AS kod, COUNT(*) AS n"
        f" FROM {p}new_projeBase j WHERE j.statecode = 0 AND j.new_editoru IS NULL"
        f" AND j.CreatedOn >= '{int(since_year):04d}-01-01'"
        + " GROUP BY j.statuscode ORDER BY COUNT(*) DESC"
    )


def projects_sql(schema: str, ids: list[str]) -> str:
    p = _prefix(schema)
    return f"SELECT {_project_cols()}{_project_from(p)} WHERE j.new_projeId IN ({_in(ids)})"


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


def crm_me(schema: str, run: Callable[[str], dict[str, Any]], username: str) -> Optional[dict[str, Any]]:
    """Oturumdaki kişinin CRM kullanıcısı; bulunamazsa None. Birden çok satırdan etkin olan seçilir."""
    if not (username or "").strip():
        return None
    return crm_me_from_rows(run(me_sql(schema, username)).get("records") or [], username)


def crm_me_from_rows(rows: list[dict[str, Any]], username: str) -> Optional[dict[str, Any]]:
    """`crm_me`'nin seçim kuralı: `me_sql`'in döndürdüğü satırlardan hesap kısmı kişininkiyle aynı olanlar, etkin
    olan önce, aynı durumda okunma sırası. Saklanmış eşleme (`crm_kisi`) de bu fonksiyonu çağırır (kural tek yerde)."""
    if not (username or "").strip():
        return None
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


def task_history(engine: sa.engine.Engine, tenant: str, task_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        owner = c.execute(sa.select(TASKS.c.id).where(TASKS.c.id == task_id, TASKS.c.tenant_id == tenant)).first()
        if not owner:
            raise AssignError("Görev bulunamadı.", 404)
        rows = c.execute(sa.select(TASK_LOG).where(TASK_LOG.c.task_id == task_id).order_by(TASK_LOG.c.at.desc())).fetchall()
    return [{"at": _iso(r.at), "actor": r.actor, "action": r.action,
             "detail": json.loads(r.detail) if r.detail else None} for r in rows]


# ================================================================================ Masam › Görevlerim

def _latest(c: Any, tenant: str, project_id: str, editor_id: str) -> Any:
    """Kişinin bu projedeki son kaydı: açık olan önce, yoksa en son kapanan."""
    return c.execute(sa.select(TASKS).where(TASKS.c.tenant_id == tenant, TASKS.c.crm_project_id == project_id,
                                            TASKS.c.editor_id == editor_id)
                     .order_by(TASKS.c.status.in_(OPEN).desc(), TASKS.c.created_at.desc())).first()


def board(projects: list[dict[str, Any]], mine: list[dict[str, Any]], *, today: Optional[date] = None,
          done_days: int = 30) -> list[dict[str, Any]]:
    """CRM'de size yazılı projeler, üstlerinde kendi takip kaydınız. Kaydı olmayan proje «sırada» görünür.

    Kapanmış (tamamlandı/iptal) kayıt son `done_days` gün içindeyse o sütunda kalır; daha eskiyse proje
    Masam'dan düşer — CRM iş planı durumu kitap basıldıktan sonra da açık kalabildiği için."""
    today = today or _today()
    since = (today - timedelta(days=done_days)).isoformat()
    by: dict[str, dict[str, Any]] = {}
    for t in mine:
        cur = by.get(t["projectId"])
        if cur is None or (t["status"] in OPEN and cur["status"] not in OPEN) or (
                (t["status"] in OPEN) == (cur["status"] in OPEN) and (t["createdAt"] or "") > (cur["createdAt"] or "")):
            by[t["projectId"]] = t
    out = []
    for p in projects:
        t = by.get(p["id"])
        if t and t["status"] not in OPEN and (t["doneAt"] or t["updatedAt"] or "")[:10] < since:
            continue
        item = dict(t) if t else {
            "id": None, "projectId": p["id"], "projectName": p.get("name"), "category": category_label(category_of(p)),
            "editorId": p.get("crmEditorId"), "editorName": p.get("crmEditor"), "role": "editor",
            "roleLabel": ROLES["editor"], "status": "sirada", "statusLabel": STATUSES["sirada"], "source": "crm",
            "start": None, "due": None, "pages": p.get("pages"), "note": None, "crmEditorId": p.get("crmEditorId"),
            "overdue": False, "createdBy": None, "createdAt": None, "updatedBy": None, "updatedAt": None, "doneAt": None,
        }
        item["projectName"] = p.get("name") or item.get("projectName")
        item["project"] = p
        out.append(item)
    return out


def save_mine(engine: sa.engine.Engine, tenant: str, actor: str, *, project: dict[str, Any], editor: dict[str, Any],
              body: dict[str, Any]) -> dict[str, Any]:
    """Masam'da bir projenin takibini değiştirir; kaydı yoksa önce açar. Yalnız CRM'de editörü olduğunuz projede."""
    pid, eid = project["id"].upper(), editor["id"].upper()
    if (project.get("crmEditorId") or "").upper() != eid:
        raise AssignError("Bu proje CRM'de size yazılı değil.", 403)
    with engine.begin() as c:
        row = _latest(c, tenant, pid, eid)
        if row is not None:
            tid = row.id
        else:
            tid = _new()
            c.execute(TASKS.insert().values(
                id=tid, tenant_id=tenant, crm_project_id=pid, project_name=_text(project.get("name"), 300),
                category=category_label(category_of(project)), editor_id=eid, editor_name=_text(editor.get("name"), 200),
                role="editor", status="sirada", source="crm", start_date=_today(), pages=project.get("pages"),
                crm_editor_id=eid, created_by=actor[:120], created_at=_now()))
            _log(c, tid, actor, "panoya-alindi", None)
    return update_task(engine, tenant, actor, tid, body)


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
