"""Offline, bounded source inspection CLI. It does not claim semantic analysis."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def run(args, timeout):
    return subprocess.run(args, check=True, capture_output=True, timeout=timeout).stdout.decode('utf-8', errors='replace')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--docling', action='store_true')
    args = parser.parse_args()
    started = time.monotonic()
    size = args.source.stat().st_size
    maximum = int(os.environ.get('EDITOR_MAX_SOURCE_BYTES', '52428800'))
    if not size or size > maximum:
        raise SystemExit('EMPTY_UPLOAD' if not size else 'SOURCE_LIMIT_EXCEEDED')
    with args.source.open('rb') as stream:
        if stream.read(5) != b'%PDF-':
            raise SystemExit('INVALID_PDF')
    digest = hashlib.file_digest(args.source.open('rb'), 'sha256').hexdigest()
    timeout = int(os.environ.get('EDITOR_PARSE_TIMEOUT', '300'))
    info = run(['pdfinfo', str(args.source)], min(timeout, 30))
    if re.search(r'^Encrypted:\s+yes', info, re.M):
        raise SystemExit('ENCRYPTED_SOURCE')
    pages = int(re.search(r'^Pages:\s+(\d+)', info, re.M).group(1))
    if not pages or pages > int(os.environ.get('EDITOR_MAX_PAGES', '100')):
        raise SystemExit('NO_PAGES' if not pages else 'SOURCE_LIMIT_EXCEEDED')
    target = args.output / digest
    target.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(args.source, target / 'original.pdf')
    manifest = {'sha256': digest, 'bytes': size, 'pdf_pages': pages,
                'semantic_status': 'NOT_ANALYZED', 'pages': [], 'tools': {}}
    for tool in ['pdfinfo', 'pdftoppm', 'tesseract']:
        cmd = [tool, '--version' if tool == 'tesseract' else '-v']
        proc = subprocess.run(cmd, capture_output=True, timeout=10)
        manifest['tools'][tool] = (proc.stdout + proc.stderr).decode(errors='replace').splitlines()[0]
    try:
        for page in range(1, pages + 1):
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('SOURCE_TIMEOUT')
            prefix = target / f'page-{page:04}'
            text = run(['pdftotext', '-f', str(page), '-l', str(page), '-layout', str(args.source), '-'], remaining)
            prefix.with_suffix('.txt').write_text(text)
            run(['pdftoppm', '-f', str(page), '-l', str(page), '-singlefile', '-scale-to', '1600', '-png', str(args.source), str(prefix)], max(1, timeout - (time.monotonic() - started)))
            image = prefix.with_suffix('.png')
            manifest['pages'].append({'pdf_page': page, 'printed_label': None,
                'text_chars': len(text.strip()), 'render_sha256': hashlib.file_digest(image.open('rb'), 'sha256').hexdigest(),
                'status': 'NEEDS_REVIEW', 'reason': 'OCR_AND_VISUAL_VERIFICATION_PENDING'})
        if args.docling:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
            options = PdfPipelineOptions(artifacts_path=os.environ['DOCLING_ARTIFACTS_PATH'])
            options.enable_remote_services = False
            options.ocr_options = TesseractCliOcrOptions(lang=['tur', 'eng'])
            options.document_timeout = max(1, timeout - (time.monotonic() - started))
            converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
            result = converter.convert(args.source, max_num_pages=int(os.environ.get('EDITOR_MAX_PAGES', '100')))
            result.document.save_as_json(target / 'docling.json')
            manifest['docling_status'] = str(result.status)
            manifest['tools']['docling'] = importlib.metadata.version('docling')
        manifest['source_accounting_complete'] = len(manifest['pages']) == pages
    finally:
        manifest['elapsed_seconds'] = round(time.monotonic() - started, 3)
        (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({'sha256': digest, 'pages': pages, 'artifact': str(target / 'manifest.json')}))


if __name__ == '__main__':
    main()
