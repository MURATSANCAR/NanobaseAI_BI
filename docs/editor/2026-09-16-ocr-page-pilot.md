# Gerçek sayfada ikinci okuyucu pilotu

## 17 Eylül güncellemesi

48/48 sayfa işlendi; 1.149 kaynak bölgesinin 778’inde okuyucular anlaştı, 371 bölge incelemede. İş `COMPLETED`, nesil `NEEDS_REVIEW`; anlamsal kabul verilmedi. Gerçek API/PG eşliği, offline paket, ayrı kuruluma yedekten dönüş ve restore sonrası dört genişlikte mobil kontrol geçti.

Pilot ana sisteme source-spans-v2 ile bağlandı. PDF/Tesseract karşılaştırması artık kelime geometrisiyle yapılır; tam koşunun s.38 kaydı 24 bölge/20 anlaşma/4 incelemedir. Eski pilot imajı güncel dağıtım imajı değildir.

[Ayrıntılı güncel durum, sürümler ve kanıtlar](2026-09-17-status-and-handoff.md).

## 16 Eylül tarihsel kayıtları

Kullanıcının talebiyle PaddleOCR 3.2.0 / PaddlePaddle 3.2.0, PP-OCRv5 mobile detection ve Türkçe Latin recognition modelleri ayrı Docker servisi olarak kuruldu. Model revision ve taban imaj digestleri sabit; bütün ağırlıklar imaj içinde. Özel ağ, dışarı açılan port yok, 4 CPU/4 GiB, salt okunur dosya sistemi. Dış TCP erişimi engelli olduğu canlı konteynerde doğrulandı. İmaj: `sha256:5ee7b3015cf37db8dcdd7da19010ca6fb7bb9b970c1a696c17516be1554aa75c`.

## Yürütme ve kanıt

- Ortam: uzak `nanobase-direct`, `/data/nanobaseai/editor`; gerçek Editor API `http://127.0.0.1:8810`, gerçek PostgreSQL ve kullanıcının PDF kaynağı.
- Nesil: `6fffd7ed-f0c6-4de5-af1b-1ebea8898c8b`, PDF 38.
- Kaynak SHA-256: `94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50`.
- Sayfa API kaydı bağımsız PostgreSQL kaydıyla birebir eşleşti. 1600 px API görüntüsü ve Tesseract'ın 2400 px görüntüsü kendi kayıtlı hashleriyle eşleşti.
- İki görüntü ayrı işlendi; otomatik bulunan metin bölgeleri büyütülüp doğrudan satır okuyucusuna verildi. Beklenen cevap, elle düzeltme veya inceleme kararı modele verilmedi. Uygulama kayıtlarına yazma yok.
- Özel kanıt: `evidence/ocr-page-0038-6fffd7ed-f0c6-4de5-af1b-1ebea8898c8b.json`; ilk başarısız servis yaklaşımı `evidence/ocr-page-0038-initial-health-blocking.json` içinde korundu. Kitap içeriği depoya eklenmedi.

## Sonuç

| Kontrol | Gerçek sonuç |
|---|---|
| Kritik anlamı tersine çeviren kelime | PaddleOCR'ın her iki çözünürlükteki ilk ve bölgesel okumasında olumsuzluk korundu. Mevcut Tesseract da bu kelimeyi doğru okuyordu; hata eski görsel model betimlemesindeydi. |
| Sayfa numarası | Yeni OCR doğru okudu; eski görsel aday yanlış numara veriyordu. |
| Eski görsel adayın yanlış alıntısı | Genel metin eşleştirme kapısı `BLOCKED_QUOTE_MISMATCH` döndürdü; beklenen cevaba göre yazılmış koşul yok. |
| Süre | 1600 px: 30,353 s; 2400 px: 31,610 s. Her süre ilk okuma ve 24 bölgenin yeniden okumasını içerir; toplam API/DB aktarım süresi değildir. |
| Kalan uyuşmazlıklar | Her iki görüntüde 24 bölgenin 4'ü `NEEDS_REVIEW`; harf/noktalama ve fazladan alıntı işareti algılama hataları mevcut. 20 anlaşma, 20 doğru okuma garantisi değildir. |
| Okuma sürerken sağlık | 15/15 HTTP 200; en yüksek örnek 126 ms. Genel SLO kabulü değildir. |

İlk denemede kırpılmış satırın yeniden yerleşim algılamasına gönderilmesi kelime sırasını bozdu; doğrudan satır tanıma ile bu yöntem düzeltildi. Seri HTTP sunucusu uzun OCR sırasında sağlık yanıtını geciktirdi; sağlık ayrı iş parçacığına alındı, OCR tek eşzamanlı çağrıyla sınırlandı. Yukarıdaki sonuçlar bu düzeltmelerin bulunduğu son imaja aittir.

## Kapsam sınırı

Ayrı 1024 görsel token denemesi de tamamlandı. PDF 29'da balon sahibi ve ışık kaynağı önceki yanlışlardan düzeldi (620,968 s); PDF 38'de yanlış alıntı tekrarlanmadı ve sayfa numarası düzeldi (499,870 s), fakat alt simge yine yanlış adlandırıldı. PDF 38 çıktısı kritik cümleyi aynen aktarmadığı için bu deneme olumsuzluğun doğru transkripsiyonu kanıtı değildir. İki çağrının istek gövdeleri kendi 256-token eski çağrılarıyla hash düzeyinde aynıydı; model/istem/kaynak aynı, görsel bütçe farklıydı. CPU/slot ayarları farklı olduğundan süreler kontrollü performans karşılaştırması sayılmaz. Geçici model konteyneri işlem sonunda kaldırıldı. Sonuç: görsel bütçe artışı yardımcı, tek başına yeterli değil.

İkinci okuyucu ve alıntı kapısı gerçek tek sayfada kalibre edildi. Devam eden kitap analizine otomatik bağlanmadı; yeni çıktı eski neslin içine karıştırılmadı. Kapı yalnız açık alıntının OCR metniyle uyuşmasını denetler; konuşmacı, olay, çizim veya bütün kitabın anlamsal doğruluğunu doğrulamaz. Tam kitap yeniden kabulü, daha geniş model karşılaştırması ve yeni offline paketin başka ortama restore kabulü bekliyor. `bundle.py --with-ocr` paketleme seçeneği eklendi; bu turda tam paket export/import koşulmadı.

Ana müdahalesiz koşunun eşzamanlı bütünlük kontrolünde 48 kaynak, 48 görsel, 8 sahne API/DB eşleşti; sıfır review ve sıfır kaynak düzeltmesi vardı. Bu kontrol içerik doğruluğu anlamına gelmez.
