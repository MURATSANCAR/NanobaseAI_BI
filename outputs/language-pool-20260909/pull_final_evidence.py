import hashlib,json,os,shlex,subprocess
from pathlib import Path
root=Path(__file__).resolve().parent;evidence=root/'evidence';evidence.mkdir(exist_ok=True)
remote='/data/nanobaseai/bi/backups/language-pool-20260909/'
files={name:name for name in ['final-summary.json','result-cell-evidence.json','complex-final-results.json','feature-final-results.json','prompts-final-status.md','source-before-final.json','source-before-targeted.json','source-after-final.json','pool-check.json','acceptance-harness-hashes-final.json']}
files.update({'compiler-deployment.json':'release-4-compiler/deployment.json','scope-deployment.json':'release-5-scope/deployment.json'})
for name,path in files.items():
 dest=evidence/name;tmp=dest.with_suffix(dest.suffix+'.tmp')
 with tmp.open('wb') as out:
  subprocess.run(['ssh','-o','ConnectTimeout=15','nanobase-direct','sudo cat -- '+shlex.quote(remote+path)],stdout=out,check=True)
 os.replace(tmp,dest)
s=json.loads((evidence/'final-summary.json').read_text());after=json.loads((evidence/'source-after-final.json').read_text());local=json.loads((evidence/'local-test-source.json').read_text())
assert not s['sourceChangedDuringAcceptance'] and not s['sourceChangedSinceTargeted']
assert s['sameServiceProcess'] and s['sameTargetedServiceProcess']
for path,expected in local['files'].items():
 assert after['files']['/data/nanobaseai/bi/frontend/'+path]==expected, 'Live/local tested source differs: '+path
assert s['complex']['completed']==100 and sum(s['targetedCounts'].values())==20
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence.iterdir() if p.is_file() and p.name!='evidence-manifest.json'}
(evidence/'evidence-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'downloaded':len(files),'sameTestedLocalAndLiveFeatureSources':True,'summary':s},ensure_ascii=False))
