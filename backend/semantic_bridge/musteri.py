"""M38 Müşteri ilişkileri ve CRM yönetimi: cari değeri, kayıp riski ve nedenleri, temsilci portföyü, aksiyon kaydı ve
30/90 gün sonucu, CRM veri sağlığı («CRM'de düzeltilecek» listesi), segmentler.

**Akış.** Gece turu (`run_night`, 04:15) Logo'nun iki yıl kopyasından cari × gün faturalı alımı (tek toplu sorgu, firma
başına), CRM'den atama/sipariş/veri sağlığı kolonlarını okur; her müşteri carisi için değer ve risk satırı yazar
(`semantic_musteri_accounts`, tam değiştirme). Veri sağlığı bulguları kalıcıdır (`semantic_musteri_health_findings`):
koşulu kalkan bulgu kendiliğinden kapanır, «CRM'de düzeltildi» işaretlenen bulgu ertesi gece taramada yoksa doğrulanır,
hâlâ varsa yeniden açılır. Ekranlar bu tablolardan okur; cari ayrıntısı son faturaları, kitap kırılımını, aylık alımı ve
CRM siparişlerini canlı okur (5 dk bellek).

**M30 ile ortak.** Temsilci ↔ cari ataması (`field_sales.assign`), CRM ↔ Logo eşleşmesi (`match_clients`), Logo takvimi
(`logo_calendar`), kaynak bağlantısı (`Source`), ziyaretler (`semantic_saha_ziyaret`), tahsilat ve kredi göstergesi
(M30 sinyal tablosu; M59 aynı kaynağı okur) M30'dan çağrılır. M38 değer/kayıp ve veri sağlığına odaklanır.

**Kayıp riski (K2, kural; ağırlıklar ekranda):** `WEIGHTS`. Süre **Logo kesim tarihine** göre ölçülür (donmuş kopyada
herkes riskli görünmesin). Model puan vermez: tekrar kayıt adaylarında «aynı firma / farklı / belirsiz» kapalı küme kararı
(`QueuedLlm.choose`) ve cari ayrıntısında 1–2 cümle neden özeti yazar; özetteki her sayı olgularda geçmek zorunda.

**Yazma:** CRM'e ve Logo'ya hiçbir şey yazılmaz. Aksiyon, bulgu işareti, segment ve puan geçmişi köprünün kendi
tablolarındadır; her yazma uçta `semantic_audit`'e düşer. Risk puanı cariye aleyhe otomatik sonuç doğurmaz (limit, fiyat
değişmez; KVKK md. 11).
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import logging
import re
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import crm_people_rules as people_rules
from semantic_bridge import field_sales as F
from semantic_bridge import field_sales_sources as fs
from semantic_bridge import musteri_sources as src
from semantic_bridge.field_sales_sources import SourceError, day, guid, num, opt_num, text

log = logging.getLogger("semantic.musteri")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()
_lock = threading.Lock()
_ready: set[int] = set()


class MusteriError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ tablolar

ACCOUNTS = sa.Table(
    "semantic_musteri_accounts", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("cari_kodu", sa.String(40), primary_key=True),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("ad", sa.String(300)),
    sa.Column("kanal", sa.String(60)),                   # CRM firma kanalı (yoksa Logo özel kod 2)
    sa.Column("logo_kanal", sa.String(60)),              # Logo CLCARD.SPECODE2 (kayıtlı kanal SQL'iyle aynı)
    sa.Column("bolge", sa.String(100)),                  # il (CRM carinin ili; yoksa Logo)
    sa.Column("temsilci", sa.String(120), index=True),   # AD hesabı (M30 ataması)
    sa.Column("temsilci_ad", sa.String(200)),
    sa.Column("bireysel_mi", sa.Boolean, nullable=False, default=False),
    sa.Column("son_fatura", sa.String(10)),
    sa.Column("son_siparis", sa.String(10)),
    sa.Column("son_ziyaret", sa.String(10)),
    sa.Column("siparis_12ay", sa.Integer),
    sa.Column("net_12ay", sa.Float), sa.Column("net_onceki_12ay", sa.Float), sa.Column("net_yil", sa.Float),
    sa.Column("degisim", sa.Float),
    sa.Column("fatura_12ay", sa.Integer),
    sa.Column("alim_gunu_24ay", sa.Integer),
    sa.Column("medyan_aralik_gun", sa.Float),
    sa.Column("aralik_kaynagi", sa.String(10)),          # kendi | kanal | genel | ayar
    sa.Column("gun_son_alim", sa.Integer),
    sa.Column("iade_orani_12ay", sa.Float), sa.Column("iade_orani_onceki", sa.Float),
    sa.Column("risk_puani", sa.Float),
    sa.Column("risk_duzeyi", sa.String(10), index=True),  # kayip | yuksek | orta | dusuk | yok
    sa.Column("onceki_risk_duzeyi", sa.String(10)),
    sa.Column("risk_gecis", sa.String(10)),              # yüksek/kayıp düzeyine geçtiği gün (gece turu)
    sa.Column("nedenler_json", sa.Text),
    sa.Column("neden_ozeti", sa.Text),
    sa.Column("ozet_kaynagi", sa.String(10)),            # kural | zeki
    sa.Column("ozet_hash", sa.String(64)),
    sa.Column("segment", sa.String(80)),
    sa.Column("deger_dilimi", sa.String(2)),
    sa.Column("egilim", sa.String(10)),
    sa.Column("logo_kesim", sa.String(10)),
    sa.Column("hesaplandi_at", sa.DateTime(timezone=True)),
)
ACTIONS = sa.Table(
    "semantic_musteri_actions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("cari_kodu", sa.String(40), nullable=False, index=True),
    sa.Column("cari_ad", sa.String(300)),
    sa.Column("tur", sa.String(10), nullable=False),     # arama | ziyaret | kampanya | diger
    sa.Column("aciklama", sa.Text, nullable=False),
    sa.Column("sahip", sa.String(120), nullable=False),  # aksiyonu yapacak kişi (AD)
    sa.Column("termin", sa.String(10)),
    sa.Column("durum", sa.String(10), nullable=False),   # acik | yapildi | iptal
    sa.Column("sonuc_notu", sa.Text),
    sa.Column("risk_puani_o_an", sa.Float),
    sa.Column("risk_duzeyi_o_an", sa.String(10)),
    sa.Column("onceki_30g", sa.Float),                   # aksiyondan önceki 30 gün net alım (karşılaştırma tabanı)
    sa.Column("sonuc_30g", sa.Float),                    # aksiyon gününden sonraki 30 gün net alım (Logo; olgunlaşınca)
    sa.Column("sonuc_90g", sa.Float),
    sa.Column("yazan", sa.String(120), nullable=False),
    sa.Column("tarih", sa.String(10), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
)
FINDINGS = sa.Table(
    "semantic_musteri_health_findings", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(20), nullable=False, index=True),
    sa.Column("varlik", sa.String(10), nullable=False),  # account | contact | sistem
    sa.Column("kayit_id", sa.String(200), nullable=False),
    sa.Column("eslesen_kayit_id", sa.String(200)),
    sa.Column("cari_kodu", sa.String(40)),
    sa.Column("ad", sa.String(300)),                     # ticari unvan (şahısta maskeli)
    sa.Column("olasilik", sa.Float),
    sa.Column("ozet", sa.String(500)),
    sa.Column("onem", sa.String(10), nullable=False),    # yuksek | orta | dusuk
    sa.Column("durum", sa.String(20), nullable=False, index=True),  # acik | crmde_duzeltildi | dogrulandi | kapandi | yoksay
    sa.Column("isaret_notu", sa.String(500)),
    sa.Column("isaretleyen", sa.String(120)),
    sa.Column("isaret_zamani", sa.DateTime(timezone=True)),
    sa.Column("ilk_goruldu", sa.String(10), nullable=False),
    sa.Column("son_goruldu", sa.String(10), nullable=False),
    sa.Column("kapanis", sa.String(10)),
)
SCORES = sa.Table(
    "semantic_musteri_health_score", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("tarih", sa.String(10), primary_key=True),
    sa.Column("puan", sa.Float, nullable=False),
    sa.Column("etkin_cari", sa.Integer),
    sa.Column("bulgulu_cari", sa.Integer),
    sa.Column("bulgu_sayilari_json", sa.Text, nullable=False),
)
SEGMENTS = sa.Table(
    "semantic_musteri_segments", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("ad", sa.String(120), nullable=False),
    sa.Column("kural_json", sa.Text, nullable=False),
    sa.Column("boyut", sa.Integer, nullable=False),      # cari sayısı (kişi değil)
    sa.Column("deger", sa.Float),                        # son 12 ay net
    sa.Column("pay", sa.Float),
    sa.Column("tarih", sa.String(10), nullable=False),
)
#: Tekrar adayı çiftine verilen karar (Zeki AI ya da kural): aynı çift her gece yeniden sorulmasın.
PAIRS = sa.Table(
    "semantic_musteri_pair_decisions", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("cift", sa.String(80), primary_key=True),
    sa.Column("karar", sa.String(10), nullable=False),   # ayni | farkli | belirsiz
    sa.Column("olasilik", sa.Float),
    sa.Column("kaynak", sa.String(10), nullable=False),  # zeki | kural
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)
META = sa.Table(
    "semantic_musteri_meta", _md,
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


def _j(s: Any, default: Any) -> Any:
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError):
        return default


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _new_id() -> str:
    return uuid.uuid4().hex


def _row(r: Any) -> dict[str, Any]:
    return dict(r._mapping)


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
    """Ayarlar ekran/ortamdan (`admin.conf`), yoksa varsayılan. M30'un ortak ayarları (cari kodu öneki, ortak hesap, CRM
    şeması, CRM ziyaret kolonu) M30'dan okunur; burada yalnız M38'e özgü eşikler var. Ölçülmemiş varsayımlar parametredir."""
    def i(key: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(str(conf(key, str(default)) or default))))
        except ValueError:
            return default

    def f(key: str, default: float, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(str(conf(key, str(default)) or default).replace(",", "."))))
        except ValueError:
            return default

    def mails(key: str) -> list[str]:
        return [x.strip() for x in (conf(key, "") or "").replace(";", ",").split(",") if "@" in x]

    field = F.settings_from(conf)
    return {
        "codePrefix": field["codePrefix"], "excludedOwners": field["excludedOwners"], "schema": field["schema"],
        "crmVisitColumn": field["crmVisitColumn"],
        "riskHigh": i("MUSTERI_RISK_HIGH", 60, 1, 100),
        "riskMid": i("MUSTERI_RISK_MID", 35, 1, 100),
        "minPurchaseDays": i("MUSTERI_MIN_PURCHASE_DAYS", 3, 2, 50),
        "defaultIntervalDays": i("MUSTERI_DEFAULT_INTERVAL_DAYS", 60, 7, 365),
        "lostMinDays": i("MUSTERI_LOST_MIN_DAYS", 180, 30, 730),
        "lostMultiple": f("MUSTERI_LOST_MULTIPLE", 4.0, 1.5, 20.0),
        "orderFloorDays": i("MUSTERI_ORDER_FLOOR_DAYS", 90, 14, 365),
        "dupRatio": f("MUSTERI_DUP_RATIO", 0.86, 0.5, 0.99),
        "dupWindow": i("MUSTERI_DUP_WINDOW", 6, 2, 50),
        "llmBudgetSec": i("MUSTERI_LLM_BUDGET_SEC", 1200, 0, 20000),
        "dupMinProb": f("MUSTERI_DUP_MIN_PROB", 0.7, 0.34, 0.99),
        "logicalrefFirm": (conf("MUSTERI_LOGICALREF_FIRM", "") or "").strip(),
        "campaignTable": (conf("MUSTERI_CAMPAIGN_TABLE", "obs_kampanyagonderimleriBase") or "").strip(),
        "campaignAccountColumn": (conf("MUSTERI_CAMPAIGN_ACCOUNT_COLUMN", "obs_firmaid") or "").strip(),
        "campaignDateColumn": (conf("MUSTERI_CAMPAIGN_DATE_COLUMN", "CreatedOn") or "").strip(),
        "campaignDays": i("MUSTERI_CAMPAIGN_DAYS", 365, 30, 1825),
        "crmUrl": (conf("MUSTERI_CRM_URL", "") or "").strip(),
        "managerRecipients": mails("MUSTERI_MANAGER_RECIPIENTS"),
        "crmAdminRecipients": mails("MUSTERI_CRM_ADMIN_RECIPIENTS"),
        "repMail": (conf("MUSTERI_REP_MAIL", "1") or "1").strip() in ("1", "true", "evet"),
        "scoreDropAlert": f("MUSTERI_SCORE_DROP_ALERT", 2.0, 0.1, 50.0),
    }


# ------------------------------------------------------------------ değer ve alım aralığı (saf)


def windows(kesim: date) -> dict[str, tuple[date, date]]:
    """Son 12 ay (kesim − 364 … kesim), önceki 12 ay, bu yıl (1 Ocak … kesim), 24 ay (aralık için)."""
    return {
        "son": (kesim - timedelta(days=364), kesim),
        "onceki": (kesim - timedelta(days=729), kesim - timedelta(days=365)),
        "yil": (date(kesim.year, 1, 1), kesim),
        "iki_yil": (kesim - timedelta(days=729), kesim),
    }


def _sum(days: dict[str, dict[str, float]], lo: date, hi: date, key: str) -> float:
    a, b = lo.isoformat(), hi.isoformat()
    return sum(v[key] for g, v in days.items() if a <= g <= b)


def value_stats(days: dict[str, dict[str, float]], kesim: date) -> dict[str, Any]:
    """Tek carinin gün → {satis, iade, fatura} haritasından değer, iade oranı ve alım günleri."""
    w = windows(kesim)
    s12, i12 = _sum(days, *w["son"], "satis"), _sum(days, *w["son"], "iade")
    sp, ip = _sum(days, *w["onceki"], "satis"), _sum(days, *w["onceki"], "iade")
    sy, iy = _sum(days, *w["yil"], "satis"), _sum(days, *w["yil"], "iade")
    lo, hi = (x.isoformat() for x in w["iki_yil"])
    buy = sorted(g for g, v in days.items() if v["satis"] > 0 and lo <= g <= hi)
    last = max((g for g, v in days.items() if v["satis"] > 0 and g <= hi), default=None)
    net, prev = round(s12 - i12, 2), round(sp - ip, 2)
    return {
        "net_12ay": net, "net_onceki_12ay": prev, "net_yil": round(sy - iy, 2),
        "degisim": round(net / prev - 1, 4) if prev > 0 else None,
        "fatura_12ay": int(_sum(days, *w["son"], "fatura")),
        "iade_orani_12ay": round(i12 / s12, 4) if s12 > 0 else None,
        "iade_orani_onceki": round(ip / sp, 4) if sp > 0 else None,
        "alim_gunleri": buy, "son_fatura": last,
        "gun_son_alim": (kesim - date.fromisoformat(last)).days if last else None,
    }


def median_interval(buy_days: list[str]) -> Optional[float]:
    """Ardışık alım günleri arasındaki gün farkının medyanı (en az iki alım)."""
    if len(buy_days) < 2:
        return None
    ds = [date.fromisoformat(x) for x in sorted(buy_days)]
    gaps = [(b - a).days for a, b in zip(ds, ds[1:]) if (b - a).days > 0]
    return float(median(gaps)) if gaps else None


def resolve_intervals(stats: dict[str, dict[str, Any]], kanal_of: dict[str, Optional[str]], min_days: int,
                      default_days: int) -> dict[str, tuple[Optional[float], Optional[str]]]:
    """Carinin medyan aralığı: yeterli alım günü (≥ `min_days`) varsa kendi; yoksa aynı kanaldaki carilerin kendi
    medyanlarının medyanı; o da yoksa bütün carilerin; hiç yoksa ayar. Alımı olmayan carinin aralığı yok."""
    own = {c: median_interval(s["alim_gunleri"]) for c, s in stats.items() if len(s["alim_gunleri"]) >= min_days}
    own = {c: v for c, v in own.items() if v is not None}
    by_k: dict[str, list[float]] = {}
    for c, v in own.items():
        by_k.setdefault(kanal_of.get(c) or "", []).append(v)
    k_med = {k: float(median(v)) for k, v in by_k.items() if v}
    g_med = float(median(own.values())) if own else None
    out: dict[str, tuple[Optional[float], Optional[str]]] = {}
    for c, s in stats.items():
        if not s["alim_gunleri"]:
            out[c] = (None, None)
        elif c in own:
            out[c] = (own[c], "kendi")
        elif (kanal_of.get(c) or "") in k_med:
            out[c] = (k_med[kanal_of.get(c) or ""], "kanal")
        elif g_med is not None:
            out[c] = (g_med, "genel")
        else:
            out[c] = (float(default_days), "ayar")
    return out


# ------------------------------------------------------------------ kayıp riski (kural)

#: (anahtar, en çok puan, ekrandaki ad). Toplam 100; ekranda yazılı.
WEIGHTS: list[tuple[str, int, str]] = [
    ("aralik", 40, "Son alımdan bu yana geçen süre, carinin olağan alım aralığına göre (Logo kesim tarihine kadar)"),
    ("dusus", 30, "Son 12 ay net alımı önceki 12 aya göre düştü"),
    ("iade", 15, "İade oranı önceki 12 aya göre arttı"),
    ("siparis", 15, "CRM'de uzun süredir sipariş yok (bugüne göre)"),
]
_W = {k: w for k, w, _ in WEIGHTS}
LEVELS = {"kayip": "Kayıp", "yuksek": "Yüksek", "orta": "Orta", "dusuk": "Düşük", "yok": "Değerlendirilmedi"}
ACTION_TYPES = {"arama": "Arama", "ziyaret": "Ziyaret", "kampanya": "Kampanya teklifi", "diger": "Diğer"}
ACTION_STATES = {"acik": "Açık", "yapildi": "Yapıldı", "iptal": "İptal"}


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _pct(x: float) -> str:
    return f"%{round(x * 100)}"


def risk(acc: dict[str, Any], st: dict[str, Any], now: date) -> tuple[float, str, list[dict[str, Any]]]:
    """Kural puanı, düzey ve neden çipleri. `acc`: value_stats + medyan_aralik_gun + son_siparis. Süre Logo kesimine
    göre (`gun_son_alim`), CRM sipariş sessizliği bugüne göre ölçülür."""
    chips: list[dict[str, Any]] = []

    def add(key: str, frac: float, label: str) -> None:
        pts = round(_W[key] * _clamp(frac), 1)
        if pts > 0:
            chips.append({"key": key, "points": pts, "label": label})

    net, prev = num(acc.get("net_12ay")), num(acc.get("net_onceki_12ay"))
    gap, med = acc.get("gun_son_alim"), opt_num(acc.get("medyan_aralik_gun"))
    if gap is None or (net <= 0 and prev <= 0 and not acc.get("alim_gunleri")):
        return 0.0, "yok", []
    last_order = acc.get("son_siparis")
    if med and med > 0:
        r = gap / med
        frac = (r - 1.5) / 1.5
        label = f"{gap} gündür alım yok (olağan aralık {round(med)} gün)"
        if last_order and acc.get("son_fatura") and last_order > acc["son_fatura"]:
            frac *= 0.5
            label += f"; CRM'de {last_order} tarihli sipariş var"
        add("aralik", frac, label)
    if prev > 0 and net < prev:
        drop = 1 - max(0.0, net) / prev
        if drop > 0.10:
            add("dusus", (drop - 0.10) / 0.50, f"Net alım {_pct(drop)} düştü ({F.short_money(prev)} → {F.short_money(net)})")
    ir, ip = opt_num(acc.get("iade_orani_12ay")), opt_num(acc.get("iade_orani_onceki"))
    if ir is not None and ir - (ip or 0.0) > 0.05:
        add("iade", (ir - (ip or 0.0) - 0.05) / 0.15, f"İade oranı {_pct(ip or 0.0)} → {_pct(ir)}")
    if acc.get("crm_account_id"):
        thr = max(st["orderFloorDays"], 2 * (med or st["defaultIntervalDays"]))
        if last_order:
            d = (now - date.fromisoformat(last_order)).days
            if d > thr:
                add("siparis", (d - thr) / thr, f"{d} gündür CRM siparişi yok")
    chips.sort(key=lambda c: -c["points"])
    pts = min(100.0, round(sum(c["points"] for c in chips), 1))
    lost_at = max(st["lostMinDays"], st["lostMultiple"] * (med or st["defaultIntervalDays"]))
    if gap >= lost_at and not (last_order and acc.get("son_fatura") and last_order > acc["son_fatura"]):
        level = "kayip"
    elif pts >= st["riskHigh"]:
        level = "yuksek"
    elif pts >= st["riskMid"]:
        level = "orta"
    else:
        level = "dusuk"
    return pts, level, chips


def rule_summary(chips: list[dict[str, Any]]) -> Optional[str]:
    """Kural özeti: en ağır iki neden, tek cümle."""
    if not chips:
        return None
    s = "; ".join(c["label"] for c in chips[:2])
    return s[0].upper() + s[1:] + "."


def at_stake(a: dict[str, Any]) -> float:
    """Risk × değer sıralaması için risk altındaki değer: önceki ve son 12 ayın büyüğü."""
    return max(num(a.get("net_12ay")), num(a.get("net_onceki_12ay")), 0.0)


# ------------------------------------------------------------------ segment (kanal × değer × eğilim)


def trend(degisim: Optional[float], prev: float) -> str:
    if prev <= 0:
        return "yeni"
    if degisim is None:
        return "sabit"
    return "buyuyen" if degisim > 0.10 else "dusen" if degisim < -0.10 else "sabit"


TRENDS = {"buyuyen": "Büyüyen", "sabit": "Sabit", "dusen": "Düşen", "yeni": "Yeni"}


def value_bands(values: dict[str, float]) -> dict[str, str]:
    """ABC: değere göre sıralı, birikimli payın ilk %80'i A, sonraki %15'i B, kalanı C; değeri olmayan «-»."""
    pos = sorted(((c, v) for c, v in values.items() if v > 0), key=lambda x: -x[1])
    tot = sum(v for _, v in pos)
    out = {c: "-" for c in values}
    run = 0.0
    for c, v in pos:
        share_before = run / tot if tot else 1.0
        out[c] = "A" if share_before < 0.80 else "B" if share_before < 0.95 else "C"
        run += v
    return out


def segments_of(rows: list[dict[str, Any]], asof: str) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    total = sum(max(0.0, num(r.get("net_12ay"))) for r in rows) or 0.0
    for r in rows:
        if r.get("deger_dilimi") in (None, "-"):
            continue
        k = (r["deger_dilimi"], r.get("logo_kanal") or r.get("kanal") or "Belirsiz", r.get("egilim") or "sabit")
        g = groups.setdefault(k, {"boyut": 0, "deger": 0.0})
        g["boyut"] += 1
        g["deger"] += num(r.get("net_12ay"))
    out = []
    for (band, kanal, eg), g in sorted(groups.items(), key=lambda kv: -kv[1]["deger"]):
        out.append({"id": hashlib.sha1(f"{band}|{kanal}|{eg}".encode()).hexdigest()[:32],
                    "ad": f"{band} · {kanal} · {TRENDS.get(eg, eg)}",
                    "kural_json": _dump({"deger_dilimi": band, "kanal": kanal, "egilim": eg}),
                    "boyut": g["boyut"], "deger": round(g["deger"], 2),
                    "pay": round(g["deger"] / total, 4) if total else None, "tarih": asof})
    return out


# ------------------------------------------------------------------ kaynak okuması (gece turu)


def read_all(source: F.Source, st: dict[str, Any], now: Optional[date] = None) -> dict[str, Any]:
    """Gece turunun bütün okuması: Logo (takvim, cari kartı, günlük alım) + CRM (atama, sipariş, veri sağlığı).
    Biri düşerse hata (yarım liste yazılmaz)."""
    now = now or today()
    schema, pre = st["schema"], st["codePrefix"]
    warnings: list[str] = []
    t0 = time.monotonic()

    def logo_part(run):
        cal = F.logo_calendar(run, now)
        firms = {int(y): f for y, f in cal["firms"].items()}
        kesim = date.fromisoformat(cal["dataEnd"]) if cal.get("dataEnd") else now
        w = windows(kesim)
        prev_firms = list(dict.fromkeys(f for y, f in sorted(firms.items(), reverse=True)
                                        if f != cal["firm"] and y >= w["iki_yil"][0].year and y <= kesim.year))
        clients = src.read_clients(run, cal["firm"], prev_firms, pre)
        start = w["iki_yil"][0] - timedelta(days=120)          # aksiyon sonucu ve kanal medyanı için pay
        daily = src.read_daily(run, firms, start, kesim, pre)
        codes: dict[str, set[str]] = {}
        for f in sorted(set(firms.values())):
            if f in (cal["firm"], *prev_firms):
                for r in fs.read_rows(run, src.all_client_codes_sql(f)):
                    codes.setdefault(f, set()).add(f"{text(r.get('code'))}\x00{int(num(r.get('ref')))}")
        return {"cal": {**cal, "firms": {str(k): v for k, v in firms.items()}}, "kesim": kesim.isoformat(),
                "clients": clients, "daily": daily, "codes": {k: sorted(v) for k, v in codes.items()}}

    logo = source.logo(logo_part)
    logo_ms = int((time.monotonic() - t0) * 1000)
    t1 = time.monotonic()

    def crm_part(run):
        out = {"users": fs.lower_keys(run(fs.crm_users_sql(schema))),
               "allUsers": fs.lower_keys(run(src.crm_all_users_sql(schema))),
               "accounts": fs.lower_keys(run(fs.crm_accounts_sql(schema))),
               "health": fs.lower_keys(run(src.crm_health_accounts_sql(schema))),
               "orders": fs.lower_keys(run(src.crm_last_orders_sql(schema, now - timedelta(days=365)))),
               "contacts": fs.lower_keys(run(src.crm_contact_consent_sql(schema))),
               "visits": (fs.lower_keys(run(fs.crm_visits_sql(schema, st["crmVisitColumn"], now - timedelta(days=730))))
                          if st["crmVisitColumn"] else [])}
        try:
            out["campaigns"] = fs.lower_keys(run(src.crm_campaign_sends_sql(
                schema, st["campaignTable"], st["campaignAccountColumn"], st["campaignDateColumn"],
                now - timedelta(days=st["campaignDays"])))) if st["campaignTable"] else None
        except Exception as e:  # noqa: BLE001 — seçenekli kaynak (yapısı ölçülecek)
            log.warning("musteri: kampanya gönderimleri okunamadı: %s", e)
            out["campaigns"] = None
            warnings.append("Kampanya gönderim tablosu okunamadı; «izinsiz cariye kampanya» denetimi bu turda yapılmadı.")
        out["security"] = security_scan(run, schema, warnings)
        return out

    crm = source.crm(crm_part)
    crm_ms = int((time.monotonic() - t1) * 1000)
    return {"logo": logo, "crm": crm, "warnings": warnings, "logoMs": logo_ms, "crmMs": crm_ms, "now": now.isoformat()}


def security_scan(run: Callable[[str], list[dict[str, Any]]], schema: str, warnings: list[str]) -> list[dict[str, Any]]:
    """Şifre içeren kolon/görünüm/günlük: yalnız varlık ve dolu satır sayısı. Değer hiçbir sorguda seçilmez;
    `new_kargofirmasi` tablosuna sorgu atılmaz (yalnız kolon adının varlığı)."""
    out: list[dict[str, Any]] = []
    try:
        cols = fs.lower_keys(run(src.secret_columns_sql(schema)))
    except Exception as e:  # noqa: BLE001
        log.warning("musteri: kolon sözlüğü okunamadı: %s", e)
        warnings.append("Güvenlik taraması: kolon sözlüğü okunamadı.")
        return out
    for c in cols:
        t, k = text(c.get("tablo")) or "", text(c.get("kolon")) or ""
        if not t.lower().endswith("base") and not t.lower().startswith("new_"):
            continue
        n = None
        if not (t in src.NEVER_QUERY_TABLES or t.lower().startswith("new_kargofirmasi")):
            try:
                rows = fs.lower_keys(run(src.secret_count_sql(schema, t, k)))
                n = int(num(rows[0].get("n"))) if rows else 0
            except Exception as e:  # noqa: BLE001
                log.info("musteri: %s.%s sayılamadı: %s", t, k, e)
        if n == 0:
            continue
        out.append({"kayit_id": f"{t}.{k}", "ozet": f"{t} tablosunda «{k}» kolonu şifre/anahtar içeriyor"
                    + (f" ({n} dolu satır)" if n is not None else " (satır sayılmadı: bu tabloya sorgu atılmaz)"),
                    "onem": "yuksek"})
    try:
        rows = fs.lower_keys(run(src.webservice_log_secret_sql(schema)))
        n = int(num(rows[0].get("n"))) if rows else 0
        if n:
            out.append({"kayit_id": "new_webservicelogBase.new_requestJSON",
                        "ozet": f"Web servis günlüğünde istek gövdesi şifre alanı taşıyor ({n} satır)", "onem": "yuksek"})
    except Exception as e:  # noqa: BLE001
        log.info("musteri: web servis günlüğü sayılamadı: %s", e)
    try:
        for v in fs.lower_keys(run(src.views_sql(schema))):
            name = text(v.get("ad"))
            if name:
                out.append({"kayit_id": f"view:{name}", "ozet": f"«{name}» görünümü kullanıcı adı/şifre açığa çıkarıyor olabilir",
                            "onem": "yuksek"})
    except Exception as e:  # noqa: BLE001
        log.info("musteri: görünüm listesi okunamadı: %s", e)
    return out


# ------------------------------------------------------------------ gece turu: cari değer ve risk (saf)


def build_accounts(data: dict[str, Any], st: dict[str, Any], visits_by_code: dict[str, str],
                   previous: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Okunan veriden cari satırları (saf; test edilir). `previous`: önceki turun satırları (düzey geçişi, özet)."""
    logo, crm = data["logo"], data["crm"]
    now = date.fromisoformat(data["now"])
    kesim = date.fromisoformat(logo["kesim"])
    assigned = F.assign(crm["accounts"], crm["users"], st["excludedOwners"])
    rows = F.match_clients(assigned, logo["clients"])
    health = {guid(h.get("account_id")): h for h in crm.get("health") or []}
    orders = {guid(o.get("account_id")): o for o in crm.get("orders") or []}
    crm_visits = {guid(v.get("account_id")): day(v.get("son")) for v in crm.get("visits") or []}
    stats = {r["logo_code"]: value_stats(logo["daily"].get(r["logo_code"], {}), kesim) for r in rows}
    kanal_of = {r["logo_code"]: r.get("logo_kanal") or r.get("kanal") for r in rows}
    intervals = resolve_intervals(stats, kanal_of, st["minPurchaseDays"], st["defaultIntervalDays"])
    out: list[dict[str, Any]] = []
    asof = now.isoformat()
    for r in rows:
        code = r["logo_code"]
        s = stats[code]
        med, how = intervals[code]
        acc_id = r.get("crm_account_id")
        o = orders.get(acc_id) if acc_id else None
        h = health.get(acc_id) if acc_id else None
        last_visit = max([x for x in (visits_by_code.get(code), crm_visits.get(acc_id)) if x], default=None)
        a = {**s, "crm_account_id": acc_id, "medyan_aralik_gun": round(med, 1) if med else None,
             "son_siparis": day(o.get("son")) if o else None}
        pts, level, chips = risk(a, st, now)
        prev_row = previous.get(code) or {}
        prev_level = prev_row.get("risk_duzeyi")
        hot = level in ("yuksek", "kayip")
        gecis = (prev_row.get("risk_gecis") or asof) if hot and prev_level in ("yuksek", "kayip") else (asof if hot else None)
        summ = rule_summary(chips)
        h_ = hashlib.sha256(_dump(chips).encode()).hexdigest()
        keep = prev_row.get("ozet_hash") == h_ and prev_row.get("ozet_kaynagi") == "zeki"
        out.append({
            "cari_kodu": code, "crm_account_id": acc_id, "ad": r.get("unvan"), "kanal": r.get("kanal"),
            "logo_kanal": r.get("logo_kanal"), "bolge": r.get("il") or r.get("logo_il"),
            "temsilci": r.get("ad_hesap"), "temsilci_ad": r.get("temsilci_ad"),
            "bireysel_mi": bool(h and people_rules.is_person_account(h)),
            "son_fatura": s["son_fatura"], "son_siparis": a["son_siparis"], "son_ziyaret": last_visit,
            "siparis_12ay": int(num(o.get("adet"))) if o else None,
            "net_12ay": s["net_12ay"], "net_onceki_12ay": s["net_onceki_12ay"], "net_yil": s["net_yil"],
            "degisim": s["degisim"], "fatura_12ay": s["fatura_12ay"], "alim_gunu_24ay": len(s["alim_gunleri"]),
            "medyan_aralik_gun": a["medyan_aralik_gun"], "aralik_kaynagi": how, "gun_son_alim": s["gun_son_alim"],
            "iade_orani_12ay": s["iade_orani_12ay"], "iade_orani_onceki": s["iade_orani_onceki"],
            "risk_puani": pts, "risk_duzeyi": level, "onceki_risk_duzeyi": prev_level, "risk_gecis": gecis,
            "nedenler_json": _dump(chips),
            "neden_ozeti": prev_row.get("neden_ozeti") if keep else summ,
            "ozet_kaynagi": "zeki" if keep else ("kural" if summ else None), "ozet_hash": h_,
            "egilim": trend(s["degisim"], s["net_onceki_12ay"]), "logo_kesim": kesim.isoformat(),
        })
    bands = value_bands({x["cari_kodu"]: num(x["net_12ay"]) for x in out})
    for x in out:
        x["deger_dilimi"] = bands[x["cari_kodu"]]
        x["segment"] = (f"{x['deger_dilimi']} · {x.get('logo_kanal') or x.get('kanal') or 'Belirsiz'} · "
                        f"{TRENDS.get(x['egilim'], x['egilim'])}") if x["deger_dilimi"] != "-" else None
    info = {"asof": asof, "kesim": kesim.isoformat(), "year": logo["cal"]["year"], "firm": logo["cal"]["firm"],
            "prevFirm": logo["cal"].get("prevFirm"), "firms": logo["cal"]["firms"], "accounts": len(out),
            "assigned": sum(1 for x in out if x["temsilci"]),
            "levels": {k: sum(1 for x in out if x["risk_duzeyi"] == k) for k in LEVELS},
            "warnings": data.get("warnings") or [], "logoMs": data.get("logoMs"), "crmMs": data.get("crmMs")}
    return out, info


def write_accounts(engine: sa.engine.Engine, tenant: str, rows: list[dict[str, Any]]) -> None:
    """Tam değiştirme, tek işlemde (okuyan yarım liste görmez)."""
    at = _now()
    with engine.begin() as c:
        c.execute(ACCOUNTS.delete().where(ACCOUNTS.c.tenant_id == tenant))
        for i in range(0, len(rows), 1000):
            part = [{**r, "tenant_id": tenant, "hesaplandi_at": at} for r in rows[i:i + 1000]]
            if part:
                c.execute(ACCOUNTS.insert(), part)


def write_segments(engine: sa.engine.Engine, tenant: str, segs: list[dict[str, Any]]) -> None:
    with engine.begin() as c:
        c.execute(SEGMENTS.delete().where(SEGMENTS.c.tenant_id == tenant))
        if segs:
            c.execute(SEGMENTS.insert(), [{**s, "tenant_id": tenant} for s in segs])


def previous_accounts(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    q = sa.select(ACCOUNTS.c.cari_kodu, ACCOUNTS.c.risk_duzeyi, ACCOUNTS.c.risk_gecis, ACCOUNTS.c.neden_ozeti,
                  ACCOUNTS.c.ozet_kaynagi, ACCOUNTS.c.ozet_hash).where(ACCOUNTS.c.tenant_id == tenant)
    with engine.connect() as c:
        return {r.cari_kodu: _row(r) for r in c.execute(q)}


# ------------------------------------------------------------------ aksiyon sonucu (30/90 gün)


def action_outcomes(actions: list[dict[str, Any]], daily: dict[str, dict[str, dict[str, float]]], kesim: date) -> list[dict[str, Any]]:
    """Aksiyon gününden sonraki 30 ve 90 gün net alım (Logo; kesim tarihi pencereyi kapsayınca), öncesindeki 30 gün taban.
    Olgunlaşmamış pencere None kalır (sıfır yazılmaz)."""
    out = []
    for a in actions:
        if a.get("durum") == "iptal":
            continue
        t = date.fromisoformat(a["tarih"])
        days = daily.get(a["cari_kodu"], {})

        def net(lo: date, hi: date) -> float:
            return round(_sum(days, lo, hi, "satis") - _sum(days, lo, hi, "iade"), 2)

        upd = {"id": a["id"], "onceki_30g": net(t - timedelta(days=30), t - timedelta(days=1)),
               "sonuc_30g": net(t, t + timedelta(days=29)) if kesim >= t + timedelta(days=29) else None,
               "sonuc_90g": net(t, t + timedelta(days=89)) if kesim >= t + timedelta(days=89) else None}
        if any(upd[k] != a.get(k) for k in ("onceki_30g", "sonuc_30g", "sonuc_90g")):
            out.append(upd)
    return out


def write_outcomes(engine: sa.engine.Engine, updates: list[dict[str, Any]]) -> int:
    if not updates:
        return 0
    with engine.begin() as c:
        for u in updates:
            c.execute(ACTIONS.update().where(ACTIONS.c.id == u["id"]).values(
                onceki_30g=u["onceki_30g"], sonuc_30g=u["sonuc_30g"], sonuc_90g=u["sonuc_90g"]))
    return len(updates)


def action_effect(actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Olgunlaşmış aksiyonlarda yeniden alım oranı (30/90 gün), riskli düzeyde yazılanlar ayrıca."""
    def rate(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
        done = [a for a in items if a.get(key) is not None]
        return {"olgun": len(done), "alan": sum(1 for a in done if num(a.get(key)) > 0),
                "oran": round(sum(1 for a in done if num(a.get(key)) > 0) / len(done), 4) if done else None}

    live = [a for a in actions if a.get("durum") != "iptal"]
    risky = [a for a in live if a.get("risk_duzeyi_o_an") in ("yuksek", "kayip")]
    return {"toplam": len(live), "gun30": rate(live, "sonuc_30g"), "gun90": rate(live, "sonuc_90g"),
            "riskli30": rate(risky, "sonuc_30g"), "riskli90": rate(risky, "sonuc_90g")}


# ------------------------------------------------------------------ veri sağlığı (saf)

HEALTH_TYPES = {
    "logo_bagi_yok": "Logo bağı yok",
    "olasi_tekrar": "Olası tekrar kayıt",
    "eksik_kanal": "Kanal bilgisi eksik",
    "sahipsiz": "Sahipsiz kayıt",
    "ortak_hesap": "Ortak hesaba ait",
    "izin_celiskisi": "İzin çelişkisi",
    "guvenlik": "Güvenlik bulgusu",
}
HEALTH_STATES = {"acik": "Açık", "crmde_duzeltildi": "CRM'de düzeltildi (doğrulama bekliyor)", "dogrulandi": "Doğrulandı",
                 "kapandi": "Kendiliğinden kapandı", "yoksay": "Yok sayıldı"}
ONEM = {"yuksek": "Yüksek", "orta": "Orta", "dusuk": "Düşük"}
_LEGAL = {"ltd", "sti", "şti", "limited", "sirketi", "şirketi", "as", "a", "s", "anonim", "san", "sanayi", "tic",
          "ticaret", "ve", "paz", "pazarlama", "ltdsti", "aş", "vs", "ith", "ihr", "ithalat", "ihracat", "ins", "insaat",
          "inşaat", "yay", "yayincilik", "yayıncılık", "dag", "dagitim", "dağıtım", "org", "organizasyon"}


def norm_name(s: Optional[str]) -> str:
    """Ad karşılaştırma anahtarı: Türkçe harf katlama, noktalama, hukuki ekler («Ltd. Şti.», «A.Ş.», «San. Tic.»)."""
    t = F.fold(s or "")
    t = re.sub(r"[^0-9a-z]+", " ", t)
    words = [w for w in t.split() if w not in _LEGAL]
    return " ".join(words)


def pair_key(a: str, b: str) -> str:
    x, y = sorted([a, b])
    return hashlib.sha1(f"{x}|{y}".encode()).hexdigest()[:32]


def finding_id(tenant: str, tur: str, varlik: str, kayit: str, eslesen: Optional[str]) -> str:
    return hashlib.sha1(f"{tenant}|{tur}|{varlik}|{kayit}|{eslesen or ''}".encode()).hexdigest()[:32]


def duplicate_candidates(accs: list[dict[str, Any]], ratio: float, window: int) -> list[dict[str, Any]]:
    """Olası tekrar çiftleri. Kural: aynı cari kodu (1,0), aynı Logo bağı (0,95), aynı normal ad + il (0,9; vergi dairesi
    iki kayıtta dolu ve farklıysa model sorulur). Bulanık: aynı il ve aynı ilk kelimedeki kayıtlar ada göre sıralanır, her
    kayıt sonraki `window` kayıtla karşılaştırılır (sıralı komşuluk); benzerlik ≥ `ratio` olan çift modele gider."""
    by_id = {guid(a.get("account_id")): a for a in accs if guid(a.get("account_id"))}
    pairs: dict[str, dict[str, Any]] = {}

    def put(a: str, b: str, p: Optional[float], why: str, ask: bool) -> None:
        if a == b:
            return
        k = pair_key(a, b)
        cur = pairs.get(k)
        if cur is None or (p or 0) > (cur["olasilik"] or 0):
            x, y = sorted([a, b])
            pairs[k] = {"cift": k, "a": x, "b": y, "olasilik": p, "neden": why, "sor": ask}

    def group(key: Callable[[dict[str, Any]], Optional[str]], p: float, why: str) -> None:
        g: dict[str, list[str]] = {}
        for i, a in by_id.items():
            k = key(a)
            if k:
                g.setdefault(k, []).append(i)
        for ids in g.values():
            ids.sort()
            for j in range(1, len(ids)):
                put(ids[0], ids[j], p, why, False)

    group(lambda a: (text(a.get("cari_kodu")) or "").strip().upper() or None, 1.0, "Aynı cari kodu")
    group(lambda a: (text(a.get("logicalref")) or "").strip() or None, 0.95, "Aynı Logo bağı")
    names = {i: norm_name(a.get("ad")) for i, a in by_id.items()}
    il = {i: F.fold(text(a.get("il")) or "") for i, a in by_id.items()}
    exact: dict[tuple[str, str], list[str]] = {}
    for i, n in names.items():
        if n:
            exact.setdefault((n, il[i]), []).append(i)
    for ids in exact.values():
        ids.sort()
        for j in range(1, len(ids)):
            a, b = by_id[ids[0]], by_id[ids[j]]
            va, vb = F.fold(text(a.get("vergi_dairesi")) or ""), F.fold(text(b.get("vergi_dairesi")) or "")
            if va and vb and va != vb:
                put(ids[0], ids[j], None, "Aynı ad ve il, vergi dairesi farklı", True)
            else:
                put(ids[0], ids[j], 0.9, "Aynı ad ve il", False)
    blocks: dict[tuple[str, str], list[str]] = {}
    for i, n in names.items():
        if n:
            blocks.setdefault((il[i], n.split()[0]), []).append(i)
    for ids in blocks.values():
        ids.sort(key=lambda i: (names[i], i))
        for x in range(len(ids)):
            for y in range(x + 1, min(len(ids), x + 1 + window)):
                a, b = ids[x], ids[y]
                if names[a] == names[b]:
                    continue
                r = difflib.SequenceMatcher(None, names[a], names[b]).ratio()
                if r >= ratio:
                    put(a, b, None, f"Ad benzerliği %{round(r * 100)}", True)
    return list(pairs.values())


def dup_prompt(a: dict[str, Any], b: dict[str, Any]) -> str:
    """Modele yalnız ticari unvan, il ve vergi dairesi gider (şahıs carisi hiç sorulmaz)."""
    def line(x: dict[str, Any]) -> str:
        return (f"Unvan: {text(x.get('ad')) or '-'} · İl: {text(x.get('il')) or '-'} · "
                f"Vergi dairesi: {text(x.get('vergi_dairesi')) or '-'}")
    return ("Bir yayınevinin müşteri (cari) kayıtlarında olası tekrarları ayıklıyoruz. İki kayıt aynı işletme mi?\n"
            f"1) {line(a)}\n2) {line(b)}\n"
            "Kısaltma, «Ltd. Şti.» gibi ekler ve yazım farkı aynı işletme sayılır; farklı şube ya da farklı kişi farklıdır.")


DUP_CHOICES = ["Aynı işletme", "Farklı işletme", "Belirsiz"]
DUP_KEYS = {"Aynı işletme": "ayni", "Farklı işletme": "farkli", "Belirsiz": "belirsiz"}


def health_findings(data: dict[str, Any], st: dict[str, Any], decisions: dict[str, dict[str, Any]],
                    tenant: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Bulgu listesi (saf). `decisions`: çift → {karar, olasilik}. Dönüş: bulgular, modele sorulacak çiftler, sayılar.
    Bulgu kimliği içerikten türetilir; aynı koşul her gece aynı kimliği verir."""
    crm, logo = data["crm"], data["logo"]
    now = date.fromisoformat(data["now"])
    accs = crm.get("health") or []
    users = {guid(u.get("id")): u for u in crm.get("allUsers") or []}
    excluded = {x.strip().lower() for x in st["excludedOwners"]}
    orders = {guid(o.get("account_id")): o for o in crm.get("orders") or []}
    all_codes: set[str] = set()
    refs: dict[str, set[int]] = {}
    for f, items in (logo.get("codes") or {}).items():
        for it in items:
            code, _, ref = it.partition("\x00")
            all_codes.add(code.strip().upper())
            refs.setdefault(f, set()).add(int(ref or 0))
    ref_firm = st["logicalrefFirm"] or logo["cal"]["firm"]
    ref_set = refs.get(ref_firm, set())
    out: list[dict[str, Any]] = []

    def importance(acc_id: Optional[str]) -> str:
        o = orders.get(acc_id) if acc_id else None
        if o and int(num(o.get("adet"))) > 0:
            return "yuksek"
        return "orta" if o else "dusuk"

    def add(tur: str, varlik: str, kayit: str, ozet: str, onem: str, acc: Optional[dict[str, Any]] = None,
            eslesen: Optional[str] = None, p: Optional[float] = None) -> None:
        out.append({"id": finding_id(tenant, tur, varlik, kayit, eslesen), "tur": tur, "varlik": varlik, "kayit_id": kayit,
                    "eslesen_kayit_id": eslesen, "cari_kodu": text(acc.get("cari_kodu")) if acc else None,
                    "ad": people_rules.masked_name(acc, text(acc.get("ad"))) if acc else None,
                    "olasilik": p, "ozet": ozet[:500], "onem": onem})

    by_id = {}
    for a in accs:
        aid = guid(a.get("account_id"))
        if not aid:
            continue
        by_id[aid] = a
        code = (text(a.get("cari_kodu")) or "").strip().upper()
        ref = text(a.get("logicalref")) or ""
        if not code and not ref:
            add("logo_bagi_yok", "account", aid, "Cari kodu ve Logo bağı boş", importance(aid), a)
        elif not ((code and code in all_codes) or (ref.isdigit() and int(ref) in ref_set)):
            add("logo_bagi_yok", "account", aid, "Cari kodu / Logo bağı dolu ama Logo'da karşılığı bulunamadı", importance(aid), a)
        if a.get("kanal") is None and a.get("kanal_tipi") is None:
            add("eksik_kanal", "account", aid, "Firma kanalı ve kanal tipi boş",
                "orta" if importance(aid) == "yuksek" else "dusuk", a)
        owner = users.get(guid(a.get("owner_id")))
        if int(num(a.get("owner_type")) or 8) != 8:
            add("sahipsiz", "account", aid, "Kayıt bir takıma atanmış; sorumlu kişi yok", importance(aid), a)
        elif owner is None or int(num(owner.get("kapali"))) == 1:
            add("sahipsiz", "account", aid, "Kaydın sahibi devre dışı ya da bulunamayan kullanıcı", importance(aid), a)
        elif (text(owner.get("ad")) or "").lower() in excluded:
            add("ortak_hesap", "account", aid, f"Kaydın sahibi ortak hesap «{text(owner.get('ad'))}»", importance(aid), a)
        if people_rules.is_person_account(a) and int(num(a.get("toplu_yok"))) == 0 and int(num(a.get("izin_kaniti"))) == 0:
            add("izin_celiskisi", "account", aid, "Bireysel carinin toplu e-posta izni açık ama izin kaydı (URL/IP) yok", "orta", a)
    campaigns = crm.get("campaigns")
    if campaigns is not None:
        for k in campaigns:
            aid = guid(k.get("account_id"))
            a = by_id.get(aid)
            if a is None or int(num(a.get("toplu_yok"))) != 1:
                continue
            last, since = day(k.get("son")), day(a.get("eposta_izin_tarihi"))
            if last and (since is None or last > since):
                add("izin_celiskisi", "account", aid, f"Toplu e-postaya izin vermeyen cariye kampanya gönderimi ({last})", "yuksek", a,
                    eslesen="kampanya")
    for c in crm.get("contacts") or []:
        cid = guid(c.get("contact_id"))
        if not cid or int(num(c.get("toplu_yok"))) == 1:
            continue
        miss = [n for n, k in (("KVKK onayı", "kvkk"), ("İYS onayı", "iys")) if int(num(c.get(k))) != 1]
        if miss:
            parent = by_id.get(guid(c.get("account_id")))
            add("izin_celiskisi", "contact", cid, f"Kişi kaydında toplu e-posta izni açık ama {' ve '.join(miss)} yok",
                "dusuk", parent)
    ask: list[dict[str, Any]] = []
    for p in duplicate_candidates(list(by_id.values()), st["dupRatio"], st["dupWindow"]):
        a, b = by_id[p["a"]], by_id[p["b"]]
        prob, why = p["olasilik"], p["neden"]
        if p["sor"]:
            d = decisions.get(p["cift"])
            if d and d["karar"] == "farkli":
                continue
            if d and d["karar"] == "ayni":
                prob, why = d.get("olasilik"), f"{why}; Zeki AI: aynı işletme"
            elif d and d["karar"] == "belirsiz":
                why = f"{why}; Zeki AI: belirsiz"
            elif people_rules.is_person_account(a) or people_rules.is_person_account(b):
                why = f"{why}; şahıs kaydı, modele sorulmadı"
            else:
                ask.append(p)
                why = f"{why}; Zeki AI kararı bekliyor"
        other = people_rules.masked_name(b, text(b.get("ad"))) or "-"
        add("olasi_tekrar", "account", p["a"], f"{why} — eş kayıt: {other}"
            + (f" ({text(b.get('cari_kodu'))})" if text(b.get("cari_kodu")) else ""),
            "yuksek" if (prob or 0) >= 0.9 else "orta", a, eslesen=p["b"], p=prob)
    for s in crm.get("security") or []:
        add("guvenlik", "sistem", s["kayit_id"], s["ozet"], s["onem"])
    counts = {k: sum(1 for f in out if f["tur"] == k) for k in HEALTH_TYPES}
    flagged = {f["kayit_id"] for f in out if f["varlik"] == "account"}
    etkin = len(by_id)
    score = round(100 * (etkin - len(flagged)) / etkin, 1) if etkin else None
    vd: dict[str, int] = {}
    for c in crm.get("contacts") or []:
        k = str(int(num(c.get("veri_durumu")))) if c.get("veri_durumu") is not None else "bos"
        vd[k] = vd.get(k, 0) + 1
    kan: dict[str, int] = {}
    for a in by_id.values():
        k = fs.CHANNEL.get(int(num(a.get("kanal")))) if a.get("kanal") is not None else "Boş"
        kan[k or "Diğer kod"] = kan.get(k or "Diğer kod", 0) + 1
    info = {"tarih": now.isoformat(), "puan": score, "etkin_cari": etkin, "bulgulu_cari": len(flagged), "sayilar": counts,
            "veriDurumu": vd, "crmKanal": kan, "kisi": len(crm.get("contacts") or [])}
    return out, ask, info


def sync_findings(engine: sa.engine.Engine, tenant: str, found: list[dict[str, Any]], on: str) -> dict[str, int]:
    """Bulguları kalıcı tabloya işler. Yeni → açık. Görülen → son_goruldu; «kapandı/doğrulandı» iken yeniden görülürse
    açılır; «CRM'de düzeltildi» iken hâlâ görülürse açılır (doğrulama tutmadı). Görülmeyen açık bulgu → kendiliğinden
    kapandı; görülmeyen «CRM'de düzeltildi» → doğrulandı. «Yok sayıldı» görüldükçe öyle kalır, koşul kalkınca kapanır."""
    ensure(engine)
    with engine.connect() as c:
        cur = {r.id: _row(r) for r in c.execute(sa.select(
            FINDINGS.c.id, FINDINGS.c.durum, FINDINGS.c.isaret_notu).where(FINDINGS.c.tenant_id == tenant))}
    seen = {f["id"] for f in found}
    ins, upd, stats = [], [], {"yeni": 0, "yeniden_acilan": 0, "dogrulanan": 0, "kapanan": 0, "tutmayan": 0}
    for f in found:
        old = cur.get(f["id"])
        vals = {k: f[k] for k in ("cari_kodu", "ad", "olasilik", "ozet", "onem")}
        if old is None:
            ins.append({**f, "tenant_id": tenant, "durum": "acik", "ilk_goruldu": on, "son_goruldu": on})
            stats["yeni"] += 1
            continue
        u = {"b_id": f["id"], **{f"b_{k}": v for k, v in vals.items()}, "b_son": on, "b_durum": old["durum"],
             "b_not": old.get("isaret_notu"), "b_kapanis": None}
        if old["durum"] in ("kapandi", "dogrulandi"):
            u["b_durum"] = "acik"
            stats["yeniden_acilan"] += 1
        elif old["durum"] == "crmde_duzeltildi":
            u["b_durum"] = "acik"
            u["b_not"] = f"CRM'de düzeltildi işaretlenmişti; {on} taramasında hâlâ var."
            stats["tutmayan"] += 1
        upd.append(u)
    closes = []
    for fid, old in cur.items():
        if fid in seen:
            continue
        if old["durum"] == "acik":
            closes.append({"b_id": fid, "b_durum": "kapandi", "b_kapanis": on})
            stats["kapanan"] += 1
        elif old["durum"] == "crmde_duzeltildi":
            closes.append({"b_id": fid, "b_durum": "dogrulandi", "b_kapanis": on})
            stats["dogrulanan"] += 1
        elif old["durum"] == "yoksay":              # koşul kalktı: yok sayılan bulgu da kapanır
            closes.append({"b_id": fid, "b_durum": "kapandi", "b_kapanis": on})
            stats["kapanan"] += 1
    with engine.begin() as c:
        for i in range(0, len(ins), 1000):
            c.execute(FINDINGS.insert(), ins[i:i + 1000])
        # bindparam adları kolon adından farklı olmalı (SQLAlchemy aynı adı SET için ayırır).
        if upd:
            c.execute(FINDINGS.update().where(FINDINGS.c.id == sa.bindparam("b_id")).values(
                cari_kodu=sa.bindparam("b_cari_kodu"), ad=sa.bindparam("b_ad"), olasilik=sa.bindparam("b_olasilik"),
                ozet=sa.bindparam("b_ozet"), onem=sa.bindparam("b_onem"), son_goruldu=sa.bindparam("b_son"),
                durum=sa.bindparam("b_durum"), isaret_notu=sa.bindparam("b_not"), kapanis=sa.bindparam("b_kapanis")), upd)
        if closes:
            c.execute(FINDINGS.update().where(FINDINGS.c.id == sa.bindparam("b_id")).values(
                durum=sa.bindparam("b_durum"), kapanis=sa.bindparam("b_kapanis")), closes)
    return stats


def save_score(engine: sa.engine.Engine, tenant: str, info: dict[str, Any]) -> Optional[float]:
    """Günün puanını yazar (aynı gün ikinci tur üstüne yazar); önceki günün puanını döndürür."""
    with engine.begin() as c:
        prev = c.execute(sa.select(SCORES.c.puan).where(SCORES.c.tenant_id == tenant, SCORES.c.tarih < info["tarih"])
                         .order_by(SCORES.c.tarih.desc()).limit(1)).scalar()
        c.execute(SCORES.delete().where(SCORES.c.tenant_id == tenant, SCORES.c.tarih == info["tarih"]))
        if info.get("puan") is not None:
            c.execute(SCORES.insert().values(tenant_id=tenant, tarih=info["tarih"], puan=info["puan"], etkin_cari=info["etkin_cari"],
                                             bulgulu_cari=info["bulgulu_cari"], bulgu_sayilari_json=_dump(info["sayilar"])))
    return prev


def decisions(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        return {r.cift: {"karar": r.karar, "olasilik": r.olasilik} for r in
                c.execute(sa.select(PAIRS).where(PAIRS.c.tenant_id == tenant))}


def save_decision(engine: sa.engine.Engine, tenant: str, cift: str, karar: str, p: Optional[float], kaynak: str) -> None:
    with engine.begin() as c:
        c.execute(PAIRS.delete().where(PAIRS.c.tenant_id == tenant, PAIRS.c.cift == cift))
        c.execute(PAIRS.insert().values(tenant_id=tenant, cift=cift, karar=karar, olasilik=p, kaynak=kaynak, zaman=_now()))


# ------------------------------------------------------------------ okuma (ekran)


def account_rows(engine: sa.engine.Engine, tenant: str, owner: Optional[str]) -> list[dict[str, Any]]:
    """Cari satırları. `owner` None = herkes (yetkili); portföy süzgeci burada, köprüde uygulanır."""
    q = sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant)
    if owner is not None:
        q = q.where(ACCOUNTS.c.temsilci == owner)
    with engine.connect() as c:
        return [_row(r) for r in c.execute(q)]


def one(engine: sa.engine.Engine, tenant: str, code: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(ACCOUNTS).where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.cari_kodu == code)).first()
    return _row(r) if r else None


def in_scope(engine: sa.engine.Engine, tenant: str, user: str, code: str, all_scope: bool) -> dict[str, Any]:
    row = one(engine, tenant, code)
    if row is None:
        raise MusteriError("Bu cari listede yok (gece turu henüz koşmadı ya da cari kodu yanlış).", 404)
    if not all_scope and (row.get("temsilci") or "") != user:
        raise MusteriError("Bu cari sizin portföyünüzde değil.", 403)
    return row


def reps(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    q = sa.select(ACCOUNTS.c.temsilci, sa.func.max(ACCOUNTS.c.temsilci_ad), sa.func.count()).where(
        ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.temsilci.isnot(None)).group_by(ACCOUNTS.c.temsilci)
    with engine.connect() as c:
        out = [{"hesap": a, "ad": n or a, "cari": int(k)} for a, n, k in c.execute(q)]
    return sorted(out, key=lambda x: (x["ad"] or "").lower())


def card(r: dict[str, Any]) -> dict[str, Any]:
    """Liste/kart biçimi (ekran). Kişi verisi yok: unvan ticari addır (şahıs carisi yalnız portföy sahibine ve yetkiliye
    gelir; liste zaten kapsamla süzülür)."""
    return {
        "code": r["cari_kodu"], "ad": r.get("ad"), "kanal": r.get("kanal"), "logoKanal": r.get("logo_kanal"),
        "bolge": r.get("bolge"), "temsilci": r.get("temsilci"), "temsilciAd": r.get("temsilci_ad"),
        "bireysel": bool(r.get("bireysel_mi")),
        "sonFatura": r.get("son_fatura"), "sonSiparis": r.get("son_siparis"), "sonZiyaret": r.get("son_ziyaret"),
        "net12": r.get("net_12ay"), "netOnceki": r.get("net_onceki_12ay"), "netYil": r.get("net_yil"),
        "degisim": r.get("degisim"), "fatura12": r.get("fatura_12ay"), "aralik": r.get("medyan_aralik_gun"),
        "aralikKaynagi": r.get("aralik_kaynagi"), "gunSonAlim": r.get("gun_son_alim"),
        "iade12": r.get("iade_orani_12ay"), "iadeOnceki": r.get("iade_orani_onceki"),
        "puan": r.get("risk_puani"), "duzey": r.get("risk_duzeyi"), "duzeyAd": LEVELS.get(r.get("risk_duzeyi") or "", ""),
        "gecis": r.get("risk_gecis"), "nedenler": _j(r.get("nedenler_json"), []), "ozet": r.get("neden_ozeti"),
        "ozetKaynagi": r.get("ozet_kaynagi"), "segment": r.get("segment"), "dilim": r.get("deger_dilimi"),
        "egilim": r.get("egilim"), "kesim": r.get("logo_kesim"),
    }


SORTS = {
    "oncelik": lambda r: (-(num(r.get("risk_puani")) / 100) * at_stake(r), r["cari_kodu"]),
    "puan": lambda r: (-num(r.get("risk_puani")), -at_stake(r)),
    "deger": lambda r: (-num(r.get("net_12ay")), r["cari_kodu"]),
    "yil": lambda r: (-num(r.get("net_yil")), r["cari_kodu"]),
    "degisim": lambda r: (num(r.get("degisim")) if r.get("degisim") is not None else 9e9, r["cari_kodu"]),
    "ad": lambda r: ((r.get("ad") or "").lower(), r["cari_kodu"]),
    "son": lambda r: (-(r.get("gun_son_alim") if r.get("gun_son_alim") is not None else -1), r["cari_kodu"]),
}


def filter_rows(rows: list[dict[str, Any]], *, kanal: str = "", bolge: str = "", risk_: str = "", q: str = "",
                segment: str = "") -> list[dict[str, Any]]:
    out = rows
    if kanal:
        k = F.fold(kanal)
        out = [r for r in out if F.fold(r.get("logo_kanal") or "Belirsiz") == k]
    if bolge:
        b = F.fold(bolge)
        out = [r for r in out if F.fold(r.get("bolge") or "") == b]
    if risk_:
        wanted = {x for x in risk_.split(",") if x in LEVELS}
        if risk_ == "riskli":
            wanted = {"yuksek", "kayip"}
        out = [r for r in out if r.get("risk_duzeyi") in wanted]
    if segment:
        out = [r for r in out if (r.get("segment") or "") == segment]
    if q.strip():
        n = F.fold(q)
        out = [r for r in out if n in F.fold(f"{r.get('ad') or ''} {r['cari_kodu']} {r.get('bolge') or ''}")]
    return out


def overview(rows: list[dict[str, Any]], actions: list[dict[str, Any]], score: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Özet: kanal (Logo özel kod 2) × aktif cari, son 12 ay değer, bu yıl değer, riskli cari; bu hafta bakılacaklar."""
    kan: dict[str, dict[str, Any]] = {}
    for r in rows:
        k = r.get("logo_kanal") or "Belirsiz"
        g = kan.setdefault(k, {"kanal": k, "aktif": 0, "net12": 0.0, "netYil": 0.0, "riskli": 0, "kayip": 0})
        if num(r.get("net_12ay")) > 0 or num(r.get("fatura_12ay")) > 0:
            g["aktif"] += 1
        g["net12"] += num(r.get("net_12ay"))
        g["netYil"] += num(r.get("net_yil"))
        g["riskli"] += 1 if r.get("risk_duzeyi") == "yuksek" else 0
        g["kayip"] += 1 if r.get("risk_duzeyi") == "kayip" else 0
    chans = sorted(kan.values(), key=lambda g: -g["net12"])
    for g in chans:
        g["net12"], g["netYil"] = round(g["net12"], 2), round(g["netYil"], 2)
    hot = sorted([r for r in rows if r.get("risk_duzeyi") in ("yuksek", "kayip")], key=SORTS["oncelik"])
    return {
        "kpi": {"cari": len(rows), "aktif": sum(g["aktif"] for g in chans), "net12": round(sum(g["net12"] for g in chans), 2),
                "netYil": round(sum(g["netYil"] for g in chans), 2),
                "riskli": sum(g["riskli"] for g in chans), "kayip": sum(g["kayip"] for g in chans),
                "saglik": score.get("puan") if score else None},
        "kanallar": chans, "bakilacak": [card(r) for r in hot[:10]], "bakilacakToplam": len(hot),
        "aksiyon": action_effect(actions),
    }


# ------------------------------------------------------------------ aksiyon kaydı


def _action_out(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": r["id"], "code": r["cari_kodu"], "cariAd": r.get("cari_ad"), "tur": r["tur"],
            "turAd": ACTION_TYPES.get(r["tur"], r["tur"]), "aciklama": r["aciklama"], "sahip": r["sahip"],
            "termin": r.get("termin"), "durum": r["durum"], "durumAd": ACTION_STATES.get(r["durum"], r["durum"]),
            "sonucNotu": r.get("sonuc_notu"), "riskPuani": r.get("risk_puani_o_an"), "riskDuzeyi": r.get("risk_duzeyi_o_an"),
            "onceki30": r.get("onceki_30g"), "sonuc30": r.get("sonuc_30g"), "sonuc90": r.get("sonuc_90g"),
            "yazan": r["yazan"], "tarih": r["tarih"], "olusturma": _iso(r.get("olusturma")),
            "guncelleyen": r.get("guncelleyen"), "guncelleme": _iso(r.get("guncelleme"))}


def _day_only(v: Any, what: str) -> Optional[str]:
    if v in (None, ""):
        return None
    s = str(v)[:10]
    try:
        date.fromisoformat(s)
    except ValueError as e:
        raise MusteriError(f"{what} tarihi geçersiz (YYYY-AA-GG).", 422) from e
    return s


def add_action(engine: sa.engine.Engine, tenant: str, user: str, acc: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    tur = str(body.get("tur") or "")
    if tur not in ACTION_TYPES:
        raise MusteriError("Aksiyon türü arama, ziyaret, kampanya ya da diger olmalı.", 422)
    desc = (text(body.get("aciklama")) or "")[:2000]
    if not desc:
        raise MusteriError("Aksiyonun açıklaması boş olamaz.", 422)
    sahip = (text(body.get("sahip")) or acc.get("temsilci") or user).strip().lower()[:120]
    row = {"id": _new_id(), "tenant_id": tenant, "cari_kodu": acc["cari_kodu"], "cari_ad": acc.get("ad"), "tur": tur,
           "aciklama": desc, "sahip": sahip, "termin": _day_only(body.get("termin"), "Termin"), "durum": "acik",
           "risk_puani_o_an": acc.get("risk_puani"), "risk_duzeyi_o_an": acc.get("risk_duzeyi"), "yazan": user,
           "tarih": today().isoformat(), "olusturma": _now()}
    with engine.begin() as c:
        c.execute(ACTIONS.insert().values(**row))
    return _action_out(row)


def get_action(engine: sa.engine.Engine, tenant: str, aid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(ACTIONS).where(ACTIONS.c.tenant_id == tenant, ACTIONS.c.id == aid)).first()
    if r is None:
        raise MusteriError("Aksiyon bulunamadı.", 404)
    return _row(r)


def update_action(engine: sa.engine.Engine, tenant: str, user: str, aid: str, body: dict[str, Any], all_scope: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Durum, sonuç notu, termin, sahip, açıklama. Yazan, sahip ya da bütün carileri gören değiştirebilir."""
    cur = get_action(engine, tenant, aid)
    if not all_scope and user not in (cur["yazan"], cur["sahip"]):
        raise MusteriError("Bu aksiyonu yalnız yazan, sorumlusu ya da yöneticisi değiştirebilir.", 403)
    vals: dict[str, Any] = {}
    if "durum" in body:
        if body["durum"] not in ACTION_STATES:
            raise MusteriError("Durum acik, yapildi ya da iptal olmalı.", 422)
        vals["durum"] = body["durum"]
    if "sonucNotu" in body:
        vals["sonuc_notu"] = str(body["sonucNotu"]).strip()[:2000] if text(body.get("sonucNotu")) else None
    if "termin" in body:
        vals["termin"] = _day_only(body.get("termin"), "Termin")
    if "aciklama" in body:
        d = (text(body.get("aciklama")) or "")[:2000]
        if not d:
            raise MusteriError("Aksiyonun açıklaması boş olamaz.", 422)
        vals["aciklama"] = d
    if "sahip" in body and text(body.get("sahip")):
        vals["sahip"] = str(body["sahip"]).strip().lower()[:120]
    diff = {k: {"eski": cur.get(k), "yeni": v} for k, v in vals.items() if cur.get(k) != v}
    if diff:
        with engine.begin() as c:
            c.execute(ACTIONS.update().where(ACTIONS.c.id == aid).values(**vals, guncelleyen=user, guncelleme=_now()))
    return _action_out(get_action(engine, tenant, aid)), diff


def list_actions(engine: sa.engine.Engine, tenant: str, *, codes: Optional[set[str]] = None, code: str = "", durum: str = "",
                 person: str = "") -> list[dict[str, Any]]:
    q = sa.select(ACTIONS).where(ACTIONS.c.tenant_id == tenant)
    if code:
        q = q.where(ACTIONS.c.cari_kodu == code)
    if durum:
        q = q.where(ACTIONS.c.durum == durum)
    with engine.connect() as c:
        rows = [_row(r) for r in c.execute(q.order_by(ACTIONS.c.olusturma.desc()))]
    if codes is not None:
        rows = [r for r in rows if r["cari_kodu"] in codes or (person and person in (r["yazan"], r["sahip"]))]
    return rows


# ------------------------------------------------------------------ veri sağlığı (ekran)


def _finding_out(r: dict[str, Any], crm_url: str) -> dict[str, Any]:
    link = None
    if crm_url and r["varlik"] in ("account", "contact"):
        etn = "account" if r["varlik"] == "account" else "contact"
        link = f"{crm_url.rstrip('/')}/main.aspx?etn={etn}&pagetype=entityrecord&id=%7B{r['kayit_id']}%7D"
    return {"id": r["id"], "tur": r["tur"], "turAd": HEALTH_TYPES.get(r["tur"], r["tur"]), "varlik": r["varlik"],
            "kayit": r["kayit_id"], "eslesen": r.get("eslesen_kayit_id"), "code": r.get("cari_kodu"), "ad": r.get("ad"),
            "olasilik": r.get("olasilik"), "ozet": r.get("ozet"), "onem": r["onem"], "onemAd": ONEM.get(r["onem"], r["onem"]),
            "durum": r["durum"], "durumAd": HEALTH_STATES.get(r["durum"], r["durum"]), "not": r.get("isaret_notu"),
            "isaretleyen": r.get("isaretleyen"), "isaretZamani": _iso(r.get("isaret_zamani")),
            "ilk": r.get("ilk_goruldu"), "son": r.get("son_goruldu"), "kapanis": r.get("kapanis"), "crmLink": link}


def list_findings(engine: sa.engine.Engine, tenant: str, *, tur: str = "", durum: str = "", onem: str = "", q: str = "",
                  security: bool = False) -> list[dict[str, Any]]:
    s = sa.select(FINDINGS).where(FINDINGS.c.tenant_id == tenant)
    if tur:
        s = s.where(FINDINGS.c.tur == tur)
    if not security:
        s = s.where(FINDINGS.c.tur != "guvenlik")
    if durum == "acik-hepsi":
        s = s.where(FINDINGS.c.durum.in_(("acik", "crmde_duzeltildi")))
    elif durum:
        s = s.where(FINDINGS.c.durum == durum)
    if onem:
        s = s.where(FINDINGS.c.onem == onem)
    with engine.connect() as c:
        rows = [_row(r) for r in c.execute(s)]
    if q.strip():
        n = F.fold(q)
        rows = [r for r in rows if n in F.fold(f"{r.get('ad') or ''} {r.get('cari_kodu') or ''} {r['kayit_id']} {r.get('ozet') or ''}")]
    order = {"yuksek": 0, "orta": 1, "dusuk": 2}
    rows.sort(key=lambda r: (order.get(r["onem"], 3), r["tur"], r.get("ad") or "", r["id"]))
    return rows


def finding_counts(engine: sa.engine.Engine, tenant: str, security: bool) -> dict[str, dict[str, int]]:
    q = sa.select(FINDINGS.c.tur, FINDINGS.c.durum, sa.func.count()).where(FINDINGS.c.tenant_id == tenant) \
        .group_by(FINDINGS.c.tur, FINDINGS.c.durum)
    out: dict[str, dict[str, int]] = {}
    with engine.connect() as c:
        for t, d, n in c.execute(q):
            if t == "guvenlik" and not security:
                continue
            out.setdefault(t, {})[d] = int(n)
    return out


def mark_finding(engine: sa.engine.Engine, tenant: str, user: str, fid: str, body: dict[str, Any], security: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    durum = str(body.get("durum") or "")
    if durum not in ("crmde_duzeltildi", "yoksay", "acik"):
        raise MusteriError("İşaret crmde_duzeltildi, yoksay ya da acik olmalı.", 422)
    note = (text(body.get("not")) or None)
    if durum == "yoksay" and not note:
        raise MusteriError("Yok saymanın gerekçesi yazılmalı.", 422)
    with engine.connect() as c:
        r = c.execute(sa.select(FINDINGS).where(FINDINGS.c.tenant_id == tenant, FINDINGS.c.id == fid)).first()
    if r is None:
        raise MusteriError("Bulgu bulunamadı.", 404)
    cur = _row(r)
    if cur["tur"] == "guvenlik" and not security:
        raise MusteriError("Güvenlik bulgularını işaretleme yetkiniz yok.", 403)
    if cur["durum"] in ("kapandi", "dogrulandi") and durum != "acik":
        raise MusteriError("Bu bulgu zaten kapanmış.", 409)
    with engine.begin() as c:
        c.execute(FINDINGS.update().where(FINDINGS.c.id == fid).values(
            durum=durum, isaret_notu=(note[:500] if note else None), isaretleyen=user, isaret_zamani=_now()))
    return _finding_out({**cur, "durum": durum, "isaret_notu": note, "isaretleyen": user, "isaret_zamani": _now()}, ""), \
        {"durum": {"eski": cur["durum"], "yeni": durum}, "not": note}


def score_history(engine: sa.engine.Engine, tenant: str, days: int = 365) -> list[dict[str, Any]]:
    since = (today() - timedelta(days=max(1, days))).isoformat()
    with engine.connect() as c:
        rows = c.execute(sa.select(SCORES).where(SCORES.c.tenant_id == tenant, SCORES.c.tarih >= since)
                         .order_by(SCORES.c.tarih)).all()
    return [{"tarih": r.tarih, "puan": r.puan, "etkin": r.etkin_cari, "bulgulu": r.bulgulu_cari,
             "sayilar": _j(r.bulgu_sayilari_json, {})} for r in rows]


def list_segments(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(SEGMENTS).where(SEGMENTS.c.tenant_id == tenant).order_by(SEGMENTS.c.deger.desc())).all()
    return [{"id": r.id, "ad": r.ad, "kural": _j(r.kural_json, {}), "boyut": r.boyut, "deger": r.deger, "pay": r.pay,
             "tarih": r.tarih} for r in rows]


# ------------------------------------------------------------------ Zeki AI özeti (olgular; rakamı model üretmez)


def facts_of(r: dict[str, Any]) -> list[str]:
    """Özetin olguları: yalnız hesaplanmış rakamlar ve kural nedenleri. Şahıs carisinin adı olgulara girmez."""
    tr = F._tr_money
    out = []
    if r.get("net_12ay") is not None:
        out.append(f"Son 12 ay net alım {tr(num(r['net_12ay']))}; önceki 12 ay {tr(num(r.get('net_onceki_12ay')))}.")
    if r.get("gun_son_alim") is not None:
        out.append(f"Son faturadan bu yana {r['gun_son_alim']} gün geçti (Logo verisi {r.get('logo_kesim')} tarihine kadar).")
    if r.get("medyan_aralik_gun"):
        out.append(f"Olağan alım aralığı {round(num(r['medyan_aralik_gun']))} gün.")
    if r.get("iade_orani_12ay") is not None:
        out.append(f"İade oranı son 12 ay %{round(num(r['iade_orani_12ay']) * 100)}"
                   + (f", önceki 12 ay %{round(num(r['iade_orani_onceki']) * 100)}." if r.get("iade_orani_onceki") is not None else "."))
    if r.get("son_siparis"):
        out.append(f"CRM'deki son sipariş {r['son_siparis']}.")
    if r.get("son_ziyaret"):
        out.append(f"Son ziyaret {r['son_ziyaret']}.")
    for c in _j(r.get("nedenler_json"), []):
        out.append(f"Neden: {c['label']}.")
    return out


def summary_prompt(r: dict[str, Any], facts: list[str]) -> str:
    who = "bu cari" if r.get("bireysel_mi") else f"«{r.get('ad') or r['cari_kodu']}» ({r.get('bolge') or '-'}, {r.get('logo_kanal') or r.get('kanal') or '-'})"
    return ("Bir yayınevinin satış temsilcisine, " + who + " için kayıp riskinin nedenini 1–2 kısa Türkçe cümleyle yaz ve "
            "bir aksiyon öner. Yalnız aşağıdaki olgulardaki sayıları kullan; yeni sayı, tarih ya da yüzde yazma.\n"
            + "\n".join(f"- {x}" for x in facts))


def summary_hash(r: dict[str, Any]) -> str:
    return hashlib.sha256((r.get("nedenler_json") or "[]").encode()).hexdigest()


def save_summary(engine: sa.engine.Engine, tenant: str, code: str, textv: str, source: str, h: str) -> None:
    with engine.begin() as c:
        c.execute(ACCOUNTS.update().where(ACCOUNTS.c.tenant_id == tenant, ACCOUNTS.c.cari_kodu == code).values(
            neden_ozeti=textv, ozet_kaynagi=source, ozet_hash=h))


# ------------------------------------------------------------------ dışa aktarma ve e-posta metni


def csv_bytes(header: list[str], rows: Iterable[list[Any]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(header)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue().encode("utf-8-sig")


def accounts_csv(rows: list[dict[str, Any]]) -> bytes:
    head = ["Cari kodu", "Unvan", "Kanal", "Bölge", "Temsilci", "Son fatura", "Son 12 ay net", "Önceki 12 ay net",
            "Değişim", "Alım aralığı (gün)", "Son alımdan gün", "İade oranı 12 ay", "Risk puanı", "Risk düzeyi", "Neden",
            "Segment", "Logo kesim"]
    return csv_bytes(head, ([r["cari_kodu"], r.get("ad"), r.get("logo_kanal") or r.get("kanal"), r.get("bolge"),
                             r.get("temsilci_ad") or r.get("temsilci"), r.get("son_fatura"), r.get("net_12ay"),
                             r.get("net_onceki_12ay"), r.get("degisim"), r.get("medyan_aralik_gun"), r.get("gun_son_alim"),
                             r.get("iade_orani_12ay"), r.get("risk_puani"), LEVELS.get(r.get("risk_duzeyi") or "", ""),
                             r.get("neden_ozeti"), r.get("segment"), r.get("logo_kesim")] for r in rows))


def findings_csv(rows: list[dict[str, Any]]) -> bytes:
    """«CRM'de düzeltilecek» listesi: CRM'e elle işlenecek kayıtlar (portal CRM'e yazmaz)."""
    head = ["Bulgu", "Önem", "Durum", "CRM kaydı", "Eş kayıt", "Cari kodu", "Unvan", "Açıklama", "İlk görülme", "Son görülme"]
    return csv_bytes(head, ([HEALTH_TYPES.get(r["tur"], r["tur"]), ONEM.get(r["onem"], r["onem"]),
                             HEALTH_STATES.get(r["durum"], r["durum"]), r["kayit_id"], r.get("eslesen_kayit_id"),
                             r.get("cari_kodu"), r.get("ad"), r.get("ozet"), r.get("ilk_goruldu"), r.get("son_goruldu")]
                            for r in rows))


def rep_mail_text(rows: list[dict[str, Any]], link: str) -> str:
    lines = [f"Bu hafta kayıp riski yükselen carileriniz: {len(rows)}", ""]
    for r in rows:
        lines.append(f"• {r.get('ad') or r['cari_kodu']} ({r['cari_kodu']}) — {LEVELS.get(r['risk_duzeyi'], '')}, puan "
                     f"{round(num(r.get('risk_puani')))}: {r.get('neden_ozeti') or ''}")
    if link:
        lines += ["", f"Portföyünüz: {link}"]
    return "\n".join(lines)


def manager_mail_text(rows: list[dict[str, Any]], asof: str, link: str) -> str:
    hot = sorted([r for r in rows if r.get("risk_duzeyi") in ("yuksek", "kayip")], key=SORTS["oncelik"])
    new = [r for r in hot if r.get("risk_gecis") and r["risk_gecis"] >= (date.fromisoformat(asof) - timedelta(days=7)).isoformat()]
    by_rep: dict[str, int] = {}
    for r in hot:
        k = r.get("temsilci_ad") or r.get("temsilci") or "Temsilcisiz"
        by_rep[k] = by_rep.get(k, 0) + 1
    lines = [f"Kayıp riski özeti ({asof}): yüksek {sum(1 for r in hot if r['risk_duzeyi'] == 'yuksek')}, "
             f"kayıp {sum(1 for r in hot if r['risk_duzeyi'] == 'kayip')}; bu hafta yeni {len(new)}.", "",
             "Temsilci başına riskli cari:"]
    lines += [f"• {k}: {v}" for k, v in sorted(by_rep.items(), key=lambda kv: -kv[1])]
    lines += ["", "Bu hafta yeni girenler (risk × değer sırası):"]
    lines += [f"• {r.get('ad') or r['cari_kodu']} — {r.get('temsilci_ad') or '-'} — {r.get('neden_ozeti') or ''}" for r in new]
    if link:
        lines += ["", link]
    return "\n".join(lines)


def monthly_series(months: list[dict[str, Any]], kesim: date, span: int = 24) -> list[dict[str, Any]]:
    """Son `span` ayı boşlukları sıfırla doldurur (grafikte kayıp ay görünür)."""
    have = {m["ay"]: m for m in months}
    out = []
    y, m = kesim.year, kesim.month
    seq = []
    for _ in range(span):
        seq.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    for k in reversed(seq):
        out.append(have.get(k) or {"ay": k, "satis": 0.0, "iade": 0.0, "net": 0.0})
    return out


def numbers_ok(summary: str, facts: Iterable[str]) -> bool:
    return F.numbers_ok(summary, facts)
