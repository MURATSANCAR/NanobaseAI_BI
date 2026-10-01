"""M34 E-ticaret ve platform yönetimi: fark motoru, kayıtlar ve ekran verisi.

Ne yapar (analiz `docs/analiz/kullanici-ihtiyaclari/M34-eticaret-platform.md`, 14. bölüm):

- **Gece fark raporu.** Aynı kitabın CRM kartı, Logo kaydı ve sitedeki (T-soft) ürünü yan yana konur; yedi fark türü
  kurallarla hesaplanır (`DIFF_KINDS`). Model bu hesaba girmez; eşleme EAN-13 (T-soft `Barcode` = CRM `new_ean13`)
  ve stok kodudur (CRM `new_StokKodu` = Logo `ITEMS.CODE`).
- **Fark kaydı ve günlüğü.** Her fark (kitap × tür) tek satırdır; ilk ve son görüldüğü gün, durum (açık / sonra /
  bilinçli / düzeltildi / kapandı), sahip ve not tutulur. Koşulu kalkan fark kendiliğinden kapanır; «düzeltildi»
  denen fark bir sonraki site okumasında hâlâ varsa yeniden açılır; «bilinçli» fark değerler değişince yeniden açılır.
  Her geçiş `semantic_eticaret_diff_log`'a yazılır.
- **Huni** (sitedeki görüntülenme → satış), **eksik ürün kartı** (doluluk), **satışta olmaması gereken** kitaplar (CRM
  yayın durumu, SEO modülünün Haklar ekranıyla aynı kural) ve **pazar yeri carileri** (Logo sell-in) ekranları.
- **Zeki AI** yalnız iki yerde: fiyat farkının olası nedeni (kapalı küme seçim, olasılığıyla; eşik altı «belirsiz»)
  ve ürün kartı metin önerisi (SEO öneri kaydına düşer, insan onaylar). Rakam üretmez.

**Hiçbir sisteme yazılmaz.** T-soft'a, CRM'e, Logo'ya ve pazar yerlerine gönderim yok; ekran «bu düzeltmeyi siz
yapacaksınız» der. İşaretler, notlar ve onaylar köprünün `semantic_eticaret_*` tablolarında durur.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic.eticaret")

_md = sa.MetaData()

ITEMS = sa.Table(
    "semantic_eticaret_items", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("product_key", sa.String(60), primary_key=True),   # EAN-13 · «crm:<id>» · «tsoft:<ürün>»
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("crm_kitap_id", sa.String(40)),
    sa.Column("tsoft_product_id", sa.String(40)),
    sa.Column("ad", sa.String(500)),
    sa.Column("ad_tsoft", sa.String(500)),
    sa.Column("sitede", sa.Boolean, nullable=False, default=False),
    sa.Column("tsoft_aktif", sa.Boolean, nullable=False, default=False),
    sa.Column("crm_var", sa.Boolean, nullable=False, default=False),
    sa.Column("crm_tsoftaktif", sa.Boolean, nullable=False, default=False),
    sa.Column("crm_etkin", sa.Boolean, nullable=False, default=False),
    sa.Column("stok_logo", sa.Float),
    sa.Column("stok_tsoft", sa.Float),
    sa.Column("fiyat_crm", sa.Float),
    sa.Column("fiyat_logo", sa.Float),
    sa.Column("fiyat_tsoft", sa.Float),
    sa.Column("fiyat_tsoft_indirimli", sa.Float),
    sa.Column("doluluk_puani", sa.Integer),
    sa.Column("eksik_alanlar_json", sa.Text, nullable=False, default="[]"),
    sa.Column("views", sa.Integer, nullable=False, default=0),
    sa.Column("total_sales", sa.Integer, nullable=False, default=0),
    sa.Column("comments", sa.Integer, nullable=False, default=0),
    sa.Column("logo_adet", sa.Float),          # son ECOM_SALES_MONTHS ay, bütün kanallar, net adet (kesim gününe kadar)
    sa.Column("logo_ciro", sa.Float),
    sa.Column("hak_durumu", sa.String(16)),
    sa.Column("yayin_durumu", sa.String(120)),
    sa.Column("yayin_bayragi", sa.String(16)),
    sa.Column("url", sa.String(800)),
    sa.Column("gorsel_url", sa.String(800)),
    sa.Column("logo_kesim_tarihi", sa.String(10)),
    sa.Column("okundu_at", sa.DateTime(timezone=True), nullable=False),
)
DIFFS = sa.Table(
    "semantic_eticaret_diffs", _md,
    sa.Column("id", sa.String(16), primary_key=True),              # sha1(tenant|anahtar|tür)
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("product_key", sa.String(60), nullable=False, index=True),
    sa.Column("tur", sa.String(16), nullable=False, index=True),
    sa.Column("ad", sa.String(500)),
    sa.Column("stok_kodu", sa.String(60)),
    sa.Column("crm_deger", sa.String(600)),
    sa.Column("logo_deger", sa.String(600)),
    sa.Column("tsoft_deger", sa.String(600)),
    sa.Column("dr_deger", sa.String(600)),                          # D&R fiyat farkında D&R'nin değeri (sonradan eklendi)
    sa.Column("aciklama", sa.String(1000)),
    sa.Column("imza", sa.String(40)),                               # değerlerin özeti: bilinçli fark değişince açılır
    sa.Column("etki", sa.Float, nullable=False, default=0.0),       # sıralama: Logo son 12 ay net adet
    sa.Column("ilk_goruldu", sa.DateTime(timezone=True), nullable=False),
    sa.Column("son_goruldu", sa.DateTime(timezone=True), nullable=False),
    sa.Column("durum", sa.String(16), nullable=False, index=True),  # acik | sonra | bilincli | duzeltildi | kapandi
    sa.Column("ertele_bitis", sa.DateTime(timezone=True)),
    sa.Column("neden_onerisi", sa.String(80)),
    sa.Column("neden_olasilik", sa.Float),
    sa.Column("neden_imza", sa.String(40)),
    sa.Column("sahip", sa.String(120)),
    sa.Column("not_", sa.String(1000)),
    sa.Column("isaretleyen", sa.String(120)),
    sa.Column("isaretlendi_at", sa.DateTime(timezone=True)),
    sa.Column("kapatan", sa.String(120)),
    sa.Column("kapandi_at", sa.DateTime(timezone=True)),
    sa.Column("dogrulandi", sa.Boolean, nullable=False, default=False),
    sa.Column("bildirildi_at", sa.DateTime(timezone=True)),
)
DIFF_LOG = sa.Table(
    "semantic_eticaret_diff_log", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("diff_id", sa.String(16), nullable=False, index=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
    sa.Column("kullanici", sa.String(120), nullable=False),
    sa.Column("eylem", sa.String(24), nullable=False),              # acildi | yeniden_acildi | isaret | kapandi | dogrulandi | sahip
    sa.Column("not_", sa.String(1000)),
)
RUNS = sa.Table(
    "semantic_eticaret_runs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(16), nullable=False),                # okuma | haftalik
    sa.Column("basladi", sa.DateTime(timezone=True), nullable=False),
    sa.Column("bitti", sa.DateTime(timezone=True)),
    sa.Column("baslatan", sa.String(120)),
    sa.Column("kaynak_ozet_json", sa.Text),
    sa.Column("hata", sa.String(1000)),
)

_lock = threading.Lock()
_ready: set[int] = set()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp

        def install() -> None:
            _md.create_all(engine, checkfirst=True)
            _add_columns(engine)
        schema_stamp.run(engine, _md.sorted_tables, install, extra="dr_deger")
        _ready.add(id(engine))


def _add_columns(engine: sa.engine.Engine) -> None:
    """Sonradan eklenen kolonlar (tablo önceden kurulmuşsa): yalnız ekler, hiçbir şey silmez."""
    have = {c["name"] for c in sa.inspect(engine).get_columns(DIFFS.name)}
    for col in DIFFS.columns:
        if col.name not in have:
            with engine.begin() as c:
                c.execute(sa.text(f"ALTER TABLE {DIFFS.name} ADD COLUMN {col.name} {col.type.compile(dialect=engine.dialect)}"))


# ------------------------------------------------------------------ sözlük ve ayar

#: Fark türleri, ekrandaki sırayla (önce hukuki risk, sonra okura yanlış görünen, en son içerik).
DIFF_KINDS: dict[str, str] = {
    "hak": "Satışta olmaması gereken",
    "fiyat": "Fiyat farkı",
    "perakende": "D&R fiyat farkı",
    "stok": "Stok yokken satışta",
    "aktiflik": "Aktiflik farkı",
    "barkod": "Barkod ve eşleşme",
    "ad": "Ad farkı",
    "eksik_kart": "Eksik ürün kartı",
}
KIND_ORDER = {k: i for i, k in enumerate(DIFF_KINDS)}
STATUSES: dict[str, str] = {
    "acik": "Açık",
    "sonra": "Sonra bakılacak",
    "bilincli": "Bilinçli fark",
    "duzeltildi": "Düzeltildi (doğrulanacak)",
    "kapandi": "Kapandı",
}
#: Kullanıcının seçebileceği işaretler. «kapandi» yalnız sistemin (koşul kalktı / düzeltme doğrulandı) işidir.
MARKS = ("acik", "sonra", "bilincli", "duzeltildi")
OPEN_STATES = ("acik", "sonra", "bilincli", "duzeltildi")
#: CRM yayın durumu bayrakları (SEO `crm.STATUS_FLAGS`): bunlardan biri varken kitap satışta olmamalı.
GONE_FLAGS: dict[str, str] = {
    "bizim_degil": "Artık bizim değil", "devredildi": "Devredildi", "geri_istendi": "Geri istendi",
    "iptal": "İptal", "cekildi": "Satıştan çekildi",
}
FIELD_LABELS: dict[str, str] = {
    "gorsel": "Kapak görseli (CRM)", "arka_kapak": "Arka kapak metni", "spot": "Spot", "yazar": "Yazar",
    "kategori": "Web kategorisi", "anahtar_kelime": "Anahtar kelimeler", "foy": "Tanıtım föy metni",
    "site_gorsel": "Sitede görsel",
}
REASONS = ["kampanya ya da indirim", "fiyat güncellemesi (yeni baskı ya da zam)", "veri hatası", "belirsiz"]
PAGE = 50

DEFAULTS: dict[str, str] = {
    "ECOM_CHANNELS": "E-TICARET",
    "ECOM_PRICE_REFERENCE": "crm",
    "ECOM_PRICE_TOLERANCE": "0.01",
    "ECOM_STOCK_MIN": "0",
    "ECOM_REQUIRED_FIELDS": "gorsel,arka_kapak,yazar,kategori,site_gorsel",
    "ECOM_HAK_RIGHTS": "",
    "ECOM_DIFF_KINDS": ",".join(DIFF_KINDS),
    "ECOM_ALERT_KINDS": "hak,fiyat,stok",
    "ECOM_ALERT_RECIPIENTS": "",
    "ECOM_WEEKLY_TO": "",
    "ECOM_WEEKLY_DAY": "0",
    "ECOM_SNOOZE_DAYS": "7",
    "ECOM_SALES_MONTHS": "12",
    "ECOM_FUNNEL_MIN_VIEWS": "500",
    "ECOM_FUNNEL_LOW_RATIO": "0.5",
    "ECOM_STOCKOUT_DAYS": "30",
    "ECOM_REASON_MIN_P": "0.70",
    "ECOM_REASON_MIN_MARGIN": "0.30",
    "ECOM_LLM_BUDGET_SEC": "600",
    "ECOM_DEFAULT_OWNERS": "",
    "ECOM_NAME_CHECK": "1",
}


class EticaretError(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def _csv(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").replace(";", ",").split(",") if x.strip()]


def _float(raw: Any, default: float) -> float:
    try:
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _int(raw: Any, default: int) -> int:
    try:
        return int(float(str(raw)))
    except (TypeError, ValueError):
        return default


def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    """Ayarlar: Yönetim ekranı > ortam > varsayılan (`admin.conf`)."""
    def g(k: str) -> str:
        v = conf(k, DEFAULTS[k])
        return DEFAULTS[k] if v is None else str(v)
    kinds = [k for k in _csv(g("ECOM_DIFF_KINDS")) if k in DIFF_KINDS] or list(DIFF_KINDS)
    owners: dict[str, str] = {}
    for part in _csv(g("ECOM_DEFAULT_OWNERS")):
        k, _, u = part.partition(":")
        if k.strip() in DIFF_KINDS and u.strip():
            owners[k.strip()] = u.strip().lower()
    return {
        "channels": _csv(g("ECOM_CHANNELS")) or ["E-TICARET"],
        "priceRef": "logo" if g("ECOM_PRICE_REFERENCE").strip().lower() == "logo" else "crm",
        "priceTol": max(0.0, _float(g("ECOM_PRICE_TOLERANCE"), 0.01)),
        "stockMin": _float(g("ECOM_STOCK_MIN"), 0.0),
        "required": [f for f in _csv(g("ECOM_REQUIRED_FIELDS")) if f in FIELD_LABELS] or ["gorsel", "arka_kapak", "yazar", "kategori"],
        "hakRights": [r for r in _csv(g("ECOM_HAK_RIGHTS")) if r in ("yok", "eksik", "incele")],
        "kinds": kinds,
        "alertKinds": [k for k in _csv(g("ECOM_ALERT_KINDS")) if k in DIFF_KINDS],
        "alertTo": _csv(g("ECOM_ALERT_RECIPIENTS")),
        "weeklyTo": _csv(g("ECOM_WEEKLY_TO")),
        "weeklyDay": min(6, max(0, _int(g("ECOM_WEEKLY_DAY"), 0))),
        "snoozeDays": max(1, _int(g("ECOM_SNOOZE_DAYS"), 7)),
        "salesMonths": max(1, _int(g("ECOM_SALES_MONTHS"), 12)),
        "funnelMinViews": max(0, _int(g("ECOM_FUNNEL_MIN_VIEWS"), 500)),
        "funnelLowRatio": max(0.0, _float(g("ECOM_FUNNEL_LOW_RATIO"), 0.5)),
        "stockoutDays": max(1, _int(g("ECOM_STOCKOUT_DAYS"), 30)),
        "reasonMinP": _float(g("ECOM_REASON_MIN_P"), 0.70),
        "reasonMinMargin": _float(g("ECOM_REASON_MIN_MARGIN"), 0.30),
        "llmBudgetSec": max(0, _int(g("ECOM_LLM_BUDGET_SEC"), 600)),
        "owners": owners,
        "nameCheck": g("ECOM_NAME_CHECK").strip() != "0",
    }


# ------------------------------------------------------------------ yardımcılar


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


def _j(raw: Optional[str], default: Any) -> Any:
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def diff_id(tenant: str, key: str, tur: str) -> str:
    return hashlib.sha1(f"{tenant}|{key}|{tur}".encode()).hexdigest()[:16]


def _sig(*parts: Any) -> str:
    return hashlib.sha1(_dump(parts).encode()).hexdigest()[:16]


_FOLD = str.maketrans({"ı": "i", "İ": "i", "I": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
                       "ö": "o", "Ö": "o", "ç": "c", "Ç": "c", "â": "a", "î": "i", "û": "u"})


def fold(s: Any) -> str:
    """Türkçe harf, büyük/küçük ve noktalama farkı gözetmeden karşılaştırma biçimi."""
    t = str(s or "").translate(_FOLD).lower()
    t = re.sub(r"[^0-9a-z]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def names_differ(crm_name: Any, site_name: Any) -> bool:
    """Ad farkı: ikisi de dolu, sadeleşmiş hâlleri eşit değil ve biri ötekini içermiyor (site adına yazar ya da
    «Ciltli» eklenmesi fark sayılmaz)."""
    a, b = fold(crm_name), fold(site_name)
    if not a or not b or a == b:
        return False
    return a not in b and b not in a


def _money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} ₺"


def _qty(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", ".")


# ------------------------------------------------------------------ eşleme: üç kaynaktan kitap satırı


def _pick_crm(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """Aynı EAN birden çok CRM kartındaysa: «TSOFT Aktif», sonra etkin, sonra en son değişen."""
    return sorted(cards, key=lambda c: (c.get("tsoft"), c.get("etkin"), c.get("degisme") or ""), reverse=True)[0]


def build_items(site: dict[str, Any], crm_cards: Optional[list[dict[str, Any]]], stock: Optional[dict[str, float]],
                prices: Optional[dict[str, dict[str, Any]]], sales: Optional[dict[str, dict[str, float]]],
                st: dict[str, Any], tsoft_values: Callable[[dict[str, Any]], dict[str, Any]], site_image: Callable[[dict[str, Any]], Any],
                cut: Optional[date]) -> dict[str, dict[str, Any]]:
    """Kitap başına tek satır. `crm_cards`/`stock`/`prices`/`sales` okunamadıysa None (o kaynağa bağlı alanlar boş kalır)."""
    items: dict[str, dict[str, Any]] = {}
    by_ean: dict[str, list[dict[str, Any]]] = {}
    for c in crm_cards or []:
        if c.get("ean"):
            by_ean.setdefault(c["ean"], []).append(c)
    rights = site.get("rights") or {}

    def blank(key: str) -> dict[str, Any]:
        return {"product_key": key, "stok_kodu": None, "crm_kitap_id": None, "tsoft_product_id": None, "ad": None, "ad_tsoft": None,
                "sitede": False, "tsoft_aktif": False, "crm_var": False, "crm_tsoftaktif": False, "crm_etkin": False,
                "stok_logo": None, "stok_tsoft": None, "fiyat_crm": None, "fiyat_logo": None, "fiyat_tsoft": None,
                "fiyat_tsoft_indirimli": None, "doluluk_puani": None, "eksik": [], "views": 0, "total_sales": 0, "comments": 0,
                "logo_adet": None, "logo_ciro": None, "hak_durumu": None, "yayin_durumu": None, "yayin_bayragi": None, "url": None,
                "logo_kesim_tarihi": cut.isoformat() if cut else None, "tsoft_urunleri": [], "crm_kart_sayisi": 0,
                "logo_kayit": None, "gorsel_url": None}

    # 1. Sitedeki ürünler (aktif olan önce: aynı barkodlu iki üründe değerler aktiften alınır).
    for p in sorted(site.get("products") or [], key=lambda r: (not r.get("active"), str(r.get("product_id")))):
        v = tsoft_values(p["data"])
        key = v["barkod"] if v["barkod"] and len(v["barkod"]) >= 8 else f"tsoft:{p['product_id']}"
        it = items.setdefault(key, blank(key))
        it["tsoft_urunleri"].append({"id": str(p["product_id"]), "aktif": bool(p.get("active")), "ad": v["ad"] or p.get("name")})
        if it["sitede"]:
            continue
        it.update(sitede=True, tsoft_aktif=bool(p.get("active")), tsoft_product_id=str(p["product_id"]),
                  ad_tsoft=v["ad"] or p.get("name"), fiyat_tsoft=v["fiyat"], fiyat_tsoft_indirimli=v["indirimli"],
                  stok_tsoft=v["stok"], views=v["views"], total_sales=v["sales"], comments=v["comments"],
                  url=(str(v["url"])[:800] if v["url"] else None), gorsel_url=_url(site_image(p["data"])))
    # Aktiflik, sitede en az bir aktif ürün varsa aktiftir.
    for it in items.values():
        if any(u["aktif"] for u in it["tsoft_urunleri"]):
            it["tsoft_aktif"] = True

    # 2. CRM kartları (EAN ile; EAN'sız «TSOFT Aktif» kart kendi satırıdır).
    if crm_cards is not None:
        for ean, cards in by_ean.items():
            c = _pick_crm(cards)
            it = items.setdefault(ean, blank(ean))
            it["crm_kart_sayisi"] = len(cards)
            _apply_crm(it, c)
        for c in crm_cards:
            if not c.get("ean") and c.get("tsoft"):
                key = f"crm:{c['id']}"
                it = items.setdefault(key, blank(key))
                it["crm_kart_sayisi"] = 1
                _apply_crm(it, c)

    # 3. Hak ve yayın durumu (SEO modülünün CRM okuması; aynı EAN anahtarı).
    for key, it in items.items():
        r = rights.get(key)
        if r:
            data = r.get("data") or {}
            it.update(hak_durumu=r.get("rights"), yayin_bayragi=r.get("statusFlag"), yayin_durumu=data.get("statusLabel"))

    # 4. Logo: stok, fiyat listesi, son dönem satış (stok koduyla).
    for it in items.values():
        code = it["stok_kodu"]
        if not code:
            continue
        if stock is not None:
            it["logo_kayit"] = code in stock
            it["stok_logo"] = float(stock.get(code, 0.0))
        if prices is not None and prices.get(code):
            it["fiyat_logo"] = prices[code].get("fiyat")
        if sales is not None:
            s = sales.get(code) or {}
            it["logo_adet"] = float(s.get("adet") or 0.0)
            it["logo_ciro"] = float(s.get("ciro") or 0.0)

    # 5. Kart doluluğu.
    for it in items.values():
        if it["crm_var"]:
            filled = dict(it.pop("_dolu", {}) or {})
            if it["sitede"]:
                filled["site_gorsel"] = bool(it["gorsel_url"])
            need = [f for f in st["required"] if f in filled]
            miss = [f for f in need if not filled.get(f)]
            it["eksik"] = miss
            it["doluluk_puani"] = round(100 * (len(need) - len(miss)) / len(need)) if need else None
        else:
            it.pop("_dolu", None)
    return items


def _url(v: Any) -> Optional[str]:
    return str(v)[:800] if v else None


def _apply_crm(it: dict[str, Any], c: dict[str, Any]) -> None:
    it.update(crm_var=True, crm_kitap_id=c.get("id"), ad=c.get("ad"), stok_kodu=c.get("stok"),
              crm_tsoftaktif=bool(c.get("tsoft")), crm_etkin=bool(c.get("etkin")), fiyat_crm=c.get("fiyat"),
              _dolu=c.get("dolu") or {})


def impact(it: dict[str, Any]) -> float:
    """Sıralama ağırlığı: Logo son dönem net adet (bütün kanallar); yoksa sitedeki toplam satış adedi."""
    if it.get("logo_adet") is not None:
        return max(0.0, float(it["logo_adet"]))
    return float(it.get("total_sales") or 0)


def compute_diffs(it: dict[str, Any], st: dict[str, Any], sources: dict[str, bool]) -> list[dict[str, Any]]:
    """Bir kitabın farkları. `sources`: bu turda okunabilen kaynaklar (tsoft, crm, logo, rights). Okunamayan kaynağa
    bağlı tür hesaplanmaz (ve kapanmaz: `evaluated_kinds`)."""
    out: list[dict[str, Any]] = []
    kinds = set(st["kinds"])
    live = it["tsoft_aktif"]
    cut = it.get("logo_kesim_tarihi")

    def add(tur: str, crm: Any, logo: Any, tsoft: Any, why: str, sig: Any = None, dr: Any = None) -> None:
        if tur in kinds:
            out.append({"tur": tur, "crm_deger": _s(crm), "logo_deger": _s(logo), "tsoft_deger": _s(tsoft), "dr_deger": _s(dr),
                        "aciklama": why[:1000], "imza": _sig(tur, sig if sig is not None else (crm, logo, tsoft))})

    # Satışta olmaması gereken (hukuki risk): CRM yayın durumu ya da ayarda seçilen hak kararı.
    if sources.get("rights") and live:
        flag = it.get("yayin_bayragi")
        if flag in GONE_FLAGS:
            add("hak", it.get("yayin_durumu") or GONE_FLAGS[flag], None, "Satışta",
                f"CRM yayın durumu «{it.get('yayin_durumu') or GONE_FLAGS[flag]}»; kitap sitede satışta olmamalı. "
                "T-soft panelinden ürünü pasife alın.", sig=flag)
        elif it.get("hak_durumu") in st["hakRights"]:
            add("hak", f"Hak kararı: {it['hak_durumu']}", None, "Satışta",
                "İnternette gösterim hakkı doğrulanamadı (Haklar ve CRM ekranı); telif birimi bakmalı.", sig=it["hak_durumu"])

    if sources.get("crm"):
        # Aktiflik (EAN'sız CRM kartı siteyle eşlenemez; onun farkı «barkod»dur).
        if it["crm_var"] and it["crm_tsoftaktif"] and it["crm_etkin"] and not live and not it["product_key"].startswith("crm:"):
            add("aktiflik", "TSOFT Aktif", None, "Satışta değil" if it["sitede"] else "Sitede ürün yok",
                "CRM'de «TSOFT Aktif» işaretli, sitede satışta değil." if it["sitede"] else
                "CRM'de «TSOFT Aktif» işaretli, sitede bu barkodla ürün yok.")
        elif live and it["crm_var"] and not (it["crm_tsoftaktif"] and it["crm_etkin"]):
            why = []
            if not it["crm_tsoftaktif"]:
                why.append("CRM'de «TSOFT Aktif» işaretsiz")
            if not it["crm_etkin"]:
                why.append("CRM kartı pasif")
            add("aktiflik", " · ".join(why), None, "Satışta", "Sitede satışta; " + ", ".join(why) + ".")
        # Barkod ve eşleşme.
        if it["product_key"].startswith("crm:"):
            add("barkod", "EAN-13 boş", None, None, "CRM kartı «TSOFT Aktif» işaretli ama EAN-13 boş; siteyle eşlenemiyor.")
        elif it["product_key"].startswith("tsoft:") and live:
            add("barkod", None, None, "Barkod yok", "Sitede satıştaki ürünün barkodu yok; CRM kartıyla eşlenemiyor.")
        elif live and not it["crm_var"]:
            add("barkod", "Kart yok", None, it["product_key"], "Sitedeki barkod CRM'de hiçbir kitap kartında yok.")
        else:
            notes = []
            active_products = [u for u in it["tsoft_urunleri"] if u["aktif"]]
            if live and len(active_products) > 1:
                notes.append(f"aynı barkod sitede {len(active_products)} aktif üründe")
            if it["crm_kart_sayisi"] > 1 and (live or it["crm_tsoftaktif"]):
                notes.append(f"aynı barkod CRM'de {it['crm_kart_sayisi']} kartta")
            if notes:
                add("barkod", f"{it['crm_kart_sayisi']} kart", None, f"{len(active_products)} ürün",
                    "Çift kayıt: " + "; ".join(notes) + ".")
        # Ad.
        if st["nameCheck"] and live and it["crm_var"] and names_differ(it["ad"], it["ad_tsoft"]):
            add("ad", it["ad"], None, it["ad_tsoft"], "Sitedeki ürün adı CRM kitap adıyla örtüşmüyor.")
        # Eksik kart.
        if live and it["crm_var"] and it["eksik"]:
            labels = [FIELD_LABELS.get(f, f) for f in it["eksik"]]
            add("eksik_kart", "Eksik: " + ", ".join(labels), None, None,
                f"Ürün kartında {len(labels)} alan boş (doluluk %{it['doluluk_puani']}).", sig=tuple(it["eksik"]))

    # Fiyat: sitedeki fiyat referansla (ayar: CRM ya da Logo) karşılaştırılır; iki taraf da dolu olmalı.
    ref_ok = sources.get("crm") if st["priceRef"] == "crm" else sources.get("logo")
    if ref_ok and live and it["fiyat_tsoft"] is not None:
        ref = it["fiyat_crm"] if st["priceRef"] == "crm" else it["fiyat_logo"]
        if ref is not None and ref > 0 and abs(float(it["fiyat_tsoft"]) - float(ref)) > st["priceTol"]:
            other = "CRM" if st["priceRef"] == "crm" else "Logo liste"
            extra = f" Sitede indirimli fiyat {_money(it['fiyat_tsoft_indirimli'])}." if it.get("fiyat_tsoft_indirimli") else ""
            add("fiyat", _money(it["fiyat_crm"]), _money(it["fiyat_logo"]), _money(it["fiyat_tsoft"]),
                f"Sitedeki fiyat {other} fiyatından farklı ({_money(it['fiyat_tsoft'])} ↔ {_money(ref)}).{extra}",
                sig=(it["fiyat_crm"], it["fiyat_logo"], it["fiyat_tsoft"], it["fiyat_tsoft_indirimli"]))

    # D&R fiyatı: TİMAŞ grubu kitap, barkodu D&R kataloğunun son görüntüsünde. (1) Sitemizde satışta ve D&R'nin satış
    # fiyatı sitedeki fiyatımızdan (indirimli varsa o) düşük; (2) D&R'deki liste fiyatı bizim liste fiyatımızdan farklı.
    dr = it.get("dr")
    if sources.get("dr") and ref_ok and dr and dr.get("katalogda") and dr.get("timas"):
        tol = st["priceTol"]
        drf, drl = dr.get("drFiyat"), dr.get("fiyat")
        site = site_effective(it) if live else None
        ref = it["fiyat_crm"] if st["priceRef"] == "crm" else it["fiyat_logo"]
        notes = []
        if site is not None and drf and dr.get("siteSatista") and drf < site - tol:
            notes.append(f"D&R'de {_money(drf)}, sitemizde {_money(site)}: aynı kitap D&R'de {_money(site - drf)} ucuz.")
        if ref is not None and ref > 0 and drl and abs(float(drl) - float(ref)) > tol:
            notes.append(f"D&R'deki liste fiyatı {_money(drl)}, bizim liste fiyatımız ({'CRM' if st['priceRef'] == 'crm' else 'Logo liste'}) "
                         f"{_money(ref)}; D&R eski ya da farklı liste fiyatı gösteriyor.")
        if notes:
            ind = dr.get("indirim")
            dr_txt = (f"{_money(drf)}" + (f" (D&R liste {_money(drl)}, %{round(ind * 100):.0f} indirim)" if ind and ind > 0 else
                                          f" (D&R liste {_money(drl)})")) if drf else f"D&R liste {_money(drl)}"
            if not dr.get("siteSatista"):
                dr_txt += " · sitede satışta değil"
            site_txt = (_money(it["fiyat_tsoft"]) + (f" · indirimli {_money(site)}" if site is not None and site != it["fiyat_tsoft"] else "")
                        if it.get("fiyat_tsoft") is not None else None)
            add("perakende", _money(it["fiyat_crm"]), _money(it["fiyat_logo"]), site_txt,
                " ".join(notes) + f" (D&R kataloğu {dr.get('son') or '—'}.)",
                sig=(drf, drl, site, ref), dr=dr_txt)

    # Stok: sitede satışta, Logo bakiyesi eşik ve altında (kesim tarihiyle).
    if sources.get("logo") and live and it["stok_kodu"] and it["stok_logo"] is not None and it["stok_logo"] <= st["stockMin"]:
        no_row = it.get("logo_kayit") is False
        site_stock = f"sitede stok {_qty(it['stok_tsoft'])}" if it.get("stok_tsoft") is not None else "sitede stok alanı yok"
        add("stok", it["stok_kodu"], _qty(it["stok_logo"]) + (" (hareket yok)" if no_row else ""), _qty(it["stok_tsoft"]),
            f"Sitede satışta; Logo stoğu {_qty(it['stok_logo'])} (kesim {cut or 'bilinmiyor'}), {site_stock}."
            + (" Logo'da bu stok koduyla hareket yok; kod doğru mu?" if no_row else ""),
            sig=(it["stok_logo"] <= st["stockMin"], no_row))
    for d in out:
        d["etki"] = impact(it)
        d["ad"] = (it.get("ad") or it.get("ad_tsoft") or "")[:500] or None
        d["stok_kodu"] = it.get("stok_kodu")
    return out


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    return str(v)[:600]


def site_effective(it: dict[str, Any]) -> Optional[float]:
    """Okurun sitede ödediği fiyat: indirimli fiyat doluysa ve liste fiyatından düşükse o, değilse site fiyatı."""
    p, d = it.get("fiyat_tsoft"), it.get("fiyat_tsoft_indirimli")
    if p is None:
        return None
    return float(d) if d is not None and 0 < float(d) < float(p) else float(p)


def evaluated_kinds(st: dict[str, Any], sources: dict[str, bool]) -> set[str]:
    """Bu turda hesaplanabilen türler: yalnız bunların kaydı kapanabilir (okunamayan kaynak farkı «kalktı» saydırmaz)."""
    if not sources.get("tsoft"):
        return set()
    out = set()
    if sources.get("rights"):
        out.add("hak")
    if sources.get("crm"):
        out |= {"aktiflik", "barkod", "ad", "eksik_kart"}
    if sources.get("crm" if st["priceRef"] == "crm" else "logo"):
        out.add("fiyat")
        if sources.get("dr"):
            out.add("perakende")
    if sources.get("logo"):
        out.add("stok")
    return out & set(st["kinds"])


# ------------------------------------------------------------------ fark kaydı


def _log(c: Any, tenant: str, did: str, user: str, eylem: str, note: Optional[str], at: datetime) -> None:
    c.execute(DIFF_LOG.insert().values(diff_id=did, tenant_id=tenant, zaman=at, kullanici=user or "sistem", eylem=eylem,
                                       not_=(note or None) and str(note)[:1000]))


def apply_run(engine: sa.engine.Engine, tenant: str, items: dict[str, dict[str, Any]], st: dict[str, Any],
              sources: dict[str, bool], site_read_at: Optional[datetime], at: Optional[datetime] = None) -> dict[str, Any]:
    """Satırları yazar, farkları günceller. Dönen: yeni/yeniden açılan farkların kimlikleri ve sayılar."""
    ensure(engine)
    at = at or now()
    site_read_at = _aware(site_read_at)
    evaluated = evaluated_kinds(st, sources)
    found: dict[str, dict[str, Any]] = {}
    for it in items.values():
        for d in compute_diffs(it, st, sources):
            found[diff_id(tenant, it["product_key"], d["tur"])] = {**d, "product_key": it["product_key"]}
    counts = {"yeni": 0, "yeniden": 0, "kapandi": 0, "dogrulandi": 0, "surdu": 0}
    events: list[str] = []
    with engine.begin() as c:
        c.execute(ITEMS.delete().where(ITEMS.c.tenant_id == tenant))
        rows = [_item_row(tenant, it, at) for it in items.values()]
        for i in range(0, len(rows), 500):
            c.execute(ITEMS.insert(), rows[i:i + 500])
        old = {r["id"]: dict(r) for r in c.execute(sa.select(DIFFS).where(DIFFS.c.tenant_id == tenant)).mappings()}
        for did, d in found.items():
            vals = {k: d.get(k) for k in ("ad", "stok_kodu", "crm_deger", "logo_deger", "tsoft_deger", "dr_deger", "aciklama",
                                          "imza", "etki")}
            prev = old.get(did)
            if prev is None:
                owner = st["owners"].get(d["tur"])
                c.execute(DIFFS.insert().values(id=did, tenant_id=tenant, product_key=d["product_key"], tur=d["tur"], ilk_goruldu=at,
                                                son_goruldu=at, durum="acik", sahip=owner, dogrulandi=False, **vals))
                _log(c, tenant, did, "sistem", "acildi", d["aciklama"], at)
                counts["yeni"] += 1
                events.append(did)
                continue
            upd: dict[str, Any] = {**vals, "son_goruldu": at}
            state = prev["durum"]
            reopen_note = None
            if state == "kapandi":
                reopen_note = "Yeniden görüldü."
                upd.update(ilk_goruldu=at)
            elif state == "duzeltildi":
                closed = _aware(prev["kapandi_at"]) or _aware(prev["isaretlendi_at"])
                if site_read_at and closed and site_read_at > closed:
                    reopen_note = "«Düzeltildi» denmişti; sonraki okumada fark hâlâ var."
            elif state == "bilincli" and prev.get("imza") != d["imza"]:
                reopen_note = "Değerler değişti; bilinçli fark yeniden açıldı."
            elif state == "sonra" and prev.get("ertele_bitis") and _aware(prev["ertele_bitis"]) <= at:
                upd.update(durum="acik", ertele_bitis=None)
                _log(c, tenant, did, "sistem", "isaret", "Erteleme süresi doldu; açık.", at)
            if reopen_note:
                upd.update(durum="acik", kapatan=None, kapandi_at=None, dogrulandi=False, ertele_bitis=None, bildirildi_at=None)
                _log(c, tenant, did, "sistem", "yeniden_acildi", reopen_note, at)
                counts["yeniden"] += 1
                events.append(did)
            else:
                counts["surdu"] += 1
            c.execute(DIFFS.update().where(DIFFS.c.id == did).values(**upd))
        for did, prev in old.items():
            if did in found or prev["durum"] == "kapandi":
                continue
            if prev["tur"] not in st["kinds"]:
                c.execute(DIFFS.update().where(DIFFS.c.id == did).values(durum="kapandi", kapatan="sistem", kapandi_at=at,
                                                                      dogrulandi=False, ertele_bitis=None))
                _log(c, tenant, did, "sistem", "kapandi", "Bu fark türü ayarda kapatıldı.", at)
                counts["kapandi"] += 1
                continue
            if prev["tur"] not in evaluated:
                continue
            if prev["durum"] == "duzeltildi":
                c.execute(DIFFS.update().where(DIFFS.c.id == did).values(durum="kapandi", dogrulandi=True, kapandi_at=at,
                                                                      kapatan=prev["kapatan"] or prev["isaretleyen"] or "sistem"))
                _log(c, tenant, did, "sistem", "dogrulandi", "Düzeltme son okumada doğrulandı.", at)
                counts["dogrulandi"] += 1
            else:
                c.execute(DIFFS.update().where(DIFFS.c.id == did).values(durum="kapandi", kapatan="sistem", kapandi_at=at,
                                                                      dogrulandi=False, ertele_bitis=None))
                _log(c, tenant, did, "sistem", "kapandi", "Koşul kalktı; kendiliğinden kapandı.", at)
                counts["kapandi"] += 1
    return {"counts": counts, "events": events, "evaluated": sorted(evaluated, key=KIND_ORDER.get), "items": len(items),
            "diffs": len(found)}


def _item_row(tenant: str, it: dict[str, Any], at: datetime) -> dict[str, Any]:
    cols = {c.name for c in ITEMS.columns}
    row = {k: v for k, v in it.items() if k in cols}
    name = it.get("ad") or it.get("ad_tsoft")
    row.update(tenant_id=tenant, eksik_alanlar_json=_dump(it.get("eksik") or []), okundu_at=at,
               ad=str(name)[:500] if name else None,
               ad_tsoft=(str(it["ad_tsoft"])[:500] if it.get("ad_tsoft") else None),
               views=int(it.get("views") or 0), total_sales=int(it.get("total_sales") or 0), comments=int(it.get("comments") or 0))
    return row


def mark(engine: sa.engine.Engine, tenant: str, user: str, did: str, durum: str, note: Optional[str], sahip: Optional[str],
         st: dict[str, Any], at: Optional[datetime] = None) -> dict[str, Any]:
    """Kullanıcı işareti. Bilinçli fark gerekçe ister; «sonra» ayardaki gün kadar erteler."""
    at = at or now()
    note = (note or "").strip()[:1000] or None
    if durum not in MARKS:
        raise EticaretError("Geçersiz işaret; açık, sonra, bilinçli ya da düzeltildi seçilmeli.", 422)
    if durum == "bilincli" and not note:
        raise EticaretError("Bilinçli fark için gerekçe yazılmalı (ör. «kampanya fiyatı»).", 422)
    with engine.begin() as c:
        prev = c.execute(sa.select(DIFFS).where(DIFFS.c.tenant_id == tenant, DIFFS.c.id == did)).mappings().first()
        if prev is None:
            raise EticaretError("Fark bulunamadı.", 404)
        if prev["durum"] == "kapandi":
            raise EticaretError("Bu fark kapanmış; koşulu yeniden görülürse kendiliğinden açılır.", 409)
        upd: dict[str, Any] = {"durum": durum, "isaretleyen": user, "isaretlendi_at": at, "not_": note or prev["not_"],
                               "ertele_bitis": at + timedelta(days=st["snoozeDays"]) if durum == "sonra" else None,
                               "kapatan": user if durum == "duzeltildi" else None, "kapandi_at": at if durum == "duzeltildi" else None}
        if sahip is not None:
            upd["sahip"] = sahip.strip().lower()[:120] or None
        c.execute(DIFFS.update().where(DIFFS.c.id == did).values(**upd))
        text = STATUSES[durum] + (f" — {note}" if note else "")
        if durum == "sonra":
            text += f" ({st['snoozeDays']} gün)"
        _log(c, tenant, did, user, "isaret", text, at)
        if sahip is not None and (upd.get("sahip") or None) != prev["sahip"]:
            _log(c, tenant, did, user, "sahip", f"Sahip: {upd.get('sahip') or '—'}", at)
    return get_diff(engine, tenant, did)


# ------------------------------------------------------------------ okuma: ekranlar


def _diff_out(r: Any) -> dict[str, Any]:
    d = dict(r)
    return {"id": d["id"], "productKey": d["product_key"], "tur": d["tur"], "turAdi": DIFF_KINDS.get(d["tur"], d["tur"]),
            "ad": d["ad"], "stokKodu": d["stok_kodu"], "crm": d["crm_deger"], "logo": d["logo_deger"], "site": d["tsoft_deger"],
            "dr": d.get("dr_deger"),
            "aciklama": d["aciklama"], "etki": d["etki"], "ilkGoruldu": iso(d["ilk_goruldu"]), "sonGoruldu": iso(d["son_goruldu"]),
            "durum": d["durum"], "durumAdi": STATUSES.get(d["durum"], d["durum"]), "erteleBitis": iso(d["ertele_bitis"]),
            "neden": ({"oneri": d["neden_onerisi"], "olasilik": d["neden_olasilik"]} if d["neden_onerisi"] else None),
            "sahip": d["sahip"], "not": d["not_"], "isaretleyen": d["isaretleyen"], "isaretlendi": iso(d["isaretlendi_at"]),
            "kapatan": d["kapatan"], "kapandi": iso(d["kapandi_at"]), "dogrulandi": bool(d["dogrulandi"])}


def _diff_filter(tenant: str, tur: str = "", durum: str = "", q: str = "", sahip: str = "") -> list[Any]:
    cond: list[Any] = [DIFFS.c.tenant_id == tenant]
    if tur:
        if tur not in DIFF_KINDS:
            raise EticaretError("Bilinmeyen fark türü.", 422)
        cond.append(DIFFS.c.tur == tur)
    if durum == "":
        cond.append(DIFFS.c.durum.in_(("acik", "sonra")))
    elif durum == "acik-hepsi":
        cond.append(DIFFS.c.durum.in_(OPEN_STATES))
    elif durum == "hepsi":
        pass
    elif durum in STATUSES:
        cond.append(DIFFS.c.durum == durum)
    else:
        raise EticaretError("Bilinmeyen durum.", 422)
    if q.strip():
        like = f"%{q.strip()}%"
        cond.append(sa.or_(DIFFS.c.ad.ilike(like), DIFFS.c.product_key.ilike(like), DIFFS.c.stok_kodu.ilike(like)))
    if sahip.strip():
        cond.append(DIFFS.c.sahip == sahip.strip().lower())
    return cond


def _order() -> list[Any]:
    kind_rank = sa.case({k: i for k, i in KIND_ORDER.items()}, value=DIFFS.c.tur, else_=99)
    return [kind_rank, DIFFS.c.etki.desc(), DIFFS.c.ilk_goruldu, DIFFS.c.id]


def list_diffs(engine: sa.engine.Engine, tenant: str, *, tur: str = "", durum: str = "", q: str = "", sahip: str = "",
               page: int = 0, size: int = PAGE) -> dict[str, Any]:
    ensure(engine)
    cond = _diff_filter(tenant, tur, durum, q, sahip)
    page, size = max(0, page), max(1, min(size, 500))
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(DIFFS).where(*cond)).scalar() or 0
        rows = c.execute(sa.select(DIFFS).where(*cond).order_by(*_order()).offset(page * size).limit(size)).mappings().all()
        by_kind = dict(c.execute(sa.select(DIFFS.c.tur, sa.func.count()).where(*_diff_filter(tenant, "", durum, q, sahip))
                                 .group_by(DIFFS.c.tur)).all())
    return {"items": [_diff_out(r) for r in rows], "total": total, "page": page, "pageSize": size,
            "turSayilari": {k: by_kind.get(k, 0) for k in DIFF_KINDS}}


def all_diffs(engine: sa.engine.Engine, tenant: str, *, tur: str = "", durum: str = "", q: str = "", sahip: str = "") -> list[dict[str, Any]]:
    """Dışa aktarma: süzgece uyan bütün satırlar, sayfalı okunur (tavan yok)."""
    out: list[dict[str, Any]] = []
    page = 0
    while True:
        chunk = list_diffs(engine, tenant, tur=tur, durum=durum, q=q, sahip=sahip, page=page, size=500)
        out.extend(chunk["items"])
        if len(out) >= chunk["total"] or not chunk["items"]:
            return out
        page += 1


def diffs_csv(rows: list[dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Tür", "Barkod / anahtar", "Stok kodu", "Kitap", "CRM", "Logo", "Site", "D&R", "Açıklama", "Durum", "Sahip", "Not",
                "İlk görüldü", "Son görüldü", "Zeki AI neden önerisi"])
    for d in rows:
        w.writerow([d["turAdi"], d["productKey"], d["stokKodu"] or "", d["ad"] or "", d["crm"] or "", d["logo"] or "",
                    d["site"] or "", d.get("dr") or "", d["aciklama"] or "", d["durumAdi"], d["sahip"] or "", d["not"] or "",
                    (d["ilkGoruldu"] or "")[:10], (d["sonGoruldu"] or "")[:10],
                    (f"{d['neden']['oneri']} (%{round((d['neden']['olasilik'] or 0) * 100)})" if d.get("neden") else "")])
    return buf.getvalue().encode("utf-8-sig")


def get_diff(engine: sa.engine.Engine, tenant: str, did: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(DIFFS).where(DIFFS.c.tenant_id == tenant, DIFFS.c.id == did)).mappings().first()
        if r is None:
            raise EticaretError("Fark bulunamadı.", 404)
        logs = c.execute(sa.select(DIFF_LOG).where(DIFF_LOG.c.tenant_id == tenant, DIFF_LOG.c.diff_id == did)
                         .order_by(DIFF_LOG.c.zaman.desc(), DIFF_LOG.c.id.desc())).mappings().all()
    return {**_diff_out(r), "gunluk": [_log_out(x) for x in logs]}


def _log_out(r: Any) -> dict[str, Any]:
    return {"zaman": iso(r["zaman"]), "kullanici": r["kullanici"], "eylem": r["eylem"], "not": r["not_"]}


def _item_out(r: Any) -> dict[str, Any]:
    d = dict(r)
    views, sales = int(d["views"] or 0), int(d["total_sales"] or 0)
    return {"productKey": d["product_key"], "stokKodu": d["stok_kodu"], "crmKitapId": d["crm_kitap_id"],
            "tsoftUrunId": d["tsoft_product_id"], "ad": d["ad"], "adSite": d["ad_tsoft"], "sitede": bool(d["sitede"]),
            "siteAktif": bool(d["tsoft_aktif"]), "crmVar": bool(d["crm_var"]), "crmTsoftAktif": bool(d["crm_tsoftaktif"]),
            "crmEtkin": bool(d["crm_etkin"]), "stokLogo": d["stok_logo"], "stokSite": d["stok_tsoft"], "fiyatCrm": d["fiyat_crm"],
            "fiyatLogo": d["fiyat_logo"], "fiyatSite": d["fiyat_tsoft"], "fiyatSiteIndirimli": d["fiyat_tsoft_indirimli"],
            "doluluk": d["doluluk_puani"], "eksik": [{"alan": f, "ad": FIELD_LABELS.get(f, f)} for f in _j(d["eksik_alanlar_json"], [])],
            "goruntulenme": views, "siteSatis": sales, "yorum": int(d["comments"] or 0),
            "donusum": (sales / views) if views > 0 else None, "logoAdet": d["logo_adet"], "logoCiro": d["logo_ciro"],
            "hak": d["hak_durumu"], "yayinDurumu": d["yayin_durumu"], "yayinBayragi": d["yayin_bayragi"], "url": d["url"],
            "logoKesim": d["logo_kesim_tarihi"], "okundu": iso(d["okundu_at"])}


def item_detail(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(ITEMS).where(ITEMS.c.tenant_id == tenant, ITEMS.c.product_key == key)).mappings().first()
        if r is None:
            raise EticaretError("Kitap bulunamadı; gece okumasından sonra yeniden deneyin.", 404)
        diffs = c.execute(sa.select(DIFFS).where(DIFFS.c.tenant_id == tenant, DIFFS.c.product_key == key)
                          .order_by(*_order())).mappings().all()
        ids = [d["id"] for d in diffs]
        logs = []
        if ids:
            logs = c.execute(sa.select(DIFF_LOG).where(DIFF_LOG.c.tenant_id == tenant, DIFF_LOG.c.diff_id.in_(ids))
                             .order_by(DIFF_LOG.c.zaman.desc(), DIFF_LOG.c.id.desc())).mappings().all()
    kinds = {d["id"]: d["tur"] for d in diffs}
    return {"kitap": _item_out(r), "farklar": [_diff_out(d) for d in diffs],
            "gunluk": [{**_log_out(x), "tur": kinds.get(x["diff_id"]), "turAdi": DIFF_KINDS.get(kinds.get(x["diff_id"], ""), "")}
                       for x in logs]}


def overview(engine: sa.engine.Engine, tenant: str, status: dict[str, Any], today_size: int = 20) -> dict[str, Any]:
    ensure(engine)
    week = now() - timedelta(days=7)
    with engine.connect() as c:
        live = c.execute(sa.select(sa.func.count()).select_from(ITEMS).where(ITEMS.c.tenant_id == tenant, ITEMS.c.tsoft_aktif.is_(True))).scalar() or 0
        crm_active = c.execute(sa.select(sa.func.count()).select_from(ITEMS).where(ITEMS.c.tenant_id == tenant, ITEMS.c.crm_tsoftaktif.is_(True))).scalar() or 0
        states = dict(c.execute(sa.select(DIFFS.c.durum, sa.func.count()).where(DIFFS.c.tenant_id == tenant).group_by(DIFFS.c.durum)).all())
        open_by = dict(c.execute(sa.select(DIFFS.c.tur, sa.func.count()).where(DIFFS.c.tenant_id == tenant, DIFFS.c.durum.in_(("acik", "sonra")))
                                 .group_by(DIFFS.c.tur)).all())
        closed = c.execute(sa.select(DIFFS.c.ilk_goruldu, DIFFS.c.kapandi_at).where(
            DIFFS.c.tenant_id == tenant, DIFFS.c.durum == "kapandi", DIFFS.c.kapandi_at >= week)).all()
        today_cond = [DIFFS.c.tenant_id == tenant, DIFFS.c.durum == "acik"]
        today_total = c.execute(sa.select(sa.func.count()).select_from(DIFFS).where(*today_cond)).scalar() or 0
        today = c.execute(sa.select(DIFFS).where(*today_cond).order_by(*_order()).limit(today_size)).mappings().all()
        last = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.tur == "okuma").order_by(RUNS.c.basladi.desc()).limit(1)).mappings().first()
        cut = c.execute(sa.select(sa.func.max(ITEMS.c.logo_kesim_tarihi)).where(ITEMS.c.tenant_id == tenant)).scalar()
    days = [(_aware(b) - _aware(a)).total_seconds() / 86400 for a, b in closed if a and b]
    open_total = sum(states.get(s, 0) for s in ("acik", "sonra"))
    return {
        "gostergeler": {"siteAktif": live, "crmTsoftAktif": crm_active, "acikFark": open_total,
                        "eksikKart": open_by.get("eksik_kart", 0), "satistaOlmamali": open_by.get("hak", 0)},
        "turSayilari": {k: open_by.get(k, 0) for k in DIFF_KINDS}, "durumSayilari": {k: states.get(k, 0) for k in STATUSES},
        "haftalik": {"kapanan": len(closed), "ortalamaKapanmaGun": round(sum(days) / len(days), 1) if days else None},
        "bugun": {"items": [_diff_out(r) for r in today], "total": today_total},
        "sonOkuma": _run_out(last) if last else None, "logoKesim": cut, "durum": status,
        "gonderim": False,
    }


def _run_out(r: Any) -> dict[str, Any]:
    return {"basladi": iso(r["basladi"]), "bitti": iso(r["bitti"]), "baslatan": r["baslatan"], "hata": r["hata"],
            "ozet": _j(r["kaynak_ozet_json"], {})}


def funnel(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], *, dusuk: bool = False, q: str = "", sort: str = "goruntulenme",
           page: int = 0, size: int = PAGE) -> dict[str, Any]:
    """Sitedeki görüntülenme → satış (T-soft kaydındaki tüm zaman sayaçları). «Düşük dönüşüm»: görüntülenmesi eşik
    üstünde, dönüşümü sitenin ortanca dönüşümünün ayardaki oranından düşük olan ürün."""
    ensure(engine)
    base = [ITEMS.c.tenant_id == tenant, ITEMS.c.tsoft_aktif.is_(True)]
    with engine.connect() as c:
        ratios = sorted(s / v for v, s in c.execute(sa.select(ITEMS.c.views, ITEMS.c.total_sales).where(*base, ITEMS.c.views > 0)).all())
    median = ratios[len(ratios) // 2] if ratios else None
    cond = list(base)
    if q.strip():
        like = f"%{q.strip()}%"
        cond.append(sa.or_(ITEMS.c.ad.ilike(like), ITEMS.c.product_key.ilike(like), ITEMS.c.stok_kodu.ilike(like)))
    limit_ratio = (median or 0) * st["funnelLowRatio"]
    if dusuk:
        cond += [ITEMS.c.views >= max(1, st["funnelMinViews"]),
                 ITEMS.c.total_sales < ITEMS.c.views * limit_ratio]
    order = {"satis": [ITEMS.c.total_sales.desc()], "donusum": [(ITEMS.c.total_sales * 1.0 / sa.func.nullif(ITEMS.c.views, 0)).asc()],
             "logo": [sa.func.coalesce(ITEMS.c.logo_adet, 0).desc()]}.get(sort, [ITEMS.c.views.desc()])
    page, size = max(0, page), max(1, min(size, 500))
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(ITEMS).where(*cond)).scalar() or 0
        rows = c.execute(sa.select(ITEMS).where(*cond).order_by(*order, ITEMS.c.product_key).offset(page * size).limit(size)).mappings().all()
        sums = c.execute(sa.select(sa.func.coalesce(sa.func.sum(ITEMS.c.views), 0), sa.func.coalesce(sa.func.sum(ITEMS.c.total_sales), 0),
                                   sa.func.coalesce(sa.func.sum(ITEMS.c.comments), 0)).where(*base)).first()
    items = []
    for r in rows:
        x = _item_out(r)
        x["olasiNedenler"] = hints(x, median, st)
        items.append(x)
    return {"items": items, "total": total, "page": page, "pageSize": size, "ortancaDonusum": median,
            "dusukEsik": {"enAzGoruntulenme": st["funnelMinViews"], "oran": st["funnelLowRatio"], "donusum": limit_ratio if median else None},
            "toplam": {"goruntulenme": int(sums[0] or 0), "satis": int(sums[1] or 0), "yorum": int(sums[2] or 0)},
            "not": "Görüntülenme ve satış sitedeki ürün sayaçlarıdır (tüm zamanlar; dönem bilgisi sitede yok). Sepet ve ödeme "
                   "adımları için site analitiği bağlı değil."}


def hints(x: dict[str, Any], median: Optional[float], st: dict[str, Any]) -> list[str]:
    """Az satmanın kurallı olası nedenleri (kart doluluğu, yorum, stok, fiyat). Model kullanılmaz: bunlar veriden okunur."""
    out = []
    if x["eksik"]:
        out.append("Kartta boş alan: " + ", ".join(e["ad"] for e in x["eksik"]))
    if not x["yorum"]:
        out.append("Okur yorumu yok")
    if x["stokLogo"] is not None and x["stokLogo"] <= st["stockMin"]:
        out.append("Logo stoğu yok")
    if x["fiyatSite"] is not None and x["fiyatCrm"] and x["fiyatSite"] - x["fiyatCrm"] > st["priceTol"]:
        out.append("Sitedeki fiyat CRM fiyatından yüksek")
    if median is not None and x["donusum"] is not None and x["donusum"] < median * st["funnelLowRatio"]:
        out.append("Dönüşüm sitenin ortancasının altında")
    return out


def stock_days(item: Optional[dict[str, Any]], months: int) -> Optional[float]:
    """Kalan gün = Logo stoğu ÷ (son dönem net adet ÷ gün). Satış yoksa None."""
    if not item or item.get("stok_logo") is None or not item.get("logo_adet") or item["logo_adet"] <= 0:
        return None
    daily = item["logo_adet"] / (months * 30.4375)
    return max(0.0, item["stok_logo"]) / daily if daily > 0 else None


def items_by_code(engine: sa.engine.Engine, tenant: str, codes: Iterable[str]) -> dict[str, dict[str, Any]]:
    codes = [c for c in dict.fromkeys(codes) if c]
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for i in range(0, len(codes), 500):
            for r in c.execute(sa.select(ITEMS).where(ITEMS.c.tenant_id == tenant, ITEMS.c.stok_kodu.in_(codes[i:i + 500]))).mappings():
                prev = out.get(r["stok_kodu"])
                if prev is None or (r["tsoft_aktif"] and not prev["tsoft_aktif"]):
                    out[r["stok_kodu"]] = dict(r)
    return out


def items_by_key(engine: sa.engine.Engine, tenant: str, keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    keys = [k for k in dict.fromkeys(keys) if k]
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for i in range(0, len(keys), 500):
            for r in c.execute(sa.select(ITEMS).where(ITEMS.c.tenant_id == tenant, ITEMS.c.product_key.in_(keys[i:i + 500]))).mappings():
                out[r["product_key"]] = dict(r)
    return out


# ------------------------------------------------------------------ pazar yerleri (Logo sell-in)


def marketplace_summary(rows: list[dict[str, Any]], year: int, cut: Optional[date]) -> dict[str, Any]:
    """Cari başına bu yıl ve geçen yılın aynı dönemi (kesim gününe kadar): satış, iade, net, iade oranı, değişim, aylık dizi.
    `rows`: iki yılın cari × ay satırları (`eticaret_sources.read_marketplaces`)."""
    last_day = cut if cut and cut.year == year else date(year, 12, 31)
    prev_last = _same_day_prev_year(last_day)
    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not r["kod"]:
            continue
        a = by.setdefault(r["kod"], {"kod": r["kod"], "unvan": r["unvan"], "kanal": r["kanal"], "satis": 0.0, "iade": 0.0,
                                     "satisAdet": 0.0, "iadeAdet": 0.0, "oncekiNet": 0.0, "oncekiSatis": 0.0, "oncekiIade": 0.0,
                                     "aylik": [0.0] * 12})
        a["unvan"] = a["unvan"] or r["unvan"]
        if r["yil"] == year:
            a["satis"] += r["satis"]
            a["iade"] += r["iade"]
            a["satisAdet"] += r["satisAdet"]
            a["iadeAdet"] += r["iadeAdet"]
            if 1 <= r["ay"] <= 12:
                a["aylik"][r["ay"] - 1] += r["satis"] - r["iade"]
        elif r["yil"] == year - 1 and r["ay"] <= prev_last.month:
            # Önceki yılın ay satırları kesimin ayına kadar; ayın içindeki gün sınırı SQL penceresinde uygulanır.
            a["oncekiSatis"] += r["satis"]
            a["oncekiIade"] += r["iade"]
            a["oncekiNet"] += r["satis"] - r["iade"]
    out = []
    for a in by.values():
        a["net"] = a["satis"] - a["iade"]
        a["iadeOrani"] = (a["iade"] / a["satis"]) if a["satis"] else None
        a["oncekiIadeOrani"] = (a["oncekiIade"] / a["oncekiSatis"]) if a["oncekiSatis"] else None
        a["degisim"] = ((a["net"] - a["oncekiNet"]) / abs(a["oncekiNet"])) if a["oncekiNet"] else None
        out.append(a)
    out.sort(key=lambda a: (-a["net"], a["kod"]))
    tot = {k: sum(a[k] for a in out) for k in ("satis", "iade", "net", "oncekiNet", "satisAdet", "iadeAdet")}
    tot["iadeOrani"] = (tot["iade"] / tot["satis"]) if tot["satis"] else None
    tot["degisim"] = ((tot["net"] - tot["oncekiNet"]) / abs(tot["oncekiNet"])) if tot["oncekiNet"] else None
    return {"yil": year, "donem": {"bas": f"{year}-01-01", "son": last_day.isoformat(), "oncekiBas": f"{year - 1}-01-01",
                                   "oncekiSon": prev_last.isoformat()},
            "cariler": out, "toplam": tot, "kesim": cut.isoformat() if cut else None}


def _same_day_prev_year(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:  # 29 Şubat
        return d.replace(year=d.year - 1, day=28)


def marketplace_windows(year: int, cut: Optional[date]) -> tuple[tuple[date, date], tuple[date, date]]:
    """Bu yıl [1 Ocak, kesim+1) ve geçen yıl aynı dönem."""
    last_day = cut if cut and cut.year == year else date(year, 12, 31)
    prev_last = _same_day_prev_year(last_day)
    return (date(year, 1, 1), last_day + timedelta(days=1)), (date(year - 1, 1, 1), prev_last + timedelta(days=1))


def marketplace_books(rows: list[dict[str, Any]], items: dict[str, dict[str, Any]], st: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        it = items.get(r["stok"])
        days = stock_days(it, st["salesMonths"])
        out.append({**r, "net": r["satisAdet"] - r["iadeAdet"], "iadeOrani": (r["iadeAdet"] / r["satisAdet"]) if r["satisAdet"] else None,
                    "stokLogo": it.get("stok_logo") if it else None, "kalanGun": round(days, 1) if days is not None else None,
                    "tukenmeRiski": days is not None and days < st["stockoutDays"],
                    "productKey": it.get("product_key") if it else None, "siteAktif": bool(it and it.get("tsoft_aktif"))})
    out.sort(key=lambda x: (-x["ciro"], x["stok"]))
    return out


# ------------------------------------------------------------------ içerik paketi


PACK_COLUMNS = [("ean", "Barkod (EAN-13)"), ("isbn", "ISBN"), ("stok", "Stok kodu"), ("ad", "Kitap adı"), ("urun_adi", "Ürün adı"),
                ("yazar", "Yazar"), ("cizer", "Çizer"), ("cevirmen", "Çevirmen"), ("sayfa", "Sayfa sayısı"), ("fiyat", "Fiyat (KDV dahil, CRM)"),
                ("kategori", "Kategori"), ("anahtar_kelime", "Anahtar kelimeler"), ("spot", "Spot"), ("arka_kapak", "Arka kapak metni"),
                ("gorsel", "Görsel adresi (site)"), ("site", "Sitedeki sayfa")]


def content_pack_rows(keys: list[str], crm: dict[str, dict[str, Any]], items: dict[str, dict[str, Any]], site_url: str) -> dict[str, Any]:
    """Seçilen kitapların platforma girilecek bilgileri. CRM'de kartı bulunmayan barkod `eksik` listesinde döner (sessizce düşmez)."""
    rows, missing = [], []
    for k in keys:
        c = crm.get(k)
        if not c:
            missing.append(k)
            continue
        it = items.get(k) or {}
        url = it.get("url")
        if url and not str(url).startswith("http") and site_url:
            url = f"{site_url.rstrip('/')}/{str(url).lstrip('/')}"
        rows.append({**{col: c.get(col) for col, _ in PACK_COLUMNS if col in c}, "ean": k, "gorsel": it.get("gorsel_url"),
                     "site": url})
    return {"rows": rows, "eksik": missing}


def content_pack_xlsx(pack: dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    wb = Workbook()
    ws = wb.active
    ws.title = "İçerik paketi"
    ws.append([label for _, label in PACK_COLUMNS])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in pack["rows"]:
        ws.append([r.get(col) for col, _ in PACK_COLUMNS])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for i, (col, _) in enumerate(PACK_COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = 60 if col in ("spot", "arka_kapak") else 22
    if pack["eksik"]:
        ws2 = wb.create_sheet("CRM'de bulunamayan")
        ws2.append(["Barkod"])
        for k in pack["eksik"]:
            ws2.append([k])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def content_pack_csv(pack: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow([label for _, label in PACK_COLUMNS])
    for r in pack["rows"]:
        w.writerow(["" if r.get(col) is None else r.get(col) for col, _ in PACK_COLUMNS])
    return buf.getvalue().encode("utf-8-sig")


# ------------------------------------------------------------------ Zeki AI: fiyat farkının olası nedeni


def reason_prompt(d: dict[str, Any], it: Optional[dict[str, Any]]) -> str:
    it = it or {}
    lines = [f"Kitap: {d.get('ad') or '-'}",
             f"CRM kapak fiyatı (KDV dahil): {_money(it.get('fiyat_crm'))}",
             f"Logo satış fiyat listesi: {_money(it.get('fiyat_logo'))}",
             f"Sitedeki fiyat: {_money(it.get('fiyat_tsoft'))}",
             f"Sitedeki indirimli fiyat: {_money(it.get('fiyat_tsoft_indirimli'))}",
             f"Logo stoğu: {_qty(it.get('stok_logo'))}"]
    return ("Bir yayınevinin sitesinde bir kitabın fiyatı iç kayıtlardan farklı görünüyor. Aşağıdaki değerlere bakarak "
            "farkın en olası nedenini seç. Sitede indirimli fiyat varsa ya da site fiyatı kayıttan düşükse kampanya olasıdır; "
            "site fiyatı kayıttan yüksekse ve Logo listesiyle uyuşuyorsa fiyat güncellemesi olasıdır; değerler arasında "
            "anlamsız sıçrama (ör. 10 kat) varsa veri hatası olasıdır. Emin değilsen «belirsiz» seç.\n\n" + "\n".join(lines))


def classify_reasons(engine: sa.engine.Engine, tenant: str, llm: Any, st: dict[str, Any], budget_sec: int) -> dict[str, Any]:
    """Açık fiyat farklarından neden önerisi olmayan ya da değerleri değişenler; süre bütçeli, sırayla. Model yoksa atlanır."""
    if llm is None or not hasattr(llm, "choose"):
        return {"skipped": "model yok"}
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(DIFFS).where(DIFFS.c.tenant_id == tenant, DIFFS.c.tur == "fiyat", DIFFS.c.durum.in_(("acik", "sonra")),
                                                sa.or_(DIFFS.c.neden_imza.is_(None), DIFFS.c.neden_imza != DIFFS.c.imza))
                         .order_by(DIFFS.c.etki.desc())).mappings().all()
    items = items_by_key(engine, tenant, [r["product_key"] for r in rows])
    started, done, unsure, failed = time.monotonic(), 0, 0, 0
    for r in rows:
        if time.monotonic() - started > budget_sec:
            break
        try:
            ch = llm.choose(reason_prompt(dict(r), items.get(r["product_key"])), REASONS)
        except Exception as e:  # noqa: BLE001 — model yok/zaman aşımı: sonraki geceye kalır
            log.info("eticaret neden sınıflaması: %s", e)
            failed += 1
            break
        ok = ch.choice and ch.choice != "belirsiz" and ch.confident(st["reasonMinP"], min_margin=st["reasonMinMargin"])
        label, prob = (ch.choice, ch.probability) if ok else ("belirsiz", ch.probability)
        unsure += 0 if ok else 1
        with engine.begin() as c:
            c.execute(DIFFS.update().where(DIFFS.c.id == r["id"]).values(neden_onerisi=label, neden_olasilik=prob, neden_imza=r["imza"]))
        done += 1
    return {"sinif": done, "belirsiz": unsure, "hata": failed, "kalan": max(0, len(rows) - done)}


# ------------------------------------------------------------------ bildirimler


def pending_alerts(engine: sa.engine.Engine, tenant: str, st: dict[str, Any]) -> list[dict[str, Any]]:
    """İlk kez görülen (ya da yeniden açılan) ve henüz bildirilmemiş, bildirim türündeki açık farklar."""
    if not st["alertKinds"]:
        return []
    with engine.connect() as c:
        rows = c.execute(sa.select(DIFFS).where(DIFFS.c.tenant_id == tenant, DIFFS.c.durum == "acik", DIFFS.c.bildirildi_at.is_(None),
                                                DIFFS.c.tur.in_(st["alertKinds"])).order_by(*_order())).mappings().all()
    return [_diff_out(r) for r in rows]


def mark_alerted(engine: sa.engine.Engine, tenant: str, ids: list[str], at: Optional[datetime] = None) -> None:
    at = at or now()
    with engine.begin() as c:
        for i in range(0, len(ids), 500):
            c.execute(DIFFS.update().where(DIFFS.c.tenant_id == tenant, DIFFS.c.id.in_(ids[i:i + 500])).values(bildirildi_at=at))


def alert_text(rows: list[dict[str, Any]], link: str) -> str:
    """Tek özet e-posta; bütün satırlar (tavan yok), türe göre gruplu."""
    parts = ["E-ticaret: yeni görülen farklar. Portal hiçbir sisteme yazmaz; düzeltmeyi T-soft panelinde siz yaparsınız.", ""]
    for tur, label in DIFF_KINDS.items():
        sub = [r for r in rows if r["tur"] == tur]
        if not sub:
            continue
        parts.append(f"{label} ({len(sub)})")
        parts += [f"- {r['ad'] or r['productKey']} [{r['productKey']}]: {r['aciklama']}" for r in sub]
        parts.append("")
    if link:
        parts.append(f"Farklar: {link}/e-ticaret/farklar")
    return "\n".join(parts)


def weekly_due(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], at: Optional[datetime] = None) -> bool:
    """Haftalık özet günü geldi mi (ayardaki gün, Pazartesi = 0) ve bu hafta gönderilmedi mi."""
    at = at or now()
    if not st["weeklyTo"]:
        return False
    local = at.astimezone(timezone(timedelta(hours=3)))
    if local.weekday() != st["weeklyDay"]:
        return False
    with engine.connect() as c:
        last = c.execute(sa.select(sa.func.max(RUNS.c.basladi)).where(RUNS.c.tenant_id == tenant, RUNS.c.tur == "haftalik",
                                                                      RUNS.c.hata.is_(None))).scalar()
    return not last or (at - _aware(last)) > timedelta(days=6)


def weekly_text(ov: dict[str, Any], markets: Optional[dict[str, Any]], risky: list[dict[str, Any]], link: str) -> str:
    g = ov["gostergeler"]
    h = ov["haftalik"]
    lines = ["E-ticaret haftalık özeti", "",
             f"Sitede satışta ürün: {_qty(g['siteAktif'])} · CRM'de «TSOFT Aktif»: {_qty(g['crmTsoftAktif'])}",
             f"Açık fark: {_qty(g['acikFark'])} (satışta olmaması gereken {_qty(g['satistaOlmamali'])}, eksik kart {_qty(g['eksikKart'])})",
             f"Son 7 günde kapanan: {_qty(h['kapanan'])}" + (f", ortalama kapanma {h['ortalamaKapanmaGun']} gün" if h["ortalamaKapanmaGun"] is not None else ""),
             ""]
    lines.append("Açık farklar türe göre:")
    lines += [f"- {DIFF_KINDS[k]}: {_qty(v)}" for k, v in ov["turSayilari"].items() if v]
    if markets and markets.get("cariler"):
        t = markets["toplam"]
        lines += ["", f"Pazar yeri carileri (Logo, {markets['donem']['bas']} – {markets['donem']['son']}; kesim {markets.get('kesim') or '—'}):",
                  f"Net ciro {_money(t['net'])}" + (f", geçen yılın aynı dönemine göre %{round(t['degisim'] * 100, 1)}" if t.get("degisim") is not None else "")]
        for a in markets["cariler"]:
            lines.append(f"- {a['unvan'] or a['kod']}: net {_money(a['net'])}, iade oranı "
                         + (f"%{round(a['iadeOrani'] * 100, 1)}" if a["iadeOrani"] is not None else "—"))
    if risky:
        lines += ["", "Pazar yerlerinde satan, stoğu tükenmek üzere olan kitaplar:"]
        lines += [f"- {r['ad'] or r['stok']} ({r['stok']}): stok {_qty(r['stokLogo'])}, yaklaşık {r['kalanGun']} gün" for r in risky]
    if link:
        lines += ["", f"Ekran: {link}/e-ticaret"]
    return "\n".join(lines)


def record_run(engine: sa.engine.Engine, tenant: str, tur: str, user: str, started: datetime, summary: Any, error: Optional[str]) -> None:
    with engine.begin() as c:
        c.execute(RUNS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, tur=tur, basladi=started, bitti=now(), baslatan=user,
                                       kaynak_ozet_json=_dump(summary), hata=(error or None) and error[:1000]))


# ------------------------------------------------------------------ gece okuması


#: Sorgu bilgisi: gece okumasında çalışan CRM/Logo/site sorgularının `semantic_query_origin` anahtarı.
KOKEN_OKUMA = "eticaret.okuma"


class Refresher:
    """Kaynak okuması ve fark hesabı. Aynı anda tek okuma (arka plan iş parçacığı ya da zamanlayıcı)."""

    def __init__(self, engine: Callable[[], sa.engine.Engine], tenant: Callable[[], str], logo_file: Callable[[], str],
                 crm_file: Callable[[], str], schema: Callable[[], str], settings: Callable[[], dict[str, Any]]) -> None:
        self.engine, self.tenant, self.logo_file, self.crm_file, self.schema, self.settings = engine, tenant, logo_file, crm_file, schema, settings
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None, "step": None}

    def running(self) -> bool:
        return self._lock.locked()

    def status(self) -> dict[str, Any]:
        return dict(self.state)

    def start(self, user: str) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        threading.Thread(target=self._run_locked, args=(user,), name="eticaret-refresh", daemon=True).start()
        return True

    def _run_locked(self, user: str) -> None:
        try:
            self._run(user)
        finally:
            self._lock.release()

    def run(self, user: str) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            return {"skipped": "başka bir okuma sürüyor"}
        try:
            return self._run(user)
        finally:
            self._lock.release()

    def _run(self, user: str) -> dict[str, Any]:
        from semantic_bridge import eticaret_sources as src
        from semantic_bridge import sorgu_yakala as Y
        from semantic_bridge.seo_geo import _image

        engine, tenant, st = self.engine(), self.tenant(), self.settings()
        ensure(engine)
        # Sorgu bilgisi: bu okumada koşan CRM/Logo sorguları ve site tablosu okuması «tabloyu dolduran asıl sorgu» olarak
        # saklanır (ekrandaki rakamın «i» penceresinde `origin`).
        q, token = Y.baslat(engine)
        started = now()
        self.state.update(running=True, startedAt=iso(started), finishedAt=None, error=None, step="site")
        summary: dict[str, Any] = {"kaynaklar": {}}
        sources = {"tsoft": False, "crm": False, "logo": False, "rights": False, "dr": False}
        error = None
        try:
            site = src.read_site(engine, tenant)
            sources["tsoft"] = bool(site["products"])
            sources["rights"] = bool(site["rights"])
            summary["kaynaklar"]["site"] = {"urun": len(site["products"]), "okundu": iso(site["tsoftAt"]),
                                            "hakKaydi": len(site["rights"]), "hakOkundu": iso(site["crmAt"])}
            if not sources["tsoft"]:
                raise EticaretError("Site ürünleri henüz okunmamış (SEO & GEO → T-soft eşitlemesi); farklar hesaplanmadı.", 409)
            crm_cards = stock = prices = sales = None
            cut = None
            self.state["step"] = "crm"
            try:
                crm_cards = src.read_crm_books(Y.izle(src.runner(self.crm_file()), "crm", Y.db_of(self.crm_file())), self.schema())
                sources["crm"] = True
                summary["kaynaklar"]["crm"] = {"kart": len(crm_cards), "tsoftAktif": sum(1 for c in crm_cards if c["tsoft"])}
            except Exception as e:  # noqa: BLE001 — okunamayan kaynak turu durdurmaz, türü hesaplanmaz
                summary["kaynaklar"]["crm"] = {"hata": str(e)[:300]}
            self.state["step"] = "logo"
            try:
                run = Y.izle(src.runner(self.logo_file()), "logo", Y.db_of(self.logo_file()))
                firms = src.firms_by_year(run)
                cut = src.read_data_end(run, firms)
                stock = src.read_stock(run, firms)
                prices = src.read_prices(run, firms, date.today())
                a, b = src.year_window(cut, st["salesMonths"])
                sales = src.read_item_sales(run, firms, a, b)
                sources["logo"] = True
                summary["kaynaklar"]["logo"] = {"kesim": cut.isoformat() if cut else None, "stokKodu": len(stock),
                                                "fiyat": len(prices), "satisPenceresi": [a.isoformat(), b.isoformat()]}
            except Exception as e:  # noqa: BLE001
                summary["kaynaklar"]["logo"] = {"hata": str(e)[:300]}
            # D&R kataloğu (M39, köprünün kendi tablosu): TİMAŞ grubu başlıkların son görüntüdeki fiyatı.
            self.state["step"] = "dr"
            dr_map: dict[str, dict[str, Any]] = {}
            try:
                from semantic_bridge import pazar_dagitim as PD

                got = PD.dr_timas(engine, tenant)
                dr_map = got["ean"]
                sources["dr"] = got["tarih"] is not None
                summary["kaynaklar"]["dr"] = {"goruntu": got["tarih"], "timasBaslik": len(dr_map)}
            except Exception as e:  # noqa: BLE001 — okunamazsa D&R fark türü bu turda hesaplanmaz (ve kapanmaz)
                summary["kaynaklar"]["dr"] = {"hata": str(e)[:300]}
            Y.bitir(token)
            Y.koken_yaz(engine, tenant, KOKEN_OKUMA, q, portal_tables=("semantic_seo_products", "semantic_seo_crm_books",
                                                                        "semantic_pazar_dagitim_titles"))
            self.state["step"] = "fark"
            site_url = ""
            try:
                from semantic_bridge import admin as admin_mod

                site_url = admin_mod.conf("SEO_SITE_URL")
            except Exception:  # noqa: BLE001
                pass
            items = build_items(site, crm_cards, stock, prices, sales, st, src.tsoft_values, lambda p: _image(p, site_url), cut)
            for key, it in items.items():
                it["dr"] = dr_map.get(key)
            result = apply_run(engine, tenant, items, st, sources, site["tsoftAt"])
            summary.update(result | {"events": len(result["events"])})
        except Exception as e:  # noqa: BLE001
            error = str(e)[:1000]
            log.warning("eticaret okuması başarısız: %s", error)
        finally:
            Y.bitir(token)
            summary["kaynakDurumu"] = sources
            record_run(engine, tenant, "okuma", user, started, summary, error)
            self.state.update(running=False, finishedAt=iso(now()), error=error, step=None)
        return {**summary, "hata": error}
