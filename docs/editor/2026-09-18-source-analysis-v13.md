# V13 hazırlığı: küçük kaynak bölgeleri ve sayfa bağlamı

Bu kayıt aday geliştirmeyi anlatır; V13 henüz canlı yayın veya tam kitap kabulü değildir. Canlı API/worker V12-r1 olarak çalışmaya devam eder. Kitap içeriğine elle müdahale edilmez.

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
