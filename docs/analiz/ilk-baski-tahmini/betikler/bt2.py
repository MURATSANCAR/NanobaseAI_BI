"""Aşama 2 deneyi: çıkıştan m ay sonra 12 aylık toplam — emsal büyümesiyle revize vs tahmin servisi (zaman serisi) vs ikisinin ortalaması."""
import json
import math
import sys
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, "/tmp/claude-m10/stage")
from semantic_bridge.management import ilk_baski_model as M  # noqa: E402
from semantic_bridge import typed_json as TJ  # noqa: E402

P12 = json.load(open("/tmp/claude-m10/params_h12.json"))
d = TJ.unpack(open("/tmp/claude-m10/data.json.z", "rb").read())
son = datetime.fromisoformat(str(d["logo_son_fatura"]["records"][0]["son_fatura"])[:19]).date()
end = M.mi(son.year, son.month) - (0 if (son + timedelta(days=1)).month != son.month else 1)
ds = M.build_dataset(d["crm_kitaplar"]["records"], d["crm_emsal"]["records"], d["logo_aylik_kanal"]["records"], end)
H = 12
T = [c for c in ds.by_launch if M.mi(2024, 1) <= ds.books[c].launch and ds.books[c].launch + H - 1 <= end and (ds.outcomes[c].total(H) or 0) > 0]
print("kitap", len(T))
p0 = min(ds.portfolio)


def mets(rows):
    le = sorted(abs(math.log(a / p)) for p, a in rows if p > 0 and a > 0)
    ape = sorted(abs(p - a) / a for p, a in rows if p > 0 and a > 0)
    n = len(ape)
    return {"n": n, "MdAPE": round(ape[n // 2], 3), "±25%": round(sum(1 for x in le if x <= math.log(1.25)) / n, 3),
            "×2": round(sum(1 for x in le if x <= math.log(2)) / n, 3)}


for m in (2, 3, 4, 6):
    series, fcs = [], {}
    for c in T:
        b = ds.books[c]
        L = b.launch
        o = ds.outcomes[c]
        fcs[c] = M.forecast(ds, b, L, L - 2, H, P12)
        series.append({"id": c, "start": M.ms(L), "values": [float(x) for x in o.months[:m]]})
    body = {"horizon": H - m, "series": series, "calendar": True, "calendar_peak_months": [9, 10],
            "shared_past": {"start": M.ms(p0), "values": [ds.portfolio.get(i, 0.0) for i in range(p0, end + 1)]},
            "engine": "timesfm3"}
    req = urllib.request.Request("http://127.0.0.1:8793/forecast/batch", method="POST", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    out = json.loads(urllib.request.urlopen(req, timeout=1800).read())
    tf = {r["id"]: sum(max(q[4], 0) for q in r["quantiles"]) for r in out["results"]}
    ra, rt, rb = [], [], []
    for c in T:
        o = ds.outcomes[c]
        got = sum(o.months[:m])
        act = o.total(H)
        an = M.revise(ds, fcs[c], o.months[:m], H)
        ts = got + tf.get(c, 0.0)
        if an:
            ra.append((an, act)); rb.append((math.sqrt(max(an, 1) * max(ts, 1)), act))
        rt.append((ts, act))
    print("m=", m, "emsal", mets(ra), "zaman serisi", mets(rt), "geometrik ort", mets(rb), flush=True)
