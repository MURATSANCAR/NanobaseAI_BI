# 17 Eylül — Restore izin düzeltmesi ve kaynak sorunu ölçümü

## Gerçek restore hatası ve kod çözümü

`book-access-v3-20260917` paketinin offline export/import ve yedek aşamaları geçti; ayrı kurulumda restore sonrası `/v1/system` 500 döndü. API günlüğü `permission denied for table users` gösterdi. `pg_dump/pg_restore` taşınabilir kurulum için ACL taşımıyor; `migrate.py` eski tablo izinlerini yeniden kurarken `0006_book_access` ile gelen dört tabloyu atlıyordu. Alembic revizyonu zaten güncel olduğundan migration tekrar çalışmıyordu.

`migrate.py` artık her kurulumda `users/access_keys` için SELECT/INSERT/UPDATE, `book_access` için ayrıca DELETE, `access_audit` için yalnız SELECT/INSERT verir. Veriler değiştirilmedi; uygulama rolüne sahiplik veya superuser verilmedi. `verify.py` gerçek PostgreSQL üzerinde dört tablonun yedi ayrı iznini denetler; audit güncelleme/silme ve gereksiz izinlerin kapalı olduğunu da doğrular.

Başarısız kurulum korunarak aynı gerçek yedek yeni `editor-restore-acl-v4` projesine geri yüklendi. 14 tablo ve bütün artifact parmak izleri yazıcılar açılmadan eşleşti. Gerçek API/PG, 48 sayfalık kaynaklar, OCR adayları, yayın kapıları, kapsamlı anahtarlar ve yönetici/okuyucu ekranları 320/390/768/1440 px geçti (`RESTORE_ACCESS_V4_PASS`). Hedef servisler durduruldu; kanıtlar/volümler korundu.

Sürüm `book-access-v4-20260917`; API imajı `sha256:1769765af50d58d75024fefb5f25cbabe512cd47b9e7a57d491c41f789547907`; 35 backend dosyası ağaç hash'i `867439dfcb028a29e871c9473f3b3c81c8e63e07c4170f2cca056c918a52a432`. Web v1 ve belge/parser upload-v2 imajları değişmedi. Bu sürümün kendi yeniden paketleme kabulü ayrıca tamamlanmalıdır; önceki başarısız v3 paketine PASS yazılmaz.

Kanıt kökü `/data/nanobaseai/editor-qualifications/book-access-v3-20260917/b652f63c/`: `restore.log` (başarısız v3), `restore-acl-v4.log` (düzeltme kabulü), `installation-acl-v4/evidence/acl-*.log`. Ana yayın takibi `/data/nanobaseai/editor/evidence/access-v4-publish.log`.

## 321 açık kaynak bölgesi

`triage-source-quality.py` yalnız okur; gerçek API'nin bütün span/sayfa/iddia kayıtlarını bağımsız PostgreSQL JSON kayıtlarıyla bire bir karşılaştırır. Kaynak metni, review veya kabul kararı yazmaz.

09:30 UTC ölçümü: 48 sayfa, 1.149 span, 828 anlaşma, 321 inceleme. Açık bölgelerde nedenler örtüşür:

| Neden | Bölge |
|---|---:|
| İkinci okuyucu eksik veya farklı | 281 |
| PDF metni kullanılamıyor veya farklı | 222 |
| Yeniden okuma kararsız | 187 |
| Tam sayfa ve bölgesel Paddle okuması farklı | 166 |
| Düşük tanıma puanı | 134 |
| Kararlı yeniden okuma mevcut metinle çelişiyor | 92 |

18 açık bölge sayfa numarası adayıdır; bunlar otomatik silinmedi veya kabul edilmedi. En fazla açık bölge s.22 ve s.24'te 16'şar, s.43'te 15, s.14 ve s.30'da 13'er. İddialardan 77'si metin eşleme kapısını geçse de senteze uygun iddia sayısı 0; konuşmacı/anlamsal kabul açık. Kanıt `evidence/source-quality-triage-20260917T093019960939Z.json`.

## Kelime geometrisi kırpım denemesi

Sayfa kutusunun kenarındaki komşu harfin kırpıma girmesi olasılığına karşı, bağımsız Tesseract kelime kutularından görüntü kırpımı ölçüldü. OCR modeline beklenen metin verilmez; yalnız görüntü verilir. Aynı kurulu Paddle ağırlıkları, ağsız ayrı konteyner, 4 CPU/4 GiB ve salt okunur kaynak volümü kullanılır. Kod `ocr/experiments/word_geometry_probe.py`, yürütücü `scripts/probe-word-crops.py`; süre sınırında yalnız kendi konteynerini temizler. Her ölçüm ayrı UUID kanıt dizinine yazılır.

İlk üç sayfalık gerçek ölçümde s.29'da beş ölçülebilir bölgede değişim yok; s.30'da 34 bölgede beş iyileşme ve bir gerileme; s.38'de 23 bölgede iyileşme yok, bir gerileme var. Karşılaştırma mevcut optik kapıyı, PDF/Tesseract ve önceki çelişkileri korur. Bu, metnin doğru olduğunun bağımsız insan kabulü değildir. Ana OCR kodu ve kitap kayıtları değiştirilmedi; yöntem genel varsayılan yapılmadı. Kanıt `evidence/word-crops-9351940d-c9fc-46c3-bd47-f7ddd291b7c2/report.json`.

Tüm kitap ölçümünün ilk denemesi API dağıtım sırasında yeniden başladığı için başlayamadı; başarısız günlük `word-crops-full.log` korundu. API açıldıktan sonra tek ölçüm yeniden başlatıldı (`word-crops-full-retry.log`). Sonuç tamamlanmadan kalite artışı veya 321 bölgenin çözüldüğü söylenmez. Kitap içeriğine manuel müdahale 0; yerel test çalıştırılmadı.

## Tüm kitap kırpım karşılaştırmasının sonucu

48 sayfa tamamlandı; 1.149 bölgenin 799'unda bağımsız okuyucunun kelime geometrisi bulundu ve ölçüm yapılabildi. 350 bölge için kutu yoktu; bunlar sessizce başarılı sayılmadı. Alternatif yöntem 19 bölgenin optik kapısını iyileştirirken önceki 47 anlaşmayı bozdu; OCR süresi 113,58 saniye. Dolayısıyla yöntem genel varsayılan için reddedildi. Başarısız aday ana OCR koduna bağlanmadı; kaynak sayıları **828/321 olarak kaldı**. Kanıt `evidence/word-crops-45d719f5-3a31-4fdd-b54d-d990f99c4f9e/report.json`. Üç sayfalık pilotun toplam sonuç yerine kullanılmaması bu geniş kontrolde gerçek gerilemeyi yakaladı.

Ana v4 yayınında `MAIN_ACCESS_V4_PASS`: kod/web hashleri, gerçek API/PG, kaynaklar, yayın kapıları, kapsamlı erişim ve yönetici/okuyucu dört genişlik kontrolleri geçti. Yeni v4 offline paket/restore koşusu `evidence/access-v4-installation-qualification.log` üzerinden ayrıca izleniyor.
