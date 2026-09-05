# NanobaseAI BI — yerel LLM servisi (llama.cpp, CUDA, MTP spekülatif çözümleme)
# Kaynaktan derlenir; LLAMA_CPP_REF ile sürüm sabitlenir.
ARG CUDA_VERSION=12.6.3
FROM nvidia/cuda:${CUDA_VERSION}-devel-ubuntu24.04 AS build
ARG LLAMA_CPP_REF=refs/pull/28243/head
ARG CUDA_ARCH=86
RUN apt-get update && apt-get install -y --no-install-recommends \
      git cmake build-essential libcurl4-openssl-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 https://github.com/ggml-org/llama.cpp . \
    && git fetch --depth 1 origin "${LLAMA_CPP_REF}" \
    && git checkout FETCH_HEAD
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON \
      -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCH} -DLLAMA_CURL=ON -DGGML_NATIVE=OFF \
    && cmake --build build --config Release -j "$(nproc)" --target llama-server

FROM nvidia/cuda:${CUDA_VERSION}-runtime-ubuntu24.04
RUN apt-get update && apt-get install -y --no-install-recommends libcurl4 curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/bin/ /opt/llm/bin/
COPY entrypoint.sh /opt/llm/entrypoint.sh
RUN chmod +x /opt/llm/entrypoint.sh
ENV LD_LIBRARY_PATH=/opt/llm/bin
EXPOSE 8080
ENTRYPOINT ["/opt/llm/entrypoint.sh"]
