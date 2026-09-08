#!/usr/bin/env python3
"""Has this change made the system worse? — one command, one answer.

Every measurement behind today's work was taken by hand, and twice a change went out that a
measurement would have stopped. The worst of them renamed the catalog's entities out from under the
certified vocabulary: nothing failed, nothing logged an error, every question still returned a
number, and the share of questions reaching the right table fell from every one of them to one in
seven. It was caught because a measurement happened to be running, not because anything checked.

So the golden set is run against a recorded baseline and the comparison is the product. Reaching the
right table is the floor: an answer from the wrong table is worse than no answer, so any drop there
fails, full stop. Everything else may move — a change that spends more tokens to send fewer wrong
tables is a good trade — and is reported so a person can judge it.

    python3 tests/text2sql/quality-gate.py                 # ölç ve tabana göre karşılaştır
    python3 tests/text2sql/quality-gate.py --record        # bugünkü ölçümü yeni taban yap
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "quality-baseline-golden.json"

#: What a drop in each measure means, and how much of one is tolerated. Recall has no tolerance:
#: an answer built from the wrong table is not a worse answer, it is a wrong one.
CHECKS = [
    ("table_recall", "doğru tabloya ulaşma", 0.0, "yüksek"),
    ("fully_recalled", "hiç tablo kaçırmayan soru", 0, "yüksek"),
    ("refused", "cevaplanamayacağını söyleyen", 0, "yüksek"),
]
#: Reported, never fatal: these are trades, and which way to take them is a person's call.
WATCH = [("table_precision", "tablo isabeti", "yüksek"),
         ("mean_tables_sent", "gönderilen tablo", "düşük"),
         ("mean_tokens", "istem büyüklüğü", "düşük")]


def measure(out: Path) -> dict:
    # One run at a time. Two of these compete for the same selector model and each makes the other
    # look slow; worse, a second run started while the first is going measures a machine under a load
    # the first one caused. A lock is cheaper than explaining the numbers afterwards.
    lock = Path("/tmp/quality-gate.lock")
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        raise SystemExit(f"başka bir ölçüm çalışıyor ({lock.read_text()}); bitmesini bekleyin "
                         f"ya da takıldıysa {lock} dosyasını silin")
    try:
        r = subprocess.run([sys.executable, str(HERE / "golden-eval.py"), "--kind", "all", "--out", str(out)],
                           cwd=HERE.parent.parent, capture_output=True, text=True)
    finally:
        lock.unlink(missing_ok=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:], sep="\n")
        raise SystemExit("ölçüm çalışmadı")
    return json.loads(out.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="bu ölçümü yeni taban olarak kaydet")
    ap.add_argument("--out", default="/tmp/quality-now.json")
    args = ap.parse_args(argv)

    now = measure(Path(args.out))
    s = now["summary"]

    if args.record or not BASELINE.exists():
        BASELINE.write_text(json.dumps(now, ensure_ascii=False, indent=1), encoding="utf-8")
        print("taban kaydedildi:", BASELINE)
        for k, label, _, _ in CHECKS:
            print("   %-30s %s" % (label, s[k]))
        return 0

    base = json.loads(BASELINE.read_text(encoding="utf-8"))["summary"]
    print("%-30s %10s %10s %10s" % ("ölçüt", "taban", "şimdi", "fark"))
    failed: list[str] = []
    for key, label, tolerance, better in CHECKS + [(k, l, None, b) for k, l, b in WATCH]:
        b, n = base.get(key), s.get(key)
        if b is None or n is None:
            continue
        d = n - b
        mark = ""
        if tolerance is not None:
            worse = (d < -tolerance) if better == "yüksek" else (d > tolerance)
            if worse:
                failed.append(label)
                mark = "  ← DÜŞTÜ"
        print("%-30s %10s %10s %+10s%s" % (label, b, n, round(d, 3), mark))

    if failed:
        print()
        print("KALDI:", ", ".join(failed))
        # Which questions changed, so the next step is a question and not a hunt.
        by_id = {r["id"]: r for r in json.loads(BASELINE.read_text(encoding="utf-8"))["rows"]}
        for r in now["rows"]:
            was = by_id.get(r["id"])
            if was and set(r["missing"]) - set(was["missing"]):
                print("   %-46s artık kaçırıyor: %s" % (r["question"][:46], ",".join(sorted(set(r["missing"]) - set(was["missing"])))))
        return 1

    print()
    print("GEÇTİ — doğru tabloya ulaşma korundu")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
