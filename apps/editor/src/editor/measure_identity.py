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


def _iou(a: list[int], b: list[int]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


async def against_golden(path: Path, stored: bool = False) -> dict:
    """Precision and coverage on one hand-checked book.

    The labels were made on one generation; every new generation scans the pages again and
    draws its own boxes. So the book's LATEST generation is measured and a figure is the
    labelled one when it is on the same page and the boxes overlap (IoU >= 0.5). `stored`
    reads what the pipeline wrote instead of resolving again. A figure marked `unsure` is
    left out of both sides; `accept` lists names that are equally right where the book's
    text itself splits one character into two."""
    gold = json.loads(path.read_text())
    bv = db.one("SELECT book_version_id b FROM generation WHERE id=%s", gold["generation"])["b"]
    gid = str(db.one("SELECT g.id FROM generation g WHERE g.book_version_id=%s AND EXISTS (SELECT 1 FROM"
                     " character_mention m WHERE m.generation_id=g.id AND m.via='VISUAL')"
                     " ORDER BY g.created_at DESC LIMIT 1", bv)["id"])
    figs = figure_identity._figures(gid)
    if stored:
        named = {str(r["id"]): r["n"] for r in db.all_rows(
            "SELECT m.id, c.canonical_name n FROM character_mention m JOIN character c ON c.id=m.character_id"
            " WHERE m.generation_id=%s AND m.via='VISUAL' AND m.resolution='RESOLVED'", gid)}
    else:
        named = (await figure_identity.resolve(gid, write=False))["by_figure"]
    judged = correct = non_figure = 0
    hit_truth: set[int] = set()
    errors = []
    for f in figs:
        name = named.get(str(f["id"]))
        best, best_i = 0.0, None
        for i, t in enumerate(gold["figures"]):
            if t["page"] == f["page_no"]:
                v = _iou(t["bbox"], f["bbox"])
                if v > best:
                    best, best_i = v, i
        if name is None or best_i is None or best < 0.5:
            continue                                   # unnamed, or a figure nobody labelled
        t = gold["figures"][best_i]
        if t.get("unsure"):
            continue
        judged += 1
        non_figure += bool(t.get("not_a_figure"))
        if t.get("name") and name in (t.get("accept") or [t["name"]]):
            correct += 1
            hit_truth.add(best_i)
        else:
            errors.append({"figure": f"s{f['page_no']} {f['bbox']}", "said": name, "truth": t.get("name")})
    named_truth = [i for i, t in enumerate(gold["figures"]) if t.get("name") and not t.get("unsure")]
    return {"book": gold["book"], "generation": gid, "figures": len(figs), "human_named": len(named_truth),
            "named": judged, "correct": correct,
            "precision": round(correct / max(1, judged), 3),
            "coverage": round(len(hit_truth) / max(1, len(named_truth)), 3),
            "named_a_non_figure": non_figure, "errors": errors[:25]}


async def main(golden: Path, stored: bool = False, corpus: bool = True) -> None:
    files = sorted(golden.glob("*-figures.json")) if golden.is_dir() else [golden]
    tot = {"named": 0, "correct": 0, "human_named": 0}
    for f in files:
        r = await against_golden(f, stored)
        for k in tot:
            tot[k] += r[k]
        print(f"{r['book'][:30]:31s} kesinlik {r['precision']:.2f} kapsama {r['coverage']:.2f} "
              f"({r['correct']}/{r['named']} doğru, insan {r['human_named']}; figür-olmayana ad {r['named_a_non_figure']})",
              flush=True)
        for e in r["errors"]:
            print(f"      {e['figure']:24s} dedi {e['said']!s:22s} doğrusu {e['truth']}")
    print(f"ALTIN TOPLAM kesinlik {tot['correct'] / max(1, tot['named']):.2f} "
          f"kapsama {tot['correct'] / max(1, tot['human_named']):.2f} ({len(files)} kitap)\n")
    if not corpus:
        return
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
    ap.add_argument("--stored", action="store_true", help="measure what the pipeline wrote")
    ap.add_argument("--no-corpus", action="store_true", help="golden books only")
    a = ap.parse_args()
    asyncio.run(main(Path(a.golden), a.stored, not a.no_corpus))
