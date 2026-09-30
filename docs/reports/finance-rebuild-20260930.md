# Zeki finans yeniden kurulum — 30 Eylül 2026

## İlk incelemenin sınırı

Yeni motor yazılmadan önce gerçek API ve bağımsız Logo/CRM okumalarıyla 10 soru incelendi.
7 soruda somut hata, 3 soruda eksik doğrulama vardı; tam cevap kabulü geçen soru yoktu.
Bu küçük seçkinin sonucu bütün ürün için bir doğruluk yüzdesi değildir. Koşu sırasında eski katalog
sürümü değiştiğinden tek bir katalog sürümüne kabul de verilmedi.

## Somut nedenler

| Örnek | Bağımsız kaynak | Eski cevaptaki sorun |
|---|---|---|
| 29 Eylül satılan kitap adedi | 62.530 toplam | 1.326 kitap satırı; istenmeyen kırılım |
| Aynı gün toptan fatura sayısı | 239 belge | 9.515 hareket satırı sayılmış |
| Aynı gün perakende satış fatura tutarı | 232.275,81 | 2015 kaynak kodu seçilmiş, NULL |
| Kanal bazında adet | 7 kanal | 2.003 kitap/kanal satırı; yanlış sonuç düzeyi |
| Aktif CRM kitap / yazar kişi | 9.380 / 660 | Logo cari alanına yönelme veya eksik cevap |
| Aylık tahsilat | Mali hareket sözleşmesi gerekir | tinyint kullanıcı ayarı tahsilat ölçüsü sanılmış |

Alan adının benzemesi iş anlamını kanıtlamıyor. Özellikle boş `new_yazarid` kolonunu yazar ilişkisi
saymak yanlış; kitap yazar künyesi metni ile aktif yazar kişi sayımı ayrıldı. Kesin yaşlandırma ve
hedef-gerçekleşen hesaplarında bağımsız iş tanımı kabulü bulunmadığı için sayı doğruluğu iddia edilmedi.

## Yeni uygulama

Yeni `finance_query` paketi eski soru, SQL, eş anlamlılar ve semantik katalog kullanmaz.
Kimlik doğrulama, veri yetkisi, kaynak bağlantısı ve sonuç saklama mevcut uygulamaya entegrasyon içindir.
Model yalnız kapalı sorgu planını üretir. Gerçek kolon doğrulaması, açık dönem kapsamı, sabit ölçü
hesabı, aktif CRM süzgeci, tekil stok kodu eşleşmesi ve toplam koruması yürütme katmanındadır.
Tanımsız koşul sessizce atılmaz; eski sorgu üreticisine dönülmez.

Mimari, alan kaynakları, desteklenen ölçüler ve geri dönüş:
[Finans sözleşme motoru](../architecture/finance-contract-engine.md).

## Kabul durumu

- Eski sorgulardan bağımsız 100 yeni soru ve referans hesapları hazırlandı.
- Sayısal tam cevaplar, kapsam dışı isteğe doğru sınır koyma ve doğrulanamayan durumlar ayrı raporlanır.
- Tam sonuç API kimliğiyle alınır; tüm satır/kolon/değer/NULL/kesilme karşılaştırılır.
- Test sunucusunda `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build` tamamlandı.
- 17:42:21'de VPN, `/run/timas-vpn-crv.auth` bulunamadığı için kapandı. Logo ve CRM yeni SQL
  bağlantıları `08S01 / Adaptive Server unavailable` ile başarısız oldu; rota artık tun0 üzerinden değil.
- Yeni motor etkinleştirilmedi. Gerçek API + Logo/CRM kabulü ve yeni cevapların mobil tablo/dışa aktarım
  akışı **DOĞRULANAMADI**. Yerel test veya müşteri VM kurulumu yapılmadı.
- Tam Git geçmişi bundle yedeği doğrulandı. Canlı PostgreSQL/kod/ayar yedeği tamamlanma ve bütünlük
  kontrolü bekliyor; bu madde yedek bitince güncellenecek.

Bu rapor yeni motorun üretime hazır olduğu anlamına gelmez. VPN erişimi, yayımlanmış CRM metadata
doğrulaması, tam test sunucusu kurulumu ve gerçek kabul koşuları tamamlanmalıdır.
