# editor-py: gateway, MCP servers, Temporal worker (one image, three commands).
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app/src
WORKDIR /app
# Son okuma yazım denetimi (proofing/spelling, name_spelling): Türkçe hunspell sözlüğü /app/data/hunspell/tr_TR.{dic,aff}
# Baskı PDF'i (editor.production.prepress): ghostscript CMYK/PDF-X ve varsayılan ICC profilleri.
RUN apt-get update && apt-get install -y --no-install-recommends hunspell-tr ghostscript \
    && mkdir -p /app/data/hunspell && cp /usr/share/hunspell/tr_TR.aff /usr/share/hunspell/tr_TR.dic /app/data/hunspell/ \
    && rm -rf /var/lib/apt/lists/*
# Kapak yazısı fontları (editor.cover_text), OFL, google/fonts sabit sürüm.
ARG GFONTS=23e54b51ddffbc7713c583748e3bd86f62b1fa4a
# Andika: basıma hazırlıkta çocuk kitabı metin fontu (editor.production.spec).
RUN mkdir -p /app/data/fonts && cd /app/data/fonts && python -c "import sys,urllib.request,urllib.parse; \
[urllib.request.urlretrieve('https://raw.githubusercontent.com/google/fonts/'+sys.argv[1]+'/ofl/'+urllib.parse.quote(p), p.split('/')[1]) for p in \
 ['baloo2/Baloo2[wght].ttf','playfairdisplay/PlayfairDisplay[wght].ttf', \
  'cormorantgaramond/CormorantGaramond[wght].ttf','notoserif/NotoSerif[wdth,wght].ttf', \
  'andika/Andika-Regular.ttf','andika/Andika-Bold.ttf','andika/Andika-Italic.ttf']]" $GFONTS \
    && ls -la /app/data/fonts
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
COPY src /app/src
COPY db /app/db
COPY deploy/models.yaml /app/deploy/models.yaml
COPY tests /app/tests
ARG CODE_VERSION=dev
ENV EDITOR_CODE_VERSION=${CODE_VERSION}
