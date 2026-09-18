# Kaynağa bağlı sonuçlar: salt okunur arayüz

Yeni `SourceImpact.tsx`, kaynak inceleme ekranında tek kapalı ayrıntı kutusu olarak yerleştirildi. Kullanıcı “Kaynakta göster” ile bir gerçek bölgeyi seçerse o kaydın etkisi, henüz bölge seçmediyse mevcut sayfanın `page_claims` etkisi gösterilir. Her OCR satırı için ayrı bileşen veya istek oluşturulmaz. Ayrıntı kullanıcı tarafından açılmadan API çağrısı yoktur.

Endpoint: `GET /v1/generations/{generation}/records/{record_id}/impact?offset=0&limit=50`. Yanıtın nesil/kayıt kimliği, `SOURCE_DEPENDENCIES` kapsamı, `complete=false`, `semantic_acceptance=false`, durumları ve sayfalama sınırları kontrol edilir. Tekrarlanan kimlikler, değişen toplam/hedef veya ilerlemeyen sayfalama karışık listede birleştirilmez; kullanıcıdan listeyi yeniden yüklemesi istenir. Yeniden yükleme yeni ilk sayfadan başlar.

Bu ilk sözleşme açığı kapatıldı: yanıt artık zorunlu64hex `snapshot_sha256` içerir. Sonraki sayfa istekleri ilk yanıtın hash'ini `expected_snapshot_sha256` ile taşır; farklı hash'li yanıt birleştirilmez. Sunucu409 `IMPACT_SNAPSHOT_CHANGED` döndürürse eski liste kaldırılır ve Türkçe yeniden yükleme açıklaması gösterilir. Kullanıcı yeniden yüklediğinde snapshot bağı olmadan ilk sayfadan yeni grafik okunur. Bu sürüm henüz canlıya yayımlanmış veya kabul edilmiş sayılmaz.

Nesil/hedef değişiminde bileşen yeniden kurulur ve kapalı başlar; eski istek iptal edilir. Token değişiminde eski yanıt gösterilmez; aktif istek serial/token kontrolüyle sınırlandırılır. Kutuyu kapatma ve unmount da isteği iptal eder. Kullanıcı arayüzünde UUID, record_key veya teknik reason kodu basılmaz; kayıt türleri ve backend nedenleri Türkçedir.

“Bağları güncel” yalnız yapısal kaynak ilişkisini anlatır; içerik doğruluğu/insan onayı değildir. Grafik eksik olabilir açıklaması her açılışta görünür. Sıfır bağlı sonuç “hiç bağlantı yok” iddiasına dönüştürülmez. İnceleme veya kaynak değişikliği yapan düğme yoktur.

`main.tsx` yalnız bileşen importu ve tek kaynak kartı bağlantısı için değişti. CSS kart/satır/metin sarması ve en az44px kontroller ekler; sayfa taşması gizlenmez. Bileşende kitap/sayfa/ad/hash/beklenen cevap özel durumu yoktur; yalnız seçilen gerçek kaydın kimliği kullanılır.

## Kabul durumu

Backend sözleşmesi `figure_identity_recovery` göreviyle koordine edildi. Yerel test/build, mock veya deployment yapılmadı; uzak R7 kaynak koşusu ve qualifier değiştirilmedi. Yeni endpoint + frontend yayımlandıktan sonra gerçek kayıt/API/bağımsız PG üzerinden hedef/etki kümesi, tembel yükleme, sayfalama, hedef/nesil değişiminde iptal ve320/390/768/1440px görünüm kabulü gerekir. Şu anda bunların gerçek ürün kabulü **DOĞRULANAMADI**.

## Hazırlanan uzak gerçek arayüz kabulü

Yeni `scripts/verify-source-impact-ui.cjs` çalıştırılmadan hazırlandı. `EDITOR_VERIFY_REMOTE_HOST`, `EDITOR_VERIFY_ROOT`, `EDITOR_VERIFY_BASE_URL`, gerçek `EDITOR_VERIFY_GENERATION_ID` ve `EDITOR_VERIFY_IMPACT_RECORD_ID` gerekir; kitap kimliği koda gömülü değildir. Ayrıca backend'in ayrı `verify-source-impact.py` gerçek API/PG kabul çıktısının yolu `EDITOR_VERIFY_IMPACT_REFERENCE_PROOF` ile verilmelidir. Bağımsız kanıtın PASS, aynı nesil/hedef/snapshot ve anlamsal kabul false olması zorunludur; kanıt dosyasının hash'i UI raporuna bağlanır.

Script gerçek giriş/seçimden sonra kutu açılmadan sıfır impact isteği olduğunu, gerçek yanıtın hedef kimliğini PG ile ve bütün grafik sonucunu aynı snapshot bağımsız kanıtıyla karşılaştırır. Gerçek `has_more` varsa tüm sayfaları snapshot parametresiyle takip eder; yoksa sayfalama NOT_EXERCISED kalır, yapay kayıt oluşturulmaz.320/390/768/1440px taşma/ekran görüntüsü, uygulama mutation isteği olmaması ve önce/sonra kayıt/review hashleri kontrol edilir. Fragment için DOM kimlik kancası yoksa o hedef reddedilir; gerçek source_span veya page_claims seçilebilir.

409 çatışması oluşturmak için gerçek kaynak değiştirilmez. Böyle bir gerçek durum bu koşuda yoksa409 yolu NOT_EXERCISED olarak kalır. Geç cevap/nesil geçişi kabulü de bu ilk scriptin kapsamı dışında açık kalır. Scriptin kendisi henüz gerçek ortamda çalıştırılmadı; root yeni yayından sonra yürütür.

## İzole uzak aday hazırlığı

CPU sunucusunda `/data/nanobaseai/editor/runtime/impact-web-candidate-20260918` altında kilitli npm bağımlılıklarıyla TypeScript/Vite ve Docker build geçti. Ana R7 web/backend yayını değiştirilmedi. Aday image `nanobase-editor-web:impact-candidate-20260918`, manifest SHA `24b8476a1d5b5db80d1dd5b1209c364d1cb62fb4793e81784383a05689da0821`. Loopback18837 nginx yalnız GET/HEAD API isteklerini bağımsız aday API18836'ya geçirir. Build ürün kabulü değildir; gerçek API/PG kanıtı ve tarayıcı kabulü bekleniyor.

GET-only kabul kontrolü artık yalnız seçilen nesilde aktif iş olmamasını zorunlu tutar. Başka nesilde ana koşunun sürmesi kontrolü engellemez; seçilen neslin bütün kayıt/review hashleri korunur. Böylece salt okunur aday incelemesi ana koşuyu durdurmaz veya onun kayıt değişimlerini kendi kanıtı olarak kullanmaz.

## Gerçek izole aday kabulü — PASS

CPU üzerindeki gerçek PostgreSQL ve GET-only aday API18836/web18837 ile `source-impact-ui-256a9421-b9f9-4f55-b0b0-3061e03952b8/verification.json` PASS. Tam uzak kanıt kökü `/data/nanobaseai/editor/evidence/`. Bağımsız API/PG grafik kanıtı `source-impact-20260918T065246080334Z.json`; iki kontrolün snapshot SHA değeri `5ce0fdcfc035fc197cbe99dc552838a9c55c1f6d9d0ba06cca33257a830bcda1`.

Ayrı regresyon girdisi: gerçek nesil `08ca6877-6e30-4bb3-b1fa-767f048248e4`, kaynak kayıt `dd24320c-8545-5e52-b0e5-ed6b68e6e2e2`. Bu kimlikler üretim kodunda veya özel kabul kuralında kullanılmaz.134 bağlı kayıt gerçek API'den üç sayfada okundu; sonraki istekler ilk snapshot'a bağlıydı. Kutuyu açmadan impact isteği yoktu. Gerçek hedef/kayıt kimlikleri bağımsız PG ile aynıydı.320/390/768/1440px ekran görüntüleri aynı kanıt klasöründe `impact-{width}.png`; yatay taşma, tarayıcı hatası, başarısız HTTP ve uygulama yazma isteği yok. Kaynak kayıt MD5 `982e6aee1814facbd612e179afe1df3e`, review MD5 `d41d8cd98f00b204e9800998ecf8427e` önce/sonra aynı. Script SHA `c10e4f97b1eacdb310037cb2718f222c3afe60b647c8ad15fdf595bc3f6b0d62`.

İlk kabul scripti wrap-label içindeki seçeneklerin erişilebilir ada katılmasını hesaba katmayan exact seçici nedeniyle durdu; teşhis kaydı gerçek ekranın ve API'nin açık olduğunu gösterdi. Genel kontrol seçicisi combobox rolü + etiket başlangıcıyla düzeltildi. İlk başarısız kanıtlar `source-impact-ui-324f97af-b87e-4716-a295-958bce55a79d` ve teşhis `source-impact-ui-1d4018e9-351e-45ea-9fcb-d7c8541d4818` korunur; ikisinde de kaynak/review değişmedi. Ürün verisi veya beklenen cevap değiştirilmedi.

Bu sonuç **izole aday** kabulüdür; ana R7 yayını değiştirilmedi ve ana üretim kabulü değildir. Hedefin UNRESOLVED durumu başarıya çevrilmedi. Graph `complete=false`, `semantic_acceptance=false` kaldı. UI409 çatışma yolu ve geciken yanıt sırasında nesil/hedef değişimi halen DOĞRULANAMADI; gerçek kaynak mutasyonu yaparak zorlanmadı. Kaynakları değiştirmeyen backend stale-snapshot409 kontrolü ayrı API kanıtında bulunur.
