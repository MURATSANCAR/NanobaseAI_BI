# NanobaseAI BI — Proje Belleği

## V14-r3 canlı kod — öykü / bilgilendirici içerik kapsamı

Backend/document/web `source-analysis-v14-r3-20260918`;47 backend dosyası tree hash `e07cdb27015c9df481a99bb1a5784dbf600f62170205165511478748e3c225a6`,9 web kaynak/çıktı eşliği geçti. Kod `ccbeccc` main üzerinde; R3 kitap koşusu henüz başlamadı. GitHub push kimliği eksik.

Yeni iş `efeeb1cb-4741-48f6-87a0-7b4e5285f786`, nesil `3db56430-4821-41c6-a513-4d6e4645bcd6` COMPLETED/NEEDS_REVIEW.48 sayfa kaynak/türetilmiş API-PG,31 sentez ifadesinde tam atıf ve yayın kapıları geçti;63 sınırlı uygun iddia/65 inceleme. Alıntı değişmez kaynak biriminden gelir; satır sonu ve ayrı büyük başlangıç harfi yalnız geometri ve doğrulanmış kaynaklarla okuma görünümünde birleşir, ham OCR değişmez. Eksik sözcük kapısı, tam ek dayanak aktarımı ve non-narrative sayfa-amacı önerileri için ayrı kaynak bağlamı eklendi. Gerçek5/8/16/29/38 pilotları ve canlı5/8 üretimi geçti; tam kitap anlamsal kabulü açık.

R1 nesli `6dca7f01-590c-4a28-a969-a8c8fbb67776`48/48 teknik bütünlük ve27 sentez ifadesinin eksiksiz atıf kontrolüyle tamamlandı; anlamsal kabul değildir.5/8/29 hataları R1 kayıtlarında korunur. R2 paket/import geçti; `/data/nanobaseai/editor-qualifications/v14-r2-20260918/3db56430` ayrı restore/mobil kabulü02:09:58UTC’de geçti; target ve geçici proxy kapatıldı. API18824/metrik19104, subnet72/73 ve geçici dar18886/18888 model proxy'si seçildi. [Ayrıntı](docs/editor/2026-09-18-source-analysis-v14.md).

R3 canlı kod:45. sayfadaki bilgilendirici ek, R2 sentezinde öykü teması olmuştu. Bütün sayfalarda açık içerik kapsamı ve kaynak hashli öykü-amacı kapısı eklendi; gerçek45/16 olumsuz,5/29/38 olumlu kaynak pilotları çalıştı. Son-hash45/5/6 pilotu geçti, yeni tam koşu bekleniyor; önceki R2 nesli anlamsal kabul almadı. İlk GPU cold-boot refs/main newline hatasında başarısız; mevcut runner’lar geri getiriliyor. Kod düzeltildi, cache-v2 yeni paket import ediliyor. Bu bakım ve gerçek çıkarım kabulü bitmeden yeni kitap işi açılmaz.

## 18 Eylül — V13-r2 tarihsel kabul

Canlı Qwen ortak GPU profili0.82 bellek payı,16 eşzamanlı slot,8192 batched-token ve chunked-prefill oldu. Eski0.90/64 profil gerçek Qwen+OCR yükünde CUDA OOM verdi; sağlık200 yanıltıcıydı. Yeni profilde iki gerçek Qwen görsel isteği+12 OCR isteği örtüşerek geçti; örneklenen boş bellek en az11.896MiB. R2 işi kayıtları korunarak API retry/attempt2 ile devam ediyor. Tam kapasite/uzun süreli yük ve kitaba anlamsal kabul açık. [Kod profili](apps/editor/gpu/compose.qwen-shared-gpu.yaml).

GPU OCR gateway kodu `apps/editor/gpu/` altında sürümlendi; idle/istek yarış düzeltmesi ayrı GPU adayında ve ardından ana gateway8010'da gerçek kitap kırpımı ve HTTP gövde kontrollerinden geçti. OCR modeli yeniden başlatılmadan V2 yayımlandı. [Kapsam](apps/editor/gpu/README.md).

Gateway V2 normal yaşam döngüsü de doğrulandı:603sn doğal idle kapanması, gerçek kırpımla otomatik açılma ve200 yanıt. Web R3 hata durumunda mobil taşma ve erken üst kaynak bulunamadı mesajını düzeltti; gerçek fragment kartı dört genişlikte API metin/okuyucu/bbox eşliğiyle geçti. Adversarial idle/istek stres matrisi ve tam anlamsal kabul açık kalır.

V12 nesli48/48 teknik kontrol ve türetilmiş API/PostgreSQL eşliğiyle tamamlandı; tam anlamsal kabul yok. V13-r1 kaynak48/48 ve27 fragment üretti, kimlik kolundaki native UUID hatası R2 ile düzeltildi. Değişen kodla eski nesli devam ettirmeme koruması korunur. Canlı backend `source-analysis-v13-r2-20260918`; iş `13640da6-8622-476e-82e2-ec259bd10401`, nesil `c046c684-8821-4770-bab3-fb7dc9c25b05` gerçek kabulde. [Güncel ayrıntılar](docs/editor/2026-09-18-source-analysis-v13.md).

R2 nesli48/48 teknik ve türetilmiş API/PG bütünlüğüyle COMPLETED/NEEDS_REVIEW:51 sınırlı sentez iddiası,24 taslak ifade,262 inceleme bölgesi ve0 genel karakter kimliği. Backend R2/web R3 uygulama paketi `/data/nanobaseai/editor-qualifications/source-analysis-v13-r2-web-r3-external-20260918` importtan geçti. GPU `/data/editor-gpu-releases/source-analysis-v13-shared-memory-v1-20260918`172 dosya/3 imaj hashleriyle importtan geçti; yeni GPU'da offline açılış kabulü değildir. GitHub HTTPS kimliği yok; origin push bekliyor.

Editör çıkarım yolu artık Mac'e bağlı değildir: GPU `editor-gpu-tunnel.service`, CPU127.0.0.1:18885/18887'yi GPU8001/8010'a bağlar. CPU nginx Docker bridge18882/18884 adreslerini korur. Ayrı SSH sistem hesabı yalnız bu iki remote porta izin verir; komut, local forward ve ek port gerçek denemede reddedildi, mevcut admin SSH config'i değişmedi. Gerçek aynı figür isteği3,184sn (Mac20,870sn); OCR0,878sn. Eski Mac tünelleri diğer tüketiciler için korunur; BI'ın bağlantı yolu bu değişiklikle otomatik taşınmış sayılmaz. [Kurulum](apps/editor/gpu/tunnel/README.md).

Güncel R2 tamamlanmış neslinin tutarlı yedeği ve ayrı `editor-v13-r2-restore` kurulumu geçti: bütün kitap/artifact eşliği, API/PG/ACL, backend/web hashleri ve320/390/768/1440px dolu OCR/kimlik/fragment/diyalog/sentez akışları doğrulandı. Hedef servisler kapatıldı, geçici ağ kuralları kaldırıldı; volume/kanıt korundu. Arama rebuild ve cevap kalitesi bu restore kabulünde yoktur. [Kanıtlar](docs/editor/2026-09-18-external-installation-acceptance.md).

## Güncel Editör model akışı — 18 Eylül

Ana model GPU Qwen3.8-Flash-Next; ihtiyaç halinde PaddleOCR-VL-1.6. Eski CPU LLM kapalı, embedding/reranker korunuyor. Bağımsız görsel/OCR kolları paralel; kaynak iddiaları tamamlanmalarını bekler. Canlı backend `source-analysis-v13-r2-20260918`, web `source-analysis-v13-r3-20260918`; tam kitap ve semantik kabul henüz yok. [Güncel kanıt ve devam kaydı](docs/editor/2026-09-18-source-analysis-v13.md).

## 2026-09-18 — Kitap seslendirme kaynak hazırlığı

Kullanıcı ses kaynağını Anilosan15/Turkish_TTS_Data olarak değiştirdi. İlk shard SHA-256 ile doğrulandı, 747 özgün WAV (84,13 dakika) ve metin manifesti çıkarıldı. Tam küme 30.606 kayıt/20,68 GB; tamamı indirilmedi. sıla veri kümesi etiketidir; lisans belirtilmemiş. Mevcut kitaptan API/PG eşliği doğrulanan metinle CPU üzerinde 11,56 sn/24 kHz pilot üretildi. Model tekrar/EOS uyarısı verdi; içerik tamlığı ve dinleme kalitesi DOĞRULANAMADI, ürün kabulü yok. [Hazırlık ve sonraki kabul adımları](apps/editor/speech/README.md).

## 2026-09-18 — Qwen ana model / paralel OCR V11

Bağımsız görsel gözlem ve ihtiyaç halinde GPU bölgesel OCR paralelleştirildi; kaynak bağımlı iddialar ikisini bekler. Ham ölçüm/provenance ve çelişki kapıları korunur. Gerçek yeni nesil kabulü sürüyor. [Ayrıntı](docs/editor/2026-09-18-qwen-ocr-parallel.md).

Bu dosya canlı özet, tek doğru kaynak. Değişiklik olunca üzerine yazılır (eski bilgi silinir/düzeltilir). Kronolojik geçmiş için [docs/GELISTIRME-GUNLUGU.md](docs/GELISTIRME-GUNLUGU.md)'ye bak.

## Proje ne

Doğal dilde soru → yönetilen SQL → doğru veri. Tek başına kurulan BI ürünü: React arayüz, FastAPI backend, Query Gateway, semantic katman, senaryo motoru ve LLM servisi. İlk/ana müşteri: TİMAŞ Logo (mağaza/satış verisi).

## PaddleOCR-VL-1.6 hazırlık durumu (2026-09-18)

GPU OCR başlangıcında bellek hatası yeniden üretildi; kullanıcı başlatma talebiyle yalnız OCR rezervasyonu %5 → %4 düzeltildi. Gateway8010 healthy=true ve model listesi200; Qwen korunuyor, boşta kapanma600 saniye. Gerçek OCR/yeniden uyanma ve Editör API/PG kabulü henüz DOĞRULANAMADI. [Kontrol kaydı](docs/editor/2026-09-18-paddleocr-vl-readiness.md).

## Editör modülü — bağımsız altyapı (2026-09-17)

Editör aynı depoda `apps/editor/` altında BI'dan bağımsızdır. Sunucu `nanobase-direct`, kök `/data/nanobaseai/editor`; API/web localhost 8810, metrikler 9096. Ayrı PostgreSQL, Qdrant, API/worker, OCR, yerel LLM/embedding/reranker, Prometheus, gateway ve ağsız parser olmak üzere 11 servis. PDF araçları ağsız Docling/Poppler/Tesseract konteynerindedir. BI iç kodu/tablosu kullanılmaz; entegrasyon API üzerinden yapılacaktır.

### Otomatik bölgesel okuma: V10 kabul çalışması

Yeni kitaplarda bölgesel yeniden okumanın yalnız önceki neslin artifactlerine bağlı kalması kodda giderildi. Ağsız ayrı tüketici, yazılabilir kuyruk ve değiştirilmeyen kaynak/kırpım/TSV kanıtları eklendi. İlk gerçek 61 bölge bileşen kontrolü geçti; yeni lease ile iptalden toparlanma açığı sonrasında düzeltildiği için V10-r2 yeniden doğrulanıyor. Yeni kitap optical API/PG kabulü ve müşteri offline/yedek kabulü henüz tamamlanmadı. Ana V5 değişmedi; ayrı V8 koşusu 17 Eylül 14:51 UTC'de 20 sayfa kontrolünü tamamlamıştı. [Bileşen kanıtı](docs/editor/2026-09-17-reread-queue-component.md), [toparlanma](docs/editor/2026-09-17-reread-attempt-recovery.md), [kurulum/yedek](docs/editor/2026-09-17-reread-deployment.md).

### Farklı kitaplarda çalışma kuralı (2026-09-17)

Üretim kodu/prompt/kapıları kitap adı, hash, karakter veya sayfa numarasına özel çözüm içermez. Aynı ad yazımı karakter kimliği değildir. Paralel inceleme limit sözleşmesi ve küçük görsel kapsam sayacında açık işler buldu. Yeni Türkçe metin konuşmacısı adayındaki ortak/kısmi ad ve geniş alıntı riskleri sıkılaştırıldı; gerçek 1.149 API/PG kaydında değişmeyen kaynakla 10 açık atıf ölçüldü. Metin atfı v5 ile yayımlandı; farklı kitaplarla anlamsal kabul ve görsel kimlik çözümü açık. [İnceleme ve kabul sınırları](docs/editor/2026-09-17-generality-review.md).

### Güncel yayın — v5 metin atıfları (2026-09-17)

Ana yayın `text-attribution-v5-20260917`; nesil `14a79646` 48/48 COMPLETED/NEEDS_REVIEW, kaynak 821/328. 10 açık metin atfı, model iddialarına bağlanan konuşmacı 0. Gerçek ana API/PG tam sayfa ve dört genişlikte atıf/bbox kabulü geçti; aynı sürümün bağımsız gerçek restore ortamında sekiz kesilen yükleme senaryosu geçti. Görsel kimlik ve anlamsal kabul açık. [Kod ve kanıt](docs/editor/2026-09-17-text-attribution.md).

### Çok kitaplı kaynak kabulü

Özgün 48 sayfalık kitaba ek olarak Kahramanını Yutan Kitap (64 sayfa) ve Dünyanın En Korkak Hayvanı (32 sayfa) ayrı API18810 ortamında değişmeyen PDF ile yüklendi. Gerçek API/PG, bağımsız Poppler sayfa sayısı ve kaynak artifact hashleri geçti. Bu iki kitabın analiz koşusu henüz başlatılmadı; üç kitapta anlamsal kabul iddiası yok.

### Devam eden v8 — anlatı ve görsel kapsam kapıları

Ayrı API18810 ortamı `narrative-coverage-v8-20260917`, nesil `7e7db466-3576-4c23-85b2-73483ab4508e`, iş `72f75bb3-a807-4e0b-8ca3-35f7ad0d0cbe`. Anlatı dışı bütün iddialar kodda engellenir; gerçek önceki 48 sayfada 15 yanlış MATCH adayını engelleyip 124 anlatı/karma adayı değiştirmedi. Görsel kapsam küçük alan nedeniyle dışlanan 52 bölgeyi açık gösterir; eski 19 büyük kırpım korunur, yeni model çağrısı eklenmez. Backend/web hash eşliği, gerçek 2/13/29 sayfalarında API/PG/ata ham kaynak ve anlatı/kapsam kontrolleri, dört genişlikte mobil kapsam ekranı geçti. Tam nesil koşusu sürüyor. Ana yayın v5 kalır. [Anlatı kapısı](docs/editor/2026-09-17-narrative-gate.md), [görsel kapsam](docs/editor/2026-09-17-visual-coverage.md).

### Hazır V9 ve otomatik sonraki koşu

Tam sayfa ikinci okuyucunun yanlış vetosu için, stabil kaynaklı kırpım + temiz PDF + bölgesel OCR desteğine dayalı genel seçim adayı gerçek 1.149 kayıtta 14 ek kazanım/0 gerileme gösterdi (874/275 yalnız aday). Sabit V9 imajı hazır; sunucudaki `continue-source-release.py` V8 tamamlanınca ayrı ortamda sürüm/hash kontrolüyle V9 koşusunu başlatıp son denetimleri yürütmek üzere WAITING_FOR_CURRENT_JOB durumunda. V8 kesilmez, ana V5 değiştirilmez; nihai kabul henüz yok. [Akış ve kanıt](docs/editor/2026-09-17-crop-source-continuation.md).

### V7 — kaynağı koruyarak devam

V6 R2 sayfa 2 taze çıkarımı 448,115 saniyede tamamlandı; kaynaklı seçim UI dört genişlikte geçti. Beşinci sayfa tamamlandıktan sonra API iptaliyle kayıtlar korundu. V7 en yakın tamamlanmış sayfa atasını seçer, model girdisini sıkıştırır ve genel priority_pages sırası ekler; kalan bütün sayfalar işlenir. Gerçek ata/tokenizer ölçümü geçti; nesil ab85c397 dokuz sayfanın kontrollerinden sonra API ile iptal edildi; sonuçlar korunarak V8 nesline geçildi. Gerçek soğuk model başlangıcında üç bağlantı hatası ve iki 503 sınırlı tekrarlarla toparlandı; 29. sayfa taze çağrısı tamamlandı. Dört genişlikte kaynak UI geçti; V7 tam koşu kabulü verilmedi; kalan iş V8 üzerinde devam ediyor. [Kayıt](docs/editor/2026-09-17-page-resume.md).

### Devam eden v6 — bölgesel kaynak seçimi

Bölgesel OCR seçim kodu gerçek 1.149 kayıtta 39 iyileşme adayı/0 gerileme gösterdi. Ayrı restore API18810 ortamının ilk v6 koşusunda iki kaynak yükseldi, model açılışındaki HTTP hatası işi durdurdu. Sınırlı geçici hata tekrarı ve durum kodu kaydı eklendi; R2 beş sayfalık kontrol sonrası korunarak iptal edildi; aynı düzeltme V7 koşusunda devam ediyor. Ana yayın v5 olarak kalır; v6 tam kabul henüz yok. [Kök neden ve kanıt](docs/editor/2026-09-17-regional-source-selection.md).

### Önceki yayın — kelime sınırı kapısı (2026-09-17)

Önceki yayın `source-boundaries-v4-r2-20260917`. OCR karşılaştırmasının boşlukları silerek farklı kelime bölünmelerini eşit sayması kodda düzeltildi. Eski neslin gerçek 1.149 API/PG bölgesinde 7 yanlış eşlik kaldırıldı (821 anlaşma/328 inceleme); çalışan kod/dosya eşliği ve temel API/PG kabulü geçti. Yeni nesil `99881d8f-77b9-499c-9876-fe114b4afc01` 48/48 tamamlandı; 821/328, ham ölçümler değişmedi, geçersiz kaynaktan geçen aday 0, yeni aday model çağrısı 0. Gerçek API/PG ve kaynak/yayın kontrolleri geçti; bu sürümün offline/restore kabulü 17 Eylül 11:02:51 UTC’de geçti. Kitap verisi elle değiştirilmedi; konuşmacı ve anlamsal kabul açık. [Kanıt ve güncel kapsam](docs/editor/2026-09-17-word-boundary-gate.md).

### Kitap kapsamlı yetki sürümü (2026-09-17)

**Önceki yayın kabulü:** `book-access-v4-20260917` kendi offline paketinden 14 tablo/artifact eşliğiyle yeni restore, gerçek API/PG/OCR ve dört genişlikte mobil kabulü 10:00:32 UTC'de geçti; restore ACL hatası kapatıldı. Font eşleme yalnız deneydir: 1.160 bozuk harf gösteriminin 1.156'sına aday karşılık bulundu, fakat optik kapıda iyileşme 0. Bu yayının kaynak sayısı 828/321 idi; 29. sayfa figür–karakter kimliği hâlâ açık. [Ayrıntılar](docs/editor/2026-09-17-restore-acl-and-source-triage.md).

**Önceki yayın — otomatik yükleme:** `upload-queue-v2-20260917`. Yeni PDF arayüzden yüklenir, ağsız parser kuyruğunda hazırlanır; 202/job_id, kalıcı durum, iptal, iki iş sınırı ve tekrar kontrolü vardır. Boş ayrı kurulumda özgün kitabın 48 sayfası, gerçek API/PG/Poppler ve dört ekran genişliğiyle doğrulandı. Kuyruk doluluğu, dosya mühürleme, iptal ve servis yeniden başlatmada devam geçti. Ana kurulumda özgün PDF tekrar kuyruğa alındı, mevcut sürüm kullanıldı; analiz kayıtları değişmedi. Bu yayının kendi offline paket/restore, geri yüklenen API/PG/OCR ve mobil kontrolleri 08:15:30 UTC’de geçti. [Kod ve gerçek kabul](docs/editor/2026-09-17-upload-pipeline.md).

**Bağlayıcı kalite kuralı:** Kitap metni, model cevabı, konuşmacı veya kabul kararı Codex tarafından elle düzeltilmez; beklenen cevap prompt/kural/veriye yazılmaz. Genel kod değiştirilir, gerçek kaynak uygulama tarafından yeniden işlenir. Önceki nesiller silinmez. İşlenen sayfa ile doğrulanmış analiz birbirinden ayrıdır.

**Önceki analiz koşusunun üretildiği yayın:** `source-review-v2-r2-20260917`; nesil `b652f63c-6ec4-4f9a-aff4-00b32d220b1b`, iş `c70995d2-496b-451d-8b34-a84eda4985f9`. 48/48 COMPLETED / NEEDS_REVIEW; 828 anlaşma/321 inceleme. Gerçek API/PG kontrolünde 371 yeniden okuma, 92 çelişki, 48 sayfanın yeniden kullanılan adayları ve yeni kaynak bağlantıları korundu; yeni model çağrısı 0. Üç nesil üzerinden 15 OCR-VL adayının kaynak bağlantısı geçti. Offline paket/import ve ayrı kuruluma restore geçti; geri yüklenen gerçek API/PG, OCR adayları ve dört genişlikte arayüz 07:18:10 UTC itibarıyla doğrulandı. [Ayrıntılı kod ve kanıt kaydı](docs/editor/2026-09-17-source-v3.md).

**OCR CPU ve paket denetimi:** Sorunlu kırpım pilotu v2 artifact alanında tamamlandı: 15 bölge, 14 tamamlanmış/1 kesilmiş, yalnız 1 sözcüklü okuyucu eşleşmesi; toplam 67,11 sn. Ana metne kabul edilmedi. Üretim önbelleği açık, bölge başına 120 sn sınırı var. Eski artifact korunur. Kurulum denetçisi dosya yazan araçların bitmesini bekler ve boş Docker alt ağı seçer; bu sürümün ayrı kurulum/restore kontrolü geçti. Docker IPAM Config=null hatası giderildi; aktif OCR artifact yazıcısı varken yedek başlamaz.

**Kaynak ekranı:** `source-review-v2-20260917` web imajında bölgeyi özgün sayfada işaretleme, PDF kullanılabilirliği ve yeniden okumalar görülebilir. Gerçek Chrome/API ile 320/390/768/1440 px, kutu eşliği ve sayfa değişimi kontrolleri geçti. OCR-VL CPU pilotu tamamlandı; doğrulanmış metin/analiz kabulü henüz yok.

**Önceki kaynak yayını — source-spans-v3:** Ek Unicode özel kullanım karakteri hatası giderildi; 371 yeniden okuma yeni nesilde kullanılıyor. Gerçek API/PG salt okunur tekrarda anlaşan bölge 778 → 828, inceleme 371 → 321; anlamsal kabul yok. Nesil `646f7dbe-fe96-4467-ae1e-351af9073543` 48/48 sayfayla tamamlandı, NEEDS_REVIEW; 828 anlaşma/321 inceleme. İlk 43 sayfanın değişmeyen ham adayları tekrar kapıdan geçirildi, son beş sayfanın çıkarımı yenilendi. OCR-VL pilotu tamamlandı ve adayları inceleme API/ekranına kaynak kimliğiyle bağlandı; ana metne kabul edilmedi. [Kod, sürüm ve kabul sınırları](docs/editor/2026-09-17-source-v3.md).

**Önceki ek yayın — otomatik yeniden okuma:** `region-reread-v1-20260917`; 46 sayfadaki 371 sorunlu bölge ağsız Tesseract PSM 7/13 ile yeniden okundu. 175 kararlı okuma, mevcut okuyucuyla eşleşen 147 aday; bunlar kabul edilmiş metin değildir. Özgün kayıtlar değişmedi. Çıktılar ayrı değişmez artifact alanında ve `region-rereads` API’sinde; `source-review` bunlara bağlanır. 46 sayfa/371 bölgenin gerçek API/artifact/PG ve inceleme bağlantısı kontrolü geçti. Konuşmacı/anlamsal kabul açık, yeni offline restore henüz yok. API imajı `sha256:3ec5c8082a38d568288b13158a1696491740d439852d84f5791b25cc1085e981`, belge imajı `sha256:2d166c713e64d9a967865ddd17c5e5e0bc681ae75017dd023f6ae41e29ed7f23`. [Yöntem, hashler ve gerçek koşu](docs/editor/2026-09-17-region-reread.md).

**Önceki inceleme API yayını:** `source-review-v1-20260917` inceleme API’si ve sayfa koordinatında balon-kuyruk/figür aday bağlantısı eklendi. 27 dosya çalışan imajla eşleşti; 48 sayfanın gerçek API/PG kontrolü geçti, kaynaklar değişmedi. 371 bölge ve karakter kimliği kabulü açık. İmaj `sha256:288d43b350356c736529eed8256dc2be3ddb929cd51d715096c3add507094ac1`; backend hash `97ce923c7592d8494546f3c51da379139a0a53dea8e3a1c887b98b155a65e00d`. Yeni ek API sürümünün offline restore kabulü henüz yok. [Kod ve doğrulama ayrıntıları](docs/editor/2026-09-17-source-review.md).

**Önceki v2 koşusu:** `source-spans-v2`, uygulama imajı `sha256:67226135f7620aa2cdd1639543700ff3dfcc42beab8248d38c490caf514e71b2`, backend ağaç hash `58004e5a5043d27508c12aa370ef81d92d97d08778abf2c7cc1b9b5a934fe2ef`, kod commit `6f14bb9`. Yeni nesil `a9471749-7447-4826-b003-f25e53943763`, iş `0d53b03d-67e5-44c4-b523-bf9a2aa56ac2`. V1 nesli `7a19f9eb-7e3e-40d0-822b-ac5e557960b4` API üzerinden iptal edildi; 18 OCR/görsel ve 17 aday/kontrol sayfası korundu. Yeni sürüm ham ölçümleri kaynak hash/köken denetimiyle yeniden kullanabilir; yeni okuma veya doğrulanmış analiz olarak göstermez. Yeni türetimler ayrı nesle yazılır.

**Düzeltmeler:** Bölgesel Paddle ölçümü artık PDF/Tesseract satırının tamamıyla değil konumca karşılık gelen kelimelerle karşılaştırılır. S.16'da gerçek veri tekrarında anlaşan bölge 1/56 → 46/56; ham metin değişmedi, bu anlamsal doğruluk oranı değildir. Alıntıda kelime sınırı, sıralı/kesintisiz kaynak ve yinelenen referans kontrolü vardır; uyuşmayan bölgeler model bağlamında boşluk olarak korunur. Serbest `visuals.description` iddia girdisi değildir. `source_spans`, `layout_regions`, `visual_observations`, `page_claims`, `page_checks` ayrı tutulur.

**Açık kapsam:** Konuşmacı kimliği ve anlamsal kabul henüz tamamlanmadı; bütün sayfaların işlenmesi nesli `NEEDS_REVIEW` yapar. Kitap sentezi, indeks, soru-cevap, kullanıcı/kitap rolleri, editör düzeltme bağımlılıkları tam müşteri ortam çeşitliliği kabulü tamamlanmış sayılmaz. `pilot_ready=false`. Diğer iki gerçek kitap, ikinci baskı ve insan editör süresi yoktur. Bu eksikler tahmin veya sentetik veriyle kapatılmaz.

**Takip:** `evidence/source-spans-run.json` canlı kimlik, `source-pages-v2-follow.log` ilerleme, `source-pages-status.md` tarihli görünüm. Her 10 sayfada ve terminal durumda `verify-source-pipeline.py` gerçek API/PG eşliğini denetler. Kod/model değişikliğinden sonra eski kabul aktarılmaz. LLM Qwen3.8-27B Q4_K_M, 48 CPU/thread, tek slot, 8192 bağlam, 1024 görsel token; embedding/reranker dörder CPU. PaddleOCR ana Compose servisidir; PP-OCRv5 Latin ağırlıkları imaj içinde, çalışma ağı kapalıdır.

**Kanıt/belgeler:** [Sistem düzeltmeleri ve açık işler](docs/editor/2026-09-16-system-quality-followup.md), [v1 kaynak akışının tarihçesi](docs/editor/2026-09-16-source-spans.md), [22 bölümlük kapsam](docs/editor/roadmap-live-status.md), [kurulum/restore](apps/editor/README.md). İlk OCR pilotu, eski caption yanlışları, iptal edilen koşular ve önceki mobil/altyapı kabulleri geliştirme günlüğünde ve bağlantılı raporlarda korunur; güncel sürüm kabulü olarak sunulmaz.


**Önceki v2 sonucu:** 48/48 sayfa işlendi; 1.149 kaynak bölgesinin 778’inde okuyucular anlaştı, 371 bölge incelemede. İş `COMPLETED`, nesil `NEEDS_REVIEW`; anlamsal kabul verilmedi. Gerçek API/PG eşliği, offline paket, ayrı kuruluma yedekten dönüş ve restore sonrası dört genişlikte mobil kontrol geçti. Manuel review ve kaynak düzeltmesi 0.

**Kurulum denetimi:** 17 Eylül 01:56:09 UTC itibarıyla v2 offline paket (8 imaj, 94 dosya, dört GGUF ve OCR), gerçek yedek/restore, hedef API/PG ve mobil kontrol geçti. Denetim `/data/nanobaseai/editor-qualifications/a9471749`; hedef servisler kontrol sonrası durduruldu, veriler korundu. Aynı hostta ayrı kurulum doğrulaması bütün müşteri ortamlarının kabulü değildir.

**Ayrıntılı devir:** [Yapılan işler ve son durum](docs/editor/2026-09-17-status-and-handoff.md).

## Mimari (üstten alta)


```
React (src/, Vite)  →  nanobase_api (FastAPI, :8790)  →  semantic_layer (Katalog + Evidence Engine + Resolver/Compiler)
                                                        →  semantic_bridge (:8795, Timaş'a özel köprü)
                                                        →  query_gateway (:8792, salt-okunur/izin listeli tek SQL çalışma noktası)
                        nanobase_awel  →  LLM operatörleri (planlama/onarım/açıklama iş akışları)
```

- **semantic_layer**: NL→SQL çekirdeği. Katalog + kanıt motoru esas doğru kaynak (WrenAI kaldırıldı, bkz. proje belleği `wren-teardown-done`). Detay: `docs/architecture/semantic-layer-v1.md`.
- **semantic_bridge (:8795)**: Timaş kokpitine özel köprü — `/api/v1/ask`, `/run_sql`, `/api/v1/semantic/*`, `/api/v1/schema/*`.
- **query_gateway (:8792)**: Müşteri SQL'inin tek çalışma noktası, salt okunur, izin listeli.
- **nanobase_api (:8790)**: API, chat gateway, semantic katalog, senaryo motoru.

## Stack

- Frontend: React + Vite + TypeScript (`src/`), Tailwind.
- Backend: Python/FastAPI (`backend/nanobase_api`, `backend/nanobase_awel`, `backend/query_gateway`, `backend/semantic_layer`, `backend/semantic_bridge`).
- Şema tarama/gömme: `tools/schema-indexer`.
- Kurulum: Docker Compose (`deploy/compose`, müşteri paketi); müşteri VM'ine yayın `scripts/server/deploy-customer-vm.sh`. LLM Türk Telekom GPU sunucusundaki Qwen3.8-Flash-Next-FP8 üzerinde; harici barındırılan model sağlayıcısı 2026-09-18'de tamamen kaldırıldı. Mevcut erişim Mac VPN/SOCKS ve SSH tüneliyle sağlanır.
- Editör: ayrı yığın `apps/editor/` (kendi Compose, PostgreSQL, Qdrant, OCR, yerel LLM).
- Meta DB: Postgres (:5434).

## Sunucu / port yapısı

| Servis | Port |
|---|---|
| Web (Vite dev) | 5174 |
| API (`nanobase_api`) | 8790 |
| Query Gateway | 8792 |
| Semantic Bridge (Timaş) | 8795 |
| LLM (OpenAI uyumlu) | Yerel GPU `qwen3.8-flash-next` / `Qwen/Qwen3.8-Flash-Next-FP8`; GPU `tt-gpu`, 2×H100 NVL. CPU host erişimi `127.0.0.1:18881/v1` (Mac VPN/SSH tüneli); Editor Docker erişimi `10.203.48.1:18882`. 18 Eylül geçiş/gerçek kabul çalışması sürüyor; harici sağlayıcıya fallback yok. |
| Gömme servisi | 8083 (embedder, CPU) |
| Meta DB (Postgres) | 5434 |
| Zeki AI sohbet | 127.0.0.1:4000 (ayrı Docker, `~/zeki-chat` deposu); portalda `/timas/sohbet/` altında AD oturumu arkasında sunulur |
| Portal giriş servisi | 8796 (`timas-login`, AD + oturum çerezi + `/chat-sso`) |
| BI uygulama VM (müşteri) | http://192.168.0.55/timas/ |

Ayrıntı proje belleklerinde: `semantic-production-deployment`, `bi-app-vm-55`, `llm-tt-gpu`, `timas-logo-network-access`.

**Çalışma yeri kuralı (2026-09-14):** Mac'te hiçbir işlem, sorgu ya da çalıştırma yapılmaz. Tüm iş bizim test sunucusu (`nanobase-direct`) ile müşteri sunucusu arasında yürür: sunucu → VPN `tun0` → TİMAŞ ağı (Logo SQL 192.168.0.155: `LOGO_DB`, socat `:14330`, `logo-mssql-connection.json`; CRM prod SQL 192.168.0.28 `CRMDATBASE`: `Timas_MSCRM`, `crm-mssql-connection.json`; BI VM 192.168.0.55). Mac yalnız sunucuya komut ileten uç ve dosya/git yeridir; müşteriye Mac'ten erişim yoktur.

**CRM ve Logo artık iki ayrı SQL sunucusu (2026-09-16):** Logo `.155` (socat `:14330`), CRM `.28` (`connector_from_file` → `secrets/crm-mssql-connection.json`, `zekiai`). Köprü `Runtime._conn_for(sql)` ile yönlendirir: SQL'de `timas_mscrm` varsa → .28, değilse → .155; tek SQL'de ikisi de = kasıtlı hata. Ayrıntı: yerel bellek `timas-crm-prod-28`.

**İki sunuculu (birleşik) sorular — plan (2026-09-16):** `semantic_layer/runtime/federated.py`. Soru iki kaynağa işaret ediyorsa (derleyici `_question_sources`, şemanın veritabanı öneki; `q.sources`) ve `SEMANTIC_FEDERATED=1` ise model tek SQL yerine JSON plan yazar: kaynak başına parça SQL'leri + `links` + bellekte (SQLite) çalışan `final`. `check_plan`: her parça yalnız kendi kaynağının katalog tablolarını okur, `final` yalnız parçaları okur, her bağ `final`'de eşitlik olarak geçer ve katalogda ölçülmüş `cross_source` ilişkisidir. Kapı yükümlülükleri parçalar üzerinde (herhangi biri karşılarsa tamam). Köprü `_answer_plan`: parça kendi bağlantısında tamamen okunur, `execute` birleştirir, cevap normal biçimde + `federated: true`. Bağlar `profiler/cross_source_links.py` + `scripts/discover_cross_links.py` (iki bağlantı) ile ölçülür, `scripts/apply_cross_links.py` ile kataloğa yazılır; gece taraması `cross_source` bağları silmez.

**Soru hattı kararları (2026-09-16):** Katalogun açıklamadığı niteleyici (ör. "tahsil edilmemiş") geri sorulmaz: `model_qualifiers` olarak modele verilir, model `-- yorum: '<kelime>' → <koşul>` satırı yazar (cevabın üstünde görünür), kapı yorum satırını ve ek bir kısıtı arar, cevap sertifikasızdır. Kaynağın kolon açıklamasında anlattığı durum `qualifier_columns` (kapı o kolonun kısıtlanmasını ister); kod etiketi olan durum doğrudan filtre. İstem tabloları sorunun kaynağından seçilir. Liste/ana veri sorularına varsayılan yıl eklenmez. Test: 500 soruluk set (`nanobase-direct:~/testset/all500.jsonl`, en zor 100: `set100.jsonl`), koşturucu `run_testset.py` (`timas-testset` systemd birimi), sonuç ekranı artifact `JMmco7kazxBbYLwaHvnxAV`. **Durum 2026-09-18 sabah:** en zor 100 sorunun 1–59'u doğrudan DB doğrulamasıyla karnede (`TİMAŞ Tek Tek Karne`, artifact `V99abTkwYZakQNLbA1qTpg`): 57 DOĞRU (10'u 'veri yok/boş doğrulandı'), Q38 kısmen (kitap kırılımı yok), Q56 açık; 60–100 sırada. CRM tarafı bu gece açıldı: bilgi paketi `rules/crm-timas.md` (Kural C1–C16), CRM ilişkileri Dynamics `MetadataSchema.Relationship`'ten okunur (`_dynamics_foreign_keys`, 11.270 lookup; eski kendine dönen uydurma ilişkiler silindi), 255 CRM tablosuna `statecode=0` varsayılan filtresi, iş bağı (OwnerId) denetim kolonlarına (CreatedBy…) tercih edilir. Kaynak seçimi: ölçü yoksa sertifikalı kolonların/ifadelerin kaynağı; oylamaya sertifikalı ifadeler de katılır; iki kaynakta ölçü varsa 2× çoğunluk. Kapı: `Timas_MSCRM_dbo_` öneki varlık karşılaştırmasında atılır; sertifikalı filtre kavramının ek `conditions`'ı her okumada aranır; modelin `NEW_X.kolon` niteleyici hatası onarılır (`repair_qualifiers_sql`). Özet: 'toplam' sorulunca genel toplam satırı, hiç dolu olmayan sütun notu. Bilinen boş CRM alanları caveats'te (telif tutarı, ajans ücreti, hakediş, etkinlik yazarı, üretim adedi).  birim testleri 853 (09-17: test sunucusunun canlı ağacında 853 geçti / 0 düştü; ağaç `main` ile md5 eş — dosya kurarken aynı commit'in `tests/` değişiklikleri de kurulur, yoksa bayat test sahte düşme üretir). **17 Eylül tarihsel CPU model ölçümü (18 Eylül GPU geçişinden önce):** sunucuda GPU yok; Qwen3.6-35B-A3B ve Arctic-Text2SQL-R1-7B gerçek istem boyunda ~375 sn ve hatalı SQL; derleme GPU sunucusundaki modelde (09-18), hız kazancı soruları deterministik yola çekmekten gelir.

**TİMAŞ erişimi:** Logo SQL (192.168.0.155) yalnız nanobase sunucusundaki WatchGuard OpenVPN tüneli (`tun0`) + socat `:14330` ile erişilir; Windows tarafına RDP (`timas\muratsancar`) de açık. VPN kullanıcısı `muratsancar` MFA (push/OTP) istiyor. Kullanıcı adı/şifreler repo'da **tutulmaz** — yerel proje belleğinde: `timas-access-credentials`.

**VPN nasıl açılır (2026-09-14'ten beri):** `timas` servis hesabı `AUTH_FAILED` veriyor; tünel `muratsancar` hesabıyla telefon onayıyla açılır. Sunucu `CRV1` meydan okumasını alır, `CRV1::<state>::p` ile bağlanır, kullanıcı WatchGuard bildirimini onaylar. Birim: `timas-vpn-mfa` (`systemd-run`). Şifreleme şartı: `--data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-256-CBC --data-ciphers-fallback AES-256-CBC`. Oturum kalıcı değil: kopma veya yeniden başlatmada push adımı tekrarlanır. Kopukken belirti: portal açılır, veri gelmez (köprü logunda FreeTDS `08001`). Kontrol: `ip -br addr show tun0`, `systemctl is-active timas-vpn-mfa`. Adım adım tarif: yerel bellek `timas-logo-network-access`.

**Türk Telekom GPU sunucusu (2026-09-17):** `tt-gpu` 172.23.85.10 (2 × H100 NVL 94 GB, 192 çekirdek, 2 TB RAM, `/data` 5,8 TB; GPU'lar arası NVLink yok, internet çıkışı ≈ 100 Mbit) ve `tt-gpu-vm` 172.23.85.11 (GPU yok). Erişim TT VPN (Ivanti/Pulse, `sgmvpn.turktelekom.com.tr/ttvm`) üzerinden; test sunucusunun ABD IP'si ağ geçidine TCP ile ulaşamadığı için VPN kullanıcı kararıyla **Mac'te** açılır: `~/bin/ttvpn-mac` (sudo'suz `~/homebrew` altında openconnect + ocproxy, SOCKS5 `127.0.0.1:11080`, Mac rotaları değişmez; parola ve e-posta OTP'sini kullanıcı yazar), `ssh tt-gpu` / `ssh tt-gpu-vm`, `~/bin/ttvpn-bridge` test sunucusunun `127.0.0.1:11080` portunu aynı vekile bağlar (yalnız HTTP/API; sunucudan SSH anahtarı eklenmedi). Makinedeki eski 2 × vLLM Gemma-4-31B (`~/mlops-pipeline`, 4 Eylül'den beri isteksiz) durduruldu, silinmedi; `mssql-logo` (LOGO_DB 301 GB, 124 GB RAM) çalışıyor. `Qwen/Qwen3.8-Flash-Next-FP8` (180B, 186 GB) `/data/hf-cache` altına iniyor; çalıştırma dosyası `/data/qwen38/docker-compose.yml` (iki GPU tek model TP2, n-gram tablosu RAM'de, MTP, port 8001) ile **18 Eylül gecesi ilk ayarlarla açıldı** (kart başına 64,6 GiB ağırlık, 950K token KV, `--numa-bind`; tek istek ≈ 130 tok/sn, 32 eşzamanlı ≈ 1.500 tok/sn; OpenAI uyumlu uç `tt-gpu:8001`, model adı `qwen3.8-flash-next`). Henüz BI köprüsüne bağlanmadı, golden set koşturulmadı. Editör OCR'ı için `PaddleOCR-VL-1.6` aynı makinede istek gelince açılan, 10 dk boşta kalınca kapanan Docker servisi olarak kuruldu (`/data/paddleocr-vl`, kapı `tt-gpu:8010`, soğuk açılış ≈ 69 sn); iki sayfalık denemede kutu ve eksiksiz metin verdi ama Türkçe harflerde zayıf, Flash-Next harfleri doğru okuyup metin atladı — editöre bağlanmadı, 1.149 bölgelik karşılaştırma bekliyor. Ayrıntı, riskler ve açık işler: [docs/TT-GPU-SUNUCUSU.md](docs/TT-GPU-SUNUCUSU.md). Parola repo'da tutulmaz.

**VPN erişim kapsamı (2026-09-17 itibarıyla):** tünel açıkken test sunucusundan Logo SQL `192.168.0.155:1433` (socat `:14330`), CRM prod SQL `192.168.0.28:1433` ve BI VM `192.168.0.55` (`ssh timas-vm`, yayın) erişilir; 16–17 Eylül'de üçü de gerçek sorgu/yayınla doğrulandı. 14 Eylül 13:30'da WatchGuard hesabı geçici olarak yalnız `.55:3389`'a indirmişti — aynı belirti görülürse (tünel var, SQL yok) neden VPN kuralıdır, TİMAŞ BT'den `.155/.28 TCP 1433` ve `.55 TCP 22` izni istenir. Teşhis ping ile değil TCP ile yapılır.

## Dizin haritası

| Dizin | İçerik |
|---|---|
| `src/` | React + Vite arayüz (tek frontend, kanvas: `src/canvas`) |
| `src/canvas/stitch/Shell.tsx` | Ortak kabuk (üst şerit, ray, modül menüsü). Kırıntıdaki kiracı adı ana sayfaya bağlantıdır; sağ üstteki pil oturumdaki kişinin baş harflerini gösterir (sahte EB/EA/SK yok). Sağ üstteki yakınlaştırma (%50–%200, adım 10) kabuğun kendi durumudur: ekranlar içeriklerini `ZoomStage` ile sarar (CSS `zoom`, `main` sabit kalır, yazdırmada 1); Genel bakış kanvası `onZoom` ile kendi ölçeğini verir (sığdırma × zoom). Pano sürüklemesi ölçeğe bölünür. `/uyarilar` ekranı `AlertsPanel inline` ile kural listesi/yeni kural gövdesidir (`?panel=yeni`); `screens.ts` yalnız `railFor`, `alertsData`, `cfoData` üretir |
| `src/canvas/board/` | Panolar: kişiye özel kart panosu (sürükle/boyutlandır, SQL paneli, son sorgu saati, başlık/not, CSV/PDF, KPI karşılaştırma, ECharts-GL 3B); düzen + son sonuç sunucuda `semantic_board_cards` (`backend/semantic_bridge/board.py`, `/api/v1/board`), tarayıcı yalnız önbellek; zamanlayıcı `timas-board.timer` |
| `backend/semantic_layer/rule_miner/` + `scripts/mine_rules.py`, `scripts/rule_probe.py` | İş kuralı madencisi (2026-09-16): Logo danışman görünümleri (`sys.sql_modules`, 211/411 okuyan 240 görünüm) ve CRM kayıtlı görünümleri (`SavedQueryBase`/`UserQueryBase` FetchXML) → etiket haritası / kolon adı / ölçü / adlandırılmış durum adayları; canlıda çürütme; politika: kaynağın kendi kuralı + çürütmeden geçti + çakışma/çok anlam/genel kelime/tek kelime(<3 kaynak)/tablo-adı değil → `rule-miner` sertifikası, aksi onay ekranı. Canlı: Logo 335 + CRM ~870 sertifika, ~600 onayda. `rule_probe` çözücü seviyesinde ölçer (kolon %90, durum %80, ölçü %73). CRM kolon adları harf duyarlı: profildeki yazım kullanılır |
| `backend/semantic_layer/vocabulary.py` | Eş anlamlı üretim hattı: alan açıklaması → aday → çürütme → insan onayı → kavram `synonyms`; `sl_vocabulary`; ezmeme kuralı (`human`/karar verilmiş satıra üretim dokunmaz); ekran `/es-anlamlilar` |
| `backend/semantic_layer/runtime/llm_queue.py` + `llm_jobs.py` + `candidates/llm_client.py` | **LLM kapısı** (2026-09-17): bütün modüller modele tek sıradan gider (`sl_llm_queue`). Öncelik 0/1/2 (`bg:`/`std:` öneki ya da `module=`/`priority=`), son slot(lar) yalnız bekleyen kişiye ayrılır, aynı öncelikte modüller sırayla hizmet alır, koşan kayıt kalp atışıyla yaşar (kiralama değil), kabul PostgreSQL advisory lock ile atomiktir. Sağlayıcının 429/503/504/529 cevabı `sl_llm_gate` ile bütün süreçlerle paylaşılır: kabul durur, slot yarıya iner, başarıyla geri açılır. Köprü içi kod `rt.llm_for("modül")` kullanır (doğrudan `LlmClient` kurmak sırayı deler); ayrı servis/arayüz `POST /api/v1/llm/jobs` → 202 + id, `GET …/{id}?wait=`, `…/events` (ndjson), `DELETE` (iptal). İşler `sl_llm_job`'da kalıcıdır: yeniden başlatmada kaybolmaz, işleyicisi ölen iş sıraya döner, aynı kullanıcı+modül+prompt uçuştayken tek iştir. Durum: `GET /api/v1/llm/queue`. Köprü iş parçacığı havuzu 200 (`SEMANTIC_THREADPOOL`). Akışlı çağrı `LLM_STREAM=1` (varsayılan kapalı; eski barındırılan sağlayıcıda ölçüldü, süre farkı yok). Ayrıntı: [docs/LLM-KAPISI.md](docs/LLM-KAPISI.md) |
| `backend/semantic_bridge/reports.py` | Planlı raporlar: cümleden plan (`parse_prompt`), `semantic_reports` tablosu, Excel/CSV üretimi (`/data/nanobaseai/bi/var/reports`), SMTP (ALERT_SMTP_*) yoksa dosya indirilir; `/api/v1/reports*`, zamanlayıcı `timas-reports.timer` (5 dk); ekran `src/canvas/reports/ReportsScreen.tsx` (`/planli-raporlar`) |
| `backend/semantic_bridge/prefs.py` | Kişi tercihleri `semantic_user_prefs` (AD hesabı + anahtar → JSON), `/api/v1/me/prefs/{key}`; Genel bakış kanvas düzeni `layout:<ekran>` burada. Kişiye özel alanların hepsi sunucuda: planlı raporlar (`username`), pano (`username`), uyarılar (`created_by`), kanvas düzeni (prefs); tarayıcı yalnız önbellek |
| `sl_query_log` (+ `src/canvas/admin/PromptTracker.tsx`) | **Promt izleyici**: sorulan her soru + üretilen SQL + tam sonuç (`result_json`) + kim sordu (`username`) + cevap tipi/özet + kapı kararı (`gate_json`) + inceleme işareti/notu. Yazan: `Runtime.ask` içindeki `_log` (16 dal). İnceleme yalnız yöneticiye: Yönetim → "Promt izleme" sekmesi, uçlar `GET/PATCH /api/v1/admin/prompts*` + `export.csv`. Amaç: alıp inceleyip nereyi düzelteceğimizi görmek. Migration `catalog_store._add_missing_columns` (var olan tabloya kolon ekler, restart'ta çalışır) |
| `backend/semantic_bridge/admin.py` + `src/canvas/admin/` | Yönetim (`/yonetim`, yalnız yöneticiler — `is_admin`: `TIMAS_ADMIN_USERS` listesi (vars. `zekiai,timasai,muratsancar`) **ya da** yönetici AD grubu `TIMAS_ADMIN_GROUP` (vars. `Administrators`, iç içe üyelik/`IN_CHAIN`). Grup üyeliği istek yolunda canlı okunmaz: `semantic_admin_group` tablosundaki anlık görüntüden okunur, `timas-admin-group.timer` 15 dk'da bir `POST /api/v1/admin/group/refresh` ile tazeler; tazeleme başarısızsa eski görüntü kalır, görüntü yoksa listeye düşer. `GET /api/v1/admin/group` üyeleri ve son tazelemeyi gösterir). **Veri Sözlüğü (`/veri-sozlugu`) ve Onaylar (`/onaylar`) da yönetici-özel:** menüler yetkisizde hiç çıkmaz (`useIsAdmin` → ray/Kampüs/ModulesMenu), ekranlar `AdminGuard` ile korunur (ortak tema uyumlu `NoAccess` kartı), uçlar `_admin_gate` (concepts/schema.gaps/review/decide 403). Yönetim: ayarlar tablosu `semantic_settings` (ekran > `/etc/nanobase/semantic-bridge.env` > varsayılan; SMTP, alıcı alan adları, e-posta bağlantısı, hatırlatma, rapor dosya sayısı, oda saatleri, CRM şeması, LLM adresi/modeli/anahtarı/zaman aşımı, yöneticiler — `admin.conf()` ile okunur). Dosyada tutulan ayarlar: Active Directory → `/etc/nanobase/timas-ad.json`, Logo veritabanı (sunucu/port/veritabanı/kullanıcı/parola/sürücü/TDS) → `SEMANTIC_CONNECTION_FILE`; ikisi de ekrandan güncellenir. LLM ve veritabanı ayarı kaydedilince çalışan köprüde yeniden kurulur (restart yok); yeni bağlantı kurulamazsa takas edilmez, eski bağlantı sürer ve hata ekranda döner. Bağlantı denemeleri `/api/v1/admin/tests[/{id}]` (database · crm · llm · directory · email · store) gerçek bağlantıyı kurar ve kayda yazılır; salt okunur sistem tanımları `/api/v1/admin/system`. Değişiklik kaydı `semantic_audit` (rapor/uyarı/pano kartı/ayar/sözlük kararı/kolon açıklaması: oluşturma, güncelleme önce→sonra, silme, çalıştırma, deneme), herkesin raporları/uyarıları/kartları, kişiler ve yönetici atama, servis ve zamanlayıcı durumu; uçlar `/api/v1/admin/*` |
| `scripts/server/portal-login/` | Giriş: `timas-login` (:8796) Timaş Active Directory ile doğrular (ldap3 + NTLM MD4; import `Crypto` ya da `Cryptodome` ad alanını kabul eder), oturum çerezi + nginx `auth_request`; AD ayarı sunucuda `/etc/nanobase/timas-ad.json`. Demo/davet/Basic hesap yok (2026-09-14'te kaldırıldı). **Zeki AI sohbet SSO:** `/chat-sso` ucu portal oturumunu doğrular, sohbette (`127.0.0.1:4000`) aynı AD hesabıyla kullanıcıyı bulur/oluşturur (şifre rastgele, kimse bilmez) ve `sso_secret` ile bir giriş jetonu döndürür — şifre sohbete hiç gitmez; sohbet bağlantısı `/etc/nanobase/zeki-chat.json` (`root:www-data 0640`) |
| `deploy/zeki/portal-sso-setup.sh` | Zeki sohbet ↔ portal SSO kurulumu (nanobase-direct'te kullanıcı koşar, sudo; idempotent 3 adım): nginx bloğu (`# ZEKI-CHAT-BASLA/BITTI`; `/timas/sohbet/` auth_request + WebSocket + `proxy_buffering off` → :4000, ayrıca `/timas/sohbet/api/` öneksiz `→ :4000/api/` çünkü Meteor önekli POST'lara 405 verir) → giriş servisini güncelle/yeniden başlat → `zeki-chat.json` yaz. Sohbet kaynağı ayrı depoda (`~/Documents/GitHub/zeki-chat`, dal `zeki/8.5.3`, Rocket.Chat 8.5.3 fork); sunucuda `~/zeki-chat`, derleme `deploy/zeki/build.sh` (paketler → Meteor → Docker `zeki-chat:8.5.3` → compose `-p zeki`), `.env` yalnız sunucuda. **Durum 2026-09-16:** sohbet açılıyor ama otomatik SSO girişi tamamlanmıyor (ddpOverREST 401 → kimlik silme döngüsü); ayrıntı günlükte |
| `backend/nanobase_api` | API, chat gateway, semantic katalog, senaryo motoru |
| `backend/nanobase_awel` | LLM operatörleri, planlama/onarım/açıklama iş akışları |
| `backend/query_gateway` | Müşteri SQL'inin tek çalışma noktası |
| `backend/semantic_layer` | Semantic Catalog + Evidence Engine + History Miner + Profiler + Resolver/Compiler |
| `src/canvas/kampus` | Girişten sonraki ilk ekran (`/`): Kampüs intraneti + ZEKİ + modüllere geçiş; BI genel bakış `/genel-bakis`. Gerçek veriyle çalışan parçalar: rehber ve profil penceresi (`ProfileDialog.tsx`), toplantı odaları, zil (bana gelen kutlamalar) ve alkış duvarı (`semantic_greetings`: `GET /api/v1/greetings` → `sent/inbox/received/wall`, rehberden kişi seçilerek `POST`), günün modu (`prefs kampus:mood`), Dahili Rehber CSV indirme. ZEKİ örnek soruları motorun kapsamındaki finans sorularıdır. 2026-09-17 denetiminde kaynağı olmayan tasarım kartları (sesli bülten, çekiliş, doğum günü, ajanda, yeni kitap, yemekhane, hızlı operasyon, sahte alt bilgi bağlantıları) kaldırılmıştı. **2026-09-18:** kullanıcı isteğiyle üçü geri getirildi — Sesli Bülten (podcast) ve Önemli Günler & Ajanda sol sütunda, Yeni Kitaplar (kitap seçme) sağ sütunda; "Şirket Nabzı" + "Günün modun" kartı kaldırıldı (ölü kod temizlendi). Bu kartlar tasarım yer tutucusudur, gerçek ses/katalog verisi sonra bağlanacak; "çalışmayan düğme bırakılmaz" kuralı yalnız bu üç kart için kullanıcı onayıyla geçici esnetildi (çekiliş/doğum günü/yemekhane hâlâ yok) |
| `backend/semantic_bridge/people.py` | Kişi rehberi + profil. Liste prod CRM `SystemUserBase` (etkin, AccessMode 0/1) ∩ AD (etkin kişi, `ActiveDirectoryGuid`=`objectGUID`, yoksa hesap adı) ∩ son `PEOPLE_MAX_IDLE_DAYS` (365, Yönetim → Kişi rehberi) gün içinde giriş; birim boşsa AD OU'su. Alan önceliği CRM > AD > kişinin yazdığı. Kişinin dahili/kat/masa/cep/hakkımda + fotoğrafı `semantic_people_profiles` (AD hesabı). Uçlar `/api/v1/people`, `/api/v1/people/{hesap}/photo`, `/api/v1/me/profile[/photo]`. AD ayarı `/etc/nanobase/timas-ad.json` köprüye ACL ile okunur (`u:administrator:r`); okunamazsa liste yalnız CRM'den gelir (`adChecked:false`) |
| `backend/semantic_bridge` | Timaş kokpiti köprüsü (:8795) |
| `tools/schema-indexer` | Şema tarama ve gömme |
| `deploy/compose` | Müşteri kurulum paketi (Docker) |
| `deploy/nginx`, `deploy/docker`, `deploy/helm`, `deploy/k8s` | nginx site tanımları (portal/bi), frontend Dockerfile, Helm/K8s taslakları |
| `scripts/server/deploy-customer-vm.sh` | Müşteri VM'ine (192.168.0.55, `/home/ai/bi-docker`) paket yayını; `systemd-run` ile koşulur, `docker-compose.override.yml/.env/secrets` dışlanır. Küçük değişiklikte yalnız değişen dosya kopyalanır (md5 karşılaştır) |
| `apps/editor/` | Editör modülü (BI'dan bağımsız; bkz. yukarıdaki Editör bölümü, kurulum/restore `apps/editor/README.md`) |
| `docs/editor/` | Editör kanıt, kabul ve devir belgeleri; giriş noktası `2026-09-17-status-and-handoff.md` |
| `docs/TIMAS-IS-TANIMLARI.md` | 16 TİMAŞ iş tanımının kararı ve nerede uygulandığı (katalog / bilgi paketi); iş teyidi bekliyor |
| `configs/semantic/knowledge/logo/knowledge/` | Bilgi paketi: `rules/logo-erp.md` (Kural 9–11: üretim, sevkiyat, tanım), `glossary/logo-timas.md`, metrikler |
| `docs/analiz` | CRM ayrıntı, Kampüs kişisel ekran ve oda rezervasyon analizleri (2026-09-15) |
| `docs/architecture` | Kilitli mimari, tasarım ve plan belgeleri |
| `docs/audits` | Denetim/inceleme kayıtları |
| `docs/product` | Ürün belgeleri |
| `configs/` | Operatör yapılandırmaları (bağlantı profilleri, şema katalogları, semantic bağlamalar) |

## Kritik kurallar (AGENTS.md'den, kısa özet)

- **Mobil öncelik**: Her arayüz değişikliği 320/390/768/masaüstü genişliklerde tarayıcıda kontrol edilir; yatay taşma yok. Detay: `apps/cockpit/AGENTS.md`.
- **Gerçek DB ile doğrulama zorunlu**: Veri alma/SQL/hesaplama/raporlama etkileyen her değişiklik bağlı gerçek veritabanı + gerçek API akışıyla doğrulanmadan tamamlanmış sayılmaz. Yerel mock/fixture/SQLite ile test **yasak** (kullanıcı ayrıca istemedikçe). Doğrulanamıyorsa **DOĞRULANAMADI** diye raporla, başarı iddia etme.
- **Tek şirket, çok yıllık yedek**: TİMAŞ'ta tek şirket var; `211`/`411` gibi kodlar farklı şirket değil, yıl yedekleridir (bkz. proje belleği `logo-period-prefixes-are-years`, `timas-logo-database-shape`).
- Tam kural metni: [AGENTS.md](AGENTS.md).

## Notlar

- Çalışma zamanı davranışları (2026-09-17): sorunun veri tabanı (Logo/CRM) ölçünün kaynağından, ölçü yoksa soru kelimelerinin eşleştiği **tablo adlarından** okunur (`SemanticQuery.source_hint` → derleyici tablo kapsamı); yıl kopyaları ortak kolon adlarıyla birleştirilir, tek yönlü tarih sınırı açık uçlu dönemdir, 1899/1900 sentinel tarih dönem değildir; eleştirmen çapraz birleştirmeyi ve farklı hedefli anahtar eşitliklerini bloke eder; kapı `LEFT JOIN … ON` filtresini kabul eder ve `-- yorum`da adı geçen tablonun okunmasını ister; sonuç deposu sınırda hata değil kısmi sonuç + `truncated` döner. Tek tek karne: https://claude.ai/artifact/V99abTkwYZakQNLbA1qTpg
- Çalışma zamanı davranışları (2026-09-17, soru 12–17): kapıda durum ölçüsünün bakiye okuması ve ölçünün dışladığı satırları okuyan alt sorgu dönem kuralından muaf; varlık adı karşılaştırması `LG_` önekine duyarsız; sorunun kelimesi sütun değeri yazılamaz; yokluk sorusu ("hiç X almamış") dışlama yapısı (NOT EXISTS / NOT IN / LEFT JOIN … IS NULL) ister. Çözücü: zaman kelimeleri yeniden aranmaz; adlandırılmış kümeden sonraki sayım sözcüğü o kümenin COUNT'u (`count_key` ile fiş sayımı); "X, Y'nin ne kadarı" oran (`SemanticQuery.ratio`); kolon + "tanımlı/dolu" = dolu koşulu; ölçünün yanındaki kolonlar kırılım; "son N ay" = cari ayla biten N ay. Planlayıcı: aynı hedef tabloya bağlanan eşlemeler referans kuralı taşıyanın yolunu paylaşır; kolon-kolon koşul (`AMOUNT > SHIPPEDAMOUNT`) yazılır; oran sütunu eklenir; kolon başlıkları kavramın kendi adından. Hatırlanan örnek SQL'ler mantıksal adla gösterilir. `LlmClient` süreyi bütün uygular. Env (`semantic-bridge.env`): `LLM_CTX=32768`, `SEMANTIC_PROMPT_RULES_CHARS=40000`, `LLM_TIMEOUT_SEC=900`, `SEMANTIC_SELECTOR_TIMEOUT_SEC=60`. İş tanımları kararları: [docs/TIMAS-IS-TANIMLARI.md](docs/TIMAS-IS-TANIMLARI.md) (katalogda operatör sertifikası, iş teyidi bekliyor).

- **Kokpit yayını:** kaynak sunucuda derlenir. `rsync -a --delete src/ nanobase-direct:/data/nanobaseai/bi/frontend/src/`, sunucuda `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build`, sonra `sudo rsync -a --delete --no-o --no-g dist/ /data/nanobaseai/bi/cockpit/dist/`. Commit etmek yayınlamak değildir; canlıdaki `index.html` tarihine bak.

- Bu proje için ayrıca kalıcı bellek kayıtları `~/.claude/projects/.../memory/MEMORY.md` altında tutulur (semantic layer kararları, sertifikalama, kalite kapısı, vb.) — kod tabanından türetilemeyen proje bağlamı orada.
- Bu dosya + `docs/GELISTIRME-GUNLUGU.md` çifti bir **talimat**tır, hook değildir: oturumdaki Claude'un CLAUDE.md'yi okuyup uygulamasına bağlıdır, zorlayıcı değildir. Gerçek zorlama istenirse `.claude/settings.json`'a bir hook eklenebilir (örn. commit sonrası günlük güncellendi mi kontrolü) — bu ayrı bir iş, henüz yapılmadı.
