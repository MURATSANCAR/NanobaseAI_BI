# book-video (images/video/server.py): Wan 2.2 + MiniMax-H3 (diffusers) + FastH3 (ComfyUI düğümleri) + iyileştirme
# (SeedVR2 7B sharp, Practical-RIFE). Ağırlıklar imaja girmez: gateway /data/editor/models/book-video'yu bağlar.
#
# İki Python ortamı (server.py belgesi):
#  - ana (/opt/conda): sunucu + Wan. Bağımlılıklar Wan'ın requirements*.txt'sinden (transformers ≤4.51.3, numpy<2);
#    flash-attn yok (Wan PyTorch dikkatine düşer). S2V'nin CosyVoice parçası kullanılmaz ama modül düzeyinde içe
#    aktarılanlar kurulur.
#  - /opt/h3 (venv, --system-site-packages: torch ana ortamdan): diffusers (MiniMax-H3 modular pipeline yalnız
#    main'de), Qwen3-VL için yeni transformers, ComfyUI requirements.txt, SeedVR2 requirements.txt. Practical-RIFE'ın
#    requirements'ındaki sk-video/moviepy kurulmaz: kendi döngümüz (worker_enhance.py) kareleri ffmpeg ile okur/yazar.
# Kaynak kodlar sabit commit'te; .git silinir.
FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg libsndfile1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------- Wan 2.2 (ana ortam)
ARG WAN_COMMIT=1ea34ff48f87168174e12956e200b1d908b1c5ff
RUN git clone https://github.com/Wan-Video/Wan2.2.git /opt/Wan2.2 && git -C /opt/Wan2.2 checkout ${WAN_COMMIT} \
    && rm -rf /opt/Wan2.2/.git /opt/Wan2.2/examples /opt/Wan2.2/assets
RUN pip install --no-cache-dir "diffusers>=0.31.0" "transformers>=4.49.0,<=4.51.3" "tokenizers>=0.20.3" \
        "accelerate>=1.1.1" tqdm "imageio[ffmpeg]" imageio-ffmpeg easydict ftfy "numpy>=1.23.5,<2" \
        opencv-python-headless safetensors decord librosa omegaconf HyperPyYAML inflect onnxruntime \
        fastapi "uvicorn[standard]" pydantic \
    && python -c "import sys; sys.path.insert(0, '/opt/Wan2.2'); import wan, decord, librosa"

# ---------------------------------------------------------------- H3 / FastH3 / iyileştirme (/opt/h3)
# diffusers main 2026-10-06 (MiniMax-H3 modular_pipelines/minimax_h3, AutoencoderKLMiniMaxH3[Audio])
ARG DIFFUSERS_COMMIT=c6df88a511a98740646ee55577b590c9852650ce
# ComfyUI 2026-10-07 (comfy/ldm/minimax, comfy_extras/nodes_minimax_h3.py — pruned FastH3 yükleyicisi)
ARG COMFY_COMMIT=b00c6e95279053474955540ba4f551646722b9aa
# numz/ComfyUI-SeedVR2_VideoUpscaler v2.5.x (inference_cli.py; seedvr2_ema_7b_sharp_fp16 kayıtlı)
ARG SEEDVR2_COMMIT=4490bd1f482e026674543386bb2a4d176da245b9
# hzwer/Practical-RIFE (model/warplayer.py, model/loss.py, model/pytorch_msssim; ağırlık 4.26 ayrı)
ARG RIFE_COMMIT=bbfd2ea90910789a860ea3e2b32a240cd577b75e
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /opt/ComfyUI && git -C /opt/ComfyUI checkout ${COMFY_COMMIT} \
    && git clone https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git /opt/SeedVR2 \
    && git -C /opt/SeedVR2 checkout ${SEEDVR2_COMMIT} \
    && git clone https://github.com/hzwer/Practical-RIFE.git /opt/Practical-RIFE \
    && git -C /opt/Practical-RIFE checkout ${RIFE_COMMIT} \
    && rm -rf /opt/ComfyUI/.git /opt/SeedVR2/.git /opt/Practical-RIFE/.git /opt/SeedVR2/docs /opt/SeedVR2/example_workflows
RUN python -m venv --system-site-packages /opt/h3 \
    && /opt/h3/bin/pip install --no-cache-dir \
        "diffusers @ git+https://github.com/huggingface/diffusers.git@${DIFFUSERS_COMMIT}" \
        "transformers>=4.57.1,<5" "accelerate>=1.1.1" "safetensors>=0.8.0" "huggingface-hub>=1.32.0,<2.0" \
        "numpy>=1.25,<2" soundfile "av>=17.0.0" imageio imageio-ffmpeg torchao \
        -r /opt/ComfyUI/requirements.txt -r /opt/SeedVR2/requirements.txt \
    && /opt/h3/bin/python -c "import diffusers, transformers; from diffusers import ComponentsManager, ModularPipeline; \
from diffusers.modular_pipelines.minimax_h3 import MiniMaxH3AudioReference, MiniMaxH3ImageReference; \
from transformers import Qwen3VLForConditionalGeneration; print(diffusers.__version__, transformers.__version__)"

COPY images/video/server.py images/video/plan.py images/video/worker_common.py images/video/worker_wan.py \
     images/video/worker_h3.py images/video/worker_fasth3.py images/video/worker_enhance.py /srv/
ENTRYPOINT ["python", "/srv/server.py"]
