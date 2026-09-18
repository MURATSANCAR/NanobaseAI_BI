#!/usr/bin/env python3
"""Remote real API/PG integrity acceptance for derived identity and semantics.

This checks scope, immutable inputs and gates, not human literary correctness.
"""
import base64
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid
import unicodedata
from source_obligation_reference import verify_obligations
from source_qualification_reference import verify_qualification
from source_role_reference import verify_role_bindings

root = Path(__file__).resolve().parents[1]
os.chdir(root)
generation = str(uuid.UUID(sys.argv[1]))
base = os.environ.get('EDITOR_VERIFY_BASE_URL', 'http://127.0.0.1:8810')
headers = {'Authorization': 'Bearer ' + (root/'secrets/api_token').read_text().strip()}
kinds = ('evidence', 'layout_regions', 'source_spans', 'page_claims', 'figure_identity', 'figure_comparisons',
         'semantic_reviews', 'semantic_synthesis')
extended = '--fragments' in sys.argv
if extended:
    kinds += ('source_fragments','fragment_checks','page_context_roles','cross_page_attributions')
def read(kind):
    rows = []
    while True:
        request = urllib.request.Request(f'{base}/v1/generations/{generation}/{kind}?limit=100&offset={len(rows)}', headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            batch = json.load(response)
        rows.extend(batch['items'])
        if not batch['has_more']:
            return rows
        assert batch['items'], 'EMPTY_PAGINATION'

api = {kind: read(kind) for kind in kinds}
code = '''import json,sys
from editor.config import connection
with connection() as db:
 rows=db.execute('SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s AND kind=ANY(%s)',(sys.argv[1],sys.argv[2:])).fetchall()
print(json.dumps(rows,default=str))
'''
database = json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,generation,*kinds]))
for kind in kinds:
    expected = {r['id']: {'id':r['id'],'record_key':r['record_key'],'data':r['data']} for r in database if r['kind']==kind}
    assert {r['id']:r for r in api[kind]} == expected, 'API_PG_MISMATCH:'+kind

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def verify_surface_references(claim,views,gate):
    assert gate['version']=='surface-reference-v1' and gate['passed'] is True
    assert gate['semantic_acceptance'] is False and gate['missing_terms']==[]
    def words(text):
        value=unicodedata.normalize('NFKC',text).replace('İ','i').replace('I','ı').lower()
        return re.findall(r'[^\W_]+',value)
    cited=set(words('\n'.join(view['reading_text'] for view in views)))
    text=unicodedata.normalize('NFC',claim['text']);expected=[]
    for match in re.finditer(r"[^\W\d_]+(?:['’ʼ][^\W\d_]+)?",text):
        token=match.group();root=re.split("['’ʼ]",token,maxsplit=1)[0]
        if len(root)<2 or not root[0].isupper():continue
        before=text[:match.start()].rstrip().rstrip('"“”\'‘’(').rstrip()
        if (not before or before[-1] in '.!?…:') and token==root:continue
        normalized=words(root)
        if len(normalized)!=1:continue
        assert normalized[0] in cited,'NAMED_REFERENCE_NOT_IN_CITED_SOURCE'
        expected.append({'term':root,'normalized_root':normalized[0],'present_in_cited_source':True})
    assert gate['checked']==expected,'NAMED_REFERENCE_GATE_COVERAGE_MISMATCH'
pages = {r['data']['pdf_page']:r['data'] for r in api['page_claims']}
assert pages and api['semantic_reviews'] and api['figure_identity'], 'DERIVED_ANALYSIS_NOT_READY'
expected_pages = {r['data']['pdf_page'] for r in api['evidence']}
assert set(pages) == expected_pages, 'PAGE_CLAIMS_INCOMPLETE'
assert {r['data']['pdf_page'] for r in api['semantic_reviews']} == expected_pages, 'SEMANTIC_REVIEWS_INCOMPLETE'
assert {r['data']['pdf_page'] for r in api['figure_identity']} == expected_pages, 'IDENTITY_PASS_INCOMPLETE'
assert len(api['semantic_synthesis']) == 1, 'SYNTHESIS_NOT_READY'
spans = {r['id']:r['data'] for r in api['source_spans']}
def verify_reading_view(view,allowed_refs,page):
    refs=view['span_refs'];assert refs and len(set(refs))==len(refs) and set(refs)<=set(allowed_refs)
    assert all(spans[r]['status']=='TEXT_AGREED' and spans[r]['role']=='TEXT' and spans[r]['pdf_page']==page for r in refs)
    assert len({spans[r]['render_sha256'] for r in refs})==1
    assert view['raw_text']=='\n'.join(spans[r]['text'] for r in refs),'READING_RAW_TEXT_CHANGED'
    joins={(j['left_span_ref'],j['right_span_ref']):j for j in view['line_end_joins']}
    assert len(joins)==len(view['line_end_joins']) and set(joins)<=set(zip(refs,refs[1:]))
    text=spans[refs[0]]['text']
    for left,right in zip(refs,refs[1:]):
        a,b=spans[left],spans[right]
        if (left,right) in joins:
            x,y,w,h=a['bbox'];xx,yy,ww,hh=b['bbox']
            if joins[left,right]['operation']=='JOIN_VERIFIED_DROP_CAP_IN_READING_VIEW_ONLY':
                glyph=a['text'].strip();body=b['text'].lstrip()
                assert len(glyph)==1 and glyph.isalpha() and glyph.isupper() and body[0].islower()
                assert h>=1.4*hh and x<xx and -.5*w<=xx-(x+w)<=.15*hh
                assert max(0,min(y+h,yy+hh)-max(y,yy))>=.5*hh and y+h>yy+hh
                text=text.rstrip()+b['text'].lstrip()
            else:
                assert joins[left,right]['operation']=='REMOVE_GEOMETRIC_LINE_END_HYPHEN_IN_READING_VIEW_ONLY'
                assert re.search(r'\w-\s*$',a['text']) and re.match(r'^\s*\w',b['text'])
                assert yy>=y+.5*h and yy-(y+h)<=2*max(h,hh)
                assert max(0,min(x+w,xx+ww)-max(x,xx))>=.5*min(w,ww)
                text=re.sub(r'-\s*$','',text)+b['text'].lstrip()
        else:text+='\n'+b['text']
    assert text==view['reading_text'],'UNDECLARED_READING_TEXT_CHANGE'

def source_order(page):
    # Independent reconstruction from API/PG geometry; do not import the proposer.
    baselines=[]
    rows=[r for r in api['source_spans'] if r['data']['pdf_page']==page]
    for row in sorted(rows,key=lambda r:(r['data']['bbox'][1],r['data']['bbox'][0])):
        x,y,w,h=row['data']['bbox'];matches=[]
        for index,(top,height,members) in enumerate(baselines):
            overlap=max(0,min(y+h,top+height)-max(y,top))/min(h,height)
            distance=abs(y+h/2-top-height/2)
            if overlap>=.5 and distance<=.6*max(h,height):matches.append((distance,index))
        if matches:baselines[min(matches)[1]][2].append(row)
        else:baselines.append((y,h,[row]))
    return [row for _,_,members in baselines for row in sorted(members,key=lambda r:r['data']['bbox'][0])]

coverage_totals={'pages':0,'units':0,'chunks':0,'needs_review_units':0,'unprocessed_units':0,'partial_context_chunks':0}
def verify_unit_coverage(page,units,lookup):
    ledger=page['source_unit_coverage'];limits=ledger['limits'];entries=ledger['unit_dispositions']
    method=page['source_unit_method'];purpose=page.get('proposal_page_purpose')
    assert method in ('source-unit-claims-v3','source-unit-claims-v4') and ledger['method']==method
    if method=='source-unit-claims-v4':
        assert isinstance(purpose,dict) and purpose['pdf_page']==page['pdf_page'] and type(purpose['passed']) is bool
        assert ledger['proposal_blocked_by_page_purpose']==(not purpose['passed'])
    assert ledger['semantic_complete'] is False and ledger['human_accepted'] is False,'UNIT_LEDGER_PROMOTED_ACCEPTANCE'
    assert ledger['catalogue_sha256']==digest(units),'UNIT_CATALOGUE_HASH_MISMATCH'
    assert ledger['catalogue_units']==len(units) and set(entries)==set(lookup),'UNIT_LEDGER_SET_MISMATCH'
    assert ledger['accounting_complete'] is True
    bounds={'units_per_chunk':48,'input_characters_per_chunk':48000,'chunks_per_page':256}
    assert set(limits)==set(bounds)
    assert all(type(limits[key]) is int and 1<=limits[key]<=maximum for key,maximum in bounds.items()),'UNIT_LIMIT_INVALID'
    agreed={ref for ref,d in spans.items() if d['pdf_page']==page['pdf_page'] and d['status']=='TEXT_AGREED' and d['role']=='TEXT'}
    catalogued={ref for unit in units for ref in unit['span_refs']}
    assert ledger['agreed_text_span_refs']==sorted(agreed)
    assert ledger['catalogued_span_refs']==sorted(catalogued)
    assert ledger['uncatalogued_agreed_span_refs']==sorted(agreed-catalogued)
    # Reconstruct bounded partitions, including every deferred catalogue unit.
    partitions=[];current=[];characters=0;deferred={}
    for unit in units:
        size=len(json.dumps(unit,ensure_ascii=False,separators=(',',':')))
        if size>limits['input_characters_per_chunk']:
            deferred[unit['unit_id']]={'status':'NEEDS_REVIEW','reason':'UNIT_EXCEEDS_INPUT_BUDGET'}
            continue
        if current and (len(current)==limits['units_per_chunk'] or characters+size>limits['input_characters_per_chunk']):
            partitions.append(current);current=[];characters=0
        current.append(unit['unit_id']);characters+=size
    if current:partitions.append(current)
    for chunk in partitions[limits['chunks_per_page']:]:
        for uid in chunk:deferred[uid]={'status':'UNPROCESSED','reason':'PAGE_CALL_BUDGET_EXCEEDED'}
    partitions=partitions[:limits['chunks_per_page']]
    if method=='source-unit-claims-v4' and not purpose['passed']:
        partitions=[]
        deferred={uid:{'status':'NEEDS_REVIEW','reason':purpose['reason']} for uid in lookup}
        assert entries==deferred and not page['claims'] and not page['blocked_claims']
        assert 'SOURCE_PAGE_PURPOSE_BLOCKED_PROPOSAL' in page['uncertainties']
    assert all(entries[uid]==value for uid,value in deferred.items()),'UNIT_DEFERRED_REASON_MISMATCH'
    chunks=page['raw_model_result']['chunks'];measurements=page['metrics']['chunks']
    assert page['metrics']['method']==method
    assert ledger['processed_chunks']==len(chunks)==len(partitions)==len(measurements),'UNIT_CHUNK_COUNT_MISMATCH'
    ordered=source_order(page['pdf_page']);positions={r['id']:i for i,r in enumerate(ordered)}
    initial_pairs=[]
    for left,right in zip(ordered,ordered[1:]):
        a,b=left['data'],right['data'];glyph=a.get('text','').strip();body=b.get('text','').lstrip()
        if len(glyph)!=1 or not glyph.isalnum() or not body or not body[0].islower() or a['render_sha256']!=b['render_sha256']:continue
        x,y,w,h=a['bbox'];xx,yy,ww,hh=b['bbox']
        if h>=1.4*hh and x<xx and -.5*w<=xx-(x+w)<=.15*hh and max(0,min(y+h,yy+hh)-max(y,yy))>=.5*hh and y+h>yy+hh:
            initial_pairs.append(({left['id'],right['id']},glyph.isalpha() and glyph.isupper() and
                                  all(d['status']=='TEXT_AGREED' and d['role']=='TEXT' for d in (a,b))))
    wrapped_pairs=[]
    for index,left in enumerate(ordered):
        a=left['data']
        if not re.search(r'\w-\s*$',a.get('text','')):continue
        required={left['id']};readable=False
        if index+1<len(ordered):
            right=ordered[index+1];b=right['data'];x,y,w,h=a['bbox'];xx,yy,ww,hh=b['bbox']
            compatible=(a['pdf_page']==b['pdf_page'] and a['render_sha256']==b['render_sha256']
                        and yy>=y+.5*h and yy-(y+h)<=2*max(h,hh)
                        and max(0,min(x+w,xx+ww)-max(x,xx))>=.5*min(w,ww))
            if compatible:
                required.add(right['id'])
                readable=all(d['status']=='TEXT_AGREED' and d['role']=='TEXT' for d in (a,b)) and bool(re.match(r'^\s*\w',b.get('text','')))
        wrapped_pairs.append((required,readable))
    atomic_groups=[];atomic_blocked=set()
    if method=='source-unit-claims-v4':
        assert extended,'ATOMIC_LAYOUT_REQUIRES_EXTENDED_VERIFICATION'
        layout_row=next(r for r in api['layout_regions'] if r['data']['pdf_page']==page['pdf_page'])
        layout=layout_row['data'];atomic=page['atomic_balloon_manifest']
        assert atomic['layout_record_id']==layout_row['id'] and atomic['layout_record_sha256']==digest(layout)
        assert atomic['contract']=='UNIQUE_GEOMETRIC_BALLOON_ATOMIC_RAW_QUOTE_V1'
        assert all(r['data']['evidence_refs']==layout['evidence_refs'] for r in ordered)
        boxes=[b.get('bbox') if isinstance(b,dict) else None for b in layout['balloon_candidates']]
        def valid_balloon_box(box):
            import math
            return (isinstance(box,(list,tuple)) and len(box)==4
                    and all(type(v) in (int,float) and math.isfinite(v) for v in box)
                    and min(box)>=0 and box[2]>0 and box[3]>0
                    and box[0]+box[2]<=1.001 and box[1]+box[3]<=1.001)
        def touch(a,b):
            return min(a[0]+a[2],b[0]+b[2])>max(a[0],b[0]) and min(a[1]+a[3],b[1]+b[3])>max(a[1],b[1])
        invalid=layout.get('balloons_truncated') or any(not valid_balloon_box(b) for b in boxes)
        if invalid:
            atomic_blocked={r['id'] for r in ordered}
            assert atomic['reason']=='BALLOON_LAYOUT_INCOMPLETE'
        else:
            touching={r['id']:[i for i,b in enumerate(boxes) if touch(r['data']['bbox'],b)] for r in ordered}
            for i,b in enumerate(boxes):
                members=[r for r in ordered if i in touching[r['id']]]
                if not members:continue
                refs=[r['id'] for r in members];selected=set(refs);reason=None
                if any(j!=i and touch(b,other) for j,other in enumerate(boxes)):reason='BALLOON_GEOMETRY_AMBIGUOUS'
                elif any(touching[r['id']]!=[i] or any((r['data']['bbox'][0]<b[0]-1e-9,
                        r['data']['bbox'][1]<b[1]-1e-9,
                        r['data']['bbox'][0]+r['data']['bbox'][2]>b[0]+b[2]+1e-9,
                        r['data']['bbox'][1]+r['data']['bbox'][3]>b[1]+b[3]+1e-9)) for r in members):reason='BALLOON_REGION_BOUNDARY_AMBIGUOUS'
                elif any(r['data']['status']!='TEXT_AGREED' or r['data']['role']!='TEXT'
                         or not isinstance(r['data'].get('text'),str) or not r['data']['text'].strip() for r in members):reason='BALLOON_SOURCE_REQUIRES_REVIEW'
                elif [positions[ref] for ref in refs]!=list(range(positions[refs[0]],positions[refs[0]]+len(refs))):reason='BALLOON_READING_ORDER_AMBIGUOUS'
                elif len({r['data']['render_sha256'] for r in members})!=1 or any(required&selected and (not readable or not required<=selected) for required,readable in initial_pairs+wrapped_pairs):reason='BALLOON_WORD_OR_RENDER_BOUNDARY_INCOMPLETE'
                atomic_groups.append({'balloon_index':i,'bbox':b,'span_refs':refs,
                                      'status':'NEEDS_REVIEW' if reason else 'ATOMIC_SOURCE_UNIT','reason':reason})
                if reason:atomic_blocked.update(refs)
        assert atomic['groups']==atomic_groups and set(atomic['blocked_span_refs'])==atomic_blocked,'ATOMIC_BALLOON_MANIFEST_MISMATCH'
        if atomic_blocked:assert 'BALLOON_SOURCE_UNIT_REQUIRES_REVIEW' in page['uncertainties']
        for group in atomic_groups:
            matches=[u for u in units if set(u['span_refs'])&set(group['span_refs'])]
            if group['status']=='NEEDS_REVIEW':assert not matches,'AMBIGUOUS_BALLOON_PRODUCED_UNIT'
            else:
                assert len(matches)==1 and matches[0]['span_refs']==group['span_refs'],'ATOMIC_BALLOON_SPLIT_OR_MISSING'
                assert matches[0]['atomic_balloon']=={'layout_record_id':layout_row['id'],
                    'layout_record_sha256':digest(layout),'balloon_index':group['balloon_index'],
                    'bbox':group['bbox'],'span_refs':group['span_refs']}
        assert not any(set(u['span_refs'])&atomic_blocked for u in units)
    for unit in units:
        refs=unit['span_refs'];sequence=[positions[ref] for ref in refs]
        assert unit['pdf_page']==page['pdf_page'] and len(refs)>=1
        if unit.get('atomic_balloon'):
            assert method=='source-unit-claims-v4' and sequence==sorted(sequence)
            assert any(g['status']=='ATOMIC_SOURCE_UNIT' and refs==g['span_refs'] for g in atomic_groups)
        else:
            assert len(refs)<=3
            assert sequence==list(range(sequence[0],sequence[0]+len(sequence))),'UNIT_NONCONTIGUOUS_SOURCE'
        for pair,readable in initial_pairs:
            if pair&set(refs):assert readable and pair<=set(refs),'UNIT_PARTIAL_INITIAL_WORD'
        for pair,readable in wrapped_pairs:
            if pair&set(refs):assert readable and pair<=set(refs),'UNIT_PARTIAL_LINE_END_WORD'
    context=[]
    for position,row in enumerate(ordered):
        d=row['data'];available=(d['status']=='TEXT_AGREED' and d['role']=='TEXT' and isinstance(d.get('text'),str) and bool(d['text'].strip()))
        context.append({'position':position,'text':d['text'] if available else '[UNVERIFIED_REGION]','available':available})
    saved=page['claims']+page['blocked_claims'];roles=[]
    for index,(chunk,expected,measurement) in enumerate(zip(chunks,partitions,measurements)):
        assert chunk['chunk_index']==measurement['chunk_index']==index
        assert chunk['unit_ids']==expected,'UNIT_CHUNK_MEMBERSHIP_MISMATCH'
        raw=chunk['result'];trace=measurement['metrics'];manifest=chunk['reading_context_manifest']
        if trace.get('error'):
            assert trace['error'] in ('CONTEXT_BUDGET_EXCEEDED','MODEL_OUTPUT_TRUNCATED')
            assert raw is None and manifest is None
        else:
            assert manifest and trace['finish_reason']=='stop'
            assert trace['prompt_version']==method
            if method=='source-unit-claims-v4':assert manifest['page_purpose_sha256']==digest(purpose)
            assert manifest['full_context_sha256']==digest(context),'UNIT_FULL_CONTEXT_HASH_MISMATCH'
            assert type(manifest['prompt_characters']) is int and 0<manifest['prompt_characters']<=limits['input_characters_per_chunk']
            if manifest['scope']=='FULL_PAGE':used=context
            else:
                assert manifest['scope']=='PARTIAL_PAGE'
                selected={positions[ref] for uid in expected for ref in lookup[uid]['span_refs']}
                used=[row if row['position'] in selected else {'position':row['position'],'text':'[UNVERIFIED_OR_OMITTED_REGION]','available':False}
                      for row in context if min(selected)<=row['position']<=max(selected)]
                coverage_totals['partial_context_chunks']+=1
            assert manifest['positions']==[row['position'] for row in used]
            assert manifest['sha256']==digest(used),'UNIT_USED_CONTEXT_HASH_MISMATCH'
            retained={row['position']:row for row in used};ranges=[]
            for row in context:
                if retained.get(row['position'])==row:continue
                position=row['position']
                if ranges and ranges[-1][1]+1==position:ranges[-1][1]=position
                else:ranges.append([position,position])
            assert manifest['omitted_position_ranges']==ranges,'UNIT_OMITTED_CONTEXT_MISMATCH'
        valid_schema=(isinstance(raw,dict) and raw.get('page_role') in ('NARRATIVE','ACTIVITY','FRONT_MATTER','APPENDIX','MIXED','UNKNOWN')
                      and isinstance(raw.get('claims'),list) and len(raw['claims'])<=4
                      and isinstance(raw.get('uncertainties'),list) and all(isinstance(v,str) for v in raw['uncertainties']))
        roles.append(raw['page_role'] if valid_schema else 'UNKNOWN')
        local_saved=[claim for claim in saved if claim['source_unit_id'] in expected]
        if not valid_schema:assert not local_saved,'INVALID_UNIT_CHUNK_PRODUCED_CLAIM'
        for claim in local_saved:
            assert claim['model_candidate'] in raw['claims'],'CLAIM_NOT_IN_OWN_UNIT_CHUNK'
            assert claim['model_candidate']['source_unit_id']==claim['source_unit_id'],'CLAIM_UNIT_SELECTION_CHANGED'
        reviews=raw.get('unit_reviews',[]) if isinstance(raw,dict) else []
        if not isinstance(reviews,list):reviews=[]
        selected={claim['source_unit_id'] for claim in local_saved}
        for uid in expected:
            assert entries[uid]['chunk_index']==index
            matching=[review for review in reviews if isinstance(review,dict) and review.get('source_unit_id')==uid]
            valid_review=(valid_schema and len(matching)==1 and matching[0].get('status') in ('CANDIDATE','NO_CLAIM','NEEDS_REVIEW')
                          and isinstance(matching[0].get('reason'),str) and bool(matching[0]['reason'].strip()))
            if valid_review:valid_review=((uid in selected)==(matching[0]['status']=='CANDIDATE'))
            expected_entry=({'status':matching[0]['status'],'reason':matching[0]['reason'],'chunk_index':index} if valid_review else
                            {'status':'NEEDS_REVIEW','reason':'INVALID_OR_MISSING_UNIT_REVIEW','chunk_index':index})
            if method=='source-unit-claims-v4' and roles[-1]!=purpose['page_role']:
                expected_entry={'status':'NEEDS_REVIEW','reason':'PROPOSAL_PAGE_PURPOSE_DISAGREEMENT','chunk_index':index}
                assert not local_saved,'DISAGREEING_PAGE_PURPOSE_PRODUCED_CLAIM'
            assert entries[uid]==expected_entry,'UNIT_MODEL_DISPOSITION_MISMATCH'
    expected_role=(purpose['page_role'] if purpose['passed'] else 'UNKNOWN') if method=='source-unit-claims-v4' else (roles[0] if roles and len(set(roles))==1 else 'UNKNOWN')
    assert page['page_role']==expected_role,'UNIT_PAGE_ROLE_PROMOTION'
    incomplete=[value for value in entries.values() if value['status'] in ('NEEDS_REVIEW','UNPROCESSED')]
    assert ledger['all_units_have_model_disposition']==(bool(units) and not incomplete)
    if incomplete:assert 'SOURCE_UNIT_COVERAGE_REQUIRES_REVIEW' in page['uncertainties']
    coverage_totals['pages']+=1;coverage_totals['units']+=len(units);coverage_totals['chunks']+=len(chunks)
    coverage_totals['needs_review_units']+=sum(value['status']=='NEEDS_REVIEW' for value in entries.values())
    coverage_totals['unprocessed_units']+=sum(value['status']=='UNPROCESSED' for value in entries.values())

for page in pages.values():
    if page.get('source_unit_method') not in ('source-unit-claims-v1','source-unit-claims-v2','source-unit-claims-v3','source-unit-claims-v4'):continue
    units=page.get('source_units',[]);lookup={u['unit_id']:u for u in units}
    assert len(lookup)==len(units),'SOURCE_UNIT_ID_COLLISION'
    for unit in units:
        refs=unit['span_refs'];assert refs and len(set(refs))==len(refs)
        assert all(spans[r]['status']=='TEXT_AGREED' and spans[r]['role']=='TEXT'
                   and spans[r]['pdf_page']==page['pdf_page'] and spans[r]['render_sha256']==unit['render_sha256'] for r in refs)
        assert unit['quote']=='\n'.join(spans[r]['text'] for r in refs),'SOURCE_UNIT_TEXT_MODIFIED'
        assert unit['sha256']==digest({k:unit[k] for k in ('pdf_page','span_refs','quote','render_sha256')})
        if page['source_unit_method'] in ('source-unit-claims-v2','source-unit-claims-v3','source-unit-claims-v4'):
            assert unit['reading_view']['span_refs']==refs
            verify_reading_view(unit['reading_view'],refs,page['pdf_page'])
    for claim in page['claims']+page['blocked_claims']:
        unit=lookup[claim['source_unit_id']]
        assert claim['quote_origin']=='IMMUTABLE_OCR_UNIT_SELECTION'
        assert claim['quote']==unit['quote'] and claim['span_refs']==unit['span_refs']
        assert claim['source_unit_sha256']==unit['sha256']
        assert claim['text']==claim['model_candidate']['text'],'MODEL_CLAIM_TEXT_CHANGED'
    if page['source_unit_method'] in ('source-unit-claims-v3','source-unit-claims-v4'):verify_unit_coverage(page,units,lookup)
if extended:
    assert {r['data']['pdf_page'] for r in api['fragment_checks']} == expected_pages, 'FRAGMENT_CHECKS_INCOMPLETE'
    for row in api['source_fragments']:
        fragment=row['data']; parent=spans[fragment['parent_source_span_id']]
        assert digest(parent)==fragment['parent_record_sha256'], 'FRAGMENT_PARENT_HASH_MISMATCH'
        assert fragment['parent_generation_id']==generation and parent['status']=='NEEDS_REVIEW'
        assert fragment['pdf_page']==parent['pdf_page'] and fragment['render_sha256']==parent['render_sha256']
        x,y,w,h=fragment['bbox'];px,py,pw,ph=parent['bbox']
        assert px<=x and py<=y and x+w<=px+pw+1e-9 and y+h<=py+ph+1e-9
        proof=fragment['measurement']
        assert hashlib.sha256(base64.b64decode(proof['crop_image_base64'],validate=True)).hexdigest()==proof['crop_sha256']
        assert hashlib.sha256(proof['paddle_raw_response'].encode()).hexdigest()==proof['paddle_response_sha256']
        for reading in proof['readings']:
            assert hashlib.sha256(reading['raw_tsv'].encode()).hexdigest()==reading['tsv_sha256']
        if fragment['status']=='TEXT_AGREED':
            assert not proof['blockers'] and proof['selected_text_is_unmodified_reader_output']
            if fragment['selected_reader']=='TESSERACT_PSM7_FRAGMENT':
                assert fragment['text']==proof['readings'][0]['text']
                assert hashlib.sha256(proof['vl_raw_response'].encode()).hexdigest()==proof['vl_response_sha256']
            else:
                assert fragment['selected_reader']=='PPOCR_FRAGMENT', 'UNKNOWN_FRAGMENT_READER'
                raw=json.loads(proof['paddle_raw_response'])
                assert raw['image_sha256']==proof['crop_sha256']
                ordered=sorted(raw['lines'],key=lambda line:(min(p[1] for p in line['polygon']),min(p[0] for p in line['polygon'])))
                assert fragment['text']==' '.join(line['text'] for line in ordered), 'FRAGMENT_RAW_READER_MISMATCH'
        assert fragment['eligible_for_synthesis'] is False and fragment['visual_identity_verified'] is False
    assert len(api['cross_page_attributions'])==1, 'CROSS_PAGE_PASS_INCOMPLETE'
    links=api['cross_page_attributions'][0]['data']
    assert links['source_page_coverage_complete'] and not links['scope_errors']
    for link in links['links']:
        assert link['eligible_for_synthesis'] is False
        if link.get('dialogue_link_verified'):
            assert link['identity_evidence'] and link.get('speaker')
            assert not link.get('semantic_acceptance', False)
eligible = {}
def verify_purpose(page,gate):
    assert extended,'PAGE_PURPOSE_REQUIRES_EXTENDED_VERIFICATION'
    contexts={r['id']:r['data'] for r in api['page_context_roles']}
    context=contexts[gate['record_id']]
    assert context['version'] in ('source-page-context-v4','source-page-context-v5') and context['pdf_page']==page
    assert gate['record_sha256']==digest(context)
    layouts={r['data']['pdf_page']:r['data'] for r in api['layout_regions']}
    neighbours=[]
    for row in api['evidence']:
        n=row['data']['pdf_page']
        if abs(n-page)>1:continue
        regions=[]
        for span in api['source_spans']+api['source_fragments']:
            d=span['data']
            if d['pdf_page']!=n:continue
            agreed=d['status']=='TEXT_AGREED' and d['role']=='TEXT'
            regions.append({'ref':span['id'] if agreed else None,'can_cite':agreed,
                'text':d['text'] if agreed else '[UNVERIFIED_REGION]','bbox':d['bbox'],
                'is_verified_subregion':bool(agreed and d.get('parent_source_span_id'))})
        neighbours.append({'pdf_page':n,'regions':regions,
            'balloon_count':len(layouts[n].get('balloon_candidates',[])),
            'picture_count':sum(r.get('type')=='PICTURE' for r in layouts[n].get('regions',[]))})
    expected=digest({'target_page':page,'pages':neighbours})
    assert gate['input_sha256']==context['input_sha256']==expected,'PAGE_PURPOSE_SOURCE_HASH_MISMATCH'
    if gate['passed']:
        assert context['content_scope']==context['review']['content_scope']=='STORY_WORLD'
        assert context['eligible_for_identity_context'] and context['review']['supported']
        assert context['uncertainty_review_complete'] and context['blocking_uncertainties']==[]
        assert context['metrics']['finish_reason']==context['review_metrics']['finish_reason']=='stop'
for page in pages.values():
    if page.get('source_unit_method')=='source-unit-claims-v4':
        purpose=page['proposal_page_purpose']
        verify_purpose(page['pdf_page'],purpose)
        contexts=[row for row in api['page_context_roles'] if row['id']==purpose.get('record_id')]
        assert len(contexts)==1 and contexts[0]['data']['classification_stage']=='BEFORE_CLAIM_PROPOSAL'
        assert contexts[0]['data']['input_claim_candidates'] is False

for row in api['semantic_reviews']:
    review = row['data']; page = pages[review['pdf_page']]
    assert review.get('version') in tuple('source-semantic-review-v'+str(i) for i in range(1,9)), 'UNKNOWN_SEMANTIC_REVIEW_VERSION'
    assert review['input_page_claims_sha256'] == digest(page), 'REVIEW_INPUT_MISMATCH'
    assert review['semantic_acceptance'] is False and review['source_records_modified'] is False
    candidates = page['claims']+page['blocked_claims']
    if review['version'] in ('source-semantic-review-v4','source-semantic-review-v5','source-semantic-review-v6','source-semantic-review-v7','source-semantic-review-v8'):
        verify_purpose(review['pdf_page'],review['page_purpose_gate'])
    assert len(review['claims']) == len(candidates), 'REVIEW_COVERAGE_MISMATCH'
    for verdict in review['claims']:
        candidate = candidates[verdict['candidate_ordinal']]
        assert verdict['candidate_sha256'] == digest(candidate), 'CANDIDATE_HASH_MISMATCH'
        if verdict['eligible_for_synthesis']:
            if review['version'] in ('source-semantic-review-v4','source-semantic-review-v5','source-semantic-review-v6','source-semantic-review-v7','source-semantic-review-v8'):assert review['page_purpose_gate']['passed']
            assert verdict['source_gate']=='MATCH' and verdict['status']=='MACHINE_SUPPORTED_CANDIDATE'
            assert all(value=='PASS' for value in verdict['model_result']['checks'].values())
            if review['version'] in ('source-semantic-review-v6','source-semantic-review-v7','source-semantic-review-v8'):
                assert set(verdict['model_result']['checks'])=={'entailment','actor','speaker','polarity','narrative_mode','epistemic_strength','page_role'}
            assert all(spans[ref]['status']=='TEXT_AGREED' and spans[ref]['pdf_page']==review['pdf_page'] for ref in candidate['span_refs'])
            assert verdict['identity_gate'] in ('NOT_REQUIRED','SOURCE_VERIFIED')
            assert verdict['claim_id'] not in eligible, 'CLAIM_ID_COLLISION'
            carried=candidate['span_refs']
            if review['version'] in ('source-semantic-review-v2','source-semantic-review-v3','source-semantic-review-v4','source-semantic-review-v5','source-semantic-review-v6','source-semantic-review-v7','source-semantic-review-v8'):
                carried=verdict['verified_support_span_refs']
                assert set(candidate['span_refs'])<=set(carried)
                assert set(verdict['model_result']['support_span_refs'])<=set(carried)
                assert all(spans[r]['status']=='TEXT_AGREED' and spans[r]['role']=='TEXT'
                           and spans[r]['pdf_page']==review['pdf_page'] for r in carried)
                regions=[{'span_id':ref,**{k:spans[ref][k] for k in ('text','bbox','render_sha256')}} for ref in carried]
                assert verdict['verified_support_regions']==regions
                cited=verdict['citation_review'];assert cited['passed'] is True
                assert cited.get('version') in tuple('source-semantic-review-v'+str(i)+'-cited-support' for i in range(2,9)), 'UNKNOWN_CITATION_REVIEW_VERSION'
                if review['version'] in ('source-semantic-review-v6','source-semantic-review-v7','source-semantic-review-v8'):
                    verify_surface_references(candidate,cited['source_reading_segments'],cited['surface_reference_gate'])
                    if review['version'] in ('source-semantic-review-v7','source-semantic-review-v8'):
                        verify_qualification(candidate,cited['source_reading_segments'],cited.get('qualification_gate'))
                    assert set(cited['model_result']['checks'])=={'entailment','actor','speaker','polarity','narrative_mode','epistemic_strength'}
                assert cited['source_sha256']==digest(regions)
                assert all(v=='PASS' for v in cited['model_result']['checks'].values())
                if review['version'] in ('source-semantic-review-v3','source-semantic-review-v4','source-semantic-review-v5','source-semantic-review-v6','source-semantic-review-v7','source-semantic-review-v8'):
                    views=cited['source_reading_segments'];view_refs=[ref for view in views for ref in view['span_refs']]
                    assert len(view_refs)==len(set(view_refs)) and set(view_refs)==set(carried)
                    for view in views:verify_reading_view(view,carried,review['pdf_page'])
                    claim={k:candidate.get(k) for k in ('kind','text','quote','span_refs','actor','speaker','narrative_mode','polarity')}
                    assert cited['input_sha256']==digest({'claim':claim,'cited_source_regions':regions,'source_reading_segments':views})
                    if review['version'] in ('source-semantic-review-v7','source-semantic-review-v8'):
                        assert cited.get('version')==review['version']+'-cited-support'
                        verify_obligations(claim,regions,cited['obligation_review'])
                        if review['version']=='source-semantic-review-v8':
                            assert cited['role_binding_review']['version']=='source-role-bindings-v8' and cited['role_binding_review']['passed'] is True
                            assert cited['role_binding_review']['reading_views']==cited['source_reading_segments']
                            verify_role_bindings(claim,regions,cited['role_binding_review'])
            eligible[verdict['claim_id']] = {**candidate,'span_refs':carried}
for row in api['figure_identity']:
    identity = row['data']
    if identity['method']=='figure-identity-v2':verify_purpose(identity['pdf_page'],identity['page_purpose_gate'])
    assert identity['semantic_acceptance'] is False
    for link in identity['links']:
        assert link['eligible_for_synthesis'] is False
        if link['visual_identity_verified']:
            if identity['method']=='figure-identity-v2':assert identity['page_purpose_gate']['passed']
            assert {e['kind'] for e in link['identity_evidence']} == {'EXPLICIT_TEXT_ATTRIBUTION','UNIQUE_BALLOON_TAIL'}
            for evidence in link['identity_evidence']:
                for ref in evidence.get('source_span_refs',[]):
                    assert spans[ref]['status']=='TEXT_AGREED' and spans[ref]['pdf_page']==identity['pdf_page']
for row in api['figure_comparisons']:
    pair = row['data']
    assert pair['visual_identity_verified'] is False and pair['eligible_for_synthesis'] is False
    assert len(pair['crop_image_base64']) == len(pair['crop_sha256']) == 2
    for image, wanted in zip(pair['crop_image_base64'], pair['crop_sha256']):
        assert hashlib.sha256(base64.b64decode(image,validate=True)).hexdigest()==wanted, 'IDENTITY_CROP_MISMATCH'
for row in api['semantic_synthesis']:
    result = row['data']
    assert result.get('version') in tuple('source-semantic-review-v'+str(i) for i in range(1,9)), 'UNKNOWN_SYNTHESIS_VERSION'
    assert result['semantic_acceptance'] is False and result['complete_book'] is False
    assert result['input_claim_count']==len(eligible)
    for statement in result['statements']:
        assert statement['claim_refs'] and set(statement['claim_refs']) <= set(eligible)
        assert statement['verification']['supported'] is True
        expected_spans = {ref for cid in statement['claim_refs'] for ref in eligible[cid]['span_refs']}
        assert set(statement['source_span_refs'])==expected_spans
        if result['version'] in ('source-semantic-review-v6','source-semantic-review-v7','source-semantic-review-v8'):
            views=statement['source_reading_segments']
            assert {ref for view in views for ref in view['span_refs']}==expected_spans
            for view in views:verify_reading_view(view,expected_spans,spans[view['span_refs'][0]]['pdf_page'])
            verify_surface_references(statement,views,statement['surface_reference_gate'])
            if result['version'] in ('source-semantic-review-v7','source-semantic-review-v8'):
                verify_qualification(statement,views,statement.get('qualification_gate'))
                obligation_regions=[{'span_id':ref,**{k:spans[ref][k] for k in ('text','bbox','render_sha256')}} for ref in sorted(expected_spans)]
                verify_obligations({'kind':statement['kind'],'text':statement['text']},obligation_regions,statement['obligation_review'])
                if result['version']=='source-semantic-review-v8':
                    assert statement['role_binding_review']['version']=='source-role-bindings-v8' and statement['role_binding_review']['passed'] is True
                    assert statement['role_binding_review']['reading_views']==statement['source_reading_segments']
                    verify_role_bindings({'kind':statement['kind'],'text':statement['text']},obligation_regions,statement['role_binding_review'])
model_calls={};incomplete_calls=[]
def verify_attempts(value):
    if isinstance(value,list):
        for item in value:verify_attempts(item)
    elif isinstance(value,dict):
        if value.get('error')=='MODEL_OUTPUT_TRUNCATED':
            attempts=value['generation_attempts']
            assert 1<=len(attempts)<=2,'UNBOUNDED_INCOMPLETE_MODEL_RETRY'
            assert len({a['messages_sha256'] for a in attempts})==1,'INCOMPLETE_MODEL_RETRY_INPUT_CHANGED'
            assert attempts[-1]['finish_reason']!='stop','COMPLETED_OUTPUT_RECORDED_AS_TRUNCATED'
            for attempt in attempts:
                assert type(attempt['max_output_tokens']) is int and attempt['max_output_tokens']>0
                assert isinstance(attempt['incomplete_output'],str)
                assert all(re.fullmatch('[0-9a-f]{64}',attempt[key]) for key in ('messages_sha256','request_sha256','response_sha256'))
                assert attempt['usage']['completion_tokens']<=attempt['max_output_tokens']
            if len(attempts)==2:
                assert attempts[0]['finish_reason']=='length','COMPLETED_INCOMPLETE_VERDICT_RETRIED'
                assert attempts[0]['max_output_tokens']<attempts[1]['max_output_tokens']<=2*attempts[0]['max_output_tokens']
            incomplete_calls.append(attempts)
        if value.get('generation_retry_policy')=='LENGTH_ONLY_IDENTICAL_INPUT_ONCE_WITHIN_CONTEXT':
            attempts=value['generation_attempts']
            assert 1<=len(attempts)<=2,'UNBOUNDED_MODEL_RETRY'
            assert len({a['messages_sha256'] for a in attempts})==1,'MODEL_RETRY_INPUT_CHANGED'
            assert attempts[0]['max_output_tokens']==value['requested_max_output_tokens']
            assert attempts[-1]['finish_reason']==value['finish_reason']=='stop'
            assert attempts[-1]['request_sha256']==value['request_sha256']
            for attempt in attempts:
                assert attempt['max_output_tokens']+value['input_token_count']+512<=value['context_limit']
                assert re.fullmatch('[0-9a-f]{64}',attempt['response_sha256'])
                assert attempt['usage']['completion_tokens']<=attempt['max_output_tokens']
            if len(attempts)==2:
                assert attempts[0]['finish_reason']=='length','COMPLETED_VERDICT_RETRIED'
                assert attempts[0]['max_output_tokens']<attempts[1]['max_output_tokens']<=2*attempts[0]['max_output_tokens']
                assert isinstance(attempts[0]['incomplete_output'],str)
            model_calls[(value['started_at'],value['request_sha256'])]=len(attempts)
        for child in value.values():verify_attempts(child)
for items in api.values():
    for row in items:verify_attempts(row['data'])
report = {'generation_id':generation,'api':base,'api_pg_match':True,
          'source_unit_coverage_integrity':coverage_totals,
          'counts':{kind:len(api[kind]) for kind in kinds},'eligible_claims':len(eligible),
          'bounded_model_calls_verified':len(model_calls),
          'bounded_incomplete_model_calls_verified':len(incomplete_calls),
          'length_retry_calls_verified':sum(n==2 for n in model_calls.values()),
          'derived_integrity_passed':True,'semantic_acceptance':False,'application_writes':0}
target = root/'evidence'/('source-analysis-'+generation+'.json')
target.write_text(json.dumps(report,indent=2));target.chmod(0o600)
print(json.dumps(report))
