# Logo 1205 yeniden deneme kanıtı — 30 Eylül 2026

## Sonuç ve sınırı

Tamamlanan `composable-r6/CP043.json` içinde **bir doğal ürün 1205 olayından sonra ikinci denemede başarılı SQL okuması** gözlendi. Bu teknik toparlanma kanıtıdır; sorunun tam ve sayısal olarak doğru cevaplandığı anlamına gelmez. CP043 bağımsız kabul sonucu **UNVERIFIED**: referans okumaları arasında kaynak değişmiş, net satış karşılaştırmasında fark bulunmuştur. API ayrıca açık CRM kaynak eksikliğiyle `PARTIAL_ANSWER` vermiştir.

İnceleme yalnız test sunucusundaki mevcut kabul JSON dosyalarını okudu. Yeni DB/API sorgusu, kilitlenme üretme, ürün koşusu veya servis yeniden başlatma yapılmadı. Mevcut SSH ControlPath kullanıldı. Ürün kodu değiştirilmedi.

## Gözlem zamanları ve kapsam

Kanıt kökü: `/data/nanobaseai/bi/acceptance/finance-expanded-20260930/`.

- İlk görüntü: **2026-09-30 19:11:32 UTC / 22:11:32 İstanbul**. Altı koşuda 145 vaka; 142 cevapta `semantic.readRetries` mevcut ve boş, üçünde alan yoktu. r6 henüz 27 vaka kaydetmişti. O anda ürün toparlanması doğrulanamamıştı; bu nihai sonuç değildi.
- Güncellenmiş görüntü: **2026-09-30 19:18:27 UTC / 22:18:27 İstanbul**. Aynı altı koşuda 163 vaka; 160 cevapta alan mevcut, bunların **birinde dolu**, üçünde alan yok. r6 artık 45/45 tamamlandı. Bu kapsam yeni 100 soru koşusunun veya diğer koşuların nihai taraması değildir.

| Koşu | Vaka dosyası | `readRetries` mevcut | Dolu |
|---|---:|---:|---:|
| composable-r3 | 43 | 43 | 0 |
| composable-r4 | 35 | 32 | 0 |
| composable-r5 | 4 | 4 | 0 |
| composable-r6 | 45 | 45 | 1 |
| crm-r1 | 5 | 5 | 0 |
| crm-r2 | 31 | 31 | 0 |

Alan yokluğu veya boş liste, ortamda hiç deadlock olmadığı sonucunu vermez; yalnız bu cevaplarda ürün retry kaydı bulunmadığını gösterir. Koşu raporları ayrıca tamamlanmamış koşular için vaka dışı UNVERIFIED kaydı içerebilir; yukarıdaki sayılar soru JSON dosyalarının sayısıdır.

## Doğal ürün toparlanması: r6 / CP043

Dosya: `composable-r6/CP043.json`.

- Ürün olayı: **2026-09-30 19:14:19.137407 UTC / 22:14:19.137407 İstanbul**.
- Kaynak `logo`, SQLSTATE `42000`, hata `1205`, `failedAttempt=1`, `retryAfterMs=360`.
- Retry ve tamamlanan yürütme aynı SQL SHA256 değerini taşır: `70e9ed366fb56e44a5b987acc37a9d285146911603b59c93566d2283bb1e06e2`.
- `semantic.executions`: `status=complete`, `attempts=2`, `rows=5275`, `dbMs=11735`.
- API türü `PARTIAL_ANSWER`; cevap `resultId` ve saklanan tam sonuç `id` aynı: `c2f87fef82a14c02922960f64883de9f`.
- Saklanan tam sonuç 224 satır, `totalRows=224`, `truncated=false`.
- Bu vakada `referenceRetries=[]`; gözlenen retry referans sorgusuna değil ürüne aittir.
- Sayısal kabul: `status=UNVERIFIED`, `referenceChanged=true`, `errors=["Numeric mismatch: net_sales"]`; önceki ve sonraki bağımsız referansların her biri 224 satırdır.
- Kaynak eksikliği: 4293 aktif kitapta Yazar katılımının aktif kişi kimliği çözülememiştir. Kısmi kişi grubu tam grup sayılmamış; satış boş yazar grubunda korunmuştur. Bu eksiklik deadlock toparlanmasından ayrı bir konudur.

Sürüm ve dosya bağları:

| Alan | Değer |
|---|---|
| engineCodeHash | `57e9dbbbdadc949e10b66309b5f320285505603635f903b889bb5c24450ff487` |
| contractHash | `c824cef07ff6a63e0e9ddac4da98c69642e9c9de24873931f9667e542938f0b5` |
| CP043 dosya SHA256 | `7afd9cbaea83e10e6c006ddcbb7f45f680a49a937d6e2d8d2c912c21f1fd7db4` |

r6 raporunda `codeStable=true`; sonuçlar 30 PASS, 7 FAIL, 8 UNVERIFIED'dır. Bunlar koşunun kendi statüleridir; tek teknik retry toparlanması bu başarısız veya doğrulanamayan vakaları başarıya dönüştürmez.

## Bağımsız referans retry olayları

Bu kayıtların `execution` değeri `independent_reference_not_product_api`dır. Her vakada sonraki referans sonucu bulunmaktadır. Ürün retry kanıtı olarak kullanılmazlar.

| Dosya | Zaman UTC | SPID | Aşama | İlk deneme sonrası bekleme | Ürün/vaka sonucu |
|---|---|---:|---|---:|---|
| composable-r4/CP019.json | 18:38:55.308059 | 86 | after_api | 1075 ms | DATA_SOURCE_UNAVAILABLE / FAIL |
| composable-r4/CP029.json | 18:39:47.872079 | 86 | before_api | 2443 ms | TEXT_TO_SQL / PASS |
| composable-r6/CP015.json | 19:10:18.240651 | 97 | after_api | 2233 ms | TEXT_TO_SQL / PASS |
| composable-r6/CP032.json | 19:12:05.790869 | 97 | after_api | 1524 ms | TEXT_TO_SQL / UNVERIFIED |

CP019/r4 ayrımı: ana incelemede ürün hatasının nedeni model servisindeki **HTTP 400 / system-message sırası** olarak belirlenmiştir. Bu dosyadaki API sonrası referans 1205 olayı ayrı yürütmedir; ürün hatası DB deadlock olarak sınıflandırılmamalıdır. Bu doküman model günlüğünü yeniden okumadı; neden bilgisi ana incelemenin tespitidir. CP019 ürün `readRetries` listesi boştur.

## Açık kalan

Bir doğal olayda teknik toparlanma gözlenmiştir; tekrarlanan olaylar için güvenilirlik oranı veya tüm cevapların doğruluğu kanıtlanmış değildir. CP043 sayısal doğruluğu ayrıca yeniden kabul gerektirir. Kilitleyen diğer işlem ve kaynak grafiği bu JSON'lardan belirlenemez; DBA'nın `system_health` deadlock XML kaydı gerekir. Mevcut hesabın bu kayıtları okuma yetkisi önceki incelemede yoktu; bu tur yetki sorgulanmadı.

Sonraki tamamlanan kabul koşularında ürün `semantic.readRetries` ile referans `referenceRetries` yine ayrı taranmalı; ürün olayı aynı SQL hashli tamamlanmış yürütme ve aynı `resultId` tam sonucuyla ilişkilendirilmelidir.

## Ek: 1 Ekim 2026 00:28:47 background refresh olayı

Ana incelemenin test sunucusu günlüğünde gördüğü kayıt `background refresh failed (fb2aff94…)`, SQLSTATE `42000`, SQL Server `1205`, Process ID `97` içerir. Saat günlükte görüldüğü biçimde aktarılmıştır; bu ek için uzak günlük veya zaman dilimi yeniden doğrulanmadı. Aşağıdaki kapsam tespiti yerel kaynak kodunun salt okunur incelemesidir; yeni DB/API koşusu değildir.

- Çağrı zinciri `backend/semantic_bridge/app.py:985` `_refresh_one` → `:704` `_execute` → `:712–715` `_execute_once` → connector `execute` şeklindedir. Finans motorunun `finance_query/executor.py:49–91` salt SELECT denetimi ve üç denemeyle sınırlı 1205 retry yolu çağrılmaz. `semantic_layer/profiler/connectors.py:121–135` hatayı yeniden fırlatır; bağlantı havuzu ve SingleFlight da retry yapmaz. Dolayısıyla bu olay finans motorunun retry başarısızlığı olarak sınıflandırılmaz; CP043'teki doğal ürün toparlanması kanıtını geçersiz kılmaz.
- Sıcak sorgu listesine ürün kodundaki giriş `app.py:652–669` `_run_sql` üzerinden olur: önce `validate_sql`, izinli tablolar ve veri kapsamı kontrol edilir, ardından fiziksel SQL oluşturulup `_touch_hot` çağrılır. `runtime/guardrails.py:136` denetimi SELECT/WITH başlangıcı, çoklu ifade ve yasak anahtar sözcük kontrolleridir. `_refresh_one` fiziksel SQL'i yeniden salt okuma kontrolünden geçirmez; önceki doğrulanmış girişe dayanır. Bu, finans motorundaki AST denetimiyle aynı koruma değildir.
- Hata yolunda `app.py:988–996` yalnız başarısızlık sayısı artar; beş başarısızlıktan sonra sıcak listeden çıkarılır. `_remember` yalnız başarıda çağrıldığı için önceki cache sonucu ve hesaplanma zamanı korunur. `:681` tazeleyici ayaktaysa eski sonucu yapılandırılmış stale sınırına kadar sunabilir. Bu, yenilemenin başarılı olduğu anlamına gelmez. Aynı sorguya katılan eşzamanlı istek SingleFlight üzerinden aynı hatayı alabilir.
- Ayrı düzeltme kaydı: bu doğrulanmış okuma yoluna sınırlı, yalnız 1205'e özgü retry ve kaynak/SQL hash/deneme/sonuç kanıtı eklenmesi değerlendirilmeli. Bekleme havuz kiralaması bırakıldıktan sonra yapılmalı; finans retry'siyle iç içe geçerek deneme sayısını artırmamalı. Streaming `batches` yolu kısmi çıktı riski nedeniyle ayrı ele alınmalı. Bu incelemede ürün kodu değiştirilmedi, commit veya deploy yapılmadı.

DBA deadlock grafiği bulunmadığından kilitleyen diğer işlem, kilit sırası ve asıl veritabanı çekişmesi bu olaydan belirlenemez. Kanıtlanan şey yeni bir 1205 kaydı ve retry kapsamı farkıdır; kök kilitlenme nedeni değildir.
