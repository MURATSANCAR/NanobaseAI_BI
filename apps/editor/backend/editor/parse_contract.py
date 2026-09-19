"""Shared filesystem contract for the networkless parser and application."""
import hashlib
import json
import os
from pathlib import Path
import uuid

ROOT = Path('/data/artifacts')
QUEUE = ROOT / 'parse-queue'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + str(uuid.uuid4()) + '.tmp')
    with temporary.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def validate_source(directory, expected_sha, expected_bytes):
    """Check actual source and every render before a content version is admitted."""
    manifest = json.loads((directory / 'manifest.json').read_text())
    original = directory / 'original.pdf'
    if (manifest.get('sha256') != expected_sha or original.stat().st_size != expected_bytes
            or digest(original) != expected_sha or manifest.get('bytes') != expected_bytes):
        raise RuntimeError('SOURCE_HASH_MISMATCH')
    pages = manifest.get('pdf_pages')
    if (not isinstance(pages, int) or not 1 <= pages <= int(os.environ.get('EDITOR_MAX_PAGES', '100'))
            or not manifest.get('source_accounting_complete')
            or [p['pdf_page'] for p in manifest['pages']] != list(range(1, pages + 1))):
        raise RuntimeError('SOURCE_ACCOUNTING_INCOMPLETE')
    if digest(directory / 'docling.json') != manifest['docling_sha256']:
        raise RuntimeError('DOCLING_HASH_MISMATCH')
    for page in manifest['pages']:
        n = page['pdf_page']
        if digest(directory / f'page-{n:04}.png') != page['render_sha256']:
            raise RuntimeError('RENDER_HASH_MISMATCH')
        for subdir in ('ocr-regions-v2', 'pdf-text-regions-v1'):
            record = json.loads((directory / subdir / f'page-{n:04}.json').read_text())
            if record['source_sha256'] != expected_sha or record['pdf_page'] != n:
                raise RuntimeError('REGION_SOURCE_MISMATCH')
            if subdir == 'ocr-regions-v2':
                if (digest(directory / subdir / f'page-{n:04}.png') != record['render_sha256']
                        or digest(directory / subdir / f'page-{n:04}.tsv') != record['raw_tsv_sha256']):
                    raise RuntimeError('REGION_HASH_MISMATCH')
    return manifest
