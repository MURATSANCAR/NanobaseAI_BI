# GPU yönetim erişimi: salt okunur tanı

18 Eylül sonraki kontrolde `ssh tt-gpu hostname` exit255 / `Connection closed by UNKNOWN port 65535` verdi. Etkin SSH tanımı GPU özel adresine doğrudan değil Mac `127.0.0.1:11080` SOCKS üzerinden gider. Gerçek port kontrolünde11080listener yok; process-name kontrolünde openconnect/ocproxy yok. Bu hata GPU SSH servisinin çöktüğünü göstermiyor: mevcut yönetim yolunun yerel VPN/SOCKS bileşeni çalışmıyor.

CPU sunucusundan mevcut GPU özel IP'sinin22portuna kontrollü TCP bağlantısı `errno113: No route to host` verdi. CPU kullanıcı SSH yapılandırmasında GPU aliası yok. GPU'dan CPU'ya mevcut ters tünelin18885/18887loopback model portları TCP kabul ediyor; bunlar yönetim SSH portları değildir. İlgili hesap etkin yapılandırması yalnız bu iki remote portu açar, `PermitOpen none`, `PermitTTY no`, `ForceCommand /usr/sbin/nologin` kullanır. Dolayısıyla mevcut model tünelinden yetkisiz yönetim sıçraması yapılmadı.

Mac'teki model proxy/reverse-tunnel launchd hizmetleri VPN/SOCKS hizmeti değildir. Bunları yeniden başlatmak11080eksikliğini çözmez. VPN erişim notlarında OTP gereksinimi bulunuyor; parola/anahtar/OTP metinleri loglanmadı. Mevcut VPN oturumu veya yönetim tüneli hizmeti bulunmadığından güvenli, tek başına restart edilebilir bir yönetim servisi doğrulanamadı. Model servisleri, çıkarım tünelleri ve container'lar değiştirilmedi.

Geri dönüş yolu: kurumun mevcut VPN/OTP oturumunu yeniden kurmasıyla11080listener ve `tt-gpu hostname` tekrar doğrulanmalı. Mac bağımlılığını kalıcı kaldırmak için kurumun yönlendirilmiş yönetim VPN/bastion erişimi veya ayrı, host-key sabitlenmiş ve dar yetkili yönetim bağlantısı ayrıca kurulmalıdır; model tünelinin mevcut izinleri genişletilmemelidir. Böyle bir yeni yolun bulunduğu veya kurulduğu iddia edilmez.

Sonuç: yönetim erişimi ve GPU offline cold-boot kabulü **DOĞRULANAMADI**. Doğrudan model tünelinin açık olması yönetim/cold-boot kabulünün yerine geçmez.
