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

## Kaynak kapsamı: tek şirketin yedekleri

Bu kurulum tek şirket içerir. Farklı veritabanları yıllar içinde alınmış yedeklerdir;
411 ve 211 gibi teknik kodlar şirket kimliği değildir. Önceki iki firma yorumu
kullanıcının 2026-09-09 düzeltmesiyle geri çekilmiştir.

Genel `context_scope.py` mekanizması teknik kaynak kapsamını taşıyabilir; bu
kurulumda `SEMANTIC_PATTERN_LABELS=Firma` kaldırılmıştır. Kaynak önceliği ve
örtüşme çözümü doğrulanmış veritabanı/yedek/dönem eşlemesine dayanmalıdır.
Mevcut dönem seçicinin bu koşulu tüm sorgularda sağladığı henüz doğrulanmamıştır.
Tek şirket kuralının model bilgisine eklenmesi deterministik tekilleştirme kanıtı değildir.

[Güncel kaynak anlamı düzeltmesi](../audits/source-topology-correction-2026-09-09.md).
