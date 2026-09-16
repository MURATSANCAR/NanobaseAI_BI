#!/usr/bin/env python3
"""Read-only host manifest. Does not read container environments or credentials."""
import datetime
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
def command(*args):
    return subprocess.check_output(args,text=True).strip()

result = {'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'host':platform.node(),'system':platform.platform(),'cpu_logical':os.cpu_count(),
          'load':os.getloadavg(),'disk':dict(zip(('total','used','free'),shutil.disk_usage(root))),
          'memory':dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines()
                        if line.startswith(('MemTotal:','MemAvailable:','SwapTotal:'))),
          'docker':command('docker','version','--format','{{.Server.Version}}'),
          'compose':command('docker','compose','version','--short'),
          'containers':[json.loads(line) for line in command('docker','ps','--format','json').splitlines()],
          'gpu':command('sh','-c','lspci | grep -Ei "vga|3d|nvidia" || true')}
print(json.dumps(result,indent=2))
