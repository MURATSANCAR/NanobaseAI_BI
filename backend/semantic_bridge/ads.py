"""M21 Dijital pazarlama ve reklam: tablolar, hesaplar ve öneri kuralları (saf işlevler; kaynak okuması `ads_sources.py`,
uçlar `ads_api.py`).

**Veri yolu (ilk sürüm).** Reklam platformlarının kendi verisi portala API ile gelmez (hesap sahipliği ve yetki müşteriden
bekleniyor; site analitiği erişimi yok). Performans uzmanı platformun dışa aktarım dosyasını (CSV/Excel, günlük satır)
yükler; kolon eşlemesi hesap başına bir kez onaylanıp kaydedilir. Aynı kampanya-gün yeniden yüklenirse son yükleme geçerli
olur (satır `import_id`'si yeni yüklemeye geçer); bir dosyada aynı kampanya-gün birden çok satırsa (reklam grubu kırılımı)
toplanır.

**Rakamlar.** Harcama, tıklama, dönüşüm dosyadan; e-ticaret cirosu Logo'dan (kanal `CLCARD.SPECODE2`, varsayılan
`E-TICARET`; faturalı satır, iade eksi, net ciro = LINENET — M46 ile aynı tanım); stok Logo'nun güncel kopyasından
(«stok bakiyesi» ölçüsü). **Pazarlama verimi** = e-ticaret net cirosu ÷ reklam harcaması, yalnız Logo verisinin bulunduğu
günlerde (iki taraf aynı günlerle sınırlanır; satış verisi bittikten sonraki harcama verime girmez, ekranda yazılır).
Platformun kendi dönüşüm değeri «platform ROAS» diye ayrıca gösterilir; gerçek getiri diye sunulmaz.

**Dış sisteme yazma yok.** Reklam platformunda bütçe değiştirme, teklif, durdurma yapılmaz (kullanıcı kararı: ilk
sürümde otomatik dış gönderim yok). Öneriler portalda onaylanır; uzman platformda kendisi uygular ve «uygulandı» işaretler.
CRM'e, Logo'ya, T-soft'a yazılmaz; bağlar ve bütçe planı `semantic_ads_*` tablolarındadır.

**Öneri kuralları** (eşiği girilmeyen kural çalışmaz, sayı uydurulmaz):
- `stok`: kitaba bağlı, son `ADS_ACTIVE_DAYS` günde harcaması olan kampanya ve kitabın stoğu `ADS_STOCK_DAYS` günlük
  satışı karşılamıyor (ya da bakiye ≤ 0).
- `satis-disi`: kitabın CRM yayıncılık durumu satış dışı listesinde (`ADS_OFF_SALE_STATUS`) ve reklam sürüyor.
- `veri-yok`: hesabın son verisi `ADS_NO_DATA_DAYS` günden eski (son 30 günde verisi olan hesap).
- `butce`: ayın harcaması gün oranıyla ay sonuna taşındığında kanal planını `ADS_OVERSPEND_PCT` üstünde aşıyor
  (plan girilmemiş kanal için kural yok).
- `durdur`: son `ADS_PERF_WINDOW_DAYS` günde harcaması `ADS_STOP_MIN_SPEND`'i geçip dönüşümü olmayan (ya da platform
  ROAS'ı `ADS_STOP_MAX_ROAS` altında) kampanya. Eşik girilmezse kapalı.
- `kaydir`: aynı kanalda platform ROAS'ı en düşük ve en yüksek kampanya arasında oran `ADS_SHIFT_ROAS_RATIO`'yu
  geçiyor; önerilen tutar = düşük kampanyanın pencere harcaması × `ADS_SHIFT_SHARE`. `ADS_SHIFT_MIN_SPEND` girilmezse kapalı.

Durum: `yeni` → (onay yetkisi) `onaylandi` | `reddedildi`; `onaylandi` → (uzman) `uygulandi`. Uyarı türleri (stok,
satis-disi, veri-yok, butce) onay istemez: uzman doğrudan `uygulandi` ya da `reddedildi` işaretler. Koşulu kalkan
açık uyarı kendiliğinden `gecersiz` olur.
"""
from __future__ import annotations

import calendar
import json
import math
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

ACCOUNTS = sa.Table(
    "semantic_ads_accounts", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("platform", sa.String(16), nullable=False),
    sa.Column("account_label", sa.String(200), nullable=False),
    sa.Column("currency", sa.String(8), nullable=False, default="TRY"),
    sa.Column("import_mapping_json", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
CAMPAIGNS = sa.Table(
    "semantic_ads_campaigns", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("account_id", sa.String(32), nullable=False, index=True),
    sa.Column("platform_campaign_id", sa.String(120)),
    sa.Column("name_key", sa.String(400), nullable=False),              # katlanmış ad: kimliksiz dosyada eşleme anahtarı
    sa.Column("name", sa.String(400), nullable=False),
    sa.Column("status", sa.String(80)),                                  # platformun dosyadaki durum metni
    sa.Column("crm_book_id", sa.String(40)),
    sa.Column("stok_kodu", sa.String(60), index=True),
    sa.Column("book_name", sa.String(400)),
    sa.Column("series", sa.String(200)),
    sa.Column("link_status", sa.String(10), nullable=False, default="yok"),   # yok | oneri | onayli
    sa.Column("link_source", sa.String(10)),                             # elle | zeki | kod | kural
    sa.Column("link_confidence", sa.Float),
    sa.Column("link_json", sa.Text),                                     # adaylar ve model kararı
    sa.Column("link_by", sa.String(120)),
    sa.Column("link_at", sa.DateTime(timezone=True)),
    sa.Column("m15_plan_id", sa.String(24)),
    sa.Column("first_seen", sa.String(10)),
    sa.Column("last_seen", sa.String(10)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_semantic_ads_campaigns_key", "account_id", "platform_campaign_id", "name_key"),
)
DAILY = sa.Table(
    "semantic_ads_daily", _md,
    sa.Column("campaign_id", sa.String(32), primary_key=True),
    sa.Column("day", sa.String(10), primary_key=True),
    sa.Column("spend", sa.Float, nullable=False, default=0.0),
    sa.Column("impressions", sa.Float),
    sa.Column("clicks", sa.Float),
    sa.Column("conversions", sa.Float),
    sa.Column("conv_value", sa.Float),
    sa.Column("currency", sa.String(8), nullable=False, default="TRY"),
    sa.Column("import_id", sa.String(32), nullable=False, index=True),
    sa.Index("ix_semantic_ads_daily_day", "day"),
)
IMPORTS = sa.Table(
    "semantic_ads_imports", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("account_id", sa.String(32), nullable=False, index=True),
    sa.Column("file_name", sa.String(300)),
    sa.Column("file_sha", sa.String(64)),
    sa.Column("rows", sa.Integer, nullable=False, default=0),            # dosyadaki okunan veri satırı
    sa.Column("days_written", sa.Integer, nullable=False, default=0),    # yazılan kampanya-gün
    sa.Column("campaigns", sa.Integer, nullable=False, default=0),
    sa.Column("total_spend", sa.Float, nullable=False, default=0.0),     # dosyanın harcama toplamı (bütün para birimleri)
    sa.Column("totals_json", sa.Text),                                   # para birimi → toplam
    sa.Column("period_from", sa.String(10)),
    sa.Column("period_to", sa.String(10)),
    sa.Column("mapping_json", sa.Text),
    sa.Column("warnings_json", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
BUDGET = sa.Table(
    "semantic_ads_budget", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("month", sa.String(7), nullable=False),                    # YYYY-MM
    sa.Column("channel", sa.String(16), nullable=False),                 # PLATFORMS anahtarı
    sa.Column("planned", sa.Float, nullable=False),
    sa.Column("note", sa.String(500)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "month", "channel", name="uq_semantic_ads_budget"),
)
SUGGESTIONS = sa.Table(
    "semantic_ads_suggestions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kind", sa.String(12), nullable=False),
    sa.Column("dedupe_key", sa.String(200), nullable=False, index=True),
    sa.Column("campaign_id", sa.String(32)),
    sa.Column("account_id", sa.String(32)),
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("payload_json", sa.Text),
    sa.Column("reason", sa.Text, nullable=False),
    sa.Column("model_note", sa.Text),
    sa.Column("status", sa.String(12), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("decision_note", sa.String(1000)),
    sa.Column("applied_by", sa.String(120)),
    sa.Column("applied_at", sa.DateTime(timezone=True)),
)
BRIEFS = sa.Table(
    "semantic_ads_briefs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("crm_book_id", sa.String(40)),
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("book_name", sa.String(400)),
    sa.Column("request_note", sa.String(1000)),
    sa.Column("body", sa.Text),
    sa.Column("status", sa.String(14), nullable=False),                  # hazirlaniyor | taslak | onayli | hata
    sa.Column("check_json", sa.Text),
    sa.Column("error", sa.String(500)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
)
ECOM = sa.Table(
    "semantic_ads_ecom_daily", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("day", sa.String(10), primary_key=True),
    sa.Column("ciro", sa.Float, nullable=False),
    sa.Column("adet", sa.Float, nullable=False),
)
ECOM_BOOK = sa.Table(
    "semantic_ads_ecom_book", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("day", sa.String(10), primary_key=True),
    sa.Column("eticaret_ciro", sa.Float, nullable=False),
    sa.Column("eticaret_adet", sa.Float, nullable=False),
    sa.Column("toplam_ciro", sa.Float, nullable=False),
    sa.Column("toplam_adet", sa.Float, nullable=False),
)
STOCK = sa.Table(
    "semantic_ads_stock", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("bakiye", sa.Float, nullable=False),
    sa.Column("gunluk_satis", sa.Float),
    sa.Column("asof", sa.String(10)),
)
META = sa.Table(
    "semantic_ads_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(80), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

#: Kanal = reklam platformu. Platform adları müşterinin kullandığı hedeflerdir, ekranda yazılır.
PLATFORMS = {"google": "Google Ads", "meta": "Meta (Facebook, Instagram)", "tiktok": "TikTok", "pazaryeri": "Pazaryeri reklamı",
             "diger": "Diğer"}
KINDS = {"stok": "Stok bitiyor, reklam açık", "satis-disi": "Satıştan kalkmış kitaba reklam", "veri-yok": "Veri gelmedi",
         "butce": "Bütçe aşımı tahmini", "durdur": "Durdurma önerisi", "kaydir": "Bütçe kaydırma önerisi"}
#: Onay isteyen (para kararı) türler; diğerleri uyarıdır.
APPROVAL_KINDS = ("durdur", "kaydir")
STATUSES = {"yeni": "Yeni", "onaylandi": "Onaylandı", "uygulandi": "Uygulandı", "reddedildi": "Reddedildi",
            "gecersiz": "Koşulu kalktı"}
OPEN = ("yeni", "onaylandi")
LINK_STATUSES = {"yok": "Bağsız", "oneri": "Zeki AI önerdi", "onayli": "Bağlı"}
LINK_SOURCES = {"elle": "Elle", "zeki": "Zeki AI", "kod": "Stok kodu / barkod", "kural": "Ad benzerliği"}
BRIEF_STATUSES = {"hazirlaniyor": "Hazırlanıyor", "taslak": "Taslak", "onayli": "Onaylı", "hata": "Yazılamadı"}
MAIN_CURRENCY = "TRY"

_ready: set[int] = set()
_lock = threading.Lock()


class AdsError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


# ------------------------------------------------------------------ yardımcılar


def now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def loads(v: Optional[str], default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def uid() -> str:
    return uuid.uuid4().hex


_FOLD = str.maketrans("İIıŞşĞğÜüÖöÇçÂâÎîÛû", "iiissgguuooccaaiiuu")


def fold(s: Any) -> str:
    return " ".join(str(s or "").translate(_FOLD).lower().split())


def one_line(v: Any, limit: int) -> Optional[str]:
    s = " ".join(str(v or "").split())
    return s[:limit] or None


def day_of(v: Any, label: str = "Tarih") -> date:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise AdsError(f"{label} YYYY-AA-GG biçiminde olmalı.") from None


def div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or not b:
        return None
    return a / b


def r2(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(float(v), 2)


# ------------------------------------------------------------------ ayarlar


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    """Yönetim → ayarlar (`ADS_*`). Boş bırakılan eşik kuralı kapatır; sayı uydurulmaz."""

    def num(key: str, default: Optional[float]) -> Optional[float]:
        raw = (conf(key) or "").strip().replace(",", ".")
        if not raw:
            return default
        try:
            v = float(raw)
        except ValueError:
            return default
        return v if math.isfinite(v) else default

    def lst(key: str, default: str) -> list[str]:
        return [x.strip() for x in ((conf(key) or "").strip() or default).replace(";", ",").split(",") if x.strip()]

    m15 = {}
    for pair in lst("ADS_M15_CHANNEL_MAP", "google=dijital,meta=sosyal-medya,tiktok=sosyal-medya,pazaryeri=dijital,diger=dijital"):
        k, _, v = pair.partition("=")
        if k.strip() in PLATFORMS and v.strip():
            m15[k.strip()] = v.strip()
    return {
        "ecomChannels": [x.upper() for x in lst("ADS_ECOM_CHANNELS", "E-TICARET")],
        "lookbackDays": int(num("ADS_LOOKBACK_DAYS", 400) or 400),
        "velocityDays": int(num("ADS_VELOCITY_DAYS", 60) or 60),
        "stockDays": num("ADS_STOCK_DAYS", 14),
        "activeDays": int(num("ADS_ACTIVE_DAYS", 3) or 3),
        "noDataDays": int(num("ADS_NO_DATA_DAYS", 2) or 2),
        "offSaleStatus": [x.upper() for x in lst("ADS_OFF_SALE_STATUS", "YS01,YS05,YS06,YS11,YS12")],
        "overspendPct": num("ADS_OVERSPEND_PCT", 0.0),
        "perfWindowDays": int(num("ADS_PERF_WINDOW_DAYS", 14) or 14),
        "stopMinSpend": num("ADS_STOP_MIN_SPEND", None),
        "stopMaxRoas": num("ADS_STOP_MAX_ROAS", None),
        "shiftMinSpend": num("ADS_SHIFT_MIN_SPEND", None),
        "shiftRoasRatio": num("ADS_SHIFT_ROAS_RATIO", 2.0) or 2.0,
        "shiftShare": (num("ADS_SHIFT_SHARE", 20.0) or 20.0) / 100.0,
        "resuggestDays": int(num("ADS_RESUGGEST_DAYS", 7) or 7),
        "linkMinProb": num("ADS_LINK_MIN_PROB", 0.70) or 0.70,
        "linkMinMargin": num("ADS_LINK_MIN_MARGIN", 0.30) or 0.30,
        "m15Channels": m15,
        "recipients": [x for x in lst("ADS_ALERT_RECIPIENTS", "") if "@" in x],
        "dayFirst": (conf("ADS_DATE_ORDER") or "gun-ay").strip() != "ay-gun",
        "maxUploadMb": num("ADS_IMPORT_MAX_MB", 50.0) or 50.0,
        "claims": lst("MARKETING_BANNED_CLAIMS", ""),
    }


# ------------------------------------------------------------------ meta


def meta_stmt(tenant: str, key: str):
    return sa.select(META).where(META.c.tenant_id == tenant, META.c.key == key)


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(meta_stmt(tenant, key)).first()
    return {**loads(row.value_json, {}), "_at": iso(row.updated_at)} if row else {}


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: dict[str, Any]) -> None:
    with engine.begin() as c:
        cond = (META.c.tenant_id == tenant, META.c.key == key)
        if c.execute(sa.select(META.c.key).where(*cond)).first():
            c.execute(META.update().where(*cond).values(value_json=dump(value), updated_at=now()))
        else:
            c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=dump(value), updated_at=now()))


# ------------------------------------------------------------------ hesaplar


def _account(r: Any) -> dict[str, Any]:
    return {"id": r.id, "platform": r.platform, "platformAdi": PLATFORMS.get(r.platform, r.platform), "ad": r.account_label,
            "paraBirimi": r.currency, "eslem": loads(r.import_mapping_json, None), "olusturan": r.created_by,
            "olusturma": iso(r.created_at), "guncelleme": iso(r.updated_at)}


def accounts_stmts(tenant: str) -> tuple[Any, Any]:
    """(reklam hesapları, hesap başına son kampanya günü)."""
    return (sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant).order_by(ACCOUNTS.c.platform, ACCOUNTS.c.account_label),
            sa.select(CAMPAIGNS.c.account_id, sa.func.max(DAILY.c.day).label("son_gun"))
            .select_from(DAILY.join(CAMPAIGNS, CAMPAIGNS.c.id == DAILY.c.campaign_id))
            .where(CAMPAIGNS.c.tenant_id == tenant).group_by(CAMPAIGNS.c.account_id))


def list_accounts(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    aq, lq = accounts_stmts(tenant)
    with engine.connect() as c:
        rows = c.execute(aq).all()
        last = dict(c.execute(lq).all())
    return [{**_account(r), "sonGun": last.get(r.id)} for r in rows]


def get_account(engine: sa.engine.Engine, tenant: str, account_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.id == str(account_id)[:32])).first()
    if not r:
        raise AdsError("Reklam hesabı bulunamadı.", 404)
    return _account(r)


def create_account(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    platform = str(body.get("platform") or "")
    if platform not in PLATFORMS:
        raise AdsError("Platform google, meta, tiktok, pazaryeri ya da diger olmalı.")
    label = one_line(body.get("ad"), 200)
    if not label:
        raise AdsError("Hesap adı gerekli (ör. «Timaş Google Ads»).")
    cur = (one_line(body.get("paraBirimi"), 8) or MAIN_CURRENCY).upper()
    with engine.begin() as c:
        dup = c.execute(sa.select(ACCOUNTS.c.id).where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.platform == platform,
                                                       sa.func.lower(ACCOUNTS.c.account_label) == label.lower())).first()
        if dup:
            raise AdsError("Bu platformda aynı adla bir hesap zaten var.", 409)
        aid = uid()
        c.execute(ACCOUNTS.insert().values(id=aid, tenant_id=tenant, platform=platform, account_label=label, currency=cur,
                                           created_by=user, created_at=now()))
    return get_account(engine, tenant, aid)


def update_account(engine: sa.engine.Engine, tenant: str, account_id: str, body: dict[str, Any]) -> dict[str, Any]:
    acc = get_account(engine, tenant, account_id)
    vals: dict[str, Any] = {}
    if "ad" in body:
        label = one_line(body.get("ad"), 200)
        if not label:
            raise AdsError("Hesap adı boş olamaz.")
        vals["account_label"] = label
    if "paraBirimi" in body:
        vals["currency"] = (one_line(body.get("paraBirimi"), 8) or MAIN_CURRENCY).upper()
    if "eslem" in body:
        vals["import_mapping_json"] = None if body["eslem"] is None else dump(clean_mapping(body["eslem"]))
    if vals:
        with engine.begin() as c:
            c.execute(ACCOUNTS.update().where(ACCOUNTS.c.id == acc["id"]).values(**vals, updated_at=now()))
    return get_account(engine, tenant, acc["id"])


#: Dosya kolonunun karşılığı olabilecek alanlar. Zorunlu: gün, kampanya, harcama.
FIELDS = {
    "day": "Gün", "day_end": "Bitiş günü (varsa)", "campaign": "Kampanya adı", "campaign_id": "Kampanya kimliği",
    "spend": "Harcama", "impressions": "Gösterim", "clicks": "Tıklama", "conversions": "Dönüşüm",
    "conv_value": "Dönüşüm değeri", "currency": "Para birimi", "status": "Kampanya durumu",
}
REQUIRED = ("day", "campaign", "spend")


def clean_mapping(m: Any) -> dict[str, str]:
    if not isinstance(m, dict):
        raise AdsError("Kolon eşlemesi alan → kolon adı biçiminde olmalı.")
    out = {k: str(v) for k, v in m.items() if k in FIELDS and v not in (None, "")}
    missing = [FIELDS[k] for k in REQUIRED if k not in out]
    if missing:
        raise AdsError("Eşlemede eksik alan: " + ", ".join(missing) + ".")
    return out


# ------------------------------------------------------------------ içe aktarma


def _campaign_key(name: str) -> str:
    return fold(name)[:400]


def commit_import(engine: sa.engine.Engine, tenant: str, user: str, account: dict[str, Any], file_name: str, file_sha: str,
                  rows: list[dict[str, Any]], mapping: dict[str, str], warnings: list[str], read_rows: int) -> dict[str, Any]:
    """Eşlenmiş satırları yazar. `rows`: {day, campaign, campaign_id, spend, impressions, clicks, conversions,
    conv_value, currency, status}. Aynı kampanya-gün dosyada birden çok kez geçiyorsa toplanır; tabloda varsa bu yükleme
    geçerli olur."""
    if not rows:
        raise AdsError("Dosyada yazılacak satır yok.")
    agg: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in rows:
        cid = (r.get("campaign_id") or "").strip()
        key = (cid, _campaign_key(r["campaign"]) if not cid else "", r["day"])
        cur = agg.get(key)
        if cur is None:
            cur = agg[key] = {"campaign": r["campaign"], "campaign_id": cid or None, "day": r["day"], "spend": 0.0,
                              "impressions": None, "clicks": None, "conversions": None, "conv_value": None,
                              "currency": (r.get("currency") or account["paraBirimi"] or MAIN_CURRENCY).upper(),
                              "status": r.get("status")}
        elif (r.get("currency") or cur["currency"]).upper() != cur["currency"]:
            raise AdsError(f"«{r['campaign']}» kampanyasının {r['day']} günü iki farklı para biriminde; dosyayı düzeltin.")
        cur["spend"] += float(r.get("spend") or 0.0)
        for f in ("impressions", "clicks", "conversions", "conv_value"):
            if r.get(f) is not None:
                cur[f] = (cur[f] or 0.0) + float(r[f])
        if r.get("status"):
            cur["status"] = r["status"]
    iid = uid()
    days = sorted({k[2] for k in agg})
    totals: dict[str, float] = {}
    for v in agg.values():
        totals[v["currency"]] = totals.get(v["currency"], 0.0) + v["spend"]
    t = now()
    with engine.begin() as c:
        existing = c.execute(sa.select(CAMPAIGNS).where(CAMPAIGNS.c.tenant_id == tenant, CAMPAIGNS.c.account_id == account["id"])).all()
        by_id = {r.platform_campaign_id: r for r in existing if r.platform_campaign_id}
        by_name = {r.name_key: r for r in existing}
        ids: dict[tuple[str, str], str] = {}
        seen: dict[str, list[str]] = {}
        for (cid, nkey, d), v in agg.items():
            ck = (cid, nkey)
            if ck not in ids:
                row = by_id.get(cid) if cid else None
                if row is None:
                    row = by_name.get(_campaign_key(v["campaign"]))
                    if row is not None and cid and row.platform_campaign_id and row.platform_campaign_id != cid:
                        row = None          # aynı ad, başka kimlik: ayrı kampanya
                if row is None:
                    new_id = uid()
                    c.execute(CAMPAIGNS.insert().values(
                        id=new_id, tenant_id=tenant, account_id=account["id"], platform_campaign_id=cid or None,
                        name_key=_campaign_key(v["campaign"]), name=v["campaign"][:400], status=v.get("status"),
                        link_status="yok", created_at=t))
                    ids[ck] = new_id
                    made = SimpleNamespace(id=new_id, platform_campaign_id=cid or None, name_key=_campaign_key(v["campaign"]))
                    by_name[made.name_key] = made
                    if cid:
                        by_id[cid] = made
                else:
                    ids[ck] = row.id
                    upd: dict[str, Any] = {"name": v["campaign"][:400], "name_key": _campaign_key(v["campaign"])}
                    if cid and not row.platform_campaign_id:
                        upd["platform_campaign_id"] = cid
                    if v.get("status"):
                        upd["status"] = str(v["status"])[:80]
                    c.execute(CAMPAIGNS.update().where(CAMPAIGNS.c.id == row.id).values(**upd))
            camp = ids[ck]
            seen.setdefault(camp, []).append(d)
            c.execute(DAILY.delete().where(DAILY.c.campaign_id == camp, DAILY.c.day == d))
            c.execute(DAILY.insert().values(campaign_id=camp, day=d, spend=round(v["spend"], 4), impressions=v["impressions"],
                                            clicks=v["clicks"], conversions=v["conversions"], conv_value=v["conv_value"],
                                            currency=v["currency"], import_id=iid))
        for camp, ds in seen.items():
            row = c.execute(sa.select(CAMPAIGNS.c.first_seen, CAMPAIGNS.c.last_seen).where(CAMPAIGNS.c.id == camp)).first()
            first = min([x for x in (row.first_seen, min(ds)) if x])
            last = max([x for x in (row.last_seen, max(ds)) if x])
            c.execute(CAMPAIGNS.update().where(CAMPAIGNS.c.id == camp).values(first_seen=first, last_seen=last))
        c.execute(IMPORTS.insert().values(
            id=iid, tenant_id=tenant, account_id=account["id"], file_name=(file_name or "")[:300], file_sha=file_sha,
            rows=read_rows, days_written=len(agg), campaigns=len(seen), total_spend=round(sum(totals.values()), 4),
            totals_json=dump({k: round(v, 4) for k, v in totals.items()}), period_from=days[0], period_to=days[-1],
            mapping_json=dump(mapping), warnings_json=dump(warnings), created_by=user, created_at=t))
        c.execute(ACCOUNTS.update().where(ACCOUNTS.c.id == account["id"]).values(import_mapping_json=dump(mapping), updated_at=t))
    return import_row(engine, tenant, iid)


def _import(r: Any, acc: Optional[dict[str, Any]] = None, live: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {"id": r.id, "hesapId": r.account_id, "hesap": (acc or {}).get("ad"), "platform": (acc or {}).get("platform"),
            "dosya": r.file_name, "satir": r.rows, "kampanyaGun": r.days_written, "kampanya": r.campaigns,
            "toplamHarcama": r.total_spend, "paraBirimiToplam": loads(r.totals_json, {}), "bas": r.period_from, "bit": r.period_to,
            "eslem": loads(r.mapping_json, {}), "uyarilar": loads(r.warnings_json, []), "yukleyen": r.created_by,
            "zaman": iso(r.created_at), **({"gecerliKampanyaGun": live.get("n", 0), "gecerliHarcama": live.get("spend", 0.0)} if live is not None else {})}


def import_stmts(tenant: str, iid: str) -> tuple[Any, Any, Any]:
    """(yükleme, yüklemenin hâlâ geçerli kampanya-gün satırı ve harcaması, hesabı)."""
    iid = str(iid)[:32]
    return (sa.select(IMPORTS).where(IMPORTS.c.tenant_id == tenant, IMPORTS.c.id == iid),
            sa.select(sa.func.count(), sa.func.coalesce(sa.func.sum(DAILY.c.spend), 0.0)).where(DAILY.c.import_id == iid),
            sa.select(ACCOUNTS).where(ACCOUNTS.c.id.in_(sa.select(IMPORTS.c.account_id).where(IMPORTS.c.id == iid))))


def import_row(engine: sa.engine.Engine, tenant: str, iid: str) -> dict[str, Any]:
    iq, lq, aq = import_stmts(tenant, iid)
    with engine.connect() as c:
        r = c.execute(iq).first()
        if not r:
            raise AdsError("Yükleme bulunamadı.", 404)
        live = c.execute(lq).first()
        acc = c.execute(aq).first()
    return _import(r, _account(acc) if acc else None, {"n": int(live[0] or 0), "spend": float(live[1] or 0.0)})


def imports_stmts(tenant: str) -> tuple[Any, Any, Any]:
    """(yüklemeler, hesaplar, yükleme başına geçerli kampanya-gün satırı ve harcama)."""
    return (sa.select(IMPORTS).where(IMPORTS.c.tenant_id == tenant).order_by(IMPORTS.c.created_at.desc()),
            sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant),
            sa.select(DAILY.c.import_id, sa.func.count(), sa.func.sum(DAILY.c.spend)).group_by(DAILY.c.import_id))


def list_imports(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    iq, aq, lq = imports_stmts(tenant)
    with engine.connect() as c:
        rows = c.execute(iq).all()
        accs = {r.id: _account(r) for r in c.execute(aq).all()}
        live = {r[0]: {"n": int(r[1] or 0), "spend": float(r[2] or 0.0)} for r in c.execute(lq).all()}
    return [_import(r, accs.get(r.account_id), live.get(r.id, {"n": 0, "spend": 0.0})) for r in rows]


def delete_import(engine: sa.engine.Engine, tenant: str, iid: str) -> dict[str, Any]:
    """Yüklemeyi geri alır: bu yüklemenin hâlâ geçerli olan kampanya-gün satırları silinir (sonraki yüklemenin yazdığı
    satırlara dokunulmaz). Hiç satırı kalmayan kampanya bağlarıyla birlikte silinmez; kaydı kalır."""
    imp = import_row(engine, tenant, iid)
    with engine.begin() as c:
        n = c.execute(DAILY.delete().where(DAILY.c.import_id == imp["id"])).rowcount
        c.execute(IMPORTS.delete().where(IMPORTS.c.id == imp["id"]))
    return {**imp, "silinenKampanyaGun": n}


# ------------------------------------------------------------------ kampanyalar


def _campaign(r: Any, acc: Optional[dict[str, Any]]) -> dict[str, Any]:
    return {"id": r.id, "hesapId": r.account_id, "hesap": (acc or {}).get("ad"), "platform": (acc or {}).get("platform"),
            "platformAdi": PLATFORMS.get((acc or {}).get("platform") or "", "—"), "platformKimlik": r.platform_campaign_id,
            "ad": r.name, "durum": r.status, "kitapId": r.crm_book_id, "stokKodu": r.stok_kodu, "kitapAdi": r.book_name,
            "seri": r.series, "bag": r.link_status, "bagAdi": LINK_STATUSES.get(r.link_status, r.link_status),
            "bagKaynak": r.link_source, "bagKaynakAdi": LINK_SOURCES.get(r.link_source or "", None), "bagGuven": r.link_confidence,
            "bagAyrinti": loads(r.link_json, None), "bagYapan": r.link_by, "bagZamani": iso(r.link_at), "m15PlanId": r.m15_plan_id,
            "ilkGun": r.first_seen, "sonGun": r.last_seen}


def campaigns_stmts(tenant: str) -> tuple[Any, Any]:
    """(hesaplar, kampanyalar ve kitap bağları)."""
    return sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant), sa.select(CAMPAIGNS).where(CAMPAIGNS.c.tenant_id == tenant)


def campaign_rows(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    aq, cq = campaigns_stmts(tenant)
    with engine.connect() as c:
        accs = {r.id: _account(r) for r in c.execute(aq).all()}
        rows = c.execute(cq).all()
    return [_campaign(r, accs.get(r.account_id)) for r in rows]


def get_campaign(engine: sa.engine.Engine, tenant: str, cid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(CAMPAIGNS).where(CAMPAIGNS.c.tenant_id == tenant, CAMPAIGNS.c.id == str(cid)[:32])).first()
        if not r:
            raise AdsError("Kampanya bulunamadı.", 404)
        a = c.execute(sa.select(ACCOUNTS).where(ACCOUNTS.c.id == r.account_id)).first()
    return _campaign(r, _account(a) if a else None)


def set_link(engine: sa.engine.Engine, tenant: str, user: str, cid: str, body: dict[str, Any],
             book_of: Callable[[str], Optional[dict[str, Any]]]) -> dict[str, Any]:
    """Kampanya ↔ kitap bağı. `{"stokKodu": …}` elle bağlar; `{"onayla": true}` Zeki AI önerisini onaylar;
    `{"kaldir": true}` bağı kaldırır; `{"seri": …}` ve `{"m15PlanId": …}` serbest alanlardır. CRM'e yazılmaz."""
    cur = get_campaign(engine, tenant, cid)
    vals: dict[str, Any] = {}
    if body.get("kaldir"):
        vals.update(crm_book_id=None, stok_kodu=None, book_name=None, link_status="yok", link_source=None, link_confidence=None,
                    link_by=user, link_at=now(), m15_plan_id=None)
    elif body.get("stokKodu"):
        book = book_of(str(body["stokKodu"]).strip())
        if not book:
            raise AdsError("Bu stok kodunda CRM'de etkin kitap kartı yok.", 404)
        vals.update(crm_book_id=book.get("kitapId"), stok_kodu=book["stokKodu"], book_name=book.get("ad"), link_status="onayli",
                    link_source="elle", link_confidence=None, link_by=user, link_at=now())
    elif body.get("onayla"):
        if cur["bag"] != "oneri" or not cur["stokKodu"]:
            raise AdsError("Onaylanacak bir kitap önerisi yok.", 409)
        vals.update(link_status="onayli", link_by=user, link_at=now())
    if "seri" in body:
        vals["series"] = one_line(body.get("seri"), 200)
    if "m15PlanId" in body:
        vals["m15_plan_id"] = one_line(body.get("m15PlanId"), 24)
    if not vals:
        raise AdsError("Değişiklik yok.")
    with engine.begin() as c:
        c.execute(CAMPAIGNS.update().where(CAMPAIGNS.c.id == cur["id"]).values(**vals))
    return get_campaign(engine, tenant, cur["id"])


def save_link_suggestion(engine: sa.engine.Engine, cid: str, result: dict[str, Any]) -> None:
    """Eşleştirme sonucunu yazar; elle ya da onaylı bağa dokunmaz."""
    with engine.begin() as c:
        r = c.execute(sa.select(CAMPAIGNS.c.link_status).where(CAMPAIGNS.c.id == cid)).first()
        if not r or r.link_status == "onayli":
            return
        book = result.get("book")
        vals: dict[str, Any] = {"link_json": dump({k: v for k, v in result.items() if k != "book"})}
        if book:
            vals.update(crm_book_id=book.get("kitapId"), stok_kodu=book["stokKodu"], book_name=book.get("ad"),
                        link_status="onayli" if result.get("source") == "kod" else "oneri", link_source=result.get("source"),
                        link_confidence=result.get("probability"), link_by="Zeki AI" if result.get("source") == "zeki" else "sistem",
                        link_at=now())
        else:
            vals.update(crm_book_id=None, stok_kodu=None, book_name=None, link_status="yok", link_source=None, link_confidence=None)
        c.execute(CAMPAIGNS.update().where(CAMPAIGNS.c.id == cid).values(**vals))


# ------------------------------------------------------------------ kampanya ↔ kitap eşleştirme (kural kısmı)

#: Kampanya adlarında kitap adı olmayan sözcükler (platform, kampanya tipi, hedefleme jargonu).
STOPWORDS = frozenset(fold(x) for x in """
kampanya kampanyasi reklam reklami reklamı arama search display pmax performance max video youtube shopping alisveris
instagram facebook meta tiktok google ads adwords story reels feed post boost trafik traffic donusum dönüşüm conversion
satis satış sales lead remarketing retargeting yeniden hedefleme lookalike benzer kitle audience test genel brand marka
timas timaş yayinlari yayınları yayinevi yayınevi kitap kitabi kitabı kitaplari kitapları yeni ve ile icin için the and for
ocak subat şubat mart nisan mayis mayıs haziran temmuz agustos ağustos eylul eylül ekim kasim kasım aralik aralık
tr turkiye türkiye ist istanbul ankara izmir mobil mobile desktop web site
""".split())
_TOKEN = re.compile(r"[a-z0-9]+")


def tokens(s: Any) -> list[str]:
    return [t for t in _TOKEN.findall(fold(s)) if len(t) >= 3 and t not in STOPWORDS and not t.isdigit()]


def code_match(name: str, books: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Kampanya adında kitabın stok kodu ya da EAN-13 barkodu geçiyorsa kesin bağ (kural; model sorulmaz)."""
    raw = str(name or "")
    digits = set(re.findall(r"(?<!\d)\d{13}(?!\d)", raw))
    for b in books:
        ean = re.sub(r"[^0-9]", "", str(b.get("ean") or ""))
        if ean and ean in digits:
            return b
    for b in books:
        code = str(b.get("stokKodu") or "")
        if len(code) >= 5 and re.search(r"(?<![0-9A-Za-z.])" + re.escape(code) + r"(?![0-9A-Za-z])", raw):
            return b
    return None


def candidates(name: str, books: list[dict[str, Any]], index: Optional[dict[str, list[int]]] = None, k: int = 8) -> list[dict[str, Any]]:
    """Ad benzerliği adayları: kampanya adıyla ortak sözcük oranı (kitap adının sözcüklerine göre). Kesin değil; modele
    ya da insana aday listesi olarak gider."""
    want = set(tokens(name))
    if not want:
        return []
    pool: Iterable[int]
    if index is not None:
        hit: set[int] = set()
        for t in want:
            hit.update(index.get(t, ()))
        pool = hit
    else:
        pool = range(len(books))
    scored = []
    for i in pool:
        b = books[i]
        bt = set(tokens(b.get("ad")))
        if not bt:
            continue
        shared = want & bt
        if not shared:
            continue
        score = len(shared) / len(bt)
        if score < 0.5:
            continue
        scored.append((score, len(shared), -len(bt), b))
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return [{**x[3], "skor": round(x[0], 3), "ortak": x[1]} for x in scored[:k]]


def book_index(books: list[dict[str, Any]]) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = {}
    for i, b in enumerate(books):
        for t in set(tokens(b.get("ad"))):
            idx.setdefault(t, []).append(i)
    return idx


NONE_CHOICE = "Hiçbiri (bu kampanya bu kitaplardan birinin reklamı değil)"


def link_prompt(campaign: dict[str, Any], cands: list[dict[str, Any]]) -> tuple[str, list[str]]:
    choices = [f"{c.get('ad')} — {c.get('yazar') or 'yazar yok'} (stok kodu {c['stokKodu']})" for c in cands] + [NONE_CHOICE]
    prompt = (f"Timaş Yayınları'nın reklam kampanyası: «{campaign['ad']}» (platform: {campaign.get('platformAdi') or '—'}).\n"
              "Kampanya adları çoğu zaman kitap adını kısaltarak ya da hedefleme bilgisiyle birlikte yazılır. Bu kampanya aşağıdaki "
              "kitaplardan hangisinin reklamı? Emin değilsen «Hiçbiri»ni seç.")
    return prompt, choices


def match_campaign(campaign: dict[str, Any], books: list[dict[str, Any]], index: dict[str, list[int]], llm: Any,
                   st: dict[str, Any]) -> dict[str, Any]:
    """Tek kampanya için bağ önerisi. Sıra: kod/barkod (kesin) → ad benzerliği adayları → Zeki AI kapalı seçim
    (aday listesinden biri ya da «Hiçbiri», olasılıkla). Model yoksa tek ve tam eşleşen aday «kural» olarak önerilir."""
    hit = code_match(campaign["ad"], books)
    if hit:
        return {"book": hit, "source": "kod", "probability": 1.0, "adaylar": []}
    cands = candidates(campaign["ad"], books, index)
    brief = [{"stokKodu": c["stokKodu"], "ad": c.get("ad"), "yazar": c.get("yazar"), "skor": c["skor"]} for c in cands]
    if not cands:
        return {"book": None, "source": None, "adaylar": [], "not": "Ad benzerliğiyle aday bulunamadı."}
    if llm is not None and hasattr(llm, "choose"):
        prompt, choices = link_prompt(campaign, cands)
        ch = llm.choose(prompt, choices)
        info = {"olasilik": ch.probability, "marj": ch.margin, "yontem": ch.method}
        if ch.choice and ch.choice != NONE_CHOICE and ch.confident(st["linkMinProb"], st["linkMinMargin"]):
            return {"book": cands[ch.index], "source": "zeki", "probability": ch.probability, "adaylar": brief, "model": info}
        return {"book": None, "source": None, "adaylar": brief, "model": info,
                "not": "Zeki AI emin değil; aday listesinden elle seçin." if ch.choice != NONE_CHOICE else "Zeki AI adaylardan birini seçmedi."}
    full = [c for c in cands if c["skor"] >= 1.0]
    if len(full) == 1:
        return {"book": full[0], "source": "kural", "probability": None, "adaylar": brief,
                "not": "Kitap adının bütün sözcükleri kampanya adında geçiyor (model bağlı değil)."}
    return {"book": None, "source": None, "adaylar": brief, "not": "Model bağlı değil; aday listesinden elle seçin."}


# ------------------------------------------------------------------ dönem toplamları


def _sum_rows(rows: Iterable[Any]) -> dict[str, Any]:
    out = {"harcama": 0.0, "gosterim": None, "tiklama": None, "donusum": None, "donusumDegeri": None}
    for r in rows:
        out["harcama"] += float(r.spend or 0.0)
        for src, key in (("impressions", "gosterim"), ("clicks", "tiklama"), ("conversions", "donusum"), ("conv_value", "donusumDegeri")):
            v = getattr(r, src)
            if v is not None:
                out[key] = (out[key] or 0.0) + float(v)
    return out


def metrics(tot: dict[str, Any]) -> dict[str, Any]:
    """Türetilen oranlar: TBM = harcama ÷ tıklama, TO = tıklama ÷ gösterim, platform ROAS = dönüşüm değeri ÷ harcama."""
    return {**{k: r2(v) if isinstance(v, float) else v for k, v in tot.items()},
            "tbm": r2(div(tot["harcama"], tot["tiklama"])), "tiklamaOrani": div(tot["tiklama"], tot["gosterim"]),
            "platformRoas": div(tot["donusumDegeri"], tot["harcama"]) if tot["harcama"] else None}


def daily_stmt(tenant: str, frm: date, to: date, platform: str = ""):
    """Dönemdeki kampanya-gün satırları (yüklenen reklam raporlarından), kanal ve kitap bağıyla."""
    j = DAILY.join(CAMPAIGNS, CAMPAIGNS.c.id == DAILY.c.campaign_id).join(ACCOUNTS, ACCOUNTS.c.id == CAMPAIGNS.c.account_id)
    cond = [CAMPAIGNS.c.tenant_id == tenant, DAILY.c.day >= frm.isoformat(), DAILY.c.day <= to.isoformat()]
    if platform:
        cond.append(ACCOUNTS.c.platform == platform)
    return sa.select(DAILY, ACCOUNTS.c.platform, CAMPAIGNS.c.stok_kodu, CAMPAIGNS.c.link_status, CAMPAIGNS.c.account_id) \
        .select_from(j).where(*cond)


def daily_rows(engine: sa.engine.Engine, tenant: str, frm: date, to: date, platform: str = "") -> list[Any]:
    with engine.connect() as c:
        return c.execute(daily_stmt(tenant, frm, to, platform)).all()


def ecom_total_stmt(tenant: str, frm: date, to: date):
    return sa.select(sa.func.sum(ECOM.c.ciro), sa.func.sum(ECOM.c.adet), sa.func.count()) \
        .where(ECOM.c.tenant_id == tenant, ECOM.c.day >= frm.isoformat(), ECOM.c.day <= to.isoformat())


def ecom_by_day_stmt(tenant: str, frm: date, to: date):
    return sa.select(ECOM.c.day, ECOM.c.ciro).where(ECOM.c.tenant_id == tenant, ECOM.c.day >= frm.isoformat(),
                                                    ECOM.c.day <= to.isoformat())


def book_sales_stmts(tenant: str, codes: Iterable[str], frm: date, to: date) -> list[Any]:
    """Kitap başına e-ticaret ve toplam satış (500'lük stok kodu parçaları; her parça ayrı okuma)."""
    want = sorted({c for c in codes if c})
    return [sa.select(ECOM_BOOK.c.stok_kodu, sa.func.sum(ECOM_BOOK.c.eticaret_ciro), sa.func.sum(ECOM_BOOK.c.eticaret_adet),
                      sa.func.sum(ECOM_BOOK.c.toplam_ciro), sa.func.sum(ECOM_BOOK.c.toplam_adet))
            .where(ECOM_BOOK.c.tenant_id == tenant, ECOM_BOOK.c.stok_kodu.in_(want[i:i + 500]),
                   ECOM_BOOK.c.day >= frm.isoformat(), ECOM_BOOK.c.day <= to.isoformat())
            .group_by(ECOM_BOOK.c.stok_kodu) for i in range(0, len(want), 500)]


def stock_stmt(tenant: str):
    return sa.select(STOCK).where(STOCK.c.tenant_id == tenant)


def ecom_total(engine: sa.engine.Engine, tenant: str, frm: date, to: date) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(ecom_total_stmt(tenant, frm, to)).first()
    return {"ciro": r2(float(r[0])) if r[0] is not None else 0.0, "adet": float(r[1] or 0.0), "gun": int(r[2] or 0)}


def ecom_by_day(engine: sa.engine.Engine, tenant: str, frm: date, to: date) -> dict[str, float]:
    with engine.connect() as c:
        return {r.day: float(r.ciro) for r in c.execute(ecom_by_day_stmt(tenant, frm, to)).all()}


def book_sales(engine: sa.engine.Engine, tenant: str, codes: Iterable[str], frm: date, to: date) -> dict[str, dict[str, float]]:
    want = sorted({c for c in codes if c})
    if not want:
        return {}
    out: dict[str, dict[str, float]] = {}
    with engine.connect() as c:
        for q in book_sales_stmts(tenant, want, frm, to):
            rows = c.execute(q).all()
            for r in rows:
                out[r[0]] = {"eticaretCiro": round(float(r[1] or 0), 2), "eticaretAdet": float(r[2] or 0),
                             "toplamCiro": round(float(r[3] or 0), 2), "toplamAdet": float(r[4] or 0)}
    return out


def velocity(engine: sa.engine.Engine, tenant: str, codes: Iterable[str], end: date, days: int) -> dict[str, float]:
    """Günlük satış hızı: son `days` günün (Logo verisinin bittiği güne kadar) bütün kanallardaki net adedi ÷ gün.
    Kitap önbelleğinden okunur; yıl sınırını aşan pencere iki firmanın satırlarını birlikte sayar."""
    frm = end - timedelta(days=days - 1)
    sales = book_sales(engine, tenant, codes, frm, end)
    return {code: max(0.0, v["toplamAdet"]) / days for code, v in sales.items()}


def stock_of(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(stock_stmt(tenant)).all()
    return {r.stok_kodu: stock_view(r.bakiye, r.gunluk_satis, r.asof) for r in rows}


def stock_view(bakiye: float, gunluk: Optional[float], asof: Optional[str]) -> dict[str, Any]:
    days = None
    if gunluk and gunluk > 0:
        days = max(0.0, bakiye) / gunluk
    return {"bakiye": bakiye, "gunlukSatis": None if gunluk is None else round(gunluk, 3),
            "gun": None if days is None else round(days, 1), "tarih": asof}


def clip(frm: date, to: date, end: Optional[date]) -> Optional[tuple[date, date]]:
    """Dönemin Logo verisi olan kısmı; yoksa None."""
    if end is None:
        return None
    hi = min(to, end)
    return (frm, hi) if hi >= frm else None


def overview(engine: sa.engine.Engine, tenant: str, frm: date, to: date, platform: str, data_end: Optional[date],
             m15_by_book: Optional[dict[str, dict[str, Any]]] = None, crm_books: Optional[dict[str, dict[str, Any]]] = None,
             st: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """İlk açılış: dört gösterge, kanal kırılımı, kampanya ve kitap tablosu, bağsız harcama payı, veri tazeliği."""
    if to < frm:
        raise AdsError("Bitiş başlangıçtan önce olamaz.")
    rows = daily_rows(engine, tenant, frm, to, platform)
    main = [r for r in rows if (r.currency or MAIN_CURRENCY) == MAIN_CURRENCY]
    other: dict[str, float] = {}
    for r in rows:
        if (r.currency or MAIN_CURRENCY) != MAIN_CURRENCY:
            other[r.currency] = round(other.get(r.currency, 0.0) + float(r.spend or 0.0), 2)
    tot = metrics(_sum_rows(main))

    overlap = clip(frm, to, data_end)
    ecom = ecom_total(engine, tenant, *overlap) if overlap else {"ciro": None, "adet": None, "gun": 0}
    spend_overlap = sum(float(r.spend or 0) for r in main if overlap and overlap[0].isoformat() <= r.day <= overlap[1].isoformat())
    verim = div(ecom["ciro"], spend_overlap) if overlap and spend_overlap else None

    by_platform: dict[str, list[Any]] = {}
    by_campaign: dict[str, list[Any]] = {}
    for r in main:
        by_platform.setdefault(r.platform, []).append(r)
        by_campaign.setdefault(r.campaign_id, []).append(r)
    channels = []
    for p, rs in sorted(by_platform.items(), key=lambda kv: -sum(float(x.spend or 0) for x in kv[1])):
        m = metrics(_sum_rows(rs))
        channels.append({"kanal": p, "kanalAdi": PLATFORMS.get(p, p), **m, "pay": div(m["harcama"], tot["harcama"])})

    camps = {c["id"]: c for c in campaign_rows(engine, tenant)}
    codes = {camps[cid]["stokKodu"] for cid in by_campaign if cid in camps and camps[cid]["stokKodu"] and camps[cid]["bag"] == "onayli"}
    bsales = book_sales(engine, tenant, codes, *overlap) if overlap else {}
    stock = stock_of(engine, tenant)
    campaigns = []
    unlinked = 0.0
    books: dict[str, dict[str, Any]] = {}
    for cid, rs in by_campaign.items():
        c = camps.get(cid)
        if not c:
            continue
        m = metrics(_sum_rows(rs))
        linked = c["bag"] == "onayli" and c["stokKodu"]
        if not linked:
            unlinked += m["harcama"] or 0.0
        campaigns.append({**{k: c[k] for k in ("id", "ad", "platform", "platformAdi", "hesap", "durum", "stokKodu", "kitapAdi", "bag",
                                                "bagAdi", "bagGuven", "seri", "sonGun")}, **m})
        if linked:
            b = books.setdefault(c["stokKodu"], {"stokKodu": c["stokKodu"], "ad": c["kitapAdi"], "kampanya": 0, "_rows": []})
            b["kampanya"] += 1
            b["_rows"].extend(rs)
    book_rows = []
    for code, b in books.items():
        rs = b.pop("_rows")
        m = metrics(_sum_rows(rs))
        sp_ov = sum(float(r.spend or 0) for r in rs if overlap and overlap[0].isoformat() <= r.day <= overlap[1].isoformat())
        sales = bsales.get(code) or ({"eticaretCiro": 0.0, "eticaretAdet": 0.0, "toplamCiro": 0.0, "toplamAdet": 0.0} if overlap else None)
        crm = (crm_books or {}).get(code) or {}
        book_rows.append({**b, **m, "satis": sales, "verim": div((sales or {}).get("eticaretCiro"), sp_ov) if sp_ov else None,
                          "harcamaVeriIcinde": round(sp_ov, 2), "stok": stock.get(code), "m15": (m15_by_book or {}).get(code),
                          "yayinDurumu": crm.get("durum"), "satisDisi": bool(crm.get("satisDisi"))})
    campaigns.sort(key=lambda x: -(x["harcama"] or 0))
    book_rows.sort(key=lambda x: -(x["harcama"] or 0))

    daily: dict[str, float] = {}
    for r in main:
        daily[r.day] = daily.get(r.day, 0.0) + float(r.spend or 0)
    ecom_days = ecom_by_day(engine, tenant, *overlap) if overlap else {}
    series = []
    d = frm
    while d <= to:
        k = d.isoformat()
        series.append({"gun": k, "harcama": round(daily.get(k, 0.0), 2),
                       "eticaretCiro": round(ecom_days[k], 2) if k in ecom_days else (0.0 if overlap and d <= overlap[1] else None)})
        d += timedelta(days=1)

    return {
        "donem": {"bas": frm.isoformat(), "bit": to.isoformat(), "kanal": platform or None},
        "veriSonu": data_end.isoformat() if data_end else None,
        "verimDonemi": {"bas": overlap[0].isoformat(), "bit": overlap[1].isoformat()} if overlap else None,
        "gosterge": {**tot, "eticaretCiro": ecom["ciro"], "eticaretAdet": ecom["adet"], "verim": verim,
                     "harcamaVeriIcinde": round(spend_overlap, 2)},
        "digerParaBirimi": other,
        "kanallar": channels,
        "kampanyalar": campaigns,
        "kitaplar": book_rows,
        "bagsiz": {"harcama": round(unlinked, 2), "pay": div(unlinked, tot["harcama"]) if tot["harcama"] else None},
        "gunluk": series,
    }


# ------------------------------------------------------------------ bütçe (ay × kanal)


def _months(year: int) -> list[str]:
    return [f"{year}-{m:02d}" for m in range(1, 13)]


def spread(amount: float, start: Optional[str], end: Optional[str], fallback: Optional[str]) -> dict[str, float]:
    """Tutarı [start, end] günlerine eşit dağıtıp aya toplar. Tarih yoksa `fallback` gününün ayına."""
    a = start or end or fallback
    b = end or start or fallback
    if not a:
        return {}
    try:
        d1, d2 = date.fromisoformat(a[:10]), date.fromisoformat(b[:10])
    except ValueError:
        return {}
    if d2 < d1:
        d1, d2 = d2, d1
    days = (d2 - d1).days + 1
    out: dict[str, float] = {}
    d = d1
    while d <= d2:
        last = date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
        seg_end = min(last, d2)
        n = (seg_end - d).days + 1
        k = f"{d.year}-{d.month:02d}"
        out[k] = out.get(k, 0.0) + amount * n / days
        d = seg_end + timedelta(days=1)
    return out


def m15_lines_stmt(tenant: str, channels: Iterable[str], codes: Optional[Iterable[str]] = None):
    """M15 onaylı planların reklam kanalı satırları; kanal yoksa ya da kitap süzgeci boşsa None."""
    from semantic_bridge.marketing import core as MC

    chans = sorted(set(channels))
    if not chans:
        return None
    cond = [MC.PLANS.c.tenant_id == tenant, MC.PLANS.c.durum == "onayli", MC.LINES.c.kanal.in_(chans)]
    want = [c for c in (codes or []) if c]
    if codes is not None:
        if not want:
            return None
        cond.append(MC.PLANS.c.stok_kodu.in_(want))
    return sa.select(MC.LINES, MC.PLANS.c.baslik, MC.PLANS.c.stok_kodu, MC.PLANS.c.yayin_tarihi,
                     MC.PLANS.c.id.label("pid"), MC.PLANS.c.kind) \
        .select_from(MC.LINES.join(MC.PLANS, MC.PLANS.c.id == MC.LINES.c.plan_id)).where(*cond)


def m15_lines(engine: sa.engine.Engine, tenant: str, channels: Iterable[str], year: Optional[int] = None,
              codes: Optional[Iterable[str]] = None) -> list[dict[str, Any]]:
    """M15 onaylı planların reklam kanalı satırları (`dijital`, `sosyal-medya` …). Plan M15'te onaylanır; burada yalnız
    okunur. Satırın tutarı başlangıç–bitiş günlerine eşit dağıtılıp aya bölünür."""
    from semantic_bridge.marketing import core as MC

    MC.ensure(engine)
    q = m15_lines_stmt(tenant, channels, codes)
    if q is None:
        return []
    with engine.connect() as c:
        rows = c.execute(q).all()
    out = []
    for r in rows:
        months = spread(float(r.tutar or 0), r.baslangic, r.bitis, r.yayin_tarihi)
        if year is not None:
            months = {k: v for k, v in months.items() if k.startswith(f"{year}-")}
            if not months:
                continue
        out.append({"planId": r.pid, "plan": r.baslik, "tur": r.kind, "stokKodu": r.stok_kodu, "kanal": r.kanal,
                    "kanalAdi": MC.CHANNELS.get(r.kanal, r.kanal), "altKanal": r.alt_kanal, "tutar": float(r.tutar or 0),
                    "bas": r.baslangic, "bit": r.bitis, "aylar": {k: round(v, 2) for k, v in months.items()}})
    return out


def m15_by_book(engine: sa.engine.Engine, tenant: str, codes: Iterable[str], channels: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Kitabın onaylı M15 planındaki reklam kanalı satırlarının toplamı (planın tamamı; dönemle kesilmez)."""
    out: dict[str, dict[str, Any]] = {}
    for ln in m15_lines(engine, tenant, channels, None, list(codes)):
        b = out.setdefault(ln["stokKodu"], {"planlar": [], "tutar": 0.0})
        if ln["planId"] not in b["planlar"]:
            b["planlar"].append(ln["planId"])
        b["tutar"] = round(b["tutar"] + ln["tutar"], 2)
    return out


def budget_stmt(tenant: str, year: int):
    return sa.select(BUDGET).where(BUDGET.c.tenant_id == tenant, BUDGET.c.month.like(f"{year}-%"))


def budget(engine: sa.engine.Engine, tenant: str, year: int, st: dict[str, Any], crm_rows: Optional[list[dict[str, Any]]] = None,
           ref: Optional[date] = None) -> dict[str, Any]:
    """Ay × kanal: bu modülde girilen plan, harcama (yüklenen dosyalar, TL), M15 onaylı kitap planlarının reklam kanalı
    satırları ve CRM «Pazarlama Bütçe Modülü» kayıtları (dijital / sosyal medya tipleri). Ay sonu tahmini yalnız içinde
    bulunulan ay için: harcama ÷ geçen gün × ayın günü."""
    months = _months(year)
    with engine.connect() as c:
        plans = c.execute(budget_stmt(tenant, year)).all()
    rows = daily_rows(engine, tenant, date(year, 1, 1), date(year, 12, 31))
    actual: dict[tuple[str, str], float] = {}
    for r in rows:
        if (r.currency or MAIN_CURRENCY) != MAIN_CURRENCY:
            continue
        k = (r.day[:7], r.platform)
        actual[k] = actual.get(k, 0.0) + float(r.spend or 0)
    planned = {(p.month, p.channel): p for p in plans}
    ref = ref or today()
    cur = f"{ref.year}-{ref.month:02d}"
    dim = calendar.monthrange(ref.year, ref.month)[1]
    cells = []
    for m in months:
        for ch in PLATFORMS:
            p = planned.get((m, ch))
            a = round(actual.get((m, ch), 0.0), 2)
            if p is None and not a:
                continue
            proj = round(a / ref.day * dim, 2) if m == cur and ref.day else None
            cells.append({"ay": m, "kanal": ch, "plan": p.planned if p else None, "not": p.note if p else None,
                          "harcama": a, "kalan": round(p.planned - a, 2) if p else None,
                          "tahmin": proj, "asim": bool(p and proj is not None and proj > p.planned)})
    lines = m15_lines(engine, tenant, set(st["m15Channels"].values()), year)
    m15_month: dict[tuple[str, str], float] = {}
    for ln in lines:
        for m, v in ln["aylar"].items():
            m15_month[(m, ln["kanal"])] = m15_month.get((m, ln["kanal"]), 0.0) + v
    crm_month: dict[str, float] = {}
    for r in crm_rows or []:
        for m, v in spread(float(r.get("tutar") or 0), r.get("baslangic"), r.get("bitis"), r.get("baslangic")).items():
            if m.startswith(f"{year}-"):
                crm_month[m] = crm_month.get(m, 0.0) + v
    totals = {"plan": round(sum(p.planned for p in plans), 2), "harcama": round(sum(v for (m, _), v in actual.items() if m.startswith(f"{year}-")), 2),
              "m15": round(sum(m15_month.values()), 2), "crm": round(sum(crm_month.values()), 2)}
    return {"yil": year, "aylar": months, "kanallar": PLATFORMS, "hucreler": cells,
            "m15": {"satirlar": lines, "ay": [{"ay": m, "kanal": k, "tutar": round(v, 2)} for (m, k), v in sorted(m15_month.items())],
                    "kanalEsleme": st["m15Channels"]},
            "crm": [{"ay": m, "tutar": round(v, 2)} for m, v in sorted(crm_month.items())], "toplam": totals}


def put_budget(engine: sa.engine.Engine, tenant: str, user: str, items: Any) -> int:
    """Ay × kanal planı yazar. `planned` boş/None satırı siler. Dönen: değişen satır sayısı."""
    if not isinstance(items, list) or not items:
        raise AdsError("Yazılacak satır yok.")
    clean = []
    for it in items:
        if not isinstance(it, dict):
            raise AdsError("Satır biçimi hatalı.")
        m = str(it.get("ay") or "")
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", m):
            raise AdsError("Ay YYYY-AA biçiminde olmalı.")
        ch = str(it.get("kanal") or "")
        if ch not in PLATFORMS:
            raise AdsError("Kanal tanınmıyor.")
        v = it.get("plan")
        if v in (None, ""):
            clean.append((m, ch, None, None))
            continue
        try:
            n = float(v)
        except (TypeError, ValueError):
            raise AdsError("Plan tutarı sayı olmalı.") from None
        if not math.isfinite(n) or n < 0:
            raise AdsError("Plan tutarı sıfır ya da artı olmalı.")
        clean.append((m, ch, round(n, 2), one_line(it.get("not"), 500)))
    n = 0
    with engine.begin() as c:
        for m, ch, v, note in clean:
            cond = (BUDGET.c.tenant_id == tenant, BUDGET.c.month == m, BUDGET.c.channel == ch)
            old = c.execute(sa.select(BUDGET.c.id).where(*cond)).first()
            if v is None:
                if old:
                    c.execute(BUDGET.delete().where(*cond))
                    n += 1
            elif old:
                c.execute(BUDGET.update().where(*cond).values(planned=v, note=note, created_by=user, updated_at=now()))
                n += 1
            else:
                c.execute(BUDGET.insert().values(id=uid(), tenant_id=tenant, month=m, channel=ch, planned=v, note=note,
                                                 created_by=user, updated_at=now()))
                n += 1
    return n


# ------------------------------------------------------------------ öneri kuralları


def _tl(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:,.0f}".replace(",", ".") + " TL"


def _campaign_window(engine: sa.engine.Engine, tenant: str, frm: date, to: date) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in daily_rows(engine, tenant, frm, to):
        if (r.currency or MAIN_CURRENCY) != MAIN_CURRENCY:
            continue
        cur = out.setdefault(r.campaign_id, {"rows": [], "platform": r.platform})
        cur["rows"].append(r)
    return {k: {**metrics(_sum_rows(v["rows"])), "platform": v["platform"], "sonGun": max(x.day for x in v["rows"])}
            for k, v in out.items()}


def evaluate(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], ref: date, *,
             crm_books: Optional[dict[str, dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """Bugünkü öneri adayları. Her aday: kind, key (tekrar anahtarı), campaign_id, account_id, stok_kodu, payload, reason."""
    out: list[dict[str, Any]] = []
    camps = {c["id"]: c for c in campaign_rows(engine, tenant)}
    stock = stock_of(engine, tenant)
    active_from = ref - timedelta(days=st["activeDays"])
    active = _campaign_window(engine, tenant, active_from, ref)

    for cid, m in active.items():
        c = camps.get(cid)
        if not c or c["bag"] != "onayli" or not c["stokKodu"] or not m["harcama"]:
            continue
        s = stock.get(c["stokKodu"])
        if s is not None:
            short = s["bakiye"] <= 0 or (st["stockDays"] is not None and s["gun"] is not None and s["gun"] < st["stockDays"])
            if short:
                why = ("stok yok" if s["bakiye"] <= 0 else f"stok yaklaşık {s['gun']:.0f} günlük satışı karşılıyor")
                out.append({"kind": "stok", "key": f"stok:{cid}", "campaign_id": cid, "account_id": c["hesapId"],
                            "stok_kodu": c["stokKodu"],
                            "payload": {"stok": s, "sonGunHarcama": m["harcama"], "esikGun": st["stockDays"]},
                            "reason": f"«{c['kitapAdi'] or c['stokKodu']}» için {why} (Logo stok bakiyesi, {s.get('tarih') or 'tarih yok'}); "
                                      f"kampanya «{c['ad']}» son {st['activeDays']} günde {_tl(m['harcama'])} harcadı. Reklamı durdurmayı "
                                      "ya da stok gelene kadar bütçeyi başka kitaba kaydırmayı değerlendirin."})
        crm = (crm_books or {}).get(c["stokKodu"]) or {}
        if crm.get("satisDisi"):
            out.append({"kind": "satis-disi", "key": f"satis-disi:{cid}", "campaign_id": cid, "account_id": c["hesapId"],
                        "stok_kodu": c["stokKodu"], "payload": {"yayinDurumu": crm.get("durum"), "sonGunHarcama": m["harcama"]},
                        "reason": f"«{c['kitapAdi'] or c['stokKodu']}» CRM'de «{crm.get('durum')}» durumunda; kampanya «{c['ad']}» "
                                  f"son {st['activeDays']} günde {_tl(m['harcama'])} harcadı."})

    # veri gelmedi: hesabın son günü eski, son 30 günde verisi var
    last_by_acc: dict[str, str] = {}
    for c in camps.values():
        if c["sonGun"] and (c["hesapId"] not in last_by_acc or c["sonGun"] > last_by_acc[c["hesapId"]]):
            last_by_acc[c["hesapId"]] = c["sonGun"]
    accs = {a["id"]: a for a in list_accounts(engine, tenant)}
    for aid, last in last_by_acc.items():
        d = date.fromisoformat(last)
        if (ref - d).days > st["noDataDays"] and (ref - d).days <= 30:
            a = accs.get(aid) or {}
            out.append({"kind": "veri-yok", "key": f"veri-yok:{aid}", "campaign_id": None, "account_id": aid, "stok_kodu": None,
                        "payload": {"sonGun": last, "gun": (ref - d).days},
                        "reason": f"«{a.get('ad') or aid}» hesabının son verisi {last} ({(ref - d).days} gün önce). "
                                  "Platformdan son günlerin dışa aktarım dosyasını yükleyin."})

    # bütçe: ay sonu tahmini plan üstünde
    y, mo = ref.year, ref.month
    month = f"{y}-{mo:02d}"
    with engine.connect() as cn:
        plans = {p.channel: p.planned for p in cn.execute(sa.select(BUDGET).where(BUDGET.c.tenant_id == tenant, BUDGET.c.month == month)).all()}
    if plans:
        mtd = _campaign_window(engine, tenant, date(y, mo, 1), ref)
        by_ch: dict[str, float] = {}
        for m in mtd.values():
            by_ch[m["platform"]] = by_ch.get(m["platform"], 0.0) + (m["harcama"] or 0)
        dim = calendar.monthrange(y, mo)[1]
        pct = st["overspendPct"] or 0.0
        for ch, planned_v in plans.items():
            spent = by_ch.get(ch, 0.0)
            proj = spent / ref.day * dim
            if planned_v >= 0 and proj > planned_v * (1 + pct / 100.0) and spent > 0:
                out.append({"kind": "butce", "key": f"butce:{month}:{ch}", "campaign_id": None, "account_id": None, "stok_kodu": None,
                            "payload": {"ay": month, "kanal": ch, "plan": planned_v, "harcama": round(spent, 2), "tahmin": round(proj, 2)},
                            "reason": f"{PLATFORMS.get(ch, ch)} kanalında {month} harcaması {_tl(spent)}; bu hızla ay sonu "
                                      f"{_tl(proj)} olur, plan {_tl(planned_v)}."})

    # durdur ve kaydır (eşik girilmediyse kapalı)
    win = _campaign_window(engine, tenant, ref - timedelta(days=st["perfWindowDays"]), ref)
    if st["stopMinSpend"] is not None:
        for cid, m in win.items():
            c = camps.get(cid)
            if not c or (m["harcama"] or 0) < st["stopMinSpend"] or m["sonGun"] < active_from.isoformat():
                continue
            no_conv = m["donusum"] is not None and m["donusum"] == 0
            low_roas = st["stopMaxRoas"] is not None and m["platformRoas"] is not None and m["platformRoas"] < st["stopMaxRoas"]
            if no_conv or low_roas:
                why = "hiç dönüşüm yok" if no_conv else f"platform ROAS {m['platformRoas']:.2f}"
                out.append({"kind": "durdur", "key": f"durdur:{cid}", "campaign_id": cid, "account_id": c["hesapId"],
                            "stok_kodu": c["stokKodu"], "payload": {"pencere": st["perfWindowDays"], **m},
                            "reason": f"«{c['ad']}» son {st['perfWindowDays']} günde {_tl(m['harcama'])} harcadı, {why}."})
    if st["shiftMinSpend"] is not None:
        by_platform: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for cid, m in win.items():
            if cid in camps and (m["harcama"] or 0) >= st["shiftMinSpend"] and m["platformRoas"] is not None and m["sonGun"] >= active_from.isoformat():
                by_platform.setdefault(m["platform"], []).append((cid, m))
        for p, items in by_platform.items():
            if len(items) < 2:
                continue
            items.sort(key=lambda x: x[1]["platformRoas"])
            (lo_id, lo), (hi_id, hi) = items[0], items[-1]
            if lo["platformRoas"] <= 0 or hi["platformRoas"] / lo["platformRoas"] >= st["shiftRoasRatio"]:
                amount = round(lo["harcama"] * st["shiftShare"], 2)
                out.append({"kind": "kaydir", "key": f"kaydir:{lo_id}:{hi_id}", "campaign_id": lo_id, "account_id": camps[lo_id]["hesapId"],
                            "stok_kodu": camps[lo_id]["stokKodu"],
                            "payload": {"kaynak": lo_id, "hedef": hi_id, "tutar": amount, "kaynakRoas": lo["platformRoas"],
                                        "hedefRoas": hi["platformRoas"], "pencere": st["perfWindowDays"], "kanal": p},
                            "reason": f"{PLATFORMS.get(p, p)}: «{camps[lo_id]['ad']}» platform ROAS {lo['platformRoas']:.2f}, "
                                      f"«{camps[hi_id]['ad']}» {hi['platformRoas']:.2f} (son {st['perfWindowDays']} gün). "
                                      f"Düşük olandan {_tl(amount)} bütçenin yüksek olana kaydırılması önerilir."})
    return out


def store_suggestions(engine: sa.engine.Engine, tenant: str, cands: list[dict[str, Any]], st: dict[str, Any]) -> dict[str, Any]:
    """Yeni adayları yazar (aynı anahtarda açık öneri ya da son `resuggestDays` günde karar verilmiş öneri varsa yazmaz);
    koşulu kalkan açık uyarıları `gecersiz` yapar. Onay isteyen türlerin açık önerisine dokunmaz."""
    keys = {c["key"] for c in cands}
    since = now() - timedelta(days=st["resuggestDays"])
    made, closed = [], 0
    with engine.begin() as c:
        rows = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant)).all()
        open_keys = {r.dedupe_key for r in rows if r.status in OPEN}
        # İnsanın karar verdiği öneri bekleme süresince yeniden yazılmaz; sistemin kapattığı (koşulu kalkmış) uyarı ise
        # koşul geri gelince hemen yeniden çıkar.
        recent = {r.dedupe_key for r in rows if r.status not in OPEN and r.status != "gecersiz" and r.decided_at is not None
                  and (r.decided_at if r.decided_at.tzinfo else r.decided_at.replace(tzinfo=timezone.utc)) >= since}
        for r in rows:
            if r.status == "yeni" and r.kind not in APPROVAL_KINDS and r.dedupe_key not in keys:
                c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.id == r.id).values(status="gecersiz", decided_by="sistem", decided_at=now()))
                closed += 1
        for x in cands:
            if x["key"] in open_keys or x["key"] in recent:
                continue
            sid = uid()
            c.execute(SUGGESTIONS.insert().values(
                id=sid, tenant_id=tenant, kind=x["kind"], dedupe_key=x["key"][:200], campaign_id=x.get("campaign_id"),
                account_id=x.get("account_id"), stok_kodu=x.get("stok_kodu"), payload_json=dump(x.get("payload")),
                reason=x["reason"], status="yeni", created_at=now()))
            made.append(sid)
    return {"yeni": made, "kapanan": closed}


def _suggestion(r: Any, camp: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {"id": r.id, "tur": r.kind, "turAdi": KINDS.get(r.kind, r.kind), "onayGerekir": r.kind in APPROVAL_KINDS,
            "kampanyaId": r.campaign_id, "kampanya": (camp or {}).get("ad"), "platformAdi": (camp or {}).get("platformAdi"),
            "hesapId": r.account_id, "stokKodu": r.stok_kodu, "kitapAdi": (camp or {}).get("kitapAdi"),
            "veri": loads(r.payload_json, {}), "gerekce": r.reason, "zekiNotu": r.model_note, "durum": r.status,
            "durumAdi": STATUSES.get(r.status, r.status), "zaman": iso(r.created_at), "karar": r.decided_by,
            "kararZamani": iso(r.decided_at), "kararNotu": r.decision_note, "uygulayan": r.applied_by, "uygulamaZamani": iso(r.applied_at)}


def suggestions_stmt(tenant: str, status: str = ""):
    cond = [SUGGESTIONS.c.tenant_id == tenant]
    if status == "acik":
        cond.append(SUGGESTIONS.c.status.in_(OPEN))
    elif status:
        cond.append(SUGGESTIONS.c.status.in_([s for s in status.split(",") if s]))
    return sa.select(SUGGESTIONS).where(*cond).order_by(SUGGESTIONS.c.created_at.desc())


def list_suggestions(engine: sa.engine.Engine, tenant: str, status: str = "") -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(suggestions_stmt(tenant, status)).all()
    camps = {x["id"]: x for x in campaign_rows(engine, tenant)}
    return [_suggestion(r, camps.get(r.campaign_id)) for r in rows]


def get_suggestion(engine: sa.engine.Engine, tenant: str, sid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(SUGGESTIONS).where(SUGGESTIONS.c.tenant_id == tenant, SUGGESTIONS.c.id == str(sid)[:32])).first()
    if not r:
        raise AdsError("Öneri bulunamadı.", 404)
    camp = get_campaign(engine, tenant, r.campaign_id) if r.campaign_id else None
    return _suggestion(r, camp)


def decide(engine: sa.engine.Engine, tenant: str, user: str, sid: str, karar: str, note: Any = None) -> dict[str, Any]:
    """`onayla` / `reddet` (onay türlerinde onay yetkisi ucun içinde denetlenir), `uygulandi` (uzman platformda uyguladı).
    Onay türünde `uygulandi` için önce onay gerekir; uyarı türü doğrudan uygulandı/reddedildi olur."""
    s = get_suggestion(engine, tenant, sid)
    st = s["durum"]
    need = s["onayGerekir"]
    if karar == "onayla":
        if not need:
            raise AdsError("Bu öneri onay istemez; «uygulandı» ya da «yok say» işaretleyin.", 409)
        if st != "yeni":
            raise AdsError("Yalnız yeni öneri onaylanır.", 409)
        vals = {"status": "onaylandi", "decided_by": user, "decided_at": now(), "decision_note": one_line(note, 1000)}
    elif karar == "reddet":
        if st not in OPEN:
            raise AdsError("Öneri zaten kapanmış.", 409)
        if need and not one_line(note, 1000):
            raise AdsError("Reddetme gerekçesi gerekli.")
        vals = {"status": "reddedildi", "decided_by": user, "decided_at": now(), "decision_note": one_line(note, 1000)}
    elif karar == "uygulandi":
        if need and st != "onaylandi":
            raise AdsError("Önce onay gerekli: para kararı pazarlama müdüründen geçer.", 409)
        if not need and st != "yeni":
            raise AdsError("Öneri zaten kapanmış.", 409)
        vals = {"status": "uygulandi", "applied_by": user, "applied_at": now()}
        if not need:
            vals.update(decided_by=user, decided_at=now(), decision_note=one_line(note, 1000))
    else:
        raise AdsError("Karar onayla, reddet ya da uygulandi olmalı.")
    with engine.begin() as c:
        c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.id == s["id"]).values(**vals))
    return get_suggestion(engine, tenant, s["id"])


def set_model_note(engine: sa.engine.Engine, sid: str, note: Optional[str]) -> None:
    with engine.begin() as c:
        c.execute(SUGGESTIONS.update().where(SUGGESTIONS.c.id == sid).values(model_note=note))


# ------------------------------------------------------------------ brief


def _brief(r: Any) -> dict[str, Any]:
    return {"id": r.id, "kitapId": r.crm_book_id, "stokKodu": r.stok_kodu, "kitapAdi": r.book_name, "istek": r.request_note,
            "metin": r.body, "durum": r.status, "durumAdi": BRIEF_STATUSES.get(r.status, r.status), "denetim": loads(r.check_json, None),
            "hata": r.error, "olusturan": r.created_by, "olusturma": iso(r.created_at), "guncelleyen": r.updated_by,
            "guncelleme": iso(r.updated_at), "onaylayan": r.approved_by, "onayZamani": iso(r.approved_at)}


def create_brief(engine: sa.engine.Engine, tenant: str, user: str, book: dict[str, Any], note: Any) -> dict[str, Any]:
    bid = uid()
    with engine.begin() as c:
        c.execute(BRIEFS.insert().values(id=bid, tenant_id=tenant, crm_book_id=book.get("kitapId"), stok_kodu=book["stokKodu"],
                                         book_name=book.get("ad"), request_note=one_line(note, 1000), status="hazirlaniyor",
                                         created_by=user, created_at=now()))
    return get_brief(engine, tenant, bid)


def brief_stmt(tenant: str, bid: str):
    return sa.select(BRIEFS).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.id == str(bid)[:32])


def briefs_stmt(tenant: str, stok: str = ""):
    cond = [BRIEFS.c.tenant_id == tenant]
    if stok:
        cond.append(BRIEFS.c.stok_kodu == stok)
    return sa.select(BRIEFS).where(*cond).order_by(BRIEFS.c.created_at.desc())


def get_brief(engine: sa.engine.Engine, tenant: str, bid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(brief_stmt(tenant, bid)).first()
    if not r:
        raise AdsError("Brief bulunamadı.", 404)
    return _brief(r)


def list_briefs(engine: sa.engine.Engine, tenant: str, stok: str = "") -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(briefs_stmt(tenant, stok)).all()
    return [_brief(r) for r in rows]


def finish_brief(engine: sa.engine.Engine, bid: str, body: Optional[str], check: Optional[dict[str, Any]], error: Optional[str] = None) -> None:
    with engine.begin() as c:
        c.execute(BRIEFS.update().where(BRIEFS.c.id == bid).values(
            body=body, check_json=None if check is None else dump(check), status="hata" if error else "taslak",
            error=None if not error else error[:500], updated_at=now()))


def update_brief(engine: sa.engine.Engine, tenant: str, user: str, bid: str, body: dict[str, Any]) -> dict[str, Any]:
    b = get_brief(engine, tenant, bid)
    vals: dict[str, Any] = {}
    if "metin" in body:
        if b["durum"] == "hazirlaniyor":
            raise AdsError("Taslak henüz hazırlanıyor.", 409)
        text_ = str(body.get("metin") or "").strip()
        if not text_:
            raise AdsError("Brief metni boş olamaz.")
        vals.update(body=text_[:60000], status="taslak", approved_by=None, approved_at=None)
    if body.get("onayla"):
        if b["durum"] not in ("taslak",) and "metin" not in vals:
            raise AdsError("Yalnız taslak brief onaylanır.", 409)
        vals.update(status="onayli", approved_by=user, approved_at=now())
    if not vals:
        raise AdsError("Değişiklik yok.")
    with engine.begin() as c:
        c.execute(BRIEFS.update().where(BRIEFS.c.id == b["id"]).values(**vals, updated_by=user, updated_at=now()))
    return get_brief(engine, tenant, b["id"])


def delete_brief(engine: sa.engine.Engine, tenant: str, bid: str) -> dict[str, Any]:
    b = get_brief(engine, tenant, bid)
    with engine.begin() as c:
        c.execute(BRIEFS.delete().where(BRIEFS.c.id == b["id"]))
    return b


def fail_stale_briefs(engine: sa.engine.Engine) -> int:
    """Köprü yeniden başlarken yarıda kalan brief işleri."""
    with engine.begin() as c:
        return c.execute(BRIEFS.update().where(BRIEFS.c.status == "hazirlaniyor").values(
            status="hata", error="Köprü yeniden başladı; yeniden isteyin.", updated_at=now())).rowcount


# ------------------------------------------------------------------ Logo önbelleği yazımı


def write_ecom(engine: sa.engine.Engine, tenant: str, frm: date, to: date, rows: list[dict[str, Any]]) -> int:
    with engine.begin() as c:
        c.execute(ECOM.delete().where(ECOM.c.tenant_id == tenant, ECOM.c.day >= frm.isoformat(), ECOM.c.day <= to.isoformat()))
        for r in rows:
            c.execute(ECOM.insert().values(tenant_id=tenant, day=r["day"], ciro=r["ciro"], adet=r["adet"]))
    return len(rows)


def write_book_sales(engine: sa.engine.Engine, tenant: str, frm: date, to: date, codes: list[str], rows: list[dict[str, Any]]) -> int:
    with engine.begin() as c:
        for i in range(0, len(codes), 500):
            c.execute(ECOM_BOOK.delete().where(ECOM_BOOK.c.tenant_id == tenant, ECOM_BOOK.c.stok_kodu.in_(codes[i:i + 500]),
                                               ECOM_BOOK.c.day >= frm.isoformat(), ECOM_BOOK.c.day <= to.isoformat()))
        for r in rows:
            c.execute(ECOM_BOOK.insert().values(tenant_id=tenant, stok_kodu=r["stok_kodu"], day=r["day"], eticaret_ciro=r["eticaret_ciro"],
                                                eticaret_adet=r["eticaret_adet"], toplam_ciro=r["toplam_ciro"], toplam_adet=r["toplam_adet"]))
    return len(rows)


def write_stock(engine: sa.engine.Engine, tenant: str, rows: list[dict[str, Any]], asof: Optional[str],
                codes: Optional[list[str]] = None) -> int:
    """Stok önbelleği. `codes` verilirse yalnız o kodlar yenilenir; verilmezse tablo baştan yazılır."""
    with engine.begin() as c:
        if codes is None:
            c.execute(STOCK.delete().where(STOCK.c.tenant_id == tenant))
        else:
            for i in range(0, len(codes), 500):
                c.execute(STOCK.delete().where(STOCK.c.tenant_id == tenant, STOCK.c.stok_kodu.in_(codes[i:i + 500])))
        for r in rows:
            c.execute(STOCK.insert().values(tenant_id=tenant, stok_kodu=r["stok_kodu"], bakiye=r["bakiye"], gunluk_satis=r.get("gunluk"),
                                            asof=asof))
    return len(rows)


def linked_codes(engine: sa.engine.Engine, tenant: str) -> list[str]:
    with engine.connect() as c:
        return sorted({r[0] for r in c.execute(sa.select(CAMPAIGNS.c.stok_kodu).where(
            CAMPAIGNS.c.tenant_id == tenant, CAMPAIGNS.c.stok_kodu.isnot(None), CAMPAIGNS.c.link_status.in_(("onayli", "oneri")))).all() if r[0]})


def first_ad_day(engine: sa.engine.Engine, tenant: str) -> Optional[date]:
    with engine.connect() as c:
        v = c.execute(sa.select(sa.func.min(DAILY.c.day)).select_from(DAILY.join(CAMPAIGNS, CAMPAIGNS.c.id == DAILY.c.campaign_id))
                      .where(CAMPAIGNS.c.tenant_id == tenant)).scalar()
    return date.fromisoformat(v) if v else None


def unlinked_campaigns(engine: sa.engine.Engine, tenant: str, ids: Optional[Iterable[str]] = None) -> list[dict[str, Any]]:
    """Bağ önerisi bekleyen kampanyalar: bağsız ve daha önce hiç denenmemiş (`link_json` boş) ya da `ids` ile istenen."""
    want = set(ids or [])
    return [c for c in campaign_rows(engine, tenant)
            if c["bag"] == "yok" and (c["id"] in want if want else c["bagAyrinti"] is None)]
