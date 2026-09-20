"""Measure the who-did-what reading on a generation that already exists.

  python -m editor.measure_actors <generation_id> [--out FILE]

Runs knowledge.attribute_event_actors with write=False: every (event, character) pair of
the generation is read, nothing is written to the generation (the calls are logged in
ed.model_call without a generation, like compare_models), and the readings go to a JSON
file. The summary shows what the probability threshold would do before it is trusted:
how the pairs fall into roles, how probabilities are spread, and where this reading and
the extractor's participant list disagree. The readings themselves are judged by eye
against the book; this tool does not know the right answer."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from . import knowledge
from .config import settings


def _spread(detail: list[dict]) -> dict:
    """How decided the readings are: share of pairs whose best probability is in each band."""
    bands = {"<0.5": 0, "0.5-0.7": 0, "0.7-0.9": 0, ">=0.9": 0}
    for d in detail:
        best = max(d["p_actor"], d["p_involved"], d["p_absent"])
        key = "<0.5" if best < 0.5 else "0.5-0.7" if best < 0.7 else "0.7-0.9" if best < 0.9 else ">=0.9"
        bands[key] += 1
    return bands


async def run(generation_id: str) -> dict:
    t0 = time.time()
    res = await knowledge.attribute_event_actors(generation_id, write=False)
    detail = res.pop("detail")
    return {"generation_id": generation_id, "seconds": round(time.time() - t0, 1),
            "min_probability": settings().actor_min_probability, "stats": res,
            "best_probability_bands": _spread(detail),
            "extractor_listed_read_absent": [d for d in detail if d["listed_by_extractor"]
                                             and d["role"] == "ABSENT"],
            "not_listed_read_actor": [d for d in detail if not d["listed_by_extractor"]
                                      and d["role"] == "ACTOR"],
            "uncertain": [d for d in detail if d["role"] == "UNCERTAIN"],
            "detail": detail}


def main() -> None:
    ap = argparse.ArgumentParser(prog="editor.measure_actors")
    ap.add_argument("generation_id")
    ap.add_argument("--out")
    a = ap.parse_args()
    out = asyncio.run(run(a.generation_id))
    path = Path(a.out) if a.out else settings().storage / "reports" / f"actors-{a.generation_id[:8]}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in out.items() if k != "detail"}, ensure_ascii=False, indent=2)[:6000])
    print(f"\n-> {path}")


if __name__ == "__main__":
    main()
