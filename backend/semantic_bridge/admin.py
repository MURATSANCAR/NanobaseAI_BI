"""Yönetim: sistem ayarları, herkesin tanımları ve değişiklik kaydı.

Ayar önceliği: yönetim ekranında kaydedilen değer > servis ortam dosyası (`/etc/nanobase/semantic-bridge.env`)
> varsayılan. Böylece SMTP gibi ayarlar sunucuya girmeden ekrandan verilir; ekrandan silinen ayar ortam
dosyasındaki değere döner. Gizli değerler (parola) hiçbir uçtan geri dönmez, kayıtta da yalnız "değişti" yazar.

Değişiklik kaydı (`semantic_audit`) kim, ne zaman, neyi oluşturdu/güncelledi/sildi/çalıştırdı sorusunun
cevabıdır. Kayıt yazılamazsa asıl işlem durmaz; kayıt bir yan üründür, kapı değil.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import smtplib
import ssl
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Optional

import sqlalchemy as sa

log = logging.getLogger(__name__)

_md = sa.MetaData()

SETTINGS = sa.Table(
    "semantic_settings", _md,
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

AUDIT = sa.Table(
    "semantic_audit", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
    sa.Column("actor", sa.String(120), nullable=False, index=True),
    sa.Column("action", sa.String(16), nullable=False),
    sa.Column("kind", sa.String(24), nullable=False, index=True),
    sa.Column("object_id", sa.String(120)),
    sa.Column("title", sa.String(300)),
    sa.Column("detail", sa.Text),
)

#: Yönetici AD grubunun üyelerinin kalıcı anlık görüntüsü. Yetki kontrolü (is_admin) bunu okur;
#: canlı AD her istekte okunmaz. 15 dk'lık timer `refresh_admin_group` ile tazelenir.
GROUP_CACHE = sa.Table(
    "semantic_admin_group", _md,
    sa.Column("group_name", sa.String(200), primary_key=True),
    sa.Column("members", sa.Text, nullable=False),   # JSON: küçük harf sAMAccountName listesi
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("error", sa.Text),                      # son tazeleme hatası (varsa); üyeler korunur
)

#: Ekrandan yönetilen ayarlar. `env` servis dosyasındaki adıdır; ekran değeri yoksa oradan okunur.
SPEC: list[dict[str, Any]] = [
    # E-posta
    {"key": "ALERT_SMTP_HOST", "group": "email", "label": "SMTP sunucusu", "type": "text", "default": "",
     "help": "Örn. smtp.office365.com ya da mail.timas.com.tr"},
    {"key": "ALERT_SMTP_PORT", "group": "email", "label": "Port", "type": "int", "default": "587",
     "help": "587 (STARTTLS) ya da 465 (SSL)"},
    {"key": "ALERT_SMTP_USER", "group": "email", "label": "Kullanıcı adı", "type": "text", "default": "",
     "help": "Gönderici hesabın oturum adı; sunucu kimlik istemiyorsa boş"},
    {"key": "ALERT_SMTP_PASSWORD", "group": "email", "label": "Parola", "type": "secret", "default": "",
     "help": "Kaydedilen parola ekranda bir daha gösterilmez"},
    {"key": "ALERT_SMTP_FROM", "group": "email", "label": "Gönderen adresi", "type": "email", "default": "",
     "help": "Boşsa kullanıcı adı kullanılır"},
    {"key": "ALERT_SMTP_SSL", "group": "email", "label": "Doğrudan SSL (465)", "type": "bool", "default": "0", "help": ""},
    {"key": "ALERT_SMTP_STARTTLS", "group": "email", "label": "STARTTLS", "type": "bool", "default": "1",
     "help": "SSL kapalıyken bağlantıyı şifreler"},
    {"key": "ALERT_RECIPIENT_DOMAINS", "group": "email", "label": "İzinli alıcı alan adları", "type": "text", "default": "",
     "help": "Virgülle, örn. timas.com.tr. Boşsa her adrese gönderilir"},
    # Bildirim ve raporlar
    {"key": "ALERT_LINK", "group": "delivery", "label": "E-postadaki bağlantı", "type": "text",
     "default": "", "help": "Uyarı ve rapor e-postalarının sonuna eklenen adres"},
    {"key": "ALERT_REMIND_HOURS", "group": "delivery", "label": "Uyarı hatırlatma (saat)", "type": "int", "default": "24",
     "help": "Eşik aşılmaya devam ederse kaç saat sonra yeniden bildirilir"},
    {"key": "REPORT_KEEP_FILES", "group": "delivery", "label": "Rapor başına saklanan dosya", "type": "int", "default": "10",
     "help": "Eski dosyalar bu sayıdan sonra silinir"},
    # Toplantı odaları
    {"key": "ROOM_DAY_START", "group": "rooms", "label": "Takvim başlangıcı", "type": "time", "default": "08:00",
     "help": "Oda takviminin ilk saati, SS:DD"},
    {"key": "ROOM_DAY_END", "group": "rooms", "label": "Takvim bitişi", "type": "time", "default": "20:00",
     "help": "Oda takviminin son saati, SS:DD (24:00 gece yarısı)"},
    {"key": "ROOM_SLOT_MINUTES", "group": "rooms", "label": "Saat adımı (dakika)", "type": "int", "default": "30",
     "help": "Takvimdeki en küçük aralık: 15, 30 ya da 60"},
    # Active Directory (giriş). Değerler giriş servisinin dosyasında tutulur (`file`), veritabanında değil;
    # timas-login her girişte dosyayı yeniden okur, kaydedilen değer hemen geçerli olur.
    {"key": "AD_HOST", "group": "directory", "label": "Etki alanı denetleyicisi", "type": "text", "default": "",
     "help": "Sunucu adı ya da IP, örn. 192.168.0.20", "file": "host"},
    {"key": "AD_PORT", "group": "directory", "label": "Port", "type": "int", "default": "389",
     "help": "389 (LDAP, NTLM ile)", "file": "port"},
    {"key": "AD_NETBIOS", "group": "directory", "label": "NetBIOS alan adı", "type": "text", "default": "",
     "help": "Örn. TIMAS; giriş TIMAS\\kullanici biçiminde yapılır", "file": "netbios"},
    {"key": "AD_DNS_DOMAIN", "group": "directory", "label": "DNS alan adı", "type": "text", "default": "",
     "help": "Örn. timas.local; kullanici@timas.local biçimi de kabul edilir", "file": "dns_domain"},
    {"key": "AD_BASE_DN", "group": "directory", "label": "Arama kökü (Base DN)", "type": "text", "default": "",
     "help": "Örn. DC=timas,DC=local", "file": "base_dn"},
    {"key": "AD_BIND_USER", "group": "directory", "label": "Servis hesabı", "type": "text", "default": "",
     "help": "Kullanıcıları arayan hesap, alan adı olmadan", "file": "bind_user"},
    {"key": "AD_BIND_PASSWORD", "group": "directory", "label": "Servis hesabı parolası", "type": "secret", "default": "",
     "help": "Kaydedilen parola ekranda bir daha gösterilmez", "file": "bind_password"},
    # Logo veritabanı. Değerler köprünün bağlantı dosyasında (`SEMANTIC_CONNECTION_FILE`) tutulur;
    # kaydedilince bağlantı yeniden kurulur, servis yeniden başlatılmaz.
    {"key": "DB_HOST", "group": "database", "label": "Sunucu", "type": "text", "default": "",
     "help": "SQL Server adresi. Tünelle bağlanılıyorsa 127.0.0.1", "file": "host", "store": "db"},
    {"key": "DB_PORT", "group": "database", "label": "Port", "type": "int", "default": "1433",
     "help": "Doğrudan 1433; bu kurulumda socat tüneli 14330", "file": "port", "store": "db"},
    {"key": "DB_NAME", "group": "database", "label": "Veritabanı", "type": "text", "default": "",
     "help": "Logo veritabanı, örn. LOGO_DB", "file": "database", "store": "db"},
    {"key": "DB_USER", "group": "database", "label": "Kullanıcı", "type": "text", "default": "",
     "help": "Salt okunur hesap. Etki alanı hesabı ise ALAN\\kullanici", "file": "user", "store": "db"},
    {"key": "DB_PASSWORD", "group": "database", "label": "Parola", "type": "secret", "default": "",
     "help": "Kaydedilen parola ekranda bir daha gösterilmez", "file": "password", "store": "db"},
    {"key": "DB_DRIVER", "group": "database", "label": "ODBC sürücüsü", "type": "text", "default": "FreeTDS",
     "help": "Sunucuda kayıtlı sürücü adı (odbcinst -q -d)", "file": "driver", "store": "db"},
    {"key": "DB_TDS_VERSION", "group": "database", "label": "TDS sürümü", "type": "text", "default": "7.4",
     "help": "FreeTDS için; SQL Server 2012+ ile 7.4", "file": "tds_version", "store": "db"},
    # CRM: artık ayrı bir sunucu (.28 prod). Tabloları şemalarında veritabanı adını taşır
    # (Timas_MSCRM.dbo); katalog bu adla tutar, köprü _conn_for ile .28 connectorune yönlendirir.
    {"key": "CRM_SCHEMA", "group": "crm", "label": "CRM şeması", "type": "text", "default": "Timas_MSCRM.dbo",
     "help": "veritabanı.şema biçiminde, örn. Timas_MSCRM.dbo. Boşsa CRM okunmaz"},
    # Kişi rehberi
    {"key": "PEOPLE_MAX_IDLE_DAYS", "group": "people", "label": "Son giriş süresi (gün)", "type": "int", "default": "365",
     "help": "Rehbere yalnız bu kadar gün içinde etki alanına giriş yapmış kişiler girer; ortak ve kullanılmayan "
             "hesaplar böyle ayrılır. 0: süreye bakılmaz"},
    # Yapay zekâ modeli
    {"key": "OPENAI_API_BASE", "group": "llm", "label": "Model adresi", "type": "text",
     "default": "https://integrate.api.nvidia.com/v1",
     "help": "OpenAI uyumlu uç, sonunda /v1"},
    {"key": "LLM_MODEL_NAME", "group": "llm", "label": "Model", "type": "text",
     "default": "deepseek-ai/deepseek-v4-flash-0731", "help": "Sağlayıcının model adı"},
    {"key": "OPENAI_API_KEY", "group": "llm", "label": "API anahtarı", "type": "secret", "default": "",
     "help": "Kaydedilen anahtar ekranda bir daha gösterilmez"},
    {"key": "LLM_TIMEOUT_SEC", "group": "llm", "label": "Zaman aşımı (sn)", "type": "int", "default": "240",
     "help": "Bir soru için modelin cevabı beklenecek en uzun süre"},
    # Yetki
    {"key": "TIMAS_ADMIN_USERS", "group": "access", "label": "Yöneticiler", "type": "users",
     "default": "zekiai,timasai,muratsancar",
     "help": "AD hesap adları, virgülle. Bu ekranı bunlar açar. zekiai her zaman yönetici AD grubunda; "
             "burada da tutulur ki AD bir an okunamasa bile yetkisi düşmesin"},
    {"key": "TIMAS_ADMIN_GROUP", "group": "access", "label": "Yönetici AD grubu", "type": "text",
     "default": "Administrators",
     "help": "Bu Active Directory grubunun üyeleri de yönetici sayılır (iç içe gruplar dahil). "
             "Boş bırakılırsa yalnız yukarıdaki liste geçerli olur"},
]
_BY_KEY = {s["key"]: s for s in SPEC}
GROUPS = [
    {"id": "email", "label": "E-posta (SMTP)", "help": "Uyarı ve planlı rapor e-postaları bu hesapla gider."},
    {"id": "delivery", "label": "Bildirim ve raporlar", "help": "Gönderim davranışı."},
    {"id": "rooms", "label": "Toplantı odaları", "help": "Rezervasyon takviminin saatleri."},
    {"id": "directory", "label": "Active Directory (giriş)",
     "help": "Portal girişi bu dizinle doğrulanır. Kaydedilen değer giriş servisinin dosyasına yazılır ve hemen geçerli olur."},
    {"id": "database", "label": "Logo veritabanı (SQL Server)",
     "help": "Soruların cevabı bu bağlantıdan okunur. Kaydedilen değer bağlantı dosyasına yazılır ve bağlantı yeniden kurulur."},
    {"id": "crm", "label": "CRM (Dynamics)", "help": "CRM prod sunucusu 192.168.0.28 (CRMDATBASE); kendi bağlantısıyla okunur."},
    {"id": "people", "label": "Kişi rehberi",
     "help": "Rehber CRM'deki etkin kullanıcılardan gelir, Active Directory ile kesiştirilir: AD'de devre dışı olanlar ve "
             "süre içinde giriş yapmamış hesaplar girmez."},
    {"id": "llm", "label": "Yapay zekâ modeli (LLM)",
     "help": "Soruyu SQL'e çeviren model. Kaydedilen değer hemen geçerli olur, servis yeniden başlatılmaz."},
    {"id": "access", "label": "Yetki",
     "help": "Yönetim ekranına kimlerin gireceği: aşağıdaki liste ya da seçilen AD grubunun üyeleri."},
]
#: Dosyada tutulan ayarlar: anahtar → (dosya, dosyadaki alan adı). Veritabanı yerine dosya, çünkü
#: bu değerleri okuyan başka bir süreç var (giriş servisi, bağlantıyı kuran sürücü).
_FILE_KEYS = {s["key"]: (s.get("store", "ad"), s["file"]) for s in SPEC if s.get("file")}
#: Giriş servisiyle aynı dosya (scripts/server/portal-login/server.py → AD_CONFIG_FILE).
AD_FILE = os.environ.get("AD_CONFIG_FILE", "/etc/nanobase/timas-ad.json")
#: Köprünün veritabanı bağlantı dosyası (SemanticSettings.connection_file ile aynı).
DB_FILE = os.environ.get("SEMANTIC_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/logo-mssql-connection.json")


def _store_path(store: str) -> str:
    return AD_FILE if store == "ad" else DB_FILE


def store_keys(store: str) -> list[str]:
    """O dosyada tutulan ayar anahtarları."""
    return [k for k, (s, _) in _FILE_KEYS.items() if s == store]


#: Ayarı kaydedilince neyin yeniden kurulacağı; köprü (app.py) bu listelere bakar.
LLM_KEYS = ("OPENAI_API_BASE", "LLM_MODEL_NAME", "OPENAI_API_KEY", "LLM_TIMEOUT_SEC")
#: Modelin ürün içindeki adı. Hangi sağlayıcının hangi modeli olduğu bir kurulum ayrıntısıdır ve
#: yerine başkası konabilir; ekranda ürünün kendi adı yazar (sohbetteki "Zeki AI" kimliğiyle aynı
#: kural). Teknik ad, düzeltilecek yerde — «Model» ayarının kendisinde — duruyor.
LLM_DISPLAY = os.environ.get("LLM_DISPLAY_NAME", "ZEKİ AI")

KIND_LABEL = {"report": "Planlı rapor", "alert": "Uyarı", "board": "Pano kartı", "setting": "Ayar",
              "term": "Sözlük terimi", "annotation": "Kolon açıklaması", "session": "Oturum",
              "room": "Toplantı odası", "booking": "Oda rezervasyonu"}

_ready: set[int] = set()
_lock = threading.Lock()
_engine: Optional[sa.engine.Engine] = None
_cache: dict[str, Any] = {"at": 0.0, "values": {}}
_TTL = 5.0


class AdminError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek düz Türkçe hata."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def ensure(engine: sa.engine.Engine) -> None:
    """Tabloları kurar ve ayar okuyucusunu bu veritabanına bağlar."""
    global _engine
    with _lock:
        if id(engine) not in _ready:
            _md.create_all(engine, checkfirst=True)
            _ready.add(id(engine))
        _engine = engine


# ------------------------------------------------------------------ ayarlar


def _stored() -> dict[str, str]:
    if _engine is None:
        return {}
    if time.monotonic() - _cache["at"] < _TTL:
        return _cache["values"]
    try:
        with _engine.connect() as c:
            rows = c.execute(sa.select(SETTINGS.c.key, SETTINGS.c.value)).all()
        _cache.update(at=time.monotonic(), values={k: v for k, v in rows})
    except Exception as e:  # noqa: BLE001
        log.warning("admin: ayarlar okunamadı, ortam değerleri kullanılıyor: %s", e)
        return {}
    return _cache["values"]


def _file(store: str) -> dict[str, Any]:
    try:
        with open(_store_path(store), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _file_write(store: str, values: dict[str, Any]) -> None:
    """Dosyayı yanına yazıp adını değiştirir: okuyan yarım dosya görmesin.

    Sahibi ve izni korunmak zorunda: giriş ayarı root'a ait ve giriş servisinin grubuna okunur.
    Yeni dosyayı aynı sahiple yazamıyorsak (chown yalnız root'un işi) ad değiştirmek, dosyayı
    okuyan servisin erişimini elinden alır — giriş çalışmaz olur. O durumda dosyanın kendisine,
    aynı düğüme yazılır: sahip, grup ve izin olduğu gibi kalır.
    """
    path = _store_path(store)
    body = json.dumps(values, ensure_ascii=False, indent=2) + "\n"
    tmp = f"{path}.tmp"
    st = None
    try:
        st = os.stat(path)
    except OSError:
        pass
    if st is not None and (st.st_uid != os.geteuid() or st.st_gid not in os.getgroups()):
        with open(path, "r+", encoding="utf-8") as f:
            f.write(body)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
        return
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(body)
    if st is not None:
        os.chmod(tmp, st.st_mode & 0o777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except OSError:
            pass
    else:
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _ad_file() -> dict[str, Any]:
    return _file("ad")


def conf(key: str, default: str = "") -> str:
    """Ayarın geçerli değeri: ekran > ortam > varsayılan. Dosyada tutulanlar yalnız kendi dosyasından."""
    if key in _FILE_KEYS:
        store, field = _FILE_KEYS[key]
        v = _file(store).get(field)
        if v is None or v == "":
            spec = _BY_KEY[key]
            return spec["default"] if default == "" else default
        return str(v)
    stored = _stored()
    if key in stored:
        return stored[key]
    if key in os.environ:
        return os.environ[key]
    spec = _BY_KEY.get(key)
    return spec["default"] if spec and default == "" else default


def admins() -> list[str]:
    return [u.strip().lower() for u in conf("TIMAS_ADMIN_USERS").split(",") if u.strip()]


#: DB'deki grup anlık görüntüsünü her is_admin çağrısında sorgulamamak için kısa bellek önbelleği.
#: Bu AD'yi DEĞİL, yalnız DB kaydını önbelleğe alır; canlı AD okuması 15 dk'lık timer'da yapılır.
_grp_mem: dict[str, Any] = {"at": 0.0, "group": "", "members": frozenset()}
_GRP_MEM_TTL = 30.0


def admin_group_members() -> frozenset[str]:
    """Yönetici AD grubunun (iç içe dahil) üyeleri — DB'deki en son anlık görüntüden okunur.
    Canlı AD burada OKUNMAZ; görüntüyü `refresh_admin_group` (15 dk'lık timer) tazeler. Grup adı
    boşsa ya da görüntü yoksa boş küme döner; o zaman yalnız `TIMAS_ADMIN_USERS` listesi geçerlidir.
    """
    group = conf("TIMAS_ADMIN_GROUP").strip().lower()
    now = time.time()
    if _grp_mem["group"] == group and now - _grp_mem["at"] < _GRP_MEM_TTL:
        return _grp_mem["members"]  # type: ignore[return-value]
    members = _load_group_snapshot(group)
    _grp_mem.update(at=now, group=group, members=members)
    return members


def _load_group_snapshot(group_lower: str) -> frozenset[str]:
    if not group_lower or _engine is None:
        return frozenset()
    try:
        with _engine.connect() as c:
            row = c.execute(sa.select(GROUP_CACHE.c.members)
                            .where(sa.func.lower(GROUP_CACHE.c.group_name) == group_lower)).first()
        if not row:
            return frozenset()
        data = json.loads(row[0]) or []
        return frozenset(str(x).strip().lower() for x in data if str(x).strip())
    except Exception as e:  # noqa: BLE001
        log.warning("admin: grup anlık görüntüsü okunamadı: %s", e)
        return frozenset()


def group_snapshot() -> dict[str, Any]:
    """Ekranda göstermek için: kayıtlı üyeler, en son tazeleme zamanı ve varsa hata."""
    group = conf("TIMAS_ADMIN_GROUP").strip()
    out: dict[str, Any] = {"group": group, "members": [], "updatedAt": None, "error": None, "count": 0}
    if not group or _engine is None:
        return out
    try:
        with _engine.connect() as c:
            row = c.execute(sa.select(GROUP_CACHE.c.members, GROUP_CACHE.c.updated_at, GROUP_CACHE.c.error)
                            .where(sa.func.lower(GROUP_CACHE.c.group_name) == group.lower())).first()
        if row:
            members = sorted(str(x).strip().lower() for x in (json.loads(row[0]) or []) if str(x).strip())
            out.update(members=members, count=len(members), updatedAt=_iso(row[1]), error=row[2])
    except Exception as e:  # noqa: BLE001
        out["error"] = f"görüntü okunamadı: {e}"[:400]
    return out


def refresh_admin_group(engine: Optional[sa.engine.Engine] = None) -> dict[str, Any]:
    """Yönetici AD grubunu canlı okuyup DB'ye yazar. 15 dk'lık timer bunu çağırır (istek yolunda değil).
    Tazeleme başarısız olursa eldeki üye görüntüsü SİLİNMEZ; yalnız hata kaydedilir ki yetki düşmesin."""
    eng = engine or _engine
    group = conf("TIMAS_ADMIN_GROUP").strip()
    if eng is None:
        return {"ok": False, "error": "veritabanı bağlı değil"}
    ensure(eng)
    if not group:
        return {"ok": True, "group": "", "count": 0, "note": "grup tanımlı değil"}
    cfg = {k: conf(k) for k in store_keys("ad")}
    missing = [k for k in ("AD_HOST", "AD_NETBIOS", "AD_BASE_DN", "AD_BIND_USER", "AD_BIND_PASSWORD") if not cfg.get(k)]
    if missing:
        return {"ok": False, "group": group, "error": "AD ayarı eksik: " + ", ".join(missing)}
    now = _now()
    try:
        members = sorted(_read_group_members(cfg, group))
    except Exception as e:  # noqa: BLE001
        log.warning("admin: yönetici grubu tazelenemedi, eski görüntü korunuyor: %s", e)
        try:
            with eng.begin() as c:
                c.execute(GROUP_CACHE.update().where(GROUP_CACHE.c.group_name == group)
                          .values(updated_at=now, error=f"{type(e).__name__}: {e}"[:400]))
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "group": group, "error": f"{type(e).__name__}: {e}"[:400]}
    body = json.dumps(members, ensure_ascii=False)
    with eng.begin() as c:
        c.execute(GROUP_CACHE.delete().where(GROUP_CACHE.c.group_name == group))
        c.execute(GROUP_CACHE.insert().values(group_name=group, members=body, updated_at=now, error=None))
    _grp_mem.update(at=0.0)   # bellek önbelleğini geçersiz kıl: sonraki okuma yeni görüntüyü alsın
    log.info("admin: yönetici grubu tazelendi (%s): %d üye", group, len(members))
    return {"ok": True, "group": group, "count": len(members), "at": _iso(now), "members": members}


def _read_group_members(cfg: dict[str, str], group: str) -> frozenset[str]:
    from ldap3 import NONE, NTLM, SUBTREE, Connection, Server  # type: ignore[import-not-found]

    _ensure_md4()
    server = Server(cfg["AD_HOST"], port=int(cfg.get("AD_PORT") or 389), get_info=NONE, connect_timeout=5)
    conn = Connection(server, user=f'{cfg["AD_NETBIOS"]}\\{cfg["AD_BIND_USER"]}', password=cfg["AD_BIND_PASSWORD"],
                      authentication=NTLM, receive_timeout=15)
    if not conn.bind():
        raise RuntimeError(f"servis hesabı reddedildi: {conn.result.get('description')}")
    try:
        if group.lower().startswith(("cn=", "ou=")) and "dc=" in group.lower():
            group_dn = group                       # tam DN girilmişse doğrudan kullan
        else:
            esc = _ldap_escape(group)
            conn.search(cfg["AD_BASE_DN"], f"(&(objectClass=group)(|(sAMAccountName={esc})(cn={esc})))",
                        SUBTREE, attributes=["distinguishedName"], size_limit=2)
            if not conn.entries:
                raise RuntimeError(f"«{group}» grubu bulunamadı")
            group_dn = conn.entries[0].entry_dn
        # 1.2.840.113556.1.4.1941 = LDAP_MATCHING_RULE_IN_CHAIN: iç içe grupların üyeleri de gelir.
        # userAccountControl bit 2 (ACCOUNTDISABLE) olanlar dışlanır.
        flt = (f"(&(objectCategory=person)(objectClass=user)"
               f"(memberOf:1.2.840.113556.1.4.1941:={_ldap_escape(group_dn)})"
               f"(!(userAccountControl:1.2.840.113556.1.4.803:=2)))")
        found = conn.extend.standard.paged_search(cfg["AD_BASE_DN"], flt, SUBTREE,
                                                  attributes=["sAMAccountName"], paged_size=500, generator=True)
        out = set()
        for e in found:
            if e.get("type") != "searchResEntry":
                continue
            # Ham öznitelik değeri liste gelir (['ahmetbozkurt']); ilk elemanı al.
            v = (e.get("attributes") or {}).get("sAMAccountName")
            if isinstance(v, (list, tuple)):
                v = v[0] if v else ""
            out.add(str(v or "").strip().lower())
        return frozenset(a for a in out if a)
    finally:
        conn.unbind()


def _ldap_escape(v: str) -> str:
    """RFC 4515 filtre kaçışı: girilen grup adı filtreyi bozmasın."""
    return v.replace("\\", "\\5c").replace("*", "\\2a").replace("(", "\\28").replace(")", "\\29").replace("\x00", "\\00")


def is_admin(user: Optional[str]) -> bool:
    if not user:
        return False
    u = user.strip().lower()
    if u in admins():
        return True
    return u in admin_group_members()


def _validate(spec: dict[str, Any], raw: Any) -> str:
    t = spec["type"]
    v = "" if raw is None else str(raw).strip()
    if t == "bool":
        return "1" if v in ("1", "true", "True", "on", "evet") else "0"
    if t == "int":
        try:
            n = int(v)
        except ValueError:
            raise AdminError(f"«{spec['label']}» bir tam sayı olmalı.") from None
        if n < 0:
            raise AdminError(f"«{spec['label']}» eksi olamaz.")
        return str(n)
    if t == "time":
        import re as _re
        m = _re.match(r"^([01]\d|2[0-4]):([0-5]\d)$", v)
        if not m or (m.group(1) == "24" and m.group(2) != "00"):
            raise AdminError(f"«{spec['label']}» SS:DD biçiminde olmalı, örn. 08:30.")
        return v
    if t == "email" and v and ("@" not in v or " " in v):
        raise AdminError(f"«{spec['label']}» geçerli bir e-posta adresi değil.")
    if t == "users":
        users = [u.strip().lower() for u in v.split(",") if u.strip()]
        if not users:
            raise AdminError("En az bir yönetici kalmalı.")
        return ",".join(dict.fromkeys(users))
    if t == "secret":
        return str(raw or "")
    return v


def settings_view() -> dict[str, Any]:
    stored = _stored()
    rows = {}
    if _engine is not None:
        with _engine.connect() as c:
            rows = {r["key"]: r for r in c.execute(sa.select(SETTINGS)).mappings().all()}
    items = []
    for s in SPEC:
        k = s["key"]
        source = "file" if k in _FILE_KEYS else "screen" if k in stored else "env" if k in os.environ else "default"
        value = conf(k)
        item = {k2: s[k2] for k2 in ("key", "group", "label", "type", "help")}
        item.update(source=source, updatedBy=rows[k]["updated_by"] if k in rows else None,
                    updatedAt=_iso(rows[k]["updated_at"]) if k in rows else None)
        if s["type"] == "secret":
            item.update(value=None, hasValue=bool(value))
        else:
            item.update(value=value, hasValue=bool(value))
        items.append(item)
    return {"groups": GROUPS, "items": items}


def save_settings(engine: sa.engine.Engine, actor: str, values: dict[str, Any]) -> dict[str, Any]:
    changed: list[dict[str, Any]] = []
    now = _now()
    clean: dict[str, str] = {}
    for k, raw in values.items():
        spec = _BY_KEY.get(k)
        if not spec:
            raise AdminError(f"Bilinmeyen ayar: {k}")
        # Boş gönderilen parola "değiştirme" demektir; silmek için ayrı uç var.
        if spec["type"] == "secret" and (raw is None or str(raw) == ""):
            continue
        clean[k] = _validate(spec, raw)
    if ("TIMAS_ADMIN_USERS" in clean and actor.lower() not in clean["TIMAS_ADMIN_USERS"].split(",")
            and actor.lower() not in admin_group_members()):
        raise AdminError("Kendinizi yöneticilerden çıkaramazsınız; önce başka bir yönetici bunu yapmalı.")
    for store in ("ad", "db"):
        file_part = {k: v for k, v in clean.items() if _FILE_KEYS.get(k, ("", ""))[0] == store}
        if not file_part:
            continue
        current = _file(store)
        merged = dict(current)
        touched = False
        for k, v in file_part.items():
            field = _FILE_KEYS[k][1]
            old = "" if current.get(field) is None else str(current.get(field))
            if old == v:
                continue
            # Dosyadaki yazımı koru: port bir kurulumda sayı, ötekinde metin yazılmış.
            merged[field] = v if isinstance(current.get(field), str) or _BY_KEY[k]["type"] != "int" else int(v)
            touched = True
            secret = _BY_KEY[k]["type"] == "secret"
            changed.append({"key": k, "label": _BY_KEY[k]["label"],
                            "from": None if secret else old, "to": None if secret else v})
        if touched:
            if store == "db" and not merged.get("datasource"):
                merged["datasource"] = "mssql"
            try:
                _file_write(store, merged)
            except OSError as e:
                raise AdminError(f"Ayar dosyası yazılamadı ({_store_path(store)}): {e}") from e
    with engine.begin() as c:
        for k, v in clean.items():
            if k in _FILE_KEYS:
                continue
            old = conf(k)
            if old == v and k in _stored():
                continue
            c.execute(SETTINGS.delete().where(SETTINGS.c.key == k))
            c.execute(SETTINGS.insert().values(key=k, value=v, updated_by=actor, updated_at=now))
            secret = _BY_KEY[k]["type"] == "secret"
            changed.append({"key": k, "label": _BY_KEY[k]["label"],
                            "from": None if secret else old, "to": None if secret else v})
    _cache["at"] = 0.0
    for ch in changed:
        audit(engine, actor, "update", "setting", ch["key"], ch["label"],
              {"from": ch["from"], "to": ch["to"]} if ch["from"] is not None or ch["to"] is not None else {"secret": True})
    return {"changed": [c["key"] for c in changed], **settings_view()}


def reset_setting(engine: sa.engine.Engine, actor: str, key: str) -> dict[str, Any]:
    spec = _BY_KEY.get(key)
    if not spec:
        raise AdminError(f"Bilinmeyen ayar: {key}")
    if key == "TIMAS_ADMIN_USERS":
        raise AdminError("Yönetici listesi sıfırlanamaz; düzenleyerek değiştirin.")
    if key in _FILE_KEYS:
        raise AdminError("Bu ayar kendi dosyasında tutulur; sunucu değeri yoktur, düzenleyerek değiştirin.")
    with engine.begin() as c:
        n = c.execute(SETTINGS.delete().where(SETTINGS.c.key == key)).rowcount
    _cache["at"] = 0.0
    if n:
        audit(engine, actor, "delete", "setting", key, spec["label"], {"to": "ortam dosyası / varsayılan"})
    return settings_view()


def smtp_test(to: str) -> tuple[bool, str]:
    """Geçerli ayarla bir deneme e-postası gönderir; hata metnini olduğu gibi döndürür."""
    from semantic_bridge import alerts as alerts_mod

    cfg = alerts_mod.smtp_settings()
    if not cfg:
        return False, "SMTP sunucusu ya da gönderen adresi girilmemiş."
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = "ZEKİ deneme e-postası", cfg["sender"], to
    msg.set_content("Bu e-posta ZEKİ yönetim ekranından gönderilen denemedir. Uyarı ve planlı rapor e-postaları bu ayarla gidecek.")
    try:
        ctx = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx) if cfg["ssl"]
                  else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
        with server as s:
            if not cfg["ssl"] and cfg["starttls"]:
                s.starttls(context=ctx)
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        return True, f"{to} adresine gönderildi."
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]


def _ensure_md4() -> None:
    """NTLM MD4 ister; OpenSSL 3 kaldırdı, pycryptodome'da var. Giriş servisindeki şimle aynı."""
    try:
        hashlib.new("md4", b"")
        return
    except ValueError:
        pass
    from Crypto.Hash import MD4  # type: ignore[import-not-found]

    builtin = hashlib.new

    class _Md4:
        def __init__(self, data: bytes = b"") -> None:
            self.h = MD4.new(data)

        def update(self, data: bytes) -> None:
            self.h.update(data)

        def digest(self) -> bytes:
            return self.h.digest()

    hashlib.new = lambda name, data=b"", **kw: _Md4(data) if name.lower() == "md4" else builtin(name, data, **kw)  # type: ignore[assignment]


def directory_test(username: str = "") -> tuple[bool, str]:
    """Servis hesabıyla dizine bağlanır; ad verilmişse o kullanıcıyı da arar. Giriş servisiyle aynı yol: NTLM, düz bağlama yok."""
    cfg = {k: conf(k) for k in store_keys("ad")}
    missing = [_BY_KEY[k]["label"] for k in ("AD_HOST", "AD_NETBIOS", "AD_BASE_DN", "AD_BIND_USER", "AD_BIND_PASSWORD") if not cfg[k]]
    if missing:
        return False, "Eksik: " + ", ".join(missing) + "."
    try:
        from ldap3 import NONE, NTLM, SUBTREE, Connection, Server  # type: ignore[import-not-found]
        from ldap3.core.exceptions import LDAPException  # type: ignore[import-not-found]
        _ensure_md4()
    except ImportError as e:
        return False, f"Sunucuda ldap3 kurulu değil: {e}"
    t0 = time.monotonic()
    try:
        server = Server(cfg["AD_HOST"], port=int(cfg["AD_PORT"] or 389), get_info=NONE, connect_timeout=5)
        conn = Connection(server, user=f'{cfg["AD_NETBIOS"]}\\{cfg["AD_BIND_USER"]}', password=cfg["AD_BIND_PASSWORD"],
                          authentication=NTLM, receive_timeout=10)
        if not conn.bind():
            return False, f"Servis hesabı reddedildi: {conn.result.get('description') or conn.result}"
        try:
            name = "".join(ch for ch in username.strip().split("\\")[-1].split("@")[0] if ch.isalnum() or ch in "._-") or cfg["AD_BIND_USER"]
            conn.search(cfg["AD_BASE_DN"], f"(&(objectClass=user)(sAMAccountName={name}))", SUBTREE,
                        attributes=["sAMAccountName", "displayName", "userAccountControl"], size_limit=2)
            ms = int((time.monotonic() - t0) * 1000)
            if len(conn.entries) != 1:
                return False, f"Bağlantı kuruldu ({ms} ms) ama «{name}» hesabı bulunamadı."
            e = conn.entries[0]
            uac = int(e.userAccountControl.value or 0)
            disabled = bool(uac & 2)
            return (not disabled,
                    f"Bağlandı ({ms} ms). {e.displayName.value or name} ({e.sAMAccountName.value})"
                    + (" — hesap devre dışı." if disabled else " — hesap etkin."))
        finally:
            conn.unbind()
    except LDAPException as e:
        return False, f"{type(e).__name__}: {e}"[:400]
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]


# ------------------------------------------------------------------ bağlantı denemeleri
# Her deneme kaydedilmiş ayarla, gerçek bağlantıyı kurarak yapılır: "ayar dolu mu" diye bakmak
# bağlantının çalıştığını söylemez. Hata metni olduğu gibi döner, çünkü düzeltecek kişi onu okur.


def _thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _test_connector(extra: Optional[dict[str, Any]] = None):
    """Bağlantı dosyasındaki tanımla yeni bir bağlantı. Canlı bağlantıya dokunulmaz: deneme
    yanlış ayarla asılı kalırsa kullanıcının sorusu bundan etkilenmesin."""
    from semantic_layer.profiler.connectors import connector_from_config

    cfg = dict(_file("db"))
    cfg.update(extra or {})
    cfg.setdefault("datasource", "mssql")
    cfg.setdefault("login_timeout", int(os.environ.get("ADMIN_TEST_LOGIN_TIMEOUT", "10")))
    return connector_from_config(cfg), str(cfg.get("datasource", "")).lower()


def _db_missing() -> list[str]:
    return [_BY_KEY[k]["label"] for k in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not conf(k)]


def database_test() -> tuple[bool, str]:
    """Logo veritabanına bağlanır ve hangi veritabanına, hangi hesapla bağlandığını söyler."""
    if missing := _db_missing():
        return False, "Eksik: " + ", ".join(missing) + "."
    t0 = time.monotonic()
    conn = None
    try:
        conn, ds = _test_connector()
        if ds in ("mssql", "sqlserver"):
            sql = ("SELECT DB_NAME() AS db, SUSER_SNAME() AS hesap, "
                   "(SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES) AS tablolar, "
                   "CAST(SERVERPROPERTY('ProductVersion') AS nvarchar(40)) AS surum")
        else:
            sql = "SELECT 1 AS db"
        _, rows, _ = conn.execute(sql, 1)
        ms = int((time.monotonic() - t0) * 1000)
        r = rows[0] if rows else {}
        if "hesap" not in r:
            return True, f"Bağlandı ({ms} ms)."
        return True, (f"Bağlandı ({ms} ms). {r.get('db')} · {r.get('hesap')} · "
                      f"{_thousands(int(r.get('tablolar') or 0))} tablo · sürüm {r.get('surum')}")
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def crm_test() -> tuple[bool, str]:
    """CRM artık ayrı bir sunucuda (.28 prod, CRMDATBASE). Deneme, CRM bağlantısının
    (crm-mssql-connection.json) Timas_MSCRM veritabanını okuyup okuyamadığına bakar."""
    schema = conf("CRM_SCHEMA").strip()
    if not schema:
        return False, "CRM şeması girilmemiş."
    _crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    if not os.path.exists(_crm_file):
        return False, "CRM bağlantı dosyası bulunamadı: " + _crm_file
    db, _, sch = schema.rpartition(".")
    if not db:
        db, sch = "", schema
    for part in (db, sch):
        if part and not all(ch.isalnum() or ch in "_-$" for ch in part):
            return False, f"«{schema}» geçerli bir ad değil; veritabanı.şema bekleniyor."
    t0 = time.monotonic()
    conn = None
    try:
        from semantic_layer.profiler.connectors import connector_from_file
        conn = connector_from_file(_crm_file)
        qual = f"[{db}]." if db else ""
        _, rows, _ = conn.execute(
            f"SELECT COUNT(*) AS tablolar FROM {qual}INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '{sch}'", 1)
        n = int((rows[0].get("tablolar") if rows else 0) or 0)
        ms = int((time.monotonic() - t0) * 1000)
        if not n:
            return False, f"Bağlandı ({ms} ms) ama «{schema}» altında tablo görünmüyor; ad ya da okuma izni yanlış olabilir."
        return True, f"Bağlandı ({ms} ms). {schema} · {_thousands(n)} tablo okunabiliyor."
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def llm_test() -> tuple[bool, str]:
    """Modele tek kelimelik bir soru sorar. Cevabın içeriği değil, geldiği önemli."""
    base, model, key = conf("OPENAI_API_BASE"), conf("LLM_MODEL_NAME"), conf("OPENAI_API_KEY")
    if not base or not model:
        return False, "Model adresi ya da model adı girilmemiş."
    timeout = float(os.environ.get("ADMIN_LLM_TEST_TIMEOUT", "60"))
    t0 = time.monotonic()
    try:
        from semantic_layer.candidates.llm_client import LlmClient

        client = LlmClient(base, model, key, timeout, extra={"chat_template_kwargs": {"enable_thinking": False}})
        out = client.chat([{"role": "user", "content": "Yalnızca TAMAM yaz."}], max_tokens=8)
        ms = int((time.monotonic() - t0) * 1000)
        text = " ".join((out or "").split())[:60]
        if not text:
            return False, f"Model bağlandı ({ms} ms) ama boş cevap verdi."
        return True, f"Cevap geldi ({ms} ms). {LLM_DISPLAY} → «{text}»"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]


def store_test() -> tuple[bool, str]:
    """Ayarların, kayıtların, panoların ve raporların tutulduğu meta veritabanı."""
    if _engine is None:
        return False, "Meta veritabanı bağlantısı kurulmamış."
    t0 = time.monotonic()
    try:
        with _engine.connect() as c:
            n = c.execute(sa.select(sa.func.count()).select_from(SETTINGS)).scalar() or 0
            audits = c.execute(sa.select(sa.func.count()).select_from(AUDIT)).scalar() or 0
        ms = int((time.monotonic() - t0) * 1000)
        return True, f"Bağlandı ({ms} ms). {n} kayıtlı ayar, {_thousands(int(audits))} değişiklik kaydı."
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"[:400]


def email_config_test() -> tuple[bool, str]:
    """E-posta için bağlantı kurmadan bakılabilecek tek şey ayarın tamlığı; gerçek deneme
    bir adrese posta gönderir ve onu kullanıcı ister (`smtp_test`)."""
    from semantic_bridge import alerts as alerts_mod

    cfg = alerts_mod.smtp_settings()
    if not cfg:
        return False, "SMTP sunucusu ya da gönderen adresi girilmemiş."
    return True, f"Ayarlı: {cfg['host']}:{cfg['port']} · gönderen {cfg['sender']}. Gerçek deneme için bir adrese gönderin."


#: Tek tuşla çalışan denemeler. E-posta burada yalnız ayar bütünlüğüne bakar: bir denemenin
#: kimseye posta göndermemesi gerekir.
CHECKS: list[dict[str, Any]] = [
    {"id": "database", "group": "database", "label": "Logo veritabanı", "run": database_test},
    {"id": "crm", "group": "crm", "label": "CRM veritabanı", "run": crm_test},
    {"id": "llm", "group": "llm", "label": "Yapay zekâ modeli", "run": llm_test},
    {"id": "directory", "group": "directory", "label": "Active Directory", "run": lambda: directory_test("")},
    {"id": "email", "group": "email", "label": "E-posta ayarı", "run": email_config_test},
    {"id": "store", "group": None, "label": "Meta veritabanı", "run": store_test},
]
_CHECK_BY_ID = {c["id"]: c for c in CHECKS}


def run_check(check_id: str) -> dict[str, Any]:
    c = _CHECK_BY_ID.get(check_id)
    if not c:
        raise AdminError(f"Bilinmeyen deneme: {check_id}")
    t0 = time.monotonic()
    try:
        ok, message = c["run"]()
    except Exception as e:  # noqa: BLE001
        ok, message = False, f"{type(e).__name__}: {e}"[:400]
    return {"id": c["id"], "group": c["group"], "label": c["label"], "ok": ok, "message": message,
            "ms": int((time.monotonic() - t0) * 1000), "at": _iso(_now())}


def run_checks() -> dict[str, Any]:
    """Hepsi sırayla: tek bağlantı üstünde koşan denemeler birbirini beklesin."""
    items = [run_check(c["id"]) for c in CHECKS]
    return {"items": items, "ok": all(i["ok"] for i in items), "at": _iso(_now())}


def system_info() -> dict[str, Any]:
    """Ekrandan değiştirilmeyen, servisin açılışta okuduğu tanımlar. Görünür olmaları gerekir:
    bir ayarın neden beklendiği gibi davranmadığı çoğu zaman burada yazar."""
    def mask(dsn: str) -> str:
        import re as _re
        return _re.sub(r"//([^:/@]+):[^@]*@", r"//\1:***@", dsn or "")

    return {"items": [
        {"label": "Bağlantı dosyası", "value": DB_FILE},
        {"label": "Giriş servisi dosyası", "value": AD_FILE},
        {"label": "Meta veritabanı", "value": mask(os.environ.get("SEMANTIC_STORE_DSN") or os.environ.get("NANOBASE_META_DSN", ""))},
        {"label": "Katalog kapsamı (şema)", "value": os.environ.get("SEMANTIC_SCHEMA", "dbo")},
        {"label": "Katalog kapsamı (tablo deseni)", "value": os.environ.get("SEMANTIC_TABLE_LIKE", "") or "tümü"},
        {"label": "Bilgi klasörü", "value": os.environ.get("SEMANTIC_KNOWLEDGE_DIR", "")},
        {"label": "Rapor klasörü", "value": os.environ.get("REPORT_DIR", "")},
        {"label": "Servis ortam dosyası", "value": "/etc/nanobase/semantic-bridge.env"},
    ]}


# ------------------------------------------------------------------ değişiklik kaydı


def audit(engine: Optional[sa.engine.Engine], actor: Optional[str], action: str, kind: str,
          object_id: Optional[str], title: Optional[str], detail: Any = None) -> None:
    eng = engine or _engine
    if eng is None:
        return
    try:
        ensure(eng)
        with eng.begin() as c:
            c.execute(AUDIT.insert().values(
                at=_now(), actor=(actor or "sistem")[:120], action=action[:16], kind=kind[:24],
                object_id=(str(object_id)[:120] if object_id else None), title=(str(title)[:300] if title else None),
                detail=json.dumps(detail, ensure_ascii=False, default=str)[:20000] if detail is not None else None))
    except Exception as e:  # noqa: BLE001
        log.warning("admin: değişiklik kaydı yazılamadı (%s %s): %s", action, kind, e)


def audit_list(engine: sa.engine.Engine, *, kind: Optional[str] = None, actor: Optional[str] = None,
               action: Optional[str] = None, q: Optional[str] = None, before: Optional[int] = None,
               limit: int = 100) -> dict[str, Any]:
    stmt = sa.select(AUDIT)
    if kind:
        stmt = stmt.where(AUDIT.c.kind == kind)
    if actor:
        stmt = stmt.where(AUDIT.c.actor == actor)
    if action:
        stmt = stmt.where(AUDIT.c.action == action)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(sa.or_(AUDIT.c.title.ilike(like), AUDIT.c.object_id.ilike(like), AUDIT.c.actor.ilike(like)))
    if before:
        stmt = stmt.where(AUDIT.c.id < before)
    limit = max(1, min(int(limit or 100), 500))
    with engine.connect() as c:
        rows = c.execute(stmt.order_by(AUDIT.c.id.desc()).limit(limit + 1)).mappings().all()
    items = [{
        "id": r["id"], "at": _iso(r["at"]), "actor": r["actor"], "action": r["action"], "kind": r["kind"],
        "kindLabel": KIND_LABEL.get(r["kind"], r["kind"]), "objectId": r["object_id"], "title": r["title"],
        "detail": json.loads(r["detail"]) if r["detail"] else None,
    } for r in rows[:limit]]
    return {"items": items, "next": items[-1]["id"] if len(rows) > limit else None}


def changes(before: dict[str, Any], after: dict[str, Any], keys: list[str]) -> dict[str, Any]:
    """İki kaydın kayda değer alanlarındaki farkı: {alan: {from, to}}."""
    out = {}
    for k in keys:
        if before.get(k) != after.get(k):
            out[k] = {"from": before.get(k), "to": after.get(k)}
    return out


# ------------------------------------------------------------------ herkesin tanımları


def all_reports(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    from semantic_bridge import reports as rm

    rm.ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(rm.REPORTS).where(*rm._scope(tenant, ds, None))
                         .order_by(rm.REPORTS.c.created_at.desc())).mappings().all()
    return [{**rm.to_dict(r), "owner": r["username"]} for r in rows]


def all_cards(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    from semantic_bridge import board as bm

    bm.ensure(engine)
    C = bm.CARDS
    cols = [C.c.id, C.c.username, C.c.title, C.c.question, C.c.chart, C.c.refresh, C.c.refresh_at,
            C.c.created_at, C.c.updated_at, C.c.result_at, C.c.last_auto_at, C.c.last_error]
    with engine.connect() as c:
        rows = c.execute(sa.select(*cols).where(C.c.tenant_id == tenant, C.c.datasource_id == ds)
                         .order_by(C.c.username, C.c.position)).mappings().all()
    return [{"id": r["id"], "owner": r["username"], "title": r["title"], "question": r["question"] or "",
             "chart": r["chart"], "refresh": r["refresh"], "refreshAt": r["refresh_at"],
             "createdAt": _iso(r["created_at"]), "updatedAt": _iso(r["updated_at"]),
             "resultAt": _iso(r["result_at"]), "lastAutoAt": _iso(r["last_auto_at"]), "lastError": r["last_error"]}
            for r in rows]


def delete_card(engine: sa.engine.Engine, tenant: str, ds: str, card_id: str) -> Optional[dict[str, Any]]:
    from semantic_bridge import board as bm

    C = bm.CARDS
    with engine.begin() as c:
        row = c.execute(sa.select(C.c.id, C.c.username, C.c.title).where(
            C.c.id == card_id, C.c.tenant_id == tenant, C.c.datasource_id == ds)).mappings().first()
        if not row:
            return None
        c.execute(C.delete().where(C.c.id == card_id))
    return dict(row)


def users(engine: sa.engine.Engine, tenant: str, ds: str) -> list[dict[str, Any]]:
    """Sistemi kullanan kişiler: tanımı ya da kaydı olan her hesap, son hareketiyle."""
    from semantic_bridge import board as bm
    from semantic_bridge import reports as rm

    people: dict[str, dict[str, Any]] = {}

    def person(u: str) -> dict[str, Any]:
        key = (u or "").lower()
        return people.setdefault(key, {"username": u, "cards": 0, "reports": 0, "actions": 0, "lastSeen": None,
                                       "admin": is_admin(u)})

    def seen(p: dict[str, Any], at: Optional[datetime]) -> None:
        s = _iso(at)
        if s and (p["lastSeen"] is None or s > p["lastSeen"]):
            p["lastSeen"] = s

    with engine.connect() as c:
        for u, n, last in c.execute(sa.select(bm.CARDS.c.username, sa.func.count(), sa.func.max(bm.CARDS.c.updated_at))
                                    .where(bm.CARDS.c.tenant_id == tenant, bm.CARDS.c.datasource_id == ds)
                                    .group_by(bm.CARDS.c.username)).all():
            p = person(u); p["cards"] = n; seen(p, last)
        for u, n, last in c.execute(sa.select(rm.REPORTS.c.username, sa.func.count(), sa.func.max(rm.REPORTS.c.updated_at))
                                    .where(*rm._scope(tenant, ds, None)).group_by(rm.REPORTS.c.username)).all():
            p = person(u); p["reports"] = n; seen(p, last)
        for u, n, last in c.execute(sa.select(AUDIT.c.actor, sa.func.count(), sa.func.max(AUDIT.c.at))
                                    .where(AUDIT.c.actor != "sistem").group_by(AUDIT.c.actor)).all():
            p = person(u); p["actions"] = n; seen(p, last)
    for a in admins():
        person(a)["admin"] = True
    return sorted(people.values(), key=lambda p: (p["lastSeen"] or ""), reverse=True)


# ------------------------------------------------------------------ sistem durumu


def _unit(name: str) -> dict[str, Any]:
    """systemd birimini okur (yetki gerektirmez). systemctl yoksa bilinmiyor döner."""
    import subprocess

    props = "ActiveState,SubState,LastTriggerUSec,NextElapseUSecRealtime,Result"
    try:
        out = subprocess.run(["systemctl", "show", name, "-p", props], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return {"unit": name, "state": "unknown"}
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return {"unit": name, "state": kv.get("ActiveState") or "unknown", "sub": kv.get("SubState"),
            "last": kv.get("LastTriggerUSec") or None, "next": kv.get("NextElapseUSecRealtime") or None,
            "result": kv.get("Result")}


TIMERS = [
    {"unit": "timas-alerts.timer", "label": "Uyarı kontrolü", "every": "15 dk"},
    {"unit": "timas-reports.timer", "label": "Planlı raporlar", "every": "5 dk"},
    {"unit": "timas-board.timer", "label": "Pano kartı tazeleme", "every": "15 dk"},
    {"unit": "nanobase-semantic-worker.timer", "label": "Gece katalog taraması", "every": "gece"},
    {"unit": "nanobase-semantic-watchdog.timer", "label": "Köprü sağlık denetimi", "every": "5 dk"},
]
SERVICES = [
    {"unit": "nanobase-semantic-bridge.service", "label": "Sorgu motoru (köprü)"},
    {"unit": "timas-login.service", "label": "Giriş servisi (Active Directory)"},
    {"unit": "timas-vpn-mfa.service", "label": "TİMAŞ VPN"},
    {"unit": "timas-mssql-14330.service", "label": "Logo veritabanı tüneli"},
]


_STAMP = r"\w{3} \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S+"


def _timer_times() -> dict[str, tuple[Optional[str], Optional[str]]]:
    """Göreli (OnUnitActiveSec) zamanlayıcılarda `systemctl show` sıradaki anı boş verir; list-timers verir.
    Satır biçimi: NEXT LEFT LAST PASSED UNIT ACTIVATES — sıradaki yoksa satır "-" ile başlar."""
    import re
    import subprocess

    try:
        out = subprocess.run(["systemctl", "list-timers", "--all", "--no-legend", "--no-pager"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return {}
    times: dict[str, tuple[Optional[str], Optional[str]]] = {}
    for line in out.splitlines():
        unit = next((w for w in line.split() if w.endswith(".timer")), None)
        if not unit:
            continue
        stamps = re.findall(_STAMP, line)
        if line.lstrip().startswith("-"):
            times[unit] = (None, stamps[0] if stamps else None)
        else:
            times[unit] = (stamps[0] if stamps else None, stamps[1] if len(stamps) > 1 else None)
    return times


def system_status() -> dict[str, Any]:
    times = _timer_times()
    timers = []
    for t in TIMERS:
        u = {**t, **_unit(t["unit"])}
        nxt, last = times.get(t["unit"], (None, None))
        u["next"] = nxt or u.get("next")
        u["last"] = last or u.get("last")
        timers.append(u)
    return {"services": [{**s, **_unit(s["unit"])} for s in SERVICES], "timers": timers}
