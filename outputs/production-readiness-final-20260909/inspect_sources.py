import json,collections
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store
from semantic_layer.profiler.connectors import connector_from_file
s=SemanticSettings.from_env();store=open_store(s.store_dsn,create=False);profiles=store.list_profiles(s.datasource_id);c=connector_from_file(s.connection_file)
custom=[p for p in profiles if not p.table_name.upper().startswith(('LG_','L_'))]
report={'schemas':dict(collections.Counter(p.schema_name for p in profiles)),'customTables':[{'schema':p.schema_name,'table':p.table_name,'entity':p.entity,'columns':len(p.columns),'describedColumns':sum(bool(x.description) for x in p.columns),'description':p.description} for p in custom]}
for name,sql in [('databases',"SELECT name FROM sys.databases WHERE HAS_DBACCESS(name)=1"),('extendedProperties',"SELECT s.name AS schema_name,t.name AS table_name,c.name AS column_name,CAST(ep.value AS nvarchar(4000)) AS description FROM sys.extended_properties ep JOIN sys.tables t ON ep.major_id=t.object_id JOIN sys.schemas s ON t.schema_id=s.schema_id LEFT JOIN sys.columns c ON c.object_id=t.object_id AND c.column_id=ep.minor_id WHERE ep.class=1 AND ep.name='MS_Description'"),('crmMetadataTables',"SELECT s.name AS schema_name,t.name AS table_name FROM [Timas_MSCRM].sys.tables t JOIN [Timas_MSCRM].sys.schemas s ON t.schema_id=s.schema_id WHERE s.name='MetadataSchema' OR t.name IN ('Entity','Attribute','LocalizedLabel','StringMapBase')")]:
 try: report[name]=c.execute(sql,100000)[1]
 except Exception as exc:report[name]={'error':str(exc)[:250]}
root=Path('/data/nanobaseai/bi/backups/readiness-final-20260909');root.mkdir(parents=True,exist_ok=True);(root/'source-inventory.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'schemas':report['schemas'],'customTables':len(custom),'sample':report['customTables'][:12],'databases':report['databases'],'extendedProperties':len(report['extendedProperties']),'crmMetadataTables':report['crmMetadataTables']},ensure_ascii=False))
c.close()
