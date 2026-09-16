# Referans kitabın kabul kayıtları

Kaynak: kullanıcının sağladığı *Ekrana Sığmayan Macera İç Baskı* PDF'si,
SHA-256 `94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50`.
Numaralar PDF sayfa sırasıdır. Kapsam, kullanıcının üretim geliştirme planındaki
B01–B18 ve V01–V08 tanımlarıdır.

Bu dosya değerlendirme ölçütlerini ve henüz kapanmamış kontrolleri tutar;
testlerin geçtiği anlamına gelmez. Modelin atıf kimliğinin varlığı, iddianın o
kaynakla desteklendiği anlamına gelmez. Referans notları model istemine eklenmez.

Gerçek koşu: `18c22ea1-35e8-4e49-b762-82b3320ed49c`. API çıktıları aynı sunucudaki
Editör PostgreSQL sorgularıyla ve değişmez kaynak dosyalarıyla karşılaştırılır.
Yerel mock veya sentetik kitap kullanılmaz. İnsan editör onayı taklit edilmez.

## Kitap senaryoları

| Kimlik | Kaynak | Denetim ve beklenen kapsam | Kabul durumu |
|---|---|---|---|
| B01 | 44–48 | Bozuk metin katmanı fark edilir; OCR, özgün görüntüyle karşılaştırılır. Küçük OCR hataları görünür kalır. | Sayfa içi OCR var; kusursuz metin/editör kabulü verilmedi. |
| B02 | 28–29 | Balon okunur, metindeki aynı konuşmaya bağlanır; tek kanonik olayda iki kaynak korunur. | Balon kaynakta doğrulandı; olay birleştirme çıktısı bekleniyor. |
| B03 | 6/12/14/37 | Az yazılı sayfalarda görsel kayıt ve kaynak erişimi bulunur. | Tam görsel koşusu bekleniyor. |
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
| V01 | Görsel doğru kaynak hash/sürüm/sayfaya açılır. | 48 özgün render hash'i doğrulandı; tam görsel çıktı kapsamı bekleniyor. |
| V02 | Az yazılı sayfalar boş sayılmaz. | B03 ile birlikte değerlendirilecek. |
| V03 | 28–29 konuşması aynı olaya bağlanır. | B02 ile birlikte değerlendirilecek. |
| V04 | Hayal/plan görseli gerçekleşmiş olay sayılmaz. | B08 ile birlikte değerlendirilecek. |
| V05 | Kompozisyonu bozan parçalama yapılmaz. | Tam sayfa render korunuyor; anlamsal kompozisyon kabulü verilmedi. |
| V06 | Belirsiz kişi/nesne eşlemesi kesin olgu sayılmaz. | 6. sayfadaki göz rengi ve 10. sayfadaki hediye yorumu reddedildi; ilk çıktı hatasız değildir. |
| V07 | Tekrar kullanımlar korunur; düzeltme bağımlı görünümleri yeniler. | Ret kararı sahne girdisinden dışlanıyor; tamamlanmış nesilde kapsamlı düzeltme akışı DOĞRULANAMADI. |
| V08 | Yetki ve sürüm, görsel ve önbellekte korunur. | Operatör jetonsuz kaynak/görsel 401 ve no-store var; kitap bazlı çok kullanıcılı yetki DOĞRULANAMADI. |

## Sonuçları değerlendirirken

- Tam API kaydı, bağımsız DB ve kaynak karşılaştırması aynı nesle ait olmalı.
- Soru için yalnız doğru sonuç etiketi yetmez: doğru sayfalar, fail, mod ve
  cevabın eksiksiz kapsamı incelenir. Kaçınan cevap otomatik başarı değildir.
- Her 10 tamamlanmış soru için başarılı/başarısız/doğrulanamayan sayısı ayrı
  tutulur. Üretilmiş cevap sayısı, geçmiş test sayısı değildir.
- Bu tek kitaptan üç kitaplık pilot, üretim kapasitesi veya yayınevi editör
  kabulü sonucu çıkarılmaz. Yeni uygulama sürümüyle offline restore ayrıca
  doğrulanmalıdır; eski altyapı restore sonucu onun yerine geçmez.
