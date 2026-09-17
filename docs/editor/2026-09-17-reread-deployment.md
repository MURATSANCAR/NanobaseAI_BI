# Otomatik bölgesel okuma: müşteri kurulumu ve yedek sınırı

17 Eylül 2026. Bu kayıt kod değişikliğidir; yeni offline paket / restore kabulü değildir.

## Bulunan eksikler ve düzeltmeler

V10 kaynak hattı yeniden okuma kuyruğuna bağımlı olmasına rağmen eski paketleyici yalnız
temel, model ve OCR profillerini topluyordu. Bu, müşteri kurulumunda tüketicinin eksik
kalmasına neden olabilirdi. `scripts/bundle.py`, kaynak ağacında `reread_queue.py`
bulunduğunda `compose.reread.yaml` profilini ve tüketici/izin hazırlama imajlarını
otomatik dahil eder. `--with-reread` açık seçeneği de vardır. Paketlenen gerçek API, işçi ve belge
imajlarında tüketici modülü içe aktarılamıyorsa veya helper SHA değerleri paketlenen
kaynakla eşleşmiyorsa paketleme başarısız olur. Müşteride indirme
yapılmaz; servisler diğer imajlar gibi içerik kimliğiyle offline etiketlenir.

`scripts/preflight.py`, bu kaynak ağacında yeniden okuma servisleri veya işçinin yazılabilir
kuyruk mount'u yoksa kurulum öncesinde açık hata üretir. Kuyruğun kurulmamış olması
kitap analizi başladıktan sonra anlaşılmamalıdır.

`scripts/backup.py` daha önce API, analiz işçisi ve ayrıştırıcıyı durduruyordu. Yeni
tüketici de artifact yazarı olduğu için yedek öncesinde durdurulan servislere eklendi.
Yalnız yedekten önce çalışan servisler yeniden başlatılır; bilerek durdurulmuş analiz
işçisi yedek işlemi nedeniyle açılmaz. Durdurma adımı kısmen başarısız olsa da
yeniden başlatma `finally` koruması çalışır. Kaynak, kırpım, ham TSV ve tamamlanmış ölçüm
raporları mevcut artifact yedeğinin içindedir. Geçici kuyruk volume'u yedek kapsamına
eklenmedi; tamamlanmış rapordan pointer toparlanması ve yeni lease ile yeniden istek
oluşturma kodu ayrı kabul gerektirir.

## Kabul durumu

- Yerel test çalıştırılmadı.
- V10-r2 gerçek kitap otomatik okuma ve lease toparlanma kabulü ayrı ortamda yürütülüyor.
- Bu paketleme/yedek değişikliklerinin dolu gerçek kitapla yeni offline kurulum,
  yedek ve restore kabulü **DOĞRULANAMADI**; önceki V4/V5 sonuçları bu koda taşınmaz.
- Ana V5 kurulumu bu değişikliklerle güncellenmedi. V8/V9 analizi ayrı kabul ortamındadır.
