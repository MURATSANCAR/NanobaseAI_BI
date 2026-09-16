FROM python:3.11-slim-bookworm@sha256:2e32f7d302adc1c37428355c1e646897c0c53f4fd60b6a551245fb90ee129f91
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir paddlepaddle==3.2.0 paddleocr==3.2.0 huggingface-hub==0.34.4
COPY prepare.py /opt/prepare.py
RUN python /opt/prepare.py && pip freeze > /opt/python-lock.txt
COPY server.py /opt/server.py
ENV HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True HOME=/tmp OMP_NUM_THREADS=4
USER 10001:10001
CMD ["python", "/opt/server.py"]
