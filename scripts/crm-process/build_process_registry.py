"""CRM süreç kayıtlarını (sipariş, bekleyen ürün, satış hedefi, etkinlik, ziyaret yeri, kitap sınıflaması) soru motorunun
CRM sözlüğüne eklenecek biçimde üretir: backend/semantic_bridge/finance_query/relational_process.py.

Kaynak CRM'in kendisidir: alan adları ve kod etiketleri MetadataSchema'dan (Türkçe, LanguageId 1055), ilişkiler
MetadataSchema.Relationship'teki fiziksel FK → tekil PK kayıtlarından. Veriyle ölçülür: aktif satırda alan doluluğu
(≥ %5 olan alınır), PK tekilliği, FK'nın hedefte bulunma oranı. Kişisel veri adı taşıyan alan (telefon, adres, e-posta,
kimlik) alınmaz. Sunucuda koşar (CRM .28 okunur, yazılmaz):

    python build_process_registry.py /tmp/ltc/crm_batch_meta.json /tmp/ltc/crm_batch_prof.json relational_process.py
"""
import json, re, sys, unicodedata, pprint
sys.path.insert(0, '/data/nanobaseai/bi/frontend/backend')
from scripts.export_crm_metadata import connect, SECRETS, DATABASE
from semantic_layer.profiler.sensitivity import name_is_sensitive

META, PROF, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
M, P = json.load(open(META)), json.load(open(PROF))
cur = connect(SECRETS, DATABASE).cursor()

KEYS = {'new_satishedefleri': 'sales_target', 'new_etkinlik': 'crm_activity', 'new_ziyaretyerleri': 'visit_place',
        'new_bekleyenurun': 'pending_item', 'new_siparis': 'crm_order', 'new_siparissatiri': 'crm_order_line',
        'new_new_kitap_new_yas': 'book_age_link', 'new_new_kitap_new_sinifkategorisi': 'book_class_link',
        'new_new_urunkategorisi_new_kitap': 'book_category_link', 'new_new_anahtarkelime_new_kitap': 'book_keyword_link',
        'new_yas': 'age_group', 'new_sinifkategorisi': 'class_category', 'new_urunkategorisi': 'product_category',
        'new_anahtarkelime': 'keyword', 'new_etkinliktipi': 'activity_type', 'new_iller': 'province', 'new_ilce': 'district',
        'systemuser': 'crm_user', 'product': 'crm_product', 'new_kampanya': 'campaign', 'new_depo': 'warehouse',
        'new_gelissekli': 'order_channel', 'new_kargofirmasi': 'cargo_company', 'new_odemevadesi': 'payment_term'}
EXISTING = {'new_kitap': ('book', 'book_id'), 'account': ('account', 'account_id'), 'contact': ('contact', 'person_id')}
NAME_COL = {'systemuser': 'FullName', 'product': 'Name'}
EXTRA = {'product': ['ProductNumber']}
SKIP = {'createdby', 'modifiedby', 'modifiedon', 'organizationid', 'ownerid', 'owningbusinessunit', 'owninguser', 'owningteam',
        'versionnumber', 'importsequencenumber', 'overriddencreatedon', 'timezoneruleversionnumber', 'utcconversiontimezonecode',
        'transactioncurrencyid', 'exchangerate', 'processid', 'stageid', 'traversedpath'}
NOISE = re.compile(r'_base$|entegrasyon|aktarildi|aktarıldı|etiketbasildi|pusula|idtext|^new_id$|hedefid|etkinliklerid|itemno', re.I)
NOTES = {
    'sales_target': ['Grain: one row per book × year × region × sales rep (new_BMT); 2026: 4.020 books × 17 reps. Totals across reps are additive (measured 2026-10-04).',
                     'Year is a CRM option set: codes are not years; filter by its label. Labels include 2000 and 1991 used in data.',
                     'Monthly target columns ocak..aralik sum to toplam_hedef on every row (325.554/325.554).'],
    'crm_order': ['CRM order is the sales PROCESS record (entry, approval, warehouse, completion). Its amounts are order-time amounts, NOT revenue: invoiced sales and collections are Logo.',
                  'Header totals equal the sum of active non-cancelled lines (Sep 2026: 5.945/5.945).'],
    'crm_order_line': ['Order line of a CRM order; cancelled lines have status İptal Edildi. Quantities are ordered/shipped/remaining at CRM process level, not invoiced quantity.'],
    'pending_item': ['Pending (backorder) item: status Bekleyen (still waiting), Siparişe Eklendi (later added to an order) or İptal Edildi. Quantity is in adet.'],
    'crm_activity': ['Sales/visit activity record: visits, school programs, fairs, phone calls. Activity type names are free-form CRM records (e.g. Ziyaret, Okul ziyaret, Fuar Programı).',
                     'Business date is gerceklesen_ziyaret_tarihi (84% filled); status Tamamlandı/İptal Edildi/Planlandı.'],
    'visit_place': ['Directory of schools and institutions to visit (not the visits themselves). Count text fields (öğrenci/öğretmen sayısı) are free text, not additive.'],
}

def fold(s):
    s = unicodedata.normalize('NFKD', (s or '').replace('ı', 'i').replace('İ', 'i'))
    s = re.sub(r'[^a-z0-9]+', '_', ''.join(ch for ch in s if not unicodedata.combining(ch)).lower()).strip('_')
    return s if s and s[0].isalpha() else 'f_' + s

def ftype(t):
    t = (t or '').lower()
    if t in ('nvarchar', 'nchar', 'varchar', 'char'): return 'text', 'nvarchar'
    if t in ('int', 'bigint', 'smallint', 'tinyint'): return 'number', t
    if t in ('decimal', 'money', 'float'): return 'number', t
    if t in ('picklist', 'state', 'status'): return 'number', 'int'
    if t == 'bit': return 'bool', 'bit'
    if t == 'datetime': return 'date', 'datetime'
    if t in ('lookup', 'primarykey', 'uniqueidentifier', 'owner', 'customer'): return 'identity', 'uniqueidentifier'
    return None, None

def summable(key, label, t, m):
    l = fold(label)
    if m.get('options') or m['type'] in ('state', 'status', 'picklist'):
        return False                                         # kod listesi toplanmaz
    if t != 'number' or any(w in l for w in ('oran', 'birim', 'fiyat', 'stok', 'limit', 'risk', 'vade', 'yil', 'sayisi')):
        return False
    if key == 'sales_target': return True
    return key in ('crm_order', 'crm_order_line', 'pending_item') and any(w in l for w in ('tutar', 'adet', 'adedi'))

def one(sql, *a):
    cur.execute(sql, *a); return cur.fetchone()

ent, rel, checks = {}, {}, []
target_keys = {lg: k for lg, k in KEYS.items()} | {lg: v[0] for lg, v in EXISTING.items()}
for lg, key in KEYS.items():
    d = M.get(lg)
    if not d: continue
    base, cols, prof = d['base'], d['columns'], P.get(lg)
    phys = {k: v for k, v in d['physical'].items() if v[0] == base}
    pk = next(c for c, m in cols.items() if m['type'] == 'primarykey')
    state = next((c for c in cols if c.lower() == 'statecode' and c.lower() in phys), None)
    fields, used = {}, set()
    def add(fid, col, m, extra=None):
        t, st = ftype(m['type'])
        if t is None: return
        fid = fid[:60]
        while fid in used: fid += '_2'
        used.add(fid)
        spec = {'column': col, 'type': t, 'sql_type': st, 'nullable': not m.get('pk'), 'sum_allowed': summable(key, m['label'] or '', t, m),
                'label_tr': m['label'] or col}
        if m.get('options'): spec['values'] = {k: v for k, v in sorted(m['options'].items(), key=lambda kv: int(kv[0]))}
        if extra: spec['semantics'] = extra
        fields[fid] = spec
        return fid
    pk_id = add(key + '_id', pk, cols[pk])
    if prof is None:                                     # küçük hedef varlık: kimlik + ad (+ durum)
        for c in [NAME_COL.get(lg, 'new_name')] + EXTRA.get(lg, []):
            real = next((x for x in cols if x.lower() == c.lower() and x.lower() in phys), None)
            if real: add(fold(cols[real]['label'] or c), real, cols[real])
        if state: add('statecode', state, cols[state])
    else:
        fks = {f['fk'].lower(): f for f in d['fks']}
        for c, m in sorted(cols.items(), key=lambda kv: (kv[0] != 'statecode', kv[0])):
            lc = c.lower()
            if c == pk or lc not in phys or lc in SKIP or NOISE.search(c) or m['type'] in ('timestamp', 'ntext'):
                continue
            if name_is_sensitive(c) or name_is_sensitive(fold(m['label'] or '')):
                continue
            fill = prof['fill'].get(c, 0)
            if lc in ('statecode', 'statuscode', 'createdon'):
                add(lc if lc != 'createdon' else 'created_on', c, m); continue
            if fill < 0.05: continue
            if m['type'] in ('lookup', 'customer') or lc in fks:     # N:N ara tablonun uçları uniqueidentifier tipinde
                f = fks.get(lc)
                if not f or f['parent'] not in target_keys: continue
                fid = add((fold(m['label']) if m['label'] else target_keys[f['parent']]) + '_id', c, m)
                rel[f'{key}_{fid}_to_{target_keys[f["parent"]]}'] = (key, fid, f['parent'], f['name'])
                continue
            add(fold(m['label'] or c), c, m)
    ent[key] = {'table': base, 'schema': 'dbo', 'primary_key': pk_id, 'grain': 'one physical source record', 'fields': fields,
                'active_predicate': ('{alias}.[' + state + ']=0') if state and lg != 'systemuser' else '1=1',
                'predicate_columns': [state] if state and lg != 'systemuser' else [],
                'provenance': 'crm_process_metadata_20261004', 'semantic_notes': NOTES.get(key, []), 'label_tr': d.get('label') or ''}
    n, nd = one(f"SELECT COUNT_BIG(*), COUNT_BIG(DISTINCT [{pk}]) FROM dbo.[{base}]" + (f" WHERE [{state}]=0" if state else ''))
    checks.append(f'{key}: PK tekil {nd}/{n}')

relations = {}
for name, (child, fid, parent_lg, provenance) in rel.items():
    if parent_lg in EXISTING:
        right, right_field = EXISTING[parent_lg]
    elif KEYS.get(parent_lg) in ent:
        right = KEYS[parent_lg]; right_field = ent[right]['primary_key']
    else:
        continue
    c_tab, c_col = ent[child]['table'], ent[child]['fields'][fid]['column']
    p_tab = {'book': 'new_kitapBase', 'account': 'AccountBase', 'contact': 'ContactBase'}.get(right) or ent[right]['table']
    p_pk = {'book': 'new_kitapId', 'account': 'AccountId', 'contact': 'ContactId'}.get(right) or ent[right]['fields'][right_field]['column']
    filled, found = one(f"SELECT COUNT_BIG(c.[{c_col}]), COUNT_BIG(p.[{p_pk}]) FROM (SELECT TOP 300000 [{c_col}] FROM dbo.[{c_tab}]) c LEFT JOIN dbo.[{p_tab}] p ON p.[{p_pk}]=c.[{c_col}]")
    checks.append(f'{name}: FK hedefte {found}/{filled}')
    relations[name] = {'left_entity': child, 'right_entity': right, 'left_field': fid, 'right_field': right_field,
                       'cardinality': 'many_to_one', 'nullable': True, 'target_unique': True, 'provenance': provenance,
                       'semantic_note': f'CRM metadata FK → PK; measured {found}/{filled} child values resolve (sample ≤300k). Reverse traversal can multiply grain.'}

with open(OUT, 'w') as f:
    f.write('"""CRM süreç kayıtları (üretilmiştir: scripts/crm-process/build_process_registry.py, 2026-10-04).\n\n'
            'Sipariş, sipariş satırı, bekleyen ürün, satış hedefi, etkinlik, ziyaret yeri ve kitap sınıflaması. Alan adları ve kod\n'
            'etiketleri CRM metadata\'sından; ilişkiler fiziksel FK → tekil PK; her biri veriyle ölçüldü (aşağıdaki MEASUREMENTS).\n'
            'CRM süreç kaydıdır: tutarlar sipariş anındaki tutardır, ciro ve tahsilat Logo\'dadır. Elle düzenlemeyin; betiği yeniden koşun.\n"""\n\n')
    f.write('PROCESS_ENTITIES = ' + pprint.pformat(ent, width=120, sort_dicts=False) + '\n\n')
    f.write('PROCESS_RELATIONS = ' + pprint.pformat(relations, width=120, sort_dicts=False) + '\n\n')
    f.write('MEASUREMENTS = ' + pprint.pformat(checks, width=120) + '\n')
print(len(ent), 'varlık', sum(len(e['fields']) for e in ent.values()), 'alan', len(relations), 'ilişki')
print('\n'.join(checks))
