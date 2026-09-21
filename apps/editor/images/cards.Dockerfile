ARG EDITOR_BASE_IMAGE
FROM ${EDITOR_BASE_IMAGE}
COPY src/editor/presentation.py src/editor/card_api.py /app/src/editor/
