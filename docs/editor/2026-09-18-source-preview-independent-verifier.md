# Taslak kaynak arama/cevap bağımsız kabul denetleyicisi

Yeni `apps/editor/scripts/verify-source-preview.py` hazırlanmıştır; bu görevde çalıştırılmadı. Test sonucu **DOĞRULANAMADI**. Script yalnız gerçek uzak uygulama/API/PostgreSQL/Qdrant üzerinde okur; model çağrısı, soru oluşturma, indeks yazımı, kaynak veya insan kararı değişikliği yapmaz. Production `verify_vectors`, `snapshot` veya diğer doğrulama fonksiyonlarını referans hesap olarak import etmez.

Gerekli ortam değişkenleri:

- `EDITOR_VERIFY_REMOTE_HOST`: CPU sunucusunun gerçek hostname'i; Linux/hostname kontrolü Mac'te çalışmayı engeller.
- `EDITOR_VERIFY_ROOT`: hedef Compose, secrets ve evidence dizininin kurulum kökü.
- `EDITOR_VERIFY_BASE_URL`: o sunucudaki gerçek loopback API adresi.
- `EDITOR_VERIFY_GENERATION_ID`: tamamlanmış gerçek kaynak nesli.
- `EDITOR_VERIFY_QUESTION_JOB_IDS`: bu nesilde gerçekten tamamlanmış bir veya daha fazla soru işinin virgülle ayrılmış UUID listesi.

Sabit kitap adı, sayfa, beklenen cevap veya 64 gibi sabit pasaj sayısı yoktur. Uygun pasaj sayısı kaynak veriden hesaplanır. API anahtarı yalnız dosyadan okunur; stdout/kanıta yazılmaz, hata metninde redakte edilir. Komut stderr'i bastırılır.

## Denetlenenler

1. Bütün kaynak kayıt türleri, `source_passages` ve `source_index` için tam sayfalanmış API cevabı bağımsız PostgreSQL sonucu ile karşılaştırılır.
2. Kaynak/review sürümleri, generation manifesti ve kayıtlı kod hash'leriyle güncel indeks girdi hash'i bağımsız yeniden hesaplanır. Aktif API konteynerindeki gerçek dosya hash'leri ve image kimliği kaydedilir.
3. Pasaj metni gerçek span metinlerinin aynen birleşimi olmalıdır; bbox/render hash'i, claim ordinal/hash'i, uygunluk kararı, destek bölgeleri, citation-review, sayfa-amacı kaydı ve tüketilen komşu bağlam kimlikleri karşılaştırılır. Açık kaynak/indeks retleri ve eski reddedilmiş pasaj claim'leri yeni indeksle aşılamaz.
4. Manifestin `vector_distance=Dot` ve tüm pasaj kimliklerinde `stored_vectors` taşıması gerekir. Kaydedilmiş her 1024 boyutlu sonlu/sıfır olmayan vektörün hash'i bağımsız hesaplanır. Qdrant koleksiyonunun gerçek GET metadatasında 1024/Dot aranır; beklenen tüm kimlikler read-only endpoint üzerinden okunur. Payload alanları bağımsız oluşturulur; her gerçek vektörün bütün değerleri backup manifestindeki değerlerle birebir, hash'i de PostgreSQL manifestiyle eşleşmelidir. Filtreli tam küme sayısı ve outbox teslimi ayrıca denetlenir. Nokta sayısı tek başına başarı değildir. Boş indekste vektör bulunmadığından fiziksel koleksiyon zorunlu değildir; manifest `EMPTY`, boş kimlik/vektör kümeleri ve Dot sözleşmesi yine doğrulanır.
5. İstenen her soru için API'nin sunduğu aynı cevap PostgreSQL cevabına eşit olmalıdır. Serbest cevap yalnız kabul edilen iddia metinlerinin birleşimi olmalı; her iddianın güncel gerçek pasajı, span'ları, tamamlanmış model önerisi, alıntı denetimi ve soruyla ilgi denetimi destekli olmalıdır. Alıntı incelemesinin girdi hash'i o cevap iddiasından yeniden hesaplanır.
6. Kaynak capability cevabı güncel uygun pasaj sayısıyla eşleşmelidir. Kontrol sonunda insan kararları ve tüm kaynak kayıtları tekrar okunur; eşzamanlı değişiklik varsa eski snapshot başarı sayılmaz.

Rapor `evidence/source-preview-<UTC>.json` dosyasına yazılır. `semantic_acceptance=False`, `complete_book=False` korunur. Bu denetim gerçek cevabın veri/provenance bütünlüğünü kontrol eder; modelin anlamsal yargısının insan editör rubriğine göre doğru olduğunu tek başına kanıtlamaz. İddia cümlelerinin bağımsız gerçek kitap değerlendirmesi ayrıca gerekir. Denetim, üretim helper'ını oracle olarak kullanmadığı halde alıntı denetiminin kaydettiği okuma-segmentlerini baştan OCR okuyarak üretmez; ham span metinleri/geometrisi ve bunları tüketen payload hash'lerini doğrular.
