# Editör: roadmap kapsamı ve gerçek koşu durumu

> **18 Eylül — V15 yayını, R5 tamamlanmış kabulü:** Canlı backend/document `source-analysis-v15-r5-20260918`, web `source-preview-v15-r2-20260918`. 49 backend dosyasının tree SHA256 değeri `71a90dcd7ed8337e87f89eeedae345390a0da2d94aabf25ebf5e466c2b771e75`; web imajı `sha256:37c90054ed5b94fbf5189e44d324ba2801436a5c655871dabf4ebe150d135f90`. **Tamamlanmış son kitap kabulü V14-r5 nesli `d9ff5c60-dd47-47cb-bf66-70a5cad59cb1` içindir:** 48 sayfa, 896 kaynak anlaşması/253 inceleme, 61 sınırlı semantik uygun aday; gerçek dolu yedek/ayrı restore ve mobil kabulü 06:08 UTC'de geçti. Bu eski neslin sonucu yeni V15 kodunun tam kitap kabulü değildir.
>
> V15 tam kaynak koşusu henüz başlamadı. Bu durum kaydı hazırlanırken gerçek ilk kaynaklı soru işi `0d53b588-e40e-4d0d-96ca-c8d6d3d0008b` çalışıyordu; soru/indeks/cevap kabulü henüz verilmedi. Kaynak preview yalnız **PARTIAL_SOURCE_SUPPORTED_DRAFT** kapsamındadır; yayımlanmış cevap veya tam kitap anlamsal kabulü değildir. Son web imajının doğru analiz kaydını yeniden açması 64 sayfalık farklı gerçek kitapla, ayrı API18810/PostgreSQL ve dört genişlikte geçti. [V15 sürüm/kanıt](2026-09-18-source-analysis-v15.md), [son web navigasyon kabulü](2026-09-18-upload-analysis-navigation-acceptance.md). Aşağıdaki R4 ve önceki sonuçlar tarihçedir.

> **18 Eylül04:25UTC — R4 tamamlandı:**48 sayfa kaynak/amaç/anlam/figür,64 sınırlı uygun iddia/27 taslak, atıf boşluğu0. Gerçek API/PG, yeni neslin dolu yedek/ayrı restore ve dört genişlikte mobil PASS; geçici ortam temizlendi.262 kaynak incelemesi ve genel kimlik0 nedeniyle tam kitap/üretim kabulü yok. GPU cold-boot sonucu VPN nedeniyle DOĞRULANAMADI; GitHub push kimliği eksik. [Kanıtlar](2026-09-18-source-analysis-v14.md). Aşağıdaki önceki durumlar tarihçedir.

> **18 Eylül03:49UTC — R4 çalışıyor:** Yeni nesil `08ca6877` gerçek kitapla başladı; R3 dolu restore/mobil kabulü tamamlandı. R4 yayımlanmış21/22/28 bileşen kontrolü geçti. GPUoffline pakette eksik CPUoffload ayarı genel kodda düzeltildi ve import geçti; son soğuk açılış isteğinde yönetimVPN koptu, sonucu DOĞRULANAMADI. Doğrudan model tüneli sayesinde kitap koşusu sürüyor. [Koşu](2026-09-18-source-analysis-v14.md), [GPU kök neden](2026-09-18-gpu-cold-boot.md).

> **18 Eylül03:19UTC:** R3 kitap işleme ve ayrı dolu restore/mobil kabulü tamamlandı;60 sınırlı iddia/27 taslak, atıf boşluğu0, anlamsal kabul false. R4 atıf-kimliği düzeltmesi canlı;47 backend dosyası eşliği ve gerçek altyapı/28ACL geçti. Yeni R4 tam koşu GPU offline soğuk açılış kontrolünün bitmesini bekliyor.262 kaynak incelemesi ve genel kimlik hâlâ açık. [Ayrıntı](2026-09-18-source-analysis-v14.md).

> **18 Eylül R3 kodu canlı:**47 backend dosyası ve9 web kaynak/çıktı eşliği geçti.45. sayfadaki bilgilendirici ek/öykü ayrımı kaynak amaç kapısıyla düzeltildi; final gerçek45/5/6 bileşen kontrolleri geçti. R3 yeni nesil97814b6c çalışıyor; bağımsız monitor ve ayrı kurulum qualifier aktif. GPU internet kapalı soğuk açılış paket refs/main newline hatasını yakaladı; paketleme/import kodu düzeltildi, cache-v3 hash/import ve gerçek HF offline çözümleme geçti. Tam GPU cold-boot, başka model isteği görüldüğü için servisler durdurulmadan ertelendi. R2’nin dolu restore/mobil kabulü geçti, anlamsal kabulü yok. [Ayrıntı](2026-09-18-source-analysis-v14.md).

> **18 Eylül V14-r2 tamamlanmış koşu:** Yeni nesil `3db56430-4821-41c6-a513-4d6e4645bcd6` COMPLETED/NEEDS_REVIEW;48 sayfa API/PG ve31 sentez ifadesinin eksiksiz atıf kontrolü geçti. Sözcük sınırı, eksiksiz atıf ve sayfa-amacı düzeltmeleri gerçek sorunlu sayfalarda geçti; ham kitap verisi değiştirilmedi. R2 paket/import geçti; ayrı restore/mobil geçti;45. sayfa bilgi/öykü kapsamı hatası için R3 düzeltmesi sınanıyor, tam kitap anlamsal kabulü açık. R1 teknik48/48 ve atıf kontrolü geçti; bilinen anlamsal hataları R2 kabulü sayılmaz. [Güncel kanıt](2026-09-18-source-analysis-v14.md).

> **18 Eylül V14-r1 tarihsel:** Backend/document V14-r1, web R3; yeni nesil `6dca7f01-590c-4a28-a969-a8c8fbb67776` çalışıyor. Kaynak birimi seçimi ve eksiksiz atıf aktarımı düzeltildi; R2 bağımsız genişletilmiş kontrolde4 eksik sentez bağlantısı verdi, eski bütünlük başarısı tam atıf kabulü sayılmaz. Yeni gerçek47 backend dosyası/web hashleri, API/PG altyapı ve28 ACL geçti. Tam kitap, dolu UI ve yeni paket/restore kabulü beklenir. R2 restore tamamlandı; aşağıdaki eski durumlar tarihçedir. [V14 kanıtları](2026-09-18-source-analysis-v14.md).

> **18 Eylül V13-r2 tarihsel:** Backend R2, web R3 ve GPU gateway V2 canlı. İş `13640da6-8622-476e-82e2-ec259bd10401`, nesil `c046c684-8821-4770-bab3-fb7dc9c25b05`: COMPLETED/NEEDS_REVIEW;48/48 teknik kaynak ve türetilmiş API/PG bütünlüğü geçti.51 sınırlı iddia/24 taslak ifade;262 kaynak incelemesi ve genel kimlik açık. Qwen/OCR eşzamanlı OOM, ortak bellek profiliyle düzeltildi; gerçek paralel çağrılar geçti. Mac'siz sunucular arası model yolu, uygulama/GPU offline import ve dört genişlikte dolu fragment/kimlik/anlam/sentez UI kabulü geçti. Güncel neslin yedek/restore kontrolüne geçildi. [V13 sürüm/kanıt](2026-09-18-source-analysis-v13.md). Aşağıdaki eski yayın etiketleri tarihçedir.

> **18 Eylül V12 tarihsel:** kaynak sonrası figür kimliği ve anlam denetimi ayrı paralel kollara bağlandı. Yeni iş `791de2a0-a440-419c-8db4-2095405eed23`, nesil `2d774b82-e04f-45a3-92fc-eadaa8a37934`. R9 22 sayfa teknik kontrolünden sonra kayıtları korunarak iptal edildi. Gerçek s7/s38 bileşen kontrolü ve gerçek figür kırpım karşılaştırması çalıştı; tam yeni nesil, kimlik ve anlamsal kabul hâlâ açık. [V12 ayrıntıları](2026-09-18-source-analysis-v12.md). Aşağıdaki eski sürüm sayıları tarihsel kanıttır.

> 18 Eylül — Qwen ana model + isteğe bağlı PaddleOCR-VL-1.6 akışı canlıya alındı. R6 ilk11 sayfanın API/PG ve ham kaynak kanıtı denetimi geçti;29. sayfada11 OCR bölgesi ve Qwen çağrısının örtüşmesi öncekiR5 koşusunda ölçüldü. Mobil OCR görünümü dört genişlikte geçti. Gereksiz simge çağrılarını azaltanR9, gerçek67 önceki çağrıda23 çağrıyı inceleme statüsünü değiştirmeden eleyebiliyor; destekli tek-glif okuması korunuyor. **P1/P2 henüz kapanmadı**: figür–karakter kimliği ve anlamsal kabul açık. [Sürüm, hatalar ve kanıt](2026-09-18-qwen-ocr-parallel.md).

## 2026-09-18 — Kitap seslendirme kaynak hazırlığı

Kullanıcı ses kaynağını Anilosan15/Turkish_TTS_Data olarak değiştirdi. İlk shard SHA-256 ile doğrulandı, 747 özgün WAV (84,13 dakika) ve metin manifesti çıkarıldı. Tam küme 30.606 kayıt/20,68 GB; tamamı indirilmedi. sıla veri kümesi etiketidir; lisans belirtilmemiş. Mevcut kitaptan API/PG eşliği doğrulanan metinle CPU üzerinde 11,56 sn/24 kHz pilot üretildi. Model tekrar/EOS uyarısı verdi; içerik tamlığı ve dinleme kalitesi DOĞRULANAMADI, ürün kabulü yok. [Hazırlık ve sonraki kabul adımları](../../apps/editor/speech/README.md).

> V10 otomatik bölgesel yeniden okuma geliştirmesi: ilk 61 gerçek bölge bileşen kontrolü geçti; son lease/toparlanma düzeltmesi V10-r2 ile yeniden kabul ediliyor. Yeni kitap uçtan uca optical kabulü ve yeni offline/restore kabulü henüz tamamlanmadı. [Kurulum ve kabul sınırı](2026-09-17-reread-deployment.md).

> Ana yayın v5: `text-attribution-v5-20260917`, ana nesil `14a79646` 48/48; 10 açık metin atfı, 0 claim-speaker. Gerçek API/PG, mobil atıf/kutu ve sekiz kesilen-yükleme kabulü geçti. Kaynak 821/328; figür kimliği ve anlamsal kabul açık. [Güncel kayıt](2026-09-17-text-attribution.md).

> Önceki yayın `source-boundaries-v4-r2-20260917`: kelime sınırı hatası kodda düzeltildi, eski neslin gerçek API/PG tekrarında 7 yanlış eşlik kaldırıldı (821/328). Yeni nesil `99881d8f` 48/48 tamamlandı; 821/328, geçersiz kaynaktan geçen aday 0, yeni aday model çağrısı 0. Gerçek API/PG ve kaynak/yayın kontrolleri geçti; offline/restore kabulü 17 Eylül 11:02:51 UTC’de geçti. P1 kaynak doğruluğu, P2 konuşmacı ve anlamsal kabul açık. [Güncel kanıt](2026-09-17-word-boundary-gate.md). Aşağıdaki yayın notları kendi tarih/sürümlerine aittir.

> V4 offline paket / restore / API / PG / OCR / mobil: **PASS**, 17 Eylül 10:00:32 UTC. Kaynak ve konuşmacı kabulü açık; 828/321. [Kabul ve deney raporu](2026-09-17-restore-acl-and-source-triage.md).

> Güncel ek: V3 yetki sürümünde restore izin hatası bulundu, v4 düzeltmesi aynı gerçek yedekle yeni kurulumda API/PG ve mobil kabulünden geçti. 321 kaynak bölgesi hâlâ açık; yeni kırpım yöntemi ölçüm aşamasında, kaynak veya inceleme kararı değiştirilmedi. [Güncel hata ve kabul kaydı](2026-09-17-restore-acl-and-source-triage.md). Aşağıdaki önceki yayın özetleri tarihçedir.

> Son ek yayın: `upload-queue-v2-20260917` ana kurulumda. Yeni PDF yükleme, otomatik ağsız ayrıştırma, iptal ve yeniden takip gerçek kitapla geçti; 321 kaynak incelemesi/anlamsal kabul açık. Yeni yayının offline restore sonucu ayrıca izlenir. [Yükleme akışı ve kanıtlar](2026-09-17-upload-pipeline.md). Aşağıdaki önceki yayın kayıtları tarihçedir.

> 17 Eylül son güncelleme: `source-review-v2-r2-20260917` ile yeni nesil `b652f63c-6ec4-4f9a-aff4-00b32d220b1b` 48/48 tamamlandı; 828 anlaşma/321 inceleme, NEEDS_REVIEW. 371 yeniden okuma ve 15 ek OCR adayının kökeni korundu; veri elle değiştirilmedi. Kaynakta kutu ve aday görüntüleme dört genişlikte gerçek tarayıcı/API kontrolünden geçti. Son offline paket/import ve ayrı kuruluma geri yükleme 07:18:10 UTC itibarıyla geçti; geri yüklenen gerçek API/PG, OCR adayları ve 320/390/768/1440 px arayüz doğrulandı. Aşağıdaki v2 restore kayıtları tarihçedir. [Kod, ölçümler ve güncel kanıtlar](2026-09-17-source-v3.md).

17 Eylül 2026 güncellemesi. Kaynak: kullanıcının `Kitap_Analiz_Sistemi_Prod_Gelistirme_Plani.docx`, sürüm 1.1. Bu belge kabul sonucu değil, açık kapsam kaydıdır.

## Kabul yöntemi

**17 Eylül tarihsel analiz:** Nesil `14a79646-79c6-4cdb-8714-00adf5698770`,
iş `75b25439-09f5-425d-9e18-08cf15898d9a`; `source-spans-v5`.
48/48 sayfa, 821 kaynak anlaşması ve 328 inceleme bölgesi vardır.
V1 iptal edilip korundu. Yeni akışın sonu NEEDS_REVIEW; konuşmacı/semantik kabul
ve buna bağlı sentez/indeks/soru-cevap açık. CPU 48, model slotu **1**.
[Güncel sistem düzeltmeleri ve kanıtlar](2026-09-16-system-quality-followup.md).

Kitabı yalnız sunucudaki uygulama, OCR ve yerel modeller işler. Codex tarafından yazılan kitap içeriği, görsel açıklaması veya beklenen cevap model girdisine verilmez. Kaynakla bağımsız karşılaştırma çıktılar üretildikten sonra yapılır. Bir hatada genel kod/model/konfigürasyon düzeltilebilir; değişen sürüm yeniden doğrulanır. API/DB eşleşmesi anlamsal doğruluk anlamına gelmez.

Önceki `18c22ea1-35e8-4e49-b762-82b3320ed49c` neslinde 48 görsel model çıktısı oluştu. Codex kaynak karşılaştırmasından gelen ret kararları sonraki sahne girdisini filtrelediği için bu nesil müdahalesiz kabul sayılamaz. İçerik düzeltmesi API kayıt sayısı 0 olarak canlı doğrulandı. İnceleme kararları eski nesilde korunur; yeni nesil aynı özgün model çıktılarını, kendi kaynak kimlikleriyle ve inceleme kararı olmadan yeniden kullanır. Bu yeniden kullanım görsellerin tekrar üretilmesi olarak sayılmaz.

## P0–P7 gerçek çıkış durumu

| Paket | Durum | Kalan kabul |
|---|---|---|
| P0 Doğrulama | Ortam/model ölçümleri var; kapanmadı | Editör etiket emeği, tam görev başarısı ve birlikte yük |
| P1 Kaynak hattı | Üç gerçek kitabın 48/64/32 sayfalık kaynak hazırlaması doğrulandı; V14-r5 ana kitapta48 sayfa,896 anlaşma/253 inceleme | 253 kaynak incelemesi; yeni V15 tam koşusu, görsel doğruluk ve anlamsal kabul açık |
| P2 Karakter/olay | Metin atfı, sınırlı çapraz diyalog ve iki aşamalı anlam denetimi; V14-r5'te61 sınırlı uygun aday. V15 kaynak birimi kapsam muhasebesi kodu/pilotları hazır | Genel figür–karakter kimliği ve tam olay/sahne/anlam kabulü açık; V15 tam nesli henüz yok |
| P3 Edebî örnekler | Kabul bekliyor | P2, diğer kitapların gerçek kabulü ve editör rubriği |
| P4 Arama/cevap | V15 kaynak destekli pasaj/indeks ve editör soru taslağı canlı; ilk gerçek soru işi çalışıyor | Gerçek soru→indeks→cevap→mobil ve yeni vektörlerle restore kabulü; preview tam kitap/yayın kabulü değildir |
| P5 Editör akışı | Gerçek PDF yükleme/sürdürme, kaynak/OCR/bbox ve yetki ekranları var. Son webin kesin analiz kimliğine dönüşü ayrı gerçek64sayfa kitapta dört genişlikte geçti | Kaynak soru formunun gerçek uçtan uca kabulü; genel düzeltme ve bağımlılık yenileme kabulü |
| P6 İşletim | V14-r5 gerçek dolu restore/mobil06:08UTC'de geçti; V15 imaj/kod eşliği ve API/PG altyapı kontrolü geçti | Yeni V15 dolu restore, GPU internet kapalı soğuk açılış, kapasite ve farklı topoloji kabulü açık |
| P7 Pilot | Başlatılabilir kabul düzeyinde değil | P1–P6, ayrılmış örnekler ve insan üretim kararı |

## Planın tüm bölümleri

Son tamamlanmış kitap nesli V14-r5'tir:48 sayfa,1.149 kaynak bölgesi,896 anlaşma/253 inceleme; işleme tamamlanmış, tam anlamsal kabul verilmemiştir. Yeni V15 kaynağı henüz tam koşulmadı. Tarihsel V5/V6/V8 değerleri ve iptal edilen nesiller kendi kanıtlarında korunur; güncel ölçüm yerine kullanılmaz. [V14-r5 kabul](2026-09-18-source-analysis-v14-r5.md), [V15 güncel yayın](2026-09-18-source-analysis-v15.md).

| Bölüm | Mevcut kanıt / uygulama | Açık iş ve kabul sınırı |
|---|---|---|
| 1 Kapsam | Üç gerçek kitapta kaynak hazırlama: 48/64/32 sayfa | Aynı kitap klasöründe beş ek gerçek PDF bulundu; 64 ve 32 sayfalık iki ek kitabın gerçek API/PG/Poppler kaynak hazırlama kabulü geçti; ayrılmış anlamsal kabul seti henüz belirlenmedi |
| 2 Doğrulama evresi | Sunucu envanteri, kaynak hashleri, gerçek API/DB | Tam uçtan uca süre, görev başarısı, editör emeği ve kalan efor ölçümü açık |
| 3 Teknoloji | PostgreSQL, LangGraph, Qdrant, Docling, Poppler, Tesseract, yerel modeller; React kaynak inceleme, gerçek yükleme ve soru formu | Model görev uygunluğu ve yeni soru formunun gerçek uçtan uca kabulü açık; ekran yalnız salt okunur değildir |
| 4 Uçtan uca | V14-r5 48 sayfa işleme ve gerçek API/PG/restore/mobil kontrolü tamamlandı; V15 yayınlandı | Yeni V15 tam kaynak nesli ve soru→indeks→cevap kabulü açık; işleme bitişi anlamsal kabul değildir |
| 5 Dosya kabulü | Gerçek 19.806.912 bayt PDF, aynı hash, yarım yükleme reddi, idempotency | Otomatik yeni PDF ayrıştırma, kuyruk, iptal ve yeniden başlatma doğrulandı; bütün hata profilleri açık |
| 6 OCR/görsel | V14-r5 48/48; PDF/Paddle/Tesseract kelime geometrisi,1.149 span,896 anlaşma/253 inceleme | 253 bölge incelemesi; bağımsız CER/bölge doğruluğu ve görsel doğruluk kabulü açık |
| 7 Görsel bağlam | Kaynak/görsel API, 48 hash eşleşmesi ve gerçek sayfa/model adayını gösteren mobil ekran | Sahne eşleme kabulü, bölge/geçici kimlik ve görsel bağı düzenleme eksik |
| 8 Veri modeli | Sürümlü kaynak/generation/record/job/review/outbox | Planın ayrıntılı varlık sözleşmesine karşı tam eşleme kabulü açık |
| 9 İddia/zaman/bakış | Olay modu, fail, nesne, konuşmacı, bakış ve göreli zaman alanları | Alanların gerçek kitapta anlamsal doğruluğu bekleniyor |
| 10 Analiz | Karakter/olay ve sınırlı edebî sentez kodu | Gerçek çıktı, alternatif yorum ve editör rubriği kabulü açık |
| 11 İlişki | Kaynaklı ilişki kayıtları oluşturma kodu | Sözlük kapsamı ve yanlış akrabalık gibi regresyonların kabulü açık |
| 12 Kanıt/cevap | V15 yalnız kaynak denetiminden geçen pasajlarla arama/reranker, ayrı alıntı ve soru ilgisi kapısı; ilk gerçek preview sorusu çalışıyor | Yeni gerçek cevap/negatif soru/mobil kabulü açık; tarihsel13 soru yeni sürüm kabulü değildir |
| 13 Sürümler/düzeltme | Immutable kayıt, inceleme sürümü ve etkinleştirme kapısı | Genel düzeltme-bağımlılık yenileme ve gerçek ikinci baskı B18 eksik |
| 14 Kuyruk/checkpoint | Lease, fencing, SKIP LOCKED, gerekçeli retry; kayıtlar kesintide korundu | Tam hata/kesinti matrisi ve kullanıcı yükü kabulü açık |
| 15 Kapasite/maliyet | CPU/GPU görev ayrımı ve gerçek çağrı süre/token izleri; V15 gruplama için açık çağrı/karakter bütçeleri | Güncel tam kitap süresi, eşzamanlı yük, tepe kaynak, maliyet ve hizmet hedefi açık; eski sabit model sınırları güncel konfigürasyon sayılmaz |
| 16 Kalite/editör | B/V senaryoları ve bağımsız kaynak notları | Üç kitap, ayrılmış set, editör dakika/örnek ve uzlaşma ölçümü yok |
| 17 B01–B18 | Ayrı senaryo takip tablosu mevcut | Çalışan uygulamanın sonuçlarıyla tek tek kapatılacak; B18 kaynağı yok |
| 18 P0–P7 | Bağımlılık ve açık paketler bu tabloda görünür | Paketlerin hiçbiri yalnız kod bulunduğu için tamamlanmış sayılmaz |
| 19 API | Eser/baskı/yükleme/analiz/job/kaynak/görsel/inceleme/soru uçları | Bütün API sözleşmesi, request/run metadata ve genel correction kabulü açık |
| 20 İşletim/yetki | V14-r5 gerçek dolu yedek, ayrı restore/API-PG/mobil kontrolü geçti; V15 imaj/kod/API eşliği doğrulandı | Yeni V15 vektörleriyle restore, farklı kullanıcı/müşteri topolojileri, saklama/silme ve RPO/RTO kabulü açık |
| 21 Pilot/üretim | `pilot_ready=false`, insan onayı verilmedi | Üretim kararı verilemez; kritik kaynak hataları ve açık teknik koşullar var |
| 22 Kaynaklar | Analiz belgesinin teknik referansları | Referans belgeleri gerçek ürün kabulünün yerine geçmez |

## 16 Eylül tarihsel kalite değerlendirmesi

Aşağıdaki caption/sahne koşuları ve restore bekleme notları tarihsel kayıttır; 17 Eylül v2 sonucu yukarıdadır. İptal edilen caption nesli `6fffd7ed-f0c6-4de5-af1b-1ebea8898c8b` güncel kabul nesli değildir.

Gerçek React ekranı 320/390/768/1440 px sunucu Chrome tarayıcısıyla kontrol edildi:
altı sekmede yatay taşma yok, kontroller en az 44px, kaynak sayfası geçişi ve
çıkış doğrulandı. Kitap/analiz listesi bağımsız PostgreSQL ile eşleşti. İlk
dağıtımda yanlış JavaScript MIME türü bulundu; nginx MIME yapılandırması ve
dosya bind mount yenilemesi sonrası aynı tarayıcı koşusu geçti. Ekran salt
okunurdur; kullanıcı/rol, yükleme ve editör karar akışları tamamlandı sayılmaz.

Sahne kartının kişi/olay adayları gerçek API ile karşılaştırıldı; dört genişlikte
açılan kartın kaynak bağlantısı doğru PDF sayfasına döndü. Soru cevabının
kısmi/yetersiz kaynak durumu ve sınırlamaları görünürdür; dolu cevaplarla kabulü
henüz beklenir. Gateway yeniden oluşturulurken takip betiğinde gerçek
`ConnectionResetError` görüldü. İşçi çalışmayı sürdürdü; bağlantı kesilmeleri
için sınırlı retry eklendi ve takip yeniden başlatıldı, önceki hata saklandı.

Yedek betiği artık kitap kayıtlarının ve bütün artifact dosyalarının hashlerini
alır; restore bunları işçiyi başlatmadan karşılaştırır. Gerçek sunucudan
340 dosya/207.058.811 bayt ve 8 tablo için referans üretildi. Bu, dolu kitabın
yeni kuruluma geri dönmesiyle aynı kabul değildir; tam restore hâlâ bekleniyor.

Yeni müdahalesiz koşuda PDF 6 için model 155,116 saniyede çıktı verdi. Açık gözlü çizimi “uyuyan” diye niteledi ve “mavi gözlü” ayrıntısı ekledi. Özgün render ile karşılaştırma bu ifadeleri desteklemiyor. Bu bir görsel doğruluk başarısızlığıdır; kaynak metni veya model kaydı düzeltilmedi, yeni nesle review kararı verilmedi. Hatanın sahne/cevaplara etkisi henüz değerlendirilmedi. Bu tek örnek genel doğruluk yüzdesi değildir.

Yeniden kullanılan 38 görselin 13'ü önceki nesilde kaynak karşılaştırmasında
reddedilmişti. Canlı DB'de hem açıklama hem render hash'i eşitliği doğrulandı:
PDF 11, 13, 15, 16, 18, 19, 20, 23, 24, 25, 26, 27, 28. Dolayısıyla eski
bulgular aynı çıktılar için geçerliliğini koruyor; bu sayfalar yeni koşuda
düzeltilmiş sayılmaz. Örneğin PDF 28'de “Nihayet” kişi adı yapılmış; özgün
sayfa ve güncel API çıktısı yeniden karşılaştırıldı. PDF 6 ile birlikte en az
14 sayfada bilinen görsel hata var. Bu sayı eksiksiz kör değerlendirme veya
genel doğruluk oranı değildir; yeni nesle karar/düzeltme yazılmadı.
Kanıt: `evidence/unassisted-reused-visual-findings.json`.

Kaynak bütünlüğü ve izlenebilir işlem kayıtları olumlu. Modelin görsel okuması güvenilir kabul edilecek düzeyde gösterilemedi: yanlış konuşmacı, yazı, nesne ve ayrıntı örnekleri var. 48/48 işleme yalnız kapsama işaret eder. Yeni koşu, bu hataların sonraki analiz ve cevaplara taşınıp taşınmadığını gösterecek. Henüz bir başarı yüzdesi veya üretime hazırlık iddiası yoktur.

Gerçek ikinci baskı ve yayınevi editör zamanı dış girdidir. Aynı klasörde ek gerçek kitap dosyaları bulundu; iki kitabın kaynak hazırlaması gerçek API/PG ile geçti, anlamsal kabul yerine sayılmaz. Tahminle veya yapay örnekle tamamlanmış gösterilmez. Ön yüzsüz API koşusu mobil arayüz kabulü değildir. Önceki temel kurulumun restore kanıtı güncel analiz sürümüne otomatik taşınmaz.

## 16 Eylül eski koşuda ölçülen çalışma darboğazı

İlk künye grubu çağrısı 758,808 saniye sürdü; bu çağrı duvar süresidir, CPU saati veya tüm kitabın toplam süresi değildir. Üç dört-sayfalık sahne çağrısı 1800 çıktı token sınırına ulaştı; kesilmiş çıktı kabul edilmeyerek otomatik bölündü. Tekrar maliyetini azaltmak için sahne bütçesi 3600’e çıkarıldı; 8192 toplam bağlam kontrolü korunuyor. Aynı iş ikinci denemede, eski tamamlanan kayıtları koruyarak devam ediyor. Bu hata ve yeniden deneme toplam kullanıcı süresinden çıkarılmaz.

Yeni bütçeyle PDF 9–12 grubu 1916 çıktı token / 1298,808 saniyede,
PDF 13–16 grubu 1421,361 saniyede tamamlandı. İlk anlatı grubunda görsel
adayın yanlış sayfa etiketi kaynak tutarsızlığı olasılığına dönüştürülmüş;
model hatasının sonraki analize taşınması gözlendi. PDF 16 etkinliği ise
ACTIVITY olarak ayrılmış ve hikâye olaylarına eklenmemiş. Bunlar ara sahne
bulgularıdır; destek kontrolü ve bütün-kitap kabulü henüz bitmedi.

15:58:38–16:58:46 UTC arasındaki 112 örnekte LLM ortalama 46,354 mantıksal
CPU, örneklenmiş tepe 22,49 GiB RAM kullandı. Bu zaman aralığı toplam kitap
süresi değildir. 8076/8078 sağlık uçlarında 110'ar örnekte hata görülmedi;
8795 için 110 örneğin 12'sinde URLError vardı. Systemd günlükleri bu
aralıklarda BI köprüsünün durdurulup yeniden başlatıldığını gösteriyor.
Nedensellik veya ortak yük SLO kabulü çıkarılamaz. Ölçüm özeti
`scripts/summarize-book-resources.py <job_id>` ile gerçek JSONL'den üretilir.
