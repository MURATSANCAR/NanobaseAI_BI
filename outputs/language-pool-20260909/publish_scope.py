import ast,hashlib,json,os,pwd,shutil,time
from pathlib import Path
p=Path('/data/nanobaseai/bi/frontend/backend/semantic_layer/runtime/context_scope.py');new=Path('/tmp/language-pool-release/context_scope.py');backup=Path('/data/nanobaseai/bi/backups/language-pool-20260909/release-5-scope')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='01cb383027f6a49ddca43644e58190ee9b280a6bb226cd7361a19d594b33fd1e', 'Context scope changed'
ast.parse(new.read_text());backup.mkdir(mode=0o700);shutil.copy2(p,backup/'before.py')
tmp=p.with_suffix('.release-tmp');shutil.copyfile(new,tmp);os.chmod(tmp,0o644);user=pwd.getpwnam('administrator');os.chown(tmp,user.pw_uid,user.pw_gid);os.replace(tmp,p)
report={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'deployedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'runtimeRestarted':False,'activePoolChanged':False}
(backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
