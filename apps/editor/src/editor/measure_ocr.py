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
import re
import time
from pathlib import Path

from . import db, ledger, prompts, schemas
from .document import _collapse_repeats, layer_health, book_stems, render_page
from .llm import Llm, image_part


def _w(t: str) -> list[str]:
    # markdown emphasis/heading marks ("**baskı**", "# Başlık") are formatting, not letters
    return ledger.norm(re.sub(r"[*#_`|>]+", " ", t)).split()


def score(truth: str, read: str, keep: set[str] | None = None) -> dict:
    """Words of the truth the reading does not contain, ORDER IGNORED. A page with speech
    bubbles and captions has no single reading order: comparing sequences charged a reader
    for reading a caption before the body (measured: a parser re-reading the very same
    digital text scored 14% "wrong" on order alone). A missing word is `changed` when the
    reading has a near-identical unmatched word (a misread letter, a "corrected" suffix) and
    `lost` otherwise. Extra words are not errors: text inside pictures is legitimately read."""
    from collections import Counter
    # `keep`: the words the book itself uses more than once. A page whose body is healthy can
    # still carry a scrambled caption or curved title in its digital layer ("icch", "mac" for
    # "Machu Picchu"); those fragments are not truth, and a reader that gets them right was
    # being charged for it. Only words the book confirms elsewhere are counted.
    a, b = Counter(w for w in _w(truth) if keep is None or w in keep), Counter(_w(read))
    missing = a - b
    spare = list((b - a).elements())
    lost = changed = 0
    pairs = []
    for word, n in missing.items():
        for _ in range(n):
            best, bi = 0.0, -1
            for i, cand in enumerate(spare):
                if abs(len(cand) - len(word)) <= 3:
                    r = difflib.SequenceMatcher(None, word, cand, autojunk=False).ratio()
                    if r > best:
                        best, bi = r, i
            if best >= 0.7:
                changed += 1
                pairs.append((word, spare.pop(bi)))
            else:
                lost += 1
    return {"words": sum(a.values()), "lost": lost, "changed": changed, "pairs": pairs}


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
        from collections import Counter
        freq = Counter(w for t in layers for w in _w(t))
        keep = {w for w, n in freq.items() if n >= 2}
        cand = []
        for p, d in by.items():
            layer, ocr = d.get("TEXT_LAYER", ""), d.get("OCR")
            if ocr is None or len(_w(layer)) < 40 or layer_health(layer, df, mean)["suspect"]:
                continue
            s = score(layer, ocr)
            looped = _collapse_repeats(ocr)[1] > 0
            cand.append({"book": bk["title"], "bv": str(bk["bv"]), "page": p, "truth": layer, "keep": keep,
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
                # markup (HTML/markdown/layout JSON) is not text of the page
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r'"(bbox|category)"\s*:\s*("[^"]*"|\[[^\]]*\])', " ", text)
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


def export(pages: list[dict], folder: Path) -> None:
    """The hard pages as one PDF (for tools that take PDFs) and their order."""
    import pymupdf
    from .document import _open_version
    folder.mkdir(parents=True, exist_ok=True)
    out = pymupdf.open()
    for p in pages:
        doc, _ = _open_version(p["bv"])
        out.insert_pdf(doc, from_page=p["page"] - 1, to_page=p["page"] - 1)
    out.save(folder / "hard.pdf")
    (folder / "hard.json").write_text(json.dumps([{"book": p["book"], "page": p["page"]} for p in pages],
                                                 ensure_ascii=False))


def external(pages: list[dict], path: Path) -> list[dict]:
    """Readings made by a tool outside the gateway: a JSON list, one text per exported page."""
    texts = json.loads(path.read_text())
    return [{"ok": t is not None, "text": t or "", "sec": 0.0} for t in texts][:len(pages)]


def rescore(files: list[Path], per_book: int, consensus: Path | None = None) -> None:
    """Score readings saved by earlier runs (their `readings`) with the current metric.

    `consensus`: a second, independent extraction of the same digital text layer (one text
    per page). Truth is then only what BOTH extractors read — two parsers agreeing on the
    publisher's text is as close to a transcription as the corpus offers without a human,
    and their disagreements (extraction artefacts of either) stop being charged to OCR."""
    pages = hard_pages(per_book)
    if consensus:
        from collections import Counter
        other = json.loads(consensus.read_text())
        for p, t in zip(pages, other):
            agreed = Counter(_w(p["truth"])) & Counter(_w(t or ""))
            p["truth"] = " ".join(agreed.elements())
    runs: dict[str, list[dict]] = {"stored": [{"ok": True, "text": p["stored_ocr"], "sec": 0.0} for p in pages]}
    for f in files:
        data = json.loads(f.read_text())
        if isinstance(data, list):                                  # an external tool's texts
            runs[f.stem] = [{"ok": True, "text": t or "", "sec": 0.0} for t in data[:len(pages)]]
            continue
        for name, texts in data.get("readings", {}).items():
            if name != "stored":
                runs[name] = [{"ok": bool(t), "text": t or "", "sec": 0.0} for t in texts]
    report(pages, runs)


def report(pages: list[dict], results: dict) -> dict:
    rep = {}
    for name, res in results.items():
        words = lost = changed = loops = failed = 0
        pairs: dict[tuple, int] = {}
        for p, r in zip(pages, res):
            if not r["ok"]:
                failed += 1
                continue
            loops += _collapse_repeats(r["text"])[1] > 0
            sc = score(p["truth"], r["text"], p.get("keep"))
            words += sc["words"]; lost += sc["lost"]; changed += sc["changed"]
            for pr in sc["pairs"]:
                pairs[pr] = pairs.get(pr, 0) + 1
        top = sorted(pairs.items(), key=lambda kv: -kv[1])[:10]
        rep[name] = {"pages": len(res) - failed, "failed": failed,
                     "wer_pct": round(100 * (lost + changed) / max(1, words), 2),
                     "lost_pct": round(100 * lost / max(1, words), 2),
                     "changed_pct": round(100 * changed / max(1, words), 2), "loops": loops,
                     "top_changes": [f"{a}→{b} ×{n}" for (a, b), n in top]}
    for name, r in sorted(rep.items(), key=lambda kv: kv[1]["wer_pct"]):
        print(f"{name[:34]:35s} hata %{r['wer_pct']:5.2f} (yanlış okunan %{r['changed_pct']:5.2f}, eksik %{r['lost_pct']:5.2f})"
              f" | döngü {r['loops']} | düşen {r['failed']}")
        print("      ", r["top_changes"][:6])
    return rep


async def main(aliases: list[str], per_book: int, out: Path | None,
               export_to: Path | None = None, externals: list[str] | None = None) -> None:
    pages = hard_pages(per_book)
    print(f"zor küme: {len(pages)} sayfa ({per_book}/kitap), döngülü {sum(p['stored_looped'] for p in pages)}")
    if export_to:
        export(pages, export_to)
        print("dışa aktarıldı:", export_to)
        return
    results = {"stored": [{"ok": True, "text": p["stored_ocr"], "sec": 0.0} for p in pages]}
    for spec in externals or []:
        name, _, path = spec.partition("=")
        results[name] = external(pages, Path(path))
    for spec in aliases:
        alias, _, native = spec.partition("=")          # alias | alias=NATIVE PROMPT | alias=@file | alias:nothink
        if native.startswith("@"):
            native = Path(native[1:]).read_text().strip()
        alias, _, mode = alias.partition(":")
        thinking = False if mode == "nothink" else None
        sem = asyncio.Semaphore(4)
        results[spec] = await asyncio.gather(*(read(alias, p, sem, native or None, thinking) for p in pages))
    rep = report(pages, results)
    for name, res in results.items():
        rep[name]["sec_per_page"] = round(sum(r["sec"] for r in res) / max(1, len(res)), 1)
        print(f"   {name[:34]:35s} {rep[name]['sec_per_page']} sn/sayfa")
    if out:
        out.write_text(json.dumps({"pages": [{k: p[k] for k in ("book", "page", "stored_err", "stored_looped")}
                                             for p in pages], "report": rep,
                                   "readings": {n: [r["text"] for r in res] for n, res in results.items()}},
                                  ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--alias", action="append", default=[])
    ap.add_argument("--export", help="write the hard pages as DIR/hard.pdf + hard.json and stop")
    ap.add_argument("--external", action="append", default=[], help="NAME=readings.json (one text per page)")
    ap.add_argument("--rescore", nargs="*", help="score saved readings (bench outputs / external JSON lists)")
    ap.add_argument("--consensus", help="second extraction of the text layer; truth = words both agree on")
    ap.add_argument("--per-book", type=int, default=8)
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.rescore is not None:
        rescore([Path(x) for x in a.rescore], a.per_book, Path(a.consensus) if a.consensus else None)
        raise SystemExit(0)
    asyncio.run(main(a.alias, a.per_book, Path(a.out) if a.out else None,
                     Path(a.export) if a.export else None, a.external))
