# NanobaseAI BI — Query Gateway (müşteri SQL'i yalnız buradan, salt-okunur, izin listeli)
FROM python:3.12-slim
RUN useradd -u 10001 -m qg \
    && apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/query_gateway/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/query_gateway /app/query_gateway
ENV PYTHONPATH=/app QUERY_GATEWAY_PORT=8792 PYTHONUNBUFFERED=1
USER 10001
EXPOSE 8792
CMD ["uvicorn", "query_gateway.app:app", "--host", "0.0.0.0", "--port", "8792", "--workers", "2"]
