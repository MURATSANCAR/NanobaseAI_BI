"""Measure smaller source regions; never repair an unresolved parent string."""
import base64
import csv
import hashlib
import io
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path

from editor.source_alignment import valid_box

VERSION = 'source-fragments-v1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def propose(row, max_candidates=4):
    d=row['data']; parent=d['bbox']
    if d.get('status')!='NEEDS_REVIEW' or not valid_box(parent): return []
    words=d.get('pdf_word_regions',[]) if d.get('pdf_usable') else []
    geometry='NATIVE_PDF'
    if not words:
        words=d.get('secondary_word_regions',[]); geometry='TESSERACT_WORDS'
    words=[w for w in words if valid_box(w.get('bbox')) and w.get('text','').strip()]
    words.sort(key=lambda w:w['bbox'][0])
    x,y,width,height=parent
    if any(w['bbox'][1]+w['bbox'][3] < y or w['bbox'][1] > y+height for w in words): return []
    candidates=[]
    for end,word in enumerate(words[:-1],1):
        if end < 3 or not re.search(r'[.!?]["”’\']?$',word['text']): continue
        # Prefix preserves the start of a quotation/attribution. The text itself
        # is never copied into a candidate source or recognition prompt.
        chosen=words[:end]
        left=max(x,min(w['bbox'][0] for w in chosen)-.003)
        right=min(x+width,max(w['bbox'][0]+w['bbox'][2] for w in chosen)+.003)
        next_left=words[end]['bbox'][0]
        if right >= next_left: continue
        box=[left,y,right-left,height]
        if not valid_box(box): continue
        candidates.append({'bbox':box,'geometry_reader':geometry,'word_range':[0,end],
                           'boundary':'TERMINAL_PUNCTUATION_PREFIX', 'parent_source_span_id':str(row['id'])})
        if len(candidates)>=max_candidates:break
    return candidates


def measure_tesseract(raw, row, candidate):
    from PIL import Image,ImageOps
    d=row['data']
    if digest(raw)!=d['render_sha256'] or candidate['parent_source_span_id']!=str(row['id']):
        raise RuntimeError('FRAGMENT_PARENT_SCOPE_MISMATCH')
    image=Image.open(io.BytesIO(raw)).convert('RGB')
    if image.width*image.height>20_000_000:raise RuntimeError('FRAGMENT_PIXEL_LIMIT')
    x,y,w,h=candidate['bbox']; px,py,pw,ph=d['bbox']
    if not valid_box(candidate['bbox']) or x<px or y<py or x+w>px+pw+1e-9 or y+h>py+ph+1e-9:
        raise RuntimeError('FRAGMENT_OUTSIDE_PARENT')
    bounds=[math.floor(x*image.width),math.floor(y*image.height),math.ceil((x+w)*image.width),math.ceil((y+h)*image.height)]
    crop=image.crop(bounds); scale=min(3,max(1,64/crop.height))
    crop=crop.resize((round(crop.width*scale),round(crop.height*scale)))
    crop=ImageOps.expand(crop,border=16,fill='white')
    stream=io.BytesIO();crop.save(stream,format='PNG');png=stream.getvalue()
    readings=[]
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'crop.png';path.write_bytes(png)
        for psm in (7,13):
            proc=subprocess.run(['tesseract',str(path),'stdout','-l','tur+eng','--psm',str(psm),'tsv'],
                capture_output=True,check=True,timeout=30,env={**os.environ,'OMP_THREAD_LIMIT':'1'})
            words=[w for w in csv.DictReader(io.StringIO(proc.stdout.decode()),delimiter='\t',quoting=csv.QUOTE_NONE)
                   if w['level']=='5' and w['text'].strip()]
            readings.append({'psm':psm,'text':' '.join(w['text'] for w in words),
                             'raw_tsv':proc.stdout.decode(),'tsv_sha256':digest(proc.stdout)})
    trained=Path('/usr/share/tesseract-ocr/5/tessdata')
    return {**candidate,'parent_render_sha256':digest(raw),'crop_sha256':digest(png),
            'crop_image_base64':base64.b64encode(png).decode(),'crop_pixels':bounds,
            'resize_scale':scale,'white_padding_pixels':16,'readings':readings,
            'engine':subprocess.check_output(['tesseract','--version'],text=True).splitlines()[0],
            'model_sha256':{lang:digest((trained/(lang+'.traineddata')).read_bytes()) for lang in ('tur','eng')}}


def decide(row, measurement, paddle_raw, vl_raw=None):
    from editor.optical_selection import word_tokens
    result=json.loads(paddle_raw); lines=result.get('lines',[])
    if (result.get('image_sha256')!=measurement['crop_sha256']
            or digest(base64.b64decode(measurement['crop_image_base64'],validate=True))!=measurement['crop_sha256']
            or measurement['parent_source_span_id']!=str(row['id'])
            or measurement['parent_render_sha256']!=row['data']['render_sha256']
            or any(digest(r['raw_tsv'].encode())!=r['tsv_sha256'] for r in measurement['readings'])):
        raise RuntimeError('FRAGMENT_MEASUREMENT_SCOPE_MISMATCH')
    ordered=sorted(lines,key=lambda line:(min(p[1] for p in line['polygon']),min(p[0] for p in line['polygon'])))
    text=' '.join(line['text'] for line in ordered)
    signatures=[word_tokens(r['text']) for r in measurement['readings']]
    tokens=word_tokens(text); blockers=[]
    if not tokens or len(signatures)!=2 or any(s!=tokens for s in signatures):blockers.append('INDEPENDENT_LEXICAL_DISAGREEMENT')
    if not lines or any(not isinstance(line.get('score'),(int,float)) or line['score']<.85 for line in lines):
        blockers.append('PADDLE_LOW_CONFIDENCE')
    # Ignore glyph variants/whitespace only, not quotation/negation boundaries.
    def punctuation(value):
        words=0; result=[]
        for token in re.findall(r'\w+|[^\w\s]',value):
            if token[0].isalnum() or token[0]=='_':words+=1
            else:result.append((words,token.translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))))
        return result
    selected_reader='PPOCR_FRAGMENT'
    vl_conflicts=[]; support_policy='PPOCR_AND_TESSERACT_FULL_READING'
    if punctuation(text)!=punctuation(measurement['readings'][0]['text']):
        supported=False
        if vl_raw is not None:
            from editor.source_pipeline import negation
            vl=json.loads(vl_raw); choice=vl['choices'][0]; vl_text=choice['message']['content']
            vl_tokens=word_tokens(vl_text) if isinstance(vl_text,str) else []
            vl_conflicts=[{'index':i,'selected_token':a,'vl_token':b}
                          for i,(a,b) in enumerate(zip(tokens,vl_tokens)) if a!=b]
            if len(tokens)!=len(vl_tokens):vl_conflicts.append({'reason':'TOKEN_COUNT_MISMATCH'})
            supported=(isinstance(vl_text,str) and choice.get('finish_reason')=='stop'
                       and vl.get('model')==os.environ.get('EDITOR_OCR_VL_MODEL','paddleocr-vl-1.6')
                       and len(vl_tokens)==len(tokens)
                       and word_tokens(' '.join(negation(vl_text)))==word_tokens(' '.join(negation(measurement['readings'][0]['text'])))
                       and punctuation(vl_text)==punctuation(measurement['readings'][0]['text'])
                       and punctuation(vl_text)==punctuation(measurement['readings'][1]['text']))
            if supported:
                text=measurement['readings'][0]['text'];selected_reader='TESSERACT_PSM7_FRAGMENT'
                support_policy='LEXICAL_PPOCR_TESS7_TESS13_PUNCTUATION_TESS7_TESS13_VL'
        if not supported:blockers.append('QUOTE_OR_PUNCTUATION_DISAGREEMENT')
    if result.get('regional_truncated'):blockers.append('PADDLE_TRUNCATED')
    proof={**measurement,'paddle_raw_response':paddle_raw,'paddle_response_sha256':digest(paddle_raw.encode()),
           'paddle_model_manifest':result.get('models'), 'method':VERSION,'blockers':blockers,
           'vl_raw_response':vl_raw,'vl_response_sha256':digest(vl_raw.encode()) if vl_raw else None,
           'vl_lexical_conflicts':vl_conflicts,'support_policy':support_policy,
           'selected_text_is_unmodified_reader_output':True}
    identifier=digest(json.dumps([str(row['id']),measurement['bbox'],measurement['crop_sha256'],
                                 proof['paddle_response_sha256'],proof['vl_response_sha256']],separators=(',',':')).encode())
    d=row['data']
    return {'id':identifier,'record_key':row['record_key']+'-fragment-'+identifier[:12],
            'data':{'pdf_page':d['pdf_page'],'bbox':measurement['bbox'],'render_sha256':d['render_sha256'],
                    'coordinate_system':'normalized_top_left','role':'TEXT','text':text,'raw_text':text,
                    'status':'TEXT_AGREED' if not blockers else 'NEEDS_REVIEW','method':VERSION,
                    'parent_source_span_id':str(row['id']),'parent_status':d['status'],'measurement':proof,
                    'selected_reader':selected_reader,
                    'evidence_refs':d.get('evidence_refs',[]),
                    'eligible_for_synthesis':False,'visual_identity_verified':False}}
