# Figür kimliği: kaynaklı sonraki adım — 18 Eylül 2026

Bu belge salt okunur gerçek kaynak incelemesidir; V12-r1 backend kodunu değiştirmez ve kimlik kabulü değildir. Kitap metni, karakter etiketi veya inceleme kararı değiştirilmedi. Aşağıdaki sayfa/kimlikler yalnız regresyon kanıtıdır; üretim kuralına veya modele beklenen cevap olarak taşınamaz.

## Somut eksik

R9 nesli `0eb7d199-cebc-4454-96f6-1d5cb1685986` üzerinde API/PG karşılaştırmasında 460 kayıt eşleşti; o an tamamlanan 19 sayfanın yerel kimlik kapısında sıfır kaynaklı isim vardı. Bunun anlamı bütün isimlerin okunamadığı değildir: konuşma atıfları çoğunlukla anlatı sayfasında, figürler komşu resimli sayfadadır. Aynı balonda açık yazılı atıf + tek kuyruk şartı bu yerleşimde anchor üretmiyor.

- Sayfa 13: kaynaklı açık konuşma atfı var, kayıtlı figür sayısı sıfır.
- Sayfa 15: iki açık konuşma atfı var; bir anlatı atfının bulunması hangi resim figürünün bu kişi olduğunu kanıtlamıyor.
- Sayfa 29: üç figür ve bir tekil kuyruk eşliği var; balon figür 0'a gidiyor. Görsel karakter kapsamı `NOT_VERIFIED`. Kalan figürü eleme yoluyla adlandırmak geçerli değil.
- Eski tamamlanmış V5 nesli `14a79646-79c6-4cdb-8714-00adf5698770` on açık metin atfı içeriyor. Bunlar tarihsel teşhistir; güncel nesle kabul edilmiş veri olarak taşınamaz.

## Kimlik bilgisini bütün satırla birlikte kaybediyoruz

R9 `source_spans` anahtarı `0028-0017`, kimliği `0de406ac-4939-5a55-9cc1-6c010561d873`, `NEEDS_REVIEW`:

| Okuyucu | Kaydedilmiş ham ölçüm |
|---|---|
| Tam sayfa PP-OCR | `"Dur!" diye bağırdı Defne. "Bu görüntüyü` |
| Bölgesel PP-OCR | `Dur!" diye bağırdı Defne. "Bu görüntüyü` |
| Tam sayfa Tesseract | `“Dur!” diye bağırdı Defne. bu goruntuyu` |
| Kırpım Tesseract PSM 7 | `“Dur!” diye bağırdı Defne. Bu goruntuyu` |
| Kırpım Tesseract PSM 13 | `“Dur!” diye bağırdı Defne, “Bu görüntüyü.` |
| PaddleOCR-VL | `"Dur!" diye bağirdi Defne. "Bu görüntüyü"` |

İlk dört kelimede PP-OCR ve bağımsız Tesseract aynı sözlü içeriği okuyor. İkinci cümlenin harfleri ve noktalama uyuşmazlığı bütün satırı bloke ediyor. Bu yüzden ilk cümlenin açık konuşma atfı `text_attribution.extract` girdisine hiç girmiyor. Bu gözlem satırın elle kabul edilmesini haklı çıkarmaz; daha küçük kaynak bölgelerini sistemin yeniden ölçmesi gerektiğini gösterir.

Tesseract gerçek kelime kutuları mevcut: ilk dört sözcük x≈0,243–0,569, y≈0,736–0,757 arasında. Bu koordinatlar yeni kodda sabitlenemez; aday kırpım sınırı her kaynakta `secondary_word_regions` ve diğer okuyucuların geometrisinden türetilmelidir. Tarihsel bölgesel seçim engeli `SECONDARY_READER_CONFLICT`; VL seçimi ayrıca `PPOCR_REGION_DISAGREES`, `NO_INDEPENDENT_REGION_SUPPORT` gibi engeller içeriyor.

## Genel uygulama sırası

1. **Konumlu alt bölge yeniden okuma.** Uyuşmayan satırdaki okuyucu token hizalamasından kararlı sözcük aralıklarını ve cümle sınırı adaylarını çıkar. Yalnız sınır belirlemek için kullan; eski satır metnini kesip kabul etme. Gerçek resimden yeni kırpım al, farklı OCR motorlarıyla yeniden oku. Yeni kayıtta üst span, kutu, render/kırpım hashleri, okuyucu sürümleri ve ham yanıtları sakla. Üst `NEEDS_REVIEW` kaydı değişmez. Olumsuzluk ekleri, sayı, kişi adı ve noktalama/alıntı sınırı uyuşmazlığı ayrı kapılarda kalır.
2. **Otomatik kaynaklı atıf ve eylem kartları.** Yalnız yeni neslin doğrulanmış alt spanlarından `mention_ref`, adın gerçek karakter aralığı, söz/eylem alıntısı, `span_refs`, zaman/olay modu, nesne ve belirsizlik üret. Kaynak dizgesinde bulunmayan ad reddedilir. Okunamayan bölge üzerinden cümle birleştirilmez. Zamir çözümleri açık atıfla aynı güçte kabul edilmez.
3. **Sayfalar arası yinelenen konuşma eşliği.** Anlatıdaki açık konuşma atfını resimli sayfadaki balonun OCR metniyle karşılaştır; balonun tekil kuyruk eşliği ayrı görsel sinyaldir. Salt komşuluk veya tek kelimelik genel ünlem kimlik kanıtı değildir. Tam ve ayırt edici söz eşliği, kapsam/olay sürekliliği ve rakipsiz eşleşme gerekir. Birinci sözden sonraki ikinci tırnaklı cümleye konuşmacı aktarımı ayrıca doğrulanır; otomatik olarak varsayılmaz.
4. **Eylem/görünüş anchor adayları.** Açık isim–eylem/nesne metni ile gerçek görsel kırpımı ayrı girdiler olarak karşılaştır. Modelden isim üretmesi değil, kaynak `mention_ref` ile figür `figure_ref` arasındaki destek/çelişkiyi ve kullanılan özellikleri istemek gerekir. İsim listesi insan tarafından yazılmaz; kaynak alanlarından programatik gelir. Adayı onaylayan kontrol aynı serbest görsel açıklamayı tekrar etmekle yetinemez; kaynak resim ve metin kanıtını yeniden incelemelidir.
5. **Anchor sonrası görsel iz sürme.** Yalnız kaynaklı anchor, farklı sayfalardaki figürlere aday aktarımı başlatabilir. Çelişen görünüş, birden çok benzer figür, sahne/zaman belirsizliği veya eksik kapsama kimlik kabulünü durdurur. Aynı yazılan adlar küresel bir karakter kimliğine kanıtsız birleştirilmez.

## Eldeki ek kanıt ve sınırı

R9 `0028-0000` / `5c29f2e8-56d0-5432-b3c3-0d629684a671` doğrulanmış metninde bir kişinin bilgisayar açma eylemi açıkça yazıyor. `0028-0010` / `c74e2b87-892b-5a7e-8890-319b9f7e9290` ekran ve renkli gezegenler arasında açık isimli bir ilişki veriyor. Sayfa 29'un Qwen gözleminde bilgisayar kullanan figür ve görüntü yansıtan robot adayları var. Bunlar isim–eylem/nesne anchor çıkarımı için gerçek kaynak adaylarıdır; modelin daha önce ürettiği görünüş açıklamasına dayanarak şimdiden kimlik onaylanamaz.

Bilgisayar kullanan bir figürün adayı güçlense dahi başka bir çocuk figürüne kalan adı atamak doğru değildir: kadronun eksiksizliği, sahne eşliği ve görsel figür kapsamı doğrulanmış değil. Özellikle `figure_coverage=NOT_VERIFIED` iken eleme kapalı kalmalıdır.

R9 gerçek kırpım karşılaştırma pilotu s29 figür0–s12 figür0 için `DIFFERENT` döndürdü; 108,681 saniye, `finish_reason=stop`. Bu otomatik negatif aday elemesini göstermekle sınırlıdır; hedef figürün adını doğrulamıyor. Kanıtlar ana sunucuda:

- `evidence/figure-identity-r9-api-pg.json`
- `evidence/figure-identity-r9-real-pair.json`

## Kabul koşulları

Yeni genel alt bölge/anchor kodu yeni nesilde gerçek kaynakla çalışmalı; başarısız eski satır ve yeni bölgeler API/PG üzerinden bağımsız karşılaştırılmalı. Ad, alıntı, bbox, model/okuyucu sürümü ve parent-child kaynak bağı eksiksiz izlenmeli. Aynı ünlemin tekrarlandığı, iki benzer figürün bulunduğu, farklı kişilerin aynı adı taşıdığı ve anlatı–resim zamanının ayrıldığı gerçek örneklerde yanlış birleşme olmamalı. Diğer kitaplarda ayrıca doğrulanmadan bu kitapta elde edilen kabul genellenemez.

**Sonuç:** Eksik yalnız başka bir görsel model değildir. Mevcut satır granülerliği kaynaklı konuşma atfını bloke ediyor; ardından anlatı sayfası–resimli sayfa eşliği eksik. Önce genel alt bölge yeniden okuma, ardından kaynaklı konuşma/eylem anchor'ı ve rakip aday denetimi gerekir. Bu not bir üretim çözümünün uygulandığı veya s29 kimliğinin doğrulandığı anlamına gelmez.

## Ayrı aday kod ve gerçek alt bölge pilotu

`source_fragments.py` ve `scripts/pilot-source-fragments.py` ayrı aday olarak eklendi; çalışan V12-r1 pipeline'a bağlanmadı. Uyuşmayan üst kaydın kelime geometrisiyle en az üç kelimelik cümle sınırı aday kırpımı üretildi. Crop gerçek OCR render hashinden doğrulandı; aynı yeni kırpım PP-OCR ve ağsız reread-worker içindeki Tesseract PSM 7/13 ile okundu. Kaynak API satırı bağımsız PG satırıyla karşılaştırıldı. Üretim kaydı yazılmadı.

İlk deneyde üç okuma kelime harflerinde anlaştı, ancak PP-OCR açılış tırnağını düşürdü. `QUOTE_OR_PUNCTUATION_DISAGREEMENT` nedeniyle parça kabul edilmedi. Bu deneydeki NARRATIVE çıkarım hipotezi sonraki script sürümünde kaldırıldı; sayfa rolü gerçek `page_claims` API/PG kaydından alınır.

İkinci deney, yalnız noktalama uyuşmazlığında aynı kırpımı PaddleOCR-VL'ye `OCR:` talebiyle gönderdi. VL açılış tırnağını okudu ama raporlama fiilindeki Türkçe harfi farklı okudu. Bütün sözcükler ve noktalama birlikte uyuşmadığından kapı yine reddetti. Kaynaklı atıf sayısı sıfır; bu başarısız deney çözüm değildir. Katı kapı korunarak hangi karakter/alan için kaç bağımsız okuyucu desteğinin yeterli olacağı ayrıca değerlendirilmelidir.

Gerçek kanıtlar:

- `evidence/source-fragments-0eb7d199-cebc-4454-96f6-1d5cb1685986-page-0028-577336f8f0c7.json`: ilk noktalama reddi.
- `evidence/source-fragments-0eb7d199-cebc-4454-96f6-1d5cb1685986-page-0028-b7bc58d1fefe.json`: gerçek sayfa rolüyle üçüncü okuyucu sonrası ret.

Pilot altyapısı hataları da düzeltildi: bağımsız SQL kontrolündeki string quoting parametre bağlamaya taşındı; eski ağsız reread imajında bulunmayan seçim modülü yalnız karar aşamasında ağlı API imajında lazy-import edilir. Bunlar ürün veya kimlik kabulü değildir.

### Alanlara ayrılmış optik destek sonrası geçen gerçek pilot

Son genel kapı yeniden ölçülen tek bir okuyucunun **ham Tesseract PSM 7 metnini aynen** seçer; okuyuculardan kelime/harf birleştirmez. Sözcük dizisinin tamamı PP-OCR + Tesseract 7 + Tesseract 13 arasında eşleşmelidir. Noktalama ve tırnakların sözcük sırasına göre konumları Tesseract 7 + Tesseract 13 + PaddleOCR-VL arasında eşleşmelidir. Yalnız genel noktalama dizisi eşliği yeterli değildir: tırnağın hangi kelimeden önce/sonra olduğu da denetlenir. VL olumsuzluk çatışması veya token sayısı farkı reddedilir; VL harf farkları `vl_lexical_conflicts` içinde ham ölçümle korunur. Bu, VL harf farkını düzeltmek veya VL'yi tek otorite saymak değildir.

Gerçek tekrar `1 fragment / 1 TEXT_AGREED / 1 otomatik açık metin atfı` verdi. Gerçek `page_claims` rolü NARRATIVE, API ve PG verileri eşit; üretim DB yazımı sıfır. Parçanın `parent_record_sha256` değeri değişmemiş üst kaydın canonical JSON hashidir. Son aday kod ve yeniden ölçüm kanıtı:

- `evidence/source-fragments-0eb7d199-cebc-4454-96f6-1d5cb1685986-page-0028-fac346ed30f5.json`.

Atıftaki söz yalnız tek kelimedir. Bu sonuç s29 figürünün kimliğini doğrulamaz; çapraz sayfa kapısı kısa/tekrarlanabilir sözleri tek başına anchor kabul etmemelidir. Geçen şey optik alt bölge ve metindeki açık atıftır.

Üretim adayı `run(job, root)` ayrı `batch_key` destekli reread kuyruğunu kullanır; batch başına en fazla 256 bölge, sabit aday anahtarlarıyla yeniden başlama, queue crop/TSV hash doğrulaması ve aynı kırpıma PP/VL çağrısı vardır. Sonuçlar ayrı immutable `source_fragments`, kapsam ve limitler `fragment_checks` kaydına gider. Üst `source_spans` değiştirilmez. Bu üretim kuyruğu entegrasyonu henüz gerçek yeni nesilde doğrulanmamıştır; çalışan V12-r1 davranışının değiştiği iddia edilmez.

### Kaynak bağlamıyla sayfa amacı denemesi

`verify-page-context.py`, gerçek komşu kaynaklar ve geçen fragment sidecar'ı ile `page_context.classify` adayını uzak API ortamında çalıştırdı. 41 API/PG kaydı ve fragment parent hash/geometrisi eşleşti. Tamamlanmamış komşu sayfa bağlama boş sayfa olarak eklenmedi. Beklenen rol veya konuşmacı verilmedi; veriler doğrudan kayıtlardan alındı.

İlk iki sürümde model dayanak olarak inceleme bekleyen üst kaydın kimliğini seçti; `INVALID_PAGE_CONTEXT_CLASSIFICATION` ile reddedildi. Genel giriş düzeltmesi bu bölgelerin atıf kimliğini kaldırdı ve `can_cite=false` yaptı. Pilot fragment'in ham ölçüm hash'i üretim kayıt kimliği değildir: son verifier, metin/proof alanlarına dokunmadan üretimdeki parent-key/bbox-hash/UUID5 şemasını yeniden üreterek `persisted=false` projection map kaydetti.

Son ölçümde model NARRATIVE önerdi ve dört geçerli kaynak atfı döndürdü; ancak şu belirsizliği ekledi: “Sayfadaki UNVERIFIED_REGION bölgelerinin içeriği bilinmemektedir; ancak okunabilir metinler anlatı akışını desteklemektedir.” Mevcut kapı herhangi bir belirsizlikte inceleme istediğinden `eligible_for_identity_context=false` kaldı ve ikinci model denetimi çalışmadı. Sayfa rolü veya kimlik elle kabul edilmedi. Belirsizliğin kaynak kapsamı mı sayfa amacı mı olduğu sonraki genel sözleşmede ayrıştırılmalıdır; bu sonuç anlamsal kabul değildir.

Son kanıt: `evidence/page-context-0eb7d199-cebc-4454-96f6-1d5cb1685986-0029-6072b5f38bbc-16dcc078b697.json`.
