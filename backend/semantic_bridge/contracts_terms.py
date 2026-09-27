"""M6 Sözleşmeler: sözleşme şartlarının tek tanımı.

Bir sözleşmenin şartları tek bir sözlüktür (`terms`). Portalda açılan taslak da, CRM'den gelip portalda
düzenlenen kayıt da aynı biçimi taşır; zeyilname bu sözlüğe yama uygular, hakediş bu sözlükten hesaplanır,
şablon bu sözlükten doldurulur. Alanların Türkçe adı, tipi ve CRM'deki karşılığı burada durur.

CRM seçim listeleri (2026-09-27, canlı CRM .28'de `StringMapBase` ile okundu):
    new_SozlesmeTipi   5 Telif Alış · 1 Telif Satış · 2 Taahhüt · 100000000 Hizmet
    new_TelifTipi      3 Tek Ödeme · 1 Baskıdan · 2 Satıştan · 7 Satıştan Kademeli · 4 Baskıdan Kademeli
                       · 5 Baskı + Satış · 8 Diğer
    new_telifturu      2 Net · 1 Brüt · 3 Değişken Net/Brüt
    new_sozlesmeparabirimi  1 TL · 2 USD · 3 EURO · 4 POUND · 6 YUAN
    statuscode         100000000 Aktif-Sözleşme · 100000006 Aktif (Proje) · 100000007 Aktif-Yenileme
                       · 1 Taslak · 100000004 Pasif · 100000005 Fesih
"""
from __future__ import annotations

import copy
import re
from datetime import date
from typing import Any, Optional


class ContractError(ValueError):
    """Kişiye olduğu gibi gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------------------------------ seçenekler

KINDS = {"telif-alis": "Telif alış", "telif-satis": "Telif satış", "taahhut": "Taahhüt", "hizmet": "Hizmet"}
KIND_FROM_CRM = {5: "telif-alis", 1: "telif-satis", 2: "taahhut", 100000000: "hizmet"}

PAYMENT_TYPES = {
    "tek": "Tek ödeme",
    "baski": "Baskıdan ödeme",
    "satis": "Satıştan ödeme",
    "satis-kademeli": "Satıştan kademeli ödeme",
    "baski-kademeli": "Baskıdan kademeli ödeme",
    "baski-satis": "Baskı + satış",
    "diger": "Diğer",
}
PAYMENT_FROM_CRM = {3: "tek", 1: "baski", 2: "satis", 7: "satis-kademeli", 4: "baski-kademeli", 5: "baski-satis", 8: "diger"}
#: Satıştan hesaplanan ödeme şekilleri (hakedişte Logo satışı okunur).
SALES_BASED = ("satis", "satis-kademeli", "baski-satis")
#: Baskıdan hesaplanan ödeme şekilleri (hakedişte baskı adedi okunur).
PRINT_BASED = ("baski", "baski-kademeli", "baski-satis")
TIERED = ("satis-kademeli", "baski-kademeli")

BASES = {"net": "Net satış tutarı üzerinden", "brut": "Kapak (liste) fiyatı üzerinden", "degisken": "Değişken (net/brüt)"}
BASIS_FROM_CRM = {2: "net", 1: "brut", 3: "degisken"}

CURRENCIES = {"TRY": "TL", "USD": "USD", "EUR": "EURO", "GBP": "POUND", "CNY": "YUAN"}
CURRENCY_FROM_CRM = {1: "TRY", 2: "USD", 3: "EUR", 4: "GBP", 6: "CNY"}

STATUSES = {
    "taslak": "Taslak",
    "imzada": "İmza sürecinde",
    "yururlukte": "Yürürlükte",
    "sona-erdi": "Süresi bitti",
    "feshedildi": "Feshedildi",
    "iptal": "İptal",
}
STATUS_FROM_CRM = {100000000: "yururlukte", 100000006: "yururlukte", 100000007: "yururlukte", 1: "taslak",
                   100000004: "sona-erdi", 100000005: "feshedildi"}
#: İzin verilen geçişler. Yürürlükteki sözleşmenin şartı yalnız zeyilnameyle değişir.
TRANSITIONS = {
    "taslak": ("imzada", "yururlukte", "iptal"),
    "imzada": ("taslak", "yururlukte", "iptal"),
    "yururlukte": ("sona-erdi", "feshedildi"),
    "sona-erdi": ("yururlukte",),
    "feshedildi": (),
    "iptal": ("taslak",),
}
#: Bu durumlarda şartlar serbestçe düzenlenir; diğerlerinde düzeltme gerekçesi istenir.
FREE_EDIT = ("taslak", "imzada")

RATE_KEYS = {"karton": "Karton kapak", "sert": "Sert kapak", "ekitap": "E-kitap", "sesli": "Sesli kitap", "yurtdisi": "Yurtdışı satış"}
RIGHT_KEYS = {
    "cogaltma": "Çoğaltma", "yayma": "Yayma", "iletim": "İşaretle, sesle ve/veya görüntü nakline yarayan araçlarla umuma iletim",
    "islenme": "İşleme", "temsil": "Temsil", "ekitap": "E-kitap", "sesli": "Sesli kitap", "ceviri": "Başka dillere çeviri",
}
RIGHT_FROM_CRM = {"new_cogaltmahakki": "cogaltma", "new_yaymahakki": "yayma", "new_iletimhakki": "iletim",
                  "new_islemehakki": "islenme", "new_tamsilhakki": "temsil", "new_EKitap": "ekitap",
                  "new_SesliKitapHakki": "sesli", "new_baskadilleretercume": "ceviri"}
PARTY_ROLES = {"yazar": "Yazar", "cevirmen": "Çevirmen", "cizer": "Çizer", "ajans": "Ajans / yayınevi", "mirasci": "Mirasçı", "diger": "Diğer"}

#: Alanın Türkçe adı; değişiklik geçmişinde, zeyilnamede ve farkta bu ad yazılır.
LABELS: dict[str, str] = {
    "title": "Sözleşme adı", "kind": "Sözleşme türü", "company": "Yayınevi tarafı", "parties": "Taraflar",
    "books": "Kitaplar", "paymentType": "Ödeme şekli", "basis": "Telif esası", "tiers": "Kademeler",
    "discountPct": "Telif hesaplama iskontosu", "currency": "Para birimi", "advance": "Avans",
    "advanceRecoupable": "Avans telifden düşülür", "flatFee": "Tek ödeme tutarı", "withholdingPct": "Stopaj oranı",
    "start": "Başlangıç", "end": "Bitiş", "openEnded": "Süresiz", "years": "Süre (yıl)",
    "periodMonths": "Hakediş dönemi (ay)", "paymentDays": "Ödeme vadesi (gün)", "printRun": "İlk baskı adedi",
    "territory": "Bölge", "language": "Dil", "notes": "Notlar",
    **{f"rates.{k}": f"{v} telifi" for k, v in RATE_KEYS.items()},
    **{f"rights.{k}": f"{v} hakkı" for k, v in RIGHT_KEYS.items()},
}

_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def empty_terms() -> dict[str, Any]:
    return {
        "title": "", "kind": "telif-alis", "company": "", "parties": [], "books": [],
        "paymentType": "satis", "basis": "net", "rates": {}, "tiers": [], "discountPct": None,
        "currency": "TRY", "advance": None, "advanceRecoupable": True, "flatFee": None, "withholdingPct": None,
        "start": None, "end": None, "openEnded": False, "years": None,
        "periodMonths": 6, "paymentDays": 30, "printRun": None,
        "territory": "", "language": "", "rights": {}, "notes": "",
    }


# ------------------------------------------------------------------------------------------ doğrulama

def _text(v: Any, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _num(v: Any, label: str, *, lo: float = 0, hi: Optional[float] = None) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        x = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        raise ContractError(f"«{label}» sayı olmalı.") from None
    if x != x or x < lo or (hi is not None and x > hi):
        raise ContractError(f"«{label}» {lo:g}" + (f"–{hi:g}" if hi is not None else " ya da üstü") + " arasında olmalı.")
    return round(x, 4)


def _int(v: Any, label: str, *, lo: int = 0, hi: Optional[int] = None) -> Optional[int]:
    x = _num(v, label, lo=lo, hi=hi)
    if x is None:
        return None
    if x != int(x):
        raise ContractError(f"«{label}» tam sayı olmalı.")
    return int(x)


def _day(v: Any, label: str) -> Optional[str]:
    t = str(v or "").strip()[:10]
    if not t:
        return None
    if not _DAY.match(t):
        raise ContractError(f"«{label}» YYYY-AA-GG biçiminde olmalı.")
    try:
        date.fromisoformat(t)
    except ValueError:
        raise ContractError(f"«{label}» geçerli bir tarih değil.") from None
    return t


def _choice(v: Any, options: dict[str, str], label: str) -> str:
    t = str(v or "").strip()
    if t not in options:
        raise ContractError(f"«{label}» için geçersiz seçim: {t or 'boş'}.")
    return t


def _parties(v: Any) -> list[dict[str, Any]]:
    out = []
    for i, p in enumerate(v or []):
        if not isinstance(p, dict):
            raise ContractError("Taraf bilgisi geçersiz.")
        name = _text(p.get("name"), 200)
        if not name:
            raise ContractError(f"{i + 1}. tarafın adı boş.")
        role = str(p.get("role") or "diger")
        out.append({
            "name": name,
            "role": role if role in PARTY_ROLES else "diger",
            "share": _num(p.get("share"), f"{name} payı", hi=100),
            "contactId": _text(p.get("contactId"), 40) or None,
            "accountId": _text(p.get("accountId"), 40) or None,
            "viaAgent": bool(p.get("viaAgent")),
        })
    return out[:50]


def _books(v: Any) -> list[dict[str, Any]]:
    out = []
    for b in v or []:
        if not isinstance(b, dict):
            raise ContractError("Kitap bilgisi geçersiz.")
        title = _text(b.get("title"), 300)
        if not title:
            raise ContractError("Kitap adı boş olamaz.")
        fmt = str(b.get("format") or "karton")
        out.append({
            "id": _text(b.get("id"), 40) or None,
            "title": title,
            "stockCode": _text(b.get("stockCode"), 60) or None,
            "isbn": _text(b.get("isbn"), 20) or None,
            "format": fmt if fmt in RATE_KEYS else "karton",
            "listPrice": _num(b.get("listPrice"), f"{title} kapak fiyatı"),
        })
    return out[:200]


def _tiers(v: Any) -> list[dict[str, Any]]:
    out = []
    for t in v or []:
        if not isinstance(t, dict):
            raise ContractError("Kademe bilgisi geçersiz.")
        out.append({"from": _int(t.get("from"), "Kademe başlangıç adedi") or 0,
                    "rate": _num(t.get("rate"), "Kademe oranı", hi=100) or 0})
    out.sort(key=lambda t: t["from"])
    if out and out[0]["from"] != 0:
        raise ContractError("İlk kademe 0 adetten başlamalı.")
    if len({t["from"] for t in out}) != len(out):
        raise ContractError("Aynı adetten başlayan iki kademe var.")
    return out[:20]


def clean(raw: dict[str, Any], base: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """`raw` (tam ya da kısmi) → doğrulanmış şartlar. `base` verilirse üzerine yazılır (yama)."""
    if not isinstance(raw, dict):
        raise ContractError("Şartlar sözlük olmalı.")
    t = copy.deepcopy(base) if base else empty_terms()
    for k, v in empty_terms().items():
        t.setdefault(k, copy.deepcopy(v))
    L = LABELS
    for key, val in raw.items():
        if key == "title":
            t[key] = _text(val, 300)
        elif key in ("company", "territory", "language"):
            t[key] = _text(val, 200)
        elif key == "notes":
            t[key] = str(val or "").strip()[:5000]
        elif key == "kind":
            t[key] = _choice(val, KINDS, L[key])
        elif key == "paymentType":
            t[key] = _choice(val, PAYMENT_TYPES, L[key])
        elif key == "basis":
            t[key] = _choice(val, BASES, L[key])
        elif key == "currency":
            t[key] = _choice(val, CURRENCIES, L[key])
        elif key == "parties":
            t[key] = _parties(val)
        elif key == "books":
            t[key] = _books(val)
        elif key == "tiers":
            t[key] = _tiers(val)
        elif key == "rates":
            if not isinstance(val, dict):
                raise ContractError("Telif oranları sözlük olmalı.")
            rates = dict(t.get("rates") or {})
            for rk, rv in val.items():
                if rk not in RATE_KEYS:
                    raise ContractError(f"Bilinmeyen telif türü: {rk}.")
                n = _num(rv, L[f"rates.{rk}"], hi=100)
                if n is None:
                    rates.pop(rk, None)
                else:
                    rates[rk] = n
            t[key] = rates
        elif key == "rights":
            if not isinstance(val, dict):
                raise ContractError("Haklar sözlük olmalı.")
            rights = dict(t.get("rights") or {})
            for rk, rv in val.items():
                if rk not in RIGHT_KEYS:
                    raise ContractError(f"Bilinmeyen hak: {rk}.")
                rights[rk] = bool(rv)
            t[key] = rights
        elif key in ("discountPct", "withholdingPct"):
            t[key] = _num(val, L[key], hi=100)
        elif key in ("advance", "flatFee"):
            t[key] = _num(val, L[key])
        elif key == "years":
            t[key] = _num(val, L[key], hi=200)
        elif key == "periodMonths":
            t[key] = _int(val, L[key], lo=1, hi=24) or 6
        elif key == "paymentDays":
            t[key] = _int(val, L[key], hi=365)
        elif key == "printRun":
            t[key] = _int(val, L[key])
        elif key in ("start", "end"):
            t[key] = _day(val, L[key])
        elif key in ("openEnded", "advanceRecoupable"):
            t[key] = bool(val)
        else:
            raise ContractError(f"Bilinmeyen alan: {key}.")
    if t["start"] and t["end"] and t["end"] < t["start"]:
        raise ContractError("Bitiş tarihi başlangıçtan önce olamaz.")
    if t["openEnded"]:
        t["end"] = None
    return t


def warnings(t: dict[str, Any]) -> list[str]:
    """Kaydı durdurmayan ama hakedişi ya da metni eksik bırakacak durumlar."""
    out = []
    shares = [p["share"] for p in t.get("parties") or [] if p.get("share") is not None]
    if shares and abs(sum(shares) - 100) > 0.01:
        out.append(f"Tarafların payları toplamı %{sum(shares):g}; hakediş paylara bölünürken 100'e tamamlanmaz.")
    if t.get("paymentType") in SALES_BASED + PRINT_BASED:
        if not t.get("rates") and not t.get("tiers"):
            out.append("Telif oranı girilmemiş; hakediş hesaplanamaz.")
        if not any(b.get("stockCode") for b in t.get("books") or []):
            out.append("Kitapların stok kodu yok; Logo satışı ya da baskısı okunamaz.")
    if t.get("paymentType") in TIERED and not t.get("tiers"):
        out.append("Kademeli ödeme seçili ama kademe tanımlanmamış; düz oran kullanılır.")
    if t.get("paymentType") == "tek" and not t.get("flatFee"):
        out.append("Tek ödeme seçili ama tutar girilmemiş.")
    if not t.get("start"):
        out.append("Başlangıç tarihi yok.")
    if not t.get("openEnded") and not t.get("end"):
        out.append("Bitiş tarihi yok (süresiz de işaretlenmemiş).")
    if not t.get("parties"):
        out.append("Taraf girilmemiş.")
    return out


# ------------------------------------------------------------------------------------------ fark

def flatten(t: dict[str, Any]) -> dict[str, Any]:
    """Karşılaştırma ve etiket için düz anahtarlar: `rates.karton`, `rights.iletim`; liste alanları bütün."""
    out: dict[str, Any] = {}
    for k, v in (t or {}).items():
        if k in ("rates", "rights") and isinstance(v, dict):
            keys = RATE_KEYS if k == "rates" else RIGHT_KEYS
            for sk in keys:
                out[f"{k}.{sk}"] = v.get(sk)
        else:
            out[k] = v
    return out


def _norm(v: Any) -> Any:
    if v in ("", [], {}):
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    return v


def diff(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Değişen alanlar: [{field, label, old, new}] — alan sırası LABELS sırasıdır."""
    a, b = flatten(before or {}), flatten(after or {})
    out = []
    for key in LABELS:
        old, new = a.get(key), b.get(key)
        if key.startswith("rights."):
            old, new = bool(old), bool(new)
        if _norm(old) != _norm(new):
            out.append({"field": key, "label": LABELS[key], "old": old, "new": new})
    return out


def patch_of(changes: list[dict[str, Any]]) -> dict[str, Any]:
    """Zeyilnamedeki değişiklik listesi → `clean`'in anlayacağı yama."""
    patch: dict[str, Any] = {}
    for ch in changes:
        field = str(ch.get("field") or "")
        if field not in LABELS:
            raise ContractError(f"Zeyilnamede bilinmeyen alan: {field or 'boş'}.")
        if "." in field:
            group, sub = field.split(".", 1)
            patch.setdefault(group, {})[sub] = ch.get("new")
        else:
            patch[field] = ch.get("new")
    return patch


# ------------------------------------------------------------------------------------------ biçim

def show(field: str, v: Any, currency: str = "TRY") -> str:
    """Bir alan değerinin sözleşme metninde ve geçmişte görünen hâli."""
    if v is None or v == "" or v == []:
        return "—"
    if field.startswith("rights."):
        return "Var" if v else "Yok"
    if field.startswith("rates.") or field in ("discountPct", "withholdingPct"):
        return f"%{fmt_num(v)}"
    if field in ("advance", "flatFee"):
        return money(v, currency)
    if field in ("openEnded", "advanceRecoupable"):
        return "Evet" if v else "Hayır"
    if field in ("start", "end"):
        return day_tr(v)
    if field == "kind":
        return KINDS.get(v, str(v))
    if field == "paymentType":
        return PAYMENT_TYPES.get(v, str(v))
    if field == "basis":
        return BASES.get(v, str(v))
    if field == "currency":
        return CURRENCIES.get(v, str(v))
    if field == "parties":
        return "; ".join(p["name"] + (f" (%{fmt_num(p['share'])})" if p.get("share") is not None else "") for p in v)
    if field == "books":
        return "; ".join(b["title"] for b in v)
    if field == "tiers":
        return "; ".join(f"{fmt_num(t['from'])} adetten itibaren %{fmt_num(t['rate'])}" for t in v)
    if isinstance(v, float):
        return fmt_num(v)
    return str(v)


def fmt_num(v: Any, digits: int = 2) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = f"{x:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def money(v: Any, currency: str = "TRY") -> str:
    if v is None:
        return "—"
    return f"{fmt_num(v, 2)} {CURRENCIES.get(currency, currency)}"


_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def day_tr(v: Any) -> str:
    t = str(v or "")[:10]
    if not _DAY.match(t):
        return t or "—"
    y, m, d = t.split("-")
    return f"{int(d)} {_MONTHS[int(m) - 1]} {y}"


_ONES = ("", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz")
_TENS = ("", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan")
_GROUPS = ("", "bin", "milyon", "milyar", "trilyon")


def words(n: int) -> str:
    """Tam sayıyı Türkçe yazıya çevirir (sözleşmede tutarın yazıyla yazılışı): 12500 → onikibinbeşyüz."""
    n = int(n)
    if n == 0:
        return "sıfır"
    if n < 0:
        return "eksi" + words(-n)
    parts = []
    g = 0
    while n:
        n, chunk = divmod(n, 1000)
        if chunk:
            h, rest = divmod(chunk, 100)
            t, o = divmod(rest, 10)
            s = ("" if h == 0 else ("yüz" if h == 1 else _ONES[h] + "yüz")) + _TENS[t] + _ONES[o]
            if g == 1 and chunk == 1:
                s = ""  # "birbin" değil "bin"
            parts.append(s + _GROUPS[g])
        g += 1
    return "".join(reversed(parts))


def money_words(v: Any, currency: str = "TRY") -> str:
    if v is None:
        return "—"
    whole = int(float(v))
    cents = int(round((float(v) - whole) * 100))
    unit = {"TRY": ("Türk lirası", "kuruş"), "USD": ("ABD doları", "sent"), "EUR": ("avro", "sent"),
            "GBP": ("İngiliz sterlini", "peni"), "CNY": ("yuan", "fen")}.get(currency, (currency, ""))
    s = f"{words(whole)} {unit[0]}"
    if cents:
        s += f" {words(cents)} {unit[1]}"
    return s
