from pathlib import Path
import json,hashlib,shutil,os
p=Path('/data/nanobaseai/bi/frontend/configs/semantic/knowledge/logo/knowledge/caveats/logo-timas.md');d=json.loads(Path('/tmp/source-topology-caveat.json').read_text());assert hashlib.sha256(p.read_bytes()).hexdigest()==d['before']
b=Path('/data/nanobaseai/bi/backups/source-topology-20260909/release-204009');shutil.copy2(p,b/'caveat-before.md');st=p.stat();tmp=p.with_suffix('.tmp');tmp.write_text(d['text']);os.chmod(tmp,st.st_mode);os.chown(tmp,st.st_uid,st.st_gid);os.replace(tmp,p)
(b/'caveat-manifest.json').write_text(json.dumps({'before':d['before'],'after':hashlib.sha256(p.read_bytes()).hexdigest(),'path':str(p)}));print('caveat corrected')
