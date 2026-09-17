# Türkçe ses kaynağı hazırlığı

Kaynak: https://huggingface.co/datasets/Anilosan15/Turkish_TTS_Data

Bu araç yalnız özgün sesleri indirir ve metin eşlerini çıkarır. Model eğitmez,
kitap metnini değiştirmez, çalışan Editör servislerine bağlanmaz.

```sh
python3 -m venv apps/editor/runtime/speech-tools
apps/editor/runtime/speech-tools/bin/pip install -r apps/editor/speech/requirements.txt
apps/editor/runtime/speech-tools/bin/python apps/editor/speech/prepare.py --output apps/editor/runtime/speech/turkish-tts-full
```

Sabit kaynak sürümü ve beklenen satırlar `source.json` içindedir. Parquet dosyaları
Hugging Face LFS SHA-256 değerleriyle karşılaştırılır. Sesler yeniden kodlanmadan
`audio/train` ve `audio/test` içine çıkarılır; özgün metin, kaynak dosya/satır,
ses hash'i, süre ve kanal bilgisi `clips.jsonl` içine yazılır. Konuşmacı etiketi kaynaktan korunur; doğrulanmış kişi kimliği sayılmaz. `acquisition.json` tamamlanan kapsamı gösterir; `--max-shards 1` ile sınırlı indirme SUBSET_ACQUIRED, tam satır eşliği SOURCE_ACQUIRED olur.
Başarısız indirme yeniden çalıştırılabilir; tamamlanmış sağlam dosyalar korunur.
Aynı hedefte eşzamanlı iki hazırlama çalıştırmayın. Runtime Git/paket dışındadır.

Yeni kaynak f2710360882a31325a932431480e00a49f69e3e3 sürümünde 30.606 kayıt,
41 Parquet dosyası ve 20.684.866.085 bayt içerir. İlk shard indirildi, LFS hash'i
bb5abfb15c22070a59832ea51c3fa5dd06929a326727670352408e48e10d0acf doğrulandı.
İlk shard içindeki 747 WAV (84,13 dakika), `runtime/speech/turkish-tts` altında
sürüm dizininde özgün baytları ve metin manifestiyle saklanır; ayrıca ilk 10 referans çıkarılmıştır.
İlk ölçümler 48 kHz/mono; referans 1 yaklaşık 7,05 saniyedir. Tam küme henüz
indirilmedi. Önceki Khan Academy denemesi yeni ses seçimi olarak kullanılmaz.

## Kitap seslendirmeye geçiş

1. Kaynak kartında lisans belirtilmemiş; ticari kullanım uygunluğu doğrulanmadı.
2. Kaynak `speaker=sıla` etiketi içeriyor. Referansların temizliği, ses benzerliği
   ve kullanım kapsamı ayrıca değerlendirilmeli; bu etiket kişi kimliği kanıtı değil.
3. Türkçe destekleyen referans-sesli TTS modelini lisans/donanım/gerçek dinleme
   ölçümüyle seç. Kısa pilot adayı Chatterbox Multilingual 0.1.7; CPU üzerinde ayrı ortam hazırlanıyor. Mevcut OCR/LLM GPU
   işlerinin yanına ölçümsüz yeni servis başlatma.
4. Kitap API sözleşmesi: kaynak sürüm + source_span kimlikleri + tam metin hash'i,
   dil, ses profili ve model revision; çıktı: parça sırası, ses hash'i, süre,
   üretim durumu. Metni LLM ile yeniden yazma; incelemedeki kaynakları onaylı
   sayma. Kitap/karakter adına özel kural ekleme. Uzunluk ve eşzamanlılık sınırları
   model seçildikten sonra açık yapılandırmaya alınmalı.
5. Gerçek Editör API/PG üzerinde en az iki farklı kitapta kısa pilot: atlanan veya
   yinelenen kelime, sayı/özel ad telaffuzu, ton, parça birleşimi ve hız ölçümü.
   ASR karşılaştırmasına ek bağımsız dinleme gerekir. Arayüz eklendiğinde
   320/390/768/masaüstü oynatma, duraklatma ve kaldığı yerden devam kabulü gerekir.

Hazırlanan arşiv bir TTS modeli değildir. Kitap seslendirme ürün kabulü: **DOĞRULANAMADI**. Pilot sonuçları ayrıca kaydedilir.

## Kısa pilotu yeniden üretme

Ayrı sunucu venv ortamında CPU torch/torchaudio 2.6.0 ve
`requirements-synthesis.txt` kurulur. `synthesize.py --text <kaynak.txt>
--reference <referans.wav> --output <yeni-nesil.wav>` yalnız tek klip üretir.
Varsayılan 8 CPU thread; mevcut GPU modellerini kullanmaz. Çıktının yanında
metin/referans/çıktı hashleri ve süre raporu yazılır. Dinleme ve üretim kabulü
varsayılan false kalır. Aynı çıktı üzerine yazılmaz.

Python 3.12 üzerinde chatterbox 0.1.6'nın numpy<1.26 bağımlılığı kurulamadı;
başarısız log korundu, 0.1.7 ile yeniden kurulum başlatıldı. Yerel ürün testi yok.

Pilot checkpoint: `ResembleAI/chatterbox`, revision
`5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18`, `t3_mtl23ls_v2.safetensors`.
Paket 0.1.7'nin yükleyicisi V2 checkpoint kullanır; bu pilot V3 olarak sunulmaz.
İndirme ağ gerektirir; çevrimdışı ürün paketine henüz eklenmemiştir.
