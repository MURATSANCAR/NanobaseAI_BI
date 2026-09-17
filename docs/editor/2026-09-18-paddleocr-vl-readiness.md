# PaddleOCR-VL-1.6 canlı hazırlık kontrolü — 18 Eylül 2026

Kullanıcı GPU kurulumunun diğer oturumda tamamlandığını bildirdi. Bu oturum mevcut kurulumu salt okunur inceledi; GPU Compose, bellek ayarları ve Qwen servisi değiştirilmedi.

- GPU: `tt-gpu`; gateway `8010`, model `PaddlePaddle/PaddleOCR-VL-1.6`, servis adı `paddleocr-vl-1.6`, vLLM 0.27.1.
- Gateway talep gelince modeli başlatır, 600 saniye boş kalınca durdurur. Uyandırmadan durum kontrolü: `/gateway/status`. `/health` modeli uyandırır; yalnız pasif izleme için kullanılmamalıdır.
- Canlı `/gateway/status`: `running=true`, `healthy=false`; gerçek `/health` isteği HTTP 503 döndü. Sonraki açılış da `Engine core initialization failed` ile sonuçlandı.
- 17 Eylül 22:03:55 UTC logunda kesin hata: CUDA cihazında 4.0/93.09 GiB boş; `gpu_memory_utilization=0.05` için gereken 4.65 GiB sağlanamıyor. Ölçülen GPU boş bellekleri 4247 ve 4623 MiB. Konteynerin running olması modelin hazır olduğu anlamına gelmez.
- Sonuç: **DOĞRULANAMADI**. Gerçek kitap OCR çağrısı ve Editör API/PostgreSQL kabulü yapılmadı; yeni model üretim OCR akışına bağlanmadı. Kitap verileri değiştirilmedi.

Sonraki adım: kurulumu yöneten oturumda Qwen ile OCR için birlikte çalışabilir GPU bellek bütçesi oluşturulmalı; yalnız OCR sınırını azaltmanın yeterli olduğu varsayılmamalı. Sağlık ve gerçek kırpım çıkarımı birlikte geçtikten sonra Editöre ayrı OCR sağlayıcısı olarak bağlanmalı. Ham cevap, kaynak/kırpım hashleri ve bbox korunmalı; yeni OCR cevabı tek başına mevcut çelişki kapılarını aşmamalı.

## Sonraki canlı düzeltme — 18 Eylül 01:16 TRT

Kullanıcının başlatma talebiyle istekle açılma tekrar denendi; aynı bellek hatası ve exit1/HTTP503 yeniden görüldü. Bu kapanma boşta otomatik durdurma değildi. GPU Compose yedeği `/data/paddleocr-vl/docker-compose.before-memory-fix.yml` alındı; yalnız OCR `gpu_memory_utilization` 0.05 → 0.04 değiştirildi ve OCR yeniden oluşturuldu. Qwen ve gateway ayarları değiştirilmedi. Depodaki karşılığı `apps/editor/deploy/paddleocr-vl-memory.override.yaml`; GPU ana Compose ile kullanılacak komut override'ıdır.

Model yüklemesi 1.82 GiB bildirdi; gateway `running=true, healthy=true`, `/v1/models` HTTP200 ve model `paddleocr-vl-1.6` doğrulandı. 600 saniyelik otomatik boşta kapanma korunuyor. **Açılış/servis erişimi geçti; gerçek OCR çıkarımı, otomatik kapanma sonrası yeniden uyanma ve Editör API/PG kabulü bu sonuçla doğrulanmış sayılmaz.**
