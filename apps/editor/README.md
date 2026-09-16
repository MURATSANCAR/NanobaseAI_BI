# Editör modülü — bağımsız kurulum

Bu modül ana BI deposunda geliştirilir; kendi Docker projesi, PostgreSQL kayıtları,
Qdrant indeksi, kaynak alanı ve yayın paketi vardır. BI'ın Python kodunu, tablolarını,
Docker ağlarını veya kimlik bilgilerini kullanmaz. BI ekran entegrasyonu sonraki
aşamada tanımlı API sözleşmeleriyle yapılacaktır.

## Bu teslimatın kapsamı

Analiz belgesinin P0 altyapısı: FastAPI, PostgreSQL/Alembic, PostgreSQL LangGraph
checkpointer, bağımsız Qdrant, gözetilen işçi süreci, Prometheus, ağsız
Docling/Poppler/Tesseract Türkçe araçları, kaynak inceleme komutu, offline kurulum
paketi ve yedek/ayrı ortama geri yükleme betikleri.

**Kitap analiz ürünü henüz pilot kabulünde değildir.** Operatör API'sine eser,
baskı, gerçek dosya yükleme, hash ile kaynak sürümü, analiz ve soru işleri,
sayfalanan kaynak/karakter/olay/görsel/inceleme uçları eklendi. İşçi PostgreSQL
kuyruğunu lease/fencing ile tüketir; LangGraph checkpoint ve değişmez adım
kayıtlarıyla devam eder. Yerel görsel okuma → kaynaklı sahne adayları → destek
kontrolü → sınırlı kitap sentezi → Qdrant/dense + yerel BM25/reranker hattı
gerçek referans kitapta çalıştırılmaktadır. **Kodun bulunması, tüm aşamaların
tamamlanıp anlamsal kabulden geçtiği anlamına gelmez.**

Bağımsız sayfa/sahne/destek grupları `EDITOR_MODEL_CONCURRENCY` ile 1–4
eşzamanlı çağrıya sınırlandırılır. Varsayılan müşteri profili tek çağrıdır.
Sunucuda ölçülen boş kapasite ve kullanıcının CPU artırma izniyle mevcut kitap
koşusu 48 CPU/48 thread, 4 model slotu ve toplam 32768 bağlam token'ı kullanır
(slot başına 8192). Model PID sınırı 512'dir: 128 sınırında 32 thread'li gerçek
başlatma `libgomp: Thread creation failed` hatası verdi. Her grubun sonucu aynı
lease/fencing altında değişmez kayda alınır; tamamlanan kayıtlar yeniden
işlenmez. Ortak host sağlık gözlemi, tam hizmet seviyesi kabulü değildir.

Kitaba özel anlamsal ölçütler ve açık kontroller:
[referans kitap kabul kayıtları](../../docs/editor/reference-book-acceptance.md).

Bu koşu tek kurulum operatörü içindir; çok kullanıcılı kitap/rol yetkisi ve düzeltme
bağımlılıklarının yeniden hesaplanması tamamlanmadı. `/editor/` altında gerçek
API'ye bağlı salt okunur React inceleme ekranı vardır; kaynak, ham model adayları
ve mevcut analiz/soru kayıtlarını gösterir. Mobil kontrol ve derleme ayrıntıları
[frontend/README.md](frontend/README.md) içindedir. Editör karar/düzeltme arayüzü
ve PDF.js bölge incelemesi bu ekranın tamamlanmış özellikleri değildir.
Yükleme tamamlama, mevcut ağsız parser ile doğrulanmış hash'i kabul eder;
yeni, henüz ayrıştırılmamış PDF `SOURCE_PARSE_REQUIRED` döndürür.
Kaynakların modelle okunması insan editör kabulü değildir. İncelenmeyen nesil
etkinleştirilmez; `editor_preview` cevapları açıkça taslaktır, `pilot_ready=false`.
İlk offline müşteri paketi bu yeni analiz kodundan önceki altyapı sürümüdür.

Güncel kabul nesli `6fffd7ed-f0c6-4de5-af1b-1ebea8898c8b` yalnız yerel model
çıktılarıyla çalışır. Codex kaynak açıklamaları veya önceki manuel ret kararları
model girdisine verilmez; karşılaştırmalar ayrı raporda tutulur. İz:
`evidence/reference-follow-unassisted.log`. Embedding ve reranker CPU/thread
sınırları ayrı ortam değişkenleriyle ayarlanır; müşteri varsayılanı 1, mevcut
ölçüm sunucusunda her biri 4'tür. Soru koşusunda dört geçici işçi kullanılıp
13 soru terminal duruma gelince bir işçiye dönülür; bu tam öncelikli kuyruk
veya çok kullanıcılı kapasite kabulü değildir.

## Ön yüz olmadan gerçek kitap koşusu

Önce ağsız `document` konteynerinde `python -m editor.source_regions
/data/artifacts/<sha256>` çalıştırılır (Compose `--entrypoint python` kullanır).
Bu geçiş `ocr-regions-v2` altında 2400px sayfa render'ı, ham Tesseract TSV ve
kelime/bbox JSON kayıtları oluşturur; özgün PDF ve ilk Docling çıktısı korunur.
Sayfalar arası Docling paragrafı bir sayfanın özgün alıntısı gibi kullanılamaz.

Sunucuda `python3 scripts/process-reference.py` eser/baskı ve mevcut gerçek
kaynağa bağlı analiz işini aynı idempotency anahtarlarıyla oluşturur. Ardından
`python3 scripts/verify-book-api.py` özgün 19,8 MB PDF'yi yükleme API'sinden
geçirir, aynı içerik sürümünü doğrular ve tam API kayıtlarını bağımsız PostgreSQL
sorgusuyla karşılaştırır. Yerelde ürün testi çalıştırılmaz.

`python3 scripts/follow-reference.py` tek seferlik uzun koşuyu izler; analiz
tamamlanınca 13 kaynaklı kabul sorusunu kuyruğa alır. Sonuçlar
`runtime/book-analysis/<generation_id>/` altında saklanır. Bunlar Git veya
müşteri yazılım paketine alınmaz. `completion.json` oluşmadan işleme tamamlandı
denmez; `run-error.json` başarısız aşamayı gösterir. Bu dosyalar editör onayı veya
bağımsız semantik kabul yerine geçmez.

## Sunucuya ilk kurulum

Hedef: Linux x86_64, Docker Engine ve Compose v2+ (`--wait` destekli), Python 3,
`ip` komutu. Kurulumu hedef sunucuda çalıştırın. Mac'te ürün testi yapılmaz.

1. Sürüm paketini kurulum dizinine kopyalayın.
2. Paket kökünde `python3 editor/scripts/import-bundle.py .` çalıştırın: bütün
   dosya hash'leri kontrol edilir, Docker imajları yerelden içeri alınır.
3. `cd editor && python3 scripts/init.py` çalıştırın.
4. `.env` içindeki proje adı, portlar ve iki ağ aralığını müşteri ortamına göre
   düzenleyin. Varsayılan erişim `127.0.0.1:8810`, Prometheus `127.0.0.1:9096`.
5. `sh scripts/install.sh` çalıştırın. İmaj indirme/derleme yapılmaz; ön kontrol,
   migration, servis sağlığı ve gerçek API–PostgreSQL karşılaştırması yapılır.

`scripts/init.py` tekrar çalıştırılabilir; mevcut sırları değiştirmez.
`secrets/` yalnız kurulum sahibine açıktır ve Git/paket kapsamı dışındadır.
DB yöneticisi, migration sahibi ve uygulama farklı PostgreSQL rolleridir;
uygulama superuser değildir. Operatör token'ı `secrets/api_token` dosyasındadır;
çıktılara, tarayıcı URL'sine veya kaynak koda yazılmaz.

Ön kontrol RAM, boş disk, portlar, platform, Compose sözleşmesi ve VPN/host/Docker
ağ çakışmalarını denetler. Müşterinin henüz bağlanmamış VPN ağları ayrıca
kurulumda değerlendirilmelidir. Aynı hostta ikinci kurulum için hem proje adı
hem portlar hem de `EDITOR_PRIVATE_SUBNET`/`EDITOR_INGRESS_SUBNET` değiştirilir.

## Yerel model servisleri

`compose.models.yaml`, sabit digest'li resmi llama.cpp CPU imajıyla üç bağımsız
servis sağlar: Qwen3.8-27B Q4_K_M + Q8 görsel projektör, bge-m3 Q8 embedding,
bge-reranker-v2-m3 Q8 reranker. Model dosyaları `runtime/models/` altındadır;
hash/revision kaydı `deploy/models.json` ve sürüm manifestindedir. BGE dosyaları
sunucudaki mevcut ağırlıkların tekrar kullanımıdır; Qwen embedding/reranker
adaylarına karşı anlamsal kalite eşdeğerliği gösterilmiş değildir.

Model içeren offline paketin `.env.example` dosyası gerekli Compose dosyalarını
ve profili zaten seçer; `compose.offline.yaml` seçimini kaldırmayın. Kaynak
depodan geliştirme sunucusu kurulumunda `.env` dosyasına ekleyin:

```dotenv
COMPOSE_FILE=compose.yaml:compose.models.yaml
COMPOSE_PROFILES=models
```

Model servisleri internete ve host portlarına açılmaz. İç adresler
`http://llm:8080`, `http://embedding:8080`, `http://reranker:8080` biçimindedir.
Qwen için 4 CPU/32 GiB, embedding ve reranker için ayrı ayrı 1 CPU/2 GiB üst
sınır vardır. Başlangıç CPU denemesinde görsel başına `EDITOR_IMAGE_MAX_TOKENS=256`
uygulanır; tam çözünürlükteki özgün kaynak korunur. Küçük yazı/balon okuma kalitesi
bu bütçeyle kabul edilmiş değildir. Bu sınırlar ölçülmüş hizmet seviyesi veya performans garantisi
değildir. Pilot kitapları ve ortak host yükü kabul edilmeden analize otomatik
iş kabulü açılmaz. GPU yolu bu sürümde kurulmamıştır.

## Gerçek kaynak incelemesi

Bu komut bütün PDF sayfalarının metin katmanını ve görünür render'ını kaydeder;
isteğe bağlı Docling+Türkçe OCR çıkarımı yapar. Kaynak dosyayı değiştirmez.

```sh
python3 scripts/probe-source.py /mutlak/yol/kitap.pdf --timeout 1200
```

Dosya/boyut tavanları `.env` içindedir; 50 MiB/100 sayfa geçici altyapı sınırıdır,
ölçülmüş pilot kapsamı değildir. Aynı hash'in artifact dizini üzerine yazılmaz.
Başarısız denemenin yarım manifesti korunur; tamamlanmamış manifest DB'ye alınmaz.
Sayfalar görsel/OCR/editör kabulü yapılana kadar `NEEDS_REVIEW` olarak kalır.
PDF sıra numarası basılı sayfa etiketi yerine kullanılmaz.

## API ve izleme

- `GET /health/live`: süreç canlılığı.
- `GET /health/ready`: PostgreSQL, checkpoint şeması, işçi, Qdrant ve kaynak alanı.
- `GET /v1/system`: operatör token'ıyla altyapı durumu ve kaynak denemesi özeti.
- `GET /v1/source-probes/{sha256}`: operatör token'ıyla gerçek kaynak manifesti.
- `GET /v1/model-services`: yerel modellerin süreç sağlığı; anlamsal kabulden ayrıdır.
- `GET /metrics`: token korumalı Prometheus ölçümleri; bağımsız Prometheus toplar.

Hazır olma kontrolü model kalitesi veya pilot kabulü değildir. Uygulama ve model
servisleri yalnız `internal` Docker ağındadır; belge ayrıştırıcısı ayrıca
`network_mode: none` ile çalışır. Yalnız nginx geçidi giriş ağına da bağlıdır.
Müşteri erişiminde kurumun TLS reverse proxy'si ve kimlik yönetimi kurulmalıdır;
bu operatör API'si doğrudan internete yayımlanmaz. BI portal bağlantısı bu
altyapı teslimatında değiştirilmez.

## Yedekleme, geri yükleme, sürüm paketi

```sh
python3 scripts/backup.py /yedekler/editor-YYYYMMDD-HHMM
```

Yedek API/işçiyi kısa süre durdurur, PostgreSQL ve artifact'ları birlikte alır,
hash manifestini yazar ve servisleri tekrar başlatır. Model dosyaları sürüm
paketinden sağlanır. Sırlar ayrı güvenli kurum yedeğinde tutulmalıdır. Başarılı
yedek varlığı tek başına geri yükleme kanıtı değildir.

Geri yükleme için **yeni dizin**, farklı proje/port/ağlar ve `scripts/init.py`
ile yeni sırlar hazırlayın. Hedefte önceden konteyner/volume bulunamaz:

```sh
python3 scripts/preflight.py
python3 scripts/restore.py /yedekler/editor-YYYYMMDD-HHMM editor-restore
```

Betik mevcut kurulumu ezmez; DB/özgün kaynak/render hash'leri ve gerçek API
cevabı yeniden doğrulanır. Qdrant bu evrede boş ve yeniden üretilebilir altyapıdır;
P4 indeks hattı kurulduğunda indeks yeniden üretme ve generation/atıf geri
yükleme kabulü eklenmeden tam ürün restore'ı kabul edilmez. Tek host/tek DB
topolojisi yüksek erişilebilirlik sağlamaz; RPO/RTO henüz taahhüt edilmemiştir.

Paketleme yalnız internet erişimli hazırlık sunucusunda yapılır:

```sh
docker compose build api
docker compose --profile tools build document
python3 scripts/prepare-models.py
python3 scripts/bundle.py /dagitim/editor-YYYYMMDD --with-models
```

Model indirme yalnız açık paketleme adımıdır; müşteri açılışında çalışmaz.
Paket imajları, yazılımı, OCR verisini, Docling modellerini ve seçilirse LLM/VLM
ağırlıklarını içerir. Kaynak kitaplar, müşteri verisi ve sırlar pakete girmez.
Dağıtımın değişmez kimlikleri `release-manifest.json` içindeki imaj ID'leri ve
SHA-256 değerleridir. Runtime kodu bind mount edilmez.
Paketin ürettiği `compose.offline.yaml` bütün servisleri içerik kimliğinden
türetilmiş yerel imaj etiketlerine bağlar. Böylece `docker load` sonrasında
registry digest bilgisinin korunmasına veya müşterinin registry erişimine
bağımlı kalınmaz; import imaj ID'lerini ayrıca karşılaştırır.

## Teknik dayanaklar

- [Docker Compose üretim kullanımı](https://docs.docker.com/compose/how-tos/production/)
- [Docling offline model hazırlığı](https://docling-project.github.io/docling/usage/advanced_options/)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Qwen3.8 GGUF ve görsel projektör](https://huggingface.co/ggml-org/Qwen3.8-27B-GGUF)

Kaynak plan: kullanıcının sağladığı `Kitap_Analiz_Sistemi_Prod_Gelistirme_Plani.docx`,
sürüm 1.1, 16 Eylül 2026. Belgedeki yaklaşık iki haftalık doğrulama ufku teslim
garantisi değildir; üretim kabulü P0–P7 kanıtlarına bağlıdır.
