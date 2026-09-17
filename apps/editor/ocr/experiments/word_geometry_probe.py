"""Offline measurement only: crop from independent reader word geometry.

Invoked inside the existing OCR image, with original artifacts mounted read-only.
No expected text is supplied to the recognizer. No source/decision is written.
"""
import hashlib
import io
import json
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageOps
from paddleocr import TextRecognition

request = json.loads(Path('/request.json').read_text())
reader = TextRecognition(model_name='latin_PP-OCRv5_mobile_rec',
    model_dir='/opt/models/latin_PP-OCRv5_mobile_rec', device='cpu',
    cpu_threads=4, enable_mkldnn=False)
results = []
started = time.monotonic()
for page in request['pages']:
    raw = (Path('/data/artifacts')/request['source_sha256']/'ocr-regions-v2'/f"page-{page['page']:04}.png").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == page['render_sha256']
    image = Image.open(io.BytesIO(raw)).convert('RGB')
    for region in page['regions']:
        words = region['word_boxes']
        if not words:
            results.append({'source_span_id': region['id'], 'status':'NO_WORD_GEOMETRY'})
            continue
        # Use independent OCR ink boxes, never trim according to matching text.
        x0 = max(0, math.floor(min(b[0] for b in words)*image.width)-1)
        y0 = max(0, math.floor(min(b[1] for b in words)*image.height)-1)
        x1 = min(image.width, math.ceil(max(b[0]+b[2] for b in words)*image.width)+1)
        y1 = min(image.height, math.ceil(max(b[1]+b[3] for b in words)*image.height)+1)
        crop = image.crop((x0,y0,x1,y1))
        crop = ImageOps.expand(crop, border=10, fill='white')
        crop = crop.resize((crop.width*2,crop.height*2),Image.Resampling.BICUBIC)
        stream = io.BytesIO(); crop.save(stream,format='PNG')
        output = list(reader.predict(np.asarray(crop)[:,:,::-1].copy()))[0]
        results.append({'source_span_id':region['id'],'status':'MEASUREMENT_ONLY',
            'text':output['rec_text'],'score':float(output['rec_score']),
            'crop_pixels':[x0,y0,x1,y1], 'crop_sha256':hashlib.sha256(stream.getvalue()).hexdigest(),
            'eligible_for_synthesis':False})
    print(json.dumps({'page_completed':page['page'],'regions':len(page['regions'])}),flush=True)
print('MEASUREMENT_JSON:'+json.dumps({'results':results,'seconds':time.monotonic()-started,
    'method':'independent-word-geometry-v1','code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}))
