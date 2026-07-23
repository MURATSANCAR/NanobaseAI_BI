#!/usr/bin/env python3
"""Export every published scenario question with ≥50 end-user language combinations.

Output JSON:
  {
    "grammarVersion": "...",
    "minCombos": 50,
    "scenarios": [
      {
        "datasource": "erp",
        "scenarioCode": "...",
        "family": "COUNT_ENTITY",
        "canonical": "...",
        "comboCount": 120,
        "combinations": ["...", ...]  # at least minCombos
      },
      ...
    ]
  }
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    for cand in (
        Path(os.environ.get("NANOBASE_API_ENV", "")),
        backend / "nanobase_api.env",
        Path("/data/nanobaseai/bi/frontend/backend/nanobase_api.env"),
    ):
        if cand and str(cand) not in (".", ""):
            _load_env_file(cand)

    from nanobase_api.scenario_engine.domain.status import ScenarioStatus
    from nanobase_api.scenario_engine.infrastructure.question_grammar import (
        GRAMMAR_VERSION,
        MIN_USER_COMBOS,
        generate_questions,
    )
    from nanobase_api.scenario_engine.infrastructure.store import get_scenario_store

    min_combos = int(os.environ.get("EXPORT_MIN_COMBOS") or MIN_USER_COMBOS)
    # Cap stored list size for readability while guaranteeing ≥ min_combos
    list_cap = int(os.environ.get("EXPORT_COMBO_CAP") or max(min_combos, 50))
    sources = [
        p.strip()
        for p in (os.environ.get("SCENARIO_REBUILD_DATASOURCES") or "erp,sigorta").split(",")
        if p.strip()
    ]
    tenant_id = (os.environ.get("SCENARIO_REBUILD_TENANT") or "default").strip()
    out_path = Path(
        os.environ.get("EXPORT_PATH")
        or str(root / "artifacts" / "user-question-combinations.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    store = get_scenario_store()
    scenarios: list[dict] = []
    below = 0
    for ds in sources:
        for inst in store.list_instances(
            tenant_id=tenant_id, datasource_id=ds, status=ScenarioStatus.PUBLISHED
        ):
            combos = generate_questions(inst.logical_plan, expand=True, min_combos=min_combos)
            if len(combos) < min_combos:
                below += 1
            scenarios.append(
                {
                    "datasource": ds,
                    "scenarioCode": inst.scenario_code,
                    "family": inst.family,
                    "entity": inst.logical_plan.entity,
                    "period": inst.logical_plan.period,
                    "canonical": inst.canonical_question,
                    "comboCount": len(combos),
                    "combinations": combos[:list_cap],
                }
            )

    scenarios.sort(key=lambda r: (r["datasource"], r["family"], r["scenarioCode"]))
    payload = {
        "grammarVersion": GRAMMAR_VERSION,
        "minCombos": min_combos,
        "listedCombosPerScenario": list_cap,
        "datasourceCount": len(sources),
        "scenarioCount": len(scenarios),
        "belowMinCount": below,
        "totalListedCombinations": sum(len(s["combinations"]) for s in scenarios),
        "scenarios": scenarios,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    # Compact index for UI / canvas
    index_path = out_path.with_name("user-question-combinations.index.json")
    index = {
        "grammarVersion": GRAMMAR_VERSION,
        "minCombos": min_combos,
        "scenarioCount": len(scenarios),
        "belowMinCount": below,
        "items": [
            {
                "datasource": s["datasource"],
                "scenarioCode": s["scenarioCode"],
                "family": s["family"],
                "canonical": s["canonical"],
                "comboCount": s["comboCount"],
                "sample": s["combinations"][:50],
            }
            for s in scenarios
        ],
    }
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {out_path} scenarios={len(scenarios)} belowMin={below} "
        f"grammar={GRAMMAR_VERSION}",
        flush=True,
    )
    print(f"Wrote {index_path}", flush=True)
    return 1 if below else 0


if __name__ == "__main__":
    raise SystemExit(main())
