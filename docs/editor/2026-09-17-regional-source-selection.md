# Bölgesel OCR kaynak seçimi — v6, kabul sürüyor

## Kök hata ve genel çözüm

Tam sayfa Paddle okuması hatalıyken, aynı kutunun bölgesel okuması bağımsız Tesseract veya kullanılabilir PDF metniyle uyuşsa bile önceki kapı tam sayfa metnini zorunlu otorite sayıyordu. `optical_selection.py` ve `source_pipeline.py` entegrasyonu bölgesel ham metni kaynak adayı olarak seçer: bölge skoru en az 0,9; en az bir bağımsız okuyucuyla tam kelime eşliği; mevcut bağımsız okuyucu veya kararlı yeniden okumayla çelişki olmaması gerekir. Boşluklar birleştirilmez; olumsuzluk harfleri korunur. Aynı Paddle modelinin tam sayfa/kırpım okumaları iki bağımsız oy sayılmaz.

Yalnız önceden NEEDS_REVIEW olan destekli bölge yükseltilir. `raw_text` tam sayfa ham okuması olarak kalır; `text` sistemin seçtiği bölge metni olabilir. `selected_reader`, bütün okur hashleri, skor ve karar gerekçesi saklanır. Yeni nesil oluşturulur; eski kaynak ve inceleme kayıtları değiştirilmez. Değişen metin veya yükselen güven, eski model adayının yeniden kullanımını engeller; taze çıkarım gerekir. Bu, OCR uyumu dışında anlamsal kabul vermez.

## Gerçek ölçüm

Sunucu ana gerçek API/PG, ebeveyn nesil `99881d8f`, 1.149 kaynak: bağımsız karşılaştırma 39 yükselme adayı / 0 gerileme, potansiyel 860 anlaşma / 289 inceleme. Kaynak kayıtlarının önce/sonra hashleri aynı. Aday SHA `059d94524056918544468c7717b9d025da9ddfd439bb1b1d56a0d0dcd8675031`. Kanıt `/data/nanobaseai/editor/evidence/optical-selection-candidate-20260917T133513249899Z.json`. Bu ölçüm üretimde 39 bölgenin tamamlandığı anlamına gelmez.

## Gerçek akış ve bulunan işletim hatası

Ayrı gerçek restore ortamı API18810, `regional-source-v6-20260917`, ilk nesil `7f966cbb-daac-4178-b736-6137cea447d8`. İlk iki sayfa / 42 kaynağın API-PG-ebeveyn ham metin/kutu/okur kökeni eşliği geçti; ikinci sayfada iki yükselme, sıfır gerileme. Fakat model servisi açılışı sırasında iş `HTTPStatusError` ile FAILED oldu. Doğrulayıcı bunu `PARTIAL_VERIFIED` / `end_to_end_job_success=false` olarak kaydeder; başarı gibi göstermez. Kanıt `evidence/regional-source-partial-verification.log`.

`analysis.model` geçici 429/503 ve bağlantı kurulamadı durumunda toplam sınırlı gecikmeli tekrar yapar; tekrarlar metriklerde saklanır. Diğer HTTP hataları durum koduyla görünürdür. Okuma zaman aşımı tekrar edilmez; sunucuda devam eden üretimi kopyalayacak ikinci çağrı başlatılmaz. Yeni kod `regional-source-v6-r2-20260917` olarak gerçek soğuk başlangıçta yeniden sınanıyor; ilk başarısız nesil korunur. Ayrı ortam model sınırı 4 yerine 48 CPU/thread oldu; ana modelin ikinci ağır analiz kopyası başlatılmadı.

## Durum ve açık kabul

V6 ana kurulumda değildir. Ayrı ortamın R2 nesli `evidence/regional-source-run.json` dosyasında; gerçek kaynak ve model akışı izleniyor. Ham kaynaklar/inceleme kararları elle düzeltilmedi. Tam 48 sayfa, yeni adaylar, kaynak seçim ekranı ve taze model çağrıları kabulü tamamlanmadan v6 üretime hazır sayılmaz. Diğer kitaplar, görsel kimlik, bütün-kitap sentezi ve P0–P7'nin kalan maddeleri açık.
