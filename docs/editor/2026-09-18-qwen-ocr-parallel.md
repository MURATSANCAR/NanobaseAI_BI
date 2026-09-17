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

## R5/R6 canlı kabul ve R9 çağrı seçimi

R5 `c5620657` 29. sayfa: 11 gerçek OCR bölgesi + bir Qwen görsel çağrısı, örtüşen istek süreleri, API/PG ve ham cevap/kırpım hashleri geçti. Qwen çağrısı205.189 saniye; bu ağ aktarımı dahil süredir, saf GPU hesaplama hızı değildir. Figür kuyruğu eşleşse de isim kanıtı olmadığından konuşmacıUNKNOWN kaldı.

R6 `8c98ea5f`, iş `0fe8c09a-403f-4055-a753-c4f60252b34f`: 29/38/6/28 ve 1–5/7/8 dahil ilk11 sayfanın teknik denetimi geçti, başarısız0. 6. sayfada taze Qwen çıktısı gözleri açık figür kaydetti (258.853 saniye). 38. sayfada olumsuzluk kaynak metinde korundu; bazı VL harf hataları kabul edilmedi. Yeni ham OCR cevaplarını source-review API ve mevcut panelde gösteren bağlantı tamamlandı. Gerçek Chrome/API ile320/390/768/1440 genişliklerinde6 sekme, OCR29/38 görünümü, bbox ve taşma denetimi geçti; kanıt `evidence/review-ui-parallel-r6/verification.json`. İlk tarayıcı denemesinde denetim betiği zaten açık details öğesini kapatmıştı; açma durumu kontrol edilerek aynı gerçek akış yeniden geçti.

CPU LLM kapatıldı; GPU Compose içinde `cpu-llm` açık profiline alındı. Embedding/reranker korundu. `!override` için Compose2.24.4+ gerekir; mevcut sunucu Compose5.1.4 ile servis listesindeCPU LLM yokluğu doğrulandı.

R9, yalnız açık kaynak bölgelerinde çağrı gerekliliğini değerlendirir. İki harften oluşan metin dayanağı yoksa VL çağrısı atlanır; temiz konumlu PDF veya stabil PP-OCR/Tesseract kırpımıyla desteklenen tek glif istisnası korunur. Tek başına kararsız Tesseract tahmini çağrı sebebi değildir. Atlanan bölge silinmez, NON_TEXT ya da kabul edilmiş sayılmaz: NEEDS_REVIEW ve çağrı gerekçesi kalır. Gerçek R6 PostgreSQL'deki67 önceki çağrıda44 gerekli/23 atlanabilir; atlananlarda kabul edilmiş kaynak yok. Büyük başlangıç harfiD olayı bu kuralın gerçek tek-glif regresyon kontrolüdür. `evidence/ocr-routing-r9-live.json`; module hash `42b6af0fa1683a154e5f3d8e0639e525fe43f7a3b42eee75e2bb4b6e5a2a4363`. R9 dağıtım kabulü ayrıca kaydedilecektir.
