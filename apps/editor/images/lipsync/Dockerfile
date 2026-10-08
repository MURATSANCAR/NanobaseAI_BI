# editor-lipsync (images/lipsync/dub.py): çekim sonrası dudak senkronu — InfiniteTalk (Wan2.1-I2V-14B + ses katmanı).
# Ağırlıklar imaja girmez: /data/editor/models salt okunur bağlanır (Wan2.1-I2V-14B-480P, chinese-wav2vec2-base,
# InfiniteTalk/{single,multi,lora}). Derleme bağlamı apps/editor (video imajıyla aynı).
#
# Taban editor-video ile aynı (pytorch 2.8.0 / CUDA 12.8 / Py 3.11): katmanlar paylaşılır, kök diske ek yük küçük.
#  - flash-attn: Wan'ın flash_attention() işlevi FA2/FA3 yoksa assert ile durur → hazır teker (2.8.3, cu12 torch2.8
#    cxx11abiTRUE cp311; derleme yok; aşağıdaki teker/ notu).
#  - xformers 0.0.32.post2 (torch==2.8.0 eşi): multitalk_model ses çapraz dikkatinde zorunlu içe aktarma.
#  - xfuser 0.4.1 --no-deps: wan/utils/multitalk_utils.py ve attention.py modül düzeyinde xfuser.core.distributed
#    içe aktarıyor (tek GPU'da da). Bağımlılığı ray/flask/pytest/opencv-python'u çekmesin diye yalnız yunchang+distvae.
#  - transformers ≤4.51.3, numpy<2 (Wan/decord eşi; editor-video ana ortamıyla aynı sabitleme).
#  - Kokoro/misaki (TTS), scenedetect/moviepy (sahne bölme), dashscope (istem genişletme) kurulmaz: dub.py bunları
#    kullanmaz, generate_infinitetalk.py'yi değil wan.InfiniteTalkPipeline'ı doğrudan çağırır.
#  - InfiniteTalk kodu sabit commit'te; Py 3.11'de olmayan `from inspect import ArgSpec` (kullanılmıyor) silinir.
# İçe aktarma denetimi GPU'suz: wan/modules/t5.py varsayılan argümanda torch.cuda.current_device() çağırdığı için
# `import wan` GPU'suz derlemede çöker → bağımlılıklar tek tek içe aktarılır, InfiniteTalk + dub.py derlenir.
FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    INFINITETALK_KOD=/opt/InfiniteTalk MODELLER=/data/editor/models
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# MeiGen-AI/InfiniteTalk main 2026-05-22
ARG INFINITETALK_COMMIT=50aa0a94184315407a991ae804d9b58d6d311ba8
# Tam klon (assets/ örnek videoları ~265 MB) derleme ağında takıldı (2026-10-08) → yalnız sabit commit sığ çekilir.
RUN git init -q /opt/InfiniteTalk \
    && git -C /opt/InfiniteTalk fetch -q --depth 1 https://github.com/MeiGen-AI/InfiniteTalk.git ${INFINITETALK_COMMIT} \
    && git -C /opt/InfiniteTalk checkout -q FETCH_HEAD \
    && rm -rf /opt/InfiniteTalk/.git /opt/InfiniteTalk/assets /opt/InfiniteTalk/examples /opt/InfiniteTalk/kokoro \
    && sed -i '/^from inspect import ArgSpec$/d' /opt/InfiniteTalk/wan/multitalk.py

# flash-attn tekeri: test sunucusunun GitHub sürüm indirmesi takılıyor (2026-10-08, 256 MB 10 dk'da 0 bayt) → teker
# images/lipsync/teker/ altına elle konabilir (depoya girmez, .gitignore); yoksa URL'den indirilir. SHA-256 denetlenir.
ARG FA_WHL=flash_attn-2.8.3+cu12torch2.8cxx11abiTRUE-cp311-cp311-linux_x86_64.whl
ARG FA_SHA256=3d41b2fc55753faa7f45d6568ea73a96b96afb48b82994ab9b49bcbcb6c87588
# (BuildKit bağlaması: teker imaj katmanına girmez)
RUN --mount=type=bind,source=images/lipsync/teker,target=/tmp/teker-yerel \
    mkdir -p /tmp/teker && cp /tmp/teker-yerel/*.whl /tmp/teker/ 2>/dev/null; \
    [ -f "/tmp/teker/${FA_WHL}" ] || python -c "import urllib.request as u; \
u.urlretrieve('https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/${FA_WHL}', '/tmp/teker/${FA_WHL}')" \
    && echo "${FA_SHA256}  /tmp/teker/${FA_WHL}" | sha256sum -c - \
    && python -c "import torch, torchvision, torchaudio; print(f'torch=={torch.__version__.split(\"+\")[0]}\ntorchvision=={torchvision.__version__.split(\"+\")[0]}\ntorchaudio=={torchaudio.__version__.split(\"+\")[0]}')" > /opt/torch-sabit.txt \
    && pip install --no-cache-dir -c /opt/torch-sabit.txt \
        "/tmp/teker/${FA_WHL}" \
        "xformers==0.0.32.post2" \
        "diffusers==0.33.1" "transformers>=4.49.0,<=4.51.3" "tokenizers>=0.20.3" "accelerate>=1.1.1" \
        "numpy>=1.23.5,<2" "optimum-quanto==0.2.6" safetensors sentencepiece einops easydict ftfy loguru tqdm \
        "imageio[ffmpeg]" imageio-ffmpeg opencv-python-headless scikit-image decord librosa soundfile pyloudnorm \
        beautifulsoup4 pyyaml \
    && pip install --no-cache-dir -c /opt/torch-sabit.txt --no-deps "xfuser==0.4.1" "yunchang==0.6.4" "distvae==0.1.0" \
    && rm -rf /tmp/teker

# xformers 0.0.32 FA ≤2.8.2 ister; torch 2.8 için 2.8.2 tekeri yok (yalnız torch 2.7). 2.8.3 ile API aynı: denetim kapalı.
ENV XFORMERS_IGNORE_FLASH_VERSION_CHECK=1
# xfuser.core.distributed içe aktarılırken CUDA sürücüsü arıyor (GPU'suz derlemede düşer): yalnız paket bulunuyor mu
RUN python -c "import importlib.util as u; assert u.find_spec('xfuser')" && python -c "import torch, flash_attn, xformers.ops, optimum.quanto, decord, librosa, \
pyloudnorm, skimage, cv2, easydict, ftfy, loguru, einops, diffusers, transformers, accelerate, soundfile; \
from diffusers.models.modeling_utils import no_init_weights, ContextManagers; \
from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2Model; \
print('lipsync', torch.__version__, flash_attn.__version__, xformers.__version__, diffusers.__version__, transformers.__version__)" \
    && python -m compileall -q /opt/InfiniteTalk/wan /opt/InfiniteTalk/src >/dev/null

COPY images/lipsync/dub.py /srv/dub.py
RUN python -m py_compile /srv/dub.py
WORKDIR /opt/InfiniteTalk
ENTRYPOINT ["python", "/srv/dub.py"]
