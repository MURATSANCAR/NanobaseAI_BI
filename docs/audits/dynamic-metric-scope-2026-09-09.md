# Dinamik ölçü kapsamı ve birleşik dönem — 9 Eylül 2026

## Ürün kodu

Soruya özel SQL veya yıl/yayınevi/işlem kodu dalı eklenmedi. Derleyici kapsamları her ölçünün katalogdaki `Mapping.extra.conditions` alanından alır. Kapsamlar farklıysa her ölçü kendi koşullu toplamını kullanır; okunan satırlar kapsamların birleşimidir. Kapsamsız bir ölçü varsa başka ölçünün filtresi ona uygulanmaz. Ortak varsayılan filtreler ve kullanıcının açık filtreleri korunur. Desteklenmeyen koşul/formül sessizce atlanmaz.

Dönem karşılaştırması denetimi, her ölçünün kendi kapsamlı formülünü AST üzerinden karşılaştırır. COUNT DISTINCT tekilleştirmesi, AVG paydası ve boş dönem davranışı korunur.

`<yıl> yılbaşından bugüne` birleşik dönem olarak ayrıştırılır; yıl, YTD ve bugün diye üç döneme bölünmez. Başlangıç belirtilen yılın başı, bitiş çalışma gününün ertesi günüdür. Açık yıl içermeyen ifade çalışma yılını kullanır. Tarihsel/farklı yıla ait yalın `YTD` için kesim tarihi tahmin edilmez; belirsizlik işaretlenir.

## Doğrulama

- Tam semantik paket: **453 geçti**, 2 uyarı.
- Yeni testler farklı tablo adları, farklı işlem kodları ve yıllarda bağımsız Python satır hesabıyla doğrular. Birleşik sonuçlar, ölçülerin tek tek sorgulanmasıyla da karşılaştırılır.
- İade, iptal, aynı kimliğin birden fazla satırda bulunması, farklı kapsamdaki işlemler, kapsamı olmayan ölçü, COUNT DISTINCT, AVG ve boş karşılaştırma dönemi sınanır.
- SQL AST'sinde ölçü koşulu değiştirilen örnek denetimden geçmez. Koşullandırılması desteklenmeyen formüller reddedilir.
- Tarih testleri 2021, 2024 artık günü ve 2033 yıl sonunu kapsar; ürün koduna bu yıllar yazılmamıştır.

## Canlı sonuç

`2026 yılbaşından bugüne yayınevi bazında net ciro ve satılan adet` ilk denemede üç dönem üretildiği için INCOMPLETE_ANSWER idi. Birleşik dönem düzeltmesinden sonra TEXT_TO_SQL döndü ve **48 satırın tamamı** bağımsız referans SQL ile eşleşti. Çıktı yayınevi, net ciro ve satılan adet sütunlarını taşıyor.

Referans SQL yalnız kabul testinde bilinen Timaş kaynağına yazıldı; ürün sorgusu bu SQL'den üretilmez. Böylece ürünün kendi formülünü doğru cevap kabul eden döngüsel bir test yapılmadı. Bu bir gerçek kullanıcı holdout kümesi değildir.

Aynı konuşmada yalnız `Mart 2026` takip sorusu gönderildi. Kırılım ve iki ölçü korundu; **46 satırın tamamı** referans SQL ile eşleşti. İlk yanıtın 48 satırı `/api/v1/result/{resultId}` üzerinden alınan kayıtla ve kolonlarıyla birebir aynı. Kanıt: `artifacts/stress/publisher-reference.json`; tekrar çalıştırılabilir test: `tests/stress/publisher_reference.py`.

## Dağıtım ve sınır

Derleyici, denetim ve dönem ayrıştırıcı semantik köprüye dağıtıldı. Üç dosyanın SHA-256 özeti yerelle eşleşti; köprü active. Önceki sürümler `/data/nanobaseai/bi/backups/metric-scope-20260909` altında.

Bu değişiklik serbest aritmetik ifadelerini otomatik sertifikalandırmaz. Katalogda tanımı belirsiz bir çıkarma isteği hâlâ netleştirme gerektirir. UI oturumu olmadığı için tarayıcıdaki grafik ve Excel etkileşimi tamamlandı sayılmıyor; API sonuç doğrulaması UI kabulünün yerine geçmez.
