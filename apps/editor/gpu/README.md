# GPU OCR gateway

`gateway.py` mevcut GPU sunucusunun gateway uygulamasından sürümlenmiştir. Ana model/kitap metni üretmez. `/gateway/status` pasiftir; diğer isteklerde mevcut OCR konteynerini gerektiğinde açar, boşta kapatır.

V2 adayında kapanma kararı ile yeni istek kabulü aynı kilitle korunur. Önceki kod boşta durumunu kilit dışında kullanarak yeni başlayan çıkarım sırasında modeli durdurabiliyordu. Monotonic süre, 32 MiB gövde sınırı, bozuk/eksik gövde reddi ve upstream bağlantı hatasında 502 eklendi. Bu dosyanın bulunması canlı yaşam döngüsü kabulü değildir.

`Dockerfile.gateway` mevcut Python imajını digest ile sabitler; ek paket indirmez. Docker socket erişimi hedef konteyneri yönetmek içindir. Gateway yalnız müşteri özel model ağında yayımlanmalıdır. `TARGET`, `UP_HOST`, `UP_PORT`, `IDLE_SECONDS`, `START_TIMEOUT`, `STOP_GRACE`, `MAX_BODY_BYTES` ortamla ayarlanır. Varsayılan hedef `paddleocr-vl`, upstream 8000, boşta süre 600 saniyedir.

Gerçek GPU sunucusunda ayrı aday konteyner, kitabın hash doğrulanmış 28. sayfa kırpımıyla HTTP200/finish_reason=stop verdi (0,168 sn; bu GPU host içi ölçümdür, Mac tünel gecikmesini içermez). Geçersiz uzunluk400, negatif/aşırı gövde413 döndü; hatalı istekler modeli uyandırmadı. Kanıt GPU hostta `/data/paddleocr-vl/candidates/editor-gateway-v2/real-crop-acceptance.json`. Kitap kaydı yazımı0. Aday konteyner ölçümden sonra durduruldu. Kapanma/istek yarışının canlı sınır koşusu henüz doğrulanmadı; ana gateway bu not yazılırken değiştirilmedi.

`compose.gateway-v2.yaml` mevcut GPU OCR Compose üzerine uygulanacak yayın override'ıdır; yalnız gateway imajını seçer ve eski bind mount yerine imaj içindeki sürümlü kodu kullanır. OCR modelini yeniden yaratmak gerekmez. Bu bir tam GPU kurulum dosyası değildir.

Qwen/OCR runner imajları ve ağırlıkları bu dizinde henüz paketlenmemiştir. Uygulama offline paketi bu GPU bağımlılıklarının yerine geçmez; tam GPU offline kurulum kabulü açık kalır.
