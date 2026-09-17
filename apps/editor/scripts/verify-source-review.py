#!/usr/bin/env python3
"""Verify the real source-review API against independent PostgreSQL counts.

Run on the deployment host. No fixtures, expected book answers or data writes.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

root = Path(__file__).resolve().parents[1]
os.chdir(root)
run = json.loads((root/'evidence/source-spans-run.json').read_text())
gen = run['generation_id']
headers = {'Authorization': 'Bearer '+(root/'secrets/api_token').read_text().strip()}
base = os.environ.get('EDITOR_VERIFY_BASE_URL', 'http://127.0.0.1:8810')


def request(path, authorized=True):
    req = urllib.request.Request(base+path, headers=headers if authorized else {})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def sql(query):
    return json.loads(subprocess.check_output([
        'docker', 'compose', 'exec', '-T', 'postgres', 'psql', '-U', 'postgres',
        '-d', 'editor', '-Atc', query], text=True))


def fingerprint():
    return sql("SELECT json_build_object('records',md5(COALESCE(string_agg(id::text||data::text,'' ORDER BY id),'')),'count',count(*)) FROM editor.records WHERE generation_id='"+gen+"'")


before = fingerprint()
path = '/v1/generations/'+gen+'/source-review'
try:
    request(path, False)
    raise AssertionError('UNAUTHENTICATED_ACCESS')
except urllib.error.HTTPError as exc:
    assert exc.code == 401
report = request(path)
assert not report['semantic_acceptance'] and report['application_writes'] == 0
db = sql("SELECT json_agg(json_build_object('id',id,'kind',kind,'record_key',record_key,'data',data) ORDER BY kind,record_key) FROM editor.records WHERE generation_id='"+gen+"' AND kind IN ('source_spans','layout_regions','visual_observations')")
spans = [r for r in db if r['kind'] == 'source_spans']
issues = Counter(i for r in spans if r['data']['status'] != 'TEXT_AGREED' for i in r['data']['issues'])
assert report['source_spans'] == len(spans)
assert report['agreed_spans'] == sum(r['data']['status'] == 'TEXT_AGREED' for r in spans)
assert report['review_spans'] == len(spans)-report['agreed_spans']
assert report['issue_counts'] == dict(issues)
checks = []; speaker_reasons = Counter()
for n, page in enumerate(report['pages'], 1):
    number = page['pdf_page']
    expected = [r for r in spans if r['data']['pdf_page'] == number and r['data']['status'] != 'TEXT_AGREED']
    assert {r['span_id'] for r in page['regions']} == {r['id'] for r in expected}
    for region in page['regions']:
        original = next(r['data'] for r in expected if r['id'] == region['span_id'])
        assert region['bbox'] == original['bbox'] and region['issues'] == original['issues']
    single = request(path+'?pdf_page='+str(number))
    assert single['pages'] == [page]
    for candidate in page['speakers']:
        assert candidate['speaker'] is None and not candidate['eligible_for_synthesis']
        speaker_reasons[candidate['reason']] += 1
        # Independently check every returned hit against original crop coordinates.
        visual = next(r['data'] for r in db if r['kind'] == 'visual_observations' and r['data']['pdf_page'] == number)
        for hit in candidate['tail_figure_hits']:
            obs_ref, fig_ref = hit['figure_ref'].split('/')
            obs = visual['observations'][int(obs_ref.split('-')[1])]
            figure = obs['figures'][int(fig_ref.split('-')[1])]
            crop, box = obs['region_bbox'], figure['bbox']
            mapped = [crop[0]+crop[2]*box[0], crop[1]+crop[3]*box[1], crop[2]*box[2], crop[3]*box[3]]
            assert hit['bbox'] == mapped
            assert all(mapped[i] <= hit['tip'][i] <= mapped[i]+mapped[i+2] for i in (0, 1))
    checks.append({'page': number, 'api_pg_equal': True, 'filtered_api_equal': True})
    if n % 10 == 0:
        print(json.dumps({'checked_pages': n, 'passed': n, 'failed': 0, 'semantic_acceptance': False}), flush=True)
assert before == fingerprint(), 'SOURCE_RECORDS_CHANGED'
result = {'generation_id': gen, 'checked_at': datetime.now(timezone.utc).isoformat(),
          'checks': checks, 'source_spans': report['source_spans'],
          'agreed_spans': report['agreed_spans'], 'review_spans': report['review_spans'],
          'issue_counts': dict(issues), 'speaker_reasons': dict(speaker_reasons),
          'source_records_unchanged': True, 'unauthorized_status': 401,
          'semantic_acceptance': False}
(root/'evidence/source-review-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({k: v for k, v in result.items() if k != 'checks'}, ensure_ascii=False), flush=True)
