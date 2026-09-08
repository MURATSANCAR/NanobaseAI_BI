"""Fill gaps in the LDDS dictionary from the user-supplied public Logo reference.

Run after import_logo_ldds.py. Use --prefer-web to apply documented web values over existing values; all changes are audited.
Download every linked page before writing outputs; --cache permits offline replay.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
import hashlib
from pathlib import Path
import re
from urllib.request import urlopen

from import_logo_ldds import OUT_JSON, OUT_GLOSSARY, REPO, base_name, glossary_markdown, parse_expression, scope_of, index_segments

URL = 'https://ugurozpinar.github.io/Logo/Tablo%20A%C3%A7%C4%B1klamalar%C4%B1%20Yeni/'
REPORT = REPO / 'docs/architecture/logo-web-audit.json'


class Tables(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tables = []
        self.row = None
        self.cell = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.tables.append([])
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            self.cell = []
        elif tag == 'br' and self.cell is not None:
            self.cell.append(' ')

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.tables[-1].append(self.row)
            self.row = None


def records(rows):
    header = rows[0]
    for row in rows[1:]:
        if len(row) != len(header):
            raise ValueError(f'Malformed row: {row}')
        yield dict(zip(header, row))


def expression(text):
    # Parenthesized comma-separated enumerations carry a footnote after the closing bracket.
    cleaned = re.sub(r'\)\d+$', ')', text)
    cleaned = re.sub(r'[,;]\s*(?=-?\d+\s*[-:])', ';', cleaned)
    cleaned = re.sub(r';\s*\((?=-?\d)', ';', cleaned)
    head, values = parse_expression(cleaned)
    return head, {k: (v[:-1] if v.endswith(')') and v.count(')') > v.count('(') else v).strip() for k, v in values.items()}


def merge(data, index, pages, prefer_web=False):
    audit = {'source_url': URL, 'pages': [], 'additions': [], 'differences': [], 'missing_descriptions': [], 'updates': [], 'policy': 'prefer-web' if prefer_web else 'fill-gaps'}
    def fill(target, key, value, location):
        if not value:
            return
        if not target.get(key):
            target[key] = value
            if '.values' not in location:
                target.setdefault('web_source', URL + location.split('.')[0])
            audit['additions'].append({'location': location, 'field': key, 'value': value})
        elif target[key] != value:
            change = {'location': location, 'field': key, 'existing': target[key], 'web': value}
            audit['differences'].append(change)
            if prefer_web:
                target[key] = value
                if '.values' not in location:
                    target['web_source'] = URL + location.split('.')[0]
                audit['updates'].append(change)

    for meta in index:
        name = meta['Resource Name']
        key = base_name(meta['Table Description']) if name == 'LDDS-Res' else base_name(name)
        sections = Tables(pages[name]).tables
        fields = next((list(records(s)) for s in sections if s and 'Field Name' in s[0]), None)
        if fields is None:
            audit['differences'].append({'location': name, 'field': 'missing_fields_section', 'existing': int(meta['Field Count']), 'web': None})
            fields = []
        if len(fields) != int(meta['Field Count']):
            audit['differences'].append({'location': name, 'field': 'field_count', 'existing': int(meta['Field Count']), 'web': len(fields)})
        table = data['tables'].setdefault(key, {'physical': name, 'level': {0:'system',1:'firm',2:'period'}[int(meta['Level'])], 'scope':scope_of(name,int(meta['Level'])), 'columns':{}, 'indexes':[], 'relations':[], 'source':'web-reference'})
        fill(table, 'description', meta['Resource Description'], name)
        for field in fields:
            colname = field['Field Name']
            if not colname:
                continue
            col = table['columns'].setdefault(colname, {})
            location = name + '.' + colname
            fill(col, 'type', field['Field Type'], location)
            fill(col, 'size', int(field['Field Size']), location)
            for source, dest, codes in [('Expression', 'description', 'values'), ('Türkçe Açıklama', 'description_tr', 'values_tr')]:
                text = field.get(source, '')
                if text == colname:
                    continue
                head, values = expression(text)
                fill(col, dest, head, location)
                for code, label in values.items():
                    fill(col.setdefault(codes, {}), code, label, location + '.' + codes)
                if col.get(codes) == {}:
                    col.pop(codes, None)
            if not col.get('description_tr'):
                audit['missing_descriptions'].append(location)
        # Audit structural differences; prefer-web applies documented entries with known columns.
        for section in sections:
            if section and ('Source Field' in section[0] or 'Index Name' in section[0]):
                kind = 'relations' if 'Source Field' in section[0] else 'index_segments'
                rows = list(records(section))
                audit['pages'].append({'table':name, 'section':kind, 'rows':rows})
                if kind == 'relations':
                    documented = [{'column': r['Source Field'], 'to': base_name(r['Destination Table']),
                                   'to_column': r['Destination Field'], 'type': r['Relation Type']}
                                  for r in rows]
                    for relation, source_row in zip(documented, rows):
                        if not any(all(existing.get(k) == v for k, v in relation.items()) for existing in table['relations']):
                            audit['differences'].append({'location': name, 'field': 'relation', 'web': relation,
                                                         'existing': [r for r in table['relations'] if r['column'] == relation['column']]})
                            target_columns = data['tables'].get(relation['to'], {}).get('columns', {})
                            if (prefer_web and not source_row.get('Extra Condition')
                                    and relation['column'] in table['columns'] and relation['to_column'] in target_columns):
                                table['relations'].append(dict(relation, source='web-reference', web_source=URL + name))
                                audit['updates'].append({'location': name, 'field': 'relation', 'web': relation})
                else:
                    documented = index_segments([dict(r, **{'Resource ID': 0}) for r in rows]).get(0, [])
                    if documented != table['indexes']:
                        audit['differences'].append({'location': name, 'field': 'indexes', 'web': documented,
                                                     'existing': table['indexes']})
                    if prefer_web:
                        # Update matching named indexes, retaining indexes the page does not list.
                        by_name = {ix['name']: ix for ix in table['indexes']}
                        for ix in documented:
                            if ix['columns'] and set(ix['columns']).issubset(table['columns']):
                                previous = by_name.get(ix['name'])
                                if previous != ix:
                                    audit['updates'].append({'location': name, 'field': 'index', 'existing': previous, 'web': ix})
                                    by_name[ix['name']] = ix
                        table['indexes'] = list(by_name.values())
        audit['pages'].append({'table':name, 'section':'fields', 'count':len(fields), 'url':URL+name})
    for metric, attr in [('column_count','columns'), ('relation_count','relations'), ('index_count','indexes')]:
        data[metric] = sum(len(t[attr]) for t in data['tables'].values())
    data['table_count'] = len(data['tables'])
    data['tr_column_count'] = sum(bool(c.get('description_tr')) for t in data['tables'].values() for c in t['columns'].values())
    data['coded_column_count'] = sum(bool(c.get('values')) for t in data['tables'].values() for c in t['columns'].values())
    data['tr_coded_column_count'] = sum(bool(c.get('values_tr')) for t in data['tables'].values() for c in t['columns'].values())
    data['web_reference'] = {'url':URL, 'generator':'backend/scripts/import_logo_web.py', 'page_count':len(index), 'policy':audit['policy']}
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--prefer-web', action='store_true', help='Prefer nonempty documented web values over existing values')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    def fetch(name):
        path = args.cache / (name + '.html')
        if not args.offline:
            with urlopen(URL + ('' if name == 'index' else name), timeout=30) as response:
                path.write_bytes(response.read())
        return path.read_text(encoding='utf-8')
    index = list(records(Tables(fetch('index')).tables[0]))
    original_index = index
    index = list({r['Resource Name']: r for r in index}.values())
    names = [r['Resource Name'] for r in index]
    with ThreadPoolExecutor(max_workers=8) as pool:
        pages = dict(zip(names, pool.map(fetch, names)))
    data = json.loads(OUT_JSON.read_text())
    audit = merge(data, index, pages, prefer_web=args.prefer_web)
    audit['index_rows'] = original_index
    audit['content_sha256'] = {name: hashlib.sha256(content.encode('utf-8')).hexdigest() for name, content in pages.items()}
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=1) , encoding='utf-8')
    OUT_GLOSSARY.write_text(glossary_markdown(data), encoding='utf-8')
    REPORT.write_text(json.dumps(audit, ensure_ascii=False, indent=1)+'\n', encoding='utf-8')
    print(json.dumps({'pages':len(names), 'additions':len(audit['additions']), 'differences':len(audit['differences']), 'updates':len(audit['updates']), 'missing_tr':len(audit['missing_descriptions'])}))


if __name__ == '__main__':
    main()
