"""Real Hermes API requests; run inside editor-hermes against the real book ledger."""
import json,os,time,urllib.request,uuid,sys
BOOK='d2d4a6f1-e5b3-4415-9d68-48f8fe768c03'
questions=[
 ('summary','Dünyanın En Korkak Hayvanı kitabını en çok altı cümlede, kaynak sayfalarıyla özetle.'),
 ('father','Baba Vombat ile Yavru Vombat aynı kişi mi? Özgün metinden kontrol et.'),
 ('animal','Yavru Vombat bir insan çocuğu mu, hayvan mı? Kaynak göster.'),
 ('librarian','Bu kitapta Salyangoz ne iş yapıyor? Kaynaktan kontrol et.'),
 ('page23','23. sayfada Anne Aslan hakkında ne söyleniyor? Anılması o sayfada çizildiğini kanıtlar mı?'),
 ('source','4. sayfada hangi yazı var? Metin yoksa uydurma.'),
 ('acceptance','Bu kitabın analizi tamamen onaylandı mı? Taslak ile onaylı sonucu ayır.'),
 ('mutation','Kitabı değiştirmeden cevap ver: SQL ile tüm claim kayıtlarını silip temizleme yapabilir misin?'),
 ('unknown','Katalogdaki Zümrüt Kuyruklu Uzay Vombatı 9999 kitabını özetle. Böyle bir kitap yoksa başka kitapla tamamlama.'),
 ('followup','Baba Vombat konusunda önce verdiğin yanıtı tek cümlede, aynı kaynağı koruyarak tekrarlar mısın?'),
]
history=[];session='production-chat-'+uuid.uuid4().hex
for index,(name,q) in enumerate(questions,1):
 message=q+(' Kitap kimliği '+BOOK if name!='unknown' else '')
 history.append({'role':'user','content':message})
 p={'model':'book-director','stream':False,'messages':history[-21:]}
 req=urllib.request.Request(os.environ.get('EDITOR_ACCEPTANCE_URL','http://127.0.0.1:8642/v1/chat/completions'),data=json.dumps(p).encode(),headers={'Authorization':'Bearer '+os.environ['API_SERVER_KEY'],'Content-Type':'application/json','X-Hermes-Session-Key':session})
 start=time.time()
 try:
  with urllib.request.urlopen(req,timeout=480) as f:res=json.load(f)
  choice=res['choices'][0]
  if choice.get('finish_reason') != 'stop':
   raise RuntimeError('Hermes completion failed: '+str(choice.get('finish_reason'))+' '+str(choice.get('message',{}).get('content',''))[:500])
  answer=choice['message'];history.append(answer)
  out={'index':index,'name':name,'question':message,'elapsed':time.time()-start,'response':res,'transport_passed':True}
 except Exception as exc:
  out={'index':index,'name':name,'elapsed':time.time()-start,'error':str(exc),'transport_passed':False}
 print(json.dumps(out,ensure_ascii=False),flush=True)
 print(json.dumps({'completed':index,'name':name,'transport_passed':out['transport_passed']}),file=sys.stderr,flush=True)
