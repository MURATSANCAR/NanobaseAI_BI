"""Run a saved question corpus against candidate code without changing the service.

Uses the configured real catalog, LLM and read-only database connector. Does not
promote feedback or write query-learning logs. LLM queue admission remains shared.
Run in a private temporary checkout with the service environment already loaded.
"""
import argparse
import json
from pathlib import Path
import time
import uuid

from semantic_bridge.app import build_runtime

parser = argparse.ArgumentParser()
parser.add_argument("--baseline", type=Path, required=True)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--declaration", type=Path, required=True)
args = parser.parse_args()
previous = json.loads(args.baseline.read_text())
runtime = build_runtime()
# Preserve one catalog snapshot throughout this evaluation. No process serving
# traffic is patched, restarted, or pointed at this checkout.
runtime.ensure_fresh = lambda: None
runtime.conventions.load_equivalences(args.declaration)
runtime.store.log_query = lambda *a, **kw: "evaluation-" + uuid.uuid4().hex
out = []
generated = {}
compile_route = runtime.router._compile
def capture_sql(*a, **kw):
    result = compile_route(*a, **kw)
    generated["sql"] = result.sql
    return result
runtime.router._compile = capture_sql
try:
    for old in previous:
        generated.clear()
        start = time.monotonic()
        question = old["q"]
        try:
            reply = runtime.ask(question, thread_id=None, sample_size=5)
            trace = (reply.get("semantic") or {}).get("query") or {}
            item = {"q": question, "before": old["tip"], "after": reply.get("type"),
                    "rows": reply.get("rowCount", reply.get("totalRows")),
                    "compiler": (reply.get("semantic") or {}).get("compiler"),
                    "explanation": reply.get("explanation"), "sql": reply.get("sql") or generated.get("sql"),
                    "temporalBinding": trace.get("temporalBinding"),
                    "seconds": round(time.monotonic() - start, 2)}
        except Exception as exc:
            item = {"q": question, "before": old["tip"], "after": "EVALUATION_ERROR",
                    "errorType": type(exc).__name__, "seconds": round(time.monotonic() - start, 2)}
        out.append(item)
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(json.dumps({k: item.get(k) for k in ("q", "before", "after", "rows", "seconds")}, ensure_ascii=False), flush=True)
finally:
    if runtime.connector:
        runtime.connector.close()
