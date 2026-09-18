# V14: kaynaktan alıntı seçimi ve eksiksiz dayanak aktarımı

V14 sunucuda çalışıyor; tam kitap veya üretim kabulü henüz değildir. Önceki R2 nesli, başarısız denemesi ve ayrı restore snapshot'ı korunur. Kitap metni, karakter adı veya inceleme kararı operatör tarafından düzeltilmez.

## Gerçek R2 bulgusu

Bağımsız API/PG denetiminde51 sınırlı iddianın6'sı ek OCR satırlarından destek alıyordu.24 sentez ifadesinin4'ünde bu ek satırların source_span_refs bağlantıları eksikti. Önceki türetilmiş kayıt eşliği bu eksik bağımlılık aktarımını sınamıyordu; başarı kapsamı genişletildi. `verify-semantic-provenance.py` artık gerçek uygulamanın verdiği sentez bağlantılarını bütün iddia/dayanak bağlantılarının birleşimiyle karşılaştırır. R2 beklenen başarısızlık kanıtı `evidence/v13-r2-semantic-provenance-gap-r2.log`; ilk verifier API öğesinde kind alanı varsaydığı için durdu, endpoint türünü bağımsız PG türüyle karşılaştıracak biçimde düzeltildi, ilk log korundu.

## Genel kod düzeltmesi

`source_unit_claims.py`, yalnız aynı sayfa/render ve ardışık TEXT_AGREED metin span'larından1–3 satırlık kaynak birimleri kurar. Her uygun satır tek başına da temsil edilir; çok satırlı birim96 sözcükle sınırlıdır. Model alıntı yazmaz, birim kimliği seçer. Alıntı ve kaynak kimlikleri bu değişmez birimden aynen alınır; ham model önerisi ayrı saklanır. Alıntı/olumsuzluk/sayfa amacı kapıları korunur. Optik/görsel ölçümler yeniden kullanılabilir; eski üretilmiş alıntılı iddia önerileri V14'te yeniden kullanılmaz. Pipeline `source-spans-v14`.

`source-semantic-review-v2`, mevcut sayfa bağlamı incelemesinin ardından yalnız açıkça taşınacak kaynak bölgelerini gören ikinci incelemeyi yapar. actor/speaker null alanları, iddia metnindeki isim/fail/konuşmacı iddiasını kontrol dışı bırakamaz. Belirsiz veya desteksiz sonuç senteze giremez. Bütün ek kaynak kimlikleri, ham metin/kutu/render hashleri ve ayrı model yanıtı kaydedilir. Sentez öncesi aynı kaynaklar gerçek span kayıtlarıyla yeniden karşılaştırılır; hash/kapsam uyuşmazlığında koşu durur. Sentez tüm gerekli kaynak bağlantılarını taşır; kayıp bağlantı sessiz kabul edilmez.

Bu iki çağrı aynı modeldir; bağımsız insan değerlendirmesi veya tam karakter kimliği kabulü değildir. semantic_acceptance/editoryal kabul false kalır. Kaynak kontrolü ham kitap kaydını değiştirmez.

## Gerçek bileşen kanıtları

R2 gerçek kaynaklarından19/28/38 sayfalarda kaynak birimi yöntemi dört iddianın alıntı kapısını MATCH verdi.16. sayfa ACTIVITY olarak ayrıldı, olay iddiası0. Kaynak birimi hash'i `a134c5f0f926`; bütün pilotlar gerçek API/PG karşılaştırmasıyla, application_writes=0 çalıştı.

Yeni atıf incelemesiyle19. sayfadaki dört adaydan ikisi ayrıca reddedildi; önceki tam sayfa model onayına rağmen açıkça atıf verilen metinler yeterli bulunmadı.38. sayfanın mevcut R2 adayları V2 üzerinden üç model destekli aday ve iki sınırlı sentez ifadesi üretti; her doğrulanmış ek dayanak son ifadeye taşındı. Kanıtlar `source-unit-claims-c046c684-8821-4770-bab3-fb7dc9c25b05-0019-fe4c51af18e7.json` ve `semantic-live-component-c046c684-8821-4770-bab3-fb7dc9c25b05-page0038-cd8c48e863d6.jsonl`.

Yeni tam kitap nesli, genişletilmiş kaynak/atıf denetimi, dolu mobil akış ve güncel paket/restore kabulü henüz yapılmadı. Mevcut R2 sonucunu V14 kabulü saymayın. GitHub HTTPS kimliği bulunmuyor ve SSH publickey reddedildi; yerel main dışına yayınlandığı iddia edilmez.

## Canlı yayın ve yeni koşu

Backend/document `source-analysis-v14-r1-20260918`, web R3. Yerel main kod commit'i `73b62fd`.47 backend dosyası tree hash `888fb9ddfb4f7993737d642a701a1d65f359642053b0ac41f213bd4f6091f7ef`;9 web dosyası ve derlenmiş çıktılar eşleşti. Gerçek API/PG altyapı ve28 ACL kontrolü geçti. Yeni iş `af2264d8-6f77-4860-be29-a5294283e49b`, nesil `6dca7f01-590c-4a28-a969-a8c8fbb67776`. Öncelik19/38/28/16/29/6; kalan sayfalar aynı koşuda işlenir. Kaynak atası R2; yeni model adayları ve atıf denetimleri sıfırdan üretilir.

İlk ağsız Dockerfile derlemesi alembic bağımlılık önbelleği bulunmadığı için başarısız oldu; loglar korundu. Mevcut doğrulanmış R2 API/document imajlarının requirements.lock/document-requirements.lock hashleri checkout ile karşılaştırıldı, aynı bağımlılıklar üzerine yalnız uygulama kodu kopyalanarak ağsız derlendi. Kanıt `v14-build-base-proof.json`; başarılı son derleme `v14-api-build-r3.log`/`v14-document-build-r3.log`. `v14-release.log`, `v14-infrastructure.log`, `source-analysis-v14-r1-start.json` CPU evidence dizinindedir. Kitap verisine/kararlarına elle değişiklik yok.

## R1 koşusunda bulunan sayfa-amacı açığı ve R2 adayı

R1 gerçek29. sayfa model yanıtı, balondaki soruyu ACTIVITY saydı. Ham yanıt ve kaynak birimleri R1 neslinde korunur. `page_context.run` yalnız UNKNOWN sayfaları denetlediğinden bu etiket komşu kaynak kontrolünü atlıyordu. Genel düzeltme, NARRATIVE/MIXED dışındaki bütün sayfa amacı önerilerini gerçek yerleşim ve komşu metinle denetler. Kaynaklı ayrı bağlam kararı varsa çapraz diyalog yalnız UNKNOWN için değil diğer ilk öneriler için de bu kararı kullanır; bütün referans/hash/iki çağrı/engelleyici belirsizlik kapıları aynen korunur. İlk sayfa kaydı değiştirilmez; eski ve yeni etiket ile uyuşmazlık ayrı kaydedilir. Karakter/konuşmacı adı verilmedi.

Aday `source-page-context-v3` gerçek R2 kaynaklarında29'u NARRATIVE (ikinci inceleme destekli),16'yı ACTIVITY (kimlik bağlamına kapalı) verdi.700 token bütçesi16'da kesilen JSON üretmişti;1100 token bütçesinde tam yanıt elde edildi, kesik yanıtı kabul etmeme kuralı değişmedi. Kanıtlar `v14-page29-role-v3.log`, `v14-page16-role-v3.log`, modül hash `116012c6c537`. Çapraz kaynak V8 pilotunda48 sayfa API/nativePG eşliği ve0 kapsam hatası var; bu pilot alt bölge girdileri içermediği için0 diyalog bağlantısı üretmiştir, tam kimlik veya diyalog kabulü değildir. Canlı R1 kodu değiştirilmedi; R2 yeni nesil ve uçtan uca kabul bekler.

Kurulum doğrulama aracı da yeni GPU topolojisine hazırlanıyor: seçili koşu dosyası, external-models paket modu, ayrı hedef model uçları, çakışmayan ağ/port seçimi ve kaynak/anlam-atıf kontrolünün restore üzerinde tekrarı. Bu araç değişikliğinin gerçek restore kabulü henüz yapılmadı. Kaynak verifier'ının karakter kayıtlarını yalnızv5–v10'da denetleyen eski sürüm listesi kaldırıldı; v5 ve sonraki gerçek kayıtlar aynı API/PG karşılaştırmasına girer.

## R2: sözcük sınırı ve doğrulanabilir okuma görünümü

R1 gerçek anlam kayıtlarında iki ek hata bulundu:8. sayfada satıra bölünen sözcüğün anlamı değiştirilmişti;5. sayfada ayrı büyük başlangıç harfi atlanınca eksik sözcük kişi adı gibi sunulmuştu. İkinci iddia R1'de model destekli/uygun sayıldı; bu yüzden48/48 kayıt eşliği anlamsal kabul değildir. Eski iddialar ve OCR kayıtları korunur.

`source-unit-claims-v2`, ham OCR ve kutuları değiştirmeden kaynak kimliklerini taşıyan ayrı `reading_view` üretir. Satır sonu tire birleşimi yalnız aynı sayfa/render, örtüşen sütun ve yakın ardışık satırlarda yapılır. Ayrı büyük başlangıç harfi de yalnız iki TEXT_AGREED bölge ve ölçülen tipografik geometriyle birleştirilir; kitap veya kişi adına özel kural yoktur. Yapılan işlemler iki span kimliğiyle kaydedilir. Atlanan/incelemedeki bölgenin üzerinden birleştirme yapılmaz. Başlangıç harfini veya gövdeyi tek başına bırakan birim modele seçtirilmez. Kaynak satırları, özgün alıntı ve kaynak hashleri aynen korunur.

`source-semantic-review-v3`, ilk ve yalnız atıflı ikinci incelemeye bu izlenebilir okuma görünümünü de verir. Sözcüğün eksik parçasına dayanan eski aday `PARTIAL_WORD_SOURCE_REQUIRES_REVIEW`, eksik ek dayanak `CITED_PARTIAL_WORD_SOURCE_REQUIRES_REVIEW` olur. Sayfa içi metinsel fail kontrolü aynı alıntı kaynaklarının doğrulanmış okuma görünümünü kullanır; genel karakter veya görsel kimlik kabulü vermez. Atıf verifier'ı ham karakter/kutu/hash ve bildirilen her birleştirme işlemini gerçek kaynakla karşılaştırır.

Gerçek API/PG, application_writes=0 pilotları: yeni5 ve8 önerileri kaynak sözcüklerini doğru kurdu; eski yanlış5 adayının yeniden incelemesi deterministik sözcük sınırı kapısında reddedildi.8'de eski hatalı iddia yeni okumayla UNKNOWN/review kaldı. Kanıtlar `source-unit-claims-6dca7f01-590c-4a28-a969-a8c8fbb67776-0005-1c98bb00cc47.json`, aynı hash ile0008; `semantic-live-component-6dca7f01-590c-4a28-a969-a8c8fbb67776-page0005-6bbf07588135.jsonl`.16/38 son hash karşı kontrolleri geçti:16 etkinlik/0 iddia;38 dört MATCH alıntı ve2 sınırlı uygun iddia. Tam R2 nesli beklenir. Son kod hashleri: kaynak birimi `0f5ffdfdf17e`, anlam `6c658a9f0514`.

29. sayfanın gerçek R1 ACTIVITY önerisi, kayıtlı dört alt bölge ve80 API/PG kaydıyla bağlam V3'e verildi: NARRATIVE ve destekli ikinci inceleme. Aynı gerçek R1 girdileriyle çapraz V8 kontrolü48 sayfa/nativePG eşliği,0 kapsam hatası ve1 sınırlı diyalog bağlantısı verdi. Böylece önceki yalnız UNKNOWN koşuluna bağlı atlama gerçek başarısız nesilde tekrarlandı ve aday kodda giderildi. Genel karakter kimliği hâlâ0.

Ek işletim kanıtı: ısınmış GPU üzerinde iki Qwen+12 OCR örtüşen gerçek istek PASS, restart0 ve en düşük boş bellek5114MiB; tam kapasite/SLO kabulü değildir. Yayın/soru kapıları gerçek R1'de401/409 verdi, soru işi ve insan kararı oluşturmadı. İzolasyon aracının reread-worker için eski private-network varsayımı düzeltildi; doğru sözleşme parser gibi network:none, read-only, cap-drop ALL, secrets/docker.sock erişimi olmamasıdır. Gerçek tekrar `v14-r1-isolation-r2.log` geçti. İlk başarısız log korunur.

R2 ara imaj derlemesinde Dockerfile FROM alanına çıplak image ID verilmesi registry adı gibi yorumlandı; başarısız loglar korundu. Yerel base tag ID’leri tekrar karşılaştırıldı, doğrulanmış taglerle bağımlılık indirmeden son dört modül katmanlandı. Son build kanıtı `v14-r2-final-build-base-proof.json`, `v14-r2-api-build-final.log`, `v14-r2-document-build-final.log`.

## R2 canlı yayın ve otomatik ayrı kurulum doğrulaması

Kod `814d7ea`, backend/document `source-analysis-v14-r2-20260918`, web R3. Yerel depo/sunucu checkout/çalışan imaj47 dosya tree hash `88837115b1fa9a2052c5a74094d0b499ad6f8f888e5af86ceb2e13a1cd967e80`;9 web dosyası ve gerçek altyapı/28 ACL kontrolü geçti. Yeni iş `efeeb1cb-4741-48f6-87a0-7b4e5285f786`, nesil `3db56430-4821-41c6-a513-4d6e4645bcd6`; kaynak atası tamamlanmış R1. Öncelik5/8/29/16/38/19/28/6; eski yanlış içerik elle değiştirilmedi. Canlı5/8 model çıktıları da yeni kaynak okumalarını üretti.

R1 kapanışı:52 sınırlı uygun iddia,27 sentez ifadesi,5 ek dayanaklı iddia; `v14-r1-final-provenance.log` eksik atıf0, API/PG eşliği PASS. Bu yalnız atıf düzeltmesinin kabulüdür; R1'de bulunan sözcük ve sayfa-amacı hataları nedeniyle tam anlamsal kabul yoktur. Kaynak887 anlaşma/262 incelemedir.

R2 qualifier `/data/nanobaseai/editor-qualifications/v14-r2-20260918/3db56430` altında ayrı paket/importu geçti ve tamamlanacak nesli bekliyor. Sonra gerçek kaynak/karakter/API/PG, türetilmiş kayıtlar, atıf kapsamı, yayına/soruya yetkisiz geçiş engelleri, tutarlı yedek, ayrı yeni kurulum/restore ve320/390/768/1440px dolu OCR/kimlik/küçük kaynak/diyalog/sentez akışı çalışacak. Ağsız reread-worker izolasyon kontrolü düzeltildi ve gerçek ana ortamda geçti. API18824/metrik19104, subnet72/73; geçici proxy18886/18888 yalnız73 ağını kabul eder. Wrapper sonunda kendi nginx/UFW kurallarını kaldırır; target volume/kanıt silinmez. Kanıt `evidence/v14-r2-qualification.log`; henüz restore PASS iddiası yok.

GPU paketinin yeni konteyner/boş çalışma cache'i ve internal ağda gerçek açılış kontrolü için `gpu/verify-offline-boot.py` hazırlandı; henüz çalıştırılmadı. Kitap ve restore işleri bitmeden model durdurulmaz. Araç paket byte/imajlarını denetler, aktif Qwen/OCR ve başka GPU işi varsa başlamaz; ayrı offline modellerin gerçek kırpım/ortak yük kontrolünden sonra önceki runner'ları yeniden açıp gerçek çıkarımı doğrular. Aynı fiziksel GPU üzerinde yeni cache testi olacaktır, farklı müşteri donanımı kabulü sayılmaz.

## R2 tam koşu ve bağımsız atıf kontrolü

18 Eylül02:05UTC itibarıyla iş COMPLETED, nesil NEEDS_REVIEW.48 kaynak/figür/anlam sayfası işlendi;63 iddia sınırlı taslağa uygun,65 iddia incelemede.31 sentez ifadesinde7 ek kaynak dayanaklı iddianın bütün kaynakları taşındı; `semantic_provenance.log` gerçek API/PG eşliği ve eksik atıf0 verdi. `source_api_pg`, `derived_api_pg`, `publication_gates`, `release_bytes_after_analysis`, `source_isolation` PASS. Bunlar tam kitabın anlamsal veya editoryal kabulü değildir;262 kaynak bölgesi ve genel karakter kimliği açık.

29. sayfa yeni koşuda kısa söze ilişkin komşu kaynak bağlantısını otomatik üretti; destek kapsamı yalnız alıntı öneki, bütün balon veya genel figür kimliği değil.17 olası kırpım eşleştirmesinin12'si ölçüldü,5'i yapılandırılmış sınır nedeniyle işlenmedi; bu eksik kapsama kayıt üzerinde görünürdür. OCR kullanılmadığında kendiliğinden kapandı, Qwen çalışmayı sürdürdü. Yedek/ayrı restore/mobil denetimi02:05:39UTC'de başladı; sonuç bekleniyor.

## R2 restore tamamlandı; R3 için yeni anlamsal hata

02:09:58UTC: R2 ayrı restore, API/PG, atıf, yayın kapıları ve320/390/768/1440px mobil kontrolü PASS. Target02:10:01UTC'de durdu, geçici proxy/UFW kuralları temizlendi; veri/kanıt korundu. Bu teknik kabul, öykü anlamının doğruluğu değildir.

İçerik incelemesinde45. sayfadaki bilgilendirici ekten bir ifade THEME olarak senteze girmişti. Özgün aday, inceleme ve sentez kayıtları korundu. Mevcut V3 sayfa-amacı kontrolü aynı84 gerçek API/PG kaydıyla yeniden çalıştırıldığında bilgilendirici düzyazıyı da NARRATIVE saydı; sınıflandırmanın anlamı eksikti. V4, sayfa biçimine ek `content_scope` (STORY_WORLD / INFORMATIONAL / READER_GUIDANCE / EXERCISE / MIXED / UNKNOWN) üretir; öykü dünyasıyla doğrudan okura verilen genel bilgi/öğüt ayrılır. Bütün sayfalar ayrıca denetlenir, yalnız ilk önerisi belirsiz sayfalar değil.

V4 kaynak amaç kararı, girdinin yeniden oluşturulan hash'i, kaynak kimlikleri ve iki model geçişiyle kontrol edilmeden anlamsal iddia ve figür/çapraz kimlik aşamasına geçemez. Okunabilir hedef metni olmayan sayfa normal biçimde incelemede kalır; kaynak bütünlüğü hatası gibi gösterilmez. Anlam V4 ve figür V2 kapıları, kapsamı uygun olmayan eski iddiaları değiştirmeden sonraki senteze kapatır. Çapraz diyalog V9 da aynı kaynak amaç kapısını kullanır. UI bilgilendirici metni Türkçe gösterir; mobil doğrulayıcı bu gerçek yeni rolü seçer.

İlk gerçek aday pilotlarında45 INFORMATIONAL/0 uygun iddia/0 sentez,16 ACTIVITY/0 uygun iddia;5/29/38 STORY_WORLD verdi. Hiçbir kitap cevabı veya beklenen sayfa etiketi modele verilmedi, application_writes=0. İlk şema INFORMATIONAL sayfa biçimini kabul etmediği için sonuç UNKNOWN kaldı; açık içerik rolü sözleşmeye eklendi ve aynı kaynak yeniden çalıştırıldı. Son kaynak-sınırı yardımcı işlev düzeltmesinden sonra45/5/6 final-hash kontrolleri sürüyor. R3 henüz canlı değil; R2'nin eski hatası düzelmiş sayılmaz.

R3 son-hash bileşen kontrolü: `page_context.py` ebb724c15449, `semantic_acceptance.py` cd00b4719d24. Gerçek45 dört eski adaydan0 uygun iddia/0 sentez;5 iki uygun iddia/iki kaynaklı ifade;6 okunabilir hedef metni olmadığı için PAGE_PURPOSE_REVIEW_REQUIRED/0 iddia. Kanıt `v14-r3-final-page45-story.log`, `...page05-story.log`, `...page06-story.log`; application_writes=0. R3 API/document imajları doğrulanmış R2 base üzerinde ağsız derlendi ve dört değişen modülün imaj byte'ları karşılaştırıldı (`v14-r3-final-build-proof.json`). Web build aracı ayrı staging dizini ve kilitli çevrimdışı npm cache seçeneği kazandı; kaynak/çıktı manifesti gerçek sunucu derlemesinde üretildi.

GPU cold-boot doğrulayıcısı484269 süreciyle başlatıldı (`/data/editor-gpu-packaging/20260918/cold-boot-v14-launch.log`); öncesinde ana kitap kuyruğu0, R2 qualification PASS, hedef STOPPED ve geçici ağ temizliği doğrulandı. Yeni R3 kitap koşusu bu bakım/geri dönüş tamamlanmadan başlatılmayacak.

## R3 canlı kod ve GPU soğuk açılışta bulunan paketleme hatası

Kod `ccbeccc` main üzerinde. R3 API/document/web canlıya alındı, yeni kitap işi henüz açılmadı.47 dosya yerel/sunucu/imaj tree hash `e07cdb27015c9df481a99bb1a5784dbf600f62170205165511478748e3c225a6`;9 web kaynak/çıktı manifesti eşliği PASS (`v14-r3-release.log`). Yayın sırasında kitap kuyruğu0, önceki restore tamamlanmıştı. Yeni nesil model bakımının bitmesini bekler; eski R2 kaydı değiştirilmedi.

GPU cold-boot testi dosya172/imaj kimliği kontrolünü geçti fakat gerçek internet kapalı açılışta LocalEntryNotFoundError verdi. Kök neden `bundle.py`'nin `refs/main` dosyasına commit kimliğinden sonra newline eklemesi: canlı cache40 byte, paket41 byte; literal snapshot yolu bulunamadı. Hash doğru olsa bile cache biçimi yanlış olabiliyordu. Kontrollü SIGTERM ile aday durduruldu, araç mevcut Qwen/OCR servislerini geri getirme aşamasına geçti; ilk başarısız paket ve log korundu.

Paket üretimi newline eklemiyor; import şimdi ref'in commit ile birebir eşliğini ve her gerçek model imajının kendi HF kütüphanesiyle ağsız snapshot çözümlemesini doğruluyor. `reprofile-bundle.py` eski ağırlık/imaj dosyalarını hardlink ile koruyup yalnız yeni metadata inode'larıyla yeni paket türetiyor. Yeni `/data/editor-gpu-releases/source-analysis-v14-cache-v2-20260918` import denetiminde. Cold-boot aracı başlangıçta ref biçimini denetliyor, model yeniden başlama döngüsünde1800 saniye beklemek yerine erken başarısız oluyor; betik hashlerini rapora koyuyor. Yeni paketin gerçek soğuk açılışı henüz geçmedi.

Cache-v2 import, yeni snapshot çözümleme adımında GPU imajında python alias'ı olmadığı için127 ile durdu. Gerçek çalışan Qwen/Paddle konteynerlerinde python3 bulundu; her iki model snapshot'ı python3 ile ağsız probe'da doğru revision'a çözüldü (`cache-v2-python3-resolution.json`). Bundle sağlık kontrolü, importer ve cold-boot ağ kontrolü python3 kullanacak şekilde düzeltildi. Yeni cache-v3 paketinde bu kod/Compose güncellemesi ayrı inode'larla taşındı; import tekrar sürüyor. Exact-ID imajlar mevcutsa yeniden docker load yapılmıyor, dosya/arsiv hashleri her seferinde kontrol ediliyor. İlk cold-boot raporu FAILED olarak korundu; live_runners_restored_and_inference_verified=true, cleanup_errors=[] ve Qwen geri açılışı200,069sn. R3 gerçek API/DB altyapı ve28 ACL kontrolü de geçti (`v14-r3-infrastructure.log`).

Cache-v3 import PASS: bütün172 dosya hash'i ve üç imaj kimliği eşleşti; Qwen/Paddle snapshot'ları kendi imajlarının HF kütüphanesiyle internet kapalı doğru sabit revision'a çözüldü. Exact-ID imajlar yeniden yüklenmedi. Kanıt `/data/editor-gpu-packaging/20260918/cache-v3-import.log`. Yeni soğuk açılış denemesi518950 PID ile `/data/editor-gpu-packaging/20260918/cold-boot-v14-cache-v3/` altında başladı; kitap kuyruğu yeniden0 doğrulandı. Bu ikinci denemenin sonucu henüz bekleniyor.

## R3 yeni tam koşu başladı; ikinci GPU bakım denemesi güvenle ertelendi

İkinci GPU cold-boot, tüm paket byte'larını doğruladıktan sonra LIVE_MODEL_USED_DURING_IDLE_CHECK ile durdu.30 saniyelik boşta kontrolünde başka bir model isteği görüldü; hiçbir stop-live-models adımı çalışmadı, temizleme hatası yok. Bu paket açılış hatası değildir; model sunucusu kullanılmakta olduğu için kesilmedi. Yeni paketin tam GPU soğuk açılış/çıkarım kabulü hâlâ DOĞRULANAMADI; gerçek HF offline çözümleme/import PASS korunur.

Mevcut model servisleri hazır ve Editör kuyruğu0 iken R3 gerçek analiz API'si çağrıldı. İş `49660185-0b6b-474c-aedf-04f78e6f86a6`, nesil `97814b6c-98fc-4c8e-b442-cbfcd9306889`, aynı içerik sürümü `3970f5b9-769a-4fe9-8032-379834fa6831`; kaynak atası tamamlanmış R2. Öncelik45/5/8/29/16/38/6/28; kaynak veya inceleme kararı elle değiştirilmedi. Monitor3140379, qualifier3140380 ayrı süreçlerdir.

R3 qualifier yolu `/data/nanobaseai/editor-qualifications/v14-r3-20260918/97814b6c`, API18826/metrik19106, subnet74/75. Geçici model proxy18886/18888 yalnız75 ağını kabul eder; wrapper sonunda kaldırır. Sürüm byte kontrolü ve offline paket üretimi geçti; import/tam analiz/atıf/yedek/restore/mobil zinciri sürüyor. Bu işler bitmeden GPU'yu durduracak yeni cold-boot denemesi açılmaz.

### 18 Eylül 02:51 UTC — R3 ara doğrulama

R3 `97814b6c` kaynak monitoründe43 sayfa geçti, hata listesi boş; iş sürüyor. Paket ve offline import geçti, dolu restore analizin tamamlanmasını bekliyor. Bu ara sonuç anlamsal kabul değildir. GPU soğuk kurulum doğrulayıcısına gerçek Docker healthcheck sonucunu da zorunlu tutan kontrol eklendi; HTTP200 tek başına paket healthcheck kabulü sayılmaz. Bu yeni kontrol henüz GPU üzerinde çalıştırılmadı; ana kitap koşusu sırasında ortak modeller durdurulmayacak.

### R3 kaynak engellerinin bağımsız sayımı

Ana R3 API kaynak kayıtları doğrudan PostgreSQL kayıtlarıyla birebir karşılaştırıldı:1149 bölge,262 inceleme;248 TEXT ve14 PAGE_LABEL_CANDIDATE. İnceleme nedenleri çakışabilir:227 ikinci okuyucu uyuşmazlığı/eksikliği,139 bölgesel okuma uyuşmazlığı,117 düşük skor,191 kullanılamayan/uyuşmayan PDF; yeniden okuma durumları67 DISAGREES,171 UNSTABLE,24 AGREES. Yeniden okumanın anlaşması bütün diğer kanıtların da geçtiği anlamına gelmez. Kanıt CPU `evidence/v14-r3-live-source-triage.json`; API/PG eşliği true, uygulama yazımı0.48 kaynak kontrolünün geçmesi bu262 bölgenin doğru okunması veya tam anlamsal kabul değildir.

### R4 / anlam denetimi V5 aday düzeltmesi

R3 gerçek21/22 sayfalarında model, UNVERIFIED_REGION yer tutucusunun kimliğini destek atfı olarak seçti; kaynak kapısı bunu reddetti.28. sayfada model özgün alıntının bazı kimliklerini destek listesinde atladı. Ham yanıtlar değiştirilmedi; tanı `evidence/v14-r3-invalid-semantic-schema-diagnosis.json`.

Genel düzeltme: okunmamış bölgelerin kimliği modele `null`, `can_cite=false` gider; geometrik boşluk korunur. Yalnız doğrulanmış kimliklerin seçilebilirliği ve özgün alıntı kimliklerinin tam taşınması çıktı sözleşmesinde açıkça belirtilir. Mevcut kaynak, sözcük, olumsuzluk, atıf-altkümesi, ikinci anlam çağrısı ve kimlik kapıları gevşetilmedi. Kod sürümü `source-semantic-review-v5`, SHA256 `eeca3f2ccb5979ab36757a195dc5144050e33b498f23fde3ebe48a1293681f4a`.

Gerçek R3 API/PG kayıtları ve canlı modellerle ayrı aday bileşen koşusu:21. sayfa0 aday/0 sentez (eksik kaynak ve olumsuzluk retleri korunur),22. sayfa1 aday/1 sentez,28. sayfa4 aday/4 sentez; üçünde geçersiz semantik şema hatası görülmedi. Uygulama yazımı0, kaynak/inceleme kararı değişmedi. Kanıtlar `evidence/v14-r3-semantic-v5-page-0021.json`, `0022.json`, `0028.json` ve `v14-r3-semantic-v5-probe.log`; aday dosyasının SHA256'sı ayrıca kayıtlıdır. Çağrı metriğindeki yayın manifesti mevcut R3 çalışma ortamıdır, aday kod hashinin yerine geçmez. Bu üç sayfa tam kitap/üretim kabulü değildir.

R4 API/document imajları bağlı Linux sunucusunda ağsız derlendi ve içlerindeki modül baytları aynı hashle eşleşti: `evidence/v14-r4-build-proof.json`. Henüz canlıya alınmadı; R3 dolu restore/mobil kabulünün sürümü değiştirilmeden tamamlanması bekleniyor.
