# OCRmyPDF (Tesseract 5) with Turkish — a classic, non-generative OCR baseline: it can misread
# a letter but cannot rewrite a word. Benchmark tooling only (editor.measure_ocr --external).
FROM jbarlow83/ocrmypdf:v17.12.1
ADD https://github.com/tesseract-ocr/tessdata_best/raw/main/tur.traineddata /usr/share/tesseract-ocr/5/tessdata/tur.traineddata
USER root
RUN chmod 644 /usr/share/tesseract-ocr/5/tessdata/tur.traineddata
