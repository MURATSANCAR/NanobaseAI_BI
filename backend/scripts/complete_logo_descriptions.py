"""Fill missing Turkish descriptions from reviewed, exact-source translation maps.

Never changes existing descriptions, physical metadata or code values. Each addition
records its source text and translation/derivation method for later review.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def complete(data, column_maps, table_map, evidence, unresolved_columns=None):
    additions = []
    unresolved_columns = unresolved_columns or set()
    translations = {}
    for source, mapping in column_maps:
        for english, turkish in mapping.items():
            if english in translations and translations[english][0] != turkish:
                raise ValueError(f"Conflicting translation: {english}")
            if not english.strip() or not turkish.strip():
                raise ValueError("Empty translation")
            translations[english] = (turkish, source)

    def fill(entry, text, location, provenance):
        if (entry.get('description_tr') or '').strip():
            return
        entry['description_tr'] = text
        entry['description_tr_provenance'] = provenance
        additions.append({'location': location, 'description_tr': text, **provenance})

    for name, table in data['tables'].items():
        if name in table_map:
            item = table_map[name]
            if table.get('description') != item['source_description']:
                raise ValueError(f"Table source changed: {name}")
            fill(table, item['description_tr'], name, {
                'method': item.get('method', 'reviewed-translation'),
                'source_description': item['source_description'],
                'source': 'configs/schemas/logo-table-translations.json'})
        if name in evidence:
            item = evidence[name]
            source = table['columns'][item['source_column']]
            # Derivation must identify the precise documented column language.
            source_field = item.get('source_field', 'description')
            if source.get(source_field) != item['source_description']:
                raise ValueError(f"Evidence source changed: {name}")
            fill(table, item['description_tr'], name, {
                'method': item['method'], 'source_column': item['source_column'],
                'source_field': source_field,
                'source_description': item['source_description'],
                'source': 'configs/schemas/logo-table-description-evidence.json'})
        for column, entry in table['columns'].items():
            if f'{name}.{column}' in unresolved_columns:
                continue
            english = entry.get('description')
            if english in translations:
                turkish, source = translations[english]
                fill(entry, turkish, f'{name}.{column}', {
                    'method': 'reviewed-translation', 'source_description': english,
                    'source': source})
    data['tr_column_count'] = sum(bool((c.get('description_tr') or '').strip())
                                  for t in data['tables'].values() for c in t['columns'].values())
    return additions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dictionary', type=Path, default=Path('configs/schemas/logo-ldds.json'))
    parser.add_argument('--audit', type=Path, default=Path('docs/audits/logo-description-completion-2026-09-09.json'))
    args = parser.parse_args()
    directory = args.dictionary.parent
    data = json.loads(args.dictionary.read_text())
    map_files = [directory / f'logo-column-translations-{suffix}.json' for suffix in ('reused', 'a', 'b')]
    documents = [(str(p), json.loads(p.read_text())) for p in map_files]
    maps = [(p, d['translations']) for p, d in documents]
    caveats = {column: {'source_description': source, 'reason': item['reason']}
               for _, document in documents for source, item in document.get('source_caveats', {}).items()
               for column in item['columns']}
    tables = json.loads((directory / 'logo-table-translations.json').read_text())
    evidence = json.loads((directory / 'logo-table-description-evidence.json').read_text())['entries']
    additions = complete(data, maps, tables, evidence, set(caveats))
    if args.audit.exists():
        if not additions:
            print(json.dumps({'additions': 0, 'audit_preserved': str(args.audit)}))
            return
        raise FileExistsError('Existing audit: choose a new --audit path for this run')
    args.dictionary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    args.audit.write_text(json.dumps({'additions': additions, 'count': len(additions),
                                     'source_conflicts_not_translated': caveats}, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'additions': len(additions), 'turkish_columns': data['tr_column_count']}))


if __name__ == '__main__':
    main()
