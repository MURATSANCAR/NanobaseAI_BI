ARG EDITOR_BASE_IMAGE
FROM ${EDITOR_BASE_IMAGE}
COPY src/editor/presentation.py src/editor/card_api.py src/editor/read_model.py src/editor/graph.py /app/src/editor/
# card_api, son okuma etiketlerini editor.proofing._labels'tan okur (denetimler yüklenmez)
COPY src/editor/proofing /app/src/editor/proofing/
