# book-voice (ÖNERİ, kurulmadı): VoxCPM2 seslendirme + Türkçe CTC hizalama. vLLM-Omni imajının Torch/CUDA,
# torchaudio, transformers ve ffmpeg'i yeniden kullanılır (GPU'da zaten var; book-upscale ile aynı taban).
# Deneme 2026-09-25: bu tabanda `pip install voxcpm==2.0.3` Torch'u değiştirmedi (2.13.0+cu130).
FROM vllm/vllm-omni@sha256:38c59f79fd8fc4831348a3d800a882833a1ca1c50a67458988d693f3aa80360c
RUN pip install --no-cache-dir voxcpm==2.0.3
COPY images/voice/server.py /srv/server.py
ENTRYPOINT ["python", "/srv/server.py"]
