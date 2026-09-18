# Kaynak soru arayüzü: gerçek kabul koşusu hazırlığı

Yeni `scripts/verify-source-question-ui.cjs` yalnız açıkça adlandırılmış uzak Linux uygulama sunucusunda çalışacak şekilde hazırlandı. **Henüz çalıştırılmadı.** Yerel test/mock/ağ simülasyonu/deployment yapılmadı.

Gerekli ortam değişkenleri: `EDITOR_VERIFY_REMOTE_HOST` gerçek uzak hostname, `EDITOR_VERIFY_ROOT` kurulum dizini, `EDITOR_VERIFY_BASE_URL=http://127.0.0.1:8810`, `EDITOR_VERIFY_GENERATION_ID` açık gerçek UUID. Gerçek token yalnız kurulumun `secrets/api_token` dosyasından okunur; kanıtlara yazılmaz. Playwright mevcut uzak `runtime/browser-check` kurulumundan, Chrome uzak `/usr/bin/google-chrome` üzerinden kullanılır.

## Kontrollü akış

1. Aktif herhangi bir iş veya parse varsa koşu yeni soru oluşturmaz. Gerçek API listesindeki kitap ve analiz, bağımsız PostgreSQL eşlemesiyle seçilir; kaynak preview kapısı hazır olmalıdır.
2. Gerçek tarayıcıyla giriş, kitap/analiz seçimi ve Soru & cevap sekmesi açılır. 2 ve 1001 karakter sınır denemelerinde düğmenin kapalı olduğu ve POST/iş oluşmadığı kontrol edilir.
3. Gerçek formdan sırayla iki genel soru gönderilir: “Kaynaklarda anlatılan olaylardan hangileri doğrulanabiliyor?” ve “Kitaptaki bütün karakterlerin kesin doğum tarihleri nelerdir?” Kitaba özgü beklenen cevap verilmez. Her iş terminal duruma gelmeden ikinci soru başlamaz; üst bekleme sınırı 15 dakikadır.
4. POST gövdesi, iş/nesil/mode cevabı ve idempotency anahtarı kaydedilir. API cevabı bağımsız PG cevabıyla tam JSON olarak karşılaştırılır. Kaynak span metni/bbox/render hashleri, pasajlar, kanıt sayfaları, alıntı hashleri ve reversible reading-view kontrolleri yapılır. Yanıt metni yalnız kaynak ve ilgi denetiminden geçen iddia metinlerinin birebir birleşimi olmalıdır.
5. İlk soruda gerçek PARTIAL veya INSUFFICIENT_EVIDENCE sonucu korunur; kalite değerlendirmesi ayrıca gerekir. Desteksiz doğum tarihi sorusu INSUFFICIENT_EVIDENCE değilse koşu FAIL olur; cevap düzeltilmez ve olumlu sonuç arayarak yeniden denenmez.
6. Aynı sorunun kaydı yeniden açıldığında ilave POST veya iş oluşmadığı doğrulanır. Gerçek cevapların arayüzde gösterildiği kontrol edilir; 320/390/768/1440 genişliklerde taşma kontrolü ve ekran görüntüsü alınır.
7. Önce/sonra kaynak kayıtları, özgün source probe kayıtları, inceleme kararları ve nesil durumu korunmalıdır. Yalnız cevap/pasaj/arama indeksi kayıtlarının sistem tarafından oluşturulması beklenir. Hata halinde kanıtlar korunur; yalnız bu koşunun gözlenen istek anahtarları, gerçek soru payload'u ve başlangıç zamanı ile sahipliği doğrulanan işi API üzerinden iptal edilebilir. Başka iş durdurulmaz.

Kanıtlar UUID'li `evidence/source-question-ui-*` dizinine yazılır. Koşu PASS olsa bile `semantic_acceptance=false` ve `quality_review_required=true` kalır. İnsan editör kabulü/activate yapılmaz. Qdrant'ın nihai vektör/içerik indeksi kabulü bu scriptin dışında root tarafından yapılacaktır.

## Açık kabul durumu

Kod statik olarak hazırdır; yeni endpoint/worker/frontend yayımlandıktan sonra gerçek koşu gerekir. Gerçek API/PG, tarayıcı, negatif soru, yeniden açma ve mobil kabulünün tamamı şu anda **DOĞRULANAMADI**. Kaynak metinlerinin hash bütünlüğü anlamsal doğruluğun bağımsız insan referansı yerine geçmez.
