"""Yetki: kim hangi sayfayı görür.

Model (analiz: docs/analiz/yetki-mekanizmasi-2026-09-27.md): AD grubu / AD OU'su / CRM güvenlik rolü / tek kişi
→ rol → yetki anahtarları. Kişinin yetkisi bağlı olduğu rollerin **birleşimidir**; «yasak» kuralı yoktur.
Yönetici (`admin.is_admin`) her şeyi görür. «Herkes» sistem rolü giriş yapan herkese uygulanır ve kurulumda
«bütün yetkiler» açık gelir — 2026-09-27 kararı: roller prod öncesi atanır, o gün Herkes daraltılır.

Üyelikler istek yolunda okunmaz. AD grubu/OU üyeleri ve CRM rol sahipleri `semantic_access_members`
anlık görüntüsünden gelir; `timas-admin-group` zamanlayıcısı (her gün 07:00 ve 12:00) `refresh()` ile tazeler. Okunamayan
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
    """«Bütün sayfalar ve işlemler» ile gelmeyen, role tek tek verilen anahtarlar: özellikler (bugüne kadar yalnız
    yöneticinin yaptığı işler) ve sayfalar (ör. Sistem durumu, İK ekranları). Kurulumda Herkes bütün yetkilerle
    açılırken kimsenin eski yetkisi bu yolla genişlemez, açıkça verilen sayfa da «Herkes»e açılmaz."""
    cat = catalog()
    return (frozenset(f["key"] for f in cat.get("features", []) if f.get("explicit"))
            | frozenset(p["key"] for p in cat.get("pages", []) if p.get("explicit")))



def sensitive_keys() -> frozenset[str]:
    """Kişisel veri gösteren anahtarlar (katalogda `sensitive`, ör. İK aday verisi): yönetici bile bunları yalnız
    rolüyle alır; «yönetici her şeyi görür» kuralı bunlarda işlemez (hr_core.who_from)."""
    cat = catalog()
    return (frozenset(f["key"] for f in cat.get("features", []) if f.get("sensitive"))
            | frozenset(p["key"] for p in cat.get("pages", []) if p.get("sensitive")))

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
    from semantic_layer.store import schema_stamp
    schema_stamp.create_all(_md, engine)
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
    from semantic_layer.store import schema_stamp
    schema_stamp.create_all(_md, engine)
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


#: Zamanlayıcının adına koştuğu kişi (kart/rapor/uyarı sahibi). Sohbetin portal verisi (chat_portal) sayfa yetkisini
#: bu kişiden okur; istekte oturum çerezi varsa ondaki kişi geçerlidir.
ACTING_USER: ContextVar[Optional[str]] = ContextVar("access_acting_user", default=None)


@contextmanager
def acting_as(user: Optional[str]):
    """Zamanlayıcıdaki kart/rapor/uyarı sahibinin veri kapsamıyla koşar: yetkisi daralan kişinin raporu da daralır."""
    token = DATA_ALLOWED.set(allowed_for(user))
    who = ACTING_USER.set((user or "").strip().lower() or None)
    try:
        yield
    finally:
        ACTING_USER.reset(who)
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
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
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


def role_stmts(tenant: str) -> dict[str, Any]:
    """Rol, rol yetkisi, bağ ve üye görüntüsü okumaları (yetki hesabı ve sorgu bilgisi aynı ifadeleri kullanır)."""
    roles = sa.select(ROLES).where(ROLES.c.tenant_id == tenant)
    return {
        "roles": roles,
        "perms": sa.select(ROLE_PERMS.c.role_id, ROLE_PERMS.c.perm).where(
            ROLE_PERMS.c.role_id.in_(sa.select(ROLES.c.id).where(ROLES.c.tenant_id == tenant).scalar_subquery())),
        "bindings": sa.select(BINDINGS).where(BINDINGS.c.tenant_id == tenant),
        "members": sa.select(MEMBERS.c.subject_type, MEMBERS.c.subject, MEMBERS.c.members, MEMBERS.c.updated_at,
                             MEMBERS.c.error),
    }


def _load(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    # Anahtar veritabanı + tenant: aynı süreçte iki veritabanı (testler, yönetim ekranının denemesi) birbirinin
    # rollerini görmesin.
    key = (id(engine), tenant)
    if _state["key"] == key and time.monotonic() - _state["at"] < _TTL:
        return _state
    st = role_stmts(tenant)
    with engine.connect() as c:
        roles = {r["id"]: {**dict(r), "perms": set()} for r in c.execute(st["roles"]).mappings()}
        for rid, perm in c.execute(st["perms"]).all():
            if rid in roles:
                roles[rid]["perms"].add(perm)
        bindings = [dict(b) for b in c.execute(st["bindings"]).mappings()]
        members: dict[tuple[str, str], frozenset[str]] = {}
        for t, s, m, _at, _err in c.execute(st["members"]).all():
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

_SEO = frozenset(page(x) for x in ("seo-geo", "seo-arama", "seo-firsat", "seo-bing", "seo-yandex", "seo-rakip", "seo-ai", "seo-sayfalar",
                                   "seo-yonlendirme", "seo-teknik", "seo-kimlik", "seo-rehber", "seo-sema", "seo-llms",
                                   "seo-crm", "seo-urun", "seo-gecmis", "seo-baglanti",
                                   "seo-izleme", "seo-kaynak", "seo-yarisan", "seo-tarama", "seo-geri-baglanti", "seo-takvim", "seo-ic-baglanti", "seo-yorum", "seo-video", "seo-kalkan", "seo-yazar-sayfa",
                                   "seo-isler", "seo-karne", "seo-biyografi", "seo-sss", "seo-benzer", "seo-eslesme", "seo-soru", "seo-youtube", "seo-alisveris", "seo-aylik",
                                   "seo-aramadan-satisa"))
_EDITORIAL = frozenset(page(x) for x in ("editoryal", "yazar-giris", "basvurular", "yayin-kurulu", "redaksiyon", "cevirmenler",
                                         "son-okuma", "kitap-tasarim", "kapak-arsivi", "kisiler", "yazar-iliskileri", "basin-web", "telif-sozlesme",
                                         "editor-atama", "serbest-calisanlar", "uretim"))

_OKUR = frozenset(page(x) for x in ("okur-toplulugu", "okur-segmentler", "okur-programlar", "okur-yorumlar"))
_CHANNELS = frozenset(page(x) for x in ("kanallar", "kanal-matris", "kanal-d2c", "kanal-eslesme"))
_SUPPLY = frozenset(page(x) for x in ("tedarik", "tedarik-yuk", "tedarik-kagit", "tedarik-tedarikciler", "tedarik-maliyet"))
_TRENDYOL = frozenset(page(x) for x in ("trendyol", "trendyol-urunler", "trendyol-siparisler", "trendyol-sorular",
                                        "trendyol-mutabakat"))
_AMAZON = frozenset(page(x) for x in ("amazon", "amazon-konsinye", "amazon-yurtdisi", "amazon-taslaklar", "amazon-mutabakat"))

_CATEGORY_READERS = frozenset({page("kategori-agaci"), page("editor-atama"), page("yayin-kurulu"),
                               page("yazar-giris")}) | _SEO
_PAZAR = frozenset(page(x) for x in ("pazar-arastirma", "pazar-rakipler", "pazar-raporlar"))

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
    ("/api/v1/budget/targets", frozenset({page("butce"), page("ilk-dagilim"), page("saha"), page("pazarlama-yeni-kitap"),
                                          page("pazarlama-aylik"),
                                          page("pazarlama-backlist")})),
    ("/api/v1/budget/deviations", frozenset({page("butce"), page("ilk-dagilim"), page("saha"), page("pazarlama-yeni-kitap"),
                                             page("pazarlama-aylik"),
                                          page("pazarlama-backlist")})),
    ("/api/v1/budget/", frozenset({page("butce")})),
    ("/api/v1/management/first-print/", frozenset({page("ilk-baski")})),
    # M29 İlk dağılım (Satış ve saha). Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/distribution/run-due", SYSTEM),
    ("/api/v1/distribution/", frozenset({page("ilk-dagilim")})),
    # M30 Saha satış ve tahsilat. Ziyaret kaydı M30/M31 ortak (semantic_saha_ziyaret): okul tanıtım sayfası da okur/yazar.
    ("/api/v1/field/run-due", SYSTEM),
    ("/api/v1/field/visits", frozenset({page("saha"), page("okul-tanitim")})),
    ("/api/v1/field/", frozenset({page("saha")})),
    # Zeki AI sesli not: M30 saha ve M31 okul ziyaret notunun mikrofonu. Not yazma yetkisi (saha.not / okul.ziyaret) uçta.
    ("/api/v1/voice-note", frozenset({page("saha"), page("okul-tanitim")})),
    # M59 Bayi riski. Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/dealers/run-due", SYSTEM),
    ("/api/v1/dealers/", frozenset({page("bayi-risk")})),
    ("/api/v1/pricing/", frozenset({page("fiyatlama")})),
    # M45 Finansal raporlar. Bütçe sekmesi M46'yı köprü içinde okur (ayrı bütçe ucu açılmaz). Zamanlayıcı yalnız run-due.
    ("/api/v1/finance/run-due", SYSTEM),
    ("/api/v1/finance/", frozenset({page("finansal-raporlar")})),
    # M43 Depo ve stok (Lojistik). Ortak uçlar (meta, kitap listesi/kartı, öneriler, Excel) bütün stok sayfalarına; liste
    # uçları kendi sayfasına ve açılış ekranına. Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/stock/run-due", SYSTEM),
    ("/api/v1/stock/running-out", frozenset({page("stok"), page("stok-bitecekler")})),
    ("/api/v1/stock/excess", frozenset({page("stok"), page("stok-fazla")})),
    ("/api/v1/stock/diff", frozenset({page("stok"), page("stok-fark")})),
    ("/api/v1/stock/transfer-errors", frozenset({page("stok"), page("stok-aktarim")})),
    ("/api/v1/stock/pick-line", frozenset({page("stok-depo-hatti")})),
    ("/api/v1/stock/thresholds", frozenset({page("stok"), page("stok-esikler")})),
    ("/api/v1/stock/", frozenset(page(x) for x in ("stok", "stok-bitecekler", "stok-fazla", "stok-esikler", "stok-fark",
                                                    "stok-aktarim", "stok-depo-hatti"))),
    # M33 İhale takibi (Satış ve saha). Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/tenders/run-due", SYSTEM),
    ("/api/v1/tenders/", frozenset({page("ihale")})),
    # M19 Pazarlama görsel ve metin. Onaylı varlık sözleşmesini (contract/assets) okuyacak modül (M21/M22/M24) kendi
    # sayfa anahtarını o satıra ekler. M15'in genel «/api/v1/marketing/» satırından önce durur (en uzun önek kazanır;
    # sıra okunurluk içindir).
    ("/api/v1/marketing/creative/run-due", SYSTEM),
    ("/api/v1/marketing/creative/contract/", frozenset({page("pazarlama-icerik")})),
    ("/api/v1/marketing/creative/", frozenset({page("pazarlama-icerik")})),
    # M47 Risk ve uyum (Finans). DYK gelince summary/reports satırlarına kendi sayfa anahtarını ekler.
    ("/api/v1/risk/run-due", SYSTEM),
    ("/api/v1/risk/", frozenset({page("risk-uyum")})),
    # DYK Kurul (Finans). Sayfa açıkça verilir; M45/M46/M47/M59/M50/M48/M6/M39 çıktıları köprü içinde okunur (kurul üyesinin
    # kaynak sayfa yetkisi gerekmez). İşlem yetkileri (kurul.*) ucun içinde; zamanlayıcı yalnız run-due.
    ("/api/v1/kurul/run-due", SYSTEM),
    ("/api/v1/kurul/", frozenset({page("kurul")})),
    # M38 Müşteri ilişkileri (Satış ve saha). Veri sağlığı ayrı sayfa; zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/musteri/run-due", SYSTEM),
    ("/api/v1/musteri/health", frozenset({page("musteri-veri-sagligi")})),
    ("/api/v1/musteri/", frozenset({page("musteri-iliskileri")})),
    # Pazarlama çekirdeği (M15; M16–M18 kendi sayfa anahtarlarını buraya ve sözleşme satırına ekler).
    # M53 Set, hediye ve promosyon (Pazarlama → Üretim).
    ("/api/v1/marketing/sets/run-due", SYSTEM),
    ("/api/v1/marketing/sets/", frozenset({page("pazarlama-set-hediye")})),
    ("/api/v1/marketing/gift-offers/", frozenset({page("pazarlama-set-hediye")})),
    ("/api/v1/marketing/promo-items", frozenset({page("pazarlama-set-hediye")})),
    # M35 E-ticaret kampanya yönetimi (Pazarlama › E-ticaret). Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/kampanya/run-due", SYSTEM),
    ("/api/v1/kampanya/", frozenset({page("kampanya")})),
    ("/api/v1/marketing/run-due", SYSTEM),
    # M18 Aylık plan ve satış föyü. Föy uçları saha temsilcisine de açık (rolünde yalnız föy sayfası olur); meta üç
    # sayfanın ortak ekran bilgisidir.
    ("/api/v1/marketing/months/run-due", SYSTEM),
    ("/api/v1/marketing/months/", frozenset({page("pazarlama-aylik")})),
    ("/api/v1/marketing/foy", frozenset({page("pazarlama-foy"), page("pazarlama-aylik")})),
    ("/api/v1/marketing/meta", frozenset({page("pazarlama-yeni-kitap"), page("pazarlama-aylik"), page("pazarlama-foy")})),
    ("/api/v1/marketing/contract/month/", frozenset({page("pazarlama-aylik"), page("pazarlama-yeni-kitap")})),
    # M16 Lansman (Pazarlama › Planlama). Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/marketing/launches/run-due", SYSTEM),
    ("/api/v1/marketing/launches", frozenset({page("pazarlama-lansman")})),
    # M17 Backlist. Aktivasyon planı çekirdeğin plan uçlarıyla açılır/onaylanır: genel satırda backlist sayfası da var.
    ("/api/v1/marketing/backlist/run-due", SYSTEM),
    ("/api/v1/marketing/backlist", frozenset({page("pazarlama-backlist")})),
    ("/api/v1/marketing/contract/", frozenset({page("pazarlama-yeni-kitap")})),
    ("/api/v1/marketing/", frozenset({page("pazarlama-yeni-kitap"), page("pazarlama-backlist")})),
    # M20 Basın ilişkileri (Pazarlama). Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/pr/run-due", SYSTEM),
    ("/api/v1/pr/", frozenset({page("basin-iliskileri")})),
    # M21 Dijital pazarlama ve reklam. Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/ads/run-due", SYSTEM),
    ("/api/v1/ads/", frozenset({page("reklam")})),
    # M22 Sosyal medya. Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/social/run-due", SYSTEM),
    ("/api/v1/social/", frozenset({page("sosyal-medya")})),
    # M23 İşbirlikleri (Pazarlama › İletişim). Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/influencers/run-due", SYSTEM),
    ("/api/v1/influencers/", frozenset({page("isbirlikleri")})),
    # M24 Katalog ve bülten. Zamanlayıcı yalnız run-due'yu çağırır.
    ("/api/v1/catalog-newsletter/run-due", SYSTEM),
    ("/api/v1/catalog-newsletter/", frozenset({page("katalog-bulten")})),
    # M27 Fuar, etkinlik ve ödül. Kampüs ajandası oturumla açılır (yalnız kişinin kendi kayıtları döner).
    ("/api/v1/events/run-due", SYSTEM),
    ("/api/v1/events/me/agenda", OPEN),
    ("/api/v1/events/", frozenset({page("etkinlikler")})),
    # M42 Platform ve kanallar (M40/M41 kendi alt yollarını ve sayfa anahtarlarını buraya ekler). Ortak uçlar (meta,
    # durum, yenileme, dışa aktarma) dört sayfada; dışa aktarılan listenin sayfası ucun içinde ayrıca denetlenir.
    ("/api/v1/channels/run-due", SYSTEM),
    ("/api/v1/channels/meta", _CHANNELS),
    ("/api/v1/channels/status", _CHANNELS),
    ("/api/v1/channels/refresh", _CHANNELS),
    ("/api/v1/channels/export/", _CHANNELS),
    ("/api/v1/channels/matrix", frozenset({page("kanal-matris")})),
    ("/api/v1/channels/d2c", frozenset({page("kanal-d2c")})),
    ("/api/v1/channels/accounts", frozenset({page("kanal-eslesme")})),
    ("/api/v1/channels/suggestions", frozenset({page("kanallar"), page("kanal-d2c")})),
    ("/api/v1/channels/", frozenset({page("kanallar")})),
    # M40 Trendyol (yalnız okuma + panel dosyası). Ortak uçlar (meta, durum, yenileme, dışa aktarma) dört sayfada;
    # dışa aktarılan listenin sayfası ucun içinde ayrıca denetlenir.
    ("/api/v1/channels/trendyol/run-due", SYSTEM),
    ("/api/v1/channels/trendyol/meta", _TRENDYOL),
    ("/api/v1/channels/trendyol/status", _TRENDYOL),
    ("/api/v1/channels/trendyol/refresh", _TRENDYOL),
    ("/api/v1/channels/trendyol/export/", _TRENDYOL),
    ("/api/v1/channels/trendyol/products", frozenset({page("trendyol-urunler")})),
    ("/api/v1/channels/trendyol/stock-diff", frozenset({page("trendyol-urunler")})),
    ("/api/v1/channels/trendyol/price-diff", frozenset({page("trendyol-urunler")})),
    ("/api/v1/channels/trendyol/orders", frozenset({page("trendyol-siparisler")})),
    ("/api/v1/channels/trendyol/claims", frozenset({page("trendyol-siparisler")})),
    ("/api/v1/channels/trendyol/questions", frozenset({page("trendyol-sorular")})),
    ("/api/v1/channels/trendyol/reviews", frozenset({page("trendyol-sorular")})),
    # Aşama 1: satış/iade mutabakatı ve hakediş (panel dosyası ↔ Logo). Aşama 0 model tespiti Trendyol sayfasında.
    ("/api/v1/channels/trendyol/mutabakat", frozenset({page("trendyol-mutabakat")})),
    ("/api/v1/channels/trendyol/", frozenset({page("trendyol")})),
    # M41 Amazon ve yurtdışı (Logo + CRM, yalnız okuma).
    ("/api/v1/channels/amazon/run-due", SYSTEM),
    ("/api/v1/channels/amazon/meta", _AMAZON),
    ("/api/v1/channels/amazon/status", _AMAZON),
    ("/api/v1/channels/amazon/refresh", _AMAZON),
    ("/api/v1/channels/amazon/export/", _AMAZON),
    ("/api/v1/channels/amazon/consignment", frozenset({page("amazon-konsinye")})),
    ("/api/v1/channels/amazon/international", frozenset({page("amazon-yurtdisi")})),
    ("/api/v1/channels/amazon/rights", frozenset({page("amazon-yurtdisi")})),
    ("/api/v1/channels/amazon/params", frozenset({page("amazon-yurtdisi")})),
    ("/api/v1/channels/amazon/market-cards", frozenset({page("amazon-yurtdisi")})),
    ("/api/v1/channels/amazon/drafts", frozenset({page("amazon-taslaklar")})),
    ("/api/v1/channels/amazon/mutabakat", frozenset({page("amazon-mutabakat")})),
    ("/api/v1/channels/amazon/", frozenset({page("amazon")})),
    # H1 Kategori ağacı. Sözleşme uçlarını (kitap profili, yürürlükteki ağaç ve düğümün kitapları) M1 başvuru
    # değerlendirmesi, M2 editör atama ve SEO sayfaları da okur; yazma uçları kategori-agaci sayfasında kalır.
    ("/api/v1/categories/run-due", SYSTEM),
    ("/api/v1/categories/profile/", _CATEGORY_READERS),
    ("/api/v1/categories/nodes", _CATEGORY_READERS),
    ("/api/v1/categories/", frozenset({page("kategori-agaci")})),
    # M49 Veri güvenliği (Altyapı ve destek). Sayfa açıkça verilir; istemci tarafı dışa aktarma bildirimi herkese açık.
    ("/api/v1/data-security/run-due", SYSTEM),
    ("/api/v1/data-security/export-notice", OPEN),
    # İstemcide üretilen CSV'nin Excel'e çevrilmesi (csv_excel.py): kişi ekranda gördüğü tabloyu gönderir; bildirim istemciden.
    ("/api/v1/export/xlsx", OPEN),
    ("/api/v1/data-security/", frozenset({page("veri-guvenligi")})),
    # M51 Müşteri hizmetleri. Zamanlayıcı run-due uçlarını, destek masası paneli (çerezsiz, sunucudan sunucuya) panel/
    # uçlarını çağırır; panel ucu temsilcinin portal yetkisini kendi içinde uygular.
    ("/api/v1/support/classify/run-due", SYSTEM),
    ("/api/v1/support/run-due", SYSTEM),
    ("/api/v1/support/panel/", SYSTEM),
    ("/api/v1/support/", frozenset({page("musteri-destek")})),
    # H2 Okuyucu veri tabanı. Sözleşme uçlarını (onaylı segment listesi ve sayıları) pazarlama sayfaları da okur
    # (M24/M37/M35 gelince kendi sayfa anahtarını buraya ekler).
    ("/api/v1/readers/run-due", SYSTEM),
    ("/api/v1/readers/contract/", frozenset({page("okurlar"), page("pazarlama-yeni-kitap")})),
    ("/api/v1/readers/", frozenset({page("okurlar")})),
    # M37 Okur topluluğu. Sözleşme (onaylı segment) M24/M35 gelince kendi sayfa anahtarını contract satırına ekler.
    # Okur sesi (öneri 15): etiket ve özet okur yorumları, Trendyol soru/sipariş ve üretim sayfalarına; kaynak süzgeci ve
    # «görüldü» yetkisi ucun içinde. Zamanlayıcı yalnız run-due.
    ("/api/v1/okur-sesi/run-due", SYSTEM),
    ("/api/v1/okur-sesi/", frozenset(page(x) for x in ("okur-yorumlar", "trendyol-sorular", "trendyol-siparisler", "uretim"))),
    # Serbest not sinyali (öneri 16): üç cari ekranı; ekranın kendi kapsamı ucun içinde.
    ("/api/v1/not-sinyali/run-due", SYSTEM),
    ("/api/v1/not-sinyali/", frozenset(page(x) for x in ("saha", "bayi-risk", "musteri-iliskileri"))),
    # Kampüs «Bugün» özeti (öneri 19): oturum yeter, her kaynak kişinin yetkisiyle köprüde süzülür.
    ("/api/v1/bugun", OPEN),
    ("/api/v1/okur/run-due", SYSTEM),
    ("/api/v1/okur/segments", frozenset({page("okur-segmentler")})),
    ("/api/v1/okur/categories", frozenset({page("okur-segmentler")})),
    ("/api/v1/okur/contract/", frozenset({page("okur-segmentler")})),
    ("/api/v1/okur/programs", frozenset({page("okur-programlar"), page("okur-toplulugu")})),
    ("/api/v1/okur/books", frozenset({page("okur-programlar")})),
    ("/api/v1/okur/events-summary", frozenset({page("okur-programlar"), page("okur-toplulugu")})),
    ("/api/v1/okur/reviews", frozenset({page("okur-yorumlar")})),
    ("/api/v1/okur/", _OKUR),
    # İnsan kaynakları (İK-0 + M55; M56–M58 kendi sayfa anahtarını _HR'a ekler). Sayfalar açıkça verilir; işlem ve
    # kişisel veri anahtarları (hepsi explicit) ucun içinde denetlenir. E-posta modülünün başvuru aktarımı SYSTEM.
    ("/api/v1/hr/me", OPEN),
    ("/api/v1/hr/purge/run-due", SYSTEM),
    ("/api/v1/hr/recruit/intake", SYSTEM),
    ("/api/v1/hr/recruit/reminders/run-due", SYSTEM),
    ("/api/v1/hr/recruit/", frozenset({page("ik-ise-alim"), page("ik-pozisyonlar"), page("ik-belgeler")})),
    # M56 performans: Performansım (bütün çalışanlara bağlanır), Ekibim, Hedefler, Değerlendirme; kişi kapsamı ucun içinde.
    ("/api/v1/hr/performance/reminders/run-due", SYSTEM),
    ("/api/v1/hr/performance/", frozenset(page(x) for x in ("ik-performansim", "ik-ekibim", "ik-hedefler", "ik-degerlendirme"))),
    # M58 bağlılık. Anket formu oturumsuz da çalışır (çerezsiz istek kapıdan geçer, uç jetonu/kodu doğrular); oturumla gelirse OPEN.
    ("/api/v1/hr/survey-public/", OPEN),
    ("/api/v1/hr/engagement/run-due", SYSTEM),
    ("/api/v1/hr/engagement/", frozenset(page(x) for x in ("ik-anketlerim", "ik-oneriler", "ik-baglilik", "ik-birimim",
                                                          "ik-anket-yonetimi", "ik-aksiyonlar"))),
    # M36 Dijital yayın ve e-kitap. Satış raporu ve gelir finans verisidir: ayrı sayfa (dijital-satis); göstergeler ve
    # platform listesi iki sayfada da açık.
    ("/api/v1/dijital/run-due", SYSTEM),
    ("/api/v1/dijital/imports", frozenset({page("dijital-satis")})),
    ("/api/v1/dijital/sales", frozenset({page("dijital-satis")})),
    ("/api/v1/dijital/meta", frozenset({page("dijital-yayin"), page("dijital-satis")})),
    ("/api/v1/dijital/overview", frozenset({page("dijital-yayin"), page("dijital-satis")})),
    ("/api/v1/dijital/platforms", frozenset({page("dijital-yayin"), page("dijital-satis")})),
    ("/api/v1/dijital/", frozenset({page("dijital-yayin")})),
    # M39 Pazar ve rakip. Meta, tazelik ve kategori listesi her üç sayfada; emsal M1/M10'da, matris M9'da da okunur.
    ("/api/v1/pazar/run-due", SYSTEM),
    ("/api/v1/pazar/dagitim/run-due", SYSTEM),
    ("/api/v1/pazar/dagitim/", _PAZAR),
    ("/api/v1/pazar/meta", _PAZAR),
    ("/api/v1/pazar/freshness", _PAZAR),
    ("/api/v1/pazar/status", _PAZAR),
    ("/api/v1/pazar/refresh", _PAZAR),
    ("/api/v1/pazar/categories", _PAZAR),
    ("/api/v1/pazar/competitors", frozenset({page("pazar-rakipler")})),
    ("/api/v1/pazar/publishers", frozenset({page("pazar-rakipler")})),
    ("/api/v1/pazar/matrix", frozenset({page("pazar-rakipler"), page("fiyatlama")})),
    ("/api/v1/pazar/category-map", frozenset({page("pazar-rakipler")})),
    ("/api/v1/pazar/watchlist", frozenset({page("pazar-rakipler")})),
    ("/api/v1/pazar/comparables", frozenset({page("pazar-rakipler"), page("yayin-kurulu"), page("basvurular"), page("ilk-baski")})),
    ("/api/v1/pazar/own-books", frozenset({page("pazar-rakipler"), page("yayin-kurulu"), page("basvurular"), page("ilk-baski")})),
    ("/api/v1/pazar/reports", frozenset({page("pazar-raporlar")})),
    ("/api/v1/pazar/figures/", frozenset({page("pazar-raporlar")})),
    ("/api/v1/pazar/", frozenset({page("pazar-arastirma")})),
    # M57 Eğitim: Eğitimlerim, ekibim, anket ve rehber okuma oturumla (uç yalnız kişinin kendi kaydını döner); ekran
    # ziyaret sayacı yalnız kendi hesabına yazar.
    # İK personel portalı: çalışan uçları portal sayfalarından birini ister (Herkes'e açık sayfalar; uç kişinin kendi
    # kaydını ya da rehber alanlarını döner); İK yönetimi uçları açıkça verilen sayfayı.
    ("/api/v1/hr/portal/admin/", frozenset({page("ik-yonetim")})),
    # M60 izin + İK e-posta kuyruğu. Çalışan/yönetici uçları kişinin kendi / ekibinin verisini döner.
    ("/api/v1/hr/mail/run-due", SYSTEM),
    ("/api/v1/hr/leave/run-due", SYSTEM),
    ("/api/v1/hr/leave/admin/", frozenset({page("ik-yonetim")})),
    ("/api/v1/hr/leave/", frozenset(page(x) for x in ("ik-izin", "ik-izin-ekip", "ik-anasayfa", "ik-rehber", "ik-yonetim"))),
    ("/api/v1/hr/portal/", frozenset(page(x) for x in ("ik-anasayfa", "ik-profilim", "ik-rehber", "ik-duyurular", "ik-evrak",
                                                      "ik-sss", "ik-yonetim"))),
    ("/api/v1/hr/visit", OPEN),
    ("/api/v1/hr/learning/me/", OPEN),
    ("/api/v1/hr/learning/reminders/run-due", SYSTEM),
    ("/api/v1/hr/learning/", frozenset({page("ik-egitim")})),
    ("/api/v1/hr/", frozenset({page("ik-ise-alim"), page("ik-pozisyonlar"), page("ik-belgeler"), page("ik-kayitlar"),
                               page("ik-egitim")})),
    ("/api/v1/seo-geo/run-due", SYSTEM),
    ("/api/v1/seo-geo/", _SEO),
    # M34 E-ticaret: ortak uçlar (meta, kitap çekmecesi, öneri) dört ekranda; liste uçları kendi ekranı + platform durumu.
    ("/api/v1/eticaret/run-due", SYSTEM),
    ("/api/v1/eticaret/diffs", frozenset({page("eticaret"), page("eticaret-farklar")})),
    ("/api/v1/eticaret/funnel", frozenset({page("eticaret"), page("eticaret-huni")})),
    ("/api/v1/eticaret/marketplaces", frozenset({page("eticaret"), page("eticaret-pazar-yerleri")})),
    ("/api/v1/eticaret/", frozenset(page(x) for x in ("eticaret", "eticaret-farklar", "eticaret-huni", "eticaret-pazar-yerleri"))),
    # H3 E-ticaret müşteri yönetimi. Sözleşme ucunu (segment sayıları) M35 kampanya, M42 D2C ve M18 aylık plan da okur.
    ("/api/v1/commerce/run-due", SYSTEM),
    ("/api/v1/commerce/segments/summary", frozenset(page(x) for x in ("eticaret-musteri", "kampanya", "kanal-d2c", "pazarlama-aylik"))),
    # Huni tek ekranda (E-ticaret › Huni, «Sipariş hunisi» sekmesi): H3 sipariş hunisi o sayfayla da okunur.
    ("/api/v1/commerce/products/funnel", frozenset({page("eticaret-musteri"), page("eticaret-huni")})),
    ("/api/v1/commerce/", frozenset({page("eticaret-musteri")})),
    ("/api/v1/reports/run-due", SYSTEM),
    ("/api/v1/reports", frozenset({page("planli-raporlar")})),
    ("/api/v1/alerts", frozenset({page("uyarilar"), page("genel-bakis")})),
    # Fark ayrıştırma («Neden?»): sohbet cevabı, pano kartı ve uyarı ekranı aynı ucu kullanır.
    ("/api/v1/fark/", frozenset({page("genel-bakis"), page("panolar"), page("uyarilar")})),
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
    # Kampüs «Matbaadan yeni çıkanlar»: herkese açık ana sayfa; yalnız kitap adı, baskı no, gün (adet/maliyet yok).
    ("/api/v1/editorial/production/new-prints", OPEN),
    ("/api/v1/editorial/production/", frozenset({page("uretim")})),
    # M52 Tedarik ve baskı (Lojistik). Gelecek depo girişlerini (incoming) M43 depo ve stok da okur; sayfa anahtarını
    # o satıra ekler. Borç/maliyet/eşleşme açıkça verilen özelliklerle ucun içinde denetlenir.
    ("/api/v1/supply/run-due", SYSTEM),
    ("/api/v1/supply/incoming", _SUPPLY),
    ("/api/v1/supply/", _SUPPLY),
    # M31 Okul tanıtım ve ziyaret. Ortak ziyaret tablosunun saha uçları (M30, /api/v1/field/) da okul-tanitim
    # sayfasına açılır; o satır M30'da yazılır.
    ("/api/v1/schools/run-due", SYSTEM),
    ("/api/v1/schools/", frozenset({page("okul-tanitim")})),
    # M48 Sistem durumu. Sayfa açıkça verilir (Herkes'e girmez); işlem yetkileri (dene, olay, ayar) de açıkça verilir ve
    # ucun içinde denetlenir. Zamanlayıcı, bekçi ve kurulum betiği çerezsiz jetonla gelir; üst bant herkese açık.
    ("/api/v1/it-ops/run-due", SYSTEM),
    ("/api/v1/it-ops/watchdog", SYSTEM),
    ("/api/v1/it-ops/report-release", SYSTEM),
    ("/api/v1/it-ops/banner", OPEN),
    ("/api/v1/it-ops/", frozenset({page("sistem-durumu")})),
    # M50 Zeki AI kalitesi. Sayfa açıkça verilir (Herkes'e girmez). Kapı betiklerinin raporu ve zamanlayıcı çerezsiz
    # jetonla gelir; cevap altındaki geri bildirim düğmesi (ve kişinin kendi hükmü) sayfa istemez, özellik ister.
    ("/api/v1/books/similar/run-due", SYSTEM),
    ("/api/v1/books/similar/index", SYSTEM),
    ("/api/v1/books/similar/status", OPEN),
    ("/api/v1/model-quality/report", SYSTEM),
    ("/api/v1/model-quality/run-due", SYSTEM),
    ("/api/v1/model-quality/feedback", OPEN),
    ("/api/v1/model-quality/", frozenset({page("zeki-kalite")})),
    # M44 Lojistik ve kargo. Günlük hat, gönderi kartı ve taslak `kargo`; firma karnesi ve karar `kargo-firmalar`;
    # mutabakat `kargo-mutabakat`; kargo maliyeti ve onun Excel'i `kargo-maliyet`. Meta dört sayfada, iş eşikleri ve öbür
    # Excel'ler üç sayfada da (liste türünün sayfası ucun içinde denetlenir).
    ("/api/v1/shipping/run-due", SYSTEM),
    ("/api/v1/shipping/carriers", frozenset({page("kargo-firmalar")})),
    ("/api/v1/shipping/decisions", frozenset({page("kargo-firmalar")})),
    ("/api/v1/shipping/reconcile", frozenset({page("kargo-mutabakat")})),
    ("/api/v1/shipping/cost", frozenset({page("kargo-maliyet")})),
    ("/api/v1/shipping/export/maliyet", frozenset({page("kargo-maliyet")})),
    ("/api/v1/shipping/meta", frozenset({page("kargo"), page("kargo-firmalar"), page("kargo-mutabakat"), page("kargo-maliyet")})),
    ("/api/v1/shipping/settings", frozenset({page("kargo"), page("kargo-firmalar"), page("kargo-mutabakat")})),
    ("/api/v1/shipping/export/", frozenset({page("kargo"), page("kargo-firmalar"), page("kargo-mutabakat")})),
    ("/api/v1/shipping/", frozenset({page("kargo")})),
    # M32 Kurumsal satış ve B2B.
    ("/api/v1/corporate/run-due", SYSTEM),
    ("/api/v1/corporate/", frozenset({page("kurumsal-satis")})),
    # M28 Kurumsal ilişkiler (kanaat önderleri, kurumlar, kamu projeleri).
    ("/api/v1/public-affairs/run-due", SYSTEM),
    ("/api/v1/public-affairs/", frozenset({page("kurumsal-iliskiler")})),
    # M1: başvuru dosyası ve kurul oturumu iki sayfada birlikte açılır (kurul üyesi başvurunun raporunu ve dosyasını,
    # başvuru ekranı oturum listesini okur).
    ("/api/v1/editorial/applications/forms/run-due", SYSTEM),
    ("/api/v1/editorial/applications", frozenset({page("basvurular"), page("yayin-kurulu")})),
    ("/api/v1/editorial/board-sessions", frozenset({page("yayin-kurulu"), page("basvurular")})),
    # H4 Kurumsal e-posta. E-postayla gelen dosya başvurularını yazar giriş süreci ekranı da okur (sözleşme ucu).
    # M1 başvuru sayfası (`sayfa:basvurular`) main'e girince o anahtar da applications satırına eklenir.
    ("/api/v1/mailbox/run-due", SYSTEM),
    ("/api/v1/mailbox/sla-due", SYSTEM),
    ("/api/v1/mailbox/applications", frozenset({page("kurumsal-eposta"), page("yazar-giris")})),
    ("/api/v1/mailbox/", frozenset({page("kurumsal-eposta")})),
    ("/api/v1/editorial/web/run-due", SYSTEM),
    ("/api/v1/editorial/authors/reminders/run-due", SYSTEM),
    ("/api/v1/editorial/authors/copurchase/run-due", SYSTEM),
    ("/api/v1/editorial/web/status", OPEN),        # menü: «Basın ve web» ortamda açık mı
    ("/api/v1/editorial/search", OPEN),            # ⌘K paletindeki kitap/kişi araması
    ("/api/v1/editorial/contracts", frozenset({page("telif-sozlesme")})),
    # Sözleşme karşılaştırma (M6 alt ekranı): emsal, serbest metin, belge madde madde.
    ("/api/v1/editorial/contracts/compare", frozenset({page("sozlesme-karsilastirma")})),
    # M54 Telif dönemi ve haklar. Sözleşme sayfası (M6) bir sözleşmenin dönem koşularını okur.
    ("/api/v1/royalty/run-due", SYSTEM),
    ("/api/v1/royalty/contracts/", frozenset({page("telif-donem"), page("telif-sozlesme")})),
    ("/api/v1/royalty/", frozenset({page("telif-donem")})),
    ("/api/v1/rights/", frozenset({page("haklar")})),
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
    # M50: cevabın altındaki Doğru / Kısmen / Yanlış düğmesi (eski uç da aynı yetkiyle).
    (frozenset({"POST"}), r"^/api/v1/(feedback|model-quality/feedback)$", "ozellik:zeki.geri-bildirim"),
    (frozenset({"GET"}), r"^/api/v1/(board/export\.xlsx|reports/[^/]+/file|financial-audit/runs/[^/]+/export"
                         r"|seo-geo/redirects/export\.csv|editorial/proofing/export\.docx|editorial/documents/[^/]+/export\.docx"
                         r"|editorial/ask/export\.pdf"
                         r"|editorial/translation/jobs/[^/]+/(export\.docx|quality\.csv)|editorial/translation/terms/export\.csv"
                         r"|editorial/freelance/payouts/[^/]+/export\.csv"
                         r"|editorial/contracts/(item|addenda|statements)/[^/]+/document\.docx"
                         r"|editorial/contracts/compare/scan\.csv"
                         r"|editorial/contracts/compare/(contract/[^/]+/report|documents/diff)\.docx)$",
     "ozellik:veri.disa-aktar"),
    (frozenset({"PUT"}), r"^/api/v1/board$", "ozellik:pano.duzenle"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/reports(/(?!run-due$)[^/]+(/run)?)?$", "ozellik:rapor.planla"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/alerts(/[^/]+)?$", "ozellik:uyari.kural"),
    (frozenset({"GET"}), r"^/api/v1/financial-audit/(lines|documents|runs/[^/]+/(exceptions|clusters)/.+)$", "ozellik:denetim.detay"),
    # İstisna kümeleme istisna satırlarını okur: ayrıntı yetkisi.
    (frozenset({"POST"}), r"^/api/v1/financial-audit/runs/[^/]+/clusters/.+$", "ozellik:denetim.detay"),
    (frozenset({"POST"}), r"^/api/v1/financial-audit/runs/[^/]+/reviews/.+$", "ozellik:denetim.inceleme"),
    (frozenset({"POST"}), r"^/api/v1/financial-audit/refresh$", "ozellik:denetim.yenile"),
    (frozenset({"POST"}), r"^/api/v1/management/reports/[^/]+/refresh$", "ozellik:yonetim-raporu.yenile"),
    # Bütçe taslağı: öneri, düzeltme, onaya gönderme, revizyon, gerçekleşmeyi yenileme. Onay/geri gönderme açıkça
    # verilen `butce.onay` ile ucun içinde denetlenir; bu kural onlara uygulanmaz.
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/budget/(plans(?!/[^/]+/(approve|reject)$)(/.*)?|refresh)$",
     "ozellik:butce.duzenle"),
    (frozenset({"GET"}), r"^/api/v1/budget/plans/[^/]+/export\.csv$", "ozellik:veri.disa-aktar"),
    (frozenset({"GET"}), r"^/api/v1/pricing/compare\.csv$", "ozellik:veri.disa-aktar"),
    # M45 Finansal raporlar: nakit sekmesi ve uçları, vergi takvimi yazma, sapma notu, dışa aktarma. Hesap eşlemesi kararı
    # (`finans.esleme`) ve ay kapanışı (`finans.kapanis`) açıkça verilir, ucun içinde denetlenir.
    (frozenset({"GET", "POST"}), r"^/api/v1/finance/cash(/.*)?$", "ozellik:finans.nakit"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/finance/tax-calendar(/.*)?$", "ozellik:finans.vergi-takvimi"),
    (frozenset({"POST"}), r"^/api/v1/finance/notes$", "ozellik:finans.sapma-notu"),
    # Aylık finansal yorum taslağı (Zeki AI) ve düzeltmesi; onay açıkça verilen `finans.yorum-onay` ile ucun içinde.
    (frozenset({"POST", "PUT"}), r"^/api/v1/finance/commentary(/draft)?$", "ozellik:finans.yorum"),
    (frozenset({"GET"}), r"^/api/v1/finance/(pnl/export\.xlsx|profitability/export\.csv)$", "ozellik:veri.disa-aktar"),
    # İlk dağılım: öneri, düzeltme, onaya gönderme, revizyon, takip ve liste yenileme. Onay/geri gönderme açıkça
    # verilen `dagilim.onay` ile ucun içinde; sevk listesi (Excel) dışa aktarma yetkisiyle.
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/distribution/(plans(?!/[^/]+/(approve|reject)$)(/.*)?|books/refresh)$",
     "ozellik:dagilim.plan"),
    (frozenset({"GET"}), r"^/api/v1/distribution/plans/[^/]+/export\.xlsx$", "ozellik:veri.disa-aktar"),
    # M43 Depo ve stok: öneri kararı ve güvenlik stoku taslağı; eşik onayı/reddi açıkça verilen `stok.esik-onay` ile ucun
    # içinde; Excel dışa aktarma yetkisiyle. Sayım/düzeltme notu sayfa yetkisiyle gelir.
    (frozenset({"POST"}), r"^/api/v1/stock/(suggestions/[^/]+/decision|thresholds)$", "ozellik:stok.oneri-karar"),
    (frozenset({"GET"}), r"^/api/v1/stock/export/[^/]+\.xlsx$", "ozellik:veri.disa-aktar"),
    # İK personel listesinin Excel'i (kişisel veri): İK yetkisine ek olarak genel dışa aktarma yetkisi.
    (frozenset({"GET"}), r"^/api/v1/hr/portal/admin/export$", "ozellik:veri.disa-aktar"),
    (frozenset({"GET"}), r"^/api/v1/hr/leave/admin/payroll$", "ozellik:veri.disa-aktar"),
    # İhale: kayıt, dosya, kalem, eşleştirme, kontrol listesi, karar önerisi, sonuç. Karar onayı/geri gönderme açıkça
    # verilen `ihale.karar` ile, ilan kaynağı `ihale.kaynak-yonet` ile ucun içinde; şirket belge arşivi `ihale.belge`.
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/tenders(/(?!run-due$|watch/|documents(/|$)|[^/]+/decision/(approve|reject)$).*)?$", "ozellik:ihale.duzenle"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/tenders/documents(/[^/]+)?$", "ozellik:ihale.belge"),
    (frozenset({"GET"}), r"^/api/v1/tenders/[^/]+/pricing\.xlsx$", "ozellik:veri.disa-aktar"),
    # Risk ve uyum: risk kaydı, gözden geçirme, aksiyon ekleme, Zeki AI önerisi/sınıflaması, brifing taslağı. Aksiyon
    # durumu (sahibi), gösterge tanımı/onayı, brifing onayı ve KVKK maddeleri açıkça verilen yetkilerle ucun içinde.
    (frozenset({"POST", "PATCH"}),
     r"^/api/v1/risk/(risks(/(suggest|classify|[^/]+(/(review|actions|accept|reject))?))?|reports/(draft|[^/]+))$", "ozellik:risk.yaz"),
    (frozenset({"POST", "PATCH"}), r"^/api/v1/risk/compliance/(items(/[^/]+)?|events/[^/]+/(evidence|close))$", "ozellik:uyum.yaz"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/risk/(policies|bcp)(/[^/]+(/document)?)?$", "ozellik:risk.sigorta-bcp"),
    (frozenset({"GET"}), r"^/api/v1/risk/reports/[^/]+/document\.docx$", "ozellik:veri.disa-aktar"),
    # DYK kurul paketi PDF'i (dondurulmuş paket; her indirme dağıtım kaydına yazılır).
    (frozenset({"GET"}), r"^/api/v1/kurul/packages/[^/]+/document\.pdf$", "ozellik:veri.disa-aktar"),
    # Kategori ağacı: öneri üretme ve kaynak yenileme; ağaç taslağı, eşleme, kural ve etiket sözlüğü. Ağaç onayı ve
    # profil kararı açıkça verilen `kategori.agac-onay` / `kategori.profil-onay` (+ `kategori.herkesinki`) ile ucun içinde.
    (frozenset({"POST"}), r"^/api/v1/categories/(books/[^/]+/propose|refresh)$", "ozellik:kategori.oneri-uret"),
    (frozenset({"PUT", "POST", "DELETE"}),
     r"^/api/v1/categories/(tree|tree/(open|draft|suggest|submit|withdraw)|mappings|rules/[^/]+|tags/decision)$",
     "ozellik:kategori.agac-duzenle"),
    (frozenset({"GET"}), r"^/api/v1/categories/crm-diff/export\.xlsx$", "ozellik:veri.disa-aktar"),
    # Güvenlik uyarısını kapatma/yeniden açma. Oturum kapatma ve saklama politikası açıkça verilir, ucun içinde.
    (frozenset({"PATCH"}), r"^/api/v1/data-security/alerts/[^/]+$", "ozellik:guvenlik.uyari-kapat"),
    # M39 Pazar ve rakip: rapor yükleme/silme/çıkarım, rakam kararı ve elle rakam, eşleme kararı/önerisi ve kaynak
    # yenileme, özet taslağı/düzenleme/onaya gönderme. Özet onayı ve geri gönderme açıkça verilen `pazar.ozet-onay` ile
    # ucun içinde; izlenen rakip listesi ve emsal arama sayfa yetkisiyle gelir.
    (frozenset({"POST", "DELETE"}), r"^/api/v1/pazar/reports(/[^/]+(/extract)?)?$", "ozellik:pazar.rapor-yukle"),
    (frozenset({"POST"}), r"^/api/v1/pazar/(figures/[^/]+/decision|reports/[^/]+/figures)$", "ozellik:pazar.rakam-onay"),
    (frozenset({"POST"}), r"^/api/v1/pazar/(category-map/(decision|suggest)|refresh)$", "ozellik:pazar.kategori-esleme"),
    (frozenset({"POST", "PATCH"}), r"^/api/v1/pazar/briefs/(draft|(?!draft$)[^/]+(/submit)?)$", "ozellik:pazar.ozet-yaz"),
    (frozenset({"GET"}), r"^/api/v1/pazar/matrix/export\.csv$", "ozellik:veri.disa-aktar"),
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
    # M44 Kargo: Zeki AI mesaj taslağı (gecikme/özür/iade; gönderimi insan yapar) ve Excel. Karar kaydı ve iş eşikleri
    # açıkça verilen `kargo.karar`, maliyet `kargo.maliyet`, alıcı adı `kargo.alici` ile ucun içinde denetlenir.
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/shipping/drafts(/[^/]+)?$", "ozellik:kargo.taslak"),
    (frozenset({"GET"}), r"^/api/v1/shipping/export/[^/]+\.xlsx$", "ozellik:veri.disa-aktar"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/marketing/gift-offers(/[^/]+(/(letter|submit|withdraw))?)?$",
     "ozellik:set.yaz"),
    (frozenset({"GET"}), r"^/api/v1/marketing/sets/[^/]+/card-todo\.(csv|pdf)$", "ozellik:veri.disa-aktar"),
    # M18 ay planı: taslağı kurma, kalem düzeltme, bütçe, öneri, onaya gönderme, revizyon (onaylar ucun içinde).
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/marketing/months/[^/]+/(build|items(/[^/]+)?|budget|suggest|submit|withdraw|revise)$",
     "ozellik:pazarlama.plan-yaz"),
    (frozenset({"GET"}), r"^/api/v1/marketing/months/[^/]+/summary\.pdf$", "ozellik:veri.disa-aktar"),
    # Satış föyü: düzeltme, CRM'den yenileme, onaya gönderme, Zeki AI argümanı. Föy onayı (`foy-onay`) ve paketi e-postayla
    # gönderme (`foy-gonder`) açık yetkilerle ucun içinde. Föy PDF'i ve paketi `veri.disa-aktar` istemez (saha işi).
    (frozenset({"PUT"}), r"^/api/v1/marketing/foy/[^/]+$", "ozellik:pazarlama.foy-yaz"),
    (frozenset({"POST"}), r"^/api/v1/marketing/foy/[^/]+/(refresh|submit|draft-args)$", "ozellik:pazarlama.foy-yaz"),
    # M51 Müşteri hizmetleri: Zeki AI sınıflama, cevap taslağı ve sonucu, sınıf düzeltme (model harcar). Müşteri bağlamı,
    # SSS onayı, bütün kuyruk ve sınıf/SLA ayarı açıkça verilen anahtarlarla ucun içinde denetlenir.
    (frozenset({"POST"}), r"^/api/v1/support/(classify|draft|drafts/[^/]+/outcome)$", "ozellik:destek.oneri"),
    (frozenset({"PUT"}), r"^/api/v1/support/insights/[^/]+/class$", "ozellik:destek.oneri"),
    # M54 Telif dönemi: koşu açma, hesaplama, seçenek, satır kararı, onaya gönderme/geri çekme, iptal. Onay/geri gönderme,
    # beyanname, ödeme listesi ve avans açılışı açıkça verilen yetkilerle ucun içinde denetlenir.
    (frozenset({"POST", "PATCH"}), r"^/api/v1/royalty/runs(/[^/]+(/(compute|submit|withdraw|cancel|lines/[^/]+))?)?$",
     "ozellik:telif.kosu"),
    (frozenset({"PATCH"}), r"^/api/v1/royalty/renewals/[^/]+$", "ozellik:telif.yenileme-karar"),
    (frozenset({"GET"}), r"^/api/v1/royalty/runs/[^/]+/(payments\.csv|withholding\.csv|statements\.zip"
                         r"|parties/[^/]+/statement\.docx)$", "ozellik:veri.disa-aktar"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/rights/(grants(/[^/]+)?|notes/classify|notes/[^/]+/approve|map/extract|map/[^/]+/decide)$",
     "ozellik:haklar.duzenle"),
    (frozenset({"POST", "PATCH"}), r"^/api/v1/rights/licenses-out(/[^/]+)?$", "ozellik:haklar.lisans"),
    # Okur veri tabanı: birleştirme kararı ve kaynak yenileme; segment taslağı/düzenleme/onaya gönderme/arşiv ve Zeki
    # önerisi; etkinlik dosyası. Kişisel veri, segment onayı ve liste dışa aktarımı açıkça verilen yetkilerle ucun içinde.
    (frozenset({"POST"}), r"^/api/v1/readers/(refresh|merge-candidates/[^/]+/decision)$", "ozellik:okur.birlestir"),
    (frozenset({"POST", "PATCH"}), r"^/api/v1/readers/segments(/(draft-from-text|[^/]+(/(submit|archive))?))?$",
     "ozellik:okur.segment"),
    (frozenset({"POST", "DELETE"}), r"^/api/v1/readers/imports(/[^/]+(/confirm)?)?$", "ozellik:okur.ice-aktar"),
    (frozenset({"POST"}), r"^/api/v1/readers/segments/[^/]+/export$", "ozellik:veri.disa-aktar"),
    (frozenset({"GET"}), r"^/api/v1/readers/imports/[^/]+/crm\.csv$", "ozellik:veri.disa-aktar"),
    # Lansman: paket açma, kontrol listesi, etkinlik/medya kaydı, veri yenileme, rapor taslağı. Değerlendirme kararı açıkça
    # verilen `pazarlama.plan-onay` ile ucun içinde denetlenir; bu kural ona uymaz.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/marketing/launches(?!/run-due$)(?!/[^/]+/reviews/[^/]+/decide$)(/.*)?$", "ozellik:pazarlama.lansman-yaz"),
    (frozenset({"GET"}), r"^/api/v1/marketing/launches/[^/]+/export\.pdf$", "ozellik:veri.disa-aktar"),
    # M17 Backlist: aktivasyon planı açma, kitap listesi, içerik taslağı, konu eşleşmesi kararı (plan yazma ile aynı iş);
    # ekip ağırlığı ayrı yetki; liste CSV'si dışa aktarım.
    (frozenset({"POST", "PUT"}), r"^/api/v1/marketing/backlist/(plans(/[^/]+/(books|materials))?|matches/[^/]+/decide)$",
     "ozellik:pazarlama.plan-yaz"),
    (frozenset({"GET"}), r"^/api/v1/marketing/backlist/export\.csv$", "ozellik:veri.disa-aktar"),
    # Basın ilişkileri: PR dosyası, liste, Zeki AI taslağı, medya kişisi, yansıma. Dosya/satır onayı (`pr.onay`) ve
    # tek alıcılı e-posta (`pr.gonder`) açıkça verilen yetkilerle ucun içinde denetlenir; bu kural onlara uymaz.
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/pr/(kits(/[^/]+(/(draft|submit|withdraw|close|reopen|sends))?)?|sends/[^/]+(/pitch)?"
     r"|contacts(/[^/]+)?|coverage(/[^/]+)?)$", "ozellik:pr.duzenle"),
    (frozenset({"GET"}), r"^/api/v1/pr/report/export\.(pdf|xlsx)$", "ozellik:veri.disa-aktar"),
    # M21 Reklam: hesap, dosya içe aktarma, kampanya ↔ kitap bağı, bütçe planı, brief, satış verisi yenileme. Para kararı
    # olan önerinin onayı/reddi açıkça verilen `reklam.onay` ile ucun içinde; «uygulandı» işareti de ucun içinde.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/ads/(accounts(/[^/]+)?|imports(/preview|/[^/]+)?|campaigns/[^/]+(/match)?|budget|briefs(/[^/]+)?|refresh)$",
     "ozellik:reklam.duzenle"),
    (frozenset({"GET"}), r"^/api/v1/ads/report/export\.(pdf|xlsx)$", "ozellik:veri.disa-aktar"),
    # M22 Sosyal medya: taslak, takvim, hesap, içe aktarma, Zeki AI taslağı/yorumu. Onay ve geri gönderme açıkça verilen
    # `sosyal.onay` ile ucun içinde denetlenir; bu kural onlara uymaz.
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/social/(posts(/[^/]+(/(submit|withdraw|published|cancel|reopen|draft|metrics))?)?|accounts(/[^/]+)?"
     r"|imports(/[^/]+)?|report/commentary)$",
     "ozellik:sosyal.duzenle"),
    (frozenset({"GET"}), r"^/api/v1/social/(posts/[^/]+/package\.zip|report/export\.pdf)$", "ozellik:veri.disa-aktar"),
    # İşbirlikleri: kayıt defteri, ölçüm, CSV, işbirliği kartı, taslak, «gönderildi» kaydı, aday gerekçesi. Teklif ve
    # taslak onayı `isbirligi.onay`, ödeme `isbirligi.odeme` (açıkça verilen) ucun içinde denetlenir.
    (frozenset({"POST", "PATCH"}),
     r"^/api/v1/influencers/(people(/import|/[^/]+(/suggest-topics)?)?|accounts/[^/]+/snapshots"
     r"|books/[^/]+/candidates/explain|collabs(/[^/]+(/(draft|mail|drafts/[^/]+))?)?)$", "ozellik:isbirligi.duzenle"),
    (frozenset({"GET"}), r"^/api/v1/influencers/(payouts|report)/export\.xlsx$", "ozellik:veri.disa-aktar"),
    # Katalog ve bülten: katalog/bülten kaydı, kitap listesi, öneri, Zeki AI metni, onaya gönderme, yayın/gönderim işareti,
    # sonuç. Onay/geri gönderme açıkça verilen `katalog-bulten.onay`, segment sayacı `bulten.segment` ile ucun içinde.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/catalog-newsletter/(pool/refresh|catalogs(/[^/]+(/(items(/[^/]+/accept)?|suggest|zeki|submit|withdraw|publish"
     r"|archive|reopen))?)?)$", "ozellik:katalog.duzenle"),
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/catalog-newsletter/newsletters(/[^/]+(/(items|suggest|draft|submit|withdraw|mark-sent|archive|reopen"
     r"|results(/[^/]+)?))?)?$", "ozellik:bulten.duzenle"),
    (frozenset({"GET"}), r"^/api/v1/catalog-newsletter/(catalogs/[^/]+/(export\.xlsx|package\.zip|preview\.pdf)"
                         r"|newsletters/[^/]+/html)$", "ozellik:veri.disa-aktar"),
    # M27: fuar kartı, kitap önerisi ve listesi, görev ekleme/silme, gider, yazar programı, tip eşlemesi. Görevi işaretlemek
    # (PATCH tasks) görevin sahibine de açık, katılım kararı açıkça verilen `etkinlik.onay` ile — ikisi ucun içinde.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/events/(fairs(/[^/]+(/(suggest-books|books|costs(/[^/]+)?|authors(/[^/]+)?))?)?|type-map(/suggest)?)$",
     "ozellik:etkinlik.duzenle"),
    (frozenset({"POST", "DELETE"}), r"^/api/v1/events/fairs/[^/]+/tasks(/[^/]+)?$", "ozellik:etkinlik.duzenle"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/events/(awards(/[^/]+(/entries)?)?|award-entries/[^/]+)$",
     "ozellik:odul.duzenle"),
    (frozenset({"GET"}), r"^/api/v1/events/fairs/[^/]+/result/export\.pdf$", "ozellik:veri.disa-aktar"),
    # Kanallar (M42): eşleme yazma (cari, kanal kodu, hedef bölgesi, Zeki AI adayı), panel dosyası yükleme/silme, öneri
    # taslağı. Marj/simülasyon ve öneri kararı açıkça verilen `kanal.marj` / `kanal.oneri-karar` ile ucun içinde.
    (frozenset({"POST", "PUT", "DELETE"}), r"^/api/v1/channels/accounts(/.*)?$", "ozellik:kanal.eslesme"),
    (frozenset({"POST", "DELETE"}), r"^/api/v1/channels/imports(/[^/]+)?$", "ozellik:kanal.yukle"),
    (frozenset({"POST"}), r"^/api/v1/channels/(suggestions|d2c/suggest)$", "ozellik:kanal.oneri-yaz"),
    (frozenset({"GET"}), r"^/api/v1/channels/export/[^/]+\.xlsx$", "ozellik:veri.disa-aktar"),
    # M40/M41: panel dosyası, Zeki AI taslağı/sınıflama/vitrin önerisi, pazar kartı, eşleme listesine ekleme, Excel.
    # Öneri/pazar kararı ve finans parametresi açıkça verilen anahtarla ucun içinde.
    (frozenset({"POST", "DELETE"}), r"^/api/v1/channels/trendyol/imports(/[^/]+)?$", "ozellik:trendyol.yukle"),
    (frozenset({"POST"}), r"^/api/v1/channels/trendyol/((questions|reviews)/[^/]+/draft|claims/classify|showcase/suggest)$",
     "ozellik:trendyol.taslak"),
    (frozenset({"POST", "PUT"}), r"^/api/v1/channels/amazon/(drafts(/[^/]+)?|market-cards)$", "ozellik:amazon.taslak"),
    (frozenset({"POST"}), r"^/api/v1/channels/(trendyol|amazon)/cariler/ekle$", "ozellik:kanal.eslesme"),
    (frozenset({"GET"}), r"^/api/v1/channels/(trendyol|amazon)/export/[^/]+\.xlsx$", "ozellik:veri.disa-aktar"),
    # Aşama 1 panel dosyaları (hakediş; Amazon sipariş/iade raporu) ve mutabakat Excel'i.
    (frozenset({"POST", "DELETE"}), r"^/api/v1/channels/trendyol/mutabakat/dosyalar(/[^/]+)?$", "ozellik:trendyol.yukle"),
    (frozenset({"POST", "DELETE"}), r"^/api/v1/channels/amazon/mutabakat/dosyalar(/[^/]+)?$", "ozellik:amazon.yukle"),
    (frozenset({"GET"}), r"^/api/v1/channels/(trendyol|amazon)/mutabakat/export/[^/]+\.xlsx$", "ozellik:veri.disa-aktar"),
    # M36 Dijital yayın: platform durumu, platform tanımı, katalog okuması; satış raporu yükleme/eşleme/onay. Hak kararı
    # (`dijital.hak-karari`) ve dijital fiyat kararı (`dijital.fiyat-onay`) açıkça verilir, ucun içinde denetlenir.
    (frozenset({"PUT"}), r"^/api/v1/dijital/titles/[^/]+/listings/[^/]+$", "ozellik:dijital.durum-yaz"),
    (frozenset({"POST", "PATCH"}), r"^/api/v1/dijital/(platforms(/[^/]+)?|refresh)$", "ozellik:dijital.durum-yaz"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/dijital/imports(/[^/]+(/(match|rows|accept-strong|commit))?)?$",
     "ozellik:dijital.rapor-yukle"),
    (frozenset({"GET"}), r"^/api/v1/dijital/(opportunities|sales)/export\.csv$", "ozellik:veri.disa-aktar"),
    # M35 Kampanya: kampanya, kitap/indirim, toplu hesap, onaya gönderme/geri çekme, iptal, takvim, öğrenim, veri yenileme.
    # Onay/geri gönderme (decision) açıkça verilen `kampanya.onay` ile ucun içinde; Zeki AI metni ve sonuç özeti `metin-uret`.
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/kampanya/(refresh|calendar(/[^/]+)?|learnings/[^/]+|campaigns(/[^/]+(/(items(/.+)?|simulate|submit|withdraw|cancel"
     r"|learnings|results/refresh))?)?)$", "ozellik:kampanya.duzenle"),
    (frozenset({"POST"}), r"^/api/v1/kampanya/campaigns/[^/]+/(copy|summary)$", "ozellik:kampanya.metin-uret"),
    (frozenset({"GET"}), r"^/api/v1/kampanya/campaigns/[^/]+/export\.xlsx$", "ozellik:veri.disa-aktar"),
    (frozenset({"POST"}), r"^/api/v1/editorial/books/[^/]+/review/decide$", "ozellik:kitap.inceleme-karar"),
    (frozenset({"POST"}), r"^/api/v1/editorial/proofing/decision$", "ozellik:son-okuma.karar"),
    (frozenset({"PUT"}), r"^/api/v1/editorial/documents$", "ozellik:son-okuma.belge"),
    # Kitap okutma (Kitaba sor): PDF gelen kutusuna yazılır, GPU'da uzun okuma işi başlar.
    (frozenset({"PUT", "DELETE"}), r"^/api/v1/editorial/ask/read(/[^/]+)?$", "ozellik:kitap.okut"),
    # Çeviri: iş açma, atama, kaynak, ZEKİ taslağı, redaksiyona aktarma; onaylı terim bankası. Çevirmenin kendi
    # işi (segment kaydı, XLIFF içe aktarımı, terim önerisi) sayfa yetkisi + işteki rolüyle olur. ZEKİ kalite tahmini
    # (POST …/jobs/{iş}/qe) da model harcar ama işin inceleyenine de açıktır: «ceviri.yonet YA DA inceleyen» burada
    # yazılamadığı için ucun içinde denetlenir (editorial_translation_qe.may_run), bu listede kuralı yoktur.
    (frozenset({"POST"}), r"^/api/v1/editorial/translation/jobs$", "ozellik:ceviri.yonet"),
    (frozenset({"PATCH", "DELETE"}), r"^/api/v1/editorial/translation/jobs/[^/]+$", "ozellik:ceviri.yonet"),
    (frozenset({"PUT"}), r"^/api/v1/editorial/translation/jobs/[^/]+/source$", "ozellik:ceviri.yonet"),
    (frozenset({"PUT"}), r"^/api/v1/editorial/translation/jobs-from-file$", "ozellik:ceviri.yonet"),
    (frozenset({"POST"}), r"^/api/v1/editorial/translation/jobs/[^/]+/(draft|to-redaction)$", "ozellik:ceviri.yonet"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/editorial/translation/terms(/(?!propose$)[^/]+)?$", "ozellik:ceviri.terim"),
    (frozenset({"PUT"}), r"^/api/v1/editorial/translation/terms/import$", "ozellik:ceviri.terim"),
    # Çeviri işinin M8 bağı (serbest çalışan, kelime ücreti, iş paketi, hakedişe aktarım): M8 kişisini ve ücretini
    # okumak `serbest.yonet`, yazmak ayrıca `ceviri.yonet` ister.
    (frozenset({"PUT", "POST"}), r"^/api/v1/editorial/translation/jobs/[^/]+/payout(/(package|transfer))?$", "ozellik:ceviri.yonet"),
    (frozenset({"GET", "PUT", "POST"}), r"^/api/v1/editorial/translation/jobs/[^/]+/payout(/(package|transfer))?$",
     "ozellik:serbest.yonet"),
    # Terim bankası TBX ve dış çeviri belleği (TMX): içe aktarma terim/yönetim yetkisiyle, dışa aktarma veri yetkisiyle.
    (frozenset({"PUT"}), r"^/api/v1/editorial/translation/terms/import\.tbx$", "ozellik:ceviri.terim"),
    (frozenset({"PUT"}), r"^/api/v1/editorial/translation/memory/import$", "ozellik:ceviri.yonet"),
    (frozenset({"DELETE"}), r"^/api/v1/editorial/translation/memory$", "ozellik:ceviri.yonet"),
    (frozenset({"GET"}), r"^/api/v1/editorial/translation/(terms/export\.tbx|memory/export\.tmx)$", "ozellik:veri.disa-aktar"),
    # Serbest çalışan kaydı, paket, atama, teslim kararı, hakediş taslağı. Yazışma ve öneri (suggest) sayfayla gelir;
    # hakediş onayı/ödemesi açıkça verilen `serbest.hakedis-onay` ile ucun içinde denetlenir.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/editorial/freelance/((people|portfolio|packages|tasks|assign|deliveries)(/.*)?|payouts(/[^/]+/(submit|delete))?)$",
     "ozellik:serbest.yonet"),
    # Üretim kartına tarih/not/kalite/teklif yazma; matbaa onayı açıkça verilen `uretim.matbaa-onay` ile ucun içinde.
    (frozenset({"POST", "DELETE"}), r"^/api/v1/editorial/production/(cards/[^/]+/(entries|quotes)|entries/[^/]+|quotes/[^/]+)$",
     "ozellik:uretim.yaz"),
    # M52 Tedarik: matbaa kapasitesi; yük dengeleme / kağıt önerisi kararı ve taslak (şartname, gecikme yazısı). Borç,
    # maliyet ve fatura/cari eşleşmesi açıkça verilen `tedarik.borc|maliyet|eslesme` ile ucun içinde denetlenir.
    (frozenset({"PUT", "DELETE"}), r"^/api/v1/supply/capacity(/[^/]+)?$", "ozellik:tedarik.kapasite"),
    (frozenset({"POST"}), r"^/api/v1/supply/(suggestions/[^/]+/decision|drafts)$", "ozellik:tedarik.oneri-karar"),
    (frozenset({"GET"}), r"^/api/v1/supply/export/[^/]+\.xlsx$", "ozellik:veri.disa-aktar"),
    # Saha: ziyaret notu, takip taslağı ve ödeme planı taslağı; müdür önceliği. Plan onayı/reddi, bütün temsilcileri görme
    # ve temsilci karşılaştırması açıkça verilen anahtarlarla ucun içinde denetlenir.
    (frozenset({"POST", "PATCH"}), r"^/api/v1/field/(visits(/[^/]+(/followup-draft)?)?|payment-plans(/[^/]+(/submit)?)?)$",
     "ozellik:saha.not"),
    (frozenset({"POST", "DELETE"}), r"^/api/v1/field/overrides(/[^/]+)?$", "ozellik:saha.oncelik-duzenle"),
    (frozenset({"GET"}), r"^/api/v1/field/report/weekly\.xlsx$", "ozellik:veri.disa-aktar"),
    # M59 Bayi riski: ziyaret notu, aksiyon, kural taslağı (önizleme okuma sayılır). Bütün bayileri görme, limit önerisi
    # kararı ve kural onayı açıkça verilen anahtarlarla ucun içinde denetlenir.
    (frozenset({"POST"}), r"^/api/v1/dealers/[^/]+/notes$", "ozellik:bayi.not"),
    (frozenset({"POST", "PATCH"}), r"^/api/v1/dealers/actions(/[^/]+)?$", "ozellik:bayi.aksiyon"),
    (frozenset({"POST", "PATCH"}), r"^/api/v1/dealers/rules(/[^/]+(/submit)?)?$", "ozellik:bayi.kural"),
    (frozenset({"GET"}), r"^/api/v1/dealers/list/export\.csv$", "ozellik:veri.disa-aktar"),
    # M38 Müşteri ilişkileri: aksiyon yazma/güncelleme; veri sağlığı bulgusunu işaretleme; dışa aktarma. Bütün carileri
    # görme ve güvenlik bulguları açıkça verilen anahtarlarla ucun içinde denetlenir.
    (frozenset({"POST", "PATCH"}), r"^/api/v1/musteri/(accounts/[^/]+/actions|actions/[^/]+)$", "ozellik:musteri.eylem-yaz"),
    (frozenset({"POST"}), r"^/api/v1/musteri/health/[^/]+/mark$", "ozellik:musteri.bulgu-isaretle"),
    (frozenset({"GET"}), r"^/api/v1/musteri/(accounts|health)/export\.csv$", "ozellik:veri.disa-aktar"),
    # M32 Kurumsal satış: fırsat, paket, teklif, kurum segmenti, hatırlatmadan fırsat, veri yenileme. Teklif onayı/geri
    # gönderme açıkça verilen `kurumsal.teklif-onay` ile ucun içinde denetlenir; bu kural onlara uygulanmaz.
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/corporate/(opportunities(/[^/]+(/quotes)?)?|quotes/[^/]+(/(submit|withdraw|sent|result|letter))?"
     r"|packages/suggest|accounts/[^/]+|reminders/[^/]+(/opportunity)?|refresh)$", "ozellik:kurumsal.teklif"),
    (frozenset({"POST"}), r"^/api/v1/corporate/themes/[^/]+/approve$", "ozellik:kurumsal.tema-onay"),
    (frozenset({"GET"}), r"^/api/v1/corporate/b2b/.+$", "ozellik:kurumsal.b2b"),
    (frozenset({"GET"}), r"^/api/v1/corporate/(quotes/[^/]+/document\.(pdf|xlsx)|b2b/(dealers|highlights)\.csv)$",
     "ozellik:veri.disa-aktar"),
    # M28 Kurumsal ilişkiler: kişi/kurum kartı, temas notu, hediye satırı ve önerisi, kişisel not taslağı, proje ve teklif
    # taslağı. Hediye/bütçe/teklif onayı ve alan listesi açıkça verilen `iliskiler.onay`, başkasının gizli notunu okumak
    # `iliskiler.hassas` ile ucun içinde denetlenir; bu kural onlara uygulanmaz.
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/public-affairs/(people(/[^/]+(/(notes|suggest-field))?)?|notes/[^/]+|orgs(/[^/]+(/notes)?)?"
     r"|gifts(/(?!approve$)[^/]+(/draft-note)?)?|projects(/[^/]+(/draft-proposal)?)?)$", "ozellik:iliskiler.duzenle"),
    (frozenset({"GET"}), r"^/api/v1/public-affairs/(report/export\.pdf|projects/[^/]+/proposal\.pdf)$", "ozellik:veri.disa-aktar"),
    # Fiyatlama (M9): analiz, pazar fiyatı, varsayılan ve toplu zam teklifi yazımı. Hesap (`calc`) ve okuma sayfayla
    # gelir; onay imzaları açıkça verilen `fiyatlama.onay-<rol>` ile ucun içinde denetlenir.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}),
     r"^/api/v1/pricing/(analyses(/[^/]+(/(submit|withdraw|archive))?)?|market(/[^/]+)?|defaults|proposals|refresh)$",
     "ozellik:fiyatlama.yaz"),
    # M1 başvuru: kayıt, dosya, editör raporu ve kararı, kurul raporu, yazışma. Kurul üyesinin oyu sayfa yetkisi +
    # oturum üyeliğiyle olur; oturum yönetimi açıkça verilen `yayin-kurulu.yonet` ile ucun içinde denetlenir.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}), r"^/api/v1/editorial/applications(/.*)?$", "ozellik:basvuru.yaz"),
    # H4 Kurumsal e-posta: atama, tür/durum düzeltme, başvuru bilgisi ve aktarımı, etiketleme; kural taslağı. Kural onayı
    # (`eposta.kural-onay`) ve iş başvurusu (`eposta.ik`) açıkça verilir, ucun içinde denetlenir.
    (frozenset({"POST"}), r"^/api/v1/mailbox/(messages/[^/]+/(assign|category|status|application|to-intake)|labeling/[^/]+)$",
     "ozellik:eposta.ata"),
    (frozenset({"PUT", "DELETE"}), r"^/api/v1/mailbox/rules(/draft)?$", "ozellik:eposta.kural"),
    (frozenset({"POST", "PATCH", "DELETE"}),
     r"^/api/v1/editorial/authors/(cards(/[^/]+)?|by-crm/[^/]+/card|meetings(/[^/]+)?)$", "ozellik:yazar-iliski.yaz"),
    (frozenset({"POST"}), r"^/api/v1/editorial/authors/advice/[^/]+$", "ozellik:yazar-iliski.oneri"),
    # M31: ziyaret raporu, plan önerisi/düzeltmesi, katalog, bayi önerme; bağlam (ilçe endeksi, takvim) yükleme.
    # Plan onayı (`okul.plan`), bayi eşleştirme onayı (açıkça verilen `okul.bayi-onay`) ve bütün ekibi görme
    # (`okul.herkesinki`) ucun içinde denetlenir.
    (frozenset({"POST", "PATCH"}),
     r"^/api/v1/schools/((?!run-due$|context/)[^/]+/(visits(/suggest)?|plan|catalog|dealers)|plan/generate|plan/[^/]+"
     r"|visits/[^/]+/next-done)$", "ozellik:okul.ziyaret"),
    (frozenset({"POST"}), r"^/api/v1/schools/context/upload$", "ozellik:okul.baglam-yukle"),
    (frozenset({"GET"}), r"^/api/v1/schools/catalogs/[^/]+\.pdf$", "ozellik:veri.disa-aktar"),
    # Kitap Tasarım Stüdyosu: işin altındaki her yazma (üretim, düzenleme, onay, yükleme; yeni uçlar da kendiliğinden)
    # «Kitap tasarımında üretim ve düzenleme» ister. Dışarıda kalan iki POST okumadır: `plan/prepare` sayfa düzeni
    # ekranının açılışı, `narration/read` metnin nasıl okunacağını döndürür. Ses kütüphanesine yükleme de aynı yetki;
    # sesi kaldırma ve kapak arşivi beslemesi ucun içinde yalnız yönetici. İndirilen dosyalar `veri.disa-aktar`;
    # tek sosyal görselin indirmesi (`marketing/social/{sid}?download=1`) görüntülemeyle aynı yolda olduğundan ucun içinde.
    (frozenset({"POST", "PUT", "PATCH", "DELETE"}), _S + r"(/(?![^/]+/(plan/prepare|narration/read)$).*)?$",
     "ozellik:tasarim.uret"),
    (frozenset({"POST"}), r"^/api/v1/editorial/studio/voices$", "ozellik:tasarim.uret"),
    (frozenset({"GET"}), _S + r"/[^/]+/(pdf/[^/]+|age/pdf|plan/versions/report|epub/file"
                               r"|marketing/(product/export|social/zip|guide/pdf))$", "ozellik:veri.disa-aktar"),
    # M19: talep açma; üretim (görsel dizimi, Zeki AI metni, başlık önerisi), kapak yükleme ve varlık düzeltme.
    # Tasarım/mesaj onayı ve marka kiti açıkça verilen yetkilerle ucun içinde denetlenir.
    (frozenset({"POST"}), r"^/api/v1/marketing/creative/(requests|from-material/[^/]+)$", "ozellik:icerik.talep"),
    (frozenset({"POST"}), r"^/api/v1/marketing/creative/requests/[^/]+/(produce|copy|headlines)$", "ozellik:icerik.uret"),
    (frozenset({"PUT"}), r"^/api/v1/marketing/creative/(requests/[^/]+/cover|assets/[^/]+)$", "ozellik:icerik.uret"),
    # M37 Okur topluluğu: segment taslağı/ölçümü/onaya gönderme, program ve duyuru taslağı, yorum cevap taslağı. Segment
    # onayı ve ilgi alanı KVKK kararı açıkça verilen `topluluk.segment-onay`, liste dışa aktarımı `topluluk.liste-disa-aktar`
    # ile ucun içinde denetlenir; bu kurallar onlara uygulanmaz.
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/okur/segments(/preview-rule|/(?!preview-rule$)[^/]+(/(preview|submit|withdraw))?)?$",
     "ozellik:topluluk.segment-yaz"),
    (frozenset({"POST"}), r"^/api/v1/okur/categories/classify$", "ozellik:topluluk.segment-yaz"),
    (frozenset({"POST", "PATCH", "DELETE"}), r"^/api/v1/okur/programs(/[^/]+(/draft)?)?$", "ozellik:topluluk.program-yaz"),
    (frozenset({"POST"}), r"^/api/v1/okur/reviews/[^/]+/(draft|mark)$", "ozellik:topluluk.yorum-taslak"),
    # M34 E-ticaret: fark işaretleme ve okumayı yenileme; Zeki AI kart önerisi (model harcar); fark CSV'si ve içerik paketi.
    # Öneri onayı açıkça verilen `eticaret.oneri-onay` ile ucun içinde denetlenir.
    (frozenset({"POST"}), r"^/api/v1/eticaret/(refresh|diffs/mark-bulk|diffs/[^/]+/mark)$", "ozellik:eticaret.fark-isaretle"),
    (frozenset({"POST"}), r"^/api/v1/eticaret/items/[^/]+/propose$", "ozellik:eticaret.oneri-uret"),
    (frozenset({"GET"}), r"^/api/v1/eticaret/(diffs/export\.csv|export/content-pack)$", "ozellik:veri.disa-aktar"),
    # H3 E-ticaret müşteri: tetik yazma/önizleme/çalıştırma ve kampanya açma; eşikler ve T-soft okuması; liste dosyası.
    # Liste onayı (`eticaret.liste-onay`), dışa aktarım (`okur.liste-aktar`) ve kişisel veri (`okur.kisisel-veri`) açıkça
    # verilir, ucun içinde denetlenir.
    (frozenset({"POST", "PATCH"}), r"^/api/v1/commerce/(triggers(/[^/]+(/(preview|run))?)?|campaigns(/[^/]+/comment)?)$",
     "ozellik:eticaret.tetik"),
    (frozenset({"POST", "PUT"}), r"^/api/v1/commerce/(refresh|settings)$", "ozellik:eticaret.ayar"),
    (frozenset({"POST"}), r"^/api/v1/commerce/runs/[^/]+/export$", "ozellik:veri.disa-aktar"),
    (frozenset({"POST"}), r"^/api/v1/seo-geo/(products/[^/]+/propose|pages/[^/]+/[^/]+/propose|proposals/batch)$",
     "ozellik:seo.oneri-uret"),
    (frozenset({"POST", "DELETE"}), r"^/api/v1/seo-geo/(sync|crm/sync|schema/crawl|search/refresh|questions(/[^/]+)?)$",
     "ozellik:seo.calistir"),
    # Uzman özellikleri (2.–3. tur): taslak üretme «öneri üret»; okuma/tarama/yenileme, iş listesi durumu ve soru önerisi
    # kararı «çalıştır»; dosya indirme «dışa aktar». Onay/ret/gönderim uçları onay yetkisini kendi içinde ister.
    (frozenset({"POST"}), r"^/api/v1/seo-geo/(guides|bios/[^/]+/draft|faq/[^/]+/draft|ga4/page-summary)$", "ozellik:seo.oneri-uret"),
    (frozenset({"POST"}), r"^/api/v1/seo-geo/((authors-trust|backlinks|bing|bios|entity|opportunities|qsuggest|reviews|seasons"
                          r"|similar|sunset|youtube|tech/sitemaps|gsc-sitemaps|merchant|ga4)/refresh|(competitors|crawlbot|impact|watch)/run|speed/run"
                          r"|tech/crawl|monthly/build|worklist/[^/]+/status|qsuggest/[^/]+/(accept|reject))$",
     "ozellik:seo.calistir"),
    (frozenset({"GET"}), r"^/api/v1/seo-geo/((worklist|similar|keymap|sunset|ga4)/export\.csv|video/(sitemap\.xml|theme-request\.md)"
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
        for t, s, m, at, err in c.execute(role_stmts("")["members"]).all():
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
    Zamanlayıcı (07:00 ve 12:00) ve yönetim ekranı çağırır; istek yolunda değil. `only` yalnız o bağı okur."""
    from semantic_layer.store import schema_stamp
    schema_stamp.create_all(_md, engine)
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

    def _people_rows(self) -> list[dict[str, Any]]:
        """Etkin kişiler (DN, hesap, görünen ad) — kişi listesi, OU sayıları ve iç içe grup sayıları buradan."""
        return self._cached("people_rows", 300.0, lambda: self._search(_PERSON, ["sAMAccountName", "displayName"]))

    def list_groups(self) -> list[dict[str, Any]]:
        """Güvenlik grupları (dağıtım listeleri ve Windows'un yerleşik grupları hariç), etkin kişi sayısıyla
        (iç içe gruplar dahil — bağlanınca rolü alacak kişi sayısının aynısı)."""
        def read() -> list[dict[str, Any]]:
            # Windows'un kendi grupları (Domain Admins, RODC, DnsAdmins…) isCriticalSystemObject taşır; listeye girmez.
            rows = self._search("(&(objectClass=group)(groupType:1.2.840.113556.1.4.803:=2147483648)"
                                "(!(isCriticalSystemObject=TRUE)))",
                                ["sAMAccountName", "description", "member", "groupType"])
            counts = nested_group_counts({str(r.get("_dn") or ""): list(r.get("member") or []) for r in rows},
                                         {str(p.get("_dn") or "") for p in self._people_rows()})
            out = []
            for r in rows:
                gt = int(_first(r.get("groupType")) or 0) & 0xFFFFFFFF
                dn = str(r.get("_dn") or "")
                if gt & 1 or ",CN=Builtin," in dn:
                    continue
                name = _first(r.get("sAMAccountName"))
                if name:
                    parts = _dn_parts(dn)
                    out.append({"subject": name, "label": name, "hint": _ou_path(",".join(parts[1:])),
                                "detail": _first(r.get("description")), "count": counts.get(dn.lower(), 0)})
            return sorted(out, key=lambda x: x["label"].lower())
        return self._cached("groups", 300.0, read)

    def list_ous(self) -> list[dict[str, Any]]:
        """Etkin kişisi olan OU'lar, kişi sayısıyla — alt birimler dahil (bağlanınca rolü alacak kişi sayısının
        aynısı: `ou_members` alt ağacı okur)."""
        def read() -> list[dict[str, Any]]:
            counts = ou_subtree_counts(str(r.get("_dn") or "") for r in self._people_rows())
            return sorted(({"subject": ou, "label": _ou_name(ou), "hint": _ou_path(ou), "count": n}
                           for ou, n in counts.items()), key=lambda x: x["label"].lower())
        return self._cached("ous", 300.0, read)

    def list_people(self) -> list[dict[str, Any]]:
        def read() -> list[dict[str, Any]]:
            out = []
            for r in self._people_rows():
                acc = _first(r.get("sAMAccountName")).lower()
                if acc:
                    out.append({"subject": acc, "label": _first(r.get("displayName")) or acc, "hint": acc,
                                "detail": _ou_name(",".join(_dn_parts(str(r.get("_dn") or ""))[1:]))})
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

    def crm_role_members_sql(self) -> str:
        """Rol üyeliği okuması (üye görüntüsünü dolduran asıl CRM sorgusu; sorgu bilgisi aynı metni gösterir)."""
        p = self._crm_prefix()
        return (f"SELECT CAST(r.ParentRootRoleId AS nvarchar(40)) AS RootId, u.DomainName "
                f"FROM {p}SystemUserRoles sur JOIN {p}RoleBase r ON r.RoleId = sur.RoleId "
                f"JOIN {p}SystemUserBase u ON u.SystemUserId = sur.SystemUserId "
                f"WHERE u.IsDisabled = 0 AND u.AccessMode IN (0, 1) AND u.DomainName IS NOT NULL AND u.DomainName <> ''")

    def crm_roles_sql(self) -> str:
        p = self._crm_prefix()
        return f"SELECT CAST(RoleId AS nvarchar(40)) AS RoleId, Name FROM {p}RoleBase WHERE ParentRoleId IS NULL"

    def crm_role_members(self) -> dict[str, set[str]]:
        """Kök rol kimliği (küçük harf) → rolü taşıyan etkin CRM kullanıcılarının hesap adları.
        CRM rolü her iş biriminde bir kopya olarak durur; kişi kopyaya atanır, kopya kök role `ParentRootRoleId` ile bağlıdır."""
        rows = self._crm_rows(self.crm_role_members_sql())
        out: dict[str, set[str]] = {}
        for r in rows:
            acc = _account(r.get("DomainName"))
            rid = str(r.get("RootId") or "").strip("{}").lower()
            if acc and rid:
                out.setdefault(rid, set()).add(acc)
        return out

    def list_crm_roles(self) -> list[dict[str, Any]]:
        def read() -> list[dict[str, Any]]:
            rows = self._crm_rows(self.crm_roles_sql())
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

    def members_of(self, t: str, subject: str) -> list[dict[str, Any]]:
        """Bağın bugünkü etkin üyeleri, kişi listesindeki ad ve birimleriyle — üye görüntüsünü dolduran okumanın
        aynısı (grupta iç içe gruplar, birimde alt birimler dahil). AD'de etkin olmayan CRM kullanıcısı hesap
        adıyla gelir."""
        subject = (subject or "").strip()
        if not subject:
            raise AccessError("Bağ seçilmedi.")
        if t == "ad_group":
            accs = self.group_members(subject)
        elif t == "ou":
            accs = self.ou_members(subject)
        elif t == "crm_role":
            accs = self.crm_role_members().get(subject.strip("{}").lower(), set())
        elif t == "user":
            accs = {subject.lower()}
        else:
            raise AccessError("Bilinmeyen bağ türü.")
        people = {p["subject"]: p for p in self.list_people()}
        out = [people.get(a) or {"subject": a, "label": a, "hint": a, "detail": "AD'de etkin hesabı yok"}
               for a in accs if a]
        return sorted(out, key=lambda x: x["label"].lower())

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


def _dn_parts(dn: str) -> list[str]:
    """DN'i bileşenlerine böler; kaçışlı virgül (`CN=Yılmaz\\, Ali`) bileşeni bölmez."""
    parts, cur, esc = [], [], False
    for ch in dn:
        if esc:
            cur.append(ch)
            esc = False
        elif ch == "\\":
            cur.append(ch)
            esc = True
        elif ch == ",":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur or parts:
        parts.append("".join(cur))
    return parts


def ou_subtree_counts(person_dns: Any) -> dict[str, int]:
    """OU DN → altındaki (alt birimler dahil) kişi sayısı. Kişinin bütün üst OU'ları sayılır."""
    counts: dict[str, int] = {}
    for dn in person_dns:
        parts = _dn_parts(dn)
        for i in range(1, len(parts)):
            if parts[i].strip().upper().startswith("OU="):
                ou = ",".join(parts[i:])
                counts[ou] = counts.get(ou, 0) + 1
    return counts


def nested_group_counts(group_members: dict[str, list[str]], person_dns: set[str]) -> dict[str, int]:
    """Grup DN (küçük harf) → iç içe gruplar dahil etkin kişi sayısı. `group_members`: grup DN → `member`
    değerleri; `person_dns`: etkin kişilerin DN'leri. Döngülü grup yapısı sonsuz dönmez."""
    groups = {g.lower(): [m.lower() for m in ms] for g, ms in group_members.items()}
    people = {p.lower() for p in person_dns}
    out: dict[str, int] = {}
    for g in groups:
        seen_g, found, stack = {g}, set(), [g]
        while stack:
            for m in groups.get(stack.pop(), ()):
                if m in people:
                    found.add(m)
                elif m in groups and m not in seen_g:
                    seen_g.add(m)
                    stack.append(m)
        out[g] = len(found)
    return out


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
