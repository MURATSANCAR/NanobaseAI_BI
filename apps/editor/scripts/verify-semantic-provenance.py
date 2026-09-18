#!/usr/bin/env python3
"""Compare delivered synthesis citations to every recorded supporting OCR span."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1];gen=str(uuid.UUID(sys.argv[1]))
base=os.environ.get('EDITOR_VERIFY_BASE_URL','http://127.0.0.1:8810')
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()};records={}
for kind in ('page_claims','semantic_reviews','semantic_synthesis'):
    rows=[]
    while True:
        req=urllib.request.Request(f'{base}/v1/generations/{gen}/{kind}?offset={len(rows)}&limit=100',headers=headers)
        with urllib.request.urlopen(req,timeout=60) as response:batch=json.load(response)
        rows+=batch['items']
        if not batch['has_more']:break
        assert batch['items'],'EMPTY_PAGINATION'
    records[kind]=rows
assert len(records['semantic_synthesis'])==1,'SYNTHESIS_NOT_COMPLETE'
assert records['page_claims'] and len(records['semantic_reviews'])==len(records['page_claims']),'PAGE_REVIEWS_NOT_COMPLETE'
query="SELECT json_agg(json_build_object('id',id,'kind',kind,'record_key',record_key,'data',data)) FROM editor.records WHERE generation_id='"+gen+"' AND kind IN ('page_claims','semantic_reviews','semantic_synthesis')"
reference=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],cwd=root))
by_id={r['id']:r for r in reference};assert len(reference)==sum(map(len,records.values()))
for kind,rows in records.items():
    for row in rows:
        assert by_id[row['id']]=={'kind':kind,**{k:row[k] for k in ('id','record_key','data')}},'API_PG_MISMATCH'
pages={r['data']['pdf_page']:r['data'] for r in records['page_claims']};claims={}
for row in records['semantic_reviews']:
    review=row['data'];page=pages[review['pdf_page']];candidates=page['claims']+page['blocked_claims']
    for verdict in review['claims']:
        if not verdict['eligible_for_synthesis']:continue
        candidate=candidates[verdict['candidate_ordinal']]
        claims[verdict['claim_id']]={'quoted':set(candidate['span_refs']),
            'support':set(verdict.get('model_result',{}).get('support_span_refs',[]))
                      |set(verdict.get('verified_support_span_refs',[])), 'page':review['pdf_page']}
gaps=[];statements=0
for row in records['semantic_synthesis']:
    for ordinal,statement in enumerate(row['data']['statements']):
        statements+=1;required=set()
        for claim_id in statement['claim_refs']:
            assert claim_id in claims,'UNKNOWN_SYNTHESIS_CLAIM'
            required|=claims[claim_id]['quoted']|claims[claim_id]['support']
        missing=required-set(statement['source_span_refs'])
        if missing:gaps.append({'statement_ordinal':ordinal,'claim_refs':statement['claim_refs'],
                               'missing_support_span_refs':sorted(missing)})
report={'generation_id':gen,'api':base,'api_pg_match':True,'application_writes':0,
    'semantic_acceptance':False,'eligible_claim_count':len(claims),'statement_count':statements,
    'claims_with_additional_support':sum(bool(c['support']-c['quoted']) for c in claims.values()),
    'citation_gaps':gaps,'source_support_coverage_passed':not gaps,
    'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
report['verification_id']=str(uuid.uuid4())
path=root/'evidence'/('semantic-provenance-'+gen+'-'+report['verifier_sha256'][:12]+'-'+report['verification_id']+'.json')
report['evidence']=str(path)
with path.open('x') as stream:json.dump(report,stream,indent=2)
print(json.dumps(report));sys.exit(1 if gaps else 0)
