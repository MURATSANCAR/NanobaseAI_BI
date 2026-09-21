ARG EDITOR_BASE_IMAGE
FROM ${EDITOR_BASE_IMAGE}
COPY src/editor/presentation.py src/editor/card_api.py src/editor/read_model.py /app/src/editor/
