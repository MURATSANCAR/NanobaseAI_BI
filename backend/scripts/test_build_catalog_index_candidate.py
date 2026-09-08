from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
from build_catalog_index_candidate import catalog_points
from semantic_layer.models import SchemaProfile,ColumnProfile


def test_every_column_is_indexed_without_inventing_descriptions():
    profiles=[SchemaProfile(datasource_id='logo',table_name=f'LG_{firm}_BANKACC',table_pattern='LG_{firm}_BANKACC',entity='BANKACC',
        columns=[ColumnProfile('IBAN',data_type='varchar'),ColumnProfile('CODE',description='Hesap kodu')]) for firm in ('211','411')]
    points,expected=catalog_points(profiles)
    assert expected=={('BANKACC','IBAN'),('BANKACC','CODE')}
    assert len([p for p in points if p.column=='IBAN'])==1
    assert next(p.text for p in points if p.column=='IBAN')=='BANKACC.IBAN — SQL tipi: varchar'
    assert len([p for p in points if p.column=='CODE'])==1
    assert len([p for p in points if p.column is None])==2
    assert [p.id for p in points]==list(range(1,len(points)+1))


def test_standard_indexer_also_keeps_undocumented_columns():
    from index_catalog_qdrant import points_for
    profile=SchemaProfile(datasource_id='logo',table_name='LG_411_BANKACC',table_pattern='LG_{firm}_BANKACC',entity='BANKACC',columns=[ColumnProfile('IBAN',data_type='varchar')])
    points=points_for([profile])
    assert any(p.column=='IBAN' and p.text=='BANKACC.IBAN — SQL tipi: varchar' for p in points)


def test_verification_rejects_missing_stored_column(monkeypatch):
    import pytest
    import build_catalog_index_candidate as module
    profile=SchemaProfile(datasource_id='logo',table_name='LG_411_BANKACC',table_pattern='LG_{firm}_BANKACC',entity='BANKACC',columns=[ColumnProfile('IBAN',data_type='varchar')])
    points,expected=catalog_points([profile])
    stored=[{'payload':{'entity':p.entity,'column':p.column,'text':p.text}} for p in points]
    def http(method,url,body=None):
        if method=='GET':return {'result':{'status':'green'}}
        return {'result':{'points':stored,'next_page_offset':None}}
    monkeypatch.setattr(module,'_http_json',http)
    assert module.verify_points('candidate',points,expected)['unindexed_columns']==0
    stored.pop()
    with pytest.raises(RuntimeError,match='coverage mismatch'):
        module.verify_points('candidate',points,expected)


def test_checkpoint_vectors_from_another_model_are_not_reused(monkeypatch):
    import build_catalog_index_candidate as module
    cached={'one':[1.0,0.0]}
    monkeypatch.setattr(module,'embed',lambda texts,key:[[1.0,0.0]])
    assert module.compatible_cache(cached,'')
    monkeypatch.setattr(module,'embed',lambda texts,key:[[0.0,1.0]])
    assert not module.compatible_cache(cached,'')
    monkeypatch.setattr(module,'embed',lambda texts,key:[[0.0,0.0]])
    assert not module.compatible_cache(cached,'')
