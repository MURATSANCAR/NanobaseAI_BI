"""M44 Lojistik ve kargo yönetimi: günlük hat, gönderi kartı, firma karnesi, mutabakat, Zeki AI taslak ve karar kaydı.

Kaynaklar yalnız okunur (CRM sipariş/sevkiyat/kargo kaydı, Logo sevk ve kargo faturası; ayrıntı `shipping_sources.py`).
Portal kargo firmasına, CRM'e, Logo'ya ve T-soft'a hiçbir şey yazmaz; etiket basmaz, gönderi iptal etmez, müşteriye mesaj
göndermez (taslak üretir, gönderimi insan kendi e-postasından yapar). Portalın kendi kayıtları `semantic_shipping_*`:

- `semantic_shipping_classes` — entegrasyon hata mesajının Zeki AI sınıfı (mesaj metni başına bir kez; `QueuedLlm.choose`).
- `semantic_shipping_decisions` — kurye / bölge / sözleşme kararı (K3; öneri gerekçesi, karar insanda).
- `semantic_shipping_drafts` — gecikme / özür / iade mesajı taslağı (K2; kişisel veri modele gitmez).
- `semantic_shipping_settings` — ekrandan verilen iş eşikleri (teslim bekleyen N gün, kutulandı N gün, il hedef süreleri)
  ve zamanlayıcının son koşu günleri.

**Termin tutulmuyor** (iş kararı 2026-09-20): «geç teslim» oranı uydurulmaz. Ölçülen: sipariş → sevk → teslim süreleri,
teslim bekleyen gönderinin yaşı ve kullanıcının il için verdiği hedef süreyi aşan pay (hedef yoksa hesaplanmaz).
0 satır «gecikme yok» diye sunulmaz; kaynağın veri sonu her ekranda yazılır.

**Rakamı model üretmez:** sayılar SQL/Python'dan gelir. Model yalnız (1) hata mesajını kapalı kümeye sınıflar, (2) verilen
olgulardan taslak ya da gerekçe özeti yazar; metinde olgularda olmayan bir sayı geçerse model metni atılır, kural metni
kullanılır.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import math
import re
import statistics
import threading
import time
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import shipping_sources as src

log = logging.getLogger("semantic.shipping")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

CLASSES = sa.Table(
    "semantic_shipping_classes", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("mesaj_hash", sa.String(64), primary_key=True),
    sa.Column("siparis_id", sa.String(40)),          # ilk görülen sipariş (bilgi)
    sa.Column("firma", sa.String(40)),
    sa.Column("sinif", sa.String(60), nullable=False),
    sa.Column("olasilik", sa.Float),
    sa.Column("marj", sa.Float),
    sa.Column("yontem", sa.String(16)),
    sa.Column("model_tarihi", sa.DateTime(timezone=True), nullable=False),
)

DECISIONS = sa.Table(
    "semantic_shipping_decisions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(16), nullable=False),              # kurye | bolge | sozlesme
    sa.Column("kapsam_json", sa.Text, nullable=False),
    sa.Column("gerekce", sa.Text),
    sa.Column("model_ozet", sa.Text),
    sa.Column("karar", sa.Text, nullable=False),
    sa.Column("karar_veren", sa.String(120), nullable=False),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
)

DRAFTS = sa.Table(
    "semantic_shipping_drafts", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("siparis_id", sa.String(40), nullable=False, index=True),
    sa.Column("siparis_no", sa.String(80)),
    sa.Column("tur", sa.String(16), nullable=False),              # gecikme | ozur | iade
    sa.Column("metin", sa.Text, nullable=False),
    sa.Column("kaynak", sa.String(10), nullable=False),           # zeki | kural
    sa.Column("yazan", sa.String(120), nullable=False),
    sa.Column("durum", sa.String(12), nullable=False),            # taslak | kullanildi
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
)

SETTINGS = sa.Table(
    "semantic_shipping_settings", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("anahtar", sa.String(60), primary_key=True),
    sa.Column("deger", sa.Text, nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
)

#: Ağır CRM okumalarının anlık görüntüsü (hız, 2026-09-29). Günlük hat, teslim bekleyen, firma karnesi aynı altı okumadan
#: gelir (kargo firmaları, gönderi kaydı, entegrasyon hatası, takipsiz sevk, kutulanmış sipariş, sevk sayısı); zamanlayıcı
#: (`timas-shipping.timer`, 15 dk) bunları okuyup buraya yazar, ekran önce bellekten, yoksa buradan okur, o da yoksa ya da
#: `SHIPPING_SNAPSHOT_MAX_MIN` dakikadan eskiyse CRM'e gider (ve buraya yazar). `deger` okumanın dönüşünün kendisidir
#: (tür etiketli JSON: tarih, ondalık, kimlik aynen geri gelir; rakam değişmez), `sorgular` o okumada ÇALIŞAN CRM metinleri
#: (sorgu bilgisinde köken). Kişisel kolon okuyan sorgu (alıcı, teslim alan) burada hiç yoktur.
SNAPSHOTS = sa.Table(
    "semantic_shipping_snapshots", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("anahtar", sa.String(300), primary_key=True),
    sa.Column("deger", sa.Text, nullable=False),
    sa.Column("sorgular", sa.Text, nullable=False),
    sa.Column("alindi", sa.DateTime(timezone=True), nullable=False),
    sa.Column("sure_ms", sa.Integer),
)

ERROR_CLASSES = ["Adres bilgisi", "Telefon bilgisi", "Desi, ağırlık ya da koli", "Kimlik doğrulama ya da yetki",
                 "Servis kapalı ya da zaman aşımı", "Mükerrer gönderi", "Diğer"]
UNSURE = "Belirsiz"
DECISION_TYPES = {"kurye": "Kurye firması", "bolge": "Bölge kuralı", "sozlesme": "Sözleşme / fiyat"}
DRAFT_TYPES = {"gecikme": "Gecikme bilgisi", "ozur": "Özür", "iade": "İade yönlendirme"}
DRAFT_STATES = {"taslak": "Taslak", "kullanildi": "Kullanıldı"}
GROUPS = {"firma": "Kargo firması", "sehir": "Alıcı şehri", "sube": "Çıkış şubesi", "firma-sehir": "Firma × şehir"}
AGE_BUCKETS = ((0, 2, "0–2 gün"), (3, 5, "3–5 gün"), (6, 14, "6–14 gün"), (15, 30, "15–30 gün"), (31, None, "30+ gün"))
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORTS = {"hatalar": "Entegrasyon hataları", "takipsiz": "Takip numarasız sevk", "kutulandi": "Kutulandı, sevk edilmedi",
           "bekleyen": "Teslim bekleyen gönderiler", "firmalar": "Kargo firma karnesi", "mutabakat": "Kargo mutabakatı"}

_lock = threading.Lock()
_ready: set[int] = set()


class ShippingError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    key = id(engine)
    with _lock:
        if key in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(key)


# ------------------------------------------------------------------ ayarlar


def _split(raw: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,;\n]", raw or "") if x.strip()]


def _codes(raw: str, default: tuple[int, ...]) -> tuple[int, ...]:
    out = tuple(int(x) for x in _split(raw) if re.fullmatch(r"-?\d{1,12}", x))
    return out or default


def _int(raw: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(str(raw).strip())))
    except (TypeError, ValueError):
        return default


def _float(raw: Any, default: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(str(raw).strip().replace(",", "."))))
    except (TypeError, ValueError):
        return default


def _hhmm(raw: str, default: str) -> str:
    return raw.strip() if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", (raw or "").strip()) else default


def fold(s: Any) -> str:
    """Karşılaştırma anahtarı: Türkçe harfler sadeleşir, büyük harf, boşluklar teke iner."""
    t = str(s or "").replace("İ", "I").replace("ı", "i").upper()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


def parse_carrier_codes(raw: str) -> dict[str, list[str]]:
    """`ARAS KARGO=320.01.001,320.01.002;MNG KARGO=320.01.003` → {fold(firma): [cari kodları]}."""
    out: dict[str, list[str]] = {}
    for part in re.split(r"[;\n]", raw or ""):
        if "=" not in part:
            continue
        name, codes = part.split("=", 1)
        key = fold(name)
        cl = [c.strip() for c in codes.split(",") if c.strip()]
        if key and cl:
            out.setdefault(key, []).extend(cl)
    return out


def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    """Yönetim ekranı > ortam > varsayılan. Ölçülmemiş her varsayım burada ayardır, kodda sabit değil."""
    def c(key: str, default: str) -> str:
        try:
            v = conf(key, default)
        except TypeError:
            v = conf(key)
        return default if v in (None, "") else str(v)

    return {
        "shippedStatuses": _codes(c("SHIPPING_SHIPPED_STATUSES", "100000000,100000015"), (100000000, 100000015)),
        "untrackedStatuses": _codes(c("SHIPPING_UNTRACKED_STATUSES", "100000000"), (100000000,)),
        "untrackedExcludeTypes": _codes(c("SHIPPING_UNTRACKED_EXCLUDE_TYPES", ""), ()),
        "okValues": {fold(x) for x in _split(c("SHIPPING_INTEGRATION_OK_VALUES",
                                                 "başarılı,basarili,success,successful,ok,true,1,evet"))},
        "windowDays": _int(c("SHIPPING_WINDOW_DAYS", "30"), 30, 1, 3650),
        "dateFormats": _split(c("SHIPPING_CARGO_DATE_FORMATS",
                                "%d.%m.%Y,%d.%m.%Y %H:%M:%S,%d.%m.%Y %H:%M,%d/%m/%Y,%Y-%m-%d,%Y-%m-%d %H:%M:%S,%Y%m%d")),
        "returnNo": {fold(x) for x in _split(c("SHIPPING_RETURN_NO_VALUES", "hayır,hayir,yok,0,false,-,normal,iade değil"))},
        "codNo": {fold(x) for x in _split(c("SHIPPING_COD_NO_VALUES", "hayır,hayir,yok,0,false,-"))},
        "carrierCodes": parse_carrier_codes(c("SHIPPING_LOGO_CARRIER_CODES", "")),
        "carrierHints": _split(c("SHIPPING_LOGO_CARRIER_HINTS", "KARGO,KURYE,LOJİSTİK,EXPRESS")),
        "staleDays": _int(c("SHIPPING_STALE_DAYS", "3"), 3, 0, 365),
        "waitingDays": _int(c("SHIPPING_WAITING_DAYS", "5"), 5, 1, 365),
        "boxedDays": _int(c("SHIPPING_BOXED_DAYS", "2"), 2, 0, 365),
        "dailyAt": _hhmm(c("SHIPPING_DAILY_AT", "06:45"), "06:45"),
        "weeklyAt": _hhmm(c("SHIPPING_WEEKLY_AT", "08:00"), "08:00"),
        "dailyTo": [x for x in _split(c("SHIPPING_DAILY_TO", "")) if "@" in x],
        "weeklyTo": [x for x in _split(c("SHIPPING_WEEKLY_TO", "")) if "@" in x],
        "monthlyTo": [x for x in _split(c("SHIPPING_MONTHLY_TO", "")) if "@" in x],
        "classifyMinProb": _float(c("SHIPPING_CLASSIFY_MIN_PROB", "0.70"), 0.70, 0.0, 1.0),
        "classifyMinMargin": _float(c("SHIPPING_CLASSIFY_MIN_MARGIN", "0.30"), 0.30, 0.0, 1.0),
        "classifyBudgetSec": _int(c("SHIPPING_CLASSIFY_BUDGET_SEC", "600"), 600, 10, 7200),
        "snapshotMaxMin": _int(c("SHIPPING_SNAPSHOT_MAX_MIN", "45"), 45, 0, 1440),
        "schema": c("CRM_SCHEMA", "Timas_MSCRM.dbo"),
    }


OPS_KEYS = ("bekleyenGun", "kutuluGun", "bolgeHedef")


def ops_stmt(tenant: str) -> Any:
    """İş eşikleri okuması (uç ve sorgu bilgisi aynı ifade)."""
    return sa.select(SETTINGS).where(SETTINGS.c.tenant_id == tenant)


def ops_settings(engine: sa.engine.Engine, tenant: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Ekrandan verilen iş eşikleri; kayıt yoksa yönetim ayarındaki varsayılan."""
    with engine.connect() as c:
        rows = {r.anahtar: r for r in c.execute(ops_stmt(tenant))}
    def val(k: str) -> Any:
        r = rows.get(k)
        if r is None:
            return None
        try:
            return json.loads(r.deger)
        except ValueError:
            return None
    hedef = val("bolgeHedef")
    return {
        "bekleyenGun": _int(val("bekleyenGun"), cfg["waitingDays"], 1, 365) if val("bekleyenGun") is not None else cfg["waitingDays"],
        "kutuluGun": _int(val("kutuluGun"), cfg["boxedDays"], 0, 365) if val("kutuluGun") is not None else cfg["boxedDays"],
        "bolgeHedef": {str(k): int(v) for k, v in (hedef or {}).items() if isinstance(v, (int, float)) and 0 < v <= 365},
        "guncelleyen": {k: rows[k].guncelleyen for k in OPS_KEYS if k in rows},
    }


def save_ops_settings(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any],
                      cfg: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    before = ops_settings(engine, tenant, cfg)
    new: dict[str, Any] = {}
    if "bekleyenGun" in body:
        new["bekleyenGun"] = _positive_int(body["bekleyenGun"], "Teslim bekleyen gün", 1, 365)
    if "kutuluGun" in body:
        new["kutuluGun"] = _positive_int(body["kutuluGun"], "Kutulandı bekleyen gün", 0, 365)
    if "bolgeHedef" in body:
        h = body["bolgeHedef"]
        if not isinstance(h, dict):
            raise ShippingError("İl hedefleri {il: gün} biçiminde olmalı.")
        clean: dict[str, int] = {}
        for k, v in h.items():
            name = re.sub(r"\s+", " ", str(k or "")).strip()
            if not name or len(name) > 60:
                raise ShippingError("İl adı boş ya da çok uzun.")
            clean[name] = _positive_int(v, f"{name} hedef süresi", 1, 365)
        new["bolgeHedef"] = clean
    if not new:
        raise ShippingError("Değiştirilecek ayar yok.")
    diff = {k: {"once": before[k], "sonra": v} for k, v in new.items() if before.get(k) != v}
    now = _now()
    with engine.begin() as c:
        for k, v in new.items():
            c.execute(SETTINGS.delete().where(sa.and_(SETTINGS.c.tenant_id == tenant, SETTINGS.c.anahtar == k)))
            c.execute(SETTINGS.insert().values(tenant_id=tenant, anahtar=k, deger=json.dumps(v, ensure_ascii=False),
                                               guncelleyen=user, guncelleme=now))
    return ops_settings(engine, tenant, cfg), diff


def _positive_int(v: Any, label: str, lo: int, hi: int) -> int:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        raise ShippingError(f"{label} tam sayı olmalı.") from None
    if not lo <= n <= hi:
        raise ShippingError(f"{label} {lo}–{hi} arasında olmalı.")
    return n


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> Optional[str]:
    with engine.connect() as c:
        r = c.execute(sa.select(SETTINGS.c.deger).where(sa.and_(SETTINGS.c.tenant_id == tenant, SETTINGS.c.anahtar == f"_{key}"))).first()
    return r[0] if r else None


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: str) -> None:
    with engine.begin() as c:
        c.execute(SETTINGS.delete().where(sa.and_(SETTINGS.c.tenant_id == tenant, SETTINGS.c.anahtar == f"_{key}")))
        c.execute(SETTINGS.insert().values(tenant_id=tenant, anahtar=f"_{key}", deger=value, guncelleyen="sistem", guncelleme=_now()))


# ------------------------------------------------------------------ anlık görüntü (ağır CRM okumaları)


def pack(v: Any) -> Any:
    """Okuma dönüşünü JSON'a türüyle yazılabilir biçime çevirir; `unpack(pack(v)) == v` (tarih, saat, ondalık, kimlik,
    bayt, demet dahil). Tanınmayan tür `TypeError`: görüntü yazılmaz, ekran canlı okumaya düşer (rakam bozulmaz)."""
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, datetime):
        return {"$t": "dt", "v": v.isoformat()}
    if isinstance(v, date):
        return {"$t": "d", "v": v.isoformat()}
    if isinstance(v, dtime):
        return {"$t": "tm", "v": v.isoformat()}
    if isinstance(v, Decimal):
        return {"$t": "dec", "v": str(v)}
    if isinstance(v, uuid.UUID):
        return {"$t": "uuid", "v": str(v)}
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"$t": "b64", "v": base64.b64encode(bytes(v)).decode("ascii")}
    if isinstance(v, tuple):
        return {"$t": "tup", "v": [pack(x) for x in v]}
    if isinstance(v, list):
        return [pack(x) for x in v]
    if isinstance(v, dict):
        if "$t" in v or not all(isinstance(k, str) for k in v):
            raise TypeError("Anlık görüntü: sözlük anahtarı metin değil ya da ayrılmış ad.")
        return {k: pack(x) for k, x in v.items()}
    raise TypeError(f"Anlık görüntü: {type(v).__name__} türü yazılamaz.")


def unpack(v: Any) -> Any:
    if isinstance(v, list):
        return [unpack(x) for x in v]
    if isinstance(v, dict):
        if set(v) == {"$t", "v"}:
            t, x = v["$t"], v["v"]
            if t == "dt":
                return datetime.fromisoformat(x)
            if t == "d":
                return date.fromisoformat(x)
            if t == "tm":
                return dtime.fromisoformat(x)
            if t == "dec":
                return Decimal(x)
            if t == "uuid":
                return uuid.UUID(x)
            if t == "b64":
                return base64.b64decode(x)
            if t == "tup":
                return tuple(unpack(i) for i in x)
        return {k: unpack(x) for k, x in v.items()}
    return v


def snapshot_key(key: Any) -> str:
    """Bellek anahtarı → görüntü anahtarı (okunur metin; pencere günü ve durum kodları dahil)."""
    return json.dumps(list(key) if isinstance(key, tuple) else key, ensure_ascii=False, default=str)


def snapshot_stmt(tenant: str, anahtar: str) -> Any:
    """Ekranın görüntü okuması (sorgu bilgisinde gösterilen ifadenin kendisi)."""
    return sa.select(SNAPSHOTS.c.deger, SNAPSHOTS.c.sorgular, SNAPSHOTS.c.alindi).where(
        SNAPSHOTS.c.tenant_id == tenant, SNAPSHOTS.c.anahtar == anahtar)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def snapshot_read(engine: sa.engine.Engine, tenant: str, anahtar: str, max_min: int) -> Optional[dict[str, Any]]:
    """Görüntü `max_min` dakikadan tazeyse {deger, sorgular, alindi, stmt}; yoksa ya da eskiyse None (canlı okunur)."""
    if max_min <= 0:
        return None
    stmt = snapshot_stmt(tenant, anahtar)
    with engine.connect() as c:
        r = c.execute(stmt).first()
    if r is None:
        return None
    at = _aware(r.alindi)
    if at is None or _now() - at > timedelta(minutes=max_min):
        return None
    return {"deger": unpack(json.loads(r.deger)), "sorgular": json.loads(r.sorgular or "[]"), "alindi": at, "stmt": stmt}


def snapshot_write(engine: sa.engine.Engine, tenant: str, anahtar: str, value: Any, runs: list[dict[str, Any]],
                   ms: Optional[int] = None) -> None:
    deger = json.dumps(pack(value), ensure_ascii=False)
    sorgular = json.dumps([{k: r.get(k) for k in ("name", "sql", "rows", "ms", "at", "tag")} for r in runs
                           if r.get("conn") != "portal"], ensure_ascii=False, default=str)
    cond = (SNAPSHOTS.c.tenant_id == tenant, SNAPSHOTS.c.anahtar == anahtar)
    with engine.begin() as c:
        c.execute(SNAPSHOTS.delete().where(*cond))
        c.execute(SNAPSHOTS.insert().values(tenant_id=tenant, anahtar=anahtar, deger=deger, sorgular=sorgular,
                                            alindi=_now(), sure_ms=ms))


# ------------------------------------------------------------------ küçük yardımcılar


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _r(v: Optional[float], nd: int = 2) -> Optional[float]:
    return None if v is None or not math.isfinite(v) else round(v, nd)


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _guid_key(v: Any) -> Optional[str]:
    s = src.clean(v)
    return s.lower().strip("{}") if s else None


def age_bucket(days: Optional[int]) -> Optional[str]:
    if days is None:
        return None
    for lo, hi, label in AGE_BUCKETS:
        if days >= lo and (hi is None or days <= hi):
            return label
    return AGE_BUCKETS[0][2]


def month_bounds(ay: str) -> tuple[date, date]:
    m = re.fullmatch(r"(\d{4})-(\d{2})", (ay or "").strip())
    if not m or not 1 <= int(m.group(2)) <= 12 or not 2000 <= int(m.group(1)) <= 2100:
        raise ShippingError("Ay «YYYY-AA» biçiminde olmalı.")
    y, mo = int(m.group(1)), int(m.group(2))
    start = date(y, mo, 1)
    end = date(y + (mo == 12), 1 if mo == 12 else mo + 1, 1)
    return start, end


def period(bas: str, bit: str, default_end: date, days: int = 30) -> tuple[date, date]:
    """[bas, bit] (bit dahil) → [start, end). Boşsa `default_end`'de biten son `days` gün."""
    try:
        end = date.fromisoformat(bit) + timedelta(days=1) if bit else default_end + timedelta(days=1)
        start = date.fromisoformat(bas) if bas else end - timedelta(days=days)
    except ValueError:
        raise ShippingError("Tarih «YYYY-AA-GG» biçiminde olmalı.") from None
    if start >= end:
        raise ShippingError("Başlangıç bitişten önce olmalı.")
    return start, end


# ------------------------------------------------------------------ kargo kaydı dizini (C19)


class CargoIndex:
    """Etkin kargo kayıtları, çevrilmiş sayı ve tarihlerle. Okunamayan değerler sayılır (ekranda yazılır)."""

    def __init__(self, raw: list[dict[str, Any]], cfg: dict[str, Any]):
        fmts = cfg["dateFormats"]
        self.rows: list[dict[str, Any]] = []
        self.by_tracking: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_id: dict[str, dict[str, Any]] = {}
        self.unreadable = Counter()
        names: dict[str, Counter] = defaultdict(Counter)
        for r in raw:
            rid = _guid_key(r.get("id"))
            if not rid:
                continue
            firma_raw = src.clean(r.get("firma"))
            fk = fold(firma_raw) or "BELIRTILMEMIS"
            names[fk][firma_raw or "Belirtilmemiş"] += 1
            irs_raw, tes_raw = src.clean(r.get("irs_tarihi")), src.clean(r.get("teslim_tarihi"))
            irs, tes = src.cargo_date(irs_raw, fmts), src.cargo_date(tes_raw, fmts)
            if irs_raw and irs is None:
                self.unreadable["irsTarihi"] += 1
            if tes_raw and tes is None:
                self.unreadable["teslimTarihi"] += 1
            nums = {}
            for k in ("tutar", "desi", "sevk_adeti", "agirlik"):
                raw_v = src.clean(r.get(k))
                nums[k] = src.cargo_number(raw_v)
                if raw_v and nums[k] is None:
                    self.unreadable[k] += 1
            iade_raw = src.clean(r.get("iade_durumu"))
            cod_raw = src.clean(r.get("tahsilatli"))
            cod_num = src.cargo_number(cod_raw)
            row = {
                "id": rid, "takipNo": src.clean(r.get("takip_no")), "musteriIrsNo": src.clean(r.get("musteri_irs_no")),
                "kargoIrsNo": src.clean(r.get("kargo_irs_no")), "firmaKey": fk, "cikisSube": src.clean(r.get("cikis_sube")),
                "varisSube": src.clean(r.get("varis_sube")), "sehir": src.clean(r.get("sehir")),
                "sehirKey": fold(r.get("sehir")) or "BELIRTILMEMIS", "irs": irs, "teslim": tes,
                "teslimSaati": src.clean(r.get("teslim_saati")), "iadeDurumu": iade_raw,
                "iade": bool(iade_raw) and fold(iade_raw) not in cfg["returnNo"],
                "tahsilatli": bool(cod_raw) and fold(cod_raw) not in cfg["codNo"] and (cod_num is None or cod_num > 0),
                "tahsilatTutar": cod_num if cod_num and cod_num > 0 else None,
                "tutar": nums["tutar"], "desi": nums["desi"], "sevkAdeti": nums["sevk_adeti"], "agirlik": nums["agirlik"],
                "kanal": src.clean(r.get("kanal")), "olusturma": src.crm_time(r.get("olusturma")),
            }
            row["gun"] = (tes - irs).days if (irs and tes) else None
            self.rows.append(row)
            self.by_id[rid] = row
            k = src.normal_key(row["takipNo"])
            if k:
                self.by_tracking[k].append(row)
        self.names = {k: c.most_common(1)[0][0] for k, c in names.items()}
        for row in self.rows:
            row["firma"] = self.names.get(row["firmaKey"], row["firmaKey"])
        dates = [r["irs"] for r in self.rows if r["irs"]]
        self.data_end: Optional[date] = max(dates) if dates else None
        created = [r["olusturma"] for r in self.rows if r["olusturma"]]
        self.last_created: Optional[str] = max(created) if created else None
        self.undated = sum(1 for r in self.rows if r["irs"] is None)

    def freshness(self, cfg: dict[str, Any], asof: date) -> dict[str, Any]:
        stale = self.data_end is None or (asof - self.data_end).days > cfg["staleDays"]
        return {"veriSonu": self.data_end.isoformat() if self.data_end else None, "sonKayit": self.last_created,
                "kayit": len(self.rows), "tarihsiz": self.undated, "okunamayan": dict(self.unreadable), "eski": stale,
                "not": (f"Kargo kayıtları {self.data_end.strftime('%d.%m.%Y') if self.data_end else '—'} tarihinden beri güncellenmemiş; "
                        "teslim ve iade bilgisi eksik olabilir." if stale else None)}


# ------------------------------------------------------------------ sipariş satırı


def _stage_times(r: dict[str, Any]) -> dict[str, Optional[str]]:
    return {k: src.crm_time(r.get(col)) for k, col in (
        ("siparis", "siparis_tarihi"), ("depoda", "depoda_bekliyor"), ("pusula", "pusula"), ("kutulandi", "kutulandi"),
        ("sevk", "sevk_tarihi"), ("tamamlandi", "tamamlandi"))}


def integration_failures(r: dict[str, Any], ok_values: set[str]) -> list[dict[str, Any]]:
    """Dört firmanın sonuç/mesaj alanında «başarılı» olmayan dolu değerler."""
    out = []
    for key, label in src.INTEGRATIONS:
        sonuc, mesaj = src.clean(r.get(f"{key}_sonuc")), src.clean(r.get(f"{key}_mesaj"))
        if not sonuc and not mesaj:
            continue
        if sonuc and fold(sonuc) in ok_values:
            continue
        if not sonuc and mesaj and fold(mesaj) in ok_values:
            continue
        out.append({"entegrasyon": label, "sonuc": sonuc, "mesaj": (mesaj or "")[:2000] or None,
                    "mesajHash": message_hash(label, mesaj or sonuc or "")})
    return out


def order_view(r: dict[str, Any], carriers: dict[str, dict[str, Any]], asof: date) -> dict[str, Any]:
    durum = int(r.get("durum") or 0)
    tip = int(r["tip"]) if r.get("tip") is not None else None
    fid = _guid_key(r.get("firma_id"))
    st = _stage_times(r)
    kutu_day = src.crm_day(r.get("kutulandi"))
    sevk_day = src.crm_day(r.get("sevk_tarihi"))
    sip_day = src.crm_day(r.get("siparis_tarihi"))
    return {
        "id": _guid_key(r.get("siparis_id")), "no": src.clean(r.get("siparis_no")), "tarih": st["siparis"],
        "durum": durum, "durumAdi": src.ORDER_STATUS.get(durum, f"Durum {durum}"),
        "tip": tip, "tipAdi": src.ORDER_TYPE.get(tip, f"Tip {tip}") if tip is not None else None,
        "firmaId": fid, "firma": (carriers.get(fid) or {}).get("ad") if fid else None,
        "takipNo": src.clean(r.get("takip_no")), "takipUrl": _safe_url(r.get("takip_url")),
        "etiket": bool(r.get("etiket")), "kutu": src.cargo_number(r.get("kutu")),
        "odeme": src.PAYMENT.get(int(r["odeme_sekli"])) if r.get("odeme_sekli") is not None else None,
        "musteri": src.clean(r.get("musteri")), "cariKodu": src.clean(r.get("cari_kodu")), "il": src.clean(r.get("il")),
        "asamalar": st,
        "kutulanaliGun": (asof - kutu_day).days if kutu_day and not sevk_day else None,
        "sevkeKadarGun": (sevk_day - sip_day).days if sevk_day and sip_day else None,
    }


def _safe_url(v: Any) -> Optional[str]:
    s = src.clean(v)
    return s if s and re.match(r"^https?://", s, re.I) else None


def message_hash(firma: str, text: str) -> str:
    body = re.sub(r"\s+", " ", text or "").strip()
    return hashlib.sha256((firma + "\n" + body).encode("utf-8")).hexdigest()


def sanitize_for_model(text: str) -> str:
    """Hata mesajı modele giderken: e-posta ve 5+ haneli sayı (telefon, takip, hesap no) silinir, 600 karakter."""
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[e-posta]", text or "")
    t = re.sub(r"\d[\d\s-]{4,}\d", "#", t)
    return re.sub(r"\s+", " ", t).strip()[:600]


# ------------------------------------------------------------------ günlük hat


def error_items(rows: list[dict[str, Any]], carriers: dict[str, dict[str, Any]], cfg: dict[str, Any],
                classes: dict[str, dict[str, Any]], asof: date) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        fails = integration_failures(r, cfg["okValues"])
        if not fails:
            continue
        v = order_view(r, carriers, asof)
        for f in fails:
            cls = classes.get(f["mesajHash"])
            f["sinif"] = cls["sinif"] if cls else None
            f["sinifOlasilik"] = cls["olasilik"] if cls else None
        v["hatalar"] = fails
        v["sinif"] = next((f["sinif"] for f in fails if f["sinif"]), None)
        out.append(v)
    out.sort(key=lambda x: x["tarih"] or "", reverse=True)
    return out


def untracked_items(rows: list[dict[str, Any]], carriers: dict[str, dict[str, Any]], asof: date) -> list[dict[str, Any]]:
    out = [order_view(r, carriers, asof) for r in rows]
    out.sort(key=lambda x: x["asamalar"]["sevk"] or "", reverse=True)
    return out


def boxed_items(rows: list[dict[str, Any]], carriers: dict[str, dict[str, Any]], asof: date, min_days: int) -> dict[str, Any]:
    all_ = [order_view(r, carriers, asof) for r in rows]
    all_.sort(key=lambda x: -(x["kutulanaliGun"] or 0))
    over = [x for x in all_ if (x["kutulanaliGun"] or 0) >= min_days]
    return {"items": over, "toplam": len(all_), "esikUstu": len(over), "esikGun": min_days,
            "tarihsiz": sum(1 for x in all_ if x["kutulanaliGun"] is None)}


def cargo_public(row: dict[str, Any], cost: bool) -> dict[str, Any]:
    out = {k: row[k] for k in ("id", "takipNo", "musteriIrsNo", "kargoIrsNo", "firma", "cikisSube", "varisSube", "sehir",
                               "teslimSaati", "iadeDurumu", "iade", "tahsilatli", "sevkAdeti", "kanal", "gun")}
    out["irsTarihi"] = row["irs"].isoformat() if row["irs"] else None
    out["teslimTarihi"] = row["teslim"].isoformat() if row["teslim"] else None
    if cost:
        out.update(desi=row["desi"], agirlik=row["agirlik"], tutar=row["tutar"], tahsilatTutar=row["tahsilatTutar"])
    return out


def waiting(index: CargoIndex, asof: date, min_days: int, *, firma: str = "", sehir: str = "", cost: bool = False,
            page: int = 0, size: int = 100) -> dict[str, Any]:
    """Teslim tarihi olmayan ve iade olmayan gönderiler; yaş = bugün − kargo irsaliye tarihi."""
    fk, sk = fold(firma), fold(sehir)
    rows = [r for r in index.rows if r["teslim"] is None and not r["iade"]
            and (not fk or r["firmaKey"] == fk) and (not sk or r["sehirKey"] == sk)]
    buckets = Counter()
    by_firm: dict[str, Counter] = defaultdict(Counter)
    items = []
    for r in rows:
        age = (asof - r["irs"]).days if r["irs"] else None
        b = age_bucket(age) or "Tarihsiz"
        buckets[b] += 1
        by_firm[r["firma"]][b] += 1
        if age is not None and age >= min_days:
            items.append({**cargo_public(r, cost), "yas": age})
    items.sort(key=lambda x: -(x["yas"] or 0))
    labels = [b[2] for b in AGE_BUCKETS] + ["Tarihsiz"]
    firms = sorted(({"firma": f, **{lab: c.get(lab, 0) for lab in labels}, "toplam": sum(c.values()),
                     "esikUstu": sum(1 for r in rows if r["firma"] == f and r["irs"] and (asof - r["irs"]).days >= min_days)}
                    for f, c in by_firm.items()), key=lambda x: -x["esikUstu"])
    start = max(0, page) * size
    return {"toplam": len(rows), "esikGun": min_days, "esikUstu": len(items), "kovalar": [{"kova": lab, "adet": buckets.get(lab, 0)} for lab in labels],
            "firmalar": firms, "items": items[start:start + size], "sayfa": page, "sayfaBoyu": size,
            "devami": start + size < len(items)}


# ------------------------------------------------------------------ firma karnesi


def _median(v: list[float]) -> Optional[float]:
    return float(statistics.median(v)) if v else None


def _p90(v: list[float]) -> Optional[float]:
    if not v:
        return None
    s = sorted(v)
    return float(s[min(len(s) - 1, math.ceil(0.9 * len(s)) - 1)])


def _sum(vals: Iterable[Optional[float]]) -> Optional[float]:
    xs = [x for x in vals if x is not None]
    return sum(xs) if xs else None


def scorecard(index: CargoIndex, start: date, end: date, *, group: str = "firma", sehir: str = "", firma: str = "",
              targets: Optional[dict[str, int]] = None, cost: bool = False) -> dict[str, Any]:
    """Dönemdeki (kargo irsaliye tarihi) gönderiler gruba göre: gönderi, sevk adedi, desi, tutar, desi başı ve sevk başı
    maliyet, teslim süresi (ortanca, ortalama, %90), iade oranı, teslim bekleyen; il hedefi verilmişse hedefi aşan pay."""
    if group not in GROUPS:
        raise ShippingError("Kırılım firma, sehir, sube ya da firma-sehir olmalı.")
    sk, fk = fold(sehir), fold(firma)
    tk = {fold(k): v for k, v in (targets or {}).items()}
    rows = [r for r in index.rows if r["irs"] and start <= r["irs"] < end
            and (not sk or r["sehirKey"] == sk) and (not fk or r["firmaKey"] == fk)]
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    city_names: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        city_names[r["sehirKey"]][r["sehir"] or "Belirtilmemiş"] += 1
        if group == "firma":
            key = (r["firma"],)
        elif group == "sehir":
            key = (r["sehirKey"],)
        elif group == "sube":
            key = (r["cikisSube"] or "Belirtilmemiş",)
        else:
            key = (r["firma"], r["sehirKey"])
        groups[key].append(r)
    cname = {k: c.most_common(1)[0][0] for k, c in city_names.items()}
    out = []
    for key, rs in groups.items():
        days = [float(r["gun"]) for r in rs if r["gun"] is not None and r["gun"] >= 0]
        city_key = key[-1] if group in ("sehir", "firma-sehir") else None
        target = tk.get(city_key) if city_key else None
        item: dict[str, Any] = {
            "gonderi": len(rs), "sevkAdeti": _r(_sum(r["sevkAdeti"] for r in rs)),
            "teslim": sum(1 for r in rs if r["teslim"]), "bekleyen": sum(1 for r in rs if not r["teslim"] and not r["iade"]),
            "iade": sum(1 for r in rs if r["iade"]), "tutarsiz": sum(1 for r in rs if r["gun"] is not None and r["gun"] < 0),
            "ortancaGun": _r(_median(days), 1), "ortalamaGun": _r(sum(days) / len(days) if days else None, 1), "p90Gun": _r(_p90(days), 1),
            "tahsilatli": sum(1 for r in rs if r["tahsilatli"]),
        }
        item["iadeOrani"] = _r(_div(item["iade"], item["gonderi"]), 4)
        if target:
            item["hedefGun"] = target
            item["hedefiAsan"] = sum(1 for d in days if d > target)
            item["hedefiAsanOrani"] = _r(_div(item["hedefiAsan"], len(days)), 4)
        if cost:
            tutar, desi, sevk = _sum(r["tutar"] for r in rs), _sum(r["desi"] for r in rs), _sum(r["sevkAdeti"] for r in rs)
            item.update(tutar=_r(tutar), desi=_r(desi), desiBasi=_r(_div(tutar, desi)), sevkBasi=_r(_div(tutar, sevk)),
                        gonderiBasi=_r(_div(tutar, len(rs))), tahsilatTutar=_r(_sum(r["tahsilatTutar"] for r in rs)))
        if group == "firma":
            item["firma"] = key[0]
        elif group == "sehir":
            item["sehir"] = cname.get(key[0], key[0])
        elif group == "sube":
            item["sube"] = key[0]
        else:
            item["firma"], item["sehir"] = key[0], cname.get(key[1], key[1])
        out.append(item)
    out.sort(key=lambda x: -x["gonderi"])
    total_days = [float(r["gun"]) for r in rows if r["gun"] is not None and r["gun"] >= 0]
    totals: dict[str, Any] = {"gonderi": len(rows), "teslim": sum(1 for r in rows if r["teslim"]),
                              "iade": sum(1 for r in rows if r["iade"]), "ortancaGun": _r(_median(total_days), 1)}
    if cost:
        t, d, s = _sum(r["tutar"] for r in rows), _sum(r["desi"] for r in rows), _sum(r["sevkAdeti"] for r in rows)
        totals.update(tutar=_r(t), desi=_r(d), desiBasi=_r(_div(t, d)), sevkBasi=_r(_div(t, s)))
    return {"kirilim": group, "kirilimAdi": GROUPS[group], "baslangic": start.isoformat(), "bitis": (end - timedelta(days=1)).isoformat(),
            "items": out, "toplam": totals,
            "sehirler": sorted({cname.get(r["sehirKey"], r["sehir"] or "Belirtilmemiş") for r in index.rows if r["sehir"]}),
            "firmalar": sorted({r["firma"] for r in index.rows})}


# ------------------------------------------------------------------ gönderi kartı


def timeline(order: dict[str, Any], cargo: list[dict[str, Any]]) -> list[dict[str, Any]]:
    st = order["asamalar"]
    steps = [("Sipariş", st["siparis"], "CRM"), ("Depoda bekliyor", st["depoda"], "CRM"), ("Pusula alındı", st["pusula"], "CRM"),
             ("Kutulandı", st["kutulandi"], "CRM"), ("Sevk edildi", st["sevk"], "CRM")]
    for c in cargo:
        steps.append((f"Kargo irsaliyesi ({c['firma']})", c["irsTarihi"], "Kargo kaydı"))
        if c["teslimTarihi"]:
            steps.append(("Teslim edildi", c["teslimTarihi"] + (f"T{c['teslimSaati'][:5]}" if c.get("teslimSaati") and re.match(r"^\d{2}:\d{2}", c["teslimSaati"]) else ""), "Kargo kaydı"))
        elif c["iade"]:
            steps.append((f"İade: {c['iadeDurumu']}", None, "Kargo kaydı"))
    if st["tamamlandi"]:
        steps.append(("Tamamlandı", st["tamamlandi"], "CRM"))
    out, prev = [], None
    for name, when, source in steps:
        if not when and not name.startswith("İade"):
            continue
        d = None
        if when and prev:
            try:
                d = (date.fromisoformat(when[:10]) - date.fromisoformat(prev[:10])).days
            except ValueError:
                d = None
        out.append({"asama": name, "zaman": when, "kaynak": source, "oncekindenGun": d})
        if when:
            prev = when
    return out


# ------------------------------------------------------------------ mutabakat


def reconcile(index: CargoIndex, start: date, end: date, *, carrier_codes: dict[str, list[str]],
              invoices: list[dict[str, Any]], logo_shipments: Optional[list[dict[str, Any]]],
              crm_shipments: Optional[list[dict[str, Any]]], notes: list[str]) -> dict[str, Any]:
    """Ay: CRM kargo kaydı toplamı (firma) ↔ Logo kargo faturası (eşlenen cariler); mükerrer takip no; Logo sevk ↔ CRM
    sevkiyat eşleşme oranı. Kargo kaydı tutarının KDV dahil mi hariç mi olduğu ölçülecek; Logo iki biçimde verilir."""
    rows = [r for r in index.rows if r["irs"] and start <= r["irs"] < end]
    by_firm: dict[str, dict[str, Any]] = {}
    for r in rows:
        f = by_firm.setdefault(r["firmaKey"], {"firma": r["firma"], "gonderi": 0, "tutar": 0.0, "desi": 0.0,
                                                "tutarOkunamayan": 0, "mukerrer": 0, "mukerrerTutar": 0.0})
        f["gonderi"] += 1
        if r["tutar"] is None:
            f["tutarOkunamayan"] += 1
        else:
            f["tutar"] += r["tutar"]
        f["desi"] += r["desi"] or 0.0
    seen: dict[str, int] = Counter(src.normal_key(r["takipNo"]) for r in rows if r["takipNo"])
    dup_seen: set[str] = set()
    for r in rows:
        k = src.normal_key(r["takipNo"])
        if k and seen[k] > 1:
            if k in dup_seen:
                f = by_firm[r["firmaKey"]]
                f["mukerrer"] += 1
                f["mukerrerTutar"] += r["tutar"] or 0.0
            dup_seen.add(k)
    code_to_firm = {c: fk for fk, cl in carrier_codes.items() for c in cl}
    logo_by: dict[str, dict[str, Any]] = {}
    for inv in invoices:
        fk = code_to_firm.get(str(inv.get("cari") or "").strip())
        if not fk:
            continue
        d = logo_by.setdefault(fk, {"fatura": 0, "kdvDahil": 0.0, "kdvHaric": 0.0, "cariler": set()})
        dahil = float(inv.get("kdv_dahil") or 0)
        kdv = float(inv.get("kdv") or 0)
        d["fatura"] += 1
        d["kdvDahil"] += dahil
        d["kdvHaric"] += dahil - kdv
        d["cariler"].add(str(inv.get("cari")))
    items = []
    for fk in sorted(set(by_firm) | set(logo_by) | set(carrier_codes), key=lambda k: -(by_firm.get(k, {}).get("tutar") or 0)):
        c = by_firm.get(fk, {"firma": index.names.get(fk, fk), "gonderi": 0, "tutar": 0.0, "desi": 0.0, "tutarOkunamayan": 0,
                             "mukerrer": 0, "mukerrerTutar": 0.0})
        lg = logo_by.get(fk)
        mapped = fk in carrier_codes
        items.append({
            "firma": c["firma"], "gonderi": c["gonderi"], "crmTutar": _r(c["tutar"]), "desi": _r(c["desi"]),
            "tutarOkunamayan": c["tutarOkunamayan"], "mukerrer": c["mukerrer"], "mukerrerTutar": _r(c["mukerrerTutar"]),
            "logoEslendi": mapped, "logoCariler": carrier_codes.get(fk, []),
            "logoFatura": lg["fatura"] if lg else 0, "logoKdvHaric": _r(lg["kdvHaric"]) if lg else (0.0 if mapped else None),
            "logoKdvDahil": _r(lg["kdvDahil"]) if lg else (0.0 if mapped else None),
            "farkKdvHaric": _r((lg["kdvHaric"] if lg else 0.0) - c["tutar"]) if mapped else None,
            "farkKdvDahil": _r((lg["kdvDahil"] if lg else 0.0) - c["tutar"]) if mapped else None,
        })
    sevk = None
    if logo_shipments is not None and crm_shipments is not None:
        logo_invoice_nos = {src.normal_key(s.get("fatura_no")) for s in logo_shipments if s.get("fatura_no")}
        crm_nos = [src.normal_key(s.get("fatura_no")) for s in crm_shipments]
        matched = sum(1 for n in crm_nos if n and n in logo_invoice_nos)
        unmatched = sorted({src.clean(s.get("fatura_no")) or "(fatura no boş)" for s in crm_shipments
                            if not src.normal_key(s.get("fatura_no")) or src.normal_key(s.get("fatura_no")) not in logo_invoice_nos})
        sevk = {"logoIrsaliye": len(logo_shipments), "logoFaturali": sum(1 for s in logo_shipments if s.get("fatura_no")),
                "logoSatir": int(sum(int(s.get("satir") or 0) for s in logo_shipments)),
                "logoAdet": _r(sum(float(s.get("adet") or 0) for s in logo_shipments)),
                "crmSevkiyat": len(crm_shipments), "eslesen": matched,
                "eslesmeOrani": _r(_div(matched, len(crm_shipments)), 4), "eslesmeyen": unmatched}
    return {"ay": start.strftime("%Y-%m"), "baslangic": start.isoformat(), "bitis": (end - timedelta(days=1)).isoformat(),
            "items": items, "sevk": sevk, "notlar": notes,
            "toplam": {"gonderi": sum(i["gonderi"] for i in items), "crmTutar": _r(sum(i["crmTutar"] or 0 for i in items)),
                       "logoKdvHaric": _r(sum(i["logoKdvHaric"] or 0 for i in items)),
                       "eslenmeyenFirma": sum(1 for i in items if not i["logoEslendi"] and i["gonderi"])}}


# ------------------------------------------------------------------ Zeki AI: sınıflama


def classes_stmt(tenant: str) -> Any:
    return sa.select(CLASSES).where(CLASSES.c.tenant_id == tenant)


def load_classes(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        return {r.mesaj_hash: {"sinif": r.sinif, "olasilik": r.olasilik, "yontem": r.yontem}
                for r in c.execute(classes_stmt(tenant))}


def classify_prompt(firma: str, text: str) -> str:
    return (f"Bir kargo firmasının ({firma}) gönderi oluşturma servisinden dönen hata mesajı aşağıda. Hatanın nedeni hangi "
            f"sınıfa giriyor? Mesajda açık bir işaret yoksa «Diğer»i seç.\n\nMesaj: {sanitize_for_model(text)}")


def classify_pending(engine: sa.engine.Engine, tenant: str, errors: list[dict[str, Any]],
                     choose: Optional[Callable[[str, list[str]], Any]], cfg: dict[str, Any],
                     budget_sec: Optional[float] = None) -> dict[str, Any]:
    """Önbellekte olmayan hata mesajlarını Zeki AI'a sınıflatır (mesaj başına bir kez). Model yoksa hiçbir şey yazılmaz."""
    if choose is None:
        return {"sinif": 0, "atlandi": "model yok"}
    known = load_classes(engine, tenant)
    todo: dict[str, tuple[str, str, str]] = {}
    for e in errors:
        for f in e.get("hatalar", []):
            h = f["mesajHash"]
            if h not in known and h not in todo:
                todo[h] = (f["entegrasyon"], f["mesaj"] or f["sonuc"] or "", e["id"])
    started, done, failed = time.monotonic(), 0, 0
    limit = budget_sec if budget_sec is not None else cfg["classifyBudgetSec"]
    for h, (firma, text, oid) in todo.items():
        if time.monotonic() - started > limit:
            break
        try:
            ch = choose(classify_prompt(firma, text), ERROR_CLASSES)
        except Exception as e:  # noqa: BLE001 — model şu an cevap veremiyor; sonraki tur dener
            log.warning("kargo hata sınıflaması: %s", e)
            failed += 1
            break
        ok = ch.choice is not None and ch.confident(cfg["classifyMinProb"], cfg["classifyMinMargin"])
        with engine.begin() as c:
            c.execute(CLASSES.delete().where(sa.and_(CLASSES.c.tenant_id == tenant, CLASSES.c.mesaj_hash == h)))
            c.execute(CLASSES.insert().values(tenant_id=tenant, mesaj_hash=h, siparis_id=oid, firma=firma,
                                              sinif=ch.choice if ok else UNSURE, olasilik=getattr(ch, "probability", None),
                                              marj=getattr(ch, "margin", None), yontem=getattr(ch, "method", None),
                                              model_tarihi=_now()))
        done += 1
    return {"sinif": done, "bekleyen": max(0, len(todo) - done), "hata": failed}


# ------------------------------------------------------------------ Zeki AI: taslak ve gerekçe (olgu dışı sayı yok)


def numbers_ok(text: str, facts: str) -> bool:
    """Metindeki her sayı ve tarih olgularda da geçmeli («22.09.2026» ↔ «2026-09-22»). Denetim: `zeki_text`."""
    from semantic_bridge import zeki_text as Z

    return Z.numbers_ok(text or "", facts)


def draft_facts(order: dict[str, Any], cargo: list[dict[str, Any]]) -> dict[str, Any]:
    """Modele giden olgular: sipariş no, durum, firma, aşama günleri, takip no. Müşteri adı, alıcı, adres, telefon yok."""
    st = order["asamalar"]
    last = cargo[-1] if cargo else None
    return {
        "siparisNo": order["no"], "durum": order["durumAdi"], "kargoFirmasi": order.get("firma") or (last or {}).get("firma"),
        "takipNo": order.get("takipNo") or (last or {}).get("takipNo"),
        "siparisGunu": (st["siparis"] or "")[:10] or None, "kutulanmaGunu": (st["kutulandi"] or "")[:10] or None,
        "sevkGunu": (st["sevk"] or "")[:10] or None, "kargoIrsaliyeGunu": (last or {}).get("irsTarihi"),
        "teslimGunu": (last or {}).get("teslimTarihi"), "iade": bool(last and last.get("iade")),
    }


def rule_draft(tur: str, f: dict[str, Any]) -> str:
    no, firma, takip = f["siparisNo"], f.get("kargoFirmasi") or "kargo firması", f.get("takipNo")
    track = f" Gönderi takip numaranız: {takip}." if takip else ""
    if tur == "gecikme":
        if f.get("sevkGunu"):
            return (f"Sayın müşterimiz, {no} numaralı siparişiniz {f['sevkGunu']} tarihinde {firma} ile yola çıkmıştır.{track} "
                    "Teslimatın gecikmesiyle ilgili kargo firmasıyla iletişimdeyiz; gelişme olduğunda size bilgi vereceğiz.")
        return (f"Sayın müşterimiz, {no} numaralı siparişiniz şu an «{f['durum']}» aşamasındadır. Sevk edildiğinde takip "
                "bilgisini size ileteceğiz.")
    if tur == "ozur":
        return (f"Sayın müşterimiz, {no} numaralı siparişinizin teslimatında yaşanan aksaklık için özür dileriz.{track} "
                "Konuyu yakından takip ediyoruz.")
    return (f"Sayın müşterimiz, {no} numaralı siparişiniz için iade talebinizi aldık. İade gönderimini {firma} ile yapabilirsiniz; "
            "paketin üzerine sipariş numaranızı yazmanızı rica ederiz.")


def draft_text(tur: str, facts: dict[str, Any], chat: Optional[Callable[[list[dict[str, str]]], str]]) -> tuple[str, str]:
    base = rule_draft(tur, facts)
    if chat is None:
        return base, "kural"
    fx = json.dumps(facts, ensure_ascii=False)
    try:
        text = chat([
            {"role": "system", "content": "Timaş Yayınları müşteri hizmetleri adına kısa, nazik, Türkçe müşteri mesajı yazarsın. "
                                          "Yalnız verilen olguları kullan; olgularda olmayan tarih, sayı, süre ya da söz verme yazma. "
                                          "Müşterinin adını bilmiyorsun, «Sayın müşterimiz» diye başla. En çok 5 cümle."},
            {"role": "user", "content": f"Mesaj türü: {DRAFT_TYPES[tur]}.\nOlgular (JSON): {fx}\nÖrnek kural metni: {base}"},
        ]) or ""
    except Exception as e:  # noqa: BLE001
        log.info("kargo taslağı modelden alınamadı: %s", e)
        return base, "kural"
    text = text.strip()
    if not text or len(text) > 1500 or not numbers_ok(text, fx + " " + base):
        return base, "kural"
    return text, "zeki"


def decision_summary(facts: dict[str, Any], chat: Optional[Callable[[list[dict[str, str]]], str]]) -> Optional[str]:
    """Karar gerekçesi özeti (K3): karne rakamları verilir, model 3–4 cümlede yorumlar; olgu dışı sayı varsa atılır."""
    if chat is None:
        return None
    fx = json.dumps(facts, ensure_ascii=False)
    try:
        text = (chat([
            {"role": "system", "content": "Lojistik müdürüne karar notu yazarsın. Yalnız verilen rakamları kullan, yeni sayı üretme, "
                                          "öneriyi yumuşak ver (karar insanındır). Türkçe, en çok 4 cümle."},
            {"role": "user", "content": f"Kargo firma karnesi (JSON): {fx}"},
        ]) or "").strip()
    except Exception as e:  # noqa: BLE001
        log.info("kargo karar özeti alınamadı: %s", e)
        return None
    return text if text and len(text) <= 2000 and numbers_ok(text, fx) else None


def create_draft(engine: sa.engine.Engine, tenant: str, user: str, order: dict[str, Any], tur: str, text: str,
                 kaynak: str) -> dict[str, Any]:
    if tur not in DRAFT_TYPES:
        raise ShippingError("Taslak türü gecikme, ozur ya da iade olmalı.")
    did = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(DRAFTS.insert().values(id=did, tenant_id=tenant, siparis_id=order["id"], siparis_no=order["no"], tur=tur,
                                         metin=text, kaynak=kaynak, yazan=user, durum="taslak", olusturma=_now()))
    return get_draft(engine, tenant, did)


def _draft_out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "siparisId": r.siparis_id, "siparisNo": r.siparis_no, "tur": r.tur, "turAdi": DRAFT_TYPES.get(r.tur, r.tur),
            "metin": r.metin, "kaynak": r.kaynak, "yazan": r.yazan, "durum": r.durum, "durumAdi": DRAFT_STATES.get(r.durum, r.durum),
            "olusturma": _iso(r.olusturma), "guncelleme": _iso(r.guncelleme)}


def get_draft(engine: sa.engine.Engine, tenant: str, did: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(DRAFTS).where(sa.and_(DRAFTS.c.tenant_id == tenant, DRAFTS.c.id == did))).first()
    if r is None:
        raise ShippingError("Taslak bulunamadı.", 404)
    return _draft_out(r)


def drafts_for(engine: sa.engine.Engine, tenant: str, order_id: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(DRAFTS).where(sa.and_(DRAFTS.c.tenant_id == tenant, DRAFTS.c.siparis_id == order_id))
                         .order_by(DRAFTS.c.olusturma.desc())).all()
    return [_draft_out(r) for r in rows]


def update_draft(engine: sa.engine.Engine, tenant: str, user: str, did: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    cur = get_draft(engine, tenant, did)
    vals: dict[str, Any] = {}
    if "metin" in body:
        t = str(body.get("metin") or "").strip()
        if not t or len(t) > 4000:
            raise ShippingError("Metin boş olamaz, en çok 4000 karakter.")
        vals["metin"] = t
    if "durum" in body:
        if body["durum"] not in DRAFT_STATES:
            raise ShippingError("Durum taslak ya da kullanildi olmalı.")
        vals["durum"] = body["durum"]
    if not vals:
        raise ShippingError("Değişiklik yok.")
    diff = {k: {"once": cur["metin" if k == "metin" else "durum"][:200], "sonra": str(v)[:200]} for k, v in vals.items()}
    with engine.begin() as c:
        c.execute(DRAFTS.update().where(sa.and_(DRAFTS.c.tenant_id == tenant, DRAFTS.c.id == did)).values(**vals, guncelleme=_now()))
    return get_draft(engine, tenant, did), diff


def delete_draft(engine: sa.engine.Engine, tenant: str, did: str) -> dict[str, Any]:
    cur = get_draft(engine, tenant, did)
    with engine.begin() as c:
        c.execute(DRAFTS.delete().where(sa.and_(DRAFTS.c.tenant_id == tenant, DRAFTS.c.id == did)))
    return cur


# ------------------------------------------------------------------ karar kaydı (K3)


def _decision_out(r: Any) -> dict[str, Any]:
    try:
        scope = json.loads(r.kapsam_json or "{}")
    except ValueError:
        scope = {}
    return {"id": r.id, "tur": r.tur, "turAdi": DECISION_TYPES.get(r.tur, r.tur), "kapsam": scope, "gerekce": r.gerekce,
            "modelOzet": r.model_ozet, "karar": r.karar, "kararVeren": r.karar_veren, "tarih": _iso(r.tarih)}


def list_decisions(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(DECISIONS).where(DECISIONS.c.tenant_id == tenant).order_by(DECISIONS.c.tarih.desc())).all()
    return [_decision_out(r) for r in rows]


def create_decision(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    tur = str(body.get("tur") or "")
    if tur not in DECISION_TYPES:
        raise ShippingError("Karar türü kurye, bolge ya da sozlesme olmalı.")
    karar = str(body.get("karar") or "").strip()
    if not karar or len(karar) > 4000:
        raise ShippingError("Karar metni boş olamaz (en çok 4000 karakter).")
    scope = body.get("kapsam") or {}
    if not isinstance(scope, dict):
        raise ShippingError("Kapsam {firma, sehir, baslangic, bitis} biçiminde olmalı.")
    scope = {k: str(v)[:120] for k, v in scope.items() if k in ("firma", "sehir", "baslangic", "bitis", "yeniFirma") and v}
    did = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(DECISIONS.insert().values(
            id=did, tenant_id=tenant, tur=tur, kapsam_json=json.dumps(scope, ensure_ascii=False),
            gerekce=(str(body.get("gerekce") or "").strip()[:4000] or None),
            model_ozet=(str(body.get("modelOzet") or "").strip()[:2000] or None), karar=karar, karar_veren=user, tarih=_now()))
        r = c.execute(sa.select(DECISIONS).where(DECISIONS.c.id == did)).first()
    return _decision_out(r)


def delete_decision(engine: sa.engine.Engine, tenant: str, did: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(DECISIONS).where(sa.and_(DECISIONS.c.tenant_id == tenant, DECISIONS.c.id == did))).first()
        if r is None:
            raise ShippingError("Karar kaydı bulunamadı.", 404)
        c.execute(DECISIONS.delete().where(DECISIONS.c.id == did))
    return _decision_out(r)


# ------------------------------------------------------------------ dışa aktarma ve e-posta metni


def xlsx(title: str, columns: list[tuple[str, str]], rows: list[dict[str, Any]], note: str = "") -> bytes:
    """Tek sayfalı Excel: başlık, not, tablo (bütün satırlar; tavan yok)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = re.sub(r"[\[\]:*?/\\]", " ", title)[:28] or "Liste"
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([note or f"Oluşturma: {datetime.now(TZ).strftime('%d.%m.%Y %H:%M')}"])
    ws.append([])
    ws.append([label for _, label in columns])
    for cell in ws[4]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append([_cell(r.get(k)) for k, _ in columns])
    for i, (_, label) in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(10, min(48, len(label) + 6))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell(v: Any) -> Any:
    if isinstance(v, bool):
        return "Evet" if v else "Hayır"
    if isinstance(v, (list, tuple, set)):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return v


def flatten_errors(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for i in items:
        for f in i["hatalar"]:
            out.append({**{k: i[k] for k in ("no", "tarih", "durumAdi", "tipAdi", "firma", "musteri", "cariKodu", "il", "etiket")},
                        "entegrasyon": f["entegrasyon"], "sonuc": f["sonuc"], "mesaj": f["mesaj"], "sinif": f.get("sinif")})
    return out


ERROR_COLUMNS = [("no", "Sipariş no"), ("tarih", "Sipariş zamanı"), ("durumAdi", "Durum"), ("tipAdi", "Tip"), ("firma", "Kargo firması"),
                 ("entegrasyon", "Entegrasyon"), ("sonuc", "Sonuç"), ("mesaj", "Mesaj"), ("sinif", "Zeki AI sınıfı"),
                 ("musteri", "Müşteri"), ("cariKodu", "Cari kodu"), ("il", "İl"), ("etiket", "Etiket basıldı")]
ORDER_COLUMNS = [("no", "Sipariş no"), ("tarih", "Sipariş zamanı"), ("durumAdi", "Durum"), ("tipAdi", "Tip"), ("firma", "Kargo firması"),
                 ("musteri", "Müşteri"), ("cariKodu", "Cari kodu"), ("il", "İl"), ("kutu", "Koli"), ("kutulanaliGun", "Kutulanalı gün"),
                 ("sevkeKadarGun", "Sipariş → sevk (gün)")]
WAITING_COLUMNS = [("takipNo", "Takip no"), ("musteriIrsNo", "Müşteri irsaliye no"), ("firma", "Kargo firması"), ("irsTarihi", "Kargo irsaliye"),
                   ("yas", "Bekleyen gün"), ("sehir", "Alıcı şehri"), ("cikisSube", "Çıkış şubesi"), ("varisSube", "Varış şubesi"),
                   ("kanal", "Satış kanalı"), ("tahsilatli", "Tahsilatlı")]


def scorecard_columns(group: str, cost: bool) -> list[tuple[str, str]]:
    head = {"firma": [("firma", "Kargo firması")], "sehir": [("sehir", "Alıcı şehri")], "sube": [("sube", "Çıkış şubesi")],
            "firma-sehir": [("firma", "Kargo firması"), ("sehir", "Alıcı şehri")]}[group]
    cols = head + [("gonderi", "Gönderi"), ("sevkAdeti", "Sevk adedi"), ("teslim", "Teslim"), ("bekleyen", "Bekleyen"),
                   ("ortancaGun", "Ortanca teslim (gün)"), ("ortalamaGun", "Ortalama (gün)"), ("p90Gun", "%90 (gün)"),
                   ("iade", "İade"), ("iadeOrani", "İade oranı"), ("hedefGun", "Hedef (gün)"), ("hedefiAsanOrani", "Hedefi aşan pay")]
    if cost:
        cols += [("desi", "Desi"), ("tutar", "Tutar"), ("desiBasi", "Desi başı"), ("sevkBasi", "Sevk başı"), ("gonderiBasi", "Gönderi başı")]
    return cols


RECONCILE_COLUMNS = [("firma", "Kargo firması"), ("gonderi", "Gönderi"), ("crmTutar", "Kargo kaydı tutarı"), ("tutarOkunamayan", "Tutarı okunamayan"),
                     ("mukerrer", "Mükerrer takip no"), ("mukerrerTutar", "Mükerrer tutar"), ("logoCariler", "Logo carileri"),
                     ("logoFatura", "Logo fatura"), ("logoKdvHaric", "Logo KDV hariç"), ("logoKdvDahil", "Logo KDV dahil"),
                     ("farkKdvHaric", "Fark (KDV hariç)"), ("farkKdvDahil", "Fark (KDV dahil)")]


def daily_text(o: dict[str, Any], link: str) -> str:
    lines = [f"Kargo günlük özeti — {datetime.now(TZ).strftime('%d.%m.%Y')}", "",
             f"Son {o['pencereGun']} günde sevk edilen sipariş: {o['sevk']['adet']} (bugün {o['sevk']['bugun']})",
             f"Entegrasyon hatası (takip no yok): {o['hata']}",
             f"Takip numarası olmadan sevk: {o['takipsiz']}",
             f"Kutulandı, {o['kutulandi']['esikGun']}+ gündür sevk edilmedi: {o['kutulandi']['esikUstu']} (toplam kutulanmış {o['kutulandi']['toplam']})",
             f"Teslim bekleyen ({o['bekleyen']['esikGun']}+ gün): {o['bekleyen']['esikUstu']} (toplam bekleyen {o['bekleyen']['toplam']})",
             "", f"Kargo kayıtlarının veri sonu: {o['kargoVeri']['veriSonu'] or '—'}"]
    if o["kargoVeri"].get("not"):
        lines.append(o["kargoVeri"]["not"])
    if link:
        lines += ["", f"Ekran: {link}/kargo"]
    lines += ["", "Bu e-posta yalnız iç bilgilendirmedir; kargo firmasına ya da müşteriye bir şey gönderilmedi."]
    return "\n".join(lines)


def weekly_text(card: dict[str, Any], fresh: dict[str, Any], link: str) -> str:
    lines = [f"Haftalık kargo firma karnesi — {card['baslangic']} / {card['bitis']}", ""]
    for i in card["items"]:
        parts = [f"{i['firma']}: {i['gonderi']} gönderi", f"ortanca teslim {i['ortancaGun'] if i['ortancaGun'] is not None else '—'} gün",
                 f"iade {i['iade']}"]
        if "desiBasi" in i:
            parts.append(f"desi başı {i['desiBasi'] if i['desiBasi'] is not None else '—'}")
        lines.append(" · ".join(parts))
    if not card["items"]:
        lines.append("Bu dönemde kargo kaydı yok (bu «gecikme yok» demek değildir; veri sonuna bakın).")
    lines += ["", f"Kargo kayıtlarının veri sonu: {fresh['veriSonu'] or '—'}"]
    if fresh.get("not"):
        lines.append(fresh["not"])
    if link:
        lines += ["", f"Ekran: {link}/kargo/firmalar"]
    return "\n".join(lines)


def monthly_text(rec: dict[str, Any], link: str) -> str:
    lines = [f"Kargo mutabakatı — {rec['ay']}", ""]
    for i in rec["items"]:
        if not i["logoEslendi"]:
            lines.append(f"{i['firma']}: kargo kaydı {i['crmTutar']} ({i['gonderi']} gönderi) — Logo carisi eşlenmemiş")
        else:
            lines.append(f"{i['firma']}: kargo kaydı {i['crmTutar']} · Logo KDV hariç {i['logoKdvHaric']} · fark {i['farkKdvHaric']}"
                         + (f" · mükerrer takip no {i['mukerrer']}" if i["mukerrer"] else ""))
    if rec.get("sevk"):
        s = rec["sevk"]
        lines += ["", f"Logo sevk ↔ CRM sevkiyat: {s['eslesen']}/{s['crmSevkiyat']} eşleşti"]
    for n in rec.get("notlar", []):
        lines.append(n)
    if link:
        lines += ["", f"Ekran: {link}/kargo/mutabakat?ay={rec['ay']}"]
    return "\n".join(lines)


def due(now_local: datetime, at: str, last: Optional[str], *, weekday: Optional[int] = None, monthday: Optional[int] = None) -> bool:
    """Zamanı geldi mi: saat `at`'ı geçti, bugün (hafta günü / ay günü tutuyorsa) ve bugün daha koşmadı."""
    if weekday is not None and now_local.weekday() != weekday:
        return False
    if monthday is not None and now_local.day != monthday:
        return False
    h, m = (int(x) for x in at.split(":"))
    if (now_local.hour, now_local.minute) < (h, m):
        return False
    return last != now_local.date().isoformat()
