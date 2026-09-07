"""Collect the values that make a column findable — all of them, and keep them where they belong.

The column index can route "trendyol satışları" to `CLFLINE.TRADINGGRP` because that column's values
happen to be in the catalog. Almost none are: the profiler probes values only on the tables it treats
as deep, so a few hundred of fourteen thousand columns know what they contain. Every other code
column — the channels, the cities, the special codes a business actually filters by, the customer
titles somebody types into a question — is invisible to a question that names one of its values.

This asks the source for them, for every text column of every table that holds rows, and writes the
answer to **two different places**, because they are two different things:

  * the search index (`--out`, JSON, runtime-only): every value, up to a ceiling that exists so one
    pathological column cannot become the whole index. Held in memory, matched against, never
    printed. This is what lets a question naming a customer reach the customer column.

  * `top_values` on the profile: only where the column is a genuine code set and holds no personal
    data. This is what a *prompt* shows the model, and the distinction is the point — a question
    about a customer must be answerable without handing a language model the customer list.

    python backend/scripts/probe_column_values.py --dry-run
    python backend/scripts/probe_column_values.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semantic_layer.config import SemanticSettings              # noqa: E402
from semantic_layer.pipeline import build_connector             # noqa: E402
from semantic_layer.store.catalog_store import open_store        # noqa: E402

#: Names that usually carry a small set of meanings. Only decides what is asked about first — what a
#: column actually holds is the source's answer, not a guess from its name.
_CODE_LIKE = re.compile(
    r"(SPECODE|CYPHCODE|AUXILCODE|TRADINGGRP|GRPCODE|GROUPCODE|STGRPCODE|CLASSCODE|DELIVERYCODE"
    r"|PAYMENTCODE|PROJECTCODE|CAMPAIGNCODE|DIVISION|DEPARTMENT|BRANCH|CITY|TOWN|COUNTRY|DISTRICT"
    r"|STATUS|STATE|KIND|CATEGORY|SECTOR|CURRENCY|CURR$|TYPE$|TYP$|CODE$|GRP$|NAME$|DEFINITION_$)")

#: How many distinct values are worth keeping for search. Far above what a code set holds, because a
#: customer title column has tens of thousands and every one is something a person might type. The
#: ceiling exists so one pathological column cannot become the whole index.
SEARCH_MAX = 5000

#: What a prompt may show: a code set small enough to read, and only where no personal data is in it.
PROMPT_MAX = 64

_NOT_A_TABLE = re.compile(r"(YEDEK|BACKUP|_BAK|_COPY|PERFTEST|_TMP|TEMP\d|_OLD|_ESKI|_TEST)", re.I)

DEFAULT_OUT = Path("/data/nanobaseai/bi/var/column-values.json")


def candidates(profiles, refresh: bool) -> list:
    """Every text column of every table that holds rows, likeliest first."""
    best: dict[str, object] = {}
    for p in profiles:
        if _NOT_A_TABLE.search(p.entity):
            continue
        cur = best.get(p.entity)
        if cur is None or (p.row_count or 0) > (cur.row_count or 0):
            best[p.entity] = p
    out = []
    for prof in best.values():
        if not (prof.row_count or 0):
            continue                    # an empty table has no values to learn
        for col in prof.columns:
            if col.top_values and not refresh:
                continue
            dtype = (col.data_type or "").lower()
            if not any(t in dtype for t in ("char", "text", "varchar")):
                continue
            out.append((prof, col, 0 if _CODE_LIKE.search(col.name.upper()) else 1))
    out.sort(key=lambda x: (x[2], -(x[0].row_count or 0)))
    return [(prof, col) for prof, col, _ in out]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refresh", action="store_true", help="daha önce okunanları da yeniden oku")
    ap.add_argument("--budget", type=float, default=0.0, help="saniye; 0 = sınır yok")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args(argv)

    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn)
    profiles = store.list_profiles(s.datasource_id)
    todo = candidates(profiles, args.refresh)
    if args.limit:
        todo = todo[: args.limit]
    print(f"aday kolon: {len(todo)} ({len({p.entity for p, _ in todo})} tabloda)")
    for prof, col in todo[:8]:
        print(f"   {prof.entity}.{col.name}  ({col.data_type}, {prof.row_count:,} satır)")
    if args.dry_run or not args.apply:
        print("\n(kuru çalışma — okumak için --apply)")
        return 0

    out_path = Path(args.out)
    search: dict[str, list[str]] = {}
    if out_path.exists():
        try:
            search = json.loads(out_path.read_text(encoding="utf-8")).get("values", {})
        except (OSError, json.JSONDecodeError):
            search = {}

    connector = build_connector(s)
    started = time.time()
    searched = prompted = freetext = failed = 0
    changed: dict[str, object] = {}
    for i, (prof, col) in enumerate(todo, start=1):
        if args.budget and time.time() - started > args.budget:
            print(f"\nsüre bütçesi doldu — {i - 1}/{len(todo)} kolon okundu")
            break
        try:
            rows = connector.top_values(prof.schema_name or "dbo", prof.table_name, col.name, SEARCH_MAX + 1)
        except Exception as e:  # noqa: BLE001
            failed += 1
            if failed <= 10:
                print(f"   okunamadı {prof.entity}.{col.name}: {str(e)[:70]}", flush=True)
            continue
        clean = [(str(v).strip(), n) for v, n in rows if str(v).strip()]
        if not clean:
            continue
        if len(clean) > SEARCH_MAX:
            freetext += 1               # unbounded free text: nothing to index, everything to lose
            continue

        # Everything searchable, wherever it came from.
        search[f"{prof.entity}.{col.name.upper()}"] = [v for v, _ in clean]
        searched += 1

        # Only a readable code set with no personal data in it reaches a prompt.
        if len(clean) <= PROMPT_MAX and not col.sensitive:
            col.top_values = clean
            col.distinct_count = len(clean)
            changed[prof.table_name] = prof
            prompted += 1
        if i % 25 == 0:
            print(f"   {i}/{len(todo)} denendi · aranabilir {searched} · isteme giren {prompted} "
                  f"({time.time() - started:.0f} sn)", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"datasource": s.datasource_id, "values": search},
                                   ensure_ascii=False), encoding="utf-8")
    for prof in changed.values():
        store.upsert_profile(prof)

    total = sum(len(v) for v in search.values())
    print(f"\naranabilir kolon : {len(search)}  ({total:,} değer) → {out_path}")
    print(f"isteme giren     : {prompted}  (yalnız ≤{PROMPT_MAX} değerli, kişisel veri içermeyen)")
    print(f"serbest metin    : {freetext} (>{SEARCH_MAX} farklı değer, alınmadı)")
    print(f"okunamadı        : {failed}")
    print(f"{len(changed)} profil güncellendi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
