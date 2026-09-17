#!/usr/bin/env python3
"""Read-only residual OCR audit of real API records and independent PostgreSQL."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import unicodedata
import urllib.request
import uuid

p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--generation',type=uuid.UUID,required=True)
a=p.parse_args();root=Path(__file__).resolve().parents[1];os.chdir(root)
token=(root/'secrets/api_token').read_text().strip();gen=str(a.generation)
def sql(q):
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',q],text=True))
def db():
    return sql("SELECT coalesce(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE kind='source_spans' AND generation_id='"+gen+"'")
def words(s):
    return re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',s or '').replace('İ','i').replace('I','ı').lower())
def corrupt(s):
    return any(unicodedata.category(c) in ('Co','Cs') or c=='\ufffd' for c in s or '')
def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=True).encode()).hexdigest()
before=db();rows=[]
while True:
    url=a.base.rstrip('/')+f'/v1/generations/{gen}/source_spans?offset={len(rows)}&limit=100'
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Authorization':'Bearer '+token}),timeout=60) as response:batch=json.load(response)
    rows.extend(batch['items'])
    if not batch['has_more']:break
    assert batch['items']
assert rows==before and rows
counts=Counter();issues=Counter();classes=Counter();details=[];buckets=Counter();pages=Counter();roles=Counter();veto_patterns=Counter()
for row in rows:
    d=row['data'];counts['all_'+d['status']]+=1
    if d['status']!='NEEDS_REVIEW':continue
    counts['review']+=1;pages[d['pdf_page']]+=1;issues.update(d['issues']);roles[d['role']]+=1
    primary=words(d['raw_text']);region=words(d.get('region_text'));tess=words(d['secondary_text']);pdf=words(d['pdf_text'])
    high=isinstance(d.get('region_score'),(int,float)) and math.isfinite(d['region_score']) and d['region_score']>=.9
    tmatch=bool(tess) and tess==region and not corrupt(d['secondary_text'])
    pmatch=d['pdf_usable'] and bool(pdf) and pdf==region and not corrupt(d['pdf_text'])
    tveto=(bool(tess) or corrupt(d['secondary_text'])) and not tmatch
    pveto=d['pdf_usable'] and not pmatch
    conf=[r['confidence'] for r in d.get('secondary_word_regions',[]) if isinstance(r.get('confidence'),(int,float)) and r['confidence']>=0]
    minconf=min(conf) if conf else None;meanconf=statistics.mean(conf) if conf else None
    reread=d.get('reread_measurement');state='NOT_AVAILABLE';rconf=[]
    if reread:
        rr=reread['readings'];assert len(rr)==2
        first,second=[words(r['text']) for r in rr]
        state=('AGREES_REGION' if first==region else 'CONFLICTS_REGION') if first and first==second else 'UNSTABLE'
        rconf=[x for r in rr for x in r.get('word_confidences',[]) if x>=0]
    supported=high and bool(region) and not corrupt(d.get('region_text')) and (tmatch or pmatch) and not tveto and not pveto and state!='CONFLICTS_REGION'
    category=('REGION_SUPPORTED_UNDER_STRICT_POLICY' if supported else 'REGION_EMPTY' if not region else
        'REGION_LOW_SCORE' if not high else 'REGION_UNICODE_CORRUPT' if corrupt(d.get('region_text')) else
        'REGION_HIGH_INDEPENDENT_READER_VETO' if tveto or pveto else
        'REGION_HIGH_STABLE_REREAD_VETO' if state=='CONFLICTS_REGION' else 'REGION_HIGH_NO_INDEPENDENT_SUPPORT')
    classes[category]+=1;counts['reread_'+state]+=1
    for name,value in {'region_high_score':high,'region_matches_primary':bool(region) and region==primary,
        'secondary_missing':not tess,'secondary_unicode_corrupt':corrupt(d['secondary_text']),
        'secondary_veto_against_region':tveto,'pdf_usable':d['pdf_usable'],
        'pdf_unicode_corrupt':corrupt(d['pdf_text']),'pdf_unusable_nonempty':not d['pdf_usable'] and bool(d['pdf_text']),
        'pdf_veto_against_region':pveto,'region_matches_tesseract':tmatch,'region_matches_usable_pdf':pmatch,
        'reread_available':bool(reread),'high_region_tess_veto':high and tveto,
        'high_region_tess_veto_min_conf_lt50':high and tveto and minconf is not None and minconf<50,
        'high_region_tess_veto_mean_conf_lt50':high and tveto and meanconf is not None and meanconf<50,
        'high_region_tess_veto_min_conf_lt50_pdf_support':high and tveto and minconf is not None and minconf<50 and pmatch,
        'high_region_tess_veto_mean_conf_lt50_pdf_support':high and tveto and meanconf is not None and meanconf<50 and pmatch,
        'high_region_tess_veto_min_conf_lt50_pdf_support_stable_region_reread':high and tveto and minconf is not None and minconf<50 and pmatch and state=='AGREES_REGION',
        'full_page_low_score_region_high':d['score']<.9 and high}.items():
        if value:counts[name]+=1
    if high and tveto:
        buckets['missing' if meanconf is None else '<25' if meanconf<25 else '25-49' if meanconf<50 else '50-79' if meanconf<80 else '80+']+=1
        compact=lambda ws: ''.join(ws)
        fold=lambda ws: compact(ws).translate(str.maketrans('çğıöşü','cgiosu'))
        pattern=('WORD_BOUNDARY_ONLY' if compact(region)==compact(tess) else
            'TURKISH_DIACRITICS_ONLY' if fold(region)==fold(tess) else
            'NUMERIC_REGION_NONMATCH' if compact(region).isdigit() else
            'FEWER_SECONDARY_TOKENS' if len(tess)<len(region) else
            'MORE_SECONDARY_TOKENS' if len(tess)>len(region) else 'SAME_TOKEN_COUNT_OTHER')
        veto_patterns[pattern]+=1
        if pattern=='TURKISH_DIACRITICS_ONLY':
            counts['diacritics_only_pdf_support']+=int(pmatch)
            counts['diacritics_only_reread_'+state]+=1
        if minconf is not None and minconf<50 and pmatch:
            counts['low_conf_pdf_support_role_'+d['role']]+=1
    details.append({'id':row['id'],'record_key':row['record_key'],'pdf_page':d['pdf_page'],'bbox':d['bbox'],
        'class':category,'role':d['role'],'issues':d['issues'],'raw_text':d['raw_text'],'region_text':d.get('region_text'),
        'secondary_text':d['secondary_text'],'pdf_text':d['pdf_text'],'pdf_usable':d['pdf_usable'],
        'full_page_score':d['score'],'region_score':d.get('region_score'),'tesseract_confidences':conf,
        'tesseract_min_confidence':minconf,'tesseract_mean_confidence':meanconf,
        'tesseract_veto':tveto,'pdf_veto':pveto,'pdf_supports_region':pmatch,'reread_state':state,
        'reread_measurement':reread,'secondary_word_regions':d.get('secondary_word_regions',[])})
after=db();assert before==after
report={'generation_id':gen,'api':a.base,'at':datetime.now(timezone.utc).isoformat(),
    'api_pg_equal':True,'source_records_unchanged':True,'source_records_sha256':fingerprint(before),
    'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'writes_to_source_or_review':0,'model_calls':0,'semantic_acceptance':False,'counts':dict(counts),
    'mutually_exclusive_classes':dict(classes),'issue_counts_nonexclusive':dict(issues),
    'high_region_tesseract_veto_mean_confidence_buckets':dict(buckets),'review_by_page':dict(pages),'regions':details}
report['review_roles']=dict(roles);report['high_region_tesseract_veto_patterns']=dict(veto_patterns)
out=root/'evidence'/('ocr-residual-audit-'+gen+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='regions'}|{'evidence':str(out)},ensure_ascii=False,indent=2))
