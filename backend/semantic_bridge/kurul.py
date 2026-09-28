"""DYK Danışma ve yönetim kurulu: gösterge kataloğu ve dönem değerleri, bölüm yorumu, toplantı, gündem, karar, aksiyon,
kurul paketi (derle → gözden geçir → dondur → PDF → dağıtım kaydı) ve kurul üyeleri.

**İlkeler (analiz §8, §12):**
- **Rakamı model üretmez.** Göstergeler diğer modüllerin onaylı çıktılarından (`kurul_sources`) okunur; burada yeniden
  hesap yoktur. Zeki AI yalnız yorum/özet/tutanak taslağı yazar; taslaktaki her sayı girdideki olgularda olmalı, olmayan
  sayı içeren taslak **kaydedilmez** (`foreign_numbers`, M47 ile aynı denetim).
- **Gri kural:** sağlayıcısı olmayan ya da kaynağı hazır olmayan gösterge `kaynak_yok`: sayı yok, renk yok. Sıfır ya da
  örnek rakam yazılmaz.
- **Renk deterministik:** göstergenin kendi eşiği varsa o (arttıkça/azaldıkça kötü); yoksa kaynak modülün kendi kuralıyla
  verdiği renk (bütçe durumu, sistem durumu tonu); ikisi de yoksa «eşik yok».
- **Dondurulan paket değişmez:** içerik ve PDF donma anında yazılır, sha256'larıyla saklanır; kaynak değer sonradan
  değişse de paket aynı kalır. Düzeltme yeni sürümdür (yeni derleme).
- **Dış gönderim yok:** dağıtım yalnız kayıttır (kime, hangi kanal, kim, ne zaman); AD'siz üyeye PDF'i insan iletir.
  Portal Logo'ya ve CRM'e yazmaz. Tablolar `semantic_kurul_*` («board» adı Panolar'ındır).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import kurul_sources as S

log = logging.getLogger("semantic.kurul")
TZ = ZoneInfo("Europe/Istanbul")

_md = sa.MetaData()
_ready: set[int] = set()
_lock = threading.Lock()
_active_jobs: set[str] = set()


def _ts(name: str, **kw: Any) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), **kw)


INDICATORS = sa.Table(
    "semantic_kurul_indicators", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kod", sa.String(60), primary_key=True),
    sa.Column("bolum", sa.String(30), nullable=False),
    sa.Column("ad", sa.String(200), nullable=False),
    sa.Column("aciklama", sa.Text),
    sa.Column("saglayici", sa.String(30)),
    sa.Column("birim", sa.String(10), nullable=False),
    sa.Column("yon", sa.String(20), nullable=False),
    sa.Column("esik_sari", sa.Float),
    sa.Column("esik_kirmizi", sa.Float),
    sa.Column("hedef_kaynagi", sa.String(200)),
    sa.Column("sahip", sa.String(120)),
    sa.Column("sahip_eposta", sa.String(200)),
    sa.Column("sira", sa.Integer, nullable=False, default=0),
    sa.Column("aktif", sa.Boolean, nullable=False, default=True),
    sa.Column("surum", sa.Integer, nullable=False, default=1),
    sa.Column("guncelleyen", sa.String(120)),
    _ts("guncelleme"),
)

VALUES = sa.Table(
    "semantic_kurul_values", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kod", sa.String(60), nullable=False),
    sa.Column("donem", sa.String(7), nullable=False),          # YYYY-MM
    _ts("olcum_at", nullable=False),
    sa.Column("deger", sa.Float),
    sa.Column("hedef", sa.Float),
    sa.Column("onceki", sa.Float),
    sa.Column("onceki_etiket", sa.String(200)),
    sa.Column("renk", sa.String(12)),                          # yesil | sari | kirmizi | esik_yok | None
    sa.Column("renk_kaynagi", sa.String(12)),                  # esik | kaynak | None
    sa.Column("durum", sa.String(12), nullable=False),         # ok | kaynak_yok | hata
    sa.Column("veri_son_gunu", sa.String(10)),
    sa.Column("kaynak", sa.String(120)),
    sa.Column("ekran", sa.String(200)),
    sa.Column("not_", sa.Text),
    sa.Column("ayrinti_json", sa.Text),
    sa.Column("onceki_renk", sa.String(12)),
    _ts("renk_degisti_at"),
    sa.UniqueConstraint("tenant_id", "kod", "donem", name="uq_kurul_value"),
)

COMMENTS = sa.Table(
    "semantic_kurul_comments", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kod", sa.String(60), nullable=False),
    sa.Column("donem", sa.String(7), nullable=False),
    sa.Column("metin", sa.Text),
    sa.Column("durum", sa.String(14), nullable=False),         # hazirlaniyor | taslak | onayli | hata
    sa.Column("kaynak", sa.String(10), nullable=False),        # insan | zeki
    sa.Column("yazan", sa.String(120), nullable=False),
    _ts("yazildi_at", nullable=False),
    sa.Column("onaylayan", sa.String(120)),
    _ts("onaylandi_at"),
    sa.Column("llm_job_id", sa.String(40)),
    sa.Column("hata", sa.Text),
)

MEETINGS = sa.Table(
    "semantic_kurul_meetings", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(10), nullable=False),           # yonetim | danisma
    sa.Column("baslik", sa.String(200), nullable=False),
    sa.Column("tarih", sa.String(10), nullable=False),         # YYYY-MM-DD
    sa.Column("saat", sa.String(5)),
    sa.Column("yer", sa.String(200)),
    sa.Column("durum", sa.String(12), nullable=False),         # planlandi | yapildi | iptal
    sa.Column("katilimcilar_json", sa.Text),
    sa.Column("notlar", sa.Text),                              # sekreterin serbest notu (tutanak taslağının girdisi)
    sa.Column("olusturan", sa.String(120), nullable=False),
    _ts("olusturma", nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    _ts("guncelleme"),
)

AGENDA = sa.Table(
    "semantic_kurul_agenda", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("meeting_id", sa.String(40), nullable=False, index=True),
    sa.Column("sira", sa.Integer, nullable=False),
    sa.Column("baslik", sa.String(300), nullable=False),
    sa.Column("tur", sa.String(8), nullable=False),            # karar | bilgi
    sa.Column("sunan", sa.String(120)),
    sa.Column("sure_dk", sa.Integer),
    sa.Column("ek_ref", sa.String(300)),
)

DECISIONS = sa.Table(
    "semantic_kurul_decisions", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("meeting_id", sa.String(40), nullable=False, index=True),
    sa.Column("gundem_sira", sa.Integer),
    sa.Column("metin", sa.Text, nullable=False),
    sa.Column("oy_ozeti", sa.String(300)),
    sa.Column("yazan", sa.String(120), nullable=False),
    _ts("tarih", nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    _ts("guncelleme"),
)

ACTIONS = sa.Table(
    "semantic_kurul_actions", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("decision_id", sa.String(40), nullable=False, index=True),
    sa.Column("meeting_id", sa.String(40), nullable=False),
    sa.Column("eylem", sa.Text, nullable=False),
    sa.Column("sahip", sa.String(120)),                        # portal hesabı (AD sAMAccountName, küçük harf)
    sa.Column("sahip_eposta", sa.String(200)),
    sa.Column("termin", sa.String(10)),
    sa.Column("durum", sa.String(12), nullable=False),         # acik | tamamlandi | iptal (gecikme hesaplanır)
    sa.Column("son_not", sa.Text),
    sa.Column("olusturan", sa.String(120), nullable=False),
    _ts("olusturma", nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    _ts("guncelleme"),
    _ts("tamamlanma"),
)

PACKAGES = sa.Table(
    "semantic_kurul_packages", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("meeting_id", sa.String(40), nullable=False, index=True),
    sa.Column("surum", sa.Integer, nullable=False),
    sa.Column("durum", sa.String(12), nullable=False),         # taslak | donduruldu | dagitildi
    sa.Column("icerik_json", sa.Text, nullable=False),
    sa.Column("icerik_sha256", sa.String(64), nullable=False),
    sa.Column("ozet_metin", sa.Text),
    sa.Column("ozet_durum", sa.String(14), nullable=False, default="yok"),  # yok | hazirlaniyor | taslak | onayli | hata
    sa.Column("ozet_kaynak", sa.String(10)),                   # zeki | insan
    sa.Column("ozet_not", sa.Text),
    sa.Column("ozet_onaylayan", sa.String(120)),
    _ts("ozet_onay_at"),
    sa.Column("derleyen", sa.String(120), nullable=False),
    _ts("derleme_at", nullable=False),
    sa.Column("pdf_yol", sa.String(500)),
    sa.Column("pdf_sha256", sa.String(64)),
    sa.Column("donduran", sa.String(120)),
    _ts("dondurma_at"),
    sa.UniqueConstraint("meeting_id", "surum", name="uq_kurul_package_version"),
)

DISTRIBUTION = sa.Table(
    "semantic_kurul_distribution", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("package_id", sa.String(40), nullable=False, index=True),
    sa.Column("alici", sa.String(200), nullable=False),
    sa.Column("uye_id", sa.String(40)),
    sa.Column("kanal", sa.String(10), nullable=False),         # baglanti | pdf | indirme
    sa.Column("gonderen", sa.String(120), nullable=False),
    _ts("gonderim_at", nullable=False),
    sa.Column("sonuc", sa.String(200)),
)

MEMBERS = sa.Table(
    "semantic_kurul_members", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("ad", sa.String(200), nullable=False),
    sa.Column("eposta", sa.String(200)),
    sa.Column("ad_hesabi", sa.String(120)),
    sa.Column("kurul", sa.String(10), nullable=False),         # yonetim | danisma
    sa.Column("gorev", sa.String(120)),
    sa.Column("aktif", sa.Boolean, nullable=False, default=True),
    sa.Column("guncelleyen", sa.String(120)),
    _ts("guncelleme"),
)

JOBS = sa.Table(
    "semantic_kurul_jobs", _md,
    sa.Column("id", sa.String(40), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(20), nullable=False),
    sa.Column("durum", sa.String(12), nullable=False),         # calisiyor | bitti | hata
    sa.Column("sonuc_json", sa.Text),
    sa.Column("hata", sa.Text),
    sa.Column("baslatan", sa.String(120), nullable=False),
    _ts("baslangic", nullable=False),
    _ts("bitis"),
)

META = sa.Table(
    "semantic_kurul_meta", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(200), primary_key=True),
    sa.Column("value_json", sa.Text),
    _ts("updated_at"),
)

UNITS = {"tl": "₺", "yuzde": "%", "adet": "adet", "gun": "gün"}
DIRECTIONS = {"artis_kotu": "Arttıkça kötü", "azalis_kotu": "Azaldıkça kötü"}
COLORS = {"yesil": "Yolunda", "sari": "İzlenmeli", "kirmizi": "Dikkat", "esik_yok": "Eşik tanımlı değil"}
MEETING_TYPES = {"yonetim": "Yönetim kurulu", "danisma": "Danışma kurulu"}
MEETING_STATES = {"planlandi": "Planlandı", "yapildi": "Yapıldı", "iptal": "İptal"}
AGENDA_TYPES = {"karar": "Karar", "bilgi": "Bilgi"}
ACTION_STATES = {"acik": "Açık", "tamamlandi": "Tamamlandı", "iptal": "İptal"}
PACKAGE_STATES = {"taslak": "Taslak", "donduruldu": "Donduruldu", "dagitildi": "Dağıtıldı"}
SUMMARY_STATES = {"yok": "Özet yok", "hazirlaniyor": "Zeki AI yazıyor", "taslak": "Taslak — onay bekliyor",
                  "onayli": "Onaylandı", "hata": "Hazırlanamadı"}
COMMENT_STATES = {"hazirlaniyor": "Zeki AI yazıyor", "taslak": "Taslak", "onayli": "Onaylı", "hata": "Hazırlanamadı"}
CHANNELS = {"baglanti": "Portal bağlantısı (AD hesabı)", "pdf": "PDF (elle iletilecek)", "indirme": "PDF indirildi"}


class KurulError(ValueError):
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


# ------------------------------------------------------------------ küçük yardımcılar


def _conf(key: str, default: str) -> str:
    try:
        from semantic_bridge import admin as admin_mod
        v = admin_mod.conf(key)
    except Exception:  # noqa: BLE001 — testte admin ayarı yok
        v = ""
    return v if v not in (None, "") else os.environ.get(key, default)


def _conf_int(key: str, default: int, lo: int = 0, hi: int = 100000) -> int:
    try:
        return max(lo, min(hi, int(str(_conf(key, str(default))).strip())))
    except ValueError:
        return default


def settings() -> dict[str, Any]:
    return {
        "company": _conf("KURUL_COMPANY", "Timaş Yayınları"),
        "staleHours": _conf_int("KURUL_STALE_HOURS", 24, 1, 24 * 30),
        "actionWarnDays": _conf_int("KURUL_ACTION_WARN_DAYS", 7, 0, 90),
        "commentRemindDays": _conf_int("KURUL_COMMENT_REMIND_DAYS", 5, 0, 30),
        "historyMonths": _conf_int("KURUL_HISTORY_MONTHS", 12, 1, 60),
    }


def files_root() -> Path:
    return Path(os.environ.get("KURUL_DIR", "/data/nanobaseai/bi/var/kurul"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def current_donem(d: Optional[date] = None) -> str:
    d = d or today()
    return f"{d.year:04d}-{d.month:02d}"


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _iso(v: Optional[datetime]) -> Optional[str]:
    v = _aware(v)
    return v.isoformat() if v else None


def _j(v: Optional[str], default: Any) -> Any:
    if not v:
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def _dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)


def _uid() -> str:
    return uuid.uuid4().hex


def _text(v: Any, limit: int, label: str = "Metin", required: bool = False) -> Optional[str]:
    s = str(v).strip() if v is not None else ""
    if not s:
        if required:
            raise KurulError(f"{label} boş olamaz.")
        return None
    if len(s) > limit:
        raise KurulError(f"{label} en çok {limit} karakter olabilir.")
    return s


def _day(v: Any, label: str, required: bool = False) -> Optional[str]:
    s = str(v).strip() if v not in (None, "") else ""
    if not s:
        if required:
            raise KurulError(f"{label} gerekli.")
        return None
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        raise KurulError(f"{label} YYYY-AA-GG biçiminde olmalı.") from None


def _num(v: Any, label: str) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        n = float(str(v).replace(",", "."))
    except ValueError:
        raise KurulError(f"{label} sayı olmalı.") from None
    if n != n or n in (float("inf"), float("-inf")):
        raise KurulError(f"{label} sayı olmalı.")
    return n


def _choice(v: Any, allowed: dict[str, str], label: str) -> str:
    s = str(v or "").strip()
    if s not in allowed:
        raise KurulError(f"{label} geçersiz: {', '.join(allowed)} olmalı.")
    return s


def _email(v: Any) -> Optional[str]:
    s = _text(v, 200, "E-posta")
    if s and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s):
        raise KurulError("E-posta adresi geçersiz.")
    return s


def _account(v: Any) -> Optional[str]:
    s = _text(v, 120, "Hesap")
    return s.lower() if s else None


def valid_donem(v: Any) -> str:
    s = str(v or "").strip()
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", s):
        raise KurulError("Dönem YYYY-AA biçiminde olmalı.")
    return s


def donem_label(donem: str) -> str:
    ay = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    y, m = donem.split("-")
    return f"{ay[int(m) - 1]} {y}"


def meta_get(engine: sa.engine.Engine, tenant: str, key: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(sa.select(META.c.value_json).where(META.c.tenant_id == tenant, META.c.key == key)).first()
    return _j(r[0], None) if r else None


def meta_set(engine: sa.engine.Engine, tenant: str, key: str, value: Any) -> None:
    with engine.begin() as c:
        c.execute(META.delete().where(META.c.tenant_id == tenant, META.c.key == key))
        c.execute(META.insert().values(tenant_id=tenant, key=key, value_json=_dump(value), updated_at=_now()))


# ------------------------------------------------------------------ biçim (Türkçe; paket ve Zeki AI olguları)


def _grp(n: float, decimals: int = 0) -> str:
    s = f"{abs(n):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if n < 0 else "") + s


def fmt_value(v: Optional[float], birim: str) -> str:
    """Ekrandaki ve PDF'teki yazımı: 848.110.179 ₺, %42,7, 12 adet, 43 gün. Değer yoksa «—»."""
    if v is None:
        return "—"
    if birim == "tl":
        return f"{_grp(v)} ₺"
    if birim == "yuzde":
        return f"%{_grp(v, 1)}"
    if birim == "gun":
        return f"{_grp(v)} gün"
    return _grp(v, 0 if float(v).is_integer() else 1)


def fmt_short(v: Optional[float], birim: str) -> str:
    """Kısa tutar: 848,1 Mn ₺; diğer birimler `fmt_value`."""
    if v is None or birim != "tl":
        return fmt_value(v, birim)
    a = abs(v)
    if a >= 1e9:
        return f"{_grp(v / 1e9, 1)} Mr ₺"
    if a >= 1e6:
        return f"{_grp(v / 1e6, 1)} Mn ₺"
    if a >= 1e3:
        return f"{_grp(v / 1e3, 1)} B ₺"
    return fmt_value(v, birim)


# ------------------------------------------------------------------ renk ve eğilim


def state_of(value: Optional[float], yon: str, sari: Optional[float], kirmizi: Optional[float]) -> Optional[str]:
    """Göstergenin kendi eşiğiyle renk; eşik yoksa None (kaynak rengine ya da «eşik yok»a bırakılır)."""
    if value is None or (sari is None and kirmizi is None):
        return None
    if yon == "azalis_kotu":
        if kirmizi is not None and value <= kirmizi:
            return "kirmizi"
        if sari is not None and value <= sari:
            return "sari"
        return "yesil"
    if kirmizi is not None and value >= kirmizi:
        return "kirmizi"
    if sari is not None and value >= sari:
        return "sari"
    return "yesil"


def color_of(ind: dict[str, Any], res: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """(renk, renk kaynağı). Kaynak yok / hata → (None, None)."""
    if res.get("durum") != "ok" or res.get("deger") is None:
        return None, None
    own = state_of(res["deger"], ind["yon"], ind.get("esikSari"), ind.get("esikKirmizi"))
    if own:
        return own, "esik"
    if res.get("renk") in ("yesil", "sari", "kirmizi"):
        return res["renk"], "kaynak"
    return "esik_yok", None


def trend(deger: Optional[float], onceki: Optional[float], yon: str) -> Optional[dict[str, Any]]:
    """Önceki döneme ok: yön (yukari/asagi/sabit), iyi/kötü, değişim oranı."""
    if deger is None or onceki is None:
        return None
    if abs(deger - onceki) < 1e-9:
        return {"yon": "sabit", "iyi": None, "oran": 0.0}
    up = deger > onceki
    good = (not up) if yon == "artis_kotu" else up
    oran = (deger - onceki) / abs(onceki) if onceki else None
    return {"yon": "yukari" if up else "asagi", "iyi": good, "oran": None if oran is None else round(oran, 4)}


# ------------------------------------------------------------------ gösterge kataloğu


def _ind_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"kod": d["kod"], "bolum": d["bolum"], "bolumAdi": S.BOLUMLER.get(d["bolum"], d["bolum"]), "ad": d["ad"],
            "aciklama": d["aciklama"], "saglayici": d["saglayici"], "birim": d["birim"], "birimAdi": UNITS.get(d["birim"], d["birim"]),
            "yon": d["yon"], "yonAdi": DIRECTIONS.get(d["yon"], d["yon"]), "esikSari": d["esik_sari"], "esikKirmizi": d["esik_kirmizi"],
            "hedefKaynagi": d["hedef_kaynagi"], "sahip": d["sahip"], "sahipEposta": d["sahip_eposta"], "sira": d["sira"],
            "aktif": bool(d["aktif"]), "surum": d["surum"], "guncelleyen": d["guncelleyen"], "guncelleme": _iso(d["guncelleme"])}


def seed_library(engine: sa.engine.Engine, tenant: str, library: Iterable[dict[str, Any]] = S.LIBRARY) -> int:
    """Hazır tanımları eksikse ekler (var olanın eşiğine, sahibine, adına dokunmaz). Eklenen sayısı."""
    added = 0
    with engine.begin() as c:
        have = {r[0] for r in c.execute(sa.select(INDICATORS.c.kod).where(INDICATORS.c.tenant_id == tenant))}
        for g in library:
            if g["kod"] in have:
                continue
            c.execute(INDICATORS.insert().values(
                tenant_id=tenant, kod=g["kod"], bolum=g["bolum"], ad=g["ad"], aciklama=g.get("aciklama"), saglayici=g.get("saglayici"),
                birim=g["birim"], yon=g["yon"], esik_sari=None, esik_kirmizi=None, hedef_kaynagi=g.get("hedefKaynagi"), sahip=None,
                sahip_eposta=None, sira=int(g.get("sira") or 0), aktif=True, surum=1, guncelleyen="sistem", guncelleme=_now()))
            added += 1
    return added


def _bolum_order(b: str) -> int:
    keys = list(S.BOLUMLER)
    return keys.index(b) if b in keys else len(keys)


def indicators(engine: sa.engine.Engine, tenant: str, *, only_active: bool = False) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(INDICATORS).where(INDICATORS.c.tenant_id == tenant)).all()
    items = [_ind_out(r) for r in rows]
    if only_active:
        items = [g for g in items if g["aktif"]]
    items.sort(key=lambda g: (_bolum_order(g["bolum"]), g["sira"], g["ad"]))
    return items


def indicator(engine: sa.engine.Engine, tenant: str, kod: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(INDICATORS).where(INDICATORS.c.tenant_id == tenant, INDICATORS.c.kod == kod)).first()
    if r is None:
        raise KurulError("Gösterge bulunamadı.", 404)
    return _ind_out(r)


def _check_thresholds(yon: str, sari: Optional[float], kirmizi: Optional[float]) -> None:
    if sari is None or kirmizi is None:
        return
    if yon == "artis_kotu" and sari > kirmizi:
        raise KurulError("Arttıkça kötü göstergede sarı eşik kırmızıdan büyük olamaz.")
    if yon == "azalis_kotu" and sari < kirmizi:
        raise KurulError("Azaldıkça kötü göstergede sarı eşik kırmızıdan küçük olamaz.")


_IND_FIELDS = {  # gövde → (kolon, dönüştürücü)
    "ad": ("ad", lambda v: _text(v, 200, "Ad", True)),
    "aciklama": ("aciklama", lambda v: _text(v, 2000, "Açıklama")),
    "bolum": ("bolum", lambda v: _choice(v, S.BOLUMLER, "Bölüm")),
    "birim": ("birim", lambda v: _choice(v, UNITS, "Birim")),
    "yon": ("yon", lambda v: _choice(v, DIRECTIONS, "Yön")),
    "esikSari": ("esik_sari", lambda v: _num(v, "Sarı eşik")),
    "esikKirmizi": ("esik_kirmizi", lambda v: _num(v, "Kırmızı eşik")),
    "hedefKaynagi": ("hedef_kaynagi", lambda v: _text(v, 200, "Hedef kaynağı")),
    "sahip": ("sahip", _account),
    "sahipEposta": ("sahip_eposta", _email),
    "sira": ("sira", lambda v: int(_num(v, "Sıra") or 0)),
    "aktif": ("aktif", bool),
}


def update_indicator(engine: sa.engine.Engine, tenant: str, user: str, kod: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Tanım, eşik, sahip ve sıra. Sağlayıcı değiştirilemez (hesap kaynağı kodla bağlanır). Her değişiklik yeni sürüm."""
    cur = indicator(engine, tenant, kod)
    vals: dict[str, Any] = {}
    diff: dict[str, Any] = {}
    for key, (col, conv) in _IND_FIELDS.items():
        if key in body:
            v = conv(body[key])
            if v != cur.get(key):
                vals[col] = v
                diff[key] = {"eski": cur.get(key), "yeni": v}
    if not vals:
        return cur, {}
    yon = vals.get("yon", cur["yon"])
    _check_thresholds(yon, vals.get("esik_sari", cur["esikSari"]), vals.get("esik_kirmizi", cur["esikKirmizi"]))
    vals.update(surum=cur["surum"] + 1, guncelleyen=user, guncelleme=_now())
    with engine.begin() as c:
        c.execute(INDICATORS.update().where(INDICATORS.c.tenant_id == tenant, INDICATORS.c.kod == kod).values(**vals))
    return indicator(engine, tenant, kod), diff


def create_indicator(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    """Elle izlenen yeni gösterge (sağlayıcısız → gri kalır, kaynak bağlanınca `saglayici` kodla verilir). Hazır
    kataloğun dışındaki sağlayıcı adı kabul edilmez: rakam her zaman bir modülden gelir, elle girilmez."""
    kod = str(body.get("kod") or "").strip().lower()
    if not re.match(r"^[a-z][a-z0-9_]{2,59}$", kod):
        raise KurulError("Kod küçük harf, rakam ve alt çizgiyle 3–60 karakter olmalı.")
    prov = body.get("saglayici") or None
    if prov is not None and prov not in S.PROVIDERS:
        raise KurulError("Bilinmeyen sağlayıcı: " + ", ".join(S.PROVIDERS) + " ya da boş olmalı.")
    vals = {col: conv(body[key]) for key, (col, conv) in _IND_FIELDS.items() if key in body}
    for need in ("ad", "bolum", "birim", "yon"):
        if not vals.get(need):
            raise KurulError(f"{need} gerekli.")
    _check_thresholds(vals["yon"], vals.get("esik_sari"), vals.get("esik_kirmizi"))
    with engine.begin() as c:
        if c.execute(sa.select(INDICATORS.c.kod).where(INDICATORS.c.tenant_id == tenant, INDICATORS.c.kod == kod)).first():
            raise KurulError("Bu kodda gösterge zaten var.", 409)
        c.execute(INDICATORS.insert().values(tenant_id=tenant, kod=kod, saglayici=prov, surum=1, guncelleyen=user,
                                             guncelleme=_now(), **{"sira": 0, "aktif": True, **vals}))
    return indicator(engine, tenant, kod)


# ------------------------------------------------------------------ ölçüm (dönem değeri)


def _value_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"donem": d["donem"], "olcum": _iso(d["olcum_at"]), "deger": d["deger"], "hedef": d["hedef"], "onceki": d["onceki"],
            "oncekiEtiket": d["onceki_etiket"], "renk": d["renk"], "renkKaynagi": d["renk_kaynagi"], "durum": d["durum"],
            "veriSonGunu": d["veri_son_gunu"], "kaynak": d["kaynak"], "ekran": d["ekran"], "not": d["not_"],
            "ayrinti": _j(d["ayrinti_json"], {}), "oncekiRenk": d["onceki_renk"], "renkDegisti": _iso(d["renk_degisti_at"])}


def _last_value_before(c: Any, tenant: str, kod: str, donem: str) -> Optional[Any]:
    return c.execute(sa.select(VALUES).where(VALUES.c.tenant_id == tenant, VALUES.c.kod == kod, VALUES.c.donem < donem)
                     .order_by(VALUES.c.donem.desc()).limit(1)).first()


def record(engine: sa.engine.Engine, tenant: str, donem: str, results: dict[str, dict[str, Any]],
           now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Ölçüm sonuçlarını dönem satırına yazar (aynı dönemde yeniden ölçüm üzerine yazar). Rengi değişen göstergeler döner.
    Sağlayıcı önceki değeri vermezse (geçen yılın aynı dönemi, 30 gün önce) önceki dönemin kaydı karşılaştırılır."""
    now = now or _now()
    inds = {g["kod"]: g for g in indicators(engine, tenant)}
    changes: list[dict[str, Any]] = []
    with engine.begin() as c:
        for kod, res in results.items():
            ind = inds.get(kod)
            if ind is None:
                continue
            renk, src = color_of(ind, res)
            cur = c.execute(sa.select(VALUES).where(VALUES.c.tenant_id == tenant, VALUES.c.kod == kod, VALUES.c.donem == donem)).first()
            prev_row = _last_value_before(c, tenant, kod, donem)
            onceki, etiket = res.get("onceki"), res.get("oncekiEtiket")
            if onceki is None and prev_row is not None and prev_row.durum == "ok" and prev_row.deger is not None:
                onceki, etiket = prev_row.deger, f"{donem_label(prev_row.donem)} ölçümü"
            old_color = cur.renk if cur is not None else (prev_row.renk if prev_row is not None else None)
            changed = renk is not None and old_color is not None and renk != old_color and renk != "esik_yok"
            vals = dict(olcum_at=now, deger=res.get("deger"), hedef=res.get("hedef"), onceki=onceki, onceki_etiket=etiket, renk=renk,
                        renk_kaynagi=src, durum=res.get("durum") or "hata", veri_son_gunu=res.get("veriSonGunu"),
                        kaynak=res.get("kaynak"), ekran=res.get("ekran"), not_=res.get("not"), ayrinti_json=_dump(res.get("ayrinti") or {}))
            if changed:
                vals.update(onceki_renk=old_color, renk_degisti_at=now)
                changes.append({"kod": kod, "ad": ind["ad"], "eski": old_color, "yeni": renk, "sahip": ind.get("sahip"),
                                "sahipEposta": ind.get("sahipEposta"), "deger": res.get("deger"), "birim": ind["birim"]})
            if cur is None:
                c.execute(VALUES.insert().values(id=_uid(), tenant_id=tenant, kod=kod, donem=donem, **vals))
            else:
                c.execute(VALUES.update().where(VALUES.c.id == cur.id).values(**vals))
    meta_set(engine, tenant, "olcum", {"at": now.isoformat(), "donem": donem, "sayi": len(results),
                                       "gri": sum(1 for r in results.values() if r.get("durum") == "kaynak_yok"),
                                       "hata": sum(1 for r in results.values() if r.get("durum") == "hata")})
    return changes


def last_measure(engine: sa.engine.Engine, tenant: str) -> Optional[dict[str, Any]]:
    return meta_get(engine, tenant, "olcum")


def is_stale(engine: sa.engine.Engine, tenant: str, now: Optional[datetime] = None) -> bool:
    m = last_measure(engine, tenant)
    if not m or not m.get("at"):
        return True
    at = _aware(datetime.fromisoformat(m["at"]))
    return (now or _now()) - at > timedelta(hours=settings()["staleHours"]) or m.get("donem") != current_donem()


def donemler(engine: sa.engine.Engine, tenant: str) -> list[str]:
    with engine.connect() as c:
        return [r[0] for r in c.execute(sa.select(VALUES.c.donem).where(VALUES.c.tenant_id == tenant).distinct()
                                        .order_by(VALUES.c.donem.desc()))]


def _values_for(engine: sa.engine.Engine, tenant: str, donem: str) -> dict[str, dict[str, Any]]:
    with engine.connect() as c:
        return {r.kod: _value_out(r) for r in c.execute(sa.select(VALUES).where(VALUES.c.tenant_id == tenant, VALUES.c.donem == donem))}


# ------------------------------------------------------------------ yorumlar


def _comment_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"id": d["id"], "kod": d["kod"], "donem": d["donem"], "metin": d["metin"], "durum": d["durum"],
            "durumAdi": COMMENT_STATES.get(d["durum"], d["durum"]), "kaynak": d["kaynak"], "yazan": d["yazan"],
            "yazildi": _iso(d["yazildi_at"]), "onaylayan": d["onaylayan"], "onaylandi": _iso(d["onaylandi_at"]), "hata": d["hata"]}


def comments(engine: sa.engine.Engine, tenant: str, kod: Optional[str] = None, donem: Optional[str] = None) -> list[dict[str, Any]]:
    cond = [COMMENTS.c.tenant_id == tenant]
    if kod:
        cond.append(COMMENTS.c.kod == kod)
    if donem:
        cond.append(COMMENTS.c.donem == donem)
    with engine.connect() as c:
        rows = c.execute(sa.select(COMMENTS).where(*cond).order_by(COMMENTS.c.yazildi_at.desc())).all()
    return [_comment_out(r) for r in rows]


def approved_comments(engine: sa.engine.Engine, tenant: str, donem: str) -> dict[str, dict[str, Any]]:
    """Dönemde göstergenin en son onaylanan yorumu."""
    out: dict[str, dict[str, Any]] = {}
    for cm in sorted((x for x in comments(engine, tenant, donem=donem) if x["durum"] == "onayli"), key=lambda x: x["onaylandi"] or ""):
        out[cm["kod"]] = cm
    return out


def comment(engine: sa.engine.Engine, tenant: str, cid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(COMMENTS).where(COMMENTS.c.tenant_id == tenant, COMMENTS.c.id == cid)).first()
    if r is None:
        raise KurulError("Yorum bulunamadı.", 404)
    return _comment_out(r)


def add_comment(engine: sa.engine.Engine, tenant: str, user: str, kod: str, donem: str, metin: Any, *, approve: bool) -> dict[str, Any]:
    """İnsan yorumu. Göstergenin sahibi yazınca doğrudan onaylıdır; başkası (sekreter) yazınca sahibin onayını bekler."""
    indicator(engine, tenant, kod)
    text = _text(metin, 2000, "Yorum", True)
    cid, now = _uid(), _now()
    with engine.begin() as c:
        c.execute(COMMENTS.insert().values(id=cid, tenant_id=tenant, kod=kod, donem=valid_donem(donem), metin=text,
                                           durum="onayli" if approve else "taslak", kaynak="insan", yazan=user, yazildi_at=now,
                                           onaylayan=user if approve else None, onaylandi_at=now if approve else None))
    return comment(engine, tenant, cid)


def start_comment_draft(engine: sa.engine.Engine, tenant: str, user: str, kod: str, donem: str) -> dict[str, Any]:
    indicator(engine, tenant, kod)
    cid = _uid()
    with engine.begin() as c:
        c.execute(COMMENTS.insert().values(id=cid, tenant_id=tenant, kod=kod, donem=valid_donem(donem), metin=None,
                                           durum="hazirlaniyor", kaynak="zeki", yazan=user, yazildi_at=_now()))
    return comment(engine, tenant, cid)


def finish_comment_draft(engine: sa.engine.Engine, cid: str, text: Optional[str], error: Optional[str], job_id: Optional[str] = None) -> None:
    with engine.begin() as c:
        c.execute(COMMENTS.update().where(COMMENTS.c.id == cid).values(
            metin=text, durum="hata" if error else "taslak", hata=error, llm_job_id=job_id))


def edit_comment(engine: sa.engine.Engine, tenant: str, cid: str, metin: Any) -> dict[str, Any]:
    cm = comment(engine, tenant, cid)
    if cm["durum"] not in ("taslak", "hata"):
        raise KurulError("Yalnız taslak yorum düzenlenir; onaylı yorumun yerine yeni yorum yazın.", 409)
    with engine.begin() as c:
        c.execute(COMMENTS.update().where(COMMENTS.c.id == cid).values(metin=_text(metin, 2000, "Yorum", True), durum="taslak",
                                                                        kaynak="insan" if cm["kaynak"] == "insan" else "zeki", hata=None))
    return comment(engine, tenant, cid)


def approve_comment(engine: sa.engine.Engine, tenant: str, user: str, cid: str) -> dict[str, Any]:
    cm = comment(engine, tenant, cid)
    if cm["durum"] != "taslak" or not cm["metin"]:
        raise KurulError("Yalnız metni olan taslak onaylanır.", 409)
    with engine.begin() as c:
        c.execute(COMMENTS.update().where(COMMENTS.c.id == cid).values(durum="onayli", onaylayan=user, onaylandi_at=_now()))
    return comment(engine, tenant, cid)


def delete_comment(engine: sa.engine.Engine, tenant: str, cid: str) -> dict[str, Any]:
    cm = comment(engine, tenant, cid)
    if cm["durum"] == "onayli":
        raise KurulError("Onaylı yorum silinmez; yerine yeni yorum yazın.", 409)
    with engine.begin() as c:
        c.execute(COMMENTS.delete().where(COMMENTS.c.id == cid))
    return cm


# ------------------------------------------------------------------ panel ve gösterge ayrıntısı


def _item(ind: dict[str, Any], val: Optional[dict[str, Any]], cm: Optional[dict[str, Any]], pending: bool) -> dict[str, Any]:
    v = val or {}
    ok = v.get("durum") == "ok"
    return {**ind, "durum": v.get("durum") or "olculmedi", "deger": v.get("deger") if ok else None,
            "degerMetin": fmt_value(v.get("deger"), ind["birim"]) if ok else None,
            "degerKisa": fmt_short(v.get("deger"), ind["birim"]) if ok else None,
            "hedef": v.get("hedef") if ok else None, "onceki": v.get("onceki") if ok else None, "oncekiEtiket": v.get("oncekiEtiket"),
            "egilim": trend(v.get("deger"), v.get("onceki"), ind["yon"]) if ok else None,
            "renk": v.get("renk") if ok else None, "renkAdi": COLORS.get(v.get("renk") or "", None) if ok else None,
            "renkKaynagi": v.get("renkKaynagi"), "veriSonGunu": v.get("veriSonGunu"), "kaynak": v.get("kaynak"),
            "ekran": v.get("ekran"), "not": v.get("not"), "olcum": v.get("olcum"), "ayrinti": v.get("ayrinti") or {},
            "renkDegisti": v.get("renkDegisti"), "oncekiRenk": v.get("oncekiRenk"),
            "yorum": ({"metin": cm["metin"], "yazan": cm["yazan"], "onaylayan": cm["onaylayan"], "onaylandi": cm["onaylandi"],
                       "kaynak": cm["kaynak"]} if cm else None),
            "yorumBekliyor": pending}


def panel(engine: sa.engine.Engine, tenant: str, donem: Optional[str] = None) -> dict[str, Any]:
    all_d = donemler(engine, tenant)
    d = valid_donem(donem) if donem else (all_d[0] if all_d else current_donem())
    vals = _values_for(engine, tenant, d)
    appr = approved_comments(engine, tenant, d)
    drafts = {cm["kod"] for cm in comments(engine, tenant, donem=d) if cm["durum"] in ("taslak", "hazirlaniyor")}
    groups: dict[str, list[dict[str, Any]]] = {}
    for ind in indicators(engine, tenant, only_active=True):
        groups.setdefault(ind["bolum"], []).append(_item(ind, vals.get(ind["kod"]), appr.get(ind["kod"]), ind["kod"] in drafts))
    bolumler = [{"id": b, "ad": S.BOLUMLER.get(b, b), "gostergeler": groups[b]} for b in sorted(groups, key=_bolum_order)]
    flat = [g for b in bolumler for g in b["gostergeler"]]
    kritik = [g for g in flat if g["renk"] == "kirmizi"]
    ends = sorted({g["veriSonGunu"] for g in flat if g["veriSonGunu"]})
    return {"donem": d, "donemAdi": donem_label(d), "donemler": all_d, "bolumler": bolumler, "kritik": kritik,
            "sayilar": {"toplam": len(flat), "hazir": sum(1 for g in flat if g["durum"] == "ok"),
                        "gri": sum(1 for g in flat if g["durum"] in ("kaynak_yok", "olculmedi")),
                        "hata": sum(1 for g in flat if g["durum"] == "hata"),
                        "kirmizi": len(kritik), "sari": sum(1 for g in flat if g["renk"] == "sari"),
                        "yorumsuzRenkli": sum(1 for g in flat if g["renk"] in ("kirmizi", "sari") and not g["yorum"])},
            "enEskiVeri": ends[0] if ends else None, "olcum": last_measure(engine, tenant)}


def indicator_detail(engine: sa.engine.Engine, tenant: str, kod: str, donem: Optional[str] = None) -> dict[str, Any]:
    ind = indicator(engine, tenant, kod)
    months = settings()["historyMonths"]
    with engine.connect() as c:
        rows = c.execute(sa.select(VALUES).where(VALUES.c.tenant_id == tenant, VALUES.c.kod == kod)
                         .order_by(VALUES.c.donem.desc()).limit(months)).all()
    seri = [_value_out(r) for r in reversed(rows)]
    d = valid_donem(donem) if donem else (seri[-1]["donem"] if seri else current_donem())
    cur = next((v for v in seri if v["donem"] == d), None)
    appr = approved_comments(engine, tenant, d).get(kod)
    return {"gosterge": _item(ind, cur, appr, False), "donem": d, "donemAdi": donem_label(d),
            "seri": [{"donem": v["donem"], "deger": v["deger"] if v["durum"] == "ok" else None, "renk": v["renk"],
                      "hedef": v["hedef"], "durum": v["durum"]} for v in seri],
            "yorumlar": comments(engine, tenant, kod=kod, donem=d)}


def comment_facts(detail: dict[str, Any]) -> dict[str, Any]:
    """Bölüm yorumu taslağının olguları: göstergenin tanımı, bu dönem ve 12 dönem seyri — yalnız bunlar."""
    g = detail["gosterge"]
    return {"gosterge": g["ad"], "bolum": g["bolumAdi"], "aciklama": g["aciklama"], "birim": g["birimAdi"],
            "donem": detail["donemAdi"], "deger": g["degerMetin"], "degerHam": g["deger"], "hedef": fmt_value(g["hedef"], g["birim"]),
            "onceki": fmt_value(g["onceki"], g["birim"]), "oncekiEtiket": g["oncekiEtiket"], "renk": g["renkAdi"],
            "veriSonGunu": g["veriSonGunu"], "kaynak": g["kaynak"], "not": g["not"],
            "seri": [{"donem": s["donem"], "deger": fmt_value(s["deger"], g["birim"]), "degerHam": s["deger"]} for s in detail["seri"]]}


# ------------------------------------------------------------------ Zeki AI metin denetimi


def foreign_numbers(text: str, facts: Any) -> set[str]:
    """Metinde geçip olgularda olmayan sayılar (M47 ile aynı denetim; ≤ 31 küçük sayılar serbest)."""
    from semantic_bridge.risk import foreign_numbers as _fn

    return _fn(text, facts)


def draft_text(chat: Optional[Callable[[list[dict[str, str]]], str]], system: str, facts: Any) -> tuple[Optional[str], Optional[str]]:
    """(metin, hata). Model yoksa, boş dönerse ya da olgularda olmayan sayı yazarsa metin **kaydedilmez**."""
    if chat is None:
        return None, "Zeki AI bu kurulumda tanımlı değil."
    msg = [{"role": "system", "content": system}, {"role": "user", "content": "Olgular (JSON):\n" + _dump(facts)}]
    try:
        text = (chat(msg) or "").strip()
    except Exception as e:  # noqa: BLE001
        return None, f"Zeki AI yanıt vermedi: {str(e)[:200]}"
    if not text:
        return None, "Zeki AI boş yanıt verdi."
    extra = foreign_numbers(text, facts)
    if extra:
        return None, f"Zeki AI metninde olgularda olmayan sayı vardı ({', '.join(sorted(extra))}); taslak kaydedilmedi."
    return text, None


COMMENT_SYSTEM = ("Bir yayınevinin yönetim kurulu paneli için tek bir göstergeye bölüm yöneticisi adına 2-3 cümlelik yorum "
                  "taslağı yazıyorsun. Yalnız verilen JSON olgularını kullan; olgularda olmayan hiçbir sayı, oran ya da tarih "
                  "yazma, tahmin yapma, neden uydurma. Neden bilinmiyorsa «nedeni bölüm yöneticisi yazacak» de. Türkçe, düz metin.")

SUMMARY_SYSTEM = ("Bir yayınevinin yönetim kurulu paketi için genel müdür adına en çok 1 sayfalık yönetici özeti taslağı "
                  "yazıyorsun. Yalnız verilen JSON olgularını kullan; olgularda olmayan hiçbir sayı yazma, tahmin ve yorum "
                  "uydurma. Önce genel durum, sonra dikkat isteyen göstergeler (bölüm yöneticisinin onaylı yorumuyla), sonra "
                  "geciken kurul aksiyonları. Kaynağı olmayan (gri) alanları «henüz bağlı değil» diye an. Türkçe; başlıklar "
                  "'## ' ile, maddeler '- ' ile.")

MINUTES_SYSTEM = ("Kurul sekreterinin toplantı notlarından karar ve aksiyon önerisi çıkarıyorsun. Yalnız notlarda yazanı "
                  "kullan; notlarda olmayan kişi, sayı, tarih ekleme. Yalnız JSON döndür: {\"kararlar\": [{\"gundemSira\": "
                  "sayı ya da null, \"metin\": \"...\", \"aksiyonlar\": [{\"eylem\": \"...\", \"sahipAdayi\": \"notlardaki ad ya da "
                  "null\", \"terminAdayi\": \"YYYY-AA-GG ya da null\"}]}]}")


def parse_minutes(raw: str, notes: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Tutanak önerisi: yalnız biçimi doğru ve notlarda geçmeyen sayı içermeyen maddeler kalır. (öneriler, düşenler)."""
    text = (raw or "").strip()
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0) if m else text)
    except (ValueError, AttributeError):
        return [], ["Zeki AI yanıtı okunamadı (JSON değil)."]
    out, dropped = [], []
    for k in (data.get("kararlar") if isinstance(data, dict) else None) or []:
        if not isinstance(k, dict) or not str(k.get("metin") or "").strip():
            continue
        karar = str(k["metin"]).strip()[:2000]
        if foreign_numbers(karar, notes):
            dropped.append(karar[:80])
            continue
        acts = []
        for a in k.get("aksiyonlar") or []:
            if not isinstance(a, dict) or not str(a.get("eylem") or "").strip():
                continue
            eylem = str(a["eylem"]).strip()[:1000]
            if foreign_numbers(eylem, notes):
                dropped.append(eylem[:80])
                continue
            termin = str(a.get("terminAdayi") or "").strip()[:10]
            try:
                termin = date.fromisoformat(termin).isoformat() if termin else None
            except ValueError:
                termin = None
            if termin and termin.replace("-", "") not in re.sub(r"\D", "", notes) and termin not in notes:
                termin = None      # notlarda geçmeyen tarih önerilmez
            sahip = str(a.get("sahipAdayi") or "").strip()[:120] or None
            if sahip and sahip.lower() not in notes.lower():
                sahip = None
            acts.append({"eylem": eylem, "sahipAdayi": sahip, "terminAdayi": termin})
        gs = k.get("gundemSira")
        out.append({"gundemSira": gs if isinstance(gs, int) else None, "metin": karar, "aksiyonlar": acts})
    return out, dropped


# ------------------------------------------------------------------ üyeler


def _member_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"id": d["id"], "ad": d["ad"], "eposta": d["eposta"], "adHesabi": d["ad_hesabi"], "kurul": d["kurul"],
            "kurulAdi": MEETING_TYPES.get(d["kurul"], d["kurul"]), "gorev": d["gorev"], "aktif": bool(d["aktif"]),
            "guncelleyen": d["guncelleyen"], "guncelleme": _iso(d["guncelleme"])}


def members(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    with engine.connect() as c:
        rows = c.execute(sa.select(MEMBERS).where(MEMBERS.c.tenant_id == tenant).order_by(MEMBERS.c.kurul, MEMBERS.c.ad)).all()
    return [_member_out(r) for r in rows]


def save_member(engine: sa.engine.Engine, tenant: str, user: str, mid: Optional[str], body: dict[str, Any]) -> dict[str, Any]:
    fields = {"ad": ("ad", lambda v: _text(v, 200, "Ad", True)), "eposta": ("eposta", _email), "adHesabi": ("ad_hesabi", _account),
              "kurul": ("kurul", lambda v: _choice(v, MEETING_TYPES, "Kurul")), "gorev": ("gorev", lambda v: _text(v, 120, "Görev")),
              "aktif": ("aktif", bool)}
    vals = {col: conv(body[k]) for k, (col, conv) in fields.items() if k in body}
    vals.update(guncelleyen=user, guncelleme=_now())
    with engine.begin() as c:
        if mid:
            if not c.execute(sa.select(MEMBERS.c.id).where(MEMBERS.c.id == mid, MEMBERS.c.tenant_id == tenant)).first():
                raise KurulError("Üye bulunamadı.", 404)
            c.execute(MEMBERS.update().where(MEMBERS.c.id == mid).values(**vals))
        else:
            if not vals.get("ad") or not vals.get("kurul"):
                raise KurulError("Ad ve kurul gerekli.")
            mid = _uid()
            c.execute(MEMBERS.insert().values(id=mid, tenant_id=tenant, **{"aktif": True, **vals}))
        r = c.execute(sa.select(MEMBERS).where(MEMBERS.c.id == mid)).first()
    return _member_out(r)


def delete_member(engine: sa.engine.Engine, tenant: str, mid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = c.execute(sa.select(MEMBERS).where(MEMBERS.c.id == mid, MEMBERS.c.tenant_id == tenant)).first()
        if r is None:
            raise KurulError("Üye bulunamadı.", 404)
        used = c.execute(sa.select(DISTRIBUTION.c.id).where(DISTRIBUTION.c.uye_id == mid)).first()
        if used:
            # Dağıtım kaydı olan üye silinmez (kime gittiği bilinmeli); pasife alınır.
            c.execute(MEMBERS.update().where(MEMBERS.c.id == mid).values(aktif=False, guncelleme=_now()))
        else:
            c.execute(MEMBERS.delete().where(MEMBERS.c.id == mid))
    return _member_out(r)


# ------------------------------------------------------------------ toplantı, gündem, karar, aksiyon


def _meeting_out(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"id": d["id"], "tur": d["tur"], "turAdi": MEETING_TYPES.get(d["tur"], d["tur"]), "baslik": d["baslik"], "tarih": d["tarih"],
            "saat": d["saat"], "yer": d["yer"], "durum": d["durum"], "durumAdi": MEETING_STATES.get(d["durum"], d["durum"]),
            "katilimcilar": _j(d["katilimcilar_json"], []), "notlar": d["notlar"], "olusturan": d["olusturan"],
            "olusturma": _iso(d["olusturma"]), "guncelleyen": d["guncelleyen"], "guncelleme": _iso(d["guncelleme"])}


def _meeting_row(c: Any, tenant: str, mid: str) -> Any:
    r = c.execute(sa.select(MEETINGS).where(MEETINGS.c.id == mid, MEETINGS.c.tenant_id == tenant)).first()
    if r is None:
        raise KurulError("Toplantı bulunamadı.", 404)
    return r


def _participants(v: Any) -> list[str]:
    if v in (None, ""):
        return []
    items = v if isinstance(v, list) else re.split(r"[,;\n]+", str(v))
    out = []
    for x in items:
        s = str(x).strip()[:200]
        if s and s not in out:
            out.append(s)
    return out[:200]


def _clock(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    if not s:
        return None
    if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", s):
        raise KurulError("Saat SS:DD biçiminde olmalı.")
    return s


_MEETING_FIELDS = {
    "tur": ("tur", lambda v: _choice(v, MEETING_TYPES, "Kurul türü")),
    "baslik": ("baslik", lambda v: _text(v, 200, "Başlık", True)),
    "tarih": ("tarih", lambda v: _day(v, "Tarih", True)),
    "saat": ("saat", lambda v: _clock(v)),
    "yer": ("yer", lambda v: _text(v, 200, "Yer")),
    "durum": ("durum", lambda v: _choice(v, MEETING_STATES, "Durum")),
    "katilimcilar": ("katilimcilar_json", lambda v: _dump(_participants(v))),
    "notlar": ("notlar", lambda v: _text(v, 20000, "Notlar")),
}


def create_meeting(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = {col: conv(body[k]) for k, (col, conv) in _MEETING_FIELDS.items() if k in body}
    vals.setdefault("tur", "yonetim")
    if not vals.get("tarih"):
        raise KurulError("Tarih gerekli.")
    vals.setdefault("baslik", MEETING_TYPES[vals["tur"]] + " toplantısı")
    mid = _uid()
    with engine.begin() as c:
        c.execute(MEETINGS.insert().values(id=mid, tenant_id=tenant, olusturan=user, olusturma=_now(),
                                           **{"durum": "planlandi", "katilimcilar_json": "[]", **vals}))
    return meeting(engine, tenant, mid)


def update_meeting(engine: sa.engine.Engine, tenant: str, user: str, mid: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    vals = {col: conv(body[k]) for k, (col, conv) in _MEETING_FIELDS.items() if k in body}
    with engine.begin() as c:
        cur = _meeting_out(_meeting_row(c, tenant, mid))
        if vals:
            c.execute(MEETINGS.update().where(MEETINGS.c.id == mid).values(guncelleyen=user, guncelleme=_now(), **vals))
    diff = {k: True for k in body if k in _MEETING_FIELDS and k != "notlar"}
    return meeting(engine, tenant, mid), {"once": {k: cur.get(k) for k in diff}, "alanlar": sorted(diff)}


def list_meetings(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(MEETINGS).where(MEETINGS.c.tenant_id == tenant).order_by(MEETINGS.c.tarih.desc())).all()
        pk = c.execute(sa.select(PACKAGES.c.meeting_id, sa.func.max(PACKAGES.c.surum))
                       .where(PACKAGES.c.tenant_id == tenant).group_by(PACKAGES.c.meeting_id)).all()
        frozen = {r[0] for r in c.execute(sa.select(PACKAGES.c.meeting_id).where(
            PACKAGES.c.tenant_id == tenant, PACKAGES.c.durum.in_(("donduruldu", "dagitildi"))))}
        dec = dict(c.execute(sa.select(DECISIONS.c.meeting_id, sa.func.count()).where(DECISIONS.c.tenant_id == tenant)
                             .group_by(DECISIONS.c.meeting_id)).all())
    last = {m: s for m, s in pk}
    t = today().isoformat()
    items = []
    for r in rows:
        m = _meeting_out(r)
        m.update(paketSurum=last.get(m["id"]), paketDondu=m["id"] in frozen, kararSayisi=int(dec.get(m["id"]) or 0),
                 kalanGun=(date.fromisoformat(m["tarih"]) - date.fromisoformat(t)).days)
        m.pop("notlar", None)
        items.append(m)
    upcoming = sorted([m for m in items if m["tarih"] >= t and m["durum"] == "planlandi"], key=lambda m: m["tarih"])
    return {"items": items, "siradaki": upcoming[0] if upcoming else None}


def _agenda(c: Any, mid: str) -> list[dict[str, Any]]:
    return [{"sira": r.sira, "baslik": r.baslik, "tur": r.tur, "turAdi": AGENDA_TYPES.get(r.tur, r.tur), "sunan": r.sunan,
             "sureDk": r.sure_dk, "ekRef": r.ek_ref}
            for r in c.execute(sa.select(AGENDA).where(AGENDA.c.meeting_id == mid).order_by(AGENDA.c.sira))]


def set_agenda(engine: sa.engine.Engine, tenant: str, mid: str, items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise KurulError("Gündem bir liste olmalı.")
    rows = []
    for i, it in enumerate(items, start=1):
        if not isinstance(it, dict):
            raise KurulError("Gündem maddesi geçersiz.")
        sure = it.get("sureDk")
        rows.append({"id": _uid(), "meeting_id": mid, "sira": i, "baslik": _text(it.get("baslik"), 300, f"{i}. madde başlığı", True),
                     "tur": _choice(it.get("tur") or "bilgi", AGENDA_TYPES, "Madde türü"), "sunan": _text(it.get("sunan"), 120, "Sunan"),
                     "sure_dk": None if sure in (None, "") else max(0, min(600, int(_num(sure, "Süre") or 0))),
                     "ek_ref": _text(it.get("ekRef"), 300, "Ek")})
    with engine.begin() as c:
        _meeting_row(c, tenant, mid)
        c.execute(AGENDA.delete().where(AGENDA.c.meeting_id == mid))
        if rows:
            c.execute(AGENDA.insert(), rows)
        return _agenda(c, mid)


def _action_out(r: Any, t: Optional[date] = None) -> dict[str, Any]:
    d = dict(r._mapping)
    t = t or today()
    kalan = (date.fromisoformat(d["termin"]) - t).days if d["termin"] else None
    late = d["durum"] == "acik" and kalan is not None and kalan < 0
    return {"id": d["id"], "kararId": d["decision_id"], "toplantiId": d["meeting_id"], "eylem": d["eylem"], "sahip": d["sahip"],
            "sahipEposta": d["sahip_eposta"], "termin": d["termin"], "kalanGun": kalan, "durum": d["durum"],
            "durumAdi": "Gecikti" if late else ACTION_STATES.get(d["durum"], d["durum"]), "gecikti": late, "sonNot": d["son_not"],
            "olusturan": d["olusturan"], "olusturma": _iso(d["olusturma"]), "guncelleyen": d["guncelleyen"],
            "guncelleme": _iso(d["guncelleme"]), "tamamlanma": _iso(d["tamamlanma"])}


def _decision_out(r: Any, acts: list[dict[str, Any]]) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"id": d["id"], "toplantiId": d["meeting_id"], "gundemSira": d["gundem_sira"], "metin": d["metin"], "oyOzeti": d["oy_ozeti"],
            "yazan": d["yazan"], "tarih": _iso(d["tarih"]), "guncelleyen": d["guncelleyen"], "guncelleme": _iso(d["guncelleme"]),
            "aksiyonlar": acts}


def _decisions(c: Any, tenant: str, meeting_ids: Optional[list[str]] = None) -> list[dict[str, Any]]:
    cond = [DECISIONS.c.tenant_id == tenant]
    if meeting_ids is not None:
        cond.append(DECISIONS.c.meeting_id.in_(meeting_ids or [""]))
    decs = c.execute(sa.select(DECISIONS).where(*cond).order_by(DECISIONS.c.gundem_sira, DECISIONS.c.tarih)).all()
    ids = [d.id for d in decs]
    acts: dict[str, list[dict[str, Any]]] = {}
    for a in c.execute(sa.select(ACTIONS).where(ACTIONS.c.decision_id.in_(ids or [""])).order_by(ACTIONS.c.termin)):
        acts.setdefault(a.decision_id, []).append(_action_out(a))
    return [_decision_out(d, acts.get(d.id, [])) for d in decs]


def meeting(engine: sa.engine.Engine, tenant: str, mid: str) -> dict[str, Any]:
    with engine.connect() as c:
        m = _meeting_out(_meeting_row(c, tenant, mid))
        m["gundem"] = _agenda(c, mid)
        m["kararlar"] = _decisions(c, tenant, [mid])
        m["paketler"] = [_package_brief(r) for r in c.execute(sa.select(PACKAGES).where(PACKAGES.c.meeting_id == mid)
                                                               .order_by(PACKAGES.c.surum.desc()))]
    return m


def _action_values(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "eylem" in body or not partial:
        vals["eylem"] = _text(body.get("eylem"), 1000, "Eylem", True)
    if "sahip" in body:
        vals["sahip"] = _account(body.get("sahip"))
    if "sahipEposta" in body:
        vals["sahip_eposta"] = _email(body.get("sahipEposta"))
    if "termin" in body:
        vals["termin"] = _day(body.get("termin"), "Termin")
    return vals


def add_decision(engine: sa.engine.Engine, tenant: str, user: str, mid: str, body: dict[str, Any]) -> dict[str, Any]:
    metin = _text(body.get("metin"), 4000, "Karar metni", True)
    gs = body.get("gundemSira")
    gs = None if gs in (None, "") else int(_num(gs, "Gündem sırası") or 0)
    acts_in = body.get("aksiyonlar") or []
    if not isinstance(acts_in, list):
        raise KurulError("Aksiyonlar bir liste olmalı.")
    acts = [_action_values(a if isinstance(a, dict) else {}, partial=False) for a in acts_in]
    did, now = _uid(), _now()
    with engine.begin() as c:
        _meeting_row(c, tenant, mid)
        c.execute(DECISIONS.insert().values(id=did, tenant_id=tenant, meeting_id=mid, gundem_sira=gs, metin=metin,
                                            oy_ozeti=_text(body.get("oyOzeti"), 300, "Oy özeti"), yazan=user, tarih=now))
        for a in acts:
            c.execute(ACTIONS.insert().values(id=_uid(), tenant_id=tenant, decision_id=did, meeting_id=mid, durum="acik",
                                              olusturan=user, olusturma=now, **a))
        return next(d for d in _decisions(c, tenant, [mid]) if d["id"] == did)


def _decision_row(c: Any, tenant: str, did: str) -> Any:
    r = c.execute(sa.select(DECISIONS).where(DECISIONS.c.id == did, DECISIONS.c.tenant_id == tenant)).first()
    if r is None:
        raise KurulError("Karar bulunamadı.", 404)
    return r


def update_decision(engine: sa.engine.Engine, tenant: str, user: str, did: str, body: dict[str, Any]) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    if "metin" in body:
        vals["metin"] = _text(body.get("metin"), 4000, "Karar metni", True)
    if "oyOzeti" in body:
        vals["oy_ozeti"] = _text(body.get("oyOzeti"), 300, "Oy özeti")
    if "gundemSira" in body:
        gs = body.get("gundemSira")
        vals["gundem_sira"] = None if gs in (None, "") else int(_num(gs, "Gündem sırası") or 0)
    with engine.begin() as c:
        r = _decision_row(c, tenant, did)
        if vals:
            c.execute(DECISIONS.update().where(DECISIONS.c.id == did).values(guncelleyen=user, guncelleme=_now(), **vals))
        return next(d for d in _decisions(c, tenant, [r.meeting_id]) if d["id"] == did)


def delete_decision(engine: sa.engine.Engine, tenant: str, did: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _decision_row(c, tenant, did)
        done = c.execute(sa.select(ACTIONS.c.id).where(ACTIONS.c.decision_id == did, ACTIONS.c.durum != "acik")).first()
        if done:
            raise KurulError("Aksiyonu kapanmış karar silinmez; metnini düzeltin.", 409)
        c.execute(ACTIONS.delete().where(ACTIONS.c.decision_id == did))
        c.execute(DECISIONS.delete().where(DECISIONS.c.id == did))
    return {"id": did, "toplantiId": r.meeting_id, "metin": r.metin}


def action(engine: sa.engine.Engine, tenant: str, aid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(ACTIONS).where(ACTIONS.c.id == aid, ACTIONS.c.tenant_id == tenant)).first()
    if r is None:
        raise KurulError("Aksiyon bulunamadı.", 404)
    return _action_out(r)


def add_action(engine: sa.engine.Engine, tenant: str, user: str, did: str, body: dict[str, Any]) -> dict[str, Any]:
    vals = _action_values(body, partial=False)
    aid = _uid()
    with engine.begin() as c:
        d = _decision_row(c, tenant, did)
        c.execute(ACTIONS.insert().values(id=aid, tenant_id=tenant, decision_id=did, meeting_id=d.meeting_id, durum="acik",
                                          olusturan=user, olusturma=_now(), **vals))
    return action(engine, tenant, aid)


def update_action(engine: sa.engine.Engine, tenant: str, user: str, aid: str, body: dict[str, Any], *, full: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Sahip yalnız durum ve son notu değiştirir; hazırlayan (sekreter) her alanı. Sahiplik API'de denetlenir."""
    cur = action(engine, tenant, aid)
    allowed = {"durum", "sonNot"} | ({"eylem", "sahip", "sahipEposta", "termin"} if full else set())
    extra = set(body) - allowed
    if extra:
        raise KurulError("Bu alanları değiştiremezsiniz: " + ", ".join(sorted(extra)), 403)
    vals = _action_values({k: v for k, v in body.items() if k in ("eylem", "sahip", "sahipEposta", "termin")}, partial=True)
    if "durum" in body:
        vals["durum"] = _choice(body["durum"], ACTION_STATES, "Durum")
        if vals["durum"] != "tamamlandi":
            vals["tamamlanma"] = None
        elif cur["durum"] != "tamamlandi":
            vals["tamamlanma"] = _now()
    if "sonNot" in body:
        vals["son_not"] = _text(body.get("sonNot"), 2000, "Not")
    if not vals:
        return cur, {}
    with engine.begin() as c:
        c.execute(ACTIONS.update().where(ACTIONS.c.id == aid).values(guncelleyen=user, guncelleme=_now(), **vals))
    out = action(engine, tenant, aid)
    diff = {k: {"eski": cur.get(k), "yeni": out.get(k)} for k in ("durum", "sonNot", "eylem", "sahip", "termin") if cur.get(k) != out.get(k)}
    return out, diff


def list_actions(engine: sa.engine.Engine, tenant: str, *, durum: str = "acik", sahip: Optional[str] = None) -> dict[str, Any]:
    cond = [ACTIONS.c.tenant_id == tenant]
    if durum in ("acik", "geciken"):
        cond.append(ACTIONS.c.durum == "acik")
    elif durum in ACTION_STATES:
        cond.append(ACTIONS.c.durum == durum)
    if sahip:
        cond.append(sa.func.lower(ACTIONS.c.sahip) == sahip.lower())
    with engine.connect() as c:
        rows = c.execute(sa.select(ACTIONS, DECISIONS.c.metin.label("karar"), MEETINGS.c.baslik.label("toplanti"),
                                   MEETINGS.c.tarih.label("toplanti_tarih"))
                         .join(DECISIONS, DECISIONS.c.id == ACTIONS.c.decision_id)
                         .join(MEETINGS, MEETINGS.c.id == ACTIONS.c.meeting_id)
                         .where(*cond).order_by(ACTIONS.c.termin)).all()
    items = []
    for r in rows:
        a = _action_out(r)
        a.update(karar=r.karar, toplanti=r.toplanti, toplantiTarihi=r.toplanti_tarih)
        items.append(a)
    if durum == "geciken":
        items = [a for a in items if a["gecikti"]]
    items.sort(key=lambda a: (not a["gecikti"], a["termin"] or "9999"))
    return {"items": items, "total": len(items), "geciken": sum(1 for a in items if a["gecikti"])}


def agenda_suggestions(engine: sa.engine.Engine, tenant: str, mid: str) -> list[dict[str, Any]]:
    """Kural (model yok): geciken kurul aksiyonları ve kırmızı göstergeler gündem maddesi önerisi olur."""
    with engine.connect() as c:
        _meeting_row(c, tenant, mid)
    out = []
    late = list_actions(engine, tenant, durum="geciken")["items"]
    if late:
        out.append({"baslik": f"Geciken kurul aksiyonları ({len(late)})", "tur": "bilgi", "neden": "aksiyon",
                    "ayrinti": [a["eylem"][:120] for a in late[:10]]})
    for g in panel(engine, tenant)["kritik"]:
        out.append({"baslik": f"{g['ad']}: {g['degerMetin']}", "tur": "karar", "neden": "gosterge", "sunan": g.get("sahip"),
                    "ayrinti": [g["yorum"]["metin"]] if g.get("yorum") else []})
    return out


# ------------------------------------------------------------------ kurul paketi


def _package_brief(r: Any) -> dict[str, Any]:
    d = dict(r._mapping)
    return {"id": d["id"], "toplantiId": d["meeting_id"], "surum": d["surum"], "durum": d["durum"],
            "durumAdi": PACKAGE_STATES.get(d["durum"], d["durum"]), "ozetDurum": d["ozet_durum"],
            "ozetDurumAdi": SUMMARY_STATES.get(d["ozet_durum"], d["ozet_durum"]), "derleyen": d["derleyen"],
            "derleme": _iso(d["derleme_at"]), "donduran": d["donduran"], "dondurma": _iso(d["dondurma_at"]),
            "pdfVar": bool(d["pdf_yol"]), "pdfSha256": d["pdf_sha256"], "icerikSha256": d["icerik_sha256"]}


def _package_row(c: Any, tenant: str, pid: str) -> Any:
    r = c.execute(sa.select(PACKAGES).where(PACKAGES.c.id == pid, PACKAGES.c.tenant_id == tenant)).first()
    if r is None:
        raise KurulError("Paket bulunamadı.", 404)
    return r


def package(engine: sa.engine.Engine, tenant: str, pid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = _package_row(c, tenant, pid)
        dist = [{"id": x.id, "alici": x.alici, "uyeId": x.uye_id, "kanal": x.kanal, "kanalAdi": CHANNELS.get(x.kanal, x.kanal),
                 "gonderen": x.gonderen, "zaman": _iso(x.gonderim_at), "sonuc": x.sonuc}
                for x in c.execute(sa.select(DISTRIBUTION).where(DISTRIBUTION.c.package_id == pid).order_by(DISTRIBUTION.c.gonderim_at))]
    d = dict(r._mapping)
    return {**_package_brief(r), "icerik": _j(d["icerik_json"], {}), "ozetMetin": d["ozet_metin"], "ozetKaynak": d["ozet_kaynak"],
            "ozetNot": d["ozet_not"], "ozetOnaylayan": d["ozet_onaylayan"], "ozetOnay": _iso(d["ozet_onay_at"]), "dagitim": dist}


def canonical_hash(content: Any) -> str:
    return hashlib.sha256(_dump(content).encode("utf-8")).hexdigest()


def previous_decisions(engine: sa.engine.Engine, tenant: str, mid: str) -> list[dict[str, Any]]:
    """Bu toplantıdan önceki toplantıların kararları: aksiyonu açık olanlar ve son toplantıdan beri kapananlar."""
    with engine.connect() as c:
        m = _meeting_row(c, tenant, mid)
        prev = c.execute(sa.select(MEETINGS).where(MEETINGS.c.tenant_id == tenant, MEETINGS.c.tarih < m.tarih,
                                                   MEETINGS.c.durum != "iptal").order_by(MEETINGS.c.tarih.desc())).all()
        if not prev:
            return []
        since = prev[0].tarih
        decs = _decisions(c, tenant, [p.id for p in prev])
    names = {p.id: (p.baslik, p.tarih) for p in prev}
    out = []
    for d in decs:
        keep = [a for a in d["aksiyonlar"] if a["durum"] == "acik" or (a["tamamlanma"] or a["guncelleme"] or "")[:10] >= since]
        if not keep and d["aksiyonlar"]:
            continue
        if not d["aksiyonlar"] and names[d["toplantiId"]][1] != since:
            continue
        out.append({"toplanti": names[d["toplantiId"]][0], "tarih": names[d["toplantiId"]][1], "karar": d["metin"],
                    "aksiyonlar": [{"eylem": a["eylem"], "sahip": a["sahip"], "termin": a["termin"], "durum": a["durumAdi"],
                                    "gecikti": a["gecikti"], "sonNot": a["sonNot"]} for a in keep]})
    out.sort(key=lambda x: (x["tarih"], x["karar"]))
    return out


def build_content(engine: sa.engine.Engine, tenant: str, mid: str, *, risk: Optional[dict[str, Any]], risk_numbers: Optional[dict[str, Any]],
                  market: Optional[dict[str, Any]], now: Optional[datetime] = None) -> dict[str, Any]:
    """Paketin anlık görüntüsü. Göstergeler son ölçüm döneminin kayıtlı değeridir (derleme anında yeniden hesap yok)."""
    now = now or _now()
    st = settings()
    m = meeting(engine, tenant, mid)
    p = panel(engine, tenant)
    groups = []
    missing = []
    for b in p["bolumler"]:
        items = []
        for g in b["gostergeler"]:
            items.append({"kod": g["kod"], "ad": g["ad"], "durum": g["durum"], "deger": g["deger"], "degerMetin": g["degerMetin"],
                          "hedefMetin": fmt_value(g["hedef"], g["birim"]) if g["hedef"] is not None else None,
                          "oncekiMetin": fmt_value(g["onceki"], g["birim"]) if g["onceki"] is not None else None,
                          "oncekiEtiket": g["oncekiEtiket"], "egilim": g["egilim"], "renk": g["renk"], "renkAdi": g["renkAdi"],
                          "birim": g["birim"], "veriSonGunu": g["veriSonGunu"], "kaynak": g["kaynak"], "not": g["not"],
                          "sahip": g["sahip"], "yorum": g["yorum"]})
            if g["renk"] in ("kirmizi", "sari") and not g["yorum"]:
                missing.append({"kod": g["kod"], "ad": g["ad"], "sahip": g["sahip"]})
        groups.append({"id": b["id"], "ad": b["ad"], "gostergeler": items})
    ends: dict[str, str] = {}
    for b in groups:
        for g in b["gostergeler"]:
            if g["veriSonGunu"] and g["kaynak"]:
                ends[g["kaynak"]] = min(ends.get(g["kaynak"], g["veriSonGunu"]), g["veriSonGunu"])
    acts = list_actions(engine, tenant, durum="acik")
    return {
        "surumYapisi": 1,
        "kapak": {"sirket": st["company"], "toplanti": {k: m[k] for k in ("id", "baslik", "tur", "turAdi", "tarih", "saat", "yer")},
                  "katilimcilar": m["katilimcilar"], "derleme": now.isoformat(), "donem": p["donem"], "donemAdi": p["donemAdi"],
                  "veriSonGunleri": dict(sorted(ends.items())), "enEskiVeri": p["enEskiVeri"]},
        "gostergeler": groups,
        "sayilar": p["sayilar"],
        "kritik": [{"ad": g["ad"], "degerMetin": g["degerMetin"], "sahip": g["sahip"], "yorum": (g["yorum"] or {}).get("metin")}
                   for g in p["kritik"]],
        "eksikYorum": missing,
        "gundem": m["gundem"],
        "oncekiKararlar": previous_decisions(engine, tenant, mid),
        "aksiyonOzeti": {"acik": acts["total"], "geciken": acts["geciken"]},
        "risk": {"sayilar": risk_numbers, "brifing": risk},
        "pazar": market,
    }


def compile_package(engine: sa.engine.Engine, tenant: str, user: str, mid: str, content: dict[str, Any]) -> dict[str, Any]:
    """Taslak varsa onu yeniler (aynı sürüm; yönetici özeti düşer, çünkü girdisi değişti); son sürüm dondurulduysa yeni
    sürüm açar."""
    h = canonical_hash(content)
    now = _now()
    with engine.begin() as c:
        _meeting_row(c, tenant, mid)
        last = c.execute(sa.select(PACKAGES).where(PACKAGES.c.meeting_id == mid).order_by(PACKAGES.c.surum.desc()).limit(1)).first()
        if last is not None and last.durum == "taslak":
            if last.ozet_durum == "hazirlaniyor":
                raise KurulError("Zeki AI yönetici özetini yazıyor; bitince yeniden derleyin.", 409)
            pid = last.id
            c.execute(PACKAGES.update().where(PACKAGES.c.id == pid).values(
                icerik_json=_dump(content), icerik_sha256=h, derleyen=user, derleme_at=now, ozet_metin=None, ozet_durum="yok",
                ozet_kaynak=None, ozet_not=None, ozet_onaylayan=None, ozet_onay_at=None))
        else:
            pid = _uid()
            c.execute(PACKAGES.insert().values(id=pid, tenant_id=tenant, meeting_id=mid, surum=(last.surum + 1) if last else 1,
                                               durum="taslak", icerik_json=_dump(content), icerik_sha256=h, ozet_durum="yok",
                                               derleyen=user, derleme_at=now))
    return package(engine, tenant, pid)


def _editable(r: Any) -> None:
    if r.durum != "taslak":
        raise KurulError("Dondurulan paket değişmez; düzeltme için yeniden derleyin (yeni sürüm açılır).", 409)


def summary_facts(content: dict[str, Any]) -> dict[str, Any]:
    """Yönetici özeti olguları: gösterge değerleri (yazılı biçimiyle), renk, onaylı yorumlar, aksiyon sayıları, risk
    sayıları. Model yalnız bunları görür."""
    return {
        "toplanti": content["kapak"]["toplanti"].get("baslik"), "tarih": content["kapak"]["toplanti"].get("tarih"),
        "donem": content["kapak"].get("donemAdi"), "enEskiVeri": content["kapak"].get("enEskiVeri"),
        "gostergeler": [{"bolum": b["ad"], "ad": g["ad"], "deger": g["degerMetin"], "onceki": g["oncekiMetin"],
                         "oncekiEtiket": g["oncekiEtiket"], "hedef": g["hedefMetin"], "renk": g["renkAdi"],
                         "durum": "kaynak yok" if g["durum"] in ("kaynak_yok", "olculmedi") else ("okunamadı" if g["durum"] == "hata" else "hazır"),
                         "yorum": (g["yorum"] or {}).get("metin"), "veriSonGunu": g["veriSonGunu"]}
                        for b in content["gostergeler"] for g in b["gostergeler"]],
        "aksiyonlar": content.get("aksiyonOzeti"),
        "oncekiKararSayisi": len(content.get("oncekiKararlar") or []),
        "risk": (content.get("risk") or {}).get("sayilar"),
        "pazarOzetiVar": bool(content.get("pazar")), "riskBrifingiVar": bool((content.get("risk") or {}).get("brifing")),
    }


def start_summary(engine: sa.engine.Engine, tenant: str, pid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _package_row(c, tenant, pid)
        _editable(r)
        if r.ozet_durum == "hazirlaniyor":
            raise KurulError("Özet zaten hazırlanıyor.", 409)
        c.execute(PACKAGES.update().where(PACKAGES.c.id == pid).values(ozet_durum="hazirlaniyor", ozet_not=None))
        return _j(r.icerik_json, {})


def finish_summary(engine: sa.engine.Engine, pid: str, text: Optional[str], error: Optional[str]) -> None:
    with engine.begin() as c:
        r = c.execute(sa.select(PACKAGES).where(PACKAGES.c.id == pid)).first()
        if r is None or r.durum != "taslak":
            return
        if error:
            c.execute(PACKAGES.update().where(PACKAGES.c.id == pid).values(ozet_durum="hata", ozet_not=error))
        else:
            c.execute(PACKAGES.update().where(PACKAGES.c.id == pid).values(ozet_metin=text, ozet_durum="taslak", ozet_kaynak="zeki",
                                                                            ozet_not=None, ozet_onaylayan=None, ozet_onay_at=None))


def edit_summary(engine: sa.engine.Engine, tenant: str, pid: str, text: Any) -> dict[str, Any]:
    """Genel müdürün düzeltmesi. İnsan metnindeki olgu dışı sayılar engellenmez ama uyarı olarak döner."""
    t = _text(text, 20000, "Özet")
    with engine.begin() as c:
        r = _package_row(c, tenant, pid)
        _editable(r)
        if r.ozet_durum == "hazirlaniyor":
            raise KurulError("Zeki AI özeti yazıyor; bitince düzenleyin.", 409)
        c.execute(PACKAGES.update().where(PACKAGES.c.id == pid).values(
            ozet_metin=t, ozet_durum="taslak" if t else "yok", ozet_kaynak="insan" if t else None,
            ozet_onaylayan=None, ozet_onay_at=None, ozet_not=None))
        content = _j(r.icerik_json, {})
    out = package(engine, tenant, pid)
    out["olguDisiSayilar"] = sorted(foreign_numbers(t or "", summary_facts(content))) if t else []
    return out


def approve_summary(engine: sa.engine.Engine, tenant: str, user: str, pid: str) -> dict[str, Any]:
    with engine.begin() as c:
        r = _package_row(c, tenant, pid)
        _editable(r)
        if r.ozet_durum != "taslak" or not r.ozet_metin:
            raise KurulError("Onaylanacak özet taslağı yok.", 409)
        c.execute(PACKAGES.update().where(PACKAGES.c.id == pid).values(ozet_durum="onayli", ozet_onaylayan=user, ozet_onay_at=_now()))
    return package(engine, tenant, pid)


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    tmp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def freeze_package(engine: sa.engine.Engine, tenant: str, user: str, pid: str,
                   render: Callable[[dict[str, Any], Optional[str], dict[str, Any]], bytes]) -> dict[str, Any]:
    """Taslak → donduruldu. PDF bir kez üretilir ve sha256'sıyla saklanır; sonraki okuma aynı dosyayı verir."""
    now = _now()
    with engine.connect() as c:
        r = _package_row(c, tenant, pid)
    _editable(r)
    if r.ozet_durum == "hazirlaniyor":
        raise KurulError("Zeki AI yönetici özetini yazıyor; bitince dondurun.", 409)
    if r.ozet_durum == "taslak":
        raise KurulError("Yönetici özeti onaylanmadı: önce onaylayın ya da metni boşaltın.", 409)
    content = _j(r.icerik_json, {})
    if canonical_hash(content) != r.icerik_sha256:
        raise KurulError("Paket içeriği kayıttaki özetle uyuşmuyor; yeniden derleyin.", 409)
    stamp = {"surum": r.surum, "donduran": user, "dondurma": now.isoformat(), "icerikSha256": r.icerik_sha256,
             "ozetOnaylayan": r.ozet_onaylayan}
    data = render(content, r.ozet_metin if r.ozet_durum == "onayli" else None, stamp)
    digest = hashlib.sha256(data).hexdigest()
    path = files_root() / "packages" / f"{pid}-v{r.surum}.pdf"
    try:
        _write_private(path, data)
    except OSError as e:
        log.error("kurul paketi PDF'i yazılamadı (%s): %s", path, e)
        raise KurulError("PDF sunucuya kaydedilemedi; yöneticiye bildirin.", 503) from e
    with engine.begin() as c:
        n = c.execute(PACKAGES.update().where(PACKAGES.c.id == pid, PACKAGES.c.durum == "taslak").values(
            durum="donduruldu", pdf_yol=str(path), pdf_sha256=digest, donduran=user, dondurma_at=now)).rowcount
    if not n:
        raise KurulError("Paket bu arada değişti; yeniden açın.", 409)
    return package(engine, tenant, pid)


def package_pdf(engine: sa.engine.Engine, tenant: str, pid: str) -> tuple[bytes, dict[str, Any]]:
    """Dondurulmuş paketin PDF'i; dosya sha256'sı kayıtla tutmuyorsa verilmez (değişmezlik denetimi)."""
    with engine.connect() as c:
        r = _package_row(c, tenant, pid)
    if r.durum == "taslak" or not r.pdf_yol:
        raise KurulError("PDF yalnız dondurulmuş pakette vardır.", 409)
    try:
        data = Path(r.pdf_yol).read_bytes()
    except OSError:
        raise KurulError("Paketin PDF dosyası sunucuda bulunamadı.", 410) from None
    if hashlib.sha256(data).hexdigest() != r.pdf_sha256:
        raise KurulError("PDF dosyası kayıttaki özetle uyuşmuyor; dosya değişmiş olabilir. Yöneticiye bildirin.", 409)
    return data, _package_brief(r)


def record_distribution(engine: sa.engine.Engine, tenant: str, user: str, pid: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    now = _now()
    with engine.begin() as c:
        r = _package_row(c, tenant, pid)
        if r.durum == "taslak":
            raise KurulError("Yalnız dondurulmuş paket dağıtılır.", 409)
        for x in rows:
            c.execute(DISTRIBUTION.insert().values(id=_uid(), tenant_id=tenant, package_id=pid, alici=x["alici"][:200],
                                                   uye_id=x.get("uyeId"), kanal=x["kanal"], gonderen=user, gonderim_at=now,
                                                   sonuc=(x.get("sonuc") or "")[:200] or None))
        if any(x["kanal"] != "indirme" for x in rows) and r.durum == "donduruldu":
            c.execute(PACKAGES.update().where(PACKAGES.c.id == pid).values(durum="dagitildi"))
    return package(engine, tenant, pid)


def distribution_rows(engine: sa.engine.Engine, tenant: str, member_ids: Any) -> list[dict[str, Any]]:
    """Seçilen üyeler → dağıtım satırları. AD hesabı olan üyeye portal bağlantısı, olmayana «PDF elle iletilecek».
    Portal kimseye e-posta göndermez."""
    if not isinstance(member_ids, list) or not member_ids:
        raise KurulError("En az bir üye seçin.")
    all_m = {m["id"]: m for m in members(engine, tenant)}
    rows = []
    for mid in member_ids:
        m = all_m.get(str(mid))
        if m is None or not m["aktif"]:
            raise KurulError("Seçilen üyelerden biri bulunamadı ya da pasif.", 404)
        if m["adHesabi"]:
            rows.append({"alici": m["ad"], "uyeId": m["id"], "kanal": "baglanti", "sonuc": f"portal hesabı {m['adHesabi']}"})
        else:
            rows.append({"alici": m["ad"], "uyeId": m["id"], "kanal": "pdf",
                         "sonuc": "PDF elle iletilecek" + (f" ({m['eposta']})" if m["eposta"] else "")})
    return rows


def list_packages(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    with engine.connect() as c:
        rows = c.execute(sa.select(PACKAGES, MEETINGS.c.baslik, MEETINGS.c.tarih).join(MEETINGS, MEETINGS.c.id == PACKAGES.c.meeting_id)
                         .where(PACKAGES.c.tenant_id == tenant).order_by(MEETINGS.c.tarih.desc(), PACKAGES.c.surum.desc())).all()
    return {"items": [{**_package_brief(r), "toplanti": r.baslik, "toplantiTarihi": r.tarih} for r in rows]}


def visible_package(pkg: dict[str, Any], can_prepare: bool) -> bool:
    """Kurul üyesi (hazırlama yetkisi olmayan) yalnız dondurulmuş paketi görür."""
    return can_prepare or pkg["durum"] != "taslak"


# ------------------------------------------------------------------ arka plan işleri


def start_job(engine: sa.engine.Engine, tenant: str, user: str, kind: str, work: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    jid = _uid()
    with engine.begin() as c:
        c.execute(JOBS.insert().values(id=jid, tenant_id=tenant, tur=kind, durum="calisiyor", baslatan=user, baslangic=_now()))
    _active_jobs.add(jid)

    def run() -> None:
        try:
            res = work(jid)
            with engine.begin() as c:
                c.execute(JOBS.update().where(JOBS.c.id == jid).values(durum="bitti", sonuc_json=_dump(res), bitis=_now()))
        except Exception as e:  # noqa: BLE001
            log.exception("kurul işi %s (%s) hata verdi", jid, kind)
            msg = str(e) if isinstance(e, KurulError) else f"İş tamamlanamadı: {str(e)[:300]}"
            with engine.begin() as c:
                c.execute(JOBS.update().where(JOBS.c.id == jid).values(durum="hata", hata=msg, bitis=_now()))
        finally:
            _active_jobs.discard(jid)

    threading.Thread(target=run, name=f"kurul-{kind}-{jid[:6]}", daemon=True).start()
    return {"id": jid, "tur": kind, "durum": "calisiyor"}


def job(engine: sa.engine.Engine, tenant: str, jid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(JOBS).where(JOBS.c.id == jid, JOBS.c.tenant_id == tenant)).first()
    if r is None:
        raise KurulError("İş bulunamadı.", 404)
    st, err = r.durum, r.hata
    if st == "calisiyor" and jid not in _active_jobs:
        st, err = "hata", "İş yarıda kaldı (hizmet yeniden başladı); yeniden başlatın."
    return {"id": jid, "tur": r.tur, "durum": st, "sonuc": _j(r.sonuc_json, {}), "hata": err, "baslatan": r.baslatan,
            "baslangic": _iso(r.baslangic), "bitis": _iso(r.bitis)}


# ------------------------------------------------------------------ hatırlatmalar (zamanlayıcı)


def _business_days_between(a: date, b: date) -> int:
    """a'dan b'ye iş günü (hafta sonu hariç; resmî tatil bilinmiyor)."""
    if b <= a:
        return 0
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def due_reminders(engine: sa.engine.Engine, tenant: str, t: Optional[date] = None) -> list[dict[str, Any]]:
    """Gönderilmemiş hatırlatmalar (her anahtar bir kez): aksiyon termine N gün kala ve termin geçince; toplantıdan N iş
    günü önce onaylı yorumu olmayan sarı/kırmızı göstergenin sahibine."""
    t = t or today()
    st = settings()
    out: list[dict[str, Any]] = []
    for a in list_actions(engine, tenant, durum="acik")["items"]:
        if a["kalanGun"] is None:
            continue
        if a["gecikti"]:
            key = f"aksiyon-gecti:{a['id']}:{a['termin']}"
            text = f"Kurul aksiyonunun termini geçti ({a['termin']}): {a['eylem'][:200]}"
        elif a["kalanGun"] <= st["actionWarnDays"]:
            key = f"aksiyon-yaklasti:{a['id']}:{a['termin']}"
            text = f"Kurul aksiyonunun terminine {a['kalanGun']} gün kaldı ({a['termin']}): {a['eylem'][:200]}"
        else:
            continue
        out.append({"key": key, "sahip": a["sahip"], "eposta": a["sahipEposta"], "metin": text})
    nxt = list_meetings(engine, tenant)["siradaki"]
    if nxt and _business_days_between(t, date.fromisoformat(nxt["tarih"])) <= st["commentRemindDays"]:
        for b in panel(engine, tenant)["bolumler"]:
            for g in b["gostergeler"]:
                if g["renk"] in ("kirmizi", "sari") and not g["yorum"] and (g.get("sahip") or g.get("sahipEposta")):
                    out.append({"key": f"yorum:{nxt['id']}:{g['kod']}", "sahip": g.get("sahip"), "eposta": g.get("sahipEposta"),
                                "metin": f"{nxt['tarih']} kurul toplantısı için «{g['ad']}» göstergenize yorum bekleniyor "
                                         f"({g['renkAdi']}, {g['degerMetin']})."})
    sent = set((meta_get(engine, tenant, "hatirlatmalar") or {}).get("keys") or [])
    return [x for x in out if x["key"] not in sent]


def mark_sent(engine: sa.engine.Engine, tenant: str, keys: Iterable[str]) -> None:
    cur = meta_get(engine, tenant, "hatirlatmalar") or {}
    have = list(dict.fromkeys([*(cur.get("keys") or []), *keys]))
    meta_set(engine, tenant, "hatirlatmalar", {"keys": have[-5000:]})


def status(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    return {"olcum": last_measure(engine, tenant), "sonKosu": meta_get(engine, tenant, "son-kosu"),
            "bayat": is_stale(engine, tenant), "ayarlar": settings()}
