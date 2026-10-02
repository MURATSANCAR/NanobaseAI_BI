# book-embedding-cpu: Qwen3-Embedding-8B CPU'da (transformers + torch bf16, AMX). vLLM imajının Torch/transformers'ı
# yeniden kullanılır (sunucuda zaten var); GPU kullanılmaz (gateway kart vermez, CUDA_VISIBLE_DEVICES boş).
FROM vllm/vllm-openai:v0.29.0
COPY images/embed-cpu/server.py /srv/server.py
ENV CUDA_VISIBLE_DEVICES=""
ENTRYPOINT ["python3", "/srv/server.py"]
