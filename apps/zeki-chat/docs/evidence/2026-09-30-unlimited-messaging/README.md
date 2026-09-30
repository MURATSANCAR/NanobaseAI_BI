# Kotasız şirket içi sohbet — gerçek ortam kanıtları

30 Eylül 2026; test sunucusu, uygulama `157d9f6a8`, mevcut timasai hesabı ve gerçek Mongo. Yerel test veya uydurma kullanıcı yok.

- `source-evidence.json`, `route-audit.json`: Git eşitliği ve eski lisans uçlarının üretim kodunda bulunmaması.
- `final-deployment.json`, `final-health.json`: doğrulanmış yedek, çalışan imaj/sürüm, sıfır yeniden başlama ve GridFS/özel geçici dosya temizliği.
- `api-evidence.json`: 51 oturum, 44.806 karakter mesaj/taslak/açıklama, 183 MiB gerçek dosya hash karşılaştırması ve 25 REST çağrısı.
- `websocket-evidence.json`, `parallel-send-evidence.json`: gerçek sokette erişim kontrolü ve aynı kullanıcının 6 ayrı bağlantısından eşzamanlı mesajlar. Gönderime başlama aralığı ile işlenme süresi farklıdır.
- `ddp-burst-evidence.json`, `ui-message-evidence.json`, `browser-evidence.json`, `unlimited-*.png`: arayüzün yöntem köprüsü, bağımsız Mongo eşleşmesi ve dört genişlikte ekran.
- `network-evidence.json`, `runtime-evidence.json`: 7/7 dış ağ kontrolü ve konteyner DNS/firewall doğrulaması.
- `data-cleanup.json`, `cleanup-evidence.json`, `data-audit.json`: yalnız bu kabulün kayıt/oturum/jeton temizliği ve bütün koleksiyonlarda kalan kabul referansı 0.

8'den fazla gerçek kişiyle grup DM, ortamda yalnız 3 hesap bulunduğu için doğrulanmadı; kaynak ve canlı ayar sınırsızdır. [Kapsam ve ayrıntılı rapor](../../zeki-unlimited-messaging.md).
