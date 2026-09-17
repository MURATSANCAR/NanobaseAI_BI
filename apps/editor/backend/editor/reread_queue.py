"""Bounded filesystem OCR queue. Consumer has no network, database, or socket."""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import unicodedata
import uuid

VERSION = 'region-reread-queue-v1'
QUEUE = Path(os.environ.get('EDITOR_REREAD_QUEUE', '/data/reread-queue'))
SOURCE = Path('/data/artifacts')
running = True
child = None


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def code_hash():
    return digest(Path(__file__).read_bytes())


def hash_ok(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def valid_box(box):
    return (isinstance(box, list) and len(box) == 4
            and all(type(v) in (int, float) and math.isfinite(v) for v in box)
            and min(box) >= 0 and box[2] > 0 and box[3] > 0
            and box[0] + box[2] <= 1.001 and box[1] + box[3] <= 1.001)


def publish(path, value, immutable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(value)
    temporary = path.with_name(path.name + '.' + str(uuid.uuid4()) + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        if immutable:
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise RuntimeError('REREAD_IMMUTABLE_CONFLICT')
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_bytes(path, raw):
    temporary = path.with_name(path.name + '.' + str(uuid.uuid4()) + '.part')
    try:
        with temporary.open('xb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != raw:
                raise RuntimeError('REREAD_IMMUTABLE_BYTES_CONFLICT')
    finally:
        temporary.unlink(missing_ok=True)


def capabilities():
    directory = Path('/usr/share/tesseract-ocr/5/tessdata')
    return {'method': VERSION, 'code_sha256': code_hash(),
            'engine': subprocess.check_output(['tesseract', '--version'], text=True).splitlines()[0],
            'models': {lang: digest((directory / (lang + '.traineddata')).read_bytes())
                       for lang in ('tur', 'eng')}}


def validate_request(request, require_current_code=True):
    if (request.get('method') != VERSION or not hash_ok(request.get('code_sha256'))
            or (require_current_code and request.get('code_sha256') != code_hash())):
        raise RuntimeError('REREAD_CODE_MISMATCH')
    uuid.UUID(request['generation_id']); uuid.UUID(request['request_id'])
    if not hash_ok(request['source_sha256']) or not hash_ok(request['render_sha256']):
        raise RuntimeError('REREAD_SOURCE_HASH_INVALID')
    if type(request['pdf_page']) is not int or request['pdf_page'] < 1:
        raise RuntimeError('REREAD_PAGE_INVALID')
    if request['languages'] not in ('tur+eng', 'tur', 'eng') or request['psm'] != [7, 13]:
        raise RuntimeError('REREAD_PROFILE_INVALID')
    if type(request['deadline_seconds']) is not int or not 1 <= request['deadline_seconds'] <= 600:
        raise RuntimeError('REREAD_DEADLINE_INVALID')
    regions = request['regions']
    if not isinstance(regions, list) or not 1 <= len(regions) <= 256:
        raise RuntimeError('REREAD_REGION_LIMIT')
    if len({r['region_key'] for r in regions}) != len(regions):
        raise RuntimeError('REREAD_DUPLICATE_REGION')
    for region in regions:
        if not isinstance(region['region_key'], str) or not 1 <= len(region['region_key']) <= 200 or not valid_box(region['bbox']):
            raise RuntimeError('REREAD_REGION_INVALID')
    if not request['models'] or not all(hash_ok(v) for v in request['models'].values()):
        raise RuntimeError('REREAD_MODEL_MANIFEST_INVALID')
    if set(request['models']) != set(request['languages'].split('+')):
        raise RuntimeError('REREAD_MODEL_MANIFEST_INVALID')
    policy = {k: request[k] for k in ('method','code_sha256','languages','models','engine','psm','deadline_seconds')}
    if 'attempt_token' in request:
        if type(request['attempt_token']) is not int or request['attempt_token'] < 1:
            raise RuntimeError('REREAD_ATTEMPT_INVALID')
        policy['attempt_token'] = request['attempt_token']
    expected_id = str(uuid.uuid5(uuid.UUID(request['generation_id']), str(request['pdf_page']) + ':' + digest(canonical(policy))))
    if expected_id != request['request_id']:
        raise RuntimeError('REREAD_REQUEST_ID_MISMATCH')
    unsigned = {k: v for k, v in request.items() if k != 'request_sha256'}
    if digest(canonical(unsigned)) != request['request_sha256']:
        raise RuntimeError('REREAD_REQUEST_HASH_MISMATCH')


def submit(generation_id, source_sha256, pdf_page, render_sha256, regions, *,
           languages='tur+eng', deadline_seconds=600, expected_models=None, attempt_token=None):
    cap = json.loads((QUEUE / 'capabilities.json').read_text())
    if cap['code_sha256'] != code_hash() or cap['method'] != VERSION:
        raise RuntimeError('REREAD_CONSUMER_VERSION_MISMATCH')
    models = {lang: cap['models'][lang] for lang in languages.split('+')}
    if expected_models is not None and expected_models != models:
        raise RuntimeError('REREAD_MODEL_MISMATCH')
    policy = {'method': VERSION, 'code_sha256': code_hash(), 'languages': languages,
              'models': models, 'engine': cap['engine'], 'psm': [7, 13], 'deadline_seconds': deadline_seconds}
    if attempt_token is not None:
        if type(attempt_token) is not int or attempt_token < 1:
            raise RuntimeError('REREAD_ATTEMPT_INVALID')
        policy['attempt_token'] = attempt_token
    generation_id = str(uuid.UUID(str(generation_id)))
    rid = str(uuid.uuid5(uuid.UUID(generation_id), str(pdf_page) + ':' + digest(canonical(policy))))
    request = {**policy, 'request_id': rid, 'generation_id': generation_id,
               'source_sha256': source_sha256, 'pdf_page': pdf_page,
               'render_sha256': render_sha256, 'regions': regions}
    request['request_sha256'] = digest(canonical(request))
    validate_request(request)
    # A lease may end after durable measurement publication or partial span
    # persistence. Reuse that exact completed proof, never mix attempt provenance
    # in an immutable page. Failed/cancelled attempts have no completed report.
    if attempt_token is not None:
        directory = SOURCE / source_sha256 / VERSION / generation_id
        ignored = {'attempt_token', 'request_id', 'request_sha256'}
        identity = {k: v for k, v in request.items() if k not in ignored}
        for path in sorted(directory.glob(f'page-{pdf_page:04}*.json')):
            report = json.loads(path.read_bytes()); prior = report['request']
            if {k: v for k, v in prior.items() if k not in ignored} != identity:
                continue
            pointer = QUEUE / 'results' / (prior['request_id'] + '.json')
            if pointer.exists() and json.loads(pointer.read_bytes()).get('status') != 'COMPLETED':
                continue
            validate_result(prior, report['result'])
            request = prior; rid = prior['request_id']
            break
    saved = artifact_report(request)
    if saved.exists():
        report = json.loads(saved.read_bytes())
        if report['request'] != request:
            raise RuntimeError('REREAD_IMMUTABLE_CONFLICT')
        validate_result(request, report['result'])
        publish(QUEUE / 'results' / (rid + '.json'), {'request_id': rid,
            'request_sha256': request['request_sha256'], 'status': 'COMPLETED',
            'artifact_sha256': digest(saved.read_bytes())}, immutable=True)
    publish(QUEUE / 'requests' / (rid + '.json'), request, immutable=True)
    return request


def validate_result(request, result, require_current_code=True):
    validate_request(request, require_current_code=require_current_code)
    if result.get('request_sha256') != request['request_sha256'] or result.get('request_id') != request['request_id']:
        raise RuntimeError('REREAD_RESULT_SCOPE_MISMATCH')
    if result.get('status') != 'COMPLETED':
        raise RuntimeError(result.get('error_code', 'REREAD_FAILED'))
    for field in ('code_sha256', 'models', 'engine', 'render_sha256', 'source_sha256', 'pdf_page'):
        if result.get(field) != request[field]:
            raise RuntimeError('REREAD_RESULT_PROVENANCE_MISMATCH')
    output = result['regions']
    if len(output) != len(request['regions']):
        raise RuntimeError('REREAD_RESULT_INCOMPLETE')
    measured = {}
    for expected, region in zip(request['regions'], output):
        if region['source_span_id'] != expected['region_key'] or region['bbox'] != expected['bbox']:
            raise RuntimeError('REREAD_REGION_SCOPE_MISMATCH')
        directory = artifact_directory(request) / str(len(measured))
        if digest((directory / 'crop.png').read_bytes()) != region['crop_sha256']:
            raise RuntimeError('REREAD_CROP_HASH_MISMATCH')
        if [r['psm'] for r in region['readings']] != [7, 13]:
            raise RuntimeError('REREAD_PSM_MISMATCH')
        for reading in region['readings']:
            raw_tsv = (directory / ('psm' + str(reading['psm']) + '.tsv')).read_bytes()
            if digest(raw_tsv) != reading['tsv_sha256']:
                raise RuntimeError('REREAD_TSV_HASH_MISMATCH')
            words = [r for r in csv.DictReader(io.StringIO(raw_tsv.decode()), delimiter='\t', quoting=csv.QUOTE_NONE)
                     if r['level']=='5' and r['text'].strip()]
            if (' '.join(r['text'] for r in words) != reading['text']
                    or [float(r['conf']) for r in words] != reading['word_confidences']):
                raise RuntimeError('REREAD_TSV_TEXT_MISMATCH')
        measured[region['source_span_id']] = region
    return measured


def artifact_report(request):
    suffix = '-' + request['request_id'] if 'attempt_token' in request else ''
    return SOURCE / request['source_sha256'] / VERSION / request['generation_id'] / f"page-{request['pdf_page']:04}{suffix}.json"


def artifact_directory(request):
    return artifact_report(request).parent / f"page-{request['pdf_page']:04}" / request['request_id']


def load_verified(provenance, evidence):
    """Revalidate an immutable report, crop and TSVs for inheritance/restore.

    evidence is either an evidence record or its data. Returns region-key mapping.
    """
    d = evidence.get('data', evidence)
    source_hash = d['source_sha256']; page = d['pdf_page']
    generation = str(uuid.UUID(provenance['generation_id']))
    if not hash_ok(source_hash) or type(page) is not int or page < 1:
        raise RuntimeError('REREAD_SOURCE_SCOPE_MISMATCH')
    rid = str(uuid.UUID(provenance['request_id']))
    directory = SOURCE / source_hash / VERSION / generation
    path = directory / f'page-{page:04}-{rid}.json'
    if not path.exists():
        path = directory / f'page-{page:04}.json'
    raw = path.read_bytes()
    if digest(raw) != provenance['artifact_sha256']:
        raise RuntimeError('REREAD_ARTIFACT_HASH_MISMATCH')
    report = json.loads(raw); request = report['request']; result = report['result']
    if (request['source_sha256'] != source_hash or request['pdf_page'] != page
            or request['generation_id'] != generation or request['request_id'] != provenance['request_id']
            or request['render_sha256'] != d.get('ocr_render_sha256', d.get('render_sha256'))):
        raise RuntimeError('REREAD_SOURCE_SCOPE_MISMATCH')
    for field in ('code_sha256', 'engine', 'models', 'request_sha256', 'render_sha256'):
        if provenance.get(field) != request[field]:
            raise RuntimeError('REREAD_PROVENANCE_MISMATCH')
    if digest((SOURCE/source_hash/'ocr-regions-v2'/f'page-{page:04}.png').read_bytes()) != request['render_sha256']:
        raise RuntimeError('REREAD_RENDER_HASH_MISMATCH')
    return validate_result(request, result, require_current_code=False)


def await_result(request, *, check_active, queue_wait_seconds=900, poll_seconds=2):
    if not 1 <= queue_wait_seconds <= 7200 or not .1 <= poll_seconds <= 10:
        raise ValueError('REREAD_WAIT_LIMIT_INVALID')
    deadline = time.monotonic() + queue_wait_seconds
    path = QUEUE / 'results' / (request['request_id'] + '.json')
    while True:
        try:
            check_active()
        except Exception:
            publish(QUEUE / 'cancel' / (request['request_id'] + '.json'), {'request_id': request['request_id']}, immutable=True)
            raise
        if path.exists():
            pointer = json.loads(path.read_bytes())
            if pointer.get('status') != 'COMPLETED':
                raise RuntimeError(pointer.get('error_code', 'REREAD_FAILED'))
            if pointer.get('request_sha256') != request['request_sha256']:
                raise RuntimeError('REREAD_RESULT_SCOPE_MISMATCH')
            provenance = {'method': VERSION, 'generation_id': request['generation_id'],
                'request_id': request['request_id'], 'request_sha256': request['request_sha256'],
                'artifact_sha256': pointer['artifact_sha256'], 'artifact_path': str(artifact_report(request)),
                'code_sha256': request['code_sha256'], 'engine': request['engine'],
                'models': request['models'], 'render_sha256': request['render_sha256']}
            measured = load_verified(provenance, {'source_sha256': request['source_sha256'],
                'pdf_page': request['pdf_page'], 'ocr_render_sha256': request['render_sha256']})
            return measured, provenance
        if time.monotonic() >= deadline:
            publish(QUEUE / 'cancel' / (request['request_id'] + '.json'),
                    {'request_id': request['request_id']}, immutable=True)
            raise RuntimeError('REREAD_QUEUE_TIMEOUT')
        time.sleep(poll_seconds)


def heartbeat():
    publish(QUEUE / 'heartbeat.json', {'at': time.time(), 'method': VERSION})


def stop(*_):
    global running
    running = False
    if child is not None and child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)


def measure(request):
    global child
    from PIL import Image, ImageOps
    validate_request(request)
    cap = capabilities()
    if cap['engine'] != request['engine'] or any(cap['models'].get(k) != v for k, v in request['models'].items()):
        raise RuntimeError('REREAD_MODEL_MISMATCH')
    directory = SOURCE / request['source_sha256']
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest['sha256'] != request['source_sha256'] or request['pdf_page'] > manifest['pdf_pages']:
        raise RuntimeError('REREAD_SOURCE_SCOPE_MISMATCH')
    raw = (directory / 'ocr-regions-v2' / f"page-{request['pdf_page']:04}.png").read_bytes()
    if digest(raw) != request['render_sha256']:
        raise RuntimeError('REREAD_RENDER_HASH_MISMATCH')
    image = Image.open(io.BytesIO(raw)).convert('RGB')
    if image.width * image.height > 20_000_000:
        raise RuntimeError('REREAD_PIXEL_LIMIT')
    deadline = time.monotonic() + request['deadline_seconds']; output = []
    for index, region in enumerate(request['regions']):
        if (QUEUE / 'cancel' / (request['request_id'] + '.json')).exists():
            raise RuntimeError('REREAD_CANCELLED')
        if not running or time.monotonic() >= deadline:
            raise RuntimeError('REREAD_INTERRUPTED' if not running else 'REREAD_TIMEOUT')
        x, y, w, h = region['bbox']
        bounds = [math.floor(x*image.width), math.floor(y*image.height), min(image.width, math.ceil((x+w)*image.width)), min(image.height, math.ceil((y+h)*image.height))]
        crop = image.crop(bounds); scale = min(3, max(1, 64/crop.height))
        crop = crop.resize((max(1, round(crop.width*scale)), max(1, round(crop.height*scale))))
        crop = ImageOps.expand(crop, border=16, fill='white')
        stream = io.BytesIO(); crop.save(stream, format='PNG'); png = stream.getvalue()
        target = artifact_directory(request) / str(index); target.mkdir(parents=True, exist_ok=True)
        crop_path = target / 'crop.png'
        publish_bytes(crop_path, png)
        readings = []
        for psm in (7, 13):
            tsv = target / ('psm' + str(psm) + '.tsv')
            temporary = target / ('psm' + str(psm) + '.' + str(uuid.uuid4()) + '.part')
            with temporary.open('xb') as stdout, (target / ('psm' + str(psm) + '.log')).open('ab') as stderr:
                child = subprocess.Popen(['tesseract', str(crop_path), 'stdout', '-l', request['languages'], '--psm', str(psm), 'tsv'],
                    stdout=stdout, stderr=stderr, start_new_session=True, env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
                call_deadline = min(deadline, time.monotonic()+20)
                while child.poll() is None:
                    heartbeat()
                    cancelled = (QUEUE / 'cancel' / (request['request_id'] + '.json')).exists()
                    if cancelled or not running or time.monotonic() >= call_deadline:
                        os.killpg(child.pid, signal.SIGKILL); child.wait()
                        raise RuntimeError('REREAD_CANCELLED' if cancelled else 'REREAD_INTERRUPTED' if not running else 'REREAD_TIMEOUT')
                    time.sleep(.2)
                if child.returncode:
                    raise RuntimeError('REREAD_ENGINE_FAILED')
                child = None
            raw_tsv = temporary.read_bytes()
            if tsv.exists() and tsv.read_bytes() != raw_tsv:
                raise RuntimeError('REREAD_IMMUTABLE_TSV_CONFLICT')
            if not tsv.exists():
                os.link(temporary, tsv)
            temporary.unlink()
            words = [r for r in csv.DictReader(io.StringIO(raw_tsv.decode()), delimiter='\t', quoting=csv.QUOTE_NONE) if r['level']=='5' and r['text'].strip()]
            readings.append({'psm': psm, 'text': ' '.join(r['text'] for r in words),
                'word_confidences': [float(r['conf']) for r in words], 'tsv_sha256': digest(raw_tsv)})
        tokens = lambda text: re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', text).replace('İ','i').replace('I','ı').lower())
        first, second = [tokens(r['text']) for r in readings]
        output.append({'source_span_id': region['region_key'], 'bbox': region['bbox'], 'crop_pixels': bounds,
            'crop_sha256': digest(png), 'readings': readings, 'stable_reread': bool(first) and first==second,
            'status': 'STABLE_REREAD_CANDIDATE' if first and first==second else 'NEEDS_REVIEW',
            'matching_original_readers': [],
            'eligible_for_synthesis': False})
    return {**{k: request[k] for k in ('request_id','request_sha256','code_sha256','models','engine','render_sha256','source_sha256','pdf_page')},
            'status': 'COMPLETED', 'regions': output}


def main():
    import fcntl
    QUEUE.mkdir(parents=True, exist_ok=True)
    lock = (QUEUE / 'consumer.lock').open('a'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    publish(QUEUE / 'capabilities.json', capabilities())
    while running:
        heartbeat()
        for path in sorted((QUEUE / 'requests').glob('*.json')):
            if not running: break
            result_path = QUEUE / 'results' / path.name
            if result_path.exists(): continue
            request = {}
            try:
                request = json.loads(path.read_text())
                if path.stem != str(uuid.UUID(request['request_id'])):
                    raise RuntimeError('REREAD_REQUEST_NAME_MISMATCH')
                attempts = QUEUE / 'attempts' / request['request_id']
                attempts.mkdir(parents=True, exist_ok=True)
                if len(list(attempts.glob('*.json'))) >= 3:
                    raise RuntimeError('REREAD_ATTEMPTS_EXHAUSTED')
                publish(attempts / (str(uuid.uuid4()) + '.json'), {'started_at': time.time()}, immutable=True)
                result = measure(request)
                validate_result(request, result)
                report = {'request': request, 'result': result}
                publish(artifact_report(request), report, immutable=True)
                result = {'request_id': request['request_id'], 'request_sha256': request['request_sha256'],
                          'status': 'COMPLETED', 'artifact_sha256': digest(canonical(report))}
            except Exception as exc:
                if not running: break
                error = str(exc) if re.fullmatch('[A-Z_]{3,80}', str(exc)) else type(exc).__name__
                result = {'request_id': request.get('request_id'), 'request_sha256': request.get('request_sha256'),
                          'status': 'FAILED', 'error_code': error}
            publish(result_path, result, immutable=True)
        time.sleep(1)


if __name__ == '__main__':
    main()
