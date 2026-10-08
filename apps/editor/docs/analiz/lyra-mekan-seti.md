# Mekân seti: NVIDIA Lyra 2.0 ile çekimden çekime tutarlı arka plan

2026-10-08. Kullanıcı kararı: Lyra 2.0 çizgi film hattına «mekân seti» olarak girecek. Bu belge hazırlıktır:
ağırlık ve kod GPU sunucusuna indirildi, **model hiç yüklenmedi, çıkarım koşturulmadı**. Kod yazılmadı; aşağıdaki
entegrasyon bir plandır. Bütün süre/bellek rakamları NVIDIA'nın belgesinden ya da tahmindir — «ölçüldü» yazmayan hiçbir
rakam ölçülmedi.

## Sorun

Bugün her çekimin ilk karesi `frames.py`'de metinden (ya da karakter kartlarıyla düzenlemeden) ayrı ayrı çizilir.
Aynı sahnenin (aynı `setting`) çekimlerinde oda her seferinde başka çıkar: pencere yer değiştirir, yatak rengi değişir,
kapı kaybolur. Karakter kartı karakteri sabitliyor; mekânı sabitleyen bir şey yok.

## Lyra 2.0 nedir

| | |
|---|---|
| Proje | https://nv-tlabs.github.io/Project-Lyra/ — makale arXiv 2604.13036 |
| Kod | https://github.com/nv-tlabs/lyra (`Lyra-2/` alt klasörü) |
| Ağırlık | https://huggingface.co/nvidia/Lyra-2.0 (kapısız) |
| Temel model | Wan 2.1 14B (görüntüden videoya, 480P) üstüne kamera denetimli, uzun ufuklu (FramePack tarzı parça parça, mekânsal bellekli) eğitim |
| Girdi | tek görüntü + kamera yolu (`trajectory.npz`) + kare indeksine bağlı metin (`captions.json`) |
| Çıktı | 1) kamera yolunda yürüyen video (mp4, 16 fps, varsayılan 480×832) 2) bu videodan 3B Gauss bulutu (`reconstructed_scene.ply`) ve yol boyunca render (`gs_trajectory.mp4`) 3) belgede mesh ve fizik motoruna aktarım da gösteriliyor (mesh betiği depoda ayrı değil, DA3 çıktısından) |
| Hızlandırma | `--use_dmd`: 4 adımlı DMD LoRA (`checkpoints/lora/dmd_distillation.safetensors`); belge: ~15× hızlı, «istem takibi zayıflayabilir, tekrarlayan desen çıkabilir» |
| Ek LoRA | `detail_enhancer`, `realism_boost` (`--lora_paths/--lora_weights`) — `realism_boost` çizgi filmde kullanılmamalı |

### Akış (depodaki betikler)

1. **Video**: `python -m lyra_2._src.inference.lyra2_custom_traj_inference --input_image_path first.png
   --trajectory_path trajectory.npz --captions_path captions.json --experiment lyra2 --checkpoint_dir checkpoints/model
   --num_frames N --resolution 480,832 [--use_dmd]`. İlk görüntünün derinliği/iç parametresi MoGe (+ DA3) ile
   çıkarılır, kamera yolu bu ölçeğe oturtulur (`--pose_scale 1.1`). Hazır yol isteyenler için
   `lyra2_zoomgs_inference` (içeri/dışarı yakınlaşma, `--num_frames_zoom_in/out`).
2. **3B**: `python -m lyra_2._src.inference.vipe_da3_gs_recon --input_video_path video.mp4` → ViPE ile poz
   (GeoCalib iç parametre + UniDepth-L anahtar kare derinliği), Lyra'nın kendi DA3 ağırlığı (`checkpoints/recon/model.pt`)
   ile Gauss bulutu (gsplat), `reconstructed_scene.ply` + render. Uzun video: `vipe_da3_chunked_gs_recon`.
3. **GUI** (`gui/`): etkileşimli kamera çizimi + Qwen3-VL-4B ile otomatik altyazı. Bizim hatta gerekmez (altyazıyı
   senaryo verir); indirilmedi.

### Kamera yolu biçimi

`trajectory.npz`: `w2c` (N×4×4 dünya→kamera, OpenCV ekseni), `intrinsics` (N×3×3 piksel), `image_height`,
`image_width`. `captions.json`: `{"0": "...", "81": "..."}` — her otoregresif parça (80 kare) anahtarı ≤ kendi başlangıç
karesi olan metni kullanır. Örnek: `kod/Lyra-2/assets/custom_trajectory_examples/example_0/`.

### Kurulum gereksinimi (INSTALL.md)

Ubuntu 22.04, CUDA 12.8, Python 3.10, torch 2.7.1 / torchvision 0.22.1 (cu128), gcc/g++ 13.3, Transformer Engine
(pytorch), flash-attn 2.6.3 (kaynaktan), MoGe (git), ViPE (depodaki alt modül, CUDA eklentisi derlenir,
`USE_SYSTEM_EIGEN=1`), Depth Anything 3 `[gs]` (alt modül; gsplat sabit commit 0b4dddf). Yazarlar conda kullanıyor;
biz imajda conda'sız yapacağız (aşağıda). Ortam: `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`.

### Bellek ve süre (belgeden; ÖLÇÜLMEDİ)

- Video: 1× H100 80GB'da 80 kare ≈ 9 dk (35 adım), DMD ile ≈ 35 sn. Belge en az belleği vermiyor; 14B DiT bf16
  (~28 GB) + umT5-XXL kodlayıcı (11 GB) + CLIP görüntü kodlayıcı (2,4 GB) + DA3-Giant + MoGe birlikte tutuluyor →
  tahmin 60–75 GB tepe. `--offload` / `--offload_when_prompt` / `--offload_da3_diffusion` bayrakları var.
- 3B kurma: ≈ 1 dk (ViPE + DA3 + render).
- Bizim kartlar H100 NVL 94 GB; kart başına video modeli 0.90 payla çalışıyor → Lyra o kartın tek sahibi olmalı
  (gateway diğer editör modellerini durdurur; çekim sürerken mekân seti kurulamaz, sıra beklenir).

## Lisans

- **Kod**: Apache-2.0 (depo kökü ve `Lyra-2/LICENSE`).
- **Model ağırlıkları (nvidia/Lyra-2.0)**: «NVIDIA Internal Scientific Research and Development Model License».
  Adı üstünde iç araştırma-geliştirme lisansı; ticari/üretim kullanımı bu lisansla kapsanmaz, NVIDIA Research
  Licensing üzerinden ayrı lisans gerekir. Kullanıcı kurumda lisans olduğunu söyledi (eleme ölçütü değil); **koşul
  kayda geçsin diye**: üretimde kullanılan sürümün NVIDIA ile yapılmış ticari lisansla kapsandığı belgelenmeli.
- **Temel model** Wan 2.1: Apache-2.0.
- **Çalışma anı bağımlıları**: `depth-anything/DA3NESTED-GIANT-LARGE-1.1` **CC-BY-NC-4.0** (ticari değil; Lyra
  kendi `recon/model.pt`'sini yükler, DA3NESTED yalnız mimari/yedek ağırlık olarak çağrılıyor — imajda gerçekten
  okunup okunmadığı ilk denemede bakılmalı); `DA3METRIC-LARGE` Apache-2.0; `Ruicheng/moge-vitl` MIT;
  `lpiccinelli/unidepth-v2-vitl14` (kartta lisans alanı boş; UniDepth deposu CC-BY-NC-4.0); `google/umt5-xxl`
  (yalnız tokenizer) Apache-2.0; GeoCalib ağırlığı Apache-2.0; DINOv2 Apache-2.0.

## İndirilenler (tt-gpu)

Hepsi `/data` altında; sistem diskine yazılmadı. İndirme `lyra2-indir` adlı konteynerde (`vllm/vllm-openai:v0.29.0`
imajı yalnız `huggingface_hub` için; `--restart no`, salt okunur kök, kullanıcı 1000, günlük sürücüsü kapalı),
kopmaya dayanıklı (hata → bekle → kaldığı yerden), sabit revizyon.

| Ne | Yer | Revizyon | Boyut |
|---|---|---|---|
| Kod | `/data/editor/models/Lyra-2/kod` (alt modüller dahil) | lyra `9fffc9adc37004091ecf26ef03abfb3abdf4d59a` (2026-07-20); vipe `b7cac64616763bc755009db79a1815c7cdc9b130`; Depth-Anything-3 (frankshen07 çatalı) `1ed6cb8eee386a3c94077d907b09c7aa1c312cd8`; salad `6aede13a3f6c` | 1,5 GB |
| Lyra 2.0 ağırlık | `/data/editor/models/Lyra-2/checkpoints/` (`model/` 32 distcp parçası ~68 GB, `text_encoder` 11,4 GB, `recon` 13,4 GB, `image_encoder` 2,4 GB, `lora/` 1,1 GB, `vae` 0,5 GB) | HF `c178c3fcf12b63cf98f6749999e6ecb63901669f` | ~97 GB (eğitim örnekleri `assets/training_data` alınmadı) |
| MoGe, UniDepth-v2-L, umT5 tokenizer, DA3METRIC-L, DA3NESTED-Giant-L-1.1 | `/data/editor/models/Lyra-2/hf/hub` (HF önbellek biçimi; çalışırken `HF_HOME=/data/editor/models/Lyra-2/hf`, `HF_HUB_OFFLINE=1`) | sırasıyla `ad326bfb…`, `52b349b5…`, `66cb9e7e…`, `4010e39f…`, `b2359bdf…` | ~12 GB |
| torch.hub dosyaları | `/data/editor/models/Lyra-2/torch-hub/` (`geocalib/pinhole.tar`, `checkpoints/dinov2_vitl14_reg4_pretrain.pth`; çalışırken `TORCH_HOME`'un `hub`'ı bu klasör) | GeoCalib v1.0, DINOv2 | ~1,7 GB |

Durum (2026-10-08 15:40): kod ve GeoCalib tamam; DINOv2 ve Lyra ağırlığı iniyor (~11 MB/s, HF anahtarsız →
Lyra için ~2,5 saat), ardından bağımlı HF modelleri. Bitişi `durum.json`'da her parçanın `"ok": true` olmasından ve
günlükteki «HEPSI BITTI»den anlaşılır; konteyner kendiliğinden çıkar (silinmez).

Betik ve günlük: `/data/editor/models/_indirme/lyra2/indir.py`, `indir.log`, `durum.json` (bitince her parça için
repo, revizyon, bayt). MANIFEST'e sha256 kaydı kurulumda yazılır (book-video düzeni).

## Entegrasyon planı

### 1. İmaj: `apps/editor/images/scene3d/`

- `Dockerfile`: `pytorch/pytorch:2.7.1-cuda12.8-cudnn9-devel` tabanı (ViPE CUDA eklentisi, flash-attn ve gsplat
  derlenecek → devel şart; derleme GPU sunucusunda, `TORCH_CUDA_ARCH_LIST=9.0`). Kod `git clone` + yukarıdaki sabit
  commit'ler + `git submodule update --init` (yalnız `vipe`, `depth_anything_3`; GUI bağımlıları alınmaz), `.git` silinir.
  Kurulum sırası INSTALL.md'deki gibi: requirements.txt → MoGe (sabit commit) → transformer-engine[pytorch] →
  flash-attn 2.6.3 `--no-build-isolation` → `pip install -e vipe` → `pip install -e depth_anything_3[gs]`. Derleme
  sonu denetimi INSTALL.md'nin içe aktarma satırı (GPU'suz yapılabilen kısmı). `HF_HUB_OFFLINE=1`.
- `server.py` (FastAPI, book-video/upscale gibi tek kilitli işçi; model istek arasında bellekte kalır):
  - `GET /health`
  - `POST /v1/scene3d/build` — `{image (b64), prompt, set_id, style, frames, dmd: bool, seed}` → kamera yolunu
    kendisi üretir (aşağıda «Set yolu»), Lyra videosu + `vipe_da3_gs_recon` → `{ply (b64 ya da sunucu yolu), video,
    cameras: {görünüm_adı: {w2c, K}}, took}`. Uzun iş (dk'lar): gateway zaman aşımı `start_timeout_sec`/istek
    zaman aşımı book-video'daki gibi uzun.
  - `POST /v1/scene3d/render` — `{set_id ya da ply, views: [{w2c, K, width, height}]}` → PNG'ler. Yalnız gsplat;
    video modeli yüklü olmasa da çalışır (birkaç GB, saniyeler). Böylece aynı set ikinci kez kurulmadan yeni açı alınır.
  - Set dosyaları film klasöründe saklanır (bkz. 3); servis durumsuz kalır, `ply` istekle gelir.
- Ağırlık imaja girmez; gateway `/data/editor/models/Lyra-2`'yi bağlar (salt okunur), `TORCH_HOME` ve `HF_HOME` ona.

### 2. Gateway takma adı: `book-scene3d` (`deploy/models.yaml`, book-video bloklarının düzeni)

```yaml
  # Kitaptan film — mekân seti (NVIDIA Lyra 2.0, kullanıcı kararı 2026-10-08): sahnenin tek çiziminden 3B Gauss seti,
  # çekim açısına göre arka plan render'ı (production/film/sets.py). Model lisansı NVIDIA Internal Scientific R&D —
  # üretim kullanımı kurumun NVIDIA lisansına bağlı (docs/analiz/lyra-mekan-seti.md «Lisans»).
  # ÖLÇÜLMEDİ: açılış süresi, bellek tepesi, set başı süre. Pay tahmin: 14B + umT5 + DA3-Giant birlikte ~60–75 GB.
  book-scene3d:
    container: editor-model-scene3d
    model_dir: Lyra-2
    real_model: nvidia/Lyra-2.0+depth-anything/DA3NESTED-GIANT-LARGE-1.1+Ruicheng/moge-vitl+lpiccinelli/unidepth-v2-vitl14
    role: Kitaptan film — mekân seti (tek çizimden 3B oda, çekim açısından arka plan)
    kind: scene3d
    gpu: 1
    mem_fraction: 0.90
    idle_stop_sec: 300
    start_timeout_sec: 1800
    env:
      PYTORCH_CUDA_ALLOC_CONF: expandable_segments:True
      HF_HOME: /models/hf
      TORCH_HOME: /models/torch-home   # hub → /models/torch-hub (imajda bağ)
      HF_HUB_OFFLINE: "1"
    image: editor-scene3d:1
    entrypoint: [python, /srv/server.py]
    args: []
```

`kind: scene3d` gateway'e yeni bir tür; gateway `/v1/{path}` ile her yolu geçirdiği için yalnız tür listesi/durum
ekranı etkilenir (gateway.py'de `kind` yalnız etiket — kurulumda doğrulanmalı). GPU 1 önerisi: book-video (kart 0) ile
çakışmasın; ama book-video-2 da kart 1'de → set kurma çekim adımından **önce** (kareler adımında) biter, çekimle
yarışmaz.

### 3. Film hattında yer: kareler adımının içinde «set» alt adımı

Yeni modül `production/film/sets.py`; `frames.build` başında çağrılır.

1. **Mekân kimliği** — `spec.shots()` her çekime sahnenin `setting`/`setting_en` alanını zaten taşıyor. Set
   anahtarı = `setting` metninin normalize hali (küçük harf, boşluk/noktalama sadeleşmiş; «Levent'in odası» ve
   «Levent'in odası » aynı set). Senaryo yazarı (`book-director`) aynı mekâna farklı adlar verirse ayrı set olur: şemaya
   zorunlu `setting_id` eklemek ya da senaryo denetiminde (spec.check) «benzer adlı iki mekân» uyarısı — açık soru.
   Gece/gündüz (`time`) aynı seti kullanır; ışık Qwen düzenlemesinde istemle verilir.
2. **Set görseli (anahtar çizim)** — her set için bir kez `book-image` ile insansız, geniş oda çizimi:
   `spec.shot_prompt`'un ortam kısmı + «empty room, no people, wide establishing view, eye level» + film üslubu.
   1280×720 üretilir, Lyra girdisi 832×480'e küçültülür. Görsel denetçi: yazı yok, kişi yok. Editör bunu onaylar/
   yeniden çizdirir (kareler ekranında «Mekânlar» şeridi). Saklama: `<film>/set/<set_id>/anahtar.png`.
3. **Set yolu (kamera)** — çizimdeki kamera noktasından odayı gezen sabit bir yol: yerinde sola dönüş (~60°), geri,
   sağa dönüş (~60°), merkeze geri, 1 m geri çekilme, yarım metre yana kayma. ~321–481 kare (4–6 Lyra parçası). Yol
   üretimi modelsiz, deterministik (testlenebilir); parça başlıkları `captions.json`'a sahnenin `setting_en`'i + üslup.
   Yol ilk kareden ayrılmayan yerde başlar ve döner: Lyra'nın mekânsal belleği dönüşte aynı odayı tutar.
4. **3B kurma** — `POST /v1/scene3d/build` → `set/<set_id>/scene.ply`, `walk.mp4`, `cameras.json`.
5. **Çekim açısı** — `framing` (genel/boy/bel/yakin/cok-yakin/omuz-ustu/kus-bakisi) ve sahnedeki çekim sırası →
   setteki adlandırılmış görünümlerden biri: `genel` = anahtar kamera; `boy`/`bel` = anahtar kameradan ileri
   (odak mesafesinin %30/%50'si); `yakin`/`cok-yakin` = arka plan bulanık yakın (render + Gauss bulanıklık; karakter
   kadrajı zaten çoğunu kapatır); `omuz-ustu` = karşı açı (180° dönüş — Lyra'nın görmediği yer; yolun dönüş kısmından
   en yakın görünüm); `kus-bakisi` = yükseltilmiş, aşağı bakan kamera. Aynı sahnede art arda iki çekim aynı framing
   ise yatay ±15° kaydırma (tekdüzelik olmasın). Kural `sets.py`'de, modelsiz.
6. **Arka plan render** — `POST /v1/scene3d/render` 1280×720 (Gauss bulutu 832×480 videodan kurulduğu için
   doku yumuşak çıkar → `book-upscale` gerekmez; Qwen düzenlemesi zaten yeniden çiziyor). Saklama:
   `kare/<shot_id>.arka.png`.
7. **Karakterleri yerleştirme** — `frames.render` değişir: arka plan ilk referans olur
   (`refs = [arka, *karakter_kartları][:I.MAX_REFS]`, MAX_REFS = 4 → en çok 3 karakter kartı; 3'ten fazla karakterli
   çekimde set kullanılmaz ya da en az görünen kart düşer — açık soru), istem: «Reference image 1 is the room: keep
   its layout, furniture, colours and camera exactly; redraw it cleanly in <style>. Place …» + mevcut `ref_note`
   (sıralama 2'den başlar). Gauss render'ındaki bulanık/boş kenarlar bu düzenlemede temizlenir.
8. **Denetim** — `review`'a bir soru eklenir: «arka plan referans odayla aynı mı (pencere, kapı, büyük eşyalar)?»
   Geçmezse yeni tohum (mevcut RETRIES düzeni).
9. **Geri dönüş** — `book-scene3d` yoksa/hata verirse bugünkü yol (metinden kare); kare kaydına `set: null` yazılır,
   ekranda «mekân seti kullanılamadı». Hat durmaz.

`kareler.json` sürüm kaydına `set_id`, `view` (görünüm adı + w2c), `background` dosyası eklenir; editör «açıyı
değiştir» ile başka görünümden yeniden çizdirebilir (`redo`'ya `view` parametresi).

### 4. Tahmini GPU süresi ve bellek (ÖLÇÜLMEDİ)

| İş | DMD (4 adım) | Tam (35 adım) |
|---|---|---|
| Model açılışı (14B + kodlayıcılar + DA3) | 3–5 dk (ilk kez; Wan 2.1 14B'nin bizdeki açılışına benzer) | aynı |
| Set başı video, 401 kare | ~3 dk | ~45 dk |
| Set başı 3B kurma | ~1–2 dk | aynı |
| Çekim başı render (gsplat) | saniyeler | aynı |
| 8 mekânlı bir film | ~45 dk (+ açılış) | ~6,5 saat |

Öneri: ilk denemede DMD açık; çizgi film üslubunda tekrar deseni/istem kayması görülürse o set tam adımla yeniden
kurulur (editörden «setleri kaliteli kur» seçeneği). Bellek: kart 1'de 0.90 pay; açılınca kart 1'deki editör
modelleri (ana model dahil) durur — book-video-2 ile aynı bedel.

### 5. İlk kurulumda sınanacaklar (sırayla; hepsi test sunucusu kuralına bağlı, GPU boşken, 21:00 sonrası)

1. İmaj derlemesi ve içe aktarma denetimi.
2. Depodaki `example_0` ile `--use_dmd` koşusu: bellek tepesi, süre (belgedeki 35 sn/80 kare doğrulanır).
3. «Levent Kardan Adam» pilotundan bir oda çizimiyle set: 2B cel-shaded çizimde MoGe/DA3 derinliği ve Gauss sonucu
   ayakta kalıyor mu (Lyra gerçekçi videoyla eğitildi — **en büyük risk**). Karşı açı (omuz-ustu) render'ı okunur mu?
4. Aynı setten 3 farklı framing render'ı + Qwen düzenlemesiyle karakter yerleştirme → görsel denetçi ve editör gözü.
5. DA3NESTED ağırlığı gerçekten okunuyor mu (lisans notu için) — `HF_HUB_OFFLINE=1` ile önbellekten kaldırınca hata
   veriyor mu.

## Açık sorular

1. Lisans: NVIDIA Internal R&D lisanslı ağırlığın üretimde kullanımı için kurumdaki lisansın yazılı kapsamı
   (sözleşme no/tarih) belgeye eklenmeli. DA3NESTED (CC-BY-NC) ve UniDepth (CC-BY-NC) için de aynı.
2. Mekân kimliği: senaryo şemasına `setting_id` eklensin mi, yoksa `setting` metni mi anahtar? (Şema değişikliği
   eski senaryoları bozar; normalize metin bozmaz ama eş anlamlı adları ayırır.)
3. 3'ten fazla karakterli çekimde arka plan referansı mı, karakter kartı mı düşsün?
4. Set kurma kartı: GPU 1 (book-video-2 ile sıra) mı, yoksa kareler adımı zaten çekimden önce olduğu için karta
   bakılmaksızın boş olana mı? Gateway şu an tek `gpu` alanı taşıyor.
5. Dış mekân (orman, sokak) setleri: Lyra büyük açık alanlarda da tutarlı (belgedeki örnekler çoğunlukla dış mekân);
   «sahne geçişi» olan uzun dış yürüyüşlerde set yerine bugünkü yol daha iyi olabilir — pilot sonrası karar.
