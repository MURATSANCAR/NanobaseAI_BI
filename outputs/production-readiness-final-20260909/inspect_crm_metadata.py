import json
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
s=SemanticSettings.from_env();c=connector_from_file(s.connection_file)
sql="SELECT t.name AS table_name,c.name AS column_name FROM [Timas_MSCRM].sys.columns c JOIN [Timas_MSCRM].sys.tables t ON c.object_id=t.object_id JOIN [Timas_MSCRM].sys.schemas s ON t.schema_id=s.schema_id WHERE s.name='MetadataSchema' AND t.name IN ('Entity','Attribute','LocalizedLabel','Relationship') ORDER BY t.name,c.column_id"
r=c.execute(sql,10000)[1]
p=Path('/data/nanobaseai/bi/backups/readiness-final-20260909');(p/'crm-metadata-schema.json').write_text(json.dumps(r,indent=2));source=json.loads((p/'source-inventory.json').read_text());print(json.dumps({'crmProfiles':[x for x in source['customTables'] if x['schema']=='Timas_MSCRM.dbo'],'metadataColumns':r},ensure_ascii=False));c.close()
