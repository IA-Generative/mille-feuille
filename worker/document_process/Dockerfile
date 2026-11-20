# syntax=docker/dockerfile:1

FROM python:3.15-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project
COPY app ./app
RUN uv sync --no-dev

FROM python:3.15-slim AS runtime
# pip est un outil de build : l\'image d\'exécution n\'installe rien, et le pip livré avec l\'image de base porte des CVE
# connues. Retiré plutôt que mis à jour, il n\'y a rien à maintenir.
RUN python -m pip uninstall -y pip
# tesseract-ocr-fra : liteparse embarque son propre moteur OCR, mais pas les
# données de langue - c'est ce paquet qui rend ocr_language="fra" utilisable.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr-fra \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 worker
WORKDIR /app
COPY --from=builder --chown=worker:worker /app/.venv /app/.venv
COPY --from=builder --chown=worker:worker /app/app /app/app
USER worker
ENV PATH="/app/.venv/bin:$PATH"
ENV TESSDATA_PATH="/usr/share/tesseract-ocr/5/tessdata"
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD celery -A app.celery_app inspect ping -d celery@$HOSTNAME || exit 1
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]
