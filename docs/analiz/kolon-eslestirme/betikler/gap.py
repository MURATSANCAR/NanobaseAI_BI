import json, re, collections
FIRMS = {'015','016','105','115','171','181','191','201','211','411'}
inv = json.load(open('/tmp/ltc_logo_inv.json'))
ld = json.load(open('/data/nanobaseai/bi/frontend/configs/schemas/logo-ldds.json'))['tables']
ldcols = {k:set(v['columns']) for k,v in ld.items()}
PAT = re.compile(r'^(LG|LV)_(\d{3})_(?:(\d{2})_)?(.+)$')
shapes = collections.defaultdict(lambda: {'phys':[], 'rows':0, 'cols':{}, 'kind':None})
other = {}
for name, o in inv.items():
    m = PAT.match(name)
    if m:
        if m.group(2) not in FIRMS: continue
        key = f"{m.group(1)}:{m.group(4)}"
        s = shapes[key]; s['kind'] = 'period' if m.group(3) else 'firm'
    elif name.startswith('L_'):
        key = f"L:{name[2:]}"; s = shapes[key]; s['kind']='system'
    else:
        # custom table/view: drop if it carries a 3-digit number of a non-TİMAŞ firm only
        nums = re.findall(r'(?<!\d)(\d{3})(?!\d)', name)
        key = f"X:{name}"; s = shapes[key]; s['kind'] = 'custom-'+o['type']
    s['phys'].append(name); s['rows'] += o['rows'] or 0
    for c, ty, ln, cid in o['columns']:
        s['cols'].setdefault(c, [ty, ln])
res = {'covered_tables':[], 'uncovered':[], 'missing_cols':{}}
for key, s in shapes.items():
    pre, base = key.split(':',1)
    if pre in ('LG','LV','L') and base in ld:
        res['covered_tables'].append(key)
        miss = sorted(set(s['cols']) - ldcols[base])
        if miss: res['missing_cols'][key] = {'rows': s['rows'], 'cols': {c: s['cols'][c] for c in miss}}
    else:
        res['uncovered'].append({'key': key, 'kind': s['kind'], 'rows': s['rows'], 'n_phys': len(s['phys']), 'sample': s['phys'][:3], 'ncols': len(s['cols']), 'cols': s['cols']})
json.dump(res, open('/tmp/ltc_logo_gap.json','w'), ensure_ascii=False)
k = collections.Counter(u['kind'] for u in res['uncovered'])
print('shapes', len(shapes), 'covered', len(res['covered_tables']), 'uncovered', len(res['uncovered']), k)
print('missing cols in covered:', sum(len(v['cols']) for v in res['missing_cols'].values()), 'in', len(res['missing_cols']), 'tables')
print('covered live cols:', sum(len(shapes[k]['cols']) for k in res['covered_tables']))
for u in sorted(res['uncovered'], key=lambda u:-u['rows'])[:60]:
    print(u['kind'], u['key'], u['rows'], u['n_phys'], u['ncols'])
