import json,hashlib,os,shutil,time
from pathlib import Path
sha=lambda b:hashlib.sha256(b).hexdigest()
plan=json.loads(Path('/tmp/source-topology-patch.json').read_text())
root=Path('/data/nanobaseai/bi/frontend')
k=root/'configs/semantic/knowledge/logo/knowledge'
changes={}
for name,replacements in plan['replacements'].items():
 p=k/name;b=p.read_bytes();assert sha(b)==plan['baseHashes'][name],name
 s=b.decode()
 for old,new in replacements:
  assert s.count(old)==1,(name,old)
  s=s.replace(old,new)
 changes[p]=s.encode()
new=k/'00-source-topology.md';assert not new.exists();changes[new]=plan['contract'].encode()
env=Path('/etc/nanobase/semantic-bridge.env');s=env.read_text();assert s.count('SEMANTIC_PATTERN_LABELS=Firma')==1
changes[env]=s.replace('SEMANTIC_PATTERN_LABELS=Firma','SEMANTIC_PATTERN_LABELS=').encode()
dist=Path('/data/nanobaseai/bi/cockpit/dist');js=dist/'assets/index-CzLs4emz.js';b=js.read_bytes();assert sha(b)=='4fa308d19dd43ed40581e7b5f5e2c2c5fbcfafcd5d6cffc7362c7f605b95725f'
old=b'title:`firma ${O.code}`';assert b.count(old)==1;b=b.replace(old,b'title:`Kaynak ${O.code}`')
asset='index-source-topology-'+sha(b)[:12]+'.js';changes[dist/'assets'/asset]=b
src=root/'apps/cockpit/src/components/CatalogExplorer.tsx';s=src.read_text();old='title={`firma ${c.code}`}';assert s.count(old)==1;changes[src]=s.replace(old,'title={`Kaynak ${c.code}`}').encode()
index=dist/'index.html';s=index.read_text();assert s.count('index-CzLs4emz.js')==1;changes[index]=s.replace('index-CzLs4emz.js',asset).encode()
backup=Path('/data/nanobaseai/bi/backups/source-topology-20260909')/('release-'+time.strftime('%H%M%S'));backup.mkdir(mode=0o700)
manifest=[]
for i,(p,data) in enumerate(changes.items()):
 prev=p.read_bytes() if p.exists() else None
 if prev is not None:shutil.copy2(p,backup/str(i))
 manifest.append({'path':str(p),'before':sha(prev) if prev is not None else None,'after':sha(data),'backup':str(i) if prev is not None else None})
(backup/'manifest.json').write_text(json.dumps(manifest,indent=2))
for p,data in changes.items():
 st=p.stat() if p.exists() else js.stat() if p.suffix=='.js' else (k/'agent-short.md').stat()
 tmp=p.with_name(p.name+'.topology-tmp');tmp.write_bytes(data);os.chmod(tmp,st.st_mode);os.chown(tmp,st.st_uid,st.st_gid);os.replace(tmp,p)
print(json.dumps({'backup':str(backup),'files':manifest,'asset':asset},indent=2))
