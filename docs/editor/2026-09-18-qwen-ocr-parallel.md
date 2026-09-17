# Qwen + isteğe bağlı OCR — V11

Qwen3.8-Flash-Next ana görsel/analiz modelidir. PaddleOCR-VL-1.6 yalnız klasik kaynak seçimi sonrası açık kalan kutularda çalışır. Aynı sayfanın görsel gözlemi kaynak OCR işlemleriyle tek ek iş parçacığında paraleldir; iddia üretimi her ikisini bekler. İşçi hâlâ sayfa sayfa ilerler.

Yeni `ocr_vl.py`, özgün render ve bbox üzerinden CPU servisine kırpım yaptırır; GPU modeline yalnız kırpım ve resmi `OCR:` görev istemini verir. Kitap cevabı, konuşmacı adı veya önceki okuma prompta eklenmez. Ham cevap, kırpım baytları, kaynak/render/kırpım/istek/cevap hashleri, model revizyonu ve süreler yeni immutable kaynak kayıtlarında saklanır. Kesilmiş cevap kabul edilmez. Destek: temiz PDF veya stabil iki Tesseract kırpımı, ayrıca bölgesel PP-OCR eşliği; stabil çelişki veto eder. Bu optik eşliktir, anlamsal kabul değildir.

`/v1/model-services`, OCR için `/gateway/status` çağırır; izleme modeli uyandırmaz. GPU profili ayrı ana model ve OCR adresleri/revizyonu ister; bulut fallback yoktur. Mac üzerinde ayrı 18083 OCR proxy + 18883 ters SSH, Docker köprüsünde18884 nginx vardır. Mevcut ana model yolu değişmez. Tünel Mac/VPN bağımlıdır; müşteri ağında adresler kendi özel bağlantısına göre verilmelidir.

Dağıtım ve gerçek API/PostgreSQL kabulü devam ediyor. Önceki V5 ve kitap kaynakları değiştirilmez; yeni nesil üretilir. P1 kaynak, P2 konuşmacı ve semantik kabul tamamlandı iddiası yoktur.

Model görev istemi: https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6 (resmi model kartı).
