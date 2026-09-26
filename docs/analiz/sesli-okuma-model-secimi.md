# Sesli okuma — model seçimi (2026-09-25)

Hedef (kullanıcı kararı): **Türkçe seslendirme yapılır, e-kitapta okunan kelime vurgulanır.** Model yerelde (TT GPU
sunucusu) çalışır, dış servise metin gitmez. Ticari kullanıma kapalı lisanslı model ürüne girmez.

İki ayrı parça gerekir:

1. **Seslendirme (TTS):** metinden ses. Türkçe kalite, *ağırlık lisansı* ve *ses (voice) lisansı* ayrı ayrı önemli:
   ağırlık serbest olsa da hazır ses bir kişinin kaydıysa ya da ses klonlaması için başkasının kaydı kullanılıyorsa o
   kaydın hakları ayrıca gerekir.
2. **Kelime zamanlaması:** EPUB medya kaplaması (SMIL) her kelimenin sesteki başlangıç/bitişini ister. Aşağıdaki
   seslendirme modellerinin hiçbiri kelime zamanı vermiyor; zaman **Türkçe zorla hizalama** (forced alignment) ile
   çıkarılır: bilinen metin + üretilen ses → Türkçe CTC konuşma tanıma modeli → Viterbi hizalaması.

## Seslendirme modelleri

| Model | Türkçe | Ağırlık lisansı | Ses lisansı | Donanım / hız | Kelime zamanı | Karar |
|---|---|---|---|---|---|---|
| **VoxCPM2** (OpenBMB, 2 B, 2026-04) | Var (30 dilden biri); Minimax-MLS Türkçe **WER %0,82**, benzerlik %87,1 | **Apache-2.0**, ticari serbest | Hazır ses yok; **ses tarifle tasarlanır** ("(orta yaşlı, sıcak sesli kadın anlatıcı)…") → hiçbir gerçek kişinin sesi gerekmez. Klonlama isteğe bağlı (o zaman kaydın hakkı gerekir) | ~8 GB GPU; RTF ~0,30 (RTX 4090), hızlandırmayla ~0,13; 48 kHz. CPU yavaş | Yok → hizalama | **Seçildi** |
| Chatterbox Multilingual v3 (Resemble AI, 0,5 B, 2026-06) | Var (25 dil); Türkçe **CER %3,89** | MIT | Hazır Türkçe ses yok; **referans kayıt ister** (10 sn) → kaydın hakkı gerekir. Bütün çıktıya görünmez **filigran** (PerTh) gömülür | GPU'da ~5× gerçek zaman; CPU'da "nano" sürüm | Yok | Yedek aday (referans kaydı hakları çözülürse) |
| FreyaTTS-small (Freya, 183 M, 2026-07) | Yalnız Türkçe; WER %8,0 / CER %3,0 (kendi Türkçe kıyas setinde), MOS 3,68 | Apache-2.0 | Tek sabit ses (şirketin ses sanatçısı, kaynağı telefon bandı); klonlama yok | 1,5 GB GPU, RTF ~0,11; dizüstü CPU'da gerçek zamanlı; 48 kHz | Yok | Yedek aday: tek ses, karakter sesi yok, kaynak kaydı dar bantlı |
| Piper (rhasspy) — `tr_TR-dfki` | Var, orta kalite, robotik | Motor MIT (eski `rhasspy/piper`; yeni `piper1-gpl` **GPL-3.0**) | **CC BY-NC-SA 4.0** (DFKI veri seti) → ticari kapalı. `fahrettin`/`fettah` sesleri katkı sahiplerinin isteğiyle depodan kaldırıldı | CPU'da çok hızlı | Fonem süresi alınabilir | Elendi (ses lisansı) |
| Coqui XTTS-v2 | Var, doğal (MOS 3,82) | **Coqui Public Model License** — ticari olmayan; şirket 2024'te kapandı, ticari lisans alınamıyor | Klonlama (kayıt hakkı gerekir) | GPU | Yok | Elendi (ağırlık lisansı) |
| F5-TTS | Resmî Türkçe yok; topluluk ince ayarı zayıf (Freya kıyasında WER %24,3) | Kod MIT, **ağırlık CC-BY-NC** (Emilia verisi) | Klonlama | GPU | Yok | Elendi |
| Meta MMS-TTS (`mms-tts-tur`) | Var, tek ses, düz | **CC-BY-NC 4.0** | — | CPU | Yok | Elendi |
| OmniVoice (k2-fsa, 600+ dil) | Var | Kod Apache-2.0, **ağırlık CC-BY-NC** | Klonlama | GPU | Yok | Elendi |
| Kokoro-82M | **Türkçe yok** (en, ja, zh, es, fr, hi, it, pt) | Apache-2.0 | Hazır sesler Apache | CPU | Yok | Elendi (dil) |
| Qwen3-TTS | **Türkçe yok** (10 dil) | Apache-2.0 | — | GPU | Yok | Elendi (dil) |
| Voxtral TTS (Mistral) | **Türkçe yok** (9 dil) | CC BY-NC 4.0 | — | GPU | Yok | Elendi |
| CosyVoice 3 | **Türkçe yok** (9 dil) | Apache-2.0 | — | GPU | Yok | Elendi (dil) |

**Seçim: VoxCPM2.** Ticari serbest (Apache-2.0), Türkçede ölçülmüş en düşük hata, ve en önemlisi **ses tarifle
tasarlandığı için hiçbir gerçek kişinin sesine ihtiyaç duymaz**: anlatıcı ve karakter sesleri ("küçük kız",
"yaşlı dede" …) metinle tarif edilir. Tarifle tasarlanan ses her üretimde biraz değişebildiği için bir kez kısa bir
referans cümle üretilir ve kitabın geri kalanı o referansla **klonlanır** (referans model çıktısıdır, kişi kaydı değildir):
bir kitap boyunca aynı anlatıcı aynı sesle okur. Model çıktısına filigran eklemez.

Dikkat edilecekler:
- Tarifle ses tasarımının sonucu çalıştırmadan çalıştırmaya değişir; ses kataloğundaki her ses **bir kez** üretilip
  saklanır (yayınevi düzeyinde), sonra hep o referans kullanılır.
- Çok uzun girdide kararsızlık bildiriliyor: metin cümle cümle üretilir, aralara noktalamaya göre sessizlik konur.
- VoxCPM'in kendi metin normalleştiricisi Türkçe değil: sayı/tarih/kısaltma okunuşu bizim kurallarımızla yapılır
  (`production/narration.py`).
- Chatterbox yedek: yayınevi kendi seslendirmenini kaydeder (yazılı izinle) ve o sesle okutmak isterse klonlamada
  daha güçlü; ama çıktıya filigran gömer ve referans kaydın hakkı gerekir.

## Kelime zamanlaması (zorla hizalama)

| Model | Lisans | Not | Karar |
|---|---|---|---|
| **`Baybars/wav2vec2-xls-r-300m-cv8-turkish`** | **Apache-2.0** (taban `facebook/wav2vec2-xls-r-300m` Apache-2.0; veri Common Voice TR, CC0) | CTC, Türkçe harfler; tanımada CER %7,6 — hizalamada metin bilindiği için yeterli | **Seçildi** |
| `mpoyraz/wav2vec2-xls-r-300m-cv7-turkish` (WhisperX'in Türkçe varsayılanı) | CC-BY-4.0 (atıf şartıyla ticari serbest) | CV7 + MediaSpeech | Yedek |
| torchaudio `MMS_FA` (çok dilli hizalayıcı) | Ağırlık **CC-BY-NC 4.0** | — | Elendi |
| Whisper + DTW kelime zamanı | MIT | Tanımaya dayanır, bilinen metinle birebir eşleşmez; kaydırma olur | Kullanılmadı |

Hizalama yöntemi: metin (normalleştirilmiş okunuş) küçük harfe (Türkçe kurallarıyla I→ı, İ→i) çevrilir, model
sözlüğünde olmayan işaretler atılır, CTC Viterbi (torchaudio `forced_align`, BSD) ile harf harf hizalanır; kelimenin
zamanı ilk harfinin başlangıcı ile son harfinin bitişidir. Okunuşta birden çok kelimeye açılan yazım ("1923'te" →
"bin dokuz yüz yirmi üçte") ekranda tek kelimedir: zamanı açılan kelimelerin ilkinin başı ile sonuncusunun sonudur.
Hizalayıcı açılamazsa zamanlar harf sayısıyla orantılı **tahmin** edilir ve kayıtta `estimated: true` yazar.

## Üründe nasıl çalışır

- **Metin → okunuş** (`apps/editor/src/editor/production/narration.py`, model yok, kitaptan bağımsız): sayılar
  («1923'te» → «bin dokuz yüz yirmi üçte», «4'ü» → «dördü»), sıra sayıları («3. sınıf», «XX. yüzyıl»), ondalık, binlik
  ayırıcı, tarih, saat, yüzde, para/birim (yalnız sayıdan sonra), aralık («7-9» → «yedi ila dokuz»), bilinen kısaltmalar
  («Dr.», «vb.», «M.Ö.»), harf harf kısaltmalar («TBMM'nin» → «te be me menin»), ek uyumu («TL'lik» → «liralık»).
  Editörün **telaffuz sözlüğü** (işe ve yayınevine kayıtlı; iş sözlüğü önce gelir) bunların hepsinin önüne geçer.
- **Sayfa → okuma birimleri**: sayfa planının yazı blokları, konuşma balonları ve serbest yazıları; okuma sırası
  kutuların yeri (yukarıdan aşağı, soldan sağa). Balonun konuşanı karakter sesiyle okunur (ses seçimi ekranda; ilk
  öneri karakter tarifinden: «girl» → küçük kız, «grandfather» → yaşlı adam …). Şekil yazıları (tabela, rozet) okunmaz.
- **Üretim**: cümle cümle (uzun cümle virgülde bölünür, metin kesilmez), aralara noktalamaya göre sessizlik; sayfa başına
  bir MP3 (EPUB medya kaplamasının çekirdek türü). İş Temporal'da (`BookNarration`, sayfa başına bir etkinlik).
- **Kelime zamanı**: servis okunuş kelimelerini hizalar; narration.py bunları ekrandaki kelimelere bağlar, eksikleri
  harf sayısıyla doldurur (`estimated`), kısa boşlukları önceki kelimeye katar (vurgu kesintisiz geçer).

### EPUB'a giden veri biçimi: `narration.media_overlay(job)`

```jsonc
{
  "version": 1, "job": "<iş>", "format": "mp3", "complete": true, "duration": 812.4,
  "missing": [], "stale": [],                 // sesi olmayan / metni sonradan değişmiş sayfalar (pages'e girmez)
  "narrator": "anlatici-kadin", "narrators": ["Kadın anlatıcı", "Küçük kız"],   // OPF media:narrator için
  "pages": [{
    "page": "p_1a2b3c4d", "no": 4,            // plan sayfa kimliği, basılı sayfa no
    "audio": "/data/editor/storage/production/<iş>/ses/sayfa/p_1a2b3c4d.mp3", "href": "ses/sayfa/p_1a2b3c4d.mp3",
    "duration": 12.34,
    "blocks": [{                               // okuma sırasıyla
      "id": "c0b3", "kind": "para|dialogue|sound|heading|bubble|text", "speaker": null, "voice": "anlatici-kadin",
      "text": "Elif pencereden baktı.",        // bloğun düz metni (run'ların birleşimi)
      "start": 0.12, "end": 2.31,
      "words": [{"i": 0, "id": "w-c0b3-0", "text": "Elif", "char": [0, 4], "spoken": "Elif",
                 "start": 0.12, "end": 0.48}]  // char: text içinde [baş, son); zamansız kelime start/end null
    }]
  }]
}
```

`narration.smil(page, text_href, audio_href, word_id_fn=None)` bir sayfanın SMIL 3.0 belgesini yazar (kelime başına bir
`<par>`: `<text src="sayfa.xhtml#w-c0b3-0"/>` + `<audio clipBegin clipEnd/>`). EPUB tarafı: XHTML'de her kelimeyi
`<span id="w-<blok>-<i>">` ile sarar (char aralıklarıyla), manifest'te XHTML öğesine `media-overlay="smil-…"`, OPF'ye
`media:duration` (sayfa ve toplam) ve `media:active-class` (ör. `-epub-media-overlay-active`) eklenir.

## Deneme (2026-09-25, TT GPU sunucusu, geçici kap, CPU)

İki GPU da doluydu (GPU 0 BI modeli, GPU 1 görsel model çalışıyordu); deneme **CPU'da** yapıldı, çalışan hiçbir
kaba dokunulmadı. Geçici kap `editor-upscale:1` tabanında (`pip install voxcpm==2.0.3`), öneri servisi
(`apps/editor/images/voice/server.py`) içinde çalıştırıldı; ürün kodu (`narration.narrate_page`) bu servise bağlanıp
iki örnek sayfayı seslendirdi. Kap ve indirilen dosyalar iş bitince silindi.

- Örnekler: çocuk kitabı sayfası (anlatıcı + iki balon: «Elif» küçük kız, «Annesi» genç kadın; «Pıt pıt pıt!» ses
  sözcüğü; «Timaş» sözlükle «tımaş»; «1. baskı», «7 yaşında») ve roman paragrafı («1923'ün», «Dr.», «2. kat»,
  «06:45'ti», «%80», «TBMM'nin», «25.09.1923», «vb.», «XX. yüzyıl», «150 TL'lik», tireyle diyalog).
- **Anlaşılırlık:** üretilen ses, hizalayıcıdan bağımsız bir Türkçe tanıyıcıyla (`mpoyraz/wav2vec2-xls-r-300m-cv7-turkish`)
  yazıya döküldü, beklenen okunuşla karşılaştırıldı: **toplam harf hatası %2,4** (941 harfte 23). Farkların çoğu
  tanıyıcının boşluk/yazım farkı («rızabey», «herşeyi»); gerçek zayıflık yalnız yansıma sözcükte («pıt pıt pıt» →
  «fıkpıtpı»). ğ, ı, ş, ç, ö, ü; sayılar, tarih, saat, yüzde, kısaltmalar doğru okundu.
- **Kelime zamanı:** 121 kelimenin 121'i hizalayıcıyla bulundu (tahmin 0). Çocuk sayfası 26,2 sn, roman paragrafı 45,2 sn.
- **Hız (CPU, sıkıştırmasız):** tek başına 32 çekirdekte RTF 3,45 (6,6 sn ses 22,6 sn'de); sunucunun başka yükleriyle
  birlikte sayfa başına RTF ~8 (26 sn ses 211 sn'de). CPU kitabın tamamı için yetmez; ürün GPU'da koşmalı. GPU ölçümü
  yapılamadı (kartlar doluydu); yayımlanan değer ~8 GB bellek, RTX 4090'da RTF ~0,30 — kurulumda ölçülmeli.
- Hizalamada bir hata bulundu ve düzeltildi: `merge_tokens`'a boşluk jetonu verilmezse 0 sayılıyor, bu sözlükte 0 kelime
  ayırıcısı («|») olduğu için bütün kelimeler tahmine düşüyordu.

Örnek dosyalar (oturum karalama klasörü, depoya girmez): `cocuk-sayfasi.mp3/.json/.overlay.json/.smil`,
`roman-paragrafi.*`, ses referansları `ses-*.wav`.

## Kalıcı kurulum (2026-09-26, kullanıcı onayıyla)

GPU'da kalıcı olan yalnız ağırlıklar + MANIFEST ve imaj; gateway'e girmesi (yeni `models.yaml` + `gateway.py` ile
editor-py imajı) kullanıcının kurulum adımıdır.

1. **Ağırlıklar** `/data/editor/models/book-voice/` (6,22 GB), yalnız resmî Hugging Face deposundan, sabit rev ile:
   - `VoxCPM2/` ← `openbmb/VoxCPM2` @ `32279effe8c19989596f05d353d1447f51d9e915` (4,96 GB: `model.safetensors`,
     `audiovae.pth`, yapılandırma ve sözlük dosyaları, `README.md` model kartı `license: apache-2.0`). `LICENSE` model
     deposunda yok; OpenBMB'nin kod deposundan (`OpenBMB/VoxCPM` @ `f772e498a45fbb5fb8e13fbf9b9c48be9fe33e69`, Apache-2.0).
   - `aligner/` ← `Baybars/wav2vec2-xls-r-300m-cv8-turkish` @ `2362365a60811ed6740ec7702b2a28aca8914715` (1,26 GB:
     `pytorch_model.bin` + işlemci/sözlük dosyaları + model kartı). Dil modeli (`language_model/`, 0,5 GB) ve eğitim
     betikleri alınmadı (hizalamada kullanılmaz). `LICENSE` = apache.org Apache-2.0 metni.
   - `MANIFEST.json`'da iki anahtar (`openbmb/VoxCPM2`, `Baybars/wav2vec2-xls-r-300m-cv8-turkish`): `dir`, `revision`,
     `url`, `license`, `files` (dosya başına sha256). Her dosya Hugging Face ile karşılaştırıldı (büyük dosyada LFS
     sha256, küçük dosyada blob kimliği); `deploy/verify_models.py VoxCPM2 wav2vec2-xls-r-300m-cv8-turkish` OK.
2. **İmaj** `editor-voice:1` (`sha256:8f3220f8e465…`, 35,9 GB ama tamamına yakını vLLM-Omni tabanıyla ortak; kendi
   katmanı 32,5 MB). `pip install --no-deps voxcpm==2.0.3`: bağımlılıkla kurulum tabanın `nvidia-nccl-cu13`'ünü
   2.30.7 → 2.29.7'ye indiriyordu, öteki bağımlılıkların hepsi tabanda var.
3. **`models.yaml`** `book-voice`: `gpu: 1`, `mem_fraction: 0.12`, `idle_stop_sec: 300`, `image: editor-voice:1`,
   `entrypoint: [python, /srv/server.py]`, derleme önbelleği (`TORCHINDUCTOR_CACHE_DIR`/`TRITON_CACHE_DIR`) gateway'in
   kalıcı `vllm-cache/book-voice` klasöründe. Pay servis içinde PyTorch'un bellek tavanıdır (`server.py`,
   `--gpu-memory-utilization`).
4. **`gateway.py`** `PASSTHROUGH`'a `audio/narrate`.

### GPU ölçümü (2026-09-26 05:45–05:55, geçici kap, GPU 1, ana model yanında açıkken)

Önce kontrol: GPU 1'de yalnız ana model (47 GiB), `busy.json` yok, Temporal'da süren iş yok, görsel model kapalı.
Kap gateway'in kuracağı kabın aynısı (aynı imaj, `/model` salt okunur, `HF_HUB_OFFLINE=1`, GPU 1); ürün kodu
(`narration.page_units → pieces → voice_ref → _call → word_times`) kaba bağlanıp sayfaları seslendirdi. Çalışan hiçbir
kaba dokunulmadı; kap, önbellek ve çıktılar iş bitince silindi.

| Yapılandırma | Açılış | Bellek hazır / tepe (nvidia-smi) | Çocuk sayfası (8 parça, 22 sn ses) | Roman paragrafı (6 parça, 45 sn) | Uzun cümle (2 × ~390 harf, 48 sn) |
|---|---|---|---|---|---|
| torch.compile, tavan 0.10, önbellek boş | 82 sn | 7,6 / 9,8 GiB (PyTorch tepe 9,1) | RTF 0,46 (+ 3 sesin referansı 6,9 sn) | RTF 0,35 | RTF 0,34 |
| torch.compile, tavan 0.12, önbellek dolu | **41 sn** | 7,6 / 9,3 GiB | RTF 0,41 | RTF 0,37 | — |
| derlemesiz, tavan 0.12 | 28 sn | 6,7 / 8,3 GiB | RTF 0,63–0,74 | RTF 0,59 | — |

- **Pay:** 0.10 (9,4 GiB) PyTorch tepesine (9,1 GiB) çok yakın → **0.12** (11,2 GiB). Aynı kartta: ana model 0.48 +
  0.12 = 0.60; görsel model 0.62 + büyütücü 0.06 + 0.12 = 0.80 < 0.92.
- **Derleme açık kalır:** açılış bir kez 41–82 sn, üretim ~1,7 kat hızlı; kitap sayfa sayfa art arda okunduğu için
  (boşta 300 sn) açılış bir kez ödenir. RTF, ana model aynı kartta %52 meşgulken ölçüldü.
- **Kelime zamanı:** 225 kelimenin 225'i hizalayıcıyla (tahmin 0); açılan yazımlar tek kelime olarak zamanlandı
  («1923'ün» 0,00–1,22 sn, «25.09.1923» 11,47–13,43 sn, «TBMM'nin» → «te be me menin» 10,71–11,47 sn).

### Kurulumda kalan (kullanıcı)

Yeni editor-py imajı (models.yaml imaja girer) ile gateway yeniden kurulur; stüdyo servisi ve işçisi yeni kodla
kalkar (BookNarration), giriş kapısı betiği (`add-studio-routes.py`) ve köprü; sonra test sunucusunda gerçek bir
kitabın birkaç sayfası gateway üzerinden seslendirilip ekranda dinlenir (model devri gateway kaydıyla doğrulanır),
anlaşılırlık ölçümü tekrarlanır.

## Kaynaklar

- VoxCPM2: <https://github.com/OpenBMB/VoxCPM>, <https://huggingface.co/openbmb/VoxCPM2>
- vLLM-Omni konuşma API'si (VoxCPM2'yi sunar, kelime zamanı vermez): <https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/speech_api/>
- Chatterbox: <https://github.com/resemble-ai/chatterbox>, <https://huggingface.co/ResembleAI/chatterbox>,
  v3 ve dil başına CER: <https://www.resemble.ai/resources/chatterbox-multilingual-v3-tts-with-embedded-watermarking-for-25-languages>
- FreyaTTS: <https://arxiv.org/abs/2607.09530>, <https://huggingface.co/freyavoice/Freya-TTS>, <https://github.com/freyavoiceai/FreyaTTS>
- Piper sesleri ve DFKI lisansı: <https://github.com/rhasspy/piper/blob/master/VOICES.md>,
  <https://huggingface.co/rhasspy/piper-voices/blob/main/tr/tr_TR/dfki/medium/MODEL_CARD>
- Coqui XTTS / MMS-TTS lisansları (özet): <https://www.ablt.dev/blog/turkish-tts/>,
  <https://github.com/Rumeysakeskin/free-turkish-tts-models>
- OmniVoice ağırlık lisansı: <https://huggingface.co/k2-fsa/OmniVoice>
- Qwen3-TTS dilleri: <https://github.com/QwenLM/Qwen3-TTS>
- Voxtral TTS: <https://huggingface.co/mistralai/Voxtral-4B-TTS-2603>, <https://mistral.ai/news/voxtral-tts/>
- CosyVoice: <https://github.com/QwenAudio/CosyVoice>
- Türkçe hizalayıcılar: <https://huggingface.co/Baybars/wav2vec2-xls-r-300m-cv8-turkish>,
  <https://huggingface.co/mpoyraz/wav2vec2-xls-r-300m-cv7-turkish>, WhisperX: <https://github.com/m-bain/whisperx>
