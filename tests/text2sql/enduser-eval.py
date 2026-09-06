#!/usr/bin/env python3
"""End-user realism suite: 50 questions phrased by someone who does not know the schema.

Its purpose is not a score — it is a gap report. Every question is classified by what the system
actually did (answered from the catalog, answered with the model, refused, errored), compared with what
should have happened, and every term the resolver could not place is collected and ranked. That ranked
list is the work queue for the catalog: the terms real users say that the semantics do not cover yet.

  offline (no service, no model):
    PYTHONPATH=backend python3 tests/text2sql/enduser-eval.py --store <dsn> --out artifacts/enduser.json
  against a running bridge (executes SQL, uses the model for catalog misses):
    ... --bridge http://127.0.0.1:8795
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.conventions import Conventions  # noqa: E402
from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider  # noqa: E402
from semantic_layer.runtime.resolver import SemanticResolver  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

# What the system did, in the user's terms.
ANSWERED_CATALOG = "katalogdan"       # deterministic SQL, no model involved
ANSWERED_MODEL = "modelden"           # the model wrote the SQL, constrained by certified facts
REFUSED = "reddetti"
ERROR = "hata"


def post(base: str, path: str, body: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def verdict(expected: str, outcome: str) -> str:
    """Did the system behave the way a careful analyst would?"""
    if expected == "answer":
        return "OK" if outcome in (ANSWERED_CATALOG, ANSWERED_MODEL) else "EKSİK"
    if expected in ("refuse", "clarify"):
        return "OK" if outcome == REFUSED else "RİSK"      # answering an unanswerable question is the risk
    return "?"


def gate(summary: dict, baseline_path: str | None) -> list[str]:
    """What got worse since the last run against this corpus.

    A catalog changes every night, and a change that fixes one term can quietly break another: a new
    sense splits an old mapping, a certification is withdrawn, a synonym starts winning. Only two
    things count as a regression, and both are things a user would notice: a question that used to be
    answered and now is not, and a question that used to be refused and is now answered — the second
    matters more, because an answer nobody can tell is wrong is worse than a refusal.
    """
    if not baseline_path or not Path(baseline_path).exists():
        return []
    try:
        old = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"önceki rapor okunamadı ({e}); karşılaştırma yapılamadı"]
    before = {r["id"]: r for r in old.get("results", [])}
    out: list[str] = []
    for r in summary["results"]:
        was = before.get(r["id"])
        if not was:
            continue
        answered_before = was["outcome"] in (ANSWERED_CATALOG, ANSWERED_MODEL)
        answered_now = r["outcome"] in (ANSWERED_CATALOG, ANSWERED_MODEL)
        if answered_before and not answered_now:
            if was["verdict"] == "RİSK":
                continue      # it used to answer a question it should not have; refusing it is the fix
            out.append(f"{r['id']} artık cevaplanmıyor ({r.get('why') or r['outcome']}): {r['q'][:70]}")
        elif was["verdict"] == "OK" and r["verdict"] == "RİSK":
            out.append(f"{r['id']} cevaplanmaması gereken soruyu cevapladı: {r['q'][:70]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=str(ROOT / "tests/text2sql/enduser-50.yaml"))
    ap.add_argument("--store", required=True)
    ap.add_argument("--datasource", default="")
    ap.add_argument("--tenant", default="")
    ap.add_argument("--bridge")
    ap.add_argument("--today", default=str(date.today()))
    ap.add_argument("--out", required=True)
    ap.add_argument("--baseline", help="previous run's JSON; the gate compares against it")
    ap.add_argument("--gate", action="store_true", help="exit non-zero when the catalog regressed")
    a = ap.parse_args()

    s = SemanticSettings.from_env()
    s.store_dsn = a.store
    if a.datasource:
        s.datasource_id = a.datasource
    if a.tenant:
        s.tenant_id = a.tenant
    store = open_store(s.store_dsn)
    profiles = store.list_profiles(s.datasource_id)
    if not profiles:
        print(f"katalogda profil yok (datasource={s.datasource_id})", file=sys.stderr)
        return 2
    conventions = Conventions.from_profiles(profiles)
    resolver = SemanticResolver(store, s.tenant_id, s.datasource_id, profiles, conventions=conventions)
    compiler = DeterministicCompiler(profiles, s.context, s.dialect or "tsql", default_filters=default_filters_provider(store, s.tenant_id, s.datasource_id), conventions=conventions)
    today = date.fromisoformat(a.today)
    corpus = yaml.safe_load(Path(a.corpus).read_text(encoding="utf-8"))["questions"]

    # A term is only work for the catalog when it blocked a question that should have been answered;
    # the same word inside a question the system is right to refuse is not a gap.
    actionable: Counter[str] = Counter()
    out_of_domain: Counter[str] = Counter()
    qualifiers: Counter[str] = Counter()
    asked_by: dict[str, list[str]] = {}
    results = []
    for item in corpus:
        t0 = time.time()
        sq = resolver.resolve(item["q"], today=today)
        (actionable if item["expect"] == "answer" else out_of_domain).update(sq.unresolved)
        qualifiers.update(sq.unhandled)
        for term in sq.unresolved + sq.unhandled:
            asked_by.setdefault(term, []).append(item["id"])
        rec = {
            "id": item["id"], "q": item["q"], "expect": item["expect"], "note": item.get("note"),
            "resolved": [{"term": x.term, "type": x.semantic_type, "status": x.status} for x in sq.slots],
            "unresolved": sq.unresolved, "unhandled": sq.unhandled, "ignored": sq.ignored, "conflicts": sq.conflicts,
            "temporal": [{"primitive": t.primitive, "ambiguous": t.ambiguous} for t in sq.temporal],
        }
        compiled = compiler.compile(sq, store)
        if a.bridge:
            try:
                r = post(a.bridge, "/api/v1/ask", {"question": item["q"], "sampleSize": 20})
                rec["bridge"] = {k: r.get(k) for k in ("type", "sql", "rowCount", "summary", "timings")}
                sem = r.get("semantic") or {}
                if r.get("type") == "TEXT_TO_SQL":
                    outcome = ANSWERED_CATALOG if sem.get("compiler") == "deterministic" else ANSWERED_MODEL
                elif r.get("type") in ("NON_SQL_QUERY", "SQL_INVALID"):
                    outcome = REFUSED
                    rec["why"] = str(r.get("explanation"))[:300]
                else:
                    outcome = ERROR
            except urllib.error.HTTPError as e:
                outcome, rec["why"] = ERROR, f"HTTP {e.code}"
            except Exception as e:  # noqa: BLE001
                outcome, rec["why"] = ERROR, str(e)[:200]
        else:
            outcome = ANSWERED_CATALOG if compiled is not None else REFUSED
            rec["sql"] = compiled.sql if compiled else None
            if compiled is None:
                rec["why"] = compiler.plan(sq)[1]
        rec["outcome"] = outcome
        rec["verdict"] = verdict(item["expect"], outcome)
        rec["wall_s"] = round(time.time() - t0, 2)
        print(f"{item['id']:4} {rec['verdict']:5} {outcome:10} {item['q'][:58]:60} {('· ' + ', '.join(sq.unresolved[:4])) if sq.unresolved else ''}", flush=True)
        results.append(rec)

    # Scope safety can only be judged where the window was actually measured; say so rather than
    # letting a deployment that never measured one look safe.
    # only entities anyone actually asks about: a table nothing references and nothing is certified on
    # has no window and needs none, and listing 275 of them would bury the ones that matter
    used = {m.entity for senses in store.certified_index(s.tenant_id, s.datasource_id).values()
            for _, maps in senses for m in maps}
    unmeasured = [p.entity for p in profiles if p.time_window is None and p.entity in used]
    counts = Counter(r["verdict"] for r in results)
    by_outcome = Counter(r["outcome"] for r in results)
    risky = [r for r in results if r["verdict"] == "RİSK"]
    summary = {
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": "bridge" if a.bridge else "offline",
        "catalog_version": (store.latest_version(s.tenant_id, s.datasource_id) or {}).get("version"),
        "verdicts": dict(counts),
        "outcomes": dict(by_outcome),
        "risky": [{"id": r["id"], "q": r["q"], "outcome": r["outcome"]} for r in risky],
        # the portal work queue: terms real users said, that stopped an answerable question
        "catalog_gaps": [{"term": t, "count": n, "questions": asked_by.get(t, [])} for t, n in actionable.most_common(40)],
        "unhandled_qualifiers": [{"term": t, "count": n, "questions": asked_by.get(t, [])} for t, n in qualifiers.most_common(20)],
        "out_of_domain_terms": out_of_domain.most_common(20),
        "unmeasured_windows": unmeasured,
        "results": results,
    }
    Path(a.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    regressions = gate(summary, a.baseline)
    print("\nVERDICTS:", dict(counts), "| OUTCOMES:", dict(by_outcome))
    print("PORTALDE TANIMLANMASI GEREKENLER:", ", ".join(f"{t}({','.join(asked_by[t])})" for t, _ in actionable.most_common(15)) or "(yok)")
    print("KARŞILANAMAYAN NİTELEYİCİLER:", ", ".join(f"{t}×{n}" for t, n in qualifiers.most_common(10)) or "(yok)")
    print("KAPSAM DIŞI (doğru reddedildi):", ", ".join(t for t, _ in out_of_domain.most_common(12)) or "(yok)")
    if unmeasured:
        print("UYARI: zaman penceresi ölçülmemiş varlıklar (kapsam kontrolü devre dışı):", ", ".join(unmeasured))
    print("→", a.out)
    if regressions:
        print("\nGERİLEME (katalog bu soruları eskiden daha iyi cevaplıyordu):")
        for line in regressions:
            print("  -", line)
        if a.gate:
            return 1
    elif a.baseline:
        print("gerileme yok — bu katalog sürümü öncekinden geri değil")
    return 0


if __name__ == "__main__":
    sys.exit(main())
