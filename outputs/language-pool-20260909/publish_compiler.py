import ast,hashlib,json,os,pwd,shutil,time
from pathlib import Path
p=Path('/data/nanobaseai/bi/frontend/backend/semantic_layer/runtime/compiler.py');new=Path('/tmp/language-pool-release/compiler.py');backup=Path('/data/nanobaseai/bi/backups/language-pool-20260909/release-4-compiler')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='bf854a06ad80804f756f8beafd061bd235bf90f014d9cd1076e935ba358d65df', 'Compiler changed'
ast.parse(new.read_text());backup.mkdir(mode=0o700);shutil.copy2(p,backup/'before.py')
tmp=p.with_suffix('.release-tmp');shutil.copyfile(new,tmp);os.chmod(tmp,0o644);user=pwd.getpwnam('administrator');os.chown(tmp,user.pw_uid,user.pw_gid);os.replace(tmp,p)
report={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'deployedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'runtimeRestarted':False,'activePoolChanged':False}
(backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
