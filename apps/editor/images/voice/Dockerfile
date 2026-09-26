# book-voice: VoxCPM2 seslendirme + Türkçe CTC hizalama (images/voice/server.py). vLLM-Omni imajının Torch/CUDA,
# torchaudio, transformers ve ffmpeg'i yeniden kullanılır (GPU'da zaten var; book-upscale ile aynı taban).
# --no-deps: voxcpm'in bütün bağımlılıkları tabanda var (2026-09-26 derlemesinde yalnız nvidia-nccl-cu13'ü
# 2.30.7 → 2.29.7'ye indirmek istedi); tabanın Torch/CUDA kümesi olduğu gibi kalır.
FROM vllm/vllm-omni@sha256:38c59f79fd8fc4831348a3d800a882833a1ca1c50a67458988d693f3aa80360c
RUN pip install --no-cache-dir --no-deps voxcpm==2.0.3 && python -c "import voxcpm, torchaudio, transformers"
COPY images/voice/server.py /srv/server.py
ENTRYPOINT ["python", "/srv/server.py"]
