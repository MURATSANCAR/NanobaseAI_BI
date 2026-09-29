# Yerel ürün kimliği ve lisans yapısı temizliği

29 Eylül 2026. Kaynak: BI `apps/zeki-chat`, uygulama sürümü `a1aec595a`.

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

Nihai imaj ve DB geçişi sürüyor; yeni sürümün canlı kabulü henüz **DOĞRULANAMADI**. Önceki sürüm sonuçları bu kodun kabulü sayılmaz. Son sonuçlar `docs/evidence/2026-09-29-full-cleanup/` altında kaydedilecektir.
