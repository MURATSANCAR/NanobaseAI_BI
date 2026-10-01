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
| Logo okuması | 19:03:35 SQL Server 1205 | API ve bağımsız referans deadlock kurbanı olmuş; şema/AI hatasından ayrı kaynak sorunu |

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

## Yedek

- Git geçmişi: `/Users/msancar/.codex/backups/nonobase-finance-20260930/repository.bundle`, `git bundle verify` başarılı.
- Test sunucusu: `/data/nanobaseai/bi/backups/finance-contracts-20260930/`; metadata DB, kod, gerçek sunulan arayüz, servis/ortam ayarları ve hash manifesti.
- PostgreSQL dökümü 13.119.667.444 bayt. Bütün arşivlerin hash/okuma denetimi ve `pg_restore --file=/dev/null` tamamlandı. Müşterinin Logo/CRM veritabanlarının tamamının yedeği değildir.

## Gerçek kabul

Yerel test çalıştırılmadı. Test sunucusunda gerçek `/api/v1/ask` cevabının `resultId` ile saklanan tüm sonucu, aynı Logo/CRM kaynakları üzerinde yeni yazılmış bağımsız pyodbc hesaplarıyla karşılaştırıldı. Eski SQL, katalog ve üretim derleyicisi referansa aktarılmadı. CRM/T-soft'a yazılmadı.

İlk VPN kesintisinden sonra kullanıcı bağlantıyı geri açtı. Yeni motor `FINANCE_QUERY_MODE=contract` ile etkin. İlk denemelerde JSON biçimi ve denetleyicinin yanlış retleri düzeltildi. CRM metadata'sı, statecode=0 içinde “Pasif” statuscode kayıtlarının bulunduğunu kanıtladı; sayım tanımları gerçek durum etiketleriyle bağlandı. Aktif kitap 9.380, aktif yazar kişi 660, “Aktif Müşteri” 11.904; potansiyel/arşiv/sorunlu müşteri bu son tanıma dahil değil.

100 soruluk ilk tam tur 95 başarılı / 5 başarısızdı. FC03 “perakende satış tutarı” ifadesi iki hesabı ayırmıyordu: 227.547,69 TL KDV hariç satır toplamı ve 232.275,81 TL fatura toplamı. Kullanıcı iş tanımını seçene kadar soru netleştirilir; eski hata saklandı, beklenen sayı API'ye uydurulmadı. FC93–96'da dönem tutarları eşleşti fakat model gereksiz “ay” kolonu üretti. Açık iç-dönem kırılımı istenmeyen karşılaştırmada dönem başlangıç/bitiş anahtarları yeterlidir; plan düzeltildi.

Son kurulu arka uç **be31c7817**, arayüz **53e8e4e93**. Aynı arka uç kaynak hash'leri koşu öncesi/sonrası değişmedi; son arayüz akışı da aynı motor hash'iyle çalıştı. **102/102 PASS: 92 tam cevap + 10 doğru netleştirme/kapsam sınırı; FAIL 0, DOĞRULANAMADI 0.** Bu, bu tanımlı soru kümesinin kabulüdür.

- 92 sayısal cevap 92 farklı resultId ile üretildi. Tam sonuç kimliği, toplam satır sayısı, bütün kayıt/kolon/anahtar/değer/NULL/kesilme ve önizleme–tam sonuç eşliği kontrol edildi; uyuşmazlık 0.
- Önce sorun çıkaran dört dönem sorusu bir önceki hesap sürümünde üçer bağımsız kez, 12/12 geçti. Tarih/sıralama/denetçi yanlış retlerinin geçmişi silinmedi.
- Gerçek portalda 1.345 satır bağımsız Logo ile eşleşti; CSV tüm satırları içerdi. 320/390/768/1440 px sayfa taşması yok, tablo kendi içinde kayıyor, sayfa 2 ve CSV kontrol edildi. Netleştirme açıklaması görünür; veri okunmadığı durum sıfır sonuç diye gösterilmiyor.
- Son turda 1205 oluşmadı: **deadlock sonrası otomatik kurtarma dalı doğal hata üzerinde DOĞRULANAMADI**. Sınırlı tekrar kodu kurulu; geçerli normal okumalar gerçek veriyle geçti. Hata tetiklemek için yapay deadlock oluşturulmadı.
- Bu çalışmanın tüm kayıtlı koşularında **17 geçici timasai oturumu silindi**. Yeni kullanıcı oluşturulmadı; Yönetim → Kişiler'de kontrol edilen claude/test/deneme/codex adları yok. Gerçek timasai sorgu geçmişi korundu. CRM/T-soft kaynak yazması 0; yerel test yok.
- Git/kod/ayar/metadata yedekleri doğrulandı. İlgili 13 üretim dosyası test sunucusuyla SHA256 eş; Mac artığı 0.

Motor hash'i: `ccb307004d72568cdab66ec2304cc2ae60e691696827d00e188a668db9795b52`. Modelin bildirdiği ad `nanobaseAI`; ağırlık dosyası/model ailesi bu koşuda ayrıca doğrulanmadı.

Kanıt: [soru bazlı kabul ve koşu geçmişi](finance-acceptance-20260930.json), [kurulu dosya hash'leri](finance-deployment-hashes-20260930.json). Tam ham kayıtlar test sunucusunda `/data/nanobaseai/bi/acceptance/finance-contracts-20260930/release-102/`; son arayüz kanıtı `ui-release/`. Her soru dosyası bağımsız referans, gerçek API/tam sonuç ve plan izini taşır; özet JSON bu dosyaların SHA256 değerlerini içerir.

### Açık veritabanı teşhisi

30 Eylül 19:03:35'te uygulama ve hemen ardından bağımsız referans SQL Server **1205** ile kesildi. Sonraki okumalar doğru sonucu verdi. Yeni uygulama yalnız bu açık deadlock-kurbanı hatasında salt okunur SELECT'i kısa artan/rastgele beklemeyle toplam en fazla üç kez dener; bütün denemeler kayda geçer. Diğer hatalar veya tükenen deneme gizlenmez. [Microsoft'un 1205 açıklaması](https://learn.microsoft.com/en-us/sql/relational-databases/errors-events/mssqlserver-1205-database-engine-error).

Logo SQL sürümü 13.0.6300.2; READ_COMMITTED_SNAPSHOT kapalı, SNAPSHOT OFF. Bunlar tek başına deadlock nedenini kanıtlamaz. system_health deadlock grafiği okuması **297/yetki yok** ile reddedildi. Kilit döngüsündeki karşı işlem ve gereken indeks/sorgu/isolation değişikliği **DOĞRULANAMADI**. Sonraki somut adım: DBA'nın bu zaman aralığına ait xml_deadlock_report kaydını vermesi; veri ve sunucu ayarı bu oturumda değiştirilmedi.

## Sınırlar

Bu sınırlı sözleşme bütün finans sorularının veya muhasebe iş tanımlarının uzman kabulü değildir. Kâr/maliyet, kesin alacak yaşlandırması, bütçe/hedef, döviz dönüşümü, oran ve desteklenmeyen özel koşullar netleştirme döndürür. Tahsilat tanımı çek/senet teslimini de içerir; nakit tahsilat diye sunulmaz. Yazar kırılımı kitap künyesi metnidir, telif hak sahibi kimliği değildir. Bu oturum yalnız test sunucusunu kurup doğruladı. Paralel çalışmanın günlüğünde müşteri VM'ine tam main f9fc01aa kurulumu kaydedilmiş; bu son kabul sürümü değildir. Müşteride FINANCE_QUERY_MODE etkinliği bu oturumda doğrulanmadı; müşteri üretim kabulü iddia edilmez.

## Soru listesi ve son durum

| Kimlik | Soru | Kabul türü | Durum | Tam satır |
|---|---|---|---|---|
| FC01 | 29 Eylül 2026 tarihinde satılan kitap adedi kaçtır? | Tam cevap | PASS | 1 |
| FC02 | 29 Eylül 2026 tarihinde toptan satış faturası sayısı kaçtır? | Tam cevap | PASS | 1 |
| FC03 | 29 Eylül 2026 tarihinde perakende satış tutarı ne kadar? | Kapsam sınırı | PASS | — |
| FC04 | 29 Eylül 2026 tarihinde kanal bazında satılan kitap adedi kaçtır? | Tam cevap | PASS | 7 |
| FC05 | CRM’de aktif kitap kaydı sayısı kaçtır? | Tam cevap | PASS | 1 |
| FC06 | CRM’de aktif yazar kişi kaydı sayısı kaçtır? | Tam cevap | PASS | 1 |
| FC07 | CRM'de aktif cari kaydı sayısı kaçtır? | Tam cevap | PASS | 1 |
| FC08 | Eylül 2026 toptan satış fatura toplamı nedir? | Tam cevap | PASS | 1 |
| FC09 | Eylül 2026 perakende satış fatura toplamı nedir? | Tam cevap | PASS | 1 |
| FC10 | Eylül 2026 müşterilerden tahsilat toplamı nedir? | Tam cevap | PASS | 1 |
| FC11 | Eylül 2025 net satış tutarı toplamı nedir? | Tam cevap | PASS | 1 |
| FC12 | Eylül 2025 net satılan adet toplamı nedir? | Tam cevap | PASS | 1 |
| FC13 | Eylül 2025 iade tutarı toplamı nedir? | Tam cevap | PASS | 1 |
| FC14 | Eylül 2026 net satış tutarı toplamı nedir? | Tam cevap | PASS | 1 |
| FC15 | Eylül 2026 net satılan adet toplamı nedir? | Tam cevap | PASS | 1 |
| FC16 | Eylül 2026 iade tutarı toplamı nedir? | Tam cevap | PASS | 1 |
| FC17 | 1 Ocak 2027 tarihinde satılan kitap adedi nedir? | Kapsam sınırı | PASS | — |
| FC18 | 29 Eylül 2026 tarihinde kitap bazında satılan adet nedir? | Tam cevap | PASS | 1345 |
| FC19 | CRM'de pasif kitap kayıtlarını say. | Kapsam sınırı | PASS | — |
| FC20 | 2026 cirosunu dolara çevir. | Kapsam sınırı | PASS | — |
| FC21 | Vadesi geçmiş alacaklarımız kesin olarak ne kadar? | Kapsam sınırı | PASS | — |
| FC22 | 2026 satış hedefi ile gerçekleşen net satış tutarını kitap bazında karşılaştır. | Kapsam sınırı | PASS | — |
| FC23 | 29 Eylül 2026 satışlarını kitap, kanal, yazar ve yayınevi bazında adet ve KDV hariç satış tutarı olarak göster. | Tam cevap | PASS | 2109 |
| FC24 | 29 Eylül 2026 tarihinde toplam kaç satış faturası kesildi? | Tam cevap | PASS | 1 |
| FC25 | Eylül 2026 günlük net satış tutarı nedir? | Tam cevap | PASS | 30 |
| FC26 | 1 Ocak 2026 tarihinde perakende satış faturası sayısı kaçtır? | Tam cevap | PASS | 1 |
| FC27 | 15 Eylül 2026 tarihinde perakende satış faturası sayısı kaçtır? | Tam cevap | PASS | 1 |
| FC28 | 28 Eylül 2026 tarihinde perakende satış faturası sayısı kaçtır? | Tam cevap | PASS | 1 |
| FC29 | 30 Eylül 2026 tarihinde perakende satış faturası sayısı kaçtır? | Tam cevap | PASS | 1 |
| FC30 | 31 Aralık 2026 tarihinde perakende satış faturası sayısı kaçtır? | Tam cevap | PASS | 1 |
| FC31 | Ocak 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC32 | Şubat 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC33 | Mart 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC34 | Nisan 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC35 | Mayıs 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC36 | Haziran 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC37 | Temmuz 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC38 | Ağustos 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC39 | Eylül 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC40 | Ekim 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC41 | Kasım 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC42 | Aralık 2025 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC43 | Ocak 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC44 | Şubat 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC45 | Mart 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC46 | Nisan 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC47 | Mayıs 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC48 | Haziran 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC49 | Temmuz 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC50 | Ağustos 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC51 | Eylül 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC52 | Ekim 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC53 | Kasım 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC54 | Aralık 2026 net satış tutarı ve satılan kitap adedi toplamını ver. | Tam cevap | PASS | 1 |
| FC55 | Ocak 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC56 | Şubat 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC57 | Mart 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC58 | Nisan 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC59 | Mayıs 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC60 | Haziran 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC61 | Temmuz 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC62 | Ağustos 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC63 | Eylül 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC64 | Ekim 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC65 | Kasım 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC66 | Aralık 2026 toptan satış faturalarının sayısını ve fatura toplamını göster. | Tam cevap | PASS | 1 |
| FC67 | 20 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 2 |
| FC68 | 21 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 9 |
| FC69 | 22 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 9 |
| FC70 | 23 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 9 |
| FC71 | 24 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 11 |
| FC72 | 25 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 9 |
| FC73 | 26 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 9 |
| FC74 | 27 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 5 |
| FC75 | 28 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 9 |
| FC76 | 29 Eylül 2026 kanal bazında net satılan kitap adedi nedir? | Tam cevap | PASS | 7 |
| FC77 | 24 Eylül 2026 kitap ve kanal bazında satılan adet ile KDV hariç satış tutarını göster. | Tam cevap | PASS | 5150 |
| FC78 | 25 Eylül 2026 kitap ve kanal bazında satılan adet ile KDV hariç satış tutarını göster. | Tam cevap | PASS | 3647 |
| FC79 | 26 Eylül 2026 kitap ve kanal bazında satılan adet ile KDV hariç satış tutarını göster. | Tam cevap | PASS | 3065 |
| FC80 | 27 Eylül 2026 kitap ve kanal bazında satılan adet ile KDV hariç satış tutarını göster. | Tam cevap | PASS | 2974 |
| FC81 | 28 Eylül 2026 kitap ve kanal bazında satılan adet ile KDV hariç satış tutarını göster. | Tam cevap | PASS | 3132 |
| FC82 | 29 Eylül 2026 kitap ve kanal bazında satılan adet ile KDV hariç satış tutarını göster. | Tam cevap | PASS | 2109 |
| FC83 | 29 Eylül 2026 yalnız DAGITICI kanalındaki satılan kitap adedi toplamı nedir? | Tam cevap | PASS | 1 |
| FC84 | 29 Eylül 2026 yalnız DIGER kanalındaki satılan kitap adedi toplamı nedir? | Tam cevap | PASS | 1 |
| FC85 | 29 Eylül 2026 yalnız E-TICARET kanalındaki satılan kitap adedi toplamı nedir? | Tam cevap | PASS | 1 |
| FC86 | 29 Eylül 2026 yalnız KITAPCI kanalındaki satılan kitap adedi toplamı nedir? | Tam cevap | PASS | 1 |
| FC87 | 29 Eylül 2026 yalnız KURUM kanalındaki satılan kitap adedi toplamı nedir? | Tam cevap | PASS | 1 |
| FC88 | 29 Eylül 2026 yalnız ZINCIR kanalındaki satılan kitap adedi toplamı nedir? | Tam cevap | PASS | 1 |
| FC89 | 26 Eylül 2026 en çok satılan ilk 10 kitabı adetleriyle göster. | Tam cevap | PASS | 10 |
| FC90 | 27 Eylül 2026 en çok satılan ilk 10 kitabı adetleriyle göster. | Tam cevap | PASS | 10 |
| FC91 | 28 Eylül 2026 en çok satılan ilk 10 kitabı adetleriyle göster. | Tam cevap | PASS | 10 |
| FC92 | 29 Eylül 2026 en çok satılan ilk 10 kitabı adetleriyle göster. | Tam cevap | PASS | 10 |
| FC93 | Mart 2025 ve Mart 2026 net satış tutarlarını dönem dönem göster. | Tam cevap | PASS | 2 |
| FC94 | Haziran 2025 ve Haziran 2026 net satış tutarlarını dönem dönem göster. | Tam cevap | PASS | 2 |
| FC95 | Ağustos 2025 ve Ağustos 2026 net satış tutarlarını dönem dönem göster. | Tam cevap | PASS | 2 |
| FC96 | Eylül 2025 ve Eylül 2026 net satış tutarlarını dönem dönem göster. | Tam cevap | PASS | 2 |
| FC97 | Eylül 2026 net satış tutarı 100 bin TL'den büyük kitapları listele. | Kapsam sınırı | PASS | — |
| FC98 | 2026 net satış büyüme yüzdesini hesapla. | Kapsam sınırı | PASS | — |
| FC99 | Eylül 2026 yalnız nakit tahsilat toplamını ver. | Kapsam sınırı | PASS | — |
| FC100 | 2026 brüt kâr tutarı nedir? | Kapsam sınırı | PASS | — |
| FC101 | 29 Eylül 2026 tarihinde perakende satış faturalarının genel toplamı ne kadar? | Tam cevap | PASS | 1 |
| FC102 | 29 Eylül 2026 tarihinde perakende satışın KDV hariç satır toplamı ne kadar? | Tam cevap | PASS | 1 |
