"""source-reading.py çıktılarını karşılaştırır: source-reading-report.py <kök-dizin> <önce> <sonra>
(kök/<ad>/*.jsonl). Etiketle okunan kaynağın uyumu, Logo sorusunu CRM'e taşıyan kelimeler, bedel."""
import json, glob, collections, sys
ROOT = sys.argv[1]
def load(d):
    out = {}
    for f in glob.glob(f"{ROOT}/{d}/*.jsonl"):
        for l in open(f):
            r = json.loads(l); out[r["id"]] = r
    return out
def srcs(r): return frozenset(s["src"] for s in r.get("slots") or [])
def verdict(r):
    want = {"logo": {"logo"}, "crm": {"crm"}, "ikisi": {"logo", "crm"}}.get(r["kaynak"])
    got = set(srcs(r))
    if not got: return "boş"
    return "uyuyor" if got == want else "uymuyor"
A, V = sys.argv[2], sys.argv[3]
on, off = load(A), load(V)
on = {k: v for k, v in on.items() if k in off}
print("soru:", len(on), len(off), "hata:", sum(1 for r in on.values() if "error" in r))
for name, d in ((A, on), (V, off)):
    t = collections.Counter((r["kaynak"], verdict(r)) for r in d.values() if "error" not in r)
    print("==", name)
    for k in ("logo", "crm", "ikisi"):
        print("  ", k, {v: t[(k, v)] for v in ("uyuyor", "uymuyor", "boş")})
# Logo sorusu CRM okuyor: taşıyan slotlar
bad = [r for r in on.values() if r.get("kaynak") == "logo" and "crm" in srcs(r)]
auto = [r for r in bad if any(s["src"] == "crm" and s["autoTerm"] for s in r["slots"])]
autoc = [r for r in bad if any(s["src"] == "crm" and (s["autoTerm"] or s["autoConcept"]) for s in r["slots"])]
print("Logo sorusu CRM slotu taşıyor:", len(bad), "| makine onaylı kelimeyle:", len(auto), "| makine onaylı kavramla:", len(autoc))
fixed = [r for r in bad if "crm" not in srcs(off[r["id"]])]
print("gizleyince CRM'den kurtulan Logo sorusu:", len(fixed))
terms = collections.Counter((s["term"], s["field"], s["words"]) for r in bad for s in r["slots"] if s["src"] == "crm" and s["autoTerm"])
print("en çok Logo sorusu çeken makine kelimeleri:")
for (t, f, w), c in terms.most_common(40): print(f"   {c:3d}  {t!r} ({w} kelime) → {f}")
other = collections.Counter((s["term"], s["field"]) for r in bad for s in r["slots"] if s["src"] == "crm" and not s["autoTerm"])
print("makine kelimesi OLMAYAN CRM slotları (Logo sorularında):")
for (t, f), c in other.most_common(20): print(f"   {c:3d}  {t!r} → {f}")
# bedel: CRM sorularında gizleyince kaybolan CRM slotu
lost = [r for r in on.values() if r.get("kaynak") in ("crm", "ikisi") and "crm" in srcs(r) and "crm" not in srcs(off[r["id"]])]
print("gizleyince CRM okumasını tamamen kaybeden CRM/ikisi sorusu:", len(lost))
