#!/usr/bin/env python3
"""Unified Text-to-SQL quality benchmark runner (target 1100 questions)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from common import ARTIFACTS, REPO_ROOT, ensure_artifacts, utc_now, write_json

TARGETS = {
    "structuredOutputValidity": 0.995,
    "unknownApprovedTable": 0,
    "unknownApprovedColumn": 0,
    "mandatoryFilterApplication": 1.0,
    "financialCurrencyCorrectness": 1.0,
    "sapLedgerCorrectness": 1.0,
    "sapReversalCorrectness": 1.0,
    "executionResultEquivalence": 0.95,
    "businessAnswerCorrectness": 0.96,
    "followUpContextAccuracy": 0.95,
    "requiredClarificationAccuracy": 0.95,
    "criticalFinancialCorrectness": 1.0,
}


def _count_yaml_questions(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    # count question: keys
    return len(re.findall(r"(?m)^\s*-?\s*question\s*:", text))


def _count_json_items(path: Path) -> int:
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return len(data)
    for key in ("questions", "cases", "metrics", "items", "results"):
        if isinstance(data.get(key), list):
            return len(data[key])
    return 0


def inventory() -> dict:
    t2s = REPO_ROOT / "tests" / "text2sql"
    arts7 = REPO_ROOT / "artifacts" / "phase-7"
    buckets = {
        "postgres": {
            "target": 300,
            "sources": [
                ("postgres-final-300", _count_yaml_questions(t2s / "postgres-final-300.yaml")),
                ("smoke", _count_yaml_questions(t2s / "smoke-questions.yaml")),
                ("erp-user", _count_yaml_questions(t2s / "erp-user-50.yaml")),
                ("semantic-benchmark", _count_json_items(arts7 / "semantic-benchmark-corpus.json")),
                ("verified-query", _count_json_items(arts7 / "verified-query-corpus.json")),
            ],
        },
        "oracle": {
            "target": 250,
            "sources": [("oracle-250", _count_yaml_questions(t2s / "oracle-250.yaml"))],
        },
        "sap": {
            "target": 400,
            "sources": [("sap-fi", _count_yaml_questions(t2s / "sap-fi-150.yaml"))],
        },
        "cross_system": {
            "target": 150,
            "sources": [
                ("cross-system-150", _count_yaml_questions(t2s / "cross-system-150.yaml")),
                ("cross-dialect", _count_json_items(t2s / "cross-dialect-100.json")),
            ],
        },
    }
    for b in buckets.values():
        # Prefer the largest single source (dedicated final corpus) to avoid double-count inflation
        counts = [c for _, c in b["sources"]]
        b["count"] = max(counts) if counts else 0
        b["allSourcesTotal"] = sum(counts)
        b["gap"] = max(0, b["target"] - b["count"])
    total = sum(b["count"] for b in buckets.values())
    return {"buckets": buckets, "total": total, "targetTotal": 1100, "gap": max(0, 1100 - total)}


def run_offline_eval(release: str) -> dict:
    """Structural offline eval: presence + skeleton validity (not live LLM)."""
    inv = inventory()
    # Inventory establishes no answer-quality measurement. Missing observations
    # must never inherit thresholds or historical scores as today's result.
    metric_scores = {name: None for name in TARGETS}
    failures = [f"{name}: UNKNOWN (live execution evidence required)" for name in TARGETS]

    # Vertical-slice mode: pass inventory gate when gap documented and postgres bucket strong
    offline_slice_pass = (
        inv["buckets"]["postgres"]["count"] >= 300
        and inv["buckets"]["oracle"]["count"] >= 250
    )
    # Full gate pass requires 1100 + metric targets
    full_pass = inv["gap"] == 0 and not failures

    return {
        "release": release,
        "generatedAt": utc_now(),
        "mode": "offline_inventory",
        "inventory": inv,
        "metrics": metric_scores,
        "targets": TARGETS,
        "failures": failures,
        "offlineVerticalSlicePass": offline_slice_pass,
        "fullPass": full_pass,
        "pass": offline_slice_pass,
        "note": "Inventory only; all answer metrics UNKNOWN until measured by a live evaluator",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", default="1.0.0-rc.1")
    parser.add_argument('--live-evidence', type=Path, help='Measured cases with hashed response/reference artifacts')
    parser.add_argument(
        "--require-full",
        action="store_true",
        help="Fail unless 1100 questions and metric targets met",
    )
    args = parser.parse_args(argv)
    ensure_artifacts()
    result = run_offline_eval(args.release)
    if args.live_evidence:
        result = evaluate_live_evidence(args.live_evidence, args.release, result)
    if args.require_full:
        result["pass"] = bool(result.get("fullPass"))
    write_json(ARTIFACTS / "text2sql-quality-results.json", result)
    print(
        json.dumps(
            {
                "total": result["inventory"]["total"],
                "gap": result["inventory"]["gap"],
                "pass": result["pass"],
                "offlineVerticalSlicePass": result["offlineVerticalSlicePass"],
            },
            indent=2,
        )
    )
    if args.require_full:
        return 0 if result["pass"] else 1
    return 0 if result["offlineVerticalSlicePass"] else 1


def evaluate_live_evidence(path, release, result):
    """No inferred scores: only explicitly assessed, traceable cases contribute."""
    evidence = json.loads(path.read_text())
    errors = []
    if evidence.get('release') != release or evidence.get('mode') != 'live':
        errors.append('Evidence release/mode mismatch')
    for key in ('codeRevision', 'catalogHash', 'datasource', 'generatedAt'):
        if not evidence.get(key):
            errors.append(f'Missing evidence provenance: {key}')
    assessed = {k: [] for k in TARGETS}
    seen = set()
    valid_cases = set()
    for case in evidence.get('cases', []):
        if not case.get('id') or case['id'] in seen or not case.get('question'):
            errors.append('Missing/duplicate case identity')
        seen.add(case.get('id'))
        valid = True
        for kind in ('response', 'reference'):
            artifact = case.get(kind, {})
            target = (path.parent / artifact.get('path', '')).resolve()
            if (not target.is_relative_to(path.parent.resolve()) or not target.is_file()
                    or hashlib.sha256(target.read_bytes()).hexdigest() != artifact.get('sha256')):
                errors.append(f"{case.get('id')}: {kind} evidence missing or changed")
                valid = False
        if valid and case.get('id') and case.get('question'):
            valid_cases.add(case['id'])
            for metric, value in case.get('checks', {}).items():
                if metric not in assessed or not isinstance(value, bool):
                    errors.append(f'Invalid assessment {metric}')
                else:
                    assessed[metric].append(value)
    if len(valid_cases) < result['inventory']['targetTotal']:
        errors.append(f"Measured case gap: {len(valid_cases)}/{result['inventory']['targetTotal']}")
    metrics = {k: (None if not values else (sum(not v for v in values) if TARGETS[k] == 0
                 else sum(values) / len(values))) for k, values in assessed.items()}
    for key, target in TARGETS.items():
        value = metrics[key]
        if value is None or (value != 0 if target == 0 else value < target):
            errors.append(f'{key}: {value if value is not None else "UNKNOWN"}; target={target}')
    result.update(mode='live_evidence', metrics=metrics, validCaseCount=len(valid_cases), measuredCases={k: len(v) for k,v in assessed.items()},
                  failures=errors, fullPass=not errors and result['inventory']['gap'] == 0)
    return result


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
