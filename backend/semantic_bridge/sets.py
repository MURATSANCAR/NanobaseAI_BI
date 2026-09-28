"""M53 Hediye, set ve promosyon ürün yönetimi: set envanteri, fiyat–marj, set önerisi, «açılacak kart» listesi, kurumsal
hediye kataloğu/teklifi, promosyon ürünleri.

**Kaynaklar** (`sets_sources`): CRM (set kartları `new_Tip = 4`, «Set İşlemi» bileşenleri, kitap kartı, paketleme maliyeti,
özel günler, B2C siparişleri) ve Logo (malzeme kartı ve KDV oranı, faturalı satış, stok bakiyesi, `PRCLIST`, reçete). İkisi
de yalnız okunur. Gece işi (`run_due`) okumaları köprünün `semantic_mkt_*` tablolarına yazar; ekranlar bu tablolardan okur.

**Yazma yok:** CRM'e, Logo'ya ve T-soft'a hiçbir şey gitmez. Onaylanan set için «açılacak kart» listesi verilir; kartı TİMAŞ
kendi akışıyla açar, modül CRM'deki kartı okuyup kendi setine eşler (bileşenler birebir tutuyorsa kendiliğinden, yoksa elle
stok kodu girilir ve CRM'de doğrulanır). Kurumsal teklif belgesi indirilir, kuruma gönderimi satış yapar. Her yazma
`semantic_audit`'e düşer (`mkt_set`, `mkt_gift_offer`, `mkt_suggestion`).

**Çift sayım yok:** set satışı setin kendi stok koduyla, bileşenin tek satışı bileşen koduyla okunur; ikisi hiçbir toplamda
birleştirilmez (`sets_sources` başındaki gerekçe). Satış tablosunda her satırın türü (`set`, `bilesen`, `promosyon`) durur.

**Kurallar (model yok):**
- *Fiyat–marj:* set fiyatı KDV dahildir. KDV, set fiyatı bileşenlerin liste fiyatı payına göre dağıtılarak her kalemin Logo
  satış KDV oranıyla ayrıştırılır (liste fiyatı eksikse adet payıyla; ekranda yazılır). Marj = KDV hariç set geliri − Σ
  (bileşen birim maliyeti × adet) − ambalaj birim maliyeti. Bir bileşende maliyet yoksa marj hesaplanmaz: «N kitapta
  maliyet yok». Birim maliyet `sets_sources.unit_costs`'tan (M9 bağlanınca oradan; yoksa «maliyet bilinmiyor»).
- *Önerilen indirim:* CRM'deki mevcut setlerin (bütün bileşen fiyatları bilinen) set fiyatı ↔ liste toplamı indiriminin
  medyanı; `SETS_DISCOUNT_MIN_N` setten azsa öneri yok (liste toplamı önerilir, karar insanda).
- *Set önerisi:* (1) B2C siparişlerinde birlikte alınan çiftler (`SETS_BASKET_MIN_ORDERS` ve üstü siparişte, birliktelik
  oranı ≥ 1: iki çok satanın tesadüfen aynı sepette olması gerekçe sayılmaz), iki bileşenle de birlikte alınan kitaplarla
  `SETS_SUGGEST_MAX_SIZE`'a kadar genişletilir; (2) aynı yazar; (3) aynı dizi. Aday yalnız stoğu olan kitap kartıdır
  (`new_Tip = 1`), promosyon kodu değildir; bileşenleri mevcut bir setle aynı olan aday düşer. Sayı tavanı yok.
- *Kurumsal hediye seçenekleri:* stoğu kişi sayısına yeten set, tek kitap ve (en çok satanlardan açgözlü doldurulan) kitap
  paketi; kademe indirimi (`SETS_GIFT_TIERS` ya da teklifte elle) sonrası kişi başı fiyatı bütçeye sığanlar, bütçeye en
  yakın olan önce.

**ZEKİ AI (LLM kapısından, `llm_for("marketing")`):** öneriye ad ve kısa tanıtım (gece, rakamsız), önerinin en uygun özel
günü (kapalı küme `QueuedLlm.choose`, olasılık/marj eşiği ayarda), set tanıtım metni ve ambalaj brief'i, kurumsal teklif
mektubu (ekranda, rakamsız). Rakam modelden gelmez.

**M32 bağlantı noktası:** kurumsal teklif akışı M32'dedir. Burada set/hediye kataloğu ve fiyat–marj hesaplanır;
`handoff` M32 teklif satırı biçiminde kalemleri verir, teklif `m32_firsat_id` ile M32 fırsatına bağlanabilir.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import re
import statistics
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import sets_sources as src

log = logging.getLogger("semantic.sets")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

SETS = sa.Table(
    "semantic_mkt_sets", _md,
    sa.Column("id", sa.String(20), primary_key=True),                 # MS-<yıl>-<sıra>
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("ad", sa.String(300), nullable=False),
    sa.Column("tur", sa.String(20), nullable=False),                  # tematik|yazar|seri|sezon|kurumsal|toplama
    sa.Column("kaynak", sa.String(10), nullable=False),               # crm|oneri|elle
    sa.Column("crm_kitap_id", sa.String(40)),
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("durum", sa.String(20), nullable=False),
    sa.Column("sezon_id", sa.String(40)),
    sa.Column("sezon_adi", sa.String(200)),
    sa.Column("kanal_json", sa.Text),
    sa.Column("set_fiyati", sa.Float),                                # KDV dahil
    sa.Column("kdv_json", sa.Text),
    sa.Column("liste_toplami", sa.Float),                             # seçilen liste fiyatı kaynağı, KDV dahil
    sa.Column("liste_toplami_logo", sa.Float),
    sa.Column("eksik_fiyat", sa.Integer),
    sa.Column("net_gelir", sa.Float),                                 # KDV hariç set geliri
    sa.Column("maliyet_toplami", sa.Float),
    sa.Column("eksik_maliyet", sa.Integer),
    sa.Column("ambalaj_turu", sa.String(40)),
    sa.Column("ambalaj_birim_maliyet", sa.Float),
    sa.Column("marj", sa.Float),
    sa.Column("marj_orani", sa.Float),
    sa.Column("hedef_adet", sa.Float),
    sa.Column("gerekce", sa.Text),
    sa.Column("tanitim", sa.Text),
    sa.Column("brief", sa.Text),
    sa.Column("notlar", sa.Text),
    sa.Column("bilesen_kaynak", sa.String(20)),
    sa.Column("crm_json", sa.Text),
    sa.Column("oneri_id", sa.String(20)),
    sa.Column("olusturan", sa.String(120)),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("karar_notu", sa.Text),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("linked_at", sa.DateTime(timezone=True)),
)
ITEMS = sa.Table(
    "semantic_mkt_set_items", _md,
    sa.Column("set_id", sa.String(20), primary_key=True),
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("sira", sa.Integer, nullable=False, default=0),
    sa.Column("adet", sa.Float, nullable=False),
    sa.Column("ad", sa.String(400)),
    sa.Column("liste_fiyat", sa.Float),
    sa.Column("liste_fiyat_logo", sa.Float),
    sa.Column("kdv", sa.Float),
    sa.Column("maliyet", sa.Float),
    sa.Column("maliyet_kaynak", sa.String(12)),
    sa.Column("stok", sa.Float),
    sa.Column("kaynak", sa.String(20), nullable=False),               # crm-set-islemi|logo-recete|oneri|elle
)
SALES = sa.Table(
    "semantic_mkt_set_sales", _md,
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("yil_ay", sa.String(7), primary_key=True),              # YYYY-AA
    sa.Column("tur", sa.String(12), nullable=False),                  # set|bilesen|promosyon
    sa.Column("net_adet", sa.Float, nullable=False),
    sa.Column("net_ciro", sa.Float, nullable=False),
    sa.Column("asof", sa.DateTime(timezone=True), nullable=False),
    sa.Column("veri_sonu", sa.String(10)),
)
PAIRS = sa.Table(
    "semantic_mkt_basket_pairs", _md,
    sa.Column("kod_a", sa.String(60), primary_key=True),
    sa.Column("kod_b", sa.String(60), primary_key=True),
    sa.Column("siparis_sayisi", sa.Integer, nullable=False),
    sa.Column("lift", sa.Float),
    sa.Column("donem", sa.String(40)),
    sa.Column("asof", sa.DateTime(timezone=True), nullable=False),
)
OFFERS = sa.Table(
    "semantic_mkt_gift_offers", _md,
    sa.Column("id", sa.String(20), primary_key=True),                 # KT-<yıl>-<sıra>
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("firma_id", sa.String(40), nullable=False),            # CRM AccountId
    sa.Column("firma_adi", sa.String(400)),
    sa.Column("firma_kodu", sa.String(40)),
    sa.Column("adet", sa.Integer, nullable=False),
    sa.Column("kisi_basi_butce", sa.Float, nullable=False),
    sa.Column("secenekler_json", sa.Text),
    sa.Column("secili_json", sa.Text),
    sa.Column("kademeler_json", sa.Text),
    sa.Column("mektup", sa.Text),
    sa.Column("gecerlilik", sa.String(10)),
    sa.Column("durum", sa.String(16), nullable=False),
    sa.Column("sezon", sa.String(200)),
    sa.Column("notlar", sa.Text),
    sa.Column("hazirlayan", sa.String(120)),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("karar_notu", sa.Text),
    sa.Column("pdf_yolu", sa.String(300)),                           # belge anlık üretilir; saklanırsa yolu
    sa.Column("m32_firsat_id", sa.String(60)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("submitted_at", sa.DateTime(timezone=True)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
)
PROMO = sa.Table(
    "semantic_mkt_promo_items", _md,
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("ad", sa.String(400)),
    sa.Column("tur", sa.String(30), nullable=False),                  # 157|crm-promosyon|crm-pazarlama-materyali
    sa.Column("crm_tip", sa.String(40)),
    sa.Column("promosyon_tipi", sa.String(60)),
    sa.Column("stok", sa.Float),
    sa.Column("son12_adet", sa.Float),
    sa.Column("son12_ciro", sa.Float),
    sa.Column("bedelsiz_cikis", sa.Float),                            # ölçüm yöntemi belirlenince dolar
    sa.Column("asof", sa.DateTime(timezone=True), nullable=False),
)
BOOKS = sa.Table(
    "semantic_mkt_books", _md,
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("ad", sa.String(400)),
    sa.Column("crm_id", sa.String(40)),
    sa.Column("crm_tip", sa.Integer),
    sa.Column("yazar", sa.String(300)),
    sa.Column("dizi", sa.String(200)),
    sa.Column("turler", sa.String(400)),
    sa.Column("yaslar", sa.String(200)),
    sa.Column("hedef", sa.String(20)),
    sa.Column("yas_min", sa.Integer),
    sa.Column("yas_max", sa.Integer),
    sa.Column("promosyon_tipi", sa.String(60)),
    sa.Column("ozet", sa.Text),
    sa.Column("spot", sa.Text),
    sa.Column("liste_fiyat", sa.Float),                               # CRM KDV dahil fiyat
    sa.Column("logo_fiyat", sa.Float),
    sa.Column("logo_fiyat_kdv_dahil", sa.Boolean),
    sa.Column("kdv", sa.Float),                                       # Logo ITEMS.SELLVAT (%)
    sa.Column("kart", sa.Integer),                                    # Logo ITEMS.CARDTYPE
    sa.Column("stok", sa.Float, nullable=False, default=0.0),
    sa.Column("son12_adet", sa.Float, nullable=False, default=0.0),
    sa.Column("son12_ciro", sa.Float, nullable=False, default=0.0),
    sa.Column("maliyet_logo", sa.Float),
    sa.Column("maliyet_logo_tarih", sa.String(10)),
    sa.Column("in_logo", sa.Boolean, nullable=False, default=False),
    sa.Column("in_crm", sa.Boolean, nullable=False, default=False),
)
SUGG = sa.Table(
    "semantic_mkt_set_suggestions", _md,
    sa.Column("id", sa.String(20), primary_key=True),                 # SO-<bileşenlerin özeti>
    sa.Column("tur", sa.String(12), nullable=False),                  # birlikte|yazar|seri
    sa.Column("ad", sa.String(300), nullable=False),
    sa.Column("ad_llm", sa.String(300)),
    sa.Column("aciklama_llm", sa.Text),
    sa.Column("gerekce", sa.Text),
    sa.Column("kodlar_json", sa.Text, nullable=False),
    sa.Column("skor", sa.Float, nullable=False, default=0.0),
    sa.Column("liste_toplami", sa.Float),
    sa.Column("onerilen_fiyat", sa.Float),
    sa.Column("stok_min", sa.Float),
    sa.Column("yas_min", sa.Integer),
    sa.Column("yas_max", sa.Integer),
    sa.Column("turler", sa.String(400)),
    sa.Column("sezon_id", sa.String(40)),
    sa.Column("sezon_adi", sa.String(200)),
    sa.Column("sezon_olasilik", sa.Float),
    sa.Column("llm_at", sa.DateTime(timezone=True)),
    sa.Column("durum", sa.String(12), nullable=False),                # yeni|benimsendi|reddedildi
    sa.Column("set_id", sa.String(20)),
    sa.Column("karar_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)
META = sa.Table(
    "semantic_mkt_sets_meta", _md,
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

TYPES = {"tematik": "Tematik", "yazar": "Yazar", "seri": "Seri / dizi", "sezon": "Sezon", "kurumsal": "Kurumsal",
         "toplama": "Toplama set"}
SOURCES = {"crm": "CRM set kartı", "oneri": "ZEKİ AI önerisi", "elle": "Elle"}
STATUSES = {"oneri": "Öneri", "taslak": "Taslak", "onayda": "Onay bekliyor", "kart-bekliyor": "Onaylı — CRM kartı bekliyor",
            "satista": "Satışta", "kapanacak": "Kapanacak", "kapandi": "Kapandı"}
EDITABLE = ("oneri", "taslak")
ITEM_SOURCES = {"crm-set-islemi": "CRM set işlemi", "logo-recete": "Logo reçetesi", "oneri": "Öneri", "elle": "Elle"}
SUGG_TYPES = {"birlikte": "Birlikte alınanlar", "yazar": "Aynı yazar", "seri": "Aynı dizi"}
SUGG_STATUS = {"yeni": "Yeni", "benimsendi": "Taslağa alındı", "reddedildi": "Reddedildi"}
OFFER_STATUS = {"taslak": "Taslak", "onayda": "Onay bekliyor", "onaylandi": "Gönderilebilir", "gonderildi": "Gönderildi",
                "kazanildi": "Kazanıldı", "kaybedildi": "Kaybedildi"}
OFFER_FINAL = ("onaylandi", "gonderildi", "kazanildi", "kaybedildi")
PROMO_TYPES = {"157": "Ticari ürün (Logo 157)", "crm-promosyon": "CRM promosyon kartı",
               "crm-pazarlama-materyali": "CRM pazarlama materyali"}
PAGE_SIZE = 100
#: Maliyet yetkisi (`ozellik:set.maliyet-gor`) olmayana sunucu tarafında çıkarılan alanlar.
COST_KEYS = frozenset({"maliyet", "maliyetToplami", "maliyetKaynak", "maliyetTahmini", "eksikMaliyet", "marj", "marjOrani",
                       "marjUyari", "marjMesaj", "ambalajBirimMaliyet", "netGelir", "maliyetBirim", "birimMaliyet"})

DEFAULTS: dict[str, str] = {
    "SETS_COMPONENT_SOURCE": "auto",
    "SETS_BOM_LINETYPES": "",
    "SETS_SALES_LINETYPES": "0",
    "SETS_SALES_YEARS": "3",
    "SETS_LIST_PRICE_SOURCE": "crm",
    "SETS_COST_SOURCE": "m9",
    "SETS_PROMO_PREFIX": "157",
    "SETS_MARGIN_MIN_PCT": "",
    "SETS_B2C_ORDER_TYPES": "8",
    "SETS_B2C_NAME_PREFIX": "B2C",
    "SETS_BASKET_MONTHS": "24",
    "SETS_BASKET_MIN_ORDERS": "2",
    "SETS_SUGGEST_SIZE": "3",
    "SETS_SUGGEST_MAX_SIZE": "4",
    "SETS_SUGGEST_MIN_STOCK": "1",
    "SETS_DISCOUNT_MIN_N": "3",
    "SETS_GIFT_OPTIONS": "5",
    "SETS_GIFT_TIERS": "",
    "SETS_OFFER_VALID_DAYS": "30",
    "SETS_SEASON_LEAD_WEEKS": "8",
    "SETS_ALERT_RECIPIENTS": "",
    "SETS_LLM_BUDGET_SEC": "900",
    "SETS_LLM_MIN_PROB": "0.70",
    "SETS_LLM_MIN_MARGIN": "0.30",
    "SETS_COMPANY_NAME": "Timaş Yayınları",
}

_ready: set[int] = set()
_lock = threading.Lock()


class SetsError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    key = id(engine)
    with _lock:
        if key in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(key)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()


def _j(v: Optional[str], default: Any) -> Any:
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _text(v: Any, limit: int) -> Optional[str]:
    s = " ".join(str(v or "").split())
    return s[:limit] or None


def _longtext(v: Any, limit: int) -> Optional[str]:
    s = str(v or "").replace("\r\n", "\n").strip()
    return s[:limit] or None


def _num(v: Any, label: str, *, allow_none: bool = False, minimum: Optional[float] = 0.0,
         maximum: Optional[float] = None) -> Optional[float]:
    if v is None or v == "":
        if allow_none:
            return None
        raise SetsError(f"{label} boş olamaz.")
    try:
        n = float(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) and "," in v else float(v)
    except (TypeError, ValueError):
        raise SetsError(f"{label} sayı olmalı.") from None
    if math.isnan(n) or math.isinf(n):
        raise SetsError(f"{label} sayı olmalı.")
    if minimum is not None and n < minimum:
        raise SetsError(f"{label} {minimum:g} değerinden küçük olamaz.")
    if maximum is not None and n > maximum:
        raise SetsError(f"{label} {maximum:g} değerinden büyük olamaz.")
    return n


def fold(s: Any) -> str:
    t = str(s or "").translate(str.maketrans("İIıŞşĞğÜüÖöÇç", "iiissgguuoocc")).lower()
    return re.sub(r"\s+", " ", t).strip()


def _r2(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(float(v), 2)


# ------------------------------------------------------------------------------------------ ayarlar


def settings_from(conf: Callable[[str, str], str]) -> dict[str, Any]:
    def g(key: str) -> str:
        v = conf(key, DEFAULTS[key])
        return DEFAULTS[key] if v is None else str(v)

    def gi(key: str, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(float(g(key)))))
        except ValueError:
            return int(DEFAULTS[key])

    def gf(key: str) -> Optional[float]:
        raw = g(key).strip()
        if raw == "":
            return None
        try:
            return float(raw.replace(",", "."))
        except ValueError:
            return float(DEFAULTS[key]) if DEFAULTS[key] else None

    comp = g("SETS_COMPONENT_SOURCE").strip().lower()
    price = g("SETS_LIST_PRICE_SOURCE").strip().lower()
    return {
        "componentSource": comp if comp in ("auto", "crm", "logo") else "auto",
        "bomLinetypes": src.int_list(g("SETS_BOM_LINETYPES")),
        "salesLinetypes": src.int_list(g("SETS_SALES_LINETYPES")) or [0],
        "salesYears": gi("SETS_SALES_YEARS", 2, 12),
        "listPriceSource": price if price in ("crm", "logo") else "crm",
        "costSource": (g("SETS_COST_SOURCE").strip().lower() or "m9"),
        "promoPrefix": re.sub(r"[^0-9A-Za-z]", "", g("SETS_PROMO_PREFIX")) or "157",
        "marginMinPct": gf("SETS_MARGIN_MIN_PCT"),
        "b2cTypes": src.int_list(g("SETS_B2C_ORDER_TYPES")),
        "b2cPrefix": g("SETS_B2C_NAME_PREFIX").strip(),
        "basketMonths": gi("SETS_BASKET_MONTHS", 1, 120),
        "basketMinOrders": gi("SETS_BASKET_MIN_ORDERS", 1, 10_000),
        "suggestSize": gi("SETS_SUGGEST_SIZE", 2, 12),
        "suggestMaxSize": gi("SETS_SUGGEST_MAX_SIZE", 2, 12),
        "suggestMinStock": gf("SETS_SUGGEST_MIN_STOCK") or 0.0,
        "discountMinN": gi("SETS_DISCOUNT_MIN_N", 1, 10_000),
        "giftOptions": gi("SETS_GIFT_OPTIONS", 1, 50),
        "giftTiers": parse_tiers(g("SETS_GIFT_TIERS")),
        "offerValidDays": gi("SETS_OFFER_VALID_DAYS", 1, 365),
        "seasonLeadWeeks": gi("SETS_SEASON_LEAD_WEEKS", 0, 52),
        "alertRecipients": [x.strip() for x in g("SETS_ALERT_RECIPIENTS").replace(";", ",").split(",") if "@" in x],
        "llmBudgetSec": gi("SETS_LLM_BUDGET_SEC", 0, 6 * 3600),
        "llmMinProb": gf("SETS_LLM_MIN_PROB") or 0.70,
        "llmMinMargin": gf("SETS_LLM_MIN_MARGIN") or 0.0,
        "company": g("SETS_COMPANY_NAME").strip() or DEFAULTS["SETS_COMPANY_NAME"],
    }


def parse_tiers(raw: Any) -> list[tuple[int, float]]:
    """«100:5;300:10» → [(100, 0.05), (300, 0.10)] (adet eşiği → indirim oranı), eşiğe göre artan."""
    if isinstance(raw, list):
        out = []
        for t in raw:
            try:
                a, p = (t.get("adet"), t.get("indirim")) if isinstance(t, dict) else (t[0], t[1])
                a, p = int(float(a)), float(p)
            except (TypeError, ValueError, IndexError, AttributeError):
                raise SetsError("Kademe «adet» ve «indirim» sayı olmalı.") from None
            if a < 1 or not 0 <= p < 1:
                raise SetsError("Kademe adedi 1'den, indirimi 0 ile 1 arasında olmalı.")
            out.append((a, p))
        return sorted(out)
    out = []
    for part in re.split(r"[;,\s]+", str(raw or "")):
        m = re.match(r"^(\d+)\s*[:=]\s*(\d+(?:[.,]\d+)?)%?$", part.strip())
        if m:
            out.append((int(m.group(1)), float(m.group(2).replace(",", ".")) / 100.0))
    return sorted(out)


def tier_for(qty: float, tiers: list[tuple[int, float]]) -> float:
    pct = 0.0
    for a, p in tiers:
        if qty >= a:
            pct = p
    return pct


# ------------------------------------------------------------------------------------------ meta


def meta_get(engine: sa.engine.Engine, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(META).where(META.c.key == key)).first()
    if not row:
        return {}
    return {**_j(row.value_json, {}), "_at": _iso(row.updated_at)}


def meta_set(engine: sa.engine.Engine, key: str, value: dict[str, Any]) -> None:
    now = _now()
    with engine.begin() as c:
        if c.execute(sa.select(META.c.key).where(META.c.key == key)).first():
            c.execute(META.update().where(META.c.key == key).values(value_json=_dump(value), updated_at=now))
        else:
            c.execute(META.insert().values(key=key, value_json=_dump(value), updated_at=now))


def data_end(engine: sa.engine.Engine) -> Optional[date]:
    v = meta_get(engine, "data_end").get("date")
    return date.fromisoformat(v) if v else None


def _next_id(c: Any, table: sa.Table, prefix: str) -> str:
    ids = [r[0] for r in c.execute(sa.select(table.c.id).where(table.c.id.like(prefix + "%"))).all()]
    n = max([int(i[len(prefix):]) for i in ids if i[len(prefix):].isdigit()] or [0]) + 1
    return f"{prefix}{n:04d}"


def window12(end: Optional[date]) -> tuple[str, str]:
    """Son 12 ay (veri bitiş ayı dahil) → (ilk YYYY-AA, son YYYY-AA)."""
    e = end or today()
    y, m = e.year, e.month
    first = (y * 12 + m - 1) - 11
    return f"{first // 12:04d}-{first % 12 + 1:02d}", f"{y:04d}-{m:02d}"


def next_occurrence(iso: Optional[str], ref: date) -> Optional[date]:
    """Özel günün bugünden sonraki ilk tarihi: CRM tarihi gelecekteyse o, geçmişteyse aynı gün/ay bu ya da gelecek yıl."""
    if not iso:
        return None
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return None
    if d >= ref:
        return d
    for y in (ref.year, ref.year + 1):
        try:
            cand = date(y, d.month, min(d.day, 28) if d.month == 2 and d.day == 29 else d.day)
        except ValueError:
            continue
        if cand >= ref:
            return cand
    return None


def seasons(engine: sa.engine.Engine, ref: Optional[date] = None) -> list[dict[str, Any]]:
    ref = ref or today()
    out = []
    for s in meta_get(engine, "seasons").get("items") or []:
        nd = next_occurrence(s.get("tarih"), ref)
        out.append({**s, "sonraki": nd.isoformat() if nd else None, "gunKaldi": (nd - ref).days if nd else None})
    return sorted(out, key=lambda x: (x["sonraki"] or "9999", x["ad"]))


# ------------------------------------------------------------------------------------------ fiyat – marj


def price_calc(items: list[dict[str, Any]], set_price: Optional[float], pack_cost: Optional[float],
               st: dict[str, Any]) -> dict[str, Any]:
    """Set fiyatı (KDV dahil) → liste toplamı, indirim, KDV ayrışması, maliyet, marj. `items`: stok, adet, liste (KDV dahil),
    kdv (%), maliyet (KDV hariç birim; bilinmiyorsa None). Rakamlar kuruşa yuvarlanır."""
    lines = [i for i in items if (i.get("adet") or 0) > 0]
    liste = [(i["liste"] * i["adet"]) if i.get("liste") is not None else None for i in lines]
    missing_price = sum(1 for x in liste if x is None)
    total = sum(x for x in liste if x) if lines else 0.0
    discount = (1.0 - set_price / total) if (set_price is not None and total > 0 and missing_price == 0) else None
    method = "liste" if (missing_price == 0 and total > 0) else "adet"
    qty = sum(i["adet"] for i in lines) or 1.0
    vat_rows, net, unknown_vat = [], None, 0
    if lines:
        net_sum = 0.0
        for i, x in zip(lines, liste):
            share = (x / total) if method == "liste" else (i["adet"] / qty)
            rate = i.get("kdv")
            if rate is None:
                unknown_vat += 1
            r = float(rate or 0.0)
            part = (set_price or 0.0) * share
            net_sum += part / (1.0 + r / 100.0)
            vat_rows.append({"stok": i["stok"], "oran": rate, "pay": round(share, 6)})
        net = net_sum if set_price is not None else None
    missing_cost = sum(1 for i in lines if i.get("maliyet") is None)
    cost = sum(i["maliyet"] * i["adet"] for i in lines) if (lines and missing_cost == 0) else None
    pack = float(pack_cost or 0.0)
    margin = (net - cost - pack) if (net is not None and cost is not None) else None
    ratio = (margin / net) if (margin is not None and net and net > 0) else None
    floor = st.get("marginMinPct")
    warn = ratio is not None and floor is not None and ratio < floor / 100.0
    msg = None
    if not lines:
        msg = "Sette bileşen yok."
    elif missing_cost:
        msg = f"Marj hesaplanamadı: {missing_cost} kitapta maliyet yok."
    elif set_price is None:
        msg = "Set fiyatı girilmemiş."
    return {"listeToplami": _r2(total) if lines else None, "eksikFiyat": missing_price, "indirim": discount,
            "kdvYontemi": method, "kdv": vat_rows, "kdvBilinmeyen": unknown_vat, "netGelir": _r2(net),
            "maliyetToplami": _r2(cost), "eksikMaliyet": missing_cost, "ambalajBirimMaliyet": _r2(pack) if pack_cost is not None else None,
            "marj": _r2(margin), "marjOrani": ratio, "marjUyari": warn, "marjMesaj": msg,
            "altSinir": floor, "setFiyati": _r2(set_price)}


def strip_costs(obj: Any) -> Any:
    """Maliyet görme yetkisi yoksa maliyet ve marj alanları yanıttan çıkarılır (iç içe her yerde)."""
    if isinstance(obj, dict):
        return {k: strip_costs(v) for k, v in obj.items() if k not in COST_KEYS}
    if isinstance(obj, list):
        return [strip_costs(x) for x in obj]
    return obj


def list_price(b: Any, st: dict[str, Any]) -> Optional[float]:
    """Kitabın KDV dahil liste fiyatı: ayardaki kaynak (CRM kart fiyatı ya da Logo satış listesi)."""
    if b is None:
        return None
    if st["listPriceSource"] == "logo":
        return logo_price_incl(b)
    return b.liste_fiyat if b.liste_fiyat and b.liste_fiyat > 0 else None


def logo_price_incl(b: Any) -> Optional[float]:
    if b is None or not b.logo_fiyat or b.logo_fiyat <= 0:
        return None
    return b.logo_fiyat if b.logo_fiyat_kdv_dahil else b.logo_fiyat * (1 + (b.kdv or 0.0) / 100.0)


def books_by_code(engine: sa.engine.Engine, codes: Iterable[str]) -> dict[str, Any]:
    codes = [c for c in dict.fromkeys(codes) if c]
    out: dict[str, Any] = {}
    with engine.connect() as c:
        for i in range(0, len(codes), 500):
            for r in c.execute(sa.select(BOOKS).where(BOOKS.c.stok_kodu.in_(codes[i:i + 500]))).all():
                out[r.stok_kodu] = r
    return out


def costs_for(engine: sa.engine.Engine, st: dict[str, Any], codes: Iterable[str], books: Optional[dict[str, Any]] = None) -> dict[str, dict[str, Any]]:
    codes = list(dict.fromkeys(codes))
    logo_costs = None
    if st["costSource"] == "logo":
        books = books if books is not None else books_by_code(engine, codes)
        logo_costs = {k: {"birim": b.maliyet_logo, "tarih": b.maliyet_logo_tarih} for k, b in books.items() if b.maliyet_logo}
    return src.unit_costs(codes, st["costSource"], logo_costs)


def enrich(engine: sa.engine.Engine, st: dict[str, Any], items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kalemlere ad, liste fiyatı (iki kaynak), KDV, stok ve maliyet eklenir (köprünün kitap tablosundan)."""
    codes = [i["stok"] for i in items]
    books = books_by_code(engine, codes)
    costs = costs_for(engine, st, codes, books)
    out = []
    for i in items:
        b = books.get(i["stok"])
        cst = costs.get(i["stok"]) or {}
        out.append({**i, "ad": (b.ad if b else None) or i.get("ad"), "liste": list_price(b, st), "listeLogo": _r2(logo_price_incl(b)),
                    "listeCrm": b.liste_fiyat if b else None, "kdv": b.kdv if b else None, "stokAdet": b.stok if b else None,
                    "maliyet": cst.get("birim"), "maliyetKaynak": cst.get("kaynak"), "maliyetTahmini": cst.get("tahmini"),
                    "yazar": b.yazar if b else None, "bilinmiyor": b is None})
    return out


# ------------------------------------------------------------------------------------------ setler


def _items_of(c: Any, set_ids: list[str]) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for i in range(0, len(set_ids), 500):
        for r in c.execute(sa.select(ITEMS).where(ITEMS.c.set_id.in_(set_ids[i:i + 500])).order_by(ITEMS.c.sira, ITEMS.c.stok_kodu)).all():
            out.setdefault(r.set_id, []).append(r)
    return out


def _sales12(engine: sa.engine.Engine, codes: list[str]) -> dict[str, dict[str, float]]:
    a, b = window12(data_end(engine))
    out: dict[str, dict[str, float]] = {}
    codes = [c for c in dict.fromkeys(codes) if c]
    with engine.connect() as c:
        for i in range(0, len(codes), 500):
            q = (sa.select(SALES.c.stok_kodu, sa.func.sum(SALES.c.net_adet), sa.func.sum(SALES.c.net_ciro))
                 .where(SALES.c.stok_kodu.in_(codes[i:i + 500]), SALES.c.yil_ay >= a, SALES.c.yil_ay <= b)
                 .group_by(SALES.c.stok_kodu))
            for code, adet, ciro in c.execute(q).all():
                out[code] = {"adet": float(adet or 0), "ciro": round(float(ciro or 0), 2)}
    return out


def _item_dict(r: Any) -> dict[str, Any]:
    return {"stok": r.stok_kodu, "ad": r.ad, "adet": r.adet, "liste": r.liste_fiyat, "listeLogo": r.liste_fiyat_logo, "kdv": r.kdv,
            "maliyet": r.maliyet, "maliyetKaynak": r.maliyet_kaynak, "stokAdet": r.stok, "kaynak": r.kaynak,
            "kaynakAdi": ITEM_SOURCES.get(r.kaynak, r.kaynak)}


def _set_dict(r: Any, items: Optional[list[Any]] = None, sales: Optional[dict[str, dict[str, float]]] = None,
              stock: Optional[float] = None) -> dict[str, Any]:
    its = [_item_dict(i) for i in (items or [])]
    s12 = (sales or {}).get(r.stok_kodu or "") if r.stok_kodu else None
    stoks = [i["stokAdet"] for i in its if i["stokAdet"] is not None]
    discount = (1.0 - r.set_fiyati / r.liste_toplami) if (r.set_fiyati and r.liste_toplami and not r.eksik_fiyat) else None
    return {"id": r.id, "ad": r.ad, "tur": r.tur, "turAdi": TYPES.get(r.tur, r.tur), "kaynak": r.kaynak,
            "kaynakAdi": SOURCES.get(r.kaynak, r.kaynak), "crmKitapId": r.crm_kitap_id, "stokKodu": r.stok_kodu,
            "durum": r.durum, "durumAdi": STATUSES.get(r.durum, r.durum), "sezonId": r.sezon_id, "sezonAdi": r.sezon_adi,
            "kanal": _j(r.kanal_json, []), "setFiyati": r.set_fiyati, "listeToplami": r.liste_toplami,
            "listeToplamiLogo": r.liste_toplami_logo, "eksikFiyat": r.eksik_fiyat or 0, "indirim": discount,
            "netGelir": r.net_gelir, "maliyetToplami": r.maliyet_toplami, "eksikMaliyet": r.eksik_maliyet,
            "ambalajTuru": r.ambalaj_turu, "ambalajBirimMaliyet": r.ambalaj_birim_maliyet, "marj": r.marj, "marjOrani": r.marj_orani,
            "hedefAdet": r.hedef_adet, "gerekce": r.gerekce, "tanitim": r.tanitim, "brief": r.brief, "notlar": r.notlar,
            "bilesenKaynak": r.bilesen_kaynak, "crm": _j(r.crm_json, {}), "oneriId": r.oneri_id,
            "bilesenSayisi": len(its), "bilesenler": its if items is not None else None,
            "bilesenStokMin": min(stoks) if stoks else None,
            "stok": stock, "son12Adet": (s12 or {}).get("adet") if r.stok_kodu else None,
            "son12Ciro": (s12 or {}).get("ciro") if r.stok_kodu else None,
            "olusturan": r.olusturan, "gonderen": r.gonderen, "onaylayan": r.onaylayan, "kararNotu": r.karar_notu,
            "createdAt": _iso(r.created_at), "updatedAt": _iso(r.updated_at), "submittedAt": _iso(r.submitted_at),
            "decidedAt": _iso(r.decided_at), "linkedAt": _iso(r.linked_at)}


def _row(c: Any, tenant: str, set_id: str) -> Any:
    r = c.execute(sa.select(SETS).where(SETS.c.tenant_id == tenant, SETS.c.id == set_id)).first()
    if r is None:
        raise SetsError("Set bulunamadı.", 404)
    return r


def list_sets(engine: sa.engine.Engine, tenant: str, *, durum: str = "", tur: str = "", sezon: str = "", kanal: str = "",
              q: str = "", sort: str = "ciro", page: int = 0) -> dict[str, Any]:
    """Bütün setler (tavansız, sayfalı). Kolonlar: bileşen sayısı, set fiyatı, liste toplamı, indirim, marj, stok, son 12 ay."""
    with engine.connect() as c:
        rows = c.execute(sa.select(SETS).where(SETS.c.tenant_id == tenant)).all()
        items = _items_of(c, [r.id for r in rows])
    codes = [r.stok_kodu for r in rows if r.stok_kodu]
    sales = _sales12(engine, codes)
    stock = {k: b.stok for k, b in books_by_code(engine, codes).items()}
    all_items = []
    for r in rows:
        its = items.get(r.id, [])
        stoks = [i.stok for i in its if i.stok is not None]
        all_items.append(_set_dict(r, None, sales, stock.get(r.stok_kodu or ""))
                         | {"bilesenSayisi": len(its), "bilesenStokMin": min(stoks) if stoks else None})
    summary = {"toplam": len(all_items),
               "satista": sum(1 for s in all_items if s["durum"] == "satista"),
               "satissiz": sum(1 for s in all_items if s["durum"] == "satista" and not (s["son12Adet"] or 0) > 0),
               "marjBilinmiyor": sum(1 for s in all_items if s["durum"] not in ("kapandi",) and s["marj"] is None),
               "onayda": sum(1 for s in all_items if s["durum"] == "onayda"),
               "kartBekliyor": sum(1 for s in all_items if s["durum"] == "kart-bekliyor"),
               "oneri": sum(1 for s in all_items if s["durum"] in ("oneri", "taslak"))}
    f = fold(q)
    out = [s for s in all_items
           if (not durum or s["durum"] in durum.split(","))
           and (not tur or s["tur"] == tur)
           and (not sezon or s["sezonId"] == sezon)
           and (not kanal or any(fold(kanal) in fold(k) for k in (s["kanal"] or [])) or fold(kanal) in fold((s["crm"] or {}).get("kanal")))
           and (not f or f in fold(s["ad"]) or f in fold(s["stokKodu"]))]
    keyf = {
        "ciro": lambda s: -(s["son12Ciro"] or 0),
        "adet": lambda s: -(s["son12Adet"] or 0),
        "ad": lambda s: fold(s["ad"]),
        "marj": lambda s: (s["marjOrani"] is None, s["marjOrani"] if s["marjOrani"] is not None else 0),
        "indirim": lambda s: -(s["indirim"] or 0),
        "durum": lambda s: list(STATUSES).index(s["durum"]) if s["durum"] in STATUSES else 99,
        "yeni": lambda s: s["createdAt"] or "",
    }.get(sort, lambda s: -(s["son12Ciro"] or 0))
    out.sort(key=keyf, reverse=(sort == "yeni"))
    page = max(0, page)
    end = data_end(engine)
    return {"items": out[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], "total": len(out), "page": page, "pageSize": PAGE_SIZE,
            "summary": summary, "dataEnd": end.isoformat() if end else None, "window": window12(end)}


def get_set(engine: sa.engine.Engine, tenant: str, set_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _row(c, tenant, set_id)
        items = _items_of(c, [r.id]).get(r.id, [])
    codes = [r.stok_kodu] if r.stok_kodu else []
    stock = {k: b.stok for k, b in books_by_code(engine, codes).items()}
    return _set_dict(r, items, _sales12(engine, codes), stock.get(r.stok_kodu or ""))


def _clean_items(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise SetsError("En az bir bileşen gerekli.")
    seen: dict[str, float] = {}
    for x in raw:
        code = str((x or {}).get("stok") or (x or {}).get("stokKodu") or "").strip()
        if not src.code_ok(code):
            raise SetsError(f"Stok kodu «{code}» geçersiz.")
        qty = _num((x or {}).get("adet", 1), "Adet", minimum=0.0001, maximum=10_000)
        seen[code] = seen.get(code, 0.0) + float(qty)
    return [{"stok": k, "adet": v} for k, v in seen.items()]


def _write_items(c: Any, set_id: str, items: list[dict[str, Any]], kaynak: str) -> None:
    c.execute(ITEMS.delete().where(ITEMS.c.set_id == set_id))
    rows = [{"set_id": set_id, "stok_kodu": i["stok"][:60], "sira": n, "adet": float(i["adet"]), "ad": (i.get("ad") or None),
             "liste_fiyat": i.get("liste"), "liste_fiyat_logo": i.get("listeLogo"), "kdv": i.get("kdv"), "maliyet": i.get("maliyet"),
             "maliyet_kaynak": i.get("maliyetKaynak"), "stok": i.get("stokAdet"), "kaynak": i.get("kaynak") or kaynak}
            for n, i in enumerate(items)]
    if rows:
        c.execute(ITEMS.insert(), rows)


def recalc(engine: sa.engine.Engine, st: dict[str, Any], set_ids: Optional[list[str]] = None) -> int:
    """Setlerin kalemlerini kitap tablosundan tazeler, fiyat–marjı yeniden hesaplar ve saklar."""
    with engine.connect() as c:
        q = sa.select(SETS)
        if set_ids is not None:
            q = q.where(SETS.c.id.in_(set_ids or ["-"]))
        rows = c.execute(q).all()
        items = _items_of(c, [r.id for r in rows])
    n = 0
    for r in rows:
        its = [{"stok": i.stok_kodu, "adet": i.adet, "kaynak": i.kaynak, "ad": i.ad} for i in items.get(r.id, [])]
        en = enrich(engine, st, its)
        calc = price_calc(en, r.set_fiyati, r.ambalaj_birim_maliyet, st)
        with engine.begin() as c:
            _write_items(c, r.id, en, "elle")
            c.execute(SETS.update().where(SETS.c.id == r.id).values(
                liste_toplami=calc["listeToplami"], liste_toplami_logo=_r2(sum((i["listeLogo"] or 0) * i["adet"] for i in en)) if en and all(i["listeLogo"] for i in en) else None,
                eksik_fiyat=calc["eksikFiyat"], net_gelir=calc["netGelir"], maliyet_toplami=calc["maliyetToplami"],
                eksik_maliyet=calc["eksikMaliyet"], marj=calc["marj"], marj_orani=calc["marjOrani"], kdv_json=_dump(calc["kdv"])))
        n += 1
    return n


def create_set(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, user: str, body: dict[str, Any], *,
               kaynak: str = "elle", oneri_id: Optional[str] = None) -> dict[str, Any]:
    name = _text(body.get("ad"), 300)
    if not name:
        raise SetsError("Set adı gerekli.")
    tur = str(body.get("tur") or "tematik")
    if tur not in TYPES:
        raise SetsError("Set türü geçersiz.")
    items = _clean_items(body.get("bilesenler") or body.get("items"))
    price = _num(body.get("setFiyati"), "Set fiyatı", allow_none=True, minimum=0.0)
    now = _now()
    with engine.begin() as c:
        sid = _next_id(c, SETS, f"MS-{today().year}-")
        c.execute(SETS.insert().values(
            id=sid, tenant_id=tenant, ad=name, tur=tur, kaynak=kaynak, durum="taslak", set_fiyati=price,
            kanal_json=_dump([k for k in (_text(x, 60) for x in (body.get("kanal") if isinstance(body.get("kanal"), list) else [])) if k]), gerekce=_longtext(body.get("gerekce"), 4000), oneri_id=oneri_id,
            sezon_id=_text(body.get("sezonId"), 40), sezon_adi=_text(body.get("sezonAdi"), 200),
            bilesen_kaynak="oneri" if kaynak == "oneri" else "elle", olusturan=user, created_at=now, updated_at=now))
        _write_items(c, sid, [{**i, "kaynak": "oneri" if kaynak == "oneri" else "elle"} for i in items], "elle")
    recalc(engine, st, [sid])
    return get_set(engine, tenant, sid)


def update_set(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, user: str, set_id: str,
               body: dict[str, Any], seasons_list: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    with engine.connect() as c:
        r = _row(c, tenant, set_id)
    vals: dict[str, Any] = {}
    core = {"ad", "tur", "setFiyati", "ambalajTuru", "ambalajBirimMaliyet"}
    if core & set(body) and r.durum not in EDITABLE:
        raise SetsError("Onaya gönderilmiş ya da satıştaki setin adı, fiyatı ve ambalajı değiştirilemez; önce onaydan çekin.", 409)
    if "ad" in body:
        vals["ad"] = _text(body["ad"], 300) or r.ad
    if "tur" in body:
        if body["tur"] not in TYPES:
            raise SetsError("Set türü geçersiz.")
        vals["tur"] = body["tur"]
    if "setFiyati" in body:
        vals["set_fiyati"] = _num(body["setFiyati"], "Set fiyatı", allow_none=True)
    if "ambalajTuru" in body:
        vals["ambalaj_turu"] = _text(body["ambalajTuru"], 40)
    if "ambalajBirimMaliyet" in body:
        vals["ambalaj_birim_maliyet"] = _num(body["ambalajBirimMaliyet"], "Ambalaj birim maliyeti", allow_none=True)
    if "hedefAdet" in body:
        vals["hedef_adet"] = _num(body["hedefAdet"], "Hedef adet", allow_none=True)
    if "kanal" in body:
        k = body["kanal"] if isinstance(body["kanal"], list) else []
        vals["kanal_json"] = _dump([_text(x, 60) for x in k if _text(x, 60)])
    for key, col, lim in (("gerekce", "gerekce", 4000), ("tanitim", "tanitim", 8000), ("brief", "brief", 8000), ("notlar", "notlar", 4000)):
        if key in body:
            vals[col] = _longtext(body[key], lim)
    if "sezonId" in body:
        sid = _text(body["sezonId"], 40)
        hit = next((s for s in seasons_list if s["id"] == sid), None) if sid else None
        if sid and not hit:
            raise SetsError("Özel gün bulunamadı.")
        vals["sezon_id"], vals["sezon_adi"] = (sid, hit["ad"]) if hit else (None, None)
    if "durum" in body and body["durum"] != r.durum:
        allowed = {"satista": ("kapanacak", "kapandi"), "kapanacak": ("satista", "kapandi"), "oneri": ("taslak",)}
        if body["durum"] not in allowed.get(r.durum, ()):
            raise SetsError(f"«{STATUSES.get(r.durum)}» durumundan «{STATUSES.get(body['durum'], body['durum'])}» durumuna geçilemez.", 409)
        vals["durum"] = body["durum"]
    if not vals:
        return get_set(engine, tenant, set_id), {}
    diff = {k: {"once": getattr(r, k), "sonra": v} for k, v in vals.items() if getattr(r, k) != v and k not in ("tanitim", "brief")}
    vals["updated_at"] = _now()
    with engine.begin() as c:
        c.execute(SETS.update().where(SETS.c.id == set_id).values(**vals))
    if {"set_fiyati", "ambalaj_birim_maliyet"} & set(vals):
        recalc(engine, st, [set_id])
    return get_set(engine, tenant, set_id), diff


def put_items(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, set_id: str, raw: Any) -> dict[str, Any]:
    with engine.connect() as c:
        r = _row(c, tenant, set_id)
    if r.durum not in EDITABLE:
        raise SetsError("Yalnız taslak setin bileşenleri değişir.", 409)
    items = _clean_items(raw)
    with engine.begin() as c:
        _write_items(c, set_id, [{**i, "kaynak": "elle"} for i in items], "elle")
        c.execute(SETS.update().where(SETS.c.id == set_id).values(updated_at=_now(), bilesen_kaynak="elle"))
    recalc(engine, st, [set_id])
    return get_set(engine, tenant, set_id)


def delete_set(engine: sa.engine.Engine, tenant: str, set_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _row(c, tenant, set_id)
    if r.kaynak == "crm" or r.durum not in EDITABLE:
        raise SetsError("Yalnız portalda açılmış taslak set silinir.", 409)
    with engine.begin() as c:
        c.execute(ITEMS.delete().where(ITEMS.c.set_id == set_id))
        c.execute(SETS.delete().where(SETS.c.id == set_id))
        if r.oneri_id:
            c.execute(SUGG.update().where(SUGG.c.id == r.oneri_id).values(durum="yeni", set_id=None, updated_at=_now()))
    return {"id": r.id, "ad": r.ad}


def price_preview(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, set_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Kaydetmeden hesap: gövdedeki fiyat/ambalaj/bileşen, yoksa setin kendi değeri."""
    with engine.connect() as c:
        r = _row(c, tenant, set_id)
        items = _items_of(c, [r.id]).get(r.id, [])
    raw = body.get("bilesenler")
    its = _clean_items(raw) if raw is not None else [{"stok": i.stok_kodu, "adet": i.adet} for i in items]
    price = _num(body["setFiyati"], "Set fiyatı", allow_none=True) if "setFiyati" in body else r.set_fiyati
    if "indirim" in body and body.get("indirim") not in (None, ""):
        d = _num(body["indirim"], "İndirim", minimum=0.0, maximum=0.95)
        en0 = enrich(engine, st, its)
        tot = sum((i["liste"] or 0) * i["adet"] for i in en0)
        price = round(tot * (1 - d), 2) if tot else price
    pack = _num(body["ambalajBirimMaliyet"], "Ambalaj birim maliyeti", allow_none=True) if "ambalajBirimMaliyet" in body else r.ambalaj_birim_maliyet
    en = enrich(engine, st, its)
    return {**price_calc(en, price, pack, st), "bilesenler": en}


# ------------------------------------------------------------------------------------------ onay akışı


def submit_set(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, user: str, set_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _row(c, tenant, set_id)
        n_items = len(_items_of(c, [r.id]).get(r.id, []))
    if r.durum not in EDITABLE:
        raise SetsError("Yalnız taslak set onaya gönderilir.", 409)
    if not n_items:
        raise SetsError("Bileşeni olmayan set onaya gönderilemez.")
    if r.set_fiyati is None:
        raise SetsError("Set fiyatı girilmeden onaya gönderilemez.")
    with engine.begin() as c:
        c.execute(SETS.update().where(SETS.c.id == set_id).values(durum="onayda", gonderen=user, submitted_at=_now(),
                                                                   updated_at=_now(), karar_notu=None))
    return get_set(engine, tenant, set_id)


def withdraw_set(engine: sa.engine.Engine, tenant: str, user: str, set_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _row(c, tenant, set_id)
    if r.durum != "onayda":
        raise SetsError("Set onay beklemiyor.", 409)
    with engine.begin() as c:
        c.execute(SETS.update().where(SETS.c.id == set_id).values(durum="taslak", updated_at=_now()))
    return get_set(engine, tenant, set_id)


def decide_set(engine: sa.engine.Engine, tenant: str, user: str, set_id: str, approve: bool, note: Any) -> dict[str, Any]:
    """Onay (fiyat dahil): gönderen onaylayamaz (409). Onaylanan set «CRM kartı bekliyor» olur; kart listesi açılır."""
    with engine.connect() as c:
        r = _row(c, tenant, set_id)
    if r.durum != "onayda":
        raise SetsError("Set onay beklemiyor.", 409)
    if (r.gonderen or "").lower() == (user or "").lower():
        raise SetsError("Onaya gönderen kişi seti onaylayamaz; onayı başka bir yetkili verir.", 409)
    text = _longtext(note, 2000)
    if not approve and not text:
        raise SetsError("Geri gönderme için gerekçe yazın.")
    with engine.begin() as c:
        c.execute(SETS.update().where(SETS.c.id == set_id).values(
            durum="kart-bekliyor" if approve else "taslak", onaylayan=user, decided_at=_now(), karar_notu=text, updated_at=_now()))
    return get_set(engine, tenant, set_id)


# ------------------------------------------------------------------------------------------ açılacak kart ve eşleme


def card_todo(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, set_id: str) -> dict[str, Any]:
    """Onaylı set için CRM «Set İşlemi» ve kart akışına girilecek bilgi. Barkod önerilmez (TİMAŞ verir)."""
    s = get_set(engine, tenant, set_id)
    if s["durum"] not in ("kart-bekliyor", "satista"):
        raise SetsError("Kart listesi yalnız onaylanmış set için çıkar.", 409)
    kanal = s["kanal"] or []
    set_tipi = "Toplama Set" if any("toplama" in fold(k) for k in kanal) or s["tur"] == "toplama" else "Normal Set"
    return {"setId": s["id"], "ad": s["ad"], "setTipi": set_tipi, "satisKanallari": kanal,
            "onerilenFiyat": s["setFiyati"], "fiyatKdvDahil": True, "hedefAdet": s["hedefAdet"],
            "ambalaj": s["ambalajTuru"], "sezon": s["sezonAdi"], "onaylayan": s["onaylayan"], "onayTarihi": s["decidedAt"],
            "bilesenler": [{"stok": i["stok"], "ad": i["ad"], "adet": i["adet"], "kdv": i["kdv"], "stokAdet": i["stokAdet"]}
                           for i in (s["bilesenler"] or [])],
            "barkod": "Set barkodu TİMAŞ tarafından verilir.",
            "adimlar": ["CRM'de kitap kartı «Tip = Set» olarak açılır (set tipi, set özellikleri, satış kanalı, fiyat).",
                        "Bağlı proje kartına set adı, set barkodu ve set kitap adedi girilir.",
                        "CRM «Set İşlemi» ile set yapılır (bileşenler ve adetleri yukarıdaki listeden) ve Logo'ya aktarılır.",
                        "Kart açılınca portal CRM'i okuyup seti kendiliğinden eşler; eşleşmezse set ekranında stok kodu girilir."],
            "eslenmis": s["stokKodu"]}


def card_todo_csv(todo: dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Set", todo["ad"]])
    w.writerow(["Set tipi", todo["setTipi"]])
    w.writerow(["Satış kanalı", ", ".join(todo["satisKanallari"] or []) or "—"])
    w.writerow(["Önerilen fiyat (KDV dahil)", _tr(todo["onerilenFiyat"])])
    w.writerow(["Hedef set adedi", _tr(todo["hedefAdet"], 0)])
    w.writerow(["Ambalaj", todo["ambalaj"] or "—"])
    w.writerow(["Özel gün", todo["sezon"] or "—"])
    w.writerow(["Barkod", todo["barkod"]])
    w.writerow([])
    w.writerow(["Bileşen stok kodu", "Ad", "Adet", "KDV %", "Logo stoku"])
    for b in todo["bilesenler"]:
        w.writerow([b["stok"], b["ad"] or "", _tr(b["adet"], 0), _tr(b["kdv"], 0), _tr(b["stokAdet"], 0)])
    return "﻿" + buf.getvalue()


def _tr(v: Any, d: int = 2) -> str:
    if v is None:
        return "—"
    s = f"{float(v):,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def link_set(engine: sa.engine.Engine, tenant: str, set_id: str, code: str, card: Optional[dict[str, Any]]) -> dict[str, Any]:
    """CRM'de açılan kartla eşleme. `card` CRM'den okunmuş karttır (yoksa kod CRM'de yok)."""
    with engine.connect() as c:
        r = _row(c, tenant, set_id)
        other = c.execute(sa.select(SETS.c.id).where(SETS.c.tenant_id == tenant, SETS.c.stok_kodu == code, SETS.c.id != set_id,
                                                     SETS.c.kaynak != "crm")).first()
    if r.durum not in ("kart-bekliyor", "satista"):
        raise SetsError("Yalnız onaylanmış set bir CRM kartıyla eşlenir.", 409)
    if card is None:
        raise SetsError(f"«{code}» stok kodlu etkin kart CRM'de bulunamadı.", 404)
    if card.get("tip") != 4:
        raise SetsError(f"CRM'deki «{card.get('ad')}» kartının türü «{card.get('tipAdi') or '—'}»; set kartı («Set») olmalı.", 409)
    if other:
        raise SetsError(f"Bu stok kodu {other[0]} setine eşlenmiş.", 409)
    now = _now()
    with engine.begin() as c:
        # CRM okumasından gelen aynı kodlu kopya (kaynak=crm) varsa portal setine katılır.
        dup = c.execute(sa.select(SETS.c.id).where(SETS.c.tenant_id == tenant, SETS.c.stok_kodu == code, SETS.c.kaynak == "crm")).first()
        if dup:
            c.execute(ITEMS.delete().where(ITEMS.c.set_id == dup[0]))
            c.execute(SETS.delete().where(SETS.c.id == dup[0]))
        c.execute(SETS.update().where(SETS.c.id == set_id).values(stok_kodu=code, crm_kitap_id=card.get("id"), durum="satista",
                                                                   linked_at=now, updated_at=now))
    return get_set(engine, tenant, set_id)


def auto_link(engine: sa.engine.Engine, tenant: str, crm_components: dict[str, dict[str, Any]],
              crm_sets: list[dict[str, Any]]) -> list[dict[str, str]]:
    """«Kart bekliyor» setin bileşenleri (kod ve adet) CRM'deki tek bir set işlemiyle birebir tutuyorsa eşler."""
    ids = {s["stok"]: s for s in crm_sets if s.get("stok")}
    sig: dict[tuple, list[str]] = {}
    for code, comp in crm_components.items():
        if code in ids:
            key = tuple(sorted((b["stok"], round(b["adet"], 4)) for b in comp["bilesenler"]))
            sig.setdefault(key, []).append(code)
    out = []
    with engine.connect() as c:
        waiting = c.execute(sa.select(SETS).where(SETS.c.tenant_id == tenant, SETS.c.durum == "kart-bekliyor",
                                                  SETS.c.stok_kodu.is_(None))).all()
        taken = {r[0] for r in c.execute(sa.select(SETS.c.stok_kodu).where(SETS.c.tenant_id == tenant, SETS.c.kaynak != "crm",
                                                                           SETS.c.stok_kodu.isnot(None))).all()}
        items = _items_of(c, [r.id for r in waiting])
    for r in waiting:
        key = tuple(sorted((i.stok_kodu, round(i.adet, 4)) for i in items.get(r.id, [])))
        cands = [x for x in sig.get(key, []) if x not in taken]
        if len(cands) == 1:
            code = cands[0]
            card = ids[code]
            link_set(engine, tenant, r.id, code, {"id": card["id"], "ad": card["ad"], "tip": 4})
            taken.add(code)
            out.append({"set": r.id, "stok": code})
    return out


def effect(engine: sa.engine.Engine, tenant: str, set_id: str) -> dict[str, Any]:
    """Sonraki sürüm: bileşenlerin tek satışı set öncesi/sonrası. Şimdilik yalnız aylık seriler (yorum yok)."""
    s = get_set(engine, tenant, set_id)
    codes = [i["stok"] for i in s["bilesenler"] or []] + ([s["stokKodu"]] if s["stokKodu"] else [])
    series: dict[str, list[dict[str, Any]]] = {}
    with engine.connect() as c:
        for r in c.execute(sa.select(SALES).where(SALES.c.stok_kodu.in_(codes or ["-"])).order_by(SALES.c.yil_ay)).all():
            series.setdefault(r.stok_kodu, []).append({"ay": r.yil_ay, "adet": r.net_adet, "ciro": r.net_ciro, "tur": r.tur})
    first = next((x["ay"] for x in series.get(s["stokKodu"] or "", []) if x["adet"] > 0), None)
    return {"hazir": False, "mesaj": "Set–bileşen etkisi yorumu sonraki sürümde; aşağıdaki seriler ayrı ayrı okunur, toplanmaz.",
            "setIlkSatisAyi": first, "seriler": series}


# ------------------------------------------------------------------------------------------ kitaplar ve sepet


def find_books(engine: sa.engine.Engine, st: dict[str, Any], q: str, page: int = 0) -> dict[str, Any]:
    f = fold(q)
    if len(f) < 2:
        return {"items": [], "total": 0, "page": 0, "pageSize": PAGE_SIZE}
    with engine.connect() as c:
        rows = c.execute(sa.select(BOOKS)).all()
    hits = [b for b in rows if f in fold(b.ad) or fold(b.stok_kodu).startswith(f) or f in fold(b.yazar)]
    hits.sort(key=lambda b: -(b.son12_adet or 0))
    page = max(0, page)
    part = hits[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    return {"items": [_book_dict(b, st) for b in part], "total": len(hits), "page": page, "pageSize": PAGE_SIZE}


def _book_dict(b: Any, st: dict[str, Any]) -> dict[str, Any]:
    return {"stok": b.stok_kodu, "ad": b.ad, "yazar": b.yazar, "dizi": b.dizi, "tip": src.CRM_TIP.get(b.crm_tip), "liste": list_price(b, st),
            "listeLogo": _r2(logo_price_incl(b)), "kdv": b.kdv, "stokAdet": b.stok, "son12Adet": b.son12_adet, "son12Ciro": b.son12_ciro,
            "yaslar": b.yaslar, "turler": b.turler}


def basket_pairs(engine: sa.engine.Engine, *, q: str = "", page: int = 0) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(PAIRS).order_by(PAIRS.c.siparis_sayisi.desc(), PAIRS.c.lift.desc())).all()
    names = {k: b.ad for k, b in books_by_code(engine, {x for r in rows for x in (r.kod_a, r.kod_b)}).items()}
    f = fold(q)
    items = [{"a": r.kod_a, "b": r.kod_b, "adA": names.get(r.kod_a), "adB": names.get(r.kod_b), "siparis": r.siparis_sayisi,
              "lift": r.lift, "donem": r.donem} for r in rows]
    if f:
        items = [i for i in items if any(f in fold(i[k]) for k in ("a", "b", "adA", "adB"))]
    page = max(0, page)
    m = meta_get(engine, "basket")
    return {"items": items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], "total": len(items), "page": page, "pageSize": PAGE_SIZE,
            "meta": m}


def median_discount(engine: sa.engine.Engine, st: dict[str, Any]) -> dict[str, Any]:
    """Mevcut CRM setlerinin gerçekleşen indirimi (set fiyatı ↔ bileşen liste toplamı) medyanı."""
    with engine.connect() as c:
        rows = c.execute(sa.select(SETS.c.set_fiyati, SETS.c.liste_toplami).where(
            SETS.c.kaynak == "crm", SETS.c.eksik_fiyat == 0, SETS.c.set_fiyati > 0, SETS.c.liste_toplami > 0)).all()
    vals = [1 - p / t for p, t in rows if 0 <= 1 - p / t < 0.95]
    if len(vals) < st["discountMinN"]:
        return {"indirim": None, "n": len(vals)}
    return {"indirim": statistics.median(vals), "n": len(vals)}


# ------------------------------------------------------------------------------------------ öneriler


def _sugg_id(codes: Iterable[str]) -> str:
    return "SO-" + hashlib.sha1("|".join(sorted(codes)).encode("utf-8")).hexdigest()[:10]


def build_suggestions(engine: sa.engine.Engine, st: dict[str, Any]) -> dict[str, Any]:
    """Kural tabanlı adaylar (model yok): birlikte alım, aynı yazar, aynı dizi. Tavansız; önceki kararlar ve model adları korunur."""
    promo = st["promoPrefix"]
    with engine.connect() as c:
        books = {b.stok_kodu: b for b in c.execute(sa.select(BOOKS).where(BOOKS.c.crm_tip == 1, BOOKS.c.in_logo.is_(True))).all()
                 if not b.stok_kodu.startswith(promo) and (b.stok or 0) >= max(st["suggestMinStock"], 0.0001)}
        pairs = c.execute(sa.select(PAIRS)).all()
        old = {r.id: r for r in c.execute(sa.select(SUGG)).all()}
        existing = c.execute(sa.select(SETS.c.id)).all()
        items = _items_of(c, [r[0] for r in existing])
    taken = {frozenset(i.stok_kodu for i in its) for its in items.values() if its}
    disc = median_discount(engine, st)["indirim"]
    cands: dict[str, dict[str, Any]] = {}

    def add(tur: str, codes: list[str], name: str, reason: str, score: float) -> None:
        key = frozenset(codes)
        if len(key) < 2 or key in taken:
            return
        sid = _sugg_id(codes)
        if sid in cands:
            # Aynı bileşenler başka bir kuraldan da çıktı: tek öneri, gerekçeler birlikte (ilk kuralın türü ve adı kalır).
            cur = cands[sid]
            if reason not in cur["gerekce"]:
                cur["gerekce"] += " " + reason
            cur["skor"] = max(cur["skor"], score)
            return
        cands[sid] = {"id": sid, "tur": tur, "kodlar": list(codes), "ad": name[:300], "gerekce": reason, "skor": score}

    # 1) Birlikte alım: çift + ikisiyle de birlikte alınan kitaplarla genişletme
    adj: dict[str, dict[str, int]] = {}
    for p in pairs:
        if p.kod_a in books and p.kod_b in books:
            adj.setdefault(p.kod_a, {})[p.kod_b] = p.siparis_sayisi
            adj.setdefault(p.kod_b, {})[p.kod_a] = p.siparis_sayisi
    for p in sorted(pairs, key=lambda x: (-x.siparis_sayisi, -(x.lift or 0))):
        a, b = p.kod_a, p.kod_b
        # Birliktelik oranı 1'in altındaki çift, iki çok satanın tesadüfen aynı sepette olmasıdır: set gerekçesi değil.
        if a not in books or b not in books or (p.lift is not None and p.lift < 1):
            continue
        group, weakest = [a, b], p.siparis_sayisi
        while len(group) < st["suggestMaxSize"]:
            common = set(adj.get(group[0], {}))
            for g in group[1:]:
                common &= set(adj.get(g, {}))
            common -= set(group)
            if not common:
                break
            best = max(common, key=lambda x: (min(adj[g][x] for g in group), books[x].son12_adet or 0))
            weakest = min(weakest, min(adj[g][best] for g in group))
            group.append(best)
        names = " + ".join((books[x].ad or x) for x in group[:3]) + (" …" if len(group) > 3 else "")
        reason = (f"B2C siparişlerinde bu kitaplar birlikte alınmış: en zayıf çift {weakest} siparişte birlikte"
                  + (f" (ilk çift {p.siparis_sayisi} sipariş, birliktelik oranı {p.lift:.1f})" if p.lift else f" (ilk çift {p.siparis_sayisi} sipariş)") + ".")
        add("birlikte", group, f"Birlikte alınanlar: {names}", reason, float(weakest))

    # 2) Aynı yazar, 3) aynı dizi
    for tur, attr, label in (("yazar", "yazar", "seçkisi"), ("seri", "dizi", "dizisinden seçki")):
        groups: dict[str, list[Any]] = {}
        for b in books.values():
            v = getattr(b, attr)
            if v and "," not in v:
                groups.setdefault(v, []).append(b)
        for k, bs in groups.items():
            if len(bs) < st["suggestSize"]:
                continue
            bs.sort(key=lambda b: -(b.son12_adet or 0))
            pick = bs[:st["suggestSize"]]
            tot12 = sum(b.son12_adet or 0 for b in pick)
            reason = (f"Aynı {'yazarın' if tur == 'yazar' else 'dizinin'} stoğu olan {len(bs)} kitabından son 12 ayda en çok satan "
                      f"{len(pick)} tanesi (toplam {tot12:,.0f} adet).").replace(",", ".")
            add(tur, [b.stok_kodu for b in pick], f"{k} {label}", reason, tot12 / max(1, len(pick)))

    now = _now()
    rows = []
    for sid, s in cands.items():
        bs = [books[x] for x in s["kodlar"]]
        prices = [list_price(b, st) for b in bs]
        total = sum(prices) if all(p is not None for p in prices) else None
        o = old.get(sid)
        ymins = [b.yas_min for b in bs if b.yas_min]
        ymaxs = [b.yas_max for b in bs if b.yas_max]
        rows.append({"id": sid, "tur": s["tur"], "ad": s["ad"], "gerekce": s["gerekce"], "kodlar_json": _dump(s["kodlar"]),
                     "skor": s["skor"], "liste_toplami": _r2(total),
                     "onerilen_fiyat": _r2(round(total * (1 - disc), 0)) if (total and disc is not None) else _r2(total),
                     "stok_min": min(b.stok or 0 for b in bs), "yas_min": min(ymins) if ymins else None,
                     "yas_max": max(ymaxs) if ymaxs else None,
                     "turler": "; ".join(sorted({t.strip() for b in bs for t in re.split(r"[;,]", b.turler or "") if t.strip()}))[:400] or None,
                     "ad_llm": o.ad_llm if o else None, "aciklama_llm": o.aciklama_llm if o else None,
                     "sezon_id": o.sezon_id if o else None, "sezon_adi": o.sezon_adi if o else None,
                     "sezon_olasilik": o.sezon_olasilik if o else None, "llm_at": o.llm_at if o else None,
                     "durum": o.durum if o else "yeni", "set_id": o.set_id if o else None, "karar_by": o.karar_by if o else None,
                     "created_at": o.created_at if o else now, "updated_at": now})
    keep = [o for sid, o in old.items() if sid not in cands and o.durum != "yeni"]
    with engine.begin() as c:
        c.execute(SUGG.delete().where(SUGG.c.id.notin_([o.id for o in keep] or ["-"])))
        for i in range(0, len(rows), 2000):
            c.execute(SUGG.insert(), rows[i:i + 2000])
    return {"aday": len(rows), "birlikte": sum(1 for r in rows if r["tur"] == "birlikte"),
            "yazar": sum(1 for r in rows if r["tur"] == "yazar"), "seri": sum(1 for r in rows if r["tur"] == "seri"),
            "indirim": disc}


def _sugg_dict(r: Any, books: dict[str, Any], costs: dict[str, dict[str, Any]], st: dict[str, Any]) -> dict[str, Any]:
    codes = _j(r.kodlar_json, [])
    comps = []
    for code in codes:
        b = books.get(code)
        comps.append({"stok": code, "ad": b.ad if b else None, "yazar": b.yazar if b else None, "adet": 1, "liste": list_price(b, st),
                      "kdv": b.kdv if b else None, "stokAdet": b.stok if b else None, "maliyet": (costs.get(code) or {}).get("birim"),
                      "son12Adet": b.son12_adet if b else None})
    calc = price_calc(comps, r.onerilen_fiyat, None, st)
    return {"id": r.id, "tur": r.tur, "turAdi": SUGG_TYPES.get(r.tur, r.tur), "ad": r.ad_llm or r.ad, "kuralAdi": r.ad,
            "aciklama": r.aciklama_llm, "gerekce": r.gerekce, "skor": r.skor, "listeToplami": r.liste_toplami,
            "onerilenFiyat": r.onerilen_fiyat, "indirim": calc["indirim"], "marj": calc["marj"], "marjOrani": calc["marjOrani"],
            "marjMesaj": calc["marjMesaj"], "marjUyari": calc["marjUyari"], "stokMin": r.stok_min, "yasMin": r.yas_min, "yasMax": r.yas_max,
            "turler": r.turler, "sezonId": r.sezon_id, "sezonAdi": r.sezon_adi, "sezonOlasilik": r.sezon_olasilik,
            "durum": r.durum, "durumAdi": SUGG_STATUS.get(r.durum, r.durum), "setId": r.set_id, "bilesenler": comps}


def list_suggestions(engine: sa.engine.Engine, st: dict[str, Any], *, yas: Optional[int] = None, tema: str = "",
                     butce_min: Optional[float] = None, butce_max: Optional[float] = None, tur: str = "", durum: str = "yeni",
                     page: int = 0) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(SUGG).order_by(SUGG.c.skor.desc(), SUGG.c.id)).all()
    t = fold(tema)
    out = [r for r in rows
           if (not durum or r.durum == durum) and (not tur or r.tur == tur)
           and (yas is None or ((r.yas_min is None or r.yas_min <= yas) and (r.yas_max is None or yas <= r.yas_max) and (r.yas_min or r.yas_max)))
           and (not t or t in fold(r.turler) or t in fold(r.ad) or t in fold(r.ad_llm))
           and (butce_min is None or (r.liste_toplami or 0) >= butce_min)
           and (butce_max is None or (r.liste_toplami is not None and r.liste_toplami <= butce_max))]
    page = max(0, page)
    part = out[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    codes = {x for r in part for x in _j(r.kodlar_json, [])}
    books = books_by_code(engine, codes)
    costs = costs_for(engine, st, codes, books)
    return {"items": [_sugg_dict(r, books, costs, st) for r in part], "total": len(out), "page": page, "pageSize": PAGE_SIZE,
            "indirim": median_discount(engine, st), "meta": meta_get(engine, "suggestions")}


def adopt_suggestion(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, user: str, sid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(SUGG).where(SUGG.c.id == sid)).first()
    if r is None:
        raise SetsError("Öneri bulunamadı.", 404)
    if r.durum == "benimsendi" and r.set_id:
        raise SetsError(f"Bu öneri {r.set_id} taslağına alınmış.", 409)
    tur = {"birlikte": "tematik", "yazar": "yazar", "seri": "seri"}.get(r.tur, "tematik")
    body = {"ad": r.ad_llm or r.ad, "tur": tur, "bilesenler": [{"stok": x, "adet": 1} for x in _j(r.kodlar_json, [])],
            "setFiyati": r.onerilen_fiyat, "gerekce": "\n".join(x for x in (r.gerekce, r.aciklama_llm) if x),
            "sezonId": r.sezon_id, "sezonAdi": r.sezon_adi}
    s = create_set(engine, st, tenant, user, body, kaynak="oneri", oneri_id=sid)
    with engine.begin() as c:
        c.execute(SUGG.update().where(SUGG.c.id == sid).values(durum="benimsendi", set_id=s["id"], karar_by=user, updated_at=_now()))
    return s


def dismiss_suggestion(engine: sa.engine.Engine, user: str, sid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(SUGG).where(SUGG.c.id == sid)).first()
        if r is None:
            raise SetsError("Öneri bulunamadı.", 404)
        c.execute(SUGG.update().where(SUGG.c.id == sid).values(durum="reddedildi", karar_by=user, updated_at=_now()))
    return {"id": sid, "ad": r.ad_llm or r.ad}


# ------------------------------------------------------------------------------------------ kurumsal hediye


def gift_options(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, qty: int, budget: float,
                 tiers: list[tuple[int, float]]) -> list[dict[str, Any]]:
    """Kişi başı bütçeye sığan ve stoğu kişi sayısına yeten seçenekler (kod üretir): set, kitap paketi, tek kitap."""
    disc = tier_for(qty, tiers)
    promo = st["promoPrefix"]
    with engine.connect() as c:
        books = [b for b in c.execute(sa.select(BOOKS).where(BOOKS.c.crm_tip == 1, BOOKS.c.in_logo.is_(True), BOOKS.c.stok >= qty)).all()
                 if not b.stok_kodu.startswith(promo) and list_price(b, st)]
        sets_ = c.execute(sa.select(SETS).where(SETS.c.tenant_id == tenant, SETS.c.durum == "satista", SETS.c.stok_kodu.isnot(None),
                                                SETS.c.set_fiyati > 0)).all()
    set_books = books_by_code(engine, [s.stok_kodu for s in sets_])
    costs = costs_for(engine, st, [b.stok_kodu for b in books])

    def option(tur: str, name: str, lines: list[dict[str, Any]], unit_list: float, set_row: Any = None) -> dict[str, Any]:
        net = round(unit_list * (1 - disc), 2)
        cost_known = all(l.get("maliyet") is not None for l in lines)
        unit_cost = sum(l["maliyet"] * l["adet"] for l in lines) if cost_known else None
        vat_net = sum((net * (l["liste"] * l["adet"] / unit_list)) / (1 + (l.get("kdv") or 0) / 100) for l in lines) if unit_list else net
        return {"tur": tur, "ad": name, "kalemler": lines, "birimListe": round(unit_list, 2), "indirim": disc, "birimNet": net,
                "toplamNet": round(net * qty, 2), "stokYeterli": True, "butceFarki": round(budget - net, 2),
                "birimMaliyet": _r2(unit_cost), "marj": _r2((vat_net - unit_cost) * qty) if unit_cost is not None else None,
                "marjOrani": ((vat_net - unit_cost) / vat_net) if (unit_cost is not None and vat_net) else None,
                "setId": set_row.id if set_row is not None else None}

    sets_opts, pack_opts, single_opts = [], [], []
    for s in sets_:
        b = set_books.get(s.stok_kodu)
        if b is None or (b.stok or 0) < qty or s.set_fiyati * (1 - disc) > budget:
            continue
        line = {"stok": s.stok_kodu, "ad": s.ad, "adet": 1, "liste": s.set_fiyati, "kdv": b.kdv,
                "maliyet": (s.maliyet_toplami + (s.ambalaj_birim_maliyet or 0)) if s.maliyet_toplami is not None else None}
        sets_opts.append(option("set", s.ad, [line], s.set_fiyati, s))
    ranked = sorted(books, key=lambda b: -(b.son12_adet or 0))
    for b in ranked:
        lp = list_price(b, st)
        if lp * (1 - disc) <= budget:
            single_opts.append(option("kitap", b.ad or b.stok_kodu, [{"stok": b.stok_kodu, "ad": b.ad, "yazar": b.yazar, "adet": 1, "liste": lp,
                                                                  "kdv": b.kdv, "maliyet": (costs.get(b.stok_kodu) or {}).get("birim")}], lp))
    used: set[str] = set()
    for _ in range(st["giftOptions"]):
        lines, total = [], 0.0
        for b in ranked:
            if b.stok_kodu in used:
                continue
            lp = list_price(b, st)
            if (total + lp) * (1 - disc) <= budget:
                lines.append({"stok": b.stok_kodu, "ad": b.ad, "yazar": b.yazar, "adet": 1, "liste": lp, "kdv": b.kdv,
                              "maliyet": (costs.get(b.stok_kodu) or {}).get("birim")})
                total += lp
        if len(lines) < 2:
            break
        used |= {l["stok"] for l in lines}
        pack_opts.append(option("paket", f"{len(lines)} kitaplık paket", lines, total))
    for group in (sets_opts, pack_opts, single_opts):
        group.sort(key=lambda o: o["butceFarki"])
    # Önce en çok iki set ve iki paket (bütçeye en yakın), kalan yer bütçeye en yakın diğer seçeneklerle dolar.
    k = st["giftOptions"]
    picked = (sets_opts[:2] + pack_opts[:2])[:k]
    for o in sorted(sets_opts[2:] + pack_opts[2:] + single_opts, key=lambda o: o["butceFarki"]):
        if len(picked) >= k:
            break
        picked.append(o)
    for n, o in enumerate(picked, 1):
        o["no"] = n
    return picked


def _offer_dict(r: Any) -> dict[str, Any]:
    return {"id": r.id, "firmaId": r.firma_id, "firmaAdi": r.firma_adi, "firmaKodu": r.firma_kodu, "adet": r.adet,
            "kisiBasiButce": r.kisi_basi_butce, "secenekler": _j(r.secenekler_json, []), "secili": _j(r.secili_json, []),
            "kademeler": [{"adet": a, "indirim": p} for a, p in _j(r.kademeler_json, [])], "mektup": r.mektup,
            "gecerlilik": r.gecerlilik, "durum": r.durum, "durumAdi": OFFER_STATUS.get(r.durum, r.durum), "sezon": r.sezon,
            "notlar": r.notlar, "hazirlayan": r.hazirlayan, "gonderen": r.gonderen, "onaylayan": r.onaylayan,
            "kararNotu": r.karar_notu, "m32FirsatId": r.m32_firsat_id, "createdAt": _iso(r.created_at), "updatedAt": _iso(r.updated_at),
            "submittedAt": _iso(r.submitted_at), "decidedAt": _iso(r.decided_at)}


def _offer_row(c: Any, tenant: str, oid: str) -> Any:
    r = c.execute(sa.select(OFFERS).where(OFFERS.c.tenant_id == tenant, OFFERS.c.id == oid)).first()
    if r is None:
        raise SetsError("Teklif bulunamadı.", 404)
    return r


def list_offers(engine: sa.engine.Engine, tenant: str, *, durum: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(OFFERS).where(OFFERS.c.tenant_id == tenant).order_by(OFFERS.c.created_at.desc())).all()
    f = fold(q)
    counts = {k: sum(1 for r in rows if r.durum == k) for k in OFFER_STATUS}
    out = [_offer_dict(r) for r in rows if (not durum or r.durum == durum) and (not f or f in fold(r.firma_adi) or f in fold(r.id))]
    ref = today()
    for o in out:
        o["gunKaldi"] = (date.fromisoformat(o["gecerlilik"]) - ref).days if o["gecerlilik"] else None
        o["secenekler"] = [{k: v for k, v in s.items() if k != "kalemler"} for s in o["secenekler"]]
    page = max(0, page)
    return {"items": out[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], "total": len(out), "page": page, "pageSize": PAGE_SIZE,
            "summary": counts}


def get_offer(engine: sa.engine.Engine, tenant: str, oid: str) -> dict[str, Any]:
    with engine.connect() as c:
        return _offer_dict(_offer_row(c, tenant, oid))


def create_offer(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, user: str, body: dict[str, Any],
                 account: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not account:
        raise SetsError("Firma CRM'de bulunamadı.", 404)
    qty = int(_num(body.get("adet"), "Kişi sayısı", minimum=1, maximum=1_000_000))
    budget = float(_num(body.get("kisiBasiButce"), "Kişi başı bütçe", minimum=0.01))
    tiers = parse_tiers(body["kademeler"]) if body.get("kademeler") else st["giftTiers"]
    opts = gift_options(engine, st, tenant, qty, budget, tiers)
    now = _now()
    with engine.begin() as c:
        oid = _next_id(c, OFFERS, f"KT-{today().year}-")
        c.execute(OFFERS.insert().values(
            id=oid, tenant_id=tenant, firma_id=account["id"], firma_adi=account.get("unvan"), firma_kodu=account.get("kod"),
            adet=qty, kisi_basi_butce=budget, secenekler_json=_dump(opts), secili_json=_dump([o["no"] for o in opts]),
            kademeler_json=_dump(tiers), gecerlilik=(today() + timedelta(days=st["offerValidDays"])).isoformat(), durum="taslak",
            sezon=_text(body.get("sezon"), 200), notlar=_longtext(body.get("notlar"), 4000), hazirlayan=user,
            m32_firsat_id=_text(body.get("m32FirsatId"), 60), created_at=now, updated_at=now))
    return get_offer(engine, tenant, oid)


def update_offer(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, user: str, oid: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.connect() as c:
        r = _offer_row(c, tenant, oid)
    vals: dict[str, Any] = {}
    content = {"adet", "kisiBasiButce", "kademeler", "secili", "mektup", "gecerlilik", "yenidenHesapla"}
    if content & set(body) and r.durum != "taslak":
        raise SetsError("Yalnız taslak teklifin içeriği değişir; önce onaydan çekin.", 409)
    qty = int(_num(body["adet"], "Kişi sayısı", minimum=1, maximum=1_000_000)) if "adet" in body else r.adet
    budget = float(_num(body["kisiBasiButce"], "Kişi başı bütçe", minimum=0.01)) if "kisiBasiButce" in body else r.kisi_basi_butce
    tiers = parse_tiers(body["kademeler"]) if "kademeler" in body else [tuple(x) for x in _j(r.kademeler_json, [])]
    if {"adet", "kisiBasiButce", "kademeler", "yenidenHesapla"} & set(body):
        opts = gift_options(engine, st, tenant, qty, budget, tiers)
        vals.update(adet=qty, kisi_basi_butce=budget, kademeler_json=_dump(tiers), secenekler_json=_dump(opts),
                    secili_json=_dump([o["no"] for o in opts]))
    if "secili" in body:
        nos = {o["no"] for o in _j(vals.get("secenekler_json") or r.secenekler_json, [])}
        try:
            pick = [int(x) for x in body["secili"] or [] if int(x) in nos]
        except (TypeError, ValueError):
            raise SetsError("Seçenek numarası sayı olmalı.") from None
        if not pick:
            raise SetsError("En az bir seçenek seçili olmalı.")
        vals["secili_json"] = _dump(pick)
    if "mektup" in body:
        vals["mektup"] = _longtext(body["mektup"], 8000)
    if "gecerlilik" in body:
        try:
            vals["gecerlilik"] = date.fromisoformat(str(body["gecerlilik"])[:10]).isoformat() if body["gecerlilik"] else None
        except ValueError:
            raise SetsError("Geçerlilik YYYY-AA-GG biçiminde olmalı.") from None
    if "notlar" in body:
        vals["notlar"] = _longtext(body["notlar"], 4000)
    if "sezon" in body:
        vals["sezon"] = _text(body["sezon"], 200)
    if "m32FirsatId" in body:
        vals["m32_firsat_id"] = _text(body["m32FirsatId"], 60)
    if "durum" in body and body["durum"] != r.durum:
        allowed = {"onaylandi": ("gonderildi",), "gonderildi": ("kazanildi", "kaybedildi")}
        if body["durum"] not in allowed.get(r.durum, ()):
            raise SetsError(f"«{OFFER_STATUS.get(r.durum)}» durumundan «{OFFER_STATUS.get(body['durum'], body['durum'])}» durumuna geçilemez.", 409)
        vals["durum"] = body["durum"]
    if vals:
        vals["updated_at"] = _now()
        with engine.begin() as c:
            c.execute(OFFERS.update().where(OFFERS.c.id == oid).values(**vals))
    return get_offer(engine, tenant, oid)


def submit_offer(engine: sa.engine.Engine, tenant: str, user: str, oid: str, withdraw: bool = False) -> dict[str, Any]:
    with engine.connect() as c:
        r = _offer_row(c, tenant, oid)
    if withdraw:
        if r.durum != "onayda":
            raise SetsError("Teklif onay beklemiyor.", 409)
        vals = {"durum": "taslak"}
    else:
        if r.durum != "taslak":
            raise SetsError("Yalnız taslak teklif onaya gönderilir.", 409)
        if not _j(r.secili_json, []):
            raise SetsError("Seçenek seçilmeden onaya gönderilemez.")
        vals = {"durum": "onayda", "gonderen": user, "submitted_at": _now(), "karar_notu": None}
    with engine.begin() as c:
        c.execute(OFFERS.update().where(OFFERS.c.id == oid).values(**vals, updated_at=_now()))
    return get_offer(engine, tenant, oid)


def decide_offer(engine: sa.engine.Engine, tenant: str, user: str, oid: str, approve: bool, note: Any) -> dict[str, Any]:
    with engine.connect() as c:
        r = _offer_row(c, tenant, oid)
    if r.durum != "onayda":
        raise SetsError("Teklif onay beklemiyor.", 409)
    if (r.gonderen or "").lower() == (user or "").lower():
        raise SetsError("Onaya gönderen kişi teklifi onaylayamaz; onayı başka bir yetkili verir.", 409)
    text = _longtext(note, 2000)
    if not approve and not text:
        raise SetsError("Geri gönderme için gerekçe yazın.")
    with engine.begin() as c:
        c.execute(OFFERS.update().where(OFFERS.c.id == oid).values(durum="onaylandi" if approve else "taslak", onaylayan=user,
                                                                   decided_at=_now(), karar_notu=text, updated_at=_now()))
    return get_offer(engine, tenant, oid)


def handoff(engine: sa.engine.Engine, tenant: str, oid: str) -> dict[str, Any]:
    """M32 kurumsal teklif akışına bağlantı noktası: seçili seçeneklerin kalemleri M32 teklif satırı biçiminde."""
    o = get_offer(engine, tenant, oid)
    lines = []
    for s in o["secenekler"]:
        if s["no"] not in o["secili"]:
            continue
        for k in s["kalemler"]:
            lines.append({"secenek": s["no"], "stok": k["stok"], "ad": k.get("ad"), "adet": k["adet"] * o["adet"],
                          "listeFiyat": k["liste"], "indirim": s["indirim"]})
    return {"kaynak": "M53", "teklifId": o["id"], "kurumCrmId": o["firmaId"], "kurum": o["firmaAdi"], "kisiSayisi": o["adet"],
            "kisiBasiButce": o["kisiBasiButce"], "gecerlilik": o["gecerlilik"], "m32FirsatId": o["m32FirsatId"], "satirlar": lines}


# ------------------------------------------------------------------------------------------ promosyon ürünleri


def list_promo(engine: sa.engine.Engine, *, stok: Optional[str] = None, tur: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(PROMO).order_by(PROMO.c.son12_adet.desc(), PROMO.c.stok_kodu)).all()
    f = fold(q)
    allrows = [{"stok": r.stok_kodu, "ad": r.ad, "tur": r.tur, "turAdi": PROMO_TYPES.get(r.tur, r.tur), "crmTip": r.crm_tip,
                "promosyonTipi": r.promosyon_tipi, "stokAdet": r.stok, "son12Adet": r.son12_adet, "son12Ciro": r.son12_ciro,
                "bedelsizCikis": r.bedelsiz_cikis} for r in rows]
    summary = {"toplam": len(allrows), "stokYok": sum(1 for r in allrows if (r["stokAdet"] or 0) <= 0),
               **{k: sum(1 for r in allrows if r["tur"] == k) for k in PROMO_TYPES},
               "son12Ciro": round(sum(r["son12Ciro"] or 0 for r in allrows if r["tur"] == "157"), 2)}
    out = [r for r in allrows
           if (stok is None or stok == "" or (stok == "0" and (r["stokAdet"] or 0) <= 0) or (stok == "1" and (r["stokAdet"] or 0) > 0))
           and (not tur or r["tur"] == tur) and (not f or f in fold(r["ad"]) or f in fold(r["stok"]))]
    page = max(0, page)
    return {"items": out[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], "total": len(out), "page": page, "pageSize": PAGE_SIZE,
            "summary": summary, "window": window12(data_end(engine))}


# ------------------------------------------------------------------------------------------ uyarılar


def due_alerts(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, ref: Optional[date] = None) -> list[dict[str, Any]]:
    """Kurallı uyarılar (model yok): özel gün geri sayımı, bileşen stoğu, marj alt sınırı, promosyon stoğu, teklif geçerliliği."""
    ref = ref or today()
    out: list[dict[str, Any]] = []
    days = {s["id"]: s for s in seasons(engine, ref)}
    with engine.connect() as c:
        rows = c.execute(sa.select(SETS).where(SETS.c.tenant_id == tenant)).all()
        items = _items_of(c, [r.id for r in rows])
        offers = c.execute(sa.select(OFFERS).where(OFFERS.c.tenant_id == tenant, OFFERS.c.durum.in_(("taslak", "onayda", "onaylandi", "gonderildi")))).all()
        promo0 = c.execute(sa.select(sa.func.count()).select_from(PROMO).where(sa.or_(PROMO.c.stok <= 0, PROMO.c.stok.is_(None)))).scalar() or 0
    lead = st["seasonLeadWeeks"] * 7
    for r in rows:
        s = days.get(r.sezon_id or "")
        if s and s["gunKaldi"] is not None and 0 <= s["gunKaldi"] <= lead and r.durum in ("oneri", "taslak", "onayda", "kart-bekliyor"):
            out.append({"tur": "sezon", "set": r.id, "mesaj": f"«{r.ad}»: {s['ad']} {s['gunKaldi']} gün sonra; set kartı CRM'de henüz açılmadı ({STATUSES[r.durum]})."})
        if r.durum in ("kart-bekliyor", "satista") and r.hedef_adet:
            short = [i for i in items.get(r.id, []) if i.stok is not None and i.stok < (r.hedef_adet or 0) * i.adet]
            if short:
                names = ", ".join(i.ad or i.stok_kodu for i in short)
                out.append({"tur": "stok", "set": r.id,
                            "mesaj": f"«{r.ad}»: {len(short)} bileşenin stoğu {_tr(r.hedef_adet, 0)} set için yetmiyor ({names})."})
        if r.durum == "onayda" and r.marj_orani is not None and st["marginMinPct"] is not None and r.marj_orani < st["marginMinPct"] / 100:
            out.append({"tur": "marj", "set": r.id, "mesaj": f"«{r.ad}» onay bekliyor ve marjı alt sınırın altında (%{r.marj_orani * 100:.1f} < %{st['marginMinPct']:g})."})
    for o in offers:
        if o.gecerlilik:
            left = (date.fromisoformat(o.gecerlilik) - ref).days
            if 0 <= left <= 7:
                out.append({"tur": "teklif", "teklif": o.id, "mesaj": f"{o.id} ({o.firma_adi}) teklifinin geçerliliği {left} gün sonra bitiyor; hazırlayan {o.hazirlayan}."})
    if promo0:
        out.append({"tur": "promosyon", "mesaj": f"{promo0} promosyon ürününde Logo stoğu yok."})
    return out


# ------------------------------------------------------------------------------------------ ZEKİ AI

NAME_PROMPT = """Bir yayınevinin pazarlama ekibi için kitap seti önerisine kısa bir ad ve bir cümlelik tanıtım yaz.
Türkçe; ad en çok altı kelime. KESİNLİKLE rakam, fiyat, adet ya da tarih yazma. Listede olmayan bilgi uydurma.
Biçim tam olarak şöyle olsun:
Ad: <set adı>
Tanıtım: <tek cümle>
Kitaplar:
{books}
Neden bir arada: {reason}"""

SEASON_PROMPT = """Bir yayınevi aşağıdaki kitap setini hangi özel gün ya da dönem için hediye seti olarak öne çıkarmalı?
Uygun olan yoksa «Hiçbiri» seç.
Kitaplar:
{books}"""

TEXT_PROMPTS = {
    "tanitim": """Aşağıdaki kitap seti için e-ticaret ürün açıklaması taslağı yaz (SEO önerisi olarak incelenecek).
Türkçe, 2 kısa paragraf ve sonunda 3 maddelik «Sette neler var» listesi. KESİNLİKLE fiyat, indirim, adet ya da tarih yazma.
Kitap adlarını ve yazarlarını olduğu gibi kullan; kitap hakkında verilmeyen bilgi uydurma.
Set: {name}
Kitaplar:
{books}
Açıklama:""",
    "brief": """Aşağıdaki kitap seti için ambalaj ve sunum brief'i taslağı yaz (tasarım ve üretim ekibine).
Türkçe, maddeler hâlinde: hedef okur, ton ve renk önerisi, ambalaj türünün kullanımı, kutu/kuşak üzerindeki metin önerisi,
dikkat edilecekler. KESİNLİKLE fiyat, maliyet, adet ya da tarih yazma.
Set: {name}
Ambalaj: {pack}
Özel gün: {season}
Kitaplar:
{books}
Brief:""",
}

LETTER_PROMPT = """Bir yayınevinin kurumsal satış temsilcisi adına, kuruma gönderilecek kısa bir kurumsal hediye teklif mektubu
taslağı yaz. Türkçe, resmî ama sıcak; 3 kısa paragraf. Hitapla başla, imza satırı yazma.
KESİNLİKLE rakam, fiyat, tutar, indirim oranı, kişi sayısı ya da tarih yazma: teklif tablosu belgede ayrıca yer alıyor.
Kitap ve set adlarını olduğu gibi kullan; listede olmayan bilgi uydurma.
Yayınevi: {company}
Kurum: {institution}
Vesile: {season}
Seçenekler:
{options}
Mektup:"""

NONE_SEASON = "Hiçbiri"


def _no_digits(text: str) -> str:
    """Model rakam yazdıysa o satırlar atılır: tutar ve adet yalnız tablodan gelir."""
    return re.sub(r"[^\n]*\d[^\n]*\n?", "", text or "").strip()


def _books_text(codes: list[str], books: dict[str, Any]) -> str:
    out = []
    for c in codes:
        b = books.get(c)
        if b is None:
            continue
        line = f"- {b.ad or c}" + (f" ({b.yazar})" if b.yazar else "")
        if b.turler or b.yaslar:
            line += f" — {', '.join(x for x in (b.turler, b.yaslar) if x)}"
        if b.spot or b.ozet:
            line += f": {(b.spot or b.ozet)[:220]}"
        out.append(line)
    return "\n".join(out) or "-"


def parse_name(answer: str) -> tuple[Optional[str], Optional[str]]:
    name = re.search(r"^\s*Ad\s*:\s*(.+)$", answer or "", re.M | re.I)
    pitch = re.search(r"^\s*Tan[ıi]t[ıi]m\s*:\s*(.+)$", answer or "", re.M | re.I)
    n = _text(name.group(1).strip(" «»\"'*"), 120) if name else None
    p = _text(pitch.group(1), 400) if pitch else None
    if n and re.search(r"\d", n):
        n = None
    if p and re.search(r"\d", p):
        p = None
    return n, p


def choose_season(llm: Any, codes: list[str], books: dict[str, Any], labels: list[str], st: dict[str, Any]) -> dict[str, Any]:
    prompt = SEASON_PROMPT.format(books=_books_text(codes, books))
    choices = list(dict.fromkeys(labels)) + [NONE_SEASON]
    if hasattr(llm, "choose"):
        r = llm.choose(prompt, choices)
        ok = bool(r.choice and r.choice != NONE_SEASON and r.confident(st["llmMinProb"], min_margin=st["llmMinMargin"]))
        return {"secim": r.choice if ok else None, "olasilik": r.probability, "yontem": r.method}
    return {"secim": None, "olasilik": None, "yontem": "none"}


def run_model_tasks(engine: sa.engine.Engine, st: dict[str, Any], llm: Any, budget_sec: int) -> dict[str, Any]:
    """Gece: öneriye ad/tanıtım ve özel gün (skor sırasıyla). Süre dolunca kalan sonraki geceye kalır."""
    out: dict[str, Any] = {"ad": 0, "sezon": 0, "eminDegil": 0}
    if llm is None or budget_sec <= 0:
        out["atlandi"] = "model tanımlı değil" if llm is None else "süre 0"
        return out
    t0 = time.monotonic()
    ss = [s for s in seasons(engine) if s.get("gunKaldi") is not None and s["gunKaldi"] <= 366]
    labels = [s["ad"] for s in ss]
    by_label = {s["ad"]: s for s in ss}
    with engine.connect() as c:
        rows = c.execute(sa.select(SUGG).where(SUGG.c.durum == "yeni", SUGG.c.llm_at.is_(None)).order_by(SUGG.c.skor.desc())).all()
    for r in rows:
        if time.monotonic() - t0 >= budget_sec:
            break
        codes = _j(r.kodlar_json, [])
        books = books_by_code(engine, codes)
        try:
            ans = llm.chat([{"role": "user", "content": NAME_PROMPT.format(books=_books_text(codes, books), reason=r.gerekce or "-")}],
                           max_tokens=200, temperature=0.3) or ""
            name, pitch = parse_name(ans)
            season = choose_season(llm, codes, books, labels, st) if labels else {"secim": None, "olasilik": None}
        except Exception as e:  # noqa: BLE001 — model düşerse kalan sonraki geceye
            log.warning("sets: öneri adı alınamadı: %s", e)
            break
        hit = by_label.get(season["secim"] or "")
        with engine.begin() as c:
            c.execute(SUGG.update().where(SUGG.c.id == r.id).values(
                ad_llm=name, aciklama_llm=pitch, sezon_id=hit["id"] if hit else None, sezon_adi=hit["ad"] if hit else None,
                sezon_olasilik=season["olasilik"] if hit else None, llm_at=_now()))
        out["ad"] += 1 if name else 0
        out["sezon"] += 1 if hit else 0
        out["eminDegil"] += 0 if hit else 1
    with engine.connect() as c:
        out["kalan"] = c.execute(sa.select(sa.func.count()).select_from(SUGG).where(SUGG.c.durum == "yeni", SUGG.c.llm_at.is_(None))).scalar() or 0
    return out


def draft_text(engine: sa.engine.Engine, llm: Any, tenant: str, set_id: str, kind: str) -> str:
    if kind not in TEXT_PROMPTS:
        raise SetsError("Metin türü geçersiz.")
    if llm is None:
        raise SetsError("ZEKİ AI bu kurulumda tanımlı değil.", 503)
    s = get_set(engine, tenant, set_id)
    codes = [i["stok"] for i in s["bilesenler"] or []]
    if not codes:
        raise SetsError("Sette bileşen yok.")
    prompt = TEXT_PROMPTS[kind].format(name=s["ad"], books=_books_text(codes, books_by_code(engine, codes)),
                                       pack=s["ambalajTuru"] or "henüz seçilmedi", season=s["sezonAdi"] or "-")
    text = _no_digits((llm.chat([{"role": "user", "content": prompt}], max_tokens=900, temperature=0.4) or "").strip())
    if not text:
        raise SetsError("ZEKİ AI metin üretemedi; yeniden deneyin.", 503)
    with engine.begin() as c:
        c.execute(SETS.update().where(SETS.c.id == set_id).values(**{("tanitim" if kind == "tanitim" else "brief"): text[:8000], "updated_at": _now()}))
    return text[:8000]


def draft_letter(engine: sa.engine.Engine, llm: Any, st: dict[str, Any], tenant: str, oid: str) -> str:
    if llm is None:
        raise SetsError("ZEKİ AI bu kurulumda tanımlı değil.", 503)
    o = get_offer(engine, tenant, oid)
    if o["durum"] != "taslak":
        raise SetsError("Mektup yalnız taslak teklifte yazılır.", 409)
    opts = [s for s in o["secenekler"] if s["no"] in o["secili"]]
    lines = "\n".join(f"- {s['ad']}: " + ", ".join((k.get("ad") or k["stok"]) + (f" ({k['yazar']})" if k.get("yazar") else "") for k in s["kalemler"])
                      for s in opts) or "-"
    prompt = LETTER_PROMPT.format(company=st["company"], institution=o["firmaAdi"] or "Kurum", season=o["sezon"] or "yıl sonu hediyesi",
                                  options=lines)
    text = _no_digits((llm.chat([{"role": "user", "content": prompt}], max_tokens=700, temperature=0.3) or "").strip())[:8000]
    if not text:
        raise SetsError("ZEKİ AI mektup yazamadı; yeniden deneyin.", 503)
    with engine.begin() as c:
        c.execute(OFFERS.update().where(OFFERS.c.id == oid).values(mektup=text, updated_at=_now()))
    return text


# ------------------------------------------------------------------------------------------ okuma (Logo + CRM → köprü)


class Refresher:
    """Logo/CRM okumasını yapar; aynı anda tek okuma."""

    def __init__(self, engine_fn: Callable[[], sa.engine.Engine], tenant_fn: Callable[[], str], logo_file: Callable[[], str],
                 crm_file: Callable[[], str], schema_fn: Callable[[], str], settings_fn: Callable[[], dict[str, Any]]):
        self._engine, self._tenant, self._logo, self._crm, self._schema, self._settings = (
            engine_fn, tenant_fn, logo_file, crm_file, schema_fn, settings_fn)
        self._thread: Optional[threading.Thread] = None
        self._guard = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "step": None, "startedAt": None, "error": None}

    def status(self) -> dict[str, Any]:
        engine = self._engine()
        ensure(engine)
        return {**self.state, "last": meta_get(engine, "refresh"), "dataEnd": meta_get(engine, "data_end").get("date"),
                "basket": meta_get(engine, "basket")}

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive()) or bool(self.state.get("running"))

    def start(self, *, basket: bool = False) -> bool:
        with self._guard:
            if self.running():
                return False
            self.state.update(running=True, step="Başlıyor", startedAt=time.time(), error=None)
            self._thread = threading.Thread(target=lambda: self.run(basket=basket), daemon=True, name="sets-refresh")
            self._thread.start()
            return True

    def _step(self, name: str) -> None:
        self.state["step"] = name

    def run(self, *, basket: Optional[bool] = None, history: Optional[bool] = None) -> dict[str, Any]:
        engine, tenant, st = self._engine(), self._tenant(), self._settings()
        ensure(engine)
        done: dict[str, Any] = {}
        warnings: list[str] = []
        t0 = time.monotonic()
        ref = today()
        try:
            self.state.update(running=True, step="CRM set kartları", error=None)
            schema = self._schema()
            crm = src.runner(self._crm())
            crm_sets = src.read_crm_sets(crm, schema)
            crm_books = src.read_crm_books(crm, schema)
            crm_comp = src.read_crm_components(crm, schema) if st["componentSource"] in ("auto", "crm") else {}
            try:
                meta_set(engine, "packaging", {"items": src.read_crm_packaging(crm, schema)})
                meta_set(engine, "seasons", {"items": src.read_crm_special_days(crm, schema)})
            except src.SourceError as e:
                warnings.append(f"Paketleme/özel gün okunamadı: {e}")
            done.update(crmSet=len(crm_sets), crmKitap=len(crm_books), crmSetIslemi=len(crm_comp))

            self._step("Logo dönemleri ve malzeme kartları")
            logo = src.runner(self._logo())
            firms = src.firms_by_year(logo)
            end = src.read_data_end(logo, firms) or ref
            meta_set(engine, "data_end", {"date": end.isoformat()})
            items = src.read_items(logo, firms)
            stock = src.read_stock(logo, firms)
            prices = src.read_prices(logo, firms, ref)
            costs = src.read_last_costs(logo, firms) if st["costSource"] == "logo" else {}

            set_codes = [s["stok"] for s in crm_sets if s.get("stok")]
            with engine.connect() as c:
                set_codes += [r[0] for r in c.execute(sa.select(SETS.c.stok_kodu).where(SETS.c.stok_kodu.isnot(None))).all()]
            bom: dict[str, list[dict[str, Any]]] = {}
            if st["componentSource"] in ("auto", "logo") and set_codes:
                self._step("Logo reçeteleri")
                need = [c for c in set_codes if st["componentSource"] == "logo" or c not in crm_comp]
                if need:
                    try:
                        bom = src.read_bom(logo, firms, need, st["bomLinetypes"])
                    except src.SourceError as e:
                        warnings.append(f"Logo reçetesi okunamadı: {e}")
            done["logoRecete"] = len(bom)

            self._step("Logo satışı")
            years = sorted({end.year, end.year - 1})
            hist = history if history is not None else (ref.weekday() == 6 or not meta_get(engine, "history").get("years"))
            if hist:
                years = sorted(set(years) | {end.year - k for k in range(st["salesYears"])})
            years = [y for y in years if y in firms]
            sales: list[dict[str, Any]] = []
            for y in years:
                self._step(f"Logo satışı {y}")
                sales += src.read_sales(logo, firms, y, st["salesLinetypes"])
            if hist:
                meta_set(engine, "history", {"years": years})
            done["satisSatiri"] = len(sales)

            self._step("Köprü tablolarına yazılıyor")
            a12, b12 = window12(end)
            s12: dict[str, dict[str, float]] = {}
            for s in sales:
                ym = f"{s['yil']:04d}-{s['ay']:02d}"
                if a12 <= ym <= b12:
                    cur = s12.setdefault(s["stok"], {"adet": 0.0, "ciro": 0.0})
                    cur["adet"] += s["adet"]
                    cur["ciro"] += s["ciro"]
            self._write_books(engine, items, stock, prices, costs, crm_books, s12)
            comp_map = self._merge_sets(engine, tenant, st, crm_sets, crm_comp, bom)
            component_codes = {c for cs in comp_map.values() for c in cs}
            promo_codes = {c for c in items if c.startswith(st["promoPrefix"])} | {c for c, b in crm_books.items() if b.get("tip") in (2, 7)}
            all_set_codes = set(set_codes) | {r for r in comp_map}
            self._write_sales(engine, sales, years, all_set_codes, component_codes, promo_codes, end)
            done["promosyon"] = self._write_promo(engine, st, items, stock, crm_books, s12)
            done["yenidenHesap"] = recalc(engine, st)
            linked = auto_link(engine, tenant, crm_comp, crm_sets)
            done["eslesen"] = len(linked)

            want_basket = basket if basket is not None else (ref.weekday() == 6 or not meta_get(engine, "basket").get("asof"))
            if want_basket:
                self._step("B2C birlikte alım çiftleri")
                try:
                    tb = time.monotonic()
                    m = end.year * 12 + end.month - 1 - st["basketMonths"]
                    since = date(m // 12, m % 12 + 1, 1)          # veri bitiş ayından N ay önceki ayın ilk günü
                    pairs, counts, total = src.read_basket(crm, schema, since, st["b2cTypes"], st["b2cPrefix"], st["basketMinOrders"])
                    self._write_pairs(engine, pairs, counts, total, f"{since.isoformat()} – {end.isoformat()}")
                    meta_set(engine, "basket", {"asof": _now().isoformat(), "cift": len(pairs), "siparis": total,
                                                "enAz": st["basketMinOrders"], "donem": [since.isoformat(), end.isoformat()],
                                                "sn": round(time.monotonic() - tb, 1)})
                    done["sepetCifti"] = len(pairs)
                except src.SourceError as e:
                    warnings.append(f"Birlikte alım okunamadı: {e}")

            self._step("Set önerileri")
            done["oneri"] = build_suggestions(engine, st)
            meta_set(engine, "suggestions", {"asof": _now().isoformat(), **done["oneri"]})
            alerts = due_alerts(engine, st, tenant, ref)
            meta_set(engine, "alerts", {"items": alerts})
            done["uyari"] = len(alerts)
            meta_set(engine, "refresh", {"ok": True, "done": done, "warnings": warnings, "sn": round(time.monotonic() - t0, 1)})
            self.state.update(running=False, step=None, error=None, finishedAt=time.time())
            return {"ok": True, "done": done, "warnings": warnings, "dataEnd": end.isoformat(), "alerts": alerts}
        except Exception as e:  # noqa: BLE001 — eski veriler kalır, hata ekranda
            log.warning("sets refresh failed: %s", e)
            msg = str(e) if isinstance(e, (src.SourceError, SetsError)) else f"Okuma hata verdi: {str(e)[:200]}"
            meta_set(engine, "refresh", {"ok": False, "error": msg, "done": done, "warnings": warnings})
            self.state.update(running=False, step=None, error=msg, finishedAt=time.time())
            return {"ok": False, "error": msg, "done": done}

    # -------------------------------------------------------------- yazma parçaları

    @staticmethod
    def _write_books(engine: sa.engine.Engine, items: dict[str, dict[str, Any]], stock: dict[str, float],
                     prices: dict[str, dict[str, Any]], costs: dict[str, dict[str, Any]], crm_books: dict[str, dict[str, Any]],
                     s12: dict[str, dict[str, float]]) -> None:
        rows = []
        for code in sorted(set(items) | set(crm_books)):
            it, b, p, cost, s = items.get(code) or {}, crm_books.get(code) or {}, prices.get(code) or {}, costs.get(code) or {}, s12.get(code) or {}
            rows.append({"stok_kodu": code[:60], "ad": (b.get("ad") or it.get("ad") or "")[:400] or None, "crm_id": b.get("id"),
                         "crm_tip": b.get("tip"), "yazar": b.get("yazar"), "dizi": b.get("dizi"), "turler": b.get("turler"),
                         "yaslar": b.get("yaslar"), "hedef": b.get("hedef"), "yas_min": b.get("yasMin"), "yas_max": b.get("yasMax"),
                         "promosyon_tipi": b.get("promosyonTipi"), "ozet": b.get("ozet"), "spot": b.get("spot"),
                         "liste_fiyat": b.get("fiyat"), "logo_fiyat": p.get("fiyat"), "logo_fiyat_kdv_dahil": p.get("kdvDahil"),
                         "kdv": it.get("kdv"), "kart": it.get("kart"), "stok": float(stock.get(code, 0.0)),
                         "son12_adet": round(float(s.get("adet") or 0.0), 4), "son12_ciro": round(float(s.get("ciro") or 0.0), 2),
                         "maliyet_logo": cost.get("birim"), "maliyet_logo_tarih": cost.get("tarih"),
                         "in_logo": code in items, "in_crm": code in crm_books})
        with engine.begin() as c:
            c.execute(BOOKS.delete())
            for i in range(0, len(rows), 5000):
                c.execute(BOOKS.insert(), rows[i:i + 5000])

    @staticmethod
    def _merge_sets(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], crm_sets: list[dict[str, Any]],
                    crm_comp: dict[str, dict[str, Any]], bom: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
        """CRM set kartları → `semantic_mkt_sets` (kaynak=crm). Eşlenmiş portal seti aynı kodla ikinci kez açılmaz. Durumu
        kullanıcı değiştirdiyse (kapanacak/kapandı) korunur; CRM'de etkin olmayan set «kapandı» olur. Dönen: set kodu → bileşenler."""
        now = _now()
        comp_map: dict[str, list[str]] = {}
        with engine.connect() as c:
            by_code = {r.stok_kodu: r for r in c.execute(sa.select(SETS).where(SETS.c.tenant_id == tenant, SETS.c.stok_kodu.isnot(None))).all()}
        seen: set[str] = set()
        for s in crm_sets:
            code = s.get("stok")
            if not code:
                continue
            seen.add(code)
            comp_src, comps = None, []
            if code in crm_comp:
                comp_src, comps = "crm-set-islemi", crm_comp[code]["bilesenler"]
            elif code in bom:
                comp_src, comps = "logo-recete", bom[code]
            crm_json = _dump({k: (v.isoformat() if isinstance(v, date) else v) for k, v in s.items() if k not in ("id", "stok")}
                             | ({"setIslemi": {k: v for k, v in crm_comp[code].items() if k != "bilesenler"}} if code in crm_comp else {}))
            old = by_code.get(code)
            with engine.begin() as c:
                if old is None:
                    sid = _next_id(c, SETS, f"MS-{today().year}-")
                    c.execute(SETS.insert().values(
                        id=sid, tenant_id=tenant, ad=(s.get("ad") or code)[:300], tur="toplama" if "toplama" in fold(s.get("setTipi")) else "tematik",
                        kaynak="crm", crm_kitap_id=s.get("id"), stok_kodu=code, durum="satista", set_fiyati=s.get("fiyat"),
                        kanal_json=_dump([s["kanal"]] if s.get("kanal") else []), bilesen_kaynak=comp_src, crm_json=crm_json,
                        created_at=now, updated_at=now))
                else:
                    sid = old.id
                    vals: dict[str, Any] = {"crm_kitap_id": s.get("id"), "crm_json": crm_json, "updated_at": now}
                    if old.kaynak == "crm":
                        vals.update(ad=(s.get("ad") or code)[:300], set_fiyati=s.get("fiyat"),
                                    kanal_json=_dump([s["kanal"]] if s.get("kanal") else []))
                    if comp_src:
                        vals["bilesen_kaynak"] = comp_src
                    c.execute(SETS.update().where(SETS.c.id == sid).values(**vals))
                if comp_src:
                    _write_items(c, sid, [{"stok": x["stok"], "adet": x["adet"], "kaynak": comp_src} for x in comps if x["adet"] > 0], comp_src)
                    comp_map[code] = [x["stok"] for x in comps]
        with engine.begin() as c:
            for code, r in by_code.items():
                if r.kaynak == "crm" and code not in seen and r.durum != "kapandi":
                    c.execute(SETS.update().where(SETS.c.id == r.id).values(durum="kapandi", updated_at=now))
        with engine.connect() as c:
            for r in c.execute(sa.select(SETS.c.id, SETS.c.stok_kodu).where(SETS.c.tenant_id == tenant, SETS.c.stok_kodu.isnot(None))).all():
                if r.stok_kodu not in comp_map:
                    comp_map[r.stok_kodu] = [i.stok_kodu for i in _items_of(c, [r.id]).get(r.id, [])]
        return comp_map

    @staticmethod
    def _write_sales(engine: sa.engine.Engine, sales: list[dict[str, Any]], years: list[int], set_codes: set[str],
                     component_codes: set[str], promo_codes: set[str], end: date) -> None:
        now = _now()
        rows: dict[tuple[str, str], dict[str, Any]] = {}
        for s in sales:
            code = s["stok"]
            tur = "set" if code in set_codes else "promosyon" if code in promo_codes else "bilesen" if code in component_codes else None
            if tur is None:
                continue
            ym = f"{s['yil']:04d}-{s['ay']:02d}"
            cur = rows.setdefault((code, ym), {"stok_kodu": code, "yil_ay": ym, "tur": tur, "net_adet": 0.0, "net_ciro": 0.0,
                                               "asof": now, "veri_sonu": end.isoformat()})
            cur["net_adet"] += s["adet"]
            cur["net_ciro"] = round(cur["net_ciro"] + s["ciro"], 2)
        with engine.begin() as c:
            for y in years:
                c.execute(SALES.delete().where(SALES.c.yil_ay.like(f"{y:04d}-%")))
            vals = list(rows.values())
            for i in range(0, len(vals), 5000):
                c.execute(SALES.insert(), vals[i:i + 5000])

    @staticmethod
    def _write_promo(engine: sa.engine.Engine, st: dict[str, Any], items: dict[str, dict[str, Any]], stock: dict[str, float],
                     crm_books: dict[str, dict[str, Any]], s12: dict[str, dict[str, float]]) -> int:
        now = _now()
        rows = []
        codes = {c for c in items if c.startswith(st["promoPrefix"])} | {c for c, b in crm_books.items() if b.get("tip") in (2, 7)}
        for code in sorted(codes):
            b = crm_books.get(code) or {}
            tur = "157" if code.startswith(st["promoPrefix"]) else ("crm-promosyon" if b.get("tip") == 2 else "crm-pazarlama-materyali")
            s = s12.get(code) or {}
            rows.append({"stok_kodu": code[:60], "ad": (b.get("ad") or (items.get(code) or {}).get("ad") or "")[:400] or None, "tur": tur,
                         "crm_tip": src.CRM_TIP.get(b.get("tip")), "promosyon_tipi": b.get("promosyonTipi"),
                         "stok": stock.get(code) if code in items else None, "son12_adet": round(float(s.get("adet") or 0.0), 4),
                         "son12_ciro": round(float(s.get("ciro") or 0.0), 2), "bedelsiz_cikis": None, "asof": now})
        with engine.begin() as c:
            c.execute(PROMO.delete())
            for i in range(0, len(rows), 5000):
                c.execute(PROMO.insert(), rows[i:i + 5000])
        return len(rows)

    @staticmethod
    def _write_pairs(engine: sa.engine.Engine, pairs: list[dict[str, Any]], counts: dict[str, int], total: int, donem: str) -> None:
        now = _now()
        rows = []
        for p in pairs:
            ca, cb = counts.get(p["a"]) or 0, counts.get(p["b"]) or 0
            lift = (p["n"] * total / (ca * cb)) if (ca and cb and total) else None
            rows.append({"kod_a": p["a"], "kod_b": p["b"], "siparis_sayisi": p["n"], "lift": round(lift, 4) if lift else None,
                         "donem": donem[:40], "asof": now})
        with engine.begin() as c:
            c.execute(PAIRS.delete())
            for i in range(0, len(rows), 5000):
                c.execute(PAIRS.insert(), rows[i:i + 5000])


def summary(engine: sa.engine.Engine, st: dict[str, Any]) -> dict[str, Any]:
    return {"alerts": meta_get(engine, "alerts").get("items") or [], "packaging": meta_get(engine, "packaging").get("items") or [],
            "seasons": seasons(engine), "discount": median_discount(engine, st), "costProvider": src.cost_provider_ready()}
