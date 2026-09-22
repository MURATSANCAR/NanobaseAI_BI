"""graph_intent_measure.py çıktısını özetler: grup başına kararlılık ve isabet, yanlış sınıflananlar."""
import collections, json, os, sys

path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OUT", "/tmp/graph-intent/results.jsonl")
by = collections.defaultdict(list)
for line in open(path, encoding="utf-8"):
    r = json.loads(line); by[r["question"]].append(r)
groups = collections.defaultdict(lambda: [0, 0, 0]); wrong = []
for q, rs in by.items():
    grp, exp = rs[0]["group"], rs[0]["expected"]
    stable = len({r["decision"] for r in rs}) == 1
    ok = all(r["decision"] == exp for r in rs)
    g = groups[grp]; g[0] += 1; g[1] += stable; g[2] += ok
    if not ok: wrong.append((q, exp, [r["decision"] for r in rs]))
for k, (n, st, ok) in sorted(groups.items()):
    print(f"{k}: soru {n}  kararlı {st}/{n}  isabet {ok}/{n}")
for w in wrong: print("yanlış:", w)
