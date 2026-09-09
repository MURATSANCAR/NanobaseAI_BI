"""Fill only missing CRM catalog labels from exported published source metadata."""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlalchemy as sa
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store
from semantic_layer.store import schema as S


def label_text(rows, name_key):
    for language in ('1055', '1033'):
        chosen = [r for r in rows if str(r.get('LanguageId')) == language]
        def texts(kind):
            return {str(r.get('Label') or '').strip() for r in chosen
                    if r.get('ObjectColumnName') == kind and str(r.get('Label') or '').strip()}
        names, descriptions = texts(name_key), texts('Description')
        if len(descriptions) > 1 or (len(names) > 1 and not descriptions):
            return None, 'CONFLICT'
        # Different display aliases do not invalidate an identical source description.
        parts = ([] if len(names) != 1 else list(names)) + list(descriptions)
        if parts:
            return '. '.join(dict.fromkeys(parts)), language
    return None, 'NO_LABEL'


def enrich(store, datasource, source, output, apply=False):
    attrs = defaultdict(list)
    entities = defaultdict(list)
    for row in source['attributeLabels']:
        attrs[(row['BaseTableName'].upper(), row['PhysicalName'].upper())].append(row)
    for row in source['entityLabels']:
        entities[row['BaseTableName'].upper()].append(row)
    report = {'applied': apply, 'source': 'Timas_MSCRM.MetadataSchema, published ComponentState=0',
              'filledTables': 0, 'filledColumns': 0, 'tables': [], 'unresolved': []}
    before = []
    with store._lock, store.engine.begin() as conn:
        rows = conn.execute(sa.select(S.sl_schema_profile).where(
            S.sl_schema_profile.c.datasource_id == datasource,
            S.sl_schema_profile.c.schema_name == 'Timas_MSCRM.dbo').with_for_update()).mappings().all()
        for row in rows:
            cols = deepcopy(row['columns_json'])
            if isinstance(cols, str): cols = json.loads(cols)
            description = row['description']
            changed = False
            if not description:
                description, language = label_text(entities[row['table_name'].upper()], 'LocalizedName')
                if description:
                    report['filledTables'] += 1
                    changed = True
            filled = 0
            for col in cols:
                if col.get('description'): continue
                text, language = label_text(attrs[(row['table_name'].upper(), col['name'].upper())], 'DisplayName')
                if text:
                    col['description'] = text
                    col.setdefault('derived', []).append({'source': 'crm_metadata_' + language, 'text': text})
                    report['filledColumns'] += 1
                    filled += 1
                    changed = True
                else:
                    report['unresolved'].append({'table': row['table_name'], 'column': col['name'], 'status': language})
            report['tables'].append({'table': row['table_name'], 'columns': len(cols), 'filledColumns': filled, 'description': description})
            if changed:
                before.append(dict(row))
                if apply:
                    conn.execute(S.sl_schema_profile.update().where(S.sl_schema_profile.c.id == row['id']).values(
                        description=description, columns_json=cols))
        if apply:
            backup = output.with_suffix('.before.json')
            if backup.exists(): raise RuntimeError('Backup already exists; use a new output path')
            backup.write_text(json.dumps(before, ensure_ascii=False, default=str, indent=2))
            backup.chmod(0o600)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    settings = SemanticSettings.from_env()
    report = enrich(open_store(settings.store_dsn, create=False), settings.datasource_id,
                    json.loads(args.source.read_text()), args.out, args.apply)
    report['sourceSha256'] = hashlib.sha256(args.source.read_bytes()).hexdigest()
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('unresolved', 'tables')}, ensure_ascii=False))
    print('Unresolved columns:', len(report['unresolved']))
