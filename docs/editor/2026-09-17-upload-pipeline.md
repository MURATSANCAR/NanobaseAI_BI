# 17 Eylül — Otomatik PDF kabulü ve ağsız ayrıştırma

## Değişen ürün davranışı

`upload-queue-v2-20260917` yeni PDF için operatörün `probe-source.py` çalıştırması gereğini kaldırır. Arayüz eser/baskı ve yükleme oturumu açar, özgün PDF'nin SHA-256 değerini hesaplar, dosyayı yollar. `POST /uploads/{id}/complete` yeni iş için 202, `job_id` ve durum adresi verir. `GET /uploads/{id}` ile `GET /jobs/{id}` kalıcı durumu gösterir; `POST /jobs/{id}/cancel` iptal ister. Tamamlanmış yüklemeye yeni idempotency anahtarıyla complete çağrısı mevcut içerik sürümünü 201 ile döndürür; önceki anahtar kendi ilk cevabını korur.

Yeni `parser` servisi ağsız, sır erişimi olmadan, salt okunur kök ve CPU/bellek sınırlarıyla çalışır. Docker soketi verilmez. Uygulama dosya kuyruğuna kaynak hash/boyut isteği yazar; belge servisi Poppler, Docling ve Tesseract ile görüntü, yerleşim, konumlu PDF ve sayfa OCR dosyalarını üretir. Eksik denemeler ayrı dizinde kalır. Tüm çıktı ve kaynak hashleri doğrulanmadan kaynak dizini yayımlanmaz. Mevcut kaynaklar yeniden doğrulanarak kullanılabilir; bu yeni OCR ölçümü olarak sunulmaz.

Uygulama işçisi, ağsız sürecin sonucunu yeniden doğrulayıp gerçek PostgreSQL içerik sürümünü oluşturur. Kaynak metnine, konuşmacıya, analiz adayına veya editör kararına elle yazma yoktur. Yükleme ile analiz başlatma ayrı işlemlerdir; kaynağın hazırlanması anlamsal doğruluk anlamına gelmez.

## Kuyruk, kesinti ve arayüz

- En fazla iki ayrıştırma işi kabul edilir; fazlası 429 ile reddedilir. Ayrıştırıcı tek tüketicidir.
- Kuyruğa alınan yükleme mühürlenir; başka PUT ile değiştirilemez (409).
- Kesinti denemeleri ayrı ve korunmuş dizinlere yazılır; üç denemeden sonra açık hata oluşur. İş başına varsayılan süre 3600 saniye.
- İptal işaretini alan süreç alt süreçlerini durdurur. İptal ile sonuç yazma yarışı olsa da uygulama iptal edilen yüklemeden içerik sürümü oluşturmaz.
- Yükleme listesi yetkili API'den alınır; sayfa yenilenince iş tekrar seçilebilir. Tarayıcıda erişim anahtarı kalıcı tutulmaz. Kullanıcıya görüntü/OCR sayfa ilerlemesi gösterilir.
- `0005_upload_parser` migration'ı hata kodu ve bitiş zamanını kalıcılaştırır.
- Yedekleme parser/API/worker yazıcılarını durdurur. Snapshot karşılaştırmasına uploads ve outbox eklendi; eski yedeklerin karşılaştırma kapsamı korunur.

## Gerçek doğrulama

Yerel test, mock veya sentetik kitap kullanılmadı. Kullanıcının özgün 19.806.912 bayt, 48 sayfalık PDF'si; SHA-256 `94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50`.

Boş kurulum: `/data/nanobaseai/editor-qualifications/upload-v1-20260917`, API `http://127.0.0.1:18812`, ayrı gerçek PostgreSQL ve boş artifact volume. Yeni kitap arayüzden yüklendi; tüm 48 sayfa otomatik hazırlandı. Tarayıcı yenilenip yeniden giriş yapıldığında aynı yükleme bulundu. 320/390/768/1440 px genişliklerinde gerçek Chrome kontrolleri geçti. Son sürümde mevcut gerçek yüklemeye dönüş tekrar kontrol edildi.

Gerçek HTTP manifesti PostgreSQL ile birebir karşılaştırıldı; sayfa sayısı ayrıca Poppler `pdfinfo` ile, hash ve boyut özgün PDF baytlarıyla karşılaştırıldı. Sonuç: 48 sayfa, tek kaynak ve tek içerik sürümü. Yetkisiz okumalar 401, tamamlanmış kaynak tekrar kabulü idempotent.

Aynı özgün kitabın yüklemeleriyle ayrı kurulumda kuyruk sınırı, mühürleme, iptal ve parser kapalıyken kuyruğa alınan işin yeniden başlatmada tamamlanması geçti. Kaynak manifesti değişmedi, içerik sürümü çoğalmadı, editör kararı sayısı 0 kaldı. Bu işlemler ana kurulumun parser'ını durdurmadı.

Ana kurulum `127.0.0.1:8810` üzerinde aynı özgün PDF yeni yükleme kuyruğundan geçti. Yükleme `eab8e040-94b3-44db-9819-7e0de7171559`, mevcut içerik sürümüne bağlandı; parser `reused_artifacts=true` bildirdi. `b652f63c-6ec4-4f9a-aff4-00b32d220b1b` analiz kayıtlarının parmak izi değişmedi.

## Dağıtım ve bulunan hatalar

- API/worker: `sha256:480f49d883e773c0e06e01b4fc928492e493c7477a8ed2664c14fc7f55598c89`.
- Document/parser: `sha256:6710488fe6611fbe8fd845ac10371c7f0d051bcc967d7f23ac22b68422e285a9`.
- Web: `sha256:872ff409d43d75f043979951327f4434fa591f3d89358d47058ff664f461d0b4`.
- 32 backend dosyasının çalışan imajla eşliği: `0011c70cef7ac0fb6fea49645d655a01d28cd0a91d41a9dfa9608b92c504917d`.
- Sekiz web kaynak dosyası ve derlenmiş çıktı hashleri imajla eşleşti.

İlk aktarımda macOS `._` metadata dosyaları migration sanıldı; aktarım filtresi düzeltildi, Docker ve paket dışlama kuralları eklendi. İlk web imajı eski dist dosyalarını taşıdı; gerçek tarayıcı kontrolü bunu yakaladı. `build-web.py` artık kilitli bağımlılıklarla build yapar, kaynak/çıktı hash manifesti üretir; `EDITOR_VERIFY_WEB=1 scripts/verify-release.py` eski build'i reddeder. Ana yayından önce düzeltildi.

Ana sunucuya kopyalamada değişmemiş, salt okunur bağımlılık kilit dosyaları üzerine yazma reddedildi; aktarım sadece farklı baytları kopyalayacak şekilde düzeltildi. Yedek başarıyla alınmıştı; tekrar üretilmeden korundu. Bu işletim hataları başarı kayıtlarından silinmedi.

Belge çıkarımında az yazılı bölgeler için Tesseract yön algılama uyarıları görüldü ve günlükte korundu. Başarılı kaynak muhasebesi bu bölgelerin metninin doğru olduğu iddiası değildir.

Kanıtlar: ayrı kurulum `evidence/upload-ui/verification.json`, `verification-final.json`, `upload-api-verification.json`, `upload-recovery-verification.json`; ana kurulum `evidence/upload-existing-source-verification.json`, `upload-publish.log`, `upload-publish-retry.log` ve `upload-release-*.log`.

## Açık kapsam

Bu sürümün kendi offline paket/import, yedek/restore, geri yüklenen API/PG/OCR ve dört genişlikte mobil kontrolü 08:15:30 UTC’de geçti. Hedef `/data/nanobaseai/editor-qualifications/upload-release-v2-20260917/b652f63c/installation`; kaynak kanıtı `evidence/upload-installation-qualification.log`. Uploads ve outbox dahil on tablonun ve artifact dosyalarının snapshot eşliği geri yüklemeden sonra, yazıcılar başlamadan doğrulandı. Hedef servisler 08:15:33 UTC’de durduruldu; kayıtlar korundu. Genel PDF hata profillerinin tamamı, gerçek kullanıcı/kitap rolleri, düzeltme bağımlılıkları ve anlamsal analiz hâlâ açık. Asıl kitabın 828 okuyucu anlaşması/321 inceleme bölgesi değişmedi. Yeni kaynak kabulü, sahne/sentez/indeks/soru-cevap kabulü değildir. Diğer iki kitap, değişmiş baskı ve insan editör değerlendirmesi eksik; tüm planın üretim kabulü **DOĞRULANAMADI**.
