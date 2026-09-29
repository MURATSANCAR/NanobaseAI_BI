"""H3 E-ticaret müşteri yönetimi: site siparişinden müşteri tablosu, RFM segmentleri, tetik listeleri, kontrol gruplu
kampanya sonucu, ürün hunisi ve müşteri kartı.

**Kaynak.** Site siparişi ve üyesi T-soft'tan yalnız okunur (`commerce_sources`); CRM'de T-soft dönemi siparişi yok
(son 12 ayda B2C sipariş 0 — kabul K3). Gerçekleşmiş finansal ciro Logo'dadır (kayıt sistemi): özet ekranı site cirosunu
M42'nin `timas.com.tr` kanal eşlemesinden gelen Logo net cirosuyla **ayrı etiketle** yan yana koyar; ikisi aynı kavram
değildir (site tutarı KDV ve kargo dahil olabilir, iptal sonrası iade Logo'da ayrı satırdır).

**Kişisel veri portalda düz metin olarak durmaz.** Müşteri anahtarı, e-posta/telefon/ad yalnız H2'nin tuzlu özeti
(`READERS_HASH_SALT`); il adı tutulur. Ad/e-posta/telefon yalnız `ozellik:okur.kisisel-veri` ile müşteri kartında ve izin
denetimli dışa aktarımda T-soft'tan anlık okunur, saklanmaz, her görüntüleme `semantic_audit`'e düşer. Modele kişisel
veri gitmez (`assert_no_personal`).

**Kimlik, izin, segment motoru H2'dendir** (yeniden yazılmadı): site müşterisi `readers.register_source("tsoft_member",
…, address=True)` ile tekil okura bağlanır; izin kararı `readers.exportable` / `final_consent`; H2 segment motoruna
«E-ticaret segmenti», «Site siparişi sayısı», «Son site siparişi», «Site cirosu», «Aldığı kategori» alanları
`readers_segments.register_field` ile eklenir (segment alanı `eticaret`). Dışa aktarım H2'nin defterine yazılır
(`readers_segments.record_export`).

**RFM (K1, kural).** Geçerli sipariş = iptal/iade durumunda olmayan sipariş. Segment: sipariş yok → «siparissiz»; son
sipariş `activeDays`'ten (90) eski → «kayip»; sipariş ≥ `loyalOrders` (4) ya da ciro ≥ `loyalRevenue` (0 = kullanılmaz)
→ «sadik»; tek sipariş → «ilk»; diğerleri «aktif». Eşikler ekrandan (`ozellik:eticaret.ayar`). Segment değişince geçiş
kaydı yazılır.

**Tetik (K1 hesap, K2 gönderim kararı).** Aday listesi kuraldan; H2 okuruna bağlanmayan ya da seçilen kanalda
dışa aktarılamayan müşteri (ret, izin yok, KVKK, çocuk, adres) listeye girmez ve nedeniyle sayılır. Kalan «ulaşılabilir»
küme özet sırasına göre `controlShare` oranında **kontrol grubuna** ayrılır (tam oran, ±1 kişi). Kontrol grubu hiçbir
zaman dışa aktarılmaz. Liste açıkça verilen `ozellik:eticaret.liste-onay` ile onaylanır; tetiği yazan ve listeyi
çalıştıran onaylayamaz. Dışa aktarım H2 ayarı (`READERS_EXPORT_ENABLED`) açıkken, `ozellik:okur.liste-aktar` ile, amaç
yazılarak; kişi o an yeniden denetlenir (CRM bayrağı, T-soft izni).

**Kampanya sonucu (K3).** Hedef ve kontrol grubunun pencere içindeki geçerli siparişleri; dönüşüm farkı, %95 güven
aralığı (normal yaklaşım), ek alıcı ve ek ciro. Kontrol grubu 30'dan küçükse sonuç «güvenilir değil» yazar. Rakamlar
hesaptan; Zeki AI yalnız rakamsız bir yorum cümlesi ekler (rakam içeren satır atılır).

T-soft'a, CRM'e ve Logo'ya hiçbir şey yazılmaz; portal ileti göndermez.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import re
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import commerce_sources as src
from semantic_bridge import readers as R

log = logging.getLogger("semantic.commerce")
_md = sa.MetaData()


class CommerceError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ tablolar (bi_meta; hepsinde tenant_id)

ORDERS = sa.Table(
    "semantic_commerce_orders", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("order_no", sa.String(60), primary_key=True),
    sa.Column("ordered_at", sa.DateTime),                              # sitenin yerel saati
    sa.Column("status", sa.String(60)),
    sa.Column("valid", sa.Boolean, nullable=False, default=True),      # iptal/iade değil
    sa.Column("total", sa.Float, nullable=False, default=0.0),
    sa.Column("discount", sa.Float),
    sa.Column("shipping", sa.Float),
    sa.Column("coupon", sa.String(80)),
    sa.Column("payment", sa.String(60)),
    sa.Column("utm_source", sa.String(120)),
    sa.Column("utm_campaign", sa.String(160)),
    sa.Column("customer_key", sa.String(64), index=True),              # tuzlu özet; kişisel veri değil
    sa.Column("member_ref", sa.String(40)),                            # T-soft üye numarası (kişi bilgisi değil)
    sa.Column("is_guest", sa.Boolean, nullable=False, default=False),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_semantic_commerce_orders_day", "tenant_id", "ordered_at"),
)
LINES = sa.Table(
    "semantic_commerce_order_lines", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("order_no", sa.String(60), primary_key=True),
    sa.Column("line_no", sa.Integer, primary_key=True),
    sa.Column("barcode", sa.String(40), index=True),
    sa.Column("code", sa.String(80)),
    sa.Column("book_id", sa.String(40)),                               # CRM new_kitapId (barkod eşleşmesi)
    sa.Column("qty", sa.Float, nullable=False, default=0.0),
    sa.Column("amount", sa.Float, nullable=False, default=0.0),
)
CUSTOMERS = sa.Table(
    "semantic_commerce_customers", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("customer_key", sa.String(64), primary_key=True),
    sa.Column("member_ref", sa.String(40)),
    sa.Column("last_order_no", sa.String(60)),
    sa.Column("email_hash", sa.String(64)),                            # H2 özeti (READERS_HASH_SALT)
    sa.Column("phone_hash", sa.String(64)),
    sa.Column("name_hash", sa.String(64)),
    sa.Column("city", sa.String(80)),
    sa.Column("consent_json", sa.Text),                                # T-soft üye izni: [{channel,status,at,detail}]
    sa.Column("member_since", sa.DateTime),
    sa.Column("first_order", sa.DateTime),
    sa.Column("last_order", sa.DateTime),
    sa.Column("orders", sa.Integer, nullable=False, default=0),
    sa.Column("revenue", sa.Float, nullable=False, default=0.0),
    sa.Column("r_score", sa.Integer),
    sa.Column("f_score", sa.Integer),
    sa.Column("m_score", sa.Integer),
    sa.Column("segment", sa.String(16), nullable=False),
    sa.Column("segment_since", sa.DateTime(timezone=True)),
    sa.Column("nodes_json", sa.Text),                                  # aldığı kategori düğümleri: {düğüm: adet}
    sa.Column("is_guest", sa.Boolean, nullable=False, default=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_semantic_commerce_customers_seg", "tenant_id", "segment"),
)
MOVES = sa.Table(
    "semantic_commerce_segment_moves", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("customer_key", sa.String(64), nullable=False),
    sa.Column("from_segment", sa.String(16)),
    sa.Column("to_segment", sa.String(16), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
)
PRODUCT_STATS = sa.Table(
    "semantic_commerce_product_stats", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("barcode", sa.String(40), primary_key=True),
    sa.Column("day", sa.Date, primary_key=True),                       # görüntülenmenin biriktiği gün (gece önceki gün)
    sa.Column("views_total", sa.Integer),
    sa.Column("views_delta", sa.Integer),                              # önceki anlık görüntüden fark; ilk gün boş
    sa.Column("orders", sa.Integer, nullable=False, default=0),
    sa.Column("qty", sa.Float, nullable=False, default=0.0),
    sa.Column("name", sa.String(500)),
)
TRIGGERS = sa.Table(
    "semantic_commerce_triggers", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("kind", sa.String(16), nullable=False),                  # yeni-kitap | geri-kazanim | ikinci-siparis | terk-sepeti
    sa.Column("params_json", sa.Text, nullable=False),
    sa.Column("channel", sa.String(8), nullable=False),                # email | sms | call
    sa.Column("control_share", sa.Float, nullable=False),
    sa.Column("status", sa.String(10), nullable=False),                # etkin | arsiv
    sa.Column("owner", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
RUNS = sa.Table(
    "semantic_commerce_trigger_runs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("trigger_id", sa.String(32), nullable=False),
    sa.Column("trigger_name", sa.String(200)),
    sa.Column("kind", sa.String(16), nullable=False),
    sa.Column("params_json", sa.Text),
    sa.Column("channel", sa.String(8), nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("candidates", sa.Integer, nullable=False),
    sa.Column("linked", sa.Integer, nullable=False),
    sa.Column("consented", sa.Integer, nullable=False),                # ulaşılabilir (izinli + dışa aktarılabilir)
    sa.Column("target", sa.Integer, nullable=False),
    sa.Column("control", sa.Integer, nullable=False),
    sa.Column("control_share", sa.Float, nullable=False),
    sa.Column("excluded_json", sa.Text),
    sa.Column("status", sa.String(14), nullable=False),                # onay-bekliyor | onayli | geri-gonderildi | aktarildi
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("decision_note", sa.String(1000)),
    sa.Column("export_id", sa.String(32)),                             # H2 semantic_reader_exports
    sa.Column("exported_by", sa.String(120)),
    sa.Column("exported_at", sa.DateTime(timezone=True)),
    sa.Column("exported_count", sa.Integer),
)
RUN_MEMBERS = sa.Table(
    "semantic_commerce_run_members", _md,
    sa.Column("run_id", sa.String(32), primary_key=True),
    sa.Column("customer_key", sa.String(64), primary_key=True),
    sa.Column("grp", sa.String(8), nullable=False),                    # hedef | kontrol
    sa.Column("reader_id", sa.String(24)),
)
CAMPAIGNS = sa.Table(
    "semantic_commerce_campaigns", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("name", sa.String(200), nullable=False),
    sa.Column("trigger_run_id", sa.String(32), nullable=False),
    sa.Column("start_day", sa.Date, nullable=False),
    sa.Column("end_day", sa.Date, nullable=False),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("result_json", sa.Text),
    sa.Column("result_at", sa.DateTime(timezone=True)),
    sa.Column("final", sa.Boolean, nullable=False, default=False),
    sa.Column("comment", sa.Text),                                     # Zeki AI yorumu (rakamsız)
    sa.Column("comment_at", sa.DateTime(timezone=True)),
)
SETTINGS = sa.Table(
    "semantic_commerce_settings", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(40), primary_key=True),
    sa.Column("value", sa.String(200), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
META = sa.Table(
    "semantic_commerce_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(40), primary_key=True),
    sa.Column("value", sa.Text),
)

_lock = threading.Lock()
_ready: set[int] = set()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(v: Any) -> Optional[datetime]:
    return R._utc(v)


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat() if v.tzinfo else v.isoformat(timespec="seconds")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _load(v: Optional[str], default: Any) -> Any:
    return R._load(v, default)


def meta_get(engine: sa.engine.Engine, tenant: str, key: str, default: Any = None) -> Any:
    with engine.connect() as c:
        v = c.execute(sa.select(META.c.value).where(META.c.tenant_id == tenant, META.c.key == key)).scalar()
    return _load(v, default) if v is not None else default


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: Any, conn: Any = None) -> None:
    def w(c: Any) -> None:
        c.execute(META.delete().where(META.c.tenant_id == tenant, META.c.key == key))
        c.execute(META.insert().values(tenant_id=tenant, key=key, value=_dump(value)))
    if conn is not None:
        w(conn)
    else:
        with engine.begin() as c:
            w(c)


# ------------------------------------------------------------------ ayarlar

SEGMENTS = ("ilk", "aktif", "sadik", "kayip", "siparissiz")
SEGMENT_LABELS = {"ilk": "İlk alıcı", "aktif": "Aktif", "sadik": "Sadık", "kayip": "Kayıp", "siparissiz": "Üye, siparişi yok"}
KINDS = {"yeni-kitap": "Yeni kitap (ilgi alanı)", "geri-kazanim": "Geri kazanım", "ikinci-siparis": "İkinci sipariş",
         "terk-sepeti": "Terk sepeti"}
RUN_STATUS = {"onay-bekliyor": "Onay bekliyor", "onayli": "Onaylı", "geri-gonderildi": "Geri gönderildi",
              "aktarildi": "Dışa aktarıldı"}
R_BUCKETS = [(30, "0–30 gün"), (90, "31–90 gün"), (180, "91–180 gün"), (365, "181–365 gün"), (None, "365+ gün")]
F_BUCKETS = [(1, "1"), (2, "2"), (4, "3–4"), (9, "5–9"), (None, "10+")]

#: Ekrandan değişen eşikler (tablo > ortam/Yönetim `COMMERCE_<ANAHTAR>` > varsayılan). Ölçülmemiş varsayımlardır.
SCREEN_DEFAULTS: dict[str, float] = {
    "activeDays": 90, "loyalOrders": 4, "loyalRevenue": 0, "controlShare": 0.10, "resultWindowDays": 14,
    "resultLagDays": 14, "dropPct": 30, "newBookDays": 60, "lookbackDays": 730, "minViews": 200,
}
_SCREEN_ENV = {"activeDays": "COMMERCE_ACTIVE_DAYS", "loyalOrders": "COMMERCE_LOYAL_ORDERS",
               "loyalRevenue": "COMMERCE_LOYAL_REVENUE", "controlShare": "COMMERCE_CONTROL_SHARE",
               "resultWindowDays": "COMMERCE_RESULT_WINDOW_DAYS", "resultLagDays": "COMMERCE_RESULT_LAG_DAYS",
               "dropPct": "COMMERCE_DROP_PCT", "newBookDays": "COMMERCE_NEW_BOOK_DAYS",
               "lookbackDays": "COMMERCE_LOOKBACK_DAYS", "minViews": "COMMERCE_MIN_VIEWS"}
_LIMITS = {"activeDays": (7, 1095), "loyalOrders": (2, 100), "loyalRevenue": (0, 10_000_000), "controlShare": (0.0, 0.5),
           "resultWindowDays": (1, 120), "resultLagDays": (0, 90), "dropPct": (1, 95), "newBookDays": (1, 365),
           "lookbackDays": (30, 3650), "minViews": (0, 1_000_000)}
SCREEN_LABELS = {"activeDays": "Aktif/kayıp sınırı (gün)", "loyalOrders": "Sadık: en az sipariş",
                 "loyalRevenue": "Sadık: en az ciro (0 = kullanılmaz)", "controlShare": "Kontrol grubu payı",
                 "resultWindowDays": "Kampanya sonuç penceresi (gün)", "resultLagDays": "Sonuç kesinleşmesi (bitişten sonra gün)",
                 "dropPct": "Sipariş düşüşü uyarısı (%)", "newBookDays": "Yeni kitap: son kaç günde açılan",
                 "lookbackDays": "İlgi alanı: son kaç günün siparişi", "minViews": "Huni: en az görüntülenme"}


def _num(v: Any, default: float) -> float:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return default


def settings(engine: sa.engine.Engine, tenant: str, conf: Callable[[str, str], str]) -> dict[str, Any]:
    with engine.connect() as c:
        stored = {r.key: r.value for r in c.execute(sa.select(SETTINGS).where(SETTINGS.c.tenant_id == tenant))}
    out: dict[str, Any] = {}
    for k, d in SCREEN_DEFAULTS.items():
        raw = stored.get(k)
        if raw in (None, ""):
            raw = conf(_SCREEN_ENV[k], "") or ""
        v = _num(raw, d) if raw not in (None, "") else d
        lo, hi = _LIMITS[k]
        out[k] = min(hi, max(lo, v))
    for k in ("activeDays", "loyalOrders", "resultWindowDays", "resultLagDays", "newBookDays", "lookbackDays", "minViews"):
        out[k] = int(out[k])
    out["cancelStatuses"] = [s.strip() for s in (conf("COMMERCE_CANCEL_STATUSES", "") or "").split(",") if s.strip()]
    out["falseIsRet"] = str(conf("COMMERCE_TSOFT_FALSE_IS_RET", "1") or "1").strip().lower() in ("1", "true", "evet", "on")
    out["resyncDays"] = int(_num(conf("COMMERCE_RESYNC_DAYS", "7") or "7", 7))
    out["staleHours"] = int(_num(conf("COMMERCE_STALE_HOURS", "30") or "30", 30))
    out["memberPath"] = (conf("COMMERCE_TSOFT_MEMBER_PATH", "customer/get") or "").strip()
    out["orderPath"] = (conf("COMMERCE_TSOFT_ORDER_PATH", "order/get") or "order/get").strip()
    out["summaryTo"] = [x.strip() for x in (conf("COMMERCE_SUMMARY_RECIPIENTS", "") or "").split(",") if "@" in x]
    out["adminTo"] = [x.strip() for x in (conf("COMMERCE_ADMIN_RECIPIENTS", "") or "").split(",") if "@" in x]
    out["enabled"] = str(conf("COMMERCE_ENABLED", "1") or "1").strip().lower() in ("1", "true", "evet", "on")
    return out


def update_settings(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any],
                    conf: Callable[[str, str], str]) -> tuple[dict[str, Any], dict[str, Any]]:
    before = settings(engine, tenant, conf)
    diff: dict[str, Any] = {}
    now = _now()
    with engine.begin() as c:
        for k, v in (body or {}).items():
            if k not in SCREEN_DEFAULTS:
                raise CommerceError(f"«{k}» bu ekrandan değiştirilemez.")
            if v is None or v == "":
                c.execute(SETTINGS.delete().where(SETTINGS.c.tenant_id == tenant, SETTINGS.c.key == k))
                diff[k] = [before[k], None]
                continue
            x = _num(v, float("nan"))
            lo, hi = _LIMITS[k]
            if math.isnan(x) or not lo <= x <= hi:
                raise CommerceError(f"{SCREEN_LABELS[k]}: {lo}–{hi} arası olmalı.")
            c.execute(SETTINGS.delete().where(SETTINGS.c.tenant_id == tenant, SETTINGS.c.key == k))
            c.execute(SETTINGS.insert().values(tenant_id=tenant, key=k, value=str(x), updated_by=user, updated_at=now))
            if x != before[k]:
                diff[k] = [before[k], x]
    return settings(engine, tenant, conf), diff


# ------------------------------------------------------------------ RFM (saf)


def r_bucket(days: Optional[int]) -> int:
    """0..4 (R_BUCKETS sırası); r_score = 5 − bucket."""
    if days is None:
        return len(R_BUCKETS) - 1
    for i, (lim, _l) in enumerate(R_BUCKETS):
        if lim is None or days <= lim:
            return i
    return len(R_BUCKETS) - 1


def f_bucket(orders: int) -> int:
    for i, (lim, _l) in enumerate(F_BUCKETS):
        if lim is None or orders <= lim:
            return i
    return len(F_BUCKETS) - 1


def segment_of(orders: int, revenue: float, recency_days: Optional[int], st: dict[str, Any]) -> str:
    if orders <= 0:
        return "siparissiz"
    if recency_days is None or recency_days > st["activeDays"]:
        return "kayip"
    if orders >= st["loyalOrders"] or (st["loyalRevenue"] and revenue >= st["loyalRevenue"]):
        return "sadik"
    if orders == 1:
        return "ilk"
    return "aktif"


def m_scores(revenues: dict[str, float]) -> dict[str, int]:
    """Ciro beşte bir dilimi (1..5); eşit ciro aynı dilimde. Sipariş olmayan müşteri puansız."""
    vals = sorted(v for v in revenues.values())
    n = len(vals)
    out: dict[str, int] = {}
    if not n:
        return out
    cuts = [vals[min(n - 1, int(math.ceil(n * q / 5)) - 1)] for q in range(1, 5)]
    for k, v in revenues.items():
        out[k] = 1 + sum(1 for c in cuts if v > c)
    return out


# ------------------------------------------------------------------ okuma turu (yazma)


def _bulk(conn: Any, table: sa.Table, rows: list[dict[str, Any]], n: int = 1000) -> None:
    for i in range(0, len(rows), n):
        conn.execute(table.insert(), rows[i:i + n])


def sync(engine: sa.engine.Engine, tenant: str, client: Any, conf: Callable[[str, str], str], *, full: bool = False,
         today: Optional[date] = None, key: Optional[bytes] = None) -> dict[str, Any]:
    """T-soft sipariş (+ satır) ve üye okuması → sipariş tabloları → müşteri tablosu (RFM, geçiş) → ürün görüntülenme.
    İlk tur ve `full` bütün siparişleri okur; diğerleri son `resyncDays` günü (değişen durumlar dahil) yeniden yazar."""
    ensure(engine)
    k = key or R.salt()                                            # tuz yoksa hiçbir şey okunmaz
    st = settings(engine, tenant, conf)
    f = src.fields(conf)
    today = today or date.today()
    last = meta_get(engine, tenant, "sync", {}) or {}
    first_time = not last.get("okAt")
    since = None if (full or first_time) else today - timedelta(days=st["resyncDays"])
    t0 = time.monotonic()
    found: dict[str, str] = {}
    persons: dict[str, dict[str, Any]] = {}
    n_orders = n_lines = n_invalid = n_unkeyed = 0
    older = 0
    books = src.book_index(engine, tenant)["books"]
    now = _now()

    def note_person(ck: Optional[str], p: src.Person, member_ref: Optional[str], order_no: Optional[str],
                    at: Optional[datetime], guest: Optional[bool]) -> None:
        if not ck:
            return
        cur = persons.setdefault(ck, {})
        newer = at is not None and (cur.get("_at") is None or at >= cur["_at"])
        for a in ("email_hash", "phone_hash", "name_hash", "city"):
            v = getattr(p, a)
            if v and (newer or not cur.get(a)):
                cur[a] = v
        if member_ref and (newer or not cur.get("member_ref")):
            cur["member_ref"] = member_ref
        if order_no and newer:
            cur["last_order_no"], cur["_at"] = order_no, at
        if guest is not None:
            cur["is_guest"] = guest if cur.get("is_guest") is None else (cur["is_guest"] and guest)

    for page in src.pages(client, st["orderPath"], src.order_params(conf, since)):
        recs = [o for o in (src.order_of(r, f, k, st["cancelStatuses"], found) for r in page) if o]
        if not recs:
            continue
        rows, lines = [], []
        for o in recs:
            if since and o.ordered_at and o.ordered_at.date() < since:
                older += 1                                          # süzgeç yok sayılmış olabilir; yine yazılır
            n_invalid += int(not o.valid)
            n_unkeyed += int(o.customer_key is None)
            rows.append({"tenant_id": tenant, "order_no": o.order_no, "ordered_at": o.ordered_at, "status": o.status,
                         "valid": o.valid, "total": o.total, "discount": o.discount, "shipping": o.shipping,
                         "coupon": o.coupon, "payment": o.payment, "utm_source": o.utm_source,
                         "utm_campaign": o.utm_campaign, "customer_key": o.customer_key, "member_ref": o.member_ref,
                         "is_guest": o.is_guest, "synced_at": now})
            for i, ln in enumerate(o.lines):
                b = books.get(ln["barcode"] or "")
                lines.append({"tenant_id": tenant, "order_no": o.order_no, "line_no": i + 1, "barcode": ln["barcode"],
                              "code": ln["code"], "book_id": b["bookId"] if b else None, "qty": ln["qty"],
                              "amount": ln["amount"]})
            note_person(o.customer_key, o.person, o.member_ref, o.order_no, o.ordered_at, o.is_guest)
        nos = sorted({r["order_no"] for r in rows})
        # Aynı sayfada aynı sipariş iki kez gelirse son hâli yazılır.
        rows = list({r["order_no"]: r for r in rows}.values())
        lines = list({(ln["order_no"], ln["line_no"]): ln for ln in lines}.values())
        with engine.begin() as c:
            for part in src.chunks(nos):
                c.execute(LINES.delete().where(LINES.c.tenant_id == tenant, LINES.c.order_no.in_(part)))
                c.execute(ORDERS.delete().where(ORDERS.c.tenant_id == tenant, ORDERS.c.order_no.in_(part)))
            _bulk(c, ORDERS, rows)
            _bulk(c, LINES, lines)
        n_orders += len(rows)
        n_lines += len(lines)

    members: dict[str, src.MemberRec] = {}
    member_error = None
    if st["memberPath"] and st["memberPath"] != "-":
        try:
            for page in src.pages(client, st["memberPath"], {}):
                for r in page:
                    m = src.member_of(r, f, k, st["falseIsRet"], found)
                    if m and m.customer_key:
                        members[m.customer_key] = m
                        note_person(m.customer_key, m.person, m.member_ref, None, None, False)
        except Exception as e:  # noqa: BLE001 — üye okunamazsa siparişten kurulan müşteri tablosu yine yazılır
            member_error = str(e)[:500]
            log.warning("commerce: T-soft üyeleri okunamadı: %s", e)

    cust = rebuild_customers(engine, tenant, st, persons, members, today)
    stats = product_snapshot(engine, tenant, today)
    missing = [r for r in ("order_no", "ordered_at", "status", "total", "customer_id", "email", "lines", "line_barcode",
                           "line_qty", "line_amount") if r not in found]
    info = {"okAt": _iso(now), "full": since is None, "since": _iso(since), "orders": n_orders, "lines": n_lines,
            "invalid": n_invalid, "unkeyed": n_unkeyed, "olderThanSince": older, "members": len(members),
            "memberError": member_error, "customers": cust["customers"], "moves": cust["moves"],
            "productDays": stats, "fields": found, "missing": missing, "seconds": round(time.monotonic() - t0, 1),
            "error": None, "errorAt": None}
    with engine.begin() as c:
        meta_set(engine, tenant, "sync", info, c)
        meta_set(engine, tenant, "stamp", _iso(now), c)
    return info


def record_error(engine: sa.engine.Engine, tenant: str, message: str) -> None:
    ensure(engine)
    info = meta_get(engine, tenant, "sync", {}) or {}
    info.update(error=message[:1000], errorAt=_iso(_now()))
    meta_set(engine, tenant, "sync", info)


def rebuild_customers(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], persons: dict[str, dict[str, Any]],
                      members: dict[str, Any], today: date) -> dict[str, int]:
    """Müşteri tablosunu sipariş tablosundan yeniden kurar (geçerli siparişler). Önceki kişisel özetler korunur,
    bu turda gelen özetler üzerine yazılır. Segment değişimi geçiş kaydıdır."""
    books = src.book_index(engine, tenant)["books"]
    with engine.connect() as c:
        old = {r.customer_key: r for r in c.execute(sa.select(CUSTOMERS).where(CUSTOMERS.c.tenant_id == tenant))}
        agg = {r.customer_key: r for r in c.execute(
            sa.select(ORDERS.c.customer_key, sa.func.count().label("n"), sa.func.sum(ORDERS.c.total).label("rev"),
                      sa.func.min(ORDERS.c.ordered_at).label("first"), sa.func.max(ORDERS.c.ordered_at).label("last"))
            .where(ORDERS.c.tenant_id == tenant, ORDERS.c.valid.is_(True), ORDERS.c.customer_key.isnot(None))
            .group_by(ORDERS.c.customer_key))}
        guests = {r.customer_key: bool(r.g) for r in c.execute(
            sa.select(ORDERS.c.customer_key, sa.func.min(sa.case((ORDERS.c.is_guest.is_(True), 1), else_=0)).label("g"))
            .where(ORDERS.c.tenant_id == tenant, ORDERS.c.customer_key.isnot(None)).group_by(ORDERS.c.customer_key))}
        last_no = {}
        for r in c.execute(sa.select(ORDERS.c.customer_key, ORDERS.c.order_no, ORDERS.c.ordered_at)
                           .where(ORDERS.c.tenant_id == tenant, ORDERS.c.customer_key.isnot(None))):
            cur = last_no.get(r.customer_key)
            if cur is None or (r.ordered_at and (cur[1] is None or r.ordered_at > cur[1])):
                last_no[r.customer_key] = (r.order_no, r.ordered_at)
        nodes: dict[str, Counter] = defaultdict(Counter)
        cut = datetime.combine(today - timedelta(days=st["lookbackDays"]), datetime.min.time())
        for r in c.execute(sa.select(ORDERS.c.customer_key, LINES.c.barcode, LINES.c.qty)
                           .select_from(LINES.join(ORDERS, sa.and_(ORDERS.c.tenant_id == LINES.c.tenant_id,
                                                                   ORDERS.c.order_no == LINES.c.order_no)))
                           .where(LINES.c.tenant_id == tenant, ORDERS.c.valid.is_(True), ORDERS.c.ordered_at >= cut,
                                  ORDERS.c.customer_key.isnot(None))):
            b = books.get(r.barcode or "")
            if b and b.get("node"):
                nodes[r.customer_key][b["node"]] += int(r.qty or 1)
    keys = set(agg) | set(members) | set(old)
    ms = m_scores({kk: float(a.rev or 0) for kk, a in agg.items()})
    now = _now()
    rows, moves = [], []
    for ck in keys:
        a = agg.get(ck)
        o = old.get(ck)
        p = persons.get(ck, {})
        m = members.get(ck)
        if a is None and m is None and o is not None and not o.member_ref:
            continue                                            # siparişi silinmiş/geçersizleşmiş misafir: düşer
        n = int(a.n) if a else 0
        rev = float(a.rev or 0) if a else 0.0
        last = a.last if a else None
        rec = (today - last.date()).days if last else None
        seg = segment_of(n, rev, rec, st)
        prev = o.segment if o else None
        since = (o.segment_since if o and prev == seg else now)
        if prev != seg and (o is not None):
            moves.append({"id": uuid.uuid4().hex, "tenant_id": tenant, "customer_key": ck, "from_segment": prev,
                          "to_segment": seg, "at": now})
        consent = ([{"channel": e.channel, "status": e.status, "at": _iso(e.at), "detail": e.detail} for e in m.evidences]
                   if m else _load(o.consent_json, []) if o else [])
        pick = lambda a_: p.get(a_) or (getattr(o, a_) if o else None)  # noqa: E731
        rows.append({
            "tenant_id": tenant, "customer_key": ck, "member_ref": pick("member_ref") or (m.member_ref if m else None),
            "last_order_no": (last_no.get(ck) or (None,))[0] or (o.last_order_no if o else None),
            "email_hash": pick("email_hash"), "phone_hash": pick("phone_hash"), "name_hash": pick("name_hash"),
            "city": pick("city"), "consent_json": _dump(consent),
            "member_since": (m.created if m else None) or (o.member_since if o else None),
            "first_order": a.first if a else None, "last_order": last, "orders": n, "revenue": round(rev, 2),
            "r_score": (5 - r_bucket(rec)) if n else None, "f_score": (f_bucket(n) + 1) if n else None,
            "m_score": ms.get(ck), "segment": seg, "segment_since": since,
            "nodes_json": _dump(dict(nodes.get(ck, {}))), "is_guest": guests.get(ck, False) if n else False,
            "updated_at": now})
    with engine.begin() as c:
        c.execute(CUSTOMERS.delete().where(CUSTOMERS.c.tenant_id == tenant))
        _bulk(c, CUSTOMERS, rows)
        _bulk(c, MOVES, moves)
    _facts_invalidate()
    return {"customers": len(rows), "moves": len(moves)}


def product_snapshot(engine: sa.engine.Engine, tenant: str, today: date) -> int:
    """SEO eşitlemesindeki toplam görüntülenmenin bugünkü hâli; önceki anlık görüntüden fark dünün görüntülenmesidir.
    Aynı gün ikinci kez koşarsa o günün satırı yenilenir."""
    prods = [p for p in src.site_products(engine, tenant) if p["barcode"]]
    if not prods:
        return 0
    day = today - timedelta(days=1)
    lo, hi = src.day_range(day)
    with engine.connect() as c:
        prev: dict[str, int] = {}
        for r in c.execute(sa.select(PRODUCT_STATS.c.barcode, PRODUCT_STATS.c.views_total, PRODUCT_STATS.c.day)
                           .where(PRODUCT_STATS.c.tenant_id == tenant, PRODUCT_STATS.c.day < day)
                           .order_by(PRODUCT_STATS.c.day)):
            if r.views_total is not None:
                prev[r.barcode] = int(r.views_total)
        sold: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
        for r in c.execute(sa.select(LINES.c.barcode, LINES.c.order_no, LINES.c.qty)
                           .select_from(LINES.join(ORDERS, sa.and_(ORDERS.c.tenant_id == LINES.c.tenant_id,
                                                                   ORDERS.c.order_no == LINES.c.order_no)))
                           .where(LINES.c.tenant_id == tenant, ORDERS.c.valid.is_(True), ORDERS.c.ordered_at >= lo,
                                  ORDERS.c.ordered_at < hi)):
            sold[r.barcode or ""][0] += 1
            sold[r.barcode or ""][1] += float(r.qty or 0)
    by_code: dict[str, dict[str, Any]] = {}
    for p in prods:
        cur = by_code.get(p["barcode"])
        if cur is None:
            by_code[p["barcode"]] = dict(p)
        elif p["views"] is not None:                              # aynı barkodlu iki ürün: görüntülenme toplanır
            cur["views"] = (cur["views"] or 0) + p["views"]
    rows = []
    for bc, p in by_code.items():
        tot = p["views"]
        delta = (tot - prev[bc]) if (tot is not None and bc in prev and tot >= prev[bc]) else None
        rows.append({"tenant_id": tenant, "barcode": bc, "day": day, "views_total": tot, "views_delta": delta,
                     "orders": int(sold.get(bc, [0, 0])[0]), "qty": float(sold.get(bc, [0, 0.0])[1]),
                     "name": (p["name"] or "")[:500] or None})
    with engine.begin() as c:
        c.execute(PRODUCT_STATS.delete().where(PRODUCT_STATS.c.tenant_id == tenant, PRODUCT_STATS.c.day == day))
        _bulk(c, PRODUCT_STATS, rows)
    return len(rows)


# ------------------------------------------------------------------ tazelik


def freshness(engine: sa.engine.Engine, tenant: str, st: dict[str, Any]) -> dict[str, Any]:
    info = meta_get(engine, tenant, "sync", {}) or {}
    ok_at = _utc(info.get("okAt"))
    err_at = _utc(info.get("errorAt"))
    with engine.connect() as c:
        last_order = c.execute(sa.select(sa.func.max(ORDERS.c.ordered_at)).where(ORDERS.c.tenant_id == tenant)).scalar()
    return {"okAt": _iso(ok_at), "stale": ok_at is None or (_now() - ok_at).total_seconds() > st["staleHours"] * 3600,
            "error": info.get("error") if err_at and (ok_at is None or err_at >= ok_at) else None,
            "lastOrder": _iso(last_order), "full": info.get("full"), "missing": info.get("missing") or [],
            "fields": info.get("fields") or {}, "memberError": info.get("memberError"),
            "orders": info.get("orders"), "invalid": info.get("invalid"), "unkeyed": info.get("unkeyed"),
            "members": info.get("members"), "olderThanSince": info.get("olderThanSince")}


def has_data(engine: sa.engine.Engine, tenant: str) -> bool:
    return bool((meta_get(engine, tenant, "sync", {}) or {}).get("okAt"))


# ------------------------------------------------------------------ özet


def windows(period: str, today: date) -> tuple[date, date, date, date, str]:
    """(başlangıç, bitiş hariç, önceki başlangıç, önceki bitiş hariç, etiket). Gece okuması: dün tam gündür."""
    if period == "dun":
        s = today - timedelta(days=1)
        return s, today, s - timedelta(days=7), today - timedelta(days=7), "Dün (geçen haftanın aynı günüyle)"
    if period == "hafta":
        s = today - timedelta(days=7)
        return s, today, s - timedelta(days=7), s, "Son 7 gün (önceki 7 günle)"
    if period == "ay":
        s = today.replace(day=1) if today.day > 1 else (today - timedelta(days=1)).replace(day=1)
        e = today if today.day > 1 else today
        n = (e - s).days
        ps = (s - timedelta(days=1)).replace(day=1)
        pe = min(ps + timedelta(days=n), s)
        return s, e, ps, pe, "Bu ay (geçen ayın aynı günleriyle)"
    raise CommerceError("Dönem dun, hafta ya da ay olmalı.")


def _window_stats(engine: sa.engine.Engine, tenant: str, s: date, e: date) -> dict[str, Any]:
    lo, hi = datetime.combine(s, datetime.min.time()), datetime.combine(e, datetime.min.time())
    with engine.connect() as c:
        rows = list(c.execute(sa.select(ORDERS.c.valid, ORDERS.c.total, ORDERS.c.customer_key, ORDERS.c.is_guest)
                              .where(ORDERS.c.tenant_id == tenant, ORDERS.c.ordered_at >= lo, ORDERS.c.ordered_at < hi)))
        keys = sorted({r.customer_key for r in rows if r.valid and r.customer_key})
        firsts: dict[str, Any] = {}
        for part in src.chunks(keys):
            for r in c.execute(sa.select(ORDERS.c.customer_key, sa.func.min(ORDERS.c.ordered_at).label("f"))
                               .where(ORDERS.c.tenant_id == tenant, ORDERS.c.valid.is_(True), ORDERS.c.customer_key.in_(part))
                               .group_by(ORDERS.c.customer_key)):
                firsts[r.customer_key] = r.f
    valid = [r for r in rows if r.valid]
    rev = sum(float(r.total or 0) for r in valid)
    new = sum(1 for k in keys if firsts.get(k) is not None and lo <= firsts[k] < hi)
    return {"siparis": len(valid), "ciro": round(rev, 2), "sepet": round(rev / len(valid), 2) if valid else None,
            "musteri": len(keys), "yeni": new, "tekrar": len(keys) - new, "iptal": len(rows) - len(valid),
            "misafir": sum(1 for r in valid if r.is_guest), "anahtarsiz": sum(1 for r in valid if not r.customer_key)}


def _change(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev in (None, 0):
        return None
    return round(cur / prev - 1, 4)


def top_books(engine: sa.engine.Engine, tenant: str, s: date, e: date, n: Optional[int] = 10) -> list[dict[str, Any]]:
    lo, hi = datetime.combine(s, datetime.min.time()), datetime.combine(e, datetime.min.time())
    agg: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    with engine.connect() as c:
        for r in c.execute(sa.select(LINES.c.barcode, LINES.c.code, LINES.c.qty, LINES.c.amount)
                           .select_from(LINES.join(ORDERS, sa.and_(ORDERS.c.tenant_id == LINES.c.tenant_id,
                                                                   ORDERS.c.order_no == LINES.c.order_no)))
                           .where(LINES.c.tenant_id == tenant, ORDERS.c.valid.is_(True), ORDERS.c.ordered_at >= lo,
                                  ORDERS.c.ordered_at < hi)):
            k = r.barcode or r.code or "?"
            agg[k][0] += float(r.qty or 0)
            agg[k][1] += float(r.amount or 0)
            agg[k][2] += 1
    names = book_names(engine, tenant, list(agg))
    out = [{"barkod": k, "ad": names.get(k), "adet": round(v[0], 2), "tutar": round(v[1], 2), "siparis": int(v[2])}
           for k, v in agg.items()]
    out.sort(key=lambda x: (-x["adet"], -x["tutar"], x["barkod"]))
    return out if n is None else out[:n]


def book_names(engine: sa.engine.Engine, tenant: str, barcodes: list[str]) -> dict[str, str]:
    idx = src.book_index(engine, tenant)["books"]
    out = {b: idx[b]["name"] for b in barcodes if b in idx and idx[b].get("name")}
    miss = [b for b in barcodes if b not in out]
    if miss:
        for p in src.site_products(engine, tenant):
            if p["barcode"] in miss and p["name"] and p["barcode"] not in out:
                out[p["barcode"]] = p["name"]
    return out


def drop_alert(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], today: date) -> dict[str, Any]:
    """Dünün geçerli sipariş sayısı önceki dört haftanın aynı gününün ortalamasına göre `dropPct`'ten fazla düştüyse."""
    y = today - timedelta(days=1)
    cur = _window_stats(engine, tenant, y, today)["siparis"]
    prev = [_window_stats(engine, tenant, y - timedelta(days=7 * i), y - timedelta(days=7 * i - 1))["siparis"] for i in range(1, 5)]
    base = sum(prev) / 4 if prev else 0
    fall = (1 - cur / base) if base else None
    return {"gun": y.isoformat(), "siparis": cur, "onceki4": prev, "ortalama": round(base, 2),
            "dusus": round(fall, 4) if fall is not None else None,
            "uyari": bool(fall is not None and fall * 100 >= st["dropPct"])}


def logo_d2c(engine: sa.engine.Engine, tenant: str, yil: int, ay: int) -> dict[str, Any]:
    """Logo'da timas.com.tr kanalına eşlenen carilerin net cirosu (M42 kanal karnesi, faturalı satır `LINENET`). Eşleme ya
    da yıl okuması yoksa nedeni döner; bu modül Logo'ya ayrıca bağlanmaz."""
    try:
        from semantic_bridge.channels import mapping as M
        from semantic_bridge.channels import scorecard as SC
    except Exception as e:  # noqa: BLE001
        return {"bagli": False, "neden": f"Kanal modülü yok: {e}"}
    try:
        card = SC.scorecard(engine, tenant, yil, ay)
    except SC.ChannelError as e:
        return {"bagli": False, "neden": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"bagli": False, "neden": f"Logo kanal verisi okunamadı: {str(e)[:160]}"}
    d = next((x for x in card["platforms"] if x["platform"] == M.D2C), None)
    if not d:
        return {"bagli": False, "neden": "timas.com.tr henüz bir Logo carisine ya da kanal koduna eşlenmedi (Kanallar › Cari eşleme)."}
    p = card["period"]
    return {"bagli": True, "yil": p["yil"], "ay": p["ay"], "ayAdi": p["ayAdi"], "kismiAy": p["kismiAy"],
            "veriSonu": p["veriSonu"], "netCiro": d["buAy"]["netCiro"], "grupSayisi": d["grupSayisi"]}


def overview(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], period: str = "dun",
             today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    s, e, ps, pe, label = windows(period, today)
    cur = _window_stats(engine, tenant, s, e)
    prev = _window_stats(engine, tenant, ps, pe)
    out: dict[str, Any] = {"period": {"key": period, "label": label, "from": s.isoformat(), "to": (e - timedelta(days=1)).isoformat(),
                                      "prevFrom": ps.isoformat(), "prevTo": (pe - timedelta(days=1)).isoformat()},
                           "cur": cur, "prev": prev,
                           "change": {k: _change(cur[k], prev[k]) for k in ("siparis", "ciro", "sepet", "musteri", "yeni")},
                           "top": top_books(engine, tenant, s, e), "freshness": freshness(engine, tenant, st),
                           "drop": drop_alert(engine, tenant, st, today)}
    # Logo uzlaşması aylıktır (M42 kanal karnesi ay kırılımlı): pencerenin başladığı ayın bütün site cirosu ile.
    m0 = s.replace(day=1)
    logo = logo_d2c(engine, tenant, m0.year, m0.month)
    if logo.get("bagli"):
        if (logo["yil"], logo["ay"]) != (m0.year, m0.month):
            # Logo verisi seçilen aydan önce bitiyor (ör. donmuş kopya): kıyas Logo'nun son ayıyla yapılır.
            logo["ayKaydi"] = (f"Logo verisi {logo.get('veriSonu') or 'daha önce'} tarihinde bitiyor; kıyas "
                               f"{logo['ayAdi']} {logo['yil']} ile.")
            m0 = date(logo["yil"], logo["ay"], 1)
        m1 = (m0 + timedelta(days=32)).replace(day=1)
        end = m1
        if logo.get("veriSonu"):
            vs = date.fromisoformat(logo["veriSonu"][:10])
            if vs.year == m0.year and vs.month == m0.month:
                end = vs + timedelta(days=1)                      # Logo verisinin bittiği güne kadar kıyasla
        site = _window_stats(engine, tenant, m0, min(end, m1))
        logo["siteCiro"] = site["ciro"]
        logo["siteDonem"] = {"from": m0.isoformat(), "to": (min(end, m1) - timedelta(days=1)).isoformat()}
        logo["fark"] = round(site["ciro"] - float(logo["netCiro"] or 0), 2)
        logo["farkOrani"] = _change(site["ciro"], logo["netCiro"])
        logo["not"] = ("Site tutarı sitenin kendi kaydıdır (KDV ve kargo dahil olabilir, iptal edilen sipariş düşülmüştür); "
                       "Logo net cirosu faturalı satırdır (KDV hariç, iade eksi). Fark bu tanım farkını da içerir.")
    out["logo"] = logo
    out["segments"] = segment_counts(engine, tenant)
    return out


# ------------------------------------------------------------------ RFM ekranları


def segment_counts(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = {r.segment: r for r in c.execute(
            sa.select(CUSTOMERS.c.segment, sa.func.count().label("n"), sa.func.sum(CUSTOMERS.c.revenue).label("rev"),
                      sa.func.sum(CUSTOMERS.c.orders).label("ord"))
            .where(CUSTOMERS.c.tenant_id == tenant).group_by(CUSTOMERS.c.segment))}
    tot = sum(int(r.n) for r in rows.values())
    return [{"segment": s, "label": SEGMENT_LABELS[s], "musteri": int(rows[s].n) if s in rows else 0,
             "ciro": round(float(rows[s].rev or 0), 2) if s in rows else 0.0,
             "siparis": int(rows[s].ord or 0) if s in rows else 0,
             "pay": round(int(rows[s].n) / tot, 4) if s in rows and tot else None} for s in SEGMENTS]


def rfm(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], today: Optional[date] = None,
        move_days: int = 30) -> dict[str, Any]:
    today = today or date.today()
    cells: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0, 0.0])
    with engine.connect() as c:
        for r in c.execute(sa.select(CUSTOMERS.c.orders, CUSTOMERS.c.revenue, CUSTOMERS.c.last_order)
                           .where(CUSTOMERS.c.tenant_id == tenant, CUSTOMERS.c.orders > 0)):
            rec = (today - r.last_order.date()).days if r.last_order else None
            cell = cells[(r_bucket(rec), f_bucket(int(r.orders)))]
            cell[0] += 1
            cell[1] += float(r.revenue or 0)
    matrix = [{"r": ri, "f": fi, "musteri": int(v[0]), "ciro": round(v[1], 2)} for (ri, fi), v in sorted(cells.items())]
    return {"rows": [lab for _l, lab in R_BUCKETS], "cols": [lab for _l, lab in F_BUCKETS], "matrix": matrix,
            "segments": segment_counts(engine, tenant), "moves": moves(engine, tenant, move_days),
            "rules": {"activeDays": st["activeDays"], "loyalOrders": st["loyalOrders"], "loyalRevenue": st["loyalRevenue"]}}


def moves(engine: sa.engine.Engine, tenant: str, days: int = 30) -> dict[str, Any]:
    since = _now() - timedelta(days=max(1, days))
    with engine.connect() as c:
        rows = list(c.execute(sa.select(MOVES.c.from_segment, MOVES.c.to_segment, sa.func.count().label("n"))
                              .where(MOVES.c.tenant_id == tenant, MOVES.c.at >= since)
                              .group_by(MOVES.c.from_segment, MOVES.c.to_segment)))
    items = [{"from": r.from_segment, "fromLabel": SEGMENT_LABELS.get(r.from_segment or "", "—"), "to": r.to_segment,
              "toLabel": SEGMENT_LABELS.get(r.to_segment, r.to_segment), "musteri": int(r.n)} for r in rows]
    items.sort(key=lambda x: -x["musteri"])
    lost = {s: sum(x["musteri"] for x in items if x["from"] == s and x["to"] != s) for s in SEGMENTS}
    return {"days": days, "items": items, "kaybettigi": lost}


def _mask(key: str) -> str:
    return "MÜ-" + key[:8].upper()


def customers(engine: sa.engine.Engine, tenant: str, segment: str = "", page: int = 0, size: int = 50,
              sort: str = "son") -> dict[str, Any]:
    q = sa.select(CUSTOMERS).where(CUSTOMERS.c.tenant_id == tenant)
    cq = sa.select(sa.func.count()).select_from(CUSTOMERS).where(CUSTOMERS.c.tenant_id == tenant)
    if segment:
        if segment not in SEGMENTS:
            raise CommerceError("Bilinmeyen segment.")
        q = q.where(CUSTOMERS.c.segment == segment)
        cq = cq.where(CUSTOMERS.c.segment == segment)
    order = {"son": CUSTOMERS.c.last_order.desc(), "ciro": CUSTOMERS.c.revenue.desc(), "siparis": CUSTOMERS.c.orders.desc()}
    if sort not in order:
        raise CommerceError("Sıralama son, ciro ya da siparis olmalı.")
    with engine.connect() as c:
        total = c.execute(cq).scalar() or 0
        rows = list(c.execute(q.order_by(order[sort], CUSTOMERS.c.customer_key).offset(max(0, page) * size).limit(size)))
    return {"items": [_customer_view(r) for r in rows], "total": total, "page": page, "pageSize": size}


def _customer_view(r: Any) -> dict[str, Any]:
    return {"key": r.customer_key, "etiket": _mask(r.customer_key), "segment": r.segment,
            "segmentLabel": SEGMENT_LABELS.get(r.segment, r.segment), "siparis": r.orders, "ciro": r.revenue,
            "ilkSiparis": _iso(r.first_order), "sonSiparis": _iso(r.last_order), "il": r.city, "misafir": bool(r.is_guest),
            "uye": bool(r.member_ref), "uyelik": _iso(r.member_since), "r": r.r_score, "f": r.f_score, "m": r.m_score,
            "segmentTarihi": _iso(r.segment_since)}


def customer_row(engine: sa.engine.Engine, tenant: str, key: str) -> Any:
    with engine.connect() as c:
        r = c.execute(sa.select(CUSTOMERS).where(CUSTOMERS.c.tenant_id == tenant, CUSTOMERS.c.customer_key == key)).first()
    if not r:
        raise CommerceError("Müşteri bulunamadı.", 404)
    return r


def reader_of(engine: sa.engine.Engine, tenant: str, keys: Iterable[str]) -> dict[str, str]:
    """Müşteri anahtarı → H2 etkin okur (H2 bağ tablosundaki `tsoft_member` kaydı)."""
    want = sorted(set(keys))
    out: dict[str, str] = {}
    if not want:
        return out
    R.ensure(engine)
    with engine.connect() as c:
        for part in src.chunks(want):
            for r in c.execute(sa.select(R.LINKS.c.source_id, R.LINKS.c.reader_id).where(
                    R.LINKS.c.tenant_id == tenant, R.LINKS.c.source == SOURCE, R.LINKS.c.source_id.in_(part))):
                out[r.source_id] = r.reader_id
    return out


def customer_card(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    r = customer_row(engine, tenant, key)
    with engine.connect() as c:
        orders = list(c.execute(sa.select(ORDERS).where(ORDERS.c.tenant_id == tenant, ORDERS.c.customer_key == key)
                                .order_by(ORDERS.c.ordered_at.desc())))
        nos = [o.order_no for o in orders]
        lines: dict[str, list[Any]] = defaultdict(list)
        for part in src.chunks(nos):
            for ln in c.execute(sa.select(LINES).where(LINES.c.tenant_id == tenant, LINES.c.order_no.in_(part))
                                .order_by(LINES.c.order_no, LINES.c.line_no)):
                lines[ln.order_no].append(ln)
        mv = list(c.execute(sa.select(MOVES).where(MOVES.c.tenant_id == tenant, MOVES.c.customer_key == key)
                            .order_by(MOVES.c.at.desc())))
    names = book_names(engine, tenant, sorted({ln.barcode for ls in lines.values() for ln in ls if ln.barcode}))
    nodes = src.book_index(engine, tenant)["nodes"]
    rid = reader_of(engine, tenant, [key]).get(key)
    alive = None
    consents = None
    if rid:
        try:
            alive = R._alive_id(engine, tenant, rid)
        except R.ReadersError:
            alive = None
        if alive:
            consents = R.consents_of(engine, tenant, [alive]).get(alive)
    return {
        **_customer_view(r),
        "siparisler": [{"no": o.order_no, "tarih": _iso(o.ordered_at), "durum": o.status, "gecerli": bool(o.valid),
                        "tutar": o.total, "indirim": o.discount, "kargo": o.shipping, "kupon": o.coupon, "odeme": o.payment,
                        "utmKaynak": o.utm_source, "utmKampanya": o.utm_campaign, "misafir": bool(o.is_guest),
                        "satirlar": [{"barkod": ln.barcode, "ad": names.get(ln.barcode or ""), "adet": ln.qty,
                                      "tutar": ln.amount, "kitap": ln.book_id} for ln in lines.get(o.order_no, [])]}
                       for o in orders],
        "iadeIptal": sum(1 for o in orders if not o.valid),
        "gecisler": [{"from": m.from_segment, "fromLabel": SEGMENT_LABELS.get(m.from_segment or "", "—"), "to": m.to_segment,
                      "toLabel": SEGMENT_LABELS.get(m.to_segment, m.to_segment), "at": _iso(m.at)} for m in mv],
        "kategoriler": [{"id": n, "ad": (nodes.get(n) or {}).get("name") or n, "adet": q}
                        for n, q in sorted(_load(r.nodes_json, {}).items(), key=lambda kv: -kv[1])],
        "siteIzni": _load(r.consent_json, []), "okur": alive, "izin": consents,
    }


# ------------------------------------------------------------------ ürün hunisi


def funnel(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], days: int = 30, page: int = 0, size: int = 100,
           only_weak: bool = False, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    days = max(1, min(int(days), 3650))
    s = today - timedelta(days=days)
    with engine.connect() as c:
        views: dict[str, list[Any]] = defaultdict(lambda: [0, 0, None, None])
        for r in c.execute(sa.select(PRODUCT_STATS).where(PRODUCT_STATS.c.tenant_id == tenant, PRODUCT_STATS.c.day >= s,
                                                         PRODUCT_STATS.c.day < today)):
            v = views[r.barcode]
            if r.views_delta is not None:
                v[0] += int(r.views_delta)
                v[1] += 1
            if v[2] is None or r.day > v[2]:
                v[2], v[3] = r.day, r.name
        covered = c.execute(sa.select(sa.func.count(sa.distinct(PRODUCT_STATS.c.day))).where(
            PRODUCT_STATS.c.tenant_id == tenant, PRODUCT_STATS.c.day >= s, PRODUCT_STATS.c.day < today,
            PRODUCT_STATS.c.views_delta.isnot(None))).scalar() or 0
    sales = {b["barkod"]: b for b in top_books(engine, tenant, s, today, None)}
    rows = []
    for bc in set(views) | set(sales):
        v = views.get(bc)
        sv = sales.get(bc) or {}
        vw = v[0] if v and v[1] else None
        qty = sv.get("adet", 0.0)
        rows.append({"barkod": bc, "ad": sv.get("ad") or (v[3] if v else None), "goruntulenme": vw,
                     "siparis": sv.get("siparis", 0), "adet": qty, "tutar": sv.get("tutar", 0.0),
                     "oran": round(qty / vw, 5) if vw else None})
    weak = [r for r in rows if r["goruntulenme"] is not None and r["goruntulenme"] >= st["minViews"]]
    weak.sort(key=lambda r: (r["oran"] if r["oran"] is not None else 0, -r["goruntulenme"]))
    base = weak if only_weak else sorted(rows, key=lambda r: (-(r["goruntulenme"] or 0), -r["adet"], r["barkod"]))
    return {"days": days, "coveredDays": int(covered), "minViews": st["minViews"], "total": len(base), "page": page,
            "pageSize": size, "items": base[max(0, page) * size:(max(0, page) + 1) * size], "weakCount": len(weak),
            "not": ("Görüntülenme T-soft'un toplam sayacının gece farkıdır (SEO eşitlemesinden); ilk gece fark yoktur. "
                    "Satış geçerli site siparişi satırıdır.")}


# ------------------------------------------------------------------ tetikler


def _clean_params(kind: str, p: dict[str, Any]) -> dict[str, Any]:
    p = p or {}

    def i(name: str, default: int, lo: int, hi: int) -> int:
        try:
            v = int(p.get(name, default))
        except (TypeError, ValueError):
            raise CommerceError(f"«{name}» sayı olmalı.") from None
        if not lo <= v <= hi:
            raise CommerceError(f"«{name}» {lo}–{hi} arası olmalı.")
        return v

    if kind == "geri-kazanim":
        lo, hi = i("minGun", 90, 1, 3650), i("maxGun", 365, 1, 3650)
        if hi < lo:
            raise CommerceError("En çok gün en az günden küçük olamaz.")
        return {"minGun": lo, "maxGun": hi, "minSiparis": i("minSiparis", 1, 1, 1000)}
    if kind == "ikinci-siparis":
        lo, hi = i("minGun", 14, 0, 3650), i("maxGun", 90, 1, 3650)
        if hi < lo:
            raise CommerceError("En çok gün en az günden küçük olamaz.")
        return {"minGun": lo, "maxGun": hi}
    if kind == "yeni-kitap":
        bc = src.ean_key(p.get("barkod"))
        if not bc:
            raise CommerceError("Yeni kitabın barkodu (EAN-13) seçilmeli.")
        level = p.get("duzey") or "alt"
        if level not in ("yaprak", "altalt", "alt", "ana"):
            raise CommerceError("Eşleşme düzeyi yaprak, altalt, alt ya da ana olmalı.")
        return {"barkod": bc, "duzey": level, "minAdet": i("minAdet", 1, 1, 1000)}
    if kind == "terk-sepeti":
        raise CommerceError("Terk sepeti tetiği kurulamaz: sepet verisi T-soft'tan okunmuyor (yöntem ölçülecek).", 409)
    raise CommerceError("Tetik türü yeni-kitap, geri-kazanim ya da ikinci-siparis olmalı.")


def _trigger_view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "kind": r.kind, "kindLabel": KINDS.get(r.kind, r.kind),
            "params": _load(r.params_json, {}), "channel": r.channel,
            "channelLabel": R.CHANNEL_LABELS.get(r.channel, r.channel), "controlShare": r.control_share,
            "status": r.status, "owner": r.owner, "createdAt": _iso(r.created_at), "updatedBy": r.updated_by,
            "updatedAt": _iso(r.updated_at)}


def list_triggers(engine: sa.engine.Engine, tenant: str, include_archived: bool = False) -> list[dict[str, Any]]:
    q = sa.select(TRIGGERS).where(TRIGGERS.c.tenant_id == tenant)
    if not include_archived:
        q = q.where(TRIGGERS.c.status != "arsiv")
    with engine.connect() as c:
        rows = list(c.execute(q.order_by(TRIGGERS.c.updated_at.desc())))
        last = {}
        for r in c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant).order_by(RUNS.c.at)):
            last[r.trigger_id] = r
    out = []
    for r in rows:
        v = _trigger_view(r)
        lr = last.get(r.id)
        v["lastRun"] = _run_view(lr) if lr else None
        out.append(v)
    return out


def trigger_row(engine: sa.engine.Engine, tenant: str, tid: str) -> Any:
    with engine.connect() as c:
        r = c.execute(sa.select(TRIGGERS).where(TRIGGERS.c.tenant_id == tenant, TRIGGERS.c.id == tid)).first()
    if not r:
        raise CommerceError("Tetik bulunamadı.", 404)
    return r


def create_trigger(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    name = (body.get("name") or "").strip()
    if len(name) < 3:
        raise CommerceError("Tetik adı en az 3 harf olmalı.")
    kind = body.get("kind") or ""
    params = _clean_params(kind, body.get("params") or {})
    channel = body.get("channel") or "email"
    if channel not in R.CHANNELS:
        raise CommerceError("Kanal e-posta, SMS ya da arama olmalı.")
    share = _num(body.get("controlShare", st["controlShare"]), st["controlShare"])
    if not 0 <= share <= 0.5:
        raise CommerceError("Kontrol grubu payı 0 ile 0,5 arasında olmalı.")
    tid, now = uuid.uuid4().hex, _now()
    with engine.begin() as c:
        c.execute(TRIGGERS.insert().values(id=tid, tenant_id=tenant, name=name[:200], kind=kind, params_json=_dump(params),
                                           channel=channel, control_share=share, status="etkin", owner=user,
                                           created_at=now, updated_by=user, updated_at=now))
    return _trigger_view(trigger_row(engine, tenant, tid))


def update_trigger(engine: sa.engine.Engine, tenant: str, tid: str, user: str, body: dict[str, Any]
                   ) -> tuple[dict[str, Any], dict[str, Any]]:
    r = trigger_row(engine, tenant, tid)
    if r.status == "arsiv":
        raise CommerceError("Arşivdeki tetik değiştirilemez.", 409)
    vals: dict[str, Any] = {}
    diff: dict[str, Any] = {}
    if "name" in body:
        name = (body.get("name") or "").strip()
        if len(name) < 3:
            raise CommerceError("Tetik adı en az 3 harf olmalı.")
        vals["name"], diff["name"] = name[:200], [r.name, name]
    if "params" in body:
        p = _clean_params(r.kind, body["params"])
        vals["params_json"], diff["params"] = _dump(p), [_load(r.params_json, {}), p]
    if "channel" in body:
        if body["channel"] not in R.CHANNELS:
            raise CommerceError("Kanal e-posta, SMS ya da arama olmalı.")
        vals["channel"], diff["channel"] = body["channel"], [r.channel, body["channel"]]
    if "controlShare" in body:
        share = _num(body["controlShare"], -1)
        if not 0 <= share <= 0.5:
            raise CommerceError("Kontrol grubu payı 0 ile 0,5 arasında olmalı.")
        vals["control_share"], diff["controlShare"] = share, [r.control_share, share]
    if body.get("archive"):
        vals["status"], diff["status"] = "arsiv", [r.status, "arsiv"]
    if vals:
        with engine.begin() as c:
            c.execute(TRIGGERS.update().where(TRIGGERS.c.id == tid).values(**vals, updated_by=user, updated_at=_now()))
    return _trigger_view(trigger_row(engine, tenant, tid)), diff


def new_books(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], today: Optional[date] = None) -> dict[str, Any]:
    """Tetik için yeni kitaplar: H1 kitap profilinde CRM'de son `newBookDays` günde açılan, barkodlu ve etkin kart."""
    today = today or date.today()
    idx = src.book_index(engine, tenant)
    cut = (today - timedelta(days=st["newBookDays"])).isoformat()
    items = [{"barkod": bc, "ad": b["name"], "kitap": b["bookId"], "acilis": b["created"],
              "dugum": b.get("node"), "dugumAdi": (idx["nodes"].get(b.get("node") or "") or {}).get("name")}
             for bc, b in idx["books"].items() if b.get("created") and b["created"] >= cut and b.get("active", True)]
    items.sort(key=lambda x: (x["acilis"] or "", x["ad"] or ""), reverse=True)
    note = None
    if idx["source"] != "h1":
        note = "Kategori ağacı kitap profili bu kurulumda yok; yeni kitap tetiği ilgi alanını bulamaz."
    elif not idx["nodes"]:
        note = "Yürürlükte kategori ağacı yok; kitapların ilgi alanı düğümü bilinmiyor."
    return {"items": items, "kaynak": idx["source"], "not": note, "gun": st["newBookDays"]}


def candidates(engine: sa.engine.Engine, tenant: str, kind: str, params: dict[str, Any], st: dict[str, Any],
               today: Optional[date] = None) -> tuple[list[str], dict[str, Any]]:
    """Kural → aday müşteri anahtarları (yalnız geçerli sipariş). İkinci değer açıklama/ek bilgi."""
    today = today or date.today()
    info: dict[str, Any] = {}
    with engine.connect() as c:
        base = sa.select(CUSTOMERS.c.customer_key, CUSTOMERS.c.orders, CUSTOMERS.c.last_order, CUSTOMERS.c.first_order,
                         CUSTOMERS.c.nodes_json).where(CUSTOMERS.c.tenant_id == tenant, CUSTOMERS.c.orders > 0)
        rows = list(c.execute(base))
    out: list[str] = []
    if kind == "geri-kazanim":
        for r in rows:
            d = (today - r.last_order.date()).days if r.last_order else None
            if d is not None and params["minGun"] <= d <= params["maxGun"] and r.orders >= params["minSiparis"]:
                out.append(r.customer_key)
        info["aciklama"] = (f"Son geçerli siparişi {params['minGun']}–{params['maxGun']} gün önce olan, en az "
                            f"{params['minSiparis']} siparişli müşteriler.")
    elif kind == "ikinci-siparis":
        for r in rows:
            d = (today - r.first_order.date()).days if r.first_order else None
            if r.orders == 1 and d is not None and params["minGun"] <= d <= params["maxGun"]:
                out.append(r.customer_key)
        info["aciklama"] = (f"Tek geçerli siparişi olan ve bu sipariş {params['minGun']}–{params['maxGun']} gün önce "
                            "verilmiş müşteriler (ikinci sipariş teşviki).")
    elif kind == "yeni-kitap":
        idx = src.book_index(engine, tenant)
        b = idx["books"].get(params["barkod"])
        if not b:
            raise CommerceError("Barkod kitap profilinde bulunamadı.", 404)
        if not b.get("node"):
            raise CommerceError("Kitabın kategori düğümü yok (Kategori ağacı › kitap profili); ilgi alanı eşleşmesi "
                                "yapılamaz.", 409)
        target = src.node_at_level(idx["nodes"], b["node"], params["duzey"])
        bought = set()
        with engine.connect() as c:
            for r in c.execute(sa.select(ORDERS.c.customer_key).select_from(LINES.join(ORDERS, sa.and_(
                    ORDERS.c.tenant_id == LINES.c.tenant_id, ORDERS.c.order_no == LINES.c.order_no)))
                    .where(LINES.c.tenant_id == tenant, LINES.c.barcode == params["barkod"], ORDERS.c.valid.is_(True))):
                bought.add(r.customer_key)
        for r in rows:
            nodes = _load(r.nodes_json, {})
            q = sum(v for n, v in nodes.items() if src.node_at_level(idx["nodes"], n, params["duzey"]) == target)
            if q >= params["minAdet"] and r.customer_key not in bought:
                out.append(r.customer_key)
        nm = (idx["nodes"].get(target or "") or {}).get("name") or target
        info.update(kitap=b["name"], dugum=target, dugumAdi=nm,
                    aciklama=(f"Son {st['lookbackDays']} günde «{nm}» kategorisinden en az {params['minAdet']} kitap alan, "
                              f"«{b['name']}» kitabını henüz almamış müşteriler."))
    else:
        raise CommerceError("Bu tetik türü hesaplanamaz.", 409)
    return sorted(out), info


def reachability(engine: sa.engine.Engine, tenant: str, keys: list[str], channel: str,
                 cfg: Optional[dict[str, Any]] = None) -> tuple[dict[str, str], dict[str, int], int]:
    """Anahtar → okur (yalnız ulaşılabilir olanlar), dışarıda kalma nedenleri, okura bağlı sayısı. Karar H2'nindir."""
    cfg = cfg or R.settings()
    rmap = reader_of(engine, tenant, keys)
    alive: dict[str, Optional[str]] = {}
    profs = {p["id"]: p for p in R.profiles(engine, tenant, cfg)}
    why: Counter = Counter()
    ok: dict[str, str] = {}
    linked = 0
    for k in keys:
        rid = rmap.get(k)
        if rid and rid not in profs:
            if rid not in alive:
                try:
                    alive[rid] = R._alive_id(engine, tenant, rid)
                except R.ReadersError:
                    alive[rid] = None
            rid = alive[rid]
        if not rid or rid not in profs:
            why["okur_yok"] += 1
            continue
        linked += 1
        e, reason = R.exportable(profs[rid], channel, cfg)
        if e:
            ok[k] = rid
        else:
            why[reason or "izin_yok"] += 1
    return ok, dict(why), linked


def preview(engine: sa.engine.Engine, tenant: str, tid: str, st: dict[str, Any], today: Optional[date] = None) -> dict[str, Any]:
    t = trigger_row(engine, tenant, tid)
    keys, info = candidates(engine, tenant, t.kind, _load(t.params_json, {}), st, today)
    ok, why, linked = reachability(engine, tenant, keys, t.channel)
    control = int(round(len(ok) * t.control_share))
    return {"candidates": len(keys), "linked": linked, "reachable": len(ok), "target": len(ok) - control,
            "control": control, "excluded": why, "info": info, "channel": t.channel}


def _order_key(run_id: str, key: str) -> str:
    return hashlib.sha256(f"{run_id}:{key}".encode()).hexdigest()


def split(run_id: str, keys: list[str], share: float) -> tuple[list[str], list[str]]:
    """Deterministik ayrım: (koşu, anahtar) özet sırasındaki ilk round(n × pay) anahtar kontrol grubudur."""
    order = sorted(keys, key=lambda k: _order_key(run_id, k))
    n = int(round(len(order) * share))
    return order[n:], order[:n]


def _run_view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "triggerId": r.trigger_id, "triggerName": r.trigger_name, "kind": r.kind,
            "kindLabel": KINDS.get(r.kind, r.kind), "params": _load(r.params_json, {}), "channel": r.channel,
            "channelLabel": R.CHANNEL_LABELS.get(r.channel, r.channel), "at": _iso(r.at), "createdBy": r.created_by,
            "candidates": r.candidates, "linked": r.linked, "reachable": r.consented, "target": r.target,
            "control": r.control, "controlShare": r.control_share, "excluded": _load(r.excluded_json, {}),
            "status": r.status, "statusLabel": RUN_STATUS.get(r.status, r.status), "approvedBy": r.approved_by,
            "approvedAt": _iso(r.approved_at), "decisionNote": r.decision_note, "exportId": r.export_id,
            "exportedBy": r.exported_by, "exportedAt": _iso(r.exported_at), "exportedCount": r.exported_count}


def run_row(engine: sa.engine.Engine, tenant: str, rid: str) -> Any:
    with engine.connect() as c:
        r = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.id == rid)).first()
    if not r:
        raise CommerceError("Liste bulunamadı.", 404)
    return r


def run_trigger(engine: sa.engine.Engine, tenant: str, tid: str, user: str, st: dict[str, Any],
                today: Optional[date] = None) -> dict[str, Any]:
    t = trigger_row(engine, tenant, tid)
    if t.status != "etkin":
        raise CommerceError("Arşivdeki tetik çalıştırılamaz.", 409)
    if not has_data(engine, tenant):
        raise CommerceError("Site siparişleri henüz okunmadı.", 409)
    keys, info = candidates(engine, tenant, t.kind, _load(t.params_json, {}), st, today)
    ok, why, linked = reachability(engine, tenant, keys, t.channel)
    rid = uuid.uuid4().hex
    target, control = split(rid, sorted(ok), t.control_share)
    now = _now()
    with engine.begin() as c:
        c.execute(RUNS.insert().values(
            id=rid, tenant_id=tenant, trigger_id=t.id, trigger_name=t.name, kind=t.kind,
            params_json=_dump({**_load(t.params_json, {}), "_bilgi": info}), channel=t.channel, at=now, created_by=user,
            candidates=len(keys), linked=linked, consented=len(ok), target=len(target), control=len(control),
            control_share=t.control_share, excluded_json=_dump(why), status="onay-bekliyor"))
        rows = [{"run_id": rid, "customer_key": k, "grp": "hedef", "reader_id": ok[k]} for k in target]
        rows += [{"run_id": rid, "customer_key": k, "grp": "kontrol", "reader_id": ok[k]} for k in control]
        _bulk(c, RUN_MEMBERS, rows)
    return _run_view(run_row(engine, tenant, rid))


def list_runs(engine: sa.engine.Engine, tenant: str, status: str = "", page: int = 0, size: int = 50) -> dict[str, Any]:
    q = sa.select(RUNS).where(RUNS.c.tenant_id == tenant)
    cq = sa.select(sa.func.count()).select_from(RUNS).where(RUNS.c.tenant_id == tenant)
    if status:
        q, cq = q.where(RUNS.c.status == status), cq.where(RUNS.c.status == status)
    with engine.connect() as c:
        total = c.execute(cq).scalar() or 0
        rows = list(c.execute(q.order_by(RUNS.c.at.desc()).offset(max(0, page) * size).limit(size)))
    return {"items": [_run_view(r) for r in rows], "total": total, "page": page, "pageSize": size}


def decide_run(engine: sa.engine.Engine, tenant: str, rid: str, user: str, approve: bool, note: Optional[str] = None
               ) -> dict[str, Any]:
    """İki göz: tetiği yazan ve listeyi çalıştıran onaylayamaz. Geri göndermede not zorunlu."""
    r = run_row(engine, tenant, rid)
    if r.status != "onay-bekliyor":
        raise CommerceError("Liste onay beklemiyor.", 409)
    t = trigger_row(engine, tenant, r.trigger_id)
    if user.lower() in {(r.created_by or "").lower(), (t.owner or "").lower()}:
        raise CommerceError("Tetiği yazan ya da listeyi çalıştıran kişi onaylayamaz.", 403)
    if not approve and not (note or "").strip():
        raise CommerceError("Geri gönderme nedeni yazılmalı.")
    vals = {"status": "onayli" if approve else "geri-gonderildi", "approved_by": user, "approved_at": _now(),
            "decision_note": (note or None) and note.strip()[:1000]}
    with engine.begin() as c:
        c.execute(RUNS.update().where(RUNS.c.id == rid).values(**vals))
    return _run_view(run_row(engine, tenant, rid))


def run_members(engine: sa.engine.Engine, tenant: str, rid: str) -> list[Any]:
    run_row(engine, tenant, rid)
    with engine.connect() as c:
        return list(c.execute(sa.select(RUN_MEMBERS).where(RUN_MEMBERS.c.run_id == rid)))


def export_run(engine: sa.engine.Engine, tenant: str, rid: str, user: str, purpose: str,
               read_crm: Callable[[list[tuple[str, str]]], dict[tuple[str, str], dict[str, Any]]],
               read_site: Callable[[list[Any]], dict[str, Optional[dict[str, Any]]]],
               cfg: Optional[dict[str, Any]] = None, false_is_ret: bool = True) -> tuple[str, bytes, dict[str, Any]]:
    """Onaylı listenin **hedef grubu** CSV olarak (kontrol grubu hiç çıkmaz). Kişi o an yeniden denetlenir; adres CRM'den,
    yoksa T-soft'tan anlık okunur. Kayıt H2'nin dışa aktarım defterine yazılır."""
    from semantic_bridge import readers_segments as seg

    cfg = cfg or R.settings()
    if not cfg["exportEnabled"]:
        raise CommerceError("Liste dışa aktarımı bu ortamda kapalı (rıza metni ve çocuk kayıtları için hukuk teyidi "
                            "bekleniyor; yönetici Yönetim → Okur veri tabanı ayarından açar).", 409)
    purpose = (purpose or "").strip()
    if len(purpose) < 5:
        raise CommerceError("Dışa aktarımın amacı yazılmalı (en az 5 harf).")
    r = run_row(engine, tenant, rid)
    if r.status not in ("onayli", "aktarildi"):
        raise CommerceError("Yalnız onaylı liste dışa aktarılır.", 409)
    channel = r.channel
    mem = [m for m in run_members(engine, tenant, rid) if m.grp == "hedef"]
    profs = {p["id"]: p for p in R.profiles(engine, tenant, cfg)}
    why: Counter = Counter()
    ok_ids: list[tuple[str, str]] = []
    for m in mem:
        rid_ = m.reader_id
        p = profs.get(rid_ or "")
        if p is None and rid_:
            try:
                rid_ = R._alive_id(engine, tenant, rid_)
            except R.ReadersError:
                rid_ = None
            p = profs.get(rid_ or "")
        if p is None:
            why["okur_yok"] += 1
            continue
        e, reason = R.exportable(p, channel, cfg)
        if not e:
            why[reason or "izin_yok"] += 1
            continue
        ok_ids.append((m.customer_key, rid_))
    links = R.links_of(engine, tenant, [x[1] for x in ok_ids])
    by_reader: dict[str, list[Any]] = defaultdict(list)
    for ln in links:
        by_reader[ln.reader_id].append(ln)
    crm_keys = [(ln.source, ln.source_id) for ln in links if ln.source in seg._PREF]
    live = read_crm(crm_keys) if crm_keys else {}
    site_keys = sorted({ln.source_id for ln in links if ln.source == SOURCE})
    site_rows = []
    with engine.connect() as c:
        for part in src.chunks(site_keys):
            site_rows += list(c.execute(sa.select(CUSTOMERS).where(CUSTOMERS.c.tenant_id == tenant,
                                                                   CUSTOMERS.c.customer_key.in_(part))))
    site_live = read_site(site_rows) if site_rows else {}
    out_rows: list[list[str]] = []
    exported: list[str] = []
    for ck, reader in ok_ids:
        recs = sorted(by_reader.get(reader, []), key=lambda ln: (seg._PREF.get(ln.source, 9), ln.source_id))
        crm_live = [(ln.source, live.get((ln.source, ln.source_id))) for ln in recs if ln.source in seg._PREF]
        crm_live = [(s, x) for s, x in crm_live if x and int(x.get("durum") or 0) == 0]
        sites = [site_live.get(ln.source_id) for ln in recs if ln.source == SOURCE]
        sites = [x for x in sites if x]
        if any(seg._blocked_live(s, x, channel, cfg) for s, x in crm_live) or \
                (false_is_ret and any((x.get("izin") or {}).get(channel) is False for x in sites)):
            why["canli_ret"] += 1
            continue
        addr = name = None
        for _s, x in crm_live:
            addr = (R.norm_email(x.get("eposta")) or R.norm_email(x.get("eposta2"))) if channel == "email" else R.norm_phone(x.get("cep"))
            if addr:
                name = x.get("ad")
                break
        if not addr:
            for x in sites:
                addr = x.get("eposta") if channel == "email" else x.get("cep")
                if addr:
                    name = x.get("ad")
                    break
        if not addr:
            why["adres_yok"] += 1
            continue
        out_rows.append([reader, (name or "").strip(), addr, (profs.get(reader) or {}).get("city") or ""])
        exported.append(reader)
    head = ["okur_no", "ad_soyad", {"email": "eposta", "sms": "cep_telefonu", "call": "telefon"}[channel], "il"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(head)
    w.writerows(out_rows)
    data = ("﻿" + buf.getvalue()).encode("utf-8")
    eid = seg.record_export(engine, tenant, list_id=f"et-{rid}"[:32], list_name=f"E-ticaret: {r.trigger_name}",
                            version=None, user=user, channel=channel, purpose=purpose, reader_ids=exported,
                            excluded=dict(why))
    now = _now()
    with engine.begin() as c:
        c.execute(RUNS.update().where(RUNS.c.id == rid).values(status="aktarildi", export_id=eid, exported_by=user,
                                                               exported_at=now, exported_count=len(exported)))
    slug = re.sub(r"[^a-z0-9]+", "-", (r.trigger_name or "liste").replace("İ", "i").lower().translate(R._TR)).strip("-")[:40]
    fname = f"eticaret-listesi-{slug or 'liste'}-{channel}-{now.strftime('%Y%m%d-%H%M')}.csv"
    return fname, data, {"id": eid, "count": len(exported), "excluded": dict(why), "excludedTotal": sum(why.values()),
                         "target": len(mem), "fileName": fname}


# ------------------------------------------------------------------ kampanya sonucu


def _campaign_view(r: Any) -> dict[str, Any]:
    return {"id": r.id, "name": r.name, "runId": r.trigger_run_id, "start": _iso(r.start_day), "end": _iso(r.end_day),
            "createdBy": r.created_by, "createdAt": _iso(r.created_at), "result": _load(r.result_json, None),
            "resultAt": _iso(r.result_at), "final": bool(r.final), "comment": r.comment, "commentAt": _iso(r.comment_at)}


def create_campaign(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    run = run_row(engine, tenant, body.get("runId") or "")
    if run.status not in ("onayli", "aktarildi"):
        raise CommerceError("Kampanya yalnız onaylı listeden açılır.", 409)
    if run.control == 0:
        raise CommerceError("Bu listede kontrol grubu yok; kontrol grubu olmadan kampanya sonucu ölçülmez.", 409)
    name = (body.get("name") or run.trigger_name or "").strip()
    if len(name) < 3:
        raise CommerceError("Kampanya adı en az 3 harf olmalı.")
    try:
        start = date.fromisoformat(str(body.get("start") or (run.exported_at or run.at).date().isoformat())[:10])
        end = (date.fromisoformat(str(body["end"])[:10]) if body.get("end")
               else start + timedelta(days=st["resultWindowDays"] - 1))
    except ValueError:
        raise CommerceError("Tarih YYYY-AA-GG olmalı.") from None
    if end < start:
        raise CommerceError("Bitiş başlangıçtan önce olamaz.")
    cid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(CAMPAIGNS.insert().values(id=cid, tenant_id=tenant, name=name[:200], trigger_run_id=run.id, start_day=start,
                                            end_day=end, created_by=user, created_at=_now(), final=False))
    return campaign(engine, tenant, cid, st)


def campaign_row(engine: sa.engine.Engine, tenant: str, cid: str) -> Any:
    with engine.connect() as c:
        r = c.execute(sa.select(CAMPAIGNS).where(CAMPAIGNS.c.tenant_id == tenant, CAMPAIGNS.c.id == cid)).first()
    if not r:
        raise CommerceError("Kampanya bulunamadı.", 404)
    return r


def list_campaigns(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = list(c.execute(sa.select(CAMPAIGNS).where(CAMPAIGNS.c.tenant_id == tenant).order_by(CAMPAIGNS.c.start_day.desc())))
    return [_campaign_view(r) for r in rows]


def lift(nt: int, bt: int, nc: int, bc: int) -> dict[str, Any]:
    """Dönüşüm farkı ve %95 güven aralığı (iki oranın farkı, normal yaklaşım)."""
    pt = bt / nt if nt else None
    pc = bc / nc if nc else None
    if pt is None or pc is None:
        return {"hedefOran": pt, "kontrolOran": pc, "fark": None, "alt": None, "ust": None, "anlamli": False,
                "goreli": None}
    diff = pt - pc
    se = math.sqrt(pt * (1 - pt) / nt + pc * (1 - pc) / nc)
    lo, hi = diff - 1.96 * se, diff + 1.96 * se
    return {"hedefOran": round(pt, 6), "kontrolOran": round(pc, 6), "fark": round(diff, 6), "alt": round(lo, 6),
            "ust": round(hi, 6), "anlamli": bool(se > 0 and (lo > 0 or hi < 0)),
            "goreli": round(diff / pc, 4) if pc else None}


def compute_result(engine: sa.engine.Engine, tenant: str, cid: str, st: dict[str, Any], today: Optional[date] = None
                   ) -> dict[str, Any]:
    today = today or date.today()
    cp = campaign_row(engine, tenant, cid)
    mem = run_members(engine, tenant, cp.trigger_run_id)
    groups = {"hedef": [m.customer_key for m in mem if m.grp == "hedef"], "kontrol": [m.customer_key for m in mem if m.grp == "kontrol"]}
    lo = datetime.combine(cp.start_day, datetime.min.time())
    hi = datetime.combine(cp.end_day + timedelta(days=1), datetime.min.time())
    res: dict[str, Any] = {}
    for g, keys in groups.items():
        buyers: set[str] = set()
        orders = 0
        rev = 0.0
        with engine.connect() as c:
            for part in src.chunks(sorted(keys)):
                for r in c.execute(sa.select(ORDERS.c.customer_key, ORDERS.c.total).where(
                        ORDERS.c.tenant_id == tenant, ORDERS.c.valid.is_(True), ORDERS.c.customer_key.in_(part),
                        ORDERS.c.ordered_at >= lo, ORDERS.c.ordered_at < hi)):
                    buyers.add(r.customer_key)
                    orders += 1
                    rev += float(r.total or 0)
        n = len(keys)
        res[g] = {"kisi": n, "alan": len(buyers), "siparis": orders, "ciro": round(rev, 2),
                  "kisiBasinaCiro": round(rev / n, 4) if n else None}
    t, k = res["hedef"], res["kontrol"]
    lf = lift(t["kisi"], t["alan"], k["kisi"], k["alan"])
    extra_buyers = round(lf["fark"] * t["kisi"], 2) if lf["fark"] is not None else None
    extra_rev = (round((t["kisiBasinaCiro"] - k["kisiBasinaCiro"]) * t["kisi"], 2)
                 if t["kisiBasinaCiro"] is not None and k["kisiBasinaCiro"] is not None else None)
    final = today > cp.end_day + timedelta(days=st["resultLagDays"])
    warn = []
    if k["kisi"] < 30:
        warn.append("Kontrol grubu 30 kişiden küçük; sonuç güvenilir değil.")
    if not final:
        warn.append(f"Sonuç kesin değil: pencere {cp.end_day.isoformat()} tarihinde biter, {st['resultLagDays']} gün sonra "
                    "kesinleşir (geç iptal/iade).")
    run = run_row(engine, tenant, cp.trigger_run_id)
    if run.exported_count is not None and run.exported_count < run.target:
        warn.append("Hedef grubun bir kısmı dışa aktarımda yeniden denetimde düştü; sonuç bütün hedef grup üzerinden "
                    "(niyet edilen) hesaplanır.")
    out = {"hedef": t, "kontrol": k, "lift": lf, "ekAlan": extra_buyers, "ekCiro": extra_rev, "kesin": final,
           "uyarilar": warn, "pencere": {"from": cp.start_day.isoformat(), "to": cp.end_day.isoformat()},
           "aktarilan": run.exported_count}
    with engine.begin() as c:
        c.execute(CAMPAIGNS.update().where(CAMPAIGNS.c.id == cid).values(result_json=_dump(out), result_at=_now(), final=final))
    return out


def campaign(engine: sa.engine.Engine, tenant: str, cid: str, st: dict[str, Any], refresh: bool = True) -> dict[str, Any]:
    cp = campaign_row(engine, tenant, cid)
    if refresh and not cp.final:
        compute_result(engine, tenant, cid, st)
        cp = campaign_row(engine, tenant, cid)
    v = _campaign_view(cp)
    v["run"] = _run_view(run_row(engine, tenant, cp.trigger_run_id))
    return v


COMMENT_PROMPT = (
    "Bir yayınevinin sitesinde bir müşteri listesine kampanya iletisi gönderildi; listenin bir kısmı kontrol grubu olarak "
    "ayrıldı. Aşağıdaki olgulara göre ekibe iki cümlelik yorum yaz. Rakam, yüzde, tutar yazma; olgularda olmayan bir şeyi "
    "iddia etme; kesin değilse bunu söyle.\n\nOlgular:\n{facts}"
)


def assert_no_personal(text: str) -> None:
    if "@" in text or re.search(r"(?:\+?90|0)?5\d{9}", re.sub(r"\D", "", text)):
        raise CommerceError("İstemde kişisel veri olabilir; model çağrılmadı.", 500)


def comment_campaign(engine: sa.engine.Engine, tenant: str, cid: str, llm: Any, st: dict[str, Any]) -> dict[str, Any]:
    if llm is None:
        raise CommerceError("Zeki AI bu kurulumda tanımlı değil.", 409)
    res = compute_result(engine, tenant, cid, st)
    lf = res["lift"]
    facts = [f"Tetik türü: {KINDS.get(run_row(engine, tenant, campaign_row(engine, tenant, cid).trigger_run_id).kind, '')}",
             "Hedef grubun alışveriş oranı kontrol grubundan " +
             ("yüksek" if (lf["fark"] or 0) > 0 else "düşük" if (lf["fark"] or 0) < 0 else "farksız"),
             "Fark istatistiksel olarak " + ("anlamlı" if lf["anlamli"] else "anlamlı değil"),
             "Sonuç " + ("kesin" if res["kesin"] else "henüz kesin değil")]
    if res["kontrol"]["kisi"] < 30:
        facts.append("Kontrol grubu küçük")
    prompt = COMMENT_PROMPT.format(facts="\n".join(f"- {x}" for x in facts))
    assert_no_personal(prompt)
    text = (llm.chat([{"role": "user", "content": prompt}], max_tokens=220, temperature=0.2) or "").strip()
    text = re.sub(r"[^\n]*\d[^\n]*\n?", "", text).strip()[:1200] or None
    with engine.begin() as c:
        c.execute(CAMPAIGNS.update().where(CAMPAIGNS.c.id == cid).values(comment=text, comment_at=_now()))
    return campaign(engine, tenant, cid, st, refresh=False)


# ------------------------------------------------------------------ sözleşme uçları (M35, M42, M18)


def segments_summary(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Yalnız sayılar: segment büyüklüğü, ciro, tekrar oranı, veri tazeliği. Kişi yok."""
    segs = segment_counts(engine, tenant)
    buyers = sum(s["musteri"] for s in segs if s["segment"] != "siparissiz")
    repeat = sum(s["musteri"] for s in segs if s["segment"] in ("aktif", "sadik"))
    with engine.connect() as c:
        rep_all = c.execute(sa.select(sa.func.count()).select_from(CUSTOMERS).where(
            CUSTOMERS.c.tenant_id == tenant, CUSTOMERS.c.orders > 1)).scalar() or 0
    info = meta_get(engine, tenant, "sync", {}) or {}
    return {"bagli": bool(info.get("okAt")), "okunma": info.get("okAt"), "segmentler": segs, "alici": buyers,
            "tekrarAlan": int(rep_all), "tekrarOrani": round(rep_all / buyers, 4) if buyers else None,
            "aktifTekrar": repeat}


def d2c_site(engine: sa.engine.Engine, tenant: str, start: str, end: str) -> dict[str, Any]:
    """M42 D2C bağlantısı: dönem içindeki geçerli site siparişlerinin özeti (iptal/iade dışarıda)."""
    ensure(engine)
    if not has_data(engine, tenant):
        return {"bagli": False, "neden": "Site siparişleri (e-ticaret müşteri modülü) henüz T-soft'tan okunmadı."}
    lo = datetime.fromisoformat(start[:10])
    y, m = int(end[:4]), int(end[5:7])
    hi = (datetime(y, m, 1) + timedelta(days=32)).replace(day=1)       # «AAAA-AA-31» → ayın sonu dahil
    monthly: dict[int, dict[str, float]] = defaultdict(lambda: {"siparis": 0, "ciro": 0.0})
    per: Counter = Counter()
    n, rev = 0, 0.0
    with engine.connect() as c:
        for r in c.execute(sa.select(ORDERS.c.ordered_at, ORDERS.c.total, ORDERS.c.customer_key).where(
                ORDERS.c.tenant_id == tenant, ORDERS.c.valid.is_(True), ORDERS.c.ordered_at >= lo, ORDERS.c.ordered_at < hi)):
            monthly[r.ordered_at.month]["siparis"] += 1
            monthly[r.ordered_at.month]["ciro"] += float(r.total or 0)
            n += 1
            rev += float(r.total or 0)
            if r.customer_key:
                per[r.customer_key] += 1
    cust = len(per)
    rep = sum(1 for v in per.values() if v > 1)
    ratio = lambda a, b: (a / b) if b else None  # noqa: E731
    return {"bagli": True, "siparis": n, "ciro": round(rev, 2), "musteri": cust, "tekrarOrani": ratio(rep, cust),
            "musteriBasinaCiro": ratio(rev, cust), "sepetOrtalamasi": ratio(rev, n),
            "aylik": [{"ay": mm, "siparis": int(v["siparis"]), "ciro": round(v["ciro"], 2)} for mm, v in sorted(monthly.items())],
            "not": "Site siparişi tutarı sitenin kendi kaydıdır (kargo ve kupon dahil olabilir; iptal/iade edilen sipariş "
                   "düşülmüştür); Logo net cirosuyla aynı şey değildir."}


# ------------------------------------------------------------------ H2 bağlantısı: kaynak ve segment alanları

SOURCE = "tsoft_member"


def h2_records(engine: sa.engine.Engine, tenant: str) -> list[R.SourceRecord]:
    """H2 okuma turunda çağrılır: e-posta ya da telefon özeti olan her site müşterisi/üyesi bir kaynak kaydıdır
    (kimlik `customer_key`). İzin kanıtı T-soft üye kaydından («Site»)."""
    ensure(engine)
    out = []
    with engine.connect() as c:
        for r in c.execute(sa.select(CUSTOMERS).where(CUSTOMERS.c.tenant_id == tenant)):
            if not (r.email_hash or r.phone_hash):
                continue
            ev = [R.Evidence(e.get("channel"), e.get("status"), "tsoft", _utc(e.get("at")), e.get("detail"))
                  for e in _load(r.consent_json, []) if e.get("channel") and e.get("status") in ("izinli", "ret")]
            attrs = {"site_musterisi": ["Siparişli" if r.orders else "Üye (siparişsiz)"],
                     "eticaret_segment": [SEGMENT_LABELS.get(r.segment, r.segment)]}
            out.append(R.SourceRecord(
                source=SOURCE, source_id=r.customer_key, email_hashes={r.email_hash} if r.email_hash else set(),
                phone_hashes={r.phone_hash} if r.phone_hash else set(), name_hash=r.name_hash, city=r.city,
                created=_utc(r.member_since or r.first_order), attrs=attrs, evidences=ev,
                last_touch=_utc(r.last_order)))
    return out


class _Facts:
    """Okur → site alışveriş özeti (H2 segment alanları için). Segment motoru yalnız profili verir; bu önbellek bağlanan
    çalışma zamanından (motor, kiracı) okunur, müşteri tablosu ya da okur tablosu değişince yenilenir."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.bound: Optional[tuple[Callable[[], Any], Callable[[], str]]] = None
        self.stamp: Any = None
        self.checked = 0.0
        self.by_reader: dict[str, dict[str, Any]] = {}

    def bind(self, engine_fn: Callable[[], Any], tenant_fn: Callable[[], str]) -> None:
        self.bound = (engine_fn, tenant_fn)
        self.by_reader = {}
        self.invalidate()

    def invalidate(self) -> None:
        with self.lock:
            self.checked = 0.0
            self.stamp = None

    def get(self, reader_id: str) -> dict[str, Any]:
        if self.bound is None:
            return {}
        now = time.monotonic()
        if now - self.checked > 60:
            try:
                self._reload()
            except Exception as e:  # noqa: BLE001 — segment alanı boş döner, H2 çalışmaya devam eder
                log.info("commerce: okur özeti yüklenemedi: %s", e)
            self.checked = now
        return self.by_reader.get(reader_id, {})

    def _reload(self) -> None:
        engine, tenant = self.bound[0](), self.bound[1]()
        ensure(engine)
        stamp = (meta_get(engine, tenant, "stamp"), R.stamp(engine, tenant))
        if stamp == self.stamp:
            return
        nodes = src.book_index(engine, tenant)["nodes"]
        cust = {}
        with engine.connect() as c:
            for r in c.execute(sa.select(CUSTOMERS.c.customer_key, CUSTOMERS.c.orders, CUSTOMERS.c.revenue,
                                         CUSTOMERS.c.first_order, CUSTOMERS.c.last_order, CUSTOMERS.c.segment,
                                         CUSTOMERS.c.nodes_json).where(CUSTOMERS.c.tenant_id == tenant)):
                cust[r.customer_key] = r
        rmap = reader_of(engine, tenant, list(cust))
        by: dict[str, dict[str, Any]] = {}
        for k, rid in rmap.items():
            r = cust[k]
            f = by.setdefault(rid, {"orders": 0, "revenue": 0.0, "first": None, "last": None, "segments": set(), "nodes": set()})
            f["orders"] += int(r.orders or 0)
            f["revenue"] += float(r.revenue or 0)
            for a, v, fn in (("first", r.first_order, min), ("last", r.last_order, max)):
                u = _utc(v)
                if u:
                    f[a] = u if f[a] is None else fn(f[a], u)
            f["segments"].add(SEGMENT_LABELS.get(r.segment, r.segment))
            for n in _load(r.nodes_json, {}):
                f["nodes"].add((nodes.get(n) or {}).get("name") or n)
        with self.lock:
            self.by_reader, self.stamp = by, stamp


FACTS = _Facts()


def _facts_invalidate() -> None:
    FACTS.invalidate()


def register_h2() -> None:
    """H2'ye kaynak ve segment alanlarını kaydeder (bir kez, köprü açılırken)."""
    from semantic_bridge import readers_segments as seg

    R.register_source(SOURCE, h2_records, address=True)
    g = FACTS.get
    seg.register_field("eticaret_segment", "E-ticaret segmenti", "set", lambda p: sorted(g(p["id"]).get("segments", ())),
                       lambda _p: [SEGMENT_LABELS[s] for s in SEGMENTS])
    seg.register_field("eticaret_siparis", "Site siparişi sayısı", "number", lambda p: g(p["id"]).get("orders"),
                       help="Geçerli (iptal/iade olmayan) site siparişi; site müşterisi olmayan okur için 0 sayılır.")
    seg.register_field("eticaret_ciro", "Site cirosu (₺)", "number",
                       lambda p: round(g(p["id"])["revenue"], 2) if g(p["id"]) else None)
    seg.register_field("eticaret_son_siparis", "Son site siparişi", "days", lambda p: g(p["id"]).get("last"))
    seg.register_field("eticaret_ilk_siparis", "İlk site siparişi", "days", lambda p: g(p["id"]).get("first"))
    seg.register_field("eticaret_kategori", "Sitede aldığı kategori", "set", lambda p: sorted(g(p["id"]).get("nodes", ())),
                       seg._opts(lambda p: sorted(g(p["id"]).get("nodes", ()))))


# ------------------------------------------------------------------ zamanlayıcı


def due(engine: sa.engine.Engine, tenant: str, now: Optional[datetime] = None) -> dict[str, bool]:
    now = now or datetime.now()
    info = meta_get(engine, tenant, "sync", {}) or {}
    ok = _utc(info.get("okAt"))
    last_full = _utc((meta_get(engine, tenant, "full", {}) or {}).get("at"))
    local_ok = ok.astimezone().replace(tzinfo=None) if ok else None
    sent = meta_get(engine, tenant, "summarySent", None)
    return {"sync": local_ok is None or local_ok.date() < now.date(),
            "full": now.weekday() == 6 and (last_full is None or (_now() - last_full).days >= 6),
            "summary": now.hour >= 7 and sent != now.date().isoformat()}


def summary_text(ov: dict[str, Any], pending: int, link: str) -> str:
    c, ch = ov["cur"], ov["change"]
    nf = lambda v: "—" if v is None else f"{v:,.0f}".replace(",", ".")  # noqa: E731
    pct = lambda v: "" if v is None else f" ({'+' if v >= 0 else ''}{v * 100:.1f}%)".replace(".", ",")  # noqa: E731
    lines = [f"Site siparişleri — {ov['period']['label']} ({ov['period']['from']})", "",
             f"Sipariş: {nf(c['siparis'])}{pct(ch['siparis'])}", f"Ciro (site): {nf(c['ciro'])} ₺{pct(ch['ciro'])}",
             f"Sepet ortalaması: {nf(c['sepet'])} ₺", f"Müşteri: {nf(c['musteri'])} (yeni {nf(c['yeni'])}, tekrar {nf(c['tekrar'])})"]
    d = ov["drop"]
    if d["uyari"]:
        lines += ["", f"Uyarı: dünkü sipariş ({nf(d['siparis'])}) önceki dört haftanın aynı gününün ortalamasının "
                      f"({nf(d['ortalama'])}) belirgin altında."]
    lg = ov.get("logo") or {}
    if lg.get("bagli"):
        lines += ["", f"Logo e-ticaret kanalı ({lg['ayAdi']} {lg['yil']}): {nf(lg['netCiro'])} ₺ net; site {nf(lg.get('siteCiro'))} ₺."]
    fr = ov["freshness"]
    if fr["stale"] or fr["error"]:
        lines += ["", "Veri tazeliği: " + (fr["error"] or "site siparişleri güncel değil.")]
    if pending:
        lines += ["", f"Onay bekleyen tetik listesi: {pending}"]
    lines += ["", f"Ayrıntı: {link}/eticaret-musteri" if link else ""]
    return "\n".join(x for x in lines if x is not None)


def pending_runs(engine: sa.engine.Engine, tenant: str, user: Optional[str] = None) -> int:
    with engine.connect() as c:
        rows = list(c.execute(sa.select(RUNS.c.created_by, RUNS.c.trigger_id).where(RUNS.c.tenant_id == tenant,
                                                                                    RUNS.c.status == "onay-bekliyor")))
        owners = {r.id: r.owner for r in c.execute(sa.select(TRIGGERS.c.id, TRIGGERS.c.owner).where(TRIGGERS.c.tenant_id == tenant))}
    if user is None:
        return len(rows)
    u = user.lower()
    return sum(1 for r in rows if u not in {(r.created_by or "").lower(), (owners.get(r.trigger_id) or "").lower()})


def refresh_results(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], today: Optional[date] = None) -> int:
    today = today or date.today()
    with engine.connect() as c:
        ids = [r.id for r in c.execute(sa.select(CAMPAIGNS.c.id).where(CAMPAIGNS.c.tenant_id == tenant,
                                                                       CAMPAIGNS.c.final.is_(False),
                                                                       CAMPAIGNS.c.start_day <= today))]
    for cid in ids:
        compute_result(engine, tenant, cid, st, today)
    return len(ids)
