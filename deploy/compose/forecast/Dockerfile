# NanobaseAI BI — Forecast API (:8793). WITH_TIMESFM=1 adds the learned engine (CPU torch).
FROM python:3.11-slim
ARG WITH_TIMESFM=1
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models/forecast
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* && useradd -u 10001 -m appuser
WORKDIR /app
COPY backend/forecasting/requirements.txt backend/forecasting/requirements-timesfm.txt /tmp/
RUN pip install -r /tmp/requirements.txt \
    && if [ "$WITH_TIMESFM" = "1" ]; then pip install -r /tmp/requirements-timesfm.txt; fi
COPY backend/forecasting /app/backend/forecasting
RUN mkdir -p /models/forecast && chown -R 10001:10001 /app /models
ENV PYTHONPATH=/app/backend
USER 10001
EXPOSE 8793
CMD ["uvicorn", "forecasting.app.main:app", "--host", "0.0.0.0", "--port", "8793", "--workers", "1"]
