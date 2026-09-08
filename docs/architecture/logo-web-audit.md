# Logo web sözlüğü karşılaştırması — 2026-09-09

Kaynak: [Uğur Özpınar — Tablo Açıklamaları Yeni](https://ugurozpinar.github.io/Logo/Tablo%20A%C3%A7%C4%B1klamalar%C4%B1%20Yeni/).
Bu üçüncü taraf referans mevcut LDDS.xls ve Türkçe yapı dokümanının tamamlayıcısıdır.

| Kapsam | Sonuç |
|---|---:|
| Ana listedeki kayıt | 252 |
| Benzersiz detay sayfası (tamamı indirildi) | 251 |
| Detay sayfalarındaki kolon satırı | 6.477 |
| Eklenen kolon | 13 |
| Eklenen Türkçe kolon açıklaması | 3.908 |
| Eklenen kod etiketi (Türkçe + İngilizce) | 369 |
| Toplam tablo | 330 → 330 |
| Toplam kolon | 9.303 → 9.316 |
| Türkçe açıklamalı kolon | 2.830 → 6.738 |

Eklenen kolonlar: ITEMS.BUFFER; INVEXIMINFO.COUNTRYREF, FREEZONEREF, PAYTYPEREF,
BRBANKREF, CUSTOMREF, SHPTYPREF, SHPAGNREF, REGTYPREF, BANKREFNR;
INVEXIMLINES.CUSTOMREF, COUNTRYREF, ORIGINCNTRREF.

Kullanıcı onayıyla web kaynağı öncelikli hale getirildi (`--prefer-web`). İlk taramadaki
eksiklerin tamamlanmasına ek olarak **2.329 güncelleme** uygulandı:

| Güncellenen bilgi | Adet |
|---|---:|
| Türkçe açıklama | 2.096 |
| İngilizce açıklama | 65 |
| Kod etiketi | 109 |
| Kolon tipi | 4 |
| Kolon uzunluğu | 26 |
| İndeks tanımı | 28 |
| İlişki | 1 |

Örneğin PAYLINES.RNDVALUE ve REPAYPLANSLN.RNDVALUE webdeki Longint/4 tanımına,
WORKFLOWCARD.WORKPLACE ve WFTASK.WORKPLACETYPE Integer/2 tanımına geçirildi.
PROCUREMENT.LOGICALREF → ORFLINE.LOGICALREF ilişkisi sayfadaki tanıma göre eklendi.
Bu tanımlar webde belgelenen sürüme aittir; müşteri veritabanında doğrulanmış DDL değildir.
Aynı adlı indeksler güncellendi; sayfada listelenmeyen mevcut indeksler korunmuştur.

Tam kayıtlar, sayfa URL'leri, kaynak içerik SHA-256 değerleri ve değişikliklerin eski/yeni
karşılıkları [logo-web-audit.json](logo-web-audit.json) içindedir. JSON raporu son çalıştırmayı
(web önceliği uygulamasını), yukarıdaki ilk tablo önceki eksik tamamlama çalışmasını özetler.

Kaynak sınırlamaları:

- LG_SLSCLREL ana listede iki kez yer alır; tek detay sayfası vardır.
- LDDS-Res adlı sayfa, ana listedeki L_WFTASK kimliğine eşlenmiştir.
- LG_ITEMSUBS sayfasında kolon bölümü yoktur; mevcut dokümandaki bilgiler korunur.
- Taranan kolonlardan 138'inde birleştirme sonrasında da Türkçe açıklama yoktur.
  Kaynağın açıklamadığı alanlara anlam uydurulmadı. Tam liste JSON raporundadır.
- Web kapsamı mevcut 330 tablonun tamamını içermez. Mevcut diğer tablolar korunmuştur.
- Canlı veritabanı sorgulanmadı, mevcut müşteri katalogları yeniden indekslenmedi.
  Değişiklik ortak sözlük ve üretilen referans belgesindedir.

Üretim: `backend/scripts/import_logo_web.py`; LDDS/DOC içe aktarımından sonra çalıştırılır.
Doğrulama: içe aktarıcı ve şema indeksleyici testlerinin 16'sı geçti. 251 sayfanın tekrar uygulanması sıfır ekleme/güncelleme üretti.
Semantic layer test paketi ortamda `sqlalchemy` bulunmadığı için başlayamadı.
