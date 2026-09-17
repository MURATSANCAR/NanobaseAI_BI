# İki ek gerçek kitapta kaynak hazırlama kabulü — 17 Eylül 2026

## Sonuç ve kapsam

İki farklı gerçek PDF, ayrı Editör kurulumuna gerçek ürün API'si üzerinden yüklendi. **96 ek sayfanın kaynak hazırlaması PASS**. Kitap metni, konuşmacı, model cevabı veya inceleme kararı elle değiştirilmedi. Bu iki kitap için analiz başlatılmadı; doğrulama anında her içerik sürümünün analiz nesli sayısı **0** idi.

Bu sonuç, üç kitabın anlamsal analiz kalitesi veya üretim kabulünün tamamlandığı anlamına gelmez. OCR metninin anlamsal doğruluğu, konuşmacı kimliği, olay/tema çıkarımı ve soru-cevap bu kabulün kapsamı dışındadır. Kaynakların bütünlüğü ve gerçek ürün yükleme akışı doğrulanmıştır.

## Gerçek yürütme ortamı

- Sunucu: `nanobase-direct`; testler yerelde çalıştırılmadı.
- Bağımsız kurulum kökü: `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation`.
- Gerçek API: `http://127.0.0.1:18810`; bağımsız referans: aynı kurulumun gerçek `editor` PostgreSQL veritabanı.
- Genel kabul betiği: `apps/editor/scripts/verify-multibook-ingestion.py`.
- Doğrulanan betik SHA256: `c55a25bffab473dfe6c070b27dd6d3d9e8eca8692d38254a29cbc5d77ff05249`.
- Parser image kimliği: `6710488fe6611fbe8fd845ac10371c7f0d051bcc967d7f23ac22b68422e285a9`.
- Kaynak araçları: Docling `2.127.0`, Poppler pdfinfo/pdftoppm `22.12.0`, Tesseract `5.3.0`.
- Kaynak PDF'ler kullanıcının mevcut `TİMAŞ/kitaplar` dizininden değiştirilmeden sunucuya aktarıldı. Yerel dosya ile sunucu kopyasının SHA256 değerleri karşılaştırıldı. Yapay kitap/fixture kullanılmadı.

## Kitap ve kanıt kimlikleri

| Gerçek kitap | Bayt | Sayfa | Son kabul UTC |
|---|---:|---:|---|
| Kahramanını Yutan Kitap | 10.647.948 | 64 | 2026-09-17 14:05:43 |
| Dünyanın En Korkak Hayvanı | 20.598.751 | 32 | 2026-09-17 14:05:47 |

### Kahramanını Yutan Kitap

- Kaynak SHA256: `fbbead4dca9a3a1b7b6e515f3df791460895cb91bdbb4f1fec74fa67ce212c73`.
- Work: `67f7d999-a639-4ae8-9e96-66a55240b22b`.
- Edition: `2824c2e7-3ac0-4f2b-ab35-650f6b59c908`.
- Upload: `311ff495-7c74-49e4-bd19-c3595128025e`.
- Content version: `56d7d123-cfef-4bc4-8334-f9acf5103883`.
- Kanıt, kurulum köküne göre: `evidence/multibook-ingestion/fbbead4dca9a3a1b7b6e515f3df791460895cb91bdbb4f1fec74fa67ce212c73.json` ve aynı adlı `.md`.
- Parser günlüğü, parser veri alanında: `/data/artifacts/parse-attempts/311ff495-7c74-49e4-bd19-c3595128025e/2409d062-a534-40da-9994-ad650194b586/parser.log`.
- Seyrek yazı bölgelerinde **4 OSD uyarısı** kaydedildi; dönüşüm tamamlandı. Bu uyarılar silinmedi veya metin başarısı olarak yorumlanmadı.

### Dünyanın En Korkak Hayvanı

- Kaynak SHA256: `12cc83a4ccffe9394fa2695c76e460cf87e2ffe32e6ae69d6699fcaee43ceea2`.
- Work: `85669588-8f3c-41a5-a8cc-1bd905d8966d`.
- Edition: `4349f240-78d6-47a9-9331-274b593bbc3b`.
- Upload: `1576cc19-3f11-4636-9344-a11f918f2f49`.
- Content version: `9deec326-e3ce-484a-9eac-7520d18d2cff`.
- Kanıt, kurulum köküne göre: `evidence/multibook-ingestion/12cc83a4ccffe9394fa2695c76e460cf87e2ffe32e6ae69d6699fcaee43ceea2.json` ve aynı adlı `.md`.
- Parser günlüğü: `/data/artifacts/parse-attempts/1576cc19-3f11-4636-9344-a11f918f2f49/bafecac7-d3c0-4325-acce-5c9d1400d609/parser.log`.
- Seyrek yazı bölgelerinde **3 OSD uyarısı** korundu; dönüşüm tamamlandı.

## Bağımsız kabul kontrolleri

1. Gerçek `works → editions → uploads → PUT content → complete` API akışı yürütüldü; parser kuyruğu iki kitap için sırayla kullanıldı.
2. API'nin `COMPLETED` yükleme durumu ve içerik sürümü, bağımsız PostgreSQL `uploads/content_versions/source_probes` birleşimiyle karşılaştırıldı.
3. API kaynak manifestinin tam JSON değeri PostgreSQL manifestiyle eşit bulundu.
4. Arşivlenen orijinal PDF'nin SHA256 ve bayt değeri, yüklenen değişmemiş dosyayla eşit bulundu.
5. Bağımsız Poppler `pdfinfo` sayfa sayısı, manifest sayfa sayısı ve sayfa kayıtlarıyla eşit bulundu; kayıtların sıralı ve eksiksiz olduğu kontrol edildi.
6. Her sayfanın render SHA256 değeri, konumlu PDF/OCR kayıtlarının kaynak/sayfa kimlikleri, OCR PNG ve ham TSV hashleri dosyalardan yeniden hesaplandı. Docling JSON hash değeri de karşılaştırıldı.
7. Her yeni içerik sürümü için PostgreSQL analiz nesli sayısının sıfır olduğu doğrulandı. Esas kitabın süren analizine veya kayıtlarına müdahale edilmedi.

Betik PDF yolu, başlık ve API adresini argüman olarak alır. Kitaba özel isim, sayfa sayısı, hash veya beklenen cevap üretim mantığına eklenmedi. Checkpoint ve idempotency anahtarları yeniden başlatmada aynı yüklemenin devamını sağlar; geçici bağlantı/502/503/504 için yalnız güvenli GET ve idempotent POST çağrıları sınırlı tekrar uygular. Bu tekrar mekanizmasının arıza enjeksiyonuyla kabulü yapılmadı; burada gerçek başarılı kaynak kabulü kaydedilmektedir.

## V7 öncelikli sayfa API sınırı — gerçek kitapla olumsuz kabul

17 Eylül **14:13:22 UTC** tarihinde aynı gerçek API ve PostgreSQL üzerinde mevcut 48 sayfalık içeriğe karşı iki geçersiz istek gönderildi. Geçerli analiz başlatılmadı; sayfa sınırı ve mevcut sayfa kimliği gerçek kaynak manifestinden alındı.

- İçerik sürümü: `3970f5b9-769a-4fe9-8032-379834fa6831`.
- Gerçek PDF SHA256: `94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50`.
- Genel betik: `apps/editor/scripts/verify-priority-pages-api.py`.
- Betik SHA256: `2bae892db98f11b1fbc2715ec27ac64e47dc0f8261d1076ab99bb019854ee290`.
- Kanıt: kurulum kökünde `evidence/priority-pages-api.json`.

| Senaryo | Gerçek gönderilen priority_pages | API sonucu | PostgreSQL önce → sonra |
|---|---|---|---|
| Gerçek sayfa sınırı + 1 | `[49]` | `422 INVALID_PRIORITY_PAGES` | jobs `15 → 15`, generations `15 → 15` |
| Yinelenen mevcut sayfa | `[1, 1]` | `422 INVALID_PRIORITY_PAGES` | jobs `15 → 15`, generations `15 → 15` |

İki istek de iş veya analiz nesli üretmeden reddedildi: **PASS**. Bu kontrol öncelik sırasının başarılı analizde uygulanmasını veya anlamsal kaliteyi doğrulamaz; yalnız gerçek kaynak sınırı/yinelenme kapısını ve yan etki oluşturmamasını doğrular.
