"""TimesFM 3.0 ayar denemeleri + Power BI kararıyla karşılaştırma (Baskı Tekrar havuzu, Logo + CRM)."""
import json, math, os, sys, time
import numpy as np
import torch
from timesfm3 import ModelConfig, TimesFM3Evaluator
torch.set_num_threads(24)
MI = lambda y, m: y * 12 + m - 1
END = MI(2026, 7)
monthly = json.load(open("/tmp/fc/monthly.json"))
stock = json.load(open("/tmp/fc/stock.json"))
snap = json.load(open("/data/nanobaseai/bi/var/management-reports/baski-oneri.json"))
v = [x for x in snap["data"]["views"] if x["id"] == "tekrar"][0]
ix = {c["key"]: i for i, c in enumerate(v["columns"])}
pool = [str(r[ix["stok_kodu"]]).strip() for r in v["rows"]]
# portföy toplamı (bütün kodlar): yalnız geçmişte bilinen büyüme sinyali
port = np.zeros(END + 1, np.float64)
for d in monthly.values():
    for k, q in d.items():
        i = MI(int(k[:4]), int(k[5:]))
        if i <= END: port[i] += q
def ser(code):
    d = monthly.get(code, {}); idx = [MI(int(k[:4]), int(k[5:])) for k in d]
    if not idx: return None, None
    s = min(idx); a = np.zeros(END - s + 1, np.float32)
    for k, q in d.items():
        i = MI(int(k[:4]), int(k[5:]))
        if s <= i <= END: a[i - s] = q
    return a, s
def pbi_speed(h):
    a = np.concatenate([np.zeros(max(0, 12 - len(h)), np.float32), h])[-12:]
    return (0.5*a[-3:].sum()/3 + 0.1*a[-6:-3].sum()/3 + 0.05*a[-9:-6].sum()/3 + 0.2*a[-12:-9].sum()/3
            + 0.05*a[-6:].sum()/6 + 0.05*a[-12:-6].sum()/6 + 0.05*a.sum()/12)
def season(start, n):
    m = (np.arange(start, start + n) % 12) + 1
    return np.stack([np.sin(2*np.pi*m/12), np.cos(2*np.pi*m/12), np.isin(m, (9, 10)).astype(float)]).astype(np.float32)
def port_cov(start, n):
    p = np.log1p(np.clip(port[start:start + n], 0, None)); return ((p - p.mean()) / (p.std() + 1e-6)).astype(np.float32)[None, :]

model = TimesFM3Evaluator(ModelConfig(checkpoint_path="/data/nanobaseai/bi/models/timesfm-3.0-pytorch", per_core_batch_size=64, device="cpu"))
CUTS = [("2024-07", MI(2024, 7), 12, "2024-07"), ("2025-01", MI(2025, 1), 6, "2025-01"),
        ("2025-07", MI(2025, 7), 12, "2025-07"), ("2026-01", MI(2026, 1), 6, "2026-01")]
CONFIGS = ["tfm_temel", "tfm_simetrik", "tfm_mevsim", "tfm_mevsim_portfoy", "tfm_log"]
res = {}
for key, cut, H, skey in CUTS:
    codes, ctx, starts, act, pbi, snv, stk = [], [], [], [], [], [], []
    for c in pool:
        a, s = ser(c)
        if a is None: continue
        p = cut - s
        if p < 12 or c not in stock[skey]: continue
        h, f = a[:p + 1], a[p + 1:p + 1 + H]
        if len(f) < H: continue
        codes.append(c); ctx.append(h); starts.append(s); act.append(f); stk.append(stock[skey][c]["stok"])
        pbi.append(np.full(H, pbi_speed(h), np.float32)); snv.append(np.resize(h[-12:], 12)[:H] if H <= 12 else np.resize(h[-12:], H))
    out = {"codes": codes, "H": H, "act": np.stack(act).tolist(), "pbi": np.stack(pbi).tolist(), "snv": np.stack(snv).tolist(), "stok": stk, "tfm": {}}
    for cfg in CONFIGS:
        t = time.monotonic()
        kw = dict(horizon=H, return_quantiles=True, make_positive=True, sort_quantiles=True,
                  use_symmetric_averaging=(cfg != "tfm_temel"))
        C = ctx
        if cfg == "tfm_log":
            C = [np.log1p(np.clip(x, 0, None)).astype(np.float32) for x in ctx]
        if cfg in ("tfm_mevsim", "tfm_mevsim_portfoy"):
            kw["past_future_covariates"] = [season(s, len(x) + H) for s, x in zip(starts, ctx)]
        if cfg == "tfm_mevsim_portfoy":
            kw["past_only_covariates"] = [port_cov(s, len(x)) for s, x in zip(starts, ctx)]
        preds = list(model.predict_batch(C, **kw))
        q = np.stack([np.asarray(p.quantiles, np.float64).reshape(-1, 9)[:H] for p in preds])
        if cfg == "tfm_log": q = np.expm1(q)
        out["tfm"][cfg] = q.tolist()
        print(f"{key} H{H} {len(codes)} kitap {cfg}: {time.monotonic()-t:.0f} sn", flush=True)
    res[key] = out
json.dump(res, open("/tmp/fc/exp.json", "w"))
print("BITTI", flush=True)
