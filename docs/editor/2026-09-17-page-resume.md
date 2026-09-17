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
