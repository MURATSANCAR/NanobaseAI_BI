"""Run only on the test server: actual audit API, persisted reports and real Logo refresh."""
import hashlib
import json
import os
import sys
from pathlib import Path
import time
import urllib.request

for line in Path('/etc/nanobase/semantic-bridge.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        key, value = line.split('=', 1)
        os.environ[key] = value.strip().strip('"').strip("'")
headers = {'X-Semantic-Caller': os.environ.get('SEMANTIC_CALLER_TOKEN', '')}
base = 'http://127.0.0.1:8795/api/v1/financial-audit/'
root = Path(os.getenv('FINANCIAL_AUDIT_DATA_DIR', '/data/nanobaseai/bi/var/financial-audit/workpapers'))
checks = []


def api(path, method='GET'):
    t = time.monotonic()
    with urllib.request.urlopen(urllib.request.Request(base + path, headers=headers, method=method), timeout=20) as response:
        return json.load(response), time.monotonic()-t


def check(name, ok, detail=None):
    checks.append(dict(name=name, status='PASS' if ok else 'FAIL', detail=detail))
    if len(checks) % 10 == 0:
        print(json.dumps(dict(completed=len(checks), passed=sum(c['status']=='PASS' for c in checks), failed=sum(c['status']=='FAIL' for c in checks), unverified=0)), flush=True)


def wait_ready():
    deadline = time.monotonic()+900
    polls = 0
    while time.monotonic() < deadline:
        try:
            state, _ = api('refresh-status')
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2)
            continue
        if state['state'] == 'error':
            raise RuntimeError(state)
        if state['state'] == 'ready' and state['calculationUpdated']:
            return state
        polls += 1
        if polls % 15 == 0:
            print(json.dumps({'refresh':'running', 'elapsedSeconds':polls*2}),flush=True)
        time.sleep(2)
    raise RuntimeError('Actual Logo refresh did not complete in 15 minutes')


if '--wait-only' in sys.argv:
    print(json.dumps(wait_ready()), flush=True)
    raise SystemExit(0)

if '--restart-check' in sys.argv:
    previous = json.loads((root.parent/'snapshot-acceptance.json').read_text())
    for attempt in range(60):
        try:
            report, elapsed = api('overview?year=2026')
            break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2)
    else:
        raise RuntimeError('API did not restart')
    check('durable-report-after-restart', report['runId']==previous['newRun'])
    check('restart-read-does-not-wait-for-logo', elapsed < 2, elapsed)
    (root.parent/'snapshot-restart.json').write_text(json.dumps({'checks':checks,'runId':report['runId']},indent=2))
    print(json.dumps(checks),flush=True)
    raise SystemExit(any(c['status']!='PASS' for c in checks))

initial = wait_ready()
old, old_time = api('overview?year=2026')
old_path = root / (old['runId']+'.json')
old_sha = hashlib.sha256(old_path.read_bytes()).hexdigest()
check('initial-snapshot-fast', old_time < 2, old_time)
check('snapshot-from-complete-archive', old['runId']==initial['runId'] and old['truncated'] is False)
check('current-backend', old['revision']==hashlib.sha256(Path('backend/semantic_bridge/financial_audit.py').read_bytes()).hexdigest())
first, post_time = api('refresh', 'POST')
check('refresh-accepted-without-blocking', first['accepted'] and first['state']=='refreshing' and post_time < 2, post_time)
second, _ = api('refresh', 'POST')
check('single-job-for-concurrent-refresh', not second['accepted'] and second['jobId']==first['jobId'])
during, during_time = api('overview?year=2026')
check('old-report-visible-during-refresh', during['runId']==old['runId'] and during['accounts']==old['accounts'])
check('read-does-not-wait-for-refresh-lock', during_time < 2, during_time)
check('real-refresh-state-visible', during['refresh']['state']=='refreshing')
final = wait_ready()
new, new_time = api('overview?year=2026')
check('new-report-atomically-published', new['runId']==final['runId'] and new['runId']!=old['runId'])
check('new-snapshot-fast', new_time<2, new_time)
check('new-timestamp', new['computedAt']>old['computedAt'])
check('old-archive-preserved', hashlib.sha256(old_path.read_bytes()).hexdigest()==old_sha)
stored = json.loads((root/(new['runId']+'.json')).read_text())
check('entire-api-result-matches-published-archive', all(new[k]==v for k,v in stored.items() if k!='cached'))
check('full-current-coverage-retained', len(new['accounts'])==379 and len(new['coverage']['items'])==649 and not new['truncated'])
check('latest-pointer-replaced', json.loads((root/'snapshots/latest.json').read_text())['runId']==new['runId'])
check('calculation-version-current', final['calculationUpdated'])
evidence = dict(environment='nanobase-direct / actual API :8795 / real Logo 2026 backup',
                oldRun=old['runId'], newRun=new['runId'], checks=checks,
                limitations=['Refresh failure retention inspected in code; no production connection deliberately broken.',
                             'Financial answer correctness checked separately by independent real DB acceptance.'])
target = root.parent/'snapshot-acceptance.json'
target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
print(json.dumps(dict(completed=len(checks), passed=sum(c['status']=='PASS' for c in checks), failed=sum(c['status']=='FAIL' for c in checks), path=str(target))),flush=True)
assert all(c['status']=='PASS' for c in checks)
