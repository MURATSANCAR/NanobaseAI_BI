#!/usr/bin/env python3
"""Read-only remote impact API acceptance against independent real PostgreSQL.

Checks declared edge witnesses and pagination; not a complete semantic graph.
No production graph helper imports, fake records, mutations or model requests.
"""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from urllib.parse import urlencode, urlparse
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone

def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)

require(sys.platform.startswith('linux') and os.environ.get('EDITOR_VERIFY_REMOTE_HOST')==socket.gethostname(), 'Explicit remote Linux host required')
root=Path(os.environ.get('EDITOR_VERIFY_ROOT',Path(__file__).resolve().parents[1])).resolve()
generation=str(uuid.UUID(os.environ['EDITOR_VERIFY_GENERATION_ID']))
target=str(uuid.UUID(os.environ['EDITOR_VERIFY_IMPACT_RECORD_ID']))
base=os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/')
require(urlparse(base).hostname in ('localhost','127.0.0.1','::1'),'Remote loopback API required')
token=(root/'secrets/api_token').read_text().strip()
report={'status':'RUNNING','generation_id':generation,'target_id':target,'api':base,
        'source_or_review_writes':0,'model_calls':0,'semantic_acceptance':False,'complete':False,
        'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
destination=root/'evidence'/('source-impact-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')

def pg(query):
    try:
        raw=subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],cwd=root,text=True,stderr=subprocess.PIPE)
    except subprocess.CalledProcessError:
        raise RuntimeError('Independent PG command failed; stderr suppressed') from None
    return json.loads(raw)

def get(offset=0, snapshot=None):
    params={'offset':offset,'limit':50}
    if snapshot:
        params['expected_snapshot_sha256']=snapshot
    request=urllib.request.Request(f'{base}/v1/generations/{generation}/records/{target}/impact?'+urlencode(params),headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(request,timeout=180) as response:
        return json.load(response)

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

try:
    raw=pg(f"SELECT COALESCE(json_agg(json_build_object('id',id,'kind',kind,'record_key',record_key,'data',data) ORDER BY kind,record_key,id),'[]'::json) FROM editor.records WHERE generation_id='{generation}'")
    rows={row['id']:row for row in raw};require(target in rows,'Target absent from selected real generation')
    raw_reviews=pg(f"SELECT COALESCE(json_agg(row_to_json(r)),'[]'::json) FROM (SELECT DISTINCT ON(target_id) target_id,decision,version FROM editor.reviews WHERE generation_id='{generation}' ORDER BY target_id,version DESC) r")
    reviews={row['target_id']:row for row in raw_reviews}
    response=get();snapshot=response['snapshot_sha256'];report['snapshot_sha256']=snapshot
    first=response;items=[]
    while True:
        require(response['generation_id']==generation and response['target']['id']==target
                and response['snapshot_sha256']==snapshot and response['offset']==len(items)
                and response['total']==first['total'] and response['target']==first['target']
                and response['graph_scope']=='SOURCE_DEPENDENCIES' and response['complete'] is False
                and response['semantic_acceptance'] is False,'Impact response/snapshot contract mismatch')
        require(len(response['items'])<=50,'Page exceeded requested size')
        items.extend(response['items'])
        if not response['has_more']:
            break
        require(response['items'],'Empty nonterminal impact page')
        response=get(len(items),snapshot)
    require(len(items)==first['total'] and len({item['id'] for item in items})==len(items)
            and target not in {item['id'] for item in items},'Impact count/duplicate/self reference mismatch')
    delivered={target:{**first['target'],'distance':0},**{item['id']:item for item in items}}
    owners={}
    for row in raw:
        if row['kind']=='page_claims':
            d=row['data']
            for ordinal,candidate in enumerate(d.get('claims',[])+d.get('blocked_claims',[])):
                if not isinstance(candidate,dict):continue
                claim={key:candidate.get(key) for key in ('kind','text','quote','span_refs','actor','speaker','narrative_mode','polarity')}
                cid=digest({'pdf_page':d.get('pdf_page'),'ordinal':ordinal,'claim':claim})
                owners.setdefault(cid,set()).add(row['id'])
    for row in raw:
        if row['kind']=='semantic_reviews':
            for claim in row['data'].get('claims',[]):
                if claim.get('claim_id') in owners:owners[claim['claim_id']].add(row['id'])
    def has_reference(value,wanted):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('metrics','model_result','raw_model_result','proposal','measurement','stored_vectors','blocked_claims','blocked_statements'):
                    continue
                if key=='passage_hashes' and wanted in item:return True
                if key=='retrieved_passages' and any(p.get('id')==wanted for p in item):return True
                if key in ('record_id','span_id','evidence_ref','parent_source_span_id','semantic_review_ref','page_claims_ref','passage_id') and item==wanted:return True
                if key in ('evidence_refs','span_refs','source_span_refs','quote_span_refs','support_span_refs','verified_support_span_refs','speaker_source_span_refs','supported_quote_span_refs','input_span_ids','span_ids','source_span_ids','dependency_refs','anchor_text_span_refs') and isinstance(item,list) and wanted in item:return True
                if has_reference(item,wanted):return True
        if isinstance(value,list):return any(has_reference(item,wanted) for item in value)
        return False
    def has_owned_claim(value,wanted):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('claim_id','claim_ids','claim_refs'):
                    refs=item if isinstance(item,list) else [item]
                    if any(wanted in owners.get(ref,set()) for ref in refs if isinstance(ref,str)):return True
                elif key not in ('metrics','model_result','raw_model_result','proposal','blocked_claims','blocked_statements') and has_owned_claim(item,wanted):return True
        elif isinstance(value,list):return any(has_owned_claim(item,wanted) for item in value)
        return False
    source_kinds={'evidence','layout_regions','source_spans','source_fragments','page_claims','page_context_roles','semantic_reviews'}
    relations=0
    for rid,item in delivered.items():
        require(rid in rows and item['kind']==rows[rid]['kind'] and item['record_key']==rows[rid]['record_key'], 'Impact item differs from independent PG')
        require(item['state'] in ('CURRENT','STALE','UNRESOLVED') and item['reasons'], 'Impact structural state missing')
        if reviews.get(rid,{}).get('decision') in ('REJECT','NEEDS_REVIEW'):
            require(item['state']=='STALE','Explicit review mismatch not reflected')
        if rid==target:continue
        require(type(item['distance']) is int and item['distance']>0 and item['relations'],'Impact path missing')
        for relation in item['relations']:
            parent=relation['record_id'];basis=relation['basis']
            require(parent in delivered and delivered[parent]['distance']+1==item['distance'],'Impact distance does not follow a delivered path')
            d=rows[rid]['data'];p=rows[parent]['data'];kind=rows[rid]['kind']
            if basis=='EXPLICIT_REFERENCE':
                valid=has_reference(d,parent) or (kind=='answers' and rows[parent]['kind']=='source_index' and d.get('source_index_input_sha256')==p.get('input_sha256'))
            elif basis=='CLAIM_OWNERSHIP':valid=has_owned_claim(d,parent)
            elif basis=='SAME_PAGE_RECORD_SCOPE':valid=kind=='semantic_reviews' and rows[parent]['kind']=='page_claims' and d.get('pdf_page')==p.get('pdf_page')
            elif basis=='INFERRED_PAGE_CONTEXT_INPUT':valid=kind=='page_context_roles' and rows[parent]['kind'] in ('evidence','layout_regions','source_spans','source_fragments') and abs(d.get('pdf_page',-1000)-p.get('pdf_page',1000))<=1
            elif basis=='CANONICAL_SNAPSHOT_INPUT':valid=(kind in ('source_passages','source_index') and rows[parent]['kind'] in source_kinds) or (kind=='semantic_synthesis' and rows[parent]['kind'] in ('page_claims','semantic_reviews'))
            else:valid=False
            require(valid,'Relation has no independent stored-source witness:'+basis)
            relations+=1
    require(get(0,snapshot)==first,'Pinned first page changed after traversal')
    route=f'/v1/generations/{generation}/records/{target}/impact'
    foreign=pg(f"SELECT to_json(id) FROM editor.records WHERE generation_id<>'{generation}' ORDER BY id LIMIT 1")
    require(foreign,'A real foreign-generation record is required for scope validation')
    guards=[('authentication',route,False,401),
            ('foreign_record',f'/v1/generations/{generation}/records/{foreign}/impact',True,404),
            ('snapshot_required',route+'?offset=1',True,400),
            ('snapshot_changed',route+'?expected_snapshot_sha256='+('0'*64 if snapshot!='0'*64 else '1'*64),True,409),
            ('limit_bound',route+'?limit=101',True,400)]
    guard_results={}
    for name,path,authenticated,expected in guards:
        request=urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token} if authenticated else {})
        try:
            with urllib.request.urlopen(request,timeout=180) as result:status=result.status
        except urllib.error.HTTPError as error:status=error.code
        require(status==expected,'Read-only API guard failed:'+name)
        guard_results[name]=status
    report.update(status='PASS',records_verified=len(delivered),relations_verified=relations,impacted_records=len(items),
                  target=first['target'],source_record_count=len(raw),snapshot_pagination_verified=True,
                  readonly_guard_checks=guard_results,
                  limitations=['Checks declared paths and scoped edges, not exhaustive semantic dependencies or all structural hash predicates.'])
except Exception as error:
    report.update(status='FAILED',reason=str(error).replace(token,'[REDACTED]'),error_type=type(error).__name__)
finally:
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({key:report[key] for key in ('status','generation_id','target_id','snapshot_sha256','reason') if key in report}|{'evidence':str(destination)}))
if report['status']!='PASS':raise SystemExit(1)
