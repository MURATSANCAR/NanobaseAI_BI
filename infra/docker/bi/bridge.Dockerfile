# Semantic bridge (NL->SQL motoru) — venv/systemd yerine taşınabilir imaj.
# ODBC/FreeTDS imaja gömülü: host'a hiçbir sürücü kurulmaz, müşteride tek `docker compose up`.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        unixodbc unixodbc-dev tdsodbc freetds-bin freetds-dev gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# FreeTDS'i ODBC sürücüsü olarak kaydet (pyodbc bunu 'FreeTDS' adıyla bulur — connection.json'daki ad).
RUN printf '[FreeTDS]\nDescription=FreeTDS\nDriver=/usr/lib/x86_64-linux-gnu/odbc/libtdsodbc.so\n' \
    > /etc/odbcinst.ini

WORKDIR /app
# Bağımlılıklar önce: kaynak değişince katman yeniden kurulmaz.
COPY backend/requirements-semantic.txt /app/backend/requirements-semantic.txt
RUN pip install --no-cache-dir -r /app/backend/requirements-semantic.txt \
        pyodbc psycopg2-binary "uvicorn[standard]"

COPY backend /app/backend
COPY configs /app/configs

ENV PYTHONPATH=/app/backend
EXPOSE 8795
CMD ["uvicorn", "semantic_bridge.app:app", "--host", "0.0.0.0", "--port", "8795", \
     "--workers", "1", "--timeout-keep-alive", "30"]
