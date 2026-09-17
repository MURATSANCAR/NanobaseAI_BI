# Sistem düzeltmesi ve gerçek koşu denetimi

## 17 Eylül güncellemesi

48/48 sayfa işlendi; 1.149 kaynak bölgesinin 778’inde okuyucular anlaştı, 371 bölge incelemede. İş `COMPLETED`, nesil `NEEDS_REVIEW`; anlamsal kabul verilmedi. Gerçek API/PG eşliği, offline paket, ayrı kuruluma yedekten dönüş ve restore sonrası dört genişlikte mobil kontrol geçti.

Bekleyen denetçi tamamlandı: restore 01:54:29 UTC, hedef API/PG 01:55:48, mobil kontrol 01:56:09. Ayrı hedef 01:56:12’de durduruldu; kanıt ve volume’lar korundu. Aşağıdaki bekleme kayıtları 16 Eylül anlık durumudur.

[Ayrıntılı güncel durum, sürümler ve kanıtlar](2026-09-17-status-and-handoff.md).

## 16 Eylül tarihsel kayıtları

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

## Canlı dağıtım

- Commit: `6f14bb9` (yerel main). GitHub push, oturumda HTTPS kullanıcı kimliği
  bulunmadığı için başarısız; origin güncelmiş gibi raporlanmaz.
- API/worker imajı: `sha256:67226135f7620aa2cdd1639543700ff3dfcc42beab8248d38c490caf514e71b2`.
- Backend ağaç hash: `58004e5a5043d27508c12aa370ef81d92d97d08778abf2c7cc1b9b5a934fe2ef`;
  dağıtılan 26 dosya repo ile eşleşti. 10 servis için izolasyon kontrolü geçti.
- V1 API iptali `CANCELLED` oldu; 18 OCR/görsel ve 17 aday/kontrol sayfası korundu.
- V2 nesli `a9471749-7447-4826-b003-f25e53943763`, iş
  `0d53b03d-67e5-44c4-b523-bf9a2aa56ac2`; 20:04 UTC'de kuyruğa alındı.
- Yeni API ile gerçek Chrome 320/390/768/1440 px kontrolü geçti. Bu ilk sayfa
  görünümü ve mobil akış kabulüdür; bütün kitabın anlamsal kabulü değildir.
- Belge aracı da güncel backend ile ayrı imajda derlendi. Paketleme kodu
  `node_modules`, `.git` ve `.env.example` dışındaki `.env*` dosyalarını dışlar;
  dağıtım kimliği `.env.example` içine gerçek release olarak yazılır.
- Koşu sonrası ayrı kurulumda gerçek yedek/restore ve offline paket sınaması için
  tek seferlik betik hazırlandı. Henüz gerçekleşmeyen adımlar başarı sayılmaz.

## V2 üzerinde ek gerçek kontroller

- İlk sayfanın altı kayıt türü, ikinci sayfanın kaynak/yerleşim/okuma kayıtları
  gerçek API ve bağımsız PostgreSQL arasında eşleşti. S.1 anlaşan 1/9, s.2 23/33;
  kalanlar incelemede. Elle review ve kaynak düzeltmesi sıfır.
- Gerçek API'de yetkisiz okuma 401; doğrulanmamış nesle preview/published soru
  ve activate girişimleri 409 verdi. Bağımsız DB önce/sonra karşılaştırmasında
  soru işi veya editör kararı oluşmadı. Kanıt: `evidence/publication-gates.json`.
- S.38 ayrı ve sınırlı gerçek OCR servis kontrolü: API kaynağı PG ile eşleşti,
  2400px render hash'i doğrulandı. Yeni kelime eşleştirmesinde 24 bölgenin 20'si
  anlaşmalı; olumsuzluk içeren bölge korundu. OCR 33,016 saniye. Bu ayrı kontrol
  ana akışın s.38'e ulaştığı veya konuşmacı/semantiğin doğrulandığı anlamına gelmez.
  Beklenen cevap sağlanmadı, uygulama kaydı yazılmadı. Kanıt:
  `evidence/source-alignment-page-0038-a9471749-7447-4826-b003-f25e53943763.json`.
- Kurulum denetçisi ilk başlangıçta üst klasör yazma izni nedeniyle çıkmıştı.
  Yalnız ayrı denetim kökü `/data/nanobaseai/editor-qualifications` operatör
  sahipliğinde 0700 oluşturuldu; kaynak kurulumun izinleri/verileri değiştirilmedi.
  Yeniden başlatılan denetçi release eşliğini geçti ve paket üretimine başladı.
  Süreç `evidence/installation-qualification-status.md` ve `.log` dosyalarına yazar.
- Offline paket **üretildi ve import kontrolünden geçti** (20:19:50 UTC): 8 imaj,
  94 dosya, OCR imajı ve dört GGUF ağırlığı. Dosya hashleri ve yüklenen imaj ID'leri
  doğrulandı. Paket: `/data/nanobaseai/editor-qualifications/a9471749/offline`.
  Kitap/secret/evidence/node_modules pakete alınmadı. Bu sonuç müşteri restore
  veya kitap analizi kabulü değildir.
- Denetçi şu anda belirli v2 işinin tamamlanmasını bekliyor. Ardından aktif başka
  iş olmadığını kontrol ederek yedek alacak; ayrı `editor-qualification-a9471749`
  projesinde 18810/19096 portları, 10.203.50/51 ağları, yeni sırlar ve ayrı volume'larla
  geri yükleyecek. Hedef API/PG ve dört genişlikli tarayıcı kontrolleri tamamlanınca
  yalnız hedef servisler durdurulacak; kanıt ve volume'lar korunacak. Bir hata veya
  kaynak sürümü değişiminde başarısızlığı kaydedip durur; doğru kitap cevabı üretmez.

## Açık kabul işleri

Konuşmacının figür/kuyruk/isimle bağlanması, iddianın anlamsal desteği, sahneler
arası karakter belleği, kaynaklı kitap sentezi, indeks ve tam soru-cevap kabulü
tamamlanmış değildir. `NEEDS_REVIEW` bir başarı etiketi değildir. Özellikle
PDF 6, 29, 38; zarfın kişi sayılması ve etkinliğin olay sayılması yeni sürümün
gerçek çıktılarıyla değerlendirilmelidir. Diğer iki kitap, ikinci baskı ve insan
editör emeği ölçümü elde yoktur; tahminle doldurulmaz.
