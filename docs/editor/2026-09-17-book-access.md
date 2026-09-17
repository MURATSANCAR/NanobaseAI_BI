# 17 Eylül — Kullanıcı ve kitap kapsamlı erişim

## Durum

Ana sunucu `book-access-v3-20260917` sürümüne yükseltildi. Gerçek API/PostgreSQL, mevcut 48 sayfalık kitabın tüm kaynak kayıtları ve yönetici/okuyucu mobil kontrolleri geçti (`MAIN_ACCESS_V3_PASS`). Tüm roadmap veya farklı gerçek kişilerle üretim kabulü verilmedi. Bu sürümün offline paket ve restore kabulü ayrıca yürütülüyor.

## Genel sistem düzeltmesi

`access.py` her istek için kullanıcı kimliği, anahtar rolü ve kitap kapsamı üretir. Kurulum anahtarı mevcut `installation-operator` yöneticisini korur. Yeni kullanıcılar, kitap grant'leri ve kapsamlı anahtarlar `0006_book_access` migration'ında ayrı tablolardır. Yeni anahtarın kendisi yalnız ilk oluşturma cevabında gösterilir; DB'de SHA-256 hash'i vardır. Audit ve idempotency kayıtlarına anahtarın açık değeri yazılmaz. İptal/devre dışı bırakma sonraki istekte denetlenir.

Kitap sahibi, açık kitap yetkisi ve anahtarın daha dar kapsamı birlikte uygulanır. READER yazamaz; EDITOR yalnız erişebildiği kitapta yazabilir. ADMIN kullanıcı/yetki yönetimini yapabilir. Kitap kapsamlı bir yönetici anahtarı genel yönetim uçlarını açmaz. Kaynak manifestinin SHA ile doğrudan okunması da kitap yetkisine bağlandı; kapsam dışı kaynak/iş/listeler içerik sızdırmaz.

İdempotency kayıtları anahtar kimliğiyle ayrılır. Başarılı mutation sırasında erişilen kitaplar kaydedilir; önceki cevap tekrar sunulmadan güncel kitap yetkisi yeniden kontrol edilir. Eski tek operatör kayıtları korunur.

`GET /me` arayüz yetkilerini verir. Yönetici paneli kullanıcı, anahtar, kitap grant'i ve anahtar iptalini sağlar. Okuyucu yükleme veya yönetim kontrollerini görmez. Kimlik bilgileri tarayıcı kalıcı depolamasına yazılmaz.

## Gerçek kabul — aday sürüm

Ortam `/data/nanobaseai/editor-qualifications/upload-v1-20260917`, gerçek HTTP API `127.0.0.1:18812`, ayrı PostgreSQL ve kullanıcının özgün PDF'si. Yerel/mock/fixture/sentetik kitap kullanılmadı. Mevcut gerçek kurulum operatörünün kısıtlı anahtarları oluşturuldu; hayalî kullanıcı hesabı eklenmedi.

- Kitap kapsamlı okuma geçti; boş kitap kapsamı listeyi boş döndürdü, bilinen kaynağın doğrudan adresleri 404 verdi.
- Okuyucu yükleme/analiz başlatma ve yönetim uçları 403 verdi. Yetkili editör anahtarı aynı özgün PDF'yi mevcut baskıya yükleyebildi; aynı içerik sürümü korundu.
- Anahtarın yalnız hash ile saklandığı PostgreSQL'den bağımsız karşılaştırıldı; audit/idempotency'de açık anahtar bulunmadı. Oluşturma isteği tekrarında anahtarın açık değeri tekrar verilmedi.
- Kaynak manifesti değişmedi, editör kararları 0 kaldı. Test anahtarları API üzerinden iptal edildi; iptal sonrası 401 doğrulandı.
- Yönetici ve okuyucu için 320/390/768/1440 px gerçek Chrome kontrolleri geçti; yatay taşma ve kalıcı tarayıcı anahtarı yok. Çıkış anahtarı temizledi.
- İlk negatif metrik kontrolünde doğrulama betiği yanlış `/v1/metrics` adresini kullanarak 404 aldı; gerçek `/metrics` ile tekrar 403 doğrulandı. Bu bir ürün düzeltmesi değildir; başarısız deneme günlüğü korundu.

Kanıtlar: ayrı kurulum `evidence/access-api.log`, `access-api-retry.log`, `access-verification.json`, `access-ui.log`, `access-ui/verification.json`. Adayın 35 backend dosyası çalışan imajla eşleşti (`9caf110aa9b5531f90f5795348f4d0dea090bad3d3df44af8c93ab4d4fcb999d`); dokuz web kaynak dosyası/çıktı hashleri doğrulandı. Sonraki kod değişikliğine bu sonuç otomatik aktarılmaz.

## Açık kabul

Farklı gerçek kişiler, gerçek kitap paylaşımları ve kuruluşun işletim politikaları için kullanıcı bilgisi istendi; henüz gelmedi. Mevcut operatörün sınırlı anahtarlarıyla yapılan kontrol, kişiler arası bütün rol matrisinin kabulü değildir. Ana dağıtım ve dolu analiz kayıtlarıyla yetki kontrolü tamamlandı; yeni release'in offline restore denetimi henüz sonuçlanmadı. Kaynak/konuşmacı ve anlamsal kabul bağımsız olarak açık kalır.

## Son sürüm: ana sunucuda gerçek kabul

`book-access-v3-20260917` backend SHA-256: `644a338bb22b793e5408ab6b61c635ed30df23995d40a0ee11442eaa523f245a`; 35 backend ve dokuz web kaynak dosyası çalışan imajla eşleşti. Web imajı `book-access-v1-20260917`, parser/document imajı `upload-queue-v2-20260917` olarak kaldı.

Son iki düzeltme: editör önizlemesi yazma yetkisi gerektirir; hash ile hazır kaynak bağlama yalnız genel yöneticiye açıktır. Kitap sahibinin örtük erişimini grant kaldırma ile kaldırmış gibi göstermek 409 ile engellenir. Gerçek kaynak, analiz kayıtları ve inceleme kararlarının değişmediği bağımsız DB parmak izleriyle kontrol edildi. Ölçümde kullanılan kapsamlı anahtarlar API'den iptal edildi ve 401 denetlendi.

Ana sunucu kanıt kökü `/data/nanobaseai/editor/evidence/`: `access-publish.log`, `access-release-verify-release.py.log`, `access-release-verify-access.py.log`, `access-release-reader-ui.log`, `access-release-ui.log`. Dört genişlik: 320/390/768/1440 px. Okuyucunun gerçek kaynak/OCR/bbox ekranları ve yönetici/okuyucu kontrol görünürlüğü geçti; yatay taşma yok.

Bu kabul, 321 açık kaynak bölgesini veya konuşmacı belirsizliklerini çözmüş sayılmaz.
