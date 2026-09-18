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
