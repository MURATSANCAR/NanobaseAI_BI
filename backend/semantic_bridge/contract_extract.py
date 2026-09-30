"""Öneri 13 — M6 sözleşme belgesinden şart çıkarma (`/telif-sozlesme/yeni`, `/telif-sozlesme/:key`).

Yüklenen sözleşme belgesi (PDF/DOCX/ODT/görüntü; taranmış sayfa OCR) ortak belge okuma hattıyla okunur
(`doc_read`). Şartlar iki katta çıkarılır, ikisi de **birebir alıntı** ister:

1. **Kural** (model yok): belgenin her cümlesi anahtar sözcüklere bakılarak okunur (telif + yüzde → oran, avans +
   tutar → avans, para birimi, net/brüt, ödeme şekli, tarih ve süre, mali haklar, dil, biçim, münhasırlık). Alıntı
   cümlenin kendisidir.
2. **Zeki AI** (LLM kapısı, `rt.llm_for("sozlesme")`): uzun belge bölüm bölüm (`doc_extract.plan_windows`); her
   değer için JSON'da alıntı. Alıntı belgede birebir bulunmazsa değer atılır ve sayılır; kapalı kümeli alanlarda
   (ödeme şekli, esas, para birimi, telif türü, mali hak, biçim) değer kümede olmalı **ve** alıntıda o değerin
   sözcüğü geçmeli.

**Model sayı üretmez:** oran, tutar, tarih, süre alıntının kendisinden kodla okunur (`doc_extract.number_in`,
`date_in`, `years_in`); modelin yazdığı değer yalnız alıntıda birden çok sayı varsa hangisini kastettiğini seçer.
Aynı alana belgede farklı değerler çıkarsa alan boş kalır ve adaylar «çelişki» olarak alıntılarıyla gösterilir.

Alan adları sözleşme şartlarıyla (`contracts_terms`) birebir: `paymentType`, `basis`, `rates.<tür>`, `currency`,
`advance`, `flatFee`, `withholdingPct`, `start`, `end`, `years`, `language`, `territory`, `rights.<hak>`. Dil, ülke,
biçim, bitiş ve münhasırlık M54 hak haritasının (`rights_map`) alan adları ve değerleriyle aynıdır (`haklar`).
Öneri forma «önerilen» olarak gelir; kaydı insan yapar (portal sözleşme kaydı). **CRM'e yazma yok.**

Modele giden metin maskelidir: e-posta, telefon, IBAN, kart, kimlik no, etiketli kişi satırları (ad soyad, adres…),
bilinen taraf adları (`doc_extract.mask_all`). Alıntılar maskeli metne karşı denetlenir.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import contracts_terms as T
from semantic_bridge import doc_extract as X
from semantic_bridge import doc_read as DR
from semantic_bridge import zeki_text as Z

log = logging.getLogger("semantic.contract_extract")

_md = sa.MetaData()

EXTRACTS = sa.Table(
    "semantic_contract_extracts", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("contract_key", sa.String(64), index=True),         # portal kaydı ya da CRM kimliği; yeni taslakta sonradan
    sa.Column("filename", sa.String(300), nullable=False),
    sa.Column("bytes", sa.Integer, nullable=False),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("path", sa.String(600), nullable=False),
    sa.Column("status", sa.String(16), nullable=False),          # hazirlaniyor | hazir | hata
    sa.Column("done", sa.Integer, nullable=False, default=0),
    sa.Column("total", sa.Integer, nullable=False, default=0),
    sa.Column("result_json", sa.Text),
    sa.Column("error", sa.Text),
    sa.Column("accepted_json", sa.Text),                          # insanın forma aktardığı alanlar
    sa.Column("accepted_by", sa.String(120)),
    sa.Column("accepted_at", sa.DateTime(timezone=True)),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
)

MODULE = "sozlesme"
FILE_MAX = 10 * 1024 * 1024
ALLOWED = ("pdf", "docx", "odt", "txt") + tuple(DR.IMAGES)
STATUS = {"hazirlaniyor": "Hazırlanıyor", "hazir": "Hazır", "hata": "Hata"}

# ------------------------------------------------------------------------------------------ M54 hak haritası adları
#: rights_map main'e girdiğinde oradaki tanımlar kullanılır; o zamana kadar aynı adlar ve değerler burada.
FORMATS = {"basili": "Basılı", "e-kitap": "E-kitap", "sesli": "Sesli kitap", "film": "Film / dizi / sahne",
           "ceviri": "Çeviri", "dijital": "Dijital (genel)"}
EXCLUSIVITY = {"munhasir": "Münhasır", "munhasir-degil": "Münhasır değil"}
FORMAT_WORDS: dict[str, tuple[str, ...]] = {
    "e-kitap": ("e-kitap", "ekitap", "e kitap", "e-book", "ebook", "elektronik kitap", "elektronik yayin", "epub"),
    "sesli": ("sesli", "audio", "seslendirme", "ses kaydi"),
    "film": ("film", "dizi", "sinema", "sahne", "tiyatro", "uyarlama", "senaryo", "televizyon", "animasyon", "belgesel"),
    "basili": ("basili", "baski", "kagit", "ciltli", "karton kapak", "matbu", "print"),
    "ceviri": ("ceviri", "tercume", "translation"),
    "dijital": ("dijital", "elektronik", "internet", "online", "cevrimici", "digital"),
}
_EXCL = ("munhasir", "exclusive", "tek yetkili", "tek yetki")
_NEG = ("degil", "olmayan", "olmaksizin", "gayri", "non-exclusive", "non exclusive", "nonexclusive", "haric")
LANGUAGES = ("turkce", "ingilizce", "almanca", "fransizca", "arapca", "farsca", "rusca", "ispanyolca", "italyanca",
             "portekizce", "japonca", "cince", "korece", "azerice", "kurtce", "bosnakca", "arnavutca", "urduca",
             "malayca", "endonezyaca", "bulgarca", "yunanca", "felemenkce", "hollandaca", "lehce", "macarca", "romence",
             "sirpca", "hirvatca", "ukraynaca", "kazakca", "ozbekce", "kirgizca", "turkmence", "tatarca", "uygurca",
             "gurcuce", "ermenice", "ibranice", "hintce", "bengalce", "isvecce", "norvecce", "danca", "fince", "cekce",
             "slovakca", "slovence", "makedonca", "osmanlica", "latince")
try:  # pragma: no cover — M54 hak haritası varsa tek tanım oradan
    from semantic_bridge import rights_map as _RM

    FORMATS, EXCLUSIVITY, FORMAT_WORDS, LANGUAGES = _RM.FORMATS, _RM.EXCLUSIVITY, _RM.FORMAT_WORDS, _RM.LANGUAGES
except Exception:  # noqa: BLE001
    _RM = None

#: Biçim hakkı → sözleşme şartlarındaki mali hak anahtarı (forma aktarılırken).
FORMAT_TO_RIGHT = {"e-kitap": "ekitap", "sesli": "sesli", "ceviri": "ceviri"}

# ------------------------------------------------------------------------------------------ sözcükler (katlanmış)
RATE_WORDS: dict[str, tuple[str, ...]] = {
    "ekitap": ("e-kitap", "e kitap", "ekitap", "elektronik kitap", "e-book", "ebook", "dijital"),
    "sesli": ("sesli kitap", "sesli", "audio"),
    "sert": ("sert kapak", "ciltli", "bez cilt"),
    "yurtdisi": ("yurt disi", "yurtdisi", "yabanci ulke", "ihracat"),
    "karton": ("karton kapak", "karton"),
}
BASIS_WORDS = {"net": ("net satis", "net tutar", "net hasilat", "net gelir", "net fatura", "net bedel"),
               "brut": ("brut", "kapak fiyat", "liste fiyat", "perakende satis fiyat", "etiket fiyat", "piyasa satis fiyat")}
PAY_WORDS = {"tek": ("tek odeme", "tek seferde", "maktu", "gotur", "defaten", "toptan odeme", "bir defaya mahsus"),
             "baski": ("basilan", "baski adedi", "her baski", "tiraj", "basim adedi", "basilacak"),
             "satis": ("satilan", "satis adedi", "satis tutar", "net satis", "satis hasilat", "satislardan", "satistan"),
             "kademe": ("kademe", "kademeli")}
RIGHT_WORDS: dict[str, tuple[str, ...]] = {
    "cogaltma": ("cogaltma", "cogaltilma", "cogaltim"),
    "yayma": ("yayma", "yayilma"),
    "iletim": ("umuma iletim", "isaret, ses", "isaret ses", "iletim"),
    "islenme": ("isleme hakk", "islenme", "isleme,", "isleme ve"),
    "temsil": ("temsil",),
    "ekitap": ("e-kitap", "e kitap", "ekitap", "elektronik kitap", "e-book"),
    "sesli": ("sesli kitap",),
    "ceviri": ("ceviri", "tercume", "baska dillere", "baska dile"),
}
_RIGHT_NEG = ("haric", "dahil degil", "devredilmemis", "devredilmez", "saklidir", "sakli tutul", "kapsam disi")
CURRENCY_RX = {
    "TRY": r"(?<![a-z])(tl|try|turk lirasi|turk lira)(?![a-z])|₺",
    "USD": r"(?<![a-z])(usd|dolar|dollar)(?![a-z])|\$",
    "EUR": r"(?<![a-z])(eur|euro|avro)(?![a-z])|€",
    "GBP": r"(?<![a-z])(gbp|sterlin|pound)(?![a-z])|£",
    "CNY": r"(?<![a-z])(cny|yuan|rmb)(?![a-z])",
}
_TAX = ("kdv", "katma deger", "damga vergisi")
_END = ("bitis", "bitim", "sona er", "kadar", "gecerli", "suresi", "tarihine")
_START = ("baslangic", "yururluge gir", "itibaren", "tarihinden")

SYSTEM = ("Sen Zeki AI'sın; telif sözleşmesi belgesinden şartları çıkarırsın. Yalnız verilen bölümde yazanı çıkar; "
          "tahmin etme, sayı, tarih ya da ülke uydurma. Her değer için bölümden AYNEN kopyalanmış kısa bir alıntı ver; "
          "sayı içeren alanlarda alıntı o sayıyı içermeli. Bölümde olmayan alanı boş bırak. Köşeli ayraç içindeki yer "
          "tutucuları olduğu gibi bırak. Sadece JSON yaz.")
SCHEMA = ('{"oran": [{"tur": "karton | sert | ekitap | sesli | yurtdisi | genel", "deger": "%…", "alinti": ""}], '
          '"taban": {"deger": "net | brut | degisken", "alinti": ""}, '
          '"tip": {"deger": "' + " | ".join(T.PAYMENT_TYPES) + '", "alinti": ""}, '
          '"avans": {"deger": "tutar", "alinti": ""}, "tek_odeme": {"deger": "tutar", "alinti": ""}, '
          '"para_birimi": {"deger": "' + " | ".join(T.CURRENCIES) + '", "alinti": ""}, '
          '"stopaj": {"deger": "%…", "alinti": ""}, '
          '"baslangic": {"deger": "tarih", "alinti": ""}, "bitis": {"deger": "tarih", "alinti": ""}, '
          '"sure": {"deger": "süre", "alinti": ""}, '
          '"dil": [{"deger": "dilin adı", "alinti": ""}], "ulke": [{"deger": "ülke ya da bölge", "alinti": ""}], '
          '"format": [{"deger": "' + " | ".join(FORMATS) + '", "alinti": ""}], '
          '"munhasirlik": {"deger": "munhasir | munhasir-degil", "alinti": ""}, '
          '"mali_haklar": [{"deger": "' + " | ".join(T.RIGHT_KEYS) + '", "alinti": ""}]}')


class ExtractError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if v is not None else None


def _f(s: Any) -> str:
    return " ".join(Z.fold(s).replace("'", " ").replace("’", " ").split())


def _has(text: str, words: tuple[str, ...]) -> bool:
    f = " " + _f(text) + " "
    return any(w in f for w in words)


# ================================================================================ alan okuyucular (saf)
# Her okuyucu (alıntı, modelin değeri ya da None) → değer ya da None. Değer alıntıdan okunur.


def rate_key(quote: str, claimed: Any = None) -> str:
    for k in ("ekitap", "sesli", "sert", "yurtdisi", "karton"):
        if _has(quote, RATE_WORDS[k]):
            return k
    c = _f(claimed)
    return c if c in T.RATE_KEYS and c != "karton" and _has(quote, RATE_WORDS.get(c, ())) else "karton"


def read_rate(quote: str, claimed: Any = None) -> Optional[float]:
    """Telif oranı: alıntıda «telif» (ya da «pay/oran») ve tek yüzde. KDV/stopaj/iskonto cümlesi oran sayılmaz."""
    if not _has(quote, ("telif", "royalt", "pay ", "payi", "oran")) or _has(quote, _TAX + ("stopaj", "iskonto", "indirim")):
        return None
    v = X.number_in(quote, claimed, percent=True)
    return v if v is not None and 0 < v <= 100 else None


def read_withholding(quote: str, claimed: Any = None) -> Optional[float]:
    if not _has(quote, ("stopaj", "gelir vergisi kesinti", "vergi kesinti")):
        return None
    v = X.number_in(quote, claimed, percent=True)
    return v if v is not None and 0 < v <= 100 else None


def read_amount(quote: str, claimed: Any = None, words: tuple[str, ...] = ("avans", "pesin")) -> Optional[float]:
    if not _has(quote, words):
        return None
    v = X.number_in(quote, claimed, percent=False)
    return v if v is not None and v > 0 else None


def read_currency(quote: str, claimed: Any = None) -> Optional[str]:
    f = _f(quote)
    found = [k for k, rx in CURRENCY_RX.items() if re.search(rx, f) or re.search(rx, str(quote))]
    if len(found) == 1:
        return found[0]
    c = str(claimed or "").strip().upper()
    return c if c in found else None


def read_basis(quote: str, claimed: Any = None) -> Optional[str]:
    net, brut = _has(quote, BASIS_WORDS["net"]), _has(quote, BASIS_WORDS["brut"])
    c = _f(claimed)
    if c == "degisken":
        return "degisken" if net and brut else None
    if net and not brut:
        return "net"
    if brut and not net:
        return "brut"
    if net and brut and c in ("net", "brut"):
        return c
    return None


def read_payment(quote: str, claimed: Any = None) -> Optional[str]:
    tek, baski, satis, kademe = (_has(quote, PAY_WORDS[k]) for k in ("tek", "baski", "satis", "kademe"))
    by_words: Optional[str] = None
    if tek and not (baski or satis):
        by_words = "tek"
    elif kademe and satis and not baski:
        by_words = "satis-kademeli"
    elif kademe and baski and not satis:
        by_words = "baski-kademeli"
    elif baski and satis:
        by_words = "baski-satis"
    elif baski:
        by_words = "baski"
    elif satis:
        by_words = "satis"
    c = _f(claimed).replace(" ", "-")
    if c in T.PAYMENT_TYPES and c != "diger":
        need = {"tek": tek, "baski": baski, "satis": satis, "satis-kademeli": satis and kademe,
                "baski-kademeli": baski and kademe, "baski-satis": baski and satis}[c]
        return c if need else None
    return by_words if claimed in (None, "") else None


def read_dates(quote: str, claimed_start: Any = None, claimed_end: Any = None) -> tuple[Optional[str], Optional[str]]:
    """(başlangıç, bitiş). İki tarihli «… tarihinden … tarihine kadar» cümlesinde ilki başlangıç, sonuncusu bitiş."""
    ds = X.dates_in(quote)
    start = end = None
    if len(ds) == 2 and _has(quote, _START) and _has(quote, _END):
        start, end = ds[0], ds[1]
    elif len(ds) >= 1:
        if claimed_end not in (None, "") or (claimed_start in (None, "") and _has(quote, _END) and not _has(quote, ("itibaren",))):
            end = X.date_in(quote, claimed_end)
        if claimed_start not in (None, "") or (claimed_end in (None, "") and _has(quote, _START) and not _has(quote, _END)):
            start = X.date_in(quote, claimed_start)
    if start and end and end < start:
        return None, None
    return start, end


def read_years(quote: str, claimed: Any = None) -> Optional[float]:
    if not _has(quote, ("sure", "yil", "sene", " ay")):
        return None
    v = X.years_in(quote)
    return v if v is not None and 0 < v <= 200 else None


def read_rights(quote: str) -> list[str]:
    """Mali hak anahtarları (sözleşme şartlarındaki `rights`). Olumsuz cümle («hariç», «saklıdır») hak vermez."""
    if not _has(quote, ("hak",)) or _has(quote, _RIGHT_NEG):
        return []
    return [k for k, words in RIGHT_WORDS.items() if _has(quote, words)]


def exclusivity_of(quote: str) -> Optional[str]:
    q = _f(quote)
    if not any(w in q for w in _EXCL):
        return None
    return "munhasir-degil" if any(w in q for w in _NEG) else "munhasir"


def format_key(value: Any) -> Optional[str]:
    v = _f(value)
    for k, label in FORMATS.items():
        if v in (_f(k), _f(label)):
            return k
    return None


def formats_in(quote: str) -> list[str]:
    return [k for k, words in FORMAT_WORDS.items() if _has(quote, words)]


def languages_in(quote: str) -> list[str]:
    out = []
    for w in re.findall(r"[^\s.,;:()\"«»/]+", quote):
        base = re.split(r"['’]", w)[0]
        fb = _f(base)
        for lang in LANGUAGES:
            if fb.startswith(lang):
                word = base[:len(lang)]
                if word and _f(word) not in {_f(x) for x in out}:
                    out.append(word)
    return out


# ================================================================================ aday toplama


class Bag:
    """Alan → aday listesi. Aday: {deger, kanit, kaynak}. Aynı değer tekrar gelirse kanıtı eklenir."""

    def __init__(self) -> None:
        self.c: dict[str, list[dict[str, Any]]] = {}

    def add(self, field: str, value: Any, ev: dict[str, Any], source: str, **extra: Any) -> None:
        if value in (None, "", []):
            return
        lst = self.c.setdefault(field, [])
        for x in lst:
            if x["deger"] == value:
                if all(e["alinti"] != ev["alinti"] for e in x["kanit"]):
                    x["kanit"].append(ev)
                return
        lst.append({"deger": value, "kanit": [ev], "kaynak": source, **extra})


SINGLE = ("paymentType", "basis", "currency", "advance", "flatFee", "withholdingPct", "start", "end", "years",
          "bitis", "munhasirlik")
MULTI = ("rights", "dil", "ulke", "format")


def _ev_of(sentence: str, reading: DR.Reading) -> Optional[dict[str, Any]]:
    h = X.hit(sentence, reading)
    return X.evidence(sentence, h) if h else None


def rule_pass(reading: DR.Reading, bag: Bag) -> None:
    """Modelsiz çıkarım: her cümle anahtar sözcüklere bakılarak okunur; alıntı cümlenin kendisidir."""
    for p in reading.pages:
        for s in X.sentences(p.get("metin") or ""):
            if len(_f(s)) < 8:
                continue
            ev = None

            def e() -> Optional[dict[str, Any]]:
                nonlocal ev
                if ev is None:
                    ev = _ev_of(s, reading) or {}
                return ev or None

            r = read_rate(s)
            if r is not None and e():
                bag.add("rates." + rate_key(s), r, e(), "kural")
            w = read_withholding(s)
            if w is not None and e():
                bag.add("withholdingPct", w, e(), "kural")
            adv = read_amount(s)
            if adv is not None and e():
                bag.add("advance", adv, e(), "kural")
                bag.add("currency", read_currency(s), e(), "kural")
            flat = read_amount(s, words=PAY_WORDS["tek"]) if not _has(s, ("avans",)) else None
            if flat is not None and e():
                bag.add("flatFee", flat, e(), "kural")
                bag.add("currency", read_currency(s), e(), "kural")
            if _has(s, ("telif", "odeme", "hesaplan")):
                if e():
                    bag.add("basis", read_basis(s), e(), "kural")
                    if _has(s, ("telif",)):
                        bag.add("paymentType", read_payment(s), e(), "kural")
            if _has(s, ("para birimi", "doviz", "odeme para")) and e():
                bag.add("currency", read_currency(s), e(), "kural")
            if _has(s, _END + _START) and X.dates_in(s) and e():
                st, en = read_dates(s)
                bag.add("start", st, e(), "kural")
                bag.add("end", en, e(), "kural")
                if en:
                    bag.add("bitis", en, e(), "kural", tarih=en)
            if _has(s, ("sozlesme", "sure")) and _has(s, ("suresi", "sure ", "yil", "sene")) and e():
                y = read_years(s)
                if y is not None and not X.dates_in(s):
                    bag.add("years", y, e(), "kural")
            for k in read_rights(s):
                if e():
                    bag.add("rights", k, e(), "kural", ad=T.RIGHT_KEYS[k])
            if _has(s, ("hak", "lisans", "yayin")) and not _has(s, _RIGHT_NEG):
                for k in formats_in(s):
                    if e():
                        bag.add("format", k, e(), "kural", ad=FORMATS[k])
                for lang in languages_in(s):
                    if e():
                        bag.add("dil", lang, e(), "kural")
            ex = exclusivity_of(s)
            if ex and e():
                bag.add("munhasirlik", ex, e(), "kural", ad=EXCLUSIVITY[ex])


def model_pass(data: dict[str, Any], reading: DR.Reading, bag: Bag) -> int:
    """Bir pencerenin JSON'u → denetimden geçen adaylar; dönen: atılan değer sayısı."""
    dropped = 0

    def ev(q: str) -> Optional[dict[str, Any]]:
        return _ev_of(q, reading)

    def take(field: str, value: Any, q: str, **extra: Any) -> None:
        nonlocal dropped
        e = ev(q) if value not in (None, "", []) else None
        if e:
            bag.add(field, value, e, "zeki", **extra)
        else:
            dropped += 1

    for x in X.items(data.get("oran")):
        q = x["alinti"]
        take("rates." + rate_key(q, x.get("tur")), read_rate(q, x.get("deger")), q)
    for key, field, fn in (("stopaj", "withholdingPct", read_withholding), ("avans", "advance", read_amount),
                           ("para_birimi", "currency", read_currency), ("taban", "basis", read_basis),
                           ("tip", "paymentType", read_payment), ("sure", "years", read_years)):
        for x in X.items(data.get(key)):
            take(field, fn(x["alinti"], x.get("deger")), x["alinti"])
    for x in X.items(data.get("tek_odeme")):
        take("flatFee", read_amount(x["alinti"], x.get("deger"), words=PAY_WORDS["tek"] + ("odeme", "bedel", "ucret")),
             x["alinti"])
    for x in X.items(data.get("baslangic")):
        take("start", read_dates(x["alinti"], claimed_start=x.get("deger") or "?")[0], x["alinti"])
    for x in X.items(data.get("bitis")):
        en = read_dates(x["alinti"], claimed_end=x.get("deger") or "?")[1]
        take("end", en, x["alinti"])
        if en:
            take("bitis", en, x["alinti"], tarih=en)
    for x in X.items(data.get("mali_haklar")):
        k = _f(x.get("deger"))
        take("rights", k if k in T.RIGHT_KEYS and k in read_rights(x["alinti"]) else None, x["alinti"],
             ad=T.RIGHT_KEYS.get(k))
    for x in X.items(data.get("format")):
        k = format_key(x.get("deger"))
        ok = bool(k) and k in formats_in(x["alinti"]) and not _has(x["alinti"], _RIGHT_NEG)
        take("format", k if ok else None, x["alinti"], ad=FORMATS.get(k or ""))
    for x in X.items(data.get("dil")):
        v = " ".join(str(x.get("deger") or "").split())
        langs = languages_in(x["alinti"])
        take("dil", next((w for w in langs if _f(w) == _f(v)[:len(_f(w))]), None) if v else None, x["alinti"])
    for x in X.items(data.get("ulke")):
        v = " ".join(str(x.get("deger") or "").split())[:120]
        ok = len(_f(v)) >= 2 and _f(v) in _f(x["alinti"]) and Z.numbers_ok(v, x["alinti"])
        take("ulke", v if ok else None, x["alinti"])
    for x in X.items(data.get("munhasirlik")):
        ex = exclusivity_of(x["alinti"])
        take("munhasirlik", ex, x["alinti"], ad=EXCLUSIVITY.get(ex or ""))
    return dropped


# ================================================================================ sonuç


def resolve(bag: Bag) -> dict[str, Any]:
    """Tek değerli alanda farklı adaylar varsa değer boş, adaylar «çelişki». Çok değerli alanlar birleşir."""
    alanlar: dict[str, Any] = {}
    for field, cands in bag.c.items():
        if field in MULTI:
            continue
        if len(cands) == 1:
            alanlar[field] = {**cands[0], "celiski": None}
        else:
            alanlar[field] = {"deger": None, "kanit": [], "kaynak": None, "celiski": cands}
    haklar = {"dil": [], "ulke": [], "format": [], "bitis": None, "munhasirlik": None}
    for k in ("dil", "ulke", "format"):
        haklar[k] = [_rm_item(x) for x in bag.c.get(k, [])]
    for k in ("bitis", "munhasirlik"):
        a = alanlar.pop(k, None)
        if a and a.get("deger") is not None:
            haklar[k] = _rm_item(a)
    rights = [{"deger": x["deger"], "ad": T.RIGHT_KEYS[x["deger"]], "kanit": x["kanit"], "kaynak": x["kaynak"]}
              for x in bag.c.get("rights", [])]
    return {"alanlar": alanlar, "haklar": haklar, "maliHaklar": rights}


def _rm_item(x: dict[str, Any]) -> dict[str, Any]:
    """M54 hak haritasının kalem biçimi: {deger, alinti, kaynak, ad?, tarih?} + sayfa/okuma."""
    ev = x["kanit"][0]
    out = {"deger": x["deger"], "alinti": ev["alinti"], "kaynak": x["kaynak"], "sayfa": ev["sayfa"], "okuma": ev["okuma"]}
    for k in ("ad", "tarih"):
        if x.get(k):
            out[k] = x[k]
    return out


def suggestion(res: dict[str, Any]) -> dict[str, Any]:
    """Forma gidecek şart önerisi (sözleşme şartlarının alan adlarıyla). Yalnız çelişkisiz, alıntılı değerler."""
    a = res["alanlar"]
    out: dict[str, Any] = {}
    for f in ("paymentType", "basis", "currency", "advance", "flatFee", "withholdingPct", "start", "end", "years"):
        v = (a.get(f) or {}).get("deger")
        if v is not None:
            out[f] = v
    rates = {f.split(".", 1)[1]: x["deger"] for f, x in a.items() if f.startswith("rates.") and x.get("deger") is not None}
    if rates:
        out["rates"] = rates
    rights = {x["deger"]: True for x in res["maliHaklar"]}
    for x in res["haklar"]["format"]:
        if x["deger"] in FORMAT_TO_RIGHT:
            rights[FORMAT_TO_RIGHT[x["deger"]]] = True
    if rights:
        out["rights"] = rights
    h = res["haklar"]
    if h["dil"]:
        out["language"] = ", ".join(x["deger"] for x in h["dil"])[:200]
    if h["ulke"]:
        out["territory"] = ", ".join(x["deger"] for x in h["ulke"])[:200]
    if h["munhasirlik"]:
        m = h["munhasirlik"]
        out["notesLine"] = f"Münhasırlık: {EXCLUSIVITY.get(m['deger'], m['deger'])} (belge s. {m['sayfa']})"
    if out.get("end"):
        out["openEnded"] = False
    try:
        T.clean({k: v for k, v in out.items() if k != "notesLine"})     # öneri şart doğrulamasından geçmeli
    except T.ContractError as e:
        log.info("sözleşme şartı önerisi doğrulanamadı: %s", e)
        out["gecersiz"] = str(e)
    return out


def analyse(reading: DR.Reading, *, names: list[str], chat: Any, cfg: dict[str, Any],
            progress: Optional[Callable[[int, int], None]] = None) -> dict[str, Any]:
    """Okunmuş sözleşme → alıntılı şart adayları ve form önerisi. `chat` yoksa yalnız kural katı."""
    mreading = X.masked(reading, lambda t: X.mask_all(t, names))
    wins = X.plan_windows(mreading, cfg["windowChars"], cfg["overlap"])
    if not wins:
        why = " ".join(reading.errors)
        raise ExtractError("Belgeden metin okunamadı." + (f" {why}" if why else ""))
    total = len(wins) + 1 if chat is not None else 1
    if progress:
        progress(0, total)
    bag = Bag()
    rule_pass(mreading, bag)
    dropped, bad, used_model = 0, [], False
    if chat is not None:
        for n, w in enumerate(wins, start=1):
            prompt = (f"Sözleşme belgesinin {n}/{len(wins)}. bölümü (sayfa {w.span}). Şu JSON'u doldur (bulunmayan alan "
                      f"null ya da boş liste):\n{SCHEMA}\n\nTelif türleri: " + "; ".join(f"{k} = {v}" for k, v in T.RATE_KEYS.items())
                      + "; genel = türü belirtilmemiş\nMali haklar: " + "; ".join(f"{k} = {v}" for k, v in T.RIGHT_KEYS.items())
                      + f"\n\nBÖLÜM:\n{w.text}")
            try:
                raw = chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}])
            except Exception as e:  # noqa: BLE001 — pencere düşerse sayılır, kural sonucu kalır
                log.warning("sözleşme şartları: %d. bölüm için model cevap vermedi: %s", n, e)
                bad.append(w.span)
                raw = ""
            data = X.parse_json(raw)
            if X.unreadable_reply(raw, data):
                bad.append(w.span)
            if data:
                used_model = True
                dropped += model_pass(data, mreading, bag)
            if progress:
                progress(n, total)
    res = resolve(bag)
    res.update({"atilan": dropped, "kaynak": "zeki" if used_model else "kural",
                "neden": None if chat is not None else "Zeki AI bu kurulumda bağlı değil; yalnız kurala göre okundu.",
                "pencere": {"sayi": len(wins), "butce": cfg["windowChars"], "ortusme": cfg["overlap"], "okunamayan": bad},
                "okuma": reading.summary()})
    res["oneri"] = suggestion(res)
    if progress:
        progress(total, total)
    return res


# ================================================================================ kayıt


def _root() -> str:
    return os.environ.get("CONTRACT_DOCS_DIR", "/data/nanobaseai/bi/var/contract-docs")


def _out(r: Any) -> dict[str, Any]:
    return {"id": r.id, "contractKey": r.contract_key, "filename": r.filename, "bytes": r.bytes, "status": r.status,
            "statusLabel": STATUS.get(r.status, r.status), "done": r.done, "total": r.total, "error": r.error,
            "createdBy": r.created_by, "createdAt": _iso(r.created_at), "finishedAt": _iso(r.finished_at),
            "accepted": json.loads(r.accepted_json) if r.accepted_json else None, "acceptedBy": r.accepted_by,
            "acceptedAt": _iso(r.accepted_at), "result": json.loads(r.result_json) if r.result_json else None}


def create(engine: sa.engine.Engine, tenant: str, user: str, filename: str, data: bytes,
           contract_key: Optional[str]) -> dict[str, Any]:
    ensure(engine)
    name = os.path.basename(str(filename or "").replace("\\", "/")).strip()[:300]
    if len(data) > FILE_MAX:
        raise ExtractError("Belge 10 MB sınırını aşıyor.", 413)
    try:
        DR.check(name, data, ALLOWED)
    except DR.ReadError as e:
        raise ExtractError(str(e), e.status) from None
    eid = uuid.uuid4().hex
    folder = os.path.join(_root(), tenant)
    path = os.path.join(folder, f"{eid}.{DR.ext_of(name)}")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as e:
        log.error("sözleşme belgesi yazılamadı (%s): %s", path, e)
        raise ExtractError("Belge sunucuya kaydedilemedi; yöneticiye bildirin.", 503) from e
    with engine.begin() as c:
        c.execute(EXTRACTS.insert().values(
            id=eid, tenant_id=tenant, contract_key=(str(contract_key).strip()[:64] or None) if contract_key else None,
            filename=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), path=path, status="hazirlaniyor",
            done=0, total=0, created_by=user, created_at=_now()))
        return _out(c.execute(sa.select(EXTRACTS).where(EXTRACTS.c.id == eid)).first())


def _row(c: Any, tenant: str, eid: str) -> Any:
    r = c.execute(sa.select(EXTRACTS).where(EXTRACTS.c.id == str(eid or ""), EXTRACTS.c.tenant_id == tenant)).first()
    if r is None:
        raise ExtractError("Belge okuması bulunamadı.", 404)
    return r


def get(engine: sa.engine.Engine, tenant: str, eid: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        return _out(_row(c, tenant, eid))


def path_of(engine: sa.engine.Engine, tenant: str, eid: str) -> tuple[str, str]:
    ensure(engine)
    with engine.connect() as c:
        r = _row(c, tenant, eid)
    if not os.path.isfile(r.path):
        raise ExtractError("Belge sunucuda bulunamadı.", 404)
    return r.path, r.filename


def for_contract(engine: sa.engine.Engine, tenant: str, key: str) -> list[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(EXTRACTS).where(EXTRACTS.c.tenant_id == tenant, EXTRACTS.c.contract_key == str(key))
                         .order_by(EXTRACTS.c.created_at.desc())).all()
    return [_out(r) for r in rows]


def progress_writer(engine: sa.engine.Engine, eid: str) -> Callable[[int, int], None]:
    def write(done: int, total: int) -> None:
        with engine.begin() as c:
            c.execute(sa.update(EXTRACTS).where(EXTRACTS.c.id == eid).values(done=done, total=total))
    return write


def finish(engine: sa.engine.Engine, eid: str, result: Optional[dict[str, Any]], error: Optional[str]) -> None:
    with engine.begin() as c:
        c.execute(sa.update(EXTRACTS).where(EXTRACTS.c.id == eid).values(
            status="hata" if error else "hazir", error=error,
            result_json=json.dumps(result, ensure_ascii=False, default=str) if result is not None else None,
            finished_at=_now()))


def reset_stale(engine: sa.engine.Engine) -> int:
    ensure(engine)
    with engine.begin() as c:
        return c.execute(sa.update(EXTRACTS).where(EXTRACTS.c.status == "hazirlaniyor").values(
            status="hata", error="Okuma sürerken sunucu yeniden başladı; belgeyi yeniden okutun.", finished_at=_now())).rowcount


ACCEPTABLE = ("paymentType", "basis", "currency", "advance", "flatFee", "withholdingPct", "start", "end", "years",
              "language", "territory", "notesLine") + tuple(f"rates.{k}" for k in T.RATE_KEYS) + \
    tuple(f"rights.{k}" for k in T.RIGHT_KEYS)


def accept(engine: sa.engine.Engine, tenant: str, user: str, eid: str, fields: Any, contract_key: Any) -> dict[str, Any]:
    """İnsanın forma aktarıp kaydettiği alanlar (öneriye karşı kim neyi onayladı) ve sözleşme bağı."""
    if not isinstance(fields, list) or not all(isinstance(x, str) for x in fields):
        raise ExtractError("Aktarılan alanlar liste olmalı.")
    bad = [x for x in fields if x not in ACCEPTABLE]
    if bad:
        raise ExtractError("Bilinmeyen alan: " + ", ".join(bad[:5]) + ".")
    ensure(engine)
    with engine.begin() as c:
        r = _row(c, tenant, eid)
        vals: dict[str, Any] = {"accepted_json": json.dumps(sorted(set(fields)), ensure_ascii=False),
                                "accepted_by": user, "accepted_at": _now()}
        key = str(contract_key or "").strip()[:64]
        if key:
            vals["contract_key"] = key
        c.execute(sa.update(EXTRACTS).where(EXTRACTS.c.id == r.id).values(**vals))
        return _out(c.execute(sa.select(EXTRACTS).where(EXTRACTS.c.id == r.id)).first())


def delete(engine: sa.engine.Engine, tenant: str, eid: str) -> dict[str, Any]:
    ensure(engine)
    with engine.begin() as c:
        r = _row(c, tenant, eid)
        if r.status == "hazirlaniyor":
            raise ExtractError("Okuma sürerken silinmez; bitince silin.", 409)
        c.execute(EXTRACTS.delete().where(EXTRACTS.c.id == r.id))
    try:
        os.remove(r.path)
    except OSError as e:
        log.warning("sözleşme belgesi diskten silinemedi (%s): %s", r.path, e)
    return {"id": r.id, "filename": r.filename}
