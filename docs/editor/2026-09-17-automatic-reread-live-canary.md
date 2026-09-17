# V10 otomatik kaynak okuma — gerçek izole DB canary

## Ortam ve izolasyon

Gerçek staging `editor` PostgreSQL veritabanı özel izinli pg_dump/pg_restore ile **`editor_reread_v10_20260917`** veritabanına kopyalandı. Başlangıçta 9.914 kayıt, 11 içerik sürümü, 16 iş vardı. Kaynak PDF ve ölçüm artefaktları gerçek kaynak volume'undan okundu; kaynak/konuşmacı/inceleme verisi elle düzeltilmedi.

- Sunucu kurulum kökü: `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation`.
- Aday API: yalnız `127.0.0.1:18811`, `reread-canary-api`.
- Aday worker: `reread-canary-worker`, DB seçimi `EDITOR_DB_NAME=editor_reread_v10_20260917`.
- Clone'a kopyalanan tek aktif iş worker başlamadan aday ürün API'siyle iptal edildi. Kaynak staging API/worker yeniden oluşturulmadı.
- Runtime image: `nanobase-editor:auto-reread-v10-r2-20260917`, ID `sha256:319280eb90b79fe6e0528dbd1d0368f885bd2062875794c3ffcc2c11c655303d`.
- Consumer image: `nanobase-editor-document:auto-reread-v10-r2-20260917`, ID `sha256:f8e3cbc55334dd82f7dac9b6c8ca76650b32289815dfd02a3791c14bb9d730b4`.
- R2 helper kod SHA256: `c4073fe5748cff67a1d5b64abab1cd621e0792dd6017b580b61a7da3ca906b4e`.
- Runtime/consumer dışında mevcut LLM modeli veya image değiştirilmedi.

## R2 bileşen kontrolü

Yeni helper'da 61 gerçek bölge bileşen kabulü **14:55:56 UTC PASS**. Kanıt: `evidence/reread-queue-component-20260917T145556Z.json`.

İlk deneme eski verifier'ın `attempt_token=None` çağrısının mevcut legacy `page-NNNN.json` ile yeni kod isteğini karşılaştırması nedeniyle `REREAD_IMMUTABLE_CONFLICT` ile durdu. Eski ölçüm silinmedi. Verifier üretim entegrasyonundaki `attempt_token=1` sözleşmesine uyarlandı; request-scoped yol üzerinde bütün 61 bölge yeniden doğrulandı. Verifier SHA256 `3c5003f6bdea42938a6b61956bb1849aac4e7172ae7b29b3638ae4a0066ed30e`.

## İlk canary hatası ve gerçek neden

İlk iş `e05426a5-b0b9-424a-a8dc-7bef5a99bd18`, nesil `2088d1bb-e8b7-4724-bbfb-523aa30f9fbf` 64 kaynak evidence kaydından sonra **FAILED / ConnectError** oldu. Henüz optical sayfa kaydı yoktu.

Gerçek neden: bağımsız staging kurulumunda `ocr` servisi çalışmıyordu. Canary API konteynerinden `ocr` DNS çözümlemesi başarısızdı. Önceki yeniden kullanılan ölçüm koşuları taze Paddle çağrısına ihtiyaç duymadığı için bu eksiklik görünmemişti. Yalnız staging `ocr` servisi `up -d --no-deps ocr` ile başlatıldı; aday API içinden `http://ocr:8080/health` başarılı doğrulandı. Kitap verisi ve model ayarı değiştirilmedi.

Başarısız nesil korundu. Verifier'ın açık `--retry-failed` seçeneği, önceki işlerin yalnız FAILED/CANCELLED ve önceki optical kayıt sayısının sıfır olduğu doğrulanınca yeni nesil açar; aynı eski veriyi düzeltmez. İlk kanıt `evidence/automatic-reread-editor_reread_v10_20260917-56d7d123-cfef-4bc4-8334-f9acf5103883-failed-20260917T194554Z.json` dosyasında korunur.

Canary API'nin ilk private-only ağından host portuna erişilememe kurulum sorunu da yalnız aday servise mevcut ingress ağı eklenerek düzeltildi; yayın adresi localhost kaldı. Bu denemeler müşteri paketi veya tüm kurulum topolojilerinin kabulü değildir.

## Gerçek yeni kitapta otomatik optical kabulü

**17 Eylül 19:46:50 UTC PASS**, 56,122 saniye:

- Kitap: gerçek 64 sayfalık *Kahramanını Yutan Kitap*.
- İçerik sürümü: `56d7d123-cfef-4bc4-8334-f9acf5103883`.
- Öncelik sayfası: 9; gerçek native PDF'de 150 temiz kelime/835 karakter bulunduğu için boş olmayan kaynak kontrolü olarak seçildi. Beklenen cevap verilmedi.
- İş: `6c4a4b3f-e65b-4075-b38d-ffdd68be4453`.
- Nesil: `958298fd-f022-4871-974c-4ce39fdc21f1`, `source-spans-v10`, **reuse_measurements_from=null**.
- 9. sayfa: **33 kaynak spanı, 14 otomatik yeni PSM 7/13 ölçümü**.
- `region_rereads` gerçek iş ilerlemesi gözlendi; request `c407617a-ee00-5c1c-b5e5-7628a09db093`.
- Kaynak/evidence/page_readings gerçek API JSON'u bağımsız clone PostgreSQL sonuçlarıyla eşit.
- Orijinal PDF SHA256 önce/sonra `fbbead4dca9a3a1b7b6e515f3df791460895cb91bdbb4f1fec74fa67ce212c73`.
- Yeni ölçüm provenance'ları ortak helper ile doğrulandı; aynı renderdan bağımsız crop yeniden üretimi ve ham TSV hash/metin/güven kıyası eşit. Request regions yalnız gerçek span kimliği ve bbox içerir; kaynak cevabı içermez.
- Önceki DB kayıtları, içerik sürümü ve incelemeler değişmedi. Yeni iş/nesil/ölçümler normal ürün akışıyla oluştu.

Kanıt: `evidence/automatic-reread-editor_reread_v10_20260917-56d7d123-cfef-4bc4-8334-f9acf5103883.json`. Koşulan verifier SHA256: `ccf82c20248271a5019adc737bd6544ba505503f79f531a1547aeacd681b299b`.

## Durma ve kabul sınırı

İlk optical sayfa tamamlandığında API cancellation istendi ve yalnız canary worker durduruldu. Yarış penceresinde bir `visual_observations` kaydı oluşmuştu; **model çağrısı hiç başlamadı denmiyor**. Rapor anında iş `RUNNING/cancellation_requested=true` idi; lease finalizasyonu sonraki worker temizliğine bırakıldı.

Bu sonuç yeni kitaba parent olmadan otomatik reread bağlandığını doğrular. **64 sayfalık kitabın tamamı, sahne/konuşmacı/özet/QA kalitesi veya müşteri paketinin üretim kabulü tamamlanmış değildir.** İlk canary raporunda o andaki fencing/cancellation kontrolü PARTIAL olarak korunmuştur. Sonraki gerçek worker lease kontrolü ve cancellation finalizasyonu aşağıda ayrı kaydedilmiştir.

## İkinci gerçek kitapta worker lease yeniden alma — PASS

**19:50:36 UTC**, 137,617 saniye:

- Gerçek 32 sayfalık *Dünyanın En Korkak Hayvanı*, içerik `9deec326-e3ce-484a-9eac-7520d18d2cff`.
- Parent'sız ilk nesil `f7136ca2-ed91-4f76-89a8-50e6ff2c8533`, iş `2008a43e-0732-4bc0-b614-fa28aa68f4cd`.
- Sayfa 16: **33 kaynak spanı, 11 otomatik yeni tekrar ölçümü**. Sayfa boş olmayan gerçek native metin miktarına göre seçildi; beklenen cevap kullanılmadı.
- Gerçek `region_rereads` sırasında **19:48:43 UTC** yalnız canary worker'a SIGKILL gönderildi ve aynı servis yeniden başlatıldı. Consumer kesilmedi.
- Önceki lease süresi **19:50:03 UTC** dolduktan sonra aynı iş başka owner ile alındı: **fencing_token 1→2**, **attempt_no 1→2**.
- Önceki tamamlanmış immutable ölçüm request'i `19069531-ba1c-53d1-967f-99a09df8964c` korundu; yeni worker aynı kitabın optical sayfasını tamamladı. Yeni DB işi veya elle düzeltilmiş kaynak üretilmedi.
- Kaynak/evidence/page_readings API=bağımsız clone PostgreSQL; orijinal PDF SHA, bağımsız crop/TSV/hash/provenance ve eski kayıtların değişmezliği PASS.
- İkinci sayfa sonrasında da API cancellation ve yalnız canary worker stop uygulandı. Bir görsel gözlem kaydı oluşmuştu; LLM çağrısı hiç başlamadı iddiası yoktur.

Kanıt: `evidence/automatic-reread-editor_reread_v10_20260917-9deec326-e3ce-484a-9eac-7520d18d2cff.json`. Verifier SHA256: `8c0ea8fb3d8a271271e7b0c2f9f815530eb1919d9ab623c39340ecc89a6af194`.

Bu senaryo sentetik callback hatası değildir: gerçek uygulama worker'ı, gerçek DB lease ve yeni owner/fence ile doğrulanmıştır. Bununla birlikte bütün olası concurrent stale-writer yarışları veya tam kitap analizi doğrulanmış sayılmaz.

## Tamamlanmış kanıtı boş kuyrukta yeniden kullanma — bileşen PASS

**19:51:35 UTC** gerçek ikinci kitap ölçümleri ayrı, başlangıçta boş geçici kuyruk dizininden tekrar çağrıldı. Orijinal queue dosyalarına dokunulmadı; yeni consumer/OCR çalıştırılmadı. Gerçek artifact ağacındaki rapor/crop/TSV kanıtı kullanıldı.

- İstenen yeni attempt token: **3**; dönen tamamlanmış request'in token'ı **1**.
- Dönen request aynı: `19069531-ba1c-53d1-967f-99a09df8964c`.
- **11 ölçüm**, aynı provenance, artefakt SHA256 `ac419ecfbb3b0aa0903c73a3868051bb535d025ceca64238660e519190413910`.
- Yeni OCR denemesi **0**; boş kuyrukta yalnız request/result pointerları yeniden oluştu.
- Orijinal queue request/result hashleri ve clone DB kayıt hashleri/inceleme/iş/nesil sayıları değişmedi. O sıradaki mevcut clone sayıları: 21 review, 19 job, 19 generation; bunlar test tarafından eklenmiş review sayıları değildir.
- Kanıt: `evidence/reread-empty-queue-recovery-f7136ca2-ed91-4f76-89a8-50e6ff2c8533.json`.
- Genel betik: `scripts/verify-reread-queue-recovery.py`; SHA256 `d28b9392b0f63155d6c2043d50258e144a5649c87d3673531fc3f1b306f15d83`.

Bu **queue recovery bileşen kabulüdür**; komple müşteri offline paket/backup/restore kabulü değildir. Veri kaydı, orijinal kaynak veya model cevabı elle değiştirilmedi.

## Son cancellation ve servis durumu

İki canary işinin API cancellation isteği normal worker reconcile/lease akışından **CANCELLED** durumuna geçti. `6c4a4b3f-…` attempt/fence **1/1**, `2008a43e-…` **2/2** ile kapandı. Doğrudan job UPDATE yapılmadı. Ardından yalnız canary worker tekrar durduruldu; yeni analiz çalışmıyor.

Kanıt: `evidence/automatic-reread-cancellation-finalization.json`. İlk raporların tarihsel `RUNNING/cancellation_requested` anlık görüntüsü değiştirilmedi; nihai durum ayrı kanıtla tutuldu.
