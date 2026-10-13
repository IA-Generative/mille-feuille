# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
WORKDIR /app
# Pas de cache uv dans l'image : ni les roues de torch (centaines de Mo) ni leur copie ne restent dans une couche, ce
# qui allège aussi le stockage éphémère du build Kaniko en CI.
ENV UV_NO_CACHE=1
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
# Le modèle GLiNER2.5 (extraction d'entités, CPU) est téléchargé au build et embarqué dans l'image : le worker ne
# sort pas sur Internet au démarrage (HF_HUB_OFFLINE). Même valeur que GLINER_MODEL (app/config.py).
ARG GLINER_MODEL=fastino/gliner2.5-multi-v1
ENV HF_HOME=/app/.cache/huggingface GLINER_MODEL=$GLINER_MODEL
RUN python -c "import os; from gliner2 import AutoExtractor; AutoExtractor.from_pretrained(os.environ['GLINER_MODEL'], map_location='cpu')"
ENV HF_HUB_OFFLINE=1
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD celery -A app.celery_app inspect ping -d celery@$HOSTNAME || exit 1
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]
