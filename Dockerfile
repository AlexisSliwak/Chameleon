FROM python:3.11-slim@sha256:673719e071ecf27434fd2635bbd8d00f49f4fdd81f243143438a42ced8bedf60 AS semantic-model
COPY deployment/model.json deployment/fetch_model.py /deployment/
RUN python /deployment/fetch_model.py /deployment/model.json /opt/chameleon-model

FROM python:3.11-slim@sha256:673719e071ecf27434fd2635bbd8d00f49f4fdd81f243143438a42ced8bedf60 AS semantic-build

RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates && rm -rf /var/lib/apt/lists/*
RUN git init /llama && cd /llama && git remote add origin https://github.com/ggml-org/llama.cpp.git && git fetch --depth 1 origin 889f2ec96deacbc2d8a9a67dbe181eaa43a2fb3b && git checkout --detach FETCH_HEAD
RUN cmake -S /llama -B /llama/build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF -DGGML_CPU_ALL_VARIANTS=ON -DGGML_BACKEND_DL=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_SERVER=ON -DLLAMA_CURL=OFF && cmake --build /llama/build --target llama-server -j 4

FROM python:3.11-slim@sha256:673719e071ecf27434fd2635bbd8d00f49f4fdd81f243143438a42ced8bedf60

WORKDIR /app

# System libs some renderer backends (e.g. skia) need at runtime, plus git
# (build-time only) so pip can install cr-renderer straight from its repo.
# Harmless to include even if your engine doesn't end up using them.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1 \
    libegl1 \
    libglib2.0-0 \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# If you add dependencies for your own resize() approach, add them to
# requirements.txt above — everything needed must install at BUILD time.
# Stage-one scoring runs with --network none, so nothing at runtime can
# reach out to the internet (no pip installs, no API calls, no model
# downloads at run time — pull those in during the build instead).

COPY chameleon_design_schema_v0.9.json .
COPY brand_kit/ ./brand_kit/
COPY renderer/ ./renderer/
COPY --from=semantic-build /usr/lib/x86_64-linux-gnu/libgomp.so.1* /usr/lib/x86_64-linux-gnu/
COPY --from=semantic-build /llama/build/bin/ /opt/llama/
COPY --from=semantic-model /opt/chameleon-model/ /opt/chameleon-model/
ENV LD_LIBRARY_PATH=/opt/llama
RUN /opt/llama/llama-server --version
ENV CHAMELEON_MODEL_DIR=/opt/chameleon-model CHAMELEON_LLAMA_SERVER=/opt/llama/llama-server

COPY engine/ ./engine/
COPY deployment/*LICENSE deployment/NOTICES.txt /opt/chameleon-notices/

# input/ and output/ are mounted as volumes at run time (see README) —
# not baked into the image.
RUN mkdir -p /app/input /app/output

ENTRYPOINT ["python", "-m", "engine.main"]
