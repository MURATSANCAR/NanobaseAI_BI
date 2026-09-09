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

Üst sınırlar: havuz 200.000 aday/256 MiB, aday 240 karakter/24 kolon bağlantısı,
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

Yayından önce gerçek API'nin tam sonuçlarını bağımsız bağlı DB sorgularıyla
karşılaştıran kabul koşusu yapılır. Kullanıcı ayrıca istemedikçe yerel test çalıştırılmaz. Şema kontrolü, arama eşleşmesi,
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

## Tüm katalog için otomatik bakım

`backend/scripts/maintain_language_pool.py`, tüm mantıksal tabloların hassas olmayan
kolonlarını sekizer hedef halinde dolaşır. Açıklaması çok olan tablolar önce gelir;
her tabloya bir sayfa ayırarak ilerler. Her hedef kolonun üretilen ifadede gerçekten
referanslanması gerekir. İlişkili tablolar sayfalar arasında döndürülür. Bu kapsam,
bütün matematiksel kolon kombinasyonlarının üretilmesi anlamına gelmez.

Kolon durumları:
- `PENDING`: henüz işlenmedi veya geçici hatadan sonra yeniden denenecek.
- `GENERATED`: hedef kolon için şemaya bağlı en az bir aday üretildi.
- `NEEDS_DEFINITION`: model mevcut açıklamadan güvenilir anlam çıkaramadığını bildirdi;
  bu değerlendirme insan incelemesi gerektirir, doğrulanmış iş tanımı değildir.
- `RETRY_EXHAUSTED`: üç işleme denemesinde hedef kapsanamadı.

Üretimden sonra ikinci bir LLM çağrısı her adayı iş nesnesi, desteklenen anlam ve
kolon birleşiminin anlamlılığı açısından inceler. Yalnız `ACCEPT` kararı alan adaylar
şema kontrolüne ve yayına ilerler; `REJECT`/`AMBIGUOUS` nedenleri checkpoint içinde
saklanır. Bu inceleme otomatik iş doğruluğu sertifikası değildir.

Hassas kolonlar örnek değerleriyle birlikte modele gönderilmez; `excludedSensitive`
listesinde sayılır. Her kaynak metaverisi ve üretici/model kimliği iş anahtarına dahildir.
Açıklama, ilişki, birim, kod açıklaması veya model değişince ilgili işler yeniden
planlanır. Eski kaynağa bağlı adaylar elenir. Geçerli önceki yayın korunur, yarım
üretim checkpoint dosyasından sürdürülür. Katalog üretim sırasında değişirse adaylar
o turda yayımlanmaz. Dosya boyutu/adet sınırı kapsam tamamlandı diye gösterilmez.

`active.maintenance.json` checkpoint'i, `active.coverage.json` ise tablo ve kolon
bazında kapsam raporunu tutar. Bunlar aktif arama dosyasından ayrıdır. Aktif dosya
yalnız tur sonunda ve içeriği değiştiğinde atomik yayımlanır; normal servis yenilemesi
ile yüklenir. İki üretici aynı hedefi kilitleyerek eşzamanlı çalışmayı engeller.

Ürün bakım servisini kurmak için sunucuda:

```sh
ROOT=/path/to/repo VENV=/path/to/venv ENV_FILE=/path/to/semantic.env SERVICE_USER=app \
  bash scripts/server/deploy-language-pool-worker.sh
```

`nanobase-language-pool.timer`, her tur bittikten iki dakika sonra devam eder.
Bir tur en çok 24 LLM grubu ve 900 saniyelik başlangıç bütçesi kullanır; başlamış
çağrı tamamlanabilir. Sistem servisi en geç 2400 saniyede durdurur ve checkpoint
sonraki tura kalır. İşler `bg:language-pool` amacıyla mevcut ortak LLM kuyruğuna girer;
kullanıcı istekleri önceliklidir. Bakım kuyruğu bekleme sınırı dolunca kullanıcıların
önüne geçmez; sonraki turda yeniden denenir. Üç ardışık hata o turu durdurur.

Bu, uygulamanın bakım servisidir; Codex sohbet otomasyonu değildir. Katalog/schema
kapsamı ile gerçek soru–SQL–sonuç doğruluğu ayrı kabul ölçüleridir. Yedek kaynak
önceliği ifade üretiminden çıkarılmaz.
