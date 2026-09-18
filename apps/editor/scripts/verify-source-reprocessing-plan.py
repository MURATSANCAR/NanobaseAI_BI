#!/usr/bin/env python3
"""Read-only remote API/real PostgreSQL acceptance; no model or source writes."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


require(sys.platform.startswith('linux') and socket.gethostname() == os.environ['EDITOR_VERIFY_REMOTE_HOST'], 'Named remote Linux host required')
root = Path(os.environ['EDITOR_VERIFY_ROOT'])
generation = str(uuid.UUID(os.environ['EDITOR_VERIFY_GENERATION_ID']))
target = str(uuid.UUID(os.environ['EDITOR_VERIFY_IMPACT_RECORD_ID']))
base = os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/')
require(urllib.parse.urlparse(base).hostname == '127.0.0.1', 'Remote loopback required')
token = (root / 'secrets/api_token').read_text().strip()
proof = json.loads(Path(os.environ['EDITOR_VERIFY_IMPACT_REFERENCE_PROOF']).read_text())
require(proof['status'] == 'PASS' and proof['generation_id'] == generation and proof['target_id'] == target, 'Independent impact proof scope mismatch')
report = {'status': 'RUNNING', 'generation_id': generation, 'target_id': target, 'api': base,
          'model_calls': 0, 'source_or_review_writes': 0, 'semantic_acceptance': False,
          'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
destination = root / 'evidence' / ('source-reprocessing-plan-' + str(uuid.uuid4()) + '.json')


def pg(query):
    result = subprocess.run(['docker', 'compose', 'exec', '-T', 'postgres', 'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query], cwd=root, capture_output=True, text=True)
    require(result.returncode == 0, 'Independent PostgreSQL read failed')
    return json.loads(result.stdout)


def protected():
    return pg(f"SELECT json_build_object('records',(SELECT md5(COALESCE(json_agg(row_to_json(r) ORDER BY r.id)::text,'')) FROM editor.records r WHERE generation_id='{generation}'),'reviews',(SELECT md5(COALESCE(json_agg(row_to_json(r) ORDER BY r.id)::text,'')) FROM editor.reviews r WHERE generation_id='{generation}'),'jobs',(SELECT count(*) FROM editor.jobs WHERE generation_id='{generation}'))")


def get(route, authenticated=True):
    request = urllib.request.Request(base + '/v1' + route, headers={'Authorization': 'Bearer ' + token} if authenticated else {})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


try:
    require(pg(f"SELECT count(*) FROM editor.jobs WHERE generation_id='{generation}' AND status IN ('QUEUED','RUNNING')") == 0, 'Selected generation still running')
    before = protected()
    reference = pg(f"SELECT json_build_object('generation_id',g.id,'content_version_id',g.content_version_id,'source_sha256',cv.sha256,'target_id',r.id) FROM editor.generations g JOIN editor.content_versions cv ON cv.id=g.content_version_id JOIN editor.records r ON r.generation_id=g.id WHERE g.id='{generation}' AND r.id='{target}'")
    route = f'/generations/{generation}/records/{target}/reprocessing-plan'
    status, plan = get(route + '?expected_snapshot_sha256=' + proof['snapshot_sha256'])
    require(status == 200, 'Actual plan request failed')
    for key in ('generation_id', 'content_version_id', 'source_sha256'):
        require(plan[key] == reference[key], 'API/PG mismatch: ' + key)
    require(plan['target'] == proof['target'] and plan['snapshot_sha256'] == proof['snapshot_sha256'], 'Plan detached from independent impact snapshot')
    require(plan['known_impacted_records'] == proof['impacted_records'], 'Impact count mismatch')
    require(plan['strategy'] == 'FULL_GENERATION_FROM_ORIGINAL_SOURCE' and plan['reuse_policy'] == 'NOT_AUTHORIZED' and plan['reuse_measurement'] is None, 'Unsafe reuse/partial strategy')
    for key in ('graph_complete', 'known_impacted_records_are_complete', 'execution_available', 'job_created', 'accepted', 'semantic_acceptance'):
        require(plan[key] is False, 'Invalid promotion: ' + key)
    for key in ('requires_new_generation', 'preserve_original_source', 'preserve_existing_records', 'preserve_existing_reviews'):
        require(plan[key] is True, 'Missing preservation: ' + key)
    unsigned = {key: value for key, value in plan.items() if key != 'plan_sha256'}
    require(hashlib.sha256(json.dumps(unsigned, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest() == plan['plan_sha256'], 'Independent canonical plan hash mismatch')
    require(get(route, authenticated=False)[0] in (401, 403), 'Unauthenticated plan accessible')
    other = pg(f"SELECT to_json(id) FROM editor.records WHERE generation_id!='{generation}' ORDER BY id LIMIT 1")
    require(other and get(f'/generations/{generation}/records/{other}/reprocessing-plan')[0] == 404, 'Cross-generation target accepted')
    report.update({'plan': plan, 'protected_before': before, 'protected_after': protected(), 'scope_rejection': 'PASS', 'unauthenticated_rejection': 'PASS', 'snapshot_change_rejection': 'NOT_EXERCISED'})
    require(report['protected_before'] == report['protected_after'], 'Source/review/job state changed')
    report['status'] = 'PASS'
except Exception as error:
    report.update({'status': 'FAIL', 'error': str(error).replace(token, '[REDACTED]')})
    raise
finally:
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'status': report['status'], 'evidence': str(destination)}))
