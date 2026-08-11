#!/usr/bin/env python3
"""Revalidate PUBLISHED scenarios against the CURRENT live schema.

Why: scenarios store SQL *templates* (executed fresh per question), so the
risk of an old build is not "serving old data" — it is schema drift: SQL
written against last month's schema silently failing (or worse, matching a
renamed column with different semantics) today. This tool proves each
published scenario's template still EXPLAINs cleanly against the live
database via the Query Gateway, and demotes the ones that don't:

    PUBLISHED --(schema error)--> STALE   (runtime immediately stops serving
                                           them: is_retrieval_eligible
                                           excludes STALE)

Failure taxonomy (deliberate — see the user requirement "eski olabilir"):
  - schema_error  → STALE (relation/column missing, parse failure: proven broken)
  - param_error   → reported, left as-is (canonical question no longer resolves
                    binds — needs human look, might be a resolver regression)
  - infra_error   → reported, left as-is (timeout/connection — proves nothing
                    about the scenario)

Usage (on the BI server, env sourced):
    set -a && source backend/nanobase_api.env && set +a
    backend/.venv/bin/python backend/scripts/revalidate_scenarios.py \
        --datasource erp [--tenant default] [--dry-run] [--concurrency 5]

After a non-dry run that staled anything: restart nanobase-bi-api (the
running workers hold the scenario store in memory; hydration happens at boot).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import re

_PLACEHOLDER = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")


def render_template(sql_template: str, params: dict[str, Any]) -> tuple[str, list[str]]:
    """Substitute :name binds with SQL literals for EXPLAIN-only validation.

    The gateway's EXPLAIN path rewrites :name → %(name)s but does not apply
    the parameters to the EXPLAIN cursor, so templated SQL can't be EXPLAINed
    through it as-is (first dry run failed 17/20 on exactly this — a tool
    artifact, not scenario staleness). Literal substitution is safe here:
    values come from resolve_parameters (dates/ints/enum strings we control),
    and the result is only ever EXPLAINed, never executed.
    Returns (rendered_sql, unresolved_placeholder_names).
    """
    unresolved: list[str] = []

    def _lit(name: str) -> str:
        if name not in params or params[name] is None:
            unresolved.append(name)
            return f":{name}"
        v = params[name]
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, (int, float)):
            return str(v)
        s = str(v).replace("'", "''")
        return f"'{s}'"

    rendered = _PLACEHOLDER.sub(lambda m: _lit(m.group(1)), sql_template)
    return rendered, unresolved


SCHEMA_ERROR_MARKERS = (
    "does not exist",
    "undefined table",
    "undefined column",
    "relation ",
    "column ",
    "syntax error",
    "table_or_view_not_found",
    "column_not_found",
    "sql_parse_failed",
    "not allowlisted",
)

INFRA_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "connection",
    "unavailable",
    "temporarily",
)


def classify_failure(message: str) -> str:
    low = (message or "").lower()
    if any(m in low for m in SCHEMA_ERROR_MARKERS):
        return "schema_error"
    if any(m in low for m in INFRA_ERROR_MARKERS):
        return "infra_error"
    return "other_error"


async def revalidate(
    *,
    tenant_id: str,
    datasource_id: str,
    dry_run: bool,
    concurrency: int,
    limit: int | None,
) -> int:
    from nanobase_api.infrastructure.query_gateway_client import QueryGatewayClient
    from nanobase_api.scenario_engine.application.param_resolver import resolve_parameters
    from nanobase_api.scenario_engine.domain.status import ScenarioStatus
    from nanobase_api.scenario_engine.infrastructure.compiler import get_compiler
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    store = get_scenario_store()
    published = [
        inst
        for inst in store.instances.values()
        if inst.tenant_id == tenant_id
        and inst.datasource_id == datasource_id
        and inst.status == ScenarioStatus.PUBLISHED
    ]
    published.sort(key=lambda i: i.scenario_code)
    if limit:
        published = published[:limit]
    print(f"→ {len(published)} PUBLISHED scenario(s) for {tenant_id}/{datasource_id}")
    if not published:
        return 0

    qg = QueryGatewayClient()
    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[dict[str, Any]] = []

    async def check(inst) -> None:
        async with sem:
            row: dict[str, Any] = {
                "id": inst.id,
                "code": inst.scenario_code,
                "family": str(inst.family),
                "question": (inst.canonical_question or "")[:120],
            }
            try:
                comp = store.get_compilation(inst.id, dialect="postgres")
                if comp is None:
                    compiled = get_compiler("postgres").compile(inst.logical_plan)
                    sql_template = compiled.sql_template
                else:
                    sql_template = comp.sql_template
                try:
                    params = resolve_parameters(
                        inst.canonical_question, inst.logical_plan
                    ).to_bind_dict()
                except Exception as pe:
                    row["verdict"] = "param_error"
                    row["detail"] = str(pe)[:200]
                    results.append(row)
                    return
                rendered, unresolved = render_template(sql_template, params or {})
                if unresolved:
                    row["verdict"] = "param_error"
                    row["detail"] = f"unresolved binds: {', '.join(unresolved[:6])}"
                    results.append(row)
                    return
                # EXPLAIN through the gateway = the same trust boundary the
                # runtime uses; catches missing tables/columns on the LIVE
                # schema without fetching data.
                res = await qg.execute(
                    sql=rendered,
                    datasource_id=datasource_id,
                    tenant_id=tenant_id,
                    explain=True,
                )
                if res.get("ok") or res.get("plan") or res.get("explain") or (
                    "rows" in res and res.get("http_status") is None and not res.get("code")
                ):
                    row["verdict"] = "ok"
                else:
                    msg = str(
                        res.get("message") or res.get("error") or res.get("detail") or res
                    )
                    row["verdict"] = classify_failure(msg)
                    row["detail"] = msg[:300]
            except Exception as e:  # noqa: BLE001 — a crashed check proves nothing
                row["verdict"] = "infra_error"
                row["detail"] = f"{type(e).__name__}: {str(e)[:200]}"
            results.append(row)
            done = len(results)
            if done % 50 == 0:
                print(f"  … {done}/{len(published)}")

    await asyncio.gather(*(check(i) for i in published))

    by_verdict = Counter(r["verdict"] for r in results)
    print("\n== Verdicts ==")
    for verdict, n in sorted(by_verdict.items()):
        print(f"  {verdict:14s} {n}")

    schema_failed = [r for r in results if r["verdict"] == "schema_error"]
    if schema_failed:
        print("\n== schema_error (will be STALE'd) — by family ==")
        for fam, n in Counter(r["family"] for r in schema_failed).most_common():
            print(f"  {fam:20s} {n}")
        print("\n== First 10 schema_error details ==")
        for r in schema_failed[:10]:
            print(f"  [{r['code']}] {r['question']}\n      {r.get('detail', '')[:200]}")

    for label in ("param_error", "other_error", "infra_error"):
        rows = [r for r in results if r["verdict"] == label]
        if rows:
            print(f"\n== {label} (NOT staled — needs human look) — first 5 ==")
            for r in rows[:5]:
                print(f"  [{r['code']}] {r.get('detail', '')[:160]}")

    if dry_run:
        print(f"\nDRY RUN — {len(schema_failed)} scenario(s) would be marked STALE.")
    else:
        staled = 0
        for r in schema_failed:
            inst = store.get_instance(r["id"])
            if inst is None:
                continue
            inst.transition_to(ScenarioStatus.STALE)
            store.save_instance(inst)
            staled += 1
        print(f"\nMarked STALE: {staled} — restart nanobase-bi-api to refresh runtime store.")

    out = Path(f"/tmp/scenario-revalidation-{datasource_id}.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Full report → {out}")
    return 0 if not schema_failed or dry_run else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--datasource", required=True)
    ap.add_argument("--tenant", default="default")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    return asyncio.run(
        revalidate(
            tenant_id=args.tenant,
            datasource_id=args.datasource,
            dry_run=args.dry_run,
            concurrency=args.concurrency,
            limit=args.limit,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
