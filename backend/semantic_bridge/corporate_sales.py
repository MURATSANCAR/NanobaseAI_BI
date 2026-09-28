"""M32 B2B web sitesi ve kurumsal satış yönetimi: kurum listesi ve alım geçmişi, tema paketi oluşturucu, teklif (hacim
indirimi, marj, onay, belge), fırsat takibi, dönemsel hatırlatma, bayi B2B paneli.

**Kaynaklar** (`corporate_sales_sources`): Logo (faturalı satış, fatura başlığı, stok bakiyesi, `PRCLIST` fiyatı) ve CRM
(kurum kartı, temsilci, kitap kartı ve tema bağı, B2B portal sipariş sayısı). İkisi de yalnız okunur. Gece işi
(`run_due`) okumaları köprünün kendi tablolarına yazar; ekranlar bu tablolardan okur, «Verileri yenile» aynı okumayı başlatır.

**Yazma yok:** B2B sitesine (bayi sipariş portalı), CRM'e ve Logo'ya hiçbir şey gitmez. Teklif, fırsat, tema etiketi ve
hatırlatma köprünün `semantic_corp_*` tablolarındadır; kabul edilen teklif sipariş satırlarıyla Excel'e aktarılır, CRM'de
insan açar. Her yazma `semantic_audit`'e düşer (`corp_quote`, `corp_opportunity`, `corp_theme`, `corp_account`,
`corp_reminder`).

**Kurallar (model yok):**
- *Hacim indirimi:* `CORP_VOLUME_TIERS` ayarı (`100:10;300:15` = 100 adet ve üstü %10 …) varsa o; yoksa son 12 ayın kurum
  faturalarında (KURUM kanalı) aynı adet aralığındaki **gerçekleşen iskontonun medyanı** (1 − Σ LINENET ÷ Σ TOTAL). Aralıkta
  `CORP_VOLUME_MIN_N` faturadan az geçmiş varsa öneri yok (0) ve ekranda yazılır.
- *Onay:* teklifte herhangi bir satırın indirimi `CORP_DISCOUNT_APPROVAL_PCT`'yi (varsayılan %30 — analizdeki iş günü örneği)
  aşarsa ya da marj biliniyor ve `CORP_MARGIN_MIN_PCT`'nin (varsayılan %0: maliyetin altında satış) altındaysa teklif
  müdür onayına düşer. Onay `ozellik:kurumsal.teklif-onay` (açıkça verilir) ister; onaya gönderen onaylayamaz (409).
- *Marj:* birim maliyet `corporate_sales_sources.unit_costs`'tan (M9 bağlanınca oradan). Maliyeti bilinmeyen satır marja
  girmez; kapsam ekranda yazılır, hiç maliyet yoksa «maliyet bilinmiyor».
- *Paket önerisi:* aday = onaylı teması seçilenlerden biri olan, stoğu paket sayısına yeten, Logo'da bugün geçerli satış
  fiyatı olan kitap (yaş verilmişse yaş aralığı örtüşen). Sıra bu yılın net satış adedidir; her alternatif önceki
  alternatiflerde kullanılmamış kitaplarla, paket başı bütçeye sığacak biçimde açgözlü doldurulur.
- *Dönemsel hatırlatma:* bugünden `CORP_REMINDER_LEAD_DAYS` (45) gün içinde başlayan ay için, geçen yıl aynı ayda KURUM
  kanalında net alımı olan her kurum bir hatırlatma olur.
- *Sessiz bayi:* bayi kanalında (`CORP_DEALER_CHANNELS`) Logo verisinin bittiği güne göre son satış faturası `gun` günden
  eski ve önceki 12 ayda en az bir satış faturası olan cari. Değer sınıfı (A/B/C) son 12 ay net cirosunun %80/%95 birikimi.

**ZEKİ AI (LLM kapısından, `llm_for("kurumsal")`):** kurum unvanından segment önerisi, kitaba en uygun tek tema (CRM
temaları + `CORP_THEMES` + «Hiçbiri») ve kaybedilen fırsat nedeninin sınıfı kapalı küme seçimiyle (`QueuedLlm.choose`,
olasılık ve marj eşiği ayarda); teklif mektubu taslağı serbest metin. Rakam modelden gelmez; öneriler insan onayına kadar
«öneri» durumundadır.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import math
import re
import statistics
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import corporate_sales_sources as src

log = logging.getLogger("semantic.corporate")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()

ACCOUNTS = sa.Table(
    "semantic_corp_accounts", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("ref", sa.String(60), primary_key=True),          # Logo cari kodu; Logo'da yoksa "crm-<guid>"
    sa.Column("logo_code", sa.String(40)),
    sa.Column("logo_clientref", sa.Integer),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("unvan", sa.String(400)),
    sa.Column("il", sa.String(80)),
    sa.Column("kanal", sa.String(24)),
    sa.Column("crm_rol", sa.Integer),
    sa.Column("segment", sa.String(20)),
    sa.Column("segment_kaynak", sa.String(10)),                # crm | oneri | elle
    sa.Column("segment_olasilik", sa.Float),
    sa.Column("segment_by", sa.String(120)),
    sa.Column("segment_at", sa.DateTime(timezone=True)),
    sa.Column("segment_asked_at", sa.DateTime(timezone=True)),
    sa.Column("temsilci", sa.String(200)),
    sa.Column("temsilci_hesap", sa.String(120)),
    sa.Column("iskonto", sa.Float),                             # Logo CLCARD.DISCRATE
    sa.Column("eposta_izni", sa.Boolean),                       # CRM İYS e-posta izni ve DoNotEMail
    sa.Column("pasif", sa.Boolean, nullable=False, default=False),
    sa.Column("ilk_alim", sa.String(10)),
    sa.Column("son_alim", sa.String(10)),
    sa.Column("asof", sa.DateTime(timezone=True), nullable=False),
)
SALES = sa.Table(
    "semantic_corp_sales", _md,
    sa.Column("logo_code", sa.String(40), primary_key=True),
    sa.Column("year", sa.Integer, primary_key=True),
    sa.Column("month", sa.Integer, primary_key=True),
    sa.Column("ciro", sa.Float, nullable=False),
    sa.Column("adet", sa.Float, nullable=False),
    sa.Column("fatura", sa.Integer, nullable=False),
    sa.Column("son", sa.String(10)),
)
BOOKS = sa.Table(
    "semantic_corp_books", _md,
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("ad", sa.String(400)),
    sa.Column("yazar", sa.String(300)),
    sa.Column("yayinevi", sa.String(200)),
    sa.Column("kitaplik", sa.String(200)),
    sa.Column("turler", sa.String(400)),
    sa.Column("yaslar", sa.String(200)),
    sa.Column("hedef", sa.String(20)),
    sa.Column("yas_min", sa.Integer),
    sa.Column("yas_max", sa.Integer),
    sa.Column("ilk_yayin", sa.String(10)),
    sa.Column("ozet", sa.Text),
    sa.Column("stok", sa.Float, nullable=False, default=0.0),
    sa.Column("yil_adet", sa.Float, nullable=False, default=0.0),
    sa.Column("fiyat", sa.Float),                               # Logo PRCLIST (bugün geçerli satış listesi)
    sa.Column("fiyat_liste", sa.String(40)),
    sa.Column("fiyat_liste_sayisi", sa.Integer),
    sa.Column("fiyat_kdv_dahil", sa.Boolean),
    sa.Column("crm_fiyat", sa.Float),
    sa.Column("bayi_son", sa.Float, nullable=False, default=0.0),     # bayi kanalı son N gün net adet
    sa.Column("bayi_onceki", sa.Float, nullable=False, default=0.0),
    sa.Column("maliyet_logo", sa.Float),                        # yalnız CORP_COST_SOURCE=logo iken dolar
    sa.Column("maliyet_logo_tarih", sa.String(10)),
    sa.Column("in_logo", sa.Boolean, nullable=False, default=False),
    sa.Column("in_crm", sa.Boolean, nullable=False, default=False),
)
THEMES = sa.Table(
    "semantic_corp_themes", _md,
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("tema", sa.String(120), primary_key=True),
    sa.Column("kaynak", sa.String(10), nullable=False),         # crm | oneri | elle
    sa.Column("durum", sa.String(12), nullable=False),          # onerildi | onayli | reddedildi
    sa.Column("olasilik", sa.Float),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)
THEME_ASKED = sa.Table(
    "semantic_corp_theme_asked", _md,
    sa.Column("stok_kodu", sa.String(60), primary_key=True),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("sonuc", sa.String(400)),
)
OPPS = sa.Table(
    "semantic_corp_opportunities", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("account_ref", sa.String(60)),
    sa.Column("logo_code", sa.String(40)),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("kurum", sa.String(400), nullable=False),
    sa.Column("ad", sa.String(300), nullable=False),
    sa.Column("tema", sa.String(200)),
    sa.Column("asama", sa.String(12), nullable=False),
    sa.Column("deger", sa.Float),
    sa.Column("karar_tarihi", sa.String(10)),
    sa.Column("sahip", sa.String(120), nullable=False),
    sa.Column("sonraki_adim", sa.String(500)),
    sa.Column("sonraki_tarih", sa.String(10)),
    sa.Column("kaybetme_nedeni", sa.Text),
    sa.Column("kayip_sinif", sa.String(20)),
    sa.Column("kayip_sinif_kaynak", sa.String(10)),             # elle | oneri
    sa.Column("kaynak", sa.String(12), nullable=False),         # elle | hatirlatma
    sa.Column("hatirlatma_id", sa.String(32)),
    sa.Column("notlar", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.Column("closed_at", sa.DateTime(timezone=True)),
)
QUOTES = sa.Table(
    "semantic_corp_quotes", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("firsat_id", sa.String(32), nullable=False, index=True),
    sa.Column("surum", sa.Integer, nullable=False),
    sa.Column("durum", sa.String(12), nullable=False),          # taslak | onayda | hazir | gonderildi | kabul | ret
    sa.Column("kalemler_json", sa.Text, nullable=False),
    sa.Column("paket_adet", sa.Integer),
    sa.Column("toplam_liste", sa.Float, nullable=False, default=0.0),
    sa.Column("toplam_net", sa.Float, nullable=False, default=0.0),
    sa.Column("toplam_maliyet", sa.Float),
    sa.Column("marj", sa.Float),
    sa.Column("maliyet_kapsami", sa.Float),
    sa.Column("onay_gerekli", sa.Boolean, nullable=False, default=False),
    sa.Column("onay_nedenleri_json", sa.Text),
    sa.Column("mektup", sa.Text),
    sa.Column("notlar", sa.Text),
    sa.Column("gecerlilik_gun", sa.Integer),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("gonderim_at", sa.DateTime(timezone=True)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_at", sa.DateTime(timezone=True)),
    sa.Column("onay_notu", sa.Text),
    sa.Column("gonderildi_at", sa.DateTime(timezone=True)),
    sa.Column("sonuc_neden", sa.Text),
    sa.Column("sonuc_at", sa.DateTime(timezone=True)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
REMINDERS = sa.Table(
    "semantic_corp_reminders", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("logo_code", sa.String(40), nullable=False),
    sa.Column("unvan", sa.String(400)),
    sa.Column("donem_ayi", sa.String(7), nullable=False),       # YYYY-MM (hatırlatılan ay)
    sa.Column("gecen_yil_tutar", sa.Float, nullable=False),
    sa.Column("gecen_yil_adet", sa.Float),
    sa.Column("durum", sa.String(10), nullable=False),          # acik | firsat | kapandi
    sa.Column("firsat_id", sa.String(32)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("tenant_id", "logo_code", "donem_ayi", name="uq_corp_reminder"),
)
DEALERS = sa.Table(
    "semantic_corp_dealers", _md,
    sa.Column("logo_code", sa.String(40), primary_key=True),
    sa.Column("logo_clientref", sa.Integer),
    sa.Column("unvan", sa.String(400)),
    sa.Column("kanal", sa.String(24)),
    sa.Column("il", sa.String(80)),
    sa.Column("son_fatura", sa.String(10)),
    sa.Column("fatura_12ay", sa.Integer, nullable=False),
    sa.Column("ciro_12ay", sa.Float, nullable=False),
    sa.Column("sinif", sa.String(1)),
    sa.Column("b2b_siparis", sa.Integer),                       # CRM, son CORP_B2B_DAYS gün
    sa.Column("b2b_kullanici", sa.Integer),                     # CRM, etkin web kullanıcısı sayısı
)
META = sa.Table(
    "semantic_corp_meta", _md,
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

STAGES = {"aday": "Aday", "gorusuldu": "Görüşüldü", "teklif": "Teklif", "karar": "Karar", "kazanildi": "Kazanıldı",
          "kaybedildi": "Kaybedildi"}
OPEN_STAGES = ("aday", "gorusuldu", "teklif", "karar")
SEGMENTS = {"sirket": "Şirket", "kamu": "Kamu kurumu", "vakif": "Vakıf, dernek, STK", "okul": "Okul", "universite": "Üniversite",
            "diger": "Diğer"}
SEGMENT_SOURCES = {"crm": "CRM kurum rolü", "oneri": "ZEKİ AI önerisi", "elle": "Elle"}
LOSS = {"fiyat": "Fiyat", "butce": "Bütçe yok ya da ertelendi", "zamanlama": "Zamanlama", "rakip": "Rakip tercih edildi",
        "uygunluk": "Kitap seçimi uymadı", "iletisim": "Yanıt alınamadı", "diger": "Diğer"}
QUOTE_STATUS = {"taslak": "Taslak", "onayda": "Onay bekliyor", "hazir": "Gönderilebilir", "gonderildi": "Gönderildi",
                "kabul": "Kabul edildi", "ret": "Reddedildi"}
THEME_STATUS = {"onerildi": "Öneri", "onayli": "Onaylı", "reddedildi": "Reddedildi"}
REMINDER_STATUS = {"acik": "Açık", "firsat": "Fırsat açıldı", "kapandi": "Kapandı"}
PAGE_SIZE = 100

DEFAULTS: dict[str, str] = {
    "CORP_CHANNEL": "KURUM",
    "CORP_DEALER_CHANNELS": "BAYI,KITAPCI",
    "CORP_HISTORY_YEARS": "3",
    "CORP_DISCOUNT_APPROVAL_PCT": "30",
    "CORP_MARGIN_MIN_PCT": "0",
    "CORP_VOLUME_TIERS": "",
    "CORP_VOLUME_BUCKETS": "1,100,300,1000",
    "CORP_VOLUME_MIN_N": "5",
    "CORP_REMINDER_LEAD_DAYS": "45",
    "CORP_DEALER_SILENT_DAYS": "60",
    "CORP_B2B_DAYS": "90",
    "CORP_HIGHLIGHT_DAYS": "90",
    "CORP_COST_SOURCE": "m9",
    "CORP_THEMES": "Liderlik ve yönetim;Kişisel gelişim;İş hayatı;Yeni çalışan;Çocuk kütüphanesi;Aile;Değerler eğitimi",
    "CORP_PACKAGE_ALTERNATIVES": "4",
    "CORP_QUOTE_VALID_DAYS": "30",
    "CORP_APPROVAL_RECIPIENTS": "",
    "CORP_B2B_REPORT_TO": "",
    "CORP_LLM_BUDGET_SEC": "1200",
    "CORP_LLM_MIN_PROB": "0.70",
    "CORP_LLM_MIN_MARGIN": "0.30",
    "CORP_COMPANY_NAME": "Timaş Yayınları",
}

_ready: set[int] = set()
_lock = threading.Lock()


class CorporateError(ValueError):
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
        raise CorporateError(f"{label} boş olamaz.")
    try:
        n = float(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) and "," in v else float(v)
    except (TypeError, ValueError):
        raise CorporateError(f"{label} sayı olmalı.") from None
    if math.isnan(n) or math.isinf(n):
        raise CorporateError(f"{label} sayı olmalı.")
    if minimum is not None and n < minimum:
        raise CorporateError(f"{label} {minimum:g} değerinden küçük olamaz.")
    if maximum is not None and n > maximum:
        raise CorporateError(f"{label} {maximum:g} değerinden büyük olamaz.")
    return n


def _day_in(v: Any, label: str) -> Optional[str]:
    if v is None or v == "":
        return None
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise CorporateError(f"{label} YYYY-AA-GG biçiminde olmalı.") from None


def fold(s: Any) -> str:
    t = str(s or "").translate(str.maketrans("İIıŞşĞğÜüÖöÇç", "iiissgguuoocc")).lower()
    return re.sub(r"\s+", " ", t).strip()


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

    buckets = sorted({int(x) for x in re.findall(r"\d+", g("CORP_VOLUME_BUCKETS")) if int(x) > 0}) or [1]
    if buckets[0] != 1:
        buckets = [1] + buckets
    return {
        "channel": g("CORP_CHANNEL").strip() or "KURUM",
        "dealerChannels": [c.strip() for c in g("CORP_DEALER_CHANNELS").replace(";", ",").split(",") if c.strip()],
        "historyYears": gi("CORP_HISTORY_YEARS", 2, 12),
        "discountApprovalPct": gf("CORP_DISCOUNT_APPROVAL_PCT"),
        "marginMinPct": gf("CORP_MARGIN_MIN_PCT"),
        "volumeTiers": parse_tiers(g("CORP_VOLUME_TIERS")),
        "volumeBuckets": buckets,
        "volumeMinN": gi("CORP_VOLUME_MIN_N", 1, 1000),
        "reminderLeadDays": gi("CORP_REMINDER_LEAD_DAYS", 0, 365),
        "silentDays": gi("CORP_DEALER_SILENT_DAYS", 1, 730),
        "b2bDays": gi("CORP_B2B_DAYS", 1, 730),
        "highlightDays": gi("CORP_HIGHLIGHT_DAYS", 7, 365),
        "costSource": (g("CORP_COST_SOURCE").strip().lower() or "m9"),
        "themes": [t.strip() for t in re.split(r"[;\n]", g("CORP_THEMES")) if t.strip()],
        "alternatives": gi("CORP_PACKAGE_ALTERNATIVES", 1, 12),
        "quoteValidDays": gi("CORP_QUOTE_VALID_DAYS", 1, 365),
        "approvalRecipients": _emails(g("CORP_APPROVAL_RECIPIENTS")),
        "b2bReportTo": _emails(g("CORP_B2B_REPORT_TO")),
        "llmBudgetSec": gi("CORP_LLM_BUDGET_SEC", 0, 6 * 3600),
        "llmMinProb": gf("CORP_LLM_MIN_PROB") or 0.70,
        "llmMinMargin": gf("CORP_LLM_MIN_MARGIN") or 0.0,
        "company": g("CORP_COMPANY_NAME").strip() or DEFAULTS["CORP_COMPANY_NAME"],
    }


def _emails(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").replace(";", ",").split(",") if "@" in x]


def parse_tiers(raw: str) -> list[tuple[int, float]]:
    """«100:10;300:15» → [(100, 0.10), (300, 0.15)], adet eşiğine göre artan."""
    out = []
    for part in re.split(r"[;,\s]+", raw or ""):
        m = re.match(r"^(\d+)\s*[:=]\s*(\d+(?:[.,]\d+)?)%?$", part.strip())
        if m:
            out.append((int(m.group(1)), float(m.group(2).replace(",", ".")) / 100.0))
    return sorted(out)


# ------------------------------------------------------------------------------------------ meta


def meta_stmt(key: str) -> sa.Select:
    """Okuma meta kaydı (data_end, volume, dealers, refresh, crm_themes, sorgular): uçta çalışan ve sorgu bilgisinde
    gösterilen ifade."""
    return sa.select(META).where(META.c.key == key)


def meta_get(engine: sa.engine.Engine, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(meta_stmt(key)).first()
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


# ------------------------------------------------------------------------------------------ hacim indirimi


def measured_discounts(invoices: list[dict[str, float]], buckets: list[int], min_n: int) -> list[dict[str, Any]]:
    """Fatura başına gerçekleşen iskonto (1 − net/brüt), adet aralıklarına göre medyan."""
    edges = list(buckets)
    out = []
    for i, lo in enumerate(edges):
        hi = edges[i + 1] if i + 1 < len(edges) else None
        rates = [max(0.0, min(1.0, 1 - inv["net"] / inv["brut"])) for inv in invoices
                 if inv["brut"] > 0 and inv["adet"] >= lo and (hi is None or inv["adet"] < hi)]
        med = statistics.median(rates) if len(rates) >= min_n else None
        out.append({"min": lo, "max": (hi - 1) if hi else None, "n": len(rates),
                    "indirim": round(med, 4) if med is not None else None})
    return out


def volume_discount(qty: float, st: dict[str, Any], measured: list[dict[str, Any]]) -> dict[str, Any]:
    """Toplam adet için önerilen indirim ve dayanağı."""
    tiers = st.get("volumeTiers") or []
    if tiers:
        rate, basis = 0.0, None
        for lo, r in tiers:
            if qty >= lo:
                rate, basis = r, lo
        return {"indirim": rate, "kaynak": "ayar", "aciklama": (f"{basis} adet ve üstü için ayardaki oran" if basis
                                                                else "Bu adet ayardaki ilk eşiğin altında")}
    for b in measured or []:
        if qty >= b["min"] and (b["max"] is None or qty <= b["max"]):
            rng = f"{b['min']}–{b['max']}" if b["max"] is not None else f"{b['min']} ve üstü"
            if b["indirim"] is None:
                return {"indirim": 0.0, "kaynak": "gecmis-yetersiz", "n": b["n"],
                        "aciklama": f"{rng} adetlik kurum faturası geçmişi yetersiz ({b['n']} fatura); indirim önerilmedi"}
            return {"indirim": b["indirim"], "kaynak": "gecmis", "n": b["n"],
                    "aciklama": f"Son 12 ayda {rng} adetlik {b['n']} kurum faturasında gerçekleşen iskontonun medyanı"}
    return {"indirim": 0.0, "kaynak": "yok", "aciklama": "Kurum faturası geçmişi henüz okunmadı"}


# ------------------------------------------------------------------------------------------ kitaplar ve temalar


def _book_dict(r: Any, themes: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    return {"stokKodu": r.stok_kodu, "ad": r.ad, "yazar": r.yazar, "yayinevi": r.yayinevi, "kitaplik": r.kitaplik,
            "turler": r.turler, "yaslar": r.yaslar, "hedef": r.hedef, "yasMin": r.yas_min, "yasMax": r.yas_max,
            "ilkYayin": r.ilk_yayin, "stok": r.stok, "yilAdet": r.yil_adet, "fiyat": r.fiyat, "fiyatListe": r.fiyat_liste,
            "fiyatListeSayisi": r.fiyat_liste_sayisi, "fiyatKdvDahil": r.fiyat_kdv_dahil, "crmFiyat": r.crm_fiyat,
            "bayiSon": r.bayi_son, "bayiOnceki": r.bayi_onceki, "temalar": themes or []}


def themes_by_book(engine: sa.engine.Engine, codes: Optional[Iterable[str]] = None) -> dict[str, list[dict[str, Any]]]:
    if codes is not None:
        codes = list(codes)
        if not codes:
            return {}
    q = themes_stmt(codes)
    out: dict[str, list[dict[str, Any]]] = {}
    with engine.connect() as c:
        for r in c.execute(q).all():
            out.setdefault(r.stok_kodu, []).append(
                {"tema": r.tema, "kaynak": r.kaynak, "durum": r.durum, "olasilik": r.olasilik, "onaylayan": r.onaylayan,
                 "zaman": _iso(r.zaman)})
    return out


def vocabulary(engine: sa.engine.Engine, st: dict[str, Any]) -> list[str]:
    """Tema kapalı kümesi: CRM temaları (okumada saklanır) + CORP_THEMES."""
    crm = meta_get(engine, "crm_themes").get("names") or []
    seen, out = set(), []
    for t in list(st.get("themes") or []) + list(crm):
        k = fold(t)
        if k and k not in seen:
            seen.add(k)
            out.append(t)
    return out


def match_theme(name: Any, vocab: list[str]) -> Optional[str]:
    k = fold(name)
    for t in vocab:
        if fold(t) == k:
            return t
    return None


def books_stmt(codes: Optional[Iterable[str]] = None) -> sa.Select:
    """Kitap kartları (gece okumasının yazdığı semantic_corp_books); `codes` verilirse yalnız o stok kodları."""
    q = sa.select(BOOKS)
    return q if codes is None else q.where(BOOKS.c.stok_kodu.in_(list(codes)))


def themes_stmt(codes: Optional[Iterable[str]] = None) -> sa.Select:
    """Kitap × tema etiketleri (CRM bağı, Zeki AI önerisi, elle); `codes` verilirse yalnız o kitaplar."""
    q = sa.select(THEMES)
    return q if codes is None else q.where(THEMES.c.stok_kodu.in_(list(codes)))


def theme_codes_stmt(durum: str = "", q: str = "", tema: str = "") -> sa.Select:
    """Tema sekmesi: seçilen durumda (ve temada) etiketi olan kitapların stok kodları (arama kitap kartında)."""
    cond = []
    if durum:
        cond.append(THEMES.c.durum == durum)
    if tema:
        cond.append(THEMES.c.tema == tema)
    base = sa.select(THEMES.c.stok_kodu).where(*cond).distinct()
    if q:
        like = f"%{q.strip()}%"
        base = base.join(BOOKS, BOOKS.c.stok_kodu == THEMES.c.stok_kodu).where(
            sa.or_(BOOKS.c.ad.ilike(like), BOOKS.c.stok_kodu.ilike(like), BOOKS.c.yazar.ilike(like)))
    return base


def theme_counts_stmt() -> sa.Select:
    """Tema etiketi sayıları, duruma göre (öneri / onaylı / reddedildi)."""
    return sa.select(THEMES.c.durum, sa.func.count().label("sayi")).group_by(THEMES.c.durum)


def list_themes(engine: sa.engine.Engine, st: dict[str, Any], *, durum: str = "onerildi", q: str = "", tema: str = "",
                page: int = 0) -> dict[str, Any]:
    if durum and durum not in THEME_STATUS:
        raise CorporateError("Geçersiz durum.")
    with engine.connect() as c:
        codes = sorted(r[0] for r in c.execute(theme_codes_stmt(durum, q, tema)).all())
        total = len(codes)
        page_codes = codes[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
        books = {r.stok_kodu: r for r in c.execute(books_stmt(page_codes)).all()} if page_codes else {}
        counts = {k: v for k, v in c.execute(theme_counts_stmt()).all()}
    th = themes_by_book(engine, page_codes)
    items = []
    for code in page_codes:
        b = books.get(code)
        items.append(_book_dict(b, th.get(code)) if b else {"stokKodu": code, "ad": None, "temalar": th.get(code, [])})
    return {"items": items, "total": total, "page": page, "pageSize": PAGE_SIZE, "counts": counts,
            "vocabulary": vocabulary(engine, st)}


def set_theme(engine: sa.engine.Engine, st: dict[str, Any], user: str, code: str, tema: Any, decision: str) -> dict[str, Any]:
    """decision: onayla | reddet | ekle | kaldir."""
    vocab = vocabulary(engine, st)
    t = match_theme(tema, vocab)
    if not t:
        raise CorporateError("Tema kapalı listede yok; önce ayarlardaki tema listesine eklenmeli.")
    now = _now()
    with engine.begin() as c:
        if not c.execute(sa.select(BOOKS.c.stok_kodu).where(BOOKS.c.stok_kodu == code)).first():
            raise CorporateError("Kitap bulunamadı.", 404)
        row = c.execute(sa.select(THEMES).where(THEMES.c.stok_kodu == code, THEMES.c.tema == t)).first()
        if decision in ("onayla", "reddet"):
            if not row:
                raise CorporateError("Bu kitapta böyle bir tema önerisi yok.", 404)
            if row.kaynak == "crm":
                raise CorporateError("CRM'deki tema bağı burada değiştirilmez; CRM'de düzeltilir.", 409)
            c.execute(THEMES.update().where(THEMES.c.stok_kodu == code, THEMES.c.tema == t).values(
                durum="onayli" if decision == "onayla" else "reddedildi", onaylayan=user, zaman=now))
        elif decision == "ekle":
            if row and row.kaynak == "crm":
                raise CorporateError("Bu tema CRM'de zaten bağlı.", 409)
            if row:
                c.execute(THEMES.update().where(THEMES.c.stok_kodu == code, THEMES.c.tema == t).values(
                    kaynak="elle", durum="onayli", onaylayan=user, zaman=now, olasilik=None))
            else:
                c.execute(THEMES.insert().values(stok_kodu=code, tema=t, kaynak="elle", durum="onayli", onaylayan=user, zaman=now))
        elif decision == "kaldir":
            if not row:
                raise CorporateError("Bu kitapta böyle bir tema yok.", 404)
            if row.kaynak == "crm":
                raise CorporateError("CRM'deki tema bağı burada kaldırılmaz; CRM'de düzeltilir.", 409)
            c.execute(THEMES.delete().where(THEMES.c.stok_kodu == code, THEMES.c.tema == t))
        else:
            raise CorporateError("Geçersiz karar.")
    return {"stokKodu": code, "tema": t, "karar": decision, "temalar": themes_by_book(engine, [code]).get(code, [])}


def book_search_stmts(q: str, page: int = 0) -> tuple[sa.Select, sa.Select]:
    """Teklife kitap arama: (toplam sayım, sayfa satırları) ifadeleri — uç ve sorgu bilgisi aynı ifadeyi kullanır."""
    like = f"%{(q or '').strip()}%"
    cond = sa.or_(BOOKS.c.ad.ilike(like), BOOKS.c.stok_kodu.ilike(like), BOOKS.c.yazar.ilike(like))
    total = sa.select(sa.func.count().label("sayi")).select_from(BOOKS).where(cond)
    rows = (sa.select(BOOKS).where(cond).order_by(BOOKS.c.yil_adet.desc(), BOOKS.c.stok_kodu)
            .offset(max(0, page) * PAGE_SIZE).limit(PAGE_SIZE))
    return total, rows


def find_books(engine: sa.engine.Engine, q: str, *, limit_page: int = 0) -> dict[str, Any]:
    """Teklife kitap eklemek için arama (ad, stok kodu, yazar)."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"items": [], "total": 0}
    total_stmt, rows_stmt = book_search_stmts(q, limit_page)
    with engine.connect() as c:
        total = c.execute(total_stmt).scalar() or 0
        rows = c.execute(rows_stmt).all()
    th = themes_by_book(engine, [r.stok_kodu for r in rows])
    return {"items": [_book_dict(r, th.get(r.stok_kodu)) for r in rows], "total": total, "page": limit_page,
            "pageSize": PAGE_SIZE}


# ------------------------------------------------------------------------------------------ maliyet ve teklif hesabı


def logo_costs_stmt(codes: Iterable[str]) -> sa.Select:
    """CORP_COST_SOURCE=logo: gece okumasında kitap kartına yazılan Logo son maliyeti (tahmini)."""
    return (sa.select(BOOKS.c.stok_kodu, BOOKS.c.maliyet_logo, BOOKS.c.maliyet_logo_tarih)
            .where(BOOKS.c.stok_kodu.in_(list(codes))))


def costs_for(engine: sa.engine.Engine, st: dict[str, Any], codes: Iterable[str]) -> dict[str, dict[str, Any]]:
    codes = list(dict.fromkeys(codes))
    logo = None
    if st.get("costSource") == "logo" and codes:
        with engine.connect() as c:
            logo = {r.stok_kodu: {"birim": r.maliyet_logo, "tarih": r.maliyet_logo_tarih}
                    for r in c.execute(logo_costs_stmt(codes)).all() if r.maliyet_logo}
    return src.unit_costs(codes, st.get("costSource") or "m9", logo)


def price_lines(engine: sa.engine.Engine, st: dict[str, Any], items: list[dict[str, Any]], default_discount: float) -> list[dict[str, Any]]:
    """Gelen kalemleri kitap kartıyla doldurur: ad, liste fiyatı, stok, maliyet. Fiyat elle verilmişse o kullanılır."""
    if not isinstance(items, list) or not items:
        raise CorporateError("Teklifte en az bir kitap olmalı.")
    codes = []
    for it in items:
        code = _text((it or {}).get("stok") or (it or {}).get("stokKodu"), 60)
        if not code:
            raise CorporateError("Kalemde stok kodu yok.")
        codes.append(code)
    if len(set(codes)) != len(codes):
        raise CorporateError("Aynı kitap teklifte iki kez var; adedi tek satırda artırın.")
    with engine.connect() as c:
        books = {r.stok_kodu: r for r in c.execute(books_stmt(codes)).all()}
    costs = costs_for(engine, st, codes)
    out = []
    for it, code in zip(items, codes):
        b = books.get(code)
        if b is None:
            raise CorporateError(f"{code} kodlu kitap kitap listesinde yok (veriler yenilenmemiş olabilir).")
        adet = _num(it.get("adet"), f"{code} adedi", minimum=1)
        disc = _num(it.get("indirim"), f"{code} indirimi", allow_none=True, minimum=0, maximum=100)
        disc = default_discount if disc is None else disc / 100.0
        manual = _num(it.get("listeFiyati"), f"{code} liste fiyatı", allow_none=True, minimum=0)
        price = manual if manual is not None else b.fiyat
        price_src = "elle" if manual is not None else ("logo" if b.fiyat else None)
        if price is None and b.crm_fiyat:
            price, price_src = b.crm_fiyat, "crm"
        if not price:
            raise CorporateError(f"{b.ad or code}: geçerli satış fiyatı yok; liste fiyatını elle girin.")
        cost = costs.get(code) or {"birim": None, "kaynak": "bilinmiyor", "tahmini": False, "tarih": None}
        net_unit = round(price * (1 - disc), 4)
        out.append({"stok": code, "ad": b.ad, "yazar": b.yazar, "adet": int(adet), "listeFiyati": round(float(price), 4),
                    "fiyatKaynak": price_src, "fiyatListe": b.fiyat_liste if price_src == "logo" else None,
                    "kdvDahil": bool(b.fiyat_kdv_dahil) if price_src == "logo" else None,
                    "indirim": round(disc, 4), "netBirim": net_unit, "netTutar": round(net_unit * adet, 2),
                    "listeTutar": round(price * adet, 2), "stokMiktar": b.stok, "stokYetersiz": (b.stok or 0) < adet,
                    "maliyetBirim": cost.get("birim"), "maliyetKaynak": cost.get("kaynak"), "maliyetTahmini": cost.get("tahmini"),
                    "maliyetTarih": cost.get("tarih")})
    return out


def quote_totals(lines: list[dict[str, Any]], st: dict[str, Any]) -> dict[str, Any]:
    liste = sum(l["listeTutar"] for l in lines)
    net = sum(l["netTutar"] for l in lines)
    costed = [l for l in lines if l.get("maliyetBirim")]
    costed_net = sum(l["netTutar"] for l in costed)
    cost = sum(l["maliyetBirim"] * l["adet"] for l in costed)
    margin = (costed_net - cost) / costed_net if costed and costed_net > 0 else None
    coverage = (costed_net / net) if net > 0 else None
    reasons = []
    lim = st.get("discountApprovalPct")
    if lim is not None:
        over = [l for l in lines if l["indirim"] * 100 > lim + 1e-9]
        if over:
            top = max(l["indirim"] for l in over)
            reasons.append({"kod": "indirim", "metin": f"İndirim %{_pct(top)} — onay eşiği %{_pct(lim / 100)}"
                                                        f" ({len(over)} kalem)"})
    mmin = st.get("marginMinPct")
    if margin is not None and mmin is not None and margin * 100 < mmin - 1e-9:
        reasons.append({"kod": "marj", "metin": f"Marj %{_pct(margin)} — alt sınır %{_pct(mmin / 100)}"})
    qty = sum(l["adet"] for l in lines)
    return {"toplamListe": round(liste, 2), "toplamNet": round(net, 2), "toplamMaliyet": round(cost, 2) if costed else None,
            "marj": round(margin, 4) if margin is not None else None,
            "maliyetKapsami": round(coverage, 4) if coverage is not None else None,
            "indirimOrani": round(1 - net / liste, 4) if liste > 0 else None, "adet": qty, "onayGerekli": bool(reasons),
            "onayNedenleri": reasons, "stokUyarisi": [l["stok"] for l in lines if l.get("stokYetersiz")]}


def _pct(v: float) -> str:
    s = f"{v * 100:.1f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


# ------------------------------------------------------------------------------------------ paket önerisi


def approved_themes_stmt() -> sa.Select:
    """Paket önerisi: onaylı tema etiketleri (CRM bağı ya da onaylanmış öneri/elle); temaya uyum Türkçe harf katlamasıyla
    uçta süzülür."""
    return sa.select(THEMES.c.stok_kodu, THEMES.c.tema, THEMES.c.kaynak).where(THEMES.c.durum == "onayli")


def approved_books_stmt() -> sa.Select:
    """Paket önerisi: onaylı en az bir tema etiketi olan kitapların kartı (stok, fiyat, bu yıl adet, yaş)."""
    return sa.select(BOOKS).where(BOOKS.c.stok_kodu.in_(sa.select(THEMES.c.stok_kodu).where(THEMES.c.durum == "onayli")))


def suggest_packages(engine: sa.engine.Engine, st: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    vocab = vocabulary(engine, st)
    raw = body.get("temalar") if isinstance(body.get("temalar"), list) else ([body["tema"]] if body.get("tema") else [])
    themes = [t for t in (match_theme(x, vocab) for x in raw) if t]
    if not themes:
        raise CorporateError("En az bir tema seçin.")
    kisi = int(_num(body.get("kisi") or body.get("adet"), "Paket sayısı", minimum=1, maximum=1_000_000))
    per = int(_num(body.get("kitapSayisi") or 1, "Paketteki kitap sayısı", minimum=1, maximum=100))
    budget = _num(body.get("butce"), "Bütçe", allow_none=True, minimum=0)
    per_budget = None
    if budget:
        per_budget = budget if (body.get("butceTuru") or "toplam") == "kisi" else budget / kisi
    yas_min = _num(body.get("yasMin"), "En küçük yaş", allow_none=True, minimum=0, maximum=99)
    yas_max = _num(body.get("yasMax"), "En büyük yaş", allow_none=True, minimum=0, maximum=99)
    n_alt = int(_num(body.get("alternatif") or st.get("alternatives") or 4, "Alternatif sayısı", minimum=1, maximum=12))
    override = _num(body.get("indirim"), "İndirim", allow_none=True, minimum=0, maximum=100)
    measured = meta_get(engine, "volume").get("buckets") or []
    vd = volume_discount(kisi * per, st, measured)
    disc = override / 100.0 if override is not None else float(vd["indirim"] or 0.0)

    theme_keys = {fold(t) for t in themes}
    with engine.connect() as c:
        rows = c.execute(approved_themes_stmt()).all()
        tagged: dict[str, list[str]] = {}
        for r in rows:
            if fold(r.tema) in theme_keys:
                tagged.setdefault(r.stok_kodu, []).append(f"{r.tema} ({'CRM' if r.kaynak == 'crm' else 'onaylı'})")
        books = {r.stok_kodu: r for r in c.execute(approved_books_stmt()).all() if r.stok_kodu in tagged} if tagged else {}
    dropped = {"stokYetersiz": 0, "fiyatYok": 0, "yasUymuyor": 0}
    cands = []
    for code, tags in tagged.items():
        b = books.get(code)
        if b is None:
            continue
        if (b.stok or 0) < kisi:
            dropped["stokYetersiz"] += 1
            continue
        if not b.fiyat:
            dropped["fiyatYok"] += 1
            continue
        if yas_min is not None or yas_max is not None:
            lo, hi = b.yas_min, b.yas_max
            if lo is None and hi is None:
                dropped["yasUymuyor"] += 1
                continue
            lo = lo if lo is not None else 0
            hi = hi if hi is not None else 99
            if (yas_max is not None and lo > yas_max) or (yas_min is not None and hi < yas_min):
                dropped["yasUymuyor"] += 1
                continue
        cands.append((b, tags))
    cands.sort(key=lambda x: (-(x[0].yil_adet or 0), x[0].stok_kodu))
    net = {b.stok_kodu: b.fiyat * (1 - disc) for b, _ in cands}

    used: set[str] = set()
    alts = []
    for i in range(n_alt):
        pool = [x for x in cands if x[0].stok_kodu not in used] or []
        if len(pool) < per:
            pool = pool + [x for x in cands if x[0].stok_kodu in used]  # yeni kitap kalmadıysa kullanılanlar da girer
        picked: list[tuple[Any, list[str]]] = []
        taken: set[str] = set()
        left = per_budget
        cheap = sorted((net[x[0].stok_kodu], x[0].stok_kodu) for x in pool)
        for b, tags in pool:
            if len(picked) == per:
                break
            if b.stok_kodu in taken:
                continue
            price = net[b.stok_kodu]
            if left is not None:
                # Kalan kitaplar en ucuz adaylarla bile bütçeye sığmalı.
                need = per - len(picked) - 1
                floor, n = 0.0, 0
                for p_, code_ in cheap:
                    if n >= need:
                        break
                    if code_ == b.stok_kodu or code_ in taken:
                        continue
                    floor += p_
                    n += 1
                if price + floor > left + 1e-6:
                    continue
                left -= price
            picked.append((b, tags))
            taken.add(b.stok_kodu)
        if not picked:
            break
        key = tuple(sorted(p[0].stok_kodu for p in picked))
        if any(tuple(sorted(l["stok"] for l in a["kalemler"])) == key for a in alts):
            break
        used.update(key)
        items = [{"stok": b.stok_kodu, "adet": kisi, "indirim": disc * 100} for b, _ in picked]
        lines = price_lines(engine, st, items, disc)
        why = {b.stok_kodu: tags for b, tags in picked}
        for l in lines:
            b = books[l["stok"]]
            l["gerekce"] = (f"Tema: {', '.join(why[l['stok']])} · stok {_int(b.stok)} · bu yıl {_int(b.yil_adet)} adet satıldı")
        tot = quote_totals(lines, st)
        pkg_net = sum(l["netBirim"] for l in lines)
        alts.append({"no": len(alts) + 1, "kalemler": lines, "paketNet": round(pkg_net, 2), "paketListe": round(sum(l["listeFiyati"] for l in lines), 2),
                     "eksik": per - len(lines), "butceyeUygun": per_budget is None or pkg_net <= per_budget + 1e-6, **tot})
    return {"temalar": themes, "kisi": kisi, "kitapSayisi": per, "paketBasiButce": round(per_budget, 2) if per_budget else None,
            "indirim": disc, "indirimDayanak": vd if override is None else {"indirim": disc, "kaynak": "elle", "aciklama": "Elle girilen indirim"},
            "adaySayisi": len(cands), "elenen": dropped, "alternatifler": alts,
            "not": None if alts else "Seçilen temada stoğu ve geçerli fiyatı olan kitap yok ya da bütçeye sığmıyor."}


def _int(v: Any) -> str:
    return f"{int(round(float(v or 0))):,}".replace(",", ".")


# ------------------------------------------------------------------------------------------ kurumlar


def _account_dict(r: Any, sales: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {"ref": r.ref, "logoKod": r.logo_code, "logoRef": r.logo_clientref, "crmId": r.crm_account_id, "unvan": r.unvan,
            "il": r.il, "kanal": r.kanal, "crmRol": src.CRM_ROLE_LABEL.get(r.crm_rol) if r.crm_rol else None,
            "segment": r.segment, "segmentLabel": SEGMENTS.get(r.segment or "", None), "segmentKaynak": r.segment_kaynak,
            "segmentOlasilik": r.segment_olasilik, "segmentBy": r.segment_by, "temsilci": r.temsilci,
            "temsilciHesap": r.temsilci_hesap, "iskonto": r.iskonto, "epostaIzni": r.eposta_izni, "pasif": bool(r.pasif),
            "ilkAlim": r.ilk_alim, "sonAlim": r.son_alim, **(sales or {})}


def ytd_window(end: Optional[date]) -> Optional[dict[str, Any]]:
    """Bu yıl ve geçen yılın aynı dönemi: verinin bittiği aydan önceki tam aylar (Ocak'ta bitiyorsa Ocak dahil)."""
    if not end:
        return None
    last = end.month - 1 if end.month > 1 else 1
    months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    return {"year": end.year, "months": last, "label": f"Ocak–{months[last - 1]}" if last > 1 else "Ocak"}


def sales_stmt(code: Optional[str] = None) -> sa.Select:
    """Kurum alım tablosu (semantic_corp_sales: cari kodu × yıl × ay net ciro, adet, fatura); `code` verilirse tek kurum."""
    q = sa.select(SALES)
    return q if code is None else q.where(SALES.c.logo_code == code).order_by(SALES.c.year, SALES.c.month)


def _summarize(rows: Iterable[Any], w: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = out.setdefault(r.logo_code, {"buYil": 0.0, "gecenYilAyni": 0.0, "gecenYil": 0.0, "toplamCiro": 0.0, "fatura": 0})
        d["toplamCiro"] += r.ciro
        d["fatura"] += r.fatura
        if w:
            if r.year == w["year"] and r.month <= w["months"]:
                d["buYil"] += r.ciro
            if r.year == w["year"] - 1:
                d["gecenYil"] += r.ciro
                if r.month <= w["months"]:
                    d["gecenYilAyni"] += r.ciro
    return out


def _sales_summary(engine: sa.engine.Engine, end: Optional[date]) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        return _summarize(c.execute(sales_stmt()).all(), ytd_window(end))


def accounts_stmt(tenant: str, *, q: str = "", segment: str = "", temsilci: str = "") -> sa.Select:
    """Kurum kartları (semantic_corp_accounts), ekrandaki arama ve segment süzgeciyle."""
    cond = [ACCOUNTS.c.tenant_id == tenant]
    if q:
        like = f"%{q.strip()}%"
        cond.append(sa.or_(ACCOUNTS.c.unvan.ilike(like), ACCOUNTS.c.logo_code.ilike(like), ACCOUNTS.c.il.ilike(like)))
    if segment == "bos":
        cond.append(ACCOUNTS.c.segment.is_(None))
    elif segment == "oneri":
        cond.append(ACCOUNTS.c.segment_kaynak == "oneri")
    elif segment:
        cond.append(ACCOUNTS.c.segment == segment)
    if temsilci:
        cond.append(ACCOUNTS.c.temsilci_hesap == temsilci)
    return sa.select(ACCOUNTS).where(*cond)


def segment_counts_stmt(tenant: str) -> sa.Select:
    """Segment başına kurum sayısı (süzgeç kutusundaki sayılar)."""
    return (sa.select(ACCOUNTS.c.segment, sa.func.count().label("sayi"))
            .where(ACCOUNTS.c.tenant_id == tenant).group_by(ACCOUNTS.c.segment))


def list_accounts(engine: sa.engine.Engine, tenant: str, *, q: str = "", segment: str = "", temsilci: str = "",
                  sort: str = "ciro", page: int = 0) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(accounts_stmt(tenant, q=q, segment=segment, temsilci=temsilci)).all()
        seg_counts = {k: v for k, v in c.execute(segment_counts_stmt(tenant)).all()}
    end = data_end(engine)
    sales = _sales_summary(engine, end)
    items = [_account_dict(r, sales.get(r.logo_code or "", {"buYil": 0.0, "gecenYilAyni": 0.0, "gecenYil": 0.0,
                                                             "toplamCiro": 0.0, "fatura": 0})) for r in rows]
    if sort == "son":
        items.sort(key=lambda a: fold(a["unvan"]))
        items.sort(key=lambda a: a["sonAlim"] or "", reverse=True)
    else:
        keyf = {"ciro": lambda a: (-a["buYil"], -a["toplamCiro"], fold(a["unvan"])),
                "gecen": lambda a: (-a["gecenYil"], fold(a["unvan"])),
                "ad": lambda a: fold(a["unvan"])}.get(sort)
        if keyf is None:
            raise CorporateError("Geçersiz sıralama.")
        items.sort(key=keyf)
    total = len(items)
    return {"items": items[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], "total": total, "page": page, "pageSize": PAGE_SIZE,
            "segments": {k or "bos": v for k, v in seg_counts.items()}, "window": ytd_window(end),
            "dataEnd": end.isoformat() if end else None}


def account_stmt(tenant: str, ref: str) -> sa.Select:
    return sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.ref == ref)


def account_opps_stmt(tenant: str, ref: str) -> sa.Select:
    """Kurumun fırsatları (elle girilir)."""
    return sa.select(OPPS).where(OPPS.c.tenant_id == tenant, OPPS.c.account_ref == ref).order_by(OPPS.c.created_at.desc())


def account_reminders_stmt(tenant: str, code: str) -> sa.Select:
    """Kurumun dönemsel hatırlatmaları."""
    return (sa.select(REMINDERS).where(REMINDERS.c.tenant_id == tenant, REMINDERS.c.logo_code == code)
            .order_by(REMINDERS.c.donem_ayi.desc()))


def account_detail(engine: sa.engine.Engine, tenant: str, ref: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(account_stmt(tenant, ref)).first()
        if not r:
            raise CorporateError("Kurum bulunamadı.", 404)
        sale_rows = c.execute(sales_stmt(r.logo_code or "")).all()
        months = [dict(x._mapping) for x in sale_rows]
        opps = c.execute(account_opps_stmt(tenant, ref)).all()
        rems = c.execute(account_reminders_stmt(tenant, r.logo_code or "")).all()
    end = data_end(engine)
    years: dict[int, dict[str, Any]] = {}
    for m in months:
        y = years.setdefault(m["year"], {"yil": m["year"], "ciro": 0.0, "adet": 0.0, "fatura": 0, "aylar": [0.0] * 12})
        y["ciro"] += m["ciro"]
        y["adet"] += m["adet"]
        y["fatura"] += m["fatura"]
        y["aylar"][m["month"] - 1] += m["ciro"]
    # En çok alınan ay: dönemsel alım alışkanlığı (hatırlatmanın dayanağı)
    by_month = [0.0] * 12
    for m in months:
        by_month[m["month"] - 1] += max(0.0, m["ciro"])
    peak = max(range(12), key=lambda i: by_month[i]) + 1 if any(by_month) else None
    return {**_account_dict(r, _summarize(sale_rows, ytd_window(end)).get(r.logo_code or "")),
            "yillar": sorted(years.values(), key=lambda x: x["yil"]), "enCokAy": peak,
            "firsatlar": [_opp_dict(o) for o in opps], "hatirlatmalar": [_rem_dict(x) for x in rems],
            "window": ytd_window(end), "dataEnd": end.isoformat() if end else None}


def set_segment(engine: sa.engine.Engine, tenant: str, user: str, ref: str, body: dict[str, Any]) -> dict[str, Any]:
    seg = body.get("segment")
    if seg in (None, ""):
        seg = None
    elif seg not in SEGMENTS:
        raise CorporateError("Geçersiz segment.")
    with engine.begin() as c:
        r = c.execute(sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.ref == ref)).first()
        if not r:
            raise CorporateError("Kurum bulunamadı.", 404)
        c.execute(ACCOUNTS.update().where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.ref == ref).values(
            segment=seg, segment_kaynak="elle" if seg else None, segment_olasilik=None, segment_by=user, segment_at=_now()))
    return {"ref": ref, "onceki": r.segment, "segment": seg}


# ------------------------------------------------------------------------------------------ fırsatlar


def _opp_dict(r: Any, quotes: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    d = {"id": r.id, "accountRef": r.account_ref, "logoKod": r.logo_code, "crmId": r.crm_account_id, "kurum": r.kurum,
         "ad": r.ad, "tema": r.tema, "asama": r.asama, "asamaLabel": STAGES.get(r.asama, r.asama), "deger": r.deger,
         "kararTarihi": r.karar_tarihi, "sahip": r.sahip, "sonrakiAdim": r.sonraki_adim, "sonrakiTarih": r.sonraki_tarih,
         "kaybetmeNedeni": r.kaybetme_nedeni, "kayipSinif": r.kayip_sinif, "kayipSinifLabel": LOSS.get(r.kayip_sinif or ""),
         "kayipSinifKaynak": r.kayip_sinif_kaynak, "kaynak": r.kaynak, "hatirlatmaId": r.hatirlatma_id, "notlar": r.notlar,
         "createdBy": r.created_by, "createdAt": _iso(r.created_at), "updatedBy": r.updated_by, "updatedAt": _iso(r.updated_at),
         "closedAt": _iso(r.closed_at)}
    if quotes is not None:
        d["teklifler"] = quotes
    return d


def _visible(user: str, see_all: bool, approver: bool, opp: Any, has_pending: bool = False) -> bool:
    return see_all or (opp.sahip or "").lower() == user.lower() or (approver and has_pending)


def _opp_row(c: Any, tenant: str, opp_id: str) -> Any:
    r = c.execute(opp_stmt(tenant, opp_id)).first()
    if not r:
        raise CorporateError("Fırsat bulunamadı.", 404)
    return r


def _check_owner(r: Any, user: str, see_all: bool) -> None:
    if not see_all and (r.sahip or "").lower() != user.lower():
        raise CorporateError("Bu fırsat başka bir temsilcinin; bütün ekibin fırsatlarını görme yetkiniz yok.", 403)


def opps_stmt(tenant: str, *, asama: str = "", sahip: str = "", q: str = "", acik: bool = False) -> sa.Select:
    """Fırsatlar (elle girilir; ekranın aşama, sahip ve arama süzgeciyle). Görme yetkisi (sahip) uçta süzülür."""
    cond = [OPPS.c.tenant_id == tenant]
    if asama:
        cond.append(OPPS.c.asama == asama)
    if acik:
        cond.append(OPPS.c.asama.in_(OPEN_STAGES))
    if sahip:
        cond.append(OPPS.c.sahip == sahip)
    if q:
        like = f"%{q.strip()}%"
        cond.append(sa.or_(OPPS.c.kurum.ilike(like), OPPS.c.ad.ilike(like), OPPS.c.tema.ilike(like)))
    return sa.select(OPPS).where(*cond).order_by(OPPS.c.karar_tarihi.is_(None), OPPS.c.karar_tarihi, OPPS.c.created_at.desc())


def pending_opps_stmt(tenant: str) -> sa.Select:
    """Onay bekleyen teklifi olan fırsatlar."""
    return sa.select(QUOTES.c.firsat_id).where(QUOTES.c.tenant_id == tenant, QUOTES.c.durum == "onayda")


def quote_heads_stmt(tenant: str) -> sa.Select:
    """Bütün teklif sürümlerinin başlığı (fırsat, sürüm, durum, teklif tutarı); fırsat başına son sürüm uçta seçilir."""
    return sa.select(QUOTES.c.firsat_id, QUOTES.c.surum, QUOTES.c.durum, QUOTES.c.toplam_net).where(QUOTES.c.tenant_id == tenant)


def list_opportunities(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, approver: bool, *,
                       asama: str = "", sahip: str = "", q: str = "", acik: bool = False) -> dict[str, Any]:
    if asama and asama not in STAGES:
        raise CorporateError("Geçersiz aşama.")
    with engine.connect() as c:
        rows = c.execute(opps_stmt(tenant, asama=asama, sahip=sahip, q=q, acik=acik)).all()
        pending = {r[0] for r in c.execute(pending_opps_stmt(tenant)).all()}
        last_quote: dict[str, Any] = {}
        for qr in c.execute(quote_heads_stmt(tenant)).all():
            cur = last_quote.get(qr.firsat_id)
            if cur is None or qr.surum > cur.surum:
                last_quote[qr.firsat_id] = qr
    items = []
    for r in rows:
        if not _visible(user, see_all, approver, r, r.id in pending):
            continue
        d = _opp_dict(r)
        lq = last_quote.get(r.id)
        d["sonTeklif"] = ({"surum": lq.surum, "durum": lq.durum, "durumLabel": QUOTE_STATUS.get(lq.durum), "toplamNet": lq.toplam_net}
                          if lq else None)
        d["onayBekliyor"] = r.id in pending
        items.append(d)
    soon = today() + timedelta(days=7)
    columns = []
    for key, label in STAGES.items():
        col = [i for i in items if i["asama"] == key]
        columns.append({"asama": key, "label": label, "sayi": len(col),
                        "deger": round(sum((i["sonTeklif"] or {}).get("toplamNet") or i["deger"] or 0 for i in col), 2)})
    return {"items": items, "columns": columns,
            "yaklasan": [i for i in items if i["asama"] in OPEN_STAGES and i["kararTarihi"] and i["kararTarihi"] <= soon.isoformat()],
            "stages": STAGES, "loss": LOSS}


def _opp_values(engine: sa.engine.Engine, tenant: str, body: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    v: dict[str, Any] = {}
    if creating or "accountRef" in body:
        ref = _text(body.get("accountRef"), 60)
        if ref:
            with engine.connect() as c:
                a = c.execute(sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.ref == ref)).first()
            if not a:
                raise CorporateError("Kurum bulunamadı.", 404)
            v.update(account_ref=a.ref, logo_code=a.logo_code, crm_account_id=a.crm_account_id, kurum=a.unvan or a.ref)
        elif creating:
            name = _text(body.get("kurum"), 400)
            if not name:
                raise CorporateError("Kurum seçin ya da kurum adını yazın.")
            v.update(account_ref=None, logo_code=None, crm_account_id=None, kurum=name)
    if creating or "ad" in body:
        ad = _text(body.get("ad"), 300)
        if not ad:
            raise CorporateError("Fırsatın adını yazın (ör. «Yılsonu hediye kitabı»).")
        v["ad"] = ad
    if "tema" in body:
        v["tema"] = _text(body.get("tema"), 200)
    if "deger" in body:
        v["deger"] = _num(body.get("deger"), "Tahmini değer", allow_none=True, minimum=0)
    if "kararTarihi" in body:
        v["karar_tarihi"] = _day_in(body.get("kararTarihi"), "Karar tarihi")
    if "sonrakiAdim" in body:
        v["sonraki_adim"] = _text(body.get("sonrakiAdim"), 500)
    if "sonrakiTarih" in body:
        v["sonraki_tarih"] = _day_in(body.get("sonrakiTarih"), "Sonraki adım tarihi")
    if "notlar" in body:
        v["notlar"] = _longtext(body.get("notlar"), 4000)
    return v


def create_opportunity(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], *,
                       reminder_id: Optional[str] = None) -> dict[str, Any]:
    v = _opp_values(engine, tenant, body, creating=True)
    asama = body.get("asama") or "aday"
    if asama not in OPEN_STAGES:
        raise CorporateError("Yeni fırsat açık bir aşamada başlar.")
    now = _now()
    oid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(OPPS.insert().values(id=oid, tenant_id=tenant, asama=asama, sahip=user, kaynak="hatirlatma" if reminder_id else "elle",
                                       hatirlatma_id=reminder_id, created_by=user, created_at=now, updated_by=user, updated_at=now, **v))
    return opportunity(engine, tenant, user, True, False, oid)


def opp_stmt(tenant: str, opp_id: str) -> sa.Select:
    return sa.select(OPPS).where(OPPS.c.tenant_id == tenant, OPPS.c.id == opp_id)


def opp_quotes_stmt(tenant: str, opp_id: str) -> sa.Select:
    """Fırsatın teklif sürümleri (kalemler, tutarlar ve onay nedenleri kaydedildiği andaki hesapla saklı)."""
    return (sa.select(QUOTES).where(QUOTES.c.tenant_id == tenant, QUOTES.c.firsat_id == opp_id)
            .order_by(QUOTES.c.surum.desc()))


def opportunity(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, approver: bool, opp_id: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _opp_row(c, tenant, opp_id)
        qs = c.execute(opp_quotes_stmt(tenant, opp_id)).all()
    pending = any(q.durum == "onayda" for q in qs)
    if not _visible(user, see_all, approver, r, pending):
        raise CorporateError("Bu fırsat başka bir temsilcinin; bütün ekibin fırsatlarını görme yetkiniz yok.", 403)
    return _opp_dict(r, [_quote_dict(q) for q in qs])


def update_opportunity(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, opp_id: str,
                       body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    v = _opp_values(engine, tenant, body, creating=False)
    if "asama" in body:
        a = body.get("asama")
        if a not in STAGES:
            raise CorporateError("Geçersiz aşama.")
        v["asama"] = a
        if a == "kaybedildi":
            cls = body.get("kayipSinif")
            if cls not in LOSS:
                raise CorporateError("Kaybedilen fırsat için neden seçin.")
            v.update(kayip_sinif=cls, kayip_sinif_kaynak="elle", kaybetme_nedeni=_longtext(body.get("kaybetmeNedeni"), 2000))
    elif "kayipSinif" in body or "kaybetmeNedeni" in body:
        if "kayipSinif" in body:
            if body["kayipSinif"] not in LOSS:
                raise CorporateError("Geçersiz neden.")
            v.update(kayip_sinif=body["kayipSinif"], kayip_sinif_kaynak="elle")
        if "kaybetmeNedeni" in body:
            v["kaybetme_nedeni"] = _longtext(body.get("kaybetmeNedeni"), 2000)
    if "sahip" in body:
        owner = _text(body.get("sahip"), 120)
        if not owner:
            raise CorporateError("Sahip boş olamaz.")
        if not see_all and owner.lower() != user.lower():
            raise CorporateError("Fırsatı başka temsilciye devretmek bütün ekibi görme yetkisi ister.", 403)
        v["sahip"] = owner.lower()
    if not v:
        raise CorporateError("Değişecek alan yok.")
    with engine.begin() as c:
        r = _opp_row(c, tenant, opp_id)
        _check_owner(r, user, see_all)
        diff = {k: {"once": getattr(r, k), "sonra": val} for k, val in v.items() if getattr(r, k) != val}
        if "asama" in v:
            closed = v["asama"] in ("kazanildi", "kaybedildi")
            v["closed_at"] = _now() if closed and r.asama in OPEN_STAGES else (r.closed_at if closed else None)
            if v["asama"] != "kaybedildi" and r.asama == "kaybedildi":
                v.update(kayip_sinif=None, kayip_sinif_kaynak=None)
        c.execute(OPPS.update().where(OPPS.c.id == opp_id).values(updated_by=user, updated_at=_now(), **v))
    return opportunity(engine, tenant, user, True, False, opp_id), diff


def closed_opps_stmt(tenant: str) -> sa.Select:
    """Kapanmış fırsatlar (Kazanıldı, Kaybedildi)."""
    return sa.select(OPPS).where(OPPS.c.tenant_id == tenant, OPPS.c.asama.in_(("kazanildi", "kaybedildi")))


def pipeline_summary(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool) -> dict[str, Any]:
    """Kazanma oranı ve kaybetme nedenleri (K3): kapanmış fırsatlar."""
    with engine.connect() as c:
        rows = c.execute(closed_opps_stmt(tenant)).all()
    rows = [r for r in rows if see_all or (r.sahip or "").lower() == user.lower()]
    won = [r for r in rows if r.asama == "kazanildi"]
    lost = [r for r in rows if r.asama == "kaybedildi"]
    reasons: dict[str, int] = {}
    for r in lost:
        reasons[r.kayip_sinif or "siniflanmadi"] = reasons.get(r.kayip_sinif or "siniflanmadi", 0) + 1
    return {"kapanan": len(rows), "kazanilan": len(won), "kaybedilen": len(lost),
            "kazanmaOrani": round(len(won) / len(rows), 4) if rows else None,
            "kazanilanDeger": round(sum(r.deger or 0 for r in won), 2),
            "nedenler": [{"kod": k, "label": LOSS.get(k, "Sınıflanmadı"), "sayi": v}
                         for k, v in sorted(reasons.items(), key=lambda x: -x[1])]}


# ------------------------------------------------------------------------------------------ teklifler


def _quote_dict(q: Any) -> dict[str, Any]:
    return {"id": q.id, "firsatId": q.firsat_id, "surum": q.surum, "durum": q.durum, "durumLabel": QUOTE_STATUS.get(q.durum, q.durum),
            "kalemler": _j(q.kalemler_json, []), "paketAdet": q.paket_adet, "toplamListe": q.toplam_liste, "toplamNet": q.toplam_net,
            "toplamMaliyet": q.toplam_maliyet, "marj": q.marj, "maliyetKapsami": q.maliyet_kapsami,
            "indirimOrani": round(1 - q.toplam_net / q.toplam_liste, 4) if q.toplam_liste else None,
            "onayGerekli": bool(q.onay_gerekli), "onayNedenleri": _j(q.onay_nedenleri_json, []), "mektup": q.mektup,
            "notlar": q.notlar, "gecerlilikGun": q.gecerlilik_gun, "gonderen": q.gonderen, "gonderimAt": _iso(q.gonderim_at),
            "onaylayan": q.onaylayan, "onayAt": _iso(q.onay_at), "onayNotu": q.onay_notu, "gonderildiAt": _iso(q.gonderildi_at),
            "sonucNeden": q.sonuc_neden, "sonucAt": _iso(q.sonuc_at), "createdBy": q.created_by, "createdAt": _iso(q.created_at),
            "updatedBy": q.updated_by, "updatedAt": _iso(q.updated_at)}


def quote_stmt(tenant: str, qid: str) -> sa.Select:
    return sa.select(QUOTES).where(QUOTES.c.tenant_id == tenant, QUOTES.c.id == qid)


def _quote_row(c: Any, tenant: str, qid: str) -> Any:
    q = c.execute(quote_stmt(tenant, qid)).first()
    if not q:
        raise CorporateError("Teklif bulunamadı.", 404)
    return q


def _computed(engine: sa.engine.Engine, st: dict[str, Any], body: dict[str, Any], default_disc: Optional[float] = None) -> dict[str, Any]:
    items = body.get("kalemler") or []
    qty = sum(float((it or {}).get("adet") or 0) for it in items if isinstance(it, dict))
    if default_disc is None:
        vd = volume_discount(qty, st, meta_get(engine, "volume").get("buckets") or [])
        default_disc = float(vd["indirim"] or 0.0)
    lines = price_lines(engine, st, items, default_disc)
    tot = quote_totals(lines, st)
    return {"kalemler_json": _dump(lines), "toplam_liste": tot["toplamListe"], "toplam_net": tot["toplamNet"],
            "toplam_maliyet": tot["toplamMaliyet"], "marj": tot["marj"], "maliyet_kapsami": tot["maliyetKapsami"],
            "onay_gerekli": tot["onayGerekli"], "onay_nedenleri_json": _dump(tot["onayNedenleri"])}


def create_quote(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, user: str, see_all: bool, opp_id: str,
                 body: dict[str, Any]) -> dict[str, Any]:
    copy_of = _text(body.get("kopya"), 32)
    with engine.connect() as c:
        r = _opp_row(c, tenant, opp_id)
        _check_owner(r, user, see_all)
        if r.asama not in OPEN_STAGES:
            raise CorporateError("Kapanmış fırsata teklif açılmaz.", 409)
        n = c.execute(sa.select(sa.func.max(QUOTES.c.surum)).where(QUOTES.c.firsat_id == opp_id)).scalar() or 0
        src_q = _quote_row(c, tenant, copy_of) if copy_of else None
    if src_q is not None:
        if src_q.firsat_id != opp_id:
            raise CorporateError("Kopyalanan teklif bu fırsatın değil.")
        body = {"kalemler": [{"stok": l["stok"], "adet": l["adet"], "indirim": l["indirim"] * 100,
                              **({"listeFiyati": l["listeFiyati"]} if l.get("fiyatKaynak") == "elle" else {})}
                             for l in _j(src_q.kalemler_json, [])],
                "paketAdet": src_q.paket_adet, "mektup": src_q.mektup, "notlar": src_q.notlar, **body}
    vals = _computed(engine, st, body)
    now = _now()
    qid = uuid.uuid4().hex
    with engine.begin() as c:
        c.execute(QUOTES.insert().values(
            id=qid, tenant_id=tenant, firsat_id=opp_id, surum=n + 1, durum="taslak",
            paket_adet=int(_num(body.get("paketAdet"), "Paket sayısı", allow_none=True, minimum=1) or 0) or None,
            mektup=_longtext(body.get("mektup"), 8000), notlar=_longtext(body.get("notlar"), 4000),
            gecerlilik_gun=int(_num(body.get("gecerlilikGun"), "Geçerlilik", allow_none=True, minimum=1, maximum=365) or st["quoteValidDays"]),
            created_by=user, created_at=now, updated_by=user, updated_at=now, **vals))
        if r.asama in ("aday", "gorusuldu"):
            c.execute(OPPS.update().where(OPPS.c.id == opp_id).values(asama="teklif", updated_by=user, updated_at=now))
    return quote(engine, tenant, user, see_all, True, qid)


def quote(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, approver: bool, qid: str) -> dict[str, Any]:
    with engine.connect() as c:
        q = _quote_row(c, tenant, qid)
        r = _opp_row(c, tenant, q.firsat_id)
    if not _visible(user, see_all, approver, r, q.durum == "onayda"):
        raise CorporateError("Bu teklif başka bir temsilcinin.", 403)
    return {**_quote_dict(q), "firsat": _opp_dict(r)}


def update_quote(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, user: str, see_all: bool, qid: str,
                 body: dict[str, Any]) -> dict[str, Any]:
    with engine.connect() as c:
        q = _quote_row(c, tenant, qid)
        _check_owner(_opp_row(c, tenant, q.firsat_id), user, see_all)
    vals: dict[str, Any] = {}
    if "kalemler" in body:
        if q.durum != "taslak":
            raise CorporateError("Yalnız taslak teklifin kalemleri değişir; değişiklik için yeni sürüm açın.", 409)
        vals.update(_computed(engine, st, body))
    if "mektup" in body:
        if q.durum not in ("taslak", "hazir"):
            raise CorporateError("Gönderilmiş teklifin mektubu değişmez.", 409)
        vals["mektup"] = _longtext(body.get("mektup"), 8000)
    if "notlar" in body:
        vals["notlar"] = _longtext(body.get("notlar"), 4000)
    if "paketAdet" in body:
        vals["paket_adet"] = int(_num(body.get("paketAdet"), "Paket sayısı", allow_none=True, minimum=1) or 0) or None
    if "gecerlilikGun" in body:
        vals["gecerlilik_gun"] = int(_num(body.get("gecerlilikGun"), "Geçerlilik", minimum=1, maximum=365))
    if not vals:
        raise CorporateError("Değişecek alan yok.")
    with engine.begin() as c:
        c.execute(QUOTES.update().where(QUOTES.c.id == qid).values(updated_by=user, updated_at=_now(), **vals))
    return quote(engine, tenant, user, True, True, qid)


def delete_quote(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, qid: str) -> dict[str, Any]:
    with engine.begin() as c:
        q = _quote_row(c, tenant, qid)
        _check_owner(_opp_row(c, tenant, q.firsat_id), user, see_all)
        if q.durum != "taslak":
            raise CorporateError("Yalnız taslak teklif silinir.", 409)
        c.execute(QUOTES.delete().where(QUOTES.c.id == qid))
    return _quote_dict(q)


def submit_quote(engine: sa.engine.Engine, st: dict[str, Any], tenant: str, user: str, see_all: bool, qid: str) -> dict[str, Any]:
    """Taslak → onayda (eşik aşıldıysa) ya da hazır (onay gerekmiyorsa). Kalemler o anki kurallarla yeniden hesaplanır."""
    with engine.connect() as c:
        q = _quote_row(c, tenant, qid)
        _check_owner(_opp_row(c, tenant, q.firsat_id), user, see_all)
    if q.durum != "taslak":
        raise CorporateError("Yalnız taslak gönderilir.", 409)
    lines = _j(q.kalemler_json, [])
    tot = quote_totals(lines, st)
    now = _now()
    status = "onayda" if tot["onayGerekli"] else "hazir"
    with engine.begin() as c:
        c.execute(QUOTES.update().where(QUOTES.c.id == qid, QUOTES.c.durum == "taslak").values(
            durum=status, onay_gerekli=tot["onayGerekli"], onay_nedenleri_json=_dump(tot["onayNedenleri"]),
            gonderen=user, gonderim_at=now, onaylayan=None, onay_at=None, onay_notu=None, updated_by=user, updated_at=now))
    return quote(engine, tenant, user, True, True, qid)


def withdraw_quote(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, qid: str) -> dict[str, Any]:
    with engine.begin() as c:
        q = _quote_row(c, tenant, qid)
        _check_owner(_opp_row(c, tenant, q.firsat_id), user, see_all)
        if q.durum not in ("onayda", "hazir"):
            raise CorporateError("Teklif onayda ya da gönderilebilir durumda değil.", 409)
        c.execute(QUOTES.update().where(QUOTES.c.id == qid).values(durum="taslak", updated_by=user, updated_at=_now()))
    return quote(engine, tenant, user, True, True, qid)


def decide_quote(engine: sa.engine.Engine, tenant: str, user: str, qid: str, approve: bool, note: Any) -> dict[str, Any]:
    """Müdür onayı. Gönderen onaylayamaz (iki göz). Geri gönderme gerekçe ister, teklif taslağa döner."""
    note_t = _longtext(note, 2000)
    if not approve and not note_t:
        raise CorporateError("Geri gönderme gerekçesi yazın.")
    with engine.begin() as c:
        q = _quote_row(c, tenant, qid)
        if q.durum != "onayda":
            raise CorporateError("Teklif onay beklemiyor.", 409)
        if (q.gonderen or "").lower() == user.lower():
            raise CorporateError("Onaya gönderen kişi aynı teklifi onaylayamaz; başka bir yetkili onaylamalı.", 409)
        now = _now()
        c.execute(QUOTES.update().where(QUOTES.c.id == qid).values(
            durum="hazir" if approve else "taslak", onaylayan=user, onay_at=now, onay_notu=note_t, updated_by=user, updated_at=now))
    return quote(engine, tenant, user, True, True, qid)


def mark_sent(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, qid: str) -> dict[str, Any]:
    with engine.begin() as c:
        q = _quote_row(c, tenant, qid)
        r = _opp_row(c, tenant, q.firsat_id)
        _check_owner(r, user, see_all)
        if q.durum != "hazir":
            raise CorporateError("Yalnız gönderilebilir (onaylı ya da onay gerektirmeyen) teklif gönderildi işaretlenir.", 409)
        now = _now()
        c.execute(QUOTES.update().where(QUOTES.c.id == qid).values(durum="gonderildi", gonderildi_at=now, updated_by=user, updated_at=now))
        if r.asama in ("aday", "gorusuldu", "teklif"):
            c.execute(OPPS.update().where(OPPS.c.id == r.id).values(asama="karar", updated_by=user, updated_at=now))
    return quote(engine, tenant, user, True, True, qid)


def record_result(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, qid: str, body: dict[str, Any]) -> dict[str, Any]:
    """Kurumun cevabı: kabul (fırsat kazanıldı, değeri teklif tutarı) ya da ret (fırsat açık kalır; kapatmak ayrı)."""
    res = body.get("sonuc")
    if res not in ("kabul", "ret"):
        raise CorporateError("Sonuç «kabul» ya da «ret» olmalı.")
    with engine.begin() as c:
        q = _quote_row(c, tenant, qid)
        r = _opp_row(c, tenant, q.firsat_id)
        _check_owner(r, user, see_all)
        if q.durum != "gonderildi":
            raise CorporateError("Sonuç yalnız gönderilmiş teklife yazılır.", 409)
        now = _now()
        c.execute(QUOTES.update().where(QUOTES.c.id == qid).values(
            durum=res, sonuc_neden=_longtext(body.get("neden"), 2000), sonuc_at=now, updated_by=user, updated_at=now))
        if res == "kabul":
            c.execute(OPPS.update().where(OPPS.c.id == r.id).values(asama="kazanildi", deger=q.toplam_net, closed_at=now,
                                                                     updated_by=user, updated_at=now))
    return quote(engine, tenant, user, True, True, qid)


def approval_queue_stmt(tenant: str) -> sa.Select:
    """Onay bekleyen teklifler, fırsatın kurumu ve sahibiyle (gönderim sırasıyla)."""
    return (sa.select(QUOTES, OPPS.c.kurum, OPPS.c.ad.label("firsat_ad"), OPPS.c.sahip)
            .join(OPPS, OPPS.c.id == QUOTES.c.firsat_id)
            .where(QUOTES.c.tenant_id == tenant, QUOTES.c.durum == "onayda").order_by(QUOTES.c.gonderim_at))


def approval_queue(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(approval_queue_stmt(tenant)).all()
    return [{**_quote_dict(r), "kurum": r.kurum, "firsatAd": r.firsat_ad, "sahip": r.sahip} for r in rows]


# ------------------------------------------------------------------------------------------ hatırlatmalar


def _rem_dict(r: Any) -> dict[str, Any]:
    return {"id": r.id, "logoKod": r.logo_code, "unvan": r.unvan, "donemAyi": r.donem_ayi, "gecenYilTutar": r.gecen_yil_tutar,
            "gecenYilAdet": r.gecen_yil_adet, "durum": r.durum, "durumLabel": REMINDER_STATUS.get(r.durum, r.durum),
            "firsatId": r.firsat_id, "createdAt": _iso(r.created_at), "updatedBy": r.updated_by, "updatedAt": _iso(r.updated_at)}


def reminder_months(now: date, lead_days: int) -> list[str]:
    """Hatırlatılacak aylar: bu ay ve başlangıcı bugünden `lead_days` gün içinde olan aylar."""
    out = []
    y, m = now.year, now.month
    while True:
        start = date(y, m, 1)
        if start > now + timedelta(days=lead_days):
            break
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def reminder_sales_stmt(year: int, month: int) -> sa.Select:
    """Hatırlatmayı üreten okuma: geçen yılın o ayında net alımı (> 0) olan kurumlar (kurum alım tablosundan)."""
    return (sa.select(SALES.c.logo_code, SALES.c.ciro, SALES.c.adet)
            .where(SALES.c.year == year, SALES.c.month == month, SALES.c.ciro > 0))


def reminders_stmt(tenant: str, months: list[str], durum: str = "") -> sa.Select:
    """Hatırlatma listesi: ayların hatırlatmaları (ekranın durum süzgeciyle)."""
    cond = [REMINDERS.c.tenant_id == tenant, REMINDERS.c.donem_ayi.in_(months)]
    if durum:
        cond.append(REMINDERS.c.durum == durum)
    return sa.select(REMINDERS).where(*cond).order_by(REMINDERS.c.donem_ayi, REMINDERS.c.gecen_yil_tutar.desc())


def reminder_reps_stmt(tenant: str) -> sa.Select:
    """Hatırlatma satırındaki temsilci ve kurum bağı (kurum kartından)."""
    return sa.select(ACCOUNTS.c.logo_code, ACCOUNTS.c.temsilci, ACCOUNTS.c.ref).where(ACCOUNTS.c.tenant_id == tenant)


def generate_reminders(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], now: Optional[date] = None) -> dict[str, Any]:
    now = now or today()
    months = reminder_months(now, st["reminderLeadDays"])
    made = 0
    with engine.begin() as c:
        names = {r.logo_code: r.unvan for r in c.execute(sa.select(ACCOUNTS.c.logo_code, ACCOUNTS.c.unvan)
                                                          .where(ACCOUNTS.c.tenant_id == tenant)).all() if r.logo_code}
        for ym in months:
            y, m = int(ym[:4]), int(ym[5:])
            rows = c.execute(reminder_sales_stmt(y - 1, m)).all()
            have = {r[0] for r in c.execute(sa.select(REMINDERS.c.logo_code).where(REMINDERS.c.tenant_id == tenant,
                                                                                   REMINDERS.c.donem_ayi == ym)).all()}
            for r in rows:
                if r.logo_code in have:
                    continue
                c.execute(REMINDERS.insert().values(
                    id=uuid.uuid4().hex, tenant_id=tenant, logo_code=r.logo_code, unvan=names.get(r.logo_code) or r.logo_code,
                    donem_ayi=ym, gecen_yil_tutar=round(r.ciro, 2), gecen_yil_adet=r.adet, durum="acik", created_at=_now()))
                made += 1
    return {"aylar": months, "yeni": made}


def list_reminders(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], *, ay: str = "", durum: str = "") -> dict[str, Any]:
    months = [ay] if ay else reminder_months(today(), st["reminderLeadDays"])
    for m in months:
        if not re.match(r"^\d{4}-\d{2}$", m):
            raise CorporateError("Ay YYYY-AA biçiminde olmalı.")
    if durum and durum not in REMINDER_STATUS:
        raise CorporateError("Geçersiz durum.")
    with engine.connect() as c:
        rows = c.execute(reminders_stmt(tenant, months, durum)).all()
        reps = {r.logo_code: (r.temsilci, r.ref) for r in c.execute(reminder_reps_stmt(tenant)).all() if r.logo_code}
    items = []
    for r in rows:
        d = _rem_dict(r)
        d["temsilci"], d["accountRef"] = reps.get(r.logo_code, (None, None))
        items.append(d)
    return {"items": items, "aylar": months, "leadDays": st["reminderLeadDays"],
            "toplamGecenYil": round(sum(i["gecenYilTutar"] for i in items), 2)}


def update_reminder(engine: sa.engine.Engine, tenant: str, user: str, rid: str, body: dict[str, Any]) -> dict[str, Any]:
    d = body.get("durum")
    if d not in ("acik", "kapandi"):
        raise CorporateError("Durum «acik» ya da «kapandi» olmalı.")
    with engine.begin() as c:
        r = c.execute(sa.select(REMINDERS).where(REMINDERS.c.tenant_id == tenant, REMINDERS.c.id == rid)).first()
        if not r:
            raise CorporateError("Hatırlatma bulunamadı.", 404)
        if r.durum == "firsat":
            raise CorporateError("Bu hatırlatmadan fırsat açıldı; fırsat üzerinden ilerleyin.", 409)
        c.execute(REMINDERS.update().where(REMINDERS.c.id == rid).values(durum=d, updated_by=user, updated_at=_now()))
    return {"id": rid, "durum": d, "unvan": r.unvan, "donemAyi": r.donem_ayi}


def opportunity_from_reminder(engine: sa.engine.Engine, tenant: str, user: str, rid: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(REMINDERS).where(REMINDERS.c.tenant_id == tenant, REMINDERS.c.id == rid)).first()
        if not r:
            raise CorporateError("Hatırlatma bulunamadı.", 404)
        if r.durum == "firsat" and r.firsat_id:
            raise CorporateError("Bu hatırlatmadan zaten fırsat açıldı.", 409)
        acc = c.execute(sa.select(ACCOUNTS.c.ref).where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.logo_code == r.logo_code)).first()
    months = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    y, m = int(r.donem_ayi[:4]), int(r.donem_ayi[5:])
    payload = {"accountRef": acc.ref if acc else None, "kurum": r.unvan,
               "ad": body.get("ad") or f"{months[m - 1]} {y} dönemsel alım", "deger": body.get("deger") or r.gecen_yil_tutar,
               "kararTarihi": body.get("kararTarihi") or date(y, m, 1).isoformat(), "tema": body.get("tema"),
               "sonrakiAdim": body.get("sonrakiAdim") or "Kurumu ara: geçen yılki alımı hatırlat"}
    out = create_opportunity(engine, tenant, user, payload, reminder_id=rid)
    with engine.begin() as c:
        c.execute(REMINDERS.update().where(REMINDERS.c.id == rid).values(durum="firsat", firsat_id=out["id"], updated_by=user,
                                                                         updated_at=_now()))
    return out


# ------------------------------------------------------------------------------------------ bayi paneli


def dealers_stmt(code: Optional[str] = None) -> sa.Select:
    """Bayi tablosu (semantic_corp_dealers: gece okumasında son 12 ay satış faturası olan bayi kanalı carileri)."""
    q = sa.select(DEALERS)
    return q if code is None else q.where(DEALERS.c.logo_code == code)


def dealer_rows(engine: sa.engine.Engine, *, gun: int, durum: str = "", sinif: str = "", q: str = "", kanal: str = "") -> dict[str, Any]:
    ref = data_end(engine)
    with engine.connect() as c:
        rows = c.execute(dealers_stmt()).all()
    items = []
    counts = {"aktif": 0, "sessiz": 0}
    for r in rows:
        last = date.fromisoformat(r.son_fatura) if r.son_fatura else None
        days = (ref - last).days if ref and last else None
        st = "sessiz" if days is not None and days >= gun else "aktif"
        counts[st] += 1
        if durum and st != durum:
            continue
        if sinif and r.sinif != sinif:
            continue
        if kanal and r.kanal != kanal:
            continue
        if q and fold(q) not in fold(f"{r.unvan} {r.logo_code} {r.il}"):
            continue
        items.append({"logoKod": r.logo_code, "unvan": r.unvan, "kanal": r.kanal, "il": r.il, "sonFatura": r.son_fatura, "gun": days,
                      "durum": st, "fatura12ay": r.fatura_12ay, "ciro12ay": r.ciro_12ay, "sinif": r.sinif,
                      "b2bSiparis": r.b2b_siparis, "b2bKullanici": r.b2b_kullanici,
                      "segment": f"{r.sinif or '—'} · {'sessiz' if st == 'sessiz' else 'aktif'}"
                                 + (" · B2B" if (r.b2b_siparis or 0) > 0 else "")})
    items.sort(key=lambda x: ({"A": 0, "B": 1, "C": 2}.get(x["sinif"] or "", 3), -(x["ciro12ay"] or 0)))
    return {"items": items, "total": len(items), "counts": counts, "gun": gun, "dataEnd": ref.isoformat() if ref else None,
            "b2b": meta_get(engine, "dealers")}


def dealers_csv(data: dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Cari kodu", "Unvan", "Kanal", "İl", "Son satış faturası", "Gün", "Durum", "Son 12 ay fatura", "Son 12 ay net ciro",
                "Değer sınıfı", "B2B siparişi (CRM)", "B2B kullanıcısı (CRM)"])
    for i in data["items"]:
        w.writerow([i["logoKod"], i["unvan"] or "", i["kanal"] or "", i["il"] or "", i["sonFatura"] or "", i["gun"] if i["gun"] is not None else "",
                    i["durum"], i["fatura12ay"], _n(i["ciro12ay"]), i["sinif"] or "", i["b2bSiparis"] if i["b2bSiparis"] is not None else "",
                    i["b2bKullanici"] if i["b2bKullanici"] is not None else ""])
    return "﻿" + buf.getvalue()


def _n(v: Any, d: int = 2) -> str:
    return "" if v is None else f"{float(v):.{d}f}".replace(".", ",")


def highlights_stmt() -> sa.Select:
    """Öne çıkarılacak kitaplar: stokta ve bayi kanalında son dönemde satan kitap kartları."""
    return (sa.select(BOOKS).where(BOOKS.c.stok > 0, BOOKS.c.bayi_son > 0)
            .order_by(BOOKS.c.bayi_son.desc(), BOOKS.c.stok_kodu))


def highlights(engine: sa.engine.Engine, st: dict[str, Any]) -> dict[str, Any]:
    """Bayilere öne çıkarılacak kitaplar: stokta, bayi kanalında son dönemde satan; değişim ve yeni çıkan işaretiyle."""
    end = data_end(engine)
    with engine.connect() as c:
        rows = c.execute(highlights_stmt()).all()
    new_from = (end - timedelta(days=120)).isoformat() if end else None
    items = []
    for r in rows:
        ch = (r.bayi_son - r.bayi_onceki) / r.bayi_onceki if r.bayi_onceki and r.bayi_onceki > 0 else None
        items.append({**_book_dict(r), "degisim": round(ch, 4) if ch is not None else None,
                      "yeni": bool(new_from and r.ilk_yayin and r.ilk_yayin >= new_from)})
    return {"items": items, "total": len(items), "gun": st["highlightDays"], "dataEnd": end.isoformat() if end else None}


def highlights_csv(data: dict[str, Any]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Stok kodu", "Kitap", "Yazar", "Yayınevi", "Kitaplık", "Stok", f"Bayi satışı son {data['gun']} gün",
                f"Önceki {data['gun']} gün", "Değişim", "Yeni çıkan", "Liste fiyatı", "Fiyat listesi"])
    for i in data["items"]:
        w.writerow([i["stokKodu"], i["ad"] or "", i["yazar"] or "", i["yayinevi"] or "", i["kitaplik"] or "", _n(i["stok"], 0),
                    _n(i["bayiSon"], 0), _n(i["bayiOnceki"], 0), _n(i["degisim"], 4), "evet" if i["yeni"] else "",
                    _n(i["fiyat"]), i["fiyatListe"] or ""])
    return "﻿" + buf.getvalue()


def abc_classes(values: dict[str, float], a: float = 0.80, b: float = 0.95) -> dict[str, str]:
    pos = sorted(((k, v) for k, v in values.items() if v > 0), key=lambda x: -x[1])
    total = sum(v for _, v in pos)
    out, run = {}, 0.0
    for k, v in pos:
        share_before = run / total if total else 1.0
        out[k] = "A" if share_before < a else ("B" if share_before < b else "C")
        run += v
    for k, v in values.items():
        out.setdefault(k, "C")
    return out


# ------------------------------------------------------------------------------------------ ZEKİ AI
#
# Kapalı küme kararları (segment, tema, kaybetme nedeni) LLM kapısının `choose` çağrısıyla sorulur: model yalnız verilen
# seçeneklerden birini seçer, her seçeneğin olasılığı döner (docs/analiz/llm-choose.md). Öneri yalnız olasılık ve marj
# eşiği (`CORP_LLM_MIN_PROB`, `CORP_LLM_MIN_MARGIN`) geçerse kaydedilir; insan onaylayana kadar «öneri»dir. `choose`
# bilmeyen eski istemcide düz metin cevabı kapalı kümeye eşlenir (olasılık yok).

SEGMENT_PROMPT = """Bir yayınevinin kurumsal satış ekibi müşteri kurumları gruplara ayırıyor. Aşağıdaki kurum unvanı hangi gruba girer?
(Kamu kurumu = bakanlık, belediye, valilik, kaymakamlık, müdürlük, resmî kurum; Vakıf, dernek, STK = vakıf, dernek, birlik,
sivil toplum; Okul = anaokulu, ilkokul, ortaokul, lise, kolej; Üniversite = üniversite, fakülte, enstitü; Şirket = ticari
şirket, banka, holding, fabrika.)
Kurum unvanı: {name}"""

THEME_PROMPT = """Bir yayınevinin kurumsal satış ekibi kitapları kurumlara (şirket, okul, kamu, vakıf) verilecek tema paketlerine
ayırıyor. Aşağıdaki kitap en çok hangi temaya uygun? Hiçbiri uymuyorsa «Hiçbiri» seç.
Kitap: {title}{author}
Tür: {kinds}
Yaş / hedef kitle: {ages}
Arka kapak: {summary}"""

LOSS_PROMPT = """Kurumsal satış fırsatı kaybedildi. Satış temsilcisinin yazdığı neden aşağıda. Neden hangi sınıfa girer?
(Fiyat = pahalı bulundu; Bütçe = kurumun bütçesi yok ya da ertelendi; Zamanlama = geç kalındı, dönem geçti; Rakip = başka
yayınevi ya da tedarikçi seçildi; Kitap seçimi = seçim ihtiyaca uymadı; Yanıt alınamadı = kurumdan dönüş yok.)
Neden: {text}"""

NONE_THEME = "Hiçbiri"

LETTER_PROMPT = """Bir yayınevinin kurumsal satış temsilcisi adına, kuruma gönderilecek kısa bir teklif mektubu taslağı yaz.
Türkçe, resmî ama sıcak bir dille; 3 kısa paragraf. Hitapla başla, imza satırı yazma.
KESİNLİKLE rakam, fiyat, tutar, indirim oranı, adet ya da tarih yazma: teklif tablosu belgede ayrıca yer alıyor.
Kitap adlarını ve yazarlarını olduğu gibi kullan; kitap hakkında listede olmayan bilgi uydurma.
Yayınevi: {company}
Kurum: {institution}
Fırsat: {opportunity}
Tema: {theme}
Kitaplar:
{books}
Mektup:"""


def _text_pick(answer: str, labels: list[str]) -> Optional[str]:
    """Yedek yol: düz metin cevabı etiketlerden birine kesin eşlenirse o, değilse None."""
    a = fold(answer).strip(" .:-*«»\"'")
    for lab in labels:
        if fold(lab) == a:
            return lab
    return None


def choose(llm: Any, prompt: str, labels: list[str], st: dict[str, Any]) -> dict[str, Any]:
    """{"secim": etiket | None, "olasilik": float | None, "marj": float | None, "yontem": str, "emin": bool}. Eşik altı
    seçim `emin=False` döner; çağıran kaydetmez. Model hiç cevap veremezse istisna yükselir (sonra dene)."""
    if hasattr(llm, "choose"):
        r = llm.choose(prompt, labels)
        conf = bool(r.confident(st["llmMinProb"], min_margin=st["llmMinMargin"]))
        return {"secim": r.choice, "olasilik": r.probability, "marj": r.margin, "yontem": r.method, "emin": conf and r.choice is not None}
    ans = llm.chat([{"role": "user", "content": prompt + "\nSeçenekler: " + "; ".join(labels) + "\nYalnız seçeneği aynen yaz.\nCevap:"}],
                   max_tokens=16, temperature=0.0)
    pick = _text_pick(ans or "", labels)
    # Olasılık yoksa öneri yine insan onayına gider; «emin» sayılmaz ama kayıt öneri olarak durur.
    return {"secim": pick, "olasilik": None, "marj": None, "yontem": "text" if pick else "none", "emin": pick is not None}


def ask_segment(llm: Any, name: str, st: dict[str, Any]) -> dict[str, Any]:
    labels = list(SEGMENTS.values())
    r = choose(llm, SEGMENT_PROMPT.format(name=name), labels, st)
    key = next((k for k, v in SEGMENTS.items() if v == r["secim"]), None)
    return {**r, "secim": key}


def ask_loss(llm: Any, text: str, st: dict[str, Any]) -> dict[str, Any]:
    names = {"butce": "Bütçe", "uygunluk": "Kitap seçimi", "iletisim": "Yanıt alınamadı"}
    labels = {k: names.get(k, v) for k, v in LOSS.items()}
    r = choose(llm, LOSS_PROMPT.format(text=text[:1200]), list(labels.values()), st)
    key = next((k for k, v in labels.items() if v == r["secim"]), None)
    return {**r, "secim": key}


def ask_theme(llm: Any, book: Any, vocab: list[str], st: dict[str, Any]) -> dict[str, Any]:
    """Kitabın en uygun tek teması (kapalı liste + «Hiçbiri»). Birden çok tema insan tarafından eklenir."""
    ages = " · ".join(x for x in (book.hedef, book.yaslar,
                                  f"{book.yas_min}–{book.yas_max} yaş" if book.yas_min or book.yas_max else None) if x) or "-"
    prompt = THEME_PROMPT.format(title=book.ad or book.stok_kodu, author=f" — {book.yazar}" if book.yazar else "",
                                 kinds=book.turler or book.kitaplik or "-", ages=ages, summary=(book.ozet or "-")[:700])
    r = choose(llm, prompt, list(vocab) + [NONE_THEME], st)
    if r["secim"] == NONE_THEME:
        r["secim"] = None
    return r


def draft_letter(llm: Any, st: dict[str, Any], opp: dict[str, Any], lines: list[dict[str, Any]]) -> str:
    books = "\n".join(f"- {l.get('ad') or l['stok']}" + (f" ({l['yazar']})" if l.get("yazar") else "") for l in lines)
    prompt = LETTER_PROMPT.format(company=st["company"], institution=opp["kurum"], opportunity=opp["ad"],
                                  theme=opp.get("tema") or "-", books=books)
    text = (llm.chat([{"role": "user", "content": prompt}], max_tokens=700, temperature=0.3) or "").strip()
    # Model rakam yazdıysa o satırlar atılır: tutar ve adet yalnız tablodan gelir.
    if re.search(r"\d", text):
        text = re.sub(r"[^\n]*\d[^\n]*\n?", "", text).strip()
    return text[:8000]


def run_model_tasks(engine: sa.engine.Engine, tenant: str, st: dict[str, Any], llm: Any, budget_sec: int) -> dict[str, Any]:
    """Gece: segment önerisi, tema önerisi, kaybetme nedeni sınıfı. Süre dolunca kalan sonraki geceye kalır."""
    out: dict[str, Any] = {"segment": 0, "tema": 0, "kayip": 0, "eminDegil": 0, "kalan": {}}
    if llm is None or budget_sec <= 0:
        out["atlandi"] = "model tanımlı değil" if llm is None else "süre 0"
        return out
    t0 = time.monotonic()

    def left() -> bool:
        return time.monotonic() - t0 < budget_sec

    with engine.connect() as c:
        accs = c.execute(sa.select(ACCOUNTS.c.ref, ACCOUNTS.c.unvan).where(
            ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.segment.is_(None), ACCOUNTS.c.segment_asked_at.is_(None))).all()
    for a in accs:
        if not left():
            break
        try:
            r = ask_segment(llm, a.unvan or a.ref, st)
        except Exception as e:  # noqa: BLE001 — model düşerse kalan sonraki geceye
            log.warning("corporate: segment önerisi alınamadı: %s", e)
            break
        ok = r["emin"] and r["secim"]
        out["eminDegil"] += 0 if ok else 1
        with engine.begin() as c:
            c.execute(ACCOUNTS.update().where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.ref == a.ref, ACCOUNTS.c.segment.is_(None))
                      .values(segment=r["secim"] if ok else None, segment_kaynak="oneri" if ok else None,
                              segment_olasilik=r["olasilik"] if ok else None, segment_asked_at=_now()))
        out["segment"] += 1

    vocab = vocabulary(engine, st)
    with engine.connect() as c:
        tagged = {r[0] for r in c.execute(sa.select(THEMES.c.stok_kodu).distinct()).all()}
        asked = {r[0] for r in c.execute(sa.select(THEME_ASKED.c.stok_kodu)).all()}
        books = [b for b in c.execute(sa.select(BOOKS).where(BOOKS.c.stok > 0, BOOKS.c.in_crm.is_(True))
                                      .order_by(BOOKS.c.yil_adet.desc())).all()
                 if b.stok_kodu not in tagged and b.stok_kodu not in asked]
    for b in books:
        if not left() or not vocab:
            break
        try:
            r = ask_theme(llm, b, vocab, st)
        except Exception as e:  # noqa: BLE001
            log.warning("corporate: tema önerisi alınamadı: %s", e)
            break
        now = _now()
        with engine.begin() as c:
            if r["secim"] and r["emin"]:
                if not c.execute(sa.select(THEMES.c.tema).where(THEMES.c.stok_kodu == b.stok_kodu, THEMES.c.tema == r["secim"])).first():
                    c.execute(THEMES.insert().values(stok_kodu=b.stok_kodu, tema=r["secim"], kaynak="oneri", durum="onerildi",
                                                     olasilik=r["olasilik"], zaman=now))
            else:
                out["eminDegil"] += 1
            note = f"{r['secim'] or 'yok'} · {r['yontem']}" + (f" · p={r['olasilik']:.2f}" if r["olasilik"] is not None else "")
            c.execute(THEME_ASKED.insert().values(stok_kodu=b.stok_kodu, at=now, sonuc=note[:400]))
        out["tema"] += 1

    with engine.connect() as c:
        lost = c.execute(sa.select(OPPS.c.id, OPPS.c.kaybetme_nedeni).where(
            OPPS.c.tenant_id == tenant, OPPS.c.asama == "kaybedildi", OPPS.c.kayip_sinif.is_(None),
            OPPS.c.kaybetme_nedeni.isnot(None))).all()
    for o in lost:
        if not left():
            break
        try:
            r = ask_loss(llm, o.kaybetme_nedeni or "", st)
        except Exception as e:  # noqa: BLE001
            log.warning("corporate: neden sınıfı alınamadı: %s", e)
            break
        if r["secim"] and r["emin"]:
            with engine.begin() as c:
                c.execute(OPPS.update().where(OPPS.c.id == o.id, OPPS.c.kayip_sinif.is_(None))
                          .values(kayip_sinif=r["secim"], kayip_sinif_kaynak="oneri"))
            out["kayip"] += 1
        else:
            out["eminDegil"] += 1
    with engine.connect() as c:
        out["kalan"] = {
            "segment": c.execute(sa.select(sa.func.count()).select_from(ACCOUNTS).where(
                ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.segment.is_(None), ACCOUNTS.c.segment_asked_at.is_(None))).scalar() or 0,
            "tema": max(0, len(books) - out["tema"])}
    return out


# ------------------------------------------------------------------------------------------ okuma (Logo + CRM → köprü)


def logged(run: src.Runner, conn: str, sink: list[dict[str, Any]], purpose: dict[str, str]) -> src.Runner:
    """Okumada ÇALIŞAN her SQL'i (değerleri yerinde) amaç etiketi, satır sayısı, süre ve anıyla kaydeder. Sonuç satırı
    kaydedilmez (kişisel veri); kayıt `semantic_corp_meta` «sorgular»a yazılır ve ekrandaki sorgu bilgisinde tabloyu
    dolduran asıl sorgu (köken) olarak gösterilir. `purpose["p"]` okumayı yapan adımın etiketidir (ör. «kurumSatis»)."""
    def go(sql: str) -> list[dict[str, Any]]:
        t = time.monotonic()
        rows = run(sql)
        sink.append({"conn": conn, "tag": purpose.get("p") or "diger", "sql": sql, "rows": len(rows),
                     "dbMs": int((time.monotonic() - t) * 1000), "at": _iso(_now())})
        return rows
    return go


def merge_queries(ran: list[dict[str, Any]], prev: dict[str, Any]) -> list[dict[str, Any]]:
    """Yarıda kalan okumada: bu turda çalışan etiketlerin sorguları yenisiyle, hiç çalışmayan etiketlerinki öncekiyle
    kalır (o tabloları önceki okuma doldurmuştur)."""
    tags = {q["tag"] for q in ran}
    return ran + [q for q in prev.get("items") or [] if q.get("tag") not in tags]


class Refresher:
    """Logo/CRM okumasını arka planda yapar; aynı anda tek okuma."""

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
        return {**self.state, "last": meta_get(engine, "refresh"), "dataEnd": meta_get(engine, "data_end").get("date")}

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> bool:
        with self._guard:
            if self.running():
                return False
            self.state.update(running=True, step="Başlıyor", startedAt=time.time(), error=None)
            self._thread = threading.Thread(target=self.run, daemon=True, name="corporate-refresh")
            self._thread.start()
            return True

    def _step(self, name: str) -> None:
        self.state["step"] = name

    def run(self) -> dict[str, Any]:
        engine, tenant, st = self._engine(), self._tenant(), self._settings()
        ensure(engine)
        done: dict[str, Any] = {}
        warnings: list[str] = []
        t0 = time.monotonic()
        ran: list[dict[str, Any]] = []      # sorgu bilgisi: bu turda çalışan her Logo/CRM SQL'i (sonuç satırı değil)
        why = {"p": "donem"}
        try:
            self.state.update(running=True, step="Logo dönemleri", error=None)
            channel = src.channel_list(st["channel"])[0]
            dealers_ch = src.channel_list(",".join(st["dealerChannels"]))
            logo = logged(src.runner(self._logo()), "logo", ran, why)
            firms = src.firms_by_year(logo)
            why["p"] = "veriSonu"
            end = src.read_data_end(logo, firms) or today()
            meta_set(engine, "data_end", {"date": end.isoformat()})

            self._step("Kurum carileri")
            why["p"] = "kurumCari"
            logo_accs = src.read_accounts(logo, firms, channel)
            since = date(end.year - st["historyYears"] + 1, 1, 1)
            self._step("Kurum alım geçmişi")
            why["p"] = "kurumSatis"
            sales = src.read_channel_sales(logo, firms, [channel], since, end + timedelta(days=1))
            with engine.begin() as c:
                c.execute(SALES.delete())
                rows = [{"logo_code": s["kod"], "year": s["yil"], "month": s["ay"], "ciro": round(s["ciro"], 2), "adet": s["adet"],
                         "fatura": s["fatura"], "son": s["son"].isoformat() if s.get("son") else None} for s in sales]
                for i in range(0, len(rows), 5000):
                    c.execute(SALES.insert(), rows[i:i + 5000])
            done["kurumSatis"] = len(rows)

            crm_accs: list[dict[str, Any]] = []
            schema = self._schema()
            crm_run = None
            try:
                self._step("CRM kurum kartları")
                why["p"] = "crmKurum"
                crm_run = logged(src.runner(self._crm()), "crm", ran, why)
                crm_accs = src.read_crm_accounts(crm_run, schema)
            except src.SourceError as e:
                warnings.append(f"CRM okunamadı: {e}")
            self._merge_accounts(engine, tenant, logo_accs, crm_accs, rows)
            done["kurum"] = len(logo_accs)

            self._step("Hacim indirimi geçmişi")
            why["p"] = "hacim"
            inv = src.read_invoice_discounts(logo, firms, [channel], end - timedelta(days=365), end + timedelta(days=1))
            meta_set(engine, "volume", {"buckets": measured_discounts(inv, st["volumeBuckets"], st["volumeMinN"]),
                                        "faturalar": len(inv), "pencere": [(end - timedelta(days=365)).isoformat(), end.isoformat()]})

            self._step("Kitaplar: stok, fiyat")
            why["p"] = "stok"
            stock = src.read_stock(logo, firms)
            why["p"] = "fiyat"
            prices = src.read_prices(logo, firms, today())
            why["p"] = "bayiKitap"
            ch_items = src.read_channel_items(logo, firms, dealers_ch, end, st["highlightDays"])
            why["p"] = "maliyet"
            costs = src.read_last_costs(logo, firms) if st["costSource"] == "logo" else {}
            crm_books: dict[str, dict[str, Any]] = {}
            crm_themes: dict[str, list[str]] = {}
            if crm_run is not None:
                try:
                    self._step("CRM kitap kartları ve temalar")
                    why["p"] = "crmKitap"
                    crm_books = src.read_crm_books(crm_run, schema)
                    why["p"] = "crmTema"
                    crm_themes = src.read_crm_book_themes(crm_run, schema)
                    why["p"] = "crmTemaAdlari"
                    meta_set(engine, "crm_themes", {"names": src.read_crm_theme_names(crm_run, schema)})
                except src.SourceError as e:
                    warnings.append(f"CRM kitap kartı okunamadı: {e}")
            self._write_books(engine, stock, prices, ch_items, costs, crm_books, crm_themes)
            done["kitap"] = len(set(stock) | set(crm_books))
            done["fiyatli"] = len(prices)

            self._step("Bayiler")
            win_a, win_b = end - timedelta(days=365), end + timedelta(days=1)
            why["p"] = "bayiFatura"
            dinv = src.read_dealer_invoices(logo, firms, dealers_ch, win_a, win_b)
            why["p"] = "bayiSatis"
            dsales = src.read_channel_sales(logo, firms, dealers_ch, win_a, win_b, invoices=False)
            b2b, users = ({}, {}), ({}, {})
            if crm_run is not None:
                try:
                    why["p"] = "crmB2b"
                    b2b = src.read_crm_b2b(crm_run, schema, st["b2bDays"])
                    why["p"] = "crmWeb"
                    users = src.read_crm_webusers(crm_run, schema)
                except src.SourceError as e:
                    warnings.append(f"CRM B2B siparişleri okunamadı: {e}")
            n_dealers = self._write_dealers(engine, dinv, dsales, b2b, users, crm_run is not None and not any("B2B" in w for w in warnings))
            done["bayi"] = n_dealers
            meta_set(engine, "dealers", {"b2bGun": st["b2bDays"], "crm": crm_run is not None, "okundu": _now().isoformat()})

            self._step("Dönemsel hatırlatmalar")
            done["hatirlatma"] = generate_reminders(engine, tenant, st)
            meta_set(engine, "sorgular", {"items": ran})
            meta_set(engine, "refresh", {"ok": True, "done": done, "warnings": warnings, "sn": round(time.monotonic() - t0, 1)})
            self.state.update(running=False, step=None, error=None, finishedAt=time.time())
            return {"ok": True, "done": done, "warnings": warnings, "dataEnd": end.isoformat()}
        except Exception as e:  # noqa: BLE001 — eski veriler kalır, hata ekranda
            log.warning("corporate refresh failed: %s", e)
            msg = str(e) if isinstance(e, (src.SourceError, CorporateError)) else f"Okuma hata verdi: {str(e)[:200]}"
            if ran:
                meta_set(engine, "sorgular", {"items": merge_queries(ran, meta_get(engine, "sorgular"))})
            meta_set(engine, "refresh", {"ok": False, "error": msg, "done": done, "warnings": warnings})
            self.state.update(running=False, step=None, error=msg, finishedAt=time.time())
            return {"ok": False, "error": msg, "done": done}

    # -------------------------------------------------------------- yazma parçaları

    @staticmethod
    def _merge_accounts(engine: sa.engine.Engine, tenant: str, logo_accs: list[dict[str, Any]], crm_accs: list[dict[str, Any]],
                        sales_rows: list[dict[str, Any]]) -> None:
        by_code = {a["kod"]: a for a in crm_accs if a.get("kod")}
        by_ref = {a["ref"]: a for a in crm_accs if a.get("ref")}
        first: dict[str, str] = {}
        last: dict[str, str] = {}
        for s in sales_rows:
            if s["ciro"] <= 0 and not s["fatura"]:
                continue
            ym = f"{s['year']:04d}-{s['month']:02d}-01"
            first[s["logo_code"]] = min(first.get(s["logo_code"], ym), ym)
            d = s.get("son") or ym
            last[s["logo_code"]] = max(last.get(s["logo_code"], d), d)
        with engine.connect() as c:
            old = {r.ref: r for r in c.execute(sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant)).all()}
        now = _now()
        rows: list[dict[str, Any]] = []
        used_crm: set[str] = set()

        def carry(ref: str, crm: Optional[dict[str, Any]]) -> dict[str, Any]:
            o = old.get(ref)
            crm_seg = src.CRM_ROLE_SEGMENT.get(crm.get("rol")) if crm else None
            if o is not None and o.segment_kaynak == "elle":
                return {"segment": o.segment, "segment_kaynak": "elle", "segment_olasilik": None, "segment_by": o.segment_by,
                        "segment_at": o.segment_at, "segment_asked_at": o.segment_asked_at}
            if crm_seg:
                return {"segment": crm_seg, "segment_kaynak": "crm", "segment_olasilik": None, "segment_by": None, "segment_at": now,
                        "segment_asked_at": o.segment_asked_at if o else None}
            if o is not None:
                return {"segment": o.segment, "segment_kaynak": o.segment_kaynak, "segment_olasilik": o.segment_olasilik,
                        "segment_by": o.segment_by, "segment_at": o.segment_at, "segment_asked_at": o.segment_asked_at}
            return {"segment": None, "segment_kaynak": None, "segment_olasilik": None, "segment_by": None, "segment_at": None,
                    "segment_asked_at": None}

        def crm_fields(crm: Optional[dict[str, Any]]) -> dict[str, Any]:
            if not crm:
                return {"crm_account_id": None, "crm_rol": None, "temsilci": None, "temsilci_hesap": None, "eposta_izni": None}
            return {"crm_account_id": crm["id"], "crm_rol": crm.get("rol"), "temsilci": crm.get("temsilci"),
                    "temsilci_hesap": crm.get("temsilciHesap"), "eposta_izni": bool(crm.get("iys")) and not crm.get("epostaYok")}

        for a in logo_accs:
            crm = by_code.get(a["kod"]) or (by_ref.get(a["ref"]) if a.get("ref") else None)
            if crm:
                used_crm.add(crm["id"])
            rows.append({"tenant_id": tenant, "ref": a["kod"], "logo_code": a["kod"], "logo_clientref": a.get("ref"),
                         "unvan": a.get("unvan") or (crm or {}).get("unvan"), "il": a.get("il"), "kanal": a.get("kanal"),
                         "iskonto": a.get("iskonto"), "pasif": bool(a.get("pasif")), "ilk_alim": first.get(a["kod"]),
                         "son_alim": last.get(a["kod"]), "asof": now, **crm_fields(crm), **carry(a["kod"], crm)})
        seen = {r["ref"] for r in rows}
        for crm in crm_accs:
            if crm["id"] in used_crm:
                continue
            ref = crm.get("kod") or f"crm-{crm['id']}"
            if ref in seen:
                continue
            seen.add(ref)
            rows.append({"tenant_id": tenant, "ref": ref[:60], "logo_code": crm.get("kod"), "logo_clientref": crm.get("ref"),
                         "unvan": crm.get("unvan"), "il": None, "kanal": "CRM" if not crm.get("kod") else None, "iskonto": None,
                         "pasif": False, "ilk_alim": first.get(crm.get("kod") or ""), "son_alim": last.get(crm.get("kod") or ""),
                         "asof": now, **crm_fields(crm), **carry(ref, crm)})
        with engine.begin() as c:
            c.execute(ACCOUNTS.delete().where(ACCOUNTS.c.tenant_id == tenant))
            for i in range(0, len(rows), 2000):
                c.execute(ACCOUNTS.insert(), rows[i:i + 2000])

    @staticmethod
    def _write_books(engine: sa.engine.Engine, stock: dict[str, dict[str, Any]], prices: dict[str, dict[str, Any]],
                     ch_items: dict[str, dict[str, float]], costs: dict[str, dict[str, Any]],
                     crm_books: dict[str, dict[str, Any]], crm_themes: dict[str, list[str]]) -> None:
        rows = []
        for code in sorted(set(stock) | set(crm_books)):
            s, p, b, ch, cost = stock.get(code) or {}, prices.get(code) or {}, crm_books.get(code) or {}, ch_items.get(code) or {}, costs.get(code) or {}
            ilk = b.get("ilkYayin")
            rows.append({"stok_kodu": code[:60], "ad": (b.get("ad") or s.get("ad") or "")[:400] or None, "yazar": b.get("yazar"),
                         "yayinevi": b.get("yayinevi"), "kitaplik": b.get("kitaplik"), "turler": b.get("turler"), "yaslar": b.get("yaslar"),
                         "hedef": b.get("hedef"), "yas_min": b.get("yasMin"), "yas_max": b.get("yasMax"),
                         "ilk_yayin": ilk.isoformat() if isinstance(ilk, date) else ilk, "ozet": b.get("ozet"),
                         "stok": float(s.get("bakiye") or 0.0), "yil_adet": float(s.get("yil_adet") or 0.0),
                         "fiyat": p.get("fiyat"), "fiyat_liste": p.get("liste"), "fiyat_liste_sayisi": p.get("listeSayisi"),
                         "fiyat_kdv_dahil": p.get("kdvDahil"), "crm_fiyat": b.get("crmFiyat"),
                         "bayi_son": float(ch.get("son") or 0.0), "bayi_onceki": float(ch.get("onceki") or 0.0),
                         "maliyet_logo": cost.get("birim"), "maliyet_logo_tarih": cost.get("tarih"),
                         "in_logo": code in stock, "in_crm": code in crm_books})
        now = _now()
        with engine.begin() as c:
            c.execute(BOOKS.delete())
            for i in range(0, len(rows), 5000):
                c.execute(BOOKS.insert(), rows[i:i + 5000])
            if crm_books:  # CRM okunduysa CRM tema bağları CRM'deki hâline eşitlenir; öneri/elle satırlarına dokunulmaz
                c.execute(THEMES.delete().where(THEMES.c.kaynak == "crm"))
                trows = []
                for code, names in crm_themes.items():
                    for t in names:
                        trows.append({"stok_kodu": code[:60], "tema": t[:120], "kaynak": "crm", "durum": "onayli", "zaman": now})
                existing = {(r.stok_kodu, r.tema) for r in c.execute(sa.select(THEMES.c.stok_kodu, THEMES.c.tema)).all()}
                for r in trows:
                    if (r["stok_kodu"], r["tema"]) in existing:  # öneri/elle ile aynı tema CRM'de de varsa CRM kazanır
                        c.execute(THEMES.delete().where(THEMES.c.stok_kodu == r["stok_kodu"], THEMES.c.tema == r["tema"]))
                    c.execute(THEMES.insert().values(**r))

    @staticmethod
    def _write_dealers(engine: sa.engine.Engine, dinv: dict[str, dict[str, Any]], dsales: list[dict[str, Any]],
                       b2b: tuple[dict[str, float], dict[int, float]], users: tuple[dict[str, float], dict[int, float]],
                       crm_ok: bool) -> int:
        ciro: dict[str, float] = {}
        for s in dsales:
            ciro[s["kod"]] = ciro.get(s["kod"], 0.0) + s["ciro"]
        classes = abc_classes({k: ciro.get(k, 0.0) for k in dinv})
        rows = []
        for code, d in dinv.items():
            ref = d.get("ref")
            b2b_n = b2b[0].get(code, b2b[1].get(ref, 0.0) if ref else 0.0)
            usr_n = users[0].get(code, users[1].get(ref, 0.0) if ref else 0.0)
            rows.append({"logo_code": code, "logo_clientref": ref, "unvan": d.get("unvan"), "kanal": d.get("kanal"), "il": d.get("il"),
                         "son_fatura": d["son"].isoformat() if d.get("son") else None, "fatura_12ay": int(d.get("fatura") or 0),
                         "ciro_12ay": round(ciro.get(code, 0.0), 2), "sinif": classes.get(code),
                         "b2b_siparis": int(b2b_n) if crm_ok else None, "b2b_kullanici": int(usr_n) if crm_ok else None})
        with engine.begin() as c:
            c.execute(DEALERS.delete())
            for i in range(0, len(rows), 5000):
                c.execute(DEALERS.insert(), rows[i:i + 5000])
        return len(rows)


def dealer_detail(engine: sa.engine.Engine, run: src.Runner, firms: dict[int, str], code: str) -> dict[str, Any]:
    """Bayinin son 12 ayda aldığı kitaplar (kitaplık karması) ve bayi kanalında satıp bu bayinin almadığı stoktaki kitaplar."""
    end = data_end(engine)
    if not end:
        raise CorporateError("Veriler henüz okunmadı.", 409)
    with engine.connect() as c:
        d = c.execute(dealers_stmt(code)).first()
        if not d:
            raise CorporateError("Bayi bulunamadı.", 404)
        books = {r.stok_kodu: r for r in c.execute(books_stmt()).all()}
    items = src.read_client_items(run, firms, code, end - timedelta(days=365), end + timedelta(days=1))
    mix: dict[str, dict[str, Any]] = {}
    bought = []
    for stok, it in items.items():
        b = books.get(stok)
        shelf = (b.kitaplik if b else None) or "Kitaplığı bilinmiyor"
        m = mix.setdefault(shelf, {"kitaplik": shelf, "adet": 0.0, "ciro": 0.0, "kitap": 0})
        m["adet"] += it["adet"]
        m["ciro"] += it["ciro"]
        m["kitap"] += 1
        bought.append({"stokKodu": stok, "ad": (b.ad if b else None) or it.get("ad"), "kitaplik": shelf, "adet": it["adet"],
                       "ciro": round(it["ciro"], 2), "son": it["son"].isoformat() if it.get("son") else None})
    gaps = [_book_dict(b) for b in sorted(books.values(), key=lambda x: -(x.bayi_son or 0))
            if (b.bayi_son or 0) > 0 and (b.stok or 0) > 0 and b.stok_kodu not in items]
    return {"logoKod": code, "unvan": d.unvan, "kanal": d.kanal, "il": d.il, "sonFatura": d.son_fatura,
            "kitaplik": sorted(mix.values(), key=lambda x: -x["ciro"]), "alinan": sorted(bought, key=lambda x: -x["ciro"]),
            "eksik": gaps, "dataEnd": end.isoformat()}


# ------------------------------------------------------------------------------------------ özet


def ytd_sales_stmt(w: dict[str, Any]) -> sa.Select:
    """Kurum cirosu kartı: bu yıl ve geçen yılın aynı aylarındaki kurum alım satırları (yıl, ay, net ciro)."""
    return (sa.select(SALES.c.year, SALES.c.month, SALES.c.ciro)
            .where(SALES.c.year.in_((w["year"], w["year"] - 1)), SALES.c.month <= w["months"]))


def accounts_count_stmt(tenant: str) -> sa.Select:
    return sa.select(sa.func.count().label("sayi")).select_from(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant)


def open_opps_stmt(tenant: str) -> sa.Select:
    """Açık fırsatlar (Aday, Görüşüldü, Teklif, Karar): sahip ve tahmini değer."""
    return sa.select(OPPS.c.sahip, OPPS.c.deger, OPPS.c.asama).where(OPPS.c.tenant_id == tenant, OPPS.c.asama.in_(OPEN_STAGES))


def pending_quotes_count_stmt(tenant: str) -> sa.Select:
    return (sa.select(sa.func.count().label("sayi")).select_from(QUOTES)
            .where(QUOTES.c.tenant_id == tenant, QUOTES.c.durum == "onayda"))


def theme_suggestions_count_stmt() -> sa.Select:
    return sa.select(sa.func.count().label("sayi")).select_from(THEMES).where(THEMES.c.durum == "onerildi")


def summary(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, st: dict[str, Any]) -> dict[str, Any]:
    end = data_end(engine)
    w = ytd_window(end)
    cur = prev = 0.0
    with engine.connect() as c:
        if w:
            for r in c.execute(ytd_sales_stmt(w)).all():
                if r.year == w["year"]:
                    cur += r.ciro
                else:
                    prev += r.ciro
        n_acc = c.execute(accounts_count_stmt(tenant)).scalar() or 0
        opps = c.execute(open_opps_stmt(tenant)).all()
        pending = c.execute(pending_quotes_count_stmt(tenant)).scalar() or 0
        pend_themes = c.execute(theme_suggestions_count_stmt()).scalar() or 0
    mine = [o for o in opps if see_all or (o.sahip or "").lower() == user.lower()]
    rem = list_reminders(engine, tenant, st, durum="acik")
    dealers = dealer_rows(engine, gun=st["silentDays"])
    return {"dataEnd": end.isoformat() if end else None, "window": w, "kurumCiro": round(cur, 2), "kurumCiroGecenYil": round(prev, 2),
            "kurumSayisi": n_acc, "acikFirsat": len(mine), "acikFirsatDeger": round(sum(o.deger or 0 for o in mine), 2),
            "onayBekleyen": pending, "temaOnerisi": pend_themes, "hatirlatma": len(rem["items"]),
            "hatirlatmaTutar": rem["toplamGecenYil"], "sessizBayi": dealers["counts"]["sessiz"], "bayi": len(dealers["items"])}
