# book-video: Wan 2.2 kareden video (i2v) + sesten konuşan çekim (s2v) servisi (images/video/server.py).
# Wan kodu sabit sürümde (commit), bağımlılıkları Wan'ın requirements*.txt'sinden; flash-attn yok (Wan kendiliğinden
# PyTorch dikkatine düşer). S2V'nin metinden ses (CosyVoice) parçası kullanılmaz (enable_tts=False) ama modül düzeyinde
# içe aktarılan bağımlılıklar kurulur. Ağırlıklar imaja girmez: gateway /data/editor/models/book-video'yu bağlar.
FROM pytorch/pytorch:2.8.0-cuda12.8-cudnn9-runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg libsndfile1 && rm -rf /var/lib/apt/lists/*
ARG WAN_COMMIT=1ea34ff48f87168174e12956e200b1d908b1c5ff
RUN git clone https://github.com/Wan-Video/Wan2.2.git /opt/Wan2.2 && git -C /opt/Wan2.2 checkout ${WAN_COMMIT} \
    && rm -rf /opt/Wan2.2/.git /opt/Wan2.2/examples /opt/Wan2.2/assets
RUN pip install --no-cache-dir "diffusers>=0.31.0" "transformers>=4.49.0,<=4.51.3" "tokenizers>=0.20.3" \
        "accelerate>=1.1.1" tqdm "imageio[ffmpeg]" imageio-ffmpeg easydict ftfy "numpy>=1.23.5,<2" \
        opencv-python-headless safetensors decord librosa omegaconf HyperPyYAML inflect onnxruntime \
        fastapi "uvicorn[standard]" pydantic \
    && python -c "import sys; sys.path.insert(0, '/opt/Wan2.2'); import wan, decord, librosa"
COPY images/video/server.py /srv/server.py
ENTRYPOINT ["python", "/srv/server.py"]
