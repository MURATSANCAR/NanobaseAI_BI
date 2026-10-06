"""Tanı: yazar geçmişi olan kitaplarda yalnız yazar ortancası mı, emsal tahmini mi daha isabetli? n ve dağınıklığa göre."""
import sys, json, math
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_bridge.management import ilk_baski as R
M = R.M
H = int(sys.argv[1]); GAP = 2
m = json.load(open("/data/nanobaseai/bi/var/management-reports/ilk-baski.model.json"))
eng = R.engine_from(m); ds = eng.ds
rows = []
for c in R.targets(ds, M.mi(2019, 1), ds.end, H):
    b = ds.books[c]
    act = ds.outcomes[c].total(H)
    if not act or act <= 0 or not b.authors: continue
    cut = b.launch - GAP
    hist = [ds.outcomes[x].total(H) for x in eng.pool(cut, H) if x != c and ds.books[x].authors & b.authors]
    if not hist: continue
    fc = eng.raw(b, b.launch, cut, H)
    if not fc: continue
    lg = [math.log(max(v, 1)) for v in hist]
    mu = sum(lg) / len(lg); sd = (sum((x - mu) ** 2 for x in lg) / len(lg)) ** 0.5
    am = math.exp(M._median(lg)) if False else M._median(hist)
    rows.append((c, b.launch, len(hist), sd, act, fc.base, max(am, 1), mu))
def md(v): v = sorted(v); return round(v[len(v)//2], 3) if v else None
def show(name, sub):
    if not sub: return
    eb = [abs(math.log(a / p)) for *_, a, p, am, mu in sub]
    ea = [abs(math.log(a / am)) for *_, a, p, am, mu in sub]
    eh = [abs(math.log(a / math.exp((math.log(p) + math.log(am)) / 2))) for *_, a, p, am, mu in sub]
    yb = [math.log(a / p) for *_, a, p, am, mu in sub]; ya = [math.log(a / am) for *_, a, p, am, mu in sub]
    print(f"{name:28s} n={len(sub):4d} | emsal MdALE {md(eb)} yan {math.exp(md(yb)):.2f} | yazar ortancası MdALE {md(ea)} yan {math.exp(md(ya)):.2f} | yarı yarıya {md(eh)}")
print("UFUK", H, "toplam", len(rows))
show("hepsi", rows)
for lo, hi in ((1, 1), (2, 2), (3, 5), (6, 999)):
    show(f"önceki kitap {lo}-{hi}", [r for r in rows if lo <= r[2] <= hi])
for lo, hi in ((0, 0.35), (0.35, 0.7), (0.7, 99)):
    show(f"≥2 kitap, sd {lo}-{hi}", [r for r in rows if r[2] >= 2 and lo <= r[3] < hi])
for thr in (5000, 20000):
    show(f"yazar ortancası ≥{thr}", [r for r in rows if r[6] >= thr])
    show(f"yazar ortancası ≥{thr}, ≥3 kitap", [r for r in rows if r[6] >= thr and r[2] >= 3])
show("yazar ortancası <2000", [r for r in rows if r[6] < 2000])
