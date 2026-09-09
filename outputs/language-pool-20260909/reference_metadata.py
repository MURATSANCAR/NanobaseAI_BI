import json
from semantic_layer.config import SemanticSettings
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.store.catalog_store import open_store
from semantic_layer.runtime.language_pool import schema_documents
s=SemanticSettings.from_env();st=open_store(s.store_dsn,create=False)
ps=one_entity_per_pattern(st.list_profiles(s.datasource_id),st.concept_entities(s.tenant_id,s.datasource_id))
for p in ps:
 if p.entity in ('ITEMS','CLCARD','SLSMAN') and ('411' in p.table_name or p.entity=='SLSMAN'):
  print(json.dumps({'entity':p.entity,'table':p.table_name,'schema':p.schema_name,'context':p.context,'columns':[c.__dict__ for c in p.columns if c.name in ('ACTIVE','CODE','CAMPPOINT','B2CCODE') ]},ensure_ascii=False,default=str))
