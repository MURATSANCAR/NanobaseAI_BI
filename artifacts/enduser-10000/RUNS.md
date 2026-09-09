# Çalıştırma kayıtları

- `before`: dengeli 10.000 soruluk düzeltme öncesi deterministik tarama. 4.000 PASS, 6.000 model yolu denenmedi.
- `model-before`: gerçek modelle üç kontrollü soru. Üç yanlış toplam; iptal/satır türü filtreleri eksik.
- `final`: üretime yayımlanmış üç düzeltme sonrasında 10.000 soruluk nihai kontrollü yürütme (tamamlanınca eklenir).
- `production`: üretim kataloğuyla 10.000 planlama kontrolü ve seçili gerçek API çağrıları (tamamlanınca eklenir).
- `model-after`: gerçek model yolu özellikle seçilerek aynı üç sorunun yeniden denemesi (tamamlanınca eklenir).
- `deploy`: ilk yayın ve düzeltme yayını hash kayıtları, 463 regresyon testinin çıktısı.

Ara çalıştırmalar nihai skora dahil değildir:
- `baseline`: DATE_ yanlışlıkla TEXT tanımlı olduğu için geçersiz ilk fixture. Ürün hatası sayılmaz.
- `baseline-valid`: tarih tipi düzeltildi, ancak yıl dağılımı dengelenmeden önceki veri kümesi.
- `preflight`, `after-all-fixes`: küçük geliştirme örnekleri.
- `after-local`: yalnız kırılım ayrıştırma düzeltmesi; dolaylı JOIN desteği henüz yok.
- `after-paths`: kırılım ve JOIN düzeltmeleriyle 10.000 PASS; son varsayılan filtre kontrolünden önce.

Kontrollü test, üretim verisi doğruluk oranı değildir. Gerçek modele yönlenmeyen cevaplar model başarısı olarak raporlanmaz. Model yoluna geçmesi gereken ancak çağrılmayan sorular PASS sayılmaz.

## Son sürüm

- `policy-final`: ödeme referansı sözleşmesi ve global LG_SLSMAN çözümü dahil üretimle aynı kaynak hashleriyle kontrollü koşu.
- `final`: önceki TOP/LIMIT düzeltmesinin 10.000 PASS koşusu; son sürüm yerine kullanılmaz.
- `live-readiness-before`: 3.190 plan hazır, 6.475 model gerektiriyor, 335 veri bulunamadı. Bu bir çalıştırma sonucu değildir.
- `live-policy-v2-invalid`: referans yalnız firma 411 ve iadeler için sıfır grupları kullandığından gerçek API karşılaştırması geçersizdir. Hata oranına dahil edilmez.
- `live-final-v3`: iki aktif firma (211, 411), iadeler hariç satılan adet, satır ödeme planı önceliği ve fatura temsilcisiyle bağımsız SQL karşılaştırması. Referans sorgusu zaman sınırı 120 saniyedir; API üretim sınırları korunur.

- `verified-final`: ortak küresel tablo, fiziksel/mantıksal ad denetimi ve LEFT JOIN kontrolü dahil son yayımlanmış derleyiciyle kontrollü koşu.
- `live-before-shared-global`: ortak tabloyu her firmada arama kusuru ve ad çözümleme reddinin ara kanıtı. Son durum yerine kullanılmaz.
- `readiness-final`: son katalogdaki 10.000 sorunun planlama sonucu, dört ayrık ID diliminin birleştirilmesiyle oluşur.
- `live-final`, `live-extra-final`: son yayın sonrası gerçek API örnekleri. Türkçe CP1254 CI harf eşleştirmesi, tüm satırlar için bağımsız SQL karşılaştırması.
- `deploy/global.json`: 471 test sonrası son çekirdek yayını. `deploy/left.json` ara sürümdür.

- `acceptance-final`: 474 test sonrası bitişik filtre/ölçü ayrımı dahil nihai kontrollü 10.000 koşusu.
- `deploy/modifier.json`: son ayrıştırıcı yayını. Ana 12 canlı örnek ortak tablo yayını sonrasında; dört ek örnek bu ayrıştırıcı yayını sonrasında doğrulandı.
