# Otomatik bölge yeniden okuma

## Uygulama

`backend/editor/region_reread.py` yalnız sorunlu kaynak kutularını özgün 2400 px render'dan kırpar. Komşu yazıyı kırpmaya eklemek yerine beyaz kenarlık ekler; yazı yüksekliğine göre en fazla üç kat büyütür. Tesseract `tur+eng`, PSM 7 ve 13 okumalarını ayrı metin/güven değerleriyle saklar. Model, TSV, kod, kaynak render ve kırpım SHA-256 kimlikleri korunur. Bir okuma en fazla 30 saniye, bir sayfa en fazla 256 bölgedir. Ağsız belge konteyneri kullanılır; yeni model servisi eklenmez.

`scripts/reread-source-regions.py` bağlı gerçek API'den kayıtları alır ve bağımsız PostgreSQL sonucuyla karşılaştırır. Aktif analiz varken çalışmaz, dosya kilidi aynı yeniden okuma işinin çoğaltılmasını engeller. Sayfa argümanları sınırlı pilot içindir; argümansız çağrı tüm inceleme bölgelerini işler. Her on tamamlanan sayfada ilerleme bildirir. Önce/sonra PostgreSQL kayıt parmak izi karşılaştırılır.

Makine çıktıları kaynak artifact alanında `region-reread-v1/<generation>/page-NNNN.json` altında atomik ve değişmez kaydedilir. Aynı istek/kod yeniden çalıştırılırsa tamamlanmış sayfa kullanılır; farklı istek/kod eski dosyanın üzerine yazamaz. Mevcut source_span, review ve iddia kayıtları değiştirilmez. Beklenen kitap cevabı OCR motoruna verilmez.

Operatör API'si `GET /v1/generations/{generation}/region-rereads` ile kayıtları sunar; `pdf_page` filtresi vardır. Kimlik doğrulama ve mevcut kitap/nesil erişim kontrolü korunur. `verify-region-rereads.py` gerçek API çıktısını artifact, özgün render hash'i ve bağımsız PostgreSQL bölge kimliği/kutusuyla doğrular; bütün inceleme bölgelerinin kapsanmasını arar.

## Kabul sınırı

İki Tesseract ayarı iki bağımsız motor değildir. Yeni metin her iki ayarda aynıysa ve mevcut bir okuyucuyla eşleşiyorsa yalnız `REREAD_SUPPORTED_CANDIDATE` olur. Uyuşmazlık çözülmüş veya kaynak doğrulanmış sayılmaz; her kayıt `eligible_for_synthesis=false` kalır. Kelime sınırını koruyan Türkçe token normalleştirmesi kullanılır. Ham okumalar değiştirilmez.

Konuşmacı kimliğinin doğrulanması ve adayların yeni analiz nesline hangi kanıt politikasıyla alınacağı ayrıca tamamlanmalıdır. Eski nesil 371 inceleme bölgesini korur. Önceki v2 paket/restore kanıtı bu yeni sürümün kabulü değildir.

## Gerçek koşu

Ortam `nanobase-direct`, `/data/nanobaseai/editor`; gerçek API `http://127.0.0.1:8810`, bağlı Editor PostgreSQL ve özgün PDF. Nesil `a9471749-7447-4826-b003-f25e53943763`.

| Pilot sayfa | Sorunlu bölge | İki ayarda aynı | Mevcut okuyucuyla desteklenen aday |
|---|---:|---:|---:|
| 16 | 10 | 3 | 3 |
| 29 | 11 | 2 | 0 |
| 38 | 4 | 2 | 2 |
| Toplam | 25 | 7 | 5 |

Pilot API'den erişildi; bağımsız PostgreSQL kaynak eşliği ve önce/sonra değişmezlik kontrolü geçti. Beş aday, beş çözülen hata anlamına gelmez. S.29 için bu yöntem desteklenen yeni aday üretmedi; gerçek olumsuz sonuç gizlenmedi.

Yayın `region-reread-v1-20260917`; API/worker imajı `sha256:3ec5c8082a38d568288b13158a1696491740d439852d84f5791b25cc1085e981`, belge imajı `sha256:2d166c713e64d9a967865ddd17c5e5e0bc681ae75017dd023f6ae41e29ed7f23`. Çalışan 28 backend dosyası eşleşti; ağaç SHA-256 `653847e42400a7ef03aab049252b06c50df7bced50dc8bb422fd494fbc8101b8`. Yeni API üzerinde yetki/soru/yayın kapıları 401/409 ile kapalı kaldı, DB'de soru/review yazılmadı.

Kanıtlar `evidence/region-reread-<generation>-16-29-38.json`, tam koşu günlüğü `evidence/region-reread-all.log`; son kapsam/kanıt kontrolü `evidence/region-reread-verification.json` içine yazılır. Model okumaları özel artifact alanındadır, Git'e kitap metni eklenmez.

## Tam yeniden okuma sonucu

46 sayfadaki 371 inceleme bölgesinin tamamı işlendi; 15 ve 42. sayfada inceleme bölgesi olmadığı için yeniden OCR çağrılmadı. 175 bölgede iki ayar aynı metni üretti; bunların 147’si mevcut okuyuculardan en az biriyle eşleşti, 28’i hiçbir kullanılabilir eski okuyucuyla eşleşmedi. 196 bölgede iki yeniden okuma arasında kararlı eşleşme yok. Bu sayılar anlamsal doğruluk veya çözülen hata sayısı değildir. Özgün PostgreSQL kayıtlarının önce/sonra parmak izi eşit kaldı.

İnceleme API’si yeni ölçümleri bölgeye bağlar: yeniden okunan kutularda `next_action=RECONCILE_READER_EVIDENCE` ve kırpım hash’i görünür. `REGION_READING_REQUIRED` durumunda bırakılarak aynı işlemin gereksiz tekrarı istenmez. Mevcut 371 NEEDS_REVIEW kararı korunur; soru/yayın kapıları kapalıdır.

46 artifact dosyasının kod SHA-256 değeri çalışan API’deki okuyucu modülüyle eşleşti: `17f6ca402c8458ec2020a1faeab8d304b82582eb34d0f378927ff1e82da27557`. Bu kod kökeni kontrolüdür; tanınan metnin doğruluğu sonucu değildir.

Son kontrol tamamlandı: 46 sayfa/371 bölgenin gerçek API–artifact–PostgreSQL eşliği, kaynak render hash’i, sayfa filtresi, yeni API’de 401 yetki reddi ve inceleme API’sine bağlantısı geçti. Son yayın/soru kontrolü 17 Eylül 05:42:36 UTC’de 401/409 ile geçti; review ve soru işi sayıları önce/sonra 0, nesil NEEDS_REVIEW. Yerel ürün testi çalıştırılmadı.
