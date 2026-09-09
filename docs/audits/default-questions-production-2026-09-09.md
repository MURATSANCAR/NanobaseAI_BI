# Hazır sorular ve doğal dil kabulü — 9 Eylül 2026

## Düzeltmeler

Sıralama isteğinde kullanıcının açıkça yazdığı sertifikalı ölçü, genel dil belirteci diye atılmaz. Parantez içindeki adet de buna dahildir. Aynı fiili açıklayan açık ölçü bulunduğunda fiilden ikinci, çelişkili tutar ölçüsü eklenmez. Top-N isteğinde adlandırılan kolonlar kırılım olarak kullanılır; mevcut ölçü düzeyi kontrolü çalışır.

Hazır iade sorusu `İade tutarına göre ilk 10 müşteri` olarak açık ölçüyle sunulur. `En çok iade alan` ifadesinin her bağlamdaki anlamı çözülmüş değildir. `INCOMPLETE_ANSWER` teknik iç ayrıntıları ana cevap yerine anlaşılır bir başarısızlık açıklamasıyla sunulur. En fazla 20 satırlık sonuçlar tabloda bütünüyle gösterilir; ilk 10 listesinin son iki kaydı yalnız Excel'e bırakılmaz.

## Doğrulanmış kapsam

- 501 yerel semantik test geçti. SQLite/fake model testleri gerçek veri kabulü yerine sayılmadı.
- Dört hazır sorunun gerçek üretim API tam sonuçları bağımsız DB sorgularıyla karşılaştırıldı: kanal cirosu 17, iade listesi 10, aylık iskonto 8, kitap listesi 10 satır. Hepsi eşleşti.
- Sözcük sırası, soru eki ve ilk/top değişen 20 ifade, aynı bağımsız referanslarla LIVE_PASS aldı.
- Son katalogla 100 karmaşık soru koşusu sürüyor; henüz tamamlandı sayılmaz. Takip zinciri (2025 → Peki 2024 → sadece KITAPCI) bağımsız, firma 211+411 referansıyla 3/3 geçti.

## Kabul kapsamı matrisi

| Alan | Beklenen davranış | Bu yayındaki kanıt |
|---|---|---|
| Adet / tutar / oran | Açık ölçüyü koru, çelişkili ölçü ekleme | Adet sıralaması ve iade adedi/oran ad çakışması düzeltildi; dört ek gerçek veri ölçü kontrolü geçti |
| İlk/top ve sıralama | Doğru kırılım, limit ve sıralama | 20 ifade; “on kitap” yazıyla sayı da doğrulandı |
| Dönem | Varsayılanı görünür tut, kısmi dönemi belirt | Dört örnek 2026 mevcut kayıtları; diğer dönemler karmaşık sette |
| Konuşma devamı | Yeni dönemi/filtreyi önceki doğru plana uygula | 3 takip isteği, bağımsız tam sonuç eşleşmesi |
| Olumsuzluk | Hariç tutma/yokluk koşulunu düşürme | Mevcut güvenlik regresyonları; tüm doğal ifade biçimleri kanıtlanmadı |
| Belirsiz iş terimi | İş anlamını uydurma, eksik bilgiyi sor | Mevcut netleştirme; doğal dilde soru kalitesi açık |
| Çok tabloluluk | Tutarı JOIN ile çoğaltma | Mevcut 100 karmaşık soru koşusu |
| NULL/sıfır/kısmi veri | Sıfıra bölme ve eksik veri anlamını koru | Yerel regresyonlar + ilgili referanslar; sınırsız kapsam iddiası yok |
| Sonuç sunumu | API/tabloda aynı yürütme, ilk 10'un tamamı görünür | Gerçek ekran kontrolü |
| Bilinmeyen soru | SQL çalıştı diye doğru sayma | Oracle yoksa DOĞRULANAMADI |

## Kanıt konumları

`outputs/default-questions-20260909/`: bağımsız sorgular, tam API yanıtları, ifade listesi/statüler ve koşu çıktıları. Üretim yedeği `/data/nanobaseai/bi/backups/default-questions-20260909/`.

Bu rapor herhangi bir serbest cümlenin koşulsuz doğru yanıtlanacağı veya tüm ürünün üretime hazır olduğu iddiası değildir. Katalogdaki `iade adedi`/oran çakışması giderildi. “iade alan”, “iptal edilen”, “tamam kitap olsun” ve olumsuzluk içeren bütün doğal ifade biçimlerinin sorunsuz çözüldüğü kanıtlanmış değildir; bunlar açık takip kapsamıdır.

## İlave düzeltmeler ve yayın sınırı

“Net ciro 2025” içindeki yılın ilgisiz CSCARD.CIRO filtresine dönüşmesi engellendi; açık `=`/`:` kolon filtresi sözdizimi korunuyor. Adet/oran çakışmasında yanlış isimli oran kavramı silinmedi, DEPRECATED durumuna alındı; doğru oran ve miktar formülleri değiştirilmedi. Önceki katalog kayıtları üretim yedeğinde saklandı.

İlk iki 100 soru koşusu düzeltme gereği 21 ve 3 soruda durduruldu; final 100 koşusuna eklenmez. API doğrulaması üretimdeki gerçek kaynak hashleriyle kaydedilir; yerel HEAD'in tümü yayımlandı iddiası yoktur. Yeniden başlatma sırasında oluşan bağlantı hatası başarı sayılmadı, servis sağlıklı olduktan sonra ilgili sorular tekrarlandı.

## Katalog taraması: tamamlanmayan risk

Sertifikalı ölçü adlarının taraması sekiz çok anlamlı ad grubu buldu (`measure-name-collisions.json`). Bu sekiz hata demek değildir: fatura/satır düzeyi alternatifleri ve aynı toplamı farklı yazan formüller mevcut. Ancak `brut kar marj` grubunda maliyetlendirilmiş satırları seçen 0–1 oranıyla farklı kapsamlı ×100 formülü aynı ad altında bulunuyor. Bu grup ayrı iş tanımı ve gerçek DB kabulü gerektirir; otomatik olarak aynı kabul edilmedi veya tahmini formülle değiştirilmedi.

İskonto grafiğinde kesirli ölçüler artık tam sayıya yuvarlanmıyor. Biçimlendirme sayının katsayı değerini korur, birim bilgisi olmadan yüzdeye çevirmez. Yeni üretim arayüzü `index-Cyvm4uWc.js`; 320/390/768/1440 genişliklerinde taşma yok, giriş yazısı 16px. Kanal tablosu 17 satırın tamamını, kitap tablosu 10 satırın tamamını gösteriyor; grafik kendi ilk 12/17 sınırını açıkça belirtiyor.

## Serbest dilde yeniden üretilen eksikler

| İfade | Güncel gerçek API yanıtı | Değerlendirme |
|---|---|---|
| En çok iade alan 10 müşteri | CLARIFICATION, “alan” koşulunu soruyor | Dil anlama eksikliği; cevap başarısı değil |
| iptal edilen kaç sipariş var | CLARIFICATION, “edilen” koşulunu soruyor | Dil anlama eksikliği; cevap başarısı değil |
| kitap olmayanlardan en çok 10 satılan ürün | NON_SQL_QUERY, “olmayanlardan” tanımsız | Olumsuzluğun bu biçimi çözülemiyor |
| En çok satan 10 kitap | TEXT_TO_SQL | Açık adet/tutar ölçüsü yok; bağımsız iş anlamı doğrulanmadığı için DOĞRULANAMADI |
| 2026 brüt kâr marjı | TEXT_TO_SQL | Bu istekte maliyetlendirilmiş satır formülü seçildi; ad çakışması riski ayrıca açık |
| test / sen kimsin? | MODULE_INTRO | SQL yerine BI modül tanıtımı görüldü; sayısal doğrulama kapsamı değil |

Bu yedi gözlem 100 karmaşık veya 20 varyasyon başarısına eklenmez. Tam yanıtlar `language-probe.json` dosyasında.

İade oranı KPI ekranında `iade_ora` adı para gibi yorumlanıp `₺0` gösteriliyordu. Tek sertifikalı RATIO ölçüsü olan deterministik cevapta arayüz artık açık sayısal biçim taşır; grafik bu biçimi alan adına dayalı para tahmininden önce uygular. Hesaplanan katsayı değiştirilmez, açık backend biçimi korunur.

Son arayüz kabulünde iade oranının bağımsız referansı ve API değeri `0.09158654324883332`, KPI gösterimi `0,0915865`; para işareti yok. Dört genişlikte değer görünür ve sayfa taşmıyor.

## Karşılaştırmanın sınırları

Gerçek sonuçlar kolon kimliğine göre hizalanır; satır sırası yerine tüm satır çokluğu karşılaştırılır. NULL, boş metin ve sayılar ayrı türlerdir. Sayılar beş ondalık basamağa yuvarlanır; metinler doğrulanan Türkçe büyük/küçük harf duyarsız DB karşılaştırma kuralıyla kıyaslanır. Kitap kırılımı sertifikalı `ITEMS.NAME` tanımıdır; aynı başlıktaki farklı stok kodlarının ayrı kitap sayıldığına dair bir iddia yoktur. Satılan adet, mevcut sertifikalı pozitif satış hareketi miktarıdır; net satış/iade düşülmüş adetle aynı kabul edilmez.
