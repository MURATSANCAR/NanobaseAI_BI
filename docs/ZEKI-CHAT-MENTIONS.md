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

## Gerçek test sunucusu kabulü — 2026-09-30

Servis `zeki-mention` enabled/active. Beş canlı dosyanın SHA256 özeti main ile eşleşti;
chat imajı `zeki-ai-chat:8.5.3-c1f548205`, yeni dış ağ izni yok. Host işleyicisi ve köprü adapteri kuruludur.
Kurulum dosyalarında AppleDouble 0. Müşteri VM kurulumu ve yerel test yapılmadı.

Gerçek `timasai` hesabı, gerçek chat API/Mongo ve bağlı Logo ile doğrulananlar:

- Etiketsiz mesaj: iş/yanıt yok. Yetkisiz adapter çağrısı: 401.
- Selam: gerçek motor cevabı; boş mention: kullanım yönlendirmesi. Yanıtlar kaynak gruba gitmedi,
  yalnız gönderen ve botun bire bir odasına gitti. API'nin gösterdiği metin, bağımsız Mongo kaydıyla eşleşti.
- 390 px gerçek sohbet kutusundan mention yazıp gönderme ve bot cevabı geçti.
- 320/390/768/1440 px özel sohbet: cevap/sorgu kaydı görünür, yatay taşma, JS hatası ve portal dışı HTTP 0.
- Servis yeniden başlatıldı: o noktadaki dört cevap dört tekil mesaj olarak kaldı; ikinci cevap oluşmadı.
- `2026 perakende satış tutarı`: bot **54.754.171,34**, bağımsız Logo referansı **54.754.171,34**.
  Gerçek sayılar 54754171.34000009 / 54754171.34000006 (float farkı kuruş altı); tek kolon, tek satır,
  kesilme yok. Kullanıcıya gönderilen aynı cevabın kaydı `q_13d95c335a78`, aktör `timasai`.
  Referans: `LG_411_01_INVOICE`, `TRCODE=7`, iptal olmayan 2026 faturaları, `SUM(NETTOTAL)`.

**Yakalanan iş doğruluğu hatası ve sınır:** `2026 toptan satış faturası sayısı` için ortak katalog `STLINE`
satır anahtarını saydırdı: 1.436.023; bağımsız fatura başlığı sayımı 27.425. Bu koşu **FAIL**; başarılı diye
sunulmaz. Katalog bu işte değiştirilmedi. Bot, `METRIC.explain.source=count_cue` ile otomatik türetilmiş
sayım ölçülerini genel bir kuralla rakam olarak yayımlamaz, veri tanımının netleştirilmesi gerektiğini söyler.
Son gerçek tekrar koşusunda hatalı rakam gönderilmedi (`q_c3df6659c1ae`). Katalog sayım düzeltmesi açık iştir.
Bu kontrol tüm Zeki AI cevapları için doğruluk garantisi değildir.

İlk teknik turda sorgu thread kimliği 64 karakterlik kolon sınırını aştı; 53 karaktere indirilip gerçek akış
yeniden doğrulandı. Hata yanıtı başarı sayılmadı. Yetkisi dar bir başka gerçek kişinin hesabı kullanılmadı;
rol daraltma ve AD hesabını kapatma davranışları canlıda **DOĞRULANAMADI**. Kod aynı `/ask` özellik kapısını,
veri/modül kapsamını ve yanıt öncesi etkin AD kontrolünü kullanır.

Üç turda oluşturulan altı geçici oda, 12 kısa ömürlü chat jetonu, bir portal oturumu ve 11 kuyruk işi
temizlendi; kalan geçici oda/yanıt/iş 0, hesap sayısı başlangıçtaki 218. API ile silinen mesajların 27 çöp-kutusu
kopyası da tam kimlikle temizlendi. İlk turda iki oda ayrı temizleme adımında silindiği için `cleanup-first.json`
oda sayısını 0 gösterir. `timasai` adına gerçek motor sorgu geçmişi korunur; ürünün kalıcı bot jetonu korunur.

Kanıtlar: `docs/evidence/2026-09-30-zeki-mention/` — API/Mongo, bağımsız veri referansı, sayım regresyonu,
tarayıcı, yerel sohbet kutusu, yeniden başlatma, temizlik ve kurulum özetleri.
