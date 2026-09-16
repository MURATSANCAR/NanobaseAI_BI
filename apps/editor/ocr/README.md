# İkinci OCR okuyucusu

PaddleOCR 3.2.0 / PaddlePaddle 3.2.0, PP-OCRv5 mobile detection ve Türkçe destekli Latin recognition modeli. Kaynak metni, güven skoru ve piksel koordinatlarını döndürür; yorum, olay veya konuşmacı üretmez. `regional_pass` otomatik saptanan ilk 128 metin bölgesini iki kat büyütüp doğrudan satır tanıma modeliyle yeniden okur; kırpılmış satırda tekrar yerleşim algılaması yapılmaz. Okumalar farklıysa `NEEDS_REVIEW`; aynıysa yalnız `CONSISTENT_CANDIDATE` olur. Aynı modelin iki okumada anlaşması doğruluk kanıtı değildir. Bölge sınırı aşılırsa `regional_truncated` açıkça döner.

Servis dört CPU, 4 GiB, salt okunur dosya sistemi ve yalnız özel Docker ağıyla çalışır. Ana makineye port açmaz. Model indirme yalnız imaj hazırlanırken yapılır; çalışma sırasında model dosyaları yereldir. `/opt/models/manifest.json` model revision ve dosya SHA-256 değerlerini, `/opt/python-lock.txt` kurulan bağımlılıkları içerir. Dağıtım aynı içerik kimlikli imajla yapılmalıdır.

Sunucuda hazırlama:

```sh
docker compose build ocr
docker compose up -d --no-deps --no-build --pull never ocr
```

OCR ana compose.yaml içinde zorunlu servistir; compose.ocr.yaml eski komutlar için boş uyumluluk dosyasıdır. Mevcut modeller kullanılıyorsa `compose.models.yaml` korunur. Müşteride derleme yerine `scripts/bundle.py DESTINATION --with-models` ile hazırlanmış offline paket kullanılır; model ağırlıkları OCR imajının içindedir. Tek sayfa denemesi, bütün müşteri paketinin restore kabulü değildir.

Gerçek kayıt üzerinden salt okunur karşılaştırma (yalnız dağıtım sunucusunda):

```sh
python3 scripts/probe-page-ocr.py GENERATION_UUID PDF_PAGE
```

Betik özgün sayfayı yetkili Editor API’sinden alır; API kaydı ile bağımsız PostgreSQL kaydını ve görüntü hashlerini karşılaştırır. 1600 px kaynak ile Tesseract’ın kullandığı 2400 px kaynağı ayrı işler. Özgün Tesseract, görsel model ve PaddleOCR sonuçları özel `evidence/` dosyasına yazılır. `reading_quality.py`, görsel betimlemedeki açık alıntıları OCR metinleriyle karşılaştırır; harf biçimi/noktalama normalleştirilir, olumsuzluk eki korunur. Hiçbir okuyucuda bulunmayan alıntı `BLOCKED_QUOTE_MISMATCH` olur. Bu dar kontrol konuşmacı/olay/anlam doğrulaması değildir ve sonuçları doğrulanmış bilgiye yükseltmez. Beklenen cevap verilmez, analiz/review/düzeltme kaydı değiştirilmez. Yeni source-spans-v1 analizinde OCR, konumlu metin kaydının ana bileşenidir; serbest görsel betimleme iddia girdisi değildir. Eski nesiller değişmez.

Özel API: `GET /health`, `POST /ocr` JSON `{ "image_base64": "...", "regional_pass": true }`. Görüntü 16 MiB istek ve 20 milyon piksel ile sınırlıdır; tek OCR çağrısı işlenir, eşzamanlı OCR çağrısı 429 döner. Sağlık kontrolü ayrı iş parçacığında yanıtlanır. Dış erişim gerekiyorsa operatör API’sinin kimlik doğrulaması arkasına alınmalıdır.
