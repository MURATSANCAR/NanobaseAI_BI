"""Fark ayrıştırma — «rakam neden değişti?» (öneri 4) ve beklenen aralık / eşik önerisi (öneri 6).

Tek iş: bir ölçünün iki dönem arasındaki farkını kanal (`CLCARD.SPECODE2`), cari ve kitap katkısına ayırmak; en çok
katkı yapan kırılımları pay ve yönüyle vermek. Rakamı model üretmez: bütün sayılar yürütücünün SQL'inden gelir, Zeki AI
yalnız anlatır (`zeki_text.interpret`, sayı denetimli; tutmazsa kural metni).

**Ölçü sohbet cevabının planından gelir.** Eski semantik katalog 2026-10-01'de emekliye ayrıldı; ayrıştırma artık finans
motorunun planını (`finance_query.Plan`) okur: sohbet cevabında sorgu kaydındaki plan (`resolved_json.plan`), pano kartı
ve uyarıda sorunun planlayıcıdan geçmiş hâli. Aynı plan kanal/cari/kitap kırılımıyla ve iki dönem için yine motorun
yürütücüsünde koşar; ölçü tanımı (KDV matrahı, fatura tarihi, iptal ve iade kuralı), filtreler, satış türü ve yıl
kopyaları sohbet cevabıyla birebir aynıdır, burada SQL yazılmaz. Yalnız toplanabilir satış satırı ölçüleri (satış/net
satış/iade tutarı, satılan/net adet) ayrıştırılır; oran, fatura sayısı, CRM ve rapor planları «ayrıştırılamadı» ve
nedeniyle döner, tahmin edilmez.

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
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import zeki_text as Z

log = logging.getLogger(__name__)

#: Ayrıştırma boyutları → finans motorunun kırılımı ve satırdaki anahtar/ad kolonları.
DIMENSIONS: dict[str, dict[str, Any]] = {
    "kanal": {"ad": "Kanal", "boyut": "channel", "anahtar": "channel", "etiket": None},
    "cari": {"ad": "Cari", "boyut": "customer", "anahtar": "customer_code", "etiket": "customer_name"},
    "kitap": {"ad": "Kitap", "boyut": "book", "anahtar": "book_code", "etiket": "book_name"},
}
DEFAULT_DIMS = ("kanal", "cari", "kitap")
COMPARE = {"gecen-yil": "geçen yılın aynı dönemi", "onceki-donem": "önceki dönem"}
#: Kırılımda boş kanal kodu (ekranda okunur ad).
EMPTY_CHANNEL = "Grup kodu boş"
#: Ayrıştırılabilen ölçüler: faturalı satış satırı üzerinde toplanabilir SUM (kırılımların toplamı bütüne eşit).
ADDITIVE_FAMILY = "sales"

#: Planı yürütür: `fetch(plan)` → (satırlar, çalıştırılan SQL'ler). Köprüde `executor_fetch(rt)`.
Fetch = Callable[[Any], tuple[list[dict[str, Any]], list[str]]]


class VarianceError(ValueError):
    """Ekrana olduğu gibi yazılan düz Türkçe neden."""


# ================================================================================ ölçü: cevabın planı


@dataclass
class Target:
    """Ayrıştırılacak hesap: tek ölçü, planın filtreleri ve satış türü, en yeni dönemi [bas, bit)."""
    olcu: str
    ad: str
    birim: str
    bas: date
    bit: date
    filtreler: tuple = ()
    satis_turu: str = "all"

    def as_dict(self) -> dict[str, Any]:
        return {"ad": self.ad, "birim": self.birim, "olcu": self.olcu,
                "filtreler": [list(f) for f in self.filtreler], "satisTuru": self.satis_turu}


def plan_of(state: Any) -> Optional[dict[str, Any]]:
    """Sorgu kaydındaki (`resolved_json`) ya da doğrudan verilen plan sözlüğü; plan yoksa None."""
    if not isinstance(state, dict):
        return None
    plan = state.get("plan") if "plan" in state else state if "metrics" in state else None
    return plan if isinstance(plan, dict) else None


def _unit(code: str) -> str:
    return "₺" if code == "TRY" else code


def target_of(plan: Optional[dict[str, Any]]) -> tuple[Optional[Target], Optional[str]]:
    """Planın ayrıştırılabilir hedefi; olmazsa (None, neden). Neden ekrana olduğu gibi gider."""
    from semantic_bridge.finance_query.contracts import METRICS

    if not plan:
        return None, "Bu cevabın hesap planı yok; ayrıştırma bir satış ölçüsünün planından yapılır."
    if any(plan.get(k) for k in ("crm", "logo_report", "crm_report", "relational_query", "sections")):
        return None, "Ayrıştırma yalnız satış ölçüsü cevaplarında yapılır; bu cevap bir rapor ya da CRM listesi."
    if plan.get("derived") or plan.get("analytics"):
        return None, "Cevap oran ya da türetilmiş hesap içeriyor; katkıya bölünemez."
    comparison = plan.get("comparison") or {}
    metrics = [comparison["metric"]] if comparison.get("metric") else list(plan.get("metrics") or [])
    if not metrics:
        return None, "Cevapta ölçü yok."
    if len(metrics) > 1:
        return None, "Cevapta birden çok ölçü var; ayrıştırma tek ölçüde yapılır."
    metric = METRICS.get(metrics[0])
    if metric is None or metric.family != ADDITIVE_FAMILY:
        return None, "Ayrıştırma yalnız toplanabilir satış ölçülerinde (satış, net satış, iade tutarı ya da adedi) yapılır."
    periods = [(_d(a), _d(b)) for a, b in (plan.get("periods") or [])]
    periods = [(a, b) for a, b in periods if a and b and a < b]
    if not periods:
        return None, "Soruda dönem yok; ayrıştırma iki dönemi karşılaştırır."
    # İki dönem anılmışsa («2025 ile 2026») en yeni dönem «şimdi»; karşı dönem ayrıştırmanın kendi seçimidir.
    a, b = max(periods, key=lambda p: (p[1], p[0]))
    filters = tuple(tuple(str(x) for x in f) for f in (plan.get("filters") or []))
    return Target(olcu=metrics[0], ad=metric.label, birim=_unit(metric.unit), bas=a, bit=b, filtreler=filters,
                  satis_turu=str(plan.get("sale_kind") or "all")), None


def leaf_plan(t: Target, dimension: Optional[str], a: date, b: date) -> Any:
    """Hedefin tek kırılımlı, tek dönemli planı (yürütücünün kendi doğrulamasından geçer)."""
    from semantic_bridge.finance_query.planner import Plan

    return Plan(metrics=(t.olcu,), dimensions=(dimension,) if dimension else (), periods=((a.isoformat(), b.isoformat()),),
                filters=t.filtreler, sale_kind=t.satis_turu)


def executor_fetch(rt: Any, seen: Optional[list[dict[str, Any]]] = None) -> Fetch:
    """Köprüde planı finans motorunun yürütücüsüyle koşturur (yetki, yıl kopyaları, okuma kapısı sohbetle aynı).
    `seen` verilirse her kaynak okumasının SQL'i, satırı ve süresi eklenir (uyarının sorgu bilgisi)."""
    from semantic_bridge.finance_query.executor import Executor

    def fetch(plan: Any) -> tuple[list[dict[str, Any]], list[str]]:
        ex = Executor(rt)
        rows = ex.execute(plan)
        if seen is not None:
            seen.extend({"sql": run["sql"], "rows": run.get("rows"), "ms": run.get("dbMs"), "at": run.get("startedAt")}
                        for run in ex.runs)
        return rows, [f"-- {run['source']}\n{run['sql']}" for run in ex.runs]
    return fetch


#: Soru metni → plan (pano kartı, uyarı). Planlayıcı model çağırır; aynı gün aynı soru bir kez planlanır.
_PLANS: dict[tuple[str, str], dict[str, Any]] = {}


def plan_for_question(rt: Any, question: str) -> Optional[dict[str, Any]]:
    """Sorunun finans planı (bağlamsız). Planlanamayan soru None — neden `target_of` mesajıyla söylenir."""
    from semantic_bridge.finance_query import ContractError, planner

    q = " ".join(str(question or "").split())[:2000]
    if not q:
        return None
    key = (date.today().isoformat(), q)
    if key not in _PLANS:
        if len(_PLANS) > 500:
            _PLANS.clear()
        try:
            _PLANS[key] = planner.build(q, rt.llm_for("finance"), None, []).to_dict()
        except ContractError as e:
            log.info("fark: soru planlanamadı: %s", e)
            return None
    return _PLANS[key]


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


def _rows_for(rows: list[dict[str, Any]], dim: str, metric: str) -> list[dict[str, Any]]:
    """Yürütücü satırı → {anahtar, ad, deger}. Boş kanal kodu okunur ada çevrilir."""
    spec = DIMENSIONS[dim]
    out = []
    for r in rows:
        key = r.get(spec["anahtar"])
        key = str(key).strip() if key not in (None, "") else (EMPTY_CHANNEL if dim == "kanal" else "#YOK")
        out.append({"anahtar": key or (EMPTY_CHANNEL if dim == "kanal" else "#YOK"),
                    "ad": r.get(spec["etiket"]) if spec["etiket"] else key, "deger": r.get(metric)})
    return out


def _daily(fetch: Fetch, t: Target, a: date, b: date, sqls: list[dict[str, str]], ad: str) -> dict[date, float]:
    rows, ran = fetch(leaf_plan(t, "day", a, b))
    sqls.extend({"ad": ad, "sql": s} for s in ran)
    return {d: _f(r.get(t.olcu)) for r in rows for d in [_d(r.get("day"))] if d}


def run(fetch: Fetch, t: Target, *, karsi: str = "gecen-yil", boyutlar: Iterable[str] = DEFAULT_DIMS) -> dict[str, Any]:
    """Ayrıştırmayı çalıştırır: önce dönemin gün gün toplamı (veri sonu ve kırpma), sonra her boyut iki dönem için."""
    if karsi not in COMPARE:
        raise VarianceError("Karşı dönem «gecen-yil» ya da «onceki-donem» olmalı.")
    dims = [x for x in boyutlar if x in DIMENSIONS] or list(DEFAULT_DIMS)
    a, b = t.bas, t.bit
    sqls: list[dict[str, str]] = []
    daily = _daily(fetch, t, a, b, sqls, f"Gün gün · {label(a, b)}")
    seen = [d for d, v in daily.items() if abs(v) > 1e-9]
    end_seen = max(seen) if seen else None
    eff_b, clipped = b, False
    if end_seen is not None and end_seen + timedelta(days=1) < b:
        eff_b, clipped = end_seen + timedelta(days=1), True
    ca, cb = compare_window(a, eff_b, karsi)
    out_dims = []
    for dim in dims:
        spec = DIMENSIONS[dim]
        cur, ran = fetch(leaf_plan(t, spec["boyut"], a, eff_b))
        sqls.extend({"ad": f"{spec['ad']} · {label(a, eff_b)}", "sql": s} for s in ran)
        prev, ran = fetch(leaf_plan(t, spec["boyut"], ca, cb))
        sqls.extend({"ad": f"{spec['ad']} · {label(ca, cb)}", "sql": s} for s in ran)
        dec = decompose(_rows_for(cur, dim, t.olcu), _rows_for(prev, dim, t.olcu))
        out_dims.append({"id": dim, "ad": spec["ad"], **dec})
    head = out_dims[0] if out_dims else {"simdi": 0.0, "onceki": 0.0, "fark": 0.0, "oran": None}
    return {"ok": True, "olcu": t.as_dict(), "donem": {"bas": a.isoformat(), "bit": eff_b.isoformat(), "etiket": label(a, eff_b)},
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


def hint(plan: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Sohbet cevabı / pano kartı / uyarı için: bu plan ayrıştırılabilir mi (SQL koşmaz). Ekran «Neden?»i buna göre gösterir."""
    t, why = target_of(plan)
    if t is None:
        return {"ok": False, "neden": why}
    return {"ok": True, "olcu": t.ad, "birim": t.birim, "bas": t.bas.isoformat(), "bit": t.bit.isoformat()}


def for_plan(fetch: Fetch, plan: Optional[dict[str, Any]], *, karsi: str = "gecen-yil",
             boyutlar: Iterable[str] = DEFAULT_DIMS) -> dict[str, Any]:
    t, why = target_of(plan)
    if t is None:
        raise VarianceError(why or "Ayrıştırılamadı.")
    return run(fetch, t, karsi=karsi, boyutlar=boyutlar)


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


def measure_range(fetch: Fetch, plan: Optional[dict[str, Any]], *, k: float = 2.0) -> dict[str, Any]:
    """Planın ölçüsü için beklenen aralık (bugünkü penceresi ve geçmiş 24 ay, tek gün gün okuma). Hesaplanamazsa
    {"ok": False, "neden"}."""
    t, why = target_of(plan)
    if t is None:
        return {"ok": False, "neden": why.replace("ayrıştırma iki dönemi karşılaştırır", "beklenen aralık bir pencerenin geçmişiyle hesaplanır")
                if why else why}
    a, b = t.bas, t.bit
    start = add_months(a, -LAGS)
    sqls: list[dict[str, str]] = []
    try:
        daily = _daily(fetch, t, start, b, sqls, "Gün gün geçmiş")
    except Exception as e:  # noqa: BLE001 — geçmişin bir kısmı için kaynak yoksa aralık uydurulmaz
        from semantic_bridge.finance_query import ContractError

        if isinstance(e, ContractError):
            return {"ok": False, "neden": f"Geçmiş 24 ay okunamadı: {e}"}
        raise
    seen = [d for d, v in daily.items() if abs(v) > 1e-9]
    last = max(seen) if seen else None
    eff_b = b
    if last is not None and last + timedelta(days=1) < b:
        eff_b = last + timedelta(days=1)
    if last is None or eff_b <= a:
        return {"ok": False, "neden": "Bu dönemde henüz veri yok.", "kaynak": {"sql": sqls}}
    cur, lags = window_lags(daily, a, eff_b)
    rng = expected_range(cur, lags, k=k)
    base = {"olcu": t.ad, "birim": t.birim, "donem": label(a, eff_b), "kirpildi": eff_b != b, "kaynak": {"sql": sqls}}
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
