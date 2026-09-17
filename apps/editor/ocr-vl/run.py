"""Offline failed-region OCR only. No book text or expected answer enters the prompt."""
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor


def valid_box(box):
    return (isinstance(box,list) and len(box)==4
        and all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in box)
        and 0<=box[0]<1 and 0<=box[1]<1 and box[2]>0 and box[3]>0
        and box[0]+box[2]<=1.000001 and box[1]+box[3]<=1.000001)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


torch.set_num_threads(4)
torch.set_num_interop_threads(1)
torch.manual_seed(17)
requests=json.load(sys.stdin)
model_dir=Path('/opt/ocr-vl');manifest=json.loads((model_dir/'manifest.json').read_text())
for name,entry in manifest['files'].items():
    with (model_dir/name).open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=entry['sha256']:
            raise RuntimeError('MODEL_HASH_MISMATCH')
started=time.monotonic()
model=AutoModelForImageTextToText.from_pretrained(model_dir,torch_dtype=torch.float32,
    attn_implementation='eager',local_files_only=True,trust_remote_code=False).eval()
processor=AutoProcessor.from_pretrained(model_dir,local_files_only=True,trust_remote_code=False)
image_config=json.loads((model_dir/'preprocessor_config.json').read_text())
print(json.dumps({'model_ready_seconds':round(time.monotonic()-started,3)}),flush=True)
for request in requests:
    source=request['source_sha256'];generation=str(uuid.UUID(request['generation_id']))
    if len(source)!=64 or any(c not in '0123456789abcdef' for c in source):
        raise ValueError('INVALID_SOURCE_HASH')
    page=request['pdf_page']
    if type(page) is not int or not 1<=page<=100 or len(request['spans'])>128:
        raise ValueError('PAGE_OR_REGION_LIMIT')
    root=Path('/data/artifacts')/source
    raw=(root/'ocr-regions-v2'/f'page-{page:04}.png').read_bytes()
    if digest(raw)!=request['render_sha256']:raise RuntimeError('RENDER_MISMATCH')
    image=Image.open(io.BytesIO(raw)).convert('RGB')
    if image.width*image.height>20_000_000:raise ValueError('PIXEL_LIMIT')
    directory=root/'ocr-vl-regions-v2'/generation;directory.mkdir(parents=True,exist_ok=True)
    for row in request['spans']:
        span_id=str(uuid.UUID(row['id']));d=row['data'];box=d['bbox']
        if not valid_box(box) or d['render_sha256']!=request['render_sha256'] or d['pdf_page']!=page:
            raise RuntimeError('SPAN_SCOPE_MISMATCH')
        target=directory/(span_id+'.json')
        if target.exists():
            previous=json.loads(target.read_text())
            if previous['render_sha256']!=request['render_sha256'] or previous['bbox']!=box or previous['code_sha256']!=digest(Path(__file__).read_bytes()):
                raise RuntimeError('IMMUTABLE_OCR_VL_CHANGED')
            print(json.dumps({'page':page,'span_id':span_id,'reused':True}),flush=True)
            continue
        x,y,w,h=box
        bounds=[math.floor(x*image.width),math.floor(y*image.height),min(image.width,math.ceil((x+w)*image.width)),min(image.height,math.ceil((y+h)*image.height))]
        crop=image.crop(tuple(bounds));stream=io.BytesIO();crop.save(stream,format='PNG')
        # Fixed OCR instruction only, no caption/context/answer from any reader.
        messages=[{'role':'user','content':[{'type':'image','image':crop},{'type':'text','text':'OCR:'}]}]
        inputs=processor.apply_chat_template(messages,add_generation_prompt=True,tokenize=True,
            return_dict=True,return_tensors='pt',processor_kwargs={'images_kwargs':{'size':{
                'shortest_edge':image_config['min_pixels'],'longest_edge':image_config['max_pixels']}}})
        begin=time.monotonic()
        with torch.inference_mode():output=model.generate(**inputs,max_new_tokens=192,do_sample=False,
            use_cache=True,max_time=120)
        tokens=output[0][inputs['input_ids'].shape[-1]:]
        eos=model.generation_config.eos_token_id
        eos=set(eos if isinstance(eos,list) else [eos])
        complete=bool(len(tokens)) and int(tokens[-1]) in eos
        text=processor.decode(tokens,skip_special_tokens=True)
        report={'generation_id':generation,'source_span_id':span_id,'source_sha256':source,
            'pdf_page':page,'render_sha256':request['render_sha256'],'bbox':box,'crop_pixels':bounds,
            'crop_sha256':digest(stream.getvalue()),'text':text,'complete':complete,
            'status':'OCR_VL_CANDIDATE' if complete else 'MODEL_OUTPUT_TRUNCATED',
            'model_manifest':manifest,'code_sha256':digest(Path(__file__).read_bytes()),
            'seconds':round(time.monotonic()-begin,3),'tokens':len(tokens),
            'prompt':'OCR:','dtype':'float32','device':'cpu','max_new_tokens':192,
            'use_cache':True,'max_time_seconds':120,'input_tokens':inputs['input_ids'].shape[-1],
            'eligible_for_synthesis':False,'expected_answer_supplied':False}
        temporary=target.with_suffix('.'+str(uuid.uuid4())+'.tmp')
        try:
            temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2));os.link(temporary,target)
        finally:temporary.unlink(missing_ok=True)
        print(json.dumps({'page':page,'span_id':span_id,'complete':complete,'seconds':report['seconds']}),flush=True)
