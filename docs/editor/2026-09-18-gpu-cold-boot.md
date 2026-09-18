# GPU offline kurulum: çalışma ayarlarının korunması

18 Eylül2026. Ortam: mevcut2×H100NVL GPU sunucusu, gerçek kitap kırpımları; yerel/sentetik test kullanılmadı. Uygulama kayıtları ve inceleme kararları değiştirilmedi.

## Doğrulanan kök neden

Aynı Qwen imajı `sha256:fc120ece0a388cc0aa1caad4a9f1cd92113484ab7ec2fd0efadd62585be05bf8` ve aynı snapshot kullanıldığı halde:

| Ölçüm | Canlı servis | Hatalı paket |
|---|---|---|
| VLLM_PLE_CPU_OFFLOAD |1|Atlanmış|
| NCCL_P2P_LEVEL |SYS|Atlanmış|
| Model yükleme belleği /GPU |64,58GiB|88,42GiB|

Kanıt GPU `/data/editor-gpu-packaging/20260918/runtime-environment-diagnosis.json`; değerler gerçek docker inspect ve model yükleme loglarından çıkarıldı. Kurulu vLLM `envs.py`, GPUworker ve Qwen PLE katmanı bu ayarı kullanıyor. Paketleyici yalnız HF offline ayarlarını taşıdığı için canlı modelin CPU offload davranışı kaybolmuştu. İlk önbellek/derleme yorumu bu bulguyla düzeltildi: bellek farkının temel nedeni eksik çalışma ayarıdır.

## Korunan başarısız denemeler

- İlk eski paket: refs/main satır sonu HF offline snapshot çözümlemesini bozdu; exporter/importer düzeltildi.
- Cache-v3 gerçek boş-cache açılışı: eksik offload ile Inductor autotuning47,69GiB ek bellek isteyip OOM verdi.
- Eager-v4: derleme kapansa da model88,42GiB yükleniyor; KV cache için kullanılabilir bellek-15,45GiB, açılış başarısız. Bu aday canlı profile uygulanmadı.
- Her iki model denemesinden sonra asıl konteynerler aynı kimlikleriyle geri açıldı, gerçek Qwen/OCR eşzamanlı istekleri geçti; cleanup_errors boş. Log/başarısız paketler silinmedi.

## Genel kod düzeltmesi

`gpu/runner_environment.py` imaj varsayılanları ile çalışan konteyner ortamını karşılaştırır. HF offline politikası, PLE CPUoffload ve NCCL P2P ayarları açık allowlist/değer kontrolüyle taşınır. Bilinmeyen override değerleri kopyalanmaz veya loglanmaz; paketleyici değişken adını bildirerek durur. Böylece çalışma ayarı sessizce kaybolmaz ve sırlar pakete alınmaz.

`bundle.py` ve `reprofile-bundle.py` runtime_environment manifestini üretir. `import-bundle.py` manifest ile Compose ortamının eşliğini ve izinli değerleri, sonra bütün byte/imaj/snapshot kimliklerini doğrular. Gerçek soğuk açılış doğrulayıcısı paket manifestini ve açılan konteynerin ortamını karşılaştırır; HTTP200'e ek Docker healthcheck, dış ağın kapalı olması, salt-okunur model mount ve gerçek eşzamanlı çıkarım aranır.

Yeni paket `/data/editor-gpu-releases/source-analysis-v14-runtime-env-v5-20260918`: import, çalışma ortamı eşliği,3 imaj ve2 gerçek imajla offline HF snapshot çözümlemesi PASS; `runtime-env-v5-import.log`. Eski gerçek cache-v3 paket güncel importer ile `RUNNER_ENVIRONMENT_MANIFEST_REQUIRED` gerekçesiyle reddedildi; `runtime-env-old-package-rejection.json`.

## Son soğuk açılışın durumu

Hedef çıktı `cold-boot-v14-runtime-env-v5/`. Başlatma isteği sırasında Mac VPN/SOCKS kapandı ve SSH bağlantısı koptu; sürecin başlaması/sonucu **DOĞRULANAMADI**. Çift bakım koşusu başlatılmadı. Önceki eager-v4 denemesinin geri dönüşü bu bağlantı kaybından önce gerçek isteklerle doğrulanmıştı.

GPU→CPU doğrudan model tüneli VPN kaybından etkilenmedi: CPU üzerinden Qwenhealth ve OCRgateway200; ardından R4 yayımlanmış kodun gerçek sayfa bileşen kontrolü başlatıldı. GPU yönetim SSH bağlantısı ise MacVPN/OTP girişini gerektiriyor. Uygulama/model erişimi ile yönetim erişimi ayrı durumlardır.

Runtime-env-v5 tam soğuk açılış kabulü, farklı fiziksel müşteriGPU/RAM kapasitesi ve uzun süreli yük hedefleri henüz tamamlanmış sayılmaz. Kitabın anlamsal kabulü bu altyapı kontrollerinden çıkarılmaz.

## 18 Eylül 06:44 UTC — yönetim erişimi yeniden doğrulandı

`ssh tt-gpu hostname` gerçek sunucuda `gpuubuntu` döndürdü. Paketleme dizini salt okunur incelendi; runtime-env-v5 import kanıtı var, fakat `cold-boot-v14-runtime-env-v5` sonuç dizini yok. Önceki bağlantı kesintisinde başlatma isteği tamamlanmış kabul edilmiyor. Ana V15 kitap analizi çalıştığı için model servisleri durdurulmadı ve ikinci bakım koşusu açılmadı. Yönetim erişim engeli şu an kalkmış görünüyor; tam offline soğuk açılış kabulü hâlâ açık ve aktif işler bittikten sonra denetlenecek.
