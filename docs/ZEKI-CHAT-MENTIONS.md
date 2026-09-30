# Zeki AI mention bağlantısı

## Analiz ve davranış

Yerleşik `zeki.bot` hesabı sistem bildirimlerinin göndereniydi; soru motoruna bağlı değildi.
Zeki AI motoru zaten `/api/v1/ask` üzerinden kullanıcı özelliği, veri alanı ve modül yetkilerini uyguluyor.
Yeni bir model veya dış servis açmak yerine aynı motor kullanılır.

Kullanıcı bir odada `@zeki.bot sorusu` yazar. Yalnız sunucunun mention listesinde bot kimliği bulunan yeni
mesajlar alınır. Eski mesajlar ilk kurulumda geriye dönük işlenmez. Bot/sistem mesajları, şifreli mesajlar,
silinmiş mesajlar, artık oda üyesi olmayan kişiler ve etkin AD hesabıyla tekil eşleşmeyen hesaplar işlenmez.
Etiketlenmeyen mesajlar ve odanın diğer konuşmaları modele gönderilmez.

**Varsayılan yanıt özeldir:** bot soruyu sorana bire bir sohbet açıp cevap verir. Bir grubun diğer üyeleri,
soruyu soran kişinin veri yetkisine sahip olmayabilir. CRM gruplarına bot eklenmez ve üyelik eşitlemesi değişmez.
Her mention bağımsız sorudur; konuşma geçmişinden otomatik bağlam alınmaz. Etiket tek başınaysa kullanım
yardımı gelir. Model/bağlantı hatası bir cevapmış gibi sunulmaz. Sonuç tablosu ve kesilme bilgisi varsa korunur;
sorgu kimliği gösterilir, ham SQL/istemler gösterilmez. Bot yanıtları yeni mention üretmez.

## Uygulama

- `deploy/zeki/mention-worker.py`: host üzerinde kalıcı kuyruk, üç saniyelik okuma döngüsü, etkin AD eşlemesi,
  mevcut bot kimliğiyle gerçek chat API'sinden özel cevap. Tek işleyici kilidi; iş durumu diskte kalır.
- `mention-mongo.cjs`: chat imajındaki mevcut Mongo sürücüsünü kullanan salt okunur yardımcı. Dış ağ açılmaz.
- `backend/semantic_bridge/chat_mention.py`: loopback + ayrı 32+ karakter servis anahtarı gerektiren
  `/api/v1/chat/mention-answer`. `/ask` ile aynı özellik kapısı, `access.acting_as` ile aynı veri/modül kapsamı.
  Kullanıcı adı yalnız güvenilir host işleyicisinden gelir; tarayıcıya servis anahtarı verilmez.
- `zeki-mention.service`: otomatik başlangıç/başarısızlıkta yeniden başlatma; `/var/lib/zeki-mention` 0700,
  kuyruk ve bot jetonu 0600. `/etc/nanobase/zeki-mention.key` köprü servisinin okuyabildiği gizli dosyadır.
- Yanıt kimliği kaynak mesajın SHA256 özetiyle belirlenir: ağ cevabı kaybolsa bile ikinci bot mesajı oluşmaz.
  Model çalışması sırasında süreç kesilirse aynı soru otomatik tekrar çalıştırılmaz; yeniden sorma bilgisi gelir.

AD ve CRM'ye yazma yok. Kullanıcı için sahte portal oturumu oluşturulmaz. Botun kendi kalıcı API jetonu
ürün kimliğidir; test jetonlarıyla karıştırılmaz. Kuyrukta yalnız mention işleri tutulur.

## Kabul durumu

Kod hazır; test sunucusu gerçek API/DB ve mobil tarayıcı kabulü henüz **DOĞRULANAMADI**.
Müşteri VM kurulumu yapılmadı. Yerel test koşulmadı.
