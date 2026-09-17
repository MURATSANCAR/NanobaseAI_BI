# Qwen + isteğe bağlı OCR — V11

Qwen3.8-Flash-Next ana görsel/analiz modelidir. PaddleOCR-VL-1.6 yalnız klasik kaynak seçimi sonrası açık kalan kutularda çalışır. Aynı sayfanın görsel gözlemi kaynak OCR işlemleriyle tek ek iş parçacığında paraleldir; iddia üretimi her ikisini bekler. İşçi hâlâ sayfa sayfa ilerler.

Yeni `ocr_vl.py`, özgün render ve bbox üzerinden CPU servisine kırpım yaptırır; GPU modeline yalnız kırpım ve resmi `OCR:` görev istemini verir. Kitap cevabı, konuşmacı adı veya önceki okuma prompta eklenmez. Ham cevap, kırpım baytları, kaynak/render/kırpım/istek/cevap hashleri, model revizyonu ve süreler yeni immutable kaynak kayıtlarında saklanır. Kesilmiş cevap kabul edilmez. Destek: temiz PDF veya stabil iki Tesseract kırpımı, ayrıca bölgesel PP-OCR eşliği; stabil çelişki veto eder. Bu optik eşliktir, anlamsal kabul değildir.

`/v1/model-services`, OCR için `/gateway/status` çağırır; izleme modeli uyandırmaz. GPU profili ayrı ana model ve OCR adresleri/revizyonu ister; bulut fallback yoktur. Mac üzerinde ayrı 18083 OCR proxy + 18883 ters SSH, Docker köprüsünde18884 nginx vardır. Mevcut ana model yolu değişmez. Tünel Mac/VPN bağımlıdır; müşteri ağında adresler kendi özel bağlantısına göre verilmelidir.

Dağıtım ve gerçek API/PostgreSQL kabulü devam ediyor. Önceki V5 ve kitap kaynakları değiştirilmez; yeni nesil üretilir. P1 kaynak, P2 konuşmacı ve semantik kabul tamamlandı iddiası yoktur.

Model görev istemi: https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6 (resmi model kartı).

## Gerçek koşuda bulunan ve kodda kapatılan engeller

- R3 yeni sürüm yönlendirme listesinde yoktu; eski akışa geçiş bulundu, API iptali ve worker durdurmasıyla kesildi. R4 artık manifest sürümü çalışan sürümle eşleşmezse açık hata verir; legacy fallback yoktur. Başarısız nesil `2f95aef0` korunur, kabul değildir.
- R4 nesil `145d114a`, 38. sayfada dört gerçek VL bölgesi üretti; API/PG ve ham cevap/kırpım hashleri geçti, destek yetersiz olduğundan sıfır yükseltme. Seçilmiş resim bölgesi olmadığından bu sayfada paralel görsel çağrısı yoktu.
- 29. sayfada paylaşılan CPU kırpım servisi429 verdi. R5 açık429/503 cevaplarına sınırlı tekrar ekler; read timeout tekrar edilmez. R4 FAILED kaydı korunur. R5 aynı gerçek sayfada yeniden kabul edilecek.
- İlk arşivde AppleDouble dosyaları migration yüklemesini durdurdu; aday imajdaki metadata temizlendi. R4 uygulama/check-out 41 dosya birebir eşleşti, backend tree SHA256 `2b2bbc22fc7aa1e3600f395e6f8ce7196b4c73754678c29c94d5845bb0c29e26`. Bu hash sonraki R5 kabulünün yerine geçmez.
