# Referans kitabın kabul kayıtları

## 2026-09-18 — Kitap seslendirme kaynak hazırlığı

Kullanıcı ses kaynağını Anilosan15/Turkish_TTS_Data olarak değiştirdi. İlk shard SHA-256 ile doğrulandı, 747 özgün WAV (84,13 dakika) ve metin manifesti çıkarıldı. Tam küme 30.606 kayıt/20,68 GB; tamamı indirilmedi. sıla veri kümesi etiketidir; lisans belirtilmemiş. Mevcut kitaptan API/PG eşliği doğrulanan metinle CPU üzerinde 11,56 sn/24 kHz pilot üretildi. Model tekrar/EOS uyarısı verdi; içerik tamlığı ve dinleme kalitesi DOĞRULANAMADI, ürün kabulü yok. [Hazırlık ve sonraki kabul adımları](../../apps/editor/speech/README.md).

Kaynak: kullanıcının sağladığı *Ekrana Sığmayan Macera İç Baskı* PDF'si,
SHA-256 `94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50`.
Numaralar PDF sayfa sırasıdır. Kapsam, kullanıcının üretim geliştirme planındaki
B01–B18 ve V01–V08 tanımlarıdır.

Bu dosya değerlendirme ölçütlerini ve henüz kapanmamış kontrolleri tutar;
testlerin geçtiği anlamına gelmez. Modelin atıf kimliğinin varlığı, iddianın o
kaynakla desteklendiği anlamına gelmez. Referans notları model istemine eklenmez.

## 17 Eylül güncel kabul durumu

V2 nesli `a9471749-7447-4826-b003-f25e53943763`: işleme 48/48 tamamlandı, nesil NEEDS_REVIEW. 1.149 span (778 anlaşma/371 inceleme), 48 sayfanın altı kayıt türü API/PG eşliği; manuel review/kaynak düzeltmesi 0. Offline paket ve gerçek tam kitap restore/API-PG/mobil kabulü geçti. Bunlar aşağıdaki anlamsal B/V senaryolarını kapatmaz. [Ayrıntılı son durum](2026-09-17-status-and-handoff.md).

Önceki caption nesli `6fffd7ed-f0c6-4de5-af1b-1ebea8898c8b` iptal edildi. O nesilde görülen anlamsal hatalar regresyon gereksinimidir; v2’nin düzeldiği veya aynı çıktıyı ürettiği ayrıca kanıtlanmalıdır. Gerçek uygulama sonuçları bağımsız PostgreSQL ve değişmez kaynakla karşılaştırılır; yerel mock/sentetik kitap veya insan onayı taklidi kullanılmaz.

## Kitap senaryoları

| Kimlik | Kaynak | Denetim ve beklenen kapsam | Kabul durumu |
|---|---|---|---|
| B01 | 44–48 | Bozuk metin katmanı fark edilir; OCR, özgün görüntüyle karşılaştırılır. Küçük OCR hataları görünür kalır. | Sayfa içi OCR var; kusursuz metin/editör kabulü verilmedi. |
| B02 | 28–29 | Balon okunur, metindeki aynı konuşmaya bağlanır; tek kanonik olayda iki kaynak korunur. | Balon kaynakta doğrulandı; olay birleştirme çıktısı bekleniyor. |
| B03 | 6/12/14/37 | Az yazılı sayfalarda görsel kayıt ve kaynak erişimi bulunur. | V2 teknik kapsam: 48 visual_observations sayfa kaydı ve kaynak API/PG eşliği; anlamsal doğruluk DOĞRULANAMADI. |
| B04 | 4/32–33 | Samet Can katkıcı; Can öykü kişisidir. Varlık kayıtları ve cevap ikisini ayırır. | Gerçek çıkarım ve cevap bekleniyor. |
| B05 | 10–11 | Bilge'nin erken geliş açıklaması bulunur; sırf erken geldi diye hata denmez. | Gerçek cevap bekleniyor. |
| B06 | 23 | Max'in hitabı şaka/kişileştirme; robotlar arasında gerçek akrabalık kurulmaz. | Olay/ilişki ve cevap bekleniyor. |
| B07 | 26/28 | Birlikte yapma önerisi ile Bilge'nin gerçekleştirdiği onarım ayrılır. Defne'nin tebriği teknik onarım katkısı değildir. | Olay/fail ve cevap bekleniyor. |
| B08 | 30–34 | Ortak laboratuvar önerisi ve hayal sahnesi, gerçekleşmiş deneyden ayrılır. Can'ın ekibe katılması ayrı olaydır. | Modlar ve cevap bekleniyor. |
| B09 | 42 | Robobi tamir bekler; Max onarımı Robobi'ye taşınmaz. | Olay ve cevap bekleniyor. |
| B10 | 32–33 | Can kendi oyununu geliştirir; yalnız oyun oynayan kişi diye anlatılmaz. | Olay ve cevap bekleniyor. |
| B11 | 40 | Oyunu gerçek dünyaya taşıma gelecek fikridir. | Olay modu ve cevap bekleniyor. |
| B12 | 16/24/35/43 | Okura etkinlik yönergeleri ACTIVITY olarak ayrılır; gerçekleşmiş karakter olayı olmaz. | PDF katmanı korundu; sınıflandırma ve cevap bekleniyor. |
| B13 | 22/27 | Robobi'nin yetenekleri açıklık adayıdır; gerekçesiz kesin tutarsızlık kararı verilmez. İki kaynak da gerekir. | Gerçek cevap ve gerekçe bekleniyor. |
| B14 | 5–10/40–42 | Bir günlük ilgi/duygu değişimi kaynaklı anlatılır; kalıcı kişilik/klinik iyileşme uydurulmaz. | Sentez ve cevap bekleniyor. |
| B15 | 8–9 | Sayfa taşan ayrıştırıcı çıktısı kaynak koordinatlarıyla ayrılır; yazara kusur yüklenmez. | Sayfa içi OCR ve 48 kaydın kaynak/API/DB eşliği doğrulandı; anlamsal çıktı bekleniyor. |
| B16 | 41 | Sayma/saklambaç önerisi, oynanmış oyun değildir. | Olay modu ve cevap bekleniyor. |
| B17 | Kitap bütünü | Defne'nin kesin yaşı uydurulmaz; sınırlı arama sonucundan mutlak yokluk hükmü verilmez. | Gerçek cevap bekleniyor. |
| B18 | Gerçek değişmiş baskı | Eski rapor korunur; değişen kaynağın bağımlıları yeni sürümde hesaplanır. | DOĞRULANAMADI: değişmiş ikinci baskı sağlanmadı. |

## Görsel senaryolar

| Kimlik | Denetim | Kabul durumu |
|---|---|---|
| V01 | Görsel doğru kaynak hash/sürüm/sayfaya açılır. | Yeni nesilde 48 API görüntüsünün hash/no-store kontrolü geçti. Gerçek Chrome’da 320/390/768/1440 px kaynak ve sahne-atıf geçişi doğrulandı; bbox incelemesi eksik. |
| V02 | Az yazılı sayfalar boş sayılmaz. | B03 ile birlikte değerlendirilecek. |
| V03 | 28–29 konuşması aynı olaya bağlanır. | B02 ile birlikte değerlendirilecek. |
| V04 | Hayal/plan görseli gerçekleşmiş olay sayılmaz. | B08 ile birlikte değerlendirilecek. |
| V05 | Kompozisyonu bozan parçalama yapılmaz. | Tam sayfa render korunuyor; anlamsal kompozisyon kabulü verilmedi. |
| V06 | Belirsiz kişi/nesne eşlemesi kesin olgu sayılmaz. | Tarihsel caption koşusunda BAŞARISIZ örnek: 6. sayfadaki açık gözlü kişi “uyuyan/mavi gözlü” diye betimlendi. V2 anlamsal regresyon kabulü DOĞRULANAMADI; adaylar senteze açık değildir. |
| V07 | Tekrar kullanımlar korunur; düzeltme bağımlı görünümleri yeniler. | V2 ham ölçüm kökeni korunur, eski review aktarılmaz; genel düzeltme-bağımlılık akışı DOĞRULANAMADI. |
| V08 | Yetki ve sürüm, görsel ve önbellekte korunur. | Operatör jetonsuz kaynak/görsel 401 ve no-store var; kitap bazlı çok kullanıcılı yetki DOĞRULANAMADI. |

## Sonuçları değerlendirirken

- Tam API kaydı, bağımsız DB ve kaynak karşılaştırması aynı nesle ait olmalı.
- Soru için yalnız doğru sonuç etiketi yetmez: doğru sayfalar, fail, mod ve
  cevabın eksiksiz kapsamı incelenir. Kaçınan cevap otomatik başarı değildir.
- Her 10 tamamlanmış soru için başarılı/başarısız/doğrulanamayan sayısı ayrı
  tutulur. Üretilmiş cevap sayısı, geçmiş test sayısı değildir.
- Bu tek kitaptan üç kitaplık pilot, üretim kapasitesi veya yayınevi editör
  kabulü sonucu çıkarılmaz. V2 offline restore 17 Eylül
  doğrulandı; bu sonuç anlamsal veya farklı müşteri ortamı kabulünün yerine geçmez.
