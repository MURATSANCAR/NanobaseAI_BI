#!/usr/bin/env python3
"""Wait for the real book, submit acceptance questions, preserve full API results.

This is a one-time connected run, not a scheduler or a synthetic test suite.
Answers and traces remain in the installation's protected evidence directory.
"""
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error
import fcntl
import html

root=Path(__file__).resolve().parents[1]
run=json.loads((root/'evidence/reference-book-run.json').read_text())
token=(root/'secrets/api_token').read_text().strip()
base='http://127.0.0.1:8810'; gen=run['job']['generation_id']
output=root/'runtime/book-analysis'/gen; output.mkdir(parents=True,exist_ok=True); output.chmod(0o700)
lock=(output/'follower.lock').open('a')
fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)


def request(path,body=None,key=None):
    headers={'Authorization':'Bearer '+token}
    if body is not None: headers['Content-Type']='application/json'
    if key: headers['Idempotency-Key']='book-acceptance-v1-'+key
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req,timeout=60) as response: return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in (502,503,504) or attempt==4: raise
        except urllib.error.URLError:
            if attempt==4: raise
        time.sleep(min(30,2**(attempt+1)))


def wait_job(job,allow_failed=False):
    start=time.monotonic(); previous=None
    while time.monotonic()-start<86400:
        state=request('/v1/jobs/'+job)
        public={k:state[k] for k in ('status','progress','error_code','counts')}
        if public!=previous:
            print(json.dumps({'job_id':job,**public},ensure_ascii=False),flush=True); previous=public
        (output/'progress.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
        if state['status']=='COMPLETED': return state
        if state['status'] in ('FAILED','CANCELLED'):
            if allow_failed: return state
            raise RuntimeError('JOB_'+state['status']+':'+str(state['error_code']))
        time.sleep(30)
    raise TimeoutError('REAL_BOOK_RUN_EXCEEDED_24_HOURS')


questions={
 'B04':'Yazarın adı nedir? Can kimdir; yazar ile aynı kişi olduğuna dair kanıt var mı?',
 'B05':'Bilge beklenenden erken mi geldi? Bunun açıklaması nedir?',
 'B06':'Max’in “dedeciğim” hitabı gerçek bir akrabalık gösteriyor mu?',
 'B07':'Max’in denge sorununu kim çözdü? Defne bu onarımda ne yaptı?',
 'B08':'Ortak laboratuvar gerçekten kuruldu mu? İlgili olayların gerçekleşme durumunu açıkla.',
 'B09':'Hikâyenin sonunda Robobi tamir edilmiş mi?',
 'B10':'Can tabletinde yalnızca oyun mu oynuyor; ne yapıyor?',
 'B11':'Oyunun gerçek dünyaya taşınması gerçekleşti mi, yoksa bir fikir mi?',
 'B12':'Kitaptaki etkinlik yönergeleri karakterlerin gerçekleştirdiği olaylar mıdır?',
 'B13':'Robobi’nin yetenekleriyle ilgili anlatım kesin bir tutarsızlık içeriyor mu? Kanıtları ve belirsizliği açıkla.',
 'B14':'Defne’nin başlangıç ve son bölümdeki duygu ve ilgisi nasıl değişti? Yorumun sınırları nelerdir?',
 'B16':'Sayma ve saklambaç oyunu oynandı mı, önerildi mi?',
 'B17':'Defne tam olarak kaç yaşında?'
}

try:
    final=wait_job(run['job']['job_id'])
    data={}
    for kind in ('evidence','visuals','scenes','entities','events','literary','validation','passages','claims','relationships','event_merges','book_synthesis','visual_corrections'):
        items=[]; offset=0
        while True:
            page=request(f'/v1/generations/{gen}/{kind}?offset={offset}&limit=100')
            items.extend(page['items'])
            if not page['has_more']: break
            offset+=len(page['items'])
        data[kind]=items
        (output/(kind+'.json')).write_text(json.dumps(items,ensure_ascii=False,indent=2))
    jobs={}
    for key,question in questions.items():
        jobs[key]=request('/v1/questions',{'generation_id':gen,'question':question,'mode':'editor_preview'},gen+'-'+key)
    (output/'question-jobs.json').write_text(json.dumps(jobs,indent=2))
    answers={}; failed_questions=[]
    for index,(key,job) in enumerate(jobs.items(),1):
        state=wait_job(job['job_id'],allow_failed=True)
        if state['status']=='COMPLETED': answers[key]=request('/v1/answers/'+job['job_id'])
        else:
            failed_questions.append(key)
            answers[key]={'answer':{'status':'ERROR','answer':'Cevap üretilemedi: '+str(state['error_code']),
                                    'claims':[]},'job':state}
        (output/'answers.json').write_text(json.dumps(answers,ensure_ascii=False,indent=2))
        if index%10==0: print(json.dumps({'questions_attempted':index,'answers_generated':index-len(failed_questions),
                                         'failed_questions':failed_questions,'semantic_reference_review':'PENDING'}),flush=True)
    reviews=[]; offset=0
    while True:
        batch=request(f'/v1/reviews?generation_id={gen}&offset={offset}&limit=100')['items']
        reviews.extend(batch)
        if len(batch)<100: break
        offset+=len(batch)
    (output/'reviews.json').write_text(json.dumps(reviews,ensure_ascii=False,indent=2))
    pages={row['id']:row['data']['pdf_page'] for row in data['evidence']}
    def refs(values): return 'PDF '+', '.join(map(str,sorted({pages[value] for value in values})))
    def clean(value): return html.escape(str(value)).replace('|','\\|').replace('\n',' ')
    modes={'ACTUAL':'Gerçekleşmiş','REPORTED':'Aktarılan','PLANNED':'Plan','HYPOTHETICAL':'Varsayım/hayal',
           'DREAM':'Rüya','METAPHOR':'Benzetme','JOKE':'Şaka'}
    lines=['# Ekrana Sığmayan Macera — kaynaklı analiz taslağı','',
      'Analiz ve soru denemelerinin sonuçları. Yayınevi editör kabulü ve bağımsız anlamsal değerlendirme bekleniyor.','',
      '## Kitabın özeti','']
    literary=data['literary'][0]['data']
    lines.extend([clean(literary.get('book_summary','')),'','## Karakterler ve diğer varlıklar','',
                  '| Ad | Tür | Kaynaklı açıklama | Kaynak |','|---|---|---|---|'])
    for row in data['entities']:
        d=row['data']; lines.append('| '+clean(d['name'])+' | '+clean(d.get('type','CHARACTER'))+' | '+clean(d.get('description',''))+' | '+refs(d['evidence_refs'])+' |')
    lines.extend(['','## Olaylar ve gerçekleşme durumu','','| Olay | Tür | Kaynak |','|---|---|---|'])
    for row in data['events']:
        d=row['data']; lines.append('| '+clean(d['description'])+' | '+modes.get(d['narrative_mode'],d['narrative_mode'])+' | '+refs(d['evidence_refs'])+' |')
    lines.extend(['','## Karakter değişimi örnekleri',''])
    for item in literary.get('character_change',[]):
        lines.extend(['### '+clean(item['character']),'',clean(item['initial'])+' → '+clean(item['later']),'',
          'Tetikleyici: '+clean(item['trigger']),'','Alternatif okuma: '+clean(item['alternative']),'',refs(item['evidence_refs']), ''])
    lines.extend(['## Tema yorumları',''])
    for item in literary.get('themes',[]):
        lines.extend([clean(item['interpretation']),'','Alternatif okuma: '+clean(item['alternative']),'',refs(item['evidence_refs']),''])
    lines.extend(['## Açık sorular ve inceleme',''])
    for item in literary.get('open_questions',[]): lines.append('- '+clean(item))
    for row in reviews:
        if row['decision'] in ('REJECT','NEEDS_REVIEW'):
            location='PDF '+str(row['data']['pdf_page']) if 'pdf_page' in row['data'] else row['record_key']
            lines.append('- '+location+' / '+row['kind']+': '+row['decision']+'. Özgün model kaydı korunuyor; kabul edilmiş bulgu değildir.')
    if data['visual_corrections']:
        lines.extend(['','## Kaynak okuma düzeltmeleri','',
            'Bunlar yerel model çıktısı değildir. Özgün sayfalardan operatör/Codex destekli gözlemler olarak girilmiş, insan onayı verilmemiş düzeltmelerdir.',''])
        for row in data['visual_corrections']:
            d=row['data']; lines.append('- PDF '+str(d['pdf_page'])+': '+clean(d['description'])+' ('+d['provenance']+')')
    lines.extend(['## Atıflı soru cevap denemeleri',''])
    for key,row in answers.items():
        a=row['answer']; lines.extend(['### '+key+' — '+questions[key],'',clean(a.get('answer','')),'',
          'Durum: '+a.get('status','UNKNOWN')+'; taslak, insan onayı yok.',''])
        for claim in a.get('claims',[]): lines.append('- '+clean(claim['text'])+' — '+refs(claim['evidence_refs']))
        lines.append('')
    lines.extend(['## Kabul sınırları','',
      '- B18: Değişmiş gerçek ikinci baskı sağlanmadı; doğrulanamadı.',
      '- Diğer iki pilot kitap ve yayınevi editör ölçümleri bu tek kitap koşusunun kapsamında tamamlanmış sayılmaz.',
      '- B01/B02/B03/B15 ve V01–V08, kaydedilmiş özgün sayfalarla bağımsız inceleme gerektirir.',
      '- İşin teknik olarak tamamlanması, anlamsal doğruluk veya üretime kabul değildir.'])
    (output/'analysis-report.md').write_text('\n'.join(lines))
    (output/'completion.json').write_text(json.dumps({'processing_complete':not failed_questions,'human_accepted':False,
        'generation_id':gen,'questions':len(answers),'failed_questions':failed_questions},indent=2))
    print(json.dumps({'processing_complete':not failed_questions,'output':str(output),'human_accepted':False}),flush=True)
except Exception as exc:
    (output/'run-error.json').write_text(json.dumps({'error_type':type(exc).__name__,'message':str(exc)},indent=2))
    raise
