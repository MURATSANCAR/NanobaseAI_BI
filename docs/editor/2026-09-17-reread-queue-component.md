# Otomatik tekrar okuma kuyruğu — bileşen kabulü

## Hazırlanan kontrol

`apps/editor/scripts/verify-reread-queue.py` gerçek kaynak/API/PostgreSQL ve ağsız consumer üzerinde çalışacak genel kabul betiğidir. Kaynak kitap veya beklenen cevap içermez; API, gerçek analiz nesli ve sayfalar argümanla verilir. Yerel test değildir.

Gerçek bağımsız kurulumda **17 Eylül 2026 14:43:10 UTC** tarihinde çalıştırıldı: **bileşen kabulü PASS**. Ürün optical akışının uçtan uca kabulü ayrıca gereklidir.

Kontroller:

- Gerçek neslin bütün `source_spans` ve `evidence` kayıtlarında sayfalanmış API JSON'u ile bağımsız PostgreSQL eşitliği.
- Seçili gerçek sayfalarda yalnız gerçek span UUID/bbox/source/render hashinden kuyruk isteği.
- Gerçek ağsız consumer'da `submit → await_result → load_verified` akışı.
- Orijinal renderdan bağımsız yeniden üretilen crop ile kaydedilmiş PNG/hash/kutu eşitliği.
- Ham TSV'lerin hashleri; farklı TSV ayrıştırma yöntemiyle metin ve güven değerlerinin eşitliği.
- Aynı isteğin tekrarında istek/sonuç/artefakt hashleri ve deneme sayısı değişmemesi.
- Önce/sonra kaynak kayıtları, incelemeler, nesil metadatası ve iş/nesil sayılarında değişiklik olmaması.

## Kapsam sınırı

Başarı bile **bileşen kabulüdür**. Ürün `source_pipeline.optical` akışının otomatik tetiklemesi, yeni kitapta parent olmadan çalışma, worker fencing/cancellation ve anlamsal kalite bu betikte doğrulanmış sayılmaz. Rapor bunları sırasıyla `product_optical_end_to_end=false`, `fence_cancellation_tested=false`, `semantic_acceptance=false` olarak belirtir.

Callback gerçek kaynak manifesti/render hashini kontrol eder; iş fencing testi gibi sunulmaz. Gerçek kaynak/inceleme DB kaydı yazılmaz. Yeni OCR ölçümleri kendi immutable artefakt dizinine yazılır ve orijinal PDF/render dosyaları değiştirilmez.

## Gerçek sonuç ve kanıt

- Ortam: `nanobase-direct`, `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation`.
- API: `http://127.0.0.1:18810`; aynı gerçek Editor PostgreSQL bağımsız sorgulandı.
- Gerçek nesil: `8c780a30-fc9b-4ad7-a576-317e6142ad3f`.
- Consumer etkinleştirme env dosyası: `runtime/candidates/auto-reread-v10/activation.json`; betik bu dosyadaki Compose/image değerleriyle çalıştırıldı. Mevcut uygulama servisleri bu kabul tarafından yeniden oluşturulmadı.
- Betik SHA256: `670ed17111a9366a0b1d22a3737ad25f3196d0573d364a3891f7e4e21b8e9126`.
- Gerçek consumer kod SHA256: `cc0b0a978a4e4d7b5952b7af2150a8abb098877088a41c607138cb654deb4ea2`.
- Ana kanıt: kurulum kökünde `evidence/reread-queue-component-20260917T144310Z.json`.

| Gerçek sayfa | Bölge | Request UUID | İlk/tekrar deneme sayısı |
|---|---:|---|---|
| 13 | 23 | `4c21345f-a85e-54bb-90ca-aa5b25b3f34e` | 1 / 1 |
| 29 | 14 | `29d55adc-ab59-5903-8f39-efffdf867ac5` | 1 / 1 |
| 38 | 24 | `50e52e65-7cf9-5bd8-9ed9-b0cd171edd27` | 1 / 1 |
| **Toplam** | **61** | | |

İlk tüketici denemesi `1789656112.3485081` Unix zamanında başladı; sonuç raporu 14:43:10 UTC'de yazıldı. İlk denemenin başlamasından bütün kabul kontrollerinin raporlanmasına kadar **yaklaşık 77,8 saniye** geçti. Bu, yalnız OCR motoru süresi değildir; sonuç bekleme, bağımsız doğrulama ve tekrar kontrolleri de dahildir.

61 kırpımın tamamı orijinal renderdan bağımsız yeniden üretildi; PNG bayt/hash ve geometri eşit bulundu. 122 ham TSV'nin hash, metin ve kelime güvenleri bağımsız header-indeksli ayrıştırmayla karşılaştırıldı. Aynı istek ikinci kez gönderildiğinde request/result/artefakt hashleri, ölçüm/provenance ve deneme sayıları değişmedi.

Gerçek DB önce/sonra: **jobs 16→16, generations 16→16, ilgili reviews 0→0**. Nesil metadatası ile bütün kaynak span/evidence kayıtları aynı kaldı; API JSON'u her iki tarafta bağımsız PostgreSQL sonucu ile eşit. Kaynak/evidence SHA256: `a3de5346fde8bc19f3d52566491c0e49c60212418adf47054f030ff93fa8b1b2`.

## Backup kapsamındaki artefaktlar

Raporlar mevcut kaynak artefakt volume'unda şu kökte durur:

`/data/artifacts/94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50/region-reread-queue-v1/8c780a30-fc9b-4ad7-a576-317e6142ad3f/`

- `page-0013.json`: `bce02ae84ca3cf2813aa4b782eea25bcc8a82c721c32d3268a0f0d91408c8cb3`.
- `page-0029.json`: `75fa94260fcb0e6755585b6b2cf9c2d16381ccff991aa9b0aef5be1745ad1c61`.
- `page-0038.json`: `b223e517168b258800eaf9680296d354c6aa804026c16e27d3afb010471aa3a8`.

Her sayfanın altındaki request UUID/bölge indeks dizininde `crop.png`, `psm7.tsv`, `psm13.tsv` ve motor günlükleri korunur. Kaynak volume'una yerleşmeleri mevcut artifact backup kapsamına girmelerini sağlar; **bu yeni ölçümlerle ayrı backup/restore koşusu bu bileşen testinde yapılmadı**.

Motor `tesseract 5.3.0`, profil `tur+eng`; Türkçe model SHA256 `7393381111e1152420fc4092cb44eef4237580d21b92bf30d7d221aad192c6b7`, İngilizce `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.

Sonuç kaynak metinlerini güncellemez. Bileşen akışı doğrulandı; kaynak kapısının bu ölçümleri otomatik üretip yeni kitabın nihai span kararlarına bağlaması, cancellation/fencing ve anlamsal kalite halen ayrı kabul adımlarıdır.
