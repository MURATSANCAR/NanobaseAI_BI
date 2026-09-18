# Kaynak birimi kapsamı: v3 adayı

## Ölçülen açık

R4 nesli `08ca6877-6e30-4bb3-b1fa-767f048248e4` için gerçek CPU API yanıtları bağımsız PostgreSQL `editor.records` sorgusuyla birebir karşılaştırıldı. 865 `TEXT_AGREED/TEXT` bölge, 2.058 değişmez kaynak birimi, 127 aday bulundu. Adaylar 262 bölgeye referans veriyor; 603 anlaşılmış metin bölgesi seçilmemiş. 29 sayfa mevcut dört aday tavanına ulaşmış. Seçilmemiş bölge tek başına eksik bir anlamsal iddia kanıtı değildir; ancak “tam kitabın anlamı eksiksiz çıkarıldı” iddiasını desteklemez.

Kanıt: CPU `/data/nanobaseai/editor/evidence/v14-r4-source-unit-coverage-diagnosis.json`. Kaynak/veri/karar değiştirilmedi.

## Genel kod değişikliği

`source_unit_claims.py`, `source-unit-claims-v3` adayı:

- Değişmez 1–3 satırlık kaynak birimleri kesilmeden sınırlı gruplara ayrılır. Önceki sayfa başına dört aday sınırı grup başına uygulanır; her grup ayrı gerçek model isteğidir.
- Varsayılan sınırlar: `EDITOR_SOURCE_UNITS_PER_CHUNK=12` (1–48), `EDITOR_SOURCE_UNIT_CHUNK_CHARACTERS=12000` (1–48000), `EDITOR_SOURCE_UNIT_CHUNKS_PER_PAGE=32` (1–256). Son oluşturulan prompt da karakter sınırına karşı denetlenir. Sunucunun gerçek tokenizer/context kapısı ayrıca geçerlidir.
- Her katalog biriminin muhasebesi tutulur: `CANDIDATE`, gerekçeli `NO_CLAIM`, `NEEDS_REVIEW` veya çağrı bütçesi yüzünden `UNPROCESSED`. Aşırı uzun birim kesilmez; açık inceleme nedeni kaydedilir. Eksik/çelişkili model muhasebesi tamamlanmış sayılmaz.
- Ham model cevabı, grup birim kimlikleri ve her isteğin özgün metrics bilgisi korunur. Kesik cevapların `generation_attempts` kayıtları da kaybolmaz. Farklı gruplar sayfa rolünde anlaşamazsa rol UNKNOWN kalır.
- Bütçeye sığdığında bütün sayfanın `reading_context` verisi korunur. Seçilebilir alıntı kimlikleri yine yalnız grubun birimleridir. Tam bağlam sığmazsa sınırlı bağlam kullanıldığı, tam/kullanılan bağlam hashleri ve atlanan konum aralıkları açıkça kaydedilir. UNKNOWN grup rolleri çoğunluk oyu ile NARRATIVE yapılmaz.
- Manifest hem anlaşılmış hem kataloglanmış span kimliklerini ve kataloglanamayanları gösterir. `semantic_complete=false`, `human_accepted=false` sabittir; muhasebe tamlığı anlamsal kabul değildir.
- Mevcut alıntı/olumsuzluk/konuşmacı/anlamsal kapılar kaldırılmaz. Kitap/sayfa/karakter özel durumu eklenmedi. Gerçek sayfa numarası yalnız pilot kanıtında kullanılır.

## Entegrasyon sözleşmesi

Root tarafından `source_pipeline.interpret` kayıtlarına `result.source_unit_coverage` aktarılmalıdır. Mevcut kabul aracındaki v1/v2 allowlist v3'ü ve v2 ile aynı reversible reading-view kontrolünü içermeli; yeni manifestin birim kimlikleri, katalog hash'i, eksik işlemleri ve kabul bayrakları bağımsız doğrulanmalıdır.

Metrics yeni toplu sözleşmesi: `{method, chunks: [{chunk_index, metrics}]}`. Her iç `metrics` mevcut model cevabının request SHA, token/süre, release, code_manifest ve generation_attempts alanlarını korur. Üstte bir isteğe aitmiş gibi SHA veya model sonucu uydurulmaz. Eski tüketiciler bu yapıyı açıkça desteklemelidir.

## Kabul sınırı

Yerel test/mock/sentetik veri çalıştırılmadı. Canlı uygulama kodu değiştirilmedi. Gerçek R4 API/PG kaynaklarıyla ayrı aday modülün deterministik plan kontrolü ve tek sayfalık gerçek model pilotu ayrıca kanıtlanır. Tam R5/R6 nesil doğrulaması, anlamsal kalite ve üretim kabulü bu aday değişiklikten kendiliğinden çıkmaz.

İlk deterministik aday (SHA `305ff1afb85f01a0a6f0a6a0235fca9a1c03180f36e7b92c96d083fa7ca29fc5`): 48 sayfa, 2.058 birim, 190 planlanmış model çağrısı, sıfır bütçe dışı birim; kaynak metinleri değişmedi. Gerçek model çağrısı bu kontrolde yapılmadı. Kanıt `evidence/v14-r4-source-unit-v3-plan-check.json`.

İlk gerçek s10 pilotu (SHA `e2b7a763a47b122f92eb050181ef5e60cce6ac36a4ca2ff0ee5804f5667acdac`): 37 birim, dört çağrı, dokuz aday, 20 NO_CLAIM, sekiz NEEDS_REVIEW; tüm grup rolleri NARRATIVE. Şema veya kesilme hatası görülmedi. Bu sonuç daha çok doğru iddia üretildiğinin kanıtı değildir; anlamsal doğrulama ayrıca gereklidir. Kanıt `evidence/v14-r4-source-unit-v3-page-0010-pilot.json`.

İlk pilot yerel bağlam yüzünden özne/zamir belirsizliklerini açık bırakmıştır. Tam bağlamı bütçeye sığdığında koruyan sonraki kod değişikliği bu nedenle yapılmıştır; ilk sonuç silinmez veya başarıya dönüştürülmez. Son hash için ayrı `*-final.json` kanıt dosyaları kullanılacaktır.

Son aday SHA `d561bf39e1cb0537c8100defc6035a142433318eff8a0044c35397109b31fea4` ile deterministik kontrol tekrarlandı: aynı 48 sayfa/2.058 birim, 190 planlı çağrı, sıfır ertelenen birim, değişmeyen OCR metni, tam birim muhasebesi. Kanıt `evidence/v14-r4-source-unit-v3-plan-check-final.json`; ilk kanıt korunur. Bu kontrol model çağırmaz ve anlamsal kabul değildir.

Aynı son hash ile tek s10 regresyonu tamamlandı: 37 birim/dört gerçek çağrı, 11 aday (10 farklı kaynak biriminden), 25 NO_CLAIM, iki NEEDS_REVIEW. Dört grup da NARRATIVE, dört yanıt da ilk denemede `finish_reason=stop`; ek başarı arama tekrarı yok. Bütün gruplar FULL_PAGE bağlamıyla çalıştı; prompt boyutları 6.966, 7.047, 6.772, 3.897 karakter, atlanan bağlam aralığı yok. İki birim inceleme istediği için `all_units_have_model_disposition=false`; `semantic_complete=false` korunur. Kaynak kayıt hash'i `8cbb02d287d74eb71628de30d46ec6fcd9af7a8dfbc5e73a4c5a9fc6ae535d47`. Kanıt `evidence/v14-r4-source-unit-v3-page-0010-pilot-final.json`.

Bu pilot **anlamsal kabul değildir**: sonraki kaynak/olumsuzluk/konuşmacı/semantik kapılar ve yeni tam nesil henüz bu adayla koşturulmadı. 11 sayısı 11 doğru iddia anlamına gelmez. PARTIAL_PAGE fallback yolu bu gerçek sayfada tetiklenmedi; o yolun canlı model kabulü **DOĞRULANAMADI**. Ana uygulama veya inceleme kayıtları değiştirilmedi. Üretim entegrasyonu ve yayın root'a devredildi.

## v3 gerçek API/PG kabul aracı entegrasyonu

`scripts/verify-source-analysis.py` v1/v2 kontrollerini koruyarak v3'ü de doğrulayacak şekilde genişletildi. Önceki bağımsız API/PG eşitliği kontrolünün üstünde katalog hash'i, birebir birim muhasebesi, ham kaynak/okuma görünümü, gerçek kaynak geometrisinden yeniden kurulan bağlam, grup bölünmeleri ve bütçe dışı nedenleri kontrol eder. Adayın kendi grubunun ham cevabında yer alması ve source_unit_id seçiminin değişmemesi gerekir. Tam/kısmi bağlam hashleri, atlanan aralıklar ve sayfa rolünün çoğunlukla yükseltilmemesi ayrıca denetlenir.

Her model grubunun özgün metrics kaydı mevcut sınırlı tekrar doğrulamasından geçer. `MODEL_OUTPUT_TRUNCATED` durumunda saklanan 1–2 eksik deneme de ayrıca doğrulanır; tamamlanmış hükmün tekrar denenmesine izin verilmez. Hata kaydı context_limit taşımadığından kesilmiş çağrının bağlam bütçesi bu hata kaydından bağımsız yeniden hesaplanamaz; başarılı çağrılardaki context-limit kontrolü korunur.

Bu yeni verifier yalnız kod olarak hazırlandı. R5 qualifier dosyaları ve CPU kaynakları değiştirilmedi; yerel veya sentetik test yok. Yeni verifier'ın gerçek API/PG üzerinde v3 nesline karşı yürütülmesi **DOĞRULANAMADI**. Önceki v3 pilot/plan sonuçları yeni verifier'ın geçtiği anlamına gelmez. Gerçek yeni nesilde normal gruplar, boş kaynak sayfası ve mevcutsa kısmi bağlam/bütçe dışı/kesilmiş yanıt yolları ayrı raporlanmalıdır. Katalog muhasebesi veya NO_CLAIM model kararı tam anlamsal kapsamın bağımsız kanıtı değildir.

## Gerçek kısmi bağlam ve çağrı bütçesi kabulü

Aynı dondurulmuş aday SHA `d561bf39e1cb0537c8100defc6035a142433318eff8a0044c35397109b31fea4` ile R4'ün aynı gerçek s10 kaynağında tek kontrollü koşu yapıldı. Yalnız pilot sürecinde `EDITOR_SOURCE_UNIT_CHUNK_CHARACTERS=6000`, `EDITOR_SOURCE_UNIT_CHUNKS_PER_PAGE=4` kullanıldı; üretim yapılandırması değiştirilmedi. Amaç kısmi bağlam/bütçe yolunu çalıştırmaktı; olumlu cevap aranarak tekrar yapılmadı.

37 birim dört gerçek çağrıya ayrıldı: iki FULL_PAGE, iki PARTIAL_PAGE bağlamı. Kısmi grupların atlanan kaynak konumu aralıkları sırasıyla `[[0,2],[8,24]]` ve `[[0,5],[9,9],[12,24]]`; bunlar sayfa numarası değil sıfır tabanlı kaynak okuma konumlarıdır. Tam ve kullanılan bağlam hashleri ayrı korunmuştur. Dört birim çağrı bütçesi nedeniyle açık UNPROCESSED, üçü NEEDS_REVIEW, sekizi CANDIDATE, 22'si NO_CLAIM kaldı. Sekiz birimden toplam 10 aday çıktı; bu sayı doğruluk kabulü değildir.

API kaynakları bağımsız PostgreSQL sorgusuyla yeniden eşleştirildi. Kaynak hash'i önceki pilotla aynı: `8cbb02d287d74eb71628de30d46ec6fcd9af7a8dfbc5e73a4c5a9fc6ae535d47`. Verifier SHA `3c72cad48209c10d1cf891aedc4030141e5357aba4f1f816d16af247751617ae` içindeki bütünlük fonksiyonları gerçek, uygulamaya yazılmamış önerici cevabına açık bir şekil adaptörüyle uygulandı. Yapay kaynak, sahte API veya beklenen model cevabı üretilmedi. Değişmez alıntı/okuma görünümü, 37 birimin ledger muhasebesi, kısmi bağlam hashleri/aralıkları ve dört başarılı çağrının sınırlı tekrar kontrolleri geçti.

Kanıtlar CPU `evidence/v14-r4-source-unit-v3-page-0010-partial-context.json` ve `evidence/v14-r4-source-unit-v3-page-0010-partial-integrity.json`; önceki dosyalar korunur. Yeni dosyalar overwrite yerine exclusive-create ile yazıldı. Kaynak/inceleme/uygulama kaydı değiştirilmedi.

Bu sonuç kısmi bağlam ve çağrı bütçesi yollarının **gerçek bileşen bütünlüğü kabulüdür**. Tam v3 neslinin API/PG kabulü değildir; kaynak/olumsuzluk/konuşmacı/semantik kapılar bu pilotta çalıştırılmadı. Kesilmiş yanıt ve aşırı uzun tek birim yolları burada tetiklenmedi; bunların gerçek yeni yol kabulü hâlâ **DOĞRULANAMADI**.
