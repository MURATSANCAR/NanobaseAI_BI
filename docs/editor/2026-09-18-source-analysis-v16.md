# V16 adayı: kaynak bağlamından sonra iddia çıkarma

## Gerçek hata ve sınırı

V15-r7 nesli `382da5b3-a13a-4986-85ba-1a38fd92ff44` içinde PDF29'un altı kaynak birimi NO_CLAIM olmuş; model balondaki soruyu etkinlik yönergesi saymış ve hiç iddia üretmemiştir. Özgün sayfa render'ı bağımsız incelendi; bu bir balon diyaloğudur. Render SHA256 `27e900ff76c22e9b36a5fcbad3704f10a25df61fd374d66cecf1d4620d063b84`, gerçek evidence kaydıyla aynıdır. Önceki tamamlanmış R5 neslinin aynı sayfa için kaynak bağlamı sınıflandırması NARRATIVE/STORY_WORLD ve desteklidir. Bu eski sonuç yeni neslin anlamsal kabulü değildir.

Genel hata: aday önerici, bütün kaynaklar ve komşu sayfa bağlamıyla yapılan ayrı amaç denetiminden önce sayfayı yeniden sınıflandırıyordu. Yanlış ilk sınıf, diyalog adaylarını sıfırlıyor; sonradan doğru amaç sınıfı üretilse bile kaybolan adayları geri getirmiyordu. Kaynak birimi muhasebesinin tam olması bu anlamsal eksikliği kapatmaz. Sayfa/kitap/karakter istisnası eklenmedi, beklenen kitap cevabı modele verilmedi.

## Genel kod düzeltmesi

- `source_pipeline.py`, `source-spans-v16`: önce sayfaların optik/görsel kaynakları ve doğrulanabilir alt bölgeleri; ardından kaynak bağlamı; sonra iddia adayları. Öncelikli sayfalar işleme sırasını etkiler, bağlam hash sırası `record_key` ile sabit kalır.
- `page_context.py`, `source-page-context-v5`: amaç sınıflandırması artık aday kayıtlarına bağımlı değildir. Her model çağrısından önce/sonra iptal ve lease kontrolü yapılır. Kayıt `BEFORE_CLAIM_PROPOSAL` aşamasını ve adayların girdi olmadığını açıkça taşır.
- `source_unit_claims.py`, `source-unit-claims-v4`: zorunlu, kaynak hash'i doğrulanmış amaç kaydı önericiye verilir. Soru/emir gibi söz edimleri gerçekleşmiş olay veya olumlu cevap yapılmaz. Kimlik belirsizse isim üretilmez. Önericinin farklı amaç sınıfı üretmesi kabul edilmez ve ilgili birimler incelemede kalır.
- Kaynak amacı belirsiz veya öykü dışıysa model çağrılmaz; birimler açık NEEDS_REVIEW olur. Bu durum NO_CLAIM veya tamamlanmış anlam analizi gibi gösterilmez. Ham kaynak ve insan kararları değişmez.
- V16 kaynak önizleme destek listesine eklendi. Tam kaynak denetleyicisi V3 kabulünü koruyup V4 amaç hash'i, çağrılmayan gruplar ve ledger sözleşmesini ayrıca kontrol eder. Gerçek bileşen pilotu API/bağımsız PG eşliğini ve önce/sonra kaynak-inceleme parmak izlerini denetler.

## Gerçek aday kontrolleri

CPU `/data/nanobaseai/editor` üzerinde R5'in değiştirilmemiş gerçek kaynaklarıyla iki bileşen kontrolü geçti: PDF45 bilgilendirici kapsamda 21 birim incelemede; PDF6 anlaşılmış hedef metni olmayan boş katalog. İkisinde de model çağrısı sıfır, API/PG eşliği doğru, kaynak/inceleme kayıtları değişmedi. Kanıtlar:

- `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0045-81e67eb13e9d.json`
- `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0006-81e67eb13e9d.json`

Bu kontroller V4 önericinin güvenli engelleme yoludur; V5 sınıflandırıcının veya V16 tam akışın kabulü değildir.

Gerçek ilk diyalog pilotu `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0029-49eae25011c8.json`: iki aday üretildi, ancak biri çok satırlı sorunun sadece son satırını kaynak seçti; atıf kapısı doğru şekilde engelledi. Genel kök neden balon metninin bölünebilmesiydi.

`source-unit-claims-v4` şimdi tekil geometrik balondaki bütün TEXT_AGREED satırlarını bölünmez ham kaynak birimi yapar. Çakışma, kısmi/okunmayan kutu, kesilme veya kopuk okuma sırası inceleme gerektirir; balonun alt parçalarını prose penceresiyle kaçırmaz. Layout kayıt/hash/bbox ve tüm kaynak kimlikleri taşınır. Gerçek katalog kontrolünde üç satır tek birim oldu; `evidence/atomic-balloon-v16-catalogue-preflight.json`. Gerçek model pilotu `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0029-871f780ceb5d.json`: bir aday, bütün üç satır, actor/speaker null. İlk semantik kontrolde anonim kimlik alanı yanlışlıkla bilinmeyen isim kanıtı gibi değerlendirildi.

`source-semantic-review-v6` anonim söz edimi ile kimlik atamasını ayırır; metindeki ad/rol iddiası null alanlarla gizlenemez. Aynı değiştirilmemiş model adayı gerçek sunucuda yeniden değerlendirildi: `evidence/semantic-candidate-7280af899f9e2a9b129a.json`, bir kaynak destekli ifade geçti, kaynak/inceleme yazımı sıfır. Bu figürün karakter kimliğini doğrulamaz.

V6 ayrıca kaynak dışı isim yüzeyi kapısı, belirsizlik derecesini koruyan epistemic_strength ekseni ve sentezde kaynak kapısını içerir. R7'nin 100 gerçek iddiasındaki beş kaynak dışı ad bu kapıda engellendi; küçük harfli konum/sahiplik gibi anlamsal sorunlar bundan ayrı açıktır. [İddia inceleme kaydı](2026-09-18-semantic-source-audit.md).

## Derleme ve açık kabul

Önceki V16-r1/r2 imajları sonraki balon ve anlamsal sözleşme değişikliklerini içermez; yeni yayın için kullanılamaz. Son kaynakla yeni imaj, yeni tam V16 nesli ve aynı sürümde kaynaklı soru/restore/mobil kabulü gerekir. V16 henüz ana yayında değildir. Global karakter kimliği ve bütün kitabın edebî doğruluğu bu düzeltmeyle otomatik tamamlanmaz. Yerel test veya yapay kaynak kullanılmadı.

## V6 gerçek ret testi ve V7 adayının gerekçesi

V6 salt okunur gerçek kayıt tekrarı `evidence/cited-semantics-probe-20260918T084907076324Z.json`: 19 iddiada 17 model PASS, iki ret; API/PG ve korunan kayıt hashleri aynı. Ancak model, kaynakta olmayan konumu gerekçesinde kabul ettiği hâlde çekirdek olay uyuyor diye PASS verdi; bir “galiba” kaybını ve adsız sahipliği de geçirdi. **V6 anlamsal kabulü başarısızdır; yayımlanmadı.**

V7 adayı iki ek kapı uygular. Genel kaynak belirsizliği kapısı, açık ihtimal tanığı olan kaynakta iddiadan bu niteliğin tamamen silinmesini incelemeye ayırır. Gerçek 19 kayıt tekrarında dört blokaj, bunların üçü önceki model PASS; model çağrısı ve veri yazımı sıfır. Bu sınırlı sözlük/biçim denetimi kapsamı doğrulamaz, bazı geçerli parafrazları da incelemeye ayırabilir. Son normalizasyonlu kanıt `evidence/source-qualification-probe-a7e6943a-6838-40df-a1c5-2f1080a533d0.json`.

Diğer kapı iddianın her token/karakter aralığı için ayrı kaynak desteği ister; tek desteksiz ayrıntı bütün ifadeyi engeller. İlk pilotta modelin literal karakter konumlarını üretmesi 16 biçim hatası verdi (19 kayıtta bir PASS, iki anlamsal ret); bu sonuç kalite başarısı sayılmadı. V2 sözleşmesi modele yalnız önceden verilmiş kaynak token kimliklerini seçtirir; metin/konum/hash OCR kaynağından kodla üretilir. Bu genel düzeltmenin aynı gerçek kayıtlardaki pilotu sürüyor. Kaynak veya model cevapları elle değiştirilmedi. V7 citation ve sentez akışına bağlı aday kodun henüz yeni tam nesil/yayın kabulü yoktur.

## Kimlik hattında iki sayfa-rolü otoritesi

R7 gerçek kayıt tanısı `evidence/identity-blocker-audit-075e68f7-be7e-4781-b25b-4a71d5cfaf9c.json`: 48 sayfada iki balon bağlantısı, dokuz sayfada 11 açık metin atfı, sıfır adlı figür çapası. Bir balon sayfasında kaynak amacı geçerken daha erken aday sınıfı ACTIVITY kaldığı için character_evidence atıfları boş oluşturulmuş. V16'da amaç önce hesaplanır, geçen amaç önericinin page_role değerine bağlanır ve metin atfı ardından üretilir; iki otoritenin ayrışmasını genel sıra düzeltmesi kapatmalıdır. Yeni tam nesilde gerçek kontrol gereklidir. Bu değişiklik metinde olmayan ismi üretmez; doğru rol sonrası açık ad kaynağı bulunmazsa figür kimliği yine UNKNOWN kalır.

## V16 rol sıralaması ve kimlik sınırı

R7'deki29sayfa rol ayrışması V16'nın genel sıralama değişikliğiyle hedefleniyor: kaynak sayfa amacı önce belirlenir; proposal sonunda passedpage_purpose.page_role esas alınır; interpret içindeki character_evidence.extract bundan sonra bu rolü kullanır. Yeni tam V16 neslinin gerçek kaynak kanıtı olmadan ayrışma giderildi denmez. Açık ad/atıf kaynağı yoksa bu düzeltmeden sonra bile adlandırılmış görsel dayanak0kalabilir. Kitaptan isim sağlanmaz; yeni identitykoduna bu adımda dokunulmadı.

## Son bileşenler ve imajlar

Dayanak V3 gerçek 19 kayıt tekrarında 19/19 biçim/kapsam bütünlüğü geçti; 14 model PASS, beş inceleme. Kaynaksız konum ve sahiplik retleri korundu. Bağlacın kaynakta harfiyen bulunmaması gerekçesi düzeldi; aynı ifadenin zaman yorumuna ilişkin inceleme devam eder, tamamen doğru ilan edilmedi. Kanıt `evidence/source-obligations-probe-20260918T090037859420Z.json`; ayrı verifier gerçek 14 PASS kaydını model çağırmadan yeniden kurdu: `evidence/source-obligation-reference-probe-ee3db84b-8de0-4103-ac12-311f476d83f2.json`.

Final birleşik V7 pilotu `evidence/semantic-v7-integrated-probe.log`: aynı 19 kayıt, ardından daha önce üretilmiş anonim diyalog adayı; kaynak değiştirmeden, destek modüllerinin ayrı SHA değerleriyle yürütülür. Henüz tam nesil kabulü değildir.

V16-r3 CPU ağsız derlemesi `evidence/v16-r3-build-proof.json`: iki imajda tüm 52 backend dosyası/40 Python modülü birebir; bağımlılık kilitleri canlı taban imajlarla aynı, fazladan Python dosyası yok. API imajı `sha256:1f42da70e7cbcff01ddff406af6c19bfd631d5b3b69de64a35d6b59e016c97e3`, document `sha256:5be33687532c5c7028c4d1aa929637824ad5a160669a2f866005edf4e1e4ea1c`. Derleme servis başlatmadı ve yayını değiştirmedi.

## Birleşik kabul sonrası iki ek genel düzeltme

İlk birleşik V7 `evidence/cited-semantics-probe-20260918T090405005153Z.json`: 19 kayıtta10PASS/9ret; kaynak dışı ad, konum, sahiplik ve iki belirsizlik kaybı engellendi. Bununla birlikte ilk lexical kapı doğru bir olayı sonraki cümlenin “belki” sözcüğüyle engelliyor, öneri bildiren bir anlatımı da kesinlik sayıyordu. Dört lexical ret, dört doğrulanmış hata demek değildir. V2 yalnız iddianın bütün tokenları aynı kaynak cümlesinde sıralı eşleştiğinde kapsamı o cümleye daraltır; bütün eşleşmeleri birlikte alır, belirsiz sınırda tam kaynağa döner. Öneri bildiren dil tanığı eklendi; bu anlamsal kabul değildir. Aynı19gerçek kayıt tekrarında iki gereksiz ret kalktı, iki belirsizlik kaybı engeli korundu: `evidence/source-qualification-probe-6c372a12-1164-4bd2-a25e-dde465a08bf6.json`; bağımsız tüm gate sözleşmesi `evidence/qualification-reference-055ead26-a729-407f-9617-3fb849913c32.json`.

Anonim diyalog adayında eklenen “kişi/varlık” sınıfını yeni kapı reddetti: `evidence/semantic-candidate-fd7bed33c913c645651b.json`. Kapı gevşetilmedi. Önericiye kaynak özne türü vermiyorsa tür eklemeyen, öznesiz söz edimi kuran genel kural eklendi. Yeni gerçek aday, actor/speaker null ve aynı bütün alıntıyla tür eklemeden oluştu; henüz ayrı birleşik anlamsal kontrol gerektirir. Atomik kaynak biriminin tek önerme demek olmadığı da genel sözleşmede netleştirildi; aynı birimden birden fazla ayrı, kaynakla tam destekli aday üretilebilir. Kitap cevabı veya örnek cümle modele verilmedi.

Bu değişiklikler R3 imaj/stage sonrasıdır; R3 dağıtıma uygun değildir. Son kaynakla R4 derlemesi ve yeni gerçek birleşik kabul gerekir.

## R4 birleşik aday ve yayın hazırlığı

Yeni öznesiz önerici aynı atomik kaynak biriminden iki ayrı söz edimi üretti; kaynak metni/ref/hash değişmedi: `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0029-d7548e4782e1.json`. Yeni birleşik koşu `evidence/semantic-v7-r4-integrated-probe.log`, PID1763790: önce19kayıt, sonra bu iki aday; eski nesle yazım yok.

R4 ağsız derleme `evidence/v16-r4-build-proof.json`: API `sha256:96ccb20acef0bbb452b1223c250881439341d79c03c862a70e202bc87cfdcd58`; document `sha256:d8988ced104fa28bb826694c962aeb521c449194c8b58df364a68b177d24ce60`. Her imajın52dosyası/40Python modülü snapshotla exact; kilitler taban imajlarla aynı. Bu imajlar derlenmiştir, henüz ana yayına alınmamıştır.

## R5: anonim söz ediminin gerçek birleşik kabulü

Dayanak V4 genel dil sözleşmesi, belirsiz artikelin kendiliğinden kesin sayı iddiası olmadığını ve edilgen söz ediminin bilinmeyen fail adı gerektirmediğini açıklar. Özel isim/tür/konum/sahiplik ve literal-ID kapıları korunur. Kitaba özel örnek veya beklenen cevap eklenmedi. Aynı iki gerçek aday V7+qualificationV2+obligationsV4 ile geçti: `evidence/semantic-candidate-b3a4aa7e9d89c618bef3.json`; bağımsız gerçek API/PG/literal/claim-hash denetimi `evidence/anonymous-obligation-reference-2371eda7-9adf-4669-9b6a-b47cd7e446b0.json` PASS, model çağrısı0, kaynak değişimi0. Karakter kimliği hâlâ UNKNOWN; bu isim kabulü değildir. Aynı19kayıtlı iddia regresyonu `evidence/semantic-v7-obligations-v4-regression.log` içinde sürer.

R5 imaj kanıtı `evidence/v16-r5-build-proof.json`: API `sha256:c8a6281486154b1f9826b18f0528ccd923cced04ebcd2f89ec0bb45bbee31676`, document `sha256:036205ed10eadb5334e6bc637b4c6b897a59230c0e409f494564fac3468f5bfd`;52backend/40Python dosyası exact, fazladanPython0, bağımlılık kilitleri aynı. Bu son aday R4sonrası dil sözleşmesini içerir; ana yayın/yenitamnesil henüz başlatılmamıştır.

## R5 canlı dağıtım ve yeni tam nesil — güncel

Son V7 + qualification V2 + obligations V4 birleşik gerçek tekrar tamamlandı: 19 iddiada 12 PASS/7 inceleme, kaynak dışı ad/konum/sahiplik ve iki belirsizlik kaybı retleri korundu. Kanıt `evidence/cited-semantics-probe-20260918T092045325887Z.json`; bağımsız 12 PASS dayanak yeniden kurması `evidence/source-obligation-reference-probe-d33ddd41-1f79-4f3b-958a-f2f0c75420c8.json`. Bu örnek kabulüdür, bütün kitabın anlam kabulü değildir.

Temiz main `1200bdd859bd9b704e62f3af754cea81f27a20f0` ile 234 uygulama dosyası tam stage olarak taşındı. R5 API/document imajları yukarıdaki son build proofuyla, P5 web imajı `sha256:24b8476a1d5b5db80d1dd5b1209c364d1cb62fb4793e81784383a05689da0821` ile eşleşti. Dağıtım **PASS**: `runtime/before-source-analysis-v16-r5-20260918-150cb61f-a9b2-48df-a669-274a0686088f/deployment-result.json`; log `evidence/v16-r5-deployment.log`. Gerçek `/v1/system` R5 sürümünü ve altyapı hazırlığını doğruladı. Yukarıdaki “ana yayına alınmadı” notları önceki aday aşamalarının tarihçesidir.

Yeni iş `8032d654-bf44-4462-aca4-962d6f68d030`, nesil `116bb4a8-b7b5-45dd-9986-ac80fd706533`; başlangıç kanıtı `evidence/source-analysis-v16-r5-start.json`. Tam kaynak/anlam/kimlik/sentez sonuçları henüz kabul edilmedi. Kitap kaynağı, model cevabı veya inceleme kararı elle değiştirilmez; yeni nesil kendi gerçek model sonuçlarıyla ilerler.

R5 offline paket ve gerçek CPU import 09:30:26 UTC’de PASS: `evidence/v16-r5-offline-import-proof.json`. Paket `/data/nanobaseai/editor-qualifications/v16-r5-20260918/release/offline`; manifest SHA256 `0c835451a89f00a8b0e0f8a6ed81454d2ee12215981df08c01ebbbd35fb0c647`. 238 paket dosyası/sekiz imaj kimliği ve yeni web11kaynak/tüm çıktı hashleri doğrulandı. 233 değişmeyen kaynak clean main ile eş; `.env.example` belgeli kurulum dönüşümüdür. Paketleme/import model çağrısı veya uygulama restartı yapmadı. [Paket kapsamı](2026-09-18-v16-r5-offline-package.md).

R5 dolu kaynaklı soru/UI/indeks ve ayrı restore kabulü yeni nesil tamamlanınca yapılmalıdır. Eski R7 soru kimlikleri R5 restore kabulünde kullanılmaz. GPU yönetim VPN erişimi nedeniyle internet kapalı soğuk açılış hâlâ DOĞRULANAMADI. Genel karakter kimliği, edebî rubrik ve kontrollü düzeltme-bağımlılık yenileme açık kalır.

## P5 sonraki genel geliştirme — salt okunur kod incelemesi

Mevcut `book_api.py:488 visual_correction` yalnız eski `visuals` kaydını kabul eder; etkin işler yokken, BUILDING ve henüz scenes oluşmamış nesille sınırlıdır. Bu yol `analysis.py:251 scenes` tarafından tüketilir; güncel source_pipeline için genel kaynak yeniden işleme sözleşmesi değildir. `book_api.py:514 review` sürüm kontrollü review ekler fakat yeni analiz işi veya bağımlı kayıt yenilemesi başlatmaz. `source_dependencies.py:55 impact` yalnız okur ve açıkça complete=false döndürür. `SourceImpact.tsx:44` etkiyi gösterir; yeniden hesaplatma komutu yoktur. Bunlar kontrollü düzeltme akışının tamamlandığı anlamına gelmez.

Önerilen sıradaki sınırlı iş: **snapshot bağlı yeniden işleme planı**. Önce salt okunur plan API'si hedef kayıt, kaynak/hash, review sürümü ve kod manifestini sabitlesin; güvenilir açık bağımlılıklarla çıkarılan aşamaları ve çözülemeyen kapsamı ayrı göstersin. Etki grafiği eksik olduğundan kısmi listeyi tam yenileme planı saymasın; kapsam ispatlanamıyorsa yeni tam nesle yöneltsin. İkinci adım, bu planı idempotency ve snapshot kontrolüyle yeni nesil/gerçek işe çevirsin; eski kayıtları değiştirmesin, kaynak metni/kimlik/review kararını otomatik düzeltmesin. Yeniden okumayı ve analizi yine sistem üretsin. Uygulama alanları book_api, source_dependencies, source_pipeline/job dispatch ve SourceImpact olacaktır.

Gerçek kabul yolu: tamamlanmış gerçek nesilde planın kaynak/API/PG bağlantıları bağımsız karşılaştırılır; yetkili plan çalıştırıldığında yalnız bir yeni job/nesil oluşması, eski kaynak/review hashlerinin korunması ve yeni kayıtların kendi kod/kaynak hashlerine bağlanması sınanır. Kaynak/snapshot değişirse eski plan 409 ile reddedilir; yeni sonuçlar gerçek kaynak/semantik kapıları geçmeden önceki cevap veya indeks kabulü miras alınmaz. Aktif R5 koşusunda bu geliştirme uygulanmadı; canlı kaynak ve review yazımı yapılmadı.


## İlerleme odağı — kullanıcı geri bildirimi

Kullanıcı küçük düzeltmeler ve yeni tam koşular nedeniyle planda somut kapanış göremediğini bildirdi. Mevcut R5 koşusu sabit kodla tamamlanacak; yeni P5 yeniden işleme planı adayı yayınlanmayacak. Teknik sayfa PASS, anlamsal kitap kabulü veya P0–P7 kapanışı değildir. Yeni tam koşu ancak tamamlanan çıktıda kanıtlanan genel kök neden düzeltmesi bunu gerektiriyorsa başlatılır; mevcut sonuçları değerlendirmeden bir sonraki sürüme geçilmez.

Kapanış sırası: (1) mevcut neslin48sayfalık kaynak/iddia muhasebesi, (2) figür–karakter ve anlamsal retlerin tek kök neden listesi, (3) aynı neslin gerçek soru/API/PG/Qdrant kabulü, (4) aynı frozen sürümün dolu restore kabulü. Yan özellikler bu sıranın yerine geçmez. İlerleme bildirimleri kapanan plan maddesi, doğrulama kanıtı ve açık kalan nedeni içerecek.
