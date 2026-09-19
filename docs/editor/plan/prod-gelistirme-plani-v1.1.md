<!-- Kullanıcının sağladığı özgün plan belgesinin metin kopyası. Kaynak: Kitap_Analiz_Sistemi_Prod_Gelistirme_Plani-v1.1.docx, SHA-256 7e36c21343abadacbb7c1f62276bf9ac7c20d5eb3b51030695f092690b898976. İçerik değiştirilmedi; yalnız biçim Markdown'a çevrildi, şekiller yer tutucuyla gösterildi. -->

# Yayınevi kitap analiz sistemi doğrulama ve pilot geliştirme planı

Yerel kitap analizi için kapsam kararları teknik akış ve kabul koşulları

Murat Sancar ve geliştirme ekibi için hazırlanmıştır. Plan sürümü 1.1. Tarih 16 Eylül 2026.

Ürün, Türkçe resimli çocuk kitaplarını kaynaklarıyla işleyen; karakterleri, olayları ve sınırlı edebî yorumları kaydeden; atıflı cevaplar ve editör incelemesi sunan yerel bir sistem olarak geliştirilecektir. İlk çalışma evresi, yaklaşık iki haftalık efor ufkuyla planlanan doğrulama evresidir. Takvim başlangıcı ve üretim teslim tarihi henüz atanmaz.

Teslim tarihi; doğrulama evresinin ölçümleri, kalan işlerin bağımlılıkları, gerçek ekip kapasitesi ve ayrılmış editör saatleri birlikte değerlendirildikten sonra belirlenir. Önceki 20 haftalık üretim takvimi bu sürümle yürürlükten kaldırılmıştır. Model adı veya genel model karşılaştırması teslim ölçütü değildir.

PostgreSQL ana kayıt sistemi, Qdrant yeniden üretilebilir arama indeksi, Python ve LangGraph işleme altyapısı olarak korunur. Belge işleme Docling, Poppler, Tesseract ve yerel görsel model üzerinden yürür. Geliştirme tek depoda ve birkaç modülde yapılır. Model, çalıştırıcı ve nicemleme birlikte sınanır; uygunluğu gösterilmeyen konfigürasyona sonraki işler bağlanmaz.

## Bölümler

Başlıklara tıklayarak ilgili bölüme geçebilirsiniz. Word gezinme bölmesi de bölüm başlıklarını gösterir.

1 Bağlayıcı kapsam ve değişiklik kararları

2 Doğrulama evresi ve çıkış koşulları

3 Teknoloji yerleşimi ve sahiplik sınırları

4 Kitabın uçtan uca işlenmesi

5 Dosya kabulü ve kaynak konumları

6 Metin OCR ve görsel kapsam

7 Görsellerin hikâye bütünlüğü içinde sunulması

8 Pilot veri modeli

9 İddia zaman ve bakış açısı sözleşmesi

10 Analiz görevleri ve sınırlı edebî değerlendirme

11 İlişki sözlüğü ve grafik kayıtları

12 Kanıt kontrolü ve soru cevap

13 Sürümler indeks ve editör düzeltmeleri

14 İş kuyruğu checkpoint ve kaynak paylaşımı

15 Model konfigürasyonu süre ve maliyet ölçümü

16 Kalite ölçümü ve editör bütçesi

17 Referans kitaptan kabul senaryoları

18 Bağımlılıklı geliştirme işleri

19 Kod modülleri ve pilot API sözleşmesi

20 Yerel işletim erişim ve kullanım politikaları

21 Pilot kabulü üretim kararı ve sonraki kapsam

22 Teknik kaynaklar

## 1 Bağlayıcı kapsam ve değişiklik kararları

İlk pilot tek yayınevi, Türkçe resimli çocuk kitabı ve iç baskı PDF profiliyle sınırlıdır. Üç referans kitap kullanılacaktır. Ekrana Sığmayan Macera ilk kitaptır; diğer iki eser yayınevi editörüyle seçilir. Sayfa ve dosya boyutu tavanı doğrulama evresinde ölçülerek yapılandırmaya yazılır. Tavanın dışındaki dosya destekleniyor gibi işleme alınmaz.

| Karar alanı | Pilot kapsamı | Sonraya bırakılan |
|---|---|---|
| Kaynak | İç baskı PDF, bütün sayfaların manifesti | EPUB ve DOCX işleme |
| Görseller | Kitaptan çıkarılan görsellerin sahne ve olay bağlamında ekranda gösterimi | Yeni görsel üretimi ve otomatik yeniden çizim |
| Bilgi | Karakter kartları, olay ve durum, kaynaklı ilişkiler | Seri evreni ve çeviri karşılaştırması |
| Edebî analiz | Üç kitapta sınırlı karakter değişimi, duygu ve tema örnekleri | Tam edebî motor ve kapsamlı otomatik bütünlük taraması |
| Soru cevap | Yetkili kitap kapsamında atıflı cevap ve açık belirsizlik | Bütün katalog üzerinde sınırsız analiz |
| Editör | Kaynak görüntüleme, kabul, ret ve düzeltme kuyruğu | Gelişmiş grafik gezgini |
| Kurum | Kullanıcı, kitap ve rol erişimi | Çok kiracılı ürün yönetimi |
| Teslimat | Ölçüme dayalı pilot ve ardından üretim kararı | Önceden verilmiş üretim tarihi |

Grafik ilişkileri pilotta veri olarak bulunur; gezgin arayüzünün ertelenmesi bu kayıtları kaldırmaz. Tema ve karakter değişimi, kanıtlı örnekler üzerinden insan incelemesine sunulur. Bu örnekler bütün kitaplarda bütün edebî sorunların bulunacağı taahhüdüne dönüşmez.

Kitabın öğrenilmesi; kaynak, karakter, olay, iddia ve arama kayıtlarından kalıcı hafıza oluşturulmasıdır. Kitap başına model ağırlığı eğitimi yapılmaz. Gelecekte eğitim kullanımı ayrı politika ve veri değerlendirmesi gerektirir.

## 2 Doğrulama evresi ve çıkış koşulları

Doğrulama evresi yaklaşık iki haftalık planlama ufkuna sahiptir; bu bir tamamlanma garantisi değildir. Ortama erişim, üç kitabın seçimi ve editörün ayrılan saati başlangıç bağımlılıklarıdır. Beklemeler aktif geliştirme eforundan ayrı kaydedilir. Bu evre sonunda çalışan teknik denemeler ve ölçüm raporları bulunmalıdır.

| İş | Yapılacak ölçüm veya kontrol | Teslim edilecek kanıt |
|---|---|---|
| Ortam envanteri | Tahsisli CPU, RAM, GPU, disk, ağ ve mevcut servis yükü | Host ve kaynak paylaşımı manifesti |
| Kaynak kabulü | Dosya boyutu, hash, sayfa yapısı ve render | Geçerli kaynak manifesti ve hata örnekleri |
| Model uygunluğu | Model, tokenizer, çalıştırıcı, nicemleme, bağlam, görsel ayarı | Tekrarlanabilir konfigürasyon ve temel görev sonuçları |
| Model yerleşimi | Tepe RAM/VRAM, model yükleme ve eşzamanlılık | Bellek ve kapasite raporu |
| Uçtan uca kitap | Ayrıştırma, OCR, görsel okuma, çıkarım, doğrulama, indeks ve cevap | Aşama süreleri, toplam duvar süresi ve iş sonucu |
| Ortak host yükü | Legal/BI başlangıç gecikmesi ve kitap işi eklenmiş durum | Önce ve birlikte yük karşılaştırması |
| Editör emeği | Okuma, örnek işaretleme, değerlendirme ve anlaşmazlık çözümü | Dakika/örnek ve saat/kitap ölçümleri |
| Kalan iş | Bağımlılıklar, mevcut kod ve ölçülen darboğazlar | Tahmin aralıklı iş listesi ve ekip kapasitesi |

Yorumlarda geçen 96 çekirdek, 251 GB RAM ve :8076 bilgileri bu ürün için doğrulanmış tahsis sayılmaz. Envanterde gerçek host, servis sahibi, kullanım penceresi ve kaynak sınırı kaydedilir. Mevcut servise kitap yükü yönlendirmek için ortak host ölçümü tamamlanmalıdır. Ayrı port veya ayrı kuyruk fiziksel kaynak izolasyonu değildir.

Model denemesi Türkçe metni, bozuk yazı bölgelerini, görsel balonu, olay/plan/şaka ayrımını, kaynak referansını ve kesilmiş çıktı davranışını kapsar. Başarısızlıkta hangi bileşenin değiştirilmesi gerektiği kaydedilir: ayrıştırıcı, prompt, model, çalıştırıcı, nicemleme veya kaynak bütçesi. API ve kaynak işleri konfigürasyondan bağımsız geliştirilebilir; başarısız modelin yeterli olduğu varsayımıyla analiz işleri kapatılmaz.

Çıkış dosyası; kaynak manifestleri, model konfigürasyonu, ilk uçtan uca çalışma kaydı, B senaryolarının gerçekleşen sonuçları, ortak yük raporu, editör kapasitesi ve kalan iş listesi içerir. Bunlar tamamlanınca pilot kapsamı, hizmet hedefleri ve teslim tahmini birlikte kesinleştirilir. Donanım ihtiyacı çıkarsa tahsis, satın alma veya kiralama bağımlılığı ayrı kalem olur; kurum dışına içerik çıkmama koşulu korunur.

## 3 Teknoloji yerleşimi ve sahiplik sınırları

| Bileşen | Çalıştığı yer | Sorumluluk |
|---|---|---|
| Python, FastAPI, Pydantic | Uygulama süreci | Yetkili API, doğrulanmış istek ve çıktı sözleşmeleri |
| PostgreSQL | Veri süreci | Kaynak, karakter, olay, kanıt, inceleme, sürüm, job ve outbox |
| LangGraph | Analiz işçisi | Analiz adımları, sınırlı yeniden okuma ve checkpoint |
| Docling ve Poppler | Belge işçisi | Yapı, okuma sırası, metin çıkarımı, render ve karşılaştırma |
| Tesseract ve Türkçe dil verisi | Belge işçisi | Görünür yazı bölgelerinde OCR ve konumlu metin |
| Yerel metin ve görsel model | Ayrılmış veya sınırlandırılmış model süreci | Sahne, kimlik, olay, sınırlı yorum ve cevap |
| Yerel embedding ve reranker | Arama işleme süreci | Pasaj temsili ve aday sıralama |
| Qdrant ve yerel BM25 | Arama süreci | Filtreli dense/sparse arama |
| React, TypeScript, PDF.js | Editör tarayıcısı | Kaynak, karakter, bulgu ve inceleme ekranları |
| Docker Compose ve yerel izleme | Kurum altyapısı | Kurulum, süreçler, ölçümler, alarmlar ve yedekleme |

İlk ana model adayı Qwen3.8-27B'dir. Model kartı, seçilen corpus üzerinde ölçülmüş başarı veya çalıştırıcı uyumu yerine geçmez [S1]. vLLM GPU çalışma yolu için, llama.cpp desteklenen CPU konfigürasyonu için uygunluk denemesine girer. Her yolun gerçek model desteği sınanır. Ana model, embedding ve reranker ayrı konfigürasyon alanlarıdır; servis endpoint ve takma adları ortam ayarlarından alınır.

Önceki Qwen3-Embedding-4B ve Qwen3-Reranker-0.6B adayları karşılaştırma başlangıcı olarak kalır [S2, S3]. Embedding için 4B boyut zorunluluğu yoktur. Daha küçük adayın kaynak getirme başarısı ve kaynak tüketimi ölçülmeden otomatik geçiş yapılmaz. Qdrant mimaride korunur; ilk kaynağın okunabildiği gösterildikten sonra arama iş paketinde bağlanır. Bu aşamaya kadar tam bağlam denemesiyle kaynak ve model hataları ayrıştırılabilir.

Job sahipliği PostgreSQL iş tablosunda, grafın devam noktası LangGraph checkpointer'da, indeks teslimi outbox'ta tutulur. İşin uygulama sonucu ve etkin analiz sürümü PostgreSQL'dedir. Aynı graf adımının ikinci bağımsız durum makinesi kurulmaz. Her bileşenin tek sorumluluğu entegrasyon testinde gösterilir.

## 4 Kitabın uçtan uca işlenmesi

*[Şekil — özgün belgede görsel]*

Şekil 1 Kitabın işlenmesi ve analiz sürümünün hazırlanması

Yetkili yükleme kaynak sürümünü oluşturur. Belge yapısı ve sayfa görüntüleri hazırlanır. Resimli çocuk kitabı profilinde bütün sayfalar görsel kapsam denetimine girer. Metin katmanı, OCR ve görsel kayıtlar aynı kaynak konumlarına bağlanır. Anlatı, etkinlik ve açıklayıcı ekler ayrılır.

Sahne çıkarımı, karakter eşleştirme ve olay birleştirme tamamlanınca sınırlı kitap/karakter sentezi yapılır. İddiaların kaynağı ve bağlamı kontrol edilir; belirsizlikler editör kuyruğuna düşer. Arama indeksi ve yapılandırılmış kayıtlar aynı generation altında hazırlanır. Uygunluk kontrollerinden geçen sürüm kullanıcıya açılır.

Kullanıcı ekranında işleme durumu, kaynak kapsamı ve editör inceleme durumu üç ayrı alandır. Örneğin işleme tamamlanmış olabilir; buna rağmen okunamayan bir balon veya incelenmemiş tema yorumu bulunabilir. Kaynak kapsamı yüzde 100 görünmesi, bütün içeriğin doğru anlaşıldığı veya editörce onaylandığı anlamına gelmez. Kritik okunamayan kaynakta tam kapsamlı rapor etkinleştirilmez.

## 5 Dosya kabulü ve kaynak konumları

Yükleme isteği kimliği doğrulanmış kullanıcıdan gelir. API kurum ve kitap yetkisini denetler; sunucu tarafından üretilmiş bir yükleme kimliği verir. Dosya önce geçici alana yazılır. Dosya türü yalnız uzantıdan değil içerikten doğrulanır. Boyut, sayfa sayısı, ayrıştırma süresi, arşiv açılma sınırı ve şifreli PDF davranışı yapılandırılır. Desteklenmeyen dosya açık hata koduyla reddedilir.

SHA-256 hash dosya tamamlandıktan sonra hesaplanır. Aynı kurum içindeki aynı içerik fiziksel olarak tekrar saklanmayabilir; buna rağmen kitap, yükleme ve izin kayıtları ayrı kalır. Kurumlar arası dedup bilgisi kullanıcıya açıklanmaz. Yükleme isteği yeniden geldiğinde Idempotency-Key aynı sonucu döndürür. Yarım yükleme yeni kitap sürümü olarak etkinleşmez.

Özgün dosya tenant/work/edition/content-version altında içerik hash'i ile adreslenir. Dosya yolu kullanıcı metninden oluşturulmaz. Ham dosya üzerine OCR veya editör düzeltmesi yazılmaz. Kaynak dosya, render, OCR, normalize metin ve diğer türevler ayrı artifact kayıtlarıdır. Her artifact üretim aracı, sürümü, girdi hash'i ve oluşturulma zamanını taşır.

PDF sayfa sırası ile basılı sayfa etiketi farklı alanlardır. Birinci PDF sayfasına basılı sayfa 1 denmez. PDF koordinatları normalize edilmiş x/y/width/height ve kullanılan dönüş/ölçek bilgisiyle saklanır.

Kabul testi; yükleme ortasında kesinti, aynı dosyanın tekrarı, yanlış uzantı, bozuk PDF, şifreli PDF ve kurum dışı kitap kimliği denemelerini içerir. Başarılı kayıt, özgün dosyanın yeniden okunabildiği ve hash'inin doğrulandığı noktada tamamlanmış sayılır.

| Hata senaryosu | Beklenen davranış |
|---|---|
| Sıfır bayt dosya | EMPTY_UPLOAD; ayrıştırma başlamaz ve içerik sürümü etkinleşmez. |
| Yarım yükleme | INCOMPLETE_UPLOAD; tamamlandı onayı verilmez, yeniden deneme aynı oturuma bağlanır. |
| Sıfır sayfa PDF | NO_PAGES; kaynak kabulü reddedilir. |
| Şifreli PDF | ENCRYPTED_SOURCE; destek politikası uygulanır, okunmuş sayılmaz. |
| Bozuk PDF | INVALID_PDF; hata nedeni ve aşaması kaydedilir. |
| Render başarısızlığı | SOURCE_RENDER_FAILED; ilgili sayfa incelemeye ayrılır. |
| Tavan dışı kaynak | SOURCE_LIMIT_EXCEEDED; sayfa/boyut sınırı açıkça bildirilir. |

Bu oturumun referansı Ekrana Sığmayan Macera İç Baskı PDF'sidir: 19.806.912 bayt, 48 sayfa. Kaynak SHA-256 değeri 94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50 olarak kaydedilmiştir. Başka bir yüklemedeki sıfır bayt hatası bu kaynağın yerine geçirilmez. Her test hash ve dosya kimliğiyle bağlanır.

## 6 Metin OCR ve görsel kapsam

Her sayfa için belge işçisi blokları, mevcut metni, görüntüleri ve geometrik yerleşimi çıkarır. Ölçümler; görünür metin bölgesine göre metin kapsamı, özel Unicode karakter yoğunluğu, anlamsız karakter dizileri, tekrar eden aynı konumdaki bloklar, okuma sırası ve dipnot bağlantılarını kapsar. İki ayrıştırıcının farkı kalite sinyalidir; farkın varlığı tek başına hangi çıktının doğru olduğunu göstermez.

Temiz metin doğrudan korunur. Metin bulunmayan ancak görünür yazı içeren bölge OCR'a gönderilir. Görsel ağırlıklı bölgeler ayrıca görsel modele gider. Türkçe OCR için başlangıçta Tesseract tur dil verisi kullanılır. Render çözünürlüğü örnek belgelerle seçilir; gerektiğinde yalnız sorunlu bölgede daha yüksek çözünürlük denenir. Sabit 600 DPI bütün arşiv için zorunlu tutulmaz.

Normalize işlemleri ayrı bir katmanda yapılır: satır sonu bölünmüş sözcükleri birleştirme, Unicode normalizasyonu, başlık ve sayfa numaralarını sınıflandırma, yinelenen PDF bloklarını koordinatlarıyla ayıklama. Her dönüşüm özgün metne geri eşleme taşır. Karakter isimleri, büyük/küçük harf ve konuşma üslubu geri döndürülemez şekilde sadeleştirilmez.

Görsel modelden görünür kişiler, nesneler, eylemler, konuşma balonları, görünür yazı ve metinle bağlantı istenir. Bir çizimdeki kişinin kimliği kanıtlanamıyorsa visual_entity geçici kimliği verilir. Yakın sayfa ve karakter görünüm kayıtlarıyla eşleme yapılır; kıyafet değişimi tek başına yeni karakter kanıtı değildir. Hayal balonu, örnek resim veya geleceğe ilişkin çizim otomatik gerçekleşmiş olaya çevrilmez.

Ekrana Sığmayan Macera testinde 44–48. sayfaların bozuk metni görünür kaynaktan düzeltilmelidir. 29. sayfadaki balon, 28. sayfadaki aynı konuşmayla eşleştirilerek tek konuşma olayına iki kaynak olarak bağlanmalıdır. Görselde yinelenen cümle yeni olay veya tekrar eden anlatım kusuru sayılmamalıdır.

Her sayfa PROCESSED_TEXT, PROCESSED_IMAGE, PROCESSED_MIXED, VERIFIED_EMPTY veya NEEDS_REVIEW olarak sonuçlanır. İçerik barındıran sayfa sessizce atlanamaz. Yüzde 100 sayfa muhasebesi, okuma doğruluğundan ayrı raporlanır. Kritik sayfa NEEDS_REVIEW iken tam kapsamlı kitap raporu yayımlanmaz.

Metin katmanı dolu diye OCR ve görsel denetim atlanmaz. Görünür sayfayla katman uyuşmazlığı ayrı bir kalite sinyalidir. Tesseract tek başına balonun konuşmacısını veya bir görselin hayal sahnesi olduğunu belirleyen otorite değildir. VLM transkripsiyonu da doğrulanmış özgün metin sayılmaz. Uyuşmayan okumalar aynı kaynak bölgesinde adaylar olarak korunur; onarım veya editör incelemesiyle çözülür.

## 7 Görsellerin hikâye bütünlüğü içinde sunulması

Kitaptaki görseller pilotta ekrana çıkarılacaktır. Gösterim; görselin kaynağını, bağlı olduğu sahneyi, görünen kişi/nesneleri ve olayın anlatı modunu birlikte korur. Aynı sahnedeki metin ve görseller tek inceleme bağlamında açılır. Bu özellik mevcut kitap görsellerinin çıkarımı ve ilişkilendirilmesidir; yeni illüstrasyon üretimi ayrı ürün kararıdır.

Önce özgün PDF içindeki görsel nesneleri ve sayfa yerleşimi çıkarılır. Bir illüstrasyon birden fazla nesneden, vektör çizgiden veya metin/görsel katmanından oluşuyorsa yalnız gömülü resim dosyası yeterli sayılmaz. Poppler sayfa render'ı ve kayıtlı bölge koordinatlarından görünür kompozisyon korunur. Kaynak sayfa her zaman açılabilir. OCR veya model yazısı özgün illüstrasyonun üzerine kalıcı olarak işlenmez.

| Kayıt | İçerik ve amaç |
|---|---|
| visual_asset | Kaynak sürümü, dosya/render hash'i, depolama konumu ve özgün çözünürlük |
| visual_occurrence | Sayfa, bbox, okuma sırası ve karşılıklı sayfa/grup bağlantısı |
| visual_scene_link | Bağlı sahne/olay, bağlantı rolü, kaynak, eşleme durumu ve editör kararı |
| visual_entities | Görünen geçici veya eşlenmiş karakter, nesne ve mekân kayıtları |
| visual_text | Balon/yazı bölgesi, okuma adayları ve bağlı konuşma olayı |

Aynı resim kitapta iki yerde kullanıldığında dosya tekilleştirilebilir; iki görünümün sayfa ve anlatı bağlamı korunur. Bir görsel birden fazla sahneye bağlanabilir. Aynı sahnenin birden fazla görseli olabilir. Yakın sayfada bulunmak tek başına doğru sahne eşlemesi değildir; diyalog, karakter, eylem ve sayfa kompozisyonu birlikte incelenir.

Varsayılan ekran sırası kitabın anlatı sırasıdır. Hikâye zamanı farklıysa ayrıca etiketlenir; geri dönüşler veya gelecek planları gerçekleşmiş ana olay sırasına sessizce taşınmaz. Sahne kartında kısa kaynaklı açıklama, ilgili metin, görseller, karakterler ve ACTUAL/PLANNED/HYPOTHETICAL/JOKE gibi mod görünür. Eksik veya belirsiz görsel bağı 'eşleştirme gerekli' durumundadır; sahneye kesin bağlanmaz.

Editör, sahnenin metnini ve görsellerini yan yana inceleyebilir, görseli büyütebilir, özgün sayfaya dönebilir, önceki/sonraki sahneye geçebilir ve yanlış bağı değiştirebilir. Karşılıklı iki sayfaya yayılan kompozisyon gerektiğinde birlikte gösterilir. Küçük önizleme kaynak yerine geçmez; tam sayfa ve ilgili bölge erişimi korunur.

Metinle görsel farklı bilgi veriyorsa iki kaynak ayrı tutulur. Sistem uyuşmazlık adayı gösterebilir; çizimin üslubu, bakış açısı veya hayal sahnesi otomatik editoryal hata sayılmaz. Bu ekrandaki insan incelemesi pilot kapsamındadır; bütün kitaplarda otomatik görsel tutarsızlık tespiti sonraki kapsamdadır.

| Görsel kabul vakası | Beklenen sonuç |
|---|---|
| V01 Kaynak görünürlüğü | Her gösterilen görsel doğru kitap/sürüm/sayfa/bölgeye açılır. |
| V02 Görsel sayfa kapsamı | Metni az olan sayfa boş sayılmaz; görsel ekran kaydı bulunur. |
| V03 Balon ve metin | 29. sayfadaki balon, 28. sayfadaki aynı konuşmayla bağlanır; iki olay oluşmaz. |
| V04 Hayal ve plan | Planlanan/hayal edilen görsel, gerçekleşmiş olay gibi gösterilmez. |
| V05 Sayfa kompozisyonu | Vektör/çok nesneli veya karşılıklı sayfa görseli anlamı bozacak biçimde parçalanmaz. |
| V06 Belirsiz eşleme | Görseldeki kişi veya sahne belirsizse aday durumu görünür; kesin kimlik uydurulmaz. |
| V07 Tekrar ve düzeltme | Aynı görselin farklı kullanımları korunur; editör bağı düzeltince sahne görünümü güncellenir. |
| V08 Yetki ve sürüm | Görsel endpoint ve önizleme cache'i kitap yetkisini ve aktif sürümü korur. |

V01–V08 test tanımlarıdır. Yeni sürüm veya görsel eşlemesi değiştiğinde ilgili sahne görünümü, görsel metin bağlantısı ve etkilenen cevap bağlamı yeniden hesaplanır. Eski raporun görsel referansları üretildiği sürüme bağlı kalır.

## 8 Pilot veri modeli

Kaynaklar, çıkarımlar ve editör kararları birbirinden ayrılır. Zorunlu kapsam anahtarları kullanıcı/kitap erişimi, eser, içerik sürümü ve analiz generation kimliğidir. Kurum kimliği gelecekteki taşıma için korunabilir; tek başına yetkilendirme mekanizması sayılmaz. Pilot için çok kiracılı yönetim ekranı ve kiracı yaşam döngüsü yapılmaz.

| Kayıt grubu | Temel sorumluluk |
|---|---|
| Eser baskı ve içerik sürümü | Dosyanın hangi kitaba ve sürüme ait olduğu |
| Artifact sayfa blok ve kaynak aralığı | Özgün dosya, render, metin ve bbox/offset eşlemesi |
| Görsel varlık görünüm ve sahne bağı | İllüstrasyon, sayfadaki görünümü, sahne/olay eşlemesi ve inceleme durumu |
| Bölüm sahne ve pasaj | Analiz bağlamı ile arama birimi |
| Karakter mention ve kimlik kararı | Ad, zamir, lakap ve geri alınabilir eşleştirme |
| Olay katılımcı ve durum | Kim yaptı, ne değişti, ne zaman ve hangi anlatı modunda |
| İddia kanıt ve ilişki | Destek, karşı kanıt, doğrulama ve grafik bağlantısı |
| İnceleme düzeltme ve bağımlılık | Editör kararı ve etkilenen türevler |
| İş analiz nesli ve release | Yürütme ve kullanıcıya sunulan tutarlı sürüm |

Veri modeli ilişkisel anahtarlar ve açık alanlarla kurulur; değişken ayrıntılar sürümlü JSONB içinde tutulabilir. Önceki generation'ın kimlik çözümü yeni birleştirme kararıyla geriye dönük değiştirilmez. Ham dosya ve geçmiş rapor korunur.

## 9 İddia zaman ve bakış açısı sözleşmesi

Bir iddianın kaynağı ile gerçekliği ayrı kavramlardır. Babanın Defne'nin tablet kullanım süresi hakkındaki sözü, önce babanın ifadesi olarak kaydedilir. Hikâyedeki ölçüm, şaka, benzetme, varsayım ve dış dünyaya yönelik bilimsel önerme birbirine karışmaz. Anlatıcının açıklığı ve güvenilirliği ayrıca yorumlanabilir; yorumun kendisi de kanıt ister.

| Alan | Değerler veya açıklama |
|---|---|
| claim_kind | EXPLICIT_STATEMENT, OBSERVED_EVENT, INFERENCE, EDITORIAL_JUDGMENT, EXTERNAL_WORLD_CLAIM |
| narrative_mode | ACTUAL, REPORTED, PLANNED, HYPOTHETICAL, DREAM, METAPHOR, JOKE |
| polarity | AFFIRMED, NEGATED, UNKNOWN |
| speaker_id ve viewpoint_id | Sözü söyleyen kişi ve bilginin bakış açısı; bilinmiyorsa null. |
| story_time | Tarih varsa aralık; yoksa göreli olay bağlantıları, sıra ve belirsizlik. |
| reveal_position | Bilginin okura açıklandığı kaynak/sahne sırası. |
| recorded_at ve superseded_at | Sistemin bu kaydı ne zaman öğrendiği ve yeni bir kayıtla değiştirdiği. |
| verification_status | CANDIDATE, SOURCE_LINKED, SOURCE_SUPPORTED, DISPUTED, HUMAN_CONFIRMED, REJECTED |
| evidence_refs ve counter_evidence_refs | Destekleyen ve karşı çıkan kaynak kimlikleri. |

SOURCE_LINKED yalnızca atfın var olduğunu belirtir. SOURCE_SUPPORTED kaynakla destek kontrollerini geçen kayıt anlamına gelir; editör onayı değildir. HUMAN_CONFIRMED yalnızca yetkili editör eylemiyle oluşur. Modelin kendi güven puanı bu durumlara tek başına geçiş yaptırmaz. Bir olgu sonradan çürütüldüğünde önceki kanıt ve karar geçmişi korunur.

Zaman kesin değilse tarih uydurulmaz. Önce/sonra, aynı sırada, yaklaşık kırk yıl önce gibi ilişkiler saklanır. Döngü oluşturan zaman bağlantıları kontrol edilir. Karakterin bir bilgiyi öğrendiği olay ayrıca kaydedilir; okurun bildiği bilgi otomatik karaktere aktarılmaz. Bir bilgiye sahip görünmenin kaynağı hayal veya gelecek planıysa gerçek bilgi durumu güncellenmez.

Örnek JSON yalnızca veri sözleşmesini açıklar; aşağıdaki kimlikler temsili değerlerdir.

{

"tenant_id": "tenant-example",

"content_version_id": "book-version-1",

"generation_id": "analysis-1",

"subject_id": "bilge",

"predicate": "REPAIRED_BALANCE",

"object_id": "max",

"claim_kind": "OBSERVED_EVENT",

"narrative_mode": "ACTUAL",

"polarity": "AFFIRMED",

"story_time": {"after_event_id": "max-balance-failure"},

"reveal_position": {"pdf_page": 28},

"verification_status": "CANDIDATE",

"evidence_refs": ["span-page28-repair"]

}

## 10 Analiz görevleri ve sınırlı edebî değerlendirme

Analiz sahneleri zaman, mekân, bakış açısı ve eylem devamlılığıyla ayrılır. Arama pasajları bu sahnelerden türetilir; pasaj sınırı sahnenin anlam sınırı sayılmaz. Bütün kaynak blokları anlatı, etkinlik, künye, görsel veya açıklayıcı ek kapsamında eşlenir.

| Geçiş | Kullanılan bağlam | Beklenen çıktı |
|---|---|---|
| Sahne okuması | Sahne, komşu bağlam ve görsel kayıt | Konuşmacı, kişi, eylem, nesne ve açık sorular |
| Kimlik çözümü | Mention ve ilgili özgün pasajlar | Ad, zamir ve hitap eşleştirmesi; belirsiz adaylar |
| Olay birleştirme | Sahne kayıtları ve kaynaklar | Katılımcılar, ACTUAL/PLANNED/JOKE ve durum değişimi |
| Karakter değişimi örneği | Seçilen karakterin ilgili bütün sahneleri | Başlangıç, değişim, tetikleyici ve karşı örnek |
| Tema ve duygu örneği | Üç pilot kitapta seçilmiş kaynak kümeleri | Kanıtlı yorum ve alternatif okuma |
| Destek kontrolü | İddia, özgün kaynak ve ilgili karşı kanıt | Destek, belirsizlik veya yeniden okuma isteği |

Kısa kitabın temiz tam metni gerçek tokenizer ile ölçülür; bağlam bütçesine uyuyorsa bütünsel geçişte birlikte kullanılır. Görseller ilgili sayfa gruplarıyla işlenir. Bağlam yetmiyorsa içerik sessizce kesilmez; paketleme değiştirilir veya kapsam dışı durumu döner.

Duygu kaydı duyguyu yaşayan kişi, tetikleyici, kaynak ve açık/örtük ifade ayrımını taşır. Anlatının tonu ve olası okur etkisi ayrı yorumlardır. Tek sahneden kalıcı kişilik veya klinik sonuç türetilmez. Tema yorumu için birden fazla ilgili kaynak ve mümkünse karşı okuma değerlendirilir.

Prompt, çıktı şeması, model konfigürasyonu ve kaynak listesi sürümlenir. Pydantic ve structured output biçim kontrolü sağlar; anlamsal destek ayrıca denetlenir [S5]. Model doğrudan veritabanı yazımı, serbest SQL veya kaynak dosya işlemi yapamaz.

Yeniden okuma ve onarım denemeleri sınırlıdır. Sınır dolduğunda inceleme kaydı oluşur. Kritik kişi/olay karışıklığı çözülmeden kesin bilgi olarak yayımlanmaz. Pilot genel otomatik tutarsızlık avcısı içermez; bilinen kritik hata örnekleri regresyon testi olarak korunur.

## 11 İlişki sözlüğü ve grafik kayıtları

İlk ilişki sözlüğünün sahibi teknik lider ve sorumlu yayınevi editörüdür. Teknik lider şema ve sorgu uyumunu, editör anlamı ve sınır örneklerini onaylar. Model yeni bir ilişki etiketi önerebilir; bu etiket kendiliğinden kanonik sözlüğe eklenmez. Sözlük sürümü her analiz manifestinde bulunur.

Başlangıç sözlüğü küçük tutulur: APPEARS_IN, PARTICIPATES_IN, LOCATED_AT, KNOWS, WANTS, CREATED, REPAIRED, PRECEDES, FRIEND_OF ve KINSHIP_OF. Bu on tip başlangıç tasarımıdır; pilot kanıtlarıyla daraltılabilir veya sürümlü genişletilebilir. KINSHIP_OF için akrabalık türü ayrıca kaydedilir; bir hitap tek başına akrabalık kanıtı değildir. Nedensellik veya tematik bağ ilk sürümde kesin kenar üretmeye zorlanmaz; kaynaklı iddia/yorum olarak saklanabilir.

Her tipte izin verilen uç varlık türleri, yönlülük, simetri, zaman alanı, narrative_mode ve kanıt gereksinimi tanımlanır. Düğüm veya kenar sayısını artırmak kalite ölçütü değildir. Aynı kanıtın yinelenen pasajları aynı olayı çoğaltmaz. Eşdizim veya grafik yolu bulunması nedensellik kanıtı değildir.

PostgreSQL'de sınırlı komşuluk ve olay/karakter sorguları kullanılır. Query budget, kitap, generation ve yetki kapsamı sunucuda uygulanır. Pilot kullanıcıya karakter kartı ve kaynaklı ilişki listesi sunar. Cytoscape gezgini, gelişmiş yol arama ve ayrı grafik motoru sonraki kapsamdır.

## 12 Kanıt kontrolü ve soru cevap

Kanıt kontrolü şema, kaynak varlığı, kitap/sürüm uyumu, metin veya görsel konumu ve anlamsal desteği ayrı denetler. Atfın sayfa numarası modelin yazdığı serbest metinden alınmaz; evidence_ref üzerinden çözülür. Alıntı özgün kaynak kaydından oluşturulur. Görsel kaynakta seçilen bölge ve gözlem/yorum ayrımı görünür.

*[Şekil — özgün belgede görsel]*

Şekil 2 Soru türüne göre kaynaklı cevap akışı

Liste ve sayım soruları yapılandırılmış kayıtları kullanır. Olgusal sorular ilgili olay/durum ve özgün pasajlara gider. Yorum sorularında karakter kayıtları, seçilmiş analizler ve kaynak araması birlikte kullanılır. Bütün kitabı kapsayan yokluk iddiası birkaç top-k sonuçla doğrulanmış sayılmaz. Pilot sınırını aşan kapsam açıkça bildirilir.

Hybrid aramada dense ve sparse adaylar birleştirilir, reranker uygulanır ve gerekli üst sahne bağlamı eklenir [S6]. Parça boyutu, aday sayısı ve vektör boyutu ölçülen konfigürasyondur. Farklı embedding uzayları aynı vektör alanında karıştırılmaz. Her kaynak cevap öncesi yetki ve generation bakımından yeniden doğrulanır.

Yanıt ANSWERED, PARTIAL, INSUFFICIENT_EVIDENCE veya NEEDS_CLARIFICATION durumu taşıyabilir. Cevap kapsamı ve destek ayrı ölçülür. Soru cevap yeni çıkarımları kanonik kitap bilgisine otomatik eklemez. Doğrulanmamış taslak, son cevap etiketiyle gösterilmez.

## 13 Sürümler indeks ve editör düzeltmeleri

PostgreSQL ana kayıt sistemidir. Qdrant noktaları kaynak ve analiz kayıtlarından yeniden üretilebilir. Bir değişiklik ve indeksleme outbox kaydı aynı veritabanı transaction'ında yazılır. Indexer deterministik point kimliğiyle tekrar güvenli upsert yapar. İndeks tesliminin başarısı doğrulanmadan yeni generation etkinleşmez.

Generation BUILDING, VALIDATED, ACTIVE ve RETIRED durumlarını taşır. Kullanıcıya sunulan release işaretçisi yalnız tam ve uyumlu nesle geçirilir. Her soru başlangıçta bir generation sabitler. Yarım indeks ile yeni karakter kayıtları aynı cevapta karıştırılmaz. Model/embedding değişiminde yeni sürüm hazırlanır; önceki sürüm geri dönüş için korunur.

Editör kaynak sayfasını, çıkarımı, destekleyen/karşı çıkan kanıtları ve belirsizliği birlikte görür. İnceleme eylemleri kabul, ret, kaynak okumasını düzeltme ve kimlik birleştirme/ayırmadır. İki editörün aynı kaydı değiştirmesinde beklenen sürüm denetlenir; sessiz son yazan kazanır davranışı uygulanmaz.

Düzeltme gerekçe, kullanıcı, hedef ve önceki sürümle yeni kayıt üretir. Kaynak düzeltmesi ile analitik yorum düzeltmesi ayrıdır. Bağımlılıklardan etkilenen karakter, olay, özet ve indeksler yeniden hesaplanır. Bilinen yanlış iddianın yeni cevaplarda kullanılmasını engelleyen düzeltme kontrolü, yeni generation hazırlanırken de aktiftir. Geçmiş rapor içeriği değişmez; sürümü görünür kalır.

Kaynak paneli PDF.js ile sayfa ve kayıtlı bbox alanını gösterir [S10]. Pilot ekranları kitap listesi, işleme durumu, kaynak inceleme, metin/görsel sahne görünümü, karakter/olay kaydı, soru cevap ve editör kuyruğudur. Grafik gezgini veya ileri rapor tasarımcısı bu teslimata eklenmez.

## 14 İş kuyruğu checkpoint ve kaynak paylaşımı

Pilotun kalıcı iş kuyruğu PostgreSQL jobs tablosudur. İşçiler kısa bir transaction içinde FOR UPDATE SKIP LOCKED ile uygun işi alır; owner_id, lease_until, attempt_no ve artan fencing_token yazar. Transaction bittikten sonra uzun model çağrısı başlar. Veritabanı kilidi model çalıştığı süre boyunca tutulmaz. SKIP LOCKED kuyruk benzeri erişimler için kullanılabilir [S7].

İşçi heartbeat gönderir. Süresi dolmuş lease dispatcher tarafından yeniden kuyruğa alınır. Eski işçi sonradan cevap döndürse bile fencing_token kontrolü sonuç commit'ini engeller. İşin aynı adımı iki kez çalışabilir; yazma işlemleri benzersiz idempotency anahtarı ve deterministik çıktı kimlikleriyle korunur. Exactly once yürütme sözü verilmez; tekrar yürütmede aynı sonuca yakınsayan uygulama davranışı hedeflenir.

LangGraph PostgreSQL checkpointer adım durumunu tutar [S8]. Dispatcher işi tekrar başlatır ve doğru thread/checkpoint ile devam ettirir. Checkpoint'in varlığı süreç izleme, heartbeat, zaman aşımı, kuyruk önceliği veya otomatik yeniden başlatma gereksinimini kaldırmaz. Thread kimliği sunucuda iş ve kurumla ilişkilendirilir; kullanıcı başka thread kimliği göndererek kayda erişemez.

Kuyruk sınıfları interactive, analysis, ingestion, reindex ve export olarak ayrılır. Kullanıcı sorularına ayrılmış kapasite bulunur. Kurum ve kitap başına eşzamanlı iş sınırı konur. Yüz kitap yüklemek yüz eşzamanlı GPU işi başlatmaz. Yük artışında admission control istekleri sıraya alır ve bekleme durumunu gösterir.

Geçici bağlantı hataları sınırlı exponential backoff ve jitter ile tekrar denenir. Geçersiz dosya veya şema uyuşmazlığı sınırsız tekrar edilmez. GPU bellek yetersizliğinde paket planı yeniden hesaplanabilir; kaynaklar sessizce kesilmez ve kapsam manifesti yeniden doğrulanır. Maksimum denemeyi aşan işler dead-letter durumuna alınır. Operatör gerekçeyi ve son tamamlanan adımı görür.

İptal isteği cancellation_requested alanını set eder. İşçi güvenli adım sınırında durur; destekleniyorsa model çağrısını da iptal eder. Tamamlanan kaynak işlemleri korunur, yarım generation aktifleşmez. Kaynak dosya değiştiğinde eski işin yeni sürüme yazması scope ve hash kontrolüyle engellenir.

Job tablosu grafın her adımını ikinci bir yürütme motorunda yönetmez. Job yaşam döngüsü ile checkpoint referansı eşlenir; devam edilecek adımın durumu checkpointer'dan alınır. Kaynak kayıtlarının commit'i ve gerekli outbox yazımı uygulama transaction sınırındadır. Checkpoint sonrası tekrar yürütme ihtimali için yan etkiler idempotent kalır.

Legal/BI ile aynı host kullanılacaksa CPU, RAM, model slotu ve varsa GPU için kabul edilmiş ortak kaynak bütçesi bulunur. Farklı kuyruklara öncelik vermek tek başına izolasyon değildir. Sistem kaynak sınırları ve birlikte yük testi uygulanır. Mevcut servisin ölçülen hizmet hedefi aşılırsa kitap işi bekletilir, kapasitesi azaltılır veya tahsisli kaynağa taşınır.

## 15 Model konfigürasyonu süre ve maliyet ölçümü

Konfigürasyon manifesti model ağırlık revision/hash, tokenizer, çalıştırıcı sürümü, nicemleme, bağlam uzunluğu, görsel çözünürlüğü ve token bütçesi, üretim sınırı, sampling ayarları, batching ve eşzamanlılık içerir. Görsel ve metin yolu ayrı görev olarak ölçülür. Bir görevde başarılı olmak bütün görevlere uygunluk sayılmaz.

CPU ve GPU profilleri kendi ölçümleriyle değerlendirilir. Aynı ağırlık ve eşdeğer ayarlarda işlem donanımı kalite düşüşü varsayımı oluşturmaz. Nicemleme, küçültülen görsel, kısaltılan bağlam veya kesilen çıktı ayrı değişkenlerdir. Çalıştırıcının model desteği gerçek denemeyle doğrulanır. BF16/FP16 karşılaştırması erişilebilir kaynak varsa kalite referansı sağlayabilir; belirli VRAM kapasitesi satın alma önkoşulu olarak sabitlenmez.

| Ölçüm | Kayıt biçimi |
|---|---|
| Aşama süresi | Parse, OCR, görsel, çıkarım, doğrulama, indeks ve cevap ayrı |
| Kullanıcı süresi | Kuyruk dahil toplam süre ve kuyruğun dışındaki işlem süresi |
| Hesaplama | Görev başına CPU/GPU kullanımı, token ve iş sayısı |
| Bellek | Yükleme, uzun bağlam ve eşzamanlı isteklerde tepe RAM/VRAM |
| Kaynak kapsamı | Sayfa, görünür yazı bölgesi, sahne ve işlenmeyen bölge |
| Editör yükü | Kitap okuma, etiketleme, değerlendirme, düzeltme ve uzlaşma |
| Birim maliyet | Hesaplama, editör zamanı, depolama ve yedek payı |

Kitap başı hesaplama maliyeti tahsisli CPU/GPU saatleri ile kurumun saatlik maliyetinin çarpımından hesaplanır. Editör maliyeti harcanan dakika ve saatlik maliyetle eklenir. Ortak host maliyet paylaşımı ayrıca belgelenir. Duvar saati ile paralel donanım saati birbirinin yerine kullanılmaz; enerji veya amortisman maliyetinin iki kez sayılması engellenir.

Modelin tüm işlerde çağrılması zorunlu değildir. Hash, kapsam, erişim, kaynak çözme ve şema denetimi deterministik çalışır. Görsel kayıtlar kaynak/model/görev sürümüyle yeniden kullanılabilir. Küçük model ancak aynı görevin ayrılmış değerlendirme örneklerinde kabul edilen başarıyı ve kapasite kazancını gösterirse devreye alınır. Daha çok model yüklemek bir performans hedefi değildir.

Sayfa/boyut tavanı, aktif soru eşzamanlılığı, kuyruk kapasitesi, bekleme hedefi ve kitap süre tahmini doğrulama çıktısıyla belirlenir. Ölçülmemiş kullanıcı sayısı veya toplam iş hacmi ürün garantisi olarak yazılmaz.

## 16 Kalite ölçümü ve editör bütçesi

Üç kitapta değerlendirme ilk günden başlar. Ekrana Sığmayan Macera hata sınıflarını kurmak için kullanılır. En az bir diğer kitap son doğrulama için ayrılır; sonuçlarına bakarak ayar yapılırsa artık bağımsız kabul seti sayılmaz. Üç kitap bütün Türkçe çocuk kitabı dağılımını temsil ediyor diye sunulmaz.

| Ölçü türü | Pilot yaklaşımı |
|---|---|
| Kaynak ve sayfa muhasebesi | Her sayfanın durumu kayıtlı; kritik içerikte sessiz atlama yok |
| Atıf bütünlüğü | Kaynak kimliği, kitap, sürüm ve konum geçerli; kırık referans sunulmaz |
| Erişim ve sürüm | Yetkisiz çıktı, eski raporun ezilmesi ve yarım release kabul edilmez |
| Karakter ve olay doğruluğu | Precision/recall ve olay modu başarısı ölçülür; başlangıç verisiyle eşik kararlaştırılır |
| OCR ve görsel yazı | CER, bölge kapsamı ve özel ad hataları ayrı; kayıp balon ayrıca kritik vaka |
| Arama ve cevap | Kanıt getirme, destek, yeterlilik ve cevap kapsamı birlikte ölçülür |
| Edebî örnekler | Kanıt, bağlam, alternatif yorum ve açıklık editör rubriğiyle değerlendirilir |

Önceki yüzde 95 veya benzeri başlangıç eşikleri bu sürümde otomatik pilot kapısı değildir. Ölçüm sonuçlarından sonra yayıneviyle görev bazında kabul hedefleri yazılır. Teknik bütünlük koşulları ertelenmez. İddia destek oranı, atıf kimliğinin varlığından ayrı bir anlamsal ölçüdür.

B01–B18 kritik regresyonları içerir. Bu kümede kritik uydurma veya yanlış olgu sunulmaması gerekir; sürekli cevap vermekten kaçınarak başarı üretilemez. Beklenen cevabın kapsamı ve doğru kanıtı da kontrol edilir. Görülmemiş kitap örnekleri ayrıca değerlendirilir. Genel model başarısı sınırlı test sayısından çıkarılmaz.

Editör planında sorumlu kişi, haftalık ayrılan saat, görev türü, örnek başına ölçülen süre, ikinci değerlendirici kapasitesi ve anlaşmazlık kuyruğu bulunur. Tema/duygu örnekleri ve kritik olay vakaları ikinci gözle incelenir. Her örneğe iki editör atamak başlangıç zorunluluğu değildir; kapsama göre örnekleme yazılır.

Örnek efor hesabı: 400 örnek, örnek başına 8–12 dakika ve iki değerlendirme varsayımı yalnız değerlendirme için yaklaşık 107–160 saat eder. Bu pilotun hedef örnek sayısı veya ölçülmüş maliyeti değildir. Kitap okuma, kanıt etiketleme, uzlaşma ve tekrarlar ayrıca eklenir. Gerçek bütçe ilk etiketleme oturumlarının süresinden hesaplanır.

İnceleme kuyruğunun geliş hızı ve editörün kapanış hızı izlenir. Birikim kapasiteyi aşıyorsa yeni kitap kabulü veya analiz hacmi sınırlandırılır. İnsan emeği görünmez ücretsiz kapasite sayılmaz. Takvim, editörün yazılı kapasitesi olmadan kesinleştirilmez.

## 17 Referans kitaptan kabul senaryoları

| Kimlik | Senaryo ve kaynak | Beklenen davranış |
|---|---|---|
| B01 | 44–48. sayfalardaki bozuk metin | Sorun tespit edilir; görünür kaynağa uygun metin elde edilir veya incelemeye ayrılır. |
| B02 | 29. sayfadaki konuşma balonu | Görsel yazı çıkarılır; 28. sayfadaki konuşmayla ilişkilendirilir. |
| B03 | 6, 12, 14 ve 37. görsel sayfalar | Metin azlığı nedeniyle boş sayfa sayılmaz; görsel içerik kaydı oluşur. |
| B04 | 4. sayfadaki Samet Can ve 32–33. sayfadaki Can | Yazar ve hikâye kişisi ayrı varlıklar kalır. |
| B05 | 10–11. sayfalarda Bilge'nin gelişi | Erken gelişin açıklaması bulunur; yanlış tutarsızlık uyarısı üretilmez. |
| B06 | 23. sayfada Max'in dedeciğim hitabı | Şaka olarak kaydedilir; gerçek akrabalık oluşturulmaz. |
| B07 | 28. sayfadaki Max onarımı | Denge sorununu çözen Bilge olarak kaydedilir; Defne'nin katkısı uydurulmaz. |
| B08 | 30–34. sayfalardaki ortak laboratuvar | Gerçekleşmiş deney değil, öneri/plan ve hayal edilen sahne ayrımı korunur. |
| B09 | 42. sayfadaki Robobi | Tamir beklediği doğru cevaplanır; Max'in tamiri ona taşınmaz. |
| B10 | 32–33. sayfalardaki Can | Tablette oyun geliştirdiği görülür; yalnız oyun oynuyor diye özetlenmez. |
| B11 | 40. sayfadaki oyun fikri | Gerçek dünyaya taşınacak oyun gelecek planı olarak kaydedilir. |
| B12 | 16, 24, 35 ve 43. etkinlik sayfaları | Okura yönerge olarak tutulur; karakterin gerçekleştirdiği olay sayılmaz. |
| B13 | 22 ve 27. sayfalardaki Robobi yetenekleri | Açıklığa kavuşturma adayı; otomatik kesin hata hükmü verilmez. |
| B14 | 5–10 ve 40–42. sayfalardaki Defne | O günkü duygu/ilgi değişimi çıkarılır; kalıcı klinik sonuç iddiası üretilmez. |
| B15 | Metin çıkarımında 8–9. sayfa tekrarları | Kaynak koordinatıyla ayrıştırıcı tekrarı ayıklanır; yazara tekrar kusuru yüklenmez. |
| B16 | 41. sayfadaki sayma ve saklambaç | Önerilen oyun gerçekleşmiş sahne olarak kaydedilmez. |
| B17 | Desteksiz soru örneği | Defne'nin kesin yaşı gibi kaynakta belirtilmeyen ayrıntıya yaş aralığından cevap uydurulmaz. |
| B18 | Yeni baskıda değişen bir pasaj | Önceki rapor korunur; yeni kaynağa bağlı etkilenen bulgular yeniden hesaplanır. |

B01–B18 bu dosya üzerinden hazırlanacak test tanımlarıdır; çalışan bir sistemin geçtiği testler olarak sunulmaz. Görsel kaynaklar editör tarafından doğru kimlik ve metinle etiketlenir. B13 ve B14 gibi yorum alanlarında beklenen sonuç; gerekçe, belirsizlik ve doğru kapsamdır. Sistem yalnız sonuç etiketini ezberleyerek başarılı sayılmaz; doğru kanıtı da getirmelidir.

## 18 Bağımlılıklı geliştirme işleri

İş paketlerine takvim tarihi verilmez. Her paket sorumlu, bağımlılık, tahmin aralığı ve çıkış kanıtıyla iş takibine aktarılır. Doğrulama evresinin ardından mevcut kod yeniden kullanımı ve gerçek ekip kapasitesiyle süreler hesaplanır. İş paketleri gerektiğinde birlikte yürütülebilir; kalite veya kaynak kabul bağımlılıkları atlanmaz.

| İş paketi | Ön koşul | Tamamlanma kanıtı |
|---|---|---|
| P0 Doğrulama | Ortam erişimi, kaynak ve editör | Ortam, model, uçtan uca süre, birlikte yük ve etiket emeği raporu |
| P1 Kaynak hattı | Kaynak sözleşmesi ve ilk render/OCR deneyi | Sürümlü yükleme, görsel varlık/görünüm çıkarımı, bütün sayfalar ve kaynak paneli |
| P2 Karakter ve olay | Uygun model yolu ve P1 çıktıları | Kimlik, olay modu/rolleri, görsel sahne eşlemesi ve kanıt kayıtları |
| P3 Sınırlı edebî örnekler | P2, seçilen üç kitap ve editör rubriği | Kaynaklı karakter değişimi, duygu ve tema örnekleri |
| P4 Arama ve cevap | Kaynak/iddia sözleşmesi ve çalışan ilk kitap | Qdrant, hybrid arama, sürüm sabitleme ve atıflı cevap |
| P5 Editör akışı | Kaynak paneli, iddia ve inceleme sözleşmesi | Metin/görsel sahne görünümü, kabul/ret, düzeltme ve bağımlılık yenileme |
| P6 İşletim | Çalışan pilot akışı | Kesinti, tekrar, yetki, offline, yedek/restore ve yük sonuçları |
| P7 Pilot değerlendirme | P1–P6 ve ayrılmış test örnekleri | Ürün başarısı, editör yükü, açık sorunlar ve üretim kararı |

Kaynak görüntüleme ve editör örnekleme P1'den itibaren çalışır; arayüz doğrulamanın sonuna bırakılmaz. İş süreleri ve hata izleri ilk denemeden itibaren tutulur; geniş izleme panosu P6'da tamamlanabilir. Lease, idempotency ve kaynak sınırları iş kuyruğu devreye girdiği anda uygulanır.

Teslim tarihi için kalan paketlerin bağımlılık grafiği, aktif geliştirme eforu, uzman kaynak çakışmaları, donanım bekleme süresi ve editör kapasitesi birlikte değerlendirilir. Sonuç tek kesin rakam yerine dayanakları ve belirsizlikleri belirtilmiş tahmin aralığıdır. Kapsam veya kapasite değiştiğinde tahmin sürümlenir.

## 19 Kod modülleri ve pilot API sözleşmesi

Tek depo, ortak Python uygulaması, ayrı API/işçi süreçleri ve editor dizini kullanılır. İlk beş uygulama modülü api, ingestion, analysis, retrieval ve review olarak düzenlenir. Veritabanı migration'ları, testler ve deploy dosyaları yardımcı dizinlerdir. Her modül ayrı dağıtılan paket veya servis olmak zorunda değildir.

Model erişimi, kaynak depolama ve grafik sorguları için dar arayüzler bulunabilir; varsayımsal geniş eklenti sistemi yapılmaz. SQLAlchemy/Alembic işlemleri ve migration'ları yönetir. Kütüphane, model, prompt, şema ve kurulum sürümleri manifestle sabitlenir.

| Uç veya uç grubu | Pilot sorumluluğu |
|---|---|
| POST /v1/works ve /editions | Eser ve baskı kaydı |
| POST /v1/editions/{id}/uploads | Yetkili yükleme oturumu |
| POST /v1/uploads/{id}/complete | Boyut/hash ve kaynak kabulü |
| POST /v1/content-versions/{id}/analyses | Analiz başlatma ve job_id |
| GET /v1/jobs/{id} ve POST /cancel | İlerleme, hata, inceleme ihtiyacı ve güvenli iptal |
| GET /v1/generations/{id}/entities | Karakter kartları ve kaynaklı kayıtlar |
| GET /v1/generations/{id}/events | Olay, mod, katılımcı ve durum |
| GET /v1/generations/{id}/scenes | Anlatı sırasındaki sahneler ve ilgili görsel/metin referansları |
| GET /v1/visuals/{id} | Yetkili önizleme, kaynak bölgesi ve sahne/olay eşlemeleri |
| GET /v1/evidence/{id} | Yetkili kaynak pasajı veya görsel bölge |
| POST /v1/questions | Kapsamlı istek, cevap durumu ve atıflar |
| GET /v1/reviews ve POST /v1/reviews | İnceleme kuyruğu ve editör kararı |
| POST /v1/corrections | Beklenen sürümle düzeltme kaydı |
| POST /v1/generations/{id}/activate | Kontrolleri geçmiş analiz sürümünü etkinleştirme |

Uzun işler 202 ve job_id döndürür. Mutation çağrıları idempotency anahtarı, düzeltmeler beklenen kayıt sürümü taşır. Liste uçları sayfalanır. Yanıt metadata'sında request_id, kaynak/analiz sürümü ve kullanılan kapsam bulunur. Ayrıntılı iç hata, yetkisiz kitabın varlığını açığa çıkarmaz.

Testler kaynak konumu, olay modu, idempotency, kesinti, sürüm sabitleme, düzeltme ve kitap yetkisini kapsar. Model değişiminde ilgili semantik set tekrar çalışır. Her küçük arayüz değişiminde bütün model değerlendirmesi yeniden yürütülmez. Tek depo düzeni sorumluluk ve kalite kontrolünü kaldırmaz.

## 20 Yerel işletim erişim ve kullanım politikaları

Model, OCR, embedding, arama, log ve yedek süreçleri kurumun kabul ettiği yerel altyapıda çalışır. Kurulum paketi model dosyaları, tokenizer, OCR dil verileri, belge modelleri, bağımlılıklar ve fontları içerir. Çalışma sırasında dış model çağrısı veya otomatik indirme yapılmaz. Ağ erişimi kapalı uçtan uca deneme zorunludur.

Kullanıcı ve kitap yetkisi API'de ve kaynak erişiminde uygulanır. PostgreSQL rolü gereksiz yüksek yetki taşımaz. Qdrant sorgusu kitap ve generation filtresiyle çalışır; sonuç yeniden doğrulanır. Cache anahtarları izin kapsamı ve release içerir. Çok kiracılı ürün yönetimi ertelenmiş olması kaynak yetkisini ertelemez.

| Politika alanı | Ayrı tanımlanacak karar |
|---|---|
| Analiz | Hangi kitap hangi kullanıcılarca ve hangi amaçla işlenebilir? |
| Eğitim | Kaynak veya editör etiketleri model eğitiminde kullanılabilir mi? |
| Log ve izler | Ham metin veya model girdi/çıktısı tutulur mu; kim erişir ve ne kadar saklanır? |
| Yedek | Kaynak ve türevlerin kopyaları nerede, ne süreyle tutulur? |
| Dışa aktarma | Hangi rapor, alıntı ve türev kim tarafından çıkarılabilir? |

Bu alanlar tek bir analiz izni altında otomatik birleştirilmez. Yayınevinin sözleşme ve içerik politikasıyla eşlenir; sözleşme hükmü varsayılmaz. Varsayılan uygulama logları ham kitap metni içermez. Eğitim işi pilotta bulunmaz. Yazılım/model/veri paketi lisansları kurulum envanterinde ayrı izlenir.

Belge ayrıştırıcıları ağsız, süre ve bellek sınırlı süreçlerde çalışır. Kitabın içindeki talimatlar model veya sistem yetkisini değiştiremez. LLM'ye serbest shell, dosya silme veya sınırsız SQL aracı verilmez. Sırlar kaynak koda yazılmaz; IP, port ve takma adlar ortam yapılandırmasındadır.

İşlem izleri kaynak işinden cevaba request_id/run_id ile bağlanır. Yerel OpenTelemetry ve ölçüm sistemi iş süreleri, kuyruk, hatalar ve kaynak kullanımını izler [S13]. Hizmet gecikmesi, RPO ve RTO hedefleri kurum ihtiyacı ve ölçümle belirlenir. Önceki sayısal varsayımlar bu pilot için taahhüt değildir.

PostgreSQL yedeği, kaynak dosyalar ve release manifesti birlikte geri getirilebilir olmalıdır. Qdrant indeksi yeniden üretilebilir kalır. Yedek dosyasının varlığı restore başarısı sayılmaz; izole ortamda geri yüklenip kaynak/atıf ve sürüm uyumu sınanır. Silme erişimi kapatır, aktif işi durdurur ve türevleri politika kapsamında temizler; yedek saklama takvimi ayrıca uygulanır.

Temel kurulumun tek hata noktaları işletim dosyasında görünür olur. Kesintisiz yüksek erişilebilirlik ayrı topoloji ve test gerektirir; ilk pilotun varsayılan teslimi değildir.

## 21 Pilot kabulü üretim kararı ve sonraki kapsam

Pilotun tamamlanması ve üretime geçiş iki ayrı karardır. Pilot kabulünde sınırlı kaynak profili, konfigürasyon manifesti, teknik zorunluluklar, ölçülen anlamsal sonuçlar, editör iş yükü ve açık sorunlar birlikte sunulur. Üretim kararı, bu kapsamın kurumun iş ihtiyacına yeterli olduğunu ve işletim sorumluluğunun atanmış olduğunu gösterir.

Zorunlu teknik koşullar kırık atıf sunulmaması, kritik kaynakta sessiz atlama olmaması, geçmiş raporun korunması, yetkisiz veri sunulmaması, yarım generation'ın etkinleşmemesi ve tekrar yürütmede kayıt bütünlüğüdür. Görev başarısı, cevap kapsamı, görsel okuma ve edebî rubrik için kalibre edilmiş eşikler ayrıca uygulanır. Bilinmeyen başarı alanı genel ortalama içinde gizlenmez.

Geri dönüşte önceki uygulama/model manifesti ve uyumlu release seçilir. Yeni editör kararları kaybedilmez; bilinen yanlış iddiaları engelleyen düzeltme kontrolü korunur. Kritik kaynak hatası, yetki ihlali veya ciddi olay/karakter regresyonu yeni sürümün açılmasını engeller. Kaynak kimliği ve index manifesti doğrulanmadan geçiş tamamlandı sayılmaz.

| Sonraki kapsam | Başlatma gerekçesi |
|---|---|
| Grafik gezgini | Editörün mevcut ilişki listeleriyle çözemediği görünür kullanım ihtiyacı |
| Seri ve çeviri | Kitaplar arası kanonik kimlik ve baskı hizalama gereksinimi |
| EPUB ve DOCX | Yayınevinin doğrulanmış teslim formatları ve yeni kabul örnekleri |
| Otomatik bütünlük taraması | Yeterli pozitif/negatif örnek ve yönetilebilir editör uyarı yükü |
| Otomatik görsel tutarlılık taraması | Pilot sahne ekranından etiketlenmiş uyuşmazlıklar ve kabul edilebilir hata oranı |
| Daha geniş tema ve duygu motoru | Üç kitaptaki sınırlı örneklerden daha geniş corpus kabulü |
| Çok kiracılı ürün yönetimi | Ayrı kurumların yaşam döngüsü ve yönetim ihtiyacı |
| Ayrı grafik veya iş motoru | Gerçek yükte ölçülen sorgu/işletim sınırı |
| Eğitim veya uzman model | İzinli veri, tekrarlayan hata sınıfı ve ayrılmış sette gösterilen fayda |

İlk geliştirme teslimatı, P0 ölçümlerinin ve kalan iş kırılımının birlikte incelenmesidir. Bundan sonra kapsam, kaynak tahsisi, editör saati, kabul hedefleri ve teslim tahmini aynı karar kaydında sürümlenir.

## 22 Teknik kaynaklar

Kaynaklar 16 Eylül 2026 tarihinde kontrol edilmiştir. Buradaki teknik uygulamalar ve görev dağılımı proje tasarımıdır; ürün belgelerindeki özellik açıklamaları projenin ölçülmüş başarısı yerine kullanılmamıştır. Uygulama sürümleri doğrulama evresindeki uyumluluk denemeleriyle sabitlenecektir.

S1 Qwen3.8-27B model kartı https://huggingface.co/Qwen/Qwen3.8-27B

S2 Qwen3-Embedding-4B model kartı https://huggingface.co/Qwen/Qwen3-Embedding-4B

S3 Qwen3-Reranker-0.6B model kartı https://huggingface.co/Qwen/Qwen3-Reranker-0.6B

S4 Docling gelişmiş ve yerel kullanım ayarları https://docling-project.github.io/docling/usage/advanced_options/

S5 vLLM structured outputs https://docs.vllm.ai/en/latest/features/structured_outputs/

S6 Qdrant hybrid queries https://qdrant.tech/documentation/search/hybrid-queries/

S7 PostgreSQL SELECT ve SKIP LOCKED https://www.postgresql.org/docs/current/sql-select.html

S8 LangGraph persistence https://docs.langchain.com/oss/python/langgraph/persistence

S9 PostgreSQL row security https://www.postgresql.org/docs/current/ddl-rowsecurity.html

S10 PDF.js https://mozilla.github.io/pdf.js/

S11 Cytoscape.js https://github.com/cytoscape/cytoscape.js

S12 Docker Compose üretim kullanımı https://docs.docker.com/compose/how-tos/production/

S13 OpenTelemetry Collector https://opentelemetry.io/docs/collector/

S14 NovelQA araştırması https://arxiv.org/abs/2403.12766

S15 Qdrant multitenancy https://qdrant.tech/documentation/manage-data/multitenancy/

S16 Pydantic veri modelleri https://pydantic.dev/docs/validation/dev/concepts/models/

S17 Tesseract dil modelleri https://github.com/tesseract-ocr/tessdata_best

S18 Qdrant BM25 kodlayıcı https://huggingface.co/Qdrant/bm25

Kitap kanıtları kullanıcı tarafından sağlanan Ekrana Sığmayan Macera İç Baskı PDF dosyasından alınmıştır. Kaynak sayfaları kabul senaryolarında belirtilmiştir. Özgün kitabın sayfa numaraları bu geliştirme planının sayfa numaralarından bağımsızdır.
