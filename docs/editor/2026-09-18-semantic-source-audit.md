# R7 gerçek iddia–atıf incelemesi ve V16 düzeltmesi

## Kapsam ve yöntem

Tamamlanmış `382da5b3-a13a-4986-85ba-1a38fd92ff44` neslindeki 100 uygun iddianın metinleri ve taşıdıkları kaynaklar salt okunur incelendi. Girdi CPU gerçek PostgreSQL dökümü `evidence/v15-r7-eligible-claims-readonly-v2.json`; kaynak/API eşliği ve tam kaynak denetimi ayrı kanıtlardır. Bu içerik incelemesi kitabın tamamının editoryal kabulü veya orijinal PDF'nin 100 bağımsız karşılaştırması değildir. Aşağıdaki tespitler kayıtları değiştirmez, modele beklenen cevap olarak verilmez ve üretim kodunda örnek/isim listesi olmaz.

## Açık kaynak desteği eksikleri

| İddia sırası / PDF sayfası | Bulgu | Genel düzeltme / kabul |
|---|---|---|
| 10 ve 12 / 11 | Alıntıdaki adsız özneye Max adı eklenmiş | V16 kaynak yüzeyi kapısı gerçek kayıtlarda engelledi |
| 21 / 15 | Alıntıda yalnız “sana” varken Defne alıcı adı eklenmiş | Aynı genel kapı engelledi |
| 57 ve 58 / 27 | Alıntıda olmayan Robobi adı eklenmiş | Aynı genel kapı engelledi |
| 23 / 15; 94 / 41 | “Galiba” kapsamı iddiada kaybolmuş | Yeni epistemic_strength ekseni; gerçek model tekrar kabulü beklenir |
| 12 / 11; 78 / 33 | Gelecek beklentisi / süren iş, farklı zaman-görünüşle aktarılmış | Aynı eksen ve entailment; gerçek tekrar kontrolü beklenir |
| 36 / 19 | Konum alıntıda yokken “bahçede” eklenmiş | Açık; özel isim kapısı bu küçük harfli konum sorununu çözmez |
| 45 / 22 | Alıntıda sahibi olmayan “anılar”a robot sahipliği eklenmiş | Açık; kişi/rol ve bağlam desteği gerekir |
| 87 / 39; 94 / 41 | Masal özel adı küçük harfle genelleştirilebiliyor | Anlam/varlık türü belirsizliği; yüzey kapısı tek başına yeterli değil |

20, 28, 79, 85, 91 ve 99 numaralı ifadelerde ayrıca söz edimi, insan/varlık türü, zamir veya zaman aktarımı için inceleme gerekir. Bunlar doğrulanmış yeni hata sayısına katılmadı. 13/14, 54/55 ve 88/89 gibi örtüşen ifadeler nedeniyle 100 sayısı 100 benzersiz olay değildir.

## Kod ve gerçek bileşen kanıtı

`source-semantic-review-v6` her iddianın sadece kendi atıflarında geçen isim yüzeylerini denetler. Büyük harf/ek ayrımı genel Unicode ve Türkçe normalizasyonuyla yapılır; kitap sözlüğü kullanılmaz. `evidence/v16-reference-gate-real-r7.json`: 100 gerçek iddiada beş kanıtsız isim ataması engellendi, model çağrısı ve kaynak/inceleme yazımı sıfır. Bu kapı genel NER ya da tüm anlamsal hataları çözme iddiası taşımaz.

Yeni anlamsal sözleşme ayrıca `epistemic_strength` eksenini, isimsiz söz ediminin karakter kimliği kanıtı sayılmamasını ve sentezde aynı kaynak yüzeyi kapısını içerir. Kaynak erişimi/önizleme doğrulayıcıları sürüm ayrımını korur. Her model çağrısı öncesi/sonrası iş iptali ve lease kontrolü yapılır.

Balondaki birden fazla OCR satırı tek bölünmez kaynak birimine dönüştürüldü. Gerçek PDF29 pilotunda üç satır birlikte alındı; yeni adayda actor/speaker null kaldı. Aynı değiştirilmemiş adayın V6 tekrarında bir kaynak destekli söz edimi geçti: `evidence/semantic-candidate-7280af899f9e2a9b129a.json`. Bu, figürün karakter kimliğini doğrulamaz.

V16 henüz ana yayında değil. Son kodun yeni imajı, yeni tam nesli ve aynı sürüm API/PG/soru/restore kabulü gerekir. R7'nin teknik kabulü bu yeni sürüme veya tam kitap anlamına taşınmaz.
