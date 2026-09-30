"""H2 Okuyucu veri tabanı: tekil okur kimliği, izin özeti, belirsiz eşleşme kuyruğu ve okur kartı.

Bu dosya H2'nin **çekirdeğidir**; H3 (e-ticaret müşteri yönetimi) ve M37 (okur topluluğu) yeniden yazmaz, buradan
kullanır. Dışarıya açık işlevler dosyanın sonundaki «Diğer modüller için» bölümündedir:
`register_source`, `SourceRecord`, `resolve_reader`, `consents_of`, `profiles`, `final_consent`; segment motoru
`readers_segments.py`'dedir (`evaluate`, `members`, `summary`).

**Kimlik (K1, deterministik).** Her kaynak kaydı (CRM kişi / aday / Tüketici-Okur firması, etkinlik yüklemesinden
yeni kişi, ileride H3'ün site üyesi) bir düğümdür. Aynı normalize e-posta, aynı normalize cep telefonu, adayın bağlı
olduğu kişi (`ParentContactId`) ve insanın «aynı kişi» kararı iki düğümü birleştirir; bağlı bileşen bir okurdur.
Normalizasyon: e-posta baş/son boşluksuz ve küçük harf, «@» içermeli (kabul SQL'i `LOWER(LTRIM(RTRIM()))` +
`LIKE '%@%'` ile aynı); telefon yalnız rakam, +90/0 önekleri atılır, yalnız 5 ile başlayan 10 haneli (Türkiye cep)
kimlikte kullanılır (santral/iş telefonları yanlış birleştirme yapmasın). Okur kimliği sürümler arası sabittir:
bileşen önceki okurlardan en çok kaydı taşıyanın kimliğini alır, diğerleri «birleşti» olur.

**Kişisel veri saklanmaz.** Portal tablolarında e-posta/telefon/ad yalnız tuzlu HMAC-SHA256 özetidir (tuz sunucu
ortamında `READERS_HASH_SALT`; yoksa okuma yapılmaz). Doğum yılından yalnız yıl, il adı ve seçim listesi etiketleri
tutulur. Ad/e-posta/telefon ekranda açıkça verilen `ozellik:okur.kisisel-veri` ile kaynaktan anlık okunur ve her
görüntüleme değişiklik kaydına düşer.

**İzin (K1, deterministik).** Kanal başına (e-posta, SMS, arama) ve KVKK açık rızası için kanıtlar tutulur:
İYS günlüğünde her (kayıt, entegrasyon alanı) için en son kayıt; CRM izin bayrakları (hangi alanın hangi değerinin
ne anlama geldiği ayardır). Sonuç: herhangi bir kanıt ret ise **ret** (ret her zaman kazanır); yoksa izinli sayılan
kaynaktan (varsayılan yalnız İYS) onay varsa **izinli**; yoksa **bilinmiyor** — İYS durumu bilinmeyen kişi izinli
sayılmaz. CRM bayrağı ileti kanalında yalnız ret üretir.

**Çocuk kayıtları (hukuk sorusu).** Bağlı kayıtlardan birinin doğum yılı yaşı `READERS_MINOR_AGE`'in (18) altına
düşürüyorsa okur «18 yaş altı» işaretlenir; ebeveyn rızası CRM'de ayrı tutulmadığından bu okurlar ayar açılmadıkça
(`READERS_MINOR_EXPORT`, varsayılan kapalı) hiçbir dışa aktarıma girmez. Aynı e-posta/telefonu taşıyan kayıtların
doğum yılları 12+ yıl ayrışıyorsa «ortak iletişim bilgisi» (ebeveyn–çocuk olabilir) işaretlenir.

**Belirsiz eşleşme (K2, insan kararı).** Farklı okurlarda aynı ad özeti + aynı il (+ doğum yılı çelişmiyor) çift
adaydır; puan kural tabanlıdır (model yok — kişisel veri modele gitmez). «Aynı kişi» kararı iki okuru hemen
birleştirir ve sonraki okumalarda da korunur; «farklı» kararı çifti bir daha önermez.

CRM'e yazma yok: portal kendi `semantic_reader_*` tablolarını yazar; CRM'deki kopyalar CRM ekibince elle düzeltilir.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import threading
import unicodedata
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import readers_sources as src

log = logging.getLogger("semantic.readers")
_md = sa.MetaData()


class ReadersError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ tablolar (bi_meta; hepsinde tenant_id)

READERS = sa.Table(
    "semantic_readers", _md,
    sa.Column("reader_id", sa.String(24), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("status", sa.String(10), nullable=False),               # aktif | birlesti | pasif
    sa.Column("merged_into", sa.String(24)),
    sa.Column("email_hash", sa.String(64)),                           # ilk (sıralı) e-posta özeti; tamamı KEYS'te
    sa.Column("phone_hash", sa.String(64)),
    sa.Column("birth_year", sa.Integer),
    sa.Column("city", sa.String(80)),
    sa.Column("gender", sa.String(40)),
    sa.Column("is_minor", sa.Boolean, nullable=False, default=False),
    sa.Column("first_seen", sa.DateTime(timezone=True)),
    sa.Column("last_touch", sa.DateTime(timezone=True)),
    sa.Column("loyalty", sa.String(10)),                              # ilk | duzenli | kayip — sonraki sürüm
    sa.Column("interests_json", sa.Text),                             # [{"ad":…, "kaynak":…}]
    sa.Column("attrs_json", sa.Text),                                 # form tipi, kayıt tipi, katılım kaynağı, UTM…
    sa.Column("sources_json", sa.Text),                               # {"crm_contact": 1, "crm_lead": 2}
    sa.Column("event_count", sa.Integer, nullable=False, default=0),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_semantic_readers_state", "tenant_id", "status"),
)
LINKS = sa.Table(
    "semantic_reader_links", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("source", sa.String(20), primary_key=True),            # crm_contact | crm_lead | crm_account | tsoft_member | upload
    sa.Column("source_id", sa.String(80), primary_key=True),
    sa.Column("reader_id", sa.String(24), nullable=False, index=True),
    sa.Column("name_hash", sa.String(64)),
    sa.Column("match_rule", sa.String(10), nullable=False),          # tek | email | phone | kaynak | manual
    sa.Column("confidence", sa.Float, nullable=False, default=1.0),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True)),              # kaynak kaydın oluşturulma zamanı
    sa.Column("attrs_json", sa.Text),                                 # kaydın kendi etiketleri (kart için)
)
KEYS = sa.Table(
    "semantic_reader_keys", _md,
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("kind", sa.String(1), nullable=False),                 # e (e-posta) | p (telefon)
    sa.Column("hash", sa.String(64), nullable=False),
    sa.Column("reader_id", sa.String(24), nullable=False),
    sa.Column("source", sa.String(20), nullable=False),
    sa.Column("source_id", sa.String(80), nullable=False),
    sa.Index("ix_semantic_reader_keys_hash", "tenant_id", "hash"),
    sa.Index("ix_semantic_reader_keys_reader", "tenant_id", "reader_id"),
)
CANDIDATES = sa.Table(
    "semantic_reader_merge_candidates", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("a_reader", sa.String(24), nullable=False),
    sa.Column("b_reader", sa.String(24), nullable=False),
    sa.Column("features_json", sa.Text),
    sa.Column("score", sa.Float, nullable=False),
    sa.Column("status", sa.String(10), nullable=False),              # bekliyor | ayni | farkli | gecersiz
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("note", sa.String(500)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_semantic_reader_cand_pair", "tenant_id", "a_reader", "b_reader"),
)
CONSENTS = sa.Table(
    "semantic_reader_consents", _md,
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("reader_id", sa.String(24), nullable=False),
    sa.Column("channel", sa.String(8), nullable=False),              # email | sms | call | kvkk
    sa.Column("status", sa.String(10), nullable=False),              # izinli | ret
    sa.Column("source", sa.String(10), nullable=False),              # iys | crm | form | tsoft
    sa.Column("at", sa.DateTime(timezone=True)),
    sa.Column("link_source", sa.String(20)),
    sa.Column("link_id", sa.String(80)),
    sa.Column("detail", sa.String(200)),                              # İYS alanı / CRM bayrağı adı
    sa.Index("ix_semantic_reader_consents_reader", "tenant_id", "reader_id"),
)
EVENTS = sa.Table(
    "semantic_reader_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("reader_id", sa.String(24), nullable=False),
    sa.Column("kind", sa.String(12), nullable=False),                # etkinlik
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("label", sa.String(300)),
    sa.Column("ref", sa.String(64)),                                  # yükleme kimliği
    sa.Index("ix_semantic_reader_events_reader", "tenant_id", "reader_id"),
)
SYNC = sa.Table(
    "semantic_reader_sync", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("source", sa.String(20), primary_key=True),            # crm_contact | crm_lead | … | _tur (tur özeti)
    sa.Column("at", sa.DateTime(timezone=True)),                      # son başarılı okuma
    sa.Column("rows", sa.Integer),
    sa.Column("error", sa.Text),
    sa.Column("error_at", sa.DateTime(timezone=True)),
    sa.Column("stats_json", sa.Text),
)
META = sa.Table(
    "semantic_reader_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(40), primary_key=True),
    sa.Column("value", sa.Text),
)

_lock = threading.Lock()
_ready: set[int] = set()


def ensure(engine: sa.engine.Engine) -> None:
    key = id(engine)
    with _lock:
        if key in _ready:
            return
        from semantic_bridge import readers_segments as seg  # noqa: F401 — segment/yükleme tabloları aynı MetaData'da değil
        from semantic_bridge import readers_imports as imp  # noqa: F401
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        seg.ensure_tables(engine)
        imp.ensure_tables(engine)
        _ready.add(key)


# ------------------------------------------------------------------ ayarlar

CHANNELS = ("email", "sms", "call")
CHANNEL_LABELS = {"email": "E-posta", "sms": "SMS", "call": "Arama", "kvkk": "KVKK açık rıza"}
STATUS_LABELS = {"izinli": "İzinli", "ret": "Ret", "bilinmiyor": "Bilinmiyor"}
SOURCE_LABELS = {"crm_contact": "CRM kişi", "crm_lead": "CRM müşteri adayı", "crm_account": "CRM okur firması",
                 "tsoft_member": "Site üyesi", "upload": "Etkinlik yüklemesi"}
ORIGIN_LABELS = {"iys": "İYS", "crm": "CRM bayrağı", "form": "Form", "tsoft": "Site"}

#: CRM izin bayraklarının anlamı (ölçülecek; ekrandan değiştirilir). İleti kanalında CRM yalnız ret üretir.
DEFAULT_FLAG_RULES: list[dict[str, Any]] = [
    {"source": "crm_contact", "field": "DoNotEMail", "value": 1, "channel": "email", "status": "ret"},
    {"source": "crm_contact", "field": "DoNotBulkEMail", "value": 1, "channel": "email", "status": "ret"},
    {"source": "crm_contact", "field": "DoNotPhone", "value": 1, "channel": "call", "status": "ret"},
    {"source": "crm_contact", "field": "obs_donotsms", "value": 1, "channel": "sms", "status": "ret"},
    {"source": "crm_contact", "field": "obs_SmsezinVerme", "value": 1, "channel": "sms", "status": "ret"},
    {"source": "crm_contact", "field": "obs_AramayazinVerme", "value": 1, "channel": "call", "status": "ret"},
    {"source": "crm_contact", "field": "new_kvkkonayi", "value": 1, "channel": "kvkk", "status": "izinli"},
    {"source": "crm_lead", "field": "DoNotEMail", "value": 1, "channel": "email", "status": "ret"},
    {"source": "crm_lead", "field": "DoNotBulkEMail", "value": 1, "channel": "email", "status": "ret"},
    {"source": "crm_lead", "field": "DoNotPhone", "value": 1, "channel": "call", "status": "ret"},
    {"source": "crm_lead", "field": "obs_donotkvkk", "value": 1, "channel": "kvkk", "status": "ret"},
    {"source": "crm_account", "field": "DoNotEMail", "value": 1, "channel": "email", "status": "ret"},
    {"source": "crm_account", "field": "DoNotBulkEMail", "value": 1, "channel": "email", "status": "ret"},
    {"source": "crm_account", "field": "DoNotPhone", "value": 1, "channel": "call", "status": "ret"},
    {"source": "crm_account", "field": "obs_donotsms", "value": 1, "channel": "sms", "status": "ret"},
]
#: Kanal başına izin tarihinin okunduğu CRM alanı (yoksa kaydın değişme tarihi).
_FLAG_DATE = {"email": "email_izin_tarihi", "sms": "sms_izin_tarihi", "call": "arama_izin_tarihi"}


def _conf(key: str, default: str) -> str:
    try:
        from semantic_bridge import admin as admin_mod
        v = admin_mod.conf(key)
    except Exception:  # noqa: BLE001 — testte admin ayarı yok
        v = ""
    return v if v not in (None, "") else os.environ.get(key, default)


def _int(key: str, default: int) -> int:
    try:
        return int(float(str(_conf(key, str(default))).replace(",", ".")))
    except ValueError:
        return default


def _bool(key: str, default: bool) -> bool:
    return str(_conf(key, "1" if default else "0")).strip().lower() in ("1", "true", "evet", "on")


def _json(key: str, default: Any) -> Any:
    raw = _conf(key, "")
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        log.warning("okur ayarı %s JSON değil; varsayılan kullanıldı", key)
        return default


def settings() -> dict[str, Any]:
    """Ekran > ortam > varsayılan. Ölçülmemiş varsayımlar burada; kodda sabit değil."""
    rules = _json("READERS_CRM_FLAG_RULES", DEFAULT_FLAG_RULES)
    if not isinstance(rules, list):
        rules = DEFAULT_FLAG_RULES
    fields = _json("READERS_IYS_FIELD_CHANNELS", {})
    return {
        "leadStates": [int(x) for x in re.findall(r"\d+", _conf("READERS_LEAD_STATES", "0"))] or [0],
        "accountChannel": _int("READERS_ACCOUNT_CHANNEL", 100000009),
        "excludeOrgContacts": _bool("READERS_EXCLUDE_ORG_CONTACTS", True),
        "excludeContributors": _bool("READERS_EXCLUDE_CONTRIBUTORS", True),
        "minorAge": max(1, _int("READERS_MINOR_AGE", 18)),
        "minorExport": _bool("READERS_MINOR_EXPORT", False),
        "requireKvkk": _bool("READERS_REQUIRE_KVKK", True),
        "exportEnabled": _bool("READERS_EXPORT_ENABLED", False),
        "importRetentionDays": max(1, _int("READERS_IMPORT_RETENTION_DAYS", 30)),
        "candidateGroupMax": max(2, _int("READERS_CANDIDATE_GROUP_MAX", 5)),
        "staleHours": max(1, _int("READERS_STALE_HOURS", 48)),
        "queueAlert": max(1, _int("READERS_QUEUE_ALERT", 200)),
        "iysApproveValue": _int("READERS_IYS_APPROVE_VALUE", 1),
        "iysFieldChannels": {str(k).strip().strip("{}").upper(): v for k, v in (fields or {}).items()
                             if v in CHANNELS} if isinstance(fields, dict) else {},
        "flagRules": [r for r in rules if isinstance(r, dict)],
        "okSources": [s.strip() for s in _conf("READERS_CONSENT_SOURCES", "iys").split(",") if s.strip()] or ["iys"],
        "fileMaxMb": max(1, _int("READERS_FILE_MAX_MB", 20)),
    }


def salt() -> bytes:
    s = os.environ.get("READERS_HASH_SALT", "")
    if len(s) < 16:
        raise ReadersError("Okur kimlik tuzu tanımlı değil; kaynaklar okunmadı (yönetici: READERS_HASH_SALT, en az 16 "
                           "karakter, sunucu ortamında).", 503)
    return s.encode("utf-8")


# ------------------------------------------------------------------ normalizasyon ve özet


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _utc(v)
    return v.isoformat() if v else None


def norm_email(v: Any) -> Optional[str]:
    """Baş/son boşluk atılır, küçük harfe çevrilir; «@» yoksa e-posta sayılmaz (kabul SQL'iyle aynı kural)."""
    if v is None:
        return None
    s = str(v).strip().replace("İ", "i").lower()
    return s if "@" in s else None


def norm_phone(v: Any) -> Optional[str]:
    """Türkiye cep telefonu: +90 5XX XXX XX XX biçimine. Başka numara kimlikte kullanılmaz (None)."""
    if v is None:
        return None
    d = re.sub(r"\D", "", str(v))
    if d.startswith("0090"):
        d = d[4:]
    elif d.startswith("90") and len(d) == 12:
        d = d[2:]
    elif d.startswith("0") and len(d) == 11:
        d = d[1:]
    return f"+90{d}" if len(d) == 10 and d.startswith("5") else None


_TR = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u"})


def norm_name(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).replace("İ", "i").replace("I", "ı").lower().translate(_TR)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) >= 3 and " " in s else None           # tek kelime ad eşleşmede kullanılmaz


def digest(kind: str, value: str, key: Optional[bytes] = None) -> str:
    return hmac.new(key or salt(), f"{kind}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def email_key(v: Any, key: Optional[bytes] = None) -> Optional[str]:
    e = norm_email(v)
    return digest("e", e, key) if e else None


def phone_key(v: Any, key: Optional[bytes] = None) -> Optional[str]:
    p = norm_phone(v)
    return digest("p", p, key) if p else None


def mask_email(v: Optional[str]) -> Optional[str]:
    e = norm_email(v)
    if not e:
        return None
    user, _, dom = e.partition("@")
    return f"{user[:1]}***@{dom[:1]}***{dom[dom.rfind('.'):] if '.' in dom else ''}"


def mask_phone(v: Optional[str]) -> Optional[str]:
    p = norm_phone(v)
    return f"{p[:6]} *** ** {p[-2:]}" if p else None


# ------------------------------------------------------------------ kaynak kaydı


@dataclass
class Evidence:
    channel: str                       # email | sms | call | kvkk
    status: str                        # izinli | ret
    origin: str                        # iys | crm | form | tsoft
    at: Optional[datetime]
    detail: Optional[str] = None


@dataclass
class SourceRecord:
    """Bir kaynaktaki tek kayıt (kişisel alanlar yalnız özet olarak). H3 site üyelerini bu biçimde verir."""
    source: str
    source_id: str
    email_hashes: set[str] = field(default_factory=set)
    phone_hashes: set[str] = field(default_factory=set)
    name_hash: Optional[str] = None
    birth_year: Optional[int] = None
    city: Optional[str] = None
    gender: Optional[str] = None
    created: Optional[datetime] = None
    attrs: dict[str, list[str]] = field(default_factory=dict)
    interests: list[dict[str, str]] = field(default_factory=list)
    evidences: list[Evidence] = field(default_factory=list)
    parent: Optional[tuple[str, str]] = None
    events: int = 0
    last_event: Optional[datetime] = None
    last_touch: Optional[datetime] = None

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.source_id)


def record(source: str, source_id: str, *, emails: Iterable[Any] = (), phones: Iterable[Any] = (), name: Any = None,
           birth_year: Optional[int] = None, city: Optional[str] = None, created: Any = None,
           attrs: Optional[dict[str, list[str]]] = None, evidences: Iterable[Evidence] = (),
           key: Optional[bytes] = None) -> SourceRecord:
    """Ham değerlerden kayıt: e-posta/telefon/ad burada özete çevrilir, ham hâli tutulmaz."""
    k = key or salt()
    nm = norm_name(name)
    return SourceRecord(
        source=source, source_id=str(source_id),
        email_hashes={h for h in (email_key(e, k) for e in emails) if h},
        phone_hashes={h for h in (phone_key(p, k) for p in phones) if h},
        name_hash=digest("n", nm, k) if nm else None, birth_year=birth_year, city=(city or None),
        created=_utc(created), attrs={a: sorted({v for v in vs if v}) for a, vs in (attrs or {}).items() if vs},
        evidences=list(evidences))


#: Diğer modüllerin kaynak sağlayıcıları (H3 site üyesi vb.): ad → işlev(engine, tenant) → [SourceRecord].
_PROVIDERS: dict[str, Callable[[sa.engine.Engine, str], list[SourceRecord]]] = {}
#: Dışa aktarımda iletişim adresi kaynaktan anlık okunabilen kaynaklar: CRM + `register_source(..., address=True)` ile
#: kaydolanlar (H3 site üyesi adresini T-soft'tan okur). Yalnız bu kaynaklardan birine bağlı okur listeye girebilir.
ADDRESS_SOURCES: set[str] = {"crm_contact", "crm_lead", "crm_account"}


def register_source(name: str, provider: Callable[[sa.engine.Engine, str], list[SourceRecord]], *,
                    address: bool = False) -> None:
    """Başka bir modülün kaynağını kimlik birleştirmeye ekler (örn. H3 `tsoft_member`). Her okuma turunda çağrılır.
    `address=True`: o modül dışa aktarımda adresi kendi kaynağından okur (H2'nin segment dışa aktarımı yalnız CRM okur)."""
    _PROVIDERS[name] = provider
    if address:
        ADDRESS_SOURCES.add(name)


def _label(labels: dict[str, dict[str, str]], attr: str, code: Any) -> Optional[str]:
    if code is None or code == "":
        return None
    try:
        c = str(int(code))
    except (TypeError, ValueError):
        c = str(code)
    return labels.get(attr.lower(), {}).get(c) or c


def iys_channels(fields: list[dict[str, Any]], labels: dict[str, dict[str, str]],
                 override: dict[str, str]) -> dict[str, str]:
    """İYS entegrasyon alanı → kanal. Ayar kazanır; yoksa alan adı/İYS alan adı/alıcı metninden."""
    out: dict[str, str] = {}
    for f in fields:
        fid = src._id(f.get("id"))
        if not fid:
            continue
        if fid in override:
            out[fid] = override[fid]
            continue
        ch = channel_from_text(" ".join(str(f.get(k) or "") for k in ("ad", "iys_alan", "alici", "gonderim_alani")))
        if ch:
            out[fid] = ch
    return out


def channel_from_text(text: str) -> Optional[str]:
    t = (text or "").upper().replace("İ", "I")
    if re.search(r"E-?POSTA|MAIL", t):
        return "email"
    if re.search(r"MESAJ|SMS", t):
        return "sms"
    if re.search(r"ARAMA|CALL|TELEFON", t):
        return "call"
    return None


def records_from_bundle(bundle: dict[str, Any], cfg: dict[str, Any], key: Optional[bytes] = None
                        ) -> tuple[list[SourceRecord], dict[str, Any]]:
    """CRM okumasından kayıtlar ve sayımlar. Kurum çalışanı ve esere katkı veren kişi (ayarla) okur değildir; sayılır."""
    k = key or salt()
    labels = bundle.get("labels") or {}
    stats: dict[str, Any] = {"read": {}, "excluded": {"kurum": 0, "katki": 0}, "iysUnmapped": 0, "iysUnknownCustomer": 0}
    rules = [r for r in cfg["flagRules"] if r.get("channel") in CHANNELS + ("kvkk",) and r.get("status") in ("izinli", "ret")]
    ok_msg_crm = "crm" in cfg["okSources"]
    recs: dict[tuple[str, str], SourceRecord] = {}
    raw_emails_cl: set[str] = set()

    def flags_of(source: str, row: dict[str, Any]) -> list[Evidence]:
        out = []
        for r in rules:
            if r.get("source") != source or r.get("field") not in row:
                continue
            v = row.get(r["field"])
            try:
                hit = v is not None and int(v) == int(r.get("value", 1))
            except (TypeError, ValueError):
                hit = False
            if not hit:
                continue
            ch, st = r["channel"], r["status"]
            if ch in CHANNELS and st == "izinli" and not ok_msg_crm:
                continue                                           # ileti izni yalnız İYS'den
            at = _utc(row.get(_FLAG_DATE.get(ch, ""))) or _utc(row.get("degisme"))
            out.append(Evidence(ch, st, "crm", at, r["field"]))
        return out

    contributors = bundle.get("contributors") or set()
    events = bundle.get("events") or {}
    interests = bundle.get("interests") or {}
    form_types: Counter = Counter()
    for row in bundle.get("contacts") or []:
        form_types[str(row.get("form_tipi")) if row.get("form_tipi") is not None else "bos"] += 1
        sid = src._id(row.get("id"))
        if not sid:
            continue
        for e in (row.get("eposta"),):
            ne = norm_email(e)
            if ne:
                raw_emails_cl.add(ne)
        if cfg["excludeOrgContacts"] and row.get("kurum_id"):
            stats["excluded"]["kurum"] += 1
            continue
        if cfg["excludeContributors"] and sid in contributors:
            stats["excluded"]["katki"] += 1
            continue
        by = [y for y in (src.year_of(row.get("dogum")), src.year_of(row.get("dogum2")), src.year_of(row.get("dogum_yili"))) if y]
        ilgi = [{"ad": x, "kaynak": "CRM uzmanlık alanı"} for x in interests.get(sid, [])]
        for part in re.split(r"[,;/]", row.get("ilgi_metni") or ""):
            if part.strip():
                ilgi.append({"ad": part.strip()[:80], "kaynak": "CRM ilgi metni"})
        rec = record("crm_contact", sid, emails=(row.get("eposta"), row.get("eposta2")), phones=(row.get("cep"),),
                     name=" ".join(x for x in (row.get("ad"), row.get("soyad")) if x), birth_year=by[0] if by else None,
                     city=src._s(row.get("il")), created=row.get("olusturma"), key=k,
                     attrs={"form_tipi": [_label(labels, "new_geliskanali", row.get("form_tipi"))],
                            "kayit_tipi": [_label(labels, "new_kayittipi", row.get("kayit_tipi"))],
                            "departman": [_label(labels, "new_ilgilidepartman", row.get("departman"))]},
                     evidences=flags_of("crm_contact", row))
        rec.gender = _label(labels, "gendercode", row.get("cinsiyet"))
        rec.interests = ilgi
        ev = events.get(sid)
        if ev:
            rec.events, rec.last_event = ev["sayi"], _utc(ev.get("son"))
        if len(set(by)) > 1:
            rec.attrs["dogum_yillari"] = sorted({str(y) for y in by})
        recs[rec.key] = rec
    stats["read"]["crm_contact"] = len(bundle.get("contacts") or [])

    for row in bundle.get("leads") or []:
        sid = src._id(row.get("id"))
        if not sid:
            continue
        ne = norm_email(row.get("eposta"))
        if ne and row.get("durum") in (0, None):
            raw_emails_cl.add(ne)
        rec = record("crm_lead", sid, emails=(row.get("eposta"), row.get("eposta2")), phones=(row.get("cep"),),
                     name=" ".join(x for x in (row.get("ad"), row.get("soyad")) if x),
                     birth_year=src.year_of(row.get("dogum")), city=src._s(row.get("il")), created=row.get("olusturma"),
                     key=k, attrs={"katilim_kaynagi": [src._s(row.get("katilim_kaynagi"))],
                                   "alt_kaynak": [src._s(row.get("alt_kaynak"))],
                                   "utm_kaynak": [src._s(row.get("utm_kaynak"))],
                                   "utm_kampanya": [src._s(row.get("utm_kampanya"))]},
                     evidences=flags_of("crm_lead", row))
        if src._s(row.get("ilgi")):
            rec.interests = [{"ad": src._s(row["ilgi"]), "kaynak": "CRM aday ilgi alanı"}]
        parent = src._id(row.get("kisi_id"))
        if parent:
            rec.parent = ("crm_contact", parent)
        recs[rec.key] = rec
    stats["read"]["crm_lead"] = len(bundle.get("leads") or [])

    for row in bundle.get("accounts") or []:
        sid = src._id(row.get("id"))
        if not sid:
            continue
        rec = record("crm_account", sid, emails=(row.get("eposta"),), phones=(row.get("cep"),), name=row.get("ad"),
                     city=src._s(row.get("il")), created=row.get("olusturma"), key=k,
                     evidences=flags_of("crm_account", row))
        recs[rec.key] = rec
    stats["read"]["crm_account"] = len(bundle.get("accounts") or [])

    # İYS: her (kayıt, alan) için en son kayıt kazanır.
    fmap = iys_channels(bundle.get("iysFields") or [], labels, cfg["iysFieldChannels"])
    chan_labels = labels.get("obs_channel", {})
    latest: dict[tuple[tuple[str, str], str], dict[str, Any]] = {}
    lo = datetime.min.replace(tzinfo=timezone.utc)

    def order(r: dict[str, Any]) -> tuple[datetime, datetime, int]:
        # Kabul SQL'iyle (R5) aynı sıra: izin tarihi, sonra oluşturma (boş en eskidir). İkisi de birebir aynı ve durum
        # farklıysa «son kayıt» belirsizdi (SQL ROW_NUMBER keyfî seçer, burada ilk okunan kalırdı): ret kazanır — izin
        # kanıtlanamıyorsa gönderilmez (KVKK tarafı güvenli), R5 aynı kuralı `CASE … END DESC` ile uygular.
        try:
            refused = 0 if int(r.get("durum")) == cfg["iysApproveValue"] else 1
        except (TypeError, ValueError):
            refused = 1
        return (_utc(r.get("tarih")) or lo, _utc(r.get("olusturma")) or lo, refused)
    latest_all: dict[tuple[str, str], dict[str, Any]] = {}
    for row in bundle.get("iys") or []:
        cid = src._id(row.get("musteri"))
        if not cid:
            # Müşterisi boş günlük satırı kimseye ait değil: son durum sayısına girmez (eski R5 bunları alan başına tek
            # bir «boş müşteri» bölmesinde +1 sayıyordu — kabuldeki 1'er fark). Sayısı ayrıca yazılır.
            stats["iysNoCustomer"] = stats.get("iysNoCustomer", 0) + 1
            continue
        fk = src._id(row.get("alan")) or f"kanal:{row.get('kanal')}"
        cur_all = latest_all.get((cid, fk))
        if cur_all is None or order(row) > order(cur_all):
            latest_all[(cid, fk)] = row
        s = src.CUSTOMER_TYPES.get(row.get("musteri_turu"))
        if s is None:
            s = next((x for x in ("crm_contact", "crm_lead", "crm_account") if (x, cid) in recs), None)
        if s is None or (s, cid) not in recs:
            stats["iysUnknownCustomer"] += 1
            continue
        cur = latest.get(((s, cid), fk))
        if cur is None or order(row) > order(cur):
            latest[((s, cid), fk)] = row
    stats["iysRows"] = len(bundle.get("iys") or [])
    for (rk, fid), row in latest.items():
        ch = fmap.get(fid) or channel_from_text(chan_labels.get(str(row.get("kanal")), ""))
        if not ch:
            stats["iysUnmapped"] += 1
            continue
        try:
            ok = int(row.get("durum")) == cfg["iysApproveValue"]
        except (TypeError, ValueError):
            continue
        at = _utc(row.get("tarih")) or _utc(row.get("olusturma"))
        recs[rk].evidences.append(Evidence(ch, "izinli" if ok else "ret", "iys", at, "İYS"))
    iys_latest: dict[str, Counter] = defaultdict(Counter)
    for (_cid, fk), row in latest_all.items():
        iys_latest[fk]["onay" if row.get("durum") == cfg["iysApproveValue"] else "ret"] += 1
    stats["iysLatest"] = {k: dict(v) for k, v in iys_latest.items()}
    last_iys = max((order(r)[0] for r in latest_all.values()), default=None)
    stats["iysLast"] = _iso(last_iys) if last_iys and last_iys > lo else None
    stats["formTypes"] = dict(form_types)
    stats["eventContacts"] = len(events)
    stats["distinctEmailsContactLead"] = len(raw_emails_cl)
    stats["iysChannels"] = fmap
    return list(recs.values()), stats


# ------------------------------------------------------------------ kimlik birleştirme (saf)


class _UF:
    def __init__(self) -> None:
        self.p: dict[Any, Any] = {}

    def find(self, x: Any) -> Any:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: Any, b: Any) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def new_reader_id() -> str:
    return "OK" + uuid.uuid4().hex[:18].upper()


@dataclass
class Resolution:
    assign: dict[tuple[str, str], str]                 # kayıt → okur
    rule: dict[tuple[str, str], str]                   # kayıt → birleşme kuralı
    members: dict[str, list[tuple[str, str]]]          # okur → kayıtlar
    merged: dict[str, str]                             # eski okur → yeni okur
    gone: set[str]                                     # kaydı kalmayan eski okurlar


def resolve(records: list[SourceRecord], prev: dict[tuple[str, str], str],
            manual: Iterable[tuple[tuple[str, str], tuple[str, str]]] = (),
            id_factory: Callable[[], str] = new_reader_id) -> Resolution:
    """Deterministik birleştirme. `prev` önceki kayıt→okur eşlemesi (kimlik sürekliliği), `manual` insan «aynı kişi»
    kararlarının kayıt çiftleri (her okurun karar anındaki temsilci kaydı)."""
    uf = _UF()
    by_key = {r.key: r for r in records}
    for r in records:
        uf.find(r.key)
    email_owner: dict[str, tuple[str, str]] = {}
    phone_owner: dict[str, tuple[str, str]] = {}
    shared_e: set[tuple[str, str]] = set()
    shared_p: set[tuple[str, str]] = set()
    for r in sorted(records, key=lambda x: x.key):
        for h in sorted(r.email_hashes):
            if h in email_owner:
                uf.union(r.key, email_owner[h])
                shared_e.update((r.key, email_owner[h]))
            else:
                email_owner[h] = r.key
        for h in sorted(r.phone_hashes):
            if h in phone_owner:
                uf.union(r.key, phone_owner[h])
                shared_p.update((r.key, phone_owner[h]))
            else:
                phone_owner[h] = r.key
    parented: set[tuple[str, str]] = set()
    for r in records:
        if r.parent and r.parent in by_key:
            uf.union(r.key, r.parent)
            parented.update((r.key, r.parent))
    for ka, kb in manual:
        ka, kb = tuple(ka), tuple(kb)
        if ka in by_key and kb in by_key:
            uf.union(ka, kb)
    comps: dict[Any, list[tuple[str, str]]] = defaultdict(list)
    for r in records:
        comps[uf.find(r.key)].append(r.key)

    assign: dict[tuple[str, str], str] = {}
    members: dict[str, list[tuple[str, str]]] = {}
    merged: dict[str, str] = {}
    taken: set[str] = set()
    for root in sorted(comps, key=lambda c: (-len(comps[c]), min(comps[c]))):
        keys = sorted(comps[root])
        counts = Counter(prev[k] for k in keys if k in prev)
        chosen = None
        for rid, _n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            if rid not in taken:
                chosen = rid
                break
        if chosen is None:
            chosen = id_factory()
        taken.add(chosen)
        for rid in counts:
            if rid != chosen and rid not in taken:
                merged[rid] = chosen
        members[chosen] = keys
        for k in keys:
            assign[k] = chosen
    gone = {rid for rid in set(prev.values()) if rid not in members and rid not in merged}
    rule: dict[tuple[str, str], str] = {}
    for rid, keys in members.items():
        for k in keys:
            if len(keys) == 1:
                rule[k] = "tek"
            elif k in shared_e:
                rule[k] = "email"
            elif k in shared_p:
                rule[k] = "phone"
            elif k in parented:
                rule[k] = "kaynak"
            else:
                rule[k] = "manual"
    return Resolution(assign, rule, members, merged, gone)


# ------------------------------------------------------------------ izin (saf)


def final_consent(evidences: Iterable[Any], channel: str, ok_sources: Iterable[str] = ("iys",)
                  ) -> tuple[str, Optional[str], Optional[datetime]]:
    """(durum, karar veren kaynak, tarih). Ret her zaman kazanır; izinli yalnız izinli sayılan kaynaktan (KVKK hariç);
    bilgi yoksa bilinmiyor. Kanıt `Evidence` ya da {channel,status,source|origin,at} sözlüğü olabilir."""
    ok = set(ok_sources)
    rets, oks = [], []
    for e in evidences:
        ch = e.channel if isinstance(e, Evidence) else e.get("channel")
        if ch != channel:
            continue
        st = e.status if isinstance(e, Evidence) else e.get("status")
        og = e.origin if isinstance(e, Evidence) else (e.get("origin") or e.get("source"))
        at = _utc(e.at if isinstance(e, Evidence) else e.get("at"))
        if st == "ret":
            rets.append((at, og))
        elif st == "izinli" and (channel == "kvkk" or og in ok):
            oks.append((at, og))
    lo = datetime.min.replace(tzinfo=timezone.utc)
    if rets:
        at, og = max(rets, key=lambda x: x[0] or lo)
        return "ret", og, at
    if oks:
        at, og = max(oks, key=lambda x: x[0] or lo)
        return "izinli", og, at
    return "bilinmiyor", None, None


def exportable(profile: dict[str, Any], channel: str, cfg: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Dışa aktarılabilir mi; değilse neden (sayım için). Sıra: ret → izin yok → KVKK → çocuk → adres."""
    c = profile["consent"].get(channel, "bilinmiyor")
    if c == "ret":
        return False, "ret"
    if c != "izinli":
        return False, "izin_yok"
    if cfg["requireKvkk"] and profile["consent"].get("kvkk") != "izinli":
        return False, "kvkk_yok"
    if profile["minor"] and not cfg["minorExport"]:
        return False, "cocuk"
    if not any(s in ADDRESS_SOURCES for s in profile["sources"]):
        return False, "adres_yok"
    return True, None


# ------------------------------------------------------------------ profil (saf)


def build_profile(recs: list[SourceRecord], extra_events: list[dict[str, Any]], minor_age: int,
                  today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    years = [r.birth_year for r in recs if r.birth_year]
    for r in recs:
        for y in r.attrs.get("dogum_yillari", []):
            years.append(int(y))
    minor = any(today.year - y < minor_age for y in years)
    by = Counter(years).most_common(1)[0][0] if years else None
    cities = Counter(r.city for r in recs if r.city)
    city = cities.most_common(1)[0][0] if cities else None
    genders = Counter(r.gender for r in recs if r.gender)
    attrs: dict[str, set[str]] = defaultdict(set)
    for r in recs:
        for a, vs in r.attrs.items():
            if a != "dogum_yillari":
                attrs[a].update(v for v in vs if v)
    for e in extra_events:
        if e.get("label"):
            attrs["etkinlik_adi"].add(e["label"])
    if years and max(years) - min(years) >= 12:
        attrs["uyari"].add("ortak_iletisim")
    interests: dict[str, dict[str, str]] = {}
    for r in recs:
        for i in r.interests:
            interests.setdefault(i["ad"].casefold(), i)
    touches = [t for r in recs for t in (r.created, r.last_event, r.last_touch) if t]
    touches += [e.at for r in recs for e in r.evidences if e.at]
    touches += [_utc(e["at"]) for e in extra_events if e.get("at")]
    created = [r.created for r in recs if r.created]
    return {
        "birth_year": by, "city": city, "gender": genders.most_common(1)[0][0] if genders else None, "is_minor": minor,
        "first_seen": min(created) if created else None, "last_touch": max(touches) if touches else None,
        "interests": list(interests.values()), "attrs": {a: sorted(v) for a, v in attrs.items() if v},
        "sources": dict(Counter(r.source for r in recs)),
        "event_count": sum(r.events for r in recs) + len(extra_events),
    }


# ------------------------------------------------------------------ belirsiz eşleşme adayları (saf)


def candidate_pairs(records: list[SourceRecord], assign: dict[tuple[str, str], str], group_max: int
                    ) -> tuple[list[tuple[str, str, dict[str, Any], float]], int]:
    """Farklı okurlarda aynı ad özeti + aynı il → aday. Doğum yılları ikisinde de biliniyor ve 1'den çok farklıysa
    aday değildir. `group_max`'tan kalabalık gruplar (yaygın ad) aday üretmez; sayısı döner."""
    groups: dict[tuple[str, str], dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for r in records:
        if r.name_hash and r.city and r.key in assign:
            groups[(r.name_hash, r.city.casefold())][assign[r.key]].update(
                {r.birth_year} if r.birth_year else set())
    out: list[tuple[str, str, dict[str, Any], float]] = []
    skipped = 0
    for _g, readers in groups.items():
        ids = sorted(readers)
        if len(ids) < 2:
            continue
        if len(ids) > group_max:
            skipped += 1
            continue
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                ya, yb = readers[a], readers[b]
                if ya and yb and min(abs(x - y) for x in ya for y in yb) > 1:
                    continue
                same_year = bool(ya and yb and ya & yb)
                feats = {"ad": "ayni", "il": "ayni", "dogum_yili": "ayni" if same_year else "bilinmiyor",
                         "eposta": "farkli", "telefon": "farkli"}
                out.append((a, b, feats, 0.9 if same_year else 0.6))
    return out, skipped


# ------------------------------------------------------------------ okuma turu (yazma)


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _load(v: Optional[str], default: Any) -> Any:
    if not v:
        return default
    try:
        return json.loads(v)
    except ValueError:
        return default


def _stamp(conn, tenant: str) -> str:
    s = _now().isoformat()
    conn.execute(META.delete().where(sa.and_(META.c.tenant_id == tenant, META.c.key == "stamp")))
    conn.execute(META.insert().values(tenant_id=tenant, key="stamp", value=s))
    return s


def stamp(engine: sa.engine.Engine, tenant: str) -> Optional[str]:
    with engine.connect() as c:
        return c.execute(sa.select(META.c.value).where(sa.and_(META.c.tenant_id == tenant, META.c.key == "stamp"))).scalar()


def _bulk(conn, table: sa.Table, rows: list[dict[str, Any]], n: int = 2000) -> None:
    for i in range(0, len(rows), n):
        conn.execute(table.insert(), rows[i:i + n])


def record_sync_error(engine: sa.engine.Engine, tenant: str, source: str, message: str) -> None:
    ensure(engine)
    with engine.begin() as c:
        row = c.execute(sa.select(SYNC).where(sa.and_(SYNC.c.tenant_id == tenant, SYNC.c.source == source))).first()
        if row:
            c.execute(SYNC.update().where(sa.and_(SYNC.c.tenant_id == tenant, SYNC.c.source == source))
                      .values(error=message[:2000], error_at=_now()))
        else:
            c.execute(SYNC.insert().values(tenant_id=tenant, source=source, error=message[:2000], error_at=_now()))


def sync(engine: sa.engine.Engine, tenant: str, bundle: dict[str, Any], cfg: Optional[dict[str, Any]] = None,
         key: Optional[bytes] = None, today: Optional[date] = None) -> dict[str, Any]:
    """Bir okuma turu: kayıtlar → kimlik → profil + izin kanıtı → aday çiftler. Hepsi tek işlemde yazılır."""
    ensure(engine)
    cfg = cfg or settings()
    k = key or salt()
    from semantic_bridge import readers_imports as imp

    records, stats = records_from_bundle(bundle, cfg, k)
    records += imp.upload_records(engine, tenant, k)
    for name, prov in list(_PROVIDERS.items()):
        try:
            extra = prov(engine, tenant)
            records += extra
            stats["read"][name] = len(extra)
        except Exception as e:  # noqa: BLE001 — başka modülün kaynağı turu düşürmez
            log.warning("okur kaynağı %s okunamadı: %s", name, e)
            bundle.setdefault("errors", {})[name] = str(e)[:300]

    with engine.connect() as c:
        prev = {(r.source, r.source_id): r.reader_id
                for r in c.execute(sa.select(LINKS.c.source, LINKS.c.source_id, LINKS.c.reader_id).where(LINKS.c.tenant_id == tenant))}
        old = {r.reader_id: r for r in c.execute(sa.select(READERS).where(READERS.c.tenant_id == tenant))}
        cand_rows = list(c.execute(sa.select(CANDIDATES).where(CANDIDATES.c.tenant_id == tenant)))
        ev_rows = list(c.execute(sa.select(EVENTS).where(EVENTS.c.tenant_id == tenant)))
    # Önceki okur zinciri: birleşmiş okurun kararları ve olayları yaşayana taşınır.
    def alive(rid: str) -> str:
        seen = set()
        while rid in old and old[rid].status == "birlesti" and old[rid].merged_into and rid not in seen:
            seen.add(rid)
            rid = old[rid].merged_into
        return rid
    manual = [tuple(_load(r.features_json, {}).get("baglar") or ()) for r in cand_rows if r.status == "ayni"]
    res = resolve(records, prev, [m for m in manual if len(m) == 2])
    deciders: dict[tuple[str, str], tuple[Optional[str], Any]] = {}
    for r in cand_rows:
        if r.status == "ayni":
            for kk in _load(r.features_json, {}).get("baglar") or []:
                deciders[tuple(kk)] = (r.decided_by, r.decided_at)
    by_key = {r.key: r for r in records}

    events_by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in ev_rows:
        rid = alive(e.reader_id)
        rid = res.merged.get(rid, rid)
        events_by[rid].append({"at": e.at, "label": e.label})

    now = _now()
    readers_rows, links_rows, keys_rows, cons_rows = [], [], [], []
    counts = {"aktif": 0, "cocuk": 0}
    for rid, keys in res.members.items():
        recs = [by_key[k] for k in keys]
        p = build_profile(recs, events_by.get(rid, []), cfg["minorAge"], today)
        eh = sorted({h for r in recs for h in r.email_hashes})
        ph = sorted({h for r in recs for h in r.phone_hashes})
        readers_rows.append({
            "reader_id": rid, "tenant_id": tenant, "status": "aktif", "merged_into": None,
            "email_hash": eh[0] if eh else None, "phone_hash": ph[0] if ph else None, "birth_year": p["birth_year"],
            "city": p["city"], "gender": p["gender"], "is_minor": p["is_minor"], "first_seen": p["first_seen"],
            "last_touch": p["last_touch"], "loyalty": None, "interests_json": _dump(p["interests"]),
            "attrs_json": _dump(p["attrs"]), "sources_json": _dump(p["sources"]), "event_count": p["event_count"],
            "updated_at": now})
        counts["aktif"] += 1
        counts["cocuk"] += int(p["is_minor"])
        for r in recs:
            links_rows.append({"tenant_id": tenant, "source": r.source, "source_id": r.source_id, "reader_id": rid,
                               "name_hash": r.name_hash, "match_rule": res.rule[r.key], "confidence": 1.0,
                               "decided_by": deciders.get(r.key, (None, None))[0] if res.rule[r.key] == "manual" else None,
                               "decided_at": deciders.get(r.key, (None, None))[1] if res.rule[r.key] == "manual" else None,
                               "created_at": r.created,
                               "attrs_json": _dump({**r.attrs, "il": r.city, "dogum_yili": r.birth_year,
                                                    "etkinlik": r.events, "son_etkinlik": _iso(r.last_event)})})
            for h in r.email_hashes:
                keys_rows.append({"tenant_id": tenant, "kind": "e", "hash": h, "reader_id": rid, "source": r.source,
                                  "source_id": r.source_id})
            for h in r.phone_hashes:
                keys_rows.append({"tenant_id": tenant, "kind": "p", "hash": h, "reader_id": rid, "source": r.source,
                                  "source_id": r.source_id})
            for e in r.evidences:
                cons_rows.append({"tenant_id": tenant, "reader_id": rid, "channel": e.channel, "status": e.status,
                                  "source": e.origin, "at": e.at, "link_source": r.source, "link_id": r.source_id,
                                  "detail": (e.detail or "")[:200]})
    # Geçmiş: kaydı kalmayan okur pasif, birleşen okur yaşayanı gösterir; eski geçmiş satırları korunur.
    for rid, o in old.items():
        if rid in res.members:
            continue
        status, into = o.status, o.merged_into
        if rid in res.merged:
            status, into = "birlesti", res.merged[rid]
        elif rid in res.gone or status == "aktif":
            status, into = "pasif", None
        readers_rows.append({**{c.name: getattr(o, c.name) for c in READERS.columns}, "status": status,
                             "merged_into": into, "updated_at": now if status != o.status else o.updated_at})

    # Adaylar: kararlılar korunur; artık üretilmeyen bekleyen aday geçersiz olur.
    active_keys = [r for r in records if r.key in res.assign]
    pairs, skipped = candidate_pairs(active_keys, res.assign, cfg["candidateGroupMax"])
    existing = {(alive(r.a_reader), alive(r.b_reader)): r for r in cand_rows}
    existing.update({(b, a): r for (a, b), r in list(existing.items())})
    new_pairs = {(a, b) for a, b, _f, _s in pairs}

    with engine.begin() as c:
        for t in (KEYS, LINKS, CONSENTS, READERS):
            c.execute(t.delete().where(t.c.tenant_id == tenant))
        _bulk(c, READERS, readers_rows)
        _bulk(c, LINKS, links_rows)
        _bulk(c, KEYS, keys_rows)
        _bulk(c, CONSENTS, cons_rows)
        for r in cand_rows:
            a, b = alive(r.a_reader), alive(r.b_reader)
            a, b = res.merged.get(a, a), res.merged.get(b, b)
            stale = a == b or a not in res.members or b not in res.members
            if r.status == "bekliyor" and (stale or ((a, b) not in new_pairs and (b, a) not in new_pairs)):
                c.execute(CANDIDATES.update().where(CANDIDATES.c.id == r.id).values(status="gecersiz"))
        for a, b, feats, score in pairs:
            if (a, b) in existing:
                ex = existing[(a, b)]
                if ex.status == "gecersiz":                      # yeniden geçerli olan çift kuyruğa döner
                    c.execute(CANDIDATES.update().where(CANDIDATES.c.id == ex.id).values(
                        status="bekliyor", a_reader=a, b_reader=b, features_json=_dump(feats), score=score))
                continue
            c.execute(CANDIDATES.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, a_reader=a, b_reader=b,
                                                 features_json=_dump(feats), score=score, status="bekliyor",
                                                 created_at=now))
        errors = bundle.get("errors") or {}
        side = {"iys": len(bundle.get("iys") or []), "iys_alan": len(bundle.get("iysFields") or []),
                "etkinlik": len(bundle.get("events") or {}), "ilgi": len(bundle.get("interests") or {}),
                "katki": len(bundle.get("contributors") or ()), "kampanya": len(bundle.get("campaigns") or []),
                "etiket": sum(len(v) for v in (bundle.get("labels") or {}).values())}
        read_rows = {**stats["read"], **{s: n for s, n in side.items() if s not in errors and "readAt" in bundle}}
        for s, n in read_rows.items():
            err = errors.get(s)
            row = c.execute(sa.select(SYNC.c.source).where(sa.and_(SYNC.c.tenant_id == tenant, SYNC.c.source == s))).first()
            # Okunamayan kaynakta son başarılı okuma zamanı korunur (tazelik ondan hesaplanır).
            vals = {"error": err, "error_at": now} if err else {"at": now, "rows": n, "error": None, "error_at": None}
            if row:
                c.execute(SYNC.update().where(sa.and_(SYNC.c.tenant_id == tenant, SYNC.c.source == s)).values(**vals))
            else:
                c.execute(SYNC.insert().values(tenant_id=tenant, source=s, **vals))
        for s, err in errors.items():
            if s in read_rows:
                continue
            row = c.execute(sa.select(SYNC.c.source).where(sa.and_(SYNC.c.tenant_id == tenant, SYNC.c.source == s))).first()
            if row:
                c.execute(SYNC.update().where(sa.and_(SYNC.c.tenant_id == tenant, SYNC.c.source == s)).values(error=err, error_at=now))
            else:
                c.execute(SYNC.insert().values(tenant_id=tenant, source=s, error=err, error_at=now))
        summary = {"readers": counts["aktif"], "minors": counts["cocuk"], "links": len(links_rows),
                   "merged": len(res.merged), "gone": len(res.gone), "candidates": len(pairs),
                   "candidateGroupsSkipped": skipped, "excluded": stats["excluded"],
                   "distinctEmailsContactLead": stats["distinctEmailsContactLead"], "iysRows": stats.get("iysRows", 0),
                   "iysUnmapped": stats["iysUnmapped"], "iysUnknownCustomer": stats["iysUnknownCustomer"],
                   "iysNoCustomer": stats.get("iysNoCustomer", 0), "iysChannels": stats.get("iysChannels", {}), "iysLatest": stats.get("iysLatest", {}), "iysLast": stats.get("iysLast"),
                   "formTypes": stats.get("formTypes", {}), "eventContacts": stats.get("eventContacts", 0),
                   "read": stats["read"], "campaigns": [
                       {"ad": src._s(x.get("ad")), "gonderim": x.get("gonderim"), "okunma": x.get("okunma"),
                        "tiklama": x.get("tiklama"), "karaListe": x.get("kara_liste"),
                        "baslangic": _iso(_utc(x.get("baslangic")) or _utc(x.get("olusturma")))}
                       for x in bundle.get("campaigns") or []],
                   "formTypeLabels": (bundle.get("labels") or {}).get("new_geliskanali", {}),
                   "errors": bundle.get("errors") or {}}
        row = c.execute(sa.select(SYNC.c.source).where(sa.and_(SYNC.c.tenant_id == tenant, SYNC.c.source == "_tur"))).first()
        vals = {"at": now, "rows": len(records), "error": None, "stats_json": _dump(summary)}
        if row:
            c.execute(SYNC.update().where(sa.and_(SYNC.c.tenant_id == tenant, SYNC.c.source == "_tur")).values(**vals))
        else:
            c.execute(SYNC.insert().values(tenant_id=tenant, source="_tur", **vals))
        _stamp(c, tenant)
    return summary


# ------------------------------------------------------------------ profiller (segment ve özet için)

_cache: dict[tuple[int, str], tuple[Optional[str], list[dict[str, Any]]]] = {}
_cache_lock = threading.Lock()


# Okuma ifadeleri ayrı kurulur: aynı ifade hem çalıştırılır hem sorgu bilgisinde gösterilir (readers_kaynak.py).
# Sorgu bilgisi yalnız SQL metnini ve satır sayısını taşır; okur satırı (kişisel veri) hiçbir zaman kayda girmez.


def active_stmt(tenant: str):
    return sa.select(READERS).where(sa.and_(READERS.c.tenant_id == tenant, READERS.c.status == "aktif"))


def consents_stmt(tenant: str):
    return sa.select(CONSENTS.c.reader_id, CONSENTS.c.channel, CONSENTS.c.status, CONSENTS.c.source,
                     CONSENTS.c.at).where(CONSENTS.c.tenant_id == tenant)


def sync_stmt(tenant: str):
    return sa.select(SYNC).where(SYNC.c.tenant_id == tenant)


def pending_stmt(tenant: str):
    return sa.select(sa.func.count()).select_from(CANDIDATES).where(
        sa.and_(CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.status == "bekliyor"))


def keys_stmt(tenant: str):
    return (sa.select(KEYS.c.kind, sa.func.count(sa.distinct(KEYS.c.hash))).where(KEYS.c.tenant_id == tenant)
            .group_by(KEYS.c.kind))


def reader_stmt(tenant: str, reader_id: str):
    return sa.select(READERS).where(sa.and_(READERS.c.tenant_id == tenant, READERS.c.reader_id == reader_id))


def reader_consents_stmt(tenant: str, reader_id: str):
    return sa.select(CONSENTS).where(sa.and_(CONSENTS.c.tenant_id == tenant, CONSENTS.c.reader_id == reader_id))


def reader_events_stmt(tenant: str, ids: list[str]):
    return sa.select(EVENTS).where(sa.and_(EVENTS.c.tenant_id == tenant, EVENTS.c.reader_id.in_(ids)))


def reader_candidates_stmt(tenant: str, reader_id: str):
    return sa.select(CANDIDATES).where(sa.and_(
        CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.status == "bekliyor",
        sa.or_(CANDIDATES.c.a_reader == reader_id, CANDIDATES.c.b_reader == reader_id)))


def links_stmt(tenant: str, ids: list[str]):
    return sa.select(LINKS).where(sa.and_(LINKS.c.tenant_id == tenant, LINKS.c.reader_id.in_(ids)))


def candidates_stmts(tenant: str, status: str, page: int, size: int) -> dict[str, Any]:
    base = sa.and_(CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.status == status)
    return {"say": sa.select(sa.func.count()).select_from(CANDIDATES).where(base),
            "sayfa": (sa.select(CANDIDATES).where(base).order_by(CANDIDATES.c.score.desc(), CANDIDATES.c.created_at)
                      .offset(max(0, page) * size).limit(size))}


def sql_runs_set(engine: sa.engine.Engine, tenant: str, runs: list[dict[str, Any]]) -> None:
    """Okuma turunun çalıştırdığı CRM SQL'leri (metin, satır sayısı, süre, an; sonuç satırı yok)."""
    with engine.begin() as c:
        c.execute(META.delete().where(sa.and_(META.c.tenant_id == tenant, META.c.key == "sql")))
        c.execute(META.insert().values(tenant_id=tenant, key="sql", value=_dump(runs)))


def sql_runs(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        v = c.execute(sa.select(META.c.value).where(sa.and_(META.c.tenant_id == tenant, META.c.key == "sql"))).scalar()
    return _load(v, []) or []


def profiles(engine: sa.engine.Engine, tenant: str, cfg: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Etkin okurların profil + kanal başına son izin durumu. Okuma turu ya da birleştirme olunca yenilenir."""
    ensure(engine)
    cfg = cfg or settings()
    st = stamp(engine, tenant)
    ck = (id(engine), tenant)
    with _cache_lock:
        hit = _cache.get(ck)
        if hit and hit[0] == st and st is not None:
            return hit[1]
    with engine.connect() as c:
        rows = list(c.execute(active_stmt(tenant)))
        ev: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in c.execute(consents_stmt(tenant)):
            ev[e.reader_id].append({"channel": e.channel, "status": e.status, "source": e.source, "at": e.at})
    today = date.today()
    out = []
    for r in rows:
        cons = {ch: final_consent(ev.get(r.reader_id, []), ch, cfg["okSources"])[0] for ch in CHANNELS + ("kvkk",)}
        attrs = _load(r.attrs_json, {})
        out.append({
            "id": r.reader_id, "sources": _load(r.sources_json, {}), "city": r.city, "gender": r.gender,
            "birthYear": r.birth_year, "age": (today.year - r.birth_year) if r.birth_year else None,
            "minor": bool(r.is_minor), "firstSeen": _utc(r.first_seen), "lastTouch": _utc(r.last_touch),
            "interests": [i.get("ad") for i in _load(r.interests_json, []) if i.get("ad")], "attrs": attrs,
            "events": r.event_count or 0, "consent": cons,
        })
    with _cache_lock:
        _cache[ck] = (st, out)
    return out


def invalidate(engine: sa.engine.Engine, tenant: str) -> None:
    with engine.begin() as c:
        _stamp(c, tenant)


# ------------------------------------------------------------------ özet ve tazelik


def sources_state(engine: sa.engine.Engine, tenant: str, cfg: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    ensure(engine)
    cfg = cfg or settings()
    stale_before = _now() - timedelta(hours=cfg["staleHours"])
    with engine.connect() as c:
        rows = list(c.execute(sync_stmt(tenant)))
    out = []
    for r in rows:
        if r.source == "_tur":
            continue
        at = _utc(r.at)
        err_at = _utc(r.error_at)
        failing = bool(r.error) and (at is None or (err_at and err_at >= at))
        out.append({"source": r.source, "label": SOURCE_LABELS.get(r.source, _SYNC_LABELS.get(r.source, r.source)),
                    "at": _iso(at), "rows": r.rows, "error": r.error if failing else None,
                    "stale": at is None or at < stale_before, "failing": failing})
    order = list(SOURCE_LABELS) + list(_SYNC_LABELS)
    return sorted(out, key=lambda x: order.index(x["source"]) if x["source"] in order else 99)


_SYNC_LABELS = {"iys": "İYS günlüğü", "iys_alan": "İYS alanları", "etkinlik": "CRM etkinlik katılımı",
                "ilgi": "CRM uzmanlık alanı", "katki": "Esere katkı verenler", "kampanya": "CRM kampanyaları",
                "etiket": "CRM seçim listeleri"}


def last_run(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(SYNC).where(sa.and_(SYNC.c.tenant_id == tenant, SYNC.c.source == "_tur"))).first()
    if not r:
        return {"at": None, "stats": {}}
    return {"at": _iso(r.at), "stats": _load(r.stats_json, {})}


def overview(engine: sa.engine.Engine, tenant: str, cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Özet: yalnız sayılar. Kişi adı yok."""
    cfg = cfg or settings()
    profs = profiles(engine, tenant, cfg)
    run = last_run(engine, tenant)
    by_source: Counter = Counter()
    link_counts: Counter = Counter()
    consent: dict[str, Counter] = {ch: Counter() for ch in CHANNELS + ("kvkk",)}
    reach: Counter = Counter()
    reasons: dict[str, Counter] = {ch: Counter() for ch in CHANNELS}
    multi = minors = shared = 0
    for p in profs:
        for s, n in p["sources"].items():
            by_source[s] += 1
            link_counts[s] += n
        if len(p["sources"]) > 1 or sum(p["sources"].values()) > 1:
            multi += 1
        minors += int(p["minor"])
        shared += int("ortak_iletisim" in p["attrs"].get("uyari", []))
        for ch in consent:
            consent[ch][p["consent"][ch]] += 1
        for ch in CHANNELS:
            ok, why = exportable(p, ch, cfg)
            if ok:
                reach[ch] += 1
            else:
                reasons[ch][why] += 1
    with engine.connect() as c:
        pending = c.execute(pending_stmt(tenant)).scalar() or 0
        keys = {k: n for k, n in c.execute(keys_stmt(tenant))}
    total_links = sum(link_counts.values())
    return {
        "readers": len(profs), "records": total_links, "multiSource": multi,
        "duplicateRate": round(1 - len(profs) / total_links, 4) if total_links else None,
        "bySource": [{"source": s, "label": SOURCE_LABELS.get(s, s), "readers": by_source[s], "records": link_counts[s]}
                     for s in SOURCE_LABELS if by_source[s] or link_counts[s]],
        "consent": {ch: {st: consent[ch][st] for st in ("izinli", "ret", "bilinmiyor")} for ch in consent},
        "reach": {ch: reach[ch] for ch in CHANNELS},
        "notReachable": {ch: dict(reasons[ch]) for ch in CHANNELS},
        "minors": minors, "sharedContact": shared, "pendingCandidates": pending,
        "distinctEmails": keys.get("e", 0), "distinctPhones": keys.get("p", 0),
        "run": run, "sources": sources_state(engine, tenant, cfg),
        "rules": {"requireKvkk": cfg["requireKvkk"], "minorAge": cfg["minorAge"], "minorExport": cfg["minorExport"],
                  "okSources": cfg["okSources"], "exportEnabled": cfg["exportEnabled"]},
    }


# ------------------------------------------------------------------ okur kartı, arama, KVKK başvurusu


def reader_row(engine: sa.engine.Engine, tenant: str, reader_id: str) -> Any:
    with engine.connect() as c:
        r = c.execute(reader_stmt(tenant, reader_id)).first()
    if not r:
        raise ReadersError("Okur bulunamadı.", 404)
    return r


def links_of(engine: sa.engine.Engine, tenant: str, reader_ids: Iterable[str]) -> list[Any]:
    ids = sorted(set(reader_ids))
    out: list[Any] = []
    with engine.connect() as c:
        for i in range(0, len(ids), 500):                     # parça parça (parametre sınırı); sonuç kesilmez
            out += list(c.execute(links_stmt(tenant, ids[i:i + 500])))
    return out


def _history_ids(engine: sa.engine.Engine, tenant: str, reader_id: str) -> list[str]:
    """Okur + ona birleşmiş eski okurlar (olay ve dışa aktarım geçmişi için)."""
    with engine.connect() as c:
        rows = list(c.execute(sa.select(READERS.c.reader_id, READERS.c.merged_into).where(
            sa.and_(READERS.c.tenant_id == tenant, READERS.c.status == "birlesti"))))
    children: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r.merged_into:
            children[r.merged_into].append(r.reader_id)
    out, stack = [], [reader_id]
    while stack:
        x = stack.pop()
        if x in out:
            continue
        out.append(x)
        stack.extend(children.get(x, []))
    return out


def card(engine: sa.engine.Engine, tenant: str, reader_id: str, cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Okur kartı (kişisel alan yok): kaynaklar, izinler (kaynak + tarih), ilgi alanları, zaman çizelgesi."""
    cfg = cfg or settings()
    r = reader_row(engine, tenant, reader_id)
    if r.status == "birlesti" and r.merged_into:
        return {"redirect": r.merged_into}
    from semantic_bridge import readers_segments as seg

    links = links_of(engine, tenant, [reader_id])
    hist = _history_ids(engine, tenant, reader_id)
    with engine.connect() as c:
        cons = list(c.execute(reader_consents_stmt(tenant, reader_id)))
        evs = list(c.execute(reader_events_stmt(tenant, hist)))
        cands = list(c.execute(reader_candidates_stmt(tenant, reader_id)))
    ev_dicts = [{"channel": x.channel, "status": x.status, "source": x.source, "at": x.at} for x in cons]
    consents = {}
    for ch in CHANNELS + ("kvkk",):
        st, og, at = final_consent(ev_dicts, ch, cfg["okSources"])
        consents[ch] = {"status": st, "label": STATUS_LABELS[st], "source": og, "sourceLabel": ORIGIN_LABELS.get(og or ""),
                        "at": _iso(at), "evidence": [
                            {"status": x.status, "source": x.source, "sourceLabel": ORIGIN_LABELS.get(x.source, x.source),
                             "at": _iso(x.at), "record": SOURCE_LABELS.get(x.link_source or "", x.link_source),
                             "detail": x.detail} for x in sorted(cons, key=lambda y: _utc(y.at) or _now()) if x.channel == ch]}
    timeline: list[dict[str, Any]] = []
    for l in links:
        a = _load(l.attrs_json, {})
        form = ", ".join(a.get("form_tipi", []) + a.get("katilim_kaynagi", []))
        timeline.append({"at": _iso(l.created_at), "kind": "kayit",
                         "text": f"{SOURCE_LABELS.get(l.source, l.source)} kaydı açıldı" + (f" ({form})" if form else "")})
        if a.get("etkinlik"):
            timeline.append({"at": a.get("son_etkinlik"), "kind": "etkinlik",
                             "text": f"CRM'de {a['etkinlik']} etkinlik katılımı (son)"})
    for x in cons:
        timeline.append({"at": _iso(x.at), "kind": "izin",
                         "text": f"{CHANNEL_LABELS.get(x.channel, x.channel)}: {STATUS_LABELS.get(x.status, x.status)} "
                                 f"({ORIGIN_LABELS.get(x.source, x.source)})"})
    for e in evs:
        timeline.append({"at": _iso(e.at), "kind": "etkinlik", "text": f"Etkinlik: {e.label or 'katılım'} (dosya yüklemesi)"})
    for x in seg.exports_of_readers(engine, tenant, hist):
        timeline.append({"at": x["at"], "kind": "disa_aktarim",
                         "text": f"«{x['segment']}» listesinde dışa aktarıldı ({x['channelLabel']}; amaç: {x['purpose']})"})
    timeline.sort(key=lambda t: t["at"] or "", reverse=True)
    profile = next((p for p in profiles(engine, tenant, cfg) if p["id"] == reader_id), None)
    segs = seg.segments_containing(engine, tenant, profile, cfg) if profile else []
    return {
        "id": r.reader_id, "status": r.status, "birthYear": r.birth_year,
        "age": (date.today().year - r.birth_year) if r.birth_year else None, "city": r.city, "gender": r.gender,
        "minor": bool(r.is_minor), "firstSeen": _iso(r.first_seen), "lastTouch": _iso(r.last_touch),
        "interests": _load(r.interests_json, []), "attrs": _load(r.attrs_json, {}), "events": r.event_count or 0,
        "sources": [{"source": l.source, "label": SOURCE_LABELS.get(l.source, l.source), "rule": l.match_rule,
                     "decidedBy": l.decided_by, "created": _iso(l.created_at)} for l in links],
        "consents": consents, "timeline": timeline, "segments": segs, "pendingCandidates": len(cands),
        "exportable": {ch: exportable(profile, ch, cfg)[0] for ch in CHANNELS} if profile else {},
    }


def by_hash(engine: sa.engine.Engine, tenant: str, kind: str, h: str) -> list[str]:
    with engine.connect() as c:
        return sorted({r.reader_id for r in c.execute(sa.select(KEYS.c.reader_id).where(
            sa.and_(KEYS.c.tenant_id == tenant, KEYS.c.kind == kind, KEYS.c.hash == h)))})


def readers_for_hashes(engine: sa.engine.Engine, tenant: str, hashes: Iterable[str]) -> dict[str, list[str]]:
    """Özet → okurlar (toplu; parça parça sorgulanır, kesilmez)."""
    hs = sorted({h for h in hashes if h})
    out: dict[str, set[str]] = defaultdict(set)
    with engine.connect() as c:
        for i in range(0, len(hs), 500):
            for r in c.execute(sa.select(KEYS.c.hash, KEYS.c.reader_id).where(sa.and_(
                    KEYS.c.tenant_id == tenant, KEYS.c.hash.in_(hs[i:i + 500])))):
                out[r.hash].add(r.reader_id)
    return {h: sorted(v) for h, v in out.items()}


def readers_for_links(engine: sa.engine.Engine, tenant: str, keys: Iterable[tuple[str, str]]) -> list[str]:
    """(kaynak, kimlik) → okurlar."""
    want = set(keys)
    ids = sorted({sid for _s, sid in want})
    out: set[str] = set()
    with engine.connect() as c:
        for i in range(0, len(ids), 500):
            for r in c.execute(sa.select(LINKS.c.source, LINKS.c.source_id, LINKS.c.reader_id).where(sa.and_(
                    LINKS.c.tenant_id == tenant, LINKS.c.source_id.in_(ids[i:i + 500])))):
                if (r.source, r.source_id) in want:
                    out.add(r.reader_id)
    return sorted(out)


def search_ids(engine: sa.engine.Engine, tenant: str, q: str) -> tuple[list[str], str]:
    """E-posta, cep telefonu ya da okur numarasıyla kesin arama (özet üzerinden). Ada göre arama API'de, yetkiyle."""
    q = (q or "").strip()
    if not q:
        return [], "bos"
    if "@" in q:
        h = email_key(q)
        return (by_hash(engine, tenant, "e", h) if h else []), "eposta"
    if norm_phone(q):
        return by_hash(engine, tenant, "p", phone_key(q)), "telefon"
    if re.fullmatch(r"OK[0-9A-Fa-f]{6,18}", q):
        with engine.connect() as c:
            rows = [r.reader_id for r in c.execute(sa.select(READERS.c.reader_id).where(sa.and_(
                READERS.c.tenant_id == tenant, READERS.c.reader_id.like(q.upper() + "%"))))]
        return rows, "numara"
    return [], "ad"


def summaries(engine: sa.engine.Engine, tenant: str, ids: list[str], cfg: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    cfg = cfg or settings()
    want = set(ids)
    byid = {p["id"]: p for p in profiles(engine, tenant, cfg) if p["id"] in want}
    out = []
    for i in ids:
        p = byid.get(i)
        if not p:
            continue
        out.append({"id": i, "sources": [SOURCE_LABELS.get(s, s) for s in p["sources"]], "city": p["city"],
                    "age": p["age"], "minor": p["minor"], "consent": p["consent"], "lastTouch": _iso(p["lastTouch"])})
    return out


# ------------------------------------------------------------------ belirsiz eşleşme kuyruğu


def candidates(engine: sa.engine.Engine, tenant: str, status: str = "bekliyor", page: int = 0, size: int = 50,
               cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = cfg or settings()
    ensure(engine)
    q = candidates_stmts(tenant, status, page, size)
    with engine.connect() as c:
        total = c.execute(q["say"]).scalar() or 0
        rows = list(c.execute(q["sayfa"]))
    ids = sorted({x for r in rows for x in (r.a_reader, r.b_reader)})
    s = {x["id"]: x for x in summaries(engine, tenant, ids, cfg)}
    items = [{"id": r.id, "a": s.get(r.a_reader, {"id": r.a_reader}), "b": s.get(r.b_reader, {"id": r.b_reader}),
              "features": _load(r.features_json, {}), "score": r.score, "status": r.status, "decidedBy": r.decided_by,
              "decidedAt": _iso(r.decided_at), "note": r.note, "reasons": _reasons(_load(r.features_json, {}))}
             for r in rows]
    return {"items": items, "total": total, "page": page, "pageSize": size}


def _reasons(f: dict[str, Any]) -> list[str]:
    out = []
    if f.get("ad") == "ayni":
        out.append("Ad ve soyad aynı")
    if f.get("il") == "ayni":
        out.append("İl aynı")
    if f.get("dogum_yili") == "ayni":
        out.append("Doğum yılı aynı")
    elif f.get("dogum_yili") == "bilinmiyor":
        out.append("Doğum yılı birinde yok")
    out.append("E-posta ve telefon farklı (kesin birleşmedi)")
    return out


def decide_candidate(engine: sa.engine.Engine, tenant: str, cid: str, decision: str, user: str,
                     note: Optional[str] = None) -> dict[str, Any]:
    """«ayni» iki okuru hemen birleştirir (bağlar, anahtarlar, izin kanıtları, olaylar taşınır); «farkli» kaydedilir."""
    if decision not in ("ayni", "farkli"):
        raise ReadersError("Karar «ayni» ya da «farkli» olmalı.")
    ensure(engine)
    now = _now()
    with engine.begin() as c:
        r = c.execute(sa.select(CANDIDATES).where(sa.and_(CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.id == cid))).first()
        if not r:
            raise ReadersError("Aday bulunamadı.", 404)
        if r.status != "bekliyor":
            raise ReadersError("Bu çift için karar zaten verilmiş.", 409)
        c.execute(CANDIDATES.update().where(CANDIDATES.c.id == cid).values(
            status=decision, decided_by=user, decided_at=now, note=(note or None) and note[:500]))
        if decision == "farkli":
            return {"id": cid, "status": decision}
        keep, drop = sorted((r.a_reader, r.b_reader))
        rows = {x.reader_id: x for x in c.execute(sa.select(READERS).where(sa.and_(
            READERS.c.tenant_id == tenant, READERS.c.reader_id.in_([keep, drop]))))}
        if len(rows) != 2 or any(x.status != "aktif" for x in rows.values()):
            raise ReadersError("Okurlardan biri artık etkin değil; kaynaklar yeniden okununca çift yenilenir.", 409)
        a, b = rows[keep], rows[drop]
        # Kararın kayıt düzeyindeki izi: iki okurun temsilci kaydı. Sonraki okumalar birleşmeyi bunlarla kurar.
        reps = []
        for rid in (keep, drop):
            l = c.execute(sa.select(LINKS.c.source, LINKS.c.source_id).where(sa.and_(
                LINKS.c.tenant_id == tenant, LINKS.c.reader_id == rid)).order_by(LINKS.c.source, LINKS.c.source_id)).first()
            if l:
                reps.append([l.source, l.source_id])
        feats = _load(r.features_json, {})
        feats["baglar"] = reps
        c.execute(CANDIDATES.update().where(CANDIDATES.c.id == cid).values(features_json=_dump(feats)))
        for t in (LINKS, KEYS, CONSENTS, EVENTS):
            c.execute(t.update().where(sa.and_(t.c.tenant_id == tenant, t.c.reader_id == drop)).values(reader_id=keep))
        c.execute(LINKS.update().where(sa.and_(LINKS.c.tenant_id == tenant, LINKS.c.reader_id == keep))
                  .values(match_rule=sa.case((LINKS.c.match_rule == "tek", "manual"), else_=LINKS.c.match_rule)))
        c.execute(LINKS.update().where(sa.and_(LINKS.c.tenant_id == tenant, LINKS.c.reader_id == keep,
                                               LINKS.c.match_rule == "manual")).values(decided_by=user, decided_at=now))
        merged = _combine(a, b)
        c.execute(READERS.update().where(READERS.c.reader_id == keep).values(**merged, updated_at=now))
        c.execute(READERS.update().where(READERS.c.reader_id == drop).values(status="birlesti", merged_into=keep, updated_at=now))
        # Artık geçersiz olan bekleyen adaylar (aynı okur çifti ya da düşen okurla eşleşenler yeniden değerlendirilir).
        for x in c.execute(sa.select(CANDIDATES).where(sa.and_(CANDIDATES.c.tenant_id == tenant, CANDIDATES.c.status == "bekliyor",
                                                              sa.or_(CANDIDATES.c.a_reader == drop, CANDIDATES.c.b_reader == drop)))):
            other = x.b_reader if x.a_reader == drop else x.a_reader
            if other == keep:
                c.execute(CANDIDATES.update().where(CANDIDATES.c.id == x.id).values(status="gecersiz"))
            else:
                lo, hi = sorted((keep, other))
                c.execute(CANDIDATES.update().where(CANDIDATES.c.id == x.id).values(a_reader=lo, b_reader=hi))
        _stamp(c, tenant)
    return {"id": cid, "status": decision, "reader": keep, "mergedFrom": drop}


def _combine(a: Any, b: Any) -> dict[str, Any]:
    def mn(x, y):
        xs = [v for v in (_utc(x), _utc(y)) if v]
        return min(xs) if xs else None

    def mx(x, y):
        xs = [v for v in (_utc(x), _utc(y)) if v]
        return max(xs) if xs else None
    attrs = _load(a.attrs_json, {})
    for k, vs in _load(b.attrs_json, {}).items():
        attrs[k] = sorted(set(attrs.get(k, [])) | set(vs))
    ints = {i["ad"].casefold(): i for i in _load(a.interests_json, []) + _load(b.interests_json, [])}
    srcs = Counter(_load(a.sources_json, {}))
    srcs.update(_load(b.sources_json, {}))
    ys = [y for y in (a.birth_year, b.birth_year) if y]
    if len(ys) == 2 and abs(ys[0] - ys[1]) >= 12:
        attrs["uyari"] = sorted(set(attrs.get("uyari", [])) | {"ortak_iletisim"})
    return {"email_hash": a.email_hash or b.email_hash, "phone_hash": a.phone_hash or b.phone_hash,
            "birth_year": a.birth_year or b.birth_year, "city": a.city or b.city, "gender": a.gender or b.gender,
            "is_minor": bool(a.is_minor or b.is_minor), "first_seen": mn(a.first_seen, b.first_seen),
            "last_touch": mx(a.last_touch, b.last_touch), "interests_json": _dump(list(ints.values())),
            "attrs_json": _dump(attrs), "sources_json": _dump(dict(srcs)),
            "event_count": (a.event_count or 0) + (b.event_count or 0)}


# ------------------------------------------------------------------ Diğer modüller için (H3, M37, M24, M35)


def resolve_reader(engine: sa.engine.Engine, tenant: str, *, email: Any = None, phone: Any = None) -> Optional[str]:
    """E-posta ya da telefona göre etkin okur kimliği (yoksa None). Ham değer saklanmaz, yalnız özetle aranır."""
    for kind, h in (("e", email_key(email) if email else None), ("p", phone_key(phone) if phone else None)):
        if h:
            ids = by_hash(engine, tenant, kind, h)
            if ids:
                return _alive_id(engine, tenant, ids[0])
    return None


def _alive_id(engine: sa.engine.Engine, tenant: str, rid: str) -> Optional[str]:
    seen: set[str] = set()
    while rid and rid not in seen:
        seen.add(rid)
        r = reader_row(engine, tenant, rid)
        if r.status == "aktif":
            return rid
        rid = r.merged_into if r.status == "birlesti" else None
    return None


def consents_of(engine: sa.engine.Engine, tenant: str, reader_ids: Iterable[str],
                cfg: Optional[dict[str, Any]] = None) -> dict[str, dict[str, str]]:
    """Okur → {kanal: izinli|ret|bilinmiyor}. Dışa aktarım kararı için `exportable` kullanılır."""
    want = set(reader_ids)
    return {p["id"]: dict(p["consent"]) for p in profiles(engine, tenant, cfg) if p["id"] in want}
