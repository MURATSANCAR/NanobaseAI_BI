import json,os,hashlib
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.store.catalog_store import open_store
from semantic_layer.profiler.connectors import connector_from_file
s=SemanticSettings.from_env();st=open_store(s.store_dsn,create=False);ps=one_entity_per_pattern(st.list_profiles(s.datasource_id),st.concept_entities(s.tenant_id,s.datasource_id));c=connector_from_file(s.connection_file)
actual=set();tr=False
for database in sorted({p.schema_name.rsplit('.',1)[0] if '.' in p.schema_name else '' for p in ps}):
 prefix=('['+database.replace(']',']]')+'].') if database else ''
 sql="SELECT s.name AS schema_name,t.name AS table_name,c.name AS column_name FROM "+prefix+"sys.objects t JOIN "+prefix+"sys.schemas s ON s.schema_id=t.schema_id JOIN "+prefix+"sys.columns c ON c.object_id=t.object_id WHERE t.type IN ('U','V')"
 _,rows,cut=c.execute(sql,500000);tr=tr or cut
 actual.update((((database+'.') if database else '')+r['schema_name']).lower()+'|'+r['table_name'].lower()+'|'+r['column_name'].upper() for r in rows)
missing=[]
for p in ps:
 for col in p.columns:
  if (p.schema_name.lower() or 'dbo')+'|'+p.table_name.lower()+'|'+col.name.upper() not in actual:missing.append({'table':p.table_name,'schema':p.schema_name,'column':col.name})
db=c.execute('SELECT DB_NAME() AS name',1)[1][0]['name'];c.close()
report={'database':db,'actualColumns':len(actual),'metadataTruncated':tr,'profileColumns':sum(len(p.columns) for p in ps),'missingProfileColumns':len(missing),'missing':missing,'status':'MATCH' if not missing and not tr else 'CATALOG_SOURCE_MISMATCH'}
p=Path('/data/nanobaseai/bi/backups/language-pool-auto-20260909/schema-live-check.json');p.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='missing'},ensure_ascii=False))
