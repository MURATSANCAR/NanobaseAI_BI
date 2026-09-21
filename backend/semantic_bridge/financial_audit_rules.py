"""Evidence-oriented interpretation of the supplied 2020 document.

Ledger observations are not evidence of document authenticity or tax compliance.
Every source occurrence has its own result; duplicate note numbers stay distinct.
"""
from collections import Counter
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2] / 'configs/financial-audit'
D = lambda x: Decimal(str(x or 0))
EPS = Decimal('.01')


def source():
    return json.loads((ROOT / 'source.json').read_text())


# Explicitly reviewed primary account for each source note. Never infer accounting
# meaning from the unreliable Logo ACCTYPE card or from copying another note.
PRIMARY = dict(zip(range(50, 88), '''100 100 100 197 101 101 102 102 103 103 110 111 112 118 119 120 121 121 122 124 126 127 128 129 131 132 133 135 136 137 138 139 150 151 152 153 157 158'''.split()))
PRIMARY.update(dict(zip(range(89, 115), '''159 17 179 180 181 190 191 193 196 197 199 220 221 222 226 229 231 232 235 236 237 239 241 242 244 247'''.split())))
PRIMARY.update(dict(zip(range(116, 143), '''252 253 254 255 259 260 262 264 269 279 280 281 291 295 298 300 320 321 322 326 329 331 332 335 336 337 340'''.split())))
PRIMARY.update(dict(zip(range(144, 160), '''380 381 391 393 397 400 420 421 422 426 429 431 432 436 437 440'''.split())))
PRIMARY.update({161:'481',162:'501',163:'540',164:'549',165:'590',166:'591',44:'19',46:'102',47:'100',48:'101',49:'121'})
OVERRIDES = {'note-115-1':'249','note-115-2':'250','note-115-3':'251',
             'note-143-1':'349','note-143-2':'371','note-160-1':'449','note-160-2':'480'}
# Union of numerator and denominator accounts, for traceability only. Prefix
# matching selects each account once; it never adds these groups to a ratio.
RATIO_ACCOUNTS = {
    2:['1','3'], 3:['1','3'], 4:['10','11','3'], 5:['1'],
    6:['1','2'], 7:['3','10','11','15'], 8:['1'], 9:['1','2'],
    10:['1','2','3','4'], 11:['1','2','5'], 12:['3','4','5'],
    13:['3','4','5'], 14:['3','4','5'], 15:['4','5'], 16:['25','5'],
    17:['25','4','5'], 18:['3','4'], 19:['300','303','400','1','2'],
    20:['300','303','400','5'], 21:['1','2'],
    22:['621','153','620','152'], 23:['60','61','12','22'],
    24:['60','61','1','3'], 25:['60','61','25'], 26:['60','61','2'],
    27:['60','61','5'], 28:['60','61','1','2'],
    29:['6','5'], 30:['6','5'], 31:['6','3','4','5'], 32:['6','1','2'],
    33:['60','61','62','63','1','2'], 34:['54','57','58','1','2'],
    35:['60','61','62','63'], 36:['60','61','62'], 37:['6'],
    38:['62','60','61'], 39:['63','60','61'], 40:['660','661','60','61'],
    41:['6'], 42:['6'],
}
SECTION_ACCOUNTS = dict(zip(range(1,50), '''60 600 601 602 61 610 612 62 620 621 622 623 63 63 630 631 632 64 640 641 642 643 644 645 646 647 648 649 65 653 654 655 656 657 658 659 66 660 661 67 671 679 68 680 681 689 690 691 692'''.split()))
DEBIT_NORMAL = set('100 101 108 110 111 112 118 120 121 126 127 128 131 132 133 135 136 138 150 151 152 153 157 159 179 180 181 190 191 193 195 196 197 198 220 221 226 231 232 233 235 236 240 242 245 248 250 251 252 253 254 255 256 258 259 260 261 262 263 264 267 269 271 272 277 279 280 281 291 292 293 294 295 297 302 308 322 337 371 402 408 422 437 501 503 580 591'.split())
CREDIT_NORMAL = set('103 119 122 124 129 137 139 158 199 222 224 229 237 239 241 243 244 246 247 249 257 268 278 298 299 300 301 303 304 305 306 309 320 321 326 329 331 332 333 335 336 340 349 350 351 352 353 354 355 356 357 360 361 368 369 370 372 373 379 380 381 391 392 397 399 400 401 405 407 409 420 421 426 429 431 432 433 436 438 440 449 472 479 480 481 492 493 499 500 502 520 521 522 523 524 529 540 541 542 548 549 570 590'.split())
FX_NOTES = {52,54,56,58,66,71,72,73,74,75,76,77,78,80,81,91,101,104,105,107,108,110,131,133,136,138,139,140,149,151,154,155,156,157}
YEAR_END_NOTES = {53,98,147,148,165,166}
PROVISION = {64,73,81,87,99,104,110,111,113,114,130}
DEPRECIATION = {116,117,118,119,121,122,123}
REESKONT = {68,79,102,109,134,141,152,158}

CORRECTIONS = {
  16:'Maddi duran varlıklar 25 hesap grubudur; kaynakta yazılan 24 mali duran varlıklardır.',
  17:'Maddi duran varlıklar için 24 yerine net 25 grubu kullanılır.',
  25:'Devir hızı paydasında maddi duran varlıklar net 25 grubudur.',
  30:'590 vergi sonrası sonuçtur; vergi öncesi kâr yerine kullanılamaz.',
  31:'Vergi öncesi sonuç ile finansman gideri birlikte alınmalı; 590 vergi öncesi sonuç değildir.',
  34:'52 sermaye yedekleri dağıtılmamış kâr değildir. Kâr yedekleri ve geçmiş net sonuçlar (54+57−58) kullanılır.',
  36:'Brüt satış kârı = net satışlar − satış maliyeti; kaynak payında 61 indirimleri eksik.',
  39:'Faaliyet giderleri 63 grubudur; 65 diğer faaliyetlerden olağan gider ve zararlardır.',
  41:'Finansman gideri paydasında 660 ile 661 toplanır; çıkarılmaz.',
  42:'Finansman gideri paydasında 660 ile 661 toplanır; çıkarılmaz.',
  49:'Kaynak senet için çek belge kodu diyor. E-defter belge türü sözlüğü doğrulanmadan kod eşlemesi uygulanmaz.',
  51:'2020 belgesindeki 7.000 TL sabiti güncel değildir. 2026 için 30.000 TL tevsik eşiği, kapsam ve istisnalarla birlikte değerlendirilir; kasa satırı tek başına ihlal kanıtı değildir.',
  65:'Alıcı alacak bakiyesi otomatik olarak 159 hesabına taşınamaz. Avansın ve işlemin niteliği belgelenmelidir.',
  83:'Kaynak ilk cümlede 721 hesabını tekrarlıyor; üretim yansıtma kapsamı 711, 721, 731 ve seçeneğe göre 799 olarak incelenir.',
  87:'Karşılık ayırmada 158 alacak / 654 borç yönü incelenir. Kaynaktaki iki borç hesabı ifadesi kullanılmaz.',
  111:'Karşılık ayırmada ilgili karşılık hesabı alacak, gider hesabı borç yönündedir.',
  131:'Banka kredisinde mevduat faiz geliri kontrolü kopyalanamaz. Kredi faizi, ödeme planı ve gider tahakkuku gerekir.',
  132:'Satıcı hesabında normal yön alacaktır; alıcı hesabının borç yönü kopyalanmaz.',
  134:'Borç senetleri reeskontu borç karakterlidir; senet hesabının kontrolü aynen kopyalanmaz.',
  137:'Örtülü sermaye testi sermaye hesabı alacak toplamının üç katı değildir; dönem başı özsermaye, ilişkili kişi borçları, tarihler ve istisnalar gerekir.',
  141:'Diğer borç senetleri reeskontu borç karakterlidir; alacak senedi kuralı kopyalanmaz.',
  145:'Gider tahakkuku, peşin gider amortismanı değildir; giderin ait olduğu dönem ve tahakkuk belgesi gerekir.',
  162:'Sermaye taahhüdü 501 borç, nakit ödeme 501 alacak yönündedir. Ayni sermaye banka hareketi gerektirmeyebilir.',
  163:'Yedek hesabı ödenmiş sermaye, önceki yedekler, net kâr ve dağıtım kararına bağlıdır; 500 alacak toplamı tek başına yeterli değildir.',
  165:'Devir sonrası 692 kapanır. Son bakiyeleri eşitlemek yerine 692 borç / 590 alacak devir fişi doğrulanır.',
  166:'Devir sonrası 692 kapanır. Son bakiyeleri eşitlemek yerine 692 alacak / 591 borç devir fişi doğrulanır.',
}
REFERENCES = [
 {'title':'GİB — Tevsik zorunluluğu, 459 Sıra No.lu VUK Genel Tebliği', 'url':'https://gib.gov.tr/mevzuat/kanun/434/teblig/7953'},
 {'title':'GİB — Nisan 2026 tevsik bilgilendirmesi', 'url':'https://cdn.gib.gov.tr/api/gibportal-file/file/getFileResources?objectKey=arsiv%2Fyardim-kaynaklar%2Finfografikler%2Fpdfs%2Fmal-hizmet-tevik.pdf'},
 {'title':'GİB — Örtülü sermaye, dönem başı özsermaye ve ilişkili kişi borçları', 'url':'https://gib.gov.tr/mevzuat/kanun/435/ozelge/28381'},
]

# Same-voucher observations, not an assertion that every transaction legally
# requires this entry (purchases, reversals, 7/A-7/B and timing may differ).
PAIRS = {
  'note-64-1':('119','credit',['654'],'debit'),
  'note-73-1':('129','credit',['654'],'debit'),
  'note-81-1':('139','credit',['654'],'debit'),
  'note-82-1':('150','credit',['710','790'],'debit'),
  'note-83-1':('151','debit',['711','721','731','799'],'credit'),
  'note-84-1':('151','credit',['152'],'debit'),
  'note-85-1':('153','credit',['621'],'debit'),
  'note-86-1':('157','credit',['623'],'debit'),
  'note-87-1':('158','credit',['654'],'debit'),
  'note-93-1':('181','debit',['6'],'credit'),
  'note-99-1':('199','credit',['654'],'debit'),
  'note-104-1':('229','credit',['654'],'debit'),
  'note-110-1':('239','credit',['654'],'debit'),
  'note-111-1':('241','credit',['654'],'debit'),
  'note-113-1':('244','credit',['654'],'debit'),
  'note-114-1':('247','credit',['654'],'debit'),
  'note-115-1':('249','credit',['654'],'debit'),
  'note-127-1':('281','debit',['6'],'credit'),
  'note-130-1':('298','credit',['654'],'debit'),
  'note-162-1':('501','credit',['102'],'debit'),
}


def pair_sql(joins, where):
    inner,outer = [],[]
    for i,(key,(p,side,other,other_side)) in enumerate(PAIRS.items()):
        condition=' OR '.join(f"A.CODE LIKE '{v}%'" for v in other)
        inner.extend([f"SUM(CASE WHEN A.CODE LIKE '{p}%' THEN CAST(L.{side} AS decimal(28,4)) ELSE 0 END) AS t{i}",
                      f"SUM(CASE WHEN ({condition}) THEN CAST(L.{other_side} AS decimal(28,4)) ELSE 0 END) AS c{i}"])
        outer.extend([f"SUM(CASE WHEN t{i}>0.01 THEN 1 ELSE 0 END) AS triggered{i}",
                      f"SUM(CASE WHEN t{i}>0.01 AND c{i}<=0.01 THEN 1 ELSE 0 END) AS missing{i}",
                      f"SUM(CASE WHEN t{i}>0.01 AND c{i}<=0.01 THEN t{i} ELSE 0 END) AS amount{i}"])
    return f"SELECT {','.join(outer)} FROM (SELECT {','.join(inner)} {joins} WHERE {where} AND F.TRCODE<>1 GROUP BY L.ACCFICHEREF) V"


def pair_results(record):
    return {key:{'id':'voucher-counterpart','title':'Aynı fişte karşı hesap gözlemi','status':'observed',
                 'triggered':int(record.get(f'triggered{i}') or 0), 'affected':int(record.get(f'missing{i}') or 0),
                 'amount':str(record.get(f'amount{i}') or 0),
                 'formula':f"Açılış dışı fişte {p} {'borç' if side=='debit' else 'alacak'} > 0,01 TL; {'/'.join(other)} {'borç' if other_side=='debit' else 'alacak'} görünmeyen fişler. Alternatif işlem/tarih/nitelik incelemesi gerekir."}
            for i,(key,(p,side,other,other_side)) in enumerate(PAIRS.items())}


def scope(item):
    n = item['note']
    if item['kind'] == 'analysis':
        return RATIO_ACCOUNTS.get(n, [])
    if item['id'] in OVERRIDES:
        return [OVERRIDES[item['id']]]
    if n in PRIMARY:
        if n == 44: return ['191','391']
        if n in {53,98,148}: return ['197','397']
        if n in {165,166}: return [PRIMARY[n], '692']
        if n == 90: return [str(c) for c in range(170,178)]
        if n == 84: return ['151','152']
        return [PRIMARY[n]]
    match = re.match(r'^(?:4|5|15)\.[\d.]+\s+(\d{3})(?:\D|$)', item['section'])
    if match: return [match[1]]
    match = re.match(r'^(?:5|15)\.1[23]\.(\d+)', item['section'])
    if match and item['page'] >= 191:
        return [SECTION_ACCOUNTS.get(int(match[1]), '6')]
    return []


def requirements(item):
    """Evidence routing only; keyword matches never decide pass/fail."""
    text = (item['title'] + ' ' + item['text']).lower()
    pairs = [
      (('fatura','irsaliye','belge'), 'Asıl fatura/irsaliye, tarih-numara, satır tutarları ve muhasebe bağlantısı'),
      (('beyan','kdv','vergi'), 'İşlem dönemi mevzuatı, uygulanabilir istisnalar ve onaylı beyanname'),
      (('kur','döviz','yabancı para'), 'Döviz türü, döviz bakiyesi, değerleme tarihi ve resmî kur'),
      (('stok','sayım','envanter','randıman','üretim'), 'Fiili sayım, miktar hareketleri, maliyet ve fire dayanakları'),
      (('amortisman','faydalı ömür'), 'Varlık kartı, edinim/kullanıma başlama tarihi, yöntem ve dönem amortisman cetveli'),
      (('ortak','sermaye','iştirak'), 'İlişkili kişi eşlemesi, sözleşme, dönem başı özsermaye ve kararlar'),
      (('şüpheli','dava','icra'), 'Borçlu bazında teminat, dava/icra ve tahsil edilebilirlik kanıtı'),
      (('reeskont','senet','çek'), 'Senet/çek portföyü, nominal bedel, vade ve uygulanabilir iskonto oranı'),
      (('banka','kredi','faiz'), 'Banka ekstresi, dış mutabakat, sözleşme ve faiz/ödeme planı'),
      (('tahakkuk','gelecek ay','gelecek yıl','avans'), 'Sözleşme, hizmet/teslim dönemi ve tahakkuk/itfa takvimi'),
    ]
    return [label for words,label in pairs if any(w in text for w in words)] or ['Dayanak belge, işlem niteliği ve yetkili incelemesi']


def extend_ratios(out, extra):
    """All 41 analysis notes, with source errors and unmet prerequisites visible."""
    def b(p):
        return sum((D(a['balance']) for a in out['accounts'] if str(a['code'] or '').startswith(p)),D(0))
    def flow(p):
        return sum((D(a['periodDebit'])-D(a['periodCredit']) for a in extra if str(a['code'] or '').startswith(p)),D(0))
    def opening(p):
        return sum((D(a['openingDebit'])-D(a['openingCredit']) for a in extra if str(a['code'] or '').startswith(p)),D(0))
    short,long,equity = -b('3'),-b('4'),-b('5')
    assets = b('1')+b('2')
    sales = -flow('60')-flow('61')
    costs,opex,finance = flow('62'),flow('63'),flow('660')+flow('661')
    gross,operating = sales-costs,sales-costs-opex
    # 69 transfers are excluded to avoid double-counting the same result.
    pretax = -sum((flow('6'+str(i)) for i in range(9)),D(0))
    net = pretax-flow('691')
    costs_open = abs(flow('7')) > EPS
    equity_open = abs(D(out['closingGap'])) > EPS
    missing = (not out['lineCount'] or any(c['status']=='unverified' for c in out['checks'])
               or any(c['status']=='finding' for c in out['checks'] if c['id'] in {'account-link','slip-link','null-amount'}))
    title = {i['note']:i['title'] for i in source()['items'] if i['kind']=='analysis'}
    specs = [
      (16,b('25'),equity,'Net maddi duran varlıklar (25) / özkaynaklar', 'equity'),
      (17,b('25'),long+equity,'Net maddi duran varlıklar (25) / devamlı sermaye','equity'),
      (22,flow('621'),(opening('153')+b('153'))/2,'Ticari mal maliyeti (621 dönem net borç) / ortalama ticari mallar','opening'),
      (23,sales,b('12')+b('22'),'Dönem net satışları / dönem sonu net ticari alacaklar; kaynak tanımındaki son bakiye esası','sales'),
      (24,sales,b('1')-short,'Dönem net satışları / net çalışma sermayesi','sales'),
      (25,sales,b('25'),'Dönem net satışları / net maddi duran varlıklar (25)','sales'),
      (26,sales,b('2'),'Dönem net satışları / net duran varlıklar','sales'),
      (27,sales,equity,'Dönem net satışları / özkaynaklar','equity'),
      (28,sales,assets,'Dönem net satışları / toplam varlıklar','sales'),
      (29,net,equity,'Vergi sonrası dönem sonucu / özkaynaklar','profit_equity'),
      (30,pretax,equity,'Vergi öncesi dönem sonucu / özkaynaklar','profit_equity'),
      (31,pretax+finance,short+long+equity,'(Vergi öncesi sonuç + finansman giderleri) / toplam kaynaklar','profit_equity'),
      (32,net,assets,'Vergi sonrası dönem sonucu / varlıklar','profit'),
      (33,operating,assets-b('24'),'Faaliyet kârı / (varlıklar − mali duran varlıklar)','profit'),
      (34,-b('54')-b('57')-b('58'),assets,'(Kâr yedekleri + geçmiş kârlar − geçmiş zararlar) / varlıklar','equity'),
      (35,operating,sales,'(Net satışlar − satış maliyeti − faaliyet giderleri) / net satışlar','profit'),
      (36,gross,sales,'(Net satışlar − satış maliyeti) / net satışlar','profit'),
      (37,net,sales,'Vergi sonrası dönem sonucu / net satışlar','profit'),
      (38,costs,sales,'Satış maliyeti (62) / net satışlar','profit'),
      (39,opex,sales,'Faaliyet giderleri (63) / net satışlar','profit'),
      (40,finance,sales,'(660 + 661 dönem net borç) / net satışlar','profit'),
      (41,pretax+finance,finance,'(Vergi öncesi sonuç + 660 + 661) / (660 + 661)','profit'),
      (42,net+finance,finance,'(Vergi sonrası sonuç + 660 + 661) / (660 + 661)','profit'),
    ]
    from datetime import date
    elapsed = (date.fromisoformat(str(out['lastDate'])[:10])-date(out['year'],1,1)).days+1 if out['lastDate'] else 0
    for n,num,den,formula,gate in specs:
        reasons = []
        if missing: reasons.append('Kaynak verisi eksik veya bağlantı/tutar bütünlüğü sağlanmadı.')
        if den <= 0: reasons.append('Payda sıfır veya negatif.')
        if 'equity' in gate and equity_open: reasons.append('Bilanço ve özkaynak kapanış uyumu doğrulanmadı.')
        if 'profit' in gate and costs_open: reasons.append('7 grubu maliyet/gider hesapları henüz kapanmamış; gelir tablosu yansıtması doğrulanmadı.')
        if n in {29,32,37,42}: reasons.append('Dönem vergi karşılığı ve net sonuç beyannameyle mutabık değil.')
        if gate=='opening': reasons.append('Açılış stokları önceki yıl kapanışıyla mutabık değil; maliyet yansıtması ayrıca doğrulanmalı.')
        ratio={'note':n,'title':title[n],'numerator':str(num),'denominator':str(den),
               'formula':formula,'value':str(num/den) if not reasons else None,
               'status':'unverified' if reasons else 'calculated','reason':' '.join(reasons) or None,
               'correction':CORRECTIONS.get(n),'periodDays':elapsed,'unit':'ratio'}
        if n in {22,23,24}:
            ratio['days'] = str(D(elapsed)*den/num) if not reasons and num>0 else None
            ratio['daysFormula']='Kapsanan takvim günü / devir hızı; ara döneme otomatik 360 gün uygulanmaz.'
        if n==22:
            ratio['additional']={'title':'Mamul stok devir hızı','numerator':str(flow('620')),
                'denominator':str((opening('152')+b('152'))/2),'value':None,
                'reason':'Mamul açılışı ve maliyet yansıtması mutabakatı gerekiyor.'}
        out['ratios'].append(ratio)
    out['ratios'].sort(key=lambda x:x['note'])
    for r in out['ratios']:
        r['correction']=CORRECTIONS.get(r['note'])
    out['incomeReadiness']={'unreflectedCostBalance':str(flow('7')),'periodNetSales':str(sales),
        'periodCostOfSales':str(costs),'periodOperatingExpenses':str(opex),'periodFinanceCosts':str(finance),
        'profitAccepted':False,'reason':'Maliyet yansıtması, vergi karşılığı ve mali tablo mutabakatı gereklidir.'}


def evaluate(out, extra):
    accounts = out['accounts']
    src = source()
    by_note = {r['note']:r for r in out['ratios']}
    observations = []
    incomplete = not out['lineCount'] or any(c['status'] == 'unverified' for c in out['checks']) or any(c['status']=='finding' for c in out['checks'] if c['id'] in {'account-link','slip-link','null-amount'})
    for item in src['items']:
        prefixes = scope(item)
        chosen = [a for a in accounts if any(str(a['code'] or '').startswith(p) for p in prefixes)]
        n = item['note']
        evidence = requirements(item)
        components = []
        status = 'needs_evidence'
        reason = 'Muhasebe kapsamı çıkarıldı; bu maddenin belgesel/işlemsel doğruluğu aşağıdaki kanıtlarla incelenmeli.'
        if item['kind'] == 'analysis':
            ratio = by_note.get(n)
            status = ratio['status'] if ratio else 'unverified'
            reason = ratio.get('reason') or 'Formül hesaplandı; sektörel yeterlilik hükmü verilmedi.' if ratio else 'Oran tanımı uygulanamadı.'
            components = [ratio] if ratio else []
            evidence = [] if status=='calculated' else ['Dönem kapanışı, maliyet yansıtması ve açılış/önceki kapanış mutabakatı']
        elif incomplete:
            status, reason = 'unverified', 'Kaynak bütünlüğü doğrulanamadığından bu madde değerlendirilemedi.'
        else:
            # This is an accounting observation within a larger control, never a
            # substitute for the legal/evidence portion of that control.
            signs = [a for a in chosen if (str(a['code'])[:3] in DEBIT_NORMAL and D(a['balance']) < -EPS)
                     or (str(a['code'])[:3] in CREDIT_NORMAL and D(a['balance']) > EPS)]
            if prefixes:
                components.append({'id':'account-scope','title':'İlgili muhasebe kayıtları','status':'calculated',
                    'accountCount':len(chosen),'lineCount':sum(a['lineCount'] for a in chosen),
                    'debit':str(sum((D(a['debit']) for a in chosen),D(0))),
                    'credit':str(sum((D(a['credit']) for a in chosen),D(0))),
                    'balance':str(sum((D(a['balance']) for a in chosen),D(0)))})
                components.append({'id':'balance-sign','title':'Alt hesap yönü gözlemi','status':'finding' if signs else 'observed',
                    'affected':len(signs),'accountRefs':[a['accountRef'] for a in signs],
                    'amount':str(sum((abs(D(a['balance'])) for a in signs),D(0))),
                    'formula':'Alt hesap net borç−alacak bakiyesi; tanımlı ana hesap yönüne ters tutar > 0,01 TL. Mahsup/avans niteliği ayrıca incelenir.'})
            if n in {65,67,100,132,150}:
                status = 'finding' if signs else 'observed'
                reason = 'Ters bakiyeler inceleme adayıdır; doğru hesaba sınıflama işlem belgesine bağlıdır.'
            if n in YEAR_END_NOTES:
                if str(out['lastDate'])[:10] < f"{out['year']}-12-31":
                    status = 'not_due'
                    reason = 'Kaynak yıl sonundan önce bitiyor; kapanış kontrolünün zamanı gelmedi. Mevcut bakiyeler yalnız gözlemdir.'
                else:
                    status = 'needs_evidence'
                    reason = 'Yıl sonu kayıtları var; kapanış onayı ve devir fişlerinin belge bazında mutabakatı gerekiyor.'
            if n in FX_NOTES:
                evidence = list(dict.fromkeys(evidence+['Döviz türü, döviz bakiyesi, değerleme tarihi, resmî kur ve muhasebe kur farkı mutabakatı']))
                fx = [r for r in extra if any(str(r['code'] or '').startswith(p) for p in prefixes)]
                components.append({'id':'fx-profile','title':'Döviz hareketi alan profili','status':'observed',
                    'rows':sum(int(r.get('foreignRows') or 0) for r in fx),
                    'formula':'TRCURR dolu ve 0/160 dışında olan satırlar; döviz kodu sözlüğü ve döviz bakiyesi mutabakatı ayrıca gerekir.'})
            if n in PROVISION or item['id']=='note-115-1':
                evidence = ['Borçlu/varlık bazında değer düşüklüğü, teminat ve karşılık kararı','Karşılık ayırma/iptal fişi ile 654/644 bağlantısı']
            if n in DEPRECIATION or item['id'] in {'note-115-2','note-115-3'}:
                evidence = ['Varlık bazında maliyet, edinim ve kullanıma başlama tarihi, faydalı ömür, yöntem, istisnalar','Varlık kartı ↔ amortisman cetveli ↔ 257/268 muhasebe fişi mutabakatı']
            if n in REESKONT:
                evidence = ['Senet bazında nominal tutar, vade, değerleme tarihi ve uygulanabilir faiz oranı','647/657 ile reeskont ayırma ve ters kayıt fişlerinin eşlemesi']
            if n in {57,61,62,63,69,131,149}:
                evidence = ['Mevduat/kredi/menkul kıymet/finansal kiralama sözleşmesi, ana para, oran ve vadeler','Gün esaslı faiz hesabı, tahsilat/ödeme ve dönem tahakkuku mutabakatı']
            if n in {70,89,103,120,124,125,135,142,153,159} or item['id'] in {'note-143-1','note-160-1'}:
                evidence = ['Cari taraf, sözleşme, avans/depozito niteliği, vade ve teslim/mahsup belgeleri','Karşı taraf mutabakatı ve hesap sınıflaması; salt bakiye ihlal kanıtı değildir']
            if n in {92,93,126,127,144,145,161} or item['id']=='note-160-2':
                evidence = ['Sözleşme, fatura ve hizmet/teslim başlangıç-bitiş tarihleri','Aylık itfa/tahakkuk cetveli, cari/gelecek dönem ve kısa/uzun vade ayrımı']
            if n in {74,75,76,77,78,105,107,108,137,138,139,140,155,156,157}:
                evidence = ['Borçlu/alacaklı ve ilişkili kişi eşlemesi, günlük bakiye ve sözleşme','Dönem başı özsermaye, emsal faiz analizi, istisnalar ve işlem döneminin mevzuatı']
            if n in {72,80}:
                evidence = ['Borçlu ve alacak kaynağı, teminatlar, dava/icra dosyası, tarihler ve hukukçu teyidi','Tahsilat, karşılık ayırma/iptal ve değerleme kayıtlarının borçlu bazında mutabakatı']
            if n in {94,95,96,97,106,112,128,129,146,163,164} or item['id']=='note-143-2':
                evidence = list(dict.fromkeys(evidence+['İlgili dönemin mevzuatı, mükellef/işlem kapsamı, karar ve onaylı beyannameler']))
            if n in range(43,50):
                evidence = ['Üretilmiş e-defter satırları, belge türü ve ödeme yöntemi sözlüğü','Belge zorunluluğu/istisnası ile belge numarası ve tarihi']
                supporting = out.get('supportingEvidence',{})
                reason = 'Logo e-defter belge alanları okundu; sayısal türlerin sözlüğü ve üretilmiş XML ile mutabakatı ayrıca gerekir.'
                if supporting.get('status')=='unverified':
                    status,reason='unverified','E-defter destek sorgularından biri tamamlanamadı; belge kontrolü doğrulanamadı.'
                elif n==43:
                    p=supporting.get('documentVoucherProfile',{})
                    for key,label in [('multipleDocumentTypes','Birden fazla belge türü olan fiş'),('multiplePaymentTypes','Birden fazla ödeme türü olan fiş')]:
                        components.append({'id':key,'title':label,'status':'observed','affected':p.get(key) or 0,
                            'formula':'EBOOKDETAILDOC kaynak beyanında belge/ödeme yok olmayan türlerin fiş bazında tekilleştirilmesi; toplulaştırma istisnaları ayrıca incelenir.'})
                elif n==45:
                    for key,label in [('missingNumber','Belge var işaretli, numarası boş kayıt'),('missingDate','Belge var işaretli, tarihi eksik kayıt'),('missingPayment','Ödeme var işaretli, ödeme yöntemi boş kayıt')]:
                        count=sum(int(p.get(key) or 0) for p in supporting.get('documentProfiles',[]))
                        components.append({'id':key,'title':label,'status':'observed','affected':count,
                            'formula':'Logo e-defter kaynak bayraklarıyla alan doluluğu karşılaştırması. Kanuni belge zorunluluğu kararı değildir.'})
                else:
                    components.append({'id':'document-account','title':'Hesaba bağlı e-defter belge kayıtları','status':'observed',
                        'lineCount':sum(int(p['rows']) for p in supporting.get('accountDocumentProfiles',[]) if p['code'] in prefixes),
                        'formula':'Belge–ana hesap ilişkisi tekilleştirilir; fiş başlığı belgesi ile satır belgesi ayrı bağlantı koşuluyla okunur.'})
            if n in DEPRECIATION or item['id'] in {'note-115-2','note-115-3'}:
                profiles=out.get('supportingEvidence',{}).get('assetProfiles',[])
                components.append({'id':'asset-source','title':'Sabit kıymet hesap cetveli kapsamı','status':'observed' if profiles else 'unverified',
                    'lineCount':sum(p['rows'] for p in profiles),
                    'formula':'2026 FAYEAR kayıtlarının tamamı; varlık–muhasebe hesabı bağlantısı doğrulanmadığından bu notun varlıkları olarak sunulmaz. Hesaplama grupları birbirine eklenmez.'})
            if n == 51:
                reason = '30.000 TL eşiği tek kasa satırına uygulanıp ceza üretilmez; taraf, işlem bütünlüğü, taksitler, aracı kurum ve istisnalar birlikte gerekir.'
            if prefixes and not chosen and status != 'not_due':
                reason = 'İlgili hesaplarda kayıt bulunmadı. Kayıt dışı işlem olasılığı nedeniyle bu durum belgesel kontrolü geçmiş sayılmaz.'
            pair = out.get('pairChecks',{}).get(item['id'])
            if pair:
                components.append(pair)
            if n == 50:
                from datetime import date
                days=(date.fromisoformat(str(out['lastDate'])[:10])-date(out['year'],1,1)).days+1
                sales=-sum((D(r['periodDebit'])-D(r['periodCredit']) for r in extra if str(r['code'] or '').startswith('60')),D(0))
                cash=sum((D(a['balance']) for a in chosen),D(0))
                components.append({'id':'cash-sales','title':'Kasa / günlük brüt satış gözlemi','status':'observed',
                    'numerator':str(cash),'denominator':str(sales/D(days)),
                    'value':str(cash/(sales/D(days))) if sales>0 else None,
                    'formula':f'Kasa bakiyesi / (dönem brüt satışları / {days} takvim günü). Kaynaktaki 360 gün ara döneme uygulanmaz; adat/vergi kararı değildir.'})
            if n in {94,95,146}:
                components.extend({'id':f"vat-{m['month']}",'title':f"{m['month']}. ay KDV muhasebe bakiyesi",'status':'observed',
                    'balance':m['balance'],'formula':'Ay sonuna kadar birikimli 191+391 net bakiyesi; hesaplar ayrıca gösterilir. Beyanname kapanış onayı yerine geçmez.',
                    'accounts':m['accounts']} for m in out.get('vatMonths',[]))
        observations.append({'id':item['id'],'note':n,'kind':item['kind'],'title':item['title'],
            'page':item['page'],'endPage':item['endPage'],'status':status,'reason':reason,
            'accountPrefixes':prefixes,'accountRefs':[a['accountRef'] for a in chosen],
            'components':components,'requiredEvidence':evidence,'correction':CORRECTIONS.get(n),
            'definitionStatus':'interpreted' if item['kind'] in {'analysis','control'} else 'review_required',
            'sourceHash':src['sha256']})
    return {'items':observations,'counts':dict(Counter(x['status'] for x in observations)),
            'kindCounts':dict(Counter(x['kind'] for x in observations)),
            'completeControlCoverage':False,
            'coverageReason':'Numaralı maddeler ve bölüm metinleri kapsamdadır; bölüm paketleri atomik kontroller değildir. Belgesel ve mevzuat kabulü tamamlanmadı.',
            'references':REFERENCES,
            'revision':hashlib.sha256(Path(__file__).read_bytes()+(ROOT/'source.json').read_bytes()).hexdigest()}
