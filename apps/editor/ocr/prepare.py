"""Download public weights at build time; record revisions and every file hash."""
import hashlib
import json
from pathlib import Path
from huggingface_hub import snapshot_download

manifest = {}
for name, revision in {
    'PP-OCRv5_mobile_det': '0d63e78e2b680928f6b1747d76a08db6e645efb7',
    'latin_PP-OCRv5_mobile_rec': 'ab2cd5cc5fa6309be2e5acdfe66eca2c2c127d57',
}.items():
    repo = 'PaddlePaddle/' + name
    directory = Path('/opt/models') / name
    snapshot_download(repo, revision=revision, local_dir=directory)
    manifest[name] = {'revision': revision, 'files': {
        str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.rglob('*') if p.is_file() and '.cache' not in p.parts}}
Path('/opt/models/manifest.json').write_text(json.dumps(manifest, indent=2))
