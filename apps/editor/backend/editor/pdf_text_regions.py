"""Offline native PDF words with positions; never use corrupt text as authority."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from editor.source_alignment import corrupt_character


def extract(source):
    source=Path(source);manifest=json.loads((source/'manifest.json').read_text())
    if hashlib.sha256((source/'original.pdf').read_bytes()).hexdigest()!=manifest['sha256']:
        raise RuntimeError('SOURCE_HASH_MISMATCH')
    target=source/'pdf-text-regions-v1';target.mkdir(exist_ok=True)
    ns={'x':'http://www.w3.org/1999/xhtml'}
    for page in manifest['pages']:
        n=page['pdf_page'];out=target/f'page-{n:04}.json'
        if out.exists():continue
        raw=subprocess.check_output(['pdftotext','-f',str(n),'-l',str(n),'-bbox-layout',str(source/'original.pdf'),'-'],timeout=60)
        tree=ET.fromstring(raw);node=tree.find('.//x:page',ns)
        if node is None:raise RuntimeError('PDF_WORD_POSITIONS_MISSING')
        w=float(node.attrib['width']);h=float(node.attrib['height']);lines=[]
        for line in node.findall('.//x:line',ns):
            words=[]
            for word in line.findall('x:word',ns):
                a=word.attrib;words.append({'text':word.text or '',
                    'bbox':[float(a['xMin'])/w,float(a['yMin'])/h,
                            (float(a['xMax'])-float(a['xMin']))/w,(float(a['yMax'])-float(a['yMin']))/h]})
            a=line.attrib;text=' '.join(word['text'] for word in words)
            lines.append({'text':text,'words':words,'bbox':[float(a['xMin'])/w,float(a['yMin'])/h,
                (float(a['xMax'])-float(a['xMin']))/w,(float(a['yMax'])-float(a['yMin']))/h],
                'corrupt_private_unicode':any(corrupt_character(c) for c in text)})
        out.write_text(json.dumps({'source_sha256':manifest['sha256'],'pdf_page':n,'lines':lines,
            'raw_xml_sha256':hashlib.sha256(raw).hexdigest(),'engine':'poppler_pdftotext_bbox_layout',
            'coordinate_system':'normalized_top_left'},ensure_ascii=False,indent=2))
    print(json.dumps({'native_pdf_position_pages':len(manifest['pages'])}),flush=True)


if __name__=='__main__':extract(sys.argv[1])
