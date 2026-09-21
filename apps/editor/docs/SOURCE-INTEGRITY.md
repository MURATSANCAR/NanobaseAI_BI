# Kaynak bütünlüğü — ilk düzeltme

21 Eylül 2026. Bu adım yeni analiz başlatmaz; bakım kilidi açık kalır.

## Sözleşme

- Fiziksel PDF manifestindeki bütün sayfalar iş planına girer. Bölüm başlığı bulmak,
  sayfanın hikâye olup olmadığına karar vermez. Başlıksız başlangıç özetten düşmez.
- `source.py` içindeki `source-reading-v1` ortak okuma izdüşümüdür. PDF metin katmanı
  aynen korunur; yoksa OCR kullanılır. Kaynaklar değişmez. Her metin aralığı özgün
  kaynağa, karakter ofsetine, SHA-256 ve generation kimliğine bağlıdır.
- PDF ile örtüşen OCR ikinci kez metne eklenmez; kaynak alternatifi olarak saklanır.
  Çelişkiler inceleme gerektirir. Ek OCR metninin geometrisi yoksa okuma sırası
  belirsiz diye işaretlenir. Metin birleştirme, anlamsal doğruluk kabulü değildir.
- OCR başlığı ancak PDF metninin başında harfiyen varsa paragraftan ayrılır; kelime
  değiştirilmez. Bölüm adayları hâlâ sezgiseldir; kaynak kapsamını etkilemez.
- Eski layout/extract sayfa rolleri öneridir. Yalnız `source=editor` rolleri bilgi
  çıkarımında dışlama için kullanılabilir. Fiziksel sayfa yine kaynak planında kalır.
- Numara verilmiş metin, sayfa paketi, alıntı doğrulama, karakter adı ipuçları ve
  arama pasajlarının metni aynı okuyucuyu kullanır. Mevcut Qdrant yeniden kurulmadı.
- Yeni TEXT kanıtı belirtilen paragrafta birebir (Unicode/boşluk/tire normalizasyonu
  dışında) aranır. Yakın alıntı sessizce düzeltilmez. `013_source_references.sql`
  ile yeni kanıtın kaynağı saklanır. Eski `source_refs IS NULL` kanıtlar tarihsel
  paragraph tablosuna aittir; yeni paragraf sırasıyla yeniden yorumlanmaz.
- API her zaman `semantic_acceptance=false` döndürür. Eksik OCR, metin çatışması,
  sırası belirsiz OCR eki ve belirlenmemiş sayfa türü görünür kalır.

## Sunucu kontrolü

`editor-control` altında kimlik doğrulamalı salt okunur `/v1/generations/{id}/source/`:
`coverage`, `plan`, `pages/{page}`, `passages`, `quote-check`.
`passages` yalnız planlanan metinleri gösterir; Qdrant'a yazmaz.

`deploy/verify_source.py` yalnız tt-gpu üzerindeki gerçek uygulama ve gerçek Editor
PostgreSQL ile çalıştırılır. Bağımsız sorgu: özgün page_text karakterlerinin kayıpsız
ve tek temsil edilmesi, tam fiziksel kapsam, kaynak hash/ofsetleri, API pasajları.
Anne Terliği 20/49, Levent 6/10, Vombat 5/6 için özgün PDF dosyası ve gerçek alıntı
kontrol edilir; aynı alıntı başka gerçek paragrafa bağlanınca reddedilmelidir.
11 kaynak/analiz tablosu önce/sonra karşılaştırılır; model çağrısı üretilmez.

Kabul sonucu yayın sonrası kanıt dosyasında kaydedilir. Yazma akışı, OCR anlamsal
uzlaştırma, tam kitap kabulü ve Qdrant araması bu salt okunur doğrulamayla kabul edilmez.
Sonraki adım: doğrulama/kimlik çözümü bittikten sonra türetilmiş çıktı üretimi;
düzeltmede eski çıktının geçersizleşmesi ve güvenli yeniden üretim tüketicisi.

## Yayın ve canlı kabul sonucu

- Sunucu: `tt-gpu`, release `/data/editor/releases/066a3cfb`,
  sürüm `0.11.0-source-066a3cfb`, image
  `sha256:a9e9fa2e4f3f517bdfa55920cae71d8a2ee8285c9a78350c8cb7e5eb90ae5559`.
- 6 gerçek kitap, 544/544 sayfa: fiziksel kapsam, özgün source karakterlerinin
  tek ve kayıpsız temsili, tam API pasaj değerleri, hash/ofset bağları **GEÇTİ**.
- Anne Terliği 20/49, Levent 6/10, Vombat 5/6 özgün PDF karşılaştırması ve alıntı
  kontrolü 6/6 geçti. Her altısında yanlış gerçek paragraf referansı reddedildi.
  Vombat 5'te MERAKLI VOMBAT başlığı ayrı span ve bölüm adayı olarak görüldü.
- Ortak claim/event/emotion okuma regresyonu yeni yayında 18/18 geçti; yetkisiz
  istek 401, yanlış UUID 422, olmayan nesil 404; eski nesiller kabul edilmedi.
- 11 tablo doğrulama öncesi/sonrası aynı. Yayın öncesi/sonrası claim, event,
  emotion, report, generation tam içerik hashleri aynı. 10.071 eski kanıtın
  `source_refs` alanı NULL kaldı; eski kanıtlar yeniden numaralandırılmadı.
- 162 sayfada metin/OCR/kapsam uyarısı, 544 sayfada editörce doğrulanmamış sayfa
  türü bulunuyor. Kaynak kayıpsızlığı, bu sorunların anlamsal çözümü değildir.
- Editor üreticileri kapalı, GPU 1: 0 MiB, bakım kilidi açık. BI modeli çalışıyor.
- Yedek `/data/editor/backups/20260921-source/`. Geri dönüş: önceki release/image
  dosyaları bu dizinde; eklenen NULL kolon eski image ile uyumludur. Veri geri
  yükleme veya analiz başlatma gerekmeden kontrol image'ı geri alınabilir.

Kanıtlar: [kaynak kabulü](evidence/2026-09-21-source-verification.json),
[ortak okuma regresyonu](evidence/2026-09-21-source-foundation-regression.json).
Yerel test çalıştırılmadı. Yeni kanıtın kalıcı yazma akışı ve model üretimi kapalı
olduğu için **DOĞRULANAMADI**; yeni workflow kabulünde gerçek kitapla denenmeli.
