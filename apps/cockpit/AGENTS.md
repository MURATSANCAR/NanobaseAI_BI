# Tasarım ana kuralı: mobil uyumluluk

Kullanıcının kalıcı ürün kuralı: tüm yeni ve değiştirilen ekranlar mobil öncelikli tasarlanır.

- Giriş, GIF/görseller, modül menüsü, formlar, tablolar, grafikler ve sohbet mobil kapsamın parçasıdır.
- 320, 390, 768 ve masaüstü genişliklerinde kontrol edin. Sayfa yatay taşmamalı; geniş tablolar/kod yalnız kendi kapsayıcısında kayabilir. Sorunu body overflow:hidden ile gizlemeyin.
- Dokunma hedefleri en az 44px; mobil form alanları en az 16px yazı. Uzun Türkçe başlıklar ve hata mesajları sarılmalı.
- Mobil menü açılıp kapanabilmeli; ekranı kapatan sabit öğeler içerik ve form kontrollerini örtmemeli. Safe-area ve dinamik ekran yüksekliğini dikkate alın.
- GIF ve görseller orantılı ölçeklenir; temel içerik kırpılmaz. Azaltılmış hareket tercihini gözetin.
- Tablo/grafik/sohbet dar ekranda birbirini sıkıştırmamalı. Özellikler yalnız mobilde gizlenerek erişilemez hale getirilmemeli.
- İlgili ekranları gerçek tarayıcıda kontrol edin; yalnız derleme başarısını mobil doğrulama olarak raporlamayın.
