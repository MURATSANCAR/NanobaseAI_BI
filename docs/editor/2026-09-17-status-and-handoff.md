# Editör — yapılan işler ve doğrulanmış son durum

> 17 Eylül son güncelleme: `source-review-v2-r2-20260917` ile yeni nesil `b652f63c-6ec4-4f9a-aff4-00b32d220b1b` 48/48 tamamlandı; 828 anlaşma/321 inceleme, NEEDS_REVIEW. 371 yeniden okuma ve 15 ek OCR adayının kökeni korundu; veri elle değiştirilmedi. Kaynakta kutu ve aday görüntüleme dört genişlikte gerçek tarayıcı/API kontrolünden geçti. Son offline paket/import ve ayrı kuruluma geri yükleme 07:18:10 UTC itibarıyla geçti; geri yüklenen gerçek API/PG, OCR adayları ve 320/390/768/1440 px arayüz doğrulandı. Aşağıdaki v2 restore kayıtları tarihçedir. [Kod, ölçümler ve güncel kanıtlar](2026-09-17-source-v3.md).

17 Eylül sonraki yayın: [Kaynak inceleme API ve balon–figür aday bağlantısı](2026-09-17-source-review.md). Aşağıdaki v2 işleme/restore sonucu korunur; yeni inceleme API’sinin ek kabulü bağlantılı kayıttadır.

17 Eylül 2026 tarihinde gerçek sunucudaki API ve kanıt dosyaları yeniden okundu. Bu belge güncel durum kaydıdır; 16 Eylül tarihli belgeler kendi tarihlerinin uygulama ve deney geçmişini korur.

## Sonuç: işleme tamamlandı, anlamsal kabul açık

| Ölçüm | Gerçek sonuç |
|---|---|
| İş | `0d53b03d-67e5-44c4-b523-bf9a2aa56ac2` — `COMPLETED`, hata kodu yok |
| Nesil | `a9471749-7447-4826-b003-f25e53943763` — `NEEDS_REVIEW` |
| Kaynak kapsamı | 48/48 sayfa |
| Konumlu metin | 1.149 `source_spans`; 778 okuyucu anlaşması, 371 inceleme gerektiren bölge |
| Sayfa kayıtları | `evidence`, `page_readings`, `layout_regions`, `visual_observations`, `page_claims`, `page_checks`: her türde 48 kayıt |
| Bağımsız kayıt karşılaştırması | 48 sayfanın altı türe ait API/PG karşılaştırması geçti |
| Müdahale | Bu nesilde manuel review 0, kaynak düzeltmesi 0, eski `visuals.description` kaydı 0 |
| Paket ve geri yükleme | Offline export/import, gerçek kitap yedeği, ayrı kuruluma restore, restore sonrası API/PG ve mobil ekran kontrolü geçti |
| Ürün kabulü | `semantic_acceptance=false`; sentez, arama ve soru kalitesi **DOĞRULANAMADI** |

778 anlaşma doğruluk oranı değildir: okuyucular aynı yanlışı yapabilir. 48 `page_claims` kaydı, 48 doğrulanmış iddia anlamına gelmez; bunlar sayfa adaylarını taşıyan kayıtlardır. İşin bitmesi nesli yayımlanabilir yapmaz. Konuşmacılar UNKNOWN, adayların senteze uygunluğu kapalıdır.

## Mimari ve kurulum

Editör `apps/editor/` altında kendi frontend/backend, bağımlılık, migration, Docker ve yapılandırmasıyla bağımsız uygulamadır. BI iç kodu veya tabloları kullanılmaz; BI ekran bağlantısı ileride API sözleşmeleriyle yapılacaktır. Kalıcı dal `main`dir.

Sunucu `nanobase-direct`, kurulum `/data/nanobaseai/editor`, Compose projesi `nanobase-editor`. API/web `127.0.0.1:8810`, Prometheus `127.0.0.1:9096`; özel ağlar `10.203.48.0/24` ve `10.203.49.0/24`. PostgreSQL, Qdrant, API, worker, OCR, LLM, embedding, reranker, Prometheus ve gateway ayrı servislerdir. Belge araçları ağsız Docling/Poppler/Tesseract konteynerindedir. Sırlar paket ve Git dışında tutulur; DB uygulama rolü superuser değildir.

CPU sunucusunda 96 mantıksal CPU ve 251 GiB RAM bulunur; GPU kullanılmaz. Son koşuda Qwen3.8-27B Q4_K_M + Q8 projektör, 48 CPU/thread, **tek slot**, 8192 bağlam ve 1024 görsel token kullanıldı. Embedding/reranker dörder CPU kullanır. Bu profil genel müşteri performans taahhüdü değildir.

PaddleOCR/PaddlePaddle 3.2.0, PP-OCRv5 mobile detector ve Latin recognizer ana Compose servisine alındı. OCR dört CPU/4 GiB ile özel ağda, salt okunur dosya sistemi üzerinde çalışır. Ağırlıklar ve revision/hash manifesti imaj içindedir; çalışma anında indirme gerekmez. `compose.ocr.yaml` eski komutlar için boş uyumluluk katmanıdır.

## Kaynak ve sürüm kimlikleri

- Plan: `Kitap_Analiz_Sistemi_Prod_Gelistirme_Plani.docx`, v1.1; SHA-256 `7e36c21343abadacbb7c1f62276bf9ac7c20d5eb3b51030695f092690b898976`.
- Gerçek PDF: *Ekrana Sığmayan Macera İç Baskı*, 48 sayfa, 19.806.912 bayt; SHA-256 `94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50`.
- Kaynak içerik sürümü: `3970f5b9-769a-4fe9-8032-379834fa6831`.
- Yayın: `source-spans-v2-6f14bb9`; genel eşleştirme düzeltmesi commit `6f14bb9`.
- API/worker imajı: `sha256:67226135f7620aa2cdd1639543700ff3dfcc42beab8248d38c490caf514e71b2`.
- Backend 26 dosya ağaç hash'i: `58004e5a5043d27508c12aa370ef81d92d97d08778abf2c7cc1b9b5a934fe2ef`.
- OCR imajı: `sha256:4e69a4268296fc59285a5c137ebb411c78fe4ed00a23a5486e4671fd700f1deb`.
- Web imajı: `sha256:1aea10ffc58e763e7ed27865c2ff5f1451fe9b5e5c574234da65f27fc0c29957`.

Özgün PDF, render, Docling, PDF kelime kutuları ve Tesseract çıktıları artifact alanında korunur. Kitap metni, görüntüler, sırlar ve özel kanıt dosyaları Git'e eklenmez.

## Hatalar ve sistemde yapılan düzeltmeler

1. **Betimlemenin metin sanılması:** Eski tam sayfa VLM betimlemelerinde yanlış konuşmacı, olumsuzluk ve kişi adayı görüldü. Yeni akışta PDF/OCR yazıyı, ayrı görsel gözlemler çizimi temsil eder. Doğrulanmamış serbest görsel betimleme iddia girdisi olamaz.
2. **OCR bölgesinin bütün satırla karşılaştırılması:** `backend/editor/source_alignment.py` kelime geometrisi üzerinden bağımsız PDF/Tesseract eşini seçer. Sayı, koordinat, kutu boyutu ve sınır kontrolleri vardır. S.16 gerçek tekrarında 1/56 yerine 46/56 anlaşma elde edildi; ham Paddle metni değiştirilmedi, 10 uyuşmazlık korundu.
3. **Alıntıda eksik veya kesintili kanıt:** Türkçe harf normalleştirme, kelime sınırı, yinelenen referans, sıra ve kesintisizlik kontrolü eklendi. Atlanan doğrulanmamış bölgeler `[UNVERIFIED_REGION]` olarak korunur. İlk 18 sayfanın 46 adayında 31 eşleşme, 4 kesintili kaynak, 11 uyuşmazlık görüldü; eşleşme anlamsal kabul değildir.
4. **Kırpılmış satırın yeniden algılanması:** OCR bölge kırpmaları doğrudan tanıma modeline gider. İlk 128 bölge yeniden okunur; sınır aşımı açıkça raporlanır. Sağlık uçları uzun OCR işinden ayrıldı; tek OCR kapasitesi doluyken 429 döner.
5. **Sürüm karışması:** V1 işi API üzerinden iptal edildi, eski kayıtlar korundu. V2 yeni nesilde çalıştı. İlk 18 sayfanın ham makine ölçümleri kaynak hash/köken kontrolüyle yeniden kullanılabildi; eski review veya türetilmiş iddialar taşınmadı. Yeniden kullanılan görsel gözlem yeni model çağrısı sayılmaz.
6. **Paket taşınabilirliği:** Paketleyici özel `.env`, sır, evidence, kitap ve geliştirme bağımlılıklarını dışlar; `.env.example` korunur. Paket hedefinin kaynak içine girip özyinelemeli kopya oluşturması engellendi. Offline imaj kimlikleri ve dosya hashleri doğrulanır.
7. **Gözetimsiz takip:** Kilitli tek süreç, 20 saniyelik durum takibi, her 10 sayfada ve terminal durumda gerçek API/PG denetimi eklendi. Kurulum denetçisi belirli nesli bekleyip tutarlı yedek ve ayrı restore kontrolü yaptı. Bunlar sürekli kod düzelten veya editör kararı üreten ajanlar değildir.

Her sayfa kaynak okuma → görsel gözlem → iddia adayı → sayfa kontrolü sırasıyla işlendi. En fazla dört iddia adayı ve sınırlı görsel kırpma gibi kapsam sınırları sürer; tam anlamsal çıkarım iddia edilmez. Çok sütunlu okuma sırası ve konuşmacı çözümü ayrıca kabul gerektirir.

## Gerçek ortam doğrulamaları

`verify-source-pipeline.py` gerçek API sonucunu bağımsız PostgreSQL kayıtlarıyla karşılaştırdı; son kontrol `2026-09-17T01:52:22.680111+00:00`. 48 sayfada metin, yerleşim, okuma, görsel gözlem, aday ve kontrol kayıtları eşleşti. Kaynak/render hashleri ve konum sınırları denetlendi. API/DB eşliği depolama/taşıma doğruluğunu gösterir; kaynak anlamının doğruluğunu göstermez.

`verify-publication-gates.py` gerçek API'de yetkisiz isteğin 401, hazır olmayan nesle soru ve etkinleştirme isteklerinin 409 verdiğini kontrol etti; yeni soru/review yazılmadı. `verify-release.py` çalışan 26 backend dosyasını, `verify-isolation.py` servis izolasyonunu kontrol etti.

S.38 ayrı sınırlı OCR tekrarında 24 bölgenin 20'si anlaştı ve kritik olumsuzluk korundu (33,016 saniye). Son tam koşuda da s.38 için 24/20/4 kaynak bölgesi kaydedildi. Bu sayfanın konuşmacı ve anlamsal kabulü bundan çıkarılamaz. Eski Tesseract da ilgili olumsuzluğu koruyordu; hata yalnız OCR eksikliği değildi.

React ekranı gerçek API ile salt okunur çalışır. Gerçek sunucu Chrome kontrolünde 320/390/768/1440 px, altı sekme ve genişletilmiş kaynak kaydı doğrulandı. Restore ortamında mobil kontrol tekrar geçti. Rol yönetimi, yükleme, editör karar/düzeltme ve PDF.js/bbox düzenleme ekranları tamamlanmadı.

## Offline paket ve gerçek restore sonucu

Denetim kökü: `/data/nanobaseai/editor-qualifications/a9471749`. Offline paket 8 imaj, 94 dosya ve dört GGUF içerir; OCR ağırlıkları imajdadır. Paket kitap ve sır içermez; **ayrı alınan özel yedek gerçek kitabı içerir**.

| Adım | Tamamlanma zamanı (UTC, 17 Eylül; paket 16 Eylül) |
|---|---|
| Offline export/import | 16 Eylül 20:19:50 |
| Tamamlanmış kaynak API/PG denetimi | 01:52:21 |
| Koşu sonrası backend eşliği ve izolasyon | 01:52:23 |
| Gerçek yedek | 01:52:44 |
| Ayrı kurulumda restore | 01:54:29 |
| Restore sonrası gerçek API/PG | 01:55:48 |
| Restore sonrası mobil tarayıcı | 01:56:09 |
| Denetim hedefini durdurma | 01:56:12 |

Hedef `editor-qualification-a9471749`, ayrı volume/sırlarla, 18810/19096 portlarında ve `10.203.50.0/24`–`10.203.51.0/24` ağlarında doğrulandı. Kontrol sonunda hedef servisler durduruldu; kanıt ve veriler korundu. Kaynak kurulum ezilmedi. Aynı Linux hostundaki ayrı kurulum kabulü, bütün müşteri işletim sistemleri, VPN topolojileri, kapasite veya yüksek erişilebilirlik garantisi değildir.

## Kanıtların yeri ve işletim

Kaynak kurulumun `evidence/` dizininde:

- `source-spans-run.json`: nesil/iş kimlikleri; başka nesle ait eski varsayılanlarla karıştırılmamalı.
- `source-pages-status.md`, `source-pages-v2-follow.log`: tarihli ilerleme/terminal kayıtları.
- `source-spans-verification.json`: 48 sayfanın kayıt eşliği ve toplamları.
- `source-alignment-comparison.json`, `source-gates-v2-replay.json`: genel kod düzeltmesi karşılaştırmaları.
- `publication-gates.json`: soru/yayın blokajları.
- `installation-qualification-status.md`: paket/restore adımları.

Denetim kökündeki `qualification.json`, adım günlükleri, `offline/`, `backup/`, `installation/` ayrı kurulumun kanıtlarıdır. Canlı API durum okuması ve bu dosyalar 17 Eylül dokümantasyon turunda kontrol edildi; yeni kitap koşusu veya yerel ürün testi başlatılmadı.

## Açık işler ve sonraki kabul

- 371 uyuşmayan bölgenin nedenlerini genel OCR/yerleşim kodunda çözmek; eski veriyi elle düzeltmeden yeni nesilde tekrar doğrulamak.
- Balon/kuyruk ve figür bağını bağımsız sinyallerle doğrulamak; belirsiz konuşmacıyı UNKNOWN tutmak.
- S.6 görsel durum, s.29 konuşmacı, s.38 olumsuzluk, “Nihayet” varlık ayrımı ve etkinlik/olay ayrımını kaynak üzerinden anlamsal regresyonda kapatmak. Beklenen cevaplar model girdisine taşınamaz.
- Kaynak kabulünden sonra karakter/olay/ilişki/sentez, indeks ve gerçek soruları uçtan uca doğrulamak; B01–B18/V01–V08'i tek tek kanıtla kapatmak.
- Genel yeni PDF ayrıştırma/yükleme, çok kullanıcılı kitap/rol yetkisi, düzeltme bağımlılıkları, ikinci baskı, saklama/silme, yük/kesinti ve RPO/RTO kabulünü tamamlamak.
- Planın diğer iki gerçek kitabı, değişmiş ikinci baskısı ve insan editör süreleri henüz yok; yapay veriyle tamamlandı sayılmaz.

## Belge haritası

- [Kurulum ve komutlar](../../apps/editor/README.md)
- [OCR sözleşmesi](../../apps/editor/ocr/README.md)
- [Ön yüz ve mobil kontrol](../../apps/editor/frontend/README.md)
- [22 bölümlük roadmap](roadmap-live-status.md)
- [B01–B18/V01–V08 kabul defteri](reference-book-acceptance.md)
- [İlk altyapı](2026-09-16-infrastructure.md), [OCR pilotu](2026-09-16-ocr-page-pilot.md), [v1 kaynak akışı](2026-09-16-source-spans.md), [v2 kod düzeltmeleri](2026-09-16-system-quality-followup.md)

Geçmiş raporlardaki bekleyen işler ve farklı nesil/imaj sayıları kendi tarihleri içindir. Güncel durum yukarıdaki v2 nesline aittir. Önceki GitHub gönderimleri HTTPS kimliği bulunamadığı için başarısızdı; yerel commit ile origin yayını aynı kabul edilmez.
