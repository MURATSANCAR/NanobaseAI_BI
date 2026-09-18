# V13 hazırlığı: küçük kaynak bölgeleri ve sayfa bağlamı

V13-r1 API/worker, ağsız document/reread tüketicisi ve web yayımlandı; tam kitap kabulü değildir. Kitap içeriğine elle müdahale edilmez.

## Güncel R2 kabul koşusu

Backend/API/worker/document `source-analysis-v13-r2-20260918` yayımlandı;46 dosya hash eşliği `4a2bff06aa1212f87e575a9d0c0e9ce422422d3f1c6a1138c7029174375b4588`, gerçek altyapı/API/PostgreSQL denetimi geçti. Eski V13-r1 işinin API retry denemesi kod manifesti değiştiği için `PIPELINE_VERSION_CHANGED_NEW_GENERATION_REQUIRED` ile doğru biçimde reddedildi; bu koruma kaldırılmadı, önceki kayıtlar değiştirilmedi.

Yeni iş `13640da6-8622-476e-82e2-ec259bd10401`, nesil `c046c684-8821-4770-bab3-fb7dc9c25b05`; kaynak atası V13-r1 neslidir. Kaynaklar mevcut koşuda yeniden denetlenir. Kanıt `evidence/source-analysis-v13-r2-start.json`; salt okunur izleyici ayrıca başlatıldı.

Fragment UI ikinci denemesinde320px taşma bulundu. Kaynak kartı değil, FAILED durumundaki uzun teknik hata kodu taşırıyordu. İşlem kartına metin kırılması, anlaşılır hata mesajı ve açılır teknik ayrıntı eklendi; kaynak/kimlik/anlam aşamalarının gerçek adları ilerleme ekranına bağlandı. Tanı ekran görüntüsü `evidence/v13-fragment-ui-r2-diagnostic/source-span-overflow-320.png`. Web R3 uzak build/kabul aşamasındadır.

Web `source-analysis-v13-r3-20260918` yayımlandı ve dokuz kaynak/çıktı dosya hash eşliği geçti. Aynı başarısız eski işin gerçek fragment verileriyle320/390/768/1440px tekrar kabulü PASS: ham küçük bölge, ham üst satır, okuyucu adı ve iki bbox gezinmesi API ile eşleşti; altı sekmede taşma/dokunma kontrolü geçti. Kanıt `evidence/v13-fragment-ui-r3/verification.json`. Yeni R2 neslinin nihai arayüz kabulü ayrıca yapılacaktır.

GPU gateway V2 doğal olarak603 saniye boşta kaldığında OCR'ı durdurdu; hiçbir manuel model stop yapılmadı. Gerçek kitap kırpımıyla yeniden açılma, HTTP200, sağlıklı durum ve start/stop sayaçları1/1 doğrulandı. GPU kanıtı `/data/paddleocr-vl/candidates/editor-gateway-v2/natural-idle-wake-acceptance/result.json`. Yoğun eşzamanlı istek/idle sınırı stres kabulü bunun dışında açık kalır.

## Canlı V13-r1

Yayın `source-analysis-v13-r1-20260918`, pipeline `source-spans-v13`; 46 backend dosyasının kaynak/imaj eşliği `b87cc35c7998650cbdb060218df7cc5899920678d58f1cac984546b92c542b76`. Yeni iş `4ca9b23a-7027-4909-b49f-1fd26c93b497`, nesil `18417f1b-d9db-4873-aeb8-b8c719fc0d0d`; V12 ölçümleri kaynak olarak tekrar kullanılır. Öncelik sayfaları yalnız koşu parametresidir. Salt okunur sayfa izleyicisi ayrıca başlatıldı.

Son kaynakla sayfa bağlamı gerçek pilotu 41 API/PG kaydı ve parent hash kontrolünü geçti; iki model çağrısı, kapsam/kimlik belirsizliklerini görünür koruyarak yalnız sayfa amacını kabul etti. Aynı hashlerle cross-page kontrolü 22 sayfada 1 sınırlı söz bağlantısı, 0 genel kimlik, 0 scope_error verdi. Kanıtlar `page-context-0eb7d199-cebc-4454-96f6-1d5cb1685986-0029-75505f9c06f8-fd8be57224ff.json` ve `cross-page-attribution-0eb7d199-cebc-4454-96f6-1d5cb1685986-c01ff688fefd-5de054fe0542-5630f696aae4.json`.

Dağıtım sonrası altyapı denetimi OCR STOPPED durumunu arıza saydı. `verify.py`, yalnız on_demand=true, gateway_reachable=true ve state=STOPPED için beklemeyi kabul edecek biçimde düzeltildi; diğer servis hataları hâlâ engellenir. Çıktı açıkça bunun OCR uyanma/çıkarım kabulü olmadığını belirtir. Gerçek altyapı kontrolü tekrar geçti. Yeni kitabın OCR gerektiren çağrısının otomatik uyanması ayrıca izleniyor. Kanıt `evidence/source-analysis-v13-infrastructure.log`.

Yeni koşu sırasında pasif gateway ölçümü running=true, healthy=true, active_requests=1 gösterdi; önceki STOPPED durumundan otomatik uyanma görüldü (`evidence/v13-ocr-auto-wake-status.json`). Bu ölçüm tek başına bütün idle/istek yarış matrisi kabulü değildir.

Webin dokuz kaynak dosyası ve dağıtım çıktıları imajla eşleşti. V13 web üzerinde gerçek V12 kimlik/inceleme/sentez kayıtları 320/390/768/1440 px kontrolünü geçti; ham API eşliği, kaynak gezinmesi ve tam kitap kabulü sınırı doğrulandı. Kanıt `evidence/v13-web-v12-semantic/verification.json`, terminal `evidence/v13-web-v12-semantic.log`. V13'e özgü dolu fragment/bağlam/diyalog kartlarının kabulü yeni kayıtları bekler.

V13-r1 external uygulama paketi `/data/nanobaseai/editor-qualifications/source-analysis-v13-r1-external-20260918` oluşturuldu; bütün paket dosyaları ve Docker imaj kimlikleri importta geçti. İlk import komutunda dosya adı alt çizgiyle yanlış yazıldığı için Python dosyayı bulamadı; ürün çalışmadı/veri değişmedi, log korundu. Doğru `import-bundle.py` komutunun kanıtı `evidence/source-analysis-v13-import-r2.log`. Qwen/OCR GPU imaj/ağırlıkları bu uygulama paketine dahil değildir. V13 ayrı restore kabulü açık kalır.

Git: uygulama kodu yerel main üzerindedir; `git push origin main` HTTPS kullanıcı kimliği bulunamadığı için başarısızdır. Sunucu yayını ile yerel kaynak hash eşliği doğrulanmıştır; origin güncellendi iddiası yoktur.

## V12 kapanış ölçümü ve devam

## V13-r1 gerçek hata ve R2 düzeltmesi

Kaynak aşaması48/48 ve anlamsal kayıtlar tamamlandıktan sonra iş FAILED/TypeError oldu. PostgreSQL kayıt kimlikleri UUID nesnesi, API kimlikleri JSON string olduğundan cross-page hash hesabı üretim çağrısında çöktü. Hata gerçek PostgreSQL kaydıyla yeniden üretildi. Hash yalnız UUID türünü kanonik stringe çevirir; genel default=str ile bilinmeyen nesneler sessiz kabul edilmez. Verifier artık aynı gerçek kayıtları hem API şekliyle hem yerel PostgreSQL UUID türleriyle çalıştırıp sonuç eşliğini karşılaştırır.

Tam48 sayfalık ve27 gerçek fragmentli kontrol ayrıca iki yanlış engellemeyi gösterdi: meşru NEEDS_REVIEW fragmentleri bozuk provenance sayılıyor, uzak bir sayfanın okunmayan balonu bütün kısa alıntıları engelliyordu. Cross-page V7, üst kaynak/hash/geometri kontrolünü korur; okunması reddedilmiş geçerli fragmenti kaynak olarak kullanmadan atlar. Eksik balon kapsamı mevcut komşu sayfa mesafesi sözleşmesiyle sınırlıdır; genel karakter birleştirme hâlâ yoktur. Tam gerçek API/PG ve native-type eşliğinde48 sayfa,1 sınırlı söz bağlantısı,0 genel kimlik,0 scope_error geçti.37. sayfanın desteklenmeyen balonu reddedilmeye devam etti. Kanıt `cross-page-attribution-18417f1b-d9db-4873-aeb8-b8c719fc0d0d-cee662005cd3-persisted-f15374332517.json`.

Yeni fragment mobil kontrolünde kaynak satırı henüz yüklenirken UI'nın bulunamadı mesajı gösterdiği görüldü. Yüklenme durumu ayrıldı; kabul kontrolü de tamamlanan gerçek kaynak isteğini bekler. İlk başarısız `v13-fragment-ui.log` korunur. R2 web uzak build geçti; yayın sonrası aynı dört genişlik tekrar koşulacaktır. Bu düzeltmeler ham kitap kayıtlarını değiştirmez; başarısız iş API retry ile mevcut checkpointlerden devam ettirilir, yeni çalıştırılan aşamanın yayın sürümü ayrıca belirtilir.

V13 kaynak kontrolleri de 48/48 geçti; hata listesi boş. Ardından 48 fragment_checks ve 27 yeni source_fragment üretildi:9 TEXT_AGREED/18 NEEDS_REVIEW. İlk kaynak kayıtları değişmedi. 29. sayfanın kaynaklı bağlam sınıflandırması ana koşuda NARRATIVE/eligible=true geçti; altı bağlam kaydının dört tanesi okunmuş hedef metni olmadığı için UNKNOWN kaldı, künye sayfası anlatı kabul edilmedi. Kimlik/anlam aşaması ve yeni dolu UI kabulü bu ölçüm anında sürüyordu.

V12 nesli `2d774b82-e04f-45a3-92fc-eadaa8a37934` 48/48 teknik kaynak kontrolüyle tamamlandı; hata listesi boş, sonuç NEEDS_REVIEW. Gerçek API ve bağımsız PostgreSQL kontrolünde 48 evidence, 1.149 source_spans, 48 page_claims, 48 figure_identity, 12 figure_comparisons, 48 semantic_reviews ve bir semantic_synthesis kaydı eşleşti. 52 iddia sentez adayı olarak kapıları geçti; bu bütün kitabın anlamsal kabulü değildir. Kanıt `evidence/source-analysis-2d774b82-e04f-45a3-92fc-eadaa8a37934.json`; application_writes=0, semantic_acceptance=false.

V13 API ve document aday imajları sunucuda mevcut bağımlılıklardan ağsız build edildi; web adayı da ayrı oluşturuldu. Henüz aktif hizmetler değiştirilmedi. Üç paralel ajan kullanım limitine takıldığı için ana oturum entegrasyonu devraldı. Son kaynak hashine ait olmayan bağlam kanıtı cross-page verifier tarafından CONTEXT_MODULE_HASH_MISMATCH ile reddedildi; mevcut kaynakla yeni gerçek ölçüm başlatıldı. Eski kanıt yeni kodun kabulü yerine kullanılmaz.

## Paralel çalışma

- Kaynak/kimlik kolu: okunamayan büyük satırın içinden bağımsız ölçülen küçük bölge, ham okuyucu metni, noktalama kapıları; sayfa amacı için kaynak kapsamı notu ile kararı engelleyen belirsizliğin ayrılması.
- Anlamsal kabul kolu: bağlam kararının sürüm/hash ve ayrı denetim koşullarının sayfalar arası atıf kapısında korunması; gerçek API/PostgreSQL eşliği.
- Arayüz kolu: küçük bölge ve değişmeyen üst kaynak, otomatik sayfa amacı, yalnız doğrulanan söz parçası bağlantısı; ayrı web imajı ve dört genişlik kabul hazırlığı.
- Entegrasyon: API kayıt türleri, kuyruk batch kimliği, aynı kaynak koduyla uygulama ve ağsız okuyucu imajı hazırlığı. Yeni kuyruk üreticisi ile eski tüketici karıştırılmadan yayımlanmalıdır.

## Gerçek ölçüm ve açık sınır

R9 neslindeki gerçek 28. sayfa kırpımında PP-OCR/Tesseract sözcük eşliği ve ayrı noktalama desteğiyle küçük bir metin kaynağı üretildi. İlk başarısız ölçümler korunur. Üst satır hâlâ NEEDS_REVIEW; hiçbir ham çıktı düzeltilmedi. Bu sonuç bütün balonu veya karakterin genel kimliğini doğrulamaz.

29. sayfa bağlam pilotunda 41 API/PostgreSQL kaydı ve fragment üst kaynak hash/geometrisi doğrulandı. Qwen NARRATIVE önerdi, dört kaynak atfı geçerliydi; okunmayan bölgelerin kapsamına ilişkin belirsizlik nedeniyle mevcut kapı kabul vermedi. Ayrı hakem çalışmadığı için öneri, doğrulanmış bağlam olarak kullanılamaz. Sayfalar arası negatif kontrol 22 gerçek sayfada bu öneriyi doğru biçimde reddetti. Yeni tipli belirsizlik şeması bu ayrımı genel olarak ele alır; kabul üretmek için kitaba özel istisna eklenmez.

Kanıtlar ana sunucunun `evidence/` dizininde:

- `page-context-0eb7d199-cebc-4454-96f6-1d5cb1685986-0029-6072b5f38bbc-16dcc078b697.json`
- `cross-page-attribution-0eb7d199-cebc-4454-96f6-1d5cb1685986-bb5ad0f31aac-66543d89ec3e-900ca7f65c1c.json`

Yerel test çalıştırılmadı. Aday sürüm için gerçek üretici/tüketici kuyruğu, yeni neslin tam API/PostgreSQL kontrolü ve dolu yeni arayüz kartlarının mobil kabulü henüz tamamlanmadı. Teknik kaynak bütünlüğü ile kitabın anlamsal kabulü ayrı tutulur.
