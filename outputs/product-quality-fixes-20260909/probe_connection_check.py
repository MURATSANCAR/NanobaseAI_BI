import json,os,time
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_bridge.app import build_runtime
from semantic_layer.runtime.value_probe import ValueProbe
settings=SemanticSettings.from_env();settings.store_dsn='sqlite:////data/nanobaseai/bi/backups/product-quality-20260909/catalog.sqlite'
os.environ['SEMANTIC_LLM']='0';os.environ['SEMANTIC_REFRESH_SEC']='0'
r=build_runtime(settings)
r.connector.execute('SELECT 1 AS ok',1)
original=r.connector._conn
probe=ValueProbe(r.connector,r.profiles,max_columns=1,budget_seconds=3)
profile=next(p for p in r.profiles if p.entity=='CLCARD' and p.column('CODE'))
started=time.monotonic();error=None;hits=[]
try: hits=probe._like(profile,'CODE','kalitedenetimibulunmayan',3)
except Exception as exc: error=type(exc).__name__ + ': ' + str(exc)[:150]
elapsed=time.monotonic()-started
_,rows,_=r.connector.execute('SELECT 1 AS ok',1)
report={'isolated':probe.c is not r.connector,'mainConnectionPreserved':r.connector._conn is original,'mainQueryOk':rows==[{'ok':1}], 'probeConnectionClosed':probe.c._conn is None,'probeSeconds':round(elapsed,3),'hits':len(hits),'probeError':error}
Path('/data/nanobaseai/bi/backups/product-quality-20260909/probe-connection-evidence.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
r.connector.close()
