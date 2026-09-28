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
from contextlib import contextmanager
from contextvars import ContextVar
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
#: Yöneticinin ekrandan verdiği varlık → veri alanı ataması; `data_domains.json` kuralının önüne geçer.
ENTITY_DOMAINS = sa.Table(
    "semantic_access_entity_domains", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("entity", sa.String(200), primary_key=True),
    sa.Column("domain", sa.String(40), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

EVERYONE_ID = "herkes"
CATALOG_FILE = Path(__file__).with_name("access_catalog.json")
DOMAINS_FILE = Path(__file__).with_name("data_domains.json")

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
    """Sayfa, özellik ve veri alanı anahtarlarının hepsi."""
    cat = catalog()
    return (frozenset(p["key"] for p in cat["pages"]) | frozenset(f["key"] for f in cat.get("features", []))
            | frozenset(data_key(d["id"]) for d in data_domains() if not d.get("always")))


def explicit_keys() -> frozenset[str]:
    """«Bütün sayfalar ve işlemler» ile gelmeyen, role tek tek verilen özellikler (bugüne kadar yalnız yöneticinin
    yaptığı işler). Kurulumda Herkes bütün yetkilerle açılırken kimsenin eski yetkisi bu yolla genişlemez."""
    return frozenset(f["key"] for f in catalog().get("features", []) if f.get("explicit"))


# ------------------------------------------------------------------ veri alanları (Aşama C)
#
# ZEKİ AI'ın hangi tabloları okuyabileceği. Kataloğun her varlığı bir alana düşer (kural dosyası + yöneticinin
# ekrandan ataması); rol `veri:<alan>` anahtarlarını taşır. Kapı SQL'in çalıştığı tek geçittedir
# (`Runtime._check_data_scope`): istek kişinin alanlarını `DATA_ALLOWED` bağlamında taşır, kapsam dışı varlık
# okuyan SQL çalışmaz. Bağlam boşsa (zamanlayıcı dışı sistem işi, yönetici) sınır yoktur.

_domains_cache: dict[str, Any] = {}


def _domains_data() -> dict[str, Any]:
    if not _domains_cache:
        data = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
        data["_rules"] = [(r["domain"], r.get("source", "any"), re.compile(r["pattern"])) for r in data["rules"]]
        _domains_cache.update(data)
    return _domains_cache


def data_domains() -> list[dict[str, Any]]:
    return [dict(d) for d in _domains_data()["domains"]]


def data_key(domain_id: str) -> str:
    return "veri:" + domain_id


def always_domains() -> frozenset[str]:
    return frozenset(d["id"] for d in _domains_data()["domains"] if d.get("always"))


def _norm_entity(name: str) -> str:
    n = (name or "").upper()
    changed = True
    while changed:
        changed = False
        for pre in _domains_data()["strip_prefixes"]:
            if n.startswith(pre) and len(n) > len(pre):
                n, changed = n[len(pre):], True
    return n


def rule_domain(entity: str, source: str) -> str:
    """Kural dosyasına göre alan; hiçbir kural tutmazsa 'atanmamis'."""
    n = _norm_entity(entity)
    for domain, src, rx in _domains_data()["_rules"]:
        if src in ("any", source) and rx.search(n):
            return domain
    return "atanmamis"


_ent_cache: dict[str, Any] = {"key": None, "at": 0.0, "map": {}}


def entity_domains(engine: sa.engine.Engine, tenant: str, profiles: list[Any]) -> dict[str, str]:
    """Varlık (büyük harf) → alan. Yönetici ataması kuralın önüne geçer. 30 sn bellek."""
    from semantic_layer.data_source import data_source

    key = (id(engine), tenant, len(profiles), id(profiles))
    if _ent_cache["key"] == key and time.monotonic() - _ent_cache["at"] < _TTL:
        return _ent_cache["map"]
    _md.create_all(engine, checkfirst=True)
    with engine.connect() as c:
        over = {str(e).upper(): d for e, d in c.execute(sa.select(ENTITY_DOMAINS.c.entity, ENTITY_DOMAINS.c.domain)
                                                         .where(ENTITY_DOMAINS.c.tenant_id == tenant)).all()}
    out: dict[str, str] = {}
    for p in profiles:
        e = p.entity.upper()
        if e not in out:
            out[e] = over.get(e) or rule_domain(p.entity, data_source(getattr(p, "schema_name", None)))
    _ent_cache.update(key=key, at=time.monotonic(), map=out)
    return out


def set_entity_domain(engine: sa.engine.Engine, tenant: str, actor: str, entity: str, domain: Optional[str]) -> None:
    """Yöneticinin ataması; `domain` None ise atama kalkar, kural geçerli olur."""
    ids = {d["id"] for d in data_domains()}
    if domain is not None and domain not in ids:
        raise AccessError("Bilinmeyen veri alanı.")
    _md.create_all(engine, checkfirst=True)
    e = (entity or "").strip().upper()
    if not e:
        raise AccessError("Varlık seçilmedi.")
    with engine.begin() as c:
        c.execute(ENTITY_DOMAINS.delete().where(ENTITY_DOMAINS.c.tenant_id == tenant, ENTITY_DOMAINS.c.entity == e))
        if domain is not None:
            c.execute(ENTITY_DOMAINS.insert().values(tenant_id=tenant, entity=e, domain=domain, updated_by=actor,
                                                     updated_at=_now()))
    _ent_cache["key"] = None


def domain_listing(engine: sa.engine.Engine, tenant: str, profiles: list[Any]) -> list[dict[str, Any]]:
    """Yönetim ekranı: her varlık, kaynağı, satır sayısı, alanı ve alanın nereden geldiği (kural / ekran)."""
    from semantic_layer.data_source import data_source

    emap = entity_domains(engine, tenant, profiles)
    with engine.connect() as c:
        over = {str(e).upper() for (e,) in c.execute(sa.select(ENTITY_DOMAINS.c.entity)
                                                     .where(ENTITY_DOMAINS.c.tenant_id == tenant)).all()}
    seen: dict[str, dict[str, Any]] = {}
    for p in profiles:
        e = p.entity.upper()
        row = seen.get(e)
        if row is None:
            row = seen[e] = {"entity": p.entity, "source": data_source(getattr(p, "schema_name", None)),
                             "description": getattr(p, "description", None) or "", "rows": 0, "tables": 0,
                             "domain": emap.get(e, "atanmamis"), "manual": e in over}
        row["rows"] += int(getattr(p, "row_count", 0) or 0)
        row["tables"] += 1
    return sorted(seen.values(), key=lambda r: (-r["rows"], r["entity"]))


#: İsteği yapan kişinin okuyabileceği veri alanları; None = sınır yok (yönetici, sistem işi).
DATA_ALLOWED: ContextVar[Optional[frozenset[str]]] = ContextVar("access_data_allowed", default=None)


class DataScopeError(PermissionError):
    """SQL, kişinin rolünde olmayan bir veri alanını okuyor. Mesaj ekranda olduğu gibi gösterilir."""

    def __init__(self, domains: list[str]):
        self.domains = domains
        names = ", ".join(f"«{d}»" for d in domains)
        super().__init__(f"Bu soru {names} verisine dayanıyor; bu veri rolünüzde yok. Erişim için bir yöneticiye başvurun.")


def allowed_domains(acc: "Access") -> Optional[frozenset[str]]:
    """Kişinin okuyabileceği alanlar; yöneticide None (sınır yok). Ortak başvuru alanları her zaman açık."""
    if acc.admin:
        return None
    granted = acc.granted()
    return frozenset(d["id"] for d in data_domains() if d.get("always") or data_key(d["id"]) in granted)


def check_entities(entities: set[str], emap: dict[str, str], allowed: Optional[frozenset[str]]) -> None:
    if allowed is None:
        return
    labels = {d["id"]: d["label"] for d in data_domains()}
    missing = sorted({emap.get(e.upper(), "atanmamis") for e in entities} - allowed)
    if missing:
        raise DataScopeError([labels.get(m, m) for m in missing])


def allowed_for(user: Optional[str]) -> Optional[frozenset[str]]:
    """Kişinin alanları (zamanlayıcı, sahibinin adına koşarken). Kişi yoksa ya da yetki okunamazsa hiçbir alan."""
    if not _bound or not user:
        return frozenset(always_domains()) if _bound else None
    try:
        return allowed_domains(effective(_bound["engine"](), _bound["tenant"](), user, _bound["is_admin"]))
    except Exception as e:  # noqa: BLE001
        log.warning("access: %s için veri kapsamı okunamadı, kapalı sayıldı: %s", user, e)
        return frozenset(always_domains())


@contextmanager
def acting_as(user: Optional[str]):
    """Zamanlayıcıdaki kart/rapor/uyarı sahibinin veri kapsamıyla koşar: yetkisi daralan kişinin raporu da daralır."""
    token = DATA_ALLOWED.set(allowed_for(user))
    try:
        yield
    finally:
        DATA_ALLOWED.reset(token)


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
                                   "seo-crm", "seo-urun", "seo-gecmis", "seo-baglanti",
                                   "seo-izleme", "seo-kaynak", "seo-yarisan", "seo-tarama", "seo-geri-baglanti", "seo-takvim", "seo-ic-baglanti", "seo-yorum", "seo-video", "seo-kalkan", "seo-yazar-sayfa",
                                   "seo-isler", "seo-karne", "seo-biyografi", "seo-sss", "seo-benzer", "seo-eslesme", "seo-soru", "seo-youtube", "seo-alisveris", "seo-aylik"))
_EDITORIAL = frozenset(page(x) for x in ("editoryal", "yazar-giris", "basvurular", "yayin-kurulu", "redaksiyon", "cevirmenler",
                                         "son-okuma", "kitap-tasarim", "kapak-arsivi", "kisiler", "yazar-iliskileri", "basin-web", "telif-sozlesme",
                                         "editor-atama", "gorevlerim", "serbest-calisanlar", "uretim"))

_CATEGORY_READERS = frozenset({page("kategori-agaci"), page("editor-atama"), page("yayin-kurulu"),
                               page("yazar-giris")}) | _SEO

#: En uzun eşleşen önek kazanır. Yeni bir uç eklenince burada bir öneke düşmeli; düşmezse test kırılır
#: (test_access.py → köprünün bütün yolları). Ortak uçlar geniş tutuldu (bir sayfanın çağırdığı uç
#: başka sayfada da kullanılıyorsa ikisi de yazılır); işlem düzeyindeki daraltma Aşama B'nin işi.
RULES: list[tuple[str, Any]] = [
    ("/api/v1/access/", OWN),
    ("/api/v1/admin/", OWN),
    ("/api/v1/financial-audit/", frozenset({page("finansal-denetim")})),
    ("/api/v1/management/", frozenset({page("yonetim-raporlari"), page("baski-oneri")})),
    # M46 Bütçe. Onaylı hedefleri okuyacak modül (M15/M17/M18/M29/M30) kendi sayfa anahtarını targets/deviations
    # satırlarına ekler; yazma uçları butce sayfasında kalır.
    ("/api/v1/budget/run-due", SYSTEM),
    ("/api/v1/budget/targets", frozenset({page("butce"), page("ilk-dagilim"), page("saha"), page("pazarlama-yeni-kitap")})),
    ("/api/v1/budget/deviations", frozenset({page("butce"), page("ilk-dagilim"), page("saha"), page("pazarlama-yeni-kitap")})),
    ("/api/v1/budget/", frozenset({page("butce")})),
    ("/api/v1/management/first-print/", frozenset({page("ilk-baski")})),
    # M29 İlk dağılım (Satış ve saha). Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/distribution/run-due", SYSTEM),
    ("/api/v1/distribution/", frozenset({page("ilk-dagilim")})),
    # M30 Saha satış ve tahsilat. Ziyaret kaydı M30/M31 ortak (semantic_saha_ziyaret): okul tanıtım sayfası da okur/yazar.
    ("/api/v1/field/run-due", SYSTEM),
    ("/api/v1/field/visits", frozenset({page("saha"), page("okul-tanitim")})),
    ("/api/v1/field/", frozenset({page("saha")})),
    ("/api/v1/pricing/", frozenset({page("fiyatlama")})),
    # M33 İhale takibi (Satış ve saha). Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/tenders/run-due", SYSTEM),
    ("/api/v1/tenders/", frozenset({page("ihale")})),
    # M19 Pazarlama görsel ve metin. Onaylı varlık sözleşmesini (contract/assets) okuyacak modül (M21/M22/M24) kendi
    # sayfa anahtarını o satıra ekler. M15'in genel «/api/v1/marketing/» satırından önce durur (en uzun önek kazanır;
    # sıra okunurluk içindir).
    ("/api/v1/marketing/creative/run-due", SYSTEM),
    ("/api/v1/marketing/creative/contract/", frozenset({page("pazarlama-icerik")})),
    ("/api/v1/marketing/creative/", frozenset({page("pazarlama-icerik")})),
    # Pazarlama çekirdeği (M15; M16–M18 kendi sayfa anahtarlarını buraya ve sözleşme satırına ekler).
    # M53 Set, hediye ve promosyon (Pazarlama → Üretim).
    ("/api/v1/marketing/sets/run-due", SYSTEM),
    ("/api/v1/marketing/sets/", frozenset({page("pazarlama-set-hediye")})),
    ("/api/v1/marketing/gift-offers/", frozenset({page("pazarlama-set-hediye")})),
    ("/api/v1/marketing/promo-items", frozenset({page("pazarlama-set-hediye")})),
    ("/api/v1/marketing/run-due", SYSTEM),
    ("/api/v1/marketing/contract/", frozenset({page("pazarlama-yeni-kitap")})),
    ("/api/v1/marketing/", frozenset({page("pazarlama-yeni-kitap")})),
    # H1 Kategori ağacı. Sözleşme uçlarını (kitap profili, yürürlükteki ağaç ve düğümün kitapları) M1 başvuru
    # değerlendirmesi, M2 editör atama ve SEO sayfaları da okur; yazma uçları kategori-agaci sayfasında kalır.
    ("/api/v1/categories/run-due", SYSTEM),
    ("/api/v1/categories/profile/", _CATEGORY_READERS),
    ("/api/v1/categories/nodes", _CATEGORY_READERS),
    ("/api/v1/categories/", frozenset({page("kategori-agaci")})),
    ("/api/v1/seo-geo/run-due", SYSTEM),
    ("/api/v1/seo-geo/", _SEO),
    ("/api/v1/reports/run-due", SYSTEM),
    ("/api/v1/reports", frozenset({page("planli-raporlar")})),
    ("/api/v1/alerts", frozenset({page("uyarilar"), page("genel-bakis")})),
    ("/api/v1/board/run-due", SYSTEM),
    ("/api/v1/board", frozenset({page("panolar"), page("genel-bakis")})),
    # Kapak arşivi kendi sayfasıdır; stüdyoda kapak tarzı seçen de örneklere bakabilsin diye ikisi.
    ("/api/v1/editorial/studio/library", frozenset({page("kapak-arsivi"), page("kitap-tasarim")})),
    ("/api/v1/editorial/studio", frozenset({page("kitap-tasarim")})),
    ("/api/v1/editorial/translation", frozenset({page("ceviri"), page("ceviri-masam")})),
    # Kişiler ekranı CRM kişisinin serbest çalışan kaydını sorar; geri kalan her şey Serbest çalışanlar sayfasının.
    ("/api/v1/editorial/freelance/lookup", frozenset({page("kisiler"), page("serbest-calisanlar")})),
    ("/api/v1/editorial/freelance/", frozenset({page("serbest-calisanlar")})),
    # M12 Üretim yönetimi; baskı çıkış tarihi (M29/M16 tüketir) editoryal sayfalardan da okunur.
    ("/api/v1/editorial/production/print-exit", _EDITORIAL),
    ("/api/v1/editorial/production/", frozenset({page("uretim")})),
    # M31 Okul tanıtım ve ziyaret. Ortak ziyaret tablosunun saha uçları (M30, /api/v1/field/) da okul-tanitim
    # sayfasına açılır; o satır M30'da yazılır.
    ("/api/v1/schools/run-due", SYSTEM),
    ("/api/v1/schools/", frozenset({page("okul-tanitim")})),
    # M32 Kurumsal satış ve B2B.
    ("/api/v1/corporate/run-due", SYSTEM),
    ("/api/v1/corporate/", frozenset({page("kurumsal-satis")})),
    # M1: başvuru dosyası ve kurul oturumu iki sayfada birlikte açılır (kurul üyesi başvurunun raporunu ve dosyasını,
    # başvuru ekranı oturum listesini okur).
    ("/api/v1/editorial/applications", frozenset({page("basvurular"), page("yayin-kurulu")})),
    ("/api/v1/editorial/board-sessions", frozenset({page("yayin-kurulu"), page("basvurular")})),
    ("/api/v1/editorial/web/run-due", SYSTEM),
    ("/api/v1/editorial/authors/copurchase/run-due", SYSTEM),
    ("/api/v1/editorial/web/status", OPEN),        # menü: «Basın ve web» ortamda açık mı
    ("/api/v1/editorial/search", OPEN),            # ⌘K paletindeki kitap/kişi araması
    ("/api/v1/editorial/contracts", frozenset({page("telif-sozlesme")})),
    ("/api/v1/editorial/", _EDITORIAL),
    # Belge incelemesi (Son Okuma → «Belge incele»): yükleme ve sonuçlar Son Okuma ya da Redaksiyon sayfasıyla
    ("/api/v1/editorial/documents", frozenset(page(x) for x in ("son-okuma", "redaksiyon"))),
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
                         r"|seo-geo/redirects/export\.csv|editorial/proofing/export\.docx|editorial/documents/[^/]+/export\.docx"
                         r"|editorial/ask/export\.pdf"
                         r"|editorial/translation/jobs/[^/]+/(export\.docx|quality\.csv)|editorial/translation/terms/export\.csv"
                         r"|editorial/freelance/payouts/[^/]+/export\.csv"
                         r"|editorial/contracts/(item|addenda|statements)/[^/]+/document\.docx)$",
     "ozellik:veri.disa-aktar"),
    (frozenset({"PUT"}), r"^/api/v1/board$", "ozellik:pano.duzenle"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/reports(/(?!run-due$)[^/]+(/run)?)?$", "ozellik:rapor.planla"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/alerts(/[^/]+)?$", "ozellik:uyari.kural"),
    (frozenset({"GET"}), r"^/api/v1/financial-audit/(lines|documents|runs/[^/]+/exceptions/.+)$", "ozellik:denetim.detay"),
    (frozenset({"POST"}), r"^/api/v1/financial-audit/runs/[^/]+/reviews/.+$", "ozellik:denetim.inceleme"),
    (frozenset({"POST"}), r"^/api/v1/financial-audit/refresh$", "ozellik:denetim.yenile"),
    (frozenset({"POST"}), r"^/api/v1/management/reports/[^/]+/refresh$", "ozellik:yonetim-raporu.yenile"),
    # Bütçe taslağı: öneri, düzeltme, onaya gönderme, revizyon, gerçekleşmeyi yenileme. Onay/geri gönderme açıkça
    # verilen `butce.onay` ile ucun içinde denetlenir; bu kural onlara uygulanmaz.
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/budget/(plans(?!/[^/]+/(approve|reject)$)(/.*)?|refresh)$",
     "ozellik:butce.duzenle"),
    (frozenset({"GET"}), r"^/api/v1/budget/plans/[^/]+/export\.csv$", "ozellik:veri.disa-aktar"),
    # İlk dağılım: öneri, düzeltme, onaya gönderme, revizyon, takip ve liste yenileme. Onay/geri gönderme açıkça
    # verilen `dagilim.onay` ile ucun içinde; sevk listesi (Excel) dışa aktarma yetkisiyle.
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/distribution/(plans(?!/[^/]+/(approve|reject)$)(/.*)?|books/refresh)$",
     "ozellik:dagilim.plan"),
    (frozenset({"GET"}), r"^/api/v1/distribution/plans/[^/]+/export\.xlsx$", "ozellik:veri.disa-aktar"),
    # İhale: kayıt, dosya, kalem, eşleştirme, kontrol listesi, karar önerisi, sonuç. Karar onayı/geri gönderme açıkça
    # verilen `ihale.karar` ile, ilan kaynağı `ihale.kaynak-yonet` ile ucun içinde; şirket belge arşivi `ihale.belge`.
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/tenders(/(?!run-due$|watch/|documents(/|$)|[^/]+/decision/(approve|reject)$).*)?$", "ozellik:ihale.duzenle"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/tenders/documents(/[^/]+)?$", "ozellik:ihale.belge"),
    (frozenset({"GET"}), r"^/api/v1/tenders/[^/]+/pricing\.xlsx$", "ozellik:veri.disa-aktar"),
    # Kategori ağacı: öneri üretme ve kaynak yenileme; ağaç taslağı, eşleme, kural ve etiket sözlüğü. Ağaç onayı ve
    # profil kararı açıkça verilen `kategori.agac-onay` / `kategori.profil-onay` (+ `kategori.herkesinki`) ile ucun içinde.
    (frozenset({"POST"}), r"^/api/v1/categories/(books/[^/]+/propose|refresh)$", "ozellik:kategori.oneri-uret"),
    (frozenset({"PUT", "POST", "DELETE"}),
     r"^/api/v1/categories/(tree|tree/(open|draft|suggest|submit|withdraw)|mappings|rules/[^/]+|tags/decision)$",
     "ozellik:kategori.agac-duzenle"),
    (frozenset({"GET"}), r"^/api/v1/categories/crm-diff/export\.xlsx$", "ozellik:veri.disa-aktar"),
    # İlk baskı kararı kaydı ve geri çekme; onay (satış/üretim) açıkça verilen `ilk-baski.onay` ile ucun içinde.
    (frozenset({"POST"}), r"^/api/v1/management/first-print/decisions(/[^/]+/withdraw)?$", "ozellik:ilk-baski.karar"),
    # Pazarlama planı: taslak, düzenleme, Zeki AI önerisi, materyal taslağı, onaya gönderme, revizyon. Plan onayı, üst
    # bütçe onayı ve materyalin editoryal onayı açıkça verilen yetkilerle ucun içinde denetlenir; bu kural onlara uymaz.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/marketing/(plans(/[^/]+(/(lines|tasks|suggest|materials|submit|withdraw|revise))?)?|materials/[^/]+)$",
     "ozellik:pazarlama.plan-yaz"),
    (frozenset({"GET"}), r"^/api/v1/marketing/plans/[^/]+/(export\.(pdf|csv)|package\.zip|crm-todo\.csv)$",
     "ozellik:veri.disa-aktar"),
    # M53 Set ve hediye: set/öneri/teklif yazma, veri yenileme. Set onayı (`set.onay`) ve teklif onayı (`set.teklif-onay`)
    # açıkça verilir, ucun içinde denetlenir; fiyat hesabı (price) kaydetmez, sayfa yetkisiyle gelir.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/marketing/sets(/refresh|/suggestions/[^/]+/(adopt|dismiss)|/(?!run-due$)[^/]+(/(items|submit|withdraw|link|text))?)?$",
     "ozellik:set.yaz"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/marketing/gift-offers(/[^/]+(/(letter|submit|withdraw))?)?$",
     "ozellik:set.yaz"),
    (frozenset({"GET"}), r"^/api/v1/marketing/sets/[^/]+/card-todo\.(csv|pdf)$", "ozellik:veri.disa-aktar"),
    (frozenset({"POST"}), r"^/api/v1/editorial/books/[^/]+/review/decide$", "ozellik:kitap.inceleme-karar"),
    (frozenset({"POST"}), r"^/api/v1/editorial/proofing/decision$", "ozellik:son-okuma.karar"),
    (frozenset({"PUT"}), r"^/api/v1/editorial/documents$", "ozellik:son-okuma.belge"),
    # Çeviri: iş açma, atama, kaynak, ZEKİ taslağı, redaksiyona aktarma; onaylı terim bankası. Çevirmenin kendi
    # işi (segment kaydı, XLIFF içe aktarımı, terim önerisi) sayfa yetkisi + işteki rolüyle olur.
    (frozenset({"POST"}), r"^/api/v1/editorial/translation/jobs$", "ozellik:ceviri.yonet"),
    (frozenset({"PATCH", "DELETE"}), r"^/api/v1/editorial/translation/jobs/[^/]+$", "ozellik:ceviri.yonet"),
    (frozenset({"PUT"}), r"^/api/v1/editorial/translation/jobs/[^/]+/source$", "ozellik:ceviri.yonet"),
    (frozenset({"POST"}), r"^/api/v1/editorial/translation/jobs/[^/]+/(draft|to-redaction)$", "ozellik:ceviri.yonet"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/editorial/translation/terms(/(?!propose$)[^/]+)?$", "ozellik:ceviri.terim"),
    (frozenset({"PUT"}), r"^/api/v1/editorial/translation/terms/import$", "ozellik:ceviri.terim"),
    # Serbest çalışan kaydı, paket, atama, teslim kararı, hakediş taslağı. Yazışma ve öneri (suggest) sayfayla gelir;
    # hakediş onayı/ödemesi açıkça verilen `serbest.hakedis-onay` ile ucun içinde denetlenir.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/editorial/freelance/((people|portfolio|packages|tasks|assign|deliveries)(/.*)?|payouts(/[^/]+/(submit|delete))?)$",
     "ozellik:serbest.yonet"),
    # Üretim kartına tarih/not/kalite/teklif yazma; matbaa onayı açıkça verilen `uretim.matbaa-onay` ile ucun içinde.
    (frozenset({"POST", "DELETE"}), r"^/api/v1/editorial/production/(cards/[^/]+/(entries|quotes)|entries/[^/]+|quotes/[^/]+)$",
     "ozellik:uretim.yaz"),
    # Saha: ziyaret notu, takip taslağı ve ödeme planı taslağı; müdür önceliği. Plan onayı/reddi, bütün temsilcileri görme
    # ve temsilci karşılaştırması açıkça verilen anahtarlarla ucun içinde denetlenir.
    (frozenset({"POST", "PATCH"}), r"^/api/v1/field/(visits(/[^/]+(/followup-draft)?)?|payment-plans(/[^/]+(/submit)?)?)$",
     "ozellik:saha.not"),
    (frozenset({"POST", "DELETE"}), r"^/api/v1/field/overrides(/[^/]+)?$", "ozellik:saha.oncelik-duzenle"),
    (frozenset({"GET"}), r"^/api/v1/field/report/weekly\.xlsx$", "ozellik:veri.disa-aktar"),
    # M32 Kurumsal satış: fırsat, paket, teklif, kurum segmenti, hatırlatmadan fırsat, veri yenileme. Teklif onayı/geri
    # gönderme açıkça verilen `kurumsal.teklif-onay` ile ucun içinde denetlenir; bu kural onlara uygulanmaz.
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/corporate/(opportunities(/[^/]+(/quotes)?)?|quotes/[^/]+(/(submit|withdraw|sent|result|letter))?"
     r"|packages/suggest|accounts/[^/]+|reminders/[^/]+(/opportunity)?|refresh)$", "ozellik:kurumsal.teklif"),
    (frozenset({"POST"}), r"^/api/v1/corporate/themes/[^/]+/approve$", "ozellik:kurumsal.tema-onay"),
    (frozenset({"GET"}), r"^/api/v1/corporate/b2b/.+$", "ozellik:kurumsal.b2b"),
    (frozenset({"GET"}), r"^/api/v1/corporate/(quotes/[^/]+/document\.(pdf|xlsx)|b2b/(dealers|highlights)\.csv)$",
     "ozellik:veri.disa-aktar"),
    # Fiyatlama (M9): analiz, pazar fiyatı, varsayılan ve toplu zam teklifi yazımı. Hesap (`calc`) ve okuma sayfayla
    # gelir; onay imzaları açıkça verilen `fiyatlama.onay-<rol>` ile ucun içinde denetlenir.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/pricing/(analyses(/[^/]+(/(submit|withdraw|archive))?)?|market(/[^/]+)?|defaults|proposals|refresh)$",
     "ozellik:fiyatlama.yaz"),
    # M1 başvuru: kayıt, dosya, editör raporu ve kararı, kurul raporu, yazışma. Kurul üyesinin oyu sayfa yetkisi +
    # oturum üyeliğiyle olur; oturum yönetimi açıkça verilen `yayin-kurulu.yonet` ile ucun içinde denetlenir.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}), r"^/api/v1/editorial/applications(/.*)?$", "ozellik:basvuru.yaz"),
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/editorial/authors/(cards(/[^/]+)?|by-crm/[^/]+/card|meetings(/[^/]+)?)$", "ozellik:yazar-iliski.yaz"),
    # M31: ziyaret raporu, plan önerisi/düzeltmesi, katalog, bayi önerme; bağlam (ilçe endeksi, takvim) yükleme.
    # Plan onayı (`okul.plan`), bayi eşleştirme onayı (açıkça verilen `okul.bayi-onay`) ve bütün ekibi görme
    # (`okul.herkesinki`) ucun içinde denetlenir.
    (frozenset({"POST", "PATCH"}),
     r"^/api/v1/schools/((?!run-due$|context/)[^/]+/(visits(/suggest)?|plan|catalog|dealers)|plan/generate|plan/[^/]+"
     r"|visits/[^/]+/next-done)$", "ozellik:okul.ziyaret"),
    (frozenset({"POST"}), r"^/api/v1/schools/context/upload$", "ozellik:okul.baglam-yukle"),
    (frozenset({"GET"}), r"^/api/v1/schools/catalogs/[^/]+\.pdf$", "ozellik:veri.disa-aktar"),
    (frozenset({"POST"}), _S + r"(/docx)?$", "ozellik:tasarim.uret"),
    (frozenset({"POST"}), _S + r"/[^/]+/(restart|resume|art/[^/]+/regenerate|plan/figures|plan/assets/[^/]+/(cutout|upscale)"
                               r"|coloring|coloring/retry|coloring/art/[^/]+/redraw|narration/run"
                               r"|collage/photos|marketing/[^/]+/generate)$", "ozellik:tasarim.uret"),
    # M19: talep açma; üretim (görsel dizimi, Zeki AI metni, başlık önerisi), kapak yükleme ve varlık düzeltme.
    # Tasarım/mesaj onayı ve marka kiti açıkça verilen yetkilerle ucun içinde denetlenir.
    (frozenset({"POST"}), r"^/api/v1/marketing/creative/(requests|from-material/[^/]+)$", "ozellik:icerik.talep"),
    (frozenset({"POST"}), r"^/api/v1/marketing/creative/requests/[^/]+/(produce|copy|headlines)$", "ozellik:icerik.uret"),
    (frozenset({"PUT"}), r"^/api/v1/marketing/creative/(requests/[^/]+/cover|assets/[^/]+)$", "ozellik:icerik.uret"),
    (frozenset({"POST"}), r"^/api/v1/seo-geo/(products/[^/]+/propose|pages/[^/]+/[^/]+/propose|proposals/batch)$",
     "ozellik:seo.oneri-uret"),
    (frozenset({"POST", "DELETE"}), r"^/api/v1/seo-geo/(sync|crm/sync|schema/crawl|search/refresh|questions(/[^/]+)?)$",
     "ozellik:seo.calistir"),
    # Uzman özellikleri (2.–3. tur): taslak üretme «öneri üret»; okuma/tarama/yenileme, iş listesi durumu ve soru önerisi
    # kararı «çalıştır»; dosya indirme «dışa aktar». Onay/ret/gönderim uçları onay yetkisini kendi içinde ister.
    (frozenset({"POST"}), r"^/api/v1/seo-geo/(guides|bios/[^/]+/draft|faq/[^/]+/draft)$", "ozellik:seo.oneri-uret"),
    (frozenset({"POST"}), r"^/api/v1/seo-geo/((authors-trust|backlinks|bing|bios|entity|opportunities|qsuggest|reviews|seasons"
                          r"|similar|sunset|youtube|tech/sitemaps)/refresh|(competitors|crawlbot|impact|watch)/run|speed/run"
                          r"|tech/crawl|monthly/build|worklist/[^/]+/status|qsuggest/[^/]+/(accept|reject))$",
     "ozellik:seo.calistir"),
    (frozenset({"GET"}), r"^/api/v1/seo-geo/((worklist|similar|keymap|sunset)/export\.csv|video/(sitemap\.xml|theme-request\.md)"
                         r"|schema/theme-request\.md|(bios/drafts|guides)/[^/]+/export\.html|faq/export\.json|shopping/feed\.tsv"
                         r"|monthly/[^/]+\.pdf|watch/report/[^/]+\.html)$",
     "ozellik:veri.disa-aktar"),
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
    allowed = allowed_domains(acc)
    data = [{**d, "key": data_key(d["id"]), "allowed": allowed is None or d["id"] in allowed} for d in data_domains()]
    return {**acc.view(), "adGroups": groups, "crmRoles": crm, "pages": pages, "features": features, "data": data,
            "notes": notes}
