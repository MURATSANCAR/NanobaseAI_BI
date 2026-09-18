# Mac'ten bağımsız model bağlantısı

CPU sunucusu GPU özel ağına ulaşamıyor fakat GPU, CPU'nun SSH portuna ulaşabiliyorsa bu ters tünel kullanılabilir. Normal müşteri özel ağında doğrudan model endpoint'leri tercih edilir; bu dosyalar her müşteriye sabit IP/hesap kurmaz.

GPU üzerinde yalnız bu iş için yeni Ed25519 anahtarı oluşturulur. Özel anahtar GPU'dan çıkarılmaz veya pakete konmaz. CPU host key'i mevcut güvenilir bağlantıdan alınarak ayrı known_hosts dosyasına sabitlenir; StrictHostKeyChecking kapatılmaz.

CPU üzerinde `editor-gpu-tunnel` sistem hesabı, `/usr/sbin/nologin` kabuğu ve yalnız bu açık anahtar bulunur. `60-editor-gpu-tunnel.conf` iki loopback portuyla sınırlar; komut/TTY, yerel TCP forward ve socket forward kapalıdır. `sshd -t` geçmeden SSH servisi reload edilmez. Diğer hesapların erişimi değişmez.

Dosyanın config.d altında bulunması uygulanması anlamına gelmez: ölçülen CPU'nun ana sshd_config dosyası drop-in dizinini include etmiyordu. Bu nedenle yalnız bu dosya için açık Include eklendi; diğer drop-in dosyaları topluca etkinleştirilmedi. `sshd -T -C user=editor-gpu-tunnel,...` ile etkin kısıtlar, mevcut administrator hesabında önce/sonra tam config eşliği doğrulandı. Yeni bağlantıda komut, izinsiz18889 remote portu ve yerel TCP forwarding denemeleri reddedildi. Mevcut oturumu yeni kurallarla yeniden bağlamadan bu kabul verilmez.

GPU systemd servisindeki `User` gerçek işletim hesabına göre seçilir (ölçülen kurulum: gpuubuntu). `/etc/editor-gpu-tunnel.env` şu değerleri taşır: `TUNNEL_DESTINATION=editor-gpu-tunnel@<cpu-host>`, `TUNNEL_KEY_FILE=<private-key-path>`, `TUNNEL_KNOWN_HOSTS=<pinned-known-hosts-path>`. Varsayılan iki uç CPU127.0.0.1:18885→GPU127.0.0.1:8001 ve CPU127.0.0.1:18887→GPU127.0.0.1:8010. Hedef portlar örnektir; müşteri port çakışması önceden denetlenir.

Yeni tünel ve gerçek çıkarım doğrulanmadan mevcut uygulama upstream'i değiştirilmez. Host nginx yalnız Editör Docker ağlarına açılır; model uçları internete açılmaz. Nginx geçişinde önceki dosya korunur, `nginx -t` sonrası graceful reload yapılır. systemd bağlantı kaybında tekrar bağlanır; bu modelin çıkarım/kalite kabulü değildir.
