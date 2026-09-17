# Editör P6: GPU dağıtımı ve taşınabilirlik açıkları

18 Eylül 2026. Bu kayıt depo kodunun incelenmesidir; yeni müşteri kurulumu veya canlı kabul koşusu değildir. Önceki CPU paket/restore kabulleri yeni GPU topolojisini doğrulamaz. Bu çalışma sırasında canlı servis değiştirilmedi ve yerel test çalıştırılmadı.

## Mevcut çalıştırma yolu

Uygulama Linux CPU sunucusunda kendi Compose/PostgreSQL/veri alanında çalışır. Ana model ve ek bölgesel OCR ayrı GPU sunucusundadır. `compose.gpu.yaml`, API ve worker için ana model kök adresi/adı ile OCR gateway kök adresi/model revizyonunu ister. Adreslere `/v1` eklenmez. Bu overlay `compose.models.yaml` üzerindeki CPU `llm` servisini isteğe bağlı `cpu-llm` profiline taşır; `models` profili embedding/reranker için korunur. `!override` desteği nedeniyle Docker Compose en az 2.24.4 olmalıdır.

Mevcut kurulumun yol haritası:

| Bileşen | Mevcut yol | Müşteride karşılığı |
|---|---|---|
| Qwen | Editor Docker köprüsü `18882` → CPU loopback `18881` → Mac proxy `18081` → VPN/SOCKS → GPU `8001` | Editor konteynerlerinden erişilebilen özel ana model adresi |
| PaddleOCR-VL | Docker köprüsü `18884` → CPU loopback `18883` → Mac proxy `18083` → VPN/SOCKS → GPU gateway `8010` | Özel, istekle açılan OCR gateway adresi |
| OCR yaşam döngüsü | `/gateway/status` pasif; işlem isteği uyandırır; 600 saniye boşta kapanır | Müşteri GPU kaynaklarıyla açılma/kapanma/yeniden açılma kabulü |
| Embedding/reranker | CPU Compose `models` profili, yerel GGUF dosyaları | İmaj ve checksum doğrulanmış ağırlıkların offline temini |

Bu ağ bilgileri [18 Eylül entegrasyon kaydına](2026-09-18-qwen-ocr-parallel.md) ve [OCR hazırlık kaydına](2026-09-18-paddleocr-vl-readiness.md) dayanır; burada yeniden canlı ölçülmedi. Mac, VPN ve ters SSH kesilirse model erişimi kesilir. Mac yolu mevcut geliştirme kurulumu için kullanılabilir; müşteriye bağımsız sunucu kurulumu olarak sunulamaz. Depodaki `deploy/gpu-tunnel-proxy.conf` açıkça bu kuruluma ait bridge IP/allowlist içerir; müşteride ağ/subnet ve erişim kuralı yeniden belirlenmelidir.

Mevcut kaynak kurulumu `.env` üzerinde `compose.yaml:compose.models.yaml:compose.ocr.yaml:compose.reread.yaml:compose.gpu.yaml` ve `COMPOSE_PROFILES=models` seçer. Ana model ve OCR adresleri ile OCR revizyonu açıkça verilmelidir. API/worker/web/document/OCR imajları doğrulanan yayınla eşleştirilir. `scripts/install.sh`, önce init/preflight, sonra `--no-build --pull never` ile başlatma ve verify çalıştırır. Bu komut eksik GPU servislerini/ağırlıklarını kurmaz. Çalışan kuruluma bu belge nedeniyle yeniden install uygulanmaz.

## Kodla doğrulanan açıklıklar ve bu değişiklik

1. **Offline paket aktif GPU topolojisini taşımıyordu.** `scripts/bundle.py`, Compose yapılandırmasını yalnız base/models/OCR/reread dosyalarıyla yeniden oluşturuyor; `compose.gpu.yaml`, harici GPU ağırlıkları ve istekle açılan gateway hizmeti pakete eklenmiyor. `--with-ocr-vl` yerel deney servisini seçer; GPU gateway paketleme desteği değildir. Aktif GPU ortamında açık `--external-models` seçimi gerekir; seçilmezse yanlış CPU paketi oluşturulmaz. Yeni external mode uygulama imajlarını ve checksum kontrollü yerel embedding/reranker ağırlıklarını paketler; Qwen/OCR GPU imajları ve ağırlıkları harici bağımlılık olarak manifestte açıkça belirtilir. **GPU servislerinin kendi offline paketi henüz uygulanmadı.**
2. **Preflight GPU kurulumunda eski CPU modeli gerektiriyordu.** `scripts/preflight.py`, yalnız `COMPOSE_PROFILES=models` üzerinden eski Qwen27B/mmproj dosyaları ve 48 GiB boş RAM istiyordu. GPU overlay aynı profili embedding/reranker için kullanır. Kontrol artık çözümlenen etkin `llm` servisi varsa CPU RAM sınırını uygular; etkin llm/embedding/reranker komutlarındaki `--model` ve `--mmproj` yollarını gerçek bind mount üzerinden doğrular. Genel temel 8 GiB kontrolü korunur. GPU model belleği/yük kapasitesi bu kontrolle doğrulanmış sayılmaz.
3. **GPU sunucusunun tam dağıtım tanımı depoda yok.** `deploy/paddleocr-vl-memory.override.yaml` yalnız harici GPU ana Compose üzerine override'dır; tam gateway/model kurulumu değildir. Yüzde4 bellek rezervasyonu bu paylaşılan H100 ölçümüne aittir, başka GPU için garanti değildir. Gateway kaynak kodu, sürümü, temel Compose, model revizyon/checksum ve offline ağırlık tedariki tek sürümlü dağıtım manifestinde tamamlanmalıdır.
4. **Güncel ayrı kurulum/restore kanıtı yok.** `scripts/qualify-completed-installation.py` hâlen CPU `bundle.py --with-models` yolunu kullanır. Bu eski komut açık external mode seçmediği için GPU ortamında durur. External mode ile üretilen uygulama paketi müşteri adresleri yapılandırıldıktan sonra ayrı kuruluma alınabilir; otomatik restore kabul scriptinin GPU sözleşmesiyle güncellenmesi ve koşulması henüz açık. Bu eksikliği saklamak için model backend/profilini değiştirip kabul üretilmez.
5. **Örnek env güncel GPU kurulum reçetesi değil.** `.env.example` eski CPU yayın etiketleri içerir; GPU adres/revizyon seçimi otomatik gelmez. External mode paketin env şablonuna GPU overlaylerini, yerel model profilini, doğrulanacak model isim/revizyonlarını ve boş müşteri endpoint alanlarını ekler. `compose.external-models.yaml`, API/worker için özel ağdan çıkış sağlar; Mac relay zorunlu değildir. GPU için müşteri özel bağlantısı ve GPU imaj/ağırlık manifesti ayrıca sağlanmalıdır. Sır/adresler mevcut canlı `.env` dosyasından paket içine kopyalanmaz.

## Kapatma için gereken gerçek kabul

- Mac olmadan hedef Linux/Docker ağından ana model ve pasif OCR status erişimi; model kimliği/revizyon doğrulaması.
- İnternetsiz hedefte bütün uygulama, GPU runner ve gateway imajları ile ağırlıkların checksum kontrollü importu; eksik dosyada açık başarısızlık.
- Gerçek kitap/API/PostgreSQL kaydı üzerinden kaynak okuma ve Qwen/OCR eşzamanlı yükü; kaynak metin ve inceleme kararlarına elle müdahale edilmez.
- OCR boşta kapanma, talep ile yeniden açılma, model meşgul/bellek yetersizliği ve bağlantı kopması davranışları; yinelenen ağır koşu başlatılmaz.
- Aynı yayın sürümünde ayrı kurulum/yedek/restore ve API–PG bağımsız eşliği, 320/390/768/1440 px kullanıcı akışı.

Bu script ve Compose düzeltmeleri yalnız statik olarak incelendi; gerçek hedefte external paket/import/preflight **DOĞRULANAMADI**. P6 açık; bu belge üretime hazır kararı değildir.


## Müşteri endpointleriyle uygulama paketi

Kaynak Linux paketleme sunucusunda aktif model isim/revizyonları ve yayın imajları ayarlandıktan sonra:

```sh
python3 scripts/bundle.py /kurum/yayin/editor-release --external-models
```

Bu mod `--with-models` veya `--with-ocr-vl` ile birlikte kullanılamaz. Qwen CPU27B/mmproj dosyaları taşınmaz; embedding/reranker taşınır. `release-manifest.json` içindeki `external_dependencies`, checksum kapsamındaki `editor/deploy/external-models.json` ile import sırasında karşılaştırılır. Paket, canlı müşteri endpointlerini veya sırlarını kopyalamaz.

Hedef Linux üzerinde paket imajları `scripts/import-bundle.py` ile yüklenir; ardından `scripts/init.py` çalıştırılır. Oluşan `.env` dosyasında `EDITOR_MODEL_BASE_URL` ve `EDITOR_OCR_VL_BASE_URL` müşterinin özel root adresleriyle doldurulur. `EDITOR_MODEL_NAME`, `EDITOR_OCR_VL_MODEL`, `EDITOR_OCR_VL_REVISION` gerçek servislerle eşleşmelidir. `EDITOR_MODEL_CONTEXT` hizmetin kapasitesini aşmamalıdır. URL içine kullanıcı/parola veya `/v1` konmaz; endpointler mevcut istemcinin kimlik doğrulamasız özel ağ sözleşmesini sağlamalıdır. Public internet servisi ya da bulut fallback kurulum reçetesi değildir.

`compose.external-models.yaml` ile API/worker mevcut ingress ağına da bağlanır; bu yalnız dışarıya model isteği için kullanılır, API/worker host portu açılmaz. Müşteri güvenlik duvarı model adresleri/portlarına erişimi sınırlandırmalıdır. Ana Compose private veri ağı ve veri servislerinin izolasyonu korunur. Eski Mac bridge relay özel adresleri zorunlu değildir.

Preflight URL biçimi, loopback hatası ve API/worker model sözleşmesi eşliğini denetler; endpoint erişimi veya çıkarım başarısını kanıtlamaz. Import yalnız uygulama paket bütünlüğünü doğrular; GPU servislerini kurmaz, ağırlık indirmez, otomatik modele çağrı yapmaz. Gerçek kitap ve idle/wake kabulü tamamlanmadan P6 kapatılmaz.
