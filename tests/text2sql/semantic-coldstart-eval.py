#!/usr/bin/env python3
"""Semantic Layer cold-start benchmark — 6 slices instead of one pass/fail number.

Offline (no LLM, no DB):
  PYTHONPATH=backend python3 tests/text2sql/semantic-coldstart-eval.py --store sqlite:////tmp/sl.db \
      --project deploy/wren-project/logo_timas --enum-probe artifacts/timas/apply-all.json --out /tmp/coldstart.json
With the bridge (recall OFF, executes SQL and compares with truth):
  ... --bridge http://127.0.0.1:8795 --truth artifacts/timas/complex-truth.json

Slices: schema / value / metric / temporal / sql / result. `sql` offline = deterministic compile succeeded
(or the question is expected to be ambiguous/unresolved); with --bridge = the bridge returned executable SQL.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.normalize import normalize_term  # noqa: E402
from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider  # noqa: E402
from semantic_layer.runtime.guardrails import referenced_tables  # noqa: E402
from semantic_layer.runtime.resolver import SemanticResolver  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def post(base: str, path: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def compare(rows: list[dict], truth: list[dict]) -> tuple[bool, str]:
    """Same rule as timas-copilot-eval: row count equal + numeric values of the first 10 truth rows present."""
    def nums(r):
        return [float(v) for v in r.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]

    def close(a, b, tol=0.005):
        if a == b:
            return True
        if b == 0:
            return abs(a) < 1e-6
        return abs(a - b) / max(abs(a), abs(b)) <= tol

    if len(rows) != len(truth):
        return False, f"satır sayısı {len(rows)} ≠ gerçek {len(truth)}"
    misses = checked = 0
    for t in truth[:10]:
        labels = {str(v).strip().lower() for v in t.values() if isinstance(v, str)}
        cand = [r for r in rows if labels and (labels & {str(v).strip().lower() for v in r.values() if isinstance(v, str)})] or rows[:1]
        rn = [x for r in cand for x in nums(r)]
        for tv in nums(t):
            if abs(tv) < 13:
                continue
            checked += 1
            if not any(close(rv, tv) or close(rv, tv * 100) or close(rv * 100, tv) for rv in rn):
                misses += 1
    if checked and misses / checked > 0.15:
        return False, f"sayısal uyumsuzluk {misses}/{checked}"
    return True, f"eşleşti ({checked} değer)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "tests/text2sql/semantic-coldstart-corpus.yaml"))
    ap.add_argument("--store", required=True)
    ap.add_argument("--project")
    ap.add_argument("--enum-probe")
    ap.add_argument("--datasource", default="logo")
    ap.add_argument("--tenant", default="default")
    ap.add_argument("--bridge", help="semantic bridge base URL (executes + compares)")
    ap.add_argument("--truth")
    ap.add_argument("--rebuild", action="store_true", help="run the offline pipeline first")
    ap.add_argument("--today", default="2026-09-06")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    s = SemanticSettings.from_env()
    s.store_dsn, s.tenant_id, s.datasource_id = a.store, a.tenant, a.datasource
    if a.project:
        s.project_dir = Path(a.project).resolve()
    store = open_store(s.store_dsn)
    if a.rebuild:
        from semantic_layer.pipeline import run_pipeline

        run_pipeline(store, s, enum_probe=Path(a.enum_probe) if a.enum_probe else None, note="bench rebuild")
    profiles = store.list_profiles(s.datasource_id)
    resolver = SemanticResolver(store, s.tenant_id, s.datasource_id, profiles)
    comp = DeterministicCompiler(profiles, s.context, s.dialect, default_filters=default_filters_provider(store, s.tenant_id, s.datasource_id))
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8")) if a.truth else {}
    today = date.fromisoformat(a.today)
    corpus = yaml.safe_load(Path(a.corpus).read_text(encoding="utf-8"))["questions"]
    slices = ["schema", "value", "metric", "temporal", "sql", "result"]
    totals = {k: [0, 0] for k in slices}
    results = []
    for c in corpus:
        t0 = time.time()
        sq = resolver.resolve(c["q"], today=today)
        det = comp.compile(sq, store)
        rec: dict = {"id": c["id"], "q": c["q"], "slices": {}, "unresolved": sq.unresolved, "deterministic": det is not None}
        slots = {(s_.mapping.entity if s_.mapping else None, (s_.mapping.column or "").upper() if s_.mapping else None, tuple(sorted(s_.mapping.values)) if s_.mapping else (), normalize_term(s_.term)) for s_ in sq.slots}
        # value slice
        if c.get("values"):
            ok = all(any(normalize_term(v["term"]) == n and col == v["column"].upper() and vals == tuple(sorted(v["values"])) for _, col, vals, n in slots) for v in c["values"])
            rec["slices"]["value"] = ok
        # metric slice
        if c.get("metric"):
            want = normalize_term(c["metric"])
            rec["slices"]["metric"] = any(s_.semantic_type == "METRIC" and (normalize_term(s_.term) == want or want in {normalize_term(x) for x in (store.get_concept(s_.concept_id).synonyms if s_.concept_id else [])} or normalize_term(store.get_concept(s_.concept_id).term) == want) for s_ in sq.slots if s_.concept_id)
        # temporal slice
        if c.get("temporal"):
            prims = [t.primitive for t in sq.temporal]
            ok = all(p in prims for p in c["temporal"])
            if c.get("grain"):
                ok = ok and sq.grain == c["grain"]
            if c.get("expect_ambiguous"):
                ok = ok and any(t.ambiguous for t in sq.temporal)
            rec["slices"]["temporal"] = ok
        # schema slice
        entities = set()
        if det is not None:
            for t in det.tables:
                from semantic_layer.naming import logical_table

                entities.add(logical_table(t).entity)
        for s_ in sq.slots:
            if s_.mapping:
                entities.add(s_.mapping.entity)
        if c.get("schema") is not None:
            rec["slices"]["schema"] = set(c["schema"]) <= entities
        if c.get("group_by"):
            rec["slices"]["value"] = rec["slices"].get("value", True) and any(normalize_term(g.term) == normalize_term(c["group_by"]) for g in sq.group_by)
        if c.get("expect_unresolved"):
            rec["slices"]["value"] = set(c["expect_unresolved"]) <= set(sq.unresolved)
        # sql slice
        bridge_sql = None
        if a.bridge:
            try:
                r = post(a.bridge, "/api/v1/ask", {"question": c["q"], "sampleSize": 100, "excludeNl": c["q"]}, 600)
                rec["bridge"] = {k: r.get(k) for k in ("type", "sql", "rowCount", "timings", "semantic")}
                bridge_sql = r.get("sql")
                rec["slices"]["sql"] = bool(bridge_sql) if not (c.get("expect_ambiguous") or c.get("expect_unresolved")) else True
                if c.get("truth") and bridge_sql and truth.get(c["truth"]):
                    rr = post(a.bridge, "/api/v1/run_sql", {"sql": bridge_sql, "limit": 200}, 300)
                    ok, why = compare(rr["records"], truth[c["truth"]])
                    rec["slices"]["result"] = ok
                    rec["why"] = why
            except Exception as e:  # noqa: BLE001
                rec["bridge_error"] = str(e)[:200]
                rec["slices"]["sql"] = False
        else:
            rec["slices"]["sql"] = det is not None or bool(c.get("expect_ambiguous") or c.get("expect_unresolved"))
            rec["sql"] = det.sql if det else None
        rec["wall_s"] = round(time.time() - t0, 2)
        for k, v in rec["slices"].items():
            totals[k][0] += int(bool(v))
            totals[k][1] += 1
        print("%-6s %s" % (c["id"], " ".join(f"{k}={'OK' if v else 'FAIL'}" for k, v in rec["slices"].items())), ("| unresolved: " + ",".join(sq.unresolved)) if sq.unresolved else "", flush=True)
        results.append(rec)
    summary = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "catalog_version": (store.latest_version(s.tenant_id, s.datasource_id) or {}).get("version"), "certified": store.status_counts(s.tenant_id, s.datasource_id).get("CERTIFIED"), "slices": {k: f"{v[0]}/{v[1]}" for k, v in totals.items() if v[1]}, "results": results}
    Path(a.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("SLICES:", summary["slices"], "→", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
