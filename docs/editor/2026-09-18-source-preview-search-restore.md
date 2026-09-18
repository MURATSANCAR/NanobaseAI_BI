# Kaynak destekli taslak indeksini müşteri ortamında geri kurma

`apps/editor/scripts/rebuild-search.py` mevcut legacy arama geri kurmasını koruyarak `source_index` nesilleri için ayrı yol içerir. Bu geliştirme görevinde çalıştırılmadı; gerçek backup/restore kabulü **DOĞRULANAMADI**. Script yalnız tam Compose proje adı eşleşen hedef kurulumda kullanılır; aktif `RUNNING`/`QUEUED` iş varsa başlamaz.

## Taslak kaynağa ait yol

- `source_index` bulunan veya `pipeline_version` bildiren nesiller legacy bütün sayfa OCR indeksine hiçbir durumda düşmez.
- `current_index` gerçek PostgreSQL pasaj/review/kod hash'lerini Qdrant gerektirmeden doğrular. Eski, reddedilmiş veya uyuşmayan otorite `SKIPPED` ve açık hata nedeni olarak raporlanır; üretim başarısı sayılmaz.
- Manifest `stored_vectors`, aynı kimliklerde `vector_hashes` ve `vector_distance=Dot` içermelidir. Eski yalnız-hash manifesti `RESTORE_IMMUTABLE_VECTOR_MANIFEST_REQUIRED` ile atlanır. Yeni embedding üretip eski kanıtın yerine konmaz.
- Backup içindeki her gerçek 1024 boyutlu float vektör sonlu/sıfır olmayan değerler ve hash ile, herhangi bir Qdrant yazımından önce doğrulanır.
- Ayrı preview koleksiyonu 1024 boyutlu `Dot` olarak hazırlanır. Kaydedilmiş float32 değerleri aynen geri yazılır; cosine yeniden normalizasyonu veya model çağrısı yoktur. Var olan farklı koleksiyon sözleşmesi hata verir; otomatik silinmez.
- Her noktanın gerçek kimliği, üretim sözleşmesinden oluşturulan kaynak payload'u ve bütün vektör değerleri readback ile birebir karşılaştırılır. Vektör hash'i manifestle aynı olmalıdır. Bütün beklenen kimlikler okunduktan sonra kapsam filtresinin tam sayısı ek/fazla nokta bulunmadığını doğrular.
- Yalnız outbox `delivered_at` alanı geri kurma teslim metadatası olarak güncellenir. Kaynak metni, claim, review, nesil statüsü ve immutable indeks manifesti değiştirilmez.
- Sonunda kaynak/review/kod otoritesi yeniden okunur. Değişmişse eski sonuç kabul edilmez.

Her nesil raporu `source_preview`, `RESTORED`/`EMPTY`/`SKIPPED`, pasaj sayısı, mevcut input hash'i, sıfır embedding çağrısı ve anlamsal kabulün false olduğunu taşır. Legacy yol mevcut davranışı gereği embedding kullanabilir; taslak yolun sıfır embedding iddiası legacy nesilleri kapsamaz. Ana çıktı `evidence/search-rebuild.json` olarak korunur.

## Gerekli gerçek kabul

Asıl yeni kodla üretilmiş gerçek soru cevabı ve PostgreSQL'de tam `stored_vectors` manifesti yedeklenmeli; aynı kod/paketle ayrı müşteri kurulumuna geri dönülmelidir. Boş gerçek Qdrant'ta yeniden kurma sonrası bağımsız source-preview verifier, aynı gerçek cevabın API/PG eşliğini ve tüm vektör/payload hash'lerini kontrol etmelidir. Salt nokta sayısı veya scriptin sıfır çıkış kodu, `SKIPPED` nesilleri başarı saymak için yeterli değildir. Yeni Dot/stored-vector sözleşmesi önceki cosine aday kabulünden ayrı doğrulanmalıdır.
