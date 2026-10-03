"""Veriden anlam çıkarımı: her hedef tablonun her kolonu için değer profili + sınıf tahmini.
Kullanım: profile.py logo|crm   -> /tmp/ltc_<src>_profile.json
Büyük tablolarda (> FULL satır) en yeni SAMPLE satır okunur; rapora yazılır."""
import json, sys, re, collections, datetime, decimal, time, os
sys.path.insert(0,'/data/nanobaseai/bi/frontend/backend')
from pathlib import Path
from scripts.export_crm_metadata import connect, SECRETS, DATABASE
SRC = sys.argv[1]
FULL, SAMPLE = 200_000, 50_000
if SRC == 'logo':
    cn = connect(Path('/data/nanobaseai/bi/secrets/logo-mssql-connection.json'), 'LOGO_DB')
    inv = json.load(open('/tmp/ltc_logo_inv.json')); gap = json.load(open('/tmp/ltc_logo_gap.json'))
    ld = json.load(open('/data/nanobaseai/bi/frontend/configs/schemas/logo-ldds.json'))['tables']
    known = {k: set(v['columns']) for k,v in ld.items()}
    targets = []  # (key, physical, columns or None=all)
    def best(phys):
        cand = [p for p in phys if (inv[p]['rows'] or 0) > 0] or phys
        rank = lambda p: (('_411_' in p) * 3 + ('_211_' in p) * 2, inv[p]['rows'] or 0)
        return max(cand, key=rank)
    allphys = collections.defaultdict(list)
    PAT = re.compile(r'^(LG|LV)_(\d{3})_(?:(\d{2})_)?(.+)$')
    for n in inv:
        m = PAT.match(n)
        if m: allphys[f"{m.group(1)}:{m.group(4)}"].append(n)
        elif n.startswith('L_'): allphys[f"L:{n[2:]}"].append(n)
        else: allphys[f"X:{n}"].append(n)
    for u in gap['uncovered']:
        ph = [p for p in allphys[u['key']] if p in inv]
        if u['kind']=='custom-V' or (u['rows'] or 0) > 0:
            targets.append((u['key'], best(u['sample'] if u['key'].startswith('X:') else ph), None, u['kind']))
    for k, v in gap['missing_cols'].items():
        if v['rows'] > 0:
            targets.append((k, best(allphys[k]), list(v['cols']), 'missing-cols'))
else:
    cn = connect(SECRETS, DATABASE)
    c = json.load(open('/tmp/ltc_crm_inv.json')); inv = c['tables']; E = c['entities']
    known = {}
    for t,o in inv.items():
        if not (t in E or t.replace('ExtensionBase','Base') in E): known[t] = None
    targets = [(f"X:{t}", t, None, 'no-metadata') for t in known if (inv[t]['rows'] or 0) > 0]
    known = {}
cur = cn.cursor()
def q(s): return '[' + s.replace(']', ']]') + ']'
def classify(name, ty, vals, n, nulls):
    nn = [v for v in vals if v is not None]
    if not nn: return 'boş', {}
    cnt = collections.Counter(nn); d = len(cnt)
    info = {'distinct': d, 'null_ratio': round(nulls / max(n,1), 3)}
    top = cnt.most_common(8)
    info['top'] = [[str(v)[:60], c] for v, c in top]
    if isinstance(nn[0], (datetime.datetime, datetime.date)):
        info['min'], info['max'] = str(min(nn)), str(max(nn)); return 'tarih', info
    if isinstance(nn[0], (bytes, bytearray)): return 'ikili', {}
    s0 = str(nn[0])
    if re.fullmatch(r'[0-9A-Fa-f-]{36}', s0) or ty == 'uniqueidentifier': return 'guid', {'distinct': d}
    if isinstance(nn[0], (int, float, decimal.Decimal)):
        fl = [float(v) for v in nn]; info['min'], info['max'] = min(fl), max(fl)
        if d == 1: return ('hep-sıfır' if fl[0] == 0 else 'sabit'), info
        if set(fl) <= {0.0, 1.0}: return 'bayrak', info
        if all(f == int(f) for f in fl):
            if re.search(r'(REF|ID|NR)$', name, re.I) and d > 50: return 'referans', info
            if all(19000101 <= f <= 21001231 for f in fl if f): return 'tarih-sayı', info
            if d <= 30: return 'kod', info
            return 'sayı', info
        return 'tutar/miktar', info
    if d == 1: return 'sabit-metin', info
    if d <= 30 and d < len(nn) / 5: return 'metin-kod', info
    return 'metin', info
out = {'meta': {'source': SRC, 'full_scan_upto': FULL, 'sample_newest': SAMPLE, 'started': time.ctime()}, 'tables': {}}
for i, (key, phys, cols, kind) in enumerate(targets):
    rec = {'physical': phys, 'kind': kind}
    try:
        if kind == 'custom-V' or (SRC=='logo' and inv[phys]['type']=='V'):
            cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID(?))", phys); d = cur.fetchone()[0] or ''
            rec['definition_head'] = ' '.join(d.split())[:600]
            cur.execute("""SELECT DISTINCT referenced_entity_name FROM sys.sql_expression_dependencies
                           WHERE referencing_id = OBJECT_ID(?) AND referenced_entity_name IS NOT NULL""", phys)
            rec['reads'] = sorted(r[0] for r in cur.fetchall())
            out['tables'][key] = rec; continue
        rows = inv[phys]['rows'] or 0
        allcols = [c[0] for c in inv[phys]['columns']]
        types = {c[0]: c[1] for c in inv[phys]['columns']}
        want = [c for c in (cols or allcols) if types.get(c) not in ('image','varbinary','text','ntext','xml','timestamp','geography')]
        if SRC == 'logo' and cols is None:
            cs = set(allcols); best_k, best_j = None, 0
            for k, kc in known.items():
                j = len(cs & kc) / len(cs | kc)
                if j > best_j: best_k, best_j = k, j
            if best_j >= 0.5: rec['looks_like'] = [best_k, round(best_j, 2)]
        if not want: out['tables'][key] = rec; continue
        order = ' ORDER BY ' + q('LOGICALREF') + ' DESC' if 'LOGICALREF' in allcols else (' ORDER BY ModifiedOn DESC' if 'ModifiedOn' in allcols else '')
        top = f'TOP {SAMPLE} ' if rows > FULL else ''
        rec['scanned'] = 'tamamı' if not top else f'en yeni {SAMPLE}'
        cur.execute(f"SELECT {top}{','.join(q(c) for c in want)} FROM {q(phys)} WITH (NOLOCK){order if top else ''}")
        data = cur.fetchall(); rec['rows'] = rows; rec['read'] = len(data)
        rec['columns'] = {}
        for j, c in enumerate(want):
            vals = [r[j] for r in data]; nulls = sum(v is None for v in vals)
            cls, info = classify(c, types[c], vals, len(vals), nulls)
            rec['columns'][c] = {'type': types[c], 'class': cls, **info}
    except Exception as e:
        rec['error'] = str(e)[:300]
    out['tables'][key] = rec
    if i % 50 == 0:
        json.dump(out, open(f'/tmp/ltc_{SRC}_profile.json', 'w'), ensure_ascii=False, default=str); print(i, len(targets), flush=True)
out['meta']['finished'] = time.ctime()
json.dump(out, open(f'/tmp/ltc_{SRC}_profile.json', 'w'), ensure_ascii=False, default=str)
print('done', len(targets))
