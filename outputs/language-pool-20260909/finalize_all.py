import hashlib,json,subprocess,sys
from pathlib import Path
root=Path('/data/nanobaseai/bi/backups/language-pool-20260909');stage=Path('/tmp/language-pool-release')
subprocess.run([sys.executable,str(stage/'snapshot.py'),'after-final'],check=True)
subprocess.run([sys.executable,str(stage/'finalize.py')],check=True)
files=[stage/f for f in ['scoped_acceptance.py','feature_acceptance_final.py','lookup_acceptance_final.py','context_guards.py','snapshot.py','finalize.py','finalize_all.py','acceptance.sh','continue-acceptance.sh','run-100.sh']]
(root/'acceptance-harness-hashes-final.json').write_text(json.dumps({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2))
