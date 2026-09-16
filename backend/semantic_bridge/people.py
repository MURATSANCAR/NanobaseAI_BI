"""Kişi rehberi ve profil.

Rehberin kaynağı CRM'deki kullanıcı tablosudur (`SystemUserBase`); elle yazılmış kişi yoktur.

CRM'de "etkin" görünen hesapların bir kısmı artık çalışmıyor (AD'de devre dışı) ya da kişi değil (pazaryeri,
kasa, ortak hesaplar — AD'de etkin ama etki alanına hiç giriş yapmamış ya da yıllardır yapmamış). Bu yüzden dizin
(AD) ayarı varsa CRM listesi AD ile kesiştirilir: CRM satırı AD nesnesine `ActiveDirectoryGuid` = `objectGUID`
ile bağlanır (hesap adı değişse de tutar), bulunamazsa hesap adıyla. Kalan kişi AD'de etkin olmalı ve son
`max_idle_days` gün içinde giriş yapmış olmalı (0 = süre bakılmaz). Kişinin rehberdeki hesap adı AD'deki
`sAMAccountName`'dir; portal oturumu da onu kullanır. AD'deki unvan/bölüm/telefon/ofis alanları boş CRM
alanlarını doldurur; bölüm boşsa kişinin bulunduğu OU birim sayılır. AD'ye ulaşılamazsa liste yalnız CRM'den
gelir ve yanıt bunu söyler.

Kişi kendi profilinde eksik alanları (dahili, kat, masa, fotoğraf…) doldurabilir; bunlar sunucuda
`semantic_people_profiles` tablosunda AD hesabına bağlı durur. Öncelik: CRM > AD > kişinin yazdığı.
Böylece CRM'e kolon eklendiği gün rehber kendiliğinden ona döner.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic_bridge.people")

_md = sa.MetaData()

PROFILES = sa.Table(
    "semantic_people_profiles", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("username", sa.String(120), primary_key=True),
    sa.Column("fields", sa.Text, nullable=False, default="{}"),
    sa.Column("photo", sa.LargeBinary),
    sa.Column("photo_type", sa.String(40)),
    sa.Column("photo_version", sa.Integer, nullable=False, default=0),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

#: Kişinin kendi yazabileceği alanlar ve üst uzunlukları.
EDITABLE: dict[str, int] = {
    "extension": 20,
    "floor": 40,
    "desk": 60,
    "mobile": 30,
    "about": 400,
}

#: Rehber alanı → CRM kolonu (öncelik sırasıyla). CRM'e yeni kolon gelince buraya eklenir.
CRM_FIELDS: dict[str, tuple[str, ...]] = {
    "title": ("JobTitle", "Title"),
    "unit": ("new_gorevbirimi",),
    "email": ("InternalEMailAddress",),
    "mobile": ("MobilePhone",),
    "phone": ("HomePhone",),
    "extension": (),
    "floor": (),
}

#: Rehber alanı → AD özniteliği (öncelik sırasıyla).
AD_FIELDS: dict[str, tuple[str, ...]] = {
    "title": ("title",),
    "unit": ("department",),
    "email": ("mail",),
    "mobile": ("mobile",),
    "phone": ("telephoneNumber",),
    "extension": ("ipPhone", "otherTelephone"),
    "floor": ("physicalDeliveryOfficeName",),
}
AD_ENABLED_PERSONS = ("(&(objectCategory=person)(objectClass=user)"
                      "(!(userAccountControl:1.2.840.113556.1.4.803:=2)))")

PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
#: Tarayıcı fotoğrafı yüklemeden önce küçültür; bu sınır yalnız bozuk/kötü niyetli isteğe karşıdır.
PHOTO_MAX_BYTES = 2_000_000

_ready: set[int] = set()
_lock = threading.Lock()


class ProfileError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""

    status = 422


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def account(domain_name: str) -> str:
    """`TIMAS\\ahmety` ya da `ahmety@timas.com.tr` → `ahmety` (AD sAMAccountName ile aynı biçim)."""
    s = (domain_name or "").strip()
    s = s.rsplit("\\", 1)[-1]
    s = s.split("@", 1)[0]
    return s.lower()


# ------------------------------------------------------------------ CRM


_NAME = re.compile(r"^[A-Za-z0-9_$-]+$")


def _table(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise ProfileError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise ProfileError("CRM şeması girilmemiş; rehber okunamıyor.")
    # Köşeli parantezsiz: köprü CRM sorgusunu `Timas_MSCRM.dbo.` önekinden tanıyıp CRM bağlantısına yollar.
    return (f"{db}." if db else "") + f"{sch}.SystemUserBase"


def directory_sql(schema: str) -> str:
    cols = sorted({c for cs in CRM_FIELDS.values() for c in cs})
    # CRM tarafında etkin: devre dışı değil, etkileşimli erişim (AccessMode 0 = okuma-yazma, 1 = yönetim),
    # AD hesabı var. Uygulama/eşitleme/destek hesapları (AccessMode 3, 4, 5…) rehbere girmez.
    return (
        "SELECT SystemUserId, FullName, DomainName, CAST(ActiveDirectoryGuid AS nvarchar(40)) AS AdGuid, "
        + ", ".join(cols)
        + f" FROM {_table(schema)}"
        + " WHERE IsDisabled = 0 AND AccessMode IN (0, 1)"
        + " AND DomainName IS NOT NULL AND DomainName <> ''"
        + " ORDER BY FullName"
    )


def _clean(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _crm_person(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": _clean(row.get("SystemUserId")),
        "username": account(_clean(row.get("DomainName"))),
        "name": _clean(row.get("FullName")),
        "guid": _clean(row.get("AdGuid")).strip("{}").lower(),
    }
    for field, cols in CRM_FIELDS.items():
        out[field] = next((_clean(row.get(c)) for c in cols if _clean(row.get(c))), "")
    return out


def _merge(person: dict[str, Any], own: Optional[dict[str, Any]]) -> dict[str, Any]:
    """CRM önce gelir; kişinin yazdığı değer yalnız CRM boşken görünür."""
    fields = (own or {}).get("fields") or {}
    merged = dict(person)
    for k in EDITABLE:
        if not merged.get(k) and fields.get(k):
            merged[k] = fields[k]
    merged["photoVersion"] = (own or {}).get("photo_version") if (own or {}).get("has_photo") else None
    return merged


def _first(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        v = next((x for x in v if x not in (None, "")), "")
    return _clean(v)


def _guid(v: Any) -> str:
    v = _one(v)
    if isinstance(v, (bytes, bytearray)) and len(v) == 16:
        return str(uuid.UUID(bytes_le=bytes(v)))
    return _clean(v).strip("{}").lower()


def _one(v: Any) -> Any:
    if isinstance(v, (list, tuple)):
        return next((x for x in v if x not in (None, "", b"")), None)
    return v


def _logon(v: Any) -> Optional[datetime]:
    """lastLogonTimestamp: ldap3 datetime ya da 1601'den beri 100 ns (FILETIME). 0/boş = hiç giriş yok."""
    v = _one(v)
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=n // 10)


def _ou(dn: Any) -> str:
    """`CN=Ali,OU=Cocuk Editorya,DC=timas,DC=local` → `Cocuk Editorya` (kişiye en yakın OU)."""
    for part in re.split(r"(?<!\\),", _clean(_one(dn))):
        k, _, v = part.partition("=")
        if k.strip().upper() == "OU" and v.strip():
            return v.strip().replace("_", " ")
    return ""


def ad_people(cfg: dict[str, str]) -> Optional[dict[str, dict[str, Any]]]:
    """AD'deki etkin kişi hesapları. Anahtar hem `guid:<objectGUID>` hem hesap adıdır. Ayar eksikse None."""
    need = ("AD_HOST", "AD_NETBIOS", "AD_BASE_DN", "AD_BIND_USER", "AD_BIND_PASSWORD")
    if not all(cfg.get(k) for k in need):
        return None
    from ldap3 import NONE, NTLM, SUBTREE, Connection, Server  # type: ignore[import-not-found]

    from semantic_bridge.admin import _ensure_md4

    _ensure_md4()
    attrs = sorted({"sAMAccountName", "objectGUID", "distinguishedName", "lastLogonTimestamp"}
                   | {a for v in AD_FIELDS.values() for a in v})
    server = Server(cfg["AD_HOST"], port=int(cfg.get("AD_PORT") or 389), get_info=NONE, connect_timeout=5)
    conn = Connection(server, user=f'{cfg["AD_NETBIOS"]}\\{cfg["AD_BIND_USER"]}', password=cfg["AD_BIND_PASSWORD"],
                      authentication=NTLM, receive_timeout=30)
    if not conn.bind():
        raise RuntimeError(f"AD servis hesabı reddedildi: {conn.result.get('description')}")
    try:
        found = conn.extend.standard.paged_search(cfg["AD_BASE_DN"], AD_ENABLED_PERSONS, SUBTREE,
                                                  attributes=attrs, paged_size=500, generator=True)
        return index_ad(e.get("attributes") or {} for e in found if e.get("type") == "searchResEntry")
    finally:
        conn.unbind()


def index_ad(entries: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for a in entries:
        acc = _first(a.get("sAMAccountName")).lower()
        if not acc:
            continue
        rec: dict[str, Any] = {f: next((_first(a.get(x)) for x in xs if _first(a.get(x))), "") for f, xs in AD_FIELDS.items()}
        if not rec["unit"]:
            rec["unit"] = _ou(a.get("distinguishedName"))
        rec["account"] = acc
        rec["lastLogon"] = _logon(a.get("lastLogonTimestamp"))
        out[acc] = rec
        g = _guid(a.get("objectGUID"))
        if g:
            out["guid:" + g] = rec
    return out


class Directory:
    """CRM (+AD) listesini kısa süre bellekte tutar: rehber her açılışta yeniden okumasın."""

    def __init__(self, ttl: float = 300.0):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._at = 0.0
        self._key = ""
        self._rows: list[dict[str, Any]] = []
        self.ad_checked = False

    def rows(self, schema: str, run: Callable[[str], dict[str, Any]], *, fresh: bool = False,
             ad: Optional[Callable[[], Optional[dict[str, dict[str, Any]]]]] = None,
             max_idle_days: int = 0) -> tuple[list[dict[str, Any]], float]:
        sql = directory_sql(schema) + f"\n-- idle:{max_idle_days}"
        with self._lock:
            if not fresh and self._key == sql and time.time() - self._at < self.ttl:
                return self._rows, self._at
        res = run(directory_sql(schema))
        rows = [_crm_person(r) for r in res.get("records") or []]
        rows = [r for r in rows if r["username"] and r["name"]]
        directory: Optional[dict[str, dict[str, Any]]] = None
        if ad is not None:
            try:
                directory = ad()
            except Exception as e:  # noqa: BLE001
                log.warning("people: AD okunamadı, rehber yalnız CRM'den: %s", e)
        if directory is not None:
            since = datetime.now(timezone.utc) - timedelta(days=max_idle_days) if max_idle_days > 0 else None
            kept = []
            for r in rows:
                rec = directory.get("guid:" + r["guid"]) if r["guid"] else None
                rec = rec or directory.get(r["username"])
                if rec is None:
                    continue                      # AD'de yok ya da devre dışı: artık çalışmıyor
                if since is not None and (rec["lastLogon"] is None or rec["lastLogon"] < since):
                    continue                      # hiç/uzun süredir giriş yok: ortak ya da kullanılmayan hesap
                kept.append(_with_ad(r, rec))
            rows = kept
        with self._lock:
            self._rows, self._at, self._key = rows, time.time(), sql
            self.ad_checked = directory is not None
        return rows, self._at


def _with_ad(person: dict[str, Any], ad: dict[str, Any]) -> dict[str, Any]:
    out = dict(person)
    out["username"] = ad["account"]           # portal oturumu AD hesap adını taşır
    for k in AD_FIELDS:
        if not out.get(k) and ad.get(k):
            out[k] = ad[k]
    return out


# ------------------------------------------------------------------ profil kaydı


def _own_rows(engine: sa.engine.Engine, tenant: str, users: Optional[list[str]] = None) -> dict[str, dict[str, Any]]:
    q = sa.select(PROFILES.c.username, PROFILES.c.fields, PROFILES.c.photo_version,
                  (PROFILES.c.photo.isnot(None)).label("has_photo"), PROFILES.c.updated_at
                  ).where(PROFILES.c.tenant_id == tenant)
    if users is not None:
        q = q.where(PROFILES.c.username.in_([u.lower() for u in users]))
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for r in c.execute(q):
            try:
                fields = json.loads(r.fields or "{}")
            except ValueError:
                fields = {}
            out[r.username] = {"fields": fields if isinstance(fields, dict) else {}, "photo_version": r.photo_version,
                               "has_photo": bool(r.has_photo), "updated_at": _iso(r.updated_at)}
    return out


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def people(engine: sa.engine.Engine, tenant: str, crm_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    own = _own_rows(engine, tenant)
    return [_merge(p, own.get(p["username"])) for p in crm_rows]


def me(engine: sa.engine.Engine, tenant: str, user: str, display: str, crm_rows: list[dict[str, Any]]) -> dict[str, Any]:
    key = user.lower()
    crm = next((p for p in crm_rows if p["username"] == key), None)
    own = _own_rows(engine, tenant, [key]).get(key) or {}
    return {
        "username": key,
        "displayName": (crm or {}).get("name") or display,
        "inCrm": crm is not None,
        "crm": crm,
        "fields": {k: (own.get("fields") or {}).get(k, "") for k in EDITABLE},
        "photoVersion": own.get("photo_version") if own.get("has_photo") else None,
        "updatedAt": own.get("updated_at"),
    }


def _upsert(engine: sa.engine.Engine, tenant: str, user: str, **values: Any) -> None:
    key = user.lower()[:120]
    now = datetime.now(timezone.utc)
    with engine.begin() as c:
        exists = c.execute(sa.select(PROFILES.c.username).where(
            PROFILES.c.tenant_id == tenant, PROFILES.c.username == key)).first()
        if exists:
            c.execute(PROFILES.update().where(PROFILES.c.tenant_id == tenant, PROFILES.c.username == key)
                      .values(updated_at=now, **values))
        else:
            c.execute(PROFILES.insert().values(tenant_id=tenant, username=key, updated_at=now,
                                               fields=values.pop("fields", "{}"),
                                               photo_version=values.pop("photo_version", 0), **values))


def save_fields(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, str]:
    raw = body.get("fields") if isinstance(body.get("fields"), dict) else body
    fields: dict[str, str] = {}
    for k, limit in EDITABLE.items():
        v = raw.get(k, "")
        if v is None:
            v = ""
        if not isinstance(v, (str, int)):
            raise ProfileError(f"«{k}» alanı metin olmalı.")
        v = " ".join(str(v).split()) if k != "about" else str(v).strip()
        if len(v) > limit:
            raise ProfileError(f"«{k}» en fazla {limit} karakter olabilir.")
        fields[k] = v
    if fields["extension"] and not re.fullmatch(r"[0-9 +()/-]{1,20}", fields["extension"]):
        raise ProfileError("Dahili numara yalnız rakam içermeli.")
    if fields["mobile"] and not re.fullmatch(r"[0-9 +()-]{7,30}", fields["mobile"]):
        raise ProfileError("Cep telefonu geçerli bir numara değil.")
    _upsert(engine, tenant, user, fields=json.dumps(fields, ensure_ascii=False))
    return fields


def save_photo(engine: sa.engine.Engine, tenant: str, user: str, data_url: str) -> int:
    m = re.fullmatch(r"data:(image/[a-z]+);base64,([A-Za-z0-9+/=\s]+)", (data_url or "").strip())
    if not m:
        raise ProfileError("Fotoğraf okunamadı; JPEG, PNG ya da WebP seçin.")
    mime = m.group(1)
    if mime not in PHOTO_TYPES:
        raise ProfileError("Fotoğraf JPEG, PNG ya da WebP olmalı.")
    try:
        blob = base64.b64decode(m.group(2), validate=False)
    except (binascii.Error, ValueError):
        raise ProfileError("Fotoğraf okunamadı.") from None
    if not blob:
        raise ProfileError("Fotoğraf boş.")
    if len(blob) > PHOTO_MAX_BYTES:
        raise ProfileError(f"Fotoğraf çok büyük ({len(blob) // 1024} kB); en fazla {PHOTO_MAX_BYTES // 1024} kB.")
    if not _magic_ok(blob, mime):
        raise ProfileError("Dosya içeriği bir görüntü değil.")
    version = int(time.time())
    _upsert(engine, tenant, user, photo=blob, photo_type=mime, photo_version=version)
    return version


def _magic_ok(blob: bytes, mime: str) -> bool:
    if mime == "image/jpeg":
        return blob[:3] == b"\xff\xd8\xff"
    if mime == "image/png":
        return blob[:8] == b"\x89PNG\r\n\x1a\n"
    if mime == "image/webp":
        return blob[:4] == b"RIFF" and blob[8:12] == b"WEBP"
    return False


def delete_photo(engine: sa.engine.Engine, tenant: str, user: str) -> None:
    with engine.begin() as c:
        c.execute(PROFILES.update().where(PROFILES.c.tenant_id == tenant, PROFILES.c.username == user.lower())
                  .values(photo=None, photo_type=None, updated_at=datetime.now(timezone.utc)))


def photo(engine: sa.engine.Engine, tenant: str, user: str) -> Optional[tuple[bytes, str]]:
    with engine.connect() as c:
        r = c.execute(sa.select(PROFILES.c.photo, PROFILES.c.photo_type).where(
            PROFILES.c.tenant_id == tenant, PROFILES.c.username == user.lower())).first()
    if not r or r.photo is None:
        return None
    return bytes(r.photo), r.photo_type or "image/jpeg"
