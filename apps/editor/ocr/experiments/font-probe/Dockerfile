FROM nanobase-editor-document:upload-queue-v2-20260917
USER root
COPY requirements.lock /tmp/font-probe.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/font-probe.lock
USER 10001:10001
ENTRYPOINT ["python"]
