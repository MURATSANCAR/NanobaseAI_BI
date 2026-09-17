# 18 Eylül — paralel kimlik ve anlamsal analiz geliştirmesi

Kullanıcı figür–karakter kimliği ve anlamsal kabul işlerinin ayrı paralel yürütülmesini istedi. Kaynak metni, karakter cevabı ve eski model sonuçları elle değiştirilmez. Aynı depoda bağımsız Editör uygulaması kuralı korunur.

## Doğrulanan web düzeltmesi

Seçilmiş PaddleOCR-VL metni kaynak ekranında okuyucu kökeni olmadan görünüyordu. `frontend/src/main.tsx` seçilmiş metni, korunmuş ilk tam sayfa okumasını, model adını ve destekleyen okuyucuları gösterir. Optik uyuşma olay/konuşmacı/karakter onayı olarak sunulmaz.

Sunucuda TypeScript/Vite derlemesi tamamlandı; yalnız gateway `nanobase-editor-web:ocr-provenance-v12-20260918` imajıyla yenilendi. API/worker R9 koşusu kesilmedi. `verify-release.py` çalışan backendin 41 dosyasını ve webin 9 kaynak dosyası/çıktı hashlerini doğruladı. Gerçek R9 API ve Chrome akışı, sayfa 5 seçilmiş OCR metni ve sayfa 29/38 inceleme adaylarıyla 320/390/768/1440 pikselde geçti; yatay taşma yok. Kanıt: sunucuda `evidence/review-ui-ocr-provenance-v12/verification.json`. Bu anlamsal kabul değildir.

## Kodda giderilen akış boşlukları

- `figure_identity.py`: açık metin atfı, aynı balon ve tek kuyruk sinyaliyle yerel kimlik bağı; isim verilmeden gerçek figür kırpımlarının çapraz sayfa karşılaştırılması. Görsel benzerlik tek başına kimlik değildir. Ayrı değişmez `figure_identity` ve çift başına `figure_comparisons` kayıtları; ham kırpım/hash/model kökeni, açık aday limiti ve kalan çift sayısı.
- `semantic_acceptance.py`: mevcut alıntı/span kapısını yeniden denetleyen, Qwen'e ayrı çağrı yapan sayfa denetimi. Anlam, fail, konuşmacı, olumsuzluk, anlatı kipi ve sayfa türü ayrı değerlendirilir. Aynı modelin ikinci görüşü bağımsız kaynak veya insan kabulü değildir.
- Uygun iddialardan kaynaklı kısmi sahne/ilişki/tema/özet taslağı; her ifade için yeniden destek kontrolü. Sayfa bazlı `semantic_reviews`, kitap bazlı `semantic_synthesis` kayıtları. Önceki adaylar ve kaynaklar korunur. Sayfa kimliği içeren iddia hashleri çakışmayı önler; kesilmiş model çıktısı başarı sayılmaz.
- `source_pipeline.py`: kaynak sayfaları tamamlanınca kimlik ve anlamsal kolları paralel yürütür. İki kol tamamlanmadan iş tamamlandı sayılmaz; nesil yine inceleme gerektirebilir. Sürüm `source-spans-v12`; yeni nesil gerekir.
- `book_api.py`: yeni kayıtların kitap yetkisi ve sayfalama üzerinden okunması. `verify-source-analysis.py`: gerçek API/bağımsız PostgreSQL tam kayıt eşliği, girdi hashleri, kaynak kapıları ve kırpım bütünlüğü kontrolü.

## Kabul sınırı

Bu belge hazırlanırken yeni backend kodunun tam yeni nesil kabulü henüz yapılmadı. R9 kaynak koşusu devam ediyor; 16 tamamlanan sayfanın teknik denetimi geçti, başarısız sayfa yok. 29. sayfada figüre uzanan kuyruk var fakat kaynaklı karakter adı yok; UNKNOWN kaldırılmadı. Üretim/insan editör kabulü, bütün kitap anlamsal doğruluğu ve P0–P7 kapanışı iddia edilmez.

Müşteri GPU kurulum/paket eksikleri ayrı [kurulum kaydında](2026-09-18-deployment-gaps.md) izlenir. Kod incelemesi veya kaynak hash eşliği, müşteri offline/restore kabulü yerine geçmez.

## V12-r1 dağıtımı ve gerçek bileşen sonuçları

Backend imajı `nanobase-editor:source-analysis-v12-r1-20260918`. Gerçek çalışan 43 dosyanın checkout eşliği geçti: `d6c3a68a40911519ddfe16677c03abe347c4bc1e3adfeaa862d55f276d5884c9`. İlk kopyalama denemesinde root sahipli lock dosyaları izin hatası verdi; o aşamadaki eşlik denetimi başarısız oldu. Yetkili kopyalama ve gerçek yeni imaj dağıtımından sonra aynı denetim geçti; ilk başarısızlık başarı sayılmadı.

R9 koşusu API üzerinden iptal edildi; 22 sayfanın teknik denetimi geçti, başarısız sayfa yok. Kaynak/aday kayıtları silinmedi. V12 nesil `2d774b82-e04f-45a3-92fc-eadaa8a37934`, iş `791de2a0-a440-419c-8db4-2095405eed23`; kanıt `evidence/source-analysis-v12-r1-start.json`. Salt okunur sayfa izleyicisi yeni işi takip eder.

Gerçek API ve bağımsız PostgreSQL eşliğiyle, uygulama kayıtlarına yazmadan:

- S7: iki adayın ayrı model kontrolü olumlu olsa da açık fail bağı eksik olduğu için sentez engellendi; iki aday alıntı kapısında kaldı.
- S38: dört kaynaklı adaydan dört sentez önerisi üretildi. İki sahne taslağı desteklendi; kaynak dışı amaç ekleme ve emirden genel zorunluluk çıkarma içeren iki ifade reddedildi. `evidence/semantic-live-component-page0007.jsonl` ve `page0038.jsonl`.
- Kimlik bileşeni: 460 API/PG kaydı ve 19 tamamlanmış sayfa eşliği; doğrulanmış yerel kimlik 0. Gerçek iki figür kırpımı Qwen tarafından 108,681 saniyede DIFFERENT olarak değerlendirildi; isim verilmedi. `evidence/figure-identity-r9-api-pg.json`, `figure-identity-r9-real-pair.json`.

Mevcut CPU sunucuda yeni preflight geçti (96 mantıksal CPU; hata listesi boş). Bu başka müşteri ağının veya GPU offline restore kabulü değildir.

## V12 arayüzü ve izleme toparlanması

`nanobase-editor-web:source-analysis-v12-20260918` kaynak ekranına gerçek kimlik/anlam kayıtlarını, kitap yorumuna kaynak sayfalarına bağlı kısmi sentez kartlarını ekler. Sunucuda derleme ve kaynak/çıktı hashleri geçti; gerçek OCR kayıtlarıyla dört genişlik regresyonu geçti. Yeni dolu kimlik/sentez kartlarının kabulü, koşu bu kayıtları oluşturunca `EDITOR_VERIFY_SEMANTIC=1` ile ayrıca yapılmalıdır; boş kart kontrolü dolu akış kabulü değildir.

Gateway yenilenirken salt okunur kontrol betiğinde iki ConnectionRefused hatası oluştu. Analiz işi devam etti. `verify-parallel-ocr.py` yalnız geçici ulaşım hatalarına sınırlı GET tekrarı ekler; `monitor-parallel-ocr.py` mevcut durumu ve deneme geçmişini koruyarak yeniden başlar, gerçek assertion hatasını tekrar deneyerek gizlemez. S1/s2 eski hata logları korundu; gerçek tekrar kontrolleri geçti. Yeni koşunun ilk20 sayfası teknik denetimde20 geçti/0 başarısız; semantik kabul değildir.

Harici model uygulama paketi `/data/nanobaseai/editor-qualifications/source-analysis-v12-r1-external-20260918` üretildi. Qwen/OCR GPU imaj ve ağırlıkları dahil değildir; müşteri endpointleri açık bağımlılıktır. Import ve ayrı restore sonucu ayrıca kaydedilecektir.

Git: geliştirme yerel `main`e `d446842` ile alındı. Dal denetiminde bulunan dört GPU/VPN dokümantasyon commit'i `6ac9302` merge'üyle main'e taşındı; günlükte iki tarafın kayıtları korundu. Başka aktif worktree'nin kullandığı VPN dalı Git tarafından silinemedi; main dışında commit kalmadı. HTTPS GitHub kimliği bulunmadığı için `git push origin main` başarısız; uzak yayın yapılmış sayılmaz.
