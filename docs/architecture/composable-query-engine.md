# Birleşebilir Logo–CRM soru motoru

30 Eylül 2026 — Aşağıdaki genişleme uygulanıyor; canlı kabul sonuçları ayrıca sürüm ve kanıtla raporlanır. Tablonun metadata içinde bulunması, bütün iş anlamlarının desteklendiği anlamına gelmez.

## Kaynak ve plan sınırı

Eski semantik katalog fiziksel olarak yedeklenip kaldırıldı. Model eski SQL örneklerini kullanmaz ve fiziksel SQL yazmaz. İsteği kapalı ölçü, varlık ve işlem sözleşmelerine çevirir. Her kaynak SELECT'i gerçek kolonlar ve kullanıcı veri yetkisiyle doğrulanır. CRM aktiflik süzgeci bağlantıda uygulanır; işin yayımlı aktif durumları ayrıca metadata ile çözülür.

Tek şirket vardır. Logo teknik kodları ayrı şirket değildir. `L_CAPIPERIOD` ve doğrulanmış kaynak kapsamı istenen zaman aralığını boşluksuz ve örtüşmesiz karşılamalıdır; aksi durumda toplam engellenir. Stok bakiyesi farklı yıl yedekleri toplanarak bulunmaz.

## Uygulanan hesap kapsamı

- Temel satış, iade, adet, fatura ve tahsilat ölçüleri; müşteri/kitap/kanal/tarih ve güncel CRM künye kırılımları.
- Oran, fark, dönem değişimi, hesap sonucu filtresi, ilk N; toplam içindeki pay/kümülatif pay, ilk N ve kalan grubunun toplamı.
- Satış satırı, fatura başlığı, ödeme hareketi ayrı toplulaştırılır; ortak müşteri/kanal/tarih düzeyinde birleştirilir. Fatura tutarı kitap satırlarına çoğaltılmaz.
- Logo stok/stok tarihi, açık alış-satış siparişi, dönem cari hareket bakiyesi, ödeme türü, işlem ve yerel para, alış fiyatı raporları. Stok miktarı görünüm ile bağımsız hareket toplamı uyuşmadığında kesin rakam verilmez.
- Fatura başlık–satır tutar farkı, benzer belge adayları, bağlantısız hareket, müşteri başına fatura ortalaması/medyanı. Benzerlik kesin mükerrerlik veya hata hükmü değildir.
- CRM kitap kalitesi, yinelenen kod/ISBN/ad, kitap–kişi gerçek yazar bağları, çok yazarlı kitaplar, yayıncı/alt marka/iletişim, müşteri vergi/kişi/coğrafya ilişkileri, yayın/kayıt tarihleri, editör ataması, sözleşme, iş planı ve randevuya bağlı açık görev raporları.
- Logo kitap kodu–CRM stok kodu ve müşteri vergi numarası eşleşme kanıtı. Eşleşmeyen veya çoğul eşleşen kayıtların tutarları korunur. Ad benzerliği kimlik kabul edilmez; çok yazarlı satış kişi sayısıyla çoğaltılmaz.
- En çok4 bağımsız bölümden oluşan rapor. Kullanıcının her koşulu plan bölümü veya açık eksik kapsam kaydıyla eşlenir; yapılamayan filtre atılıp daha geniş nüfusla cevap verilmez.

## İş tanımı ve kaynak eksikleri

Gerçek maliyet/iade maliyeti doğrulanmadığından alış fiyatından kâr üretilmez. PAYTRANS alanının varlığı, fatura–ödeme kapamasını kanıtlamaz; FIFO veya TOTAL−PAID varsayımıyla kesin yaşlandırma hesaplanmaz. Sözleşme revizyon/yenileme önceliği, geçmiş yayınevi değişim zamanları, iş aşamasına giriş anı ve denetim alanlarının çözümü kanıtlanmadan kesin tarihçe üretilmez. Vergi numarası metni ülke/kimlik türü doğrulanmadan kesin tüzel kişi kimliği değildir.

Her böyle boşluk `gaps` alanında açıklanır. Destek eksikliği, gerçek kullanıcı belirsizliği, kaynak sözleşmesi hatası ve erişim hatası ayrı statülerdir. Kısmen okunabilen rapor `PARTIAL_ANSWER`; kaynak eksikliği başarı sayılmaz. Bölüm sonuçları, notlar, tanımlar ve kaynak kapsamı aynı `resultId` altında saklanır; arayüzde ayrı bölüm ve tam CSV olarak açılır.

## Dosyalar

`planner.py`, `model_schema.py`, `language.py` tipli plan/doğal tarih/koşul denetimi; `contracts.py` temel ölçüler; `operations.py` Decimal işlemler; `executor.py` kaynak okuma/aktiflik/şema/dönem/tutar korunumu; `crm_reports.py`, `logo_reports.py`, `invoice_reports.py`, `cross_reports.py` kapalı rapor sözleşmeleri; `result_metadata.py` ortak etiket/birim/formüller. Kaynak envanteri raporları kabul kanıtıdır, eski katalog yerine tahmini ilişki kaynağı değildir.

## Gerçek kabul kapısı

Yerel test yoktur. Test sunucusunun gerçek API'sinin aynı yürütmedeki tam sonucu, bağlı Logo/CRM üzerindeki bağımsız SELECT/hesapla karşılaştırılır: kolon kimlikleri, tüm satırlar, anahtar, NULL/sıfır, sayısal değer ve kesilme. 100 karmaşık günlük dil sorusu geniş regresyondur; bir SQL'in çalışması doğru cevap kabulü değildir. Kapsam/sınır kontrolleri tam cevap başarısından ayrı sayılır. Kod hashleri ve oturum temizliği kaydedilir; yayın değişirse önceki kabul yeni sürüme taşınmaz.
