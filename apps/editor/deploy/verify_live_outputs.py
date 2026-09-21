"""Read-only checkpoints for the real-book output lifecycle, run on tt-gpu.

No fixtures or local tests. Captures the actual control API and independent
base-table reference, including immutable history and validation ordering.
Usage inside editor-control: python verify_live_outputs.py GENERATION STAGE
"""
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone

import httpx

from editor import db, jobs
from editor.config import settings

gid, stage = sys.argv[1:3]


def plain(value):
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))


def digest(value):
    return hashlib.sha256(json.dumps(plain(value), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


with db.tx() as c:
    c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    state = c.execute("SELECT * FROM generation_state WHERE generation_id=%s", (gid,)).fetchone()
    gen = c.execute("SELECT * FROM generation WHERE id=%s", (gid,)).fetchone()
    job = c.execute("SELECT * FROM analysis_job WHERE id=%s", (gen['job_id'],)).fetchone()
    pointers = c.execute("SELECT * FROM derived_artifact WHERE generation_id=%s ORDER BY kind", (gid,)).fetchall()
    versions = c.execute("SELECT * FROM artifact_version WHERE generation_id=%s ORDER BY created_at,kind", (gid,)).fetchall()
    snapshots = c.execute("SELECT * FROM knowledge_snapshot WHERE generation_id=%s ORDER BY created_at", (gid,)).fetchall()
    queue = c.execute("SELECT * FROM rebuild_request WHERE generation_id=%s", (gid,)).fetchone()
    history = c.execute("SELECT * FROM knowledge_change WHERE generation_id=%s ORDER BY revision", (gid,)).fetchall()
    old = {}
    for table in ('claim', 'event', 'emotion', 'evidence', 'page_text', 'paragraph',
                  'character', 'character_mention', 'event_actor', 'review_item',
                  'contradiction', 'regression_run', 'report'):
        rows = c.execute(f"SELECT to_jsonb(t) AS row FROM {table} t JOIN generation_state s "
            "ON s.generation_id=t.generation_id WHERE s.origin='LEGACY_UNASSESSED' "
            "ORDER BY to_jsonb(t)::text").fetchall()
        old[table] = {'count': len(rows), 'sha256': digest(rows)}
    model_calls = c.execute("SELECT count(*) n FROM model_call WHERE generation_id=%s", (gid,)).fetchone()['n']

checks = []
api = {}


async def workflow_history():
    handle = (await jobs.temporal()).get_workflow_handle(job['workflow_id'])
    history = await handle.fetch_history()
    scheduled, steps, markers = {}, [], []
    for event in history.events:
        if event.HasField('activity_task_scheduled_event_attributes'):
            scheduled[event.event_id] = event.activity_task_scheduled_event_attributes.activity_type.name
            steps.append({'event': event.event_id, 'state': 'scheduled',
                          'activity': scheduled[event.event_id], 'time': str(event.event_time)})
        elif event.HasField('activity_task_completed_event_attributes'):
            sid = event.activity_task_completed_event_attributes.scheduled_event_id
            steps.append({'event': event.event_id, 'state': 'completed',
                          'activity': scheduled.get(sid), 'time': str(event.event_time)})
        elif event.HasField('marker_recorded_event_attributes'):
            for value in event.marker_recorded_event_attributes.details.values():
                markers.extend(p.data.decode(errors='replace') for p in value.payloads)
    return {'steps': steps, 'markers': markers}


workflow = asyncio.run(workflow_history())
checks.append({'check': 'temporal:verified_order_branch',
    'passed': any('verified-revision-outputs-v1' in m for m in workflow['markers'])})
for step in workflow['steps']:
    if step['activity'] == 'rebuild_outputs' and step['state'] == 'scheduled':
        completed = {s['activity'] for s in workflow['steps']
                     if s['state'] == 'completed' and s['event'] < step['event']}
        checks.append({'check': 'temporal:producers_before_outputs',
            'passed': {'resolve_identity', 'visual_identity', 'continuity_checks',
                       'emotions_themes', 'confirm_text_visual'} <= completed})

with httpx.Client(base_url='http://127.0.0.1:8000', timeout=60,
                  headers={'Authorization': 'Bearer ' + settings().gateway_internal_key}) as client:
    for pointer in pointers:
        kind = pointer['kind']
        response = client.get(f'/v1/generations/{gid}/artifacts/{kind}')
        response.raise_for_status()
        value = response.json()
        api[kind] = value
        eligible = [v for v in versions if v['kind'] == kind and v['build_key'] == pointer['build_key']
                    and v['input_revision'] == state['knowledge_revision']
                    and pointer['input_revision'] == state['knowledge_revision']
                    and state['validated_revision'] == state['knowledge_revision']
                    and pointer['state'] == 'READY']
        checks.append({'check': kind + ':availability', 'passed': value['available'] == bool(eligible)})
        if eligible:
            ref = eligible[0]
            checks.append({'check': kind + ':full_content', 'passed': value['artifact']['content'] == plain(ref['content'])})
            checks.append({'check': kind + ':build_key', 'passed': value['artifact']['build_key'] == ref['build_key']})

for version in versions:
    snap = next((s for s in snapshots if s['revision'] == version['input_revision']
                 and s['input_digest'] == version['input_digest']), None)
    checks.append({'check': version['kind'] + ':validation_before_output:' + version['build_key'],
                   'passed': snap is not None and snap['created_at'] <= version['created_at']})
    if snap and version['kind'] == 'report':
        checks.append({'check': 'report:canonical_events_emotions:' + version['build_key'],
            'passed': all(version['content'][k] == snap['content'][k] for k in ('events', 'emotions'))})

index = api.get('search_index', {})
qdrant_reference = None
if index.get('available'):
    from qdrant_client import models
    from editor.retrieval import qdrant

    artifact = index['artifact']
    snap = next(s for s in snapshots if s['input_digest'] == artifact['input_digest'])['content']
    expected = {}
    for page in snap['sources']:
        for span in page['spans']:
            expected[span['span_id']] = {'kind': 'paragraph', 'page_no': page['page_no'],
                'paragraph_idx': span['idx'], 'ref': span['span_id'], 'text': span['text'],
                'source_issues': page['issues']}
    for event in snap['events']:
        ref = 'event:' + event['id']
        expected[ref] = {'kind': 'event', 'page_no': event['page_from'], 'ref': ref,
                         'text': event['summary'], 'claim_id': event['claim_id']}
    for payload in expected.values():
        payload.update(generation_id=gid, build_key=artifact['build_key'], knowledge_revision=snap['revision'])

    async def read_index():
        rows, offset = [], None
        while True:
            batch, offset = await qdrant().scroll(artifact['content']['collection'], limit=100,
                offset=offset, with_payload=True, with_vectors=False,
                scroll_filter=models.Filter(must=[
                    models.FieldCondition(key='generation_id', match=models.MatchValue(value=gid)),
                    models.FieldCondition(key='build_key', match=models.MatchValue(value=artifact['build_key']))]))
            rows.extend(p.payload for p in batch)
            if offset is None:
                return rows

    actual = asyncio.run(read_index())
    by_ref = {p['ref']: p for p in actual}
    checks.append({'check': 'qdrant:full_payloads', 'passed': by_ref == expected and len(actual) == len(expected)})
    qdrant_reference = {'count': len(actual), 'expected_count': len(expected),
                        'payload_sha256': digest(by_ref), 'build_key': artifact['build_key']}

result = {'environment': 'tt-gpu/editor-control; real ed PostgreSQL; loopback control API',
    'timestamp': datetime.now(timezone.utc).isoformat(), 'stage': stage, 'generation_id': gid,
    'code_version': gen['code_version'], 'job': job, 'state': state, 'queue': queue,
    'pointers': pointers, 'versions': versions, 'snapshots': snapshots,
    'knowledge_changes': history, 'api': api, 'legacy_hashes': old, 'model_calls': model_calls,
    'qdrant_reference': qdrant_reference, 'workflow': workflow,
    'checks': checks, 'passed': sum(x['passed'] for x in checks),
    'failed': sum(not x['passed'] for x in checks), 'semantic_acceptance': False}
print(json.dumps(plain(result), ensure_ascii=False, indent=2))
if result['failed']:
    raise SystemExit(1)
