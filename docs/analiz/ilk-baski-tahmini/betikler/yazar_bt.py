"""Yazar geçmişi deneyi: A = yazarın önceki kitaplarının ilk h ayı ile harman, B = yazarın önceki kitaplarının
tahmin artığı (gerçek/tahmin) ile düzeltme. Seçim 2021-07..2023-12, sınama 2024+. Veri: canlı model.json."""
import sys, json, math, time
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_bridge.management import ilk_baski as R
M = R.M
H = int(sys.argv[1]) if len(sys.argv) > 1 else 6
m = json.load(open("/data/nanobaseai/bi/var/management-reports/ilk-baski.model.json"))
eng = R.engine_from(m); ds = eng.ds
P = M.params_for(H)
GAP = 2
t0 = time.time()
BASE = {}   # kod -> ham tahmin (kendi lansmanı - 2)
for c in ds.by_launch:
    b = ds.books[c]
    if b.launch < M.mi(2016, 1): continue
    fc = eng.raw(b, b.launch, b.launch - GAP, H)
    if fc and fc.base > 0: BASE[c] = fc.base
print("ham tahminler", len(BASE), f"{time.time()-t0:.0f} sn", flush=True)

HC = {}
def history(c, cut):
    if c in HC: return HC[c]
    HC[c] = _history(c, cut); return HC[c]

def _history(c, cut):
    """Yazarın kesimde ilk H ayı tam gözlenmiş önceki kitapları: (kod, satış, yaş yıl)."""
    b = ds.books[c]
    if not b.authors: return []
    out = []
    for x in eng.pool(cut, H):
        if x == c: continue
        a = ds.books[x]
        if a.authors & b.authors:
            out.append((x, ds.outcomes[x].total(H), max(0, b.launch - a.launch) / 12))
    return out

def wmed(vals, wts): return M.wquantile(vals, wts, 0.5)

def predict(c, cfg):
    b = ds.books[c]; base = BASE[c]
    if cfg["mode"] == "none": return base, 0
    hist = history(c, b.launch - GAP)
    if not hist: return base, 0
    w = [math.exp(-age / cfg["tau"]) for _, _, age in hist]
    n = sum(w)
    a = cfg["amax"] * n / (n + cfg["lam"])
    if cfg["mode"] == "A":
        v = wmed([math.log(max(s, 1)) for _, s, _ in hist], w)
        return math.exp((1 - a) * math.log(base) + a * v), len(hist)
    if cfg["mode"] in ("CA", "CB"):
        if cfg["mode"] == "CA":
            r = [math.log(max(sv, 1)) for _, sv, _ in hist]; ww = w
        else:
            r, ww = [], []
            for (x, sv, _), wi in zip(hist, w):
                if x in BASE: r.append(math.log(max(sv, 1) / BASE[x])); ww.append(wi)
        if not r: return base, 0
        n = sum(ww); mu = sum(a_ * b_ for a_, b_ in zip(r, ww)) / n
        var = sum(b_ * (a_ - mu) ** 2 for a_, b_ in zip(r, ww)) / n
        var = (n * var + cfg["nu"] * cfg["s0"] ** 2) / (n + cfg["nu"])
        a = cfg["amax"] * n / (n + cfg["lam"] * var)
        if cfg["mode"] == "CA":
            return math.exp((1 - a) * math.log(base) + a * mu), len(r)
        return base * math.exp(a * mu), len(r)
    # B: artık
    r, ww = [], []
    for (x, s, _), wi in zip(hist, w):
        if x in BASE: r.append(math.log(max(s, 1) / BASE[x])); ww.append(wi)
    if not r: return base, 0
    n = sum(ww); a = cfg["amax"] * n / (n + cfg["lam"])
    return base * math.exp(a * wmed(r, ww)), len(r)

def tg(lo, hi): return [c for c in R.targets(ds, lo, hi, H) if c in BASE and (ds.outcomes[c].total(H) or 0) > 0]
TRAIN = tg(M.mi(int(sys.argv[2]) if len(sys.argv) > 2 else 2021, 1 if len(sys.argv) > 2 else 7), M.mi(2023, 12)); TEST = tg(M.mi(2024, 1), ds.end)
print("seçim", len(TRAIN), "sınama", len(TEST), flush=True)

def met(rows):
    n = len(rows)
    if not n: return {}
    le = sorted(abs(math.log(a / p)) for p, a in rows); ape = sorted(abs(p - a) / a for p, a in rows)
    lr = sorted(math.log(a / p) for p, a in rows)
    return {"n": n, "MdALE": round(le[n//2], 3), "MdAPE": round(ape[n//2], 3),
            "WAPE": round(sum(abs(p-a) for p, a in rows) / sum(a for _, a in rows), 3),
            "±50%": round(sum(1 for x in le if x <= math.log(1.5)) / n, 3),
            "×2": round(sum(1 for x in le if x <= math.log(2)) / n, 3), "yan": round(math.exp(lr[n//2]), 3),
            "MeanALE": round(sum(le) / n, 3), "×3 dışı": round(sum(1 for x in le if x > math.log(3)) / n, 3)}

def run(cands, cfg):
    allr, hr, nr = [], [], []
    for c in cands:
        p, k = predict(c, cfg); a = ds.outcomes[c].total(H)
        allr.append((p, a)); (hr if k else nr).append((p, a))
    return allr, hr, nr

grid = []
for mode in ("A", "B"):
    for lam in (0.5, 1, 2, 4, 8):
        for amax in (0.25, 0.5, 0.75, 1.0):
            for tau in (2, 4, 10):
                grid.append({"mode": mode, "lam": lam, "amax": amax, "tau": tau})
OBJ = sys.argv[3] if len(sys.argv) > 3 else "md"
grid = [g for g in grid if 0]
for mode in ("CA", "CB"):
    for lam in (1, 2, 4, 8, 16, 32):
        for s0 in (0.3, 0.5, 0.8):
            for nu in (1, 3):
                for tau in (2, 4, 10):
                    for amax in (0.75, 0.9, 1.0):
                        grid.append({"mode": mode, "lam": lam, "s0": s0, "nu": nu, "tau": tau, "amax": amax})
if len(sys.argv) > 4:
    grid = [json.loads(sys.argv[4])]
res = []
for cfg in grid:
    rr = run(TRAIN, cfg)[0]
    s = met(rr)["MdALE"] if OBJ == "md" else sum(abs(math.log(a / p)) for p, a in rr) / len(rr)
    res.append((s, cfg))
base_s = met(run(TRAIN, {"mode": "none"})[0])["MdALE"]
print("seçim MdALE bugünkü", base_s)
for mode in ("CA", "CB"):
    best = min((r for r in res if r[1]["mode"] == mode), key=lambda r: r[0])
    print("en iyi", mode, best, flush=True)
for name, cfg in [("bugünkü", {"mode": "none"})] + [(f"en iyi {md}", min((r for r in res if r[1]["mode"] == md), key=lambda r: r[0])[1]) for md in ("CA", "CB")]:
    for per, cands in (("SEÇİM", TRAIN), ("SINAMA", TEST)):
        a, h, n = run(cands, cfg)
        print(f"{name:10s} {per:7s} hepsi {met(a)}")
        print(f"{'':10s} {'':7s} yazar geçmişli {met(h)}")
        st = [(predict(c, cfg)[0], ds.outcomes[c].total(H)) for c in cands
              if (lambda hh: len(hh) >= 3 and M._median([x[1] for x in hh]) >= 20000)(history(c, ds.books[c].launch - GAP))]
        print(f"{'':10s} {'':7s} çok satan yazar (≥3 kitap, ortanca ≥20 bin) {met(st)}")
# Örnek: Babası Kılıklı (Mert Arık)
c = "15201.01.6783"
if c in BASE:
    for name, cfg in [("bugünkü", {"mode": "none"})] + [(f"en iyi {md}", min((r for r in res if r[1]["mode"] == md), key=lambda r: r[0])[1]) for md in ("CA", "CB")]:
        print("Babası Kılıklı", name, round(predict(c, cfg)[0]), "gerçek", ds.outcomes[c].total(H))
