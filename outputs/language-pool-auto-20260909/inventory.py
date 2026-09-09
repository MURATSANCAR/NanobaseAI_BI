import json,os
from collections import Counter
from semantic_layer.config import SemanticSettings
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.store.catalog_store import open_store
from semantic_layer.runtime.language_pool import schema_documents,LanguagePool
s=SemanticSettings.from_env();st=open_store(s.store_dsn,create=False);ps=one_entity_per_pattern(st.list_profiles(s.datasource_id),st.concept_entities(s.tenant_id,s.datasource_id));by={p.table_pattern:p.entity for p in ps};an={}
for a in sorted(st.list_annotations(s.datasource_id),key=lambda a:a.created_at):
 if a.table_pattern in by and a.text:an[(by[a.table_pattern],(a.column or '').upper() or None)]=a.text
d=schema_documents(ps,an);pool=LanguagePool.load(os.environ.get('SEMANTIC_LANGUAGE_POOL'),ps,s.datasource_id,an)
print(json.dumps({'physicalProfiles':len(ps),'entities':len(d),'columns':sum(len(x['columns']) for x in d.values()),'maxColumns':max(len(x['columns']) for x in d.values()),'emptyTables':sum(not x['columns'] for x in d.values()),'describedColumns':sum(any(v['description'] for v in vs) for x in d.values() for vs in x['columns'].values()),'sensitiveExcluded':sum(c.sensitive for p in ps for c in p.columns),'poolEntries':len(pool.entries),'poolPath':os.environ.get('SEMANTIC_LANGUAGE_POOL'),'model':s.llm_model,'largest':[{'entity':e,'columns':len(x['columns'])} for e,x in sorted(d.items(),key=lambda z:-len(z[1]['columns']))[:5]]},ensure_ascii=False,indent=2))
