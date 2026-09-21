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
