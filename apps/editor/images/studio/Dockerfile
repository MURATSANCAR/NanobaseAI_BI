# editor-py-studio: Kitap Tasarım Stüdyosu'nun imajı (editor-studio API'si + editor-studio-worker).
# editor-py'nin üstüne yalnız stüdyonun gerektirdiği katman: tam e-kitap denetimi (EPUBCheck 5.4.0, W3C) ve onu
# çalıştıran başsız Java; sesli okumadaki efekt karışımı için ffmpeg ve efekt aramasının metin kolu (onnxruntime).
# Öteki editör servisleri (gateway, kartlar, MCP, işçi…) editor-py'de kalır, etkilenmez.
#
#   docker build -t editor-py-studio:<etiket> --build-arg BASE=editor-py:<etiket> -f images/studio/Dockerfile .
#
# EPUBCheck yalnız resmî W3C GitHub sürümünden (github.com/w3c/epubcheck/releases/tag/v5.4.0) indirilir; zip'in
# sha256'sı sabittir (GitHub sürüm kaydındaki özetle aynı), tutmazsa derleme durur. Lisans (BSD-3-Clause) ve üçüncü
# taraf lisansları kurulu klasörde kalır: /opt/epubcheck-5.4.0/{LICENSE.txt,THIRD-PARTY.txt}. Ana jar lib/ klasörünü
# kendi Class-Path'iyle bulur; klasör yapısı bozulmaz. Denetimin komutu: editor.production.epub.full_checker.
ARG BASE=editor-py:latest
FROM ${BASE}
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/* && java -version
ARG EPUBCHECK_VERSION=5.4.0
ARG EPUBCHECK_SHA256=33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c
RUN python - "$EPUBCHECK_VERSION" "$EPUBCHECK_SHA256" <<'PY'
import hashlib, io, sys, urllib.request, zipfile
ver, want = sys.argv[1], sys.argv[2]
url = f"https://github.com/w3c/epubcheck/releases/download/v{ver}/epubcheck-{ver}.zip"
data = urllib.request.urlopen(url, timeout=600).read()
got = hashlib.sha256(data).hexdigest()
if got != want:
    sys.exit(f"epubcheck-{ver}.zip sha256 tutmadı: {got} != {want}")
z = zipfile.ZipFile(io.BytesIO(data))
keep = [n for n in z.namelist() if not n.endswith(("CHANGELOG.txt", "README.txt"))]
z.extractall("/opt", members=keep)
print(url, got, len(keep), "dosya")
PY
ENV EDITOR_EPUBCHECK_JAR=/opt/epubcheck-5.4.0/epubcheck.jar
RUN test -f /opt/epubcheck-5.4.0/LICENSE.txt && test -f /opt/epubcheck-5.4.0/THIRD-PARTY.txt \
    && java -jar "$EDITOR_EPUBCHECK_JAR" --version
# Sesli okumaya efekt sesleri (production/sfx.py, sfx_library.py): karışım ve yükseklik ölçümü ffmpeg ile (Debian
# paketi, LGPL/GPL derlemesi; ayrı süreç olarak çağrılır), efekt havuzunda metinle arama için ses-metin eşleme
# modelinin metin kolu ONNX olarak CPU'da çalışır (onnxruntime MIT, tokenizers Apache-2.0). Havuzun kendisi ve
# metin kolu imaja girmez: /data/editor/sfx birimi salt okunur bağlanır (deploy/docker-compose.yml).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/* \
    && ffmpeg -hide_banner -version | head -1 \
    && pip install --no-cache-dir onnxruntime==1.30.0 tokenizers==0.23.2 \
    && python -c "import onnxruntime, tokenizers; print(onnxruntime.__version__, tokenizers.__version__)"
