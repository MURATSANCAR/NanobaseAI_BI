# Yerel ürün kimliği ve lisans yapısı temizliği

29 Eylül 2026. Kaynak: BI `apps/zeki-chat`, uygulama sürümü `6c6d214d4`.

Bu belge kimlik/lisans temizliğinin 29 Eylül kabul kaydıdır. Güncel sürüm ve sonradan kaldırılan kullanım sınırları için [30 Eylül kotasız mesajlaşma raporu](zeki-unlimited-messaging.md) geçerlidir.

## Değişiklik

Ürünün lisans belgesi, süre/deneme/plan/kota modeli ve bunlara bağlı ekranlar kaldırıldı. Uygulama, kurulu yerel modülleri `@zeki.chat/capabilities` ile kaydeder; `GET /api/v1/capabilities.info` yalnız modül listesini döndürür. Yetki kontrolleri ve iki aşamalı doğrulama korunur. Başka üreticilerin uygulamalarına ait kullanım hakları bu kayıt tarafından açılmaz; dış mağaza tam yerel kurulumda kapalıdır.

Sahip olunan paketler `@zeki.chat/*`, Meteor paketleri `zekichat:*`, Mongo koleksiyonları `zeki_*`, sistem botu `zeki.bot` kimliğini kullanır. Widget, DOM, font bağlantısı, gizli kurulum dosyaları, örnekler ve çeviriler birlikte tarandı. Ürünün kullanılmayan yayın, bulut geliştirme ve dış test raporlama dosyaları kaldırıldı.

## DB geçişi ve geri dönüş

`deploy/zeki/migrate-owned-identity.cjs` önce bütün koleksiyonların dönüşüm planını ve çakışmalarını okur. Varsayılan çalışma yazmaz. Yazma için uygulama kapalı ve doğrulanmış `mongodump` yedeği olmalıdır. Bot kimliği değişimi transaction içindedir; koleksiyon geçişinin tamamı tek transaction değildir. Hata halinde uygulama kapalı kalır; kısmi hedef koleksiyonları da kapsayacak biçimde yalnız sohbet DB'si doğrulanmış yedekten geri yüklenir.

Geçiş, kullanıcı mesajlarını topluca değiştirmez. Tam belge içerik hashleri, belge sayıları ve indeks sayıları beklenen dönüşümle karşılaştırılır. Gerçek API sonuçları ayrıca bağımsız Mongo okumalarıyla karşılaştırılır.

## Bilinçli kalan teknik bağlar

- Harici npm/Deno paketlerinin gerçek registry kimlikleri korunur. İsim değiştirip var olmayan paket indirilmez. `@rocket.chat/logo` uyumluluk bağı yalnız yerel ZEKI logosuna yönelir.
- UIKit dış uygulama payload sözleşmesindeki eski engine değeri protokol uyumluluğu için korunur.
- Engellenecek adresler güvenlik kurallarında ve kabul problarında; eski kimlikler DB geçişinde bulunur.
- Geçmiş kabul kanıtları, kaynak sorunlarına ilişkin yorum atıfları ve bağımsız bileşen bildirimleri korunur.

Bu nedenle kaynak ağacında eski kelimenin mutlak sıfır olması kabul ölçütü değildir. Ürünün görünür kimliği, kendi lisans mekanizması ve dış çalışma trafiği ayrı doğrulanır. Derleme sunucusunun paket depolarından bağımlılık indirmesi ile çalışan sohbet konteynerlerinin dış çıkışı farklı kapsamlardır.

## Canlı kabul

Test sunucusunda `zeki-ai-chat:8.5.3-6c6d214d4` yayında; aşağıdaki kabul kontrolleri geçti. Kaynak Git ağacından taşındı: 9.523 dosyada içerik farkı ve AppleDouble dosyası 0. İmaj taraması 118.737 dosya ve 61 sahip olunan paket manifestini kapsadı; ürüne ait lisans alanı/eski lisans dosyası 0.

- **Veritabanı:** 90 koleksiyon, 12.615 belge ve 426 indeks tarandı. Taranan içerik ve koleksiyon/indeks adlarında eski üretici/lisans bulgusu 0. Eski lisans/deneme ayarları 0; bot kimliği ve kullanıcı adı `zeki.bot`. Kullanıcı/oda/mesaj sayıları geçiş öncesiyle aynı: 3/1/1.
- **Derin taramada bulunan ek sorun:** harici federation SDK'sı iki boş eski koleksiyonu yeniden oluşturuyordu. Tam yerel modda başlangıç ve ilgili callback yolları kapatıldı; yalnız bu iki boş koleksiyon yedekli kaldırıldı. Korunan 90 koleksiyonun içerik hashleri, sayıları ve indeks sayıları değişmedi; eski koleksiyonlar yeniden oluşmadı.
- **Gerçek API–Mongo karşılaştırması:** 1 abonelik ve 1 mesajın tam sonuç alanları bağımsız DB okumasıyla eşleşti. Capability API kaynakla aynı 25 modülü döndürdü; eski iki lisans ucu 404 verdi.
- **Tarayıcı:** mevcut `timasai` hesabıyla 320/390/768/1440 px doğrulandı. Yatay taşma, görünen eski marka, JS hatası, başarısız JS/CSS/font ve dış HTTP isteği 0. Görsel incelemede bulunan ikon fontu çakışması düzeltildi; dört genişlikte `ZekiChat` fontu ve ikonlar doğrulandı. CSP ve service worker engelleri geçti.
- **Dış çıkış:** 7/7 Node/Deno/doğrudan IP/DNS/host üzerinden dolanma kontrolü geçti; gerçek Mongo bağlantısı çalıştı. Üç konteynerin DNS ve ağ kuralları doğrulandı. Fiziksel eth0 yakalamasında kasıtlı dış bağlantı probunun çıkış paketi 0.
- **Temizlik:** bu kabulde açılan 1 kısa portal oturumu ve 4 sohbet jetonu silindi; kalan 0. Test kullanıcı veya mesajı oluşturulmadı. Yerel test çalıştırılmadı; müşteri VM'ine kurulum yapılmadı.

Kanıtlar: [2026-09-29-full-cleanup](evidence/2026-09-29-full-cleanup/README.md). Sonuçlar belirtilen sürüm, veri ve akışlara aittir; bütün ürün özelliklerinin kabulü veya host yeniden başlatma testi değildir. Çalışan sohbetin otomatik dış servis trafiği engellenir; kullanıcının tarayıcıda elle başka siteye gitmesini engellediğimiz iddia edilmez. Geri dönüş yedekleri ve Git geçmişi silinmemiştir.
