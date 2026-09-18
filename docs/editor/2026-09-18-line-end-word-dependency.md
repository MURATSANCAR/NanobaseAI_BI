# Satır sonunda bölünen sözcüğün kaynak bağımlılığı

Gerçek kaynak soru koşusu `0d53b588-e40e-4d0d-96ca-c8d6d3d0008b` incelemesinde bir cevap, yalnız satır sonunda tireyle yarım kalmış sözcüğü içeren bölgeye atıf vererek tamamlanmış sözcük anlamını kullandı. Önceki `incomplete_word_refs` denetimi yalnız ayrık baş harfi koruyordu; satır sonu sözcüğünün devamını zorunlu kaynak bağımlılığı saymıyordu. Bu, genel bir kaynak kapsamı hatasıdır; kitap metni veya cevap elle düzeltilmez.

## Genel düzeltme

`source_unit_claims.py` içindeki yeni `hyphen_pairs`, `\w-` ile biten her satırın komşu devamını denetler. Devam yalnız aynı PDF sayfası/render hash'i, ardışık geometrik okuma sırası ve mevcut `reading_segments` ile aynı alt satır/mesafe/yatay örtüşme koşullarında bağlanır. İki tarafın da TEXT_AGREED/TEXT olması ve devamın sözcük karakteriyle başlaması gerekir.

Kaynak seçimi iki tarafı birlikte taşımıyorsa eksiktir. Komşu devam bulunamıyorsa, geometrisi belirsizse veya taraflardan biri okunamamışsa kaynak kapısı kapalı kalır. Tamamlama tahmini yapılmaz; ham OCR metni değiştirilmez. Bağımlılık hem önek hem sonek tarafından denetlenir; yalnız soneki seçmek de tam sözcük kanıtı sayılmaz. Üçten fazla bölgeye uzanan bir sözcük zinciri mevcut birim sınırına sığmıyorsa kesilerek kabul edilmez.

`verify-source-analysis.py` aynı bağımlılığı uygulama yardımcı fonksiyonunu çağırmadan, gerçek kaynak geometrisinden bağımsız kurar. Eksik birliktelik `UNIT_PARTIAL_LINE_END_WORD` ile reddedilir. Mevcut drop-cap, quote, reading-view ve kapsam kontrolleri korunur.

Yalnız bu iki dosya değiştirildi. `source-unit-claims-v3` yöntem etiketi korunmuştur; **değişen kod hash'i yeni R6 yayın/nesil manifestine bağlanmalıdır**. Eski v3 kataloglarının eski verifier ile aldığı kabul, yeni sözcük bağımlılığı sözleşmesinin kabulü değildir. Eski cevaplar korunur; yeni kod ve güncel kaynakla sistem yeniden denetlenmelidir.

## Kabul sınırı

Yerel test, model çağrısı, ana koşu veya deployment çalıştırılmadı. Bu kayıt kod düzeltmesini belgeliyor; gerçek başarısız senaryonun yeni yayın üzerinden tekrar kabulü root tarafından yapılacak. R6 gerçek kaynak/cevap/alıntı kapısı yeniden doğrulanana kadar **DOĞRULANAMADI**. Kitap adı, sayfa numarası, karakter veya beklenen cevap üretim koduna eklenmedi.

## R6 gerçek bileşen koşusu — yürütme kesintisi

R6 yayımlandıktan sonra gerçek R4 kaynak nesli `08ca6877-6e30-4bb3-b1fa-767f048248e4` üzerinde API/bağımsız PG verisiyle 48 sayfalık katalog ve sözcük bağımlılığı denetimi başlatıldı. Model çağrısı veya uygulama kaydı yazımı yoktu. Tek API container sürecinde çalışan kontrol sonuç üretmeden exit137 ile kesildi; bu bir kaynak/anlam kararı veya PASS değildir.

18 Eylül06:25:36UTC salt okunur durum gözleminde aynı `nanobase-editor:source-analysis-v15-r6-20260918` container'ı running, restart_count1, son başlangıç06:24:49UTC ve `OOMKilled=false` idi. Exit137 tek başına OOM nedenini kanıtlamaz. Root eski API sınırlarının512MB/0,5CPU olduğunu bildirdi; kaynak ayarı ve yeniden deneme koordinasyonu root'tadır.

Kanıt `/data/nanobaseai/editor/evidence/v15-r6-live-hyphen-catalogue-r4-interrupted.json`; sonuç üretilmediği ve otomatik tekrar yapılmadığı açık kayıtlıdır. Başlangıç kod hash'i kontrolü scriptte bulunmasına rağmen tamamlanmamış süreç doğrulanmış hash/katalog kabulü sayılamaz. Kaynak düzenlemesi sonrası daha küçük, sayfa başına ayrı süreç ve özet çıktıyla yeni koşu ayrıca kaydedilecektir; mevcut kesinti kanıtı silinmez. Gerçek 48 sayfa bileşen kabulü hâlâ **DOĞRULANAMADI**.

## R6 kaynak sınırı güncellemesi sonrası gerçek bileşen kabulü

Root API sınırını 2CPU/1GiB olarak güncelledikten sonra, değişmeyen R6 uygulama imajında yeni ve sınırlı koşu yürütüldü. Her sayfa kendi API/PG okuması ve ayrı Python süreciyle doğrulandı; tüm kitabın kaynaklarını API container belleğine tek seferde yükleyen önceki yöntem tekrarlanmadı. Yeni kanıt `evidence/v15-r6-live-hyphen-catalogue-r4-pagewise.json`; eski137 kesinti kanıtı korunur.

Gerçek R4 nesli `08ca6877-6e30-4bb3-b1fa-767f048248e4` üzerinde **48/48 sayfa bileşen bütünlüğü PASS**: 1.466 değişmez kaynak birimi ve 162 satır sonu sözcük bağımlılığı bağımsız geometrik referansla denetlendi. Her sayfada çalışan modül SHA256 `a1136a886944580b67176a2052a40651ac943a85e298e7f6e00e0d9dfa6bd8ac` doğrulandı. API kaynakları bağımsız PostgreSQL sorgusuyla eşleşti. Kaynak ve inceleme kayıtlarının önce/sonra özetleri aynı kaldı; ayrıca her sayfanın kaynak SHA256 değeri kanıtta bulunur. Model çağrısı, yeni iş veya uygulama kaydı yazımı sıfırdır.

Başarısız gerçek s13 senaryosunda `8459887e-0f74-5703-87df-9b684a8e2870` bölgesi TEXT_AGREED, geometrik devamı `5f39ae46-c652-5d59-a4fc-875ce1a8df43` ise NEEDS_REVIEW'dur. Bu nedenle yalnız önek değil, önek ve devam birlikte seçildiğinde de kaynak kapısı kapanır. Devam bölgesi ayrıca sonraki bölgeyle başka bir satır sonu sözcük bağı taşır. Sonek tek başına seçimi de reddedildi. Kaynak metin veya bu durumlar elle değiştirilmedi.

- s13 kaynak sayfası SHA256: `92e92ecde6c6c0ab905126b97463586209ab76f42f2c7d3126dad3436384df15`.
- Önek özgün kayıt SHA256: `ae2d1b300c13a29e45ad45d46cfcc74af285ef12c8833cebf1dbf5d5b7fd71ef`.
- Devam özgün kayıt SHA256: `7041011f3c47202fd97165053cd84934d4e922948fa87adc60e4480ff3a39254`.

Önceki R4 birim planındaki2.058 katalog biriminin yeni kuralla1.466'ya düşmesi daha fazla anlamsal başarı değildir; eksik sözcük kanıtının dışarıda bırakılmasıdır. Bu sonuç canlı R6 **kaynak birimi/sözcük bağımlılığı bileşen kabulüdür**. Yeni tam V15 nesli, sorunun R6 uçtan uca cevap kabulü veya kitabın anlamsal kabulü yerine geçmez; bunları root ayrı gerçek koşularla doğrular.
