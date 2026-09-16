# Sistem düzeltmesi ve gerçek koşu denetimi

Kullanıcı bilgisayar başında değilken mevcut koşuyu izleme, uçtan uca kontrol,
hata/eksikleri kod üzerinden giderme ve yapılanları Markdown'a kaydetme talebi.
Kitap içeriği, beklenen cevap, konuşmacı veya kabul kararı elle yazılmaz.
Genel kod değişir; sonuçları gerçek sunucudaki uygulama üretir.

## Başlangıçta doğrulanan durum

Sunucu `/data/nanobaseai/editor`, gerçek API `http://127.0.0.1:8810/v1`,
Editor PostgreSQL ve aynı özgün 48 sayfalık PDF kullanıldı. Yerel test yok.
`7a19f9eb-7e3e-40d0-822b-ac5e557960b4` nesli ilk kontrolde 17 OCR / 16 sayfa
kontrol kaydıyla çalışıyordu; sonraki salt okunur karşılaştırma ilk 18 sayfayı kapsadı.
Eski serbest görsel açıklama, elle kaynak düzeltmesi ve review kaydı bu nesilde yok.
Bu sayılar anlamsal kalite veya üretim kabulü değildir.

## Bulunan ve kodda ele alınan hatalar

1. **Kelime kutusu bütün satırla karşılaştırılıyordu.** Paddle tek kelimelik
   bölge verdiğinde PDF/Tesseract'ın tamamı seçiliyordu. `source_alignment.py`
   artık yalnız konumca karşılık gelen kelimeleri seçer; metin benzerliğine göre
   sayfanın başka yerinden cevap aramaz. Ham okuyucu metinleri değişmez.
2. **Alıntı harf alt dizisi ve eksik bölge üzerinden geçebiliyordu.** Yeni kapı
   kelime sınırlarını, yinelenen referansı, kaynak sırasını ve aradaki eksik
   bölgeyi kontrol eder. Okunması uyuşmayan yerler modele açık boşluk olarak gider;
   kalan kelimeler eksiksiz bir cümleymiş gibi sunulmaz.
3. **Dedektör sırası okuma sırası değildi.** Aynı satırın kelimeleri geometrik
   satır gruplamasıyla soldan sağa dizilir. Çok sütunlu anlatı sırası ayrıca
   doğrulanmış sayılmaz.
4. **Takip yalnız ilerleme yazıyordu.** Gözlemciye tarihli Markdown durum dosyası,
   her 10 sayfada ve terminal durumda gerçek API/PG denetimi eklendi.
   Kaynak/karar yazmaz; otomatik kabul veya yayın yapmaz.

Yeni türetim sürümü `source-spans-v2`. Önceki tamamlanmış ham OCR ölçümleri ve
doğrulanmamış görsel adayları aynı kaynak hashleri ve açık parent kimlikleriyle
yeniden kullanılabilir. Alıntı/iddia/kabul kararları taşınmaz. Bu yeniden kullanım
yeni OCR/VLM çağrısı diye sayılmaz; ham metin, kutu, skor ve eski ölçüm provenance'ı
korunur. Kaynak durumları ve aday iddialar yeni nesilde uygulama tarafından hesaplanır.

## Gerçek veriyle elde edilen kanıt

- `verify-source-pipeline.py`: ilk 17 sayfanın kaynak API/PG tam değer eşliği geçti.
  Denetim, tamamlanmış sayfalarda görsel/iddia/kontrol kayıtlarına da genişletildi.
- `verify-source-alignment.py`: gerçek API kayıtları bağımsız PG ile eşleştirildi,
  PDF konum artifact hashleri doğrulandı. İlk 18 sayfalık karşılaştırmada s.16
  okuyucu anlaşması **1/56 → 46/56** oldu; kalan 10 bölge kabul edilmedi.
  Bu anlaşma oranıdır, karakter/tema veya bütün sayfa doğruluk oranı değildir.
- Yeni Docker imajıyla `verify-source-gates.py` gerçek PostgreSQL kayıtlarını
  salt okunur tekrar işledi: 18 sayfanın ham metin/kutu/skorları aynen korundu.
  46 eski aday alıntının 31'i yeni alıntı kapısından geçti, 4'ü kesintili/sırasız
  kaynak, 11'i alıntı uyuşmazlığı nedeniyle geçmedi. Semantik kabul verilmedi.
- Özel kanıtlar sunucuda `evidence/source-alignment-comparison.json`,
  `evidence/source-gates-v2-replay.json`, `evidence/source-spans-verification.json`.
  Kitap metni içeren dosyalar depoya eklenmez.

## GitHub önerilerinin inceleme sonucu

- [BooookScore](https://github.com/lilakk/BooookScore): hiyerarşik/artımlı özet
  yöntemleri referans; OCR/konuşmacı doğrulamasının yerine geçmez.
- [FABLES](https://github.com/mungg/FABLES): kanıtlı atomik iddia değerlendirme
  veri seti; hazır otomatik doğruluk motoru değildir. Çalışma LLM hakemlerinin
  özellikle yanlış iddialarda sınırlı kaldığını bildirir.
- [AI-Reader-V2](https://github.com/mouseart2025/AI-Reader-V2): kaynak span'ı,
  kimlik/takma ad belleği ve bağımsız ikinci okuma incelenmeye değer. Geliştiricinin
  kalite uyarısı vardır; Türkçe resimli kitabın kabulü gösterilmemiştir.
- [screenplay-analyzer](https://github.com/ops120/ai-novel-screenplay-analyzer):
  ilişki evrimi yaklaşımı yararlı. Balon konuşmacısını hazır çözmez.
- [NovelSummaryAssistant](https://github.com/Ice-wilderness/NovelSummaryAssistant):
  karakter ve olay örgüsünü ayrı özetleme yararlı; dört kademe her kısa kitaba zorlanmaz.
- [NovelIQ](https://github.com/famameilin/NovelIQ): LDA/ölçüm ve kaynak erişimi
  yaklaşımı mevcut. Sözcük kümesi edebî temanın kanıtı sayılmaz.
- BookNLP İngilizce öğrenilmiş modeller kullanır; deterministik/hatasız kabul edilmez.
  Diğer listedeki projeler için üretim veya Türkçe kalite kabulü yapılmadı.

Repo incelemesi kurulmuş/ürüne uygulanmış özellik sayılmaz. Yeni genel VLM,
ikinci büyük model veya yeni vektör veritabanı eklenmedi.

## Açık kabul işleri

Konuşmacının figür/kuyruk/isimle bağlanması, iddianın anlamsal desteği, sahneler
arası karakter belleği, kaynaklı kitap sentezi, indeks ve tam soru-cevap kabulü
tamamlanmış değildir. `NEEDS_REVIEW` bir başarı etiketi değildir. Özellikle
PDF 6, 29, 38; zarfın kişi sayılması ve etkinliğin olay sayılması yeni sürümün
gerçek çıktılarıyla değerlendirilmelidir. Diğer iki kitap, ikinci baskı ve insan
editör emeği ölçümü elde yoktur; tahminle doldurulmaz.
