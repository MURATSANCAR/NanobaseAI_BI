#!/usr/bin/env python3
"""Convert a legacy WrenAI (v1-final / GenBI Classic) deployment into a WrenAI main-line project (schema_version 5).

Inputs (exported from the legacy wren-ui sqlite: deploy_log.manifest, instruction, sql_pair):
  --mdl        mdl-legacy.json        (camelCase manifest: models/columns/relationships)
  --knowledge  knowledge-legacy.json  ({"instructions": [...], "sql_pairs": [...]})
Output: a project directory with wren_project.yml, models/<name>/metadata.yml, relationships.yml,
        knowledge/rules/*.md, knowledge/sql/*.md, knowledge/knowledge.yml  →  `wren context build`.

No column pruning: every column of every model is carried over (user decision, 2026-09-06).
Strings are emitted as JSON literals, which are valid YAML double-quoted scalars (no PyYAML needed).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def q(v: object) -> str:
    return json.dumps(v, ensure_ascii=False)


def slug(s: str, n: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower().replace("ı", "i").replace("ş", "s").replace("ğ", "g").replace("ç", "c").replace("ö", "o").replace("ü", "u")).strip("-")
    return s[:n] or "pair"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def convert(mdl: dict, knowledge: dict, out: Path, *, name: str, data_source: str, profile: str | None) -> dict:
    stats = {"models": 0, "columns": 0, "relationships": 0, "rules": 0, "sql_pairs": 0}
    # --- wren_project.yml
    lines = ["schema_version: 5", f"name: {q(name)}", 'version: "1.0"', f"catalog: {q(mdl.get('catalog') or 'wren')}", f"schema: {q(mdl.get('schema') or 'public')}", f"data_source: {data_source}"]
    if profile:
        lines.append(f"profile: {profile}")
    write(out / "wren_project.yml", "\n".join(lines) + "\n")

    # --- models
    rel_names = {r["name"] for r in mdl.get("relationships", [])}
    for m in mdl.get("models", []):
        tr = m.get("tableReference") or {}
        y = [f"name: {q(m['name'])}"]
        if m.get("refSql"):
            y.append("ref_sql: |")
            y += ["  " + ln for ln in str(m["refSql"]).splitlines()]
        else:
            y.append("table_reference:")
            if tr.get("catalog"):
                y.append(f"  catalog: {q(tr['catalog'])}")
            if tr.get("schema"):
                y.append(f"  schema: {q(tr['schema'])}")
            y.append(f"  table: {q(tr.get('table') or m['name'])}")
        if m.get("primaryKey"):
            y.append(f"primary_key: {q(m['primaryKey'])}")
        desc = (m.get("properties") or {}).get("description") or (m.get("properties") or {}).get("displayName")
        props = {k: v for k, v in (m.get("properties") or {}).items() if v not in (None, "")}
        if props:
            y.append("properties:")
            for k, v in props.items():
                y.append(f"  {q(k)}: {q(str(v))}")
        y.append("columns:")
        for c in m.get("columns", []):
            if c.get("relationship"):
                # relationship handle column → keep only if the relationship survives
                if c["relationship"] not in rel_names:
                    continue
                y.append(f"  - name: {q(c['name'])}")
                y.append(f"    type: {q(c['type'])}")
                y.append(f"    relationship: {q(c['relationship'])}")
                continue
            y.append(f"  - name: {q(c['name'])}")
            y.append(f"    type: {q(c.get('type') or 'VARCHAR')}")
            if c.get("isCalculated"):
                y.append("    is_calculated: true")
            if c.get("expression"):
                y.append(f"    expression: {q(c['expression'])}")
            if c.get("notNull"):
                y.append("    not_null: true")
            if m.get("primaryKey") and c["name"] == m["primaryKey"]:
                y.append("    is_primary_key: true")
            cprops = {k: v for k, v in (c.get("properties") or {}).items() if v not in (None, "")}
            if cprops:
                y.append("    properties:")
                for k, v in cprops.items():
                    y.append(f"      {q(k)}: {q(str(v))}")
            stats["columns"] += 1
        write(out / "models" / m["name"] / "metadata.yml", "\n".join(y) + "\n")
        stats["models"] += 1

    # --- relationships.yml
    y = ["relationships:"]
    for r in mdl.get("relationships", []):
        y.append(f"  - name: {q(r['name'])}")
        y.append("    models:")
        for mm in r["models"]:
            y.append(f"      - {q(mm)}")
        y.append(f"    join_type: {r['joinType']}")
        # legacy condition quotes model names: "dbo_X".COL = "dbo_Y".COL → keep as-is (valid SQL equality)
        y.append(f"    condition: {q(r['condition'])}")
        stats["relationships"] += 1
    write(out / "relationships.yml", "\n".join(y) + "\n")

    # --- knowledge
    write(out / "knowledge" / "knowledge.yml", "schema_version: 1\n")
    rules = ["# Logo ERP iş kuralları (legacy WrenAI instructions'tan taşındı)", ""]
    for i, ins in enumerate(knowledge.get("instructions", []), start=1):
        text = str(ins.get("instruction") or "").strip()
        if not text:
            continue
        qs = ins.get("questions")
        if isinstance(qs, str):
            try:
                qs = json.loads(qs)
            except Exception:  # noqa: BLE001
                qs = [qs]
        rules.append(f"## Kural {i}")
        rules.append(text)
        if qs:
            rules.append("")
            rules.append("Örnek sorular: " + "; ".join(str(x) for x in qs))
        rules.append("")
        stats["rules"] += 1
    write(out / "knowledge" / "rules" / "logo-erp.md", "\n".join(rules).rstrip() + "\n")
    for pair in knowledge.get("sql_pairs", []):
        nl = str(pair.get("question") or "").strip()
        sql = str(pair.get("sql") or "").strip()
        if not nl or not sql:
            continue
        body = ["---", f"nl: {q(nl)}", "sql: |"] + ["  " + ln for ln in sql.splitlines()] + ["source: legacy-wren-ui", f"datasource: {profile or data_source}", "---", ""]
        write(out / "knowledge" / "sql" / f"{slug(nl)}.md", "\n".join(body))
        stats["sql_pairs"] += 1
    write(out / ".gitignore", "target/\n.wren/\n")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mdl", required=True)
    ap.add_argument("--knowledge", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default="logo_timas")
    ap.add_argument("--data-source", default="mssql")
    ap.add_argument("--profile", default=None)
    a = ap.parse_args()
    mdl = json.load(open(a.mdl, encoding="utf-8"))
    kn = json.load(open(a.knowledge, encoding="utf-8"))
    stats = convert(mdl, kn, Path(a.out), name=a.name, data_source=a.data_source, profile=a.profile)
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
