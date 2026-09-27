"""Yetki: kim hangi sayfayı görür.

Model (analiz: docs/analiz/yetki-mekanizmasi-2026-09-27.md): AD grubu / AD OU'su / CRM güvenlik rolü / tek kişi
→ rol → yetki anahtarları. Kişinin yetkisi bağlı olduğu rollerin **birleşimidir**; «yasak» kuralı yoktur.
Yönetici (`admin.is_admin`) her şeyi görür. «Herkes» sistem rolü giriş yapan herkese uygulanır ve kurulumda
«bütün yetkiler» açık gelir — 2026-09-27 kararı: roller prod öncesi atanır, o gün Herkes daraltılır.

Üyelikler istek yolunda okunmaz. AD grubu/OU üyeleri ve CRM rol sahipleri `semantic_access_members`
anlık görüntüsünden gelir; 15 dk'lık `timas-admin-group` zamanlayıcısı `refresh()` ile tazeler. Okunamayan
kaynağın eski görüntüsü silinmez, yalnız hatası yazılır.

Sayfa kapısı köprüdedir (`rule_for` + `page_allowed`); ön yüzdeki menü ve rota bu kapının yansımasıdır.
Kişi eşlemesi: AD'de `sAMAccountName` (küçük harf), CRM'de `DomainName`'in hesap kısmı — portal oturumu
da aynı adı taşır.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic_bridge.access")

_md = sa.MetaData()

ROLES = sa.Table(
    "semantic_access_roles", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(120), nullable=False),
    sa.Column("description", sa.Text),
    sa.Column("all_perms", sa.Boolean, nullable=False, default=False),   # bütün anahtarlar, sonradan eklenenler dahil
    sa.Column("is_system", sa.Boolean, nullable=False, default=False),   # Herkes: silinmez, adı değişmez
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

ROLE_PERMS = sa.Table(
    "semantic_access_role_perms", _md,
    sa.Column("role_id", sa.String(40), primary_key=True),
    sa.Column("perm", sa.String(120), primary_key=True),
)

BINDINGS = sa.Table(
    "semantic_access_bindings", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("role_id", sa.String(40), nullable=False, index=True),
    sa.Column("subject_type", sa.String(16), nullable=False),   # ad_group | ou | crm_role | user
    sa.Column("subject", sa.String(400), nullable=False),       # grup adı, OU DN, CRM kök rol kimliği, hesap adı
    sa.Column("label", sa.String(300)),                         # ekranda okunan ad
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "role_id", "subject_type", "subject", name="uq_access_binding"),
)

#: Grup/OU/CRM rolü → üye hesapları. Tenant'a bağlı değil: dizin tek.
MEMBERS = sa.Table(
    "semantic_access_members", _md,
    sa.Column("subject_type", sa.String(16), primary_key=True),
    sa.Column("subject", sa.String(400), primary_key=True),   # küçük harf
    sa.Column("members", sa.Text, nullable=False),             # JSON: küçük harf hesap adları
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("error", sa.Text),
)

SUBJECT_TYPES = {"ad_group": "AD grubu", "ou": "AD birimi (OU)", "crm_role": "CRM rolü", "user": "Kişi"}
EVERYONE_ID = "herkes"
CATALOG_FILE = Path(__file__).with_name("access_catalog.json")

_ready: set[int] = set()
_lock = threading.Lock()
_TTL = 30.0
_state: dict[str, Any] = {"at": 0.0, "key": None, "roles": {}, "bindings": [], "members": {}}


class AccessError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


# ------------------------------------------------------------------ katalog


_catalog_cache: dict[str, Any] = {}


def catalog() -> dict[str, Any]:
    if not _catalog_cache:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        data.pop("_note", None)
        _catalog_cache.update(data)
    return _catalog_cache


def all_keys() -> frozenset[str]:
    """Sayfa ve özellik anahtarlarının hepsi."""
    cat = catalog()
    return frozenset(p["key"] for p in cat["pages"]) | frozenset(f["key"] for f in cat.get("features", []))


def explicit_keys() -> frozenset[str]:
    """«Bütün sayfalar ve işlemler» ile gelmeyen, role tek tek verilen özellikler (bugüne kadar yalnız yöneticinin
    yaptığı işler). Kurulumda Herkes bütün yetkilerle açılırken kimsenin eski yetkisi bu yolla genişlemez."""
    return frozenset(f["key"] for f in catalog().get("features", []) if f.get("explicit"))


def page(item_id: str) -> str:
    return "sayfa:" + item_id


# ------------------------------------------------------------------ kurulum


def ensure(engine: sa.engine.Engine, tenant: str) -> None:
    """Tabloları kurar; tenant'ın «Herkes» rolü yoksa bütün yetkilerle açar."""
    key = (id(engine), tenant)
    with _lock:
        if key in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        with engine.begin() as c:
            found = c.execute(sa.select(ROLES.c.id).where(ROLES.c.id == _role_id(tenant, EVERYONE_ID))).first()
            if not found:
                now = _now()
                c.execute(ROLES.insert().values(
                    id=_role_id(tenant, EVERYONE_ID), tenant_id=tenant, name="Herkes",
                    description="Giriş yapan herkes. Roller atanana kadar bütün sayfaları görür; prod öncesi daraltılır.",
                    all_perms=True, is_system=True, created_by="sistem", created_at=now, updated_by="sistem", updated_at=now))
        _ready.add(key)


def _role_id(tenant: str, rid: str) -> str:
    # Herkes rolünün kimliği tenant başına sabit: kurulum yeniden koşunca ikinci kez açılmaz.
    return rid if tenant in ("", "default") else f"{rid}:{tenant}"[:40]


def invalidate() -> None:
    _state["at"] = 0.0


# ------------------------------------------------------------------ durum (30 sn bellek)


def _load(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    # Anahtar veritabanı + tenant: aynı süreçte iki veritabanı (testler, yönetim ekranının denemesi) birbirinin
    # rollerini görmesin.
    key = (id(engine), tenant)
    if _state["key"] == key and time.monotonic() - _state["at"] < _TTL:
        return _state
    with engine.connect() as c:
        roles = {r["id"]: {**dict(r), "perms": set()} for r in
                 c.execute(sa.select(ROLES).where(ROLES.c.tenant_id == tenant)).mappings()}
        for rid, perm in c.execute(sa.select(ROLE_PERMS.c.role_id, ROLE_PERMS.c.perm)
                                   .where(ROLE_PERMS.c.role_id.in_(list(roles) or [""]))).all():
            roles[rid]["perms"].add(perm)
        bindings = [dict(b) for b in c.execute(sa.select(BINDINGS).where(BINDINGS.c.tenant_id == tenant)).mappings()]
        members: dict[tuple[str, str], frozenset[str]] = {}
        for t, s, m in c.execute(sa.select(MEMBERS.c.subject_type, MEMBERS.c.subject, MEMBERS.c.members)).all():
            try:
                members[(t, s)] = frozenset(str(x).strip().lower() for x in json.loads(m or "[]") if str(x).strip())
            except ValueError:
                members[(t, s)] = frozenset()
    _state.update(at=time.monotonic(), key=key, roles=roles, bindings=bindings, members=members)
    return _state


# ------------------------------------------------------------------ etkin yetki


@dataclass
class Access:
    user: str
    admin: bool
    all: bool
    perms: frozenset[str]
    #: [{id, name, via: [«AD grubu: Satis_Group», …]}]
    roles: list[dict[str, Any]] = field(default_factory=list)

    def can(self, *keys: str) -> bool:
        """Anahtarlardan biri verilmiş mi. «Bütün» rolü açıkça verilen özellikleri kapsamaz."""
        return self.admin or any(k in self.granted() for k in keys)

    def granted(self) -> frozenset[str]:
        if self.admin:
            return all_keys()
        return (all_keys() - explicit_keys()) | self.perms if self.all else self.perms

    def view(self) -> dict[str, Any]:
        # `all` yalnız yöneticide doğru: ön yüz o zaman listeye bakmaz. «Bütün» rolünde bile açıkça verilen
        # özellikler listede yoksa kapalıdır; bu yüzden ön yüz her zaman `perms` listesini okur.
        return {"user": self.user, "isAdmin": self.admin, "all": self.admin, "allRoles": self.all,
                "perms": sorted(self.granted()), "roles": self.roles}


def effective(engine: sa.engine.Engine, tenant: str, user: str,
              is_admin: Callable[[str], bool]) -> Access:
    ensure(engine, tenant)
    u = (user or "").strip().lower()
    st = _load(engine, tenant)
    admin = bool(u) and is_admin(u)
    via: dict[str, list[str]] = {}
    for rid, r in st["roles"].items():
        if r["is_system"]:
            via.setdefault(rid, []).append("Giriş yapan herkes")
    for b in st["bindings"]:
        t, s = b["subject_type"], str(b["subject"]).strip().lower()
        hit = (u == s) if t == "user" else (u in st["members"].get((t, s), frozenset()))
        if hit and b["role_id"] in st["roles"]:
            via.setdefault(b["role_id"], []).append(f"{SUBJECT_TYPES.get(t, t)}: {b.get('label') or b['subject']}")
    perms: set[str] = set()
    every = False
    roles = []
    for rid, reasons in via.items():
        r = st["roles"][rid]
        every = every or bool(r["all_perms"])
        perms |= r["perms"]
        roles.append({"id": rid, "name": r["name"], "via": reasons})
    roles.sort(key=lambda x: x["name"].lower())
    return Access(user=u, admin=admin, all=every, perms=frozenset(perms & all_keys()), roles=roles)


_bound: dict[str, Any] = {}


def bind(engine: Callable[[], sa.engine.Engine], tenant: Callable[[], str], is_admin: Callable[[str], bool]) -> None:
    """Köprü açılışta bağlar: yetkiyi uç dışındaki modüller de (SEO onayı gibi) aynı hesapla sorsun."""
    _bound.update(engine=engine, tenant=tenant, is_admin=is_admin)


def user_can(user: Optional[str], key: str) -> bool:
    """Kişiye bu anahtar verilmiş mi (yönetici her şey). Köprü bağlanmadıysa ya da okunamazsa False."""
    if not user or not _bound:
        return False
    try:
        return effective(_bound["engine"](), _bound["tenant"](), user, _bound["is_admin"]).can(key)
    except Exception as e:  # noqa: BLE001
        log.warning("access: %s için %s okunamadı: %s", user, key, e)
        return False


# ------------------------------------------------------------------ köprü uçlarının sayfa kuralı

OPEN = "open"        # oturum yeter (ortak uçlar; kendi kontrolü varsa o da geçerli)
OWN = "own"          # uç kendi yetkisini denetler (yönetim, yetki)
SYSTEM = "system"    # yalnız zamanlayıcı/betik (çerezsiz) ya da yönetici

_SEO = frozenset(page(x) for x in ("seo-geo", "seo-arama", "seo-firsat", "seo-bing", "seo-rakip", "seo-ai", "seo-sayfalar",
                                   "seo-yonlendirme", "seo-teknik", "seo-kimlik", "seo-rehber", "seo-sema", "seo-llms",
                                   "seo-crm", "seo-urun", "seo-gecmis", "seo-baglanti"))
_EDITORIAL = frozenset(page(x) for x in ("editoryal", "yazar-giris", "yayin-kurulu", "redaksiyon", "cevirmenler",
                                         "son-okuma", "kitap-tasarim", "kisiler", "basin-web", "telif-sozlesme",
                                         "editor-atama"))

#: En uzun eşleşen önek kazanır. Yeni bir uç eklenince burada bir öneke düşmeli; düşmezse test kırılır
#: (test_access.py → köprünün bütün yolları). Ortak uçlar geniş tutuldu (bir sayfanın çağırdığı uç
#: başka sayfada da kullanılıyorsa ikisi de yazılır); işlem düzeyindeki daraltma Aşama B'nin işi.
RULES: list[tuple[str, Any]] = [
    ("/api/v1/access/", OWN),
    ("/api/v1/admin/", OWN),
    ("/api/v1/financial-audit/", frozenset({page("finansal-denetim")})),
    ("/api/v1/management/", frozenset({page("yonetim-raporlari"), page("baski-oneri")})),
    ("/api/v1/seo-geo/run-due", SYSTEM),
    ("/api/v1/seo-geo/", _SEO),
    ("/api/v1/reports/run-due", SYSTEM),
    ("/api/v1/reports", frozenset({page("planli-raporlar")})),
    ("/api/v1/alerts", frozenset({page("uyarilar"), page("genel-bakis")})),
    ("/api/v1/board/run-due", SYSTEM),
    ("/api/v1/board", frozenset({page("panolar"), page("genel-bakis")})),
    ("/api/v1/editorial/studio", frozenset({page("kitap-tasarim")})),
    ("/api/v1/editorial/web/run-due", SYSTEM),
    ("/api/v1/editorial/web/status", OPEN),        # menü: «Basın ve web» ortamda açık mı
    ("/api/v1/editorial/search", OPEN),            # ⌘K paletindeki kitap/kişi araması
    ("/api/v1/editorial/", _EDITORIAL),
    ("/api/v1/people", OPEN),                      # Kampüs rehberi
    ("/api/v1/me/", OPEN),
    ("/api/v1/greetings", OPEN),
    ("/api/v1/bulletins", OPEN),                   # Kampüs sesli bülteni (yazma /api/v1/admin/bulletins)
    ("/api/v1/rooms", OPEN),
    ("/api/v1/ask", OPEN),                         # veri kapsamı Aşama C'de SQL kapısında
    ("/api/v1/run_sql", OPEN),
    ("/api/v1/result/", OPEN),
    ("/api/v1/llm/", OPEN),
    ("/api/v1/engine", OPEN),
    ("/api/v1/feedback", OPEN),
    ("/api/v1/semantic/", OPEN),                   # yazan uçlar kendi yönetici kontrolünü yapar
    ("/api/v1/schema/", OPEN),
    ("/health", OPEN),
]
_RULES = sorted(RULES, key=lambda r: len(r[0]), reverse=True)


#: Sayfa içindeki işlemler: (yöntemler, yol deseni, anahtar). Sayfa kuralından SONRA bakılır; eşleşen her
#: desenin anahtarı istenir. Açıkça verilen (explicit) özellikler burada değil, ucun içinde denetlenir
#: (yönetici yerine «yönetici ya da bu yetki»).
_S = r"^/api/v1/editorial/studio/jobs"
FEATURE_RULES: list[tuple[frozenset[str], str, str]] = [
    (frozenset({"POST"}), r"^/api/v1/ask(/stream)?$", "ozellik:zeki.soru"),
    (frozenset({"GET"}), r"^/api/v1/(board/export\.xlsx|reports/[^/]+/file|financial-audit/runs/[^/]+/export"
                         r"|seo-geo/redirects/export\.csv|editorial/proofing/export\.docx|editorial/ask/export\.pdf)$",
     "ozellik:veri.disa-aktar"),
    (frozenset({"PUT"}), r"^/api/v1/board$", "ozellik:pano.duzenle"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/reports(/(?!run-due$)[^/]+(/run)?)?$", "ozellik:rapor.planla"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/alerts(/[^/]+)?$", "ozellik:uyari.kural"),
    (frozenset({"GET"}), r"^/api/v1/financial-audit/(lines|documents|runs/[^/]+/exceptions/.+)$", "ozellik:denetim.detay"),
    (frozenset({"POST"}), r"^/api/v1/financial-audit/runs/[^/]+/reviews/.+$", "ozellik:denetim.inceleme"),
    (frozenset({"POST"}), r"^/api/v1/financial-audit/refresh$", "ozellik:denetim.yenile"),
    (frozenset({"POST"}), r"^/api/v1/management/reports/[^/]+/refresh$", "ozellik:yonetim-raporu.yenile"),
    (frozenset({"POST"}), r"^/api/v1/editorial/books/[^/]+/review/decide$", "ozellik:kitap.inceleme-karar"),
    (frozenset({"POST"}), r"^/api/v1/editorial/proofing/decision$", "ozellik:son-okuma.karar"),
    (frozenset({"POST"}), _S + r"(/docx)?$", "ozellik:tasarim.uret"),
    (frozenset({"POST"}), _S + r"/[^/]+/(restart|resume|art/[^/]+/regenerate|plan/figures|plan/assets/[^/]+/(cutout|upscale)"
                               r"|coloring|coloring/retry|coloring/art/[^/]+/redraw|narration/run"
                               r"|collage/photos|marketing/[^/]+/generate)$", "ozellik:tasarim.uret"),
    (frozenset({"POST"}), r"^/api/v1/seo-geo/(products/[^/]+/propose|pages/[^/]+/[^/]+/propose|proposals/batch)$",
     "ozellik:seo.oneri-uret"),
    (frozenset({"POST", "DELETE"}), r"^/api/v1/seo-geo/(sync|crm/sync|schema/crawl|search/refresh|questions(/[^/]+)?)$",
     "ozellik:seo.calistir"),
]
_FEATURE_RULES = [(m, re.compile(rx), k) for m, rx, k in FEATURE_RULES]


def features_for(method: str, path: str) -> list[str]:
    """Bu isteğin istediği özellik anahtarları (sayfa kuralına ek)."""
    m = method.upper()
    return [k for methods, rx, k in _FEATURE_RULES if m in methods and rx.match(path)]


def rule_for(path: str) -> Any:
    """Yolun kuralı; hiçbir öneke düşmüyorsa None (test bunu yakalar, çalışırken kapı açık kalmaz: 403)."""
    for prefix, rule in _RULES:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return rule
    return None


# ------------------------------------------------------------------ roller ve bağlar (yönetim ekranı)


def _clean_perms(perms: Any) -> set[str]:
    keys = all_keys()
    out = {str(p) for p in (perms or []) if str(p) in keys}
    unknown = {str(p) for p in (perms or [])} - out
    if unknown:
        raise AccessError("Bilinmeyen yetki: " + ", ".join(sorted(unknown)))
    return out


def list_roles(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    ensure(engine, tenant)
    invalidate()
    st = _load(engine, tenant)
    snaps = _snapshots(engine)
    out = []
    for rid, r in st["roles"].items():
        binds = []
        for b in st["bindings"]:
            if b["role_id"] != rid:
                continue
            snap = snaps.get((b["subject_type"], str(b["subject"]).lower()))
            binds.append({"id": b["id"], "type": b["subject_type"], "typeLabel": SUBJECT_TYPES.get(b["subject_type"]),
                          "subject": b["subject"], "label": b.get("label") or b["subject"],
                          "members": (1 if b["subject_type"] == "user" else (snap or {}).get("count")),
                          "updatedAt": (snap or {}).get("updatedAt"), "error": (snap or {}).get("error"),
                          "createdBy": b.get("created_by"), "createdAt": _iso(b.get("created_at"))})
        binds.sort(key=lambda x: (x["type"], x["label"].lower()))
        out.append({"id": rid, "name": r["name"], "description": r.get("description") or "",
                    "allPerms": bool(r["all_perms"]), "system": bool(r["is_system"]),
                    "perms": sorted(r["perms"]), "bindings": binds,
                    "updatedBy": r.get("updated_by"), "updatedAt": _iso(r.get("updated_at"))})
    out.sort(key=lambda x: (not x["system"], x["name"].lower()))
    return out


def save_role(engine: sa.engine.Engine, tenant: str, actor: str, body: dict[str, Any],
              role_id: Optional[str] = None) -> dict[str, Any]:
    ensure(engine, tenant)
    name = " ".join(str(body.get("name") or "").split())[:120]
    desc = str(body.get("description") or "").strip()[:2000]
    perms = _clean_perms(body.get("perms"))
    all_perms = bool(body.get("allPerms"))
    now = _now()
    with engine.begin() as c:
        if role_id is None:
            if not name:
                raise AccessError("Rolün adı boş olamaz.")
            _unique_name(c, tenant, name, None)
            role_id = "rol_" + uuid.uuid4().hex[:20]
            c.execute(ROLES.insert().values(id=role_id, tenant_id=tenant, name=name, description=desc,
                                            all_perms=all_perms, is_system=False, created_by=actor, created_at=now,
                                            updated_by=actor, updated_at=now))
            before = None
        else:
            row = c.execute(sa.select(ROLES).where(ROLES.c.id == role_id, ROLES.c.tenant_id == tenant)).mappings().first()
            if not row:
                raise LookupError(role_id)
            if row["is_system"]:
                name = row["name"]                    # Herkes'in adı sabit
            elif not name:
                raise AccessError("Rolün adı boş olamaz.")
            else:
                _unique_name(c, tenant, name, role_id)
            before = {"name": row["name"], "allPerms": bool(row["all_perms"]),
                      "perms": sorted(p for (p,) in c.execute(sa.select(ROLE_PERMS.c.perm)
                                                               .where(ROLE_PERMS.c.role_id == role_id)).all())}
            c.execute(ROLES.update().where(ROLES.c.id == role_id).values(
                name=name, description=desc, all_perms=all_perms, updated_by=actor, updated_at=now))
            c.execute(ROLE_PERMS.delete().where(ROLE_PERMS.c.role_id == role_id))
        if perms:
            c.execute(ROLE_PERMS.insert(), [{"role_id": role_id, "perm": p} for p in sorted(perms)])
    invalidate()
    after = {"name": name, "allPerms": all_perms, "perms": sorted(perms)}
    return {"id": role_id, "before": before, "after": after}


def _unique_name(c: Any, tenant: str, name: str, role_id: Optional[str]) -> None:
    q = sa.select(ROLES.c.id).where(ROLES.c.tenant_id == tenant, sa.func.lower(ROLES.c.name) == name.lower())
    if role_id:
        q = q.where(ROLES.c.id != role_id)
    if c.execute(q).first():
        raise AccessError(f"«{name}» adında bir rol zaten var.")


def delete_role(engine: sa.engine.Engine, tenant: str, role_id: str) -> Optional[dict[str, Any]]:
    ensure(engine, tenant)
    with engine.begin() as c:
        row = c.execute(sa.select(ROLES).where(ROLES.c.id == role_id, ROLES.c.tenant_id == tenant)).mappings().first()
        if not row:
            return None
        if row["is_system"]:
            raise AccessError("«Herkes» rolü silinemez; yetkilerini daraltabilirsiniz.")
        c.execute(BINDINGS.delete().where(BINDINGS.c.role_id == role_id))
        c.execute(ROLE_PERMS.delete().where(ROLE_PERMS.c.role_id == role_id))
        c.execute(ROLES.delete().where(ROLES.c.id == role_id))
    invalidate()
    return dict(row)


def add_binding(engine: sa.engine.Engine, tenant: str, actor: str, role_id: str, body: dict[str, Any]) -> dict[str, Any]:
    ensure(engine, tenant)
    t = str(body.get("type") or "")
    if t not in SUBJECT_TYPES:
        raise AccessError("Bağ türü AD grubu, AD birimi, CRM rolü ya da kişi olmalı.")
    subject = str(body.get("subject") or "").strip()
    if not subject or len(subject) > 400:
        raise AccessError("Bağlanacak grup, birim, rol ya da kişi seçilmedi.")
    if t == "user":
        subject = subject.lower()
    label = " ".join(str(body.get("label") or subject).split())[:300]
    with engine.begin() as c:
        role = c.execute(sa.select(ROLES).where(ROLES.c.id == role_id, ROLES.c.tenant_id == tenant)).mappings().first()
        if not role:
            raise LookupError(role_id)
        if role["is_system"]:
            raise AccessError("«Herkes» rolü herkese uygulanır; ona bağ eklenmez.")
        dup = c.execute(sa.select(BINDINGS.c.id).where(
            BINDINGS.c.tenant_id == tenant, BINDINGS.c.role_id == role_id, BINDINGS.c.subject_type == t,
            sa.func.lower(BINDINGS.c.subject) == subject.lower())).first()
        if dup:
            raise AccessError(f"«{label}» bu role zaten bağlı.")
        bid = "bag_" + uuid.uuid4().hex[:20]
        c.execute(BINDINGS.insert().values(id=bid, tenant_id=tenant, role_id=role_id, subject_type=t, subject=subject,
                                           label=label, created_by=actor, created_at=_now()))
    invalidate()
    return {"id": bid, "role": role["name"], "type": t, "subject": subject, "label": label}


def delete_binding(engine: sa.engine.Engine, tenant: str, binding_id: str) -> Optional[dict[str, Any]]:
    ensure(engine, tenant)
    with engine.begin() as c:
        row = c.execute(sa.select(BINDINGS, ROLES.c.name.label("role")).select_from(
            BINDINGS.join(ROLES, ROLES.c.id == BINDINGS.c.role_id)).where(
            BINDINGS.c.id == binding_id, BINDINGS.c.tenant_id == tenant)).mappings().first()
        if not row:
            return None
        c.execute(BINDINGS.delete().where(BINDINGS.c.id == binding_id))
    invalidate()
    return dict(row)


# ------------------------------------------------------------------ üye görüntüsü (AD / CRM)


def _snapshots(engine: sa.engine.Engine) -> dict[tuple[str, str], dict[str, Any]]:
    out = {}
    with engine.connect() as c:
        for t, s, m, at, err in c.execute(sa.select(MEMBERS.c.subject_type, MEMBERS.c.subject, MEMBERS.c.members,
                                                    MEMBERS.c.updated_at, MEMBERS.c.error)).all():
            try:
                n = len(json.loads(m or "[]"))
            except ValueError:
                n = 0
            out[(t, s)] = {"count": n, "updatedAt": _iso(at), "error": err}
    return out


def _write_snapshot(engine: sa.engine.Engine, t: str, subject: str, members: Optional[set[str]],
                    error: Optional[str]) -> None:
    key = subject.strip().lower()
    with engine.begin() as c:
        exists = c.execute(sa.select(MEMBERS.c.subject).where(MEMBERS.c.subject_type == t,
                                                              MEMBERS.c.subject == key)).first()
        if members is None:                     # okunamadı: eski üyeler korunur
            if exists:
                c.execute(MEMBERS.update().where(MEMBERS.c.subject_type == t, MEMBERS.c.subject == key)
                          .values(error=(error or "")[:400]))
            else:
                c.execute(MEMBERS.insert().values(subject_type=t, subject=key, members="[]", updated_at=None,
                                                  error=(error or "")[:400]))
            return
        body = json.dumps(sorted(members), ensure_ascii=False)
        if exists:
            c.execute(MEMBERS.update().where(MEMBERS.c.subject_type == t, MEMBERS.c.subject == key)
                      .values(members=body, updated_at=_now(), error=None))
        else:
            c.execute(MEMBERS.insert().values(subject_type=t, subject=key, members=body, updated_at=_now(), error=None))


def refresh(engine: sa.engine.Engine, directory: "Directory", only: Optional[tuple[str, str]] = None) -> dict[str, Any]:
    """Bağı olan her AD grubunun, OU'nun ve CRM rolünün üyelerini okuyup görüntüye yazar.
    Zamanlayıcı (15 dk) ve yönetim ekranı çağırır; istek yolunda değil. `only` yalnız o bağı okur."""
    _md.create_all(engine, checkfirst=True)
    with engine.connect() as c:
        subjects = sorted({(t, str(s)) for t, s in c.execute(
            sa.select(BINDINGS.c.subject_type, BINDINGS.c.subject).where(BINDINGS.c.subject_type != "user")).all()})
    if only is not None:
        subjects = [x for x in subjects if (x[0], x[1].lower()) == (only[0], only[1].lower())] or [only]
    done, failed = 0, []
    crm_roles: Optional[dict[str, set[str]]] = None
    crm_error: Optional[str] = None
    for t, s in subjects:
        try:
            if t == "ad_group":
                members: Optional[set[str]] = directory.group_members(s)
            elif t == "ou":
                members = directory.ou_members(s)
            elif t == "crm_role":
                if crm_roles is None and crm_error is None:
                    try:
                        crm_roles = directory.crm_role_members()
                    except Exception as e:  # noqa: BLE001
                        crm_error = f"{type(e).__name__}: {e}"[:400]
                if crm_roles is None:
                    raise RuntimeError(crm_error or "CRM okunamadı")
                members = crm_roles.get(s.lower(), set())
            else:
                continue
            _write_snapshot(engine, t, s, members, None)
            done += 1
        except Exception as e:  # noqa: BLE001
            msg = f"{type(e).__name__}: {e}"[:400]
            log.warning("access: %s %s okunamadı, eski üyeler korunuyor: %s", t, s, msg)
            _write_snapshot(engine, t, s, None, msg)
            failed.append({"type": t, "subject": s, "error": msg})
    invalidate()
    return {"ok": not failed, "refreshed": done, "failed": failed}


class Directory:
    """AD ve CRM'den okuma. Testte sahtesi verilir; gerçeği `admin` modülünün AD ayarını ve CRM bağlantı
    dosyasını kullanır."""

    def __init__(self, ad_conf: Callable[[], dict[str, str]], crm_schema: Callable[[], str],
                 crm_file: Optional[str] = None):
        self._ad_conf = ad_conf
        self._crm_schema = crm_schema
        self._crm_file = crm_file or os.environ.get("SEMANTIC_CRM_CONNECTION_FILE",
                                                    "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
        self._cache: dict[str, tuple[float, Any]] = {}
        self._clock = threading.Lock()

    # -- AD
    def _ad(self):
        from ldap3 import NONE, NTLM, Connection, Server  # type: ignore[import-not-found]

        from semantic_bridge.admin import _ensure_md4

        cfg = self._ad_conf()
        missing = [k for k in ("AD_HOST", "AD_NETBIOS", "AD_BASE_DN", "AD_BIND_USER", "AD_BIND_PASSWORD") if not cfg.get(k)]
        if missing:
            raise RuntimeError("AD ayarı eksik: " + ", ".join(missing))
        _ensure_md4()
        server = Server(cfg["AD_HOST"], port=int(cfg.get("AD_PORT") or 389), get_info=NONE, connect_timeout=5)
        conn = Connection(server, user=f'{cfg["AD_NETBIOS"]}\\{cfg["AD_BIND_USER"]}', password=cfg["AD_BIND_PASSWORD"],
                          authentication=NTLM, receive_timeout=30)
        if not conn.bind():
            raise RuntimeError(f"AD servis hesabı reddedildi: {conn.result.get('description')}")
        return conn, cfg["AD_BASE_DN"]

    def _search(self, flt: str, attrs: list[str], base: Optional[str] = None) -> list[dict[str, Any]]:
        from ldap3 import SUBTREE  # type: ignore[import-not-found]

        conn, root = self._ad()
        try:
            found = conn.extend.standard.paged_search(base or root, flt, SUBTREE, attributes=attrs,
                                                      paged_size=500, generator=True)
            return [dict(e.get("attributes") or {}, _dn=e.get("dn")) for e in found if e.get("type") == "searchResEntry"]
        finally:
            conn.unbind()

    def _group_dn(self, group: str) -> str:
        from semantic_bridge.admin import _ldap_escape

        if group.lower().startswith(("cn=", "ou=")) and "dc=" in group.lower():
            return group
        esc = _ldap_escape(group)
        rows = self._search(f"(&(objectClass=group)(|(sAMAccountName={esc})(cn={esc})))", ["distinguishedName"])
        if not rows:
            raise RuntimeError(f"«{group}» grubu AD'de bulunamadı")
        return str(rows[0]["_dn"])

    def group_members(self, group: str) -> set[str]:
        from semantic_bridge.admin import _ldap_escape

        dn = self._group_dn(group)
        rows = self._search(f"(&{_PERSON}(memberOf:1.2.840.113556.1.4.1941:={_ldap_escape(dn)}))", ["sAMAccountName"])
        return {_first(r.get("sAMAccountName")).lower() for r in rows} - {""}

    def ou_members(self, ou_dn: str) -> set[str]:
        rows = self._search(_PERSON, ["sAMAccountName"], base=ou_dn)
        return {_first(r.get("sAMAccountName")).lower() for r in rows} - {""}

    def _cached(self, key: str, ttl: float, fn: Callable[[], Any]) -> Any:
        with self._clock:
            hit = self._cache.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
        val = fn()
        with self._clock:
            self._cache[key] = (time.monotonic(), val)
        return val

    def list_groups(self) -> list[dict[str, Any]]:
        """Güvenlik grupları (dağıtım listeleri ve Windows'un yerleşik grupları hariç), doğrudan üye sayısıyla."""
        def read() -> list[dict[str, Any]]:
            # Windows'un kendi grupları (Domain Admins, RODC, DnsAdmins…) isCriticalSystemObject taşır; listeye girmez.
            rows = self._search("(&(objectClass=group)(groupType:1.2.840.113556.1.4.803:=2147483648)"
                                "(!(isCriticalSystemObject=TRUE)))",
                                ["sAMAccountName", "description", "member", "groupType"])
            out = []
            for r in rows:
                gt = int(_first(r.get("groupType")) or 0) & 0xFFFFFFFF
                dn = str(r.get("_dn") or "")
                if gt & 1 or ",CN=Builtin," in dn:
                    continue
                name = _first(r.get("sAMAccountName"))
                if name:
                    parent = dn.split(",", 1)[1] if "," in dn else ""
                    out.append({"subject": name, "label": name, "hint": _ou_path(parent),
                                "detail": _first(r.get("description")), "count": len(r.get("member") or [])})
            return sorted(out, key=lambda x: x["label"].lower())
        return self._cached("groups", 300.0, read)

    def list_ous(self) -> list[dict[str, Any]]:
        """Etkin kişisi olan OU'lar, kişi sayısıyla (kişinin doğrudan bulunduğu OU)."""
        def read() -> list[dict[str, Any]]:
            counts: dict[str, int] = {}
            for r in self._search(_PERSON, ["sAMAccountName"]):
                dn = str(r.get("_dn") or "")
                parent = dn.split(",", 1)[1] if "," in dn else ""
                if parent.upper().startswith("OU="):
                    counts[parent] = counts.get(parent, 0) + 1
            return sorted(({"subject": ou, "label": _ou_name(ou), "hint": _ou_path(ou), "count": n}
                           for ou, n in counts.items()), key=lambda x: x["label"].lower())
        return self._cached("ous", 300.0, read)

    def list_people(self) -> list[dict[str, Any]]:
        def read() -> list[dict[str, Any]]:
            out = []
            for r in self._search(_PERSON, ["sAMAccountName", "displayName"]):
                acc = _first(r.get("sAMAccountName")).lower()
                if acc:
                    out.append({"subject": acc, "label": _first(r.get("displayName")) or acc, "hint": acc,
                                "detail": _ou_name(str(r.get("_dn") or "").split(",", 1)[-1])})
            return sorted(out, key=lambda x: x["label"].lower())
        return self._cached("people", 300.0, read)

    def user_groups(self, user: str) -> list[str]:
        """Kişinin (iç içe dahil) AD grupları — «kişi gözüyle» ekranı için; canlı okunur."""
        from semantic_bridge.admin import _ldap_escape

        rows = self._search(f"(&{_PERSON}(sAMAccountName={_ldap_escape(user)}))", ["distinguishedName"])
        if not rows:
            return []
        dn = str(rows[0]["_dn"])
        groups = self._search(f"(&(objectClass=group)(member:1.2.840.113556.1.4.1941:={_ldap_escape(dn)}))",
                              ["sAMAccountName"])
        return sorted({_first(g.get("sAMAccountName")) for g in groups} - {""}, key=str.lower)

    # -- CRM
    def _crm_rows(self, sql: str) -> list[dict[str, Any]]:
        from semantic_layer.profiler.connectors import connector_from_file

        if not os.path.exists(self._crm_file):
            raise RuntimeError("CRM bağlantı dosyası bulunamadı")
        conn = connector_from_file(self._crm_file)
        try:
            _, rows, _ = conn.execute(sql, 100_000)
            return rows
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass

    def _crm_prefix(self) -> str:
        schema = (self._crm_schema() or "").strip()
        if not schema:
            raise RuntimeError("CRM şeması girilmemiş")
        for part in schema.split("."):
            if not part or not all(ch.isalnum() or ch in "_-$" for ch in part):
                raise RuntimeError(f"CRM şeması «{schema}» geçerli bir ad değil")
        return schema + "."

    def crm_role_members(self) -> dict[str, set[str]]:
        """Kök rol kimliği (küçük harf) → rolü taşıyan etkin CRM kullanıcılarının hesap adları.
        CRM rolü her iş biriminde bir kopya olarak durur; kişi kopyaya atanır, kopya kök role `ParentRootRoleId` ile bağlıdır."""
        p = self._crm_prefix()
        rows = self._crm_rows(
            f"SELECT CAST(r.ParentRootRoleId AS nvarchar(40)) AS RootId, u.DomainName "
            f"FROM {p}SystemUserRoles sur JOIN {p}RoleBase r ON r.RoleId = sur.RoleId "
            f"JOIN {p}SystemUserBase u ON u.SystemUserId = sur.SystemUserId "
            f"WHERE u.IsDisabled = 0 AND u.AccessMode IN (0, 1) AND u.DomainName IS NOT NULL AND u.DomainName <> ''")
        out: dict[str, set[str]] = {}
        for r in rows:
            acc = _account(r.get("DomainName"))
            rid = str(r.get("RootId") or "").strip("{}").lower()
            if acc and rid:
                out.setdefault(rid, set()).add(acc)
        return out

    def list_crm_roles(self) -> list[dict[str, Any]]:
        def read() -> list[dict[str, Any]]:
            p = self._crm_prefix()
            rows = self._crm_rows(f"SELECT CAST(RoleId AS nvarchar(40)) AS RoleId, Name FROM {p}RoleBase "
                                  f"WHERE ParentRoleId IS NULL")
            members = self.crm_role_members()
            out = []
            for r in rows:
                rid = str(r.get("RoleId") or "").strip("{}").lower()
                name = str(r.get("Name") or "").strip()
                if rid and name:
                    out.append({"subject": rid, "label": name, "hint": "", "count": len(members.get(rid, ()))})
            return sorted(out, key=lambda x: (-x["count"], x["label"].lower()))
        return self._cached("crm_roles", 300.0, read)

    def user_crm_roles(self, user: str) -> list[str]:
        roles = {x["subject"]: x["label"] for x in self.list_crm_roles()}
        mine = [rid for rid, accs in self.crm_role_members().items() if user.lower() in accs]
        return sorted((roles.get(r, r) for r in mine), key=str.lower)

    def candidates(self, t: str) -> list[dict[str, Any]]:
        if t == "ad_group":
            return self.list_groups()
        if t == "ou":
            return self.list_ous()
        if t == "crm_role":
            return self.list_crm_roles()
        if t == "user":
            return self.list_people()
        raise AccessError("Bilinmeyen bağ türü.")


_PERSON = "(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"


def _first(v: Any) -> str:
    if isinstance(v, (list, tuple)):
        v = next((x for x in v if x not in (None, "")), "")
    return "" if v is None else str(v).strip()


def _account(domain_name: Any) -> str:
    s = _first(domain_name).rsplit("\\", 1)[-1].split("@", 1)[0]
    return s.strip().lower()


def _ou_name(dn: str) -> str:
    first = dn.split(",", 1)[0]
    k, _, v = first.partition("=")
    return v.strip() if k.strip().upper() == "OU" else dn


def _ou_path(dn: str) -> str:
    """`OU=Satis,OU=Merkez,DC=…` → `Merkez / Satis` (etki alanı parçaları olmadan)."""
    parts = [p.split("=", 1)[1] for p in dn.split(",") if p.upper().startswith(("OU=", "CN=")) and "=" in p]
    return " / ".join(reversed(parts))


# ------------------------------------------------------------------ kişi gözüyle


def explain(engine: sa.engine.Engine, tenant: str, user: str, is_admin: Callable[[str], bool],
            directory: Optional[Directory]) -> dict[str, Any]:
    acc = effective(engine, tenant, user, is_admin)
    groups: list[str] = []
    crm: list[str] = []
    notes: list[str] = []
    if directory is not None:
        try:
            groups = directory.user_groups(acc.user)
        except Exception as e:  # noqa: BLE001
            notes.append(f"AD okunamadı: {type(e).__name__}")
        try:
            crm = directory.user_crm_roles(acc.user)
        except Exception as e:  # noqa: BLE001
            notes.append(f"CRM okunamadı: {type(e).__name__}")
    cat = catalog()
    keys = acc.granted()
    pages = [{**p, "allowed": p["key"] in keys} for p in cat["pages"]]
    features = [{**f, "allowed": f["key"] in keys} for f in cat.get("features", [])]
    return {**acc.view(), "adGroups": groups, "crmRoles": crm, "pages": pages, "features": features, "notes": notes}
