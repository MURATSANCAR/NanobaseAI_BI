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
