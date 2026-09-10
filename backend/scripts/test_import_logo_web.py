import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from import_logo_web import Tables, records, expression, merge, OUT_JSON


def test_html_cells_preserve_nested_text_and_entities():
    rows = Tables('<table><tr><th>Field Name</th><th>Text</th></tr><tr><td>CODE</td><td><b>Kod</b> &amp; ad<br>satır</td></tr></table>').tables[0]
    assert list(records(rows)) == [{'Field Name': 'CODE', 'Text': 'Kod & ad satır'}]


def test_parenthesized_codes_and_footnotes():
    assert expression('Durum ;(0- Aktif, 1- Pasif)1') == ('Durum', {'0': 'Aktif', '1': 'Pasif'})
    assert expression('Tür;20- Malzeme Sınıfı (Genel)')[1] == {'20': 'Malzeme Sınıfı (Genel)'}


def test_dictionary_codes_remain_numeric_and_descriptions_are_consumable():
    data = json.loads(OUT_JSON.read_text())
    for table in data['tables'].values():
        for col in table['columns'].values():
            for field in ('values', 'values_tr'):
                for code in col.get(field, {}):
                    int(code)
    assert data['tables']['INVEXIMINFO']['columns']['COUNTRYREF']['type'] == 'Longint'
    assert data['tables']['ITEMS']['columns']['CARDTYPE']['values_tr']['20'].endswith('(Genel)')


def test_merge_preserves_existing_values_and_is_idempotent():
    data = {'tables': {'TEST': {'columns': {'CODE': {'type': 'Byte', 'description_tr': 'Özgün'}}, 'indexes': [], 'relations': []}}}
    index = [{'Resource Name':'LG_TEST','Field Count':'1','Level':'1','Resource Description':'Test'}]
    html = '<table><tr><th>Field Name</th><th>Field Type</th><th>Field Size</th><th>Türkçe Açıklama</th><th>Expression</th></tr><tr><td>CODE</td><td>Integer</td><td>2</td><td>Yeni</td><td>Code</td></tr></table>'
    audit = merge(data, index, {'LG_TEST': html})
    assert data['tables']['TEST']['columns']['CODE']['description_tr'] == 'Özgün'
    assert data['tables']['TEST']['columns']['CODE']['type'] == 'Byte'
    assert any(d['field'] == 'type' for d in audit['differences'])
    before = copy.deepcopy(data)
    assert merge(data, index, {'LG_TEST': html})['additions'] == []
    assert data == before


def test_prefer_web_replaces_conflicts_but_preserves_unlisted_columns_and_codes():
    data = {'tables': {'TEST': {'columns': {'CODE': {'type': 'Byte', 'description_tr': 'Özgün', 'values_tr': {'1':'Eski', '9':'Korunan'}}, 'EXTRA': {'type':'Byte'}}, 'indexes': [], 'relations': []}}}
    index = [{'Resource Name':'LG_TEST','Field Count':'1','Level':'1','Resource Description':'Test'}]
    html = '<table><tr><th>Field Name</th><th>Field Type</th><th>Field Size</th><th>Türkçe Açıklama</th><th>Expression</th></tr><tr><td>CODE</td><td>Integer</td><td>2</td><td>Yeni;1- Etkin</td><td>Code</td></tr></table>'
    audit = merge(data, index, {'LG_TEST':html}, prefer_web=True)
    col = data['tables']['TEST']['columns']['CODE']
    assert col['description_tr'] == 'Yeni'
    assert col['type'] == 'Integer'
    assert col['values_tr'] == {'1':'Etkin', '9':'Korunan'}
    assert 'EXTRA' in data['tables']['TEST']['columns']
    assert audit['updates']
    before = copy.deepcopy(data)
    assert merge(data, index, {'LG_TEST':html}, prefer_web=True)['updates'] == []
    assert data == before
