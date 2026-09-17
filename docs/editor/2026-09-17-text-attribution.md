# Açık metin atıfları ve kesilen yüklemeye devam

## Uygulama

`source-spans-v5`, aynı kaynağın yeni neslinde sayfa başına `character_evidence` kaydeder. Kaynağı uyuşan Türkçe alıntı + bildirme fiili + açık ad yapıları işlenir. Belirsiz/kısmi/ortak özne, başka sayfa, doğrulanmamış bölge ve birden çok atıf eşleşmesi konuşmacı üretmez. Claim bağlantısı yalnız STATEMENT, MATCH ve alıntı bölgesi içinde tek yönlü alıntı eşliği ile kurulabilir. Yazılı konuşmacı etiketi görsel figür kimliği veya olayın doğruluğu değildir; anlamsal sentez kapısı kapalıdır.

Arayüz alıntı, yazılı ad ve gerçek kaynak kutusuna dönüşü gösterir. Aynı yazılan adlar yalnız yazım altında listelenir; karakter kimliği birleştirilmez. Yükleme arayüzü CREATED oturumuna özgün PDF ile, RECEIVED oturumuna dosyayı tekrar göndermeden devam eder. Kaynağın boyutu/hash'i sunucuda doğrulanır.

## Gerçek kabul ortamı

Sunucu `nanobase-direct`; mevcut gerçek yedekten geri yüklenmiş bağımsız kurulum: `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation`; API `http://127.0.0.1:18810`. Özgün PDF kullanıldı; yerel/yapay veri testi yapılmadı. Yeni nesil `8c780a30-fc9b-4ad7-a576-317e6142ad3f`, iş `93d1ccc7-31a4-4525-885d-05ed683aa5af`; 48/48 tamamlandı, NEEDS_REVIEW.

- Backend 36 dosya çalışan konteynerle aynı: `a194d142eeddb7aae2ec8d296dec421459a573cd5d243542c18586ef7c1ce74f`. Web kaynak/çıktı hashleri eşleşti.
- Web ilk derlemesinde nullable kayıt TS18048 bulundu; açık kayıt kontrolü eklendi, gerçek sunucuda tekrar derleme geçti. Önceki başarısız log saklandı.
- 320/390/768/1440 px, altı sekme, metin atıf alıntısı/adı/API eşliği ve doğru kaynak kutusu geçti; taşma yok. Kanıt `evidence/text-attribution-ui.log` ve `evidence/review-ui/`.
- Tamamlanmış sayfa sınırını donduran doğrulayıcı çalışırken iş bittiğinde bütün sayfaları denetlenmiş sanıyordu; başlangıç iş durumu ve tam kapsama bilgisi ayrıldı. Son kontrol tamamlanmış nesilde yeniden yapılıyor. İlk hata `evidence/text-attribution-verify-final.log` ile korundu.
- Kaynak yapısı/API/PG betiği geçti: `evidence/text-attribution-source-check.log`.
- Kesilen yükleme tarayıcı kabulü dört genişlikte iki durum için sürüyor. Denetçi düğme metnindeki ok ve ortak CSS sınıfını yanlış seçti; seçiciler düzeltildi, gerçek akış tekrarlandı. API yanıtı taklit edilmedi; tarayıcı PUT/complete isteği kesilip aynı gerçek yükleme sürdürüldü.

## Açık kapsam

Ana kurulumun yeni yayın kabulü, son atıf denetimi ve yükleme matrisi henüz kapanmadı. 29. sayfadaki görsel figür–karakter kimliği, inceleme bölgeleri ve doğrulanmış bütün-kitap analizi bu özelliğin tamamlanmasıyla kapanmış sayılmaz. Farklı gerçek kitaplar, ikinci baskı ve insan editör rubriği olmadan planın tüm kabul maddeleri tamamlandı denmez.

## Restore ortamı son kabul

Tam neslin atıf denetimi geçti: 48 sayfa, 10 açık atıf; mevcut model claimlerine bağlanan konuşmacı 0. Dolayısıyla dolu claim-speaker dalının kabulü DOĞRULANAMADI; atıfların kaynakları ve arayüzü doğrulandı. `evidence/character-evidence-verification-20260917T132125735234Z.json`, `evidence/text-attribution-verify-final-retry.log`. Sekiz kesilen yükleme senaryosu geçti; dört genişlikte CREATED bir PUT, RECEIVED sıfır PUT ile gerçek API/PG eşliğinde tamamlandı. Kanıt `evidence/upload-resume-c88caacf-d2c3-404d-b8e8-56aa82a30032/verification.json`. Ana kurulum yayını başlatılıyor.

## Ana kurulum kabulü

`text-attribution-v5-20260917` ana API/web/worker üzerinde yayımlandı. Nesil `14a79646-79c6-4cdb-8714-00adf5698770`, iş `75b25439-09f5-425d-9e18-08cf15898d9a`: 48/48 COMPLETED/NEEDS_REVIEW. `evidence/text-attribution-main-check-final.log`: tam kapsama true, 10 atıf, 0 claim-speaker, PASS. `text-attribution-main-source-check.log`: tamamlanmış neslin bütün kaynak/atıf/kontrol kayıtları API/PG eşit. `text-attribution-main-ui.log`: dört genişlik/altı sekme, gerçek kaynak kutuları ve atıflar PASS. `text-attribution-main-release.log`: çalışan 36 backend ve 9 web kaynak dosyası eşit. Önceki 45 sayfalık ara denetim tam kabul sayılmadı; final ayrıca alındı.

Git commit `37ef67a` main üzerinde; origin push HTTPS kimliği olmadığı için başarısız (`could not read Username`). Sunucu kodu yerel main kaynaklarından yayımlandı. Sonraki bölgesel OCR çalışması bu kapanmış v5 kabulünden ayrıdır.
