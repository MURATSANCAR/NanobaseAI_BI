import os, sys, json, shlex, datetime
sys.path.insert(0, '/data/nanobaseai/bi/frontend/backend')
for line in open('/etc/nanobase/semantic-bridge.env'):
    line=line.strip()
    if not line or line.startswith('#') or '=' not in line: continue
    k,v=line.removeprefix('export ').split('=',1)
    vals=shlex.split(v)
    os.environ[k]=' '.join(vals)
os.environ['SEMANTIC_QUERY_TIMEOUT_SEC']='45'
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
c=connector_from_file(SemanticSettings.from_env().connection_file)
def query(label,sql):
    try:
        _,rows,truncated=c.execute(sql,10000)
        print(json.dumps(dict(label=label,sql=sql,rows=rows,truncated=truncated),ensure_ascii=False),flush=True)
        return rows
    except Exception as e:
        print(json.dumps(dict(label=label,error=type(e).__name__+': '+str(e)[:300])),flush=True)
        return []
tables=query('logo_inventory',"SELECT t.name, SUM(p.rows) AS approximate_rows FROM sys.tables t JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1) WHERE t.name LIKE 'LG[_]%[_]STLINE' GROUP BY t.name ORDER BY t.name")
query('crm_inventory',"SELECT t.name,SUM(p.rows) AS approximate_rows FROM Timas_MSCRM.sys.tables t JOIN Timas_MSCRM.sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1) WHERE t.name IN ('new_siparisBase','new_siparissatiriBase','new_kitapBase','new_projeBase') GROUP BY t.name")
for t in tables:
    if not t['approximate_rows']: continue
    name=t['name']
    if not all(ch.isalnum() or ch=='_' for ch in name): continue
    query(name, f"SELECT YEAR(DATE_) AS year,MONTH(DATE_) AS month,COUNT_BIG(*) AS rows,MIN(DATE_) AS first_date,MAX(DATE_) AS last_date,SUM(CASE WHEN CANCELLED=0 AND LINETYPE=0 AND TRCODE IN (7,8) THEN 1 ELSE 0 END) AS sale_rows,SUM(CASE WHEN CANCELLED=0 AND LINETYPE=0 AND TRCODE IN (2,3) THEN 1 ELSE 0 END) AS return_rows FROM dbo.[{name}] GROUP BY YEAR(DATE_),MONTH(DATE_) ORDER BY year,month OPTION (MAXDOP 1)")
for col in ['new_siparistarihi','new_sevktarihi']:
    query('crm_'+col,f"SELECT YEAR([{col}]) AS year,MONTH([{col}]) AS month,COUNT_BIG(*) AS rows,MIN([{col}]) AS first_date,MAX([{col}]) AS last_date FROM Timas_MSCRM.dbo.new_siparisBase GROUP BY YEAR([{col}]),MONTH([{col}]) ORDER BY year,month OPTION (MAXDOP 1)")
c.close()
