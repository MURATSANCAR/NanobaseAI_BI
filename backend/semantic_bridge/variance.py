"""Fark ayrıştırma — «rakam neden değişti?» (öneri 4) ve beklenen aralık / eşik önerisi (öneri 6).

Tek iş: bir ölçünün iki dönem arasındaki farkını kanal (`CLCARD.SPECODE2`), cari ve kitap katkısına SQL ile ayırmak;
en çok katkı yapan kırılımları pay ve yönüyle vermek. Rakamı model üretmez: bütün sayılar buradaki SQL'den gelir, Zeki AI
yalnız anlatır (`zeki_text.interpret`, sayı denetimli; tutmazsa kural metni).

**Ölçü katalogdan gelir, örnekten değil.** Soru çözümleyiciden geçer; sorunun sertifikalı METRIC formülü (ör.
`SUM(CASE WHEN STLINE.TRCODE IN (7,8,9) THEN STLINE.VATMATRAH ELSE 0 END)`), formülün koşulları (`INVOICEREF NOT IN
(0)`),
ölçünün varsayılan satır kapsamı (DEFAULT_FILTER) ve sorudaki değer filtreleri (DIMENSION_VALUE) aynen SQL'e taşınır;
böylece ayrıştırmanın toplamı sohbet cevabının rakamıyla aynı tanımdadır. Desteklenmeyen durum açıkça söylenir, tahmin
edilmez: ölçü `STLINE` üzerinde toplanabilir bir SUM değilse (oran, ortalama, tekil sayım), soru başka tablo filtresi
taşıyorsa ya da dönemi yoksa «ayrıştırılamadı» ve nedeni döner.

**Yıl kopyaları** (211 = 2021–2025, 411 = 2026): SQL mantıksal varlık adlarıyla yazılır (`STLINE`, `CLCARD`, `ITEMS`);
köprünün fiziksel yeniden yazımı dönemi taşıyan kopyaları kendi tarihleriyle birleştirir — sohbet cevabıyla aynı yol.

**Karşı dönem**: «geçen yılın aynı dönemi» (varsayılan) ya da «önceki dönem» (aynı uzunlukta hemen önceki pencere).
Dönem veri son gününden ileri uzanıyorsa (ay ortası, donmuş kopya) karşı dönem aynı uzunluğa kırpılır ve bu yazılır.

**Beklenen aralık** (`expected_range`): aynı pencerenin geçmiş 24 ayki değerlerinden; mevsim yıllık oranla ayıklanır
(v_k / v_{k+12}) ve oranın medyanı ± k·1,4826·MAD bant verir. En az 12 oran yoksa mevsimsiz medyan ± MAD; o da yoksa
aralık yok (uydurulmaz). Eşik önerisi bu banttan «kurala göre öneri» olarak verilir; model yok.
"""
from __future__ import annotations

import calendar
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import zeki_text as Z

log = logging.getLogger(__name__)

#: Ayrıştırma boyutları. Anahtar ifadesi SQL'de gruplamadır; ad gösterimdir.
DIMENSIONS: dict[str, dict[str, Any]] = {
    "kanal": {"ad": "Kanal", "anahtar": "ISNULL(NULLIF(LTRIM(RTRIM(CLCARD.SPECODE2)), ''), N'Grup kodu boş')",
              "etiket": None, "tablo": "CLCARD"},
    "cari": {"ad": "Cari", "anahtar": "ISNULL(CLCARD.CODE, N'#YOK')", "etiket": "MAX(CLCARD.DEFINITION_)", "tablo": "CLCARD"},
    "kitap": {"ad": "Kitap", "anahtar": "ISNULL(ITEMS.CODE, N'#YOK')", "etiket": "MAX(ITEMS.NAME)", "tablo": "ITEMS"},
}
DEFAULT_DIMS = ("kanal", "cari", "kitap")
#: Ayrıştırmada kullanılabilen varlıklar ve STLINE'a bağları.
JOINS = {
    "CLCARD": "LEFT JOIN CLCARD AS CLCARD ON CLCARD.LOGICALREF = STLINE.CLIENTREF",
    "ITEMS": "LEFT JOIN ITEMS AS ITEMS ON ITEMS.LOGICALREF = STLINE.STOCKREF",
}
ENTITIES = {"STLINE", "CLCARD", "ITEMS"}
COMPARE = {"gecen-yil": "geçen yılın aynı dönemi", "onceki-donem": "önceki dönem"}
_OPS = {"IN", "NOT IN", "=", "<>", "!=", ">", ">=", "<", "<="}
_REF = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.\[?([A-Za-z_][A-Za-z0-9_]*)\]?")
_NOT_ADDITIVE = re.compile(r"\b(AVG|COUNT|MIN|MAX|STDEV|VAR)\s*\(|\bDISTINCT\b|/", re.I)
#: SQL'e taşınan metinde yasak (catalog'dan gelse de): ikinci deyim, yorum, veri değiştiren komut.
_UNSAFE = re.compile(r";|--|/\*|\b(INSERT|UPDATE|DELETE|DROP|ALTER|EXEC|EXECUTE|MERGE|TRUNCATE|CREATE|GRANT)\b", re.I)

Runner = Callable[[str, Optional[tuple]], list[dict[str, Any]]]


class VarianceError(ValueError):
    """Ekrana olduğu gibi yazılan düz Türkçe neden."""


# ================================================================================ ölçü: sorunun katalog tanımı


@dataclass
class Measure:
    ad: str
    formul: str
    kosullar: list[str] = field(default_factory=list)
    birim: str = "₺"
    tablolar: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, Any]:
        return {"ad": self.ad, "birim": self.birim, "formul": self.formul, "kosullar": list(self.kosullar)}


def _qdict(sq: Any) -> dict[str, Any]:
    if sq is None:
        return {}
    if isinstance(sq, dict):
        return sq
    return sq.to_dict() if hasattr(sq, "to_dict") else {}


def _value(v: Any) -> str:
    s = str(v)
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        return s
    return "N'" + s.replace("'", "''") + "'"


def _entities_of(text: str) -> set[str]:
    return {m.group(1).upper() for m in _REF.finditer(text or "") if not m.group(1).upper().startswith("DBO")}


def _condition(mp: dict[str, Any]) -> Optional[str]:
    """Bir eşlemenin (değer filtresi / varsayılan kapsam) SQL koşulu; tanınmayan biçimde None."""
    if mp.get("formula"):
        return f"({mp['formula']})"
    col, op = mp.get("column"), str(mp.get("operator") or "IN").upper().strip()
    vals = [v for v in (mp.get("values") or []) if v is not None]
    ent = str(mp.get("entity") or "").upper()
    if col and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(col)) and op in ("IS NULL", "IS NOT NULL"):
        return f"{ent}.{col} {op}"
    if not col or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(col)) or op not in _OPS or not vals:
        return None
    ref = f"{ent}.{col}"
    if op in ("IN", "NOT IN"):
        return f"{ref} {op} ({', '.join(_value(v) for v in vals)})"
    return f"{ref} {'<>' if op == '!=' else op} {_value(vals[0])}"


def _unit(formula: str) -> str:
    f = formula.upper()
    if re.search(r"LINENET|TOTAL|PRICE|VATMATRAH|DISTCOST|OUTCOST", f):
        return "₺"
    return "adet" if "AMOUNT" in f else ""


def measure_of(sq: Any) -> tuple[Optional[Measure], Optional[str]]:
    """Sorunun çözümünden ayrıştırılabilir ölçü; olmazsa (None, neden)."""
    q = _qdict(sq)
    slots = q.get("slots") or []
    metrics = [s for s in slots if s.get("semanticType") == "METRIC" and s.get("mapping")]
    if not metrics:
        return None, "Soruda katalogda tanımlı bir ölçü yok."
    if len(metrics) > 1:
        return None, "Soruda birden çok ölçü var; ayrıştırma tek ölçüde yapılır."
    m = metrics[0]["mapping"]
    formula = str(m.get("formula") or "").strip()
    if str(m.get("entity") or "").upper() != "STLINE" or not formula:
        return None, "Ayrıştırma yalnız satış/fatura satırı (STLINE) ölçülerinde yapılır."
    if _NOT_ADDITIVE.search(formula) or not re.match(r"^\s*SUM\s*\(", formula, re.I):
        return None, "Bu ölçü toplanabilir değil (oran, ortalama ya da tekil sayım); katkıya bölünemez."
    conds: list[str] = [str(c) for c in ((m.get("extra") or {}).get("conditions") or []) if str(c).strip()]
    for s in slots:
        t = s.get("semanticType")
        if t not in ("DEFAULT_FILTER", "DIMENSION_VALUE"):
            continue
        mp = s.get("mapping") or {}
        c = _condition(mp)
        if c is None:   # taşınamayan kapsam tanımı değiştirir: yaklaşık ayrıştırma yapılmaz
            return None, f"«{s.get('term')}» {'filtresi' if t == 'DIMENSION_VALUE' else 'kapsamı'} ayrıştırmaya taşınamadı."
        conds.append(c)
    for extra in ("unhandled", "qualifierColumns", "modelQualifiers"):
        if q.get(extra):
            return None, "Soruda katalogda tanımı olmayan bir niteleyici var; ayrıştırma aynı tanımı kuramaz."
    tables = _entities_of(" ".join([formula, *conds]))
    bad = tables - ENTITIES
    if bad:
        return None, f"Ölçü ya da filtre başka tabloya dayanıyor ({', '.join(sorted(bad))}); ayrıştırılamadı."
    if any(_UNSAFE.search(x) for x in [formula, *conds]):
        return None, "Ölçü tanımı ayrıştırmaya uygun değil."
    return Measure(ad=str(metrics[0].get("term") or "ölçü"), formul=formula, kosullar=conds, birim=_unit(formula),
                   tablolar=tables - {"STLINE"}), None


# ================================================================================ dönem


def _d(v: Any) -> Optional[date]:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def bounds_of(sq: Any) -> tuple[Optional[date], Optional[date]]:
    """Sorunun dönemi [başlangıç, bitiş). Dönemsiz soruda (None, None). Soru iki dönem anıyorsa («2025 ile 2026») en
    yeni dönem «şimdi» sayılır; karşı dönem ayrıştırmanın kendi seçimidir (iki dönemi birleştirip tek pencere yapmaz)."""
    t = [(s, e) for s, e in ((_d(x.get("start")), _d(x.get("end"))) for x in (_qdict(sq).get("temporal") or [])) if s and e]
    if not t:
        return None, None
    return max(t, key=lambda p: (p[1], p[0]))


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _month_aligned(a: date, b: date) -> bool:
    return a.day == 1 and b.day == 1


def shift(a: date, b: date, months: int) -> tuple[date, date]:
    """Pencereyi ay kaydırır; ay başı–ay başı pencerede ay sınırları korunur, diğerinde uzunluk korunur."""
    na = add_months(a, months)
    if _month_aligned(a, b):
        return na, add_months(b, months)
    return na, na + (b - a)


def compare_window(a: date, b: date, how: str) -> tuple[date, date]:
    if how == "gecen-yil":
        return shift(a, b, -12)
    if how == "onceki-donem":
        if _month_aligned(a, b):
            n = (b.year - a.year) * 12 + b.month - a.month
            return add_months(a, -n), a
        return a - (b - a), a
    raise VarianceError("Karşı dönem «gecen-yil» ya da «onceki-donem» olmalı.")


def label(a: date, b: date) -> str:
    last = b - timedelta(days=1)
    return f"{a.strftime('%d.%m.%Y')}–{last.strftime('%d.%m.%Y')}"


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


# ================================================================================ SQL


def _where(m: Measure, a: date, b: date) -> str:
    parts = [f"STLINE.DATE_ >= '{_ymd(a)}'", f"STLINE.DATE_ < '{_ymd(b)}'", *[f"({c})" for c in m.kosullar]]
    return "\n  AND ".join(parts)


def _joins(tables: Iterable[str]) -> str:
    return "\n".join(JOINS[t] for t in ("CLCARD", "ITEMS") if t in set(tables))


def dim_sql(m: Measure, dim: str, a: date, b: date) -> str:
    """Bir boyutun [a, b) dönemindeki değerleri (mantıksal varlık adlarıyla; yıl kopyaları köprüde çözülür)."""
    spec = DIMENSIONS[dim]
    name = spec["etiket"] or spec["anahtar"]
    tables = set(m.tablolar) | {spec["tablo"]}
    return (f"-- Fark ayrıştırma: {m.ad} · {DIMENSIONS[dim]['ad'].lower()} kırılımı · {label(a, b)}\n"
            f"SELECT {spec['anahtar']} AS anahtar, {name} AS ad, {m.formul} AS deger, MAX(STLINE.DATE_) AS son\n"
            f"FROM STLINE AS STLINE\n{_joins(tables)}\n"
            f"WHERE {_where(m, a, b)}\n"
            f"GROUP BY {spec['anahtar']}").replace("\n\n", "\n")


def daily_sql(m: Measure, a: date, b: date) -> str:
    """Gün gün toplam (beklenen aralık için geçmiş pencereler bundan toplanır)."""
    return (f"-- Beklenen aralık: {m.ad} · gün gün · {label(a, b)}\n"
            f"SELECT CONVERT(date, STLINE.DATE_) AS gun, {m.formul} AS deger\n"
            f"FROM STLINE AS STLINE\n{_joins(m.tablolar)}\n"
            f"WHERE {_where(m, a, b)}\n"
            f"GROUP BY CONVERT(date, STLINE.DATE_)").replace("\n\n", "\n")


def total_sql(m: Measure, a: date, b: date) -> str:
    return (f"SELECT {m.formul} AS deger, MAX(STLINE.DATE_) AS son\nFROM STLINE AS STLINE\n{_joins(m.tablolar)}\n"
            f"WHERE {_where(m, a, b)}").replace("\n\n", "\n")


# ================================================================================ ayrıştırma (saf)


def _f(v: Any) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) else 0.0


def decompose(current: list[dict[str, Any]], previous: list[dict[str, Any]]) -> dict[str, Any]:
    """İki dönemin aynı boyuttaki satırları → toplamlar ve kırılım katkıları (mutlak farka göre büyükten küçüğe).
    `pay`: kalemin farkı / net fark (karşı yönlü kalemler varsa %100'ü aşabilir); `payMutlak`: |fark| / Σ|fark|."""
    rows: dict[str, dict[str, Any]] = {}
    for side, data in (("simdi", current), ("onceki", previous)):
        for r in data or []:
            k = str(r.get("anahtar") if r.get("anahtar") is not None else "#YOK").strip() or "#YOK"
            d = rows.setdefault(k, {"anahtar": k, "ad": None, "simdi": 0.0, "onceki": 0.0})
            d[side] += _f(r.get("deger"))
            ad = r.get("ad")
            if ad not in (None, "") and not d["ad"]:
                d["ad"] = " ".join(str(ad).split())
    now = sum(d["simdi"] for d in rows.values())
    before = sum(d["onceki"] for d in rows.values())
    diff = now - before
    gross = sum(abs(d["simdi"] - d["onceki"]) for d in rows.values())
    items = []
    for d in rows.values():
        f = d["simdi"] - d["onceki"]
        if abs(f) < 1e-9:
            continue
        items.append({**d, "ad": d["ad"] or d["anahtar"], "simdi": round(d["simdi"], 2), "onceki": round(d["onceki"], 2),
                      "fark": round(f, 2), "yon": "artis" if f > 0 else "azalis",
                      "pay": round(f / diff, 4) if abs(diff) > 1e-9 else None,
                      "payMutlak": round(abs(f) / gross, 4) if gross > 0 else None,
                      "yeni": abs(d["onceki"]) < 1e-9, "kayip": abs(d["simdi"]) < 1e-9})
    items.sort(key=lambda x: (-abs(x["fark"]), x["anahtar"]))
    return {"simdi": round(now, 2), "onceki": round(before, 2), "fark": round(diff, 2),
            "oran": round(diff / before, 4) if abs(before) > 1e-9 else None, "kalemler": items,
            "kalemSayisi": len(items)}


def _last_day(rows: Iterable[dict[str, Any]]) -> Optional[date]:
    ds = [d for d in (_d(r.get("son")) for r in rows) if d]
    return max(ds) if ds else None


def run(runner: Runner, m: Measure, a: date, b: date, *, karsi: str = "gecen-yil",
        boyutlar: Iterable[str] = DEFAULT_DIMS) -> dict[str, Any]:
    """Ayrıştırmayı çalıştırır. `runner(sql, dönem)` → satırlar (köprüde `run_complete`, dönemle)."""
    dims = [x for x in boyutlar if x in DIMENSIONS] or list(DEFAULT_DIMS)
    sqls: list[dict[str, str]] = []
    cur: dict[str, list[dict[str, Any]]] = {}
    for dim in dims:
        sql = dim_sql(m, dim, a, b)
        sqls.append({"ad": f"{DIMENSIONS[dim]['ad']} · {label(a, b)}", "sql": sql})
        cur[dim] = runner(sql, (a, b))
    seen = [d for d in (_last_day(v) for v in cur.values()) if d]
    end_seen = max(seen) if seen else None
    eff_b, clipped = b, False
    if end_seen is not None and end_seen + timedelta(days=1) < b:
        eff_b, clipped = end_seen + timedelta(days=1), True
    ca, cb = compare_window(a, eff_b, karsi)
    out_dims = []
    for dim in dims:
        sql = dim_sql(m, dim, ca, cb)
        sqls.append({"ad": f"{DIMENSIONS[dim]['ad']} · {label(ca, cb)}", "sql": sql})
        prev = runner(sql, (ca, cb))
        dec = decompose(cur[dim], prev)
        out_dims.append({"id": dim, "ad": DIMENSIONS[dim]["ad"], **dec})
    head = out_dims[0] if out_dims else {"simdi": 0.0, "onceki": 0.0, "fark": 0.0, "oran": None}
    return {"ok": True, "olcu": m.as_dict(), "donem": {"bas": a.isoformat(), "bit": eff_b.isoformat(), "etiket": label(a, eff_b)},
            "karsi": {"tur": karsi, "ad": COMPARE[karsi], "bas": ca.isoformat(), "bit": cb.isoformat(), "etiket": label(ca, cb)},
            "kirpildi": clipped, "veriSonu": end_seen.isoformat() if end_seen else None,
            "toplam": {k: head[k] for k in ("simdi", "onceki", "fark", "oran")},
            "boyutlar": out_dims, "kaynak": {"sql": sqls}}


# ================================================================================ anlatım


def tr_num(v: Optional[float], decimals: int = 0) -> str:
    if v is None:
        return "—"
    s = f"{abs(v):,.{decimals}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    return ("−" if v < 0 else "") + s


def tr_amount(v: Optional[float], unit: str) -> str:
    return f"{tr_num(v)} {unit}".strip() if unit else tr_num(v)


def tr_pct(r: Optional[float]) -> str:
    return "—" if r is None else f"%{tr_num(abs(r) * 100, 1)}"


def facts(res: dict[str, Any], top: int = 3) -> list[str]:
    """Modele (ve kural metnine) giden olgular. Her sayı burada yazıldığı gibidir; model yenisini yazamaz."""
    unit = (res.get("olcu") or {}).get("birim") or ""
    t = res["toplam"]
    yon = "arttı" if t["fark"] > 0 else "azaldı" if t["fark"] < 0 else "değişmedi"
    out = [f"Ölçü: {(res.get('olcu') or {}).get('ad')}.",
           f"Dönem {res['donem']['etiket']}: {tr_amount(t['simdi'], unit)}.",
           f"Karşı dönem ({res['karsi']['ad']}, {res['karsi']['etiket']}): {tr_amount(t['onceki'], unit)}.",
           f"Fark: {tr_amount(abs(t['fark']), unit)} {yon}" + (f" ({tr_pct(t['oran'])})." if t.get("oran") is not None else ".")]
    if res.get("kirpildi"):
        out.append(f"Veri {res['donem']['etiket']} sonuna kadar; karşı dönem aynı uzunluğa kırpıldı.")
    for d in res.get("boyutlar") or []:
        parts = []
        for it in d["kalemler"][:top]:
            w = "artış" if it["fark"] > 0 else "azalış"
            share = f", farkın {tr_pct(it['pay'])} kadarı" if it.get("pay") is not None else ""
            parts.append(f"{it['ad']}: {tr_amount(abs(it['fark']), unit)} {w}{share}")
        if parts:
            base = f" ({d['karsi']})" if d.get("karsi") else ""
            out.append(f"En büyük {d['ad'].lower()} katkıları{base} — " + "; ".join(parts) + ".")
    return out


def rule_text(res: dict[str, Any]) -> str:
    """Model yoksa ya da metni denetimden geçmezse gösterilen metin: toplamlar ve ilk iki boyutun en büyük katkıları."""
    f = facts(res)
    return " ".join(f[1:4] + [x for x in f[4:] if x.startswith("En büyük")][:2])


TASK = ("Bir yöneticiye rakamın neden değiştiğini anlat: önce farkı, sonra farkı en çok sürükleyen kanal, cari ya da "
        "kitabı söyle. Yalnız olgulardaki kırılımları kullan; olgularda olmayan neden (kampanya, fiyat, mevsim) uydurma.")


def explain(res: dict[str, Any], *, llm: Any = None, rt: Any = None, module: str = "fark",
            priority: Optional[int] = None) -> dict[str, Any]:
    it = Z.interpret(facts(res), rule_text(res), llm=llm, rt=rt, module=module, priority=priority, task=TASK,
                     min_sentences=2, max_sentences=3, max_chars=700)
    return it.as_dict()


# ================================================================================ soru → ayrıştırma


def hint(sq: Any) -> dict[str, Any]:
    """Sohbet cevabı / pano kartı / uyarı için: bu soru ayrıştırılabilir mi. Ekran «Neden?»i buna göre gösterir."""
    m, why = measure_of(sq)
    a, b = bounds_of(sq)
    if m is None:
        return {"ok": False, "neden": why}
    if not (a and b):
        return {"ok": False, "neden": "Soruda dönem yok; ayrıştırma iki dönemi karşılaştırır."}
    return {"ok": True, "olcu": m.ad, "birim": m.birim, "bas": a.isoformat(), "bit": b.isoformat()}


def for_question(runner: Runner, sq: Any, *, karsi: str = "gecen-yil", boyutlar: Iterable[str] = DEFAULT_DIMS) -> dict[str, Any]:
    m, why = measure_of(sq)
    if m is None:
        raise VarianceError(why or "Ayrıştırılamadı.")
    a, b = bounds_of(sq)
    if not (a and b):
        raise VarianceError("Soruda dönem yok; ayrıştırma iki dönemi karşılaştırır.")
    if karsi not in COMPARE:
        raise VarianceError("Karşı dönem «gecen-yil» ya da «onceki-donem» olmalı.")
    return run(runner, m, a, b, karsi=karsi, boyutlar=boyutlar)


# ================================================================================ beklenen aralık ve eşik önerisi


MIN_POINTS = 12
LAGS = 24


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _mad(xs: list[float], med: float) -> float:
    return _median([abs(x - med) for x in xs]) if xs else 0.0


def expected_range(current_window: Optional[float], lags: dict[int, float], *, k: float = 2.0,
                   min_points: int = MIN_POINTS) -> Optional[dict[str, Any]]:
    """`lags`: gecikme (ay) → aynı pencerenin o kadar ay önceki değeri. Dönen: {alt, merkez, ust, yontem, nokta, disinda}.
    Yeterli geçmiş yoksa None. Mevsim: yıllık oran v_k / v_{k+12} (k = 1..12) — oranın medyanı ve MAD'ı."""
    ratios = []
    for lag in range(1, 13):
        a, b = lags.get(lag), lags.get(lag + 12)
        if a is not None and b is not None and b > 0 and a >= 0:
            ratios.append(a / b)
    base = lags.get(12)
    if len(ratios) >= min_points and base is not None and base > 0:
        med = _median(ratios)
        s = 1.4826 * _mad(ratios, med)
        lo, hi = base * max(0.0, med - k * s), base * (med + k * s)
        out = {"alt": round(lo, 2), "merkez": round(base * med, 2), "ust": round(hi, 2), "yontem": "mevsimsel",
               "nokta": len(ratios), "k": k}
    else:
        vals = [v for lag, v in sorted(lags.items()) if 1 <= lag <= 12 and v is not None]
        if len(vals) < min_points:
            return None
        med = _median(vals)
        s = 1.4826 * _mad(vals, med)
        out = {"alt": round(med - k * s, 2), "merkez": round(med, 2), "ust": round(med + k * s, 2), "yontem": "medyan",
               "nokta": len(vals), "k": k}
    if current_window is not None:
        out["deger"] = round(current_window, 2)
        out["disinda"] = current_window < out["alt"] or current_window > out["ust"]
        out["yon"] = "ust" if current_window > out["ust"] else "alt" if current_window < out["alt"] else None
    return out


def window_lags(daily: dict[date, float], a: date, b: date, lags: int = LAGS) -> tuple[Optional[float], dict[int, float]]:
    """Gün gün değerlerden şimdiki pencerenin ve geçmiş pencerelerin toplamı. Veri başlamadan önceki pencere yok sayılır."""
    if not daily:
        return None, {}
    first = min(daily)
    cur = sum(v for d, v in daily.items() if a <= d < b)
    out: dict[int, float] = {}
    for k in range(1, lags + 1):
        pa, pb = shift(a, b, -k)
        if pa < first:
            continue
        out[k] = sum(v for d, v in daily.items() if pa <= d < pb)
    return cur, out


def measure_range(runner: Runner, sq: Any, *, k: float = 2.0, today: Optional[date] = None) -> dict[str, Any]:
    """Sorunun ölçüsü için beklenen aralık (bugünkü penceresi ve geçmiş 24 ay). Hesaplanamazsa {"ok": False, "neden"}."""
    m, why = measure_of(sq)
    a, b = bounds_of(sq)
    if m is None:
        return {"ok": False, "neden": why}
    if not (a and b):
        return {"ok": False, "neden": "Soruda dönem yok; beklenen aralık bir pencerenin geçmişiyle hesaplanır."}
    start = add_months(a, -LAGS)
    sql = daily_sql(m, start, b)
    rows = runner(sql, (start, b))
    daily = {d: _f(r.get("deger")) for r in rows for d in [_d(r.get("gun"))] if d}
    last = max(daily) if daily else None
    eff_b = b
    if last is not None and last + timedelta(days=1) < b:
        eff_b = last + timedelta(days=1)
    if eff_b <= a:
        return {"ok": False, "neden": "Bu dönemde henüz veri yok.", "kaynak": {"sql": [{"ad": "Gün gün", "sql": sql}]}}
    cur, lags = window_lags(daily, a, eff_b)
    rng = expected_range(cur, lags, k=k)
    base = {"olcu": m.ad, "birim": m.birim, "donem": label(a, eff_b), "kirpildi": eff_b != b,
            "kaynak": {"sql": [{"ad": "Gün gün geçmiş", "sql": sql}]}}
    if rng is None:
        return {"ok": False, "neden": f"Beklenen aralık için en az {MIN_POINTS} geçmiş pencere gerekir.", **base}
    return {"ok": True, **base, **rng}


def suggest_threshold(rng: dict[str, Any], condition: str) -> Optional[dict[str, Any]]:
    """Kurala göre eşik önerisi: «büyüktür» kuralında beklenen aralığın üstü, «küçüktür» kuralında altı."""
    if not rng or not rng.get("ok", True) or rng.get("alt") is None:
        return None
    if condition in ("gt", "gte"):
        v, why = rng["ust"], "beklenen aralığın üst sınırı"
    elif condition in ("lt", "lte"):
        v, why = rng["alt"], "beklenen aralığın alt sınırı"
    else:
        return None
    return {"esik": round(v, 2), "gerekce": why, "alt": rng["alt"], "ust": rng["ust"], "merkez": rng.get("merkez"),
            "yontem": rng.get("yontem"), "nokta": rng.get("nokta"), "etiket": "Kurala göre öneri"}


def range_facts(rng: dict[str, Any], rule_title: str) -> list[str]:
    unit = rng.get("birim") or ""
    out = [f"Kural: {rule_title}.", f"Dönem {rng.get('donem')}: {tr_amount(rng.get('deger'), unit)}.",
           f"Beklenen aralık: {tr_amount(rng['alt'], unit)} – {tr_amount(rng['ust'], unit)} (merkez {tr_amount(rng.get('merkez'), unit)})."]
    out.append("Değer beklenen aralığın " + ("üstünde." if rng.get("yon") == "ust" else "altında." if rng.get("yon") == "alt" else "içinde."))
    out.append("Aralık geçmiş 24 ayın aynı penceresinden, yıllık orana göre mevsim ayıklanarak hesaplandı." if rng.get("yontem") == "mevsimsel"
               else "Aralık son 12 ayın aynı penceresinin medyanından hesaplandı.")
    return out


# ================================================================================ bütçe sapması (M46 / M45)


def _dim(did: str, ad: str, karsi: str, rows: list[tuple[str, str, float, float]]) -> dict[str, Any]:
    """(anahtar, ad, simdi, onceki) satırlarından boyut."""
    dec = decompose([{"anahtar": k, "ad": n, "deger": s} for k, n, s, _ in rows],
                    [{"anahtar": k, "ad": n, "deger": p} for k, n, _, p in rows])
    return {"id": did, "ad": ad, "karsi": karsi, **dec}


def budget_reason(engine: Any, tenant: str, alert_id: str) -> dict[str, Any]:
    """Bütçe sapma satırının nedeni: satışta kitap katkısı (hedefe göre) ve kanal/cari katkısı (geçen yılın aynı
    tamamlanmış aylarına göre, M45'in Logo okumasından); giderde ay ay aşım. Rakamlar M46/M45 tablolarından; model yok."""
    import sqlalchemy as sa

    from semantic_bridge import budget as B
    from semantic_bridge import finance as F

    B.ensure(engine)
    with engine.connect() as c:
        a = c.execute(sa.select(B.ALERTS).where(B.ALERTS.c.id == alert_id, B.ALERTS.c.tenant_id == tenant)).first()
        if a is None:
            raise VarianceError("Sapma bulunamadı.")
        plan = c.execute(sa.select(B.PLANS).where(B.PLANS.c.id == a.plan_id)).first()
        books = c.execute(sa.select(B.BOOKS).where(B.BOOKS.c.plan_id == a.plan_id)).all() if plan else []
    if plan is None:
        raise VarianceError("Sapmanın planı bulunamadı.")
    asof = B._asof(engine, plan.year)
    if asof is None:
        raise VarianceError("Bu yıl için gerçekleşme okunmadı.")
    dims: list[dict[str, Any]] = []
    notes: list[str] = []
    birim = "₺"
    if a.kind == "satis":
        sel = [r for r in books if a.scope == "toplam" or (a.scope == "kitap" and r.stok_kodu == a.key)
               or (a.scope == "yayinevi" and (r.yayinevi or "Yayınevi belirsiz") == a.key)]
        tr, _ = B._track_books(engine, plan, sel)
        if a.scope != "kitap":
            dims.append(_dim("kitap", "Kitap", "hedefe göre (beklenen ciro)",
                             [(r.stok_kodu, r.ad or r.stok_kodu, t["gercekCiro"], t["beklenenCiro"]) for r, t in zip(sel, tr)]))
        # geçen yılın aynı tamamlanmış aylarına göre kanal ve cari (M45 okuması)
        last_full = asof.month if asof == date(asof.year, asof.month, calendar.monthrange(asof.year, asof.month)[1]) else asof.month - 1
        if last_full >= 1:
            F.ensure(engine)
            codes = {r.stok_kodu for r in sel}
            with engine.connect() as c:
                def items(year: int) -> dict[str, float]:
                    q = sa.select(F.PROFIT_ITEMS.c.kanal, F.PROFIT_ITEMS.c.stok_kodu, F.PROFIT_ITEMS.c.net).where(
                        F.PROFIT_ITEMS.c.year == year, F.PROFIT_ITEMS.c.month.between(1, last_full))
                    out: dict[str, float] = {}
                    for kanal, code, net in c.execute(q).all():
                        if a.scope == "toplam" or code in codes:
                            out[kanal] = out.get(kanal, 0.0) + float(net or 0)
                    return out
                now_k, prev_k = items(plan.year), items(plan.year - 1)
                clients_now: dict[str, tuple[str, float]] = {}
                clients_prev: dict[str, float] = {}
                if a.scope == "toplam":
                    for y, sink in ((plan.year, "now"), (plan.year - 1, "prev")):
                        q = sa.select(F.PROFIT_CLIENTS.c.cari_kodu, F.PROFIT_CLIENTS.c.cari_adi, F.PROFIT_CLIENTS.c.net).where(
                            F.PROFIT_CLIENTS.c.year == y, F.PROFIT_CLIENTS.c.month.between(1, last_full))
                        for code, name, net in c.execute(q).all():
                            if sink == "now":
                                n0 = clients_now.get(code, (name, 0.0))
                                clients_now[code] = (n0[0] or name, n0[1] + float(net or 0))
                            else:
                                clients_prev[code] = clients_prev.get(code, 0.0) + float(net or 0)
            if now_k or prev_k:
                ay = f"Ocak–{B.AY[last_full - 1]}"
                karsi = f"geçen yılın aynı aylarına göre ({ay}, net satış)"
                dims.append(_dim("kanal", "Kanal", karsi, [(k, k, now_k.get(k, 0.0), prev_k.get(k, 0.0)) for k in set(now_k) | set(prev_k)]))
                if clients_now or clients_prev:
                    keys = set(clients_now) | set(clients_prev)
                    dims.append(_dim("cari", "Cari", karsi, [(k, (clients_now.get(k) or (k, 0))[0] or k, (clients_now.get(k) or ("", 0.0))[1],
                                                               clients_prev.get(k, 0.0)) for k in keys]))
            else:
                notes.append("Kanal ve cari kırılımı için Finansal raporlar okuması bu yılda yok.")
        else:
            notes.append("Yılın ilk ayı tamamlanmadı; geçen yılla kanal karşılaştırması yapılmadı.")
    elif a.kind == "gider":
        center, _, hesap = str(a.key).partition("|")
        with engine.connect() as c:
            d = c.execute(sa.select(B.DEPTS).where(B.DEPTS.c.plan_id == plan.id, B.DEPTS.c.merkez_kodu == center,
                                                   B.DEPTS.c.hesap == hesap)).first()
        if d is None:
            raise VarianceError("Sapmanın bütçe satırı bulunamadı.")
        budget_m = B._j(d.aylar_json, [0.0] * 12)
        elapsed = B.elapsed_shares(plan.year, asof)
        actual = (B._expenses_by_line(engine, B.month_index(plan.year, 1), B.month_index(plan.year, 13)).get((center, hesap)) or {}).get("aylar") or [0.0] * 12
        rows = [(f"{i + 1:02d}", B.AY[i], float(actual[i] or 0), float(budget_m[i] or 0) * elapsed[i]) for i in range(12) if elapsed[i] > 0]
        dims.append(_dim("ay", "Ay", "bütçeye göre (geçen günlere düşen pay)", rows))
    else:
        raise VarianceError("Bu sapma türü ayrıştırılmaz.")
    total = {"simdi": round(float(a.actual or 0), 2), "onceki": round(float(a.expected or 0), 2),
             "fark": round(float(a.actual or 0) - float(a.expected or 0), 2),
             "oran": round((float(a.actual or 0) - float(a.expected or 0)) / float(a.expected), 4) if a.expected else None}
    return {"ok": True, "olcu": {"ad": a.label or a.key, "birim": birim}, "sapma": {"id": a.id, "tur": a.kind, "kapsam": a.scope},
            "donem": {"etiket": f"{plan.year} yıl başından {asof.strftime('%d.%m.%Y')}'e", "bas": f"{plan.year}-01-01",
                      "bit": (asof + timedelta(days=1)).isoformat()},
            "karsi": {"tur": "hedef", "ad": "bütçe/hedef", "etiket": "hedefin bugüne düşen payı"},
            "kirpildi": False, "toplam": total, "boyutlar": dims, "notlar": notes,
            "kaynak": {"tablolar": ["semantic_budget_*", "semantic_finance_profit_items", "semantic_finance_profit_clients"]}}
