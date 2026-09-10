#!/usr/bin/env python3
"""Compiler A/B — the same SemanticQuery through every compiler, scored on the same corpus.

One resolver run per question (so the semantic layer is held constant), then each compiler produces
SQL that is guardrail-checked, optionally executed and compared with the recorded truth. The report
is a matrix, not a single number: compiled / executable / correct / latency / certified.

  # offline, deterministic only (no service needed)
  PYTHONPATH=backend python3 tests/text2sql/compiler-ab-eval.py --store sqlite:///catalog.db \
      --compilers deterministic --out /tmp/ab.json

  # full A/B against the running bridge (executes SQL) and a SuperSonic deployment
  SUPERSONIC_BASE=http://127.0.0.1:9080 SUPERSONIC_DATASETS=INVOICE=7,STLINE=8 \
  PYTHONPATH=backend python3 tests/text2sql/compiler-ab-eval.py --store "$NANOBASE_META_DSN" \
      --compilers deterministic,existing_llm,supersonic --bridge http://127.0.0.1:8795 \
      --truth artifacts/timas/complex-truth.json --out artifacts/timas/compiler-ab.json

Promotion gate: a challenger replaces the incumbent only when it is at least as correct and either
strictly more correct or materially faster; the script prints the verdict and exits 0 either way.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.runtime.compiler import DeterministicCompiler, ExistingCompiler, default_filters_provider  # noqa: E402
from semantic_layer.runtime.guardrails import validate_sql  # noqa: E402
from semantic_layer.runtime.resolver import SemanticResolver  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

LATENCY_EDGE = 0.20    # a challenger must be ≥20 % faster to win on speed alone
LATENCY_FLOOR_MS = 50  # below this the incumbent is already instant: speed cannot decide


def post(base: str, path: str, body: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def compare(rows: list[dict], truth: list[dict]) -> tuple[bool, str]:
    def nums(r):
        return [float(v) for v in r.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]

    def close(a, b, tol=0.005):
        if a == b:
            return True
        if b == 0:
            return abs(a) < 1e-6
        return abs(a - b) / max(abs(a), abs(b)) <= tol

    if len(rows) != len(truth):
        return False, f"satır sayısı {len(rows)} ≠ {len(truth)}"
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


def build_compilers(names: list[str], store, settings, profiles, conventions):
    out: dict[str, object] = {}
    for name in names:
        if name == "deterministic":
            out[name] = DeterministicCompiler(profiles, settings.context, settings.dialect or "tsql", default_filters=default_filters_provider(store, settings.tenant_id, settings.datasource_id), conventions=conventions)
        elif name in ("existing_llm", "existing"):
            from semantic_layer.candidates.llm_client import LlmClient

            llm = LlmClient(settings.llm_base, settings.llm_model, settings.llm_key, settings.llm_timeout)
            rules = ""
            if settings.project_dir and (settings.project_dir / "knowledge").exists():
                rules = "\n\n".join(f.read_text(encoding="utf-8") for f in sorted((settings.project_dir / "knowledge").rglob("*.md")) if f.parent.name != "sql")
            out["existing_llm"] = ExistingCompiler(llm, profiles, settings.context, rules_text=rules, dialect=settings.dialect or "tsql", conventions=conventions)
        elif name == "supersonic":
            from semantic_layer.runtime.supersonic import build_adapter

            adapter = build_adapter()
            if adapter is None:
                print("supersonic: SUPERSONIC_BASE tanımlı değil — atlanıyor", file=sys.stderr)
                continue
            out[name] = adapter
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ap.add_argument("--corpus", default=str(ROOT / "tests/text2sql/semantic-coldstart-corpus.yaml"))
    ap.add_argument("--truth")
    ap.add_argument("--project")
    ap.add_argument("--datasource", default="")
    ap.add_argument("--tenant", default="")
    ap.add_argument("--compilers", default="deterministic")
    ap.add_argument("--bridge", help="execute the SQL through the semantic bridge")
    ap.add_argument("--baseline", default="deterministic", help="incumbent compiler for the promotion gate")
    ap.add_argument("--today", default=str(date.today()))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    settings = SemanticSettings.from_env()
    settings.store_dsn = a.store
    if a.datasource:
        settings.datasource_id = a.datasource
    if a.tenant:
        settings.tenant_id = a.tenant
    if a.project:
        settings.project_dir = Path(a.project).resolve()
    store = open_store(settings.store_dsn)
    profiles = store.list_profiles(settings.datasource_id)
    if not profiles:
        print(f"katalogda profil yok (datasource={settings.datasource_id}) — önce pipeline çalıştırın", file=sys.stderr)
        return 2
    from semantic_layer.conventions import Conventions

    conventions = Conventions.from_profiles(profiles)
    resolver = SemanticResolver(store, settings.tenant_id, settings.datasource_id, profiles, conventions=conventions)
    compilers = build_compilers([c.strip() for c in a.compilers.split(",") if c.strip()], store, settings, profiles, conventions)
    if not compilers:
        print("çalıştırılacak derleyici yok", file=sys.stderr)
        return 2
    truth = json.loads(Path(a.truth).read_text(encoding="utf-8")) if a.truth else {}
    corpus = yaml.safe_load(Path(a.corpus).read_text(encoding="utf-8"))["questions"]
    today = date.fromisoformat(a.today)

    per_compiler: dict[str, dict[str, list]] = {name: {"compiled": [], "executable": [], "correct": [], "latency": [], "certified": [], "behaved": []} for name in compilers}
    results = []
    for item in corpus:
        q = resolver.resolve(item["q"], today=today)
        # A question the corpus marks as ambiguous/unresolved is answered correctly by *refusing*.
        refusal_expected = bool(item.get("expect_ambiguous") or item.get("expect_unresolved"))
        rec = {"id": item["id"], "q": item["q"], "unresolved": q.unresolved, "conflicts": q.conflicts, "refusalExpected": refusal_expected, "compilers": {}}
        for name, comp in compilers.items():
            t0 = time.perf_counter()
            try:
                out = comp.compile(q, store)
            except Exception as e:  # noqa: BLE001
                out = None
                rec["compilers"][name] = {"error": str(e)[:200]}
            ms = int((time.perf_counter() - t0) * 1000)
            entry = rec["compilers"].setdefault(name, {})
            sql = (out.sql if out else "") or ""
            entry.update({"sql": sql, "ms": ms, "certified": bool(out and out.certified), "explain": (out.explain if out else ["compiler returned None"])[:3]})
            per_compiler[name]["compiled"].append(bool(sql))
            per_compiler[name]["behaved"].append(not bool(sql) if refusal_expected else bool(sql))
            per_compiler[name]["latency"].append(ms)
            per_compiler[name]["certified"].append(bool(out and out.certified))
            if not sql:
                continue
            ok, why = validate_sql(sql)
            entry["guardrail"] = why
            if not ok:
                per_compiler[name]["executable"].append(False)
                continue
            if a.bridge:
                try:
                    run = post(a.bridge, "/api/v1/run_sql", {"sql": sql, "limit": 200})
                    entry["rowCount"] = run.get("totalRows")
                    per_compiler[name]["executable"].append(True)
                    if item.get("truth") and truth.get(item["truth"]):
                        match, why = compare(run["records"], truth[item["truth"]])
                        entry["result"] = {"match": match, "why": why}
                        per_compiler[name]["correct"].append(match)
                except Exception as e:  # noqa: BLE001
                    entry["run_error"] = str(e)[:200]
                    per_compiler[name]["executable"].append(False)
            else:
                per_compiler[name]["executable"].append(True)
        line = " | ".join(f"{n}: {'SQL' if rec['compilers'][n].get('sql') else '—':>3} {rec['compilers'][n].get('ms', 0):>5}ms" + ("" if "result" not in rec["compilers"][n] else (" OK" if rec["compilers"][n]["result"]["match"] else " YANLIŞ")) for n in compilers)
        print(f"{item['id']:<6} {line}", flush=True)
        results.append(rec)

    def ratio(values: list[bool]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    summary = {}
    for name, m in per_compiler.items():
        summary[name] = {
            "compiled": f"{sum(m['compiled'])}/{len(m['compiled'])}",
            "compiled_ratio": ratio(m["compiled"]),
            "behaviour": f"{sum(m['behaved'])}/{len(m['behaved'])}",   # SQL where expected, refusal where expected
            "behaviour_ratio": ratio(m["behaved"]),
            "executable_ratio": ratio(m["executable"]),
            "result_correct": f"{sum(m['correct'])}/{len(m['correct'])}" if m["correct"] else "n/a",
            "result_ratio": ratio(m["correct"]) if m["correct"] else None,
            "certified_ratio": ratio(m["certified"]),
            "latency_ms_mean": int(statistics.fmean(m["latency"])) if m["latency"] else 0,
            "latency_ms_median": int(statistics.median(m["latency"])) if m["latency"] else 0,
        }

    verdict = {"baseline": a.baseline, "promote": None, "reason": "tek derleyici koşuldu" if len(compilers) < 2 else ""}
    base = summary.get(a.baseline)
    if base and len(compilers) > 1:
        for name, s in summary.items():
            if name == a.baseline:
                continue
            base_acc = base["result_ratio"] if base["result_ratio"] is not None else base["behaviour_ratio"]
            cand_acc = s["result_ratio"] if s["result_ratio"] is not None else s["behaviour_ratio"]
            faster = base["latency_ms_median"] > LATENCY_FLOOR_MS and s["latency_ms_median"] <= base["latency_ms_median"] * (1 - LATENCY_EDGE)
            if cand_acc > base_acc or (cand_acc >= base_acc and faster):
                verdict = {"baseline": a.baseline, "promote": name, "reason": f"{name} doğruluk {cand_acc} ≥ {base_acc}" + (" ve belirgin daha hızlı" if faster else " ve daha doğru")}
                break
        else:
            verdict["reason"] = "hiçbir aday eşiği geçmedi — mevcut derleyici kalır"

    report = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "datasource": settings.datasource_id, "catalog_version": (store.latest_version(settings.tenant_id, settings.datasource_id) or {}).get("version"), "compilers": list(compilers), "summary": summary, "verdict": verdict, "results": results}
    Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\nSUMMARY:", json.dumps(summary, ensure_ascii=False))
    print("VERDICT:", json.dumps(verdict, ensure_ascii=False), "→", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
