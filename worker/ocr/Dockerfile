# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project
COPY app ./app
RUN uv sync --no-dev

# The models come from PaddlePaddle's own Hugging Face organization (its official ONNX exports), at pinned
# revisions and checked against their hashes: the pod never downloads anything when it runs.
FROM builder AS model
ARG DET_MODEL_REPO=PaddlePaddle/PP-OCRv6_tiny_det_onnx
ARG DET_MODEL_REVISION=2ba1506c0380b8f0b03dd142459aac66d4421f6c
ARG DET_MODEL_SHA256=193bab7a04fca699a6c82e6abb5b81bdb28177f0abd4062552b04908dafb19f8
ARG REC_MODEL_REPO=PaddlePaddle/PP-OCRv6_tiny_rec_onnx
ARG REC_MODEL_REVISION=2612ab37152ae0a677521bae4e1e3d4fb4cf7c30
ARG REC_MODEL_SHA256=9ef676d6ed3c88256a2d92c640c44f25b0c40947e111b14b8be8f594091563e6
RUN /app/.venv/bin/python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('${DET_MODEL_REPO}', revision='${DET_MODEL_REVISION}', \
local_dir='/models/PP-OCRv6_tiny_det_onnx', allow_patterns=['inference.onnx', 'inference.yml']); \
snapshot_download('${REC_MODEL_REPO}', revision='${REC_MODEL_REVISION}', \
local_dir='/models/PP-OCRv6_tiny_rec_onnx', allow_patterns=['inference.onnx', 'inference.yml'])" \
    && echo "${DET_MODEL_SHA256}  /models/PP-OCRv6_tiny_det_onnx/inference.onnx" | sha256sum -c - \
    && echo "${REC_MODEL_SHA256}  /models/PP-OCRv6_tiny_rec_onnx/inference.onnx" | sha256sum -c - \
    && rm -rf /models/*/.cache

FROM python:3.12-slim AS runtime
# pip is a build tool: the runtime image never installs anything, and the pip bundled with the base
# image carries known CVEs. Removed rather than upgraded, so there is nothing left to keep patched.
RUN python -m pip uninstall -y pip
# OpenCV (a dependency of PaddleOCR) loads these two at import.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 worker
WORKDIR /app
COPY --from=builder --chown=worker:worker /app/.venv /app/.venv
COPY --from=builder --chown=worker:worker /app/app /app/app
COPY --from=model --chown=worker:worker /models /models

USER worker
ENV PATH="/app/.venv/bin:$PATH"
# HOME is where PaddleOCR keeps its small working files: /tmp, the one writable place on a read-only root
# filesystem. It looks for no model hoster (the model is in the image).
ENV HOME=/tmp
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
ENV MODELS_DIR=/models
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD celery -A app.celery_app inspect ping -d celery@$HOSTNAME || exit 1
# The model is loaded once per child process: keep the concurrency to what the pod's memory allows (about
# 1 GB each), and ONNX_INTRA_OP_THREADS to the CPUs the pod is given divided by it.
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "-Q", "document_ocr", "-c", "2"]
