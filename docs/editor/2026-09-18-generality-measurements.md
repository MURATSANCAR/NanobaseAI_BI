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

## 5. Devam satırı: kural önce, model yalnız kalan yerde

Soru: konuşma çizgili satırın altına sarılan satır konuşmanın devamı mı, anlatıcı mı? Etiket tırnaklı kitaplardan türetilir, soru tırnaklar silinip çizgili biçimde sorulur. Alt satırı yeni tırnakla başlayan örnekler çıkarıldı: tırnak silinince aynı konuşmacı mı yeni konuşmacı mı olduğu belirlenemez (ilk ölçümde bunlar yanlış etiketlenmişti).

Genel kural: çizgili satırda konuşma noktalamasından (`, ! ? … ...`) sonra küçük harfle başlayan, en az bir okuması üçüncü kişi çekimli fiil olan aktarma yüklemi varsa ve bu anlatıcı cümlesi o satırda kapanmıyorsa alt satır anlatıcıdır. Cümle aynı satırda kapanıyorsa kural karar vermez: alt satır sürdürülen konuşma da yeni paragraf da olabilir, bunu ancak satır geometrisi söyler. Kalan örneklerde yalnız 0,8 üstü emin model kararı kullanılır, gerisi çekimser.

Gerçek ölçüm, yeni model çağrısı yok (kayıtlı olasılıklar; `scripts/probe-continuation-combined.py`, kanıt `evidence/continuation-combined-20260918T213430Z.json`):

| Kitap | Örnek | Kural karar / doğru | Birleşik karar / doğru | Çekimser |
|---|---:|---:|---:|---:|
| Ekrana Sığmayan Macera | 60 | 13 / 13 | 45 / 45 | 15 |
| Kahramanını Yutan Kitap | 20 | 0 / 0 | 7 / 6 | 13 |
| Dünyanın En Korkak Hayvanı | 7 | 0 / 0 | 4 / 4 | 3 |
| Toplam | 87 | 13 / 13 | 56 / 55 | 31 |

Tek yanlış, tırnak içinde verilmiş iki satırlık bir başlık. Yalnız model (0,8 eşiği) aynı örneklerde 48 kararın 42'sini doğru veriyordu; yanlışların hepsi alt satıra taşan anlatıcı cümlesiydi ve kural onları kapattı.

Sınırlar: kural bu 67 örnekte hatalarına bakılarak iki kez düzeltildi (sözlükte ad okuması olan aktarma fiilleri; kapanan cümleden sonra çekimserlik); görülmemiş veride ölçülmedi. Etiket yalnız tırnaklı kitaplardan gelir; gerçekten konuşma çizgili kitapta doğruluk ölçülmedi. %36 çekimserlik satır geometrisi gerektiriyor. Üretime bağlı değil.

## 6. Altı gerçek kitapta konuşma işaretlemesi (19 Eylül)

Üç yeni kitap kabul kurulumunda kaynak hazırlığından geçti (API/PG + Poppler PASS): Dedem Tekrar Çocuk Oldu (128 s.), Anne Terliği (128 s.), Levent Dünya Harikalarının Peşinde (144 s., 360 MB; ayrıştırıcı tepe bellek 9,74 GiB, 6 GiB sınırında OOM ile ölmüştü). Profil kanıtı `evidence/utterance-profile-probe-20260919T084342180923Z.json` (yalnız sayı; kişi eki kapısı v4).

| Kitap | Sayfa | Tırnaklı aralık | Konuşma çizgili satır | Birinci kişi yüklem | Kapı uygulanabilir | İşaretli konuşma dışında |
|---|---:|---:|---:|---:|---:|---:|
| Ekrana Sığmayan Macera | 48 | 159 | 0 | 38 | 38 | 0 |
| Kahramanını Yutan Kitap | 64 | 58 | 86 | 183 | 41 | 135 |
| Dünyanın En Korkak Hayvanı | 32 | 19 | 36 | 9 | 2 | 5 |
| Dedem Tekrar Çocuk Oldu | 128 | ≈600 | 7 | 337 | 103 | 234 |
| Anne Terliği | 128 | ≈690 | 0 | 121 | 120 | 1 |
| Levent Dünya Harikalarının Peşinde | 144 | ≈60 | 304 | 229 | 32 | 168 |

Tırnaklı aralık sütunu v4'ün konuşma çizgili parçaları da saydığı ham sayıdan çizgili parçalar düşülerek yaklaşık verilmiştir.

Bulgu: ölçüm protokolündeki "birinci kişi anlatıcı" dilimi için ilk gerçek veri. Dedem birinci kişi anlatıcılı ve diyaloğu tırnakla veriyor ("… dedim."); Levent birinci kişi anlatıcılı ve diyaloğu konuşma çizgisiyle (–) veriyor, dekoratif başlıkları OCR'da bozuk. Bu iki kitapta birinci kişi yüklemlerin çoğu anlatıcıya aittir; kapı bunlarda doğru biçimde `NOT_APPLICABLE` döner, yani PDF27 sınıfı hatayı anlatıcı metninde yakalayamaz. Anlatıcı kimliği kitap düzeyinde kurulmadan (Sorun 1b) bu açık kapanmaz. Yeni kitaplarda analiz nesli ve iddia yok; kapının doğru/yanlış işaret oranı ölçülmedi.
