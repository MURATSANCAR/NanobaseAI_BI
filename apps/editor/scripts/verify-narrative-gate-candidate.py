#!/usr/bin/env python3
"""Read-only real API/PG candidate measurement, never editorial acceptance."""
import ast
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid

root=Path(os.environ['EDITOR_VERIFY_ROOT']);os.chdir(root)
run=json.loads(Path(os.environ['EDITOR_VERIFY_RUN_FILE']).read_text())
generation=str(uuid.UUID(run['generation_id']))
base=os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/')
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
code=Path(os.environ['EDITOR_VERIFY_CANDIDATE_CODE']).read_text()
tree=ast.parse(code)
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='narrative_gate')
namespace={};exec(compile(ast.Module(body=[function],type_ignores=[]),'<narrative-gate-candidate>','exec'),namespace)
candidate=namespace['narrative_gate']


def rows(kind,page=None):
    items=[]
    while True:
        url=f'{base}/v1/generations/{generation}/{kind}?offset={len(items)}&limit=100'+(f'&pdf_page={page}' if page is not None else '')
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as response:batch=json.load(response)
        items.extend(batch['items'])
        if not batch['has_more']:return items
        assert batch['items'],'EMPTY_PAGINATION'


def pg(page):
    query=("SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) "
           f"ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='{generation}' AND kind='page_claims' AND data->>'pdf_page'='{page}'")
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))


pages=sorted({row['data']['pdf_page'] for row in rows('page_checks')})
assert pages,'NO_COMPLETED_PAGES'
snapshots={};checks=[];counts=Counter();roles={}
for page in pages:
    actual=rows('page_claims',page);assert actual==pg(page) and len(actual)==1
    snapshots[page]=actual
    row=actual[0];data=row['data'];role=data['page_role'];summary=roles.setdefault(role,Counter())
    for bucket in ('claims','blocked_claims'):
        for index,claim in enumerate(data[bucket]):
            original=claim['source_gate'];decision=candidate(role,original)
            # Independently specified closed role allowlist; do not call product
            # extractors or use book text/expected names to construct a reference.
            expected=(original if role in {'NARRATIVE','MIXED'} else
                      'NON_NARRATIVE_CLAIM_BLOCKED' if role in {'ACTIVITY','FRONT_MATTER','APPENDIX','UNKNOWN'} else 'INVALID_PAGE_ROLE')
            assert decision==expected
            assert claim['eligible_for_synthesis'] is False
            summary['claims']+=1;counts['claims']+=1
            if original=='MATCH':summary['prior_match']+=1
            if original=='MATCH' and decision!='MATCH':summary['newly_blocked_match']+=1;counts['newly_blocked_match']+=1
            if role in {'NARRATIVE','MIXED'}:
                assert decision==original,'NARRATIVE_GATE_REGRESSION'
                counts['narrative_mixed_unchanged']+=1
            else:summary['closed_role_candidates']+=1;counts['closed_role_candidates']+=1
            checks.append({'page':page,'page_claims_id':row['id'],'bucket':bucket,'index':index,
                           'kind':claim['kind'],'page_role':role,'old_gate':original,'candidate_gate':decision})
for page,previous in snapshots.items():assert pg(page)==previous,'IMMUTABLE_PAGE_CHANGED'
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
report={'generation_id':generation,'api':base,'completed_pages':len(pages),'pages':pages,
        'api_pg_equal':True,'source_records_unchanged':True,'independent_reference_equal':True,
        'counts':dict(counts),'roles':{role:dict(value) for role,value in roles.items()},'checks':checks,
        'record_snapshot_sha256':hashlib.sha256(json.dumps(snapshots,sort_keys=True).encode()).hexdigest(),
        'candidate_function_sha256':hashlib.sha256(ast.get_source_segment(code,function).encode()).hexdigest(),
        'inference_calls':0,'source_or_review_writes':0,'production_installed':False,'end_to_end_acceptance':False}
destination=root/'evidence'/('narrative-gate-candidate-'+stamp+'.json')
destination.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='checks'}|{'evidence':str(destination)},ensure_ascii=False,indent=2))
