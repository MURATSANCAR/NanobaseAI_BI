"""İlişki defterlerinin ortak çekirdeği: M7 Yazar ilişkileri ve M28 Kurumsal ilişkiler (kanaat önderleri, kurumlar).

İki modül de aynı üç şeyi yapar: kişi/kurum için kart tutar, temas (görüşme notu) yazar, temaslardan bir «ilişki
ısısı» çıkarır. Bu dosya o ortak parçaları taşır; tablolar ve iş kuralları her modülün kendi dosyasındadır
(`author_relations.py`, `public_affairs.py`). Yeni bir ilişki modülü (M15/M16/M30/M31/M32/M37/M38) buradan alır, kopyalamaz.

- **Doğrulama yardımcıları** (`text_field`, `long_field`, `choice`, `str_list`, `guid`, `cid`, `norm`): kullanıcıdan
  gelen serbest metni kırpar, uzunluğu denetler, düz Türkçe `RelationError` atar.
- **Isı puanı** (`heat`): 0–100, yalnız insan temasından. Son temasın yakınlığı en çok 50 (180 günde sıfırlanır), son
  12 aydaki temas sayısı en çok 30 (temas başı 10), son üç temasın tonu en çok 20 (olumlu 20, nötr ya da tonsuz 10,
  olumsuz 0). Hiç temas yoksa 0 ve «temas yok»; 0–33 soğuk, 34–66 ılık, 67–100 sıcak. Hangi kaydın «yapılmış temas»,
  hangisinin «planlanan randevu» olduğu ve zamanının hangi alanda durduğu çağırana göre değişir (`done`, `planned`,
  `when`); varsayılanlar M7'nin görüşme tablosudur.
- **Gizli not** (`can_read`): «yalnız ben ve katılımcılar» işaretli kaydın metni yalnız yazana, katılımcılara ve
  ayrıcalıklı kişiye (yönetici ya da modülün hassas-not yetkisi) gider; kaydın varlığı ısıya yine sayılır.
- **CRM salt okuma** (`crm_prefix`, `like`): şema adı doğrulanır, serbest metin LIKE için kaçışlanır.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")

CHANNELS = {
    "yuz_yuze": "Yüz yüze",
    "telefon": "Telefon",
    "video": "Görüntülü",
    "eposta": "E-posta",
    "etkinlik": "Etkinlik",
    "diger": "Diğer",
}
TONES = {"olumlu": "Olumlu", "notr": "Nötr", "olumsuz": "Olumsuz"}

#: Isı puanı parçaları (modül başındaki tanım).
RECENCY_MAX, RECENCY_DAYS = 50, 180
FREQUENCY_MAX, FREQUENCY_EACH = 30, 10
TONE_MAX = 20
TONE_POINTS = {"olumlu": 20, "notr": 10, "olumsuz": 0, None: 10}
MONTHS = 12

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
ID_RE = re.compile(r"^[0-9a-f]{32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^[0-9+()\-\s./]{5,60}$")
URL_RE = re.compile(r"^https?://\S+$", re.I)


class RelationError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400, **extra: Any):
        super().__init__(message)
        self.status = status
        self.extra = extra


# ------------------------------------------------------------------------------------------ zaman


def now() -> datetime:
    return datetime.now(timezone.utc)


def utc(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)


def iso(v: Optional[datetime]) -> Optional[str]:
    v = utc(v)
    return v.isoformat() if v else None


def crm_day(v: Any) -> Optional[date]:
    """CRM tarihi (UTC saklanır) → İstanbul günü. Yalnız gün olan alanlar gece yarısından önceki UTC saatle gelir."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        d = v
    elif isinstance(v, date):
        return v
    else:
        try:
            d = datetime.fromisoformat(str(v).strip().replace(" ", "T").replace("Z", "+00:00"))
        except ValueError:
            return None
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(TZ).date()


# ------------------------------------------------------------------------------------------ doğrulama


def text_field(body: dict[str, Any], key: str, limit: int, label: str, *, required: bool = False) -> Optional[str]:
    v = body.get(key)
    t = re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""
    if required and not t:
        raise RelationError(f"{label} gerekli.")
    if len(t) > limit:
        raise RelationError(f"{label} en çok {limit} karakter olabilir.")
    return t or None


def long_field(body: dict[str, Any], key: str, limit: int, label: str) -> Optional[str]:
    v = body.get(key)
    t = str(v).replace("\r\n", "\n").strip() if v is not None else ""
    if len(t) > limit:
        raise RelationError(f"{label} en çok {limit} karakter olabilir.")
    return t or None


def choice(body: dict[str, Any], key: str, options: dict[str, str], label: str, default: Optional[str] = None) -> Optional[str]:
    v = body.get(key)
    if v in (None, ""):
        return default
    if v not in options:
        raise RelationError(f"{label} geçerli değil.")
    return str(v)


def str_list(body: dict[str, Any], key: str, limit: int, label: str) -> list[str]:
    v = body.get(key) or []
    if isinstance(v, str):
        v = [x for x in re.split(r"[,\n]", v)]
    if not isinstance(v, list):
        raise RelationError(f"{label} liste olmalı.")
    out: list[str] = []
    for x in v:
        t = re.sub(r"\s+", " ", str(x or "")).strip()
        if not t:
            continue
        if len(t) > limit:
            raise RelationError(f"{label} içindeki her değer en çok {limit} karakter olabilir.")
        if t.lower() not in (o.lower() for o in out):
            out.append(t)
    return out


def guid(v: Any, label: str = "CRM kişi kimliği") -> str:
    t = str(v or "").strip().strip("{}")
    if not GUID_RE.match(t):
        raise RelationError(f"{label} geçerli değil.")
    return t.lower()


def cid(v: Any, label: str = "Kayıt") -> str:
    t = str(v or "").strip().lower()
    if not ID_RE.match(t):
        raise RelationError(f"{label} bulunamadı.", 404)
    return t


def json_list(v: Optional[str]) -> list[Any]:
    try:
        out = json.loads(v or "[]")
        return out if isinstance(out, list) else []
    except ValueError:
        return []


def norm(name: str) -> str:
    """Arama ve karşılaştırma için sadeleştirilmiş metin: küçük harf, Türkçe harfler ASCII, yalnız harf/rakam."""
    t = (name or "").casefold().replace("ı", "i").replace("İ".casefold(), "i")
    for a, b in (("ç", "c"), ("ğ", "g"), ("ö", "o"), ("ş", "s"), ("ü", "u"), ("â", "a"), ("î", "i"), ("û", "u")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


# ------------------------------------------------------------------------------------------ katılımcı ve gizlilik


def participants(ps: Any) -> list[dict[str, str]]:
    """Katılımcı listesi: {username, display}, küçük harfli kullanıcı adıyla tekilleştirilmiş."""
    if ps in (None, ""):
        return []
    if not isinstance(ps, list):
        raise RelationError("Katılımcılar liste olmalı.")
    clean, seen = [], set()
    for p in ps:
        if not isinstance(p, dict):
            continue
        u = str(p.get("username") or "").strip().lower()[:120]
        d = re.sub(r"\s+", " ", str(p.get("display") or u)).strip()[:200]
        if u and u not in seen:
            seen.add(u)
            clean.append({"username": u, "display": d or u})
    return clean


def participant_names(participants_json: Optional[str]) -> set[str]:
    return {str(p.get("username") or "").lower() for p in json_list(participants_json) if isinstance(p, dict)}


def can_read(private: bool, created_by: Optional[str], participants_json: Optional[str], user: str, privileged: bool) -> bool:
    """Gizli («yalnız ben ve katılımcılar») kaydın metnini bu kişi görebilir mi."""
    if not private or privileged or created_by == user:
        return True
    return user in participant_names(participants_json)


# ------------------------------------------------------------------------------------------ ısı


def month_keys(at: Optional[datetime] = None, months: int = MONTHS) -> list[str]:
    """Son `months` ay (İstanbul), eskiden yeniye 'YYYY-AA'."""
    loc = (at or now()).astimezone(TZ)
    y, m = loc.year, loc.month
    out = []
    for _ in range(months):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def band(score: int) -> str:
    return "soguk" if score <= 33 else "ilik" if score <= 66 else "sicak"


def _is_done(m: Any) -> bool:
    return m.status == "yapildi"


def _is_planned(m: Any) -> bool:
    return m.status == "planlandi"


def _starts(m: Any) -> datetime:
    return m.starts_at


def heat(contacts: Iterable[Any], at: Optional[datetime] = None, *,
         done: Callable[[Any], bool] = _is_done, planned: Callable[[Any], bool] = _is_planned,
         when: Callable[[Any], datetime] = _starts) -> dict[str, Any]:
    """Temaslardan ısı puanı ve ay ay temas sayısı. Yalnız yapılmış temas sayılır; tonu `tone` alanından okunur."""
    at = at or now()
    keys = month_keys(at)
    by_month = {k: 0 for k in keys}
    items = list(contacts)
    made = sorted((m for m in items if done(m)), key=lambda m: utc(when(m)), reverse=True)
    upcoming = sorted((m for m in items if planned(m) and utc(when(m)) >= at), key=lambda m: utc(when(m)))
    year_ago = at - timedelta(days=365)
    in_year = 0
    for m in made:
        s = utc(when(m))
        k = s.astimezone(TZ).strftime("%Y-%m")
        if k in by_month:
            by_month[k] += 1
        if s >= year_ago:
            in_year += 1
    if not made:
        score, recency, freq, tone = 0, 0, 0, 0
        days = None
    else:
        days = max(0, (at - utc(when(made[0]))).days)
        recency = round(RECENCY_MAX * max(0.0, 1 - days / RECENCY_DAYS))
        freq = min(FREQUENCY_MAX, FREQUENCY_EACH * in_year)
        last3 = made[:3]
        tone = round(sum(TONE_POINTS.get(getattr(m, "tone", None), 10) for m in last3) / len(last3))
        score = recency + freq + tone
    return {"score": score, "band": band(score) if made else "yok",
            "parts": {"recency": recency, "frequency": freq, "tone": tone},
            "lastContact": iso(when(made[0])) if made else None, "daysSince": days,
            "contactsYear": in_year, "months": [by_month[k] for k in keys],
            "next": iso(when(upcoming[0])) if upcoming else None,
            "recencyFrom": "gorusme" if made else None, "lastTrace": None, "traceKind": None, "traceDays": None}


def heat_meta() -> dict[str, Any]:
    """Ekranda açıklama olarak gösterilen ısı tanımı."""
    return {"recencyMax": RECENCY_MAX, "recencyDays": RECENCY_DAYS, "frequencyMax": FREQUENCY_MAX,
            "frequencyEach": FREQUENCY_EACH, "toneMax": TONE_MAX, "months": MONTHS}


# ------------------------------------------------------------------------------------------ CRM (salt okuma)


def crm_prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not NAME_RE.match(part):
            raise RelationError(f"CRM şeması «{schema}» geçerli bir ad değil.", 503)
    if not sch:
        raise RelationError("CRM şeması girilmemiş; CRM okunamıyor.", 503)
    return (f"{db}." if db else "") + f"{sch}."


def like(text: str) -> str:
    """LIKE N'%…%' içine konacak kaçışlanmış metin (en çok 80 karakter)."""
    t = (text or "").strip()[:80].replace("'", "''")
    for ch in ("[", "%", "_"):
        t = t.replace(ch, f"[{ch}]")
    return t
