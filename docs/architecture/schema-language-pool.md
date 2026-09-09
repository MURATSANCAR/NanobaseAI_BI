# Şemaya bağlı Türkçe ifade havuzu

Mevcut katalog aramasını, yapılandırılmış LLM'nin gerçek tablo/kolon açıklamalarından
ürettiği iş dili ifadeleriyle genişletir. Ayrı bir firma sözlüğü, genel Türkçe anlam
veritabanı veya otomatik sertifikasyon katmanı kurmaz. Kaynak, bağlı veri kaynağının
katalog profilleri, açıklama düzeltmeleri, kolon tipleri, birimler, kod açıklamaları
ve tanımlı ilişkileridir. Örnek müşteri kayıtları ve kolon örnek değerleri üreticiye gönderilmez.

## Üretim ve kullanım

1. `backend/scripts/build_language_pool.py` yapılandırılmış katalog ve LLM'yi kullanır.
2. Kolonlar sayfalanır, tablolar sırayla dolaşılır; uygun ilişkili tablolar bağlama eklenir.
3. LLM kısa ifadeler ve tam sorular, kolon bağlantıları, işlem türü ve belirsizlikleri üretir.
4. Olmayan/hassas kolonlar, bağlantısız tablo birleşimleri, ana tablosunu içermeyen
   adaylar ve sözleşmeye uymayan yanıtlar reddedilir. Bu kontrol iş anlamının doğruluğunu kanıtlamaz.
5. Kabul edilen adaylar `SCHEMA_CHECKED_CANDIDATE` statüsündedir; `CERTIFIED` değildir.
6. Çalışma zamanında ifadeler mevcut kolon ve vektör aramasına ek bir sözcüksel arama
   kanalı olur. En fazla dört eşleşme tablo seçimine ve ilgili kolonların model bağlamında
   tutulmasına katkı verir. Tüm havuz her soruya eklenmez.
7. Adaylar resolver slotlarını, doğrulanmış ölçüleri veya iş kurallarını değiştirmez.
   Netleştirme gerektiren sorular mevcut kontrol yolunda kalır.

Açıklama, tip, birim, kod açıklaması veya ilgili tablo ilişkisi değişirse o kaynağa
bağlı eski adaylar yüklenirken elenir. Yeni satırlar veya örnek değerler kaynak
anlamını değiştirmiş sayılmaz. Yeniden üretim değişen bağlamı işler; tamamlanmış
aynı bağlamı tekrar çağırmaz. LLM talimatının değişmesi de yeni üretim işi oluşturur.

## Çalıştırma

Uygulamanın katalog ve LLM ortam değişkenleri yüklüyken:

```sh
PYTHONPATH=backend python backend/scripts/build_language_pool.py \
  --output /absolute/path/pool.candidate.json \
  --max-batches 8 --per-batch 6 --columns-per-batch 48
```

`--entities` verilmezse katalogdaki tüm varlıklar sırayla işlenir. İsteğe bağlı
`--entities ENTITY_A,ENTITY_B` yalnız ilk üretim kapsamını sınırlar; ürün kodunda
müşteri veya Logo tablo listesi sabitlenmez. Aynı dosyaya aynı anda iki üretici
başlatılamaz. Dosya her tamamlanan grupta atomik kaydedilir; başarısız LLM çağrısından
sonra önceki geçerli adaylar korunur. Aynı komutla devam edilir.

Üst sınırlar: havuz 20.000 aday/32 MiB, aday 240 karakter/24 kolon bağlantısı,
LLM çağrısı en çok 12 istek adayı. Üretim çevrim dışı bir bakım adımıdır; kullanıcı
sorusu sırasında havuz genişletmek için ek LLM çağrısı yapılmaz. Tüm katalog için
üretimin tamamlandığı, kısmi bir koşunun başarıyla bitmesinden çıkarılmamalıdır.

## Yayın ve izleme

Doğrulanan aday dosyasını servis kullanıcısının okuyabileceği bir yola atomik olarak
koyun ve `SEMANTIC_LANGUAGE_POOL=/absolute/path/pool.json` ayarlayın. Ortam değişkeni
ilk eklendiğinde servis yeniden başlatılır. Sonraki atomik dosya güncellemeleri
normal katalog yenileme kontrolünde görülür; kontrol aralığı yaklaşık 30 saniyedir ve katalog yükleme süresi buna eklenir.
Değişken yoksa veya dosya geçersizse havuz boş kalır; katalog araması çalışmaya devam eder.

API yanıtındaki `semantic.query.languageCandidates` ilgili arama kanıtlarını,
`semantic.query.languagePoolHash` yüklenmiş geçerli havuzun hashini taşır.
Adayların açıklamaları veri niteliğindedir; talimat veya iş kuralı değildir.

Yayından önce birim regresyonları ve gerçek API'nin tam sonuçlarını bağımsız bağlı
DB sorgularıyla karşılaştıran kabul koşusu yapılır. Şema kontrolü, arama eşleşmesi,
SQL yürütme başarısı ve sayısal sonuç doğruluğu ayrı ölçülür. Bağımsız iş tanımı
olmayan yeni ifade, yalnız SQL çalıştı diye başarılı sayılmaz.

## Canlı kontrolde düzeltilen fiziksel kapsam

Açıkça belirtilen fiziksel bağlamın kaybolması, ifade aramasından bağımsız bir sonuç
hatasıydı: `411 firmasında` denmesine rağmen iki firmanın kartları birlikte
okunabiliyordu. `context_scope.py`, veri kaynağının mevcut
`SEMANTIC_PATTERN_LABELS` yapılandırmasındaki adları kullanarak bitişik sayısal
kapsamı katalogdaki `n0`, `n1` değerleriyle eşler. Bu Logo dağıtımında ilk bağlamın
etiketi `Firma` olarak yapılandırıldı; uygulama kodunda `411`, `211`, firma veya
Logo tablo isimleri sabitlenmedi.

`semantic.query.contextScope` doğrulanan kapsamı kaydeder. Aynı kapsam modelin
şema seçimine, deterministik SQL derlemesine, ön SQL kontrolüne, tam sonuç yürütmesine ve dolayısıyla sonuç
önbelleğinin fiziksel SQL anahtarına taşınır. Kapsam dışı açık fiziksel tablo
isimleri reddedilir. Katalogda olmayan, çelişkili veya desteklenmeyen çoklu/negatif
kapsamlar tek firmaya sessizce daraltılmaz; netleştirme istenir. Kapsam belirtilmeyen
soruların mevcut dönem seçimi değişmez.

Bu eşleme üretilmiş ifade anlamını onaylamaz. Mevcut resolver'ın bir sözcüğü yanlış
varlığa bağlaması ve henüz çözülemeyen niteleyiciler ayrı sorunlardır; havuz bunların
kontrollerini atlamaz.
