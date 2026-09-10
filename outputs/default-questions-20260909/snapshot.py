import hashlib,json,time
from pathlib import Path
root=Path('/data/nanobaseai/bi/frontend')
out=Path('/data/nanobaseai/bi/backups/default-questions-20260909')
files=[p for folder in ('backend/semantic_layer','backend/semantic_bridge') for p in (root/folder).rglob('*.py')]+[root/'backend/nanobase_api/chat_widgets.py']
files += list(Path('/data/nanobaseai/bi/cockpit/dist').glob('index.html'))+list(Path('/data/nanobaseai/bi/cockpit/dist/assets').glob('index-CVdpn7rI.js'))
manifest={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.exists()}
(out/'source-manifest.json').write_text(json.dumps({'capturedAt':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'files':manifest},indent=2))
print('Captured',len(manifest),'source hashes')
