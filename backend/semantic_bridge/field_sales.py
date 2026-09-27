"""M30 Saha satış yönetimi ve tahsilat (BMT): portföy, sinyaller, ziyaret önceliği, müşteri brifingi, tahsilat listeleri,
ziyaret notu, ödeme planı önerisi ve onayı, haftalık saha raporu.

**Akış.** Gece turu (`run_due('gece')`, 06:30) CRM'den temsilci ↔ cari atamasını, Logo'dan bakiye/yaşlandırma, satış, ödeme,
çek olaylarını okur; her müşteri carisi için bir sinyal satırı yazar (`semantic_field_portfolio`, `semantic_field_signals`;
tam değiştirme, sessiz tavan yok). Ekranlar bu tablolardan okur (telefonda hızlı); brifing ayrıca tek carinin son faturalarını,
kitap kırılımını ve CRM siparişlerini canlı okur (5 dk bellek). Hafif tur (`'hafif'`, 15 dk) CRM tahsilat durum değişimini ve
riske takılan siparişi portal içi bildirime çevirir. Haftalık tur (`'haftalik'`, pazartesi) saha raporunu e-postalar.

**Öncelik (K2, kural; ağırlıklar ekranda):** `WEIGHTS`. Model puan vermez; yalnız brifingde 3 cümlelik özet yazar ve
reddedilen tahsilatın serbest metin nedenini kapalı kümeye sınıflar (LLM kapısı `llm_for("saha")`). Özetteki her sayı
verilen olgularda geçmek zorunda (`numbers_ok`); geçmezse kural özeti gösterilir. Rakamı model üretmez.

**Kapsam:** kişi yalnız kendi carilerini görür (`semantic_field_portfolio.ad_hesap = oturum`); `ozellik:saha.herkesinki`
(açıkça verilir) bütün temsilcileri açar. Temsilci karşılaştırması `ozellik:saha.performans` (açıkça verilir).

**Yazma:** CRM'e ve Logo'ya hiçbir şey yazılmaz. Ziyaret/not ortak tablo `semantic_saha_ziyaret` (M31 ile ortak: `tur='okul'`),
ödeme planı `semantic_field_payment_plans` (yalnız kayıt; müşteriyle anlaşma ve Logo/CRM işlemi insanın), müdür önceliği
`semantic_field_overrides`. Her yazma `semantic_audit`'e düşer (uçta).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import field_sales_sources as src
from semantic_bridge.field_sales_sources import SourceError, day, guid, num, opt_num, text

log = logging.getLogger("semantic.field")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()
_lock = threading.Lock()
_ready: set[int] = set()
MAX_ROWS = 2_000_000  # güvenlik ağı; aşılırsa hata verilir, sessizce kesilmez


class FieldError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ tablolar

PORTFOLIO = sa.Table(
    "semantic_field_portfolio", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("logo_code", sa.String(40), primary_key=True),
    sa.Column("systemuser_id", sa.String(40)),
    sa.Column("ad_hesap", sa.String(120), index=True),
    sa.Column("temsilci_ad", sa.String(200)),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("logo_clientref", sa.Integer),
    sa.Column("unvan", sa.String(300)),
    sa.Column("il", sa.String(100)),
    sa.Column("kanal", sa.String(60)),
    sa.Column("logo_il", sa.String(100)),                       # Logo CLCARD.CITY (benzer cari eşleşmesi)
    sa.Column("logo_kanal", sa.String(60)),                     # Logo CLCARD.SPECODE2
    sa.Column("atama_kaynagi", sa.String(10)),                  # owner | il | slsman
    sa.Column("asof", sa.String(10), nullable=False),
)
SIGNALS = sa.Table(
    "semantic_field_signals", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("logo_code", sa.String(40), primary_key=True),
    sa.Column("logo_clientref", sa.Integer),
    sa.Column("asof", sa.String(10), nullable=False),
    sa.Column("bakiye", sa.Float), sa.Column("vadesi_gecmis", sa.Float), sa.Column("gelmemis", sa.Float),
    sa.Column("plansiz", sa.Float),
    sa.Column("k_1_30", sa.Float), sa.Column("k_31_60", sa.Float), sa.Column("k_61_90", sa.Float), sa.Column("k_90p", sa.Float),
    sa.Column("son_odeme_tarihi", sa.String(10)), sa.Column("odeme_12ay", sa.Float),
    sa.Column("karsiliksiz_olay_12ay", sa.Integer), sa.Column("protesto_olay_12ay", sa.Integer), sa.Column("cek_olay_tutar", sa.Float),
    sa.Column("risk_toplam", sa.Float), sa.Column("limit_toplam", sa.Float), sa.Column("risk_doluluk", sa.Float),
    sa.Column("siparis_riskte", sa.Integer), sa.Column("siparis_riskte_sebep", sa.String(60)),
    sa.Column("ytd_net_ciro", sa.Float), sa.Column("gecen_yil_ayni_donem", sa.Float), sa.Column("gecen_yil_tam", sa.Float),
    sa.Column("iade_orani", sa.Float), sa.Column("son_fatura", sa.String(10)),
    sa.Column("hedef_yil", sa.Float), sa.Column("hedef_beklenen", sa.Float), sa.Column("hedef_acigi", sa.Float),
    sa.Column("hedef_kaynagi", sa.String(10)),
    sa.Column("saha_son_ziyaret", sa.String(10)), sa.Column("saha_tahsilat_json", sa.Text),
    sa.Column("oncelik_puani", sa.Float), sa.Column("gerekce_json", sa.Text),
)
BRIEFS = sa.Table(
    "semantic_field_briefs", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("logo_code", sa.String(40), primary_key=True),
    sa.Column("asof", sa.String(10), primary_key=True),
    sa.Column("girdi_hash", sa.String(64), nullable=False),
    sa.Column("ozet_metin", sa.Text, nullable=False),
    sa.Column("oneri_kitaplar_json", sa.Text),
    sa.Column("model_is_kimligi", sa.String(80)),               # "kural" ya da LLM kapısı iş kimliği / model adı
    sa.Column("olusturan", sa.String(120)),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
)
#: M30/M31 ortak ziyaret tablosu (hangisi önce kodlanırsa açar; M30 açtı). `tur`: cari | okul | kurum.
VISITS = sa.Table(
    "semantic_saha_ziyaret", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(10), nullable=False),
    sa.Column("hedef_kimlik", sa.String(60), nullable=False),    # cari: Logo cari kodu · okul: CRM ziyaret yeri · kurum: CRM cari
    sa.Column("hedef_ad", sa.String(300)),
    sa.Column("sahip", sa.String(120), nullable=False),          # AD hesabı
    sa.Column("planlanan", sa.String(19)),                       # YYYY-MM-DD ya da YYYY-MM-DDTHH:MM (İstanbul)
    sa.Column("gerceklesen", sa.String(19)),
    sa.Column("durum", sa.String(12), nullable=False),           # planlandi | yapildi | iptal
    sa.Column("notu", sa.Text),
    sa.Column("ton", sa.String(12)),                             # olumlu | notr | olumsuz
    sa.Column("sonraki_adim", sa.String(500)),
    sa.Column("sonraki_tarih", sa.String(10)),
    sa.Column("soz_odeme_tarihi", sa.String(10)),
    sa.Column("soz_odeme_tutari", sa.Float),
    sa.Column("gizli", sa.Boolean, nullable=False, default=False),
    sa.Column("eslik_eden_bayi", sa.String(40)),                 # M31: okul ziyaretine eşlik eden bayinin Logo cari kodu
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
    sa.Index("ix_semantic_saha_ziyaret_hedef", "tenant_id", "tur", "hedef_kimlik"),
    sa.Index("ix_semantic_saha_ziyaret_sahip", "tenant_id", "sahip"),
)
PLANS = sa.Table(
    "semantic_field_payment_plans", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("logo_code", sa.String(40), nullable=False),
    sa.Column("unvan", sa.String(300)),
    sa.Column("temsilci", sa.String(120)),
    sa.Column("tutar", sa.Float, nullable=False),
    sa.Column("taksitler_json", sa.Text, nullable=False),
    sa.Column("gerekce", sa.Text),
    sa.Column("durum", sa.String(12), nullable=False),           # taslak | onayda | onayli | reddedildi
    sa.Column("oneren", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("gonderen", sa.String(120)),
    sa.Column("gonderim", sa.DateTime(timezone=True)),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("zaman", sa.DateTime(timezone=True)),
    sa.Column("karar_notu", sa.Text),
)
OVERRIDES = sa.Table(
    "semantic_field_overrides", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("logo_code", sa.String(40), nullable=False),
    sa.Column("neden", sa.String(300), nullable=False),
    sa.Column("bitis", sa.String(10)),
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
)
EVENTS = sa.Table(
    "semantic_field_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("sahip", sa.String(120), nullable=False),
    sa.Column("tur", sa.String(20), nullable=False),             # tahsilat-red | siparis-risk | cek-olay | plan-onay | plan-karar
    sa.Column("anahtar", sa.String(80), nullable=False),         # aynı olay iki kez yazılmasın
    sa.Column("baslik", sa.String(300), nullable=False),
    sa.Column("detay", sa.Text),
    sa.Column("logo_code", sa.String(40)),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
    sa.Column("goruldu", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("tenant_id", "sahip", "tur", "anahtar", name="uq_semantic_field_events_key"),
    sa.Index("ix_semantic_field_events_sahip", "tenant_id", "sahip"),
)
REASONS = sa.Table(
    "semantic_field_reason_labels", _md,
    sa.Column("tahsilat_id", sa.String(40), primary_key=True),
    sa.Column("etiket", sa.Integer, nullable=False),              # REJECT_REASON kodu
    sa.Column("olasilik", sa.Float),
    sa.Column("kaynak", sa.String(20), nullable=False),           # zeki
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)
META = sa.Table(
    "semantic_field_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(60), primary_key=True),
    sa.Column("value_json", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return str(v)


def fold(s: Optional[str]) -> str:
    """Türkçe harf duyarsız arama anahtarı."""
    t = (s or "").replace("İ", "i").replace("I", "ı").lower()
    return t.translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))


def _j(s: Any, default: Any) -> Any:
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError):
        return default


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _new_id() -> str:
    return uuid.uuid4().hex


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> dict[str, Any]:
    with engine.connect() as c:
        row = c.execute(sa.select(META).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    return {**_j(row.value_json, {}), "_at": _iso(row.updated_at)} if row else {}


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: dict[str, Any]) -> None:
    with engine.begin() as c:
        cond = (META.c.tenant_id == tenant, META.c.key == key)
        if c.execute(sa.select(META.c.key).where(*cond)).first():
            c.execute(META.update().where(*cond).values(value_json=_dump(value), updated_at=_now()))
        else:
            c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=_dump(value), updated_at=_now()))


# ------------------------------------------------------------------ ayarlar


def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    """Ayarlar ekran/ortamdan (`admin.conf`), yoksa varsayılan. Ölçülmemiş varsayımlar burada parametredir."""
    def i(key: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(str(conf(key, str(default)) or default))))
        except ValueError:
            return default

    return {
        "codePrefix": (conf("FIELD_CUSTOMER_CODE_PREFIX", "120") or "120").strip(),
        "excludedOwners": [x.strip() for x in (conf("FIELD_EXCLUDED_OWNERS", "Timas CRM") or "").split(",") if x.strip()],
        "paymentTrcodes": list(src.trcodes(conf("FIELD_PAYMENT_TRCODES", "1,20,61,62,70"))),
        "visitCycleDays": i("FIELD_VISIT_CYCLE_DAYS", 30, 7, 365),
        "collectionDays": i("FIELD_COLLECTION_DAYS", 90, 7, 730),
        "pendingWarnHours": i("FIELD_PENDING_WARN_HOURS", 48, 1, 720),
        "planMaxInstallments": i("FIELD_PLAN_MAX_INSTALLMENTS", 6, 1, 24),
        "similarMin": i("FIELD_SIMILAR_MIN", 3, 1, 100),
        "newBookDays": i("FIELD_NEW_BOOK_DAYS", 90, 7, 365),
        "orderDays": i("FIELD_ORDER_DAYS", 180, 7, 730),
        "agingAsof": (conf("FIELD_AGING_ASOF", "bugun") or "bugun").strip(),       # bugun | veri-sonu
        "targetSource": (conf("FIELD_CUSTOMER_TARGET_SOURCE", "auto") or "auto").strip(),  # auto | m46 | crm
        "mmx": (conf("FIELD_MMX_ENABLED", "0") or "0").strip() in ("1", "true", "evet"),
        "crmVisitColumn": (conf("FIELD_CRM_VISIT_ACCOUNT_COLUMN", "") or "").strip(),
        "reportRecipients": [x.strip() for x in (conf("FIELD_REPORT_RECIPIENTS", "") or "").replace(";", ",").split(",") if "@" in x],
        "financeRecipients": [x.strip() for x in (conf("FIELD_FINANCE_RECIPIENTS", "") or "").replace(";", ",").split(",") if "@" in x],
        "schema": (conf("CRM_SCHEMA", "Timas_MSCRM.dbo") or "").strip(),
    }


# ------------------------------------------------------------------ öncelik (kural)

#: Ziyaret önceliği bileşenleri: (anahtar, en çok puan, ekrandaki ad). Toplam 100'de kesilir; ekranda yazılı.
WEIGHTS: list[tuple[str, int, str]] = [
    ("gecikme", 25, "Vadesi geçmiş alacak (yaşa göre ağırlıklı, portföy içindeki sırası)"),
    ("doksan", 10, "90 günü geçen alacak var"),
    ("cek", 15, "Son 12 ayda karşılıksız ya da protestolu çek/senet"),
    ("risk", 10, "CRM risk limiti doluluğu"),
    ("siparis", 10, "Sipariş risk onayına takılmış"),
    ("soz", 15, "Verilen ödeme sözünün tarihi geçti, sonrasında ödeme yok"),
    ("red", 10, "Son 30 günde reddedilen tahsilat"),
    ("hedef", 10, "Yıl başından hedefin gerisinde"),
    ("satis", 10, "Satış geçen yılın aynı döneminin gerisinde"),
    ("ziyaret", 10, "Uzun süredir ziyaret yok"),
    ("mudur", 20, "Müdür önceliği"),
]
_W = {k: w for k, w, _ in WEIGHTS}
BUCKETS = [("k_1_30", "1–30 gün"), ("k_31_60", "31–60 gün"), ("k_61_90", "61–90 gün"), ("k_90p", "90+ gün")]
TONES = {"olumlu": "Olumlu", "notr": "Nötr", "olumsuz": "Olumsuz"}
VISIT_STATES = {"planlandi": "Planlandı", "yapildi": "Yapıldı", "iptal": "İptal"}
VISIT_KINDS = {"cari": "Cari", "okul": "Okul", "kurum": "Kurum"}
PLAN_STATES = {"taslak": "Taslak", "onayda": "Onay bekliyor", "onayli": "Onaylandı", "reddedildi": "Reddedildi"}


def weighted_overdue(s: dict[str, Any]) -> float:
    """Yaşa göre ağırlıklı vadesi geçmiş: 1–30 ×1, 31–60 ×2, 61–90 ×3, 90+ ×4."""
    return (num(s.get("k_1_30")) + 2 * num(s.get("k_31_60")) + 3 * num(s.get("k_61_90")) + 4 * num(s.get("k_90p")))


def pct_ranks(values: dict[str, float]) -> dict[str, float]:
    """Sıfırdan büyük değerlerin portföy içindeki yüzdelik sırası (0–1]; sıfır 0. Sabit tutar eşiği yok."""
    pos = sorted(v for v in values.values() if v > 0)
    n = len(pos)
    out = {}
    for k, v in values.items():
        if v <= 0 or n == 0:
            out[k] = 0.0
            continue
        below = sum(1 for x in pos if x <= v)
        out[k] = below / n
    return out


def short_money(v: Optional[float]) -> str:
    """42.350 → «42 bin ₺», 1.250.000 → «1,3 Mn ₺» (gerekçe çipleri için)."""
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1_000_000:
        s = f"{v / 1_000_000:.1f}".replace(".", ",") + " Mn ₺"
    elif a >= 1_000:
        s = f"{round(v / 1_000):.0f} bin ₺"
    else:
        s = f"{round(v):.0f} ₺"
    return s


def score(sig: dict[str, Any], ctx: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    """Kural puanı ve gerekçe çipleri. `ctx`: gecikmeRank (0–1), sozGecti (bool, tarih, tutar), red (sayı), mudur (neden),
    sonZiyaret (ISO gün | None), today, visitCycleDays."""
    chips: list[dict[str, Any]] = []

    def add(key: str, frac: float, label: str) -> None:
        pts = round(_W[key] * max(0.0, min(1.0, frac)), 1)
        if pts > 0:
            chips.append({"key": key, "points": pts, "label": label})

    rank = float(ctx.get("gecikmeRank") or 0)
    if num(sig.get("vadesi_gecmis")) > 0:
        add("gecikme", rank, f"Vadesi geçmiş {short_money(num(sig.get('vadesi_gecmis')))}")
    if num(sig.get("k_90p")) > 0:
        add("doksan", 1, f"90+ gün {short_money(num(sig.get('k_90p')))}")
    ev = int(num(sig.get("karsiliksiz_olay_12ay"))) + int(num(sig.get("protesto_olay_12ay")))
    if ev:
        kinds = []
        if num(sig.get("karsiliksiz_olay_12ay")):
            kinds.append(f"karşılıksız {int(num(sig.get('karsiliksiz_olay_12ay')))}")
        if num(sig.get("protesto_olay_12ay")):
            kinds.append(f"protesto {int(num(sig.get('protesto_olay_12ay')))}")
        add("cek", 1, "Çek/senet: " + ", ".join(kinds))
    fill = opt_num(sig.get("risk_doluluk"))
    if fill is not None and fill >= 0.5:
        add("risk", (fill - 0.5) / 0.5, f"Risk limiti %{round(fill * 100)} dolu")
    if int(num(sig.get("siparis_riskte"))):
        why = sig.get("siparis_riskte_sebep")
        add("siparis", 1, "Sipariş riske takıldı" + (f" ({why})" if why else ""))
    soz = ctx.get("soz")
    if soz:
        add("soz", 1, f"Ödeme sözü {soz['tarih']} geçti" + (f" ({short_money(soz.get('tutar'))})" if soz.get("tutar") else ""))
    if ctx.get("red"):
        add("red", 1, f"Reddedilen tahsilat ({ctx['red']})")
    gap = opt_num(sig.get("hedef_acigi"))
    if gap is not None and gap > 0.05:
        add("hedef", gap, f"Hedef açığı %{round(gap * 100)}")
    ly, ytd = num(sig.get("gecen_yil_ayni_donem")), num(sig.get("ytd_net_ciro"))
    if ly > 0 and ytd < ly:
        drop = 1 - max(0.0, ytd) / ly
        if drop > 0.05:
            add("satis", drop, f"Satış geçen yılın %{round(drop * 100)} gerisinde")
    last = ctx.get("sonZiyaret")
    cycle = int(ctx.get("visitCycleDays") or 30)
    now = ctx.get("today") or today()
    if last:
        days = (now - date.fromisoformat(last[:10])).days
        if days > cycle:
            add("ziyaret", (days - cycle) / cycle, f"{days} gündür ziyaret yok")
    if ctx.get("mudur"):
        add("mudur", 1, f"Müdür önceliği: {ctx['mudur']}")
    chips.sort(key=lambda c: -c["points"])
    return min(100.0, round(sum(c["points"] for c in chips), 1)), chips


# ------------------------------------------------------------------ atama (CRM) ve eşleşme (Logo)


def assign(accounts: list[dict[str, Any]], users: list[dict[str, Any]], excluded: Iterable[str]) -> list[dict[str, Any]]:
    """CRM carisi → temsilci. «BMT İl» carisinde il tablosundaki müşteri temsilcisi (boşsa kaydın sahibi), «BMT Cari»
    ya da boş seçimde kaydın sahibi. Takıma atanmış (OwnerIdType ≠ 8) ya da servis hesabına ait kayıt temsilcisiz kalır."""
    from semantic_bridge.people import account as ad_account

    by_id = {guid(u.get("id")): u for u in users}
    skip = {x.strip().lower() for x in excluded}
    out = []
    for a in accounts:
        mode = a.get("bmt_il_cari")
        owner = guid(a.get("owner_id")) if int(num(a.get("owner_type")) or 8) == 8 else None
        il_rep = guid(a.get("il_temsilci"))
        uid, how = (il_rep, "il") if mode is not None and int(mode) == src.BMT_IL and il_rep else (owner, "owner")
        u = by_id.get(uid) if uid else None
        if u and (text(u.get("ad")) or "").lower() in skip:
            u = None
        out.append({**a, "systemuser_id": guid(u.get("id")) if u else None,
                    "ad_hesap": ad_account(text(u.get("domain")) or "") if u else None,
                    "temsilci_ad": text(u.get("ad")) if u else None, "atama_kaynagi": how if u else None})
    return out


def match_clients(assigned: list[dict[str, Any]], clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """CRM carisi ↔ Logo müşteri carisi: önce cari kodu (`new_CariKodu` = `CODE`), yoksa Logo ref (`new_logicalref`).
    Logo'da olup CRM'de eşi olmayan müşteri carisi de portföye girer (temsilcisiz)."""
    by_code = {text(c.get("code")): c for c in clients if text(c.get("code"))}
    by_ref = {int(num(c.get("ref"))): c for c in clients}
    seen: set[str] = set()
    rows = []
    for a in assigned:
        c = by_code.get(text(a.get("cari_kodu")) or "")
        if c is None:
            ref = text(a.get("logicalref"))
            if ref and ref.isdigit():
                c = by_ref.get(int(ref))
        if c is None:
            continue
        code = text(c.get("code"))
        if code in seen:
            continue
        seen.add(code)
        rows.append({"logo_code": code, "logo_clientref": int(num(c.get("ref"))), "crm_account_id": guid(a.get("account_id")),
                     "unvan": text(c.get("unvan")) or text(a.get("unvan")), "il": text(a.get("il")) or text(c.get("il")),
                     "kanal": src.CHANNEL.get(int(num(a.get("kanal")))) if a.get("kanal") is not None else text(c.get("kanal")),
                     "logo_kanal": text(c.get("kanal")), "logo_il": text(c.get("il")),
                     "systemuser_id": a.get("systemuser_id"), "ad_hesap": a.get("ad_hesap"),
                     "temsilci_ad": a.get("temsilci_ad"), "atama_kaynagi": a.get("atama_kaynagi"), "_crm": a})
    for c in clients:
        code = text(c.get("code"))
        if code and code not in seen:
            seen.add(code)
            rows.append({"logo_code": code, "logo_clientref": int(num(c.get("ref"))), "crm_account_id": None,
                         "unvan": text(c.get("unvan")), "il": text(c.get("il")), "kanal": text(c.get("kanal")),
                         "logo_kanal": text(c.get("kanal")), "logo_il": text(c.get("il")),
                         "systemuser_id": None, "ad_hesap": None, "temsilci_ad": None, "atama_kaynagi": None, "_crm": None})
    return rows


# ------------------------------------------------------------------ hedef (M46)


def elapsed_fraction(monthly: list[float], asof: date, year: int) -> float:
    """Yıllık hedefin `asof`'a kadar beklenen payı: aylık ağırlıklar (toplam 1'e normalize), içinde bulunulan ay gün oranıyla."""
    if asof.year < year:
        return 0.0
    if asof.year > year:
        return 1.0
    tot = sum(max(0.0, x) for x in monthly) or 0.0
    w = [max(0.0, x) / tot for x in monthly] if tot > 0 else [1 / 12] * 12
    import calendar

    done = sum(w[: asof.month - 1])
    dim = calendar.monthrange(year, asof.month)[1]
    return min(1.0, done + w[asof.month - 1] * asof.day / dim)


def customer_targets(prev_full: dict[str, float], plan: Optional[dict[str, Any]], crm_targets: dict[str, float],
                     asof: date, year: int, source: str = "auto") -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Cari yıllık hedefi. **M46 dağıtım kuralı (ekranda yazılı):** carinin önceki yıl net cirosunun bütün müşteri
    carilerinin önceki yıl net cirosuna payı × yürürlükteki planın toplam hedef cirosu; payların toplamı 1 olduğu için
    cari hedeflerinin toplamı planın toplamına eşittir. Beklenen = yıllık hedef × planın aylık dağılımıyla geçen pay.
    Plan yoksa (ya da `crm` seçiliyse) CRM `new_CariYilHedef` (doluysa), beklenen takvim günü oranıyla."""
    out: dict[str, dict[str, Any]] = {}
    info: dict[str, Any] = {"kaynak": None, "plan": None, "toplamHedef": None, "pay": None}
    use_m46 = source in ("auto", "m46") and plan and plan.get("items")
    if use_m46:
        total_target = sum(num(i.get("hedef", {}).get("ciro")) for i in plan["items"])
        monthly = [sum(num((i.get("aylik") or [])[m].get("ciro")) if len(i.get("aylik") or []) > m else 0.0 for i in plan["items"])
                   for m in range(12)]
        frac = elapsed_fraction(monthly, asof, year)
        base = sum(v for v in prev_full.values() if v > 0)
        info.update({"kaynak": "m46", "plan": plan.get("plan"), "toplamHedef": round(total_target, 2), "pay": round(frac, 4)})
        if base > 0:
            for code, v in prev_full.items():
                if v <= 0:
                    continue
                t = total_target * v / base
                out[code] = {"yil": round(t, 2), "beklenen": round(t * frac, 2), "kaynak": "m46"}
        return out, info
    if source in ("auto", "crm"):
        import calendar

        days = 366 if calendar.isleap(year) else 365
        frac = 0.0 if asof.year < year else 1.0 if asof.year > year else asof.timetuple().tm_yday / days
        info.update({"kaynak": "crm", "pay": round(frac, 4)})
        for code, t in crm_targets.items():
            if t and t > 0:
                out[code] = {"yil": round(t, 2), "beklenen": round(t * frac, 2), "kaynak": "crm"}
    return out, info


# ------------------------------------------------------------------ ödeme planı (kural)


def plan_installments(amount: float, count: int, start: date) -> list[dict[str, Any]]:
    """Eşit taksit, 100 ₺'ye yuvarlı, kalan son taksitte; ilk taksit `start`, sonrakiler birer ay arayla (ayın aynı günü,
    ay kısaysa son günü). Rakamı model değil bu kural üretir."""
    import calendar

    amount = round(max(0.0, amount), 2)
    n = max(1, int(count))
    each = math.floor(amount / n / 100) * 100 if amount >= 100 * n else round(amount / n, 2)
    out = []
    for i in range(n):
        m = start.month - 1 + i
        y, mo = start.year + m // 12, m % 12 + 1
        d = min(start.day, calendar.monthrange(y, mo)[1])
        out.append({"sira": i + 1, "tarih": date(y, mo, d).isoformat(), "tutar": each})
    out[-1]["tutar"] = round(amount - each * (n - 1), 2)
    return out


def suggest_plan(sig: dict[str, Any], max_n: int, now: date) -> dict[str, Any]:
    """Öneri: tutar = vadesi geçmiş (FIFO); taksit sayısı = vadesi geçmiş ÷ carinin son 12 ayın aylık ortalama ödemesi
    (yukarı yuvarlı, 1…azami); ilk taksit 15 gün sonra. Gerekçe metni şablondan."""
    overdue = round(num(sig.get("vadesi_gecmis")), 2)
    if overdue <= 0:
        raise FieldError("Bu carinin vadesi geçmiş alacağı yok; ödeme planı önerilmez.")
    monthly = num(sig.get("odeme_12ay")) / 12
    n = max(1, min(max_n, math.ceil(overdue / monthly))) if monthly > 0 else max_n
    start = now + timedelta(days=15)
    rows = plan_installments(overdue, n, start)
    why = (f"Vadesi geçmiş {_tr_money(overdue)} (yaklaşık, FIFO). "
           + (f"Son 12 ayda aylık ortalama ödeme {_tr_money(monthly)}; bu hızla {n} taksit. " if monthly > 0
              else f"Son 12 ayda ödeme kaydı yok; azami taksit sayısı ({n}) önerildi. ")
           + f"İlk taksit {rows[0]['tarih']}.")
    return {"tutar": overdue, "taksitler": rows, "gerekce": why}


def _tr_money(v: float) -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} ₺"


# ------------------------------------------------------------------ özet: kural ve model denetimi


def facts_of(b: dict[str, Any]) -> list[str]:
    """Brifingin olgu cümleleri (modelin tek girdisi; özetteki her sayı buradan gelmek zorunda)."""
    s = b.get("signals") or {}
    f = []
    f.append(f"Bakiye: {_tr_money(num(s.get('bakiye')))}; vadesi geçmiş (yaklaşık): {_tr_money(num(s.get('vadesi_gecmis')))}; "
             f"90 günü geçen: {_tr_money(num(s.get('k_90p')))}.")
    if s.get("son_odeme_tarihi"):
        d = (date.fromisoformat(b["asof"]) - date.fromisoformat(s["son_odeme_tarihi"])).days if b.get("asof") else None
        f.append(f"Son ödeme: {s['son_odeme_tarihi']}" + (f" ({d} gün önce)." if d is not None else "."))
    ytd, ly = num(s.get("ytd_net_ciro")), num(s.get("gecen_yil_ayni_donem"))
    f.append(f"Yıl başından net alım: {_tr_money(ytd)}; geçen yılın aynı dönemi: {_tr_money(ly)}"
             + (f" (geçen yılın %{round(ytd / ly * 100)}'i)." if ly > 0 else "."))
    if s.get("hedef_acigi") is not None:
        f.append(f"Yıl başından hedefin %{round(num(s.get('hedef_acigi')) * 100)} gerisinde.")
    ev = int(num(s.get("karsiliksiz_olay_12ay")))
    if ev:
        f.append(f"Son 12 ayda {ev} karşılıksız çek/senet olayı.")
    if s.get("risk_doluluk") is not None:
        f.append(f"Risk limiti doluluğu %{round(num(s.get('risk_doluluk')) * 100)}.")
    if int(num(s.get("siparis_riskte"))):
        f.append(f"{int(num(s.get('siparis_riskte')))} sipariş risk onayı bekliyor.")
    gaps = [g for g in (b.get("hedefKitaplar") or [])[:3]]
    if gaps:
        f.append("Hedef açığı en büyük kitaplar: " + ", ".join(g.get("ad") or g["stok"] for g in gaps) + ".")
    # Gizli not özete girmez: özet önbelleğe yazılır ve carinin brifingini açan herkese görünür.
    last = next((v for v in (b.get("ziyaretler") or []) if v.get("notu") and not v.get("gizli")), None)
    if last:
        f.append(f"Son görüşme notu ({(last.get('gerceklesen') or last.get('planlanan') or '')[:10]}): {last['notu'][:200]}")
    return f


def rule_summary(b: dict[str, Any]) -> str:
    """Modelsiz özet: ilk üç olgu."""
    return " ".join(facts_of(b)[:3])


_DIGITS = re.compile(r"\d+")


def numbers_ok(summary: str, facts: Iterable[str]) -> bool:
    """Özetteki her rakam dizisi olgularda da geçmeli (model yeni rakam yazmasın)."""
    allowed = set(_DIGITS.findall(" ".join(facts)))
    return all(n in allowed for n in _DIGITS.findall(summary or ""))


def summary_prompt(facts: list[str]) -> str:
    return ("Aşağıda bir kitap müşterisinin (kitapçı/bayi) ziyaret öncesi olguları var. Saha temsilcisi için en fazla 3 kısa "
            "Türkçe cümlelik özet yaz: önce ödeme durumu, sonra alım eğilimi, sonra görüşmede öne çıkarılacak konu. Yalnız "
            "verilen rakamları aynen kullan; yeni rakam, oran ya da tarih yazma, hesap yapma. Başlık ve madde işareti kullanma.\n\n"
            "OLGULAR:\n- " + "\n- ".join(facts))


def reason_prompt(textv: str) -> str:
    """Kapalı küme sınıflama sorusu (`QueuedLlm.choose` seçenekleri kendisi ekler)."""
    return ("Bir kitap müşterisinden alınan tahsilat kaydı finans tarafından reddedildi. Red açıklaması aşağıda. "
            f"Red nedeni hangi sınıfa girer?\n\nAçıklama: {textv[:500]}")


#: Sınıflama seçenekleri → CRM red sebebi kodu (aynı küme; uydurma sınıf olamaz).
REASON_CHOICES = {label: code for code, label in src.REJECT_REASON.items()}
#: Öneri eşiği (docs/analiz/llm-choose.md): ekranda «Zeki AI'ya göre» diye gösterilir, CRM kaydını değiştirmez.
REASON_MIN_PROB, REASON_MIN_MARGIN = 0.70, 0.30


def followup_prompt(facts: list[str], visit: dict[str, Any], customer: str) -> str:
    return ("Saha temsilcisi müşteri ziyaretinden sonra müşteriye kısa bir teşekkür ve takip e-postası gönderecek. Taslağı "
            "Türkçe, nazik ve 120 kelimeyi geçmeyecek şekilde yaz. Görüşmede konuşulanları ve sonraki adımı an. Rakam "
            "yazacaksan yalnız aşağıdakileri aynen kullan. Selamlama ve imza satırını '[Adınız]' olarak bırak.\n\n"
            f"Müşteri: {customer}\nGörüşme notu: {(visit.get('notu') or '')[:600]}\nSonraki adım: {visit.get('sonraki_adim') or '-'}"
            + (f" ({visit.get('sonraki_tarih')})" if visit.get("sonraki_tarih") else "")
            + (f"\nÖdeme sözü: {visit.get('soz_odeme_tarihi')} — {_tr_money(num(visit.get('soz_odeme_tutari')))}"
               if visit.get("soz_odeme_tarihi") else "")
            + "\n\nOLGULAR:\n- " + "\n- ".join(facts[:2]))


# ------------------------------------------------------------------ kaynak okuması (gece turu)


def _runner(conn: Any) -> Callable[[str], list[dict[str, Any]]]:
    def run(sql: str) -> list[dict[str, Any]]:
        _cols, rows, truncated = conn.execute(sql, MAX_ROWS)
        if truncated:
            raise SourceError("Sonuç beklenenden büyük; eksik okunmasın diye durduruldu.")
        return rows
    return run


def _close(conn: Any) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


class Source:
    """CRM + Logo bağlantıları (okuma başına açılıp kapanır). CRM tahsilat okuması 5 dk bellekte (ekran + hafif tur)."""

    TTL = 300

    def __init__(self, crm_connect: Callable[[], Any], logo_connect: Callable[[], Any]):
        self._crm, self._logo = crm_connect, logo_connect
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, Any]] = {}

    def crm(self, fn: Callable[[Callable[[str], list[dict[str, Any]]]], Any]) -> Any:
        conn = self._crm()
        try:
            return fn(_runner(conn))
        finally:
            _close(conn)

    def logo(self, fn: Callable[[Callable[[str], list[dict[str, Any]]]], Any]) -> Any:
        conn = self._logo()
        try:
            return fn(_runner(conn))
        finally:
            _close(conn)

    def cached(self, key: str, fresh: bool, fn: Callable[[], Any]) -> Any:
        with self._lock:
            hit = self._cache.get(key)
            if hit and not fresh and time.time() - hit[0] < self.TTL:
                return hit[1]
        val = fn()
        with self._lock:
            self._cache[key] = (time.time(), val)
            if len(self._cache) > 2000:   # bellek koruması: en eskiler atılır (veri kesilmez, yeniden okunur)
                for k, _ in sorted(self._cache.items(), key=lambda kv: kv[1][0])[:500]:
                    self._cache.pop(k, None)
        return val

    def collections(self, settings: dict[str, Any], fresh: bool = False) -> list[dict[str, Any]]:
        since = today() - timedelta(days=settings["collectionDays"])
        return self.cached(f"crm-collections:{since}", fresh, lambda: self.crm(
            lambda run: src.lower_keys(run(src.crm_collections_sql(settings["schema"], since)))))

    def users(self, settings: dict[str, Any], fresh: bool = False) -> list[dict[str, Any]]:
        return self.cached("crm-users", fresh, lambda: self.crm(lambda run: src.lower_keys(run(src.crm_users_sql(settings["schema"])))))


def logo_calendar(run: Callable[[str], list[dict[str, Any]]], now: date) -> dict[str, Any]:
    """Yıl → firma; bu yılın (ya da verisi olan son yılın) firması, önceki yıl firması, verinin bittiği gün."""
    from semantic_bridge import budget_sources as bsrc

    firms = bsrc.firms_by_year(run)
    years = [y for y in firms if y <= now.year]
    if not years:
        raise SourceError("Logo'da bu yılın ya da önceki bir yılın dönemi yok.")
    cur = max(years)
    rows = src.lower_keys(run(src.data_end_sql(firms[cur])))
    end = day(rows[0].get("son")) if rows else None
    return {"firms": {y: f for y, f in firms.items()}, "year": cur, "firm": firms[cur],
            "prevFirm": firms.get(cur - 1), "dataEnd": end}


def read_all(source: Source, settings: dict[str, Any], now: Optional[date] = None) -> dict[str, Any]:
    """Gece turunun bütün okuması. Logo ve CRM ayrı bağlantı; biri düşerse hata (yarım portföy yazılmaz)."""
    now = now or today()
    schema = settings["schema"]
    pre = settings["codePrefix"]
    t0 = time.monotonic()

    def crm_part(run):
        return {"users": src.lower_keys(run(src.crm_users_sql(schema))),
                "accounts": src.lower_keys(run(src.crm_accounts_sql(schema))),
                "riskOrders": src.lower_keys(run(src.crm_risk_orders_sql(schema))),
                "collections": src.lower_keys(run(src.crm_collections_sql(schema, now - timedelta(days=settings["collectionDays"])))),
                "crmVisits": (src.lower_keys(run(src.crm_visits_sql(schema, settings["crmVisitColumn"], now - timedelta(days=365))))
                              if settings["crmVisitColumn"] else [])}

    crm = source.crm(crm_part)
    crm_ms = int((time.monotonic() - t0) * 1000)
    t1 = time.monotonic()
    warnings: list[str] = []

    def logo_part(run):
        cal = logo_calendar(run, now)
        f, pf, year = cal["firm"], cal["prevFirm"], cal["year"]
        end = date.fromisoformat(cal["dataEnd"]) if cal["dataEnd"] else now
        aging_asof = end if settings["agingAsof"] == "veri-sonu" else now
        codes = tuple(settings["paymentTrcodes"])
        out: dict[str, Any] = {"cal": cal, "agingAsof": aging_asof.isoformat()}
        out["clients"] = src.read_rows(run, src.clients_sql(f, pre))
        out["aging"] = src.read_aging(run, f, year, aging_asof, pre)
        pay: dict[str, dict[str, Any]] = {}
        for ff in [x for x in (pf, f) if x]:
            for r in src.read_rows(run, src.payments_sql(ff, now - timedelta(days=365), codes, pre)):
                code = text(r.get("code"))
                cur = pay.setdefault(code, {"son": None, "toplam": 0.0})
                d = day(r.get("son"))
                if d and (cur["son"] is None or d > cur["son"]):
                    cur["son"] = d
                cur["toplam"] += num(r.get("toplam"))
        out["payments"] = pay
        out["ytd"] = {text(r.get("code")): r for r in src.read_rows(run, src.sales_sql(f, date(year, 1, 1), end, pre))}
        if pf:
            try:
                ly_end = end.replace(year=end.year - 1)
            except ValueError:            # 29 Şubat
                ly_end = end.replace(year=end.year - 1, day=28)
            out["ly"] = {text(r.get("code")): r for r in src.read_rows(run, src.sales_sql(pf, date(year - 1, 1, 1), ly_end, pre))}
            out["lyFull"] = {text(r.get("code")): r for r in src.read_rows(run, src.sales_sql(pf, date(year - 1, 1, 1), date(year - 1, 12, 31), pre))}
        else:
            out["ly"], out["lyFull"] = {}, {}
            warnings.append("Logo'da önceki yılın dönemi yok; geçen yıl karşılaştırması ve hedef dağılımı yapılamadı.")
        out["cheques"] = src.read_cheque_events(run, [x for x in (f, pf) if x], now - timedelta(days=365), pre)
        out["mmxVisits"], out["mmxCollections"] = {}, {}
        if settings["mmx"]:
            try:
                for r in src.read_rows(run, src.mmx_visits_sql(f, now - timedelta(days=365))):
                    out["mmxVisits"][text(r.get("code"))] = day(r.get("son"))
                for r in src.read_rows(run, src.mmx_collections_sql(f, now - timedelta(days=settings["collectionDays"]))):
                    out["mmxCollections"].setdefault(text(r.get("code")), []).append(
                        {"no": text(r.get("no")), "tur": text(r.get("tur")), "tutar": num(r.get("tutar")), "vade": day(r.get("vade")),
                         "tarih": day(r.get("tarih")), "senkron": r.get("senkron"), "durum": r.get("durum")})
            except Exception as e:  # noqa: BLE001 — seçenekli kaynak; ana tur sürer
                log.warning("field: saha uygulaması tabloları okunamadı: %s", e)
                warnings.append("Saha uygulaması tabloları okunamadı; ayar açık ama kaynak yok ya da yapısı farklı.")
        return out

    logo = source.logo(logo_part)
    logo_ms = int((time.monotonic() - t1) * 1000)
    return {"crm": crm, "logo": logo, "warnings": warnings, "crmMs": crm_ms, "logoMs": logo_ms, "now": now.isoformat()}


# ------------------------------------------------------------------ gece turu: portföy + sinyaller


def build(data: dict[str, Any], settings: dict[str, Any], plan: Optional[dict[str, Any]],
          visits_by_code: dict[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Okunan veriden portföy ve sinyal satırları (saf; test edilir). `visits_by_code`: portaldaki son ziyaret günü."""
    crm, logo = data["crm"], data["logo"]
    now = date.fromisoformat(data["now"])
    cal = logo["cal"]
    end = date.fromisoformat(cal["dataEnd"]) if cal.get("dataEnd") else now
    assigned = assign(crm["accounts"], crm["users"], settings["excludedOwners"])
    rows = match_clients(assigned, logo["clients"])
    risk_orders = {guid(r.get("account_id")): r for r in crm["riskOrders"]}
    crm_visits = {guid(r.get("account_id")): day(r.get("son")) for r in crm.get("crmVisits") or []}
    prev_full = {code: num(r.get("satis")) - num(r.get("iade")) for code, r in logo["lyFull"].items() if code}
    crm_targets = {r["logo_code"]: num((r["_crm"] or {}).get("yil_hedef")) for r in rows if r.get("_crm")}
    targets, tinfo = customer_targets(prev_full, plan, crm_targets, end, cal["year"], settings["targetSource"])
    asof = now.isoformat()
    portfolio, signals = [], []
    for r in rows:
        code = r["logo_code"]
        ag = logo["aging"].get(r["logo_clientref"], {})
        ytd = logo["ytd"].get(code) or {}
        ly = logo["ly"].get(code) or {}
        sat, iad = num(ytd.get("satis")), num(ytd.get("iade"))
        risk = src.risk_of(r["_crm"]) if r.get("_crm") else {}
        ro = risk_orders.get(r["crm_account_id"]) if r.get("crm_account_id") else None
        ch = logo["cheques"].get(code) or {}
        pay = logo["payments"].get(code) or {}
        tg = targets.get(code)
        ytd_net = round(sat - iad, 2)
        gap = None
        if tg and tg["beklenen"] > 0:
            gap = round(max(0.0, 1 - ytd_net / tg["beklenen"]), 4)
        last_visit = max([x for x in (visits_by_code.get(code), logo["mmxVisits"].get(code), crm_visits.get(r["crm_account_id"])) if x],
                         default=None)
        portfolio.append({k: r[k] for k in ("logo_code", "systemuser_id", "ad_hesap", "temsilci_ad", "crm_account_id",
                                             "logo_clientref", "unvan", "il", "kanal", "logo_il", "logo_kanal", "atama_kaynagi")} | {"asof": asof})
        signals.append({
            "logo_code": code, "logo_clientref": r["logo_clientref"], "asof": asof,
            "bakiye": ag.get("bakiye", 0.0), "vadesi_gecmis": ag.get("vadesi_gecmis", 0.0), "gelmemis": ag.get("gelmemis", 0.0),
            "plansiz": ag.get("plansiz", 0.0),
            "k_1_30": ag.get("k_1_30", 0.0), "k_31_60": ag.get("k_31_60", 0.0), "k_61_90": ag.get("k_61_90", 0.0), "k_90p": ag.get("k_90p", 0.0),
            "son_odeme_tarihi": pay.get("son"), "odeme_12ay": round(pay.get("toplam", 0.0), 2),
            "karsiliksiz_olay_12ay": int(ch.get("karsiliksiz_adet", 0)), "protesto_olay_12ay": int(ch.get("protesto_adet", 0)),
            "cek_olay_tutar": round(num(ch.get("karsiliksiz_tutar")) + num(ch.get("protesto_tutar")), 2),
            "risk_toplam": risk.get("risk_toplam"), "limit_toplam": risk.get("limit_toplam"), "risk_doluluk": risk.get("risk_doluluk"),
            "siparis_riskte": int(num(ro.get("adet"))) if ro else 0,
            "siparis_riskte_sebep": src.ORDER_RISK_REASON.get(int(num(ro.get("sebep")))) if ro else None,
            "ytd_net_ciro": ytd_net, "gecen_yil_ayni_donem": round(num(ly.get("satis")) - num(ly.get("iade")), 2),
            "gecen_yil_tam": round(prev_full.get(code, 0.0), 2),
            "iade_orani": round(iad / sat, 4) if sat > 0 else None, "son_fatura": day(ytd.get("son_fatura")),
            "hedef_yil": tg["yil"] if tg else None, "hedef_beklenen": tg["beklenen"] if tg else None, "hedef_acigi": gap,
            "hedef_kaynagi": tg["kaynak"] if tg else None,
            "saha_son_ziyaret": last_visit,
            "saha_tahsilat_json": _dump(logo["mmxCollections"].get(code)) if logo["mmxCollections"].get(code) else None,
            "oncelik_puani": None, "gerekce_json": None,
        })
    info = {"asof": asof, "dataEnd": cal.get("dataEnd"), "year": cal["year"], "firm": cal["firm"], "prevFirm": cal.get("prevFirm"),
            "agingAsof": logo["agingAsof"], "target": tinfo, "portfolio": len(portfolio),
            "assigned": sum(1 for p in portfolio if p["ad_hesap"]),
            "crmUnmatched": sum(1 for a in assigned if a.get("cari_kodu") or a.get("logicalref")) - sum(1 for r in rows if r.get("_crm")),
            "warnings": data.get("warnings") or [], "crmMs": data.get("crmMs"), "logoMs": data.get("logoMs"), "mmx": settings["mmx"]}
    return portfolio, signals, info


def write_snapshot(engine: sa.engine.Engine, tenant: str, portfolio: list[dict[str, Any]], signals: list[dict[str, Any]]) -> None:
    """Tam değiştirme, tek işlemde: okuyan yarım portföy görmez."""
    with engine.begin() as c:
        c.execute(PORTFOLIO.delete().where(PORTFOLIO.c.tenant_id == tenant))
        c.execute(SIGNALS.delete().where(SIGNALS.c.tenant_id == tenant))
        for chunk in range(0, len(portfolio), 1000):
            part = [{**p, "tenant_id": tenant} for p in portfolio[chunk:chunk + 1000]]
            if part:
                c.execute(PORTFOLIO.insert(), part)
        for chunk in range(0, len(signals), 1000):
            part = [{**s, "tenant_id": tenant} for s in signals[chunk:chunk + 1000]]
            if part:
                c.execute(SIGNALS.insert(), part)


# ------------------------------------------------------------------ okuma (ekran)


def _row(r: Any) -> dict[str, Any]:
    return dict(r._mapping)


def portfolio_rows(engine: sa.engine.Engine, tenant: str, owner: Optional[str]) -> list[dict[str, Any]]:
    """Portföy + sinyaller. `owner` None = herkes (yetkili)."""
    j = PORTFOLIO.join(SIGNALS, sa.and_(SIGNALS.c.tenant_id == PORTFOLIO.c.tenant_id, SIGNALS.c.logo_code == PORTFOLIO.c.logo_code))
    q = sa.select(PORTFOLIO, *[c for c in SIGNALS.c if c.name not in ("tenant_id", "logo_code", "logo_clientref", "asof")]).select_from(j) \
        .where(PORTFOLIO.c.tenant_id == tenant)
    if owner is not None:
        q = q.where(PORTFOLIO.c.ad_hesap == owner)
    with engine.connect() as c:
        return [_row(r) for r in c.execute(q)]


def one(engine: sa.engine.Engine, tenant: str, code: str) -> Optional[dict[str, Any]]:
    j = PORTFOLIO.join(SIGNALS, sa.and_(SIGNALS.c.tenant_id == PORTFOLIO.c.tenant_id, SIGNALS.c.logo_code == PORTFOLIO.c.logo_code))
    q = sa.select(PORTFOLIO, *[c for c in SIGNALS.c if c.name not in ("tenant_id", "logo_code", "logo_clientref", "asof")]).select_from(j) \
        .where(PORTFOLIO.c.tenant_id == tenant, PORTFOLIO.c.logo_code == code)
    with engine.connect() as c:
        r = c.execute(q).first()
    return _row(r) if r else None


def reps(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    q = sa.select(PORTFOLIO.c.ad_hesap, sa.func.max(PORTFOLIO.c.temsilci_ad), sa.func.count()).where(
        PORTFOLIO.c.tenant_id == tenant, PORTFOLIO.c.ad_hesap.isnot(None)).group_by(PORTFOLIO.c.ad_hesap)
    with engine.connect() as c:
        out = [{"hesap": a, "ad": n or a, "cari": int(k)} for a, n, k in c.execute(q)]
    return sorted(out, key=lambda x: (x["ad"] or "").lower())


def in_scope(engine: sa.engine.Engine, tenant: str, user: str, code: str, all_scope: bool) -> dict[str, Any]:
    row = one(engine, tenant, code)
    if row is None:
        raise FieldError("Bu cari portföyde yok (gece turu henüz koşmadı ya da cari kodu yanlış).", 404)
    if not all_scope and (row.get("ad_hesap") or "") != user:
        raise FieldError("Bu cari size atanmış değil.", 403)
    return row


# ------------------------------------------------------------------ ziyaret (ortak tablo)


def _visit_out(r: dict[str, Any], viewer: str, admin: bool = False) -> dict[str, Any]:
    hidden = bool(r.get("gizli")) and r.get("sahip") != viewer and not admin
    return {"id": r["id"], "tur": r["tur"], "hedef": r["hedef_kimlik"], "hedefAd": r.get("hedef_ad"), "sahip": r["sahip"],
            "planlanan": r.get("planlanan"), "gerceklesen": r.get("gerceklesen"), "durum": r["durum"],
            "durumAd": VISIT_STATES.get(r["durum"], r["durum"]),
            "notu": None if hidden else r.get("notu"), "gizli": bool(r.get("gizli")), "gizliNot": hidden,
            "ton": None if hidden else r.get("ton"), "sonrakiAdim": None if hidden else r.get("sonraki_adim"),
            "sonrakiTarih": r.get("sonraki_tarih"),
            "sozOdemeTarihi": r.get("soz_odeme_tarihi"), "sozOdemeTutari": r.get("soz_odeme_tutari"),
            "eslikEdenBayi": r.get("eslik_eden_bayi"), "olusturma": _iso(r.get("olusturma")),
            "guncelleyen": r.get("guncelleyen"), "guncelleme": _iso(r.get("guncelleme"))}


_DT = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$")


def _dt(v: Any, what: str) -> Optional[str]:
    if v in (None, ""):
        return None
    s = str(v).strip()[:16]
    if not _DT.match(s):
        raise FieldError(f"{what} YYYY-AA-GG ya da YYYY-AA-GGTSS:DD olmalı.", 422)
    try:
        datetime.fromisoformat(s if "T" in s else s + "T00:00")
    except ValueError:
        raise FieldError(f"{what} geçerli bir tarih değil.", 422) from None
    return s


def _day_only(v: Any, what: str) -> Optional[str]:
    s = _dt(v, what)
    return s[:10] if s else None


def _visit_values(body: dict[str, Any], partial: bool) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if not partial or "durum" in body:
        d = str(body.get("durum") or ("yapildi" if body.get("gerceklesen") or body.get("notu") else "planlandi"))
        if d not in VISIT_STATES:
            raise FieldError("Durum planlandi, yapildi ya da iptal olmalı.", 422)
        vals["durum"] = d
    if "planlanan" in body or not partial:
        vals["planlanan"] = _dt(body.get("planlanan"), "Planlanan tarih")
    if "gerceklesen" in body or not partial:
        vals["gerceklesen"] = _dt(body.get("gerceklesen"), "Gerçekleşen tarih")
    for k, col, n in (("notu", "notu", 4000), ("sonrakiAdim", "sonraki_adim", 500)):
        if k in body or not partial:
            v = text(body.get(k))
            vals[col] = v[:n] if v else None
    if "ton" in body or not partial:
        t = body.get("ton") or None
        if t is not None and t not in TONES:
            raise FieldError("Ton olumlu, notr ya da olumsuz olmalı.", 422)
        vals["ton"] = t
    for k, col, what in (("sonrakiTarih", "sonraki_tarih", "Sonraki adım tarihi"), ("sozOdemeTarihi", "soz_odeme_tarihi", "Ödeme sözü tarihi")):
        if k in body or not partial:
            vals[col] = _day_only(body.get(k), what)
    if "sozOdemeTutari" in body or not partial:
        v = body.get("sozOdemeTutari")
        amt = opt_num(str(v).replace(".", "").replace(",", ".") if isinstance(v, str) else v) if v not in (None, "") else None
        if amt is not None and amt < 0:
            raise FieldError("Ödeme sözü tutarı eksi olamaz.", 422)
        vals["soz_odeme_tutari"] = amt
    if "gizli" in body or not partial:
        vals["gizli"] = bool(body.get("gizli"))
    if "eslikEdenBayi" in body or not partial:
        vals["eslik_eden_bayi"] = (text(body.get("eslikEdenBayi")) or None)
    if vals.get("durum") == "yapildi" and not vals.get("gerceklesen") and not partial:
        vals["gerceklesen"] = datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")
    return vals


def add_visit(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any], hedef_ad: Optional[str]) -> dict[str, Any]:
    tur = str(body.get("tur") or "cari")
    if tur not in VISIT_KINDS:
        raise FieldError("Ziyaret türü cari, okul ya da kurum olmalı.", 422)
    hedef = text(body.get("hedef"))
    if not hedef:
        raise FieldError("Ziyaret edilecek yer seçilmedi.", 422)
    vals = _visit_values(body, partial=False)
    if not vals.get("planlanan") and not vals.get("gerceklesen"):
        vals["planlanan"] = today().isoformat()
    row = {"id": _new_id(), "tenant_id": tenant, "tur": tur, "hedef_kimlik": hedef[:60], "hedef_ad": (hedef_ad or text(body.get("hedefAd")) or "")[:300] or None,
           "sahip": user, "olusturan": user, "olusturma": _now(), **vals}
    with engine.begin() as c:
        c.execute(VISITS.insert().values(**row))
    return _visit_out(row, user)


def get_visit(engine: sa.engine.Engine, tenant: str, vid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(VISITS).where(VISITS.c.tenant_id == tenant, VISITS.c.id == vid)).first()
    if r is None:
        raise FieldError("Ziyaret bulunamadı.", 404)
    return _row(r)


def update_visit(engine: sa.engine.Engine, tenant: str, user: str, vid: str, body: dict[str, Any], admin: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    cur = get_visit(engine, tenant, vid)
    if cur["sahip"] != user and not admin:
        raise FieldError("Bu ziyaret kaydı başkasına ait; yalnız sahibi değiştirir.", 403)
    vals = _visit_values(body, partial=True)
    if vals.get("durum") == "yapildi" and not (vals.get("gerceklesen") or cur.get("gerceklesen")):
        vals["gerceklesen"] = datetime.now(TZ).strftime("%Y-%m-%dT%H:%M")
    diff = {k: {"eski": cur.get(k), "yeni": v} for k, v in vals.items() if cur.get(k) != v and k != "notu"}
    if "notu" in vals and vals["notu"] != cur.get("notu"):
        diff["notu"] = {"degisti": True}
    vals.update(guncelleyen=user, guncelleme=_now())
    with engine.begin() as c:
        c.execute(VISITS.update().where(VISITS.c.id == vid).values(**vals))
    return _visit_out({**cur, **vals}, user, admin), diff


def list_visits(engine: sa.engine.Engine, tenant: str, viewer: str, *, codes: Optional[set[str]] = None, hedef: str = "",
                tur: str = "", owner: Optional[str] = None, day_: str = "", since: str = "", admin: bool = False) -> list[dict[str, Any]]:
    """Ziyaretler (yeniden eskiye). `codes` verilirse yalnız bu cariler (kapsam) ve kişinin kendi kayıtları."""
    q = sa.select(VISITS).where(VISITS.c.tenant_id == tenant)
    if tur:
        q = q.where(VISITS.c.tur == tur)
    if hedef:
        q = q.where(VISITS.c.hedef_kimlik == hedef)
    if owner:
        q = q.where(VISITS.c.sahip == owner)
    if day_:
        q = q.where(sa.or_(VISITS.c.planlanan.like(f"{day_}%"), VISITS.c.gerceklesen.like(f"{day_}%")))
    if since:
        q = q.where(sa.or_(VISITS.c.planlanan >= since, VISITS.c.gerceklesen >= since))
    q = q.order_by(sa.func.coalesce(VISITS.c.gerceklesen, VISITS.c.planlanan).desc(), VISITS.c.olusturma.desc())
    with engine.connect() as c:
        rows = [_row(r) for r in c.execute(q)]
    if codes is not None:
        rows = [r for r in rows if r["sahip"] == viewer or (r["tur"] == "cari" and r["hedef_kimlik"] in codes)]
    return [_visit_out(r, viewer, admin) for r in rows]


def last_visit_days(engine: sa.engine.Engine, tenant: str) -> dict[str, str]:
    q = sa.select(VISITS.c.hedef_kimlik, sa.func.max(VISITS.c.gerceklesen)).where(
        VISITS.c.tenant_id == tenant, VISITS.c.tur == "cari", VISITS.c.durum == "yapildi").group_by(VISITS.c.hedef_kimlik)
    with engine.connect() as c:
        return {k: str(v)[:10] for k, v in c.execute(q) if v}


def broken_promises(engine: sa.engine.Engine, tenant: str, pay_after: dict[str, Optional[str]], now: date) -> dict[str, dict[str, Any]]:
    """Cari → tarihi geçmiş, sonrasında Logo'da ödeme görünmeyen en son ödeme sözü. Söz tutulmazsa ertesi gün listede üste."""
    q = sa.select(VISITS.c.hedef_kimlik, VISITS.c.soz_odeme_tarihi, VISITS.c.soz_odeme_tutari).where(
        VISITS.c.tenant_id == tenant, VISITS.c.tur == "cari", VISITS.c.soz_odeme_tarihi.isnot(None),
        VISITS.c.soz_odeme_tarihi < now.isoformat(), VISITS.c.durum != "iptal")
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for code, d, amt in c.execute(q):
            paid = pay_after.get(code)
            if paid and paid >= d:
                continue
            if code not in out or d > out[code]["tarih"]:
                out[code] = {"tarih": d, "tutar": amt}
    return out


# ------------------------------------------------------------------ müdür önceliği


def overrides(engine: sa.engine.Engine, tenant: str, now: Optional[date] = None) -> dict[str, dict[str, Any]]:
    now = now or today()
    with engine.connect() as c:
        rows = [_row(r) for r in c.execute(sa.select(OVERRIDES).where(OVERRIDES.c.tenant_id == tenant))]
    out = {}
    for r in rows:
        if r.get("bitis") and r["bitis"] < now.isoformat():
            continue
        out[r["logo_code"]] = {"id": r["id"], "neden": r["neden"], "bitis": r.get("bitis"), "olusturan": r["olusturan"],
                               "olusturma": _iso(r["olusturma"])}
    return out


def add_override(engine: sa.engine.Engine, tenant: str, user: str, code: str, body: dict[str, Any]) -> dict[str, Any]:
    why = text(body.get("neden"))
    if not why:
        raise FieldError("Öne alma nedeni yazılmalı (listede gerekçe olarak görünür).", 422)
    until = _day_only(body.get("bitis"), "Bitiş tarihi")
    row = {"id": _new_id(), "tenant_id": tenant, "logo_code": code, "neden": why[:300], "bitis": until, "olusturan": user, "olusturma": _now()}
    with engine.begin() as c:
        c.execute(OVERRIDES.delete().where(OVERRIDES.c.tenant_id == tenant, OVERRIDES.c.logo_code == code))
        c.execute(OVERRIDES.insert().values(**row))
    return {**row, "olusturma": _iso(row["olusturma"])}


def delete_override(engine: sa.engine.Engine, tenant: str, oid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(OVERRIDES).where(OVERRIDES.c.tenant_id == tenant, OVERRIDES.c.id == oid)).first()
        if r is None:
            raise FieldError("Öncelik kaydı bulunamadı.", 404)
        c.execute(OVERRIDES.delete().where(OVERRIDES.c.id == oid))
    return _row(r)


# ------------------------------------------------------------------ bugünün listesi


def rejected_by_account(collections: list[dict[str, Any]], now: date, days: int = 30) -> dict[str, int]:
    since = (now - timedelta(days=days)).isoformat()
    out: dict[str, int] = {}
    for t in collections:
        if int(num(t.get("durum"))) == src.T_REJECTED and (day(t.get("red_tarihi")) or day(t.get("degisme")) or "") >= since:
            g = guid(t.get("account_id"))
            if g:
                out[g] = out.get(g, 0) + 1
    return out


def ranked(rows: list[dict[str, Any]], *, promises: dict[str, dict[str, Any]], rejected: dict[str, int],
           boosts: dict[str, dict[str, Any]], last_visits: dict[str, str], cycle: int, now: date) -> list[dict[str, Any]]:
    """Satırlara puan ve gerekçe çipi; gecikme sırası temsilci portföyü içinde. Büyükten küçüğe."""
    by_rep: dict[str, dict[str, float]] = {}
    for r in rows:
        by_rep.setdefault(r.get("ad_hesap") or "", {})[r["logo_code"]] = weighted_overdue(r)
    rank: dict[str, float] = {}
    for vals in by_rep.values():
        rank.update(pct_ranks(vals))
    out = []
    for r in rows:
        code = r["logo_code"]
        last = max([x for x in (last_visits.get(code), r.get("saha_son_ziyaret")) if x], default=None)
        pts, chips = score(r, {"gecikmeRank": rank.get(code, 0.0), "soz": promises.get(code),
                               "red": rejected.get(r.get("crm_account_id") or "", 0),
                               "mudur": (boosts.get(code) or {}).get("neden"), "sonZiyaret": last,
                               "today": now, "visitCycleDays": cycle})
        out.append({**r, "puan": pts, "gerekce": chips, "sonZiyaret": last})
    out.sort(key=lambda x: (-x["puan"], -num(x.get("vadesi_gecmis")), x.get("unvan") or ""))
    return out


def customer_card(r: dict[str, Any]) -> dict[str, Any]:
    """Liste satırının ekrana giden biçimi (kişisel veri yok)."""
    return {
        "code": r["logo_code"], "unvan": r.get("unvan"), "il": r.get("il"), "kanal": r.get("kanal"),
        "temsilci": r.get("ad_hesap"), "temsilciAd": r.get("temsilci_ad"), "atama": r.get("atama_kaynagi"),
        "bakiye": r.get("bakiye"), "vadesiGecmis": r.get("vadesi_gecmis"), "kovalar": {k: r.get(k) for k, _ in BUCKETS},
        "plansiz": r.get("plansiz"), "sonOdeme": r.get("son_odeme_tarihi"), "sonFatura": r.get("son_fatura"),
        "ytd": r.get("ytd_net_ciro"), "gecenYil": r.get("gecen_yil_ayni_donem"),
        "hedefBeklenen": r.get("hedef_beklenen"), "hedefAcigi": r.get("hedef_acigi"),
        "riskDoluluk": r.get("risk_doluluk"), "siparisRiskte": r.get("siparis_riskte"),
        "cekOlay": int(num(r.get("karsiliksiz_olay_12ay"))) + int(num(r.get("protesto_olay_12ay"))),
        "puan": r.get("puan"), "gerekce": r.get("gerekce") or [], "sonZiyaret": r.get("sonZiyaret"),
    }


# ------------------------------------------------------------------ tahsilat (CRM onay akışı)


def collection_out(t: dict[str, Any], users: dict[str, dict[str, Any]], accounts: dict[str, dict[str, Any]],
                   labels: dict[str, dict[str, Any]], now: datetime) -> dict[str, Any]:
    st = int(num(t.get("durum")))
    created = t.get("olusturma")
    created_dt = None
    if created:
        try:
            created_dt = datetime.fromisoformat(str(created).replace(" ", "T").replace("Z", "+00:00"))
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            created_dt = None
    owner = users.get(guid(t.get("owner_id")) or "") or {}
    acc = accounts.get(guid(t.get("account_id")) or "") or {}
    code = int(num(t.get("red_sebep"))) or None
    lab = labels.get(guid(t.get("id")) or "")
    reason = src.REJECT_REASON.get(code) if code else None
    ai = None
    if lab and (code in (None, 100000003)):
        ai = {"etiket": src.REJECT_REASON.get(lab["etiket"]), "olasilik": lab.get("olasilik")}
    return {
        "id": guid(t.get("id")), "ad": text(t.get("ad")), "durum": st, "durumAd": src.COLLECTION_STATUS.get(st, str(st)),
        "tip": src.COLLECTION_TYPE.get(int(num(t.get("tip")))), "tutar": opt_num(t.get("tutar")),
        "vade": day(t.get("vade")), "tahsilatTarihi": day(t.get("tahsilat_tarihi")), "olusturma": day(created),
        "onayTarihi": day(t.get("onay_tarihi")), "redTarihi": day(t.get("red_tarihi")),
        "yasSaat": round((now - created_dt).total_seconds() / 3600, 1) if created_dt and st == src.T_PENDING else None,
        "redSebebi": reason, "redMetni": text(t.get("red_metin")), "zekiEtiket": ai,
        "temsilci": owner.get("hesap"), "temsilciAd": owner.get("ad"),
        "musteri": acc.get("unvan"), "code": acc.get("logo_code"),
    }


def collections_view(items: list[dict[str, Any]], *, durum: str, owner_ids: Optional[set[str]], codes: Optional[set[str]],
                     users: dict[str, dict[str, Any]], accounts: dict[str, dict[str, Any]], labels: dict[str, dict[str, Any]],
                     now: Optional[datetime] = None, reject_days: int = 30) -> dict[str, Any]:
    """CRM tahsilatları: `onay-bekliyor` (hepsi, yaşıyla) ya da `reddedildi` (son `reject_days` gün). Kapsam: kaydın sahibi
    kişi ya da cari kişinin portföyünde. Yeniden girdirme yok: kayıt CRM'dedir, burada yalnız görünür."""
    now = now or datetime.now(timezone.utc)
    want = {"onay-bekliyor": src.T_PENDING, "reddedildi": src.T_REJECTED, "onaylandi": src.T_APPROVED,
            "aktarildi": src.T_TRANSFERRED}.get(durum)
    if want is None:
        raise FieldError("Durum onay-bekliyor, reddedildi, onaylandi ya da aktarildi olmalı.", 422)
    since = (now.astimezone(TZ).date() - timedelta(days=reject_days)).isoformat()
    out = []
    for t in items:
        if int(num(t.get("durum"))) != want:
            continue
        if want != src.T_PENDING and (day(t.get("red_tarihi") if want == src.T_REJECTED else t.get("degisme")) or "") < since:
            continue
        if owner_ids is not None:
            acc = accounts.get(guid(t.get("account_id")) or "") or {}
            if guid(t.get("owner_id")) not in owner_ids and (acc.get("logo_code") not in (codes or set())):
                continue
        out.append(collection_out(t, users, accounts, labels, now))
    out.sort(key=lambda x: (x.get("olusturma") or ""), reverse=(want != src.T_PENDING))
    reasons: dict[str, int] = {}
    for x in out:
        k = x["redSebebi"] or (x["zekiEtiket"] or {}).get("etiket") or "Belirtilmemiş"
        reasons[k] = reasons.get(k, 0) + 1
    return {"items": out, "count": len(out), "total": round(sum(x["tutar"] or 0 for x in out), 2),
            "reasons": [{"sebep": k, "adet": v} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])] if want == src.T_REJECTED else []}


# ------------------------------------------------------------------ ödeme planı


def _plan_out(r: dict[str, Any]) -> dict[str, Any]:
    rows = _j(r.get("taksitler_json"), [])
    return {"id": r["id"], "code": r["logo_code"], "unvan": r.get("unvan"), "temsilci": r.get("temsilci"),
            "tutar": r["tutar"], "taksitler": rows, "taksitToplam": round(sum(num(x.get("tutar")) for x in rows), 2),
            "gerekce": r.get("gerekce"), "durum": r["durum"], "durumAd": PLAN_STATES.get(r["durum"], r["durum"]),
            "oneren": r["oneren"], "olusturma": _iso(r.get("olusturma")), "gonderen": r.get("gonderen"),
            "gonderim": _iso(r.get("gonderim")), "onaylayan": r.get("onaylayan"), "zaman": _iso(r.get("zaman")),
            "kararNotu": r.get("karar_notu")}


def _clean_installments(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise FieldError("En az bir taksit girilmeli.", 422)
    out = []
    for i, x in enumerate(raw):
        d = _day_only((x or {}).get("tarih"), f"{i + 1}. taksit tarihi")
        amt = opt_num((x or {}).get("tutar"))
        if not d or amt is None or amt <= 0:
            raise FieldError(f"{i + 1}. taksitin tarihi ve artı tutarı olmalı.", 422)
        out.append({"sira": i + 1, "tarih": d, "tutar": round(amt, 2)})
    out.sort(key=lambda x: x["tarih"])
    for i, x in enumerate(out):
        x["sira"] = i + 1
    return out


def create_plan(engine: sa.engine.Engine, tenant: str, user: str, cust: dict[str, Any], body: dict[str, Any], max_n: int,
                now: Optional[date] = None) -> dict[str, Any]:
    now = now or today()
    sug = suggest_plan(cust, max_n, now)
    n = body.get("taksitSayisi")
    if n not in (None, ""):
        try:
            n = max(1, min(24, int(n)))
        except (TypeError, ValueError):
            raise FieldError("Taksit sayısı tam sayı olmalı.", 422) from None
        start = date.fromisoformat(_day_only(body.get("baslangic"), "İlk taksit tarihi") or sug["taksitler"][0]["tarih"])
        sug["taksitler"] = plan_installments(sug["tutar"], n, start)
        sug["gerekce"] += f" Taksit sayısı öneren tarafından {n} seçildi."
    row = {"id": _new_id(), "tenant_id": tenant, "logo_code": cust["logo_code"], "unvan": cust.get("unvan"),
           "temsilci": cust.get("ad_hesap"), "tutar": sug["tutar"], "taksitler_json": _dump(sug["taksitler"]),
           "gerekce": sug["gerekce"], "durum": "taslak", "oneren": user, "olusturma": _now()}
    with engine.begin() as c:
        c.execute(PLANS.insert().values(**row))
    return _plan_out(row)


def get_plan(engine: sa.engine.Engine, tenant: str, pid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(PLANS).where(PLANS.c.tenant_id == tenant, PLANS.c.id == pid)).first()
    if r is None:
        raise FieldError("Ödeme planı bulunamadı.", 404)
    return _row(r)


def edit_plan(engine: sa.engine.Engine, tenant: str, user: str, pid: str, body: dict[str, Any]) -> dict[str, Any]:
    cur = get_plan(engine, tenant, pid)
    if cur["durum"] != "taslak":
        raise FieldError("Yalnız taslak plan düzenlenir.", 409)
    if cur["oneren"] != user:
        raise FieldError("Taslağı yalnız öneren düzenler.", 403)
    vals: dict[str, Any] = {}
    if "taksitler" in body:
        vals["taksitler_json"] = _dump(_clean_installments(body["taksitler"]))
    if "gerekce" in body:
        vals["gerekce"] = (text(body.get("gerekce")) or "")[:2000] or None
    if vals:
        with engine.begin() as c:
            c.execute(PLANS.update().where(PLANS.c.id == pid).values(**vals))
    return _plan_out({**cur, **vals})


def submit_plan(engine: sa.engine.Engine, tenant: str, user: str, pid: str) -> dict[str, Any]:
    cur = get_plan(engine, tenant, pid)
    if cur["durum"] != "taslak":
        raise FieldError("Yalnız taslak plan onaya gönderilir.", 409)
    if cur["oneren"] != user:
        raise FieldError("Taslağı yalnız öneren onaya gönderir.", 403)
    vals = {"durum": "onayda", "gonderen": user, "gonderim": _now()}
    with engine.begin() as c:
        c.execute(PLANS.update().where(PLANS.c.id == pid).values(**vals))
    return _plan_out({**cur, **vals})


def decide_plan(engine: sa.engine.Engine, tenant: str, user: str, pid: str, approve: bool, note: Optional[str]) -> dict[str, Any]:
    """Onay/red: yalnız onayda plan; gönderen (ve öneren) karar veremez (iki göz). Red gerekçe ister."""
    cur = get_plan(engine, tenant, pid)
    if cur["durum"] != "onayda":
        raise FieldError("Plan onay beklemiyor.", 409)
    if user in (cur.get("gonderen"), cur.get("oneren")):
        raise FieldError("Planı öneren ya da gönderen onaylayamaz; başka bir yetkili karar verir.", 409)
    note = (text(note) or "")[:1000] or None
    if not approve and not note:
        raise FieldError("Geri çevirme nedeni yazılmalı.", 422)
    vals = {"durum": "onayli" if approve else "reddedildi", "onaylayan": user, "zaman": _now(), "karar_notu": note}
    with engine.begin() as c:
        c.execute(PLANS.update().where(PLANS.c.id == pid).values(**vals))
    return _plan_out({**cur, **vals})


def list_plans(engine: sa.engine.Engine, tenant: str, *, codes: Optional[set[str]], durum: str = "", code: str = "") -> list[dict[str, Any]]:
    q = sa.select(PLANS).where(PLANS.c.tenant_id == tenant)
    if durum:
        q = q.where(PLANS.c.durum == durum)
    if code:
        q = q.where(PLANS.c.logo_code == code)
    with engine.connect() as c:
        rows = [_row(r) for r in c.execute(q.order_by(PLANS.c.olusturma.desc()))]
    if codes is not None:
        rows = [r for r in rows if r["logo_code"] in codes]
    return [_plan_out(r) for r in rows]


# ------------------------------------------------------------------ bildirim


def add_event(engine: sa.engine.Engine, tenant: str, owner: str, kind: str, key: str, title: str,
              detail: Optional[str] = None, code: Optional[str] = None) -> bool:
    """Aynı (kişi, tür, anahtar) ikinci kez yazılmaz. Yazıldıysa True."""
    with engine.begin() as c:
        hit = c.execute(sa.select(EVENTS.c.id).where(EVENTS.c.tenant_id == tenant, EVENTS.c.sahip == owner,
                                                     EVENTS.c.tur == kind, EVENTS.c.anahtar == key)).first()
        if hit:
            return False
        c.execute(EVENTS.insert().values(id=_new_id(), tenant_id=tenant, sahip=owner, tur=kind, anahtar=key[:80],
                                         baslik=title[:300], detay=detail, logo_code=code, zaman=_now()))
    return True


def events(engine: sa.engine.Engine, tenant: str, owner: str, days: int = 30) -> list[dict[str, Any]]:
    since = _now() - timedelta(days=days)
    with engine.connect() as c:
        rows = c.execute(sa.select(EVENTS).where(EVENTS.c.tenant_id == tenant, EVENTS.c.sahip == owner, EVENTS.c.zaman >= since)
                         .order_by(EVENTS.c.zaman.desc())).all()
    return [{"id": r.id, "tur": r.tur, "baslik": r.baslik, "detay": r.detay, "code": r.logo_code, "zaman": _iso(r.zaman),
             "goruldu": r.goruldu is not None} for r in rows]


def mark_seen(engine: sa.engine.Engine, tenant: str, owner: str) -> int:
    with engine.begin() as c:
        res = c.execute(EVENTS.update().where(EVENTS.c.tenant_id == tenant, EVENTS.c.sahip == owner, EVENTS.c.goruldu.is_(None))
                        .values(goruldu=_now()))
    return int(res.rowcount or 0)


# ------------------------------------------------------------------ brifing: kitap önerisi ve hedef açığı


def book_target_gaps(cust_prev: dict[str, float], book_prev_total: dict[str, float], cust_cur: dict[str, float],
                     plan_items: list[dict[str, Any]], asof: date, year: int) -> list[dict[str, Any]]:
    """Kitap hedef açığı bu cari için: carinin önceki yıl bu kitaptaki adet payı × kitabın yıllık hedef adedi × aylık
    dağılımla geçen pay − carinin bu yılki adedi. Önceki yıl bu kitabı almamış cari için pay 0 (öneri bölümüne düşer)."""
    out = []
    for it in plan_items:
        code = it.get("stokKodu")
        mine, tot = cust_prev.get(code, 0.0), book_prev_total.get(code, 0.0)
        if mine <= 0 or tot <= 0:
            continue
        share = mine / tot
        adet = num((it.get("hedef") or {}).get("adet"))
        ciro = num((it.get("hedef") or {}).get("ciro"))
        frac = elapsed_fraction([num(m.get("adet")) for m in it.get("aylik") or []], asof, year)
        expected = adet * share * frac
        actual = cust_cur.get(code, 0.0)
        gap = expected - actual
        if gap <= 0.5:
            continue
        unit = ciro / adet if adet > 0 else 0.0
        out.append({"stok": code, "ad": it.get("ad"), "pay": round(share, 4), "hedefAdet": round(adet * share, 1),
                    "beklenen": round(expected, 1), "gerceklesen": round(actual, 1), "acikAdet": round(gap, 1),
                    "acikCiro": round(gap * unit, 2)})
    out.sort(key=lambda x: -x["acikCiro"])
    return out


def suggestions(bought: set[str], similar: dict[str, dict[str, Any]], new_books: dict[str, dict[str, Any]],
                min_similar: int) -> list[dict[str, Any]]:
    """Öneri: bu carinin 24 ayda almadığı, benzer carilerden (aynı şehir + kanal) en az `min_similar`'ının aldığı kitaplar
    (kaç cari aldı, sonra ciro) + yeni çıkan kitaplar (ilk faturalı satışı ayardaki gün içinde). Liste kesilmez."""
    out: dict[str, dict[str, Any]] = {}
    for code, s in similar.items():
        if code in bought or s["cari"] < min_similar:
            continue
        out[code] = {"stok": code, "ad": s.get("ad"), "benzerCari": s["cari"], "benzerCiro": round(s["ciro"], 2),
                     "yeni": code in new_books, "ilkSatis": (new_books.get(code) or {}).get("ilk"), "neden": []}
    for code, nb in new_books.items():
        if code in bought:
            continue
        cur = out.setdefault(code, {"stok": code, "ad": nb.get("ad"), "benzerCari": (similar.get(code) or {}).get("cari", 0),
                                    "benzerCiro": round((similar.get(code) or {}).get("ciro", 0.0), 2), "yeni": True,
                                    "ilkSatis": nb.get("ilk"), "neden": []})
        cur["yeni"] = True
    for x in out.values():
        if x["benzerCari"]:
            x["neden"].append(f"Benzer {x['benzerCari']} cari aldı")
        if x["yeni"]:
            x["neden"].append(f"Yeni çıktı ({x['ilkSatis']})" if x.get("ilkSatis") else "Yeni çıktı")
    return sorted(out.values(), key=lambda x: (-x["benzerCari"], -x["benzerCiro"], not x["yeni"], x["stok"]))


def merge_similar(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """(stok, cari kodu) satırlarından kitap başına ayrı cari sayısı, adet ve ciro (iki yıl firması birleşir)."""
    acc: dict[str, dict[str, Any]] = {}
    for r in rows:
        code = text(r.get("stok"))
        if not code:
            continue
        cur = acc.setdefault(code, {"ad": text(r.get("ad")), "cariler": set(), "adet": 0.0, "ciro": 0.0})
        if num(r.get("adet")) > 0:
            cur["cariler"].add(text(r.get("cari")))
        cur["adet"] += num(r.get("adet"))
        cur["ciro"] += num(r.get("ciro"))
    return {k: {"ad": v["ad"], "cari": len(v["cariler"]), "adet": v["adet"], "ciro": v["ciro"]} for k, v in acc.items()}


def input_hash(b: dict[str, Any]) -> str:
    return hashlib.sha256(_dump(facts_of(b)).encode("utf-8")).hexdigest()


def cached_brief(engine: sa.engine.Engine, tenant: str, code: str, asof: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(BRIEFS).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.logo_code == code, BRIEFS.c.asof == asof)).first()
    return _row(r) if r else None


def save_brief(engine: sa.engine.Engine, tenant: str, code: str, asof: str, h: str, summary: str, books: Any, model: str, user: str) -> None:
    with engine.begin() as c:
        c.execute(BRIEFS.delete().where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.logo_code == code, BRIEFS.c.asof == asof))
        c.execute(BRIEFS.insert().values(tenant_id=tenant, logo_code=code, asof=asof, girdi_hash=h, ozet_metin=summary,
                                         oneri_kitaplar_json=_dump(books), model_is_kimligi=model[:80], olusturan=user, olusturma=_now()))


# ------------------------------------------------------------------ haftalık rapor


def week_bounds(hafta: str, now: Optional[date] = None) -> tuple[date, date]:
    """`2026-W39` ya da bir gün → pazartesi..pazar. Boşsa geçen hafta (pazartesi raporu geçen haftayı anlatır)."""
    now = now or today()
    if not hafta:
        start = now - timedelta(days=now.weekday() + 7)
    elif re.match(r"^\d{4}-W\d{2}$", hafta):
        y, w = int(hafta[:4]), int(hafta[6:])
        try:
            start = date.fromisocalendar(y, w, 1)
        except ValueError:
            raise FieldError("Hafta geçersiz.", 422) from None
    else:
        d = _day_only(hafta, "Hafta")
        start = date.fromisoformat(d) - timedelta(days=date.fromisoformat(d).weekday())
    return start, start + timedelta(days=6)


def weekly_report(rows: list[dict[str, Any]], visits: list[dict[str, Any]], collections: list[dict[str, Any]],
                  users_by_id: dict[str, dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    """Temsilci başına: cari, YTD net alım, geçen yıl aynı dönem, hedef beklenen, hedef oranı, vadesi geçmiş, 90+,
    onay bekleyen/reddedilen (hafta) tahsilat, haftadaki yapılan ziyaret ve not."""
    reps_: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = r.get("ad_hesap") or ""
        cur = reps_.setdefault(key, {"hesap": key or None, "ad": r.get("temsilci_ad") or ("Temsilcisiz" if not key else key),
                                     "cari": 0, "ytd": 0.0, "gecenYil": 0.0, "hedefBeklenen": 0.0, "hedefli": 0,
                                     "vadesiGecmis": 0.0, "k90": 0.0, "onayBekleyen": 0, "onayBekleyenTutar": 0.0,
                                     "reddedilen": 0, "ziyaret": 0, "not": 0, "cekOlay": 0})
        cur["cari"] += 1
        cur["ytd"] += num(r.get("ytd_net_ciro"))
        cur["gecenYil"] += num(r.get("gecen_yil_ayni_donem"))
        if r.get("hedef_beklenen"):
            cur["hedefBeklenen"] += num(r.get("hedef_beklenen"))
            cur["hedefli"] += 1
        cur["vadesiGecmis"] += num(r.get("vadesi_gecmis"))
        cur["k90"] += num(r.get("k_90p"))
        cur["cekOlay"] += int(num(r.get("karsiliksiz_olay_12ay"))) + int(num(r.get("protesto_olay_12ay")))
    s, e = start.isoformat(), end.isoformat()
    for v in visits:
        if v["tur"] != "cari" or v["durum"] != "yapildi":
            continue
        d = (v.get("gerceklesen") or "")[:10]
        if s <= d <= e and v["sahip"] in reps_:
            reps_[v["sahip"]]["ziyaret"] += 1
            if v.get("notu") or v.get("gizliNot"):
                reps_[v["sahip"]]["not"] += 1
    for t in collections:
        owner = (users_by_id.get(guid(t.get("owner_id")) or "") or {}).get("hesap")
        if owner not in reps_:
            continue
        st = int(num(t.get("durum")))
        if st == src.T_PENDING:
            reps_[owner]["onayBekleyen"] += 1
            reps_[owner]["onayBekleyenTutar"] += num(t.get("tutar"))
        elif st == src.T_REJECTED and s <= (day(t.get("red_tarihi")) or "") <= e:
            reps_[owner]["reddedilen"] += 1
    out = []
    for x in reps_.values():
        x["hedefOrani"] = round(x["ytd"] / x["hedefBeklenen"], 4) if x["hedefBeklenen"] > 0 else None
        x["buyume"] = round(x["ytd"] / x["gecenYil"] - 1, 4) if x["gecenYil"] > 0 else None
        for k in ("ytd", "gecenYil", "hedefBeklenen", "vadesiGecmis", "k90", "onayBekleyenTutar"):
            x[k] = round(x[k], 2)
        out.append(x)
    out.sort(key=lambda x: (x["hesap"] is None, (x["ad"] or "").lower()))
    return out


def report_text(items: list[dict[str, Any]], start: date, end: date, link: str = "") -> str:
    lines = [f"Saha haftalık raporu — {start.strftime('%d.%m.%Y')}–{end.strftime('%d.%m.%Y')}", ""]
    for x in items:
        ratio = f"%{round(x['hedefOrani'] * 100)}" if x.get("hedefOrani") is not None else "hedef yok"
        lines.append(f"• {x['ad']}: {x['cari']} cari · yıl başından {_tr_money(x['ytd'])} ({ratio}) · vadesi geçmiş "
                     f"{_tr_money(x['vadesiGecmis'])} (90+ {_tr_money(x['k90'])}) · hafta {x['ziyaret']} ziyaret, "
                     f"{x['reddedilen']} reddedilen tahsilat · onay bekleyen {x['onayBekleyen']}")
    lines += ["", "Vadesi geçmiş tutarlar yaklaşıktır (Logo'da ödeme kapama yok; FIFO)."]
    if link:
        lines.append(link)
    return "\n".join(lines)


def report_xlsx(items: list[dict[str, Any]], start: date, end: date) -> bytes:
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.worksheet.table import Table, TableStyleInfo

    wb = Workbook()
    ws = wb.active
    ws.title = "Saha raporu"
    ws["A1"] = f"Saha haftalık raporu {start.isoformat()} – {end.isoformat()}"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = "Vadesi geçmiş tutarlar yaklaşıktır (Logo'da ödeme kapama yok; FIFO)."
    head = ["Temsilci", "Cari", "Yıl başından net alım", "Geçen yıl aynı dönem", "Büyüme", "Hedef (beklenen)", "Hedef oranı",
            "Vadesi geçmiş", "90+ gün", "Çek/senet olayı (12 ay)", "Onay bekleyen tahsilat", "Onay bekleyen tutar",
            "Reddedilen (hafta)", "Ziyaret (hafta)", "Notlu ziyaret"]
    ws.append([])
    ws.append(head)
    for x in items:
        ws.append([x["ad"], x["cari"], x["ytd"], x["gecenYil"], x["buyume"], x["hedefBeklenen"], x["hedefOrani"],
                   x["vadesiGecmis"], x["k90"], x["cekOlay"], x["onayBekleyen"], x["onayBekleyenTutar"], x["reddedilen"],
                   x["ziyaret"], x["not"]])
    last = 4 + len(items)
    for row in ws.iter_rows(min_row=5, max_row=last):
        for cell in row[2:4] + row[5:6] + row[7:9] + row[11:12]:
            cell.number_format = "#,##0.00"
        for cell in (row[4], row[6]):
            cell.number_format = "0.0%"
    if items:
        t = Table(displayName="SahaRaporu", ref=f"A4:{chr(64 + len(head))}{last}")
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(t)
    for i, w in enumerate([28, 8, 18, 18, 10, 18, 11, 16, 14, 12, 12, 16, 12, 10, 10]):
        ws.column_dimensions[chr(65 + i)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
