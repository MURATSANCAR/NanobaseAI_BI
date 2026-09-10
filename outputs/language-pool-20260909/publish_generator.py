import ast,hashlib,json,os,pwd,shutil,time
from pathlib import Path
p=Path('/data/nanobaseai/bi/frontend/backend/scripts/build_language_pool.py');new=Path('/tmp/language-pool-release/build_language_pool.py');backup=Path('/data/nanobaseai/bi/backups/language-pool-20260909/release-3-generator')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='0d61080f7fb6abdc8afea9d410e79f034cfc70d5a55cfaf099b3e7d03a8e4ba5', 'Generator changed'
ast.parse(new.read_text());backup.mkdir(mode=0o700);shutil.copy2(p,backup/'before.py')
tmp=p.with_suffix('.release-tmp');shutil.copyfile(new,tmp);os.chmod(tmp,0o644);user=pwd.getpwnam('administrator');os.chown(tmp,user.pw_uid,user.pw_gid);os.replace(tmp,p)
report={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'deployedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'runtimeRestarted':False,'activePoolChanged':False}
(backup/'deployment.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
