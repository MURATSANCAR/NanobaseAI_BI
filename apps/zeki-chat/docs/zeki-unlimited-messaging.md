# Şirket içi mesajlaşma: kullanım kotası yok

30 Eylül 2026. Test sunucusunda yayındaki sürüm: `157d9f6a8`; imaj: `zeki-ai-chat:8.5.3-157d9f6a8`. Aşağıdaki gerçek kullanım kontrolleri geçti; 8 kişiyi aşan grup için veri eksikliği ayrıca belirtilmiştir.

Ürün kullanıcı/koltuk, toplam mesaj veya depolama lisans kotası uygulamaz. Mesaj karakter ve grup özel mesajı katılımcı sınırları için pozitif olmayan değer sınırsızdır; dosya boyutunda -1 sınırsızdır. Dağıtım bu ayarları -1 olarak sabitler. Uzun mesajı zorunlu dosyaya çevirme ve zamanla mesaj silen saklama politikası kapalıdır. Pozitif sınırların eski tüketicileri sınırsız değeri doğru işleyecek biçimde düzeltildi (taslak, yükleme açıklaması, REST, DDP, istemci, webhook, e-posta ve içe aktarma).

Tam yerel modda kimliği doğrulanmış kullanıcılar için REST/DDP istek kotası uygulanmaz. Anonim giriş ve kimlik doğrulama, oda erişim yetkisi ve dosya türü güvenlik kontrolleri korunur. Giriş jetonları tüketilen mesaj kredisi değildir; kullanıcı başına 50 jeton nedeniyle oturum budaması kaldırıldı. Süre dolması, çıkış ve açıkça iptal etme çalışmaya devam eder.

Eski lisans yolları uygulamanın route/şema/istemci kodundan önceden kaldırılmıştır. Var olmayan bir adrese istek yapılırsa genel 404 yanıtı alınır; bunu değiştirmek için eski lisans uçlarını yeniden tanımlamak gerekmez.

Bu taahhüt lisans ve ürün kullanım kotasının olmamasıdır. Fiziksel disk/RAM, veritabanı belge boyutu ve aktarım altyapısının kapasitesi sonsuz değildir. Liste sayfalaması, görüntü işleme ve alıntı zinciri gibi çalışma sınırları toplam mesaj kotası değildir.

## Gerçek ortam kabulü

Yerel test, mock veya yeni test kullanıcısı kullanılmadı. Test sunucusundaki gerçek sohbet API'si, tarayıcı ve bağımsız Mongo okumaları mevcut `timasai` hesabıyla karşılaştırıldı. Kontroller boş/geçersiz gövdelerle başladı (400/403); yazma kontrolleri yalnız kabulde oluşturulan özel kendine-mesaj odasında yapıldı.

| Kontrol | Sonuç |
| --- | --- |
| Kaynak / sürüm | 9.552 Git dosyası birebir; farklı blob ve AppleDouble dosyası 0 |
| Eski lisans uçları | Test/spec ve kanıtlar hariç 7.257 kaynak dosyasında iki eski uç referansı 0; genel 404 davranışı korunur |
| Kullanıcı başına giriş jetonu | 51 gerçek jeton aynı anda mevcut; ilk jeton hâlâ giriş yapabiliyor |
| Mesaj, taslak, dosya açıklaması | 44.806 karakter; mesajın tam metni API–Mongo ve arayüz–Mongo eşleşti; taslak ve açıklama tam kaydedildi |
| Dosya | Gerçek kaynak arşivi 191.866.880 bayt (yaklaşık 183 MiB); dış nginx üzerinden yüklendi, Mongo boyutu ve indirilen dosyanın SHA-256 değeri kaynakla eşleşti |
| Kimliği doğrulanmış REST | Art arda 25 istek: tamamı 200 |
| Arayüzün HTTP yöntem köprüsü | Art arda 25 `getRoomById`: tamamı başarılı; önceki 10 istek sınırı tekrarlanmadı |
| Doğrudan WebSocket | 25 okuma ve 6 mesaj başarılı; anonim oda okuması reddedildi |
| Aynı kullanıcı, 6 ayrı bağlantı | 6 mesaj 5 ms gönderim aralığında başlatıldı; toplam tamamlanma 4.137 sn; 6 tam mesaj bağımsız Mongo ile eşleşti |
| Mobil ve masaüstü | 320/390/768/1440 px: taşma, JS hatası, görünür eski marka ve dış HTTP isteği 0; uzun mesaj arayüzden gönderildi |
| Oturumu sürdürme | Tarayıcı yenilenince mevcut oturum kullanıldı; yeni SSO jetonu oluşturulmadı |
| Dış ağ | Yeni sürümde 7/7 ağ kontrolü ve üç konteynerin DNS/firewall denetimi geçti |
| Grup özel mesajında 8'den fazla kişi | **DOĞRULANAMADI**: ortamda yalnız 3 hesap var. Kaynakta ve canlı ayarda sınır kaldırıldı; uydurma kullanıcı oluşturulmadı |

İlk turda WebSocket oturumuna bakmak, HTTP yöntem köprüsünün doğrulanmış isteklerini kapsamıyordu. Gerçek tarayıcı koşusu 10 isteklik sınırı yakaladı. Son sürüm, her iki taşıma yolunun sunucuda doğrulanmış kullanıcı kimliğini kullanır ve sınırsız isteklerde sayaç artırmaz. Anonim/giriş kontrolü korunur. Sonuçların tamamı düzeltmeden sonra yeniden alındı.

## Temizlik ve kapsam

Son kabulün 16 mesajı, 1 dosyası, 1 odası, 1 portal oturumu ve 55 sohbet jetonu silindi. Bu kayıtlara ait 18 çöp-kutusu belgesi temizlendi. DB'nin bütün koleksiyonlarında kabul kimlikleriyle kalan referans 0; GridFS dosya/parça sayısı 0. Önceki turun 8 mesajı, 1 dosyası, 1 odası, 1 portal oturumu, 52 jetonu ve 10 çöp-kutusu belgesi de temizlendi. Kullanıcı/oda/mesaj sayıları başlangıçtaki 3/1/1'e döndü. Gerçek kullanıcıya ait genel denetim geçmişi silinmedi.

Son sağlık kontrolünde üç konteyner çalışıyor, yeniden başlama sayısı 0; sürüm `157d9f6a8`. Kaynak `main`'den kuruldu. Müşteri VM'ine kurulum yapılmadı. Bu çalışma az sayıdaki mevcut hesapla fonksiyonel kabuldür; sınırsız kullanıcı kapasitesi veya yük performansı ölçümü değildir.

[JSON kanıtları ve ekran görüntüleri](evidence/2026-09-30-unlimited-messaging/README.md).
