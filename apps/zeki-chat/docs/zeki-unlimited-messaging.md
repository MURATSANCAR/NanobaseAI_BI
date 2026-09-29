# Şirket içi mesajlaşma: kullanım kotası yok

29 Eylül 2026. Bu değişikliğin canlı kabulü henüz DOĞRULANAMADI.

Ürün kullanıcı/koltuk, toplam mesaj veya depolama lisans kotası uygulamaz. Mesaj karakter ve grup özel mesajı katılımcı sınırları için pozitif olmayan değer sınırsızdır; dosya boyutunda -1 sınırsızdır. Dağıtım bu ayarları -1 olarak sabitler. Uzun mesajı zorunlu dosyaya çevirme ve zamanla mesaj silen saklama politikası kapalıdır. Pozitif sınırların eski tüketicileri sınırsız değeri doğru işleyecek biçimde düzeltildi (taslak, yükleme açıklaması, REST, DDP, istemci, webhook, e-posta ve içe aktarma).

Tam yerel modda kimliği doğrulanmış kullanıcılar için REST/DDP istek kotası uygulanmaz. Anonim giriş ve kimlik doğrulama, oda erişim yetkisi ve dosya türü güvenlik kontrolleri korunur. Giriş jetonları tüketilen mesaj kredisi değildir; kullanıcı başına 50 jeton nedeniyle oturum budaması kaldırıldı. Süre dolması, çıkış ve açıkça iptal etme çalışmaya devam eder.

Eski lisans yolları uygulamanın route/şema/istemci kodundan önceden kaldırılmıştır. Var olmayan bir adrese istek yapılırsa genel 404 yanıtı alınır; bunu değiştirmek için eski lisans uçlarını yeniden tanımlamak gerekmez.

Bu taahhüt lisans ve ürün kullanım kotasının olmamasıdır. Fiziksel disk/RAM, veritabanı belge boyutu ve aktarım altyapısının kapasitesi sonsuz değildir. Liste sayfalaması, görüntü işleme ve alıntı zinciri gibi çalışma sınırları toplam mesaj kotası değildir.
