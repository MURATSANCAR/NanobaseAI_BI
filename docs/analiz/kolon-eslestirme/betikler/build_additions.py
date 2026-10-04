"""Sözlük eki üretir: web bulguları + canlı veriyle doğrulanan kodlar → configs/schemas/logo-column-additions.json.

Sunucuda koşar (canlı şema envanteri /tmp/ltc_logo_inv.json gerekir). Yalnız TİMAŞ firmalarında canlı bulunan
tablo/kolonlar alınır; güveni high/medium olmayan, başka tablodan aktarılan ya da açıklamasız bulgular alınmaz.
Müşteri verisi içermez: tablo/kolon adı, açıklama, kod etiketi ve kaynak adresi.

    python build_additions.py logo-web-bulgular.json logo-column-additions.json
"""
import json, re, sys
from datetime import date

FIRMS = {'015', '016', '105', '115', '171', '181', '191', '201', '211', '411'}
PAT = re.compile(r'^LG_(\d{3})_(?:(\d{2})_)?(.+)$')
web = json.load(open(sys.argv[1]))
inv = json.load(open('/tmp/ltc_logo_inv.json'))
ldds = set(json.load(open('/data/nanobaseai/bi/frontend/configs/schemas/logo-ldds.json'))['tables'])
phys = lambda base, scope: ('L_' if scope == 'system' else 'LG_') + base

live = {}                                   # BASE -> (scope, physical-pattern, columns)
for name, o in inv.items():
    m = PAT.match(name)
    if m and m.group(1) in FIRMS:
        base, scope = m.group(3), ('period' if m.group(2) else 'firm')
    elif name.startswith('L_'):
        base, scope = name[2:], 'system'             # sözlük anahtarı önekiz: L_CAPIDEF → CAPIDEF
    else:
        continue
    s = live.setdefault(base, [scope, set()])
    s[1].update(c[0] for c in o['columns'])

# Canlı veriyle doğrulananlar (docs/analiz/kolon-eslestirme/dogrulama.md): kod etiketi ve açıklama.
V = 'canlı veriyle doğrulandı 2026-10-03 (docs/analiz/kolon-eslestirme/dogrulama.md)'
VERIFIED = {
    ('INVOICE', 'EINVOICE'): ('Faturanın kesiliş biçimi', {'0': 'Kağıt fatura', '1': 'e-Fatura', '2': 'e-Arşiv fatura', '3': 'e-Arşiv fatura'}),
    ('INVOICE', 'PROFILEID'): ('e-Fatura senaryosu', {'0': 'Senaryo seçilmemiş', '1': 'Temel fatura', '2': 'Ticari fatura'}),
    ('EINVOICEDET', 'PROFILEID'): ('e-Fatura senaryosu', {'0': 'Senaryo seçilmemiş', '1': 'Temel fatura', '2': 'Ticari fatura'}),
    ('INVOICE', 'EINVOICETYP'): ('e-Fatura/e-Arşiv fatura tipi', {'0': 'Satış (iade faturasında İade)', '2': 'İstisna', '4': 'Tevkifat'}),
    ('EINVOICEDET', 'EINVOICETYP'): ('e-Fatura/e-Arşiv fatura tipi', {'0': 'Satış (iade faturasında İade)', '2': 'İstisna', '4': 'Tevkifat'}),
    ('EARCHIVEDET', 'SENDMOD'): ('e-Arşiv gönderim şekli', {'0': 'Belirtilmemiş', '1': 'Kağıt', '2': 'Elektronik'}),
    ('EBOOKDETAILDOC', 'DOCUMENTTYPE'): ('e-Defter belge türü', {'0': 'Seçilmemiş (cari/banka/kasa kaynaklı mahsup)', '2': 'Fatura', '6': 'Diğer (açıklama dolu)', '99': 'Belgesiz'}),
    ('CLCARD', 'ACCEPTEINV'): ('Cari e-Fatura mükellefi mi', {'0': 'Mükellef değil', '1': 'e-Fatura mükellefi'}),
    ('CLCARD', 'ISPERSCOMP'): ('Şahıs mı şirket mi (kimlik no TCKNO, vergi no TAXNR)', {'0': 'Şirket', '1': 'Şahıs'}),
    ('INVOICE', 'CANCELDATE'): ('Faturanın iptal tarihi (CANCELLED=1 olan faturada dolu; iptal çoğu kez sonraki ay yapılır)', None),
    ('INVOICE', 'CANCELEXP'): ('İptal açıklaması', None),
    ('INVOICE', 'DOCDATE'): ('Belge tarihi: satış faturasında DATE_ ile aynı; alış ve alınan hizmet faturasında tedarikçi belgesinin tarihi', None),
    ('INVOICE', 'TOTALSERVICES'): ('Faturadaki hizmet satırlarının (STLINE LINETYPE=4) toplamı', None),
    ('PAYTRANS', 'MATCHDATE'): ('Kapanma (eşleşme) tarihi: ödenen = toplam olduğunda dolar; boşsa kalem açık ya da kapama koşulmamış', None),
    ('STFICHE', 'CANCELLEDINVREF1'): ('İrsaliyenin bağlı olduğu iptal edilmiş faturanın referansı', None),
    ('STLINE', 'DEDUCTIONPART1'): ('Tevkifat oranının payı (DEDUCTIONPART2 paydası; ör. 2/3, 9/10)', None),
    ('STLINE', 'DEDUCTIONPART2'): ('Tevkifat oranının paydası', None),
    ('STLINE', 'VATEXCEPTCODE'): ('GİB KDV istisna kodu', {'301': 'Mal ihracatı', '302': 'Hizmet ihracatı', '335': 'Basılı kitap ve süreli yayın teslimi', '350': 'Diğer istisnalar', '351': 'İstisna olmayan diğer'}),
    ('INVOICE', 'VATEXCEPTCODE'): ('GİB KDV istisna kodu', {'301': 'Mal ihracatı', '302': 'Hizmet ihracatı', '335': 'Basılı kitap ve süreli yayın teslimi', '350': 'Diğer istisnalar', '351': 'İstisna olmayan diğer'}),
}

def keep(c):
    if not c or c.get('confidence') not in ('high', 'medium'):
        return False
    if 'tabloya aktarıldı' in (c.get('source_note') or ''):
        return False
    return bool((c.get('description_tr') or '').strip() or (c.get('description_en') or '').strip())

out = {'generated_at': str(date.today()), 'generator': 'docs/analiz/kolon-eslestirme/betikler/build_additions.py',
       'sources': web.get('sources', []), 'tables': {}}
for key, t in web['tables'].items():
    base = key[2:] if key.startswith('L_') else key
    if base not in live or key in web.get('copies', {}):
        continue
    scope, cols = live[base]
    entry = {'scope': scope, 'physical': phys(base, scope), 'columns': {}}
    if keep(t) or (t.get('description_tr') and (t.get('url') or '').startswith('http') and t.get('confidence') in ('high', 'medium')):
        entry.update({k: v for k, v in {'description_tr': t.get('description_tr'), 'description': t.get('description_en'),
                      'web_source': t.get('url'), 'confidence': t.get('confidence')}.items() if v})
    for col, c in (t.get('columns') or {}).items():
        if col in cols and keep(c):
            e = {k: v for k, v in {'description_tr': (c.get('description_tr') or '').strip() or None, 'description': c.get('description_en'),
                 'web_source': c.get('url'), 'confidence': c.get('confidence')}.items() if v}
            vals = {str(k): v for k, v in (c.get('values') or {}).items() if str(k).lstrip('-').isdigit()}
            if vals:
                e['values_tr'] = vals
            entry['columns'][col] = e
    if entry['columns'] or entry.get('description_tr'):
        out['tables'][base] = entry
generic = {k: v for k, v in web.get('columns_generic', {}).items() if keep(v)}
known = ldds | set(out['tables'])                   # yedek/kopya tablolar (STLINE_yedek1…) genel kolon almaz
for base, (scope, cols) in live.items():           # genel kolonlar (SITEID, RECSTATUS…) bilinen her canlı tabloda
    if base not in known:
        continue
    for col in cols & set(generic):
        t = out['tables'].setdefault(base, {'scope': scope, 'physical': phys(base, scope), 'columns': {}})
        c = generic[col]
        t['columns'].setdefault(col, {k: v for k, v in {'description_tr': c.get('description_tr'), 'description': c.get('description_en'),
                                      'web_source': c.get('url'), 'confidence': c.get('confidence')}.items() if v})
for (base, col), (text, values) in VERIFIED.items():
    if base not in live or col not in live[base][1]:
        continue
    t = out['tables'].setdefault(base, {'scope': live[base][0], 'physical': phys(base, live[base][0]), 'columns': {}})
    e = t['columns'].setdefault(col, {})
    e.update({'description_tr': text, 'confidence': 'verified', 'verified': V})
    if values:
        e['values_tr'] = values
json.dump(out, open(sys.argv[2], 'w'), ensure_ascii=False, indent=1, sort_keys=True)
print('tablo', len(out['tables']), 'kolon', sum(len(t['columns']) for t in out['tables'].values()),
      'doğrulanmış', sum(1 for t in out['tables'].values() for c in t['columns'].values() if c.get('confidence') == 'verified'))
