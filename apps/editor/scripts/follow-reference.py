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

root=Path(__file__).resolve().parents[1]
run=json.loads((root/'evidence/reference-book-run.json').read_text())
token=(root/'secrets/api_token').read_text().strip()
base='http://127.0.0.1:8810'; gen=run['job']['generation_id']
output=root/'runtime/book-analysis'/gen; output.mkdir(parents=True,exist_ok=True); output.chmod(0o700)


def request(path,body=None,key=None):
    headers={'Authorization':'Bearer '+token}
    if body is not None: headers['Content-Type']='application/json'
    if key: headers['Idempotency-Key']='book-acceptance-v1-'+key
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=60) as response: return json.load(response)


def wait_job(job):
    start=time.monotonic(); previous=None
    while time.monotonic()-start<86400:
        state=request('/v1/jobs/'+job)
        public={k:state[k] for k in ('status','progress','error_code','counts')}
        if public!=previous:
            print(json.dumps({'job_id':job,**public},ensure_ascii=False),flush=True); previous=public
        (output/'progress.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
        if state['status']=='COMPLETED': return state
        if state['status'] in ('FAILED','CANCELLED'): raise RuntimeError('JOB_'+state['status']+':'+str(state['error_code']))
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
    for kind in ('evidence','visuals','scenes','entities','events','literary','validation','passages'):
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
    answers={}
    for index,(key,job) in enumerate(jobs.items(),1):
        wait_job(job['job_id']); answers[key]=request('/v1/answers/'+job['job_id'])
        (output/'answers.json').write_text(json.dumps(answers,ensure_ascii=False,indent=2))
        if index%10==0: print(json.dumps({'questions_completed':index,'semantic_reference_review':'PENDING'}),flush=True)
    lines=['# Ekrana Sığmayan Macera — kaynaklı analiz taslağı','',
      'Analiz nesli: '+gen,'','İşleme tamamlandı. Yayınevi editör kabulü ve bağımsız anlamsal değerlendirme bekleniyor.','',
      '## Kitap ve sınırlı edebî analiz','']
    for row in data['literary']: lines.extend(['```json',json.dumps(row['data'],ensure_ascii=False,indent=2),'```',''])
    lines.extend(['## Atıflı soru cevap denemeleri',''])
    for key,row in answers.items():
        a=row['answer']; lines.extend(['### '+key+' — '+questions[key],'',a.get('answer',''),'',
          'Durum: '+a.get('status','UNKNOWN')+'; taslak, insan onayı yok.',''])
        for claim in a.get('claims',[]): lines.append('- '+claim['text']+' — '+', '.join(claim['evidence_refs']))
        lines.append('')
    lines.extend(['## Kabul sınırları','',
      '- B18: Değişmiş gerçek ikinci baskı sağlanmadı; doğrulanamadı.',
      '- Diğer iki pilot kitap ve yayınevi editör ölçümleri bu tek kitap koşusunun kapsamında tamamlanmış sayılmaz.',
      '- B01/B02/B03/B15 ve V01–V08, kaydedilmiş özgün sayfalarla bağımsız inceleme gerektirir.',
      '- İşin teknik olarak tamamlanması, anlamsal doğruluk veya üretime kabul değildir.'])
    (output/'analysis-report.md').write_text('\n'.join(lines))
    (output/'completion.json').write_text(json.dumps({'processing_complete':True,'human_accepted':False,'generation_id':gen,'questions':len(answers)},indent=2))
    print(json.dumps({'processing_complete':True,'output':str(output),'human_accepted':False}),flush=True)
except Exception as exc:
    (output/'run-error.json').write_text(json.dumps({'error_type':type(exc).__name__,'message':str(exc)},indent=2))
    raise
