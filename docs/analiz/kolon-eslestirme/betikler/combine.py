import json, re, fnmatch, collections, sys
W = json.load(open('/tmp/ltc/logo_web_findings.json'))
for _t in W['tables'].values():
    for _c in (_t.get('columns') or {}).values():
        if 'tabloya aktarıldı' in (_c.get('source_note') or ''): _c['confidence'] = 'low'; _c['source_note'] += ' (başka tablodan aktarım — doğrulanmadı)'
CW = json.load(open('/tmp/ltc/crm_web_findings.json'))
INV = json.load(open('/tmp/ltc_logo_inv.json'))
LD = json.load(open('/data/nanobaseai/bi/frontend/configs/schemas/logo-ldds.json'))['tables']
LP = json.load(open('/tmp/ltc_logo_profile.json'))['tables']; CP = json.load(open('/tmp/ltc_crm_profile.json'))['tables']
G = json.load(open('/tmp/ltc_logo_gap.json')); CI = json.load(open('/tmp/ltc_crm_inv.json'))
EMPTY = {'boş','hep-sıfır','sabit','sabit-metin'}
# Veriden çözülen kodlar (probe2/probe3: FICHEOBJECT içindeki UBL XML ile eşleştirme, LG_411)
DECODED = {
 ('EINVOICEDET','PROFILEID'): {'0':'İhracat (IHRACAT) — 2 örnek','1':'Temel fatura (TEMELFATURA)','2':'Ticari fatura (TICARIFATURA)'},
 ('EINVOICEDET','EINVOICETYP'): {'0':'Satış (SATIS; iade faturasında IADE)','2':'İstisna (ISTISNA)','4':'Tevkifat (TEVKIFAT)'},
 ('EARCHIVEDET','SENDMOD'): {'0':'Belirtilmemiş (XML yok)','1':'Kağıt (KAGIT)','2':'Elektronik (ELEKTRONIK)'},
 ('EBOOKDETAILDOC','DOCUMENTTYPE'): {'0':'Belge türü seçilmemiş — cari/banka/kasa kaynaklı mahsup fişleri (1.736)','2':'Fatura','6':'Diğer (EXPLAIN dolu: Kredi Kartı Fişi, Dekont, Sarf Fişi…)','99':'Belgesiz (UNDOCUMENTED)'},
}
def logo_base(key):
    p, b = key.split(':', 1)
    return ('L_' + b) if p == 'L' else b
def web_table(base):
    if base in W['copies']: return {'copy_of': W['copies'][base]['original']}, W['tables'].get(W['copies'][base]['original'])
    return None, W['tables'].get(base) or W['tables'].get(base.replace('L_', '', 1))
def status_of(web, prof):
    if web and web.get('confidence') in ('high','medium') and str(web.get('url','')).startswith('http'): return 'web-kaynaklı'
    if prof and prof.get('class') in EMPTY: return 'kullanılmıyor'
    if web: return 'web-ad-benzerliği'
    if prof: return 'yalnız-veri'
    return 'bilinmiyor'
def slim(p):
    if not p: return None
    d = {'sınıf': p['class']}
    if p.get('top'): d['değerler'] = p['top'][:5]
    for k in ('min','max','distinct','null_ratio'):
        if k in p: d[k] = p[k]
    return d
logo = {'tablolar': {}, 'eksik_kolonlar': {}}
st = collections.Counter(); tst = collections.Counter(); cst = collections.Counter()
for key, rec in LP.items():
    base = logo_base(key)
    copy, wt = web_table(base)
    cols = {}
    for c, p in (rec.get('columns') or {}).items():
        wc = (wt or {}).get('columns', {}).get(c) or W['columns_generic'].get(c)
        tb = (copy or {}).get('copy_of') or base
        d = {'durum': status_of(wc, p), 'veri': slim(p)}
        if wc: d.update({'açıklama': wc.get('description_tr'), 'kaynak': wc.get('url'), 'güven': wc.get('confidence')})
        if wc and wc.get('values'): d['kodlar_web'] = wc['values']
        if (tb, c) in DECODED: d['kodlar_veriden'] = DECODED[(tb, c)]; d['durum'] = 'web+veri'
        cols[c] = d; st[d['durum']] += 1
    entry = {'fiziksel': rec.get('physical'), 'tür': rec['kind'], 'satır': rec.get('rows'), 'okunan': rec.get('scanned')}
    if copy: entry['kopyası'] = copy['copy_of']
    if key.startswith('X:'):
        cs = {c[0] for c in INV.get(rec.get('physical'), {}).get('columns', [])}
        best = max(((k, len(cs & set(v['columns'])) / max(len(cs), 1)) for k, v in LD.items() if len(v['columns']) >= 10), key=lambda x: x[1], default=(None, 0))
        if len(cs) >= 8 and best[1] >= 0.9: rec['looks_like'] = [best[0], round(best[1], 2)]; rec['contain'] = True
    if key.startswith('X:') and not rec.get('looks_like'):
        m = re.search(r'(\d{3})_(?:\d{2}_)?([A-Z]+)$', key)
        if m and m.group(2) in LD: rec['name_of'] = [m.group(2), m.group(1)]
    ll = rec.get('looks_like')
    if ll and len(LD.get(ll[0], {}).get('columns', {})) >= 10: entry['kolonları_benziyor'] = ll
    else: rec.pop('looks_like', None)
    fam = re.match(r'^L:(TABLELAYS|RPLAYS|RPFILTS)_?(\d+)$', key)
    if fam and not wt:
        wt = W['tables'].get('L_' + fam.group(1)) or {'description_tr': {'TABLELAYS':'Kullanıcı başına liste/tablo görünüm düzeni','RPLAYS':'Kullanıcı başına rapor tasarım düzeni','RPFILTS':'Kullanıcı başına kayıtlı rapor filtreleri'}[fam.group(1)] + f' (sonek {fam.group(2)} = kullanıcı/firma numarası)', 'url': 'kaynak: ad benzerliği', 'confidence': 'low'}
    if rec.get('reads') is not None:
        entry['okuduğu_tablolar'] = rec['reads']; entry['kolon_adları'] = [c[0] for c in INV.get(rec['physical'], {}).get('columns', [])]
        entry['not'] = 'tanım okunamadı: zekiai hesabında VIEW DEFINITION yetkisi yok'
    if wt and wt.get('description_tr'): entry.update({'açıklama': wt['description_tr'], 'kaynak': wt.get('url'), 'güven': wt.get('confidence')})
    if rec['kind'] == 'missing-cols':
        logo['eksik_kolonlar'][key] = {'fiziksel': rec.get('physical'), 'satır': rec.get('rows'), 'kolonlar': cols}
    else:
        if cols: entry['kolonlar'] = cols
        if copy: s = 'kopya'
        elif entry.get('açıklama') and str(entry.get('kaynak','')).startswith('http'): s = 'web-kaynaklı'
        elif entry.get('açıklama'): s = 'web-ad-benzerliği'
        elif rec.get('name_of'): entry['adından'] = f"firma {rec['name_of'][1]} {rec['name_of'][0]} tablosunun özel kopyası/özeti (ad + kolonlar)"; s = 'ad-kalıbından'
        elif entry.get('kolonları_benziyor'): s = 'kopya-benzeri' if not rec.get('contain') else 'alt-küme-kopya'
        elif 'okuduğu_tablolar' in entry: s = 'view-yalnız-ad'
        elif cols and all(v['durum']=='kullanılmıyor' for v in cols.values()): s = 'kullanılmıyor'
        elif cols: s = 'yalnız-veri'
        else: s = 'bilinmiyor'
        entry['durum'] = s; tst[(rec['kind'].split('-')[0], s)] += 1
        logo['tablolar'][key] = entry
# boş (0 satır) tablolar: profile girmedi
empty_tables = [u['key'] for u in G['uncovered'] if not u['rows'] and u['kind'] != 'custom-V']
logo['bos_tablolar'] = empty_tables
logo['ozet'] = {'kolon_durum': dict(st), 'tablo_durum': {f'{a}/{b}': n for (a,b),n in tst.items()}, 'bos_tablo': len(empty_tables)}
json.dump(logo, open('/tmp/ltc/out_logo.json','w'), ensure_ascii=False, indent=1, default=str)
# CRM
T, E, A = CI['tables'], CI['entities'], CI['attributes']
LOGICAL = {d['logical'].lower(): d['custom'] for d in CI['entities'].values()}
PAT = {p['pattern']: p for p in CW['column_patterns']}
def crm_col(name):
    if name in CW['columns']: return CW['columns'][name]
    if name.lower().endswith('id') and name[:-2].lower() in LOGICAL:
        p = PAT['<özel_varlık>id (N:N FK)'] if LOGICAL[name[:-2].lower()] else PAT['<sistem_varlık>id (N:N FK)']
        return {**p, 'description_tr': f"{name[:-2]} kaydının kimliği (ara tablo yabancı anahtarı). " + (p.get('description_tr') or '')}
    for p in CW['column_patterns']:
        if name in p.get('examples', []) or fnmatch.fnmatchcase(name, p['pattern']): return p
crm = {'etiketsiz_kolonlar': {}, 'metadata_disi_tablolar': {}, 'adsiz_entityler': {}}
ccs = collections.Counter()
for t, o in T.items():
    ent = t if t in E else t.replace('ExtensionBase', 'Base')
    if ent not in A: continue
    for col, *_ in o['columns']:
        a = A[ent].get(col)
        if a and not any(k.startswith('DisplayName:1055') for k in a['labels']):
            w = crm_col(col)
            d = {'durum': 'web-kaynaklı' if w and str(w.get('url','')).startswith('http') else ('web-ad-benzerliği' if w else 'bilinmiyor')}
            if w: d.update({'açıklama': w.get('description_tr'), 'kaynak': w.get('url'), 'güven': w.get('confidence')})
            crm['etiketsiz_kolonlar'].setdefault(t, {})[col] = d; ccs[d['durum']] += 1
tcs = collections.Counter()
for t, o in T.items():
    if t in E or t.replace('ExtensionBase','Base') in E: continue
    w = CW['tables'].get(t); p = CP.get(f'X:{t}')
    d = {'satır': o['rows'], 'kolon': len(o['columns'])}
    if w: d.update({'açıklama': w.get('description_tr'), 'kaynak': w.get('url'), 'güven': w.get('confidence'), 'tür': w.get('kind')})
    if p and p.get('columns'): d['kolonlar'] = {c: slim(v) for c, v in p['columns'].items()}; d['okunan'] = p.get('scanned')
    elif t == 'tblPaymentLog': d['not'] = 'ödeme günlüğü (yetki/kart verisi) — bilinçli okunmadı'
    d['durum'] = ('web-kaynaklı' if w and str(w.get('url','')).startswith('http') else 'web-ad-benzerliği+veri' if w and d.get('kolonlar') else 'web-ad-benzerliği' if w else 'yalnız-veri' if d.get('kolonlar') else 'bilinmiyor')
    tcs[d['durum']] += 1; crm['metadata_disi_tablolar'][t] = d
for e, d in E.items():
    if not any(k.startswith('LocalizedName:1055') for k in d['labels']):
        w = CW['entities'].get(d['logical'])
        crm['adsiz_entityler'][e] = {'mantıksal': d['logical'], 'özel': d['custom'], **({'açıklama': w.get('description_tr'), 'kaynak': w.get('url'), 'güven': w.get('confidence')} if w else {})}
crm['ozet'] = {'kolon_durum': dict(ccs), 'tablo_durum': dict(tcs), 'adsiz_entity': len(crm['adsiz_entityler']), 'adsiz_entity_aciklanan': sum('açıklama' in v for v in crm['adsiz_entityler'].values())}
json.dump(crm, open('/tmp/ltc/out_crm.json','w'), ensure_ascii=False, indent=1, default=str)
print(json.dumps(logo['ozet'], ensure_ascii=False)); print(json.dumps(crm['ozet'], ensure_ascii=False))
