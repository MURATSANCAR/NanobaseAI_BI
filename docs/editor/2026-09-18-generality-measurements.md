# Genellik ölçümleri: diakritik itiraz kuralı, konuşma işaretlemesi, doğrulama seti (18 Eylül 2026)

Üçü de aday/ölçümdür; üretime, imaja ve pakete bağlı değildir. Ortam `nanobase-direct:/data/nanobaseai/editor/runtime/morph-probe` (zeyrek 0.1.3). Model çağrısı 0, uygulama/DB yazımı 0, metin düzeltmesi 0.

## 1. Diakritik itiraz kuralı — `source_diacritic_witness.py` (`source-diacritic-witness-v1`)

Genel sorun: optik kabulde tek bağımsız okuyucunun itirazı bölgeyi incelemede tutuyor; itirazların bir kısmı yalnız Türkçe diakritikte ayrışan ve Türkçe sözcük biçimi olmayan okumalardır.

Genel kural: en az iki bağımsız okuyucu bütün bölgede anlaşıyorsa, itiraz eden okuma yalnız diakritikte ayrışıyorsa, farklı her sözcükte anlaşılan biçim geçerli ve itiraz edilen biçim geçersizse, sözcük en az 3 harfliyse ve satır sonu tire parçası değilse itiraz `DIACRITIC_VETO_NOT_A_WORD` gerekçesiyle geçersiz sayılabilir. Seçilen metin her zaman bir okuyucunun ham çıktısıdır. Bağımsız okuyucular: bölgesel PaddleOCR, tam sayfa Tesseract, kullanılabilir PDF metni. Tesseract kırpım yeniden okumaları aynı motor olduğu için destek sayılmaz.

Gerçek ölçüm (`ocr-residual-audit-14a79646-….json`, 328 inceleme bölgesi; sürücü `scripts/probe-diacritic-veto.py`; kanıt `evidence/diacritic-veto-probe-20260918T131625469123Z.json`):

| Sonuç | Bölge |
|---|---:|
| İtiraz geçersiz sayılabilir | **32** (24'ünde itiraz eden Paddle, 8'inde Tesseract) |
| İki okuyucu anlaşması yok | 158 |
| İtiraz yok | 65 |
| İtiraz yalnız diakritik değil | 38 |
| Satır sonu parçası | 19 |
| İki biçim de geçerli | 9 |
| Sözcük 3 harften kısa | 5 |
| Anlaşılan sözcük geçerli değil | 2 |

Serbest kalan 32 bölgenin 30'unda aynı motorlu kırpım yeniden okuması da anlaşılan metni verdi, 0'ında itiraz edeni; bu destek sayılmadı, yalnız raporlandı. Açık: tek kitap, eski V5 nesli; PDF'i bozuk sayfalarda iki okuyucu anlaşması kurulamadığı için kural orada çalışmaz; bölgeler arası tire parçası (`çirsek`) algılanmıyor ama seçilen metin yine iki okuyucunun ham ortak okumasıdır; zeyrek sözlüğü gevşek. Kapıya bağlanmadı.

## 2. Konuşma işaretlemesi üç gerçek kitapta farklı

Sürücü `scripts/probe-utterance-profile.py`, girdi hazırlanmış kaynak artifact'larındaki sayfa metinleri (kabul kurulumu, API 18810); kanıt yalnız sayı içerir, kitap metni yazılmaz: `evidence/utterance-profile-probe-20260918T131854267812Z.json`.

| Kitap | Konuşma çizgili satır | Birinci kişi yüklem | Kapı uygulanabilir | Uygulanamaz: işaretli konuşma dışında | Uygulanamaz: sınır belirsiz |
|---|---:|---:|---:|---:|---:|
| Ekrana Sığmayan Macera (48 s.) | 0 | 38 | 38 | 0 | 0 |
| Kahramanını Yutan Kitap (64 s.) | 86 | 183 | 40 | 135 | 8 |
| Dünyanın En Korkak Hayvanı (32 s.) | 36 | 9 | 1 | 5 | 3 |

Bulgu: bütün ölçümlerin yapıldığı kitap diyaloğu yalnız tırnakla veriyor; diğer iki gerçek kitap konuşma çizgisi kullanıyor ve birinci kişi yüklemlerin çoğu işaretli konuşmanın dışında. Kişi eki kapısının ilk sürümü bu kitaplarda sessizce devre dışı kalırdı. `source-person-agreement-v3`: konuşma çizgisi konuşmanın başını verir ama sonunu vermez ("— Geldim, dedi Ali."), bu aralık hiçbir zaman kesin sayılmaz; iddia böyle bir yüklemi ya da işaretli konuşma dışındaki birinci kişi yüklemi taşıyorsa kapı `NOT_APPLICABLE` ve nedenini döndürür. R5 91 ve R7 100 iddiada sonuç değişmedi (1 işaret / 0 işaret, uygulanamaz 0); modül SHA-256 `406a620f…`.

Açık: bu tablo sayfa metni düzeyindedir, üretimdeki 1–3 satırlık kaynak birimi düzeyi değil. Diğer iki kitapta analiz nesli ve iddia yoktur; kapının orada doğru/yanlış işaret oranı **DOĞRULANAMADI**. Konuşma çizgili diyalogda konuşma sonu ve birinci kişi anlatıcının kimliği çözülmedi; kapı bu durumlarda yalnız çekilir.

## 3. Doğrulama seti

Bilinen gerçek hata örneği 1 iken hiçbir kapının yakalama oranı ölçülemez. `scripts/export-validation-sheet.py`, kabul edilmiş gerçek iddiaları ve kayıtlı kaynak metinlerini etiketleme dosyasına çıkarır. Dosya uygulama kökünün dışındadır (`/data/nanobaseai/editor-qualifications/editor-validation/`, mod 600), Git'e ve pakete girmez, üretim kodu tarafından okunmaz, kapı sonuçlarını içermez (etiketleyeni yönlendirmemek için). İlk dosya: R5 + R7, yinelenenler atılınca 164 satır.

Etiket: `SADIK`, `SADIK_DEGIL`, `KARARSIZ`. Hata sınıfı: `OZNE_KAYMASI`, `KONUSMACI_YANLIS`, `KONUM_SAHIPLIK_EKLEME`, `ZAMAN_KAYMASI`, `KESINLIK_KAYMASI`, `LISTE_GENELLEME`, `KAYNAKTA_OLMAYAN_AD`, `DIGER`. Etiketler insan tarafından doldurulur; beklenen cevap hiçbir zaman modele, isteme ya da üretim koduna verilmez. Açık: etiketleme yapılmadı; tek kitap; roman dilimi yok.

## 4. Konuşma çizgisinde konuşma sonu — `source-person-agreement-v4`

İki genel kural kodlandı: (a) çizgili satırın içinde "virgül/ünlem/soru + isteğe bağlı `diye` + bütün çözümlemeleri üçüncü kişi çekimli fiil + yalın olabilen özne + nokta" kalıbı anlatıcı ara cümlesidir ve adı konuşmanın dışına çıkarır; (b) bir sonraki dolu satır da çizgiyle başlıyorsa ya da metin bitiyorsa konuşma satır sonunda biter. Soru ve ünlemle biten parça konuşma sayılır (ilk denemede "görmüyor musun?" yanlışlıkla anlatıcı sayılmıştı; düzeltildi).

Gerçek ölçüm (`evidence/utterance-profile-probe-20260918T211611107556Z.json`, modül SHA-256 `085842f5…`): iki kitaptaki 123 konuşma parçasının yalnız **15**'i kesinleşti, 1 anlatıcı ara cümlesi bulundu; ikinci örnek satır sonunda bölündüğü için ("…, dedi ‖ Kirpicik.") kaçtı. R5/R7 sonucu değişmedi (1 / 0).

Sonuç: sayfa metni düzeyinde kural kazancı küçüktür. Alt satıra sarılan devamın konuşma mı yeni anlatıcı paragrafı mı olduğu ancak satır geometrisinden (girinti, satır aralığı; `source_spans` kutuları) çıkar. Sıradaki genel iş paragraf sınırını geometriyle belirlemek ve kuralı birleştirilmiş paragraf metninde çalıştırmaktır; yapılmadı. Kapı bu arada belirsiz yerde `NOT_APPLICABLE` döner.
