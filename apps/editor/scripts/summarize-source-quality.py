#!/usr/bin/env python3
"""Read actual API records, match PostgreSQL, and report unresolved coverage."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1]
generation=str(uuid.UUID(sys.argv[1]))
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
kinds=('source_spans','page_claims','figure_identity','semantic_reviews','semantic_synthesis')
records={}
for kind in kinds:
    rows=[]
    while True:
        request=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}/{kind}?limit=100&offset={len(rows)}',headers=headers)
        with urllib.request.urlopen(request,timeout=60) as response:batch=json.load(response)
        rows.extend(batch['items'])
        if not batch['has_more']:break
        assert batch['items'],'EMPTY_PAGINATION'
    records[kind]=rows
code='''import json,sys
from editor.config import connection
with connection() as db:
 rows=db.execute('SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s AND kind=ANY(%s)',(sys.argv[1],sys.argv[2:])).fetchall()
print(json.dumps(rows,default=str))
'''
database=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,generation,*kinds],cwd=root))
for kind in kinds:
    expected={r['id']:{'id':r['id'],'record_key':r['record_key'],'data':r['data']} for r in database if r['kind']==kind}
    assert {r['id']:r for r in records[kind]}==expected,'API_PG_MISMATCH:'+kind
spans=[r['data'] for r in records['source_spans']]
claims={r['data']['pdf_page']:r['data'] for r in records['page_claims']}
identities={r['data']['pdf_page']:r['data'] for r in records['figure_identity']}
reviews={r['data']['pdf_page']:r['data'] for r in records['semantic_reviews']}
pages=[]
for page in sorted({s['pdf_page'] for s in spans}|set(claims)):
    source=[s for s in spans if s['pdf_page']==page]
    review=reviews.get(page,{})
    identity=identities.get(page,{})
    pages.append({'pdf_page':page,'page_role':claims.get(page,{}).get('page_role'),
        'source_statuses':dict(Counter(s['status'] for s in source)),
        'unresolved_source_roles':dict(Counter(s['role'] for s in source if s['status']!='TEXT_AGREED')),
        'claim_count':len(claims.get(page,{}).get('claims',[]))+len(claims.get(page,{}).get('blocked_claims',[])),
        'reviewed_claims':len(review.get('claims',[])),
        'synthesis_eligible_claims':sum(v.get('eligible_for_synthesis') is True for v in review.get('claims',[])),
        'review_reasons':dict(Counter(v.get('reason','MISSING_REASON') for v in review.get('claims',[]) if not v.get('eligible_for_synthesis'))),
        'identity_links':len(identity.get('links',[])),
        'verified_local_identity_links':sum(v.get('visual_identity_verified') is True for v in identity.get('links',[])),
        'identity_reasons':dict(Counter(v.get('reason',v.get('status','UNRESOLVED')) for v in identity.get('links',[]) if not v.get('visual_identity_verified')))})
report={'generation_id':generation,'api_pg_match':True,'application_writes':0,
        'semantic_acceptance':False,'page_count':len(pages),
        'source_statuses':dict(Counter(s['status'] for s in spans)),
        'review_reasons':dict(sum((Counter(p['review_reasons']) for p in pages),Counter())),
        'eligible_claims':sum(p['synthesis_eligible_claims'] for p in pages),
        'verified_local_identity_links':sum(p['verified_local_identity_links'] for p in pages),
        'synthesis_statements':sum(len(r['data'].get('statements',[])) for r in records['semantic_synthesis']),
        'pages':pages}
target=root/'evidence'/('source-quality-'+generation+'.json')
target.write_text(json.dumps(report,ensure_ascii=False,indent=2));target.chmod(0o600)
print(json.dumps({k:v for k,v in report.items() if k!='pages'},ensure_ascii=False))
