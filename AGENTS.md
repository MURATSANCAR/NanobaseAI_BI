# Çalışma kuralları

@/Users/msancar/.codex/RTK.md

## Ürün tasarımının ana kuralı: mobil uyumluluk

Kullanıcının açık talebi: bu projede yaptığımız bütün tasarımlar mobil öncelikli ve mobil uyumlu olmalı. Bu, yalnız kokpit için değil giriş, modüller, GIF/görseller, menüler, tablolar, grafikler ve tüm yeni arayüzler için geçerlidir.

320px, 390px, 768px ve masaüstü genişliklerinde ilgili akışları tarayıcıda kontrol edin. Sayfa yatay taşmamalı; geniş tablo/kod yalnız kendi kapsayıcısında kaymalıdır. Mobil kontroller dokunulabilir, metinler okunabilir olmalı; temel özellikler mobilde erişilebilir kalmalıdır. Taşmayı sayfa düzeyinde overflow:hidden ile gizlemeyin. Kokpit ayrıntıları: apps/cockpit/AGENTS.md.

## Zorunlu ürün doğrulama kuralı: bağlı gerçek DB ile test

Kullanıcının kalıcı talebi: ürünün veri alma, SQL üretme, hesaplama, raporlama veya sonuç sunma davranışını etkileyen her değişiklik, bağlı gerçek veritabanı ve gerçek uygulama/API akışı üzerinden doğrulanmadan tamamlanmış veya üretime hazır sayılmaz.

- Birim testleri ve kontrollü test verileri regresyon kontrolü için kullanılabilir; gerçek DB kabul testinin yerine geçmez. Bu iki test türünün sonuçlarını ayrı raporlayın.
- Etkilenen akışları basitten karmaşığa doğru sınayın. SQL/semantik katman ve katalog değişikliklerinde çok tablolu sorguları; ilgiliyse 7–8 tablolu JOIN, dönem karşılaştırması, NULL/sıfır değerler ve büyük sonuçları kapsayın. Mevcut 100 karmaşık soru setini ilgili geniş regresyonlarda kullanın; yeni doğrulanmış hata senaryolarını sete ekleyerek kapsamı geliştirin.
- Başarıyı yalnız SQL'in çalışmasına göre vermeyin. Gerçek API'nin kullanıcıya sunduğu aynı yürütmenin tam sonucunu, bağımsız referans sorgu/hesapla karşılaştırın. Kolon kimliklerini, satır sayısını, sayısal değerleri ve kesilme bilgisini kontrol edin. Uygulamanın ürettiği SQL'i yeniden çalıştırmak, uygulamanın verdiği cevabı doğrulamak yerine geçmez.
- Tablo, grafik veya dışa aktarım değiştiyse ilgili gerçek kullanıcı akışını da doğrulayın. Önizleme sınırını tam sonuç sınırıyla karıştırmayın.
- Düzeltme sonrası başarısız senaryoyu yeniden çalıştırın. Test edilen kod/katalog sürümünü veya içerik hashlerini, soru kimliğini, sonucu ve kanıt dosyalarını kaydedin. Sonradan değişen kodu önceki testlerle doğrulanmış saymayın.
- Uzun soru koşularında her 10 tamamlanan soruda başarı, başarısızlık ve doğrulanamayan sayısını paylaşın. Sonda soru listesi, statüler, uygulanan çözümler ve açık kalanları verin.
- Gerçek DB/API erişimi yoksa veya bağımsız referans bulunamıyorsa durumu açıkça **DOĞRULANAMADI** olarak raporlayın; başarı veya tamamlanma iddiasında bulunmayın. Tahmini iş tanımlarıyla eksikleri kapatmayın.
- Gerçek veri testlerini salt okunur ve kontrollü yükle yürütün; aynı ağır koşunun birden fazla kopyasını başlatmayın. Canlı kabul sonucu, doğrulanan yayın sürümüne ait olmalıdır.

Bu bir çalışma/kabul kuralıdır; zamanlanmış otomasyon talebi değildir. Yalnız dokümantasyon gibi ürün davranışını etkilemeyen değişikliklerde gerçek DB sorgusu çalıştırmak gerekmez.
