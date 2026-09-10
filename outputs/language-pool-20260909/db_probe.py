import json,time
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
s=SemanticSettings.from_env();c=connector_from_file(s.connection_file)
t=time.monotonic()
try:
 cols,rows,tr=c.execute("SELECT r.session_id,r.status,r.command,r.wait_type,r.blocking_session_id,r.total_elapsed_time,r.cpu_time,r.logical_reads,r.reads,r.writes,s.program_name,t.text AS query_text FROM sys.dm_exec_requests r JOIN sys.dm_exec_sessions s ON s.session_id=r.session_id CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) t WHERE r.session_id<>@@SPID AND r.session_id>50 AND r.status<>'background'",30)
 import re,hashlib
 for row in rows:
  query=row.pop('query_text','') or ''
  row['tables']=sorted(set(re.findall(r'(?:LG|LV)_[A-Za-z0-9_]+',query)))
  row['queryHash']=hashlib.sha256(query.encode()).hexdigest()
  row['queryLength']=len(query)

 print(json.dumps({'seconds':time.monotonic()-t,'requests':rows},default=str),flush=True)
except Exception as e:print(json.dumps({'seconds':time.monotonic()-t,'error':str(e)[:400]}),flush=True)
c.close()
