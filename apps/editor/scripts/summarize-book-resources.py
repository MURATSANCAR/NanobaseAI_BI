#!/usr/bin/env python3
"""Summarize actual sampled runtime; health latency is never a business SLO."""
import datetime
import json
from pathlib import Path
import re
import statistics
import sys
import uuid

root = Path(__file__).resolve().parents[1]
job = str(uuid.UUID(sys.argv[1]))
samples = [json.loads(line) for line in (root / 'evidence' / f'resources-{job}.jsonl').read_text().splitlines() if line.strip()]
if not samples:
    raise SystemExit('No real resource samples')


def gib(value):
    number, unit = re.fullmatch(r'([\d.]+)(\w+)', value.strip()).groups()
    factors = {'B': 1, 'kB': 1000, 'MB': 1000**2, 'GB': 1000**3,
               'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3}
    return float(number) * factors[unit] / 1024**3


services = {}
for sample in samples:
    for item in sample.get('containers', []):
        name = item['Name']; data = services.setdefault(name, {'cpu': [], 'memory': []})
        data['cpu'].append(float(item['CPUPerc'].rstrip('%')) / 100)
        data['memory'].append(gib(item['MemUsage'].split('/')[0]))
health = {}
for sample in samples:
    for item in sample.get('health_only_not_business_slo', []):
        data = health.setdefault(str(item['port']), {'samples': 0, 'non_200': 0, 'seconds': []})
        data['samples'] += 1
        data['non_200'] += item.get('status') != 200
        if isinstance(item.get('seconds'), (int, float)): data['seconds'].append(item['seconds'])
report = {
    'job_id': job, 'first_sample': samples[0]['observed_at'], 'last_sample': samples[-1]['observed_at'],
    'observation_seconds': (datetime.datetime.fromisoformat(samples[-1]['observed_at']) - datetime.datetime.fromisoformat(samples[0]['observed_at'])).total_seconds(),
    'samples': len(samples), 'latest_job_status': samples[-1]['status'],
    'not_total_job_wall_time': True,
    'containers': {name: {'sampled_mean_logical_cpu': round(statistics.mean(d['cpu']), 3),
                           'sampled_peak_logical_cpu': round(max(d['cpu']), 3),
                           'sampled_peak_memory_gib': round(max(d['memory']), 3)} for name, d in services.items()},
    'health_only_not_business_slo': {port: {'samples': d['samples'], 'non_200': d['non_200'],
           'max_seconds': max(d['seconds']) if d['seconds'] else None} for port, d in health.items()},
    'semantic_acceptance': False,
}
(root / 'evidence' / f'resource-summary-{job}.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
