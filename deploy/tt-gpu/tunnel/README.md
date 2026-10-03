# GPU model tüneli (TT GPU → nanobase-direct)

CPU sunucusu GPU'nun özel ağına ulaşamıyor, GPU ise CPU'nun SSH portuna ulaşabiliyor. Bu ters tünel GPU'daki model dağıtıcısını (`llm-dispatch`, port 8010 → GPU 0 `qwen38-27b` ve analiz yokken GPU 1 `editor-model-director`, sunulan ad `nanobaseAI`; bkz. `../llm-dispatch/README.md`) CPU sunucusunda `127.0.0.1:18885` olarak açar. BI'ın semantik köprüsü (`nanobase-semantic-bridge.service`, :8795) modele bu adresten bağlanır (`OPENAI_API_BASE=http://127.0.0.1:18885/v1`). Tünel koparsa BI'ın model gerektiren soruları durur.

Kurulu parçalar (adlar sunucudaki gerçek adlardır, tarihsel nedenle `editor-gpu-tunnel`):

- GPU (`gpuubuntu`): systemd servisi `editor-gpu-tunnel.service` (bu dizindeki dosya), ortam dosyası `/etc/editor-gpu-tunnel.env` (`TUNNEL_DESTINATION`, `TUNNEL_KEY_FILE`, `TUNNEL_KNOWN_HOSTS`). Yalnız bu iş için üretilmiş Ed25519 anahtarı GPU'dan çıkmaz; CPU host key'i ayrı known_hosts dosyasına sabitlenir.
- CPU (`nanobase-direct`): komut/TTY açamayan `editor-gpu-tunnel` hesabı (`/usr/sbin/nologin`) ve `/etc/ssh/sshd_config.d/60-editor-gpu-tunnel.conf` (bu dizindeki dosya). Ana `sshd_config` drop-in dizinini içermediği için yalnız bu dosya açık `Include` ile eklendi. Değişiklikten önce `sshd -t`; etkin kısıtlar `sshd -T -C user=editor-gpu-tunnel,...` ile görülür.

Portalın "kitaba sor" özelliği kart servisinin tünelinden (`editor-cards-tunnel.service`, `EDITOR_CATALOG_BASE`) `POST /v1/books/ask` ile sorar. 2026-10-03'e kadar bu servis `127.0.0.1:18887` → GPU `19110` (sohbet ajanının API'si) yönlendirmesini de açıyordu; ajan kaldırıldı, yönlendirme de kaldırıldı. `PermitListen`'deki 18887 boş kalır.

Kurulum ve model ayrıntıları: [GPU sunucusu belgesi](../../../docs/TT-GPU-SUNUCUSU.md).
