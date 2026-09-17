# Gerçek referans kitap: font çizimi eşleme deneyi

Bu dizin üretim ayrıştırıcısına bağlı değildir. Ana kitabın metnini veya kabul kararlarını değiştirmez. Kod, 44–48. sayfaların gömülü Caveat Brush çizimlerini, Google Fonts deposundaki hash ile sabitlenmiş fontun çizimleriyle karşılaştıran gerçek sunucu deneyinin bire bir kaydıdır. Genel müşteri kurulumu özelliği sayılmaz.

- `manifest.json`: resmî font, lisans ve metadata URL/revision/SHA-256. Kitap veya cevap içermez.
- `requirements.lock` / `tool-manifest.json`: fontTools 4.59.0 ve pypdf 6.0.0 wheel hashleri. Ayrı deney imajına kurulmuştur; ana uygulama bağımlılıkları değişmez.
- `Dockerfile`: mevcut belge imajının üstüne yalnız deney bağımlılıkları; imaj `nanobase-editor-font-probe:v1`. Deneme çalışırken ağ yok; kaynak volümü salt okunur; 2 CPU/2 GiB sınırı kullanıldı.
- `outline_probe.py`: kontrol noktaları, çizim işlemleri, unitsPerEm ve glyph genişliğinin tam SHA-256 eşliği; referans fontun cmap ve GSUB single/alternate ilişkileri. Benzerlik eşiği, kelime sözlüğü veya beklenen kitap cevabı yok. CID→GID Identity dışı fontta durur. Bu ilk ölçüm referans PDF ve beş sayfaya sınırlıdır; pypdf özel API kullanımı sabit sürüme bağlıdır.
- `compare_source.py`: özgün API kayıtlarını bağımsız PostgreSQL kayıtlarıyla karşılaştırır; yeni font adayıyla mevcut optik kapının sonucunu yalnız bellekte ölçer. Kaynak/DB yazımı yok.
- `font_inventory.py`: PDFium ile bozuk kod birimlerini font ve sayfa bazında sayar. PDFium'un UTF-16 surrogate birimleri harf adedi sayılmaz.

Sonuç: 47 özel Unicode glyph türünün 45'ine tek eşleme; gerçek 1.160 harf gösteriminin 1.156'sına karşılık, 4'üne karşılık bulunamadı. 2.320 önceki sayı UTF-16 kod birimidir. Beş sayfada 101 kaynak bölgesinin 68'inde font adayı PDF metnini kullanılabilir hale getirdi; mevcut OCR/yeniden okuma çelişkileri korunduğunda optik kapı iyileşmesi 0, yeni çelişki 0. Ana kaynak sayısı 828 anlaşma/321 inceleme olarak kaldı. Sentez/konuşmacı kabulü verilmedi.

Sunucu kanıtları `/data/nanobaseai/editor/evidence/font-gsub-character-probe-v2.json`, `font-recovery-source-comparison.json`, `native-font-audit.json`. Font varlıkları `/data/nanobaseai/editor/runtime/font-probe/` içindedir; deney için indirildi, ana offline pakete eklenmedi. Gömülü font ve özgün PDF değiştirilmedi. Bu sonuç üretim entegrasyonu, genel font desteği veya bütün kitabın anlaşılması değildir.
