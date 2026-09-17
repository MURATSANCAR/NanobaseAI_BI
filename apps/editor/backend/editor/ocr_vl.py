"""Demand-driven region OCR; no character attribution or free-form source repair."""
import base64
import hashlib
import json
import os
from pathlib import Path
import time
import unicodedata

import httpx
from editor.optical_selection import word_tokens
from editor.source_alignment import valid_box

VERSION = 'paddleocr-vl-region-v1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_region(raw, evidence, bbox):
    if not valid_box(bbox) or digest(raw) != evidence['ocr_render_sha256']:
        raise RuntimeError('OCR_VL_SOURCE_MISMATCH')
    base = os.environ['EDITOR_OCR_VL_BASE_URL'].rstrip('/')
    name = os.environ.get('EDITOR_OCR_VL_MODEL', 'paddleocr-vl-1.6')
    started = time.time()
    with httpx.Client(timeout=900, trust_env=False) as client:
        # The CPU crop service supplies geometry only, not a transcription prompt.
        response = client.post('http://ocr:8080/crop', json={
            'image_base64':base64.b64encode(raw).decode(), 'bbox':bbox})
        response.raise_for_status(); crop = response.json()
        png = base64.b64decode(crop['image_base64'], validate=True)
        if (crop['source_image_sha256'] != digest(raw) or crop['bbox'] != bbox
                or digest(png) != crop['crop_sha256']):
            raise RuntimeError('OCR_VL_CROP_MISMATCH')
        payload = {'model':name, 'temperature':0, 'max_tokens':512,
                   'messages':[{'role':'user','content':[
                       {'type':'image_url','image_url':{'url':'data:image/png;base64,'+crop['image_base64']}},
                       {'type':'text','text':'OCR:'}]}]}
        request_raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
        # No health polling: this request wakes the gateway. A read timeout is
        # not retried, because an upstream inference could still be running.
        response = client.post(base+'/v1/chat/completions', content=request_raw,
                               headers={'Content-Type':'application/json'})
        if response.status_code != 200:
            raise RuntimeError('OCR_VL_HTTP_'+str(response.status_code))
        result = response.json(); choice = result['choices'][0]
        text = choice['message']['content']
        if not isinstance(text, str) or result.get('model') != name:
            raise RuntimeError('OCR_VL_RESPONSE_SCHEMA_MISMATCH')
    return {'method':VERSION, 'model':name, 'model_revision':os.environ.get('EDITOR_OCR_VL_REVISION'),
            'code_sha256':digest(Path(__file__).read_bytes()),
            'source_sha256':evidence['source_sha256'], 'render_sha256':digest(raw),
            'pdf_page':evidence['pdf_page'], 'bbox':bbox, 'crop_sha256':digest(png),
            'crop_image_base64':crop['image_base64'],
            'request_sha256':digest(request_raw), 'raw_response':response.text,
            'response_sha256':digest(response.content), 'text':text,
            'finish_reason':choice['finish_reason'], 'usage':result.get('usage',{}),
            'started_at':started, 'finished_at':time.time(),
            'seconds':round(time.time()-started,3),
            'status':'READ' if choice['finish_reason']=='stop' else 'TRUNCATED',
            'eligible_for_synthesis':False}


def select_supported(measurement, line, secondary, pdf_text, pdf_usable, reread):
    """VL never wins alone. Require clean native PDF or two stable crop PSMs.

    Stable crop disagreement and usable native disagreement are vetoes. Whole
    page Tesseract may be superseded only by native PDF plus crop agreement.
    Character identity and semantic validity remain outside this gate.
    """
    text=measurement['text']; tokens=word_tokens(text); blockers=[]; support=[]
    clean=lambda value: not any(unicodedata.category(c) in ('Co','Cs') or c=='\ufffd' for c in value)
    if measurement['status']!='READ': blockers.append('OCR_VL_TRUNCATED')
    if not tokens or not clean(text): blockers.append('OCR_VL_EMPTY_OR_CORRUPT')
    native=bool(pdf_usable and clean(pdf_text) and tokens and tokens==word_tokens(pdf_text))
    if native: support.append('NATIVE_PDF')
    if pdf_usable and not native: blockers.append('USABLE_PDF_CONFLICT')
    raw=[r['text'] for r in reread['readings']] if reread else []
    stable=bool(len(raw)==2 and word_tokens(raw[0]) and word_tokens(raw[0])==word_tokens(raw[1]))
    crop=bool(stable and tokens==word_tokens(raw[0]) and all(clean(r) for r in raw))
    if crop: support.append('TESSERACT_CROP')
    if stable and not crop: blockers.append('STABLE_REREAD_CONFLICT')
    if not native and not crop: blockers.append('NO_INDEPENDENT_REGION_SUPPORT')
    regional=bool(tokens and tokens==word_tokens(line.get('region_text') or ''))
    if regional: support.append('PPOCR_REGION')
    if not regional: blockers.append('PPOCR_REGION_DISAGREES')
    if word_tokens(secondary) and tokens!=word_tokens(secondary) and not (native and crop):
        blockers.append('SECONDARY_READER_CONFLICT')
    return {'method':VERSION, 'selected_text':text if not blockers else None,
            'supporting_readers':support,'blockers':blockers,'pdf_matches':native,
            'eligible_for_synthesis':False}
