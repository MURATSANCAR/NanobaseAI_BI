import json, os, sys, collections, re
sys.path.insert(0,'/data/nanobaseai/bi/frontend/backend')
os.environ.setdefault('SEMANTIC_FIRMS','015,016,105,115,171,181,191,201,211,411')
from semantic_layer.firm_scope import foreign_tables
g = json.load(open('/tmp/ltc_logo_gap.json'))
inv = json.load(open('/tmp/ltc_logo_inv.json'))
names = [k for k in inv]
foreign = foreign_tables(names)
keep = []
for u in g['uncovered']:
    if u['kind'].startswith('custom'):
        if u['sample'][0] in foreign: continue
    keep.append(u)
g['uncovered'] = keep
json.dump(g, open('/tmp/ltc_logo_gap.json','w'), ensure_ascii=False)
k = collections.Counter(u['kind'] for u in keep)
print('uncovered after firm filter', len(keep), k, 'with rows>0:', sum(1 for u in keep if u['rows']>0))
# custom name prefixes
pref = collections.Counter(re.split(r'[_ ]', u['key'][2:])[0].upper() for u in keep if u['kind'].startswith('custom'))
print(pref.most_common(40))
# CRM gap
c = json.load(open('/tmp/ltc_crm_inv.json'))
T, E, A = c['tables'], c['entities'], c['attributes']
lab = lambda d: any(k.endswith(':1055') for k in d['labels'])
labeled_tbl = set(E)
tbl_nometa = [t for t in T if not (t in E or t.replace('ExtensionBase','Base') in E)]
print('crm tables', len(T), 'entities w/ base', len(E), 'tables w/o metadata', len(tbl_nometa), 'rows>0:', sum(1 for t in tbl_nometa if (T[t]['rows'] or 0)>0))
ent_nolab = [e for e,d in E.items() if not any(k.startswith('LocalizedName:1055') for k in d['labels'])]
print('entities without TR name', len(ent_nolab), 'custom:', sum(E[e]['custom'] for e in ent_nolab))
tot=nolab=nolab_custom=0; col_nometa=0
for t,o in T.items():
    ent = t if t in E else t.replace('ExtensionBase','Base')
    if ent not in A: continue
    for col,*_ in o['columns']:
        tot+=1
        a = A[ent].get(col)
        if a is None: col_nometa+=1
        elif not any(k.startswith('DisplayName:1055') for k in a['labels']):
            nolab+=1; nolab_custom+=a['custom']
print('crm cols in entity tables', tot, 'no metadata', col_nometa, 'no TR label', nolab, 'custom among', nolab_custom)
print(sorted(((T[t]['rows'] or 0),t) for t in tbl_nometa)[-25:])
