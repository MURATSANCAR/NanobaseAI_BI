# book-music: kitaptan çizgi filmin müziği (images/music/server.py). Motorların kütüphane sürümleri birbiriyle çakışır
# (Stable Audio 3: torch 2.7.1 + transformers 5; YuE2: torch 2.10 + transformers 4.57.6; diffusers 0.41:
# huggingface-hub ≥ 1.32; heartlib: transformers 4.57.0 + torchao 0.9; ACE-Step: torchao 0.16 + uv.lock); her motor
# kendi sanal ortamındadır, servis motoru o ortamın Python'uyla ayrı süreçte açar (worker.py).
#   /opt/venv/sa3        Stable Audio 3 (Py 3.10, torch 2.7.1 cu126, flash-attn 2.6.3 README'deki hazır tekerlek)
#   /opt/venv/yue2       YuE2 — resmî instrumental tarifinin requirements-inference.txt'si (yue2-infer 0.1.5, sha256)
#   /opt/venv/mm3        MiniMax Music 3 — README: diffusers (minimax_music3 v0.40'tan beri sürümde) + transformers +
#                        accelerate + soundfile
#   /opt/venv/acestep    ACE-Step 1.5 — deponun Dockerfile'ı: `uv sync --frozen --no-dev` (uv.lock), Python 3.11
#   /opt/venv/heartmula  HeartMuLa — heartlib README: Python 3.10, pyproject sabitleri
# Ticari serbest iki motor (ACE-Step, HeartMuLa) her zaman, lisanslı üç motor ENGINES ile kurulur (varsayılan üçü). Kaynak kodlar sabit commit'te. Ağırlıklar imaja girmez:
# gateway /data/editor/models/book-music'i /model olarak bağlar.
FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TOKENIZERS_PARALLELISM=false \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python UV_NO_CACHE=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.12.23 fastapi==0.136.1 uvicorn==0.46.0

# --- HeartMuLa (şarkı yedeği, ticari serbest)
ARG HEARTLIB_COMMIT=96ef96e0ee2346e8a3ca3300aabfdff85e0231be
RUN git clone https://github.com/HeartMuLa/heartlib.git /opt/heartlib && git -C /opt/heartlib checkout ${HEARTLIB_COMMIT} \
    && rm -rf /opt/heartlib/.git /opt/heartlib/assets \
    && uv venv -p 3.10 /opt/venv/heartmula \
    && uv pip install --python /opt/venv/heartmula /opt/heartlib torch==2.10.0 torchaudio==2.10.0 torchcodec==0.10.0 \
        datasets==5.0.1
# torchaudio 2.10'un save'i torchcodec ister (heartlib postprocess torchaudio.save ile yazar; 2026-10-08 derlemesi
# bunsuz ImportError ile düştü). torch heartlib'in sınırı (<2.11) içinde sabit, torchcodec 0.10 onun eşi. datasets sabit:
# torchcodec eklenince çözücü 2.14.4'e indi, o da pyarrow 25'te kalkan PyExtensionType'ı arıyor (torchtune içe aktarırken
# düşüyor); 2026-10-07 derlemesinde çözülen 5.0.1 ile sorun yok. Denetim ayrı
# katmanda: düşerse kurulum katmanı önbellekte kalır.
RUN /opt/venv/heartmula/bin/python -c "import torch, torchaudio, soundfile; from heartlib import HeartMuLaGenPipeline; torchaudio.save('/tmp/s.wav', torch.zeros(2, 480), 48000)" \
    && rm -f /tmp/s.wav

# --- ACE-Step 1.5 XL (film müziği yedeği, ticari serbest)
ARG ACESTEP_COMMIT=ca1e85fe9430179831e6bc6be790c332190a3866
RUN git clone https://github.com/ace-step/ACE-Step-1.5.git /opt/acestep && git -C /opt/acestep checkout ${ACESTEP_COMMIT} \
    && rm -rf /opt/acestep/.git /opt/acestep/assets /opt/acestep/docs \
    && cd /opt/acestep && UV_PROJECT_ENVIRONMENT=/opt/venv/acestep uv sync --frozen --no-dev --python 3.11 \
    && /opt/venv/acestep/bin/python -c "import torch, soundfile; from acestep.handler import AceStepHandler; from acestep.llm_inference import LLMHandler; from acestep.inference import GenerationParams, GenerationConfig, generate_music"

# --- Stable Audio 3 (film müziği ana), YuE2 (şarkı ana + sözsüz yedek), MiniMax Music 3 (şarkı yedeği)
ARG ENGINES="stable-audio-3 yue2 minimax-music3"
# pypi.nvidia.com GPU sunucusundan zaman zaman yavaş akıyor: uv'nin 30 sn'lik okuma süresi ve 3 denemesi torch'un CUDA
# tekerleklerinde iki kez düştü (2026-10-08, «operation timed out»). ARG olarak buradan sonraki RUN'lara ortam değişkeni geçer;
# önceki katmanların önbelleği bozulmaz.
ARG UV_HTTP_TIMEOUT=600 UV_HTTP_RETRIES=10 UV_CONCURRENT_DOWNLOADS=4
ARG SA3_COMMIT=3a82c807b69cf4b7c5c05270011a5d5e47abac18
ARG FLASH_ATTN_WHL=https://github.com/mjun0812/flash-attention-prebuild-wheels/releases/download/v0.7.16/flash_attn-2.6.3+cu126torch2.7-cp310-cp310-linux_x86_64.whl
ARG YUE_COMMIT=1647252d68b70cbead046ffd3f7caf036dde47ee
ARG MM3_PKGS="diffusers==0.41.0 transformers accelerate soundfile torch"
RUN set -e; case " ${ENGINES} " in *" stable-audio-3 "*) \
      git clone https://github.com/Stability-AI/stable-audio-3.git /opt/sa3 && git -C /opt/sa3 checkout ${SA3_COMMIT}; \
      rm -rf /opt/sa3/.git /opt/sa3/optimized /opt/sa3/docs; uv venv -p 3.10 /opt/venv/sa3; \
      uv pip install --python /opt/venv/sa3 torch==2.7.1 torchaudio==2.7.1 --index-url https://download.pytorch.org/whl/cu126; \
      uv pip install --python /opt/venv/sa3 /opt/sa3 "${FLASH_ATTN_WHL}"; \
      /opt/venv/sa3/bin/python -c "import stable_audio_3.model, stable_audio_3.loading_utils, flash_attn, soundfile; from transformers import T5GemmaEncoderModel";; esac
RUN set -e; case " ${ENGINES} " in *" yue2 "*) \
      git clone https://github.com/multimodal-art-projection/YuE.git /opt/yue && git -C /opt/yue checkout ${YUE_COMMIT}; \
      rm -rf /opt/yue/.git /opt/yue/assets /opt/yue/docs; uv venv -p 3.12 /opt/venv/yue2; \
      uv pip install --python /opt/venv/yue2 -r /opt/yue/skills/yue2-music/instrumental/requirements-inference.txt; \
      cd /opt/yue/skills/yue2-music/instrumental/scripts; \
      /opt/venv/yue2/bin/python -c "import yue2, soundfile, instrumental, importlib.metadata as m; from yue2 import YuE2Pipeline; assert m.version('yue2-infer') == '0.1.5'";; esac
RUN set -e; case " ${ENGINES} " in *" minimax-music3 "*) \
      uv venv -p 3.12 /opt/venv/mm3; uv pip install --python /opt/venv/mm3 ${MM3_PKGS}; \
      /opt/venv/mm3/bin/python -c "import torch, soundfile; from diffusers import ModularPipeline; from diffusers.modular_pipelines.minimax_music3 import modular_pipeline";; esac

COPY images/music/server.py /srv/server.py
COPY images/music/worker.py /srv/worker.py
ENTRYPOINT ["python", "/srv/server.py"]
