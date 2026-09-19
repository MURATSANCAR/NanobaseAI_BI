# GPU model tüneli (TT GPU → nanobase-direct)

CPU sunucusu GPU'nun özel ağına ulaşamıyor, GPU ise CPU'nun SSH portuna ulaşabiliyor. Bu ters tünel GPU'daki modeli (`qwen38-27b`, port 8001, sunulan ad `nanobaseAI`) CPU sunucusunda `127.0.0.1:18885` olarak açar. BI'ın semantik köprüsü (`nanobase-semantic-bridge.service`, :8795) modele bu adresten bağlanır (`OPENAI_API_BASE=http://127.0.0.1:18885/v1`). Tünel koparsa BI'ın model gerektiren soruları durur.

Kurulu parçalar (adlar sunucudaki gerçek adlardır, tarihsel nedenle `editor-gpu-tunnel`):

- GPU (`gpuubuntu`): systemd servisi `editor-gpu-tunnel.service` (bu dizindeki dosya), ortam dosyası `/etc/editor-gpu-tunnel.env` (`TUNNEL_DESTINATION`, `TUNNEL_KEY_FILE`, `TUNNEL_KNOWN_HOSTS`). Yalnız bu iş için üretilmiş Ed25519 anahtarı GPU'dan çıkmaz; CPU host key'i ayrı known_hosts dosyasına sabitlenir.
- CPU (`nanobase-direct`): komut/TTY açamayan `editor-gpu-tunnel` hesabı (`/usr/sbin/nologin`) ve `/etc/ssh/sshd_config.d/60-editor-gpu-tunnel.conf` (bu dizindeki dosya). Ana `sshd_config` drop-in dizinini içermediği için yalnız bu dosya açık `Include` ile eklendi. Değişiklikten önce `sshd -t`; etkin kısıtlar `sshd -T -C user=editor-gpu-tunnel,...` ile görülür.

Servis ikinci bir yönlendirme de açar (`127.0.0.1:18887` → GPU `8010`); o portun GPU'daki hedefi kaldırıldı, yönlendirme boştadır ve 18885'i etkilemez. Kaldırmak için servis dosyasından `-R 127.0.0.1:18887:...` ve sshd dosyasındaki `PermitListen` girdisi birlikte çıkarılır; önce `sshd -t`, sonra servis yeniden başlatılır.

Kurulum ve model ayrıntıları: [GPU sunucusu belgesi](../../../docs/TT-GPU-SUNUCUSU.md).
