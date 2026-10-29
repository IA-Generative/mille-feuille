# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project
COPY app ./app
RUN uv sync --no-dev

FROM python:3.12-slim AS runtime
# pip est un outil de build : l'image d'exécution n'installe rien, et le pip livré avec l'image de base porte des CVE
# connues. Retiré plutôt que mis à jour, il n'y a rien à maintenir.
RUN python -m pip uninstall -y pip
RUN useradd --create-home --uid 1000 worker
WORKDIR /app
COPY --from=builder --chown=worker:worker /app/.venv /app/.venv
COPY --from=builder --chown=worker:worker /app/app /app/app

USER worker
ENV PATH="/app/.venv/bin:$PATH"
ENV HOME=/tmp
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD celery -A app.celery_app inspect ping -d celery@$HOSTNAME || exit 1
# Aucun modèle local : le pod attend le hub, la concurrence ne coûte que des connexions.
CMD ["celery", "-A", "app.celery_app", "worker", "--loglevel=info", "-Q", "document_vision", "-c", "4"]
