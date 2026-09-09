# Üretim ürün kalitesi — düzeltme ve kabul kaydı

9 Eylül 2026. Kapsam: doğal dil sorusundan gerçek ERP sonucuna, tam rapor teslimine ve doğrulama kanıtına kadar ürün akışı. Giriş/yetkilendirme bu çalışmanın kapsamında değildir.

## Yayın

Semantic bridge ve kokpit değişiklikleri üretime alındı. Servis sağlıklı, DB bağlı; 4.121 profil ve 104 sertifikalı kavram mevcut. Kaynak dosyaları SHA256 ile eşleştirildi; 22 dosyada fark yok. Yedekler ve yayın manifestleri sunucuda `/data/nanobaseai/bi/backups/product-quality-20260909` altında. Son arayüz paketi `index-DfnMGJ23.js`.

Canlı test 30., 53. ve 57. sorulardan sonra güvenli biçimde duraklatılıp sırasıyla saklama koruması, tek hesaplanma zaman damgası ve 64 KiB aktarım tamponu yayınlandı. Test kaldığı yerden sürdü. SQL üretimi ve karşılaştırıcı bu ara yayınlarda değişmedi; yürütme kimliği, saklama ve aktarım davranışları iyileştirildi. Her ara yayının önceki app.py dosyası yedekte korunuyor.

## Bulguların durumu

| # | Bulgu | Uygulanan çözüm | Kabul kanıtı / sınır |
|---|---|---|---|
| 1 | Tam rapor 500 satırda kesiliyordu | Tek DB yürütmesi, parçalı okuma, özel disk dosyası, 64 KiB aktarım, aynı resultId ile tam indirme | Gerçek API 61.865 satır; bağımsız referansla tam eşleşme. Excel 61.865 veri satırı/7 kolon ve 5.255 veri satırı/6 kolon. |
| 2 | Aylık sıralama/değişim sorusu çalışmıyordu | Onaylı temel toplama üzerinde aylık DENSE_RANK, önceki takvim ayı ve ilk ay için önceki yıl verisi | 5.255 satır bağımsız SQL+Python referansıyla eşleşti. Desteklenen aylık soru çerçevesi; tüm analitik soru biçimleri için genel başarı iddiası yok. |
| 3 | Karşılaştırıcı kolon rollerini kaybediyordu | Kolon eşlemesi korunuyor; gerçek API'nin saklanan cevabı karşılaştırılıyor; cevabın SQL'i yeniden yürütülmüyor | Kolon değişimi, NULL/boş ayrımı regresyonları geçti. 100 gerçek soru tekrarı sürüyor. |
| 4 | Kalite kapısı ölçülmemiş başarı oranı yayımlıyordu | Ölçülmeyen metrik UNKNOWN; tam geçiş kapalı. Canlı kanıt için dosya hashleri, kaynak/sürüm/kimlik ve ölçülmüş vaka sayısı zorunlu | Envanterin tek başına geçemediği, değiştirilmiş kanıtın reddedildiği test edildi. SAP/Oracle vb. ölçülmeyen kapsam başarılı ilan edilmiyor. |
| 5 | Grafik/özet kapsamı yanıltıcıydı | Çok boyutlu sonuç tablo; tüm kolonlar korunuyor; gerçek önizleme sayısı, hesaplanma zamanı ve önbellek yaşı gösteriliyor | 320/390/768/1440 piksel tarayıcı kontrolü; sayfa taşması yok. Geniş tablo kendi içinde kayıyor. |
| 6 | Büyük sorgular faydasız arka plan tekrarına giriyordu | Saklanmayan sonuç sıcak listeden çıkarılıyor; tam sonuç disk önbelleğinde tekrar kullanılıyor | Üç eşzamanlı istek aynı zaman/hash/5.255 satırı önbellekten aldı. Bu sınırlı eşzamanlılık kontrolüdür, kapasite/yük sertifikası değildir. |
| 7 | Değer araması ortak bağlantıyı ve süre bütçesini aşıyordu | MSSQL probe için ayrı bağlantı/kilit, kalan süreye göre login/sorgu timeout; bağlantı sonlandırma | Gerçek ayrı bağlantı araması 1,677 sn; ana bağlantı korundu, arama bağlantısı kapandı ve ana SELECT başarılı. Bir önceki denemede sürücü timeout uyguladı. Kasıtlı ağ kesintisi oluşturulmadı. |
| 8 | İş anlamı kapsamı eksikti | Onaylı eşlemeler, metrik koşulları, gerçek JOIN/tarih kolonları mevcut kaynaklarla tarandı | Kritik sorgu kapsamında 47/47 kolon tanımlı. Tüm ERP'deki özel alanların iş anlamı tamamlanmış değildir; ek kaynak bekleniyor. |
| 9 | Katalog sürümü içerikle örtüşmüyordu | Çözücünün kullandığı tam onaylı içerik değişmez snapshot/hash olarak yayınlanıyor; sorgu izine yazılıyor | Canlı katalog v13, 104 kavram. Aynı sayıda kavramla eşleme değiştiğinde hash ve sürümün değiştiği test edildi. |

## Gerçek veri sınır durumları

Aylık analiz: önceki ayı olmayan 1.955 satır, önceki ayı sıfır olan 12 satır; hepsinde değişim NULL. Ocak için Aralık değeri bulunan 432 satır doğrulandı. Önceki ayı negatif 174 satır da bağımsız karşılaştırmaya dahil. Yüzde değişim formülü `100 * (cari - önceki) / ABS(önceki)`; sıfır payda NULL. Sıralamada eşit değerlere aynı DENSE_RANK verilir.

## Saklama ve çalışma sınırları

Tam sonuç varsayılanları: rapor başına 1.000.000 satır / 256 MiB; toplam disk kotası 1 GiB. Limit aşılırsa kısmi sonuç başarı olarak yayımlanmaz. Eski sonuçlar süre, adet veya disk kotası nedeniyle kaldırılabilir; artık saklanmayan resultId için HTTP 410 döner. Yeni bir sorgu sessizce çalıştırılıp eski sonucun yerine konmaz. Servis yeniden başladığında geçici sonuçlar sona erer.

## Doğrulama

- Gerçek müşteri DB'si: 61.865 ve 5.255 satırlık bağımsız kabul karşılaştırmaları geçti.
- Eşzamanlılık: üç istek geçti; son sürümde 7,387–7,506 saniye uçtan uca (başka canlı testler de sürüyordu). Tek warmup 5,004 saniye. Aktarım tamponu öncesindeki üçlü kontrol 15,885–16,000 saniyeydi; bunlar aynı yük altında kontrollü performans karşılaştırması değildir. Genel p95 veya ölçeklenebilirlik sonucu olarak yorumlanmamalı.
- Excel: indirilen iki XLSX dosyası doğrudan incelendi; 61.865 kayıt/yedi kolon (3.167.369 bayt) ve 5.255 kayıt/altı kolon. Başlık satırı bu sayılara dahil değil. 61.865 satırın tüm hücreleri referansla eşleşti (SHA256 `bcc2f889b84ec4c99aee7419c1e7a5de2cf80e56c1aeb54421ab2904dd2bfce9`). XLSX sunumunda NULL/boş metin boş hücredir; bu karşılaştırmada yalnız Excel için bu sunum politikası uygulandı. API doğrulayıcısı NULL ve boş metni ayrı tutar.
- Mobil: 320/390/768/1440 genişliklerinde document.scrollWidth == viewport width. Mobil giriş 16px/44px; Excel düğmesi 44px yüksek.
- TypeScript/Vite derlemesi geçti. Paket büyüklüğü uyarısı mevcut; derleme hatası yok.
- Son kodla birleşik regresyon: **469 geçti**, iki uyarı, 52,72 saniye. Bunlar birim/entegrasyon kontrolleridir; müşteri verisi kabulü yukarıdaki canlı karşılaştırmalarla ayrı yürütüldü.
- 100 soru çalışması sürüyor. Son liste ve statüler tamamlanınca bu kayıt güncellenecek.

## Açık kapsam

Özel ERP tablolarının tamamına iş anlamı atanmadı. İlk incelemedeki 87.721 UNDEFINED kolon toplamı indeks eksikliği sayısı değildir; tümünü tahmini açıklamalarla doldurmak doğru olmaz. Kritik 47 kolon için açıklama/onaylı kavram var; özel iş akışları kaynak doküman ve ayrı gerçek veri kabul soruları gerektiriyor.

Bu kanıtlar test edilen satış/aylık analiz kapsamını destekler; tüm ürün, tüm doğal dil soruları veya ölçülmeyen veri kaynakları için hatasızlık garantisi değildir.
