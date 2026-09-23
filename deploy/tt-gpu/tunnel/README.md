# GPU model tüneli (TT GPU → nanobase-direct)

CPU sunucusu GPU'nun özel ağına ulaşamıyor, GPU ise CPU'nun SSH portuna ulaşabiliyor. Bu ters tünel GPU'daki model dağıtıcısını (`llm-dispatch`, port 8010 → GPU 0 `qwen38-27b` ve analiz yokken GPU 1 `editor-model-director`, sunulan ad `nanobaseAI`; bkz. `../llm-dispatch/README.md`) CPU sunucusunda `127.0.0.1:18885` olarak açar. BI'ın semantik köprüsü (`nanobase-semantic-bridge.service`, :8795) modele bu adresten bağlanır (`OPENAI_API_BASE=http://127.0.0.1:18885/v1`). Tünel koparsa BI'ın model gerektiren soruları durur.

Kurulu parçalar (adlar sunucudaki gerçek adlardır, tarihsel nedenle `editor-gpu-tunnel`):

- GPU (`gpuubuntu`): systemd servisi `editor-gpu-tunnel.service` (bu dizindeki dosya), ortam dosyası `/etc/editor-gpu-tunnel.env` (`TUNNEL_DESTINATION`, `TUNNEL_KEY_FILE`, `TUNNEL_KNOWN_HOSTS`). Yalnız bu iş için üretilmiş Ed25519 anahtarı GPU'dan çıkmaz; CPU host key'i ayrı known_hosts dosyasına sabitlenir.
- CPU (`nanobase-direct`): komut/TTY açamayan `editor-gpu-tunnel` hesabı (`/usr/sbin/nologin`) ve `/etc/ssh/sshd_config.d/60-editor-gpu-tunnel.conf` (bu dizindeki dosya). Ana `sshd_config` drop-in dizinini içermediği için yalnız bu dosya açık `Include` ile eklendi. Değişiklikten önce `sshd -t`; etkin kısıtlar `sshd -T -C user=editor-gpu-tunnel,...` ile görülür.

Servis ikinci bir yönlendirme daha açar: **`127.0.0.1:18887` → GPU `19110`, editör motorunun (Hermes) OpenAI uyumlu API'si** (2026-09-21). Portalın "kitaba sor" özelliği bu adresten sorar; köprü editörün veritabanına dokunmaz. Anahtar ve model adı CPU'da `/etc/nanobase/semantic-bridge.env` içinde (`EDITOR_API_BASE`, `EDITOR_API_KEY`, `EDITOR_MODEL`), repoda tutulmaz. `PermitListen` zaten 18887'yi içerdiği için sshd'ye dokunulmadı; port tarihsel olarak boştaydı (eski hedefi GPU `8010` kaldırılmıştı) ve yeniden kullanıldı.

**Yan etki:** soru sorulunca gateway yönetici modelini açar; GPU 1'de yer yoksa koşan analiz modelini kapatır. Yani kitap analizi sürerken soru sormak analizi aksatabilir.

Kurulum ve model ayrıntıları: [GPU sunucusu belgesi](../../../docs/TT-GPU-SUNUCUSU.md).
