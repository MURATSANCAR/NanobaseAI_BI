#!/usr/bin/env python3
"""Bounded read-only actual API/PG local-identity blocker classification."""
import collections
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
import uuid

assert sys.platform.startswith('linux') and socket.gethostname()==os.environ['EDITOR_VERIFY_REMOTE_HOST']
root=Path(os.environ['EDITOR_VERIFY_ROOT']);gen=str(uuid.UUID(sys.argv[1]))
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
def pg(sql):
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',sql],cwd=root))
def state():
    return pg("SELECT json_build_object('records',(SELECT md5(string_agg(md5(row_to_json(r)::text),'' ORDER BY id)) FROM editor.records r WHERE generation_id='"+gen+"'),'reviews',(SELECT md5(string_agg(md5(row_to_json(r)::text),'' ORDER BY id)) FROM editor.reviews r WHERE generation_id='"+gen+"'))")
before=state();records={}
for kind in ('figure_identity','character_evidence','layout_regions','source_spans'):
    rows=[]
    while True:
        req=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{gen}/{kind}?offset={len(rows)}&limit=100',headers=headers)
        with urllib.request.urlopen(req,timeout=120) as response:batch=json.load(response)
        rows.extend(batch['items']);assert len(rows)<=10000,'BOUNDED_RECORD_LIMIT'
        if not batch['has_more']:break
        assert batch['items']
    reference=pg("SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data)),'[]'::json) FROM editor.records WHERE generation_id='"+gen+"' AND kind='"+kind+"'")
    assert {r['id']:r for r in rows}=={r['id']:r for r in reference},'API_PG_MISMATCH'
    records[kind]=rows
def contained(a,b):
    return isinstance(a,list) and isinstance(b,list) and len(a)==len(b)==4 and a[2]>0 and a[3]>0 and b[2]>0 and b[3]>0 and b[0]<=a[0] and b[1]<=a[1] and a[0]+a[2]<=b[0]+b[2] and a[1]+a[3]<=b[1]+b[3]
by_page={kind:{r['data']['pdf_page']:r for r in records[kind]} for kind in ('figure_identity','character_evidence','layout_regions')}
counts=collections.Counter();reasons=collections.Counter();details=[];attributions=0;pages_with_attrs=0
for page,row in sorted(by_page['figure_identity'].items()):
    identity=row['data'];attr=by_page['character_evidence'][page];layout=by_page['layout_regions'][page]
    spans={r['id']:r['data'] for r in records['source_spans'] if r['data']['pdf_page']==page}
    entries=attr['data'].get('attributions',[]);attributions+=len(entries);pages_with_attrs+=bool(entries)
    links=identity['links'];counts['pages']+=1;counts['links']+=len(links)
    counts['named_anchors']+=identity['named_identity_count'];counts['pages_without_balloon_links']+=not links
    counts['role_gate_blocked_pages']+=not identity.get('page_purpose_gate',{}).get('passed',False)
    assert len(links)==len(layout['data'].get('balloon_candidates',[])), 'LAYOUT_IDENTITY_LINK_COUNT_MISMATCH'
    for link in links:
        reasons[link['reason']]+=1;diagnosis=[];matching=[];valid=[]
        if not identity.get('page_purpose_gate',{}).get('passed') or attr['data'].get('page_role')!='NARRATIVE':diagnosis.append('ROLE_GATE')
        if not link.get('local_figure_candidate'):
            diagnosis.append('MULTIPLE_TAIL_OR_FIGURE' if link['reason']=='AMBIGUOUS_TAIL_OR_FIGURE' else 'TAIL_OR_FIGURE_UNAVAILABLE')
        for ordinal,entry in enumerate(entries):
            refs=entry.get('source_span_refs',[]);quoted=entry.get('quote_span_refs',[])
            if not refs or not quoted or not set(quoted)<=set(refs):continue
            if any(ref not in spans or spans[ref]['status']!='TEXT_AGREED' or spans[ref]['role']!='TEXT' for ref in refs):continue
            if len({spans[ref]['render_sha256'] for ref in refs})!=1:continue
            valid.append(ordinal)
            owners=[b for b in layout['data'].get('balloon_candidates',[]) if all(contained(spans[ref]['bbox'],b.get('bbox')) for ref in quoted)]
            if len(owners)==1 and all(contained(spans[ref]['bbox'],link.get('bbox')) for ref in quoted):matching.append(ordinal)
        if not entries:diagnosis.append('NO_EXPLICIT_ATTRIBUTION')
        elif not valid:diagnosis.append('ATTRIBUTION_SOURCE_NOT_AGREED_OR_INVALID')
        elif not matching:diagnosis.append('QUOTE_BALLOON_MISMATCH_OR_MULTIPLE_OWNER')
        elif len(matching)>1:diagnosis.append('MULTIPLE_MATCHING_ATTRIBUTIONS')
        if layout['data'].get('balloons_truncated'):diagnosis.append('BALLOONS_TRUNCATED')
        if link.get('visual_identity_verified'):diagnosis.append('SOURCE_GROUNDED')
        elif not diagnosis:diagnosis.append('UNEXPLAINED_BLOCKER')
        for category in diagnosis:counts[category]+=1
        details.append({'pdf_page':page,'identity_record_id':row['id'],'layout_record_id':layout['id'],'attribution_record_id':attr['id'],
                        'balloon_index':link['balloon_index'],'recorded_reason':link['reason'],'categories':diagnosis,
                        'attribution_count':len(entries),'valid_attribution_count':len(valid),'matching_attribution_count':len(matching),
                        'page_purpose_passed':identity.get('page_purpose_gate',{}).get('passed'),
                        'attribution_page_role':attr['data'].get('page_role'),
                        'tail_hit_count':len(link.get('tail_figure_hits',[])),'local_figure_candidate_present':bool(link.get('local_figure_candidate'))})
after=state();assert before==after,'SOURCE_CHANGED_DURING_AUDIT'
report={'status':'PASS','scope':'STRUCTURAL_BLOCKER_CLASSIFICATION_NOT_IDENTITY_ACCEPTANCE','generation_id':gen,
        'api_pg_match':True,'protected_before':before,'protected_after':after,'counts':dict(counts),'recorded_reasons':dict(reasons),
        'attributions':attributions,'pages_with_attributions':pages_with_attrs,'details':details,'model_calls':0,'application_writes':0,
        'semantic_acceptance':False,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
out=root/'evidence'/('identity-blocker-audit-'+str(uuid.uuid4())+'.json')
with out.open('x') as f:json.dump(report,f,indent=2)
out.chmod(0o600);print(json.dumps({'evidence':str(out),'counts':dict(counts),'recorded_reasons':dict(reasons),'attributions':attributions,'pages_with_attributions':pages_with_attrs}))
