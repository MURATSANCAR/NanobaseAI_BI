# Günlük dil soruları için birleşebilir hesap motoru

30 Eylül 2026 — Kullanıcının paralel inceleme talebi sonrası geliştirme planı. Bu belge uygulanmış yetenek veya canlı kabul iddiası değildir.

## Teşhis

Eski katalog fallback kaldırılması yanlış kaynağa sapmayı durdurur; yeni motorun hesap kapsamını büyütmez. Mevcut finance_query planı 11 ölçü, 8 kırılım ve tek ölçü ailesiyle sınırlıdır. Şema doğrulaması kolon varlığı kontrolüdür, genel alan/ilişki keşfi değildir. CRM tarafı üç güncel sayım; tek çapraz eşleşme kitap stok kodudur. Yazar künye metni kişi veya hak sahibi kimliği sayılamaz.

Statik incelemede yürütücüde bulunduğu halde planlayıcının reddedebildiği durumlar: CRM kaynak bağımlılığında filtrelerin göz ardı edilmesi; “ilk on” ifadesinde rakam aranması; takip sorusunda önceki doğrulanmış filtrenin yeniden söylenmesinin beklenmesi. Bunlar canlı yeniden üretim ve bağımsız referans olmadan düzeltilmiş kabul edilmez.

## Hedef

Model fiziksel SQL veya tahmini tablo ilişkisi üretmez. Kullanıcı isteğini doğrulanmış varlık, ölçü ve işlemlerden oluşan tipli plana çevirir. Bir ölçü/işlem eklendiğinde birçok ifade birleşimsel olarak desteklenir; soru kimliğine özel üretim kuralı eklenmez.

Plan sırası: kaynak okuma → filtre → kayıt düzeyine göre toplulaştırma → doğrulanmış kimlikle zenginleştirme → türetme/oran/dönem karşılaştırması → hesap sonucu filtresi → sıralama → limit. İşlemler gerektiğinde alt planlara ayrılır. Mali hareket tabloları doğrudan birbirine JOIN edilmez; aynı ortak düzeye toplandıktan sonra birleştirilir.

Her düğüm kullanıcı ifadesi dayanağı, kaynak bağımlılığı, kayıt düzeyi, anahtar, para/birim, NULL/sıfır davranışı, tanım sürümü ve sonuç kolonlarını taşır. Doğrulayıcı tüm kullanıcı koşullarının karşılandığını, ilişki tekilliğini, tutar korunumunu ve dönem uyumunu denetler.

## Geliştirme dilimleri

1. **Doğru durum ve mevcut yetenekler:** gerçek kullanıcı belirsizliği, desteklenmeyen özellik, doğrulanmamış iş tanımı, erişilemeyen kaynak ve geçersiz plan ayrı statülerdir. Kaynak bağımlılığı ölçü+kırılım+filtre üzerinden bulunur. Doğal sayı, göreli dönem ve takip bağlamı tipli girdiler olur. Eksik yetenek “soruyu netleştir” diye gizlenmez.
2. **Mevcut ölçülerden birleşik hesap:** aynı ölçü ailesinde fark, açık tanımlı oran, dönem değişimi, sonuç eşiği ve ilk N. Decimal ve tanımlı sıfır payda politikası kullanılır. Birbirinden bağımsız ölçü ailelerini birleştirmek ayrı plan düğümü gerektirir.
3. **CRM varlık okuma:** liste, kırılım, filtre, tarih semantiği. MetadataSchema ve StringMapBase üzerinden canlı etiket/ilişki/durum kanıtı; her uygun varlık için zorunlu aktif kayıt kapsamı. Kitap–kişi–eser katılımı–sözleşme ilişkileri gerçek kimliklerle doğrulanır.
4. **Logo operasyonları ve kaynaklararası plan:** stok, sipariş, alacak/tahsilat ve sözleşme süreçleri. İlişki başına 1:1/1:N/N:N, eşleşmeyen/çoğalan kayıt ve ölçü korunum kanıtı gerekir. Ad benzerliği kimlik kanıtı değildir.
5. **İş tanımı gerektiren hesaplar:** kâr, yaşlandırma, kur, hedef ve tahmin. Kaynak/maliyet/vade/kapama/payda tanımı doğrulanmadan varsayımla sonuç üretilmez.

## Dosya sorumlulukları

- `scripts/acceptance/finance_contracts/schema.py`: eski katalogdan bağımsız canlı fiziksel ve Dynamics metadata kanıtını genişletir.
- Yeni `finance_query/source_manifest.py`: tek şirket, yedek tarihi, işlem dönemi, esas kaynak ve örtüşme politikasını taşır. Teknik kodlar ayrı şirket değildir.
- Yeni `entities.py`, `relationships.py`: varlık kimliği, kayıt düzeyi, aktiflik ve kanıtlı ilişkiler.
- `contracts.py`: ölçü tanımı, birim, toplama davranışı, dönem anlamı ve kanıt referansı.
- Yeni `errors.py`, `plan.py`; `model_schema.py`, `planner.py`: tipli durum ve işlem planı, bütün istek koşullarının doğrulanması.
- `executor.py`: izinli salt SELECT, kaynak bazlı önce toplulaştırma, tutar koruyan birleştirme ve Decimal türetmeler.

## Kabul kapısı

Yalnız test sunucusundaki gerçek API ve bağlı Logo/CRM kullanılır. Aynı yürütmenin resultId tam sonucu bağımsız doğrudan kaynak hesabıyla satır, kolon, değer, NULL, tekillik ve kesilme açısından karşılaştırılır. Günlük dil varyantları, çok turlu sorular ve geliştirmede kullanılmamış sorular eklenir. Mevcut 100 karmaşık soru geniş regresyondur; destek dışı cevaplar tam doğru cevap sayılmaz.

Rapor kategorileri: doğru tam cevap / doğru netleştirme / destek dışı / yanlış cevap / doğrulanamadı. Her 10 soruda sayılar açıklanır. Kod, kaynak manifesti ve hesap tanımı hashleri kaydedilir. Kaynağa yazma ve yerel test yapılmaz.
