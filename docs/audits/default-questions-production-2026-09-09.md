# Hazır sorular ve doğal dil kalite kabulü — 9 Eylül 2026

Dört hazır soru düzeltildi ve yayımlandı. Mevcut sertifikalı iş tanımlarıyla gerçek sonuç doğrulaması geçti. **Ürünün her serbest ifadeyi doğru anladığı veya bütünüyle üretime hazır olduğu sonucu çıkarılamaz:** aşağıdaki dil boşlukları ve katalog riski açık.

## Yayımlanan düzeltmeler

- Sıralama sorusunda açık ölçü (parantez içindeki adet dahil) korunuyor; fiilden çelişkili bir tutar ölçüsü eklenmiyor. “On kitap” gibi yazıyla sıralama sayısı da doğrulandı. Çözüm soru metinlerinin listesini eşleştiren statik cevaplar kullanmıyor.
- İlk/top sıralamasında adlandırılan kolonlar kırılım oluyor; ölçünün fatura/satır düzeyine uyumu mevcut kontrolden geçiyor.
- “Net ciro 2025” içindeki yıl artık ilgisiz CSCARD.CIRO filtresine dönüşmüyor. Açık `=`/`:` fiziksel kolon filtresi sözdizimi korunuyor.
- Hazır iade sorusu **İade tutarına göre ilk 10 müşteri** oldu. Yanlışlıkla oran formülüne bağlı “iade adedi” kavramı DEPRECATED durumuna alındı; oran kavramından miktar eş anlamlısı çıkarıldı. Doğru miktar ve oran formülleri değiştirilmedi; önceki kayıtlar yedeklendi.
- Tablo ilk 10'un tamamını gösteriyor. Kesirli grafik değerleri tam sayıya yuvarlanmıyor. Tek sertifikalı RATIO ölçüsü para gibi gösterilmiyor; katsayı korunuyor, yüzde ölçeği tahmin edilmiyor.
- Eksik cevap durumunda teknik kolon adları yerine anlaşılır hata metni gösteriliyor.

## Kabul sonuçları

| Kontrol | Sonuç | Kanıt |
|---|---|---|
| Yerel semantik regresyon | 501 geçti | Gerçek DB kabulünden ayrı; resolver kaynak hashi kaydedildi |
| Dört hazır sorunun 20 söylenişi | 20 LIVE_PASS | variants-accepted.jsonl |
| Adet / iade adedi / iade oranı / satış tutarı ayrımı | 4 LIVE_PASS | measure-edges.json |
| 2025 → Peki 2024 → sadece KITAPCI | 3 LIVE_PASS, katalog v14 | followups-accepted.json |
| Karmaşık gerçek API soruları | 100 LIVE_PASS; 0 başarısız, 0 doğrulanamayan | complex-final-results.json |
| Kaynak ve katalog tutarlılığı | PASS | acceptance-verification.json |
| Arayüz | Üretimde gerçek sorular; 320/390/768/1440 genişlik kontrolü | ui-checks.json |

Karmaşık sette tablo türü dağılımı: {'7': 32, '8': 68}. En büyük tam sonuç 85,703 satırdır. API'nin aynı yürütmeye ait saklanan **tam** sonucu bağımsız referans sorguyla karşılaştırıldı; üretilen SQL'i yeniden çalıştırmak doğrulama olarak kullanılmadı. Kolon kimlikleri, satır çokluğu, sayısal değerler ve kesilme bilgisi kontrol edildi. NULL, boş metin ve sayı ayrımı korunur; sayılar beş ondalık basamak, metinler doğrulanan Türkçe büyük/küçük harf duyarsız DB kuralıyla kıyaslanır.

Hazır soruların beklenen satır sayıları: kanal net cirosu 17, iade tutarı sıralaması 10, aylık iskonto 8, en çok satan kitaplar 10. Kitap kırılımı sertifikalı ITEMS.NAME tanımıdır; aynı adlı farklı stok kodlarının ayrı kitap sayıldığı iddia edilmez. Satılan adet pozitif satış miktarıdır, net/iade düşülmüş adet değildir.

İade oranı referansı ve API değeri `0.09158654324883332`; KPI gösterimi `0,0915865`, para işareti yok. Mobilde görünür ve yatay taşma yok. Giriş yazısı 16px, sohbet düğmeleri en az 44px. Kanal grafiği 12/17 sınırını açıkça gösterirken tablo 17 satırın tamamını gösterir.

## Açık kalanlar — üretime hazır kararı için engeller

1. **Doğal ifade çözümleme:** “En çok iade alan 10 müşteri” hâlâ “alan”, “iptal edilen kaç sipariş var” hâlâ “edilen” için gereksiz netleştirme istiyor. “kitap olmayanlardan en çok 10 satılan ürün” NON_SQL_QUERY dönüyor. Bu ifadeler güncel gerçek API'de yeniden üretildi ve başarılı sayılmadı.
2. **Belirsiz ölçü:** “En çok satan 10 kitap” açık adet/tutar belirtmeden SQL döndürüyor. İş anlamı bağımsız doğrulanmadı; DOĞRULANAMADI. Açık ölçülü hazır soru geçiyor diye bu ifade otomatik doğru kabul edilmiyor.
3. **Brüt kâr marjı katalog riski:** Aynı sertifikalı ad altında farklı kapsamlı 0–1 ve ×100 tanımları var. Son denemede maliyetlendirilmiş satış satırı formülü seçildi; bu, diğer alternatiflerin güvenli olduğunu kanıtlamaz. Sekiz çok anlamlı ad grubunun tamamı hata değildir; fatura/satır alternatifleri ve eşdeğer toplamlar ayrıca ayrılmalıdır.
4. **Kapsam sınırı:** Bu 100 soru, her serbest ifade, her iş metriği, her sıfır/boş veri durumu veya tüm ürün yük kapasitesi için garanti değildir. Anlam belirsizken SQL çalışması başarı sayılmaz.

`test` ve `sen kimsin?` soruları MODULE_INTRO döndü; SQL üretmedi. Bunlar sayısal 100 soruya eklenmedi. Yedi serbest dil gözlemi `language-probe.json` içinde ayrı tutulur.

## Sürüm ve kanıtlar

- Karmaşık koşu katalog hashi: `6474bbad8e2bf3112c619ac2a3dbb93255abf5c33c16cc245de8a4c9341a1736`.
- `source-manifest.json`: üretimdeki backend kaynakları. Kabul sonunda değişmedikleri kontrol edildi.
- `frontend-manifest.json`: son arayüz `index-CzLs4emz.js`; sunucu hashleri derlemeyle eşleşti.
- `deployed-source/`: resolver ve yayımlanan arayüz kaynak kopyaları. Arayüz üretimdeki `/api/v1/ask` akışına göre izole derlendi; yerel HEAD'in tümünün yayımlandığı iddia edilmez.
- `prompts-final-status.md`: 100 sorunun nihai listesi ve statüleri.
- `default-prompts-status.md`: 20 hazır soru varyasyonu.
- `live-100-accepted/`: her sorunun gerçek API yanıtı, referans SQL'i, sonuç hashleri ve satır sayıları.

İlk iki kısmi koşu düzeltme nedeniyle 21 ve 3 soruda durduruldu; final 100'e eklenmedi. Servis yeniden başlatılırken görülen bağlantı hatası başarı sayılmadı, servis sağlıklı olduktan sonra ilgili kabul tekrarlandı.

Yerel kanıt dizini: `outputs/default-questions-20260909/`. Sunucu yedeği: `/data/nanobaseai/bi/backups/default-questions-20260909/`.
