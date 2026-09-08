import copy
import pytest
from complete_logo_descriptions import complete


def fixture():
    return {'tables': {'A': {'description': 'Cards', 'columns': {
        'X': {'description': 'Code', 'type': 'Longint', 'values': {'1': 'One'}},
        'Y': {'description': 'Code', 'description_tr': 'Yerel açıklama'},
        'Z': {'type': 'Byte'},
    }}}}


def test_fill_is_exact_sourced_idempotent_and_preserves_metadata():
    data = fixture()
    original = copy.deepcopy(data)
    args = ([('review.json', {'Code': 'Kod'})], {'A': {'source_description': 'Cards', 'description_tr': 'Kartlar'}}, {})
    assert len(complete(data, *args)) == 2
    assert complete(data, *args) == []
    cols = data['tables']['A']['columns']
    assert cols['Y'] == original['tables']['A']['columns']['Y']
    assert cols['Z'] == original['tables']['A']['columns']['Z']
    assert cols['X']['type'] == 'Longint' and cols['X']['values'] == {'1': 'One'}
    assert cols['X']['description_tr_provenance']['source_description'] == 'Code'


def test_conflicting_or_stale_sources_fail():
    with pytest.raises(ValueError, match='Conflicting'):
        complete(fixture(), [('a', {'Code': 'Kod'}), ('b', {'Code': 'Numara'})], {}, {})
    with pytest.raises(ValueError, match='source changed'):
        complete(fixture(), [], {'A': {'source_description': 'Different', 'description_tr': 'Kartlar'}}, {})


def test_table_derivation_checks_column_source():
    evidence = {'A': {'source_column': 'X', 'source_description': 'Wrong', 'description_tr': 'Kartlar', 'method': 'documented-column'}}
    with pytest.raises(ValueError, match='Evidence source changed'):
        complete(fixture(), [], {}, evidence)


def test_unresolved_source_conflicts_are_not_propagated():
    data = fixture()
    assert complete(data, [('a', {'Code': 'Kod'})], {}, {}, {'A.X'}) == []
    assert 'description_tr' not in data['tables']['A']['columns']['X']
