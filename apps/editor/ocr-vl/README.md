# Sorunlu bölge OCR-VL aracı

Bu araç sabit `PaddlePaddle/PaddleOCR-VL-1.6` revision'ını yalnız özgün PDF'den alınan sorunlu kırpımlarda OCR için kullanır. Çıktı doğrulanmış kitap metni değildir; analize otomatik kabul edilmez. Referans kitap veya beklenen cevap prompt'a girmez.

Sunucuda paket hazırlama:

```sh
python3 scripts/prepare-ocr-vl.py
python3 scripts/build-ocr-vl.py
python3 scripts/pilot-ocr-vl.py
python3 scripts/verify-ocr-vl.py
```

İndirme yalnız ilk komutta internet kullanır. Sonraki araç `network_mode: none`, 4 CPU, 10 GiB, salt okunur kök ve ayrı artifact alanıyla çalışır. Model dosyaları imaj içinde hash kontrolünden geçer; uzak model kodu çalıştırılmaz. Pilot gerçek API ve PostgreSQL eşliğini kontrol eder, s.29/38 başarısız bölgelerinin en fazla 32'sini seçer. Kırpım/metin özel sunucu artifact alanında kalır. Süre aşımında yalnız koşunun kendi konteyneri kaldırılır. Aynı kod/kutu/render için tamamlanan artifact yeniden kullanılır; değişen kod aynı artifact'ın üstüne yazamaz.

Çıktı: `ocr-vl-regions-v1/<generation>/<span_id>.json`; özgün kaynak, kutu, kırpım, kod ve model hashleri, EOS/tamamlanma, süre ve ham OCR bulunur. Tamamlanmayan yanıt reddedilir. Doğrulayıcı okuyucu eşleşmesini raporlar; bunu semantik kabul olarak göstermez ve kitap kayıtlarını değiştirmez.

İsteğe bağlı offline paket:

```sh
python3 scripts/bundle.py /guvenli/benzersiz-paket-yolu --with-models --with-ocr-vl
```

Model ağırlıkları bu imajda gömülüdür. `ocr-vl` araç profili normal servis açılışında başlatılmaz. Paket/restore kabulü yeni imaj için ayrıca yapılmalıdır. Tam otomatik pipeline entegrasyonu ve müşteri kabulü henüz tamamlanmadı.

Resmi model: https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6
