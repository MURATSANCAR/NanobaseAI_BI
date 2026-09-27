"""Sezon takvimi: yaklaşan özel günler, o güne bağlı kitaplar ve sayfalarının hazır olup olmadığı.

Kaynak (canlı CRM .28, 2026-09-27 ölçümü):
- Özel gün `new_ozelgunlerBase` (93 kayıt): ad, `new_ozelgunhafta1`/`new_ozelgunlerhafta2` (ISO hafta numarası,
  başlangıç/bitiş), `new_webyayindurum` (sitede yayında mı), `new_Tarih` (tanımlı ama hiçbir kayıtta dolu değil).
  Aynı ad iki kez girilmiş olabilir ("Dünya Okuma Günü"); ekranda tek gün sayılır, kitapları birleşir.
- Kitap bağı `new_new_kitap_new_ozelgunlerBase` (~820 bağ) → `new_kitapBase.new_ean13` → T-soft ürünü (barkod).

Tarih: (1) kural — hareketli günler kodda hesaplanır: Anneler Günü mayısın 2. pazarı, Babalar Günü haziranın 3.
pazarı; Ramazan/Kurban Bayramı, kandiller, hicri yılbaşı hicri takvimden (standart tablo hesabı; Diyanet ilanıyla
±1 gün fark olabilir, ekranda yazılır). Tarihi sabit resmî günler de kuraldır (Öğretmenler Günü 24 Kasım …).
(2) CRM'de `new_Tarih` doluysa o gün/ay. (3) Adın içinde tarih geçiyorsa ("15 Temmuz …") o gün. (4) Yoksa CRM'deki
ISO haftası (pazartesi–pazar). Hiçbiri yoksa "tarih bilinmiyor": tahmin yapılmaz (LGS/YKS tarihini her yıl sınav
kurumu açıklar).

Geçen yılın arama artışı (Search Console, yalnız okuma; en çok 16 ay geriye veri verir): gece, haftalık sorgu
kırılımı okunur (`dims=['query']`, hafta başına; tamamlanmış hafta bir kez okunur ve saklanır) ve site geneli
günlük toplam (`dims=['date']`). Her gün için adından türetilen anahtar kelimeleri ve bağlı kitapların adlarını içeren
sorguların gösterimi, geçen yılki gün öncesi 4 haftada, ondan önceki 8 haftanın haftalık ortalamasıyla karşılaştırılır;
aynı pencerede site geneli değişim de yanında durur.

Hazırlık: gün tarihinden `LEAD_DAYS` gün önce başlar. Kitap hazırlığı mevcut veriden: SEO puanı ve açık sorunlar
(ürün denetimi), bekleyen/onaylı öneri, CRM hak özeti. CRM'de durum işareti olan kitap (çekildi, bizim değil …)
listeye girmez. Hiçbir yere yazılmaz.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request

from . import connections, crm
from .store import CRM_BOOKS, PRODUCTS, PROPOSALS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

DAYS = sa.Table(
    "semantic_seo_seasons_days", _md,  # özel gün (CRM + kodda tanımlı hareketli günler), anahtar kelimeleri, geçen yıl artışı
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("day_key", sa.String(120), primary_key=True),
    sa.Column("name", sa.String(300), nullable=False),
    sa.Column("source", sa.String(8), nullable=False),        # crm | kural
    sa.Column("crm_ids", sa.Text, nullable=False),             # JSON liste
    sa.Column("week_from", sa.Integer),
    sa.Column("week_to", sa.Integer),
    sa.Column("fixed_date", sa.String(5)),                     # "AA-GG", CRM new_Tarih
    sa.Column("web", sa.Boolean, nullable=False, default=False),
    sa.Column("crm_books", sa.Integer, nullable=False, default=0),
    sa.Column("keywords_json", sa.Text, nullable=False),
    sa.Column("uplift_json", sa.Text),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)
BOOKS = sa.Table(
    "semantic_seo_seasons_books", _md,  # özel gün ↔ CRM kitap kartı (barkodla T-soft ürününe bağlanır)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("day_key", sa.String(120), primary_key=True),
    sa.Column("ean", sa.String(20), primary_key=True),
    sa.Column("book_id", sa.String(40), nullable=False),
    sa.Column("name", sa.String(500)),
    sa.Column("uplift_json", sa.Text),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)
WEEKS = sa.Table(
    "semantic_seo_seasons_weeks", _md,  # Search Console haftalık sorgu taraması: anahtar → gösterim (tamamlanmış hafta)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("week", sa.String(10), primary_key=True),        # pazartesi, YYYY-AA-GG
    sa.Column("sig", sa.String(40), nullable=False),           # anahtar kelime tanımlarının özeti; değişirse yeniden okunur
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)

#: Hazırlık, gün tarihinden bu kadar gün önce başlar (sayfa düzeltmesinin Google'da görünmesi için pay).
LEAD_DAYS = 21
DEFAULT_WEEKS = 12
#: Takvim en çok bir yıl ileriye bakar (her gün yılda bir kez döner; daha uzun pencere aynı günü iki kez gösterirdi).
MAX_WEEKS = 52
#: Artış penceresi: geçen yılki gün öncesi 4 hafta; kıyas: ondan önceki 8 hafta (haftalık ortalama).
WINDOW_WEEKS, BASELINE_WEEKS = 4, 8
#: Search Console en çok 16 ay geriye veri verir; kesin veri 3 gün geç gelir.
GSC_HISTORY_DAYS, LAG = 480, 3
#: Hazır sayılan en düşük SEO puanı (ürün denetimindeki "iyi" eşiğiyle aynı).
READY_SCORE = 80
#: CRM tarih alanları UTC saklanır; Türkiye saati UTC+3.
CRM_UTC_OFFSET_HOURS = 3
LIMIT = 500_000

_ready: set[int] = set()
_ready_lock = threading.Lock()
_run_lock = threading.Lock()
state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "days": None, "books": None,
                         "weeksRead": None, "error": None, "gscError": None}


def ensure_tables(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) not in _ready:
            for t in (DAYS, BOOKS, WEEKS):
                t.create(engine, checkfirst=True)
            _ready.add(id(engine))


# ================================================================================================ metin

def fold(text: Any) -> str:
    """Türkçe harf ve şapka farkını siler: "Öğretmenler GÜNÜ" → "ogretmenler gunu"."""
    t = str(text or "").replace("İ", "i").replace("I", "ı").lower().replace("̇", "")
    return t.translate(str.maketrans("ışğüöçâîû’", "isguocaiu'"))


_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
STOP = {"ve", "ile", "bir", "icin", "the", "of", "and", "de", "da"}
#: Gün adında çok geçen, tek başına bir güne işaret etmeyen kelimeler.
GENERIC = {"gunu", "gun", "gunleri", "haftasi", "hafta", "bayrami", "bayram", "dunya", "uluslararasi", "uluslar",
           "arasi", "ulusal", "anma", "kutlama", "yildonumu", "senlikleri"}
MONTHS = ("ocak", "subat", "mart", "nisan", "mayis", "haziran", "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik")


def tokens(text: Any) -> list[str]:
    """Kelimeler; kesme işaretinden sonraki ek atılır ("Atatürk'ü" → "ataturk")."""
    return [t.split("'", 1)[0] for t in _TOKEN.findall(fold(text).replace("`", "'"))]


def _alternatives(name: str) -> list[str]:
    raw = re.sub(r"\([^)]*\)", " ", str(name or ""))
    return [p for p in re.split(r"\s[-/–]\s|/", raw) if p.strip()]


def keywords(name: str) -> list[list[str]]:
    """Gün adından arama anahtarları: her biri, sorguda hepsi geçmesi gereken kelimeler.

    Genel kelimeler (gün, hafta, dünya …) atılır; kalan çok kısaysa ("Dünya Su Günü" → "su") ad tam hâliyle kalır.
    Ad "/" ya da " - " ile iki ad taşıyorsa ikisi de ayrı anahtar olur."""
    out: list[list[str]] = []
    for part in _alternatives(name):
        toks = [t for t in tokens(part) if t not in STOP and not t.isdigit()]
        if not toks:
            continue
        core = [t for t in toks if t not in GENERIC]
        kw = core if core and sum(len(t) for t in core) >= 5 else toks
        if kw not in out:
            out.append(kw)
    return out


def book_keywords(name: str) -> list[list[str]]:
    """Kitap adı sorguda geçiyor mu: adın bütün kelimeleri. Tek kısa kelimelik ad (çok genel) anahtar olmaz."""
    toks = [t for t in tokens(name) if t not in STOP and not t.isdigit()]
    if not toks or max(len(t) for t in toks) < 4 or (len(toks) == 1 and len(toks[0]) < 6):
        return []
    return [toks]


def _tok_match(q: str, k: str) -> bool:
    return q == k or (len(k) >= 4 and q.startswith(k))


def matches(query_tokens: Iterable[str], kw: list[str]) -> bool:
    """Anahtarın her kelimesi sorguda (Türkçe ek için 4+ harfli kelimede önek olarak) geçiyor mu."""
    qt = list(query_tokens)
    return all(any(_tok_match(q, k) for q in qt) for k in kw)


def _anchor(kw: list[str]) -> str:
    longest = max(kw, key=len)
    return longest[:4] if len(longest) >= 4 else longest


def build_index(entries: list[tuple[str, list[str]]]) -> dict[str, list[tuple[str, list[str]]]]:
    """Hızlı tarama için anahtarlar en uzun kelimelerinin ilk 4 harfine göre gruplanır."""
    idx: dict[str, list[tuple[str, list[str]]]] = {}
    for key, kw in entries:
        idx.setdefault(_anchor(kw), []).append((key, kw))
    return idx


def scan(rows: list[dict[str, Any]], index: dict[str, list[tuple[str, list[str]]]]) -> dict[str, float]:
    """Search Console sorgu satırları → anahtar başına toplam gösterim. Bir sorgu bir anahtara bir kez sayılır."""
    out: dict[str, float] = {}
    for r in rows:
        keys = r.get("keys") or []
        qt = tokens(keys[0] if keys else "")
        if not qt:
            continue
        seen: set[str] = set()
        for q in qt:
            for probe in {q[:4], q}:
                for key, kw in index.get(probe, ()):
                    if key not in seen and matches(qt, kw):
                        seen.add(key)
                        out[key] = out.get(key, 0.0) + float(r.get("impressions") or 0)
    return out


def signature(entries: list[tuple[str, list[str]]]) -> str:
    return hashlib.sha1(dumps(sorted([k, v] for k, v in entries)).encode()).hexdigest()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(name)).strip("-")[:120] or "gun"


# ================================================================================================ takvim

def hijri_to_gregorian(year: int, month: int, day: int) -> date:
    """Standart tablo hicri takvimi (30 yıllık döngü, 1 Muharrem 1 = 16 Temmuz 622). Diyanet ilanı ±1 gün farklı olabilir."""
    jdn = day + (295 * (month - 1) + 9) // 10 + (year - 1) * 354 + (3 + 11 * year) // 30 + 1948439
    return date.fromordinal(jdn - 1721425)


def hijri_in_year(year: int, month: int, day: int) -> list[date]:
    """Verilen miladi yılın içine düşen (hicri ay, gün) tarihleri; bir miladi yılda iki kez düşebilir."""
    base = (year - 622) * 33 // 32
    out = [hijri_to_gregorian(hy, month, day) for hy in range(base - 1, base + 3)]
    return sorted(d for d in out if d.year == year)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Ayın n. haftanın günü (pazartesi=0 … pazar=6)."""
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def iso_week_monday(year: int, week: int) -> date:
    last = date(year, 12, 28).isocalendar()[1]
    return date.fromisocalendar(year, max(1, min(int(week), last)), 1)


def week_range(year: int, w1: int, w2: int) -> tuple[date, date]:
    start = iso_week_monday(year, w1)
    end = iso_week_monday(year if w2 >= w1 else year + 1, w2) + timedelta(days=6)
    return start, end


#: Kurallar: adın katlanmış hâlinde parçası geçen ilk kural uygulanır. `precision`: kesin | yaklasik (± gün).
#: Hicri kandil tarihi gecenin başladığı akşamdır: hicri günden bir gün önce (offset -1).
RULES: list[dict[str, Any]] = [
    {"match": ("anneler gunu",), "kind": "nth", "month": 5, "weekday": 6, "n": 2, "why": "Mayısın 2. pazarı"},
    {"match": ("babalar gunu",), "kind": "nth", "month": 6, "weekday": 6, "n": 3, "why": "Haziranın 3. pazarı"},
    {"match": ("ogretmenler gunu",), "kind": "fixed", "month": 11, "day": 24, "why": "24 Kasım"},
    {"match": ("cumhuriyet bayrami",), "kind": "fixed", "month": 10, "day": 29, "why": "29 Ekim"},
    {"match": ("ulusal egemenlik", "cocuk bayrami"), "kind": "fixed", "month": 4, "day": 23, "why": "23 Nisan"},
    {"match": ("genclik ve spor",), "kind": "fixed", "month": 5, "day": 19, "why": "19 Mayıs"},
    {"match": ("zafer bayrami",), "kind": "fixed", "month": 8, "day": 30, "why": "30 Ağustos"},
    {"match": ("canakkale zaferi",), "kind": "fixed", "month": 3, "day": 18, "why": "18 Mart"},
    {"match": ("dunya kadinlar gunu",), "kind": "fixed", "month": 3, "day": 8, "why": "8 Mart"},
    {"match": ("sevgililer gunu",), "kind": "fixed", "month": 2, "day": 14, "why": "14 Şubat"},
    {"match": ("istiklal marsi",), "kind": "fixed", "month": 3, "day": 12, "why": "12 Mart"},
    {"match": ("turk dil bayrami",), "kind": "fixed", "month": 9, "day": 26, "why": "26 Eylül"},
    {"match": ("istanbul'un fethi", "istanbulun fethi"), "kind": "fixed", "month": 5, "day": 29, "why": "29 Mayıs"},
    {"match": ("malazgirt",), "kind": "fixed", "month": 8, "day": 26, "why": "26 Ağustos"},
    {"match": ("ramazan bayrami",), "kind": "hijri", "month": 10, "day": 1, "offset": 0, "days": 3, "why": "1 Şevval"},
    {"match": ("kurban bayrami",), "kind": "hijri", "month": 12, "day": 10, "offset": 0, "days": 4, "why": "10 Zilhicce"},
    {"match": ("ramazan baslangici", "ramazan ayi"), "kind": "hijri", "month": 9, "day": 1, "offset": 0, "days": 30, "why": "1 Ramazan"},
    {"match": ("hicri yilbasi",), "kind": "hijri", "month": 1, "day": 1, "offset": 0, "days": 1, "why": "1 Muharrem"},
    {"match": ("asure",), "kind": "hijri", "month": 1, "day": 10, "offset": 0, "days": 1, "why": "10 Muharrem"},
    {"match": ("mevlid-i nebi haftasi", "mevlidi nebi haftasi"), "kind": "hijri", "month": 3, "day": 12, "offset": -1, "days": 7,
     "why": "Mevlid Kandili ile başlayan hafta (12 Rebiülevvel)"},
    {"match": ("mevlid kandili",), "kind": "hijri", "month": 3, "day": 12, "offset": -1, "days": 1, "why": "12 Rebiülevvel gecesi"},
    {"match": ("regaip kandili",), "kind": "regaip", "why": "Receb'in ilk cumasından önceki gece"},
    {"match": ("mirac kandili",), "kind": "hijri", "month": 7, "day": 27, "offset": -1, "days": 1, "why": "27 Receb gecesi"},
    {"match": ("berat kandili",), "kind": "hijri", "month": 8, "day": 15, "offset": -1, "days": 1, "why": "15 Şaban gecesi"},
    {"match": ("kadir gecesi",), "kind": "hijri", "month": 9, "day": 27, "offset": -1, "days": 1, "why": "27 Ramazan gecesi"},
    {"match": ("okullarin acilisi",), "kind": "nth", "month": 9, "weekday": 0, "n": 2, "approx": 7,
     "why": "Genellikle eylülün 2. pazartesi; kesin tarihi bakanlık açıklar"},
    {"match": ("lgs",), "kind": "unknown", "why": "Sınav tarihini her yıl bakanlık açıklar; CRM'de tarih yok."},
    {"match": ("yks",), "kind": "unknown", "why": "Sınav tarihini her yıl sınav kurumu açıklar; CRM'de tarih yok."},
]
#: CRM'de olmayan ama yayınevi için önemli günler: kitap bağı yoktur, anahtar kelime artışı ve rehber denetimi yapılır.
BUILTIN = ("Ramazan Bayramı", "Kurban Bayramı", "Regaip Kandili", "Miraç Kandili", "Berat Kandili", "Kadir Gecesi",
           "Mevlid Kandili", "Anneler Günü", "Babalar Günü", "Öğretmenler Günü", "Okulların Açılışı",
           "LGS (Liselere Geçiş Sınavı)", "YKS (Üniversite Sınavı)")


def rule_for(name: str) -> Optional[dict[str, Any]]:
    f = fold(name)
    toks = set(tokens(name))
    for r in RULES:
        for m in r["match"]:
            if (m in toks) if " " not in m and len(m) <= 4 else (m in f):
                return r
    return None


def date_in_name(name: str) -> Optional[tuple[int, int]]:
    """Adın içindeki "15 Temmuz" gibi gün+ay."""
    m = re.search(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\b", fold(name))
    if not m:
        return None
    mo, d = MONTHS.index(m.group(2)) + 1, int(m.group(1))
    try:
        date(2000, mo, d)
    except ValueError:
        return None
    return mo, d


def resolve(day: dict[str, Any]) -> dict[str, Any]:
    """Gün kaydı → tarih yöntemi. `day`: name, weekFrom, weekTo, fixedDate ("AA-GG")."""
    r = rule_for(day.get("name") or "")
    if r and r["kind"] == "unknown":
        return {"method": "unknown", "why": r["why"], "precision": "bilinmiyor", "uncertainty": None}
    if r:
        approx = 1 if r["kind"] in ("hijri", "regaip") else r.get("approx")
        return {"method": "rule", "rule": r, "why": r["why"], "precision": "yaklasik" if approx else "kesin",
                "uncertainty": approx}
    fd = day.get("fixedDate")
    if fd:
        mo, d = (int(x) for x in fd.split("-"))
        return {"method": "fixed", "month": mo, "day": d, "why": "CRM'deki tarih", "precision": "kesin", "uncertainty": None}
    named = date_in_name(day.get("name") or "")
    if named:
        return {"method": "fixed", "month": named[0], "day": named[1], "why": "Adındaki tarih", "precision": "kesin",
                "uncertainty": None}
    if day.get("weekFrom"):
        w1, w2 = int(day["weekFrom"]), int(day.get("weekTo") or day["weekFrom"])
        return {"method": "weeks", "weeks": (w1, w2), "why": f"CRM'deki {w1}." + (f"–{w2}." if w2 != w1 else "") + " hafta",
                "precision": "hafta", "uncertainty": None}
    return {"method": "unknown", "why": "CRM'de hafta ya da tarih girilmemiş.", "precision": "bilinmiyor", "uncertainty": None}


def _safe(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:  # 29 Şubat
        return date(year, month, 28)


def occurrences(how: dict[str, Any], year: int) -> list[tuple[date, date]]:
    """Miladi yıl içinde başlayan (başlangıç, bitiş) aralıkları."""
    m = how["method"]
    if m == "fixed":
        d = _safe(year, how["month"], how["day"])
        return [(d, d)]
    if m == "weeks":
        return [week_range(year, *how["weeks"])]
    if m != "rule":
        return []
    r = how["rule"]
    if r["kind"] == "fixed":
        d = _safe(year, r["month"], r["day"])
        return [(d, d)]
    if r["kind"] == "nth":
        d = nth_weekday(year, r["month"], r["weekday"], r["n"])
        return [(d, d)]
    if r["kind"] == "hijri":
        out = []
        # yıl sınırında kaydırma (kandil akşamı) başka yıla düşebilir: komşu yılları da hesapla, sonra süz
        for y in (year - 1, year, year + 1):
            for d in hijri_in_year(y, r["month"], r["day"]):
                s = d + timedelta(days=r.get("offset", 0))
                if s.year == year:
                    out.append((s, s + timedelta(days=r.get("days", 1) - 1)))
        return sorted(set(out))
    if r["kind"] == "regaip":
        out = []
        for y in (year - 1, year, year + 1):
            for first in hijri_in_year(y, 7, 1):
                friday = first + timedelta(days=(4 - first.weekday()) % 7)
                s = friday - timedelta(days=1)
                if s.year == year:
                    out.append((s, s))
        return sorted(set(out))
    return []


def next_occurrence(how: dict[str, Any], today: date) -> Optional[tuple[date, date]]:
    """Bitişi bugünden önce olmayan ilk aralık (süren gün de dahil)."""
    cands = [o for y in range(today.year - 1, today.year + 3) for o in occurrences(how, y) if o[1] >= today]
    return min(cands) if cands else None


def previous_occurrence(how: dict[str, Any], start: date) -> Optional[tuple[date, date]]:
    """Bir önceki yılın aynı günü: `start`tan en az 300 gün önceki son aralık (hicri gün her yıl ~11 gün kayar)."""
    cands = [o for y in range(start.year - 2, start.year + 1) for o in occurrences(how, y) if o[0] <= start - timedelta(days=300)]
    return max(cands) if cands else None


def lead_window(start: date, end: date, today: date, lead_days: int = LEAD_DAYS) -> dict[str, Any]:
    """Hazırlık penceresi. phase: yaklasiyor (hazırlık başlamadı) | hazirlik (şimdi düzeltme zamanı) | suruyor."""
    prep = start - timedelta(days=lead_days)
    if start <= today <= end:
        phase = "suruyor"
    elif today >= prep:
        phase = "hazirlik"
    else:
        phase = "yaklasiyor"
    return {"prepStart": prep.isoformat(), "daysLeft": max(0, (start - today).days),
            "prepDaysLeft": max(0, (prep - today).days), "phase": phase}


# ================================================================================================ hazırlık

READINESS_LABEL = {"hazir": "Hazır", "duzelt": "Düzeltilmeli", "onay_bekliyor": "Öneri onay bekliyor",
                   "onaylandi": "Onaylandı, sitede bekleniyor"}
_BLOCKING = ("kritik", "yüksek")


def readiness(score: Optional[int], severities: list[str], proposal: Optional[str], rights: Optional[str]) -> dict[str, Any]:
    """Kitap sayfası güne hazır mı. Öncelik: bekleyen öneri → onaylı öneri → puan/sorun.

    `proposal`: ürünün en son önerisinin durumu (hazir | onaylandi | reddedildi | None)."""
    blocking = sum(1 for s in severities if s in _BLOCKING)
    reasons: list[str] = []
    if score is not None and score < READY_SCORE:
        reasons.append(f"SEO puanı {score} (hazır için en az {READY_SCORE})")
    if blocking:
        reasons.append(f"{blocking} kritik/yüksek sorun açık")
    if proposal == "hazir":
        level = "onay_bekliyor"
    elif not reasons:
        level = "hazir"
    elif proposal == "onaylandi":
        level = "onaylandi"
    else:
        level = "duzelt"
    rights_warn = rights in ("eksik", "yok")
    if rights_warn:
        reasons.append("İnternette gösterim hakkı " + ("eksik" if rights == "eksik" else "yok") + ": kitaptan alıntı kullanılmaz")
    return {"level": level, "label": READINESS_LABEL[level], "reasons": reasons, "rightsWarning": rights_warn,
            "openIssues": len(severities), "blockingIssues": blocking}


# ================================================================================================ arama artışı

def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly(daily_rows: list[dict[str, Any]]) -> dict[date, float]:
    """`dims=['date']` satırları → pazartesi başına toplam gösterim."""
    out: dict[date, float] = {}
    for r in daily_rows:
        keys = r.get("keys") or []
        try:
            d = date.fromisoformat(str(keys[0])[:10])
        except (ValueError, IndexError):
            continue
        out[monday(d)] = out.get(monday(d), 0.0) + float(r.get("impressions") or 0)
    return out


def _pct(a: float, b: float) -> Optional[float]:
    return (a / b - 1) * 100 if b > 0 else None


def uplift(series: dict[date, float], site: dict[date, float], day_start: date, have: set[date]) -> Optional[dict[str, Any]]:
    """Geçen yılki gün öncesi `WINDOW_WEEKS` hafta ile ondan önceki `BASELINE_WEEKS` haftanın haftalık ortalaması.

    `have`: okunmuş haftalar (pazartesi). Pencerelerden biri eksikse (16 aydan eski) None."""
    m = monday(day_start)
    win = [m - timedelta(weeks=k) for k in range(WINDOW_WEEKS)]
    base = [m - timedelta(weeks=k) for k in range(WINDOW_WEEKS, WINDOW_WEEKS + BASELINE_WEEKS)]
    if any(w not in have for w in win + base):
        return None
    w = sum(series.get(x, 0.0) for x in win) / WINDOW_WEEKS
    b = sum(series.get(x, 0.0) for x in base) / BASELINE_WEEKS
    sw = sum(site.get(x, 0.0) for x in win) / WINDOW_WEEKS
    sb = sum(site.get(x, 0.0) for x in base) / BASELINE_WEEKS
    up, site_up = _pct(w, b), _pct(sw, sb)
    return {"dayStart": day_start.isoformat(), "window": [win[-1].isoformat(), (m + timedelta(days=6)).isoformat()],
            "baseline": [base[-1].isoformat(), (base[0] + timedelta(days=6)).isoformat()],
            "impressions": round(w * WINDOW_WEEKS), "weekly": round(w, 1), "baselineWeekly": round(b, 1),
            "upliftPct": up, "siteUpliftPct": site_up,
            "netPt": (up - site_up) if up is not None and site_up is not None else None}


def gsc_weeks(today: date) -> list[date]:
    """Kesin verisi tamamlanmış, Search Console'un geriye verdiği bütün haftalar (pazartesi)."""
    last_end = today - timedelta(days=LAG)
    last = monday(last_end) - (timedelta(weeks=1) if last_end.weekday() < 6 else timedelta(0))
    first = monday(today - timedelta(days=GSC_HISTORY_DAYS)) + timedelta(weeks=1)
    out, w = [], first
    while w <= last:
        out.append(w)
        w += timedelta(weeks=1)
    return out


# ================================================================================================ CRM

def days_sql(p: str) -> str:
    return ("SELECT o.new_ozelgunlerId AS id, o.new_name AS name, o.new_ozelgunhafta1 AS w1, o.new_ozelgunlerhafta2 AS w2,"
            " CAST(ISNULL(o.new_webyayindurum, 0) AS int) AS web, CONVERT(varchar(19), o.new_Tarih, 120) AS dt"
            f" FROM {p}new_ozelgunlerBase o WHERE o.statecode = 0")


def links_sql(p: str) -> str:
    return ("SELECT l.new_ozelgunlerid AS day_id, k.new_kitapId AS book_id, k.new_name AS name, k.new_ean13 AS ean"
            f" FROM {p}new_new_kitap_new_ozelgunlerBase l JOIN {p}new_kitapBase k ON k.new_kitapId = l.new_kitapid"
            " WHERE k.statecode = 0 AND k.new_ean13 IS NOT NULL")


def _crm_date(v: Any) -> Optional[str]:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v)[:19]) + timedelta(hours=CRM_UTC_OFFSET_HOURS)
    except ValueError:
        return None
    return f"{d.month:02d}-{d.day:02d}"


def read_crm(schema: str, execute: Callable[[str, int], Any]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """CRM özel günleri (aynı ada sahip kayıtlar birleşir) ve gün anahtarı başına kitaplar (barkod tekil)."""
    from semantic_bridge.editorial import _prefix

    p = _prefix(schema)

    def rows(sql: str) -> list[dict[str, Any]]:
        _, out, truncated = execute(sql, LIMIT)
        if truncated:
            raise RuntimeError("CRM sonucu kesildi; eksik veriyle takvim kurulmaz.")
        return out

    days: dict[str, dict[str, Any]] = {}
    by_id: dict[str, str] = {}
    for r in rows(days_sql(p)):
        name = crm.clean(r.get("name"))
        if not name:
            continue
        key = slug(name)
        d = days.setdefault(key, {"key": key, "name": name, "source": "crm", "crmIds": [], "weekFrom": None,
                                  "weekTo": None, "fixedDate": None, "web": False})
        d["crmIds"].append(str(r["id"]))
        d["web"] = d["web"] or bool(r.get("web"))
        if r.get("w1") and not d["weekFrom"]:
            d["weekFrom"], d["weekTo"] = int(r["w1"]), int(r.get("w2") or r["w1"])
        d["fixedDate"] = d["fixedDate"] or _crm_date(r.get("dt"))
        by_id[str(r["id"]).upper()] = key
    books: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows(links_sql(p)):
        key = by_id.get(str(r["day_id"]).upper())
        ean = crm.ean_key(r.get("ean"))
        if not key or len(ean) < 8:
            continue
        books.setdefault(key, {}).setdefault(ean[:20], {"ean": ean[:20], "bookId": str(r["book_id"]), "name": crm.clean(r.get("name"))})
    return list(days.values()), {k: list(v.values()) for k, v in books.items()}


def merge_builtin(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Kodda tanımlı günler, CRM'de aynı kurala düşen gün yoksa eklenir."""
    have_rules = {id(rule_for(d["name"])) for d in days if rule_for(d["name"])}
    have_keys = {d["key"] for d in days}
    out = list(days)
    for name in BUILTIN:
        r = rule_for(name)
        key = slug(name)
        if key in have_keys or (r is not None and id(r) in have_rules):
            continue
        out.append({"key": key, "name": name, "source": "kural", "crmIds": [], "weekFrom": None, "weekTo": None,
                    "fixedDate": None, "web": False})
    return out


# ================================================================================================ yenileme

def _crm_configured() -> bool:
    import os

    from semantic_bridge import admin as admin_mod

    return bool(admin_mod.conf("CRM_SCHEMA")) and bool(crm.CONNECTION_FILE) and os.path.exists(crm.CONNECTION_FILE)


def _load_days(seo) -> list[dict[str, Any]]:
    eng, tenant = seo.engine(), seo.tenant()
    ensure_tables(eng)
    with eng.connect() as c:
        rows = c.execute(sa.select(DAYS).where(DAYS.c.tenant_id == tenant)).mappings().all()
    out = [{"key": r["day_key"], "name": r["name"], "source": r["source"], "crmIds": loads(r["crm_ids"], []),
            "weekFrom": r["week_from"], "weekTo": r["week_to"], "fixedDate": r["fixed_date"], "web": bool(r["web"]),
            "crmBooks": r["crm_books"], "keywords": loads(r["keywords_json"], []), "uplift": loads(r["uplift_json"], None),
            "syncedAt": iso(r["synced_at"])} for r in rows]
    if not out:  # ilk okumadan önce de hareketli günler görünsün
        out = [{**d, "crmBooks": 0, "keywords": [" ".join(k) for k in keywords(d["name"])], "uplift": None, "syncedAt": None}
               for d in merge_builtin([])]
    return out


def _gsc_scan(seo, entries: list[tuple[str, list[str]]], today: date) -> tuple[dict[date, dict[str, float]], dict[date, float], set[date]]:
    """Eksik haftaları okur, saklar; bütün haftaların anahtar → gösterim tablosunu döndürür."""
    eng, tenant = seo.engine(), seo.tenant()
    sig = signature(entries)
    weeks = gsc_weeks(today)
    with eng.connect() as c:
        cached = {r["week"]: r for r in c.execute(sa.select(WEEKS).where(WEEKS.c.tenant_id == tenant)).mappings().all()}
    index = build_index(entries)
    per_week: dict[date, dict[str, float]] = {}
    read = 0
    for w in weeks:
        k = w.isoformat()
        r = cached.get(k)
        if r is not None and r["sig"] == sig:
            per_week[w] = loads(r["data_json"], {})
            continue
        rows = connections.gsc_all(k, (w + timedelta(days=6)).isoformat(), ["query"])
        per_week[w] = scan(rows, index)
        read += 1
        with eng.begin() as c:
            c.execute(WEEKS.delete().where(WEEKS.c.tenant_id == tenant, WEEKS.c.week == k))
            c.execute(WEEKS.insert().values(tenant_id=tenant, week=k, sig=sig, data_json=dumps(per_week[w]), saved_at=now()))
    with eng.begin() as c:  # 16 aydan eskiyen haftalar
        if weeks:
            c.execute(WEEKS.delete().where(WEEKS.c.tenant_id == tenant, WEEKS.c.week < weeks[0].isoformat()))
    site: dict[date, float] = {}
    if weeks:
        site = weekly(connections.gsc_all(weeks[0].isoformat(), (weeks[-1] + timedelta(days=6)).isoformat(), ["date"]))
    state["weeksRead"] = read
    return per_week, site, set(weeks)


def refresh(seo, today: Optional[date] = None) -> dict[str, Any]:
    """CRM günleri ve kitap bağları + (bağlıysa) Search Console geçen yıl artışı. Tabloların son hâlini yazar."""
    from semantic_bridge import admin as admin_mod

    today = today or date.today()
    eng, tenant = seo.engine(), seo.tenant()
    ensure_tables(eng)
    if _crm_configured():
        con = crm.connector()
        try:
            crm_days, books = read_crm(admin_mod.conf("CRM_SCHEMA"), con.execute)
        finally:
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass
    else:  # CRM yoksa var olan kayıt korunur
        prev = [d for d in _load_days(seo) if d["source"] == "crm"]
        crm_days = prev
        with eng.connect() as c:
            books = {}
            for r in c.execute(sa.select(BOOKS).where(BOOKS.c.tenant_id == tenant)).mappings().all():
                books.setdefault(r["day_key"], []).append({"ean": r["ean"], "bookId": r["book_id"], "name": r["name"]})
    days = merge_builtin(crm_days)
    for d in days:
        d["keywords"] = keywords(d["name"])
    entries = [(f"d:{d['key']}", kw) for d in days for kw in d["keywords"]]
    book_kw = {b["ean"]: book_keywords(b.get("name") or "") for bs in books.values() for b in bs}
    entries += [(f"b:{ean}", kw) for ean, kws in book_kw.items() for kw in kws]
    day_uplift: dict[str, Any] = {}
    book_uplift: dict[tuple[str, str], Any] = {}
    gsc_error = None
    if connections.service_account_email():
        try:
            per_week, site, have = _gsc_scan(seo, entries, today)
            for d in days:
                how = resolve(d)
                nxt = next_occurrence(how, today)
                prev_occ = previous_occurrence(how, nxt[0]) if nxt else None
                if not prev_occ:
                    continue
                series = {w: v.get(f"d:{d['key']}", 0.0) for w, v in per_week.items()}
                day_uplift[d["key"]] = uplift(series, site, prev_occ[0], have)
                for b in books.get(d["key"], []):
                    if book_kw.get(b["ean"]):
                        bs = {w: v.get(f"b:{b['ean']}", 0.0) for w, v in per_week.items()}
                        book_uplift[(d["key"], b["ean"])] = uplift(bs, site, prev_occ[0], have)
        except Exception as e:  # noqa: BLE001 — Search Console düşerse CRM günleri yine yazılır
            gsc_error = str(e)[:500]
            log.warning("sezon takvimi Search Console okuması başarısız: %s", gsc_error)
    stamp = now()
    with eng.begin() as c:
        old = {r[0]: r[1] for r in c.execute(sa.select(DAYS.c.day_key, DAYS.c.uplift_json).where(DAYS.c.tenant_id == tenant)).all()}
        c.execute(DAYS.delete().where(DAYS.c.tenant_id == tenant))
        c.execute(BOOKS.delete().where(BOOKS.c.tenant_id == tenant))
        for d in days:
            up = day_uplift.get(d["key"])
            c.execute(DAYS.insert().values(
                tenant_id=tenant, day_key=d["key"], name=d["name"][:300], source=d["source"], crm_ids=dumps(d["crmIds"]),
                week_from=d.get("weekFrom"), week_to=d.get("weekTo"), fixed_date=d.get("fixedDate"), web=bool(d.get("web")),
                crm_books=len(books.get(d["key"], [])), keywords_json=dumps([" ".join(k) for k in d["keywords"]]),
                # Search Console bu tur okunamadıysa önceki ölçüm korunur
                uplift_json=dumps(up) if up is not None else (old.get(d["key"]) if gsc_error else None), synced_at=stamp))
        vals = [dict(tenant_id=tenant, day_key=k, ean=b["ean"], book_id=b["bookId"], name=(b.get("name") or "")[:500],
                     uplift_json=dumps(book_uplift[(k, b["ean"])]) if book_uplift.get((k, b["ean"])) else None, synced_at=stamp)
                for k, bs in books.items() if k in {d["key"] for d in days} for b in bs]
        for i in range(0, len(vals), 1000):
            c.execute(BOOKS.insert(), vals[i:i + 1000])
    state["gscError"] = gsc_error
    return {"days": len(days), "books": len(vals), "measured": sum(1 for v in day_uplift.values() if v), "gscError": gsc_error}


def start_refresh(seo, user: str) -> bool:
    if not _run_lock.acquire(blocking=False):
        return False
    state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)

    def job() -> None:
        try:
            out = refresh(seo)
            state.update(days=out["days"], books=out["books"])
            log.info("seo seasons refresh (%s): %s", user, out)
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)[:1000]
            log.exception("seo seasons refresh failed")
        finally:
            state.update(running=False, finishedAt=iso(now()))
            _run_lock.release()

    threading.Thread(target=job, name="seo-seasons", daemon=True).start()
    return True


# ================================================================================================ ekran verisi

_EAN = sa.func.regexp_replace(sa.func.coalesce(sa.cast(PRODUCTS.c.data_json, sa.JSON)["Barcode"].as_string(), ""), "[^0-9]", "", "g")
_SALES = sa.func.coalesce(sa.cast(sa.func.nullif(sa.func.regexp_replace(
    sa.cast(PRODUCTS.c.data_json, sa.JSON)["CountTotalSales"].as_string(), "[^0-9.]", "", "g"), ""), sa.Float), 0.0)


def _books_for(seo, keys: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Gün başına T-soft'ta aktif, CRM durum işareti olmayan kitaplar; çok satandan aza, hazırlık bilgisiyle."""
    if not keys:
        return {}
    tenant = seo.tenant()
    j = BOOKS.join(PRODUCTS, sa.and_(PRODUCTS.c.tenant_id == BOOKS.c.tenant_id, _EAN == BOOKS.c.ean, PRODUCTS.c.active.is_(True))) \
        .outerjoin(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == BOOKS.c.tenant_id, CRM_BOOKS.c.ean == BOOKS.c.ean))
    q = (sa.select(BOOKS.c.day_key, BOOKS.c.ean, BOOKS.c.uplift_json, PRODUCTS.c.product_id, PRODUCTS.c.name,
                   PRODUCTS.c.score, PRODUCTS.c.issues_json, _SALES.label("sales"), CRM_BOOKS.c.rights)
         .select_from(j).where(BOOKS.c.tenant_id == tenant, BOOKS.c.day_key.in_(keys), CRM_BOOKS.c.status_flag.is_(None))
         .order_by(BOOKS.c.day_key, _SALES.desc(), PRODUCTS.c.product_id))
    with seo.engine().connect() as c:
        rows = c.execute(q).mappings().all()
        pids = sorted({r["product_id"] for r in rows})
        latest: dict[str, str] = {}
        for i in range(0, len(pids), 1000):
            for pid, status in c.execute(sa.select(PROPOSALS.c.product_id, PROPOSALS.c.status).where(
                    PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.product_id.in_(pids[i:i + 1000]))
                    .order_by(PROPOSALS.c.created_at.desc())).all():
                latest.setdefault(pid, status)
    out: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for r in rows:
        if (r["day_key"], r["product_id"]) in seen:
            continue
        seen.add((r["day_key"], r["product_id"]))
        issues = loads(r["issues_json"], [])
        prop = latest.get(r["product_id"])
        out.setdefault(r["day_key"], []).append({
            "id": r["product_id"], "name": r["name"], "ean": r["ean"], "score": r["score"], "sales": int(r["sales"] or 0),
            "issues": [{"rule": i.get("rule"), "title": i.get("title"), "severity": i.get("severity")} for i in issues],
            "proposal": prop if prop in ("hazir", "onaylandi") else None, "rights": r["rights"],
            "readiness": readiness(r["score"], [i.get("severity") for i in issues], prop, r["rights"]),
            "uplift": loads(r["uplift_json"], None)})
    return out


def _guides(seo) -> Optional[list[str]]:
    """Reddedilmemiş rehber taslaklarının başlıkları; rehber tablosu yoksa None."""
    from .guides import GUIDES

    eng = seo.engine()
    if not sa.inspect(eng).has_table(GUIDES.name):
        return None
    with eng.connect() as c:
        return [t for (t,) in c.execute(sa.select(GUIDES.c.title).where(
            GUIDES.c.tenant_id == seo.tenant(), GUIDES.c.status != "reddedildi")).all() if t]


def guide_for(day_keywords: list[list[str]], titles: list[str]) -> list[str]:
    """Başlığında günün anahtar kelimelerinden biri geçen rehberler."""
    return [t for t in titles if any(matches(tokens(t), kw) for kw in day_keywords)]


def _counts(books: list[dict[str, Any]]) -> dict[str, int]:
    c = {k: 0 for k in READINESS_LABEL}
    for b in books:
        c[b["readiness"]["level"]] += 1
    return {"books": len(books), **c, "rightsWarning": sum(1 for b in books if b["readiness"]["rightsWarning"])}


def _day_view(d: dict[str, Any], today: date) -> dict[str, Any]:
    how = resolve(d)
    nxt = next_occurrence(how, today)
    base = {"id": d["key"], "name": d["name"], "source": d["source"], "web": d["web"], "crmBooks": d.get("crmBooks", 0),
            "keywords": d.get("keywords") or [" ".join(k) for k in keywords(d["name"])], "precision": how["precision"],
            "uncertaintyDays": how["uncertainty"], "dateWhy": how["why"],
            "crmWeeks": [d["weekFrom"], d["weekTo"]] if d.get("weekFrom") else None, "uplift": d.get("uplift")}
    if not nxt:
        return base | {"start": None, "end": None}
    return base | {"start": nxt[0].isoformat(), "end": nxt[1].isoformat()} | lead_window(nxt[0], nxt[1], today)


def calendar(seo, weeks: int, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    horizon = today + timedelta(weeks=weeks)
    loaded = _load_days(seo)
    views = [_day_view(d, today) for d in loaded]
    upcoming = sorted((v for v in views if v["start"] and date.fromisoformat(v["start"]) <= horizon),
                      key=lambda v: (v["start"], v["name"]))
    undated = sorted((v for v in views if not v["start"]), key=lambda v: v["name"])
    books = _books_for(seo, [v["id"] for v in upcoming])
    titles = _guides(seo)
    actions: list[dict[str, Any]] = []
    for v in upcoming:
        bs = books.get(v["id"], [])
        v["counts"] = _counts(bs)
        v["fix"] = [{"id": b["id"], "name": b["name"], "score": b["score"], "label": b["readiness"]["label"]}
                    for b in bs if b["readiness"]["level"] == "duzelt"]
        kws = [k.split() for k in v["keywords"]]
        v["guides"] = guide_for(kws, titles) if titles is not None else None
        if v["phase"] in ("hazirlik", "suruyor"):
            if v["fix"]:
                actions.append({"kind": "duzelt", "dayId": v["id"], "dayName": v["name"], "start": v["start"],
                                "text": f"{v['name']} için şu kitapların sayfasını şimdi düzeltin", "books": v["fix"]})
            if titles is not None and not v["guides"]:
                actions.append({"kind": "rehber", "dayId": v["id"], "dayName": v["name"], "start": v["start"],
                                "text": f"{v['name']} için rehber/liste sayfası yok"})
    return {"today": today.isoformat(), "weeks": weeks, "leadDays": LEAD_DAYS, "readyScore": READY_SCORE,
            "windowWeeks": WINDOW_WEEKS, "baselineWeeks": BASELINE_WEEKS,
            "connected": {"crm": _crm_configured(), "gsc": bool(connections.service_account_email())},
            "guidesAvailable": titles is not None, "state": state, "lastRefresh": max((d.get("syncedAt") or "" for d in loaded), default="") or None,
            "days": upcoming, "undated": undated, "actions": actions}


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


# ================================================================================================ uçlar

def register(app, ctx) -> None:
    seo = ctx.seo

    def nightly() -> None:
        start_refresh(seo, "zamanlayıcı")

    seo.nightly.append(("seasons", nightly))

    @app.get("/api/v1/seo-geo/seasons")
    def seo_seasons(request: Request, weeks: int = DEFAULT_WEEKS) -> dict[str, Any]:
        ctx.gate(request)
        if weeks < 1 or weeks > MAX_WEEKS:
            raise _err(422, f"Hafta sayısı 1 ile {MAX_WEEKS} arasında olmalı.")
        return calendar(seo, weeks)

    @app.get("/api/v1/seo-geo/seasons/{day_id}")
    def seo_season_day(request: Request, day_id: str, start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        today = date.today()
        day = next((d for d in _load_days(seo) if d["key"] == day_id), None)
        if day is None:
            raise _err(404, "Özel gün bulunamadı.")
        view = _day_view(day, today)
        books = _books_for(seo, [day_id]).get(day_id, [])
        titles = _guides(seo)
        view["guides"] = guide_for([k.split() for k in view["keywords"]], titles) if titles is not None else None
        start = max(0, start)
        return {"day": view | {"counts": _counts(books)}, "start": start, "total": len(books),
                "items": books[start:start + max(1, limit)], "leadDays": LEAD_DAYS, "readyScore": READY_SCORE,
                "connected": {"crm": _crm_configured(), "gsc": bool(connections.service_account_email())},
                "guidesAvailable": titles is not None}

    @app.post("/api/v1/seo-geo/seasons/refresh")
    def seo_seasons_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        started = start_refresh(seo, user)
        seo.audit(user, "run", "seasons", "Sezon takvimi okuması", {"started": started})
        return {"started": started, "state": state}
