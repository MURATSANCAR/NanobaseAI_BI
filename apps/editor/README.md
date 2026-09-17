# Editör modülü — bağımsız kurulum

Bu modül ana BI deposunda geliştirilir; kendi Docker projesi, PostgreSQL kayıtları,
Qdrant indeksi, kaynak alanı ve yayın paketi vardır. BI'ın Python kodunu, tablolarını,
Docker ağlarını veya kimlik bilgilerini kullanmaz. BI ekran entegrasyonu sonraki
aşamada tanımlı API sözleşmeleriyle yapılacaktır.

## Kaynak inceleme API — 17 Eylül ek yayını

`GET /v1/generations/{generation}/source-review?pdf_page=29`, kayıtlı bölge uyuşmazlıklarını ve balon kuyruğunun sayfa koordinatındaki figür adaylarını döndürür. Yeni okuma veya kabul kararı yazmaz. Gerçek API/PG kontrolü 48/48 sayfada geçti; 371 bölge hâlâ incelemededir. [Kod değişikliği, sürüm ve kanıtlar](../../docs/editor/2026-09-17-source-review.md). Önceki v2 offline restore kabulü aşağıdaki kitap işleme sürümüne aittir; bu ek API imajının restore kontrolü henüz yoktur.

## Güncel teslimat ve doğrulama — 17 Eylül 2026

48/48 sayfa işlendi; 1.149 kaynak bölgesinin 778’inde okuyucular anlaştı, 371 bölge incelemede. İş `COMPLETED`, nesil `NEEDS_REVIEW`; anlamsal kabul verilmedi. Gerçek API/PG eşliği, offline paket, ayrı kuruluma yedekten dönüş ve restore sonrası dört genişlikte mobil kontrol geçti.

Canlı nesil `a9471749-7447-4826-b003-f25e53943763`, iş `0d53b03d-67e5-44c4-b523-bf9a2aa56ac2`, sürüm `source-spans-v2-6f14bb9`. Kaynak, okuma, yerleşim, görsel gözlem, iddia adayı ve sayfa kontrolü ayrı kaydedilir. OCR/PDF kelime eşleştirmesi ve kesintisiz alıntı kapısı uygulanır. Konuşmacı UNKNOWN kalır; adaylar senteze açılmaz.

FastAPI, PostgreSQL/Alembic, LangGraph checkpoint, Qdrant, lease/fencing kullanan işçi, ana Compose OCR servisi, yerel modeller, Prometheus, ağsız belge araçları ve salt okunur React ekranı kuruldu. BI entegrasyonu API üzerinden sonraki aşamadır. LLM son koşuda 48 CPU/thread, tek slot, 8192 bağlam, 1024 görsel token ve PID sınırı 512 kullanır; embedding/reranker dörder CPU kullanır.

Sentez/indeks/soru kodunun bulunması v2 neslin bu aşamalardan geçtiği anlamına gelmez. `pilot_ready=false`; çok kullanıcılı kitap/rol, editör düzeltme bağımlılıkları, PDF.js/bbox incelemesi ve genel yeni PDF ayrıştırma akışı açık. Henüz ayrıştırılmamış kaynak `SOURCE_PARSE_REQUIRED` döndürür. Kitap metni/cevabı/review elle düzeltilmez; genel kod düzeltmesi sonrası yeni nesil doğrulanır.

[Ayrıntılı yapılan işler, sürüm hashleri, kanıtlar ve açık işler](../../docs/editor/2026-09-17-status-and-handoff.md). [Kitap kabul defteri](../../docs/editor/reference-book-acceptance.md). [Mobil ekran](frontend/README.md).

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

## Konumlu kaynak ve sayfa kontrolü

Yeni analizlerin varsayılanı `source-spans-v2` akışıdır. PaddleOCR artık ana `compose.yaml` servisidir; model ağırlıkları imajda, çalışma ağı özeldir. `compose.ocr.yaml` eski komutlar için boş uyumluluk dosyasıdır. Offline paket OCR imajını varsayılan olarak içerir.

Her sayfada yerel PDF kelime kutuları, PaddleOCR bölgesel okuması ve Tesseract karşılaştırması `source_spans` kayıtlarına yazılır. Bozuk PDF karakterleri doğrulayıcı sayılmaz. Uyuşmazlık incelemeye ayrılır. `layout_regions`, balon/kuyruk geometri adaylarını; `visual_observations` kırpılmış çizim gözlemlerini saklar. Serbest görsel betimlemeler iddia kaynağı değildir. Konuşmacı kimliği henüz güvenilir biçimde çözülmediği için UNKNOWN kalır.

İş sırası her sayfa için kaynak → bölgesel gözlem → metne bağlı aday → kontrol, sonra sonraki sayfadır. `page_checks` kayıtları optik işlem tamamlanmasını gösterir; anlamsal kabul değildir. Doğrulanmamış adaylar senteze/olay tablosuna aktarılmaz. Mevcut sürüm sonunda nesil `NEEDS_REVIEW` olur; kitap sentezi, indeks ve soru kabulü kendiliğinden başlamaz. Bunlar tamamlanmış özellik olarak sunulamaz.

Yeni gerçek koşunun takip dosyası `evidence/source-spans-run.json`, salt okunur gözlemci `scripts/follow-source-pages.py`, gerçek API/PG karşılaştırması `scripts/verify-source-pipeline.py`. Kaynak metin dosyalarının üretiminde `editor.source_regions`, yerel PDF kelime kutularını da çıkarır. Teknik OCR ayrıntıları: [OCR servisi](ocr/README.md).

V2, bütün satır yerine konumlu kelimeleri eşleştirir; alıntıda kelime sınırını,
referans sırasını ve aradaki okunamayan bölgeleri denetler. `reuse_measurements_from`
aynı kaynak sürümünün ham ölçümlerini köken kimlikleriyle tekrar kullanabilir;
iddia ve kabul kararları taşınmaz. Kitap metni elle düzeltilmez.

Gözlemci `evidence/source-pages-status.md` yazar; her 10 sayfada ve terminal durumda
API/PG denetimi yapar. `scripts/qualify-completed-installation.py` tek seferlik
gerçek koşu sonrası paket/yedek/restore denetimini ayrı kurulumda yürütür;
başarısız analizi tekrar başlatmaz, anlamsal kabul veya yayın yapmaz.

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
python3 scripts/rebuild-search.py editor-restore
```

Betik mevcut kurulumu ezmez. Yeni yedekler kitap/sürüm/job/analiz/inceleme
kayıtlarının ve bütün kaynak/türev dosyaların hashlerini içerir; hedef işçileri
başlamadan karşılaştırılır. Eski manifestlerde bu kontrol yoktur ve sonuçta
`book_records_and_artifacts_equal=false` görünür. Sonrasında arama betiği
PostgreSQL pasajlarından Qdrant indeksini kurar; her vektörü ve kaynak bağını
kontrol eder. Bu adım aktif işi olan kurulumda çalışmaz. Geri dönen gerçek API
cevapları, atıflar ve kaynak ekranı ayrıca doğrulanmalıdır. 17 Eylül v2 dolu kitap yedeği ayrı kurulumda restore edildi; gerçek API/PG ve mobil ekran denetimi geçti. Sentez/arama/cevap kalitesi bu restore ile doğrulanmış değildir. Tek host/tek DB
topolojisi yüksek erişilebilirlik sağlamaz; RPO/RTO henüz taahhüt edilmemiştir.

Referans kitap kabul betiklerinde `EDITOR_VERIFY_BASE_URL` ile hedef kurulumun
loopback adresi seçilir. Örneğin `EDITOR_VERIFY_BASE_URL=http://127.0.0.1:8811`
ile `verify-book-results.py`, `verify-book-answers.py`, `verify-source-views.py`
ve `verify-review-ui.cjs` geri yükleme kurulumunu denetler. Bu betikler hedefin
kendi operatör anahtarını, Compose DB'sini ve kopyalanmış kabul koşusu
kimliklerini kullanır; varsayılan adres 8810'dur. Kaynak kurulum üzerinde
alınmış bir sonuç hedef restore kabulü olarak sunulmaz.

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
