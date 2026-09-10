"""Fill only missing CRM catalog labels from exported published source metadata.

Three things come across: what the source calls a table, what it calls a column, and what it calls
each of a coded column's values. The last one is the difference between a prompt that reads
`statuscode {1, 2, 100000001}` and one that reads `statuscode {1=Taslak, 100000001=İptal Edildi}` —
and between a question about cancelled orders finding nothing and finding the code it means.

Nothing already written is overwritten: a description the catalog holds, from whatever source, stands.
Run without --apply first; the report says exactly what would change.
"""
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlalchemy as sa
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.sensitivity import VALUE_SHAPE_REASONS as SHAPE_REASONS
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


def option_labels(rows):
    """{code: word} for one column, in the source's own words.

    A code named twice in the same language is dropped rather than picked between: two published
    labels for one value means the customisation is ambiguous, and inventing a winner would put a
    wrong word in front of every question that reads this column.
    """
    for language in ('1055', '1033'):
        chosen = defaultdict(set)
        for r in rows:
            if str(r.get('LanguageId')) == language and str(r.get('Label') or '').strip():
                chosen[str(r['Value'])].add(str(r['Label']).strip())
        named = {code: next(iter(words)) for code, words in chosen.items() if len(words) == 1}
        if named:
            return named, language
    return {}, 'NO_LABEL'


def enrich(store, datasource, source, output, apply=False):
    attrs = defaultdict(list)
    entities = defaultdict(list)
    options = defaultdict(list)
    for row in source['attributeLabels']:
        attrs[(row['BaseTableName'].upper(), row['PhysicalName'].upper())].append(row)
    for row in source['entityLabels']:
        entities[row['BaseTableName'].upper()].append(row)
    for row in source.get('optionLabels') or []:
        options[(row['BaseTableName'].upper(), row['PhysicalName'].upper())].append(row)
    report = {'applied': apply, 'source': 'Timas_MSCRM.MetadataSchema, published ComponentState=0',
              'filledTables': 0, 'filledColumns': 0, 'filledValueLabels': 0, 'namedCodes': 0, 'taggedTables': 0,
              'tables': [], 'unresolved': [], 'unflagged': []}
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
            derived = deepcopy(row['derived_json']) if row['derived_json'] else []
            if isinstance(derived, str): derived = json.loads(derived)
            said, language = label_text(entities[row['table_name'].upper()], 'LocalizedName')
            if not description and said:
                description = said
                report['filledTables'] += 1
                changed = True
            # Where a table's description came from, recorded the same way a column's is. Without it
            # the catalog holds "Sipariş" with no account of who said so, and the compiler's fallback
            # to it can never fire. Claimed only where the stored description is word for word what
            # the source says: a description somebody else wrote is not this source's to sign.
            if said and description == said and not any(d.get('text') == said for d in derived):
                derived.append({'source': 'crm_metadata_' + language, 'text': said})
                report['taggedTables'] += 1
                changed = True
            filled = coded = 0
            for col in cols:
                key = (row['table_name'].upper(), col['name'].upper())
                # The words for this column's codes, kept whether or not the column already has a
                # description: they are a different fact about it, and one does not stand in for the
                # other. Only the codes the data actually carries are kept — a status no row holds is
                # not a filter anyone can usefully be offered.
                named, _ = option_labels(options[key])
                if named and not col.get('value_labels'):
                    seen = {str(v) for v, _ in (col.get('top_values') or [])}
                    kept = {c: w for c, w in named.items() if not seen or c in seen}
                    if kept:
                        col['value_labels'] = kept
                        report['filledValueLabels'] += 1
                        report['namedCodes'] += len(kept)
                        coded += 1
                        changed = True
                # The source declaring this an option set settles what the values are, and a column
                # of option codes holds no personal data. Only a guess made from the shape of the
                # data is withdrawn: Dynamics numbers its options 100000001, which is nine digits and
                # read as a phone number. A column whose *name* says personal data keeps its mark —
                # the source naming its codes says nothing about what the column is for.
                if named and col.get('sensitive') and col.get('sensitivity_reason') in SHAPE_REASONS:
                    col['sensitive'] = False
                    col['sensitivity_reason'] = None
                    report['unflagged'].append({'table': row['table_name'], 'column': col['name']})
                    changed = True
                if col.get('description'): continue
                text, language = label_text(attrs[key], 'DisplayName')
                if text:
                    col['description'] = text
                    col.setdefault('derived', []).append({'source': 'crm_metadata_' + language, 'text': text})
                    report['filledColumns'] += 1
                    filled += 1
                    changed = True
                else:
                    report['unresolved'].append({'table': row['table_name'], 'column': col['name'], 'status': language})
            report['tables'].append({'table': row['table_name'], 'columns': len(cols), 'filledColumns': filled,
                                     'filledValueLabels': coded, 'description': description})
            if changed:
                before.append(dict(row))
                if apply:
                    conn.execute(S.sl_schema_profile.update().where(S.sl_schema_profile.c.id == row['id']).values(
                        description=description, columns_json=cols, derived_json=derived))
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
