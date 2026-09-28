"""Yapılandırılmış hak haritası (öneri 18): CRM hak açıklaması serbest metninden dil, ülke/bölge, format, bitiş ve
münhasırlık alanları — her alan metinden **birebir alıntıyla**; alıntısı metinde bulunmayan alan boş kalır.

Ortak sınıflamanın (`rights_notes`, tablo `semantic_rights_notes`) üstüne kurulur: aynı sözleşme anahtarı, aynı temiz
metin (`rights_notes.canonical`) ve aynı metin özeti. Sınıf «hangi tür kısıt» sorusunu cevaplar; harita «hangi dil, hangi
ülke, hangi biçim, ne zamana kadar, münhasır mı» alanlarını. İki modül (M54 `/haklar`, M36 `/dijital-yayin`) aynı
haritayı okur; metin değişmedikçe yeniden çıkarılmaz, metin değişince onay düşer.

Çıkarım iki katlıdır, ikisi de alıntı denetiminden geçer:

1. **Kural** (model yok): cümle cümle anahtar sözcükler — biçim (e-kitap, sesli, film/dizi/sahne, basılı, çeviri,
   dijital), münhasırlık (münhasır / münhasır değil; olumsuzluk kuraldan), bitiş (tam tarih ya da «… yıl» süresi),
   dil adları. Alıntı cümlenin kendisidir.
2. **Zeki AI** (LLM kapısından, `chat`): kuralın bulamadığı dil/ülke/bitiş alanları için JSON. Kabul koşulu: alıntı
   metinde aynen geçmeli; dil/ülke değeri alıntının içinde geçmeli; biçim kapalı kümeden olmalı ve alıntıda o biçimin
   bir sözcüğü bulunmalı; bitiş değerindeki her sayı alıntıda olmalı (tek sayı denetçisi). Tarih modelden alınmaz,
   alıntıdan okunur. Münhasırlık değeri de modelden değil alıntıdan kuralla belirlenir.

Modele giden metin kişisel veriden maskelenir (`zeki_text.mask_personal`); alıntılar maskeli metne karşı denetlenir.
Onay insandadır (`ozellik:haklar.duzenle`): önerilen harita onaylanır, düzeltilerek onaylanır ya da reddedilir.
CRM'e hiçbir şey yazılmaz.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import rights_notes as RN
from semantic_bridge import royalty as RY
from semantic_bridge import zeki_text as Z

log = logging.getLogger("semantic.rights_map")

MAP = sa.Table(
    "semantic_rights_map", RY._md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("contract_key", sa.String(40), nullable=False),
    sa.Column("no", sa.String(120)),
    sa.Column("kitap", sa.String(400)),
    sa.Column("metin_hash", sa.String(64), nullable=False),
    sa.Column("alanlar", sa.JSON),
    sa.Column("kaynak", sa.String(12)),          # zeki | kural | insan
    sa.Column("atilan", sa.Integer),             # alıntı denetiminden geçemeyen model alanı sayısı
    sa.Column("neden", sa.String(200)),          # model kullanılamadıysa nedeni
    sa.Column("durum", sa.String(12), nullable=False),   # oneri | onayli | reddedildi
    sa.Column("onaylayan", sa.String(120)),
    sa.Column("onay_at", sa.DateTime(timezone=True)),
    sa.Column("tarih", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "contract_key", name="uq_semantic_rights_map"),
)

FIELDS = ("dil", "ulke", "format", "bitis", "munhasirlik")
FIELD_LABELS = {"dil": "Dil", "ulke": "Ülke / bölge", "format": "Format", "bitis": "Bitiş", "munhasirlik": "Münhasırlık"}
FORMATS = {"basili": "Basılı", "e-kitap": "E-kitap", "sesli": "Sesli kitap", "film": "Film / dizi / sahne",
           "ceviri": "Çeviri", "dijital": "Dijital (genel)"}
EXCLUSIVITY = {"munhasir": "Münhasır", "munhasir-degil": "Münhasır değil"}
STATUSES = {"oneri": "Öneri", "onayli": "Onaylı", "reddedildi": "Reddedildi"}

#: Biçim → alıntıda aranan sözcük kökleri (katlanmış). Model bir biçim söylese bile alıntıda bunlardan biri yoksa düşer.
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
#: Dil adları (katlanmış kök). Genel dil sözlüğüdür, sözleşmeye/kitaba özel değildir; kural yalnız metinde geçeni alır.
LANGUAGES = ("turkce", "ingilizce", "almanca", "fransizca", "arapca", "farsca", "rusca", "ispanyolca", "italyanca",
             "portekizce", "japonca", "cince", "korece", "azerice", "kurtce", "bosnakca",
             "arnavutca", "urduca", "malayca", "endonezyaca", "bulgarca", "yunanca", "felemenkce", "hollandaca",
             "lehce", "macarca", "romence", "sirpca", "hirvatca", "ukraynaca", "kazakca", "ozbekce", "kirgizca",
             "turkmence", "tatarca", "uygurca", "gurcuce", "ermenice", "ibranice", "hintce", "bengalce", "isvecce",
             "norvecce", "danca", "fince", "cekce", "slovakca", "slovence", "makedonca", "osmanlica", "latince")
_DURATION = re.compile(r"\b(\d{1,3})\s*(yil|yıl|ay|gun|gün|year|month)", re.I)
_MONTHS = {"ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7, "agustos": 8,
           "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12}
_MONTH_DATE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\b")
_END_WORDS = ("bitis", "bitim", "sona er", "kadar", "sure", "gecerli", "suresi", "yil", "tarihine", "tarihinde")
_SENT = re.compile(r"(?<=[.;!?\n])\s+|\n+")

SYSTEM = ("Sen Zeki AI'sın; telif sözleşmesindeki serbest metinli hak açıklamasından alan çıkarırsın. Yalnız metinde "
          "yazanı çıkar; tahmin etme, tarih ya da ülke uydurma. Her değer için metinden AYNEN kopyalanmış kısa alıntı "
          "ver. Metinde olmayan alanı boş bırak. Sadece JSON yaz.")
PROMPT = ("Aşağıdaki hak açıklamasından şu JSON'u çıkar (bulunmayan alan boş liste ya da null):\n"
          '{"dil": [{"deger": "dilin adı", "alinti": ""}], "ulke": [{"deger": "ülke ya da bölge adı", "alinti": ""}], '
          '"format": [{"deger": "' + " | ".join(FORMATS.values()) + '", "alinti": ""}], '
          '"bitis": {"deger": "bitiş tarihi ya da süre", "alinti": ""}, '
          '"munhasirlik": {"deger": "münhasır | münhasır değil", "alinti": ""}}\n'
          "«alinti» metinden birebir kopya olmalı; «deger» alıntının içinde geçmeli.\n\nHak açıklaması:\n«{text}»")


# ------------------------------------------------------------------------------------------ kurulum

_ready: set[int] = set()


def ensure(engine: sa.engine.Engine) -> None:
    if id(engine) in _ready:
        return
    RY.ensure(engine)
    MAP.create(engine, checkfirst=True)
    _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------------------------------ alıntı denetimi (saf)

def f(s: Any) -> str:
    """Karşılaştırma biçimi: katlanmış, kesme işaretsiz, tek boşluk."""
    return " ".join(Z.fold(s).replace("'", " ").replace("’", " ").split())


def quote_ok(quote: str, text_fold: str) -> bool:
    q = f(quote)
    return len(q) >= 3 and q in text_fold


def value_in_quote(value: str, quote: str) -> bool:
    """Dil/ülke değeri alıntının içinde geçmeli (ekli biçim kabul: «Türkçe» ↔ «Türkçe'ye»)."""
    v, q = f(value), f(quote)
    return bool(v) and len(v) >= 2 and v in q


def format_key(value: Any) -> Optional[str]:
    v = f(value)
    for k, label in FORMATS.items():
        if v in (f(k), f(label)) or (v and f(label).startswith(v)):
            return k
    for k, words in FORMAT_WORDS.items():
        if any(w in v for w in words):
            return k
    return None


def format_in_quote(key: str, quote: str) -> bool:
    q = f(quote)
    return any(w in q for w in FORMAT_WORDS.get(key, ()))


def exclusivity_of(quote: str) -> Optional[str]:
    """Münhasırlık değeri alıntıdan kuralla: münhasırlık sözcüğü yoksa None; olumsuzluk varsa «münhasır değil»."""
    q = f(quote)
    if not any(w in q for w in _EXCL):
        return None
    return "munhasir-degil" if any(w in q for w in _NEG) else "munhasir"


def date_in(quote: str) -> Optional[str]:
    """Alıntıdaki tek tam tarih (gg.aa.yyyy, yyyy-aa-gg, «31 Aralık 2030»); yoksa ya da birden çoksa None."""
    days = {n.day for n in Z.tokens(quote) if n.kind == "tarih" and n.day}
    for m in _MONTH_DATE.finditer(f(quote)):
        d, mo, y = int(m.group(1)), _MONTHS[m.group(2)], int(m.group(3))
        if 1 <= d <= 31:
            days.add((y, mo, d))
    if len(days) != 1:
        return None
    y, mo, d = days.pop()
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if s and s.strip()]


def _item(value: str, quote: str, source: str, **extra: Any) -> dict[str, Any]:
    return {"deger": str(value).strip()[:200], "alinti": str(quote).strip()[:600], "kaynak": source, **extra}


# ------------------------------------------------------------------------------------------ çıkarım (saf)

def empty() -> dict[str, Any]:
    return {"dil": [], "ulke": [], "format": [], "bitis": None, "munhasirlik": None}


def rule_extract(text: str) -> dict[str, Any]:
    """Modelsiz çıkarım: anahtar sözcüklü cümle alıntıdır (metnin kendi parçası)."""
    out = empty()
    for s in sentences(text):
        fs = f(s)
        for k, words in FORMAT_WORDS.items():
            if any(w in fs for w in words) and not any(x["deger"] == k for x in out["format"]):
                out["format"].append(_item(k, s, "kural", ad=FORMATS[k]))
        for lang in LANGUAGES:
            m = re.search(r"(?<![a-z])" + re.escape(lang), fs)
            if m and not any(f(x["deger"]) == lang for x in out["dil"]):
                word = _original_word(s, lang)
                if word:
                    out["dil"].append(_item(word, s, "kural"))
        if out["munhasirlik"] is None:
            ex = exclusivity_of(s)
            if ex:
                out["munhasirlik"] = _item(ex, s, "kural", ad=EXCLUSIVITY[ex])
        if out["bitis"] is None and any(w in fs for w in _END_WORDS):
            day = date_in(s)
            dur = _DURATION.search(s)
            if day:
                out["bitis"] = _item(day, s, "kural", tarih=day)
            elif dur:
                out["bitis"] = _item(dur.group(0), s, "kural", tarih=None)
    return out


def _original_word(sentence: str, lang: str) -> Optional[str]:
    """Metindeki yazımıyla dil adı (eki atılmış): «İngilizce'ye» → «İngilizce»."""
    for w in re.findall(r"[^\s.,;:()\"«»/]+", sentence):
        base = re.split(r"['’]", w)[0]
        if f(base).startswith(lang):
            return base[:len(lang)]    # katlama harf sayısını değiştirmez; ek düşer («Türkçeye» → «Türkçe»)
    return None


def parse_json(raw: Any) -> dict[str, Any]:
    s = Z.strip_thinking(raw)
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    m = re.search(r"\{.*\}", s, flags=re.S)
    try:
        v = json.loads(m.group(0) if m else s)
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def validate_model(data: dict[str, Any], text: str) -> tuple[dict[str, Any], int]:
    """Model JSON'unu alıntı denetiminden geçirir. Dönen: (geçen alanlar, atılan sayısı)."""
    tf = f(text)
    out, dropped = empty(), 0

    def items(v: Any) -> list[dict[str, Any]]:
        if isinstance(v, dict):
            v = [v]
        return [x for x in (v or []) if isinstance(x, dict) and str(x.get("deger") or "").strip()]

    for key in ("dil", "ulke"):
        for x in items(data.get(key)):
            val, q = str(x["deger"]), str(x.get("alinti") or "")
            if quote_ok(q, tf) and value_in_quote(val, q) and Z.numbers_ok(val, q):
                out[key].append(_item(val, q, "zeki"))
            else:
                dropped += 1
    for x in items(data.get("format")):
        k, q = format_key(x["deger"]), str(x.get("alinti") or "")
        if k and quote_ok(q, tf) and format_in_quote(k, q):
            out["format"].append(_item(k, q, "zeki", ad=FORMATS[k]))
        else:
            dropped += 1
    b = items(data.get("bitis"))
    if b:
        val, q = str(b[0]["deger"]), str(b[0].get("alinti") or "")
        if quote_ok(q, tf) and Z.numbers_ok(val, q):
            out["bitis"] = _item(val, q, "zeki", tarih=date_in(q))
        else:
            dropped += 1
    m = items(data.get("munhasirlik"))
    if m:
        q = str(m[0].get("alinti") or "")
        ex = exclusivity_of(q) if quote_ok(q, tf) else None
        if ex:
            out["munhasirlik"] = _item(ex, q, "zeki", ad=EXCLUSIVITY[ex])
        else:
            dropped += 1
    return out, dropped


def merge(rule: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    """Kural önce; model yalnız kuralın bulmadığını ekler (aynı değer iki kez yazılmaz)."""
    out = {k: (list(v) if isinstance(v, list) else v) for k, v in rule.items()}
    for key in ("dil", "ulke", "format"):
        have = {f(x["deger"]) for x in out[key]}
        for x in model.get(key) or []:
            if f(x["deger"]) not in have:
                out[key].append(x)
                have.add(f(x["deger"]))
    for key in ("bitis", "munhasirlik"):
        if out[key] is None and model.get(key):
            out[key] = model[key]
    return out


def is_empty(fields: dict[str, Any]) -> bool:
    return not any(fields.get(k) for k in FIELDS)


def extract(text: str, llm: Any = None) -> dict[str, Any]:
    """Tek metnin haritası. `llm`: LLM kapısı sarmalayıcısı (`chat`); yoksa yalnız kural."""
    text = RN.canonical(text)
    masked = Z.mask_personal(text)
    rule = rule_extract(masked)
    if llm is None or not hasattr(llm, "chat"):
        return {"alanlar": rule, "kaynak": "kural", "atilan": 0, "neden": "model-yok"}
    try:
        raw = llm.chat([{"role": "system", "content": SYSTEM},
                        {"role": "user", "content": PROMPT.replace("{text}", masked[:4000])}],
                       max_tokens=900, temperature=0.0)
    except Exception as e:  # noqa: BLE001 — model yoksa kural sonucu kalır
        log.info("hak haritası: model cevap vermedi: %s", e)
        return {"alanlar": rule, "kaynak": "kural", "atilan": 0, "neden": "model-cevap-vermedi"}
    data = parse_json(raw)
    if not data:
        return {"alanlar": rule, "kaynak": "kural", "atilan": 0, "neden": "json-yok"}
    model, dropped = validate_model(data, masked)
    fields = merge(rule, model)
    used = any((x or {}).get("kaynak") == "zeki" for k in FIELDS for x in
               (fields[k] if isinstance(fields[k], list) else [fields[k]]))
    return {"alanlar": fields, "kaynak": "zeki" if used else "kural", "atilan": dropped, "neden": None}


# ------------------------------------------------------------------------------------------ kayıt

def _row(r: Any) -> dict[str, Any]:
    return {"id": r.id, "contractKey": r.contract_key, "no": r.no, "book": r.kitap, "fields": r.alanlar or empty(),
            "source": r.kaynak, "dropped": r.atilan or 0, "reason": r.neden, "status": r.durum,
            "statusLabel": STATUSES.get(r.durum), "approvedBy": r.onaylayan, "approvedAt": RY._iso(r.onay_at),
            "at": RY._iso(r.tarih), "hash": r.metin_hash}


def pending(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """Haritası çıkarılacak notlar: ortak tablodaki (her iki modülün yazdığı) notlardan haritası olmayan ya da metni
    değişmiş olanlar. Onaylı ve aynı metinli harita yeniden çıkarılmaz."""
    ensure(engine)
    n, m = RY.NOTES.c, MAP.c
    with engine.connect() as c:
        notes = c.execute(sa.select(n.contract_key, n.no, n.kitap, n.metin, n.metin_hash)
                          .where(n.tenant_id == tenant).order_by(n.no)).all()
        have = {r.contract_key: r.metin_hash for r in c.execute(sa.select(m.contract_key, m.metin_hash)
                                                                .where(m.tenant_id == tenant)).all()}
    return [{"key": r.contract_key, "no": r.no, "book": r.kitap, "text": r.metin, "hash": r.metin_hash}
            for r in notes if r.metin and have.get(r.contract_key) != r.metin_hash]


def save(engine: sa.engine.Engine, tenant: str, item: dict[str, Any], res: dict[str, Any]) -> None:
    values = {"no": RY._text(item.get("no"), 120), "kitap": RY._text(item.get("book"), 400),
              "metin_hash": item.get("hash") or RY.note_hash(item["text"]), "alanlar": res["alanlar"],
              "kaynak": res["kaynak"], "atilan": res.get("atilan") or 0, "neden": (res.get("neden") or None),
              "durum": "oneri", "onaylayan": None, "onay_at": None, "tarih": _now()}
    with engine.begin() as c:
        cur = c.execute(sa.select(MAP.c.id).where(MAP.c.tenant_id == tenant, MAP.c.contract_key == item["key"])).first()
        if cur:
            c.execute(MAP.update().where(MAP.c.id == cur.id).values(**values))
        else:
            c.execute(MAP.insert().values(tenant_id=tenant, contract_key=item["key"], **values))


def run(engine: sa.engine.Engine, tenant: str, items: list[dict[str, Any]], llm: Any, *,
        budget_sec: Optional[float] = None, progress: Optional[Callable[[bool], None]] = None) -> dict[str, Any]:
    """`pending` çıktısını çıkarır ve yazar. Süre bütçesi biterse kalan sonraki koşuya kalır (kalan sayısı döner)."""
    t0, done, model_fail = time.monotonic(), 0, 0
    for it in items:
        if budget_sec is not None and time.monotonic() - t0 > budget_sec:
            break
        res = extract(it["text"], llm)
        if res.get("neden") == "model-cevap-vermedi":
            model_fail += 1
        save(engine, tenant, it, res)
        done += 1
        if progress:
            progress(res.get("neden") != "model-cevap-vermedi")
    return {"cikarilan": done, "kalan": len(items) - done, "modelHatasi": model_fail}


def for_keys(engine: sa.engine.Engine, tenant: str, keys: Iterable[str]) -> dict[str, dict[str, Any]]:
    ks = sorted({RN.key(k) for k in keys if k})
    if not ks:
        return {}
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(MAP).where(MAP.c.tenant_id == tenant, MAP.c.contract_key.in_(ks))).all()
    return {r.contract_key: _row(r) for r in rows}


def matching(maps: dict[str, dict[str, Any]], contract_key: Any, text: Any) -> Optional[dict[str, Any]]:
    """`for_keys` sonucundan sözleşmenin haritası, yalnız metin özeti bugünkü metinle aynıysa (metin değiştiyse eski
    harita gösterilmez)."""
    t = RN.canonical(text)
    r = maps.get(RN.key(contract_key)) if t else None
    return r if r and r["hash"] == RY.note_hash(t) else None


def for_text(engine: sa.engine.Engine, tenant: str, contract_key: str, text: Any) -> Optional[dict[str, Any]]:
    return matching(for_keys(engine, tenant, [contract_key]), contract_key, text) if RN.canonical(text) else None


def digital_view(m: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """M36 ekranının okuduğu biçim."""
    if not m:
        return None
    return {"alanlar": m["fields"], "ozet": summary_line(m["fields"]), "durum": m["status"], "durumAdi": m["statusLabel"],
            "kaynak": m["source"], "onayli": m["status"] == "onayli"}


def counts_stmt(tenant: str) -> sa.Select:
    """Hak haritası durum sayıları (sorgu bilgisi aynı ifadeyi gösterir)."""
    return sa.select(MAP.c.durum, sa.func.count()).where(MAP.c.tenant_id == tenant).group_by(MAP.c.durum)


def counts(engine: sa.engine.Engine, tenant: str) -> dict[str, int]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(counts_stmt(tenant)).all()
    return {d: int(n) for d, n in rows}


def _clean_fields(body: Any) -> dict[str, Any]:
    """İnsanın düzelttiği harita: yalnız bilinen alanlar; biçim ve münhasırlık kapalı kümeden; tarih ISO.
    İnsanın eklediği değerin alıntısı olmayabilir (kaynak «insan»)."""
    if not isinstance(body, dict):
        raise RY.RoyaltyError("Alanlar okunamadı.", 422)
    out = empty()

    def one(x: Any, key: str) -> Optional[dict[str, Any]]:
        if not isinstance(x, dict) or not str(x.get("deger") or "").strip():
            return None
        val = str(x["deger"]).strip()[:200]
        src = x.get("kaynak") if x.get("kaynak") in ("zeki", "kural", "insan") else "insan"
        item = {"deger": val, "alinti": str(x.get("alinti") or "")[:600], "kaynak": src}
        if key == "format":
            k = format_key(val)
            if not k:
                raise RY.RoyaltyError(f"Bilinmeyen format: {val}", 422)
            item.update(deger=k, ad=FORMATS[k])
        if key == "munhasirlik":
            if val not in EXCLUSIVITY:
                raise RY.RoyaltyError("Münhasırlık «munhasir» ya da «munhasir-degil» olmalı.", 422)
            item["ad"] = EXCLUSIVITY[val]
        if key == "bitis":
            t = x.get("tarih")
            if t:
                try:
                    item["tarih"] = date.fromisoformat(str(t)[:10]).isoformat()
                except ValueError:
                    raise RY.RoyaltyError("Bitiş tarihi geçerli değil.", 422) from None
            else:
                item["tarih"] = None
        return item

    for key in ("dil", "ulke", "format"):
        v = body.get(key) or []
        if not isinstance(v, list):
            raise RY.RoyaltyError(f"{FIELD_LABELS[key]} liste olmalı.", 422)
        out[key] = [i for i in (one(x, key) for x in v) if i]
    for key in ("bitis", "munhasirlik"):
        out[key] = one(body.get(key), key)
    return out


def decide(engine: sa.engine.Engine, tenant: str, user: str, map_id: int, body: dict[str, Any]) -> dict[str, Any]:
    """Onay (`action: onayla`, isteğe bağlı düzeltilmiş `fields`) ya da ret (`action: reddet`)."""
    action = str(body.get("action") or "onayla")
    if action not in ("onayla", "reddet"):
        raise RY.RoyaltyError("İşlem «onayla» ya da «reddet» olmalı.", 422)
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(MAP).where(MAP.c.tenant_id == tenant, MAP.c.id == int(map_id))).first()
        if not r:
            raise RY.RoyaltyError("Hak haritası bulunamadı.", 404)
        values: dict[str, Any] = {"durum": "onayli" if action == "onayla" else "reddedildi", "onaylayan": user,
                                  "onay_at": _now()}
        if action == "onayla" and body.get("fields") is not None:
            fields = _clean_fields(body["fields"])
            if fields != (r.alanlar or empty()):
                values.update(alanlar=fields, kaynak="insan")
        c.execute(MAP.update().where(MAP.c.id == r.id).values(**values))
        row = c.execute(sa.select(MAP).where(MAP.c.id == r.id)).first()
    return _row(row)


def summary_line(fields: dict[str, Any]) -> str:
    """Tek satır okuma (liste ve dijital ekranı için)."""
    parts = []
    if fields.get("format"):
        parts.append(", ".join(x.get("ad") or FORMATS.get(x["deger"], x["deger"]) for x in fields["format"]))
    if fields.get("dil"):
        parts.append(", ".join(x["deger"] for x in fields["dil"]))
    if fields.get("ulke"):
        parts.append(", ".join(x["deger"] for x in fields["ulke"]))
    if fields.get("munhasirlik"):
        parts.append(fields["munhasirlik"].get("ad") or EXCLUSIVITY.get(fields["munhasirlik"]["deger"], ""))
    if fields.get("bitis"):
        b = fields["bitis"]
        parts.append("bitiş " + (b.get("tarih") or b["deger"]))
    return " · ".join(p for p in parts if p)
