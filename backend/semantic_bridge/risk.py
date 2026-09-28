"""M47 Risk yönetimi ve uyum: risk kaydı (olasılık × etki, sahip, aksiyon, gözden geçirme), gösterge (KRI) tanımı ve
ölçüm geçmişi, eşik kenarı ve «gözden geçir» kuyruğu, uyum yükümlülükleri ve takvimi (kanıt dosyasıyla), sigorta
poliçeleri ve iş sürekliliği (BCP) kaydı, çeyreklik risk brifingi (Zeki AI taslağı → insan onayı).

**İlkeler (analiz §8):**
- Portal Logo'ya ve CRM'e yazmaz; bütün kayıtlar köprünün `semantic_risk_*` / `semantic_compliance_*` tablolarında.
- Risk puanı insan kararıdır (K3): sistem olasılık/etkiyi hiç değiştirmez; göstergesi eşiği aşan riski yalnız
  «gözden geçir» kuyruğuna koyar. Zeki AI risk taslağı yazar ama puanlamaz.
- Hukuki hüküm üretilmez: gösterge değeri inceleme adayıdır; ekranda «uyumsuz», «ceza» gibi sonuç yazmaz.
- Demo veri yok: kayıt boş açılır. Hazır gösterge tanımları (kütüphane, `risk_sources.LIBRARY`) değer değil tanımdır;
  **eşikleri boş** gelir — eşik sahibi önerir, başka biri onaylar (sürümlü; hazırlayan onaylayamaz).
- KVKK işleme envanteri M49 Veri güvenliği modülünde tutulur (bağlantı noktası `risk_api` → `kvkk`); burada yalnız
  KVKK alanındaki uyum yükümlülükleri vardır. Poliçe numarası yalnız maskeli saklanır.

Gösterge durumu: `artis_kotu` yönünde değer ≥ kırmızı eşik → kırmızı, ≥ sarı → sarı, değilse yeşil; `azalis_kotu`
tersine. Eşik yoksa «eşik yok», değer okunamadıysa «ölçülemedi». Bildirim kenarda gider (`edge`): kırmızıya ilk
geçişte bir kez; kırmızıda kalırsa `ALERT_REMIND_HOURS` dolunca bir kez daha (uyarılar altyapısıyla aynı kural).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

log = logging.getLogger("semantic.risk")
TZ = ZoneInfo("Europe/Istanbul")
_md = sa.MetaData()


def _ts(name: str, **kw: Any) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


RISKS = sa.Table(
    "semantic_risk_register", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("baslik", sa.String(300), nullable=False),
    sa.Column("tanim", sa.Text),
    sa.Column("neden", sa.Text),
    sa.Column("sonuc", sa.Text),
    sa.Column("kategori", sa.String(20), nullable=False),
    sa.Column("alt_kategori", sa.String(120)),
    sa.Column("sahip", sa.String(120)),                             # portal kullanıcı adı
    sa.Column("sahip_eposta", sa.String(200)),
    sa.Column("olasilik", sa.Integer),                              # 1–5; insan girer (öneride boş)
    sa.Column("etki", sa.Integer),                                  # 1–5
    sa.Column("puan", sa.Integer),                                  # olasılık × etki
    sa.Column("egilim", sa.String(10)),                             # artiyor | sabit | azaliyor
    sa.Column("durum", sa.String(12), nullable=False),              # oneri | acik | izleniyor | kabul | kapandi | reddedildi
    sa.Column("kaynak", sa.String(10), nullable=False),             # elle | gosterge | denetim
    sa.Column("kaynak_ref", sa.String(120)),
    sa.Column("gozden_gecirme_gun", sa.Integer),                    # gözden geçirme aralığı (gün)
    _ts("son_gozden_gecirme"),
    sa.Column("sonraki_gozden_gecirme", sa.String(10)),
    sa.Column("olusturan", sa.String(120), nullable=False),
    _ts("created_at", nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at"),
    sa.Column("surum", sa.Integer, nullable=False, default=1),
    sa.Index("ix_semantic_risk_register_state", "tenant_id", "durum"),
)
INDICATORS = sa.Table(
    "semantic_risk_indicators", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("kod", sa.String(60), nullable=False),
    sa.Column("surum", sa.Integer, nullable=False),
    sa.Column("ad", sa.String(200), nullable=False),
    sa.Column("aciklama", sa.Text),
    sa.Column("kaynak_turu", sa.String(8), nullable=False),         # sql | modul
    sa.Column("kaynak_ref", sa.String(300)),
    sa.Column("birim", sa.String(10), nullable=False),              # gun | yuzde | adet | tl
    sa.Column("yon", sa.String(12), nullable=False),                # artis_kotu | azalis_kotu
    sa.Column("esik_sari", sa.Float),
    sa.Column("esik_kirmizi", sa.Float),
    sa.Column("sahip", sa.String(120)),
    sa.Column("sahip_eposta", sa.String(200)),
    sa.Column("siklik", sa.String(10), nullable=False),             # gunluk | haftalik | aylik
    sa.Column("durum", sa.String(12), nullable=False),              # taslak | yururlukte | arsiv | reddedildi
    sa.Column("notu", sa.Text),
    sa.Column("olusturan", sa.String(120), nullable=False),
    _ts("olusturma", nullable=False),
    sa.Column("onaylayan", sa.String(120)),
    _ts("onay_zamani"),
    sa.UniqueConstraint("tenant_id", "kod", "surum", name="uq_semantic_risk_indicator_version"),
)
VALUES = sa.Table(
    "semantic_risk_indicator_values", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("kod", sa.String(60), nullable=False),
    _ts("olcum_at", nullable=False),
    sa.Column("deger", sa.Float),
    sa.Column("durum", sa.String(12), nullable=False),              # yesil | sari | kirmizi | esik_yok | olculemedi
    sa.Column("veri_son_gunu", sa.String(10)),
    sa.Column("kanit_json", sa.Text),
    sa.Column("esik_json", sa.Text),                                # ölçüm anındaki tanım sürümü ve eşikler
    sa.Column("hata", sa.Text),
    sa.Column("olcen", sa.String(120)),
    sa.Index("ix_semantic_risk_values_kod", "tenant_id", "kod", "olcum_at"),
)
ALERT_STATE = sa.Table(
    "semantic_risk_indicator_alerts", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kod", sa.String(60), primary_key=True),
    sa.Column("durum", sa.String(12), nullable=False),
    _ts("since", nullable=False),                                   # bu duruma geçiş anı
    _ts("notified_at"),                                             # son bildirim (yalnız kırmızı)
)
LINKS = sa.Table(
    "semantic_risk_links", _md,
    sa.Column("risk_id", sa.String(32), primary_key=True),
    sa.Column("gosterge_kod", sa.String(60), primary_key=True),
)
ACTIONS = sa.Table(
    "semantic_risk_actions", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("risk_id", sa.String(32), nullable=False, index=True),
    sa.Column("eylem", sa.Text, nullable=False),
    sa.Column("sahip", sa.String(120)),
    sa.Column("sahip_eposta", sa.String(200)),
    sa.Column("termin", sa.String(10)),
    sa.Column("durum", sa.String(12), nullable=False),              # acik | devam | tamamlandi | iptal
    sa.Column("kanit_ad", sa.String(300)),
    sa.Column("kanit_yolu", sa.String(500)),
    sa.Column("kanit_mime", sa.String(120)),
    sa.Column("notu", sa.Text),
    sa.Column("olusturan", sa.String(120), nullable=False),
    _ts("created_at", nullable=False),
    sa.Column("tamamlayan", sa.String(120)),
    _ts("tamamlanma"),
)
REVIEWS = sa.Table(
    "semantic_risk_reviews", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("risk_id", sa.String(32), nullable=False, index=True),
    _ts("tarih", nullable=False),
    sa.Column("eski_olasilik", sa.Integer),
    sa.Column("eski_etki", sa.Integer),
    sa.Column("yeni_olasilik", sa.Integer),
    sa.Column("yeni_etki", sa.Integer),
    sa.Column("eski_puan", sa.Integer),
    sa.Column("yeni_puan", sa.Integer),
    sa.Column("egilim", sa.String(10)),
    sa.Column("notu", sa.Text),
    sa.Column("tetik_json", sa.Text),                               # gözden geçirmeyi tetikleyen göstergeler/değerler
    sa.Column("gozden_geciren", sa.String(120), nullable=False),
)
COMP_ITEMS = sa.Table(
    "semantic_compliance_items", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("alan", sa.String(12), nullable=False),               # telif | kvkk | vergi | ticaret | is_sagligi | diger
    sa.Column("madde", sa.String(500), nullable=False),
    sa.Column("dayanak", sa.String(500)),
    sa.Column("siklik", sa.String(10), nullable=False),             # tek | aylik | ceyreklik | yillik
    sa.Column("ilk_son_gun", sa.String(10), nullable=False),
    sa.Column("sorumlu", sa.String(120)),
    sa.Column("sorumlu_eposta", sa.String(200)),
    sa.Column("aktif", sa.Boolean, nullable=False, default=True),
    sa.Column("notu", sa.Text),
    sa.Column("olusturan", sa.String(120), nullable=False),
    _ts("created_at", nullable=False),
)
COMP_EVENTS = sa.Table(
    "semantic_compliance_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("item_id", sa.String(32), nullable=False, index=True),
    sa.Column("donem", sa.String(20), nullable=False),
    sa.Column("son_gun", sa.String(10), nullable=False),
    sa.Column("durum", sa.String(10), nullable=False),              # bekliyor | kanit | kapandi
    sa.Column("kanit_ad", sa.String(300)),
    sa.Column("kanit_yolu", sa.String(500)),
    sa.Column("kanit_mime", sa.String(120)),
    sa.Column("kanit_sha256", sa.String(64)),
    sa.Column("yukleyen", sa.String(120)),
    _ts("yukleme"),
    sa.Column("kapatan", sa.String(120)),
    _ts("kapanis"),
    sa.Column("notu", sa.Text),
    sa.UniqueConstraint("item_id", "son_gun", name="uq_semantic_compliance_event"),
)
POLICIES = sa.Table(
    "semantic_risk_policies", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(120), nullable=False),
    sa.Column("sigortaci", sa.String(200)),
    sa.Column("police_no_maskeli", sa.String(40)),
    sa.Column("teminat_json", sa.Text),                             # [{ad, tutar}] kullanıcı girer
    sa.Column("prim", sa.Float),
    sa.Column("bas", sa.String(10)),
    sa.Column("bit", sa.String(10)),
    sa.Column("sorumlu", sa.String(120)),
    sa.Column("sorumlu_eposta", sa.String(200)),
    sa.Column("belge_ad", sa.String(300)),
    sa.Column("belge_yolu", sa.String(500)),
    sa.Column("belge_mime", sa.String(120)),
    sa.Column("notu", sa.Text),                                     # boşluk notu (teminat dışı kalanlar)
    sa.Column("olusturan", sa.String(120), nullable=False),
    _ts("created_at", nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at"),
)
BCP = sa.Table(
    "semantic_risk_bcp", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("surec", sa.String(300), nullable=False),
    sa.Column("kritiklik", sa.Integer),                             # 1–5
    sa.Column("kabul_kesinti_saat", sa.Float),
    sa.Column("veri_kaybi_saat", sa.Float),
    sa.Column("sorumlu", sa.String(120)),
    sa.Column("sorumlu_eposta", sa.String(200)),
    sa.Column("son_tatbikat", sa.String(10)),
    sa.Column("sonraki_tatbikat", sa.String(10)),
    sa.Column("belge_surum", sa.String(60)),
    sa.Column("durum", sa.String(12), nullable=False),              # taslak | onayli | guncellenecek
    sa.Column("notu", sa.Text),
    sa.Column("olusturan", sa.String(120), nullable=False),
    _ts("created_at", nullable=False),
    sa.Column("updated_by", sa.String(120)),
    _ts("updated_at"),
)
REPORTS = sa.Table(
    "semantic_risk_reports", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("donem", sa.String(20), nullable=False),              # 2026-Q3
    sa.Column("metin", sa.Text),
    sa.Column("girdi_json", sa.Text),
    sa.Column("girdi_hash", sa.String(64)),
    sa.Column("durum", sa.String(14), nullable=False),              # hazirlaniyor | taslak | onayli | hata
    sa.Column("kaynak", sa.String(8)),                              # zeki | kural
    sa.Column("kaynak_notu", sa.Text),
    sa.Column("olusturan", sa.String(120), nullable=False),
    _ts("created_at", nullable=False),
    sa.Column("duzenleyen", sa.String(120)),
    _ts("updated_at"),
    sa.Column("onaylayan", sa.String(120)),
    _ts("onay_zamani"),
)
JOBS = sa.Table(
    "semantic_risk_jobs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("tur", sa.String(12), nullable=False),                # oneri | brifing
    sa.Column("durum", sa.String(12), nullable=False),              # calisiyor | bitti | hata
    sa.Column("sonuc_json", sa.Text),
    sa.Column("hata", sa.Text),
    sa.Column("baslatan", sa.String(120), nullable=False),
    _ts("baslangic", nullable=False),
    _ts("bitis"),
)
REMINDERS = sa.Table(
    "semantic_risk_reminders", _md,
    sa.Column("key", sa.String(160), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    _ts("gonderildi", nullable=False),
)

KATEGORILER = {"operasyonel": "Operasyonel (stok, lojistik, üretim)", "finansal": "Finansal (kur, faiz, likidite, alacak)",
               "yasal": "Yasal uyum (telif, KVKK, ticaret, vergi)", "itibar": "İtibar (basın, sosyal medya, yazar)",
               "bt": "Bilgi teknolojisi ve veri"}
RISK_STATES = {"oneri": "Zeki AI önerisi — kabul bekliyor", "acik": "Açık", "izleniyor": "İzleniyor", "kabul": "Kabul edildi",
               "kapandi": "Kapandı", "reddedildi": "Öneri reddedildi"}
LIVE_STATES = ("acik", "izleniyor", "kabul")
TRENDS = {"artiyor": "Artıyor", "sabit": "Sabit", "azaliyor": "Azalıyor"}
SOURCES = {"elle": "Elle girildi", "gosterge": "Gösterge eşiğinden", "denetim": "Finansal denetim bulgusundan"}
ACTION_STATES = {"acik": "Açık", "devam": "Sürüyor", "tamamlandi": "Tamamlandı", "iptal": "İptal"}
IND_STATES = {"taslak": "Onay bekliyor", "yururlukte": "Yürürlükte", "arsiv": "Önceki sürüm", "reddedildi": "Reddedildi"}
VALUE_STATES = {"yesil": "Eşik içinde", "sari": "Sarı eşik aşıldı", "kirmizi": "Kırmızı eşik aşıldı", "esik_yok": "Eşik tanımlı değil",
                "olculemedi": "Ölçülemedi"}
UNITS = {"gun": "gün", "yuzde": "%", "adet": "adet", "tl": "₺"}
DIRECTIONS = {"artis_kotu": "Arttıkça kötü", "azalis_kotu": "Azaldıkça kötü"}
FREQS = {"gunluk": 1, "haftalik": 7, "aylik": 30}
FREQ_LABELS = {"gunluk": "Günlük", "haftalik": "Haftalık", "aylik": "Aylık"}
AREAS = {"telif": "Telif ve sözleşme", "kvkk": "KVKK", "vergi": "Vergi", "ticaret": "Ticaret mevzuatı",
         "is_sagligi": "İş sağlığı ve güvenliği", "diger": "Diğer"}
COMP_FREQS = {"tek": "Bir kez", "aylik": "Aylık", "ceyreklik": "Çeyreklik", "yillik": "Yıllık"}
EVENT_STATES = {"bekliyor": "Bekliyor", "kanit": "Kanıt yüklendi", "kapandi": "Kapandı"}
BCP_STATES = {"taslak": "Taslak", "onayli": "Onaylı", "guncellenecek": "Güncellenecek"}
REPORT_STATES = {"hazirlaniyor": "Hazırlanıyor", "taslak": "Taslak", "onayli": "Onaylandı", "hata": "Hazırlanamadı"}

_lock = threading.Lock()
_ready: set[int] = set()
_active: set[str] = set()


class RiskError(ValueError):
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


# ------------------------------------------------------------------ ayarlar


def _conf(key: str, default: str) -> str:
    try:
        from semantic_bridge import admin as admin_mod
        v = admin_mod.conf(key)
    except Exception:  # noqa: BLE001 — testte admin ayarı yok
        v = ""
    return v if v not in (None, "") else os.environ.get(key, default)


def _conf_float(key: str, default: float) -> float:
    try:
        return float(str(_conf(key, str(default))).replace(",", "."))
    except ValueError:
        return default


def _ints(raw: str, default: list[int]) -> list[int]:
    out = [int(x) for x in re.findall(r"\d+", raw or "")]
    return out or default


def settings() -> dict[str, Any]:
    """Modülün ayarları (ekran > ortam > varsayılan). Ölçülmemiş varsayımlar buradadır, kodda sabit değil."""
    bands = _ints(_conf("RISK_SCORE_BANDS", "5,10,15"), [5, 10, 15])[:3]
    while len(bands) < 3:
        bands.append(bands[-1] + 5)
    return {
        "scoreBands": sorted(bands),                                  # < b0 düşük, < b1 orta, < b2 yüksek, üstü kritik
        "reviewDays": max(1, int(_conf_float("RISK_REVIEW_DAYS", 90))),
        "actionWarnDays": max(0, int(_conf_float("RISK_ACTION_WARN_DAYS", 7))),
        "complianceWarnDays": _ints(_conf("RISK_COMPLIANCE_WARN_DAYS", "14,3"), [14, 3]),
        "policyWarnDays": max(0, int(_conf_float("RISK_POLICY_WARN_DAYS", 60))),
        "remindHours": max(1.0, _conf_float("ALERT_REMIND_HOURS", 24)),
        "fileMaxMb": max(1, int(_conf_float("RISK_FILE_MAX_MB", 50))),
        "horizonMonths": max(1, int(_conf_float("RISK_COMPLIANCE_HORIZON_MONTHS", 12))),
        "criticalImpact": min(5, max(1, int(_conf_float("RISK_CRITICAL_IMPACT", 5)))),
    }


def files_root() -> Path:
    return Path(os.environ.get("RISK_DIR", "/data/nanobaseai/bi/var/risk"))


# ------------------------------------------------------------------ küçük yardımcılar


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


def _j(v: Optional[str], default: Any) -> Any:
    try:
        out = json.loads(v or "")
    except (TypeError, ValueError):
        return default
    return out if isinstance(out, type(default)) else default


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def _uid() -> str:
    return uuid.uuid4().hex


def _text(v: Any, limit: int, label: str = "Metin", required: bool = False) -> Optional[str]:
    s = str(v or "").strip()
    if not s:
        if required:
            raise RiskError(f"{label} girilmeli.")
        return None
    if len(s) > limit:
        raise RiskError(f"{label} {limit} karakteri aşıyor.")
    return s


def _email(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    if not s:
        return None
    if not re.fullmatch(r"[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+", s) or len(s) > 200:
        raise RiskError("E-posta adresi geçerli değil.")
    return s


def _num(v: Any, label: str, *, minimum: Optional[float] = None) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, str):
        s = v.strip().replace(" ", "").replace("₺", "").replace("%", "")
        v = s.replace(".", "").replace(",", ".") if "," in s else (s.replace(".", "") if s.count(".") > 1 else s)
    try:
        n = float(v)
    except (TypeError, ValueError):
        raise RiskError(f"{label} sayı olmalı.") from None
    if not math.isfinite(n) or (minimum is not None and n < minimum):
        raise RiskError(f"{label} geçersiz.")
    return n


def _scale(v: Any, label: str) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise RiskError(f"{label} 1–5 arası olmalı.") from None
    if not 1 <= n <= 5:
        raise RiskError(f"{label} 1–5 arası olmalı.")
    return n


def _day(v: Any, label: str) -> Optional[str]:
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v).strip()[:10]).isoformat()
    except ValueError:
        raise RiskError(f"{label} YYYY-AA-GG biçiminde olmalı.") from None


def _choice(v: Any, allowed: dict[str, str], label: str) -> str:
    s = str(v or "").strip()
    if s not in allowed:
        raise RiskError(f"{label} geçersiz: {s or '(boş)'}.")
    return s


def days_between(a: Optional[str], asof: Optional[date] = None) -> Optional[int]:
    """`a` tarihine kalan gün (geçtiyse eksi)."""
    if not a:
        return None
    try:
        return (date.fromisoformat(a[:10]) - (asof or today())).days
    except ValueError:
        return None


def score(olasilik: Optional[int], etki: Optional[int]) -> Optional[int]:
    return olasilik * etki if olasilik and etki else None


def level(puan: Optional[int], bands: Optional[list[int]] = None) -> Optional[str]:
    """Isı haritası bandı. Sınırlar ayardır (`RISK_SCORE_BANDS`, varsayılan 5,10,15)."""
    if not puan:
        return None
    b = bands or settings()["scoreBands"]
    if puan < b[0]:
        return "dusuk"
    if puan < b[1]:
        return "orta"
    if puan < b[2]:
        return "yuksek"
    return "kritik"


LEVELS = {"dusuk": "Düşük", "orta": "Orta", "yuksek": "Yüksek", "kritik": "Kritik"}


def mask_policy_no(v: Any) -> Optional[str]:
    """Poliçe numarasının yalnız son 4 karakteri saklanır."""
    s = re.sub(r"\s+", "", str(v or ""))
    if not s:
        return None
    if s.startswith("•"):
        return s[:40]
    return "••••" + s[-4:] if len(s) > 4 else "••••"


# ------------------------------------------------------------------ gösterge durumu ve kenar


def state_of(value: Optional[float], yon: str, sari: Optional[float], kirmizi: Optional[float]) -> str:
    """Değerin eşiklere göre durumu. Eşik yoksa «esik_yok»; eşiklerden biri tanımlıysa yalnız o sınanır."""
    if value is None:
        return "olculemedi"
    if sari is None and kirmizi is None:
        return "esik_yok"
    worse = (lambda v, t: v >= t) if yon != "azalis_kotu" else (lambda v, t: v <= t)
    if kirmizi is not None and worse(value, kirmizi):
        return "kirmizi"
    if sari is not None and worse(value, sari):
        return "sari"
    return "yesil"


def edge(prev: Optional[dict[str, Any]], new_state: str, now: datetime, remind: timedelta) -> tuple[dict[str, Any], Optional[str]]:
    """Kenar kuralı. Dönen: (yeni kayıt {durum, since, notified_at}, bildirim türü «yeni» | «hatirlat» | None).

    - Kırmızıya ilk geçiş (önceki kırmızı değil): bir kez «yeni».
    - Kırmızıda kalırken son bildirimin üstünden `remind` geçtiyse bir kez «hatirlat»; dolmadan ikinci bildirim yok.
    - «Ölçülemedi» durumu önceki kırmızıyı bozmaz (okuma hatası riskin geçtiği anlamına gelmez)."""
    if prev and new_state == "olculemedi":
        return dict(prev), None
    if new_state != "kirmizi":
        if prev and prev.get("durum") == new_state:
            return dict(prev), None
        return {"durum": new_state, "since": now, "notified_at": None}, None
    if not prev or prev.get("durum") != "kirmizi":
        return {"durum": "kirmizi", "since": now, "notified_at": now}, "yeni"
    last = _aware(prev.get("notified_at")) or _aware(prev.get("since"))
    if last is None or now - last >= remind:
        return {**prev, "notified_at": now}, "hatirlat"
    return dict(prev), None


# ------------------------------------------------------------------ satır → sözlük


def _risk_out(r: Any, links: list[str] | None = None, bands: Optional[list[int]] = None) -> dict[str, Any]:
    d = dict(r._mapping)
    left = days_between(d["sonraki_gozden_gecirme"])
    return {"id": d["id"], "baslik": d["baslik"], "tanim": d["tanim"], "neden": d["neden"], "sonuc": d["sonuc"],
            "kategori": d["kategori"], "kategoriAdi": KATEGORILER.get(d["kategori"], d["kategori"]),
            "altKategori": d["alt_kategori"], "sahip": d["sahip"], "sahipEposta": d["sahip_eposta"],
            "olasilik": d["olasilik"], "etki": d["etki"], "puan": d["puan"], "seviye": level(d["puan"], bands),
            "egilim": d["egilim"], "durum": d["durum"], "durumAdi": RISK_STATES.get(d["durum"], d["durum"]),
            "kaynak": d["kaynak"], "kaynakAdi": SOURCES.get(d["kaynak"], d["kaynak"]), "kaynakRef": d["kaynak_ref"],
            "gozdenGecirmeGun": d["gozden_gecirme_gun"], "sonGozdenGecirme": _iso(d["son_gozden_gecirme"]),
            "sonrakiGozdenGecirme": d["sonraki_gozden_gecirme"], "gozdenGecirmeKalan": left,
            "olusturan": d["olusturan"], "olusturma": _iso(d["created_at"]), "guncelleyen": d["updated_by"],
            "guncelleme": _iso(d["updated_at"]), "surum": d["surum"], "gostergeler": links or []}


def _action_out(r: Any, asof: Optional[date] = None) -> dict[str, Any]:
    d = dict(r._mapping)
    left = days_between(d["termin"], asof)
    return {"id": d["id"], "riskId": d["risk_id"], "eylem": d["eylem"], "sahip": d["sahip"], "sahipEposta": d["sahip_eposta"],
            "termin": d["termin"], "kalanGun": left, "durum": d["durum"], "durumAdi": ACTION_STATES.get(d["durum"], d["durum"]),
            "gecikti": bool(left is not None and left < 0 and d["durum"] in ("acik", "devam")),
            "kanitAd": d["kanit_ad"], "kanitVar": bool(d["kanit_yolu"]), "not": d["notu"], "olusturan": d["olusturan"],
            "olusturma": _iso(d["created_at"]), "tamamlayan": d["tamamlayan"], "tamamlanma": _iso(d["tamamlanma"])}


def _review_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"id": d["id"], "tarih": _iso(d["tarih"]), "eskiOlasilik": d["eski_olasilik"], "eskiEtki": d["eski_etki"],
            "yeniOlasilik": d["yeni_olasilik"], "yeniEtki": d["yeni_etki"], "eskiPuan": d["eski_puan"], "yeniPuan": d["yeni_puan"],
            "egilim": d["egilim"], "not": d["notu"], "tetik": _j(d["tetik_json"], []), "gozdenGeciren": d["gozden_geciren"]}


def _indicator_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"id": d["id"], "kod": d["kod"], "surum": d["surum"], "ad": d["ad"], "aciklama": d["aciklama"],
            "kaynakTuru": d["kaynak_turu"], "kaynakRef": d["kaynak_ref"], "birim": d["birim"], "birimAdi": UNITS.get(d["birim"], d["birim"]),
            "yon": d["yon"], "yonAdi": DIRECTIONS.get(d["yon"], d["yon"]), "esikSari": d["esik_sari"], "esikKirmizi": d["esik_kirmizi"],
            "sahip": d["sahip"], "sahipEposta": d["sahip_eposta"], "siklik": d["siklik"], "siklikAdi": FREQ_LABELS.get(d["siklik"], d["siklik"]),
            "durum": d["durum"], "durumAdi": IND_STATES.get(d["durum"], d["durum"]), "not": d["notu"], "olusturan": d["olusturan"],
            "olusturma": _iso(d["olusturma"]), "onaylayan": d["onaylayan"], "onayZamani": _iso(d["onay_zamani"])}


def _value_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"olcum": _iso(d["olcum_at"]), "deger": d["deger"], "durum": d["durum"], "durumAdi": VALUE_STATES.get(d["durum"], d["durum"]),
            "veriSonGunu": d["veri_son_gunu"], "kanit": {k: v for k, v in (_j(d["kanit_json"], {}) or {}).items() if k != "_sorgular"},
            "esik": _j(d["esik_json"], {}), "hata": d["hata"],
            "olcen": d["olcen"]}


# ------------------------------------------------------------------ gösterge kütüphanesi ve tanımlar


def seed_library(engine: sa.engine.Engine, tenant: str, library: Iterable[dict[str, Any]]) -> int:
    """Hazır gösterge tanımlarını (yoksa) sürüm 1 olarak yürürlüğe koyar. Eşikler ve sahip BOŞ gelir: sayı uydurulmaz,
    eşiği sahibi önerir, başka biri onaylar. Var olan koda dokunulmaz (kullanıcının sürümü korunur)."""
    added = 0
    with engine.begin() as c:
        have = {r.kod for r in c.execute(sa.select(INDICATORS.c.kod).where(INDICATORS.c.tenant_id == tenant))}
        for spec in library:
            if spec["kod"] in have:
                continue
            c.execute(INDICATORS.insert().values(
                id=_uid(), tenant_id=tenant, kod=spec["kod"], surum=1, ad=spec["ad"], aciklama=spec.get("aciklama"),
                kaynak_turu=spec["kaynak_turu"], kaynak_ref=spec.get("kaynak_ref"), birim=spec["birim"], yon=spec["yon"],
                esik_sari=None, esik_kirmizi=None, sahip=None, sahip_eposta=None, siklik=spec.get("siklik", "gunluk"),
                durum="yururlukte", notu="Hazır tanım; eşik ve sahip girilmedi.", olusturan="sistem", olusturma=_now(),
                onaylayan="sistem", onay_zamani=_now()))
            added += 1
    return added


# ------------------------------------------------------------------ okuma ifadeleri (sorgu bilgisi aynısını gösterir)


def risks_stmt(tenant: str):
    return sa.select(RISKS).where(RISKS.c.tenant_id == tenant)


def risk_stmt(tenant: str, rid: str):
    return sa.select(RISKS).where(RISKS.c.id == rid, RISKS.c.tenant_id == tenant)


def actions_stmt(risk_ids: Optional[list[str]] = None, *, live: bool = False):
    q = sa.select(ACTIONS)
    if risk_ids is not None:
        q = q.where(ACTIONS.c.risk_id.in_(risk_ids or [""]))
    if live:
        q = q.where(ACTIONS.c.durum.in_(("acik", "devam")))
    return q.order_by(ACTIONS.c.created_at)


def links_stmt(risk_ids: Optional[list[str]] = None):
    q = sa.select(LINKS.c.risk_id, LINKS.c.gosterge_kod)
    if risk_ids is not None:
        q = q.where(LINKS.c.risk_id.in_(risk_ids or [""]))
    return q


def reviews_stmt(rid: str):
    return sa.select(REVIEWS).where(REVIEWS.c.risk_id == rid).order_by(REVIEWS.c.tarih.desc())


def indicator_defs_stmt(tenant: str, kod: Optional[str] = None):
    q = sa.select(INDICATORS).where(INDICATORS.c.tenant_id == tenant)
    if kod is None:
        return q.where(INDICATORS.c.durum.in_(("yururlukte", "taslak"))).order_by(INDICATORS.c.kod, INDICATORS.c.surum)
    return q.where(INDICATORS.c.kod == kod).order_by(INDICATORS.c.surum.desc())


def values_stmt(tenant: str, kod: Optional[str] = None):
    q = sa.select(VALUES).where(VALUES.c.tenant_id == tenant)
    if kod is not None:
        q = q.where(VALUES.c.kod == kod)
    return q.order_by(VALUES.c.olcum_at.desc())


def alert_state_stmt(tenant: str):
    return sa.select(ALERT_STATE).where(ALERT_STATE.c.tenant_id == tenant)


def comp_items_stmt(tenant: str):
    return sa.select(COMP_ITEMS).where(COMP_ITEMS.c.tenant_id == tenant).order_by(COMP_ITEMS.c.alan, COMP_ITEMS.c.madde)


def comp_events_stmt(tenant: str, first: Optional[date] = None, last: Optional[date] = None):
    q = sa.select(COMP_EVENTS).where(COMP_EVENTS.c.tenant_id == tenant)
    if first is not None and last is not None:
        q = q.where(sa.or_(sa.and_(COMP_EVENTS.c.son_gun >= first.isoformat(), COMP_EVENTS.c.son_gun <= last.isoformat()),
                           sa.and_(COMP_EVENTS.c.son_gun < first.isoformat(), COMP_EVENTS.c.durum != "kapandi")))
    return q


def policies_stmt(tenant: str):
    return sa.select(POLICIES).where(POLICIES.c.tenant_id == tenant)


def bcp_stmt(tenant: str):
    return sa.select(BCP).where(BCP.c.tenant_id == tenant)


def reports_stmt(tenant: str, rid: Optional[str] = None):
    q = sa.select(REPORTS).where(REPORTS.c.tenant_id == tenant)
    return q.where(REPORTS.c.id == rid) if rid else q.order_by(REPORTS.c.created_at.desc())


def measure_queries(engine: sa.engine.Engine, tenant: str) -> dict[str, dict[str, Any]]:
    """Her göstergenin son ölçümünde çalışan sorgular (kanıtın yanında saklanır; ekrana kanıt olarak gitmez)."""
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for r in c.execute(values_stmt(tenant)):
            if r.kod in out:
                continue
            out[r.kod] = {"olcum": _iso(r.olcum_at), "sorgular": (_j(r.kanit_json, {}) or {}).get("_sorgular") or []}
    return out


def _current(c: Any, tenant: str, kod: str) -> Optional[Any]:
    return c.execute(sa.select(INDICATORS).where(INDICATORS.c.tenant_id == tenant, INDICATORS.c.kod == kod,
                                                 INDICATORS.c.durum == "yururlukte")).first()


def indicators(engine: sa.engine.Engine, tenant: str, library_codes: Optional[set[str]] = None,
               links: Optional[dict[str, list[str]]] = None) -> list[dict[str, Any]]:
    """Yürürlükteki her gösterge: son değer, son 12 değer, bekleyen taslak, bağlı riskler."""
    with engine.connect() as c:
        defs = c.execute(indicator_defs_stmt(tenant)).all()
        vals = c.execute(values_stmt(tenant)).all()
        alerts = {r.kod: r for r in c.execute(alert_state_stmt(tenant))}
        link_rows = c.execute(links_stmt()).all() if links is None else None
    if links is None:
        links = {}
        for lr in link_rows or []:
            links.setdefault(lr.gosterge_kod, []).append(lr.risk_id)
    hist: dict[str, list[Any]] = {}
    for v in vals:
        h = hist.setdefault(v.kod, [])
        if len(h) < 12:
            h.append(v)
    out: dict[str, dict[str, Any]] = {}
    drafts: dict[str, dict[str, Any]] = {}
    for d in defs:
        if d.durum == "yururlukte":
            out[d.kod] = _indicator_out(d)
        else:
            drafts[d.kod] = _indicator_out(d)
    for kod, d in drafts.items():
        if kod not in out:                        # yeni gösterge, ilk sürümü onay bekliyor
            out[kod] = {**d, "yeni": True}
    for kod, item in out.items():
        h = hist.get(kod, [])
        item["son"] = _value_out(h[0]) if h else None
        item["gecmis"] = [_value_out(v) for v in reversed(h)]
        item["taslak"] = drafts.get(kod) if drafts.get(kod, {}).get("id") != item["id"] else None
        a = alerts.get(kod)
        item["kirmiziBaslangic"] = _iso(a.since) if a is not None and a.durum == "kirmizi" else None
        item["riskler"] = links.get(kod, [])
        item["hazir"] = library_codes is None or kod in library_codes
    return sorted(out.values(), key=lambda x: ({"kirmizi": 0, "sari": 1, "olculemedi": 2, "esik_yok": 3, "yesil": 4}
                                               .get((x["son"] or {}).get("durum", "esik_yok"), 5), x["ad"]))


def indicator_values(engine: sa.engine.Engine, tenant: str, kod: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(values_stmt(tenant, kod)).all()
        versions = c.execute(indicator_defs_stmt(tenant, kod)).all()
    if not versions:
        raise RiskError("Gösterge bulunamadı.", 404)
    return {"kod": kod, "items": [_value_out(r) for r in rows], "surumler": [_indicator_out(v) for v in versions]}


def _indicator_fields(body: dict[str, Any], base: Optional[dict[str, Any]]) -> dict[str, Any]:
    b = base or {}
    get = lambda k, d=None: body[k] if k in body else b.get(k, d)  # noqa: E731
    out = {
        "ad": _text(get("ad"), 200, "Gösterge adı", required=True),
        "aciklama": _text(get("aciklama"), 4000, "Açıklama"),
        "birim": _choice(get("birim", "adet"), UNITS, "Birim"),
        "yon": _choice(get("yon", "artis_kotu"), DIRECTIONS, "Yön"),
        "esik_sari": _num(get("esikSari", b.get("esik_sari")), "Sarı eşik"),
        "esik_kirmizi": _num(get("esikKirmizi", b.get("esik_kirmizi")), "Kırmızı eşik"),
        "sahip": _text(get("sahip"), 120, "Sahip"),
        "sahip_eposta": _email(get("sahipEposta", b.get("sahip_eposta"))),
        "siklik": _choice(get("siklik", "gunluk"), FREQ_LABELS, "Sıklık"),
        "notu": _text(get("not", b.get("notu")), 2000, "Not"),
    }
    s, k = out["esik_sari"], out["esik_kirmizi"]
    if s is not None and k is not None:
        if out["yon"] == "artis_kotu" and s > k:
            raise RiskError("Arttıkça kötü göstergede sarı eşik kırmızıdan büyük olamaz.")
        if out["yon"] == "azalis_kotu" and s < k:
            raise RiskError("Azaldıkça kötü göstergede sarı eşik kırmızıdan küçük olamaz.")
    return out


def propose_indicator(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any],
                      library: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Gösterge tanımı ya da eşik değişikliği taslağı (yeni sürüm). Kaynak yalnız hazır hesapçılardan biri olabilir:
    serbest SQL kabul edilmez (her gösterge bağımsız doğrulanmış bir hesapçıdır)."""
    kod = str(body.get("kod") or "").strip()
    if kod not in library:
        raise RiskError("Gösterge kaynağı hazır hesapçılardan biri olmalı.")
    with engine.begin() as c:
        cur = _current(c, tenant, kod)
        if c.execute(sa.select(INDICATORS.c.id).where(INDICATORS.c.tenant_id == tenant, INDICATORS.c.kod == kod,
                                                      INDICATORS.c.durum == "taslak")).first():
            raise RiskError("Bu göstergenin onay bekleyen bir taslağı var; önce onu sonuçlandırın.", 409)
        base = dict(cur._mapping) if cur is not None else {k: v for k, v in library[kod].items()}
        f = _indicator_fields(body, base)
        top = c.execute(sa.select(sa.func.max(INDICATORS.c.surum)).where(INDICATORS.c.tenant_id == tenant, INDICATORS.c.kod == kod)).scalar() or 0
        iid = _uid()
        spec = library[kod]
        c.execute(INDICATORS.insert().values(id=iid, tenant_id=tenant, kod=kod, surum=top + 1, kaynak_turu=spec["kaynak_turu"],
                                             kaynak_ref=spec.get("kaynak_ref"), durum="taslak", olusturan=user,
                                             olusturma=_now(), **f))
        return _indicator_out(c.execute(sa.select(INDICATORS).where(INDICATORS.c.id == iid)).first())


def decide_indicator(engine: sa.engine.Engine, tenant: str, user: str, kod: str, approve: bool, note: Optional[str]) -> dict[str, Any]:
    """Taslağı yürürlüğe alır (önceki sürüm arşive) ya da reddeder. Hazırlayan kendi taslağını onaylayamaz."""
    with engine.begin() as c:
        d = c.execute(sa.select(INDICATORS).where(INDICATORS.c.tenant_id == tenant, INDICATORS.c.kod == kod,
                                                  INDICATORS.c.durum == "taslak")).first()
        if d is None:
            raise RiskError("Onay bekleyen taslak yok.", 404)
        if d.olusturan == user:
            raise RiskError("Taslağı hazırlayan onaylayamaz; başka bir yetkili onaylamalı.", 403)
        if approve:
            c.execute(INDICATORS.update().where(INDICATORS.c.tenant_id == tenant, INDICATORS.c.kod == kod,
                                                INDICATORS.c.durum == "yururlukte").values(durum="arsiv"))
        note_txt = _text(note, 2000, "Not")
        c.execute(INDICATORS.update().where(INDICATORS.c.id == d.id).values(
            durum="yururlukte" if approve else "reddedildi", onaylayan=user, onay_zamani=_now(),
            notu=(d.notu + "\n" if d.notu and note_txt else d.notu or "") + (note_txt or "") or None))
        return _indicator_out(c.execute(sa.select(INDICATORS).where(INDICATORS.c.id == d.id)).first())


def due_indicators(engine: sa.engine.Engine, tenant: str, now: Optional[datetime] = None) -> list[str]:
    """Sıklığı gelmiş yürürlükteki göstergeler (hiç ölçülmemiş olan hemen)."""
    now = now or _now()
    with engine.connect() as c:
        defs = c.execute(sa.select(INDICATORS.c.kod, INDICATORS.c.siklik).where(INDICATORS.c.tenant_id == tenant,
                                                                                INDICATORS.c.durum == "yururlukte")).all()
        last = dict(c.execute(sa.select(VALUES.c.kod, sa.func.max(VALUES.c.olcum_at)).where(VALUES.c.tenant_id == tenant)
                              .group_by(VALUES.c.kod)).all())
    out = []
    for d in defs:
        t = _aware(last.get(d.kod))
        # 1 saat pay: 06:15 zamanlayıcısı bir gün 06:14'te koşarsa göstergeyi bir gün atlamasın.
        if t is None or now - t >= timedelta(days=FREQS.get(d.siklik, 1)) - timedelta(hours=1):
            out.append(d.kod)
    return out


def record_measure(engine: sa.engine.Engine, tenant: str, kod: str, result: dict[str, Any], user: str,
                   now: Optional[datetime] = None, remind: Optional[timedelta] = None) -> tuple[dict[str, Any], Optional[str]]:
    """Ölçüm sonucunu yürürlükteki tanımın eşikleriyle değerlendirip yazar; kenar bildirimi türünü döner."""
    now = now or _now()
    remind = remind or timedelta(hours=settings()["remindHours"])
    with engine.begin() as c:
        d = _current(c, tenant, kod)
        if d is None:
            raise RiskError("Gösterge yürürlükte değil.", 404)
        value = result.get("deger")
        err = result.get("hata")
        st = "olculemedi" if value is None else state_of(float(value), d.yon, d.esik_sari, d.esik_kirmizi)
        c.execute(VALUES.insert().values(
            tenant_id=tenant, kod=kod, olcum_at=now, deger=None if value is None else float(value), durum=st,
            veri_son_gunu=result.get("veri_son_gunu"),
            kanit_json=_dump({**(result.get("kanit") or {}), **({"_sorgular": result["sorgular"]} if result.get("sorgular") else {})}),
            esik_json=_dump({"surum": d.surum, "sari": d.esik_sari, "kirmizi": d.esik_kirmizi, "yon": d.yon}),
            hata=(str(err)[:2000] if err else None), olcen=user))
        prev_row = c.execute(sa.select(ALERT_STATE).where(ALERT_STATE.c.tenant_id == tenant, ALERT_STATE.c.kod == kod)).first()
        prev = dict(prev_row._mapping) if prev_row is not None else None
        new, note = edge(prev, st, now, remind)
        vals = {"durum": new["durum"], "since": new["since"], "notified_at": new.get("notified_at")}
        if prev is None:
            c.execute(ALERT_STATE.insert().values(tenant_id=tenant, kod=kod, **vals))
        else:
            c.execute(ALERT_STATE.update().where(ALERT_STATE.c.tenant_id == tenant, ALERT_STATE.c.kod == kod).values(**vals))
        row = c.execute(sa.select(VALUES).where(VALUES.c.tenant_id == tenant, VALUES.c.kod == kod)
                        .order_by(VALUES.c.id.desc())).first()
    out = _value_out(row)
    out.update({"kod": kod, "ad": d.ad, "birim": d.birim, "sahip": d.sahip, "sahipEposta": d.sahip_eposta})
    return out, note


# ------------------------------------------------------------------ risk kaydı


def _links_map(c: Any, risk_ids: Optional[list[str]] = None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in c.execute(links_stmt(risk_ids)):
        out.setdefault(r.risk_id, []).append(r.gosterge_kod)
    return out


def visible(risk: dict[str, Any], user: str, see_all: bool, action_owners: Iterable[str] = ()) -> bool:
    """Bütün riskleri görme yetkisi yoksa kişi yalnız sahibi, açanı ya da aksiyon sahibi olduğu riski görür."""
    if see_all:
        return True
    u = (user or "").lower()
    return u in {(risk.get("sahip") or "").lower(), (risk.get("olusturan") or "").lower()} or u in {(o or "").lower() for o in action_owners}


def _risk_row(c: Any, tenant: str, rid: str) -> Any:
    r = c.execute(risk_stmt(tenant, rid)).first()
    if r is None:
        raise RiskError("Risk bulunamadı.", 404)
    return r


def _all_risks(c: Any, tenant: str) -> tuple[list[Any], dict[str, list[Any]]]:
    rows = c.execute(risks_stmt(tenant)).all()
    acts: dict[str, list[Any]] = {}
    ids = [r.id for r in rows]
    if ids:
        for a in c.execute(actions_stmt(ids)):
            acts.setdefault(a.risk_id, []).append(a)
    return rows, acts


_RISK_FIELDS = {  # gövde anahtarı → (kolon, dönüştürücü)
    "baslik": ("baslik", lambda v: _text(v, 300, "Başlık", required=True)),
    "tanim": ("tanim", lambda v: _text(v, 8000, "Tanım")),
    "neden": ("neden", lambda v: _text(v, 4000, "Neden")),
    "sonuc": ("sonuc", lambda v: _text(v, 4000, "Sonuç")),
    "kategori": ("kategori", lambda v: _choice(v, KATEGORILER, "Kategori")),
    "altKategori": ("alt_kategori", lambda v: _text(v, 120, "Alt kategori")),
    "sahip": ("sahip", lambda v: _text(v, 120, "Sahip")),
    "sahipEposta": ("sahip_eposta", _email),
    "egilim": ("egilim", lambda v: _choice(v, TRENDS, "Eğilim") if v else None),
    "gozdenGecirmeGun": ("gozden_gecirme_gun", lambda v: int(_num(v, "Gözden geçirme aralığı", minimum=1) or 0) or None),
    "sonrakiGozdenGecirme": ("sonraki_gozden_gecirme", lambda v: _day(v, "Sonraki gözden geçirme")),
}


def _set_links(c: Any, rid: str, codes: Any, known: Optional[set[str]]) -> list[str]:
    if codes is None:
        return sorted(_links_map(c, [rid]).get(rid, []))
    if not isinstance(codes, list):
        raise RiskError("Gösterge listesi geçersiz.")
    clean = sorted({str(x).strip() for x in codes if str(x).strip()})
    bad = [x for x in clean if known is not None and x not in known]
    if bad:
        raise RiskError(f"Bilinmeyen gösterge: {', '.join(bad)}.")
    c.execute(LINKS.delete().where(LINKS.c.risk_id == rid))
    for k in clean:
        c.execute(LINKS.insert().values(risk_id=rid, gosterge_kod=k))
    return clean


def _known_codes(c: Any, tenant: str) -> set[str]:
    return {r.kod for r in c.execute(sa.select(INDICATORS.c.kod).where(INDICATORS.c.tenant_id == tenant).distinct())}


def create_risk(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    cfg = settings()
    vals: dict[str, Any] = {}
    for key, (col, fn) in _RISK_FIELDS.items():
        if key in body:
            vals[col] = fn(body.get(key))
    if not vals.get("baslik"):
        raise RiskError("Başlık girilmeli.")
    vals.setdefault("kategori", _choice(body.get("kategori"), KATEGORILER, "Kategori"))
    o, e = _scale(body.get("olasilik"), "Olasılık"), _scale(body.get("etki"), "Etki")
    days = vals.get("gozden_gecirme_gun") or cfg["reviewDays"]
    rid = _uid()
    now = _now()
    with engine.begin() as c:
        c.execute(RISKS.insert().values(
            id=rid, tenant_id=tenant, olasilik=o, etki=e, puan=score(o, e), durum="acik", kaynak="elle",
            kaynak_ref=_text(body.get("kaynakRef"), 120, "Kaynak"), gozden_gecirme_gun=days,
            sonraki_gozden_gecirme=vals.pop("sonraki_gozden_gecirme", None) or (today() + timedelta(days=days)).isoformat(),
            olusturan=user, created_at=now, surum=1, **{k: v for k, v in vals.items() if k != "gozden_gecirme_gun"}))
        links = _set_links(c, rid, body.get("gostergeler") or [], _known_codes(c, tenant))
        return _risk_out(_risk_row(c, tenant, rid), links)


def update_risk(engine: sa.engine.Engine, tenant: str, user: str, rid: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Tanım alanları, durum ve bağlı göstergeler. Olasılık/etki buradan değil gözden geçirmeyle değişir (iz kalır)."""
    if "olasilik" in body or "etki" in body:
        raise RiskError("Olasılık ve etki gözden geçirme kaydıyla değişir.")
    with engine.begin() as c:
        old = _risk_row(c, tenant, rid)
        vals: dict[str, Any] = {}
        for key, (col, fn) in _RISK_FIELDS.items():
            if key in body:
                vals[col] = fn(body.get(key))
        if "durum" in body:
            st = _choice(body.get("durum"), {k: v for k, v in RISK_STATES.items() if k not in ("oneri", "reddedildi")}, "Durum")
            if old.durum in ("oneri", "reddedildi"):
                raise RiskError("Öneri önce kabul edilmeli.", 409)
            vals["durum"] = st
        diff = {k: {"eski": getattr(old, k), "yeni": v} for k, v in vals.items() if getattr(old, k) != v}
        if vals:
            c.execute(RISKS.update().where(RISKS.c.id == rid).values(updated_by=user, updated_at=_now(),
                                                                      surum=(old.surum or 1) + 1, **vals))
        prev_links = sorted(_links_map(c, [rid]).get(rid, []))
        links = _set_links(c, rid, body.get("gostergeler"), _known_codes(c, tenant))
        if links != prev_links:
            diff["gostergeler"] = {"eski": prev_links, "yeni": links}
        return _risk_out(_risk_row(c, tenant, rid), links), diff


def review_risk(engine: sa.engine.Engine, tenant: str, user: str, rid: str, body: dict[str, Any],
                triggers: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """Gözden geçirme: puan aynı kalabilir; not ve eğilimle iz bırakır, sonraki gözden geçirme tarihini ileri alır.
    «Gözden geçir» kuyruğundaki öğe bu kayıtla düşer."""
    with engine.begin() as c:
        old = _risk_row(c, tenant, rid)
        if old.durum in ("oneri", "reddedildi", "kapandi"):
            raise RiskError("Bu risk gözden geçirilemez (öneri, reddedilmiş ya da kapanmış).", 409)
        o = _scale(body.get("olasilik"), "Olasılık") if body.get("olasilik") not in (None, "") else old.olasilik
        e = _scale(body.get("etki"), "Etki") if body.get("etki") not in (None, "") else old.etki
        if not (o and e):
            raise RiskError("Olasılık ve etki (1–5) girilmeli.")
        trend = _choice(body.get("egilim"), TRENDS, "Eğilim") if body.get("egilim") else old.egilim
        note = _text(body.get("not"), 4000, "Not")
        now = _now()
        days = old.gozden_gecirme_gun or settings()["reviewDays"]
        nxt = _day(body.get("sonrakiGozdenGecirme"), "Sonraki gözden geçirme") or (today() + timedelta(days=days)).isoformat()
        c.execute(REVIEWS.insert().values(id=_uid(), risk_id=rid, tarih=now, eski_olasilik=old.olasilik, eski_etki=old.etki,
                                          yeni_olasilik=o, yeni_etki=e, eski_puan=old.puan, yeni_puan=score(o, e), egilim=trend,
                                          notu=note, tetik_json=_dump(triggers or []), gozden_geciren=user))
        c.execute(RISKS.update().where(RISKS.c.id == rid).values(olasilik=o, etki=e, puan=score(o, e), egilim=trend,
                                                                  son_gozden_gecirme=now, sonraki_gozden_gecirme=nxt,
                                                                  updated_by=user, updated_at=now, surum=(old.surum or 1) + 1))
        return _risk_out(_risk_row(c, tenant, rid), _links_map(c, [rid]).get(rid, []))


def accept_suggestion(engine: sa.engine.Engine, tenant: str, user: str, rid: str, accept: bool, body: dict[str, Any]) -> dict[str, Any]:
    """Zeki AI risk önerisini kabul (puanıyla, insan girer) ya da ret."""
    with engine.begin() as c:
        old = _risk_row(c, tenant, rid)
        if old.durum != "oneri":
            raise RiskError("Bu kayıt öneri değil.", 409)
        vals: dict[str, Any] = {"updated_by": user, "updated_at": _now()}
        if accept:
            o, e = _scale(body.get("olasilik"), "Olasılık"), _scale(body.get("etki"), "Etki")
            if not (o and e):
                raise RiskError("Kabul ederken olasılık ve etkiyi (1–5) siz girin; sistem puanlamaz.")
            for key, (col, fn) in _RISK_FIELDS.items():
                if key in body:
                    vals[col] = fn(body.get(key))
            vals.update(olasilik=o, etki=e, puan=score(o, e), durum="acik")
        else:
            vals["durum"] = "reddedildi"
        c.execute(RISKS.update().where(RISKS.c.id == rid).values(**vals))
        return _risk_out(_risk_row(c, tenant, rid), _links_map(c, [rid]).get(rid, []))


def risk_detail(engine: sa.engine.Engine, tenant: str, rid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _risk_row(c, tenant, rid)
        links = _links_map(c, [rid]).get(rid, [])
        acts = c.execute(actions_stmt([rid])).all()
        revs = c.execute(reviews_stmt(rid)).all()
    out = _risk_out(r, links)
    out["aksiyonlar"] = [_action_out(a) for a in acts]
    out["gozdenGecirmeler"] = [_review_out(v) for v in revs]
    return out


def list_risks(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, *, durum: str = "canli", kategori: str = "",
               q: str = "", sahip: str = "", hucre: str = "") -> dict[str, Any]:
    bands = settings()["scoreBands"]
    with engine.connect() as c:
        rows, acts = _all_risks(c, tenant)
        links = _links_map(c)
    items = []
    qs = q.strip().lower()
    for r in rows:
        d = _risk_out(r, links.get(r.id, []), bands)
        owners = [a.sahip for a in acts.get(r.id, [])]
        if not visible(d, user, see_all, owners):
            continue
        if durum == "canli" and d["durum"] not in LIVE_STATES:
            continue
        if durum not in ("canli", "hepsi") and d["durum"] != durum:
            continue
        if kategori and d["kategori"] != kategori:
            continue
        if sahip and (d["sahip"] or "").lower() != sahip.lower():
            continue
        if hucre:
            try:
                ho, he = (int(x) for x in hucre.split("x"))
            except ValueError:
                raise RiskError("Hücre «olasılıkxetki» biçiminde olmalı.") from None
            if (d["olasilik"], d["etki"]) != (ho, he):
                continue
        if qs and qs not in " ".join(str(d.get(k) or "") for k in ("baslik", "tanim", "altKategori", "sahip")).lower():
            continue
        live = [a for a in acts.get(r.id, []) if a.durum in ("acik", "devam")]
        d["acikAksiyon"] = len(live)
        d["gecikenAksiyon"] = sum(1 for a in live if (days_between(a.termin) or 0) < 0)
        items.append(d)
    items.sort(key=lambda x: (-(x["puan"] or 0), x["baslik"].lower()))
    return {"items": items, "total": len(items)}


# ------------------------------------------------------------------ aksiyonlar


def add_action(engine: sa.engine.Engine, tenant: str, user: str, rid: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        _risk_row(c, tenant, rid)
        aid = _uid()
        c.execute(ACTIONS.insert().values(id=aid, risk_id=rid, eylem=_text(body.get("eylem"), 4000, "Aksiyon", required=True),
                                          sahip=_text(body.get("sahip"), 120, "Sahip"), sahip_eposta=_email(body.get("sahipEposta")),
                                          termin=_day(body.get("termin"), "Termin"), durum="acik",
                                          notu=_text(body.get("not"), 4000, "Not"), olusturan=user, created_at=_now()))
        return _action_out(c.execute(sa.select(ACTIONS).where(ACTIONS.c.id == aid)).first())


def action_scope(engine: sa.engine.Engine, tenant: str, aid: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """(aksiyon, risk) — uçtaki sahiplik denetimi için."""
    with engine.connect() as c:
        a = c.execute(sa.select(ACTIONS).where(ACTIONS.c.id == aid)).first()
        if a is None:
            raise RiskError("Aksiyon bulunamadı.", 404)
        r = _risk_row(c, tenant, a.risk_id)
    return _action_out(a), _risk_out(r)


def update_action(engine: sa.engine.Engine, tenant: str, user: str, aid: str, body: dict[str, Any], *,
                  full: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Durum ve not herkese (sahiplik uçta denetlenir); eylem metni, sahip ve termin yalnız `full` (risk yazma yetkisi)."""
    with engine.begin() as c:
        a = c.execute(sa.select(ACTIONS).where(ACTIONS.c.id == aid)).first()
        if a is None:
            raise RiskError("Aksiyon bulunamadı.", 404)
        _risk_row(c, tenant, a.risk_id)
        vals: dict[str, Any] = {}
        if "durum" in body:
            st = _choice(body.get("durum"), ACTION_STATES, "Aksiyon durumu")
            vals["durum"] = st
            if st == "tamamlandi" and a.durum != "tamamlandi":
                vals.update(tamamlayan=user, tamamlanma=_now())
            elif st != "tamamlandi":
                vals.update(tamamlayan=None, tamamlanma=None)
        if "not" in body:
            vals["notu"] = _text(body.get("not"), 4000, "Not")
        editable = {"eylem": ("eylem", lambda v: _text(v, 4000, "Aksiyon", required=True)),
                    "sahip": ("sahip", lambda v: _text(v, 120, "Sahip")), "sahipEposta": ("sahip_eposta", _email),
                    "termin": ("termin", lambda v: _day(v, "Termin"))}
        for key, (col, fn) in editable.items():
            if key in body:
                if not full:
                    raise RiskError("Aksiyonun metnini, sahibini ve terminini risk yazma yetkisi olan değiştirir.", 403)
                vals[col] = fn(body.get(key))
        diff = {k: {"eski": getattr(a, k), "yeni": v} for k, v in vals.items() if k in ("durum", "eylem", "sahip", "termin") and getattr(a, k) != v}
        if vals:
            c.execute(ACTIONS.update().where(ACTIONS.c.id == aid).values(**vals))
        return _action_out(c.execute(sa.select(ACTIONS).where(ACTIONS.c.id == aid)).first()), diff


# ------------------------------------------------------------------ dosyalar

_MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "xls": "application/vnd.ms-excel", "csv": "text/csv", "txt": "text/plain",
         "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "doc": "application/msword",
         "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
_MAGIC = {"pdf": (b"%PDF",), "xlsx": (b"PK",), "docx": (b"PK",), "png": (b"\x89PNG",), "jpg": (b"\xff\xd8",),
          "jpeg": (b"\xff\xd8",), "xls": (b"\xd0\xcf\x11\xe0",), "doc": (b"\xd0\xcf\x11\xe0",)}


def save_file(folder: str, filename: str, data: bytes) -> tuple[str, str, str, str]:
    """(ad, yol, mime, sha256). Uzantı ve içerik imzası denetlenir; boyut sınırı ayardır."""
    max_mb = settings()["fileMaxMb"]
    name = re.sub(r"[\\/\x00-\x1f]", "_", (filename or "").strip())[:200]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    mime = _MIME.get(ext)
    if not mime:
        raise RiskError("Dosya PDF, Word, Excel, CSV, metin ya da görsel (JPG/PNG) olmalı.")
    if not data:
        raise RiskError("Dosya boş.")
    if len(data) > max_mb * 1024 * 1024:
        raise RiskError(f"Dosya {max_mb} MB sınırını aşıyor.", 413)
    magic = _MAGIC.get(ext)
    if magic and not any(data.startswith(m) for m in magic):
        raise RiskError("Dosyanın içeriği uzantısıyla uyuşmuyor.")
    path = files_root() / folder / f"{_uid()}.{ext}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as e:
        log.error("risk dosyası yazılamadı (%s): %s", path, e)
        raise RiskError("Dosya sunucuya kaydedilemedi; yöneticiye bildirin.", 503) from e
    return name, str(path), mime, hashlib.sha256(data).hexdigest()


def _replace_file(old_path: Optional[str]) -> None:
    if old_path:
        Path(old_path).unlink(missing_ok=True)


def attach_action_evidence(engine: sa.engine.Engine, tenant: str, aid: str, filename: str, data: bytes) -> dict[str, Any]:
    with engine.connect() as c:
        a = c.execute(sa.select(ACTIONS).where(ACTIONS.c.id == aid)).first()
        if a is None:
            raise RiskError("Aksiyon bulunamadı.", 404)
        _risk_row(c, tenant, a.risk_id)
    name, path, mime, _ = save_file(f"aksiyon/{aid}", filename, data)
    with engine.begin() as c:
        c.execute(ACTIONS.update().where(ACTIONS.c.id == aid).values(kanit_ad=name, kanit_yolu=path, kanit_mime=mime))
        out = _action_out(c.execute(sa.select(ACTIONS).where(ACTIONS.c.id == aid)).first())
    _replace_file(a.kanit_yolu if a.kanit_yolu != path else None)
    return out


def file_of(table: sa.Table, engine: sa.engine.Engine, tenant: str, oid: str, prefix: str) -> tuple[str, str, str]:
    """Kaydın dosyası (yol, ad, mime). `prefix` kolon ön eki: kanit | belge."""
    with engine.connect() as c:
        r = c.execute(sa.select(table).where(table.c.id == oid)).first()
        if r is None:
            raise RiskError("Kayıt bulunamadı.", 404)
        m = r._mapping
        if "tenant_id" in m and m["tenant_id"] != tenant:
            raise RiskError("Kayıt bulunamadı.", 404)
        if "risk_id" in m:
            _risk_row(c, tenant, m["risk_id"])
    path = m.get(f"{prefix}_yolu")
    if not path or not Path(path).exists():
        raise RiskError("Dosya bulunamadı.", 404)
    return path, m.get(f"{prefix}_ad") or "dosya", m.get(f"{prefix}_mime") or "application/octet-stream"


# ------------------------------------------------------------------ uyum


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    last = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


STEP = {"tek": 0, "aylik": 1, "ceyreklik": 3, "yillik": 12}


def occurrences(first: date, siklik: str, until: date) -> list[date]:
    """İlk son günden başlayıp `until`'e kadar olan son günler (tek seferlikse yalnız ilki)."""
    step = STEP.get(siklik, 0)
    if step == 0:
        return [first]
    out, i = [], 0
    while True:
        d = _add_months(first, step * i)
        if d > until:
            break
        out.append(d)
        i += 1
    return out or [first]


def _period(d: date, siklik: str) -> str:
    if siklik == "yillik":
        return str(d.year)
    if siklik == "ceyreklik":
        return f"{d.year}-Ç{(d.month - 1) // 3 + 1}"
    if siklik == "aylik":
        return f"{d.year}-{d.month:02d}"
    return d.isoformat()


def generate_events(engine: sa.engine.Engine, tenant: str, horizon_months: Optional[int] = None) -> int:
    """Etkin her yükümlülük için ufuk içindeki dönemleri (yoksa) açar. Var olan olaya dokunmaz."""
    until = _add_months(today(), horizon_months or settings()["horizonMonths"])
    added = 0
    with engine.begin() as c:
        items = c.execute(sa.select(COMP_ITEMS).where(COMP_ITEMS.c.tenant_id == tenant, COMP_ITEMS.c.aktif.is_(True))).all()
        for it in items:
            have = {r.son_gun for r in c.execute(sa.select(COMP_EVENTS.c.son_gun).where(COMP_EVENTS.c.item_id == it.id))}
            for d in occurrences(date.fromisoformat(it.ilk_son_gun), it.siklik, until):
                if d.isoformat() in have:
                    continue
                c.execute(COMP_EVENTS.insert().values(id=_uid(), tenant_id=tenant, item_id=it.id, donem=_period(d, it.siklik),
                                                      son_gun=d.isoformat(), durum="bekliyor"))
                added += 1
    return added


def _item_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"id": d["id"], "alan": d["alan"], "alanAdi": AREAS.get(d["alan"], d["alan"]), "madde": d["madde"], "dayanak": d["dayanak"],
            "siklik": d["siklik"], "siklikAdi": COMP_FREQS.get(d["siklik"], d["siklik"]), "ilkSonGun": d["ilk_son_gun"],
            "sorumlu": d["sorumlu"], "sorumluEposta": d["sorumlu_eposta"], "aktif": bool(d["aktif"]), "not": d["notu"],
            "olusturan": d["olusturan"], "olusturma": _iso(d["created_at"])}


def _event_out(r: Any, item: Optional[dict[str, Any]] = None, asof: Optional[date] = None) -> dict[str, Any]:
    d = dict(r._mapping)
    left = days_between(d["son_gun"], asof)
    out = {"id": d["id"], "itemId": d["item_id"], "donem": d["donem"], "sonGun": d["son_gun"], "kalanGun": left,
           "durum": d["durum"], "durumAdi": EVENT_STATES.get(d["durum"], d["durum"]),
           "gecikti": bool(left is not None and left < 0 and d["durum"] != "kapandi"),
           "kanitAd": d["kanit_ad"], "kanitVar": bool(d["kanit_yolu"]), "yukleyen": d["yukleyen"], "yukleme": _iso(d["yukleme"]),
           "kapatan": d["kapatan"], "kapanis": _iso(d["kapanis"]), "not": d["notu"]}
    if item:
        out.update({"alan": item["alan"], "alanAdi": item["alanAdi"], "madde": item["madde"], "dayanak": item["dayanak"],
                    "sorumlu": item["sorumlu"]})
    return out


def compliance_items(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(comp_items_stmt(tenant)).all()
        ev = c.execute(comp_events_stmt(tenant)).all()
    by: dict[str, list[Any]] = {}
    for e in ev:
        by.setdefault(e.item_id, []).append(e)
    items = []
    for r in rows:
        d = _item_out(r)
        es = sorted(by.get(r.id, []), key=lambda e: e.son_gun)
        nxt = next((e for e in es if e.durum != "kapandi"), None)
        d["siradaki"] = _event_out(nxt) if nxt is not None else None
        d["kapanan"] = sum(1 for e in es if e.durum == "kapandi")
        d["geciken"] = sum(1 for e in es if e.durum != "kapandi" and (days_between(e.son_gun) or 0) < 0)
        items.append(d)
    return {"items": items, "alanlar": AREAS, "sikliklar": COMP_FREQS}


def save_item(engine: sa.engine.Engine, tenant: str, user: str, iid: Optional[str], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    fields = {"alan": ("alan", lambda v: _choice(v, AREAS, "Alan")),
              "madde": ("madde", lambda v: _text(v, 500, "Yükümlülük", required=True)),
              "dayanak": ("dayanak", lambda v: _text(v, 500, "Dayanak")),
              "siklik": ("siklik", lambda v: _choice(v, COMP_FREQS, "Sıklık")),
              "ilkSonGun": ("ilk_son_gun", lambda v: _day(v, "İlk son gün")),
              "sorumlu": ("sorumlu", lambda v: _text(v, 120, "Sorumlu")),
              "sorumluEposta": ("sorumlu_eposta", _email),
              "aktif": ("aktif", lambda v: bool(v)),
              "not": ("notu", lambda v: _text(v, 4000, "Not"))}
    vals = {col: fn(body.get(k)) for k, (col, fn) in fields.items() if k in body}
    with engine.begin() as c:
        if iid is None:
            for req in ("alan", "madde", "siklik", "ilk_son_gun"):
                if not vals.get(req):
                    raise RiskError("Alan, yükümlülük, sıklık ve ilk son gün girilmeli.")
            iid = _uid()
            c.execute(COMP_ITEMS.insert().values(id=iid, tenant_id=tenant, olusturan=user, created_at=_now(),
                                                 aktif=vals.pop("aktif", True), **vals))
            diff = {"yeni": True}
        else:
            old = c.execute(sa.select(COMP_ITEMS).where(COMP_ITEMS.c.id == iid, COMP_ITEMS.c.tenant_id == tenant)).first()
            if old is None:
                raise RiskError("Yükümlülük bulunamadı.", 404)
            if "ilk_son_gun" in vals and not vals["ilk_son_gun"]:
                raise RiskError("İlk son gün boş olamaz.")
            diff = {k: {"eski": getattr(old, k), "yeni": v} for k, v in vals.items() if getattr(old, k) != v}
            if vals:
                c.execute(COMP_ITEMS.update().where(COMP_ITEMS.c.id == iid).values(**vals))
            if "siklik" in diff or "ilk_son_gun" in diff:
                # Takvim değişti: kanıtı ya da kapanışı olmayan açık dönemler yeniden kurulur.
                c.execute(COMP_EVENTS.delete().where(COMP_EVENTS.c.item_id == iid, COMP_EVENTS.c.durum == "bekliyor",
                                                     COMP_EVENTS.c.kanit_yolu.is_(None)))
        row = c.execute(sa.select(COMP_ITEMS).where(COMP_ITEMS.c.id == iid)).first()
    generate_events(engine, tenant)
    return _item_out(row), diff


def item_area(engine: sa.engine.Engine, tenant: str, iid: str) -> str:
    with engine.connect() as c:
        r = c.execute(sa.select(COMP_ITEMS.c.alan).where(COMP_ITEMS.c.id == iid, COMP_ITEMS.c.tenant_id == tenant)).first()
    if r is None:
        raise RiskError("Yükümlülük bulunamadı.", 404)
    return r.alan


def event_area(engine: sa.engine.Engine, tenant: str, eid: str) -> str:
    with engine.connect() as c:
        r = c.execute(sa.select(COMP_ITEMS.c.alan).select_from(COMP_EVENTS.join(COMP_ITEMS, COMP_ITEMS.c.id == COMP_EVENTS.c.item_id))
                      .where(COMP_EVENTS.c.id == eid, COMP_EVENTS.c.tenant_id == tenant)).first()
    if r is None:
        raise RiskError("Dönem bulunamadı.", 404)
    return r.alan


def calendar(engine: sa.engine.Engine, tenant: str, ay: str = "") -> dict[str, Any]:
    """Ayın yükümlülükleri (+ o güne kadar kapanmamış eski dönemler «gecikti»)."""
    try:
        first = date.fromisoformat(f"{ay}-01") if ay else today().replace(day=1)
    except ValueError:
        raise RiskError("Ay YYYY-AA biçiminde olmalı.") from None
    last = _add_months(first, 1) - timedelta(days=1)
    with engine.connect() as c:
        items = {r.id: _item_out(r) for r in c.execute(comp_items_stmt(tenant))}
        rows = c.execute(comp_events_stmt(tenant, first, last)).all()
    out = [_event_out(r, items.get(r.item_id)) for r in rows if r.item_id in items]
    out.sort(key=lambda e: (e["sonGun"], e.get("madde") or ""))
    return {"ay": first.strftime("%Y-%m"), "items": out, "bugun": today().isoformat()}


def attach_event_evidence(engine: sa.engine.Engine, tenant: str, user: str, eid: str, filename: str, data: bytes, note: str = "") -> dict[str, Any]:
    with engine.connect() as c:
        e = c.execute(sa.select(COMP_EVENTS).where(COMP_EVENTS.c.id == eid, COMP_EVENTS.c.tenant_id == tenant)).first()
    if e is None:
        raise RiskError("Dönem bulunamadı.", 404)
    if e.durum == "kapandi":
        raise RiskError("Kapanmış döneme kanıt eklenmez.", 409)
    name, path, mime, digest = save_file(f"uyum/{e.item_id}", filename, data)
    with engine.begin() as c:
        c.execute(COMP_EVENTS.update().where(COMP_EVENTS.c.id == eid).values(
            kanit_ad=name, kanit_yolu=path, kanit_mime=mime, kanit_sha256=digest, yukleyen=user, yukleme=_now(), durum="kanit",
            notu=_text(note, 2000, "Not") or e.notu))
        out = _event_out(c.execute(sa.select(COMP_EVENTS).where(COMP_EVENTS.c.id == eid)).first())
    _replace_file(e.kanit_yolu)
    return out


def close_event(engine: sa.engine.Engine, tenant: str, user: str, eid: str, note: str = "") -> dict[str, Any]:
    """Dönemi kapatır. Kanıt yüklenmemişse kapanış notu zorunludur (kanıtsız kapanış açıklamasız kalmaz)."""
    with engine.begin() as c:
        e = c.execute(sa.select(COMP_EVENTS).where(COMP_EVENTS.c.id == eid, COMP_EVENTS.c.tenant_id == tenant)).first()
        if e is None:
            raise RiskError("Dönem bulunamadı.", 404)
        if e.durum == "kapandi":
            raise RiskError("Dönem zaten kapalı.", 409)
        n = _text(note, 2000, "Not")
        if not e.kanit_yolu and not n:
            raise RiskError("Kanıt dosyası yoksa kapanış için açıklama yazın.")
        c.execute(COMP_EVENTS.update().where(COMP_EVENTS.c.id == eid).values(durum="kapandi", kapatan=user, kapanis=_now(),
                                                                              notu=n or e.notu))
        return _event_out(c.execute(sa.select(COMP_EVENTS).where(COMP_EVENTS.c.id == eid)).first())


# ------------------------------------------------------------------ sigorta ve BCP


def _policy_out(r: Any, warn: int) -> dict[str, Any]:
    d = dict(r._mapping)
    left = days_between(d["bit"])
    return {"id": d["id"], "tur": d["tur"], "sigortaci": d["sigortaci"], "policeNo": d["police_no_maskeli"],
            "teminat": _j(d["teminat_json"], []), "prim": d["prim"], "bas": d["bas"], "bit": d["bit"], "kalanGun": left,
            "yaklasti": bool(left is not None and 0 <= left <= warn), "bitti": bool(left is not None and left < 0),
            "sorumlu": d["sorumlu"], "sorumluEposta": d["sorumlu_eposta"], "belgeAd": d["belge_ad"], "belgeVar": bool(d["belge_yolu"]),
            "not": d["notu"], "olusturan": d["olusturan"], "guncelleyen": d["updated_by"], "guncelleme": _iso(d["updated_at"])}


def _bcp_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    left = days_between(d["sonraki_tatbikat"])
    return {"id": d["id"], "surec": d["surec"], "kritiklik": d["kritiklik"], "kabulKesintiSaat": d["kabul_kesinti_saat"],
            "veriKaybiSaat": d["veri_kaybi_saat"], "sorumlu": d["sorumlu"], "sorumluEposta": d["sorumlu_eposta"],
            "sonTatbikat": d["son_tatbikat"], "sonrakiTatbikat": d["sonraki_tatbikat"], "tatbikatKalan": left,
            "tatbikatGecikti": bool(left is not None and left < 0), "belgeSurum": d["belge_surum"], "durum": d["durum"],
            "durumAdi": BCP_STATES.get(d["durum"], d["durum"]), "not": d["notu"], "olusturan": d["olusturan"],
            "guncelleyen": d["updated_by"], "guncelleme": _iso(d["updated_at"])}


def _teminat(v: Any) -> Optional[str]:
    if v in (None, ""):
        return None
    if not isinstance(v, list):
        raise RiskError("Teminat listesi geçersiz.")
    out = []
    for x in v:
        if not isinstance(x, dict):
            raise RiskError("Teminat satırı geçersiz.")
        ad = _text(x.get("ad"), 200, "Teminat adı")
        if ad:
            out.append({"ad": ad, "tutar": _num(x.get("tutar"), "Teminat tutarı", minimum=0)})
    return _dump(out)


def policies(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    warn = settings()["policyWarnDays"]
    with engine.connect() as c:
        rows = c.execute(policies_stmt(tenant)).all()
    items = [_policy_out(r, warn) for r in rows]
    items.sort(key=lambda p: (p["bit"] is None, p["bit"] or "", p["tur"]))
    return {"items": items, "uyariGun": warn}


def save_policy(engine: sa.engine.Engine, tenant: str, user: str, pid: Optional[str], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    fields = {"tur": ("tur", lambda v: _text(v, 120, "Poliçe türü", required=True)),
              "sigortaci": ("sigortaci", lambda v: _text(v, 200, "Sigortacı")),
              "policeNo": ("police_no_maskeli", mask_policy_no),
              "teminat": ("teminat_json", _teminat),
              "prim": ("prim", lambda v: _num(v, "Prim", minimum=0)),
              "bas": ("bas", lambda v: _day(v, "Başlangıç")), "bit": ("bit", lambda v: _day(v, "Bitiş")),
              "sorumlu": ("sorumlu", lambda v: _text(v, 120, "Sorumlu")), "sorumluEposta": ("sorumlu_eposta", _email),
              "not": ("notu", lambda v: _text(v, 4000, "Not"))}
    vals = {col: fn(body.get(k)) for k, (col, fn) in fields.items() if k in body}
    if vals.get("bas") and vals.get("bit") and vals["bit"] < vals["bas"]:
        raise RiskError("Bitiş başlangıçtan önce olamaz.")
    with engine.begin() as c:
        if pid is None:
            if not vals.get("tur"):
                raise RiskError("Poliçe türü girilmeli.")
            pid = _uid()
            c.execute(POLICIES.insert().values(id=pid, tenant_id=tenant, olusturan=user, created_at=_now(), **vals))
            diff: dict[str, Any] = {"yeni": True}
        else:
            old = c.execute(sa.select(POLICIES).where(POLICIES.c.id == pid, POLICIES.c.tenant_id == tenant)).first()
            if old is None:
                raise RiskError("Poliçe bulunamadı.", 404)
            diff = {k: {"eski": getattr(old, k), "yeni": v} for k, v in vals.items() if getattr(old, k) != v}
            if vals:
                c.execute(POLICIES.update().where(POLICIES.c.id == pid).values(updated_by=user, updated_at=_now(), **vals))
        return _policy_out(c.execute(sa.select(POLICIES).where(POLICIES.c.id == pid)).first(), settings()["policyWarnDays"]), diff


def attach_policy_document(engine: sa.engine.Engine, tenant: str, pid: str, filename: str, data: bytes) -> dict[str, Any]:
    with engine.connect() as c:
        old = c.execute(sa.select(POLICIES).where(POLICIES.c.id == pid, POLICIES.c.tenant_id == tenant)).first()
    if old is None:
        raise RiskError("Poliçe bulunamadı.", 404)
    name, path, mime, _ = save_file(f"police/{pid}", filename, data)
    with engine.begin() as c:
        c.execute(POLICIES.update().where(POLICIES.c.id == pid).values(belge_ad=name, belge_yolu=path, belge_mime=mime))
        out = _policy_out(c.execute(sa.select(POLICIES).where(POLICIES.c.id == pid)).first(), settings()["policyWarnDays"])
    _replace_file(old.belge_yolu)
    return out


def delete_row(engine: sa.engine.Engine, table: sa.Table, tenant: str, oid: str, label: str, file_col: Optional[str] = None) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(table).where(table.c.id == oid, table.c.tenant_id == tenant)).first()
        if r is None:
            raise RiskError(f"{label} bulunamadı.", 404)
        c.execute(table.delete().where(table.c.id == oid))
    if file_col:
        _replace_file(r._mapping.get(file_col))
    return dict(r._mapping)


def bcp(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(bcp_stmt(tenant)).all()
    items = [_bcp_out(r) for r in rows]
    items.sort(key=lambda b: (-(b["kritiklik"] or 0), b["surec"]))
    return {"items": items, "durumlar": BCP_STATES}


def save_bcp(engine: sa.engine.Engine, tenant: str, user: str, bid: Optional[str], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    fields = {"surec": ("surec", lambda v: _text(v, 300, "Süreç", required=True)),
              "kritiklik": ("kritiklik", lambda v: _scale(v, "Kritiklik")),
              "kabulKesintiSaat": ("kabul_kesinti_saat", lambda v: _num(v, "Kabul edilebilir kesinti", minimum=0)),
              "veriKaybiSaat": ("veri_kaybi_saat", lambda v: _num(v, "Kabul edilebilir veri kaybı", minimum=0)),
              "sorumlu": ("sorumlu", lambda v: _text(v, 120, "Sorumlu")), "sorumluEposta": ("sorumlu_eposta", _email),
              "sonTatbikat": ("son_tatbikat", lambda v: _day(v, "Son tatbikat")),
              "sonrakiTatbikat": ("sonraki_tatbikat", lambda v: _day(v, "Sonraki tatbikat")),
              "belgeSurum": ("belge_surum", lambda v: _text(v, 60, "Belge sürümü")),
              "durum": ("durum", lambda v: _choice(v, BCP_STATES, "Durum")),
              "not": ("notu", lambda v: _text(v, 4000, "Not"))}
    vals = {col: fn(body.get(k)) for k, (col, fn) in fields.items() if k in body}
    with engine.begin() as c:
        if bid is None:
            if not vals.get("surec"):
                raise RiskError("Süreç adı girilmeli.")
            bid = _uid()
            c.execute(BCP.insert().values(id=bid, tenant_id=tenant, olusturan=user, created_at=_now(),
                                          durum=vals.pop("durum", "taslak"), **vals))
            diff: dict[str, Any] = {"yeni": True}
        else:
            old = c.execute(sa.select(BCP).where(BCP.c.id == bid, BCP.c.tenant_id == tenant)).first()
            if old is None:
                raise RiskError("Süreç bulunamadı.", 404)
            diff = {k: {"eski": getattr(old, k), "yeni": v} for k, v in vals.items() if getattr(old, k) != v}
            if vals:
                c.execute(BCP.update().where(BCP.c.id == bid).values(updated_by=user, updated_at=_now(), **vals))
        return _bcp_out(c.execute(sa.select(BCP).where(BCP.c.id == bid)).first()), diff


# ------------------------------------------------------------------ özet ve kuyruk


def review_queue(risks: list[dict[str, Any]], ind: dict[str, dict[str, Any]], asof: Optional[date] = None) -> list[dict[str, Any]]:
    """Gözden geçirilmesi gereken riskler: bağlı göstergesi kırmızıya döndükten sonra gözden geçirilmemiş, gözden
    geçirme tarihi gelmiş ya da sahibi/puanı olmayan canlı riskler. Kuyruk kaydı tutulmaz; gözden geçirme düşürür."""
    out = []
    for r in risks:
        if r["durum"] not in LIVE_STATES:
            continue
        reasons = []
        last = r["sonGozdenGecirme"]
        for kod in r["gostergeler"]:
            g = ind.get(kod)
            since = g and g.get("kirmiziBaslangic")
            if since and (last is None or datetime.fromisoformat(last) < datetime.fromisoformat(since)):
                son = g.get("son") or {}
                reasons.append({"tur": "gosterge", "kod": kod, "ad": g["ad"], "deger": son.get("deger"), "birim": g["birim"],
                                "since": since})
        left = days_between(r["sonrakiGozdenGecirme"], asof)
        if left is not None and left <= 0:
            reasons.append({"tur": "tarih", "gun": -left})
        if not r["sahip"]:
            reasons.append({"tur": "sahipsiz"})
        if not r["puan"]:
            reasons.append({"tur": "puansiz"})
        if reasons:
            out.append({"risk": {k: r[k] for k in ("id", "baslik", "kategori", "kategoriAdi", "sahip", "olasilik", "etki", "puan",
                                                   "seviye", "sonGozdenGecirme")}, "nedenler": reasons})
    out.sort(key=lambda x: (0 if any(n["tur"] == "gosterge" for n in x["nedenler"]) else 1, -(x["risk"]["puan"] or 0)))
    return out


def summary(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, ind_list: list[dict[str, Any]]) -> dict[str, Any]:
    cfg = settings()
    listing = list_risks(engine, tenant, user, see_all, durum="hepsi")["items"]
    live = [r for r in listing if r["durum"] in LIVE_STATES]
    grid = [[{"olasilik": o, "etki": e, "puan": o * e, "seviye": level(o * e, cfg["scoreBands"]), "sayi": 0, "riskler": []}
             for e in range(1, 6)] for o in range(1, 6)]
    unscored = 0
    for r in live:
        if r["olasilik"] and r["etki"]:
            cell = grid[r["olasilik"] - 1][r["etki"] - 1]
            cell["sayi"] += 1
            cell["riskler"].append({"id": r["id"], "baslik": r["baslik"]})
        else:
            unscored += 1
    ind = {g["kod"]: g for g in ind_list}
    visible_ids = {r["id"] for r in live}
    with engine.connect() as c:
        acts = c.execute(actions_stmt(live=True)).all()
    overdue, soon = [], []
    titles = {r["id"]: r["baslik"] for r in listing}
    for a in acts:
        if a.risk_id not in visible_ids:        # aksiyon sahibi riski zaten görür (visible)
            continue
        d = _action_out(a)
        d["riskBaslik"] = titles.get(a.risk_id)
        if d["gecikti"]:
            overdue.append(d)
        elif d["kalanGun"] is not None and d["kalanGun"] <= cfg["actionWarnDays"]:
            soon.append(d)
    overdue.sort(key=lambda a: a["kalanGun"] or 0)
    soon.sort(key=lambda a: a["kalanGun"] or 0)
    red = [{"kod": g["kod"], "ad": g["ad"], "deger": (g["son"] or {}).get("deger"), "birim": g["birim"], "riskler": g["riskler"],
            "since": g["kirmiziBaslangic"]} for g in ind_list if (g["son"] or {}).get("durum") == "kirmizi"]
    cal = calendar(engine, tenant)
    top = sorted(live, key=lambda r: -(r["puan"] or 0))[:10]
    return {"isiHaritasi": grid, "puansiz": unscored, "bantlar": cfg["scoreBands"], "seviyeler": LEVELS,
            "kuyruk": review_queue(live, ind), "gecikenAksiyon": overdue, "yaklasanAksiyon": soon, "kirmiziGosterge": red,
            "uyumBuAy": cal["items"], "ilk10": top, "oneriSayisi": sum(1 for r in listing if r["durum"] == "oneri"),
            "sayilar": {"canli": len(live), "kritik": sum(1 for r in live if r["seviye"] == "kritik"),
                        "gosterge": len(ind_list), "kirmizi": len(red),
                        "esiksiz": sum(1 for g in ind_list if (g["son"] or {}).get("durum") == "esik_yok")},
            "tumunuGorur": see_all}


# ------------------------------------------------------------------ Zeki AI: sınıflama, öneri, brifing

_NUM_RX = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> set[str]:
    """Metindeki sayılar, binlik/ondalık ayıracı sadeleşmiş hâlde (1.234,5 → 1234,5 → «1234.5»)."""
    out = set()
    for m in _NUM_RX.findall(text or ""):
        s = m
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3):
            s = s.replace(".", "")
        try:
            n = float(s)
        except ValueError:
            continue
        out.add(f"{n:.2f}".rstrip("0").rstrip("."))
    return out


def foreign_numbers(text: str, facts: Any) -> set[str]:
    """Metinde geçip girdide (olgularda) olmayan sayılar, sadeleşmiş yazımla («7500000»). Küçük sayılar (≤ 31: tarih
    günü, çeyrek, sıra) serbest. Denetim: `zeki_text` (tek sayı denetçisi)."""
    from semantic_bridge import zeki_text as Z

    extra = set()
    for tok in Z.unsupported(text or "", _dump(facts), free_upto=31):
        for n in numbers_in(tok):
            try:
                if float(n) <= 31:
                    continue
            except ValueError:
                pass
            extra.add(n)
    return extra


def classify(text: str, choose: Optional[Callable[[str, list[str]], Any]], min_prob: float = 0.70,
             min_margin: float = 0.30) -> Optional[dict[str, Any]]:
    """Risk kategorisi: kapalı küme seçimi (tek token + olasılık). Emin değilse öneri «emin değil» işaretiyle döner."""
    if choose is None or not (text or "").strip():
        return None
    labels = list(KATEGORILER.values())
    res = choose("Aşağıdaki kurumsal riskin kategorisi hangisi?\n\nRisk: " + text.strip()[:2000], labels)
    if res is None or res.choice is None:
        return None
    kod = next(k for k, v in KATEGORILER.items() if v == res.choice)
    return {"kategori": kod, "kategoriAdi": res.choice, "olasilik": res.probability, "marj": res.margin,
            "emin": bool(res.confident(min_prob, min_margin))}


def suggestion_facts(g: dict[str, Any]) -> dict[str, Any]:
    son = g.get("son") or {}
    return {"gosterge": g["ad"], "aciklama": g.get("aciklama"), "deger": son.get("deger"), "birim": UNITS.get(g["birim"], g["birim"]),
            "durum": VALUE_STATES.get(son.get("durum"), son.get("durum")), "veriSonGunu": son.get("veriSonGunu"),
            "esikSari": g.get("esikSari"), "esikKirmizi": g.get("esikKirmizi")}


def rule_suggestion(facts: dict[str, Any]) -> dict[str, Any]:
    v = facts.get("deger")
    val = "okunamadı" if v is None else f"{_fmt(v)} {facts['birim']}"
    return {"baslik": f"{facts['gosterge']}: eşik aşıldı",
            "tanim": f"«{facts['gosterge']}» göstergesi {val} ({facts['durum']}). Değer {facts.get('veriSonGunu') or 'son okunan'} "
                     f"tarihli veriden. Risk sahibi nedenini ve etkisini değerlendirmeli.",
            "neden": None, "sonuc": None}


def _fmt(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = f"{f:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s[:-3] if s.endswith(",00") else s


def _json_from(raw: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return {}
    try:
        v = json.loads(m.group(0))
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def draft_suggestion(facts: dict[str, Any], chat: Optional[Callable[[list[dict[str, str]]], str]]) -> tuple[dict[str, Any], str, Optional[str]]:
    """(taslak, kaynak «zeki»|«kural», not). Model metninde girdide olmayan bir sayı varsa kural metnine düşer."""
    if chat is None:
        return rule_suggestion(facts), "kural", "Zeki AI bu kurulumda tanımlı değil."
    msg = [{"role": "system", "content": "Bir yayınevinin risk koordinatörüne yardım ediyorsun. Yalnız verilen olgulara dayan, "
                                         "yeni sayı yazma, hukuki hüküm verme («uyumsuz», «ceza» deme). Türkçe, kısa. "
                                         "Yalnız JSON döndür: {\"baslik\": ..., \"tanim\": ..., \"neden\": ..., \"sonuc\": ...}"},
           {"role": "user", "content": "Eşiği aşan gösterge için risk kaydı taslağı yaz. Olgular:\n" + _dump(facts)}]
    try:
        raw = chat(msg)
    except Exception as e:  # noqa: BLE001
        return rule_suggestion(facts), "kural", f"Zeki AI yanıt vermedi: {str(e)[:160]}"
    d = _json_from(raw)
    draft = {k: (str(d.get(k)).strip()[:4000] if d.get(k) else None) for k in ("baslik", "tanim", "neden", "sonuc")}
    if not draft["baslik"]:
        return rule_suggestion(facts), "kural", "Zeki AI yanıtı okunamadı."
    extra = foreign_numbers(" ".join(v for v in draft.values() if v), facts)
    if extra:
        return rule_suggestion(facts), "kural", f"Zeki AI metninde girdide olmayan sayı vardı ({', '.join(sorted(extra))}); kural metni kullanıldı."
    draft["baslik"] = draft["baslik"][:300]
    return draft, "zeki", None


def create_suggestion(engine: sa.engine.Engine, tenant: str, user: str, g: dict[str, Any], draft: dict[str, Any],
                      kategori: Optional[dict[str, Any]]) -> dict[str, Any]:
    rid = _uid()
    now = _now()
    days = settings()["reviewDays"]
    with engine.begin() as c:
        c.execute(RISKS.insert().values(
            id=rid, tenant_id=tenant, baslik=draft["baslik"], tanim=draft.get("tanim"), neden=draft.get("neden"),
            sonuc=draft.get("sonuc"), kategori=(kategori or {}).get("kategori") or "operasyonel",
            alt_kategori=None if (kategori or {}).get("emin") else "Kategori emin değil — kontrol edin",
            sahip=g.get("sahip"), sahip_eposta=g.get("sahipEposta"), durum="oneri", kaynak="gosterge", kaynak_ref=g["kod"],
            gozden_gecirme_gun=days, sonraki_gozden_gecirme=(today() + timedelta(days=days)).isoformat(),
            olusturan=user, created_at=now, surum=1))
        c.execute(LINKS.insert().values(risk_id=rid, gosterge_kod=g["kod"]))
        return _risk_out(_risk_row(c, tenant, rid), [g["kod"]])


def suggestion_targets(engine: sa.engine.Engine, tenant: str, ind_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Eşiği aşan (sarı/kırmızı) ve bağlı canlı riski ya da bekleyen önerisi olmayan göstergeler."""
    with engine.connect() as c:
        rows = c.execute(sa.select(RISKS.c.id, RISKS.c.durum).where(RISKS.c.tenant_id == tenant)).all()
        links = _links_map(c)
    st = {r.id: r.durum for r in rows}
    covered = {k for rid, ks in links.items() if st.get(rid) in LIVE_STATES + ("oneri",) for k in ks}
    return [g for g in ind_list if (g.get("son") or {}).get("durum") in ("sari", "kirmizi") and g["kod"] not in covered]


def report_facts(sm: dict[str, Any], ind_list: list[dict[str, Any]], donem: str) -> dict[str, Any]:
    """Brifingin bütün sayıları buradan gelir; model yalnız bunları kullanabilir."""
    return {
        "donem": donem,
        "riskSayilari": sm["sayilar"],
        "ilk10": [{"baslik": r["baslik"], "kategori": r["kategoriAdi"], "olasilik": r["olasilik"], "etki": r["etki"],
                   "puan": r["puan"], "egilim": TRENDS.get(r["egilim"] or "", None), "sahip": r["sahip"]} for r in sm["ilk10"]],
        "kirmiziGostergeler": [{"ad": g["ad"], "deger": g["deger"], "birim": UNITS.get(g["birim"], g["birim"])} for g in sm["kirmiziGosterge"]],
        "gostergeler": [{"ad": g["ad"], "deger": (g["son"] or {}).get("deger"), "birim": UNITS.get(g["birim"], g["birim"]),
                         "durum": VALUE_STATES.get((g["son"] or {}).get("durum"), None), "veriSonGunu": (g["son"] or {}).get("veriSonGunu")}
                        for g in ind_list],
        "gecikenAksiyon": [{"eylem": a["eylem"][:200], "sahip": a["sahip"], "termin": a["termin"], "risk": a.get("riskBaslik")}
                           for a in sm["gecikenAksiyon"]],
        "gozdenGecirKuyrugu": len(sm["kuyruk"]),
        "uyum": [{"madde": e.get("madde"), "alan": e.get("alanAdi"), "sonGun": e["sonGun"], "durum": e["durumAdi"],
                  "gecikti": e["gecikti"]} for e in sm["uyumBuAy"]],
    }


def rule_report(f: dict[str, Any]) -> str:
    s = f["riskSayilari"]
    lines = [f"# Risk brifingi — {f['donem']}", "", "## Genel durum",
             f"Canlı risk: {s['canli']} (kritik bantta {s['kritik']}). Gösterge: {s['gosterge']}, kırmızıda {s['kirmizi']}, "
             f"eşiği tanımlanmamış {s['esiksiz']}. Gözden geçirme bekleyen risk: {f['gozdenGecirKuyrugu']}.", "",
             "## Öncelikli riskler"]
    lines += [f"- {r['baslik']} ({r['kategori']}; olasılık {r['olasilik'] or '—'} × etki {r['etki'] or '—'} = {r['puan'] or '—'}; "
              f"sahibi {r['sahip'] or 'atanmadı'})" for r in f["ilk10"]] or ["- Kayıtlı risk yok."]
    lines += ["", "## Kırmızı göstergeler"]
    lines += [f"- {g['ad']}: {_fmt(g['deger'])} {g['birim']}" for g in f["kirmiziGostergeler"]] or ["- Kırmızı gösterge yok."]
    lines += ["", "## Geciken aksiyonlar"]
    lines += [f"- {a['eylem']} (sahibi {a['sahip'] or '—'}, termin {a['termin'] or '—'})" for a in f["gecikenAksiyon"]] or ["- Geciken aksiyon yok."]
    lines += ["", "## Uyum takvimi (bu ay)"]
    lines += [f"- {e['madde']} — {e['alan']}, son gün {e['sonGun']}: {e['durum']}{' (gecikti)' if e['gecikti'] else ''}"
              for e in f["uyum"]] or ["- Bu ay yükümlülük yok."]
    lines += ["", "Göstergeler inceleme adayıdır; bu belge hukuki ya da denetim görüşü değildir."]
    return "\n".join(lines)


def draft_report_text(f: dict[str, Any], chat: Optional[Callable[[list[dict[str, str]]], str]]) -> tuple[str, str, Optional[str]]:
    if chat is None:
        return rule_report(f), "kural", "Zeki AI bu kurulumda tanımlı değil; kural metni hazırlandı."
    msg = [{"role": "system", "content": "Bir yayınevinin yönetim kurulu için çeyreklik risk brifingi taslağı yazıyorsun. "
                                         "Yalnız verilen JSON olgularını kullan; olgularda olmayan hiçbir sayı yazma, tahmin yapma. "
                                         "Hukuki hüküm verme. Türkçe, 1-2 sayfa. Başlıklar '# ' ve '## ' ile, maddeler '- ' ile."},
           {"role": "user", "content": "Olgular:\n" + _dump(f)}]
    try:
        text = (chat(msg) or "").strip()
    except Exception as e:  # noqa: BLE001
        return rule_report(f), "kural", f"Zeki AI yanıt vermedi: {str(e)[:160]}; kural metni hazırlandı."
    if not text:
        return rule_report(f), "kural", "Zeki AI boş yanıt verdi; kural metni hazırlandı."
    extra = foreign_numbers(text, f)
    if extra:
        return rule_report(f), "kural", f"Zeki AI metninde olgularda olmayan sayı vardı ({', '.join(sorted(extra))}); kural metni hazırlandı."
    return text, "zeki", None


def quarter_of(d: date) -> str:
    return f"{d.year}-Ç{(d.month - 1) // 3 + 1}"


def _report_out(r: Any, with_text: bool = True) -> dict[str, Any]:
    d = dict(r._mapping)
    out = {"id": d["id"], "donem": d["donem"], "durum": d["durum"], "durumAdi": REPORT_STATES.get(d["durum"], d["durum"]),
           "kaynak": d["kaynak"], "kaynakNotu": d["kaynak_notu"], "girdiHash": d["girdi_hash"], "olusturan": d["olusturan"],
           "olusturma": _iso(d["created_at"]), "duzenleyen": d["duzenleyen"], "guncelleme": _iso(d["updated_at"]),
           "onaylayan": d["onaylayan"], "onayZamani": _iso(d["onay_zamani"])}
    if with_text:
        out["metin"] = d["metin"]
        out["girdi"] = _j(d["girdi_json"], {})
    return out


def reports(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(reports_stmt(tenant)).all()
    return {"items": [_report_out(r, False) for r in rows]}


def report(engine: sa.engine.Engine, tenant: str, rid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(reports_stmt(tenant, rid)).first()
    if r is None:
        raise RiskError("Rapor bulunamadı.", 404)
    return _report_out(r)


def start_report(engine: sa.engine.Engine, tenant: str, user: str, donem: str, facts: dict[str, Any]) -> str:
    rid = _uid()
    raw = _dump(facts)
    with engine.begin() as c:
        c.execute(REPORTS.insert().values(id=rid, tenant_id=tenant, donem=donem, girdi_json=raw,
                                          girdi_hash=hashlib.sha256(raw.encode()).hexdigest(), durum="hazirlaniyor",
                                          olusturan=user, created_at=_now()))
    return rid


def finish_report(engine: sa.engine.Engine, rid: str, text: Optional[str], source: Optional[str], note: Optional[str], error: bool = False) -> None:
    with engine.begin() as c:
        c.execute(REPORTS.update().where(REPORTS.c.id == rid).values(metin=text, kaynak=source, kaynak_notu=note,
                                                                      durum="hata" if error else "taslak", updated_at=_now()))


def edit_report(engine: sa.engine.Engine, tenant: str, user: str, rid: str, text: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(REPORTS).where(REPORTS.c.id == rid, REPORTS.c.tenant_id == tenant)).first()
        if r is None:
            raise RiskError("Rapor bulunamadı.", 404)
        if r.durum != "taslak":
            raise RiskError("Yalnız taslak düzenlenir.", 409)
        c.execute(REPORTS.update().where(REPORTS.c.id == rid).values(metin=_text(text, 200_000, "Metin", required=True),
                                                                      duzenleyen=user, updated_at=_now()))
    return report(engine, tenant, rid)


def approve_report(engine: sa.engine.Engine, tenant: str, user: str, rid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(REPORTS).where(REPORTS.c.id == rid, REPORTS.c.tenant_id == tenant)).first()
        if r is None:
            raise RiskError("Rapor bulunamadı.", 404)
        if r.durum != "taslak":
            raise RiskError("Yalnız taslak onaylanır.", 409)
        if r.olusturan == user:
            raise RiskError("Taslağı hazırlatan onaylayamaz; başka bir yetkili onaylamalı.", 403)
        c.execute(REPORTS.update().where(REPORTS.c.id == rid).values(durum="onayli", onaylayan=user, onay_zamani=_now()))
    return report(engine, tenant, rid)


# ------------------------------------------------------------------ arka plan işleri


def start_job(engine: sa.engine.Engine, tenant: str, user: str, kind: str, work: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Aynı türden aynı anda tek iş."""
    jid = _uid()
    with engine.begin() as c:
        running = [r.id for r in c.execute(sa.select(JOBS.c.id).where(JOBS.c.tenant_id == tenant, JOBS.c.tur == kind,
                                                                      JOBS.c.durum == "calisiyor"))]
        if any(i in _active for i in running):
            raise RiskError("Bu iş zaten sürüyor; bitmesini bekleyin.", 409)
        c.execute(JOBS.insert().values(id=jid, tenant_id=tenant, tur=kind, durum="calisiyor", baslatan=user, baslangic=_now()))
    _active.add(jid)

    def run() -> None:
        try:
            res = work()
            with engine.begin() as c:
                c.execute(JOBS.update().where(JOBS.c.id == jid).values(durum="bitti", sonuc_json=_dump(res), bitis=_now()))
        except Exception as e:  # noqa: BLE001
            log.exception("risk işi %s (%s) hata verdi", jid, kind)
            msg = str(e) if isinstance(e, RiskError) else f"İş tamamlanamadı: {str(e)[:300]}"
            with engine.begin() as c:
                c.execute(JOBS.update().where(JOBS.c.id == jid).values(durum="hata", hata=msg, bitis=_now()))
        finally:
            _active.discard(jid)

    threading.Thread(target=run, name=f"risk-{kind}-{jid[:6]}", daemon=True).start()
    return job(engine, tenant, jid)


def job(engine: sa.engine.Engine, tenant: str, jid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(JOBS).where(JOBS.c.id == jid, JOBS.c.tenant_id == tenant)).first()
    if r is None:
        raise RiskError("İş bulunamadı.", 404)
    d = dict(r._mapping)
    st, err = d["durum"], d["hata"]
    if st == "calisiyor" and jid not in _active:
        st, err = "hata", "İş yarıda kaldı (hizmet yeniden başladı); yeniden başlatın."
    return {"id": jid, "tur": d["tur"], "durum": st, "sonuc": _j(d["sonuc_json"], {}), "hata": err, "baslatan": d["baslatan"],
            "baslangic": _iso(d["baslangic"]), "bitis": _iso(d["bitis"])}


# ------------------------------------------------------------------ hatırlatmalar (zamanlayıcı)


def due_reminders(engine: sa.engine.Engine, tenant: str, cfg: Optional[dict[str, Any]] = None,
                  asof: Optional[date] = None) -> list[dict[str, Any]]:
    """Gönderilmemiş hatırlatmalar: aksiyon termini (N gün kala ve geçince), gözden geçirme tarihi, uyum son günü
    (14 ve 3 gün kala, geçince), poliçe bitişi (60 gün kala), BCP tatbikatı gecikmesi. Her biri bir kez gider."""
    cfg = cfg or settings()
    asof = asof or today()
    items: list[dict[str, Any]] = []
    with engine.connect() as c:
        sent = {r.key for r in c.execute(sa.select(REMINDERS.c.key).where(REMINDERS.c.tenant_id == tenant))}
        risks = {r.id: r for r in c.execute(sa.select(RISKS).where(RISKS.c.tenant_id == tenant))}
        acts = c.execute(sa.select(ACTIONS).where(ACTIONS.c.durum.in_(("acik", "devam")))).all()
        comp_items = {r.id: r for r in c.execute(sa.select(COMP_ITEMS).where(COMP_ITEMS.c.tenant_id == tenant, COMP_ITEMS.c.aktif.is_(True)))}
        events = c.execute(sa.select(COMP_EVENTS).where(COMP_EVENTS.c.tenant_id == tenant, COMP_EVENTS.c.durum != "kapandi")).all()
        pols = c.execute(sa.select(POLICIES).where(POLICIES.c.tenant_id == tenant)).all()
        bcps = c.execute(sa.select(BCP).where(BCP.c.tenant_id == tenant)).all()

    def add(key: str, kind: str, text: str, to: Optional[str], owner: Optional[str]) -> None:
        if key not in sent:
            items.append({"key": key, "tur": kind, "metin": text, "eposta": to, "sahip": owner})

    for a in acts:
        r = risks.get(a.risk_id)
        if r is None or r.durum not in LIVE_STATES:
            continue
        left = days_between(a.termin, asof)
        if left is None:
            continue
        if left < 0:
            add(f"aksiyon-gecti:{a.id}:{a.termin}", "aksiyon", f"Aksiyon termini geçti ({-left} gün): {a.eylem[:160]} — risk «{r.baslik}»",
                a.sahip_eposta or r.sahip_eposta, a.sahip or r.sahip)
        elif left <= cfg["actionWarnDays"]:
            add(f"aksiyon-yakin:{a.id}:{a.termin}", "aksiyon", f"Aksiyon termini {left} gün sonra ({a.termin}): {a.eylem[:160]} — risk «{r.baslik}»",
                a.sahip_eposta or r.sahip_eposta, a.sahip or r.sahip)
    for r in risks.values():
        if r.durum not in LIVE_STATES:
            continue
        left = days_between(r.sonraki_gozden_gecirme, asof)
        if left is not None and left <= 0:
            add(f"gozden-gecir:{r.id}:{r.sonraki_gozden_gecirme}", "gozden_gecirme",
                f"Gözden geçirme tarihi geldi ({r.sonraki_gozden_gecirme}): «{r.baslik}»", r.sahip_eposta, r.sahip)
    warn = sorted(set(cfg["complianceWarnDays"]), reverse=True)
    for e in events:
        it = comp_items.get(e.item_id)
        if it is None:
            continue
        left = days_between(e.son_gun, asof)
        if left is None:
            continue
        if left < 0:
            add(f"uyum-gecti:{e.id}", "uyum", f"Uyum son günü geçti ({e.son_gun}): {it.madde[:160]} ({AREAS.get(it.alan)})",
                it.sorumlu_eposta, it.sorumlu)
            continue
        for w in warn:  # en dar pencere tek bildirim
            if left <= w and not any(left <= w2 for w2 in warn if w2 < w):
                add(f"uyum-{w}:{e.id}", "uyum", f"Uyum son günü {left} gün sonra ({e.son_gun}): {it.madde[:160]} ({AREAS.get(it.alan)})",
                    it.sorumlu_eposta, it.sorumlu)
    for p in pols:
        left = days_between(p.bit, asof)
        if left is not None and 0 <= left <= cfg["policyWarnDays"]:
            add(f"police:{p.id}:{p.bit}", "police", f"Poliçe {left} gün sonra bitiyor ({p.bit}): {p.tur}"
                + (f" — {p.sigortaci}" if p.sigortaci else ""), p.sorumlu_eposta, p.sorumlu)
    for b in bcps:
        left = days_between(b.sonraki_tatbikat, asof)
        if left is not None and left < 0:
            add(f"bcp:{b.id}:{b.sonraki_tatbikat}", "bcp", f"İş sürekliliği tatbikatı gecikti ({b.sonraki_tatbikat}): {b.surec}",
                b.sorumlu_eposta, b.sorumlu)
    return items


def mark_sent(engine: sa.engine.Engine, tenant: str, keys: Iterable[str]) -> None:
    now = _now()
    with engine.begin() as c:
        for k in keys:
            if not c.execute(sa.select(REMINDERS.c.key).where(REMINDERS.c.key == k)).first():
                c.execute(REMINDERS.insert().values(key=k, tenant_id=tenant, gonderildi=now))


def indicator_alert_lines(events: list[dict[str, Any]], risks_by_kod: dict[str, list[dict[str, Any]]]) -> list[str]:
    out = []
    for ev in events:
        rs = risks_by_kod.get(ev["kod"], [])
        tag = "Kırmızıya döndü" if ev["bildirim"] == "yeni" else "Hâlâ kırmızı"
        val = "—" if ev["deger"] is None else f"{_fmt(ev['deger'])} {UNITS.get(ev['birim'], ev['birim'])}"
        out.append(f"{tag}: {ev['ad']} = {val}" + (f" — bağlı risk: {', '.join(r['baslik'] for r in rs)}" if rs else " — bağlı risk yok"))
    return out
