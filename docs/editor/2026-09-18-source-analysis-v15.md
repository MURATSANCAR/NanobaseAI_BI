# V15 — kaynak kapsamı ve kaynak destekli soru taslağı

## Canlı sürüm

18 Eylül 2026: backend/document `source-analysis-v15-r5-20260918`, web `source-preview-v15-r2-20260918`. Önceki V14-r5 tam teknik kabulü ve ayrı restore tamamlandıktan, gerçek DB'de aktif iş bulunmadığı doğrulandıktan sonra yayımlandı. CPU49 backend dosyası tree SHA256 `71a90dcd7ed8337e87f89eeedae345390a0da2d94aabf25ebf5e466c2b771e75`;10 web kaynak/çıktı eşliği ve gerçek API/PG altyapı kontrolü PASS.

- API imajı: `sha256:0735cbb7f27cf7535e2dbbd94ac1a0f116e39e5cf25d39abd10daaa567e14031`.
- Document: `sha256:251568dd2d523c99f196ce11857f3b561d7f31004e996603d0ac0ea08a59bddc`.
- Web: `sha256:37c90054ed5b94fbf5189e44d324ba2801436a5c655871dabf4ebe150d135f90`.
- CPU kanıtları: `evidence/v15-r5-build-proof.json`, `v15-r5-deployment.log`, `v15-r5-release.log`, `v15-r5-infrastructure.log`.

R1–R4 V15 imajları geliştirme adaylarıdır; ana yayına alınmadı. Başarısız ilk TypeScript derlemesi `web-v15-r2-build.log` içinde korundu; soru işinin optional kimliği açıkça doğrulanarak düzeltildi, ikinci sunucu derlemesi `web-v15-r2-build-attempt-02.log` geçti. Yerel test veya yapay kitap kullanılmadı.

## Genel kod değişiklikleri

Kaynak birimleri sayfa başına dört adayla sınırlanmaz; sınırlı gruplar halinde, her birime açık işlem durumu verilerek yürütülür. Kaynak metin yeniden yazılmaz. Tam/kısmi bağlam ve atlanan aralıklar kaydedilir; gruplar arasında gerçek iş iptali/lease kontrol edilir. [Gerçek pilotlar ve kapsam sözleşmesi](2026-09-18-source-unit-coverage.md).

`source_retrieval.py` yalnız güncel anlamsal/kaynak kontrollerini geçen iddiaların gerçek destek bölgelerini kullanır. Kanıtsız tam sayfa OCR/PDF metni ve VLM betimlemesi aramaya alınmaz. Nesil+girdi hash'i ile ayrı Qdrant koleksiyonu, kaynaklı BM25+vektör araması, birleşik sıralama ve mevcut reranker kullanılır. İnsan REJECT/NEEDS_REVIEW kararları kaynak ve türetilmiş pasaj bağımlılıkları üzerinden yeniden denetlenir; eski indeks yeniden oluşturularak ret aşılamaz.

İlk gerçek editör sorusu gerektiğinde indeksi kurar. Normalize edilmiş vektörler1024/Dot koleksiyonuna yazılır; gerçek float32 readback, payload, tam kimlik kümesi ve vektör hashleri kontrol edilir. Aynı değerler PostgreSQL indeks manifestine kaydedilir; restore model/embedding çağırmadan aynı değerleri geri yükleyebilir. [Restore sözleşmesi](2026-09-18-source-preview-search-restore.md).

`source_answers.py` tek pasajla desteklenen en fazla üç cevap adayı çıkarır. Her aday ayrı kaynak/olumsuzluk/fail/konuşmacı/kip denetimi ve soru ilgisi denetiminden geçer. Serbest cevap metni kullanılmaz; gösterilen cevap yalnız geçen cümlelerden birleştirilir. Sonuç en fazla PARTIAL, destek yoksa INSUFFICIENT_EVIDENCE olur; tam kitap veya insan kabulü yükseltilmez. İndeks/inceleme değişirse eski cevap okuma sırasında gizlenir.

API kaynak nesillerini eski bütün-sayfa cevap yoluna düşürmez. `editor_preview` gerçek tamamlanmış kaynak analizi ve geçerli kaynak sınırı ister; kitabın yazma yetkisi idempotency tekrarında da korunur. `published` ve etkinleştirme kapıları açılmadı. Yeni capability yolu genel kayıt yolundan önce tanımlanır. Kaynak pasaj/indeks kayıtları gerçek API üzerinden denetlenebilir.

Frontend gerçek soru formu, aynı soru için stabil istek kimliği, gerçek iş durumu takibi ve nesil değişiminde geç yanıt engeli içerir. Yüklemeden analiz açma exact job_id kullanır. Son web imajının analiz navigasyonu64sayfalık farklı gerçek kitapla dört genişlikte geçti; kanıt ayrı API18810 kurulumunda `evidence/upload-analysis-navigation-718c19dd-07bd-4c81-80f9-a6531f822db7/verification.json`. Kaynak veya insan kararı değiştirilmedi; iki kontrollü analiz API ile iptal edildi.

## Henüz açık kabul

Yeni tam V15 kaynak nesli, gerçek soru→indeks→cevap→mobil akışı ve yeni vektörleri içeren restore kabulü henüz tamamlanmadı. R4 gerçek kayıtlarıyla64/64 pasajın API/PG kaynak bağımsız eşliği R2 adayında geçti; bu sonuç sonraki tam kabulün yerine geçmez. Yeni gerçek soru akışı `evidence/v15-r5-source-question-ui.log` ile başlatıldı. Kitabın doğru cevabı sisteme elle verilmez; hata varsa kod düzeltilir ve başarısız kanıt korunur.

## R6 düzeltmeleri — 18 Eylül, gerçek soru koşusu sonrası

R5 gerçek soru işi `0d53b588-e40e-4d0d-96ca-c8d6d3d0008b` model tarafından tamamlandı, ancak `/answers` okuması `IdleInTransactionSessionTimeout` nedeniyle 500 döndü. Kaynak/vektör doğrulaması artık kısa DB okuma/yetki işlemi kapandıktan sonra çalışır. Başarısız tarayıcı kanıtı `evidence/source-question-ui-fedaca38-5be9-465f-8fc8-b90e11fec2f9/verification.json` korundu; kaynak/inceleme/generation durumu değişmedi. Önceki iki başarısız deneme soru oluşturmayan seçici hatalarıydı; gerçek akışta select ve textarea seçicileri düzeltildi.

Aynı gerçek çıktıda yalnız `gurur-` ile biten bölgeye dayanılarak tamamlanmış sözcük kullanıldığı görüldü. Kitaba özel cevap yazılmadı: geometrik satır sonu sözcük bağımlılığı genel kodda zorunlu yapıldı. Eksik devamı olan aday aramaya alınmaz; yeni analizde kaynak birimi iki parçayı birlikte taşımalıdır. [Genel düzeltme](2026-09-18-line-end-word-dependency.md).

Boş cevap dahil her cevap kesin kaynak indeks hash'ine bağlandı. Cevap incelemesi kaynak indeksinin fingerprint'inden ayrıldı; cevap için REJECT/NEEDS_REVIEW ayrıca görünürlük kapısına bağlandı. ACCEPT tam kitap/yayın kabulüne dönüşmez. [Sözleşme](2026-09-18-source-preview-review-snapshot-fixes.md).

R6 backend/document imajları sunucuda ağsız derlendi: API `sha256:27055e864729fea3452a8859ead96a119c5c28392cbdeeb165eab8e0409d34ba`, document `sha256:4f9e7e48ed2f4533d9682f5dfdc2c1dd8ce73ac6886aa66f023b17706459ebc8`. Son web değişmedi. Canlı yeniden kabul bekleniyor; bu kod düzeltmeleri test sonucu değildir.

Triage raporundaki uygun iddia sayısı yanlış katmandan okunuyordu: kaynak adaylarının daima false kalan bayrağı yerine gerçek semantic_reviews kayıtları sayılıyor. Ayrı aday bayrağı alanı korunur. Gerçek R5 API/PG tekrarında 896/253 ve61 uygun iddia doğrulandı; `evidence/source-quality-triage-20260918T062036382660Z.json`.

### R6 gerçek kaynak sınırı düzeltmesi

R6 ilk soru işi `b6e1fd2c-4102-4dda-a275-2df62658bdb7` tamamlandı; UI koşusu cevap GET504 nedeniyle kaldı (`evidence/source-question-ui-930eac8c-adcf-43e3-8c03-60a892496eff/verification.json`). Aynı eski cevap GET artık200/NEEDS_REVIEW verdi, ancak20,364sn sürdü. Tek gerçekPG profili53pasaj current_index6,08sn, JSON/hash1,49sn ve615tekrarlı okuma sırası hesaplaması gösterdi. Tam API işlemcisi0,5CPU/512MiB ile sınırlıydı; eşzamanlı tarayıcı okumasında darboğaz oluştu.

Compose'ta API/worker sınırları ayrı çevre değişkenleriyle2CPU/1GiB varsayılanına taşındı; müşteri ortamı bunları `.env` üzerinden değiştirebilir. Aktif iş sayısı0 kontrol edilerek yalnız bu iki servis yeniden oluşturuldu. İmaj ve kitap verisi değişmedi. Gerçek konteyner sınırları doğrulandı; kanıt `evidence/v15-r6-resource-bounds.json`, ComposeSHA `ab3a4dbfdcb73675bdc5afbe1a02b92e47368ffa859dd2937d560898086c1b7c`. Bu değişiklik görev/model paralelliğini artırmaz; kaynak güvenlik kontrollerini kaldırmaz.

R6 gerçek48sayfa salt-okunur katalog bileşeni denemesinde exit137 görüldü; PASS sayılmadı, `...live-hyphen-catalogue-r4-interrupted.json` korundu. GözlenenAPIrestart1/OOMKilledfalse tek başınaOOMkanıtı değildir. Yeni kontrol sayfa başına sınırlı süreç/özetle yapılacak.

## R7 — soru taslağında kimlik yetkisinin korunması

R6 kaynak güncellemesiyle iki gerçek soru+mobil320/390/768/1440 teknik kabulü geçti; kanıt `evidence/source-question-ui-559b2406-684e-4c26-bab1-91cfc73f2649/verification.json`. İlk soru2kaynaklı iddia/PARTIAL, ikinci0iddia/INSUFFICIENT_EVIDENCE; her ikisindeAPI/PGeşit ve kaynak/inceleme/generation değişmedi. R6 çıktısının bağımsız içerik incelemesi yapılandırılmış actor alanında yer bildiren yeni etiket buldu; teknikPASSanlamsalPASSsayılmadı.

`source-answer-preview-v2`, soru katmanının kaynak pasajında doğrulanmamış yeni actor/speaker etiketi üretmesini engeller. Null dışı değer aynı kaynak alanıyla tam eşleşmelidir; altiddiada eyleyen desteklenmiyorsa modelnull seçmelidir. Uygun olmayan aday değiştirilmeden gerekçesiyle saklanır. Eski v1 cevaplar güncel gösterilmez; kaynak indeksi ve kitap metni değişmez. [Kod sınırı](2026-09-18-source-answer-identity-authority.md).

R6 bağımsız arama verifier'ı birden fazla tarihsel kod manifestini güncel saydığı için `Exactly one current source_index required` verdi; başarısız kanıt `evidence/source-preview-20260918T063007460261Z.json`. Betik önce kurulu dosyaların hash'lerini okuyup sadece bunlarla eşleşen manifesti seçmek üzere düzeltildi; tek güncel indeks zorunluluğu kaldırılmadı. R7 canlı yeniden kabulü bekleniyor.

R6 ayrı kaynak bileşeni kabulü48/48,1466birim/162sözcükbağımlılığı PASS; eski2058birime göre düşüş güvenlik dışlamasıdır, anlamsal kapsam artışı değildir. [Bölünmüş sözcük kanıtı](2026-09-18-line-end-word-dependency.md).
