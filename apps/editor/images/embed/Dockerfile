# editor-embed: the character-identity embedder. Its own image because it needs
# onnxruntime (no wheels for the 3.14 the rest of the editor runs on) and because it
# is the only editor process that touches the GPU without going through the gateway.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
# imgutils pins numpy<2, so onnxruntime is left to the resolver rather than pinned
# against it; the pair that resolves today is onnxruntime-gpu 1.30 + numpy 1.26.
RUN pip install dghs-imgutils==0.19.0 onnxruntime-gpu==1.30.0 fastapi==0.141.1 \
    uvicorn==0.53.0 pillow==12.3.0 \
 && pip install --force-reinstall opencv-python-headless==4.13.0.92
COPY images/embed/server.py /app/server.py
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
