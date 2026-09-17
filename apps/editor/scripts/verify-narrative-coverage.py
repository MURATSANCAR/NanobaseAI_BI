#!/usr/bin/env python3
"""Real deployed narrative/coverage invariants, independently read from API/PG."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid
from datetime import datetime,timezone

root=Path(os.environ['EDITOR_VERIFY_ROOT']);os.chdir(root)
run=json.loads(Path(os.environ['EDITOR_VERIFY_RUN_FILE']).read_text());gen=str(uuid.UUID(run['generation_id']))
base=os.environ['EDITOR_VERIFY_BASE_URL'];headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
def rows(g,kind,page):
    items=[]
    while True:
        with urllib.request.urlopen(urllib.request.Request(f'{base}/v1/generations/{g}/{kind}?pdf_page={page}&offset={len(items)}&limit=100',headers=headers),timeout=60) as response:b=json.load(response)
        items+=b['items']
        if not b['has_more']:break
        assert b['items']
    q=f"SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='{g}' AND kind='{kind}' AND data->>'pdf_page'='{page}'"
    db=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',q],text=True));assert db==items
    return items
pages=run.get('priority_pages')
assert pages,'EXPLICIT_PAGE_SCOPE_REQUIRED'
results=[]
for page in pages:
    checks=rows(gen,'page_checks',page)
    if not checks:
        results.append({'page':page,'status':'PENDING'});continue
    claims=rows(gen,'page_claims',page)[0]['data'];visual=rows(gen,'visual_observations',page)[0]['data'];layout=rows(gen,'layout_regions',page)[0]['data']
    reading=rows(gen,'page_readings',page)[0]['data'];spans=rows(gen,'source_spans',page)
    parent=str(uuid.UUID(reading['reused_from_generation'])) if reading.get('reused_from_generation') else None
    previous={r['record_key']:r for r in rows(parent,'source_spans',page)} if parent else {}
    from reread_artifact_reference import verify_artifacts
    source_evidence=rows(gen,'evidence',page)
    assert len(source_evidence)==1
    artifact_proof=verify_artifacts(spans,source_evidence[0]['data'],gen)
    for r in spans:
        if parent is None:
            assert r['data'].get('reused_source_span_id') is None
            continue
        old=previous[r['record_key']];assert r['data']['reused_source_span_id']==old['id']
        for field in ('raw_text','bbox','region_text','secondary_text','pdf_text','reread_measurement'):
            if field=='reread_measurement' and r['data'].get('reread_generated_in_generation'):
                assert r['data']['pipeline_version']=='source-spans-v10'
                assert r['data']['reread_provenance']['generation_id']==gen
                continue
            assert r['data'][field]==old['data'][field],field
    candidates=claims['claims']+claims['blocked_claims'];closed=claims['page_role'] not in ('NARRATIVE','MIXED')
    for c in candidates:
        assert c['eligible_for_synthesis'] is False
        if closed:assert c['source_gate'] in ('NON_NARRATIVE_CLAIM_BLOCKED','INVALID_PAGE_ROLE')
    if closed:assert not claims['claims']
    pictures=[r for r in layout['regions'] if r['type']=='PICTURE'];coverage=visual['coverage'];assert len(coverage['regions'])==len(pictures)
    assert coverage['whole_page_visual_coverage']==coverage['figure_coverage']=='NOT_VERIFIED'
    large=[r for r in pictures if r['bbox'][2]*r['bbox'][3]>.06][:3]
    for region,picture in zip(coverage['regions'],pictures):
        assert region['bbox']==picture['bbox'] and region['source_ref']==picture.get('source_ref')
        reason=('BELOW_MINIMUM_AREA' if picture['bbox'][2]*picture['bbox'][3]<=.06 else
                'REGION_BUDGET_LIMIT' if picture not in large else
                None if any(o['region_bbox']==picture['bbox'] for o in visual['observations']) else 'OBSERVATION_MISSING')
        assert region['reason']==reason
    assert visual['omitted_regions']==sum(r['status']=='UNOBSERVED' for r in coverage['regions'])
    assert rows(gen,'source_spans',page)==spans
    results.append({'page':page,'status':'PASS','page_role':claims['page_role'],'claims':len(candidates),
                    'blocked':len(claims['blocked_claims']),'matched':len(claims['claims']),
                    'omitted_regions':visual['omitted_regions'],'parent_generation':parent,
                    'parent_raw_source_unchanged':True if parent else None,'artifact_proof':artifact_proof})
q=f"SELECT count(*) FROM editor.reviews WHERE generation_id='{gen}'"
assert int(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',q],text=True))==0
report={'generation_id':gen,'api':base,'pages':results,'api_pg_equal':True,'manual_reviews':0,'application_writes':0,
        'semantic_acceptance':False,'status':'PASS' if all(r['status']=='PASS' for r in results) else 'PENDING'}
p=root/'evidence'/('narrative-coverage-integration-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json');p.write_text(json.dumps(report,indent=2));print(json.dumps({**report,'evidence':str(p)},indent=2))
