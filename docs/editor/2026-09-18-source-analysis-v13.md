# V13 hazırlığı: küçük kaynak bölgeleri ve sayfa bağlamı

V13-r1 API/worker, ağsız document/reread tüketicisi ve web yayımlandı; tam kitap kabulü değildir. Kitap içeriğine elle müdahale edilmez.

## Canlı V13-r1

Yayın `source-analysis-v13-r1-20260918`, pipeline `source-spans-v13`; 46 backend dosyasının kaynak/imaj eşliği `b87cc35c7998650cbdb060218df7cc5899920678d58f1cac984546b92c542b76`. Yeni iş `4ca9b23a-7027-4909-b49f-1fd26c93b497`, nesil `18417f1b-d9db-4873-aeb8-b8c719fc0d0d`; V12 ölçümleri kaynak olarak tekrar kullanılır. Öncelik sayfaları yalnız koşu parametresidir. Salt okunur sayfa izleyicisi ayrıca başlatıldı.

Son kaynakla sayfa bağlamı gerçek pilotu 41 API/PG kaydı ve parent hash kontrolünü geçti; iki model çağrısı, kapsam/kimlik belirsizliklerini görünür koruyarak yalnız sayfa amacını kabul etti. Aynı hashlerle cross-page kontrolü 22 sayfada 1 sınırlı söz bağlantısı, 0 genel kimlik, 0 scope_error verdi. Kanıtlar `page-context-0eb7d199-cebc-4454-96f6-1d5cb1685986-0029-75505f9c06f8-fd8be57224ff.json` ve `cross-page-attribution-0eb7d199-cebc-4454-96f6-1d5cb1685986-c01ff688fefd-5de054fe0542-5630f696aae4.json`.

Dağıtım sonrası altyapı denetimi OCR STOPPED durumunu arıza saydı. `verify.py`, yalnız on_demand=true, gateway_reachable=true ve state=STOPPED için beklemeyi kabul edecek biçimde düzeltildi; diğer servis hataları hâlâ engellenir. Çıktı açıkça bunun OCR uyanma/çıkarım kabulü olmadığını belirtir. Gerçek altyapı kontrolü tekrar geçti. Yeni kitabın OCR gerektiren çağrısının otomatik uyanması ayrıca izleniyor. Kanıt `evidence/source-analysis-v13-infrastructure.log`.

## V12 kapanış ölçümü ve devam

V12 nesli `2d774b82-e04f-45a3-92fc-eadaa8a37934` 48/48 teknik kaynak kontrolüyle tamamlandı; hata listesi boş, sonuç NEEDS_REVIEW. Gerçek API ve bağımsız PostgreSQL kontrolünde 48 evidence, 1.149 source_spans, 48 page_claims, 48 figure_identity, 12 figure_comparisons, 48 semantic_reviews ve bir semantic_synthesis kaydı eşleşti. 52 iddia sentez adayı olarak kapıları geçti; bu bütün kitabın anlamsal kabulü değildir. Kanıt `evidence/source-analysis-2d774b82-e04f-45a3-92fc-eadaa8a37934.json`; application_writes=0, semantic_acceptance=false.

V13 API ve document aday imajları sunucuda mevcut bağımlılıklardan ağsız build edildi; web adayı da ayrı oluşturuldu. Henüz aktif hizmetler değiştirilmedi. Üç paralel ajan kullanım limitine takıldığı için ana oturum entegrasyonu devraldı. Son kaynak hashine ait olmayan bağlam kanıtı cross-page verifier tarafından CONTEXT_MODULE_HASH_MISMATCH ile reddedildi; mevcut kaynakla yeni gerçek ölçüm başlatıldı. Eski kanıt yeni kodun kabulü yerine kullanılmaz.

## Paralel çalışma

- Kaynak/kimlik kolu: okunamayan büyük satırın içinden bağımsız ölçülen küçük bölge, ham okuyucu metni, noktalama kapıları; sayfa amacı için kaynak kapsamı notu ile kararı engelleyen belirsizliğin ayrılması.
- Anlamsal kabul kolu: bağlam kararının sürüm/hash ve ayrı denetim koşullarının sayfalar arası atıf kapısında korunması; gerçek API/PostgreSQL eşliği.
- Arayüz kolu: küçük bölge ve değişmeyen üst kaynak, otomatik sayfa amacı, yalnız doğrulanan söz parçası bağlantısı; ayrı web imajı ve dört genişlik kabul hazırlığı.
- Entegrasyon: API kayıt türleri, kuyruk batch kimliği, aynı kaynak koduyla uygulama ve ağsız okuyucu imajı hazırlığı. Yeni kuyruk üreticisi ile eski tüketici karıştırılmadan yayımlanmalıdır.

## Gerçek ölçüm ve açık sınır

R9 neslindeki gerçek 28. sayfa kırpımında PP-OCR/Tesseract sözcük eşliği ve ayrı noktalama desteğiyle küçük bir metin kaynağı üretildi. İlk başarısız ölçümler korunur. Üst satır hâlâ NEEDS_REVIEW; hiçbir ham çıktı düzeltilmedi. Bu sonuç bütün balonu veya karakterin genel kimliğini doğrulamaz.

29. sayfa bağlam pilotunda 41 API/PostgreSQL kaydı ve fragment üst kaynak hash/geometrisi doğrulandı. Qwen NARRATIVE önerdi, dört kaynak atfı geçerliydi; okunmayan bölgelerin kapsamına ilişkin belirsizlik nedeniyle mevcut kapı kabul vermedi. Ayrı hakem çalışmadığı için öneri, doğrulanmış bağlam olarak kullanılamaz. Sayfalar arası negatif kontrol 22 gerçek sayfada bu öneriyi doğru biçimde reddetti. Yeni tipli belirsizlik şeması bu ayrımı genel olarak ele alır; kabul üretmek için kitaba özel istisna eklenmez.

Kanıtlar ana sunucunun `evidence/` dizininde:

- `page-context-0eb7d199-cebc-4454-96f6-1d5cb1685986-0029-6072b5f38bbc-16dcc078b697.json`
- `cross-page-attribution-0eb7d199-cebc-4454-96f6-1d5cb1685986-bb5ad0f31aac-66543d89ec3e-900ca7f65c1c.json`

Yerel test çalıştırılmadı. Aday sürüm için gerçek üretici/tüketici kuyruğu, yeni neslin tam API/PostgreSQL kontrolü ve dolu yeni arayüz kartlarının mobil kabulü henüz tamamlanmadı. Teknik kaynak bütünlüğü ile kitabın anlamsal kabulü ayrı tutulur.
