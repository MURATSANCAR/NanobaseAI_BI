# Kaynak destekli taslak arama: bağlı olmayan aday modül

`apps/editor/backend/editor/source_retrieval.py` yeni ve genel bir modüldür. Modülün ilk hazırlanmasında deploy, model çağrısı, gerçek DB yazımı veya yerel test yapılmadı. Aşağıdaki gerçek salt okunur canonical kabul daha sonra yürütüldü; indeks ve soru-cevap ürün kabulü bu deneyle **DOĞRULANAMADI**. Kodun bulunması çalışan soru-cevap özelliği değildir.

## Gerçek salt okunur aday kabulü

CPU'da `nanobase-editor:source-analysis-v15-r2-20260918`, kesin image ID `sha256:cdf24544d6fcc9b32b1d05c7c8b1112fc71d5ed20c09d935ffa26b560420682a` ile tamamlanmış R4 nesli `08ca6877-6e30-4bb3-b1fa-767f048248e4` üzerinde `snapshot` çağrısı geçti. 64 uygun inceleme iddiasından 64 kaynak pasajı çıktı; import sonrası işlem 1,924 saniye sürdü.

Yedi kaynak kayıt türünün gerçek API cevapları bağımsız PostgreSQL sorgusuyla eşleştirildi. Her pasajın aday hash'i, dayanak kimlikleri, gerçek span metni/bbox/render hash'i ve kaynak bölgesi hash'i ayrıca API referansından hesaplandı ve eşleşti. Kanıt `/data/nanobaseai/editor/evidence/source-preview-r4-readonly-v15-r2-candidate.json`; aday kod bağımlılık hash'leri bu rapordadır. Çalıştırıcı `runtime/source-preview-readonly-candidate.py`.

Ephemeral konteyner salt okunur kök, yalnız `db_app` secret mount, özel ağ ve `PGOPTIONS=-c default_transaction_read_only=on` kullandı. Model çağrısı, uygulama/indeks yazımı ve kaynak/review değişikliği sıfırdır. Canlı uygulama veya devam eden R5 koşusu değiştirilmedi. Bu sonuç canonical kaynak seçimini doğrular; Qdrant indeksleme, soru cevabı veya yayın kabulü değildir.

## Sözleşme

- `verified_passages(generation)` gerçek PostgreSQL'in tutarlı salt okunur snapshot'ından makine denetimli, kapsamı sınırlı kaynak pasajlarını döndürür. Dönüş `id`, `record_key`, `data` içerir. `data`: gerçek destek metni, sayfa, `source_span_refs`, `regions`, `claim_ids`, bağımlı kayıtlar ve hash'lerdir.
- `build_index(job)` çalışan işin lease/fence yetkisiyle `source_passages`, outbox ve `source_index` kayıtlarını yazar; ayrı `editor_source_preview_1024_v1` Qdrant koleksiyonunu kullanır. Tamamlanmış iş üzerinde çağrılamaz.
- `ready(generation)` mevcut kaynak/review/kod snapshot'ıyla eşleşen manifest, PostgreSQL pasajları/outbox ve bütün Qdrant payload/vektörlerini doğrular. Uyuşmazlıkta false; DB bağlantı hatası yükselir ve API erişimi başarı sayamaz.
- `search(generation, question)` aynı doğrulamadan sonra en çok beş güncel pasaj döndürür. Kaynak/review arama sırasında değişirse hata verir. Boş uygun kaynak kümesinde indeks durumu `EMPTY`, `ready=True`, arama `[]` olur; üst katman modelsiz `INSUFFICIENT_EVIDENCE` döndürmelidir.

## Korunan kapılar

Mevcut `semantic_acceptance` ve `page_context` yardımcılarıyla sayfa amacı, kaynak bağlamı, aday hash'i, model girdileri, destek bölgeleri, alıntı ve sözcük sınırı, olumsuzluk ve ayrı citation-review geçişi yeniden hesaplanır. Modelin tamamlanmış cevapları gerekir. Görsel betimleme ve ham sayfa OCR/PDF metni modele veya vektör metnine eklenmez; sadece izinli `TEXT_AGREED` destek span'larının metni kullanılır. Ham kayıtlar yalnız kaynak kapsamının hash doğrulamasında bulunur.

İsim eşlemesi yalnız tekrar doğrulanabilen sayfa içi açık metin kapsamındadır. `ENTITY` ve dış görsel kimlik gerektiren iddialar bu modülde yükseltilmez; aynı adlar birleştirilmez. Makine uygunluğu insan kabulü değildir. Her pasaj `preview_only=True`, `editorial_acceptance=False`, `complete_book=False` taşır.

Son açık insan `REJECT` veya `NEEDS_REVIEW` kararı kullanılan kaydı dışlar. İnsan kararı olmayan makine destekli kaynak yalnız taslak için kullanılabilir. Sayfa-amacı komşu bağlamı tükettiğinden komşu kaynak/geometri kayıtlarına konan ret de ilgili sayfanın dayanağını geçersizleştirir; bu bilinçli olarak muhafazakârdır. Türetilmiş pasajın reddi, claim kimliği üzerinden sonraki indeks nesnesine de taşınır. İndeks kaydının açık reddi yeni bir manifest üretip ret kararını aşamaz; kapı kapanır.

İndeks kimliği kaynak kayıtları, insan karar sürümleri, generation manifesti ve kullanılan kod dosyalarının hash'lerinden türetilir. Pasaj/indeks immutable kayıtlardır; eski index yeni kaynakmış gibi güncellenmez. Kaynak değişince eski vektörler yeni manifest filtresinden seçilemez.

Qdrant kabulü yalnız nokta sayısına dayanmaz: beklenen tüm kimlikler, her payload, 1024 sonlu/sıfır olmayan vektör değeri, vektör readback hash'i ve PostgreSQL/outbox eşliği kontrol edilir. Cosine vektörleri yazmadan normalize edilir; ilk readback beklenen normalize vektörle float toleransında karşılaştırılır. Aynı hazır manifestin retry'ı yeniden embedding üretmez; mevcut veriyi doğrular.

## Ana görevin entegrasyonu ve gerçek kabul

1. Ana görevin entegrasyon kararı: kaynak analizi tamamlandıktan sonra ilk `source_answers` soru işçisi kendi `RUNNING` lease/fence yetkisiyle indeksi ihtiyaç halinde oluşturur. Kaynak koşusu değiştirilmez ve indeks arızası bütün kitabın tekrar analizini gerektirmez. Desteklenen pipeline sürümleri açıkça `source-spans-v14` ve `source-spans-v15` ile sınırlıdır; semantik/sayfa-amacı sürümü ve bütün girdi/hash kapıları yine güncel doğrulayıcıyla eşleşmelidir. Neslin `NEEDS_REVIEW` statüsü değiştirilmez.
2. Ayrı taslak cevap işçisi yalnız bu modülün pasajlarını kullanmalıdır. Legacy `retrieval.build_index` ve `analysis.answer_question` bu akışa bağlanmamalıdır.
3. API `editor_preview` için tamamlanmış kaynak akışı ve `ready` kapısını ayrı değerlendirmelidir. Published/ACTIVE ve insan kabul kapıları aynı kalmalıdır.
4. Gerçek bağlı DB/API neslinde pasajları bağımsız source/review referans hesabıyla karşılaştırın; gerçek vektör payload ve embedding model/image sürümünü kaydedin. Erişim sınırı, kapsam dışı atıf, ret sonrası stale indeks, boş kaynak ve iş lease/cancel kabulü ayrıca doğrulanmalıdır. Kaynak/inceleme kararlarını bu test için elle değiştirmeyin; gerçek mevcut ret senaryosu yoksa ilgili negatif kabul doğrulanamadı kalır.
5. Yeni modül değişirse hash değişir; eski indeks kabulü yeni kodu kapsamaz. Bu modül tek başına tam anlamsal kabul veya bütün P4 kapsamı sağlamaz: şu an dense aramadır, hybrid/reranker ve cevap cümlelerinin kaynak denetimi ayrı entegrasyondur. Embedding servisinin gerçek ağırlık/image kimliği dağıtım kabulünde ayrıca sabitlenmelidir; bu modül tek başına servis imaj kimliğini keşfetmez.
