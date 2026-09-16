"""Networkless page-local OCR: never attach a multi-page paragraph to one page."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    source=Path(sys.argv[1]); manifest=json.loads((source/'manifest.json').read_text())
    from editor.pdf_text_regions import extract
    extract(source)
    target=source/'ocr-regions-v2'; target.mkdir(exist_ok=True)
    for page in manifest['pages']:
        n=page['pdf_page']; destination=target/f'page-{n:04}.json'
        if destination.exists(): continue
        started=time.monotonic(); prefix=target/f'page-{n:04}'
        render=prefix.with_suffix('.png')
        previous=source/'ocr-regions-v1'/render.name
        if not render.exists():
            if previous.exists(): os.link(previous,render)
            else: subprocess.run(['pdftoppm','-f',str(n),'-l',str(n),'-singlefile','-scale-to','2400','-png',str(source/'original.pdf'),str(prefix)],check=True,capture_output=True,timeout=90)
        proc=subprocess.run(['tesseract',str(render),'stdout','-l','tur+eng','--psm','11','tsv'],check=True,capture_output=True,timeout=90)
        prefix.with_suffix('.tsv').write_bytes(proc.stdout)
        # Tesseract TSV does not CSV-escape quotation marks in book dialogue.
        rows=list(csv.DictReader(io.StringIO(proc.stdout.decode()),delimiter='\t',quoting=csv.QUOTE_NONE))
        width=int(rows[0]['width']); height=int(rows[0]['height']); lines={}
        for r in rows:
            if r['level']!='5' or not r['text'].strip(): continue
            if '\t' in r['text'] or '\n' in r['text']: raise RuntimeError('INVALID_TSV_WORD')
            key=tuple(r[k] for k in ('block_num','par_num','line_num'))
            lines.setdefault(key,[]).append(r)
        blocks=[]
        for key,words in lines.items():
            x=min(int(w['left']) for w in words); y=min(int(w['top']) for w in words)
            right=max(int(w['left'])+int(w['width']) for w in words); bottom=max(int(w['top'])+int(w['height']) for w in words)
            blocks.append({'text':' '.join(w['text'] for w in words),'bbox':[x/width,y/height,(right-x)/width,(bottom-y)/height],
              'words':[{'text':w['text'],'confidence':float(w['conf']),
                'bbox':[int(w['left'])/width,int(w['top'])/height,int(w['width'])/width,int(w['height'])/height]} for w in words]})
        result={'pdf_page':n,'source_sha256':manifest['sha256'],'render_sha256':digest(render),
          'render_width':width,'render_height':height,'engine':'tesseract','languages':'tur+eng','psm':11,
          'parser_version':'page-local-tsv-v2','raw_tsv_sha256':digest(prefix.with_suffix('.tsv')),
          'seconds':round(time.monotonic()-started,3),'blocks':blocks,'text':'\n'.join(b['text'] for b in blocks),
          'review_status':'PENDING','coordinate_system':'normalized_top_left'}
        destination.write_text(json.dumps(result,ensure_ascii=False,indent=2))
        if n%10==0 or n==manifest['pdf_pages']: print(json.dumps({'page_local_ocr_completed':n,'total':manifest['pdf_pages']}),flush=True)


if __name__=='__main__': main()
