# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project
COPY app ./app
RUN uv sync --no-dev

FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 1000 worker
WORKDIR /app
COPY --from=builder --chown=worker:worker /app/.venv /app/.venv
COPY --from=builder --chown=worker:worker /app/app /app/app
RUN mkdir -p /app/.cache && chown worker:worker /app/.cache
USER worker
ENV PATH="/app/.venv/bin:$PATH"
# Le modèle CLIP (classification visuelle, CPU) est téléchargé au build et embarqué dans l'image : le worker ne
# sort pas sur Internet au démarrage (HF_HUB_OFFLINE). Même valeur que CLIP_MODEL (app/config.py).
ARG CLIP_MODEL=openai/clip-vit-base-patch32
ENV HF_HOME=/app/.cache/huggingface CLIP_MODEL=$CLIP_MODEL
RUN python -c "import os; from transformers import CLIPModel, CLIPProcessor; m = os.environ['CLIP_MODEL']; CLIPModel.from_pretrained(m); CLIPProcessor.from_pretrained(m)"
ENV HF_HUB_OFFLINE=1
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD celery -A app.celery_app inspect ping -d celery@$HOSTNAME || exit 1
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]
