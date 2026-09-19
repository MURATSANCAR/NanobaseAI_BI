# Giriş servisi (Timaş Active Directory) — sunucudaki timas-login ile aynı kod.
# Oturumlar bi_login hacmindeki SQLite'ta; AD ayar dosyası secrets/ad/ klasöründen okunur.
FROM python:3.12-slim

WORKDIR /app
COPY scripts/server/portal-login/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY scripts/server/portal-login/server.py /app/server.py

ENV LOGIN_HOST=0.0.0.0 \
    SESSION_DB=/data/sessions.sqlite \
    AD_CONFIG_FILE=/app/ad/timas-ad.json
EXPOSE 8796
CMD ["python", "/app/server.py"]
