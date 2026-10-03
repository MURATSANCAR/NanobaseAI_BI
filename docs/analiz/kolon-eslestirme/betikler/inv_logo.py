import json, re, sys
sys.path.insert(0,'/data/nanobaseai/bi/frontend/backend')
from scripts.export_crm_metadata import connect
from pathlib import Path
cn = connect(Path('/data/nanobaseai/bi/secrets/logo-mssql-connection.json'), 'LOGO_DB')
cur = cn.cursor()
cur.execute("""
SELECT o.name, o.type, c.name, t.name, c.max_length, c.column_id
FROM sys.objects o JOIN sys.columns c ON c.object_id=o.object_id
JOIN sys.types t ON t.user_type_id=c.user_type_id
WHERE o.type IN ('U','V') AND o.is_ms_shipped=0""")
cols = cur.fetchall()
cur.execute("""SELECT o.name, SUM(p.rows) FROM sys.objects o JOIN sys.partitions p ON p.object_id=o.object_id AND p.index_id IN (0,1)
WHERE o.type='U' GROUP BY o.name""")
rows = {n:int(r) for n,r in cur.fetchall()}
out = {}
for name, typ, col, ty, ln, cid in cols:
    o = out.setdefault(name, {'type': typ.strip(), 'rows': rows.get(name), 'columns': []})
    o['columns'].append([col, ty, ln, cid])
json.dump(out, open('/tmp/ltc_logo_inv.json','w'), ensure_ascii=False)
print(len(out), len(cols))
