#!/usr/bin/env python3
"""Host-side preflight. Run on the target Linux server, not a developer laptop."""
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
os.chdir(root)
settings = dict(line.split('=', 1) for line in (root / '.env').read_text().splitlines() if line and not line.startswith('#'))
errors = []
if platform.system() != 'Linux' or platform.machine() != 'x86_64':
    errors.append('This release is qualified for Linux x86_64 only.')
subprocess.run(['docker', 'info', '--format', '{{.ServerVersion}}'], check=True)
subprocess.run(['docker', 'compose', 'config', '--quiet'], check=True)
usage = shutil.disk_usage(root)
if usage.free < 20 * 1024**3:
    errors.append('At least 20 GiB free disk required for foundation images and initial artifacts; model space is additional.')
mem = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
if int(mem['MemAvailable'].split()[0]) < 8 * 1024**2:
    errors.append('At least 8 GiB available RAM required for the bounded document tooling.')
running = subprocess.check_output(['docker', 'compose', 'ps', '-q'], text=True).strip()
if not running:
    for port in (int(settings['EDITOR_PORT']), int(settings['EDITOR_METRICS_PORT'])):
        with socket.socket() as sock:
            try:
                sock.bind((settings.get('EDITOR_BIND', '127.0.0.1'), port))
            except OSError:
                errors.append(f'Port {port} is already used.')
print(json.dumps({'host': platform.node(), 'architecture': platform.machine(), 'cpu_logical': os.cpu_count(),
                  'load': os.getloadavg(), 'disk_free_bytes': usage.free,
                  'memory_available_kib': int(mem['MemAvailable'].split()[0]), 'errors': errors}, indent=2))
sys.exit(bool(errors))
