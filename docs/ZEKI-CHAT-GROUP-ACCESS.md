# Özel grup erişimi — gerçek ortam kabulü, 2026-09-30

## Sonuç ve kapsam

**Grup izolasyonu geçti.** Normal kullanıcı üye olmadığı özel grubu listeleyemez/arayamaz; grup bilgisi,
üyeler ve mesajları okuyamaz; oda kimliğini bilerek mesaj gönderemez veya kendisini davet edemez.
Üyelik kaldırıldığında aynı açık oturum anahtarıyla okuma/yazma da reddedilir.
Mevcut ürün korumaları bu kontrollerde yeterli çıktı; grup erişimini değiştiren üretim yaması gerekmedi.

Kullanıcının bu turdaki iki kapsam kararı: AD'de hesabı gerçekten kapatma adımı açık kalacak;
botun veri rolleri ayrı ele alınacak. Portalın canlı “Herkes” rolü bütün veri alanlarını açıyor ve `timasai`
portal yöneticisi. Dolayısıyla bu çalışma **kısıtlı bot veri rolü doğrulaması değildir**; portal yetkileri
değiştirilmedi. Portal yöneticiliği ile chat rolü ayrı kontrol edildi: canlı chat'te `timasai` yalnız `user`.

## Ortam ve yöntem

- Test sunucusu, gerçek chat API `127.0.0.1:4000`, bağımsız Mongo `zeki`, gerçek portal/tarayıcı.
- Chat imajı `zeki-ai-chat:8.5.3-c1f548205`. Kaynak kontrol betiği `scripts/acceptance/zeki-access/check.py`.
- Yeni kullanıcı oluşturulmadı. Mevcut `timasai`, kısa ömürlü oturum ve `user` rolüyle sınandı.
- CRM'den aktarılmış 12 grubun tamamı `t=p`; test hesabı bunların birine üye, 11'ine üye değil.
- Mali İşler grubundaki üç etkin gerçek çalışan da yalnız `user` rolünde. Aynı normal rol ve üyelik
  koruması sınandı; bu çalışanların yerine giriş yapılmadı, özel yazışmaları okunmadı.
- İki geçici özel grup: birine test hesabı üye, diğerine değil. Geçerli yazma denemesi bu geçici gruplarda;
  gerçek departman gruplarına mesaj gönderilmedi. AD/CRM salt okunur; müşteri VM kurulumu ve yerel test yok.

## Bulgular

| Kontrol | Kanıt |
| --- | --- |
| Gerçek CRM grupları | 12/12 özel; üye olunmayan 11 grubun bilgisi reddedildi; listede hiçbiri yok |
| Özel grup API okuma | `groups.info`, `rooms.info`, `groups.history`, `groups.members`, `groups.messages`, `chat.search` reddedildi |
| Yönetim listesi | Normal kullanıcıya `groups.listAll` reddedildi |
| Mesaj yazma | Önce boş gövde reddi; sonra geçerli `chat.sendMessage` üye olmayana ret, Mongo yazımı 0 |
| Olumlu karşılık | Üye olunan grupta aynı token ile mesaj yazıldı, API'den okundu ve Mongo kaydı 1 |
| Diğer yollar | `chat.postMessage` ve kendini ekleyen `groups.invite` reddedildi; üyelik/mesaj 0 |
| Üyeliğin kaldırılması | `groups.kick` sonrası **aynı token** ile grup bilgisi, geçmiş ve önceki tekil `chat.getMessage` reddedildi; gönderim reddedildi, Mongo yazımı 0 |
| Tarayıcı | 320/390/768/1440 px: özel grup arama sonuçlarında yok; doğrudan adres “Oda bulunamadı”, mesaj kutusu yok, yatay taşma yok |

İlk API matrisi **25/25**, ek davet/gönderim kontrolü **2/2**, üyelik kaldırma kontrolü **4/4**.
Tarayıcı dört genişlikte ayrıca geçti. Retler uygulamanın `error-not-allowed`/oda erişim kontrolünden gelen
HTTP 400 yanıtlarıdır; yalnız durum kodu değil içerik yokluğu ve bağımsız DB'de yazı/üyelik olmaması denetlendi.
Bu sonuçlar normal kullanıcılar içindir; yönetim yetkisine sahip hesaplar için aynı yetki iddiası yapılmaz.
Genel/public kanallar (ör. `general`) özel departman gruplarından farklıdır.

## Temizlik ve açık işler

İki geçici oda, beş chat jetonu, bir portal oturumu ve beş çöp-kutusu kaydı temizlendi. Kalan geçici oda,
mesaj ve ilgili jeton 0. Test hesabı hâlâ `user`, toplam hesap sayısı 218; gerçek grup üyelikleri korunur.

AD'de gerçek hesap kapatma/yeniden açma ve kısıtlı bot veri rolü **DOĞRULANAMADI / kapsam dışında**,
kullanıcının kararıyla ayrı kaldı. Finansal katalog sayım sorunu bu turda ele alınmadı.

Kanıtlar: `docs/evidence/2026-09-30-zeki-access/`.
