"""M10 geçmiş sınama (ön çalışma): ayar seçimi 2021-07…2023-12 lansmanları, sınama 2024-01+ lansmanları.
Koşturma: python bt.py [fit]  (data.pkl gerekir; tahmin servisi 127.0.0.1:8793)"""
import json
import math
import pickle
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta

sys.path.insert(0, "/tmp/claude-m10/stage")
from semantic_bridge.management import ilk_baski_model as M  # noqa: E402

d = pickle.load(open("/tmp/claude-m10/data.pkl", "rb"))
son = d["logo_son_fatura"]["records"][0]["son_fatura"]
son = son if isinstance(son, (date, datetime)) else datetime.fromisoformat(str(son)[:19])
son = son.date() if isinstance(son, datetime) else son
end = M.mi(son.year, son.month) - (0 if (son + timedelta(days=1)).month != son.month else 1)
t0 = time.time()
ds = M.build_dataset(d["crm_kitaplar"]["records"], d["crm_emsal"]["records"], d["logo_aylik_kanal"]["records"], end)
print("veri", len(ds.books), "kitap,", len(ds.outcomes), "geçerli lansman, son tam ay", M.ms(end), f"{time.time()-t0:.1f} sn")
by_year = defaultdict(int)
for c in ds.outcomes:
    by_year[ds.books[c].launch // 12] += 1
print("lansman/yıl", dict(sorted(by_year.items())))
em_cov = sum(1 for c in ds.outcomes if ds.emsal.get(c)) / max(1, len(ds.outcomes))
print("emsal girilmiş lansman oranı", round(em_cov, 3))

GAP = 2  # tahmin lansmandan 2 ay önce yapılır (kesim = L-2, o aya kadar veri)
H = int(sys.argv[2]) if len(sys.argv) > 2 else 6


def targets(lo, hi):
    return [c for c in ds.by_launch if lo <= ds.books[c].launch <= hi and ds.books[c].launch + H - 1 <= end and (ds.outcomes[c].total(H) or 0) > 0]


TRAIN = targets(M.mi(2021, 7), M.mi(2023, 12))
TEST = targets(M.mi(2024, 1), end - H + 1)
print("seçim", len(TRAIN), "sınama", len(TEST), "ufuk", H)

# Portföy düzeyi: her kesim için ZEKİ AI tahmin modelinden (yalnız o güne kadarki veriyle) gelecek aylar.
cut_all = sorted({ds.books[c].launch - GAP for c in TRAIN + TEST})
p0 = min(ds.portfolio)
series = [{"id": str(c), "start": M.ms(p0), "values": [ds.portfolio.get(i, 0.0) for i in range(p0, c + 1)]} for c in cut_all]
t0 = time.time()
req = urllib.request.Request("http://127.0.0.1:8793/forecast/batch", method="POST",
                             data=json.dumps({"horizon": GAP + H + 1, "series": series, "calendar": True,
                                              "calendar_peak_months": [9, 10], "engine": "timesfm3"}).encode(),
                             headers={"Content-Type": "application/json"})
out = json.loads(urllib.request.urlopen(req, timeout=1800).read())
LEVEL = {}
for r in out["results"]:
    c = int(r["id"])
    lv = {i: v for i, v in ds.portfolio.items() if i <= c}
    for j, q in enumerate(r["quantiles"]):
        lv[c + 1 + j] = q[4]
    LEVEL[c] = lv
print("portföy tahmini", len(LEVEL), "kesim", f"{time.time()-t0:.0f} sn")
# portföy tahmininin kendi hatası (h ay toplamı)
pe = []
for c, lv in LEVEL.items():
    L = c + GAP
    if L + H - 1 <= end:
        f = sum(lv[L + j] for j in range(H)); a = sum(ds.portfolio[L + j] for j in range(H))
        pe.append(abs(f - a) / a)
print("portföy 6 ay pencere hatası ortanca", round(sorted(pe)[len(pe)//2], 3) if pe else None)

POOLS = {}


def pool(cut):
    if cut not in POOLS:
        POOLS[cut] = M.pool_for(ds, cut, H)
    return POOLS[cut]


def run(cands, p, method="model"):
    res = []
    for c in cands:
        b = ds.books[c]
        L = b.launch
        cut = L - GAP
        act = ds.outcomes[c].total(H)
        pl = pool(cut)
        if method == "naive":  # son 12 ayda çıkan bütün kitapların ortancası
            v = [ds.outcomes[x].total(H) for x in pl if ds.books[x].launch >= cut - H - 11]
            pred, tier = M._median(v), "-"
        elif method == "emsal":
            em = [x for x in ds.emsal.get(c, []) if x in set(pl)]
            if em:
                pred, tier = M._median([ds.outcomes[x].total(H) for x in em]), "emsal"
            else:
                v = [ds.outcomes[x].total(H) for x in pl if ds.books[x].launch >= cut - H - 11]
                pred, tier = M._median(v), "yok"
        else:
            fc = M.forecast(ds, b, L, cut, H, p, level=LEVEL.get(cut), pool=pl)
            pred, tier = fc.base, M.confidence_tier(fc)
        res.append((c, max(pred, 1.0), act, tier))
    return res


def metrics(res):
    le = sorted(abs(math.log(a / p)) for _, p, a, _ in res)
    ape = sorted(abs(p - a) / a for _, p, a, _ in res)
    wape = sum(abs(p - a) for _, p, a, _ in res) / sum(a for _, p, a, _ in res)
    bias = sorted(math.log(a / p) for _, p, a, _ in res)
    n = len(res)
    return {"n": n, "MdALE": round(le[n // 2], 3), "MdAPE": round(ape[n // 2], 3), "WAPE": round(wape, 3),
            "±25%": round(sum(1 for x in le if x <= math.log(1.25)) / n, 3),
            "±50%": round(sum(1 for x in le if x <= math.log(1.5)) / n, 3),
            "×2 içinde": round(sum(1 for x in le if x <= math.log(2)) / n, 3),
            "yan(ortanca a/p)": round(math.exp(bias[n // 2]), 3)}


def score(p):
    return metrics(run(TRAIN, p))["MdALE"]


P = dict(M.PARAMS)
if len(sys.argv) > 1 and sys.argv[1] == "fit":
    grid = {"w_emsal": [0, 1, 3, 6], "w_author": [0, 1, 2, 4], "w_series": [0, 0.5, 1, 2], "w_library": [0, 0.5, 1, 2],
            "w_publisher": [0, 0.5, 1], "w_audience": [0, 0.5, 1], "w_genre": [0, 0.5, 1], "w_price": [0, 0.5, 1, 2],
            "w_pages": [0, 0.5, 1], "tau_years": [1, 2, 3, 6, 20], "k": [5, 10, 15, 25, 40], "beta": [0, 0.5, 1]}
    best = score(P)
    print("başlangıç", best, flush=True)
    for rnd in range(2):
        changed = False
        for key, vals in grid.items():
            for v in vals:
                if v == P[key]:
                    continue
                q = dict(P); q[key] = v
                s = score(q)
                if s < best - 1e-4:
                    best, P, changed = s, q, True
                    print(f"  {key}={v} → {s}", flush=True)
        print("tur", rnd, best, P, flush=True)
        if not changed:
            break
    json.dump(P, open(f"/tmp/claude-m10/params_h{H}.json", "w"))

print("AYAR", P)
for name, cands in (("SEÇİM", TRAIN), ("SINAMA", TEST)):
    for meth in ("naive", "emsal", "model"):
        print(name, meth, metrics(run(cands, P, meth)))

# Kalibrasyon: seçim döneminin log(a/p) dağılımı güven düzeyine göre → sınamada kapsama
tr = run(TRAIN, P)
te = run(TEST, P)
qs = {}
for tier in ("yuksek", "orta", "dusuk"):
    r = sorted(math.log(a / p) for _, p, a, t in tr if t == tier)
    if len(r) < 20:
        r = sorted(math.log(a / p) for _, p, a, t in tr)
    qs[tier] = {q: r[min(len(r) - 1, int(q * len(r)))] for q in (0.1, 0.2, 0.5, 0.8, 0.9)}
print("kalibrasyon", {k: {q: round(math.exp(v), 2) for q, v in d_.items()} for k, d_ in qs.items()})
for tier in ("yuksek", "orta", "dusuk", "hepsi"):
    rows = [x for x in te if tier == "hepsi" or x[3] == tier]
    if not rows:
        continue
    cov = sum(1 for _, p, a, t in rows if p * math.exp(qs[t][0.1]) <= a <= p * math.exp(qs[t][0.9])) / len(rows)
    so = {q: round(sum(1 for _, p, a, t in rows if a > p * math.exp(qs[t][q])) / len(rows), 3) for q in (0.2, 0.5, 0.8)}
    print("sınama", tier, len(rows), "p10–p90 kapsama", round(cov, 3), "tükenme oranı (senaryo adedi basılsa)", so,
          metrics([(c, p * math.exp(qs[t][0.5]), a, t) for c, p, a, t in rows]))
# Aşama 2: gerçekleşen ilk m ayla revize
for m in (1, 2, 3):
    rr = []
    for c in TEST:
        b = ds.books[c]; L = b.launch
        fc = M.forecast(ds, b, L, L - GAP, H, P, level=LEVEL.get(L - GAP), pool=pool(L - GAP))
        act = ds.outcomes[c].months[:m]
        v = M.revise(ds, fc, act, H)
        if v:
            rr.append((c, v, ds.outcomes[c].total(H), "-"))
    print("revize m=", m, metrics(rr))
json.dump({"qs": {k: {str(q): v for q, v in d_.items()} for k, d_ in qs.items()}, "P": P}, open(f"/tmp/claude-m10/calib_h{H}.json", "w"))
