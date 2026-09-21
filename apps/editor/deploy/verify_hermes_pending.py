"""Run inside editor-hermes, only after director phase starts on the isolated real run."""
import urllib.request,json,os,time
payload={'model':'book-director','stream':False,'messages':[
 {'role':'system','content':'Türkçe cevap ver. Bu salt okunur kontrol: analiz başlatma, kayıt yazma, cron veya bellek yazma. Kitap bilgisi için gerçek MCP okuma araçlarını kullan. Hazır olmayan çıktıyı eski nesilden veya genel bilgiden tamamlama.'},
 {'role':'user','content':'Dünyanın En Korkak Hayvanı kitabının son analizinin özeti hazır mı? Hazırsa özeti göster; hazır değilse açıkça söyle. Kitap kimliği d2d4a6f1-e5b3-4415-9d68-48f8fe768c03.'}]}
r=urllib.request.Request('http://127.0.0.1:8642/v1/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+os.environ['API_SERVER_KEY'],'Content-Type':'application/json'})
t=time.time()
with urllib.request.urlopen(r,timeout=900) as res:out=json.load(res)
print(json.dumps({'elapsed':time.time()-t,'request':payload,'response':out},ensure_ascii=False))
