import copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent))
from refresh_logo_catalog import refresh
from semantic_layer.models import SchemaProfile, ColumnProfile


def test_refresh_only_updates_known_descriptions_and_preserves_live_structure():
    class Store:
        def __init__(self):
            self.profiles=[SchemaProfile(datasource_id='logo',table_name='LG_411_ITEMS',table_pattern='LG_{firm}_ITEMS',entity='ITEMS',
                columns=[ColumnProfile('CARDTYPE',data_type='smallint',description='old',top_values=[('1',10)]),ColumnProfile('CUSTOM',description='local')],
                primary_key=['CARDTYPE'],row_count=10)]
        def list_profiles(self,ds):return self.profiles
        def upsert_profile(self,p):pass
    store=Store()
    before=copy.deepcopy(store.profiles[0])
    stats=refresh(store,'logo')
    after=store.profiles[0]
    assert stats['columns_updated']==1
    assert 'Ticari' in after.columns[0].description
    assert after.columns[0].data_type==before.columns[0].data_type
    assert after.columns[0].top_values==before.columns[0].top_values
    assert after.columns[1]==before.columns[1]
    assert after.primary_key==before.primary_key and after.row_count==before.row_count
    assert len(after.columns)==len(before.columns)
    assert refresh(store,'logo')['profiles_updated']==0
