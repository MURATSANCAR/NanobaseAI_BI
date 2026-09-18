"""gold-parts/part-*.json dosyalarını answers-set100.json ile birleştirir.

    merge-gold-parts.py [--apply]

Yalnız geçerli girişleri alır: `expect` dolu, `reference_sql` ya da `checks` var, soru metni sette aynı. `expect: null`
(tanımı/verisi belirsiz) girişler birleştirilmez, listelenir. Ana dosyada zaten olan soru ezilmez. `--apply` olmadan
yalnız ne yapacağını söyler.
"""
import glob, json, sys
from pathlib import Path

root = Path(__file__).parent
gold = json.loads((root / "answers-set100.json").read_text(encoding="utf-8"))
questions = [json.loads(l) for l in (root / "set100.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
holdout = set(json.loads((root / "set100-split.json").read_text(encoding="utf-8"))["holdout"])
have = {c["n"] for c in gold["cases"]}
added, skipped = [], []
for path in sorted(glob.glob(str(root / "gold-parts" / "part-*.json"))):
    try:
        cases = json.loads(Path(path).read_text(encoding="utf-8"))["cases"]
    except Exception as ex:  # noqa: BLE001
        skipped.append(f"{Path(path).name}: okunamadı ({ex})")
        continue
    for c in cases:
        n = c.get("n")
        if not isinstance(n, int) or not 1 <= n <= len(questions):
            skipped.append(f"{Path(path).name}: geçersiz n={n}")
            continue
        q = questions[n - 1]
        c.update(id=q["id"], soru=q["soru"], kaynak=q["kaynak"], holdout=q["id"] in holdout)   # kimlik setten gelir
        if n in have:
            skipped.append(f"Q{n}: ana dosyada var, ezilmedi")
        elif not c.get("expect"):
            skipped.append(f"Q{n}: belirsiz — {str(c.get('note'))[:140]}")
        elif c.get("expect") in ("answer", ["answer"]) and not c.get("checks"):
            skipped.append(f"Q{n}: cevap bekleniyor ama kontrol yok")
        else:
            c["verified"] = bool(c.get("verified"))
            gold["cases"].append(c)
            have.add(n)
            added.append(n)
gold["cases"].sort(key=lambda c: c["n"])
print(f"eklenecek {len(added)}: {sorted(added)}")
print(f"doğrulanmış (verified) {sum(1 for c in gold['cases'] if c.get('verified'))} / toplam {len(gold['cases'])}")
for line in skipped:
    print("  atlandı:", line)
if "--apply" in sys.argv:
    (root / "answers-set100.json").write_text(json.dumps(gold, ensure_ascii=False, indent=1), encoding="utf-8")
    print("yazıldı")
