#!/usr/bin/env python3
"""Read Docker IPAM once and emit one network plan for proxy and restore.

No network is created, removed or reserved. The restore qualifier must recheck
the selected pair immediately before creating its target networks.
"""
import argparse
import hashlib
import ipaddress
import json
import subprocess


def network_plan(pool, prefix):
    pool = ipaddress.ip_network(pool)
    if pool.version != 4 or not pool.is_private or not pool.prefixlen <= prefix <= 29:
        raise ValueError('INVALID_QUALIFICATION_NETWORK_POOL')
    ids = subprocess.check_output(['docker', 'network', 'ls', '-q'], text=True).split()
    networks = json.loads(subprocess.check_output(['docker', 'network', 'inspect', *ids], text=True)) if ids else []
    inventory = sorted(({'name': n['Name'], 'subnet': c['Subnet']}
                        for n in networks for c in (n.get('IPAM', {}).get('Config') or [])
                        if c.get('Subnet')), key=lambda item: (item['name'], item['subnet']))
    used = [ipaddress.ip_network(item['subnet']) for item in inventory]
    free = []
    for subnet in pool.subnets(new_prefix=prefix):
        if not any(other.version == 4 and subnet.overlaps(other) for other in used):
            free.append(str(subnet))
            if len(free) == 2:
                return {'private_subnet': free[0], 'ingress_subnet': free[1],
                        'docker_ipam': inventory,
                        'ipam_sha256': hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest(),
                        'reserved': False}
    raise RuntimeError('NO_FREE_QUALIFICATION_SUBNET_PAIR')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool', required=True, help='Explicit private IPv4 allocation pool')
    parser.add_argument('--prefix', type=int, default=24)
    args = parser.parse_args()
    print(json.dumps(network_plan(args.pool, args.prefix), sort_keys=True))
