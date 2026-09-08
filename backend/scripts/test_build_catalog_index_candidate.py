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
