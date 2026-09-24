import json, math
import numpy as np
R = json.load(open("/tmp/fc/exp.json"))
CAT = ["Risk/Acil", "Kritik", "Karar Ver", "Takip Et", "Yeterli Stok"]
def cat(t):  # Power BI eşikleri tükenme süresi (ay) üzerinden: marj = t − 1
    return 0 if t <= 1 else 1 if t <= 1.5 else 2 if t <= 2 else 3 if t <= 2.5 else 4
def deplete(path, S):
    """Stok S, aylık talep yolunda kaç ayda biter (kesirli). Bitmezse inf."""
    if S <= 0: return 0.0
    cum = 0.0
    for h, d in enumerate(path):
        d = max(float(d), 0.0)
        if cum + d >= S: return h + (S - cum) / d if d > 0 else float(h)
        cum += d
    return math.inf
def pbi_t(speed, S):
    if S <= 0: return 0.0
    return S / speed if speed > 0 else math.inf
print("## 1) TALEP DOGRULUGU — donem toplami WAPE / aylik WAPE / sapma (tum havuz)")
names = None
summary = {}
for key, d in R.items():
    A = np.array(d["act"]); H = d["H"]; n = len(A)
    M = {"Power BI hizi": np.array(d["pbi"]), "gecen yil ayni ay": np.array(d["snv"])}
    for c, q in d["tfm"].items(): M[c] = np.array(q)[:, :, 4]
    rank = np.argsort(-np.array(d["pbi"])[:, 0]); AB = np.zeros(n, bool); AB[rank[: n // 2]] = True
    print(f"\n{key} (ufuk {H} ay, {n} kitap, gercek {A.sum():,.0f} adet)")
    print(f"   {'yontem':22}{'toplam':>8}{'aylik':>8}{'sapma':>8}{'A+B top':>9}{'zirve sapma':>13}")
    for name, F in M.items():
        tot = 100*np.abs(F.sum(1)-A.sum(1)).sum()/np.abs(A.sum(1)).sum()
        mon = 100*np.abs(F-A).sum()/np.abs(A).sum()
        bias = 100*(F.sum()/A.sum()-1)
        ab = 100*np.abs(F[AB].sum(1)-A[AB].sum(1)).sum()/np.abs(A[AB].sum(1)).sum()
        start_m = int(key[5:]) % 12  # kesim ayı → ufkun ilk ayı = kesim+1
        months = [((int(key[5:]) + h) % 12) + 1 for h in range(H)]
        pk = [h for h, m in enumerate(months) if m in (9, 10)]
        peak = f"{100*(F[:, pk].sum()/A[:, pk].sum()-1):+.0f}%" if pk else "-"
        print(f"   {name:22}{tot:7.1f}%{mon:7.1f}%{bias:+7.1f}%{ab:8.1f}%{peak:>13}")
        summary.setdefault(name, []).append((tot, mon))
    for c, q in d["tfm"].items():
        Q = np.array(q); cov = ((A >= Q[:, :, 0]) & (A <= Q[:, :, 8])).mean()
        if c in ("tfm_temel", "tfm_mevsim_portfoy"): print(f"   p10-p90 kapsama {c}: %{100*cov:.0f}")
print("\n## ortalama (4 kesim): donem toplami / aylik WAPE")
for k, v in summary.items(): print(f"   {k:22} {np.mean([a for a, b in v]):5.1f}% / {np.mean([b for a, b in v]):5.1f}%")

print("\n## 2) KARAR DOGRULUGU — ayni Logo stoku, gercek tukenme ayina gore")
for key, d in R.items():
    A = np.array(d["act"]); H = d["H"]; S = np.array(d["stok"]); P = np.array(d["pbi"])[:, 0]
    best = "tfm_mevsim_portfoy" if "tfm_mevsim_portfoy" in d["tfm"] else "tfm_simetrik"
    Q = np.array(d["tfm"][best])
    tt = np.array([deplete(A[i], S[i]) for i in range(len(A))])
    tp = np.array([pbi_t(P[i], S[i]) for i in range(len(A))])
    t50 = np.array([deplete(Q[i, :, 4], S[i]) for i in range(len(A))])
    t80 = np.array([deplete(Q[i, :, 7], S[i]) for i in range(len(A))])   # p80: temkinli
    live = S > 0
    print(f"\n{key}: {len(A)} kitap, stoku olan {live.sum()} | gercekte {H} ay icinde tukenen: {np.isfinite(tt[live]).sum()} ({100*np.isfinite(tt[live]).mean():.0f}%)")
    # Power BI kategorisi (2,5 ay ufku) doğruluğu
    for name, t in (("Power BI", tp), (f"TimesFM p50 ({best})", t50)):
        ca = np.mean([cat(a) == cat(b) for a, b in zip(t[live], tt[live])])
        print(f"   {name:34} Power BI kategorisi dogru: %{100*ca:.0f}")
    # 'ufuk içinde tükenir' ikili kararı
    for lim in (2.5, 6.0):
        if lim > H: continue
        truth = tt[live] <= lim
        print(f"   '{lim:g} ay icinde tukenir' uyarisi (gercek pozitif {truth.sum()}):")
        for name, t in (("Power BI", tp), ("TimesFM p50", t50), ("TimesFM p80 (temkinli)", t80)):
            pred = t[live] <= lim
            tp_ = (pred & truth).sum(); fp = (pred & ~truth).sum(); fn = (~pred & truth).sum()
            rec = tp_/max(truth.sum(),1); prec = tp_/max(pred.sum(),1)
            print(f"      {name:24} yakalanan %{100*rec:3.0f} | uyarilarin isabeti %{100*prec:3.0f} | kacirilan {fn:4d} | bosuna uyari {fp:4d}")
    cap = lambda x: np.minimum(x, H)
    for name, t in (("Power BI", tp), ("TimesFM p50", t50)):
        print(f"   tukenme ayi ortalama mutlak hata {name}: {np.mean(np.abs(cap(t[live]) - cap(tt[live]))):.2f} ay")

print("\n## 3) CRM KIRILIMI — yayinevine gore donem toplami WAPE (2025-07, 12 ay; en buyuk 6 yayinevi)")
snap = json.load(open("/data/nanobaseai/bi/var/management-reports/baski-oneri.json"))
v = [x for x in snap["data"]["views"] if x["id"] == "tekrar"][0]
ix = {c["key"]: i for i, c in enumerate(v["columns"])}
card = {str(r[ix["stok_kodu"]]).strip(): r for r in v["rows"]}
d = R["2025-07"]; A = np.array(d["act"]); P = np.array(d["pbi"])
best = "tfm_mevsim_portfoy"; T = np.array(d["tfm"][best])[:, :, 4]; E = (P + T) / 2
yv = np.array([card[c][ix["yayinevi"]] or "(bos)" for c in d["codes"]])
vol = {y: A[yv == y].sum() for y in set(yv)}
for y in sorted(vol, key=lambda k: -vol[k])[:6]:
    m = yv == y
    w = lambda F: 100*np.abs(F[m].sum(1)-A[m].sum(1)).sum()/max(np.abs(A[m].sum(1)).sum(), 1e-9)
    print(f"   {y[:28]:28} {m.sum():5d} kitap {vol[y]:>11,.0f} adet | PBI {w(P):5.1f}% | TimesFM {w(T):5.1f}% | ortalama {w(E):5.1f}%")
