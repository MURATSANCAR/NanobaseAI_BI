# ZEKI AI CHAT — yerel ağ sınırı

## 2026-09-29 kararı ve kapsam

Kullanıcı üreticiye giden tüm yolların paralel denetlenmesini istedi. Üç bağımsız inceleme kaynak, canlı ayarlar/bağımlılıklar ve tarayıcıyı kapsadı. Sabit üretici servisleri kapalı olsa da dinamik URL önizlemesi, webhook, eklenti/Deno ve tarayıcı wildcard CSP yolları bulundu. Kullanıcı açıkça “Tam yerel: tüm dış servis çıkışlarını engelle” seçeneğini seçti. Bu dağıtım yalnız kendi portalı ve MongoDB ile çalışır. Dış bildirim, bağlantı önizlemesi, dış dosya/SSO/çeviri/eklenti ağı ve WebRTC çağrıları bu modda kullanılmaz. Kurulum öncesi canlıda bu entegrasyonlara ait kurulu uygulama/entegrasyon/push token yoktu; dosyalar GridFS'teydi.

## Uygulanan koruma

- Compose `zeki-local` ağı `internal: true`, IPv6 kapalı, sabit köprü `zeki-local0`. Chat, Mongo ve yalnız sabit chat hedefine proxy yapan ingress dışında üye olmaz; dış ağa varsayılan rota yoktur. Mevcut adlandırılmış veri hacimleri değişmez.
- Host INPUT zincirinde yalnız `zeki-local0` ve `zeki-ingress0` için `ZEKI-LOCAL-HOST`: yalnız `ESTABLISHED,RELATED --ctdir REPLY` cevapları geçer, konteynerin hosta başlattığı bağlantılar (önceden açık olanlar dahil) reddedilir. Böylece host üzerindeki bir proxy yoluna da gidemez. Diğer konteyner/SSH/portal trafiği bu kurala girmez.
- İç ağda Docker port yayını yapılamadığı canlıda görüldü. Digest ile sabitlenmiş, yetkisiz kullanıcıyla çalışan, salt okunur `zeki-ingress` nginx yalnız 127.0.0.1:4000 dinler; tek upstream `zeki-chat:3000` (dinamik istek adresi upstream olamaz). Ek ingress ağından dış çıkış `DOCKER-USER`/FORWARD `ZEKI-LOCAL-EGRESS` zinciriyle reddedilir; yalnız `REPLY` yönündeki bağlantı cevapları geçer. Chat/Mongo bu ingress ağına bağlı değildir. Üç servisin de DNS fallback adresi açıkça kendi loopback adresine bağlanır (`dns: [127.0.0.1]`); Docker servis adı çözülür, dış DNS çözülmez. Aksi halde Docker daemon DNS aktarması ağ filtresinin dışından çalışabildiği negatif kontrolde görüldü.
- `ZEKI_LOCAL_ONLY=true`: CSP aynı origin ile sınırlı; ek CDN/CSP ayarları bunu genişletemez, custom script dağıtılmaz, VoIP provider açılmaz. ICE, push, NPS ve oEmbed env override ile kapalıdır.
- Worker sohbetin kendi alt yoluna kaydolur; güncelleme HTTP cache kullanmadan denetlenir. Dosya fetch yalnız aynı origin ve `redirect: error` ile çalışır. Eski decrypted cache okunmaz/yazılmaz; ortak portal cache verisi silinmez. Decrypted belge ve hata yanıtları sandbox CSP, `nosniff`, `no-store` taşır. Bütün iframe kaynakları kapalıdır; otomatik giriş yönlendirmesi aynı origin ile sınırlıdır.
- `serverFetch` başlangıç ve bütün redirect hedeflerini DNS/proxy öncesi vendor filtresinden geçirir. Bu katman ağ izolasyonunun yerine geçmez; Deno/raw socket de ağ izolasyonu ile sınırlıdır.
- Eski `apps/meteor/install.sh` upstream indirme yapamaz. Derleme ana makinede main kaynaklarından yapılır; bağımlılık indirmeleri çalışma zamanı izolasyonundan ayrıdır.

## Kurulum

Main kaynağı taşınır ve yeni imaj derlenir. Yeniden başlatmadan önce:

```bash
sudo install -m 0755 deploy/zeki/local-egress-firewall.sh /usr/local/sbin/zeki-local-egress
sudo install -m 0644 deploy/zeki/zeki-local-egress.service /etc/systemd/system/zeki-local-egress.service
sudo systemctl daemon-reload
sudo systemctl enable --now zeki-local-egress.service
```

Sonra `deploy/zeki` altında sabit imaj etiketiyle `docker compose --env-file .env -p zeki up -d` ve `bash clear-external-ice.sh` uygulanır. Mongo health ve aynı veri hacimleri doğrulanır. Docker ağı kalıcıdır; systemd guard UFW/netfilter/nftables restore birimlerinden sonra, Docker başlamadan önce uygulanır ve Docker için gerekli bir birimdir; guard başarısızsa Docker başlangıcı da başarısız olur. Docker yeniden başlatıldığında guard yeniden uygulanır. Build betiği restart öncesi yalnız active durumuna güvenmez, kuralları yeniden uygular. Ağ kartına dış ağ eklemek veya local-only modu kaldırmak bu kabulü geçersiz kılar.

Saat dilimi (ZEKI-28): üç konteyner `TZ=Europe/Istanbul` ile ve hostun `/usr/share/zoneinfo` dizini salt okunur bağlanarak çalışır (yerel dosya, ağ gerektirmez); sohbette rapor saat dilimi `Default_Timezone_For_Reporting=custom` + `Default_Custom_Timezone=Europe/Istanbul` env ile sabittir. Mongo tarihleri UTC saklamaya devam eder; TZ yalnız günlük saatini ve sunucu tarafı gün hesabını etkiler. İmaj derlemesi gerekmez; `docker compose --env-file .env -p zeki up -d` üç konteyneri aynı veri hacimleriyle yeniden oluşturur.

## Kabul sınırı

Kabul bu sürüm/ayar/ağ topolojisi içindir. Paket yakalama yalnız zaman penceresini gösterir; kalıcı koruma ağ topolojisi ve CSP'dir. Kullanıcının tarayıcı adres çubuğuna bir site yazması, sağ tıkla yeni sekmeye gitmesi veya sunucu yöneticisinin firewall/deployment politikasını değiştirmesi ürünün otomatik servis trafiği değildir ve bu korumanın kapsamı dışındadır. Tüm zamanlanmış işlerin her olası veriyle çalıştığı iddia edilmez; ağ bariyeri aynı konteynerdeki işlere uygulanır.

## İkinci bağımsız tarama ve canlı kabul — 2026-09-29 21:00

Kullanıcının «tekrar bak başka kalmasın» talebi üzerine paralel kaynak/ağ/tarayıcı incelemesi tekrarlandı. Ek olarak bulunan ve düzeltilen yollar:

- Eski kök kapsamlı worker kaydı, dış dosya URL/yönlendirmesi ve bütün origin cache'lerinden eski belge cevabı okuma. Worker artık `/timas/sohbet/` kapsamında; güncelleme cache kullanmaz, eski decrypted cache okunmaz. Bütün belge/hata yanıtları ayrı sandbox CSP + no-store + nosniff taşır.
- Aynı origin iframe ile farklı portal belgesinin daha geniş politikasını kullanma: `frame-src 'none'`. Otomatik giriş yönlendirmesi aynı origin ile sınırlı.
- Önceden kurulmuş dış bağlantıyı yaşatabilen geniş conntrack izni: yalnız REPLY yönü; eski geniş kural IPv4/IPv6'dan kaldırılır.
- UFW başlangıcının kuralları sonradan ezmesi ihtimali: guard firewall restore birimlerinden sonra, Docker'dan önce çalışır. Chat ve Mongo DNS fallback de loopback'e sabitlendi.

Son uygulama/konfig `9b12e38` (`6c4c4d3` + decrypted cache düzeltmesi); canlı imaj `zeki-ai-chat:8.5.3-9b12e38`. Main arşiviyle kuruldu; paket/Meteor/Docker derlemesi yalnız test sunucusunda. Üç konteyner aynı kalıcı veri hacimleriyle yeniden oluşturuldu. 9.612 kaynak dosyası main ile eşleşti; fark/AppleDouble 0. Yerel test çalıştırılmadı; müşteri VM'ine kurulmadı.

| Son sürüm kontrolü | Sonuç |
| --- | --- |
| Chat ağı | Gerçek Mongo açık; dış DNS/Node fetch/IPv4/IPv6/host proxy/Deno engelli, 7/7 |
| Mongo ve ingress | Üç servisin DNS fallback'i 127.0.0.1; Mongo dış DNS EAI_AGAIN, ingress dış DNS SERVFAIL ve dış HTTP REJECT; iç servis DNS açık |
| Kalıcı firewall | IPv4/IPv6 iki zincirde yalnız REPLY RETURN + REJECT; guard active/enabled, UFW sonrası/Docker öncesi |
| Fiziksel ağ | Yeni firewall ile bilinçli 1.1.1.1:80 denemesi reddedildi; eth0 8 sn pencerede eşleşen paket 0 (imaj değişmeden önce; firewall/ingress politikası aynı) |
| Gerçek tarayıcı | Mevcut timasai ile 320/390/768/1440 px giriş başarılı; taşma/JS hatası/görünür vendor metni 0 |
| Çalışan worker | Gerçek scope/active/controller doğru; updateViaCache none; iki dış adres ve credentialized URL reddedildi, aynı-origin fetch200, gerçek302 redirect reddedildi |
| Worker belge politikası | Gerçek eksik dosya404 ve hatalı anahtar400 worker üzerinden sandbox CSP/no-store ile döndü; nosniff doğrulandı, eski cache okuma/yazma yok |
| Browser çıkışları | Fetch/WebSocket/görsel/dış iframe/aynı-origin iframe reddedildi; vendor link iptal; ağa ulaşan yasak HTTP isteği0 |
| API–gerçek DB | Beş ayar ve abonelik listesinin tüm `_id/rid/unread` alanları/satır sayısı bağımsız MongoDB okumasıyla eşleşti (1 satır) |
| Veri ve temizlik | Kullanıcı/mesaj/oda3/1/1 değişmedi; 1 portal oturumu ve4 kontrol jetonu silindi, kalan jeton/oturum dosyası0 |

Kanıt: [dağıtım](evidence/2026-09-29-recheck/deployment-evidence.json), [ağ](evidence/2026-09-29-recheck/network-evidence.json), [runtime](evidence/2026-09-29-recheck/runtime-evidence.json), [tarayıcı/worker](evidence/2026-09-29-recheck/browser-evidence.json), [API–DB](evidence/2026-09-29-recheck/subscriptions-evidence.json), [veri/temizlik](evidence/2026-09-29-recheck/data-evidence.json), [kaynak](evidence/2026-09-29-recheck/source-evidence.json), [fiziksel ağ](evidence/2026-09-29-recheck/physical-evidence.json), [derleme](evidence/2026-09-29-recheck/build-evidence.json). Browser attemptedRequestHosts içindeki vendor adresi bilinçli negatif probudur, başarılı dış trafik değildir.

Açık sohbet sekmesi bir kez yenilenmelidir; hiç yenilenmemiş eski sayfaya geriye dönük CSP uygulanmış sayılmaz. Tam host/Docker yeniden başlatma ve gerçek şifreli ek dosyanın başarılı decrypt işlevi bu turda sınanmadı; worker hata yolu, çalışan guard ve kaynak incelemesi doğrulandı. Ağ kabulü bu sürüm ve değişmeyen dağıtım politikası içindir; bütün ürün özelliklerinin fonksiyonel kabulü değildir. Kontrol betiğinde container'a root sahipliğiyle kopyalanan geçici dosya temizliği ve mongosh await sözdizimi düzeltildikten sonra runtime kontrolleri tekrar geçti. GitHub push yeniden `Repository not found` döndü; chat yerel main ve test sunucusunda güncel, uzak yayın hâlâ bekliyor.

## Önceki canlı kabul — 2026-09-29

Test sunucusunda uygulama imajı `zeki-ai-chat:8.5.3-43bcc94`, uygulama kodu `43bcc94`; ağ/dağıtım son kaynak commit'i `098dfe2`. Kaynak karşılaştırması 9.597 dosyada fark 0, AppleDouble 0. Build: 67 paket görevi + Meteor + Docker, sunucuda tamamlandı. Yerel test çalıştırılmadı. Kullanıcı/mesaj/oda sayıları 3/1/1 olarak korundu, aynı üç veri hacmi kullanılıyor. Mongo yedeği ve eski imaj saklandı.

| Kabul | Sonuç |
| --- | --- |
| Vendor URL guard | 14 engellenen + 6 izin verilen senaryo geçti; çalışan imajın gerçek serverFetch'i normal/SSRF bypass/allowlist seçenekleriyle 3/3 reddetti |
| Chat ağ bariyeri | Mongo bağlantısı açık; dış DNS, Node fetch, IPv4, IPv6, host proxy ve Deno fetch kapalı: 7/7 |
| Ingress | İç `zeki-chat` DNS çözümü açık; dış DNS SERVFAIL; dış HTTP firewall REJECT; firewall enabled/active |
| Fiziksel ağ | Ingress'ten bilinçli 1.1.1.1:80 çıkış denemesinde `eth0` üzerinde eşleşen paket 0; bağlantı reddedildi |
| Tarayıcı | Gerçek timasai SSO, 320/390/768/1440 px: oturum açık, taşma/JS hatası/görünür vendor metni 0 |
| CSP negatif kabul | Dış fetch, WebSocket, görsel ve iframe politikayla reddedildi; normal vendor link tıklaması engellendi; ağa ulaşan yasak tarayıcı isteği 0 |
| Worker | Gerçek enc.js 200, JavaScript MIME/içerik ve aynı kısıtlı CSP doğrulandı |
| Gerçek API–DB | Beş ayar birebir eşleşti; gerçek abonelik listesinin tüm `_id/rid/unread` alanları ve satır sayısı bağımsız MongoDB okumasıyla eşleşti |
| Temizlik | 3 kısa ömürlü portal oturumu, 12 sohbet jetonu silindi; yeni kullanıcı ve kalan kontrol jetonu/oturum dosyası 0 |

Chat ağ ad alanında 180 sn, son ingress yapılandırmasında 120 sn paket metadata'sı toplandı. Normal trafik yerel servisler/host yanıtlarıydı. Ingress kaydındaki tek `1.1.1.1` paketi bilinçli negatif probun konteynerden köprüye çıkan SYN'idir; firewall'da reddedildi. Ayrı fiziksel NIC kontrolünde dışarı çıkmadığı görüldü. Browser `attemptedRequestHosts` listesindeki vendor host da bilinçli CSP probudur; başarılı dış istek anlamına gelmez.

Kurulum sırasında bulunan sorunlar giderildi: internal ağın port yayımlamaması için sabit upstream ingress eklendi; otomatik Docker subnetinin müşteri VPN'iyle çakışması açık 10.254.250.0/28 ile düzeltildi; ingress Docker DNS aktarımı kapatıldı. İlk WebSocket kabulü asenkron CSP hatasını yakalamadığı için yanlış başarısızdı, hata olayını bekleyecek şekilde düzeltildi. İlk ayar okuyucu sayfalama nedeniyle readiness bekledi ve 429 aldı; poller durduruldu, beş ayar açık kimlik filtresiyle tek çağrıda doğrulandı. Boş env override'ın DB'de bıraktığı eski ICE değeri dar kapsamlı migration ile temizlendi. Son kontroller bu düzeltmelerden sonra tekrar geçti.

Kanıtlar: [dağıtım](evidence/2026-09-29-egress/deployment-evidence.json), [chat ağı](evidence/2026-09-29-egress/network-probes-final.json), [ingress](evidence/2026-09-29-egress/ingress-evidence.json), [fiziksel ağ](evidence/2026-09-29-egress/physical-egress-evidence.json), [tarayıcı](evidence/2026-09-29-egress/browser-evidence.json), [gerçek abonelik](evidence/2026-09-29-egress/subscriptions-evidence.json), [veri/temizlik](evidence/2026-09-29-egress/data-continuity.json), [kaynak](evidence/2026-09-29-egress/source-evidence.json).

Sunucunun/Docker daemon'unun tamamı yeniden başlatılmadı; kalıcılık birim bağımlılıkları ve aktif kurallarla doğrulandı, servis konteynerleri yeniden oluşturuldu. Bütün sohbet özelliklerinin fonksiyonel kabulü veya mesaj gönderme testi yapılmadı; kabul giriş, okuma, arayüz ve ağ izolasyonu içindir. Müşteri VM'ine kurulum yapılmadı. GitHub hedefi hâlâ `Repository not found`; yerel main ve test sunucusu güncel, GitHub yayını bekliyor.

Ağ tasarımı referansı: [Docker internal network](https://docs.docker.com/engine/network/) ve [Docker kullanıcı firewall zinciri](https://docs.docker.com/engine/network/firewall-iptables/).
