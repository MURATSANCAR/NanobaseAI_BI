#!/usr/bin/env python3
"""Read-only replay of real persisted measurements through the new code image.

Run inside the proposed API image against the connected Editor PostgreSQL.
No synthetic inputs and no saved data corrections.
"""
from collections import Counter
import json
import sys

from editor.book_store import get_records, sha
from editor.source_pipeline import reused_reading, quote_check

gen=sys.argv[1]
before=get_records(gen,'source_spans')
fingerprint=sha(json.dumps(before,sort_keys=True,default=str).encode())
readings={r['record_key']:r for r in get_records(gen,'page_readings')}
pages=[]
for evidence in get_records(gen,'evidence'):
    if evidence['record_key'] not in readings:continue
    value=reused_reading(gen,evidence)
    assert value is not None
    original=[r for r in before if r['data']['pdf_page']==evidence['data']['pdf_page']]
    assert len(value['lines'])==len(original)
    for line,row in zip(value['lines'],original):
        assert line['text']==row['data']['raw_text']
        assert line['region_text']==row['data']['region_text']
        assert line['bbox']==row['data']['bbox']
        assert line['score']==row['data']['score']
        assert line['reused_source_span_id']==str(row['id'])
    pages.append(evidence['data']['pdf_page'])
reasons=Counter();details=[]
for record in get_records(gen,'page_claims'):
    page=record['data']['pdf_page']
    spans=[r for r in before if r['data']['pdf_page']==page]
    allowed={str(r['id']):r for r in spans}
    for claim in record['data']['claims']+record['data']['blocked_claims']:
        refs=claim.get('span_refs',[])
        chosen=[allowed[r] for r in refs if r in allowed]
        reason=quote_check(claim.get('quote',''),chosen,spans) if refs and len(chosen)==len(refs) else 'INVALID_SPAN_REFERENCE'
        reasons[reason]+=1
        details.append({'page':page,'original_gate':claim['source_gate'],'new_quote_gate':reason})
after=get_records(gen,'source_spans')
# The running worker may append a later page; existing records must stay exact.
old_ids={str(r['id']) for r in before}
after=[r for r in after if str(r['id']) in old_ids]
assert fingerprint==sha(json.dumps(after,sort_keys=True,default=str).encode())
print(json.dumps({'generation_id':gen,'replayed_pages':pages,'raw_measurements_preserved':True,
    'source_fingerprint':fingerprint,'quote_results':dict(reasons),'details':details,
    'semantic_acceptance':False,'writes':0},ensure_ascii=False,indent=2))
