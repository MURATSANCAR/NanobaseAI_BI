# Dörtgen düzeltmeli bölge okuma — ölçüm, üretim tercihi değil

`server-perspective-v1.py` mevcut üretim OCR sunucusunun ölçüm için dondurulmuş bir varyantıdır. `regional_geometry=compare-perspective-v1` istendiğinde aynı Paddle tanıyıcısıyla dörtgeni perspektif dönüşümle düzelten ek kırpımı okur. Beklenen kitap metni verilmez; üretim `region_text` alanı değiştirilmez. Bu dosya ana OCR Dockerfile'ında kullanılmaz.

Gerçek 48 sayfalık kitabın sorunlu sayfalarında, aynı sayfa/render/hash ve önceki API/PG kayıtlarıyla karşılaştırıldı. S.29: 14 bölge, eski/yeni anlaşma 3/3. S.38: 24 bölge, eski/yeni anlaşma 20/20. Mevcut kapı ve Tesseract/PDF yeniden okuma çelişkileri korunarak iyileşen veya gerileyen bölge 0; ilk ölçümlere göre durum sapması 0. Süreler 9,689 ve 21,416 saniye. Bu optik anlaşma ölçümüdür; anlamsal doğruluk oranı değildir.

Üretim OCR imajı değiştirilmedi. Kaynak/iddia/review kaydı yazılmadı. Ayrı deney konteyneri durduruldu. Temel imaj `sha256:4e69a4268296fc59285a5c137ebb411c78fe4ed00a23a5486e4671fd700f1deb`; deney `sha256:68bab438b92417280e8351d2e93746b48044a419a15b18068353f4b9fbdab7aa`.

Gerçek sunucudaki ölçüm betiği `scripts/probe-ocr-geometry.py`; kanıt `evidence/ocr-geometry-summary.json` ve sayfa bazlı aynı önekli JSON dosyalarıdır. Tek başına kırpım geometrisini değiştirmek bu iki sayfadaki blokajı çözmediği için üretim varsayılanı yapılmadı.

## Bağımsız kelime kutusu kırpımı

`word_geometry_probe.py` + `scripts/probe-word-crops.py`, model cevabı verilmeden yalnız gerçek görüntülerle ölçüm yapar. 48 sayfada 799 ölçülebilir bölge: 19 optik iyileşme, 47 gerileme; 350 bölgede bağımsız kelime kutusu bulunmadı. Varsayılan yöntem için reddedildi, kaynak kayıtları değiştirilmedi. Detay ve gerçek sunucu kanıtı `docs/editor/2026-09-17-restore-acl-and-source-triage.md`.
