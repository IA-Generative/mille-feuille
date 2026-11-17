# syntax=docker/dockerfile:1
#
# Worker de rendu de documents (issue #146) : remplit un modèle ODT puis produit un PDF avec LibreOffice.
# Les polices installées ici décident de la fidélité du PDF : une police absente est remplacée sans prévenir.

FROM python:3.12-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
# pip est un outil de build : l\'image d\'exécution n\'installe rien, et le pip livré avec l\'image de base porte des CVE
# connues. Retiré plutôt que mis à jour, il n\'y a rien à maintenir.
RUN python -m pip uninstall -y pip
# Writer seul, sans interface : l'image reste à ~700 Mo. Les polices métriquement compatibles avec
# Arial/Times/Calibri/Cambria (Liberation, Carlito, Caladea) évitent les décalages de mise en page.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer-nogui \
    fonts-liberation fonts-dejavu-core fonts-crosextra-carlito fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 worker
WORKDIR /app
COPY --from=builder --chown=worker:worker /app/.venv /app/.venv
COPY --from=builder --chown=worker:worker /app/app /app/app
USER worker
ENV PATH="/app/.venv/bin:$PATH"
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD celery -A app.celery_app inspect ping -d celery@$HOSTNAME || exit 1
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "--queues=document_render", "--concurrency=2"]
