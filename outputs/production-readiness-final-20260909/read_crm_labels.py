import json
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
s=SemanticSettings.from_env();c=connector_from_file(s.connection_file);root=Path('/data/nanobaseai/bi/backups/readiness-final-20260909')
tables=[r['name'] for r in c.execute("SELECT name FROM [Timas_MSCRM].sys.tables WHERE name LIKE 'new[_]%' OR name IN ('AccountBase','ContactBase','CustomerAddressBase','ProductBase','SystemUserBase','TerritoryBase')",10000)[1]];params=','.join('?' for _ in tables)
queries={
'attributes':f"SELECT e.BaseTableName,a.PhysicalName,a.Name,a.LogicalName,a.AttributeId,a.AttributeRowId,a.ComponentState FROM [Timas_MSCRM].[MetadataSchema].[Entity] e JOIN [Timas_MSCRM].[MetadataSchema].[Attribute] a ON a.EntityId=e.EntityId WHERE e.BaseTableName IN ({params}) AND e.ComponentState=0 AND a.ComponentState=0",
'attributeLabels':f"SELECT e.BaseTableName,a.PhysicalName,l.LanguageId,l.ObjectColumnName,l.Label,l.ComponentState FROM [Timas_MSCRM].[MetadataSchema].[Entity] e JOIN [Timas_MSCRM].[MetadataSchema].[Attribute] a ON a.EntityId=e.EntityId JOIN [Timas_MSCRM].[MetadataSchema].[LocalizedLabel] l ON l.ObjectId=a.AttributeId WHERE e.BaseTableName IN ({params}) AND e.ComponentState=0 AND a.ComponentState=0 AND l.ComponentState=0",
'entityLabels':f"SELECT e.BaseTableName,l.LanguageId,l.ObjectColumnName,l.Label FROM [Timas_MSCRM].[MetadataSchema].[Entity] e JOIN [Timas_MSCRM].[MetadataSchema].[LocalizedLabel] l ON l.ObjectId=e.EntityId WHERE e.BaseTableName IN ({params}) AND e.ComponentState=0 AND l.ComponentState=0"}
report={}
for k,sql in queries.items():
 cols,rows=c._rows(sql,tuple(tables));report[k]=[{col:str(v) if v is not None else None for col,v in zip(cols,row)} for row in rows]
(root/'crm-labels.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'counts':{k:len(v) for k,v in report.items()},'entityLabels':report['entityLabels'][:16],'sampleAttributeLabels':report['attributeLabels'][:6]},ensure_ascii=False));c.close()
