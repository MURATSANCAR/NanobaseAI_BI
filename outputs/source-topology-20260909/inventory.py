import json
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store
from semantic_layer.profiler.connectors import connector_from_file
s=SemanticSettings.from_env();c=connector_from_file(s.connection_file);store=open_store(s.store_dsn)
report={}
for key,sql in [('connectedDatabase','SELECT DB_NAME() AS database_name'),('visibleDatabases','SELECT name,state_desc FROM sys.databases WHERE database_id>4 ORDER BY name')]:
 try:
  cols,rows,tr=c.execute(sql,200);report[key]={'rows':rows,'truncated':tr}
 except Exception as e:report[key]={'errorType':type(e).__name__}
report['sourceTables']=[{'table':p.table_name,'schema':p.schema_name,'entity':p.entity,'context':p.context,'rows':p.row_count,'window':p.time_window} for p in store.list_profiles(s.datasource_id) if p.table_name.upper().endswith(('_INVOICE','_STLINE')) and p.table_name.upper().startswith('LG_')]
p=Path('/data/nanobaseai/bi/backups/source-topology-20260909');p.mkdir(mode=0o700,exist_ok=True);(p/'inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str));print(json.dumps(report,ensure_ascii=False,default=str));c.close()
