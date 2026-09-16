FROM python:3.12-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1
WORKDIR /app
COPY backend/requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY backend /app
RUN useradd --uid 10001 --create-home editor
USER 10001:10001
CMD ["uvicorn", "editor.api:app", "--host", "0.0.0.0", "--port", "8810", "--no-access-log"]

FROM runtime AS document
USER root
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-tur tesseract-ocr-eng fonts-dejavu-core libglib2.0-0 libgl1 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY backend/document-requirements.lock /app/document-requirements.lock
RUN pip install --no-cache-dir --require-hashes -r document-requirements.lock
# Assets are downloaded at build time only, never when a customer opens a book.
RUN HF_HUB_OFFLINE=0 docling-tools models download --output-dir /opt/docling-models layout tableformer
ENV DOCLING_ARTIFACTS_PATH=/opt/docling-models OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
USER 10001:10001
ENTRYPOINT ["python", "-m", "editor.ingestion"]
