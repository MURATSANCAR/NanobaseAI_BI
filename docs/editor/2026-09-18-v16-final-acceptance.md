# V16-r5 yeni tam nesil kabulü — teknik kontroller ve iki soru geçti

Canlı sürüm `source-analysis-v16-r5-20260918`; iş `8032d654-bf44-4462-aca4-962d6f68d030`, nesil `116bb4a8-b7b5-45dd-9986-ac80fd706533`. Başlangıç kaydı `evidence/source-analysis-v16-r5-start.json`. Frozen kaynak commit1200bdd ve son R5 image/build proofları esas alınır; sonradan hazırlanan P5 yeniden işleme planı bu yayına dahil değildir.

Mevcut `monitor-parallel-ocr.py` PID1858000 çalışıyor; ikinci sayfa monitoru başlatılmadı. Final kabul wrapperı `runtime/editor-r5-final-acceptance.py`, mevcut monitor checkpointinin TECHNICAL_PASS sonucunu bekler; iş COMPLETED ve canlı R5 sürümü doğrulanmadan QA/model çağrısı başlamaz. Altı frozen verifier/helper hashinin final-main_sources manifestiyle eşliği de zorunludur.

Kabul dizini `evidence/v16-r5-final-acceptance-dd26ec79-46d6-48e6-8041-4af11d80967b`; üst log `evidence/v16-r5-final-acceptance-run.log`. Sıralı kontroller: source-analysis --fragments (gerçek API/PG), semantic-provenance, publication-gates ret yolları; ardından gerçek source-question-ui ile iki yeni soru ve 320/390/768/1440 piksel. UI betiği aktif iş/parse varsa başlatmaz, kaynak/review hashlerini korur ve soruları tek tek tamamlar. Başarısızlıkta zincir durur; cevap/veri elle değiştirilmez ve başarı aramak için yeniden soru üretilmez.

İlk kayıt sırasında ana iş devam ettiği için final sonuç bekleniyordu. Sonraki gerçek sonuçlar aşağıdadır; eski R7 veya bileşen PASS yeni tam neslin kabulü sayılmaz. Teknik kabul geçse dahi tam kitap, edebî kalite veya karakter kimliği için anlamsal kabul verilmez. Sonraki görev kapsamı bu yeni neslin dolu restore kabulünü de içerir.

## Tamamlanan gerçek R5 kabulü

Ana iş COMPLETED/NEEDS_REVIEW; mevcut monitor TECHNICAL_PASS,48/48 sayfa, failed_pages0. Frozen source-analysis --fragments ve API/PG: 1489 kaynak birimi,81chunk,774 inceleme gerektiren birim, işlenmemiş0/kısmi bağlam0;91 sınırlı uygun iddia. Bunlar benzersiz/doğru olay veya tam kitap başarısı sayıları değildir.758 bounded çağrı ve5length retry bütünlüğü doğrulandı. Semantic-provenance:35 sentez ifadesi,22 ek kaynak destekli iddia, atıf boşluğu0. Publication-gates ret kontrolleri geçti. Üçünün logları final kabul dizininde korunur.

Gerçek UI/PG iki soru kabulü PASS: `evidence/source-question-ui-2e0d2175-008e-444d-83e8-c2f1df69dbb0/verification.json`. İş `4bc30350-d3a3-4a9d-9288-18f4d095e9e9`: PARTIAL/2 destekli iddia; iş `b6e0e53e-5be8-4a64-ae66-6d654f0eacff`: INSUFFICIENT_EVIDENCE/0 iddia. Kaynak sorusu yalnız kısmi taslak; bütün kitabı cevaplamış sayılmaz. API/PG aynı cevap, kaynak bölgeleri/hashleri,3..1000karakter doğrulaması ve320/390/768/1440px taşma0 geçti. Korunan kaynak/review hashleri aynı; kabul kararı veya kitap verisi elle değiştirilmedi.

Ayrı bağımsız91pasaj API/PG/Qdrant kontrolü PASS: `evidence/source-preview-20260918T103039756197Z.json`. Ana teknik wrapper PASS; tüm kanıtlar semantic_acceptance=false olarak kalır. Kaynak incelemeleri, karakter kimliği ve edebî rubrik açık.

## R5 dolu yedek/ayrı restore — başladı

Yalnız bu yeni nesil ve iki yeni soru kimliği `evidence/source-preview-qualification-input-v16-r5.json` ile sabitlendi. Frozen qualifier `runtime/run-v16-r5-qualification.py` tek kopya, log `evidence/v16-r5-qualification.log`. Hedef `/data/nanobaseai/editor-qualifications/v16-r5-20260918/116bb4a8`.

Mevcut gerçek paket/import kanıtına bağlı hazırlık kaydı oluşturuldu; work/offline mevcut immutable release/offline paketine bağlandı. Qualifier'ın desteklediği resume yolu paketi REUSED işaretler, bütün dosya ve imaj hashlerini importta yeniden denetler. Önceden restore başlatılmış hedef yoktur; eski R7 backup veya soru kimlikleri kullanılmaz. Dinamik ağ planı gerçek Docker IPAM üzerinden seçilir; önceki ağ/containerlar silinmez. Ana Editör writerlarının tutarlı backup için kısa durdurulup açılması dışında GPU/model veya diğer uygulamalar yeniden başlatılmaz.

Restore, geri yüklenen API/PG/Qdrant, mobil ve cleanup sonucu henüz bekleniyor. Paket/QA PASS restore PASS yerine kullanılamaz.

## Restore tamamlandı; mobil verifier hatası genel kodda giderildi

Dolu backup, ayrı restore, geri yüklenen91pasaj/API/PG/Qdrant, kaynak/türetilmiş/provenance/publication kontrolleri geçti. İlk qualifier yalnız mobilde `UI span differs from API` hatası verdi: `.source-notes details:first` artık P5 etki kartını seçiyordu. Ürünün OCR metni değişmemişti. Genel verifier gerçek API kaydının `data-span-id` değerini hedefleyecek şekilde düzeltildi; frozen bundle/backend korunarak ayrı hedef betiğiyle aynı gerçek restore UI akışı yeniden çalıştırıldı. Eski qualifier FAILED kaydı silinmedi veya PASS'e çevrilmedi.

İlk tekrarın kendi koruma sorgusu tüm geçmiş JSON'u tek aggregate topladığı için restored PG backend'i signal9 aldı; bu hata da `evidence/v16-r5-restored-mobile-selector-proof.json` ile korundu. Genel `verify-restored-review-ui.py`, kayıt başına MD5 ardından küçük hash agregasyonu ve PG SELECT1/API hazır kapıları kullanır. Bütün geçmiş kayıt/review hashleri korunur; yalnız nesle daraltıldığı iddia edilmez. Ayrı hedefin mevcut PG/Qdrant/API/gateway containerları başlatılır; worker/model başlamaz ve finally hedef durdurulur. Bu araç ayrıca runfile ve UI sonuçlarının açık generation parametresiyle eşliğini zorunlu tutar. Son ek kapsam kapıları mevcut gerçek proof üzerinde ayrıca bağımsız kontrol edildi; aynı UI gereksiz tekrarlanmadı.

Gerçek düzeltme kabulü **PASS**: `evidence/restored-mobile-resume-f57d581a-09cb-401f-bc88-23145fccc205.json`. Dört genişlik320/390/768/1440, altı sekme, gerçek kaynak/atıf/region/OCR/fragment/context/semantic görünümü; yatay taşma yok. Bütün kayıt/review hashleri önce/sonra aynı, aktif iş0, model çağrısı0. Eski verifier SHA `dd2dba829fc6ca461a2ed7f4439f5ca14840a032fc85e2a56469920aea7f0bfb`; kabul edilen selector düzeltmesi SHA `9d66796ae3cf4e3f181d9e3517fb214107def7062fc7c27039b4640036fda073`.

Birleşik teknik kurulum kapanış kanıtı `evidence/v16-r5-qualified-resolution.json`,10:44:23 UTC **PASS**. Bu kayıt eski qualifier'ın mobil FAILED sonucunu ve düzeltme kanıtını birlikte taşır. Hedef servisler STOPPED; proxy/UFW temizliği hatasız, veri/kanıtlar korundu. Ana R5 tekrar gerçek `/v1/system` +PG ile infrastructure_ready=true, active_jobs0, iki tamamlanmış soru olarak doğrulandı. Ana post-restore release52backend/11web ve verify.py28ACL kontrolleri de geçti.

**Anlamsal kalite hâlâ kabul edilmedi.** [Gerçek içerik incelemesindeki yanlış PASS bulguları](2026-09-18-v16-semantic-content-review.md) teknik paket/restore/UI PASS ile kapanmaz. Yeni tam koşu bu belgeyle önerilmez; önce genel kök neden düzeltmesi ve gerçek başarısız örnek kabulü gerekir.
