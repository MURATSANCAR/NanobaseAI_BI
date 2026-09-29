"""H2 Okuyucu veri tabanı: etkinlik/fuar katılımcı dosyası yükleme ve eşleştirme.

Akış: dosya (CSV ya da Excel) yüklenir → başlıklardan kolon eşlemesi tahmin edilir, önizleme maskeli gösterilir →
kişi eşlemeyi onaylar, etkinlik adı ve tarihini yazar → satırlar okur kimliğine **özetle** eşlenir (aynı normalize
e-posta, yoksa aynı cep telefonu): «eşleşti» (etkinlik okurun zaman çizelgesine yazılır), «yeni» (CRM'de yok),
«geçersiz» (e-posta da cep telefonu da yok), «tekrar» (aynı dosyada ikinci kez). Eşleşenlerden e-posta izni
izinli olmayanlar «izin eksik» sayılır.

**Saklama:** satırlar (dosyadaki kişisel değerler) geçicidir; `READERS_IMPORT_RETENTION_DAYS` (varsayılan 30 gün)
sonunda gece işi siler, yükleme başlığı ve sayılar kalır. «Yeni» kişiler bu süre içinde CRM'e işlenmek üzere
listelenir (CRM'e portal yazmaz); süre içinde kaynak okuması onları «etkinlik yüklemesi» kaynaklı okur sayar,
süre dolunca bu kayıtlar düşer (CRM'e işlendiyse CRM'den gelir). Dosyadaki izin kolonu yalnız bilgi amaçlıdır: İYS'ye
işlenmemiş form izni «izinli» sayılmaz.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import sqlalchemy as sa

from semantic_bridge import readers as R
from semantic_bridge import readers_sources as src

log = logging.getLogger("semantic.readers.imports")
_md = sa.MetaData()

IMPORTS = sa.Table(
    "semantic_reader_imports", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("file_name", sa.String(300), nullable=False),
    sa.Column("uploaded_by", sa.String(120), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("status", sa.String(10), nullable=False),              # yuklendi | eslesti | silindi
    sa.Column("event_name", sa.String(300)),
    sa.Column("event_date", sa.Date),
    sa.Column("headers_json", sa.Text),
    sa.Column("mapping_json", sa.Text),
    sa.Column("rows", sa.Integer, nullable=False, default=0),
    sa.Column("matched", sa.Integer, nullable=False, default=0),
    sa.Column("new", sa.Integer, nullable=False, default=0),
    sa.Column("rejected", sa.Integer, nullable=False, default=0),
    sa.Column("duplicates", sa.Integer, nullable=False, default=0),
    sa.Column("missing_consent", sa.Integer, nullable=False, default=0),
    sa.Column("confirmed_by", sa.String(120)),
    sa.Column("confirmed_at", sa.DateTime(timezone=True)),
    sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
    sa.Column("purged_at", sa.DateTime(timezone=True)),
)
IMPORT_ROWS = sa.Table(
    "semantic_reader_import_rows", _md,                             # geçici: purge_after gelince silinir
    sa.Column("import_id", sa.String(32), primary_key=True),
    sa.Column("row_no", sa.Integer, primary_key=True),
    sa.Column("data_json", sa.Text, nullable=False),                  # dosyadaki hücreler (kişisel; geçici)
    sa.Column("status", sa.String(10), nullable=False),              # bekliyor | eslesti | yeni | gecersiz | tekrar
    sa.Column("reader_id", sa.String(24)),
    sa.Column("email_hash", sa.String(64)),
    sa.Column("phone_hash", sa.String(64)),
    sa.Column("missing_consent", sa.Boolean),
)


def ensure_tables(engine: sa.engine.Engine) -> None:
    from semantic_layer.store import schema_stamp
    schema_stamp.create_all(_md, engine)


ROLES = {"ad_soyad": "Ad soyad", "ad": "Ad", "soyad": "Soyad", "eposta": "E-posta", "telefon": "Cep telefonu",
         "il": "İl", "dogum_yili": "Doğum yılı", "izin": "Form izni (bilgi)"}
ROW_STATUS = {"bekliyor": "Bekliyor", "eslesti": "Eşleşti", "yeni": "Yeni (CRM'de yok)", "gecersiz": "Geçersiz",
              "tekrar": "Dosyada tekrar"}


def _fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").replace("İ", "i").replace("I", "ı").lower().translate(R._TR)).strip()


def guess_mapping(headers: list[str]) -> dict[str, Optional[int]]:
    """Başlıktan kolon rolü. Emin olunamayan rol boş kalır; kişi ekranda seçer."""
    out: dict[str, Optional[int]] = {r: None for r in ROLES}
    for i, h in enumerate(headers):
        f = _fold(h)
        role = None
        if re.search(r"mail|posta", f):
            role = "eposta"
        elif re.search(r"\b(tel|telefon|gsm|cep|mobil)", f):
            role = "telefon"
        elif re.search(r"ad soyad|adsoyad|ad ve soyad|isim soyisim|adi soyadi|katilimci|tam ad", f):
            role = "ad_soyad"
        elif re.search(r"^(soyad|soyadi|soyisim)$", f):
            role = "soyad"
        elif re.search(r"^(ad|adi|isim)$", f):
            role = "ad"
        elif re.search(r"^(il|sehir|sehri|il adi)$", f):
            role = "il"
        elif re.search(r"dogum", f):
            role = "dogum_yili"
        elif re.search(r"izin|onay|kvkk|riza", f):
            role = "izin"
        if role and out[role] is None:
            out[role] = i
    return out


def _clean_mapping(mapping: Any, width: int) -> dict[str, Optional[int]]:
    out: dict[str, Optional[int]] = {r: None for r in ROLES}
    if not isinstance(mapping, dict):
        raise R.ReadersError("Kolon eşlemesi geçersiz.")
    for role, idx in mapping.items():
        if role not in ROLES or idx in (None, ""):
            continue
        try:
            i = int(idx)
        except (TypeError, ValueError):
            raise R.ReadersError(f"«{ROLES[role]}» kolonu geçersiz.") from None
        if not 0 <= i < width:
            raise R.ReadersError(f"«{ROLES[role]}» kolonu dosyada yok.")
        out[role] = i
    if out["eposta"] is None and out["telefon"] is None:
        raise R.ReadersError("E-posta ya da cep telefonu kolonu seçilmeli; eşleştirme bunlarla yapılır.")
    return out


def _cell(row: list[str], i: Optional[int]) -> Optional[str]:
    if i is None or i >= len(row):
        return None
    v = (row[i] or "").strip()
    return v or None


def _person(row: list[str], m: dict[str, Optional[int]]) -> dict[str, Any]:
    name = _cell(row, m["ad_soyad"]) or " ".join(x for x in (_cell(row, m["ad"]), _cell(row, m["soyad"])) if x) or None
    return {"ad": name, "eposta": _cell(row, m["eposta"]), "telefon": _cell(row, m["telefon"]), "il": _cell(row, m["il"]),
            "dogum_yili": src.year_of(_cell(row, m["dogum_yili"])), "izin": _cell(row, m["izin"])}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create(engine: sa.engine.Engine, tenant: str, user: str, file_name: str, data: bytes,
           cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = cfg or R.settings()
    R.ensure(engine)
    try:
        headers, body = src.parse_file(file_name, data)
    except src.FileError as e:
        raise R.ReadersError(str(e)) from None
    iid = uuid.uuid4().hex
    now = _now()
    mapping = guess_mapping(headers)
    with engine.begin() as c:
        c.execute(IMPORTS.insert().values(
            id=iid, tenant_id=tenant, file_name=(file_name or "dosya")[:300], uploaded_by=user, at=now, status="yuklendi",
            headers_json=R._dump(headers), mapping_json=R._dump(mapping), rows=len(body),
            purge_after=now + timedelta(days=cfg["importRetentionDays"])))
        for i in range(0, len(body), 2000):
            c.execute(IMPORT_ROWS.insert(), [{"import_id": iid, "row_no": i + n + 1, "data_json": R._dump(r),
                                              "status": "bekliyor"} for n, r in enumerate(body[i:i + 2000])])
    return get(engine, tenant, iid, personal=False)


def _imp(conn, tenant: str, iid: str) -> Any:
    r = conn.execute(sa.select(IMPORTS).where(sa.and_(IMPORTS.c.tenant_id == tenant, IMPORTS.c.id == iid))).first()
    if not r:
        raise R.ReadersError("Yükleme bulunamadı.", 404)
    return r


def _view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "fileName": r.file_name, "uploadedBy": r.uploaded_by, "at": R._iso(r.at), "status": r.status,
            "eventName": r.event_name, "eventDate": r.event_date.isoformat() if r.event_date else None,
            "headers": R._load(r.headers_json, []), "mapping": R._load(r.mapping_json, {}), "rows": r.rows,
            "matched": r.matched, "new": r.new, "rejected": r.rejected, "duplicates": r.duplicates,
            "missingConsent": r.missing_consent, "confirmedBy": r.confirmed_by, "confirmedAt": R._iso(r.confirmed_at),
            "purgeAfter": R._iso(r.purge_after), "purgedAt": R._iso(r.purged_at)}


def imports_stmt(tenant: str):
    return sa.select(IMPORTS).where(IMPORTS.c.tenant_id == tenant).order_by(IMPORTS.c.at.desc())


def import_stmts(tenant: str, iid: str, status: str, page: int, size: int) -> dict[str, Any]:
    """Tek yüklemenin okumaları: kayıt, süzgeçli satır sayısı, bu sayfanın satırları, durum başına sayı."""
    q = sa.select(IMPORT_ROWS).where(IMPORT_ROWS.c.import_id == iid)
    if status:
        q = q.where(IMPORT_ROWS.c.status == status)
    return {"kayit": sa.select(IMPORTS).where(sa.and_(IMPORTS.c.tenant_id == tenant, IMPORTS.c.id == iid)),
            "say": sa.select(sa.func.count()).select_from(q.subquery()),
            "sayfa": q.order_by(IMPORT_ROWS.c.row_no).offset(max(0, page) * size).limit(size),
            "durum": (sa.select(IMPORT_ROWS.c.status, sa.func.count()).where(IMPORT_ROWS.c.import_id == iid)
                      .group_by(IMPORT_ROWS.c.status))}


def list_imports(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    R.ensure(engine)
    with engine.connect() as c:
        return [_view(r) for r in c.execute(imports_stmt(tenant))]


def get(engine: sa.engine.Engine, tenant: str, iid: str, *, personal: bool, status: str = "", page: int = 0,
        size: int = 50) -> dict[str, Any]:
    """Yükleme + satırlar (sayfalı). Kişisel değerler yalnız `personal` iken açık; yoksa maskeli."""
    R.ensure(engine)
    with engine.connect() as c:
        r = _imp(c, tenant, iid)
        m = R._load(r.mapping_json, {})
        q = import_stmts(tenant, iid, status, page, size)
        total = c.execute(q["say"]).scalar() or 0
        rows = list(c.execute(q["sayfa"]))
        by_status = dict(c.execute(q["durum"]).all())
    items = []
    mm = {k: (int(v) if v is not None else None) for k, v in m.items() if k in ROLES}
    for x in rows:
        cells = R._load(x.data_json, [])
        p = _person(cells, {k: mm.get(k) for k in ROLES})
        items.append({"row": x.row_no, "status": x.status, "statusLabel": ROW_STATUS.get(x.status, x.status),
                      "readerId": x.reader_id, "missingConsent": x.missing_consent,
                      "name": p["ad"] if personal else None,
                      "email": p["eposta"] if personal else R.mask_email(p["eposta"]) or (p["eposta"] and "***"),
                      "phone": p["telefon"] if personal else R.mask_phone(p["telefon"]) or (p["telefon"] and "***"),
                      "city": p["il"]})
    out = _view(r)
    out.update(items=items, total=total, page=page, pageSize=size, byStatus=by_status, roles=ROLES)
    return out


def confirm(engine: sa.engine.Engine, tenant: str, iid: str, user: str, body: dict[str, Any],
            cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = cfg or R.settings()
    key = R.salt()
    event = (body.get("eventName") or "").strip()
    if len(event) < 3:
        raise R.ReadersError("Etkinlik adı yazılmalı.")
    try:
        ev_date = date.fromisoformat(str(body.get("eventDate") or date.today().isoformat())[:10])
    except ValueError:
        raise R.ReadersError("Etkinlik tarihi geçersiz.") from None
    with engine.connect() as c:
        imp = _imp(c, tenant, iid)
        if imp.status == "silindi":
            raise R.ReadersError("Bu yüklemenin satırları saklama süresi dolduğu için silindi.", 409)
        rows = list(c.execute(sa.select(IMPORT_ROWS).where(IMPORT_ROWS.c.import_id == iid).order_by(IMPORT_ROWS.c.row_no)))
    headers = R._load(imp.headers_json, [])
    m = _clean_mapping(body.get("mapping") if body.get("mapping") is not None else R._load(imp.mapping_json, {}), len(headers))
    profs = {p["id"]: p for p in R.profiles(engine, tenant, cfg)}
    people = [_person(R._load(x.data_json, []), m) for x in rows]
    hashes = [(R.email_key(p["eposta"], key), R.phone_key(p["telefon"], key)) for p in people]
    owners = R.readers_for_hashes(engine, tenant, [h for pair in hashes for h in pair])
    seen: set[str] = set()
    updates, touched = [], {}
    cnt: Counter = Counter()
    for x, (eh, ph) in zip(rows, hashes):
        st, rid, miss = "gecersiz", None, None
        if eh or ph:
            dup_key = eh or ph
            if dup_key in seen:
                st = "tekrar"
            else:
                seen.add(dup_key)
                for h in (eh, ph):
                    ids = [i for i in owners.get(h or "", []) if i in profs]
                    if ids:
                        rid = ids[0]
                        break
                if rid:
                    st = "eslesti"
                    miss = profs[rid]["consent"]["email"] != "izinli"
                    touched[rid] = True
                else:
                    st = "yeni"
        cnt[st] += 1
        cnt["izin_eksik"] += int(bool(miss))
        updates.append({"import_id": iid, "row_no": x.row_no, "status": st, "reader_id": rid, "email_hash": eh,
                        "phone_hash": ph, "missing_consent": miss})
    now = _now()
    at = datetime(ev_date.year, ev_date.month, ev_date.day, 12, tzinfo=timezone.utc)
    with engine.begin() as c:
        for u in updates:
            c.execute(IMPORT_ROWS.update().where(sa.and_(IMPORT_ROWS.c.import_id == iid, IMPORT_ROWS.c.row_no == u["row_no"]))
                      .values(status=u["status"], reader_id=u["reader_id"], email_hash=u["email_hash"],
                              phone_hash=u["phone_hash"], missing_consent=u["missing_consent"]))
        c.execute(R.EVENTS.delete().where(sa.and_(R.EVENTS.c.tenant_id == tenant, R.EVENTS.c.ref == iid)))
        for rid in touched:
            c.execute(R.EVENTS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, reader_id=rid, kind="etkinlik",
                                               at=at, label=event[:300], ref=iid))
            r = c.execute(sa.select(R.READERS).where(R.READERS.c.reader_id == rid)).first()
            if r:
                attrs = R._load(r.attrs_json, {})
                attrs["etkinlik_adi"] = sorted(set(attrs.get("etkinlik_adi", [])) | {event[:300]})
                lt = max(x for x in (R._utc(r.last_touch), at) if x)
                c.execute(R.READERS.update().where(R.READERS.c.reader_id == rid).values(
                    attrs_json=R._dump(attrs), last_touch=lt, event_count=(r.event_count or 0) + 1))
        c.execute(IMPORTS.update().where(IMPORTS.c.id == iid).values(
            status="eslesti", event_name=event[:300], event_date=ev_date, mapping_json=R._dump(m),
            matched=cnt["eslesti"], new=cnt["yeni"], rejected=cnt["gecersiz"], duplicates=cnt["tekrar"],
            missing_consent=cnt["izin_eksik"], confirmed_by=user, confirmed_at=now))
        R._stamp(c, tenant)
    return get(engine, tenant, iid, personal=False)


def new_people_csv(engine: sa.engine.Engine, tenant: str, iid: str) -> tuple[str, bytes, int]:
    """«CRM'e işlenecek» yeni kişiler (saklama süresi içinde). Kişisel veri: çağıran yetkiyi denetler."""
    with engine.connect() as c:
        imp = _imp(c, tenant, iid)
        rows = list(c.execute(sa.select(IMPORT_ROWS).where(sa.and_(IMPORT_ROWS.c.import_id == iid,
                                                                   IMPORT_ROWS.c.status == "yeni")).order_by(IMPORT_ROWS.c.row_no)))
    m = {k: (int(v) if v is not None else None) for k, v in R._load(imp.mapping_json, {}).items() if k in ROLES}
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["satir", "ad_soyad", "eposta", "cep_telefonu", "il", "dogum_yili", "form_izni", "etkinlik", "etkinlik_tarihi"])
    for x in rows:
        p = _person(R._load(x.data_json, []), {k: m.get(k) for k in ROLES})
        w.writerow([x.row_no, p["ad"] or "", R.norm_email(p["eposta"]) or (p["eposta"] or ""),
                    R.norm_phone(p["telefon"]) or (p["telefon"] or ""), p["il"] or "", p["dogum_yili"] or "",
                    p["izin"] or "", imp.event_name or "", imp.event_date.isoformat() if imp.event_date else ""])
    name = f"crm-e-islenecek-{re.sub(r'[^a-z0-9]+', '-', _fold(imp.event_name or imp.file_name))[:40] or 'yukleme'}.csv"
    return name, ("﻿" + buf.getvalue()).encode("utf-8"), len(rows)


def purge(engine: sa.engine.Engine, tenant: str, iid: Optional[str] = None) -> int:
    """Saklama süresi dolan (ya da `iid` verilirse o) yüklemenin satırlarını siler. Başlık ve sayılar kalır."""
    R.ensure(engine)
    now = _now()
    with engine.begin() as c:
        q = sa.select(IMPORTS.c.id).where(sa.and_(IMPORTS.c.tenant_id == tenant, IMPORTS.c.status != "silindi"))
        q = q.where(IMPORTS.c.id == iid) if iid else q.where(IMPORTS.c.purge_after <= now)
        ids = [r.id for r in c.execute(q)]
        for i in ids:
            c.execute(IMPORT_ROWS.delete().where(IMPORT_ROWS.c.import_id == i))
            c.execute(IMPORTS.update().where(IMPORTS.c.id == i).values(status="silindi", purged_at=now))
        if ids:
            R._stamp(c, tenant)
    return len(ids)


def upload_records(engine: sa.engine.Engine, tenant: str, key: bytes) -> list[R.SourceRecord]:
    """Onaylı, satırları silinmemiş yüklemelerdeki «yeni» kişiler: okuma turunda kaynak kaydı olur."""
    out: list[R.SourceRecord] = []
    with engine.connect() as c:
        imps = list(c.execute(sa.select(IMPORTS).where(sa.and_(IMPORTS.c.tenant_id == tenant, IMPORTS.c.status == "eslesti"))))
        for imp in imps:
            m = {k: (int(v) if v is not None else None) for k, v in R._load(imp.mapping_json, {}).items() if k in ROLES}
            for x in c.execute(sa.select(IMPORT_ROWS).where(sa.and_(IMPORT_ROWS.c.import_id == imp.id,
                                                                    IMPORT_ROWS.c.status == "yeni"))):
                p = _person(R._load(x.data_json, []), {k: m.get(k) for k in ROLES})
                rec = R.record("upload", f"{imp.id}:{x.row_no}", emails=(p["eposta"],), phones=(p["telefon"],),
                               name=p["ad"], birth_year=p["dogum_yili"], city=p["il"], created=imp.event_date,
                               attrs={"etkinlik_adi": [imp.event_name]}, key=key)
                out.append(rec)
    return out
