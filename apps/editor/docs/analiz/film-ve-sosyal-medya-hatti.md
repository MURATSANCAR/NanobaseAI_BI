# Kitaptan film, çizgi film ve sosyal medya kısa videosu — hat sözleşmesi

2026-10-04. Kullanıcı kararı: «paralelde hem sosyal medya paylaşımları hem de çizgi film için uçtan uca yapı; modelleri
ayağa kaldırma, sadece kod tarafını hazırla». Kod: `src/editor/production/film/`, uçlar `production/api_film.py`,
video servisi `images/video/`. Testler `tests/test_film.py` (modelsiz).

## Tek hat, üç biçim

| Biçim | Oran | Süre | Altyazı | Kanca | Ses düzeyi |
|---|---|---|---|---|---|
| `cizgi-film` | 16:9, 1920×1080 | 60–600 sn | ayrı .srt | — | −16 LUFS |
| `fragman` | 16:9 | 45–120 sn | ayrı .srt | ilk 5 sn | −14 LUFS |
| `reels` | 9:16, 1080×1920 | 15–90 sn | görüntüye basılı + .srt | ilk 3 sn | −14 LUFS |

Üslup: 2B çizgi film, 3B animasyon, suluboya, gerçekçi (`spec.STYLES`). Paylaşım kesitleri bitmiş filmden alınır:
Instagram Reels, TikTok, YouTube Shorts, YouTube, Instagram kare (`spec.PLATFORMS`); oran farklıysa bulanık dolgu.

## Adımlar ve onaylar

| # | Adım | Ne yapar | Model (gateway) | Onay |
|---|---|---|---|---|
| 1 | senaryo | Kitap özetinden çekim listesi; her çekim kitaptan birebir cümleye bağlı | `book-director` | editör |
| 2 | oyuncular | Karakter → onaylı kart (görünüş + referans) ve katalogdan ses | — | editör |
| 3 | ses | Replikler duygusuyla okunur; çekim süresi gerçek ses süresine uzar | `book-voice` | — |
| 4 | kareler | Her çekimin ilk karesi, karakter referansıyla; görsel denetçi | `book-image`, `book-vision-fast` | editör |
| 5 | çekim | İlk kare hareketlenir; tek konuşanlı yakın planda ağız sese uyar | `book-video` (KAPALI) | — |
| 6 | kurgu | Sahne müziği (+ isteğe bağlı tema şarkısı), sonra çekim + replik + efekt + ortam + müzik; kısma; ses düzeyi; altyazı | `book-director` (müzik ipucu), `book-music` (KAPALI) + ffmpeg | editör |
| 7 | paylaşım | Platform kesitleri, kapak karesi, açıklama + etiket taslağı | `book-director` | editör |

Bir adım yeniden üretilince sonraki adımlar «eski» olur (`store.set_stage`). Onaysız paylaşım paketi indirilemez.
Otomatik paylaşım yoktur (dış gönderim kapalı).

## Kurallar (kitaptan bağımsız)

- Çekim 2–10 sn. Uzun sahne art arda çekimdir. Replik süresi: 2,4 kelime/sn tahmini, gerçek süre sesten.
- Senaryo denetimi (`spec.check`): toplam süre biçim aralığında, çekim süresi sınırda, konuşan/görünen oyuncu
  listesinde, replik çekime sığıyor, görüntü tarifi dolu. Ölümcül sorun → senaryo sorunlarıyla yeniden istenir
  (en çok 3). Kitapta bulunamayan alıntı ölümcül değil, editöre «kanıtsız» gösterilir.
- Duygu → Sesli Okuma'nın ölçülmüş ifade tablosu (`expression.TABLE`); yeni ton ölçülmeden eklenmez. Bağırma =
  öfke hızı + kazanç.
- Ses seçimi: yaş + cinsiyet + rol kelimesi → `voices_zeki` katalogu; aynı ses iki ana karaktere verilmez. Katalogda
  çocuk sesi yok: çocuk karakter genç sesle okunur.
- Görsel denetçi kareyi reddederse yeni tohumla en çok 2 kez yeniden çizilir; çekim için üç örnek karede bakılır,
  bir kez yeniden çekilir. Yine geçmeyen editörün önüne «denetimden geçmedi» notuyla gelir.

## Video servisi sözleşmesi (`images/video/server.py`)

`POST /v1/video/generations` `{model: book-video, mode: i2v|s2v, image, prompt, negative_prompt, seconds, width,
height, seed, audio?, steps?, engine?: wan2.2|h3|fast-h3|fast-h3-fp8, refs?: [png b64]}` → `{video, seconds, fps,
frames, engine}` (+ H3'te `canvas`, `steps`, `refs_used`; FastH3'te `first_frame_used: false`). `engine` yoksa servisin `VIDEO_ENGINE`'i — varsayılan **`h3`**
(kullanıcı kararı 2026-10-07: h3 birinci, `fast-h3` hızlı kip, `wan2.2` yedek); istemci yalnız `EDITOR_VIDEO_ENGINE`
verilmişse gönderir. `refs` karakter kartlarıdır (en çok 8), istemci yalnız s2v'de yollar. `VIDEO_LICENSED_ENGINES`
ile kapatılmış motor **409** döner (aşağıda).

`POST /v1/video/enhance` `{model, video: mp4 b64, target: 1080p|4k, fps: 24|30}` → `{video, width, height, fps,
engine}`.

### Motorlar

| Motor | Kod (sabit commit) | Ağırlık | i2v | s2v |
|---|---|---|---|---|
| `wan2.2` | Wan2.2 `1ea34ff4` | `i2v/`, `s2v/` | I2V-A14B, 16 fps, 81 karelik parçalar son kareden sürer | S2V-14B, ses sürdürür |
| `h3` | diffusers `c6df88a5` (`ModularPipeline`, MiniMax-H3) | `h3/` | `fl2va`: ilk kare tuvale bağlı | `ref2va`: ilk kare + kartlar + replik izi |
| `fast-h3` | FastVideo `d1416b59` (`VideoGenerator`) | `fast-h3/` (V2 bf16) + `h3/` ortak parçalar | `t2va` (ilk kare girmez), 8 ileri geçiş | yok → 422 |
| `fast-h3-fp8` | FastVideo `d1416b59` | `fast-h3-fp8/` (V2-FP8, tam depo) | `t2va` | yok → 422 |

Her motor ayrı süreçte (worker_*.py). Üç Python ortamı, çünkü sabitlemeler çakışıyor: ana (Wan; transformers ≤4.51.3),
`/opt/h3` (diffusers H3 + SeedVR2 + RIFE; transformers ≥4.57), `/opt/fastvideo` (FastVideo: torch 2.12, transformers
≥5.15, Python 3.12, fastvideo-kernel 0.3.5). Kartta aynı anda tek işçi; başka motor istenince süreç kapanır, GPU/CPU
belleği onunla boşalır. Hesap kuralları (kare sayısı, tuval, lisans, iyileştirme bayrakları) `images/video/plan.py`'de,
torch'suz ve testli.

**H3 kaynaktan çıkarılan sözleşme** (diffusers `docs/.../pipelines/minimax_h3.md`, `modular_pipelines/minimax_h3/`):
24 fps; kare sayısı 17n+5'e yukarı yuvarlanır ve *yuvarlanmış* süre 5–15 sn olmalı → 124–345 kare; 5 sn'den kısa çekim
124 kare üretilip istenen süreye kesilir. Tuval kısa kenar 768, alan tavanı 768×1344, eksenler 32'nin katı (16:9 →
1344×768, 9:16 → 768×1344). Ağırlık CFG-damıtılmış: negatif istem/guidance yok; adım 50 (`H3_STEPS`). Görüntü ve 32 kHz
stereo ses birlikte üretilir. Model kartı Context-IR (istem genişletici) ve Regenerate-2K'yı açık kaynak vermiyor (yalnız
ücretli API); onların yerine `plan.h3_prompt` rehberdeki bölüm biçimini (integrated_multimodal_description /
subject_definitions / retention_analysis …) sade kalıpla kurar. FL2VA/Ref2VA özgün bölümleri indirilmedi; diffusers
biçimi (`transformer/` = t2va/fl2va, `transformer_ref/` = ref2va, ortak VAE/ses VAE/Qwen3-VL-32B) yeterli.

**Ses ve dudak:** H3'ün ürettiği ses her motorda atılır; filmin sesi bizim Türkçe replik izimizdir. Dudak uyumu:
- `h3` s2v → `ref2va`: <Picture 1> ilk kare, <Picture 2…> kartlar, <Audio 1> replik izi `fully_copy` (rehber: «the
  complete source audio serves as the target video's complete final audio track»). Ağız bu sese göre üretilir; uyum
  modelin istemi izlemesine bağlıdır (koşul, zorlama değil). ref2va ilk kareyi tuvale **bağlamaz** — yalnız istemde
  «first frame» denir; kare kayması olabilir, ölçülecek.
- `fast-h3` / `fast-h3-fp8`: dudak uyumu yok (aşağıda); konuşan çekim için `h3`. Not: ComfyUI'de
  `MiniMaxH3AddGuide(audio, frame_idx=0)` ile fl2va'ya ses çıpası vermek mümkün (tam H3 ağırlığıyla); bu yol
  kurulmadı, diffusers'ta fl2va'ya ses çıpası yok.
- Türkçe H3'ün «kararlı 11 dil» listesinde değil («diğer diller değişen ölçüde»); `<d>[Turkish] …</d>` diyalog metni
  sözleşmede olmadığı için istemde yazılmaz. Dudak uyumu ilk kurulumda gözle ve ölçüyle değerlendirilecek.

**FastH3 V2 (FastVideo resmî yolu):** `FastVideo/FastVideo-FastH3-8-Step-V2` (diffusers düzeni; indirme yalnız
transformer + yapılandırma, ortak parçalar MiniMax-H3 ile birebir — 34/34 özet) ve `…-V2-FP8` (transformer FP8 E4M3
kanal başı, Qwen3-VL NVFP4 → FP4'süz kartta katman başı açılır, LynnReal hafif VAE; tam depo). İşçi
examples/inference/basic/basic_fasth3.py'nin `build_generator_config`/`build_request`'ini tek kart için kurar
(num_gpus 1, FSDP yok, Qwen3-VL ve VAE CPU'ya iner, transformer kartta; `FAST_H3_DIT_LAYERWISE=1` katman katman
indirme), ortam «strict» profil + Triton VSA (Hopper'da sm100a çekirdeği ve FA4 yok; kart: `--vsa-kernel triton
--no-fa4`), VSA seyreklik 0,8 / döşeme 64, 9 sigma noktası (= 8 ileri geçiş; kayma 10/3 ve DMD basamakları
`fastvideo_inference.json`'dan). V2 klasörü `basic_fasth3_omniref_pdd.py` `compose_model_dir` desenindeki gibi
sembolik bağlarla MiniMax-H3 ortak parçalarıyla birleştirilir.

**FastH3 V2 kapsam sınırı (model kartı «Scope»):** «This checkpoint supports text-to-audio-video generation. FL2VA and
Ref2VA were not distilled.» FastVideo yemek kitabı da CUDA'da FL2VA/Ref2VA'yı yalnız tam H3 için listeler. Sonuç:
`fast-h3` i2v'de **onaylı ilk kare modele girmez** (t2va; karakter/sahne tutarlılığı yalnız istemle), s2v desteklenmez
(422 → editöre Türkçe hata). Yani hızlı kip ön izleme/taslak içindir; editörün onayladığı kareden film için `h3`.
(Eski FastVideo-FastH3-Comfy v1 paketi — ComfyUI'nin «pruned» biçimi — artık kullanılmıyor; klasör kurulumda taşınmaz.)

**V2 için tek H100'de beklenen süre (ölçülmedi; kaynaktaki ölçümlerden tahmin):** FastVideo'nun kayıtlı Hopper
ölçümleri FastH3 *Preview* (4 ileri geçiş) içindir: 8×H100 1344×768 345 kare (14,4 sn) 13,5 sn; 4×H100 NVLink 960×544
345 kare 13,0–14,0 sn (examples/inference/basic/README.md «Hopper»). V2 8 ileri geçiş yapar (2×). Kusursuz ölçekleme
varsayımıyla tek kart: 960×544 / 14,4 sn video ≈ 4 × 13,5 × 2 ≈ **~110 sn**, 1344×768 ≈ 8 × 13,5 × 2 ≈ **~215 sn**;
tek kartta dizi paralelliği iletişimi olmadığı için biraz daha iyi, kodlayıcı/VAE CPU'dan gidip geldiği için (her
istekte ~62 GB kodlayıcı taşınır) birkaç on saniye daha kötü. 5 sn'lik (124 kare) çekim dikkat karesel olduğundan
bunun ~⅓'ünden az: 960×544'te **~30–40 sn** mertebesi. FP8 sürümü bellek için; Hopper FP8 matmul ile hız kazancı
beklenir ama ölçümü yok. Kart, 66 GB bf16 DiT'in 80 GB H100'e çoğaltılarak sığmadığını yazıyor; 94 GB H100 NVL'de
kodlayıcı CPU'da iken sığması bekleniyor — sığmazsa `FAST_H3_DIT_LAYERWISE=1` ya da `fast-h3-fp8`.

### Tek kart (H100 NVL 94 GB, 2 TB RAM) planı

Resmî öneri 4 GPU (SGLang `--num-gpus 4 --ulysses-degree 4`). Transformer 61,7 GB + Qwen3-VL-32B 62,1 GB bf16 aynı
anda sığmaz. Diffusers'ın kendi «tek 80 GB kart» tarifi uygulanır: bütün bileşenler CPU belleğinde,
`ComponentsManager.enable_auto_cpu_offload(device="cuda", memory_reserve_margin="12GB")` her bileşeni sırası gelince
karta alır, yer gerekince ötekini indirir (önce kodlayıcı çalışır, sonra transformer kartta kalır). İki transformer
bölümü (fl2va + ref2va) birlikte CPU'ya yüklenir (~186 GB RAM). FP8/int8 gerekmez; 94 GB kartta 62 GB transformer +
etkinlikler sığar. Gerekirse kaynakta iki seçenek: torchao `Int8WeightOnlyConfig(version=2)` + blok düzeyi grup
indirme (tüketici kart tarifi) ve `set_attention_backend("_flash_3_hub")` (Hopper ~3×, çekirdek Hub'dan iner;
`H3_ATTENTION`). Hız kolu tuvaldir: 960×544, 1344×768'e göre adım başına ~2,3× hızlı (diffusers belgesi). FastH3 V2:
yukarıda. ÖLÇÜLMEDİ: açılış, bellek tepesi, çekim başı süre.

### Lisans (MiniMax H3 Community License — `h3` ve `fast-h3`)

- **IV.1:** yıllık geliri 20 M $'ı aşan ticari ürün/hizmet için MiniMax'ten önceden yazılı izin şart (api@minimax.io,
  konu «MiniMax H3 licensing - authorization request»). Kullanıcı 2026-10-07: «kurumlarımızın hepsinin lisansı var»
  (MiniMax H3 dahil).
- **IV.2:** H3 kullanan ticari ürünün arayüzünde «MiniMax H3» adı belirgin gösterilmeli. Bu, «ekranda teknoloji adı
  yok» kuralıyla çelişir; **ekran kararı kullanıcının** — kod ekrana ad yazmaz, yanıttaki `engine` alanı
  (`minimax-h3-…`, `fasth3-…`) kayda girer, ekran isterse oradan gösterir.
- **I.3/I.5, V.4:** lisans Avrupa Birliği, Birleşik Krallık, Kore ve ABD dışında geçerli; H3 çıktısı bu bölgelerde
  kullanılamaz/gösterilemez — sosyal medya paylaşımının bu bölgelerden izlenmesi hukuken sorulmalı.
- **V.2/V.5:** kullanıcılar kabul edilebilir kullanım koşullarına bağlanmalı, ihlal bildirim yolu tutulmalı.
- Kod kapısı: `VIDEO_LICENSED_ENGINES` verilmezse üç motor da açık. Verilirse yalnız listedekiler açılır (örn.
  `wan2.2` yazmak H3 ve FastH3'ü kapatır, istek 409 döner); `wan2.2` (Apache-2.0) her zaman açık. SeedVR2
  (Apache-2.0) ve RIFE (MIT) serbest.
- FastH3 V2 / V2-FP8 MiniMax H3 Community License'ı devralır (model kartı); FastVideo kodu Apache-2.0.

### İyileştirme (SeedVR2 + RIFE)

Kurgu öncesi her seçili çekim bir kez iyileştirilir: çekim adımının sonunda `shoot.enhance_selected` (kurgu GPU
adımı değil, model geçişi çekim adımında kalsın diye) → `cekim/<id>.vK.hd.mp4`, sürüm kaydında `hd {file, width,
height, fps, engine, target}`. Kurgu (`mix.pick_videos`) hd varsa onu alır; yoksa ham çekim lanczos ile ölçeklenir.
Kaç çekimin iyileştirildiği film.json'da kurgu adımına `enhanced: n/toplam` (çekim adımına da, hata nedeni
`enhance_error`), başarısız sürümde `hd_error`. Servis yoksa kalan çekimler denenmez; bir sonraki çekim koşusu
(çekilecek çekim olmasa da) eksikleri yeniden dener. `EDITOR_FILM_ENHANCE=0` kapatır, `EDITOR_FILM_ENHANCE_TARGET`
(1080p | 4k, varsayılan 1080p — çıktı biçimi 1080p).

- **SeedVR2 7B sharp:** `seedvr2_ema_7b_sharp_fp16.safetensors` + `ema_vae_fp16.safetensors` (numz/SeedVR2_comfyUI).
  Bu dosyaları yükleyen kod numz/ComfyUI-SeedVR2_VideoUpscaler (`model_registry.py:49,52`, sha256 kayıtlı);
  ByteDance-Seed/SeedVR'ın resmî betikleri `.pth` yükler, bu dosyalarla çalışmaz. Paketin kendi CLI'ı çağrılır:
  kısa kenar 1080/2160, parti 4n+1 (en çok 33, çekim kısaysa çekim boyu), `--uniform_batch_size --temporal_overlap 3
  --color_correction lab`, 4K'da VAE döşeme + CPU'ya indirme.
- **Practical-RIFE 4.26** (2024-09-21; README: «4.24+ … diffusion model generated videos» için uygun): ağırlık
  Google Drive'dan (HF'de yok) `/data/editor/models/RIFE/4.26/train_log` (flownet.pkl 24,6 MB, IFNet_HDv3.py,
  RIFE_HDv3.py; zip sha256 `c2452dd2…`, `__MACOSX`/`._*` silindi; model içindeki sürüm alanı 4.25). Kat: kaynak ≥ hedef
  ise RIFE yok; değilse tam bölünen en küçük kat (16→24: 3 kat, 2'de bir kare), yoksa en küçük kat + kare hızı
  süzgeci (24→30: 2 kat → 30). 4K'da `scale 0.5`.

### Ağırlık klasörü (kurulumda `/data/editor/models/book-video/` altına taşınır)

    i2v/       ← Wan2.2-I2V-A14B          s2v/   ← Wan2.2-S2V-14B
    h3/        ← MiniMax-H3 (FL2VA/ Ref2VA/ hariç; fast-h3 ortak parçaları buradan alır)
    fast-h3/   ← FastH3-V2 (transformer/, scheduler/, audio_scheduler/, fastvideo_inference.json, modular_model_index.json)
    fast-h3-fp8/ ← FastH3-V2-FP8 (tam depo)
    enhance/seedvr2/  ← SeedVR2/{seedvr2_ema_7b_sharp_fp16, ema_vae_fp16}.safetensors
    enhance/rife/     ← RIFE/4.26/train_log

## Müzik (2026-10-07)

Kullanıcı kararı: «en iyi açık kaynak»; kurumun bütün motorlar için lisansı var (2026-10-07). Kod
`production/film/music.py`, servis `images/music/` (`editor-music:1`), gateway takma adı `book-music`
(`POST /v1/audio/music`, `PASSTHROUGH` `audio/music`; `models.yaml`'da YORUM SATIRI), indirme `deploy/muzik/`.

| İş | Sıra | Motor (anahtar) | Lisans | Ağırlık |
|---|---|---|---|---|
| Sözsüz sahne müziği | 1 | Stable Audio 3.0 Medium (`stable-audio-3`) — tempo, ton, süre tutar | Stability AI Community License (+ Gemma Terms, metin kodlayıcı) | HF kapılı: anahtar bekleniyor |
| | 2 | ACE-Step 1.5 XL-SFT (4B DiT) + LM 4B (`acestep15`) — tempo/ton istenmez | MIT | indiriliyor |
| | 3 | YuE2 sözsüz kipi (`yue2`) | CC BY-NC 4.0 (+ kurum lisansı) | indiriliyor |
| Tema şarkısı | 1 | YuE2-3B + YuE2-Vae (`yue2`) — WildSongBench 6,73, PER %8,4 | CC BY-NC 4.0 (+ kurum lisansı) | indiriliyor |
| | 2 | MiniMax Music 3 (`minimax-music3`) — PER %6,3 (açıklar içinde en düşük) | MiniMax-Music3 Community License | indiriliyor |
| | 3 | HeartMuLa-oss-3B happy-new-year + HeartCodec (`heartmula`) — 6,25, PER %10,7 | Apache-2.0 | indiriliyor |

İstekte `engine` yoksa servis kurulu ve açık ilk motoru seçer; `MUSIC_DISABLED_ENGINES` (virgüllü) bir motoru kapatır.
ACE-Step şarkıyı yalnız açıkça istenirse yapar. Türkçe söz hiçbir motorda belgelenmedi: ilk kurulumda üç şarkı motoru
aynı Türkçe sözle karşılaştırılıp sıra gerekirse değişir. ACE-Step varyantı modelin kartından: XL-SFT «Highest
Quality» (50 adım, CFG), XL + 4B LM «Full quality»; turbo/base alınmadı. HeartMuLa sürümü heartlib README'sinden:
happy-new-year «best open-sourced… lyrics controllability and music quality» (RL-20260123 değil).

**Lisans koşulları (kullanımda uyulacak):**
- Stable Audio 3: Stability AI Community License — yıllık geliri 1 M $ üstü kurum için kurumsal (Enterprise) lisans
  şart (kurumun lisansı var, kullanıcı beyanı). Metin kodlayıcı Gemma Terms of Use (kullanım kısıtları §3.2) ile
  dağıtılır. Depo kapılı olduğundan LICENSE.md henüz okunamadı; atıf koşulu indirilince oradan doğrulanacak.
- YuE2: CC BY-NC 4.0 — atıf (eser sahibi, lisans bağlantısı, değişiklik belirtme); ticari kullanım kurumun ayrı
  lisansına dayanır. Üçüncü taraf kod lisansları (SnakeBeta NVIDIA-MIT, stable-audio-tools MIT) klasördeki licenses/.
- MiniMax Music 3: MiniMax-Music3 Community License — ticari üründe arayüzde «MiniMax-Music3» adının belirgin
  gösterilmesi şart (madde 3.1; projenin «ekranda teknoloji adı yok» kuralıyla ÇELİŞİR — kurumun lisansı bu maddeyi
  kaldırmıyorsa kullanıcı kararı gerekir); yıllık gelir 20 M $ üstünde MiniMax'ın yazılı izni; kötüye kullanıma karşı
  önlem yükümlülüğü (madde 4) ve Kabul Edilebilir Kullanım Politikası (Ek A).
- ACE-Step 1.5: MIT — telif bildirimi ve lisans metni korunur (klasörde LICENSE, kod deposundan sabit commit).
  Model kartı: üretilen müzik ticari kullanılabilir.
- HeartMuLa: Apache-2.0 — LICENSE korunur, değişiklik belirtilir (klasörde LICENSE, heartlib sabit commit).

Ağırlıklar `/data/editor/models/book-music/<anahtar>` (sabit revizyon ve bayt `_indirme/muzik-durum.json`). Stable
Audio 3 için: HF'de şartları kabul edip okuma anahtarını `/data/editor/secrets/hf-token`'a koyun (gpuubuntu
okuyabilmeli), sonra `sh /data/editor/models/_indirme/muzik_baslat.sh` — biten modeller atlanır.

Akış (kurgu adımının parçası; `store.STAGES` değişmedi, ekran bozulmaz):

1. **Sahne planı** (modelsiz, `music.scene_plan`): sahne başlangıcı ve süresi kurgu zaman çizelgesiyle aynı hesap.
2. **Müzik ipucu** (`book-director`, istem `production_film_music` v1): sahne başına İngilizce sözsüz tarif, tempo,
   ton, Türkçe duygu etiketi, `music: false` ile sessiz sahne; istenirse (`theme_song: true`) Türkçe tema şarkısı
   sözü + tarzı (okur yaşına göre, kitaba özel kural yok). Girdinin özeti aynıysa yeniden istenmez.
3. **Üretim**: sahne süresi + 2 sn (çapraz geçiş payı) kadar `kind: score`; tema şarkısı `kind: song` (120 sn
   istenir). Aynı tarif+süre yeniden üretilmez; sahne hatası filmi düşürmez (muzik.json'da `error`). İş bitince model
   gateway iç ucuyla kapatılır.
4. **Kurgu** (`mix.py`): müzik ayrı bir bus; sahne parçası sınırda XFADE/2 taşar, komşu müzikli sahneyle 2 sn çapraz
   geçer, film başı/sonu 1,5 sn açılış/kapanış; parça kısa gelirse döngü, uzunsa kesilir (ACE-Step tempo/süre
   tutmasına güvenilmez). `MUSIC_DB` −17 dB, konuşmada ayrıca `MUSIC_DUCK` sidechain (efektten yavaş geri açılır).

Servis yoksa (takma ad listesinde değil ya da 404) müzik sessizce atlanır, komut müziksiz kurguyla birebir aynıdır.
Kayıt: `<film>/muzik/s<NN>.wav`, `muzik/tema.wav`, `muzik.json`; `kurgu.json` ve film.json'un kurgu adımında
`music: "var" | "yok"`. Tema şarkısı filme karıştırılmaz (ayrı dosya; medya ucundan `muzik/` dinlenir). Uç: kurgu
başlatma gövdesinde `theme_song`. Ekranda motor/teknoloji adı geçmez.

ÖLÇÜLMEDİ / DOĞRULANMADI: motorlar GPU'da hiç koşturulmadı (çağrılar kaynak belgelerden; ayrıntı
`images/music/worker.py` başı); Türkçe söz kalitesi; açılış süresi, bellek tepesi (pay 0.40 tahmin); Stable Audio 3
`model_config.json`'ındaki metin kodlayıcı yolunun yerel kopyaya yönlendirilmesi (depo kapılı, dosya okunamadı);
ACE-Step'in salt okunur checkpoint klasöründe çalışması (/tmp gölge klasörüyle çözüldü, denenmedi).

## Henüz yapılmayan (bilerek)

- **Modeller ayağa kaldırılmadı** (kullanıcı kararı 2026-10-04). `models.yaml`'daki `book-video` bloğu yorum
  satırıdır; çekim adımı başlatılırsa «Video üretimi bu kurulumda henüz açık değil» döner. Açma sırası: ağırlıkları
  `/data/editor/models/book-video/{i2v,s2v}` altına taşı → MANIFEST'e sha256 → `editor-video:1` derle → bloğu aç →
  açılış süresi, bellek tepesi, çekim başı süre ölç ve buraya yaz.
- Video servisi kodu GPU'da hiç çalıştırılmadı (2026-10-07'de de; kullanıcı kararı): Wan, H3 (diffusers), FastH3
  V2 (FastVideo), SeedVR2 CLI ve RIFE çağrıları kaynak kodla satır satır eşlendi (her işçinin başındaki belge), ilk
  kurulumda doğrulanacak. İmaj `editor-video:1` GPU'da derlendi, içe aktarma denetimi GPU'suz yapıldı.
- «MiniMax H3» adının ekranda gösterimi (lisans IV.2) yapılmadı — kullanıcı karar verecek.
- Müzik servisi ayağa kaldırılmadı (`book-music` yorum satırı); kurgu o güne dek müziksizdir. Efekt ve ortam sesi
  GPU'daki telifsiz efekt havuzundan.
- Portal ekranı ve köprü vekili yok (sonraki adım).
