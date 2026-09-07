#!/usr/bin/env python3
"""Score the pipeline against the golden set — schema linking first, SQL second.

Execution accuracy alone hides the failure this system has to avoid: the right number from the wrong
table. A query that joins a table nobody asked for can still return a plausible figure, and counting
it as a pass is how a benchmark rewards luck. So every case is scored on what reached the model as
well as on what came back — table recall, the tables that had no business being there, and whether a
question this deployment cannot answer was refused rather than answered anyway.

    PYTHONPATH=backend python3 tests/text2sql/golden-eval.py --golden tests/text2sql/golden-timas.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="tests/text2sql/golden-timas.json")
    ap.add_argument("--out", default="")
    ap.add_argument("--kind", default="base-table", help="base-table | view | all")
    args = ap.parse_args(argv)

    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store
    from semantic_layer.runtime.resolver import SemanticResolver
    from semantic_bridge.app import Runtime

    class Llm:
        def chat(self, messages): return ""

    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn)
    rt = Runtime(s, store=store, connector=None, llm=Llm())
    c = rt.existing
    resolver = SemanticResolver(store, s.tenant_id, s.datasource_id, rt.profiles)

    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    cases = [x for x in golden["cases"] if args.kind == "all" or x.get("kind") == args.kind]
    rows = []
    for case in cases:
        t0 = time.perf_counter()
        sq = resolver.resolve(case["question"], today=date(2026, 8, 20))
        sent = [p.entity for p in c._one_per_entity(c.relevant_entities(sq, []), sq)]
        prompt = c.build_messages(sq, [])[0]["content"]
        ms = (time.perf_counter() - t0) * 1000

        want = set(case["expected_tables"])
        got = set(sent)
        rows.append({
            "id": case["id"], "question": case["question"],
            "state": sq.state, "refusal": sq.refusal_reason,
            "expected": sorted(want), "sent": sorted(got),
            "missing": sorted(want - got), "extra": sorted(got - want),
            "recall": (len(want & got) / len(want)) if want else None,
            "precision": (len(want & got) / len(got)) if got else None,
            "tables_sent": len(got), "prompt_chars": len(prompt),
            "tokens": round(len(prompt) / 3), "ms": round(ms),
        })

    scored = [r for r in rows if r["recall"] is not None]
    n = len(scored) or 1
    summary = {
        "cases": len(rows),
        "table_recall": round(sum(r["recall"] for r in scored) / n, 3),
        "table_precision": round(sum(r["precision"] or 0 for r in scored) / n, 3),
        "fully_recalled": sum(1 for r in scored if r["recall"] == 1.0),
        "mean_tables_sent": round(sum(r["tables_sent"] for r in rows) / (len(rows) or 1), 1),
        "mean_extra_tables": round(sum(len(r["extra"]) for r in scored) / n, 1),
        "mean_tokens": round(sum(r["tokens"] for r in rows) / (len(rows) or 1)),
        "refused": sum(1 for r in rows if r["refusal"]),
        "states": {k: sum(1 for r in rows if r["state"] == k) for k in ("RESOLVED", "PARTIAL", "UNRESOLVED")},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n%-46s %-9s %-5s %-5s %6s  %s" % ("soru", "durum", "rec", "eks", "token", "fazladan"))
    for r in rows:
        print("%-46s %-9s %-5s %-5d %6d  %s" % (
            r["question"][:44], r["state"],
            "-" if r["recall"] is None else "%.2f" % r["recall"],
            len(r["missing"]), r["tokens"], ",".join(r["extra"][:5])))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\nyazildi:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
