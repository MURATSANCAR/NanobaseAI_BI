# Figür–karakter kimliği: gerçek kaynak sınırı

R4 nesli `08ca6877-6e30-4bb3-b1fa-767f048248e4` için CPU sunucusunda gerçek API (`127.0.0.1:8810`) kayıtları bağımsız PostgreSQL kayıtlarıyla karşılaştırıldı. `figure_identity`, `layout_regions`, `visual_observations`, `character_evidence` türlerinde API/PG eşitliği sağlandı. Model çağrısı, kaynak/review değişikliği ve yerel test yapılmadı.

## Ölçülen durum

- 48 kimlik sayfası, 33 ölçülmüş figür adayı, 0 kaynakla doğrulanmış yerel figür kimliği.
- 14 sayfada figür adayı var ancak ölçülmüş balon bağlantısı yok.
- Açık metinsel konuşmacı atfı bulunan 8 sayfada kaynağa bağlı figür çapası yok.
- Bir sayfada tek kuyruk–figür bağı var, aynı sayfada o balondaki sözü adla eşleyen açık metin yok.
- Bir sayfada balon/kuyruk geometrisi tekil değil; OCR da yeterli değil.

Bu kategoriler örtüşebilir. Figür aday sayısı kitapta bulunan gerçek karakter sayısı değildir; görsel kapsam doğrulanmamıştır. Sıfır kimlik tek başına kod hatası veya tam inceleme sonucu değildir.

## Otomatik çözüm sınırı ve somut kayıtlar

29. sayfadaki üç satırlı balonun yalnız ilk sözcüğü başka sayfadaki anlatıcı atfıyla eşleşiyor. Kaynak span `479eaae4-4a5b-5c0c-96f5-dd828e899276`, anlatıcı fragmanı `78f98ac9-b02f-5bcb-98f7-ee2cf6c78e37`, fragmanın ham ebeveyni `cb477810-4eec-568c-82d3-57e824680d6e`. Mevcut sistem bunu `EXACT_QUOTED_PREFIX_ONLY_NOT_WHOLE_BALLOON` kapsamında tutuyor. Bu bağlantı bütün balona veya global karakter adına genişletilemez.

Balonsuz aynı sayfa eşlemesi de mevcut kayıtlarda ad yetkisi sağlamıyor. 26. sayfanın atıf kaydı `bb877919-3f11-5006-b2fe-aa3ec81fa288` bir kişinin başka bir karakteri sormasını içeriyor. Görsel kaydı `c730f86d-df54-5c89-af5a-dedd1b8cf925` tek robot adayı içeriyor. Aynı sayfada tek ad/tek figür bulunması, soran kişinin resimdeki kişi olduğunu kanıtlamaz.

36. sayfanın görsel kaydı `aec9db98-d2a7-5c75-8c06-19b865f59786` robot benzeri bir figür önerirken kendi belirsizlik alanında bunun başlık kutusu/grafik öğesi olabileceğini söylüyor. Atıf kaydı `21dbd170-27f6-5ea7-9e2d-11a2ab00dfd0` bu görsel nesneyi adlandırmıyor. Görsel betimlemesini kimlik kanıtına yükseltmek güvenli değildir.

## Tanı deneyi ve karar

Genel, salt okunur `identity_coverage` adayı gerçek 48 sayfada sunucunun API konteyneri içinde çalıştırıldı. Kanıt: `/data/nanobaseai/editor/evidence/figure-identity-coverage-r4-candidate.json`; çalıştırıcı: `runtime/figure-identity-coverage-probe.py`; aday kaynak: `runtime/figure-identity-coverage-candidate.py`. Kanıtta aday kod hash'i, API/PG eşitliği, sıfır model çağrısı ve sıfır veri yazımı bulunur.

Bu deney yalnız eksik kanıt nedenlerini saydı; kimlik çözmedi. Sırf tanı alanı eklemek için çalışan backend ve nesil değiştirilmedi; üretim dosyasındaki deneysel ek kaldırıldı. Aktif R5 koşusuna ve modellere dokunulmadı.

Mevcut veriyle güvenle otomatikleştirilebilen şey sınırlı alıntı bağlantısı ve eksik kanıtın açık raporudur. Tam figür kimliği için isimle figürü doğrudan bağlayan yeni kaynak sinyali (örneğin doğrulanmış ad etiketi, eksiksiz açık konuşmacı alıntısı ve tekil kuyruk, ya da yayınevinin kaynak karakter tanımı) gerekir. Yakınlık, tek aday veya görsel benzerlik bu eksikliği kapatmaz. Ek kaynak yoksa `UNKNOWN` korunur; kullanıcı yerine editoryal karar verilmez.
