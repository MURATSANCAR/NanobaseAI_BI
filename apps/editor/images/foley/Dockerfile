# editor-foley (images/foley/foley.py): çekim videosundan senkron efekt/ortam sesi — HunyuanVideo-Foley (video+metin → 48 kHz).
# Ağırlıklar imaja girmez: /data/editor/models salt okunur bağlanır.
#   - /data/editor/models/HunyuanVideo-Foley: hunyuanvideo_foley.pth (XXL) / _xl.pth, vae_128d_48k.pth (DAC),
#     synchformer_state_dict.pth (tencent/HunyuanVideo-Foley rev 3abd4e83, _indirme/durum.json)
#   - SigLIP2 (google/siglip2-base-patch16-512) + CLAP (laion/larger_clap_general): kod bunları HF adıyla açar →
#     HF_HOME=/data/editor/models/HunyuanVideo-Foley/hf önbelleği (_indirme/foley-durum.json), HF_HUB_OFFLINE=1.
#     Sabit revizyonla indirildiği için refs/main elle yazıldı (yoksa çevrimdışı adla çözüm bulamıyor).
# Derleme bağlamı apps/editor (lipsync/video imajlarıyla aynı).
#
# Taban editor-lipsync / editor-video ile aynı (pytorch 2.8.0 / CUDA 12.8 / Py 3.11): katmanlar paylaşılır.
#  - transformers 4.51.3: SigLIP2 + ClapTextModelWithProjection resmî sürümde (depo v4.49.0-SigLIP-2 git dalını
#    istiyor; git kurulumu gerekmez).
#  - audiotools: depo git ana dalını istiyor; PyPI descript-audiotools 0.7.2 aynı API (DAC: AudioSignal, ml.BaseModel).
#  - flash-attn yok: yapılandırma attn_mode "torch" (SDPA); flash_attn içe aktarması try/except.
#  - gradio / pandas / geliştirme araçları kurulmaz (foley.py infer.py'yi değil iç işlevleri çağırır).
# İçe aktarma denetimi GPU'suz: modüller içe aktarılır, model kurulmaz (Synchformer/DAC kurucuları ağırlık ister).
FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/data/editor/models/HunyuanVideo-Foley/hf \
    FOLEY_KOD=/opt/HunyuanVideo-Foley FOLEY_MODEL=/data/editor/models/HunyuanVideo-Foley
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Tencent-Hunyuan/HunyuanVideo-Foley main 2025-09-29 (XL + offload sürümü). Sunucuda başvuru kopyası:
# /data/editor/models/HunyuanVideo-Foley/kod (aynı commit).
ARG FOLEY_COMMIT=df7b005b5023df2a9b73e1d66dd51d452799884e
RUN git init -q /opt/HunyuanVideo-Foley \
    && git -C /opt/HunyuanVideo-Foley fetch -q --depth 1 https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley.git ${FOLEY_COMMIT} \
    && git -C /opt/HunyuanVideo-Foley checkout -q FETCH_HEAD \
    && rm -rf /opt/HunyuanVideo-Foley/.git /opt/HunyuanVideo-Foley/assets /opt/HunyuanVideo-Foley/tests \
    && apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

RUN python -c "import torch, torchvision, torchaudio; print(f'torch=={torch.__version__.split(\"+\")[0]}\ntorchvision=={torchvision.__version__.split(\"+\")[0]}\ntorchaudio=={torchaudio.__version__.split(\"+\")[0]}')" > /opt/torch-sabit.txt \
    && pip install --no-cache-dir -c /opt/torch-sabit.txt \
        "numpy==1.26.4" scipy "transformers==4.51.3" "tokenizers>=0.21,<0.22" "diffusers==0.33.1" "accelerate>=1.1.1" \
        timm "av>=12" pillow einops pyyaml omegaconf easydict loguru tqdm packaging soundfile safetensors \
        "descript-audiotools==0.7.2" \
    && (pip check || true)

RUN cd /opt/HunyuanVideo-Foley && python -c "import torch, transformers, diffusers, audiotools, av, timm, soundfile; \
from transformers import AutoModel, AutoTokenizer, ClapTextModelWithProjection, Siglip2VisionModel; \
from hunyuanvideo_foley.utils.model_utils import load_model, denoise_process; \
from hunyuanvideo_foley.utils.feature_utils import feature_process; \
from hunyuanvideo_foley.models.dac_vae.model.dac import DAC; \
from hunyuanvideo_foley.models.synchformer import Synchformer; \
from hunyuanvideo_foley.models.hifi_foley import HunyuanVideoFoley; \
print('foley', torch.__version__, transformers.__version__, diffusers.__version__, audiotools.__version__)" \
    && python -m compileall -q /opt/HunyuanVideo-Foley/hunyuanvideo_foley >/dev/null

COPY images/foley/foley.py /srv/foley.py
RUN python -m py_compile /srv/foley.py && cd /tmp && python -c "import sys; sys.argv=['foley','--help']; \
import runpy; runpy.run_path('/srv/foley.py', run_name='__main__')" >/dev/null
WORKDIR /opt/HunyuanVideo-Foley
ENTRYPOINT ["python", "/srv/foley.py"]
