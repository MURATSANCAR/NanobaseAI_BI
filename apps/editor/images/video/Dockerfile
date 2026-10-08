# book-video (images/video/server.py): Wan 2.2 + MiniMax-H3 (diffusers) + FastH3 V2 (FastVideo) + iyileştirme
# (SeedVR2 7B sharp, Practical-RIFE). Ağırlıklar imaja girmez: gateway /data/editor/models/book-video'yu bağlar.
#
# Üç Python ortamı (server.py belgesi), çünkü sabitlemeler çakışıyor:
#  - ana (/opt/conda, Py 3.11, torch 2.8): sunucu + Wan. Wan'ın requirements*.txt'si (transformers ≤4.51.3, numpy<2);
#    flash-attn yok (Wan PyTorch dikkatine düşer). S2V'nin CosyVoice parçası kullanılmaz.
#  - /opt/h3 (venv, --system-site-packages: torch ana ortamdan): diffusers (MiniMax-H3 modular pipeline yalnız main'de),
#    transformers 5.x (diffusers main huggingface-hub ≥1.32 ister; transformers 4.57 hub<1 ister → çözülemez),
#    SeedVR2 requirements.txt. torchao kurulmaz (2026-10-08 derlemesi): diffusers/transformers onu yalnız varsa yükler
#    (is_torchao_available), bizde nicemleme yok; sabitsiz 0.18 torch ≥2.11 istiyor (ScalingType), torch 2.8 eşi 0.13
#    ise diffusers main'in istediği FqnToConfig'i (≥0.15) taşımıyor. Practical-RIFE'ın sk-video/moviepy'si kurulmaz: kendi
#    döngümüz (worker_enhance.py) kareleri ffmpeg ile okur/yazar.
#  - /opt/fastvideo (uv venv, Py 3.12): FastVideo pyproject'i torch==2.12.0, transformers>=5.15 ister; fastvideo-kernel
#    0.3.5 tekeri yalnız cp312. torch cu130 (sürücü 580 = CUDA 13). FA4/sm100a eklentileri (fasth3 ekstrası, Blackwell)
#    kurulmaz; Hopper'da VSA Triton çekirdeğiyle çalışır (model kartı: --vsa-kernel triton --no-fa4).
# Kaynak kodlar sabit commit'te; .git silinir. İçe aktarma denetimleri GPU'suz yapılır (Wan'ın t5.py'si sınıf
# tanımında torch.cuda.current_device() çağırdığı için `import wan` GPU'suz derlemede çöker → yalnız sözdizimi).
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
        fastapi "uvicorn[standard]" pydantic
RUN python -m compileall -q /opt/Wan2.2/wan && python -c "import decord, librosa, easydict, ftfy, diffusers, transformers, fastapi, uvicorn"

# ---------------------------------------------------------------- H3 + iyileştirme (/opt/h3)
# diffusers main 2026-10-06 (modular_pipelines/minimax_h3, AutoencoderKLMiniMaxH3[Audio])
ARG DIFFUSERS_COMMIT=c6df88a511a98740646ee55577b590c9852650ce
# numz/ComfyUI-SeedVR2_VideoUpscaler v2.5.x (inference_cli.py; seedvr2_ema_7b_sharp_fp16 kayıtlı)
ARG SEEDVR2_COMMIT=4490bd1f482e026674543386bb2a4d176da245b9
# hzwer/Practical-RIFE (model/warplayer.py, model/loss.py, model/pytorch_msssim; ağırlık 4.26 ayrı)
ARG RIFE_COMMIT=bbfd2ea90910789a860ea3e2b32a240cd577b75e
RUN git clone https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git /opt/SeedVR2 \
    && git -C /opt/SeedVR2 checkout ${SEEDVR2_COMMIT} \
    && git clone https://github.com/hzwer/Practical-RIFE.git /opt/Practical-RIFE \
    && git -C /opt/Practical-RIFE checkout ${RIFE_COMMIT} \
    && rm -rf /opt/SeedVR2/.git /opt/Practical-RIFE/.git /opt/SeedVR2/docs /opt/SeedVR2/example_workflows
RUN python -m venv --system-site-packages /opt/h3 \
    && /opt/h3/bin/pip install --no-cache-dir --retries 10 --timeout 120 \
        "diffusers @ https://github.com/huggingface/diffusers/archive/${DIFFUSERS_COMMIT}.tar.gz" \
        "transformers>=5.15,<6" "accelerate>=1.1.1" "safetensors>=0.8.0" "huggingface-hub>=1.32.0,<2.0" \
        "numpy>=1.25,<2" soundfile "av>=17.0.0" imageio imageio-ffmpeg \
        -r /opt/SeedVR2/requirements.txt
RUN /opt/h3/bin/python -c "import diffusers, transformers, soundfile; from diffusers import ComponentsManager, ModularPipeline; \
from diffusers.modular_pipelines.minimax_h3 import MiniMaxH3AudioReference, MiniMaxH3ImageReference; \
from transformers import Qwen3VLForConditionalGeneration; import omegaconf, rotary_embedding_torch, peft, cv2; \
print('h3', diffusers.__version__, transformers.__version__)"

# ---------------------------------------------------------------- FastH3 V2 (/opt/fastvideo)
# hao-ai-lab/FastVideo 2026-10-07 (registry: FastVideo/FastVideo-FastH3-8-Step-V2; FP8 yükleyici fsdp_load.py)
ARG FASTVIDEO_COMMIT=d1416b59301d830f12c48f08b08f825f206b6328
RUN pip install --no-cache-dir uv \
    && git clone https://github.com/hao-ai-lab/FastVideo.git /opt/FastVideo && git -C /opt/FastVideo checkout ${FASTVIDEO_COMMIT} \
    && rm -rf /opt/FastVideo/.git \
    && uv venv --python 3.12 --seed /opt/fastvideo \
    && UV_TORCH_BACKEND=cu130 uv pip install --python /opt/fastvideo/bin/python --no-cache \
        --no-sources-package fastvideo-kernel -e /opt/FastVideo
# GPU'suz denetim: fastvideo'yu (alt modülü dahil) içe aktarmak fastvideo_kernel'in Triton çekirdeklerini yükler, Triton da
# modül yüklenirken etkin GPU sürücüsü arar ("0 active drivers", 2026-10-08) → burada yalnız kurulu sürümler, worker_fasth3'ün
# fastvideo.api'den aldığı adlar (kaynağın sözdizim ağacından) ve derlenebilirlik denetlenir; gerçek içe aktarma GPU'da olur.
RUN /opt/fastvideo/bin/python -c "import ast, torch, transformers, importlib.metadata as m; \
t = ast.parse(open('/opt/FastVideo/fastvideo/api/__init__.py').read()); \
have = {a.asname or a.name for n in ast.walk(t) if isinstance(n, ast.ImportFrom) for a in n.names}; \
need = {'CompileConfig', 'ComponentConfig', 'EngineConfig', 'GeneratorConfig', 'OffloadConfig', 'ParallelismConfig', \
'PipelineSelection', 'GenerationRequest', 'OutputConfig', 'SamplingConfig'}; assert need <= have, need - have; \
print('fastvideo', m.version('fastvideo'), m.version('fastvideo-kernel'), torch.__version__, transformers.__version__)" \
    && /opt/fastvideo/bin/python -m compileall -q /opt/FastVideo/fastvideo >/dev/null \
    && grep -q "^from fastvideo.entrypoints.video_generator import VideoGenerator" /opt/FastVideo/fastvideo/__init__.py

COPY images/video/server.py images/video/plan.py images/video/worker_common.py images/video/worker_wan.py \
     images/video/worker_h3.py images/video/worker_fasth3.py images/video/worker_enhance.py /srv/
ENTRYPOINT ["python", "/srv/server.py"]
