"""Single networkless filesystem consumer. No DB credentials or Docker socket."""
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from editor.parse_contract import ROOT, QUEUE, atomic_json, digest, validate_source

running = True
child = None


def stop(*_):
    global running
    running = False
    if child and child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)


def heartbeat():
    atomic_json(QUEUE / 'heartbeat.json', {'at': time.time()})


def execute(command, log, deadline, status_path):
    global child
    child = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
    try:
        while child.poll() is None:
            heartbeat()
            with open(log.name, 'rb') as reader:
                reader.seek(max(0, os.path.getsize(log.name)-8192))
                for line in reader.read().decode(errors='replace').splitlines()[::-1]:
                    try:
                        progress=json.loads(line)
                        if isinstance(progress,dict) and any(k in progress for k in ('rendered_pages','page_local_ocr_completed','native_pdf_position_pages')):
                            atomic_json(status_path,{'status':'RUNNING','progress':progress})
                            break
                    except ValueError:
                        pass
            cancelled=status_path.with_name(status_path.name.replace('.status.json','.cancel.json')).exists()
            if cancelled or not running or time.monotonic() > deadline:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise RuntimeError('CANCELLED' if cancelled else 'PARSER_INTERRUPTED' if not running else 'SOURCE_TIMEOUT')
            time.sleep(2)
        if child.returncode:
            raise RuntimeError('SOURCE_PARSE_FAILED')
    finally:
        child = None


def process(request_path):
    request = json.loads(request_path.read_text())
    upload = str(uuid.UUID(request_path.name.removesuffix('.request.json')))
    expected = request['sha256']
    if not re.fullmatch('[a-f0-9]{64}', expected):
        raise RuntimeError('INVALID_SOURCE_HASH')
    result_path = QUEUE / (upload + '.result.json')
    if result_path.exists():
        return
    source = ROOT / 'uploads' / (upload + '.pdf')
    final = ROOT / expected
    reused = final.exists()
    attempts = ROOT / 'parse-attempts' / upload
    if attempts.exists() and len(list(attempts.iterdir()))>=3:
        atomic_json(result_path, {'status':'FAILED','error_code':'PARSE_ATTEMPTS_EXHAUSTED','sha256':expected})
        return
    attempt = attempts / str(uuid.uuid4())
    attempt.mkdir(parents=True)
    atomic_json(QUEUE / (upload + '.status.json'), {'status': 'RUNNING', 'started_at': time.time()})
    try:
        if (QUEUE/(upload+'.cancel.json')).exists(): raise RuntimeError('CANCELLED')
        if source.stat().st_size != request['bytes'] or digest(source) != expected:
            raise RuntimeError('SOURCE_HASH_MISMATCH')
        if not reused:
            deadline = time.monotonic() + int(os.environ.get('EDITOR_PARSE_TIMEOUT', '3600'))
            with (attempt / 'parser.log').open('xb') as log:
                status_path=QUEUE / (upload + '.status.json')
                execute([sys.executable, '-m', 'editor.ingestion', str(source), '--output', str(attempt), '--docling'], log, deadline,status_path)
                execute([sys.executable, '-m', 'editor.source_regions', str(attempt / expected)], log, deadline,status_path)
            validate_source(attempt / expected, expected, request['bytes'])
            # Publish all source files at once. Incomplete attempts remain separate.
            (attempt / expected).rename(final)
        manifest = validate_source(final, expected, request['bytes'])
        atomic_json(result_path, {'status': 'COMPLETED', 'sha256': expected,
                    'pages': manifest['pdf_pages'], 'reused_artifacts': reused})
    except Exception as exc:
        code = str(exc) if re.fullmatch('[A-Z_]{3,80}', str(exc)) else type(exc).__name__
        # An interrupted service retries from a separate attempt, preserving all evidence.
        if running:
            atomic_json(result_path, {'status': 'CANCELLED' if code=='CANCELLED' else 'FAILED', 'error_code': code, 'sha256': expected})
        raise


def main():
    QUEUE.mkdir(parents=True, exist_ok=True)
    lock = (QUEUE / 'consumer.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while running:
        heartbeat()
        for request in sorted(QUEUE.glob('*.request.json')):
            if not running:
                break
            try:
                process(request)
            except Exception as exc:
                print('parse_error:' + type(exc).__name__, flush=True)
        for _ in range(3):
            if running:
                time.sleep(1)


if __name__ == '__main__':
    main()
