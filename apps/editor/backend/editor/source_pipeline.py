"""Page-local sources before interpretation. Captions are never source text.

Source records are immutable; optical agreement is not editorial acceptance.
Unresolved regions remain visible and block dependent claims, not other pages.
"""
import base64
import json
import re
import unicodedata

import httpx
from psycopg.types.json import Jsonb
from editor.book_store import ROOT, sha, identifier, get_records, source_for, fence
from editor.config import connection, code_manifest
from editor.source_alignment import reader_text, reading_order, valid_box

VERSION = 'source-spans-v4'


def norm(value):
    value = re.sub(r'-\s*\n\s*', '', value)
    value = unicodedata.normalize('NFKC', value).replace('İ','i').replace('I','ı').lower()
    return ''.join(c for c in value if c.isalnum())


def negation(value):
    # A rejection aid, never sufficient to accept a sentence. Exact quote matching
    # below also catches forms this deliberately incomplete Turkish check misses.
    return re.findall(r'\b\w*(?:mıyor|miyor|muyor|müyor|madı|medi)\w*\b|\b(?:değil|yok|hayır)\b', value.lower())


def quote_tokens(value):
    value = re.sub(r'-\s*\n\s*', '', value)
    value = unicodedata.normalize('NFKC',value).replace('İ','i').replace('I','ı').lower()
    return re.findall(r'[^\W_]+',value)


def optical_verdict(line, secondary, pdf_text, pdf_usable, reread=None):
    # Preserve word boundaries, just as the downstream quote gate does. Joining
    # all letters hid split/merged words and could certify a different reading.
    primary_tokens = quote_tokens(line['text'])
    secondary_tokens = quote_tokens(secondary)
    primary = bool(primary_tokens) and primary_tokens == quote_tokens(line.get('region_text') or '')
    second = bool(secondary_tokens) and secondary_tokens == primary_tokens
    native = pdf_usable and bool(quote_tokens(pdf_text)) and quote_tokens(pdf_text) == primary_tokens
    conflict = (bool(secondary_tokens) and not second) or (pdf_usable and not native)
    score = min(line['score'], line.get('region_score') or 0)
    issues = []
    if not primary: issues.append('REGIONAL_READING_DISAGREES')
    if not second: issues.append('SECOND_READER_DISAGREES_OR_MISSING')
    if not native: issues.append('PDF_TEXT_DISAGREES_OR_UNUSABLE')
    if score < .9: issues.append('LOW_RECOGNITION_SCORE')
    # Stored "stable"/"matching" flags are diagnostic, not acceptance authority.
    # Recompute from the two immutable raw readings; a new contradiction blocks.
    reread_state = 'NOT_AVAILABLE'
    if reread is not None:
        readings = reread['readings']
        if len(readings) != 2 or [r['psm'] for r in readings] != [7,13]:
            raise RuntimeError('REREAD_SCHEMA_MISMATCH')
        tokens = [quote_tokens(r['text']) for r in readings]
        stable = bool(tokens[0]) and tokens[0] == tokens[1]
        reread_state = 'AGREES' if stable and tokens[0] == quote_tokens(line['text']) else 'DISAGREES' if stable else 'UNSTABLE'
        if reread_state == 'DISAGREES':
            conflict = True
            issues.append('REREAD_CONFLICT')
        elif reread_state == 'UNSTABLE':
            issues.append('REREAD_UNSTABLE')
    return {'status': 'TEXT_AGREED' if primary and (second or native) and not conflict and score >= .9 else 'NEEDS_REVIEW',
            'issues': issues, 'pdf_matches': native, 'reread_state': reread_state}


def reread_measurements(root, parent, evidence):
    if not parent:
        return {}, None
    path = root/'region-reread-v1'/str(parent)/f"page-{evidence['data']['pdf_page']:04}.json"
    if not path.exists():
        # A parent may itself reuse measurements. Follow the stored original
        # artifact identity, never silently lose reader conflicts on generation 3+.
        inherited={};provenance=None;reports={}
        for row in get_records(parent,'source_spans'):
            d=row['data']
            if d['pdf_page']!=evidence['data']['pdf_page'] or not d.get('reread_measurement'):
                continue
            p=d['reread_provenance'];origin=p['generation_id']
            if origin not in reports:
                original=root/'region-reread-v1'/origin/f"page-{d['pdf_page']:04}.json"
                raw=original.read_bytes();report=json.loads(raw)
                e=evidence['data']
                if (sha(raw)!=p['artifact_sha256'] or report['generation_id']!=origin
                        or report['source_sha256']!=e['source_sha256'] or report['pdf_page']!=e['pdf_page']
                        or report['render_sha256']!=e['ocr_render_sha256']):
                    raise RuntimeError('INHERITED_REREAD_SOURCE_MISMATCH')
                reports[origin]={r['source_span_id']:r for r in report['regions']}
                if len(reports[origin])!=len(report['regions']):raise RuntimeError('DUPLICATE_REREAD_SOURCE')
            measurement=d['reread_measurement']
            if reports[origin].get(measurement['source_span_id'])!=measurement or measurement['bbox']!=d['bbox']:
                raise RuntimeError('INHERITED_REREAD_MEASUREMENT_MISMATCH')
            if provenance is not None and provenance!=p:raise RuntimeError('MIXED_REREAD_PROVENANCE')
            provenance=p;inherited[str(row['id'])]=measurement
        return inherited, provenance
    raw = path.read_bytes(); report = json.loads(raw); d = evidence['data']
    if (report['generation_id'] != str(parent) or report['source_sha256'] != d['source_sha256']
            or report['render_sha256'] != d['ocr_render_sha256'] or report['pdf_page'] != d['pdf_page']):
        raise RuntimeError('REREAD_SOURCE_SCOPE_MISMATCH')
    rows = {r['source_span_id']:r for r in report['regions']}
    if len(rows) != len(report['regions']):
        raise RuntimeError('DUPLICATE_REREAD_SOURCE')
    return rows, {'artifact_sha256':sha(raw),'generation_id':str(parent),
                  'method':report['method'],'code_sha256':report['code_sha256'],
                  'engine':report['engine'],'models':report['models']}


def quote_check(quote, rows, all_rows=None):
    if not isinstance(quote,str) or not quote_tokens(quote) or not rows:
        return 'QUOTE_MISMATCH'
    ids=[str(r['id']) for r in rows]
    if len(set(ids))!=len(ids): return 'DUPLICATE_SPAN_REFERENCE'
    if all_rows is not None:
        positions={str(r['id']):i for i,r in enumerate(reading_order(all_rows))}
        order=[positions.get(r,-1) for r in ids]
        if -1 in order or order!=list(range(order[0],order[0]+len(order))):
            return 'NONCONTIGUOUS_SOURCE_SPANS'
    joined='\n'.join(r['data']['text'] for r in rows)
    needle=quote_tokens(quote); haystack=quote_tokens(joined)
    if any(haystack[i:i+len(needle)]==needle for i in range(len(haystack)-len(needle)+1)):
        return 'MATCH' if rows and all(r['data']['status']=='TEXT_AGREED' for r in rows) else 'SOURCE_NEEDS_REVIEW'
    if rows and bool(negation(quote)) != bool(negation(joined)):
        return 'POSSIBLE_NEGATION_FLIP'
    return 'QUOTE_MISMATCH'


def save(job, kind, key, data):
    from editor.analysis import commit
    return commit(job, kind, key, data)


def reused_reading(parent,evidence):
    """Reuse immutable machine measurements, never claims or review decisions."""
    if not parent: return None
    key=evidence['record_key']; page=evidence['data']['pdf_page']
    readings={r['record_key']:r for r in get_records(parent,'page_readings')}
    layouts={r['record_key']:r for r in get_records(parent,'layout_regions')}
    prior={r['record_key']:r for r in get_records(parent,'evidence')}
    if key not in readings or key not in layouts or key not in prior: return None
    previous=prior[key]['data']; current=evidence['data']
    if any(previous[k]!=current[k] for k in ('source_sha256','render_sha256','ocr_render_sha256','ocr_artifact_sha256')):
        raise RuntimeError('REUSED_SOURCE_HASH_MISMATCH')
    spans=[r for r in get_records(parent,'source_spans') if r['data']['pdf_page']==page]
    reading=readings[key]['data']
    if len(spans)!=reading['span_count']: raise RuntimeError('REUSED_SOURCE_INCOMPLETE')
    lines=[]
    for row in spans:
        d=row['data'];x,y,w,h=d['bbox']
        if d['render_sha256']!=current['ocr_render_sha256']:raise RuntimeError('REUSED_RENDER_MISMATCH')
        lines.append({'text':d['raw_text'],'score':d['score'],'region_text':d['region_text'],
            'region_score':d['region_score'],'polygon':[[x,y],[x+w,y],[x+w,y+h],[x,y+h]],
            'bbox':d['bbox'],
            'reused_source_span_id':str(row['id'])})
    return {'width':1,'height':1,'image_sha256':current['ocr_render_sha256'],'lines':lines,
        'engine':spans[0]['data']['engine'] if spans else 'paddleocr',
        'models':reading['model_manifest'],'seconds':reading['seconds'],
        'regional_truncated':reading['regional_truncated'],
        'balloon_candidates':layouts[key]['data'].get('balloon_candidates',[]),
        'balloons_truncated':layouts[key]['data'].get('balloons_truncated',False),
        'reused_from_generation':str(parent),'reused_reading_id':str(readings[key]['id'])}


def optical(job, evidence, document, root, parent=None):
    gen=job['generation_id']; page=evidence['data']['pdf_page']; key=evidence['record_key']
    d=evidence['data']; image_path=root/'ocr-regions-v2'/f'page-{page:04}.png'
    raw=image_path.read_bytes()
    if sha(raw)!=d['ocr_render_sha256']: raise RuntimeError('OCR_RENDER_HASH_MISMATCH')
    result=reused_reading(parent,evidence)
    if result is None:
        with httpx.Client(timeout=600,trust_env=False) as client:
            response=client.post('http://ocr:8080/ocr',json={
                'image_base64':base64.b64encode(raw).decode(),'regional_pass':True})
            response.raise_for_status(); result=response.json()
    if result['image_sha256']!=sha(raw): raise RuntimeError('OCR_RESPONSE_SOURCE_MISMATCH')
    width,height=result['width'],result['height']; spans=[]
    pdf_path=root/'pdf-text-regions-v1'/f'page-{page:04}.json'
    if not pdf_path.exists():raise RuntimeError('NATIVE_PDF_REGIONS_REQUIRED')
    pdf=json.loads(pdf_path.read_text())
    if pdf['source_sha256']!=d['source_sha256'] or pdf['pdf_page']!=page:raise RuntimeError('PDF_SOURCE_SCOPE_MISMATCH')
    rereads, reread_provenance = reread_measurements(root,parent,evidence)
    for i,line in enumerate(result['lines']):
        xs=[p[0] for p in line['polygon']]; ys=[p[1] for p in line['polygon']]
        bbox=line.get('bbox') or [min(xs)/width,min(ys)/height,(max(xs)-min(xs))/width,(max(ys)-min(ys))/height]
        # Match readers by position; never promote a similar word elsewhere on the page.
        secondary,neighbors,_=reader_text(bbox,d['blocks'])
        pdf_text,pdf_neighbors,pdf_usable=reader_text(bbox,pdf['lines'])
        reread = rereads.get(line.get('reused_source_span_id'))
        if reread is not None and reread['bbox'] != bbox:
            raise RuntimeError('REREAD_REGION_MISMATCH')
        verdict = optical_verdict(line,secondary,pdf_text,pdf_usable,reread)
        status,issues,pdf_agrees = verdict['status'],verdict['issues'],verdict['pdf_matches']
        sid=identifier(gen,'source_spans',key+f'-{i:04}')
        value={'pdf_page':page,'evidence_refs':[str(evidence['id'])], 'bbox':bbox,
            'coordinate_system':'normalized_top_left','text':line['text'],'raw_text':line['text'],
            'region_text':line.get('region_text'), 'secondary_text':secondary,
            'pdf_text':pdf_text,'pdf_usable':pdf_usable,'pdf_matches':pdf_agrees,
            'pdf_word_regions':pdf_neighbors,'secondary_word_regions':neighbors,
            'alignment_method':'word_geometry_v2','pdf_artifact_sha256':sha(pdf_path.read_bytes()),
            'score':line['score'],'region_score':line.get('region_score'),
            'status':status,'issues':issues,'engine':result['engine'],'model_manifest':result['models'],
            'render_sha256':result['image_sha256'],'pipeline_version':VERSION,
            'reread_measurement':reread,'reread_provenance':reread_provenance if reread else None,
            'reread_state':verdict['reread_state'],
            'reused_source_span_id':line.get('reused_source_span_id'),
            'reused_from_generation':result.get('reused_from_generation'),
            'role':'PAGE_LABEL_CANDIDATE' if bbox[1]>.85 and line['text'].strip().isdigit() else 'TEXT',
            'review_status':'PENDING'}
        save(job,'source_spans',key+f'-{i:04}',value)
        spans.append({'id':sid,'data':value})
    regions=[]; size=document['pages'][str(page)]['size']
    for group in ('texts','pictures'):
        for item in document.get(group,[]):
            for p in item.get('prov',[]):
                if p['page_no']!=page: continue
                b=p['bbox']; top=(size['height']-b['t']) if b['coord_origin']=='BOTTOMLEFT' else b['t']
                x=max(0,b['l']/size['width']); y=max(0,top/size['height'])
                bbox=[x,y,min(1-x,abs(b['r']-b['l'])/size['width']),min(1-y,abs(b['t']-b['b'])/size['height'])]
                if min(bbox[2:])<=0: continue
                regions.append({'type':'PICTURE' if group=='pictures' else 'TEXT',
                    'label':item.get('label'),'bbox':bbox,'source_ref':item['self_ref']})
    save(job,'layout_regions',key,{'pdf_page':page,'evidence_refs':[str(evidence['id'])],
        'regions':regions,'method':'existing_hash_verified_docling_layout',
        'native_pdf_regions':pdf['lines'],'native_pdf_artifact_sha256':sha(pdf_path.read_bytes()),
        'balloon_candidates':result.get('balloon_candidates',[]),
        'balloons_truncated':result.get('balloons_truncated',False),
        'source_artifact_sha256':sha((root/'docling.json').read_bytes()),
        'verification_status':'CANDIDATE','does_not_supply_text':True})
    save(job,'page_readings',key,{'pdf_page':page,'evidence_refs':[str(evidence['id'])],
        'span_ids':[r['id'] for r in spans], 'span_count':len(spans),
        'agreed_spans':sum(r['data']['status']=='TEXT_AGREED' for r in spans),
        'review_spans':sum(r['data']['status']!='TEXT_AGREED' for r in spans),
        'regional_truncated':result['regional_truncated'],'seconds':result['seconds'],
        'measurement_reused':bool(result.get('reused_from_generation')),
        'reused_from_generation':result.get('reused_from_generation'),
        'reused_reading_id':result.get('reused_reading_id'),
        'render_sha256':result['image_sha256'],'model_manifest':result['models'],
        'status':('NO_TEXT_DETECTED' if not spans else 'NEEDS_REVIEW' if result['regional_truncated'] or any(r['data']['status']!='TEXT_AGREED' for r in spans) else 'TEXT_AGREED'),
        'review_status':'PENDING','pipeline_version':VERSION})


def observe(job,evidence,layout,spans,root,parent=None):
    from editor.analysis import model
    from editor.source_review import speaker_candidates
    gen=job['generation_id']; page=evidence['data']['pdf_page']; key=evidence['record_key']
    illustrations=[r for r in layout['data']['regions'] if r['type']=='PICTURE' and r['bbox'][2]*r['bbox'][3]>.06]
    observations=[]
    if parent:
        prior=next((r for r in get_records(parent,'visual_observations') if r['record_key']==key),None)
        old_evidence=next((r for r in get_records(parent,'evidence') if r['record_key']==key),None)
        if prior and old_evidence and old_evidence['data']['render_sha256']==evidence['data']['render_sha256']:
            value={**prior['data'],'evidence_refs':[str(evidence['id'])],
                'source_span_ids':[str(s['id']) for s in spans],
                'reused_visual_observation_id':str(prior['id']),
                'reused_from_generation':str(parent),'pipeline_version':VERSION}
            value['speaker_links']=speaker_candidates(layout['data'],value)
            # Keep original metrics and provenance; do not claim a new model call.
            save(job,'visual_observations',key,value)
            return
    # Every selected region has its own crop; any omitted region is explicit.
    for i,region in enumerate(illustrations[:3]):
        raw=(root/f'page-{page:04}.png').read_bytes()
        with httpx.Client(timeout=60,trust_env=False) as client:
            response=client.post('http://ocr:8080/crop',json={'image_base64':base64.b64encode(raw).decode(),'bbox':region['bbox']})
            response.raise_for_status(); crop=response.json()
        if crop['source_image_sha256']!=evidence['data']['render_sha256']: raise RuntimeError('CROP_SOURCE_MISMATCH')
        prompt=('Yalnız bu kırpılmış resimde görünen figür ve hareket adaylarını kaydet. '
            'Yazıları okuma veya alıntılama, karakter adı verme, hikaye özeti yazma. '
            'JSON {"figures":[{"local_id":"figure_1","appearance":"...","visible_action":"...",'
            '"bbox":[0.0,0.0,0.2,0.2]}],"uncertainties":["..."]}. '
            'bbox kırpım içinde normalize sol üst x,y,genişlik,yükseklik. Gözün açık/kapalı olduğu belirsizse söyle. '
            'Figür yoksa figures boş. En fazla dört figür. Bunlar doğrulanmamış gözlemlerdir.')
        answer,metrics=model([{'role':'user','content':[{'type':'text','text':prompt},
            {'type':'image_url','image_url':{'url':'data:image/png;base64,'+crop['image_base64']}}]}],
            max_tokens=650,prompt_version=VERSION+'-visual-regions')
        figures=[]
        for f in answer.get('figures',[])[:4]:
            box=f.get('bbox',[])
            if not valid_box(box):
                continue
            figures.append({k:f.get(k) for k in ('local_id','appearance','visible_action','bbox')})
        observations.append({'region_bbox':region['bbox'],'crop_sha256':crop['crop_sha256'],
            'figures':figures,'uncertainties':answer.get('uncertainties',[]),'metrics':metrics})
    # No inferred speaker may become a named character without independent grounding.
    save(job,'visual_observations',key,{'pdf_page':page,'evidence_refs':[str(evidence['id'])],
        'observations':observations,'omitted_regions':max(0,len(illustrations)-3),
        'speaker_links':speaker_candidates(layout['data'],{'observations':observations}),
        'speaker':'UNKNOWN','speaker_status':'TAIL_AND_CHARACTER_GROUNDING_NOT_VERIFIED',
        'verification_status':'CANDIDATE','eligible_as_claim_source':False,
        'source_span_ids':[str(s['id']) for s in spans], 'pipeline_version':VERSION,
        'review_status':'PENDING'})


def reusable_claim_candidates(parent,key,spans):
    if not parent:
        return None
    prior=next((r for r in get_records(parent,'page_claims') if r['record_key']==key),None)
    if prior is None:
        return None
    old=[r for r in get_records(parent,'source_spans') if r['data']['pdf_page']==int(key)]
    def context(rows):
        return [(r['data']['text'] if r['data']['status']=='TEXT_AGREED' and r['data']['role']=='TEXT' else '[UNVERIFIED_REGION]',
                 r['data']['bbox']) for r in reading_order(rows)]
    if context(old)!=context(spans):
        return None
    new_by_key={r['record_key']:str(r['id']) for r in spans}
    mapping={str(r['id']):new_by_key[r['record_key']] for r in old if r['record_key'] in new_by_key}
    candidates=[]
    for candidate in prior['data']['claims']+prior['data']['blocked_claims']:
        if any(ref not in mapping for ref in candidate.get('span_refs',[])):
            return None
        candidates.append({**candidate,'span_refs':[mapping[ref] for ref in candidate.get('span_refs',[])]})
    return {'page_role':prior['data']['page_role'],'claims':candidates,
            'uncertainties':prior['data']['uncertainties']},prior['data']['metrics'],str(prior['id'])


def interpret(job,evidence,spans,parent=None):
    from editor.analysis import model
    page=evidence['data']['pdf_page']; key=evidence['record_key']
    usable=[s for s in spans if s['data']['status']=='TEXT_AGREED' and s['data']['role']=='TEXT']
    excluded=[str(s['id']) for s in spans if s not in usable]
    usable_ids={str(s['id']) for s in usable}
    context=[{'span_id':str(s['id']),'text':s['data']['text'] if str(s['id']) in usable_ids else '[UNVERIFIED_REGION]',
              'usable':str(s['id']) in usable_ids,'bbox':s['data']['bbox']} for s in reading_order(spans)]
    reused=reusable_claim_candidates(parent,key,spans)
    if reused:
        result,metrics,reused_id=reused
    elif not usable:
        result={'page_role':'UNKNOWN','claims':[],'uncertainties':['NO_AGREED_TEXT_SPANS']}; metrics={}
    else:
        prompt=('Yalnız verilen OCR metin bölgelerinden aday çıkar. Görsel betimleme girdisi yoktur. '
            'UNVERIFIED_REGION okunması uyuşmayan yeri gösterir; üzerinden atlayıp cümle kurma. '
            'Eksik bölgeler var; eksik cümleyi tamamlama. Bağlamı eksikse iddia üretme. '
            'JSON {"page_role":"NARRATIVE|ACTIVITY|FRONT_MATTER|APPENDIX|MIXED|UNKNOWN",'
            '"claims":[{"kind":"EVENT|ENTITY|STATEMENT","text":"...","quote":"kaynakta aynen geçen dayanak",'
            '"span_refs":["id"],"actor":null,"speaker":null,'
            '"narrative_mode":"ACTUAL|REPORTED|PLANNED|HYPOTHETICAL|DREAM|JOKE|UNKNOWN",'
            '"polarity":"AFFIRMED|NEGATED|UNKNOWN"}],"uncertainties":["..."]}. '
            'Etkinlik yönergeleri ve künye hikaye olayı değildir. Bağlaç/zarfı kişi adı sayma. '
            'Adı açık metinle bağlanamayan konuşmacı null. En fazla 4 aday. Alıntıyı yeniden yazma.\n'+json.dumps(context,ensure_ascii=False))
        try:
            result,metrics=model([{'role':'user','content':prompt}],max_tokens=1400,prompt_version=VERSION+'-claims')
        except RuntimeError as exc:
            if str(exc) not in ('CONTEXT_BUDGET_EXCEEDED','MODEL_OUTPUT_TRUNCATED'): raise
            result={'page_role':'UNKNOWN','claims':[],'uncertainties':[str(exc)]};metrics={}
    allowed={str(s['id']):s for s in usable}; accepted=[]; blocked=[]
    for c in result.get('claims',[]):
        refs=c.get('span_refs',[]); chosen=[allowed[r] for r in refs if r in allowed]
        reason=quote_check(c.get('quote',''),chosen,spans) if refs and len(chosen)==len(refs) else 'INVALID_SPAN_REFERENCE'
        if reason=='MATCH' and bool(negation(c.get('quote',''))) != bool(negation(c.get('text',''))):
            reason='CLAIM_POLARITY_REQUIRES_REVIEW'
        if c.get('kind')=='EVENT' and result.get('page_role') in ('ACTIVITY','FRONT_MATTER','APPENDIX','UNKNOWN'):
            reason='NON_NARRATIVE_EVENT_BLOCKED'
        if c.get('kind')=='ENTITY': reason='ENTITY_IDENTITY_REQUIRES_REVIEW'
        # Supported transcription is not entailment. Keep all semantic candidates out
        # of accepted facts until semantic and speaker checks exist for that claim.
        item={**c,'speaker':None,'speaker_status':'UNKNOWN',
            'source_gate':reason,'verification_status':'TEXT_MATCHED_CANDIDATE' if reason=='MATCH' else 'NEEDS_REVIEW',
            'eligible_for_synthesis':False,'evidence_refs':[str(evidence['id'])]}
        (accepted if reason=='MATCH' else blocked).append(item)
    save(job,'page_claims',key,{'pdf_page':page,'page_role':result.get('page_role','UNKNOWN'),
        'claims':accepted,'blocked_claims':blocked,'excluded_span_ids':excluded,
        'input_span_ids':list(allowed),'input_visual_descriptions':False,
        'reused_claim_candidates_from':reused_id if reused else None,
        'reused_from_generation':str(parent) if reused else None,
        'uncertainties':result.get('uncertainties',[]),'metrics':metrics,'review_status':'PENDING'})
    save(job,'page_checks',key,{'pdf_page':page,'evidence_refs':[str(evidence['id'])],
        'status':'NEEDS_REVIEW','text_matched_candidates':len(accepted),'blocked_claims':len(blocked),
        'source_review_spans':len(excluded),'semantic_acceptance':False,
        'reason':'SEMANTIC_AND_SPEAKER_ACCEPTANCE_PENDING','pipeline_version':VERSION})


def run(job):
    from editor.analysis import ingest
    gen=job['generation_id']; source=source_for(gen); root=ROOT/source['sha256']
    with connection() as db:
        fence(db,job)
        previous=db.execute('SELECT manifest FROM editor.generations WHERE id=%s',(gen,)).fetchone()['manifest']
        if previous.get('code_manifest') and previous['code_manifest']!=code_manifest():
            raise RuntimeError('PIPELINE_VERSION_CHANGED_NEW_GENERATION_REQUIRED')
        db.execute('UPDATE editor.generations SET manifest=manifest || %s WHERE id=%s',
            (Jsonb({'pipeline_version':VERSION,'code_manifest':code_manifest(),
                   'old_visual_reuse':False,'processing_order':'one_page_source_visual_claim_gate_then_next',
                   'source_of_quotes':'source_spans_only'}),gen))
    parent=previous.get('reuse_measurements_from')
    if parent and source_for(parent)['content_version_id']!=source['content_version_id']:
        raise RuntimeError('REUSED_CONTENT_VERSION_MISMATCH')
    ingest(job)
    document=json.loads((root/'docling.json').read_text())
    evidence=get_records(gen,'evidence'); done={r['record_key'] for r in get_records(gen,'page_readings')}
    observed={r['record_key'] for r in get_records(gen,'visual_observations')}
    checked={r['record_key'] for r in get_records(gen,'page_checks')}
    for row in evidence:
        with connection() as db: fence(db,job)
        if row['record_key'] not in done: optical(job,row,document,root,parent)
        layouts={r['record_key']:r for r in get_records(gen,'layout_regions')}
        all_spans=get_records(gen,'source_spans')
        spans=[s for s in all_spans if s['data']['pdf_page']==row['data']['pdf_page']]
        if row['record_key'] not in observed: observe(job,row,layouts[row['record_key']],spans,root,parent)
        if row['record_key'] not in checked: interpret(job,row,spans,parent)
    with connection() as db:
        fence(db,job)
        db.execute("UPDATE editor.jobs SET status='COMPLETED',finished_at=now(),progress=%s WHERE id=%s",
            (Jsonb({'stage':'page_checks','status':'NEEDS_REVIEW','completed_pages':len(evidence)}),job['id']))
        db.execute("UPDATE editor.generations SET status='NEEDS_REVIEW' WHERE id=%s",(gen,))
