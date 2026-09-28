# Zeki AI sesli not — model ölçümü (2026-09-28, TT GPU, GPU 0)

Soru: saha ve okul ziyaret notu için Türkçe konuşma tanımada hangi açık model «çok kaliteli» not tutar, GPU'daki BI
modeli ve editör işleri durmadan çalışır mı? Ölçüm TT GPU'da geçici klasörde (`/data/voice-olcum-claude`, iş bitince
silindi), GPU 0'da, süreç başına 10 GB bellek tavanıyla yapıldı; hiçbir servis durdurulmadı/yeniden başlatılmadı.
Betikler: [olcum/](olcum/) (`indir.py`, `olc.py`, `runall.sh`).

## Veri ve koşullar

- **FLEURS tr_tr test** (Google, CC-BY-4.0): 743 kayıt, 156,3 dakika, okunmuş genel Türkçe cümle.
- **temiz**: kayıt olduğu gibi.
- **telefon**: 300–3400 Hz bant, 8 kHz μ-law (G.711) ve geri 16 kHz.
- **kalabalık**: aynı setten başka 5 konuşmacının üst üste bindirilmiş uğultusu, SNR 10 dB, sonra Opus 32 kb/sn
  (tarayıcı kaydı gibi). Mağaza/okul koridoru gibi arkada konuşma olan ortamın vekili.
- **Normalleştirme** (referans ve çıktıya aynı): Türkçe küçük harf (İ→i, I→ı), şapka düşer, kesme işareti atılır
  («Ankara'da» = «Ankarada»), noktalama atılır, sayılar yazıya çevrilir («%15» = «yüzde on beş»).
- **Alan dili (iskonto, vade, sevk, kitap/okul/yayınevi adları) ÖLÇÜLMEDİ.** Açık Türkçe veride satış ziyareti dili
  yok; ben seslendiremediğim için yalnız açık veriyle ölçtüm. Sahada okunacak 20 cümle hazır:
  [olcum/alan-cumleleri.tsv](olcum/alan-cumleleri.tsv); ölçüm `OLC_ALAN=<dizin> python3 olc.py …` ya da uçtan uca
  `scripts/acceptance/voice-note/kabul.py`.

## Adaylar

| Aday | Ne | Lisans |
|---|---|---|
| openai/whisper-large-v3 | büyük çok dilli model (1,55 Mr parametre) | MIT |
| openai/whisper-large-v3-turbo | aynı ailenin hızlı sürümü (4 katmanlı çözücü) | MIT |
| turkmedstt/whisper-large-v3-turkish-general | large-v3'ün ~140 saat genel Türkçeyle (CV, ISSAI, OpenSLR; FLEURS yok) ince ayarı | Apache-2.0 |
| Qwen/Qwen3-ASR-1.7B-hf | 2026'nın çok dilli tanıma modeli (Türkçe destekli) | Apache-2.0 |

Hepsi hazır vLLM imajındaki transformers ile, fp16/bf16, açgözlü çözüm (beam 1), toplu 16 (Qwen 8).

## Sonuç

| Model | temiz WER / CER | telefon WER / CER | kalabalık WER / CER | hatasız cümle (temiz/telefon/kalabalık) | 1 dk ses, GPU | 1 dk ses, sıralı | GPU belleği (60 sn / toplu 16 tepe) |
|---|---|---|---|---|---|---|---|
| **whisper-large-v3** | **%4,80 / %1,25** | **%5,83 / %1,66** | **%10,12** / %4,83 | **%56 / %51 / %39** | 1,49 sn | 2,75 sn | 3,9 / 7,8 GB |
| whisper-large-v3-turbo | %5,20 / %1,36 | %6,20 / %1,71 | %14,53 / %8,02 | %54 / %48 / %33 | **0,32 sn** | 0,43 sn | 1,8 / 2,8 GB |
| Türkçe ince ayarlı (tr-general) | %5,52 / %1,50 | %6,38 / %1,73 | %10,52 / **%4,28** | %53 / %48 / %34 | 1,37 sn | 2,84 sn | 3,9 / 7,8 GB |
| Qwen3-ASR-1.7B | %7,57 / %1,95 | %9,03 / %2,56 | %12,19 / %4,72 | %40 / %34 / %24 | 2,12 sn | 4,25 sn | 4,7 / 9,5 GB (toplu 8) |
| large-v3, beam 5 | %4,56 / %1,19 | %5,32 / %1,39 | %11,55 / %6,46 | — | 2,41 sn | 3,34 sn | 5,9 / 10,0 GB (toplu 4) |

«1 dk ses, GPU»: 60 sn kayıt, servisin yaptığı gibi iki 30 sn parça tek toplu çağrıda (üç ölçümün ortancası, ısınmış).
«Sıralı»: aynı iki parça tek tek. **CPU yolu** (32 çekirdek, fp32): large-v3 1 dk ses 10,4 sn, turbo 3,8 sn.

Gözlemler:
- **large-v3 her koşulda en iyi WER.** Türkçe ince ayarlı sürüm genel veride tabandan iyi değil (kalabalıkta CER'i
  biraz iyi); Qwen3-ASR Türkçede belirgin geride ve 2,5 kat yavaş.
- **turbo gürültüde bozuluyor** (%14,5) ve bir kalabalık kaydında 184 kelimelik tekrar döngüsüne girdi.
  large-v3'te boş ya da döngüye giren çıktı yok (en kötü cümle 10 kelime hata).
- **beam 5** temiz/telefonda 0,2–0,5 puan kazandırıyor ama kalabalıkta kötüleşiyor (%11,55), 1,6 kat yavaş ve belleği
  ikiye katlıyor → servis beam 1.
- large-v3'ün kalan hataları çoğunlukla yabancı özel adlar («Mitchell Gourley» → «Michel Goli») ve bitişik/ayrı yazım
  («sebebi ile»/«sebebiyle», «sualtı»/«su altı»); sıra sayıları rakamla gelir («on birinci» → «11.»). Anlamı bozan
  hata az. Özel ad ve noktalama için portal tarafında isteğe bağlı Zeki AI düzeltmesi var (sayı denetimli).

## Örnek çıktılar (large-v3, temiz)

| Referans | Çıktı |
|---|---|
| USOC'nin; lisans iptali yerine kurumumuzda mantıklı değişiklikler yapmaya devam ederek atletlerimizin, kulüplerimizin ve yaptıkları sporların çıkarlarına daha iyi hizmet edilebileceği yönündeki beyanına katılıyoruz. | USOC'nin lisans iptali yerine kurumumuzda mantıklı değişiklikler yapmaya devam ederek atletlerimizin, kulüplerimizin ve yaptıkları sporların çıkarlarına daha iyi hizmet edebileceği yönündeki beyanına katılıyoruz. |
| Çoğu modern araştırma teleskobu, uygun atmosfer koşullarına sahip ücra bölgelerdeki devasa tesislerdir. | Çoğu modern araştırma teleskobu uygun atmosfer koşullarına sahip ücra bölgelerdeki devasa tesislerdir. |
| Sualtı topolojisi nedeniyle, geri dönüş akışı birkaç derin kısımda yoğunlaşır … | Su altı topolojisi nedeniyle geri dönüş akışı birkaç derin kısımda yoğunlaşır … |
| … Avustralyalı Mitchell Gourley on birinci sırada bitirdi, Çek yarışmacı Oldrich Jelinek … (en kötü) | … Avustralya'nın Mitchell Gourley 11. sırada bitirdi. Çek yarışmacı Oldswich Jelinek … |

## Servis denemesi (gerçek model, geçici konteyner; kurulum değil)

Depodaki servis kodu (`apps/voice-note`) large-v3 ile, kurulacak düzende (salt okunur kök, `/tmp` bellekte, GPU 0,
bellek payı 0,11, toplu 8) 127.0.0.1:18797'de açıldı, denendi ve kaldırıldı.

| Deneme | Sonuç |
|---|---|
| 191,8 sn birleşik FLEURS kaydı, WAV / AAC / Opus 32 | 200; işlem 6,5 sn (ilk istek) / 2,4 sn / 4,6 sn; 15 parça, zaman damgalı |
| Aynı kaydın WER'i: servis (parçalı) ↔ aynı 15 cümle tek tek | %11,39 ↔ %11,39 — parçalama kalite kaybettirmiyor (bu 15 cümle ortalamadan zor) |
| 68,6 sn kayıt, 3 eşzamanlı istek | sırayla: bekleme 0 / 2,4 / 3,3 sn, işlem 2,4 / 1,0 / 1,0 sn |
| 10 sn sessizlik | 200, boş metin (modele gitmedi) |
| sınırdan uzun kayıt / bozuk gövde | 413 / 400 |
| servis belleği | 3,4 GB (hazır) → 5,5 GB tepe |
| günlük / konteyner dosyaları | günlükte yalnız süre/parça/bekleme; `/tmp`'de yalnız CUDA derleme önbelleği, ses yok |

Bu denemede bir hata bulundu ve düzeltildi: sabit «konuşma eşiği» (RMS 0,008) kısık okunmuş iki gerçek cümleyi
sessiz sayıp atıyordu (WER %24). Sessizlik artık kaydın kendi gürültü tabanına göre (95. yüzdelik < max(0,0015,
2 × 20. yüzdelik)) — düzeltmeden sonra %11,39.

## Karar

**Seçim: openai/whisper-large-v3, beam 1.** Genel Türkçede WER %4,8 (CER %1,25), telefon hattında %5,8, kalabalık
ortamda %10,1; cümlelerin yarısından fazlası hatasız. «Çok kaliteli not» için kalite eşiği olarak temiz ≤ %6, telefon
≤ %8, kalabalık ≤ %12 WER aldım; large-v3 üçünü de geçiyor (turbo kalabalıkta, Qwen3-ASR temizde geçmiyor). 1 dakikalık
not GPU'da ~1,5 sn; 10 GB bellek payının içinde (tepe 5,5 GB).

**Sınır:** satış/okul ziyareti diline özgü terim ve özel adlar ölçülmedi. Sesli not ekranı ayarla kapalı gelir
(`VOICE_NOTE_ENABLED=0`); açma kararı sahada okunan 20 alan cümlesinin kabul sonucuna (`kabul.py`) bağlı —
karar kullanıcıda. GPU 0'daki boş bellek o an koşan işlere göre değişiyor (ölçüm başında 13 GB, sonunda başka bir
oturumun eğitim işiyle 5 GB); servis kurulurken `nvidia-smi` ile yer olduğu görülmeli, yoksa CPU yolu
(`VOICE_DEVICE=cpu`, 1 dk ≈ 10 sn) seçilebilir.
