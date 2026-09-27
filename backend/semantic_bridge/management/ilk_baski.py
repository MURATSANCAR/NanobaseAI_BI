"""M10 İlk baskı ve satış tahmini — gizli yönetim raporu (kendi ekranı: /ilk-baski).

Günde bir kez CRM'den kitap kartlarını, editörün girdiği emsalleri ve baskı adetlerini, Logo'dan 2015'ten bu yana
kitap × ay × kanal satışını okur; hesap çekirdeği `ilk_baski_model`. Sonuç (yayımlanacak kitapların tahmini, ilk
satış takibi, geçmiş sınama ve anlık tahmin için sıkıştırılmış veri kümesi) rapor önbelleğine yazılır; ekranın
uçları (`ilk_baski_api`) oradan okur, Logo'ya gitmez.

Baskı Öneri raporuyla aynı altyapı: aynı Logo satış görünümleri ve süzgeç (`{satis:yil}`), aynı CRM kitap
görünümleri, aynı zamanlayıcı ve önbellek. Pazar düzeyi düzeltmesi açıksa (ayarda `beta` > 0) gelecek ayların
portföy düzeyi Baskı Öneri tahmin sekmesinin kullandığı tahmin servisinden (`zeki_tahmin.post_batch`) gelir.
"""
from __future__ import annotations

import math
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Callable

from semantic_bridge.management import ilk_baski_model as M
from semantic_bridge.management import zeki_tahmin

REPORT_ID = "ilk-baski"
TITLE = "İlk baskı ve satış tahmini"
DESCRIPTION = "Yeni kitap için emsal kitapların satışından ilk baskı adedi ve satış tahmini."
HIDDEN = True  # Yönetim raporları listesinde değil; kendi ekranı var
STANDALONE = True  # başka raporun girdisi değil: zamanlayıcı ve diğer raporlar bu dosyayı okumaz
MODEL_FILE = "ilk-baski.model.json"  # anlık tahminin veri kümesi (büyük): rapor önbelleğinin yanında ayrı dosya
REFRESH_SECONDS = int(os.environ.get("FIRST_PRINT_REFRESH_SECONDS", str(24 * 3600)))
FIRST_YEAR = zeki_tahmin.FIRST_YEAR
GAP = 2               # tahmin lansmandan 2 ay önce yapılır: sınamada kesim = lansman − 2 (baskı kararı zamanı)
HORIZONS = (6, 12)    # ilk 6 ay (en az ilk baskı) ve ilk 12 ay
FIT_FROM, FIT_TO = (2021, 7), (2023, 12)  # kalibrasyon (ayar seçimi) dönemi; sınama 2024 başından
TEST_FROM = (2024, 1)
CALIB_MIN = 100      # güven düzeyine özel kalibrasyon için en az örnek; azsa bütün seçim dönemi (2026-09-28: 20 ile düşük güvende kapsama %49)
TRACK_MONTHS = 6      # ilk satış takibi: son 6 ayda çıkan kitaplar
UPCOMING_BACK_MONTHS = 18  # ilk yayını boş kartlarda: son 18 ayda açılmış kart «yayımlanacak» sayılır
CLOSED_STATUS = ("YS01", "YS05", "YS07", "YS08", "YS10P", "YS11")  # iptal, bizim değil, basılmayacak…

SOURCES = [
    ("crm_kitaplar", "crm", "Kitap kartları", "Emsal aramanın özellikleri (yazar, dizi, kitaplık, yayınevi, hedef "
     "kitle, tür, sayfa, fiyat) ve ilk yayın tarihi."),
    ("crm_emsal", "crm", "Emsal kitaplar", "Kitap kartında editörün girdiği emsal kitaplar."),
    ("crm_baski", "crm", "Baskı adetleri", "Kitabın baskı sayısı ve son baskı adedi: geçmiş ilk baskı kararları."),
    ("logo_son_fatura", "logo", "Son fatura tarihi", "Logo'daki en son fatura günü; son tam ayı belirler."),
    ("logo_aylik_kanal", "logo", "Aylık kanal satışı",
     "Kitap × ay × kanal net satış adedi ve tutarı; 2015'ten bu yana her yıl ayrı okunur."),
]
FORMULAS = [
    ("Lansman", "Kitabın Logo'daki ilk net satış ayı; CRM ilk yayın ayıyla en çok 3 ay fark (daha büyük fark başka "
                "baskının devamıdır, emsal olmaz)."),
    ("Emsal puanı", "CRM emsali + aynı yazar + aynı dizi + aynı kitaplık + aynı yayınevi + aynı hedef kitle + tür "
                    "örtüşmesi + fiyat (çıktığı yılın fiyatlarına göre) ve sayfa yakınlığı; eski lansmanın puanı azalır."),
    ("Baz tahmin", "En yüksek puanlı emsallerin ilk 6 / 12 aylık net satışının puan ağırlıklı ortancası × kalibrasyon."),
    ("Senaryolar", "Kötümser / baz / iyimser: geçmiş sınamada gerçekleşenin tahmine oranının %20 / %50 / %80 "
                   "noktaları; güven aralığı %10–%90. Emsal gücü azsa aralık geniştir."),
    ("İlk baskı önerisi", "Baz senaryonun ilk 6 aylık satışı, yayınevinin kullandığı en yakın üst baskı adedine "
                          "yuvarlanır. Tükenme olasılığı: geçmiş sınamada bu kadar basılsaydı 6 ayda tükenen kitap oranı."),
    ("Ciro", "Adet × kapak fiyatı × emsallerin ilk 6 ayındaki net tutar / liste tutarı oranı (iskonto)."),
    ("Revize tahmin", "Gerçekleşen ilk aylar × emsallerin aynı aydan 6. / 12. aya büyümesi (puan ağırlıklı ortanca)."),
]
NOTES = [
    "Satış Logo'daki faturalı satıştır, iade düşülmüş net adettir (Baskı Öneri ile aynı satırlar).",
    "Logo kopyasının son faturası rapordaki tarih kadar günceldir; sonrasındaki satış tahmine girmez.",
]


def _day(v: Any) -> date | None:
    return zeki_tahmin._day(v)


# ---------------------------------------------------------------- yardımcılar

def print_steps(baski_rows: list[dict]) -> list[int]:
    """Yayınevinin kullandığı ilk baskı adetleri (tek baskılı kitaplarda en az 3 kez kullanılmış adet)."""
    c = Counter(int(r["son_baski_adet"]) for r in baski_rows
                if (r.get("baski_sayisi") or 0) == 1 and M.num(r.get("son_baski_adet")))
    steps = sorted(a for a, n in c.items() if n >= 3)
    return steps


def round_print(x: float, steps: list[int]) -> int:
    """En yakın üst baskı adedi; basamakların üstündeyse bine yuvarlanır. Basamak yoksa 500'ün katı."""
    for s in steps:
        if s >= x:
            return s
    unit = 1000 if steps else 500
    return int(math.ceil(max(x, 1) / unit) * unit)


def _quantiles(values: list[float]) -> dict[float, float]:
    v = sorted(values)
    out = {}
    for q in (0.1, 0.2, 0.5, 0.8, 0.9):
        pos = q * (len(v) - 1)
        lo, hi = int(math.floor(pos)), int(math.ceil(pos))
        out[q] = v[lo] + (v[hi] - v[lo]) * (pos - lo)
    return out


def targets(ds: M.Dataset, lo: int, hi: int, h: int) -> list[str]:
    return [c for c in ds.by_launch if lo <= ds.books[c].launch <= hi and ds.books[c].launch + h - 1 <= ds.end]


class Engine:
    """Veri kümesi + kalibrasyon: bir kitabın tahminini kurar (rapor hazırlanırken ve ekrandan anlık)."""

    def __init__(self, ds: M.Dataset, level: dict[int, float] | None, calib: dict, steps: list[int],
                 params: dict | None = None, baski: dict[str, dict] | None = None):
        self.ds, self.level, self.calib, self.steps = ds, level, calib, steps
        self.p = params or M.PARAMS
        self.baski = baski or {}
        self.rule_stats: dict[str, dict] = {}  # geçmiş sınamada kural başına tükenme / elde kalan
        self._pools: dict[tuple[int, int], list[str]] = {}

    def pool(self, cutoff: int, h: int) -> list[str]:
        key = (cutoff, h)
        if key not in self._pools:
            self._pools[key] = M.pool_for(self.ds, cutoff, h)
        return self._pools[key]

    def raw(self, book: M.Book, launch: int, cutoff: int, h: int, emsal: list[str] | None = None) -> M.Forecast | None:
        return M.forecast(self.ds, book, launch, cutoff, h, M.params_for(h, self.p), level=self.level,
                          pool=self.pool(cutoff, h), emsal=emsal)

    def ratios(self, h: int, tier: str) -> dict[float, float]:
        c = self.calib.get(str(h), {})
        return {float(k): v for k, v in (c.get(tier) or c.get("hepsi") or {}).items()}

    def scenarios(self, fc: M.Forecast, h: int) -> dict:
        tier = M.confidence_tier(fc, self.p)
        r = self.ratios(h, tier)
        val = {q: fc.base * r.get(q, 1.0) for q in (0.1, 0.2, 0.5, 0.8, 0.9)}
        return {"tier": tier, "values": val}

    def stockout(self, fc: M.Forecast, h: int, qty: float) -> float | None:
        """Geçmiş sınamada gerçekleşen/tahmin oranları: bu kadar basılsaydı h ayda tükenme olasılığı."""
        tier = M.confidence_tier(fc, self.p)
        c = self.calib.get(str(h), {})
        rs = c.get("ratios", {}).get(tier) or c.get("ratios", {}).get("hepsi")
        if not rs or fc.base <= 0:
            return None
        lim = qty / fc.base
        return sum(1 for x in rs if x > lim) / len(rs)

    def curve(self, fc: M.Forecast, h: int) -> list[float]:
        """Emsallerin aylık dağılımı (puan ağırlıklı ortalama pay)."""
        shares = [0.0] * h
        tot_w = 0.0
        for a, w in zip(fc.analogs, fc.weights):
            o = self.ds.outcomes[a["code"]]
            t = o.total(h)
            if not t or t <= 0:
                continue
            for j in range(h):
                shares[j] += w * max(o.months[j], 0.0) / t
            tot_w += w
        if tot_w <= 0:
            return [1.0 / h] * h
        s = sum(shares)
        return [x / s for x in shares] if s > 0 else [1.0 / h] * h

    def channels(self, fc: M.Forecast) -> list[dict]:
        acc: dict[str, float] = defaultdict(float)
        tot_w = 0.0
        for a, w in zip(fc.analogs, fc.weights):
            ch = self.ds.outcomes[a["code"]].channels
            pos = {k: v for k, v in ch.items() if v > 0}
            t = sum(pos.values())
            if t <= 0:
                continue
            for k, v in pos.items():
                acc[k] += w * v / t
            tot_w += w
        if tot_w <= 0:
            return []
        return sorted(({"channel": k, "share": v / tot_w} for k, v in acc.items()), key=lambda x: -x["share"])

    def price_ratio(self, fc: M.Forecast) -> float | None:
        num_ = den = 0.0
        for a, w in zip(fc.analogs, fc.weights):
            o = self.ds.outcomes[a["code"]]
            if o.listv > 0 and o.net > 0:
                num_ += w * o.net / o.listv
                den += w
        return num_ / den if den else None

    def full(self, book: M.Book, launch: int, emsal: list[str] | None = None, cutoff: int | None = None) -> dict | None:
        """Ekranın kitap ayrıntısı: iki ufuk, senaryolar, öneri, kanal, aylık eğri, emsaller, gerekçe."""
        cutoff = min(cutoff if cutoff is not None else self.ds.end, launch - 1)
        out: dict[str, Any] = {"book": book.public(), "launch": M.ms(launch), "launchName": M.month_name(launch),
                               "cutoff": M.ms(cutoff), "horizons": {}}
        fc6 = None
        for h in HORIZONS:
            fc = self.raw(book, launch, cutoff, h, emsal)
            if fc is None:
                continue
            fc6 = fc6 or (fc if h == 6 else None)
            sc = self.scenarios(fc, h)
            v = sc["values"]
            curve = self.curve(fc, h)
            cum, run = [], 0.0
            for j, s in enumerate(curve):
                run += s
                cum.append({"month": M.ms(launch + j), "label": M.month_name(launch + j), "share": round(s, 4),
                            "low": round(v[0.1] * run), "base": round(v[0.5] * run), "high": round(v[0.9] * run),
                            "pess": round(v[0.2] * run), "opt": round(v[0.8] * run)})
            ratio = self.price_ratio(fc)
            unit = book.price * ratio if book.price and ratio else None
            out["horizons"][str(h)] = {
                "tier": sc["tier"],
                "scenarios": [{"id": sid, "label": lab, "units": round(v[q]),
                               "revenue": round(v[q] * unit) if unit else None} for sid, lab, q in M.SCENARIOS],
                "band": {"low": round(v[0.1]), "high": round(v[0.9])},
                "raw": round(fc.base),
                "curve": cum,
                "unitRevenue": round(unit, 2) if unit else None, "discount": round(1 - ratio, 3) if ratio else None,
                "analogs": fc.analogs,
                "channels": [{"channel": c["channel"], "share": round(c["share"], 4), "units": round(c["share"] * v[0.5])}
                             for c in self.channels(fc)],
            }
        if fc6 is None:
            return None
        values = {}
        for h in HORIZONS:
            if str(h) in out["horizons"]:
                fc_h = self.raw(book, launch, cutoff, h, emsal)
                values[h] = self.scenarios(fc_h, h)["values"]
        options = []
        for rid, lab, h, q in PRINT_RULES:
            if h not in values:
                continue
            units = round_print(values[h][q], self.steps)
            options.append({"rule": rid, "label": lab, "units": units, "stockout6": self.stockout(fc6, 6, units),
                            "history": (self.rule_stats or {}).get(rid)})
        rec = next(o for o in options if o["rule"] == RECOMMEND_RULE) if any(o["rule"] == RECOMMEND_RULE for o in options) \
            else options[0]
        minimum = next((o for o in options if o["rule"] == "baz6"), None)
        out["recommendation"] = {
            "units": rec["units"], "rule": rec["rule"],
            "basis": RECOMMEND_BASIS,
            "minimum": minimum["units"] if minimum else None,
            "stockout6": rec["stockout6"],
            "options": options,
        }
        out["reasons"] = self.reasons(book, out, fc6)
        return out

    def reasons(self, book: M.Book, out: dict, fc: M.Forecast) -> list[str]:
        h6 = out["horizons"]["6"]
        an = fc.analogs
        tags = Counter(r for a in an for r in a["reasons"])
        lines = []
        strong = [a for a in an if {"CRM emsali", "aynı yazar", "aynı dizi"} & set(a["reasons"])]
        lines.append(f"{len(an)} emsal kitap kullanıldı; {len(strong)} tanesi güçlü eşleşme "
                     f"(CRM emsali, aynı yazar ya da aynı dizi).")
        if tags:
            top = ", ".join(f"{k} ({n})" for k, n in tags.most_common(4))
            lines.append(f"En sık benzerlik: {top}.")
        vals = sorted(a["sales"] for a in an)
        if vals:
            lines.append(f"Emsallerin ilk 6 ayı {vals[0]:,} ile {vals[-1]:,} adet arasında; ortanca "
                         f"{vals[len(vals) // 2]:,}.".replace(",", "."))
        tier = {"yuksek": "yüksek", "orta": "orta", "dusuk": "düşük"}[h6["tier"]]
        lines.append(f"Güven düzeyi {tier}: aralık, geçmiş sınamada bu güven düzeyindeki kitapların gerçekleşen / "
                     f"tahmin oranlarından kuruldu.")
        if not book.price:
            lines.append("Kitabın fiyatı CRM'de yok; ciro hesaplanmadı.")
        if h6["channels"]:
            c0 = h6["channels"][0]
            lines.append(f"Emsallerde satışın en büyük kanalı {c0['channel']} (%{round(c0['share'] * 100)}).")
        return lines


# ---------------------------------------------------------------- sınama

def calibrate(eng: Engine, h: int) -> dict:
    """Seçim döneminin gerçekleşen / ham tahmin oranları, güven düzeyine göre (kantiller + ham oranlar)."""
    ds = eng.ds
    rows = []
    for c in targets(ds, M.mi(*FIT_FROM), M.mi(*FIT_TO), h):
        b = ds.books[c]
        fc = eng.raw(b, b.launch, b.launch - GAP, h)
        if fc is None or fc.base <= 0:
            continue
        rows.append((M.confidence_tier(fc), ds.outcomes[c].total(h) / fc.base))
    out: dict[str, Any] = {"n": len(rows), "ratios": {}}
    for tier in ("yuksek", "orta", "dusuk", "hepsi"):
        r = [x for t, x in rows if tier == "hepsi" or t == tier]
        if len(r) < CALIB_MIN:  # az örnekli düzeyde bütün seçim dönemi kullanılır
            continue
        out[tier] = {str(q): v for q, v in _quantiles(r).items()}
        out["ratios"][tier] = sorted(round(x, 4) for x in r)
    return out


def _metrics(rows: list[tuple[float, float]]) -> dict | None:
    rows = [(p, a) for p, a in rows if p > 0 and a > 0]
    if not rows:
        return None
    n = len(rows)
    le = sorted(abs(math.log(a / p)) for p, a in rows)
    ape = sorted(abs(p - a) / a for p, a in rows)
    lr = sorted(math.log(a / p) for p, a in rows)
    return {
        "n": n,
        "mdape": ape[n // 2],
        "wape": sum(abs(p - a) for p, a in rows) / sum(a for _, a in rows),
        "within25": sum(1 for x in le if x <= math.log(1.25)) / n,
        "within50": sum(1 for x in le if x <= math.log(1.5)) / n,
        "within2x": sum(1 for x in le if x <= math.log(2)) / n,
        "bias": math.exp(lr[n // 2]),
    }


def backtest(eng: Engine, h: int) -> dict:
    """Sınama dönemi (2024+): her kitap lansmandan 2 ay önceki veriyle tahmin edilir, gerçekleşenle karşılaştırılır."""
    ds = eng.ds
    lo = M.mi(*TEST_FROM)
    rows_model, rows_naive, rows_emsal, cover, so = [], [], [], [], {"kotumser": [], "baz": [], "iyimser": [], "oneri": []}
    by_year: dict[int, list] = defaultdict(list)
    by_tier: dict[str, list] = defaultdict(list)
    tier_cover: dict[str, list] = defaultdict(list)
    revise = {1: [], 2: [], 3: []}
    samples = []
    for c in targets(ds, lo, ds.end, h):
        b = ds.books[c]
        cut = b.launch - GAP
        act = ds.outcomes[c].total(h)
        fc = eng.raw(b, b.launch, cut, h)
        if fc is None:
            continue
        sc = eng.scenarios(fc, h)["values"]
        rows_model.append((sc[0.5], act))
        by_year[b.launch // 12].append((sc[0.5], act))
        cover.append(sc[0.1] <= act <= sc[0.9])
        tier = M.confidence_tier(fc)
        by_tier[tier].append((sc[0.5], act))
        tier_cover[tier].append(sc[0.1] <= act <= sc[0.9])
        so["kotumser"].append(act > sc[0.2]); so["baz"].append(act > sc[0.5]); so["iyimser"].append(act > sc[0.8])
        pl = eng.pool(cut, h)
        recent = [ds.outcomes[x].total(h) for x in pl if ds.books[x].launch >= cut - h - 11]
        naive = M._median(recent) if recent else None
        if naive:
            rows_naive.append((naive, act))
        em = [x for x in ds.emsal.get(c, []) if x in set(pl)]
        rows_emsal.append((M._median([ds.outcomes[x].total(h) for x in em]) if em else naive or 0, act))
        if h == 6:
            q = next(q for rid, _, hh, q in PRINT_RULES if rid == RECOMMEND_RULE)
            rec = round_print(sc[q], eng.steps)
            so["oneri"].append(act > rec)
            for m in (1, 2, 3):
                v = M.revise(ds, fc, ds.outcomes[c].months[:m], h)
                if v:
                    revise[m].append((max(sum(ds.outcomes[c].months[:m]), v), act))
        samples.append({"code": c, "name": b.name, "launch": M.ms(b.launch), "forecast": round(sc[0.5]),
                        "low": round(sc[0.1]), "high": round(sc[0.9]), "actual": round(act),
                        "tier": M.confidence_tier(fc)})
    rate = lambda v: (sum(v) / len(v)) if v else None  # noqa: E731
    out = {
        "horizon": h, "from": M.ms(lo), "to": M.ms(ds.end - h + 1),
        "model": _metrics(rows_model), "naive": _metrics(rows_naive), "emsal": _metrics(rows_emsal),
        "coverage80": rate(cover),
        "stockout": {k: rate(v) for k, v in so.items() if v},
        "byYear": {str(y): _metrics(v) for y, v in sorted(by_year.items())},
        "byTier": {t: {**(_metrics(by_tier[t]) or {}), "coverage80": rate(tier_cover[t])}
                   for t in ("yuksek", "orta", "dusuk") if by_tier.get(t)},
        "samples": samples,
    }
    if h == 6:
        out["revise"] = {str(m): _metrics(v) for m, v in revise.items() if v}
    return out


# İlk baskı adedi kuralları: (kimlik, ad, ufuk, kantil). Geçmiş sınamada her biri için 6 / 12 ayda tükenme ve
# 12. ay sonunda elde kalan pay ölçülür; önerilen kural `RECOMMEND_RULE` (ölçümle seçildi, bkz. analiz belgesi).
PRINT_RULES = (
    ("baz6", "İlk 6 ay, baz", 6, 0.5),
    ("iyimser6", "İlk 6 ay, iyimser", 6, 0.8),
    ("ust6", "İlk 6 ay, aralığın üstü", 6, 0.9),
    ("baz12", "İlk 12 ay, baz", 12, 0.5),
    ("iyimser12", "İlk 12 ay, iyimser", 12, 0.8),
)
RECOMMEND_RULE = "iyimser6"
RECOMMEND_BASIS = ("İlk 6 ayın iyimser senaryosu (gerçekleşenin %80 olasılıkla altında kalacağı adet), yayınevinin "
                   "kullandığı en yakın üst baskı adedine yuvarlandı. Asgari: 6 aylık baz satış.")


def print_rules_backtest(eng: Engine, their: dict[str, int]) -> dict:
    """12 ayı gözlenmiş sınama kitaplarında her kural kadar basılsaydı: 6 / 12 ayda tükenme, 12. ay sonunda elde kalan."""
    ds = eng.ds
    rows: dict[str, list] = defaultdict(list)
    their_rows = []
    for c in targets(ds, M.mi(*TEST_FROM), ds.end, 12):
        b = ds.books[c]
        cut = b.launch - GAP
        o = ds.outcomes[c]
        a6, a12 = o.total(6), o.total(12)
        if not a6 or a6 <= 0:
            continue
        vals = {}
        for rid, _, h, q in PRINT_RULES:
            fc = eng.raw(b, b.launch, cut, h)
            if fc is None:
                break
            vals[rid] = round_print(eng.scenarios(fc, h)["values"][q], eng.steps)
        else:
            for rid, qty in vals.items():
                rows[rid].append((qty, a6, a12))
            if c in their:
                their_rows.append((their[c], a6, a12))

    def summ(v):
        if not v:
            return None
        n = len(v)
        return {"n": n, "stockout6": sum(1 for q, a6, _ in v if a6 > q) / n,
                "stockout12": sum(1 for q, _, a12 in v if a12 > q) / n,
                "leftover12": M._median([max(q - a12, 0) / q for q, _, a12 in v]),
                "medianPrint": M._median([q for q, _, _ in v])}

    return {"rules": [{"id": rid, "label": lab, **(summ(rows[rid]) or {})} for rid, lab, *_ in PRINT_RULES],
            "theirs": summ(their_rows), "recommended": RECOMMEND_RULE}


# ---------------------------------------------------------------- rapor

def _level(ds: M.Dataset, post: Callable[[dict], dict], cutoffs: list[int], horizon: int) -> dict[int, dict[int, float]]:
    """Her kesim için portföy düzeyi: o güne kadarki gerçek + sonrası tahmin servisinin beklenen değeri (p50)."""
    p0 = min(ds.portfolio)
    series = [{"id": str(c), "start": M.ms(p0), "values": [ds.portfolio.get(i, 0.0) for i in range(p0, c + 1)]}
              for c in cutoffs]
    out = post({"horizon": min(36, horizon), "series": series, "calendar": True,
                "calendar_peak_months": zeki_tahmin.PEAK_MONTHS, "engine": "timesfm3"})
    levels = {}
    for r in out["results"]:
        c = int(r["id"])
        lv = {i: v for i, v in ds.portfolio.items() if i <= c}
        for j, q in enumerate(r["quantiles"]):
            lv[c + 1 + j] = q[4]
        levels[c] = lv
    return levels


def upcoming_books(ds: M.Dataset, today: date) -> list[tuple[M.Book, int]]:
    """Henüz satışı olmayan, etkin, kapanmamış kitaplar ve tahminde kullanılacak lansman ayı."""
    now = M.mi(today.year, today.month)
    first_card = now - UPCOMING_BACK_MONTHS
    out = []
    for c, b in ds.books.items():
        if not M.is_book(c) or not b.active or (b.status and b.status.split(" ")[0] in CLOSED_STATUS):
            continue
        if sum(v for v in ds.sales.get(c, {}).values() if v > 0) > 0:
            continue
        crm = M.month_of(b.first_pub)
        if crm is None:
            continue  # ilk yayın tarihi girilmemiş kart: kitap aranarak açılır, listeye girmez
        if crm < now - 2:
            continue  # yayın tarihi geçmiş ama hiç satışı yok: eski/iptal kart
        out.append((b, max(crm, ds.end + 1)))
    return sorted(out, key=lambda x: (x[1], x[0].name))


def summary_row(eng: Engine, b: M.Book, launch: int) -> dict | None:
    f = eng.full(b, launch)
    if not f:
        return None
    h6, h12 = f["horizons"].get("6"), f["horizons"].get("12")
    return {**b.public(), "launchUsed": f["launch"], "tier": h6["tier"],
            "base6": h6["scenarios"][1]["units"], "low6": h6["band"]["low"], "high6": h6["band"]["high"],
            "base12": h12["scenarios"][1]["units"] if h12 else None,
            "revenue12": h12["scenarios"][1]["revenue"] if h12 else None,
            "print": f["recommendation"]["units"], "stockout6": f["recommendation"]["stockout6"],
            "analogs": len(h6["analogs"]), "emsal": len(eng.ds.emsal.get(b.code, []))}


def tracking(eng: Engine) -> list[dict]:
    """Aşama 2: son TRACK_MONTHS ayda çıkan kitaplar — lansman öncesi tahmin, gerçekleşen, revize, sapma."""
    ds = eng.ds
    out = []
    for c in ds.by_launch:
        b = ds.books[c]
        if b.launch < ds.end - TRACK_MONTHS + 1:
            continue
        o = ds.outcomes[c]
        fcs = {}
        for h in HORIZONS:
            fc = eng.raw(b, b.launch, b.launch - GAP, h)
            if fc is None:
                continue
            v = eng.scenarios(fc, h)["values"]
            curve = eng.curve(fc, h)
            m = len(o.months)
            exp_m = sum(curve[:m])
            rev = M.revise(ds, fc, o.months, h)
            fcs[str(h)] = {"base": round(v[0.5]), "low": round(v[0.1]), "high": round(v[0.9]),
                           "pess": round(v[0.2]),
                           "expectedSoFar": round(v[0.5] * exp_m), "pessSoFar": round(v[0.2] * exp_m),
                           "revised": round(rev) if rev is not None else None}
        if "6" not in fcs:
            continue
        got = sum(o.months)
        f6 = fcs["6"]
        dev = (got / f6["expectedSoFar"] - 1) if f6["expectedSoFar"] > 0 else None
        out.append({**b.public(), "months": [{"month": M.ms(b.launch + j), "label": M.month_name(b.launch + j),
                                               "units": round(q)} for j, q in enumerate(o.months)],
                    "actual": round(got), "observed": len(o.months), "forecast": fcs, "deviation": dev,
                    "alert": got < f6["pessSoFar"]})
    return sorted(out, key=lambda x: (x["deviation"] if x["deviation"] is not None else 0))


def serialize(eng: Engine) -> dict:
    """Anlık tahmin uçlarının veri kümesi (ham satış satırları olmadan; yalnız lansman sonuçları)."""
    ds = eng.ds
    return {
        "end": ds.end,
        "books": [[b.code, b.name, b.publisher, b.library, b.series, b.authors_text, b.audience, b.genre_text, b.pages,
                   b.price, b.first_pub, b.status, b.active, b.target, b.launch, b.valid_launch] for b in ds.books.values()],
        "outcomes": {c: [o.months, o.channels, round(o.net, 2), round(o.listv, 2)] for c, o in ds.outcomes.items()},
        "portfolio": {str(k): v for k, v in ds.portfolio.items()},
        "emsal": ds.emsal,
        "priceMedian": {str(k): v for k, v in ds.price_median.items()},
        "level": {str(k): v for k, v in (eng.level or {}).items()},
        "calib": eng.calib, "steps": eng.steps, "params": eng.p, "ruleStats": eng.rule_stats,
        "sold": sorted(c for c, s in ds.sales.items() if sum(v for v in s.values() if v > 0) > 0),
    }


def engine_from(model: dict) -> Engine:
    books = {}
    for r in model["books"]:
        b = M.Book(code=r[0], name=r[1], publisher=r[2], library=r[3], series=r[4], authors_text=r[5], audience=r[6],
                   genre_text=r[7], pages=r[8], price=r[9], first_pub=r[10], status=r[11], active=r[12], target=r[13]).finish()
        b.launch, b.valid_launch = r[14], r[15]
        books[b.code] = b
    sold = set(model.get("sold") or [])
    ds = M.Dataset(books=books, sales={c: {0: 1.0} for c in sold}, portfolio={int(k): v for k, v in model["portfolio"].items()},
                   end=int(model["end"]), emsal=model["emsal"])
    ds.outcomes = {c: M.Outcome(months=v[0], channels=v[1], net=v[2], listv=v[3]) for c, v in model["outcomes"].items()}
    ds.price_median = {int(k): v for k, v in model["priceMedian"].items()}
    ds.by_launch = sorted(ds.outcomes, key=lambda c: books[c].launch)
    level = {int(k): v for k, v in (model.get("level") or {}).items()} or None
    eng = Engine(ds, level, model["calib"], model["steps"], model.get("params"))
    eng.rule_stats = model.get("ruleStats") or {}
    return eng


def save_model(model: dict) -> dict:
    """Veri kümesini rapor önbelleğinin yanına yazar (atomik); özet rapora yalnız damgası girer."""
    from semantic_bridge.management import _cache_dir, _save
    path = _cache_dir() / MODEL_FILE
    _save(path, model)
    return {"file": MODEL_FILE, "bytes": path.stat().st_size}


def build(run: Callable[[str, dict | None], dict], today: date | None = None,
          post: Callable[[dict], dict] = zeki_tahmin.post_batch,
          save: Callable[[dict], dict] = save_model) -> dict:
    today = today or date.today()
    res: dict[str, dict] = {}

    def rows(source_id: str, params: dict | None = None) -> list[dict]:
        res[source_id] = run(source_id, params)
        return res[source_id]["records"]

    kitaplar = rows("crm_kitaplar")
    emsal = rows("crm_emsal")
    baski = rows("crm_baski")
    son = rows("logo_son_fatura")
    son_fatura = _day(son[0]["son_fatura"]) if son else None
    end = zeki_tahmin.last_full_month(son_fatura, today)
    sales: list[dict] = []
    n_rows = db_ms = 0
    last_sql = warning = None
    for y in range(FIRST_YEAR, end // 12 + 1):
        r_ = run("logo_aylik_kanal", {"yil": y})
        sales += r_["records"]
        n_rows += len(r_["records"]); db_ms += r_.get("dbMs") or 0
        last_sql, warning = r_.get("sql"), warning or r_.get("warning")
    res["logo_aylik_kanal"] = {"rowCount": n_rows, "dbMs": db_ms, "sql": last_sql, "warning": warning}

    ds = M.build_dataset(kitaplar, emsal, sales, end)
    del sales
    steps = print_steps(baski)
    their = {str(r["stok_kodu"]).strip(): int(r["son_baski_adet"]) for r in baski
             if (r.get("baski_sayisi") or 0) == 1 and M.num(r.get("son_baski_adet"))}
    level = None
    level_note = None
    if any(M.params_for(h).get("beta") for h in HORIZONS):
        try:
            level = _level(ds, post, [end], 36)[end]
        except RuntimeError as e:  # tahmin servisi yoksa pazar düzeltmesi olmadan sürer; ekran söyler
            level_note = str(e)
    eng = Engine(ds, level, {}, steps, M.PARAMS)
    eng.calib = {str(h): calibrate(eng, h) for h in HORIZONS}
    bt = {str(h): backtest(eng, h) for h in HORIZONS}
    bt["print"] = print_rules_backtest(eng, their)
    eng.rule_stats = {r["id"]: {k: r.get(k) for k in ("n", "stockout6", "stockout12", "leftover12")} for r in bt["print"]["rules"]}
    up = [r for r in (summary_row(eng, b, L) for b, L in upcoming_books(ds, today)) if r]
    return {
        "asOf": today.isoformat(),
        "dataEnd": son_fatura.isoformat() if son_fatura else None,
        "lastFullMonth": M.ms(end),
        "counts": {"books": len(ds.books), "launches": len(ds.outcomes),
                   "withEmsal": sum(1 for c in ds.outcomes if ds.emsal.get(c))},
        "levelNote": level_note,
        "backtest": bt,
        "upcoming": up,
        "tracking": tracking(eng),
        "model": save(serialize(eng)),
        "sourceStats": {sid: {"rows": r.get("rowCount", len(r.get("records") or [])), "dbMs": r.get("dbMs"),
                              "sql": r.get("sql"), "warning": r.get("warning")} for sid, r in res.items()},
        "warnings": sorted({r["warning"] for r in res.values() if r.get("warning")}),
    }
