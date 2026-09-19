# editor-py: gateway, MCP servers, Temporal worker (one image, three commands).
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/src
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
COPY src /app/src
COPY db /app/db
COPY deploy/models.yaml /app/deploy/models.yaml
COPY tests /app/tests
ARG CODE_VERSION=dev
ENV EDITOR_CODE_VERSION=${CODE_VERSION}
