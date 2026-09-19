#!/usr/bin/env python3
"""Read-only probe: is each candidate table needed? One token per table, with its probability.

The table selector asks for a JSON list and gets a yes or a no per table with nothing in between.
Here every candidate the compiler would offer is asked about on its own — closed set, one output
token (vLLM structured_outputs.choice) — and the probability of "needed" is read from the returned
log-probabilities. The calls for one question go out together; vLLM batches them.

What the model is shown about a table is the thing being measured, so it is a variant:

  bare     the selector's own note: description and the first twelve columns in declaration order
  columns  the note, plus the columns of that table this question reached (resolved slots and the
           lexical/value index — the same set `prompt_columns` keeps for the SQL prompt)
  context  `columns`, and the whole shortlist above it, so the table is judged against the others

Each decision is a record (state, question, candidate, probability, target). The target comes from
the golden case's expected_tables and is never shown to the model. Nothing is written to the
catalog or the application; the running bridge is not touched.

  PYTHONPATH=backend python3 tests/text2sql/probe-table-choice-logprob.py --case 0 --variant context
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from semantic_bridge.app import build_runtime  # noqa: E402

VERSION = "table-choice-logprob-probe-v2"
VARIANTS = ("bare", "columns", "context")
CHOICES = ["E", "H"]
RULE = ("Bu tablo, soruyu yanıtlayan SQL'de gerekli mi? Gerekli: ölçü, kırılım, filtre ya da zorunlu "
        "bağlantı bu tablodan geliyor. E: gerekli. H: gerekli değil. Yalnız tek harf yaz.")


def reached_columns(comp, q, entity: str) -> list[str]:
    """Columns of `entity` this question reached, with what the source says they are."""
    p = comp.by_entity.get(entity)
    if p is None:
        return []
    named = {s.mapping.column.upper() for s in q.slots
             if s.mapping and s.mapping.column and s.mapping.entity in (None, "", entity)}
    scored = comp._scored_columns(q.question)
    out = []
    for c in p.columns:
        name = c.name.upper()
        if name in named or (entity, name) in scored:
            out.append(f"{c.name} ({c.description.strip()[:60]})" if c.description else c.name)
    return out


def ask(client: httpx.Client, s, content: str) -> float | None:
    body = {"model": s.llm_model, "temperature": 0, "seed": 17, "max_tokens": 1,
            "logprobs": True, "top_logprobs": 10,
            "chat_template_kwargs": {"enable_thinking": False},
            "structured_outputs": {"choice": CHOICES},
            "messages": [{"role": "user", "content": content}]}
    # The model sits behind a tunnel that drops a connection now and then. One dropped call out of
    # several thousand is not a result; it is retried, and only a call that keeps failing is a gap.
    for attempt in range(4):
        try:
            r = client.post(s.llm_base + "/chat/completions", json=body)
            r.raise_for_status()
            break
        except (httpx.TransportError, httpx.HTTPStatusError):
            if attempt == 3:
                return None
            time.sleep(2 ** attempt)
    top = r.json()["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
    mass = {c: sum(math.exp(t["logprob"]) for t in top if t["token"].strip() == c) for c in CHOICES}
    total = sum(mass.values())
    return round(mass["E"] / total, 4) if total > 0 else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", default=str(ROOT / "tests/text2sql/golden-timas.json"))
    ap.add_argument("--case", type=int, action="append", help="golden index; repeatable; default all")
    ap.add_argument("--variant", action="append", choices=VARIANTS, help="repeatable; default all")
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--out", help="JSONL written as each question finishes, so a broken run keeps what it measured")
    args = ap.parse_args()

    cases = json.load(open(args.golden, encoding="utf-8"))
    cases = cases if isinstance(cases, list) else cases["cases"]
    picked = [cases[i] for i in args.case] if args.case else cases
    variants = args.variant or list(VARIANTS)

    rt = build_runtime()
    comp, s = rt.existing, rt.settings
    headers = {"Authorization": f"Bearer {s.llm_key}"} if s.llm_key else {}
    records, summary = [], []
    out = open(args.out, "a", encoding="utf-8") if args.out else None
    with httpx.Client(timeout=300, trust_env=False, headers=headers,
                      limits=httpx.Limits(max_connections=args.parallel)) as client, \
            ThreadPoolExecutor(args.parallel) as pool:
        for case in picked:
            q = rt.resolver.resolve(case["question"])
            recalled = comp.recall(q.question) if comp.recall else []
            entities = comp.relevant_entities(q, recalled)
            placed = {sl.mapping.entity for sl in q.slots if sl.mapping and sl.mapping.entity in entities}
            expected = {t.upper() for t in case.get("expected_tables") or []}
            notes = {"bare": {e: (comp.entity_note(e) or "").replace("\n", " ")[:200] for e in entities}}
            notes["columns"] = {}
            for e in entities:
                reached = reached_columns(comp, q, e)
                notes["columns"][e] = notes["bare"][e] + (f" [soruyla eşleşen kolonlar: {', '.join(reached)}]" if reached else "")
            shortlist = "\n".join(f"- {e}: {notes['columns'][e]}" for e in entities)
            for variant in variants:
                note_of = notes["bare" if variant == "bare" else "columns"]
                head = f"Soru: {q.question}\n"
                if variant == "context":
                    head += f"Aday tabloların tamamı:\n{shortlist}\n\n"
                prompts = [f"{head}{RULE}\nDeğerlendirilen tablo: {e}: {note_of[e]}" for e in entities]
                t0 = time.monotonic()
                probs = list(pool.map(lambda c: ask(client, s, c), prompts))
                seconds = round(time.monotonic() - t0, 1)
                ranked = sorted(entities, key=lambda e: -(probs[entities.index(e)] or 0))
                hit = [e for e in entities if e.upper() in expected]
                summary.append({"family_id": case["id"], "variant": variant, "candidates": len(entities),
                                "seconds": seconds, "expected_missing_from_candidates": sorted(expected - {e.upper() for e in entities}),
                                "target_p": {e: probs[entities.index(e)] for e in hit},
                                "target_worst_rank": max((ranked.index(e) + 1 for e in hit), default=None),
                                "top5": [(e, probs[entities.index(e)]) for e in ranked[:5]]})
                mark = len(records)
                for e, p in zip(entities, probs):
                    records.append({"family_id": case["id"], "variant": variant,
                                    "state": f"Soru: {q.question} | Yerleşen tablolar: {', '.join(sorted(placed)) or '-'}",
                                    "question": {"type": "boolean", "instruction": RULE},
                                    "candidate": e, "candidate_note": note_of[e], "resolver_placed": e in placed,
                                    "p_needed": p, "target": e.upper() in expected,
                                    "target_source": "golden.expected_tables"})
                if out:
                    out.write(json.dumps({"summary": summary[-1], "records": records[mark:]}, ensure_ascii=False) + "\n")
                    out.flush()
    print(json.dumps({"version": VERSION, "model": s.llm_model, "cases": len(picked), "decisions": len(records),
                      "output_tokens_per_call": 1, "application_writes": 0,
                      "summary": summary, "records": records}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
