# Ekrana Sığmayan Macera — bağımsız kaynak inceleme notları

Bu dosya, sunucudaki otomatik analizi karşılaştırmak için Codex'in gerçek kaynak
sayfalarından hazırladığı referanstır. Yerel Qwen modelinin çıktısı, yayınevi
editör onayı veya tamamlanmış pilot kabul raporu değildir. Otomatik analize
beklenen cevap olarak verilmez.

- Kaynak: kullanıcının sağladığı iç baskı PDF; 48 sayfa, 19.806.912 bayt.
- SHA-256: `94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50`.
- Sayfa numaraları PDF sırasıdır; genel olarak basılı etiket varsayımı yapılmaz.
- Referans: özgün PDF render'ları, gerçek sunucudaki PDF metin katmanı ve
  `ocr-regions-v2` sayfa içi OCR adayları. OCR hataları özgün görselle ayrıştırılır.
- İncelenen otomatik nesil: `18c22ea1-35e8-4e49-b762-82b3320ed49c`.

## Eserin kapsamı

Öykü, ailesinin teknoloji molası kararından sonra tabletini arayan Defne'nin
arkadaşı Bilge, robotlar, yeni tanıştığı Can ve dedesiyle geçirdiği günü anlatır.
Kodlama ve robot merakı; arkadaşlık, bahçede üretim ve doğayı fark etme ile
birlikte ele alınır. Sonuç, teknolojinin bütünüyle reddedilmesi değildir.
Anlatı 42. sayfada kapanır; aralara yerleştirilmiş etkinlikler ve 44–48. sayfalardaki
bilgilendirici kitapçık ayrı içerik türleri olarak tutulmalıdır.

## Karakterler ve kimlik sınırları

| Varlık | Kaynağın desteklediği rol | Başlıca PDF sayfaları |
|---|---|---|
| Defne | Öykünün odağındaki çocuk; başlangıçta tabletini arar, gün içinde kodlama ve doğaya ilgi gösterir. Kesin yaşı verilmiş bir olgu olarak çıkarılamaz. | 5–15, 25–42 |
| Bilge | Defne'nin arkadaşı; Max'i geliştirmiştir, kodlama bilgilerini paylaşır ve denge sorununu çözer. | 10–15, 25–28 |
| Can | Mahalleye yeni taşınan çocuk; e-sporla ilgilidir ve tablette kendi oyununu geliştirir. Yazar Samet Can ile aynı kişi değildir. | 32–34, 36, 40 |
| Profesör Bulut | Defne'nin dedesi; bilim/robot deneyimini çocuklarla paylaşır; Robobi'yi yaklaşık kırk yıl önce yaptığını anlatır. | 8, 19–22, 27, 30–31, 36–42 |
| Max | Bilge'nin robotu; konuşur ve çeşitli işlevler gösterir. Denge arızası, onarımı ve Robobi'den farklı kimliği korunmalıdır. | 11–15, 18–23, 26–29, 33, 40–42 |
| Robobi | Bulut'un eski robotu; geçmiş işlevleri Bulut'un anlatımıdır. Finalde tamir beklemektedir. | 22–23, 27, 30–37, 42 |
| Masal | Defne'nin kedisi; gerçek kedi ile tablet oyununun sanal kedileri ayrıdır. | 7–10, 19, 38–42 |
| Anne ve baba | Ebeveynler; teknoloji molası ve gündelik aile akışında yer alırlar. Metinde verilmemiş özel adlar üretilmemelidir. | 7–10, 17, 32, 39–42 |
| Zeynep | 32. sayfada gelişinden söz edilir. Hitaptan tek başına biyolojik akrabalık veya ek aile bağı çıkarılmaz. | 32 |
| Samet Can | Yazar; hikâye karakteri Can'dan ayrı eser katkıcısıdır. | 4 |
| Kerem Çufalar | Çizer; hikâye kişisi değildir. | 4 |

## Olay akışı ve anlatı modu

| Kaynak | Olay/iddia | Mod ve dikkat noktası |
|---|---|---|
| 5–9 | Defne tabletini düşünerek uykusuz kalır, sabah aramaya koyulur ve babasıyla karşılaşır. | Gerçekleşen öykü olayları. Babanın günlük sekiz saat ifadesi, önce babanın beyanıdır. |
| 10–11 | Öğleden sonra beklenen Bilge erken gelir. Bekleyemediğini ve Max'i sabah şarj etmek istediğini açıklar. | Gerçekleşmiş geliş ve Bilge'nin açıklaması; salt saat farkından tutarsızlık üretilmez. |
| 11–15 | Max tanıtılır; dans eder, takla denemesinde düşer ve denge sorunu belirir. | Gerçekleşmiş olay. Görsel 12 ve 14, metni az olduğu için boş sayılamaz. |
| 17–20 | Kahvaltı ve dedenin bahçesine geçiş; Max'in işlevleri gösterilir. | Gerçekleşmiş olaylar ile karakterlerin yetenek beyanları ayrı tutulur. |
| 21–23 | Tavan arasında Robobi bulunur. Max'in dedeciğim hitabı güldürür. | Robot akrabalığı değil şaka/kişileştirme. Bulut–Defne dede/torun bağıyla karıştırılmaz. |
| 25–28 | Kodlama ve tamir konuşulur; Bilge bilgisayarda denge sorununu çözer, Defne tebrik eder. | Gerçekleşmiş onarımın faili Bilge. Önceki birlikte yapma önerisinden Defne'ye gerçekleşmiş teknik katkı yazılmaz. |
| 28–29 | Max'in Güneş Sistemi gösterisi ve Defne'nin görüntünün nasıl yapıldığını sorması. | 29. sayfadaki balon, 28. sayfadaki konuşmanın görsel kanıtıdır; ikinci bağımsız konuşma olayı sayılmamalıdır. |
| 30–31 | Robotların birleştirilmesiyle mini laboratuvar fikri; Defne'nin zihninde canlanan deney sahnesi. | Öneri/plan ve hayal ayrımı. Robobi'nin tamamlanmış onarımı veya yapılmış deney sonucu değildir. |
| 32–34 | Can'ın oyun geliştirdiği görülür, ekibe katılması konuşulur ve kabul eder. | Can yalnız oyun oynayan biri diye özetlenmez. Ekibe katılım gerçekleşir; sonraki laboratuvar hedefleri plandır. |
| 36–39 | Çalışmaya mola, domates toplama, kelebeği fark etme ve yağmurdan eve koşma. | Gerçekleşmiş olaylar. 37. sayfa robot üzerinde çalışma görselidir; Robobi'nin tamirinin bittiğini kanıtlamaz. |
| 40 | Can oyununu gerçek dünyaya taşımak istediğini söyler; robotla doğa araştırma fikirleri konuşulur. | Gelecek planları. Bitmiş uygulama veya yapılmış araştırma sonucu değildir. |
| 41–42 | Yemek ve saklambaç önerileri, sıcak çikolata, Defne'nin gününe ilişkin değerlendirmesi. | Saklambaç/sayma önerisi, gerçekleşmiş oyun değildir. Robobi hâlâ tamir bekler. |

## Sınırlı edebî değerlendirme adayları

### Defne'nin gün içindeki değişimi

Başlangıçta düşünceleri tabletteki rekora odaklanır; uykusuzluk, gizlice arama ve
yakalanınca mahcubiyet anlatılır (5–10). Bilge'nin robotu ve kodlama, merakını
başka bir etkinliğe yönlendirir (11–15, 25–28). Bahçedeki deneyimler ve son
konuşması, ekran dışındaki yaşantılara verdiği değerin artışını gösterir (38–42).

Bu, bir günlük anlatı içindeki ilgi/duygu değişimidir. Kalıcı kişilik değişimi,
klinik tanı veya bağımlılığın tedavi edildiği sonucu değildir. 36. sayfada robot
işine devam etmek istemesi, değişimin basit bir teknoloji karşıtlığı olmadığını
gösteren karşı okumadır.

### Tüketimden üretime ve birlikte öğrenmeye yönelme

Bilge'nin kodlaması, Can'ın kendi oyununu geliştirmesi ve ortak proje önerileri
bu yorumu destekler (15, 25–34, 40). Teknoloji yaratıcı bir araç olarak da
görünür. Alternatif okuma, ekranın kendisinden çok kullanım amacı ve denge
üzerinde durur; her teknolojik uğraş otomatik olarak zararlı gösterilmez.

### Doğa ve gündelik deneyimi fark etme

Domates toplama, kelebek, yağmur ve son sohbet doğal/gündelik yaşantıları
öykünün merak ve keyif alanına alır (36–42). Robotlarla doğa araştırma fikri
iki alanı birbirini dışlayan karşıtlar hâline getirmez.

### Hatanın öğrenmeye açılması

Max'in düşmesi ve Profesör Bulut'un hatalar hakkındaki sözü, hata yapmayı
onarılabilir bir süreç olarak sunar (13–15, 20–21, 26–28). Bu yorumun kaynağı
belirli sahnelerdir; bütün karakterlerin tüm hata deneyimlerine genellenmez.

## Editör incelemesine ayrılacak noktalar

1. **Robobi'nin geçmiş yetenekleri:** 22. sayfadaki yalnız basit matematik
   vurgusu ile 27. sayfadaki ipucu/deney işlevleri birlikte okunmalıdır. Açıklık
   gerektiren adaydır; bağlam incelenmeden kesin hata hükmü verilmez.
2. **OCR kalite farkları:** 44. sayfada örneğin Hazırsan sözcüğünün OCR adayı
   hatalıdır. Metnin büyük bölümünün okunması, sıfır hata veya editör kabulü
   değildir. 29. sayfanın konuşma balonu sayfa içi OCR'de okunmuştur; çevredeki
   çizgilerden üretilen anlamsız OCR parçaları kaynak yazısı sayılmamalıdır.
3. **Renkli etkinlik panelleri:** 16 ve 24 başta olmak üzere OCR gövde metnini
   kaçırabilir. Görünür kaynak ve okunabilir PDF metin katmanı birlikte
   kullanılmalıdır. 16/24/35/43 etkinlikleri okura yöneliktir.
4. **Bilgilendirici kitapçık:** 44–48, öyküde gerçekleşmiş olaylardan ayrıdır.
   Ekran kullanımı/bağımlılık hakkındaki ifadeler kitapçığın anlatımı olarak
   kaydedilir; bu inceleme tıbbi doğrulama veya karakter tanısı değildir.
5. **Sürüm testi:** Değişmiş gerçek ikinci baskı yoktur. B18'in kaynak değişimi
   kabulü yalnız mevcut PDF üzerinden geçmiş sayılamaz.

## Otomatik koşunun değerlendirilmesi

Bu referans notları tek başına B01–B18 veya V01–V08 başarısı değildir. Otomatik
API'nin gerçekten ürettiği kayıtlar, cevap kapsamı ve aynı yürütmenin atıfları
bu kaynaklarla karşılaştırılmalıdır. İnsan editör kabulü ayrıca beklenir.
