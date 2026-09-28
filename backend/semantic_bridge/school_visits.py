"""M31 Okul tanıtım ve ziyaret yönetimi (bayi eşleştirme dahil): portal kayıtları ve hesaplar.

Okul listesi, geçmiş ziyaret, sipariş, bayi ve katalog CRM/Logo'dan okunur (`school_visits_sources`); CRM'e yazma
yetkimiz olmadığı için (AGENTS.md «CRM'e yazma yok») portalın ürettiği her şey burada, köprünün kendi tablolarındadır:

- `semantic_school_profiles` — CRM ziyaret yerlerinin gece kopyası (metin sayılar temizlenmiş; diğer modüller ve
  doğrudan SQL okuması için). Ekran canlı okumayı kullanır; kopya `asof` ile «listenin tarihi»ni taşır.
- `semantic_school_context` — elle yüklenen dış veri: ilçe gelişmişlik endeksi (`ilce_endeks`) ve akademik takvim
  (`takvim`: tatil, sınav haftası). Müşteride web taraması kapalı; kaynak adı ve tarihi yüklemeyle birlikte kaydedilir.
- `semantic_school_priority` — gece hesaplanan öncelik puanı ve bileşenleri (dönem başına).
- `semantic_school_plans` — haftalık ziyaret planı (öneri → onaylı / iptal).
- `semantic_school_dealer_links` — okul ↔ bayi eşleşmesi: CRM geçmişi («cari ile ziyaret»), Zeki AI önerisi, elle;
  onay açıkça verilen `ozellik:okul.bayi-onay` ile. M59 gelirse aynı tabloya yazar (tek kayıt yeri M31).
- `semantic_school_catalogs` — okula hazırlanan kitap listesi (PDF buradan üretilir).
- `semantic_saha_ziyaret` — **M30 ile ortak** ziyaret tablosu (`tur='okul'`, `hedef_kimlik` = ziyaret yeri GUID);
  okul ziyaretine özgü alanlar `semantic_school_visit_details`'ta.
- `semantic_school_name_matches` — CRM etkinliğindeki serbest «okul» metninin ziyaret yerine eşlenmesi (kural ya da
  Zeki AI kararı; bir kez sorulur, kalıcıdır).

Rakam modelden gelmez: puan, sayı ve tutar kuraldan/SQL'den; model yalnız gerekçe cümlesi, öneri metni, serbest
nottan alan önerisi ve «aynı okul mu» kapalı sorusunu yazar (LLM kapısı, `rt.llm_for("okul")`).
"""
from __future__ import annotations

import base64
import csv
import io
import json
import logging
import re
import threading
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from semantic_bridge import school_visits_sources as src

log = logging.getLogger("semantic.school_visits")
TZ = ZoneInfo("Europe/Istanbul")
PAGE_SIZE = 50

# ------------------------------------------------------------------------------------------ tablolar

#: M30 ile ortak ziyaret tablosu. Tek tanım M30'da (`field_sales.VISITS`; tabloyu M30 açtı): not kolonu `notu`,
#: zamanlar İstanbul saatiyle metin (`YYYY-MM-DD` ya da `YYYY-MM-DDTHH:MM`), `olusturan` zorunlu. M31'in kendi kopya
#: tanımı (`not`, tarih tipleri) canlıdaki tabloyla uyuşmuyordu; okul kartı ve dönem raporu 502 veriyordu (2026-09-28).
#: M31 içinde zamanlar datetime/date olarak dolaşır; tabloya yazarken ve okurken aşağıdaki çeviricilerden geçer.
from semantic_bridge.field_sales import VISITS as SAHA_ZIYARET  # noqa: E402

_md = sa.MetaData()
PROFILES = sa.Table(
    "semantic_school_profiles", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("ziyaret_yeri_id", sa.String(40), primary_key=True),
    sa.Column("ad", sa.String(300)),
    sa.Column("kurum_tipi", sa.String(40)),
    sa.Column("kurum_turu", sa.String(40)),
    sa.Column("okul_turu", sa.String(60)),
    sa.Column("kademe", sa.String(60)),
    sa.Column("ogrenci", sa.Integer),
    sa.Column("ogretmen", sa.Integer),
    sa.Column("derslik", sa.Integer),
    sa.Column("kitap_sayisi", sa.Integer),
    sa.Column("il", sa.String(80)),
    sa.Column("ilce", sa.String(80)),
    sa.Column("kaynak", sa.String(10), nullable=False),                # crm | yukleme
    sa.Column("kaynak_tarihi", sa.Date),                               # CRM'de son değişiklik
    sa.Column("asof", sa.DateTime(timezone=True), nullable=False),
)
CONTEXT = sa.Table(
    "semantic_school_context", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("tur", sa.String(20), nullable=False),                   # ilce_endeks | takvim
    sa.Column("anahtar", sa.String(200), nullable=False),              # il|ilçe (sade) ya da başlangıç..bitiş|il
    sa.Column("deger_json", sa.Text, nullable=False),
    sa.Column("kaynak", sa.String(300)),
    sa.Column("kaynak_tarihi", sa.Date),
    sa.Column("yukleme_id", sa.String(32), nullable=False, index=True),
    sa.Column("aktif", sa.Boolean, nullable=False, default=True),
    sa.Column("yukleyen", sa.String(120), nullable=False),
    sa.Column("yukleme_zamani", sa.DateTime(timezone=True), nullable=False),
)
PRIORITY = sa.Table(
    "semantic_school_priority", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("ziyaret_yeri_id", sa.String(40), primary_key=True),
    sa.Column("donem", sa.String(20), primary_key=True),
    sa.Column("puan", sa.Float, nullable=False),
    sa.Column("bilesenler_json", sa.Text, nullable=False),
    sa.Column("gerekce", sa.Text),
    sa.Column("sahip", sa.String(400)),                                # virgülle: okulu kapsamında gören hesaplar
    sa.Column("hesaplandi", sa.DateTime(timezone=True), nullable=False),
)
PLANS = sa.Table(
    "semantic_school_plans", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("sahip", sa.String(120), nullable=False, index=True),
    sa.Column("sahip_ad", sa.String(200)),
    sa.Column("donem", sa.String(20), nullable=False),
    sa.Column("hafta", sa.Date, nullable=False, index=True),           # haftanın pazartesisi
    sa.Column("gun", sa.Date),
    sa.Column("ziyaret_yeri_id", sa.String(40), nullable=False),
    sa.Column("okul_adi", sa.String(300)),
    sa.Column("puan", sa.Float),
    sa.Column("gerekce", sa.Text),
    sa.Column("model_gerekce", sa.Text),
    sa.Column("durum", sa.String(12), nullable=False),                 # oneri | onayli | iptal
    sa.Column("not", sa.Text),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_zamani", sa.DateTime(timezone=True)),
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
    sa.Column("guncelleyen", sa.String(120)),
    sa.Column("guncelleme", sa.DateTime(timezone=True)),
)
DEALER_LINKS = sa.Table(
    "semantic_school_dealer_links", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("ziyaret_yeri_id", sa.String(40), nullable=False, index=True),
    sa.Column("logo_clientref", sa.String(40)),
    sa.Column("crm_account_id", sa.String(40)),
    sa.Column("cari_kodu", sa.String(60)),
    sa.Column("bayi_adi", sa.String(300)),
    sa.Column("kaynak", sa.String(10), nullable=False),                # gecmis | oneri | elle
    sa.Column("durum", sa.String(12), nullable=False),                 # oneri | onayli | reddedildi
    sa.Column("puan", sa.Float),
    sa.Column("gerekce", sa.Text),
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("zaman", sa.DateTime(timezone=True)),                    # onay/ret zamanı
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
)
CATALOGS = sa.Table(
    "semantic_school_catalogs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("ziyaret_yeri_id", sa.String(40), nullable=False, index=True),
    sa.Column("okul_adi", sa.String(300)),
    sa.Column("secim_json", sa.Text, nullable=False),                  # süzgeçler (sınıf, fiyat üstü, adet)
    sa.Column("kitaplar_json", sa.Text, nullable=False),               # stok kodu, ad, sınıf, fiyat, stok, uygunluk
    sa.Column("uygun_toplam", sa.Integer),                             # süzgece uyan bütün kitap sayısı
    sa.Column("bayi_json", sa.Text),                                   # PDF'teki temin noktası (onaylı bayi)
    sa.Column("pdf_yolu", sa.String(300)),                             # PDF istek anında üretilir; saklanmaz
    sa.Column("olusturan", sa.String(120), nullable=False),
    sa.Column("olusturma", sa.DateTime(timezone=True), nullable=False),
)
VISIT_DETAILS = sa.Table(
    "semantic_school_visit_details", _md,
    sa.Column("ziyaret_id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("kisi_rolu", sa.String(40)),
    sa.Column("ilgi", sa.String(10)),                                  # yuksek | orta | dusuk
    sa.Column("istenen_kitaplar_json", sa.Text, nullable=False, default="[]"),
    sa.Column("bayi_yonlendirildi", sa.Boolean, nullable=False, default=False),
    sa.Column("yonlendirilen_bayi", sa.String(60)),                    # cari kodu
    sa.Column("sahip_ad", sa.String(200)),
    sa.Column("plan_id", sa.String(32)),
    sa.Column("hatirlatildi", sa.DateTime(timezone=True)),
)
NAME_MATCHES = sa.Table(
    "semantic_school_name_matches", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("metin_anahtar", sa.String(300), primary_key=True),      # il_id|sade okul metni
    sa.Column("ziyaret_yeri_id", sa.String(40)),                       # boş = eşleşmedi
    sa.Column("karar", sa.String(10), nullable=False),                 # evet | hayir | belirsiz
    sa.Column("kaynak", sa.String(10), nullable=False),                # kural | model
    sa.Column("olasilik", sa.Float),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)

_ready: set[int] = set()
_lock = threading.Lock()
#: Bu süreçte yapılan her yazma sayacı artırır; puan önbelleği buna bakar.
VERSION = [0]


def bump() -> None:
    VERSION[0] += 1


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        SAHA_ZIYARET.metadata.create_all(engine, tables=[SAHA_ZIYARET], checkfirst=True)   # M30 önce kurduysa dokunmaz
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


class SchoolError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return datetime.now(TZ).date()


def _iso(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).isoformat()


def local_day(v: Any) -> Optional[str]:
    """Saklanan zaman (UTC; saat dilimsiz gelirse UTC sayılır) → İstanbul günü."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            return v[:10]
    if isinstance(v, datetime):
        return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).astimezone(TZ).date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return None


def _to_shared(v: Any) -> Optional[str]:
    """datetime/date → ortak ziyaret tablosunun biçimi (İstanbul saatiyle metin)."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v).astimezone(TZ).strftime("%Y-%m-%dT%H:%M")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:19]


def _from_shared(v: Any) -> Optional[datetime]:
    """Ortak tablodaki metin zaman → İstanbul saat dilimli datetime (yalnız gün yazılmışsa gün başı)."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=TZ)
    try:
        d = datetime.fromisoformat(str(v)[:16])
    except ValueError:
        return None
    return d.replace(tzinfo=TZ) if d.tzinfo is None else d


def _shared_row(r: dict[str, Any]) -> dict[str, Any]:
    r["gerceklesen"] = _from_shared(r.get("gerceklesen"))
    r["planlanan"] = _from_shared(r.get("planlanan"))
    nd = r.get("sonraki_tarih")
    r["sonraki_tarih"] = date.fromisoformat(str(nd)[:10]) if nd and not isinstance(nd, date) else nd
    r["not"] = r.get("notu")
    return r


def _dstr(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:10] or None


_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_RID = re.compile(r"^[0-9a-f]{32}$")


def school_id(v: Any) -> str:
    t = str(v or "").strip()
    if not _GUID.match(t):
        raise SchoolError("Okul bulunamadı.", 404)
    return t.lower()


def rid(v: Any, what: str = "Kayıt") -> str:
    t = str(v or "").strip()
    if not _RID.match(t):
        raise SchoolError(f"{what} bulunamadı.", 404)
    return t


def _text(v: Any, limit: int, label: str = "Metin") -> Optional[str]:
    t = re.sub(r"[ \t]+", " ", str(v or "")).strip()
    if len(t) > limit:
        raise SchoolError(f"{label} en çok {limit} karakter olabilir.")
    return t or None


def parse_day(v: Any, label: str = "Tarih", required: bool = False) -> Optional[date]:
    if v in (None, ""):
        if required:
            raise SchoolError(f"{label} gerekli.")
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    t = str(v).strip()
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$", t)
    try:
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return date.fromisoformat(t[:10])
    except ValueError:
        raise SchoolError(f"{label} GG.AA.YYYY ya da YYYY-AA-GG biçiminde olmalı.") from None


def parse_when(v: Any, label: str = "Tarih") -> Optional[datetime]:
    """Ekrandan gelen yerel zaman ('2026-10-05T10:30' ya da gün) → UTC."""
    if v in (None, ""):
        return None
    t = str(v).strip()
    try:
        if len(t) <= 10:
            d = parse_day(t, label)
            return datetime(d.year, d.month, d.day, 12, 0, tzinfo=TZ).astimezone(timezone.utc)
        x = datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        raise SchoolError(f"{label} geçersiz.") from None
    if x.tzinfo is None:
        x = x.replace(tzinfo=TZ)
    return x.astimezone(timezone.utc)


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ------------------------------------------------------------------------------------------ metin sadeleştirme

_TR = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u", "ö": "o", "Ö": "o",
                     "ç": "c", "Ç": "c", "â": "a", "î": "i", "û": "u"})


def fold(v: Any) -> str:
    """Karşılaştırma için: Türkçe harfler sade, küçük harf, noktalama boşluk."""
    t = str(v or "").translate(_TR).lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


#: Okul adında yazım farkı: «ilk okulu» = «ilkokulu», «orta okulu» = «ortaokulu», kısaltmalar.
_JOIN = [(r"\bilk okulu\b", "ilkokulu"), (r"\borta okulu\b", "ortaokulu"), (r"\bana okulu\b", "anaokulu"),
         (r"\bilkogretim okulu\b", "ilkokulu"), (r"\bilkogretim\b", "ilkokulu"), (r"\bi o\b", "ilkokulu"),
         (r"\bo o\b", "ortaokulu"), (r"\bmtal\b", "mesleki ve teknik anadolu lisesi"), (r"\ba l\b", "anadolu lisesi"),
         (r"\bihl\b", "imam hatip lisesi"), (r"\bihl\b", "imam hatip lisesi"), (r"\bihoo?\b", "imam hatip ortaokulu")]


def name_key(v: Any) -> str:
    t = fold(v)
    for rx, rep in _JOIN:
        t = re.sub(rx, rep, t)
    return re.sub(r"\s+", " ", t).strip()


def name_score(a: Any, b: Any) -> float:
    """İki okul adının benzerliği (0–1): sade kelime kümelerinin Jaccard oranı; biri ötekinin tamamını içeriyorsa
    ve fark yalnız il/ilçe adıysa yüksek kalır."""
    ta, tb = set(name_key(a).split()), set(name_key(b).split())
    if not ta or not tb:
        return 0.0
    if ta == tb:
        return 1.0
    return len(ta & tb) / len(ta | tb)


# ------------------------------------------------------------------------------------------ kademe ve sınıf

#: Okul kademesi → sınıflar (0 = okul öncesi, 13 = yükseköğretim/yetişkin).
KADEME_GRADES: dict[int, frozenset[int]] = {
    1: frozenset({0}),                    # Anaokulu
    3: frozenset({1, 2, 3, 4}),           # İlkokul
    5: frozenset({5, 6, 7, 8}),           # Ortaokul
    4: frozenset({9, 10, 11, 12}),        # Lise
    2: frozenset(range(1, 13)),           # BİLSEM (1–12. sınıf öğrencileri)
    6: frozenset(),                       # RAM: tanıtım kataloğu yok
}
#: Kademesi boş okulda okul türünden.
OKUL_TURU_GRADES: dict[int, frozenset[int]] = {
    1: frozenset({0}), 9: frozenset(range(1, 9)), 10: frozenset(range(1, 9)),
    2: frozenset(range(9, 13)), 4: frozenset(range(9, 13)), 5: frozenset(range(9, 13)), 6: frozenset(range(5, 13)),
    7: frozenset(range(9, 13)), 8: frozenset(range(9, 13)),
}
UNIVERSITY = frozenset({13})


def grade_label(g: int) -> str:
    return "Okul öncesi" if g == 0 else ("Yetişkin" if g == 13 else f"{g}. sınıf")


def grades_text(gs: Iterable[int]) -> str:
    gs = sorted(set(gs))
    if not gs:
        return "—"
    if gs == [0]:
        return "Okul öncesi"
    if gs == [13]:
        return "Yetişkin"
    parts = []
    if 0 in gs:
        parts.append("Okul öncesi")
    nums = [g for g in gs if 1 <= g <= 12]
    if nums:
        parts.append(f"{nums[0]}.–{nums[-1]}. sınıf" if len(nums) > 1 else f"{nums[0]}. sınıf")
    if 13 in gs:
        parts.append("yetişkin")
    return ", ".join(parts)


def school_grades(kurum_tipi: Optional[int], kademe: Optional[int], okul_turu: Optional[int]) -> frozenset[int]:
    if kurum_tipi == 3:
        return UNIVERSITY
    if kademe in KADEME_GRADES:
        return KADEME_GRADES[kademe]
    return OKUL_TURU_GRADES.get(okul_turu or -1, frozenset())


def book_grades(r: dict[str, Any]) -> frozenset[int]:
    """CRM kitap kartından sınıflar: sınıf bitleri; yoksa yaş bitleri (yaş − 6); yoksa ağırlıklı hedef yaş aralığı;
    o da yoksa hedef kitle «Yetişkin» → 13. Hiçbiri yoksa boş (kademe uygunluğu bilinmiyor)."""
    out: set[int] = set()
    if r.get("new_okuloncesi"):
        out.add(0)
    for n in range(1, 13):
        if r.get(f"new_{n}sinif"):
            out.add(n)
    if out:
        return frozenset(out)
    for a in range(1, 15):
        if r.get(f"new_{a}yas"):
            out.add(0 if a <= 5 else a - 6)
    if out:
        return frozenset(out)
    lo, hi = src.ival(r.get("yas_bas")), src.ival(r.get("yas_bit"))
    if lo is not None and hi is not None and 0 < lo <= hi <= 25:
        for a in range(lo, hi + 1):
            out.add(0 if a <= 5 else (13 if a >= 19 else a - 6))
        return frozenset(out)
    if src.ival(r.get("hedef_kitle")) == 3:
        return UNIVERSITY
    return frozenset()


# ------------------------------------------------------------------------------------------ ayarlar

DEFAULT_WEIGHTS = {"ogrenci": 30, "ziyaret": 25, "gecmis": 15, "kademe": 10, "bolge": 10, "tur": 5, "bayi": 5}
WEIGHT_LABELS = {"ogrenci": "Öğrenci sayısı", "ziyaret": "Son ziyaret", "gecmis": "Geçmiş örnek/satış",
                 "kademe": "Uygun katalog", "bolge": "İlçe gelişmişlik endeksi", "tur": "Özel/vakıf okul",
                 "bayi": "Bağlı bayi"}


def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    """Ayarlar (ekran > ortam > varsayılan). Varsayımlar ölçülünce buradan değişir, kod değişmez."""
    def num(key: str, default: float, lo: float, hi: float) -> float:
        try:
            return max(lo, min(hi, float(str(conf(key, str(default)) or default).replace(",", "."))))
        except ValueError:
            return default

    t = today()
    hist = conf("SCHOOLS_HISTORY_FROM", "") or ""
    try:
        history = date.fromisoformat(hist[:10]) if hist else date(t.year - 3, 9, 1)
    except ValueError:
        history = date(t.year - 3, 9, 1)
    weights = dict(DEFAULT_WEIGHTS)
    raw = conf("SCHOOLS_PRIORITY_WEIGHTS", "") or ""
    if raw.strip():
        try:
            for k, v in json.loads(raw).items():
                if k in weights:
                    weights[k] = max(0.0, float(v))
        except (ValueError, TypeError, AttributeError):
            log.warning("SCHOOLS_PRIORITY_WEIGHTS okunamadı, varsayılan ağırlıklar kullanılıyor")
    tipler = tuple(int(x) for x in re.findall(r"\d+", conf("SCHOOLS_KURUM_TIPLERI", "1") or "1")) or (1,)
    owners = {x.strip() for x in (conf("SCHOOLS_OWNER_RULES", "sahip,il,ziyaret") or "").split(",") if x.strip()}
    return {
        "historyFrom": history.isoformat(),
        "kurumTipleri": list(tipler),
        "dealerMonths": int(num("SCHOOLS_DEALER_MONTHS", 24, 3, 60)),
        "revisitDays": int(num("SCHOOLS_REVISIT_DAYS", 90, 0, 730)),
        "planSize": int(num("SCHOOLS_WEEKLY_PLAN_SIZE", 10, 1, 200)),
        "catalogSize": int(num("SCHOOLS_CATALOG_SIZE", 20, 0, 1000)),
        "minStock": num("SCHOOLS_CATALOG_MIN_STOCK", 1, 0, 1_000_000),
        "nameMatch": num("SCHOOLS_NAME_MATCH", 0.85, 0.5, 1.0),
        "nameAsk": num("SCHOOLS_NAME_ASK", 0.6, 0.3, 1.0),
        "matchBudget": int(num("SCHOOLS_MATCH_BUDGET", 200, 0, 100_000)),
        # Kapalı küme seçim eşikleri (docs/analiz/llm-choose.md): insan görmeden yazılan ad eşleşmesi otomatik kabul,
        # onaya giden öneri (bayi, nottan ilgi/rol) daha gevşek. Gerçek veriyle ölçülünce buradan değişir.
        "autoMinP": num("SCHOOLS_AUTO_MIN_P", 0.90, 0.5, 1.0),
        "autoMinMargin": num("SCHOOLS_AUTO_MIN_MARGIN", 0.50, 0.0, 1.0),
        "suggestMinP": num("SCHOOLS_SUGGEST_MIN_P", 0.70, 0.3, 1.0),
        "suggestMinMargin": num("SCHOOLS_SUGGEST_MIN_MARGIN", 0.30, 0.0, 1.0),
        "conversionMonths": int(num("SCHOOLS_CONVERSION_MONTHS", 3, 1, 12)),
        "weights": weights,
        "owners": sorted(owners),
    }


# ------------------------------------------------------------------------------------------ dönem (akademik yıl)

_TERM = re.compile(r"^(\d{4})-(\d{4})(?:/([12]))?$")


def term_of(d: date) -> str:
    """Akademik dönem: 1. dönem 1 Eylül – 31 Ocak, 2. dönem 1 Şubat – 31 Ağustos."""
    if d.month >= 9:
        return f"{d.year}-{d.year + 1}/1"
    if d.month == 1:
        return f"{d.year - 1}-{d.year}/1"
    return f"{d.year - 1}-{d.year}/2"


def term_range(term: str) -> tuple[date, date]:
    """[başlangıç, bitiş] (bitiş dahil). «2026-2027» bütün akademik yıl."""
    m = _TERM.match((term or "").strip())
    if not m or int(m.group(2)) != int(m.group(1)) + 1:
        raise SchoolError("Dönem «2026-2027/1» ya da «2026-2027» biçiminde olmalı.")
    y = int(m.group(1))
    half = m.group(3)
    if half == "1":
        return date(y, 9, 1), date(y + 1, 1, 31)
    if half == "2":
        return date(y + 1, 2, 1), date(y + 1, 8, 31)
    return date(y, 9, 1), date(y + 1, 8, 31)


# ------------------------------------------------------------------------------------------ model (CRM + Logo dizini)


def _visit_day(v: dict[str, Any]) -> Optional[str]:
    return src.dayiso(v.get("gerceklesen")) or src.dayiso(v.get("baslangic")) or src.dayiso(v.get("olustu"))


def _price_of(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Stok kodu → geçerli satış fiyatı. Genel liste (cari özel kodu boş) önce, birden çok geçerli genel listede en
    düşük; genel liste yoksa en düşük geçerli liste (ekranda hangisi olduğu yazılır)."""
    by: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        code = src.s(r.get("stok_kodu"))
        p = src.num(r.get("fiyat"))
        if code and p is not None and p > 0:
            by.setdefault(code.upper(), []).append(r)
    out: dict[str, dict[str, Any]] = {}
    for code, rs in by.items():
        general = [r for r in rs if not src.s(r.get("cari_kodu_ozel"))]
        pick = min(general or rs, key=lambda r: float(r["fiyat"]))
        out[code] = {"price": round(float(pick["fiyat"]), 2), "list": src.s(pick.get("liste")),
                     "basis": "Logo genel satış listesi" if general else "Logo özel satış listesi (genel liste yok)",
                     "lists": len(rs)}
    return out


class Model:
    """Bir okumanın (snapshot) dizinleri. Salt okunur; portal kayıtları istek anında üstüne bindirilir."""

    def __init__(self, snap: dict[str, Any], settings: dict[str, Any], matches: dict[str, Optional[str]]):
        self.snap = snap
        self.settings = settings
        self._idx: dict[str, tuple[dict[str, frozenset], dict[str, list[str]]]] = {}
        self._memo: dict[str, Optional[str]] = {}
        self.as_of = snap.get("asOf")
        self.warnings = list(snap.get("warnings") or [])
        self.users: dict[str, dict[str, Any]] = {}
        for u in snap.get("users") or []:
            acc = _account(u.get("hesap"))
            if acc:
                self.users[acc] = {"name": src.s(u.get("ad")) or acc, "email": src.s(u.get("eposta"))}
        # ---- okullar
        self.schools: dict[str, dict[str, Any]] = {}
        self.by_il: dict[str, list[str]] = {}
        last_change = None
        for r in snap.get("schools") or []:
            sc = clean_school(r)
            if not sc:
                continue
            self.schools[sc["id"]] = sc
            self.by_il.setdefault(sc["ilId"] or "", []).append(sc["id"])
            if sc["changed"] and (last_change is None or sc["changed"] > last_change):
                last_change = sc["changed"]
        self.list_changed = last_change
        # ---- ilçeler (endeks eşleşmesi)
        self.districts: dict[str, dict[str, Any]] = {}
        for r in snap.get("districts") or []:
            key = f"{fold(r.get('il'))}|{fold(r.get('ilce'))}"
            self.districts[key] = {"id": src.guid(r.get("id")), "il": src.s(r.get("il")), "ilce": src.s(r.get("ilce"))}
        # ---- CRM ziyaretleri
        self.visits: dict[str, list[dict[str, Any]]] = {}
        self.visits_by_name: dict[str, list[dict[str, Any]]] = {}
        self.unmatched_names: dict[str, dict[str, Any]] = {}
        for r in snap.get("visits") or []:
            v = {"id": src.guid(r.get("id")), "name": src.s(r.get("ad")), "type": src.ival(r.get("tip")),
                 "typeLabel": src.VISIT_TYPES.get(src.ival(r.get("tip")) or -1),
                 "form": src.ival(r.get("sekil")), "formLabel": src.VISIT_FORMS.get(src.ival(r.get("sekil")) or -1),
                 "status": src.ival(r.get("durum")), "statusLabel": src.VISIT_STATUS.get(src.ival(r.get("durum")) or -1, "Diğer"),
                 "day": _visit_day(r), "dealerId": src.guid(r.get("bayi_id")), "dealer": src.s(r.get("bayi_adi")),
                 "dealerCode": src.s(r.get("bayi_kodu")), "participants": src.ival(r.get("katilimci")),
                 "sold": src.ival(r.get("satilan")), "owner": _account(r.get("sorumlu_hesap")) or _account(r.get("sahip_hesap")),
                 "ownerName": src.s(r.get("sorumlu_ad")), "schoolText": src.s(r.get("okul_metni")),
                 "ilId": src.guid(r.get("il_id")), "source": "crm", "done": src.ival(r.get("durum")) == src.VISIT_DONE}
            sid = src.guid(r.get("ziyaret_yeri"))
            if sid:
                self.visits.setdefault(sid, []).append(v)
                continue
            text = v["schoolText"]
            if not text:
                continue
            key = f"{v['ilId'] or ''}|{name_key(text)}"
            hit = matches.get(key, "?")
            if hit == "?":
                hit = self._rule_match(v["ilId"], text)
                if hit is None:
                    self.unmatched_names.setdefault(key, {"key": key, "text": text, "ilId": v["ilId"]})
            if hit:
                self.visits_by_name.setdefault(hit, []).append(dict(v, matchedBy="ad"))
        # ---- bayiler (CRM) + Logo cari kartı
        self.clcards: dict[str, dict[str, Any]] = {}
        for r in snap.get("clcards") or []:
            code = src.s(r.get("kod"))
            if code:
                self.clcards[code.upper()] = {"ref": str(r.get("ref")), "code": code, "name": src.s(r.get("ad")),
                                              "city": src.s(r.get("sehir")), "town": src.s(r.get("ilce")),
                                              "phone": src.s(r.get("telefon"))}
        self.dealers: dict[str, dict[str, Any]] = {}          # cari kodu (büyük harf) → bayi
        self.dealer_by_account: dict[str, str] = {}
        for r in snap.get("dealers") or []:
            code = src.s(r.get("cari_kodu"))
            acc = src.guid(r.get("id"))
            if not code:
                continue
            key = code.upper()
            cl = self.clcards.get(key) or {}
            d = {"code": code, "accountId": acc, "name": src.s(r.get("ad")) or cl.get("name"),
                 "channel": src.DEALER_CHANNELS.get(src.ival(r.get("kanal")) or -1),
                 "ilId": src.guid(r.get("il_id")), "il": src.s(r.get("il")) or cl.get("city"),
                 "ilceId": src.guid(r.get("ilce_id")), "ilce": src.s(r.get("ilce")) or cl.get("town"),
                 "phone": src.s(r.get("telefon")) or cl.get("phone"), "email": src.s(r.get("eposta")),
                 "logicalref": src.s(r.get("logicalref")) or cl.get("ref"), "owner": _account(r.get("sahip_hesap"))}
            self.dealers[key] = d
            if acc:
                self.dealer_by_account[acc] = key
        self.dealers_by_il: dict[str, list[str]] = {}
        for key, d in self.dealers.items():
            self.dealers_by_il.setdefault(fold(d["il"]), []).append(key)
        # ---- geçmiş okul–bayi (cari ile ziyaret)
        self.history: list[dict[str, Any]] = []
        for r in snap.get("history") or []:
            self.history.append({"school": src.guid(r.get("ziyaret_yeri")), "accountId": src.guid(r.get("bayi_id")),
                                 "count": src.ival(r.get("adet")) or 0, "last": src.dayiso(r.get("son"))})
        # ---- siparişler: okul adıyla eşleşen firma (CRM'de siparişin okul kolonu yok)
        self.orders: list[dict[str, Any]] = []
        self.orders_by_school: dict[str, list[dict[str, Any]]] = {}
        for r in snap.get("orders") or []:
            o = {"id": src.guid(r.get("id")), "no": src.s(r.get("no")), "type": src.ival(r.get("tip")),
                 "typeLabel": src.ORDER_TYPES.get(src.ival(r.get("tip")) or -1), "status": src.ival(r.get("durum")),
                 "day": src.dayiso(r.get("tarih")) or src.dayiso(r.get("olustu")), "created": src.dayiso(r.get("olustu")),
                 "firm": src.s(r.get("firma")), "firmId": src.guid(r.get("firma_id")), "code": src.s(r.get("cari_kodu")),
                 "ilId": src.guid(r.get("il_id")), "qty": src.num(r.get("adet")), "amount": src.num(r.get("tutar"))}
            self.orders.append(o)
            if o["firm"] and o["ilId"]:
                hit = self._rule_match(o["ilId"], o["firm"])
                if hit:
                    self.orders_by_school.setdefault(hit, []).append(o)
        # ---- kitaplar
        self.stock: dict[str, float] = dict(snap.get("stock") or {})
        self.prices = _price_of(snap.get("prices") or [])
        self.books: list[dict[str, Any]] = []
        for r in snap.get("books") or []:
            code = src.s(r.get("stok_kodu"))
            if not code:
                continue
            key = code.upper()
            price = self.prices.get(key)
            crm_price = src.num(r.get("crm_fiyat"))
            self.books.append({
                "id": src.guid(r.get("id")), "code": code, "title": src.s(r.get("ad")), "grades": book_grades(r),
                "pages": src.ival(r.get("sayfa")), "genres": src.s(r.get("turler")),
                "stock": self.stock.get(key) if self.stock else None,
                "price": price["price"] if price else (round(crm_price, 2) if crm_price else None),
                "priceBasis": price["basis"] if price else ("CRM kitap kartı fiyatı" if crm_price else None),
            })
        self.books_by_code = {b["code"].upper(): b for b in self.books}
        # ---- bayi satışı (Logo)
        self.dealer_items: dict[str, dict[str, float]] = {}
        for r in snap.get("dealerItems") or []:
            c, k = src.s(r.get("cari_kodu")), src.s(r.get("stok_kodu"))
            if c and k:
                m = self.dealer_items.setdefault(c.upper(), {})
                m[k.upper()] = m.get(k.upper(), 0.0) + float(r.get("adet") or 0)
        self.dealer_months: dict[str, dict[int, dict[str, float]]] = {}
        for r in snap.get("dealerMonths") or []:
            c = src.s(r.get("cari_kodu"))
            if c:
                m = self.dealer_months.setdefault(c.upper(), {})
                ay = int(r.get("ay") or 0)
                cur = m.setdefault(ay, {"qty": 0.0, "amount": 0.0})
                cur["qty"] += float(r.get("adet") or 0)
                cur["amount"] += float(r.get("ciro") or 0)
        self.logo_ok = bool(snap.get("firms"))

    # -------------------------------------------------------------- eşleşme
    def _index(self, il_id: str) -> tuple[dict[str, frozenset], dict[str, list[str]]]:
        """İl başına okul adı kelime kümeleri ve kelime → okullar dizini (bir kez kurulur)."""
        hit = self._idx.get(il_id)
        if hit is None:
            toks: dict[str, frozenset] = {}
            inv: dict[str, list[str]] = {}
            for sid in self.by_il.get(il_id, []):
                ts = frozenset(name_key(self.schools[sid]["name"]).split())
                toks[sid] = ts
                for t in ts:
                    inv.setdefault(t, []).append(sid)
            hit = (toks, inv)
            self._idx[il_id] = hit
        return hit

    def _scores(self, il_id: Optional[str], text: str) -> list[tuple[str, float]]:
        """Metnin ildeki okullarla benzerliği; yalnız ortak kelimesi olan okullar hesaplanır (önce seyrek kelimeler)."""
        if not il_id or not text:
            return []
        q = frozenset(name_key(text).split())
        if not q:
            return []
        toks, inv = self._index(il_id)
        n = max(1, len(toks))
        cand: set[str] = set()
        for t in q:
            lst = inv.get(t) or []
            if lst and len(lst) <= max(50, n * 0.05):
                cand.update(lst)
        if not cand:
            for t in q:
                cand.update(inv.get(t) or [])
        out = []
        for sid in cand:
            ts = toks[sid]
            out.append((sid, 1.0 if ts == q else len(ts & q) / len(ts | q)))
        out.sort(key=lambda x: -x[1])
        return out

    def _rule_match(self, il_id: Optional[str], text: str) -> Optional[str]:
        """Aynı ildeki okullar arasında ad benzerliği eşiği geçen tek aday. Eşik altı ya da iki yakın aday → None."""
        key = f"{il_id or ''}|{name_key(text)}"
        if key in self._memo:
            return self._memo[key]
        sc = self._scores(il_id, text)
        best = sc[0] if sc else None
        second = sc[1][1] if len(sc) > 1 else 0.0
        hit = best[0] if best and best[1] >= self.settings["nameMatch"] and best[1] - second >= 0.1 else None
        self._memo[key] = hit
        return hit

    def candidates_for(self, il_id: Optional[str], text: str) -> list[tuple[str, float]]:
        return [x for x in self._scores(il_id, text) if x[1] >= self.settings["nameAsk"]]

    # -------------------------------------------------------------- okul yardımcıları
    def crm_visits(self, sid: str) -> list[dict[str, Any]]:
        return (self.visits.get(sid) or []) + (self.visits_by_name.get(sid) or [])

    def fitting_books(self, grades: Iterable[int], *, min_stock: Optional[float] = None) -> list[dict[str, Any]]:
        gs = set(grades)
        if not gs:
            return []
        ms = self.settings["minStock"] if min_stock is None else min_stock
        out = []
        for b in self.books:
            if not (b["grades"] & gs):
                continue
            if self.stock and (b["stock"] is None or b["stock"] < ms):
                continue
            out.append(b)
        return out

    def dealer_grade_sales(self, code: str, grades: Iterable[int]) -> float:
        gs = set(grades)
        items = self.dealer_items.get(code.upper()) or {}
        total = 0.0
        for k, q in items.items():
            b = self.books_by_code.get(k)
            if b and b["grades"] & gs:
                total += q
        return total

    def il_popularity(self, il: Optional[str]) -> dict[str, float]:
        """İldeki bayilerin kitap başına satışı (katalog sıralaması için)."""
        out: dict[str, float] = {}
        for code in self.dealers_by_il.get(fold(il), []):
            for k, q in (self.dealer_items.get(code) or {}).items():
                out[k] = out.get(k, 0.0) + q
        return out


def _account(v: Any) -> Optional[str]:
    t = src.s(v)
    if not t:
        return None
    t = t.rsplit("\\", 1)[-1].split("@", 1)[0].strip().lower()
    return t or None


def clean_school(r: dict[str, Any]) -> Optional[dict[str, Any]]:
    sid = src.guid(r.get("id"))
    if not sid:
        return None
    kt, kademe, tur = src.ival(r.get("kurum_tipi")), src.ival(r.get("kademe")), src.ival(r.get("okul_turu"))
    ogrenci = r.get("ogrenci")
    if kt == 3:
        ogrenci = r.get("toplam_ogrenci")
    name = src.s(r.get("okul_adi")) or src.s(r.get("kurum_adi")) or src.s(r.get("kod")) or "Adı girilmemiş"
    grades = school_grades(kt, kademe, tur)
    return {
        "id": sid, "code": src.s(r.get("kod")), "name": name,
        "kurumTipi": src.KURUM_TIPI.get(kt or -1), "kurumTipiKod": kt,
        "kurumTuru": src.KURUM_TURU.get(src.ival(r.get("kurum_turu")) or -1), "kurumTuruKod": src.ival(r.get("kurum_turu")),
        "okulTuru": src.OKUL_TURU.get(tur or -1), "kademe": src.KADEME.get(kademe or -1), "kademeKod": kademe,
        "grades": grades, "gradesText": grades_text(grades),
        "students": ogrenci if isinstance(ogrenci, int) else src.ival(ogrenci),
        "teachers": src.ival(r.get("ogretmen")), "classrooms": src.ival(r.get("derslik")),
        "libraryBooks": src.ival(r.get("kitap_sayisi")), "hall": src.s(r.get("konferans")),
        "phone": src.s(r.get("telefon")), "address": src.s(r.get("adres")),
        "ilId": src.guid(r.get("il_id")), "il": src.s(r.get("il")),
        "ilceId": src.guid(r.get("ilce_id")), "ilce": src.s(r.get("ilce")), "ilceKodu": src.s(r.get("ilce_kodu")),
        "owner": _account(r.get("sahip_hesap")), "ilOwner": _account(r.get("il_temsilci_hesap")),
        "changed": src.dayiso(r.get("degisti")), "created": src.dayiso(r.get("olustu")),
    }


# ------------------------------------------------------------------------------------------ bağlam (elle yükleme)

CONTEXT_KINDS = {"ilce_endeks": "İlçe gelişmişlik endeksi", "takvim": "Akademik takvim"}
CAL_KINDS = {"tatil": "Tatil", "sinav": "Sınav haftası", "diger": "Diğer"}


def _hdr(h: str) -> str:
    return fold(h).replace(" ", "")


def read_table(body: dict[str, Any]) -> list[dict[str, str]]:
    """CSV metni (`csv`) ya da Excel dosyası (`xlsx`, base64) → başlık adı sade satırlar."""
    if body.get("xlsx"):
        try:
            import openpyxl
        except ImportError as e:  # pragma: no cover
            raise SchoolError("Excel okuyucu sunucuda kurulu değil; dosyayı CSV olarak yükleyin.") from e
        try:
            raw = base64.b64decode(str(body["xlsx"]).split(",", 1)[-1], validate=False)
            wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as e:  # noqa: BLE001
            raise SchoolError("Excel dosyası okunamadı.") from e
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        head = next(it, None)
        if not head:
            raise SchoolError("Dosya boş.")
        keys = [_hdr(str(h or "")) for h in head]
        out = []
        for row in it:
            if row is None or all(c in (None, "") for c in row):
                continue
            out.append({k: ("" if c is None else (c.isoformat()[:10] if isinstance(c, (date, datetime)) else str(c)))
                        for k, c in zip(keys, row) if k})
        return out
    text = str(body.get("csv") or "")
    if not text.strip():
        raise SchoolError("Dosya boş.")
    text = text.lstrip("﻿")
    first = text.splitlines()[0]
    delim = ";" if first.count(";") >= first.count(",") and ";" in first else ("\t" if "\t" in first else ",")
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    head = next(reader, None) or []
    keys = [_hdr(h) for h in head]
    out = []
    for row in reader:
        if not row or all(not c.strip() for c in row):
            continue
        out.append({k: c.strip() for k, c in zip(keys, row) if k})
    return out


def _pick(row: dict[str, str], *names: str) -> str:
    for n in names:
        if row.get(n, "").strip():
            return row[n].strip()
    return ""


def _decimal(v: str) -> Optional[float]:
    t = (v or "").strip().replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def parse_context(tur: str, rows: list[dict[str, str]], districts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Yüklenen satırlar → (anahtar, değer) listesi + okunamayan/eşleşmeyen satırlar. Hiçbir satır sessizce düşmez:
    düşen her satır nedeniyle raporda."""
    items: list[tuple[str, dict[str, Any]]] = []
    bad: list[dict[str, Any]] = []
    if tur == "ilce_endeks":
        for n, r in enumerate(rows, start=2):
            il, ilce = _pick(r, "il", "ili", "sehir"), _pick(r, "ilce", "ilcesi")
            val = _decimal(_pick(r, "endeks", "deger", "puan", "skor", "segeendeksi"))
            if not il or not ilce or val is None:
                bad.append({"satir": n, "neden": "il, ilçe ya da endeks okunamadı", "veri": r})
                continue
            key = f"{fold(il)}|{fold(ilce)}"
            d = districts.get(key)
            items.append((key, {"il": il, "ilce": ilce, "endeks": val, "yil": _pick(r, "yil", "donem") or None,
                                "crmIlceId": d["id"] if d else None}))
            if not d:
                bad.append({"satir": n, "neden": "CRM ilçe listesinde bulunamadı (yine de kaydedildi)", "veri": r})
    elif tur == "takvim":
        for n, r in enumerate(rows, start=2):
            try:
                a = parse_day(_pick(r, "baslangic", "baslangictarihi", "ilkgun"), "Başlangıç", required=True)
                b = parse_day(_pick(r, "bitis", "bitistarihi", "songun") or _pick(r, "baslangic", "baslangictarihi"), "Bitiş",
                              required=True)
            except SchoolError as e:
                bad.append({"satir": n, "neden": str(e), "veri": r})
                continue
            if b < a:
                bad.append({"satir": n, "neden": "bitiş başlangıçtan önce", "veri": r})
                continue
            kind = fold(_pick(r, "tur", "tip")) or "tatil"
            kind = "sinav" if kind.startswith("sinav") else ("tatil" if kind.startswith("tatil") else "diger")
            il = _pick(r, "il", "ili")
            items.append((f"{a.isoformat()}..{b.isoformat()}|{fold(il) or '*'}",
                          {"baslangic": a.isoformat(), "bitis": b.isoformat(), "tur": kind,
                           "ad": _pick(r, "ad", "aciklama", "adi") or CAL_KINDS[kind], "il": il or None}))
    else:
        raise SchoolError("Yükleme türü «ilce_endeks» ya da «takvim» olmalı.")
    return {"items": items, "bad": bad}


def save_context(engine: sa.engine.Engine, tenant: str, user: str, tur: str, items: list[tuple[str, dict[str, Any]]],
                 source: Optional[str], source_day: Optional[date]) -> str:
    """Yeni yükleme o türün önceki yüklemesinin yerine geçer (eski satırlar pasif kalır, silinmez)."""
    up = uuid.uuid4().hex
    at = now_utc()
    with engine.begin() as c:
        c.execute(CONTEXT.update().where(CONTEXT.c.tenant_id == tenant, CONTEXT.c.tur == tur, CONTEXT.c.aktif.is_(True))
                  .values(aktif=False))
        if items:
            c.execute(CONTEXT.insert(), [
                {"id": uuid.uuid4().hex, "tenant_id": tenant, "tur": tur, "anahtar": k[:200],
                 "deger_json": json.dumps(v, ensure_ascii=False), "kaynak": source, "kaynak_tarihi": source_day,
                 "yukleme_id": up, "aktif": True, "yukleyen": user, "yukleme_zamani": at} for k, v in items])
    bump()
    return up


def context_stmt(tenant: str) -> Any:
    """Yüklü bağlam (ilçe endeksi, akademik takvim): etkin yüklemenin satırları."""
    return sa.select(CONTEXT).where(CONTEXT.c.tenant_id == tenant, CONTEXT.c.aktif.is_(True))


def load_context(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    out: dict[str, Any] = {"ilce_endeks": {}, "takvim": [], "uploads": {}}
    with engine.connect() as c:
        for r in c.execute(context_stmt(tenant)).mappings():
            v = json.loads(r["deger_json"])
            if r["tur"] == "ilce_endeks":
                out["ilce_endeks"][r["anahtar"]] = v
            elif r["tur"] == "takvim":
                out["takvim"].append(v)
            up = out["uploads"].setdefault(r["tur"], {"kind": r["tur"], "label": CONTEXT_KINDS.get(r["tur"]), "rows": 0,
                                                      "source": r["kaynak"], "sourceDay": _dstr(r["kaynak_tarihi"]),
                                                      "by": r["yukleyen"], "at": _iso(r["yukleme_zamani"])})
            up["rows"] += 1
    out["takvim"].sort(key=lambda x: x["baslangic"])
    vals = [v["endeks"] for v in out["ilce_endeks"].values() if isinstance(v.get("endeks"), (int, float))]
    out["endeksRange"] = (min(vals), max(vals)) if vals else None
    return out


def conflicts(ctx: dict[str, Any], a: date, b: date, il: Optional[str]) -> list[dict[str, Any]]:
    """[a, b] aralığına düşen tatil/sınav günleri; il boşsa bütün illere uyanlar."""
    out = []
    fil = fold(il)
    for e in ctx.get("takvim") or []:
        if e["bitis"] < a.isoformat() or e["baslangic"] > b.isoformat():
            continue
        if e.get("il") and fold(e["il"]) != fil:
            continue
        out.append({"from": e["baslangic"], "to": e["bitis"], "kind": e["tur"], "kindLabel": CAL_KINDS.get(e["tur"], e["tur"]),
                    "name": e.get("ad"), "il": e.get("il")})
    return out


# ------------------------------------------------------------------------------------------ öncelik puanı


def _ref_students(model: Model) -> dict[Optional[int], float]:
    """Kurum tipi başına öğrenci sayısının 90. yüzdeliği: puan buna göre ölçeklenir (en kalabalık %10 tam puan)."""
    by: dict[Optional[int], list[int]] = {}
    for sc in model.schools.values():
        if isinstance(sc["students"], int) and sc["students"] > 0:
            by.setdefault(sc["kurumTipiKod"], []).append(sc["students"])
    out = {}
    for k, vs in by.items():
        vs.sort()
        out[k] = float(vs[min(len(vs) - 1, int(len(vs) * 0.9))])
    return out


def score_school(sc: dict[str, Any], *, weights: dict[str, float], ref_students: float, last_visit: Optional[str],
                 orders: list[dict[str, Any]], fitting: int, endeks: Optional[float], endeks_range: Optional[tuple],
                 has_dealer: bool, now: date) -> dict[str, Any]:
    """Kural puanı (0–100 ağırlıklarla) ve bileşenleri. Her bileşen: puan, en çok, açıklama. Rakam modelden gelmez."""
    parts: list[dict[str, Any]] = []

    def add(key: str, ratio: float, note: str) -> None:
        w = float(weights.get(key, 0))
        parts.append({"key": key, "label": WEIGHT_LABELS[key], "points": round(w * max(0.0, min(1.0, ratio)), 1),
                      "max": w, "note": note})

    st = sc.get("students")
    if isinstance(st, int) and st > 0 and ref_students > 0:
        add("ogrenci", st / ref_students, f"{st:,} öğrenci".replace(",", "."))
    else:
        add("ogrenci", 0, "öğrenci sayısı bilinmiyor")
    if not last_visit:
        add("ziyaret", 1, "hiç ziyaret edilmemiş")
    else:
        days = (now - date.fromisoformat(last_visit)).days
        ratio = 0.8 if days > 365 else (0.4 if days > 180 else 0.0)
        add("ziyaret", ratio, f"son ziyaret {days} gün önce")
    cut = (now - timedelta(days=730)).isoformat()
    recent = [o for o in orders if (o.get("created") or o.get("day") or "") >= cut]
    if any(o["type"] == 13 for o in recent):
        add("gecmis", 1, "son 2 yılda okul satışı var")
    elif any(o["type"] in (10, 11) for o in recent):
        add("gecmis", 2 / 3, "son 2 yılda örnek gönderilmiş, satış yok")
    else:
        add("gecmis", 0, "son 2 yılda örnek/satış siparişi yok")
    if not sc["grades"]:
        add("kademe", 0, "kademe/tür boş: katalog seçilemiyor")
    else:
        add("kademe", 1 if fitting > 0 else 0, f"{fitting} uygun ve stokta kitap" if fitting else "uygun ve stokta kitap yok")
    if endeks is not None and endeks_range:
        lo, hi = endeks_range
        add("bolge", (endeks - lo) / (hi - lo) if hi > lo else 1, f"ilçe endeksi {endeks:g}")
    else:
        add("bolge", 0, "ilçe endeksi yüklenmedi" if not endeks_range else "ilçenin endeksi yüklü listede yok")
    add("tur", 1 if sc.get("kurumTuruKod") in (2, 3) else 0, sc.get("kurumTuru") or "kurum türü boş")
    add("bayi", 1 if has_dealer else 0, "onaylı bağlı bayi var" if has_dealer else "bağlı bayi yok")
    total = round(sum(p["points"] for p in parts), 1)
    top = sorted((p for p in parts if p["points"] > 0), key=lambda p: -p["points"])[:3]
    reason = "; ".join(p["note"] for p in top) if top else "öncelik sinyali yok"
    return {"score": total, "parts": parts, "reason": reason[0].upper() + reason[1:]}


# ------------------------------------------------------------------------------------------ portal kayıtları: ziyaret

ROLES = {"mudur": "Müdür", "mudur-yardimcisi": "Müdür yardımcısı", "kutuphane": "Kütüphane sorumlusu",
         "turkce": "Türkçe / edebiyat öğretmeni", "sinif": "Sınıf öğretmeni", "rehber": "Rehber öğretmen",
         "brans": "Branş öğretmeni", "diger": "Diğer"}
INTEREST = {"yuksek": "Yüksek", "orta": "Orta", "dusuk": "Düşük"}
INTEREST_TONE = {"yuksek": "olumlu", "orta": "notr", "dusuk": "olumsuz"}
VISIT_STATES = {"planlandi": "Planlandı", "yapildi": "Yapıldı", "iptal": "İptal"}


def visit_values(body: dict[str, Any], model: Optional[Model], now: date) -> dict[str, Any]:
    durum = str(body.get("durum") or "yapildi")
    if durum not in VISIT_STATES:
        raise SchoolError("Ziyaret durumu geçersiz.")
    when = parse_when(body.get("gerceklesen") or body.get("tarih"), "Ziyaret tarihi")
    if durum == "yapildi":
        when = when or now_utc()
        if when.astimezone(TZ).date() > now:
            raise SchoolError("Yapılan ziyaretin tarihi ileri bir gün olamaz.")
    planned = parse_when(body.get("planlanan"), "Planlanan tarih")
    if durum == "planlandi" and not planned:
        planned = when
        when = None
    ilgi = str(body.get("ilgi") or "") or None
    if ilgi is not None and ilgi not in INTEREST:
        raise SchoolError("İlgi düzeyi yüksek, orta ya da düşük olmalı.")
    if durum == "yapildi" and ilgi is None:
        raise SchoolError("İlgi düzeyini seçin.")
    role = str(body.get("kisiRolu") or "") or None
    if role is not None and role not in ROLES:
        raise SchoolError("Görüşülen kişinin rolü geçersiz.")
    books = body.get("istenenKitaplar") or []
    if not isinstance(books, list):
        raise SchoolError("İstenen kitaplar liste olmalı.")
    clean_books = []
    for b in books:
        code = str((b.get("code") if isinstance(b, dict) else b) or "").strip()
        if not code:
            continue
        known = model.books_by_code.get(code.upper()) if model else None
        clean_books.append({"code": code[:60], "title": (known or {}).get("title") or (b.get("title") if isinstance(b, dict) else None),
                            "qty": src.ival(b.get("qty")) if isinstance(b, dict) else None})
    nxt_day = parse_day(body.get("sonrakiTarih"), "Sonraki adım tarihi")
    nxt = _text(body.get("sonrakiAdim"), 300, "Sonraki adım")
    if nxt_day and not nxt:
        raise SchoolError("Sonraki adımı bir cümleyle yazın.")
    routed = bool(body.get("bayiYonlendirildi"))
    dealer = str(body.get("bayi") or "").strip() or None
    if routed and not dealer:
        raise SchoolError("Yönlendirilen bayiyi seçin.")
    escort = str(body.get("eslikEdenBayi") or "").strip() or None
    escort_ref = None
    if escort and model:
        d = model.dealers.get(escort.upper())
        escort_ref = (d or {}).get("logicalref") or escort
    elif escort:
        escort_ref = escort
    return {"durum": durum, "gerceklesen": when, "planlanan": planned, "not": _text(body.get("not"), 4000, "Not"),
            "ton": INTEREST_TONE.get(ilgi or ""), "sonraki_adim": nxt, "sonraki_tarih": nxt_day,
            "gizli": bool(body.get("gizli")), "eslik_eden_bayi": (escort_ref or "")[:40] or None,
            "_details": {"kisi_rolu": role, "ilgi": ilgi, "istenen_kitaplar_json": json.dumps(clean_books, ensure_ascii=False),
                         "bayi_yonlendirildi": routed, "yonlendirilen_bayi": dealer[:60] if dealer else None,
                         "plan_id": str(body.get("planId") or "")[:32] or None}}


def add_visit(engine: sa.engine.Engine, tenant: str, user: str, display: str, sid: str, vals: dict[str, Any]) -> str:
    details = vals.pop("_details")
    vid = uuid.uuid4().hex
    at = now_utc()
    with engine.begin() as c:
        row = {**vals, "notu": vals.pop("not", None), "gerceklesen": _to_shared(vals.get("gerceklesen")),
               "planlanan": _to_shared(vals.get("planlanan")), "sonraki_tarih": _to_shared(vals.get("sonraki_tarih"))}
        row.pop("not", None)
        c.execute(SAHA_ZIYARET.insert().values(id=vid, tenant_id=tenant, tur="okul", hedef_kimlik=sid, sahip=user,
                                               olusturan=user, olusturma=at, **row))
        c.execute(VISIT_DETAILS.insert().values(ziyaret_id=vid, tenant_id=tenant, sahip_ad=display, **details))
    bump()
    return vid


def visits_stmt(tenant: str, *, school: Optional[str] = None, owner: Optional[str] = None, vid: Optional[str] = None,
                since: Optional[datetime] = None) -> Any:
    """Portal okul ziyaretleri (ortak saha ziyaret tablosu + okul ayrıntısı); uçta çalışan ifade."""
    q = (sa.select(SAHA_ZIYARET, VISIT_DETAILS.c.kisi_rolu, VISIT_DETAILS.c.ilgi, VISIT_DETAILS.c.istenen_kitaplar_json,
                   VISIT_DETAILS.c.bayi_yonlendirildi, VISIT_DETAILS.c.yonlendirilen_bayi, VISIT_DETAILS.c.sahip_ad,
                   VISIT_DETAILS.c.plan_id, VISIT_DETAILS.c.hatirlatildi)
         .select_from(SAHA_ZIYARET.outerjoin(VISIT_DETAILS, VISIT_DETAILS.c.ziyaret_id == SAHA_ZIYARET.c.id))
         .where(SAHA_ZIYARET.c.tenant_id == tenant, SAHA_ZIYARET.c.tur == "okul"))
    if school:
        q = q.where(SAHA_ZIYARET.c.hedef_kimlik == school)
    if owner:
        q = q.where(SAHA_ZIYARET.c.sahip == owner)
    if vid:
        q = q.where(SAHA_ZIYARET.c.id == vid)
    if since:
        # Metin zamanlar aynı biçimde (İstanbul, YYYY-AA-GG[THH:MM]); sözlük sırası zaman sırasıdır.
        edge = _to_shared(since)
        q = q.where(sa.or_(SAHA_ZIYARET.c.gerceklesen >= edge, SAHA_ZIYARET.c.planlanan >= edge))
    return q.order_by(SAHA_ZIYARET.c.olusturma.desc())


def load_visits(engine: sa.engine.Engine, tenant: str, *, school: Optional[str] = None, owner: Optional[str] = None,
                vid: Optional[str] = None, since: Optional[datetime] = None) -> list[dict[str, Any]]:
    q = visits_stmt(tenant, school=school, owner=owner, vid=vid, since=since)
    with engine.connect() as c:
        return [_shared_row(dict(r)) for r in c.execute(q).mappings()]


def visit_view(r: dict[str, Any], *, viewer: str, can_all: bool) -> dict[str, Any]:
    """Portal ziyareti ekran biçimi. Gizli işaretli notun metni yalnız yazana gider."""
    mine = r["sahip"] == viewer
    hidden = bool(r.get("gizli")) and not mine
    when = r.get("gerceklesen") or r.get("planlanan")
    try:
        books = json.loads(r.get("istenen_kitaplar_json") or "[]")
    except ValueError:
        books = []
    return {"id": r["id"], "source": "portal", "school": r["hedef_kimlik"], "owner": r["sahip"],
            "ownerName": r.get("sahip_ad") or r["sahip"], "mine": mine,
            "state": r["durum"], "stateLabel": VISIT_STATES.get(r["durum"], r["durum"]),
            "at": _iso(when), "day": local_day(when),
            "note": None if hidden else r.get("not"), "hidden": hidden, "secret": bool(r.get("gizli")),
            "tone": r.get("ton"), "interest": r.get("ilgi"), "interestLabel": INTEREST.get(r.get("ilgi") or ""),
            "role": r.get("kisi_rolu"), "roleLabel": ROLES.get(r.get("kisi_rolu") or ""),
            "books": books, "routed": bool(r.get("bayi_yonlendirildi")), "routedDealer": r.get("yonlendirilen_bayi"),
            "escort": r.get("eslik_eden_bayi"), "next": r.get("sonraki_adim"), "nextDay": _dstr(r.get("sonraki_tarih")),
            "planId": r.get("plan_id"), "created": _iso(r.get("olusturma"))}


def last_visits_stmt(tenant: str) -> Any:
    """Okul başına portalda yapılan son ziyaret."""
    return (sa.select(SAHA_ZIYARET.c.hedef_kimlik, sa.func.max(SAHA_ZIYARET.c.gerceklesen).label("son_ziyaret"))
            .where(SAHA_ZIYARET.c.tenant_id == tenant, SAHA_ZIYARET.c.tur == "okul", SAHA_ZIYARET.c.durum == "yapildi")
            .group_by(SAHA_ZIYARET.c.hedef_kimlik))


def last_visits(engine: sa.engine.Engine, tenant: str) -> dict[str, str]:
    """Okul → portalda yapılan son ziyaret günü."""
    q = last_visits_stmt(tenant)
    out = {}
    with engine.connect() as c:
        for sid, at in c.execute(q):
            day = local_day(_from_shared(at))
            if day:
                out[sid] = day
    return out


def portal_owners(engine: sa.engine.Engine, tenant: str) -> dict[str, set[str]]:
    """Okul → portalda o okula ziyaret ya da plan yazmış hesaplar (kapsam için)."""
    out: dict[str, set[str]] = {}
    with engine.connect() as c:
        for sid, who in c.execute(sa.select(SAHA_ZIYARET.c.hedef_kimlik, SAHA_ZIYARET.c.sahip).distinct()
                                  .where(SAHA_ZIYARET.c.tenant_id == tenant, SAHA_ZIYARET.c.tur == "okul")):
            out.setdefault(sid, set()).add(who)
        for sid, who in c.execute(sa.select(PLANS.c.ziyaret_yeri_id, PLANS.c.sahip).distinct()
                                  .where(PLANS.c.tenant_id == tenant, PLANS.c.durum != "iptal")):
            out.setdefault(sid, set()).add(who)
    return out


def mark_reminded(engine: sa.engine.Engine, ids: list[str]) -> None:
    if not ids:
        return
    with engine.begin() as c:
        c.execute(VISIT_DETAILS.update().where(VISIT_DETAILS.c.ziyaret_id.in_(ids)).values(hatirlatildi=now_utc()))


# ------------------------------------------------------------------------------------------ portal kayıtları: plan

PLAN_STATES = {"oneri": "Öneri", "onayli": "Onaylı", "iptal": "İptal"}


def plans_stmt(tenant: str, *, week: Optional[date] = None, owner: Optional[str] = None, since: Optional[date] = None,
               until: Optional[date] = None, pid: Optional[str] = None, school: Optional[str] = None) -> Any:
    """Haftalık ziyaret planı satırları; uçta çalışan ifade."""
    q = sa.select(PLANS).where(PLANS.c.tenant_id == tenant)
    if school:
        q = q.where(PLANS.c.ziyaret_yeri_id == school)
    if week:
        q = q.where(PLANS.c.hafta == week)
    if owner:
        q = q.where(PLANS.c.sahip == owner)
    if since:
        q = q.where(PLANS.c.hafta >= monday(since))
    if until:
        q = q.where(PLANS.c.hafta <= until)
    if pid:
        q = q.where(PLANS.c.id == pid)
    return q.order_by(PLANS.c.gun, PLANS.c.puan.desc())


def load_plans(engine: sa.engine.Engine, tenant: str, *, week: Optional[date] = None, owner: Optional[str] = None,
               since: Optional[date] = None, until: Optional[date] = None, pid: Optional[str] = None) -> list[dict[str, Any]]:
    q = plans_stmt(tenant, week=week, owner=owner, since=since, until=until, pid=pid)
    with engine.connect() as c:
        return [dict(r) for r in c.execute(q).mappings()]


def insert_plans(engine: sa.engine.Engine, rows: list[dict[str, Any]]) -> None:
    if rows:
        with engine.begin() as c:
            c.execute(PLANS.insert(), rows)
        bump()


def update_plan(engine: sa.engine.Engine, tenant: str, pid: str, values: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as c:
        c.execute(PLANS.update().where(PLANS.c.tenant_id == tenant, PLANS.c.id == pid).values(**values))
    bump()
    rows = load_plans(engine, tenant, pid=pid)
    return rows[0]


def plan_view(r: dict[str, Any], realized: Optional[dict[str, Any]], conflicts_: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": r["id"], "owner": r["sahip"], "ownerName": r.get("sahip_ad") or r["sahip"], "term": r["donem"],
            "week": _dstr(r["hafta"]), "day": _dstr(r.get("gun")), "school": r["ziyaret_yeri_id"], "schoolName": r.get("okul_adi"),
            "score": r.get("puan"), "reason": r.get("gerekce"), "aiReason": r.get("model_gerekce"),
            "state": r["durum"], "stateLabel": PLAN_STATES.get(r["durum"], r["durum"]), "note": r.get("not"),
            "approvedBy": r.get("onaylayan"), "approvedAt": _iso(r.get("onay_zamani")),
            "realized": realized, "conflicts": conflicts_}


# ------------------------------------------------------------------------------------------ portal kayıtları: bayi bağı

LINK_SOURCES = {"gecmis": "CRM'deki ortak ziyaret", "oneri": "Zeki AI önerisi", "elle": "Elle eklendi"}
LINK_STATES = {"oneri": "Onay bekliyor", "onayli": "Onaylı", "reddedildi": "Reddedildi"}


def links_stmt(tenant: str, *, school: Optional[str] = None, state: Optional[str] = None, lid: Optional[str] = None) -> Any:
    """Okul–bayi eşleşmeleri (öneri/onaylı/red); uçta çalışan ifade."""
    q = sa.select(DEALER_LINKS).where(DEALER_LINKS.c.tenant_id == tenant)
    if school:
        q = q.where(DEALER_LINKS.c.ziyaret_yeri_id == school)
    if state:
        q = q.where(DEALER_LINKS.c.durum == state)
    if lid:
        q = q.where(DEALER_LINKS.c.id == lid)
    return q.order_by(DEALER_LINKS.c.olusturma.desc())


def load_links(engine: sa.engine.Engine, tenant: str, *, school: Optional[str] = None, state: Optional[str] = None,
               lid: Optional[str] = None) -> list[dict[str, Any]]:
    with engine.connect() as c:
        return [dict(r) for r in c.execute(links_stmt(tenant, school=school, state=state, lid=lid)).mappings()]


def approved_links(engine: sa.engine.Engine, tenant: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in load_links(engine, tenant, state="onayli"):
        out.setdefault(r["ziyaret_yeri_id"], []).append(r)
    return out


def link_view(r: dict[str, Any], model: Optional[Model]) -> dict[str, Any]:
    d = (model.dealers.get((r.get("cari_kodu") or "").upper()) if model else None) or {}
    return {"id": r["id"], "school": r["ziyaret_yeri_id"], "code": r.get("cari_kodu"), "name": r.get("bayi_adi") or d.get("name"),
            "accountId": r.get("crm_account_id"), "logicalref": r.get("logo_clientref"),
            "source": r["kaynak"], "sourceLabel": LINK_SOURCES.get(r["kaynak"], r["kaynak"]),
            "state": r["durum"], "stateLabel": LINK_STATES.get(r["durum"], r["durum"]), "score": r.get("puan"),
            "reason": r.get("gerekce"), "decidedBy": r.get("onaylayan"), "decidedAt": _iso(r.get("zaman")),
            "createdBy": r.get("olusturan"), "created": _iso(r.get("olusturma")),
            "il": d.get("il"), "ilce": d.get("ilce"), "phone": d.get("phone"), "email": d.get("email"), "channel": d.get("channel")}


def add_link(engine: sa.engine.Engine, tenant: str, user: str, sid: str, dealer: dict[str, Any], *, kaynak: str, durum: str,
             puan: Optional[float], gerekce: Optional[str], approver: Optional[str] = None) -> dict[str, Any]:
    """Aynı okul + cari için bekleyen/onaylı bir bağ varsa yenisi açılmaz, o döner."""
    code = dealer["code"]
    with engine.begin() as c:
        cur = c.execute(sa.select(DEALER_LINKS).where(
            DEALER_LINKS.c.tenant_id == tenant, DEALER_LINKS.c.ziyaret_yeri_id == sid, DEALER_LINKS.c.cari_kodu == code,
            DEALER_LINKS.c.durum.in_(("oneri", "onayli")))).mappings().first()
        if cur:
            return dict(cur)
        row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "ziyaret_yeri_id": sid, "logo_clientref": dealer.get("logicalref"),
               "crm_account_id": dealer.get("accountId"), "cari_kodu": code, "bayi_adi": dealer.get("name"), "kaynak": kaynak,
               "durum": durum, "puan": puan, "gerekce": gerekce, "onaylayan": approver,
               "zaman": now_utc() if durum != "oneri" else None, "olusturan": user, "olusturma": now_utc()}
        c.execute(DEALER_LINKS.insert().values(**row))
    bump()
    return row


def decide_link(engine: sa.engine.Engine, tenant: str, lid: str, user: str, approve: bool, note: Optional[str]) -> dict[str, Any]:
    rows = load_links(engine, tenant, lid=lid)
    if not rows:
        raise SchoolError("Eşleşme bulunamadı.", 404)
    r = rows[0]
    reason = r.get("gerekce") or ""
    if note:
        reason = (reason + "\n" if reason else "") + f"Karar notu: {note}"
    with engine.begin() as c:
        c.execute(DEALER_LINKS.update().where(DEALER_LINKS.c.id == lid).values(
            durum="onayli" if approve else "reddedildi", onaylayan=user, zaman=now_utc(), gerekce=reason or None))
    bump()
    return load_links(engine, tenant, lid=lid)[0]


def sync_history_links(engine: sa.engine.Engine, tenant: str, model: Model) -> dict[str, int]:
    """CRM «cari ile ziyaret» çiftleri → `kaynak='gecmis'` bağları. Geçmiş ortak ziyaret kanıtlanmış bağdır: onaylı açılır
    (yönetici reddedebilir; reddedilen bir daha açılmaz). Bayi artık bayi/kitapçı kanalında değilse de CRM hesabıyla yazılır."""
    have: set[tuple[str, str]] = set()
    with engine.connect() as c:
        for sid, acc in c.execute(sa.select(DEALER_LINKS.c.ziyaret_yeri_id, DEALER_LINKS.c.crm_account_id)
                                  .where(DEALER_LINKS.c.tenant_id == tenant, DEALER_LINKS.c.kaynak == "gecmis")):
            have.add((sid, acc or ""))
    new = []
    at = now_utc()
    for h in model.history:
        if not h["school"] or not h["accountId"] or (h["school"], h["accountId"]) in have:
            continue
        code = model.dealer_by_account.get(h["accountId"])
        d = model.dealers.get(code or "") or {}
        new.append({"id": uuid.uuid4().hex, "tenant_id": tenant, "ziyaret_yeri_id": h["school"],
                    "logo_clientref": d.get("logicalref"), "crm_account_id": h["accountId"], "cari_kodu": d.get("code"),
                    "bayi_adi": d.get("name"), "kaynak": "gecmis", "durum": "onayli", "puan": None,
                    "gerekce": f"CRM'de {h['count']} «cari ile ziyaret» kaydı; son {h['last'] or 'tarihsiz'}.",
                    "onaylayan": None, "zaman": at, "olusturan": "sistem", "olusturma": at})
        have.add((h["school"], h["accountId"]))
    if new:
        with engine.begin() as c:
            c.execute(DEALER_LINKS.insert(), new)
        bump()
    return {"created": len(new), "pairs": len(model.history)}


def dealer_candidates(model: Model, sc: dict[str, Any], *, linked_counts: dict[str, int], risk: dict[str, dict[str, Any]]
                      ) -> list[dict[str, Any]]:
    """Okul için aday bayiler (kural): aynı ildeki bayi/kitapçılar. Puan: aynı ilçe 40, kademeye uygun kitap satışı
    (adaylar arasında en çok satana göre) 40, bu okulda ya da ilçede geçmiş ortak ziyaret 10, ağ dengesi 10 (zaten
    bağlı okul sayısı arttıkça azalır). Riskli bayi (M30 sinyali varsa) uyarıyla gelir, puandan düşülmez."""
    il = fold(sc.get("il"))
    codes = model.dealers_by_il.get(il, [])
    if not codes:
        return []
    sales = {c: model.dealer_grade_sales(c, sc["grades"]) for c in codes}
    top = max(sales.values()) if sales else 0.0
    joint_here = {model.dealer_by_account.get(h["accountId"]) for h in model.history if h["school"] == sc["id"]}
    ilce = fold(sc.get("ilce"))
    ilce_schools = {x for x in model.by_il.get(sc.get("ilId") or "", []) if fold(model.schools[x].get("ilce")) == ilce}
    joint_ilce = {model.dealer_by_account.get(h["accountId"]) for h in model.history if h["school"] in ilce_schools}
    out = []
    for code in codes:
        d = model.dealers[code]
        same_ilce = bool(ilce) and fold(d.get("ilce")) == ilce
        s_ratio = (sales[code] / top) if top > 0 else 0.0
        joint = 10.0 if code in joint_here else (5.0 if code in joint_ilce else 0.0)
        n = linked_counts.get(code, 0)
        balance = 10.0 / (1 + n / 5)
        score = round((40.0 if same_ilce else 0.0) + 40.0 * max(0.0, s_ratio) + joint + balance, 1)
        why = []
        why.append("aynı ilçede" if same_ilce else "aynı ilde (ilçe farklı ya da bilinmiyor)")
        why.append(f"bu kademeye uygun kitaplardan son {model.settings['dealerMonths']} ayda {int(round(sales[code])):,} adet"
                   .replace(",", ".") if sales[code] > 0 else "bu kademeye uygun kitap satışı yok")
        if code in joint_here:
            why.append("bu okula daha önce birlikte gidilmiş")
        elif code in joint_ilce:
            why.append("ilçedeki okullara daha önce birlikte gidilmiş")
        if n:
            why.append(f"zaten {n} okula bağlı")
        warn = None
        rk = risk.get((d.get("logicalref") or "").strip())
        if rk and ((rk.get("riskFill") or 0) >= 0.9 or (rk.get("overdue90") or 0) > 0):
            warn = "Bayi risk sinyali taşıyor (limit doluluğu yüksek ya da 90 günü aşan borç): yönlendirmeden önce bakın."
        out.append({"code": d["code"], "name": d["name"], "channel": d["channel"], "il": d["il"], "ilce": d["ilce"],
                    "phone": d["phone"], "email": d["email"], "score": score, "sameIlce": same_ilce,
                    "gradeSales": round(sales[code], 0), "linkedSchools": n, "why": why, "warning": warn,
                    "logicalref": d.get("logicalref"), "accountId": d.get("accountId")})
    out.sort(key=lambda x: (-x["score"], fold(x["name"])))
    return out


def read_risk(engine: sa.engine.Engine) -> dict[str, dict[str, Any]]:
    """M30'un bayi sinyal tablosu varsa (henüz yoksa boş): limit doluluğu ve 90+ gün borç, en yeni `asof`."""
    try:
        insp = sa.inspect(engine)
        if not insp.has_table("semantic_field_signals"):
            return {}
        t = sa.Table("semantic_field_signals", sa.MetaData(), autoload_with=engine)
        cols = set(t.c.keys())
        if not {"logo_clientref", "asof"} <= cols:
            return {}
        out: dict[str, dict[str, Any]] = {}
        with engine.connect() as c:
            for r in c.execute(sa.select(t).order_by(t.c.asof)).mappings():
                out[str(r["logo_clientref"])] = {"riskFill": r.get("risk_doluluk"), "overdue90": r.get("k_90p")}
        return out
    except Exception as e:  # noqa: BLE001
        log.info("school_visits: saha sinyalleri okunamadı: %s", e)
        return {}


# ------------------------------------------------------------------------------------------ katalog


def select_catalog(model: Model, sc: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    """Okulun kademesine uygun, stokta, fiyat süzgecine uyan kitaplar; sıralama: ildeki bayilerin satışı (çok satan
    önce), sonra ad. `adet` 0 ya da «hepsi» = süzgece uyan bütün kitaplar (sessiz kesme yok; toplam her zaman yazılır)."""
    grades = set(sc["grades"])
    wanted = body.get("siniflar")
    if isinstance(wanted, list) and wanted:
        try:
            pick = {int(x) for x in wanted}
        except (TypeError, ValueError):
            raise SchoolError("Sınıf listesi sayı olmalı.") from None
        grades = (grades & pick) if grades else pick
    if not grades:
        raise SchoolError("Okulun kademesi ya da türü CRM'de boş; katalog için sınıf seçin.")
    cap = src.num(body.get("fiyatUst"))
    raw_n = body.get("adet")
    n = model.settings["catalogSize"] if raw_n in (None, "") else (0 if str(raw_n) == "hepsi" else src.ival(raw_n))
    if n is None or n < 0:
        raise SchoolError("Kitap sayısı geçersiz.")
    pop = model.il_popularity(sc.get("il"))
    books = [b for b in model.fitting_books(grades) if cap is None or (b["price"] is not None and b["price"] <= cap)]
    books.sort(key=lambda b: (-pop.get(b["code"].upper(), 0.0), fold(b["title"])))
    chosen = books if n == 0 else books[:n]
    return {"grades": sorted(grades), "priceCap": cap, "size": n, "total": len(books),
            "items": [{"code": b["code"], "title": b["title"], "grades": grades_text(b["grades"]), "pages": b["pages"],
                       "price": b["price"], "priceBasis": b["priceBasis"], "stock": b["stock"],
                       "regionSales": round(pop.get(b["code"].upper(), 0.0))} for b in chosen]}


def save_catalog(engine: sa.engine.Engine, tenant: str, user: str, sc: dict[str, Any], sel: dict[str, Any],
                 dealer: Optional[dict[str, Any]]) -> dict[str, Any]:
    row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "ziyaret_yeri_id": sc["id"], "okul_adi": sc["name"],
           "secim_json": json.dumps({"grades": sel["grades"], "priceCap": sel["priceCap"], "size": sel["size"]}),
           "kitaplar_json": json.dumps(sel["items"], ensure_ascii=False), "uygun_toplam": sel["total"],
           "bayi_json": json.dumps(dealer, ensure_ascii=False) if dealer else None, "pdf_yolu": None,
           "olusturan": user, "olusturma": now_utc()}
    with engine.begin() as c:
        c.execute(CATALOGS.insert().values(**row))
    return row


def load_catalog(engine: sa.engine.Engine, tenant: str, cid: str) -> dict[str, Any]:
    with engine.connect() as c:
        r = c.execute(sa.select(CATALOGS).where(CATALOGS.c.tenant_id == tenant, CATALOGS.c.id == cid)).mappings().first()
    if not r:
        raise SchoolError("Katalog bulunamadı.", 404)
    return dict(r)


def catalog_pdf(cat: dict[str, Any], sc: Optional[dict[str, Any]], made_by: str) -> bytes:
    """Öğretmene bırakılacak liste. Dil «tanıtım ve okuma kültürü»: satış çağrısı yok, «MEB tavsiyeli» ibaresi yok;
    kitap seçiminin okulun seçim komisyonunda olduğu yazılır."""
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise SchoolError("PDF üretici sunucuda kurulu değil.", 503) from e
    from semantic_bridge.editorial_export import _fold as ascii_fold, _resolve_fonts

    items = json.loads(cat["kitaplar_json"] or "[]")
    sel = json.loads(cat["secim_json"] or "{}")
    dealer = json.loads(cat["bayi_json"]) if cat.get("bayi_json") else None
    regular, bold = _resolve_fonts()
    uni = regular is not None
    fam = "ZekiSans" if uni else "Helvetica"
    T = (lambda x: x) if uni else ascii_fold
    violet, ink, muted = (91, 60, 196), (30, 30, 40), (110, 110, 125)
    school_name = (sc or {}).get("name") or cat.get("okul_adi") or ""
    stamp = (cat["olusturma"] if isinstance(cat["olusturma"], datetime) else datetime.fromisoformat(str(cat["olusturma"])))
    stamp_txt = (stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp).astimezone(TZ).strftime("%d.%m.%Y")

    class Pdf(FPDF):
        def footer(self) -> None:
            self.set_y(-12)
            self.set_font(fam, "", 7.5)
            self.set_text_color(*muted)
            self.cell(0, 5, T(f"Timaş Yayınları · {stamp_txt} · Sayfa {self.page_no()}/{{nb}}"), align="C")

    pdf = Pdf(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_title(f"Kitap önerileri — {school_name}")
    pdf.set_author("Timaş Yayınları")
    pdf.set_margins(16, 16, 16)
    pdf.set_auto_page_break(auto=True, margin=18)
    if uni:
        pdf.add_font(fam, "", str(regular))
        pdf.add_font(fam, "B", str(bold or regular))
    pdf.add_page()
    pdf.set_text_color(*violet)
    pdf.set_font(fam, "B", 9)
    pdf.cell(0, 5, T("TİMAŞ YAYINLARI · OKUMA KÜLTÜRÜ"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*ink)
    pdf.set_font(fam, "B", 16)
    pdf.multi_cell(0, 8, T(f"{school_name} için kitap önerileri"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(fam, "", 9.5)
    pdf.set_text_color(*muted)
    grades = grades_text(sel.get("grades") or [])
    pdf.multi_cell(0, 5, T(f"{grades} öğrencilerinin okuma listesine ve okul kütüphanesine önerilen {len(items)} kitap. "
                           "Kitap seçimi okulunuzun kütüphane seçim komisyonunun değerlendirmesine sunulur."),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    widths = (100, 36, 18, 24)
    heads = ("Kitap", "Sınıf / yaş", "Sayfa", "Liste fiyatı")
    pdf.set_font(fam, "B", 8.5)
    pdf.set_text_color(*muted)
    for w, h in zip(widths, heads):
        pdf.cell(w, 6, T(h), border="B")
    pdf.ln(6)
    pdf.set_text_color(*ink)
    pdf.set_font(fam, "", 9)
    for it in items:
        price = it.get("price")
        cells = (it.get("title") or it.get("code") or "", it.get("grades") or "—",
                 str(it.get("pages") or "—"), (f"{price:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")) if price else "—")
        if pdf.get_y() > 268:
            pdf.add_page()
        x0, y0 = pdf.l_margin, pdf.get_y()
        # Önce sağdaki kısa kolonlar, sonra kitap adı sarılarak: satır yüksekliği adın satır sayısı kadar olur.
        pdf.set_xy(x0 + widths[0], y0)
        for w, c in zip(widths[1:], cells[1:]):
            pdf.cell(w, 5.2, T(c))
        pdf.set_xy(x0, y0)
        pdf.multi_cell(widths[0] - 2, 5.2, T(cells[0]), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(0.8)
    pdf.ln(4)
    if dealer:
        pdf.set_font(fam, "B", 9.5)
        pdf.cell(0, 5, T("Kitapları temin edebileceğiniz nokta"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(fam, "", 9.5)
        line = " · ".join(x for x in (dealer.get("name"), dealer.get("ilce") or dealer.get("il"), dealer.get("phone")) if x)
        pdf.multi_cell(0, 5, T(line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font(fam, "", 8)
    pdf.set_text_color(*muted)
    pdf.multi_cell(0, 4.2, T(f"Liste {made_by} tarafından hazırlanmıştır. Fiyatlar liste fiyatıdır ve değişebilir."),
                   new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ------------------------------------------------------------------------------------------ kopya tablolar (gece)


def write_profiles(engine: sa.engine.Engine, tenant: str, model: Model) -> int:
    """CRM okul listesinin kopyası: CRM kaynaklı satırlar her gece baştan yazılır (kopya, müşteri verisi değil)."""
    at = now_utc()
    rows = [{"tenant_id": tenant, "ziyaret_yeri_id": sc["id"], "ad": sc["name"][:300], "kurum_tipi": sc["kurumTipi"],
             "kurum_turu": sc["kurumTuru"], "okul_turu": sc["okulTuru"], "kademe": sc["kademe"], "ogrenci": sc["students"],
             "ogretmen": sc["teachers"], "derslik": sc["classrooms"], "kitap_sayisi": sc["libraryBooks"], "il": sc["il"],
             "ilce": sc["ilce"], "kaynak": "crm", "kaynak_tarihi": date.fromisoformat(sc["changed"]) if sc["changed"] else None,
             "asof": at} for sc in model.schools.values()]
    with engine.begin() as c:
        c.execute(PROFILES.delete().where(PROFILES.c.tenant_id == tenant, PROFILES.c.kaynak == "crm"))
        for i in range(0, len(rows), 2000):
            c.execute(PROFILES.insert(), rows[i:i + 2000])
    return len(rows)


def write_priority(engine: sa.engine.Engine, tenant: str, term: str, scored: dict[str, dict[str, Any]],
                   owners: dict[str, set[str]]) -> int:
    at = now_utc()
    rows = [{"tenant_id": tenant, "ziyaret_yeri_id": sid, "donem": term, "puan": s["score"],
             "bilesenler_json": json.dumps(s["parts"], ensure_ascii=False), "gerekce": s["reason"],
             "sahip": ",".join(sorted(owners.get(sid, set())))[:400] or None, "hesaplandi": at} for sid, s in scored.items()]
    with engine.begin() as c:
        c.execute(PRIORITY.delete().where(PRIORITY.c.tenant_id == tenant, PRIORITY.c.donem == term))
        for i in range(0, len(rows), 2000):
            c.execute(PRIORITY.insert(), rows[i:i + 2000])
    return len(rows)


def catalogs_stmt(tenant: str, sid: str) -> Any:
    """Okul için hazırlanmış kataloglar (en yeni önce)."""
    return (sa.select(CATALOGS.c.id, CATALOGS.c.olusturan, CATALOGS.c.olusturma, CATALOGS.c.uygun_toplam, CATALOGS.c.kitaplar_json)
            .where(CATALOGS.c.tenant_id == tenant, CATALOGS.c.ziyaret_yeri_id == sid).order_by(CATALOGS.c.olusturma.desc()))


def matches_stmt(tenant: str) -> Any:
    """CRM ziyaretindeki serbest okul adı → ziyaret yeri kararları (Zeki AI ya da kişi)."""
    return sa.select(NAME_MATCHES).where(NAME_MATCHES.c.tenant_id == tenant)


def load_matches(engine: sa.engine.Engine, tenant: str) -> dict[str, Optional[str]]:
    with engine.connect() as c:
        return {r["metin_anahtar"]: (r["ziyaret_yeri_id"] if r["karar"] == "evet" else None)
                for r in c.execute(sa.select(NAME_MATCHES).where(NAME_MATCHES.c.tenant_id == tenant)).mappings()}


def save_match(engine: sa.engine.Engine, tenant: str, key: str, sid: Optional[str], kaynak: str,
               karar: Optional[str] = None, olasilik: Optional[float] = None) -> None:
    """Ad eşleşmesi kararı kalıcıdır: «evet» (okul bağlanır), «hayir» (hiçbiri), «belirsiz» (model emin değil; yeniden
    sorulmaz, ekranda ad eşleşmesi yok kalır)."""
    with engine.begin() as c:
        c.execute(NAME_MATCHES.delete().where(NAME_MATCHES.c.tenant_id == tenant, NAME_MATCHES.c.metin_anahtar == key[:300]))
        c.execute(NAME_MATCHES.insert().values(tenant_id=tenant, metin_anahtar=key[:300], ziyaret_yeri_id=sid,
                                               karar=karar or ("evet" if sid else "hayir"), kaynak=kaynak, olasilik=olasilik,
                                               zaman=now_utc()))
    bump()


# ------------------------------------------------------------------------------------------ Zeki AI (LLM kapısı)

def numbers_ok(text: str, facts: str) -> bool:
    """Model metnindeki her sayı verilen bilgide geçmeli (rakamı model üretmez). Denetim: `zeki_text`."""
    from semantic_bridge import zeki_text as Z

    return Z.numbers_ok(text or "", facts)


def ask(llm: Any, system: str, user: str, max_tokens: int = 220) -> Optional[str]:
    if llm is None:
        return None
    try:
        out = llm.chat([{"role": "system", "content": system}, {"role": "user", "content": user}], max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001 — model yoksa kural metni kalır
        log.info("school_visits: model cevap vermedi: %s", e)
        return None
    out = re.sub(r"<think>.*?</think>", "", str(out or ""), flags=re.S).strip()
    return out or None


SYSTEM_TR = ("Sen Zeki AI'sın: Timaş Yayınları'nın okul tanıtım ekibine yardım ediyorsun. Türkçe, kısa ve somut yaz. "
             "Yalnız verilen bilgileri kullan; yeni sayı, tarih ya da ad uydurma. Satış dili kullanma; okuma kültürü ve "
             "tanıtım dilinde yaz. «MEB tavsiyeli» gibi ibareler kullanma. Öğrenci hakkında kişisel bilgi yazma.")


def ai_reason(llm: Any, sc: dict[str, Any], scored: dict[str, Any]) -> Optional[str]:
    facts = json.dumps({"okul": sc["name"], "ilce": sc.get("ilce"), "kademe": sc.get("kademe") or sc.get("gradesText"),
                        "bilesenler": [{"ad": p["label"], "puan": p["points"], "not": p["note"]} for p in scored["parts"]]},
                       ensure_ascii=False)
    out = ask(llm, SYSTEM_TR, "Bu okulun bu hafta ziyaret listesinde neden öne çıktığını tek cümleyle yaz.\n" + facts, 90)
    if out and numbers_ok(out, facts):
        return out.splitlines()[0][:300]
    return None


def ai_advice(llm: Any, facts: dict[str, Any]) -> Optional[str]:
    blob = json.dumps(facts, ensure_ascii=False, default=str)
    out = ask(llm, SYSTEM_TR, "Temsilci bu okula gitmeden önce okuyacak. 2–3 cümlelik ziyaret önerisi yaz: kiminle "
                              "görüşmeli, hangi kitaplarla, neye dikkat etmeli.\n" + blob, 260)
    if out and numbers_ok(out, blob):
        return out[:900]
    return None


def choose(llm: Any, prompt: str, choices: list[str], min_p: float, min_margin: float) -> dict[str, Any]:
    """Kapalı küme seçim (LLM kapısı `QueuedLlm.choose`, docs/analiz/llm-choose.md): verilen seçeneklerden biri ve
    olasılığı. Eşik çağıranın: `confident(min_p, min_margin)` geçmezse `choice=None` («emin değil»). Model yoksa ya da
    istemci kapısız ise (choose yok) `available=False` — karar verilmez, sonra yeniden denenir."""
    if llm is None or not hasattr(llm, "choose"):
        return {"available": False, "choice": None, "probability": None, "margin": None}
    try:
        r = llm.choose(prompt, choices, system=SYSTEM_CHOICE)
    except Exception as e:  # noqa: BLE001 — model cevap veremedi: «sonra dene»
        log.info("school_visits: seçim yapılamadı: %s", e)
        return {"available": False, "choice": None, "probability": None, "margin": None}
    ok = r.confident(min_p, min_margin)
    return {"available": True, "choice": r.choice if ok else None, "raw": r.choice, "probability": r.probability,
            "margin": r.margin, "method": r.method}


SYSTEM_CHOICE = "Timaş Yayınları okul tanıtım ekibi için kayıt eşleştiriyorsun. Yalnız verilen bilgiye göre seç; emin değilsen «Hiçbiri»ni seç."
NONE_OF_THEM = "Hiçbiri: listedeki okulların hiçbiri değil"


def ai_pick_school(llm: Any, text: str, candidates: list[dict[str, Any]], min_p: float, min_margin: float) -> dict[str, Any]:
    """CRM etkinliğindeki serbest okul metni hangi kayıtlı okul? Aday okullar (aynı il, ad benzerliği eşiği üstünde) +
    «Hiçbiri» arasından seçim. Dönen `school`: okul kimliği, «hiçbiri» için "" (kalıcı ret), emin değilse None."""
    labels = [f"{c['name']} ({c.get('ilce') or 'ilçe bilinmiyor'}; {c.get('kademe') or c.get('gradesText') or 'kademe bilinmiyor'})"
              for c in candidates]
    uniq = []
    for i, lbl in enumerate(labels):
        uniq.append(lbl if lbl not in uniq else f"{lbl} #{i + 1}")
    res = choose(llm, f"CRM'deki bir okul ziyareti kaydında okul adı serbest metin olarak «{text}» yazılmış. "
                      "Aynı ildeki kayıtlı okullardan hangisi?", uniq + [NONE_OF_THEM], min_p, min_margin)
    pick = res.get("choice")
    school: Optional[str] = None
    if pick == NONE_OF_THEM:
        school = ""
    elif pick is not None:
        school = candidates[uniq.index(pick)]["id"]
    return {**res, "school": school}


def ai_pick_dealer(llm: Any, sc: dict[str, Any], candidates: list[dict[str, Any]], min_p: float, min_margin: float
                   ) -> dict[str, Any]:
    """Okul için önerilecek bayi (K2, yönetici onaylar): kuralın sıraladığı ilk adaylar, gerekçeleriyle seçenek olur.
    Emin değilse kuralın birincisi önerilir (çağıran karar verir)."""
    labels = []
    for c in candidates:
        lbl = f"{c['name'] or c['code']} ({c.get('ilce') or c.get('il') or '—'}): " + "; ".join(c["why"])
        labels.append(lbl if lbl not in labels else f"{lbl} #{c['code']}")
    res = choose(llm, f"Okul: {sc['name']} ({sc.get('ilce') or '—'}, {sc.get('kademe') or sc.get('gradesText')}). Öğretmenler "
                      "kitapları hangi bayiden ya da kitapçıdan alsın? Yakınlık, bu kademede satış ve geçmiş ortak ziyaret önemlidir.",
                 labels, min_p, min_margin)
    pick = res.get("choice")
    return {**res, "code": candidates[labels.index(pick)]["code"] if pick is not None else None}


def ai_pick(llm: Any, prompt: str, options: dict[str, str], min_p: float, min_margin: float) -> Optional[str]:
    """Anahtar → etiket sözlüğünden seçim; emin değilse None."""
    keys = list(options)
    res = choose(llm, prompt, [options[k] for k in keys], min_p, min_margin)
    return keys[[options[k] for k in keys].index(res["choice"])] if res.get("choice") is not None else None


def ai_note_fields(llm: Any, note: str, books: list[dict[str, Any]], min_p: float = 0.70,
                   min_margin: float = 0.30) -> Optional[dict[str, Any]]:
    """Serbest ziyaret notundan alan önerisi (temsilci onaylar). İlgi düzeyi ve görüşülen kişinin rolü kapalı küme
    seçimle (emin değilse boş kalır); kitap adları, sıradaki adım ve bayi yönlendirmesi metinden çıkarılır, kitaplar
    katalog adlarıyla kuralla eşlenir."""
    text = note[:2000]
    res: dict[str, Any] = {}
    ilgi = ai_pick(llm, f"Okul ziyareti notu: «{text}»\nOkulun kitaplara ilgisi hangi düzeyde?", INTEREST, min_p, min_margin)
    if ilgi:
        res["ilgi"] = ilgi
    role = ai_pick(llm, f"Okul ziyareti notu: «{text}»\nTemsilci okulda en çok kiminle görüşmüş?", ROLES, min_p, min_margin)
    if role:
        res["kisiRolu"] = role
    q = ("Aşağıdaki okul ziyareti notundan şu alanları JSON olarak çıkar: "
         '{"kitaplar": ["nottaki kitap adları"], "sonrakiAdim": "tek cümle ya da boş", "bayiYonlendirildi": true|false}. '
         "Notta olmayanı boş bırak. Yalnız JSON yaz.\nNot: " + text)
    out = ask(llm, "Yalnız geçerli JSON yaz.", q, 300)
    data: dict[str, Any] = {}
    m = re.search(r"\{.*\}", out or "", flags=re.S)
    if m:
        try:
            data = json.loads(m.group(0))
        except ValueError:
            data = {}
    if not res and not data:
        return None
    if isinstance(data.get("sonrakiAdim"), str) and data["sonrakiAdim"].strip():
        res["sonrakiAdim"] = data["sonrakiAdim"].strip()[:300]
    if isinstance(data.get("bayiYonlendirildi"), bool):
        res["bayiYonlendirildi"] = data["bayiYonlendirildi"]
    found = []
    for t in data.get("kitaplar") or []:
        best, hit = 0.0, None
        for b in books:
            sc = name_score(t, b.get("title"))
            if sc > best:
                best, hit = sc, b
        if hit and best >= 0.6:
            found.append({"code": hit["code"], "title": hit["title"]})
    if found:
        res["istenenKitaplar"] = found
    return res
