import json, sys
sys.path.insert(0,'/data/nanobaseai/bi/frontend/backend')
from scripts.export_crm_metadata import connect, SECRETS, DATABASE
cn = connect(SECRETS, DATABASE); cur = cn.cursor()
cur.execute("""
SELECT o.name, o.type, c.name, t.name, c.max_length, c.column_id
FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
JOIN sys.types t ON t.user_type_id=c.user_type_id
JOIN sys.schemas s ON s.schema_id=o.schema_id
WHERE o.type IN ('U') AND o.is_ms_shipped=0 AND s.name='dbo'""")
cols = cur.fetchall()
cur.execute("""SELECT o.name, SUM(p.rows) FROM sys.objects o JOIN sys.partitions p ON p.object_id=o.object_id AND p.index_id IN (0,1)
JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.type='U' AND s.name='dbo' GROUP BY o.name""")
rows = {n:int(r) for n,r in cur.fetchall()}
out = {}
for name, typ, col, ty, ln, cid in cols:
    o = out.setdefault(name, {'type': typ.strip(), 'rows': rows.get(name), 'columns': []})
    o['columns'].append([col, ty, ln, cid])
# CRM own labels: entity + attribute (Turkish 1055, English 1033), custom flag
cur.execute("""SELECT e.BaseTableName, e.Name, e.IsCustomEntity, l.LanguageId, l.ObjectColumnName, l.Label
FROM MetadataSchema.Entity e LEFT JOIN MetadataSchema.LocalizedLabel l ON l.ObjectId=e.EntityId AND l.ComponentState=0
 AND l.ObjectColumnName IN ('LocalizedName','Description')
WHERE e.BaseTableName IS NOT NULL AND e.ComponentState=0""")
ent = {}
for bt, n, cu, lang, oc, lab in cur.fetchall():
    d = ent.setdefault(bt, {'logical': n, 'custom': bool(cu), 'labels': {}})
    if lab: d['labels'][f'{oc}:{lang}'] = lab
cur.execute("""SELECT e.BaseTableName, a.PhysicalName, a.IsCustomField, l.LanguageId, l.ObjectColumnName, l.Label
FROM MetadataSchema.Attribute a JOIN MetadataSchema.Entity e ON e.EntityId=a.EntityId AND e.ComponentState=0
LEFT JOIN MetadataSchema.LocalizedLabel l ON l.ObjectId=a.AttributeId AND l.ComponentState=0 AND l.ObjectColumnName IN ('DisplayName','Description')
WHERE a.IsLogical=0 AND a.PhysicalName IS NOT NULL AND e.BaseTableName IS NOT NULL AND a.ComponentState=0""")
att = {}
for bt, pn, cu, lang, oc, lab in cur.fetchall():
    d = att.setdefault(bt, {}).setdefault(pn, {'custom': bool(cu), 'labels': {}})
    if lab: d['labels'][f'{oc}:{lang}'] = lab
json.dump({'tables': out, 'entities': ent, 'attributes': att}, open('/tmp/ltc_crm_inv.json','w'), ensure_ascii=False)
print(len(out), len(cols), len(ent), sum(len(v) for v in att.values()))
