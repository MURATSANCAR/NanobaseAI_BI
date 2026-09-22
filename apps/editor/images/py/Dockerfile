# editor-py: gateway, MCP servers, Temporal worker (one image, three commands).
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/src
WORKDIR /app
# Son okuma yazım denetimi (proofing/spelling, name_spelling): Türkçe hunspell sözlüğü /app/data/hunspell/tr_TR.{dic,aff}
RUN apt-get update && apt-get install -y --no-install-recommends hunspell-tr \
    && mkdir -p /app/data/hunspell && cp /usr/share/hunspell/tr_TR.aff /usr/share/hunspell/tr_TR.dic /app/data/hunspell/ \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
COPY src /app/src
COPY db /app/db
COPY deploy/models.yaml /app/deploy/models.yaml
COPY tests /app/tests
ARG CODE_VERSION=dev
ENV EDITOR_CODE_VERSION=${CODE_VERSION}
