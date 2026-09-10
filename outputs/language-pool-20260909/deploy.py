import ast, hashlib, json, os, pwd, shutil, subprocess, time, urllib.request
from pathlib import Path
base=Path('/data/nanobaseai/bi')
root=base/'frontend'
stage=Path('/tmp/language-pool-release')
backup=base/'backups/language-pool-20260909/release-1'
env=Path('/etc/nanobase/semantic-bridge.env')
pool_path=base/'var/language-pool.json'
manifest=json.loads((stage/'manifest.json').read_text())
files={'app':root/'backend/semantic_bridge/app.py','compiler':root/'backend/semantic_layer/runtime/compiler.py','models':root/'backend/semantic_layer/models.py','language_pool':root/'backend/semantic_layer/runtime/language_pool.py','build_language_pool':root/'backend/scripts/build_language_pool.py'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for name,p in files.items():
 ast.parse((stage/(name+'.py')).read_text())
 if name in manifest:
  assert sha(p)==manifest[name]['before'], f'Production changed: {name}'
  assert sha(stage/(name+'.py'))==manifest[name]['after'], f'Candidate changed: {name}'
assert not backup.exists(), 'Release already exists; inspect before rerunning'
from semantic_layer.config import SemanticSettings
from semantic_layer.catalog import one_entity_per_pattern
from semantic_layer.store.catalog_store import open_store
from semantic_layer.runtime.language_pool import LanguagePool
s=SemanticSettings.from_env(); store=open_store(s.store_dsn,create=False)
ps=one_entity_per_pattern(store.list_profiles(s.datasource_id),store.concept_entities(s.tenant_id,s.datasource_id))
by_pattern={p.table_pattern:p.entity for p in ps}; annotations={}
for a in sorted(store.list_annotations(s.datasource_id),key=lambda a:a.created_at):
 if a.table_pattern in by_pattern and a.text:annotations[(by_pattern[a.table_pattern],(a.column or '').upper() or None)]=a.text
pool=LanguagePool.load(stage/'pool.json',ps,s.datasource_id,annotations)
assert pool.entries and pool.rejected==0, 'Invalid or empty candidate pool'
backup.mkdir(mode=0o700,parents=True)
shutil.copy2(env,backup/'environment.before')
existed={name:p.exists() for name,p in files.items()}
for name,p in files.items():
 if p.exists():shutil.copy2(p,backup/(name+'.before.py'))
pool_existed=pool_path.exists()
if pool_existed:shutil.copy2(pool_path,backup/'pool.before.json')
user=pwd.getpwnam('administrator')
def install(source,target,mode=0o644):
 target.parent.mkdir(parents=True,exist_ok=True)
 tmp=target.with_name(target.name+'.language-release-tmp')
 shutil.copyfile(source,tmp);os.chmod(tmp,mode);os.chown(tmp,user.pw_uid,user.pw_gid)
 os.replace(tmp,target)
def healthy():
 for _ in range(30):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8795/health',timeout=3) as r: h=json.load(r)
   if h.get('status')=='ok' and h.get('db') and h.get('llm'):return h
  except Exception:pass
  time.sleep(2)
 raise RuntimeError('Service did not become healthy')
try:
 for name,p in files.items():install(stage/(name+'.py'),p)
 install(stage/'pool.json',pool_path,0o600)
 lines=[line for line in env.read_text().splitlines() if not line.startswith('SEMANTIC_LANGUAGE_POOL=')]
 lines.append('SEMANTIC_LANGUAGE_POOL='+str(pool_path))
 tmp=env.with_suffix('.language-release-tmp');tmp.write_text('\n'.join(lines)+'\n');os.chmod(tmp,0o600);os.replace(tmp,env)
 print('Feature files and pool installed; restarting service',flush=True)
 subprocess.run(['systemctl','restart','nanobase-semantic-bridge'],check=True)
 health=healthy()
 report={'files':{str(p):sha(p) for p in files.values()},'poolFileSha256':sha(pool_path),'poolHash':pool.content_hash,'poolCandidates':len(pool.entries),'health':health,'deployedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
 (backup/'deployment.json').write_text(json.dumps(report,indent=2))
 print(json.dumps(report),flush=True)
except Exception:
 for name,p in files.items():
  if existed[name]:install(backup/(name+'.before.py'),p)
  elif p.exists():p.unlink()
 shutil.copy2(backup/'environment.before',env)
 if pool_existed:install(backup/'pool.before.json',pool_path,0o600)
 elif pool_path.exists():pool_path.unlink()
 subprocess.run(['systemctl','restart','nanobase-semantic-bridge'],check=True)
 print('Release rolled back',flush=True)
 raise
