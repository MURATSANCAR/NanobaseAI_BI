import json,hashlib,os,shutil,pwd
from pathlib import Path
stage=Path('/tmp/language-pool-auto-release');root=Path('/data/nanobaseai/bi/frontend');backup=Path('/data/nanobaseai/bi/backups/language-pool-auto-20260909');backup.mkdir(mode=0o700,exist_ok=True)
plan=json.loads((stage/'release.json').read_text());sha=lambda b:hashlib.sha256(b).hexdigest()
for row in plan:
 p=root/row['path'];assert (sha(p.read_bytes()) if p.exists() else None)==row['before'],str(p);assert sha((stage/row['source']).read_bytes())==row['after']
for i,row in enumerate(plan):
 p=root/row['path'];p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():shutil.copy2(p,backup/('before-'+str(i)));st=p.stat()
 else:st=(root/'backend/scripts/build_language_pool.py').stat()
 t=p.with_name(p.name+'.auto-tmp');t.write_bytes((stage/row['source']).read_bytes());os.chmod(t,st.st_mode);os.chown(t,st.st_uid,st.st_gid);os.replace(t,p)
owner=pwd.getpwnam('administrator');folder=Path('/data/nanobaseai/bi/var/language-pool');folder.mkdir(mode=0o700,exist_ok=True);os.chown(folder,owner.pw_uid,owner.pw_gid)
legacy=Path('/data/nanobaseai/bi/var/language-pool.json');active=folder/'active.json';assert not active.exists();shutil.copy2(legacy,backup/'pool-before.json');shutil.copy2(legacy,active);os.chown(active,owner.pw_uid,owner.pw_gid)
(backup/'deployment.json').write_text(json.dumps(plan,indent=2));print('Code deployed; candidate directory prepared. Runtime pool path unchanged pending live validation.')
