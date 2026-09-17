# Editör: roadmap kapsamı ve gerçek koşu durumu

> Güncel v5: `text-attribution-v5-20260917`, ana nesil `14a79646` 48/48; 10 açık metin atfı, 0 claim-speaker. Gerçek API/PG, mobil atıf/kutu ve sekiz kesilen-yükleme kabulü geçti. Kaynak 821/328; figür kimliği ve anlamsal kabul açık. [Güncel kayıt](2026-09-17-text-attribution.md).

> Önceki yayın `source-boundaries-v4-r2-20260917`: kelime sınırı hatası kodda düzeltildi, eski neslin gerçek API/PG tekrarında 7 yanlış eşlik kaldırıldı (821/328). Yeni nesil `99881d8f` 48/48 tamamlandı; 821/328, geçersiz kaynaktan geçen aday 0, yeni aday model çağrısı 0. Gerçek API/PG ve kaynak/yayın kontrolleri geçti; offline/restore kabulü 17 Eylül 11:02:51 UTC’de geçti. P1 kaynak doğruluğu, P2 konuşmacı ve anlamsal kabul açık. [Güncel kanıt](2026-09-17-word-boundary-gate.md). Aşağıdaki yayın notları kendi tarih/sürümlerine aittir.

> V4 offline paket / restore / API / PG / OCR / mobil: **PASS**, 17 Eylül 10:00:32 UTC. Kaynak ve konuşmacı kabulü açık; 828/321. [Kabul ve deney raporu](2026-09-17-restore-acl-and-source-triage.md).

> Güncel ek: V3 yetki sürümünde restore izin hatası bulundu, v4 düzeltmesi aynı gerçek yedekle yeni kurulumda API/PG ve mobil kabulünden geçti. 321 kaynak bölgesi hâlâ açık; yeni kırpım yöntemi ölçüm aşamasında, kaynak veya inceleme kararı değiştirilmedi. [Güncel hata ve kabul kaydı](2026-09-17-restore-acl-and-source-triage.md). Aşağıdaki önceki yayın özetleri tarihçedir.

> Son ek yayın: `upload-queue-v2-20260917` ana kurulumda. Yeni PDF yükleme, otomatik ağsız ayrıştırma, iptal ve yeniden takip gerçek kitapla geçti; 321 kaynak incelemesi/anlamsal kabul açık. Yeni yayının offline restore sonucu ayrıca izlenir. [Yükleme akışı ve kanıtlar](2026-09-17-upload-pipeline.md). Aşağıdaki önceki yayın kayıtları tarihçedir.

> 17 Eylül son güncelleme: `source-review-v2-r2-20260917` ile yeni nesil `b652f63c-6ec4-4f9a-aff4-00b32d220b1b` 48/48 tamamlandı; 828 anlaşma/321 inceleme, NEEDS_REVIEW. 371 yeniden okuma ve 15 ek OCR adayının kökeni korundu; veri elle değiştirilmedi. Kaynakta kutu ve aday görüntüleme dört genişlikte gerçek tarayıcı/API kontrolünden geçti. Son offline paket/import ve ayrı kuruluma geri yükleme 07:18:10 UTC itibarıyla geçti; geri yüklenen gerçek API/PG, OCR adayları ve 320/390/768/1440 px arayüz doğrulandı. Aşağıdaki v2 restore kayıtları tarihçedir. [Kod, ölçümler ve güncel kanıtlar](2026-09-17-source-v3.md).

17 Eylül 2026 güncellemesi. Kaynak: kullanıcının `Kitap_Analiz_Sistemi_Prod_Gelistirme_Plani.docx`, sürüm 1.1. Bu belge kabul sonucu değil, açık kapsam kaydıdır.

## Kabul yöntemi

**Güncel analiz:** Canlı nesil `14a79646-79c6-4cdb-8714-00adf5698770`,
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
| P1 Kaynak hattı | Üç gerçek kitabın 48/64/32 sayfalık kaynak hazırlaması doğrulandı; ilk kitap kaynak paneli ve kelime sınırı kapısı çalışıyor | 328 kaynak bölgesi; görsel kaynak doğruluğu |
| P2 Karakter/olay | 10 kaynaklı metin atfı ve mobil kaynak bağlantısı doğrulandı; claim-speaker 0 | Konuşmacı/kimlik, olay modu ve sahne eşliği |
| P3 Edebî örnekler | Kabul bekliyor | P2, diğer kitapların gerçek kabulü ve editör rubriği |
| P4 Arama/cevap | Altyapı mevcut; bu nesilde kabul yok | Doğrulanmış iddialarla kaynaklı cevap |
| P5 Editör akışı | Kaynak/OCR/bbox ve yetki ekranları çalışıyor | Genel düzeltme ve bağımlılık yenileme kabulü |
| P6 İşletim | Kuyruk/yetki/offline/restore kontrolleri yürütüldü | V5 son paket kabulü, farklı kullanıcı/yük/topolojiler; v4-r2 offline kabulü geçti |
| P7 Pilot | Başlatılabilir kabul düzeyinde değil | P1–P6, ayrılmış örnekler ve insan üretim kararı |

## Planın tüm bölümleri

V5 işleme tamamlandı: 48 sayfa, 1.149 kaynak bölgesi, 821 anlaşma/328 inceleme, 10 açık metin atfı. İş COMPLETED; nesil NEEDS_REVIEW. Gerçek ana API/PG, kaynak/atıf ve mobil kontrolü geçti. V6 R2 sonuçları korunarak V7 ab85c397 koşusuna geçildi; ayrı API18810 kabulü sürüyor, ana sürüm sayılarıyla karıştırılmaz. [V5 kabul](2026-09-17-text-attribution.md), [V6 devam eden kabul](2026-09-17-regional-source-selection.md).

| Bölüm | Mevcut kanıt / uygulama | Açık iş ve kabul sınırı |
|---|---|---|
| 1 Kapsam | Üç gerçek kitapta kaynak hazırlama: 48/64/32 sayfa | Aynı kitap klasöründe beş ek gerçek PDF bulundu; 64 ve 32 sayfalık iki ek kitabın gerçek API/PG/Poppler kaynak hazırlama kabulü geçti; ayrılmış anlamsal kabul seti henüz belirlenmedi |
| 2 Doğrulama evresi | Sunucu envanteri, kaynak hashleri, gerçek API/DB | Tam uçtan uca süre, görev başarısı, editör emeği ve kalan efor ölçümü açık |
| 3 Teknoloji | PostgreSQL, LangGraph, Qdrant, Docling, Poppler, Tesseract, yerel modeller ve salt okunur React ekranı | Model görev uygunluğu kabul edilmedi; bbox/OCR inceleme ekranı doğrulandı; PDF.js özel görüntüleyici ve anlamsal kabul kapsamı ayrıca açık |
| 4 Uçtan uca | 48 kaynak/okuma/görsel aday/kontrol kaydı; v2 iş COMPLETED | NEEDS_REVIEW; doğrulanmış sahne → sentez → indeks → cevap kabulü açık |
| 5 Dosya kabulü | Gerçek 19.806.912 bayt PDF, aynı hash, yarım yükleme reddi, idempotency | Otomatik yeni PDF ayrıştırma, kuyruk, iptal ve yeniden başlatma doğrulandı; bütün hata profilleri açık |
| 6 OCR/görsel | 48/48; PDF/Paddle/Tesseract kelime geometrisi, 1.149 span, 821 anlaşma/328 inceleme | CER ve bölge doğruluğu ölçülmedi; görsel adaylarda gerçek yanlışlar var |
| 7 Görsel bağlam | Kaynak/görsel API, 48 hash eşleşmesi ve gerçek sayfa/model adayını gösteren mobil ekran | Sahne eşleme kabulü, bölge/geçici kimlik ve görsel bağı düzenleme eksik |
| 8 Veri modeli | Sürümlü kaynak/generation/record/job/review/outbox | Planın ayrıntılı varlık sözleşmesine karşı tam eşleme kabulü açık |
| 9 İddia/zaman/bakış | Olay modu, fail, nesne, konuşmacı, bakış ve göreli zaman alanları | Alanların gerçek kitapta anlamsal doğruluğu bekleniyor |
| 10 Analiz | Karakter/olay ve sınırlı edebî sentez kodu | Gerçek çıktı, alternatif yorum ve editör rubriği kabulü açık |
| 11 İlişki | Kaynaklı ilişki kayıtları oluşturma kodu | Sözlük kapsamı ve yanlış akrabalık gibi regresyonların kabulü açık |
| 12 Kanıt/cevap | Hybrid arama, reranker, kapsam/atıf kimliği denetimi | 13 gerçek soru; destek, yeterlilik ve kapsama göre bağımsız değerlendirme bekleniyor |
| 13 Sürümler/düzeltme | Immutable kayıt, inceleme sürümü ve etkinleştirme kapısı | Genel düzeltme-bağımlılık yenileme ve gerçek ikinci baskı B18 eksik |
| 14 Kuyruk/checkpoint | Lease, fencing, SKIP LOCKED, gerekçeli retry; kayıtlar kesintide korundu | Tam hata/kesinti matrisi ve kullanıcı yükü kabulü açık |
| 15 Kapasite/maliyet | 48 CPU, tek model slotu, 8192 bağlam/1024 görsel token; çağrı izleri | Tam kitap süresi, tepe kaynak, maliyet ve hizmet hedefi açık |
| 16 Kalite/editör | B/V senaryoları ve bağımsız kaynak notları | Üç kitap, ayrılmış set, editör dakika/örnek ve uzlaşma ölçümü yok |
| 17 B01–B18 | Ayrı senaryo takip tablosu mevcut | Çalışan uygulamanın sonuçlarıyla tek tek kapatılacak; B18 kaynağı yok |
| 18 P0–P7 | Bağımlılık ve açık paketler bu tabloda görünür | Paketlerin hiçbiri yalnız kod bulunduğu için tamamlanmış sayılmaz |
| 19 API | Eser/baskı/yükleme/analiz/job/kaynak/görsel/inceleme/soru uçları | Bütün API sözleşmesi, request/run metadata ve genel correction kabulü açık |
| 20 İşletim/yetki | V2 offline paket, gerçek tam kitap yedeği, ayrı restore/API-PG/mobil kontrolü geçti | Kullanıcı/kitap yetkisi gerçek sınırlı anahtarlarla geçti; farklı gerçek kullanıcı matrisi, müşteri topolojileri, saklama/silme ve RPO/RTO kabulü açık |
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
