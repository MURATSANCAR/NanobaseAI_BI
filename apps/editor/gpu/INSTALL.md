# GPU hizmetleri için offline paket

Bu paket çalışan GPU kurulumunun seçilmiş runner imajları ve hash kontrollü model snapshot'larıdır. Import başarısı yeni GPU'da model açılması veya kitap kalitesi kabulü değildir. Mevcut ölçülen profil iki GPU ile Qwen tensor parallel2 ve ikinci GPU üzerinde OCR kullanır; imajın CUDA/driver ve bellek uygunluğu hedef sunucuda ayrıca doğrulanmalıdır. Yeni model indirme veya bulut fallback yoktur.

1. Paketi Linux GPU sunucusuna taşıyın. Docker GPU erişimini ve boş portları doğrulayın. GPU hizmetlerinin ikinci kopyasını çalışan modelin yanında başlatmayın.
2. `python3 import-bundle.py .` ile bütün dosya hashlerini, imaj kimliklerini, sabitlenmiş cache referanslarını, çalışma ortamı manifestini ve Compose sözdizimini doğrulayın. Komut, her imajın kendi Hugging Face kütüphanesini tek seferlik ağsız konteynerde çalıştırıp paket içindeki snapshot'ın bulunabildiğini denetler; model sunucusu veya GPU çıkarımı başlatmaz.
3. `.env.example` dosyasını `.env` olarak kopyalayın. `GPU_BIND_ADDRESS` değerini müşteri özel model ağına göre ayarlayın; varsayılan loopback yalnız aynı sunucudan erişilir. Editör uygulamasının özel endpoint sözleşmesine göre erişimi sağlayın.
4. Önce `docker compose create --no-build --pull never ocr` ile gateway'in yöneteceği OCR konteynerini oluşturun. Ardından `docker compose up -d --no-build --pull never --wait --wait-timeout 1800 qwen gateway` çalıştırın. OCR ilk gerçek istekle açılır ve boşta kapanır.
5. Gerçek kitap kırpımı, model kimlikleri, normal idle/wake ve eşzamanlı yük kabulünü hedefte uygulayın. Qwen/OCR servisi çalışır kabul edilmeden uygulamayı üretime hazır saymayın.

Snapshot kimlikleri `model-identities.json`, dosya ve imaj hashleri `gpu-release-manifest.json` içindedir. Yalnız seçilen iki model snapshot'ı kopyalanır; Hugging Face tokenları, diğer modeller, kitaplar ve müşteri sırları paketlenmez. Model cache read-only bağlanır; türetilen çalışma cache'leri ayrı volume/tmp dizinindedir. Ağırlıklar model sağlayıcılarının kendi lisans koşullarına tabidir; snapshot içindeki lisans/README dosyaları korunur.

`refs/main` tam olarak sabitlenmiş commit kimliğini taşır; sonunda satır sonu bulunmaz. Eski paket değiştirilmeyip düzeltilmiş metadata ile yeni paket türetilir ve bütün byte'lar yeniden doğrulanır. Dosya hashlerinin tutması, model kütüphanesinin cache'i okuyabildiği veya GPU üzerinde açıldığı anlamına gelmez; bunlar ayrı kabul adımlarıdır.

`runtime_environment` manifesti zorunludur. Bu kurulumda Qwen `VLLM_PLE_CPU_OFFLOAD=1` ve `NCCL_P2P_LEVEL=SYS` kullanır; bunların atlanması aynı imaj ve ağırlıklarla farklı bellek davranışına yol açtı. Paket yalnız açıkça izin verilen, sır içermeyen çalışma ayarlarını taşır; tanınmayan bir imaj-dışı override varsa paketleme durur. CPU offload GPU sunucusunun RAM kapasitesini de kullanır; hedef donanımda gerçek açılış/çıkarım kabulü gerekir. Başarısız eski cache-v3 ve eager-v4 denemeleri müşteri kurulum kanıtı değildir.
