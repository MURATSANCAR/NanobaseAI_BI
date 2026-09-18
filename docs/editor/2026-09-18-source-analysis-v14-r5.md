# V14-r5: kesilmiş model yanıtı ve bağımsız bölgesel OCR uzlaşması

18 Eylül 05:28 UTC. R4 teknik kabulden sonra açık işleri bekletmek yerine geliştirmeye devam edildi. Bu belge R5'in tam kitap kabulü değildir.

## Kod değişiklikleri

`analysis.py`: yalnız `finish_reason=length` olan model çağrısı aynı kaynak, istem, model ve seed ile bir kez daha yapılır. Çıktı bütçesi en fazla iki katına çıkar; gerçek tokenizer ile ölçülen bağlam sınırı ve 512 token pay korunur. Kısmi yanıt yeni isteme eklenmez. Tamamlanmış olumsuz/belirsiz karar olumlu sonuç aramak için tekrar edilmez. İlk kesilmiş çıktı, iki isteğin/yanıtın hashleri, değişmeyen mesaj hashleri, token kullanımı ve bitiş nedenleri kanıt olarak saklanır. İkinci deneme de kesilirse kabul verilmez; `semantic_acceptance.py` başarısız deneme izini de korur.

`ocr_vl.py` V2: temiz ve geometrisi bağlı PDF metni, Tesseract'ın iki kırpım okuması ve OCR-VL aynı sözcükleri ve noktalama konumlarını destekliyorsa tek bölgesel Paddle uyuşmazlığı aşılabilir. Apostrof ile çift tırnak birbirine çevrilmez; sözcük sınırları, olumsuzluk ve ham okuyucu metni korunur. Bozuk PDF, kararsız kırpım, noktalama farkı veya bağımsız destek eksikliği bu yeni yolu açmaz. Hangi okuyucunun geçersiz kılındığı kaydedilir. Kitaba/sayfaya/karakter adına özel yanıt yoktur.

Kaynak doğrulayıcı, bu yeni seçim yolundaki dört tam token akışını üretim seçim fonksiyonunu kullanmadan karşılaştırır. Türetilmiş analiz doğrulayıcı aynı girdili en fazla iki model denemesini, bağlam/çıktı sınırını ve yalnız kesilmiş yanıtın yeniden denenmesini denetler.

## Gerçek CPU API / PostgreSQL / GPU bileşen doğrulaması

Kaynak nesil R4 `08ca6877-6e30-4bb3-b1fa-767f048248e4`. Uygulama kayıtları yalnız okundu; kitap veya inceleme kararı yazımı 0. Yerel/sentetik test çalıştırılmadı.

- 10 ve32. sayfalarda gerçek kesilmiş ikinci atıf çağrıları, aynı girdi hashleriyle tekrar üretildi. İkisinde de ilk çağrı yeniden `length` oldu; tek ek deneme tamamlandı ve kaynak denetimi geçti. Kanıtlar CPU `evidence/bounded-model-retry-real-page-0010.json` ve `...0032.json`; log `evidence/bounded-retry-probe.log`. Bu yalnız iki gerçek bileşenin kabulüdür, bütün kitabın değil.
- 1.149 gerçek kaynak bölgesi API/bağımsız PG eşliğiyle incelendi. 210 OCR-VL ölçümü, mevcut13 OCR-VL seçimi korunarak sınandı. Son dosya hashinde9 ek bölge yeni güçlü uzlaşma kuralını karşıladı. Diğer incelemeler açık kaldı. Kanıt `evidence/ocr-native-crop-consensus-v2-final-real-book.json`; son kod SHA256 `0fa06d3baa2a005eb35947dd4aa181b27e9a86b20f1cfc41a90778e5ffbd1c24`. Önceki aday kanıtı ayrı dosyada korunur.

## Hazırlanan imajlar

CPU üzerinde mevcut R4 tabanlarından ağsız derlendi; bu satırların yazıldığı anda henüz canlıya alınmadı:

- API `nanobase-editor:source-analysis-v14-r5-20260918`: `sha256:5f7c9aa044619bc189ec3b016829b91d175d64fe7e7783810cc9bf42b8668d64`
- Document `nanobase-editor-document:source-analysis-v14-r5-20260918`: `sha256:12e6a914c7a2b58ab906fea82438db1390c04eb6db40d183f4c54ea8cf624928`
- `analysis.py`: `ef08da2339dba6f09a07c9a803468ea476d8ad0e4e966831af84e7a0a2cf0191`
- `semantic_acceptance.py`: `1dd31aa2254ae7fde29bb432f7b29ac67fbef48dac6398a6ec80ad6cdc0a36ba`

Build kanıtı `evidence/v14-r5-build-proof.json`. Model tekrar kodu paylaşılan çalışma alanında `d95d1a4` commitine girdi; içerik hashleri yukarıdadır. R5 yeni nesil ve yeni tam API/PG/atıf/paket/restore kabulünden geçmeden R4 başarısı R5'e taşınmaz. Genel figür kimliği, tam anlamsal kapsam ve üretim kabulü açık kalır.

## R5 canlı yayın

API/worker/parser/reread servisleri R5 ile yenilendi; R4 tamamlanmış nesli değişmedi. Gerçek47 backend dosyası eşliği tree SHA256 `cffbf1094e794a28c294fda9e3cbf5aefcc8f62934da490e59730875732824a5`,9 web kaynak/çıktı eşliği, API/PG hazır oluşu ve28 ACL kontrolü PASS. CPU `evidence/v14-r5-release.log`, `v14-r5-infrastructure.log`, `v14-r5-deployment.log`. Aktif QUEUED/RUNNING iş olmadığı gerçek DB'de doğrulandıktan sonra yayın yapıldı; geri dönüş için eski env/kod özel runtime dizininde korundu, kimlik bilgileri rapora çıkarılmadı. Yeni analiz ve qualifier için boş API18830/metrik19110, subnet78/79 ayrıldı. Yeni tam kitap kabulü henüz verilmedi.

## R5 yeni tam koşu başladı

İş `4b0895be-3038-4140-9dff-caa64bdfe177`, nesil `d9ff5c60-dd47-47cb-bf66-70a5cad59cb1`, kaynak atasından yalnız ölçüm yeniden kullanımı `08ca6877`. Öncelik gerçek düzeltme sayfaları10/32/1/8/20/21/26/33/40 ve regresyon29/38/6/45. CPU monitor126887 ve qualifier126888 ayrı süreçler; `evidence/source-analysis-v14-r5-start.json`, `evidence/v14-r5-qualification.log`. Eski nesil değiştirilmedi.

## Tam teknik kabul — 18 Eylül 06:08 UTC

R5 analiz işi tamamlandı; kaynak/amaç/kimlik/anlam kayıtları48/48. Gerçek API/PG, atıf bütünlüğü, yayın engelleri, aynı sürüm dosya hashleri ve izolasyon PASS. 370 sınırlı model çağrısı denetlendi; dördünde yalnız kesilme nedeniyle aynı girdili ek deneme doğrulandı. 61 sınırlı sentez iddiası,12 figür karşılaştırması,24 kaynak alt bölgesi kaydedildi. 61 sayısı R4'teki64 sayısından düşüktür; OCR iyileşmesi tek başına anlamsal kalite artışı veya tam kitap kabulü olarak yorumlanmaz.

Gerçek kaynak kalite tekrarı:1.149 bölge=896 anlaşma+253 inceleme; önceki887/262'ye göre9 ek güçlü destek. Kanıt `evidence/source-quality-triage-20260918T060816202995Z.json`. Bu tanılama dosyasındaki `synthesis_eligible_claims=0`, kaynak sayfası adaylarının kasıtlı kapalı bayrağını sayar; ayrı anlamsal incelemeden gelen61 uygun iddia için `evidence/source-analysis-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1.json` esas alınır.

Offline paket/import, gerçek dolu yedek, farklı Compose/ağ/portlarda restore, restore API/PG/atıf/yayın kontrolleri ve320/390/768/1440px mobil kabulü geçti. İş dizini `/data/nanobaseai/editor-qualifications/v14-r5-20260918/d9ff5c60`. Son cleanup raporu `evidence/v14-r5-qualification-network-cleanup.json`: returncode0, geçici proxy kaldırıldı, cleanup_errors boş. Hedef servisler kapandı; veri ve kanıtlar korundu. Genel figür kimliği,253 inceleme bölgesi ve tam anlamsal kabul hâlâ açık; bu sonuç üretim/hatasız kitap kabulü değildir.
