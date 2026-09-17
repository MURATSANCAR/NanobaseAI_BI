#!/usr/bin/env python3
"""Download pinned public OCR weights during package preparation, never inference."""
import hashlib
import json
from pathlib import Path
import urllib.request

REPO='PaddlePaddle/PaddleOCR-VL-1.6'
REVISION='c5630abae1d940eafe0697512a0325494b02ab42'
root=Path(__file__).resolve().parents[1]/'runtime/ocr-vl'
root.mkdir(parents=True,exist_ok=True)
with urllib.request.urlopen(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true',timeout=60) as response:
    metadata=json.load(response)
assert metadata['sha']==REVISION
manifest={'repository':REPO,'revision':REVISION,'files':{}}
for entry in metadata['siblings']:
    name=entry['rfilename']
    if '/' in name or not name.endswith(('.json','.safetensors','.model','.jinja')):
        continue
    path=root/name
    expected=entry.get('lfs',{}).get('sha256')
    if not path.exists():
        temporary=path.with_suffix(path.suffix+'.part')
        with urllib.request.urlopen(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}',timeout=300) as response, temporary.open('wb') as stream:
            while data:=response.read(1024*1024):stream.write(data)
        temporary.replace(path)
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    assert path.stat().st_size==entry['size'],'MODEL_SIZE_MISMATCH'
    assert not expected or digest==expected,'MODEL_HASH_MISMATCH'
    if not expected:
        # HF small files use Git blob object identity, not a raw SHA-1 digest.
        raw=path.read_bytes()
        assert hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()==entry['blobId'],'MODEL_BLOB_MISMATCH'
    manifest['files'][name]={'bytes':path.stat().st_size,'sha256':digest}
    print(json.dumps({'prepared':name,'bytes':path.stat().st_size}),flush=True)
(root/'manifest.json').write_text(json.dumps(manifest,indent=2))
