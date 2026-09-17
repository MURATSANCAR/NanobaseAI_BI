"""Bounded offline crop rereading; never rewrite original source or decisions."""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

from PIL import Image, ImageOps
from editor.source_alignment import valid_box
from editor.source_pipeline import quote_tokens

VERSION = 'region-reread-v1'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def reread_page(request):
    source_hash = request['source_sha256']
    if len(source_hash) != 64 or any(c not in '0123456789abcdef' for c in source_hash):
        raise ValueError('INVALID_SOURCE_HASH')
    generation = str(uuid.UUID(request['generation_id']))
    page = request['pdf_page']
    if type(page) is not int or not 1 <= page <= 100:
        raise ValueError('INVALID_PAGE')
    root = Path('/data/artifacts')/source_hash
    raw = (root/'ocr-regions-v2'/f'page-{page:04}.png').read_bytes()
    if digest(raw) != request['render_sha256']:
        raise ValueError('SOURCE_RENDER_MISMATCH')
    request_hash = digest(json.dumps(request, sort_keys=True).encode())
    target = root/VERSION/generation/f'page-{page:04}.json'
    if target.exists():
        previous = json.loads(target.read_text())
        if (previous['request_sha256'] != request_hash
                or previous['code_sha256'] != digest(Path(__file__).read_bytes())):
            raise ValueError('IMMUTABLE_REREAD_REQUEST_CHANGED')
        return previous
    spans = request['spans']
    if len(spans) > 256:
        raise ValueError('REGION_LIMIT')
    image = Image.open(io.BytesIO(raw)).convert('RGB')
    if image.width*image.height > 20_000_000:
        raise ValueError('PIXEL_LIMIT')
    results = []
    engine = subprocess.check_output(['tesseract', '--version'], text=True).splitlines()[0]
    traineddata = Path('/usr/share/tesseract-ocr/5/tessdata')
    models = {lang: digest((traineddata/(lang+'.traineddata')).read_bytes()) for lang in ('tur', 'eng')}
    for row in spans:
        d = row['data']; box = d['bbox']
        if not valid_box(box) or d['render_sha256'] != request['render_sha256'] or d['pdf_page'] != page:
            raise ValueError('REGION_SCOPE_MISMATCH')
        x, y, w, h = box
        # Crop without neighbouring text; white padding is added afterwards.
        bounds = [math.floor(x*image.width), math.floor(y*image.height),
                  min(image.width, math.ceil((x+w)*image.width)),
                  min(image.height, math.ceil((y+h)*image.height))]
        crop = image.crop(tuple(bounds))
        scale = min(3, max(1, 64/crop.height))
        crop = crop.resize((max(1, round(crop.width*scale)), max(1, round(crop.height*scale))))
        crop = ImageOps.expand(crop, border=16, fill='white')
        stream = io.BytesIO(); crop.save(stream, format='PNG'); crop_bytes = stream.getvalue()
        readings = []
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'crop.png'; path.write_bytes(crop_bytes)
            for psm in (7, 13):
                proc = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'tur+eng',
                                       '--psm', str(psm), 'tsv'], capture_output=True,
                                      check=True, timeout=30, env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
                words = [r for r in csv.DictReader(io.StringIO(proc.stdout.decode()),
                         delimiter='\t', quoting=csv.QUOTE_NONE) if r['level'] == '5' and r['text'].strip()]
                text = ' '.join(r['text'] for r in words)
                readings.append({'psm': psm, 'text': text,
                                 'word_confidences': [float(r['conf']) for r in words],
                                 'tsv_sha256': digest(proc.stdout)})
        signature = quote_tokens(readings[0]['text'])
        stable = bool(signature) and signature == quote_tokens(readings[1]['text'])
        supports = []
        if stable:
            for key in ('raw_text', 'region_text', 'secondary_text', 'pdf_text'):
                if key == 'pdf_text' and not d.get('pdf_usable'):
                    continue
                if signature == quote_tokens(d.get(key) or ''):
                    supports.append(key)
        results.append({'source_span_id': str(row['id']), 'bbox': box,
                        'crop_pixels': bounds, 'crop_sha256': digest(crop_bytes),
                        'readings': readings, 'stable_reread': stable,
                        'matching_original_readers': supports,
                        'status': 'REREAD_SUPPORTED_CANDIDATE' if stable and supports else 'NEEDS_REVIEW',
                        'eligible_for_synthesis': False})
    report = {'generation_id': generation, 'pdf_page': page, 'source_sha256': source_hash,
              'render_sha256': request['render_sha256'], 'request_sha256': request_hash,
              'method': VERSION, 'code_sha256': digest(Path(__file__).read_bytes()),
              'engine': engine, 'models': models, 'regions': results,
              'semantic_acceptance': False, 'original_records_modified': False}
    target.parent.mkdir(parents=True, exist_ok=True)
    # Install an immutable complete JSON atomically; never leave a partial result.
    temporary = target.with_suffix('.'+str(uuid.uuid4())+'.tmp')
    try:
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return report


if __name__ == '__main__':
    requests = json.load(sys.stdin)
    for request in requests:
        result = reread_page(request)
        print(json.dumps({'page': result['pdf_page'], 'regions': len(result['regions']),
                          'stable': sum(r['stable_reread'] for r in result['regions']),
                          'supported_candidates': sum(r['status'] == 'REREAD_SUPPORTED_CANDIDATE' for r in result['regions']),
                          'semantic_acceptance': False}), flush=True)
