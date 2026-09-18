# P5 — Salt okunur kaynak bağımlılığı etkisi

Yeni `source_dependencies.py`, `book_api.py` salt okunur endpoint'i ve `verify-source-impact.py` hazırlandı. Uzak uygulama/koşu değiştirilmedi; yeni iş/model çağrısı ve kaynak/review yazımı yapılmadı. Yerelde yalnız Python AST sözdizimi incelemesi yapıldı; uygulama/test çalıştırılmadı. Gerçek endpoint/mobil kabulü yeni sürüm yayımlandıktan sonra yapılmalıdır: **DOĞRULANAMADI**.

## Gerçek kayıt şekli kontrolü

CPU PostgreSQL'de tamamlanmış R4 neslinin her kayıt türünden bir örneğin yalnız kimlik/alan adları/hash'leri tek sınırlı salt okunur sorguyla incelendi. Kanıt `evidence/source-impact-real-record-shape-audit.json`. `evidence.source_sha256`, `evidence.ocr_render_sha256` ve span `render_sha256` gerçek alanlardır; örnek kaynak bağı eşleşti. `page_readings.span_ids` ve `visual_observations.source_span_ids` gerçek şemadan görüldükten sonra açık referans kapsamına alındı. Bu şema kontrolü endpoint kabulü değildir; R4 kimlikleri yalnız kanıt girdisidir, üretim koduna özel kitap/sayfa/karakter kuralı konmadı.

## API ve durum anlamı

`GET /v1/generations/{generation}/records/{record_id}/impact?offset=0&limit=50`

Yanıt `generation_id`, hedef kayıt, etkilenen kayıtlar, `offset/limit/has_more/total`, `snapshot_sha256`, `graph_scope=SOURCE_DEPENDENCIES`, `complete=false`, `semantic_acceptance=false` taşır. Hedef `items` içine tekrar konmaz. Her öğede id/tür/kayıt anahtarı/sayfalar, hedefe mesafe, durum, gerekçeler ve kısıtlı ilişki tanıkları bulunur.

- `CURRENT`: denetlenen yapısal kaynak bağlarında uyuşmazlık saptanmadı. İnsan onayı, anlamsal kabul veya yayın izni değildir.
- `STALE`: mevcut insan ret/inceleme kararı, bulunamayan açık kaynak referansı, eşleşmeyen kaynak/girdi/kod hash'i veya açık bağımlılığın bu durumu kanıtlandı.
- `UNRESOLVED`: kimlik/otorite doğrulanamadı, kaynak okuması inceleme bekliyor, tür desteklenmiyor veya sayfa bağlamının kapsamı ancak çıkarımla belirlendi. Yakın sayfa tek başına kesin bağımlılık ya da kimlik kanıtı sayılmaz.

İlişki `basis` değerleri `EXPLICIT_REFERENCE`, `CLAIM_OWNERSHIP`, `SAME_PAGE_RECORD_SCOPE`, `INFERRED_PAGE_CONTEXT_INPUT`, `CANONICAL_SNAPSHOT_INPUT` olabilir. Claim hash'leri kaynak `page_claims` adaylarından hesaplanıp review/sentez sahipliğine bağlanır. Pasaj/indeks/cevap bağlantıları saklanmış referans ve hash'lerden gelir. Modelin ham cevapları, reddedilmiş önerileri ve serbest görsel açıklamaları yeni otorite üretmez. Tarihsel indeks/cevaplar silinmez; mevcut hash'e uymuyorsa eski olarak görünür.

## Sabit snapshot ile sayfalama

İlk cevap target, kayıtlar, karar sürümleri, kod/otorite ve oluşturulmuş grafiği kapsayan `snapshot_sha256` döndürür. Sonraki sayfalarda `expected_snapshot_sha256` zorunludur. Eksikse `400 IMPACT_SNAPSHOT_REQUIRED`, biçim bozuksa `400 INVALID_IMPACT_SNAPSHOT_HASH`, aynı akışın snapshot'ı değiştiyse `409 IMPACT_SNAPSHOT_CHANGED`. Arayüz farklı anlara ait sayfaları birleştiremez; yeniden ilk sayfadan yüklemelidir.

Önce generation/work ACL doğrulanır; başka generation'a ait record `404` olur. DB okuması `REPEATABLE READ, READ ONLY` snapshot'ındadır ve bütün okuma bittikten sonra işlem kapatılır; hash/graf hesaplanırken açık transaction tutulmaz. SQL statement limiti 8 saniyedir. Genel ortam sözleşmeleri `EDITOR_IMPACT_MAX_RECORDS` (varsayılan 10000), `EDITOR_IMPACT_MAX_BYTES` (64 MiB), `EDITOR_IMPACT_MAX_EDGES` (200000) sınırları aşılırsa `413` döndürür. Büyük kapsam gizlice kesilip tamamlanmış gösterilmez. Tam snapshot'tan türeyen ilişkiler BFS'de yalnız en kısa mesafedeki ilk kapsam noktasında genişletilir; gereksiz kaynak-sayısı × pasaj-sayısı tekrarları yapılmaz.

## Sınırlar ve bağımsız kabul

Bu bir etki önizlemesidir; otomatik yeniden işleme, kitap metni düzeltme, karar verme veya tüm bağımlılıkların kanıtlandığı iddiası değildir. Sayfa amacı komşu girdi kapsamı açıkça çıkarım olarak etiketlenir. Başka nesilden gelen eski ölçüm soy ağacı ve dosya/vektör içeriklerinin tamamı bu grafikte yeniden doğrulanmaz. Aynı isimler birleştirilmez. `complete=false` daima korunur.

`verify-source-impact.py` uzak Linux/hostname ve gerçek loopback API ister; env `EDITOR_VERIFY_REMOTE_HOST`, `EDITOR_VERIFY_ROOT`, `EDITOR_VERIFY_BASE_URL`, `EDITOR_VERIFY_GENERATION_ID`, `EDITOR_VERIFY_IMPACT_RECORD_ID`. Gerçek PG kayıtlarını bağımsız okur; API hedef/öğe kimliklerini, saklanmış açık referans/claim sahipliği/kapsam tanıklarını, mesafe zincirini, snapshot'a bağlı tam sayfalamayı ve mevcut insan retlerinin görünmesini karşılaştırır. Production graph helper'ını import etmez; çıktı `evidence/source-impact-<UTC>.json` olur. Bütün anlamsal bağımlılıkların eksiksizliğini veya her yapısal hash önermesini bağımsız kanıtladığını iddia etmez. Gerçek mobil kabul ve farklı eser ACL denetimi ayrıca yapılmalıdır; sentetik kaynak/karar yaratılmaz.
# Gerçek izole kabul — 18 Eylül 2026

CPU'da ana R7 image (`8b9b3042c82727a1484cc694e0d91bfe021c696feff85277ec7dd589a8bd4b76`) üzerine yalnız `source_dependencies.py` ve `book_api.py` kopyalanarak aday API `127.0.0.1:18836` üzerinde çalıştırıldı. Ana API/worker/model ve devam eden nesil değiştirilmedi. Aday GET/HEAD dışında istek reddeden wrapper, salt okunur kök/artifact/secrets ve PostgreSQL `transaction_read_only=on` ile sınırlandı. Başlangıçta migration/startup yazımı olmadığı koddan incelendi.

Gerçek tamamlanmış R4 nesli `08ca6877-6e30-4bb3-b1fa-767f048248e4`, kaynak hedefi `dd24320c-8545-5e52-b0e5-ed6b68e6e2e2` ile bağımsız PostgreSQL/API doğrulaması **PASS**: 135 kayıt, 164 ilişki, 134 etkilenen kayıt; üç sayfalık sonuç aynı snapshot'a bağlı. Kimliksiz erişim 401, başka neslin gerçek kaydı 404, devam sayfasında snapshot eksikliği 400, değişmiş snapshot 409 ve limit aşımı 400 kontrolleri geçti. Hedef `UNRESOLVED / SOURCE_READING_REQUIRES_REVIEW` kaldı; sonuç anlamsal kabul veya yayın yetkisi değildir. Kullanıcının mevcut erişimiyle doğrulandı; ayrı kısıtlı kullanıcı hesabının ACL matrisi bu koşuda sınanmadı.

CPU kanıtları: `/data/nanobaseai/editor/evidence/source-impact-20260918T065246080334Z.json`, `/data/nanobaseai/editor/evidence/p5-impact-isolated-candidate-runtime.json`. Aday image: `19610e39f3a83b29bf76c8de972c396d2eb107365f8e9cfb813f900539446f01`; snapshot: `5ce0fdcfc035fc197cbe99dc552838a9c55c1f6d9d0ba06cca33257a830bcda1`.

İlk iki bağlantı denemesi başarısızlığı (`065113226574Z`, `065140835544Z`) korundu: wrapper uygulama import yolu ve internal Docker ağının host port yayımlamaması izole runtime üzerinde giderildi. Başarısız denemeler kabul sayılmadı. Yeni başarılı koşu gerçek aynı veriyle tekrarlandı. Grafik kapsamı hâlâ sınırlıdır: bağımsız denetleyici beyan edilen yolların gerçek kaynak bağlantılarını doğrular; tüm olası anlamsal bağımlılıkların eksiksizliğini kanıtlamaz. Mobil UI kabulü ayrı ajan tarafından aynı adaya karşı yürütülür; ana yayına dağıtım yapılmadı.
