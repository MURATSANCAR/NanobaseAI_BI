# Şemaya bağlı ifade havuzu: geliştirme ve canlı kabul

> **2026-09-09 düzeltmesi:** Tek şirket vardır; farklı kaynaklar yıllar içindeki yedeklerdir. Bu rapordaki “411/211 firması” yorumları geri çekilmiştir. Önceki sayısal karşılaştırmalar tarihsel ölçümlerdir; yedek seçimi, örtüşme ve tekilleştirmenin iş açısından doğruluğunu kanıtlamaz. Aşağıdaki kabul tamamlandı ifadesi bu düzeltmeden önceki değerlendirmedir. Güncel durum: [kaynak anlamı düzeltmesi](source-topology-correction-2026-09-09.md).

**Durum: ifade havuzu yayında; son sürümün canlı kabulü tamamlandı. Dört dil çözümleme senaryosu açık. Bu rapor bütün BI ürününün eksiksiz üretime hazır olduğu iddiasını taşımaz.**

## Son sürümün canlı kabul sonucu

| Kontrol | Sonuç |
|---|---|
| Yerel semantik regresyon | 535 geçti; 2 mevcut bağımlılık kullanım uyarısı |
| Gerçek API + bağlı DB, 100 karmaşık soru | 100 başarılı; 0 başarısız; 0 doğrulanamayan |
| Karmaşıklık | 32 soru 7, 68 soru 8 farklı tablo türü kullanıyor |
| Tam sonuçlar | 100 soru da dolu; sorular boyunca toplam 4.274.127 satır karşılaştırıldı |
| En büyük tek sonuç | 85.703 satır; tam sonuç kesilmedi |
| Ek 20 hedefli kontrol | 10 tam sonuç eşleşmesi, 6 beklenen koruma davranışı, 4 cevaplanamayan ifade |
| Sürüm bütünlüğü | İzlenen 114 dosya değişmedi; hedefli ve geniş kabul boyunca aynı servis süreci |

Başarı, aynı API yürütmesinin `resultId` üzerinden alınan tam sonucu ile bağımsız
kaynak sorgusunun kolon kimlikleri, satır sayıları ve değerlerinin eşleşmesidir.
SQL'i tekrar çalıştırıp benzer sonuç görmek başarı ölçütü yapılmadı. Büyük sonuçların
önizlemesi ile tam sonuç ayrıldı. Yerel testteki beş özellik kaynak dosyasının
hashleri yayınlanan dosyalarla da birebir eşleşti.

NULL ve sıfır için ek kanıt: P09860'ın aynı yürütmeden saklanan 38.852 satırlık
sonucunda 27.098 NULL hücre ve 668 sayısal sıfır hücresi bulundu. Tam sonuç yeniden
SQL çalıştırılmadan alındı; normalize edilmiş hash hem önce kaydedilen API tam
sonucuyla hem bağımsız referansla aynı kaldı. Bu sayılar yalnız bu sonuç kümesine
aittir. Ayrıca S08'de veri olmayan önceki yıl NULL olarak korundu.

- [120 sorunun nihai listesi ve statüleri](../../outputs/language-pool-20260909/evidence/prompts-final-status.md)
- [Özet ölçümler](../../outputs/language-pool-20260909/evidence/final-summary.json)
- [100 karmaşık sorunun SQL, referans ve sonuç hashleri](../../outputs/language-pool-20260909/evidence/complex-final-results.json)
- [20 hedefli kontrolün ayrıntıları](../../outputs/language-pool-20260909/evidence/feature-final-results.json)
- [Son kaynak sürümü](../../outputs/language-pool-20260909/evidence/source-after-final.json)
- [Kanıt dosyalarının hashleri](../../outputs/language-pool-20260909/evidence/evidence-manifest.json)


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
aynı bağımsız referansla **27.790 = 27.790** olarak doğrulandı. Son sürümün L03 kontrolü de geçti.

Ayrıca deterministik derleyicinin fiziksel tablo birleşimlerini kapsam daraltılmadan
üretmesi giderildi. Kapsam, istek için ayrılmış derleyici örneğine uygulanır; ortak
derleyici veya sonraki kapsam belirtilmemiş sorgu değiştirilmez. Son kod değişikliği
öncesindeki 56/100 başarılı koşu arşivlendi; yeni sürüm için kabul baştan çalıştırıldı ve 100/100 tamamlandı.

Dönem karşılaştırması kontrolünde `411 firmasında 2025 ve 2026` ifadesindeki
yılların ikinci firma listesi sanıldığı da bulundu ve düzeltildi. Önceden bağlı
firma değerinden sonra gelen dönem listesi fiziksel kapsamı değiştirmez. Bu
senaryo ve `ile` varyantı yerel regresyona eklendi.

Kapsam eşlemesi `SEMANTIC_PATTERN_LABELS` yapılandırmasını kullanır; koda firma
numarası veya müşteri adı eklenmez. Bu kaynağın ilk fiziksel parametresi `Firma`
olarak etiketlendi. Bilinmeyen, çoklu veya negatif kapsam örneklerinin sessizce
tek firmaya çevrilmemesi gerçek API üzerinden de doğrulandı.

## Doğrulama ayrımı

- Yerel semantik regresyon: **535 geçti**. Bunlar gerçek DB kabulünün yerine geçmez.
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

100 karmaşık soru, mevcut soru üreticisindeki çok tablolu senaryolardan seçilmiş
regresyon kümesidir. Gerçek üretim API'sinde çalıştırılır; soru üreticisinin
kullanılması kontrollü veri tabanı kullanıldığı anlamına gelmez. Bu küme 100
bağımsız insan ifade biçimini veya tüm üretilmiş havuz anlamlarını doğrulamaz.
Havuzun arama kapsamı, bağlı DB sonuç doğruluğu ve dil çözümleme eksikleri ayrı
raporlanır.

## Açık kalanlar

1. `aktif malzeme kartları`: havuz ITEMS.ACTIVE/CODE adayını buluyor; eski resolver
   `aktif` sözcüğünü CLCARD.ACTIVE'a, `malzeme`yi STLINE.LINETYPE'a bağlıyor.
   Çelişkili sonuç sunulmuyor, fakat soru henüz cevaplanamıyor.
2. `kampanya puanı 10 üzerinde olan malzeme kartları`: kolon adayı bulunuyor;
   sayısal koşul ve `olan` niteleyicisi henüz doğrulanmış sorgu yükümlülüğüne
   dönüşmediği için netleştirme isteniyor.
3. `e-mağaza kodu NULL veya boş metin olmayan malzeme kartları`: mevcut anlam
   çözümleme akışı sayısal sonuç üretmiyor. Havuz bu engeli atlamıyor.

4. `411 firmasında 2025 ve 2026 satış tutarı karşılaştırması`: firma/yıl ayrımı
   düzeltildi; mevcut çözümleyici `karşılaştırması` sözcüğünü ayrıca tanımsız
   saydığı için sonuç üretemiyor. Bu ifade başarılı sayılmıyor.

Sekiz tablolu ilk bağımsız referansta aynı adlı açıklama kolonları benzersiz
alias taşımadığından Python kayıt sözlüğünde çakıştı. Referans kolon kimlikleri
ayrıştırılarak aynı gerçek API akışı yeniden sınandı; ilk denemenin kanıtı
`release-4-partial-acceptance/scoped-acceptance-initial-oracle.json` içinde korunur.

Yıl karşılaştırmasının ilk referansı, veri olmayan yıl için `ELSE 0` nedeniyle
sıfır üretiyordu. Her yılı ayrı filtreleyip toplama yapan bağımsız referansla
tekrar kontrol edildi; gerçek API önceki yılın boş sonucunu NULL olarak korudu.
İlk referans `scoped-year-initial-oracle.json` içinde korunur ve doğruluk kanıtı
sayılmaz. `411 firmasında geçen yıla göre satış tutarı` son referansla eşleşti;
dönem kapsamlarının eşitliği veya veri yükünün bütünlüğü bu eşleşmeyle kanıtlanmaz.

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
