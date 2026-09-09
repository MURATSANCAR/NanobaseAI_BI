# Şemaya bağlı ifade havuzu: geliştirme ve canlı kabul

**Durum: canlı geniş kabul koşusu sürüyor. Bu belge sonuçlar tamamlandığında güncellenecek.**

## Yapılan geliştirme

Mevcut katalog aramasına, yapılandırılmış LLM'nin gerçek tablo/kolon açıklamalarından
ürettiği Türkçe ifadeler bağlandı. Ayrı bir müşteri sözlüğü kurulmadı. Üretilen
anlamlar sertifikalı kurala dönüştürülmez; tablo seçimini ve ilgili kolonların
model bağlamında kalmasını destekler. En fazla dört ilgili aday kullanılır.

İlk yayın 55 şema kontrollü aday içeriyor. Bu havuza ait üretimde 5 aday elendi:
2 bağlantısız tablo birleşimi, 2 geçersiz işlem türü ve 1 bilinmeyen/hassas kolon
başvurusu. Bunlar şema/sözleşme kontrolleridir; iş anlamının insan tarafından
onaylandığı anlamına gelmez. Havuz tüm kataloğun tamamlandığı iddiasını taşımaz.

Üretici kaldığı yerden devam eder, aynı dosyaya ikinci üreticiyi engeller,
atomik kayıt yapar ve değişen kaynak sürümünün ifadelerini yeniler. Kaynak sürümü
üretilen sayfanın dışındaki kolon değişikliklerini de içerir. Eşleşmede aynı
kelimenin kök/ekli biçimi iki bağımsız kanıt sayılmaz.

## Canlı testte bulunan ve düzeltilen hata

Soru: `411 firmasında kullanım dışı cari hesap kartlarının sayısı nedir?`

İlk sürümde fiziksel SQL 211 ve 411 firmalarını birlikte okuyarak 27.811 döndürdü.
Bağımsız `dbo.LG_411_CLCARD WHERE ACTIVE=1` referansı 27.790 idi. Açık firma kapsamı
katalogdaki fiziksel parametreden yürütmeye taşındı. Düzeltme sonrası aynı soru,
aynı bağımsız referansla **27.790 = 27.790** olarak doğrulandı.

Kapsam eşlemesi `SEMANTIC_PATTERN_LABELS` yapılandırmasını kullanır; koda firma
numarası veya müşteri adı eklenmez. Bu kaynağın ilk fiziksel parametresi `Firma`
olarak etiketlendi. Bilinmeyen, çoklu veya negatif kapsam örneklerinin sessizce
tek firmaya çevrilmemesi gerçek API üzerinden de doğrulandı.

## Doğrulama ayrımı

- Yerel semantik regresyon: **532 geçti**. Bunlar gerçek DB kabulünün yerine geçmez.
- Havuz arama kontrolü: 55/55 ifade kendi kaydına ulaştı. Üretilmiş eşleşmelerde
  hedeflenen 100 kolonun 32'si mevcut kolon aramasında, 100'ü genişletilmiş aramada
  bulundu; 45 ifadenin kolon kapsamı genişledi. Bu sentetik arama kontrolü doğal
  dil doğruluğu oranı değildir.
- Gerçek LLM ile güncel üreticinin küçük kontrolünde 1 aday kabul edildi, 1 aday
  elendi. Tekrar çalıştırmada tamamlanan grup yeniden üretilmedi. Bu ayrı kontrol
  dosyası canlı 55 adaylık havuza eklenmedi.
- Açık 411 kapsamıyla ödeme planı kod/açıklama listesi ve grup koduna göre kayıt
  sayısı gerçek API tam sonuçlarıyla, bağımsız kaynak SQL'leriyle eşleşti.
- İlk ödeme planı denemelerinin referansı, kapsam belirtilmeyen soruda iki firmanın
  okunacağını varsayıyordu. Bu referans yeterli değildi; ilk denemeler sayısal
  doğruluk kanıtı olarak kullanılmıyor. Nihai sorular ve referanslar açıkça 411
  firmasını belirtiyor.

## Açık kalanlar

1. `aktif malzeme kartları`: havuz ITEMS.ACTIVE/CODE adayını buluyor; eski resolver
   `aktif` sözcüğünü CLCARD.ACTIVE'a, `malzeme`yi STLINE.LINETYPE'a bağlıyor.
   Çelişkili sonuç sunulmuyor, fakat soru henüz cevaplanamıyor.
2. `kampanya puanı 10 üzerinde olan malzeme kartları`: kolon adayı bulunuyor;
   sayısal koşul ve `olan` niteleyicisi henüz doğrulanmış sorgu yükümlülüğüne
   dönüşmediği için netleştirme isteniyor.
3. `e-mağaza kodu NULL veya boş metin olmayan malzeme kartları`: mevcut anlam
   çözümleme akışı sayısal sonuç üretmiyor. Havuz bu engeli atlamıyor.

Canlı kaynakta beklemeler ve geçici `DATA_SOURCE_UNAVAILABLE` yanıtı gözlendi.
İlk 10 kitap sorusu yeniden denemede bağımsız referansla eşleşti; ilk başarısız
çalıştırma kanıtı korunuyor. Yeni düzeltmelerin doğruluğu, bütün modülün her ifadeyi
anladığı veya üretim gecikmesinin çözüldüğü anlamına gelmez.

## Kanıtlar

Üretim kanıt dizini: `/data/nanobaseai/bi/backups/language-pool-20260909/`.
Ham API cevapları ve büyük sonuç kanıtları bu dizinde tutulur. Yerel raporlar
soru/statü, SQL, sonuç hashleri ve kaynak sürümlerini içerir; müşteri kayıtlarının
kopyasını rapora taşımak gerekmez.

- Mimari ve çalıştırma: `docs/architecture/schema-language-pool.md`
- Yerel kanıt dizini: `outputs/language-pool-20260909/`
- Canlı havuz içerik hash: `aed56bd7cee10e053efc875d841e891631eac46ec7f4749c540d149e31bc5d0e`
