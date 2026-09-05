# NanobaseAI BI — API + iş kuyruğu işçisi + şema indeksleyici (tek imaj)
# Bağlam: depo kökü (deploy/compose/docker-compose.yml → context: ../..)
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 10001 -m appuser
WORKDIR /app
COPY backend/nanobase_api/requirements.txt /tmp/req-api.txt
COPY backend/bridge/requirements.txt /tmp/req-bridge.txt
COPY backend/query_gateway/requirements.txt /tmp/req-gateway.txt
RUN pip install -r /tmp/req-api.txt -r /tmp/req-bridge.txt -r /tmp/req-gateway.txt \
      "psycopg[binary]>=3.1" "qdrant-client>=1.9"
COPY backend/nanobase_api /app/backend/nanobase_api
COPY backend/nanobase_awel /app/backend/nanobase_awel
COPY backend/bridge /app/backend/bridge
COPY backend/query_gateway /app/backend/query_gateway
COPY backend/scripts /app/backend/scripts
COPY tools/schema-indexer /app/tools/schema-indexer
COPY configs /app/configs
RUN mkdir -p /data /secrets && chown -R 10001:10001 /app /data /secrets
ENV PYTHONPATH=/app/backend
USER 10001
EXPOSE 8790
CMD ["uvicorn", "nanobase_api.app:app", "--host", "0.0.0.0", "--port", "8790", "--workers", "2"]
