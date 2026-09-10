import hashlib,json,sys,time,urllib.request
from pathlib import Path
root=Path('/data/nanobaseai/bi/frontend');out=Path('/data/nanobaseai/bi/backups/language-pool-20260909')
files=[p for folder in ('backend/semantic_layer','backend/semantic_bridge') for p in (root/folder).rglob('*.py')]+[root/'backend/nanobase_api/chat_widgets.py',root/'backend/scripts/build_language_pool.py',Path('/data/nanobaseai/bi/var/language-pool.json'),root/'tests/stress/enduser_live_10000.py',root/'tests/stress/result_comparison.py',root/'tests/stress/enduser_10000.py']
manifest={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.exists()}
with urllib.request.urlopen('http://127.0.0.1:8795/health',timeout=10) as r:health=json.load(r)
(out/('source-'+sys.argv[1]+'.json')).write_text(json.dumps({'capturedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'files':manifest,'health':health},indent=2))
print('Captured',len(manifest),'source hashes; service PID',health['pid'])
