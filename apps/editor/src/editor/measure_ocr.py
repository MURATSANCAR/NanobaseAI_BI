"""Benchmark OCR models on the pages where OCR has hurt most.

  python -m editor.measure_ocr --alias book-vision-deep [--alias 'book-ocr-paddle=OCR:'] [--per-book 8] [--out FILE]

Ground truth is free wherever a page has a HEALTHY digital text layer: the publisher's
own text. The hard set is chosen by measurement, not by hand, and the same way for every
book: the pages where the stored OCR reading was furthest from that text (misreadings,
loops), most wrong first. Every candidate alias reads exactly those pages with the
production prompt and schema; nothing is written to page_text (calls are logged without a
generation). Reported per model: word error rate, how many words it CHANGED into another
valid-looking word (the "correcting" failure), loops, and seconds per page."""

from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import time
from pathlib import Path

from . import db, ledger, prompts, schemas
from .document import _collapse_repeats, layer_health, book_stems, render_page
from .llm import Llm, image_part


def _w(t: str) -> list[str]:
    return ledger.norm(t).split()


def score(truth: str, read: str) -> dict:
    """Words of the truth the reading lost or changed. Extra words are not errors: a reader
    that also transcribes a sign inside the picture is doing its job."""
    a, b = _w(truth), _w(read)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    lost = changed = 0
    pairs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "delete":
            lost += i2 - i1
        elif tag == "replace":
            changed += i2 - i1
            if i2 - i1 == j2 - j1:
                pairs += list(zip(a[i1:i2], b[j1:j2]))
    return {"words": len(a), "lost": lost, "changed": changed, "pairs": pairs}


def hard_pages(per_book: int) -> list[dict]:
    out = []
    books = db.all_rows(
        "SELECT b.title, bv.id AS bv, g.id AS gid FROM book b JOIN book_version bv ON bv.book_id=b.id"
        " JOIN LATERAL (SELECT g.id FROM generation g WHERE g.book_version_id=bv.id AND EXISTS"
        " (SELECT 1 FROM page_text pt WHERE pt.generation_id=g.id AND pt.source='OCR')"
        " ORDER BY g.created_at DESC LIMIT 1) g ON true ORDER BY bv.page_count")
    for bk in books:
        rows = db.all_rows("SELECT page_no, source, text FROM page_text WHERE generation_id=%s", bk["gid"])
        by: dict[int, dict] = {}
        for r in rows:
            by.setdefault(r["page_no"], {})[r["source"]] = r["text"] or ""
        layers = [by.get(p, {}).get("TEXT_LAYER", "") for p in sorted(by)]
        df, mean = book_stems(layers)
        cand = []
        for p, d in by.items():
            layer, ocr = d.get("TEXT_LAYER", ""), d.get("OCR")
            if ocr is None or len(_w(layer)) < 40 or layer_health(layer, df, mean)["suspect"]:
                continue
            s = score(layer, ocr)
            looped = _collapse_repeats(ocr)[1] > 0
            cand.append({"book": bk["title"], "bv": str(bk["bv"]), "page": p, "truth": layer,
                         "stored_ocr": ocr, "stored_err": (s["lost"] + s["changed"]) / s["words"],
                         "stored_looped": looped})
        cand.sort(key=lambda x: (-x["stored_looped"], -x["stored_err"]))
        out += cand[:per_book]
    return out


async def read(alias: str, page: dict, sem: asyncio.Semaphore, native: str | None = None,
               thinking: bool | None = None) -> dict:
    """`native`: the model's own task prompt (an OCR specialist is trained on "OCR:", not on
    our instructions or a JSON schema); its answer is plain text."""
    png = Path(render_page(page["bv"], page["page"])["path"]).read_bytes()
    ref, body = prompts.render("ocr_page", page_no=str(page["page"]))
    t0 = time.time()
    try:
        async with sem:
            if native:
                text, _ = await Llm(None).chat(
                    alias, [{"role": "user", "content": [image_part(png), {"type": "text", "text": native}]}],
                    pages=[page["page"]], max_tokens=4096, temperature=0.0)
                return {"ok": True, "text": text, "sec": time.time() - t0}
            out, _ = await Llm(None).chat(
                alias, [{"role": "user", "content": [image_part(png), {"type": "text", "text": body}]}],
                prompt=ref, schema=schemas.OCR, pages=[page["page"]], max_tokens=16384, temperature=0.0,
                thinking=thinking)
            # (no `thinking=False`: a Thinking-only model then answers with an empty content —
            #  measured, 39 of 39 calls — so every alias runs the way production runs it)
        text = "\n\n".join(b["text"].strip() for b in out["blocks"] if b["text"].strip())
        return {"ok": True, "text": text, "sec": time.time() - t0}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "text": "", "sec": time.time() - t0, "error": str(e)[:200]}


async def main(aliases: list[str], per_book: int, out: Path | None) -> None:
    pages = hard_pages(per_book)
    print(f"zor küme: {len(pages)} sayfa ({per_book}/kitap), döngülü {sum(p['stored_looped'] for p in pages)}")
    results = {"stored": [{"ok": True, "text": p["stored_ocr"], "sec": 0.0} for p in pages]}
    for spec in aliases:
        alias, _, native = spec.partition("=")          # alias | alias=NATIVE PROMPT | alias:nothink
        alias, _, mode = alias.partition(":")
        thinking = False if mode == "nothink" else None
        sem = asyncio.Semaphore(4)
        results[spec] = await asyncio.gather(*(read(alias, p, sem, native or None, thinking) for p in pages))
    report = {}
    for name, res in results.items():
        words = lost = changed = loops = failed = 0
        pairs: dict[tuple, int] = {}
        for p, r in zip(pages, res):
            if not r["ok"]:
                failed += 1
                continue
            loops += _collapse_repeats(r["text"])[1] > 0
            s = score(p["truth"], r["text"])
            words += s["words"]; lost += s["lost"]; changed += s["changed"]
            for pr in s["pairs"]:
                pairs[pr] = pairs.get(pr, 0) + 1
        top = sorted(pairs.items(), key=lambda kv: -kv[1])[:12]
        report[name] = {"pages": len(res) - failed, "failed": failed, "words": words,
                        "lost_pct": round(100 * lost / max(1, words), 2),
                        "changed_pct": round(100 * changed / max(1, words), 2),
                        "wer_pct": round(100 * (lost + changed) / max(1, words), 2), "loops": loops,
                        "sec_per_page": round(sum(r["sec"] for r in res) / max(1, len(res)), 1),
                        "top_changes": [f"{a}→{b} ×{n}" for (a, b), n in top]}
        print(f"\n{name}: WER %{report[name]['wer_pct']} (kayıp %{report[name]['lost_pct']}, "
              f"değiştirilen %{report[name]['changed_pct']}) | döngü {loops} | düşen {failed} | "
              f"{report[name]['sec_per_page']} sn/sayfa")
        print("   ", report[name]["top_changes"])
    if out:
        out.write_text(json.dumps({"pages": [{k: p[k] for k in ("book", "page", "stored_err", "stored_looped")}
                                             for p in pages], "report": report,
                                   "readings": {n: [r["text"] for r in res] for n, res in results.items()}},
                                  ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias", action="append", required=True)
    ap.add_argument("--per-book", type=int, default=8)
    ap.add_argument("--out")
    a = ap.parse_args()
    asyncio.run(main(a.alias, a.per_book, Path(a.out) if a.out else None))
