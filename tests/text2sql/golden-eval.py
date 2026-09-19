#!/usr/bin/env python3
"""Score the pipeline against the golden set — schema linking first, SQL second.

Execution accuracy alone hides the failure this system has to avoid: the right number from the wrong
table. A query that joins a table nobody asked for can still return a plausible figure, and counting
it as a pass is how a benchmark rewards luck. So every case is scored on what reached the model as
well as on what came back — table recall, the tables that had no business being there, and whether a
question this deployment cannot answer was refused rather than answered anyway.

    PYTHONPATH=backend python3 tests/text2sql/golden-eval.py --golden tests/text2sql/golden-timas.json

Paralel: `--shard 0/12 --out a.json` … her parça ayrı süreçte koşar; `--merge a.json b.json … --out all.json`
parçaları golden sırasıyla birleştirip özeti bütün üzerinden yeniden hesaplar (quality-gate.py bunu yapar).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path


def answer_block_reason(sq):
    # A clarification is still not a delivered answer. Moving a question from
    # rejection to clarification must not make the acceptance score look better.
    return sq.refusal_reason or ("CLARIFICATION" if sq.clarification else None)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default="tests/text2sql/golden-timas.json")
    ap.add_argument("--out", default="")
    ap.add_argument("--kind", default="base-table", help="base-table | view | all")
    ap.add_argument("--shard", default="", help="I/N: yalnız bu parçanın vakaları (paralel koşu)")
    ap.add_argument("--merge", nargs="*", default=None, help="parça çıktılarını birleştir, ölçüm yapma")
    args = ap.parse_args(argv)

    golden = json.loads(Path(args.golden).read_text(encoding="utf-8"))
    cases = [x for x in golden["cases"] if args.kind == "all" or x.get("kind") == args.kind]
    if args.merge is not None:
        order = {c["id"]: i for i, c in enumerate(cases)}
        rows = [r for f in args.merge for r in json.loads(Path(f).read_text(encoding="utf-8"))["rows"]]
        rows.sort(key=lambda r: order.get(r["id"], len(order)))
        return report(rows, args.out)
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        cases = cases[i::n]

    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store
    from semantic_layer.runtime.resolver import SemanticResolver
    from semantic_layer.runtime.audit import unmet_obligations, audit_sql, sources_from
    from semantic_bridge.app import Runtime

    class Llm:
        def chat(self, messages): return ""

    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn)
    rt = Runtime(s, store=store, connector=None, llm=Llm())
    c = rt.existing
    # The runtime's own resolver: it carries the datasource's declared equivalences (dates, filters),
    # and a bare resolver measures a system that does not exist.
    resolver = rt.resolver

    rows = []
    for case in cases:
        t0 = time.perf_counter()
        sq = resolver.resolve(case["question"], today=date(2026, 8, 20))
        # What the prompt is actually built from, not what retrieval proposed: the selector
        # narrows between the two, and scoring the wider list credits the system with tables
        # it never sent and blames it for tables it dropped.
        sent = [p.entity for p in c._one_per_entity(c.narrow(sq, c.relevant_entities(sq, [])), sq)]
        prompt = c.build_messages(sq, [])[0]["content"]
        ms = (time.perf_counter() - t0) * 1000

        want = set(case["expected_tables"])
        got = set(sent)
        # The gate over the answer this case says is right. A correct answer the gate refuses is a
        # gate bug, and until now nothing counted those.
        gate = None
        expected_sql = (case.get("expected_sql") or "").strip()
        if expected_sql and not case.get("expect_refusal"):
            try:
                gate = unmet_obligations(sq, expected_sql, sources=sources_from(rt.profiles)) + audit_sql(sq, expected_sql, conventions=rt.conventions)
            except Exception as e:  # noqa: BLE001
                gate = [f"kapı hatası: {e!r}"[:200]]
        rows.append({
            "id": case["id"], "question": case["question"],
            "state": sq.state, "refusal": answer_block_reason(sq),
            "expected": sorted(want), "sent": sorted(got),
            "missing": sorted(want - got), "extra": sorted(got - want),
            "recall": (len(want & got) / len(want)) if want else None,
            "precision": (len(want & got) / len(got)) if got else None,
            "tables_sent": len(got), "prompt_chars": len(prompt),
            "tokens": round(len(prompt) / 3), "ms": round(ms),
            "gate": gate,
        })
    return report(rows, args.out)


def report(rows: list[dict], out: str) -> int:
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
        # share of golden answers the gate lets through; the denominator is every case with an answer
        "gate_recall": round(sum(1 for r in rows if r["gate"] == []) / (sum(1 for r in rows if r["gate"] is not None) or 1), 3),
        "gate_refused": sum(1 for r in rows if r["gate"]),
        "states": {k: sum(1 for r in rows if r["state"] == k) for k in ("RESOLVED", "PARTIAL", "UNRESOLVED")},
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n%-46s %-9s %-5s %-5s %6s  %s" % ("soru", "durum", "rec", "eks", "token", "fazladan"))
    for r in rows:
        if r["gate"]:
            print("KAPI REDDİ %-40s %s" % (r["question"][:40], "; ".join(r["gate"])[:160]))
    for r in rows:
        print("%-46s %-9s %-5s %-5d %6d  %s" % (
            r["question"][:44], r["state"],
            "-" if r["recall"] is None else "%.2f" % r["recall"],
            len(r["missing"]), r["tokens"], ",".join(r["extra"][:5])))
    if out:
        Path(out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\nyazildi:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
