"""python -m editor.proofing <generation_id> [--only NAME ...] [--dry]

--dry runs the checks and prints the findings without writing anything (for measuring a
rule on real books)."""
import argparse
import asyncio
import json

from . import checks, run_all

ap = argparse.ArgumentParser()
ap.add_argument("generation_id")
ap.add_argument("--only", nargs="*")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
if a.dry:
    async def dry():
        for name, mod in checks().items():
            if a.only and name not in a.only:
                continue
            res = await mod.run(a.generation_id)
            findings, stats = res if isinstance(res, tuple) else (res, {})
            print(json.dumps({"check": name, "stats": stats, "findings": findings}, ensure_ascii=False,
                             indent=1, default=str))
    asyncio.run(dry())
else:
    print(json.dumps(asyncio.run(run_all(a.generation_id, a.only)), ensure_ascii=False, indent=1, default=str))
