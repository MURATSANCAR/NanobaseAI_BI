> Güncel backend/document: `source-analysis-v15-r7-20260918`; web: `source-preview-v15-r2-20260918`. Gerçek soru akışında bulunan API500, eksik sözcük atfı ve cevap güncelliği sorunları kodda düzeltildi. Yeni canlı soru/tam kitap/arama restore kabulü sürüyor. [Ayrıntılar](../../docs/editor/2026-09-18-source-analysis-v15.md).

# Editör modülü — bağımsız kurulum

> **Güncel yayın V14-r5:** Backend/document `source-analysis-v14-r5-20260918`, web R3. Aynı girdili sınırlı model yeniden denemesi ve güçlü PDF/kırpım/OCR-VL uzlaşması canlı.47 backend dosyası,9 web kaynak/çıktı eşliği ve gerçek API/PG/28ACL geçti.10/32 kesilmiş çağrı bileşenleri ve9 ek destekli bölge gerçek kaynaklarda doğrulandı; yeni tam kitap/restore kabulü henüz beklenir. [R5 kod ve kanıtlar](../../docs/editor/2026-09-18-source-analysis-v14-r5.md). Aşağıdaki R4 ve önceki sürümler tarihçedir.

> **Tamamlanmış önceki yayın V14-r4:** Backend/document `source-analysis-v14-r4-20260918`, web R3. Nesil `08ca6877`48 sayfada COMPLETED/NEEDS_REVIEW;64 sınırlı uygun iddia/27 taslak, atıf boşluğu0. Gerçek API/PG, offline paket/import, ayrı dolu restore ve320/390/768/1440px mobil kabulü18 Eylül04:25UTC'de geçti.262 kaynak incelemesi ve genel figür kimliği açık; tam anlamsal/üretim kabulü yok. Qwen + isteğe bağlı PaddleOCR-VL doğrudan GPU→CPU tüneli üzerinden Mac VPN'i olmadan koşuyu tamamladı. Son GPU offline cold-boot sonucu yönetim VPN nedeniyle DOĞRULANAMADI. [Sürüm ve kanıtlar](../../docs/editor/2026-09-18-source-analysis-v14.md). Aşağıdaki eski yayın notları tarihçedir.

## 2026-09-18 — Kitap seslendirme kaynak hazırlığı

Kullanıcı ses kaynağını Anilosan15/Turkish_TTS_Data olarak değiştirdi. İlk shard SHA-256 ile doğrulandı, 747 özgün WAV (84,13 dakika) ve metin manifesti çıkarıldı. Tam küme 30.606 kayıt/20,68 GB; tamamı indirilmedi. sıla veri kümesi etiketidir; lisans belirtilmemiş. Mevcut kitaptan API/PG eşliği doğrulanan metinle CPU üzerinde 11,56 sn/24 kHz pilot üretildi. Model tekrar/EOS uyarısı verdi; içerik tamlığı ve dinleme kalitesi DOĞRULANAMADI, ürün kabulü yok. [Hazırlık ve sonraki kabul adımları](speech/README.md).

> V10 otomatik bölgesel yeniden okuma geliştirmesi: ilk 61 gerçek bölge bileşen kontrolü geçti; son lease/toparlanma düzeltmesi V10-r2 ile yeniden kabul ediliyor. Yeni kitap uçtan uca optical kabulü ve yeni offline/restore kabulü henüz tamamlanmadı. [Kurulum ve kabul sınırı](../../docs/editor/2026-09-17-reread-deployment.md).

> Ayrı API18810 doğrulaması: V8 `7e7db466` koşusu devam ediyor. Künye/etkinlik iddiası engeli ve görsel kapsam kaydı kodda düzeltildi; gerçek 2/13/29 sayfa API/PG ve dört genişlikte arayüz kabulü geçti. Ana yayın V5 olarak kalır. [Anlatı kapısı](../../docs/editor/2026-09-17-narrative-gate.md), [görsel kapsam](../../docs/editor/2026-09-17-visual-coverage.md).

> İki ek gerçek kitabın 64/32 sayfalık kaynak hazırlaması doğrulandı; analizleri henüz başlatılmadı. [Çok kitaplı kabul](../../docs/editor/2026-09-17-multibook-ingestion.md).

> Ana yayın v5: `text-attribution-v5-20260917`, ana nesil `14a79646` 48/48; 10 açık metin atfı, 0 claim-speaker. Gerçek API/PG, mobil atıf/kutu ve sekiz kesilen-yükleme kabulü geçti. Kaynak 821/328; figür kimliği ve anlamsal kabul açık. [Güncel kayıt](../../docs/editor/2026-09-17-text-attribution.md).

Önceki yayın `source-boundaries-v4-r2-20260917`: kelime sınırlarını silen optik karşılaştırma düzeltildi. Gerçek 1.149 API/PG bölgesinde 7 yanlış eşlik kaldırıldı; yeni nesil 48/48 tamamlandı, gerçek API/PG ve kaynak/yayın kontrolleri geçti; bu sürümün paket kabulü ayrıca izleniyor. [Kod, kabul kanıtı ve açık işler](../../docs/editor/2026-09-17-word-boundary-gate.md).

Bu modül ana BI deposunda geliştirilir; kendi Docker projesi, PostgreSQL kayıtları,
Qdrant indeksi, kaynak alanı ve yayın paketi vardır. BI'ın Python kodunu, tablolarını,
Docker ağlarını veya kimlik bilgilerini kullanmaz. BI ekran entegrasyonu sonraki
aşamada tanımlı API sözleşmeleriyle yapılacaktır.

## Güncel kurulum ve erişim

`book-access-v4-20260917`, kullanıcı/kitap kapsamlı erişim ve yedekten dönüşte yetki tablolarının izinlerini yeniden kuran başlangıç kodunu içerir. `verify.py` gerçek DB’de 28 izin kontrolünü, API ve kaynak hashlerini doğrular. [Restore hatası ve gerçek kabul kaydı](../../docs/editor/2026-09-17-restore-acl-and-source-triage.md).

## Önceki yayın: otomatik PDF kabulü

`upload-queue-v2-20260917`: yeni kitap arayüzden yüklenir, ağsız `parser` tarafından otomatik hazırlanır. 202/job_id, kalıcı ilerleme ve iptal API'si vardır. Gerçek kitabın 48 sayfası boş ayrı kurulumda; kuyruk sınırı, iptal, yeniden başlatma ve dört ekran genişliğiyle doğrulandı. [Ayrıntılı kod, imaj hashleri ve kabul sınırları](../../docs/editor/2026-09-17-upload-pipeline.md).

Web yayını sunucuda `python3 scripts/build-web.py <imaj-etiketi>` ile derlenir; `EDITOR_VERIFY_WEB=1 python3 scripts/verify-release.py` kaynak ve çıktı hashlerini çalışan imajla karşılaştırır. Müşteri kurulumu doğrulanmış offline imajları yükler; çalışma anında npm/model indirmesi yapmaz. Parser varsayılan 4 CPU, 6 GiB, 3600 saniye; sunucudaki doğrulamada 8 CPU kullanıldı. `EDITOR_PARSER_CPUS`, `EDITOR_PARSER_THREADS`, `EDITOR_UPLOAD_PARSE_TIMEOUT` ortam ayarlarıdır.

Aşağıdaki v2 işleme kayıtları tarihçedir; güncel analiz nesli `b652f63c-6ec4-4f9a-aff4-00b32d220b1b`, 828 anlaşma/321 inceleme ve NEEDS_REVIEW durumundadır. Kaynak hazırlama anlamsal kabul değildir.

## Sorunlu bölgelerin otomatik yeniden okunması

Sunucuda `python3 scripts/reread-source-regions.py 16 29 38` sınırlı gerçek sayfa koşusunu, argümansız çağrı bütün NEEDS_REVIEW bölgelerini işler. İki Tesseract satır ayarı ağsız belge konteynerinde çalışır; makine çıktıları ayrı artifact dosyalarına yazılır. Eski kayıtlar değişmez, sonuçlar otomatik onaylanmaz. Gerçek API: `GET /v1/generations/{generation}/region-rereads`; doğrulama `python3 scripts/verify-region-rereads.py`. [Ayrıntılar ve koşu sonucu](../../docs/editor/2026-09-17-region-reread.md).

## Kaynak inceleme API — 17 Eylül ek yayını

`GET /v1/generations/{generation}/source-review?pdf_page=29`, kayıtlı bölge uyuşmazlıklarını ve balon kuyruğunun sayfa koordinatındaki figür adaylarını döndürür. Yeni okuma veya kabul kararı yazmaz. Gerçek API/PG kontrolü 48/48 sayfada geçti; 371 bölge hâlâ incelemededir. [Kod değişikliği, sürüm ve kanıtlar](../../docs/editor/2026-09-17-source-review.md). Önceki v2 offline restore kabulü aşağıdaki kitap işleme sürümüne aittir; bu ek API imajının restore kontrolü henüz yoktur.

## Güncel teslimat ve doğrulama — 17 Eylül 2026

48/48 sayfa işlendi; 1.149 kaynak bölgesinin 778’inde okuyucular anlaştı, 371 bölge incelemede. İş `COMPLETED`, nesil `NEEDS_REVIEW`; anlamsal kabul verilmedi. Gerçek API/PG eşliği, offline paket, ayrı kuruluma yedekten dönüş ve restore sonrası dört genişlikte mobil kontrol geçti.

Canlı nesil `a9471749-7447-4826-b003-f25e53943763`, iş `0d53b03d-67e5-44c4-b523-bf9a2aa56ac2`, sürüm `source-spans-v2-6f14bb9`. Kaynak, okuma, yerleşim, görsel gözlem, iddia adayı ve sayfa kontrolü ayrı kaydedilir. OCR/PDF kelime eşleştirmesi ve kesintisiz alıntı kapısı uygulanır. Konuşmacı UNKNOWN kalır; adaylar senteze açılmaz.

FastAPI, PostgreSQL/Alembic, LangGraph checkpoint, Qdrant, lease/fencing kullanan işçi, ana Compose OCR servisi, yerel modeller, Prometheus, ağsız belge araçları ve salt okunur React ekranı kuruldu. BI entegrasyonu API üzerinden sonraki aşamadır. LLM son koşuda 48 CPU/thread, tek slot, 8192 bağlam, 1024 görsel token ve PID sınırı 512 kullanır; embedding/reranker dörder CPU kullanır.

Sentez/indeks/soru kodunun bulunması v2 neslin bu aşamalardan geçtiği anlamına gelmez. `pilot_ready=false`; çok kullanıcılı kitap/rol, editör düzeltme bağımlılıkları, PDF.js/bbox incelemesi açık. Genel yeni PDF ayrıştırma akışı sonraki `upload-queue-v2-20260917` yayınıyla eklendi; ayrıştırılmamış kaynak artık 202 ile kuyruğa alınır. Kitap metni/cevabı/review elle düzeltilmez; genel kod düzeltmesi sonrası yeni nesil doğrulanır.

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

## Kaynak v3 ve sınırlı OCR-VL

Ek Unicode özel kullanım karakterlerinin PDF metni sayılması düzeltildi; değişmez yeniden okuma ölçümleri yeni nesilde kullanılır. [Gerçek koşu ve açık kabul](../../docs/editor/2026-09-17-source-v3.md). Sorunlu kırpımlar için isteğe bağlı [ağsız OCR-VL aracı](ocr-vl/README.md) ve `bundle.py --with-ocr-vl` paketleme desteği vardır; pilot ve yeni restore sonucu doğrulanmadan üretim kabulü değildir.

18 Eylül R3 kodu canlı: öykü dünyası ile okura verilen bilgi/öğüt için kaynaklı kapsam kapısı eklendi. Gerçek45/5/6 pilotları geçti, R3 tam kitap koşusu bekliyor. R2 dolu restore/mobil PASS. GPU cache paketindeki refs/main newline hatası gerçek offline açılışta bulundu; exporter/importer düzeltildi ve yeni cache-v2 doğrulanıyor. [Güncel kanıtlar](../../docs/editor/2026-09-18-source-analysis-v14.md).

18 Eylül03:19UTC: R3 gerçek kitap dolu restore ve320/390/768/1440px mobil kabulünü geçti. R4 genel atıf-kimliği düzeltmesi canlı;47 backend/imaj eşliği ve gerçekAPI/PG altyapı/28ACL geçti. R4 tam kitap koşusu henüz başlamadı; GPU soğuk kurulum kabulü sürüyor.262 kaynak incelemesi ve tam anlamsal kabul açık. [Kanıt](../../docs/editor/2026-09-18-source-analysis-v14.md).
# Güncel yayın — V15 kaynaklı editör taslağı

Backend/document `source-analysis-v15-r5-20260918`, web `source-preview-v15-r2-20260918`.49 backend ve10 web dosya eşliği ile gerçek altyapı kontrolü geçti. Kaynak birimi gruplaması, kaynak destekli hibrit arama ve gerçek editör soru formu bağlı; yeni soru/tam nesil/indeks restore kabulü henüz tamamlanmadı. `published`, insan kabulü ve tam kitap doğruluğu açık kalır. [Güncel kanıt ve sınırlar](../../docs/editor/2026-09-18-source-analysis-v15.md).

Önceki V14-r5 tam teknik koşu, ayrı restore ve dört genişlikte mobil kontrol06:08UTC'de geçti; kaynak896/253, uygun sınırlı iddia61. Aşağıdaki eski sürüm notları tarihçedir.

API ve işçi kaynak sınırları `.env` üzerinden `EDITOR_API_CPUS`, `EDITOR_API_MEMORY`, `EDITOR_WORKER_CPUS`, `EDITOR_WORKER_MEMORY` ile ayarlanır; varsayılan her servis2CPU/1GiB. Bu sınırlar model eşzamanlılık sayısını değiştirmez. YarımCPU sınırı gerçek cevap ekranında zaman aşımına neden olduğu için kaldırıldı; kaynak güvenlik denetimleri korunur.
