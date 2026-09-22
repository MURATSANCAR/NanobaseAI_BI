# OpenDataLoader PDF (Apache-2.0): re-reads a PDF's digital text layer with its own XY-Cut++
# reading order. Benchmark tooling only: does it recover pages whose layer came out scrambled?
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends default-jre-headless \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir opendataloader-pdf pymupdf
