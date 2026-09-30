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

## Yedek

- Git geçmişi: `/Users/msancar/.codex/backups/nonobase-finance-20260930/repository.bundle`, `git bundle verify` başarılı.
- Test sunucusu: `/data/nanobaseai/bi/backups/finance-contracts-20260930/`; metadata DB, kod, gerçek sunulan arayüz, servis/ortam ayarları ve hash manifesti.
- PostgreSQL dökümü 13.119.667.444 bayt. Bütün arşivlerin hash/okuma denetimi ve `pg_restore --file=/dev/null` tamamlandı. Müşterinin Logo/CRM veritabanlarının tamamının yedeği değildir.

## Gerçek kabul

Yerel test çalıştırılmadı. Test sunucusunda gerçek `/api/v1/ask` cevabının `resultId` ile saklanan tüm sonucu, aynı Logo/CRM kaynakları üzerinde yeni yazılmış bağımsız pyodbc hesaplarıyla karşılaştırıldı. Eski SQL, katalog ve üretim derleyicisi referansa aktarılmadı. CRM/T-soft'a yazılmadı.

İlk VPN kesintisinden sonra kullanıcı bağlantıyı geri açtı. Yeni motor `FINANCE_QUERY_MODE=contract` ile etkin. İlk denemelerde JSON biçimi ve denetleyicinin yanlış retleri düzeltildi. CRM metadata'sı, statecode=0 içinde “Pasif” statuscode kayıtlarının bulunduğunu kanıtladı; sayım tanımları gerçek durum etiketleriyle bağlandı. Aktif kitap 9.380, aktif yazar kişi 660, “Aktif Müşteri” 11.904; potansiyel/arşiv/sorunlu müşteri bu son tanıma dahil değil.

100 soruluk ilk tam tur 95 başarılı / 5 başarısızdı. FC03 “perakende satış tutarı” ifadesi iki hesabı ayırmıyordu: 227.547,69 TL KDV hariç satır toplamı ve 232.275,81 TL fatura toplamı. Kullanıcı iş tanımını seçene kadar soru netleştirilir; eski hata saklandı, beklenen sayı API'ye uydurulmadı. FC93–96'da dönem tutarları eşleşti fakat model gereksiz “ay” kolonu üretti. Açık iç-dönem kırılımı istenmeyen karşılaştırmada dönem başlangıç/bitiş anahtarları yeterlidir; plan düzeltildi.

Son sürüm (`21551baad`) için 102 soru: 92 tam cevap + 10 kapsam sınırı. **Koşu sürüyor; nihai sayı henüz verilmedi.** Önceki sürüm geçişleri bu sürüme aktarılmaz. Soru bazında kaynak, bağımsız SQL, tüm sonuç, plan, model adı, sözleşme/kod hash'i ve hata raporu sunucuda `/tmp/claude-finance-contracts-20260930/final-102/` altında.

Gerçek portal tam sonuç/CSV kabulü geçti: 1.345 satırın tümü bağımsız Logo ile eşleşti, 50 satır önizleme sınırı dışa aktarıma taşınmadı. 320/390/768/1440 px: sayfa taşması yok, tablo kendi içinde kayar; sayfa 2 ve bütün CSV kontrol edildi. Kanıt `ui-1/report.json`, dört ekran görüntüsü, API cevabı/tam sonuç/CSV. Bu koşunun 1 geçici timasai oturumu silindi.

## Sınırlar

Bu sınırlı sözleşme bütün finans sorularının veya muhasebe iş tanımlarının uzman kabulü değildir. Kâr/maliyet, kesin alacak yaşlandırması, bütçe/hedef, döviz dönüşümü, oran ve desteklenmeyen özel koşullar netleştirme döndürür. Tahsilat tanımı çek/senet teslimini de içerir; nakit tahsilat diye sunulmaz. Yazar kırılımı kitap künyesi metnidir, telif hak sahibi kimliği değildir. Müşteri VM'ine bu değişiklik kurulmadı.
