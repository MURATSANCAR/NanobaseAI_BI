#!/usr/bin/env python3
"""Verify every packaged byte before Docker image import. Run from the bundle root."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(sys.argv[1]).resolve()
manifest = json.loads((root/'release-manifest.json').read_text())
for name, expected in manifest['files'].items():
    path = (root/name).resolve()
    if not path.is_relative_to(root):
        raise SystemExit('Invalid bundle member')
    with path.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != expected:
            raise SystemExit('Bundle checksum mismatch: '+name)
if manifest.get('deployment_mode') == 'external_models':
    contract_path = root/'editor/deploy/external-models.json'
    if ('editor/deploy/external-models.json' not in manifest['files']
            or json.loads(contract_path.read_text()) != manifest.get('external_dependencies')):
        raise SystemExit('External dependency contract missing or differs from package manifest')
    print('Application-only offline bundle: customer-managed Qwen/OCR services and GPU weights are NOT included. '
          'Configure endpoint variables before installation; GPU/inference acceptance remains pending.')
subprocess.run(['docker','load','-i',str(root/'images.tar')],check=True)
for image in manifest['images']:
    for tag in image['tags'] or []:
        actual = subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',tag],text=True).strip()
        if actual != image['id']:
            raise SystemExit('Image mismatch: '+tag)
print('Bundle hashes and Docker image identities verified.')
