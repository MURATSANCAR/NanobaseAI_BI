"""Continuous paraphrase expansion from question grammar (no SQL rebuild)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from nanobase_api.scenario_engine.domain.scenario import (
    ScenarioParaphrase,
    normalize_question,
    question_hash,
)
from nanobase_api.scenario_engine.domain.status import ScenarioStatus
from nanobase_api.scenario_engine.infrastructure.question_grammar import (
    GRAMMAR_VERSION,
    generate_questions,
    supported_expand_families,
)
from nanobase_api.scenario_engine.infrastructure.store import ScenarioStore, get_scenario_store

_PERIOD_CUE_RE = re.compile(
    r"\b(bugun|dun|hafta|ay|yil|ceyrek|basindan|kadar|ait|bugunku|dunki|gecen)\b"
)


def purge_periodless_paraphrases_from_period_scenarios(
    *,
    tenant_id: str,
    datasource_id: str,
    store: ScenarioStore | None = None,
    families: set[str] | None = None,
) -> dict[str, Any]:
    """Remove bare phrases wrongly attached to period-scoped scenarios."""
    store = store or get_scenario_store()
    fam_filter = families or set(supported_expand_families())
    removed = 0
    scanned = 0
    for inst in store.list_instances(
        tenant_id=tenant_id, datasource_id=datasource_id, status=ScenarioStatus.PUBLISHED
    ):
        if inst.family not in fam_filter or not inst.logical_plan.period:
            continue
        for para in list(store.paraphrases_for_scenario(inst.id)):
            scanned += 1
            norm = normalize_question(para.text)
            if _PERIOD_CUE_RE.search(norm):
                continue
            with store._lock:
                store.paraphrases.pop(para.id, None)
            if store.sql_repo is not None:
                try:
                    from sqlalchemy import text

                    eng = getattr(store.sql_repo, "_engine", None)
                    if eng is not None:
                        with eng.begin() as conn:
                            conn.execute(
                                text("DELETE FROM sc_scenario_paraphrase WHERE id = :id"),
                                {"id": para.id},
                            )
                except Exception:
                    pass
            removed += 1
    return {
        "tenant_id": tenant_id,
        "datasource_id": datasource_id,
        "paraphrases_scanned": scanned,
        "paraphrases_removed": removed,
    }


def refresh_paraphrases_from_grammar(
    *,
    tenant_id: str,
    datasource_id: str,
    store: ScenarioStore | None = None,
    families: set[str] | None = None,
    limit_scenarios: int | None = None,
) -> dict[str, Any]:
    """Add missing grammar paraphrases for published scenarios.

    Idempotent by normalized question hash within the tenant/datasource.
    Does not mutate SQL / compilations — end-user surface language only.
    """
    store = store or get_scenario_store()
    fam_filter = families or set(supported_expand_families())
    instances = [
        i
        for i in store.list_instances(
            tenant_id=tenant_id, datasource_id=datasource_id, status=ScenarioStatus.PUBLISHED
        )
        if i.family in fam_filter
    ]
    if limit_scenarios is not None:
        instances = instances[: max(0, int(limit_scenarios))]

    existing_hashes: set[str] = set()
    for p in store.paraphrases.values():
        if p.tenant_id == tenant_id and p.datasource_id == datasource_id:
            existing_hashes.add(p.normalized_hash)

    added = 0
    scanned = 0
    touched_scenarios = 0
    family_added: dict[str, int] = {}
    for inst in instances:
        texts = generate_questions(inst.logical_plan, expand=True)
        scanned += len(texts)
        new_for_inst = 0
        for text in texts:
            h = question_hash(text)
            if h in existing_hashes:
                continue
            para = ScenarioParaphrase(
                id=f"par-{uuid.uuid4().hex[:12]}",
                scenario_id=inst.id,
                language="tr",
                text=text,
                status=ScenarioStatus.PUBLISHED,
                tenant_id=inst.tenant_id,
                datasource_id=inst.datasource_id,
            )
            store.save_paraphrase(para)
            existing_hashes.add(h)
            added += 1
            new_for_inst += 1
            family_added[inst.family] = family_added.get(inst.family, 0) + 1
        if new_for_inst:
            touched_scenarios += 1

    return {
        "tenant_id": tenant_id,
        "datasource_id": datasource_id,
        "grammarVersion": GRAMMAR_VERSION,
        "scenarios": len(instances),
        "touched_scenarios": touched_scenarios,
        "texts_scanned": scanned,
        "paraphrases_added": added,
        "by_family": family_added,
    }


def expand_paraphrases_continuous(
    *,
    tenant_id: str,
    datasource_id: str,
    store: ScenarioStore | None = None,
    families: set[str] | None = None,
    purge_periodless: bool = True,
) -> dict[str, Any]:
    """Purge drift + expand all end-user combinations for one datasource."""
    store = store or get_scenario_store()
    fam_filter = families or set(supported_expand_families())
    out: dict[str, Any] = {
        "grammarVersion": GRAMMAR_VERSION,
        "families": sorted(fam_filter),
    }
    if purge_periodless:
        out["purge"] = purge_periodless_paraphrases_from_period_scenarios(
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            store=store,
            families=fam_filter,
        )
    out["refresh"] = refresh_paraphrases_from_grammar(
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        store=store,
        families=fam_filter,
    )
    # Coverage snapshot after expand
    published = store.list_instances(
        tenant_id=tenant_id, datasource_id=datasource_id, status=ScenarioStatus.PUBLISHED
    )
    para_n = sum(
        1
        for p in store.paraphrases.values()
        if p.tenant_id == tenant_id
        and p.datasource_id == datasource_id
        and p.status == ScenarioStatus.PUBLISHED
    )
    out["coverage"] = {
        "published_scenarios": len(published),
        "published_paraphrases": para_n,
        "avg_paraphrases_per_scenario": round(para_n / max(1, len(published)), 1),
    }
    return out
