# PDF yükleme ve analiz kaydına dönüş

Mevcut frontend zaten gerçek `/works`, `/editions`, `/uploads`, PDF PUT, kaynak hazırlama, kaldığı yerden yükleme ve analiz başlatma akışlarını içerir. “Arayüz yalnız salt okunur; yükleme henüz yok” ifadesi mevcut kod için güncel değildir. Bunun canlı sürümde eksiksiz kabul edildiği ayrıca kanıtlanmalıdır.

Bu değişiklik analiz başlatma cevabındaki gerçek `job_id` değerini korur. Çalışma alanı yenilenirken hata oluşursa düğme aynı işi açmayı yeniden dener; başka analiz oluşturmaz. Kitap seçimi değişince çalışan asenkron listeleme de aynı işi seçer; listenin ilk işini otomatik seçerek farklı baskı/analize geçmez. Tamamlanmış yükleme yeniden açılırsa mevcut sunucu idempotency anahtarı aynı analiz cevabını döndürür. Yükleme geçmişinin API sayfalaması arayüzde erişilebilir hale gelir; ilk 50 kayıtla sınırlı kalmaz.

Backend/API sözleşmesi, kaynak metni, analiz cevabı ve kabul kararları değiştirilmedi. Kaynak hazırlanması ile anlamsal kabul arayüzde ayrı tutulur. Kitap kimliği veya beklenen cevap üzerinden özel durum yoktur.

## Kabul durumu

Kod/API sözleşmesi statik olarak incelendi. Yerel test, mock, sentetik veri veya yerel build çalıştırılmadı. R5 canlı qualifier sırasında dağıtım yapılmadı. **DOĞRULANAMADI:** bu frontend değişikliğinin gerçek API/DB ile tarayıcı kabulü; 320, 390, 768 ve 1440 px kontrolü. Canlı kabulde gerçek yüklemenin analiz düğmesi, çalışma alanı değişimi, aynı işe yeniden dönüş, bağlantı hatasından sonra yeniden açma ve mevcut gerçek kayıtlarla sayfalama kontrol edilmelidir. Yeni PDF/analiz koşusu ancak ana koşu kapasitesi uygunsa başlatılmalıdır.
