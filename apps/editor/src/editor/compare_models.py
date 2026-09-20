"""Read the same pages with two vision aliases and report where they differ.

  python -m editor.compare_models <generation_id> [--ref book-vision-deep]
                                 [--alias book-vision-deep-fp8] [--out FILE]

Both aliases get exactly the same prompt and image for every page the generation
scanned deeply, one alias after the other (they need not fit on the GPU together). Nothing is written to the
ledger's analysis tables: results go to a JSON file (the calls themselves are logged
in ed.model_call without a generation, like any other call)."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from . import db, prompts, schemas
from .config import settings
from .document import page_text_numbered, render_page
from .llm import Llm, image_part
from .vision import contradicts


def _names(res: dict) -> list[str]:
    return sorted((c.get("name") or "?").strip().casefold() for c in res.get("characters", []))


async def main(generation_id: str, ref_alias: str, alias: str, out: Path) -> None:
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    pages = [r["page_no"] for r in db.all_rows("SELECT page_no FROM page_scan WHERE generation_id=%s AND"
                                               " pass='DEEP' ORDER BY page_no", generation_id)]
    sem = asyncio.Semaphore(settings().deep_concurrency * 2)
    llm = Llm(None)

    async def scan(alias: str, p: int) -> dict:
        png = Path(render_page(str(gen["book_version_id"]), p)["path"]).read_bytes()
        ctx = "\n".join(page_text_numbered(generation_id, q) for q in (p - 1, p + 1) if q > 0)
        ref, body = prompts.render("page_scan_deep", page_no=str(p), reasons="DEEP_FIRST", fast_result="-",
                                   page_text=page_text_numbered(generation_id, p), context_text=ctx or "-",
                                   known_characters="-")
        t0 = time.time()
        try:
            async with sem:
                res, call_id = await llm.chat(alias, [{"role": "user", "content": [
                    image_part(png), {"type": "text", "text": body}]}], prompt=ref,
                    schema=schemas.PAGE_SCAN, pages=[p], max_tokens=16384, temperature=0.1)
            tok = db.one("SELECT completion_tokens t, latency_ms l FROM model_call WHERE id=%s", call_id)
            return {"page": p, "ok": True, "result": res, "sec": round(time.time() - t0),
                    "tokens": tok["t"], "latency_ms": tok["l"]}
        except Exception as e:  # noqa: BLE001
            return {"page": p, "ok": False, "error": str(e)[:300], "sec": round(time.time() - t0)}

    runs, wall = {}, {}
    for al in (ref_alias, alias):
        t0 = time.time()
        runs[al] = await asyncio.gather(*(scan(al, p) for p in pages))
        wall[al] = round(time.time() - t0)
    rows, same_names, same_count = [], 0, 0
    for r, c in zip(runs[ref_alias], runs[alias]):
        if not (r["ok"] and c["ok"]):
            rows.append({"page": r["page"], "failed": {ref_alias: r.get("error"), alias: c.get("error")}})
            continue
        a, b = r["result"], c["result"]
        na, nb = _names(a), _names(b)
        same_names += na == nb
        same_count += len(a["characters"]) == len(b["characters"])
        rows.append({"page": r["page"], "names_ref": na, "names_cand": nb, "names_equal": na == nb,
                     "figures": [len(a["characters"]), len(b["characters"])],
                     "objects": [len(a["objects"]), len(b["objects"])],
                     "contradicts": [sum(contradicts(x) for x in a["text_visual_checks"]),
                                     sum(contradicts(x) for x in b["text_visual_checks"])],
                     "text_in_image": [len(a["text_in_image"]), len(b["text_in_image"])],
                     "tokens": [r["tokens"], c["tokens"]],
                     "scene_ref": a["scene"]["description"][:160], "scene_cand": b["scene"]["description"][:160]})
    def stats(al: str) -> dict:
        ok = [x for x in runs[al] if x["ok"]]
        return {"ok": len(ok), "wall_sec": wall[al],
                "avg_tokens": round(sum(x["tokens"] or 0 for x in ok) / max(1, len(ok))),
                "avg_latency_s": round(sum(x["latency_ms"] or 0 for x in ok) / max(1, len(ok)) / 1000)}

    summary = {"pages": len(pages), ref_alias: stats(ref_alias), alias: stats(alias),
               "names_equal_pages": same_names, "figure_count_equal_pages": same_count}
    out.write_text(json.dumps({"summary": summary, "pages": rows, "raw": runs},
                              ensure_ascii=False, indent=1, default=str))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for x in rows:
        if x.get("failed"):
            print(f"s{x['page']}: DÜŞTÜ {x['failed']}")
        elif not x["names_equal"] or x["figures"][0] != x["figures"][1] or x["contradicts"][0] != x["contradicts"][1]:
            print(f"s{x['page']}: adlar {x['names_ref']} | {x['names_cand']}  figür {x['figures']}  çelişki {x['contradicts']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("generation_id")
    ap.add_argument("--ref", default="book-vision-deep")
    ap.add_argument("--alias", default="book-vision-deep-fp8")
    ap.add_argument("--out", default="/data/editor/storage/compare-models.json")
    a = ap.parse_args()
    asyncio.run(main(a.generation_id, a.ref, a.alias, Path(a.out)))
