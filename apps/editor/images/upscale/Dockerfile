# book-upscale: Real-ESRGAN x4plus (spandrel). vLLM-Omni imajının Torch/CUDA'sı yeniden kullanılır (GPU'da zaten var).
FROM vllm/vllm-omni@sha256:38c59f79fd8fc4831348a3d800a882833a1ca1c50a67458988d693f3aa80360c
RUN pip install --no-cache-dir spandrel==0.4.1
COPY images/upscale/server.py /srv/server.py
ENTRYPOINT ["python", "/srv/server.py"]
