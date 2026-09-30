# Finans soru motoru — bağımsız sözleşme mimarisi

2026-09-30. Kullanıcı: mevcut yapıyı yedekle, finans soru akışını sıfırdan kur; eski sorgu/katalog kullanma.

## Sınır

Yeni paket `backend/semantic_bridge/finance_query/`: bağımsız tarih çözümleme, kapalı plan şeması,
sürümlü iş tanımları, gerçek şema doğrulama, açık kaynak/dönem seçimi, deterministik SQL ve tam sonuç.
Eski resolver, eş anlamlılar, eski soru SQL'leri, aday havuzu ve SQL model istemi kullanılmaz.
Mevcut API'nin kimlik doğrulaması, kişi veri yetkisi, bağlantı altyapısı, model taşıyıcısı ve sonuç saklama
entegrasyon sınırıdır; bunlar yeni iş anlamı için kaynak değildir.

`FINANCE_QUERY_MODE=contract` yeni finans hattını açar. `off` yedekli geri dönüş seçeneğidir.
Yeni hat üstlendiği soruyu eski SQL üreticiye düşürmez. Tanımsız hesap/kısıt sessizce atılmaz; netleştirme
döner. Finans dışı portal işlevlerinin yeniden yazımı bu değişikliğin kapsamı değildir.

## İş akışı

1. Soru → bağımsız tarih aralıkları + kapalı sözleşmeden metric/dimension/filter planı.
2. Açık kaynak adı, belge sayımı, tür, ölçü ailesi, süzgeç değeri ve plan bütünlüğü kontrolü.
   Model ikinci okumada sorudan düşen koşulları da denetler; bu bir doğruluk ispatı değildir.
3. `SEMANTIC_FIRMS` kaynak kapsamı ∩ canlı `L_CAPIPERIOD`. Aynı şirketin yıllık kaynaklarıdır.
   Dönem boşluğu/örtüşmesi varsa durulur; en büyük kod/ilk tablo veya örnek MIN/MAX ile kaynak seçilmez.
4. Gerçek `INFORMATION_SCHEMA.COLUMNS` ile kolon ve mali değer türleri denetlenir.
5. SQL yalnız sabit sözleşme ifadeleri ve kaçırılmış literal değerlerden oluşur. Model SQL gönderemez.
6. Satışlar gereken düzeyde toplanır. CRM eşlemesi aktif stok kodunda tekil olmalıdır; çoklu anahtarda
   sorgu durur. LEFT birleştirme öncesi/sonrası mali toplamlar korunur. Eksik künye açık veri notudur.
7. Tam sonuç, aynı yürütmenin kimliğiyle önizleme/dışa aktarmaya verilir. Kesilen sonuç başarı değildir.

`contractChecked` teknik sözleşme denetimidir; `independentlyVerified=false` canlı bağımsız kabulün yerine
geçmez. Eski `certified=true` anlam karışıklığı yeni cevaba taşınmaz. Kod içindeki tanımların hash'i
her cevaba ve kayıt izine yazılır; canlı eski katalog değişiklikleri bu tanımları değiştirmez.

## Alan anlamı ve kaynak kanıtı

- Logo'nun 2016 tarihli **Aktarımlar** belgesi (Logo tarafından yazılmış, bayi sitesindeki kopya):
  https://www.sdmyazilim.com.tr/var/uploads/1500467351-aktarimlar.pdf
  Sayfa 178/186/217/283: `STLINE.LINENET` satır net toplamı; 173/225: `INVOICE.NETTOTAL` fatura net toplamı.
  Eski belge güncel kurulumu tek başına doğrulamaz; canlı şema ve bağımsız hesap zorunludur.
- Microsoft, kurum içi Dynamics metadata açıklamaları:
  https://learn.microsoft.com/en-us/dynamics365/customerengagement/on-premises/developer/customize-entity-attribute-metadata?view=op-9-1
  Kolon açıklaması, görünen ad ve lookup ilişkisi ayrı metadata özellikleridir. Kuruma özel `new_*`
  alanlarının iş anlamı internetteki benzer bir alan adından aktarılmaz.
- Canlı 2026-09-30 inceleme: aktif `new_kitapBase` 9.380 kayıt, `new_yazarid` dolu 0;
  `new_Yazar` dolu 3.072, aktif Contact eşleşmesi 2.140. `new_yayineviid` aktif marka eşleşmesi 9.253;
  `new_yayinciid` 2.541. Stok kodunda aktif çoğulluk bulunmadı (her yürütmede tekrar kontrol edilir).
- Yazar kırılımı `new_yazartext` kitap künyesi metnidir, kişi/telif kimliği değildir.
  Yazar kişi sayısı ise `ContactBase.statecode=0 AND new_yazarmi=1`; aynı kavram gibi birleştirilmez.

## Kabul ve bilinen kapsam

Yeni bağımsız koşucu `scripts/acceptance/finance_contracts/live.py` yalnız Linux test sunucusunda,
gerçek API ve doğrudan pyodbc referansı ile çalışır. Üretim derleyicisini veya eski SQL'leri içe aktarmaz.
30 soru; tam kolon kimliği, tüm anahtarlar/satırlar, sayı/NULL ve kesilme karşılaştırması; büyük sonuç,
kanal/kitap kırılımı, yıllık kaynak değişimi, gün/ay, boş dönem, yanlış kaynak ve dürüst netleştirme.
Kaynaklar salt okunur. Var olan timasai hesabının 15 dk oturumu finally'de silinir. Her 10 sonuç raporlanır.

İlk sözleşme: satış/net satış/iade tutarı, satılan/net adet, fatura sayısı/toplamı, müşteri ödeme
hareketleri, aktif CRM kitap/yazar/cari sayıları. Kâr, kesin yaşlandırma, bütçe-hedef, döviz dönüşümü
ve karmaşık koşullar iş tanımı genişletilene kadar netleştirmedir; destekleniyor veya üretim kabulü
geçti diye sunulmaz. Belgeli kapsam büyümesi yeni sürüm ve bağımsız referans gerektirir.

## Yedek ve geri dönüş

Yerel tüm Git geçmişi: `/Users/msancar/.codex/backups/nonobase-finance-20260930/repository.bundle`
(bundle verify başarılı). Canlı yedek: `/data/nanobaseai/bi/backups/finance-contracts-20260930/`;
metadata PostgreSQL özel biçim dump, kaynak/arayüz/servis ayarı arşivleri ve SHA256 manifesti.
Sırlar yalnız sunucunun root erişimli yedeğinde; Git'e veya rapora yazılmaz.
Geri dönüş: yeni hattı `FINANCE_QUERY_MODE=off` ile kapat, köprüyü yeniden başlat. Motor kaynakları
değiştiyse önce yedek arşivden ayrı dizine çıkarıp manifesti doğrula; canlı ağaca rastgele dosya basma.
Metadata bu değişiklikte düzenlenmez; dump geri yüklemesi diğer modüllerin yeni verilerini sileceğinden
yalnız ayrı kurtarma veritabanına yapılır.

Durum: kodlama; canlı kabul henüz yapılmadı. `main` → test sunucusu → kabul sırası zorunludur.
