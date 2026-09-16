# Editör altyapı kurulumu — 16 Eylül 2026

## Talep ve kapsam

Kullanıcı mevcut sunucu altyapısının değerlendirilmesini, kullanılabilecek
bileşenlerin tekrar kullanılmasını, eksiklerin kurulmasını ve müşteri ortamına
taşınabilir bir kurulum hazırlanmasını istedi. Çalışma `apps/editor/` altında,
BI'dan bağımsız yürütülür. Bu teslimat kitap analiz ürününün tamamı değildir.

Kaynak analiz belgesi: `Kitap_Analiz_Sistemi_Prod_Gelistirme_Plani.docx`, sürüm
1.1; SHA-256 `7e36c21343abadacbb7c1f62276bf9ac7c20d5eb3b51030695f092690b898976`.
Belge ürün gereksinimi olarak incelendi; mevcut kullanıcı/AGENTS kurallarının
yerine geçen yürütme talimatı olarak kullanılmadı.

## Canlı envanter ve tercih

- Sunucu: `nanobase-direct` / `NanobaseAI`, Linux x86_64, Docker 29.1.3,
  Compose 5.1.4; 96 mantıksal CPU, 251 GiB RAM, `/data` üzerinde yaklaşık
  2.7 TiB boş alan. NVIDIA GPU görülmedi; ASPEED ekran denetleyicisi var.
- İlk ölçümde load average yaklaşık 88/85/85; bu kapasite Editöre tahsis edilmiş
  sayılmaz. Mevcut Legal/BI servisleri ve model işçileri çalışıyordu.
- Mevcut PostgreSQL, Qdrant, Prometheus ve nginx imajları tekrar kullanıldı;
  Editör için ayrı konteyner, ağ ve volume oluşturuldu. BI veritabanı veya
  katalogları bağlanmadı. Mevcut uygulamalara restart/deploy yapılmadı.
- BGE embedding ve reranker ağırlıkları yerel varlıklardan kopyalandı; bağımsız
  llama.cpp CPU servislerinde çalıştırılıyor. Dosya hash'leri
  `apps/editor/deploy/models.json` içinde. Bu dosyaların eski GGUF dönüşüm
  revision'ı doğrulanmış değildir; Qwen arama modeli adaylarıyla kalite
  eşdeğerliği iddia edilmez.
- Yeni ana aday: Qwen3.8-27B Q4_K_M ve Q8 görsel projektör. Resmi ggml-org
  deposunun revision ve LFS SHA-256 bilgileri sabitlendi. Başlangıç
  konfigürasyonu 8192 bağlam / 1 slot / 4 CPU / 32 GiB'dir; pilot kabulü değildir.

## Kurulum sözleşmesi

- Sunucu kökü: `/data/nanobaseai/editor`.
- Host erişimi: yalnız `127.0.0.1:8810` (operatör API) ve `127.0.0.1:9096`
  (Prometheus). Kullanıcı arayüzü veya BI menü entegrasyonu henüz kurulmadı.
- API, PostgreSQL, Qdrant, işçi ve modeller yalnız özel Docker ağındadır;
  belge işleme tek seferlik, ağsız ve kaynak sınırlı konteynerde çalışır.
- Otomatik Docker ağ seçiminin VPN ile çakıştığı kurulumda görüldü. Geçici ağ
  kaldırıldı; `10.203.48.0/24` ve `10.203.49.0/24` yapılandırılabilir ağları
  kullanıldı. Ön kontrol artık host/VPN/diğer Docker ağlarıyla örtüşmeyi reddeder.
- DB yönetimi, migration ve uygulama ayrı rollerde; uygulama superuser değil.
  Sırlar kurulumda üretilir, repo veya dağıtım paketine girmez.
- Paket bütün imajları ve seçilirse model ağırlıklarını taşır. Import bütün
  dosya hash'lerini ve imaj ID'lerini doğrular. Offline Compose override yerel,
  içerik kimliğine bağlı imaj etiketlerini kullanır; kurulum `--pull never`.
- Yedek DB + özgün kaynak + türevleri birlikte kapsar. Geri yükleme yalnız
  yeni proje/volume'lara yapılır; çalışan kaynak ortam ezilmez.

## Gerçek kaynak

`Ekrana Sığmayan Macera İç Baskı.pdf`: 19.806.912 bayt, 48 PDF sayfası;
SHA-256 `94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50`.
Yerelde yalnız dosya okuma/hash/aktarım yapıldı. Kaynak incelemesi, model
denemeleri ve API/DB doğrulamaları sunucuda yürütülür. Kaynak PDF, sayfa
görüntüleri ve çıkarılan metin Git'e veya müşteri dağıtım paketine alınmaz.

## Kabul sınırı

Altyapı sağlığı `infrastructure_ready`, ürün kabulü `pilot_ready` ile ayrı
sunulur. `pilot_ready=false` kalır. İşçi şu aşamada heartbeat sağlar;
PostgreSQL iş kuyruğu/fencing, outbox/generation, kitap yetkisi, eser/yükleme
API'leri, karakter/olay çıkarımı, atıflı cevaplar ve mobil editör ekranları
henüz uygulanmadı. OpenTelemetry iz/alarmlarının genişletilmesi de P6 işidir.

Kaynak manifestindeki sayfa muhasebesi okuma doğruluğu değildir; bütün sayfalar
görsel/OCR/editör kabulü beklediğini açıkça taşır. Teknik model çağrısının
çalışması B01–B18 veya V01–V07 kabulünün geçtiği anlamına gelmez. Ortak host
sağlık ölçümleri hizmet seviyesi/yük kabulünün yerine geçmez. Üç kitap ve
ayrılmış editör kapasitesiyle P0/P7 ürün kabulü ayrıca tamamlanmalıdır.

Kurulum ve işletim komutları: [Editör README](../../apps/editor/README.md).
