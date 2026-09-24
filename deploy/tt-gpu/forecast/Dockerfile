# BI tahmin servisi (TimesFM 3.0) — TT GPU, GPU 0. Temel imaj BI modelinin (qwen38-27b) kullandığı vLLM imajı:
# CUDA'lı torch, fastapi, uvicorn, numpy hazır; yalnız TimesFM kaynağı ve servis kodu eklenir (indirme yok).
FROM vllm/vllm-openai:v0.27.1
COPY timesfm /opt/timesfm
RUN pip install --no-deps --no-cache-dir /opt/timesfm && python3 -c "from timesfm3 import ModelConfig, TimesFM3Evaluator"
COPY forecasting /app/forecasting
WORKDIR /app
ENV PYTHONPATH=/app
ENTRYPOINT ["uvicorn", "forecasting.app.main:app", "--host", "0.0.0.0", "--port", "8793", "--workers", "1", "--timeout-keep-alive", "30"]
