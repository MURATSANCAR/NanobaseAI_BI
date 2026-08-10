FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd -u 10001 -m appuser
COPY requirements.txt* ./
RUN pip install --no-cache-dir -r requirements.txt 2>/dev/null || pip install --no-cache-dir fastapi uvicorn
COPY . /app/nanobase_api
USER 10001
EXPOSE 8790
CMD ["uvicorn", "nanobase_api.main:app", "--host", "0.0.0.0", "--port", "8790", "--workers", "2"]
