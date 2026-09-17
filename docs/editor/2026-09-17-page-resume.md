# Tamamlanmış sayfadan devam ve öncelikli sayfa — v7

## Genel kod

`page_reuse.resolve_page_parent` aynı içerik sürümünün nesil zincirinde bir sayfanın en yakın tamamlanmış kaynak/layout/görsel/aday/kontrol kayıtlarını bulur. Eksik sayfa önceki atadan alınır; başka içerik sürümü, döngü, eksik ata ve 64 derinlik aşımı hata verir. Her sayfanın gerçek kaynak atası kayıt kökeninde korunur. Önceki kabul kararları kopyalanmaz; yeni kaynak kapısı/alıntı kontrolü yeniden çalışır. Metin veya güven yükselmesi değiştiyse model adayları yine taze üretilir.

Model girdisi `[span_id,metin,kullanılabilir,bbox]` satırlarına sıkıştırılır; yalnız model girdisinde bbox üç ondalığa yuvarlanır. Kaydedilen kaynak geometrisi ve metin aynen kalır. Anlatı dışı sayfalar için boş claims istenir; künye ve yönergeleri kişi/olay üretimine harcamak engellenir. Bu prompt talimatı tek başına anlamsal kabul değildir.

Analiz API'sinin `priority_pages` parametresi en fazla 20 benzersiz, gerçek PDF içinde kalan sayfayı öne alır. Kalan bütün sayfalar normal sırayla işlenir; sayfa atlamak veya kitabın kalanını tamamlandı saymak değildir. Kitaba özel sayfa numarası üretim kodunda yoktur.

## Gerçek ölçümler

Aynı özgün kitabın gerçek API/PG kaydıyla sayfa 2 mevcut tamamlanmış R2 neslinden, sayfa 7 onun tamamlanmış atasından seçildi. İlgili beş kayıt türü her atada API ve bağımsız PG ile eşit. Kanıt kabul ortamı `evidence/page-reuse-candidate-20260917T135539Z.json`. Negatif döngü/eksik ata koşulları gerçek veride yaratılmadı; bu dallar canlı kabul sayılmaz.

Gerçek tokenizer ölçümünde sayfa 2 girdisi 3.952 → 1.873 token (%52,61 azalma, satır şeması açıklaması dahil); kaynak metni/ID/sıra/kullanılabilirlik eşit. Bu ölçüm model süresi/kalitesi kabulü değildir. `evidence/token-packaging-page2-audit.json`. Önceki R2 sayfa 2 gerçek model çağrısı 448,115 saniye/607 çıktı token sürdü; geçici retry metriği boştu, dolayısıyla retry dalı o çağrıda sınanmış sayılmaz.

## Aktarım

V6 R2'nin beşinci sayfa kontrolü tamamlandıktan sonra API iptali istendi; worker/model durduruldu, parser'a dokunulmadı. Beşinci sayfanın mevcut sonucu ve önceki nesil korunur. `evidence/regional-source-r2-checkpoint-cancel.json`. Ayrı ortam `page-resume-v7-20260917` görüntüsüne geçiriliyor. Yeni koşu sorunlu kaynak sayfasına öncelik verecek; ardından kalan sayfaları işleyecek. Ana uygulama doğrulanmış v5 sürümünde kalır.

## Kabul sınırı

V7 henüz uçtan uca kabul edilmedi. Beklenen kontrol: yeni kayıtların doğru atadan ham kaynak eşliği, kaynağı değişen sayfada taze model çağrısı, öncelik sırası ve 48 sayfanın eksiksiz kapsanması, kaynak/atıf mobil ekranı ve model kapalıyken başlayan gerçek isteğin sınırlı tekrarlarla toparlanması. Kitap metni, konuşmacı veya inceleme kararı elle düzeltilmez.

## Canlı V7 doğrulaması — 17 Eylül

Ayrı API18810 ortamında nesil `ab85c397-25f9-4cd9-8291-fc6ffed8e61b`, iş `0941d6e2-b7f5-4465-ab81-7f5c760dbab7`, sürüm `page-resume-v7-20260917` çalışıyor. Öncelik girdisi `[29,13]`; üretim kodunda kitap/sayfa sabiti yok. 14:11 UTC gözleminde sekiz sayfanın kontrolleri tamamlandı, dokuzuncu sayfanın görsel aşaması kaydedildi. Bu anlık gözlem tam koşu kabulü değildir.

Gerçek model servisi kapalıyken başlayan 29. sayfa isteği üç CONNECT_ERROR ve iki HTTP503 sonrasında sınırlı tekrarlarla tamamlandı. Gecikmeler 1/2/4/8/16 saniye; gerçek çağrı 145,529 saniye, 966 girdi/171 çıktı token, finish_reason=stop. Kanıt `evidence/page-resume-cold-start.json` ve neslin page_claims metriğidir. Önceki R2 boş retry listesi bu dalın kanıtı olarak kullanılmaz.

29. sayfada bir bölgesel metin bağımsız okuyucularla yükseldi; 3 anlaşma/11 inceleme var. Taze model sonucu UNKNOWN ve sıfır claim üretti: kimlik veya kitap analizi başarıyla çözüldü anlamına gelmez. Kaynak arayüzü 320/390/768/1440 genişliklerinde geçti: `evidence/page-resume-ui-verification.json`.

Kimlik zinciri denetimi (`evidence/identity-anchor-source-audit-20260917T140757Z.json`) 13. sayfada doğrulanmış kendini tanıtma biçimli metin bulunduğunu, ancak kayıtlı balon/figür olmadığını gösterdi. Devamındaki iki kaynak satırı inceleme gerektiriyor. 29. sayfanın balon-kuyruk-figür ilişkisi tekil olsa da doğrulanmış isim çapası yok. Bu iki eksik kanıt birleştirilerek isim atanmaz; genel görsel kapsam kök nedeni ayrıca düzeltilmektedir.

Gerçek API parametre kabulü `evidence/priority-pages-api.json`: gerçek PDF sınırının dışı ve aynı sayfanın tekrarı 422 INVALID_PRIORITY_PAGES döndürdü. Her isteğin bağımsız PostgreSQL öncesi/sonrası jobs=15, generations=15; yanlış istek yeni iş üretmedi. Bölgesel kaynak denetiminin 14:13:57 UTC dokuz sayfalık sınırında API/PG eşliği geçti: 100 anlaşma/53 inceleme, en yakın sayfa ataları doğru, beş yeni yükselme ve sıfır gerileme (R2'de zaten yükselen üç bölge ayrı). 13 ve 29'un değişen kaynaklarında taze model çağrısı doğrulandı. Tam nesil kabulü hâlâ açık.
