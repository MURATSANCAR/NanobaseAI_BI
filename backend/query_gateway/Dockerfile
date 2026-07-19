FROM python:3.12-slim

RUN useradd -u 10001 -m qg && \
    apt-get update && apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/query_gateway/requirements.txt
RUN pip install --no-cache-dir -r /app/query_gateway/requirements.txt

COPY . /app/query_gateway
ENV PYTHONPATH=/app
ENV QUERY_GATEWAY_PORT=8792
USER 10001
EXPOSE 8792
CMD ["uvicorn", "query_gateway.app:app", "--host", "0.0.0.0", "--port", "8792"]
