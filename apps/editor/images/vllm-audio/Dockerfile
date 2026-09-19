# book-audio (Qwen3-Omni-30B-A3B-Captioner) needs vLLM's audio extra
# (librosa, soundfile); the official image ships without it.
FROM vllm/vllm-openai:v0.29.0
RUN pip install --no-cache-dir "vllm[audio]==0.29.0"
