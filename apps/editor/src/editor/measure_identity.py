"""Measure figure identity against the crops a human checked one by one.

  python -m editor.measure_identity [--golden tests/golden]   (every *-figures.json in it)

Coverage alone is a bad target: naming every figure at random would score 100%. This
prints precision (of the names given, how many are right) next to coverage (of the
figures a human named, how many got that name), on the one book whose every crop was
looked at, and coverage for the rest of the corpus."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from . import db, figure_identity


def _key(page: int, bbox: list[int]) -> str:
    return f"{page}:{','.join(str(int(b)) for b in bbox)}"


async def against_golden(path: Path) -> dict:
    """Precision and coverage on one hand-checked book. A figure marked `unsure` (a
    group, a crop nobody can name with confidence) is left out of both sides; `accept`
    lists the names that are equally right where the book's text itself splits one
    character into two."""
    gold = json.loads(path.read_text())
    gid = gold["generation"]
    truth = {_key(f["page"], f["bbox"]): f for f in gold["figures"]}
    st = await figure_identity.resolve(gid, write=False)
    figs = {str(f["id"]): f for f in figure_identity._figures(gid)}
    got = {_key(figs[mid]["page_no"], figs[mid]["bbox"]): name
           for mid, name in st["by_figure"].items() if mid in figs}
    judged = {k: v for k, v in got.items() if k in truth and not truth[k].get("unsure")}

    def right(k: str, name: str) -> bool:
        t = truth[k]
        return bool(t.get("name")) and name in (t.get("accept") or [t["name"]])

    correct = sum(1 for k, v in judged.items() if right(k, v))
    named_truth = [k for k, t in truth.items() if t.get("name") and not t.get("unsure")]
    return {"book": gold["book"], "figures": len(truth), "human_named": len(named_truth),
            "named": len(judged), "correct": correct,
            "precision": round(correct / max(1, len(judged)), 3),
            "coverage": round(correct / max(1, len(named_truth)), 3),
            "named_a_non_figure": sum(1 for k in judged if truth[k].get("not_a_figure")),
            "errors": [{"figure": k, "said": v, "truth": truth[k].get("name")}
                       for k, v in judged.items() if not right(k, v)][:25]}


async def main(golden: Path) -> None:
    files = sorted(golden.glob("*-figures.json")) if golden.is_dir() else [golden]
    tot = {"named": 0, "correct": 0, "human_named": 0}
    for f in files:
        r = await against_golden(f)
        for k in tot:
            tot[k] += r[k]
        print(f"{r['book'][:30]:31s} kesinlik {r['precision']:.2f} kapsama {r['coverage']:.2f} "
              f"({r['correct']}/{r['named']} doğru, insan {r['human_named']}; figür-olmayana ad {r['named_a_non_figure']})",
              flush=True)
        for e in r["errors"]:
            print(f"      {e['figure']:24s} dedi {e['said']!s:22s} doğrusu {e['truth']}")
    print(f"ALTIN TOPLAM kesinlik {tot['correct'] / max(1, tot['named']):.2f} "
          f"kapsama {tot['correct'] / max(1, tot['human_named']):.2f} ({len(files)} kitap)\n")
    rows = db.all_rows("""select b.title t, g.id gid from generation g
      join book_version bv on bv.id=g.book_version_id join book b on b.id=bv.book_id
      where g.sealed_at is not null and g.id=(select g2.id from generation g2
        where g2.book_version_id=bv.id and g2.sealed_at is not null order by g2.created_at desc limit 1)
      order by bv.page_count""")
    tot_f = tot_n = 0
    for r in rows:
        st = await figure_identity.resolve(str(r["gid"]), write=False)
        tot_f += st["figures"]
        tot_n += st["named_figures"]
        print(f"{r['t'][:30]:31s} figür {st['figures']:3d} küme {st['clusters']:3d} "
              f"adlı {st['named_figures']:3d} (%{round(100 * st['named_figures'] / max(1, st['figures'])):3d})"
              f" | hakem {st['adjudicated']:3d} bölünen {st.get('split', 0):2d} "
              f"red-figür-değil {st['refused_not_character']:2d} red-karışık {st['refused_mixed']:2d}",
              flush=True)
    print(f"TOPLAM figür {tot_f} adlı {tot_n} (%{round(100 * tot_n / max(1, tot_f))})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="/app/tests/golden")
    a = ap.parse_args()
    asyncio.run(main(Path(a.golden)))
