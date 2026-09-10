# 10.000 son kullanıcı sorusu — 9 Eylül 2026

İlk üretim yayını testlerden önce yapıldı. Bulunan düzeltmeler de üretime alındı. Yayınların servis sağlık sonucu ve kaynak SHA-256 kayıtları `artifacts/enduser-10000/deploy` altında tutuluyor.

## Sonuçlar

| Kontrol | Sonuç |
|---|---:|
| Kontrollü SQL yürütme ve bağımsız sonuç hesabı | 10.000 / 10.000 geçti |
| 7 tabloluk kontrollü sorular | 1.000 / 1.000 geçti |
| 8 tabloluk kontrollü sorular | 1.000 / 1.000 geçti |
| Üretim kataloğunda plan kurulabiliyor | 8.954 |
| Model veya iş kuralı değerlendirmesi gerekiyor | 861 |
| Dönem verisi yok | 185 |
| Gerçek API ve veri örnekleri | 16 / 16 geçti |
| Regresyon testleri | 474 geçti |

861 model gerektiren planın 461'inde fatura tutarını birim kırılımına bağlama, 400'ünde “bilgisini” ifadesini yorumlama gerekiyor. Bunlar canlı çalıştırma başarısızlığı olarak ölçülmedi. 9.984 prompt canlı API'de tek tek çalıştırılmadı. Kontrollü ölçü tanımları ile üretim ölçü tanımları farklıdır; örneğin kontrollü satış tutarı satır tutarıyken üretimde fatura tutarı kullanılır.

İlk tarama 4.000 kontrollü başarı ve model yolu denenmemiş 6.000 soruydu. Bu 6.000 kayıt başarısız model cevabı değildir. Ayrı gerçek model regresyonundaki üç yanlış sonuç düzeltme sonrası üç başarılı sonuca döndü. Ana 12 canlı örnek ortak tablo yayını sonrasında, dört ek örnek son ayrıştırıcı ve katalog koşulu düzeltmesi sonrasında doğrulandı. Ana ve ek canlı örneklerin son koşusunda deterministik derleyici kullanıldı.

## Kapsam ve sonuçların anlamı

10.000 benzersiz Türkçe metin, 24 ölçü/ilişki ailesinin kontrollü varyasyonlarıdır. Beş zorluk seviyesi, dört ölçü, 2022–2026 aylık dönemleri, toptan/perakende türleri ve dört ifade kalıbı içerir. Bir insan holdout kümesi değildir. Her seviyede 2.000 soru vardır. En zor bölümde 1.000 soru yedi, 1.000 soru sekiz tablo kullanır. Tablolar sorulan kırılımı veya gerekli bağlantıyı sağlar.

Kontrollü testte Runtime.ask üzerinden SQL üretilir ve çalıştırılır. 2.160 satırlık veri üzerindeki bütün sonuçlar SQL'den bağımsız Python hesabıyla karşılaştırılır. SQL'in tablo kümesi de denetlenir. Bu test kendi sertifikalı ölçü/kırılım tanımlarını kullanır. Üretim kataloğunun bütün anlam eşleştirmelerini veya modelin serbest sorulardaki başarısını doğrulamaz.

`PASS` yalnız kontrollü sonuçtur. `DETERMINISTIC_PLAN_READY` üretim kataloğunda plan kurulabildiği anlamına gelir; planın doğru iş anlamını seçtiğini veya SQL'in çalıştığını kanıtlamaz. `MODEL_REQUIRED` model yolu denenmeden başarı veya hata sayılmaz. `DATA_UNAVAILABLE` ilgili dönem kapsamının bulunmadığını belirtir. Gelecek aylar özellikle bu kapsama girebilir.

Canlı API örnekleri Ocak/Şubat 2026 satılan adet sorularıdır. Bağımsız referans SQL firmaları ayrı bağlar ve sonuçlarını birleştirir. İadeler satılan adede dahil edilmez. Üretilen SQL ayrıca yeniden çalıştırılarak en çok 100.000 sonuç satırına kadar tam karşılaştırılır. Referans da kesilirse test geçmez. `LIVE_PASS_SQL_PREVIEW_LIMITED` tam SQL sonucunun eşleştiğini, API önizlemesinin 500 satırla sınırlı olduğunu gösterir. Önizleme dışındaki satırların UI'dan indirilebildiği bu testte doğrulanmadı.

## Uygulanan düzeltmeler

1. Virgül, “ve” ve “ile” ile yazılmış çoklu kırılımlar doğru gruplanıyor. Önceki filtre cümlesi yanlışlıkla kırılıma katılmıyor.
2. Tekil anahtarlara dayalı, benzersiz çok adımlı ilişkiler çözülebiliyor. Belirsiz yollar ve toplamı çoğaltacak ters bağlantılar reddediliyor.
3. Model SQL'inde iptal ve satır türü gibi sertifikalı varsayılan filtrelerin eksikliği denetleniyor. Üç gerçek model örneği önce yanlış sonuç verirken düzeltme sonrası üçü de tam sonuç karşılaştırmasını geçti.
4. Kullanıcı sınır istemediğinde modelin eklediği dış TOP/LIMIT kaldırılıyor. Açık “ilk 50” isteği ve iç alt sorgu sınırları korunuyor.
5. Genel LG_SLSMAN tablosunun sözlükten ilişki çözümü düzeltildi. Üretimde 16 profilin temsilci ilişkisi tamamlandı.
6. Altı rapor kırılımı tanımlandı. Etkin ödeme planı satırdaki sıfır olmayan referansı, yoksa fatura planını kullanır. “Fatura ödeme planı” yalnız başlıktır. Satış temsilcisi fatura başlığından alınır. Tanımsız boyutlar LEFT JOIN ile korunur; model denetimi bu önceliği ve satırların korunmasını kontrol eder.
7. Ortak tablonun her firmada ayrı kopyası olması beklentisi kaldırıldı. Tekil anahtarlı ortak referans, firmaların kendi satırlarını çoğaltmadan kullanılır. İki firmalı bağımsız sonuç testi eklendi. SQL denetimi türetilmiş tablo takma adlarını ve statik fiziksel adları takip eder.
8. Satış satırı sayısı açık COUNT ölçüsü olarak tanımlandı. Perakende kodu 7 için fatura ve satış satırı anlamları mevcut onay tablosu anlamının yanına eklendi.

9. Tek sözcüklü bir ifade hem ölçü hem filtre olabiliyorsa, hemen ardından gelen açık ölçünün varlığındaki sertifikalı filtre anlamı kullanılır. Virgül veya “ve” ile ayrılmış ölçüler korunur. Perakende payı ile perakende satılan adet karışıklığı bu kuralla giderildi.

## Ölçüm sınırları ve açık alanlar

10.000 kontrollü başarı, 10.000 canlı API başarısı değildir. Canlı çağrı yapılmayan satırlar `NOT_LIVE_TESTED` olarak teslim edilir. Planlama taramasında ölçülerin farklı varlıklara dağılması, fatura tutarının satır/birim kırılımına dağıtımı gibi ek anlam doğrulaması gerektiren durumlar bulunuyor. Bunlar sessizce geçerli kabul edilmedi; satır bazında durum ve neden saklandı. Plan hazır satırların anlamsal doğruluğu ayrıca denetlenmelidir.

İlk canlı referans yalnız firma 411'i kullandığı ve iade gruplarını sıfır satır olarak koruduğu için bazı hatalı uyuşmazlıklar üretti. Bu koşu geçersizdir ve başarı oranına katılmaz. Son karşılaştırma veritabanının SQL_Latin1_General_CP1254_CI_AS kuralına uygun Türkçe büyük/küçük harf eşleştirmesi kullanır. Bir satırdaki harf yazımı farkı sayı hatası olarak raporlanmaz. Yayın sırasında bağlantısı kesilen ara çağrılar son sürümde tekrarlandı.

## İş kuralı kaynakları

- [Logo Tiger Enterprise Finans kullanım belgesi](https://www.sdmyazilim.com.tr/var/uploads/1500469815-finans.pdf): satır ödeme planı önceliği ve fatura planına dönüş.
- [Logo GO3 Faturalar kullanım belgesi](https://www.sdmyazilim.com.tr/var/uploads/1500477553-fatura.pdf): fatura satış elemanı alanı.

Sayısal kanıtlar ve SQL'ler JSONL çalıştırma dosyalarında, teslim listesi Excel/CSV/JSON biçimindedir. İşlem tablolarına veri yazılmadı.

## Son kaynak doğrulaması

- İlk yayın: 9 Eylül 2026 03:19 Türkiye saati, testlerden önce.
- Ortak tablo yayını: 04:08:21. Son ayrıştırıcı yayını: 04:13:46. Servis sağlık kontrolü başarılı.
- Son kontrollü koşu: 181,1 saniye, sıfır model çağrısı. Üretimdeki beş ilgili kaynak dosyasının SHA-256 özetleri bu koşunun kayıtlarıyla eşleşti.
- Katalog sayım koşulu kaydı sonradan beklenen Predicate.key biçimine getirildi; anlamı değiştirilmedi. Ek dört canlı örnek bunun ardından yeniden doğrulandı.
- Üretim yedekleri: `enduser-10000-initial-20260909`, `enduser-10000-global-20260909`, `enduser-10000-modifier-20260909`, `enduser-10000-dimensions-20260909`.
