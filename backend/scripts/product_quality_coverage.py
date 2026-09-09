"""Grounded critical-column coverage; never infer a business meaning from a name."""
import json
import re
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.profiler import logo_dictionary


def assess(store, tenant, datasource, sqls=()):
    profiles = one_entity_per_pattern(store.list_profiles(datasource), store.concept_entities(tenant, datasource))
    by_entity = {}
    for profile in profiles:
        by_entity.setdefault(profile.entity, []).append(profile)
    required = set()
    meanings = {}
    for pairs in store.certified_index(tenant, datasource).values():
        for concept, mappings in pairs:
            for m in mappings:
                if m.column:
                    required.add((m.entity, m.column.upper()))
                    meanings.setdefault((m.entity, m.column.upper()), set()).add(concept.term)
                for text in [m.formula or '', *((m.extra or {}).get('conditions') or [])]:
                    required.update((e, c.upper()) for e,c in re.findall(r'\b([A-Z][A-Z0-9_]*)\.\[?([A-Z][A-Z0-9_]*)', text))
    # Include actual query joins and date predicates, which need not be concepts themselves.
    from sqlglot import exp, parse_one
    tables = {p.table_name.upper(): p.entity for p in profiles}
    tables.update({p.entity.upper(): p.entity for p in profiles})
    for sql in sqls:
        tree = parse_one(sql, read='tsql')
        aliases = {t.alias_or_name.upper(): tables[t.name.upper()] for t in tree.find_all(exp.Table)
                   if t.name.upper() in tables}
        for col in tree.find_all(exp.Column):
            entity = aliases.get(col.table.upper())
            if entity:
                required.add((entity, col.name.upper()))
    rows = []
    for entity, column in sorted(required):
        candidates = by_entity.get(entity, [])
        observed = [(p, p.column(column)) for p in candidates if p.column(column)]
        docs = sorted({c.description for _,c in observed if c.description} |
                      {logo_dictionary.column_description(p.table_name,column) for p,_ in observed})
        docs = [d for d in docs if d]
        rows.append({'entity':entity,'column':column,'physicalTables':len(observed),
                     'status':'MISSING_SCHEMA' if not observed else 'DEFINED' if docs or meanings.get((entity,column)) else 'NEEDS_SOURCE',
                     'descriptions':docs,'certifiedTerms':sorted(meanings.get((entity,column),set()))})
    return {'scope':'Certified mappings, metric conditions and supplied real query columns; not the entire ERP',
            'requiredColumns':len(rows),'unresolved':sum(r['status']!='DEFINED' for r in rows),'columns':rows}


if __name__ == '__main__':
    from semantic_layer.config import SemanticSettings
    from semantic_layer.store.catalog_store import open_store
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser()
    parser.add_argument('--results-jsonl', type=Path)
    args = parser.parse_args()
    sqls = []
    if args.results_jsonl:
        for line in args.results_jsonl.read_text().splitlines():
            row = json.loads(line)
            sqls.extend(row[k] for k in ('sql', 'reference_sql') if row.get(k))
    settings = SemanticSettings.from_env()
    report = assess(open_store(settings.store_dsn, create=False), settings.tenant_id, settings.datasource_id, sqls)
    print(json.dumps(report, ensure_ascii=False, indent=2))
