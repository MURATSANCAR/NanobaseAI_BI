import importlib.util,sys,json,hashlib
from pathlib import Path
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
from semantic_layer.store.catalog_store import open_store
spec=importlib.util.spec_from_file_location('readiness_compiler','/tmp/readiness-compiler.py');module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
s=SemanticSettings.from_env();c=connector_from_file(s.connection_file);store=open_store(s.store_dsn,create=False)
root=Path('/data/nanobaseai/bi/backups/readiness-final-20260909');tables=[r['table'] for r in json.loads((root/'source-inventory.json').read_text())['customTables'] if r['schema']=='Timas_MSCRM.dbo'];results=[]
for table in tables:
 sql='SELECT COUNT_BIG(*) AS n FROM '+module.Dialect('tsql').table('Timas_MSCRM.dbo',table)
 actual=c.execute(sql,1)[1][0]['n']
 ref='SELECT COUNT_BIG(*) AS n FROM [Timas_MSCRM]..['+table.replace(']',']]')+']'
 expected=c.execute(ref,1)[1][0]['n'];results.append({'table':table,'actual':actual,'reference':expected,'passed':actual==expected,'sql':sql})
report={'compilerSha256':hashlib.sha256(Path('/tmp/readiness-compiler.py').read_bytes()).hexdigest(),'results':results,'passed':all(r['passed'] for r in results)}
(root/'compiler-real-db.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));c.close()
